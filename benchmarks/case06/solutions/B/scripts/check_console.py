"""Finite real-TTY startup/cleanup probe. Run directly in Windows Terminal."""

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.model import generate_tree
from ascii_tree.render import RenderOptions
from ascii_tree.terminal import Terminal, run


def modes():
    if os.name != "nt":
        import termios
        return termios.tcgetattr(sys.stdin.fileno())
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    result = []
    for number in (-10, -11):
        mode = wintypes.DWORD()
        if not kernel.GetConsoleMode(kernel.GetStdHandle(number & 0xFFFFFFFF), ctypes.byref(mode)):
            raise OSError("GetConsoleMode failed")
        result.append(mode.value)
    return result


def main():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("NOT RUN: this probe needs a real TTY; use scripts/smoke.py for headless checks.")
        return 2
    before = modes()
    result = run(generate_tree(42), RenderOptions(), ROOT / ".tmp", max_frames=1)
    after_normal = modes()
    try:
        with Terminal():
            raise RuntimeError("intentional cleanup probe")
    except RuntimeError:
        pass
    after_exception = modes()
    report = {"platform": sys.platform, "normal_exit": result,
              "modes_before": before, "modes_after_normal": after_normal,
              "modes_after_exception": after_exception,
              "passed": result == 0 and before == after_normal == after_exception}
    output = ROOT / "artifacts" / "console-probe.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
