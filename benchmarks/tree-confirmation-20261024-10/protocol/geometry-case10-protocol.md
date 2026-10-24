# Independent geometry protocol

Prepared for case10 on 2026-10-24. Evaluation root: `evaluation-case10-20261024`; read-only verifier root: `verification-runtime-20261024-10`. The unchanged rubric retains 26 criteria and five critical gates.

Freeze this protocol before generation. It specifies evidence for the unchanged
task and rubric; it does not change criterion weights, acceptance, scores or
thresholds. The canonical rubric SHA256 remains
`74aa2e1de107aac0226d1df352970fe4ba0e5ec56cc777ce49983d851879c466`.
No prior solution, score, author, model, strategy or arm mapping belongs in the
checker packet. Anonymous submissions are identified only as `solution-23` and
`solution-24`.

This document creates no application inputs or application-specific adapters.
After generation ends and anonymous code is available, derive an explicit adapter
from that submission's documented API and production source. Execute it only in
the reviewed sandbox through the new verifier launcher, after the unchanged
frozen evaluator has run. Record source hashes before and after. Never import an
application on the host, modify its source, repair its API, or manufacture a
missing capability. Unsupported discovery remains `not_assessed`; a confirmed
missing required capability remains a failure. Neither outcome changes the
original evaluator record.

## Production geometry and graph

Use full production objects for both fixed seeds, 42 and 137. Inspect every branch
endpoint and every actual leaf/foliage vertex exposed by the model, rather than
only a small illustrative sample or a separate toy geometry helper. Record the
seed on each check and the actual point/edge counts. Establish these properties:

1. Actual finite XYZW coordinates exist throughout the branch skeleton and full
   model. W must be a stored or production-derived geometric component, not a
   label substituted for another unrelated 3D tree.
2. Branch links form one connected rooted skeleton with genuine branching and
   valid parent/child references. Actual XYZ segment lengths are positive
   (`>1e-12`); radii/thicknesses are finite and positive. Do not infer connected
   geometry merely from a dense leaf cloud. Procedural taper and morphology
   remain part of the separate source/frame review under the existing rubric.
3. Translate each point set by its first point and compute its affine XYZ rank.
   Require rank 3 for the skeleton as well as the full point set. Preserve the
   numerical pivot tolerance `max(1e-10, scale * 1e-10)`, where scale is the maximum
   absolute XYZ component of those translated rows. Cosmetic leaf jitter must
   not disguise a planar skeleton.
4. Preserve the established W-span check: more than one distinct finite W value
   and span `>1e-8`, on both the actual skeleton and full model. Record measured
   spans. Do not replace W variation with a claim based only on rendered labels.

## True space/W rotation

The original task requires **at least one** genuine XW, YW **or** ZW rotation.
It does not require all three. Check every implemented/documented space/W plane
used by production rendering; absence of extra planes adds no new failure gate.
Identify the spatial axis `s` and W axis from production source, not from whichever
output happens to pass. Record angle units, vector orientation, rotation order
and the documented sign convention in the adapter.

For column-vector notation, fix one convention sign `sigma` from source:

```text
R(theta) e_s = cos(theta) e_s + sigma sin(theta) e_W
R(theta) e_W = -sigma sin(theta) e_s + cos(theta) e_W
R(theta) e_j = e_j                       for every other axis j
sigma is +1 or -1, fixed for that documented operator
```

A row-vector API may be adapted by the corresponding transpose. Degrees may be
converted to radians as documented. These are representation adapters, not
alternative expected answers selected independently for each vector or angle.

Use the **production rotation operator** on canonical basis vectors, at both
37 degrees and 90 degrees. Compare each component to the exact signed sin/cos
relations above, with absolute and relative tolerances `1e-10`. At 90 degrees the
spatial and W basis vectors exchange axes with the documented signs; unaffected
axes remain unchanged. This guarantees a meaningful W/space mixing test without
choosing an arbitrary application point whose components might cancel.

From the four transformed basis vectors, independently assemble the actual 4×4
matrix. At 0, 37 and 90 degrees verify `R.T @ R = I`, determinant `+1`, preservation
of 4D norm, the identity angle, and the inverse relation `R(-theta)R(theta)=I`, all
with absolute and relative tolerances `1e-10`. Apply the operator to actual full
model points as an additional source-backed norm/inverse check. For a composition
of several plane rotations, the inverse must reverse the documented operation
order; negating angles in the same order is generally not the inverse.

**Never fail a rotation because an arbitrary point changes by more or less than
0.1 in one coordinate.** A small component, the origin, or cancellation between
components can make that assertion false for a correct rotation. Arbitrary-point
checks may compare against the exact linear transformation, norm and inverse;
they must not introduce a minimum movement threshold. Required observable
angle-dependent raster changes remain the existing frozen CLI/frame criterion,
separate from these mathematical checks.

## Actual 4D → 3D → 2D projection

Trace the production renderer's point path. Independently reproduce its documented
4D projection, camera transform, 3D perspective and terminal aspect correction;
compare the actual projected coordinates before integer rasterization when that
API is available. Use both complete seeded models and the same finite ordinary
views established by the documented controls/defaults. Include the zero-angle
view and the 37-degree supported space/W view. Record the exact view parameters.

For a conventional 4D perspective, for example, the first scale is
`d4 / (d4 - w)`; a documented opposite camera/sign convention is acceptable when
derived consistently from production source. The second perspective similarly
uses the actual 3D camera depth and focal distance. Test the sequential composition
itself, not a renamed direct 3D projection or a disconnected demonstration function.
Preserve the established projection comparison tolerance: relative `2e-10`,
absolute `2e-9`. Do not change task/rubric scoring to accommodate an adapter.

Check the production handling of zero, near and invalid perspective denominators
and nonfinite intermediate values where the API permits explicit point inputs.
Documented clipping/rejection or bounded finite projection is acceptable; NaN,
infinite output, unguarded division errors and unbounded raster coordinates are
not. Account for near-plane guards before dividing, and actual image width/height
when applying terminal scaling and aspect ratio. If a safe private projection
function cannot be identified, report the unassessed component honestly; do not
replace the production renderer with a repaired checker implementation.

## Stable model and evidence

Fingerprint the complete production graph, XYZW coordinates, radii and foliage
before and after selecting 2D/3D/4D and changing documented angles. View changes
must preserve the base seed/model and topology. Camera or render-time animation
transforms may change projected coordinates without replacing the base geometry.
Do not require a particular class name, immutable dataclass implementation, or
Python object identity if structural evidence establishes the same model.
Regeneration is assessed only through the documented new-seed operation.

Report each property with seed, status, measurements, production function/source
references, adapter convention and any exception or unavailable evidence. Keep
unknowns null; do not convert partial execution into an all-pass record or a
normalized score. The separate frozen evaluator, independent native interaction
protocol and blind source/frame assessment retain their own original findings.
All required rubric criteria and critical gates remain independently assessable;
this protocol awards no points and makes no claim before actual execution.
