# Verification

Verified locally with Python 3.12.10 on Windows. The 35 standard-library unittest
tests passed. The actual module's `--help` and the README example command also
passed, with only the example's output path changed to a fresh owned path.

Run the checks again from this directory:

```console
python -m unittest discover -s tests -p "test*.py"
```

Acceptance coverage in `tests/test_ledgerreconcile.py`:

1. CLI/schema, exact cents, signed refunds/statuses, currency totals, and original
   string IDs/sorting: exact expected report comparisons and real CLI invocations.
2. Row-order determinism, logical payment idempotence, conflicting payments,
   duplicate orders, and unknown orders: byte comparisons and controlled rejection.
3. Currency mismatch, money grammar/bounds, headers/malformed CSV, BOM/quoted UTF-8,
   and empty/header-only semantics: valid and invalid input cases on disk.
4. Atomic failure, existing output preservation, help/space paths/controlled exits,
   authored tests, and working README smoke: real filesystem and CLI checks.

Publication checks use actual Windows hard links, including two real CLI processes
competing for one destination. Additional fault-injection tests simulate fsync/link
failure and destination creation immediately before linking; these simulations do
not claim to reproduce every storage-device failure. Existing files, empty and
populated directories, both input paths, and inputs after rejection are preserved.

Saved evidence lives in `verification/`: `unittest.txt` contains the final test run,
`example-report.json` is the actual README smoke output, `smoke.json` records the
finite command checks, and `source-sha256.json` records source hashes checked before
and after the final run. The CLI never rewrites an existing output.

Not run: another operating system, a filesystem without hard-link support, or the
independent evaluator. Unsupported hard-link publication returns a controlled error
and does not fall back to exposing partial bytes. The independent evaluator's score
is not asserted here.
