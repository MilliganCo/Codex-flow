"""Conservative dependency-free pre-publication scan of Git content and history.

This is a targeted equivalent for this small Python repository, not a guarantee
that every possible secret format is detectable. Findings never print matched data.
"""
from pathlib import Path
import argparse, json, re, subprocess

RULES={
    'provider-key':re.compile(rb'\bsk-(?:or-v1-|proj-)?[A-Za-z0-9_-]{24,}'),
    'github-token':re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{40,})'),
    'private-key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'aws-key':re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'jwt':re.compile(rb'\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}'),
    'personal-windows-path':re.compile(rb'(?i)[a-z]:[\\/]+Users[\\/]+(?!Public\b|<|USER\b|example\b)[A-Za-z0-9_.-]+[\\/]'),
}
BAD_NAMES={'auth.json','.env','credentials.json'}

def git(root,*args):
    p=subprocess.run(['git','-C',str(root),*args],capture_output=True,check=True)
    return p.stdout

def scan(root:Path,history=False):
    findings=[];checked=0
    files=git(root,'ls-files','-z').decode().split('\0')
    for name in filter(None,files):
        path=root/name
        if path.is_symlink():findings.append({'scope':'working','path':name,'rule':'symlink'})
        if path.name in BAD_NAMES or path.suffix in {'.key','.pem'}:findings.append({'scope':'working','path':name,'rule':'credential-file'})
        if path.is_file():
            raw=path.read_bytes();checked+=1
            for rule,pattern in RULES.items():
                if pattern.search(raw):findings.append({'scope':'working','path':name,'rule':rule})
    if history:
        for commit in git(root,'rev-list','--all').decode().splitlines():
            for entry in git(root,'ls-tree','-rz',commit).split(b'\0'):
                if not entry:continue
                meta,name=entry.split(b'\t',1);mode=meta.split()[0];path=Path(name.decode())
                if mode in (b'120000',b'160000'):
                    findings.append({'scope':'history','path':str(path),'commit':commit,'rule':'linked-content'})
                if path.name in BAD_NAMES or path.suffix in {'.key','.pem'}:
                    findings.append({'scope':'history','path':str(path),'commit':commit,'rule':'credential-file'})
        objects=git(root,'rev-list','--objects','--all').decode().splitlines()
        for entry in objects:
            oid,_,name=entry.partition(' ')
            if git(root,'cat-file','-t',oid).strip()!=b'blob':continue
            raw=git(root,'cat-file','blob',oid);checked+=1
            for rule,pattern in RULES.items():
                if pattern.search(raw):findings.append({'scope':'history','path':name,'object':oid,'rule':rule})
    return {'checked_objects':checked,'findings':findings,'passed':not findings,'history_scanned':history,
            'limitations':'targeted token/key/path signatures; manual provenance and publication allowlist review also required'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--history',action='store_true')
    a=p.parse_args();r=scan(a.repo,a.history);print(json.dumps(r,indent=2));raise SystemExit(0 if r['passed'] else 1)
