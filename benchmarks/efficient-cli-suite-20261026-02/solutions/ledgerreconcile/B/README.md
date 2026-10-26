# LedgerReconcile 1.0

Offline order/payment reconciliation using Python 3.12 and only its standard
library. Run from this repository directory; no installation is needed.

```sh
python -m ledgerreconcile --help
```

Try the included tiny inputs (choose a fresh output filename on each run):

```sh
python -m ledgerreconcile --orders examples/orders.csv --payments examples/payments.csv --output example-report.json
```

Order `001` receives 700 of its expected 1000 cents and is `partial`; order `002`
receives 250 cents and is `paid`. A successful run exits 0 and writes one UTF-8
JSON line. Errors exit nonzero with a diagnostic on stderr and no traceback.
Quote file paths containing spaces, for example `--output "my report.json"`.

## Input rules

Orders have exactly `order_id,currency,amount`; payments have exactly
`payment_id,order_id,currency,amount`. Header order may vary. Both files require
headers, even when they contain no data. UTF-8 with or without a BOM and quoted
CSV fields (including embedded commas, quotes, CR and LF) are supported.
Malformed CSV, duplicate/missing/extra headers and incorrect row widths fail.

IDs are nonempty, case-sensitive strings, preserved exactly, including spaces
and leading zeroes. Currency must be three uppercase ASCII letters. Amounts
follow `-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?` with absolute value at most 1000000.00.
Orders must be positive; payments may be positive, zero or negative (refunds).
There is no floating-point money, exponent notation, whitespace, thousands
separator, excess precision or rounding. Negative zero is zero.

Order IDs must be unique, even for identical rows. Repeating a payment ID with
the same order, currency and integer-cent value is idempotent (`1.0` equals
`1.00`). A conflicting payment, unknown order, currency mismatch or invalid
field rejects the entire operation. At most 10000 data rows are allowed across
both files, counting repeated payment rows. Neither input is changed.

## Report and output safety

The report has exactly `schema: 1`, `orders: [...]` and `totals: [...]`. Each
order has `order_id`, `currency`, `expected_cents`, `received_cents`,
`balance_cents` and `status`. Each currency total has `currency`,
`expected_cents`, `received_cents` and `balance_cents`. Balance is expected minus
received. Status is `negative_net` for received below zero, `unpaid` for zero,
`partial` for a positive amount below expected, `paid` for equality, and
`overpaid` above expected. Orders without payments are included. Header-only
inputs produce empty arrays.

Orders sort by their original string IDs; totals sort by currency. Output uses
`json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(',', ':'))`
plus one final LF, encoded as UTF-8 without a BOM. Embedded newlines in strings
are escaped. Input row order and logical duplicate payments do not change bytes.

Validation and serialization finish before publication. A complete sibling
temporary file is flushed and atomically linked to the destination without
replacement, then removed. The output parent must already exist and its local
filesystem must support hard links; otherwise the operation fails safely.
Existing files, directories and symbolic links are never overwritten, including
when another process creates the destination during reconciliation.

## Tests

```sh
python -m unittest discover -s tests -p "test*.py"
```

Tests invoke the actual CLI in subprocesses and use temporary files inside this
repository. They cover exact money/refunds, deterministic bytes, ID semantics,
CSV validation, duplicate rules, row limits and output preservation.
