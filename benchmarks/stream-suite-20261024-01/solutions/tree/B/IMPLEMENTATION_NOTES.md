# Implementation notes

Python 3.12 standard library only; no runtime dependency installation. Windows uses
`msvcrt` keyboard input and `GetConsoleMode`/`SetConsoleMode` to enable VT output.
POSIX uses cbreak input and select. A context manager restores cursor, alternate
screen and original console modes even after Ctrl+C or an exception.
Windows disables processed input while active and interprets Ctrl+C as a key;
this avoids ConPTY hosts swallowing processed control events. External Python
KeyboardInterrupt still follows the same cleanup path.

The immutable graph is generated once per seed, from a local `random.Random`.
Fifteen curved trunk internodes support ten primary branches, each with two
secondary branches and two terminal shoots per secondary. Recursion stops at
order 3. Lengths, azimuths, curvature and leaf clusters vary with the seed.
Child vertices reuse the parent's endpoint exactly; positive radii taper along
each path. Default seed 42 has 315 segments and 548 sparse foliage samples.

2D uses an orthographic X/Y projection. 3D rotates real XYZ by camera yaw/pitch,
then uses perspective. 4D centers Y and scales growth W to world units, rotates
XW with an orthogonal two-axis matrix, projects from W=16, then applies the 3D
camera. Both stages reject points behind a 0.5-unit near plane. XW rotation
preserves the XW norm and is invertible. W changes monotonically along branches.
4D reserves an additional 20% framing margin for W-perspective expansion.

The rasterizer stamps elliptical tubes with cell aspect 0.5, clips to the
viewport, samples bounded centerlines and compares per-pixel camera depths.
Reciprocal depth interpolation is evaluated at the fragment's screen position;
surface offsets use physical branch radii. A one-cell minimum footprint keeps
twigs readable. Depth-dependent bark/leaf glyphs and stroke direction shade
structure. Sparse leaves have their own depths and can occlude branches.

Trade-offs: ASCII has no antialiasing; leaf density is deliberately restrained.
Tiny terminals show a resize hint; the headless renderer still accepts 1x1.
Zoom may intentionally crop. Segments crossing a perspective near plane are
conservatively discarded, rather than geometrically split. Export is a tree-only
viewport at its current dimensions; help/status are excluded. No color is needed.
Animation is capped near 10 fps and paused displays redraw only on input/resize.
The last terminal column is reserved to prevent automatic line wrapping.

Verification and measured performance are recorded in VERIFICATION.md.
