#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
# "click","toml",
# ]
# ///

#=tools
#$邮件助手(拷贝邮件地址和邮件正文)
#@usage:
#@mail_helper.py copy-address
#@mail_helper.py copy-lines

import subprocess
from pathlib import Path

import click
import toml


@click.command()
def copy_address():
    config_path = Path.home() / '.config' / 'mail-helper' / 'helper.toml'

    with open(config_path, 'r') as f:
        config = toml.load(f)

    addresses = config['addresses']
    addresses_size = len(addresses)
    index = config['index']

    subprocess.run(["pbcopy"], input=addresses[index], text=True)

    index += 1
    index = index % addresses_size
    config['index'] = index
    with open(config_path, 'w') as f:
        toml.dump(config, f)


@click.command()
def copy_lines():
    config_path = Path.home() / '.config' / 'mail-helper' / 'helper.toml'

    with open(config_path, 'r') as f:
        config = toml.load(f)

    res_dir = Path(config['res_dir']).expanduser()
    book_name = config['book_name']
    book_next_read_line = config['book_next_read_line']
    print_lines = config['print_lines']
    book_path = res_dir / book_name

    start_line = book_next_read_line
    contents = []
    with open(book_path, 'r') as file:
        # 跳过前面的lines
        for _ in range(start_line - 1):
            file.readline()

        for _ in range(print_lines):
            line = file.readline()
            if not line:
                # 如果剩余的行数小于print_lines,则退出
                break
            contents.append(line.strip())

    all_contents = "\n".join(contents)
    subprocess.run(["pbcopy"], input=all_contents, text=True)

    config['book_next_read_line'] += print_lines
    with open(config_path, 'w') as f:
        toml.dump(config, f)


@click.group()
def run():
    config_path = Path.home() / '.config' / 'mail-helper' / 'helper.toml'

    if not config_path.is_file():
        applescript = 'display notification "mail-helper的配置文件缺失" with title "mail-helper" sound name "Glass"'
        subprocess.run(["osascript", "-e", applescript])

        raise FileNotFoundError(f"文件{config_path}不存在")


run.add_command(copy_address)
run.add_command(copy_lines)

if __name__ == "__main__":
    run()
