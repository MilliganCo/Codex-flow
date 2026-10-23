"""Explicit 4D rotation, 4D perspective, and a conventional 3D camera."""

from dataclasses import dataclass
import math

from .model import Point4

NEAR = 0.25


def xw_matrix(degrees: float) -> tuple[tuple[float, ...], ...]:
    angle = math.radians(degrees % 360)
    c, s = math.cos(angle), math.sin(angle)
    return ((c, 0, 0, -s), (0, 1, 0, 0), (0, 0, 1, 0), (s, 0, 0, c))


def rotate_xw(point: Point4, degrees: float) -> Point4:
    matrix = xw_matrix(degrees)
    c, s = matrix[0][0], -matrix[0][3]
    return Point4(c * point.x - s * point.w, point.y, point.z,
                  s * point.x + c * point.w)


def project_4d(point: Point4, distance: float = 24.0) -> tuple[float, float, float, float] | None:
    """Return XYZ plus radius scale; clip at the W eye plane instead of exploding."""
    denominator = distance - point.w
    if not math.isfinite(denominator) or denominator <= NEAR:
        return None
    factor = distance / denominator
    return point.x * factor, point.y * factor, point.z * factor, factor


@dataclass(frozen=True, slots=True)
class Camera:
    yaw: float = 25.0
    pitch: float = -7.0
    distance: float = 34.0

    def transform(self, xyz: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = xyz
        yaw, pitch = math.radians(self.yaw % 360), math.radians(self.pitch % 360)
        x, z = math.cos(yaw) * x + math.sin(yaw) * z, -math.sin(yaw) * x + math.cos(yaw) * z
        y, z = math.cos(pitch) * y - math.sin(pitch) * z, math.sin(pitch) * y + math.cos(pitch) * z
        return x, y, z

    def project(self, xyz: tuple[float, float, float]) -> tuple[float, float, float, float] | None:
        x, y, z = self.transform(xyz)
        depth = self.distance - z
        if not math.isfinite(depth) or depth <= NEAR:
            return None
        factor = self.distance / depth
        return x * factor, y * factor, depth, factor
