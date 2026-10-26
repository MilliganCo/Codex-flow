# Configuration

The runtime reads `.codex-flow/config.json` under `--repo`, or an explicit `--config <file>`. Both are global CLI options and must precede the subcommand. Missing configuration uses the defaults below. Unknown fields, wrong types and unsupported values are rejected.

```json
{
  "schema_version": 1,
  "enabled": false,
  "mode": "safe",
  "max_agents": 3,
  "max_depth": 1,
  "max_attempts": 1,
  "timeout_s": 1200,
  "model": "gpt-6.1-sol",
  "effort": "xhigh",
  "mercury": false,
  "harness2": false,
  "max_refinements": 1,
  "allow_paid_api": false,
  "max_model_requests": 80,
  "native_request_retries": 0
}
```

| Field | Accepted values and actual scope |
|---|---|
| `enabled` | Boolean; `run --enable` also opts in for one invocation |
| `mode` | `safe`, `benchmark`, `experimental`; a label, not permission to bypass safety |
| `max_agents` | Integer 1–3; requested native concurrent helper cap |
| `max_depth` | Only 1 in local config; delegation-depth restriction is instruction-only, not a native CLI setting |
| `max_attempts` | Integer 1–2; current wrapper executes one attempt regardless |
| `timeout_s` | Integer 1–3600; wall-clock wrapper deadline |
| `model`, `effort` | Only `gpt-6.1-sol`, `xhigh` in this verified profile |
| `mercury`, `harness2` | Booleans, default false; configured does not mean validated |
| `max_refinements` | Integer 1–2 for guarded local proposals; no automatic unbounded loop |
| `allow_paid_api` | Only false; true is rejected |
| `max_model_requests` | Integer 1–80; shared hard gateway inference-request budget, including planning probes |
| `native_request_retries` | Integer 0–1, default 0; optional native HTTP retry with stateless recovery in the same budgets |

## Bounded HTTP recovery

Set `"native_request_retries": 1` in a reviewed project configuration, or pass
that file through the global `--config <file>` option. There is no separate CLI
retry flag. The native HTTP request retry limit becomes one, stream retries stay
zero, and the gateway never replays a request itself. Every physical upstream
attempt reserves the same hard request budget, including failed attempts.

Only recognized transient transport failures and structured temporary HTTP 429
responses are eligible. Retry-After is honored up to the fixed 60-second policy;
a longer delay or one exceeding the remaining deadline defers instead of being
clamped into an early retry. This does not resume a failed task or promise
exactly-once backend execution. Default HTTP encoding remains `identity`; request
compression is disabled. Generic gzip does not establish token or quota savings.

The nine synthetic recovery cases and the separate 24-check real native
prerequisite are archived with the [final cohort](../benchmarks/efficient-cli-suite-20261026-02/README.md).
Their successful recovery/integration evidence is separate from the failed
performance criterion. The final candidate's test-proposal orchestration was
rejected; current Flow instructions use the balanced context-only reviewer.

`--max-agents` and `--timeout` override run-level values. `--no-mercury` and `--no-harness2` disable optional components for that run. An external Mercury installation is selected by `--mercury-root`; its key or source is never placed in project config. The enabled Harness²-inspired guard defers calibration with zero automatic online probes. Explicit library planning diagnostics cannot adopt instructions and do not establish application-quality gains. Historical two-probe runs retain their original runtime and measurements.

## Routing inputs

`--independent-steps` defaults to 1. At least two independent steps are required for the rule-based parallel route. `--single-agent` and `--strategy single` force single execution. `--strategy parallel` still passes through the independence gate; it is not an unconditional fan-out switch.

| Run flag | Admission behavior |
|---|---|
| `--risk-level low\|normal\|medium\|high\|critical` | Default `normal`; medium, high and critical stop execution for a scope decision |
| `--conflicting-paths` | Declare overlapping ownership and select single execution |

Risk, ownership and independence are caller-provided facts, not automatic task decomposition or risk detection. These deterministic gates run before Mercury. Single execution, escalation and dry runs make no Mercury call. Only an admitted parallel candidate may request its bounded recommendation; accepted `normal` risk is encoded as `low` for the external adapter, while escalated risks are never sent or relabeled as safe.

## CLI and host settings

### External acceptance

`run --acceptance-file <owner-reviewed-contract.json>` enables the optional
[external acceptance gate](acceptance-gate.md). Config schema 1 is unchanged;
no checker is discovered automatically. `verify --acceptance-file ...` inspects
without execution; add `--execute` for a no-model Windows sandbox check. Both
commands accept repeatable `--protect-path <existing-path>` read denials. Missing
targets and workspace-ancestor denies are rejected before execution. A configured
gate failure exits 3; an invalid contract/admission exits 2. An unconfigured run
retains its existing completion/exit behavior and explicitly reports `accepted: false`.

`--codex` takes precedence over `CODEX_FLOW_CODEX`, followed by PATH discovery. The adapter checks `--version` and native subscription login before execution.

Runtime overrides are scoped to the launched CLI process: root Sol XHigh, workspace-based permissions, approvals disabled for this noninteractive wrapper, shell-network access off and discovery/hooks/plugins/apps/memory disabled. With read-denial targets, a named permission profile extends `:workspace` and adds explicit existing-path denies; it is not a sandbox bypass. `benchmark tree --protect-path <existing-path>` is repeatable. Missing targets are rejected because Windows SDK materialized future deny paths as directories.

Single-agent parents are ephemeral. Parallel parents persist for native worker rollouts; `sqlite_home`/`log_dir` point into `.codex-flow/native-state/`, history persistence is disabled, and role files live under `.codex-flow/runtime-agents/`. Native authentication and rollout container remain shared. The environment builder uses the default native credential home rather than preserving a caller's custom `CODEX_HOME`. Host config files are not edited.

The native subscription base URL is process-locally redirected to a nonce-protected loopback gateway; its only upstream is the fixed official subscription endpoint. No external provider URL or paid fallback is configurable. Custom helper profiles inherit parent permissions; read-only and depth rules are instructions, not profile-enforced sandboxes. Review [safety](safety-and-permissions.md) before enabling execution.

The separate legacy helper has its own `--home`, `--codex-home`, `--skills-dir` and installer options. Those are not runtime options. No config migration is attempted silently; a schema change requires an explicit new supported version.
