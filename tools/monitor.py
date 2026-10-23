"""Optional metadata-only Windows resource sampling of owned experiment PIDs.

Run beside the experiment. It never reads prompts, output, or credentials.
Missing early samples are explicit; this is not a whole-machine performance trace.
"""
from pathlib import Path
import argparse, ctypes, json, os, time
from datetime import datetime, timezone
from ctypes import wintypes

class Memory(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ['peak_working_set','working_set','quota_peak_paged','quota_paged','quota_peak_nonpaged','quota_nonpaged','pagefile','peak_pagefile']]

def sample(pid):
    k=ctypes.WinDLL('kernel32',use_last_error=True);ps=ctypes.WinDLL('psapi',use_last_error=True)
    k.OpenProcess.restype=wintypes.HANDLE;k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    k.CloseHandle.argtypes=[wintypes.HANDLE]
    ps.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Memory),wintypes.DWORD]
    h=k.OpenProcess(0x410,False,pid)
    if not h:return None
    try:
        m=Memory();m.cb=ctypes.sizeof(m)
        if not ps.GetProcessMemoryInfo(h,ctypes.byref(m),m.cb):return None
        return {'pid':pid,'working_set_bytes':m.working_set,'peak_working_set_bytes':m.peak_working_set}
    finally:k.CloseHandle(h)

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--seconds',type=int,default=2400)
    a=p.parse_args();end=time.monotonic()+min(max(a.seconds,1),7200)
    if os.name!='nt':raise SystemExit('Windows collector; use platform-native collector elsewhere')
    with (a.root/'resource-samples.jsonl').open('a',encoding='utf-8') as f:
        while time.monotonic()<end:
            controls=list(a.root.glob('run-*/control.json'))+list(a.root.glob('harness-*/probe-run-*/control.json'))
            for path in controls:
                try:
                    c=json.loads(path.read_text())
                    if c.get('status')!='running':continue
                    r=sample(c['pid'])
                    if r:f.write(json.dumps(dict(r,run=str(path.parent.relative_to(a.root)),timestamp=datetime.now(timezone.utc).isoformat(),scope='root PID only; sampling began after launch'))+'\n');f.flush()
                except (OSError,ValueError):continue
            if (a.root/'metrics.json').exists():break
            time.sleep(5)

if __name__=='__main__':main()
