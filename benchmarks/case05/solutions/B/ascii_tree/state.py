"""Terminal-independent input state. Only G regenerates the immutable tree."""

from dataclasses import dataclass, field

from .geometry import Camera
from .model import Tree, generate_tree
from .render import render


@dataclass(slots=True)
class Explorer:
    seed: int = 42
    mode: str = "3d"
    yaw: float = 25.0
    pitch: float = -8.0
    angle4d: float = 0.0
    zoom: float = 1.0
    aspect: float = 2.0
    animation_time: float = 0.0
    playing: bool = False
    help_visible: bool = False
    running: bool = True
    message: str = "H: help | G: grow a new tree | E: export"
    tree: Tree = field(init=False)

    def __post_init__(self) -> None:
        self.tree = generate_tree(self.seed)

    def camera(self, width: int, height: int) -> Camera:
        return Camera(width, height, self.mode, self.yaw, self.pitch,
                      self.angle4d, self.zoom, self.aspect, self.animation_time)

    def frame(self, width: int, height: int) -> tuple[str, ...]:
        return render(self.tree, self.camera(width, height))

    def key(self, key: str) -> str | None:
        if key in ("q", "Q", "escape", "\x03"):
            self.running = False
        elif key in ("1", "2", "3"):
            self.mode = {"1": "2d", "2": "3d", "3": "4d"}[key]
        elif key.lower() in ("h", "?"):
            self.help_visible = not self.help_visible
        elif key in ("+", "="):
            self.zoom = min(5.0, self.zoom * 1.1)
        elif key in ("-", "_"):
            self.zoom = max(0.15, self.zoom / 1.1)
        elif key in ("[", "]") and self.mode == "4d":
            self.angle4d = (self.angle4d + (7.5 if key == "]" else -7.5)) % 360
        elif key in ("left", "right", "up", "down") and self.mode != "2d":
            if key in ("left", "right"):
                self.yaw = (self.yaw + (7.5 if key == "right" else -7.5)) % 360
            else:
                self.pitch = max(-85, min(85, self.pitch + (5 if key == "up" else -5)))
        elif key == " ":
            self.playing = not self.playing
        elif key.lower() == "g":
            self.seed += 1
            self.tree = generate_tree(self.seed)
            self.message = f"New tree: seed {self.seed}"
        elif key.lower() == "r":
            self.yaw, self.pitch, self.angle4d, self.zoom = 25.0, -8.0, 0.0, 1.0
            self.animation_time = 0.0
            self.message = "Orientation and zoom reset"
        elif key.lower() == "e":
            return "export"
        return None

    def tick(self, seconds: float) -> None:
        if self.playing:
            self.animation_time += seconds
            if self.mode != "2d":
                self.yaw = (self.yaw + seconds * 12) % 360
            if self.mode == "4d":
                self.angle4d = (self.angle4d + seconds * 9) % 360

    def status(self) -> str:
        return (f"ASCII TREE | {self.mode.upper()} | seed {self.seed} | "
                f"yaw {self.yaw % 360:05.1f} pitch {self.pitch:+05.1f} | "
                f"XW {self.angle4d % 360:05.1f} | zoom {self.zoom:.2f} | "
                f"{'PLAY' if self.playing else 'PAUSE'}")


HELP = (
    "ASCII TREE EXPLORER - HELP",
    "1 / 2 / 3    2D / 3D / 4D (same tree)",
    "Arrows       orbit / tilt camera in 3D and 4D",
    "[ / ]        rotate XW plane in 4D (-/+ 7.5 deg)",
    "+ / -        zoom in / out (= also zooms in)",
    "Space        play / pause (2D wind; 3D/4D rotation)",
    "G            next seed; generate a new tree",
    "R            reset orientation and zoom",
    "E            export visible tree raster as ASCII .txt",
    "H / ?        toggle help; Q / Esc: exit; Ctrl+C: exit",
    "",
    "4D: each point has (x,y,z,w); w is branch birth age.",
    "XW rotation mixes x and w, then 4D -> 3D -> 2D.",
    "The terminal shows a projection of 4D data.",
    "2D: fixed XY view; camera arrows have no effect.",
    "Resize freely. Exports omit help and status lines.",
)
