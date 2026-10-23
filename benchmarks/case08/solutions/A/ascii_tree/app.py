"""Interactive state and ASCII UI, independent of console input/output."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from .geometry import Tree, generate_tree
from .render import RenderOptions, frame_bytes, render_frame

HELP = (
    "ASCII TREE EXPLORER / HELP",
    "",
    "1  2D front     2  3D camera     3  4D projection",
    "Arrow keys      Orbit / tilt the camera in 3D and 4D",
    "[ / ]           Rotate XW by 8 degrees (4D mode)",
    "+ / -           Zoom in / out   (= also zooms in)",
    "Space           Play / pause camera and XW animation",
    "G               Grow next seed (current seed + 1)",
    "R               Reset orientation, zoom and animation time",
    "E               Export only the image to a plain ASCII .txt",
    "H / ?           Open / close this help",
    "Q / Esc         Quit (Ctrl+C also restores the terminal)",
    "",
    "4D: every vertex has (x, y, z, w). W is emergence along",
    "the growth path. [ ] mix X and W with a true rotation.",
    "The screen shows a 4D -> 3D -> 2D perspective projection.",
    "2D uses the SAME tree, seen orthographically from the front.",
    "Export is deterministic; no color or UI enters the file.",
    "",
    "Press H or ? to return. In tiny windows use Q to exit.",
)


@dataclass(slots=True)
class ExplorerState:
    settings: RenderOptions = field(default_factory=RenderOptions)
    seed: int = 42
    export_dir: Path = field(default_factory=lambda: Path("exports"))
    tree: Tree = field(init=False)
    playing: bool = False
    help_visible: bool = False
    quit: bool = False
    message: str = "H: help | G: next seed | E: export"

    def __post_init__(self) -> None:
        self.tree = generate_tree(self.seed)

    def options(self, width: int, height: int) -> RenderOptions:
        return replace(self.settings, width=max(1, min(500, width)),
                       height=max(1, min(200, height)))

    def tick(self, elapsed: float) -> bool:
        if not self.playing or self.help_visible:
            return False
        self.settings = replace(self.settings, time=self.settings.time + min(0.25, max(0, elapsed)))
        return True

    def export(self, width: int, height: int) -> Path:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        payload = frame_bytes(self.tree, self.options(width, height))
        # Exclusive creation preserves earlier exports and user's files.
        for number in range(1, 10001):
            path = self.export_dir / f"tree-{self.seed}-{self.settings.mode}-{number:04d}.txt"
            try:
                with path.open("xb") as stream:
                    stream.write(payload)
                return path
            except FileExistsError:
                continue
        raise OSError("export directory already contains 10000 frames for this seed/mode")

    def handle_key(self, key: str, width: int = 100, height: int = 40) -> bool:
        o = self.settings
        key = key.lower()
        if key in ("q", "escape", "ctrl-c"):
            self.quit = True
        elif key in ("h", "?"):
            self.help_visible = not self.help_visible
        elif key in ("1", "2", "3"):
            self.settings = replace(o, mode={"1": "2d", "2": "3d", "3": "4d"}[key])
        elif key in ("left", "right") and o.mode != "2d":
            self.settings = replace(o, yaw=(o.yaw + (8 if key == "right" else -8)) % 360)
        elif key in ("up", "down") and o.mode != "2d":
            self.settings = replace(o, pitch=max(-80, min(80, o.pitch + (6 if key == "up" else -6))))
        elif key in ("[", "]") and o.mode == "4d":
            self.settings = replace(o, angle4=(o.angle4 + (8 if key == "]" else -8)) % 360)
        elif key in ("+", "=", "-"):
            self.settings = replace(o, zoom=max(0.1, min(8.0, o.zoom * (1.15 if key != "-" else 1 / 1.15))))
        elif key == " ":
            self.playing = not self.playing
        elif key == "g":
            self.seed += 1
            self.tree = generate_tree(self.seed)
            self.message = f"Grew seed {self.seed}; orientation preserved"
        elif key == "r":
            self.settings = replace(o, yaw=25.0, pitch=-7.0, angle4=0.0, zoom=1.0, time=0.0)
            self.message = "View reset"
        elif key == "e":
            try:
                path = self.export(width, height)
                self.message = f"Saved {path} ({width}x{height}, ASCII)"
            except OSError as exc:
                self.message = f"Export failed: {exc}"
        else:
            return False
        return True


def image_size(columns: int, rows: int) -> tuple[int, int]:
    """Reserve one column against terminal autowrap and four UI rows."""
    ui_rows = 1 if columns < 36 or rows < 10 else 4
    return max(1, min(500, columns - 1)), max(1, min(200, rows - ui_rows))


def compose_screen(state: ExplorerState, columns: int, rows: int) -> tuple[str, ...]:
    width, height = image_size(columns, rows)
    rows = max(1, min(204, rows))
    o = state.settings
    if state.help_visible:
        lines = list(HELP)
    elif columns < 36 or rows < 10:
        # Still useful at a minimum size; no negative layout calculations.
        lines = [f"{o.mode.upper()} seed={state.seed} Q:quit H:help"]
        lines.extend(render_frame(state.tree, state.options(width, height)))
    else:
        effective_yaw = (o.yaw % 360 + (o.time % 30) * 12) % 360
        effective_xw = (o.angle4 % 360 + (o.time % 22.5) * 16) % 360
        lines = [f"ASCII TREE EXPLORER | 1:2D  2:3D  3:4D | [{o.mode.upper()}] seed {state.seed}",
                 f"{'PLAY' if state.playing else 'PAUSED'}  zoom {o.zoom:.2f}  yaw {effective_yaw:.0f}  "
                 f"tilt {o.pitch:.0f}  XW {effective_xw:.0f} deg  | "
                 + ("4D data -> 3D -> 2D" if o.mode == "4d" else "One tree / three projections")]
        lines.extend(render_frame(state.tree, state.options(width, height)))
        lines.extend(["Arrows:orbit  [ ]:XW  +/-:zoom  Space:play  G:seed  R:reset  E:save  H:help  Q:quit",
                      state.message])
    # ASCII even when an OS error message or export path contains Unicode.
    clean = [line.encode("ascii", errors="replace").decode("ascii")[:width].ljust(width)
             for line in lines[:rows]]
    return tuple(clean + [" " * width] * (rows - len(clean)))
