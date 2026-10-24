"""Command line entry point: python -m ledgerreconcile."""

from __future__ import annotations

import argparse
import csv
import sys

from .core import ReconciliationError, build_report, report_bytes, write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ledgerreconcile",
        description="Reconcile CSV orders and payments offline using exact integer cents.",
        allow_abbrev=False,
    )
    parser.add_argument("--orders", required=True, help="orders CSV (UTF-8, optional BOM)")
    parser.add_argument("--payments", required=True, help="payments CSV (UTF-8, optional BOM)")
    parser.add_argument("--output", required=True, help="new JSON path; existing paths are never overwritten")
    arguments = parser.parse_args(argv)
    try:
        report = build_report(arguments.orders, arguments.payments)
        write_report(arguments.output, report_bytes(report))
    except (ReconciliationError, OSError, UnicodeError, csv.Error, ValueError) as exc:
        # ascii() keeps diagnostics printable even in a restricted terminal
        # encoding, and escapes control characters originating in input paths.
        print(f"ledgerreconcile: error: {ascii(str(exc))[1:-1]}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ledgerreconcile: error: interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
