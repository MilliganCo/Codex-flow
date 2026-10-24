"""Independent case09 full-model geometry checks. Execute only in reviewed SDK sandbox."""
from __future__ import annotations
import argparse
import dataclasses
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys
import traceback
from types import MappingProxyType

AXES = ('x', 'y', 'z', 'w')
HERE = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def manifest(root):
    return {str(p.relative_to(root)).replace('\\', '/'): sha(p)
            for p in sorted(root.rglob('*')) if p.is_file()
            and '__pycache__' not in p.parts and '.tmp' not in p.parts}

def vec(p):
    return tuple(getattr(p, a) for a in AXES)

def rank_xyz(points):
    origin = points[0]
    rows = [[p[j]-origin[j] for j in range(3)] for p in points]
    scale = max((abs(v) for row in rows for v in row), default=0.)
    tolerance = max(1e-10, scale*1e-10)
    pivot = 0
    for col in range(3):
        index = max(range(pivot, len(rows)), key=lambda i: abs(rows[i][col]), default=pivot)
        if index >= len(rows) or abs(rows[index][col]) <= tolerance:
            continue
        rows[pivot], rows[index] = rows[index], rows[pivot]
        divisor = rows[pivot][col]
        rows[pivot] = [v/divisor for v in rows[pivot]]
        for i in range(pivot+1, len(rows)):
            multiple = rows[i][col]
            rows[i] = [a-multiple*b for a, b in zip(rows[i], rows[pivot])]
        pivot += 1
    return pivot, scale, tolerance

