"""Immutable, connected botanical geometry. No renderer state or global RNG."""
from dataclasses import dataclass
import math
import random

Point4 = tuple[float, float, float, float]
Vec3 = tuple[float, float, float]
MAX_SEGMENTS = 4096


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


def unit(v: Vec3) -> Vec3:
    length = math.hypot(*v)
    if not math.isfinite(length) or length < 1e-12:
        raise ValueError("Direction must be finite and nonzero")
    return tuple(x / length for x in v)


def generate_tree(seed: int = 42) -> Tree:
    """Bounded recursive branching; W is normalized developmental path age."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Seed must be an integer")
    rng = random.Random(seed)
    segments: list[Segment] = []
    leaves: list[Leaf] = []

    def add(a, b, r0, r1, parent, order):
        if len(segments) >= MAX_SEGMENTS:
            raise ValueError("Tree segment limit reached")
        segments.append(Segment(a, b, r0, r1, parent, order))
        return len(segments) - 1

    def limb(start, direction, length, radius, order, parent):
        direction = unit(direction)
        current = start
        children = []
        for step in range(5):
            direction = unit((direction[0] + rng.uniform(-.14, .14),
                              direction[1] + .065, direction[2] + rng.uniform(-.14, .14)))
            size = length / 5 * rng.uniform(.88, 1.12)
            end = tuple(current[i] + direction[i] * size for i in range(3)) + (
                current[3] + size / 13,)
            r0 = max(.002, radius * (1 - .76 * step / 5))
            r1 = max(.002, radius * (1 - .76 * (step + 1) / 5))
            parent = add(current, end, r0, r1, parent, order)
            current = end
            if step in (2, 4) and order < 4:
                children.append((current, parent, r1))
            if order >= 3 and step >= 2:
                # Small loose sprays keep gaps through which wood remains visible.
                for _ in range(3 if order == 4 else 1):
                    p = (current[0] + rng.uniform(-.24, .24),
                         current[1] + rng.uniform(-.12, .28),
                         current[2] + rng.uniform(-.24, .24), current[3])
                    leaves.append(Leaf(p, rng.uniform(.045, .10), rng.random()))
        for position, ancestor, junction_radius in children:
            azimuth = math.atan2(direction[2], direction[0])
            azimuth += rng.choice((-1, 1)) * rng.uniform(.55, 1.35)
            elevation = rng.uniform(.22, .64)
            child_dir = (math.cos(azimuth) * math.cos(elevation), math.sin(elevation),
                         math.sin(azimuth) * math.cos(elevation))
            limb(position, child_dir, length * rng.uniform(.52, .71),
                 junction_radius * .72, order + 1, ancestor)

    current: Point4 = (0., 0., 0., 0.)
    parent = None
    azimuth = rng.uniform(0, math.tau)
    for step in range(12):
        end = (current[0] + rng.uniform(-.13, .17),
               current[1] + rng.uniform(.49, .65),
               current[2] + rng.uniform(-.12, .12), (step + 1) * .045)
        r0 = .36 * (1 - step / 14) ** 1.2
        r1 = .36 * (1 - (step + 1) / 14) ** 1.2
        parent = add(current, end, r0, r1, parent, 0)
        current = end
        if step >= 4:
            azimuth += 2.39996 + rng.uniform(-.30, .30)
            elevation = rng.uniform(.24, .57) + step * .017
            direction = (math.cos(azimuth) * math.cos(elevation), math.sin(elevation),
                         math.sin(azimuth) * math.cos(elevation))
            limb(current, direction, rng.uniform(3.0, 4.7) * (1 - (step - 5) * .025),
                 r1 * .71, 1, parent)
    return Tree(seed, tuple(segments), tuple(leaves))
