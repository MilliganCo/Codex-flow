"""Run with python -m ledgerreconcile."""

import argparse
import sys

from .core import ReconcileError, reconcile, write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile UTF-8 orders and payments using exact integer cents.",
        epilog="The output must be a new path. Existing files and directories are preserved.",
    )
    parser.add_argument("--orders", required=True, metavar="CSV", help="orders CSV input")
    parser.add_argument("--payments", required=True, metavar="CSV", help="payments CSV input")
    parser.add_argument("--output", required=True, metavar="JSON", help="new JSON report path")
    args = parser.parse_args(argv)
    try:
        report = reconcile(args.orders, args.payments)
        write_report(report, args.output)
    except (ReconcileError, OSError, UnicodeError, ValueError) as exc:
        print(f"ledgerreconcile: error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ledgerreconcile: error: interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