def fingerprint(tree):
    return hashlib.sha256(json.dumps(dataclasses.asdict(tree), sort_keys=True,
                                      separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def near(a, b, rel=1e-10, abs_=1e-10):
    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_)

def matrix(operator, angle, point_class):
    columns = [vec(operator(point_class(*(1. if i == j else 0. for i in range(4))), angle))
               for j in range(4)]
    return [[columns[j][i] for j in range(4)] for i in range(4)]

def matmul(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]

def determinant(m):
    import itertools
    return sum((-1 if sum(p[i] > p[j] for i in range(4) for j in range(i+1, 4)) % 2 else 1)
               * math.prod(m[i][p[i]] for i in range(4)) for p in itertools.permutations(range(4)))

def identity_close(m):
    return all(near(m[i][j], float(i == j)) for i in range(4) for j in range(4))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--solution', '--solution-root', dest='solution', type=Path, required=True)
    parser.add_argument('--id', '--solution-id', dest='id', choices=('17','18'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.solution.resolve()
    frozen_sources = MappingProxyType(manifest(root))
    report = {'protocol': 'geometry-case09', 'solution': 'solution-'+args.id,
              'checks': [], 'errors': [], 'source_before': dict(frozen_sources),
              'checker_hashes': {p.name: sha(p) for p in (Path(__file__), HERE/'evaluator.py', HERE/'rubric.json')},
              'adapter': {'plane':'XW', 'sigma':1, 'vector_orientation':'column',
                          'rotation_order':'XW, 4D perspective, yaw, pitch, 3D perspective, cell aspect',
                          'operator_units':'radians' if args.id == '17' else 'degrees'}}
    def check(name, passed, seed=None, **measurements):
        report['checks'].append({'property':name, 'seed':seed,
                                 'status':'pass' if passed else 'fail', **measurements})
    try:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(root))
        model = importlib.import_module('ascii_tree.model')
        render = importlib.import_module('ascii_tree.render')
        app_module = importlib.import_module('ascii_tree.app')
        projection = importlib.import_module('ascii_tree.projection') if args.id == '17' else render
        Point = model.Point4 if args.id == '17' else model.Point
        operator = projection.rotate_xw
        convert = math.radians if args.id == '17' else float
        # Convention fixed from each production rotate_xw expression before execution.
        for degrees in (0., 37., 90.):
            angle = convert(degrees)
            m = matrix(operator, angle, Point)
            c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
            signed = [[c,0.,0.,-s],[0.,1.,0.,0.],[0.,0.,1.,0.],[s,0.,0.,c]]
            check('rotation.signed_basis', all(near(m[i][j],signed[i][j]) for i in range(4) for j in range(4)),
                  degrees=degrees, matrix=m, source='ascii_tree/'+('projection.py' if args.id == '17' else 'render.py')+':rotate_xw')
            transpose = [list(row) for row in zip(*m)]
            check('rotation.orthogonal', identity_close(matmul(transpose,m)), degrees=degrees)
            check('rotation.determinant', near(determinant(m),1.), degrees=degrees, determinant=determinant(m))
            check('rotation.inverse', identity_close(matmul(matrix(operator,-angle,Point),m)), degrees=degrees)
            if degrees == 0:
                check('rotation.zero_identity',identity_close(m))
        for seed in (42,137):
            tree = model.generate_tree(seed)
            skeleton_objects = [p for segment in tree.segments for p in (segment.start,segment.end)]
            leaf_objects = [leaf.point if args.id == '17' else leaf.center for leaf in tree.leaves]
            full_objects = skeleton_objects+leaf_objects
            skeleton = [vec(p) for p in skeleton_objects]
            full = [vec(p) for p in full_objects]
            for label, points in (('skeleton',skeleton), ('full_model',full)):
                finite = bool(points) and all(len(p)==4 and all(math.isfinite(v) for v in p) for p in points)
                check(label+'.finite_xyzw',finite,seed,point_count=len(points),unique_points=len(set(points)))
                rank,scale,tolerance = rank_xyz(points)
                check(label+'.affine_xyz_rank',rank==3,seed,rank=rank,scale=scale,pivot_tolerance=tolerance)
                ws = [p[3] for p in points]
                span = max(ws)-min(ws)
                check(label+'.variable_w',len(set(ws))>1 and span>1e-8,seed,w_span=span,distinct_w=len(set(ws)))
            roots = [i for i,s in enumerate(tree.segments) if s.parent is None]
            references = all(s.parent is None or isinstance(s.parent,int) and 0<=s.parent<len(tree.segments) and s.parent!=i
                             for i,s in enumerate(tree.segments))
            connections = all(s.parent is None or vec(s.start)==vec(tree.segments[s.parent].end)
                              for s in tree.segments) if references else False
            children = {i:[] for i in range(len(tree.segments))}
            if references:
                for i,s in enumerate(tree.segments):
                    if s.parent is not None: children[s.parent].append(i)
            reached = set()
            queue = roots[:]
            while queue:
                i = queue.pop()
                if i in reached: continue
                reached.add(i)
                queue.extend(children[i])
            check('graph.connected_rooted_branching',references and connections and len(roots)==1 and len(reached)==len(tree.segments)
                  and max(map(len,children.values()),default=0)>1,seed,edge_count=len(tree.segments),root_count=len(roots),
                  reachable_count=len(reached),max_children=max(map(len,children.values()),default=0))
            lengths = [math.sqrt(sum((getattr(s.end,a)-getattr(s.start,a))**2 for a in AXES[:3])) for s in tree.segments]
            radii = [r for s in tree.segments for r in (s.radius_start,s.radius_end)]
            check('graph.positive_lengths_radii',all(math.isfinite(v) and v>1e-12 for v in lengths)
                  and all(math.isfinite(v) and v>0 for v in radii),seed,min_length=min(lengths),min_radius=min(radii),leaf_count=len(leaf_objects))
            for degrees in (0.,37.,90.):
                angle = convert(degrees)
                maximum_norm_error = maximum_inverse_error = 0.
                success = True
                for p in full_objects:
                    q = operator(p,angle)
                    restored = operator(q,-angle)
                    before_norm = sum(v*v for v in vec(p))
                    after_norm = sum(v*v for v in vec(q))
                    maximum_norm_error = max(maximum_norm_error,abs(before_norm-after_norm))
                    maximum_inverse_error = max(maximum_inverse_error,max(abs(a-b) for a,b in zip(vec(p),vec(restored))))
                    success &= near(before_norm,after_norm) and all(near(a,b) for a,b in zip(vec(p),vec(restored)))
                check('rotation.full_points_norm_inverse',success,seed,degrees=degrees,point_count=len(full_objects),
                      max_norm_squared_error=maximum_norm_error,max_inverse_component_error=maximum_inverse_error)
            # Reproduce the actual point path independently, including base framing, cell aspect and camera signs.
            for degrees in (0.,37.):
                width,height = 100,40
                if args.id == '17':
                    center = vec(tree.center)
                    span_x,span_y = tree.span
                    scale = max(.015,min(max(1,width-6)/(span_x*2.),max(1,height-4)/span_y))*.91
                    yaw,pitch = math.radians(25.),math.radians(-8.)
                    production = projection.Projector(tree.center,width,height,scale,'4d',yaw,pitch,math.radians(degrees),2.,0.)
                    parameters = {'width':width,'height':height,'scale':scale,'center':center,'yaw':25.,'pitch':-8.,'angle4d':degrees,'aspect':2.,'time':0.}
                else:
                    yaw,pitch = math.radians(-22. % 360),math.radians(8.)
                    scale = min(height/14.4,width*.5/16)*.8
                    view = render.View(mode='4d',yaw=-22.,pitch=8.,angle4d=degrees)
                    production = lambda p: render.project(p,view,width,height)
                    parameters = {'width':width,'height':height,'scale':scale,'center_y':6.,'W':'8*(w-.5)','yaw':-22.,'pitch':8.,'angle4d':degrees,'aspect':.5,'time':0.}
                def independent(p):
                    x,y,z,w = vec(p)
                    if args.id == '17':
                        x,y,z,w = [a-b for a,b in zip((x,y,z,w),center)]
                        distance4,distance3 = 18.,30.
                    else:
                        y,w = y-6.,(w-.5)*8
                        distance4,distance3 = 16.,24.
                    c,s = math.cos(math.radians(degrees)),math.sin(math.radians(degrees))
                    x,w = c*x-s*w,s*x+c*w
                    denominator4 = distance4-w
                    if denominator4<.5: return None
                    k4 = distance4/denominator4
                    x,y,z = x*k4,y*k4,z*k4
                    x,z = math.cos(yaw)*x+math.sin(yaw)*z,-math.sin(yaw)*x+math.cos(yaw)*z
                    y,z = math.cos(pitch)*y-math.sin(pitch)*z,math.sin(pitch)*y+math.cos(pitch)*z
                    depth = distance3-z if args.id == '17' else distance3+z
                    if depth<.5: return None
                    k3 = distance3/depth
                    return ((width-1)/2+x*scale*2*k3,(height-1)/2-y*scale*k3,depth,
                            k3*k4 if args.id == '17' else scale*k3*k4)
                maximum_error = 0.
                compared = clipped = 0
                okay = True
                for p in full_objects:
                    actual = production(p)
                    reference = independent(p)
                    if actual is None or reference is None:
                        okay &= actual is None and reference is None
                        clipped += 1
                        continue
                    actual_vector = (actual.x,actual.y,actual.depth,actual.magnification if args.id == '17' else actual.scale)
                    maximum_error = max(maximum_error,max(abs(a-b) for a,b in zip(actual_vector,reference)))
                    okay &= all(math.isclose(a,b,rel_tol=2e-10,abs_tol=2e-9) for a,b in zip(actual_vector,reference))
                    compared += 1
                check('projection.full_sequential_composition',okay,seed,point_count=len(full_objects),compared=compared,clipped=clipped,
                      max_absolute_error=maximum_error,parameters=parameters,
                      source='ascii_tree/'+('projection.py:Projector.__call__' if args.id == '17' else 'render.py:project'))
            # Direct pathological inputs exercise production projection rather than a repaired adapter.
            cases = []
            if args.id == '17':
                for w in (18.,18.-1e-12,18.1): cases.append(('4D denominator '+str(w),lambda w=w: projection.project_4d(Point(1.,2.,3.,w))))
                for z in (30.,30.-1e-12,31.):
                    pr = projection.Projector(Point(0.,0.,0.,0.),100,40,1.,'3d',0.,0.,0.)
                    cases.append(('3D denominator '+str(z),lambda z=z,pr=pr: pr(Point(1.,2.,z,0.))))
                cases.extend((('nonfinite '+axis+' '+str(v),lambda axis=axis,v=v: production(Point(*(v if a==axis else 0. for a in AXES))))
                              for axis in AXES for v in (float('nan'),float('inf'),-float('inf'))))
            else:
                for w in (2.5,2.5-1e-12,2.6): cases.append(('4D denominator '+str(w),lambda w=w: render.project_4d(Point(1.,2.,3.,w),0.)))
                for z in (-24.,-24.+1e-12,-25.): cases.append(('3D denominator '+str(z),lambda z=z: render.project(Point(1.,6.,z,0.),render.View(mode='3d',yaw=0.,pitch=0.),100,40)))
                cases.extend((('nonfinite '+axis+' '+str(v),lambda axis=axis,v=v: render.project(Point(*(v if a==axis else 0. for a in AXES)),render.View(mode='4d'),100,40))
                              for axis in AXES for v in (float('nan'),float('inf'),-float('inf'))))
            for label,call in cases:
                try:
                    result = call()
                    values = dataclasses.astuple(result) if dataclasses.is_dataclass(result) else result
                    safe = result is None or all(math.isfinite(v) and abs(v)<1e12 for v in values)
                    check('projection.pathological_input',safe,seed,case=label,result=None if result is None else [str(v) if not math.isfinite(v) else v for v in values])
                except Exception as exc:
                    check('projection.pathological_input',False,seed,case=label,error=type(exc).__name__+': '+str(exc))
            initial = fingerprint(tree)
            explorer = app_module.Explorer(tree) if args.id == '17' else app_module.Explorer(seed)
            transitions = []
            for key in ('1','2','3',']','right','up','[','r'):
                (explorer.handle_key if args.id == '17' else explorer.handle)(key)
                transitions.append({'key':key,'fingerprint':fingerprint(explorer.tree)})
            check('model.stable_across_modes_angles',all(t['fingerprint']==initial for t in transitions),seed,
                  initial_fingerprint=initial,transitions=transitions)
            (explorer.handle_key if args.id == '17' else explorer.handle)('g')
            check('model.new_seed_operation',explorer.tree.seed==seed+1 and fingerprint(explorer.tree)!=initial,seed,new_seed=explorer.tree.seed)
    except Exception:
        report['errors'].append(traceback.format_exc())
    finally:
        report['source_after'] = manifest(root)
        report['sources_unchanged'] = dict(frozen_sources)==report['source_after']
        report['completion'] = 'complete' if not report['errors'] else 'incomplete'
        report['all_checks_passed'] = not report['errors'] and bool(report['checks']) and all(c['status']=='pass' for c in report['checks'])
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(json.dumps({'output':str(args.output),'completion':report['completion'],'checks':len(report['checks']),
                          'failed':sum(c['status']=='fail' for c in report['checks']),'sources_unchanged':report['sources_unchanged']}))
    return 0 if report['completion']=='complete' else 1

if __name__=='__main__':
    raise SystemExit(main())
