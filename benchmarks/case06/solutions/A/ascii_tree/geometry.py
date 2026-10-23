"""Small, explicit geometry primitives. Angles in this module are radians."""

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class Point4:
    x: float
    y: float
    z: float
    w: float

    def lerp(self, other: "Point4", t: float) -> "Point4":
        return Point4(*(a + (b - a) * t for a, b in zip(self.values(), other.values())))

    def values(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.z, self.w


def rotation4(angle: float, plane: str = "xw") -> tuple[tuple[float, ...], ...]:
    """Orthogonal 4x4 matrix; det=1, inverse is rotation4(-angle)."""
    if plane not in ("xw", "yw", "zw"):
        raise ValueError("plane must be xw, yw or zw")
    i = "xyz".index(plane[0])
    c, s = math.cos(angle), math.sin(angle)
    matrix = [[float(row == col) for col in range(4)] for row in range(4)]
    matrix[i][i], matrix[i][3] = c, -s
    matrix[3][i], matrix[3][3] = s, c
    return tuple(tuple(row) for row in matrix)


def transform4(point: Point4, matrix: tuple[tuple[float, ...], ...]) -> Point4:
    return Point4(*(sum(a * b for a, b in zip(row, point.values())) for row in matrix))


def project4(point: Point4, distance: float, near: float = 0.2) -> tuple[float, float, float] | None:
    """4D eye at +W; reject points at or behind its near hyperplane."""
    denominator = distance - point.w
    if denominator < near:
        return None
    factor = distance / denominator
    return point.x * factor, point.y * factor, point.z * factor


def rotate3(x: float, y: float, z: float, yaw: float, pitch: float) -> tuple[float, float, float]:
    c, s = math.cos(yaw), math.sin(yaw)
    x, z = c * x + s * z, -s * x + c * z
    c, s = math.cos(pitch), math.sin(pitch)
    return x, c * y - s * z, s * y + c * z
