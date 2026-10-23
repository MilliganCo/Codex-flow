"""Clipped ASCII capsule rasterizer with a per-character depth buffer."""

from dataclasses import dataclass
import math
from pathlib import Path

from .geometry import Tree
from .projection import Projector, ScreenPoint, View

MAX_WIDTH, MAX_HEIGHT = 500, 240


def validate_size(width: int, height: int) -> None:
    if not 1 <= width <= MAX_WIDTH or not 1 <= height <= MAX_HEIGHT:
        raise ValueError(f"size must be 1..{MAX_WIDTH} columns by 1..{MAX_HEIGHT} rows")


@dataclass(frozen=True, slots=True)
class Frame:
    rows: tuple[str, ...]

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    @property
    def height(self) -> int:
        return len(self.rows)

    def to_bytes(self) -> bytes:
        """Fixed-width printable ASCII rows, LF terminators, including the last row."""
        return ("\n".join(self.rows) + "\n").encode("ascii")

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())


class Raster:
    def __init__(self, width: int, height: int):
        validate_size(width, height)
        self.width, self.height = width, height
        self.cells = [[" "] * width for _ in range(height)]
        self.depths = [[math.inf] * width for _ in range(height)]
        self.priorities = [[-1] * width for _ in range(height)]

    def put(self, x: int, y: int, depth: float, char: str, priority: int = 0) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height and math.isfinite(depth)):
            return
        previous = self.depths[y][x]
        if depth < previous - 1e-7 or (abs(depth - previous) <= 1e-7 and
                (priority, char) > (self.priorities[y][x], self.cells[y][x])):
            self.cells[y][x], self.depths[y][x] = char, depth
            self.priorities[y][x] = priority

    def segment(self, a: ScreenPoint, b: ScreenPoint, r0: float, r1: float,
                aspect: float, char: str | None = None, perspective: bool = True) -> None:
        """Draw a tapered capsule, clipping iteration bounds to the viewport.

        Depth is reciprocal-interpolated for perspective (linear for orthographic).
        Closest-point sampling fills diagonal joins without disconnected dashes.
        """
        values = (a.x, a.y, a.depth, b.x, b.y, b.depth, r0, r1, aspect)
        if not all(math.isfinite(v) for v in values) or min(a.depth, b.depth, aspect) <= 0:
            return
        r0, r1 = max(0.30, r0), max(0.30, r1)
        radius = min(max(r0, r1), max(self.width, self.height) * 2)
        left = max(0, math.floor(min(a.x, b.x) - radius / aspect - 1))
        right = min(self.width - 1, math.ceil(max(a.x, b.x) + radius / aspect + 1))
        top = max(0, math.floor(min(a.y, b.y) - radius - 1))
        bottom = min(self.height - 1, math.ceil(max(a.y, b.y) + radius + 1))
        dx, dy = (b.x - a.x) * aspect, b.y - a.y
        length2 = dx * dx + dy * dy
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                t = max(0.0, min(1.0, (((x - a.x) * aspect * dx +
                                        (y - a.y) * dy) / length2))) if length2 else 0.0
                distance = math.hypot((x - a.x) * aspect - dx * t, y - a.y - dy * t)
                r = min(radius, r0 + (r1 - r0) * t)
                # Minimum width is enough to keep thin diagonal branches connected.
                if distance > max(0.56, r):
                    continue
                depth = (1 / ((1 - t) / a.depth + t / b.depth) if perspective else
                         a.depth + (b.depth - a.depth) * t)
                # A cylinder's front surface lies slightly ahead of its centerline.
                surface = depth - math.sqrt(max(0, r * r - distance * distance)) * 0.14
                glyph = char or self.wood_glyph(dx, dy, r, depth, distance)
                self.put(x, y, surface, glyph, 2)

    @staticmethod
    def wood_glyph(dx: float, dy: float, radius: float, depth: float, distance: float) -> str:
        if radius > 0.63:
            if distance > radius * 0.78:
                return "|" if abs(dy) > abs(dx) else "+"
            return "@" if depth < 22 else "#" if depth < 26 else "%"
        if abs(dy) > abs(dx) * 2:
            return "|"
        if abs(dx) > abs(dy) * 2.5:
            return "_" if depth < 25 else "-"
        return "\\" if dx * dy > 0 else "/"

    def frame(self) -> Frame:
        return Frame(tuple("".join(row) for row in self.cells))


def render_tree(tree: Tree, width: int = 100, height: int = 40,
                view: View | None = None) -> Frame:
    view = view or View()
    raster = Raster(width, height)
    project = Projector(tree, width, height, view)
    # Leaves occupy single cells, rather than opaque blobs hiding the skeleton.
    for leaf in tree.leaves:
        p = project(leaf.point)
        if p is None or not (-1 <= p.x <= width and -1 <= p.y <= height):
            continue
        glyph = (".,:*" if p.depth > 25 else ":*o'")[leaf.shade]
        raster.put(round(p.x), round(p.y), p.depth - leaf.size * 0.4, glyph, 1)
    for segment in tree.segments:
        a, b = project(segment.start), project(segment.end)
        # Near-plane crossings are discarded; generated trees remain well in front.
        if a is None or b is None:
            continue
        raster.segment(a, b, segment.radius_start * a.scale,
                       segment.radius_end * b.scale, view.aspect,
                       perspective=view.mode != "2d")
    return raster.frame()
