"""Strict input validation, deterministic reconciliation, and no-replace publication."""

import csv
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile


MAX_ROWS = 10000
MAX_CENTS = 100000000
MONEY = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?")
CURRENCY = re.compile(r"[A-Z]{3}")
ORDER_HEADER = ("order_id", "currency", "amount")
PAYMENT_HEADER = ("payment_id", "order_id", "currency", "amount")


class ReconcileError(Exception):
    """A controlled validation or publication failure."""


def cents(value):
    """Parse the specified decimal grammar without floating point or rounding."""
    if MONEY.fullmatch(value) is None:
        raise ReconcileError("invalid amount syntax")
    negative = value.startswith("-")
    unsigned = value[1:] if negative else value
    whole, _, fraction = unsigned.partition(".")
    # Reject huge values before int() to avoid Python's integer digit limit.
    if len(whole) > 7:
        raise ReconcileError("amount exceeds 1000000.00")
    result = int(whole) * 100 + int(fraction.ljust(2, "0") or "0")
    if result > MAX_CENTS:
        raise ReconcileError("amount exceeds 1000000.00")
    return -result if negative else result


def validate_quotes(text, label):
    """Reject malformed quote placement that csv.reader(strict=True) tolerates.

    CR and LF terminate records outside quoted fields; inside quotes they are
    preserved. Doubled quotes are the only quote escape.
    """
    state = "start"
    for char in text:
        if state == "quoted":
            if char == '"':
                state = "closed"
        elif state == "closed":
            if char == '"':
                state = "quoted"
            elif char in ",\r\n":
                state = "start"
            else:
                raise ReconcileError(f"{label}: malformed CSV after closing quote")
        elif char == '"':
            if state != "start":
                raise ReconcileError(f"{label}: malformed CSV quote in unquoted field")
            state = "quoted"
        elif char in ",\r\n":
            state = "start"
        else:
            state = "plain"
    if state == "quoted":
        raise ReconcileError(f"{label}: unterminated quoted CSV field")


def records(path, header, label, row_count):
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as source:
            text = source.read()
    except (OSError, UnicodeError, ValueError) as exc:
        raise ReconcileError(f"{label}: cannot read UTF-8 input") from exc
    validate_quotes(text, label)
    # IDs have no specified size limit. Do not inherit csv's small default cap.
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            break
        except OverflowError:
            limit //= 10
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        actual = next(reader, None)
        if actual is None or len(actual) != len(header) or set(actual) != set(header):
            raise ReconcileError(f"{label}: missing, extra, or duplicate CSV headers")
        for row in reader:
            row_count[0] += 1
            if row_count[0] > MAX_ROWS:
                raise ReconcileError("combined inputs exceed 10000 data rows")
            if len(row) != len(header):
                raise ReconcileError(f"{label}: wrong field count at line {reader.line_num}")
            yield dict(zip(actual, row))
    except csv.Error as exc:
        raise ReconcileError(f"{label}: malformed CSV at line {reader.line_num}") from exc


def fields(row, label):
    if not row["order_id"]:
        raise ReconcileError(f"{label}: order_id must be nonempty")
    if CURRENCY.fullmatch(row["currency"]) is None:
        raise ReconcileError(f"{label}: currency must be three uppercase ASCII letters")
    try:
        amount = cents(row["amount"])
    except ReconcileError as exc:
        raise ReconcileError(f"{label}: {exc}") from exc
    return row["order_id"], row["currency"], amount


def status(expected, received):
    if received < 0:
        return "negative_net"
    if received == 0:
        return "unpaid"
    if received < expected:
        return "partial"
    if received == expected:
        return "paid"
    return "overpaid"


def reconcile(orders_path, payments_path):
    count = [0]
    orders = {}
    received = {}
    for row in records(orders_path, ORDER_HEADER, "orders", count):
        order_id, currency, expected = fields(row, "orders")
        if expected <= 0:
            raise ReconcileError("orders: amount must be strictly positive")
        if order_id in orders:
            raise ReconcileError("orders: duplicate order_id")
        orders[order_id] = (currency, expected)
        received[order_id] = 0
    payments = {}
    for row in records(payments_path, PAYMENT_HEADER, "payments", count):
        order_id, currency, amount = fields(row, "payments")
        payment_id = row["payment_id"]
        if not payment_id:
            raise ReconcileError("payments: payment_id must be nonempty")
        if order_id not in orders:
            raise ReconcileError("payments: unknown order_id")
        if orders[order_id][0] != currency:
            raise ReconcileError("payments: currency does not match order")
        payload = (order_id, currency, amount)
        if payment_id in payments:
            if payments[payment_id] != payload:
                raise ReconcileError("payments: conflicting duplicate payment_id")
            continue
        payments[payment_id] = payload
        received[order_id] += amount
    order_rows = []
    totals = {}
    for order_id in sorted(orders):
        currency, expected = orders[order_id]
        paid = received[order_id]
        balance = expected - paid
        order_rows.append({
            "order_id": order_id, "currency": currency,
            "expected_cents": expected, "received_cents": paid,
            "balance_cents": balance, "status": status(expected, paid),
        })
        total = totals.setdefault(currency, {
            "currency": currency, "expected_cents": 0,
            "received_cents": 0, "balance_cents": 0,
        })
        total["expected_cents"] += expected
        total["received_cents"] += paid
        total["balance_cents"] += balance
    return {"schema": 1, "orders": order_rows,
            "totals": [totals[currency] for currency in sorted(totals)]}


def publish(report, output):
    """Link a complete sibling temporary file atomically, never replacing a path.

    A hard link is a single no-replace operation on both Windows and POSIX. If
    the filesystem does not support it, fail safely instead of exposing a partial
    destination. No output path is opened for writing.
    """
    destination = Path(output)
    if os.path.lexists(destination):
        raise ReconcileError("output already exists")
    data = (json.dumps(report, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".ledgerreconcile-", suffix=".tmp",
                                         dir=destination.parent)
        with os.fdopen(fd, "wb") as staged:
            staged.write(data)
            staged.flush()
            os.fsync(staged.fileno())
        os.link(temporary, destination)
    except OSError as exc:
        raise ReconcileError("cannot publish output; path must be new and parent writable") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                # Publication is the commit point. Cleanup cannot undo it or
                # turn an already published complete report into a failure.
                pass
