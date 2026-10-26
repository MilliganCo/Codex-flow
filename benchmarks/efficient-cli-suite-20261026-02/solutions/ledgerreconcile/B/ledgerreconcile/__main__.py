"""Command-line entry point: python -m ledgerreconcile."""

import argparse
import sys

from .core import ReconcileError, publish, reconcile


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ledgerreconcile",
        description="Reconcile UTF-8 order and payment CSV files using exact integer cents.",
        allow_abbrev=False,
    )
    parser.add_argument("--orders", required=True, metavar="CSV", help="orders CSV input")
    parser.add_argument("--payments", required=True, metavar="CSV", help="payments CSV input")
    parser.add_argument("--output", required=True, metavar="JSON", help="new report path; must not exist")
    args = parser.parse_args(argv)
    try:
        report = reconcile(args.orders, args.payments)
        publish(report, args.output)
    except ReconcileError as exc:
        print(f"ledgerreconcile: error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, UnicodeError, OverflowError):
        print("ledgerreconcile: error: unable to process the requested file paths", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ledgerreconcile: error: interrupted", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
