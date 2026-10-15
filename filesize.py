#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.9"
# ///

"""filesize — 统计文件/目录的总大小，同时输出人类可读大小与字节数。

计算什么:
  传入单个文件      该文件的大小
  传入多个文件      每个文件一行，最后加「总计」行
  传入一个目录      目录下第一层文件的总大小（子目录本身不计）
  传入多个目录      每个目录一行，最后加「总计」行
  什么都不传        等价于传入当前目录「.」

不计算什么（默认行为，可用对应选项开启）:
  隐藏文件 / 隐藏子目录     名字以 . 开头；用 -a 开启统计
  子目录里的内容            用 -r 开启递归，-d N 限制深度
  符号链接指向的目标        用 -L 开启跟随
  目录自身占用的空间        用 --du 开启（与 du 的计数方式一致）
  指定后缀以外的文件        用 -e/--ext 开启后缀过滤
  被 --exclude 匹配的条目

用法示例:
  ./filesize                         # 当前目录下第一层文件的总大小
  ./filesize a.txt                   # 单个文件
  ./filesize a.txt b.txt c.mp4       # 多个文件，自动追加「总计」
  ./filesize -r project/             # 递归统计子目录（含孙目录…）
  ./filesize -r -d 2 project/        # 只递归到第 2 层
  ./filesize -r -e .py project/      # 递归只统计所有 .py 文件
  ./filesize -u -r data/             # 按磁盘实际占用统计（稀疏/压缩文件更真实）
  ./filesize --exclude '*.tmp' -r .  # 排除匹配项

全部选项与规则细节见: ./filesize --help
"""

import argparse
import fnmatch
import os
import stat
import sys

VERSION = "1.3.0"


def stat_size(st, usage: bool) -> int:
    """从 stat 结果取大小。

    默认返回逻辑大小（st_size，即 ls / Finder 显示的值）；
    usage=True 时返回磁盘实际占用（st_blocks × 512），
    对稀疏文件、APFS 压缩文件而言占用往往明显小于逻辑大小。
    """
    if usage:
        blocks = getattr(st, "st_blocks", None)
        return st.st_size if blocks is None else blocks * 512
    return st.st_size


def human(n: int, si: bool) -> str:
    """字节数 → 人类可读字符串。

    si=False（默认）按 1024 进制输出 KiB/MiB/GiB；
    si=True 按 1000 进制输出 KB/MB/GB。
    精度规则: B 取整；KiB/KB、MiB/MB 保留 1 位小数；GiB/GB 及以上保留 2 位小数。
    落在 MiB/MB 量级、且换算为 GiB/GB 后四舍五入非 0.00 时，额外附带换算值，
    如 "512.0 MiB (0.50 GiB)"，便于直观读出「零点几 G」。
    """
    base = 1000 if si else 1024
    units = ("B", "KB", "MB", "GB", "TB", "PB") if si else ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    v = float(n)
    for i, u in enumerate(units):
        if v < base or i == len(units) - 1:
            if i == 0:
                return f"{int(v)} B"
            digits = 1 if i <= 2 else 2  # K/M 级 1 位小数，G 及以上 2 位小数
            s = f"{v:.{digits}f} {u}"
            if i == 2:  # M 级附带 G 换算
                g = v / base
                if round(g, 2) >= 0.01:  # 换算值四舍五入后非 0.00 才附带
                    s += f" ({g:.2f} {'GB' if si else 'GiB'})"
            return s
        v /= base
    return f"{n} B"  # 不可达，仅为兜底


def excluded(rel: str, name: str, patterns) -> bool:
    """--exclude 匹配：相对路径或文件名任一命中即排除。

    fnmatch 规则，`*` 可以跨目录层级匹配（如 '*.tmp' 能命中深层文件）。
    命中目录时整棵子树都会被跳过。
    """
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) for p in patterns)


def matches_ext(name: str, exts) -> bool:
    """-e/--ext 后缀过滤：文件名字符串以任一指定后缀结尾即命中。

    exts 为 None 表示不过滤（统计所有文件）；
    否则按条目名字匹配（不区分大小写），如 '.py' 也能命中 'a.tar.py' 的结尾。
    """
    if exts is None:
        return True
    low = name.lower()
    return any(low.endswith(e) for e in exts)


def normalize_exts(ext_args):
    """把命令行给的 -e 参数规范化为统一小写、带前导点的后缀集合。

    支持 '.py' 与 'py' 两种写法；'-e .tar.gz' 这类复合后缀原样保留。
    未传 -e（None）或全部为空时返回 None（表示不过滤）。
    """
    out = set()
    for e in (ext_args or []):
        e = e.strip()
        if not e:
            continue
        out.add(e.lower() if e.startswith(".") else "." + e.lower())
    return frozenset(out) if out else None


