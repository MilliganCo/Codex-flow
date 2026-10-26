"""Independent stdlib CLI evaluator. Only --self-test may run on the host."""
from __future__ import annotations
import argparse
import ast
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import stat
import subprocess
import sys
import threading
import time

CAP = 65536
PRIVATE = re.compile(r'(?i)(?:[A-Z]:[\\/][^\s"<>]*|/(?:Users|home)/[^\s"<>]*|sk-(?:or-v1-|proj-)?[A-Za-z0-9_-]{16,}|Bearer\s+\S+)')
SKIP = {'.git','.codex','.codex-flow','.agents','.home','.tmp','__pycache__','.venv','venv','.pytest_cache','.mypy_cache','.ruff_cache'}

def canonical(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')

def digest(raw): return hashlib.sha256(raw).hexdigest()

def ordinary(path):
    for item in (path,*path.parents):
        info=item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400: raise ValueError('link_boundary')
    if not path.is_file(): raise ValueError('ordinary_file_required')

def hashes(root):
    result={}
    for folder,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=sorted(name for name in dirs if name not in SKIP)
        for name in dirs:
            path=Path(folder)/name
            if path.is_symlink() or getattr(path.lstat(),'st_file_attributes',0)&0x400: raise ValueError('source_link')
        for name in sorted(names):
            path=Path(folder)/name
            if name in SKIP: continue
            ordinary(path)
            with path.open('rb') as stream: result[path.relative_to(root).as_posix()]=hashlib.file_digest(stream,'sha256').hexdigest()
    return result

def excerpt(raw): return PRIVATE.sub('[REDACTED]',raw.decode('utf-8','replace'))[:400]

def matches_file(path,expected):
    try:
        ordinary(path)
        return path.stat().st_size==len(expected) and path.read_bytes()==expected
    except (OSError,ValueError):return False

def execute(solution,args,temp,timeout=10):
    env={key:value for key,value in os.environ.items() if not any(word in key.upper() for word in ('API_KEY','ACCESS_TOKEN','AUTH_TOKEN','SECRET','CODEX_'))}
    temp.mkdir(parents=True,exist_ok=True)
    env.update(PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',TMP=str(temp),TEMP=str(temp),TMPDIR=str(temp))
    started=time.monotonic()
    try:
        proc=subprocess.Popen([sys.executable,'-B',*args],cwd=solution,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=os.name!='nt')
    except OSError:
        return {'launch_error':True,'timed_out':False,'exit_code':None,'stdout':b'','stderr':b'','stdout_tail':b'','stderr_tail':b'','stdout_bytes':0,'stderr_bytes':0}
    data={}
    def drain(name,stream):
        first=bytearray();tail=bytearray();count=0;sha=hashlib.sha256()
        for block in iter(lambda:stream.read(4096),b''):
            count+=len(block);sha.update(block)
            first.extend(block[:max(0,CAP-len(first))]);tail.extend(block)
            if len(tail)>8192:del tail[:-8192]
        data[name]=bytes(first);data[name+'_tail']=bytes(tail);data[name+'_bytes']=count;data[name+'_sha256']=sha.hexdigest()
    threads=[threading.Thread(target=drain,args=(name,stream),daemon=True) for name,stream in (('stdout',proc.stdout),('stderr',proc.stderr))]
    for thread in threads:thread.start()
    timed_out=False
    try:proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out=True
        if os.name=='nt':
            try:subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
            except (OSError,subprocess.TimeoutExpired):pass
        else:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        if proc.poll() is None:proc.kill()
        try:proc.wait(timeout=2)
        except subprocess.TimeoutExpired:pass
    for thread in threads:thread.join(timeout=1)
    result={'launch_error':False,'timed_out':timed_out,'exit_code':proc.returncode,'wall_s':round(time.monotonic()-started,6),'capture_complete':not any(t.is_alive() for t in threads)}
    for name in ('stdout','stderr'):
        result[name]=data.get(name,b'');result[name+'_tail']=data.get(name+'_tail',b'')
        result[name+'_bytes']=data.get(name+'_bytes');result[name+'_sha256']=data.get(name+'_sha256')
    return result

class Harness:
    def __init__(self,solution,output):self.solution=solution;self.output=output;self.results=collections.defaultdict(list);self.counter=0
    def fixture(self,label):
        self.counter+=1;path=self.output/'fixtures'/(str(self.counter).zfill(3)+'-'+label);path.mkdir(parents=True);return path
    def run(self,args,folder,timeout=10):return execute(self.solution,args,folder/'process-temp',timeout)
    def record(self,cid,label,passed,run=None,reason='contract_check'):
        status='not_assessed' if run and run.get('launch_error') else 'pass' if passed else 'fail'
        item={'case':label,'status':status,'reason':reason}
        if run:
            item.update({key:run.get(key) for key in ('exit_code','timed_out','wall_s','capture_complete','stdout_bytes','stderr_bytes','stdout_sha256','stderr_sha256')})
            item['stdout_excerpt']=excerpt(run.get('stdout',b''));item['stderr_excerpt']=excerpt(run.get('stderr',b''))
        self.results[cid].append(item)

def success(run):return not run.get('launch_error') and not run.get('timed_out') and run.get('exit_code')==0 and run.get('capture_complete',True)
def controlled_failure(run):
    captured=b''.join(run.get(key,b'') for key in ('stdout','stderr','stdout_tail','stderr_tail'))
    return not run.get('launch_error') and not run.get('timed_out') and run.get('capture_complete') is True and run.get('exit_code') not in (0,None) and b'Traceback (most recent call last)' not in captured
def stdout_matches(run,expected):return success(run) and run.get('stdout_bytes')==len(expected) and run.get('stdout_sha256')==digest(expected)

def authored(h,cid):
    folder=h.fixture('authored-tests');run=h.run(['-m','unittest','discover','-s','tests','-p','test*.py'],folder,90)
    text=run.get('stdout',b'')+run.get('stderr',b'')+run.get('stdout_tail',b'')+run.get('stderr_tail',b'')
    counts=re.findall(rb'Ran\s+([0-9]+)\s+tests?\b',text)
    h.record(cid,'stdlib-unittest-at-least-five',success(run) and bool(counts) and int(counts[-1])>=5,run)

def readme_commands(solution,module):
    path=solution/'README.md';ordinary(path);text=path.read_text(encoding='utf-8')
    commands=[];fenced=False
    for line in text.splitlines():
        if line.strip().startswith('```'):fenced=not fenced;continue
        if not fenced:continue
        try:parts=[part[1:-1] if len(part)>=2 and part[0]==part[-1] and part[0] in (chr(34),chr(39)) else part for part in shlex.split(line.strip(),posix=False)]
        except ValueError:continue
        if parts[:2]==['py','-3']:parts=['python',*parts[2:]]
        if len(parts)>=3 and parts[0] in ('python','python3') and parts[1:3]==['-m',module] and not any(p in ('|',';','&&','>','<') for p in parts):commands.append(parts[1:])
    test_command=re.search(r'python(?:3)?\s+-m\s+unittest\s+discover\s+-s\s+tests\s+-p\s+[\"\']?test\*\.py',text) is not None
    if re.search(r'(?:python(?:3)?|py\s+-3)\s+-m\s+'+re.escape(module)+r'\s+--help\b',text) and ['-m',module,'--help'] not in commands:commands.append(['-m',module,'--help'])
    return commands,test_command

def example(solution,name):
    path=Path(name)
    if path.is_absolute() or '..' in path.parts:raise ValueError('example_path')
    path=solution/path;ordinary(path)
    if not path.resolve().is_relative_to(solution):raise ValueError('example_boundary')
    return path

def validate_rubric(prefix):
    rubric=json.loads(Path(__file__).with_name('rubric.json').read_bytes())
    ids=[prefix+str(i).zfill(2) for i in range(1,21)]
    assert [row['id'] for row in rubric['criteria']]==ids
    assert all(row['max']==5 for row in rubric['criteria']) and sum(row['max'] for row in rubric['criteria'])==100
    assert rubric['acceptance']['required']==ids and rubric['acceptance']['minimum_score']==100
    assert rubric['timeouts']=={'fixture_s':10,'authored_tests_s':90}
    return rubric

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--self-test',action='store_true');parser.add_argument('--solution-root',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();rubric=validate_rubric(PREFIX)
    if args.self_test:
        def forbidden_subprocess(*_args,**_kwargs):raise AssertionError('self_test_subprocess_forbidden')
        subprocess.Popen=forbidden_subprocess;subprocess.run=forbidden_subprocess
        checks=self_test();valid,invalid=fixture_cases()
        counts={'valid_fixture_cases':sum(map(len,valid.values())),'invalid_fixture_cases':sum(map(len,invalid.values()))}
        print(json.dumps({'self_test':'passed','task':rubric['task'],'checks':checks,'criteria':20,'total_max':100,'fixture_counts':counts,'subprocess_guard':True,'app_processes':0,'sdk_calls':0,'model_calls':0}));return
    if os.environ.get('FLOW_EVALUATION_INSIDE_SDK')!='1':parser.error('Evaluation requires the trusted official-SDK launch assertion')
    if args.solution_root is None or args.output is None:parser.error('--solution-root and --output required')
    solution=args.solution_root.resolve();output=args.output.resolve()
    if not solution.is_dir() or args.output.exists() or args.output.is_symlink() or output.is_relative_to(solution):parser.error('Existing ordinary solution and fresh external output required')
    before=hashes(solution);output.mkdir(parents=True,exist_ok=False);h=Harness(solution,output)
    evaluate(h)
    try:after=hashes(solution)
    except (OSError,ValueError):after=None
    criteria=[]
    for row in rubric['criteria']:
        cases=h.results.get(row['id'],[])
        status='fail' if any(case['status']=='fail' for case in cases) else 'pass' if cases and all(case['status']=='pass' for case in cases) else 'not_assessed'
        criteria.append({'id':row['id'],'max':5,'score':5 if status=='pass' else 0 if status=='fail' else None,'status':status,'evidence':cases})
    earned=sum(row['score'] for row in criteria if row['score'] is not None);assessed=sum(row['max'] for row in criteria if row['score'] is not None)
    report={'schema':1,'task':rubric['task'],'criteria':criteria,'assessed_points':earned,'assessed_max':assessed,'unassessed_max':100-assessed,'quality_score':earned if assessed==100 else None,'accepted':assessed==100 and earned==100 and before==after,'source_unchanged':before==after,'source_sha256_before':before,'source_sha256_after':after,'rubric_sha256':digest(Path(__file__).with_name('rubric.json').read_bytes()),'model_calls':0,'submissions_imported_on_host':False,'launch_assertion_is_not_sandbox_attestation':True}
    with (output/'evaluation.json').open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'task':rubric['task'],'accepted':report['accepted'],'assessed_points':earned,'assessed_max':assessed,'source_unchanged':before==after,'model_calls':0}))

