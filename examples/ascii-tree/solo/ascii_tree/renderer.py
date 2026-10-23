"""Cell-aspect-aware software rasterizer with a per-cell depth buffer."""

from dataclasses import dataclass
import math

from .geometry import Vec3, Vec4, rotation4
from .model import Tree

MAX_DIMENSION = 1000
MAX_CELLS = 240_000


@dataclass(frozen=True, slots=True)
class RenderOptions:
    width: int = 100
    height: int = 40
    mode: str = "3d"
    yaw: float = -20.0
    pitch: float = 8.0
    angle4: float = 0.0
    plane: str = "xw"
    zoom: float = 1.0
    aspect: float = 0.5
    time: float = 0.0

    def __post_init__(self):
        if not (1 <= self.width <= MAX_DIMENSION and 1 <= self.height <= MAX_DIMENSION):
            raise ValueError(f"width and height must be in 1..{MAX_DIMENSION}")
        if self.width * self.height > MAX_CELLS:
            raise ValueError(f"frame may contain at most {MAX_CELLS} cells")
        if self.mode not in ("2d", "3d", "4d"):
            raise ValueError("mode must be 2d, 3d or 4d")
        if self.plane not in ("xw", "yw", "zw"):
            raise ValueError("plane must be xw, yw or zw")
        if not all(math.isfinite(v) for v in (self.yaw, self.pitch, self.angle4,
                                               self.zoom, self.aspect, self.time)):
            raise ValueError("render parameters must be finite")
        if not .15 <= self.zoom <= 5:
            raise ValueError("zoom must be in 0.15..5")
        if not .2 <= self.aspect <= 1:
            raise ValueError("aspect must be in 0.2..1 (cell width / cell height)")


@dataclass(frozen=True, slots=True)
class Frame:
    rows: tuple[str, ...]

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    @property
    def height(self) -> int:
        return len(self.rows)

    def text(self) -> str:
        """Canonical export: printable ASCII rows, LF, one final newline."""
        return "\n".join(self.rows) + "\n"


class DepthBuffer:
    """Nearest surface wins; equal depths use a stable material priority.

    A smaller positive camera-space depth is closer. This is independent of
    primitive submission order, including branch/leaf overlap.
    """

    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.chars = [[" "] * width for _ in range(height)]
        self.depth = [[math.inf] * width for _ in range(height)]
        self.priority = [[-1] * width for _ in range(height)]

    def put(self, x: int, y: int, depth: float, char: str, priority: int = 0) -> bool:
        if not (0 <= x < self.width and 0 <= y < self.height and math.isfinite(depth)):
            return False
        old = self.depth[y][x]
        if depth < old - 1e-8 or (abs(depth - old) <= 1e-8 and priority > self.priority[y][x]):
            self.depth[y][x], self.chars[y][x] = depth, char
            self.priority[y][x] = priority
            return True
        return False

    def frame(self) -> Frame:
        return Frame(tuple("".join(row) for row in self.chars))


@dataclass(frozen=True, slots=True)
class ScreenPoint:
    x: float
    y: float
    depth: float
    factor: float


class Projector:
    def __init__(self, tree: Tree, options: RenderOptions):
        self.options = options
        positions = [p.xyz for p in tree.vertices]
        low, high = min(p.y for p in positions), max(p.y for p in positions) + .5
        self.center = Vec3(0, (high + low) / 2, 0)
        horizontal = max(math.hypot(p.x, p.z) for p in positions) * 2 + 1
        vertical = high - low + .6
        self.scale = min(max(1, options.height - 2) / vertical,
                         max(1, options.width - 2) * options.aspect / horizontal) * .86 * options.zoom
        self.distance = max(32.0, vertical * 2.7)
        self.matrix = rotation4(options.angle4 + (options.time % 60) * 6.0, options.plane)
        self.axis = "xyz".index(options.plane[0])
        self.cos4, self.sin4 = self.matrix[self.axis][self.axis], self.matrix[3][self.axis]
        yaw = options.yaw + (options.time % 24) * 15 if options.mode != "2d" else 0
        pitch = options.pitch if options.mode != "2d" else 0
        self.cy, self.sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        self.cp, self.sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))

    def project(self, point: Vec4) -> ScreenPoint | None:
        o = self.options
        x, y, z = point.x, point.y - self.center.y, point.z
        # A continuous bend field preserves shared endpoints and the base.
        if o.time:
            sway = .19 * math.sin((o.time % (math.tau / 1.6)) * 1.6 + point.y * .35)
            x += sway * (max(0, point.y) / max(1, self.center.y * 2)) ** 2
        factor4 = 1.0
        if o.mode == "4d":
            # A rotation in one coordinate plane has just four nontrivial
            # coefficients. Use those exact matrix entries instead of doing
            # sixteen multiplies and allocating temporary vectors per leaf.
            spatial = (x, y, z)[self.axis]
            mixed = self.cos4 * spatial - self.sin4 * point.w
            w = self.sin4 * spatial + self.cos4 * point.w
            if self.axis == 0:
                x = mixed
            elif self.axis == 1:
                y = mixed
            else:
                z = mixed
            denominator = self.distance - w
            if not math.isfinite(denominator) or denominator <= .5:
                return None
            factor4 = self.distance / denominator
            x, y, z = x * factor4, y * factor4, z * factor4
        # Time is deterministic; animation moves the camera, never the graph.
        x, z = self.cy * x + self.sy * z, -self.sy * x + self.cy * z
        y, z = self.cp * y - self.sp * z, self.sp * y + self.cp * z
        if o.mode == "2d":
            depth, factor = self.distance + z, 1.0
        else:
            depth = self.distance + z
            if not math.isfinite(depth) or depth <= .5:
                return None
            factor = self.distance / depth
            x, y = x * factor, y * factor
        return ScreenPoint((o.width - 1) / 2 + x * self.scale / o.aspect,
                           (o.height - 1) / 2 - y * self.scale,
                           depth, factor * factor4)


