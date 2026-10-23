"""Small, dependency-free vector and projection primitives.

Coordinates use Y up; camera Z increases away from the viewer. All public
angles are in degrees. Projection functions reject points at/behind a near
plane instead of allowing unbounded perspective division.
"""

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float
    y: float
    z: float

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scale: float) -> "Vec3":
        return Vec3(self.x * scale, self.y * scale, self.z * scale)

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec3") -> "Vec3":
        return Vec3(self.y * other.z - self.z * other.y,
                    self.z * other.x - self.x * other.z,
                    self.x * other.y - self.y * other.x)

    def length(self) -> float:
        return math.sqrt(self.dot(self))

    def unit(self) -> "Vec3":
        length = self.length()
        return self * (1.0 / length) if length > 1e-12 else Vec3(0, 1, 0)


@dataclass(frozen=True, slots=True)
class Vec4:
    x: float
    y: float
    z: float
    w: float

    @property
    def xyz(self) -> Vec3:
        return Vec3(self.x, self.y, self.z)


def rotation4(angle: float, plane: str = "xw") -> tuple[tuple[float, ...], ...]:
    """A proper orthogonal rotation; W really mixes with a spatial axis."""
    if plane not in ("xw", "yw", "zw"):
        raise ValueError("4D plane must be xw, yw or zw")
    axis = "xyz".index(plane[0])
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    rows = [[float(i == j) for j in range(4)] for i in range(4)]
    rows[axis][axis] = rows[3][3] = c
    rows[axis][3], rows[3][axis] = -s, s
    return tuple(tuple(row) for row in rows)


def transform4(point: Vec4, matrix: tuple[tuple[float, ...], ...]) -> Vec4:
    values = (point.x, point.y, point.z, point.w)
    return Vec4(*(sum(a * b for a, b in zip(row, values)) for row in matrix))


def project4(point: Vec4, distance: float = 32.0, near: float = 0.5) -> Vec3 | None:
    denominator = distance - point.w
    if not math.isfinite(denominator) or denominator <= near:
        return None
    return point.xyz * (distance / denominator)


def camera_rotate(point: Vec3, yaw: float, pitch: float) -> Vec3:
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    x, z = cy * point.x + sy * point.z, -sy * point.x + cy * point.z
    return Vec3(x, cp * point.y - sp * z, sp * point.y + cp * z)


def perspective(point: Vec3, distance: float, near: float = 0.5) -> tuple[float, float, float, float] | None:
    depth = distance + point.z
    if not math.isfinite(depth) or depth <= near:
        return None
    factor = distance / depth
    return point.x * factor, point.y * factor, depth, factor
