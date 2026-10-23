"""Dependency-free command line entrypoint."""

import argparse
from pathlib import Path
import sys

from .model import generate_tree
from .render import RenderOptions, render_tree


def write_frame(path: Path, frame: str) -> None:
    """Exact ASCII bytes, LF on every OS, no BOM or terminal controls."""
    path.write_bytes(frame.encode("ascii"))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ascii-tree", description="Explore one procedural tree in 2D / 3D / 4D. Offline; ASCII only.")
    sub = root.add_subparsers(dest="action", required=True)
    for name, description in (("view", "interactive explorer (requires a TTY)"), ("render", "deterministic headless ASCII frame")):
        command = sub.add_parser(name, help=description)
        command.add_argument("--seed", type=int, default=42)
        command.add_argument("--mode", choices=("2d", "3d", "4d"), default="3d")
        command.add_argument("--width", type=int, default=100, help="render columns; view follows terminal size")
        command.add_argument("--height", type=int, default=40, help="render rows; view follows terminal size")
        command.add_argument("--yaw", type=float, default=25, help="3D yaw in degrees")
        command.add_argument("--pitch", type=float, default=-7, help="3D pitch in degrees")
        command.add_argument("--angle4d", type=float, default=0, help="XW rotation in degrees")
        command.add_argument("--zoom", type=float, default=1)
        command.add_argument("--aspect", type=float, default=2, help="cell height / width (default 2)")
        command.add_argument("--time", type=float, default=0, help="deterministic animation time in seconds")
        command.add_argument("--bare", action="store_true", help="show branches without foliage")
        if name == "render":
            command.add_argument("--output", type=Path, help="ASCII .txt path; otherwise stdout")
        else:
            command.add_argument("--export-dir", type=Path, default=Path("exports"))
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    options = RenderOptions(width=args.width, height=args.height, mode=args.mode,
                            yaw=args.yaw, pitch=args.pitch, angle4d=args.angle4d,
                            zoom=args.zoom, aspect=args.aspect, time=args.time, foliage=not args.bare)
    try:
        options.validate()
        if args.action == "view":
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                print("view needs an interactive TTY. Use: python -m ascii_tree render --seed 42 --mode 3d", file=sys.stderr)
                return 2
            from .terminal import run
            return run(generate_tree(args.seed), options, args.export_dir)
        frame = render_tree(generate_tree(args.seed), options)
        if args.output:
            write_frame(args.output, frame)
        else:
            sys.stdout.buffer.write(frame.encode("ascii"))
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError) as error:
        print(f"ascii-tree: {error}", file=sys.stderr)
        return 2
