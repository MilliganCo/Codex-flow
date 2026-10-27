"""Opt-in runtime CLI. Offline legacy flowctl commands are preserved separately."""
from __future__ import annotations
import argparse
from dataclasses import asdict, replace
from pathlib import Path
import json, sys, uuid, time
from .config import Config, load
from .contracts import PolicyError, inside
from .telemetry import write_json, replay

FLOW_INSTRUCTIONS='''You coordinate Codex Flow as GPT-6.1 Sol xhigh. Preserve every task acceptance condition.
Read applicable local rules; this workflow is sufficient without global skill discovery.
The chief is the sole application-file writer and integrator. Own and test numerical,
parsing, security and atomic/transactional boundaries on the production path, including
applicable malformed/empty/nonfinite/near-zero cases. Ordinary examples alone are insufficient.
Prefer one cohesive implementation slice for bounded work: production code, required
tests, examples and README together, followed by a finite acceptance-check batch.
Split only at a real dependency or uncertainty; do not create extra planning, smoke,
documentation or status stages merely to demonstrate activity. Batch independent tools.
In parallel mode, promptly start one native reviewer (agent_type=reviewer, Sol high)
alongside useful chief work. Supply requirements; ask for at most five acceptance risks
and boundary cases, no production code. Its initial pass uses no tools, file reads or
polling. Never serialize implementation behind that review. Receive and apply relevant
evidence once before acceptance; follow up only for an observed unresolved defect.
Helpers are read-only, never delegate, and never query budget status. Maximum three
globally, one delegation level; add helpers only for independent work that justifies cost.
A failed or unused helper is degraded execution; do not retry or claim delegation.
Do not duplicate completed work or repeat unchanged passing checks. Await running work
without repeated short polling. Budget status is optional decision support for the chief,
not a mandatory checkpoint: query only when needed, at most twice unless the task explicitly
requires a protocol stress check; batch with necessary work, never after acceptance.
Keep verification within the shared hard time/request budget. For platform-sensitive
behavior verify actual startup, control and shutdown before acceptance; inspect a real
representative render when required. Report pass/fail/not-run and actual artifacts.
Finish when acceptance evidence is complete; avoid optional polish or extra test frameworks.
All work must stay within the assigned workspace. Do not read sibling workspaces/evaluators,
global user files, credentials, memories or prior solutions. Do not use paid APIs, internet,
publication, deployment, sandbox bypass, global config changes or external applications.
Do not inspect .codex-flow/native-state, native SQLite databases, session/rollout or
history containers, or historical thread metadata, including inside this workspace.
Do not stage, commit, merge, or alter Git history; the experiment controller owns archives.
Do not claim success from a zero exit alone. Stop only when acceptance is met or blocked.
'''
BASE_INSTRUCTIONS='''Work independently as one GPT-6.1 Sol xhigh agent. Do not delegate.
All work must stay within the assigned workspace. Do not read sibling workspaces/evaluators,
global user files, credentials, memories or prior solutions. Do not use paid APIs, internet,
publication, deployment, sandbox bypass, global config changes or external applications.
Do not inspect .codex-flow/native-state, native SQLite databases, session/rollout or
history containers, or historical thread metadata, including inside this workspace.
Do not stage, commit, merge, or alter Git history; the experiment controller owns archives.
Run relevant finite tests; report pass/fail/not-run and limitations. Preserve task acceptance.
'''

