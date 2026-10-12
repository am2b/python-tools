#!/usr/bin/env -S uv run

# /// script
# requires-python = ">=3.8"
# ///

#=tools
#$从"文件分片池"里面恢复一个文件,默认恢复到命令行的当前工作目录
#@usage:
#@script pool_path manifest.txt [out_path]
#@注意:
#@pool_path就是分片文件所在的路径
#@如果manifest.txt文件名中包含空格的话,那么需要用单引号将其括起来

import sys
import os
import shutil
import subprocess

def resolve_path(s: str):
    s1 = os.path.expanduser(s)
    s2 = os.path.expandvars(s1)
    return s2

def parse_manifest(file_path: str):
    orig_filename = None
    chunk_files = []

    section = None

    with open(file_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            #raw_line末尾有换行符\n
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            #跳过空行
            if not stripped:
                continue
            #跳过注释行
            if stripped.startswith("#"):
                continue

            #区块切换标记
            if stripped == "[原始文件信息]":
                section = "info"
                continue
            if stripped == "[分片列表]":
                section = "chunks"
                continue

            if section == "info":
                #只在第一个=位置分割
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key == "文件名":
                        orig_filename = value
            elif section == "chunks":
                #格式: 序号 | 分片文件名 | 分片大小 | 分片SHA256
                parts = line.split("|")
                #4个字段才是合法分片行
                if len(parts) == 4:
                    #分片文件名永远是第二个元素(下标:1)
                    chunk_name = parts[1].strip()
                    chunk_files.append(chunk_name)

    #打包成字典
    result = {
        "orig_filename": orig_filename,
        "chunk_list": chunk_files
    }

    return result


def main():
    if not (3 <= len(sys.argv) <= 4):
        print("用法: ./restore_file_from_pool.py 文件分片池路径 清单文件路径 [输出目录]")
        print("示例: ./restore_file_from_pool.py pool_path manifest.txt")
        print("示例: ./restore_file_from_pool.py pool_path manifest.txt out_path")
        sys.exit(1)

    pool_path = resolve_path(sys.argv[1])
    manifest_path = resolve_path(sys.argv[2])
    #输出目录默认为命令行的工作目录
    out_path = sys.argv[3] if len(sys.argv) >= 4 else os.getcwd()
    out_path = resolve_path(out_path)

    if not os.path.isfile(manifest_path):
        print(f"错误:文件不存在:{manifest_path}")
        sys.exit(1)

    if not os.path.isdir(pool_path):
        print(f"错误:文件分片池目录不存在:{pool_path}")
        sys.exit(1)

    data = parse_manifest(manifest_path)

    #创建parts目录
    parts_dir_name = data['orig_filename'] + ".parts"
    parts_dir = os.path.join(pool_path,parts_dir_name)
    os.makedirs(parts_dir, exist_ok=True)

    #move 文件分片
    for chunk_name in data['chunk_list']:
        chunk_path = os.path.join(pool_path,chunk_name)
        if not os.path.isfile(chunk_path):
            print(f"错误:文件分片:{chunk_name},不在文件池中")
            sys.exit(1)
        shutil.move(chunk_path,parts_dir)

    #copy manifest
    shutil.copy2(manifest_path, parts_dir)

    #调用binsplit来进行合并
    subprocess.run(["binsplit", "merge", "-i", parts_dir, "-o", out_path])

    #将文件分片再move回池中
    for chunk_name in data['chunk_list']:
        chunk_path = os.path.join(parts_dir,chunk_name)
        shutil.move(chunk_path,pool_path)

    #删除parts目录
    shutil.rmtree(parts_dir)

if __name__ == "__main__":
    main()
