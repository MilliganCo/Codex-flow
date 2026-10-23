"""UI state machine, independent of console input/output for finite tests."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from .model import Tree, generate_tree
from .render import RenderOptions, animated_angle, render

HELP = (
    "ASCII TREE EXPLORER / HELP",
    "",
    "1 2D   2 3D   3 4D     (same tree / same seed)",
    "Arrows: orbit / tilt in 3D and 4D",
    "[ / ]: rotate XW in 4D (mix space and branch age)",
    "+ / -: zoom     Space: animate / pause",
    "G: next seed    R: reset view, zoom and animation time",
    "E: export visible tree raster to a plain ASCII .txt",
    "H / ?: close help     Q / Esc / Ctrl+C: quit",
    "",
    "2D: orthographic XY view of the shared XYZ tree.",
    "3D: XYZ camera perspective with a depth buffer.",
    "4D: W = developmental distance along each branch.",
    "Rotate XW, project 4D -> 3D, then camera -> 2D.",
    "This terminal displays a projection of 4D data.",
    "",
    "Animation: orbit in 3D; orbit + XW rotation in 4D.",
    "2D remains still. Export never includes this help.",
    "For tiny windows, enlarge the terminal to read help.",
)


@dataclass
class Explorer:
    options: RenderOptions = field(default_factory=RenderOptions)
    seed: int = 42
    export_dir: Path = field(default_factory=lambda: Path("exports"))
    tree: Tree = field(init=False)
    running: bool = True
    animated: bool = False
    help_open: bool = False
    status: str = "H: help | E: export | Q: quit"
    last_frame: str = ""
    exports: int = 0

    def __post_init__(self) -> None:
        self.tree = generate_tree(self.seed)

    def handle(self, key: str) -> bool:
        """Return whether the display needs redrawing."""
        lower = key.lower()
        o = self.options
        if lower in ("q", "escape", "ctrl+c"):
            self.running = False
        elif lower in ("h", "?"):
            self.help_open = not self.help_open
        elif key in ("1", "2", "3"):
            self.options = replace(o, mode={"1": "2d", "2": "3d", "3": "4d"}[key])
        elif key in ("left", "right", "up", "down") and o.mode != "2d":
            yaw = o.yaw + ({"left": -8, "right": 8}.get(key, 0))
            pitch = o.pitch + ({"up": -6, "down": 6}.get(key, 0))
            self.options = replace(o, yaw=yaw % 360, pitch=max(-80, min(80, pitch)))
        elif key in ("[", "]") and o.mode == "4d":
            self.options = replace(o, angle4d=(o.angle4d + (8 if key == "]" else -8)) % 360)
        elif key in ("+", "=", "-"):
            zoom = o.zoom * (1 / 1.12 if key == "-" else 1.12)
            self.options = replace(o, zoom=max(0.15, min(5.0, zoom)))
        elif key == " ":
            self.animated = not self.animated
        elif lower == "g":
            self.seed = (self.seed + 1) % (2 ** 32)
            self.tree = generate_tree(self.seed)
            self.status = f"New tree: seed {self.seed}"
        elif lower == "r":
            self.options = replace(o, yaw=25, pitch=-8, angle4d=0, zoom=1, time=0)
            self.animated = False
            self.status = "View reset; animation paused"
        elif lower == "e":
            try:
                self.last_frame = render(self.tree, self.options)
                self.export_dir.mkdir(parents=True, exist_ok=True)
                # Do not overwrite a previous session's export.
                while True:
                    self.exports += 1
                    path = self.export_dir / f"tree-{self.seed}-{o.mode}-{self.exports:03d}.txt"
                    try:
                        with path.open("xb") as stream:
                            stream.write(self.last_frame.encode("ascii"))
                        break
                    except FileExistsError:
                        continue
                self.status = f"Saved {path}"
            except OSError as error:
                self.status = f"Export failed: {error.strerror or type(error).__name__}"
        else:
            return False
        return True

    def tick(self, seconds: float) -> None:
        if self.animated and not self.help_open and self.options.mode != "2d":
            # Clamp a stalled event loop; all angle calculations are periodic.
            self.options = replace(self.options, time=self.options.time + max(0, min(seconds, 0.25)))

    def screen(self, columns: int, rows: int) -> str:
        width, height = max(1, min(columns - 1, 1000)), max(1, min(rows - 1, 1000))
        body_height = max(1, height - 4)
        self.options = replace(self.options, width=width, height=body_height)
        self.last_frame = render(self.tree, self.options)
        o = self.options
        state = "PLAY" if self.animated else "PAUSE"
        header = f"{o.mode.upper()} | ASCII TREE EXPLORER | seed {self.seed} | {state} | zoom {o.zoom:.2f}"
        if o.mode == "4d":
            info = f"4D data -> 3D -> 2D | XW {animated_angle(o.angle4d, 8, o.time):5.1f} deg | W = branch age"
        elif o.mode == "3d":
            info = f"XYZ perspective | yaw {animated_angle(o.yaw, 12, o.time):5.1f} | pitch {o.pitch:.1f} | depth buffer"
        else:
            info = "XY orthographic projection | same procedural tree | + / - zoom"
        body = list(HELP) if self.help_open else self.last_frame.splitlines()
        body = (body + [""] * body_height)[:body_height]
        lines = [header, info, *body,
                 "1:2D 2:3D 3:4D | Arrows:orbit [ ]:XW +/-:zoom Space:play G:new R:reset",
                 self.status]
        # Every printable UI cell is ASCII, including OS error/path messages.
        return "\n".join(line.encode("ascii", "replace").decode("ascii")[:width].ljust(width)
                         for line in lines[:height])
