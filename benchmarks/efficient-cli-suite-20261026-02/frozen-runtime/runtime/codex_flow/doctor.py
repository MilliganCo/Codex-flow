"""Read-only metadata preflight; live typed smoke is explicit and free-only."""
from pathlib import Path
from dataclasses import asdict
import json, queue, subprocess, threading, time, platform, shutil
from .native import executable, subscription
from .contracts import IntegrationHealth

def metadata(exe):
    proc=subprocess.Popen([exe,'app-server','--stdio','-c','approval_policy="never"','-c','sandbox_mode="read-only"'],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
    q=queue.Queue()
    def read():
        for line in proc.stdout:q.put(line)
        q.put(None)
    threading.Thread(target=read,daemon=True).start()
    def send(v):proc.stdin.write(json.dumps(v)+'\n');proc.stdin.flush()
    send({'id':1,'method':'initialize','params':{'clientInfo':{'name':'codex_flow_doctor','version':'2.0.0'}}})
    result={};deadline=time.monotonic()+25
    try:
        while time.monotonic()<deadline and len(result)<2:
            try:line=q.get(timeout=1)
            except queue.Empty:continue
            if line is None:break
            event=json.loads(line)
            if event.get('id')==1:
                send({'method':'initialized','params':{}})
                for i,m in [(2,'model/list'),(3,'account/read')]:send({'id':i,'method':m,'params':{}})
            if event.get('id')==2:
                result['models']=[{'model':m.get('model'),'efforts':[e['reasoningEffort'] for e in m.get('supportedReasoningEfforts',[])]}
                                  for m in event.get('result',{}).get('data',[])]
            if event.get('id')==3:
                a=event.get('result',{}).get('account') or {};result['auth_class']=a.get('type')
    finally:
        proc.terminate();proc.wait(timeout=10)
    return result

def doctor(exe=None,deep=False,mercury_root=None,live_mercury=False):
    result={'python':platform.python_version(),'os':platform.system(),'git':shutil.which('git') is not None,
            'configured_model':'gpt-6.1-sol','configured_effort':'xhigh','model_available':None,
            'generation_validated':False,'cost_usd':None,'global_configuration_written':False}
    try:
        cli=executable(exe);subscription(cli)
        result['codex_version']=subprocess.run([cli,'--version'],capture_output=True,text=True,timeout=10).stdout.strip()
        result['auth_class']='chatgpt'
        if deep:
            m=metadata(cli);result.update(m)
            result['model_available']=any(x['model']=='gpt-6.1-sol' and 'xhigh' in x['efforts'] for x in m.get('models',[]))
    except (OSError,ValueError,subprocess.SubprocessError) as e:
        result['codex_error']=type(e).__name__;result['codex_status']='unavailable'
    result['mercury']=asdict(IntegrationHealth(configured=bool(mercury_root),reason='live smoke not requested'))
    if live_mercury:
        from .mercury import MercuryBridge
        observed=MercuryBridge(mercury_root).decide({'complexity':'high','independent_steps':2,'conflicting_paths':False,'risk_level':'normal'},enabled=True)
        result['mercury']=dict(observed,configured=bool(mercury_root),active=observed['status']=='OBSERVED',validated=observed['status']=='OBSERVED')
    result['harness2']=asdict(IntegrationHealth(status='degraded',configured=True,reason='project-only Harness2-inspired adapter; unsafe upstream executor excluded'))
    return result
