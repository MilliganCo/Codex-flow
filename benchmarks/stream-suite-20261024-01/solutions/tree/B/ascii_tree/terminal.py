"""Small native terminal adapter: Windows console and POSIX TTY, no curses."""
import os
from pathlib import Path
import shutil
import sys
import time

from .app import Explorer, compose

ENTER = "\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H"
LEAVE = "\x1b[?25h\x1b[?1049l"


class Terminal:
    def __init__(self):
        self.previous = None
        self.output_mode = None
        self.input_mode = None
        self.pending = ""
        self.escape_at = 0.

    def __enter__(self):
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes
                self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                self.kernel.GetStdHandle.argtypes = [wintypes.DWORD]
                self.kernel.GetStdHandle.restype = wintypes.HANDLE
                self.kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                self.kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                self.output_handle = self.kernel.GetStdHandle(-11)
                self.input_handle = self.kernel.GetStdHandle(-10)
                output, input_ = wintypes.DWORD(), wintypes.DWORD()
                if not self.kernel.GetConsoleMode(self.output_handle, ctypes.byref(output)):
                    raise OSError("stdout is not a Windows console")
                if not self.kernel.GetConsoleMode(self.input_handle, ctypes.byref(input_)):
                    raise OSError("stdin is not a Windows console")
                self.output_mode, self.input_mode = output.value, input_.value
                if not self.kernel.SetConsoleMode(self.output_handle, output.value | 0x4):
                    raise OSError("cannot enable virtual terminal output")
                # Read Ctrl+C as a key as well: ConPTY hosts may consume processed
                # control events before Python receives SIGINT. External SIGINT
                # still reaches run's KeyboardInterrupt cleanup path.
                if not self.kernel.SetConsoleMode(self.input_handle, (input_.value | 0x80) & ~(0x1 | 0x2 | 0x4 | 0x40)):
                    raise OSError("cannot enable interactive console input")
            else:
                import termios
                import tty
                self.previous = termios.tcgetattr(sys.stdin.fileno())
                tty.setcbreak(sys.stdin.fileno())
            sys.stdout.write(ENTER)
            sys.stdout.flush()
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def __exit__(self, *_):
        try:
            sys.stdout.write(LEAVE)
            sys.stdout.flush()
        finally:
            if os.name == "nt":
                if self.output_mode is not None:
                    self.kernel.SetConsoleMode(self.output_handle, self.output_mode)
                if self.input_mode is not None:
                    self.kernel.SetConsoleMode(self.input_handle, self.input_mode)
            elif self.previous is not None:
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.previous)

    def keys(self) -> list[str]:
        if os.name == "nt":
            import msvcrt
            keys = []
            while msvcrt.kbhit():
                char = msvcrt.getwch()
                if char in ("\x00", "\xe0"):
                    char = {"K": "left", "M": "right", "H": "up", "P": "down"}.get(msvcrt.getwch(), "")
                keys.append({"\x1b": "esc", "\x03": "ctrl+c"}.get(char, char))
            return keys
        import select
        while select.select([sys.stdin], [], [], 0)[0]:
            chunk = os.read(sys.stdin.fileno(), 128).decode("ascii", errors="ignore")
            if not chunk:
                return ["q"]
            self.pending += chunk
        keys = []
        while self.pending:
            if self.pending[0] != "\x1b":
                keys.append("ctrl+c" if self.pending[0] == "\x03" else self.pending[0])
                self.pending = self.pending[1:]
                continue
            sequences = {"\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
                         "\x1bOA": "up", "\x1bOB": "down", "\x1bOC": "right", "\x1bOD": "left"}
            match = next((seq for seq in sequences if self.pending.startswith(seq)), None)
            if match:
                keys.append(sequences[match])
                self.pending = self.pending[len(match):]
                self.escape_at = 0.
            elif any(seq.startswith(self.pending) for seq in sequences) and time.monotonic()-self.escape_at < .05:
                break
            elif not self.escape_at:
                self.escape_at = time.monotonic()
                break
            else:
                keys.append("esc")
                self.pending = self.pending[1:]
                self.escape_at = 0.
        return keys


def run(app: Explorer, export_dir: Path, *, max_frames: int | None = None) -> int:
    """Fixed-rate animation, event-driven paused display. Always restore console."""
    last_size = None
    frames = 0
    last_tick = time.monotonic()
    dirty = True
    frame_size = (100, 37)
    try:
        with Terminal() as terminal:
            while app.running:
                now = time.monotonic()
                size = shutil.get_terminal_size((100, 40))
                usable = (max(1, size.columns-1), max(1, size.lines))
                for key in terminal.keys():
                    if app.handle(key) == "export":
                        try:
                            app.export(*frame_size, export_dir)
                        except OSError as exc:
                            app.message = f"Export failed: {exc}"
                    dirty = True
                if not app.running:
                    break
                if app.playing and now-last_tick >= .1:
                    app.tick(min(.25, now-last_tick))
                    dirty = True
                if now-last_tick >= .1:
                    last_tick = now
                if dirty or usable != last_size:
                    lines, frame_size = compose(app, *usable)
                    sys.stdout.write("\x1b[H"+"\r\n".join(lines))
                    sys.stdout.flush()
                    last_size, dirty = usable, False
                    frames += 1
                    if max_frames is not None and frames >= max_frames:
                        break
                time.sleep(.015)
    except KeyboardInterrupt:
        return 0
    return 0