import io
import warnings
import zipfile

PREFIX='Z'
FILE_LIMIT=512*1024
TOTAL_LIMIT=2*1024*1024
RESERVED={'CON','PRN','AUX','NUL'}|{prefix+str(i) for prefix in ('COM','LPT') for i in range(1,10)}

def portable(name,directory):
    if not name or name.startswith('/') or ':' in name or chr(92) in name:raise ValueError('path')
    if directory:name=name[:-1]
    parts=name.split('/')
    if any(not re.fullmatch(r'[A-Za-z0-9._ -]{1,80}',part) or part in ('.','..') or part.endswith(('.', ' ')) or part.split('.',1)[0].upper() in RESERVED for part in parts):raise ValueError('component')
    return name

def oracle(raw):
    entries=[];payload={};dirs=set();seen=set();files=set();total=0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos=archive.infolist()
        if len(infos)>64:raise ValueError('entries')
        checked=[]
        for info in infos:
            directory=info.is_dir();name=portable(info.orig_filename,directory);key=name.casefold();mode=stat.S_IFMT(info.external_attr>>16)
            if key in seen or info.flag_bits&1 or info.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):raise ValueError('metadata')
            if mode not in ((0,stat.S_IFDIR) if directory else (0,stat.S_IFREG)):raise ValueError('kind')
            if mode==0 and bool(info.external_attr&0x10)!=directory:raise ValueError('kind')
            if info.external_attr&0x10 and not directory:raise ValueError('kind')
            seen.add(key)
            if directory:
                if info.file_size!=0:raise ValueError('directory-size')
                dirs.add(name)
            else:
                if info.file_size>FILE_LIMIT or info.file_size and (info.compress_size==0 or info.file_size>100*info.compress_size):raise ValueError('quota')
                total+=info.file_size
                if total>TOTAL_LIMIT:raise ValueError('total')
                files.add(key)
            checked.append((info,name,directory))
        for _info,name,_directory in checked:
            components=name.casefold().split('/')
            if any('/'.join(components[:i]) in files for i in range(1,len(components))):raise ValueError('prefix')
        actual_total=0
        for info,name,directory in checked:
            with archive.open(info) as stream:data=stream.read(FILE_LIMIT+1)
            if len(data)!=info.file_size or len(data)>FILE_LIMIT:raise ValueError('read-limit')
            if not directory:
                actual_total+=len(data)
                if actual_total>TOTAL_LIMIT:raise ValueError('read-total')
                payload[name]=data
            entries.append({'path':name,'kind':'dir' if directory else 'file','size':0 if directory else len(data),'sha256':None if directory else digest(data)})
    return {'schema':1,'entries':sorted(entries,key=lambda item:item['path']),'file_count':len(payload),'total_uncompressed_bytes':actual_total},payload,dirs

