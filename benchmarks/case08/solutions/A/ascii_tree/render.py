"""ASCII capsule rasterizer with a per-character depth buffer."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .geometry import Point4, Tree
from .math4d import CAMERA_DISTANCE, camera_point, project_camera


@dataclass(frozen=True, slots=True)
class RenderOptions:
    mode: str = "3d"
    width: int = 100
    height: int = 40
    yaw: float = 25.0
    pitch: float = -7.0
    angle4: float = 0.0
    zoom: float = 1.0
    aspect: float = 2.0
    time: float = 0.0

    def __post_init__(self) -> None:
        if self.mode not in ("2d", "3d", "4d"):
            raise ValueError("mode must be 2d, 3d or 4d")
        if not (1 <= self.width <= 500 and 1 <= self.height <= 200):
            raise ValueError("frame must be 1..500 columns by 1..200 rows")
        if not all(math.isfinite(v) for v in
                   (self.yaw, self.pitch, self.angle4, self.zoom, self.aspect, self.time)):
            raise ValueError("render parameters must be finite")
        if not 0.1 <= self.zoom <= 8.0:
            raise ValueError("zoom must be between 0.1 and 8")
        if not 0.5 <= self.aspect <= 4.0:
            raise ValueError("aspect must be between 0.5 and 4")


class DepthBuffer:
    """Smaller Z wins. Stable tie breaking makes order-independent crossings."""

    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.chars = [[" "] * width for _ in range(height)]
        self.depth = [[math.inf] * width for _ in range(height)]

    def put(self, x: int, y: int, depth: float, char: str) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        if not math.isfinite(depth):
            return
        old = self.depth[y][x]
        if depth < old - 1e-9 or (abs(depth - old) <= 1e-9 and char > self.chars[y][x]):
            self.depth[y][x], self.chars[y][x] = depth, char

    def lines(self) -> tuple[str, ...]:
        return tuple("".join(row) for row in self.chars)


def _clip_line(x0: float, y0: float, x1: float, y1: float,
               width: int, height: int, margin: float) -> tuple[float, float] | None:
    """Liang-Barsky clipping bounds work even for huge offscreen segments."""
    dx, dy = x1 - x0, y1 - y0
    lower, upper = 0.0, 1.0
    for p, q in ((-dx, x0 + margin), (dx, width - 1 + margin - x0),
                 (-dy, y0 + margin), (dy, height - 1 + margin - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return None
        elif p < 0:
            lower = max(lower, q / p)
        else:
            upper = min(upper, q / p)
        if lower > upper:
            return None
    return lower, upper


def draw_segment(buffer: DepthBuffer, a: tuple[float, float, float, float],
                 b: tuple[float, float, float, float], radius0: float, radius1: float,
                 aspect: float = 2.0, char: str | None = None,
                 perspective: bool = True) -> None:
    """Draw a tapered capsule; depth interpolates reciprocally in perspective.

    Public to allow controlled occlusion tests without random tree geometry.
    Radii are world-space; a/b contain screen x/y, depth and projection scale.
    """
    x0, y0, z0, scale0 = a
    x1, y1, z1, scale1 = b
    dx, dy = x1 - x0, y1 - y0
    max_radius = min(buffer.width, max(radius0 * scale0, radius1 * scale1))
    interval = _clip_line(x0, y0, x1, y1, buffer.width, buffer.height, max_radius + 1)
    if interval is None:
        return
    lo, hi = interval
    steps = max(1, math.ceil(max(abs(dx), abs(dy)) * (hi - lo) * 1.8))
    orientation = "|" if abs(dy) * aspect > abs(dx) * 1.6 else (
        "-" if abs(dx) > abs(dy) * aspect * 2.4 else ("\\" if dx * dy > 0 else "/"))
    # A world-fixed light source makes branch faces and camera depth readable.
    for step in range(steps + 1):
        t = lo + (hi - lo) * step / steps
        x, y = x0 + dx * t, y0 + dy * t
        if perspective:
            inverse = (1.0 - t) / z0 + t / z1
            depth = 1.0 / inverse
            u = (t / z1) / inverse
        else:
            depth, u = z0 + (z1 - z0) * t, t
        scale = scale0 + (scale1 - scale0) * t
        radius = (radius0 + (radius1 - radius0) * u) * scale
        rx, ry = max(0.52, radius), max(0.52, radius / aspect)
        left, right = max(0, math.ceil(x - rx)), min(buffer.width - 1, math.floor(x + rx))
        top, bottom = max(0, math.ceil(y - ry)), min(buffer.height - 1, math.floor(y + ry))
        # Nearest-cell centerline keeps sub-pixel twigs connected.
        ink = char or orientation
        buffer.put(round(x), round(y), depth, ink)
        for row in range(top, bottom + 1):
            for col in range(left, right + 1):
                nx, ny = (col - x) / rx, (row - y) / ry
                surface = 1.0 - nx * nx - ny * ny
                if surface < 0:
                    continue
                relief = math.sqrt(surface)
                front = depth - relief * (radius0 + (radius1 - radius0) * u)
                if char:
                    ink = char
                elif radius >= 0.85:
                    depth_offset = depth - 22 if perspective else depth
                    light = max(0.0, min(0.999, 0.50 - 0.27 * nx - 0.12 * ny
                                           + 0.15 * relief - 0.012 * depth_offset))
                    ink = ":+%#@"[int(light * 5)]
                else:
                    ink = orientation
                buffer.put(col, row, front, ink)


def render_frame(tree: Tree, options: RenderOptions | None = None) -> tuple[str, ...]:
    options = options or RenderOptions()
    o = options
    buffer = DepthBuffer(o.width, o.height)
    yaw = math.radians((o.yaw % 360 + (o.time % 30) * 12.0) % 360.0)
    pitch = math.radians(o.pitch % 360.0)
    angle = math.radians((o.angle4 % 360 + (o.time % 22.5) * 16.0) % 360.0)

    def project(p):
        if o.mode == "2d" and o.time != 0:
            phase = (o.time % (math.tau / 1.4)) * 1.4
            wind = math.sin(phase + p.y * 0.2) - math.sin(p.y * 0.2)
            p = Point4(p.x + wind * 0.12 * (max(0, p.y) / 12) ** 2, p.y, p.z, p.w)
        q = camera_point(p, o.mode, yaw, pitch, angle)
        if q is None:
            return None
        return project_camera(q, o.mode, o.width, o.height, o.zoom, o.aspect)

    projected = [project(p) for p in tree.nodes]
    # Sparse leaf samples are small opaque fragments, tested against wood's Z.
    for leaf in tree.leaves:
        if leaf.tone < 0.65:
            continue
        p = project(leaf.point)
        if p is None:
            continue
        x, y, depth, _ = p
        if not (-1 <= x <= o.width and -1 <= y <= o.height):
            continue
        depth_offset = depth if o.mode == "2d" else depth - CAMERA_DISTANCE
        tone = leaf.tone - 0.008 * depth_offset
        glyph = "." if tone < 0.76 else ("'" if tone < 0.86 else ("*" if tone < 0.95 else "o"))
        buffer.put(round(x), round(y), depth - leaf.size, glyph)
    for segment in tree.segments:
        a, b = projected[segment.start], projected[segment.end]
        if a is not None and b is not None:
            draw_segment(buffer, a, b, segment.radius_start, segment.radius_end,
                         o.aspect, perspective=o.mode != "2d")
    return buffer.lines()


def frame_bytes(tree: Tree, options: RenderOptions) -> bytes:
    """Canonical export: fixed-width rows, LF newlines, including final LF."""
    return ("\n".join(render_frame(tree, options)) + "\n").encode("ascii")
