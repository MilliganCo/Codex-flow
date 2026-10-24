# Rollback

Preserve current artifacts and local edits before restoring anything. Runtime shutdown, local proposal rollback and global skill uninstall are different operations. None requires disabling the host sandbox.

## Before the terminal-aware stream change

The previous private `main` commit is
`4b5fddd3e18514a379b30d3cbb513dd20b9d1d44`. Recover it into a new directory:

```powershell
git worktree add --detach ../codex-flow-before-stream-fix 4b5fddd3e18514a379b30d3cbb513dd20b9d1d44
```

The development backup `before-terminal-stream-fix-20261024.bundle` separately
preserves the pre-change development history. Keep that bundle local. Do not
publish its history or use it to overwrite an active checkout.

The stream parser and helper-proposal policy are project code. Restoring this
checkout requires no global configuration, skill, MCP or sandbox changes. Keep
the fixed experiment sources, failures and independent evaluations as evidence.

Для отката исправления чтения создайте отдельный каталог командой выше. Она
сохраняет текущие правки и результаты. Глобальные настройки и sandbox не меняются.

To inspect the previous coordination policy while keeping the terminal-aware
reader, use its exact retained runtime for a dry run from the repository root:

```powershell
python benchmarks/stream-suite-20261024-01/frozen-runtime/codex-flow.py --repo <project> run "Describe the task" --dry-run
```

This invokes the frozen source-`6c30bbe` runtime without overwriting current code
or installing a global skill. Review its plan before any explicit execution.

## Stop a runtime execution

```powershell
python codex-flow.py --repo <project> runs list
python codex-flow.py --repo <project> runs cancel <run-id>
python codex-flow.py --repo <project> runs show <run-id>
```

Cancellation writes a request consumed by the owning wrapper, which terminates its process tree. Verify the final status and actual process exit; a request alone is not proof of termination. Keep `events.jsonl`, `metrics.json`, diagnostics and produced source for diagnosis.

For future runs, omit `--enable` and set project `enabled` to false. Set `mercury` and `harness2` false as well. No global host config change is needed. Event replay is read-only and never restarts a task.

## Restore a local instruction proposal

`GuardedHarness.rollback(proposal_id)` is a Python library method, not a CLI command. It reads the stored proposal record and restores the previous project-local active text only when the current hash matches the adopted hash. If someone edited that text, rollback refuses to overwrite their work.

An operator using the library must pass the same project root and reviewed proposal ID. Inspect `.codex-flow/lessons/proposal-<id>.json` and its recorded previous text locally. Do not share these files without reviewing them. There is no command named `codex-flow rollback` in the current runtime.

## Existing global skill installation

The unchanged offline installer owns its manifest and targeted backups. Start with:

```powershell
python payload/codex-flow/scripts/flowctl.py uninstall --dry-run
```

Use the same physical `--codex-home`/`--skills-dir` choices used at installation. Inspect the listed files and preserve any local edits. Only after review, execute the same uninstall without `--dry-run`. The helper restores/removes only owned files and preserves text outside its managed global block. Edited managed content may cause a safe refusal; reconcile it instead of deleting the manifest or forcing replacement.

Backups and installation records may contain private instructions. Keep them local. Project `.codex-flow` data is separate from global uninstall and is not automatically erased.

## Restore source

Before the live-budget/MCP change, the private repository's reviewed commit is
`aa9cd7a2c85b5b2bce11c6e26e4e3042c3920160`. Keep the current checkout and recover
into a new directory:

```powershell
git worktree add --detach ../codex-flow-before-budget aa9cd7a2c85b5b2bce11c6e26e4e3042c3920160
```

Budget MCP configuration is per process and disappears when that native process
exits. No global MCP uninstall/config restore is required. Preserve the owned run
directory and its status/audit evidence. The local pre-change Git bundle retains
development commit `b1fc69a90e4ec6a4c2c30b0d5d038ac72db5fdf8`.

Для отката изменений бюджета/MCP используйте команду выше: она создаёт отдельный
каталог со старой версией и сохраняет текущие исходники, результаты и локальные
правки. Глобальные настройки и sandbox не меняются.

For a non-destructive recovery from the case06 orchestration change, the private
repository's previous reviewed commit is `5f9fe86847ca412abe227d4c35071307a8a1cdb1`.
From your clone, create a new, previously unused recovery directory:

```powershell
git worktree add --detach ../codex-flow-before-case06 5f9fe86847ca412abe227d4c35071307a8a1cdb1
```

Run the older entrypoint from that separate checkout after reviewing its settings.
This preserves current source, the new experiment and all local edits. It does not
install/uninstall the global skill or change any host sandbox configuration. The
local development backup also records source commit
`51fd9bb6f1b2ac85552cfc57092cec32f51cc6ba` in the verified pre-repeat Git bundle.

Для отката после case06 создайте отдельный каталог приведённой командой и
проверьте настройки перед запуском старого entrypoint. Текущие исходники и
результаты экспериментов сохраняются; глобальная установка не меняется.

Use the recorded pre-change source snapshot or a known reviewed Git commit in a separate recovery checkout. Compare with current dirty changes before applying selected files. Do not run `git reset --hard`, `git clean`, bulk directory deletion or blind backup restore against a user's active workspace. A proposed restore should identify exact paths and preserve current changes first.
