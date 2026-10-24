# ASCII Tree Explorer

Python 3.12+, Windows Terminal + PowerShell 7 or Linux/WSL. No runtime dependencies,
network, GPU or API keys. Run from this project directory:

```powershell
python -m ascii_tree --help
python -m ascii_tree view --seed 42 --mode 3d
python -m ascii_tree render --seed 42 --mode 4d --width 100 --height 40 --output sample.txt
python -m unittest discover -s tests -v
```

The module entrypoint works without installation. Optional packaging exposes
`ascii-tree` via `python -m pip install .` (requires the pinned build dependency).

Controls: `1` 2D, `2` 3D, `3` 4D; arrows orbit/tilt; `[` / `]` rotate XW in 4D;
`+` / `-` zoom (`=` also zooms in); Space animates/pauses; `G` next seed;
`R` resets camera/zoom/XW/wind; `E` exports; `H` / `?` help; `Q` / Esc / Ctrl+C exits.
Modes preserve the exact immutable tree. E exports only the current tree viewport,
without title/help/status/ANSI, into the current directory (or `--export-dir`).

The model is a connected graph of tapered 3D branches. W records developmental
time. 4D centers/scales W, applies a real orthogonal XW rotation, projects from
W=16 into 3D, then uses the same perspective camera and depth buffer as 3D.
2D is a fixed orthographic view of this same graph. The display is a projection
of four-dimensional data. It is not a claim that a terminal has four dimensions.

The exact 4D transform uses `X=x`, `Y=y-6`, `Z=z`, `W=8*(w-0.5)`:

```text
X' = X*cos(a) - W*sin(a)       W' = X*sin(a) + W*cos(a)
Y' = Y                        Z' = Z
(x3, y3, z3) = 16/(16-W') * (X', Y', Z')
```

The XW block has determinant 1; rotating by `-a` reverses it. Near-eye points
are rejected before division. Camera yaw/pitch then rotate XYZ and perspective
from depth 24 maps into text cells. Extra 4D framing room keeps the crown visible.

Headless options: `--seed`, `--mode`, `--width`, `--height`, `--yaw`, `--pitch`,
`--angle4d`, `--zoom`, `--time`, `--aspect`. Dimensions: 1..500 by 1..250.
The default cell aspect (width/height) is 0.5; adjust for your font.
Equal arguments produce identical LF-terminated ASCII bytes. `view` without a
TTY exits with code 2 and a useful message; `render` works with redirected streams.

One-command reproducible smoke (no terminal required):

```powershell
python tools/smoke.py
```

To save the combined test log, smoke output and artifact checks:

```powershell
python tools/verify.py
```

Saved frames for seeds 42 and 43 are in [artifacts/frames](artifacts/frames).
Compare `seed42-4d-xw0.txt` with `seed42-4d-xw35.txt` for a genuine XW rotation.
Recreate all six examples and their SHA-256 manifest with:

```powershell
python tools/generate_samples.py
```

For a finite actual-console startup/shutdown check, run inside Windows Terminal:

```powershell
python tools/native_probe.py --startup --label startup
```

This writes a report to `artifacts/native-startup.json` and verifies restoration
of the original Windows input/output console modes. It cannot run through a pipe.
See [INTERACTIVE_DEMO.md](INTERACTIVE_DEMO.md) for the keyboard/resize walkthrough
and [VERIFICATION.md](VERIFICATION.md) for tested scope and limitations.
