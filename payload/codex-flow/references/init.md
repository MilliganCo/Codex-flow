# Initialize this repository, not every repository on the computer

`init` authorizes a small local bootstrap for the current repository, not a product rewrite,
new dependencies, a new agent framework, global config edits, or changes in neighboring repos.
Confirm the actual project root from current working directory and Git metadata. Read existing
root/ancestor instructions; respect nested instructions for any directory being changed.

Read existing README and package/CI context only as needed. Use the helper for mechanical
scaffolding; it never runs package scripts or installs dependencies:

```text
python <skill-directory>/scripts/flowctl.py init --repo <absolute-repo-root> --attach
```

Use `--dry-run` to inspect proposed paths without writes. The helper:
- discovers manifests at the root and a bounded set of conventional app folders;
- creates `.codex-flow/PROJECT.md` only when missing;
- creates `.codex-flow/.gitignore` for transient tasks/reports/backups when missing;
- appends one marked instruction block to the effective root AGENTS file;
- preserves unrelated contents, makes backups, and is idempotent;
- refuses symlinks/junctions and non-Git locations rather than writing through them.

## Complete the context once

The generated profile is a starting point, not an inferred full architecture. Populate only
facts established from this repo: runtime/environment, important modules, protected contracts,
existing tracker, and actual test/type/lint/build commands with their sources.

Candidate commands are UNVERIFIED. Inspect what each does before execution: watch mode,
network, Docker, database resets, package installation, pre/post hooks or production effects.
When a command is verified, record the exact cwd, command, outcome and prerequisites.
Do not run the entire test suite merely to initialize instructions if it is expensive or
requires unauthorized services. Missing/unknown commands remain explicitly unknown.

For a monorepo, record only relevant packages at first. Do not recurse through all app
folders or every installed skill to create a universal architecture map.

Review existing orchestration rules for real conflicts. If Superpowers or another requested
workflow already provides planning/review/status, reuse those artifacts and do not bolt on a
second loop. Do not disable plugins or rewrite global instructions in this mode.

## Without Python

Use normal file tools. Preserve existing files and encodings; create a small PROJECT.md
with source-backed commands and UNVERIFIED unknowns; copy the short repository block from
assets/repo-instructions.md once into the effective root instruction file. Back up any file
you modify. Do not overwrite an AGENTS.override.md or assume AGENTS.md is active when the
override is non-empty. Treat links as boundaries and ask the user to use a physical path.

## Report and stop

List files created/changed, known commands, what still needs verification, any instruction
conflicts and how to invoke run/review/resume. The installed global skill already works
without bootstrapping. Do not start implementing a feature when the user only requested init.
