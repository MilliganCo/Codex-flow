# Case08: observed results and boundaries

[English](README.md) В· [Р СѓСЃСЃРєРёР№](README.ru.md)

[Metrics](results.json) В· [Hashes](evidence-hashes.json) В· [Source manifest](source-manifest.json) В· [Protocol](../protocol/)

Original task/rubric, Sol 6.1 XHigh, 1500 seconds and 80 native requests per arm. Scores are preserved without normalization; artifact acceptance never changes execution status.

| Arm | Score /100 | Accepted | Total seconds | Original status | Native requests |
|---|---:|---|---:|---|---:|
| A | 97 | True | 1120.781 | `completed_unverified` | 34 |
| B | 97 | True | 1094.797 | `failed` | 28 |

| Arm | MCP configured | Successful status calls | Use evidence |
|---|---|---:|---|
| A | False | n/a | not_configured |
| B | True | 4 | observed |

Budget suffix injection is off for both arms. B uses native MCP flow_budget.status. Configuration, successful calls and channel health are separate. Audit counts identify neither root/worker nor causal benefit; invalid audit data cannot establish use. Absent A counters stay null.

The HarnessВІ-inspired guard defers calibration: zero online probes and no demonstrated active optimizer benefit. Complete usage requires completed requests across all phases; known lower bounds remain separate. Unmeasured money and quota stay unknown.

Native pass requires exactly 57 passing checks and complete_protocol=true. Original failures, partial evidence and supplemental not_run are preserved. MCP-audit phases and passive request snapshots are separate. RSS/CPU covers sampled root PIDs only; open/read timings include upstream waiting/generation, and overlapping requests are not additive task latency.

Case07 stopped before grading and has no scores. Cases are not pooled; speedup and causal module contribution are unestablished. ZIPs stay local. The common task brief is in the protocol; native payloads, auth/state, databases, journals, stderr and personal paths remain unpublished.

## What this result establishes

Both artifacts received 97/100: each lost three aesthetic points. All 26 criteria were assessed; both passed the five critical gates, the frozen
headless 25/25 subset, and all 57 native console checks. Supplied test suites passed 45/31 tests for A/B. Required
README/launch instructions and real Ctrl+C restoration are present in both; the
old eight-point documentation/control loss was not reproduced.

B is **not a successful timing completion**. Request 28 received HTTP 200 headers
but body reading did not return normally, after 56.594seconds. Native execution
then failed with 405seconds and 52 request attempts unused. The exact exception
class was not retained. A size-limit or deadline cause is not supported by the
record. B's complete aggregate usage remains null;27 completed requests provide
only a known lower bound. Neither its shorter stopped duration nor request count
establishes acceleration or subscription savings.

Flow preparation took 1.062seconds; its one native medium worker and one validated
free-only Mercury decision were observed. Budget MCP had 4/4 successful audited
calls, with no unavailable result; audit counts do not identify callers. Enabled
Harness-inspired calibration remained deferred with zero online probes. The
[metadata analysis](evidence/orchestration-analysis.json) preserves request unions,
profile overlap, HMAC repeat counts and unknowns without classifying all late
verification as wasted work.

## Mathematical and verification boundaries

Canonical basis rotations at 0/37/90 degrees, norm/inverse/determinant/orthogonality,
actual skeleton/full-model XYZ rank 3 and variable W for seeds 42/137, and tested
sequential 4D perspective all passed. Raw geometry JSON remains `fail` because two
extra explicit NaN-input probes fail per solution. B's private nested final screen
coordinate API could not be called directly; its source formula and native oracle
were assessed separately. These auxiliary limits are disclosed, not new task gates.

The first geometry 15 checker failed in final source-hash bookkeeping: a manifest
name had been rebound to projected coordinates. That immutable failed attempt and
the separately approved three-name correction remain in evidence. Mathematics,
thresholds and app source were unchanged. A separate audit corrects an overstated
cleanup flag in the headless execution receipts; descendant cleanup was not
independently proven merely by normal outer-process exit.

## Run the unchanged demonstrations

From the repository root, choose a snapshot and start its viewer:

```powershell
Set-Location benchmarks/case08/solutions/A
python -m ascii_tree view --seed 42 --mode 4d
```

For B, use `solutions/B` instead. Python 3.12+, no external runtime dependencies.
Press 1/2/3 for modes, [/] for XW, arrows for camera, Space for animation, E for
export, Q/Esc/Ctrl+C to exit. Headless example in either snapshot:

```powershell
python -m ascii_tree render --seed 42 --mode 4d --angle4 37 --width 100 --height 40 --output tree.txt
```

[Actual six exports](comparison.png) are typeset from the frozen evaluator's files;
they are not interactive screenshots. Their [provenance](comparison-provenance.json)
records original SHA256s. Windows native behavior was independently verified;
these new originals have not been independently executed on Linux.

All 70 evaluated files remain unchanged locally. [67 source/artifact files](source-publication.json)
are published verbatim; only three noncode console logs containing personal paths
are excluded and remain local. Original self-reports are not independent evidence.
Frozen runtime bytes match explicit curated commit
`f52b7e45f7beddf0d3ef9a7c64bb66da91f51d18` after LF normalization. Later protected
server snapshots and typed transport diagnostics are separately verified hardening,
not silently included in this experiment's timings. [Rollback](../../docs/rollback.md)
preserves the current checkout and artifacts.
