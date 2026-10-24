"""CSV validation, reconciliation, and atomic no-overwrite JSON publication."""

import csv
import json
import os
from pathlib import Path
import re
import struct
import tempfile
from collections.abc import Iterator
from typing import TextIO


MAX_ROWS = 10_000
MAX_CENTS = 100_000_000
ORDER_HEADERS = ("order_id", "currency", "amount")
PAYMENT_HEADERS = ("payment_id", "order_id", "currency", "amount")
_AMOUNT = re.compile(r"-?(0|[1-9][0-9]*)(?:\.([0-9]{1,2}))?")
_CURRENCY = re.compile(r"[A-Z]{3}")


class LedgerError(ValueError):
    """Invalid ledger data or a report destination that cannot be published."""


def _cents(value: str) -> int:
    match = _AMOUNT.fullmatch(value)
    if match is None:
        raise LedgerError(f"invalid amount: {value!r}")
    whole, fraction = match.groups()
    # Check length before int(), including for arbitrarily long digit strings.
    if len(whole) > 7:
        raise LedgerError("amount absolute value exceeds 1000000.00")
    cents = int(whole) * 100 + int((fraction or "").ljust(2, "0"))
    if cents > MAX_CENTS:
        raise LedgerError("amount absolute value exceeds 1000000.00")
    return -cents if value.startswith("-") else cents


def _strict_lines(stream: TextIO) -> Iterator[str]:
    """Validate quote placement that csv.reader(strict=True) alone permits.

    Feed unchanged physical lines to csv.reader so embedded CR, LF, CRLF,
    delimiters, and escaped quotes retain their original field values.
    """
    state = "start"
    for line in stream:
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
                    raise LedgerError("malformed CSV: unexpected character after closing quote")
            elif char == '"':
                if state != "start":
                    raise LedgerError("malformed CSV: quote inside an unquoted field")
                state = "quoted"
            elif char == "," or char in "\r\n":
                state = "start"
            else:
                state = "unquoted"
        yield line
    if state == "quoted":
        raise LedgerError("malformed CSV: unterminated quoted field")


def _rows(path: Path, headers: tuple[str, ...]) -> Iterator[tuple[int, dict[str, str]]]:
    # IDs have no specified length limit. Restore the process-local CSV setting
    # when this reader closes, including if the consumer rejects a row early.
    previous_limit = csv.field_size_limit()
    try:
        # Python 3.12 accepts a C long here, which is 32-bit on Windows even
        # when the interpreter and sys.maxsize are 64-bit.
        csv.field_size_limit((1 << (8 * struct.calcsize("l") - 1)) - 1)
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(_strict_lines(stream), strict=True)
            actual = next(reader, None)
            if actual is None:
                raise LedgerError("missing CSV header")
            if len(actual) != len(headers) or set(actual) != set(headers):
                raise LedgerError(f"headers must contain exactly {','.join(headers)}")
            for number, values in enumerate(reader, start=1):
                if len(values) != len(headers):
                    raise LedgerError(f"data record {number}: wrong number of CSV fields")
                yield number, dict(zip(actual, values))
    except (csv.Error, LedgerError, UnicodeError) as exc:
        raise LedgerError(f"{str(path)!r}: {exc}") from None
    finally:
        csv.field_size_limit(previous_limit)


def _fields(row: dict[str, str], *, payment: bool) -> int:
    for key in (("order_id", "payment_id") if payment else ("order_id",)):
        if not row[key]:
            raise LedgerError(f"empty {key}")
    if _CURRENCY.fullmatch(row["currency"]) is None:
        raise LedgerError(f"invalid currency: {row['currency']!r}")
    amount = _cents(row["amount"])
    if not payment and amount <= 0:
        raise LedgerError("order amount must be strictly positive")
    return amount


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
    """Read both inputs without modifying them; return the complete report."""
    orders: dict[str, tuple[str, int]] = {}
    received: dict[str, int] = {}
    payments: dict[str, tuple[str, str, int]] = {}
    row_count = 0
    for path, headers, payment in (
        (Path(orders_path), ORDER_HEADERS, False),
        (Path(payments_path), PAYMENT_HEADERS, True),
    ):
        records = _rows(path, headers)
        try:
            for number, row in records:
                row_count += 1
                if row_count > MAX_ROWS:
                    raise LedgerError(f"at most {MAX_ROWS} data rows are allowed across both inputs")
                try:
                    amount = _fields(row, payment=payment)
                    order_id, currency = row["order_id"], row["currency"]
                    if not payment:
                        if order_id in orders:
                            raise LedgerError(f"duplicate order_id: {order_id!r}")
                        orders[order_id] = (currency, amount)
                        received[order_id] = 0
                        continue
                    if order_id not in orders:
                        raise LedgerError(f"unknown order_id: {order_id!r}")
                    if orders[order_id][0] != currency:
                        raise LedgerError(f"currency mismatch for order_id: {order_id!r}")
                    payment_id = row["payment_id"]
                    payload = (order_id, currency, amount)
                    if payment_id in payments:
                        if payments[payment_id] != payload:
                            raise LedgerError(f"conflicting duplicate payment_id: {payment_id!r}")
                        continue
                    payments[payment_id] = payload
                    received[order_id] += amount
                except LedgerError as exc:
                    raise LedgerError(f"{str(path)!r}: data record {number}: {exc}") from None
        finally:
            records.close()

    order_reports = []
    totals: dict[str, dict] = {}
    for order_id in sorted(orders):
        currency, expected = orders[order_id]
        actual = received[order_id]
        balance = expected - actual
        order_reports.append({
            "order_id": order_id,
            "currency": currency,
            "expected_cents": expected,
            "received_cents": actual,
            "balance_cents": balance,
            "status": _status(expected, actual),
        })
        total = totals.setdefault(currency, {
            "currency": currency, "expected_cents": 0, "received_cents": 0, "balance_cents": 0
        })
        total["expected_cents"] += expected
        total["received_cents"] += actual
        total["balance_cents"] += balance
    return {
        "schema": 1,
        "orders": order_reports,
        "totals": [totals[currency] for currency in sorted(totals)],
    }


def write_report(report: dict, output_path: str | Path) -> None:
    """Publish complete UTF-8 bytes atomically, refusing every existing path.

    A hard link publishes a fully written temporary file without replacement.
    Unlike replace() or POSIX rename(), link() also refuses a racing destination.
    If the filesystem cannot create hard links, fail without creating a report.
    """
    output = Path(output_path)
    if os.path.lexists(output):
        raise LedgerError(f"output path already exists: {str(output)!r}")
    data = (json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    fd, temporary_name = tempfile.mkstemp(prefix=".ledgerreconcile-", suffix=".tmp", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        # Once published, cleanup must not turn successful publication into a
        # reported failure. Never delete the destination, including on a race.
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
