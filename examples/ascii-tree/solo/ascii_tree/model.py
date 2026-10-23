"""A seeded, connected broadleaf tree with a curved leader and recursive limbs."""

from dataclasses import dataclass
import hashlib
import json
import math
import random

from .geometry import Vec3, Vec4

MAX_ORDER = 4
MAX_SEGMENTS = 5000
FINGERPRINT_FORMAT = "ascii-tree-fixed9-v1"


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
    segment: int
    tone: int


@dataclass(frozen=True, slots=True)
class Tree:
    seed: int
    vertices: tuple[Vec4, ...]
    segments: tuple[Segment, ...]
    leaves: tuple[Leaf, ...]

    @property
    def fingerprint(self) -> str:
        """Identify the full graph at nine decimal places, not libm's last bit."""
        def scalar(value: float) -> str:
            if not math.isfinite(value):
                raise ValueError("fingerprint requires finite geometry")
            text = format(value, ".9f")
            return "0.000000000" if text == "-0.000000000" else text

        def point(value: Vec4) -> tuple[str, ...]:
            return tuple(scalar(v) for v in (value.x, value.y, value.z, value.w))

        payload = {
            "format": FINGERPRINT_FORMAT,
            "seed": self.seed,
            "vertices": tuple(map(point, self.vertices)),
            "segments": tuple((s.start, s.end, scalar(s.radius_start), scalar(s.radius_end),
                               s.parent, s.order) for s in self.segments),
            "leaves": tuple((point(leaf.position), scalar(leaf.size), leaf.segment, leaf.tone)
                            for leaf in self.leaves),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canonical.encode("ascii")).hexdigest()[:16]


def generate_tree(seed: int) -> Tree:
    """Generate once; all views consume precisely the same immutable graph.

    Branches fork around local tangent frames, not an XY template. W is the
    normalized birth time along root-to-tip distance, centered for rotation.
    Leaves inherit their supporting twig's birth time.
    """
    rng = random.Random(seed)
    points = [Vec3(0, 0, 0)]
    ages = [0.0]
    segments: list[Segment] = []
    leaf_data: list[tuple[Vec3, float, float, int, int]] = []

    def add(start: int, end: Vec3, radius: float, tip: float,
            parent: int | None, order: int) -> tuple[int, int]:
        if len(segments) >= MAX_SEGMENTS:
            raise RuntimeError("tree segment budget exceeded")
        end_id = len(points)
        points.append(end)
        ages.append(ages[start] + (end - points[start]).length())
        segment_id = len(segments)
        segments.append(Segment(start, end_id, radius, tip, parent, order))
        return end_id, segment_id

    def leaf_cluster(end: int, segment_id: int, spread: float) -> None:
        # Sparse clusters leave the larger branch orders visible.
        for _ in range(rng.randint(7, 12)):
            offset = Vec3(rng.gauss(0, spread), rng.gauss(0.10, spread * .58),
                          rng.gauss(0, spread))
            leaf_data.append((points[end] + offset, ages[end],
                              rng.uniform(.06, .13), segment_id, rng.randrange(5)))

    def limb(start: int, direction: Vec3, length: float, radius: float,
             parent: int, order: int) -> None:
        # Fixed depth and explicit budget bound all recursion/work.
        count = 4 if order == 1 else 3
        current, previous = start, parent
        tangent = direction.unit()
        for step in range(count):
            t = (step + 1) / count
            tangent = (tangent + Vec3(rng.uniform(-.10, .10), .10,
                                      rng.uniform(-.10, .10))).unit()
            end = points[current] + tangent * (length / count * rng.uniform(.86, 1.14))
            r0 = radius * (1 - .82 * step / count)
            r1 = radius * (1 - .82 * t)
            current, previous = add(current, end, r0, r1, previous, order)
            if order < MAX_ORDER and step >= 1:
                # Golden-angle progression avoids regular, mirrored forks.
                helper = Vec3(0, 1, 0) if abs(tangent.y) < .94 else Vec3(1, 0, 0)
                u = tangent.cross(helper).unit()
                v = tangent.cross(u).unit()
                phi = rng.uniform(0, math.tau) + step * 2.39996
                side = u * math.cos(phi) + v * math.sin(phi)
                child_direction = (tangent * .58 + side * .83 + Vec3(0, .20, 0)).unit()
                limb(current, child_direction, length * rng.uniform(.40, .61),
                     r1 * rng.uniform(.48, .65), previous, order + 1)
            if order >= 3 and step >= 1:
                leaf_cluster(current, previous, .24 if order == 3 else .19)
        if order == MAX_ORDER:
            leaf_cluster(current, previous, .29)

    trunk_nodes: list[tuple[int, int, float]] = []
    current, parent = 0, None
    lean_x, lean_z = rng.uniform(-.16, .16), rng.uniform(-.13, .13)
    for index in range(13):
        height = (index + 1) * .89
        end = Vec3(lean_x * height + .14 * math.sin(index * .7), height,
                   lean_z * height + .12 * math.sin(index * .9))
        radius = .49 * (1 - index / 14) ** 1.25
        tip = .49 * (1 - (index + 1) / 14) ** 1.25
        current, parent = add(current, end, radius, tip, parent, 0)
        trunk_nodes.append((current, parent, tip))

    azimuth = rng.uniform(0, math.tau)
    for index, (node, segment_id, tip) in enumerate(trunk_nodes[3:12], 3):
        azimuth += 2.39996 + rng.uniform(-.27, .27)
        for fork in range(2 if index in (4, 6, 8) else 1):
            angle = azimuth + fork * 2.7
            direction = Vec3(math.cos(angle), rng.uniform(.24, .65), math.sin(angle))
            length = (6.5 - abs(index - 6) * .60) * rng.uniform(.88, 1.15)
            limb(node, direction, length, max(.07, tip * .72), segment_id, 1)
    limb(current, Vec3(.2, 1, .1), 2.1, .05, len(trunk_nodes) - 1, 2)

    max_age = max(ages)

    def point4(point: Vec3, age: float) -> Vec4:
        return Vec4(point.x, point.y, point.z, (age / max_age - .5) * 12.0)

    return Tree(seed, tuple(point4(p, age) for p, age in zip(points, ages)),
                tuple(segments),
                tuple(Leaf(point4(p, age), size, segment_id, tone)
                      for p, age, size, segment_id, tone in leaf_data))
