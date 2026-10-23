"""ASCII rasterizer with aspect correction and per-cell depth testing."""

from dataclasses import dataclass
import math

from .geometry import Point4, project4, rotate3, rotation4, transform4
from .model import Tree


@dataclass(frozen=True, slots=True)
class RenderOptions:
    width: int = 100
    height: int = 40
    mode: str = "3d"
    yaw: float = -25.0
    pitch: float = 8.0
    angle4: float = 0.0
    plane: str = "xw"
    zoom: float = 1.0
    aspect: float = 0.5  # character width / character height
    time: float = 0.0  # deterministic breeze, seconds; zero is undeformed geometry

    def __post_init__(self) -> None:
        if not (1 <= self.width <= 500 and 1 <= self.height <= 200):
            raise ValueError("frame dimensions must be 1..500 by 1..200")
        if self.mode not in ("2d", "3d", "4d"):
            raise ValueError("mode must be 2d, 3d or 4d")
        if self.plane not in ("xw", "yw", "zw"):
            raise ValueError("plane must be xw, yw or zw")
        if not all(math.isfinite(v) for v in (self.yaw, self.pitch, self.angle4, self.zoom, self.aspect, self.time)):
            raise ValueError("angles, zoom and aspect must be finite")
        if not 0.1 <= self.zoom <= 6 or not 0.25 <= self.aspect <= 1.0:
            raise ValueError("zoom must be 0.1..6; aspect must be 0.25..1")


class DepthBuffer:
    """Smaller positive eye-distance is nearer; order cannot reveal hidden wood."""

    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.cells = [[" "] * width for _ in range(height)]
        self.depth = [[math.inf] * width for _ in range(height)]
        self.priority = [[-1] * width for _ in range(height)]

    def put(self, x: int, y: int, depth: float, char: str, priority: int = 0) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height and math.isfinite(depth)):
            return
        if depth < self.depth[y][x] - 1e-7 or (
                abs(depth - self.depth[y][x]) <= 1e-7 and priority > self.priority[y][x]):
            self.depth[y][x] = depth
            self.priority[y][x] = priority
            self.cells[y][x] = char

    def frame(self) -> str:
        # Explicit LF, including final LF. Files are written as bytes on Windows.
        return "\n".join("".join(row) for row in self.cells) + "\n"


@dataclass(frozen=True, slots=True)
class Projected:
    x: float
    y: float
    depth: float
    size_scale: float


class Projector:
    def __init__(self, tree: Tree, options: RenderOptions):
        self.options = options
        self.center_y = tree.height * 0.50
        self.height = tree.height
        self.center_w = max(p.w for p in tree.vertices) * 0.5
        radial = max(math.hypot(p.x, p.z) for p in tree.vertices) + 0.8
        self.radius = max(radial, tree.height * 0.58)
        self.distance = self.radius * 3.6
        self.distance4 = self.radius * 3.3
        self.matrix = rotation4(math.radians(options.angle4), options.plane)
        self.yaw, self.pitch = math.radians(options.yaw), math.radians(options.pitch)
        self.scale = min(max(0.1, options.width - 4) * options.aspect / (2 * radial),
                         max(0.1, options.height - 3) / (tree.height * 1.12)) * options.zoom

    def __call__(self, point: Point4) -> Projected | None:
        o = self.options
        height_fraction = max(0.0, point.y / self.height)
        phase = (o.time % (math.tau / 1.7)) * 1.7
        wind = 0.27 * height_fraction ** 1.7 * (math.sin(phase + point.y * 0.7) - math.sin(point.y * 0.7))
        p = Point4(point.x + wind, point.y - self.center_y, point.z + wind * 0.35, point.w - self.center_w)
        four_scale = 1.0
        if o.mode == "4d":
            p = transform4(p, self.matrix)
            xyz = project4(p, self.distance4)
            if xyz is None:
                return None
            four_scale = self.distance4 / (self.distance4 - p.w)
            x, y, z = xyz
        else:
            x, y, z = p.x, p.y, p.z
        if o.mode == "2d":
            perspective, depth = 1.0, self.distance - z
        else:
            x, y, z = rotate3(x, y, z, self.yaw, self.pitch)
            depth = self.distance - z
            if depth < 0.2:
                return None
            perspective = self.distance / depth
        size = self.scale * perspective * four_scale
        return Projected((o.width - 1) / 2 + x * self.scale * perspective / o.aspect,
                         (o.height - 1) / 2 - y * self.scale * perspective,
                         depth, size)


