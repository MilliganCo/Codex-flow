"""Explicit XW rotation followed by guarded 4D and 3D perspective."""
import math
from .model import Point


def xw_matrix(angle: float) -> tuple[tuple[float, ...], ...]:
    c, s = math.cos(angle), math.sin(angle)
    return ((c, 0., 0., -s), (0., 1., 0., 0.),
            (0., 0., 1., 0.), (s, 0., 0., c))


def rotate_xw(p: Point, angle: float) -> Point:
    c, s = math.cos(angle), math.sin(angle)
    return Point(c * p.x - s * p.w, p.y, p.z, s * p.x + c * p.w)


def perspective_factor(coordinate: float, distance: float) -> float:
    # Near-plane clamp, also bounds extreme caller-provided coordinates.
    return distance / max(distance - coordinate, distance * .15)


def project(p: Point, mode: str, yaw: float, pitch: float, angle4: float):
    x, y, z = p.x, p.y - 5.5, p.z
    scale4 = 1.
    if mode == "4d":
        q = rotate_xw(p, angle4)
        scale4 = perspective_factor(q.w, 24.)
        x, y, z = q.x * scale4, (q.y - 5.5) * scale4, q.z * scale4
    if mode == "2d":
        return x, y, 32. - z, 1.
    c, s = math.cos(yaw), math.sin(yaw)
    x, z = c * x + s * z, -s * x + c * z
    c, s = math.cos(pitch), math.sin(pitch)
    y, z = c * y - s * z, s * y + c * z
    factor = perspective_factor(z, 32.)
    return x * factor, y * factor, max(4.8, 32. - z), factor * scale4
