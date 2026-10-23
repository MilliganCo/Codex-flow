"""Native Windows input / POSIX cbreak, with transactional console restoration."""

from __future__ import annotations

import os
import select
import shutil
import sys
import time
from typing import TextIO

from .app import Explorer

WINDOWS_KEYS = {0x25: "left", 0x27: "right", 0x26: "up", 0x28: "down", 0x1B: "escape"}
ANSI_KEYS = {"\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
             "\x1bOA": "up", "\x1bOB": "down", "\x1bOC": "right", "\x1bOD": "left"}


def windows_key(down: bool, virtual_key: int, char: str) -> str:
    # ConPTY synthesizes Alt+numpad for punctuation absent from the active layout.
    # Its completed Unicode character arrives on Alt release, not on key-down.
    composed = not down and virtual_key == 0x12 and char != "\x00"
    if not down and not composed:
        return ""
    key = WINDOWS_KEYS.get(virtual_key, char)
    if not key or key == "\x00":
        return ""
    return "ctrl+c" if key == "\x03" else key


class KeyDecoder:
    """Incremental VT decoder; fragmented arrows must not be mistaken for Esc."""

    def __init__(self) -> None:
        self.pending = ""
        self.since = 0.0

    def feed(self, data: str, now: float) -> list[str]:
        self.pending += data
        result: list[str] = []
        while self.pending:
            if not self.pending.startswith("\x1b"):
                c, self.pending = self.pending[0], self.pending[1:]
                result.append("ctrl+c" if c == "\x03" else c)
                continue
            match = next((s for s in ANSI_KEYS if self.pending.startswith(s)), None)
            if match:
                result.append(ANSI_KEYS[match])
                self.pending = self.pending[len(match):]
            elif any(s.startswith(self.pending) for s in ANSI_KEYS):
                if not self.since:
                    self.since = now
                break
            else:
                result.append("escape")
                self.pending = self.pending[1:]
        if not self.pending:
            self.since = 0.0
        return result

    def flush(self, now: float) -> list[str]:
        if self.pending and now - self.since >= 0.06:
            self.pending = ""
            self.since = 0.0
            return ["escape"]
        return []


class Terminal:
    def __init__(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.decoder = KeyDecoder()
        self._restore: list = []
        self._active = False
        self._windows_input = None

    def __enter__(self) -> Terminal:
        try:
            if os.name == "nt":
                self._setup_windows()
            else:
                import termios
                import tty
                fd = self.stdin.fileno()
                original = termios.tcgetattr(fd)
                self._restore.append(lambda: termios.tcsetattr(fd, termios.TCSADRAIN, original))
                tty.setcbreak(fd)
            self._active = True
            self.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")
            self.stdout.flush()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _setup_windows(self) -> None:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel.GetStdHandle.restype = wintypes.HANDLE
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        for identifier, output in ((-11, True), (-10, False)):
            handle = kernel.GetStdHandle(identifier & 0xffffffff)
            original = wintypes.DWORD()
            if not kernel.GetConsoleMode(handle, ctypes.byref(original)):
                raise OSError("interactive Windows console is required; use 'render' when redirected")
            self._restore.append(lambda h=handle, m=original.value: kernel.SetConsoleMode(h, m))
            # Read Ctrl+C as an input event as well: hosts can inherit an ignored
            # CTRL_C process handler. The app still exits through normal cleanup.
            mode = (original.value | 0x0004) if output else (
                original.value & ~(0x0001 | 0x0002 | 0x0004 | 0x0040 | 0x0200)
            ) | 0x0080
            if not kernel.SetConsoleMode(handle, mode):
                raise OSError("could not configure terminal console mode")
            if not output:
                self._windows_input = WindowsInput(kernel, handle)

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            if self._active:
                self.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
                self.stdout.flush()
        finally:
            self._active = False
            for restore in reversed(self._restore):
                restore()
            self._restore.clear()

    def size(self) -> tuple[int, int]:
        size = shutil.get_terminal_size(fallback=(100, 40))
        return max(1, size.columns), max(1, size.lines)

    def keys(self, timeout: float) -> list[str]:
        if os.name == "nt":
            end = time.monotonic() + timeout
            while True:
                result = self._windows_input.read()
                if result or time.monotonic() >= end:
                    return result
                time.sleep(min(0.005, max(0, end - time.monotonic())))
        ready, _, _ = select.select([self.stdin], [], [], timeout)
        data = os.read(self.stdin.fileno(), 128).decode("ascii", "ignore") if ready else ""
        if ready and not data:
            return ["q"]  # EOF / disconnected TTY
        return self.decoder.feed(data, time.monotonic()) + self.decoder.flush(time.monotonic())

    def draw(self, screen: str, resized: bool = False) -> None:
        self.stdout.write(("\x1b[2J" if resized else "") + "\x1b[H" + screen.replace("\n", "\r\n"))
        self.stdout.flush()


class WindowsInput:
    """Read Unicode key events directly, including keys with no scan-code mapping.

    `msvcrt.getwch` can drop OEM punctuation in a pseudoconsole and its second
    extended-key code can remain pending even while `kbhit` is false.
    """

    def __init__(self, kernel, handle) -> None:
        import ctypes
        from ctypes import wintypes

        class KeyEvent(ctypes.Structure):
            _fields_ = [("down", wintypes.BOOL), ("repeat", wintypes.WORD),
                        ("virtual_key", wintypes.WORD), ("scan", wintypes.WORD),
                        ("char", wintypes.WCHAR), ("control", wintypes.DWORD)]

        class Event(ctypes.Union):
            _fields_ = [("key", KeyEvent), ("padding", ctypes.c_byte * 16)]

        class InputRecord(ctypes.Structure):
            _fields_ = [("kind", wintypes.WORD), ("event", Event)]

        self.kernel, self.handle, self.record_type = kernel, handle, InputRecord
        kernel.GetNumberOfConsoleInputEvents.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.ReadConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.POINTER(InputRecord),
                                            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]

    def read(self) -> list[str]:
        import ctypes
        from ctypes import wintypes
        count = wintypes.DWORD()
        if not self.kernel.GetNumberOfConsoleInputEvents(self.handle, ctypes.byref(count)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not count.value:
            return []
        records = (self.record_type * min(count.value, 128))()
        if not self.kernel.ReadConsoleInputW(self.handle, records, len(records), ctypes.byref(count)):
            raise ctypes.WinError(ctypes.get_last_error())
        keys = []
        for record in records[:count.value]:
            if record.kind != 1:
                continue
            event = record.event.key
            key = windows_key(event.down, event.virtual_key, event.char)
            if key:
                keys.extend([key] * min(event.repeat, 32))
        return keys


def run_interactive(explorer: Explorer, terminal: Terminal | None = None) -> int:
    console = terminal or Terminal()
    try:
        with console:
            previous = time.monotonic()
            old_size = None
            dirty = True
            while explorer.running:
                now = time.monotonic()
                elapsed, previous = now - previous, now
                explorer.tick(elapsed)
                size = console.size()
                animating = explorer.animated and not explorer.help_open and explorer.options.mode != "2d"
                if dirty or animating or size != old_size:
                    console.draw(explorer.screen(*size), resized=size != old_size)
                    old_size, dirty = size, False
                # 15fps maximum: include rendering time in the frame budget.
                timeout = max(0.0, 1 / 15 - (time.monotonic() - now)) if animating else 0.08
                for key in console.keys(timeout):
                    dirty = explorer.handle(key) or dirty
    except KeyboardInterrupt:
        return 0
    return 0
