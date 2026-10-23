# Known limitations

This list describes implementation boundaries, not missing evidence disguised as passing checks.

## Execution and coordination

- Root model/effort is fixed to Sol 6.1 XHigh. Metadata preflight does not prove inference availability.
- Independent-step counts are supplied by the caller; arbitrary task prose is not automatically converted into a validated dependency graph.
- Native concurrent-helper cap is requested; custom roles inherit parent permissions. Read-only ownership, total-helper and depth restrictions are instruction-only. Configured role models are not proof of actual helper execution.
- `max_attempts` is configurable but the current wrapper executes a single attempt. There is no general autonomous retry/refinement daemon.
- No runtime TUI, dashboard or resume command exists. JSON inspection and event replay are implemented.

## Security and environment

- Workspace permissions do not give full read isolation. Reciprocal Windows deny profiles interfere through shared `CodexSandboxUsers` ACLs; the benchmark uses identical existing-target denials protecting evaluator/prior solutions while current-peer reads remain soft/degraded. Future deny targets are rejected after the aborted case03.
- Native auth/rollout storage remains shared. Single-agent parents are ephemeral; parallel parents persist for worker rollouts. SQLite/logs are project-local, not a separate auth/rollout container. The environment builder uses the default credential home rather than a caller's custom `CODEX_HOME`.
- Task restrictions, ownership, depth guidance and redaction are not substitutes for OS access control or human review.
- Native CLI schemas and flags may change. Global configuration is not rewritten to compensate silently.
- Windows behavior is the primary environment under evaluation; portability requires platform-specific evidence.

## Integrations

- Mercury is external and optional. Current source passed one real free-only typed smoke after Windows system-proxy forwarding to Node; this is not a routing-accuracy or availability guarantee. It remains disabled by default. The earlier frozen benchmark still recorded zero successful calls and must remain degraded for Mercury.
- Free pricing/provider/build guarantees depend on the trusted external adapter's checks; no external provider implementation is bundled.
- The local optimizer is Harness²-inspired and measures plan coverage in its current experiment. It does not execute upstream Harness² or establish application-quality gains.
- Explicitly configured Harness-inspired probes add two planning calls before a normal run. Their plan-coverage metric does not establish final application quality; account for their overhead separately.

## Measurement and acceptance

- Gateway all-request usage is known only when every observed request completes with usable counters; it does not identify agents or independently confirm reasoning effort. Root usage is separate. Quota deltas and actual API cost may remain unknown.
- First-working-demo time is not automatically established by file creation or native completion.
- The benchmark runner freezes evaluator hashes but does not invoke the evaluator or perform blind interactive review automatically.
- Parallel runs contend for host/network/quota resources. One experiment cannot support general speed claims.
- Final quality requires independent evidence, including real 4D mathematics and runnable behavior; self-tests and changed frame bytes are insufficient alone.

The frozen case02 artifact scores A=95/B=97/C=95/D=96 coexist with zero successful Mercury calls and unconfirmed helpers. They do not validate a full-component performance gain. Case03 is aborted and immutable. Case04 started at 2026-10-23 14:00:48 UTC and has A/B running in this snapshot. Its requested-profile `multi_agent_verified` heuristic is insufficient worker proof; native collaboration and completed-request evidence must be assessed separately. Development-source fixes, including stdin-write cleanup, do not change that frozen runtime.

## Distribution

No project license has been chosen. Keep repository access private while ownership, distribution rights and the final license are reviewed. Original 1.2.0 reports remain historical records, not evidence that newly added runtime paths passed those earlier checks.
