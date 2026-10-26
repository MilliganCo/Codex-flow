"""Validation, reconciliation, and atomic report publication (standard library only)."""

import csv
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TextIO


MAX_ROWS = 10_000
MAX_CENTS = 100_000_000
ORDER_COLUMNS = ("order_id", "currency", "amount")
PAYMENT_COLUMNS = ("payment_id", "order_id", "currency", "amount")
AMOUNT = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?")
CURRENCY = re.compile(r"[A-Z]{3}")


class ReconcileError(Exception):
    """An invalid input or an unsafe output destination."""


@dataclass
class _Order:
    currency: str
    expected_cents: int
    received_cents: int = 0


def _strict_lines(stream: TextIO, path: Path) -> Iterator[str]:
    """Reject invalid quote placement, which csv.reader(strict=True) alone accepts."""
    state = "start"
    line_number = 0
    for line_number, line in enumerate(stream, 1):
        for char in line:
            if state == "quoted":
                if char == '"':
                    state = "after_quote"
            elif state == "after_quote":
                if char == '"':
                    state = "quoted"
                elif char == "," or char in "\r\n":
                    state = "start"
                else:
                    raise ReconcileError(
                        f"{path}: line {line_number}: malformed CSV after closing quote"
                    )
            elif char == '"':
                if state != "start":
                    raise ReconcileError(
                        f"{path}: line {line_number}: malformed CSV quote in unquoted field"
                    )
                state = "quoted"
            elif char == "," or char in "\r\n":
                state = "start"
            else:
                state = "unquoted"
        yield line
    if state == "quoted":
        raise ReconcileError(f"{path}: line {line_number}: unterminated quoted CSV field")


def _rows(path: Path, columns: tuple[str, ...]) -> Iterator[dict[str, str]]:
    # IDs have no specified length limit; do not inherit csv's small default cap.
    previous_limit = csv.field_size_limit()
    field_limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(field_limit)
            break
        except OverflowError:
            # Windows builds may accept only a C long, narrower than sys.maxsize.
            field_limit //= 10
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(_strict_lines(stream, path), strict=True)
            header = next(reader, None)
            if header is None:
                raise ReconcileError(f"{path}: missing CSV header")
            if len(header) != len(columns) or set(header) != set(columns):
                raise ReconcileError(
                    f"{path}: headers must contain exactly {','.join(columns)} once each"
                )
            for row in reader:
                if len(row) != len(header):
                    raise ReconcileError(
                        f"{path}: line {reader.line_num}: wrong number of CSV fields"
                    )
                yield dict(zip(header, row))
    except csv.Error as exc:
        raise ReconcileError(f"{path}: malformed CSV: {exc}") from None
    except UnicodeError:
        raise ReconcileError(f"{path}: input must be valid UTF-8") from None
    finally:
        csv.field_size_limit(previous_limit)


def _cents(value: str) -> int:
    if AMOUNT.fullmatch(value) is None:
        raise ReconcileError("invalid amount: use decimal money with at most two fractional digits")
    unsigned = value.removeprefix("-")
    whole, dot, fraction = unsigned.partition(".")
    # Bound before int() so even enormous invalid amounts have controlled errors.
    if len(whole) > 7:
        raise ReconcileError("amount exceeds the absolute limit of 1000000.00")
    cents = int(whole) * 100 + (int(fraction.ljust(2, "0")) if dot else 0)
    if cents > MAX_CENTS:
        raise ReconcileError("amount exceeds the absolute limit of 1000000.00")
    return -cents if value.startswith("-") else cents


def _validate_fields(row: dict[str, str], *, payment: bool) -> int:
    if row["order_id"] == "" or (payment and row["payment_id"] == ""):
        raise ReconcileError("IDs must be nonempty strings")
    if CURRENCY.fullmatch(row["currency"]) is None:
        raise ReconcileError("currency must be exactly three uppercase ASCII letters")
    cents = _cents(row["amount"])
    if not payment and cents <= 0:
        raise ReconcileError("order amounts must be strictly positive")
    return cents


def _status(expected: int, received: int) -> str:
    if received < 0:
        return "negative_net"
    if received == 0:
        return "unpaid"
    if received < expected:
        return "partial"
    if received == expected:
        return "paid"
    return "overpaid"


def reconcile(orders_path: str | Path, payments_path: str | Path) -> dict:
    """Validate all input rows and return a deterministic report; write nothing."""
    orders: dict[str, _Order] = {}
    seen_payments: dict[str, tuple[str, str, int]] = {}
    row_count = 0

    for row in _rows(Path(orders_path), ORDER_COLUMNS):
        row_count += 1
        if row_count > MAX_ROWS:
            raise ReconcileError("inputs exceed the combined limit of 10000 data rows")
        cents = _validate_fields(row, payment=False)
        order_id = row["order_id"]
        if order_id in orders:
            raise ReconcileError(f"duplicate order ID: {order_id!r}")
        orders[order_id] = _Order(row["currency"], cents)

    for row in _rows(Path(payments_path), PAYMENT_COLUMNS):
        row_count += 1
        if row_count > MAX_ROWS:
            raise ReconcileError("inputs exceed the combined limit of 10000 data rows")
        cents = _validate_fields(row, payment=True)
        order_id = row["order_id"]
        payment_id = row["payment_id"]
        if order_id not in orders:
            raise ReconcileError(f"unknown order ID: {order_id!r}")
        order = orders[order_id]
        if row["currency"] != order.currency:
            raise ReconcileError(f"currency mismatch for order ID: {order_id!r}")
        payload = (order_id, row["currency"], cents)
        if payment_id in seen_payments:
            if seen_payments[payment_id] != payload:
                raise ReconcileError(f"conflicting duplicate payment ID: {payment_id!r}")
            continue
        seen_payments[payment_id] = payload
        order.received_cents += cents

    report_orders = []
    totals: dict[str, dict] = {}
    for order_id in sorted(orders):
        order = orders[order_id]
        balance = order.expected_cents - order.received_cents
        report_orders.append({
            "order_id": order_id,
            "currency": order.currency,
            "expected_cents": order.expected_cents,
            "received_cents": order.received_cents,
            "balance_cents": balance,
            "status": _status(order.expected_cents, order.received_cents),
        })
        total = totals.setdefault(order.currency, {
            "currency": order.currency,
            "expected_cents": 0,
            "received_cents": 0,
            "balance_cents": 0,
        })
        total["expected_cents"] += order.expected_cents
        total["received_cents"] += order.received_cents
        total["balance_cents"] += balance
    return {
        "schema": 1,
        "orders": report_orders,
        "totals": [totals[currency] for currency in sorted(totals)],
    }


def write_report(report: dict, output_path: str | Path) -> None:
    """Publish complete UTF-8 bytes atomically, without replacing any existing path."""
    output = Path(output_path)
    if os.path.lexists(output):
        raise ReconcileError(f"output already exists: {output}")
    content = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    staged: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=output.parent, prefix=".ledgerreconcile-", suffix=".tmp", delete=False
        ) as stream:
            staged = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # link() creates the destination in one operation and refuses all existing
        # files, directories, and symlinks, including ones created after lexists().
        os.link(staged, output)
    finally:
        if staged is not None:
            try:
                staged.unlink(missing_ok=True)
            except OSError:
                # Publication has already committed if link() succeeded. Cleanup
                # failure must not turn a complete published report into an error.
                pass
