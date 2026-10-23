# Long work and Goals: converging on a finite outcome

This adds controls to the ordinary implementation/debugging route. It is not the default for
every task. A long ordinary chat can use checkpoints without starting native Goal mode.
Do not start, reset, edit or clear a native Goal unless requested and supported by actual tools.

## Scope contract

Capture requested outcome, protected behavior, explicit non-goals, evidence that counts as
completion, and external prerequisites. A goal such as "improve the whole app" is not a
finite verification target. Convert it to a small proposed milestone with observable value;
resolve product tradeoffs before treating a guess as authorization.

When acceptance is clear, do not turn it into a lengthy interview. Keep the contract stable.
New findings that are not blockers become deferred follow-ups, not an expanding backlog.

## Milestones and state

Work in observable milestones (for example reproduce -> minimal fix -> regression evidence),
not arbitrary token/time slices. Keep the current milestone with one owner; delegate only
independent ready work. Reuse an existing implementation-status/task file. If none exists,
use one `.codex-flow/tasks/<id>.md` checkpoint with the structure in resume.md.

Update that note after meaningful progress, a changed decision, a blocker, or before a
handoff/compaction. Do not rewrite it after every tool call. Keep only facts needed to resume:
criteria, decisions, actual files/base state, evidence, blocker, next exact action.
Do not open a second persistent ledger or generate a full architecture document unnecessarily.

## No-progress signals

Watch for repeated scans, unchanged failing commands, planning the same task again, helper
handoff loops, reinvestigating an accepted decision without new evidence, polishing beyond
acceptance, or repeated full verification with no code changes.

After two same-evidence failed attempts, change strategy: isolate a smaller reproduction,
inspect a different boundary, use one scoped second opinion, or surface the prerequisite
that is missing. This is a trigger to learn, not a rule to abandon a solvable problem.
Do not retry paid API calls, flaky network operations or full builds endlessly.

If execution cannot proceed safely, preserve the checkpoint and report BLOCKED or
IMPLEMENTED_NOT_VERIFIED, not DONE. Do not pretend to keep working asynchronously when no
runtime is executing. Do not alter Goal databases or internal session files.

## Budgets and controls

If the user supplies a budget, respect its actual meaning (wall time, spending, iterations,
or concurrency). Record actual measurements if available. Do not invent remaining tokens,
accurate runtime estimates, or a hard stop implemented by prose. A skill instruction is a
soft policy; hard time/spending limits require a supported runtime/control.

For an active native Goal, use the real pause/stop control when requested and available.
If no such control is available to the agent, tell the user to pause via the Goal progress
row or supported client control; say it has not been paused automatically. A checkpoint
file or a final text answer alone does not prove the scheduler stopped.

## Deliver

Stop once the agreed criteria and applicable checks are satisfied. Return results and
verification, then note any deferred non-blocking findings. If only a milestone is complete,
say exactly which one and what remains; do not label the whole Goal complete.
