"""Windows console / POSIX terminal adapters and a bounded alternate-screen UI.

No shell commands, curses dependency, background worker or external process.
The terminal context always restores console mode and cursor on exit.
"""

from collections import deque
from dataclasses import dataclass
import math
import os
from pathlib import Path
import select
import shutil
import sys
import time
from typing import TextIO

from .renderer import Frame, MAX_CELLS, render_tree
from .state import ExplorerState

ENTER_SCREEN = "\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H"
LEAVE_SCREEN = "\x1b[0m\x1b[?25h\x1b[?1049l"
ARROWS = {"\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
          "\x1bOA": "up", "\x1bOB": "down", "\x1bOC": "right", "\x1bOD": "left"}


class TerminalError(RuntimeError):
    pass


class KeyDecoder:
    """Recognize fragmented ANSI arrows and a standalone Escape key."""

    def __init__(self):
        self.pending = ""

    def feed(self, data: str, flush_escape: bool = False) -> list[str]:
        self.pending += data
        keys = []
        while self.pending:
            if self.pending[0] != "\x1b":
                char, self.pending = self.pending[0], self.pending[1:]
                if char == "\x03":
                    raise KeyboardInterrupt
                keys.append(char)
                continue
            sequence = next((seq for seq in ARROWS if self.pending.startswith(seq)), None)
            if sequence:
                keys.append(ARROWS[sequence])
                self.pending = self.pending[len(sequence):]
            elif any(seq.startswith(self.pending) for seq in ARROWS) and not flush_escape:
                break
            elif self.pending.startswith("\x1b[") and not flush_escape:
                # Ignore complete unsupported CSI sequences (e.g. Home/F keys).
                end = next((i for i in range(2, len(self.pending)) if "@" <= self.pending[i] <= "~"), None)
                if end is None and len(self.pending) < 32:
                    break
                self.pending = self.pending[end + 1:] if end is not None else ""
            else:
                keys.append("escape")
                self.pending = self.pending[1:]
        return keys


def _enable_windows_console(input_stream: TextIO, output: TextIO):
    import ctypes
    from ctypes import wintypes
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetConsoleMode.restype = wintypes.BOOL
    kernel.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.SetConsoleMode.restype = wintypes.BOOL
    output_handle = wintypes.HANDLE(msvcrt.get_osfhandle(output.fileno()))
    input_handle = wintypes.HANDLE(msvcrt.get_osfhandle(input_stream.fileno()))
    output_original, input_original = wintypes.DWORD(), wintypes.DWORD()
    if not (kernel.GetConsoleMode(output_handle, ctypes.byref(output_original)) and
            kernel.GetConsoleMode(input_handle, ctypes.byref(input_original))):
        raise TerminalError("Cannot read console modes. Use Windows Terminal or the render command.")
    if not kernel.SetConsoleMode(output_handle, output_original.value | 0x0004):
        raise TerminalError("Cannot enable ANSI output. Use Windows Terminal or the render command.")
    # Deliver Ctrl+C as a key even in ConPTY hosts that suppress control events.
    # getwch handles special keys; line editing/echo are unnecessary here.
    input_mode = input_original.value & ~(0x0001 | 0x0002 | 0x0004)
    if not kernel.SetConsoleMode(input_handle, input_mode):
        kernel.SetConsoleMode(output_handle, output_original.value)
        raise TerminalError("Cannot enable console key input.")

    def restore():
        kernel.SetConsoleMode(input_handle, input_original.value)
        kernel.SetConsoleMode(output_handle, output_original.value)

    return restore


def _enable_posix_cbreak(input_stream: TextIO):
    import termios
    import tty
    fd = input_stream.fileno()
    original = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    return lambda: termios.tcsetattr(fd, termios.TCSADRAIN, original)


