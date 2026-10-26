# LedgerReconcile v1.0 — common A/B task

Build a complete offline Python 3.12 standard-library CLI, source, tests and README.
No network, external dependencies, API keys, paid APIs or other workspace access.

```
python -m ledgerreconcile --help
python -m ledgerreconcile --orders orders.csv --payments payments.csv --output report.json
```

orders.csv has exactly order_id,currency,amount headers; payments.csv has exactly
payment_id,order_id,currency,amount. Header order may vary; missing/extra/duplicate
headers or malformed CSV are errors. Accept UTF-8 and UTF-8 BOM, ordinary quoted
CSV including commas, quotes and newlines inside fields. IDs are nonempty strings
preserved without trimming, case conversion or numeric conversion: 001 and 1 differ.
Currency is exactly three uppercase ASCII letters. Amount grammar is
`-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?`, absolute value <=1000000.00. No exponent,
NaN/Inf, thousands separators, plus sign or rounding excess precision. Orders are
strictly positive; payments may be positive, zero or negative. Calculate exact
integer cents, never binary floating-point money.

Order IDs are unique, including identical duplicate rows (error). Payment IDs are
idempotent for the same logical (order_id,currency,integer cents) payload, so 1.0
and 1.00 are equivalent. A conflicting duplicate payment is an error. Unknown
orders, mismatching currencies, empty IDs or invalid fields fail the whole operation.
There are at most 10000 data rows across both inputs; exceeding this bound is an error.
Header-only inputs are valid; a missing header/zero-byte file is invalid.

Output schema is exactly:
{"schema":1,"orders":[{"order_id":"001","currency":"USD","expected_cents":100,
"received_cents":100,"balance_cents":0,"status":"paid"}],
"totals":[{"currency":"USD","expected_cents":100,"received_cents":100,"balance_cents":0}]}

`totals` is an ARRAY, not a currency-keyed object. Each currency has exactly the four
shown fields. Each order has exactly the six shown fields. Balance=expected-received.
Status is negative_net for received<0, unpaid for received=0, partial for
0<received<expected, paid for equality, otherwise overpaid. Include orders with no
payments. Sort orders by original string ID and totals by currency. Empty inputs
produce orders:[] and totals:[]. Do not include timestamps, random data or extra fields.

Write exact UTF-8 bytes equivalent to
`json.dumps(report,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n'`.
The final LF is the only structural line break (newlines inside JSON strings are escaped).
Input row permutations and added logical duplicate payments leave the report bytes
unchanged. Success exits 0; errors exit nonzero with controlled diagnostics, no raw
traceback. A new output appears only on complete success; never expose a partial
report or overwrite any existing output file/directory. Preserve both input files.

Include >=5 runnable standard-library unittest tests in tests/, covering valid,
money, duplicate and rejection/atomic behavior. README must give the actual command:
`python -m unittest discover -s tests -p "test*.py"`.
Include tiny valid example inputs and a real single-line fenced README smoke command
using `python -m ledgerreconcile --orders <included-relative-file> --payments
<included-relative-file> --output <new-file>` (all on one line). Document --help.
Do not use shell operators, pipelines or a separate installer in that smoke command.
The independent evaluator reruns those actual module/flags/example inputs, changing
only the output path to an owned fresh file. It checks behavior, not README wordcount.

Acceptance uses 20 independently assessed criteria, each 5 points: basic CLI/schema;
exact cents; signed/refund semantics; currency totals; string IDs/sorting; row-order
determinism; payment idempotence; conflicting payment rejection; duplicate order
rejection; unknown order rejection; currency mismatch; invalid money/bounds; headers
and malformed CSV; BOM/quotes/UTF-8; empty/header-only semantics; atomic failure;
existing output preservation; help/space paths/controlled exits; >=5 authored tests;
working README smoke. Accepted requires all 20 pass (100/100) and unchanged sources.
Partial results remain partial. Implement independently in your assigned workspace.
