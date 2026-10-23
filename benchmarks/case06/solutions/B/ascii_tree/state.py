"""Input-independent explorer state; switching mode never regenerates geometry."""

from dataclasses import dataclass, replace
from pathlib import Path

from .model import Tree, generate_tree
from .render import RenderOptions, render_tree


@dataclass(slots=True)
class Explorer:
    tree: Tree
    options: RenderOptions
    animated: bool = False
    help_open: bool = False
    quit: bool = False
    export_requested: bool = False
    message: str = "H help  |  Space animate  |  E export"

    def key(self, key: str) -> bool:
        key = key.lower()
        changes = {}
        if key in ("q", "escape", "ctrl-c"):
            self.quit = True
        elif key in ("1", "2", "3"):
            changes["mode"] = {"1": "2d", "2": "3d", "3": "4d"}[key]
            self.message = "Same seed, same branch graph."
        elif key in ("left", "right", "up", "down"):
            if self.options.mode == "2d":
                self.message = "2D is a fixed front elevation. Press 2 for the 3D camera."
            elif key in ("left", "right"):
                changes["yaw"] = (self.options.yaw + (8 if key == "right" else -8)) % 360
            else:
                changes["pitch"] = max(-80, min(80, self.options.pitch + (6 if key == "up" else -6)))
        elif key in ("[", "]"):
            if self.options.mode == "4d":
                changes["angle4d"] = (self.options.angle4d + (8 if key == "]" else -8)) % 360
            else:
                self.message = "Press 3 for 4D, then [ / ] to rotate XW."
        elif key in ("+", "=", "-", "_"):
            changes["zoom"] = max(0.15, min(5, self.options.zoom * (1.12 if key in ("+", "=") else 1 / 1.12)))
        elif key == " ":
            self.animated = not self.animated
            self.message = "Animation running" if self.animated else "Animation paused"
        elif key == "g":
            self.tree = generate_tree(self.tree.seed + 1)
            self.message = f"Grew seed {self.tree.seed}. Press G for the next seed."
        elif key == "r":
            changes.update(yaw=25.0, pitch=-7.0, angle4d=0.0, zoom=1.0, time=0.0)
            self.animated = False
            self.message = "Orientation, time and zoom reset."
        elif key in ("h", "?"):
            self.help_open = not self.help_open
        elif key == "e":
            self.export_requested = True
        elif key == "b":
            changes["foliage"] = not self.options.foliage
        else:
            return False
        if changes:
            self.options = replace(self.options, **changes)
        return True

    def advance(self, seconds: float) -> bool:
        if self.animated and not self.help_open and seconds > 0:
            self.options = replace(self.options, time=self.options.time + min(seconds, 0.25))
            return self.options.mode != "2d"
        return False

    def export(self, directory: Path, frame: str) -> Path:
        # Exclusive creation protects earlier exports; exact currently visible raster.
        directory.mkdir(parents=True, exist_ok=True)
        stem = f"tree-{self.tree.seed}-{self.options.mode}"
        for index in range(1, 10001):
            path = directory / f"{stem}-{index:04d}.txt"
            try:
                with path.open("xb") as stream:
                    stream.write(frame.encode("ascii"))
                return path
            except FileExistsError:
                continue
        raise OSError("export directory already has 10000 frames for this seed/mode")


HELP = (
    "ASCII TREE EXPLORER / FIELD GUIDE",
    "",
    "1  2D elevation    2  3D camera    3  4D projection",
    "Arrow keys: orbit / tilt in 3D and 4D",
    "[ / ]: rotate the XW hyperplane in 4D",
    "+ / -: zoom (also = / _)    Space: animate / pause",
    "G: next seed    R: reset view    B: foliage on / off",
    "E: export current tree raster to a plain ASCII .txt",
    "H / ?: close help    Q / Esc: quit    Ctrl+C: quit",
    "",
    "One immutable branch graph is shared by all modes.",
    "W records growth-path age. XW rotation mixes X with W.",
    "4D points -> XW rotation -> 4D perspective -> 3D camera",
    "-> 2D terminal. This is a projection of 4D data.",
    "",
    "Tip: pause, press 3, then ] several times. Branches",
    "move differently because their W coordinates differ.",
    "Windows Terminal: Cascadia Mono, around 100 x 40 cells.",
)


def compose_screen(explorer: Explorer, width: int, height: int) -> tuple[list[str], str]:
    """Compose fixed-sized rows plus the exportable tree raster. No ANSI here."""
    width, height = max(1, min(500, width)), max(1, min(250, height))
    # Keep a tree even in a 1x1 terminal. Larger screens reserve 5 UI rows.
    if height < 7 or width < 24:
        options = replace(explorer.options, width=width, height=height)
        frame = render_tree(explorer.tree, options)
        rows = frame.splitlines()
        if height >= 2:
            rows[0] = f"{options.mode.upper()} Q quit H help"[:width].ljust(width)
        return rows, frame
    options = replace(explorer.options, width=width, height=height - 5)
    frame = render_tree(explorer.tree, options)
    mode = options.mode.upper()
    yaw = (options.yaw + options.time * 14) % 360
    xw = (options.angle4d + options.time * 9) % 360
    title = f" ASCII TREE EXPLORER  /  {mode}  /  seed {explorer.tree.seed}"
    status = f" yaw {yaw:5.1f}  tilt {options.pitch:+5.1f}  XW {xw:5.1f}  zoom {options.zoom:.2f}  {'PLAY' if explorer.animated else 'PAUSE'}"
    explanation = " 4D -> 3D -> 2D: projection of (x,y,z,w); [ ] mixes X and growth-age W" if mode == "4D" else " 1 2D   2 3D   3 4D  |  arrows orbit  +/- zoom  Space play  H help  Q quit"
    raster = frame.splitlines()
    if explorer.help_open:
        raster = [" " * width for _ in raster]
        for index, line in enumerate(HELP[:len(raster)]):
            raster[index] = (" " + line)[:width].ljust(width)
    rows = [title, status, "-" * width, *raster, explanation, " " + explorer.message]
    return [line[:width].ljust(width) for line in rows], frame
