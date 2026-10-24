# Implementation notes

## Decisions

- Python 3.12 standard library only. `msvcrt` and Win32 console modes on Windows;
  `termios`/`select` on Linux/WSL. No install or dependency resolution is needed
  for `python -m ascii_tree`. Optional packaging pins setuptools; Pillow is only
  used by the optional development contact-sheet script, never at runtime.
- Immutable XYZW graph, local seeded RNG, maximum branching order 4 and 4096
  segment guard. Each child starts exactly at an existing parent endpoint. The
  radius passed to a shoot comes from that junction, so branches cannot thicken
  at a split. W accumulates path length / 13 along branches; it is developmental
  age rather than physical clock time. Leaves carry the nearby branch's W.
- 2D is the XY projection of the same graph; 3D rotates XYZ and uses perspective.
  Bounds are computed from the unchanged tree, so rotating never regenerates or
  dynamically refits it. Character aspect defaults to 0.5 (width / height).
- Normalize XYZ by a bounding sphere, center Y, center/scale W, rotate XW using
  `x'=x*cos(a)-w*sin(a)`, `w'=x*sin(a)+w*cos(a)`. 4D perspective is
  `(x,y,z)*4/(4-w')`; then yaw/pitch and ordinary 3D perspective
  `(x,y)*3.6/(3.6-z)`. A 2% near plane clips singular/behind-camera points.
- A per-character depth buffer compares near/far branch surfaces and foliage.
  Projected tapered capsules are lit across their radius; thin wood uses slope
  glyphs. A DDA centerline keeps subpixel horizontal twigs visible and connected.
  Larger Z means nearer. Leaves are sparse depth-aware ASCII points.

## Trade-offs and known limits

- This is a small broadleaf-tree model, not a botanical simulator. The finite
  canopy has 612 segments and 672 leaves for seed 42. Leaf sprites remain one
  text cell; tiny twigs retain a minimum one-cell centerline, trading physical
  size for legibility. Foliage may visually merge at small resolutions.
- Depth is interpolated in screen space with a round-surface approximation.
  This gives real per-cell occlusion, not a physically exact ray tracer. A segment
  with an endpoint behind the 4D near plane is skipped rather than partially
  clipped. Generated trees stay comfortably outside that plane at normal views.
- Zoom and strong XW angles can deliberately crop the tree. 4D growth age is not
  a fourth physical direction; it is a genuine fourth data coordinate whose
  rotation changes the spatial projection. 2D animation adds a gentle projected
  sway; 3D/4D animation turns the camera and XW angle, without changing geometry.
- Terminal UI reserves the last column to avoid autowrap and five rows for UI.
  Interactive E therefore exports the current **art area**, not a fixed 100x40
  frame. Use `render --width 100 --height 40` for exactly that size. At height 1,
  the compact status takes the only visible row; a 1x1 raster can still export.
- `render --output` writes a same-directory temporary file, flushes it and
  atomically replaces the named file. Interactive E uses exclusive file
  creation and never overwrites an earlier export; a failed write is removed.
  Parent directories for CLI
  output must already exist; errors are reported with return code 2.
- Linux/WSL code is included but requires a separate real POSIX terminal check.
  Windows Terminal GUI rendering/physical window resize cannot be inferred from
  passing controller simulations. Native PTY checks are documented separately.

## Performance and boundaries

Rendering is O(segments + leaves + covered text cells), not a full pixel ray trace.
The native UI limits animation to roughly 10–16 FPS depending on render time,
and does not redraw a paused screen unless input/resize occurs. Dimensions are
bounded to 1000x500 and at most 250000 cells; UI caps at 999x250. Zoom is 0.1..8,
aspect 0.2..1, all numeric camera values must be finite. Huge finite angles are
reduced modulo 360 before trig. All perspective divisions check their near plane.

Tests explicitly exercise NaN/Infinity, zero/near-zero denominators, empty trees,
invalid dimensions, minimal rasters and real CLI error paths. See `VERIFICATION.md`
for measured performance, commands and platform limitations.
