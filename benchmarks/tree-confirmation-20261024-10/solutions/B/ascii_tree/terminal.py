"""Small native terminal adapter: msvcrt on Windows, termios/select on POSIX."""
from dataclasses import dataclass, replace
import math
import os
from pathlib import Path
import shutil
import sys
import time

from .model import Tree, generate_tree
from .render import Camera, render

HELP = (
    "CONTROLS / same tree in every mode",
    "1 2D orthographic XY | 2 3D perspective | 3 4D projection",
    "Arrows / WASD : orbit and tilt (3D/4D)",
    "[ / ] : rotate XW in 4D (mixes space and branch age W)",
    "+ / - : zoom | Space : animate / pause | R : reset view",
    "G : next seed | E : export the visible tree raster as .txt",
    "H / ? : close help | Q / Esc : exit | Ctrl+C : exit",
    "4D: XYZW -> XW rotation -> 3D perspective -> 2D terminal.",
    "W is developmental path age. You see a projection of 4D data.",
    "Tip: pause, then compare [ and ] while the seed stays fixed.",
)


@dataclass
class Explorer:
    tree: Tree
    camera: Camera
    running: bool = True
    animated: bool = False
    help_open: bool = False
    message: str = "H help | Space animate | E export"

    def key(self, key):
        """Pure controller except explicit G regeneration; E is handled by the UI."""
        if key in ("q", "Q", "escape", "\x03"):
            self.running = False
        elif key in ("1", "2", "3"):
            self.camera = replace(self.camera, mode={"1": "2d", "2": "3d", "3": "4d"}[key])
        elif key in ("h", "H", "?"):
            self.help_open = not self.help_open
        elif key == " ":
            self.animated = not self.animated
        elif key in ("g", "G"):
            self.tree = generate_tree(self.tree.seed + 1)
            self.message = f"New tree: seed {self.tree.seed}"
        elif key in ("r", "R"):
            self.camera = Camera(mode=self.camera.mode, aspect=self.camera.aspect)
            self.message = "Orientation, animation time and zoom reset"
        elif key in ("+", "=", "-", "_"):
            factor = 1.12 if key in ("+", "=") else 1 / 1.12
            self.camera = replace(self.camera, zoom=max(.1, min(8., self.camera.zoom * factor)))
        elif key in ("[", "]") and self.camera.mode == "4d":
            self.camera = replace(self.camera, angle4d=math.remainder(
                self.camera.angle4d + (8 if key == "]" else -8), 360))
        elif self.camera.mode != "2d":
            if key in ("left", "a", "A", "right", "d", "D"):
                self.camera = replace(self.camera, yaw=math.remainder(
                    self.camera.yaw + (-8 if key in ("left", "a", "A") else 8), 360))
            elif key in ("up", "w", "W", "down", "s", "S"):
                self.camera = replace(self.camera, pitch=max(-85., min(85.,
                    self.camera.pitch + (6 if key in ("up", "w", "W") else -6))))

    def tick(self, seconds):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Elapsed time must be finite and nonnegative")
        if self.animated:
            self.camera = replace(self.camera, time=(self.camera.time + min(seconds, .25)) % 3600)


class Terminal:
    def __enter__(self):
        self.saved = None
        self.saved_output = None
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes
                self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                self.kernel.GetStdHandle.argtypes = [wintypes.DWORD]
                self.kernel.GetStdHandle.restype = wintypes.HANDLE
                self.kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                self.kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                self.output_handle = self.kernel.GetStdHandle(-11 & 0xffffffff)
                mode = wintypes.DWORD()
                if not self.kernel.GetConsoleMode(self.output_handle, ctypes.byref(mode)):
                    raise OSError("Cannot read console mode; use render for headless output")
                self.saved_output = mode.value
                if not self.kernel.SetConsoleMode(self.output_handle, mode.value | 4):
                    raise OSError("Cannot enable ANSI terminal output")
                # Read Ctrl+C as an explicit key. Some PowerShell-hosted children
                # inherit an ignored console signal; raw input avoids losing it.
                self.input_handle = self.kernel.GetStdHandle(-10 & 0xffffffff)
                input_mode = wintypes.DWORD()
                if self.kernel.GetConsoleMode(self.input_handle, ctypes.byref(input_mode)):
                    self.saved = input_mode.value
                    raw_mode = (input_mode.value | 0x80) & ~(0x40 | 0x01 | 0x02 | 0x04)
                    if not self.kernel.SetConsoleMode(self.input_handle, raw_mode):
                        raise OSError("Cannot enable interactive console input")
            else:
                import termios
                import tty
                self.saved = termios.tcgetattr(sys.stdin.fileno())
                tty.setcbreak(sys.stdin.fileno())
            sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")
            sys.stdout.flush()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        try:
            sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
        finally:
            if os.name == "nt":
                if self.saved is not None:
                    self.kernel.SetConsoleMode(self.input_handle, self.saved)
                if self.saved_output is not None:
                    self.kernel.SetConsoleMode(self.output_handle, self.saved_output)
            elif self.saved is not None:
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.saved)

    def key(self, timeout=.03):
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + timeout
            while not msvcrt.kbhit():
                if time.monotonic() >= deadline:
                    return None
                time.sleep(.005)
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(msvcrt.getwch())
            return "escape" if key == "\x1b" else key
        import select
        if not select.select([sys.stdin], [], [], timeout)[0]:
            return None
        raw = os.read(sys.stdin.fileno(), 1)
        if raw != b"\x1b":
            return raw.decode("ascii", errors="ignore") if raw else "q"
        sequence = b""
        while len(sequence) < 2 and select.select([sys.stdin], [], [], .025)[0]:
            sequence += os.read(sys.stdin.fileno(), 1)
        return {b"[A": "up", b"[B": "down", b"[C": "right", b"[D": "left",
                b"OA": "up", b"OB": "down", b"OC": "right", b"OD": "left"}.get(sequence, "escape")

    def size(self):
        columns, rows = shutil.get_terminal_size((100, 40))
        # Spare the last column to avoid autowrap and scroll at the bottom right.
        return max(1, min(999, columns - 1)), max(1, min(250, rows))

    def paint(self, lines, width, height):
        content = [line[:width].ljust(width) for line in lines[:height]]
        content += [" " * width] * (height - len(content))
        sys.stdout.write("\x1b[H" + "\r\n".join(content))
        sys.stdout.flush()


