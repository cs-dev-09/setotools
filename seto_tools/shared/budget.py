"""The green-yellow-red ramp every Analysis tool grades against.

One vocabulary for "how far past vanilla is this": a tool measures whatever
it measures - triangles against a size-scaled entitlement, texels per metre
against a target - divides by what vanilla spends, and hands the ratio here.
1× is always "what Rockstar spends on this", whatever *this* happens to be,
which is what lets two tools' colours mean the same thing side by side.

The scale is logarithmic between the pins so every doubling is one equal
visual step. On a linear ramp the single worst offender takes the whole top
of the range and everything else reads as "green, roughly".
"""

import math

GREEN = (0.05, 0.65, 0.10, 1.0)
YELLOW = (0.95, 0.85, 0.10, 1.0)
RED = (0.90, 0.10, 0.08, 1.0)

# Where the colours pin, as multiples of the budget. Yellow falls exactly at
# 1× because log(1) is the midpoint of log(1/4) and log(4).
GREEN_RATIO = 0.25
RED_RATIO = 4.0


def fraction(value):
    """Where a budget ratio sits on the colour scale, 0 green to 1 red.

    None means "nothing to measure against" - a mesh with triangles but no
    surface, an object with no texture - and pins to 1: it is the exact
    thing a budget pass exists to point at.
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
