# ASCII Tree Explorer demos

[Русский](README.ru.md) · [Case02 results](../../benchmarks/case02/results.json)

Two independently evaluated case02 applications are preserved without combining their implementations:

| Folder | Original arm / anonymous ID | Artifact score | Execution status |
|---|---|---:|---|
| [solo](solo/README.md) | A / solution-2 | 95/100 | `timed_out` |
| [flow](flow/README.md) | B / solution-1 | 97/100 | `timed_out` |

Artifact acceptance came after independent review; it does not change those process statuses or prove a full-flow speedup. In case02, successful Mercury calls were zero and native helper execution was unconfirmed.

Both demos use Python 3.12+ and the standard library only. No API key, service, package install or GPU is required. Use a real terminal for interactive viewing; the two applications have different non-TTY `view` behavior. Use `render` in scripts.

## PowerShell

From the repository root, choose either `solo` or `flow`:

```powershell
$variant = 'solo' # change to 'flow' for arm B
Push-Location (Join-Path 'examples/ascii-tree' $variant)
python -m ascii_tree --help
python -m ascii_tree view --seed 42 --mode 3d
Pop-Location
```

## Linux / WSL

From the repository root:

```bash
cd examples/ascii-tree/solo # or examples/ascii-tree/flow
python3 -m ascii_tree --help
python3 -m ascii_tree view --seed 42 --mode 3d
```

Interactive controls: `1`/`2`/`3` choose 2D/3D/4D; arrows rotate; `[`/`]` change the 4D angle; `H` shows help; `E` exports; `Q` exits. Each variant's README documents its exact flags and behavior. Both support:

```text
python -m ascii_tree render --seed 42 --mode 4d --width 100 --height 40 --output frame.txt
python -m unittest discover -s tests -v
```

Run the same test command inside each variant when evaluating this package. **No application, import, test or CI execution was performed during packaging.** Historical case02 verification is recorded separately; [flow/VERIFICATION.md](flow/VERIFICATION.md) was added after evaluation to repair a missing documentation link.

## Subsequent verification

After packaging, a Windows sandbox check passed **35 solo tests and 47 flow tests**. For both copies, headless 2D/3D/4D smoke checks passed ASCII/dimensions, repeat determinism and seed variation. That smoke did not run an interactive terminal scenario. This is new verification of the packaged copies, separate from their original case02 artifact scores.

The first Ubuntu CI exposed platform drift in solo's full-float `repr` fingerprint. A separately recorded post-benchmark packaging fix uses versioned canonical JSON at nine decimal places. It changes identity serialization and its expectations, preserving geometry and all ASCII fixture bytes. Isolated Linux verification passed the 36-test solo suite (one Windows-only skip), the 47-test flow suite and all 18 headless render calls. Fresh Windows/Ubuntu CI for the fix is pending; see [acceptance status](../../docs/acceptance-status.md).

Each `provenance.json` maps the original arm/anonymous ID, retains original hashes, records current code hashes and labels post-benchmark packaging changes. Solo's fingerprint fix does not change the original artifact or score. Static ASCII fixtures are retained. Runtime exports, raw logs/terminal recordings, Git/native state, databases, journals, credentials and temporary directories are excluded. See each variant's `PACKAGING.md` for omitted historical links.
