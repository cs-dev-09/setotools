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

SPONSOR_URL = "https://github.com/sponsors/seto3d"
ISSUES_URL = "https://github.com/seto3d/setotools/issues"


def draw_links(layout):
    """The two buttons, drawn the same way wherever they appear."""
    col = layout.column(align=True)
    col.scale_y = 1.2
    col.operator("wm.url_open", text="Report a Bug",
                 icon='URL').url = ISSUES_URL
    col.operator("wm.url_open", text="Become a Sponsor",
                 icon='FUND').url = SPONSOR_URL


class SETO_PT_support_panel(bpy.types.Panel):
    bl_label = "Support"
    bl_idname = "SETO_PT_support_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    # Last in the tab, after the three tool sections.
    bl_order = 3
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
        col.prop(settings, "title")
        col.separator()
        col.prop(settings, "steps")
        col.prop(settings, "result")
        col.prop(settings, "expected")
        box.prop(settings, "include_environment")

        row = box.row(align=True)
        row.scale_y = 1.3
        row.operator("seto.support_report", icon='URL')
        box.operator("seto.support_copy", icon='COPYDOWN')

        note = box.column(align=True)
        note.scale_y = 0.8
        note.label(text="Opens GitHub with this filled in. Nothing")
        note.label(text="is sent until you press Submit there.")
        note.label(text="A .blend attached to the issue is worth")
        note.label(text="more than anything written here.")

        layout.separator()
        draw_links(layout)

        note = layout.column(align=True)
        note.scale_y = 0.8
        note.label(text="Seto Tools is free and stays free.")


_classes = (SETO_PT_support_panel,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
