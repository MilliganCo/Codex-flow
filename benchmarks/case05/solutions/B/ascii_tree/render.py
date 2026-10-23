"""ASCII software rasterizer: tapered capsules, sparse leaves and a z-buffer."""

from dataclasses import dataclass
from pathlib import Path
import math

from .geometry import Camera, project_4d, rotate_camera
from .model import Tree, Vec4


@dataclass(frozen=True, slots=True)
class ScreenPoint:
    x: float
    y: float
    depth: float
    scale: float


class Raster:
    """Smaller positive depth wins; equal-depth ties have a stable glyph rule."""

    def __init__(self, width: int, height: int) -> None:
        if not 1 <= width <= 1000 or not 1 <= height <= 500:
            raise ValueError("invalid raster dimensions")
        self.width, self.height = width, height
        self.chars = [[" "] * width for _ in range(height)]
        self.depth = [[math.inf] * width for _ in range(height)]

    def put(self, x: int, y: int, depth: float, glyph: str) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        if not math.isfinite(depth) or depth <= 0:
            return
        old = self.depth[y][x]
        if depth < old - 1e-9 or (abs(depth - old) <= 1e-9
                                  and glyph > self.chars[y][x]):
            self.depth[y][x], self.chars[y][x] = depth, glyph

    def segment(self, a: ScreenPoint, b: ScreenPoint,
                radius_a: float, radius_b: float, aspect: float,
                glyph: str | None = None, perspective: bool = True) -> None:
        """Sample overlapping elliptical cross sections, clipped to the frame.

        Reciprocal depth interpolation follows perspective. The front of each
        cylindrical sample participates in the same depth test as the leaves.
        A forced glyph is useful for synthetic occlusion tests.
        """
        dx, dy = b.x - a.x, b.y - a.y
        steps = min(8000, max(1, math.ceil(max(abs(dx), abs(dy)) * 2)))
        slope = abs(dy) * aspect / max(1e-9, abs(dx))
        twig = "|" if slope > 2.2 else "_" if slope < 0.28 else "\\" if dx * dy > 0 else "/"
        for i in range(steps + 1):
            t = i / steps
            x, y = a.x + dx * t, a.y + dy * t
            inv_depth = (1 - t) / a.depth + t / b.depth
            depth = 1 / inv_depth if perspective else a.depth * (1 - t) + b.depth * t
            if perspective:
                # World-space interpolation parameter for this screen sample.
                u = (t / b.depth) / inv_depth
            else:
                u = t
            radius = radius_a * (1 - u) + radius_b * u
            local_scale = a.scale * (1 - t) + b.scale * t
            ry = max(0.34, radius * local_scale)
            rx = max(0.51, radius * local_scale * aspect)
            if x + rx < 0 or x - rx > self.width - 1 or y + ry < 0 or y - ry > self.height - 1:
                continue
            for py in range(max(0, math.ceil(y - ry)), min(self.height - 1, math.floor(y + ry)) + 1):
                for px in range(max(0, math.ceil(x - rx)), min(self.width - 1, math.floor(x + rx)) + 1):
                    nx, ny = (px - x) / rx, (py - y) / ry
                    d2 = nx * nx + ny * ny
                    if d2 > 1:
                        continue
                    front = math.sqrt(max(0, 1 - d2))
                    surface_depth = depth - radius * front
                    if glyph is None:
                        if radius * local_scale * aspect < 0.85:
                            char = twig
                        else:
                            # Upper-left light and camera depth both affect bark.
                            light = max(0, min(0.999, 0.48 - nx * 0.25 - ny * 0.18
                                               + front * 0.20 + (24 - depth) * 0.018))
                            char = ":oO%#@"[int(light * 6)]
                    else:
                        char = glyph
                    self.put(px, py, surface_depth, char)
            # A sub-cell twig must remain connected even between cell centres.
            # For thick limbs the shaded cross section above already covers it.
            if radius * local_scale < 0.55:
                self.put(round(x), round(y), depth - radius * 0.5, glyph or twig)

    def lines(self) -> tuple[str, ...]:
        return tuple("".join(row) for row in self.chars)


def render(tree: Tree, camera: Camera) -> tuple[str, ...]:
    max_y = max(s.end[1] for s in tree.segments)
    center_y = max_y * 0.48
    raster = Raster(camera.width, camera.height)

    def raw_project(p: Vec4, yaw: float, pitch: float, angle: float,
                    time: float = 0) -> ScreenPoint:
        wind = (0.6 * math.sin(time * 1.7) * max(0, p[1] / max_y) ** 1.8
                if camera.mode == "2d" else 0.0)
        centered = (p[0] + wind, p[1] - center_y, p[2], p[3])
        xyz = project_4d(centered, angle) if camera.mode == "4d" else centered[:3]
        if camera.mode != "2d":
            xyz = rotate_camera(xyz, yaw, pitch)
        depth = max(0.5, 24 - xyz[2])
        factor = 1 if camera.mode == "2d" else 24 / depth
        return ScreenPoint(xyz[0] * factor, xyz[1] * factor, depth, factor)

    # Frame a fixed reference orientation, including the demonstrated XW arc.
    # Perspective can enlarge upper limbs far beyond the raw XY bounding box.
    # The reference is independent of current angles/time, so orbiting never
    # auto-centres or auto-zooms the image. Wide orbits can still need zoom-out.
    points = [tree.segments[0].start] + [s.end for s in tree.segments]
    points += [leaf.position for leaf in tree.leaves]
    reference = [raw_project(p, 25, -8, angle) for p in points
                 for angle in ((0, 45) if camera.mode == "4d" else (0,))]
    left, right = min(p.x for p in reference), max(p.x for p in reference)
    bottom, top = min(p.y for p in reference), max(p.y for p in reference)
    scale = min(max(0.1, camera.height - 4) / max(1, top - bottom),
                max(0.1, camera.width - 5) / (max(1, right - left) * camera.aspect)) * camera.zoom
    center_x, center_screen_y = (left + right) / 2, (bottom + top) / 2

    def project(p: Vec4) -> ScreenPoint:
        q = raw_project(p, camera.yaw, camera.pitch, camera.angle4d, camera.time)
        return ScreenPoint((camera.width - 1) / 2 + (q.x - center_x) * scale * camera.aspect,
                           (camera.height - 1) / 2 - (q.y - center_screen_y) * scale,
                           q.depth, q.scale * scale)

    for leaf in tree.leaves:
        p = project(leaf.position)
        shade = max(0, min(0.999, leaf.tone * 0.65 + (30 - p.depth) * 0.035))
        char = " .,'*:o"[1 + int(shade * 5)]
        raster.put(round(p.x), round(p.y), p.depth, char)
    for segment in tree.segments:
        raster.segment(project(segment.start), project(segment.end),
                       segment.radius_start, segment.radius_end, camera.aspect,
                       perspective=camera.mode != "2d")
    return raster.lines()


def frame_bytes(lines: tuple[str, ...]) -> bytes:
    """Fixed rows, trailing spaces preserved, exactly one LF per row, no ANSI."""
    if not lines or len({len(line) for line in lines}) != 1:
        raise ValueError("frame rows must have equal width")
    if any(not 32 <= ord(char) <= 126 for line in lines for char in line):
        raise ValueError("frame must contain only printable ASCII")
    return ("\n".join(lines) + "\n").encode("ascii")


def export_frame(path: str | Path, lines: tuple[str, ...]) -> None:
    Path(path).write_bytes(frame_bytes(lines))
