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

The runtime requests `workspace-write`, never a bypass mode, and leaves host config files unchanged. It supplies a noninteractive `never` approval policy and disables shell-network access through process-local overrides. These do not authorize work beyond the task or provide full read confinement. A local test showed sibling reads possible. Native credential home remains shared; the wrapper does not copy tokens into the project. Environment filtering and log redaction are defensive measures, not guarantees against arbitrary secret formats.

The optional Mercury adapter root is a trust decision because external Python code is loaded for credential retrieval. Do not select an untrusted source tree. Disabled integration must remain side-effect free. No paid API fallback is supported.

## Verification expectations

Use focused offline tests and independent review for validated fixes. Preserve failure evidence and report untested paths. Do not disable sandboxing, copy credentials or run live attacks against unrelated systems merely to validate a suspected defect. Coordinate any external disclosure with the owner.
