"""Seeded, bounded branch growth. All modes consume the same immutable graph."""

from dataclasses import dataclass
import math
import random

Vec3 = tuple[float, float, float]


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
    tone: float


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]

    @property
    def center(self) -> Point4:
        points = [s.end for s in self.segments] + [self.segments[0].start]
        return Point4(*((min(getattr(p, a) for p in points)
                        + max(getattr(p, a) for p in points)) / 2
                       for a in ("x", "y", "z", "w")))

    @property
    def span(self) -> tuple[float, float]:
        points = [s.end for s in self.segments] + [self.segments[0].start]
        # Keep the same scale when the camera turns around a broad crown.
        width = max(max(p.x for p in points) - min(p.x for p in points),
                    max(p.z for p in points) - min(p.z for p in points)) + 1.2
        height = max(p.y for p in points) - min(p.y for p in points) + 1.2
        return width, height


def unit(v: Vec3) -> Vec3:
    length = math.sqrt(sum(a * a for a in v))
    if length < 1e-12:
        return (0.0, 1.0, 0.0)
    return tuple(a / length for a in v)


def generate_tree(seed: int = 42) -> Tree:
    """Grow a crooked leader, spiral scaffold limbs, forks and loose leaf sprays.

    Recursion is capped at order 4; every new segment attaches to a previously
    emitted endpoint. W measures accumulated growth distance (not random noise).
    """
    rng = random.Random(seed)
    segments: list[Segment] = []
    leaves: list[Leaf] = []
    max_order, max_segments = 4, 3500
    phase = rng.uniform(0, math.tau)
    lean_x, lean_z = rng.uniform(-0.055, 0.055), rng.uniform(-0.045, 0.045)

    def append(start: Point4, direction: Vec3, length: float,
               radius: float, end_radius: float, parent: int | None,
               order: int) -> int:
        dx, dy, dz = unit(direction)
        end = Point4(start.x + dx * length, start.y + dy * length,
                     start.z + dz * length, start.w + length * (0.28 + order * 0.045))
        index = len(segments)
        segments.append(Segment(start, end, radius, end_radius, parent, order))
        return index

    def spray(tip: Point4, direction: Vec3, length: float) -> None:
        # Sparse small sprays at twig ends leave the interior branchwork visible.
        for _ in range(rng.randint(8, 14)):
            t = rng.uniform(-0.55, 0.25) * length
            spread = rng.uniform(0.14, 0.48)
            point = Point4(tip.x + direction[0] * t + rng.gauss(0, spread),
                           tip.y + direction[1] * t + rng.gauss(0, spread * 0.65),
                           tip.z + direction[2] * t + rng.gauss(0, spread),
                           tip.w + rng.uniform(-0.08, 0.12))
            leaves.append(Leaf(point, rng.uniform(0.08, 0.16), rng.random()))

    def branch(parent: int, direction: Vec3, length: float,
               radius: float, order: int) -> None:
        if order > max_order or len(segments) + 40 >= max_segments:
            return
        direction = unit(direction)
        previous = parent
        for step in range(4):
            # Gravity at the base, then phototropic upward-curving tips.
            direction = unit((direction[0] + rng.uniform(-0.10, 0.10),
                              direction[1] + 0.09 + step * 0.012,
                              direction[2] + rng.uniform(-0.10, 0.10)))
            r0 = radius * (1 - step * 0.205)
            r1 = radius * (1 - (step + 1) * 0.205)
            previous = append(segments[previous].end, direction, length / 4,
                              r0, r1, previous, order)
            if order < max_order and step in (1, 3):
                sign = -1 if step == 1 else 1
                angle = sign * rng.uniform(0.48, 0.98)
                ca, sa = math.cos(angle), math.sin(angle)
                child_dir = unit((direction[0] * ca - direction[2] * sa,
                                  direction[1] * 0.62 + rng.uniform(0.08, 0.32),
                                  direction[0] * sa + direction[2] * ca))
                branch(previous, child_dir, length * rng.uniform(0.49, 0.65),
                       r1 * 0.66, order + 1)
        if order >= 3:
            spray(segments[previous].end, direction, length)

    # Make the trunk first so side growth cannot alter its random sequence.
    trunk: list[int] = []
    start = Point4(0, 0, 0, 0)
    for i in range(13):
        t = i / 13
        direction = (lean_x + math.sin(i * 0.65 + phase) * 0.055,
                     1.0, lean_z + math.cos(i * 0.5 + phase) * 0.055)
        radius = 0.58 * (1 - t) ** 1.3 + 0.035
        r_end = 0.58 * (1 - (i + 1) / 13) ** 1.3 + 0.035
        index = append(start, direction, rng.uniform(0.87, 1.02), radius,
                       r_end, trunk[-1] if trunk else None, 0)
        trunk.append(index)
        start = segments[index].end

    # Irrational phyllotactic spacing avoids a flat, mirrored binary silhouette.
    for i, attachment in enumerate(trunk[3:12]):
        azimuth = phase + i * 2.399963229728653 + rng.uniform(-0.28, 0.28)
        elevation = rng.uniform(0.18, 0.38) + i * 0.027
        length = (5.2 - i * 0.22) * rng.uniform(0.86, 1.16)
        direction = (math.cos(azimuth), elevation, math.sin(azimuth))
        branch(attachment, direction, length,
               segments[attachment].radius_end * rng.uniform(0.53, 0.70), 1)
    branch(trunk[-1], (math.cos(phase), 1.3, math.sin(phase)), 1.8,
           segments[trunk[-1]].radius_end * 0.8, 2)
    return Tree(seed, tuple(segments), tuple(leaves))
