"""Command-line interface: python -m safezip."""

import argparse
import sys
import zipfile
import zlib

from .core import SafeZipError, extract_archive, inspect_archive, manifest_json


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m safezip",
        description="Inspect or transactionally extract a portable, bounded ZIP archive offline.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="validate and print the canonical manifest")
    inspect.add_argument("archive", help="path to a stored/deflated ZIP archive")
    extract = commands.add_parser("extract", help="validate and extract into a new directory")
    extract.add_argument("archive", help="path to a stored/deflated ZIP archive")
    extract.add_argument("--dest", required=True, help="absent destination; its parent must exist")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            manifest = inspect_archive(args.archive)
        else:
            manifest = extract_archive(args.archive, args.dest)
        # Binary output avoids Windows newline translation: the manifest ends with one LF.
        sys.stdout.buffer.write(manifest_json(manifest).encode("utf-8"))
        sys.stdout.buffer.flush()
        return 0
    except (SafeZipError, OSError, zipfile.BadZipFile, zipfile.LargeZipFile,
            zlib.error, UnicodeError, ValueError, NotImplementedError, EOFError) as error:
        print(f"safezip: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("safezip: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
