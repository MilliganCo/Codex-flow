# Known limitations

This list describes implementation boundaries, not missing evidence disguised as passing checks.

## Execution and coordination

- Root model/effort is fixed to Sol 6.1 XHigh. Metadata preflight does not prove inference availability.
- Independent-step counts are supplied by the caller; arbitrary task prose is not automatically converted into a validated dependency graph.
- Native concurrent-helper cap is requested; custom roles inherit parent permissions. Read-only ownership, total-helper and depth restrictions are instruction-only. Configured role models are not proof of actual helper execution.
- `max_attempts` is configurable but the current wrapper executes a single attempt. There is no general autonomous retry/refinement daemon.
- No runtime TUI, dashboard or resume command exists. JSON inspection and event replay are implemented.

## Security and environment

- Workspace permissions do not give full read isolation. Reciprocal Windows deny profiles interfere through shared `CodexSandboxUsers` ACLs; the benchmark uses identical existing-target denials protecting evaluator/prior solutions while current-peer reads remain soft/degraded. Future deny targets are rejected after the aborted case03.
- Native auth/rollout storage remains shared. SQLite/log paths are physically project-local, but the CLI can rehydrate unrelated historical thread metadata into the local database. Separate paths do not establish isolated native contexts/log contents; strict independent profiles are a platform blocker. Never publish native databases, journals or raw logs. Single-agent parents are ephemeral; parallel parents persist for worker rollouts.
- Task restrictions, ownership, depth guidance and redaction are not substitutes for OS access control or human review.
- Native CLI schemas and flags may change. Global configuration is not rewritten to compensate silently.
- Windows behavior is the primary environment under evaluation; portability requires platform-specific evidence.

## Integrations

- Mercury is external and optional. Current source passed a real free-only typed smoke; case04 recorded one successful call in each of B/C. This is not a routing-accuracy or availability guarantee, and configuration remains disabled by default. Case02 still has zero successful calls; later evidence does not change its integration status.
- Free pricing/provider/build guarantees depend on the trusted external adapter's checks; no external provider implementation is bundled.
- The local optimizer is Harness²-inspired and measures plan coverage. Both benchmark and normal opt-in `run` currently use the same hardcoded ASCII Tree planning brief; it is not a general task-specific optimizer and does not establish application-quality gains. Existing project proposal limits can refuse repeated probes; history is preserved.
- Explicitly configured Harness-inspired probes add two planning calls before a normal run. Their plan-coverage metric does not establish final application quality; account for their overhead separately.

## Measurement and acceptance

- Gateway all-request usage is known only when every observed request completes with usable counters; it does not identify agents or independently confirm reasoning effort. Root usage is separate. Quota deltas and actual API cost may remain unknown.
- First-working-demo time is not automatically established by file creation or native completion.
- The benchmark runner freezes evaluator hashes but does not invoke the evaluator or perform blind interactive review automatically.
- Parallel runs contend for host/network/quota resources. One experiment cannot support general speed claims.
- Final quality requires independent evidence, including real 4D mathematics and runnable behavior; self-tests and changed frame bytes are insufficient alone.

The frozen case02 artifact scores A=95/B=97/C=95/D=96 coexist with zero successful Mercury calls and unconfirmed helpers. They do not validate a full-component performance gain. Case03 is aborted and immutable. Case04 artifact scores are A=89/B=83/C=96/D=90, with all artifacts accepted under the frozen formula despite documented defects. B/C each recorded one Mercury call; B/D each ran two local inspired probes. Helpers were unverified in B/C/D. Requested-profile heuristics are insufficient proof, and development-source fixes do not change that frozen runtime.

The separate [native capability proof](evidence/integration-2026-10-23.json) did verify a root and worker using exact owned-session metadata, native collaboration calls and eight completed requests. It took 144.578 seconds and is not a benchmark/speed proof. The root's synthetic protected read produced `PermissionError`; the worker refused under policy without attempting it. A zero-model-call kernel check separately passed normal reads/writes and denied protected synthetic file/SQLite operations while preserving host fixture access. These bounded successes do not establish strict native-history/state isolation or hard helper read-only/depth enforcement. Imported historical metadata is not proof of actual cross-arm reading.

Local Windows verification after record-access hardening reports 174 core tests passed/18 symlink skips; WSL passed all 192. Confirmed private CI for `f757663` passed all 192 core tests on both Windows and Ubuntu, plus packaged examples, static checks, build and full-history scan. Windows example suites passed 36/47 tests; Ubuntu passed 35/45 with 1/2 Windows-only skips. The solo copy has a labelled post-benchmark canonical fingerprint patch; original artifacts/scores remain unchanged. Nine-decimal canonicalization reduces observed libm drift but cannot guarantee equality across every rounding boundary or OS. See [acceptance status](acceptance-status.md) for the verified commit scope.

Final case05 observed actual B/C/D helpers (1/2/1), B/C Mercury calls and B/D inspired probes. Scores A/B/C/D=97/89/89/94 are accepted artifacts, while B/C generators timed out and D failed to open an upstream connection. B's ConPTY Ctrl+C timeout, C's cached exports, D's fixture-test failures and missing documentation remain preserved in the unrepaired source snapshots. These defects are not hidden by successful geometry or later demo exports. All four snapshots were evaluated on Windows; example CI elsewhere does not establish their cross-platform portability. Solo scored highest in this case, without a general causal/performance conclusion.

## Distribution

No project license has been chosen. Keep repository access private while ownership, distribution rights and the final license are reviewed. Original 1.2.0 reports remain historical records, not evidence that newly added runtime paths passed those earlier checks.