def scan_dir(root, follow, limit, excludes, du_mode, usage, seen, include_hidden, exts):
    """统计一个目录子树的总字节数。

    用显式栈迭代遍历（而非递归），深层目录不会触发 Python 递归上限。
    limit: None 表示不限深度；整数表示只统计深度 <= limit 的条目（根=0）。
    include_hidden: False 时跳过以「.」开头的隐藏文件/隐藏子目录（整棵不统计）。
    exts: 非 None 时只统计文件名以指定后缀结尾的文件（目录照常遍历）。
    返回 (总字节数, 错误数)。
    """
    total, errors = 0, 0
    if follow:
        # 根目录自身 inode 也入去重集合，防止符号链接环回根目录重复扫描
        try:
            st0 = os.stat(root)
            seen.add((st0.st_dev, st0.st_ino))
        except OSError:
            pass
    stack = [(root, "", 0)]
    while stack:
        dpath, rel, depth = stack.pop()

        if du_mode:  # 目录自身的 inode 也计入（du 兼容）
            try:
                st = os.stat(dpath) if follow else os.lstat(dpath)
                total += stat_size(st, usage)
            except OSError:
                pass

        if limit is not None and depth >= limit:
            continue  # 到达深度上限：不再展开子项

        try:
            it = os.scandir(dpath)
        except OSError as err:
            errors += 1
            print(f"filesize: 无法读取目录 {dpath}: {err.strerror or err}", file=sys.stderr)
            continue
        with it:
            for e in it:
                erel = os.path.join(rel, e.name)
                if not include_hidden and e.name.startswith("."):
                    continue  # 默认跳过隐藏文件/目录；命中目录则整棵不统计
                if excluded(erel, e.name, excludes):
                    continue
                try:
                    st = e.stat(follow_symlinks=follow)
                    isdir = stat.S_ISDIR(st.st_mode)
                except OSError as err:
                    errors += 1
                    print(f"filesize: 无法访问 {e.path}: {err.strerror or err}", file=sys.stderr)
                    continue

                key = (st.st_dev, st.st_ino)
                if isdir:
                    if follow and key in seen:
                        continue  # 符号链接环/重复目录：已统计过
                    seen.add(key)
                    stack.append((e.path, erel, depth + 1))
                else:
                    if not matches_ext(e.name, exts):
                        continue  # 后缀过滤：只统计指定后缀的文件
                    if key in seen:
                        continue  # 硬链接：同一 inode 只计一次
                    seen.add(key)
                    total += stat_size(st, usage)
    return total, errors


