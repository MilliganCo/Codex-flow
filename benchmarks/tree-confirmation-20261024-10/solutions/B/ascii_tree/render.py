"""ASCII capsule rasterizer with per-cell surface depth, aspect correction and lighting."""
from dataclasses import dataclass
import math

from .geometry import finite, perspective, project_4d, rotate_3d, rotate_xw


@dataclass(frozen=True, slots=True)
class Camera:
    mode: str = "3d"
    yaw: float = 25.
    pitch: float = -7.
    angle4d: float = 0.
    zoom: float = 1.
    aspect: float = .5  # cell width / cell height
    time: float = 0.

    def validate(self):
        if self.mode not in ("2d", "3d", "4d"):
            raise ValueError("Mode must be 2d, 3d or 4d")
        finite(self.yaw, self.pitch, self.angle4d, self.zoom, self.aspect, self.time)
        if not .1 <= self.zoom <= 8:
            raise ValueError("Zoom must be between 0.1 and 8")
        if not .2 <= self.aspect <= 1:
            raise ValueError("Cell aspect must be between 0.2 and 1")
        if abs(self.time) > 1e9:
            raise ValueError("Animation time must be within +/- 1e9 seconds")


class Raster:
    """Largest Z is nearest; stable tie-break makes order-independent occlusion."""
    def __init__(self, width, height, aspect=.5):
        if (isinstance(width, bool) or isinstance(height, bool)
                or not isinstance(width, int) or not isinstance(height, int)
                or not 1 <= width <= 1000 or not 1 <= height <= 500
                or width * height > 250_000):
            raise ValueError("Frame must be 1..1000 by 1..500, at most 250000 cells")
        finite(aspect)
        if not .2 <= aspect <= 1:
            raise ValueError("Invalid cell aspect")
        self.width, self.height, self.aspect = width, height, aspect
        self.chars = [[" "] * width for _ in range(height)]
        self.depth = [[-math.inf] * width for _ in range(height)]
        self.owners = [[2**63] * width for _ in range(height)]

    def put(self, x, y, depth, char, owner=0):
        if not math.isfinite(depth):
            raise ValueError("Depth must be finite")
        if len(char) != 1 or not 32 <= ord(char) <= 126:
            raise ValueError("Raster accepts printable ASCII only")
        if 0 <= x < self.width and 0 <= y < self.height:
            old = self.depth[y][x]
            if depth > old or (depth == old and owner < self.owners[y][x]):
                self.depth[y][x], self.chars[y][x], self.owners[y][x] = depth, char, owner

    def segment(self, a, b, r0, r1, owner, glyph=None):
        """Projected endpoints (column,row,depth); radii are in row units."""
        finite(*a, *b, r0, r1)
        if r0 <= 0 or r1 <= 0:
            raise ValueError("Radii must be positive")
        aspect = self.aspect
        ax, ay, az = a
        bx, by, bz = b
        dx, dy = (bx - ax) * aspect, by - ay
        length2 = dx * dx + dy * dy
        radius = max(r0, r1, .36)
        x0 = max(0, math.floor(min(ax, bx) - radius / aspect - 1))
        x1 = min(self.width - 1, math.ceil(max(ax, bx) + radius / aspect + 1))
        y0 = max(0, math.floor(min(ay, by) - radius - 1))
        y1 = min(self.height - 1, math.ceil(max(ay, by) + radius + 1))
        if glyph is None:
            slope = abs(dy) / (abs(dx) + 1e-9)
            glyph = "|" if slope > 1.9 else ("_" if slope < .30 else ("\\" if dx * dy > 0 else "/"))
        # A DDA skeleton guarantees a continuous 8-connected thin branch even
        # halfway between two text rows. The capsule adds the physical thickness.
        # Clip iteration count to viewport scale; off-screen endpoints are safe.
        span = max(abs(bx - ax), abs(by - ay))
        if span > 1e-9:
            low, high = 0., 1.
            for origin, delta, limit in ((ax, bx - ax, self.width), (ay, by - ay, self.height)):
                if abs(delta) < 1e-12:
                    if origin < -radius / aspect or origin > limit + radius / aspect:
                        low, high = 1., 0.
                else:
                    t0, t1 = sorted(((-1 - origin) / delta, (limit - origin) / delta))
                    low, high = max(low, t0), min(high, t1)
            if low <= high:
                steps = max(1, math.ceil(span * (high - low)))
                for i in range(steps + 1):
                    t = low + (high - low) * i / steps
                    r = r0 + (r1 - r0) * t
                    char = "#" if r > .68 and glyph in "|_/\\" else glyph
                    self.put(round(ax + (bx - ax) * t), round(ay + (by - ay) * t),
                             az + (bz - az) * t + max(.36, r) / 30, char, owner)
        else:
            self.put(round(ax), round(ay), max(az, bz) + radius / 30, glyph, owner)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                px, py = (x - ax) * aspect, y - ay
                t = 0. if length2 < 1e-12 else max(0., min(1., (px * dx + py * dy) / length2))
                distance2 = (px - t * dx) ** 2 + (py - t * dy) ** 2
                r = max(.36, r0 + (r1 - r0) * t)
                if distance2 <= r * r:
                    # Front of a round branch, with a consistent directional light.
                    front = math.sqrt(max(0., r * r - distance2))
                    depth = az + t * (bz - az) + front / 30
                    char = glyph
                    if r > .68:
                        light = .65 * front / r - .35 * (px - t * dx) / r
                        char = "@" if light < .05 else ("#" if light < .60 else "%")
                    self.put(x, y, depth, char, owner)

    def text(self):
        return "\n".join("".join(row) for row in self.chars) + "\n"


