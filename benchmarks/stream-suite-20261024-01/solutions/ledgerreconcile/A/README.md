# LedgerReconcile v1.0

An offline Python 3.12 CLI using only the standard library. Run commands from
this directory; no installation, network access, or credentials are needed.

## Run

The included inputs contain a paid USD order and an EUR order with a refund:

```sh
python -m ledgerreconcile --orders examples/orders.csv --payments examples/payments.csv --output report.json
```

Choose a fresh output path for each run. Quote paths containing spaces.
The output's parent directory must already exist.

```sh
python -m ledgerreconcile --help
```

## Input rules

Orders have exactly `order_id,currency,amount` headers; payments have exactly
`payment_id,order_id,currency,amount`. Header order may vary. Inputs accept UTF-8
with or without a BOM, CR/LF/CRLF record endings, and quoted fields containing
commas, doubled quotes, and embedded newlines. Headers and values are never
trimmed. Missing, repeated, or extra headers, malformed quoting, and incorrect
field counts fail validation. Header-only files are valid; zero-byte files are not.

IDs are nonempty, case-sensitive strings: `001`, `1`, and ` 1` are different.
Currency must be three uppercase ASCII letters. Amounts must match
`-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?`, with absolute value at most `1000000.00`.
Orders must be positive; payments can be positive, zero, or negative (refunds).
All arithmetic uses integer cents. Exponents, signs prefixed with `+`, whitespace,
thousands separators, NaN/Inf, and more than two decimal places are rejected.

Every order ID must be unique. Repeated payment IDs count once if their order ID,
currency, and integer cents agree (`1.0` and `1.00` are equivalent); conflicts fail.
Every payment must reference an existing order with the same currency. The two
inputs together may contain at most 10,000 data rows, including duplicate payments.

## Report and failure behavior

The JSON has exactly `schema` (1), `orders` (an array), and `totals` (an array).
Each order contains `order_id`, `currency`, `expected_cents`, `received_cents`,
`balance_cents`, and `status`. Each currency total contains `currency`,
`expected_cents`, `received_cents`, and `balance_cents`. Balances are expected
minus received, and orders without payments are included. Orders sort by their
original string IDs; totals sort by currency.

Status is `negative_net` for a negative receipt, `unpaid` for zero, `partial` for a
positive receipt below the expected amount, `paid` for equality, and `overpaid`
above it. Empty ledgers produce empty order and total arrays.

Output is exactly UTF-8 encoded
`json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n'`.
There is one final LF and no other structural line break. Row permutations and
logical duplicate payments leave output bytes unchanged.

Success exits 0; errors exit nonzero with a diagnostic on stderr and no traceback.
Inputs are only opened for reading. Validation finishes before output is written.
A temporary file in the output directory is fully written, flushed, and synced,
then atomically published with a no-overwrite hard link. Existing files,
directories, and symlinks are preserved, including a destination created during
publication. A filesystem that does not support hard links causes a controlled
failure without a report; there is no weaker publication fallback.

## Tests

```sh
python -m unittest discover -s tests -p "test*.py"
```

Tests use standard-library `unittest`, isolated temporary directories under
`.tmp/`, and finite local CLI subprocesses. They cover exact cents, refund
statuses, totals, IDs, deterministic bytes, duplicate rules, CSV/UTF-8 validation,
row limits, output preservation, and publication failures and races.
