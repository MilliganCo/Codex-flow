# Anonymous case10 production API adapters

Derived only from the two supplied anonymous source trees and the two fixed
protocols. No application code was imported or executed on the host. Host checker
validation consists solely of AST parsing and in-memory compilation. The root
coordinator performs all actual application/checker execution through its official
SDK launcher, following review of the checker bytes.

## Solution 23

- CLI: `python -m ascii_tree view|render`. Seed 42, mode 2d, yaw 25 degrees,
  pitch -7 degrees, XW 0 degrees, zoom 1, time 0. Hyperparameter `--angle4d`.
  Viewer export uses `--export-dir` and exclusive `tree-SEED-MODE-NNNN.txt` files.
- Native controls: Right/Left add/subtract 8 yaw degrees; Up/Down add/subtract 6
  pitch degrees; brackets add/subtract 8 XW degrees; zoom factor 1.12; G increments
  seed by one; R restores yaw/pitch/XW/zoom/time without changing mode. View is
  paused initially. Startup marker `ASCII TREE EXPLORER`; help marker
  `CONTROLS / same tree in every mode`. Actual image viewport is 99x35 at console
  100x40; 29x7 at 30x12; 1x1 at 1x1.
- Actual model: `ascii_tree.model.generate_tree`; segment.start/end are stored
  4-tuples, segment.parent is a preceding segment index or None; leaves use
  leaf.point. Full fingerprint includes every dataclass field, radii and foliage.
- Actual rotation: `geometry.rotate_xw(point, radians)`, column-vector convention
  X'=cos(a)X-sin(a)W; W'=sin(a)X+cos(a)W. Sigma +1. `xw_matrix` has the same form.
- Production renderer: `render.render(tree,width,height,Camera(...))` defines its
  private `project(p)` closure. XYZ is normalized by its fixed tree bound,
  Y is centered on half the highest branch endpoint; W becomes `(W-.5)*1.35`.
  Then XW rotation, guarded `project_4d` at distance 4, yaw, pitch, guarded
  `perspective` at distance 3.6, aspect .5, terminal centering/scaling. Returns
  subpixel X,Y,Z,radius scale before rasterization.
- The geometry checker observes actual closure return events with sys.setprofile
  only inside SDK. It checks exact source filename/name/hash, restores the prior
  profiler in finally, records all branch/leaf calls and compares their returned
  values to an independent formula. It obtains the untouched closure from the
  returning renderer's locals, then invokes that same function for denominator
  and nonfinite-input probes. No app source, input, local/global, or callable is
  modified. This profiling is absent from native checks and any timing metric.

## Solution 24

- CLI: `python -m ascii_tree view|render`. Seed 42, mode 2d, yaw 25 degrees,
  pitch 8 degrees, XW 0 degrees, zoom 1, time 0. Hyperparameter `--angle4`.
  Viewer exports exclusive `tree_SEED_MODE_NNNN.txt` in `--export-dir`.
- Native controls: yaw increment 7 degrees, pitch increment 5 degrees, XW
  increment 10 degrees; zoom factor 1.12; G increments seed by one; R restores
  yaw/pitch/XW/zoom/time without changing mode. Initially paused. Startup marker
  `ASCII TREE EXPLORER`; help marker `ASCII TREE EXPLORER / HELP`. Actual image
  viewport is 100x36 at console 100x40; 30x8 at 30x12; 1x1 at 1x1.
- Actual model: `ascii_tree.geometry.generate_tree`; stored Point4 vertices,
  segments with start/end vertex indices and parent segment indices; foliage
  positions are leaf.position. Buttress roots have no parent but share root
  vertex 0. These are one connected rooted skeleton, not independent trees.
- Actual rotation: `projection.rotate_xw(Point4,degrees)`; same column convention
  sigma +1. Production Projector inlines the identical XW operation, which is
  separately validated by comparison of its complete production subpixel path.
- Production `Projector(tree, RenderOptions(...)).project(Point4)` centers Y on
  all-geometry vertical bounds and W on skeleton W bounds. It performs XW,
  guarded perspective4, yaw, pitch, guarded 3D perspective, aspect 2, then screen
  scaling. Returns ScreenPoint(x,y,depth,radius_scale). Independent reference
  derives its framing from every actual skeleton/foliage coordinate.

## Shared accounting and limitations

The checkers never award points. Both seeds 42 and 137 use full actual production
models; rotation tolerances remain 1e-10 and projection tolerances remain relative
2e-10/absolute 2e-9. Skeleton and full-model affine rank and W span are separate.
An immutable `frozen_sources` inventory remains distinct from projection expected
values and is compared before/after execution.

The native checker imports only the byte-identical neutral ConPTY plumbing. It
uses literal input, physical resize, exact headless state oracles and the fixed
57-check count, including the embedded 3D forward/reverse comparison inside check
7. Wait limits and explicit animation/resize pauses match the protocol. It adds
no console-mode or signal repairs. Failure retains transcripts/partial checks and
marks all unexecuted checks incomplete, never passed.

Auxiliary nonfinite public/private API probes retain failures as failures, even
when ordinary validated production views are safe. Such observations are evidence
for adjudication under the original rubric; they introduce no additional critical
gate. Original console input modes cannot be queried after process exit.
