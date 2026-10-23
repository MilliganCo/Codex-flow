"""Application state is independent of the console, including every hotkey."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .model import Tree, generate_tree
from .render import RenderOptions, render_lines


HELP = (
    "CONTROLS / press H or ? to return",
    "",
    "1  2D front elevation (orthographic)",
    "2  3D perspective / 3  4D projection",
    "Arrows or WASD  orbit / tilt in 3D and 4D",
    "[ / ]  rotate XW by 7.5 degrees in 4D",
    "+ / -  zoom (= also zooms in)",
    "Space  play / pause; 2D sways, 3D orbits",
    "4D animation also rotates the XW plane",
    "G  next seed / R  reset camera and zoom",
    "E  export tree raster, without this UI",
    "Q / Esc  exit / Ctrl+C  stop safely",
    "",
    "WHAT IS 4D?",
    "Every vertex has X,Y,Z,W coordinates.",
    "W records distance along the growth graph.",
    "X' = X*cos(a) - W*sin(a)",
    "W' = X*sin(a) + W*cos(a)",
    "4D -> perspective 3D -> terminal 2D.",
    "Change [ / ] to mix growth with space.",
    "The same tree survives all mode switches.",
)


@dataclass(slots=True)
class Explorer:
    seed: int = 42
    mode: str = "3d"
    yaw: float = 28.0
    pitch: float = -8.0
    angle4: float = 0.0
    zoom: float = 1.0
    aspect: float = 2.0
    elapsed: float = 0.0
    export_dir: Path = field(default_factory=lambda: Path("exports"))
    tree: Tree = field(init=False)
    playing: bool = False
    help_visible: bool = False
    running: bool = True
    message: str = "H help | E export a clean frame | Q quit"
    last_frame: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.tree = generate_tree(self.seed)

    def options(self, width: int, height: int) -> RenderOptions:
        return RenderOptions(width, height, self.mode, self.yaw, self.pitch, self.angle4,
                             self.zoom, self.aspect, self.elapsed)

    def handle_key(self, key: str) -> bool:
        """Return whether a redraw is useful. No hidden random regeneration."""
        if not key:
            return False
        key = key.lower()
        if key in ("q", "esc", "ctrl+c"):
            self.running = False
        elif key in ("1", "2", "3"):
            self.mode = {"1": "2d", "2": "3d", "3": "4d"}[key]
        elif key in ("h", "?"):
            self.help_visible = not self.help_visible
        elif key == " ":
            self.playing = not self.playing
        elif key in ("+", "=", "-", "_"):
            factor = 1.12 if key in ("+", "=") else 1 / 1.12
            self.zoom = max(0.1, min(8, self.zoom * factor))
        elif key in ("left", "right", "up", "down", "a", "d", "w", "s"):
            if self.mode == "2d":
                self.message = "2D is a fixed front elevation; use 2 or 3 to orbit."
            elif key in ("left", "a", "right", "d"):
                self.yaw = (self.yaw + (-7.5 if key in ("left", "a") else 7.5)) % 360
            else:
                self.pitch = max(-85, min(85, self.pitch + (5 if key in ("up", "w") else -5)))
        elif key in ("[", "]"):
            if self.mode == "4d":
                self.angle4 = (self.angle4 + (7.5 if key == "]" else -7.5)) % 360
            else:
                self.message = "Press 3 for 4D, then [ / ] to rotate the XW plane."
        elif key == "g":
            self.seed += 1
            self.tree = generate_tree(self.seed)
            self.message = f"New tree: seed {self.seed}"
        elif key == "r":
            self.yaw, self.pitch, self.angle4, self.zoom, self.elapsed = 28.0, -8.0, 0.0, 1.0, 0.0
            self.message = "Camera, XW rotation, wind and zoom reset."
        elif key == "e":
            try:
                path = self.export_frame()
                self.message = f"Saved {path}"
            except OSError as exc:
                self.message = f"Export failed: {exc}"
        else:
            return False
        return True

    def advance(self, seconds: float) -> None:
        if not self.playing:
            return
        self.elapsed += seconds
        if self.mode != "2d":
            self.yaw = (self.yaw + seconds * 12) % 360
        if self.mode == "4d":
            self.angle4 = (self.angle4 + seconds * 14) % 360

    def export_frame(self) -> Path:
        if not self.last_frame:
            self.last_frame = render_lines(self.tree, self.options(100, 34))
        self.export_dir.mkdir(parents=True, exist_ok=True)
        data = ("\n".join(self.last_frame) + "\n").encode("ascii")
        # Exclusive creation prevents accidental replacement of an earlier export.
        for number in range(1, 10001):
            path = self.export_dir / f"tree-{self.seed}-{self.mode}-{number:04d}.txt"
            try:
                with path.open("xb") as stream:
                    stream.write(data)
                return path
            except FileExistsError:
                continue
        raise OSError("10000 exports with this name already exist")

    def screen(self, columns: int, rows: int) -> tuple[str, ...]:
        # Leave the terminal's final column and row untouched to prevent scrolling.
        width = max(1, min(500, columns - 1))
        height = max(1, min(200, rows - 1))
        chrome = 6 if height >= 10 else 2
        canvas_height = max(1, height - chrome)
        self.last_frame = render_lines(self.tree, self.options(width, canvas_height))
        canvas = list(self.last_frame)
        if self.help_visible:
            # On tiny screens show the most useful controls first; no out-of-range writes.
            for i in range(len(canvas)):
                canvas[i] = ("  " + HELP[i]) if i < len(HELP) else ""
        title = f" ASCII TREE EXPLORER  /  {self.mode.upper()}  /  SEED {self.seed}  /  {'PLAYING' if self.playing else 'PAUSED'}"
        if height < 10:
            lines = [f"{self.mode.upper()} seed={self.seed}"] + canvas + ["1/2/3 H Q +/-"]
        else:
            description = {
                "2d": " Front elevation / one connected XYZ tree / orthographic projection",
                "3d": " XYZ perspective / camera orbit / depth-tested wood and foliage",
                "4d": " 4D data -> XW rotation -> 3D -> 2D | W = growth distance",
            }[self.mode]
            stats = (f" yaw {self.yaw:6.1f}  tilt {self.pitch:+5.1f}  XW {self.angle4:6.1f}"
                     f"  zoom {self.zoom:.2f}x  |  {len(self.tree.segments)} branches")
            keys = " 1 2D | 2 3D | 3 4D | arrows orbit | [ ] XW | +/- zoom | Space play | H help"
            lines = [title, description, "-" * width] + canvas + [stats, keys, " " + self.message]
        return tuple(line[:width].ljust(width) for line in lines[:height])
