"""Small native terminal backend: Windows console + POSIX, no curses dependency."""

from collections import deque
import os
from pathlib import Path
import shutil
import sys
import time

from .render import export_frame
from .state import Explorer, HELP

ENTER_SCREEN = "\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H"
LEAVE_SCREEN = "\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l"


class KeyDecoder:
    """Handles split ANSI sequences and native Windows extended-key prefixes."""

    def __init__(self) -> None:
        self.buffer = ""
        self.escape_at = 0.0

    def feed(self, text: str, now: float) -> None:
        if not self.buffer and text.startswith("\x1b"):
            self.escape_at = now
        self.buffer += text

    def pop(self, now: float) -> str | None:
        if not self.buffer:
            return None
        first = self.buffer[0]
        if first in ("\x00", "\xe0"):
            if len(self.buffer) < 2:
                return None
            second, self.buffer = self.buffer[1], self.buffer[2:]
            if self.buffer.startswith("\x1b"):
                self.escape_at = now
            return {"K": "left", "M": "right", "H": "up", "P": "down"}.get(second, "unknown")
        if first == "\x1b":
            if len(self.buffer) >= 3 and self.buffer[1] in ("[", "O"):
                # Consume complete CSI sequences, including modifier keys.
                for i in range(2, len(self.buffer)):
                    if "@" <= self.buffer[i] <= "~":
                        final, self.buffer = self.buffer[i], self.buffer[i + 1:]
                        if self.buffer.startswith("\x1b"):
                            self.escape_at = now
                        return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(final, "unknown")
            if now - self.escape_at < 0.04:
                return None
            self.buffer = self.buffer[1:]
            return "escape"
        self.buffer = self.buffer[1:]
        if self.buffer.startswith("\x1b"):
            self.escape_at = now
        return first


class NativeTerminal:
    def __init__(self) -> None:
        self.decoder = KeyDecoder()
        self._input_mode = None
        self._output_mode = None
        self._kernel = None
        self._output_handle = None

    def __enter__(self):
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise OSError("interactive terminal required")
        if os.name == "nt":
            import ctypes
            import msvcrt
            from ctypes import wintypes

            self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self._kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            self._kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            handle = msvcrt.get_osfhandle(sys.stdout.fileno())
            mode = wintypes.DWORD()
            if not self._kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                raise OSError("Windows console handle unavailable; use Windows Terminal")
            self._output_mode, self._output_handle = mode.value, handle
            if not self._kernel.SetConsoleMode(handle, mode.value | 0x0004):
                raise OSError("cannot enable Windows virtual terminal output")
        else:
            import termios
            import tty

            self._input_mode = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        try:
            sys.stdout.write(ENTER_SCREEN)
            sys.stdout.flush()
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(self, *_exc):
        try:
            sys.stdout.write(LEAVE_SCREEN)
            sys.stdout.flush()
        finally:
            if os.name == "nt" and self._output_mode is not None:
                self._kernel.SetConsoleMode(self._output_handle, self._output_mode)
            elif self._input_mode is not None:
                import termios

                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._input_mode)

    def size(self) -> tuple[int, int]:
        size = shutil.get_terminal_size((100, 40))
        return (max(1, min(1000, size.columns)), max(1, min(500, size.lines)))

    def read_key(self, timeout: float) -> str | None:
        deadline = time.monotonic() + max(0, timeout)
        while True:
            now = time.monotonic()
            key = self.decoder.pop(now)
            if key is not None:
                return key
            if os.name == "nt":
                import msvcrt

                while msvcrt.kbhit():
                    self.decoder.feed(msvcrt.getwch(), time.monotonic())
            else:
                import select

                ready, _, _ = select.select([sys.stdin], [], [], 0)
                if ready:
                    data = os.read(sys.stdin.fileno(), 64)
                    if not data:
                        return "q"
                    self.decoder.feed(data.decode("ascii", errors="ignore"), now)
            key = self.decoder.pop(time.monotonic())
            if key is not None:
                return key
            if now >= deadline:
                return None
            time.sleep(min(0.005, max(0, deadline - time.monotonic())))

    def draw(self, lines: tuple[str, ...]) -> None:
        # Explicit cursor addressing avoids line-feed scrolling at the bottom
        # right cell. Erasing each line also handles terminal shrink/growth.
        output = ["\x1b[?7l"]
        for i, line in enumerate(lines):
            output.append(f"\x1b[{i + 1};1H\x1b[2K{line}")
        output.append("\x1b[?7h")
        sys.stdout.write("".join(output))
        sys.stdout.flush()


