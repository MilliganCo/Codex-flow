"""Seeded branch graph. Geometry is independent of the display mode."""
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
    center: Point
    radius: float
    tone: int


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]


def _unit(x: float, y: float, z: float) -> tuple[float, float, float]:
    length = math.sqrt(x*x + y*y + z*z)
    return (x/length, y/length, z/length) if length > 1e-12 else (0., 1., 0.)


def generate_tree(seed: int = 42) -> Tree:
    """Finite, asymmetric broadleaf crown with three orders of woody branches.

    W is developmental time: the base is 0, terminal shoots approach 1.
    Every child starts at its parent's exact endpoint, including W.
    """
    rng = random.Random(seed)
    segments: list[Segment] = []
    leaves: list[Leaf] = []

    def foliage(p: Point, amount: int = 5) -> None:
        for _ in range(amount):
            spread = rng.uniform(.12, .40)
            leaves.append(Leaf(Point(p.x + rng.gauss(0, spread),
                                     p.y + rng.gauss(.10, spread*.6),
                                     p.z + rng.gauss(0, spread), p.w),
                               rng.uniform(.06, .14), rng.randrange(5)))

    def branch(start: Point, parent: int, direction: tuple[float, float, float],
               length: float, radius: float, order: int) -> None:
        steps = 6 if order == 1 else 4
        p, previous = start, parent
        dx, dy, dz = direction
        for i in range(steps):
            dx, dy, dz = _unit(dx + rng.uniform(-.14, .14),
                               dy + .07 + rng.uniform(-.08, .08),
                               dz + rng.uniform(-.14, .14))
            step = length / steps * rng.uniform(.84, 1.16)
            growth = start.w + (1-start.w)*((i+1)/steps)*(.44 if order < 3 else .96)
            q = Point(p.x+dx*step, p.y+dy*step, p.z+dz*step, growth)
            r0 = radius * (1-.88*i/steps)**.85
            r1 = radius * (1-.88*(i+1)/steps)**.85
            index = len(segments)
            segments.append(Segment(p, q, r0, r1, previous, order))
            if order < 3 and i in (2, steps-1):
                phi = rng.choice((-1, 1))*rng.uniform(.65, 1.35)
                child_direction = _unit(dx*math.cos(phi)-dz*math.sin(phi),
                                        dy*.5+rng.uniform(.12, .40),
                                        dx*math.sin(phi)+dz*math.cos(phi))
                branch(q, index, child_direction, length*rng.uniform(.42, .64),
                       r1*.68, order+1)
            if order == 3 and i >= 1:
                foliage(q, 4)
            elif order == 2 and i == steps-1:
                foliage(q, 3)
            p, previous = q, index

    p = Point(0., 0., 0., 0.)
    parent = None
    sway = rng.uniform(-.18, .18)
    for i in range(15):
        q = Point(p.x + sway + rng.uniform(-.10, .10),
                  p.y + rng.uniform(.53, .68),
                  p.z + rng.uniform(-.13, .13), (i+1)/15*.56)
        r0 = .43*(1-i/16)**1.18
        r1 = .43*(1-(i+1)/16)**1.18
        index = len(segments)
        segments.append(Segment(p, q, r0, r1, parent, 0))
        if 4 <= i <= 13:
            theta = i*2.399963 + rng.uniform(-.4, .4)
            length = (3.8 - abs(i-8)*.29)*rng.uniform(.83, 1.15)
            branch(q, index, _unit(math.cos(theta), rng.uniform(.22, .62),
                                    math.sin(theta)), length, r1*.62, 1)
        p, parent = q, index
    foliage(p, 8)
    return Tree(seed, tuple(segments), tuple(leaves))
