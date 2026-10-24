"""UI state and pure screen composition, independently testable without a TTY."""

from dataclasses import dataclass, field, replace
from pathlib import Path

from .model import Tree, generate_tree
from .render import RenderSettings, render

HELP_LINES = (
    "ONE TREE / THREE VIEWS",
    "",
    "1          2D: fixed XY orthographic view",
    "2          3D: perspective camera + depth buffer",
    "3          4D: XW rotation -> 3D -> 2D projection",
    "",
    "Arrows     Orbit / tilt in 3D and 4D",
    "[ / ]      Rotate XW plane by -/+ 7.5 degrees (4D)",
    "+ / -      Zoom in / out (= also zooms in)",
    "Space      Play / pause breeze and camera animation",
    "G          Next seed (seed + 1); same view settings",
    "R          Reset camera, XW angle, zoom and time",
    "E          Export tree only, ASCII .txt, no ANSI",
    "H / ?      Toggle this help; other keys still work",
    "Q / Esc    Quit (Ctrl+C also restores the terminal)",
    "",
    "W is accumulated growth distance along each branch.",
    "XW rotation mixes X and W, then perspective projects",
    "4 coordinates into 3 and the 3D camera into 2.",
    "This screen is a projection of 4D data.",
    "",
    "Resize freely. Very small windows crop the controls.",
    "Export directory can be set with --export-dir.",
)


@dataclass
class Explorer:
    tree: Tree
    settings: RenderSettings = field(default_factory=RenderSettings)
    playing: bool = False
    help_visible: bool = False
    quitting: bool = False
    message: str = "H / ? for help  |  E saves the current tree frame"
    export_count: int = 0

    def handle_key(self, key: str) -> str | None:
        key = key.lower()
        s = self.settings
        if key in ("q", "escape", "\x03"):
            self.quitting = True
            return "quit"
        if key in ("1", "2", "3"):
            self.settings = replace(s, mode={"1": "2d", "2": "3d", "3": "4d"}[key])
        elif key in ("left", "right") and s.mode != "2d":
            self.settings = replace(s, yaw=(s.yaw + (7.5 if key == "right" else -7.5)) % 360)
        elif key in ("up", "down") and s.mode != "2d":
            self.settings = replace(s, pitch=max(-80, min(80, s.pitch + (5 if key == "up" else -5))))
        elif key in ("[", "]") and s.mode == "4d":
            self.settings = replace(s, angle4d=(s.angle4d + (7.5 if key == "]" else -7.5)) % 360)
        elif key in ("+", "=", "-"):
            self.settings = replace(s, zoom=max(0.15, min(5, s.zoom * (1.12 if key != "-" else 1 / 1.12))))
        elif key == " ":
            self.playing = not self.playing
        elif key == "g":
            self.tree = generate_tree(self.tree.seed + 1)
            self.message = f"New tree: seed {self.tree.seed}"
        elif key == "r":
            self.settings = replace(s, yaw=25, pitch=-8, angle4d=0, zoom=1, time=0)
            self.playing = False
            self.message = "Camera, scale and time reset; animation paused"
        elif key in ("h", "?"):
            self.help_visible = not self.help_visible
        elif key == "e":
            return "export"
        return None

    def tick(self, seconds: float) -> None:
        if not self.playing:
            return
        dt = min(0.25, max(0, seconds))
        s = self.settings
        self.settings = replace(s, time=s.time + dt,
                                yaw=(s.yaw + dt * 12) % 360 if s.mode != "2d" else s.yaw,
                                angle4d=(s.angle4d + dt * 18) % 360 if s.mode == "4d" else s.angle4d)

    def resize(self, columns: int, rows: int) -> None:
        columns, rows = max(1, min(500, columns)), max(1, min(200, rows))
        tree_rows = max(1, rows - (6 if rows >= 9 else 2))
        self.settings = replace(self.settings, width=columns, height=tree_rows)

    def frame(self) -> str:
        return render(self.tree, self.settings)

    def export(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        self.export_count += 1
        path = directory / f"tree-seed{self.tree.seed}-{self.settings.mode}-{self.export_count:03d}.txt"
        # Never overwrite an earlier session's frame.
        while True:
            try:
                with path.open("x", encoding="ascii", newline="\n") as stream:
                    stream.write(self.frame())
                break
            except FileExistsError:
                self.export_count += 1
                path = directory / f"tree-seed{self.tree.seed}-{self.settings.mode}-{self.export_count:03d}.txt"
        self.message = f"Saved: {path.name} ({self.settings.width}x{self.settings.height})"
        return path

    def screen(self, columns: int, rows: int) -> str:
        self.resize(columns, rows)
        s = self.settings
        frame = self.frame().splitlines()
        if self.help_visible:
            frame = list(HELP_LINES[:s.height]) + [""] * max(0, s.height - len(HELP_LINES))
        title = f" ASCII TREE EXPLORER   [{s.mode.upper()}]   seed {self.tree.seed}"
        status = (f" yaw {s.yaw:6.1f}  pitch {s.pitch:5.1f}  XW {s.angle4d:6.1f}  "
                  f"zoom {s.zoom:.2f}  {'PLAYING' if self.playing else 'PAUSED'}")
        explanation = {"2d": " 2D: fixed XY projection of the shared branch graph",
                       "3d": " 3D: perspective / near branches occlude far branches",
                       "4d": " 4D data projection: XW rotation -> 3D -> 2D; W = growth"}[s.mode]
        if rows >= 9:
            lines = [title, status] + frame + [explanation,
                " 1/2/3 modes  Arrows orbit  [/] XW  +/- zoom  Space play/pause",
                " G seed  R reset  E export  H/? help  Q/Esc quit", " " + self.message]
        else:
            lines = [title] + frame + [" H help | Q quit"]
        width, height = max(1, min(500, columns)), max(1, min(200, rows))
        return "\n".join(line[:width].ljust(width) for line in lines[:height])
