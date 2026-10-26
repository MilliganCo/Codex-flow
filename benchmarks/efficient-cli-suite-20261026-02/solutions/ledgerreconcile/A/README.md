# LedgerReconcile 1.0

An offline Python 3.12 CLI using only the standard library. Run commands from this
directory; no installation, network access, credentials, or dependencies are needed.

Show usage and flag descriptions:

```console
python -m ledgerreconcile --help
```

Run this smoke command with the included example inputs and a fresh output path:

```console
python -m ledgerreconcile --orders examples/orders.csv --payments examples/payments.csv --output report.json
```

The example produces a paid USD order (`001`, expected and received 1000 cents)
and an unpaid EUR order (`002`, expected 250 cents). Quote paths containing spaces:

```console
python -m ledgerreconcile --orders "input files/orders.csv" --payments "input files/payments.csv" --output "output files/report.json"
```

Run the tests:

```console
python -m unittest discover -s tests -p "test*.py"
```

## Input rules

Orders require exactly `order_id,currency,amount`; payments require exactly
`payment_id,order_id,currency,amount`. Header order may vary. Missing, extra or
duplicate headers, invalid UTF-8, malformed CSV, and rows with the wrong number
of fields fail. UTF-8 BOMs, quoted commas, escaped quotes and embedded newlines
are supported. Header-only files are valid; zero-byte files are invalid. At most
10,000 data rows are allowed across both files, including duplicate payment rows.

IDs are nonempty strings preserved exactly, including whitespace, Unicode and
leading zeroes. Order IDs must be unique. A repeated payment ID is accepted only
when its order ID, currency and integer-cent amount match its earlier payload;
`1`, `1.0` and `1.00` are equivalent amounts. Each logical payment counts once.
Every payment must reference an existing order with the same currency.

Currencies are exactly three uppercase ASCII letters. Amounts must match
`-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?`, with absolute value at most `1000000.00`.
No whitespace, plus signs, exponents, separators, nonfinite values, leading zeroes
or excess precision are accepted. Order amounts must be positive. Payment amounts
may be positive, zero or negative; refunds reduce the received total. All money
is calculated as integer cents without rounding or binary floating point.

## Report and failure behavior

The report contains exactly `schema` (1), `orders` (an array), and `totals` (an
array). Orders contain `order_id`, `currency`, `expected_cents`, `received_cents`,
`balance_cents`, and `status`. Currency totals contain `currency`, `expected_cents`,
`received_cents`, and `balance_cents`. Balance is expected minus received.

Statuses depend on net received cents: negative means `negative_net`, zero means
`unpaid`, below expected means `partial`, equal means `paid`, and above means
`overpaid`. Orders with no payments are included. Orders sort by the original
string ID; totals sort by currency. Two header-only files produce empty arrays.
Changing row order or adding logical duplicate payments (within the row limit)
does not change report bytes.

The file is UTF-8 without a BOM, with sorted JSON keys, compact separators,
unescaped Unicode and exactly one final LF. Embedded string newlines are escaped.
Serialization is exactly
`json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n'`.

Success exits 0. Invalid input or filesystem errors exit nonzero with a controlled
diagnostic on stderr. Both inputs are read without modification. All validation
and serialization finish before a report is staged beside the destination. The
complete, flushed file is published with an atomic, exclusive hard link; an
existing file, directory or symlink is never replaced, including a destination
created concurrently. The output's parent directory must already exist and its
filesystem must support hard links. If safe publication fails, the command fails
without publishing a partial report. Temporary files are removed when possible.
Choose a new output filename for each run.
