"""Frozen, independent-worktree A/B and ablation runner (subscription only)."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, time
from .config import Config
from .contracts import PolicyError
from .native import run, executable, subscription
from .telemetry import write_json, utc
from .cli import FLOW_INSTRUCTIONS, BASE_INSTRUCTIONS

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def delegation_evidence(metrics,cfg):
    """Transport profiles describe requests; native spawn IDs prove children."""
    profiles=[]
    for request in metrics.get('subscription',{}).get('requests',[]):
        if (request.get('status')=='completed' and request.get('actual_model') and
                (request.get('model')!=cfg.model or request.get('effort')!=cfg.effort)):
            profile={'actual_model':request['actual_model'],'requested_model':request.get('model'),
                     'requested_effort':request.get('effort')}
            if profile not in profiles:profiles.append(profile)
    children=metrics.get('native_child_ids')
    confirmed=bool(isinstance(children,list) and children and metrics.get('delegation_evidence') in
                   ('native_completed_spawn','native_parent_link_and_usage_metadata'))
    return {'observed_role_profile':bool(profiles),'observed_role_profiles':profiles,
            'multi_agent_verified':confirmed,
            'multi_agent_evidence':children if confirmed else None}

def hardware():
    memory=None
    if os.name=='nt':
        import ctypes
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        m=Memory();m.length=ctypes.sizeof(m)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):memory=m.total
    else:
        try:memory=os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')
        except (ValueError,OSError):pass
    return {'cpu':platform.processor(),'logical_cpus':os.cpu_count(),'ram_bytes':memory,'machine':platform.machine()}

def git(root,*args):
    p=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True,timeout=30)
    if p.returncode:raise PolicyError('benchmark Git operation failed: '+p.stderr[:200])
    return p.stdout.strip()

def probe(exe,workspace,run_root,cfg,*,deadline=None,request_budget=None,denied_reads=()):
    """Explicit diagnostic only; plan coverage cannot authorize instruction adoption."""
    from .harness import GuardedHarness,HarnessProposal,EvaluationResult
    observations=[]
    deadline=deadline or time.monotonic()+cfg.timeout_s
    candidate_instructions=FLOW_INSTRUCTIONS+'\nUse explicit acceptance checkpoints and verification actions before handoff.'
    for name,tested_instructions in [('baseline',FLOW_INSTRUCTIONS),('candidate',candidate_instructions)]:
        w=run_root/('probe-'+name);w.mkdir()
        git(w,'init','-q')
        prompt='Create only plan.json, a JSON object with fields geometry, projection4d, occlusion, controls, verification. Each field is a short concrete plan for ASCII Tree Explorer. Do not implement code, delegate, or read outside this workspace.'
        remaining=int(deadline-time.monotonic())
        if remaining<=0:
            m={'status':'budget_exhausted','wall_clock_s':0.0,'input_tokens':None,'output_tokens':None}
        else:
            extra={}
            if request_budget is not None:extra['request_budget']=request_budget
            if denied_reads:extra['denied_reads']=denied_reads
            m=run(exe,w,replace(cfg,timeout_s=min(remaining,120)),prompt,run_root/('probe-run-'+name),instructions=tested_instructions,**extra)
        quality=0
        try:
            plan=json.loads((w/'plan.json').read_text(encoding='utf-8-sig'))
            quality=sum(isinstance(plan.get(k),str) and len(plan[k])>=20 for k in ['geometry','projection4d','occlusion','controls','verification'])
        except (OSError,ValueError):pass
        observations.append((m,EvaluationResult(float(quality),m['wall_clock_s'],m['status']=='completed_unverified',quality==5,name)))
    proposal=HarnessProposal('acceptance-checkpoints',candidate_instructions,
                             'Improve complete plan coverage without changing task acceptance',('baseline','candidate'))
    decision=GuardedHarness(workspace).compare(proposal,observations[0][1],observations[1][1],adopt=False)
    return {'status':'degraded','mode':'Harness2-inspired','upstream_probes':0,'inspired_probes':2,
            'decision':decision,'application_quality_eligible':False,'runs':[o[0] for o in observations],
            'limitation':'one plan-coverage pair; does not establish application-quality improvement'}

def prepare(root,task,evaluator,exe,timeout,groups='ABCD'):
    if root.exists():raise PolicyError('experiment root already exists; never overwrite a frozen experiment')
    if not task.is_file() or not evaluator.is_file():raise PolicyError('task/evaluator missing')
    root.mkdir(parents=True)
    scaffold=root/'scaffold';scaffold.mkdir()
    (scaffold/'TASK.md').write_bytes(task.read_bytes())
    (scaffold/'.gitignore').write_text('__pycache__/\n*.pyc\n.tmp/\n.home/\n.codex-flow/\n',encoding='utf-8')
    git(scaffold,'init','-q');git(scaffold,'config','user.name','Codex Flow Benchmark')
    git(scaffold,'config','user.email','benchmark@users.noreply.github.com')
    git(scaffold,'add','.');git(scaffold,'commit','-qm','Freeze common empty benchmark scaffold')
    commit=git(scaffold,'rev-parse','HEAD')
    for group in groups:git(scaffold,'worktree','add','--detach',str(root/('workspace-'+group)),commit)
    frozen=root/'frozen';frozen.mkdir()
    (frozen/'TREE_BENCHMARK_TASK.md').write_bytes(task.read_bytes())
    manifest={'experiment_id':root.name,'created_utc':utc(),'calendar_date':utc().split('T')[0],'calendar_timezone':'UTC','task_sha256':sha(task),
              'scaffold_sha':commit,'evaluator_sha256':sha(evaluator),'rubric_sha256':sha(evaluator.with_name('rubric.json')),
              'codex_version':subprocess.run([exe,'--version'],capture_output=True,text=True,timeout=10).stdout.strip(),
              'root_model':'gpt-6.1-sol','root_effort':'xhigh','os':platform.platform(),'python':platform.python_version(),
              'cpu_count':os.cpu_count(),'timeout_s_per_arm':timeout,'max_helpers':3,'max_depth':1,
              'hardware':hardware(),'terminal':'headless generation; independent Windows ConPTY evaluation',
              'selected_groups':list(groups),'initial_order':[list(pair) for pair in (('A','B'),('C','D')) if all(g in groups for g in pair)],'auth_class':'ChatGPT subscription; common credential home, no token copying',
              'isolation':{'worktrees':True,'home_temp_cache':True,'shared_codex_auth_home':True,
                           'project_sqlite_logs':True,'parallel_parent_persistence':True,'cross_arm_read_isolation':False,
                           'shared_deny_policy':True,'hidden_evaluator_and_prior_solutions_denied':True,
                           'boundary_smoke':'single deny works; reciprocal Windows profiles interfere through shared CodexSandboxUsers ACL; custom roles inherit parent permissions'},
              'validity':'degraded physical read isolation; independent contexts/workspaces and no operator transfer; Harness2-inspired only; per-arm provider trace required',
              'max_model_requests_per_arm_including_probes':80,
              'flow_treatment':{'harness':'enabled guard; calibration deferred; zero automatic online probes',
                                'helper':'bounded readonly evidence; instruction requests concurrent root implementation',
                                'phase_reserve':'final 20 percent planning instruction; not independently enforced'},
              'acceptance':'score>=80 AND actual 4D geometry/rotation/projection AND runnable app',
              'quality_scores_frozen':{'2d':12,'3d':13,'4d':20,'ux':12,'aesthetics':12,'reliability':10,'tests':9,'maintainability':7,'readme':5},
              'runtime_sha256':{p.name:sha(p) for p in Path(__file__).parent.glob('*.py')}}
    write_json(root/'experiment-manifest.json',manifest)
    return manifest

def execute(root:Path,task:Path,evaluator:Path,codex=None,mercury_root=None,timeout=1200,*,execute=False,protect_paths=(),groups='ABCD'):
    if type(timeout) is not int or not 1<=timeout<=3600:raise PolicyError('invalid timeout')
    if groups not in ('AB','ABCD'):raise PolicyError('groups must be AB or ABCD')
    exe=executable(codex);subscription(exe)
    root=root.resolve();task=task.resolve();evaluator=evaluator.resolve()
    protect_paths=tuple(Path(p).resolve() for p in protect_paths)
    if any(not p.exists() for p in protect_paths):raise PolicyError('protected read paths must already exist')
    if not execute:return {'dry_run':True,'groups':list(groups),'root':str(root),'provider_calls':0,'isolation_limit':'shared auth; filesystem read isolation unavailable'}
    manifest=prepare(root,task,evaluator,exe,timeout,groups)
    prompt=(root/'frozen/TREE_BENCHMARK_TASK.md').read_text(encoding='utf-8-sig')
    cfg=Config(enabled=True,mode='benchmark',timeout_s=timeout)
    # Reciprocal per-arm read denials are unsafe on this Windows sandbox version:
    # its CodexSandboxUsers deny ACLs affect concurrently running native profiles.
    # All arms receive one identical policy instead. Previous solutions and the
    # hidden evaluator remain denied; current-peer isolation is explicitly soft.
    shared_denied=tuple(p for p in root.parent.iterdir() if p.is_dir() and p!=root and (p/'experiment-manifest.json').is_file())
    shared_denied+=(evaluator.parent,)+protect_paths
    def arm(group):
        start=time.monotonic();workspace=root/('workspace-'+group);details={}
        from .subscription import RequestBudget
        budget=RequestBudget(cfg.max_model_requests)
        denied=shared_denied
        from .mercury import MercuryBridge
        from .policy import route
        if group in 'BC':
            details['mercury']=MercuryBridge(mercury_root).decide({'complexity':'high','independent_steps':3,'conflicting_paths':False,'risk_level':'low'},enabled=True)
        if group in 'BD':
            from .harness import runtime_guard
            details['harness']=runtime_guard()
        decision=route(independent_steps=1 if group=='A' else 3,single=group=='A',mercury=details.get('mercury'))
        instructions=BASE_INSTRUCTIONS if group=='A' else FLOW_INSTRUCTIONS
        preparation_s=time.monotonic()-start
        remaining=int(timeout-preparation_s)
        if remaining<=0:raise PolicyError('total task budget exhausted during routing; task execution not started')
        m=run(exe,workspace,replace(cfg,timeout_s=remaining),prompt,root/('run-'+group),parallel=group!='A' and decision.strategy=='parallel',instructions=instructions,
              request_budget=budget,denied_reads=denied)
        m.update(group=group,task_sha256=manifest['task_sha256'],scaffold_sha=manifest['scaffold_sha'],
                 total_arm_s=round(time.monotonic()-start,3),strategy=decision.strategy,
                 orchestration_frontload_s=round(preparation_s,3),
                 mercury_real_calls=details.get('mercury',{}).get('successful_calls',0),harness2_real_probes=0,
                 harness_inspired_probes=details.get('harness',{}).get('inspired_probes',0),
                 time_to_first_working_demo_s=None,quality_score=None,tests_passed=None,tests_total=None,
                 integration_status='disabled' if group=='A' else 'degraded',details=details)
        m.update(delegation_evidence(m,cfg))
        m['model_requests_total']=budget.used
        if details.get('harness',{}).get('decision',{}).get('adopted') and m['status']!='completed_unverified':
            from .harness import GuardedHarness
            details['harness']['rollback']=GuardedHarness(workspace).rollback(details['harness']['decision']['proposal']['id'])
        if group!='A':
            m['root_input_tokens']=m['input_tokens'];m['root_output_tokens']=m['output_tokens']
            m['input_tokens']=None;m['output_tokens']=None;m['cached_tokens']=None
            m['usage_limitation']='root/probe usage retained; aggregate native subagent usage not exposed by this JSON stream'
        phases=[m]+details.get('harness',{}).get('runs',[])
        aggregates=[p.get('all_requests_usage') for p in phases]
        if all(a is not None for a in aggregates):
            m['input_tokens']=sum(a['input_tokens'] for a in aggregates)
            m['output_tokens']=sum(a['output_tokens'] for a in aggregates)
            m['cached_tokens']=sum(a['cached_tokens'] for a in aggregates) if all(a.get('cached_tokens') is not None for a in aggregates) else None
            m['usage_limitation']=None
        write_json(root/('metrics-'+group+'.json'),m)
        return m
    outcomes={}
    for pair in [('A','B'),('C','D')]:
        if not all(g in groups for g in pair):continue
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending={g:pool.submit(arm,g) for g in pair}
            for g,future in pending.items():
                try:outcomes[g]=future.result()
                except Exception as e:
                    outcomes[g]={'group':g,'status':'failed','reason':type(e).__name__}
                    write_json(root/('metrics-'+g+'.json'),outcomes[g])
    write_json(root/'metrics.json',outcomes)
    return outcomes

def report(root):
    return {'manifest':json.loads((root/'experiment-manifest.json').read_text(encoding='utf-8')),
            'metrics':{g:json.loads((root/('metrics-'+g+'.json')).read_text(encoding='utf-8')) for g in 'ABCD' if (root/('metrics-'+g+'.json')).exists()}}
