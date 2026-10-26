"""Command-line entry point: python -m safezip."""

import argparse
import sys

from .core import SafeZipError, extract_archive, inspect_archive, manifest_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m safezip",
        description="Inspect or transactionally extract a portable, bounded ZIP archive offline.")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="validate the whole ZIP and print its manifest")
    inspect.add_argument("archive", help="path to a stored/deflated ZIP archive")
    extract = commands.add_parser("extract", help="extract into a new directory and print its manifest")
    extract.add_argument("archive", help="path to a stored/deflated ZIP archive")
    extract.add_argument("--dest", required=True,
                         help="absent destination; its parent directory must already exist")
    args = parser.parse_args(argv)
    try:
        manifest = (inspect_archive(args.archive) if args.command == "inspect"
                    else extract_archive(args.archive, args.dest))
        sys.stdout.buffer.write(manifest_bytes(manifest))
        sys.stdout.buffer.flush()
        return 0
    except (SafeZipError, OSError) as exc:
        print(f"safezip: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("safezip: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
