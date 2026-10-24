"""ASCII rasterization with tapered tubes and a per-cell depth buffer."""

from dataclasses import dataclass
import math

from .geometry import Tree
from .projection import Projector, RenderOptions, ScreenPoint


@dataclass(frozen=True, slots=True)
class Frame:
    rows: tuple[str, ...]

    def text(self) -> str:
        """Exactly H LF-terminated rows of W printable ASCII characters."""
        return "\n".join(self.rows) + "\n"

    def bytes(self) -> bytes:
        return self.text().encode("ascii")


class Raster:
    def __init__(self, width: int, height: int, aspect: float = 2.0):
        self.width, self.height, self.aspect = width, height, aspect
        self.cells = [[" "] * width for _ in range(height)]
        self.depth = [[math.inf] * width for _ in range(height)]
        self.priority = [[-1] * width for _ in range(height)]

    def put(self, x: int, y: int, depth: float, glyph: str, priority: int = 0) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height) or not math.isfinite(depth):
            return
        old = self.depth[y][x]
        if depth < old - 1e-7 or (abs(depth - old) <= 1e-7 and priority > self.priority[y][x]):
            self.cells[y][x] = glyph
            self.depth[y][x] = depth
            self.priority[y][x] = priority

    def branch(self, a: ScreenPoint, b: ScreenPoint, r0: float, r1: float,
               order: int, flat: bool = False) -> None:
        dx, dy = b.x - a.x, b.y - a.y
        # Bound work even when a zoomed or tilted branch is mostly off screen.
        margin = max(r0 * a.radius_scale, r1 * b.radius_scale) * self.aspect + 1
        left, right = -margin, self.width - 1 + margin
        top, bottom = -margin, self.height - 1 + margin
        t0, t1 = 0.0, 1.0
        for p, q in ((-dx, a.x - left), (dx, right - a.x),
                     (-dy, a.y - top), (dy, bottom - a.y)):
            if abs(p) < 1e-12:
                if q < 0:
                    return
            elif p < 0:
                t0 = max(t0, q / p)
            else:
                t1 = min(t1, q / p)
        if t0 > t1:
            return
        steps = max(1, math.ceil(max(abs(dx), abs(dy)) * (t1 - t0) * 2.2))
        if abs(dx) > abs(dy) * 2.2:
            twig = "-"
        elif abs(dy) > abs(dx) * 1.8:
            twig = "|"
        else:
            twig = "\\" if dx * dy > 0 else "/"
        for step in range(steps + 1):
            t = t0 + (t1 - t0) * step / steps
            x, y = a.x + dx * t, a.y + dy * t
            # Inverse depth interpolation gives proper projected depth ordering.
            inv_depth = (1 - t) / a.depth + t / b.depth
            depth = 1 / inv_depth
            world_t = (t / b.depth) / inv_depth
            radius = r0 * (1 - world_t) + r1 * world_t
            size = radius * (a.radius_scale * (1 - t) + b.radius_scale * t)
            rx, ry = max(0.52, size * self.aspect), max(0.48, size)
            for iy in range(max(0, math.ceil(y - ry)), min(self.height - 1, math.floor(y + ry)) + 1):
                for ix in range(max(0, math.ceil(x - rx)), min(self.width - 1, math.floor(x + rx)) + 1):
                    nx, ny = (ix - x) / rx, (iy - y) / ry
                    distance2 = nx * nx + ny * ny
                    if distance2 <= 1.12:
                        if size * self.aspect < 0.85:
                            glyph = twig
                        else:
                            light = max(0.0, min(1.0, 0.58 - nx * 0.25 - ny * 0.17
                                                 + (a.depth - depth) * 0.025))
                            glyph = "+%#@"[min(3, int(light * 4))]
                        surface = depth - radius * math.sqrt(max(0, 1 - distance2))
                        self.put(ix, iy, 0.0 if flat else surface, glyph, 10 - order)
            # A sub-cell twig still gets a connected 8-neighbour centerline.
            self.put(round(x), round(y), 0.0 if flat else depth - radius,
                     twig if size * self.aspect < 0.85 else "#", 10 - order)

    def frame(self) -> Frame:
        return Frame(tuple("".join(row) for row in self.cells))


def render_tree(tree: Tree, options: RenderOptions | None = None) -> Frame:
    options = options or RenderOptions()
    projector = Projector(tree, options)
    raster = Raster(options.width, options.height, options.aspect)
    flat = options.mode == "2d"
    # Sparse leaflets, not opaque canopy blobs. Near leaves can occlude far wood.
    for leaf in tree.leaves:
        point = projector.project(leaf.position)
        if point is None:
            continue
        light = sum(a * b for a, b in zip(leaf.normal, (-0.45, 0.8, 0.4)))
        depth_shade = (projector.distance - point.depth) / projector.radius
        shade = max(0, min(4, int(2 + light * 1.7 + depth_shade * 0.7)))
        glyph = ".,:*o"[shade]
        raster.put(round(point.x), round(point.y), 2.0 if flat else point.depth, glyph)
    projected = tuple(projector.project(point) for point in tree.vertices)
    for segment in tree.segments:
        a, b = projected[segment.start], projected[segment.end]
        if a is not None and b is not None:
            raster.branch(a, b, segment.radius_start, segment.radius_end, segment.order, flat)
    return raster.frame()
