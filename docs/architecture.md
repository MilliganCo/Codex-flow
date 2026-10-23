# Architecture

Codex Flow has two compatible layers. `payload/codex-flow/` retains the 1.2.0 skill and offline helper. `codex-flow.py` imports the opt-in implementation from `runtime/codex_flow/`. Existing CLI contracts remain separate rather than being replaced by a new installer.

| Module | Responsibility |
|---|---|
| `cli.py`, `config.py` | Public command parsing, bounded project-local settings and explicit enabling |
| `contracts.py`, `policy.py` | Serializable task/route records, dependency readiness and deterministic routing |
| `native.py` | Native CLI discovery, subscription check, process-local overrides, timeout/cancellation |
| `mercury.py`, `harness.py` | Optional external typed decisions and project-local measured proposals |
| `telemetry.py`, `doctor.py`, `benchmark.py` | Sanitized evidence, metadata preflight and experiment lifecycle |

## Task execution

1. Parse configuration and task text; reject unknown fields or unsupported bounds.
2. Select single or parallel execution from independence and risk rules. An optional validated Mercury result is advisory.
3. Start one root Sol XHigh native turn with explicit sandbox/config overrides. Native delegation belongs to that turn; helpers have bounded instructions and ownership.
4. Consume native JSON events, record sanitized metadata, and capture supported root usage.
5. Return completion state and artifacts for independent verification.

`ExecutionPlan.ready_batches()` validates dependency identifiers, rejects cycles and avoids overlapping paths within one batch. It is a library contract; the current `run` command does not automatically extract a complete task graph from arbitrary prose.

The coordinator is the integrator. Sol medium is the requested default helper profile; review instructions can request stronger review reasoning where the host supports it. Per-helper profile enforcement and aggregate helper accounting must be verified from actual host evidence. Do not infer them from the role description alone.

## Optimization boundary

`GuardedHarness` records a proposal, measured baseline/candidate evidence and an eligibility decision. Safety and completeness must both pass; improvement is higher quality, or equal quality with shorter measured duration. Adoption is explicit and project-local. Rollback checks that the adopted file is unchanged before restoring the previous text.

The benchmark and an explicitly configured `run` measure a pair of **plan-coverage** probes and can adopt the resulting instruction proposal. Both require opt-in, and those probes consume additional subscription quota/time. This is Harness²-inspired behavior, not execution of the [upstream Harness²](https://github.com/google-research/harness2) optimizer.

## Evidence boundary

Run JSONL events have timestamps, trace/task identifiers, event type, sanitized payload, duration and error category. Root usage is retained when exposed. Unknown aggregate helper usage is `null`. Concurrent-helper cap is native configuration; maximum total helpers and depth are instruction-only limits. There is no live TUI or authoritative billing ledger.

Separate worktrees isolate writes and Git state, but share Git history and native credential home. Current `workspace-write` execution permits sibling reads. Isolation is therefore degraded for adversarial or confidential multi-workspace workloads; it is not a hard read boundary.
