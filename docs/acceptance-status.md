# Acceptance status — 2026-10-23

This is an evidence boundary, not a claim that the entire requested architecture has passed. Status values are `pass`, `degraded`, `blocked` and `notimplemented`. Independent integration proofs, packaged-demo verification and frozen benchmarks are separate records; later success does not rewrite an earlier run.

| Requirement | Status | Verified scope / remaining limit |
|---|---|---|
| Existing Codex Flow compatibility | pass | Legacy skill/helper contracts retained; offline regression checks passed |
| Mercury free-only integration | pass | Real typed smoke with validated model/build/provider and reported cost 0; disabled by default; no routing-accuracy claim |
| Harness²-inspired optimization | degraded | Bounded measured plan probes, guarded adoption/rollback; plan coverage is not application quality |
| Upstream Harness² executor | blocked | Unsafe upstream execution path excluded; not silently substituted or claimed active |
| Native root/helper capability | pass | Separate proof: exact owned root/worker sessions, native spawn/wait and 8 completed subscription requests |
| Kernel tool boundary | pass | Zero-model-call synthetic check: normal read/write passed, private sentinel/SQLite operations raised `PermissionError`, host fixture remained usable |
| Strict independent native profiles/state | blocked | Auth/rollout container shared; project SQLite can import historical metadata; separate paths do not establish isolation |
| Hard helper read-only/depth isolation | degraded | Custom roles inherit parent permissions; ownership/depth are instructions; worker policy refusal is not an observed OS attempt |
| Full multi-agent A/B contribution | degraded | Case04 scored 89/83/96/90; B/C/D helpers unverified despite Mercury calls/probes. New case05 is running on a separately frozen runtime after a verified controller/helper prerequisite |
| Doctor, integration status, cancel, event replay | pass | Implemented CLI controls; replay does not resume inference |
| Runtime TUI / native-session resume | notimplemented | No such commands or interface shipped |
| Real 2D/3D/4D demos | pass | Accepted old case02 originals preserved; labelled packaged portability patch passed Windows/Ubuntu CI |
| Local core verification | pass | 192 tests after the run-record boundary fix: Windows 174 passed/18 skipped; WSL 192 passed |
| Private CI | pass | Confirmed green for d5fb49a: 181 core tests on Windows/Ubuntu; packaged examples, static checks, build and all-history scan passed |
| License selection | blocked | Owner decision pending; repository remains private |
| Host configuration preservation | pass | Process-local overrides; no copied auth tokens, global-setting rewrites or sandbox bypass |

## Native proof and its limits

The public [sanitized integration summary](evidence/integration-2026-10-23.json) records the successful second helper proof: **144.578 seconds**, 8/8 completed requests, actual response model `gpt-6.1-sol`, requested efforts six `xhigh` and two `medium`. Known usage totals are 142,279 input, 3,385 output and 28,800 cached tokens. Response metadata does not independently echo reasoning effort. API cost and subscription quota delta remain `null`.

Only the exact owned native sessions were inspected: one had null role metadata and one `worker`. Native collaboration calls plus completed requests support capability. The root actually attempted a protected synthetic-state read and received `PermissionError`; the helper refused under the known policy without issuing that operation. Do not claim a helper OS-level denial. An earlier missing-Git setup failure used zero model calls and remains retained. This separate proof is not a Tree benchmark or speedup result.

The model-free kernel check separately exercised real sandbox permissions on owned synthetic files/SQLite and confirmed host access before/after. Native internal history access was not fully audited. Shared-state and current-peer isolation remain degraded; raw databases, journals, rollout/auth containers and native logs must never be published.

## Demos, CI and frozen experiments

Subsequent Windows sandbox verification of the initial packaged demos passed 35 solo and 47 flow tests. Ubuntu CI later exposed solo's platform-dependent full-float fingerprint. The explicitly recorded post-benchmark canonical-identity patch preserved geometry and fixture bytes. The subsequent green CI passed all 36 solo/47 flow tests on Windows; Ubuntu passed 35/45 with 1/2 Windows-only skips. Both platforms passed all 18 renders. Original snapshots and scores are unchanged; packaging and subsequent verification are distinct records.

The [confirmed green private CI run](https://github.com/MilliganCo/Codex-flow/actions/runs/39987763791) tested commit `d5fb49a` on Windows and Ubuntu: all 181 core tests, the packaged demos, static checks, zipapp build and a 442-object working-tree/all-history scan passed. [Exact CI evidence](evidence/ci-2026-10-23.json) retains the prior failed run and platform-specific skips. This verifies the named commit, not an untested later revision.

A subsequent [run-record path-boundary fix](evidence/runs-boundary-2026-10-23.json) added eleven tests: the combined 192-test local suites passed, with Windows symlink skips as recorded. It changes inspection/cancellation only and does not rewrite the frozen experiment. CI for that later fix is pending.

Case02 retained accepted artifact scores A=95/B=97/C=95/D=96 with zero successful Mercury calls and unconfirmed helpers. Case03 is aborted and immutable. Case04 independently accepted A=89/B=83/C=96/D=90, with the remaining defects preserved in its reports. B/C each recorded one Mercury call and B/D each two Harness²-inspired probes; helpers were unverified. No full-integration or acceleration conclusion follows. Frozen runtime and original evaluation evidence remain unchanged. Case05 uses a new frozen runtime and unchanged task/rubric; no results are assigned before independent evaluation.
