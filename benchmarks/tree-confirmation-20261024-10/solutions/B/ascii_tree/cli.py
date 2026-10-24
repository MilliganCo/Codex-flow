"""Dependency-free command line. Headless view deliberately emits one plain frame."""
import argparse
import math
from pathlib import Path
import sys

from .model import generate_tree
from .render import Camera, render


def finite_float(text):
    try:
        value = float(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a finite number") from error
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError("expected a finite number")
    return value


def parser():
    root = argparse.ArgumentParser(description="ASCII Tree Explorer | one tree, three projections")
    root.add_argument("--version", action="version", version="ASCII Tree Explorer 1.0.0")
    sub = root.add_subparsers(dest="command", required=True)
    for command in ("view", "render"):
        p = sub.add_parser(command, help="interactive explorer" if command == "view" else "deterministic plain ASCII frame")
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--mode", choices=("2d", "3d", "4d"), default="3d")
        p.add_argument("--width", type=int, default=100)
        p.add_argument("--height", type=int, default=40)
        p.add_argument("--yaw", type=finite_float, default=25., help="3D yaw in degrees")
        p.add_argument("--pitch", type=finite_float, default=-7., help="3D pitch in degrees")
        p.add_argument("--angle4d", type=finite_float, default=0., help="XW rotation in degrees")
        p.add_argument("--zoom", type=finite_float, default=1.)
        p.add_argument("--aspect", type=finite_float, default=.5, help="cell width/height (default .5)")
        p.add_argument("--time", type=finite_float, default=0., help="deterministic animation seconds")
        if command == "render":
            p.add_argument("--output", type=Path, help="file path; otherwise stdout")
        else:
            p.add_argument("--export-dir", type=Path, default=Path("exports"))
            p.add_argument("--frames", type=int, help="exit after N UI frames (finite startup smoke)")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    camera = Camera(args.mode, args.yaw, args.pitch, args.angle4d, args.zoom, args.aspect, args.time)
    try:
        camera.validate()
        # Validate dimensions before generating any geometry.
        from .render import Raster
        Raster(args.width, args.height, args.aspect)
        if args.command == "view" and args.frames is not None and not 1 <= args.frames <= 10000:
            raise ValueError("--frames must be between 1 and 10000")
        tree = generate_tree(args.seed)
        if args.command == "view" and sys.stdin.isatty() and sys.stdout.isatty():
            from .terminal import run
            return run(tree, camera, args.export_dir, args.frames)
        frame = render(tree, args.width, args.height, camera)
        if args.command == "render" and args.output is not None:
            from .export import write_frame
            write_frame(args.output, frame)
        else:
            sys.stdout.write(frame)
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError) as error:
        print(f"ascii-tree: {error}", file=sys.stderr)
        return 2
