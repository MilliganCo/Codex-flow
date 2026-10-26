# LedgerReconcile 1.0

Reconcile orders and payments offline with Python 3.12 and the standard library.
Run commands from this directory. No installation or network access is needed.

Show the CLI options:

```text
python -m ledgerreconcile --help
```

Run the included tiny example (choose a new output name each time):

```text
python -m ledgerreconcile --orders examples/orders.csv --payments examples/payments.csv --output example-report.json
```

The example produces paid orders `001` (1000 USD cents) and `002` (250 EUR
cents, including a refund). Use your own files with the same flags. Quote paths
containing spaces. Success exits 0 and is silent. Invalid input or output errors
exit nonzero with a diagnostic on stderr and no traceback.

Orders require exactly `order_id,currency,amount`; payments require exactly
`payment_id,order_id,currency,amount`. Header order may vary. UTF-8, an optional
initial UTF-8 BOM, and CSV quoting with commas, doubled quotes and embedded
newlines are supported. Missing, extra or duplicate headers, malformed records,
blank records and invalid UTF-8 are rejected. Header-only files are valid;
zero-byte files have no header and are invalid.

IDs are nonempty strings preserved exactly, including spaces, case and leading
zeros. Currency is exactly three uppercase ASCII letters. Amounts match
`-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?` and have absolute value at most `1000000.00`.
Orders must be positive; payments may be positive, zero or negative. All money
is computed as integer cents, without rounding or binary floating point.

Order IDs must be unique. Repeated payment IDs are counted once when their
order ID, currency and integer cents match (`1.0` and `1.00` are equivalent).
Conflicts, unknown orders and currency mismatches reject the entire operation.
At most 10,000 data records are allowed across both files; duplicate payments
also count toward this limit. Embedded newlines do not add records.

The report has exactly `schema`, `orders` and `totals`. Schema is `1`; orders
are sorted by their original string IDs, and totals is an array sorted by
currency. Every order includes `order_id`, `currency`, `expected_cents`,
`received_cents`, `balance_cents` and `status`. Every currency total includes
`currency`, `expected_cents`, `received_cents` and `balance_cents`.
Balance is expected minus received. Status is `negative_net` for a negative
received amount, `unpaid` for zero, `partial` for a positive amount below
expected, `paid` for equality and `overpaid` for an excess. Orders with no
payments are included. Two header-only files yield empty orders and totals.

Output is compact UTF-8 JSON with sorted object keys and exactly one final LF.
Non-ASCII text is preserved and embedded newlines are escaped. Reordering rows
or adding equivalent payment duplicates leaves the report bytes unchanged
within the row limit.

Both inputs are opened read-only. The complete report is written and flushed
to a sibling temporary file, then atomically published with a no-overwrite hard
link. Existing files, directories and symlinks are never replaced, even if
created concurrently. Input errors leave no report; write/publication failures
leave no partial report. The output parent must already exist on a filesystem
supporting hard links (such as NTFS or ext4); otherwise the command fails safely.

Run the standard-library test suite:

```text
python -m unittest discover -s tests -p "test*.py"
```
