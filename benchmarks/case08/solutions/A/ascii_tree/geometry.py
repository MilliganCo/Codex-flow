"""Seeded, connected woody geometry. No rendering or global random state."""

from __future__ import annotations

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
    tone: float
    attachment: int


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    nodes: tuple[Point4, ...]
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(a * a for a in v))
    if length < 1e-12:
        return (0.0, 1.0, 0.0)
    return tuple(a / length for a in v)


def generate_tree(seed: int = 42) -> Tree:
    """Grow a trunk, scaffold limbs, secondary limbs and leafy terminal twigs.

    W measures emergence distance along the graph, centered on the tree's
    growth span. The depth bound (3) and fixed branch counts bound all work.
    Radii are always positive; each segment starts at an existing node.
    """
    rng = random.Random(seed)
    nodes = [Point4(0.0, 0.0, 0.0, 0.0)]
    distances = [0.0]
    segments: list[Segment] = []
    leaves: list[Leaf] = []

    def add(start: int, delta: tuple[float, float, float], r0: float,
            r1: float, order: int, parent: int | None) -> tuple[int, int]:
        p = nodes[start]
        distance = math.sqrt(sum(c * c for c in delta))
        distances.append(distances[start] + distance)
        nodes.append(Point4(p.x + delta[0], p.y + delta[1], p.z + delta[2], 0.0))
        segments.append(Segment(start, len(nodes) - 1, parent, r0, r1, order))
        return len(nodes) - 1, len(segments) - 1

    def foliage(node: int, radius: float) -> None:
        p = nodes[node]
        # Airy, irregular leaf sprays leave the underlying branching visible.
        for _ in range(rng.randint(8, 14)):
            azimuth = rng.uniform(0.0, math.tau)
            elevation = rng.uniform(-0.75, 0.9)
            spread = radius * rng.random() ** (1.0 / 3.0)
            ring = math.sqrt(1.0 - elevation * elevation)
            q = Point4(p.x + math.cos(azimuth) * spread * ring,
                       p.y + elevation * spread * 0.72,
                       p.z + math.sin(azimuth) * spread * ring, float(node))
            leaves.append(Leaf(q, rng.uniform(0.045, 0.09), rng.random(), node))

    def grow(start: int, direction: tuple[float, float, float], length: float,
             radius: float, order: int, parent: int) -> None:
        count = 5 if order == 1 else 4
        current, previous = start, parent
        path: list[tuple[int, int, tuple[float, float, float], float]] = []
        for j in range(count):
            # Persistent curvature, phototropism, and small non-planar deviations.
            direction = _unit((direction[0] + rng.uniform(-0.12, 0.12),
                               direction[1] + 0.075 + rng.uniform(-0.04, 0.04),
                               direction[2] + rng.uniform(-0.12, 0.12)))
            fraction = (j + 1) / count
            r0 = max(0.012, radius * (1.0 - 0.86 * j / count))
            r1 = max(0.009, radius * (1.0 - 0.86 * fraction))
            step = length / count * rng.uniform(0.88, 1.12)
            current, previous = add(current, tuple(v * step for v in direction),
                                    r0, r1, order, previous)
            path.append((current, previous, direction, r1))
        if order < 3:
            for slot in (1, 2, 3):
                node, branch_parent, tangent, branch_radius = path[slot]
                az = math.atan2(tangent[2], tangent[0])
                side = -1 if slot % 2 else 1
                az += side * rng.uniform(0.55, 1.35)
                tilt = rng.uniform(0.25, 0.62)
                child_direction = _unit((math.cos(az), tilt, math.sin(az)))
                grow(node, child_direction, length * rng.uniform(0.38, 0.60),
                     max(0.017, branch_radius * 0.72), order + 1, branch_parent)
        else:
            for node, _, _, _ in path[1:]:
                foliage(node, rng.uniform(0.35, 0.65))
        foliage(current, 0.5 if order > 1 else 0.65)

    trunk: list[tuple[int, int]] = []
    current, previous = 0, None
    lean_x, lean_z = rng.uniform(-0.10, 0.10), rng.uniform(-0.08, 0.08)
    height = rng.uniform(9.5, 11.0)
    for j in range(12):
        r0 = 0.43 * (1.0 - j / 13.0) ** 1.15 + (0.12 if j == 0 else 0.0)
        r1 = 0.43 * (1.0 - (j + 1) / 13.0) ** 1.15
        current, previous = add(current,
                                (lean_x + rng.uniform(-0.08, 0.08), height / 12,
                                 lean_z + rng.uniform(-0.07, 0.07)),
                                r0, r1, 0, previous)
        trunk.append((current, previous))

    phase = rng.uniform(0, math.tau)
    for j in range(3, 12):
        node, parent = trunk[j]
        # Golden-angle spacing avoids a flat or regularly paired silhouette.
        az = phase + j * 2.399963229728653 + rng.uniform(-0.4, 0.4)
        length = (5.6 - 0.35 * (j - 3)) * rng.uniform(0.86, 1.15)
        direction = _unit((math.cos(az), rng.uniform(0.25, 0.7), math.sin(az)))
        grow(node, direction, length, 0.20 * (1.0 - (j - 3) / 13), 1, parent)
        if j in (4, 6, 8):
            az += rng.uniform(2.0, 3.1)
            grow(node, _unit((math.cos(az), 0.5, math.sin(az))), length * 0.85,
                 0.14, 1, parent)

    # Small buttress roots visually ground the tree without a second object.
    for j in range(5):
        az = j * math.tau / 5 + phase
        root, _ = add(0, (math.cos(az) * rng.uniform(0.65, 1.1), 0.025,
                          math.sin(az) * rng.uniform(0.65, 1.1)), 0.22, 0.018, 0, None)
        distances[root] = 0.0

    span = max(distances)
    nodes = [Point4(p.x, p.y, p.z, 5.0 * d / span - 2.5)
             for p, d in zip(nodes, distances)]
    leaves = [Leaf(Point4(leaf.point.x, leaf.point.y, leaf.point.z,
                         nodes[leaf.attachment].w), leaf.size, leaf.tone, leaf.attachment)
              for leaf in leaves]
    return Tree(seed, tuple(nodes), tuple(segments), tuple(leaves))
