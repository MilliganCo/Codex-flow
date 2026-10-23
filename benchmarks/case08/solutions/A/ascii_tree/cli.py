"""Interactive and deterministic headless entry points."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__
from .app import ExplorerState
from .geometry import generate_tree
from .render import RenderOptions, frame_bytes
from .terminal import run_interactive


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ascii-tree", description="One procedural tree in 2D, 3D and 4D ASCII.")
    p.add_argument("--version", action="version", version=__version__)
    actions = p.add_subparsers(dest="action", required=True)
    for name, help_text in (("view", "interactive explorer (requires a TTY)"),
                            ("render", "one deterministic pure ASCII frame; no TTY needed")):
        sub = actions.add_parser(name, help=help_text)
        sub.add_argument("--seed", type=int, default=42)
        sub.add_argument("--mode", choices=("2d", "3d", "4d"), default="3d")
        sub.add_argument("--width", type=int, default=100, help="1..500 columns (render)")
        sub.add_argument("--height", type=int, default=40, help="1..200 rows (render)")
        sub.add_argument("--yaw", type=float, default=25.0, help="3D orbit in degrees")
        sub.add_argument("--pitch", type=float, default=-7.0, help="3D tilt in degrees")
        sub.add_argument("--angle4", "--xw", type=float, default=0.0, help="XW rotation in degrees")
        sub.add_argument("--zoom", type=float, default=1.0, help="0.1..8 (1 fits the tree)")
        sub.add_argument("--aspect", type=float, default=2.0, help="character height/width; 0.5..4")
        sub.add_argument("--time", type=float, default=0.0, help="deterministic animation time in seconds")
        if name == "render":
            sub.add_argument("--output", type=Path, help=".txt path (default: stdout)")
        else:
            sub.add_argument("--export-dir", type=Path, default=Path("exports"))
    return p


def main(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    try:
        options = RenderOptions(mode=args.mode, width=args.width, height=args.height,
                                yaw=args.yaw, pitch=args.pitch, angle4=args.angle4,
                                zoom=args.zoom, aspect=args.aspect, time=args.time)
    except ValueError as exc:
        p.error(str(exc))
    try:
        if args.action == "render":
            payload = frame_bytes(generate_tree(args.seed), options)
            if args.output is not None:
                args.output.write_bytes(payload)
            else:
                sys.stdout.buffer.write(payload)
                sys.stdout.buffer.flush()
            return 0
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print("ascii-tree: view requires an interactive TTY. Use: "
                  "python -m ascii_tree render --seed 42 --mode 3d", file=sys.stderr)
            return 2
        return run_interactive(ExplorerState(options, args.seed, args.export_dir))
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0
    except OSError as exc:
        print(f"ascii-tree: {exc}", file=sys.stderr)
        return 1
