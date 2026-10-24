"""Finite real-terminal lifecycle check; explicitly requires an interactive TTY."""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.app import Explorer
from ascii_tree.model import generate_tree
from ascii_tree.terminal import Terminal


def windows_modes():
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    result = []
    for kind in (-10, -11):
        mode = wintypes.DWORD()
        if not kernel.GetConsoleMode(kernel.GetStdHandle(kind), ctypes.byref(mode)):
            raise OSError("requires a real console")
        result.append(mode.value)
    return tuple(result)


def main():
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("NOT RUN: tty_probe requires a terminal", file=sys.stderr)
        return 2
    if os.name == "nt":
        before = windows_modes()
    else:
        import termios
        before = termios.tcgetattr(sys.stdin.fileno())
    app = Explorer(generate_tree(42))
    with Terminal() as terminal:
        if os.name == "nt":
            inside = windows_modes()
            assert inside[1] & 4, "VT output disabled"
            assert not inside[0] & (1 | 2 | 4 | 0x40 | 0x200), "raw key mode not enabled"
        terminal.draw(app.screen(*terminal.size()))
    after = windows_modes() if os.name == "nt" else termios.tcgetattr(sys.stdin.fileno())
    assert before == after, (before, after)
    print("PASS: real TTY startup, draw, raw keyboard mode, exact console restoration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
