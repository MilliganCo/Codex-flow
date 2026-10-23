"""Pure rotations and perspective projections; all public angles are degrees."""

from dataclasses import dataclass
import math

from .model import Vec3, Vec4


def xw_matrix(angle: float) -> tuple[tuple[float, ...], ...]:
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return ((c, 0, 0, -s), (0, 1, 0, 0), (0, 0, 1, 0), (s, 0, 0, c))


def rotate_xw(p: Vec4, angle: float) -> Vec4:
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return (p[0] * c - p[3] * s, p[1], p[2], p[0] * s + p[3] * c)


def project_4d(p: Vec4, angle: float, distance: float = 18.0) -> Vec3:
    q = rotate_xw(p, angle)
    # The generated tree is inside the 4D eye distance. Clamp the near plane
    # for callers supplying arbitrary geometry, rather than dividing by zero.
    factor = distance / max(0.5, distance - q[3])
    return (q[0] * factor, q[1] * factor, q[2] * factor)


def rotate_camera(p: Vec3, yaw: float, pitch: float) -> Vec3:
    a, b = math.radians(yaw), math.radians(pitch)
    x = p[0] * math.cos(a) + p[2] * math.sin(a)
    z = -p[0] * math.sin(a) + p[2] * math.cos(a)
    return (x, p[1] * math.cos(b) - z * math.sin(b),
            p[1] * math.sin(b) + z * math.cos(b))


@dataclass(frozen=True, slots=True)
class Camera:
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
        if not 1 <= self.width <= 1000 or not 1 <= self.height <= 500:
            raise ValueError("frame size must be 1..1000 columns and 1..500 rows")
        if self.mode not in ("2d", "3d", "4d"):
            raise ValueError("mode must be 2d, 3d or 4d")
        if not all(math.isfinite(v) for v in
                   (self.yaw, self.pitch, self.angle4d, self.zoom, self.aspect, self.time)):
            raise ValueError("camera parameters must be finite")
        if not 0.15 <= self.zoom <= 5 or not 0.5 <= self.aspect <= 4:
            raise ValueError("zoom must be 0.15..5; aspect must be 0.5..4")
