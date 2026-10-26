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

import csv
from decimal import Decimal
import io

PREFIX='L'
MONEY=re.compile(r'-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?')

def cents(value,positive=False):
    if not isinstance(value,str) or not MONEY.fullmatch(value):raise ValueError('money')
    amount=Decimal(value)
    if abs(amount)>Decimal('1000000.00') or positive and amount<=0:raise ValueError('bounds')
    return int(amount*100)

def table(raw,headers):
    text=raw.decode('utf-8-sig');reader=csv.reader(io.StringIO(text,newline=''),strict=True)
    try:actual=next(reader)
    except StopIteration:raise ValueError('headers')
    if len(actual)!=len(headers) or set(actual)!=set(headers):raise ValueError('headers')
    result=[]
    for row in reader:
        if not row:continue
        if len(row)!=len(actual):raise ValueError('row')
        result.append(dict(zip(actual,row)))
    return result

def oracle(orders,payments):
    orders=table(orders,('order_id','currency','amount'));payments=table(payments,('payment_id','order_id','currency','amount'))
    if len(orders)+len(payments)>10000:raise ValueError('rows')
    expected={};received={};seen={}
    for row in orders:
        key=row['order_id'];currency=row['currency']
        if not key or key in expected or re.fullmatch('[A-Z]{3}',currency) is None:raise ValueError('order')
        expected[key]=(currency,cents(row['amount'],True));received[key]=0
    for row in payments:
        key=row['payment_id'];order=row['order_id'];currency=row['currency'];amount=cents(row['amount'])
        if not key or order not in expected or expected[order][0]!=currency:raise ValueError('payment')
        payload=(order,currency,amount)
        if key in seen:
            if seen[key]!=payload:raise ValueError('duplicate')
            continue
        seen[key]=payload;received[order]+=amount
    rows=[];totals={}
    for key in sorted(expected):
        currency,due=expected[key];paid=received[key]
        status='negative_net' if paid<0 else 'unpaid' if paid==0 else 'partial' if paid<due else 'paid' if paid==due else 'overpaid'
        rows.append({'order_id':key,'currency':currency,'expected_cents':due,'received_cents':paid,'balance_cents':due-paid,'status':status})
        values=totals.setdefault(currency,[0,0]);values[0]+=due;values[1]+=paid
    return {'schema':1,'orders':rows,'totals':[{'currency':currency,'expected_cents':a,'received_cents':b,'balance_cents':a-b} for currency,(a,b) in sorted(totals.items())]}

def csv_bytes(headers,rows,bom=False):
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerow(headers);writer.writerows(rows)
    return (b'\xef\xbb\xbf' if bom else b'')+stream.getvalue().encode('utf-8')

def data(orders,payments,bom=False):return csv_bytes(('order_id','currency','amount'),orders,bom),csv_bytes(('payment_id','order_id','currency','amount'),payments,bom)

BASIC=data([('001','USD','0.30'),('x','EUR','2.00')],[('p1','001','USD','0.10'),('p2','001','USD','0.20'),('p3','x','EUR','1.00')])

def fixture_cases():
    valid={
      'L01':[('basic',*BASIC)],
      'L02':[('exact-cents',*data([('m','USD','0.30'),('big','USD','1000000.00')],[('a','m','USD','0.1'),('b','m','USD','0.20'),('c','big','USD','999999.99')]))],
      'L03':[('signed',*data([('a','USD','1.00'),('b','USD','1.00'),('c','USD','1.00')],[('p','a','USD','2.00'),('q','a','USD','-0.50'),('r','b','USD','-0.01')]))],
      'L04':[('currencies',*data([('a','JPY','2'),('b','USD','2'),('c','EUR','2')],[('x','a','JPY','1'),('y','b','USD','3')]))],
      'L05':[('opaque-ids',*data([('001','USD','1'),('1','USD','2'),(' a ','USD','3')],[('p','001','USD','1'),('q',' a ','USD','1')]))],
      'L06':[('permutation-a',*BASIC),('permutation-b',*data([('x','EUR','2.00'),('001','USD','0.30')],[('p3','x','EUR','1.00'),('p2','001','USD','0.20'),('p1','001','USD','0.10')]))],
      'L07':[('semantic-duplicates',*data([('a','USD','1')],[('p','a','USD','1.0'),('p','a','USD','1.00'),('p','a','USD','1')]))],
      'L14':[('quoted-utf8-bom',*data([('a,"Ω\nline','USD','1')],[('p,\n"Ω','a,"Ω\nline','USD','1')],True))],
      'L15':[('header-only',*data([],[])),('unpaid',*data([('a','USD','1')],[]))],
    }
    invalid={
      'L08':[('conflicting-payment',*data([('a','USD','1')],[('p','a','USD','1'),('p','a','USD','2')])),('conflicting-order',*data([('a','USD','1'),('b','USD','1')],[('p','a','USD','1'),('p','b','USD','1')]))],
      'L09':[('duplicate-order',*data([('a','USD','1'),('a','USD','1')],[]))],
      'L10':[('unknown-order',*data([('a','USD','1')],[('p','missing','USD','1')]))],
      'L11':[('currency-mismatch',*data([('a','USD','1')],[('p','a','EUR','1')]))],
      'L12':[('invalid-money-'+str(i),*data([('a','USD','1')],[('p','a','USD',amount)])) for i,amount in enumerate(('NaN','Inf','1e2','0.001','01.00','+1','1000000.01','-1000000.01'))],
      'L13':[('zero-byte',b'',BASIC[1]),('extra-header',b'order_id,currency,amount,extra\na,USD,1,x\n',BASIC[1]),('duplicate-header',b'order_id,currency,currency\na,USD,USD\n',BASIC[1]),('broken-quote',b'order_id,currency,amount\na,USD,"1.00\n',BASIC[1]),('empty-id',*data([('','USD','1')],[]))],
      'L16':[('late-invalid-atomic',*data([('a','USD','1')],[('ok','a','USD','1'),('bad','other','USD','1')]))],
    }
    valid['L02'].append(('row-limit-exact',*data([('a','USD','1000000')],[(str(i),'a','USD','0.01') for i in range(9999)])))
    invalid['L12'] += [('invalid-order-'+str(i),*data([('a','USD',value)],[])) for i,value in enumerate(('0','-0.01','1000000.01'))]
    invalid['L12'].append(('row-limit-exceeded',*data([('a','USD','1000000')],[(str(i),'a','USD','0.01') for i in range(10000)])))
    return valid,invalid

