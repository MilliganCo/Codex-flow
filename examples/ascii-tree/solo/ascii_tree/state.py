"""UI state is separate from immutable procedural geometry and terminal I/O."""

from dataclasses import dataclass, field, replace

from .model import Tree, generate_tree
from .renderer import RenderOptions

MODES = {"1": "2d", "2": "3d", "3": "4d"}


@dataclass(slots=True)
class ExplorerState:
    tree: Tree
    options: RenderOptions = field(default_factory=RenderOptions)
    playing: bool = False
    help_visible: bool = False
    running: bool = True
    status: str = "Ready. H opens the field guide."

    def handle_key(self, key: str) -> str | None:
        """Apply one logical key; return an export intent for the I/O layer."""
        key = key.lower()
        o = self.options
        if key in MODES:
            self.options = replace(o, mode=MODES[key])
            self.status = f"Same tree, {self.options.mode.upper()} projection."
        elif key in ("q", "escape", "\x1b"):
            self.running = False
        elif key in ("h", "?"):
            self.help_visible = not self.help_visible
        elif key == " ":
            self.playing = not self.playing
        elif key in ("+", "="):
            self.options = replace(o, zoom=min(5.0, o.zoom * 1.12))
        elif key == "-":
            self.options = replace(o, zoom=max(.15, o.zoom / 1.12))
        elif key in ("left", "right", "up", "down"):
            if o.mode == "2d":
                self.status = "2D is a fixed XY view. Press 2 or 3 to orbit."
            else:
                self.options = replace(o, yaw=(o.yaw + {"left": -7, "right": 7}.get(key, 0)) % 360,
                                       pitch=max(-80, min(80, o.pitch + {"up": 5, "down": -5}.get(key, 0))))
        elif key in ("[", "]", ",", "."):
            if o.mode == "4d":
                self.options = replace(o, angle4=(o.angle4 + (7 if key in ("]", ".") else -7)) % 360)
            else:
                self.status = "Press 3 for 4D, then [ / ] to rotate with W."
        elif key == "g":
            self.tree = generate_tree(self.tree.seed + 1)
            self.status = f"Grew a new tree. Seed {self.tree.seed}."
        elif key == "r":
            self.options = replace(o, yaw=-20, pitch=8, angle4=0, zoom=1, time=0)
            self.status = "Orientation, time and zoom reset."
        elif key == "e":
            return "export"
        return None

    def tick(self, seconds: float) -> None:
        if self.playing:
            self.options = replace(self.options, time=self.options.time + max(0, seconds))

    def viewport(self, width: int, height: int) -> RenderOptions:
        return replace(self.options, width=width, height=height)
