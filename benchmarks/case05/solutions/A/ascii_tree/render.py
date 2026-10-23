"""ASCII rasterizer with a per-cell z-buffer and tapered branch coverage."""

from dataclasses import dataclass
import math
from pathlib import Path

from .geometry import Projector, View
from .model import Tree


@dataclass(frozen=True, slots=True)
class Frame:
    lines: tuple[str, ...]

    @property
    def width(self):
        return len(self.lines[0]) if self.lines else 0

    @property
    def height(self):
        return len(self.lines)

    def text(self) -> str:
        return '\n'.join(self.lines) + '\n'

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.text().encode('ascii'))
        return target


class Raster:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.cells = [[' '] * width for _ in range(height)]
        self.depth = [[math.inf] * width for _ in range(height)]

    def put(self, x: int, y: int, depth: float, char: str):
        if (0 <= x < self.width and 0 <= y < self.height
                and math.isfinite(depth) and depth < self.depth[y][x]):
            self.depth[y][x] = depth
            self.cells[y][x] = char

    def frame(self):
        return Frame(tuple(''.join(row) for row in self.cells))


def _clip_line(x0, y0, x1, y1, width, height, margin):
    """Liang-Barsky clipping bounds work even at extreme zoom."""
    dx, dy = x1 - x0, y1 - y0
    lo, hi = 0.0, 1.0
    for p, q in ((-dx, x0 + margin), (dx, width - 1 + margin - x0),
                 (-dy, y0 + margin), (dy, height - 1 + margin - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return None
        else:
            t = q / p
            if p < 0:
                lo = max(lo, t)
            else:
                hi = min(hi, t)
            if lo > hi:
                return None
    return lo, hi


def raster_segment(raster, a, b, radius_a, radius_b, order):
    """Interpolate reciprocal depth, so crossings obey perspective occlusion."""
    dx, dy = b.x - a.x, b.y - a.y
    largest = min(12, max(radius_a * a.scale, radius_b * b.scale))
    clipping = _clip_line(a.x, a.y, b.x, b.y, raster.width, raster.height,
                          largest * 2 + 1)
    if clipping is None:
        return
    lo, hi = clipping
    steps = max(1, math.ceil(max(abs(dx), abs(dy)) * (hi - lo) * 1.5))
    slope = abs(dy) / max(0.01, abs(dx))
    direction = '|' if slope > 1.3 else '-' if slope < 0.24 else ('\\' if dx * dy > 0 else '/')
    for step in range(steps + 1):
        t = lo + (hi - lo) * step / steps
        x, y = a.x + dx * t, a.y + dy * t
        reciprocal = (1 - t) / max(0.5, a.depth) + t / max(0.5, b.depth)
        depth = 1 / reciprocal
        radius = min(12.0, max(0.0, (radius_a * a.scale * (1 - t) + radius_b * b.scale * t)))
        rx, ry = max(0.52, radius * 2), max(0.50, radius)
        for py in range(max(0, math.ceil(y - ry)), min(raster.height - 1, math.floor(y + ry)) + 1):
            for px in range(max(0, math.ceil(x - rx)), min(raster.width - 1, math.floor(x + rx)) + 1):
                cross = ((px - x) / rx) ** 2 + ((py - y) / ry) ** 2
                if cross <= 1.1:
                    if radius >= 0.38:
                        # Cylindrical highlight and nearer/darker ASCII tones.
                        light = (px - x) / rx * 0.4 + (depth - 40) * 0.025
                        char = '@' if light < -0.27 else '#' if light < 0.25 else '%'
                    else:
                        char = direction if order <= 2 else ('+' if depth < 43 else ':')
                    raster.put(px, py, depth - radius * math.sqrt(max(0, 1 - cross)) * 0.35, char)
        # A center sample keeps sub-cell twigs continuous at every orientation.
        char = direction if radius < 0.38 else '#'
        if order >= 3 and radius < 0.38:
            char = '+' if depth < 43 else ':'
        raster.put(round(x), round(y), depth, char)


def render(tree: Tree, view: View = View(), width: int = 100, height: int = 40) -> Frame:
    if not (1 <= width <= 500 and 1 <= height <= 200):
        raise ValueError('Frame size must be 1..500 columns and 1..200 rows')
    if view.mode not in ('2d', '3d', '4d'):
        raise ValueError('Mode must be 2d, 3d or 4d')
    if not all(math.isfinite(v) for v in (view.yaw, view.pitch, view.angle4, view.zoom, view.time)):
        raise ValueError('View parameters must be finite')
    if not 0.1 <= view.zoom <= 8:
        raise ValueError('Zoom must be between 0.1 and 8')
    raster = Raster(width, height)
    projector = Projector(tree, view, width, height)
    for segment in tree.segments:
        a, b = projector.project(segment.start), projector.project(segment.end)
        if a is not None and b is not None:
            raster_segment(raster, a, b, segment.radius_start, segment.radius_end, segment.order)
    for leaf in tree.leaves:
        point = projector.project(leaf.point)
        if point is not None:
            shade = leaf.tone + (45 - point.depth) * 0.04
            char = "'" if shade < 0.22 else '.' if shade < 0.48 else '*' if shade < 0.80 else 'o'
            raster.put(round(point.x), round(point.y), point.depth, char)
    return raster.frame()
