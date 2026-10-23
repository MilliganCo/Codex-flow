# Safety and permissions

The runtime is an opt-in executor, not a security boundary for untrusted source. Existing project rules and explicit authorization remain authoritative.

## Process contract

The default config has execution, Mercury and Harness-inspired optimization off. Actual `run` requires `--enable` or `enabled: true`. It uses a native `workspace-write` sandbox and does not pass sandbox-bypass flags. The adapter supplies process-local overrides and leaves host config files unchanged.

The noninteractive child requests approval policy `never`, shell-network access off and disabled hooks/plugins/apps/memory/discovery. These are meaningful execution-policy choices, not inherited host behavior. Review them before enabling the wrapper. A disabled approval prompt is not permission to perform an unauthorized action; permitted work remains bounded by the task and sandbox.

## Isolation limits

Each workspace gets separate home, temp and cache directories, while native `CODEX_HOME` remains shared for subscription credential reuse. No tokens are copied into the repository. Native ephemeral contexts avoid persistent benchmark chat reuse.

**A local boundary probe found sibling reads possible under `workspace-write`.** Worktrees provide independent writes and artifact locations, not strict read confidentiality. Do not run mutually untrusted or confidential tasks in adjacent directories and call this full isolation. The benchmark records degraded read isolation and instructs all agents not to inspect siblings/evaluators; instructions are not equivalent to an OS read barrier.

Native concurrent-helper limits are requested through the current CLI configuration. Depth=1 and total-helper limits are instruction-only; hard runtime enforcement is unverified. Ownership instructions and a sole integrator reduce conflicts but do not eliminate shared-filesystem risks.

## Authentication and external requests

Model generation uses the existing native ChatGPT subscription. API-key fallback is rejected. The wrapper does not open auth files and filters common secret-bearing environment names. Environment filtering is defense in depth, not proof that every possible secret name has been removed.

Mercury is separate: selecting a trusted external root allows its credential helper to supply a key only when explicitly enabled. The external adapter must retain provider/build/zero-price/zero-cost checks and prohibit paid fallbacks. The project does not bundle its source or credentials.

## Logs and artifacts

Telemetry is bounded and sanitized. It records event metadata, short summaries and available usage. Redaction is not a guarantee that arbitrary prose contains no private information. Review logs before sharing them. Do not publish native credential homes, installer manifests/backups, raw authenticated stderr, project secrets or hidden evaluator cases.

An exit code or `completed_unverified` state is insufficient acceptance. Inspect outputs and run relevant tests. Unknown metrics remain `null`. No routine browser launch or production action is needed to make a report appear complete.

See [security reporting](../SECURITY.md), [limitations](limitations.md) and [rollback](rollback.md).
