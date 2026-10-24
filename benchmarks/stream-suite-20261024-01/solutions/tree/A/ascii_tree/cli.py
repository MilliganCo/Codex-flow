"""Reproducible CLI. Headless render never emits terminal escape sequences."""

import argparse
from dataclasses import replace
from pathlib import Path
import sys

from . import __version__
from .app import Explorer
from .model import generate_tree
from .render import RenderSettings, render
from .terminal import run


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="ascii-tree", description="Explore one seeded ASCII tree in 2D, 3D and a real 4D projection.")
    result.add_argument("--version", action="version", version=__version__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("view", "render"):
        p = commands.add_parser(name, help="interactive terminal" if name == "view" else "deterministic ASCII frame; no TTY needed")
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--mode", type=str.lower, choices=("2d", "3d", "4d"), default="3d")
        p.add_argument("--width", type=int, default=100, help="frame columns, 1..500 (headless)")
        p.add_argument("--height", type=int, default=40, help="frame rows, 1..200 (headless)")
        p.add_argument("--yaw", type=float, default=25, help="3D yaw in degrees")
        p.add_argument("--pitch", type=float, default=-8, help="3D pitch in degrees")
        p.add_argument("--angle4d", type=float, default=0, help="XW rotation in degrees")
        p.add_argument("--zoom", type=float, default=1, help="0.15..5")
        p.add_argument("--aspect", type=float, default=2, help="character height/width, 1..3")
        p.add_argument("--time", type=float, default=0, help="deterministic animation time in seconds (breeze + camera)")
        if name == "render":
            p.add_argument("--output", "-o", type=Path, help="ASCII .txt destination; omitted = stdout")
        else:
            p.add_argument("--export-dir", type=Path, default=Path("exports"))
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser()
    args = arguments.parse_args(argv)
    try:
        settings = RenderSettings(args.width, args.height, args.mode, args.yaw,
                                  args.pitch, args.angle4d, args.zoom, args.aspect, args.time)
        settings = replace(settings,
                           yaw=(settings.yaw % 360 + (settings.time % 30) * 12) % 360
                           if settings.mode != "2d" else settings.yaw,
                           angle4d=(settings.angle4d % 360 + (settings.time % 20) * 18) % 360
                           if settings.mode == "4d" else settings.angle4d)
    except ValueError as error:
        arguments.error(str(error))
    try:
        tree = generate_tree(args.seed)
        if args.command == "render":
            frame = render(tree, settings)
            if args.output is not None:
                with args.output.open("w", encoding="ascii", newline="\n") as stream:
                    stream.write(frame)
            else:
                # Binary stdout avoids Windows newline translation: file/stdout
                # produce identical bytes even through PowerShell redirection.
                if hasattr(sys.stdout, "buffer"):
                    sys.stdout.buffer.write(frame.encode("ascii"))
                    sys.stdout.buffer.flush()
                else:
                    sys.stdout.write(frame)
            return 0
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print("view requires an interactive TTY. Use: python -m ascii_tree render --seed 42 --mode 3d", file=sys.stderr)
            return 2
        return run(Explorer(tree, settings), args.export_dir)
    except BrokenPipeError:
        # Avoid a second flush error during Python shutdown after `| head`.
        try:
            sys.stdout.close()
        except BrokenPipeError:
            pass
        return 0
    except KeyboardInterrupt:
        return 0
    except OSError as error:
        print(f"ascii-tree: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
