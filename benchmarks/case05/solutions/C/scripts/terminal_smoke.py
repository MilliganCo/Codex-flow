"""Real Windows ConPTY integration check; no visible window or external tools.

python scripts/terminal_smoke.py --record artifacts/interactive-demo.txt
All waits are bounded. This is a test harness, not part of the application.
"""

from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


class Coord(C.Structure):
    _fields_ = [("X", C.c_short), ("Y", C.c_short)]


class StartupInfo(C.Structure):
    _fields_ = [("cb", W.DWORD), ("lpReserved", W.LPWSTR), ("lpDesktop", W.LPWSTR),
                ("lpTitle", W.LPWSTR), ("dwX", W.DWORD), ("dwY", W.DWORD),
                ("dwXSize", W.DWORD), ("dwYSize", W.DWORD), ("dwXCountChars", W.DWORD),
                ("dwYCountChars", W.DWORD), ("dwFillAttribute", W.DWORD), ("dwFlags", W.DWORD),
                ("wShowWindow", W.WORD), ("cbReserved2", W.WORD), ("lpReserved2", C.POINTER(W.BYTE)),
                ("hStdInput", W.HANDLE), ("hStdOutput", W.HANDLE), ("hStdError", W.HANDLE)]


class StartupInfoEx(C.Structure):
    _fields_ = [("StartupInfo", StartupInfo), ("lpAttributeList", C.c_void_p)]


class ProcessInfo(C.Structure):
    _fields_ = [("hProcess", W.HANDLE), ("hThread", W.HANDLE),
                ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD)]


class Screen:
    """Small VT screen reader for the cursor/erase operations ConPTY emits."""
    def __init__(self, width, height):
        self.resize(width, height)
        self.pending = ""
        self.x = self.y = 0

    def resize(self, width, height):
        self.width, self.height = width, height
        self.cells = [[" "] * width for _ in range(height)]
        self.x = self.y = 0

    def feed(self, data):
        self.pending += data.decode("utf-8", errors="replace")
        while self.pending:
            if self.pending.startswith("\x1b["):
                end = 2
                while end < len(self.pending) and not ("@" <= self.pending[end] <= "~"):
                    end += 1
                if end == len(self.pending):
                    return
                raw, command = self.pending[2:end], self.pending[end]
                self.pending = self.pending[end + 1:]
                numbers = [int(v) if v.isdigit() else 0 for v in raw.lstrip("?=>").split(";")]
                n = numbers[0] or 1
                if command in "Hf":
                    self.y = min(self.height - 1, max(0, n - 1))
                    self.x = min(self.width - 1, max(0, (numbers[1] if len(numbers) > 1 else 1) - 1))
                elif command == "A":
                    self.y = max(0, self.y - n)
                elif command == "B":
                    self.y = min(self.height - 1, self.y + n)
                elif command == "C":
                    self.x = min(self.width - 1, self.x + n)
                elif command == "D":
                    self.x = max(0, self.x - n)
                elif command == "G":
                    self.x = min(self.width - 1, n - 1)
                elif command == "d":
                    self.y = min(self.height - 1, n - 1)
                elif command == "K":
                    mode = numbers[0]
                    for x in range(self.width):
                        if mode == 2 or (mode == 0 and x >= self.x) or (mode == 1 and x <= self.x):
                            self.cells[self.y][x] = " "
                elif command == "J":
                    mode = numbers[0]
                    for y in range(self.height):
                        for x in range(self.width):
                            if mode in (2, 3) or (mode == 0 and (y, x) >= (self.y, self.x)):
                                self.cells[y][x] = " "
                elif command == "X":
                    for x in range(self.x, min(self.width, self.x + n)):
                        self.cells[self.y][x] = " "
                continue
            if self.pending.startswith("\x1b]"):
                end = self.pending.find("\x07")
                terminator = 1
                if end < 0:
                    end = self.pending.find("\x1b\\")
                    terminator = 2
                if end < 0:
                    return
                self.pending = self.pending[end + terminator:]
                continue
            if self.pending[0] == "\x1b":
                if len(self.pending) < 2:
                    return
                length = 3 if self.pending[1] in "()" else 2
                if len(self.pending) < length:
                    return
                self.pending = self.pending[length:]
                continue
            char, self.pending = self.pending[0], self.pending[1:]
            if char == "\r":
                self.x = 0
            elif char == "\n":
                self.y = min(self.height - 1, self.y + 1)
            elif char == "\b":
                self.x = max(0, self.x - 1)
            elif " " <= char <= "~":
                self.cells[self.y][min(self.width - 1, self.x)] = char
                self.x = min(self.width - 1, self.x + 1)

    def text(self):
        return "\n".join("".join(row) for row in self.cells)


