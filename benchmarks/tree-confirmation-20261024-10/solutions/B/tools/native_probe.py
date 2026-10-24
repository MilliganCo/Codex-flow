"""Run actual UI in a TTY and record return code and Win32 console restoration.

python tools/native_probe.py --report verification/native-ctrl-c.json --mode 4d
Then press Ctrl+C. This is a manual/native probe, not a simulated terminal.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ascii_tree.cli import main


def console_modes():
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    modes = []
    for which in (-10, -11):
        mode = wintypes.DWORD()
        if not kernel.GetConsoleMode(kernel.GetStdHandle(which & 0xffffffff), ctypes.byref(mode)):
            raise OSError("Not a native Windows console")
        modes.append(mode.value)
    return modes


def probe():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args, remaining = parser.parse_known_args()
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        parser.error("native_probe requires an interactive TTY")
    report = args.report.resolve()
    if not report.is_relative_to(ROOT):
        parser.error("report must stay in the project directory")
    before = console_modes()
    result = main(["view", *remaining])
    after = console_modes()
    report.parent.mkdir(parents=True, exist_ok=True)
    data = {"native_tty": True, "platform": sys.platform, "arguments": remaining,
            "application_return_code": result, "console_modes_before": before,
            "console_modes_after": after, "console_modes_restored": before == after}
    report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Application return code: {result}; console modes restored: {before == after}")
    return result


if __name__ == "__main__":
    raise SystemExit(probe())
