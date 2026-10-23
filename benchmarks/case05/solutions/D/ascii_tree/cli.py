"""Installed entrypoint and python -m ascii_tree; no TTY needed for render."""

import argparse
import math
from pathlib import Path
import sys

from .geometry import generate_tree
from .projection import View
from .render import MAX_HEIGHT, MAX_WIDTH, render_tree
from .state import Explorer
from .terminal import run_interactive


def finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("must be a finite number")
    return number


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ascii-tree", description="One procedural tree, three dimensions of exploration.")
    sub = root.add_subparsers(dest="command", required=True)
    for name, help_text in (("view", "interactive terminal explorer"), ("render", "deterministic ASCII frame; no TTY required")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--seed", type=int, default=42)
        command.add_argument("--mode", choices=("2d", "3d", "4d"), default="3d")
        command.add_argument("--yaw", type=finite_float, default=25, help="camera yaw in degrees (3D/4D)")
        command.add_argument("--pitch", type=finite_float, default=-7, help="camera pitch in degrees (3D/4D)")
        command.add_argument("--angle4d", type=finite_float, default=0, help="XW rotation in degrees (4D)")
        command.add_argument("--zoom", type=finite_float, default=1, help="0.1..8")
        command.add_argument("--aspect", type=finite_float, default=0.5, help="character width / height, 0.2..2")
        command.add_argument("--time", type=finite_float, default=0, help="deterministic animation seconds from these angles")
        if name == "render":
            command.add_argument("--width", type=int, default=100, help=f"1..{MAX_WIDTH}")
            command.add_argument("--height", type=int, default=40, help=f"1..{MAX_HEIGHT}")
            command.add_argument("--output", type=Path, help="ASCII file; stdout if omitted")
        else:
            command.add_argument("--export-dir", type=Path, default=Path("exports"))
    return root


def main(argv: list[str] | None = None) -> int:
    arguments = parser()
    args = arguments.parse_args(argv)
    try:
        yaw = (args.yaw + (24 if args.mode == "3d" else 9 if args.mode == "4d" else 0) * args.time) % 360
        angle4d = (args.angle4d + (24 * args.time if args.mode == "4d" else 0)) % 360
        view = View(args.mode, yaw, args.pitch, angle4d, args.zoom, args.aspect)
        if args.command == "render":
            frame = render_tree(generate_tree(args.seed), args.width, args.height, view)
            if args.output is not None:
                frame.save(args.output)
            else:
                # Write bytes to avoid CRLF conversion and code-page dependencies.
                sys.stdout.buffer.write(frame.to_bytes())
            return 0
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print("view requires an interactive TTY. Use: python -m ascii_tree render --seed 42 --mode 3d", file=sys.stderr)
            return 2
        return run_interactive(Explorer(args.seed, view, args.export_dir))
    except (ValueError, OSError) as exc:
        print(f"ascii-tree: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
