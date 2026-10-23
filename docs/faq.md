# Frequently asked questions

## Does this replace the existing Codex Flow skill?

No. The original `payload/codex-flow/` skill and offline `flowctl.py` remain separate and compatible. The new project-local runtime is entered through `python codex-flow.py` and is disabled until explicitly enabled.

## Does it install or switch the model globally?

No. Runtime process arguments request `gpt-6.1-sol` and `xhigh`. Host files are not rewritten. This profile is currently fixed; unsupported root values are rejected rather than silently substituted.

## Is Mercury included or paid through my ChatGPT subscription?

No. Mercury uses an explicitly selected external adapter and separate provider authentication. Its source and credentials are not redistributed. Only verified free-only calls are supported. The initial Node shutdown problem was fixed, but the subsequent free-only smoke was rejected with HTTP 403, zero inference attempts and zero successful calls. Fallback remains deterministic until valid live evidence establishes otherwise.

## Is this the upstream Harness² optimizer?

No. The local module is Harness²-inspired. It compares bounded measured proposals with safety/completeness gates and project-local adoption/rollback. The benchmark's probe metric is plan coverage, not final application quality. The upstream executor is not used.

## Are three agents and one delegation level hard guarantees?

The current CLI receives a concurrent-helper cap of three. Maximum total helpers and depth=1 are instruction-only restrictions; hard runtime enforcement is unverified. Native helper execution, filesystem isolation and per-helper usage require actual evidence. Helpers share the workspace unless separately isolated.

## Does `max_attempts: 2` automatically retry a failed run?

No. The field is validated but the current wrapper executes one attempt, with automatic transport retries disabled. Failed artifacts remain available for inspection.

## Is the benchmark strictly isolated?

It uses separate worktrees, ephemeral native contexts and workspace home/temp/cache directories. It shares credential home for native login reuse and does not copy tokens. A boundary probe showed sibling reads are possible under `workspace-write`, so reports explicitly state degraded read isolation.

## Why are usage and cost values null?

The native stream exposes some root usage but not reliable aggregate helper usage or quota deltas. Unknown is `null`. Subscription usage is not an actual paid API charge, and no API-equivalent estimate is presented as spending.

## Can I resume a runtime session or open a dashboard?

The runtime has neither feature. `runs show` reads metrics, `runs replay` summarizes events and `runs cancel` requests termination. The existing skill has conversational resume/checkpoint routes; they are not new runtime commands.

## Is this open source?

The repository is private and no project license has been selected. See [license options](license-options.md). References to upstream projects do not grant a license for this project's original code or permission to redistribute the external Mercury adapter.
