"""The Color 1 vertex colour every Seto tool writes.

Kept in one place so the tools cannot drift apart: they all write the same RGB,
and differ only in the alpha they fade between.

    RGB    0.0, 0.7, 0.0   (#00B200)
    alpha  1.0 at the centre of the strip, 0.0 at its outer edge

The alpha is the part that does the work - it is what the decal shaders use as
their blend factor, so full at the crease and zero at the edge is what makes a
strip fade out instead of ending on a visible border.

The RGB is not read by the shaders these tools use: decal.sps takes its base
colour from the texture, and decal_normal_only only perturbs the normal. It is
fixed here anyway so every generated strip carries the same, recognisable value
rather than whatever each tool happened to default to.

Written through Sollumz's create_color_attr, which stores BYTE_COLOR via
`color_srgb`. That matters for mid-range values - they go through an sRGB
conversion on the way to bytes - but not for the 0.0 / 1.0 alphas above.
"""

# (R, G, B) written to Color 1 on every generated vertex.
DEFAULT_RGB = (0.0, 0.7, 0.0)

# Alpha at the corner/centre of a strip, and at its outer edge.
DEFAULT_ALPHA_CENTER = 1.0
DEFAULT_ALPHA_OUTER = 0.0
