"""Budget maths - how many triangles a mesh of this size is entitled to.

Pure functions, no bpy: the operator measures the mesh and everything after
that is arithmetic, which is what makes this testable without a scene.

A flat triangles-per-square-metre bar cannot grade a bottle and a room shell
at once: real detail packed into a tiny surface measures thousands per m²
while a clean structural wall measures single digits, and one threshold is
always unfair to one of them. What vanilla GTA V assets actually follow is a
budget that grows with the **square root** of surface area - measured across
the stock inventory, `1000 × √area` lands a bottle, a chair, a tyre and a
room shell all near 1× of budget, which is exactly what "vanilla is the
standard" should mean.

So the verdict is the ratio of what a mesh spends to what its size entitles
it to, on a log scale: 0.25× and under is fully green, 1× - spot on the
vanilla budget - is yellow, 4× and over is fully red, and every doubling in
between is one equal visual step.
"""

import math

GREEN = (0.05, 0.65, 0.10, 1.0)
YELLOW = (0.95, 0.85, 0.10, 1.0)
RED = (0.90, 0.10, 0.08, 1.0)

# Where the colours pin, as multiples of the budget. Yellow falls exactly at
# 1× because log(1) is the midpoint of log(1/4) and log(4).
GREEN_RATIO = 0.25
RED_RATIO = 4.0


def budget(c, area):
    """Triangles a surface of `area` m² is entitled to, at `c` per √m²."""
    return c * math.sqrt(area)


def ratio(triangle_count, c, area):
    """How many times its budget a mesh spends, or None when there is no
    surface to entitle it to anything - a mesh of loose or degenerate
    triangles has a count but no area, and dividing by it would rank the
    object by float noise."""
    if area <= 1e-9:
        return None
    return triangle_count / budget(c, area)


def density(triangle_count, area):
    """Triangles per square metre - shown for information, not judged."""
    if area <= 1e-9:
        return None
    return triangle_count / area


def fraction(value):
    """Where a budget ratio sits on the colour scale, 0 green to 1 red.

    None (no measurable surface) pins to 1: geometry that manages triangles
    without area is the exact thing a budget pass exists to point at.
    """
    if value is None:
        return 1.0
    if value <= GREEN_RATIO:
        return 0.0
    if value >= RED_RATIO:
        return 1.0
    return math.log(value / GREEN_RATIO) / math.log(RED_RATIO / GREEN_RATIO)


def colour(t):
    """Green through yellow to red, as an object viewport colour."""
    if t <= 0.5:
        return _lerp(GREEN, YELLOW, t * 2.0)
    return _lerp(YELLOW, RED, (t - 0.5) * 2.0)


def _lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))
