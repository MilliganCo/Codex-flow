"""Small native terminal adapter: msvcrt on Windows, termios/select on POSIX."""

from collections import deque
import os
import shutil
import sys
import time


class KeyDecoder:
    """Incremental VT input parser; a lone Esc expires after 45 ms."""
    SEQUENCES = {f"\x1b{prefix}{suffix}": key
                 for prefix in ("[", "O")
                 for suffix, key in zip("ABCD", ("up", "down", "right", "left"))}

    def __init__(self):
        self.pending = ""
        self.since = 0.0
        self.keys = deque()

    def feed(self, text: str, now: float) -> None:
        if not self.pending:
            self.since = now
        self.pending += text
        self._parse(now)

    def _parse(self, now: float) -> None:
        while self.pending:
            for sequence, key in self.SEQUENCES.items():
                if self.pending.startswith(sequence):
                    self.keys.append(key)
                    self.pending = self.pending[len(sequence):]
                    break
            else:
                if (any(sequence.startswith(self.pending) for sequence in self.SEQUENCES)
                        and now - self.since < 0.045):
                    return
                first, self.pending = self.pending[0], self.pending[1:]
                self.keys.append("escape" if first == "\x1b" else first)

    def pop(self, now: float) -> str | None:
        self._parse(now)
        return self.keys.popleft() if self.keys else None


class Terminal:
    ENTER = "\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[2J"
    LEAVE = "\x1b[?7h\x1b[?25h\x1b[?1049l"

    def __init__(self, stdin=None, stdout=None):
        self.stdin = stdin if stdin is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout
        self.decoder = KeyDecoder()
        self.previous = ()
        self.saved_input = None
        self.saved_output = None
        self.active_output = None

    def _enable(self) -> None:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            import msvcrt
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.GetConsoleMode.restype = wintypes.BOOL
            kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.SetConsoleMode.restype = wintypes.BOOL
            handle = msvcrt.get_osfhandle(self.stdout.fileno())
            mode = wintypes.DWORD()
            if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                raise OSError("stdout is not a Windows console; use render")
            self.saved_output = (kernel, handle, mode.value)
            if not kernel.SetConsoleMode(handle, mode.value | 0x0004):
                raise OSError("cannot enable terminal escape sequences")
        else:
            import termios
            import tty
            self.saved_input = termios.tcgetattr(self.stdin.fileno())
            tty.setcbreak(self.stdin.fileno())

    def _restore(self) -> None:
        if self.active_output is not None:
            self.active_output.close()
            self.active_output = None
        if self.saved_input is not None:
            import termios
            termios.tcsetattr(self.stdin.fileno(), termios.TCSADRAIN, self.saved_input)
            self.saved_input = None
        if self.saved_output is not None:
            kernel, handle, mode = self.saved_output
            kernel.SetConsoleMode(handle, mode)
            self.saved_output = None

    def __enter__(self):
        try:
            self._enable()
            self.stdout.write(self.ENTER)
            self.stdout.flush()
            if self.saved_output is not None:
                # The original Windows handle can still refer to the inactive
                # main buffer after VT enters the alternate screen.
                self.active_output = open("CONOUT$", "w", encoding="ascii")
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.stdout.write(self.LEAVE)
            self.stdout.flush()
        finally:
            self._restore()
        return False

    def size(self) -> tuple[int, int]:
        try:
            output = self.active_output if self.active_output is not None else self.stdout
            size = os.get_terminal_size(output.fileno())
        except (OSError, ValueError):
            size = shutil.get_terminal_size((100, 40))
        return max(1, min(500, size.columns)), max(1, min(240, size.lines))

    def draw(self, rows: tuple[str, ...]) -> None:
        parts = []
        if len(rows) != len(self.previous) or (rows and self.previous and len(rows[0]) != len(self.previous[0])):
            parts.append("\x1b[2J")
            self.previous = ()
        for row, text in enumerate(rows):
            if row >= len(self.previous) or text != self.previous[row]:
                parts.append(f"\x1b[{row + 1};1H{text}")
        if parts:
            self.stdout.write("".join(parts))
            self.stdout.flush()
        self.previous = rows

    def read_key(self, timeout: float) -> str | None:
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + timeout
            while True:
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key in ("\x00", "\xe0"):
                        return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(msvcrt.getwch())
                    return "escape" if key == "\x1b" else key
                if time.monotonic() >= deadline:
                    return None
                time.sleep(0.004)
        import select
        result = self.decoder.pop(time.monotonic())
        if result is not None:
            return result
        ready, _, _ = select.select([self.stdin.fileno()], [], [], timeout)
        if ready:
            data = os.read(self.stdin.fileno(), 64)
            if not data:
                return "q"
            self.decoder.feed(data.decode("ascii", errors="ignore"), time.monotonic())
        return self.decoder.pop(time.monotonic())
