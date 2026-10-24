"""UI state is testable without a terminal; changing modes never regenerates it."""
from dataclasses import dataclass, field, replace
from pathlib import Path

from .model import Tree, generate_tree
from .render import View, render_tree


@dataclass
class Explorer:
    seed: int = 42
    view: View = field(default_factory=View)
    playing: bool = False
    help_open: bool = False
    running: bool = True
    message: str = "H: help | E: export | Q: quit"
    tree: Tree = field(init=False)
    export_count: int = 0

    def __post_init__(self) -> None:
        self.tree = generate_tree(self.seed)

    def handle(self, key: str) -> str | None:
        key = key.lower()
        if key in ("q", "esc", "ctrl+c"):
            self.running = False
        elif key in ("1", "2", "3"):
            self.view = replace(self.view, mode={"1": "2d", "2": "3d", "3": "4d"}[key])
        elif key in ("left", "right", "up", "down") and self.view.mode != "2d":
            self.view = replace(self.view,
                                yaw=(self.view.yaw+({"left": -8, "right": 8}.get(key, 0))) % 360,
                                pitch=max(-80., min(80., self.view.pitch+({"up": 6, "down": -6}.get(key, 0)))))
        elif key in ("[", "]") and self.view.mode == "4d":
            self.view = replace(self.view, angle4d=(self.view.angle4d+(-8 if key == "[" else 8)) % 360)
        elif key in ("+", "=", "-"):
            self.view = replace(self.view, zoom=max(.1, min(5., self.view.zoom*(.9 if key == "-" else 1.1))))
        elif key == " ":
            self.playing = not self.playing
        elif key == "g":
            self.seed += 1
            self.tree = generate_tree(self.seed)
            self.message = f"New tree: seed {self.seed}"
        elif key == "r":
            self.view = View(mode=self.view.mode, aspect=self.view.aspect)
            self.message = "Camera, XW angle, wind time and zoom reset"
        elif key in ("h", "?"):
            self.help_open = not self.help_open
        elif key == "e":
            return "export"
        return None

    def tick(self, seconds: float) -> None:
        if self.playing:
            self.view = replace(self.view, yaw=(self.view.yaw+seconds*12) % 360,
                                angle4d=(self.view.angle4d+seconds*9) % 360,
                                time=self.view.time+seconds)

    def export(self, width: int, height: int, directory: Path) -> Path:
        self.export_count += 1
        path = directory/f"tree-{self.seed}-{self.view.mode}-{self.export_count:03d}.txt"
        # Exclusive creation preserves earlier sessions' exports.
        while path.exists():
            self.export_count += 1
            path = directory/f"tree-{self.seed}-{self.view.mode}-{self.export_count:03d}.txt"
        with path.open("x", encoding="ascii", newline="\n") as stream:
            stream.write(render_tree(self.tree, width, height, self.view))
        self.message = f"Saved {path.name} ({width}x{height})"
        return path


HELP = (
    "ASCII TREE EXPLORER / controls",
    "1  2D   2  3D   3  4D   |   same tree, same seed",
    "Arrows: orbit / tilt in 3D and 4D",
    "[ / ]: rotate XW in 4D     + / -: zoom",
    "Space: animate / pause    G: next seed",
    "R: reset view             E: export clean .txt",
    "H / ?: close help         Q / Esc / Ctrl+C: quit",
    "",
    "4D: W stores branch growth, from base to young tips.",
    "XW rotation mixes space and growth. Perspective:",
    "4D -> 3D (W eye) -> 2D (camera) -> ASCII cells.",
    "You see a projection of 4D data, not a 4D screen.",
)


def compose(app: Explorer, width: int, height: int) -> tuple[list[str], tuple[int, int]]:
    """Fit every UI line; reserve the terminal's last column against auto-wrap."""
    width, height = max(1, min(500, width)), max(1, min(250, height))
    if height < 5 or width < 16:
        lines = ["Resize | Q quits"]+[""]*(height-1)
        return [line[:width].ljust(width) for line in lines], (width, max(1, height-3))
    frame_height = height-3
    title = f"ASCII TREE EXPLORER | {app.view.mode.upper()} | seed {app.seed} | {'PLAY' if app.playing else 'PAUSED'}"
    status = (f"yaw {app.view.yaw:.0f}  tilt {app.view.pitch:.0f}  zoom {app.view.zoom:.2f}  "
              + (f"XW {app.view.angle4d:.0f} | 4D -> 3D -> 2D projection" if app.view.mode == "4d" else "H: controls"))
    if app.help_open:
        body = list(HELP[:frame_height])+[""]*max(0, frame_height-len(HELP))
    else:
        body = render_tree(app.tree, width, frame_height, app.view).splitlines()
    lines = [title]+body+[status, app.message]
    return [line[:width].ljust(width) for line in lines], (width, frame_height)
