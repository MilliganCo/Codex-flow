"""Native Windows / POSIX console I/O, with no third-party dependencies."""

from __future__ import annotations

import os
import shutil
import sys
import time
from typing import Callable

from .app import Explorer


class TerminalError(RuntimeError):
    pass


class WindowsInput:
    """Read console events without blocking or relying on CRT Ctrl+C behavior."""

    def __init__(self, kernel, handle):
        import ctypes
        from ctypes import wintypes

        class Character(ctypes.Union):
            _fields_ = [("UnicodeChar", ctypes.c_wchar), ("AsciiChar", ctypes.c_char)]

        class KeyEvent(ctypes.Structure):
            _fields_ = [("down", wintypes.BOOL), ("repeat", wintypes.WORD),
                        ("virtual_key", wintypes.WORD), ("scan", wintypes.WORD),
                        ("char", Character), ("control", wintypes.DWORD)]

        class Event(ctypes.Union):
            _fields_ = [("key", KeyEvent), ("padding", wintypes.BYTE * 16)]

        class InputRecord(ctypes.Structure):
            _fields_ = [("kind", wintypes.WORD), ("event", Event)]

        self.kernel, self.handle, self.record_type = kernel, handle, InputRecord
        kernel.GetNumberOfConsoleInputEvents.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.ReadConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.POINTER(InputRecord),
                                           wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]

    @staticmethod
    def decode(char: str, virtual_key: int, control: int = 0, down: bool = True) -> str | None:
        if not down:
            return None
        if char == "\x03" or (virtual_key == 0x43 and control & 0x000C):
            return "ctrl+c"
        if virtual_key in (0x25, 0x26, 0x27, 0x28, 0x1B):
            return {0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down", 0x1B: "esc"}[virtual_key]
        return char if char and char != "\x00" else None

    def poll(self) -> list[str]:
        import ctypes
        from ctypes import wintypes
        count, read = wintypes.DWORD(), wintypes.DWORD()
        if not self.kernel.GetNumberOfConsoleInputEvents(self.handle, ctypes.byref(count)):
            raise TerminalError("Cannot poll console input")
        if not count.value:
            return []
        records = (self.record_type * min(count.value, 64))()
        if not self.kernel.ReadConsoleInputW(self.handle, records, len(records), ctypes.byref(read)):
            raise TerminalError("Cannot read console input")
        keys = []
        for record in records[:read.value]:
            if record.kind == 1:  # KEY_EVENT; window/mouse/focus events are harmless.
                event = record.event.key
                key = self.decode(event.char.UnicodeChar, event.virtual_key, event.control, event.down)
                if key is not None:
                    keys.extend([key] * max(1, min(10, event.repeat)))
        return keys


class PosixKeyDecoder:
    def __init__(self) -> None:
        self.buffer = ""
        self.escape_since: float | None = None

    def feed(self, data: str, now: float) -> list[str]:
        self.buffer += data
        keys: list[str] = []
        while self.buffer:
            if self.buffer[0] != "\x1b":
                char, self.buffer = self.buffer[0], self.buffer[1:]
                keys.append("ctrl+c" if char == "\x03" else char)
                continue
            if self.escape_since is None:
                self.escape_since = now
            if self.buffer in ("\x1b", "\x1b[", "\x1bO") and now - self.escape_since < 0.04:
                break
            if len(self.buffer) >= 3 and self.buffer[1] in ("[", "O"):
                # Consume an entire CSI sequence, so Delete/Home digits never switch modes.
                end = 2
                while end < len(self.buffer) and not ("@" <= self.buffer[end] <= "~"):
                    end += 1
                if end == len(self.buffer) and now - self.escape_since < 0.04:
                    break
                if end < len(self.buffer):
                    token = self.buffer[end]
                    if token in "ABCD":
                        keys.append({"A": "up", "B": "down", "C": "right", "D": "left"}[token])
                    self.buffer = self.buffer[end + 1:]
                else:
                    self.buffer = ""
            else:
                keys.append("esc")
                self.buffer = self.buffer[1:]
            self.escape_since = None
        return keys


class Terminal:
    def __init__(self) -> None:
        self.windows_input = None
        self.posix_decoder = PosixKeyDecoder()
        self.original_output_mode = None
        self.original_console_input_mode = None
        self.original_input = None
        self.entered = False

    def __enter__(self) -> Terminal:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise TerminalError("Interactive view requires a TTY")
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.GetStdHandle.argtypes = [wintypes.DWORD]
                kernel.GetStdHandle.restype = wintypes.HANDLE
                kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                handle = kernel.GetStdHandle(-11 & 0xFFFFFFFF)
                mode = wintypes.DWORD()
                if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                    raise TerminalError("Cannot read console mode; try Windows Terminal or use render")
                if not kernel.SetConsoleMode(handle, mode.value | 0x0005):
                    raise TerminalError("Cannot enable ANSI output; use Windows Terminal or render")
                self.original_output_mode = kernel, handle, mode.value
                input_handle = kernel.GetStdHandle(-10 & 0xFFFFFFFF)
                input_mode = wintypes.DWORD()
                if not kernel.GetConsoleMode(input_handle, ctypes.byref(input_mode)):
                    raise TerminalError("Cannot read console input mode")
                # Deliver Ctrl+C as a key event. Disable echo, line buffering and quick edit.
                raw_mode = (input_mode.value & ~0x0247) | 0x0080
                if not kernel.SetConsoleMode(input_handle, raw_mode):
                    raise TerminalError("Cannot set console input mode")
                self.original_console_input_mode = kernel, input_handle, input_mode.value
                self.windows_input = WindowsInput(kernel, input_handle)
            else:
                import termios
                import tty
                self.original_input = termios.tcgetattr(sys.stdin.fileno())
                tty.setcbreak(sys.stdin.fileno())
            sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")
            sys.stdout.flush()
            self.entered = True
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(self, *args: object) -> None:
        try:
            if self.entered:
                sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
                sys.stdout.flush()
        finally:
            self.entered = False
            if self.original_output_mode is not None:
                kernel, handle, mode = self.original_output_mode
                kernel.SetConsoleMode(handle, mode)
                self.original_output_mode = None
            if self.original_console_input_mode is not None:
                kernel, handle, mode = self.original_console_input_mode
                kernel.SetConsoleMode(handle, mode)
                self.original_console_input_mode = None
                self.windows_input = None
            if self.original_input is not None:
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.original_input)
                self.original_input = None

    def size(self) -> tuple[int, int]:
        size = shutil.get_terminal_size((100, 40))
        return max(1, size.columns), max(1, size.lines)

    def poll_keys(self) -> list[str]:
        if os.name == "nt":
            return self.windows_input.poll() if self.windows_input is not None else []
        import select
        data = ""
        if select.select([sys.stdin], [], [], 0)[0]:
            raw = os.read(sys.stdin.fileno(), 256)
            if not raw:
                return ["q"]
            data = raw.decode("ascii", errors="ignore")
        return self.posix_decoder.feed(data, time.monotonic())

    def draw(self, lines: tuple[str, ...]) -> None:
        # Absolute cursor addressing avoids LF translation and bottom-right scrolling.
        output = "".join(f"\x1b[{i + 1};1H{line}\x1b[K" for i, line in enumerate(lines))
        sys.stdout.write(output + "\x1b[J")
        sys.stdout.flush()


def run_interactive(state: Explorer, terminal: Terminal | None = None, *, fps: int = 12,
                    clock: Callable[[], float] = time.monotonic,
                    sleep: Callable[[float], None] = time.sleep) -> int:
    if not 1 <= fps <= 30:
        raise ValueError("fps must be 1..30")
    terminal = terminal if terminal is not None else Terminal()
    try:
        with terminal:
            previous = clock()
            next_frame = previous
            previous_size = (0, 0)
            dirty = True
            while state.running:
                now = clock()
                dt, previous = min(0.25, max(0, now - previous)), now
                state.advance(dt)
                for key in terminal.poll_keys():
                    if key == "ctrl+c":
                        raise KeyboardInterrupt
                    dirty = state.handle_key(key) or dirty
                    if not state.running:
                        break
                if not state.running:
                    break
                size = terminal.size()
                dirty = dirty or size != previous_size
                if dirty or (state.playing and now >= next_frame):
                    terminal.draw(state.screen(*size))
                    previous_size, dirty, next_frame = size, False, now + 1 / fps
                sleep(0.008)
    except KeyboardInterrupt:
        state.running = False
        return 130
    return 0
