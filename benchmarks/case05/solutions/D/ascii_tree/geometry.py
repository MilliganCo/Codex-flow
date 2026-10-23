"""Immutable, seeded tree graph; generation is independent of display mode."""

from dataclasses import dataclass
import math
import random


@dataclass(frozen=True, slots=True)
class Point4:
    x: float
    y: float
    z: float
    w: float


@dataclass(frozen=True, slots=True)
class Segment:
    start: Point4
    end: Point4
    radius_start: float
    radius_end: float
    parent: int | None
    order: int


@dataclass(frozen=True, slots=True)
class Leaf:
    point: Point4
    size: float
    branch: int
    shade: int


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]
    center: tuple[float, float, float]
    extent: float


def unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(c * c for c in v))
    if length < 1e-12:
        return (0.0, 1.0, 0.0)
    return tuple(c / length for c in v)


def generate_tree(seed: int = 42) -> Tree:
    """A curved leader, spiral scaffold limbs, secondary fans and leafy twigs.

    Every child starts at its parent's endpoint. A bounded three-level branch
    recursion gives O(1) resource bounds for any integer seed. W is distance
    along the growth path (scaled and centered), including individual leaves.
    """
    rng = random.Random(seed)
    segments: list[Segment] = []
    leaves: list[Leaf] = []

    def add(start: Point4, direction: tuple[float, float, float], length: float,
            r0: float, r1: float, parent: int | None, order: int) -> int:
        d = unit(direction)
        end = Point4(start.x + d[0] * length, start.y + d[1] * length,
                     start.z + d[2] * length, start.w + length * 0.46)
        segments.append(Segment(start, end, r0, r1, parent, order))
        return len(segments) - 1

    def foliage(index: int, count: int) -> None:
        segment = segments[index]
        for _ in range(count):
            # Light, separated sprays allow the branch skeleton to remain legible.
            t = rng.uniform(0.45, 1.2)
            dx, dy, dz = (rng.gauss(0, 0.18) for _ in range(3))
            a, b = segment.start, segment.end
            point = Point4(a.x + (b.x - a.x) * t + dx,
                           a.y + (b.y - a.y) * t + dy,
                           a.z + (b.z - a.z) * t + dz,
                           a.w + (b.w - a.w) * t + 0.08)
            leaves.append(Leaf(point, rng.uniform(0.045, 0.095), index,
                               rng.randrange(4)))

    def limb(parent: int, direction: tuple[float, float, float], length: float,
             radius: float, order: int) -> None:
        # Four internodes per limb; child fans alternate around each internode.
        current = parent
        d = unit(direction)
        for step in range(4):
            d = unit((d[0] + rng.uniform(-0.12, 0.12),
                      d[1] + 0.09 + rng.uniform(-0.04, 0.04),
                      d[2] + rng.uniform(-0.12, 0.12)))
            r0 = radius * (1 - step * 0.21)
            index = add(segments[current].end, d, length / 4,
                        r0, radius * (1 - (step + 1) * 0.21), current, order)
            current = index
            if order < 3 and step >= 1:
                azimuth = math.atan2(d[2], d[0])
                sign = -1 if step % 2 else 1
                spread = sign * rng.uniform(0.65, 1.2)
                angle = azimuth + spread
                child_d = (math.cos(angle) * 0.88,
                           rng.uniform(0.40, 0.85), math.sin(angle) * 0.88)
                limb(index, child_d, length * rng.uniform(0.39, 0.55),
                     segments[index].radius_end * 0.62, order + 1)
            if order == 3 or (order == 2 and step >= 2):
                foliage(index, 3 if order == 3 else 2)

    root = Point4(0, 0, 0, -2.3)
    parent = None
    leader: list[int] = []
    drift = rng.uniform(0, math.tau)
    for step in range(13):
        t = step / 13
        r0 = 0.32 * (1 - t) ** 1.2 + 0.018
        r1 = 0.32 * (1 - (step + 1) / 13) ** 1.2 + 0.018
        direction = (0.10 * math.sin(drift + step * 0.5) + t * 0.09,
                     1, 0.08 * math.cos(drift + step * 0.45))
        index = add(root if parent is None else segments[parent].end,
                    direction, rng.uniform(0.66, 0.84), r0, r1, parent, 0)
        leader.append(index)
        parent = index

    phase = rng.uniform(0, math.tau)
    for step in range(3, 13):
        # Lower branches spread wider; high branches fill the apex.
        count = 2 if step < 11 else 1
        for side in range(count):
            angle = phase + step * 2.39996 + side * 2.7 + rng.uniform(-0.3, 0.3)
            length = (4.2 - (step - 4) * 0.29) * rng.uniform(0.85, 1.15)
            direction = (math.cos(angle), rng.uniform(0.22, 0.49), math.sin(angle))
            limb(leader[step], direction, max(1.3, length),
                 segments[leader[step]].radius_end * 0.65, 1)
    foliage(leader[-1], 10)
    points = [s.end for s in segments] + [root] + [leaf.point for leaf in leaves]
    min_y, max_y = min(p.y for p in points), max(p.y for p in points)
    center = (0.0, (min_y + max_y) / 2, 0.0)
    extent = max(math.sqrt(p.x**2 + (p.y - center[1])**2 + p.z**2)
                 for p in points) + 0.25
    return Tree(seed, tuple(segments), tuple(leaves), center, extent)
