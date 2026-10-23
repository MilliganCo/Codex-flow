"""ASCII capsule rasterizer with a per-cell depth buffer and aspect correction."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .math4d import Point4, perspective4, rotate3, rotate_xw
from .model import Tree


@dataclass(frozen=True, slots=True)
class RenderOptions:
    width: int = 100
    height: int = 40
    mode: str = "3d"
    yaw: float = 28.0
    pitch: float = -8.0
    angle4: float = 0.0
    zoom: float = 1.0
    aspect: float = 2.0  # character height / character width
    time: float = 0.0   # deterministic wind, in seconds

    def __post_init__(self) -> None:
        if self.mode not in ("2d", "3d", "4d"):
            raise ValueError("mode must be 2d, 3d or 4d")
        if not (1 <= self.width <= 500 and 1 <= self.height <= 200):
            raise ValueError("frame dimensions must be 1..500 by 1..200")
        if not all(math.isfinite(v) for v in (self.yaw, self.pitch, self.angle4, self.zoom, self.aspect, self.time)):
            raise ValueError("angles, zoom, aspect and time must be finite")
        if not 0.1 <= self.zoom <= 8 or not 0.5 <= self.aspect <= 4:
            raise ValueError("zoom must be 0.1..8; aspect must be 0.5..4")


class DepthBuffer:
    """Smaller camera distance wins. Tie priority keeps wood readable in 2D."""

    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.chars = [[" "] * width for _ in range(height)]
        self.depth = [[math.inf] * width for _ in range(height)]
        self.priority = [[-1] * width for _ in range(height)]

    def put(self, x: int, y: int, depth: float, char: str, priority: int = 0) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height and math.isfinite(depth)):
            return
        old = self.depth[y][x]
        if depth < old - 1e-7 or (abs(depth - old) <= 1e-7 and priority > self.priority[y][x]):
            self.chars[y][x] = char
            self.depth[y][x] = depth
            self.priority[y][x] = priority

    def lines(self) -> tuple[str, ...]:
        return tuple("".join(row) for row in self.chars)


@dataclass(frozen=True, slots=True)
class Projected:
    x: float
    y: float
    depth: float
    scale: float


class Projector:
    def __init__(self, tree: Tree, options: RenderOptions):
        self.tree, self.options = tree, options
        # Y screen units are rows; X units are physical half-width cells by default.
        self.scale = min(max(0.25, options.width - 4) / options.aspect,
                         max(0.25, options.height - 3)) / (tree.radius * 1.73) * options.zoom
        self.distance3 = tree.radius * 4
        self.distance4 = tree.radius * 4

    def project(self, point: Point4) -> Projected | None:
        o, center = self.options, self.tree.center
        p = Point4(point.x - center.x, point.y - center.y, point.z - center.z, point.w - center.w)
        if o.time:
            # Pinned roots; fine crown bends slightly. No random state in animation.
            strength = max(0, (point.y / max(1, center.y * 2))) ** 2
            p = Point4(p.x + math.sin(o.time * 1.7 + point.y * 0.6) * 0.18 * strength, p.y, p.z, p.w)
        factor4 = 1.0
        if o.mode == "4d":
            p = rotate_xw(p, o.angle4)
            xyz = perspective4(p, self.distance4)
            if xyz is None:
                return None
            factor4 = self.distance4 / (self.distance4 - p.w)
        else:
            xyz = (p.x, p.y, p.z)
        if o.mode == "2d":
            x, y, _ = xyz
            depth, factor3 = self.distance3, 1.0
        else:
            x, y, z = rotate3(xyz, o.yaw, o.pitch)
            depth = self.distance3 - z
            if not math.isfinite(depth) or depth <= self.distance3 * 0.05:
                return None
            factor3 = self.distance3 / depth
        scale = self.scale * factor3
        result = Projected((o.width - 1) / 2 + x * scale * o.aspect,
                           (o.height - 1) / 2 - y * scale, depth, scale * factor4)
        return result if all(math.isfinite(v) for v in (result.x, result.y, result.depth, result.scale)) else None


def _wood_char(dx: float, dy: float, radius: float, depth: float, distance: float, across: float) -> str:
    if radius >= 0.65:
        # Light from upper-left and depth both affect the bark tone.
        light = max(0, min(0.999, 0.56 - across * 0.28 + (distance - depth) / distance))
        return ":+%#@"[int(light * 5)]
    if abs(dx) > abs(dy) * 2.2:
        return "_" if depth > distance * 1.12 else "-"
    if abs(dy) > abs(dx) * 1.65:
        return "|" if depth < distance * 1.12 else ":"
    return "\\" if dx * dy > 0 else "/"


def draw_segment(buffer: DepthBuffer, a: Projected, b: Projected, r0: float, r1: float,
                 aspect: float, distance: float, *, glyph: str | None = None) -> None:
    """Sample a tapered capsule, including endpoints; interpolate reciprocal depth.

    Sampling at <=0.45 cell intervals gives an 8-connected centerline. Elliptic
    footprints account for non-square character cells. Bounds are clamped before loops.
    """
    dx, dy = b.x - a.x, b.y - a.y
    steps = min(6000, max(1, math.ceil(max(abs(dx), abs(dy)) * 2.25)))
    for i in range(steps + 1):
        t = i / steps
        cx, cy = a.x + dx * t, a.y + dy * t
        # Perspective-correct interpolation: radius/depth are attributes over the line.
        reciprocal = (1 - t) / a.depth + t / b.depth
        depth = 1 / reciprocal
        u = (t / b.depth) / reciprocal
        radius = (r0 * (1 - u) * a.scale + r1 * u * b.scale)
        rx, ry = max(0.48, radius * aspect), max(0.48, radius)
        left, right = max(0, math.ceil(cx - rx)), min(buffer.width - 1, math.floor(cx + rx))
        top, bottom = max(0, math.ceil(cy - ry)), min(buffer.height - 1, math.floor(cy + ry))
        # Always include a center cell even when sub-cell coverage misses all cell centers.
        if 0 <= round(cx) < buffer.width and 0 <= round(cy) < buffer.height:
            char = glyph or _wood_char(dx, dy, radius, depth, distance, 0)
            buffer.put(round(cx), round(cy), depth, char, 2)
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                across = (x - cx) / rx
                if across * across + ((y - cy) / ry) ** 2 <= 1:
                    char = glyph or _wood_char(dx, dy, radius, depth, distance, across)
                    # Approximate the front surface of the woody tube, not just its axis.
                    surface = depth - min(r0, r1) * math.sqrt(max(0, 1 - across * across))
                    buffer.put(x, y, surface, char, 2)


def render_lines(tree: Tree, options: RenderOptions) -> tuple[str, ...]:
    projector = Projector(tree, options)
    buffer = DepthBuffer(options.width, options.height)
    projected: dict[Point4, Projected | None] = {}

    def project(point: Point4) -> Projected | None:
        if point not in projected:
            projected[point] = projector.project(point)
        return projected[point]

    # Submit leaves first. Only actual nearer geometry can cover them in 3D/4D.
    for leaf in tree.leaves:
        p = project(leaf.position)
        if p is None:
            continue
        light = max(0, min(0.999, 0.45 * leaf.tone + 0.4 + (projector.distance3 - p.depth) / projector.distance3))
        char = ".,'+:*o"[int(light * 7)]
        buffer.put(round(p.x), round(p.y), p.depth, char, 0)
        if leaf.radius * p.scale * options.aspect > 0.65:
            buffer.put(round(p.x) + 1, round(p.y), p.depth, "'", 0)
    for segment in tree.segments:
        a, b = project(segment.start), project(segment.end)
        if a is not None and b is not None:
            draw_segment(buffer, a, b, segment.radius_start, segment.radius_end,
                         options.aspect, projector.distance3)
    return buffer.lines()


def render_text(tree: Tree, options: RenderOptions) -> str:
    """Exact width per row, exact row count, one LF after every row (also last)."""
    return "\n".join(render_lines(tree, options)) + "\n"
