"""ConPTY test bootstrap when the harness itself has redirected std handles.

Windows copies the parent's std handle numbers even when they are not inherited.
Provide the attached pseudoconsole's actual handles before running the app.
This is test plumbing, not a fallback for noninteractive `view` users.
"""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import runpy
import sys

import msvcrt

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
for target, name, flags, identifier in (
    (0, "CONIN$", os.O_RDWR, -10),
    (1, "CONOUT$", os.O_RDWR, -11),
    (2, "CONOUT$", os.O_RDWR, -12),
):
    descriptor = os.open(name, flags | os.O_BINARY)
    os.dup2(descriptor, target)
    if descriptor != target:
        os.close(descriptor)
    if not kernel.SetStdHandle(identifier & 0xffffffff, msvcrt.get_osfhandle(target)):
        raise ctypes.WinError(ctypes.get_last_error())

sys.stdin = sys.__stdin__ = open(0, "r", encoding="utf-8", closefd=False)
sys.stdout = sys.__stdout__ = open(1, "w", encoding="utf-8", buffering=1, closefd=False)
sys.stderr = sys.__stderr__ = open(2, "w", encoding="utf-8", buffering=1, closefd=False)
arguments = sys.argv[1:]
if arguments[0] != "-m":
    raise ValueError("the console harness accepts '-m module' invocations")
sys.argv = arguments[1:]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
runpy.run_module(arguments[1], run_name="__main__", alter_sys=True)
