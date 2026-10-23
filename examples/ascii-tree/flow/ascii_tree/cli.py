"""Offline CLI: `python -m ascii_tree {view,render}`."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__
from .app import Explorer
from .model import generate_tree
from .render import RenderOptions, render, write_frame
from .terminal import run_interactive


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="python -m ascii_tree", description="ASCII Tree Explorer: one seeded tree in 2D, 3D and a real XW-rotated 4D projection.")
    cli.add_argument("--version", action="version", version=__version__)
    commands = cli.add_subparsers(dest="command", required=True)
    for command in ("view", "render"):
        p = commands.add_parser(command, help="interactive explorer (TTY required)" if command == "view" else "deterministic ASCII raster, no TTY required")
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--mode", choices=("2d", "3d", "4d"), default="3d")
        p.add_argument("--width", type=int, default=100, help="raster columns; view follows terminal size")
        p.add_argument("--height", type=int, default=40, help="raster rows; view reserves room for controls")
        p.add_argument("--yaw", type=float, default=25, help="3D camera yaw in degrees")
        p.add_argument("--pitch", type=float, default=-8, help="3D camera pitch in degrees")
        p.add_argument("--angle4d", type=float, default=0, help="XW rotation in degrees")
        p.add_argument("--zoom", type=float, default=1, help="0.15..5")
        p.add_argument("--aspect", type=float, default=2, help="character height/width, 0.5..4")
        p.add_argument("--time", type=float, default=0, help="deterministic animation seconds (yaw +12/s, XW +8/s)")
        if command == "render":
            p.add_argument("--output", type=Path, help="plain ASCII .txt; otherwise stdout")
        else:
            p.add_argument("--export-dir", type=Path, default=Path("exports"))
    return cli


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    try:
        options = RenderOptions(**{k: getattr(args, k) for k in (
            "width", "height", "mode", "yaw", "pitch", "angle4d", "zoom", "aspect", "time")})
    except ValueError as error:
        cli.error(str(error))
    try:
        if args.command == "render":
            frame = render(generate_tree(args.seed), options)
            if args.output:
                write_frame(args.output, frame)
            else:
                # Preserve LF bytes even on Windows redirected stdout.
                binary = getattr(sys.stdout, "buffer", None)
                if binary is not None:
                    binary.write(frame.encode("ascii"))
                    binary.flush()
                else:
                    sys.stdout.write(frame)
            return 0
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print("view requires an interactive TTY on stdin and stdout; use: python -m ascii_tree render --seed 42 --mode 3d", file=sys.stderr)
            return 2
        return run_interactive(Explorer(options, args.seed, args.export_dir))
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as error:
        print(f"ascii-tree: {error}", file=sys.stderr)
        return 2
