"""Pure sampling logic for Trash Scatter.

No bpy and no Sollumz here: triangles in, placements out, everything in
world space. What this solves is "random but controlled" - three properties
a plain per-triangle random scatter does not have:

1. **Even coverage.** Points are dart-thrown against a per-item spacing
   radius, so two props never stack and a burst of luck never empties one
   corner while flooding another.
2. **Edge bias.** Real litter collects where feet do not go: along walls
   and in corners. Each candidate point knows its distance to the boundary
   of the selected floor region, and the bias setting turns that into an
   acceptance probability - 0 is uniform, 1 puts nearly everything within
   arm's reach of a wall.
3. **Determinism.** One seed, one layout. Re-running with the same settings
   rebuilds the same floor, which is what makes the seed a design control
   rather than a dice roll.
"""

import math
import random

from mathutils import Vector

# How quickly the wall-hugging preference falls off with distance from the
# region boundary, in metres. At 0.4 m the probability boost has dropped to
# 1/e - roughly "within a stride of the wall", which is where litter lives.
EDGE_FALLOFF = 0.4

# Give up after this many rejected darts per requested placement. Guards the
# pathological cases (spacing larger than the floor, bias 1 on a floor with
# no boundary near anything) without ever refusing the easy ones.
MAX_ATTEMPTS_PER_ITEM = 30

# How quickly a cluster's pull fades with distance from its centre, in
# metres - roughly the radius of one believable heap of litter.
CLUSTER_FALLOFF = 0.9

# One attraction point per this many square metres, and never fewer than
# two: a single cluster reads as a spawn point, two read as habit.
AREA_PER_CLUSTER = 10.0


class Placement:
    """One accepted sample: where, which item, how turned and how scaled."""

    __slots__ = ("position", "item", "yaw", "scale", "radius", "lying")

    def __init__(self, position, item, yaw, scale, radius, lying=False):
        self.position = position
        self.item = item
        self.yaw = yaw
        self.scale = scale
        self.radius = radius
        self.lying = lying


def triangle_area(a, b, c):
    return (b - a).cross(c - a).length / 2.0


