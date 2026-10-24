"""Fixed 57-check case09 protocol. No app imports: real ConPTY plus CLI oracles."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from types import MappingProxyType
from conpty_case09_neutral import WindowsConsole

HERE = Path(__file__).resolve().parent

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def manifest(root):
    return {str(p.relative_to(root)).replace('\\','/'):sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and '.tmp' not in p.parts}

def valid(data,width,height):
    lines=data.split(b'\n')
    return len(lines)==height+1 and lines[-1]==b'' and all(len(line)==width for line in lines[:-1])

def ascii_lf(data):
    return bool(data) and all(b==10 or 32<=b<=126 for b in data) and data.endswith(b'\n')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--solution','--solution-root',dest='solution',type=Path,required=True)
    parser.add_argument('--id','--solution-id',dest='id',choices=('17','18'),required=True)
    output=parser.add_mutually_exclusive_group(required=True)
    output.add_argument('--output',type=Path)
    output.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    if args.output_dir is not None:
        args.output=args.output_dir/'report.json'
    root=args.solution.resolve()
    destination=args.output.resolve().parent
    destination.mkdir(parents=True,exist_ok=True)
    export_dir=destination/('native57-exports-'+args.id)
    export_dir.mkdir(exist_ok=False)
    frozen_sources=MappingProxyType(manifest(root))
    report={'protocol':'conpty-case09-57','solution':'solution-'+args.id,'checks':[],
            'exports':[],'oracles':[],'errors':[], 'source_before':dict(frozen_sources),
            'checker_hashes':{p.name:sha(p) for p in (Path(__file__),HERE/'conpty_case09_neutral.py',HERE/'evaluator.py',HERE/'rubric.json')},
            'adapter':{'module':'ascii_tree','plane':'XW','initial_yaw':25 if args.id=='17' else -22,
                       'initial_pitch':-8 if args.id=='17' else 8,'initial_angle4d':0,'next_seed':'seed+1',
                       'yaw_step':7.5 if args.id=='17' else 8,'pitch_step':5 if args.id=='17' else 6,
                       'xw_step':7.5 if args.id=='17' else 8,'zoom_in':1.12 if args.id=='17' else 1.1,
                       'zoom_out':1/1.12 if args.id=='17' else .9,
                       'viewport_100x40':[99,33] if args.id=='17' else [99,37],
                       'viewport_30x12':[29,5] if args.id=='17' else [29,9],
                       'viewport_1x1':[1,1]}}
    console=None
    sessions=[]
    def check(name,passed,**detail):
        report['checks'].append({'number':len(report['checks'])+1,'name':name,'status':'pass' if passed else 'fail',**detail})
    state={'seed':42,'mode':'2d','yaw':25. if args.id=='17' else -22.,'pitch':-8. if args.id=='17' else 8.,'angle4d':0.,'zoom':1.}
    width,height=report['adapter']['viewport_100x40']
    def oracle(label):
        command=[sys.executable,'-B','-m','ascii_tree','render','--width',str(width),'--height',str(height)]
        for k,v in state.items(): command+=['--'+k,str(v)]
        command+=['--time','0']
        result=subprocess.run(command,cwd=root,capture_output=True,timeout=15)
        path=destination/('oracle-'+label+'.txt')
        path.write_bytes(result.stdout)
        (destination/('oracle-'+label+'.stderr.txt')).write_bytes(result.stderr)
        report['oracles'].append({'label':label,'command':command,'returncode':result.returncode,
                                  'sha256':hashlib.sha256(result.stdout).hexdigest(),'path':str(path)})
        if result.returncode: raise RuntimeError('headless oracle failed: '+label+' '+result.stderr.decode('utf-8','replace'))
        return result.stdout
    def snapshot(label,top=True):
        before=set(export_dir.glob('*.txt'))
        console.send('e')
        console.wait_for(lambda: bool(set(export_dir.glob('*.txt'))-before),5)
        additions=set(export_dir.glob('*.txt'))-before
        if len(additions)!=1: raise RuntimeError('expected one new export: '+label)
        path=next(iter(additions))
        # Creation precedes completion of write; wait for the same LF rectangle, not a second input.
        console.wait_for(lambda: valid(path.read_bytes(),width,height),5)
        data=path.read_bytes()
        report['exports'].append({'label':label,'path':str(path),'width':width,'height':height,
                                  'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
        if top:
            check(label+'.dimensions',valid(data,width,height),width=width,height=height)
            check(label+'.ascii_lf',ascii_lf(data))
        elif not valid(data,width,height) or not ascii_lf(data):
            raise RuntimeError('embedded export is not a bounded ASCII frame: '+label)
        return data
    def frame(label):
        data=snapshot(label)
        check(label+'.oracle',data==oracle(label))
        return data
    def leave(label,key,codes):
        console.send(key)
        code=console.wait(5)
        console.wait_for(lambda: b'\x1b[?25h' in bytes(console.output) and b'\x1b[?1049l' in bytes(console.output),5)
        check(label+'.exit_code',code in codes,returncode=code)
        check(label+'.restore',b'\x1b[?25h' in bytes(console.output) and b'\x1b[?1049l' in bytes(console.output))
        console.close()
    try:
        # -B must not enter neutral bootstrap argv, whose explicit module contract starts at -m.
        import os
        os.environ['PYTHONDONTWRITEBYTECODE']='1'
        def start(label):
            c=WindowsConsole(['-m','ascii_tree','view','--seed','42','--mode','2d','--export-dir',str(export_dir)],root,100,40)
            sessions.append((label,c))
            return c
        console=start('main')
        console.wait_for(lambda:b'ASCII TREE EXPLORER' in bytes(console.output),5)
        check('startup.marker',True)
        console.send('1')
        f2=frame('2d')
        console.send('2');state['mode']='3d'
        f3=snapshot('3d')
        original_oracle=oracle('3d')
        console.send(b'\x1b[C\x1b[A')
        state['yaw']=(state['yaw']+report['adapter']['yaw_step'])%360
        state['pitch']+=report['adapter']['pitch_step']
        orbited=snapshot('3d-roundtrip-forward',False)
        forward_oracle=oracle('3d-roundtrip-forward')
        console.send(b'\x1b[D\x1b[B')
        state['yaw']=(state['yaw']-report['adapter']['yaw_step'])%360
        state['pitch']-=report['adapter']['pitch_step']
        restored=snapshot('3d-roundtrip-reverse',False)
        restored_oracle=oracle('3d-roundtrip-reverse')
        check('3d.oracle_and_embedded_camera_roundtrip',f3==original_oracle and orbited!=f3 and orbited==forward_oracle
              and restored==f3 and restored==restored_oracle)
        console.send('3');state['mode']='4d'
        f4=frame('4d')
        check('three_distinct_shared_seed_modes',len({f2,f3,f4})==3)
        console.send(']');state['angle4d']=report['adapter']['xw_step']
        frame('xw-forward')
        console.send('[');state['angle4d']=0.
        frame('xw-reverse')
        console.send(b'\x1b[C\x1b[A')
        state['yaw']=(state['yaw']+report['adapter']['yaw_step'])%360
        state['pitch']+=report['adapter']['pitch_step']
        frame('camera-forward')
        console.send('+');state['zoom']*=report['adapter']['zoom_in']
        frame('zoom-in')
        console.send('-');state['zoom']*=report['adapter']['zoom_out']
        rotated=frame('zoom-out')
        offset=len(console.output)
        console.send('h')
        marker=b'ONE TREE / THREE VIEWS' if args.id=='17' else b'ASCII TREE EXPLORER / controls'
        console.wait_for(lambda:marker in bytes(console.output[offset:]),5)
        check('help.marker',True)
        console.send('?')
        frame('help-closed')
        console.send(' ');time.sleep(.45);console.send(' ')
        animated=snapshot('animation')
        check('animation.changed',animated!=rotated)
        time.sleep(.15)
        paused=snapshot('paused')
        check('paused.identical',paused==animated)
        console.send('r')
        state.update(yaw=25. if args.id=='17' else -22.,pitch=-8. if args.id=='17' else 8.,angle4d=0.,zoom=1.)
        frame('reset')
        console.send('g');state['seed']=43
        frame('new-seed')
        console.resize(30,12);time.sleep(.3)
        width,height=report['adapter']['viewport_30x12']
        frame('resize-30x12')
        console.resize(1,1);time.sleep(.3)
        width,height=1,1
        frame('resize-1x1')
        console.resize(100,40);time.sleep(.3)
        width,height=report['adapter']['viewport_100x40']
        frame('resize-restored')
        leave('q','q',(0,))
        console=start('escape')
        console.wait_for(lambda:b'ASCII TREE EXPLORER' in bytes(console.output),5)
        leave('escape',b'\x1b',(0,))
        console=start('ctrl-c')
        console.wait_for(lambda:b'ASCII TREE EXPLORER' in bytes(console.output),5)
        leave('ctrl-c',b'\x03',(0,130))
    except Exception:
        report['errors'].append(traceback.format_exc())
    finally:
        for label,c in sessions:
            c.close()
            transcript=destination/('conpty-'+label+'.bin')
            transcript.write_bytes(bytes(c.output))
            report.setdefault('transcripts',[]).append({'session':label,'path':str(transcript),'sha256':sha(transcript),'bytes':len(c.output)})
        report['source_after']=manifest(root)
        report['sources_unchanged']=dict(frozen_sources)==report['source_after']
        report['executed_checks']=len(report['checks'])
        report['unexecuted_check_numbers']=list(range(len(report['checks'])+1,58))
        report['smoke_completion']='pass' if len(report['checks'])==57 and not report['errors'] and all(c['status']=='pass' for c in report['checks']) and report['sources_unchanged'] else 'fail'
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(json.dumps({'output':str(args.output),'checks':len(report['checks']),'smoke_completion':report['smoke_completion'],
                          'sources_unchanged':report['sources_unchanged'],'error_count':len(report['errors'])}))
    return 0 if report['smoke_completion']=='pass' else 1

if __name__=='__main__':
    raise SystemExit(main())
