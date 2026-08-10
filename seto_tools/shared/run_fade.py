"""Fading a strip ALONG its run, rather than across it.

Alpha Center and Alpha Outer fade a strip across the shelf, from the corner out
onto the wall. This is the other direction: a run that goes floor to ceiling
usually should not arrive at either end at full strength.

Written once here because every tool that builds a strip wants it. Ambient
Occlusion grew it first and still carries its own copy - deduplicating that
means editing a file another chat is working in, so it is left for after the
next push rather than done twice in parallel.

The ramp is linear, because that is what the geometry can carry: a run built
from ONE selected edge has two vertices along its length, and two vertices
cannot describe a curve. Subdividing the source edge gives a tighter falloff,
the same as it does for everything else in these tools.
"""

from mathutils import Vector


def local_up_axis(matrix_world):
    """World "up", expressed in the object's own local space.

    Strips are built in the source's local space, but bottom and top mean the
    bottom and top of the *building*, not of the object's axes - a wall whose
    object happens to be rotated still has to fade toward the actual floor.

    A point's world Z is row 2 of `matrix_world` dotted with the local point
    (plus that row's translation, which drops out of any comparison), so the
    row IS the direction local positions grow world-upward along. Taken
    directly rather than by inverting the matrix, which gets non-uniform scale
    wrong.
    """
    row = matrix_world[2]
    return Vector((row[0], row[1], row[2]))


def apply(vertex_alpha, run_points, up_axis, alpha_bottom, alpha_top):
    """Scale each vertex's alpha by where along the run it sits.

    `run_points[i]` is the point on the SOURCE edge that vertex `i` was
    generated from - not the vertex's own position. The two differ the moment
    the run is not vertical: a wall-to-floor edge is all one height, but its
    strip climbs the wall, so measuring the vertices themselves would fade the
    top of the *shelf* and call it the top of the run. Measured properly, a run
    with no height has nothing to fade between and is left alone.

    Multiplies whatever the across-fade already produced, so 1.0 at both ends
    is a no-op rather than a flattening.
    """
    if up_axis is None or (alpha_bottom >= 1.0 and alpha_top >= 1.0):
        return
    if up_axis.length < 1e-9 or not run_points:
        return

    up = up_axis.normalized()
    heights = [point.dot(up) for point in run_points]
    low, high = min(heights), max(heights)
    span = high - low
    if span < 1e-6:
        return

    for index, height in enumerate(heights):
        if index >= len(vertex_alpha):
            break
        from_bottom = (height - low) / span
        vertex_alpha[index] *= (
            (alpha_bottom + (1.0 - alpha_bottom) * from_bottom)
            * (alpha_top + (1.0 - alpha_top) * (1.0 - from_bottom))
        )
