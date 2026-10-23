# Troubleshooting

Start with `python codex-flow.py doctor`, then the relevant command's `--help`. Preserve failed-run metrics and events. Do not repeatedly rerun an unchanged failing command or weaken sandbox/auth restrictions to obtain a green status.

| Symptom | Cause or discriminating check | Safe next step |
|---|---|---|
| Runtime disabled | Default `enabled: false` | Review a dry run; opt in with `--enable` for an authorized execution |
| Codex unavailable | Missing PATH entry, invalid executable or incompatible CLI | Select the existing executable with `--codex`; inspect its version/help |
| Subscription login required | Native login is absent or not ChatGPT | Use the native login flow; do not copy tokens or enable API fallback |
| Sol XHigh absent in deep doctor | CLI model metadata lacks the exact profile | Record the unavailable profile; do not silently substitute another root model |
| Mercury degraded | External root absent, missing credentials, validation failure or subprocess error | Keep deterministic fallback; inspect sanitized reason and existing external adapter |
| Timeout/cancel | Wrapper deadline or cancellation request | Confirm process ended and inspect artifacts before deciding whether a new run is appropriate |
| Completed but no accepted app | Native completion is not acceptance | Run the independent evaluator and relevant project checks |
| Empty/unknown usage | Native stream did not expose aggregate helper accounting | Keep `null`; retain root usage separately |

## Mercury: Node shutdown fixed, HTTP 403 remains

The initial Windows Node process crashed before a successful decision response. A natural-exit wrapper fixed that shutdown path without modifying the trusted external installation. The subsequent free-only smoke returned `REJECTED` with `http_403`, zero inference attempts and zero successful calls. Keep Mercury unavailable/degraded. HTTP 403 needs an authorization/routing investigation; it is not permission to try a paid route, copy secrets into scripts or mark `configured` as `validated`.

An explicit `doctor --mercury-root <trusted-root> --live-mercury` can recheck the integration once its environment has materially changed. It is a real provider request and must retain free-only policy. Ordinary `doctor` is model-free.

## Installer refuses an update

The offline installer protects edited managed files, unknown global-block changes, manifest ownership and link/junction boundaries. Save local edits, compare the package and reconcile the managed region. `--replace-edited`, uninstalling or deleting the manifest is not a routine conflict-resolution strategy. Existing customized browser routing should be preserved deliberately.

## Run inspection

```powershell
python codex-flow.py --repo <project> runs list
python codex-flow.py --repo <project> runs show <run-id>
python codex-flow.py --repo <project> runs replay <run-id>
```

Replay reads saved JSONL and reports event/error counts and available root usage. It does not replay task execution. Redacted diagnostics may omit the raw cause; collect only the minimum permitted local evidence without exporting credentials or authenticated payloads.
