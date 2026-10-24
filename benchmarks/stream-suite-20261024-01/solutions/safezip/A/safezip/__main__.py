"""Command-line interface; stdout is reserved for canonical manifest bytes."""

import argparse
import json
import struct
import sys
import zipfile
import zlib

from .core import SafeZipError, extract_archive, validate_archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="safezip", description="Inspect or transactionally extract a portable, bounded ZIP archive."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="validate a ZIP and print its canonical manifest")
    inspect.add_argument("archive", help="path to a stored/deflated ZIP archive")
    extract = commands.add_parser("extract", help="validate, then extract into a new directory")
    extract.add_argument("archive", help="path to a stored/deflated ZIP archive")
    extract.add_argument("--dest", required=True, help="absent destination; its parent must already exist")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            manifest, _ = validate_archive(args.archive)
        else:
            manifest = extract_archive(args.archive, args.dest)
        encoded = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        # Binary output avoids Windows newline translation, preserving exact JSON bytes.
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
        return 0
    except (SafeZipError, OSError, ValueError, EOFError, NotImplementedError, struct.error,
            zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error) as error:
        print(f"safezip: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("safezip: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
