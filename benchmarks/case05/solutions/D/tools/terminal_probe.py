"""Optional live terminal check with evidence, not part of the headless test suite.

python tools/terminal_probe.py --output validation/pty_q.json
python tools/terminal_probe.py --output validation/pty_ctrl_c.json --expect-exit 130
"""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ascii_tree.state import Explorer
from ascii_tree.terminal import Terminal, run_interactive


def console_modes():
    if os.name != "nt":
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    result = {}
    for label, number in (("input", -10), ("output", -11)):
        mode = wintypes.DWORD()
        if not kernel.GetConsoleMode(kernel.GetStdHandle(number & 0xFFFFFFFF), ctypes.byref(mode)):
            raise OSError("Not a native Windows console")
        result[label] = mode.value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("validation/pty_q.json"))
    parser.add_argument("--expect-exit", type=int, choices=(0, 130), default=0)
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("This optional probe needs an interactive TTY")
    events, sizes, snapshots = [], [], {}
    state = Explorer()
    tree = state.tree

    class Probe(Terminal):
        def present(self, rows):
            key = f"{state.view.mode}_xw{round(state.view.angle4d)}"
            if key not in snapshots and len(snapshots) < 8:
                snapshots[key] = "\n".join(rows) + "\n"
            super().present(rows)

        def size(self):
            result = super().size()
            if not sizes or sizes[-1] != result:
                sizes.append(result)
            return result

        def read_key(self, timeout):
            try:
                key = super().read_key(timeout)
            except KeyboardInterrupt:
                events.append("KeyboardInterrupt")
                raise
            if key:
                events.append(key)
            return key

    before = console_modes()
    code = run_interactive(state, Probe)
    after = console_modes()
    result = {"platform": sys.platform, "python": sys.version.split()[0], "exit_code": code,
              "expected_exit_code": args.expect_exit, "keys": events, "viewport_sizes": sizes,
              "modes_before": before, "modes_after": after, "modes_restored": before == after,
              "final_mode": state.view.mode, "final_seed": state.seed,
              "tree_preserved": state.tree is tree, "snapshots": list(snapshots)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii", newline="\n")
    directory = args.output.parent / args.output.stem
    directory.mkdir(exist_ok=True)
    for key, data in snapshots.items():
        (directory / f"{key}.txt").write_bytes(data.encode("ascii"))
    print(json.dumps(result))
    return 0 if code == args.expect_exit and before == after else 1


if __name__ == "__main__":
    raise SystemExit(main())
