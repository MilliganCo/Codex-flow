# Workflow setup: real sandbox controls

[Русский](README.ru.md)

Verified on Windows on 2026-10-27, using the reviewed installed Codex CLI
0.164.0-alpha.11.1. **No real model calls and no host execution of application or
checker code.** This is infrastructure validation, not a model benchmark.

All 14 predeclared acceptance controls matched their expected outcomes:

| Controls | Result |
| --- | --- |
| Correct application; added test file | Accepted; 1 and 2 actual passes |
| Incorrect application; changed baseline test | Rejected |
| Empty suite; all tests skipped | Rejected, including an explicit skip allowance |
| Mixed suite; class setup skip, allowance 1 | Accepted; 1 actual pass and 1 skip each |
| Expected failure; unexpected success; import error; failed subtest | Rejected |
| 800 tests; 801 tests | Accepted with 800 actual passes; rejected at the bound |

A separate end-to-end control uses `workflow init`, the bound default contract,
one **fixture** generator, one real sandbox verification, and the ordinary report
stage. The saved result is accepted, all four stages complete once, and the
original incorrect application remains unchanged. One synthetic request
reservation is charged; it is not an inference call or subscription measurement.

`proof-result.json` records actual unittest counts separately from policy checks.
`preregistration.json` fixes expectations before execution. `frozen-runtime/`
contains the exact 24 runtime modules used. `proof-script.py` is an exact copy of
the reproduction tool; `publication.json` binds all raw published files by bytes
and SHA-256. Native conversation state, raw receipts and temporary project paths
are retained locally; their receipt hashes are recorded, not redacted in place.

To reproduce with a reviewed existing Windows sandbox and a new output directory:

```powershell
python -B tools/check_workflow_setup.py --root C:\work\new-setup-proof --codex C:\tools\codex.exe
```

The tool refuses an existing output directory, writes fixtures as data, imports
only the trusted Flow runtime on the host, and invokes application/checker code
only through `codex sandbox`. Runtime hashes must remain unchanged during the
run. This command does not install Codex, enable a model, or modify global settings.
Use the commit matching `frozen-runtime/` when comparing exact hashes.

An earlier local 14-control run passed before admission hardening; its untouched
evidence remains local. The published run adds the end-to-end control and uses the
final hardened runtime. These controls do not establish hostile-test resistance,
model quality, speed improvement, account entitlement, or Terra execution.