def _line_clip(a: ScreenPoint, b: ScreenPoint, width: int, height: int,
               margin: float) -> tuple[float, float] | None:
    """Liang-Barsky clipping also bounds work for zoomed/off-screen lines."""
    lower, upper = 0.0, 1.0
    dx, dy = b.x - a.x, b.y - a.y
    for p, q in ((-dx, a.x + margin), (dx, width - 1 + margin - a.x),
                 (-dy, a.y + margin), (dy, height - 1 + margin - a.y)):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        ratio = q / p
        if p < 0:
            lower = max(lower, ratio)
        else:
            upper = min(upper, ratio)
        if lower > upper:
            return None
    return lower, upper


def raster_segment(buffer: DepthBuffer, a: ScreenPoint, b: ScreenPoint,
                   radius_a: float, radius_b: float, scale: float, aspect: float,
                   order: int = 0, perspective_correct: bool = True) -> None:
    """Rasterize tapered cylinders; reciprocal depth interpolates perspective.

    A 0.34-row minimum footprint keeps connected twigs visible at cell scale.
    Cylinder-front depth and directional glyphs provide thickness/light cues.
    """
    max_radius = max(radius_a * a.factor, radius_b * b.factor) * scale
    clipped = _line_clip(a, b, buffer.width, buffer.height, max(1, max_radius / aspect))
    if clipped is None:
        return
    t0, t1 = clipped
    dx, dy = b.x - a.x, b.y - a.y
    steps = max(1, math.ceil(max(abs(dx), abs(dy)) * (t1 - t0) * 1.6))
    # The depth argument is camera-space, regardless of output mode.
    if abs(dy) > abs(dx) * .85:
        thin = "|"
    elif abs(dy) < abs(dx) * .23:
        thin = "_" if order < 2 else "-"
    else:
        thin = "\\" if dx * dy > 0 else "/"
    for step in range(steps + 1):
        t = t0 + (t1 - t0) * step / steps
        x, y = a.x + dx * t, a.y + dy * t
        if perspective_correct:
            inverse = (1 - t) / a.depth + t / b.depth
            depth = 1 / max(inverse, 1e-12)
            world_t = (t / b.depth) / max(inverse, 1e-12)
        else:
            depth, world_t = a.depth * (1 - t) + b.depth * t, t
        radius = radius_a * (1 - world_t) + radius_b * world_t
        factor = a.factor * (1 - t) + b.factor * t
        ry = max(.34, radius * scale * factor)
        rx = max(.48, ry / aspect)
        xmin, xmax = max(0, math.floor(x - rx)), min(buffer.width - 1, math.ceil(x + rx))
        ymin, ymax = max(0, math.floor(y - ry)), min(buffer.height - 1, math.ceil(y + ry))
        # Nearest cell ensures no dropped sub-cell endpoints / disconnected lines.
        buffer.put(round(x), round(y), depth - radius, thin, 5)
        for iy in range(ymin, ymax + 1):
            for ix in range(xmin, xmax + 1):
                distance = ((ix - x) / rx) ** 2 + ((iy - y) / ry) ** 2
                if distance > 1:
                    continue
                surface = depth - radius * math.sqrt(max(0, 1 - distance))
                if ry < .53:
                    glyph = thin
                else:
                    # Side light from upper left; dark, thick bark on the right.
                    light = (ix - x) / rx
                    glyph = "|" if light < -.40 else ("#" if light < .38 else "%")
                    if depth > 43 and glyph == "%":
                        glyph = ":"
                buffer.put(ix, iy, surface, glyph, 5)


def render_tree(tree: Tree, options: RenderOptions | None = None) -> Frame:
    o = options or RenderOptions()
    projector = Projector(tree, o)
    buffer = DepthBuffer(o.width, o.height)
    projected = [projector.project(p) for p in tree.vertices]
    for segment in tree.segments:
        a, b = projected[segment.start], projected[segment.end]
        if a is None or b is None:
            continue
        raster_segment(buffer, a, b, segment.radius_start, segment.radius_end,
                       projector.scale, o.aspect, segment.order, o.mode != "2d")
    for leaf in tree.leaves:
        point = projector.project(leaf.position)
        if point is None:
            continue
        # Each leaf is a small billboard; sparsity preserves the branch skeleton.
        x, y = round(point.x), round(point.y)
        depth_shade = (point.depth - projector.distance) / 5
        shade = max(0, min(4, leaf.tone - round(depth_shade)))
        glyph = (".", "'", ":", "*", "o")[shade]
        buffer.put(x, y, point.depth - leaf.size * .25, glyph, 1)
    root = projected[0]
    if root:
        # Ground is a sparse, far-depth ellipse anchored at the root.
        ground_y = round(root.y + .5)
        for dx in range(-max(2, round(projector.scale * 1.5 / o.aspect)),
                        max(2, round(projector.scale * 1.5 / o.aspect)) + 1):
            buffer.put(round(root.x) + dx, ground_y, projector.distance + 30,
                       "." if dx % 3 else "'", -1)
    return buffer.frame()
