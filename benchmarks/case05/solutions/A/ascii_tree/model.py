"""Seeded botanical skeleton shared, without regeneration, by every view."""

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
    tone: float


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]
    center: Point4
    extent: float


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(c * c for c in v))
    if length < 1e-10:
        return (0.0, 1.0, 0.0)
    return tuple(c / length for c in v)


def generate_tree(seed: int) -> Tree:
    """Grow a crooked leader, radial boughs, forks and terminal leaf sprays.

    A segment's parent always precedes it and ends exactly at its start.
    W is accumulated growth distance (not a second random tree).
    Recursion is capped at four branch orders and 6,000 segments.
    """
    rng = random.Random(seed)
    segments: list[Segment] = []
    leaves: list[Leaf] = []

    def append(start, end, radius, end_radius, parent, order):
        if len(segments) >= 6000:
            raise ValueError("Tree segment budget exceeded")
        segments.append(Segment(start, end, radius, end_radius, parent, order))
        return len(segments) - 1

    def spray(point, size):
        # Sparse ellipsoids leave the woody skeleton legible.
        for _ in range(rng.randint(13, 22)):
            azimuth = rng.uniform(0, math.tau)
            vertical = rng.uniform(-1, 1)
            radial = rng.random() ** (1 / 3)
            flat = math.sqrt(1 - vertical * vertical)
            dx = math.cos(azimuth) * flat * size * radial
            dy = vertical * size * 0.65 * radial
            dz = math.sin(azimuth) * flat * size * radial
            leaves.append(Leaf(Point4(point.x + dx, point.y + dy,
                                      point.z + dz, point.w + 0.12 * radial),
                               rng.random()))

    def branch(start, direction, length, radius, parent, order):
        count = 4
        current = start
        direction = _unit(direction)
        attachments = []
        for step in range(count):
            direction = _unit((direction[0] + rng.uniform(-0.12, 0.12),
                               direction[1] + 0.10 + rng.uniform(-0.035, 0.035),
                               direction[2] + rng.uniform(-0.12, 0.12)))
            distance = length / count * rng.uniform(0.88, 1.12)
            endpoint = Point4(current.x + direction[0] * distance,
                              current.y + direction[1] * distance,
                              current.z + direction[2] * distance,
                              current.w + distance * (0.72 + order * 0.045))
            r0 = max(0.009, radius * (1 - step / count) ** 1.15)
            r1 = max(0.006, radius * (1 - (step + 1) / count) ** 1.15)
            parent = append(current, endpoint, r0, r1, parent, order)
            current = endpoint
            attachments.append((current, parent, direction, r1))
        if order >= 4 or length < 0.42:
            spray(current, rng.uniform(0.36, 0.65))
            return
        # Alternating side shoots, with a variable terminal fork.
        for index in (1, 3):
            origin, ancestor, tangent, available_radius = attachments[index]
            azimuth = math.atan2(tangent[2], tangent[0])
            azimuth += rng.choice((-1, 1)) * rng.uniform(0.65, 1.35)
            elevation = rng.uniform(0.32, 0.80)
            new_direction = _unit((math.cos(azimuth), elevation, math.sin(azimuth)))
            branch(origin, new_direction, length * rng.uniform(0.48, 0.68),
                   min(radius * 0.52, available_radius * 0.88), ancestor, order + 1)
        if order <= 2 and rng.random() < 0.55:
            origin, ancestor, tangent, available_radius = attachments[2]
            branch(origin, (-tangent[2], rng.uniform(0.4, 0.9), tangent[0]),
                   length * 0.45, min(radius * 0.4, available_radius * 0.8),
                   ancestor, order + 1)
        spray(current, 0.4)

    current = Point4(0.0, 0.0, 0.0, 0.0)
    parent = None
    trunk = []
    lean_x, lean_z = rng.uniform(-0.17, 0.17), rng.uniform(-0.12, 0.12)
    for level in range(13):
        distance = rng.uniform(0.59, 0.76)
        endpoint = Point4(current.x + lean_x + rng.uniform(-0.10, 0.10),
                          current.y + distance,
                          current.z + lean_z + rng.uniform(-0.09, 0.09),
                          current.w + distance * 0.72)
        r0 = 0.38 * (1 - level / 14) ** 1.3 + 0.012
        r1 = 0.38 * (1 - (level + 1) / 14) ** 1.3 + 0.012
        if level == 0:
            r0 *= 1.5  # Root flare.
        parent = append(current, endpoint, r0, r1, parent, 0)
        current = endpoint
        trunk.append((current, parent, r1))

    rotation = rng.uniform(0, math.tau)
    for level in range(3, 13):
        origin, ancestor, radius = trunk[level]
        for side in range(2 if level < 10 else 1):
            azimuth = rotation + level * 2.39996 + side * 2.8 + rng.uniform(-0.45, 0.45)
            # Lower boughs spread; higher shoots rise and get shorter.
            length = (3.9 - (level - 3) * 0.23) * rng.uniform(0.85, 1.22)
            branch(origin, (math.cos(azimuth), rng.uniform(0.18, 0.58), math.sin(azimuth)),
                   length, radius * rng.uniform(0.52, 0.72), ancestor, 1)
    spray(current, 0.5)

    points = [s.end for s in segments] + [s.start for s in segments[:1]]
    points.extend(leaf.point for leaf in leaves)
    low = [min(getattr(p, axis) for p in points) for axis in ('x', 'y', 'z', 'w')]
    high = [max(getattr(p, axis) for p in points) for axis in ('x', 'y', 'z', 'w')]
    # Center on the trunk's horizontal origin, preserving natural asymmetry.
    center = Point4(0.0, (low[1] + high[1]) / 2, 0.0, (low[3] + high[3]) / 2)
    extent = max(6.0, (high[1] - low[1]) / 2 + 0.8,
                 max(abs(low[0]), abs(high[0]), abs(low[2]), abs(high[2])) + 0.5)
    return Tree(seed, tuple(segments), tuple(leaves), center, extent)