def layout(state: Explorer, width: int, height: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return UI rows and the exact underlying image exported with E."""
    width, height = max(1, min(1000, width)), max(1, min(500, height))
    chrome = 4 if height >= 8 else 1 if height >= 3 else 0
    image = state.frame(width, max(1, height - chrome))
    rows = list(image)
    if state.help_visible:
        # Wrap help to fit narrow screens; crop safely when no space remains.
        from textwrap import wrap

        help_rows = [part for line in HELP for part in (wrap(line, max(1, width - 4)) or [""])]
        for i, text in enumerate(help_rows[:len(rows)]):
            rows[i] = ("  " + text).ljust(width)[:width]
    if chrome == 4:
        explanation = ("4D data projection: (x,y,z,w) -> XW rotation -> 3D -> screen"
                       if state.mode == "4d" else
                       "1:2D  2:3D  3:4D | Arrows:orbit | [ ]:XW | +/-:zoom | Space:play")
        rows = [state.status(), "-" * width] + rows + [explanation, state.message]
    elif chrome == 1:
        rows = [f"{state.mode.upper()} seed {state.seed} | H help | Q quit"] + rows
    return tuple(row[:width].ljust(width) for row in rows[:height]), image


def run_view(state: Explorer, terminal, *, fps: int = 12,
             export_dir: Path = Path("exports"), max_frames: int | None = None,
             demo: bool = False) -> int:
    """Injectable loop used by the native frontend and integration tests."""
    dirty = True
    previous_size = None
    last_tick = time.monotonic()
    next_draw = last_tick
    frame_count, export_count = 0, 0
    image: tuple[str, ...] = ()
    # A finite repeatable live tour, using precisely the regular key handlers.
    tour = deque([(0.0, "1"), (1.2, "2"), (2.4, "right"), (3.6, "3"),
                  (4.8, "]"), (6.0, "]"), (7.2, "g"), (8.4, "h"),
                  (10.0, "h"), (11.0, " "), (13.0, "q")]) if demo else deque()
    started = last_tick
    try:
        with terminal:
            while state.running:
                now = time.monotonic()
                key = terminal.read_key(max(0, min(0.05, next_draw - now)))
                now = time.monotonic()
                if tour and now - started >= tour[0][0]:
                    _, key = tour.popleft()
                if key is not None:
                    action = state.key(key)
                    dirty = True
                    if action == "export":
                        # Re-render at the current size, so E also works directly
                        # after resize or a mode switch, before the next redraw.
                        w, h = terminal.size()
                        _, image = layout(state, w, h)
                        export_count += 1
                        path = export_dir / f"tree-{state.seed}-{state.mode}-{export_count:03d}.txt"
                        try:
                            export_dir.mkdir(parents=True, exist_ok=True)
                            export_frame(path, image)
                            state.message = f"Saved {path}"
                        except OSError as exc:
                            state.message = f"Export failed: {exc}"
                if not state.running:
                    break
                size = terminal.size()
                dirty |= size != previous_size
                if now >= next_draw:
                    state.tick(min(0.25, now - last_tick))
                    last_tick = now
                    if dirty or state.playing:
                        rows, image = layout(state, *size)
                        terminal.draw(rows)
                        previous_size, dirty = size, False
                        frame_count += 1
                    next_draw = now + 1 / fps
                    if max_frames is not None and frame_count >= max_frames:
                        break
    except KeyboardInterrupt:
        state.running = False
        return 130
    return 0
