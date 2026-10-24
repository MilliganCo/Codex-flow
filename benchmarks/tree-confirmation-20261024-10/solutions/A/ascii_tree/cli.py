"""Offline command line entry points. Render never requires a TTY."""

import argparse
import math
from pathlib import Path
import sys

from . import __version__
from .app import Explorer, run_loop
from .geometry import generate_tree
from .projection import RenderOptions
from .render import render_tree
from .terminal import Terminal


def finite_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a number") from None
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError("expected a finite number")
    return value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ascii-tree", description="Explore one procedural tree in 2D, 3D and true XW-rotated 4D.")
    root.add_argument("--version", action="version", version=__version__)
    actions = root.add_subparsers(dest="action")
    for name, description in (("view", "Interactive explorer; one plain frame when no TTY is attached"),
                              ("render", "Deterministic, plain ASCII frame (no TTY needed)")):
        sub = actions.add_parser(name, help=description, description=description)
        sub.add_argument("--seed", type=int, default=42, help="integer tree seed (default: 42)")
        sub.add_argument("--mode", choices=("2d", "3d", "4d"), default="3d")
        sub.add_argument("--width", type=int, default=100, help="columns, 1..500; view fallback size")
        sub.add_argument("--height", type=int, default=40, help="rows, 1..240; view fallback size")
        sub.add_argument("--yaw", type=finite_float, default=25, help="3D camera azimuth in degrees")
        sub.add_argument("--pitch", type=finite_float, default=8, help="3D camera tilt in degrees")
        sub.add_argument("--angle4", type=finite_float, default=0, help="4D XW rotation in degrees")
        sub.add_argument("--zoom", type=finite_float, default=1, help="magnification, 0.15..5")
        sub.add_argument("--aspect", type=finite_float, default=2, help="cell height / width, 0.5..4")
        sub.add_argument("--time", type=finite_float, default=0, help="deterministic wind time in seconds")
        if name == "render":
            sub.add_argument("--output", type=Path, help=".txt path; default: stdout")
        else:
            sub.add_argument("--animate", action="store_true", help="start animation immediately")
            sub.add_argument("--fps", type=finite_float, default=12, help="animation cap, 1..30 (default: 12)")
            sub.add_argument("--duration", type=finite_float, help="auto-close after this many seconds (finite demo)")
            sub.add_argument("--export-dir", type=Path, default=Path("exports"))
    return root


def main(argv: list[str] | None = None) -> int:
    command = parser()
    args = command.parse_args(argv)
    if args.action is None:
        command.print_help()
        return 0
    try:
        options = RenderOptions(args.width, args.height, args.mode, args.yaw, args.pitch,
                                args.angle4, args.zoom, args.aspect, args.time)
        if args.action == "view":
            if not 1 <= args.fps <= 30:
                raise ValueError("fps must be 1..30")
            if args.duration is not None and not 0.05 <= args.duration <= 86400:
                raise ValueError("duration must be 0.05..86400 seconds")
        if args.action == "render" or not (sys.stdin.isatty() and sys.stdout.isatty()):
            frame = render_tree(generate_tree(args.seed), options)
            if args.action == "render" and args.output is not None:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(frame.bytes())
            else:
                if hasattr(sys.stdout, "buffer"):
                    sys.stdout.buffer.write(frame.bytes())
                else:
                    sys.stdout.write(frame.text())
            if args.action == "view":
                print("No interactive TTY: rendered one plain frame. Use render for explicit export.", file=sys.stderr)
            return 0
        state = Explorer(args.seed, args.mode, args.yaw, args.pitch, args.angle4,
                         args.zoom, args.aspect, args.time, args.animate)
        return run_loop(state, Terminal(), args.export_dir, args.fps, args.duration)
    except BrokenPipeError:
        raise
    except (ValueError, OSError) as error:
        print(f"ascii-tree: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


def entrypoint() -> None:
    try:
        code = main()
        sys.stdout.flush()
    except BrokenPipeError:
        code = 0
        # Avoid another flush error when a consumer closes its pipe early.
        sys.stdout = open(__import__("os").devnull, "w")
    raise SystemExit(code)
