# Acceptance status — 2026-10-26

This is an evidence boundary, not a claim that the entire requested architecture has passed. Status values are `pass`, `degraded`, `deferred`, `blocked` and `notimplemented`. Independent integration proofs, packaged-demo verification and frozen benchmarks are separate records; later success does not rewrite an earlier run.

The latest [CLI cohort](../benchmarks/efficient-cli-suite-20261026-02/README.md)
completed both fixed tasks in both arms with four independent 100/100 grades.
Flow took longer on both: 719.281 vs 599.609 seconds, and 1207.984 vs 925.687
seconds. Acceleration without quality loss was not achieved. The experimental
test-proposal policy is retained only as a frozen candidate; current instructions
restore the balanced context-only reviewer. Earlier failures and incomplete rows
remain in their original cohorts. The CI links below describe named historical
commits; current publication requires its own exact-commit Actions result.

| Requirement | Status | Verified scope / remaining limit |
|---|---|---|
| Existing Codex Flow compatibility | pass | Legacy skill/helper contracts retained; offline regression checks passed |
| Mercury free-only integration | pass | Real typed smoke with validated model/build/provider and reported cost 0; disabled by default; no routing-accuracy claim |
| Harness²-inspired optimization | deferred | Enabled guard, zero automatic online probes, no stale overlay; explicit plan diagnostics cannot adopt; optimizer benefit unproven |
| Upstream Harness² executor | blocked | Unsafe upstream execution path excluded; not silently substituted or claimed active |
| Native root/helper capability | pass | Separate bounded proofs plus case05: B/C/D used 1/2/1 direct children; scoped journal audit observed depth one |
| Kernel tool boundary | pass | Zero-model-call synthetic check: normal read/write passed, private sentinel/SQLite operations raised `PermissionError`, host fixture remained usable |
| Strict independent native profiles/state | blocked | Auth/rollout container shared; project SQLite can import historical metadata; separate paths do not establish isolation |
| Hard helper read-only/depth isolation | degraded | Custom roles inherit parent permissions; ownership/depth are instructions; worker policy refusal is not an observed OS attempt |
| Configured multi-agent A/B | pass | Case05 observed real helpers/Mercury/inspired probes; independently accepted artifact scores A/B/C/D=97/89/89/94 |
| Updated orchestration A/B repeat | pass | Case06: solo 97/Flow 98, both completed, headless 25/25 and native 57/57; Flow one verified helper/one Mercury call/deferred guard with zero online probes |
| Acceleration without quality loss | degraded | Final CLI cohort: all four artifacts 100/100 and all generators complete, but Flow slower on each task; fixed per-task ratio criterion fails |
| Optional bounded HTTP recovery | pass | Nine synthetic cases and 24-check/eight-request real native prerequisite; default retries 0, stream retries 0, gateway replay 0; separate from performance credit |
| Doctor, integration status, cancel, event replay | pass | Implemented CLI controls; replay does not resume inference |
| External acceptance in ordinary run | pass | Explicit frozen owner contract/checker; no-model Windows SDK gate; seven real fault/boundary controls and 21 offline regressions; claims only selected checks |
| Runtime TUI / native-session resume | notimplemented | No such commands or interface shipped |
| Real 2D/3D/4D demos | pass | Accepted old case02 originals preserved; labelled packaged portability patch passed Windows/Ubuntu CI |
| Local core verification | pass | Acceptance-gate source: Windows discovered 327 tests, 306 passed/21 unavailable-symlink skips, exit 0 in 29.923s; Ruff selected correctness rules and mypy on 16 files passed |
| Historical private CI | pass | Confirmed green for f757663: all 192 then-current core tests on Windows/Ubuntu; examples, static checks, build and 454-object all-history scan passed; this is not current-release CI |
| Exact new publication CI | deferred | Must be checked on the new private main commit after publication; retain final verification outside Git to avoid a self-referential commit loop |
| License selection | blocked | Owner decision pending; repository remains private |
| Host configuration preservation | pass | Process-local overrides; no copied auth tokens, global-setting rewrites or sandbox bypass |

