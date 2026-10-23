"""Bind redirected test-host stdio to actual ConPTY devices, then run the app.

This helper also measures actual console modes before and after the app. It
never forces isatty or substitutes a fake terminal implementation.
"""
import ctypes as C
from ctypes import wintypes as W
import msvcrt
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    source=os.open("CONIN$",os.O_RDWR)
    target=os.open("CONOUT$",os.O_RDWR)
    for origin,destination in ((source,0),(target,1),(target,2)):
        os.dup2(origin,destination)
    os.close(source); os.close(target)
    k=C.WinDLL("kernel32",use_last_error=True)
    k.SetStdHandle.argtypes=[W.DWORD,W.HANDLE]
    k.GetConsoleMode.argtypes=[W.HANDLE,C.POINTER(W.DWORD)]
    for number,fd in ((-10,0),(-11,1),(-12,2)):
        if not k.SetStdHandle(number,msvcrt.get_osfhandle(fd)):
            raise C.WinError(C.get_last_error())

    def snapshot():
        modes=[]
        for fd in (0,1):
            mode=W.DWORD()
            if not k.GetConsoleMode(msvcrt.get_osfhandle(fd),C.byref(mode)):
                raise C.WinError(C.get_last_error())
            modes.append(mode.value)
        return modes

    before=snapshot()
    from ascii_tree.cli import main as app_main
    code=app_main(["view",*sys.argv[1:]])
    after=snapshot()
    if before!=after:
        print(f"CONSOLE_MODE_RESTORE_FAILED {before} -> {after}",flush=True)
        return 97
    print("CONSOLE_MODES_RESTORED",flush=True)
    return code


if __name__=="__main__":
    raise SystemExit(main())
