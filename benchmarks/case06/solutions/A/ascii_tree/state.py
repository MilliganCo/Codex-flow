"""UI state is separate from immutable geometry and terminal I/O."""

from dataclasses import dataclass, field

from .model import Tree, generate_tree
from .render import RenderOptions


@dataclass
class ExplorerState:
    seed: int = 42
    mode: str = "3d"
    yaw: float = -25.0
    pitch: float = 8.0
    angle4: float = 0.0
    plane: str = "xw"
    zoom: float = 1.0
    aspect: float = 0.5
    time: float = 0.0
    animated: bool = False
    help_visible: bool = False
    running: bool = True
    message: str = "H: help | E: export frame"
    tree: Tree = field(init=False)

    def __post_init__(self) -> None:
        self.tree = generate_tree(self.seed)

    def options(self, width: int, height: int) -> RenderOptions:
        return RenderOptions(width, height, self.mode, self.yaw, self.pitch,
                             self.angle4, self.plane, self.zoom, self.aspect, self.time)

    def handle_key(self, key: str) -> str | None:
        """Return an I/O request (export) without performing filesystem operations."""
        key = key.lower()
        if key in ("q", "escape", "\x03"):
            self.running = False
        elif key in ("1", "2", "3"):
            self.mode = {"1": "2d", "2": "3d", "3": "4d"}[key]
            self.help_visible = False
        elif key in ("h", "?"):
            self.help_visible = not self.help_visible
        elif key == " ":
            self.animated = not self.animated
        elif key in ("+", "="):
            self.zoom = min(6.0, self.zoom * 1.12)
        elif key in ("-", "_"):
            self.zoom = max(0.1, self.zoom / 1.12)
        elif key == "r":
            self.yaw, self.pitch, self.angle4, self.zoom, self.time = -25.0, 8.0, 0.0, 1.0, 0.0
            self.animated = False
            self.message = "View reset; tree preserved"
        elif key == "g":
            self.seed += 1
            self.tree = generate_tree(self.seed)
            self.message = f"New tree: seed {self.seed}"
        elif key in ("left", "right", "up", "down") and self.mode != "2d":
            if key in ("left", "right"):
                self.yaw = (self.yaw + (-8 if key == "left" else 8)) % 360
            else:
                self.pitch = max(-85.0, min(85.0, self.pitch + (6 if key == "up" else -6)))
        elif key in ("[", "]") and self.mode == "4d":
            self.angle4 = (self.angle4 + (-8 if key == "[" else 8)) % 360
        elif key == "e":
            return "export"
        return None

    def advance(self, seconds: float) -> None:
        if self.animated and not self.help_visible:
            self.time += seconds
            if self.mode != "2d":
                self.yaw = (self.yaw + seconds * 12) % 360
            if self.mode == "4d":
                self.angle4 = (self.angle4 + seconds * 18) % 360
