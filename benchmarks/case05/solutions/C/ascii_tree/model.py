"""Bounded, seeded botanical growth. All views share this immutable graph."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random

from .math4d import Point4


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
    position: Point4
    radius: float
    tone: float
    parent: int


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]
    center: Point4
    radius: float


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(x * x for x in v))
    return tuple(x / length for x in v) if length > 1e-9 else (0.0, 1.0, 0.0)


def generate_tree(seed: int = 42) -> Tree:
    """A curved leader, irregular whorls, lateral limbs and leafy fine twigs.

    W records accumulated growth distance, not a display-mode parameter.
    Recursion stops at order 3, with an independent segment budget of 3000.
    """
    rng = random.Random(seed)
    segments: list[Segment] = []
    leaves: list[Leaf] = []
    budget = 3000

    def add(start: Point4, end: Point4, r0: float, r1: float, parent: int | None, order: int) -> int:
        if len(segments) >= budget:
            raise RuntimeError("Tree segment budget exceeded")
        segments.append(Segment(start, end, r0, r1, parent, order))
        return len(segments) - 1

    def foliage(point: Point4, parent: int, count: int) -> None:
        for _ in range(count):
            # Small loose clusters leave windows through which wood stays readable.
            offset = (rng.gauss(0, 0.19), rng.gauss(0.04, 0.15), rng.gauss(0, 0.19))
            p = Point4(point.x + offset[0], point.y + offset[1], point.z + offset[2], point.w + 0.05)
            leaves.append(Leaf(p, rng.uniform(0.065, 0.13), rng.random(), parent))

    def limb(start: Point4, direction: tuple[float, float, float], length: float,
             radius: float, parent: int, order: int) -> None:
        steps = 7 if order == 1 else 5 if order == 2 else 4
        direction = _unit(direction)
        azimuth = math.atan2(direction[2], direction[0])
        side = rng.choice((-1, 1))
        previous = parent
        point = start
        for j in range(steps):
            t = j / steps
            # Curving toward light, with reproducible small departures from a straight line.
            direction = _unit((direction[0] + rng.uniform(-0.07, 0.07),
                               direction[1] + 0.065, direction[2] + rng.uniform(-0.07, 0.07)))
            step = length / steps * rng.uniform(0.88, 1.12)
            end = Point4(point.x + direction[0] * step, point.y + direction[1] * step,
                         point.z + direction[2] * step, point.w + step * 0.62)
            r0 = max(0.009, radius * (1 - t) ** 0.85)
            r1 = max(0.008, radius * (1 - (j + 1) / steps) ** 0.85)
            current = add(point, end, r0, r1, previous, order)
            if order < 3 and j in ((2, 4, 6) if order == 1 else (2, 4)):
                side *= -1
                a = azimuth + side * rng.uniform(0.55, 1.25)
                child_direction = (math.cos(a), rng.uniform(0.25, 0.7), math.sin(a))
                child_length = length * rng.uniform(0.34, 0.5) * (1 - t * 0.25)
                limb(end, child_direction, child_length, r1 * 0.58, current, order + 1)
            if order == 3 and j >= 1:
                foliage(end, current, 3)
            point, previous = end, current
        foliage(point, previous, 6 if order >= 2 else 3)

    point = Point4(0, 0, 0, 0)
    previous: int | None = None
    height = rng.uniform(9.4, 11.1)
    phase = rng.uniform(0, math.tau)
    lean_x, lean_z = rng.uniform(-0.6, 0.6), rng.uniform(-0.5, 0.5)
    for i in range(15):
        t = (i + 1) / 15
        end = Point4(lean_x * t + 0.18 * math.sin(t * 5 + phase) - 0.18 * math.sin(phase),
                     height * t, lean_z * t + 0.13 * math.sin(t * 7), height * t * 0.62)
        r0 = 0.39 * (1 - i / 16) ** 1.12 + (0.11 if i == 0 else 0)
        r1 = 0.39 * (1 - (i + 1) / 16) ** 1.12
        current = add(point, end, r0, r1, previous, 0)
        if 4 <= i <= 13:
            # Golden-angle distribution avoids a flat, mirrored Y skeleton.
            angle = phase + i * 2.399963 + rng.uniform(-0.3, 0.3)
            branch_length = (5.8 - (i - 4) * 0.32) * rng.uniform(0.8, 1.17)
            limb(end, (math.cos(angle), rng.uniform(0.3, 0.65), math.sin(angle)),
                 branch_length, r1 * 0.7, current, 1)
            if i in (5, 8, 10):
                a = angle + rng.uniform(2.0, 3.0)
                limb(end, (math.cos(a), 0.55, math.sin(a)), branch_length * 0.8, r1 * 0.57, current, 1)
        point, previous = end, current
    foliage(point, previous, 10)

    points = [s.end for s in segments] + [segments[0].start] + [leaf.position for leaf in leaves]
    bounds = [(min(p.values()[i] for p in points), max(p.values()[i] for p in points)) for i in range(4)]
    center = Point4(*((lo + hi) / 2 for lo, hi in bounds))
    # Rotation-invariant 4D bounding sphere makes camera scale stable across modes.
    radius = max(math.sqrt(sum((a - b) ** 2 for a, b in zip(p.values(), center.values()))) for p in points) + 0.5
    return Tree(seed, tuple(segments), tuple(leaves), center, radius)