def main(argv=None):
    p=argparse.ArgumentParser(description='Codex Flow opt-in runtime (legacy installer: payload/codex-flow/scripts/flowctl.py)')
    p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--codex');p.add_argument('--config',type=Path)
    sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('doctor');d.add_argument('--deep',action='store_true');d.add_argument('--mercury-root',type=Path);d.add_argument('--live-mercury',action='store_true')
    s=sub.add_parser('integrations');s.add_argument('action',choices=['status'])
    r=sub.add_parser('run');r.add_argument('task',nargs='?');r.add_argument('--task-file',type=Path)
    r.add_argument('--dry-run',action='store_true');r.add_argument('--enable',action='store_true')
    r.add_argument('--strategy',choices=['auto','single','parallel'],default='auto');r.add_argument('--single-agent',action='store_true')
    r.add_argument('--max-agents',type=int);r.add_argument('--no-mercury',action='store_true');r.add_argument('--no-harness2',action='store_true');r.add_argument('--mercury-root',type=Path)
    r.add_argument('--independent-steps',type=int,default=1)
    r.add_argument('--risk-level',choices=['low','normal','medium','high','critical'],default='normal')
    r.add_argument('--conflicting-paths',action='store_true')
    r.add_argument('--timeout',type=int)
    r.add_argument('--acceptance-file',type=Path)
    r.add_argument('--execution-contract',type=Path)
    r.add_argument('--protect-path',type=Path,action='append',default=[])
    v=sub.add_parser('verify',help='Inspect or execute owner-selected external acceptance checks without a model')
    v.add_argument('--acceptance-file',type=Path,required=True)
    v.add_argument('--execute',action='store_true');v.add_argument('--timeout',type=int)
    v.add_argument('--protect-path',type=Path,action='append',default=[])
    w=sub.add_parser('workflow',help='Durable prepare/generate/verify/report stages')
    ws=w.add_subparsers(dest='workflow_action',required=True)
    start=ws.add_parser('start')
    start.add_argument('task',nargs='?');start.add_argument('--task-file',type=Path)
    start.add_argument('--acceptance-file',type=Path,required=True)
    start.add_argument('--execution-contract',type=Path)
    start.add_argument('--enable',action='store_true');start.add_argument('--dry-run',action='store_true')
    start.add_argument('--timeout',type=int);start.add_argument('--max-model-requests',type=int)
    for action in ('status','pause','resume','cancel'):
        action_parser=ws.add_parser(action);action_parser.add_argument('workflow_id')
        if action=='resume':action_parser.add_argument('--enable',action='store_true')
    s=sub.add_parser('runs');s.add_argument('action',choices=['list','show','cancel','replay']);s.add_argument('run_id',nargs='?')
    b=sub.add_parser('benchmark');b.add_argument('action',choices=['tree','report']);b.add_argument('--task-file',type=Path);b.add_argument('--root',type=Path);b.add_argument('--evaluator',type=Path);b.add_argument('--mercury-root',type=Path);b.add_argument('--execute',action='store_true');b.add_argument('--timeout',type=int,default=1200)
    b.add_argument('--protect-path',type=Path,action='append',default=[])
    b.add_argument('--groups',choices=['AB','ABCD'],default='ABCD')
    args=p.parse_args(argv)
    try:
        repo=args.repo.resolve()
        control_only=(args.command=='workflow' and args.workflow_action in ('status','pause','cancel'))
        cfg=Config() if control_only else load(args.config or repo/'.codex-flow/config.json')
        if args.command=='doctor':
            from .doctor import doctor
            out=doctor(args.codex,args.deep,args.mercury_root,args.live_mercury)
        elif args.command=='integrations':
            out={'mercury':{'enabled':cfg.mercury,'status':'configured' if cfg.mercury else 'disabled','validated':False},
                 'harness2':{'enabled':cfg.harness2,'mode':'Harness2-inspired','validated':False}}
        elif args.command=='run':
            started=time.monotonic()
            from .native import executable,run
            from .policy import route
            if args.max_agents is not None:cfg=replace(cfg,max_agents=args.max_agents)
            if args.timeout is not None:cfg=replace(cfg,timeout_s=args.timeout)
            from .budget import ExecutionBudget
            from . import acceptance
            from . import execution_contract
            execution_budget=ExecutionBudget(cfg.timeout_s,cfg.max_model_requests)
            prompt=args.task_file.read_text(encoding='utf-8-sig') if args.task_file else args.task
            if not prompt:raise PolicyError('task or --task-file required')
            if not args.dry_run and not (cfg.enabled or args.enable):raise PolicyError('runtime disabled; use --enable or project config')
            contract=acceptance.load_contract(args.acceptance_file) if args.acceptance_file else None
            execution=execution_contract.load(args.execution_contract,repo) if args.execution_contract else None
            if execution and not contract:raise PolicyError('execution contract requires --acceptance-file')
            protected=acceptance.protected_paths(repo,args.protect_path)
            if contract and not args.dry_run:acceptance.require_backend()
            mercury=None
            decision=route(independent_steps=args.independent_steps,conflicting_paths=args.conflicting_paths,
                           risk_level=args.risk_level,single=args.single_agent or args.strategy=='single')
            if execution:
                assert contract is not None
                decision=execution_contract.admit(execution,contract.inputs,single=args.single_agent or args.strategy=='single',
                                                  conflicting=args.conflicting_paths,risk=args.risk_level)
            if not execution and decision.strategy=='parallel' and cfg.mercury and not args.no_mercury and not args.dry_run:
                from .mercury import MercuryBridge
                mercury=MercuryBridge(args.mercury_root).decide({'complexity':'high','independent_steps':min(args.independent_steps,100),
                    'conflicting_paths':False,'risk_level':'low' if args.risk_level=='normal' else args.risk_level},enabled=True)
                decision=route(independent_steps=args.independent_steps,conflicting_paths=args.conflicting_paths,
                               risk_level=args.risk_level,single=args.single_agent or args.strategy=='single',mercury=mercury)
            if args.dry_run:out={'dry_run':True,'config':asdict(cfg),'route':asdict(decision),'external_calls':0,
                                'acceptance':contract.summary() if contract else {'configured':False},
                                'execution_contract':execution.summary() if execution else {'configured':False}}
            else:
                if not (cfg.enabled or args.enable):raise PolicyError('runtime disabled; use --enable or project config')
                if decision.strategy=='escalate':raise PolicyError(decision.reason)
                cli=executable(args.codex)
                prepared=acceptance.prepare(repo,contract) if contract else None
                frozen_execution=execution_contract.freeze(execution) if execution else None
                from .subscription import RequestBudget
                request_budget=RequestBudget(cfg.max_model_requests)
                harness=None
                if cfg.harness2 and not args.no_harness2:
                    from .harness import runtime_guard
                    harness=runtime_guard()
                instructions=FLOW_INSTRUCTIONS if decision.strategy=='parallel' else BASE_INSTRUCTIONS
                if execution:instructions=execution.instructions()
                active=repo/'.codex-flow/lessons/active.txt'
                if harness and harness['decision']['adopted']:instructions=active.read_text(encoding='utf-8')
                if execution and harness and harness['decision']['adopted']:
                    raise PolicyError('execution contract cannot use an adopted instruction overlay')
                remaining=int(cfg.timeout_s-(time.monotonic()-started))
                if remaining<=0:
                    if harness and harness['decision']['adopted']:
                        from .harness import GuardedHarness
                        GuardedHarness(repo).rollback(harness['decision']['proposal']['id'])
                    raise PolicyError('total task budget exhausted during routing/probes; task execution not started')
                run_dir=repo/'.codex-flow/runs'/uuid.uuid4().hex
                out=run(cli,repo,replace(cfg,timeout_s=remaining),prompt,run_dir,
                        parallel=decision.strategy=='parallel',instructions=instructions,request_budget=request_budget,
                        execution_budget=execution_budget,denied_reads=protected,executor_mode=execution is not None)
                out['execution_s']=out['wall_clock_s']
                execution_evidence=None
                if execution:
                    assert frozen_execution is not None
                    try:execution_evidence=execution_contract.observe(execution,frozen_execution,out,
                                        budget=execution_budget,cancel_file=run_dir/'cancel.request')
                    except (OSError,ValueError,TypeError):
                        execution_evidence={'status':'degraded','verified':False,'reason':'execution_evidence_unavailable'}
                    out['execution_contract']=execution_evidence
                gate=None
                if prepared:
                    gate=(acceptance.verify(cli,repo,prepared,run_dir,execution_budget,protected)
                          if out['status']=='completed_unverified' and (not execution or execution_evidence['verified']) else
                          {'status':'not_run','accepted':False,'reason':'native_or_execution_contract_not_verified'})
                if execution and gate and gate.get('accepted') is True:
                    try:
                        current=execution_contract.observe(execution,frozen_execution,out,
                                        budget=execution_budget,cancel_file=run_dir/'cancel.request')
                        if (not current['verified'] or current['artifact_sha256']!=execution_evidence['artifact_sha256']):
                            current={**current,'verified':False,'status':'degraded','reason':'execution_artifact_drift'}
                        execution_evidence=current
                    except (OSError,ValueError,TypeError):
                        execution_evidence={'status':'degraded','verified':False,'reason':'execution_artifact_drift'}
                acceptance.apply_result(out,gate)
                if execution:
                    out['execution_contract']=execution_evidence
                    if not execution_evidence['verified']:
                        out['status']='execution_contract_failed';out['accepted']=False
                    if (run_dir/'cancel.request').exists():
                        out['status']='cancelled';out['accepted']=False
                    elif execution_budget.remaining_s()<=0:
                        out['status']='timed_out';out['accepted']=False
                out['wall_clock_s']=round(time.monotonic()-started,3)
                out['root_usage']={k:out[k] for k in ('input_tokens','output_tokens','cached_tokens')}
                if decision.strategy=='parallel':
                    for key in ('input_tokens','output_tokens','cached_tokens'):out[key]=None
                out['route']=asdict(decision);out['mercury']=mercury
                out['harness2']=harness or {'status':'disabled'}
                if harness and harness['decision']['adopted'] and out['status'] not in ('completed_unverified','completed_verified'):
                    from .harness import GuardedHarness
                    try:out['harness2']['rollback']=GuardedHarness(repo).rollback(harness['decision']['proposal']['id'])
                    except PolicyError:out['harness2']['rollback_error']='active instruction drift; preserved for review'
                if prepared:
                    out['execution_budget']=execution_budget.snapshot(request_budget.used)
                write_json(repo/'.codex-flow/runs'/out['run_id']/'metrics.json',out)
                if prepared:
                    write_json(run_dir/'control.json',{'pid':None,'status':out['status']})
                    print(json.dumps(out,ensure_ascii=False,indent=2));return 0 if out['accepted'] else 3
        elif args.command=='workflow':
            from .workflow import Engine
            engine=Engine(repo)
            if args.workflow_action=='start':
                if args.timeout is not None:cfg=replace(cfg,timeout_s=args.timeout)
                if args.max_model_requests is not None:cfg=replace(cfg,max_model_requests=args.max_model_requests)
                task=args.task_file.read_text(encoding='utf-8-sig') if args.task_file else args.task
                out=engine.start(cfg,task,args.acceptance_file,args.execution_contract,
                                 exe=args.codex,enable=args.enable,dry_run=args.dry_run)
            elif args.workflow_action=='resume':
                if not (args.enable or cfg.enabled):raise PolicyError('workflow resume requires --enable or current enabled config')
                out=engine.resume(args.workflow_id,enable=args.enable or cfg.enabled,exe=args.codex)
            elif args.workflow_action=='status':out=engine.status(args.workflow_id)
            else:out=engine.signal(args.workflow_id,args.workflow_action)
            print(json.dumps(out,ensure_ascii=False,indent=2))
            if args.workflow_action in ('start','resume') and not out.get('dry_run'):
                return 0 if out['state'] in ('completed','paused') and out.get('integrity')!='failed' else 3
            return 0
        elif args.command=='verify':
            from . import acceptance
            from .budget import ExecutionBudget
            contract=acceptance.load_contract(args.acceptance_file)
            protected=acceptance.protected_paths(repo,args.protect_path)
            if not args.execute:
                out={'dry_run':True,'acceptance':contract.summary(),'external_calls':0,'model_calls':0}
            else:
                acceptance.require_backend()
                from .native import executable
                cli=executable(args.codex)
                budget=ExecutionBudget(args.timeout if args.timeout is not None else cfg.timeout_s,cfg.max_model_requests)
                prepared=acceptance.prepare(repo,contract)
                run_dir=inside(repo,repo/'.codex-flow/runs'/('verify-'+uuid.uuid4().hex))
                run_dir.mkdir(parents=True,exist_ok=False)
                receipt=acceptance.verify(cli,repo,prepared,run_dir,budget,protected)
                out={'run_id':run_dir.name,'status':'completed_verified' if receipt['accepted'] else 'verification_failed',
                     'accepted':receipt['accepted'],'acceptance':receipt,'model_calls':0,
                     'execution_budget':budget.snapshot(0)}
                write_json(run_dir/'metrics.json',out)
                write_json(run_dir/'control.json',{'pid':None,'status':out['status']})
                print(json.dumps(out,ensure_ascii=False,indent=2));return 0 if out['accepted'] else 3
        elif args.command=='runs':
            def checked_record_path(path):
                try:return inside(repo,path)
                except (PolicyError,OSError):raise PolicyError('run record boundary refused') from None
            root=checked_record_path(repo/'.codex-flow/runs')
            if args.action=='list':
                out=[]
                for candidate in root.glob('*'):
                    d=checked_record_path(candidate)
                    if not d.is_dir():continue
                    metrics=checked_record_path(d/'metrics.json')
                    state=metrics if metrics.exists() else checked_record_path(d/'control.json')
                    if state.is_file():out.append({'run_id':d.name,**json.loads(state.read_text(encoding='utf-8'))})
            else:
                if not args.run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.run_id):raise PolicyError('invalid run id')
                folder=checked_record_path(root/args.run_id)
                if not folder.is_dir():raise PolicyError('run missing')
                if args.action=='cancel':checked_record_path(folder/'cancel.request').touch();out={'cancel_requested':True}
                elif args.action=='replay':out=replay(checked_record_path(folder/'events.jsonl'))
                else:
                    metrics=checked_record_path(folder/'metrics.json')
                    state=metrics if metrics.exists() else checked_record_path(folder/'control.json')
                    out=json.loads(state.read_text(encoding='utf-8'))
                    if not metrics.exists():
                        events=checked_record_path(folder/'events.jsonl')
                        if events.exists():out['trace']=replay(events)
        else:
            from .benchmark import execute,report
            if args.action=='tree':
                if not args.root or not args.task_file or not args.evaluator:raise PolicyError('--root, --task-file and frozen --evaluator required')
                measured=execute(args.root,args.task_file,args.evaluator,args.codex,args.mercury_root,args.timeout,execute=args.execute,protect_paths=args.protect_path,groups=args.groups,
                                 native_request_retries=cfg.native_request_retries)
                out=({'experiment':str(args.root),'groups':{g:{k:m.get(k) for k in ('status','total_arm_s','mercury_real_calls','multi_agent_verified','model_requests_total','input_tokens','output_tokens')} for g,m in measured.items()}}
                     if args.execute else measured)
            else:
                if not args.root:raise PolicyError('--root required')
                out=report(args.root)
        print(json.dumps(out,ensure_ascii=False,indent=2));return 0
    except (PolicyError,OSError,ValueError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr);return 2
