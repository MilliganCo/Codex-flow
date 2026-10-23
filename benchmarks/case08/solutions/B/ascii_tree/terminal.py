"""Small native terminal backend: Windows console / POSIX termios, no deps."""
import os
import sys
import time
from pathlib import Path
from .render import render, export_frame
from .state import Explorer


HELP = [
    "ASCII TREE EXPLORER / FIELD GUIDE",
    "1 2D: orthographic study of the same 3D branch graph",
    "2 3D: perspective, per-cell depth and branch shading",
    "3 4D: projection of (x,y,z,w) data: 4D -> 3D -> 2D",
    "W = root-to-vertex path length / 2 - 4 (growth coordinate).",
    "[ / ] rotate the XW plane: X and W really mix.",
    "",
    "Left/Right: orbit   Up/Down: tilt   (3D and 4D)",
    "[ / ]: XW angle    + / -: zoom     R: reset view",
    "Space: animate/pause (3D orbit / 4D XW; 2D stays still)",
    "G: next seed       E: export       H / ?: close help",
    "Q / Esc: quit      Ctrl+C: quit safely",
    "",
    "Exports contain only the tree raster, no ANSI or interface.",
    "Tip: pause, orbit, then compare 3D with 4D at XW = 0 / 45.",
]


class Terminal:
    def __init__(self):
        self.saved = []
        self.fd = None

    def __enter__(self):
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.GetStdHandle.restype = wintypes.HANDLE
                kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wintypes.BOOL]
                # Some process hosts inherit an ignored CTRL_C state. Restore
                # delivery for this process so Python can unwind the context.
                kernel.SetConsoleCtrlHandler(None, False)
                for identifier in (-10, -11):
                    handle = kernel.GetStdHandle(identifier)
                    mode = wintypes.DWORD()
                    if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                        raise OSError("Windows console handles are unavailable; use render")
                    self.saved.append((kernel, handle, mode.value))
                    # Preserve processed Ctrl+C; disable line/echo/QuickEdit input.
                    value = (mode.value | 0x80 | 0x1) & ~(0x2 | 0x4 | 0x40) if identifier == -10 else mode.value | 0x4
                    if not kernel.SetConsoleMode(handle, value):
                        raise OSError("could not enable terminal mode")
            else:
                import termios
                import tty
                self.fd = sys.stdin.fileno()
                self.old_termios = termios.tcgetattr(self.fd)
                tty.setcbreak(self.fd)
            sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
            sys.stdout.flush()
            return self
        except BaseException:
            self.restore()
            raise

    def restore(self):
        try:
            sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
        finally:
            for kernel, handle, mode in reversed(self.saved):
                kernel.SetConsoleMode(handle, mode)
            self.saved.clear()
            if self.fd is not None:
                import termios
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_termios)
                self.fd = None

    def __exit__(self, *args):
        self.restore()

    def size(self):
        try:
            size = os.get_terminal_size(sys.stdout.fileno())
            return max(1, min(1000, size.columns - 1)), max(1, min(500, size.lines))
        except OSError:
            return 99, 40

    def read_key(self):
        if os.name == "nt":
            import msvcrt
            if not msvcrt.kbhit():
                return None
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                return {"K": "left", "M": "right", "H": "up", "P": "down"}.get(msvcrt.getwch(), "")
            return "escape" if key == "\x1b" else key
        import select
        if not select.select([sys.stdin], [], [], 0)[0]:
            return None
        key = os.read(sys.stdin.fileno(), 1).decode("ascii", "ignore")
        if key != "\x1b":
            return key
        sequence = b""
        # A real Esc is distinct from a complete terminal arrow sequence.
        for _ in range(5):
            if not select.select([sys.stdin], [], [], .015)[0]:
                break
            sequence += os.read(sys.stdin.fileno(), 1)
            if sequence[-1:] in (b"A", b"B", b"C", b"D"):
                break
        return {b"[A": "up", b"[B": "down", b"[C": "right", b"[D": "left",
                b"OA": "up", b"OB": "down", b"OC": "right", b"OD": "left"}.get(sequence, "escape")


def compose_screen(state: Explorer, frame: str, width: int, height: int):
    title = f"ASCII TREE EXPLORER  |  {state.mode.upper()}  |  seed {state.seed}  |  {'PLAY' if state.animated else 'PAUSED'}"
    view = f"yaw {state.yaw * 180 / 3.14159265:6.1f}  tilt {state.pitch * 180 / 3.14159265:5.1f}  XW {state.angle4 * 180 / 3.14159265:6.1f}  zoom {state.zoom:.2f}"
    meaning = "4D DATA PROJECTION: XW rotation -> 3D perspective -> ASCII" if state.mode == "4d" else "1:2D  2:3D  3:4D  arrows:orbit  +/-:zoom  Space:play"
    body = frame.splitlines()
    if state.help_visible:
        body = HELP[:]
    lines = [title, view, meaning] + body + [state.message, "H/?:help  G:seed  R:reset  E:export  Q/Esc:quit"]
    return "\x1b[H" + "\r\n".join(line[:width].ljust(width) for line in (lines + [""] * height)[:height])


def run_view(state: Explorer, export_dir: Path) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("view requires an interactive TTY; use: python -m ascii_tree render --seed 42 --mode 3d", file=sys.stderr)
        return 2
    frame = ""
    last_size = None
    dirty = True
    last_tick = time.monotonic()
    last_draw = 0.
    with Terminal() as terminal:
        while state.running:
            now = time.monotonic()
            dt, last_tick = min(.2, now - last_tick), now
            state.advance(dt)
            size = terminal.size()
            if size != last_size:
                dirty = True
                last_size = size
            key = terminal.read_key()
            if key:
                if key.lower() == "e":
                    # Export the exact last displayed raster, even while playing.
                    try:
                        if not frame:
                            frame = render(state.tree, state.options(size[0], max(1, size[1] - 5)))
                        export_dir.mkdir(parents=True, exist_ok=True)
                        path = export_dir / f"tree-{state.seed}-{state.mode}.txt"
                        export_frame(frame, path)
                        rows = frame.splitlines()
                        state.message = f"Saved {path} ({len(rows[0])} x {len(rows)})"
                    except OSError as exc:
                        state.message = f"Export failed: {exc.strerror or str(exc)}"
                else:
                    state.handle(key)
                dirty = True
            if dirty or (state.animated and now - last_draw >= .10):
                width, height = size
                frame = render(state.tree, state.options(width, max(1, height - 5)))
                sys.stdout.write(compose_screen(state, frame, width, height))
                sys.stdout.flush()
                last_draw, dirty = now, False
            time.sleep(.015)
    return 0
