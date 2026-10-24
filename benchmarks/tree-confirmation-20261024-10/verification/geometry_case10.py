"""Independent production geometry protocol for anonymous case10. SDK execution only."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict, deque
import dataclasses
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
from types import MappingProxyType

ROT_TOL = 1e-10
PROJ_REL, PROJ_ABS = 2e-10, 2e-9


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(tree):
    return hashlib.sha256(json.dumps(dataclasses.asdict(tree), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def affine_rank(points):
    anchor = points[0]
    rows = [[p[i] - anchor[i] for i in range(3)] for p in points[1:]]
    scale = max((abs(v) for row in rows for v in row), default=0)
    tolerance = max(1e-10, scale * 1e-10)
    rank = 0
    for column in range(3):
        pivot = max(range(rank, len(rows)), key=lambda i: abs(rows[i][column]), default=None)
        if pivot is None or abs(rows[pivot][column]) <= tolerance:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        value = rows[rank][column]
        rows[rank] = [x / value for x in rows[rank]]
        for i in range(rank + 1, len(rows)):
            factor = rows[i][column]
            rows[i] = [x - factor * y for x, y in zip(rows[i], rows[rank])]
        rank += 1
        if rank == 3:
            break
    return rank, scale, tolerance


def determinant(matrix):
    total = 0.0
    for perm in itertools.permutations(range(4)):
        inversions = sum(perm[i] > perm[j] for i in range(4) for j in range(i + 1, 4))
        total += (-1 if inversions % 2 else 1) * math.prod(matrix[i][perm[i]] for i in range(4))
    return total


def near(a, b, rel=ROT_TOL, absolute=ROT_TOL):
    return math.isclose(a, b, rel_tol=rel, abs_tol=absolute)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--solution-root', required=True, type=Path)
    parser.add_argument('--solution-id', required=True, type=int, choices=(23, 24))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root, output, sid = args.solution_root.resolve(), args.output.resolve(), args.solution_id
    if root.name != f'solution-{sid}' or not root.is_dir() or output.is_relative_to(root) or output.exists():
        parser.error('Expected matching anonymous solution and new external JSON output')
    frozen_sources = MappingProxyType(dict(json.loads((root.parent / 'source-hashes.json').read_text('utf-8'))[root.name]))
    def inventory():
        return {name: sha(root / name) if (root / name).is_file() else None for name in frozen_sources}
    before = inventory()
    report = {'schema': 1, 'solution_id': sid, 'protocol': 'geometry-case10-protocol.md', 'checks': [],
              'source_before': before, 'baseline_matches': before == dict(frozen_sources),
              'checker_sha256': sha(Path(__file__)), 'complete': False, 'error': None,
              'rotation_convention': {'plane': 'XW', 'spatial_axis': 0, 'w_axis': 3, 'sigma': 1,
                                      'vectors': 'column', 'units': 'radians' if sid == 23 else 'degrees',
                                      'order': 'center/normalize, XW, 4D perspective, yaw, pitch, 3D perspective, aspect and viewport'},
              'tolerances': {'rotation_rel_abs': ROT_TOL, 'projection_rel': PROJ_REL, 'projection_abs': PROJ_ABS}}

    def check(name, ok, seed=None, auxiliary=False, **evidence):
        report['checks'].append(dict(name=name, seed=seed, status='pass' if ok else 'fail', auxiliary=auxiliary, **evidence))

    def ptuple(p):
        return tuple(p) if sid == 23 else (p.x, p.y, p.z, p.w)

    try:
        if before != dict(frozen_sources):
            raise RuntimeError('Frozen inventory changed before execution')
        sys.path.insert(0, str(root))
        if sid == 23:
            from ascii_tree import model as model_api, geometry as rotation_api, render as render_api, terminal as control_api
            generate = model_api.generate_tree
            def rotate(p, deg):
                return rotation_api.rotate_xw(p, math.radians(deg))
            def model_points(tree):
                skeleton = [p for segment in tree.segments for p in (segment.start, segment.end)]
                leaves = [leaf.point for leaf in tree.leaves]
                return skeleton, skeleton + leaves
        else:
            from ascii_tree import geometry as model_api, projection as rotation_api, render as render_api, app as control_api
            generate = model_api.generate_tree
            def rotate(p, deg):
                return ptuple(rotation_api.rotate_xw(model_api.Point4(*p), deg))
            def model_points(tree):
                skeleton = [ptuple(p) for p in tree.vertices]
                return skeleton, skeleton + [ptuple(leaf.position) for leaf in tree.leaves]

        # Production rotation operator, exact basis, determinant, inverse, norm.
        for angle in (0, 37, 90):
            radians = math.radians(angle)
            cosine, sine = math.cos(radians), math.sin(radians)
            expected = ((cosine, 0, 0, -sine), (0, 1, 0, 0), (0, 0, 1, 0), (sine, 0, 0, cosine))
            columns = [rotate(tuple(float(i == j) for i in range(4)), angle) for j in range(4)]
            matrix = [[columns[j][i] for j in range(4)] for i in range(4)]
            check('rotation exact canonical basis', all(near(matrix[i][j], expected[i][j]) for i in range(4) for j in range(4)), angle_degrees=angle, actual_matrix=matrix)
            orthogonal_error = max(abs(sum(matrix[k][i] * matrix[k][j] for k in range(4)) - float(i == j)) for i in range(4) for j in range(4))
            det = determinant(matrix)
            inverse_error = max(abs(v - float(i == j)) for j in range(4) for i, v in enumerate(rotate(columns[j], -angle)))
            check('rotation orthogonality determinant and inverse', orthogonal_error <= ROT_TOL and near(det, 1) and inverse_error <= ROT_TOL,
                  angle_degrees=angle, orthogonality_max_abs=orthogonal_error, determinant=det, inverse_max_abs=inverse_error)

        for seed in (42, 137):
            tree = generate(seed)
            original_fingerprint = fingerprint(tree)
            skeleton, full = model_points(tree)
            for label, points in [('skeleton', skeleton), ('full model', full)]:
                finite = bool(points) and all(len(p) == 4 and all(math.isfinite(v) for v in p) for p in points)
                check(f'{label}: finite actual XYZW', finite, seed, point_count=len(points))
                rank, scale, tolerance = affine_rank(points)
                check(f'{label}: affine XYZ rank 3', rank == 3, seed, rank=rank, translated_scale=scale, pivot_tolerance=tolerance)
                w_values = {p[3] for p in points}
                span = max(w_values) - min(w_values)
                check(f'{label}: variable stored W', len(w_values) > 1 and span > 1e-8, seed, distinct_w=len(w_values), w_span=span)
            adjacency = defaultdict(set)
            valid_parent = valid_radii = positive_lengths = True
            lengths = []
            roots = set()
            for index, segment in enumerate(tree.segments):
                a = tuple(segment.start) if sid == 23 else ptuple(tree.vertices[segment.start])
                b = tuple(segment.end) if sid == 23 else ptuple(tree.vertices[segment.end])
                adjacency[a].add(b); adjacency[b].add(a)
                length = math.dist(a[:3], b[:3]); lengths.append(length)
                positive_lengths &= math.isfinite(length) and length > 1e-12
                valid_radii &= all(math.isfinite(v) and v > 0 for v in (segment.radius_start, segment.radius_end))
                parent = segment.parent
                if parent is None:
                    roots.add(a)
                elif not isinstance(parent, int) or not 0 <= parent < index:
                    valid_parent = False
                else:
                    ancestor = tree.segments[parent]
                    parent_end = tuple(ancestor.end) if sid == 23 else ptuple(tree.vertices[ancestor.end])
                    valid_parent &= parent_end == a
            initial = next(iter(adjacency))
            reached = {initial}; todo = deque([initial])
            while todo:
                for p in adjacency[todo.popleft()]:
                    if p not in reached:
                        reached.add(p); todo.append(p)
            connected = len(reached) == len(adjacency) and len(roots) == 1
            branching = any(len(v) > 2 for v in adjacency.values())
            check('connected rooted positive branching graph', connected and branching and valid_parent and valid_radii and positive_lengths,
                  seed, segment_count=len(tree.segments), graph_vertices=len(adjacency), reached=len(reached), root_count=len(roots),
                  branching=branching, valid_parent_links=valid_parent, finite_positive_radii=valid_radii, positive_lengths=positive_lengths, minimum_length=min(lengths))
            for angle in (0, 37, 90):
                norm_error = inverse_error = 0.0
                norm_ok = inverse_ok = True
                for p in full:
                    transformed = rotate(p, angle)
                    restored = rotate(transformed, -angle)
                    n0, n1 = math.hypot(*p), math.hypot(*transformed)
                    norm_error = max(norm_error, abs(n0 - n1))
                    inverse_error = max(inverse_error, max(abs(a - b) for a, b in zip(p, restored)))
                    norm_ok &= near(n0, n1)
                    inverse_ok &= all(near(a, b) for a, b in zip(p, restored))
                check('full production points rotation norm and inverse', norm_ok and inverse_ok, seed,
                      point_count=len(full), angle_degrees=angle, norm_max_abs=norm_error, inverse_max_abs=inverse_error)

            for hyper_angle in (0, 37):
                width, height, yaw = 100, 40, 25
                pitch = -7 if sid == 23 else 8
                if sid == 23:
                    camera = render_api.Camera(mode='4d', yaw=yaw, pitch=pitch, angle4d=hyper_angle)
                    render_source = (root / 'ascii_tree/render.py').resolve()
                    source_hash = sha(render_source)
                    observations = []
                    captured = []
                    prior = sys.getprofile()
                    def observe(frame, event, result):
                        if event != 'return' or frame.f_code.co_name not in ('project', 'render'):
                            return
                        if Path(frame.f_code.co_filename).resolve() != render_source:
                            return
                        if event == 'return' and frame.f_code.co_name == 'project':
                            observations.append((tuple(frame.f_locals['p']), result))
                        elif event == 'return' and frame.f_code.co_name == 'render':
                            captured.append(frame.f_locals.get('project'))
                    try:
                        sys.setprofile(observe)
                        rendered = render_api.render(tree, width, height, camera)
                    finally:
                        sys.setprofile(prior)
                    production = captured[0] if len(captured) == 1 else None
                    identity_ok = (production is not None and production.__code__.co_name == 'project'
                                   and Path(production.__code__.co_filename).resolve() == render_source
                                   and source_hash == frozen_sources['ascii_tree/render.py'] == sha(render_source))
                    expected_calls = Counter(p for segment in tree.segments for p in (segment.start, segment.end)) + Counter(leaf.point for leaf in tree.leaves)
                    actual_calls = Counter(p for p, result in observations)
                    check('actual private production projection coverage', identity_ok and expected_calls == actual_calls, seed,
                          angle_degrees=hyper_angle, observed_calls=len(observations), expected_calls=sum(expected_calls.values()),
                          full_branch_leaf_coverage=expected_calls == actual_calls, method='observational sys.setprofile return events; prior profiler restored in finally',
                          source=str(render_source), source_sha256=source_hash, exact_code_identity=identity_ok)
                    center = max(s.end[1] for s in tree.segments) / 2
                    bound_points = [s.end for s in tree.segments] + [tree.segments[0].start]
                    bound = max(math.sqrt(p[0]**2 + (p[1] - center)**2 + p[2]**2) for p in bound_points) * 1.08
                    scale = max(.1, min(width * .5 * .45, height * .44))
                    distance4, distance3 = 4., 3.6
                    def raw_for_rotated(x, y, z, w):
                        a = math.radians(hyper_angle); c, s = math.cos(a), math.sin(a)
                        x, w = c * x + s * w, -s * x + c * w
                        return x * bound, y * bound + center, z * bound, w / 1.35 + .5
                    def reference(p):
                        x, y, z, w = p[0] / bound, (p[1] - center) / bound, p[2] / bound, (p[3] - .5) * 1.35
                        a = math.radians(hyper_angle); c, s = math.cos(a), math.sin(a)
                        x, w = x * c - w * s, x * s + w * c
                        if 4 - w <= max(1e-6, 4 * .02):
                            return None
                        f4 = 4 / (4 - w); x, y, z = x * f4, y * f4, z * f4
                        ya, pi = math.radians(yaw), math.radians(pitch)
                        x, z = x * math.cos(ya) + z * math.sin(ya), -x * math.sin(ya) + z * math.cos(ya)
                        y, z = y * math.cos(pi) - z * math.sin(pi), y * math.sin(pi) + z * math.cos(pi)
                        if 3.6 - z <= max(1e-6, 3.6 * .02):
                            return None
                        f3 = 3.6 / (3.6 - z)
                        return width / 2 - .5 + x * f3 * scale / .5, height / 2 - .5 - y * f3 * scale, z, scale / bound * f3 * f4
                    values = observations
                else:
                    options = rotation_api.RenderOptions(width=width, height=height, mode='4d', yaw=yaw, pitch=pitch, angle4=hyper_angle)
                    projector = rotation_api.Projector(tree, options)
                    low = min(p[1] for p in full); high = max(p[1] for p in full)
                    radial = max(math.hypot(p[0], p[2]) for p in full)
                    extent = max(high - low, 1)
                    cy, cw = (low + high) / 2, (max(p[3] for p in skeleton) + min(p[3] for p in skeleton)) / 2
                    radius = max(extent * .65, radial, 1)
                    distance = radius * 4
                    distance4 = distance3 = distance
                    def raw_for_rotated(x, y, z, w):
                        a = math.radians(hyper_angle); c, s = math.cos(a), math.sin(a)
                        x, w = c * x + s * w, -s * x + c * w
                        return x, y + cy, z, w + cw
                    scale = max(.01, min(max(1, width - 4) / (max(radial * 2.25, extent * .88) * 2), max(1, height - 3) / (extent * 1.12)))
                    def reference(p):
                        x, y, z, w = p[0], p[1] - cy, p[2], p[3] - cw
                        a = math.radians(hyper_angle); c, s = math.cos(a), math.sin(a)
                        x, w = x * c - w * s, x * s + w * c
                        if distance - w <= max(1e-6, distance * .05):
                            return None
                        f4 = distance / (distance - w); x, y, z = x * f4, y * f4, z * f4
                        ya, pi = math.radians(yaw), math.radians(pitch)
                        x, z = x * math.cos(ya) + z * math.sin(ya), -x * math.sin(ya) + z * math.cos(ya)
                        y, z = y * math.cos(pi) - z * math.sin(pi), y * math.sin(pi) + z * math.cos(pi)
                        depth = distance - z
                        if depth <= distance * .05:
                            return None
                        f3 = distance / depth
                        return (width - 1) / 2 + x * f3 * scale * 2, (height - 1) / 2 - y * f3 * scale, depth, scale * f4 * f3
                    def production(p):
                        value = projector.project(model_api.Point4(*p))
                        return None if value is None else (value.x, value.y, value.depth, value.radius_scale)
                    values = [(p, production(p)) for p in full]
                max_error = 0.0; matching = True; clipped = 0
                for p, actual in values:
                    expected_projection = reference(p)
                    if actual is None or expected_projection is None:
                        matching &= actual is None and expected_projection is None
                        clipped += actual is None
                    else:
                        max_error = max(max_error, max(abs(a - b) for a, b in zip(actual, expected_projection)))
                        matching &= len(actual) == 4 and all(math.isfinite(a) and near(a, b, PROJ_REL, PROJ_ABS) for a, b in zip(actual, expected_projection))
                check('full production sequential 4D-to-3D-to-screen', matching, seed, points_compared=len(values), max_abs_error=max_error, clipped=clipped,
                      view=dict(width=width, height=height, yaw=yaw, pitch=pitch, hyper_angle=hyper_angle, zoom=1, time=0, aspect=.5 if sid == 23 else 2))
                guard_cases = []
                for label, w in [('zero 4D denominator', distance4), ('near 4D denominator', distance4 - 1e-12), ('behind 4D plane', distance4 + 1)]:
                    guard_cases.append((label, raw_for_rotated(.1, .2, .3, w)))
                for label, depth_z in [('zero 3D denominator', distance3), ('near 3D denominator', distance3 - 1e-12), ('behind 3D plane', distance3 + 1)]:
                    ya, pi = math.radians(yaw), math.radians(pitch)
                    y0, z0 = math.cos(pi) * .2 + math.sin(pi) * depth_z, -math.sin(pi) * .2 + math.cos(pi) * depth_z
                    x0, z0 = math.cos(ya) * .1 - math.sin(ya) * z0, math.sin(ya) * .1 + math.cos(ya) * z0
                    guard_cases.append((label, raw_for_rotated(x0, y0, z0, 0)))
                for label, point in guard_cases:
                    exception = None
                    try:
                        value = production(point)
                        safe = value is None or all(math.isfinite(v) and abs(v) < 1e6 for v in value)
                    except (ValueError, OverflowError) as exc:
                        safe = True; exception = type(exc).__name__
                    except Exception as exc:
                        safe = False; exception = type(exc).__name__
                    check('actual production sequential perspective guard', safe, seed, auxiliary=True,
                          angle_degrees=hyper_angle, case=label, exception=exception)
                for coordinate in range(4):
                    for invalid in (math.nan, math.inf, -math.inf):
                        p = [0.1, 0.2, 0.3, 0.4]; p[coordinate] = invalid
                        exception = None
                        try:
                            value = production(tuple(p))
                            safe = value is None or all(math.isfinite(v) for v in value)
                        except (ValueError, OverflowError) as exc:
                            exception = type(exc).__name__; safe = True
                        except Exception as exc:
                            exception = type(exc).__name__; safe = False
                        check('auxiliary production projection nonfinite input', safe, seed, auxiliary=True, angle_degrees=hyper_angle,
                              coordinate=coordinate, input=str(invalid), exception=exception)

            # Public perspective denominators: clipping/rejection/finite bounded values.
            def probe(label, callback, cases):
                for name, point, distance in cases:
                    exception = None
                    try:
                        value = callback(point, distance)
                        safe = value is None or all(math.isfinite(v) and abs(v) < 1e6 for v in value)
                    except (ValueError, OverflowError) as exc:
                        safe = True; exception = type(exc).__name__
                    except Exception as exc:
                        safe = False; exception = type(exc).__name__
                    check(label, safe, seed, auxiliary=True, case=name, exception=exception)
            fourth_cases = [(label, (0.1, .2, .3, w), 4.0) for label, w in [('zero denominator', 4), ('near denominator', 4 - 1e-12), ('behind', 5), ('ordinary', .4), ('nan W', math.nan), ('infinite W', math.inf)]]
            fourth_cases += [('zero distance', (.1,.2,.3,.4), 0), ('nan distance', (.1,.2,.3,.4), math.nan)]
            if sid == 23:
                probe('auxiliary public 4D perspective guard', rotation_api.project_4d, fourth_cases)
                third_cases = [(label, (.1,.2,z), 3.6) for label, z in [('zero denominator',3.6), ('near denominator',3.6-1e-12), ('behind',4.6), ('ordinary',.3), ('nan Z',math.nan), ('infinite Z',math.inf)]]
                probe('auxiliary public 3D perspective guard', rotation_api.perspective, third_cases)
                controller = control_api.Explorer(tree, render_api.Camera())
                for key in ('1', '2', '3', ']', 'right', 'up'):
                    controller.key(key)
                stable_tree = controller.tree
            else:
                probe('auxiliary public 4D perspective guard', lambda p,d: rotation_api.perspective4(model_api.Point4(*p),d), fourth_cases)
                controller = control_api.Explorer(seed)
                for key in ('1', '2', '3', ']', 'right', 'up'):
                    controller.key(key)
                stable_tree = controller.tree
            final_fingerprint = fingerprint(tree)
            check('stable complete model through mode and angle controls', original_fingerprint == final_fingerprint == fingerprint(stable_tree), seed,
                  before=original_fingerprint, after=final_fingerprint, controlled=fingerprint(stable_tree), includes='all dataclass fields: graph, XYZW, radii, foliage')
            check('deterministic complete production model', fingerprint(generate(seed)) == original_fingerprint, seed, fingerprint=original_fingerprint)
        report['complete'] = True
    except BaseException as exc:
        report['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    finally:
        after = inventory()
        report['source_after'] = after
        report['source_unchanged'] = before == after == dict(frozen_sources)
        report['core_failed'] = [c['name'] for c in report['checks'] if c['status'] == 'fail' and not c['auxiliary']]
        report['auxiliary_failed_count'] = sum(c['status'] == 'fail' and c['auxiliary'] for c in report['checks'])
        report['core_all_passed'] = report['complete'] and not report['core_failed'] and report['source_unchanged']
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', 'utf-8')
    print(json.dumps({'output': str(output), 'complete': report['complete'], 'core_all_passed': report['core_all_passed'], 'auxiliary_failed_count': report['auxiliary_failed_count']}))
    return 0 if report['core_all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
