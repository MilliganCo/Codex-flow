"""4D -> 3D -> screen projection and depth-buffered ASCII rasterization."""
from dataclasses import dataclass
import math

from .model import Point, Tree

CHAR_ASPECT = .5  # cell width / cell height, configurable for other terminal fonts
NEAR = .5


@dataclass(frozen=True, slots=True)
class View:
    mode: str = "3d"
    yaw: float = -22.
    pitch: float = 8.
    angle4d: float = 0.
    zoom: float = 1.
    time: float = 0.
    aspect: float = CHAR_ASPECT

    def __post_init__(self) -> None:
        if self.mode not in ("2d", "3d", "4d"):
            raise ValueError("mode must be 2d, 3d or 4d")
        if not all(math.isfinite(x) for x in
                   (self.yaw, self.pitch, self.angle4d, self.zoom, self.time, self.aspect)):
            raise ValueError("view parameters must be finite")
        if not .1 <= self.zoom <= 5 or not .2 <= self.aspect <= 1:
            raise ValueError("zoom must be 0.1..5; aspect must be 0.2..1")


def rotate_xw(p: Point, degrees: float) -> Point:
    """An orthogonal SO(4) rotation; positive angle mixes X into W."""
    angle = math.radians(degrees % 360)
    c, s = math.cos(angle), math.sin(angle)
    return Point(c*p.x-s*p.w, p.y, p.z, s*p.x+c*p.w)


def project_4d(p: Point, degrees: float) -> tuple[float, float, float, float] | None:
    """Center growth about zero, rotate XW, then perspective from W=16.

    Return spatial XYZ and the local perspective scale; clip behind the eye.
    """
    p = rotate_xw(Point(p.x, p.y-6., p.z, (p.w-.5)*8), degrees)
    distance = 16-p.w
    if distance < NEAR:
        return None
    scale = 16/distance
    return p.x*scale, p.y*scale, p.z*scale, scale


@dataclass(frozen=True, slots=True)
class Projected:
    x: float
    y: float
    depth: float
    scale: float


def project(p: Point, view: View, width: int, height: int) -> Projected | None:
    # Deterministic, mild wind: rooted trunk stays still, tips move most.
    wind = math.sin(view.time*1.3 + p.y*.8)*p.w**3*.16 if view.time else 0.
    p = Point(p.x+wind, p.y, p.z, p.w)
    scale4 = 1.
    if view.mode == "4d":
        spatial = project_4d(p, view.angle4d)
        if spatial is None:
            return None
        x, y, z, scale4 = spatial
    else:
        x, y, z = p.x, p.y-6., p.z
    yaw = math.radians(view.yaw % 360) if view.mode != "2d" else 0.
    pitch = math.radians(view.pitch % 360) if view.mode != "2d" else 0.
    x, z = x*math.cos(yaw)+z*math.sin(yaw), -x*math.sin(yaw)+z*math.cos(yaw)
    y, z = y*math.cos(pitch)-z*math.sin(pitch), y*math.sin(pitch)+z*math.cos(pitch)
    depth = 24+z
    if depth < NEAR:
        return None
    perspective = 1. if view.mode == "2d" else 24/depth
    scale = min(height/14.4, width*view.aspect/16)*view.zoom
    if view.mode == "4d":
        scale *= .8  # room for the extra W-perspective expansion
    return Projected((width-1)/2+x*scale*perspective/view.aspect,
                     (height-1)/2-y*scale*perspective,
                     depth, scale*perspective*scale4)


