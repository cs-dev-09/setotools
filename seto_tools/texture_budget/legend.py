"""The texel scale, spelled out, and where its numbers come from.

The Density Check's legend with the other tool's units - same five bands,
same swatches, same reason for existing: a colour a user cannot trace is a
colour they will not trust, so the panel says what 1× is and which file it
was measured from.

Nothing here scolds either. A hero prop wearing a big sheet is not a
mistake; it is a hero prop.
"""

BANDS = (
    ('COLLECTION_COLOR_04', "< 0.25×", "big surfaces, tiling sheets"),
    ('COLLECTION_COLOR_03', "0.25–1×", "normal props - vanilla spend"),
    ('COLLECTION_COLOR_02', "1–2×", "sharp, for close-up work"),
    ('COLLECTION_COLOR_02', "2–4×", "hero territory"),
    ('COLLECTION_COLOR_01', "4×+", "large for its size, or room to save"),
)

# The one band that is not on the ramp: grey means "no texture to grade",
# which is a fact about the mesh rather than a verdict on it.
NEUTRAL_BAND = ('COLLECTION_COLOR_08', "grey", "no texture - nothing to grade")

FOOTNOTE = (
    "1× is the target above, in texels per metre.",
    "Measured from Franklin's house: 592 of its 601",
    "textures are 512² or smaller and the other nine",
    "reach 1024, ≈55 MB all told. Its meshes grade",
    "at a median of 0.4×. Red is a flag, not a mistake.",
)


def draw(layout):
    col = layout.column(align=True)
    for icon, band, meaning in BANDS:
        col.row(align=True).label(text=f"{band}  {meaning}", icon=icon)
    icon, band, meaning = NEUTRAL_BAND
    col.row(align=True).label(text=f"{band}  {meaning}", icon=icon)
    foot = layout.column(align=True)
    foot.scale_y = 0.8
    for line in FOOTNOTE:
        foot.label(text=line)
