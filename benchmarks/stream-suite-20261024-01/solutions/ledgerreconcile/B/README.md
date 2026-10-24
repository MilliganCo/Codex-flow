# LedgerReconcile 1.0

An offline Python 3.12 CLI using only the standard library. No installation,
network, credentials, or dependencies are required. Run commands from this
repository directory.

Show all command-line options:

```console
python -m ledgerreconcile --help
```

Run the included tiny inputs, choosing an output path that does not already exist:

```console
python -m ledgerreconcile --orders examples/orders.csv --payments examples/payments.csv --output example-report.json
```

This produces two sorted orders: `001` is paid (USD 1000 expected and received
cents); `002` is partial (EUR 550 expected, 250 received, 300 balance cents).
The output is UTF-8 JSON with one final LF, canonical key ordering, and no timestamps.
Running the same command again refuses to overwrite the report. Choose another
new output filename for another run. Quote any paths containing spaces.

Run the complete standard-library test suite:

```console
python -m unittest discover -s tests -p "test*.py"
```

Orders require exactly `order_id,currency,amount` headers; payments require exactly
`payment_id,order_id,currency,amount`. Header order may vary. UTF-8 BOMs and quoted
fields containing commas, doubled quotes, or newlines are supported. Empty files,
invalid headers, malformed CSV, and blank records are errors; header-only inputs
are valid. At most 10,000 data records are accepted across both inputs, counting
duplicate payments before deduplication.

IDs are nonempty, case-sensitive strings, preserved exactly (including whitespace
and leading zeroes). Currencies are three uppercase ASCII letters. Amounts match
`-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?` and have absolute value at most `1000000.00`.
Order amounts must be positive; payments may include zero and refunds. All money
uses integer cents, with no floating point or rounding. Duplicate order IDs fail.
Repeated payment IDs count once only when order, currency, and integer cents agree;
`1`, `1.0`, and `1.00` are equivalent. Conflicts, unknown orders, or currency
mismatches fail the entire operation.

The report contains exactly `schema` (1), `orders` (an array), and `totals` (an array).
Each order has `order_id`, `currency`, `expected_cents`, `received_cents`,
`balance_cents`, and `status`. Each currency total has `currency`, `expected_cents`,
`received_cents`, and `balance_cents`. Balance is expected minus received. Orders
sort by original string ID; totals sort by currency. Status is `negative_net` for
negative received cents, `unpaid` for zero, `partial` for positive receipts below
the expected amount, `paid` for equality, and `overpaid` otherwise. Orders without
payments are included. Two header-only inputs produce empty arrays.

Success exits 0. Invalid arguments exit 2; validation or filesystem errors exit 1
with a controlled diagnostic on stderr. Both inputs remain unchanged. Validation
and serialization finish before publication; complete bytes are written to a
temporary sibling and atomically hard-linked to the new destination. This requires
a filesystem supporting hard links (including NTFS and common Linux filesystems).
Unsupported publication fails with a diagnostic, without a partial output. Existing
files, directories, and symlinks are never replaced, including concurrent creation
of the destination. The output parent directory must already exist.
