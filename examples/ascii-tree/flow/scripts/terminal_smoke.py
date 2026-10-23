"""Actual Windows terminal demo/test: python scripts/terminal_smoke.py.

Run in a private Windows pseudoconsole, write artifacts into artifacts/terminal/.
Also callable by unittest with a temporary output directory.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ascii_tree.model import generate_tree
from ascii_tree.render import RenderOptions, render
from scripts.windows_console import WindowsConsole


def exercise(directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    exports = directory / "exports"
    if exports.exists() and any(exports.iterdir()):
        raise RuntimeError(f"use an empty export directory: {exports}")
    report = {"platform": sys.platform, "python": sys.version.split()[0], "checks": []}
    args = ["-m", "ascii_tree", "view", "--seed", "42", "--export-dir", str(exports.resolve())]
    with WindowsConsole(args, ROOT) as console:
        console.wait_for(lambda: b"ASCII TREE EXPLORER" in console.output)
        report["checks"].append("startup: actual view process in 100x40 ConPTY")
        tree = generate_tree(42)

        def export(keys, number, mode, size=None, **changes):
            console.send(keys + "e")
            seed = changes.pop("seed", 42)
            path = exports / f"tree-{seed}-{mode}-{number:03d}.txt"
            console.wait_for(lambda: path.exists() and path.stat().st_size > 0)
            data = path.read_bytes()
            lines = data.splitlines()
            width, height = len(lines[0]), len(lines)
            if size is not None and (width, height) != size:
                raise AssertionError(f"{path.name}: resize gave {width}x{height}, expected {size}")
            expected = render(tree if seed == 42 else generate_tree(seed),
                              RenderOptions(width=width, height=height, mode=mode, **changes)).encode("ascii")
            if data != expected:
                raise AssertionError(f"{path.name}: actual TTY export differs from expected projection")
            report["checks"].append(f"keys {keys!r}: {path.name}, {width}x{height}, exact expected bytes")
            return data

        first = export("1", 1, "2d")
        second = export("2", 2, "3d")
        third = export("3", 3, "4d")
        fourth = export("]", 4, "4d", angle4d=8)
        if len({first, second, third, fourth}) != 4:
            raise AssertionError("mode/XW changes were not visible")
        export("\x1b[C\x1b[A", 5, "4d", angle4d=8, yaw=33, pitch=-14)
        static = export("+", 6, "4d", angle4d=8, yaw=33, pitch=-14, zoom=1.12)
        console.send("h")
        console.wait_for(lambda: b"HELP" in console.output)
        console.send("h")
        report["checks"].append("help open/close")
        console.send(" ")
        console.wait_for(lambda: b"PLAY" in console.output)
        # Allow several real 15fps ticks, then assert a changed exported raster.
        time.sleep(0.25)
        console.send(" e")
        path = exports / "tree-42-4d-007.txt"
        console.wait_for(lambda: path.exists() and path.stat().st_size > 0)
        paused = path.read_bytes()
        if paused == static:
            raise AssertionError("animation did not change the visible raster")
        time.sleep(0.1)
        console.send("e")
        path = exports / "tree-42-4d-008.txt"
        console.wait_for(lambda: path.exists() and path.stat().st_size > 0)
        if path.read_bytes() != paused:
            raise AssertionError("paused animation changed the raster")
        export("r", 9, "4d")
        report["checks"].append("animation changes raster; pause holds exact bytes; reset restores projection")
        export("g", 10, "4d", seed=43)
        console.resize(30, 12)
        time.sleep(0.2)  # two idle polls; dimensions are asserted below, not assumed
        export("", 11, "4d", seed=43, size=(29, 7))
        console.resize(1, 1)
        time.sleep(0.2)
        export("1", 12, "2d", seed=43, size=(1, 1))
        console.resize(100, 40)
        time.sleep(0.2)
        export("3r", 13, "4d", seed=43, size=(99, 35))
        report["checks"].append("live resize 30x12 -> 1x1 -> 100x40 without crash")
        console.send("q")
        if console.wait() != 0:
            raise AssertionError("Q did not exit successfully")
        report["checks"].append("Q exits with code 0")
    transcript = bytes(console.output)
    if b"\x1b[?25h" not in transcript or b"\x1b[?1049l" not in transcript:
        raise AssertionError("terminal cursor/alternate-screen restoration not observed")
    (directory / "session.ansi").write_bytes(transcript)
    report["checks"].append("cursor shown and alternate screen restored")

    for key, label in ((b"\x1b", "Esc"), (b"\x03", "Ctrl+C")):
        with WindowsConsole(args, ROOT) as console:
            console.wait_for(lambda: b"ASCII TREE EXPLORER" in console.output)
            console.send(key)
            try:
                code = console.wait()
            except TimeoutError as error:
                raise TimeoutError(f"{label} did not exit the actual console process") from error
            if code != 0:
                raise AssertionError(f"{label} did not exit successfully")
        report["checks"].append(f"{label}: actual process exits with code 0")
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "terminal")
    args = parser.parse_args()
    if os.name != "nt":
        print("NOT_RUN: this harness requires Windows ConPTY; see docs/DEMO.md for manual checks")
        return 0
    directory = args.output_dir.resolve()
    if not directory.is_relative_to(ROOT):
        parser.error("output directory must be inside the project")
    if directory.exists():
        # Each invocation gets its own directory; never remove existing artifacts.
        index = 2
        while (directory.parent / f"{directory.name}-{index}").exists():
            index += 1
        directory = directory.parent / f"{directory.name}-{index}"
    report = exercise(directory)
    print(f"PASS: {len(report['checks'])} actual Windows console checks; artifacts: {directory.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