class TerminalSession:
    def __init__(self, input_stream: TextIO | None = None, output: TextIO | None = None):
        self.input = input_stream if input_stream is not None else sys.stdin
        self.output = output if output is not None else sys.stdout
        self.restore_mode = None
        self.entered = False
        self.decoder = KeyDecoder()
        self.keys: deque[str] = deque()
        self.escape_at = 0.0

    def __enter__(self):
        if not self.input.isatty() or not self.output.isatty():
            raise TerminalError("Interactive view needs a TTY on stdin and stdout.")
        try:
            if os.name == "nt":
                self.restore_mode = _enable_windows_console(self.input, self.output)
            else:
                self.restore_mode = _enable_posix_cbreak(self.input)
            self.entered = True
            self.output.write(ENTER_SCREEN)
            self.output.flush()
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self.entered:
                self.output.write(LEAVE_SCREEN)
                self.output.flush()
        finally:
            self.entered = False
            if self.restore_mode:
                self.restore_mode()
                self.restore_mode = None

    def size(self) -> tuple[int, int]:
        try:
            size = os.get_terminal_size(self.output.fileno())
        except (OSError, ValueError):
            size = shutil.get_terminal_size((100, 40))
        # Leave the final column unused to avoid terminal autowrap/scroll.
        width = max(1, min(1000, size.columns - 1))
        height = max(1, min(1000, size.lines, MAX_CELLS // width))
        return width, height

    def draw(self, rows: tuple[str, ...], resized: bool = False) -> None:
        prefix = "\x1b[2J" if resized else ""
        self.output.write(prefix + "\x1b[H" + "\r\n".join(rows))
        self.output.flush()

    def read_key(self, timeout: float) -> str | None:
        if self.keys:
            return self.keys.popleft()
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + timeout
            while True:
                if msvcrt.kbhit():
                    char = msvcrt.getwch()
                    if char in ("\x00", "\xe0"):
                        return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(msvcrt.getwch())
                    if char == "\x03":
                        raise KeyboardInterrupt
                    return "escape" if char == "\x1b" else char
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                time.sleep(min(.01, remaining))
        ready, _, _ = select.select([self.input], [], [], timeout)
        if ready:
            data = os.read(self.input.fileno(), 64)
            if not data:
                return "q"
            self.keys.extend(self.decoder.feed(data.decode("utf-8", errors="ignore")))
            self.escape_at = time.monotonic()
        elif self.decoder.pending and time.monotonic() - self.escape_at >= .04:
            self.keys.extend(self.decoder.feed("", flush_escape=True))
        return self.keys.popleft() if self.keys else None


HELP = (
    "FIELD GUIDE / ASCII TREE EXPLORER",
    "",
    "1       2D: fixed XY silhouette of the same tree",
    "2       3D: perspective camera + depth buffer",
    "3       4D: a projection of (x, y, z, w) data",
    "Arrows  Orbit left/right, tilt up/down in 3D/4D",
    "[ / ]   Rotate W with space in 4D (, / . also work)",
    "+ / -   Zoom in/out (= also zooms in)",
    "Space   Play/pause: breeze, orbit, 4D rotation",
    "G       Next seed; only this key changes the tree",
    "R       Reset camera, zoom, 4D angle and time",
    "E       Export visible tree area as plain ASCII .txt",
    "H / ?   Toggle this guide",
    "Q / Esc Quit (Ctrl+C also restores the terminal)",
    "",
    "W = branch birth time along root-to-tip distance.",
    "A true XW/YW/ZW rotation mixes W with space.",
    "Then: 4D perspective -> 3D camera -> 2D characters.",
    "The terminal displays a projection, not a 4D volume.",
    "",
    "Choose plane at launch with --plane xw|yw|zw.",
    "Exports contain the tree only, without UI or ANSI.",
)


@dataclass(frozen=True, slots=True)
class Screen:
    rows: tuple[str, ...]
    frame: Frame


def viewport_size(width: int, height: int) -> tuple[int, int]:
    return max(1, width), max(1, height - 6)


def compose_screen(state: ExplorerState, width: int, height: int) -> Screen:
    width, height = max(1, width), max(1, height)
    o = state.options
    playing = "PLAY" if state.playing else "PAUSED"
    frame = render_tree(state.tree, state.viewport(*viewport_size(width, height)))
    title = f" ASCII TREE EXPLORER / {o.mode.upper()} / seed {state.tree.seed}"
    controls = (f" yaw {o.yaw + (o.time * 15 if o.mode != '2d' else 0):.0f}  pitch {o.pitch:.0f}"
                f"  {o.plane.upper()} {o.angle4 + (o.time * 6 if o.mode == '4d' else 0):.0f}"
                f"  zoom {o.zoom:.2f}  {playing}")
    explanation = {"2d": " XY silhouette / same graph / breeze animation",
                   "3d": " 3D perspective / nearest surface wins / arrows orbit",
                   "4d": " 4D DATA -> 3D -> 2D / W=birth time / [ ] or , . rotate"}[o.mode]
    rows = [title, controls, explanation, *frame.rows,
            " 1/2/3 mode  Arrows orbit  [ ] 4D  +/- zoom  Space play",
            " G seed  R reset  E export  H/? help  Q/Esc quit",
            " " + state.status]
    if width < 42 or height < 14:
        # Keep shortcuts active while presenting a useful compact viewport.
        rows = [f"{o.mode.upper()} seed {state.tree.seed} {playing}",
                *frame.rows, "1/2/3 modes | H help", "Q quit | E export", state.status]
    rows = [line[:width].ljust(width) for line in rows[:height]]
    rows += [" " * width] * (height - len(rows))
    if state.help_visible:
        _overlay_help(rows, width, height)
    return Screen(tuple(rows), frame)


def _overlay_help(rows: list[str], width: int, height: int) -> None:
    if width < 24 or height < 8:
        compact = ("HELP", "1/2/3 modes", "+/- zoom", "G new seed", "E export", "H close", "Q quit")
        for index, line in enumerate(compact[:height]):
            rows[index] = line[:width].ljust(width)
        return
    box_width = min(width - 2, 72)
    inside = box_width - 4
    content = []
    import textwrap
    for line in HELP:
        content.extend(textwrap.wrap(line, width=inside, replace_whitespace=False) or [""])
    available = height - 4
    if len(content) > available:
        content = content[:max(1, available - 1)] + ["H closes help; full keys in README."]
    box = ["+" + "-" * (box_width - 2) + "+"]
    box += ["| " + line[:inside].ljust(inside) + " |" for line in content]
    box += ["+" + "-" * (box_width - 2) + "+"]
    left, top = (width - box_width) // 2, max(0, (height - len(box)) // 2)
    for index, line in enumerate(box[:height]):
        row = top + index
        if row < height:
            rows[row] = rows[row][:left] + line + rows[row][left + box_width:]


def export_frame(frame: Frame, directory: Path, seed: int, mode: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    data = frame.text().encode("ascii")
    # Exclusive creation avoids overwriting an earlier screenshot.
    for index in range(1, 10_001):
        path = directory / f"tree_seed{seed}_{mode}_{index:03d}.txt"
        try:
            with path.open("xb") as output:
                output.write(data)
            return path
        except FileExistsError:
            continue
    raise OSError("Export directory already contains 10000 frames for this tree/mode.")


def run_interactive(state: ExplorerState, fps: float = 8.0,
                    export_dir: Path = Path("exports"), session=None) -> int:
    if not math.isfinite(fps) or not 1 <= fps <= 30:
        raise ValueError("fps must be in 1..30")
    terminal = session if session is not None else TerminalSession()
    with terminal:
        dirty, old_size = True, None
        last_tick = time.monotonic()
        while state.running:
            now = time.monotonic()
            if state.playing and now - last_tick >= 1 / fps:
                state.tick(now - last_tick)
                last_tick, dirty = now, True
            elif not state.playing:
                last_tick = now
            size = terminal.size()
            resized = size != old_size
            if dirty or resized:
                screen = compose_screen(state, *size)
                terminal.draw(screen.rows, resized=resized)
                dirty, old_size = False, size
            key = terminal.read_key(.04)
            if key is not None:
                intent = state.handle_key(key)
                if intent == "export":
                    # Render current state/size, even if it changed since last draw.
                    frame = render_tree(state.tree, state.viewport(*viewport_size(*terminal.size())))
                    try:
                        path = export_frame(frame, export_dir, state.tree.seed, state.options.mode)
                        state.status = f"Saved {path} ({frame.width}x{frame.height}, ASCII)."
                    except OSError as error:
                        state.status = f"Export failed: {error}"
                dirty = True
    return 0
