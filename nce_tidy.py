#!/usr/bin/env -S uv run

# /// script
# requires-python = ">=3.12"
# dependencies = [
# ]
# ///

import sys
from enum import StrEnum
from pathlib import Path

title_lines = []
text_lines = []
new_words_lines = []

title = []
text = []
new_words = []


class NceError(Exception):
    """
    NCE异常
    """


class Section(StrEnum):
    TITLE = "#title"
    TEXT = "#text"
    NEW_WORDS = "#new words"


def parse_lines(file):
    with file.open("r", encoding="utf-8") as f:
        section = None
        for line in f:
            line = line.strip()

            if not line:
                continue

            if line == Section.TITLE:
                section = Section.TITLE
                continue
            elif line == Section.TEXT:
                section = Section.TEXT
                continue
            elif line == Section.NEW_WORDS:
                section = Section.NEW_WORDS
                continue

            match section:
                case Section.TITLE:
                    title_lines.append(line)
                case Section.TEXT:
                    text_lines.append(line)
                case Section.NEW_WORDS:
                    new_words_lines.append(line)


def process_title():
    length = len(title_lines)
    # title部分一定是3行
    if length != 3:
        raise NceError("标题行数不正确")

    title.append(Section.TITLE + "\n")

    for line in title_lines:
        title.append(line + "\n")

    title.append("\n")


def process_text():
    length = len(text_lines)
    # 可能没有课文
    if length == 0:
        return

    if length % 2 != 0:
        raise NceError("课文与其中文翻译数量不匹配")

    text_num = length // 2
    text_english = text_lines[:text_num]
    text_chinese = text_lines[text_num:]

    text.append(Section.TEXT + "\n")

    for i in range(text_num):
        text.append(text_english[i] + "\n")
        text.append(text_chinese[i] + "\n")

    text.append("\n")


def process_new_words():
    length = len(new_words_lines)
    if length == 0:
        raise NceError("没有读取到单词")

    if length % 2 != 0:
        raise NceError("单词与其中文释义数量不匹配")

    words_num = length // 2
    new_words_english = new_words_lines[:words_num]
    new_words_chinese = new_words_lines[words_num:]

    new_words.append(Section.NEW_WORDS + "\n")

    for i in range(words_num):
        new_words.append(new_words_english[i] + "|" + new_words_chinese[i] + "\n")


def writes(file):
    if not title:
        raise NceError("写的时候发现没有title")

    if not new_words:
        raise NceError("写的时候发现没有单词")

    # 如果要写的文件已经存在了
    if file.is_file():
        raise NceError(f"输出文件:{file}已经存在了")

    # file.write_text("".join(lines)
    with file.open("w", encoding="utf-8") as f:
        f.writelines(title)
        f.writelines(text)
        f.writelines(new_words)


def main():
    if sys.version_info < (3, 12):
        curren_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        raise NceError(f"需要Python 3.12+，当前版本:{curren_version}")

    args_num = len(sys.argv)
    if args_num == 1 or args_num > 3:
        raise NceError("用法: python new_words.py input_file.nce [output_file.txt]")

    input_file = sys.argv[1]
    input_file = Path(input_file)
    input_suffix = input_file.suffix.lower()
    # 如果有后缀,但是后缀不是.nce
    if input_suffix and input_suffix != ".nce":
        raise NceError(f"输入文件:{input_file}的后缀名不是.nce")

    # 如果没有后缀,那么就自动添加.nce后缀
    if not input_suffix:
        input_file = input_file.with_suffix(".nce")

    # 检查输入文件是否存在
    if not input_file.is_file():
        raise NceError(f"输入文件:{input_file}不存在")

    if args_num == 3:
        output_file = Path(sys.argv[2])
    else:
        output_file = input_file.with_suffix(".txt")

    # 解析行
    parse_lines(input_file)

    # 处理title
    process_title()
    # 处理text
    process_text()
    # 处理new words
    process_new_words()

    # 写
    writes(output_file)


if __name__ == "__main__":
    main()
