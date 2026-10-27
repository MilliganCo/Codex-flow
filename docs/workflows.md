# Durable project workflows

[Русский](workflows.ru.md)

Use `workflow` to preserve progress across four stages:
`prepare → generate → verify → report`. Existing `run`, `verify`, `runs`, and
`benchmark` commands retain their separate behavior.

## 1. Inspect a task before enabling generation

Run from the Codex Flow checkout. Global options precede `workflow`:

```powershell
python codex-flow.py --repo C:\work\project workflow start "Implement the agreed change" --acceptance-file C:\checks\contract.json --dry-run
```

Supply either the task argument or `--task-file C:\checks\task.md`. An explicit,
owner-reviewed `--acceptance-file` is required. Its checker must be a reviewed,
self-contained Python file; see the [acceptance contract](acceptance-gate.md).
The dry run inspects local inputs without generation or checker execution.

An existing Git project, Python 3.11+, and the installed native Codex CLI are
required for execution. Generation needs the existing subscription login.
Verification requires the reviewed official Windows Codex command sandbox.
Workflow execution does not install packages, change global configuration, or
select a paid API fallback.

## 2. Start with fixed budgets

```powershell
python codex-flow.py --repo C:\work\project workflow start --task-file C:\checks\task.md --acceptance-file C:\checks\contract.json --enable --timeout 1200 --max-model-requests 40
```

Execution requires `--enable` or an enabled project configuration. `--timeout`
accepts 1–3600 seconds of active workflow time; `--max-model-requests` accepts
1–80 physical inference requests. These limits are frozen at creation.
An optional `--execution-contract C:\checks\execution.json` freezes an explicitly
selected execution topology; it does not grant extra permissions or budget.

The default is one Sol generation. Optional Luna execution modes remain
experimental and have no live validation for this workflow. Current workflow
evidence uses labelled test fixtures only; model execution remains paused.
No benchmark or quality advantage follows from fixture success.

## 3. Inspect, pause, resume, or cancel

Use the returned workflow ID:

```powershell
python codex-flow.py --repo C:\work\project workflow status WORKFLOW_ID
python codex-flow.py --repo C:\work\project workflow pause WORKFLOW_ID
python codex-flow.py --repo C:\work\project workflow resume WORKFLOW_ID --enable
python codex-flow.py --repo C:\work\project workflow cancel WORKFLOW_ID
```

Pause and cancel are persisted control requests; an active operation must observe
them before it stops. Paused time does not consume the active-time budget.
Resume needs `--enable` or a currently enabled project configuration. Turning
project enablement off stops new CLI execution; frozen parameters alone do not
authorize a new model run.
It accepts no replacement budgets, task, checker, or execution contract.
Cancellation is terminal. Completed workflows preserve their original evidence.

Resume rechecks frozen inputs, runtime identity, cached receipts, and file hashes.
A valid completed stage is reused. Each stage allows at most two attempts,
started through explicit execution/resume; there is no automatic workflow retry
loop or automatic model/HTTP 429 replay. An unchanged semantic verification
failure is terminal. Interrupted attempts retain their evidence in separate paths.
If the budget or attempt limit is exhausted, create a separately authorized task.

## 4. Understand files and durable state

Project state lives under `.codex-flow/workflows/`. SQLite `state.sqlite` is the
authority for stages, control requests, ownership, requests, and time accounting.
JSON receipts and traces are diagnostic evidence; editing them cannot grant
permissions, restore budget, or mark a stage accepted.

`prepare` snapshots the current bytes of Git-tracked files and nonignored
untracked files, including dirty changes. Tracked files deleted from the working
tree remain absent. Ignored dependencies are not traversed for source snapshots.
Control directories `.git`, `.codex-flow`, `.codex`, `.agents`, `.home`, `.tmp`
and credential filenames are excluded. Credential exclusions include `.env`,
`.env.*` except `.env.example`, `auth.json`, `credentials.json`, `*.key`, `*.pem`.

Snapshots reject links, reparse points, multiply linked regular files, path
escapes, case aliases, Windows device names, and trailing-dot/space aliases.
Limits are 10,000 files, 256 MiB total, and 64 MiB per file; overflow fails
explicitly. Manifests bind relative paths, SHA-256, byte counts, and POSIX
executable bits where supported. Source and snapshot integrity are rechecked.

`generate` starts from the frozen seed in a fresh attempt directory. Its local
Git metadata is initialized with empty templates and hooks/fsmonitor disabled.
Git metadata commands do not run checkout filters, textconv, or project hooks.
The workflow does not apply generated changes to the original project.

`verify` runs the frozen checker through the official command sandbox. The
attempt workspace is read-only and scratch output is writable; the host does
not import or execute generated application or checker code. Check failure,
invalid evidence, drift, or exhausted budgets prevents acceptance.

`report` creates a review bundle with the complete exact result tree in `files/`,
`manifest.json`, `seed-manifest.json`, `diff.patch`, and `report.json`. The report
lists added, changed, and deleted paths. Text diff input and output are capped at
1 MiB per file and the complete diff is capped at 8 MiB. Large or binary files
and exhausted diff space receive bounded summaries; `text_diff_limited` records
this. Exact result bytes always remain in `files/` with their manifest hashes.
The diff is for review and is not guaranteed to be applyable. No patch is applied
upstream.

## 5. Read budget and recovery evidence correctly

Each physical model request is durably reserved before forwarding. Failed,
unknown, and interrupted requests consume reservations; resume does not reset
them. Known usage records may refine evidence, but cannot refund a reservation.

Active time uses 30-second reservations with a 5-second heartbeat. Clean progress
settles observed time. After an owner crash, an unknown outstanding quantum is
forfeited conservatively; restart does not recreate its budget.

Only one workflow owner can run per project. Ownership binds a PID and its
creation identity. Recovery blocks while an owner or registered child may still
be alive, including unknown process state; it does not kill foreign processes.
Investigate the recorded owner/child before requesting another resume.

`accepted` establishes the frozen owner's declared checks for the preserved
bundle. It does not establish that the live original project now passes them.
`source_project_updated` remains false; the report's `source_changed_since_start`
flags independent changes to the original source since the seed was captured.
Inspect `backend_kind` to distinguish fixture evidence from native execution.

These are owned snapshot directories, not Git worktrees. They do not establish
complete host-read confidentiality, independent descendant-termination proof,
comprehensive test coverage, or an observed speed/quality gain. The native
platform's [isolation limits](safety-and-permissions.md) still apply.

## Verified recovery controls

[Two real crash controls](../benchmarks/workflow-recovery-20261027/README.md)
passed with the portable no-model fixture generator and real Windows SDK. Each
workflow retained one generator invocation and one request reservation across
resume; all eight configured checks passed. Report-only recovery made no new SDK
call. The original project retained its independent manual edit.

An unresolved pre-spawn launch intent blocks recovery even if the owner died.
It is not cleared by guessing a PID or killing unrelated sessions. Internal
attempt paths are compact to reduce Windows launcher path growth.
