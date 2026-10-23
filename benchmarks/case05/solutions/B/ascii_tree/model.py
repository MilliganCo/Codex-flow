"""Bounded, seeded broadleaf growth. Coordinates use Y up; W encodes birth age."""

from dataclasses import dataclass
import math
import random

Vec3 = tuple[float, float, float]
Vec4 = tuple[float, float, float, float]


def add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a: Vec3, scale: float) -> Vec3:
    return (a[0] * scale, a[1] * scale, a[2] * scale)


def unit(a: Vec3) -> Vec3:
    length = math.sqrt(sum(v * v for v in a))
    if length < 1e-12:
        return (0.0, 1.0, 0.0)
    return mul(a, 1.0 / length)


@dataclass(frozen=True, slots=True)
class Segment:
    start: Vec4
    end: Vec4
    radius_start: float
    radius_end: float
    parent: int | None
    order: int


@dataclass(frozen=True, slots=True)
class Leaf:
    position: Vec4
    tone: float


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]


def generate_tree(seed: int) -> Tree:
    """One connected graph, at most 4 branching orders, no global RNG state.

    Continuations inherit their parent's exact endpoint and end radius. Side
    branches start thinner. Golden-angle placement avoids artificial flat fans.
    """
    rng = random.Random(seed)
    segments: list[Segment] = []
    leaves: list[Leaf] = []
    height = rng.uniform(9.4, 11.0)
    phase = rng.uniform(0, math.tau)

    def append(start: Vec4, end: Vec4, r0: float, r1: float,
               parent: int | None, order: int) -> int:
        if len(segments) >= 2500:
            raise RuntimeError("bounded growth segment budget exceeded")
        segments.append(Segment(start, end, r0, r1, parent, order))
        return len(segments) - 1

    def foliage(p: Vec4, count: int) -> None:
        for _ in range(count):
            # Sparse clusters leave the supporting limbs visible.
            dx, dy, dz = (rng.gauss(0, s) for s in (0.30, 0.20, 0.30))
            leaves.append(Leaf((p[0] + dx, p[1] + dy, p[2] + dz, p[3]),
                               rng.random()))

    def grow(start: Vec4, direction: Vec3, length: float, radius: float,
             order: int, parent: int) -> None:
        steps = 5 if order == 1 else 4 if order == 2 else 3
        p = start
        tangent = direction
        bend = rng.uniform(-0.09, 0.09)
        nodes: list[tuple[Vec4, Vec3, int, float]] = []
        for step in range(steps):
            t = (step + 1) / steps
            tangent = unit((tangent[0] - tangent[2] * bend + rng.uniform(-0.10, 0.10),
                            tangent[1] * 0.85 + (0.11 if order < 3 else 0.08),
                            tangent[2] + tangent[0] * bend + rng.uniform(-0.10, 0.10)))
            xyz = add(p[:3], mul(tangent, length / steps))
            # Monotonic age along every root-to-tip path, already centered.
            end = (*xyz, p[3] + length / steps * 0.40)
            r0 = radius * (1 - 0.84 * step / steps)
            r1 = radius * (1 - 0.84 * t)
            parent = append(p, end, r0, r1, parent, order)
            nodes.append((end, tangent, parent, r1))
            p = end
            if order == 3 and step >= 1:
                foliage(p, rng.randint(4, 7))

        if order >= 3:
            return
        for index in (1, 2, steps - 1):
            node, tangent, branch_parent, node_radius = nodes[index]
            azimuth = math.atan2(tangent[2], tangent[0])
            azimuth += rng.choice((-1, 1)) * rng.uniform(0.55, 1.30)
            rise = rng.uniform(0.35, 0.85)
            child_dir = unit((math.cos(azimuth), rise, math.sin(azimuth)))
            child_length = length * rng.uniform(0.40, 0.61)
            grow(node, child_dir, child_length,
                 min(node_radius * 0.73, radius * 0.48), order + 1, branch_parent)

    p: Vec4 = (0.0, 0.0, 0.0, -3.0)
    parent = None
    trunk: list[tuple[Vec4, int, float]] = []
    base = rng.uniform(0.35, 0.43)
    for i in range(13):
        t = (i + 1) / 13
        end = (0.23 * math.sin(t * 3 + phase) * t,
               height * t, 0.26 * math.sin(t * 4 + phase) * t,
               -3 + height * t * 0.40)
        r0 = base * (1 - 0.94 * i / 13) ** 1.1
        r1 = base * (1 - 0.94 * t) ** 1.1
        parent = append(p, end, r0, r1, parent, 0)
        trunk.append((end, parent, r1))
        p = end

    for i in range(3, 12):
        node, branch_parent, radius = trunk[i]
        azimuth = phase + i * 2.39996 + rng.uniform(-0.25, 0.25)
        # Lower limbs spread out; upper limbs form a narrower, irregular crown.
        envelope = math.sin((i / 13) * math.pi) ** 0.55
        length = (3.4 + 1.7 * envelope) * rng.uniform(0.86, 1.10)
        rise = rng.uniform(0.28, 0.52) + 0.25 * (i / 13)
        direction = unit((math.cos(azimuth), rise, math.sin(azimuth)))
        grow(node, direction, length, radius * 0.67, 1, branch_parent)
    grow(trunk[-1][0], unit((0.2, 1.0, -0.1)), 1.7,
         trunk[-1][2], 2, trunk[-1][1])
    return Tree(seed, tuple(segments), tuple(leaves))
