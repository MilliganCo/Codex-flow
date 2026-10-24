"""Official subscription CLI adapter. No direct inference HTTP or unsafe flags."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import hashlib, hmac, json, os, queue, secrets, shutil, subprocess, sys, threading, time
from .config import Config
from .contracts import PolicyError, inside
from .telemetry import Trace, write_json, utc

def executable(explicit: str | None = None) -> str:
    value=explicit or os.environ.get('CODEX_FLOW_CODEX') or shutil.which('codex')
    if not value: raise PolicyError('Codex executable missing; set CODEX_FLOW_CODEX')
    result=subprocess.run([value,'--version'],capture_output=True,text=True,timeout=15)
    if result.returncode or 'codex-cli' not in result.stdout: raise PolicyError('Codex executable failed version check')
    return value

def subscription(exe):
    p=subprocess.run([exe,'login','status'],capture_output=True,text=True,timeout=15)
    if p.returncode or 'Logged in using ChatGPT' not in p.stdout+p.stderr:
        raise PolicyError('ChatGPT subscription login required; API fallback forbidden')

def environment(workspace:Path):
    env={k:v for k,v in os.environ.items() if not any(t in k.upper() for t in ('API_KEY','ACCESS_TOKEN','AUTH_TOKEN','SECRET','CODEX_'))}
    # CLI owns auth. No credential is opened, copied, or printed by this adapter.
    env['CODEX_HOME']=str(Path.home()/'.codex')
    home=inside(workspace,workspace/'.home');home.mkdir(exist_ok=True)
    env.update(HOME=str(home),USERPROFILE=str(home),XDG_CACHE_HOME=str(home/'.cache'))
    temp=inside(workspace,workspace/'.tmp');temp.mkdir(exist_ok=True)
    env.update(TEMP=str(temp),TMP=str(temp),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    return env

def argv(exe:str,workspace:Path,cfg:Config,*,parallel=False,instructions='',gateway=None,denied_reads=(),profiles=None,budget_channel=None):
    if parallel:
        instructions += ('\nController execution plan: selected_strategy=parallel; max_helpers='+str(cfg.max_agents)+
                         '; delegation_depth=1 (instruction boundary). The human owner explicitly authorized '
                         'this multi-agent execution. Your FIRST TOOL ACTION must spawn exactly one independent '
                         'read-only reviewer with agent_type=reviewer (the provided Sol high profile) using the native spawn tool, BEFORE editing application files or running '
                         'shell commands. This is a required execution step, not a discretionary recommendation. '
                         'Supply the task requirements and request at most five concrete acceptance risks and '
                         'boundary checks. This initial review uses supplied context only: no tools, file reads, '
                         'polling or production implementation. Return concise evidence and limitations. Continue useful implementation '
                         'of a different part immediately while it works; do not '
                         'ask it to wait or poll for files that do not exist yet. It should return available '
                         'requirements evidence and missing prerequisites once. Do not '
                         'wait for its plan; receive its evidence before final integration. '
                         'A failed spawn is degraded execution: report it and do not retry. Never ask helpers to delegate.')
    overrides={
        'model_provider':'flow_subscription','model_reasoning_effort':cfg.effort,'approval_policy':'never',
        'model_providers.flow_subscription.name':'Codex Flow subscription transport',
        'model_providers.flow_subscription.base_url':'https://chatgpt.com/backend-api/codex',
        'model_providers.flow_subscription.wire_api':'responses',
        'model_providers.flow_subscription.requires_openai_auth':True,
        'model_providers.flow_subscription.supports_websockets':False,
        'model_providers.flow_subscription.request_max_retries':0,
        'model_providers.flow_subscription.stream_max_retries':0,
        'sandbox_workspace_write.network_access':False,'sandbox_workspace_write.exclude_tmpdir_env_var':True,
        'sandbox_workspace_write.exclude_slash_tmp':True,'windows.sandbox':'elevated',
        'project_doc_max_bytes':0,'web_search':'disabled','features.memories':False,
        'features.hooks':False,'features.plugins':False,'features.apps':False,
        'features.remote_plugin':False,'features.skill_search':False,'features.skip_host_skill_discovery':True,
        'features.skill_mcp_dependency_install':False,'features.shell_snapshot':False,
        'features.browser_use':False,'features.computer_use':False,'features.image_generation':False,
        'features.multi_agent':parallel,'agents.max_concurrent_threads_per_session':cfg.max_agents,
        'agents.default_subagent_model':'gpt-6.1-sol',
        'agents.default_subagent_reasoning_effort':'medium',
        'developer_instructions':instructions,
        'sqlite_home':str(workspace/'.codex-flow/native-state'),
        'log_dir':str(workspace/'.codex-flow/native-state/logs'),
        'history.persistence':'none',
    }
    if gateway is not None:
        overrides['model_providers.flow_subscription.base_url']=gateway.base_url
        overrides['model_providers.flow_subscription.env_http_headers.X-Codex-Flow-Token']='CODEX_FLOW_GATEWAY_TOKEN'
        overrides['features.enable_request_compression']=False
    if budget_channel is not None:
        # The protected snapshot is copied before native tools can edit source.
        # -I excludes cwd/PYTHONPATH; never fall back to the writable package.
        bootstrap = ('import runpy,sys;sys.path.insert(0,' + repr(str(budget_channel.runtime_root))
                     + ');runpy.run_module("codex_flow.budget_stdio",run_name="__main__")')
        overrides.update({
            'mcp_servers.flow_budget.command': sys.executable,
            'mcp_servers.flow_budget.args': ['-I', '-B', '-c', bootstrap, '--root', str(workspace),
                                           '--status-file', str(budget_channel.status_file),
                                           '--audit-dir', str(budget_channel.audit_dir)],
            'mcp_servers.flow_budget.enabled': True,
            'mcp_servers.flow_budget.enabled_tools': ['status'],
            'mcp_servers.flow_budget.startup_timeout_sec': 10,
            'mcp_servers.flow_budget.tool_timeout_sec': 5,
            'mcp_servers.flow_budget.default_tools_approval_mode': 'writes',
            'mcp_servers.flow_budget.tools.status.approval_mode': 'approve',
        })
    for name,path in (profiles or {}).items():
        overrides['agents.'+name+'.description']='Evidence role instructed not to write or delegate: '+name
        overrides['agents.'+name+'.config_file']=str(path)
    command=[exe,'--no-daemon','exec','--ignore-user-config','--ignore-rules',
             '--sandbox','workspace-write','--model',cfg.model,'--cd',str(workspace),'--json','--color','never']
    if not parallel:command.append('--ephemeral')
    for key,value in overrides.items():command+=['-c',key+'='+json.dumps(value)]
    if denied_reads:
        # Named profiles are process-local. Explicit deny rules close cross-arm
        # reads; the regular workspace sandbox alone does not provide that.
        at=command.index('--sandbox');del command[at:at+2]
        cleaned=[];index=0
        while index<len(command):
            if command[index]=='-c' and command[index+1].startswith('sandbox_workspace_write.'):
                index+=2;continue
            cleaned.append(command[index]);index+=1
        command=cleaned
        if any(not Path(p).exists() for p in denied_reads):
            raise PolicyError('read-denial targets must already exist; Windows materializes missing targets as directories')
        denies={str(Path(p).resolve()).replace('\\','/'):'deny' for p in denied_reads}
        if str(workspace.resolve()).replace('\\','/') in denies:raise PolicyError('workspace cannot deny itself')
        denies[str(workspace.resolve()).replace('\\','/')]='write'
        denies[str(workspace.resolve()/'.codex-flow').replace('\\','/')]='read'
        entries=','.join(json.dumps(k)+'='+json.dumps(v) for k,v in denies.items())
        profile='{extends=":workspace",filesystem={'+entries+'},network={enabled=false}}'
        command+=['-c','default_permissions="flow_task"','-c','permissions.flow_task='+profile]
    return command+['-']

def role_profiles(workspace:Path,*,named_permissions:bool):
    import uuid
    folder=inside(workspace,workspace/'.codex-flow/runtime-agents'/uuid.uuid4().hex)
    folder.mkdir(parents=True,exist_ok=False)
    result={}
    for name,model,effort in [('default','gpt-6.1-sol','medium'),('worker','gpt-6.1-sol','medium'),
                              ('explorer','gpt-6-luna','medium'),('reviewer','gpt-6.1-sol','high'),('awaiter','gpt-6.1-sol','medium')]:
        path=folder/(name+'.toml')
        text='model = '+json.dumps(model)+'\nmodel_reasoning_effort = '+json.dumps(effort)+'\n'
        text+='developer_instructions = "Read-only work in the assigned workspace. Never write files or spawn further agents. Budget status belongs to the coordinator; never query it. Return concise evidence or an explicitly requested low-risk bounded proposal in your final reply, with limitations."\n[features]\napps = false\nplugins = false\nmemories = false\nrequest_permissions_tool = false\n'
        with path.open('x',encoding='utf-8') as f:f.write(text)
        result[name]=path
    return result

def terminate_tree(proc):
    if proc.poll() is not None:return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=15)
    else:
        import signal
        try:os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)

def _run(exe:str,workspace:Path,cfg:Config,prompt:str,run_dir:Path,*,parallel=False,instructions='',cancel:threading.Event|None=None,gateway=None,denied_reads=(),execution_budget=None,budget_channel=None):
    from .budget import ExecutionBudget
    execution_budget=execution_budget or ExecutionBudget(cfg.timeout_s,cfg.max_model_requests)
    subscription(exe)
    if not workspace.is_dir():raise PolicyError('workspace missing')
    run_dir.mkdir(parents=True,exist_ok=False)
    trace=Trace(run_dir/'events.jsonl',run_dir.name)
    if gateway is not None:gateway.trace=trace
    started=time.monotonic()
    profiles=role_profiles(workspace,named_permissions=bool(denied_reads)) if parallel else None
    if parallel:
        instructions+='\nController task time budget: '+str(cfg.timeout_s)+' seconds including native execution. Plan the final '+str(max(1,round(cfg.timeout_s*.2)))+' seconds for verification, documentation and handoff; do not claim an enforced phase timer.'
    if budget_channel is not None:
        instructions += ('\nThe local flow_budget MCP server exposes the read-only status tool. '
                         'After the required initial reviewer spawn, only the chief consults status, at most twice '
                         '(first runnable slice and before final verification), unless an explicit verification '
                         'protocol requires more. Batch it with an already necessary independent tool action when '
                         'supported; do not create a standalone status-only turn or query after acceptance. '
                         'It reports the shared remaining time and reserved native request attempts. '
                         'Treat unavailable status as missing evidence; do not invent a balance or skip acceptance checks. '
                         'The phase is planning guidance, not proof of completion.')
    command=argv(exe,workspace,cfg,parallel=parallel,instructions=instructions,gateway=gateway,denied_reads=denied_reads,profiles=profiles,budget_channel=budget_channel)
    trace.emit('execution.start',{'model':cfg.model,'effort':cfg.effort,'sandbox':'workspace-write',
                               'parallel':parallel,'max_agents':cfg.max_agents,'task_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
    env=environment(workspace)
    if gateway is not None:env.update(CODEX_FLOW_GATEWAY_TOKEN=gateway.nonce,NO_PROXY='127.0.0.1,localhost')
    proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          cwd=workspace,env=env,text=True,encoding='utf-8',errors='replace',
                          start_new_session=os.name!='nt')
    write_json(run_dir/'control.json',{'pid':proc.pid,'status':'running','started_utc':utc()})
    lines:queue.Queue[str|None]=queue.Queue(); stderr_size=[0]; stderr_tail=[]
    def drain():
        for line in proc.stdout:lines.put(line)
        lines.put(None)
    def errors():
        for line in proc.stderr:
            stderr_size[0]+=len(line.encode());stderr_tail.append(line)
            if len(stderr_tail)>12:stderr_tail.pop(0)
    threading.Thread(target=drain,daemon=True).start();threading.Thread(target=errors,daemon=True).start()
    assert proc.stdin is not None
    input_done=threading.Event();input_failed=threading.Event()
    def send_input():
        try:
            assert proc.stdin is not None
            proc.stdin.write(prompt);proc.stdin.close()
        except (OSError,ValueError):
            input_failed.set()
        finally:input_done.set()
    writer=threading.Thread(target=send_input,daemon=True)
    result={'run_id':run_dir.name,'model_root':cfg.model,'effort_root':cfg.effort,'pid':proc.pid,
            'status':'partial','started_utc':utc(),'wall_clock_s':None,'input_tokens':None,'output_tokens':None,
            'cached_tokens':None,'actual_api_cost_usd':None,'subscription_quota_delta':None,
            'tool_calls':0,'failed_calls':0,'agent_count':None if parallel else 1,'peak_concurrent_agents':None if parallel else 1,
            'billing_class':'chatgpt_subscription','shared_auth_home':True,'isolated_sessions':True,
            'full_filesystem_read_isolation_verified':False,'attempts':1,'native_exit_code':None}
    result['depth_and_total_agent_caps']='read-only ownership and depth are instruction-only; native global concurrent cap and hard shared inference budget'
    result['ephemeral_session']=not parallel
    result['parallel_persistence_reason']='CLI subagents require a persisted parent; project-local sqlite/log state; shared native auth/rollout container' if parallel else None
    result['readonly_child_instructions_configured']=bool(profiles)
    result['native_child_ids']=None
    result['native_child_count']=None
    result['delegation_evidence']='not_exposed'
    completed=False;timed_out=False;cancelled=False;seen_agents:set[str]=set();stdout_closed=False
    operation_key=secrets.token_bytes(32);operation_starts:dict[str,float]={}
    root_thread_id=None;root_identity_conflict=False
    try:
        writer.start()
        while True:
            cancelled=bool((cancel and cancel.is_set()) or (run_dir/'cancel.request').exists())
            if time.monotonic()-started>cfg.timeout_s or execution_budget.remaining_s()<=0 or cancelled:
                timed_out=not cancelled
                result['stop_reason']='cancelled' if cancelled else 'deadline_exhausted'
                if gateway is not None:gateway.cancel(reason=result['stop_reason'])
                terminate_tree(proc);break
            if input_failed.is_set():
                result['error_category']='stdin_write_failed';result['failed_calls']+=1
                terminate_tree(proc);break
            if stdout_closed:
                if input_done.is_set():break
                input_done.wait(.05);continue
            try:line=lines.get(timeout=.2)
            except queue.Empty:
                continue
            if line is None:
                stdout_closed=True;continue
            try:event=json.loads(line)
            except ValueError:continue
            kind=event.get('type','unknown');safe={}
            item=event.get('item') or {}
            if kind in ('item.started','item.completed') and isinstance(item,dict):
                itype=item.get('type','unknown')
                if itype in ('command_execution','mcp_tool_call','collab_tool_call'):
                    safe['item_type']=itype
                    item_id=item.get('id')
                    if isinstance(item_id,str) and 0<len(item_id)<=256:
                        safe['item_id_hash']=hmac.new(operation_key,item_id.encode(),hashlib.sha256).hexdigest()
                        if kind=='item.started' and len(operation_starts)<1024:operation_starts[item_id]=time.monotonic()
                        elif kind=='item.completed' and item_id in operation_starts:
                            safe['tool_duration_s']=round(time.monotonic()-operation_starts.pop(item_id),6)
                    operation=item.get('command') if itype=='command_execution' else item.get('tool')
                    if isinstance(operation,str) and len(operation)<=262144:
                        safe['operation_hash']=hmac.new(operation_key,(itype+'\0'+operation).encode(),hashlib.sha256).hexdigest()
            if kind=='thread.started':
                from .native_metadata import thread_hash
                identity=event.get('thread_id')
                identity_hash=thread_hash(identity)
                if identity_hash is not None:
                    safe['thread_sha256']=identity_hash
                    if root_thread_id is None and not root_identity_conflict:root_thread_id=identity
                    elif root_thread_id!=identity:root_thread_id=None;root_identity_conflict=True
            if kind=='turn.completed':
                completed=True;usage=event.get('usage') or {};safe['usage']=usage
                for src,dst in [('input_tokens','input_tokens'),('output_tokens','output_tokens'),('cached_input_tokens','cached_tokens')]:
                    if type(usage.get(src)) is int:result[dst]=usage[src]
            if kind=='item.completed':
                itype=item.get('type','unknown');safe.update(item_type=itype,status=item.get('status'),exit_code=item.get('exit_code'))
                if itype in ('command_execution','mcp_tool_call','collab_tool_call'):result['tool_calls']+=1
                if itype=='agent_message':safe['summary']=item.get('text','')[-2048:]
                if itype=='collab_tool_call':
                    safe['tool']=item.get('tool');safe['agent_count']=len(item.get('agents_states') or {})
                    safe['schema_keys']=sorted(item)[:40]
                    recipients=item.get('receiver_thread_ids') or item.get('receiverThreadIds') or []
                    states=item.get('agents_states') or item.get('agentsStates') or item.get('agent_states') or {}
                    ids=list(recipients) if isinstance(recipients,list) else []
                    if isinstance(states,dict):ids+=list(states)
                    # A requested profile or a wait target does not prove a
                    # child exists. Only successful native spawn events count.
                    if item.get('tool') in ('spawn_agent','spawnAgent') and item.get('status')=='completed' and not item.get('error') and item.get('exit_code') in (None,0):
                        seen_agents.update(x for x in ids if isinstance(x,str) and 0<len(x)<=256)
                    safe['observed_agent_ids']=[hashlib.sha256(x.encode()).hexdigest()[:12] for x in sorted(seen_agents)]
                    if seen_agents:
                        result['agent_count']=1+len(seen_agents)
                        result['native_child_ids']=safe['observed_agent_ids']
                        result['native_child_count']=len(seen_agents)
                        result['delegation_evidence']='native_completed_spawn'
                if item.get('exit_code') not in (None,0):result['failed_calls']+=1
            if kind in ('error','turn.failed'):
                safe['error']='native_error';result['failed_calls']+=1
            trace.emit('native.'+kind,safe,error_category='native_error' if kind in ('error','turn.failed') else None)
        proc.wait(timeout=15)
    except (KeyboardInterrupt,BaseException):
        terminate_tree(proc);raise
    finally:
        if proc.poll() is None:terminate_tree(proc)
        writer.join(timeout=1)
        result['stdin_writer_stopped']=not writer.is_alive()
        if input_failed.is_set() and not timed_out and result.get('error_category')!='stdin_write_failed':
            result['error_category']='stdin_write_failed';result['failed_calls']+=1
        result.update(native_exit_code=proc.returncode,ended_utc=utc(),wall_clock_s=round(time.monotonic()-started,3),stderr_bytes_suppressed=stderr_size[0])
        result['status']='cancelled' if cancelled else 'timed_out' if timed_out else ('completed_unverified' if completed and proc.returncode==0 and not input_failed.is_set() else 'failed')
        used=getattr(getattr(gateway,'budget',None),'used',0)
        result['execution_budget']=execution_budget.snapshot(used if type(used) is int else 0)
        if parallel:
            from .native_metadata import observe_children
            metadata=observe_children(workspace,root_thread_id)
            result['native_metadata']=metadata
            if metadata['status']=='observed' and metadata['children'] and not result['native_child_ids']:
                result['native_child_ids']=[child['thread_sha256'] for child in metadata['children']]
                result['native_child_count']=len(metadata['children'])
                result['agent_count']=1+len(metadata['children'])
                result['delegation_evidence']='native_parent_link_and_usage_metadata'
            child_count=result.get('native_child_count')
            authoritative=result.get('delegation_evidence') in ('native_completed_spawn','native_parent_link_and_usage_metadata')
            verified=authoritative and type(child_count) is int and child_count>0
            result['orchestration_status']='verified' if verified else 'degraded'
            result['orchestration_reason']=result['delegation_evidence'] if verified else 'helper_not_observed'
        trace.emit('execution.end',result)
        write_json(run_dir/'metrics.json',result)
        write_json(run_dir/'control.json',{'pid':proc.pid,'status':result['status']})
        # Keep sanitized diagnostics only. Never persist raw authenticated errors.
        from .telemetry import sanitize
        write_json(run_dir/'diagnostics.json',{'stderr_tail':sanitize(''.join(stderr_tail))})
    return result

def run(exe:str,workspace:Path,cfg:Config,prompt:str,run_dir:Path,*,parallel=False,instructions='',cancel=None,denied_reads=(),request_budget=None,execution_budget=None,budget_guidance=None):
    from .subscription import RequestBudget, SubscriptionGateway
    from .budget import BudgetChannel, ExecutionBudget
    from contextlib import nullcontext
    budget=request_budget if request_budget is not None else RequestBudget(cfg.max_model_requests)
    execution_budget=execution_budget or ExecutionBudget(cfg.timeout_s,budget.max_requests)
    if not workspace.is_dir():raise PolicyError('workspace missing')
    # The official CLI may backfill shared historical metadata into this local
    # SQLite directory. Its filesystem location does not imply content isolation.
    # Precreate only this owned target: Windows materializes nonexistent denies.
    private_state=inside(workspace,workspace/'.codex-flow/native-state')
    private_state.mkdir(parents=True,exist_ok=True)
    denied_reads=tuple(denied_reads)+(private_state,)+tuple(p for p in (Path.home()/'.codex',Path.home()/'.agents') if p.exists())
    # Proxy suffix injection is experimental and never enabled implicitly: native
    # async histories have opaque continuation boundaries. MCP owns its protocol.
    guidance=False if budget_guidance is None else budget_guidance
    channel=BudgetChannel(workspace,execution_budget,budget) if parallel else None
    with channel if channel is not None else nullcontext():
        with SubscriptionGateway(budget=budget,execution_budget=execution_budget,guidance=guidance,cancel=cancel) as gateway:
            result=_run(exe,workspace,cfg,prompt,run_dir,parallel=parallel,instructions=instructions,cancel=cancel,
                        gateway=gateway,denied_reads=denied_reads,execution_budget=execution_budget,budget_channel=channel)
    result['budget_tool']=channel.summary() if channel is not None else {'configured':False}
    result['subscription']=gateway.summary()
    result['transport_validated']=result['subscription']['completed_requests']>0
    result['root_cli_usage']={k:result[k] for k in ('input_tokens','output_tokens','cached_tokens')}
    result['all_requests_usage']=result['subscription']['aggregate_usage']
    result['read_denials_configured']=bool(denied_reads)
    result['native_state_may_rehydrate_shared_history']=True
    result['native_state_content_isolation_verified']=False
    result['native_state_tool_read_denial_configured']=True
    result['native_state_tool_read_denial_verified']=False
    write_json(run_dir/'metrics.json',result)
    return result
