"""Input and animation state, kept separate from the console and renderer."""

from dataclasses import dataclass, field
from pathlib import Path

from .geometry import Tree, generate_tree
from .projection import View
from .render import Frame, render_tree


@dataclass
class Explorer:
    seed: int = 42
    view: View = field(default_factory=View)
    export_dir: Path = field(default_factory=lambda: Path("exports"))
    tree: Tree = field(init=False)
    running: bool = True
    animated: bool = False
    help_open: bool = False
    message: str = "H: help  |  Space: animate  |  Q: quit"
    export_number: int = 0
    last_frame: Frame | None = None

    def __post_init__(self) -> None:
        self.tree = generate_tree(self.seed)

    def change_view(self, **changes: float | str) -> None:
        from dataclasses import replace
        self.view = replace(self.view, **changes)

    def advance(self, seconds: float) -> None:
        if self.animated:
            if self.view.mode == "4d":
                self.change_view(angle4d=(self.view.angle4d + 24 * seconds) % 360,
                                 yaw=(self.view.yaw + 9 * seconds) % 360)
            elif self.view.mode == "3d":
                self.change_view(yaw=(self.view.yaw + 24 * seconds) % 360)

    def draw(self, width: int, height: int) -> Frame:
        self.last_frame = render_tree(self.tree, width, height, self.view)
        return self.last_frame

    def key(self, key: str) -> None:
        key = key.lower()
        if key in {"q", "escape", "ctrl+c"}:
            self.running = False
        elif key in {"1", "2", "3"}:
            self.change_view(mode={"1": "2d", "2": "3d", "3": "4d"}[key])
            self.message = ("4D DATA -> XW rotation -> 3D -> terminal projection"
                            if key == "3" else "Same tree; arrows orbit in 3D / 4D")
        elif key in {"h", "?"}:
            self.help_open = not self.help_open
        elif key in {"left", "right"} and self.view.mode != "2d":
            self.change_view(yaw=(self.view.yaw + (8 if key == "right" else -8)) % 360)
        elif key in {"up", "down"} and self.view.mode != "2d":
            self.change_view(pitch=max(-80, min(80, self.view.pitch + (6 if key == "up" else -6))))
        elif key in {"[", "]"} and self.view.mode == "4d":
            self.change_view(angle4d=(self.view.angle4d + (8 if key == "]" else -8)) % 360)
        elif key in {"+", "=", "-"}:
            self.change_view(zoom=max(0.1, min(8, self.view.zoom * (1 / 1.15 if key == "-" else 1.15))))
        elif key == " ":
            self.animated = not self.animated
            self.message = ("Animation: orbit in 3D, orbit + XW rotation in 4D"
                            if self.animated else "Animation paused")
        elif key == "r":
            self.view = View(mode=self.view.mode, aspect=self.view.aspect)
            self.animated = False
            self.message = "Orientation and zoom reset; seed preserved"
        elif key == "g":
            self.seed += 1
            self.tree = generate_tree(self.seed)
            self.message = f"New tree: seed {self.seed}"
        elif key == "e":
            if self.last_frame is None:
                self.message = "No frame yet"
                return
            try:
                self.export_dir.mkdir(parents=True, exist_ok=True)
                # Exclusive creation protects previous frames, even across sessions.
                while True:
                    self.export_number += 1
                    path = self.export_dir / f"tree_{self.seed}_{self.view.mode}_{self.export_number:03}.txt"
                    try:
                        with path.open("xb") as stream:
                            stream.write(self.last_frame.to_bytes())
                        break
                    except FileExistsError:
                        continue
                self.message = f"Saved {path}"
            except OSError as exc:
                self.message = f"Export failed: {exc.strerror or str(exc)}"
