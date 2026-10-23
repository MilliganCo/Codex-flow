# Frequently asked questions

## Does this replace the existing Codex Flow skill?

No. The original `payload/codex-flow/` skill and offline `flowctl.py` remain separate and compatible. The new project-local runtime is entered through `python codex-flow.py` and is disabled until explicitly enabled.

## Does it install or switch the model globally?

No. Runtime process arguments request `gpt-6.1-sol` and `xhigh`. Host files are not rewritten. This profile is currently fixed; unsupported root values are rejected rather than silently substituted.

## Is Mercury included or paid through my ChatGPT subscription?

No. Mercury uses an explicitly selected external adapter and separate provider authentication. Its source and credentials are not redistributed. Only verified free-only calls are supported. The current bridge completed one real typed smoke with verified zero cost after forwarding the existing Windows system proxy to the Node child. Mercury still defaults to disabled. The frozen case study used an earlier bridge with zero successful calls; the later smoke cannot be counted as benchmark activity.

## Is this the upstream Harness² optimizer?

No. The local module is Harness²-inspired. It compares bounded measured proposals with safety/completeness gates and project-local adoption/rollback. The benchmark's probe metric is plan coverage, not final application quality. The upstream executor is not used.

## Are three agents and one delegation level hard guarantees?

The current CLI receives a concurrent-helper cap of three. Maximum total helpers, depth=1 and helper read-only ownership are instruction-only restrictions. Custom roles inherit parent permissions, so they have no separate hard read-only sandbox. A shared gateway budget caps inference requests at 80 including probes, but request counts do not establish agent identities.

## Does `max_attempts: 2` automatically retry a failed run?

No. The field is validated but the current wrapper executes one attempt, with automatic transport retries disabled. Failed artifacts remain available for inspection.

## Is the benchmark strictly isolated?

It uses separate worktrees with their own home, temp and cache directories plus project-local native SQLite/logs. Single-agent parents are ephemeral; parallel parents persist because native workers need their parent rollout. Authentication/rollout storage remains shared. Reciprocal Windows deny profiles interfered through shared ACLs, so all arms now use the same policy protecting existing evaluator/prior-solution paths. Current-peer reads remain a soft prohibition; isolation is explicitly degraded.

## Why are usage and cost values null?

Root CLI usage and gateway totals are separate. The nonce-protected loopback gateway forwards only to the fixed official subscription upstream and records requested model/effort, actual response model and usage. It totals usage only when every observed request completes with complete counters. Missing/incomplete totals and quota deltas stay `null`. Requests do not identify agents, and response metadata does not independently confirm reasoning effort. Subscription usage is not a paid API charge.

## Can I resume a runtime session or open a dashboard?

The runtime has neither feature. `runs show` reads metrics, `runs replay` summarizes events and `runs cancel` requests termination. The existing skill has conversational resume/checkpoint routes; they are not new runtime commands.

## Is this open source?

The repository is private and no project license has been selected. See [license options](license-options.md). References to upstream projects do not grant a license for this project's original code or permission to redistribute the external Mercury adapter.
