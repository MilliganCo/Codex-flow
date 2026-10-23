# Security policy

This private development project has no published security support SLA. Security fixes should be coordinated with the repository owner; no release is represented as independently certified.

## Report privately

Use the repository's private vulnerability-reporting channel if the owner has enabled it. Otherwise agree on a private channel with the owner before sharing sensitive details. Do not place credentials, auth files, private instructions, raw authenticated stderr or exploit-bearing customer data in an ordinary issue or public discussion.

Include the affected commit/version, exact component, platform, minimal reproducible conditions, expected/actual behavior and impact. Use synthetic data where possible. Distinguish observed exploitation from a hypothetical path.

## Areas requiring particular care

- Native CLI process arguments, sandbox configuration, cancellation and secret-bearing environment handling.
- External adapter trust, credential loading, provider/build validation and free-only billing checks.
- Installer ownership/path validation, managed-block preservation, backup/rollback and symlink/junction behavior.
- Telemetry redaction and accidental publication of private artifacts.
- Benchmark cross-workspace reads and false claims of filesystem or account isolation.

## Known security boundaries

The runtime uses workspace-based native permissions, never a bypass mode, and leaves host config files unchanged. Explicit denies use a named profile extending `:workspace`. It supplies a noninteractive `never` approval policy and disables shell-network access through process-local overrides. These do not authorize work beyond the task or provide full read confinement.

The loopback subscription gateway requires a fresh per-run nonce, has a fixed official upstream with redirects disabled, rejects API-key-style credentials and enforces a shared inference-request budget of at most 80. Native authentication is forwarded in memory; it is not copied into the project or logged. Request/response bounds and sanitized metadata reduce exposure without making the gateway safe against a compromised local process.

Single-agent parents are ephemeral; parallel parents persist because workers need their rollout. Native SQLite/logs are project-local, while authentication/rollout storage is shared. Custom helper roles inherit parent permissions: read-only ownership and depth are instruction-only. Reciprocal Windows deny profiles interfered through shared `CodexSandboxUsers` ACLs; current benchmark arms use an identical existing-target policy protecting evaluator/prior solutions. Current-peer reads remain soft/degraded. Missing protected targets are rejected after case03 created directories and was aborted. Environment filtering and redaction are defensive measures, not guarantees against arbitrary secret formats.

The optional Mercury adapter root is a trust decision because external Python code is loaded for credential retrieval. Do not select an untrusted source tree. Disabled integration must remain side-effect free. No paid API fallback is supported.

## Verification expectations

Use focused offline tests and independent review for validated fixes. Preserve failure evidence and report untested paths. Do not disable sandboxing, copy credentials or run live attacks against unrelated systems merely to validate a suspected defect. Coordinate any external disclosure with the owner.
