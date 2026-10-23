"""Public command line. Headless rendering never emits terminal sequences."""

import argparse
import math
import os
from pathlib import Path
import sys

from .geometry import Camera
from .model import generate_tree
from .render import export_frame, frame_bytes, render
from .state import Explorer
from .terminal import NativeTerminal, run_view


def finite_number(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError("must be a finite number")
    return value


def bounded_int(low: int, high: int):
    def parse(text: str) -> int:
        value = int(text)
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return value
    return parse


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="ascii-tree", description=
        "Explore one procedural tree in 2D, 3D and 4D. No external dependencies.")
    sub = root.add_subparsers(dest="action", required=True)
    for name, description in (("view", "Interactive viewer; one plain frame if no TTY"),
                              ("render", "Deterministic ASCII frame (works without TTY)")):
        command = sub.add_parser(name, help=description, description=description)
        command.add_argument("--seed", type=int, default=42)
        command.add_argument("--mode", choices=("2d", "3d", "4d"), default="3d")
        command.add_argument("--width", type=bounded_int(1, 1000), default=100,
                             help="columns (view uses actual TTY size; default 100)")
        command.add_argument("--height", type=bounded_int(1, 500), default=40,
                             help="rows (view uses actual TTY size; default 40)")
        command.add_argument("--yaw", type=finite_number, default=25, help="3D yaw in degrees")
        command.add_argument("--pitch", type=finite_number, default=-8, help="3D pitch in degrees")
        command.add_argument("--angle4d", type=finite_number, default=0, help="XW rotation in degrees")
        command.add_argument("--zoom", type=finite_number, default=1, help="0.15..5 (default 1)")
        command.add_argument("--aspect", type=finite_number, default=2, help="cell height / width, 0.5..4")
        command.add_argument("--time", type=finite_number, default=0,
                             help="animation time in seconds (2D wind; yaw +12/s, XW +9/s)")
        if name == "render":
            command.add_argument("--output", "-o", type=Path, help=".txt path; default stdout")
        else:
            command.add_argument("--export-dir", type=Path, default=Path("exports"))
            command.add_argument("--fps", type=bounded_int(1, 30), default=12)
            command.add_argument("--frames", type=bounded_int(1, 100000),
                                 help="exit after N drawn frames (for terminal smoke tests)")
            command.add_argument("--demo", action="store_true", help="13-second live keyboard tour")
    return root


def main(argv: list[str] | None = None) -> int:
    command = parser()
    args = command.parse_args(argv)
    yaw = args.yaw + (args.time * 12 if args.mode != "2d" else 0)
    angle4d = args.angle4d + (args.time * 9 if args.mode == "4d" else 0)
    try:
        camera = Camera(args.width, args.height, args.mode, yaw, args.pitch,
                        angle4d, args.zoom, args.aspect, args.time)
        if args.action == "render" or not (sys.stdin.isatty() and sys.stdout.isatty()):
            lines = render(generate_tree(args.seed), camera)
            output = getattr(args, "output", None)
            if output is not None:
                export_frame(output, lines)
            else:
                sys.stdout.buffer.write(frame_bytes(lines))
                sys.stdout.buffer.flush()
            if args.action == "view":
                print("No interactive TTY: rendered one plain ASCII frame; use render --output FILE.",
                      file=sys.stderr)
            return 0
        state = Explorer(seed=args.seed, mode=args.mode, yaw=yaw, pitch=args.pitch,
                         angle4d=angle4d, zoom=args.zoom, aspect=args.aspect,
                         animation_time=args.time)
        return run_view(state, NativeTerminal(), fps=args.fps, export_dir=args.export_dir,
                        max_frames=args.frames, demo=args.demo)
    except BrokenPipeError:
        # Avoid a second BrokenPipeError from interpreter shutdown flush.
        sys.stdout = open(os.devnull, "w")
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as exc:
        print(f"ascii-tree: {exc}", file=sys.stderr)
        return 2