def ledger_case(h,cid,label,orders,payments,valid=True,existing=False):
    folder=h.fixture(label);a=folder/'orders.csv';b=folder/'payments.csv';output=folder/'report.json'
    a.write_bytes(orders);b.write_bytes(payments)
    if existing=='directory':output.mkdir();(output/'keep').write_bytes(b'PRESERVE_EXISTING_OUTPUT\n')
    elif existing:output.write_bytes(b'PRESERVE_EXISTING_OUTPUT\n')
    run=h.run(['-m','ledgerreconcile','--orders',str(a),'--payments',str(b),'--output',str(output)],folder)
    if valid and not existing:
        expected=canonical(oracle(orders,payments));passed=success(run) and matches_file(output,expected)
    else:passed=controlled_failure(run) and (output.is_dir() and {item.name for item in output.iterdir()}=={'keep'} and matches_file(output/'keep',b'PRESERVE_EXISTING_OUTPUT\n') if existing=='directory' else matches_file(output,b'PRESERVE_EXISTING_OUTPUT\n') if existing else not output.exists() if not existing else False)
    passed=passed and matches_file(a,orders) and matches_file(b,payments)
    h.record(cid,label,passed,run)

def readme(h):
    folder=h.fixture('readme-smoke')
    try:
        commands,test=readme_commands(h.solution,'ledgerreconcile')
        command=next(command for command in commands if len(command)==8 and set(command[2::2])=={'--orders','--payments','--output'})
        options=dict(zip(command[2::2],command[3::2]));a=example(h.solution,options['--orders']);b=example(h.solution,options['--payments']);expected=canonical(oracle(a.read_bytes(),b.read_bytes()))
        output=folder/'README-output.json';args=list(command);args[args.index('--output')+1]=str(output)
        run=h.run(args,folder);passed=test and ['-m','ledgerreconcile','--help'] in commands and success(run) and matches_file(output,expected)
        h.record('L20','actual-readme-command',passed,run)
    except (OSError,ValueError,StopIteration,UnicodeError):h.record('L20','actual-readme-command',False,reason='missing_or_invalid_documented_smoke')

def evaluate(h):
    valid,invalid=fixture_cases()
    for cid,cases in valid.items():
        for label,a,b in cases:ledger_case(h,cid,label,a,b)
    for cid,cases in invalid.items():
        for label,a,b in cases:ledger_case(h,cid,label,a,b,False)
    ledger_case(h,'L17','existing-output',*BASIC,existing=True)
    ledger_case(h,'L17','existing-output-directory',*BASIC,existing='directory')
    run=h.run(['-m','ledgerreconcile','--help'],h.fixture('help'))
    h.record('L18','help',success(run) and bool(run.get('stdout',b'')+run.get('stderr',b'')),run)
    ledger_case(h,'L18','paths with spaces',*BASIC)
    authored(h,'L19');readme(h)

def self_test():
    checks=0;valid,invalid=fixture_cases()
    for cases in valid.values():
        for _label,a,b in cases:
            report=oracle(a,b);assert set(report)=={'schema','orders','totals'} and isinstance(report['totals'],list);assert canonical(report).endswith(b'\n');checks+=1
    for cases in invalid.values():
        for _label,a,b in cases:
            try:oracle(a,b)
            except (ValueError,csv.Error,UnicodeError):checks+=1
            else:raise AssertionError('Invalid fixture accepted by oracle')
    report=oracle(*BASIC);assert report['orders'][0]['received_cents']==30;checks+=1
    assert canonical(oracle(*valid['L06'][0][1:]))==canonical(oracle(*valid['L06'][1][1:]));checks+=1
    assert oracle(*valid['L07'][0][1:])['orders'][0]['received_cents']==100;checks+=1
    assert b'\nline' in valid['L14'][0][1] and isinstance(oracle(*BASIC)['totals'],list);checks+=1
    assert cents('1000000.00')==100000000 and cents('-0.01')==-1;checks+=1
    controlled={'launch_error':False,'timed_out':False,'capture_complete':True,'exit_code':2,'stdout':b'','stderr':b'Invalid input\n','stdout_tail':b'','stderr_tail':b''}
    assert controlled_failure(controlled);checks+=1
    assert not controlled_failure({**controlled,'stderr_tail':b'Traceback (most recent call last):\n'});checks+=1
    assert not controlled_failure({**controlled,'capture_complete':False});checks+=1
    return checks

if __name__=='__main__':main()
