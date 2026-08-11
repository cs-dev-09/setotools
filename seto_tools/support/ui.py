"""The bug report form and the two links, at the bottom of the tab.

Where a user goes when they want to say something. Both links open a
browser through Blender's own `wm.url_open`, so nothing here talks to the
network itself - and the report is written here but **sent by the user**,
on GitHub's own page, signed in as themselves. See report.py.

A collapsed panel below the tools rather than a row inside them: a sponsor
button repeated at the foot of six tool panels is nagging, and a bug
report form is only wanted on the day something is wrong.
"""

import bpy

from ..shared import icons
from . import properties

SPONSOR_URL = "https://github.com/sponsors/seto3d"
ISSUES_URL = "https://github.com/seto3d/setotools/issues"


def draw_links(layout, issues=True):
    """The links, drawn the same way wherever they appear.

    `issues` is off in the panel, where the form above it already is the
    way to report something - a second button that only opens the issue
    list is one more thing to read past. The add-on preferences keep it,
    because there is no form there.

    "Become a Sponsor" was the wording first and it read like a request.
    Nobody opens a modelling tool wanting to be asked for money, and this
    one is free either way - so the button says where it goes and leaves
    the asking out of it.
    """
    col = layout.column(align=True)
    col.scale_y = 1.2
    if issues:
        col.operator("wm.url_open", text="Report a Bug",
                     icon='URL').url = ISSUES_URL
    col.operator("wm.url_open", text="Support the Project",
                 icon='FUND').url = SPONSOR_URL


class SETO_PT_support_panel(bpy.types.Panel):
    bl_label = "Support"
    bl_idname = "SETO_PT_support_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    # Last in the tab, after the three tool sections.
    bl_order = 4
    bl_options = {'DEFAULT_CLOSED'}

    # No Sollumz poll: the day someone most needs the bug report form is
    # the day the add-on is not working properly on their machine.

    def draw_header(self, context):
        icons.draw_header(self.layout, "support", 'COMMUNITY')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_support

        box = layout.box()
        box.label(text="Report a bug", icon='ERROR')

        col = box.column(align=True)
        col.label(text="Title")
        col.prop(settings, "title", text="")
        col.separator()

        # An aligned stack of line fields, all of them, always: aligned
        # fields at natural height share their borders and read as one
        # frame, and drawing every line every time is what keeps the
        # panel perfectly still while it is typed into. Revealing lines
        # as they filled was tried in two flavours and both moved the
        # form under the user's hands. See properties.py for the whole
        # history; in particular **never `emboss=False`** on these - it
        # removes the typing along with the border - and **no scale_y** -
        # shrinking aligned fields opens seams that read as separate
        # frames.
        for name, label in properties.FIELDS:
            col.label(text=label)
            area = col.column(align=True)
            for index in range(properties.LINES):
                area.prop(settings, f"{name}_{index}", text="")
            col.separator()

        box.prop(settings, "include_environment")

        # No file field for the picture. An image cannot travel in a URL,
        # so anything gathered here would have to be dragged onto the
        # issue by hand anyway - which is the same work, after a detour
        # through a file browser. Saying where it goes is worth more than
        # a control that cannot finish the job.
        shot = box.column(align=True)
        shot.scale_y = 0.8
        shot.label(text="Add your screenshot on GitHub - drag it",
                   icon='IMAGE_DATA')
        shot.label(text="onto the issue box after it opens.")

        row = box.row()
        row.scale_y = 1.4
        row.operator("seto.support_report", icon='URL')
        box.operator("seto.support_clear", text="Clear Report", icon='X')

        # No paragraph under the buttons explaining what Send does. The
        # preview it opens says all of it - on the screen where it still
        # matters - and a wall of small print in the panel is read once
        # and scrolled past for ever after.

        layout.separator()
        draw_links(layout, issues=False)

        note = layout.column(align=True)
        note.scale_y = 0.8
        note.label(text="Seto Tools is free and always will be.")
        note.label(text="If it saved you an afternoon, there is a")
        note.label(text="page for that - no pressure either way.")


_classes = (SETO_PT_support_panel,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
