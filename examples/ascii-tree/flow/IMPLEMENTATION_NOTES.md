# Implementation notes

## Decisions

Python 3.12, standard library only: the source checkout runs offline immediately.
`python -m ascii_tree` is the primary entrypoint; no build backend, package install,
GPU, service, or global configuration is required. `requirements.txt` deliberately
contains no dependencies, so there are no third-party versions to pin.

`model.py` owns immutable vertices, tapered segments, leaves and parent indices.
The trunk is a curved chain with a wider base. Golden-angle primary branches have
seeded reach/elevation variations, curved secondary/tertiary forks and porous
terminal foliage. The maximum order is 3 and a hard 6,000-segment budget guards
future changes. Seed 42 currently has 598 segments, 599 vertices and 1,386 leaves.
Local `random.Random(seed)` isolates generation from application state.

`geometry.py` implements an explicit orthogonal XW matrix and guarded 4D perspective.
W accumulates developmental path length; it is part of every model vertex, not
assigned by the renderer. A single fixed normalization/framing applies across
modes: camera or XW rotation never regenerates or re-fits the tree.

`render.py` projects shared vertices, rasterizes tapered capsules and depth-tests
each cell. Reciprocal camera depth is interpolated along projected segments;
an approximate cylinder front-surface offset avoids treating bark as a flat line.
Directional twig glyphs and depth-dependent punctuation preserve branching;
thicker bark uses a fixed upper-left light. Leaf samples share the z-buffer.
Explicit tie priority makes wood win exact depth ties. Output uses printable
ASCII and LF only; file export writes bytes to avoid Windows newline conversion.

`app.py` is a separately testable state machine. `terminal.py` uses alternate screen,
cursor home and buffered updates at at most 15fps. Paused scenes redraw only after
input/resize. Windows reads native Unicode input events with ctypes. This handles
arrows without the pending-code problem in `msvcrt.getwch`, and Alt-release Unicode
composition used by ConPTY for punctuation absent from an active keyboard layout.
Ctrl+C is a normal input event in Windows; POSIX uses cbreak/select and catches
KeyboardInterrupt. Console modes, cursor and alternate screen restore on exit/error.

## Trade-offs and known limitations

- This is a botanical-inspired deciduous tree, not a species simulator. W models
  developmental distance, not years, time travel or an anatomical fourth axis.
  XW rotation intentionally distorts the familiar silhouette.
- ASCII shading is approximate. Leaves are single-cell porous samples, not textured
  polygons; their stored botanical size does not make an opaque foliage surface.
  Very thin or distant twigs can merge at coarse resolutions. This is a cell
  z-buffer with an approximate cylinder surface, not a full polygon ray tracer.
- Perspective endpoints at/behind a near plane reject their segment instead of
  geometrically splitting it. The generated normalized trees stay well clear of
  those planes; guards also cover direct math calls. Extreme zoom/camera angles
  can clip the crown, as expected. Huge finite animation times are reduced modulo
  the shared angular period before arithmetic to avoid overflow.
- 1x1 and narrow terminals remain safe, but cannot display useful detail or full
  help. Interactive output caps at 1000x1000 cells and reserves one column and one
  row to prevent normal terminal wrap/scroll. Forced process termination cannot
  execute cleanup. Alphabetic shortcuts assume the Latin keyboard layout.
- Byte determinism is verified across independent Python processes on this Windows
  environment; cross-platform bit identity of system trigonometric functions is
  not claimed. Linux/WSL code exists but was not executed here. ConPTY validates
  native input/output, not the appearance of a particular terminal font.

## Performance

`python scripts/benchmark.py` measures generation and 20 frames per mode at 100x40.
An initial local sample on Python 3.12.10: generation 7.72 ms; median raster time
15.83 ms (2D), 17.50 ms (3D), 23.37 ms (4D). These are measurements, not guarantees.
Terminal output cost is additional. Geometry is generated once per seed and reused;
the event loop includes rendering time in its 15fps budget, avoiding queued frames.

## Test plumbing

`scripts/windows_console.py` creates an invisible Windows pseudoconsole with a
background pipe reader, finite waits and process cleanup. `console_child.py`
supplies CONIN$/CONOUT$ handles because a redirected parent otherwise copies
invalid standard handle numbers into the child. This affects only the test harness;
the application still rejects redirected `view` streams. Tests compare actual
TTY exports against deterministic headless renders, including modes, arrows, XW,
zoom, seed and each asserted resized raster. Animation is checked for changed
pixels and exact paused stability. Q, Esc and Ctrl+C run through real processes.

No network, external model, extra agent, browser, publication or deployment was used.