def zip_bytes(items,compression=zipfile.ZIP_STORED,stamp=(2020,1,2,3,4,6)):
    output=io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',UserWarning)
        with zipfile.ZipFile(output,'w') as archive:
            for item in items:
                name,data=item[:2];mode=item[2] if len(item)>2 else stat.S_IFDIR if name.endswith('/') else stat.S_IFREG
                info=zipfile.ZipInfo(name,stamp);info.create_system=3;info.compress_type=compression
                info.external_attr=((mode|0o600)<<16)|(0x10 if name.endswith('/') else 0)
                archive.writestr(info,data)
    return output.getvalue()

def encrypted(raw):
    raw=bytearray(raw)
    for signature,offset in ((b'PK\x03\x04',6),(b'PK\x01\x02',8)):
        index=raw.index(signature)+offset;raw[index:index+2]=(int.from_bytes(raw[index:index+2],'little')|1).to_bytes(2,'little')
    return bytes(raw)

def zero_compressed(raw):
    raw=bytearray(raw)
    for signature,offset in ((b'PK\x03\x04',18),(b'PK\x01\x02',20)):
        index=raw.index(signature)+offset;raw[index:index+4]=bytes(4)
    return bytes(raw)

def damaged_crc():
    raw=bytearray(zip_bytes([('crc.txt',b'OWNED_CRC_PAYLOAD_4567')]))
    index=raw.index(b'OWNED_CRC_PAYLOAD_4567');raw[index]^=1;return bytes(raw)

