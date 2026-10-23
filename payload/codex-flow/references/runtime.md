# Optional project-local runtime

The source repository includes `codex-flow.py`, a separate opt-in runtime extending
this workflow. It preserves the offline `scripts/flowctl.py` interface. The skill
installer does not install the runtime or modify the user's model/sandbox settings.

From a reviewed source checkout, use `python codex-flow.py --help`,
`python codex-flow.py doctor`, and `python codex-flow.py run "task" --dry-run`.
Execution requires `--enable` or explicit project configuration. Inspect the
repository README, configuration and safety documentation before enabling it.

The runtime uses the official ChatGPT-authenticated Codex CLI with workspace-write
sandbox, Sol XHigh and optional native helpers. Mercury uses an explicitly selected
external free-only adapter. The local optimizer is Harness2-inspired, not the
upstream executor. No paid API fallback is supported.

Do not infer filesystem read isolation from separate worktrees. Do not infer hard
depth/total-agent caps from instructions. Unknown usage is null, not zero. Runtime
completion needs independent acceptance. Keep global installation unchanged unless
the user separately asks to install a reviewed update.
