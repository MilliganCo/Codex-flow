# Case09 independent blind review

**solution-17:98/100, accepted. solution-18:96/100, accepted.** All 26 criteria are assessed for each; the same five critical functional gates pass. This is the completed independent blind review; the frozen evaluator outputs remain unchanged.

| Category | Max | solution-17 | solution-18 |
|---|---:|---:|---:|
| 2D procedural branched tree and determinism | 12 | 12 | 12 |
| 3D XYZ rotation depth and occlusion | 13 | 13 | 13 |
| 4D XYZW variable W hyperplane rotation and sequential projection | 20 | 20 | 19 |
| UX controls help stable object and export | 12 | 12 | 12 |
| Organic appearance crown branching and shading | 12 | 10 | 9 |
| Resize Ctrl+C headless tiny terminal and crashes | 10 | 10 | 10 |
| Meaningful reproducible test coverage | 9 | 9 | 9 |
| Modularity source and dependencies | 7 | 7 | 7 |
| Real setup commands and explanation of 4D | 5 | 5 | 5 |

## Actual execution evidence

- The frozen evaluator recorded 25/25 automated assessed points per submission and 20 successful render invocations, including deterministic repeats, matched-size seed diversity, yaw/XW changes and tiny output. Its total score stayed null pending independent review.
- Both unmodified viewers passed exactly 57/57 actual Windows ConPTY checks. Literal keys, 3D forward/reverse arrows, animation/pause, help, reset, seed, export, physical30x12/1x1/restored resizing and CLI oracle comparisons all passed. q/Esc/Ctrl+C exited 0 with cursor-show and alternate-screen-leave sequences.
- Geometry: solution-17 passed 79/79; solution-18 passed 61/79. All complete-model geometry, graph, affine rank, W, signed-basis/orthogonality/determinant/inverse/norm, sequential projection and stable-model checks passed. All 18 solution-18 failures are direct malformed nonfinite-point inputs and remain preserved.
- Documented unittest commands exited 0: 50 observed tests for solution-17 and 26 for solution-18. Counts establish a nonempty executed suite; they are not scoring bonuses.
- Six root SDK runs completed without execution error, timeout, source change, checker change or retry. No application code was imported/run on the host.

## Geometry measurements

| Submission / seed | Branch segments | Foliage vertices | Endpoint visits / full visits | Skeleton XYZ rank | Skeleton W span |
|---|---:|---:|---:|---:|---:|
| solution-17 / 42 | 581 | 1224 | 1162 / 2386 | 3 | 5.70201888397 |
| solution-17 / 137 | 581 | 1242 | 1162 / 2404 | 3 | 6.01256473983 |
| solution-18 / 42 | 315 | 548 | 630 / 1178 | 3 | 0.994012330667 |
| solution-18 / 137 | 315 | 548 | 630 / 1178 | 3 | 0.994012330667 |

Both submissions store actual XYZW. Their production XW operators use column-vector convention X'=cos(a)X-sin(a)W, W'=sin(a)X+cos(a)W; solution-17 accepts radians and solution-18 degrees. Fixed basis checks at 37/90 degrees and matrix checks at 0/37/90 pass with 1e-10 absolute/relative tolerances. Full projection comparisons at XW 0/37 degrees, both seeds and every vertex agree with the independent sequential reproduction (maximum recorded error 0 at the specified tolerances). Full skeleton and foliage affine XYZ ranks are 3. Complete geometry/radius/foliage fingerprints survive mode/angle/reset changes; only G produces seed +1.

## Score judgments and retained defect

**solution-17 aesthetics 10/12:** Recognizable organic trees with a coherent tapered trunk, uneven multi-order branches, varied foliage sprays and visible bark depth/light shading. Seeds differ clearly. Dense upper twigs/foliage can merge into punctuation texture; some high 4D foliage touches/crops the top border. Subjective 10/12.

**solution-18 aesthetics 9/12:** Recognizable asymmetric tapered trees with visible limb hierarchy and airy foliage clusters; seeds have distinct silhouettes. Small repeated leaf bouquets and angular twig tangles read more as a sparse scaffold than a full organic crown, with coarser bark shading; some upper views touch/crop the frame. Subjective 9/12.

