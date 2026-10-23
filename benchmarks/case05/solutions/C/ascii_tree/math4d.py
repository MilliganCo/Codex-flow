"""Small, explicit transformations. Angles at the API boundary are in degrees."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class Point4:
    x: float
    y: float
    z: float
    w: float

    def lerp(self, other: Point4, t: float) -> Point4:
        return Point4(*(a + (b - a) * t for a, b in zip(self.values(), other.values())))

    def values(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.z, self.w


def xw_matrix(degrees: float) -> tuple[tuple[float, ...], ...]:
    """An orthogonal, determinant +1 rotation, mixing actual X and W."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return ((c, 0, 0, -s), (0, 1, 0, 0), (0, 0, 1, 0), (s, 0, 0, c))


def rotate_xw(p: Point4, degrees: float) -> Point4:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return Point4(c * p.x - s * p.w, p.y, p.z, s * p.x + c * p.w)


def perspective4(p: Point4, distance: float) -> tuple[float, float, float] | None:
    """Project from an eye on +W; clip its near plane before division."""
    denominator = distance - p.w
    if not math.isfinite(denominator) or denominator <= max(0.05, distance * 0.05):
        return None
    factor = distance / denominator
    result = p.x * factor, p.y * factor, p.z * factor
    return result if all(math.isfinite(v) for v in result) else None


def rotate3(p: tuple[float, float, float], yaw: float, pitch: float) -> tuple[float, float, float]:
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    x, y, z = p
    x, z = cy * x + sy * z, -sy * x + cy * z
    return x, cp * y - sp * z, sp * y + cp * z