## Latest balanced repeat

[Case08](../benchmarks/case08/README.md) accepted both 97-point artifacts after all
26 criteria were assessed and five gates passed. Both passed native 57/57 and
headless 25/25. A finished in 1120.781 seconds; B failed at 1094.797 seconds with an
incomplete upstream body read and unknown failed-request usage. This is not
successful faster completion. Four MCP status calls and one used direct worker
were observed. Latest-head private CI is tracked on the published commit; previous CI rows are
named historical evidence.

The separate model-free MCP snapshot proof passed 15 SDK checks and 10 controller
checks. Host non-project config semantics and all 15 installed skill/AGENTS/manifest
files remain unchanged. Native project registration changed; auth content was not
copied and no host sandbox configuration was disabled.

## Native proof and its limits

The public [sanitized integration summary](evidence/integration-2026-10-23.json) records the successful second helper proof: **144.578 seconds**, 8/8 completed requests, actual response model `gpt-6.1-sol`, requested efforts six `xhigh` and two `medium`. Known usage totals are 142,279 input, 3,385 output and 28,800 cached tokens. Response metadata does not independently echo reasoning effort. API cost and subscription quota delta remain `null`.

Only the exact owned native sessions were inspected: one had null role metadata and one `worker`. Native collaboration calls plus completed requests support capability. The root actually attempted a protected synthetic-state read and received `PermissionError`; the helper refused under the known policy without issuing that operation. Do not claim a helper OS-level denial. An earlier missing-Git setup failure used zero model calls and remains retained. This separate proof is not a Tree benchmark or speedup result.

The model-free kernel check separately exercised real sandbox permissions on owned synthetic files/SQLite and confirmed host access before/after. Native internal history access was not fully audited. Shared-state and current-peer isolation remain degraded; raw databases, journals, rollout/auth containers and native logs must never be published.

## Demos, CI and frozen experiments

Subsequent Windows sandbox verification of the initial packaged demos passed 35 solo and 47 flow tests. Ubuntu CI later exposed solo's platform-dependent full-float fingerprint. The explicitly recorded post-benchmark canonical-identity patch preserved geometry and fixture bytes. The subsequent green CI passed all 36 solo/47 flow tests on Windows; Ubuntu passed 35/45 with 1/2 Windows-only skips. Both platforms passed all 18 renders. Original snapshots and scores are unchanged; packaging and subsequent verification are distinct records.

The [confirmed green private CI run](https://github.com/MilliganCo/Codex-flow/actions/runs/39989887104) tested commit `f757663` on Windows and Ubuntu: all 192 core tests, the packaged demos, static checks, zipapp build and a 454-object working-tree/all-history scan passed. [Exact CI evidence](evidence/ci-2026-10-23.json) retains prior runs and platform-specific skips. This verifies the named code commit; later report-only revisions are checked by their own Actions runs.

The [run-record path-boundary fix](evidence/runs-boundary-2026-10-23.json) added eleven tests and is included in that green CI. It changes inspection/cancellation only and does not rewrite the frozen experiment.

Case02 retained accepted artifact scores A=95/B=97/C=95/D=96 with zero successful Mercury calls and unconfirmed helpers. Case03 is aborted and immutable. Case04 accepted A=89/B=83/C=96/D=90 with unverified helpers. Final [case05](../benchmarks/case05/README.md) accepted A=97/B=89/C=89/D=94 after all 26 criteria/five gates. B/C/D used 1/2/1 helpers; B/C made one Mercury call each; B/D ran two inspired probes each. A completed, B/C hit deadlines and D failed on an upstream connection-open error without a retry. All defects and original process statuses remain recorded; no causal acceleration conclusion follows.

The [127 published case05 application files](../benchmarks/case05/source-publication.json) preserve evaluated bytes; five original self-report logs are omitted. Their raw snapshot subtree uses `-text` to preserve fixture bytes across Git checkouts. Snapshot defects remain unrepaired; two-platform example CI applies to the separately maintained case02 copies. A post-evaluation GIF uses twelve real CLI exports from unchanged case05 A and does not contribute a benchmark timing claim.
