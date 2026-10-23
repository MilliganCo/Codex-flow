"""Deterministic, connected, bounded procedural branch graph in R4."""
from dataclasses import dataclass
import math
import random


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float
    z: float
    w: float


@dataclass(frozen=True, slots=True)
class Segment:
    start: Point
    end: Point
    radius_start: float
    radius_end: float
    parent: int | None
    order: int


@dataclass(frozen=True, slots=True)
class Leaf:
    position: Point
    size: float
    tone: int


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]


def generate_tree(seed: int) -> Tree:
    """An irregular leader, spiral scaffold branches and four twig orders.

    W is accumulated distance from the root / 2 - 4 (a growth coordinate).
    Children share their parent's exact endpoint, including W.
    """
    rng = random.Random(seed)
    segments: list[Segment] = []
    leaves: list[Leaf] = []

    def append(start, direction, length, radius, end_radius, parent, order):
        norm = math.sqrt(sum(v * v for v in direction))
        dx, dy, dz = (v / norm * length for v in direction)
        end = Point(start.x + dx, start.y + dy, start.z + dz, start.w + length / 2)
        segments.append(Segment(start, end, radius, end_radius, parent, order))
        return len(segments) - 1, end

    def foliage(p, direction):
        # Airy leaf sprays leave the woody skeleton legible.
        for _ in range(rng.randint(7, 12)):
            leaves.append(Leaf(Point(p.x + rng.gauss(0, .29),
                                     p.y + rng.gauss(.08, .23),
                                     p.z + rng.gauss(0, .29), p.w),
                               rng.uniform(.065, .12), rng.randrange(4)))

    def branch(start, azimuth, elevation, length, radius, parent, order):
        # Strict order/segment bounds: never depend on unbounded recursion.
        if order > 4 or len(segments) > 2200:
            return
        p = start
        ancestor = parent
        steps = 3
        for step in range(steps):
            azimuth += rng.uniform(-.12, .12)
            elevation = min(1.42, elevation + rng.uniform(.015, .12))
            direction = (math.cos(azimuth) * math.cos(elevation),
                         math.sin(elevation), math.sin(azimuth) * math.cos(elevation))
            fraction = step / steps
            r0 = radius * (1 - fraction * .45)
            r1 = radius * (1 - (step + 1) / steps * .45)
            ancestor, p = append(p, direction, length / steps, r0, r1, ancestor, order)
            if order == 4 and step > 0:
                foliage(p, direction)
        if order < 4:
            for side in (-1, 1):
                branch(p, azimuth + side * rng.uniform(.45, .95),
                       elevation + rng.uniform(-.26, .19),
                       length * rng.uniform(.53, .69), radius * .48,
                       ancestor, order + 1)
            if order < 3:
                # A shorter third shoot makes less mechanical fork shapes.
                branch(p, azimuth + rng.uniform(-1.3, 1.3), elevation + .25,
                       length * .49, radius * .38, ancestor, order + 1)

    p = Point(0, 0, 0, -4)
    parent = None
    leader_radius = .43
    spiral = rng.random() * math.tau
    for i in range(11):
        end_radius = max(.026, .43 * (1 - (i + 1) / 12) ** 1.22)
        parent, p = append(p, (rng.uniform(-.12, .12), 1, rng.uniform(-.10, .10)),
                           rng.uniform(.77, .98), leader_radius, end_radius, parent, 0)
        leader_radius = end_radius
        if i >= 2:
            azimuth = spiral + i * 2.39996 + rng.uniform(-.35, .35)
            crown_factor = math.sin((i - 1) / 11 * math.pi)
            branch(p, azimuth, rng.uniform(.18, .48),
                   (2.25 + 1.15 * crown_factor) * rng.uniform(.83, 1.16),
                   end_radius * .70, parent, 1)
            if i in (4, 6, 8):
                branch(p, azimuth + 2.3, rng.uniform(.3, .6),
                       2.5 * rng.uniform(.8, 1.1), end_radius * .55, parent, 1)
    foliage(p, (0, 1, 0))
    return Tree(seed, tuple(segments), tuple(leaves))
