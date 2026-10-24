"""Command-line interface; all expected failures have controlled diagnostics."""

import argparse
import os
import sys

from .core import LedgerError, reconcile, write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ledgerreconcile",
        description="Reconcile UTF-8 order and payment CSVs into an exact-cent JSON report.",
        allow_abbrev=False,
    )
    parser.add_argument("--orders", required=True, metavar="CSV", help="orders CSV path")
    parser.add_argument("--payments", required=True, metavar="CSV", help="payments CSV path")
    parser.add_argument(
        "--output", required=True, metavar="JSON", help="new report path (must not already exist)"
    )
    args = parser.parse_args(argv)
    try:
        if os.path.lexists(args.output):
            raise LedgerError(f"output path already exists: {args.output!r}")
        report = reconcile(args.orders, args.payments)
        write_report(report, args.output)
    except (LedgerError, OSError, UnicodeError, ValueError) as exc:
        print(f"ledgerreconcile: error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ledgerreconcile: error: interrupted", file=sys.stderr)
        return 130
    return 0
