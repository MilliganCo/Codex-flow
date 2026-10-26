# LedgerReconcile 1.0

An offline Python 3.12 CLI using only the standard library. Run commands from this
directory; no installation, network access, dependencies, or API keys are needed.

Show the available flags:

```text
python -m ledgerreconcile --help
```

Run the included tiny examples (choose a fresh output filename on each run):

```text
python -m ledgerreconcile --orders examples/orders.csv --payments examples/payments.csv --output example-report.json
```

For your own files, including paths with spaces:

```text
python -m ledgerreconcile --orders "my data/orders.csv" --payments "my data/payments.csv" --output "my data/new report.json"
```

The orders header must contain exactly `order_id,currency,amount`; payments must
contain exactly `payment_id,order_id,currency,amount`. Header order may vary.
Inputs accept UTF-8 with or without a BOM, quoted commas, escaped double quotes,
and quoted newlines. Missing, extra, or duplicate headers, malformed CSV, rows
with the wrong number of fields, and invalid UTF-8 are rejected. Header-only
inputs are valid; zero-byte files are not. Both inputs together may contain at
most 10,000 data records, counting repeated payment records.

IDs are nonempty strings preserved exactly, including spaces and leading zeros.
Order IDs must be unique. Repeated payment IDs count once only if their order ID,
currency, and integer-cent amount match; `1.0` and `1.00` match. Conflicts, unknown
orders, and currency mismatches are errors. Currency must be exactly three
uppercase ASCII letters.

Amounts must match `-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?`, with absolute value at most
`1000000.00`. Orders must be strictly positive. Payments may include zero and
negative refunds. Money uses integer cents throughout, without floating-point
conversion or rounding. Exponents, plus signs, leading zeros, thousands separators,
NaN/Inf, whitespace, and excess decimal places are rejected.

The report contains exactly `schema` (1), `orders` (an array), and `totals` (an
array). Each order contains `order_id`, `currency`, `expected_cents`,
`received_cents`, `balance_cents`, and `status`. Each currency total contains
`currency`, `expected_cents`, `received_cents`, and `balance_cents`. Balance is
expected minus received. Status is `negative_net` for negative received amounts,
`unpaid` for zero, `partial` below the expected amount, `paid` for equality, and
`overpaid` above it. Orders without payments are included. Orders sort by their
original string IDs; totals sort by currency. Empty inputs produce two empty arrays.

Output is canonical UTF-8 JSON, equivalent to
`json.dumps(report,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n'`.
It has one final LF, with newlines inside strings escaped. Input record order and
logical duplicate payments do not change report bytes while within the row limit.

Success exits 0. Errors exit nonzero with a diagnostic on stderr and no traceback.
Inputs are opened read-only. A complete report is written and synced to a temporary
file in the destination directory, then atomically published using a hard link
that refuses to replace an existing path, including a directory or symbolic link.
The destination's parent directory must exist and its filesystem must support
hard links (for example, NTFS or typical Linux filesystems). A publication failure
leaves the destination absent or preserves the path already there. There is no
unsafe overwrite fallback. Temporary files are removed on normal success/failure;
forced process termination or a cleanup permission failure can leave a temporary file.

Run the standard-library test suite:

```text
python -m unittest discover -s tests -p "test*.py"
```
