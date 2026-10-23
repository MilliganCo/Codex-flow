# Defer proxy calibration and deliver acceptance artifacts earlier

Status: implemented before independent case06 generation. Runtime change: `aa43370`.

Case05's solo score97 and Flow score89 differed only in actual Windows Ctrl+C
(three points) and missing README setup/commands/4D explanation (five points).
The other22 rubric criteria were equal, including mathematical4D gates.

Flow spent125.328 seconds on two sequential XHigh planning probes before its main
turn: eight requests,149255 input tokens and1894 output tokens. Both plans scored
5/5 under the proxy. This did not establish an application-quality improvement.
Mercury took1.281 seconds. The main Flow turn received1373.797 seconds before
its outer deadline; solo completed in1463.437 seconds.

The used native helper was not uniformly wasteful: the run credited it with two
concrete fixes. Its measured request durations mostly overlapped root inference;
they cannot be added as serial orchestration latency. Exact helper wait time is
unknown. Sanitized events do not establish duplicated shell/test work.

## Decision

Remove automatic planning calibration from both normal execution and benchmarks.
An enabled Harness2-inspired guard now reports `deferred`, zero probes and no
adoption. It does not load old active overlays. Explicit plan diagnostics remain
available in the library but always use `adopt=False`. Generic measured proposal
comparison and hash-checked rollback remain compatible; neither a faster plan nor
an equal coverage score demonstrates better application quality.

Keep one application writer. Request one bounded readonly helper evidence task and
use its results once while root implementation proceeds. Request an early runnable
slice, a documented launch command, finite smoke checks, and current required
artifacts. Distinguish simulated exceptions from actual platform interactions.
The final20% verification/documentation reserve is instructional, not an enforced
phase scheduler. Native timeout and request limits remain hard outer controls.

Add optional `--groups AB`; retain defaultABCD. Case06 is one preregistered fresh
A/B repeat with unchanged literal task, evaluator, rubric, requested SolXHigh and
1500-second/80-request limits. A's developer instructions remain byte-identical.
No application code, solution-specific fix or judge result is given to either
generator. The new B guard is explicitly not active Harness2 optimization.

## Evidence and limits

Focused wiring checks, stale-overlay/diagnostic regressions and the combined196
tests passed: all196 in WSL;178 plus18 symlink skips locally on Windows. Ruff and
mypy passed. Existing payload, subscription transport and sandbox policies were
preserved. This proves local wiring and contracts; only the new independent
experiment can assess resulting artifact quality. One repeat cannot establish
general speedup or causal component contributions.

Rollback: restore the pre-change code via a reviewed Git revert; preserve all
experiment artifacts and proposal history. The external pre-change bundle records
source commit51fd9bb6f1b2ac85552cfc57092cec32f51cc6ba. No global installation or
protected Harness2 runtime was changed.
