"""Official subscription CLI adapter. No direct inference HTTP or unsafe flags."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import hashlib, json, os, queue, shutil, subprocess, threading, time
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

def argv(exe:str,workspace:Path,cfg:Config,*,parallel=False,instructions='',gateway=None,denied_reads=(),profiles=None):
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
        text+='developer_instructions = "Read-only evidence gathering in the assigned workspace. Never write application files or spawn further agents. Return concise evidence and limitations."\n[features]\napps = false\nplugins = false\nmemories = false\nrequest_permissions_tool = false\n'
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

def _run(exe:str,workspace:Path,cfg:Config,prompt:str,run_dir:Path,*,parallel=False,instructions='',cancel:threading.Event|None=None,gateway=None,denied_reads=()):
    subscription(exe)
    if not workspace.is_dir():raise PolicyError('workspace missing')
    run_dir.mkdir(parents=True,exist_ok=False)
    trace=Trace(run_dir/'events.jsonl',run_dir.name)
    if gateway is not None:gateway.trace=trace
    started=time.monotonic()
    profiles=role_profiles(workspace,named_permissions=bool(denied_reads)) if parallel else None
    command=argv(exe,workspace,cfg,parallel=parallel,instructions=instructions,gateway=gateway,denied_reads=denied_reads,profiles=profiles)
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
    completed=False;timed_out=False;seen_agents:set[str]=set();stdout_closed=False
    try:
        writer.start()
        while True:
            if time.monotonic()-started>cfg.timeout_s or (cancel and cancel.is_set()) or (run_dir/'cancel.request').exists():
                timed_out=True;terminate_tree(proc);break
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
            if kind=='turn.completed':
                completed=True;usage=event.get('usage') or {};safe['usage']=usage
                for src,dst in [('input_tokens','input_tokens'),('output_tokens','output_tokens'),('cached_input_tokens','cached_tokens')]:
                    if type(usage.get(src)) is int:result[dst]=usage[src]
            if kind=='item.completed':
                itype=item.get('type','unknown');safe={'item_type':itype,'status':item.get('status'),'exit_code':item.get('exit_code')}
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
        result['status']='timed_out' if timed_out else ('completed_unverified' if completed and proc.returncode==0 and not input_failed.is_set() else 'failed')
        trace.emit('execution.end',result)
        write_json(run_dir/'metrics.json',result)
        write_json(run_dir/'control.json',{'pid':proc.pid,'status':result['status']})
        # Keep sanitized diagnostics only. Never persist raw authenticated errors.
        from .telemetry import sanitize
        write_json(run_dir/'diagnostics.json',{'stderr_tail':sanitize(''.join(stderr_tail))})
    return result

def run(exe:str,workspace:Path,cfg:Config,prompt:str,run_dir:Path,*,parallel=False,instructions='',cancel=None,denied_reads=(),request_budget=None):
    from .subscription import RequestBudget, SubscriptionGateway
    budget=request_budget if request_budget is not None else RequestBudget(cfg.max_model_requests)
    denied_reads=tuple(denied_reads)+tuple(p for p in (Path.home()/'.codex',Path.home()/'.agents') if p.exists())
    with SubscriptionGateway(budget=budget) as gateway:
        result=_run(exe,workspace,cfg,prompt,run_dir,parallel=parallel,instructions=instructions,cancel=cancel,
                    gateway=gateway,denied_reads=denied_reads)
    result['subscription']=gateway.summary()
    result['transport_validated']=result['subscription']['completed_requests']>0
    result['root_cli_usage']={k:result[k] for k in ('input_tokens','output_tokens','cached_tokens')}
    result['all_requests_usage']=result['subscription']['aggregate_usage']
    result['read_denials_configured']=bool(denied_reads)
    write_json(run_dir/'metrics.json',result)
    return result
