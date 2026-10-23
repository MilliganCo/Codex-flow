# Integrations

Integration states are evidence, not feature badges. Disabled, configured, reachable, validated and active are different facts. `integrations status` reads settings only and leaves validation false. Use `doctor` for native CLI preflight, or an explicitly requested live Mercury smoke.

## Native Codex

The runtime uses an existing [Codex CLI](https://github.com/openai/codex), requires native ChatGPT subscription login and launches a process-local subscription provider contract. It does not open or copy auth token files. It rejects API-key fallback. Availability in `doctor --deep` means the model/effort appears in native metadata; it does not prove a generation request completed.

The requested root is `gpt-6.1-sol` with `xhigh`. Parallel mode enables native multi-agent execution, requests a maximum of three concurrent helpers and Sol medium defaults. Maximum total helpers and delegation depth are stated in instructions only; no verified native hard limit is claimed for them.

## Mercury: external and free-only

`MercuryBridge` references an existing, explicitly trusted installation containing its decision client and credential helper. **That implementation is not bundled or redistributed.** Selecting its root authorizes loading that trusted external helper. Disabled or absent configuration performs no credential read or provider call.

The bridge sends bounded abstract facts such as complexity, independent-step count, risk and ownership conflicts. It does not send source trees, task prose, paths, evaluator cases or credentials as decision state. Response acceptance requires the expected free model/build, validated usage, verified zero cost and a finite probability in range. Low confidence or failed validation falls back to deterministic rules. No routing answer grants write permissions, changes the root model or relaxes a sandbox.

The [official free model page](https://openrouter.ai/inception/mercury-decide:free) describes the free route. Availability and pricing must be rechecked by the external adapter for actual calls; a historical free listing is not a permanent guarantee.

An explicit smoke is:

```powershell
python codex-flow.py doctor --mercury-root <trusted-external-root> --live-mercury
```

This is an external provider request, unlike the default doctor. It requires an already configured external free-only adapter and its own authentication. It does not reuse ChatGPT subscription quota for OpenRouter.

**Current local integration status:** the initial Windows Node shutdown issue was fixed with a bounded natural-exit wrapper without editing the external installation. A subsequent free-only smoke returned `REJECTED`, `http_403`, `inference_attempts: 0`, `successful_calls: 0`. Mercury remains unavailable/degraded until actual per-run evidence says otherwise. An HTTP 403 does not establish a provider-wide outage or authorize a paid fallback.

## Harness²-inspired local probes

The [upstream Harness² project](https://github.com/google-research/harness2) is a research reference. Its executor is not bundled or launched. The local module implements bounded proposal comparison, safety/completeness gates, explicit adoption and hash-checked rollback inside `.codex-flow/lessons/`.

The Tree benchmark runs two single-agent planning probes per enabled arm: baseline and candidate instructions. The metric is coverage of five required plan fields. Probe duration and model usage remain part of the experiment overhead. This is a real measured planning experiment, but it does not establish improved application correctness or speed. Reports must say **Harness²-inspired**, with upstream probes zero.

A normal `run` with `harness2: true` invokes the same paired measured planning probe unless `--no-harness2` is supplied. Probe records are stored under `.codex-flow/probes/`; proposals and active instructions remain project-local. Its result is degraded because the measured plan metric is not final application quality. Include probe cost/time in any efficiency comparison. The current CLI exposes no separate general proposal/adopt/rollback subcommand. The library rollback procedure is documented in [rollback](rollback.md).
