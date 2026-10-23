"""ASCII rasterizer with interpolated z, tapered capsules, and sparse leaves."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from .geometry import NEAR, Vec4, camera, project4
from .model import Tree

MAX_CELLS = 1_000_000


def animated_angle(base: float, rate: float, seconds: float) -> float:
    # Rates are 12 and 8 deg/s, with a shared 90-second period. Reduce before
    # multiplication so even very large finite CLI times cannot overflow.
    return (base % 360 + (seconds % 90) * rate) % 360


@dataclass(frozen=True, slots=True)
class RenderOptions:
    width: int = 100
    height: int = 40
    mode: str = "3d"
    yaw: float = 25.0
    pitch: float = -8.0
    angle4d: float = 0.0
    zoom: float = 1.0
    aspect: float = 2.0  # cell height / cell width
    time: float = 0.0

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1 or self.width * self.height > MAX_CELLS:
            raise ValueError("frame dimensions must be positive and at most 1,000,000 cells")
        if self.mode not in ("2d", "3d", "4d"):
            raise ValueError("mode must be 2d, 3d or 4d")
        for name in ("yaw", "pitch", "angle4d", "zoom", "aspect", "time"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        if not 0.15 <= self.zoom <= 5.0 or not 0.5 <= self.aspect <= 4.0:
            raise ValueError("zoom must be 0.15..5; aspect must be 0.5..4")


@dataclass(frozen=True, slots=True)
class ScreenPoint:
    x: float
    y: float
    depth: float
    scale: float


class Raster:
    """Smaller positive depth wins, independently of submission order."""

    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.cells = [[" "] * width for _ in range(height)]
        self.depth = [[math.inf] * width for _ in range(height)]
        self.priority = [[-1] * width for _ in range(height)]

    def put(self, x: int, y: int, depth: float, char: str, priority: int = 0) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height and math.isfinite(depth)):
            return
        old = self.depth[y][x]
        if depth < old - 1e-7 or (abs(depth - old) <= 1e-7 and priority > self.priority[y][x]):
            self.depth[y][x], self.cells[y][x], self.priority[y][x] = depth, char, priority

    def text(self) -> str:
        return "\n".join("".join(row) for row in self.cells) + "\n"


class Projector:
    def __init__(self, tree: Tree, options: RenderOptions) -> None:
        self.tree, self.options = tree, options
        self.yaw = math.radians(animated_angle(options.yaw, 12, options.time))
        self.pitch = math.radians(options.pitch % 360)
        self.angle = math.radians(animated_angle(options.angle4d, 8, options.time))
        self.pixels = min((options.height - 1) / 2.45,
                          (options.width - 1) / (2.7 * options.aspect)) * options.zoom

    def point(self, point: Vec4) -> ScreenPoint | None:
        p = self.tree.normalized(point)
        factor4 = 1.0
        if self.options.mode == "4d":
            projected = project4(p, self.angle)
            if projected is None:
                return None
            xyz, factor4 = projected
        else:
            xyz = p[:3]
        if self.options.mode == "2d":
            x, y, z = xyz
            depth, perspective = 4.5 + z, 1.0
        else:
            x, y, z = camera(xyz, self.yaw, self.pitch)
            depth = 4.5 + z
            if depth <= NEAR:
                return None
            perspective = 4.5 / depth
        o = self.options
        return ScreenPoint((o.width - 1) / 2 + x * perspective * self.pixels * o.aspect,
                           (o.height - 1) / 2 - y * perspective * self.pixels,
                           depth, factor4 * perspective * self.pixels)


def draw_segment(raster: Raster, a: ScreenPoint, b: ScreenPoint,
                 radius_a: float, radius_b: float, aspect: float, order: int) -> None:
    """Bounded capsule rasterization; reciprocal depth is linear on screen."""
    dx, dy = (b.x - a.x) / aspect, b.y - a.y
    length2 = dx * dx + dy * dy
    ra, rb = radius_a * a.scale, radius_b * b.scale
    reach = max(ra, rb, 0.46)
    x0 = max(0, math.floor(min(a.x, b.x) - reach * aspect - 1))
    x1 = min(raster.width - 1, math.ceil(max(a.x, b.x) + reach * aspect + 1))
    y0 = max(0, math.floor(min(a.y, b.y) - reach - 1))
    y1 = min(raster.height - 1, math.ceil(max(a.y, b.y) + reach + 1))
    directional = "|" if abs(dy) > abs(dx) * 1.8 else "-" if abs(dx) > abs(dy) * 2.2 else ("\\" if dx * dy > 0 else "/")
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            px, py = (x - a.x) / aspect, y - a.y
            t = max(0.0, min(1.0, (px * dx + py * dy) / length2)) if length2 else 0.0
            ex, ey = px - dx * t, py - dy * t
            radius = max(0.46, ra + (rb - ra) * t)
            if ex * ex + ey * ey > radius * radius:
                continue
            depth = 1.0 / ((1 - t) / a.depth + t / b.depth)
            # Cylinder's visible front surface. Per-cell depth also resolves crossings.
            depth -= math.sqrt(max(0, radius * radius - ex * ex - ey * ey)) / max(a.scale, b.scale, 1)
            physical_radius = ra + (rb - ra) * t
            if physical_radius >= 0.55:
                # A fixed upper-left light gives bark a readable round profile.
                light = max(0, min(1, 0.55 - ex / max(radius, 0.1) * 0.4 - (depth - 4.5) * 0.2))
                char = ":+%#@"[min(4, int(light * 5))]
            elif depth > 4.85 and order >= 2:
                char = ":" if order == 2 else "."
            else:
                char = directional
            raster.put(x, y, depth, char, 2)


def render(tree: Tree, options: RenderOptions | None = None) -> str:
    o = options or RenderOptions()
    raster = Raster(o.width, o.height)
    projector = Projector(tree, o)
    points = [projector.point(p) for p in tree.vertices]
    # Leaves are porous samples, not opaque crown discs. Z still determines visibility.
    for leaf in tree.leaves:
        p = projector.point(leaf.position)
        if p is None:
            continue
        char = (".'*o" if p.depth < 4.5 else ".,'+")[min(3, int(leaf.tone * 4))]
        raster.put(round(p.x), round(p.y), p.depth, char, 1)
    for segment in tree.segments:
        a, b = points[segment.start], points[segment.end]
        if a is not None and b is not None:
            draw_segment(raster, a, b, segment.radius_start / tree.scale,
                         segment.radius_end / tree.scale, o.aspect, segment.order)
    return raster.text()


def write_frame(path: str | Path, frame: str) -> None:
    """Binary LF output: no BOM, platform newline translation, or ANSI."""
    if any(ord(c) > 126 or (ord(c) < 32 and c != "\n") for c in frame):
        raise ValueError("frame must contain printable ASCII and LF only")
    Path(path).write_bytes(frame.encode("ascii"))
