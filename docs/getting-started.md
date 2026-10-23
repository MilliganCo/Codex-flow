# Getting started

Run these commands from the repository root. The project-local runtime and the existing global skill installer are separate interfaces.

## Prerequisites

- Python 3.11+; Python 3.12 is preferred for the Tree benchmark.
- An existing native [Codex CLI](https://github.com/openai/codex) supporting the flags used by `runtime/codex_flow/native.py`.
- An existing ChatGPT subscription login for actual model execution.
- Git for the legacy scaffolder and benchmark worktrees.

No runtime package installation is required. A model run requires network transport through the native CLI even though generated shell commands have network access disabled.

## Inspect before execution

```powershell
python codex-flow.py --help
python codex-flow.py doctor
python codex-flow.py doctor --deep
python codex-flow.py integrations status
python codex-flow.py run "Make the agreed small change" --dry-run
```

`doctor --deep` reads account class and model capabilities through an app-server metadata session. It does not generate text. `integrations status` reports configured flags with `validated: false`; a configured component may still be unusable.

If `codex` is absent from PATH, select the already installed executable with `--codex <executable>` before the command, or `CODEX_FLOW_CODEX`. Do not reinstall a user's CLI merely to pass a preflight.

## Execute one authorized task

```powershell
python codex-flow.py --repo <project> run "Implement the agreed small change" --enable --single-agent
python codex-flow.py --repo <project> runs list
python codex-flow.py --repo <project> runs show <run-id>
```

The run prints a JSON result. `completed_unverified` means a native turn completed successfully; independently inspect artifacts and run relevant tests before acceptance. Root usage and complete gateway totals are separate. A hard shared inference budget defaults to 80 including optional probes. Timeout and cancellation terminate the spawned process tree; cancellation is consumed at the wrapper polling boundary, so a request is not instantaneous completion.

For independent work, start with a reviewed dry run:

```powershell
python codex-flow.py --repo <project> run --task-file <task.md> --independent-steps 2 --max-agents 2 --dry-run
```

The integer is a caller-supplied independence hint, not source analysis. The coordinator owns application writes; generated helper roles gather evidence and inherit the parent's permissions. Their read-only/depth restrictions are instructions, not separate hard sandboxes. Parallel parents persist for native worker rollouts; SQLite/logs are project-local while native auth/rollouts remain shared. Review [isolation limits](safety-and-permissions.md) before using confidential workspaces, and preserve dirty files.

## Keep the original skill

```powershell
python payload/codex-flow/scripts/flowctl.py doctor
python payload/codex-flow/scripts/flowctl.py install --dry-run
```

Review installer output and existing managed-file customizations before a real installation. `--skill-only` and `--native-agents` are installer options; changing a previously recorded installation option requires deliberate migration. The runtime does not need global installation.

See [configuration](configuration.md) for exact defaults and [rollback](rollback.md) before changing an existing installation.
