# Interactive demonstration / manual checks

Run in Windows Terminal with a monospace font, around 100 columns by 40 rows:

```powershell
python -m ascii_tree view --seed 42 --mode 3d
```

1. Press `1`, `2`, `3` with a pause between them. The title changes 2D / 3D /
   4D, the tree retains seed 42, and the views differ. In 3D, use all four arrows:
   branches move relative to one another, and foreground strokes cover background
   strokes. Use `R` to restore the starting camera.
2. In 4D press `]` four times, then `[` twice. The visible XW angle and geometry
   change; the status says `4D -> 3D -> 2D projection`. Try `+` and `-`, open
   `H`, read the dimensional explanation, then close with `?`.
3. Press Space, observe smooth replacement of frames for 3 seconds, press Space
   to pause. Press `E`: the status shows a new `.txt` filename. Open it with
   `Get-Content <filename>` after exit; it contains only the current tree raster.
   Press `G`: seed becomes 43 and a different tree appears. Press `R` to reset.
4. Shrink the terminal to 30x10, then as small as the host permits, including
   a very narrow width. Open help, resize again, return to 100x40. There must be
   no traceback, scrolling frame spam or stale status. A tiny window shows a
   resize hint, while `Q` still works.
5. Exit with `Q`; run again and exit with Esc; run a third time and exit with
   Ctrl+C. The ordinary PowerShell prompt and cursor return. Run `Write-Output OK`
   to check that normal typing/echo works.

For recorded native console evidence, use:

```powershell
python tools/native_probe.py --label manual
```

It runs the actual application in the actual terminal, then saves
`artifacts/native-manual.json` with the final seed/mode/angles, exports, and the
before/after Windows console modes. It has a 45-second watchdog. Complete the
key sequence and quit within that interval. `--startup --label startup` provides
a finite one-frame check without waiting for input.

Saved native reports in this project record the checks actually performed in
Windows ConPTY. The walkthrough above also covers host-window resize and font
appearance, which need a visible Windows Terminal window for full manual QA.
