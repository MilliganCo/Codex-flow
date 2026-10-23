"""Actual Windows ConPTY lifecycle/input/resize check, no third-party package.

Creates only this application's console and exits within 45 seconds. Captures
the native VT stream and a JSON report in artifacts/. This is not a screenshot
or a mock of Terminal; the child uses actual Get/SetConsoleMode and msvcrt.
"""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import json
import os
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


class COORD(C.Structure):
    _fields_=[("X",C.c_short),("Y",C.c_short)]


class STARTUPINFO(C.Structure):
    _fields_=[("cb",W.DWORD),("lpReserved",W.LPWSTR),("lpDesktop",W.LPWSTR),
              ("lpTitle",W.LPWSTR),("dwX",W.DWORD),("dwY",W.DWORD),
              ("dwXSize",W.DWORD),("dwYSize",W.DWORD),("dwXCountChars",W.DWORD),
              ("dwYCountChars",W.DWORD),("dwFillAttribute",W.DWORD),
              ("dwFlags",W.DWORD),("wShowWindow",W.WORD),("cbReserved2",W.WORD),
              ("lpReserved2",C.POINTER(W.BYTE)),("hStdInput",W.HANDLE),
              ("hStdOutput",W.HANDLE),("hStdError",W.HANDLE)]


class STARTUPINFOEX(C.Structure):
    _fields_=[("StartupInfo",STARTUPINFO),("lpAttributeList",C.c_void_p)]


class PROCESSINFO(C.Structure):
    _fields_=[("hProcess",W.HANDLE),("hThread",W.HANDLE),
              ("dwProcessId",W.DWORD),("dwThreadId",W.DWORD)]


