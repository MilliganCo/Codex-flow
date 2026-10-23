# Review: findings, not a second implementation

Establish the review target: working diff, staged changes, branch versus an explicit base,
or named files. Do not guess `main` when the repository uses another base. When no base is
specified, inspect working changes first; if none exist, ask for the review target rather
than auditing the whole repository. Include relevant new/untracked source files without
reading ignored secrets or generated directories.

Read acceptance criteria and the relevant code paths. Check correctness, compatibility,
data safety, security boundaries, edge cases, concurrency and meaningful test coverage.
Use project review instructions. Do not treat stylistic preferences as correctness failures.

A good finding contains:
- severity and concrete impact;
- file/symbol or precise location;
- the input/path that triggers it and supporting reasoning/evidence;
- a narrow correction or test suggestion.

Label uncertainty. Never invent a finding to justify the review. State "no material findings"
when warranted, with what was and was not checked. Static review alone is not a passed test.

For a broad risky diff, one separate native reviewer may add useful independence. Split by
concrete risk, not several reviewers all reading the same code with different job titles.
Use parallel.md for the delegation contract. If there is no subagent tool, perform a focused
review yourself and do not call it an independent review.

One focused review pass, then recheck changed findings after authorized corrections. Do not
cycle "review -> improve -> review" indefinitely or redesign adjacent modules. Preserve
remaining optional findings in the final response or the existing task ledger.

Review mode is read-only: do not auto-fix, format, stage, commit, push, or open PRs. Tests
may have side effects; use only the already-authorized test environment and disclose any
not-run checks. Switch to implementation only when the user requests fixes.
