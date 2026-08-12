"""The Updates panel, first in the tab.

Top-level rather than a box inside Support, at the owner's request: when
an update exists it is the one thing in the tab worth seeing first, and
the collapsed header carries the news - the version number appears right
on it, so nobody has to open anything to learn there is something new.
The rest of the time it is one closed line above Geometry.
"""

import bpy

from ..shared import icons, ui_common
from . import logic
from ..shared import panel_layout as pl


class SETO_PT_updates_panel(bpy.types.Panel):
    bl_label = "Updates"
    bl_idname = "SETO_PT_updates_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = pl.TAB
    # First in the tab - the groups start at 1 to leave this slot.
    bl_order = 0
    bl_options = {'DEFAULT_CLOSED'}

    # No Sollumz poll: updating is about this add-on, not about Sollumz,
    # and the update that fixes a broken Sollumz integration must be
    # reachable on exactly the machine where the integration is broken.

    def draw_header(self, context):
        state = context.window_manager.seto_updater
        if state.update_available:
            # The notification: the new version, on the closed header.
            self.layout.label(text=state.latest, icon='IMPORT')
        else:
            icons.draw_header(self.layout, "updates", 'FILE_REFRESH')

    def draw(self, context):
        layout = self.layout
        state = context.window_manager.seto_updater

        layout.label(text=f"Void Tools {logic.current_str()}",
                     icon='BLENDER')

        if state.update_available:
            row = layout.row()
            row.scale_y = 1.4
            row.operator("seto.update_install",
                         text=f"Install {state.latest}", icon='IMPORT')

        row = layout.row()
        row.scale_y = 1.2
        row.operator("seto.update_check", icon='URL')

        if state.status:
            note = layout.column(align=True)
            note.scale_y = 0.8
            for line in ui_common.wrap(state.status, 38):
                note.label(text=line)

        hint = layout.column(align=True)
        hint.scale_y = 0.7
        hint.label(text="Checks github.com once per start - the")
        hint.label(text="request carries nothing about you. Turn")
        hint.label(text="it off in the add-on preferences.")


_classes = (SETO_PT_updates_panel,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