class Console:
    def __init__(self, arguments):
        self.k=C.WinDLL("kernel32",use_last_error=True)
        k=self.k
        definitions={
            "CreatePipe":([C.POINTER(W.HANDLE),C.POINTER(W.HANDLE),C.c_void_p,W.DWORD],W.BOOL),
            "CloseHandle":([W.HANDLE],W.BOOL),
            "CreatePseudoConsole":([COORD,W.HANDLE,W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)],C.c_long),
            "ResizePseudoConsole":([W.HANDLE,COORD],C.c_long),
            "ClosePseudoConsole":([W.HANDLE],None),
            "InitializeProcThreadAttributeList":([C.c_void_p,W.DWORD,W.DWORD,C.POINTER(C.c_size_t)],W.BOOL),
            "UpdateProcThreadAttribute":([C.c_void_p,W.DWORD,C.c_size_t,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p],W.BOOL),
            "DeleteProcThreadAttributeList":([C.c_void_p],None),
            "CreateProcessW":([W.LPCWSTR,W.LPWSTR,C.c_void_p,C.c_void_p,W.BOOL,W.DWORD,C.c_void_p,W.LPCWSTR,C.POINTER(STARTUPINFO),C.POINTER(PROCESSINFO)],W.BOOL),
            "ReadFile":([W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p],W.BOOL),
            "WriteFile":([W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p],W.BOOL),
            "WaitForSingleObject":([W.HANDLE,W.DWORD],W.DWORD),
            "GetExitCodeProcess":([W.HANDLE,C.POINTER(W.DWORD)],W.BOOL),
            "TerminateProcess":([W.HANDLE,W.UINT],W.BOOL),
        }
        for name,(argtypes,restype) in definitions.items():
            getattr(k,name).argtypes=argtypes
            getattr(k,name).restype=restype
        self.inread=W.HANDLE(); self.input=W.HANDLE()
        self.output=W.HANDLE(); self.outwrite=W.HANDLE(); self.pc=W.HANDLE()
        self.process=PROCESSINFO()
        self.buffer=bytearray()
        self.closed=False
        self.check(k.CreatePipe(C.byref(self.inread),C.byref(self.input),None,0))
        self.check(k.CreatePipe(C.byref(self.output),C.byref(self.outwrite),None,0))
        self.check(k.CreatePseudoConsole(COORD(100,40),self.inread,self.outwrite,0,C.byref(self.pc))==0)
        k.CloseHandle(self.inread); k.CloseHandle(self.outwrite)
        size=C.c_size_t()
        k.InitializeProcThreadAttributeList(None,1,0,C.byref(size))
        self.attributes=C.create_string_buffer(size.value)
        self.check(k.InitializeProcThreadAttributeList(self.attributes,1,0,C.byref(size)))
        self.check(k.UpdateProcThreadAttribute(self.attributes,0,0x00020016,self.pc,C.sizeof(W.HANDLE),None,None))
        startup=STARTUPINFOEX()
        startup.StartupInfo.cb=C.sizeof(startup)
        startup.lpAttributeList=C.cast(self.attributes,C.c_void_p)
        # When this harness itself has redirected stdio, Windows may preserve
        # those inherited standard handles despite attaching a real console.
        # Bind the child's OS descriptors to its real ConPTY console devices.
        command=C.create_unicode_buffer(subprocess.list2cmdline([sys.executable,str(ROOT/"tools"/"console_child.py"),*arguments]))
        self.check(k.CreateProcessW(None,command,None,None,False,0x00080000,None,str(ROOT),
                                   C.byref(startup.StartupInfo),C.byref(self.process)))
        k.DeleteProcThreadAttributeList(self.attributes)
        self.reader=threading.Thread(target=self.read,daemon=True)
        self.reader.start()

    @staticmethod
    def check(ok):
        if not ok:
            raise C.WinError(C.get_last_error())

    def read(self):
        block=C.create_string_buffer(8192)
        count=W.DWORD()
        while self.k.ReadFile(self.output,block,len(block),C.byref(count),None) and count.value:
            self.buffer.extend(block.raw[:count.value])

    def send(self,text):
        data=text.encode("ascii")
        count=W.DWORD()
        self.check(self.k.WriteFile(self.input,data,len(data),C.byref(count),None))

    def expect(self,token,start=0,timeout=5):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if token in bytes(self.buffer[start:]):
                return
            if self.k.WaitForSingleObject(self.process.hProcess,0)==0:
                raise AssertionError(f"child exited before {token!r}: {bytes(self.buffer[-600:])!r}")
            time.sleep(.02)
        raise AssertionError(f"missing {token!r}: {bytes(self.buffer[-600:])!r}")

    def key_expect(self,key,token):
        start=len(self.buffer)
        self.send(key)
        self.expect(token,start)

    def finish(self,key="q",expected=0):
        self.send(key)
        if self.k.WaitForSingleObject(self.process.hProcess,5000)!=0:
            raise AssertionError(f"child did not exit within 5s after key {key!r}")
        code=W.DWORD()
        self.check(self.k.GetExitCodeProcess(self.process.hProcess,C.byref(code)))
        time.sleep(.1)
        assert code.value==expected,("exit",code.value)
        assert b"\x1b[?25h" in self.buffer,"cursor restore absent"
        assert b"\x1b[?1049l" in self.buffer,"alternate-screen restore absent"
        assert b"CONSOLE_MODES_RESTORED" in self.buffer,"actual input/output console modes not restored"
        assert b"Traceback" not in self.buffer,bytes(self.buffer[-1000:])

    def close(self):
        if self.closed:
            return
        self.closed=True
        if self.process.hProcess and self.k.WaitForSingleObject(self.process.hProcess,0)!=0:
            self.k.TerminateProcess(self.process.hProcess,99)
            self.k.WaitForSingleObject(self.process.hProcess,2000)
        self.k.CloseHandle(self.input)
        # Drain in the reader while ClosePseudoConsole flushes its final output.
        self.k.ClosePseudoConsole(self.pc)
        self.k.CloseHandle(self.output)
        self.reader.join(timeout=1)
        self.k.CloseHandle(self.process.hThread)
        self.k.CloseHandle(self.process.hProcess)


