import bpy

from ..shared import addon_prefs, groups, icons, panel_layout as pl, ui_common
from . import object_settings, operators


def _library_hint(layout, context):
    """One line on where the models come from, only when it needs saying."""
    from . import library
    prefs = addon_prefs.get(context)
    folder = getattr(prefs, "scatter_library", "") if prefs else ""
    if not folder:
        pl.hint(layout, "Boxes only: set the Prop Library folder in "
                        "the add-on preferences for real models.")
    elif not library.is_indexed(context):
        # Indexing takes minutes, so it never runs by itself - which
        # means a freshly set folder does nothing until this is pressed.
        pl.hint(layout, "Library not indexed yet - press Rescan in "
                        "the add-on preferences (takes minutes).")


class SETO_PT_scatter_panel(bpy.types.Panel):
    bl_label = "Trash Scatter"
    bl_idname = "SETO_PT_scatter_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = pl.TAB
    bl_parent_id = groups.DRESSING
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 0

    def draw_header(self, context):
        icons.draw_header(self.layout, "scatter", 'PARTICLES')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_scatter

        if ui_common.draw_sollumz_warning(layout):
            return

        col = pl.section(layout, "Props", 'OBJECT_DATA')
        col.prop(settings, "preset", text="")

        col = pl.section(layout, "Layout", 'STICKY_UVS_DISABLE')
        col.prop(settings, "density")
        col.prop(settings, "edge_bias")
        col.prop(settings, "prop_scale")
        col.prop(settings, "scale_jitter")
        col.prop(settings, "topple")
        col.prop(settings, "clustering")
        col.prop(settings, "seed")

        col = pl.section(layout, "Floor Dirt", 'MOD_FLUIDSIM')
        col.prop(settings, "dirt_enabled")
        sub = col.column(align=True)
        sub.enabled = settings.dirt_enabled
        sub.prop(settings, "dirt_amount")
        sub.prop(settings, "dirt_scale")

        pl.create_button(layout, operators.SETO_OT_scatter_create.bl_idname,
                         "Scatter", 'PARTICLES')
        row = layout.row()
        row.operator(operators.SETO_OT_scatter_clear.bl_idname,
                     icon='TRASH')

        if context.mode == 'EDIT_MESH':
            pl.hint(layout, "Scatters over the selected faces.")
        else:
            pl.hint(layout, "Edit Mode: select the floor faces first.")
        _library_hint(layout, context)


class SETO_PT_scatter_selected_panel(pl.SelectedPanel, bpy.types.Panel):
    """The scattered floor's own settings - live, like every other tool."""
    bl_label = "Selected Scatter"
    bl_idname = "SETO_PT_scatter_selected_panel"
    bl_parent_id = SETO_PT_scatter_panel.bl_idname
    bl_category = pl.TAB

    @classmethod
    def poll(cls, context):
        return object_settings.has_region(context.active_object)

    def draw(self, context):
        layout = self.layout
        floor = context.active_object
        data = floor.seto_scatter_data

        box = layout.box()
        row = box.row()
        row.label(text=floor.name, icon='OUTLINER_OB_MESH')
        count = sum(1 for obj in bpy.data.objects
                    if obj.get(object_settings.SRC_PROP) == floor.name)
        row.label(text=f"{count} props")

        layout.prop(data, "live_update")

        col = pl.section(layout, "Props", 'OBJECT_DATA')
        col.prop(data, "preset", text="")

        col = pl.section(layout, "Layout", 'STICKY_UVS_DISABLE')
        col.prop(data, "density")
        col.prop(data, "edge_bias")
        col.prop(data, "prop_scale")
        col.prop(data, "scale_jitter")
        col.prop(data, "topple")
        col.prop(data, "clustering")
        col.prop(data, "seed")

        col = pl.section(layout, "Floor Dirt", 'MOD_FLUIDSIM')
        col.prop(data, "dirt_enabled")
        sub = col.column(align=True)
        sub.enabled = data.dirt_enabled
        sub.prop(data, "dirt_amount")
        sub.prop(data, "dirt_scale")
        sub.separator()
        sub.prop(data, "dirt_tolerance")
        sub.operator(operators.SETO_OT_scatter_optimize_dirt.bl_idname,
                     icon='MOD_DECIM')

        # Always offered, not only with Live Update off: the settings are
        # not the only thing that can go stale. Scaling or moving the
        # floor changes the region's world area, and nothing watches a
        # transform - this button is the answer to "I made the floor
        # bigger and the layout did not follow".
        pl.rebuild_button(
            layout, operators.SETO_OT_scatter_rebuild.bl_idname)
        _library_hint(layout, context)


_classes = (SETO_PT_scatter_panel, SETO_PT_scatter_selected_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
