"""Native Windows console / POSIX TTY adapters with exception-safe restoration."""

from contextlib import AbstractContextManager
import os
from pathlib import Path
import shutil
import sys
import time

from .model import Tree
from .render import RenderOptions
from .state import Explorer, compose_screen

ENTER_SCREEN = "\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[2J\x1b[H"
LEAVE_SCREEN = "\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l"


class Terminal(AbstractContextManager):
    def __init__(self):
        self._restore = []
        self._buffer = ""

    def __enter__(self):
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.GetStdHandle.argtypes = [wintypes.DWORD]
                kernel.GetStdHandle.restype = wintypes.HANDLE
                kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                kernel.GetConsoleMode.restype = wintypes.BOOL
                kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel.SetConsoleMode.restype = wintypes.BOOL
                for handle_number, output in ((-11, True), (-10, False)):
                    handle = kernel.GetStdHandle(handle_number & 0xFFFFFFFF)
                    previous = wintypes.DWORD()
                    if not kernel.GetConsoleMode(handle, ctypes.byref(previous)):
                        raise OSError("could not read console mode; use Windows Terminal")
                    # Raw console keys: disabling processed input delivers Ctrl+C
                    # as a character to getwch instead of losing it in a ConPTY.
                    # VT input is off because getwch uses native arrow scan codes.
                    mode = previous.value | 0x0004 if output else (previous.value | 0x0080) & ~(0x0001 | 0x0002 | 0x0004 | 0x0040 | 0x0200)
                    if not kernel.SetConsoleMode(handle, mode):
                        raise OSError("could not enable terminal input/output")
                    self._restore.append(lambda h=handle, m=previous.value: kernel.SetConsoleMode(h, m))
            else:
                import termios
                import tty
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                self._restore.append(lambda: termios.tcsetattr(fd, termios.TCSADRAIN, old))
                tty.setcbreak(fd)
            sys.stdout.write(ENTER_SCREEN)
            sys.stdout.flush()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        try:
            sys.stdout.write(LEAVE_SCREEN)
            sys.stdout.flush()
        finally:
            for restore in reversed(self._restore):
                restore()
            self._restore.clear()
        return False

    def read_key(self, timeout: float = 0.025) -> str | None:
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + timeout
            while not msvcrt.kbhit():
                if time.monotonic() >= deadline:
                    return None
                time.sleep(0.005)
            char = msvcrt.getwch()
            if char in ("\x00", "\xe0"):
                return {"K": "left", "M": "right", "H": "up", "P": "down"}.get(msvcrt.getwch())
            return {"\x1b": "escape", "\x03": "ctrl-c"}.get(char, char)
        import select
        if not self._buffer:
            if not select.select([sys.stdin], [], [], timeout)[0]:
                return None
            self._buffer = os.read(sys.stdin.fileno(), 64).decode("ascii", errors="ignore")
            if not self._buffer:
                return "q"  # Input EOF: leave, never spin forever.
        # An escape byte can arrive before the rest of an arrow sequence.
        if self._buffer.startswith("\x1b"):
            deadline = time.monotonic() + 0.035
            while len(self._buffer) < 3 and select.select([sys.stdin], [], [], max(0, deadline - time.monotonic()))[0]:
                chunk = os.read(sys.stdin.fileno(), 16)
                if not chunk:
                    break
                self._buffer += chunk.decode("ascii", errors="ignore")
            for prefix in ("\x1b[", "\x1bO"):
                if self._buffer.startswith(prefix) and len(self._buffer) >= 3:
                    key = {"A": "up", "B": "down", "C": "right", "D": "left"}.get(self._buffer[2])
                    self._buffer = self._buffer[3:]
                    return key
            self._buffer = self._buffer[1:]
            return "escape"
        char, self._buffer = self._buffer[0], self._buffer[1:]
        return {"\x03": "ctrl-c"}.get(char, char)

    def draw(self, rows: list[str]) -> None:
        # Absolute cursor positioning avoids both linefeed spam and bottom-row scroll.
        payload = "".join(f"\x1b[{index + 1};1H{line}" for index, line in enumerate(rows))
        sys.stdout.write(payload)
        sys.stdout.flush()


def run(tree: Tree, options: RenderOptions, export_dir: Path,
        *, terminal_factory=Terminal, size_provider=shutil.get_terminal_size,
        clock=time.monotonic, max_frames: int | None = None) -> int:
    """Run at most 12 FPS; injection points permit finite non-console lifecycle tests."""
    explorer = Explorer(tree, options)
    last_time = clock()
    next_frame = last_time
    last_size = None
    dirty = True
    frame = ""
    frames = 0
    exit_code = 0
    try:
        with terminal_factory() as terminal:
            while not explorer.quit:
                key = terminal.read_key(0.025)
                if key:
                    dirty = explorer.key(key) or dirty
                    if key == "ctrl-c":
                        exit_code = 130
                if explorer.quit:
                    break
                now = clock()
                size = size_provider()
                if size != last_size:
                    dirty = True
                    last_size = size
                if now >= next_frame:
                    dirty = explorer.advance(now - last_time) or dirty
                    last_time = now
                    next_frame = now + 1 / 12
                    if dirty:
                        rows, frame = compose_screen(explorer, size.columns, size.lines)
                        terminal.draw(rows)
                        frames += 1
                        dirty = False
                        if max_frames is not None and frames >= max_frames:
                            break
                if explorer.export_requested:
                    try:
                        # Generate current options at current size even if between ticks.
                        _, frame = compose_screen(explorer, size.columns, size.lines)
                        path = explorer.export(export_dir, frame)
                        explorer.message = f"Saved {path}"
                    except OSError as error:
                        explorer.message = f"Export failed: {error}"
                    explorer.export_requested = False
                    dirty = True
        return exit_code
    except KeyboardInterrupt:
        return 130
