"""Strict CSV validation, deterministic reconciliation and atomic publication."""

import csv
import json
import os
import re
import struct
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

MAX_ROWS = 10_000
MAX_CENTS = 100_000_000
_MONEY = re.compile(r"-?(0|[1-9][0-9]*)(?:\.([0-9]{1,2}))?")
_CURRENCY = re.compile(r"[A-Z]{3}")


class LedgerError(Exception):
    """An invalid ledger or a destination that cannot be safely published."""


def _strict_lines(stream: TextIO, label: str) -> Iterator[str]:
    """Reject stray quotes, which csv.reader accepts even with strict=True.

    Keep newlines unchanged, including those inside quoted fields. csv.reader
    handles record construction and escaped quotes after this lexical check.
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
                elif char == ",":
                    state = "start"
                elif char in "\r\n":
                    state = "start"
                else:
                    raise LedgerError(
                        f"{label}: malformed CSV at line {line_number}: text after closing quote"
                    )
            elif char == '"':
                if state != "start":
                    raise LedgerError(
                        f"{label}: malformed CSV at line {line_number}: quote in unquoted field"
                    )
                state = "quoted"
            elif char == "," or char in "\r\n":
                state = "start"
            else:
                state = "unquoted"
        yield line
    if state == "quoted":
        raise LedgerError(f"{label}: malformed CSV: unterminated quoted field")


def _read_rows(
    path: Path, headers: tuple[str, ...], label: str, remaining: int,
) -> list[dict[str, str]]:
    # IDs have no field-length limit in the format. Restore the process setting
    # even if parsing fails; the default csv limit would reject valid long IDs.
    c_long_max = (1 << (8 * struct.calcsize("l") - 1)) - 1
    old_limit = csv.field_size_limit(min(sys.maxsize, c_long_max))
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(_strict_lines(stream, label), strict=True)
            actual = next(reader, None)
            if actual is None or len(actual) != len(headers) or set(actual) != set(headers):
                raise LedgerError(f"{label}: headers must be exactly {','.join(headers)}")
            rows = []
            for record_number, row in enumerate(reader, 1):
                if len(row) != len(headers):
                    raise LedgerError(f"{label}: record {record_number} has the wrong field count")
                if len(rows) >= remaining:
                    raise LedgerError(f"inputs exceed the {MAX_ROWS} data-row limit")
                rows.append(dict(zip(actual, row)))
            return rows
    except UnicodeError:
        raise LedgerError(f"{label}: input must be valid UTF-8") from None
    except csv.Error as exc:
        raise LedgerError(f"{label}: malformed CSV: {exc}") from None
    finally:
        csv.field_size_limit(old_limit)


def _cents(value: str, label: str) -> int:
    match = _MONEY.fullmatch(value)
    if match is None:
        raise LedgerError(f"{label}: invalid amount syntax")
    whole, fractional = match.groups()
    # Check length before int(): arbitrarily large digit strings are invalid
    # amounts and must not trigger Python's integer-string conversion limit.
    if len(whole) > 7:
        raise LedgerError(f"{label}: amount exceeds 1000000.00")
    cents = int(whole) * 100 + int((fractional or "").ljust(2, "0"))
    if cents > MAX_CENTS:
        raise LedgerError(f"{label}: amount exceeds 1000000.00")
    return -cents if value.startswith("-") else cents


def _validate(row: dict[str, str], label: str, *, payment: bool) -> int:
    if not row["order_id"] or (payment and not row["payment_id"]):
        raise LedgerError(f"{label}: IDs must be nonempty")
    if _CURRENCY.fullmatch(row["currency"]) is None:
        raise LedgerError(f"{label}: currency must be three uppercase ASCII letters")
    cents = _cents(row["amount"], label)
    if not payment and cents <= 0:
        raise LedgerError(f"{label}: order amounts must be strictly positive")
    return cents


def _status(received: int, expected: int) -> str:
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
    """Validate both files completely, then return the version 1 report."""
    order_rows = _read_rows(
        Path(orders_path), ("order_id", "currency", "amount"), "orders", MAX_ROWS,
    )
    orders: dict[str, tuple[str, int]] = {}
    for number, row in enumerate(order_rows, 1):
        label = f"orders: record {number}"
        expected = _validate(row, label, payment=False)
        order_id = row["order_id"]
        if order_id in orders:
            raise LedgerError(f"{label}: duplicate order ID")
        orders[order_id] = (row["currency"], expected)

    payment_rows = _read_rows(
        Path(payments_path), ("payment_id", "order_id", "currency", "amount"),
        "payments", MAX_ROWS - len(order_rows),
    )
    seen: dict[str, tuple[str, str, int]] = {}
    received = dict.fromkeys(orders, 0)
    for number, row in enumerate(payment_rows, 1):
        label = f"payments: record {number}"
        cents = _validate(row, label, payment=True)
        order_id, currency = row["order_id"], row["currency"]
        if order_id not in orders:
            raise LedgerError(f"{label}: unknown order ID")
        if currency != orders[order_id][0]:
            raise LedgerError(f"{label}: currency does not match the order")
        payload = (order_id, currency, cents)
        payment_id = row["payment_id"]
        if payment_id in seen:
            if seen[payment_id] != payload:
                raise LedgerError(f"{label}: conflicting duplicate payment ID")
        else:
            seen[payment_id] = payload
            received[order_id] += cents

    entries = []
    totals: dict[str, dict] = {}
    for order_id in sorted(orders):
        currency, expected = orders[order_id]
        actual = received[order_id]
        balance = expected - actual
        entries.append({
            "order_id": order_id,
            "currency": currency,
            "expected_cents": expected,
            "received_cents": actual,
            "balance_cents": balance,
            "status": _status(actual, expected),
        })
        total = totals.setdefault(currency, {
            "currency": currency, "expected_cents": 0,
            "received_cents": 0, "balance_cents": 0,
        })
        total["expected_cents"] += expected
        total["received_cents"] += actual
        total["balance_cents"] += balance
    return {"schema": 1, "orders": entries, "totals": [totals[c] for c in sorted(totals)]}


def write_report(report: dict, output_path: str | Path) -> None:
    """Publish a complete UTF-8 report without replacing any destination.

    A hard link atomically publishes a fully written sibling temporary file.
    Unlike replace/rename on POSIX, it fails if any destination already exists,
    including one created concurrently. Unsupported filesystems fail safely.
    """
    output = Path(output_path)
    data = (json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".ledgerreconcile-", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError:
            raise LedgerError("output already exists; refusing to overwrite it") from None
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            # Publication is the last fallible operation affecting the report.
            # A cleanup failure must not turn a completed publication into an
            # error; the destination always contains the full serialized bytes.
            pass
