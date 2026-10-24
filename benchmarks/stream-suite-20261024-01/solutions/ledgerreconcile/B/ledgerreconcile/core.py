"""Validation, deterministic reconciliation, and create-only publication."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import re
import struct
import tempfile
from collections.abc import Iterator


MAX_ROWS = 10_000
MAX_CENTS = 100_000_000
ORDER_HEADERS = ("order_id", "currency", "amount")
PAYMENT_HEADERS = ("payment_id", "order_id", "currency", "amount")
_AMOUNT = re.compile(r"-?(0|[1-9][0-9]*)(?:\.[0-9]{1,2})?")
_CURRENCY = re.compile(r"[A-Z]{3}")


class ReconciliationError(ValueError):
    """An input or publication rule was violated."""


class _RowBudget:
    def __init__(self) -> None:
        self.count = 0

    def consume(self) -> None:
        self.count += 1
        if self.count > MAX_ROWS:
            raise ReconciliationError("inputs exceed the shared 10000 data-row limit")


def parse_amount(value: str, *, positive: bool = False) -> int:
    """Parse the specified decimal grammar into cents, without float or rounding."""
    if _AMOUNT.fullmatch(value) is None:
        raise ReconciliationError("invalid amount syntax")
    unsigned = value.removeprefix("-")
    whole, _, fraction = unsigned.partition(".")
    # Check length before int(), including on Python's integer-string digit limit.
    if len(whole) > 7:
        raise ReconciliationError("amount exceeds 1000000.00 in absolute value")
    cents = int(whole) * 100 + int(fraction.ljust(2, "0"))
    if cents > MAX_CENTS:
        raise ReconciliationError("amount exceeds 1000000.00 in absolute value")
    if value.startswith("-"):
        cents = -cents
    if positive and cents <= 0:
        raise ReconciliationError("order amounts must be strictly positive")
    return cents


def _strict_lines(source: Iterator[str]) -> Iterator[str]:
    """Reject stray quotes that csv.reader(strict=True) otherwise tolerates.

    Track fields across physical lines so quoted commas, escaped quotes, and
    embedded CR/LF remain valid and retain their original contents.
    """
    state = "start"
    for line in source:
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
                    raise ReconciliationError("malformed CSV: text after closing quote")
            elif char == '"':
                if state != "start":
                    raise ReconciliationError("malformed CSV: quote in unquoted field")
                state = "quoted"
            elif char in ",\r\n":
                state = "start"
            else:
                state = "unquoted"
        yield line
    if state == "quoted":
        raise ReconciliationError("malformed CSV: unterminated quoted field")


def _read_rows(
    path: Path, headers: tuple[str, ...], budget: _RowBudget
) -> Iterator[dict[str, str]]:
    # The specification limits record count, not identifier length.
    csv.field_size_limit((1 << (8 * struct.calcsize("l") - 1)) - 1)
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(_strict_lines(source), strict=True)
        try:
            actual = next(reader, None)
            if (
                actual is None
                or len(actual) != len(headers)
                or set(actual) != set(headers)
            ):
                raise ReconciliationError("missing, extra, or duplicate CSV headers")
            for fields in reader:
                budget.consume()
                if len(fields) != len(headers):
                    raise ReconciliationError("CSV row has the wrong number of fields")
                yield dict(zip(actual, fields))
        except (csv.Error, ReconciliationError) as exc:
            raise ReconciliationError(
                f"{path.name!r}, near line {reader.line_num}: {exc}"
            ) from None


def _currency(value: str) -> str:
    if _CURRENCY.fullmatch(value) is None:
        raise ReconciliationError("currency must be exactly three uppercase ASCII letters")
    return value


def _identifier(value: str, field: str) -> str:
    if value == "":
        raise ReconciliationError(f"{field} must be nonempty")
    return value


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


def build_report(orders_path: str | Path, payments_path: str | Path) -> dict:
    """Read both inputs completely and reconcile only validated logical payments."""
    budget = _RowBudget()
    orders: dict[str, tuple[str, int]] = {}
    received: dict[str, int] = {}
    for row in _read_rows(Path(orders_path), ORDER_HEADERS, budget):
        order_id = _identifier(row["order_id"], "order_id")
        currency = _currency(row["currency"])
        expected = parse_amount(row["amount"], positive=True)
        if order_id in orders:
            raise ReconciliationError(f"duplicate order_id: {order_id!r}")
        orders[order_id] = (currency, expected)
        received[order_id] = 0

    payments: dict[str, tuple[str, str, int]] = {}
    for row in _read_rows(Path(payments_path), PAYMENT_HEADERS, budget):
        payment_id = _identifier(row["payment_id"], "payment_id")
        order_id = _identifier(row["order_id"], "order_id")
        currency = _currency(row["currency"])
        cents = parse_amount(row["amount"])
        payload = (order_id, currency, cents)
        if payment_id in payments:
            if payments[payment_id] != payload:
                raise ReconciliationError(f"conflicting payment_id: {payment_id!r}")
            continue
        if order_id not in orders:
            raise ReconciliationError(f"unknown order_id: {order_id!r}")
        if currency != orders[order_id][0]:
            raise ReconciliationError(f"currency mismatch for order_id: {order_id!r}")
        payments[payment_id] = payload
        received[order_id] += cents

    order_results = []
    totals: dict[str, dict] = {}
    for order_id in sorted(orders):
        currency, expected = orders[order_id]
        net = received[order_id]
        balance = expected - net
        order_results.append(
            {
                "order_id": order_id,
                "currency": currency,
                "expected_cents": expected,
                "received_cents": net,
                "balance_cents": balance,
                "status": _status(expected, net),
            }
        )
        total = totals.setdefault(
            currency,
            {"currency": currency, "expected_cents": 0, "received_cents": 0, "balance_cents": 0},
        )
        total["expected_cents"] += expected
        total["received_cents"] += net
        total["balance_cents"] += balance
    return {
        "schema": 1,
        "orders": order_results,
        "totals": [totals[currency] for currency in sorted(totals)],
    }


def report_bytes(report: dict) -> bytes:
    """Return the single canonical UTF-8 representation, including its final LF."""
    return (
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def write_report(output: str | Path, data: bytes) -> None:
    """Publish complete bytes atomically without replacing any destination.

    Hard-linking a fully written sibling temporary file is an atomic create-only
    operation. Unsupported filesystems fail safely; no non-atomic fallback is used.
    """
    destination = Path(output)
    if os.path.lexists(destination):
        raise ReconciliationError("output already exists; choose a new output path")
    descriptor, temporary = tempfile.mkstemp(
        prefix=".ledgerreconcile-", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        # Publication is already complete after link succeeds. Cleanup failure
        # must not report an unsuccessful reconciliation with a published output.
        try:
            os.unlink(temporary)
        except OSError:
            pass
