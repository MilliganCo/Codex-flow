"""Pure transforms; positive camera depth points away from the observer."""

from __future__ import annotations

import math

from .geometry import Point4

NEAR = 0.35
W_EYE = 20.0
CAMERA_DISTANCE = 25.0
CENTER_Y = 6.0


def rotation_xw(angle: float) -> tuple[tuple[float, ...], ...]:
    """An orthogonal, determinant +1 rotation; angle is in radians."""
    c, s = math.cos(angle), math.sin(angle)
    return ((c, 0.0, 0.0, -s), (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0), (s, 0.0, 0.0, c))


def rotate_xw(point: Point4, angle: float) -> Point4:
    c, s = math.cos(angle), math.sin(angle)
    return Point4(c * point.x - s * point.w, point.y, point.z,
                  s * point.x + c * point.w)


def project_4d(point: Point4, angle: float) -> tuple[float, float, float] | None:
    """Rotate XW, then perspective-project along W around the crown center.

    Points outside the W near plane are clipped, never divided by zero.
    The generated tree stays well inside this frustum for any XW angle.
    """
    p = rotate_xw(Point4(point.x, point.y - CENTER_Y, point.z, point.w), angle)
    denominator = W_EYE - p.w
    if denominator < NEAR:
        return None
    factor = W_EYE / denominator
    return p.x * factor, p.y * factor, p.z * factor


def camera_point(point: Point4, mode: str, yaw: float, pitch: float,
                 angle4: float) -> tuple[float, float, float] | None:
    if mode == "4d":
        spatial = project_4d(point, angle4)
        if spatial is None:
            return None
        x, y, z = spatial
    else:
        x, y, z = point.x, point.y - CENTER_Y, point.z
    if mode == "2d":
        return x, y, z  # Orthographic front projection; Z still resolves visibility.
    cy, sy = math.cos(yaw), math.sin(yaw)
    x, z = cy * x + sy * z, -sy * x + cy * z
    cp, sp = math.cos(pitch), math.sin(pitch)
    y, z = cp * y - sp * z, sp * y + cp * z
    return x, y, z + CAMERA_DISTANCE


def project_camera(point: tuple[float, float, float], mode: str,
                   width: int, height: int, zoom: float = 1.0,
                   aspect: float = 2.0) -> tuple[float, float, float, float] | None:
    """Return column, row, positive depth and horizontal pixels/world-unit.

    Character cells are roughly twice as tall as wide. A world-space circle
    therefore occupies twice as many columns as rows.
    """
    x, y, z = point
    factor = 1.0
    if mode != "2d":
        if z < NEAR:
            return None
        factor = CAMERA_DISTANCE / z
    margin = 0.90 if mode == "4d" else 1.0
    scale = min(width / 20.0, height * aspect / 17.0) * zoom * factor * margin
    return ((width - 1) / 2 + x * scale,
            (height - 1) / 2 - y * scale / aspect, z, scale)
