# Integrations

Integration states are evidence, not feature badges. Disabled, configured, reachable, validated and active are different facts. `integrations status` reads settings only and leaves validation false. Use `doctor` for native CLI preflight, or an explicitly requested live Mercury smoke.

## Native Codex

The runtime uses an existing [Codex CLI](https://github.com/openai/codex), requires native ChatGPT subscription login and launches a process-local subscription provider contract through a loopback gateway. It does not open or copy auth token files. The native CLI supplies authentication, which the gateway forwards in memory only to the fixed official subscription upstream. A fresh per-run nonce protects the listener; redirects and API-key-style credentials are rejected. Availability in `doctor --deep` means the model/effort appears in native metadata; it does not prove a generation request completed.

The root requests `gpt-6.1-sol` with `xhigh`. Generated helper profiles request Sol medium for default/worker/awaiter, Luna medium for explorer and Sol high for reviewer. Native concurrency is capped at three helpers. All custom roles inherit parent permissions; their read-only ownership, maximum total count and depth are instruction-only. Parallel parent persistence is required for native worker rollouts; role-file existence or different request profiles alone does not prove a distinct helper ran.

The shared gateway inference budget is at most 80 requests across probes/root/gateway-routed helpers. It records request model/effort, actual response model and usage; response metadata does not independently echo reasoning effort. Complete usage aggregates require every observed request to finish with complete usage. Worker identities and subscription quota deltas remain separate evidence questions.

### Independent native capability proof

The [sanitized integration evidence](evidence/integration-2026-10-23.json) records a separate helper proof completed in **144.578 seconds**, outside every Tree benchmark arm. All eight requests completed: six actual `gpt-6.1-sol` responses at requested `xhigh`, and two at requested `medium`. Observed totals were 142,279 input, 3,385 output and 28,800 cached tokens. Money and subscription quota delta remain unknown. Requested effort is not independently echoed by the response.

The audit was limited to the proof's exact owned native sessions: one session had null role metadata and one had role `worker`; native spawn/wait calls and completed requests support actual helper capability. The root's synthetic protected-state read produced `PermissionError`. The helper refused that operation under the known policy **without attempting it**; no helper OS-level read denial is claimed. The earlier proof attempt failed during missing-Git setup with zero model calls and is retained separately. Neither attempt is a benchmark or speedup measurement.

A separate **zero-model-call** kernel boundary check passed ordinary project reads/writes and observed `PermissionError` for protected synthetic sentinel/SQLite operations. The host could read/update its own SQLite fixture before and afterward. This proves those tool boundaries for owned synthetic files, not isolation of native internal history or every indirect read.

## Mercury: external and free-only

`MercuryBridge` references an existing, explicitly trusted installation containing its decision client and credential helper. **That implementation is not bundled or redistributed.** Selecting its root authorizes loading that trusted external helper. Disabled or absent configuration performs no credential read or provider call.

The bridge sends bounded abstract facts such as complexity, independent-step count, risk and ownership conflicts. It does not send source trees, task prose, paths, evaluator cases or credentials as decision state. Response acceptance requires the expected free model/build, validated usage, verified zero cost and a finite probability in range. Low confidence or failed validation falls back to deterministic rules. No routing answer grants write permissions, changes the root model or relaxes a sandbox.

The [official free model page](https://openrouter.ai/inception/mercury-decide:free) describes the free route. Availability and pricing must be rechecked by the external adapter for actual calls; a historical free listing is not a permanent guarantee.

An explicit smoke is:

```powershell
python codex-flow.py doctor --mercury-root <trusted-external-root> --live-mercury
```

This is an external provider request, unlike the default doctor. It requires an already configured external free-only adapter and its own authentication. It does not reuse ChatGPT subscription quota for OpenRouter.

**Current source: validated typed smoke.** A natural-exit wrapper fixed the initial Windows Node shutdown issue. The subsequent HTTP 403 was resolved by forwarding the user's existing configured Windows system proxy into the Node subprocess and using `--use-env-proxy`. Proxy values were not logged, global settings were not changed, and the external installation was not modified.

The real free-only smoke returned `OBSERVED` with probability `0.9947798753220525`, `successful_calls: 1`, `inference_attempts: 1`, and usage `{ "cost": 0, "input_tokens": 144, "output_tokens": 1 }`. Expected model/build/provider and zero-cost checks were adapter-validated. This validates one actual typed routing call in the current environment, not routing accuracy, general uptime or every future invocation. Configuration still defaults to disabled.

**Keep experiment versions separate.** Frozen case02 recorded zero successful Mercury calls; the later smoke must not be counted in those arms. Case04 independently scored A/B/C/D=89/83/96/90: B/C each recorded one successful Mercury call, while B/D each ran two Harness²-inspired probes. Helpers were not verified in B/C/D, so these counts do not establish full integration or causal benefit. Independent helper proofs establish capability outside that benchmark, not delegation within its arms.

Final case05 did observe parent-linked used helpers in B/C/D (1/2/1), successful Mercury in B/C (one each) and two inspired probes in B/D. All four artifact scores passed acceptance: 97/89/89/94. B/C still reached their deadlines and D failed on an upstream connection-open error. This proves observed component execution in that frozen case; general routing accuracy, application-quality improvement, quota savings and strict profile isolation remain unestablished. See the [report](../benchmarks/case05/README.md).

## Harness²-inspired local probes

The [upstream Harness² project](https://github.com/google-research/harness2) is a research reference. Its executor is not bundled or launched. The local module implements bounded proposal comparison, safety/completeness gates, explicit adoption and hash-checked rollback inside `.codex-flow/lessons/`.

Historical cases02/04/05 ran two single-agent planning probes per enabled arm, measuring coverage of five plan fields. Their duration and usage remain in those immutable results. The paired proxy did not establish application-quality benefit; case05 spent125.328 seconds on this prefix.

Current normal execution and benchmarks use an enabled guard with status `deferred`, zero automatic probes and no implicit loading of `active.txt`. This removes the unvalidated calibration prefix rather than claiming a faster optimizer. Re-enabling optimization would require independent application-quality evidence under a separately declared calibration protocol.

The explicit library `benchmark.probe` remains diagnostic only and always passes `adopt=False`. It cannot modify an existing active overlay. Library comparison/rollback contracts and old records remain available; the CLI exposes no separate calibration/adopt command. Reports must distinguish the guard from active optimization and keep upstream probes zero. See [rollback](rollback.md).
