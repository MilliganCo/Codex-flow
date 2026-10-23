"""Interactive application and compact ASCII-only interface."""

from pathlib import Path
import time

from .render import render_tree
from .state import ExplorerState
from .terminal import Terminal


HELP = (
    "ASCII TREE EXPLORER / HELP",
    "",
    "1 2D   2 3D   3 4D    Same tree, different projections",
    "Arrows     Orbit / tilt camera in 3D and 4D",
    "[ / ]      Rotate W with X, Y or Z in 4D (8 degrees)",
    "+ / -      Zoom in / out   (= also zooms in)",
    "Space      Animate / pause (breeze + camera orbit)",
    "G          Generate next seed",
    "R          Reset camera, zoom, time; pause",
    "E          Export visible tree canvas as ASCII .txt",
    "H / ?      Toggle this help; animation pauses here",
    "Q / Esc    Exit (Ctrl+C also restores the terminal)",
    "",
    "4D: vertices have (x,y,z,w); W = growth distance.",
    "True plane rotation mixes W with a spatial axis.",
    "Perspective 4D -> 3D -> terminal; this is a projection.",
    "Use --plane xw|yw|zw on startup (default: xw).",
    "2D: fixed orthographic XY view; Space adds a breeze.",
)


def canvas_size(width: int, height: int) -> tuple[int, int]:
    return width, max(1, height - 5)


def compose_screen(state: ExplorerState, width: int, height: int, frame: str) -> str:
    if width < 28 or height < 10:
        lines = [f"TREE {state.mode.upper()} seed {state.seed}", "Small terminal", "Resize for full UI", "1/2/3 modes  H help", "Q / Esc: exit"]
        if state.help_visible:
            lines = ["HELP (resize to read)", "1/2/3: 2D/3D/4D", "Arrows: orbit", "[]: 4D  +/-: zoom", "Space: animate", "G: seed R: reset", "E: export H: help", "Q/Esc: exit"]
    else:
        title = f" ASCII TREE EXPLORER   seed {state.seed}   [1] 2D  [2] 3D  [3] 4D"
        info = (f" {state.mode.upper()} | yaw {state.yaw % 360:5.1f}  pitch {state.pitch:+5.1f}"
                f" | zoom {state.zoom:.2f}x | {'PLAY' if state.animated else 'PAUSED'}")
        if state.mode == "4d":
            info = f" 4D -> 3D -> terminal | {state.plane.upper()} {state.angle4 % 360:5.1f} deg | zoom {state.zoom:.2f}x | {'PLAY' if state.animated else 'PAUSED'}"
        lines = [title, info] + frame.splitlines()
        lines += ["-" * width,
                  " Arrows orbit  [] 4D  +/- zoom  Space play  G seed  R reset  E save  H help  Q exit",
                  " " + state.message]
        lines += [""] * max(0, height - len(lines))
        if state.help_visible:
            box_width = min(66, width - 4)
            help_lines = HELP
            if height < len(HELP) + 2:
                help_lines = (
                    "HELP | H close | Q/Esc exit",
                    "1/2/3: 2D / 3D / 4D",
                    "Arrows: orbit / tilt (3D/4D)",
                    "[ / ]: 4D plane angle",
                    "+/- zoom | Space animate",
                    "G seed | R reset | E export",
                    "4D = (x,y,z,w) -> 3D -> 2D",
                    "W: branch growth distance",
                )
            content = ["+" + "-" * (box_width - 2) + "+"]
            content += ["| " + line[:box_width - 4].ljust(box_width - 4) + " |" for line in help_lines]
            content += ["+" + "-" * (box_width - 2) + "+"]
            top = max(0, (height - len(content)) // 2)
            left = (width - box_width) // 2
            # Scroll-free help on shorter windows: the essential controls go first.
            for index, line in enumerate(content[:height]):
                row = top + index
                if row >= height:
                    break
                base = lines[row].ljust(width)
                lines[row] = base[:left] + line + base[left + box_width:]
    return "\n".join((lines[row] if row < len(lines) else "")[:width].ljust(width)
                     for row in range(height)) + "\n"


def export_frame(directory: Path, state: ExplorerState, width: int, height: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    prefix = f"tree_seed{state.seed}_{state.mode}"
    index = 1
    data = render_tree(state.tree, state.options(width, height)).encode("ascii")
    while True:
        path = directory / f"{prefix}_{index:03d}.txt"
        try:
            with path.open("xb") as output:
                output.write(data)
            return path
        except FileExistsError:
            index += 1


def run_view(state: ExplorerState, export_dir: Path = Path("exports"),
             terminal=None, clock=time.monotonic) -> int:
    """The same loop supports the real terminal and a finite scripted test driver."""
    terminal = terminal if terminal is not None else Terminal()
    with terminal:
        previous = clock()
        last_render = -1e9
        old_size = None
        dirty = True
        while state.running:
            now = clock()
            seconds = min(0.25, max(0, now - previous))
            previous = now
            state.advance(seconds)
            size = terminal.size()
            if size != old_size:
                dirty = True
                old_size = size
            width, height = size
            cw, ch = canvas_size(width, height)
            if dirty or (state.animated and not state.help_visible and now - last_render >= 1 / 12):
                frame = render_tree(state.tree, state.options(cw, ch))
                terminal.draw(compose_screen(state, width, height, frame))
                dirty = False
                last_render = now
            keys = terminal.read_keys(0.025)
            for key in keys:
                request = state.handle_key(key)
                dirty = True
                if request == "export":
                    try:
                        path = export_frame(export_dir, state, cw, ch)
                        state.message = f"Saved {path.as_posix()} ({cw}x{ch})"
                    except OSError as error:
                        state.message = f"Export failed: {error.strerror or type(error).__name__}"
                if not state.running:
                    break
    return 0
