"""Aspect-correct ASCII rasterization with a per-cell depth buffer."""
from dataclasses import dataclass
import math
from pathlib import Path
from .geometry import project
from .model import Tree


@dataclass(frozen=True, slots=True)
class RenderOptions:
    width: int = 100
    height: int = 35
    mode: str = "3d"
    yaw: float = .45
    pitch: float = .08
    angle4: float = 0.
    zoom: float = 1.
    aspect: float = .5  # character width / character height

    def __post_init__(self):
        if not (1 <= self.width <= 1000 and 1 <= self.height <= 500):
            raise ValueError("frame size must be 1..1000 columns and 1..500 rows")
        if self.mode not in ("2d", "3d", "4d"):
            raise ValueError("mode must be 2d, 3d or 4d")
        if not all(math.isfinite(v) for v in (self.yaw, self.pitch, self.angle4, self.zoom, self.aspect)):
            raise ValueError("angles, zoom and aspect must be finite")
        if not (.1 <= self.zoom <= 8 and .2 <= self.aspect <= 2):
            raise ValueError("zoom must be .1..8 and aspect .2..2")


class Canvas:
    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.pixels = [[" "] * width for _ in range(height)]
        self.depth = [[math.inf] * width for _ in range(height)]
        self.priority = [[-1] * width for _ in range(height)]

    def put(self, x, y, depth, char, priority=1):
        if not (0 <= x < self.width and 0 <= y < self.height and math.isfinite(depth)):
            return
        old = self.depth[y][x]
        # At equal depth wood wins over leaves. Else the nearer surface wins.
        if depth < old - 1e-7 or (abs(depth - old) <= 1e-7 and priority > self.priority[y][x]):
            self.pixels[y][x] = char
            self.depth[y][x] = depth
            self.priority[y][x] = priority

    def text(self):
        return "\n".join("".join(row) for row in self.pixels) + "\n"


def segment_glyph(dx, dy, radius, depth):
    if radius >= .95:
        return "@" if depth < 31 else "#"
    if radius >= .60:
        return "O" if depth < 32 else "%"
    if abs(dx) < abs(dy) * .45:
        return "|"
    if abs(dy) < abs(dx) * .25:
        return "-"
    return "\\" if dx * dy > 0 else "/"


def draw_segment(canvas: Canvas, a, b, radius_a, radius_b, aspect=.5, glyph=None):
    """Dense DDA covers connected centerlines; ellipses cover thick branches.

    Depth uses reciprocal interpolation appropriate for projected segments.
    Radii and depths describe surfaces, not just a draw-order painter.
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    steps = max(1, math.ceil(max(abs(dx), abs(dy)) * 2))
    # Projection/zoom bounds keep this finite even if the frame is clipped.
    steps = min(steps, 16000)
    for i in range(steps + 1):
        t = i / steps
        x, y = a[0] + dx * t, a[1] + dy * t
        depth = 1 / ((1 - t) / max(a[2], .01) + t / max(b[2], .01))
        radius = radius_a * (1 - t) + radius_b * t
        rx, ry = max(.48, radius / aspect), max(.48, radius)
        char = glyph or segment_glyph(dx, dy, radius, depth)
        cx, cy = round(x), round(y)
        canvas.put(cx, cy, depth, char, 2)
        if radius < .36:
            continue
        for yy in range(max(0, math.ceil(y - ry)), min(canvas.height - 1, math.floor(y + ry)) + 1):
            for xx in range(max(0, math.ceil(x - rx)), min(canvas.width - 1, math.floor(x + rx)) + 1):
                ellipse = ((xx - x) / rx) ** 2 + ((yy - y) / ry) ** 2
                if ellipse <= 1:
                    canvas.put(xx, yy, depth - .04 * (1 - ellipse), char, 2)


def render(tree: Tree, options: RenderOptions = RenderOptions()) -> str:
    o = options
    canvas = Canvas(o.width, o.height)
    cache = {}

    def transform(p):
        if p not in cache:
            cache[p] = project(p, o.mode, o.yaw, o.pitch, o.angle4)
        return cache[p]

    points = [transform(s.end) for s in tree.segments]
    points += [transform(s.start) for s in tree.segments if s.parent is None]
    points += [transform(leaf.position) for leaf in tree.leaves]
    if not points:
        return canvas.text()
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
    scale = min(max(1, o.width - 5) * o.aspect / max(.1, xmax - xmin),
                max(1, o.height - 3) / max(.1, ymax - ymin)) * o.zoom
    centerx, centery = (xmin + xmax) / 2, (ymin + ymax) / 2

    def screen(p):
        x, y, depth, factor = transform(p)
        return ((o.width - 1) / 2 + (x - centerx) * scale / o.aspect,
                (o.height - 1) / 2 - (y - centery) * scale, depth, factor)

    # Leaf samples have genuine depth but are intentionally sparse.
    for leaf in tree.leaves:
        x, y, depth, factor = screen(leaf.position)
        char = (".", "'", ":", "*")[leaf.tone] if depth < 35 else "."
        canvas.put(round(x), round(y), depth, char, 0)
    for seg in tree.segments:
        a, b = screen(seg.start), screen(seg.end)
        draw_segment(canvas, a, b, seg.radius_start * scale * a[3],
                     seg.radius_end * scale * b[3], o.aspect)
    return canvas.text()


def export_frame(frame: str, path: str | Path):
    """Canonical bytes: printable ASCII cells, LF newlines, trailing LF."""
    if any(c != "\n" and not 32 <= ord(c) <= 126 for c in frame):
        raise ValueError("frame contains a non-printable ASCII cell")
    Path(path).write_bytes(frame.encode("ascii"))
