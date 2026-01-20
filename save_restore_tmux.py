#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "pynput>=1.7",
# ]
# ///

#=tmux:
#$save or restore tmux contents
#@usage:
#@save_restore_tmux.py s
#@save_restore_tmux.py r

import sys
import time
from pynput.keyboard import Key, Controller

def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: save_restore_tmux.py [s|r]", file=sys.stderr)
        return 1

    key = Controller()

    with key.pressed(Key.ctrl):
        key.press('b')
        time.sleep(0.01)
        key.release('b')

    if sys.argv[1] == 's':
        with key.pressed(Key.ctrl):
            key.press('s')
            time.sleep(0.01)
            key.release('s')

    elif sys.argv[1] == 'r':
        with key.pressed(Key.ctrl):
            key.press('r')
            time.sleep(0.01)
            key.release('r')

    else:
        print("Invalid argument", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
