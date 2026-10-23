"""Explicit 4D rotation and guarded 4D -> 3D -> 2D projection."""

from dataclasses import dataclass
import math

from .model import Point4, Tree


def rotation_xw(angle: float) -> tuple[tuple[float, ...], ...]:
    """An orthogonal, determinant +1 matrix. Angle is in radians."""
    c, s = math.cos(angle), math.sin(angle)
    return ((c, 0.0, 0.0, -s), (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0), (s, 0.0, 0.0, c))


def rotate_xw(point: Point4, angle: float) -> Point4:
    c, s = math.cos(angle), math.sin(angle)
    return Point4(c * point.x - s * point.w, point.y, point.z,
                  s * point.x + c * point.w)


def perspective_factor(depth: float, near: float = 0.5) -> float | None:
    """Reject the near plane and non-finite inputs before division."""
    if not math.isfinite(depth) or depth <= near:
        return None
    return 1.0 / depth


@dataclass(frozen=True, slots=True)
class View:
    mode: str = '3d'
    yaw: float = -20.0
    pitch: float = 8.0
    angle4: float = 0.0
    zoom: float = 1.0
    time: float = 0.0


@dataclass(frozen=True, slots=True)
class Projected:
    x: float
    y: float
    depth: float
    scale: float


class Projector:
    """Coordinates in character cells; cell width is half its height.

    D4=40 and D3=45 are in model units. Increasing view Z is nearer.
    2D is an orthographic XY view; depth still resolves overlaps.
    """

    def __init__(self, tree: Tree, view: View, width: int, height: int):
        self.center = tree.center
        self.view = view
        self.width, self.height = width, height
        self.scale = max(0.02, min((width - 1) / (4 * tree.extent),
                                   (height - 1) / (2 * tree.extent))) * view.zoom
        yaw = math.radians((view.yaw % 360 + ((view.time % 30) * 12 if view.mode != '2d' else 0)) % 360)
        pitch = math.radians(view.pitch % 360)
        self.cy, self.sy = math.cos(yaw), math.sin(yaw)
        self.cp, self.sp = math.cos(pitch), math.sin(pitch)
        self.angle4 = math.radians((view.angle4 % 360 + (view.time % 22.5) * 16) % 360)

    def project(self, point: Point4) -> Projected | None:
        x, y, z, w = (point.x - self.center.x, point.y - self.center.y,
                       point.z - self.center.z, point.w - self.center.w)
        if self.view.time:
            # Continuous wind field: a junction receives the same displacement
            # through every incident segment, preserving connectivity.
            phase = (self.view.time % (math.tau / 1.5)) * 1.5
            x += 0.012 * max(0, point.y) ** 1.6 * math.sin(phase + point.y * 0.25)
        factor4 = 1.0
        if self.view.mode == '4d':
            rotated = rotate_xw(Point4(x, y, z, w), self.angle4)
            reciprocal = perspective_factor(40.0 - rotated.w)
            if reciprocal is None:
                return None
            factor4 = 40.0 * reciprocal
            x, y, z = rotated.x * factor4, rotated.y * factor4, rotated.z * factor4
        if self.view.mode != '2d':
            x, z = self.cy * x + self.sy * z, -self.sy * x + self.cy * z
            y, z = self.cp * y - self.sp * z, self.sp * y + self.cp * z
            reciprocal = perspective_factor(45.0 - z)
            if reciprocal is None:
                return None
            factor3 = 45.0 * reciprocal
        else:
            factor3 = 1.0
        depth = 45.0 - z
        if not all(math.isfinite(v) for v in (x, y, z, depth)):
            return None
        sx = (self.width - 1) / 2 + x * self.scale * 2 * factor3
        sy = (self.height - 1) / 2 - y * self.scale * factor3
        scale = self.scale * factor3 * factor4
        if not all(math.isfinite(value) for value in (sx, sy, scale)):
            return None
        return Projected(sx, sy, depth, scale)
