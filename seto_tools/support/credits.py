"""Who this is better because of, drawn inside the add-on.

The names live here rather than only in the README, because the README is not
where somebody using the tool is looking. Blender's own add-on entry shows the
author and the two link buttons; this is the rest of it.

**Nobody is listed without asking, and the rule is not decorative.** A sponsor
appears here only if their sponsorship is public on the sponsors page - a
private one is thanked privately and never written into shipped code, where it
would travel to every user of the add-on. A contributor appears once their pull
request is merged, since the commit is public either way. Anyone can ask to be
removed, and the answer is yes without a reason.

A link is optional on purpose: not everyone thanked here has a GitHub account
to point at.
"""

# (name, url or "", what for). Keep the "what for" short enough for the N-panel.
CONTRIBUTORS = (
    ("cs-dev-09", "https://github.com/cs-dev-09", "Vertex Colour picker"),
    ("gecu", "https://github.com/gecu3d", "Material Maker"),
)

SPONSORS = (
    ("Zydrec", "https://github.com/Zydrec", "the first to fund this"),
)

# What the add-on is built on. Not a courtesy - Sollumz does the GTA V half of
# every tool here, and Material Maker is a port of somebody else's algorithms.
BUILT_ON = (
    ("Sollumz", "https://docs.sollumz.org",
     "the shaders, the export, the whole pipeline"),
    ("Materialize", "https://github.com/BoundingBoxSoftware/Materialize",
     "the maps Material Maker generates (GPL-3)"),
)


def _people(layout, title, entries, icon):
    box = layout.box()
    box.label(text=title, icon=icon)
    col = box.column(align=True)
    for name, url, what in entries:
        row = col.row(align=True)
        if url:
            row.operator("wm.url_open", text=name, icon='URL').url = url
        else:
            # No account to point at. Still named, just not linked.
            sub = row.row()
            sub.enabled = False
            sub.label(text=name, icon='USER')
        note = row.row()
        note.enabled = False
        note.label(text=what)


def draw(layout):
    """The Thank You block, for the add-on preferences."""
    layout.separator()
    header = layout.row()
    header.label(text="Thank You", icon='FUND')

    _people(layout, "Contributors", CONTRIBUTORS, 'COMMUNITY')
    _people(layout, "Sponsors", SPONSORS, 'FUND')
    _people(layout, "Built on", BUILT_ON, 'PLUGIN')

    note = layout.column(align=True)
    note.scale_y = 0.8
    note.enabled = False
    note.label(text="Sponsors are listed only if their sponsorship is public.")
    note.label(text="Ask on the issue tracker to be added or removed.")
