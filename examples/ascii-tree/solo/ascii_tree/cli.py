"""Actual entry point: python -m ascii_tree [view|render]."""

import argparse
from pathlib import Path
import sys

from . import __version__
from .model import generate_tree
from .renderer import Frame, RenderOptions, render_tree
from .state import ExplorerState
from .terminal import TerminalError, run_interactive


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ascii_tree", description="ASCII Tree Explorer: one living graph in 2D, 3D and true 4D projection.")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    for name, description in (("view", "Open the interactive terminal explorer; non-TTY renders one frame."),
                              ("render", "Render a deterministic plain ASCII frame without a TTY.")):
        sub = subparsers.add_parser(name, help=description, description=description)
        sub.add_argument("--seed", type=int, default=42, help="deterministic tree seed (default: 42)")
        sub.add_argument("--mode", choices=("2d", "3d", "4d"), default="3d")
        sub.add_argument("--width", type=int, default=100, help="headless columns, 1..1000 (default: 100)")
        sub.add_argument("--height", type=int, default=40, help="headless rows, 1..1000 (default: 40)")
        sub.add_argument("--yaw", type=float, default=-20, help="3D yaw, degrees")
        sub.add_argument("--pitch", type=float, default=8, help="3D tilt, degrees")
        sub.add_argument("--angle4", "--angle-4d", type=float, default=0, help="4D rotation angle, degrees")
        sub.add_argument("--plane", choices=("xw", "yw", "zw"), default="xw")
        sub.add_argument("--zoom", type=float, default=1, help="zoom, 0.15..5")
        sub.add_argument("--aspect", type=float, default=.5, help="cell width / height, 0.2..1 (default: 0.5)")
        sub.add_argument("--time", type=float, default=0, help="deterministic animation time, seconds")
        if name == "render":
            sub.add_argument("--output", type=Path, help="output .txt file; default or '-' writes stdout")
        else:
            sub.add_argument("--fps", type=float, default=8, help="animation limit, 1..30 (default: 8)")
            sub.add_argument("--export-dir", type=Path, default=Path("exports"))
    return parser


def write_frame(frame: Frame, output: Path | None = None) -> None:
    data = frame.text().encode("ascii")
    if output is not None and str(output) != "-":
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
    elif hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    else:
        sys.stdout.write(data.decode("ascii"))
        sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    args_list = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(args_list or ["view"])
    try:
        options = RenderOptions(width=args.width, height=args.height, mode=args.mode,
                                yaw=args.yaw, pitch=args.pitch, angle4=args.angle4,
                                plane=args.plane, zoom=args.zoom, aspect=args.aspect, time=args.time)
        if args.command == "view" and not (1 <= args.fps <= 30):
            parser.error("fps must be in 1..30")
        tree = generate_tree(args.seed)
        if args.command == "render":
            write_frame(render_tree(tree, options), args.output)
        elif not (sys.stdin.isatty() and sys.stdout.isatty()):
            print("No interactive TTY: rendered one frame. Use 'render --output file.txt' for export.", file=sys.stderr)
            write_frame(render_tree(tree, options))
        else:
            return run_interactive(ExplorerState(tree, options), fps=args.fps, export_dir=args.export_dir)
        return 0
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0
    except (ValueError, OSError, TerminalError) as error:
        print(f"ascii-tree: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
