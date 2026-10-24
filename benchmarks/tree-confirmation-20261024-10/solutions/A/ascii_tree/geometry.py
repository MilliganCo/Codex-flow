"""Seeded broadleaf trees. All modes share this immutable, four-component graph."""

from dataclasses import dataclass
import math
import random

Vec3 = tuple[float, float, float]


def add(a: Vec3, b: Vec3) -> Vec3:
    return tuple(x + y for x, y in zip(a, b))


def mul(a: Vec3, scale: float) -> Vec3:
    return tuple(x * scale for x in a)


def unit(a: Vec3) -> Vec3:
    length = math.sqrt(sum(x * x for x in a))
    return mul(a, 1.0 / length) if length > 1e-12 else (0.0, 1.0, 0.0)


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


@dataclass(frozen=True, slots=True)
class Point4:
    x: float
    y: float
    z: float
    w: float

    @property
    def xyz(self) -> Vec3:
        return self.x, self.y, self.z


@dataclass(frozen=True, slots=True)
class Segment:
    start: int
    end: int
    radius_start: float
    radius_end: float
    parent: int | None
    order: int


@dataclass(frozen=True, slots=True)
class Leaf:
    position: Point4
    radius: float
    normal: Vec3


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    vertices: tuple[Point4, ...]
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]

    @property
    def bounds(self) -> tuple[float, float, float]:
        """Vertical extent and horizontal radius, including foliage."""
        points = self.vertices + tuple(leaf.position for leaf in self.leaves)
        return (min(p.y for p in points), max(p.y for p in points),
                max(math.hypot(p.x, p.z) for p in points))


def generate_tree(seed: int = 42) -> Tree:
    """A curved leader with spiral scaffold limbs, laterals and fine twigs.

    W is developmental distance from the root, scaled into spatial units.
    Recursion stops at order 3, with a second hard segment budget.
    No global RNG, time, hashing or mode participates in generation.
    """
    rng = random.Random(seed)
    vertices = [Point4(0.0, 0.0, 0.0, 0.0)]
    segments: list[Segment] = []
    leaves: list[Leaf] = []
    budget = 1800

    def extend(start: int, position: Vec3, r0: float, r1: float,
               parent: int | None, order: int) -> tuple[int, int]:
        origin = vertices[start]
        distance = math.dist(origin.xyz, position)
        vertex = Point4(*position, origin.w + distance * 0.55)
        end = len(vertices)
        vertices.append(vertex)
        index = len(segments)
        segments.append(Segment(start, end, r0, r1, parent, order))
        return end, index

    def foliage(node: int, size: float, count: int) -> None:
        origin = vertices[node]
        for _ in range(count):
            normal = unit((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
            spread = rng.random() ** (1 / 3) * size
            offset = (normal[0] * spread, normal[1] * spread * 0.65,
                      normal[2] * spread)
            position = add(origin.xyz, offset)
            leaves.append(Leaf(Point4(*position, origin.w + spread * 0.08),
                               rng.uniform(0.065, 0.13), normal))

    def branch(start: int, direction: Vec3, length: float, radius: float,
               order: int, parent: int) -> None:
        if order > 3 or len(segments) + 6 > budget:
            return
        count = 5 if order == 1 else 4
        current = start
        previous = parent
        nodes: list[tuple[int, int, Vec3, float]] = []
        for step in range(count):
            t = (step + 1) / count
            jitter = (rng.uniform(-0.11, 0.11), rng.uniform(-0.04, 0.09),
                      rng.uniform(-0.11, 0.11))
            direction = unit(add(add(direction, jitter), (0.0, 0.07, 0.0)))
            r0 = radius * (1 - step / count) ** 0.85
            r1 = max(radius * 0.10, radius * (1 - t) ** 0.85)
            position = add(vertices[current].xyz, mul(direction, length / count))
            current, previous = extend(current, position, r0, r1, previous, order)
            nodes.append((current, previous, direction, r1))
        if order < 3:
            # Alternate sides around the local axis; no coplanar Y template.
            phase = rng.uniform(0, math.tau)
            for child_number, node_index in enumerate((1, 2, count - 1)):
                node, ancestor, tangent, node_radius = nodes[node_index]
                basis = unit(cross(tangent, (0.0, 1.0, 0.05)))
                other = unit(cross(tangent, basis))
                azimuth = phase + child_number * 2.4 + rng.uniform(-0.4, 0.4)
                lateral = add(mul(basis, math.cos(azimuth)), mul(other, math.sin(azimuth)))
                shoot = unit(add(add(mul(tangent, 0.65), mul(lateral, 0.85)),
                                 (0.0, 0.35, 0.0)))
                branch(node, shoot, length * rng.uniform(0.40, 0.63),
                       min(node_radius * 0.8, radius * 0.48), order + 1, ancestor)
            foliage(current, 0.30 if order == 1 else 0.40, 9)
        else:
            for node, _, _, _ in nodes[1:]:
                foliage(node, rng.uniform(0.30, 0.49), rng.randint(7, 12))

    height = rng.uniform(8.7, 10.5)
    phase = rng.uniform(0, math.tau)
    trunk_nodes: list[tuple[int, int, float]] = []
    current = 0
    previous = None
    for step in range(14):
        t = (step + 1) / 14
        bend = t * t
        position = (math.sin(t * 2 + phase) * bend * 0.8,
                    height * t,
                    math.cos(t * 2.7 + phase) * bend * 0.55)
        r0 = 0.43 * (1 - step / 14) ** 0.95 + 0.018
        r1 = 0.43 * (1 - t) ** 0.95 + 0.018
        current, previous = extend(current, position, r0, r1, previous, 0)
        trunk_nodes.append((current, previous, r1))
    # Lower limbs reach outward; upper limbs are shorter and more upright.
    for step in range(4, 14):
        node, ancestor, radius = trunk_nodes[step]
        t = step / 14
        azimuth = phase + step * 2.39996 + rng.uniform(-0.45, 0.45)
        direction = unit((math.cos(azimuth), 0.35 + t * 0.65,
                          math.sin(azimuth)))
        length = (4.6 - t * 2.4) * rng.uniform(0.83, 1.18)
        branch(node, direction, length, radius * rng.uniform(0.55, 0.72), 1, ancestor)
    foliage(current, 0.40, 16)
    # Buttress roots attach to the very same root vertex.
    for number in range(5):
        angle = phase + number * math.tau / 5
        reach = rng.uniform(0.55, 1.0)
        extend(0, (math.cos(angle) * reach, -0.10, math.sin(angle) * reach),
               0.22, 0.015, None, 1)
    return Tree(seed, tuple(vertices), tuple(segments), tuple(leaves))
