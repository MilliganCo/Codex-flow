"""Run with python -m ledgerreconcile; no installation is needed."""

import argparse
from pathlib import Path
import sys
from typing import Sequence

from .core import reconcile, write_report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile orders and signed payments into exact-cent JSON, offline.",
        allow_abbrev=False,
    )
    parser.add_argument("--orders", type=Path, required=True, help="orders CSV (UTF-8 or UTF-8 BOM)")
    parser.add_argument("--payments", type=Path, required=True, help="payments CSV (UTF-8 or UTF-8 BOM)")
    parser.add_argument("--output", type=Path, required=True, help="new JSON path; existing paths are refused")
    args = parser.parse_args(argv)
    try:
        report = reconcile(args.orders, args.payments)
        write_report(report, args.output)
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"ledgerreconcile: error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ledgerreconcile: error: interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
