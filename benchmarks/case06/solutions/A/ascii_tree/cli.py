"""CLI entry point; render is independent of console capabilities."""

import argparse
import math
from pathlib import Path
import sys

from . import __version__
from .app import run_view
from .model import generate_tree
from .render import RenderOptions, render_tree
from .state import ExplorerState


def finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError("must be finite")
    return value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ascii-tree", description="Explore one procedural ASCII tree in 2D, 3D and real 4D projections.")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("view", "render"):
        command = commands.add_parser(name, help="interactive terminal explorer" if name == "view" else "deterministic plain ASCII frame (no TTY needed)")
        command.add_argument("--seed", type=int, default=42)
        command.add_argument("--mode", choices=("2d", "3d", "4d"), default="3d")
        command.add_argument("--yaw", type=finite_float, default=-25.0, help="3D yaw in degrees (default: -25)")
        command.add_argument("--pitch", type=finite_float, default=8.0, help="3D pitch in degrees (default: 8)")
        command.add_argument("--angle4", type=finite_float, default=0.0, help="4D plane rotation in degrees")
        command.add_argument("--plane", choices=("xw", "yw", "zw"), default="xw")
        command.add_argument("--zoom", type=finite_float, default=1.0, help="0.1..6 (default: 1)")
        command.add_argument("--aspect", type=finite_float, default=0.5, help="character width/height, 0.25..1 (default: 0.5)")
        command.add_argument("--time", type=finite_float, default=0.0, help="deterministic breeze time in seconds")
        if name == "render":
            command.add_argument("--width", type=int, default=100, help="1..500 columns")
            command.add_argument("--height", type=int, default=40, help="1..200 rows")
            command.add_argument("--output", type=Path, help="write ASCII/LF file; omitted or - means stdout")
        else:
            command.add_argument("--export-dir", type=Path, default=Path("exports"))
    return root


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    try:
        options = RenderOptions(width=getattr(args, "width", 100), height=getattr(args, "height", 40),
                                mode=args.mode, yaw=args.yaw, pitch=args.pitch, angle4=args.angle4,
                                plane=args.plane, zoom=args.zoom, aspect=args.aspect, time=args.time)
    except ValueError as error:
        cli.error(str(error))
    try:
        if args.command == "render":
            data = render_tree(generate_tree(args.seed), options).encode("ascii")
            if args.output is not None and str(args.output) != "-":
                args.output.write_bytes(data)
            else:
                # Avoid Windows text-mode newline translation in redirected output.
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            return 0
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print("ascii-tree: view requires an interactive TTY. Use: python -m ascii_tree render --seed 42 --mode 3d", file=sys.stderr)
            return 2
        state = ExplorerState(seed=args.seed, mode=args.mode, yaw=args.yaw, pitch=args.pitch,
                              angle4=args.angle4, plane=args.plane, zoom=args.zoom, aspect=args.aspect, time=args.time)
        return run_view(state, args.export_dir)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # Prevent a second failure during interpreter shutdown when piped to head.
        try:
            sys.stdout.close()
        except BrokenPipeError:
            pass
        return 0
    except OSError as error:
        print(f"ascii-tree: {error}", file=sys.stderr)
        return 1
