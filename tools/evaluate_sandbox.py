"""Run a frozen evaluator inside the native Windows sandbox, with no inference.

The evaluator and solution are explicit trusted inputs to the caller; generated
programs still run with restricted writes/network and denied credential paths.
"""
from pathlib import Path
import argparse,json,os,subprocess,sys

def main():
    p=argparse.ArgumentParser();p.add_argument('--codex',required=True);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--evaluator',type=Path,required=True);p.add_argument('--solution',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=a.root.resolve()
    for path in (a.solution.resolve(),a.output.resolve()):
        if root not in path.parents:raise SystemExit('solution/output must be beneath evaluation root')
    deny={str(Path.home()/'.codex').replace('\\','/'):'deny',str(Path.home()/'.agents').replace('\\','/'):'deny'}
    entries=','.join(json.dumps(k)+'="deny"' for k in deny)
    entries+=','+json.dumps(str(root).replace('\\','/'))+'="write"'
    profile='permissions.flow_evaluator={extends=":workspace",filesystem={'+entries+'},network={enabled=false}}'
    command=[a.codex,'sandbox','-P','flow_evaluator','--cd',str(root),'-c',profile,'-c','windows.sandbox="elevated"',
             '--',sys.executable,str(a.evaluator.resolve()),str(a.solution.resolve()),'--output',str(a.output.resolve())]
    env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ('API_KEY','ACCESS_TOKEN','AUTH_TOKEN','SECRET','CODEX_'))}
    env['PYTHONUTF8']='1';env['PYTHONDONTWRITEBYTECODE']='1'
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',env=env,timeout=600)
    print(result.stdout)
    if result.returncode:print(result.stderr[-2048:],file=sys.stderr)
    return result.returncode

if __name__=='__main__':raise SystemExit(main())
