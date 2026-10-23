# Integrations

Integration states are evidence, not feature badges. Disabled, configured, reachable, validated and active are different facts. `integrations status` reads settings only and leaves validation false. Use `doctor` for native CLI preflight, or an explicitly requested live Mercury smoke.

## Native Codex

The runtime uses an existing [Codex CLI](https://github.com/openai/codex), requires native ChatGPT subscription login and launches a process-local subscription provider contract through a loopback gateway. It does not open or copy auth token files. The native CLI supplies authentication, which the gateway forwards in memory only to the fixed official subscription upstream. A fresh per-run nonce protects the listener; redirects and API-key-style credentials are rejected. Availability in `doctor --deep` means the model/effort appears in native metadata; it does not prove a generation request completed.

The root requests `gpt-6.1-sol` with `xhigh`. Generated helper profiles request Sol medium for default/worker/awaiter, Luna medium for explorer and Sol high for reviewer. Native concurrency is capped at three helpers. All custom roles inherit parent permissions; their read-only ownership, maximum total count and depth are instruction-only. Parallel parent persistence is required for native worker rollouts; role-file existence or different request profiles alone does not prove a distinct helper ran.

The shared gateway inference budget is at most 80 requests across probes/root/gateway-routed helpers. It records request model/effort, actual response model and usage; response metadata does not independently echo reasoning effort. Complete usage aggregates require every observed request to finish with complete usage. Worker identities and subscription quota deltas remain separate evidence questions.

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

**Frozen benchmark: degraded Mercury.** The active frozen case study was launched with an earlier copied runtime and recorded zero successful Mercury calls. The later current-source smoke must not be counted in those arms or used to relabel B as fully active. Its earlier HTTP 403 evidence remains valid for the runtime that actually executed the experiment. Any comparison using the corrected bridge needs a new frozen experiment ID.

## Harness²-inspired local probes

The [upstream Harness² project](https://github.com/google-research/harness2) is a research reference. Its executor is not bundled or launched. The local module implements bounded proposal comparison, safety/completeness gates, explicit adoption and hash-checked rollback inside `.codex-flow/lessons/`.

The Tree benchmark runs two single-agent planning probes per enabled arm: baseline and candidate instructions. The metric is coverage of five required plan fields. Probe duration and model usage remain part of the experiment overhead. This is a real measured planning experiment, but it does not establish improved application correctness or speed. Reports must say **Harness²-inspired**, with upstream probes zero.

A normal `run` with `harness2: true` invokes the same paired measured planning probe unless `--no-harness2` is supplied. Probe records are stored under `.codex-flow/probes/`; proposals and active instructions remain project-local. Its result is degraded because the measured plan metric is not final application quality. Include probe cost/time in any efficiency comparison. The current CLI exposes no separate general proposal/adopt/rollback subcommand. The library rollback procedure is documented in [rollback](rollback.md).
