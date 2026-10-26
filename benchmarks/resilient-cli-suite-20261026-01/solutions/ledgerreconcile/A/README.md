# LedgerReconcile v1.0

An offline Python 3.12 CLI using only the standard library. Run commands from this
directory; no installation, network access, or API keys are needed.

View all flags:

```text
python -m ledgerreconcile --help
```

Run the included examples with a fresh output path:

```text
python -m ledgerreconcile --orders examples/orders.csv --payments examples/payments.csv --output report.json
```

The example pays order `001` in full and partially pays order `002`. Use a new
output name on subsequent runs. Paths containing spaces must be quoted:

```text
python -m ledgerreconcile --orders "my inputs/orders.csv" --payments "my inputs/payments.csv" --output "my reports/new report.json"
```

Run the standard-library tests:

```text
python -m unittest discover -s tests -p "test*.py"
```

## Input rules

Orders require exactly `order_id,currency,amount` headers; payments require exactly
`payment_id,order_id,currency,amount`. Header order may vary. Files accept UTF-8,
an optional UTF-8 BOM, and quoted fields containing commas, doubled quotes, and
newlines. Missing, extra, or duplicate headers, invalid quoting, blank data rows,
and incorrect field counts are errors. Header-only files are valid; files without
headers are invalid. At most 10,000 data rows are allowed across both files,
including repeated payments.

IDs are nonempty strings preserved exactly: `001`, `1`, `A`, `a`, and ` A ` are
different IDs. Order IDs must be unique, even for identical repeated rows.
Payment IDs may repeat only with the same order ID, currency, and integer cents;
`1`, `1.0`, and `1.00` are equivalent amounts. Each logical payment counts once.
All payments must reference known orders and match their currencies.

Currency must be exactly three uppercase ASCII letters. Amounts follow
`-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?` with absolute value at most `1000000.00`.
Orders must be strictly positive. Payments allow positive values, zero, and
negative refunds. Exponents, leading plus signs, leading zeros, whitespace,
thousands separators, NaN/Inf, and excess decimal places are rejected. Money is
calculated with integer cents; no binary floating point or rounding is used.

## Output and failure behavior

The JSON contains exactly `schema` (integer `1`), `orders` (array), and `totals`
(array). Orders contain exactly `order_id`, `currency`, `expected_cents`,
`received_cents`, `balance_cents`, and `status`. Currency totals contain exactly
`currency`, `expected_cents`, `received_cents`, and `balance_cents`.

Balance is expected minus net received. Status is `negative_net` for negative
received, `unpaid` for zero, `partial` below expected, `paid` at equality, and
`overpaid` above expected. Every order appears, including those without payments.
Orders sort by original string ID; totals sort by currency. Empty inputs with
valid headers produce empty arrays.

Output bytes are UTF-8 with Unicode preserved, sorted JSON keys, compact
separators, and exactly one final LF. Newlines in IDs are escaped. Reordering
input rows or adding equivalent duplicate payments does not change report bytes
within the row limit.

Success exits `0`. Invalid input, inaccessible paths, or publication failures exit
nonzero with a diagnostic on stderr and no traceback. Both inputs are opened
read-only. The output parent directory must already exist. Complete output is
staged in that directory, flushed, and atomically published using a hard link
that cannot replace an existing file, directory, or symlink, even if another
process creates the destination during publication. The destination appears only
with a complete report; failures leave existing paths intact. The filesystem
must support hard links; otherwise publication fails safely. Temporary files are
removed after normal success or failure (cleanup is best effort on OS errors).
