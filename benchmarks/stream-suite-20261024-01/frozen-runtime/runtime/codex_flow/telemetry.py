"""Bounded JSONL with metadata-only native events and safe replay."""
from datetime import datetime, timezone
from pathlib import Path
import json, re, time
import uuid
import os, tempfile, threading
from .contracts import inside

SECRET=re.compile(r'(?i)(?:sk-(?:or-v1-|proj-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}|Bearer\s+\S+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)')
PRIVATE=re.compile(r'(?i)(?:[A-Z]:[\\/][^\s\"<>]*|/(?:home|Users)/[^\s\"<>]*)')

def sanitize(value):
    if isinstance(value,dict):
        return {k: '[REDACTED]' if any(s in k.lower() for s in ('secret','password','authorization','api_key','prompt','command','output_text')) else sanitize(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)): return [sanitize(v) for v in value[:100]]
    if isinstance(value,str): return PRIVATE.sub('[LOCAL_PATH]',SECRET.sub('[REDACTED]',value))[:2048]
    return value

def utc(): return datetime.now(timezone.utc).isoformat()

def write_json(path: Path, value):
    inside(path.parent,path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.flow-',suffix='.tmp',dir=path.parent)
    temp=Path(name)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
            stream.flush();os.fsync(stream.fileno())
        inside(path.parent,path)
        temp.replace(path)
    finally:temp.unlink(missing_ok=True)

class Trace:
    def __init__(self,path:Path,run_id:str,task_id='root'):
        inside(path.parent,path)
        self.path=path; self.run_id=run_id; self.task_id=task_id
        self._lock=threading.Lock()
        self.trace_id=uuid.uuid4().hex; self.start=time.monotonic()
        path.parent.mkdir(parents=True,exist_ok=True)
    def emit(self,event_type,payload=None,actor='coordinator',model='gpt-6.1-sol',error_category=None):
        event=dict(run_id=self.run_id,trace_id=self.trace_id,task_id=self.task_id,timestamp=utc(),
                   actor=actor,model=model,event_type=event_type,duration_s=round(time.monotonic()-self.start,4),
                   payload=sanitize(payload or {}),token_usage=None,error_category=error_category)
        with self._lock:
            inside(self.path.parent,self.path)
            with self.path.open('a',encoding='utf-8') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')

def replay(path:Path):
    counts:dict[str,int]={}; usage=None; errors=0
    with path.open(encoding='utf-8') as f:
        for line in f:
            if len(line)>65536: raise ValueError('oversized event')
            e=json.loads(line); kind=e.get('event_type','unknown'); counts[kind]=counts.get(kind,0)+1
            if e.get('error_category'):errors+=1
            if kind=='native.turn.completed': usage=e.get('payload',{}).get('usage')
    return {'events':counts,'errors':errors,'usage':usage}
