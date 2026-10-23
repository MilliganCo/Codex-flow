# Parallel work: independence before headcount

## Gate

Delegate only if there is an independent, bounded work item and the host actually exposes
subagent tools. For a small fix, sequencing usually needs less coordination. The package's
starting point is one coordinator plus up to two helpers, not a demand to fill slots.
Increase concurrency only for a clear independent workload and within user/runtime limits.

Useful patterns: investigate two unrelated root-cause hypotheses; map an unfamiliar module
while the coordinator implements a different known path; review a ready diff independently.
Use one writer plus read-only helpers as the conservative default.

Do NOT parallelize a dependency chain, incompatible alternative implementations, unsettled
shared interfaces, changes to the same file, or tests using a shared database/port/cache.
Reserve contract files, generated output, lockfiles and migrations to one named owner.

## Capability check

Use native subagents, not nested `codex exec` processes or a new external framework.
If native tools are unavailable, do the work sequentially and say so. Never describe several
internal perspectives as independent agent runs. Optional `cf-explorer`, `cf-reviewer` and
`cf-worker` roles may be used if actually discovered; otherwise use native built-in roles
with the same explicit contract. Do not reconfigure the user's installation mid-task.

## Worker contract

Send a self-contained brief; avoid forwarding the whole chat or unrelated private context.
Use the host's available isolation controls; do not invent unsupported spawn parameters.

```text
Task: one concrete deliverable
Acceptance: what must be demonstrated
Allowed scope: exact module/files; READ_ONLY or WRITE
Forbidden scope: shared interfaces, lockfiles, migrations, unrelated dirty files
Workspace: absolute path; confirm your actual cwd before any write
Dependencies: stable inputs already available; what is not ready
Evidence: exact files/symbols or commands/results
Completion: stop when this deliverable is met; no further delegation
Return: result, changed files, tests/results, blocker/risks; normally <=250 words
```

Read-only means no file writes or test commands with mutable side effects. A sandbox default
is not a complete security guarantee; live parent overrides and external tools may differ.
Use permission boundaries and explicit write restrictions together. Do not relax sandbox or
approval policy to unblock a helper.

## Worktree safety

An agent thread is not automatically a separate Git working tree. Before multiple writers:
confirm isolated paths, correct base commit, disjoint ownership and an integration strategy.
Use an existing verified app worktree or explicitly authorized Git worktree mechanism.
If the host cannot reliably direct each writer to its worktree, serialize all writes.

Git worktrees share repository history, not uncommitted changes. Do not assume a new worktree
contains the coordinator's dirty edits. Never stash/reset/commit those edits automatically.
Agree on a clean or explicitly staged source-of-truth snapshot; otherwise keep one writer.

Isolation does not separate databases, ports, external services, test fixtures or build caches.
Account for those resources too. A worktree prevents simultaneous filesystem edits but does
not prevent semantically incompatible designs or merge conflicts.

## Coordinator discipline

Do useful unassigned work while helpers run, or wait using the native tool; do not repeatedly
poll status or repeat the same investigation. Steer once when a helper is off scope. Close
completed helper threads when supported. Do not leave a helper writing after final delivery.

Review actual returned artifacts; a worker's "done" is not verification. Integrate serially
into the intended working tree under normal user authorization. Never auto-merge, commit,
push or cherry-pick merely because the helper finished. Run applicable combined checks once.

When a helper fails, reuse its evidence and narrowed blocker. Don't create three new agents
with the same broad prompt. Recover with a better local experiment or continue sequentially.
