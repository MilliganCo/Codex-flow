"""Seeded, bounded, botanical-inspired branching graph; no rendering state."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random

from .geometry import Vec3, Vec4, add, cross, mul, unit

MAX_ORDER = 3
MAX_SEGMENTS = 6000


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
    position: Vec4
    size: float
    tone: float


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    vertices: tuple[Vec4, ...]
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]
    center: Vec4
    scale: float

    def normalized(self, point: Vec4) -> Vec4:
        return tuple((p - c) / self.scale for p, c in zip(point, self.center))  # type: ignore[return-value]


def generate_tree(seed: int = 42) -> Tree:
    rng = random.Random(seed)
    vertices: list[Vec4] = [(0.0, 0.0, 0.0, 0.0)]
    segments: list[Segment] = []
    leaves: list[Leaf] = []

    def extend(start: int, direction: Vec3, length: float, r0: float,
               r1: float, parent: int | None, order: int) -> tuple[int, int]:
        if len(segments) >= MAX_SEGMENTS:
            raise RuntimeError("generation segment budget exceeded")
        p = vertices[start]
        xyz = add(p[:3], mul(unit(direction), length))
        # Developmental distance from the root, in the same units as XYZ.
        vertices.append((*xyz, p[3] + length * 0.55))
        segments.append(Segment(start, len(vertices) - 1, r0, r1, parent, order))
        return len(vertices) - 1, len(segments) - 1

    def foliage(vertex: int, direction: Vec3, amount: int) -> None:
        p = vertices[vertex]
        for _ in range(amount):
            # Small, porous tufts around fine twigs; big limbs remain exposed.
            offset = (rng.gauss(0, 0.25), rng.gauss(0.05, 0.18), rng.gauss(0, 0.25))
            pos = add(add(p[:3], mul(direction, rng.uniform(0, 0.3))), offset)
            leaves.append(Leaf((*pos, p[3]), rng.uniform(0.07, 0.13), rng.random()))

    def branch(start: int, parent: int, direction: Vec3, length: float,
               radius: float, order: int) -> None:
        direction = unit(direction)
        count = 5 if order == 1 else 4
        node, previous = start, parent
        forks: list[tuple[int, int, Vec3, float]] = []
        for step in range(count):
            t = (step + 1) / count
            direction = unit(add(direction, (rng.uniform(-0.09, 0.09),
                                             0.07 + order * 0.012,
                                             rng.uniform(-0.09, 0.09))))
            r0 = max(0.012, radius * (1.0 - 0.85 * step / count))
            r1 = max(0.009, radius * (1.0 - 0.85 * t))
            node, previous = extend(node, direction, length / count, r0, r1, previous, order)
            if step in (count - 4, count - 2, count - 1):
                forks.append((node, previous, direction, t))
            if order >= 2 and step >= count - 2:
                foliage(node, direction, 3 if order == 2 else 6)
        if order >= MAX_ORDER:
            return
        # A local orthogonal frame makes secondary forks genuinely spatial.
        u = unit(cross(direction, (0.0, 1.0, 0.0))
                 if abs(direction[1]) < 0.95 else cross(direction, (1.0, 0.0, 0.0)))
        v = cross(u, direction)
        phase = rng.uniform(0, math.tau)
        for i, (origin, ancestor, tangent, t) in enumerate(forks):
            azimuth = phase + i * 2.6
            lateral = add(mul(u, math.cos(azimuth)), mul(v, math.sin(azimuth)))
            child_dir = unit(add(add(mul(tangent, 0.65), mul(lateral, 0.8)), (0, 0.32, 0)))
            branch(origin, ancestor, child_dir, length * rng.uniform(0.48, 0.66),
                   max(0.025, radius * (0.43 - 0.12 * t)), order + 1)

    height = rng.uniform(8.8, 10.3)
    lean = (rng.uniform(-0.12, 0.12), 1.0, rng.uniform(-0.1, 0.1))
    node, parent = 0, None
    origins: list[tuple[int, int, int]] = []
    for step in range(15):
        direction = unit(add(lean, (rng.uniform(-0.08, 0.08), 0, rng.uniform(-0.08, 0.08))))
        t0, t1 = step / 15, (step + 1) / 15
        # Buttressed base tapering into a slender leader.
        r0 = 0.50 * (1 - t0) ** 1.3 + 0.025
        r1 = 0.50 * (1 - t1) ** 1.3 + 0.025
        node, parent = extend(node, direction, height / 15, r0, r1, parent, 0)
        if step >= 4:
            origins.append((node, parent, step))
    phase = rng.uniform(0, math.tau)
    for origin, ancestor, step in origins:
        t = step / 15
        azimuth = phase + step * 2.399963 + rng.uniform(-0.32, 0.32)
        reach = (1.0 - t) ** 0.65 * rng.uniform(4.8, 6.8) + 0.8
        elevation = rng.uniform(0.2, 0.5) + t * 0.26
        direction = unit((math.cos(azimuth), elevation, math.sin(azimuth)))
        branch(origin, ancestor, direction, reach, 0.17 * (1 - t) + 0.045, 1)

    points = vertices + [leaf.position for leaf in leaves]
    low = tuple(min(p[i] for p in points) for i in range(4))
    high = tuple(max(p[i] for p in points) for i in range(4))
    center = tuple((a + b) / 2 for a, b in zip(low, high))
    # Stable framing across modes/angles: never re-fit a rotated frame.
    scale = max((high[i] - low[i]) / 2 for i in range(3)) * 1.08
    return Tree(seed, tuple(vertices), tuple(segments), tuple(leaves), center, scale)  # type: ignore[arg-type]
