"""Explicit 4D -> 3D -> camera -> character plane transformations."""

from dataclasses import dataclass
import math

from .geometry import Point4, Tree

NEAR = 0.3
CAMERA_DISTANCE = 25.0
W_DISTANCE = 18.0


def rotate_xw(point: Point4, angle: float) -> Point4:
    """Radians; matrix rows (c,0,0,-s), (0,1,0,0), (0,0,1,0), (s,0,0,c)."""
    c, s = math.cos(angle), math.sin(angle)
    return Point4(c * point.x - s * point.w, point.y, point.z,
                  s * point.x + c * point.w)


def project_4d(point: Point4) -> tuple[float, float, float] | None:
    denominator = W_DISTANCE - point.w
    if denominator < NEAR or not math.isfinite(denominator):
        return None
    factor = W_DISTANCE / denominator
    return point.x * factor, point.y * factor, point.z * factor


@dataclass(frozen=True, slots=True)
class View:
    mode: str = "3d"
    yaw: float = 25.0
    pitch: float = -7.0
    angle4d: float = 0.0
    zoom: float = 1.0
    aspect: float = 0.5  # Character cell width / height; x needs twice as many cells.

    def __post_init__(self) -> None:
        if self.mode not in {"2d", "3d", "4d"}:
            raise ValueError("mode must be 2d, 3d or 4d")
        if not all(math.isfinite(v) for v in
                   (self.yaw, self.pitch, self.angle4d, self.zoom, self.aspect)):
            raise ValueError("view values must be finite")
        if not 0.1 <= self.zoom <= 8 or not 0.2 <= self.aspect <= 2:
            raise ValueError("zoom must be 0.1..8; aspect must be 0.2..2")


@dataclass(frozen=True, slots=True)
class ScreenPoint:
    x: float
    y: float
    depth: float
    scale: float


class Projector:
    def __init__(self, tree: Tree, width: int, height: int, view: View):
        self.tree, self.width, self.height, self.view = tree, width, height, view
        self.scale = min(max(1, height - 3), max(1, width - 4) * view.aspect)
        self.scale *= 0.96 * view.zoom / (2 * tree.extent)
        self.cy, self.sy = math.cos(math.radians(view.yaw)), math.sin(math.radians(view.yaw))
        self.cp, self.sp = math.cos(math.radians(view.pitch)), math.sin(math.radians(view.pitch))

    def __call__(self, point: Point4) -> ScreenPoint | None:
        x, y, z = (point.x - self.tree.center[0], point.y - self.tree.center[1],
                   point.z - self.tree.center[2])
        factor4 = 1.0
        if self.view.mode == "4d":
            rotated = rotate_xw(Point4(x, y, z, point.w), math.radians(self.view.angle4d))
            spatial = project_4d(rotated)
            if spatial is None:
                return None
            factor4 = W_DISTANCE / (W_DISTANCE - rotated.w)
            x, y, z = spatial
        if self.view.mode != "2d":
            x, z = self.cy * x + self.sy * z, -self.sy * x + self.cy * z
            y, z = self.cp * y - self.sp * z, self.sp * y + self.cp * z
            depth = CAMERA_DISTANCE - z  # Smaller positive depth is nearer the camera.
            if depth < NEAR:
                return None
            perspective = CAMERA_DISTANCE / depth
        else:
            depth, perspective = CAMERA_DISTANCE - z, 1.0
        scale = self.scale * perspective * factor4
        result = ScreenPoint((self.width - 1) / 2 + x * self.scale * perspective / self.view.aspect,
                             (self.height - 1) / 2 - y * self.scale * perspective,
                             depth, scale)
        return result if all(math.isfinite(v) for v in
                             (result.x, result.y, result.depth, result.scale)) else None
