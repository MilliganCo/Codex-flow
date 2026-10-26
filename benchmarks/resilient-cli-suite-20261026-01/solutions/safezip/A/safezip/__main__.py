"""Command line entry point; successful commands emit only canonical JSON."""

import argparse
import sys

from . import SafeZipError, extract_archive, inspect_archive, manifest_bytes


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="safezip", description="Inspect or safely extract a bounded, portable ZIP archive."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="validate and hash without writing files")
    inspect.add_argument("archive", help="path to a stored/deflated ZIP archive")
    extract = commands.add_parser("extract", help="validate and extract into a new directory")
    extract.add_argument("archive", help="path to a stored/deflated ZIP archive")
    extract.add_argument("--dest", required=True, help="absent destination; parent must exist")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            manifest = inspect_archive(args.archive)
        else:
            manifest = extract_archive(args.archive, args.dest)
        # Write bytes so Windows cannot translate the required LF into CRLF.
        sys.stdout.buffer.write(manifest_bytes(manifest))
        sys.stdout.buffer.flush()
    except (SafeZipError, OSError) as exc:
        print(f"safezip: {ascii(str(exc))[1:-1]}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("safezip: interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