def render(tree, width=100, height=40, camera=None):
    camera = camera or Camera()
    camera.validate()
    raster = Raster(width, height, camera.aspect)
    if not tree.segments:
        raise ValueError("Tree has no segments")
    # Normalize once from the unchanged object, never refit after camera rotation.
    points = [s.end for s in tree.segments] + [tree.segments[0].start]
    center_y = max(p[1] for p in points) / 2
    bound = max(math.sqrt(p[0]**2 + (p[1]-center_y)**2 + p[2]**2) for p in points) * 1.08
    if not math.isfinite(bound) or bound < 1e-9:
        raise ValueError("Tree bounds must be finite and nonzero")
    scale = max(.1, min(width * camera.aspect * .45, height * .44)) * camera.zoom
    yaw = math.radians(math.remainder(camera.yaw + camera.time * 14, 360))
    pitch = math.radians(math.remainder(camera.pitch, 360))
    angle = math.radians(math.remainder(camera.angle4d + camera.time * 19, 360))

    def project(p):
        finite(*p)
        q = (p[0] / bound, (p[1] - center_y) / bound, p[2] / bound,
             (p[3] - .5) * 1.35)
        if camera.mode == "2d" and camera.time:
            q = (q[0] + .025 * math.sin(camera.time * 1.4) * (q[1] + 1)**2, *q[1:])
        factor4 = 1.
        if camera.mode == "4d":
            rotated = rotate_xw(q, angle)
            spatial = project_4d(rotated)
            if spatial is None:
                return None
            factor4 = 4 / (4 - rotated[3])
        else:
            spatial = q[:3]
        if camera.mode == "2d":
            projected = (*spatial[:2], spatial[2], 1.)
        else:
            projected = perspective(rotate_3d(spatial, yaw, pitch))
        if projected is None:
            return None
        x, y, z, factor3 = projected
        return (width / 2 - .5 + x * scale / camera.aspect,
                height / 2 - .5 - y * scale, z,
                scale / bound * factor3 * factor4)

    # Wood and foliage share one depth buffer. Sparse leaf sprites leave branch gaps.
    for index, segment in enumerate(tree.segments):
        a, b = project(segment.start), project(segment.end)
        if a is not None and b is not None:
            raster.segment(a[:3], b[:3], segment.radius_start * a[3],
                           segment.radius_end * b[3], index)
    for index, leaf in enumerate(tree.leaves):
        p = project(leaf.point)
        if p is not None:
            x, y, z, _ = p
            char = "." if z < -.25 else ("'" if leaf.tone < .3 else ("o" if leaf.tone > .84 else ":"))
            raster.put(round(x), round(y), z, char, len(tree.segments) + index)
    return raster.text()
