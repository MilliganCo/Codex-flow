"""ASCII capsule rasterizer with a per-character depth buffer and bark lighting."""

from dataclasses import dataclass
import math

from .model import Tree
from .projection import Projected, Projector


@dataclass(frozen=True, slots=True)
class RenderSettings:
    width: int = 100
    height: int = 40
    mode: str = "3d"
    yaw: float = 25.0
    pitch: float = -8.0
    angle4d: float = 0.0
    zoom: float = 1.0
    aspect: float = 2.0
    time: float = 0.0

    def __post_init__(self) -> None:
        if not (1 <= self.width <= 500 and 1 <= self.height <= 200):
            raise ValueError("frame size must be 1..500 columns and 1..200 rows")
        if self.mode not in ("2d", "3d", "4d"):
            raise ValueError("mode must be 2d, 3d or 4d")
        if not all(math.isfinite(a) for a in
                   (self.yaw, self.pitch, self.angle4d, self.zoom, self.aspect, self.time)):
            raise ValueError("angles, zoom and aspect must be finite")
        if not 0.15 <= self.zoom <= 5 or not 1 <= self.aspect <= 3:
            raise ValueError("zoom must be 0.15..5; aspect must be 1..3")


class Raster:
    """Depth is distance to camera: the smaller fragment wins, regardless of order."""

    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.chars = [[" "] * width for _ in range(height)]
        self.depth = [[math.inf] * width for _ in range(height)]
        self.priority = [[-1] * width for _ in range(height)]

    def put(self, x: int, y: int, depth: float, char: str, priority: int = 1) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height and math.isfinite(depth)):
            return
        old = self.depth[y][x]
        if depth < old - 1e-8 or (abs(depth - old) <= 1e-8
                                 and priority > self.priority[y][x]):
            self.depth[y][x], self.chars[y][x] = depth, char
            self.priority[y][x] = priority

    def text(self) -> str:
        # LF is the only control character; keep every trailing space.
        return "\n".join("".join(row) for row in self.chars) + "\n"

    def segment(self, a: Projected, b: Projected, radius_a: float,
                radius_b: float, scale: float, aspect: float,
                perspective: bool = True) -> None:
        dx, dy = b.x - a.x, b.y - a.y
        margin_x = max(radius_a, radius_b) * aspect + 0.6
        margin_y = max(radius_a, radius_b) + 0.6
        left = max(0, math.floor(min(a.x, b.x) - margin_x))
        right = min(self.width - 1, math.ceil(max(a.x, b.x) + margin_x))
        top = max(0, math.floor(min(a.y, b.y) - margin_y))
        bottom = min(self.height - 1, math.ceil(max(a.y, b.y) + margin_y))
        slope = abs(dy) / (abs(dx) + 1e-9)
        direction_char = "|" if slope > 1.15 else (
            "_" if slope < 0.25 else ("\\" if dx * dy > 0 else "/"))
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                # Closest point in physical cell units, not square-pixel units.
                physical_denom = (dx / aspect) ** 2 + dy * dy
                t = 0.0 if physical_denom < 1e-12 else min(1.0, max(0.0,
                    ((x - a.x) * dx / (aspect * aspect) + (y - a.y) * dy)
                    / physical_denom))
                cx, cy = a.x + t * dx, a.y + t * dy
                distance = math.hypot((x - cx) / aspect, y - cy)
                radius = radius_a * (1 - t) + radius_b * t
                # Half-cell coverage preserves sub-character twigs and joins.
                if distance > max(0.40, radius + 0.27):
                    continue
                depth = (1 / ((1 - t) / a.depth + t / b.depth) if perspective
                         else a.depth * (1 - t) + b.depth * t)
                if radius > 0.44:
                    normal_x = max(-1.0, min(1.0, (x - cx) / (aspect * max(radius, .01))))
                    light = 0.6 - normal_x * 0.27 + (30 - depth) * 0.018
                    char = "#%@"[min(2, max(0, int(light * 3)))]
                else:
                    char = direction_char
                # Front surface of an approximate round branch capsule.
                surface = math.sqrt(max(0, radius * radius - distance * distance))
                self.put(x, y, depth - surface / max(scale, 0.001), char, 2)
        # A subpixel branch can otherwise disappear between character centers.
        # Sample a centerline in addition to coverage, bounded by viewport size.
        steps = min(2000, max(1, math.ceil(max(abs(dx), abs(dy)) * 1.5)))
        for i in range(steps + 1):
            t = i / steps
            depth = (1 / ((1 - t) / a.depth + t / b.depth) if perspective
                     else a.depth * (1 - t) + b.depth * t)
            self.put(round(a.x + t * dx), round(a.y + t * dy), depth, direction_char, 1)


def render(tree: Tree, settings: RenderSettings = RenderSettings()) -> str:
    width, height = settings.width, settings.height
    span_x, span_y = tree.span
    scale = max(0.015, min(max(1, width - 6) / (span_x * settings.aspect),
                           max(1, height - 4) / span_y)) * settings.zoom * 0.91
    projector = Projector(tree.center, width, height, scale, settings.mode,
                          math.radians(settings.yaw % 360),
                          math.radians(settings.pitch % 360),
                          math.radians(settings.angle4d % 360), settings.aspect,
                          settings.time)
    raster = Raster(width, height)
    for leaf in tree.leaves:
        p = projector(leaf.point)
        if p is None:
            continue
        # The lit side and depth choose a soft ASCII foliage texture.
        light = leaf.tone * 0.65 + (35 - p.depth) * 0.035
        char = ".,'*o"[min(4, max(0, int(light * 5)))]
        raster.put(round(p.x), round(p.y), p.depth, char, 0)
        # At close zoom a leaf occupies more than one character, but remains airy.
        if leaf.size * scale * p.magnification * settings.aspect > 0.8:
            raster.put(round(p.x) + 1, round(p.y), p.depth + 0.01, "'", 0)
    for segment in tree.segments:
        a, b = projector(segment.start), projector(segment.end)
        if a is None or b is None:
            continue
        raster.segment(a, b, segment.radius_start * scale * a.magnification,
                       segment.radius_end * scale * b.magnification,
                       scale, settings.aspect, settings.mode != "2d")
    return raster.text()
