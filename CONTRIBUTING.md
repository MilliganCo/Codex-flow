# Contributing

This is a private development repository with no selected project license. Coordinate access and distribution with the owner before sharing source or artifacts. Do not assume that repository access grants redistribution rights.

## Make a bounded change

1. Read applicable project instructions and identify exact acceptance criteria and owned files.
2. Preserve existing dirty work and the legacy installer/skill contracts. Prefer one writer; helpers need explicit independent ownership.
3. Implement the smallest change and add meaningful verification for changed behavior.
4. Inspect the final combined diff and run the relevant finite checks. Report passed, failed and not-run results accurately.
5. Submit a reviewable description with behavior, evidence and limitations; keep private paths, credentials and raw authenticated traces out of the change.

Run the offline suite from the repository root:

```powershell
python -m unittest discover -s tests -v
```

Tests should use disposable homes/workspaces and injected provider runners. CI and ordinary tests must not call paid APIs, authenticate external accounts, invoke live model generation or mutate a user's global setup. Live integration experiments require separate explicit authorization and immutable manifests.

## Compatibility and safety

Do not rewrite `payload/codex-flow/scripts/flowctl.py` or managed installation behavior for an unrelated runtime change. Preserve marker protections, ownership validation, encoding, local customizations, targeted backups and rollback. No silent model substitution, sandbox bypass, provider fallback, dependency installation or global reconfiguration.

Keep integration labels honest: local plan probes are Harness²-inspired; the external Mercury adapter is not bundled. A configured component is not validated until evidence establishes it. Preserve the loopback gateway's fixed upstream, nonce checks and shared request budget. Requested effort, actual response model/usage and agent identities are separate evidence. Unknown usage remains null, and subscription usage is not an API billing estimate.

## Benchmark independence

Executors must not inspect sibling solutions or evaluator files. Freeze task, scaffold, evaluator/rubric and runtime versions before starting. A changed condition creates a new experiment ID. Reviewers should use anonymous solution labels until scores and evidence are recorded. Do not cherry-pick the best pieces across arms during a run.

For security findings, follow [SECURITY.md](SECURITY.md). Changes to distribution rights require a separate owner-reviewed license decision.
