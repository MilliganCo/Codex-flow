"""CSV validation, integer-cent accounting, and atomic report publication."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Iterator, TextIO


MAX_ROWS = 10_000
MAX_CENTS = 100_000_000
ORDER_HEADERS = ("order_id", "currency", "amount")
PAYMENT_HEADERS = ("payment_id", "order_id", "currency", "amount")
_MONEY = re.compile(r"-?(0|[1-9][0-9]*)(?:\.([0-9]{1,2}))?")
_CURRENCY = re.compile(r"[A-Z]{3}")


class ReconciliationError(ValueError):
    """An invalid input or an output that cannot safely be published."""


def parse_cents(value: str) -> int:
    """Parse the exact money grammar without floats, rounding, or huge ints."""
    match = _MONEY.fullmatch(value)
    if match is None:
        raise ReconciliationError(f"invalid amount: {value!r}")
    whole, fraction = match.group(1), match.group(2) or ""
    # Check length before int(): Python also limits conversion of huge integers.
    if len(whole) > 7:
        raise ReconciliationError("amount exceeds absolute limit 1000000.00")
    cents = int(whole) * 100 + int(fraction.ljust(2, "0"))
    if cents > MAX_CENTS:
        raise ReconciliationError("amount exceeds absolute limit 1000000.00")
    return -cents if value.startswith("-") else cents


def _checked_lines(stream: TextIO, path: Path) -> Iterator[str]:
    """Reject stray quotes that even csv.reader(strict=True) otherwise accepts.

    csv.reader still parses all fields, escaped quotes, and embedded newlines.
    This small lexical check requires quotes to enclose a complete field.
    """
    state = "start"
    for line_number, line in enumerate(stream, 1):
        for char in line:
            if state == "quoted":
                if char == '"':
                    state = "closed"
            elif state == "closed":
                if char == '"':
                    state = "quoted"
                elif char in ",\r\n":
                    state = "start"
                else:
                    raise ReconciliationError(
                        f"{path}: line {line_number}: malformed CSV after closing quote"
                    )
            elif char == '"':
                if state != "start":
                    raise ReconciliationError(
                        f"{path}: line {line_number}: malformed CSV quote in unquoted field"
                    )
                state = "quoted"
            elif char in ",\r\n":
                state = "start"
            else:
                state = "unquoted"
        yield line
    if state == "quoted":
        raise ReconciliationError(f"{path}: malformed CSV: unterminated quoted field")


def _read_table(
    path: Path, required: tuple[str, ...], remaining: int
) -> list[tuple[int, dict[str, str]]]:
    rows: list[tuple[int, dict[str, str]]] = []
    field_limit = sys.maxsize
    while True:
        try:
            previous_limit = csv.field_size_limit(field_limit)
            break
        except OverflowError:
            # On Windows csv's C long can be narrower than Python's ssize_t.
            field_limit //= 10
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(_checked_lines(stream, path), strict=True)
            try:
                header = next(reader, None)
                if header is None:
                    raise ReconciliationError(f"{path}: missing CSV header")
                if len(header) != len(required) or set(header) != set(required):
                    raise ReconciliationError(
                        f"{path}: header must contain exactly {','.join(required)}"
                    )
                for values in reader:
                    if len(rows) >= remaining:
                        raise ReconciliationError(
                            f"inputs exceed the {MAX_ROWS} data row limit"
                        )
                    if len(values) != len(header):
                        raise ReconciliationError(
                            f"{path}: line {reader.line_num}: wrong number of CSV fields"
                        )
                    rows.append((reader.line_num, dict(zip(header, values))))
            except csv.Error as exc:
                raise ReconciliationError(
                    f"{path}: line {reader.line_num}: malformed CSV: {exc}"
                ) from exc
    finally:
        csv.field_size_limit(previous_limit)
    return rows


def _validate_row(row: dict[str, str], context: str, payment: bool) -> int:
    for field in (("order_id", "payment_id") if payment else ("order_id",)):
        if row[field] == "":
            raise ReconciliationError(f"{context}: {field} must be nonempty")
    if _CURRENCY.fullmatch(row["currency"]) is None:
        raise ReconciliationError(f"{context}: currency must be three uppercase ASCII letters")
    try:
        cents = parse_cents(row["amount"])
    except ReconciliationError as exc:
        raise ReconciliationError(f"{context}: {exc}") from exc
    if not payment and cents <= 0:
        raise ReconciliationError(f"{context}: order amount must be strictly positive")
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


def reconcile(orders_path: Path, payments_path: Path) -> dict:
    """Validate both inputs in full and return the deterministic report."""
    order_rows = _read_table(orders_path, ORDER_HEADERS, MAX_ROWS)
    orders: dict[str, tuple[str, int]] = {}
    received: dict[str, int] = {}
    for line, row in order_rows:
        context = f"{orders_path}: line {line}"
        cents = _validate_row(row, context, payment=False)
        order_id = row["order_id"]
        if order_id in orders:
            raise ReconciliationError(f"{context}: duplicate order ID {order_id!r}")
        orders[order_id] = (row["currency"], cents)
        received[order_id] = 0

    payment_rows = _read_table(payments_path, PAYMENT_HEADERS, MAX_ROWS - len(order_rows))
    payments: dict[str, tuple[str, str, int]] = {}
    for line, row in payment_rows:
        context = f"{payments_path}: line {line}"
        cents = _validate_row(row, context, payment=True)
        payment_id, order_id, currency = row["payment_id"], row["order_id"], row["currency"]
        if order_id not in orders:
            raise ReconciliationError(f"{context}: unknown order ID {order_id!r}")
        if currency != orders[order_id][0]:
            raise ReconciliationError(f"{context}: currency mismatch for order {order_id!r}")
        payload = (order_id, currency, cents)
        if payment_id in payments:
            if payments[payment_id] != payload:
                raise ReconciliationError(f"{context}: conflicting payment ID {payment_id!r}")
            continue
        payments[payment_id] = payload
        received[order_id] += cents

    report_orders = []
    currency_sums: dict[str, list[int]] = {}
    for order_id in sorted(orders):
        currency, expected = orders[order_id]
        net = received[order_id]
        report_orders.append(
            {
                "order_id": order_id,
                "currency": currency,
                "expected_cents": expected,
                "received_cents": net,
                "balance_cents": expected - net,
                "status": _status(expected, net),
            }
        )
        sums = currency_sums.setdefault(currency, [0, 0])
        sums[0] += expected
        sums[1] += net
    totals = [
        {
            "currency": currency,
            "expected_cents": currency_sums[currency][0],
            "received_cents": currency_sums[currency][1],
            "balance_cents": currency_sums[currency][0] - currency_sums[currency][1],
        }
        for currency in sorted(currency_sums)
    ]
    return {"schema": 1, "orders": report_orders, "totals": totals}


def write_report(report: dict, output: Path) -> None:
    """Stage complete UTF-8 bytes, then atomically link to a new destination.

    A hard link never replaces an existing path, including under concurrent
    creation. Filesystems without hard-link support fail without publishing.
    """
    payload = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if os.path.lexists(output):
        raise ReconciliationError(f"output already exists: {output}")
    descriptor, temporary = tempfile.mkstemp(prefix=".ledgerreconcile-", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError as exc:
            raise ReconciliationError(f"output already exists: {output}") from exc
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            # Publication may already have succeeded; cleanup cannot undo it.
            pass
