"""Strict CSV input, integer money, and atomic report publication."""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

MAX_ROWS = 10_000
MAX_CENTS = 100_000_000
ORDER_FIELDS = ("order_id", "currency", "amount")
PAYMENT_FIELDS = ("payment_id", "order_id", "currency", "amount")
_AMOUNT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?")
_CURRENCY = re.compile(r"[A-Z]{3}")


class ReconcileError(ValueError):
    """Input or output violates the reconciliation contract."""


@dataclass
class _RowBudget:
    used: int = 0

    def consume(self) -> None:
        self.used += 1
        if self.used > MAX_ROWS:
            raise ReconcileError("inputs exceed the combined 10000 data row limit")


def _strict_lines(lines: Iterable[str]) -> Iterator[str]:
    """Reject misplaced quotes that csv.reader(strict=True) otherwise accepts.

    State persists across physical lines so quoted embedded newlines are valid.
    The csv module still performs record parsing and checks unterminated quotes.
    """
    state = "start"
    for line in lines:
        for character in line:
            if state == "quoted":
                if character == '"':
                    state = "closed"
            elif state == "closed":
                if character == '"':
                    state = "quoted"
                elif character == ",":
                    state = "start"
                elif character in "\r\n":
                    state = "start"
                else:
                    raise csv.Error("unexpected character after a closing quote")
            elif character == '"':
                if state != "start":
                    raise csv.Error("quote inside an unquoted field")
                state = "quoted"
            elif character == "," or character in "\r\n":
                state = "start"
            else:
                state = "unquoted"
        yield line


def _rows(
    path: Path, fields: tuple[str, ...], budget: _RowBudget
) -> Iterator[tuple[int, dict[str, str]]]:
    # No arbitrary field-length restriction: IDs are any nonempty strings.
    previous_limit = csv.field_size_limit(sys.maxsize)
    reader = None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(_strict_lines(stream), strict=True)
            header = next(reader, None)
            if header is None:
                raise ReconcileError(f"{path}: missing CSV header")
            if len(header) != len(set(header)):
                raise ReconcileError(f"{path}: duplicate CSV header")
            if len(header) != len(fields) or set(header) != set(fields):
                raise ReconcileError(
                    f"{path}: CSV headers must be exactly {','.join(fields)}"
                )
            for record_number, row in enumerate(reader, start=2):
                budget.consume()
                if len(row) != len(header):
                    raise ReconcileError(
                        f"{path}: record {record_number}: expected {len(header)} fields, "
                        f"got {len(row)}"
                    )
                yield record_number, dict(zip(header, row))
    except (csv.Error, UnicodeError) as error:
        line = reader.line_num if reader is not None else 0
        raise ReconcileError(f"{path}: invalid UTF-8 or malformed CSV near line {line}: {error}") from None
    finally:
        csv.field_size_limit(previous_limit)


def _money(value: str, *, positive: bool, location: str) -> int:
    if _AMOUNT.fullmatch(value) is None:
        raise ReconcileError(f"{location}: invalid amount")
    negative = value.startswith("-")
    unsigned = value[1:] if negative else value
    whole, _, fraction = unsigned.partition(".")
    # Check length before int() to handle arbitrarily long invalid amounts safely.
    if len(whole) > 7:
        raise ReconcileError(f"{location}: amount exceeds 1000000.00")
    cents = int(whole) * 100 + int(fraction.ljust(2, "0"))
    if cents > MAX_CENTS:
        raise ReconcileError(f"{location}: amount exceeds 1000000.00")
    if negative:
        cents = -cents
    if positive and cents <= 0:
        raise ReconcileError(f"{location}: order amount must be strictly positive")
    return cents


def _validate_fields(row: dict[str, str], location: str) -> None:
    for field in ("order_id", "payment_id"):
        if field in row and row[field] == "":
            raise ReconcileError(f"{location}: {field} must be nonempty")
    if _CURRENCY.fullmatch(row["currency"]) is None:
        raise ReconcileError(f"{location}: currency must be three uppercase ASCII letters")


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


def reconcile(orders_path: Path | str, payments_path: Path | str) -> dict:
    """Validate both complete inputs and return a deterministic report.

    Every physical data record counts toward the limit, including idempotent
    duplicates. Inputs are opened read-only and no output is created here.
    """
    orders_path, payments_path = Path(orders_path), Path(payments_path)
    budget = _RowBudget()
    expected: dict[str, tuple[str, int]] = {}
    received: dict[str, int] = {}
    for number, row in _rows(orders_path, ORDER_FIELDS, budget):
        location = f"{orders_path}: record {number}"
        _validate_fields(row, location)
        cents = _money(row["amount"], positive=True, location=location)
        order_id = row["order_id"]
        if order_id in expected:
            raise ReconcileError(f"{location}: duplicate order_id {order_id!r}")
        expected[order_id] = (row["currency"], cents)
        received[order_id] = 0

    payments: dict[str, tuple[str, str, int]] = {}
    for number, row in _rows(payments_path, PAYMENT_FIELDS, budget):
        location = f"{payments_path}: record {number}"
        _validate_fields(row, location)
        cents = _money(row["amount"], positive=False, location=location)
        order_id, currency, payment_id = row["order_id"], row["currency"], row["payment_id"]
        payload = (order_id, currency, cents)
        if payment_id in payments:
            if payments[payment_id] != payload:
                raise ReconcileError(f"{location}: conflicting payment_id {payment_id!r}")
            continue
        if order_id not in expected:
            raise ReconcileError(f"{location}: unknown order_id {order_id!r}")
        if currency != expected[order_id][0]:
            raise ReconcileError(f"{location}: payment currency differs from order currency")
        payments[payment_id] = payload
        received[order_id] += cents

    order_reports = []
    currency_totals: dict[str, dict] = {}
    for order_id in sorted(expected):
        currency, expected_cents = expected[order_id]
        received_cents = received[order_id]
        balance = expected_cents - received_cents
        order_reports.append({
            "order_id": order_id,
            "currency": currency,
            "expected_cents": expected_cents,
            "received_cents": received_cents,
            "balance_cents": balance,
            "status": _status(expected_cents, received_cents),
        })
        total = currency_totals.setdefault(currency, {
            "currency": currency,
            "expected_cents": 0,
            "received_cents": 0,
            "balance_cents": 0,
        })
        total["expected_cents"] += expected_cents
        total["received_cents"] += received_cents
        total["balance_cents"] += balance
    return {
        "schema": 1,
        "orders": order_reports,
        "totals": [currency_totals[currency] for currency in sorted(currency_totals)],
    }


def write_report(report: dict, output: Path | str) -> None:
    """Publish complete canonical UTF-8 bytes without replacing any path.

    A temporary file in the destination directory is fully written and synced
    before os.link atomically creates the destination. A concurrent creator wins
    safely: link fails if the destination already exists. No overwrite fallback
    is used when the filesystem does not support hard links.
    """
    output = Path(output)
    if os.path.lexists(output):
        raise ReconcileError(f"{output}: output already exists")
    data = (json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".ledgerreconcile-", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            # Publication has already succeeded or the primary failure must
            # propagate. Cleanup cannot turn a committed report into an error.
            pass
