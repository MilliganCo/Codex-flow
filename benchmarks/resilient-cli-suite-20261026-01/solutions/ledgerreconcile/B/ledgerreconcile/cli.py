"""Command-line interface; successful runs are silent."""

import argparse
import sys
from pathlib import Path

from .core import LedgerError, build_report, write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ledgerreconcile",
        description="Reconcile UTF-8 orders and payments offline using exact integer cents.",
        allow_abbrev=False,
    )
    parser.add_argument("--orders", type=Path, required=True, help="orders CSV input")
    parser.add_argument("--payments", type=Path, required=True, help="payments CSV input")
    parser.add_argument(
        "--output", type=Path, required=True,
        help="new JSON report path (existing files and directories are never replaced)",
    )
    args = parser.parse_args(argv)
    try:
        report = build_report(args.orders, args.payments)
        write_report(report, args.output)
    except (LedgerError, OSError, UnicodeError, ValueError) as exc:
        print(f"ledgerreconcile: error: {exc}", file=sys.stderr)
        return 1
    return 0
