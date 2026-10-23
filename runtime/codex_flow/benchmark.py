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

def git(root,*args):
    p=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True,timeout=30)
    if p.returncode:raise PolicyError('benchmark Git operation failed: '+p.stderr[:200])
    return p.stdout.strip()

def probe(exe,workspace,run_root,cfg):
    """One paired instruction probe, scored for plan coverage, not application quality."""
    from .harness import GuardedHarness,HarnessProposal,EvaluationResult
    observations=[]
    candidate_instructions=FLOW_INSTRUCTIONS+'\nUse explicit acceptance checkpoints and verification actions before handoff.'
    for name,tested_instructions in [('baseline',FLOW_INSTRUCTIONS),('candidate',candidate_instructions)]:
        w=run_root/('probe-'+name);w.mkdir()
        git(w,'init','-q')
        prompt='Create only plan.json, a JSON object with fields geometry, projection4d, occlusion, controls, verification. Each field is a short concrete plan for ASCII Tree Explorer. Do not implement code, delegate, or read outside this workspace.'
        m=run(exe,w,replace(cfg,timeout_s=min(cfg.timeout_s,120)),prompt,run_root/('probe-run-'+name),instructions=tested_instructions)
        quality=0
        try:
            plan=json.loads((w/'plan.json').read_text(encoding='utf-8-sig'))
            quality=sum(isinstance(plan.get(k),str) and len(plan[k])>=20 for k in ['geometry','projection4d','occlusion','controls','verification'])
        except (OSError,ValueError):pass
        observations.append((m,EvaluationResult(float(quality),m['wall_clock_s'],m['status']=='completed_unverified',quality==5,name)))
    proposal=HarnessProposal('acceptance-checkpoints',candidate_instructions,
                             'Improve complete plan coverage without changing task acceptance',('baseline','candidate'))
    decision=GuardedHarness(workspace).compare(proposal,observations[0][1],observations[1][1],adopt=True)
    return {'status':'degraded','mode':'Harness2-inspired','upstream_probes':0,'inspired_probes':2,
            'decision':decision,'runs':[o[0] for o in observations],
            'limitation':'one plan-coverage pair; does not establish application-quality improvement'}

def prepare(root,task,evaluator,exe,timeout):
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
    for group in 'ABCD':git(scaffold,'worktree','add','--detach',str(root/('workspace-'+group)),commit)
    frozen=root/'frozen';frozen.mkdir()
    (frozen/'TREE_BENCHMARK_TASK.md').write_bytes(task.read_bytes())
    manifest={'experiment_id':root.name,'created_utc':utc(),'calendar_date':'2026-10-23','task_sha256':sha(task),
              'scaffold_sha':commit,'evaluator_sha256':sha(evaluator),'rubric_sha256':sha(evaluator.with_name('rubric.json')),
              'codex_version':subprocess.run([exe,'--version'],capture_output=True,text=True,timeout=10).stdout.strip(),
              'root_model':'gpt-6.1-sol','root_effort':'xhigh','os':platform.platform(),'python':platform.python_version(),
              'cpu_count':os.cpu_count(),'timeout_s_per_arm':timeout,'max_helpers':3,'max_depth':1,
              'initial_order':[['A','B'],['C','D']],'auth_class':'ChatGPT subscription; common credential home, no token copying',
              'isolation':{'worktrees':True,'ephemeral_contexts':True,'home_temp_cache':True,'shared_codex_auth_home':True,
                           'read_isolation':False,'evidence':'workspace-write boundary probe could read sibling sentinel'},
              'validity':'degraded-isolation; Harness2-inspired only; Mercury availability requires actual per-arm trace',
              'acceptance':'score>=80 AND actual 4D geometry/rotation/projection AND runnable app',
              'quality_scores_frozen':{'2d':12,'3d':13,'4d':20,'ux':12,'aesthetics':12,'reliability':10,'tests':9,'maintainability':7,'readme':5},
              'runtime_sha256':{p.name:sha(p) for p in Path(__file__).parent.glob('*.py')}}
    write_json(root/'experiment-manifest.json',manifest)
    return manifest

def execute(root:Path,task:Path,evaluator:Path,codex=None,mercury_root=None,timeout=1200,*,execute=False):
    if type(timeout) is not int or not 1<=timeout<=3600:raise PolicyError('invalid timeout')
    exe=executable(codex);subscription(exe)
    root=root.resolve();task=task.resolve();evaluator=evaluator.resolve()
    if not execute:return {'dry_run':True,'groups':['A','B','C','D'],'root':str(root),'provider_calls':0,'isolation_limit':'shared auth; filesystem read isolation unavailable'}
    manifest=prepare(root,task,evaluator,exe,timeout)
    prompt=(root/'frozen/TREE_BENCHMARK_TASK.md').read_text(encoding='utf-8-sig')
    cfg=Config(enabled=True,mode='benchmark',timeout_s=timeout)
    def arm(group):
        start=time.monotonic();workspace=root/('workspace-'+group);details={}
        from .mercury import MercuryBridge
        from .policy import route
        if group in 'BC':
            details['mercury']=MercuryBridge(mercury_root).decide({'complexity':'high','independent_steps':3,'conflicting_paths':False,'risk_level':'low'},enabled=True)
        if group in 'BD':
            probe_root=root/('harness-'+group);probe_root.mkdir()
            details['harness']=probe(exe,workspace,probe_root,cfg)
        decision=route(independent_steps=1 if group=='A' else 3,single=group=='A',mercury=details.get('mercury'))
        instructions=BASE_INSTRUCTIONS if group=='A' else FLOW_INSTRUCTIONS
        active=workspace/'.codex-flow/lessons/active.txt'
        if active.is_file():instructions=active.read_text(encoding='utf-8')
        remaining=max(1,timeout-int(time.monotonic()-start))
        m=run(exe,workspace,replace(cfg,timeout_s=remaining),prompt,root/('run-'+group),parallel=group!='A' and decision.strategy=='parallel',instructions=instructions)
        m.update(group=group,task_sha256=manifest['task_sha256'],scaffold_sha=manifest['scaffold_sha'],
                 total_arm_s=round(time.monotonic()-start,3),strategy=decision.strategy,
                 mercury_real_calls=details.get('mercury',{}).get('successful_calls',0),harness2_real_probes=0,
                 harness_inspired_probes=details.get('harness',{}).get('inspired_probes',0),
                 time_to_first_working_demo_s=None,quality_score=None,tests_passed=None,tests_total=None,
                 integration_status='disabled' if group=='A' else 'degraded',details=details)
        if group!='A':
            m['root_input_tokens']=m['input_tokens'];m['root_output_tokens']=m['output_tokens']
            m['input_tokens']=None;m['output_tokens']=None;m['cached_tokens']=None
            m['usage_limitation']='root/probe usage retained; aggregate native subagent usage not exposed by this JSON stream'
        write_json(root/('metrics-'+group+'.json'),m)
        return m
    outcomes={}
    for groups in [('A','B'),('C','D')]:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending={g:pool.submit(arm,g) for g in groups}
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
