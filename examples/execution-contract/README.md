# Sol chief and bounded Luna proposal

[Русский](README.ru.md)

The owner execution contract assigns one independent module proposal to Luna
medium. Sol XHigh writes the CLI, reviews and integrates the source once, and
remains the only file writer. The official sandbox acceptance checker verifies
the CLI and compares the saved proposal's AST with the integrated module.

Inspect without a model, filesystem scaffolding or execution:

```powershell
python codex-flow.py --repo examples/execution-contract run --task-file examples/execution-contract/task.md --execution-contract examples/execution-contract/execution.json --acceptance-file examples/execution-contract/acceptance.json --dry-run
```

Copy these four input files to a fresh project directory before a live run:
`task.md`, `execution.json`, `acceptance.json`, `verifier.py`. Review all inputs.
Then use the same `run` arguments with your absolute paths, an installed official
`--codex` executable and `--enable`, omitting `--dry-run`. This consumes the
existing ChatGPT subscription; no paid API fallback is used. Keep finite project
limits and preserve every attempt. The example intentionally contains no app.py
or core.py before generation.

Only observed native role usage, required artifacts and passing external checks
can yield acceptance. Declared scopes are logical ownership; helpers inherit
parent sandbox permissions. Presence of a saved proposal alone does not prove it
came from the child. This bounded example is not evidence of universal speedup.
