"""The colour scale, spelled out, and where its numbers come from.

Shown in the tool's own panel. The bands are the measured shape of a
vanilla GTA interior rather than anybody's opinion - Franklin's house, 261
render meshes, three quarters of them under 1x and only hero props past 4x
- and saying so is the point of the footnote: a user who knows the scale is
Rockstar's own can read a colour as information instead of as a telling-off.

Which is also why nothing here scolds. A red mesh is not a mistake; it is a
mesh spending more than vanilla would, which is exactly what a hero prop is
supposed to do.
"""

# (icon, band, meaning) - icons are Blender's collection-colour swatches,
# picked to match where the band sits on the green-yellow-red ramp.
BANDS = (
    ('COLLECTION_COLOR_04', "< 0.25×", "walls, glass, big surfaces"),
    ('COLLECTION_COLOR_03', "0.25–1×", "normal props - vanilla spend"),
    ('COLLECTION_COLOR_02', "1–2×", "detailed props"),
    ('COLLECTION_COLOR_02', "2–4×", "rich detail - hero territory"),
    ('COLLECTION_COLOR_01', "4×+", "hero props, or room to optimise"),
)

FOOTNOTE = (
    "1× is what vanilla GTA spends on a mesh this size.",
    "Measured from Franklin's house: of its 261 meshes,",
    "three quarters sit under 1× and only hero props",
    "pass 4×. Red is a flag, not a mistake.",
)


def draw(layout):
    col = layout.column(align=True)
    for icon, band, meaning in BANDS:
        row = col.row(align=True)
        row.label(text=f"{band}  {meaning}", icon=icon)
    foot = layout.column(align=True)
    foot.scale_y = 0.8
    for line in FOOTNOTE:
        foot.label(text=line)
