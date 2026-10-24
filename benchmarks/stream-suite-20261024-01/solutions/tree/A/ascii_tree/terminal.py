"""Small Windows/POSIX terminal backend. No curses, threads or dependencies."""

from contextlib import AbstractContextManager
from pathlib import Path
import os
import shutil
import sys
import time

from .app import Explorer

ENTER = "\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H"
LEAVE = "\x1b[0m\x1b[?25h\x1b[?1049l"
ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}


class Terminal(AbstractContextManager):
    def __init__(self):
        self.saved_mode = None
        self.saved_input_mode = None
        self.handle = None
        self.input_handle = None
        self.fd = None
        self.attrs = None
        self.entered = False
        self.pending = ""
        self.escape_started = None
        self.extended = False

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
                kernel.GetConsoleMode.restype = kernel.SetConsoleMode.restype = wintypes.BOOL
                self.kernel = kernel
                self.handle = kernel.GetStdHandle(-11)
                mode = wintypes.DWORD()
                if not kernel.GetConsoleMode(self.handle, ctypes.byref(mode)):
                    raise OSError("stdout is not a Windows console")
                self.saved_mode = mode.value
                # Disable wrap at the last column; restore the exact original mode.
                if not kernel.SetConsoleMode(self.handle, (mode.value | 4) & ~2):
                    raise OSError("console does not support ANSI/VT output; use Windows Terminal")
                self.input_handle = kernel.GetStdHandle(-10)
                if not kernel.GetConsoleMode(self.input_handle, ctypes.byref(mode)):
                    raise OSError("stdin is not a Windows console")
                self.saved_input_mode = mode.value
                # Read Ctrl+C as a key, too: some hosting shells inherit an
                # ignored console control handler. Do not depend on that handler.
                # Disable Quick Edit, line/echo, VT input and processed input.
                input_mode = (mode.value | 0x80) & ~(0x40 | 2 | 4 | 0x200 | 1)
                if not kernel.SetConsoleMode(self.input_handle, input_mode):
                    raise OSError("cannot configure keyboard input")
            else:
                import termios
                import tty
                self.fd = sys.stdin.fileno()
                self.attrs = termios.tcgetattr(self.fd)
                tty.setcbreak(self.fd)
            self.entered = True
            sys.stdout.write(ENTER)
            sys.stdout.flush()
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def __exit__(self, *exc):
        try:
            if self.entered:
                sys.stdout.write(LEAVE)
                sys.stdout.flush()
        finally:
            self.entered = False
            if os.name == "nt":
                if self.saved_mode is not None:
                    self.kernel.SetConsoleMode(self.handle, self.saved_mode)
                if self.saved_input_mode is not None:
                    self.kernel.SetConsoleMode(self.input_handle, self.saved_input_mode)
            elif self.attrs is not None:
                import termios
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.attrs)
        return False

    def read_keys(self) -> list[str]:
        if os.name == "nt":
            import msvcrt
            keys = []
            while msvcrt.kbhit() and len(keys) < 64:
                char = msvcrt.getwch()
                if self.extended:
                    keys.append({"H": "up", "P": "down", "K": "left", "M": "right"}.get(char, ""))
                    self.extended = False
                elif char in ("\x00", "\xe0"):
                    self.extended = True
                else:
                    keys.append("escape" if char == "\x1b" else char)
            return keys
        import select
        if select.select([self.fd], [], [], 0)[0]:
            data = os.read(self.fd, 128)
            if not data:
                return ["q"]
            self.pending += data.decode("ascii", errors="ignore")
        return self.decode_pending(time.monotonic())

    def decode_pending(self, now: float) -> list[str]:
        """Wait briefly for fragmented escape sequences; Esc alone still exits."""
        keys = []
        while self.pending:
            if self.pending[0] != "\x1b":
                keys.append(self.pending[0])
                self.pending = self.pending[1:]
                continue
            if self.escape_started is None:
                self.escape_started = now
            if len(self.pending) >= 3 and self.pending[1] in ("[", "O"):
                keys.append(ARROWS.get(self.pending[2], ""))
                self.pending = self.pending[3:]
                self.escape_started = None
            elif len(self.pending) >= 2 and self.pending[1] not in ("[", "O"):
                keys.append("escape")
                self.pending = self.pending[1:]
                self.escape_started = None
            elif now - self.escape_started >= 0.06:
                keys.append("escape")
                self.pending = self.pending[1:]
                self.escape_started = None
            else:
                break
        return keys

    @staticmethod
    def size() -> tuple[int, int]:
        try:
            size = os.get_terminal_size(sys.stdout.fileno())
        except (OSError, AttributeError, ValueError):
            size = shutil.get_terminal_size((100, 40))
        # Leave the physical last row/column alone to prevent scrolling.
        return max(1, min(500, size.columns - 1)), max(1, min(200, size.lines - 1))

    @staticmethod
    def draw(screen: str) -> None:
        sys.stdout.write("\x1b[H\x1b[J" + screen.replace("\n", "\r\n"))
        sys.stdout.flush()


def run(explorer: Explorer, export_dir: Path, *, terminal_factory=Terminal,
        clock=time.monotonic, sleeper=time.sleep) -> int:
    """Finite work per tick, capped at 12 FPS; input is polled at 50 Hz."""
    try:
        with terminal_factory() as terminal:
            previous = clock()
            last_draw = -1.0
            last_size = None
            dirty = True
            while not explorer.quitting:
                now = clock()
                dt, previous = now - previous, now
                for key in terminal.read_keys():
                    action = explorer.handle_key(key)
                    dirty = True
                    if action == "export":
                        try:
                            explorer.export(export_dir)
                        except OSError as error:
                            explorer.message = f"Export failed: {error.strerror or type(error).__name__}"
                    if explorer.quitting:
                        break
                if explorer.quitting:
                    break
                explorer.tick(dt)
                size = terminal.size()
                if size != last_size:
                    dirty = True
                if dirty or (explorer.playing and now - last_draw >= 1 / 12):
                    terminal.draw(explorer.screen(*size))
                    last_draw, last_size, dirty = now, size, False
                sleeper(0.02)
    except KeyboardInterrupt:
        return 0
    return 0