def _pick_triangle(rng, triangles, cumulative, total_area):
    """Area-weighted triangle pick, then a uniform point via barycentrics."""
    target = rng.random() * total_area
    lo, hi = 0, len(cumulative) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cumulative[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    a, b, c = triangles[lo]
    r1 = math.sqrt(rng.random())
    r2 = rng.random()
    return a * (1.0 - r1) + b * (r1 * (1.0 - r2)) + c * (r1 * r2)


def _segment_distance_sq(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 0.0:
        t = 0.0
    else:
        t = ((px - ax) * dx + (py - ay) * dy) / length_sq
        t = max(0.0, min(1.0, t))
    cx, cy = ax + dx * t, ay + dy * t
    return (px - cx) ** 2 + (py - cy) ** 2


# Beyond this the wall-hugging term is exp(-7.5) - nothing. Queries stop
# looking there, which is what bounds the work per sample on a floor whose
# rim is thousands of segments long.
BOUNDARY_REACH = 3.0


class BoundaryIndex:
    """Nearest-boundary distance, bucketed so a query is not a full scan.

    The plain version measured every sample against every rim segment.
    On a real MLO floor that is thousands of segments times thousands of
    samples times two consumers (the litter's edge bias and the dirt
    overlay's, once per overlay vertex) - which is exactly why the tool
    felt slow. Segments are dropped into 1 m cells here; a query walks
    rings outward from its own cell and stops as soon as the best hit is
    closer than the next ring could possibly be.
    """

    CELL = 1.0

    def __init__(self, boundaries):
        self.cells = {}
        self.segments = list(boundaries)
        for index, (ax, ay, bx, by) in enumerate(self.segments):
            lo_x = int(math.floor(min(ax, bx) / self.CELL))
            hi_x = int(math.floor(max(ax, bx) / self.CELL))
            lo_y = int(math.floor(min(ay, by) / self.CELL))
            hi_y = int(math.floor(max(ay, by) / self.CELL))
            for cx in range(lo_x, hi_x + 1):
                for cy in range(lo_y, hi_y + 1):
                    self.cells.setdefault((cx, cy), []).append(index)

    def __bool__(self):
        return bool(self.segments)

    def distance(self, point):
        """2D distance to the nearest boundary, clamped at BOUNDARY_REACH.

        2D on purpose: the boundary of a sloped floor still reads as "the
        wall line" from above, and litter piles against the wall, not
        against the wall's altitude.
        """
        if not self.segments:
            return BOUNDARY_REACH
        px, py = point.x, point.y
        base_x = int(math.floor(px / self.CELL))
        base_y = int(math.floor(py / self.CELL))
        best_sq = math.inf
        max_ring = int(math.ceil(BOUNDARY_REACH / self.CELL))

        for ring in range(max_ring + 1):
            # Anything outside this ring is at least (ring-1) cells away,
            # so a hit already closer than that cannot be beaten.
            if best_sq < ((ring - 1) * self.CELL) ** 2:
                break
            for cx in range(base_x - ring, base_x + ring + 1):
                for cy in range(base_y - ring, base_y + ring + 1):
                    if ring and max(abs(cx - base_x), abs(cy - base_y)) != ring:
                        continue          # interior of the ring, already done
                    for index in self.cells.get((cx, cy), ()):
                        ax, ay, bx, by = self.segments[index]
                        dist_sq = _segment_distance_sq(px, py, ax, ay, bx, by)
                        if dist_sq < best_sq:
                            best_sq = dist_sq
        if best_sq is math.inf:
            return BOUNDARY_REACH
        return min(BOUNDARY_REACH, math.sqrt(best_sq))


def as_boundary_index(boundaries):
    """Accept either a raw segment list or an already-built index."""
    if isinstance(boundaries, BoundaryIndex):
        return boundaries
    return BoundaryIndex(boundaries or ())


def _distance_to_boundary(point, boundaries):
    """Convenience wrapper - builds an index for one-off callers."""
    return as_boundary_index(boundaries).distance(point)


def scatter(triangles, boundaries, items, density, seed, edge_bias,
            scale_jitter, base_scale=1.0, topple=0.0, field=None,
            clustering=0.0):
    """Compute placements over a triangulated floor region.

    `triangles`: [(Vector, Vector, Vector), ...] in world space.
    `boundaries`: [(ax, ay, bx, by), ...] - the region's open edges, world
        space, flattened to 2D.
    `items`: [(weight, radius, lying_radius, standing), ...] - the caller
        keeps the names; placements refer to items by index.
    `topple`: the chance a *standing* item (a bottle, a can) is laid on
        its side instead - real litter is mostly knocked over. Flat items
        ignore it.
    `field`: optional callable point -> [0, 1] that biases acceptance -
        the dirt overlay's own noise goes here, so the litter gathers
        where the grime is dark and thins where the floor is clean.
    `clustering`: 0 spreads as before; toward 1 the litter gathers into
        heaps around a few seeded attraction points - cigarette butts by
        a doorway, not one per square metre. The points themselves obey
        the edge bias, so the heaps form where litter really piles.
    `density`: requested placements per square metre.
    `edge_bias`: 0 = uniform, 1 = almost everything near the boundary.
    `scale_jitter`: half-width of the uniform scale range around 1.0.
    `base_scale`: every prop's scale is this times its jitter - GTA props
        are their real size, so 1.0 is realism and anything else is a
        stylistic choice the user asked to be able to make.

    Returns a list of Placement. May return fewer than density*area asks
    for when spacing genuinely does not fit more - that is the controlled
    part working, not a failure.
    """
    if not triangles or not items:
        return []

    areas = [triangle_area(*tri) for tri in triangles]
    total_area = sum(areas)
    if total_area <= 0.0:
        return []

    cumulative = []
    running = 0.0
    for area in areas:
        running += area
        cumulative.append(running)

    requested = max(1, round(density * total_area))
    rng = random.Random(seed)
    index = as_boundary_index(boundaries)

    # The attraction points come first, from the same rng, so one seed is
    # still one layout. Each is dart-thrown with the same edge-bias
    # acceptance the litter uses - a heap in the middle of the room is
    # exactly as unlikely as a single bottle there.
    centers = []
    if clustering > 0.0:
        wanted_centers = max(2, round(total_area / AREA_PER_CLUSTER))
        tries = wanted_centers * 20
        while len(centers) < wanted_centers and tries > 0:
            tries -= 1
            candidate = _pick_triangle(rng, triangles, cumulative, total_area)
            if index and edge_bias > 0.0:
                distance = index.distance(candidate)
                keep = (1.0 - edge_bias) \
                    + edge_bias * math.exp(-distance / EDGE_FALLOFF)
                if rng.random() > keep:
                    continue
            centers.append(candidate)

    weights = [item[0] for item in items]
    placements = []
    attempts = requested * MAX_ATTEMPTS_PER_ITEM

    # The spacing grid's cell has to be at least the largest possible
    # exclusion diameter, or a 3x3 neighbourhood could miss a conflict.
    biggest = max(max(item[1], item[2]) for item in items)
    spacing_cell = max(1e-4,
                       2.0 * biggest * base_scale * (1.0 + scale_jitter))
    occupied = {}

    while len(placements) < requested and attempts > 0:
        attempts -= 1
        point = _pick_triangle(rng, triangles, cumulative, total_area)

        if index and edge_bias > 0.0:
            distance = index.distance(point)
            keep = (1.0 - edge_bias) + edge_bias * math.exp(-distance / EDGE_FALLOFF)
            if rng.random() > keep:
                continue

        if field is not None:
            # Never a hard mask: 0.3 base keeps a clean patch sparsely
            # littered rather than suspiciously spotless.
            if rng.random() > 0.3 + 0.7 * field(point):
                continue

        if centers:
            # Pull, do not reject: an accept/reject gate here just spends
            # the attempt budget refilling the quota from everywhere and
            # the heaps dilute away (measured - the clumpiness test
            # caught it). Warping the sample toward its nearest centre
            # keeps the count and concentrates it; spacing still holds
            # afterwards, so a heap saturates instead of stacking.
            center = min(centers,
                         key=lambda c: (point.x - c.x) ** 2
                         + (point.y - c.y) ** 2)
            pull = clustering * rng.uniform(0.5, 0.95)
            point = point.lerp(center, pull)

        item = rng.choices(range(len(items)), weights=weights)[0]
        scale = base_scale * (1.0 + rng.uniform(-scale_jitter, scale_jitter))
        _weight, radius_up, radius_lying, standing = items[item]
        lying = standing and rng.random() < topple
        radius = (radius_lying if lying else radius_up) * scale

        # Spacing through a uniform grid rather than against every prop
        # placed so far: the pairwise version is quadratic, and a dense
        # floor spends most of its time there.
        cell_x = int(math.floor(point.x / spacing_cell))
        cell_y = int(math.floor(point.y / spacing_cell))
        too_close = False
        for nx in range(cell_x - 1, cell_x + 2):
            for ny in range(cell_y - 1, cell_y + 2):
                for other in occupied.get((nx, ny), ()):
                    limit = radius + other.radius
                    dx = point.x - other.position.x
                    dy = point.y - other.position.y
                    if dx * dx + dy * dy < limit * limit:
                        too_close = True
                        break
                if too_close:
                    break
            if too_close:
                break
        if too_close:
            continue

        yaw = rng.uniform(0.0, math.tau)
        placement = Placement(Vector(point), item, yaw, scale, radius, lying)
        placements.append(placement)
        occupied.setdefault((cell_x, cell_y), []).append(placement)

    return placements
