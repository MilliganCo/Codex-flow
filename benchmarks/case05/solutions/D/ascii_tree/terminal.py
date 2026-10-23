"""Small Windows / POSIX terminal adapter. All console changes are reversible."""

import os
import shutil
import sys
import time

from .render import MAX_HEIGHT, MAX_WIDTH
from .state import Explorer

ENTER_SCREEN = "\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H"
LEAVE_SCREEN = "\x1b[0m\x1b[?25h\x1b[?1049l"
WINDOWS_KEYS = {"K": "left", "M": "right", "H": "up", "P": "down"}
ANSI_KEYS = {"\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
             "\x1bOA": "up", "\x1bOB": "down", "\x1bOC": "right", "\x1bOD": "left"}


def console_mode(mode: int, output: bool) -> int:
    # msvcrt expects native extended keys, so disable VT input as well as echo,
    # line buffering and QuickEdit. Read Ctrl+C as a key: inherited Windows
    # process groups can otherwise swallow its processed console signal.
    return mode | 0x5 if output else (mode & ~0x247) | 0x80


def windows_key(first: str, second: str = "") -> str:
    if first in {"\x00", "\xe0"}:
        return WINDOWS_KEYS.get(second, "")
    return "escape" if first == "\x1b" else "ctrl+c" if first == "\x03" else first


class Terminal:
    def __init__(self):
        self.output = sys.stdout
        self.input = sys.stdin
        self.saved_modes: list[tuple[object, int]] = []
        self.saved_termios = None
        self.kernel = None
        self.entered = False

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
                for stream_id, output in ((-11, True), (-10, False)):
                    handle = self.kernel.GetStdHandle(stream_id & 0xFFFFFFFF)
                    mode = wintypes.DWORD()
                    if not self.kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                        raise OSError("A Windows console is required; use 'render' for redirected streams")
                    self.saved_modes.append((handle, mode.value))
                    new_mode = console_mode(mode.value, output)
                    if not self.kernel.SetConsoleMode(handle, new_mode):
                        raise OSError("Cannot enable terminal mode; use Windows Terminal or 'render'")
            else:
                import termios
                import tty
                self.saved_termios = termios.tcgetattr(self.input.fileno())
                tty.setcbreak(self.input.fileno())
            self.entered = True
            self.output.write(ENTER_SCREEN)
            self.output.flush()
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.entered:
                self.output.write(LEAVE_SCREEN)
                self.output.flush()
        finally:
            if self.kernel is not None:
                for handle, mode in reversed(self.saved_modes):
                    self.kernel.SetConsoleMode(handle, mode)
                self.saved_modes.clear()
            if self.saved_termios is not None:
                import termios
                termios.tcsetattr(self.input.fileno(), termios.TCSADRAIN, self.saved_termios)
                self.saved_termios = None
            self.entered = False

    def size(self) -> tuple[int, int]:
        size = shutil.get_terminal_size((100, 40))
        # Leave a physical column and row unused to avoid autowrap/scrolling.
        return max(1, min(MAX_WIDTH, size.columns - 1)), max(1, min(MAX_HEIGHT, size.lines - 1))

    def present(self, rows: tuple[str, ...]) -> None:
        # Address each row explicitly, so LF/CR modes cannot shift subsequent rows.
        self.output.write("".join(f"\x1b[{i + 1};1H{row}\x1b[K" for i, row in enumerate(rows)) + "\x1b[J")
        self.output.flush()

    def read_key(self, timeout: float) -> str:
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + timeout
            while True:
                if msvcrt.kbhit():
                    first = msvcrt.getwch()
                    return windows_key(first, msvcrt.getwch() if first in {"\x00", "\xe0"} else "")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return ""
                time.sleep(min(0.01, remaining))
        import select
        if not select.select([self.input], [], [], timeout)[0]:
            return ""
        key = os.read(self.input.fileno(), 1).decode("ascii", "ignore")
        if key == "\x1b":
            # A lone Esc exits; CSI/SS3 arrows arrive as a short byte sequence.
            while len(key) < 8 and select.select([self.input], [], [], 0.025)[0]:
                key += os.read(self.input.fileno(), 1).decode("ascii", "ignore")
                if key in ANSI_KEYS:
                    return ANSI_KEYS[key]
            return "escape" if key == "\x1b" else ""
        return "ctrl+c" if key == "\x03" else key or "q"


HELP = (
    "ASCII TREE EXPLORER / CONTROLS",
    "",
    "1: 2D   2: 3D   3: 4D   (same tree)",
    "Arrow keys: orbit / tilt camera in 3D and 4D",
    "[ / ]: rotate the XW hyperplane in 4D",
    "+ / -: zoom   (= also zooms in)",
    "Space: pause / animate (3D orbit, 4D orbit + XW)",
    "G: next seed   R: reset camera / zoom / animation",
    "E: export visible tree to exports/*.txt (no ANSI)",
    "H / ?: close help   Q / Esc / Ctrl+C: quit",
    "",
    "4D means a projection of (x,y,z,w) data:",
    "w is growth-path distance, not a second tree.",
    "Rotate XW, project 4D -> 3D, then 3D -> 2D.",
    "2D is a fixed orthographic front projection.",
    "",
    "Try: 3, ], ], Space. Pause before exporting.",
)


def compose_screen(state: Explorer, width: int, height: int) -> tuple[str, ...]:
    view = state.view
    if height < 8 or width < 24:
        lines = [f"TREE {view.mode.upper()}", f"seed {state.seed}", "Small terminal", "1/2/3 mode; Q quit"]
        state.draw(width, max(1, height - 2))
    else:
        frame = state.draw(width, height - 6)
        mode_info = ("4D DATA -> XW -> 3D -> 2D projection" if view.mode == "4d" else
                     "Orthographic front projection" if view.mode == "2d" else "Perspective + depth buffer")
        lines = [f" ASCII TREE EXPLORER   [{view.mode.upper()}]   seed {state.seed}   "
                 f"{'PLAY' if state.animated else 'PAUSED'}",
                 f" yaw {view.yaw:6.1f}  pitch {view.pitch:5.1f}  XW {view.angle4d:6.1f} deg  zoom {view.zoom:.2f}",
                 f" {mode_info}"]
        if state.help_open:
            body = [" " + line for line in HELP]
            # Keep the complete control list readable on moderately short terminals.
            if len(body) > height - 6:
                body = [line for line in body if line.strip()]
            lines += body[:height - 6] + [""] * max(0, height - 6 - len(body))
        else:
            lines += list(frame.rows)
        lines += [" 1/2/3 mode | Arrows orbit | [ ] XW | +/- zoom | Space play",
                  " G seed | R reset | E export | H help | Q quit",
                  " " + state.message]
    return tuple((lines[i] if i < len(lines) else "")[:width].ljust(width) for i in range(height))


def run_interactive(state: Explorer, terminal_factory=Terminal) -> int:
    try:
        with terminal_factory() as terminal:
            last_time = time.monotonic()
            last_size = None
            dirty = True
            while state.running:
                now = time.monotonic()
                state.advance(min(0.25, now - last_time))
                last_time = now
                size = terminal.size()
                if dirty or size != last_size or (state.animated and state.view.mode != "2d"):
                    terminal.present(compose_screen(state, *size))
                    last_size, dirty = size, False
                key = terminal.read_key(1 / 12 if state.animated else 0.12)
                if key:
                    if key == "ctrl+c":
                        raise KeyboardInterrupt
                    state.key(key)
                    dirty = True
        return 0
    except KeyboardInterrupt:
        state.running = False
        return 130
