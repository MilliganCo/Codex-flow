"""CLI with deterministic headless render and an explicit non-TTY contract."""
import argparse
from pathlib import Path
import sys

from .app import Explorer
from .model import generate_tree
from .render import View, render_tree


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="ASCII Tree Explorer: one procedural tree, 2D / 3D / 4D.")
    sub = result.add_subparsers(dest="command", required=True)
    for name in ("view", "render"):
        command = sub.add_parser(name, help="interactive explorer" if name == "view" else "deterministic ASCII frame, no TTY needed")
        command.add_argument("--seed", type=int, default=42)
        command.add_argument("--mode", choices=("2d", "3d", "4d"), default="3d")
        command.add_argument("--yaw", type=float, default=-22, help="3D camera angle, degrees")
        command.add_argument("--pitch", type=float, default=8, help="camera tilt, degrees")
        command.add_argument("--angle4d", type=float, default=0, help="XW rotation, degrees")
        command.add_argument("--zoom", type=float, default=1, help="0.1..5")
        command.add_argument("--time", type=float, default=0, help="deterministic wind time in seconds")
        command.add_argument("--aspect", type=float, default=.5, help="cell width / height, 0.2..1")
        if name == "render":
            command.add_argument("--width", type=int, default=100)
            command.add_argument("--height", type=int, default=40)
            command.add_argument("--output", type=Path, help="ASCII .txt; default: stdout")
        else:
            command.add_argument("--export-dir", type=Path, default=Path.cwd(), help="existing directory for E exports")
            command.add_argument("--max-frames", type=int, help="finite real-terminal startup smoke check")
    return result


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    try:
        view = View(args.mode, args.yaw, args.pitch, args.angle4d, args.zoom, args.time, args.aspect)
        if args.command == "render":
            frame = render_tree(generate_tree(args.seed), args.width, args.height, view)
            if args.output:
                # Binary write makes LF output identical on Windows and Linux.
                args.output.write_bytes(frame.encode("ascii"))
            else:
                sys.stdout.buffer.write(frame.encode("ascii"))
                sys.stdout.buffer.flush()
            return 0
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print("view requires an interactive TTY; use 'python -m ascii_tree render --seed 42 --mode 3d'", file=sys.stderr)
            return 2
        if args.max_frames is not None and args.max_frames < 1:
            raise ValueError("max-frames must be positive")
        if not args.export_dir.is_dir():
            raise ValueError("export-dir must be an existing directory")
        from .terminal import run
        return run(Explorer(args.seed, view), args.export_dir, max_frames=args.max_frames)
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError) as exc:
        print(f"ascii-tree: {exc}", file=sys.stderr)
        return 2
