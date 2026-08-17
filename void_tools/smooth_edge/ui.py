import bpy

from ..shared import groups, icons, manual_offset, panel_layout as pl, ui_common
from ..fake_ao.ui import _draw_bevel


class SETO_PT_smooth_edge_panel(bpy.types.Panel):
    bl_label = "Smooth Edge"
    bl_idname = "SETO_PT_smooth_edge_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # Second of the two Geometry tools, under Edge Wear (0). Same strip, the
    # opposite intent: this one rounds the edge off instead of chipping it.
    bl_category = pl.TAB
    bl_parent_id = groups.GEOMETRY
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 1

    def draw_header(self, context):
        icons.draw_header(self.layout, "smooth_edge", 'MOD_SMOOTH')

    def draw(self, context):
        layout = self.layout

        if ui_common.draw_sollumz_warning(layout):
            return

        # This tool has no settings of its own: it builds the same strip Edge
        # Wear does, from the shape the Geometry section above describes, and
        # puts a normal map on it instead of a damage texture. Drawing that
        # shape again here is exactly the duplication that was reported.
        pl.create_button(layout, "seto.create_smooth_edge",
                         "Create Smooth Edge", 'MOD_EDGESPLIT')
        pl.edit_mode_hint(layout, context)


class SETO_PT_smooth_edge_object_panel(pl.SelectedPanel, bpy.types.Panel):
    """Settings of the selected Smooth Edge strip, editable after the fact.

    Nested under the Smooth Edge section rather than given its own tab, and
    only drawn when the active object is actually one of our strips. Every row
    here is live: changing it rebuilds the strip in place.
    """
    bl_label = "Selected Edge"
    bl_idname = "SETO_PT_smooth_edge_object_panel"
    bl_parent_id = "SETO_PT_smooth_edge_panel"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and obj.seto_smooth_edge_data.is_smooth_edge)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        data = obj.seto_smooth_edge_data

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

        col = pl.section(layout, "Vertex Colour", 'COLOR')
        col.prop(data, "color_preset", text="")
        row = col.row()
        row.enabled = data.color_preset == 'CUSTOM'
        row.prop(data, "color_rgb", text="")

        manual_offset.draw(layout, data, "seto_smooth_edge_data")

        layout.separator()
        if data.edge_keys:
            _draw_bevel(layout, data, tool_label="Smooth Edge")
        else:
            box = layout.box()
            box.scale_y = 0.8
            box.label(text="Bevel needs a selected edge.", icon='INFO')

        if not data.live_update:
            pl.rebuild_button(layout, "seto.smooth_edge_rebuild")


_classes = (SETO_PT_smooth_edge_panel, SETO_PT_smooth_edge_object_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