def backslash_name():
    # ZipInfo normalizes OS separators on Windows; mutate only the owned ZIP
    # filename bytes in the local and central headers to preserve this fixture.
    raw=zip_bytes([('a/b.txt',b'x')]);assert raw.count(b'a/b.txt')==2
    return raw.replace(b'a/b.txt',b'a'+bytes([92])+b'b.txt')

def mode_zero_directory_without_flag():
    output=io.BytesIO();info=zipfile.ZipInfo('mode-zero-dir/')
    info.create_system=3;info.external_attr=0o600<<16
    with zipfile.ZipFile(output,'w') as archive:archive.writestr(info,b'')
    return output.getvalue()

def ratio_boundary():
    for count in range(1,257):
        raw=zip_bytes([('ratio.txt',b'R'*(100*count))],zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            info=archive.infolist()[0]
            if info.file_size==100*info.compress_size:return raw
    raise AssertionError('Bounded exact-ratio fixture unavailable')

BASIC=zip_bytes([('docs/',b''),('docs/a.txt',b'hello\n'),('binary.dat',bytes(range(256))),('empty',b'')])

def fixture_cases():
    valid={
      'Z01':[('stored-basic',BASIC),('deflated-basic',zip_bytes([('a.txt',bytes(range(256))*2)],zipfile.ZIP_DEFLATED))],
      'Z02':[('binary-directory',BASIC)],'Z03':[('manifest-agreement',BASIC)],
      'Z04':[('order-a',zip_bytes([('b.txt',b'B'),('a.txt',b'A')])),('order-b',zip_bytes([('a.txt',b'A'),('b.txt',b'B')],stamp=(2024,2,3,4,5,6)))],
      'Z05':[('portable-valid',zip_bytes([('A b/file-1.txt',b'data'),('x'*80,b'x')]))],
      'Z09':[('mode-zero-file',zip_bytes([('mode-zero.txt',b'zero',0)])),('mode-zero-directory',zip_bytes([('mode-zero-dir/',b'',0)]))],
      'Z11':[('entries-64',zip_bytes([(str(i)+'.txt',b'') for i in range(64)])),('file-512KiB',zip_bytes([('max.bin',b'Q'*FILE_LIMIT)])),('total-2MiB',zip_bytes([(str(i)+'.bin',b'Q'*FILE_LIMIT) for i in range(4)])),('ratio-exact-100',ratio_boundary())],
      'Z16':[('archive-preserved',BASIC)],'Z17':[('empty-archive',zip_bytes([])),('empty-binary',zip_bytes([('zero',b''),('bytes',b'\x00\xff\x0a\x1b')]))],
    }
    invalid={
      'Z05':[('portable-invalid-'+str(i),zip_bytes([(name,b'x')])) for i,name in enumerate(('CON.txt','aux','com1.log','trailing.','bad name ','x'*81,'accent-é.txt'))],
      'Z06':[('absolute-invalid-'+str(i),zip_bytes([(name,b'x')])) for i,name in enumerate(('/absolute.txt','C:relative.txt','C:/absolute.txt','//server/share.txt'))]+[('backslash-name',backslash_name())],
      'Z07':[('component-invalid-'+str(i),zip_bytes([(name,b'x')])) for i,name in enumerate(('../outside.marker','a/../outside.marker','a//b.txt','./a.txt','a/./b.txt'))],
      'Z08':[('casefold-duplicate',zip_bytes([('a.txt',b'1'),('A.TXT',b'2')])),('file-parent',zip_bytes([('x',b'file'),('x/y',b'child')])),('file-directory-collision',zip_bytes([('x/',b''),('x',b'file')]))],
      'Z09':[('unix-symlink',zip_bytes([('link',b'outside.marker',stat.S_IFLNK)])),('unix-special',zip_bytes([('fifo',b'',stat.S_IFIFO)])),('mode-zero-directory-without-flag',mode_zero_directory_without_flag())],
      'Z10':[('encrypted-header',encrypted(zip_bytes([('secret.txt',b'x')])))],
      'Z11':[('entries-65',zip_bytes([(str(i)+'.txt',b'') for i in range(65)])),('file-too-large',zip_bytes([('big',b'Q'*(FILE_LIMIT+1))])),('total-too-large',zip_bytes([(str(i),b'Q'*FILE_LIMIT) for i in range(4)]+[('extra',b'x')])),('ratio-too-large',zip_bytes([('ratio.txt',b'X'*65536)],zipfile.ZIP_DEFLATED)),('positive-zero-compressed',zero_compressed(zip_bytes([('x',b'data')])))],
      'Z12':[('damaged-crc',damaged_crc())],
      'Z13':[('late-unsafe',zip_bytes([('good.txt',b'valid'),('../outside.marker',b'BAD')]))],
      'Z15':[('outside-sentinel',zip_bytes([('../outside.marker',b'BAD')]))],
    }
    return valid,invalid

def tree_matches(destination,payload,dirs):
    try:
        if not destination.is_dir() or destination.is_symlink() or getattr(destination.lstat(),'st_file_attributes',0)&0x400:return False
        actual={}
        for folder,subdirs,names in os.walk(destination,followlinks=False):
            if any((Path(folder)/name).is_symlink() or getattr((Path(folder)/name).lstat(),'st_file_attributes',0)&0x400 for name in subdirs):return False
            for name in names:
                path=Path(folder)/name;ordinary(path)
                relative=path.relative_to(destination).as_posix()
                if relative not in payload or path.stat().st_size!=len(payload[relative]):return False
                actual[relative]=path.read_bytes()
        return actual==payload and all((destination/name).is_dir() for name in dirs)
    except (OSError,ValueError):return False

def zip_case(h,cid,label,raw,valid=True,existing=False,owned_absolute=False):
    folder=h.fixture(label);archive=folder/'input.zip';destination=folder/'dest';outside=folder/'outside.marker';outside.write_bytes(b'PRESERVE_OUTSIDE_SENTINEL\n')
    if owned_absolute:raw=zip_bytes([(str(outside.resolve()),b'BAD')])
    archive.write_bytes(raw)
    if existing=='file':destination.write_bytes(b'PRESERVE_DESTINATION\n')
    elif existing:destination.mkdir();(destination/'keep.txt').write_bytes(b'PRESERVE_DESTINATION\n')
    if valid and not existing:manifest,payload,dirs=oracle(raw);expected=canonical(manifest)
    if valid and not existing:
        first=h.run(['-m','safezip','inspect',str(archive)],folder)
        before_extract={path.relative_to(folder).as_posix() for path in folder.rglob('*')}
        inspect_clean=before_extract=={'input.zip','outside.marker','process-temp'}
        second=h.run(['-m','safezip','extract',str(archive),'--dest',str(destination)],folder)
        passed=stdout_matches(first,expected) and inspect_clean and stdout_matches(second,expected) and tree_matches(destination,payload,dirs)
        h.record(cid,label+'-inspect',stdout_matches(first,expected) and inspect_clean,first)
    else:
        if not existing:
            rejected=h.run(['-m','safezip','inspect',str(archive)],folder)
            h.record(cid,label+'-inspect-rejected',controlled_failure(rejected),rejected)
        second=h.run(['-m','safezip','extract',str(archive),'--dest',str(destination)],folder)
        passed=controlled_failure(second) and (matches_file(destination,b'PRESERVE_DESTINATION\n') if existing=='file' else tree_matches(destination,{'keep.txt':b'PRESERVE_DESTINATION\n'},set()) if existing else not destination.exists())
        remaining={path.relative_to(folder).as_posix() for path in folder.rglob('*')}
        allowed={'input.zip','outside.marker','process-temp'}|({'dest'} if existing=='file' else {'dest','dest/keep.txt'} if existing else set())
        passed=passed and remaining==allowed
    passed=passed and matches_file(archive,raw) and matches_file(outside,b'PRESERVE_OUTSIDE_SENTINEL\n')
    h.record(cid,label+'-extract',passed,second)

def readme(h):
    folder=h.fixture('readme-smoke')
    try:
        commands,test=readme_commands(h.solution,'safezip')
        inspect=next(cmd for cmd in commands if len(cmd)==4 and cmd[2]=='inspect')
        extract=next(cmd for cmd in commands if len(cmd)==6 and cmd[2]=='extract' and cmd[4]=='--dest')
        for index,cmd in enumerate((inspect,extract)):
            archive=example(h.solution,cmd[3]);raw=archive.read_bytes();manifest,payload,dirs=oracle(raw);args=list(cmd);expected=canonical(manifest)
            destination=folder/('README-dest-'+str(index))
            if index:args[5]=str(destination)
            run=h.run(args,folder)
            passed=test and ['-m','safezip','--help'] in commands and stdout_matches(run,expected) and (not index or tree_matches(destination,payload,dirs)) and matches_file(archive,raw)
            h.record('Z20','actual-readme-command-'+str(index),passed,run)
    except (OSError,ValueError,StopIteration,UnicodeError,zipfile.BadZipFile,RuntimeError):h.record('Z20','actual-readme-command',False,reason='missing_or_invalid_documented_smoke')

def evaluate(h):
    valid,invalid=fixture_cases()
    for cid,cases in valid.items():
        for label,raw in cases:zip_case(h,cid,label,raw)
    for cid,cases in invalid.items():
        for label,raw in cases:zip_case(h,cid,label,raw,False)
    zip_case(h,'Z06','owned-absolute-sentinel',BASIC,False,owned_absolute=True)
    zip_case(h,'Z14','existing-destination',BASIC,existing=True)
    zip_case(h,'Z14','existing-destination-file',BASIC,existing='file')
    run=h.run(['-m','safezip','--help'],h.fixture('help'))
    h.record('Z18','help',success(run) and bool(run.get('stdout',b'')+run.get('stderr',b'')),run)
    zip_case(h,'Z18','paths with spaces',BASIC)
    authored(h,'Z19');readme(h)

def self_test():
    checks=0;valid,invalid=fixture_cases()
    for cases in valid.values():
        for _label,raw in cases:
            manifest,payload,_dirs=oracle(raw);assert manifest['file_count']==len(payload);assert len(raw)<3*1024*1024;checks+=1
    for cases in invalid.values():
        for _label,raw in cases:
            assert len(raw)<3*1024*1024
            try:oracle(raw)
            except (ValueError,zipfile.BadZipFile,RuntimeError,NotImplementedError):checks+=1
            else:raise AssertionError('Invalid fixture accepted by oracle')
    assert canonical(oracle(valid['Z04'][0][1])[0])==canonical(oracle(valid['Z04'][1][1])[0]);checks+=1
    assert oracle(BASIC)[1]['binary.dat']==bytes(range(256));checks+=1
    assert oracle(zip_bytes([]))[0]=={'schema':1,'entries':[],'file_count':0,'total_uncompressed_bytes':0};checks+=1
    controlled={'launch_error':False,'timed_out':False,'capture_complete':True,'exit_code':2,'stdout':b'','stderr':b'Invalid input\n','stdout_tail':b'','stderr_tail':b''}
    assert controlled_failure(controlled);checks+=1
    assert not controlled_failure({**controlled,'stderr_tail':b'Traceback (most recent call last):\n'});checks+=1
    assert not controlled_failure({**controlled,'capture_complete':False});checks+=1
    return checks

if __name__=='__main__':main()
