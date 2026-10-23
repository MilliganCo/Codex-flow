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
  "allow_paid_api": false
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

`--max-agents` and `--timeout` override run-level values. `--no-mercury` and `--no-harness2` disable optional components for that run. An external Mercury installation is selected by `--mercury-root`; its key or source is never placed in project config. Enabling `harness2` executes two measured planning probes before the main task, consuming additional subscription time/quota; plan coverage remains a limited metric.

## Routing inputs

`--independent-steps` defaults to 1. At least two independent steps are required for the rule-based parallel route. `--single-agent` and `--strategy single` force single execution. `--strategy parallel` currently still passes through the independence gate; it is not an unconditional fan-out switch. Risk and ownership validation are available in the policy library but are not automatically derived from arbitrary task text.

## CLI and host settings

`--codex` takes precedence over `CODEX_FLOW_CODEX`, followed by PATH discovery. The adapter checks `--version` and native subscription login before execution.

Runtime overrides are scoped to the launched CLI process: Sol XHigh, `workspace-write`, approvals disabled for this noninteractive wrapper, shell-network access off, discovery/hooks/plugins/apps/memory disabled and ephemeral sessions. The runtime uses the native default credential home for login reuse; custom caller `CODEX_HOME` is not preserved by the execution environment builder. Host config files are not edited. Review this process contract before use; see [safety](safety-and-permissions.md).

The separate legacy helper has its own `--home`, `--codex-home`, `--skills-dir` and installer options. Those are not runtime options. No config migration is attempted silently; a schema change requires an explicit new supported version.