def compose(state, width, height):
    if height < 8 or width < 24:
        frame = render(state.tree, width, max(1, height - 1), state.camera)
        lines = [f"{state.camera.mode.upper()} {state.tree.seed} Q quit"] + frame.splitlines()
        return lines[:height], frame
    art_height = height - 5
    frame = render(state.tree, width, art_height, state.camera)
    camera = state.camera
    status = (f" ASCII TREE EXPLORER | {camera.mode.upper()} | seed {state.tree.seed} | "
              f"{'PLAY' if state.animated else 'PAUSED'} | zoom {camera.zoom:.2f}")
    info = (f" yaw {math.remainder(camera.yaw + camera.time * 14, 360):.0f}  pitch {camera.pitch:.0f}  "
            f"XW {math.remainder(camera.angle4d + camera.time * 19, 360):.0f} deg")
    if camera.mode == "4d":
        info += " | 4D data -> 3D -> 2D projection; W = branch age"
    else:
        info += " | same geometry; G creates the next tree"
    lines = [status, info, "-" * width] + frame.splitlines() + [
        " 1 2D  2 3D  3 4D | Arrows orbit | [ ] XW | +/- zoom | H help | Q quit",
        " " + state.message,
    ]
    if state.help_open:
        start = 4
        for i, line in enumerate(HELP[:max(0, art_height - 1)]):
            lines[start + i] = " " + line
    return lines, frame


def export_frame(directory: Path, state, frame):
    """Exclusive creation never overwrites a previous export, including another run."""
    directory.mkdir(parents=True, exist_ok=True)
    for index in range(1, 10001):
        path = directory / f"tree-{state.tree.seed}-{state.camera.mode}-{index:04d}.txt"
        try:
            output = path.open("xb")
        except FileExistsError:
            continue
        try:
            with output:
                output.write(frame.encode("ascii"))
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    raise OSError("Export directory already contains 10000 frames for this tree/mode")


def run(tree, camera, export_dir, frames=None, terminal_factory=Terminal):
    state = Explorer(tree, camera)
    try:
        with terminal_factory() as terminal:
            previous = time.monotonic()
            count = 0
            dirty = True
            last_size = None
            while state.running:
                now = time.monotonic()
                elapsed, previous = now - previous, now
                state.tick(elapsed)
                size = terminal.size()
                if dirty or size != last_size or state.animated:
                    lines, frame = compose(state, *size)
                    terminal.paint(lines, *size)
                    count += 1
                    last_size, dirty = size, False
                    if frames is not None and count >= frames:
                        break
                key = terminal.key(.06 if state.animated else .04)
                if key is not None:
                    if key == "\x03":
                        raise KeyboardInterrupt
                    if key in ("e", "E"):
                        try:
                            # Render after resize, even if no frame has been painted yet.
                            _, frame = compose(state, *terminal.size())
                            path = export_frame(export_dir, state, frame)
                            state.message = f"Saved {path}"
                        except OSError as error:
                            state.message = f"Export failed: {error}"
                    else:
                        state.key(key)
                    dirty = True
                # Finite --frames also advances when paused for startup/shutdown checks.
                if frames is not None:
                    dirty = True
        return 0
    except KeyboardInterrupt:
        return 130
