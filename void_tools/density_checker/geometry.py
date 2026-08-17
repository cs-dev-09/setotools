"""Budget maths - how many triangles a mesh of this size is entitled to.

Pure functions, no bpy: the operator measures the mesh and everything after
that is arithmetic, which is what makes this testable without a scene.

A flat triangles-per-square-metre bar cannot grade a bottle and a room shell
at once: real detail packed into a tiny surface measures thousands per m²
while a clean structural wall measures single digits, and one threshold is
always unfair to one of them. What vanilla GTA V assets actually follow is a
budget that grows with the **square root** of surface area - measured across
Franklin's house, `1000 × √area` puts three quarters of its render meshes
under 1× and leaves only hero props past 4×.

So the verdict is the ratio of what a mesh spends to what its size entitles
it to. The colour that ratio turns into is `shared/budget.py`'s, shared with
every other Analysis tool so that 1× means the same thing across the tab -
`fraction` and `colour` are re-exported here because this module is where
the tool reaches for them.
"""

import math

from ..shared.budget import (  # noqa: F401  (re-exported for this package)
    GREEN,
    GREEN_RATIO,
    RED,
    RED_RATIO,
    YELLOW,
    colour,
    fraction,
)


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
