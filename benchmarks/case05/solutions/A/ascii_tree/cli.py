"""Headless output is byte-stable ASCII; interactive input is never required."""

import argparse
import math
from pathlib import Path
import sys

from . import __version__
from .app import Explorer
from .geometry import View
from .model import generate_tree
from .render import render
from .terminal import Terminal


def finite_number(text):
    number = float(text)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError('must be a finite number')
    return number


def bounded_integer(low, high):
    def parse(text):
        value = int(text)
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f'must be in {low}..{high}')
        return value
    return parse


def parser():
    root = argparse.ArgumentParser(prog='ascii-tree', description='Explore one procedural ASCII tree in 2D, 3D and true 4D projections.')
    root.add_argument('--version', action='version', version=__version__)
    actions = root.add_subparsers(dest='action', required=True)
    for name in ('view', 'render'):
        action = actions.add_parser(name, help='Interactive terminal explorer' if name == 'view' else 'Deterministic ASCII frame; no TTY needed')
        action.add_argument('--seed', type=int, default=42)
        action.add_argument('--mode', choices=('2d', '3d', '4d'), default='3d')
        action.add_argument('--width', type=bounded_integer(1, 500), default=100, help='Headless columns, 1..500 (default 100)')
        action.add_argument('--height', type=bounded_integer(1, 200), default=40, help='Headless rows, 1..200 (default 40)')
        action.add_argument('--yaw', type=finite_number, default=-20, help='3D orbit in degrees')
        action.add_argument('--pitch', type=finite_number, default=8, help='3D tilt in degrees')
        action.add_argument('--angle4', type=finite_number, default=0, help='4D XW rotation in degrees')
        action.add_argument('--zoom', type=finite_number, default=1)
        action.add_argument('--time', type=finite_number, default=0, help='Deterministic animation time in seconds (default 0)')
        if name == 'view':
            action.add_argument('--export-dir', type=Path, default=Path('exports'))
        else:
            action.add_argument('--output', type=Path, help='Write pure ASCII with LF line endings; otherwise stdout')
    return root


def main(argv=None):
    arguments_parser = parser()
    args = arguments_parser.parse_args(argv)
    if not 0.1 <= args.zoom <= 8:
        arguments_parser.error('--zoom must be in 0.1..8')
    view = View(args.mode, args.yaw % 360, args.pitch,
                args.angle4 % 360, args.zoom, args.time)
    try:
        if args.action == 'view' and sys.stdin.isatty() and sys.stdout.isatty():
            Explorer(args.seed, view, args.export_dir).run(Terminal())
            return 0
        if args.action == 'view':
            print('No interactive TTY: rendering one frame. Use render --output FILE for export.', file=sys.stderr)
        frame = render(generate_tree(args.seed), view, args.width, args.height)
        if args.action == 'render' and args.output is not None:
            frame.save(args.output)
        else:
            # Bypass Windows CRLF conversion so pipes match --output bytes.
            if hasattr(sys.stdout, 'buffer'):
                sys.stdout.buffer.write(frame.text().encode('ascii'))
                sys.stdout.buffer.flush()
            else:
                sys.stdout.write(frame.text())
        return 0
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0
    except OSError as error:
        print(f'ascii-tree: {error}', file=sys.stderr)
        return 1

