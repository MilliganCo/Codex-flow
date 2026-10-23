# Safety and permissions

The runtime is an opt-in executor, not a security boundary for untrusted source. Existing project rules and explicit authorization remain authoritative.

## Process contract

The default config has execution, Mercury and Harness-inspired optimization off. Actual `run` requires `--enable` or `enabled: true`. It uses workspace-based native permissions and does not pass sandbox-bypass flags. When read denies are supplied, a named profile extends `:workspace` rather than the plain `--sandbox workspace-write` flag. The adapter supplies process-local overrides and leaves host config files unchanged.

The noninteractive child requests approval policy `never`, shell-network access off and disabled hooks/plugins/apps/memory/discovery. These are meaningful execution-policy choices, not inherited host behavior. Review them before enabling the wrapper. A disabled approval prompt is not permission to perform an unauthorized action; permitted work remains bounded by the task and sandbox.

## Isolation limits

Each workspace gets separate home, temp/cache and physical native SQLite/log paths, while native `CODEX_HOME` remains shared for subscription credential reuse and native rollout storage. No tokens are copied into the repository. Single-agent parents are ephemeral; parallel parents **are not ephemeral**, because native workers require a persisted parent rollout.

**Project-local storage is not isolated native state.** The CLI can rehydrate thread metadata from the shared rollout container into the local SQLite database; unrelated historical working-directory metadata was observed there. Separate log paths likewise do not establish independently scoped native context or log contents. This is a platform blocker for strict independent profiles, not a claim that actual cross-arm solution reading occurred. An audit restricted to each execution's own native sessions remains pending until A/B reaches a terminal state. Do not query broad shared history to investigate it. Never publish native databases, SQLite journals/WAL files or raw native logs.

**A local boundary probe found sibling reads possible under `workspace-write`.** Explicit single-target read denies worked, but reciprocal Windows profiles interfered through the shared `CodexSandboxUsers` ACL. Consequently, all benchmark arms receive the same deny policy for existing hidden-evaluator, prior-solution and additional protected paths. Current-peer read isolation remains soft: agents must not read peers, but that prohibition is not a hard physical boundary. The experiment records degraded read and shared-state isolation. Do not use it for mutually untrusted confidential work.

Deny targets must already exist. In the aborted case03, Windows SDK materialized future targets as directories; that frozen experiment is preserved and excluded rather than repaired in place. Do not add reciprocal/future deny paths during an active run.

Native concurrent-helper limits are requested through the current CLI configuration. Custom helper roles inherit parent permissions; their read-only ownership, depth=1 and total-helper limits are instruction-only. They do not have independently enforced read-only sandboxes. A sole integrator reduces conflicts but does not eliminate shared-filesystem risks.

## Authentication and external requests

Model generation uses the existing native ChatGPT subscription. Native CLI authentication is forwarded in memory through a loopback gateway protected by a fresh per-run nonce. The gateway binds only `127.0.0.1`, forwards models/responses only to the fixed official subscription upstream, disables redirects and rejects API-key-style credentials. It has no configurable external upstream or paid fallback. The local nonce is not forwarded upstream.

A shared locked budget allows at most 80 inference requests across probes/root/gateway-routed helpers; a rejected validation request is not an inference completion. Request and response sizes are bounded. Raw authenticated bodies/headers are not written to logs. The wrapper does not open auth files and filters common secret-bearing environment names. These measures are not proof against every secret format or a compromised process already running as the user.

Mercury is separate: selecting a trusted external root allows its credential helper to supply a key only when explicitly enabled. The external adapter must retain provider/build/zero-price/zero-cost checks and prohibit paid fallbacks. The project does not bundle its source or credentials. On Windows, the current bridge can forward the user's existing configured system proxy to the Node child using `--use-env-proxy`; it does not create a new proxy, edit global settings or log proxy values. This child-provider connection is distinct from the native generated shell's network restrictions.

## Logs and artifacts

Runtime telemetry is bounded and sanitized; this does not describe raw native databases or logs. It records event metadata, short summaries, requested model/effort and actual response model/usage. Reasoning effort is not independently echoed by the response. Complete all-request totals require every observed request to complete with usage; request counts do not identify worker agents. Redaction is not a guarantee that arbitrary prose contains no private information. Review allowed exports before sharing them. Do not publish native databases/journals, raw native logs, auth/rollout containers, installer manifests/backups, raw authenticated stderr, project secrets or hidden evaluator cases.

An exit code or `completed_unverified` state is insufficient acceptance. Inspect outputs and run relevant tests. Unknown metrics remain `null`. No routine browser launch or production action is needed to make a report appear complete.

See [security reporting](../SECURITY.md), [limitations](limitations.md) and [rollback](rollback.md).