def scan_arg(path, follow, limit, excludes, du_mode, usage, include_hidden, exts):
    """统计单个命令行参数；返回 (总字节数, 错误数)。"""
    try:
        st = os.stat(path) if follow else os.lstat(path)
    except OSError as err:
        print(f"filesize: 无法访问 {path}: {err.strerror or err}", file=sys.stderr)
        return 0, 1
    if stat.S_ISDIR(st.st_mode):
        return scan_dir(path, follow, limit, excludes, du_mode, usage, set(), include_hidden, exts)
    return stat_size(st, usage), 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="filesize",
        description=(
            "统计文件/目录的总大小，同时输出人类可读大小与字节数。\n"
            "\n"
            "计算什么:\n"
            "  传入单个文件       该文件的大小\n"
            "  传入多个文件       每个文件一行，最后加「总计」行\n"
            "  传入一个目录       目录下第一层文件的总大小（子目录本身不计、内容不展开）\n"
            "  传入多个目录       每个目录一行，最后加「总计」行\n"
            "  什么都不传         等价于传入当前目录「.」\n"
            "\n"
            "不计算什么（默认行为，用对应选项开启）:\n"
            "  隐藏文件 / 隐藏子目录     名字以 . 开头；用 -a 开启统计\n"
            "  子目录里的内容            用 -r 开启递归，-d N 限制深度\n"
            "  符号链接指向的目标        用 -L 开启跟随\n"
            "  目录自身占用的空间        用 --du 开启（与 du 的计数方式一致）\n"
            "  指定后缀以外的文件        用 -e/--ext 开启后缀过滤\n"
            "  被 --exclude 匹配的条目"
        ),
        epilog=(
            "规则细节:\n"
            "  · 硬链接只计一次（同一文件被多个名字引用不重复累计）。\n"
            "  · 隐藏判断、后缀判断、--exclude 均针对目录遍历时发现的条目；\n"
            "    命令行直接给出的路径不受这些过滤影响。\n"
            "  · 不同参数重复传入按各自统计（如 filesize dir dir/sub 会重复累计）。\n"
            "  · 无法读取的路径/目录会报错到 stderr 并继续统计，退出码为 1。\n"
            "  · 输出格式: <人类可读大小>  <字节数>  <路径>。\n"
            "  · 精度: K/M 级保留 1 位小数，G 及以上保留 2 位小数；\n"
            "    M 级文件若换算成 G 后四舍五入非 0.00，额外附带换算值（如 512.0 MiB (0.50 GiB)）。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="*", metavar="路径", default=["."],
                        help="文件或目录，可多个；默认当前目录「.」")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="递归统计子目录里的文件（含孙目录…）；默认只统计目录下第一层文件")
    parser.add_argument("-d", "--max-depth", type=int, metavar="N",
                        help="只递归到第 N 层（0=只算根目录本身），隐含 -r")
    parser.add_argument("-a", "--all", action="store_true",
                        help="把隐藏文件、隐藏子目录也统计进来（默认跳过名字以 . 开头的条目）")
    parser.add_argument("-e", "--ext", action="append", metavar="EXT",
                        help="只统计文件名以该后缀结尾的文件，可重复（如 -e .py -e .md）；"
                             "不区分大小写，'.py' 与 'py' 写法均可；"
                             "配合 -r 时子目录里的同名后缀文件也会统计；"
                             "隐藏文件仍受 -a 规则控制")
    parser.add_argument("-L", "--follow", action="store_true",
                        help="跟随符号链接统计其目标（自动防循环）；默认只统计链接本身")
    parser.add_argument("-u", "--usage", action="store_true",
                        help="按磁盘实际占用统计（稀疏/压缩文件更真实）；默认逻辑大小")
    parser.add_argument("--du", action="store_true",
                        help="目录自身占用的空间也计入（与 du 一致）；默认只统计文件内容")
    parser.add_argument("--exclude", action="append", metavar="GLOB", default=[],
                        help="跳过匹配的条目，可重复（fnmatch 规则，* 可跨层级）；"
                             "命中子目录则整棵跳过；对目录内条目生效")
    parser.add_argument("--si", action="store_true",
                        help="按 1000 进制输出（KB/MB/GB）；默认 1024 进制（KiB/MiB/GiB）")
    parser.add_argument("--sort", action="store_true",
                        help="多个路径时按大小降序排列输出")
    parser.add_argument("--total", action="store_true",
                        help="即使只有 1 个路径也输出「总计」行")
    parser.add_argument("--no-human", action="store_true",
                        help="只输出原始字节数和路径（便于脚本解析）")
    parser.add_argument("--version", action="version", version=f"filesize {VERSION}")

    args = parser.parse_args(argv)

    if args.max_depth is not None:
        if args.max_depth < 0:
            parser.error("--max-depth 不能为负数")
        limit = args.max_depth
    else:
        limit = 1 if not args.recursive else None

    ext_set = normalize_exts(args.ext)
    if args.ext and ext_set is None:
        parser.error("--ext 不能为空")

    results = []
    grand = 0
    any_error = False
    for path in args.paths:
        size, errs = scan_arg(path, args.follow, limit, args.exclude, args.du, args.usage,
                              args.all, ext_set)
        results.append((size, path, errs))
        grand += size
        any_error = any_error or errs > 0

    if args.sort:
        results.sort(key=lambda r: r[0], reverse=True)

    show_total = args.total or len(results) > 1
    width = max(len(f"{s:,}") for s, _, _ in results) if results and not args.no_human else 0
    # 人类可读列按内容动态取宽（MiB 级附带 G 换算后行会变长，固定 9 列会挤坏对齐）
    hwidth = max(len(human(s, args.si)) for s, _, _ in results) if results and not args.no_human else 0

    try:
        for size, path, _ in results:
            if args.no_human:
                print(f"{size}\t{path}")
            else:
                print(f"{human(size, args.si):>{hwidth}}  {size:>{width},}  {path}")
        if show_total:
            if args.no_human:
                print(f"{grand}\t总计")
            else:
                print(f"{human(grand, args.si):>{hwidth}}  {grand:>{width},}  总计")
    except BrokenPipeError:
        raise  # 交给外层安静处理（如管道被 head 截断）

    return 1 if any_error else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
#（注：内容由AI生成）
