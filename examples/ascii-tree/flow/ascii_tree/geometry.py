"""Small, explicit 3D/4D math. Angles inside this module are radians."""

from __future__ import annotations

import math

Vec3 = tuple[float, float, float]
Vec4 = tuple[float, float, float, float]
Mat4 = tuple[Vec4, Vec4, Vec4, Vec4]
NEAR = 0.08


def add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a: Vec3, scale: float) -> Vec3:
    return (a[0] * scale, a[1] * scale, a[2] * scale)


def unit(a: Vec3) -> Vec3:
    length = math.sqrt(sum(v * v for v in a))
    if length < 1e-12:
        raise ValueError("zero-length direction")
    return mul(a, 1.0 / length)


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def xw_matrix(angle: float) -> Mat4:
    """Proper orthogonal rotation: x'=cx-sw, w'=sx+cw; det=+1."""
    c, s = math.cos(angle), math.sin(angle)
    return ((c, 0.0, 0.0, -s), (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0), (s, 0.0, 0.0, c))


def transform4(point: Vec4, matrix: Mat4) -> Vec4:
    return tuple(sum(a * b for a, b in zip(row, point)) for row in matrix)  # type: ignore[return-value]


def project4(point: Vec4, angle: float, distance: float = 4.0) -> tuple[Vec3, float] | None:
    """4D perspective from +W. Clip the singularity instead of dividing by zero."""
    x, y, z, w = transform4(point, xw_matrix(angle))
    denominator = distance - w
    if denominator <= NEAR:
        return None
    factor = distance / denominator
    return (x * factor, y * factor, z * factor), factor


def camera(point: Vec3, yaw: float, pitch: float) -> Vec3:
    x, y, z = point
    c, s = math.cos(yaw), math.sin(yaw)
    x, z = c * x + s * z, -s * x + c * z
    c, s = math.cos(pitch), math.sin(pitch)
    return x, c * y - s * z, s * y + c * z
