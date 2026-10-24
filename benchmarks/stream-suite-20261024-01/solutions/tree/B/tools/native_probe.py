"""Run in a real TTY. --startup is finite; otherwise send the documented keys.

Reports actual Windows console mode restoration. No mock terminal is involved.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import threading
import _thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ascii_tree.app import Explorer
from ascii_tree.terminal import run


def modes():
    if os.name != 'nt':
        return None
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    values = []
    for number in (-10, -11):
        value = wintypes.DWORD()
        if not kernel.GetConsoleMode(kernel.GetStdHandle(number), ctypes.byref(value)):
            raise OSError('probe requires a real Windows console')
        values.append(value.value)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--startup', action='store_true')
    parser.add_argument('--label', default='interactive')
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error('run this check inside a real TTY')
    app = Explorer()
    original = app.tree
    before = modes()
    timed_out = []

    def timeout():
        timed_out.append(True)
        _thread.interrupt_main()

    watchdog = threading.Timer(45, timeout)
    watchdog.daemon = True
    target = ROOT/'artifacts'/'probe-exports'
    target.mkdir(parents=True, exist_ok=True)
    watchdog.start()
    try:
        result = run(app, target, max_frames=1 if args.startup else None)
    finally:
        watchdog.cancel()
    after = modes()
    report = {'platform': sys.platform, 'real_tty': True, 'label': args.label,
              'startup_only': args.startup, 'returncode': result, 'seed': app.seed,
              'mode': app.view.mode, 'angle4d': app.view.angle4d, 'yaw': app.view.yaw,
              'pitch': app.view.pitch, 'zoom': app.view.zoom, 'time': app.view.time,
              'playing': app.playing, 'help_open': app.help_open,
              'same_tree': app.tree is original, 'export_count': app.export_count,
              'console_before': before, 'console_after': after,
              'console_restored': before == after, 'timed_out': bool(timed_out)}
    (ROOT/'artifacts').mkdir(exist_ok=True)
    path = ROOT/'artifacts'/f'native-{args.label}.json'
    path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))
    assert result == 0 and before == after and not timed_out, report
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
