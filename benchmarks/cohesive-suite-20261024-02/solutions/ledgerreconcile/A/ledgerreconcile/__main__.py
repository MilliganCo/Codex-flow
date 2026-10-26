"""Command-line entry point: python -m ledgerreconcile."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import ReconcileError, reconcile, write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ledgerreconcile",
        description="Reconcile offline UTF-8 order and payment CSVs into an exact-cent JSON report.",
        allow_abbrev=False,
    )
    parser.add_argument("--orders", required=True, type=Path, help="orders CSV: order_id,currency,amount")
    parser.add_argument("--payments", required=True, type=Path, help="payments CSV: payment_id,order_id,currency,amount")
    parser.add_argument("--output", required=True, type=Path, help="new JSON path; existing paths are never overwritten")
    args = parser.parse_args(argv)
    try:
        report = reconcile(args.orders, args.payments)
        write_report(report, args.output)
    except (ReconcileError, OSError, UnicodeError) as error:
        print(f"ledgerreconcile: error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ledgerreconcile: error: interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
