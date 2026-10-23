"""Finite headless CLI and the native interactive entry point."""
import argparse
import math
from pathlib import Path
import sys
from .model import generate_tree
from .render import RenderOptions, render, export_frame
from .state import Explorer
from .terminal import run_view


def parser():
    root = argparse.ArgumentParser(prog="ascii-tree", description="Explore one procedural tree in 2D, 3D and true XW-rotated 4D.")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("view", "render"):
        sub = commands.add_parser(name, help="interactive terminal" if name == "view" else "deterministic ASCII frame; no TTY required")
        sub.add_argument("--seed", type=int, default=42)
        sub.add_argument("--mode", choices=("2d", "3d", "4d"), default="3d")
        sub.add_argument("--yaw", type=float, default=math.degrees(.45), help="camera yaw, degrees")
        sub.add_argument("--pitch", type=float, default=math.degrees(.08), help="camera tilt, degrees")
        sub.add_argument("--angle4", type=float, default=0., help="XW rotation, degrees")
        sub.add_argument("--zoom", type=float, default=1.)
        sub.add_argument("--aspect", type=float, default=.5, help="character width / height (default .5)")
        if name == "render":
            sub.add_argument("--width", type=int, default=100)
            sub.add_argument("--height", type=int, default=40)
            sub.add_argument("--output", type=Path, help="ASCII .txt; omit to write stdout")
            sub.add_argument("--time", type=float, default=0., help="deterministic animation seconds: 3D yaw / 4D XW")
        else:
            sub.add_argument("--export-dir", type=Path, default=Path("exports"))
    return root


def main(argv=None):
    arguments = parser()
    args = arguments.parse_args(argv)
    try:
        state = Explorer(args.seed, args.mode, math.radians(args.yaw), math.radians(args.pitch),
                         math.radians(args.angle4), args.zoom, args.aspect)
        state.options(1, 1)  # validate view arguments too, before touching terminal
        if args.command == "view":
            return run_view(state, args.export_dir)
        if not math.isfinite(args.time) or abs(args.time) > 1e9:
            raise ValueError("time must be finite and between -1e9 and 1e9")
        if args.mode == "3d":
            state.yaw += args.time * .32
        elif args.mode == "4d":
            state.angle4 += args.time * .27
        frame = render(state.tree, state.options(args.width, args.height))
        if args.output:
            export_frame(frame, args.output)
        else:
            # Binary stdout preserves canonical LF bytes even on Windows.
            sys.stdout.buffer.write(frame.encode("ascii"))
        return 0
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0
    except (ValueError, OSError) as exc:
        print(f"ascii-tree: {exc}", file=sys.stderr)
        return 2