class PseudoConsole:
    def __init__(self, export_dir):
        self.k = C.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreatePipe": ([C.POINTER(W.HANDLE), C.POINTER(W.HANDLE), C.c_void_p, W.DWORD], W.BOOL),
            "CreatePseudoConsole": ([Coord, W.HANDLE, W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)], C.c_long),
            "ResizePseudoConsole": ([W.HANDLE, Coord], C.c_long),
            "ClosePseudoConsole": ([W.HANDLE], None),
            "CloseHandle": ([W.HANDLE], W.BOOL),
            "InitializeProcThreadAttributeList": ([C.c_void_p, W.DWORD, W.DWORD, C.POINTER(C.c_size_t)], W.BOOL),
            "UpdateProcThreadAttribute": ([C.c_void_p, W.DWORD, C.c_size_t, C.c_void_p, C.c_size_t, C.c_void_p, C.c_void_p], W.BOOL),
            "DeleteProcThreadAttributeList": ([C.c_void_p], None),
            "CreateProcessW": ([W.LPCWSTR, W.LPWSTR, C.c_void_p, C.c_void_p, W.BOOL, W.DWORD,
                                C.c_void_p, W.LPCWSTR, C.POINTER(StartupInfo), C.POINTER(ProcessInfo)], W.BOOL),
            "PeekNamedPipe": ([W.HANDLE, C.c_void_p, W.DWORD, C.c_void_p, C.POINTER(W.DWORD), C.c_void_p], W.BOOL),
            "ReadFile": ([W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p], W.BOOL),
            "WriteFile": ([W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p], W.BOOL),
            "GetExitCodeProcess": ([W.HANDLE, C.POINTER(W.DWORD)], W.BOOL),
            "TerminateProcess": ([W.HANDLE, W.UINT], W.BOOL),
            "WaitForSingleObject": ([W.HANDLE, W.DWORD], W.DWORD),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.k, name)
            function.argtypes, function.restype = args, result
        self.handles = []
        self.hpc = W.HANDLE()
        self.process = ProcessInfo()
        self.attributes = None
        self.screen = Screen(100, 40)
        self.transcript = bytearray()
        self.export_dir = export_dir

    @staticmethod
    def check(ok):
        if not ok:
            raise C.WinError(C.get_last_error())

    def __enter__(self):
        try:
            input_read, self.input_write = W.HANDLE(), W.HANDLE()
            self.output_read, output_write = W.HANDLE(), W.HANDLE()
            self.check(self.k.CreatePipe(C.byref(input_read), C.byref(self.input_write), None, 0))
            self.handles.extend((input_read, self.input_write))
            self.check(self.k.CreatePipe(C.byref(self.output_read), C.byref(output_write), None, 0))
            self.handles.extend((self.output_read, output_write))
            result = self.k.CreatePseudoConsole(Coord(100, 40), input_read, output_write, 0, C.byref(self.hpc))
            if result != 0:
                raise RuntimeError(f"CreatePseudoConsole HRESULT {result:#x}")
            size = C.c_size_t()
            self.k.InitializeProcThreadAttributeList(None, 1, 0, C.byref(size))
            self.attributes = C.create_string_buffer(size.value)
            self.check(self.k.InitializeProcThreadAttributeList(self.attributes, 1, 0, C.byref(size)))
            self.check(self.k.UpdateProcThreadAttribute(self.attributes, 0, 0x00020016,
                                                       self.hpc, C.sizeof(W.HANDLE), None, None))
            startup = StartupInfoEx()
            startup.StartupInfo.cb = C.sizeof(startup)
            startup.lpAttributeList = C.cast(self.attributes, C.c_void_p)
            command = C.create_unicode_buffer(subprocess.list2cmdline([
                sys.executable, str(ROOT / "scripts" / "terminal_smoke.py"), "--child", str(self.export_dir)]))
            self.check(self.k.CreateProcessW(None, command, None, None, False, 0x00080000, None,
                                             str(ROOT), C.byref(startup.StartupInfo), C.byref(self.process)))
            self.handles.extend((self.process.hThread, self.process.hProcess))
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def pump(self):
        available, read = W.DWORD(), W.DWORD()
        if self.k.PeekNamedPipe(self.output_read, None, 0, None, C.byref(available), None) and available.value:
            buffer = C.create_string_buffer(min(available.value, 65536))
            self.check(self.k.ReadFile(self.output_read, buffer, len(buffer), C.byref(read), None))
            data = buffer.raw[:read.value]
            self.transcript.extend(data)
            self.screen.feed(data)

    def send(self, keys):
        data = keys.encode("ascii")
        written = W.DWORD()
        self.check(self.k.WriteFile(self.input_write, data, len(data), C.byref(written), None))
        if written.value != len(data):
            raise RuntimeError("Short pseudo-console input write")

    def wait(self, predicate, description, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.pump()
            if predicate():
                return
            code = W.DWORD()
            self.k.GetExitCodeProcess(self.process.hProcess, C.byref(code))
            if code.value != 259:
                raise RuntimeError(f"Exited {code.value} while waiting for {description}\n{self.screen.text()}")
            time.sleep(0.015)
        raise RuntimeError(f"Timeout: {description}\n{self.screen.text()}")

    def contains(self, text):
        self.wait(lambda: text in self.screen.text(), repr(text))

    def resize(self, width, height):
        result = self.k.ResizePseudoConsole(self.hpc, Coord(width, height))
        if result != 0:
            raise RuntimeError(f"ResizePseudoConsole HRESULT {result:#x}")
        self.screen.resize(width, height)

    def finish(self, key, expected):
        self.send(key)
        deadline = time.monotonic() + 5
        code = W.DWORD(259)
        while time.monotonic() < deadline:
            self.pump()
            self.k.GetExitCodeProcess(self.process.hProcess, C.byref(code))
            if code.value != 259:
                break
            time.sleep(0.015)
        self.pump()
        if code.value != expected:
            raise RuntimeError(f"Expected exit {expected}, got {code.value}")
        if b"\x1b[?25h" not in self.transcript:
            raise RuntimeError("No cursor restoration in terminal output")

    def __exit__(self, *args):
        if self.process.hProcess:
            code = W.DWORD()
            self.k.GetExitCodeProcess(self.process.hProcess, C.byref(code))
            if code.value == 259:
                self.k.TerminateProcess(self.process.hProcess, 1)
                self.k.WaitForSingleObject(self.process.hProcess, 1000)
        if self.hpc:
            self.k.ClosePseudoConsole(self.hpc)
            self.hpc = W.HANDLE()
        if self.attributes is not None:
            self.k.DeleteProcThreadAttributeList(self.attributes)
        for handle in reversed(self.handles):
            self.k.CloseHandle(handle)
        self.handles.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--child", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.name != "nt":
        print("NOT RUN: this integration smoke requires Windows ConPTY", file=sys.stderr)
        return 2
    if args.child:
        # Redirected runners can supply inherited pipe handles even inside ConPTY.
        # Reopen the attached console explicitly; the application itself is unchanged.
        import msvcrt
        sys.stdin = open("CONIN$", "r", encoding="utf-8")
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout
        sys.__stdin__, sys.__stdout__, sys.__stderr__ = sys.stdin, sys.stdout, sys.stderr
        kernel = C.WinDLL("kernel32", use_last_error=True)
        kernel.SetStdHandle.argtypes = [W.DWORD, W.HANDLE]
        for number, stream in ((-10, sys.stdin), (-11, sys.stdout), (-12, sys.stderr)):
            if not kernel.SetStdHandle(number & 0xFFFFFFFF, msvcrt.get_osfhandle(stream.fileno())):
                raise C.WinError(C.get_last_error())
        sys.path.insert(0, str(ROOT))
        from ascii_tree.cli import main as application
        return application(["view", "--seed", "42", "--export-dir", str(args.child)])
    (ROOT / ".tmp").mkdir(exist_ok=True)
    snapshots = []
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
        export_dir = Path(directory)
        with PseudoConsole(export_dir) as pty:
            pty.contains("ASCII TREE EXPLORER")
            snapshots.append("START / 3D / seed 42\n" + pty.screen.text())
            for key, mode in (("1", "2D"), ("2", "3D"), ("3", "4D")):
                pty.send(key)
                pty.contains(f"/  {mode}  /")
                pty.send("e")
                pty.wait(lambda m=mode: bool(list(export_dir.glob(f"tree-42-{m.lower()}-*.txt"))), f"{mode} export")
                pty.contains("Saved")
                snapshots.append(f"MODE {mode} / same seed 42\n" + pty.screen.text())
            pty.send("\x1b[C\x1b[A]")
            pty.contains("35.5")
            pty.contains("-3.0")
            pty.contains("7.5")
            pty.send(" ")
            pty.contains("PLAYING")
            pty.wait(lambda: (match := re.search(r"XW\s+([\d.]+).*zoom", pty.screen.text()))
                     and float(match[1]) > 7.5, "animated XW change")
            pty.send(" ")
            pty.contains("PAUSED")
            snapshots.append("4D / camera + XW rotation / after animation\n" + pty.screen.text())
            pty.send("g")
            pty.contains("SEED 43")
            pty.send("r+")
            pty.contains("1.12x")
            pty.contains("28.0")
            pty.send("-")
            pty.contains("1.00x")
            pty.send("h")
            pty.contains("WHAT IS 4D?")
            snapshots.append("HELP\n" + pty.screen.text())
            pty.send("?")
            pty.wait(lambda: "WHAT IS 4D?" not in pty.screen.text(), "help closed")
            pty.resize(18, 6)
            pty.contains("4D seed=43")
            snapshots.append("RESIZE / 18x6\n" + pty.screen.text())
            pty.resize(1, 1)
            # A 1x1 terminal scrolls its sole printable cell away. Test survival,
            # then recovery; a stable visible glyph at this size is not a valid assertion.
            tiny_deadline = time.monotonic() + 0.15
            pty.wait(lambda: time.monotonic() >= tiny_deadline, "survival at 1x1")
            pty.resize(100, 40)
            pty.contains("ASCII TREE EXPLORER")
            pty.send("e")
            pty.wait(lambda: bool(list(export_dir.glob("tree-43-4d-*.txt"))), "new seed export")
            for path in export_dir.glob("*.txt"):
                data = path.read_bytes()
                if len(data.splitlines()) != 33 or {len(row) for row in data.splitlines()} != {99}:
                    raise RuntimeError(f"Interactive export dimensions: {path.name}")
                if not all(v == 10 or 32 <= v <= 126 for v in data):
                    raise RuntimeError(f"Non-ASCII/control codes: {path.name}")
            pty.finish("q", 0)
        for key, code in (("\x1b", 0), ("\x03", 130)):
            with PseudoConsole(export_dir) as pty:
                pty.contains("ASCII TREE EXPLORER")
                pty.finish(key, code)
    if args.record:
        args.record.write_bytes(("\n\n".join(snapshots) + "\n").encode("ascii"))
    print("PASS: real Windows ConPTY startup, modes, arrows, XW, animation, seeds, help, zoom, export, resize 100x40/18x6/1x1, Q/Esc/Ctrl+C exits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
