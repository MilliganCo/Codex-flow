# Case09 independent application adapters

Prepared from anonymous production text only. No application has been imported or
executed on the host. Both scripts accept `--id 17|18 --solution ABS_PATH --output
ABS_JSON_PATH`; `--solution-root` / `--solution-id` are equivalent aliases.
The native checker also accepts `--output-dir NEW_ATTEMPT_DIR` instead of
`--output`, mapping to `NEW_ATTEMPT_DIR/report.json` without overwriting attempts.
Run only through the root's reviewed official SDK launcher, after
the frozen evaluator. Output parents must be separate for each native attempt.
The scripts perform no source repairs or monkeypatches. `frozen_sources` is an
immutable mapping and is never rebound. Source manifests cover every original
file except Python caches and test scratch `.tmp`; all generated evidence belongs
outside the submission. Frozen evaluator observations remain separate.

## Source-derived production APIs

| Item | solution-17 | solution-18 |
|---|---|---|
| CLI | `python -m ascii_tree view|render` | same |
| Graph | `model.generate_tree(seed)`; `Tree.segments/leaves` | same |
| Vertices | segment start/end `Point4`; leaf `.point` | segment start/end `Point`; leaf `.center` |
| Rotation | `projection.rotate_xw(point,radians)` | `render.rotate_xw(point,degrees)` |
| Rotation convention | column vectors; X'=cX-sW, W'=sX+cW; sigma=+1 | same |
| Full projection | `projection.Projector(...).__call__` used by `render.render` | `render.project` used by `render.render_tree` |
| 4D preprocessing | subtract immutable `tree.center` | `(x,y-6,z,8*(w-.5))` |
| 4D perspective | 18/(18-W); reject denominator<.5 | 16/(16-W); reject denominator<.5 |
| Camera order | yaw then pitch; depth 30-Z | yaw then pitch; depth 24+Z |
| Character correction | horizontal factor aspect=2 | horizontal divisor aspect=.5 |
| Framing | exact `render.render` tree span fit and .91 margin | exact `render.project` size fit and .8 4D margin |
| State | `app.Explorer(tree).handle_key` | `app.Explorer(seed).handle` |
| Reset yaw/pitch/XW/zoom/time | 25,-8,0,1,0 | -22,8,0,1,0 |
| Right/Up/XW step | +7.5,+5,+7.5 degrees | +8,+6,+8 degrees |
| Zoom + / - | multiply1.12 / divide1.12 | multiply1.1 / multiply.9; roundtrip .99 |
| New seed | seed+1 | seed+1 |
| Export naming | tree-seed42-MODE-NNN.txt | tree-42-MODE-NNN.txt |
| Initial startup marker | ASCII TREE EXPLORER | same |
| Help marker | ONE TREE / THREE VIEWS | ASCII TREE EXPLORER / controls |
| Terminal100x40 image | 99x33: reserve row/column, then6 rows | 99x37: reserve column, then3 rows |
| Terminal30x12 image | 29x5 | 29x9 |
| Terminal1x1 image | 1x1 | 1x1 |

All ordinary geometry comparisons use time0, yaw/pitch defaults and 100x40 at
XW0 and37 degrees, both seeds42 and137, every endpoint and foliage vertex.
Rotation bases at0/37/90 degrees use fixed sigma+1, absolute/relative1e-10;
full-model norm/inverse checks use the same bound. Affine-rank pivot tolerance is
max(1e-10,scale*1e-10). Projection tolerance is relative2e-10/absolute2e-9.
Pathological inputs call the production projection API directly; any actual
NaN/Inf or exception is retained as a failed auxiliary observation, with no new
rubric gate. No minimum arbitrary-point movement threshold exists.

## Fixed native interaction

`native57_case09.py` uses the byte-identical `conpty_case09_neutral.py` only for
ConPTY creation, I/O, resize, wait and generic module bootstrap. It does not change
control handlers or input modes. Full fixed57 sequence, including embedded3D
camera roundtrip, physical30x12/1x1/100x40 resizing, .45/.15/.3-second pauses,
5-second native waits and15-second CLI oracle waits is preserved. Oracle and
interactive state share documented numeric settings. Three genuine sessions send
q, byte0x1B and byte0x03; required cursor-show and alternate-screen-leave bytes
are checked in real transcripts. No view handler is used in the native checker.

Raw exports, stdout/stderr oracle records, binary transcripts, partial checks,
errors and source/checker hashes remain in the new attempt directory. First
execution exception stops the sequence; unexecuted checks cannot pass.

## Host verification boundary

Only standard-library AST parsing and in-memory `compile(source, ..., 'exec')`
were performed on these new checker sources. This compiles but does not execute
checker or application code. No application imports were used in this proof.
Runtime results are pending root launcher receipts.
