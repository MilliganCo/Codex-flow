# Changed-policy Tree confirmation

[Русский](README.ru.md) · [Results](results.json) · [Preregistration](preregistration.json) · [Runtime audit](../../docs/evidence/tree-case10-runtime-audit.json)

**Flow produced the higher-scoring artifact and completed within budget. The
preregistered speed comparison failed because Solo reached its deadline.**

| Measurement | Solo A | Flow B |
|---|---:|---:|
| Blind artifact score | 88/100 | 94/100 |
| Native run status | timed out | completed |
| Successful completion time | unknown | 1344.609 s |
| Observed stop time | 1499.875 s | 1344.609 s |
| Native request attempts | 25; 24 completed | 38; all completed |
| Independent native checks | 55 passed, 2 unexecuted | 57/57 passed |
| Headless evaluator | 25/25 | 25/25 |

The time limit remained 1500 seconds and the request limit 80 per branch. The
observed Solo stop time is censored and is **not a completion time**. The A/B
successful-completion ratio remains null. No percentage speedup is inferred.
Both artifacts met the original score>=80 plus five critical-gate acceptance
rule; that does not mean every task requirement passed. Solo has no README and
did not exit on the literal Ctrl+C byte in the fixed no-repair SDK/ConPTY context.
Its passing authored native fixture resets control handling, so it cannot replace
the independent failure. q/Esc, physical resizes and the 3D round trip passed.

## Quality and actual evidence

The fresh reviewer sealed all 26 criterion scores before identity disclosure.
Flow gained on reliability, tests, maintainability and README. Solo had the better
aesthetic score, 10/12 versus 8/12, and higher 2D/3D category scores. Flow's screen
depth interpolation is approximate; a higher total score is not a claim of better
appearance in every category. [The full blind review](evidence/blind-review.md)
retains these tradeoffs.

Flow's geometry observations were 138/138. Solo had 84 passing observations and
38 retained auxiliary nonfinite-input failures; all substantive finite-model,
rank, W-span, rotation and sequential-projection checks passed. Counts differ
because production APIs expose different additional guards; they are not
normalized quality scores. Flow's private production projection was observed
read-only with a temporary profiler inside the SDK, with the previous profiler
restored. Application source, globals, input and control handlers were not patched.

All 72 selected source files are byte-identical under [solutions](solutions).
There were no generation retries, application repairs or scoring changes.
The six SDK evaluations/checks retain the failed native Solo receipt. Reports
are explicit path-redacted derivatives with raw/published hashes; source, checker
and ASCII bytes are preserved. Two root-owned frozen execution sidecars are
outside the judge's seal, as explicitly marked in [publication provenance](results-publication.json).
Raw VT streams, native databases, credentials and private maps remain local.

## What changed and what was observed

The exact 16 runtime files from source commit
`8d3913cbee77cc91c482a13fed12c031170d4594` are in [frozen-runtime](frozen-runtime).
Only the CLI/native coordination policy changed from the original three-task
runtime. The provider, transport, input bytes, disabled suffix guidance, sandbox,
deadline and request-budget engine remained unchanged.

The first reviewer used Sol high and one actual request; the chief used Sol
XHigh. Two successful budget calls were observed, versus six in the preceding
Tree Flow run. Total Flow requests changed historically from 40 to 38, while
chief XHigh requests increased from 35 to 37. These historical differences do
not prove time or quota savings. Complete Flow usage is 2,382,661 input and
48,580 output tokens. Solo's complete usage is unknown; its 24 completed requests
provide only a lower bound of 1,132,428 input and 43,248 output tokens.

The final Solo request was HTTP200 but was interrupted during its body read by
`control/deadline_exhausted`. It did not reach a validated model terminal and its
usage remains null. This is distinct from `upstream_read_error`. One free Mercury
decision succeeded for Flow; Harness online probes remained zero. No paid API
was connected. The [native prerequisite](prerequisite-result.json) passed 21/21
with six requests and earns no benchmark credit.

## Run the actual Flow demonstration

```powershell
Push-Location benchmarks/tree-confirmation-20261024-10/solutions/B
python -m ascii_tree view --seed 42 --mode 4d
Pop-Location
```

Keys `1`, `2`, `3` select 2D/3D/4D; `[` and `]` rotate in XW; `q` quits.
[Actual 2D](evidence/frozen-23/2d-42.txt), [3D](evidence/frozen-23/3d-42.txt) and
[4D](evidence/frozen-23/4d-42.txt) exports and 108 recorded ASCII frames are retained.
The demonstration needs Python and no model account or package installation.
Native acceptance was measured on Windows SDK/ConPTY; visible GUI/font appearance
and these frozen applications' Linux interaction were not assessed.

The original [negative denominator-three cohort](../stream-suite-20261024-01/README.md)
remains failed and is not replaced or pooled. This single confirmation also
failed its strict admission rule. Shared native state and degraded physical read
isolation remain explicit limits. [Rollback](../../docs/rollback.md) preserves
current edits and host settings.
