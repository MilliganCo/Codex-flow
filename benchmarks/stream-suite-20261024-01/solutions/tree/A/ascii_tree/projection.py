"""Explicit 4D -> 3D perspective followed by a yaw/pitch 3D camera."""

from dataclasses import dataclass
import math

from .model import Point4, Vec3


def rotate_xw(point: Point4, angle: float) -> Point4:
    """A proper orthogonal XW rotation, determinant +1. Angle is in radians."""
    c, s = math.cos(angle), math.sin(angle)
    return Point4(c * point.x - s * point.w, point.y, point.z,
                  s * point.x + c * point.w)


def project_4d(point: Point4, distance: float = 18.0) -> Vec3 | None:
    denominator = distance - point.w
    if denominator < 0.5 or not all(math.isfinite(a) for a in
                                   (point.x, point.y, point.z, point.w)):
        return None
    scale = distance / denominator
    return point.x * scale, point.y * scale, point.z * scale


@dataclass(frozen=True, slots=True)
class Projected:
    x: float
    y: float
    depth: float
    magnification: float


class Projector:
    def __init__(self, center: Point4, width: int, height: int, scale: float,
                 mode: str, yaw: float, pitch: float, angle4d: float,
                 aspect: float = 2.0, time: float = 0.0):
        self.center, self.width, self.height = center, width, height
        self.scale, self.mode, self.aspect = scale, mode, aspect
        self.cy, self.sy = math.cos(yaw), math.sin(yaw)
        self.cp, self.sp = math.cos(pitch), math.sin(pitch)
        self.angle4d = angle4d
        self.time = time

    def __call__(self, point: Point4) -> Projected | None:
        if not all(math.isfinite(v) for v in (point.x, point.y, point.z, point.w)):
            return None
        # A continuous, deterministic breeze; shared joints stay shared. At t=0
        # the displacement is exactly zero, and no model data is mutated.
        wind = 0.0025 * max(0, point.y) ** 2 * (
            math.sin((self.time % (math.tau / 1.6)) * 1.6 + point.y * 0.4)
            - math.sin(point.y * 0.4))
        p = Point4(point.x - self.center.x + wind, point.y - self.center.y,
                   point.z - self.center.z, point.w - self.center.w)
        hyper_scale = 1.0
        if self.mode == "4d":
            p = rotate_xw(p, self.angle4d)
            xyz = project_4d(p)
            if xyz is None:
                return None
            hyper_scale = 18.0 / (18.0 - p.w)
            x, y, z = xyz
        else:
            x, y, z = p.x, p.y, p.z
        if self.mode != "2d":
            x, z = self.cy * x + self.sy * z, -self.sy * x + self.cy * z
            y, z = self.cp * y - self.sp * z, self.sp * y + self.cp * z
        depth = 30.0 - z
        if depth < 0.5 or not math.isfinite(depth):
            return None
        camera_scale = 1.0 if self.mode == "2d" else 30.0 / depth
        mag = camera_scale * hyper_scale
        return Projected((self.width - 1) / 2 + x * self.scale * self.aspect * camera_scale,
                         (self.height - 1) / 2 - y * self.scale * camera_scale,
                         depth, mag)
