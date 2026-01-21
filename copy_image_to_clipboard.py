#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
# "click","toml",
# ]
# ///

#=tools
#$邮件助手
#$拷贝照片到剪贴板,然后删除照片文件
#$目前实际的邮件中拷贝照片时,使用的是go的版本
#@usage:
#@mail_helper.py copy-image

import subprocess
from pathlib import Path

import click
import toml


@click.command()
def copy_image():
    config_path = Path.home() / '.config' / 'mail-helper' / 'helper.toml'

    with open(config_path, 'r') as f:
        config = toml.load(f)

    res_dir = Path(config['res_dir']).expanduser()
    images = config['images']
    images_path = res_dir / images
    if images_path.is_symlink():
        images_path = images_path.resolve()

    # 非递归,会打印出文件,隐藏的文件,文件夹:for image_file in images_path.iterdir():
    # 递归遍历,会打印出后缀名匹配的文件
    for image_file in images_path.rglob("*"):
        if image_file.suffix.lower() in ['.jpg', '.jpeg', '.png']:
            try:
                # 使用AppleScript将图片复制到剪贴板
                # 尽管指定了以JPEG格式读取,但这主要是剪贴板存储的格式,输入的图片可以是任意PIL支持的格式
                script = f'tell application "System Events" to set the clipboard to (read (POSIX file "{image_file}") as JPEG picture)'
                subprocess.run(['osascript', '-e', script], check=True)
                image_file.unlink()
                break
            except FileNotFoundError:
                print(f"error:未找到文件{image_file}")
            except subprocess.CalledProcessError as e:
                print(f"error:执行AppleScript时出错:{e}")
            except Exception as e:
                print(f"error:发生其他错误:{e}")


@click.group()
def run():
    config_path = Path.home() / '.config' / 'mail-helper' / 'helper.toml'

    if not config_path.is_file():
        applescript = 'display notification "mail-helper的配置文件缺失" with title "mail-helper" sound name "Glass"'
        subprocess.run(["osascript", "-e", applescript])

        raise FileNotFoundError(f"文件{config_path}不存在")


run.add_command(copy_image)

if __name__ == "__main__":
    run()
