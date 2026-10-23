"""Input state shared by the real terminal and finite event tests."""
from dataclasses import dataclass, field
import math
from .model import Tree, generate_tree
from .render import RenderOptions


@dataclass
class Explorer:
    seed: int = 42
    mode: str = "3d"
    yaw: float = .45
    pitch: float = .08
    angle4: float = 0.
    zoom: float = 1.
    aspect: float = .5
    animated: bool = False
    help_visible: bool = False
    running: bool = True
    message: str = "H: help | E: save frame | Q: quit"
    tree: Tree = field(init=False)

    def __post_init__(self):
        self.tree = generate_tree(self.seed)

    def handle(self, key: str):
        key = key.lower()
        if key in ("q", "escape", "\x03"):
            self.running = False
        elif key in ("1", "2", "3"):
            self.mode = {"1": "2d", "2": "3d", "3": "4d"}[key]
        elif key in ("h", "?"):
            self.help_visible = not self.help_visible
        elif key == " ":
            self.animated = not self.animated
        elif key == "g":
            self.seed += 1
            self.tree = generate_tree(self.seed)
            self.message = f"New tree: seed {self.seed}"
        elif key == "r":
            self.yaw, self.pitch, self.angle4, self.zoom = .45, .08, 0., 1.
        elif key in ("+", "="):
            self.zoom = min(8., self.zoom * 1.12)
        elif key == "-":
            self.zoom = max(.1, self.zoom / 1.12)
        elif key == "left" and self.mode != "2d":
            self.yaw -= .12
        elif key == "right" and self.mode != "2d":
            self.yaw += .12
        elif key == "up" and self.mode != "2d":
            self.pitch = min(1.4, self.pitch + .10)
        elif key == "down" and self.mode != "2d":
            self.pitch = max(-1.4, self.pitch - .10)
        elif key in ("[", "]") and self.mode == "4d":
            self.angle4 += .12 if key == "]" else -.12
        self.yaw = math.remainder(self.yaw, math.tau)
        self.angle4 = math.remainder(self.angle4, math.tau)

    def advance(self, dt: float):
        if self.animated:
            if self.mode == "4d":
                self.angle4 = math.remainder(self.angle4 + dt * .27, math.tau)
            elif self.mode == "3d":
                self.yaw = math.remainder(self.yaw + dt * .32, math.tau)
            # 2D remains a stable orthographic study. Space state is retained.

    def options(self, width, height):
        return RenderOptions(width, height, self.mode, self.yaw, self.pitch,
                             self.angle4, self.zoom, self.aspect)
