# Run: implementation without process inflation

## Start from the request and current state

Read applicable instructions and any relevant existing project context. Do not launch a
setup audit at the start of each task. When using Git, establish the working directory and
existing dirty changes once; avoid printing large diffs or all untracked/generated files.
Do not change directories, branches or worktrees merely because an orchestration exists.

For a tiny, clear change, proceed directly to the edit and relevant check. For larger work,
state a short contract: observable outcome, protected behavior, scope/non-goals, and how
success will be checked. Reuse decisions and requirements already supplied. Resolve facts
from code or docs before asking the user. Ask only for a genuinely blocking product,
security, compatibility or destructive-action decision; do not repeatedly request permission
to do the requested task. Do not implement when the user asked only for a plan.

## Explore only what changes the decision

Start at a likely entry point or failing test and trace the needed dependency path. Prefer
symbol searches and targeted file reads. Exclude build output, environments, dependencies,
generated files, graphs and caches unless that exact artifact is the target.

Before broad exploration, produce a useful piece of evidence: a reproducible error, the
relevant code path, a failing test, or a small runnable vertical slice. A large listing is
not evidence of progress by itself. Keep long command output in a task-local log and return
the relevant excerpt, without secrets.

Existing Graphify output is optional navigation. Use it when the question concerns impact,
indirect dependencies or a confusing large codebase. Check index age/scope and verify
critical graph claims in current source. For a local fix, ordinary search is sufficient.
Do not perform a full graph rebuild unless it is needed and authorized.

## Plan by dependencies, not by job titles

Use a short 3–6-step plan when helpful; use the current session plan tool instead of making
a new document for every task. Identify the dependency that blocks the next useful check.
Keep that dependency with the coordinator or one worker. Delegate independent research or
implementation only after reading parallel.md. "Frontend / backend / tests" is not proof
of independence when the API contract is unsettled.

Do not spawn a planner to plan another planner. Do not assign a reviewer implementation
that is not ready. Do not run two model implementations just to choose a favorite unless
comparison is the actual user request.

## Implement a testable slice

Follow project conventions. For behavioral fixes add or adjust a regression test when
practical; follow an existing TDD requirement. Do not create a new testing framework solely
for a trivial stylesheet or text correction. If no automated test applies, give a concrete
manual/smoke check and report that limitation.

Keep new abstractions and dependencies proportional to actual requirements. Preserve public
interfaces unless changing them is authorized. Validate error handling and boundary cases,
not just the happy path. Use the repository's existing environment and lockfile strategy.

## Verification ladder

1. Run the smallest applicable check during development so defects surface early.
2. After integration, run affected tests and relevant lint/type/build checks.
3. Run the repository-required full suite at final integration. If a full suite is not
   required, choose additional regression coverage by impact and risk. Do not make each
   helper repeat the entire suite. Do not rerun an unchanged full suite after note-only edits.
4. Inspect the final diff, including staged and unstaged changes and newly created relevant
   files. Compare against the initial dirty state; do not attribute user changes to yourself.
5. For UI/frontend changes, *do not automatically launch Playwright or a browser*.
   Prefer component tests, existing integration tests, typecheck/lint and focused source
   checks. A build alone does not prove user-visible behavior, so identify what the
   chosen checks actually establish. Escalate to browser testing only if explicitly
   requested, mandated by repository/CI/release instructions, or indispensable to
   validating browser-only behavior or a changed high-impact user journey. Apply the
   necessity gate in `browser.md` BEFORE choosing an engine. For skipped optional E2E,
   say "NOT_RUN — browser verification not required" if reporting test scope.

Choose finite test invocations. A watcher/dev server still running is not a completed test.
Treat timed-out runs, zero collected tests, unavailable browsers, missing secrets and failed
external services as explicit limits; never silently downgrade them to PASSED.

Track known baseline failures separately, with evidence. Do not fix unrelated failures
without scope authorization, and never claim the full suite is green while they remain.

## Finish

The result is complete when requested behavior works, required checks are accounted for,
and no material blocker is concealed. Do not add a second broad audit/review pass after a
focused clean review unless new changes or evidence justify it. Stop building when acceptance
is met. Give a short delivery summary with files, command results and actual remaining risks.
