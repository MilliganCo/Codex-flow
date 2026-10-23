"""ASCII capsule rasterizer with a per-cell depth buffer and 2:1 cell aspect."""

from dataclasses import dataclass
import math

from .geometry import Camera, project_4d, rotate_xw
from .model import Point4, Tree


@dataclass(frozen=True, slots=True)
class RenderOptions:
    width: int = 100
    height: int = 40
    mode: str = "3d"
    yaw: float = 25.0
    pitch: float = -7.0
    angle4d: float = 0.0
    zoom: float = 1.0
    aspect: float = 2.0
    time: float = 0.0
    foliage: bool = True

    def validate(self) -> None:
        if not 1 <= self.width <= 500 or not 1 <= self.height <= 250:
            raise ValueError("frame must be between 1x1 and 500x250")
        if self.mode not in ("2d", "3d", "4d"):
            raise ValueError("mode must be 2d, 3d or 4d")
        if not all(math.isfinite(x) for x in (self.yaw, self.pitch, self.angle4d,
                                             self.zoom, self.aspect, self.time)):
            raise ValueError("angles, time, aspect and zoom must be finite")
        if not 0.15 <= self.zoom <= 5 or not 0.5 <= self.aspect <= 4:
            raise ValueError("zoom must be 0.15..5 and aspect 0.5..4")


class FrameBuffer:
    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.cells = [[" "] * width for _ in range(height)]
        self.depth = [[math.inf] * width for _ in range(height)]

    def put(self, x: int, y: int, depth: float, char: str) -> None:
        if 0 <= x < self.width and 0 <= y < self.height and math.isfinite(depth):
            if depth < self.depth[y][x]:
                self.depth[y][x] = depth
                self.cells[y][x] = char

    def text(self) -> str:
        return "\n".join("".join(row) for row in self.cells) + "\n"

    def capsule(self, a: tuple[float, float, float, float],
                b: tuple[float, float, float, float], char: str, aspect: float = 2.0) -> None:
        """Rasterize a tapered segment; depth is reciprocal-interpolated.

        Minimum half-cell coverage keeps subpixel twigs connected. Only the
        viewport's bounded box is visited, even at large zoom or offscreen ends.
        """
        ax, ay, az, ar = a
        bx, by, bz, br = b
        radius = max(ar, br, 0.50)
        x0, x1 = max(0, math.floor(min(ax, bx) - radius * aspect)), min(self.width - 1, math.ceil(max(ax, bx) + radius * aspect))
        y0, y1 = max(0, math.floor(min(ay, by) - radius)), min(self.height - 1, math.ceil(max(ay, by) + radius))
        vx, vy = (bx - ax) / aspect, by - ay
        length2 = vx * vx + vy * vy
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                px, py = (x - ax) / aspect, y - ay
                t = min(1.0, max(0.0, (px * vx + py * vy) / length2)) if length2 > 1e-12 else 0.0
                r = max(0.50, ar + (br - ar) * t)
                if (px - t * vx) ** 2 + (py - t * vy) ** 2 <= r * r:
                    depth = 1.0 / ((1 - t) / max(az, 0.001) + t / max(bz, 0.001))
                    # Front surface, not merely the segment's central axis.
                    self.put(x, y, depth - 0.03 * r, char)


def render_tree(tree: Tree, options: RenderOptions = RenderOptions()) -> str:
    options.validate()
    frame = FrameBuffer(options.width, options.height)
    points = [s.end for s in tree.segments]
    bottom = min(min(s.start.y, s.end.y) for s in tree.segments) - 0.2
    top = max(p.y for p in points) + 0.8
    center_y = (top + bottom) / 2
    extent_y = (top - bottom) / 2
    extent_x = max(math.hypot(p.x, p.z) for p in points) + 0.75
    # Stable model-space framing: rotating does not silently refit the object.
    scale = min(max(0.1, options.height - 3) / (2 * extent_y),
                max(0.1, options.width - 5) / (2 * extent_x * options.aspect)) * options.zoom * 0.88
    if options.mode == "4d":
        # Fixed extra margin for W perspective; independent of the XW angle.
        scale *= 0.75
    camera = Camera(options.yaw + options.time * 14, options.pitch)
    angle4d = options.angle4d + options.time * 9

    def project(point: Point4) -> tuple[float, float, float, float] | None:
        centered = Point4(point.x, point.y - center_y, point.z, point.w)
        radius_factor = 1.0
        xyz = (centered.x, centered.y, centered.z)
        if options.mode == "4d":
            higher = project_4d(rotate_xw(centered, angle4d))
            if higher is None:
                return None
            xyz, radius_factor = higher[:3], higher[3]
        if options.mode == "2d":
            x, y, z = xyz
            # Orthographic front elevation of this same 3D graph.
            projected = (x, y, camera.distance - z, 1.0)
        else:
            projected = camera.project(xyz)
            if projected is None:
                return None
        x, y, depth, factor = projected
        if depth <= 0 or not all(math.isfinite(c) for c in projected):
            return None
        return ((options.width - 1) / 2 + x * scale * options.aspect,
                (options.height - 1) / 2 - y * scale, depth, scale * factor * radius_factor)

    for segment in tree.segments:
        a, b = project(segment.start), project(segment.end)
        if a is None or b is None:
            continue
        dx, dy = (b[0] - a[0]) / options.aspect, b[1] - a[1]
        thickness = max(segment.radius_start * a[3], segment.radius_end * b[3])
        depth = (a[2] + b[2]) / 2
        if thickness > 0.65:
            char = "@" if depth < 31 else "#" if depth < 36 else "%"
        elif thickness > 0.27:
            char = "+" if segment.order >= 2 else "#"
        elif abs(dx) < abs(dy) * 0.45:
            char = "|"
        elif abs(dy) < abs(dx) * 0.4:
            char = "-"
        else:
            char = "\\" if dx * dy > 0 else "/"
        frame.capsule((a[0], a[1], a[2], segment.radius_start * a[3]),
                      (b[0], b[1], b[2], segment.radius_end * b[3]), char, options.aspect)
    if options.foliage:
        for leaf in tree.leaves:
            p = project(leaf.point)
            if p is None:
                continue
            # Sparse individual leaves, with depth and local light variation.
            light = leaf.tone * 0.6 + max(0, min(1, (38 - p[2]) / 16)) * 0.4
            char = "." if light < 0.28 else "'" if light < 0.47 else ":" if light < 0.68 else "*"
            radius = max(0.21, leaf.radius * p[3])
            frame.capsule((p[0], p[1], p[2], radius), (p[0], p[1], p[2], radius), char, options.aspect)
    return frame.text()
