# Changelog

## Unreleased — opt-in runtime development

- Add durable `workflow start/status/pause/resume/cancel`: project-local SQLite
 stage/attempt state, request reservations before forwarding, renewable 30-second
 active-time reservations, PID/creation ownership and pre-spawn launch barriers.
 Immutable snapshots and review bundles preserve the original working tree;
 explicit resume reuses accepted stages and never resets the shared budget.
 Model-stage retries are manual and bounded to two attempts. A portable no-model
 control proves real process death and SDK acceptance without repeating generation.
 Runtime and native conversation resume remain distinct.

- Add explicit owner-selected external acceptance to ordinary `run`, with a
 `completed_verified` result only after all declared sandboxed checks pass.
 Preserve unconfigured runs as `completed_unverified`; configured rejection
 exits 3. Standalone `verify` defaults to inert contract inspection and can run
 checks without a model. Freeze checker/contract before generation, bind declared
 inputs before/after, reject empty/stale/incomplete evidence, and share the task
 deadline. The first backend is the reviewed Windows Codex sandbox; other hosts
 refuse explicit execution before generation. Seven real sandbox controls and
 21 offline acceptance regressions are separate from prior model benchmarks.

- Share a monotonic task deadline/attempt view between native execution and the
 subscription gateway. Parallel Flow receives a fixed-path read-only local MCP
 budget status tool. Gateway message injection is disabled by default after native
 async-history incompatibilities; original request bytes are forwarded unchanged.
 Add safe operation timing/HMAC metadata and header-open/body-read timings.
 Control refusals now distinguish408 deadline,429 request budget and503 cancellation;
 native cancellation is `cancelled`, distinct from deadline timeout. No retry,
 provider, sandbox or global-setting change is introduced. Case07 was cancelled
 before grading; all partial artifacts/traces remain. The native MCP prerequisite
 passed19/19 checks; independent case08 A/B is in progress. Offline250 tests passed
 in WSL; Windows229 passed with21 symlink skips. An isolated Python bootstrap
 prevents workspace/PYTHONPATH imports in the trusted MCP server.

- After the case08 freeze, snapshot the four trusted MCP modules into the
 model-read-only controller tree before native launch. This closes editable-source
 imports in self-hosting tasks without changing the frozen external-runtime trial.
 Source-mutation and zipapp resource checks passed; combined252 tests passed in
 WSL, with231 Windows passes and21 symlink skips. No performance claim is assigned
 to this subsequent security hardening.

- Preserve case08 B's body-read failure and unknown usage. Add prospective fixed
 error-type/phase diagnostics and failed-read duration without raw responses or
 exception text. Mark completion only after successful response close; a failed
 close returns a fixed error body and cannot count as completed. No retries or
 fallback were added. Both254-test suites passed (Windows233/21 skipped).

- Independent case06 repeat: solo 97/Flow 98, both completed within 1500 seconds,
 43/36 native requests, headless 25/25 and native 57/57 each. Preserve 69 unchanged
 submitted files, raw failed auxiliary rotation assertions and their observed-value
 audit. The one-point score difference is aesthetic; no general speed or quota
 claim. Runtime code maps to curated commit 11ee18d after LF normalization.

- Remove automatic plan-coverage calibration from the task critical path; enabled guard reports deferred with zero probes and ignores stale overlays. Explicit plan diagnostics cannot adopt. Request early runnable/docs/check artifacts, bounded helper evidence and an instruction-only final verification reserve. Add optional AB-only repeats while retaining default ABCD and the same task/model/budget boundaries.

- Preserve the existing 1.2.0 skill payload, offline installer and `flowctl.py` command contracts.
- Add a project-local runtime entrypoint, strict bounded config and deterministic single/parallel routing.
- Add native subscription CLI execution with Sol XHigh, explicit sandbox overrides, cancellation/deadlines and sanitized event evidence.
- Add a nonce-protected loopback gateway with fixed official subscription upstream, a shared inference-request budget of at most 80, and separate requested-profile/actual-response usage evidence.
- Add an optional external free-only Mercury bridge and bounded Harness²-inspired measured proposal comparison with guarded adoption/rollback.
- Add experiment scaffolding for concurrent A/B and fresh ablations, plus English/Russian entry documentation, safety boundaries and license review notes.

- Fix the Windows Mercury child transport with natural Node exit and forwarding of an existing configured system proxy through `--use-env-proxy`, without logging values or editing global settings. Current source completed one real typed smoke with adapter-validated model/build/provider and usage cost zero. The earlier frozen benchmark retains zero successful Mercury calls.

Known limits: parallel parents persist for native worker rollouts; SQLite/logs are project-local but native auth/rollouts remain shared. Custom roles inherit parent permissions, with instruction-only read-only/depth restrictions. Windows reciprocal ACL interference requires identical existing-target denials; peer read isolation is soft/degraded. Incomplete gateway usage stays null, and requests do not identify agents. The wrapper makes one attempt regardless of `max_attempts`.

Frozen case02 artifact scores are A=95/B=97/C=95/D=96, with zero successful Mercury calls and unconfirmed helpers. Case04 independently accepted A=89/B=83/C=96/D=90, with real Mercury calls and inspired probes but unverified helpers. No full-component speed claim follows. Case03 is aborted and immutable after future deny targets became directories. All original records remain unchanged.

Current source adds mandatory parallel developer instructions, exact owned parent-linked metadata with positive child usage, and an explicit degraded orchestration outcome when no helper is verified. A separate ordinary-controller prerequisite observed one real child and a correct artifact; a zero-model concurrent fixture check passed protected-state denials. Final case05 accepted artifacts A=97/B=89/C=89/D=94 with real B/C/D helpers, B/C Mercury calls and B/D inspired probes. Deadlines, D's upstream connection-open failure and all application defects remain preserved. Publish 127 unchanged application files and twelve actual post-evaluation XW frames. No speedup claim or project license is introduced.

Fix a subsequently reproduced P2 in `runs list/show/replay/cancel`: validate roots, folders and record/cancel paths before access so links cannot redirect outside the project. Eleven focused regressions and the combined 192-test suites passed in WSL/local Windows with recorded symlink skips. This source-only fix does not modify frozen case05. Original private development history is retained.

## 1.2.0 — existing baseline

Existing selective browser verification routes, safe managed-global-block upgrade protections, installer tests and workflow references. Historical validation is recorded in `TEST-REPORT.md`; it does not cover the new runtime.
