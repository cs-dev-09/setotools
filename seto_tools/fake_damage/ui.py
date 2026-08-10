import bpy

from ..shared import groups, icons, manual_offset, panel_layout as pl, ui_common
from ..fake_ao.ui import _draw_bevel


class SETO_PT_fake_damage_panel(bpy.types.Panel):
    bl_label = "Edge Wear"
    bl_idname = "SETO_PT_fake_damage_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # First of the two Geometry tools, above Smooth Edge (1). Both build mesh
    # along the selected edges; this is the one that breaks the edge up.
    bl_category = "Seto Tools"
    bl_parent_id = groups.GEOMETRY
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 0

    def draw_header(self, context):
        icons.draw_header(self.layout, "fake_damage", 'MOD_EXPLODE')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_fake_damage

        if ui_common.draw_sollumz_warning(layout):
            return

        # Nothing to set before Create. UV Scale and UV Offset are live on the
        # finished strip, and listing them here as well only invited dragging
        # the copy that does nothing - see strip_settings.draw().
        pl.create_button(layout, "seto.create_fake_damage", "Create Edge Wear",
                         'MOD_EDGESPLIT')
        pl.edit_mode_hint(layout, context)


class SETO_PT_fake_damage_object_panel(pl.SelectedPanel, bpy.types.Panel):
    """Settings of the selected Edge Wear strip, editable after the fact.

    Nested under the Edge Wear section rather than given its own tab, and
    only drawn when the active object is actually one of our strips. Every row
    here is live: changing it rebuilds the strip in place.
    """
    bl_label = "Selected Strip"
    bl_idname = "SETO_PT_fake_damage_object_panel"
    bl_parent_id = "SETO_PT_fake_damage_panel"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and obj.seto_fake_damage_data.is_fake_damage)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        data = obj.seto_fake_damage_data

        pl.object_header(layout, obj, data)

        col = pl.section(layout, "Shape", 'MOD_SOLIDIFY')
        col.prop(data, "width")
        col.prop(data, "surface_offset")
        col.prop(data, "merge_distance")
        col.prop(data, "flip_direction")

        # Across the strip first, then along the run - see shared/run_fade.py.
        col = pl.section(layout, "Fade", 'IMAGE_ALPHA')
        col.prop(data, "alpha_center")
        col.prop(data, "alpha_outer")
        col.prop(data, "invert_fade")
        col.separator()
        col.prop(data, "alpha_bottom")
        col.prop(data, "alpha_top")

        col = pl.section(layout, "Texture Placement", 'UV')
        col.prop(data, "uv_scale")
        col.prop(data, "uv_offset")

        manual_offset.draw(layout, data, "seto_fake_damage_data")

        layout.separator()
        if data.edge_keys:
            _draw_bevel(layout, data, tool_label="Edge Wear")
        else:
            box = layout.box()
            box.scale_y = 0.8
            box.label(text="Bevel needs a selected edge.", icon='INFO')

        if not data.live_update:
            pl.rebuild_button(layout, "seto.fake_damage_rebuild")


_classes = (SETO_PT_fake_damage_panel, SETO_PT_fake_damage_object_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