def main():
    if os.name!="nt":
        print("NOT RUN: native ConPTY smoke requires Windows 10 1809+ / Windows 11")
        return 2
    artifacts=ROOT/"artifacts"
    exports=ROOT/".tmp"/"terminal-smoke"
    artifacts.mkdir(exist_ok=True); exports.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(ROOT))
    from ascii_tree.model import generate_tree
    from ascii_tree.render import render, RenderOptions
    report={"platform":sys.platform,"backend":"actual Windows ConPTY","checks":[]}
    consoles=[]
    try:
        c=Console(["--seed","42","--mode","3d","--export-dir",str(exports)])
        consoles.append(c)
        c.expect(b"3D"); report["checks"].append("startup 100x40")
        c.key_expect("1",b"2D")
        c.key_expect("e",b"Saved")
        c.key_expect("2",b"3D")
        c.key_expect("\x1b[C",b"yaw")
        c.key_expect("\x1b[A",b"tilt")
        c.key_expect("e",b"Saved")
        c.key_expect("3",b"4D DATA PROJECTION")
        c.key_expect("]",b"XW")
        c.key_expect("e",b"Saved")
        report["checks"].append("mode keys 1/2/3, arrows, XW ], export E")
        for mode in ("2d","3d","4d"):
            data=(exports/f"tree-42-{mode}.txt").read_bytes()
            assert len(data)==100*35,(mode,len(data)) # 99 raster cols + LF
            assert all(b==10 or 32<=b<=126 for b in data)
            expected=render(generate_tree(42),RenderOptions(99,35,mode,
                            yaw=.45 if mode=="2d" else .57,
                            pitch=.08 if mode=="2d" else .18,
                            angle4=.12 if mode=="4d" else 0))
            assert data==expected.encode("ascii"),(mode,"key-driven frame differs from expected camera")
        report["checks"].append("native key-driven exports match exact expected 2D/3D/4D rasters")
        c.key_expect("h",b"FIELD GUIDE")
        c.key_expect("h",b"4D DATA PROJECTION")
        c.key_expect(" ",b"PLAY")
        time.sleep(.3)
        c.key_expect(" ",b"PAUSED")
        c.key_expect("+",b"zoom")
        c.key_expect("r",b"zoom")
        c.key_expect("g",b"seed 43")
        report["checks"].append("help, animation pause/resume, zoom/reset, new seed")
        for width,height in ((20,8),(8,4),(100,40)):
            start=len(c.buffer)
            c.check(c.k.ResizePseudoConsole(c.pc,COORD(width,height))==0)
            c.expect(b"ASCII" if width>8 else b"AS",start)
        c.check(c.k.ResizePseudoConsole(c.pc,COORD(1,1))==0)
        time.sleep(.2)
        assert c.k.WaitForSingleObject(c.process.hProcess,0)!=0,"crash at 1x1"
        start=len(c.buffer)
        c.check(c.k.ResizePseudoConsole(c.pc,COORD(100,40))==0)
        c.expect(b"ASCII",start)
        report["checks"].append("native resize 100x40 -> 20x8 -> 8x4 -> 1x1 -> 100x40")
        c.finish(); c.close()
        report["checks"].append("Q exit 0, cursor + alternate screen restored")
        c=Console(["--seed","42","--mode","4d"])
        consoles.append(c)
        c.expect(b"4D DATA PROJECTION")
        c.finish("\x03",130); c.close()
        report["checks"].append("fresh startup, real Ctrl+C exit 130, terminal restored")
        c=Console(["--seed","43","--mode","2d"])
        consoles.append(c)
        c.expect(b"2D")
        c.finish("\x1b"); c.close()
        report["checks"].append("seed 43 startup, real Esc exit 0, console modes restored")
        report["status"]="PASS"
    except Exception as exc:
        report["status"]="FAIL"
        report["error"]=str(exc)
    finally:
        for index,c in enumerate(consoles):
            c.close()
            (artifacts/f"terminal-{index+1}.vt").write_bytes(bytes(c.buffer))
        (artifacts/"terminal-smoke.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0 if report["status"]=="PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
