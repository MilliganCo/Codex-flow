# Checkpoint and resume

Prefer an existing project tracker. Otherwise use one `.codex-flow/tasks/<safe-task-id>.md`
per long task. Do not overwrite another session's checkpoint, use a shared global task file,
or infer that the most recent timestamp necessarily identifies the user's intended task.
If multiple plausible checkpoints exist and the user gave no task, list the short identifiers
and ask which one to resume. Read only the selected note initially.

Optional helper to create a new note (not needed to resume):

```text
python <skill-directory>/scripts/flowctl.py new-task --repo <repo> --id parser-fix --title "Parser fix"
```

The helper writes a NOT_STARTED note and a local ignore file. It does not implement or
verify anything, and refuses to overwrite an existing note. Without Python, create the
same structure with file tools after checking target paths and existing instructions.

## Checkpoint template

```markdown
# Task title
Task id: unique local identifier
State: IN_PROGRESS / BLOCKED / IMPLEMENTED_NOT_VERIFIED / DONE
Updated: actual timestamp if available
Branch/base: actual branch and HEAD; relevant pre-existing dirty changes

## Acceptance criteria and non-goals
The finite requested outcome; protected behavior.

## Current checkpoint
Completed milestone; actual changed files.

## Decisions and evidence
Chosen contract; decisive observations; rejected hypotheses and why.

## Work ownership
Actual helpers and their scopes/cwd; outstanding artifacts; no simulated agents.

## Verification
Command + cwd | observed outcome | timestamp/evidence | remaining limitation

## Blocker and next exact action
One concrete next experiment/edit/check; missing prerequisite if any.
```

Do not store hidden chain-of-thought, credentials, raw full logs or private context unrelated
to the task. A concise rationale and observable evidence are enough.

## Resume sequence

Compare the checkpoint to current branch/HEAD/working diff and relevant file content. A
checkpoint can be stale; Git state and current source are evidence, not permission to reset.
If changes conflict with another task/user's edits, pause before modifying them.

Reuse accepted decisions and successful checks when their inputs are unchanged. Rerun a
check only if relevant inputs/environment changed or its evidence was inadequate. Do not
restart a broad repository scan, reinstall dependencies, rebuild Graphify or generate a new
plan just because the chat is new.

Recover outstanding helper results through supported controls if still available. Otherwise
use their recorded artifacts; do not assume old workers are stopped or keep writing safely.
Continue at the next ready action and close with the ordinary verification/result contract.
