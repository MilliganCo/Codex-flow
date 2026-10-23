"""Small Windows/POSIX console adapter, with restoration on every exit path."""

from __future__ import annotations

import os
import select
import shutil
import sys
import time

from .app import ExplorerState, compose_screen, image_size

ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}


class Terminal:
    def __init__(self, stdin=None, stdout=None):
        self.stdin = sys.stdin if stdin is None else stdin
        self.stdout = sys.stdout if stdout is None else stdout
        self.saved = None
        self.win_mode = None
        self.win_input_mode = None

    def __enter__(self):
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
                    raise OSError("stdout is not a Windows console; use render for redirected output")
                self.win_mode = kernel, handle, mode.value
                if not kernel.SetConsoleMode(handle, mode.value | 0x0004):
                    raise OSError("cannot enable Windows virtual terminal output")
                input_handle = kernel.GetStdHandle(-10 & 0xFFFFFFFF)
                input_mode = wintypes.DWORD()
                if not kernel.GetConsoleMode(input_handle, ctypes.byref(input_mode)):
                    raise OSError("stdin is not a Windows console")
                self.win_input_mode = kernel, input_handle, input_mode.value
                # Read Ctrl+C as a key; disable line/echo and Quick Edit freezes.
                raw_mode = (input_mode.value | 0x0080) & ~(0x0001 | 0x0002 | 0x0004 | 0x0040)
                if not kernel.SetConsoleMode(input_handle, raw_mode):
                    raise OSError("cannot enable Windows console key input")
            else:
                import termios
                import tty
                self.saved = termios.tcgetattr(self.stdin.fileno())
                tty.setcbreak(self.stdin.fileno())
            self.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")
            self.stdout.flush()
        except BaseException:
            self._restore()
            raise
        return self

    def _restore(self):
        if self.saved is not None:
            import termios
            termios.tcsetattr(self.stdin.fileno(), termios.TCSADRAIN, self.saved)
            self.saved = None
        for attribute in ("win_input_mode", "win_mode"):
            saved_mode = getattr(self, attribute)
            if saved_mode is not None:
                kernel, handle, mode = saved_mode
                kernel.SetConsoleMode(handle, mode)
                setattr(self, attribute, None)

    def __exit__(self, *args):
        try:
            self.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            self.stdout.flush()
        finally:
            self._restore()

    def size(self) -> tuple[int, int]:
        size = shutil.get_terminal_size(fallback=(100, 40))
        return max(1, size.columns), max(1, size.lines)

    def draw(self, lines: tuple[str, ...]) -> None:
        # Clear each row; write at home, without a final newline that could scroll.
        self.stdout.write("\x1b[H" + "\r\n".join("\x1b[2K" + row for row in lines))
        self.stdout.flush()

    def read_key(self, timeout: float) -> str | None:
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + timeout
            while not msvcrt.kbhit():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                time.sleep(min(0.01, remaining))
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(msvcrt.getwch())
        else:
            if not select.select([self.stdin], [], [], timeout)[0]:
                return None
            key = os.read(self.stdin.fileno(), 1).decode("ascii", errors="replace")
            if not key:
                return "q"
            if key == "\x1b" and select.select([self.stdin], [], [], 0.035)[0]:
                sequence = os.read(self.stdin.fileno(), 1)
                if sequence in (b"[", b"O") and select.select([self.stdin], [], [], 0.035)[0]:
                    return ARROWS.get(os.read(self.stdin.fileno(), 1).decode("ascii", errors="replace"))
                return None
        return {"\x1b": "escape", "\x03": "ctrl-c"}.get(key, key)


def run_interactive(state: ExplorerState, terminal_factory=Terminal, clock=time.monotonic) -> int:
    """No frame stream: one alternate screen, redrawn on changes at <=10 FPS."""
    try:
        with terminal_factory() as terminal:
            previous = clock()
            last_draw = previous - 1
            last_size = None
            dirty = True
            while not state.quit:
                now = clock()
                dirty = state.tick(now - previous) or dirty
                previous = now
                size = terminal.size()
                dirty = dirty or size != last_size
                if dirty and now - last_draw >= 0.1:
                    terminal.draw(compose_screen(state, *size))
                    last_draw, last_size, dirty = now, size, False
                key = terminal.read_key(0.025)
                if key is not None:
                    dirty = state.handle_key(key, *image_size(*size)) or dirty
                    if key == "ctrl-c":
                        return 130
    except KeyboardInterrupt:
        return 130
    return 0
