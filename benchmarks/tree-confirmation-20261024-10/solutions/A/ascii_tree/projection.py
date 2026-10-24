"""Explicit XW rotation, 4D perspective, then a conventional 3D camera."""

from dataclasses import dataclass
import math

from .geometry import Point4, Tree


def xw_matrix(degrees: float) -> tuple[tuple[float, ...], ...]:
    angle = math.radians(degrees % 360)
    c, s = math.cos(angle), math.sin(angle)
    return ((c, 0.0, 0.0, -s), (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0), (s, 0.0, 0.0, c))


def rotate_xw(point: Point4, degrees: float) -> Point4:
    matrix = xw_matrix(degrees)
    values = (point.x, point.y, point.z, point.w)
    return Point4(*(sum(a * b for a, b in zip(row, values)) for row in matrix))


def perspective4(point: Point4, distance: float) -> tuple[float, float, float, float] | None:
    """Return XYZ and the radius magnification, clipping at the near plane."""
    denominator = distance - point.w
    if distance <= 0 or denominator <= max(1e-6, distance * 0.05):
        return None
    scale = distance / denominator
    return point.x * scale, point.y * scale, point.z * scale, scale


@dataclass(frozen=True, slots=True)
class RenderOptions:
    width: int = 100
    height: int = 40
    mode: str = "3d"
    yaw: float = 25.0
    pitch: float = 8.0
    angle4: float = 0.0
    zoom: float = 1.0
    aspect: float = 2.0
    time: float = 0.0

    def __post_init__(self) -> None:
        if not (1 <= self.width <= 500 and 1 <= self.height <= 240):
            raise ValueError("frame size must be 1..500 columns by 1..240 rows")
        if self.mode not in ("2d", "3d", "4d"):
            raise ValueError("mode must be 2d, 3d or 4d")
        values = (self.yaw, self.pitch, self.angle4, self.zoom, self.aspect, self.time)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("camera and time values must be finite")
        if not (0.15 <= self.zoom <= 5.0 and 0.5 <= self.aspect <= 4.0):
            raise ValueError("zoom must be 0.15..5 and aspect must be 0.5..4")
        if self.time < 0:
            raise ValueError("time must be nonnegative")


@dataclass(frozen=True, slots=True)
class ScreenPoint:
    x: float
    y: float
    depth: float
    radius_scale: float


class Projector:
    def __init__(self, tree: Tree, options: RenderOptions):
        self.options = options
        low, high, radial = tree.bounds
        self.height = max(high - low, 1.0)
        self.center_y = (high + low) / 2
        self.center_w = (max(p.w for p in tree.vertices) + min(p.w for p in tree.vertices)) / 2
        self.radius = max(self.height * 0.65, radial, 1.0)
        # Fixed framing for this object: rotations do not silently refit the view.
        fit_width = max(radial * 2.25, self.height * 0.88)
        self.scale = max(0.01, min(max(1, options.width - 4) / (fit_width * options.aspect),
                                    max(1, options.height - 3) / (self.height * 1.12))) * options.zoom
        self.distance = self.radius * 4.0
        self.distance4 = self.radius * 4.0
        yaw = math.radians(options.yaw % 360)
        pitch = math.radians(options.pitch % 360)
        self.cy, self.sy = math.cos(yaw), math.sin(yaw)
        self.cp, self.sp = math.cos(pitch), math.sin(pitch)
        angle = math.radians(options.angle4 % 360)
        self.c4, self.s4 = math.cos(angle), math.sin(angle)

    def project(self, point: Point4) -> ScreenPoint | None:
        options = self.options
        x, y, z = point.x, point.y - self.center_y, point.z
        if options.time:
            # A deterministic bend, identical for shared segment endpoints.
            phase = (options.time % 10000) * 1.7 + point.y * 0.34
            x += math.sin(phase) * (max(0, point.y) / self.height) ** 2 * 0.24
        magnification = 1.0
        if options.mode == "4d":
            w = point.w - self.center_w
            rotated = Point4(x * self.c4 - w * self.s4, y, z,
                             x * self.s4 + w * self.c4)
            result = perspective4(rotated, self.distance4)
            if result is None:
                return None
            x, y, z, magnification = result
        if options.mode != "2d":
            x, z = x * self.cy + z * self.sy, -x * self.sy + z * self.cy
            y, z = y * self.cp - z * self.sp, y * self.sp + z * self.cp
            depth = self.distance - z
            if depth <= self.distance * 0.05:
                return None
            factor = self.distance / depth
            x, y = x * factor, y * factor
            magnification *= factor
        else:
            depth = self.distance
        return ScreenPoint((options.width - 1) / 2 + x * self.scale * options.aspect,
                           (options.height - 1) / 2 - y * self.scale,
                           depth, self.scale * magnification)
