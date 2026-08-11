"""What the two severities mean, and how far the tool will go itself.

The other Analysis tools explain a colour ramp; this one has no colours,
but it has the same problem to solve - a list of findings is only useful
if the reader knows how much each one matters and how far to trust it.

Drawn whether or not a run has happened, unlike the other two legends: the
most useful moment for "here is what this catches, and it will not touch
your mesh" is *before* the button is pressed.
"""

LEVELS = (
    ('ERROR', "Breaks in game", "it will not draw the way it looks here"),
    ('INFO', "Worth knowing", "it exports, but a known bug starts here"),
)

FOOTNOTE = (
    "Every check is something vanilla barely does:",
    "261 of Franklin's 265 meshes come back clean,",
    "and the four that do not trip the mildest one.",
    "Fix appears only where the repair is mechanical",
    "and there is one right answer - it is a single",
    "undo step, and the status bar says what it did.",
    "An unwrap or a shader choice is yours, so those",
    "findings explain instead of acting.",
)


def draw(layout):
    col = layout.column(align=True)
    for icon, title, meaning in LEVELS:
        col.row(align=True).label(text=f"{title} - {meaning}", icon=icon)
    foot = layout.column(align=True)
    foot.scale_y = 0.8
    for line in FOOTNOTE:
        foot.label(text=line)
