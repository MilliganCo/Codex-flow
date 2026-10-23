"""Windows console + POSIX TTY support, with no curses dependency."""

import os
import shutil
import sys
import time


class KeyDecoder:
    """Incremental ANSI input, including arrows split across reads."""

    ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}

    def __init__(self):
        self.pending = ""

    def feed(self, text: str, flush_escape: bool = False) -> list[str]:
        self.pending += text
        keys: list[str] = []
        while self.pending:
            if self.pending[0] != "\x1b":
                keys.append(self.pending[0])
                self.pending = self.pending[1:]
                continue
            if len(self.pending) == 1:
                if flush_escape:
                    keys.append("escape")
                    self.pending = ""
                break
            if self.pending[1] in ("[", "O"):
                end = next((i for i in range(2, len(self.pending)) if "@" <= self.pending[i] <= "~"), None)
                if end is None:
                    if flush_escape or len(self.pending) > 32:
                        self.pending = ""
                    break
                final = self.pending[end]
                if final in self.ARROWS:
                    keys.append(self.ARROWS[final])
                self.pending = self.pending[end + 1:]
            else:
                keys.append("escape")
                self.pending = self.pending[1:]
        return keys


class Terminal:
    def __init__(self, stdin=None, stdout=None):
        self.stdin = stdin if stdin is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout
        self.decoder = KeyDecoder()
        self._saved = None
        self._entered = False
        self._escape_since: float | None = None
        self._win_prefix = False

    def __enter__(self):
        if not self.stdin.isatty() or not self.stdout.isatty():
            raise OSError("view needs an interactive input and output TTY; use render")
        try:
            if os.name == "nt":
                self._setup_windows()
            else:
                import termios
                import tty
                self._saved = termios.tcgetattr(self.stdin.fileno())
                tty.setcbreak(self.stdin.fileno())
            # Mark before writing so even a partial startup write gets cleanup.
            self._entered = True
            self.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")
            self.stdout.flush()
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def _setup_windows(self) -> None:
        import ctypes
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetConsoleMode.restype = wintypes.BOOL
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.SetConsoleMode.restype = wintypes.BOOL
        input_handle = msvcrt.get_osfhandle(self.stdin.fileno())
        output_handle = msvcrt.get_osfhandle(self.stdout.fileno())
        old_input, old_output = wintypes.DWORD(), wintypes.DWORD()
        if not kernel.GetConsoleMode(input_handle, ctypes.byref(old_input)) or not kernel.GetConsoleMode(output_handle, ctypes.byref(old_output)):
            raise OSError("Windows console handles are unavailable; use Windows Terminal or render")
        self._saved = kernel, input_handle, output_handle, old_input.value, old_output.value
        # Read Ctrl+C as a key. Processed Ctrl+C can be swallowed by a parent
        # PowerShell/ConPTY host instead of delivering Python's signal handler.
        input_mode = (old_input.value | 0x0080) & ~(0x0001 | 0x0002 | 0x0004 | 0x0040 | 0x0200)
        if not kernel.SetConsoleMode(input_handle, input_mode) or not kernel.SetConsoleMode(output_handle, old_output.value | 0x0004):
            raise OSError("could not enable Windows virtual-terminal output")

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self._entered:
                self.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
                self.stdout.flush()
        finally:
            if self._saved is not None:
                if os.name == "nt":
                    kernel, ih, oh, im, om = self._saved
                    kernel.SetConsoleMode(ih, im)
                    kernel.SetConsoleMode(oh, om)
                else:
                    import termios
                    termios.tcsetattr(self.stdin.fileno(), termios.TCSADRAIN, self._saved)
            self._saved = None
            self._entered = False
        return False

    def size(self) -> tuple[int, int]:
        try:
            size = os.get_terminal_size(self.stdout.fileno())
        except (OSError, ValueError):
            size = shutil.get_terminal_size((100, 40))
        # Reserve final column/row: no bottom-right wrap or scrollback spam.
        return min(500, max(1, size.columns - 1)), min(200, max(1, size.lines - 1))

    def draw(self, frame: str) -> None:
        self.stdout.write("\x1b[H" + frame.rstrip("\n").replace("\n", "\r\n") + "\x1b[J")
        self.stdout.flush()

    def read_keys(self, timeout: float) -> list[str]:
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + timeout
            while not msvcrt.kbhit() and time.monotonic() < deadline:
                time.sleep(min(0.01, max(0, deadline - time.monotonic())))
            keys = []
            arrows = {"H": "up", "P": "down", "K": "left", "M": "right"}
            while msvcrt.kbhit():
                key = msvcrt.getwch()
                if self._win_prefix:
                    if key in arrows:
                        keys.append(arrows[key])
                    self._win_prefix = False
                elif key in ("\x00", "\xe0"):
                    self._win_prefix = True
                elif key == "\x1b":
                    keys.append("escape")
                elif key == "\x03":
                    raise KeyboardInterrupt
                else:
                    keys.append(key)
            return keys
        import select
        ready, _, _ = select.select([self.stdin], [], [], timeout)
        data = os.read(self.stdin.fileno(), 1024).decode("ascii", "ignore") if ready else ""
        if ready and not data:
            return ["q"]
        now = time.monotonic()
        flush = self._escape_since is not None and now - self._escape_since >= 0.08
        keys = self.decoder.feed(data, flush_escape=flush)
        if self.decoder.pending and self._escape_since is None:
            self._escape_since = now
        elif not self.decoder.pending:
            self._escape_since = None
        return keys
