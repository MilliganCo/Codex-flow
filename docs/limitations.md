# Known limitations

This list describes implementation boundaries, not missing evidence disguised as passing checks.

## Execution and coordination

- Root model/effort is fixed to Sol 6.1 XHigh. Metadata preflight does not prove inference availability.
- Independent-step counts are supplied by the caller; arbitrary task prose is not automatically converted into a validated dependency graph.
- Native concurrent-helper cap is requested; total-helper and depth restrictions are instruction-only. Hard depth enforcement and individual review-helper reasoning overrides are unverified.
- `max_attempts` is configurable but the current wrapper executes a single attempt. There is no general autonomous retry/refinement daemon.
- No runtime TUI, dashboard or resume command exists. JSON inspection and event replay are implemented.

## Security and environment

- `workspace-write` is not full read isolation. A sibling sentinel could be read in a local boundary probe.
- Shared native credential home preserves login without token copying but weakens claims of fully separate profiles. The environment builder uses the native default credential home rather than a caller's custom `CODEX_HOME`.
- Task restrictions, ownership, depth guidance and redaction are not substitutes for OS access control or human review.
- Native CLI schemas and flags may change. Global configuration is not rewritten to compensate silently.
- Windows behavior is the primary environment under evaluation; portability requires platform-specific evidence.

## Integrations

- Mercury is external and optional. The Windows Node shutdown issue was fixed; the subsequent free-only smoke was rejected with HTTP 403, zero inference attempts and zero successful calls. Configured/available/validated must remain separate.
- Free pricing/provider/build guarantees depend on the trusted external adapter's checks; no external provider implementation is bundled.
- The local optimizer is Harness²-inspired and measures plan coverage in its current experiment. It does not execute upstream Harness² or establish application-quality gains.
- Explicitly configured Harness-inspired probes add two planning calls before a normal run. Their plan-coverage metric does not establish final application quality; account for their overhead separately.

## Measurement and acceptance

- Aggregate helper tokens, subscription quota deltas and actual API costs may be unknown. Root metrics do not represent complete multi-agent spending.
- First-working-demo time is not automatically established by file creation or native completion.
- The benchmark runner freezes evaluator hashes but does not invoke the evaluator or perform blind interactive review automatically.
- Parallel runs contend for host/network/quota resources. One experiment cannot support general speed claims.
- Final quality requires independent evidence, including real 4D mathematics and runnable behavior; self-tests and changed frame bytes are insufficient alone.

## Distribution

No project license has been chosen. Keep repository access private while ownership, distribution rights and the final license are reviewed. Original 1.2.0 reports remain historical records, not evidence that newly added runtime paths passed those earlier checks.
