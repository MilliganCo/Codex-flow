"""A bounded, seeded branch graph shared by every viewing mode."""

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
    radius: float
    tone: float


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(c * c for c in v))
    if length < 1e-12:
        return (0.0, 1.0, 0.0)
    return tuple(c / length for c in v)


def generate_tree(seed: int = 42) -> Tree:
    """Grow an asymmetric broadleaf tree; no global RNG or unbounded recursion.

    W encodes accumulated distance along a growth path, centered around zero.
    Parent endpoints are reused exactly, including their W coordinate.
    """
    rng = random.Random(seed)
    segments: list[Segment] = []
    leaves: list[Leaf] = []
    max_segments = 4000

    def add(start: Point4, direction: tuple[float, float, float], length: float,
            radius: float, end_radius: float, parent: int | None, order: int) -> int:
        if len(segments) >= max_segments:
            raise RuntimeError("generation segment budget exceeded")
        dx, dy, dz = _unit(direction)
        end = Point4(start.x + dx * length, start.y + dy * length,
                     start.z + dz * length, start.w + length * 0.52)
        segments.append(Segment(start, end, radius, end_radius, parent, order))
        return len(segments) - 1

    def grow(parent: int, direction: tuple[float, float, float], length: float,
             radius: float, order: int) -> None:
        current = parent
        heading = direction
        steps = 3 if order <= 2 else 2
        for step in range(steps):
            heading = _unit((heading[0] + rng.uniform(-0.13, 0.13),
                             heading[1] + rng.uniform(0.01, 0.16),
                             heading[2] + rng.uniform(-0.13, 0.13)))
            fraction = step / steps
            current = add(segments[current].end, heading, length / steps,
                          radius * (1 - 0.45 * fraction),
                          radius * (1 - 0.45 * (step + 1) / steps), current, order)
        end = segments[current].end
        if order >= 4:
            # Small clusters, with gaps so the branch skeleton remains visible.
            for _ in range(rng.randint(6, 10)):
                point = Point4(end.x + rng.gauss(0, 0.36), end.y + rng.gauss(0, 0.26),
                               end.z + rng.gauss(0, 0.36), end.w + rng.uniform(0, 0.22))
                leaves.append(Leaf(point, rng.uniform(0.12, 0.25), rng.random()))
            return
        # Fork in a local basis perpendicular to the branch, not a flat XY Y.
        dx, dy, dz = heading
        side = _unit((-dz, 0, dx))
        cross = _unit((dy * side[2] - dz * side[1],
                       dz * side[0] - dx * side[2], dx * side[1] - dy * side[0]))
        phase = rng.uniform(-math.pi, math.pi)
        children = 3 if order == 1 and rng.random() < 0.35 else 2
        for child in range(children):
            angle = phase + child * (2 * math.pi / children) + rng.uniform(-0.35, 0.35)
            spread = rng.uniform(0.36, 0.7)
            heading_child = _unit(tuple(heading[k] + spread * (math.cos(angle) * side[k]
                                      + math.sin(angle) * cross[k]) for k in range(3)))
            # Gravity competition: every fork keeps a positive upward tendency.
            heading_child = _unit((heading_child[0], max(0.16, heading_child[1]), heading_child[2]))
            grow(current, heading_child, length * rng.uniform(0.58, 0.73),
                 radius * rng.uniform(0.49, 0.61), order + 1)

    trunk_nodes: list[int] = []
    start = Point4(0, 0, 0, -4.5)
    parent = None
    lean_x, lean_z = rng.uniform(-0.065, 0.065), rng.uniform(-0.065, 0.065)
    for i in range(11):
        radius = 0.50 * (1 - i / 12) ** 1.25 + 0.035
        end_radius = 0.50 * (1 - (i + 1) / 12) ** 1.25 + 0.035
        parent = add(start, (lean_x + rng.uniform(-0.045, 0.045), 1,
                             lean_z + rng.uniform(-0.045, 0.045)),
                     rng.uniform(0.87, 1.03), radius, end_radius, parent, 0)
        trunk_nodes.append(parent)
        start = segments[parent].end

    # Buttress roots connect to the first trunk endpoint, and flare at the ground.
    for i in range(5):
        phi = i * math.tau / 5 + rng.uniform(-0.25, 0.25)
        add(segments[0].end, (math.cos(phi), -0.7, math.sin(phi)),
            rng.uniform(1.25, 1.7), 0.28, 0.045, 0, 1)

    phase = rng.uniform(0, math.tau)
    for level in range(3, 11):
        for branch in range(2 if level < 8 else 1):
            phase += 2.3999632297 + rng.uniform(-0.28, 0.28)
            elevation = rng.uniform(0.32, 0.60) + (level - 3) * 0.035
            length = rng.uniform(3.4, 4.5) * (1 - 0.037 * (level - 3))
            grow(trunk_nodes[level], _unit((math.cos(phase), elevation, math.sin(phase))),
                 length, segments[trunk_nodes[level]].radius_end * 0.62, 1)
    return Tree(seed, tuple(segments), tuple(leaves))
