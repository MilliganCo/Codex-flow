"""Minimal local ConPTY harness for actual Windows console integration checks.

No extra process except the requested Python program, no visible helper window,
no third-party packages. Kept outside the application runtime.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import threading
import time


class COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE),
    ]


class STARTUPINFOEX(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFO), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


class WindowsConsole:
    def __init__(self, args: list[str], cwd: Path, width: int = 100, height: int = 40):
        if os.name != "nt":
            raise OSError("ConPTY requires Windows 10/11")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        k = self.kernel
        handle, dword, void = wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p
        k.CreatePipe.argtypes = [ctypes.POINTER(handle), ctypes.POINTER(handle), void, dword]
        k.CreatePipe.restype = wintypes.BOOL
        k.CreatePseudoConsole.argtypes = [COORD, handle, handle, dword, ctypes.POINTER(handle)]
        k.CreatePseudoConsole.restype = ctypes.c_long
        k.ResizePseudoConsole.argtypes = [handle, COORD]
        k.ResizePseudoConsole.restype = ctypes.c_long
        k.ClosePseudoConsole.argtypes = [handle]
        k.CloseHandle.argtypes = [handle]
        k.InitializeProcThreadAttributeList.argtypes = [void, dword, dword, ctypes.POINTER(ctypes.c_size_t)]
        k.UpdateProcThreadAttribute.argtypes = [void, dword, ctypes.c_size_t, void, ctypes.c_size_t, void, void]
        k.DeleteProcThreadAttributeList.argtypes = [void]
        k.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, void, void, wintypes.BOOL,
                                     dword, void, wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOEX), ctypes.POINTER(PROCESS_INFORMATION)]
        k.CreateProcessW.restype = wintypes.BOOL
        k.ReadFile.argtypes = [handle, void, dword, ctypes.POINTER(dword), void]
        k.WriteFile.argtypes = [handle, void, dword, ctypes.POINTER(dword), void]
        k.WaitForSingleObject.argtypes = [handle, dword]
        k.WaitForSingleObject.restype = dword
        k.GetExitCodeProcess.argtypes = [handle, ctypes.POINTER(dword)]
        k.TerminateProcess.argtypes = [handle, wintypes.UINT]
        self.handles: list = []
        self.hpc = handle()
        self.process = PROCESS_INFORMATION()
        self.output = bytearray()
        self.reader = None
        self.closed = False
        self.attributes = None
        try:
            input_read, input_write, output_read, output_write = (handle() for _ in range(4))
            self._check(k.CreatePipe(ctypes.byref(input_read), ctypes.byref(input_write), None, 0))
            self.handles.extend((input_read, input_write))
            self._check(k.CreatePipe(ctypes.byref(output_read), ctypes.byref(output_write), None, 0))
            self.handles.extend((output_read, output_write))
            self.input_write, self.output_read = input_write, output_read
            hr = k.CreatePseudoConsole(COORD(width, height), input_read, output_write, 0, ctypes.byref(self.hpc))
            if hr < 0:
                raise OSError(f"CreatePseudoConsole HRESULT 0x{hr & 0xffffffff:08x}")
            size = ctypes.c_size_t()
            k.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
            self.attributes = ctypes.create_string_buffer(size.value)
            self._check(k.InitializeProcThreadAttributeList(self.attributes, 1, 0, ctypes.byref(size)))
            self._check(k.UpdateProcThreadAttribute(self.attributes, 0, 0x00020016,
                                                   self.hpc, ctypes.sizeof(handle), None, None))
            startup = STARTUPINFOEX()
            startup.StartupInfo.cb = ctypes.sizeof(startup)
            startup.StartupInfo.dwFlags = 1  # STARTF_USESHOWWINDOW
            startup.StartupInfo.wShowWindow = 0  # SW_HIDE
            startup.lpAttributeList = ctypes.cast(self.attributes, void)
            command = ctypes.create_unicode_buffer(subprocess.list2cmdline([
                sys.executable, str(cwd / "scripts" / "console_child.py"), *args]))
            self._check(k.CreateProcessW(None, command, None, None, False, 0x00080000,
                                         None, str(cwd), ctypes.byref(startup), ctypes.byref(self.process)))
            self.handles.extend((self.process.hProcess, self.process.hThread))
            # Only ConPTY retains these ends. EOF becomes observable after its close.
            for h in (input_read, output_write):
                k.CloseHandle(h)
                self.handles.remove(h)
            self.reader = threading.Thread(target=self._read, daemon=True)
            self.reader.start()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _check(ok):
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())

    def _read(self):
        buffer = ctypes.create_string_buffer(16384)
        count = wintypes.DWORD()
        while self.kernel.ReadFile(self.output_read, buffer, len(buffer), ctypes.byref(count), None) and count.value:
            chunk = buffer.raw[:count.value]
            self.output.extend(chunk)
            if b"\x1b[6n" in chunk:
                self.send(b"\x1b[1;1R")

    def send(self, data: str | bytes):
        data = data.encode("ascii") if isinstance(data, str) else data
        count = wintypes.DWORD()
        self._check(self.kernel.WriteFile(self.input_write, data, len(data), ctypes.byref(count), None))

    def resize(self, width: int, height: int):
        hr = self.kernel.ResizePseudoConsole(self.hpc, COORD(width, height))
        if hr < 0:
            raise OSError(f"ResizePseudoConsole HRESULT 0x{hr & 0xffffffff:08x}")

    def wait_for(self, predicate, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            if self.process.hProcess and self.kernel.WaitForSingleObject(self.process.hProcess, 0) == 0:
                # Let the pipe reader drain the final bytes before reporting failure.
                time.sleep(0.03)
                if predicate():
                    return
                break
            time.sleep(0.01)
        raise TimeoutError("ConPTY condition unmet; output tail: " + bytes(self.output[-2000:]).decode("ascii", "replace"))

    def wait(self, timeout: float = 5.0) -> int:
        if self.kernel.WaitForSingleObject(self.process.hProcess, int(timeout * 1000)) != 0:
            raise TimeoutError("interactive process failed to exit")
        code = wintypes.DWORD()
        self._check(self.kernel.GetExitCodeProcess(self.process.hProcess, ctypes.byref(code)))
        return code.value

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.hProcess and self.kernel.WaitForSingleObject(self.process.hProcess, 0) != 0:
            self.kernel.TerminateProcess(self.process.hProcess, 99)
            self.kernel.WaitForSingleObject(self.process.hProcess, 2000)
        if self.hpc:
            self.kernel.ClosePseudoConsole(self.hpc)
            self.hpc = None
        if self.reader:
            self.reader.join(timeout=2)
        if self.attributes is not None:
            self.kernel.DeleteProcThreadAttributeList(self.attributes)
        for handle in reversed(self.handles):
            self.kernel.CloseHandle(handle)
        self.handles.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