**solution-18 projection 3/4:** production `ascii_tree/render.py:38` and`:59` guard near-eye denominators but do not consistently reject NaN/Inf point coordinates. Nine malformed input cases fail for each seed: X=NaN/+Inf/-Inf, Y=NaN/+Inf, Z=NaN/+Inf and W=NaN/-Inf. Some return NaN components; Y/Z+Inf can return infinite depth. This defect costs one point under the existing projection criterion. It is not erased or relabeled as a passing auxiliary suite. Every finite generated point in the complete seeded models and all tested CLI views remains correct and guarded, so the existing functional 4D-projection gate passes; no separate invalid-input critical gate is invented.

Other rubric categories receive their documented maximum based on source and actual execution. In both, the generator creates asymmetric connected tapered limbs and finite foliage; the raster uses depth ordering and shading; controls preserve the model; packaging has zero runtime dependencies and a pinned optional build backend. Tests meaningfully cover all ten requested areas. README commands and mathematical explanations agree with production code. Documentation volume, number of files, number of tests, response format and any author/strategy identity contribute no points.

## All 26 criteria

| Criterion | Max | solution-17 | solution-18 |
|---|---:|---:|---:|
| 2d.determinism | 3 | 3 | 3 |
| 2d.seed_variation | 2 | 2 | 2 |
| 2d.procedural_morphology | 7 | 7 | 7 |
| 3d.angular_change | 4 | 4 | 4 |
| 3d.geometry | 4 | 4 | 4 |
| 3d.occlusion | 5 | 5 | 5 |
| 4d.angular_change | 4 | 4 | 4 |
| 4d.coordinates | 4 | 4 | 4 |
| 4d.variable_w | 4 | 4 | 4 |
| 4d.rotation_math | 4 | 4 | 4 |
| 4d.projection | 4 | 4 | 3 |
| ux.help | 2 | 2 | 2 |
| ux.export | 2 | 2 | 2 |
| ux.interactive_controls | 6 | 6 | 6 |
| ux.stable_object | 2 | 2 | 2 |
| aesthetics.blind_frames | 12 | 10 | 9 |
| reliability.headless | 3 | 3 | 3 |
| reliability.tiny | 2 | 2 | 2 |
| reliability.resize | 2 | 2 | 2 |
| reliability.ctrl_c | 3 | 3 | 3 |
| tests.execution | 3 | 3 | 3 |
| tests.coverage | 6 | 6 | 6 |
| maintainability.review | 7 | 7 | 7 |
| readme.commands | 2 | 2 | 2 |
| readme.installation | 1 | 1 | 1 |
| readme.4d_explanation | 2 | 2 | 2 |

## Five unchanged critical gates

| Gate | solution-17 | solution-18 |
|---|---|---|
| 4d.coordinates | pass | pass |
| 4d.variable_w | pass | pass |
| 4d.rotation_math | pass | pass |
| 4d.projection | pass | pass |
| reliability.headless | pass | pass |

## Evidence and integrity

- [Completed structured blind review](blind-review.json) includes per-criterion reasons, source/function references, measurements, exact auxiliary failures and acceptance.
- [Full source integrity](blind-review-source-integrity.json) lists all 90 original submission files: 49 for solution-17 and 41 for solution-18. Original, geometry-before/after, native-before/after and final review hashes all agree. Checkers/evaluator/rubric and both frozen evaluation JSON hashes are also recorded.
- Raw unchanged evidence: [frozen17](frozen-17/evaluation.json), [frozen18](frozen-18/evaluation.json), [geometry17](geometry-17.json), [geometry18](geometry-18.json), [native17](interactive-17/report.json), [native18](interactive-18/report.json). Each execution has its own retained `*-execution.json` receipt and raw stdout/stderr; native reports point to exports/oracles/binary transcripts.
- New adapters and assumptions: `verification/tree/CASE09_ADAPTERS.md`. Fixed protocols and canonical rubric were read before adapter creation; checkers were AST parsed/in-memory compiled on host, then reviewed and run by root through the SDK.

This review remained blind and independent: no identity/arm/strategy mapping, prior-case score, prior app-specific checker, memory, benchmark/performance artifact contents or other submission source was consulted. No application changes or runtime repairs occurred. Host report-summary parsing had one syntax-only reader error, then was corrected without executing app/checker code or changing evidence.

The actual console evidence establishes transcript restoration, not a post-exit query of original mode flags. Visible-font screenshots and Linux/WSL behavior are unassessed. Saved ASCII frames provide the aesthetic evidence; those subjective judgments do not claim photorealism or full-view fit for every possible camera angle.
