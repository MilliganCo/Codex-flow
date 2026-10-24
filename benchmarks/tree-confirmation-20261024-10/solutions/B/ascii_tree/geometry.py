"""Explicit 4D rotation and guarded perspective math (angles in radians)."""
import math


def finite(*values):
    try:
        valid = all(math.isfinite(v) for v in values)
    except (TypeError, OverflowError) as error:
        raise ValueError("Coordinates and camera values must be finite numbers") from error
    if not valid:
        raise ValueError("Coordinates and camera values must be finite")


def xw_matrix(angle):
    finite(angle)
    c, s = math.cos(angle), math.sin(angle)
    return ((c, 0., 0., -s), (0., 1., 0., 0.),
            (0., 0., 1., 0.), (s, 0., 0., c))


def rotate_xw(point, angle):
    if len(point) != 4:
        raise ValueError("4D point must have four components")
    finite(*point, angle)
    x, y, z, w = point
    c, s = math.cos(angle), math.sin(angle)
    return (x * c - w * s, y, z, x * s + w * c)


def project_4d(point, distance=4.):
    """4D perspective onto W=0; near-plane points are clipped, never divided."""
    if len(point) != 4:
        raise ValueError("4D point must have four components")
    finite(*point, distance)
    if distance <= 0:
        raise ValueError("4D camera distance must be positive")
    denominator = distance - point[3]
    if denominator <= max(1e-6, distance * .02):
        return None
    factor = distance / denominator
    result = tuple(v * factor for v in point[:3])
    return result if all(math.isfinite(v) for v in result) else None


def rotate_3d(point, yaw, pitch):
    finite(*point, yaw, pitch)
    x, y, z = point
    c, s = math.cos(yaw), math.sin(yaw)
    x, z = c * x + s * z, -s * x + c * z
    c, s = math.cos(pitch), math.sin(pitch)
    return (x, c * y - s * z, s * y + c * z)


def perspective(point, distance=3.6):
    if len(point) != 3:
        raise ValueError("3D point must have three components")
    finite(*point, distance)
    if distance <= 0:
        raise ValueError("Camera distance must be positive")
    denominator = distance - point[2]
    if denominator <= max(1e-6, distance * .02):
        return None
    factor = distance / denominator
    result = (point[0] * factor, point[1] * factor, point[2], factor)
    return result if all(math.isfinite(v) for v in result) else None
