"""Run an explicit verification command in a project-local Windows sandbox."""
from pathlib import Path
import argparse,json,os,subprocess,sys

def main():
    p=argparse.ArgumentParser();p.add_argument('--codex',required=True);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=180);p.add_argument('command',nargs=argparse.REMAINDER)
    p.add_argument('--capture',type=Path)
    a=p.parse_args();args=a.command[1:] if a.command[:1]==['--'] else a.command
    if not args or not 1<=a.timeout<=900:raise SystemExit('explicit command and timeout 1..900 required')
    root=a.root.resolve()
    rules={str(Path.home()/n).replace('\\','/'):'deny' for n in ('.codex','.agents')}
    rules[str(root).replace('\\','/')]='write'
    table=','.join(json.dumps(k)+'='+json.dumps(v) for k,v in rules.items())
    profile='permissions.flow_verify={extends=":workspace",filesystem={'+table+'},network={enabled=false}}'
    cmd=[a.codex,'sandbox','-P','flow_verify','--cd',str(root),'-c',profile,'-c','windows.sandbox="elevated"','--',*args]
    env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ('API_KEY','ACCESS_TOKEN','AUTH_TOKEN','SECRET','CODEX_'))}
    env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    try:r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',env=env,timeout=a.timeout)
    except subprocess.TimeoutExpired:raise SystemExit('verification command timed out')
    if a.capture:
        target=a.capture.resolve()
        if root not in target.parents:raise SystemExit('capture path must be beneath verification root')
        target.write_text(r.stdout,encoding='utf-8')
    try:
        report=json.loads(r.stdout)
        print(json.dumps({'status':report.get('status'),'checks':len(report.get('checks',[])),
                          'failed':[c for c in report.get('checks',[]) if c.get('status')=='fail']}))
    except (ValueError,TypeError,AttributeError):print(r.stdout[-10000:])
    if r.stderr:print(r.stderr[-10000:],file=sys.stderr)
    return r.returncode

if __name__=='__main__':raise SystemExit(main())
