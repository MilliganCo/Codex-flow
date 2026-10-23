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
  "max_model_requests": 80
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

`--max-agents` and `--timeout` override run-level values. `--no-mercury` and `--no-harness2` disable optional components for that run. An external Mercury installation is selected by `--mercury-root`; its key or source is never placed in project config. Enabling `harness2` executes two measured planning probes before the main task, consuming additional subscription time/quota. Both probes use the fixed five-field ASCII Tree brief even for an unrelated task; this is a narrow integration pilot, not a task-specific general optimizer or a measure of application quality.

## Routing inputs

`--independent-steps` defaults to 1. At least two independent steps are required for the rule-based parallel route. `--single-agent` and `--strategy single` force single execution. `--strategy parallel` still passes through the independence gate; it is not an unconditional fan-out switch.

| Run flag | Admission behavior |
|---|---|
| `--risk-level low\|normal\|medium\|high\|critical` | Default `normal`; medium, high and critical stop execution for a scope decision |
| `--conflicting-paths` | Declare overlapping ownership and select single execution |

Risk, ownership and independence are caller-provided facts, not automatic task decomposition or risk detection. These deterministic gates run before Mercury. Single execution, escalation and dry runs make no Mercury call. Only an admitted parallel candidate may request its bounded recommendation; accepted `normal` risk is encoded as `low` for the external adapter, while escalated risks are never sent or relabeled as safe.

## CLI and host settings

`--codex` takes precedence over `CODEX_FLOW_CODEX`, followed by PATH discovery. The adapter checks `--version` and native subscription login before execution.

Runtime overrides are scoped to the launched CLI process: root Sol XHigh, workspace-based permissions, approvals disabled for this noninteractive wrapper, shell-network access off and discovery/hooks/plugins/apps/memory disabled. With read-denial targets, a named permission profile extends `:workspace` and adds explicit existing-path denies; it is not a sandbox bypass. `benchmark tree --protect-path <existing-path>` is repeatable. Missing targets are rejected because Windows SDK materialized future deny paths as directories.

Single-agent parents are ephemeral. Parallel parents persist for native worker rollouts; `sqlite_home`/`log_dir` point into `.codex-flow/native-state/`, history persistence is disabled, and role files live under `.codex-flow/runtime-agents/`. Native authentication and rollout container remain shared. The environment builder uses the default native credential home rather than preserving a caller's custom `CODEX_HOME`. Host config files are not edited.

The native subscription base URL is process-locally redirected to a nonce-protected loopback gateway; its only upstream is the fixed official subscription endpoint. No external provider URL or paid fallback is configurable. Custom helper profiles inherit parent permissions; read-only and depth rules are instructions, not profile-enforced sandboxes. Review [safety](safety-and-permissions.md) before enabling execution.

The separate legacy helper has its own `--home`, `--codex-home`, `--skills-dir` and installer options. Those are not runtime options. No config migration is attempted silently; a schema change requires an explicit new supported version.
