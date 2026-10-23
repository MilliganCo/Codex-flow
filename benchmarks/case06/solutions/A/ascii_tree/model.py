"""A seeded, connected broadleaf tree; every attachment shares an exact vertex."""

from dataclasses import dataclass
import math
import random

from .geometry import Point4


@dataclass(frozen=True, slots=True)
class Segment:
    start: int
    end: int
    parent: int | None
    radius_start: float
    radius_end: float
    order: int


@dataclass(frozen=True, slots=True)
class Leaf:
    point: Point4
    size: float
    light: float


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    vertices: tuple[Point4, ...]
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]

    @property
    def height(self) -> float:
        return max(p.y for p in self.vertices)


def generate_tree(seed: int = 42) -> Tree:
    """Bounded recursion (four branch orders), local RNG, no time/global state.

    W records accumulated growth distance, scaled to the size of the tree.
    A curved leader and irregular whorls use a golden-angle distribution.
    """
    rng = random.Random(seed)
    vertices = [Point4(0.0, 0.0, 0.0, 0.0)]
    segments: list[Segment] = []
    leaves: list[Leaf] = []

    def add(start: int, xyz: tuple[float, float, float], parent: int | None,
            r0: float, r1: float, order: int) -> tuple[int, int]:
        p = vertices[start]
        length = math.dist((p.x, p.y, p.z), xyz)
        q = Point4(*xyz, p.w + length * 0.48)
        vertices.append(q)
        segments.append(Segment(start, len(vertices) - 1, parent, r0, r1, order))
        return len(vertices) - 1, len(segments) - 1

    def foliage(tip: Point4, length: float) -> None:
        # Open clusters: isolated leaves preserve the woody structure.
        for _ in range(rng.randint(2, 4)):
            dx, dy, dz = (rng.uniform(-1, 1) for _ in range(3))
            spread = max(0.20, length * 0.26)
            leaves.append(Leaf(Point4(tip.x + dx * spread, tip.y + dy * spread * 0.65,
                                     tip.z + dz * spread, tip.w + rng.uniform(0, 0.12)),
                               rng.uniform(0.055, 0.115), rng.uniform(0.2, 1.0)))

    def branch(start: int, parent: int, azimuth: float, rise: float,
               length: float, radius: float, order: int) -> None:
        count = 4
        current, previous = start, parent
        attachments: list[tuple[int, int, int]] = []
        angle = azimuth
        for step in range(count):
            angle += rng.uniform(-0.16, 0.16)
            # Tips turn upward; each branch keeps its own asymmetry.
            elevation = rise + step * 0.105 + rng.uniform(-0.06, 0.06)
            stride = length / count * rng.uniform(0.88, 1.12)
            p = vertices[current]
            dx = math.cos(angle) * math.cos(elevation) * stride
            dz = math.sin(angle) * math.cos(elevation) * stride
            dy = math.sin(elevation) * stride
            t0, t1 = step / count, (step + 1) / count
            r0 = radius * (1 - 0.78 * t0)
            r1 = radius * (1 - 0.78 * t1)
            current, previous = add(current, (p.x + dx, p.y + dy, p.z + dz),
                                    previous, r0, r1, order)
            attachments.append((current, previous, step))
        if order < 4:
            for vertex, edge, step in attachments[1:]:
                sign = -1 if step % 2 else 1
                branch(vertex, edge, angle + sign * rng.uniform(0.50, 1.05),
                       rise + rng.uniform(0.10, 0.34),
                       length * rng.uniform(0.38, 0.57),
                       segments[edge].radius_end * 0.68, order + 1)
        else:
            for vertex, _, _ in attachments[1:]:
                foliage(vertices[vertex], length)

    height = rng.uniform(10.5, 12.5)
    lean_x, lean_z = rng.uniform(-0.7, 0.7), rng.uniform(-0.5, 0.5)
    phase = rng.uniform(0, math.tau)
    current, previous = 0, None
    for level in range(1, 17):
        t = level / 16
        x = lean_x * t + math.sin(t * 5 + phase) * 0.22 * t
        z = lean_z * t + math.cos(t * 4 + phase) * 0.19 * t
        r0 = 0.46 * (1 - (level - 1) / 16) ** 0.95 + 0.012
        r1 = 0.46 * (1 - t) ** 0.95 + 0.012
        current, previous = add(current, (x, height * t, z), previous, r0, r1, 0)
        if level >= 5:
            for side in range(2 if level < 14 else 1):
                az = phase + level * 2.399963 + side * 2.65 + rng.uniform(-0.3, 0.3)
                length = (4.8 * math.sin(t * math.pi) ** 0.7 + 0.6) * rng.uniform(0.85, 1.15)
                branch(current, previous, az, rng.uniform(0.12, 0.40), length,
                       r1 * rng.uniform(0.50, 0.65), 1)
    foliage(vertices[current], 0.8)
    return Tree(seed, tuple(vertices), tuple(segments), tuple(leaves))