class Raster:
    """Z-buffer: smaller positive camera depth wins, ties are deterministic."""
    def __init__(self, width: int, height: int):
        if not 1 <= width <= 500 or not 1 <= height <= 250:
            raise ValueError("frame dimensions must be width 1..500, height 1..250")
        self.width, self.height = width, height
        self.pixels = [" "]*(width*height)
        self.depth = [math.inf]*(width*height)

    def put(self, x: int, y: int, depth: float, char: str) -> None:
        if 0 <= x < self.width and 0 <= y < self.height and math.isfinite(depth) and depth >= NEAR:
            i = y*self.width+x
            if (depth, char) < (self.depth[i], self.pixels[i]):
                self.depth[i], self.pixels[i] = depth, char

    def line(self, a: Projected, b: Projected, r0: float, r1: float,
             char: str, aspect: float = CHAR_ASPECT) -> None:
        """Conservative screen clipping, bounded sampling, elliptical tube stamps."""
        dx, dy = b.x-a.x, b.y-a.y
        radius = max(r0*a.scale, r1*b.scale, .42)
        # Clip parameter interval against expanded viewport (Liang-Barsky).
        lo, hi = 0., 1.
        for origin, delta, low, high in ((a.x, dx, -radius/aspect, self.width+radius/aspect),
                                          (a.y, dy, -radius, self.height+radius)):
            if abs(delta) < 1e-12:
                if not low <= origin <= high:
                    return
            else:
                t0, t1 = (low-origin)/delta, (high-origin)/delta
                lo, hi = max(lo, min(t0, t1)), min(hi, max(t0, t1))
                if lo > hi:
                    return
        count = min(4000, max(1, math.ceil(max(abs(dx), abs(dy))*(hi-lo)*2)))

        def fragment_depth(ix: int, iy: int) -> float:
            length2 = dx*dx+dy*dy
            t = max(lo, min(hi, ((ix-a.x)*dx+(iy-a.y)*dy)/length2)) if length2 else float(b.depth < a.depth)
            return 1/((1-t)/a.depth+t/b.depth)

        for step in range(count+1):
            t = lo+(hi-lo)*step/count
            x, y = a.x+dx*t, a.y+dy*t
            scale = a.scale+(b.scale-a.scale)*t
            ry = max(.42, (r0+(r1-r0)*t)*scale)
            rx = max(.48, ry/aspect)
            # The centerline is a connected digital path even for sub-cell twigs.
            self.put(round(x), round(y), fragment_depth(round(x), round(y)), char)
            for iy in range(max(0, math.floor(y-ry)), min(self.height, math.ceil(y+ry)+1)):
                for ix in range(max(0, math.floor(x-rx)), min(self.width, math.ceil(x+rx)+1)):
                    surface = ((ix-x)/rx)**2+((iy-y)/ry)**2
                    if surface <= 1:
                        physical_radius = r0+(r1-r0)*t
                        self.put(ix, iy, max(NEAR, fragment_depth(ix, iy)-math.sqrt(1-surface)*physical_radius), char)

    def text(self) -> str:
        return "\n".join("".join(self.pixels[y*self.width:(y+1)*self.width])
                         for y in range(self.height))+"\n"


def render_tree(tree: Tree, width: int = 100, height: int = 40, view: View | None = None) -> str:
    view = view or View()
    raster = Raster(width, height)
    cache: dict[Point, Projected | None] = {}

    def screen(p: Point) -> Projected | None:
        if p not in cache:
            cache[p] = project(p, view, width, height)
        return cache[p]

    for segment in tree.segments:
        a, b = screen(segment.start), screen(segment.end)
        if a is None or b is None:
            continue
        dx, dy = b.x-a.x, b.y-a.y
        if segment.order == 0:
            char = "#" if (a.depth+b.depth)/2 < 24 else "%"
        elif segment.radius_start*a.scale > .38:
            char = "+" if a.depth < 24 else ":"
        elif abs(dx) > abs(dy)*1.8:
            char = "-"
        elif abs(dy) > abs(dx)*1.8:
            char = "|"
        else:
            char = "/" if dx*dy < 0 else "\\"
        raster.line(a, b, segment.radius_start, segment.radius_end, char, view.aspect)
    for leaf in tree.leaves:
        p = screen(leaf.center)
        if p is None:
            continue
        # Sparse clusters leave the structural branch graph legible.
        char = (".,:*o" if p.depth > 24 else ",*oO+")[leaf.tone]
        raster.put(round(p.x), round(p.y), p.depth, char)
    return raster.text()
