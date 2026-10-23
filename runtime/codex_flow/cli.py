"""Opt-in runtime CLI. Offline legacy flowctl commands are preserved separately."""
from __future__ import annotations
import argparse
from dataclasses import asdict, replace
from pathlib import Path
import json, sys, uuid, time
from .config import Config, load
from .contracts import PolicyError, inside
from .telemetry import write_json, replay

FLOW_INSTRUCTIONS='''You are the Codex Flow coordinator, GPT-6.1 Sol xhigh. Keep task acceptance fixed.
Use native subagents only when independent work exists. Maximum three helpers globally,
maximum one delegation level, never ask helpers to delegate. Prefer at most two helpers.
The coordinator is the sole writer and integrator. Give each helper one independent
read-only evidence task with a narrow scope, concrete acceptance condition and concise
output: actionable findings, file/line evidence, checks and limitations. Use Sol medium
for bounded research and Sol high for review where available. Read applicable project rules.
For an explicitly parallel run, use at least one independent read-only native helper;
receive its evidence before final integration. A failed spawn is degraded execution,
never proof of delegation. Do not repeatedly retry an unavailable helper.
The initial helper should inspect the task and available constraints, then return one
concise evidence pass. If required files do not exist yet, report that prerequisite
once; never keep polling or waiting for the coordinator to create them. A later code
review needs an explicit stable scope and a concrete reason for a follow-up.
Continue implementing while the helper works; do not wait for a generic plan. Start with
a runnable vertical slice, a documented launch command and a finite smoke check. Keep
required documentation and artifacts current as features land, rather than leaving them
until the end. Map the task's acceptance conditions to concrete checks; distinguish unit
simulations from actual platform behavior. Prioritize unverified critical boundaries.
Reserve the final 20 percent of the task's time budget for verification, required artifacts,
documentation and handoff. This is a planning target, not a guaranteed runtime timer.
Integrate helper findings once; follow up only for a concrete unresolved defect. Do not
duplicate its assigned investigation or rerun unchanged checks without new evidence.
Consult the controller's read-only budget status tool at major stage boundaries when available.
Complete a minimal real platform
startup/shutdown check early, before optional rendering or structural polish. Batch
independent finite checks when appropriate and wait for a running operation rather
than spending repeated model turns polling it. Keep required documentation and saved
artifacts complete during implementation. After acceptance evidence is complete,
finish promptly; do not keep changing working features to consume the remaining time.
This local workflow context is sufficient. Do not retry unavailable global skills or
read denied global paths; report the bounded limitation and continue locally.
All work must stay within the assigned workspace. Do not read sibling workspaces/evaluators,
global user files, credentials, memories or prior solutions. Do not use paid APIs, internet,
publication, deployment, sandbox bypass, global config changes or external applications.
Do not inspect .codex-flow/native-state, native SQLite databases, session/rollout or
history containers, or historical thread metadata, including inside this workspace.
Do not stage, commit, merge, or alter Git history; the experiment controller owns archives.
Run relevant finite tests; report pass/fail/not-run, actual paths and limitations. Do not
claim success merely because a tool exited zero. Stop only when acceptance is met or blocked.
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
    s=sub.add_parser('runs');s.add_argument('action',choices=['list','show','cancel','replay']);s.add_argument('run_id',nargs='?')
    b=sub.add_parser('benchmark');b.add_argument('action',choices=['tree','report']);b.add_argument('--task-file',type=Path);b.add_argument('--root',type=Path);b.add_argument('--evaluator',type=Path);b.add_argument('--mercury-root',type=Path);b.add_argument('--execute',action='store_true');b.add_argument('--timeout',type=int,default=1200)
    b.add_argument('--protect-path',type=Path,action='append',default=[])
    b.add_argument('--groups',choices=['AB','ABCD'],default='ABCD')
    args=p.parse_args(argv)
    try:
        repo=args.repo.resolve();cfg=load(args.config or repo/'.codex-flow/config.json')
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
            execution_budget=ExecutionBudget(cfg.timeout_s,cfg.max_model_requests)
            prompt=args.task_file.read_text(encoding='utf-8-sig') if args.task_file else args.task
            if not prompt:raise PolicyError('task or --task-file required')
            if not args.dry_run and not (cfg.enabled or args.enable):raise PolicyError('runtime disabled; use --enable or project config')
            mercury=None
            decision=route(independent_steps=args.independent_steps,conflicting_paths=args.conflicting_paths,
                           risk_level=args.risk_level,single=args.single_agent or args.strategy=='single')
            if decision.strategy=='parallel' and cfg.mercury and not args.no_mercury and not args.dry_run:
                from .mercury import MercuryBridge
                mercury=MercuryBridge(args.mercury_root).decide({'complexity':'high','independent_steps':min(args.independent_steps,100),
                    'conflicting_paths':False,'risk_level':'low' if args.risk_level=='normal' else args.risk_level},enabled=True)
                decision=route(independent_steps=args.independent_steps,conflicting_paths=args.conflicting_paths,
                               risk_level=args.risk_level,single=args.single_agent or args.strategy=='single',mercury=mercury)
            if args.dry_run:out={'dry_run':True,'config':asdict(cfg),'route':asdict(decision),'external_calls':0}
            else:
                if not (cfg.enabled or args.enable):raise PolicyError('runtime disabled; use --enable or project config')
                if decision.strategy=='escalate':raise PolicyError(decision.reason)
                cli=executable(args.codex)
                from .subscription import RequestBudget
                request_budget=RequestBudget(cfg.max_model_requests)
                harness=None
                if cfg.harness2 and not args.no_harness2:
                    from .harness import runtime_guard
                    harness=runtime_guard()
                instructions=FLOW_INSTRUCTIONS if decision.strategy=='parallel' else BASE_INSTRUCTIONS
                active=repo/'.codex-flow/lessons/active.txt'
                if harness and harness['decision']['adopted']:instructions=active.read_text(encoding='utf-8')
                remaining=int(cfg.timeout_s-(time.monotonic()-started))
                if remaining<=0:
                    if harness and harness['decision']['adopted']:
                        from .harness import GuardedHarness
                        GuardedHarness(repo).rollback(harness['decision']['proposal']['id'])
                    raise PolicyError('total task budget exhausted during routing/probes; task execution not started')
                out=run(cli,repo,replace(cfg,timeout_s=remaining),prompt,repo/'.codex-flow/runs'/uuid.uuid4().hex,
                        parallel=decision.strategy=='parallel',instructions=instructions,request_budget=request_budget,execution_budget=execution_budget)
                out['execution_s']=out['wall_clock_s']
                out['wall_clock_s']=round(time.monotonic()-started,3)
                out['root_usage']={k:out[k] for k in ('input_tokens','output_tokens','cached_tokens')}
                if decision.strategy=='parallel':
                    for key in ('input_tokens','output_tokens','cached_tokens'):out[key]=None
                out['route']=asdict(decision);out['mercury']=mercury
                out['harness2']=harness or {'status':'disabled'}
                if harness and harness['decision']['adopted'] and out['status']!='completed_unverified':
                    from .harness import GuardedHarness
                    try:out['harness2']['rollback']=GuardedHarness(repo).rollback(harness['decision']['proposal']['id'])
                    except PolicyError:out['harness2']['rollback_error']='active instruction drift; preserved for review'
                write_json(repo/'.codex-flow/runs'/out['run_id']/'metrics.json',out)
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
                measured=execute(args.root,args.task_file,args.evaluator,args.codex,args.mercury_root,args.timeout,execute=args.execute,protect_paths=args.protect_path,groups=args.groups)
                out=({'experiment':str(args.root),'groups':{g:{k:m.get(k) for k in ('status','total_arm_s','mercury_real_calls','multi_agent_verified','model_requests_total','input_tokens','output_tokens')} for g,m in measured.items()}}
                     if args.execute else measured)
            else:
                if not args.root:raise PolicyError('--root required')
                out=report(args.root)
        print(json.dumps(out,ensure_ascii=False,indent=2));return 0
    except (PolicyError,OSError,ValueError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr);return 2
