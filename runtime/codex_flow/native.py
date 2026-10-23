"""Official subscription CLI adapter. No direct inference HTTP or unsafe flags."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import hashlib, json, os, queue, shutil, subprocess, threading, time
from .config import Config
from .contracts import PolicyError
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
    home=workspace/'.home';home.mkdir(exist_ok=True)
    env.update(HOME=str(home),USERPROFILE=str(home),XDG_CACHE_HOME=str(home/'.cache'))
    temp=workspace/'.tmp';temp.mkdir(exist_ok=True)
    env.update(TEMP=str(temp),TMP=str(temp),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    return env

def argv(exe:str,workspace:Path,cfg:Config,*,parallel=False,instructions=''):
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
    }
    command=[exe,'--no-daemon','exec','--ignore-user-config','--ignore-rules','--ephemeral',
             '--sandbox','workspace-write','--model',cfg.model,'--cd',str(workspace),'--json','--color','never']
    for key,value in overrides.items():command+=['-c',key+'='+json.dumps(value)]
    return command+['-']

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

def run(exe:str,workspace:Path,cfg:Config,prompt:str,run_dir:Path,*,parallel=False,instructions='',cancel:threading.Event|None=None):
    subscription(exe)
    if not workspace.is_dir():raise PolicyError('workspace missing')
    run_dir.mkdir(parents=True,exist_ok=False)
    trace=Trace(run_dir/'events.jsonl',run_dir.name)
    started=time.monotonic()
    command=argv(exe,workspace,cfg,parallel=parallel,instructions=instructions)
    trace.emit('execution.start',{'model':cfg.model,'effort':cfg.effort,'sandbox':'workspace-write',
                               'parallel':parallel,'max_agents':cfg.max_agents,'task_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
    proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          cwd=workspace,env=environment(workspace),text=True,encoding='utf-8',errors='replace',
                          start_new_session=os.name!='nt')
    write_json(run_dir/'control.json',{'pid':proc.pid,'status':'running','started_utc':utc()})
    lines=queue.Queue(); stderr_size=[0]; stderr_tail=[]
    def drain():
        for line in proc.stdout:lines.put(line)
        lines.put(None)
    def errors():
        for line in proc.stderr:
            stderr_size[0]+=len(line.encode());stderr_tail.append(line)
            if len(stderr_tail)>12:stderr_tail.pop(0)
    threading.Thread(target=drain,daemon=True).start();threading.Thread(target=errors,daemon=True).start()
    proc.stdin.write(prompt);proc.stdin.close()
    result={'run_id':run_dir.name,'model_root':cfg.model,'effort_root':cfg.effort,'pid':proc.pid,
            'status':'partial','started_utc':utc(),'wall_clock_s':None,'input_tokens':None,'output_tokens':None,
            'cached_tokens':None,'actual_api_cost_usd':None,'subscription_quota_delta':None,
            'tool_calls':0,'failed_calls':0,'agent_count':None if parallel else 1,'peak_concurrent_agents':None if parallel else 1,
            'billing_class':'chatgpt_subscription','shared_auth_home':True,'isolated_sessions':True,
            'full_filesystem_read_isolation_verified':False,'attempts':1,'native_exit_code':None}
    result['depth_and_total_agent_caps']='instruction-only; not a verified native runtime limit'
    completed=False;timed_out=False
    try:
        while True:
            if time.monotonic()-started>cfg.timeout_s or (cancel and cancel.is_set()) or (run_dir/'cancel.request').exists():
                timed_out=True;terminate_tree(proc);break
            try:line=lines.get(timeout=.2)
            except queue.Empty:
                continue
            if line is None:break
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
                if item.get('exit_code') not in (None,0):result['failed_calls']+=1
            if kind in ('error','turn.failed'):
                safe['error']='native_error';result['failed_calls']+=1
            trace.emit('native.'+kind,safe,error_category='native_error' if kind in ('error','turn.failed') else None)
        proc.wait(timeout=15)
    except (KeyboardInterrupt,BaseException):
        terminate_tree(proc);raise
    finally:
        if proc.poll() is None:terminate_tree(proc)
        result.update(native_exit_code=proc.returncode,ended_utc=utc(),wall_clock_s=round(time.monotonic()-started,3),stderr_bytes_suppressed=stderr_size[0])
        result['status']='timed_out' if timed_out else ('completed_unverified' if completed and proc.returncode==0 else 'failed')
        trace.emit('execution.end',result)
        write_json(run_dir/'metrics.json',result)
        write_json(run_dir/'control.json',{'pid':proc.pid,'status':result['status']})
        # Keep sanitized diagnostics only. Never persist raw authenticated errors.
        from .telemetry import sanitize
        write_json(run_dir/'diagnostics.json',{'stderr_tail':sanitize(''.join(stderr_tail))})
    return result
