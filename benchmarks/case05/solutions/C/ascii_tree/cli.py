"""Dependency-free command line; all file exports use explicit ASCII LF bytes."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__
from .app import Explorer
from .model import generate_tree
from .render import RenderOptions, render_text
from .terminal import TerminalError, run_interactive


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="ascii-tree", description="Explore one procedural tree in 2D, 3D and real 4D projections.")
    result.add_argument("--version", action="version", version=__version__)
    actions = result.add_subparsers(dest="action", required=True)
    for name, description in (("view", "Interactive viewer; one plain frame if no TTY"),
                              ("render", "Deterministic ASCII frame, no TTY needed")):
        p = actions.add_parser(name, help=description)
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--mode", choices=("2d", "3d", "4d"), default="3d")
        p.add_argument("--width", type=int, default=100, help="frame columns, 1..500; non-TTY only for view")
        p.add_argument("--height", type=int, default=40, help="frame rows, 1..200; non-TTY only for view")
        p.add_argument("--yaw", type=float, default=28, help="3D yaw in degrees")
        p.add_argument("--pitch", type=float, default=-8, help="3D pitch in degrees")
        p.add_argument("--angle4", type=float, default=0, help="XW rotation in degrees (4D)")
        p.add_argument("--zoom", type=float, default=1, help="0.1..8")
        p.add_argument("--aspect", type=float, default=2, help="character height / width, 0.5..4")
        p.add_argument("--time", type=float, default=0, help="deterministic wind time in seconds")
        if name == "render":
            p.add_argument("--output", "-o", type=Path, help="ASCII LF .txt path; default stdout")
        else:
            p.add_argument("--export-dir", type=Path, default=Path("exports"))
            p.add_argument("--fps", type=int, choices=range(1, 31), default=12, metavar="1..30")
            p.add_argument("--animate", action="store_true", help="start playing immediately")
    return result


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    try:
        options = RenderOptions(args.width, args.height, args.mode, args.yaw, args.pitch,
                                args.angle4, args.zoom, args.aspect, args.time)
        tty = sys.stdin.isatty() and sys.stdout.isatty()
        if args.action == "view" and tty:
            state = Explorer(args.seed, args.mode, args.yaw, args.pitch, args.angle4,
                             args.zoom, args.aspect, args.time, args.export_dir)
            state.playing = args.animate
            return run_interactive(state, fps=args.fps)
        if args.action == "view":
            print("No interactive TTY: writing one ASCII frame. Use 'render' for explicit export.", file=sys.stderr)
        text = render_text(generate_tree(args.seed), options)
        data = text.encode("ascii")
        if args.action == "render" and args.output is not None:
            args.output.write_bytes(data)
        elif hasattr(sys.stdout, "buffer"):
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        else:
            sys.stdout.write(text)
        return 0
    except (ValueError, TerminalError) as exc:
        cli.error(str(exc))
    except BrokenPipeError:
        # A consumer such as `head` may close stdout early.
        return 0
    except OSError as exc:
        print(f"ascii-tree: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 2
