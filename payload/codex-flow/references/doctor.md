# Doctor: identify a bottleneck before prescribing an accelerator

Read-only by default. Do not alter config, model selection, plugins, credentials, permissions,
Goal state or project files. A folder inventory is not a trace of an actual slow session.
State which evidence exists and which timing/activation facts are unavailable.

## Bounded mechanical inspection

```text
python <skill-directory>/scripts/flowctl.py doctor --repo <repository>
```

Without `--repo`, this inspects only the user-level setup. The helper uses allowlisted
configuration facts/counts and instruction sizes/keyword counts. It intentionally does not
print full config, provider commands, URLs, environment variables or credentials. It only
counts immediate folders in the user `.agents/skills`, not every plugin or cached skill.
Its output is not a full registry of active plugins.

If Python is unavailable, inspect only known effective AGENTS files and allowlisted scalar
settings with ordinary read tools. Do not dump config to chat. Never read auth.json, token
stores, sessions, sqlite databases, caches or an entire home directory for this audit.

## Diagnose by evidence category

1. **Inference latency**: actual selected model, reasoning/intelligence level and client
   state. Higher reasoning can cost more time; a workflow prompt cannot change current
   generation speed. Suggest changes only with the user's quality and cost constraints.
2. **Work inflation**: repeated planning, broad scans, redundant agents, re-reading the
   same files, repeated full builds, expanding scope or endless review/fix cycles.
3. **Tool/environment wait**: observed test duration, watch processes, dependency installs,
   unavailable servers, network timeouts, approval prompts or resource contention.
4. **Instruction/discovery conflict**: effective AGENTS chain, explicit competing mandatory
   workflows, duplicate skills actually shown/loaded, or overly broad trigger descriptions.

Skill metadata is not the same as full skill content in context. A path under `.tmp`, a
marketplace checkout or plugin cache does not establish that a skill was active. Never blame
"thousands of plugins" based solely on a filesystem inventory or delete caches as a remedy.

For a concrete slow task, use supplied excerpts/timings or the user's selected current task
activity. Do not fetch all conversation/session histories. Classify time only when measured;
otherwise label the suspected cause a hypothesis and propose the smallest discriminating test.

## Actionable report

Return a small set of confirmed facts, likely bottleneck with confidence/evidence, and one
low-risk change to test first. For example: remove redundant planning from the next matching
task while holding model and verification fixed. Avoid changing everything simultaneously.

If a config change is needed, show an exact proposed diff, validate the current client schema,
and ask for authorization before applying it. This package's default installer never edits
config.toml, changes paid mode or disables existing plugins. Do not use `--yolo` or unrestricted
approvals as a performance fix. Optional role files are not guaranteed tool isolation when
the parent session overrides their defaults.
