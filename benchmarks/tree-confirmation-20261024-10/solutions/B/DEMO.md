# Interactive demonstration (about 2 minutes)

Use Windows Terminal + PowerShell 7 with Python 3.12+. Run in the project directory:

```powershell
python -m ascii_tree view --seed 42 --mode 2d
```

1. Set the window to approximately 100 columns by 40 rows. Press `H`, read the
   controls, then `H` again. The top row shows **2D / seed 42**. Look for the
   crooked trunk, progressively thinner branches and scattered foliage.
2. Press `2`, then Left/Right and Up/Down. Depth, crossings and canopy shape
   change. Press `3`, then `]` five times. XW reaches 40 degrees: branch age W
   is mixed with X. The crown bends in the projection; seed remains 42.
3. Press Space, wait 3 seconds, press Space again. The screen updates in place.
   Press `+`, `-`, then `R`. Reset restores yaw 25, pitch -7, XW 0 and zoom 1.
   Press `E`: the footer names a new file under `exports/`; open it in a text
   editor with a monospace font. It contains only the tree raster, no UI or ANSI.
4. Resize to 30x10, then 10x4, then back to 100x40. No crash; the tree refits.
   At very small sizes the compact status uses the first row. Press `G`: seed
   becomes 43 and the geometry changes. Press `1`, `2`, `3`: it stays seed 43.
5. Press `Q` or Esc. The original screen and cursor return. Launch again and
   use Ctrl+C. It should also restore the terminal (process return code 130).

Finite **real terminal** startup/shutdown check:

```powershell
python -m ascii_tree view --seed 42 --mode 4d --frames 2
```

In redirected/non-TTY environments this emits one ordinary frame and exits.
Run it inside a terminal to exercise alternate-screen startup and restoration.

The automated controller tests simulate resize and interrupts; they do not prove
native window-manager resize or how a particular Windows Terminal font looks.
See `VERIFICATION.md` for checks actually performed in the development environment.
