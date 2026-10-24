# Terminal-aware runtime: fixed three-task series

[Русский](README.ru.md) · [Machine-readable result](series-result.json) · [Frozen protocol](frozen-protocol.json)

**All six branches completed and were independently accepted. The preregistered
speed-without-quality-loss criterion failed.** No failed comparison was removed.

| Task | Solo score | Flow score | Solo seconds | Flow seconds | Native requests A/B |
|---|---:|---:|---:|---:|---:|
| ASCII Tree Explorer | 98 | 96 | 1322.578 | 1277.359 | 30 / 40 |
| LedgerReconcile | 100 | 100 | 573.031 | 630.516 | 13 / 19 |
| SafeZip | 100 | 100 | 821.328 | 1090.875 | 17 / 28 |

Flow used 3.419% less elapsed time on Tree, 10.032% more on Ledger and 32.818%
more on SafeZip. The geometric mean A/B time ratio is **0.891478**; the
preregistered admission threshold was at least 1.10, with Flow quality at least
Solo quality on every task. Tree quality also failed that condition. These data
do not prove acceleration, quota savings or a causal contribution from a helper.

## Fixed execution and assessment

The runtime is source commit `6c30bbe69a76c846257196cedd378c8a1c5d2eff`; its exact
16 files are retained in [frozen-runtime](frozen-runtime). Each pair ran fresh A/B
in parallel, sequentially across tasks, with Sol 6.1 XHigh roots and the same
1500-second/80-native-request limits. One free-only Mercury decision was allowed
per Flow branch. All three succeeded at reported cost zero. The Harness guard
deferred optimization: zero upstream or inspired online probes. No paid API,
transport retry, source repair or benchmark retry was used.

Every one of the **147 native requests** reached validated `response.completed`,
with no read failure. This verifies the new reader in these runs; the separate
[old/new real loopback proof](../../docs/evidence/terminal-stream-loopback.json)
establishes the constructed gateway defect. The exact exception in historical
case08 was not retained and cannot be reconstructed from that proof.

Tree kept the literal task, unchanged evaluator/rubric, 26 criteria, five
critical gates and real 57-check ConPTY protocol. Both passed headless 25/25 and
native 57/57. A fresh blind reviewer sealed 98/96 before identity disclosure.
One point of the difference is subjective aesthetics; one concerns safe
projection. Flow retained 18 auxiliary failures for direct NaN/Infinity point
inputs, while its production-model geometry, rotation and sequential projection
passed. Its geometry record is **61/79**, versus Solo **79/79**; neither record
was repaired or normalized to all-pass.

The two new tasks froze public briefs, 20×5 rubrics and hidden deterministic
fixtures before generation. Acceptance required 100/100 and unchanged source.
Both Ledger implementations passed strict CSV, integer cents, duplicate/conflict,
malformed-input, atomic output, authored-test and documented-smoke criteria.
Both SafeZip implementations passed traversal/collision/type/CRC/quota and atomic
extraction criteria. Applications ran only in the existing official Windows SDK
sandbox, without network. Grading occurred between pairs.

## Unchanged runnable demonstrations

All **130 selected submitted files** are retained byte-identically under
[solutions](solutions), with source hashes in each publication manifest.

```powershell
Push-Location benchmarks/stream-suite-20261024-01/solutions/tree/B
python -m ascii_tree view --seed 42 --mode 4d
Pop-Location
```

The original [Ledger README](solutions/ledgerreconcile/B/README.md) and
[SafeZip README](solutions/safezip/B/README.md) provide included benign input
examples and actual tested commands. These frozen submissions are evidence;
later runtime changes do not repair or regrade them.

Tree has [108 actual ASCII exports](tree-evidence-publication.json), independent
[blind review](evidence/tree/blind-review.md), [geometry](evidence/tree/geometry-18.json)
and [native interaction](evidence/tree/interactive-18/report.json) records.
Ledger/SafeZip evidence is under [evidence](evidence), with portable checker
copies under [verification](verification). Source/ASCII/checker copies retain
bytes; path-redacted reports explicitly map original and published hashes.
Raw VT streams, native state, credentials and private maps stay local.

## Limits and follow-up

One pair per task does not establish statistical or universal superiority.
Native authentication/rollout state remains shared and physical current-peer
read isolation is degraded. Read-only helper ownership/depth are instructions.
CPU/RSS monitoring covers only the declared root CLI PID, not descendants or
remote inference. Unknown monetary cost/quota deltas remain null.

This negative cohort remains in full. A changed-policy confirmation, if run, is
a separately preregistered experiment and cannot replace these outcomes.