def _clip_line(a: Projected, b: Projected, width: int, height: int, margin: float) -> tuple[float, float] | None:
    """Liang-Barsky screen clipping bounds work even at maximum zoom."""
    lo, hi = 0.0, 1.0
    dx, dy = b.x - a.x, b.y - a.y
    for p, q in ((-dx, a.x + margin), (dx, width - 1 + margin - a.x),
                 (-dy, a.y + margin), (dy, height - 1 + margin - a.y)):
        if abs(p) < 1e-12:
            if q < 0:
                return None
        elif p < 0:
            lo = max(lo, q / p)
        else:
            hi = min(hi, q / p)
    return None if lo > hi else (lo, hi)


def draw_segment(buffer: DepthBuffer, a: Projected, b: Projected,
                 r0: float, r1: float, aspect: float, distance: float) -> None:
    """Rasterize a tapered tube; interpolate inverse depth for perspective correctness."""
    margin = max(r0 * a.size_scale, r1 * b.size_scale) / aspect + 1
    clipped = _clip_line(a, b, buffer.width, buffer.height, margin)
    if clipped is None:
        return
    lo, hi = clipped
    dx, dy = b.x - a.x, b.y - a.y
    steps = max(1, math.ceil(max(abs(dx), abs(dy)) * (hi - lo) * 1.8))
    direction = "|" if abs(dy) > abs(dx) * 0.85 else "-" if abs(dy) < abs(dx) * 0.24 else ("\\" if dx * dy > 0 else "/")
    for step in range(steps + 1):
        t = lo + (hi - lo) * step / steps
        x, y = a.x + t * dx, a.y + t * dy
        inv_depth = (1 - t) / a.depth + t / b.depth
        depth = 1 / inv_depth
        u = (t / b.depth) / inv_depth
        radius = (r0 + (r1 - r0) * u) * (a.size_scale + (b.size_scale - a.size_scale) * t)
        ry = max(0.44, radius)
        rx = max(0.48, radius / aspect)
        for py in range(max(0, math.ceil(y - ry)), min(buffer.height - 1, math.floor(y + ry)) + 1):
            for px in range(max(0, math.ceil(x - rx)), min(buffer.width - 1, math.floor(x + rx)) + 1):
                norm = ((px - x) / rx) ** 2 + ((py - y) / ry) ** 2
                if norm <= 1.15:
                    light = (px - x) / rx
                    char = direction
                    if radius > 0.6:
                        char = "#" if light < -0.22 else "%" if light < 0.30 else ":"
                    elif depth > distance * 1.10:
                        char = ":"
                    buffer.put(px, py, depth - radius * 0.06, char, 2)
        # A centerline guarantees even sub-cell twigs have connected coverage.
        buffer.put(round(x), round(y), depth - radius * 0.06, direction if radius < 0.6 else "#", 2)


def render_tree(tree: Tree, options: RenderOptions | None = None) -> str:
    o = options or RenderOptions()
    buffer = DepthBuffer(o.width, o.height)
    projector = Projector(tree, o)
    projected = [projector(p) for p in tree.vertices]
    for leaf in tree.leaves:
        p = projector(leaf.point)
        if p is None:
            continue
        char = "." if p.depth > projector.distance * 1.08 else ("'" if leaf.light < 0.4 else "o" if leaf.light > 0.82 else "*")
        buffer.put(round(p.x), round(p.y), p.depth, char, 0)
    for segment in tree.segments:
        a, b = projected[segment.start], projected[segment.end]
        if a is not None and b is not None:
            draw_segment(buffer, a, b, segment.radius_start, segment.radius_end, o.aspect, projector.distance)
    return buffer.frame()
