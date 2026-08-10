import bpy

from ..shared import groups, icons, ui_common


class SETO_PT_smooth_edge_panel(bpy.types.Panel):
    bl_label = "Smooth Edge"
    bl_idname = "SETO_PT_smooth_edge_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # Second of the two Geometry tools, under Edge Wear (0). Same strip, the
    # opposite intent: this one rounds the edge off instead of chipping it.
    bl_category = "Seto Tools"
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
        layout.operator("seto.create_smooth_edge", text="Create Smooth Edge",
                        icon='MOD_EDGESPLIT')

        if context.mode != 'EDIT_MESH':
            layout.label(text="Enter Edit Mode and select edges first.", icon='INFO')
        else:
            layout.label(text="Settings stay live on the created strip.", icon='INFO')


class SETO_PT_smooth_edge_object_panel(bpy.types.Panel):
    """Settings of the selected Smooth Edge strip, editable after the fact.

    Nested under the Smooth Edge section rather than given its own tab, and
    only drawn when the active object is actually one of our strips.
    """
    bl_label = "Selected Edge"
    bl_idname = "SETO_PT_smooth_edge_object_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_parent_id = "SETO_PT_smooth_edge_panel"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and obj.seto_smooth_edge_data.is_smooth_edge)

    def draw_header(self, context):
        self.layout.label(text="", icon='MODIFIER')

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        data = obj.seto_smooth_edge_data

        box = layout.box()
        row = box.row()
        row.label(text=obj.name, icon='OUTLINER_OB_MESH')
        row.label(text=f"{len(obj.data.polygons)} quads")
        source_row = box.row()
        source_row.enabled = False
        source_row.prop(data, "source_object", text="From")

        if data.status:
            warn = layout.box()
            warn.alert = True
            col = warn.column(align=True)
            col.label(text="Cannot rebuild:", icon='ERROR')
            for line in ui_common.wrap(data.status, 38):
                col.label(text=line)

        layout.prop(data, "live_update")

        col = layout.column(align=True)
        col.prop(data, "width")
        col.prop(data, "surface_offset")
        col.prop(data, "merge_distance")

        layout.separator()
        col = layout.column(align=True)
        col.prop(data, "alpha_center")
        col.prop(data, "alpha_outer")
        layout.prop(data, "invert_fade")
        layout.prop(data, "flip_direction")

        if not data.live_update:
            layout.separator()
            layout.operator("seto.smooth_edge_rebuild", icon='FILE_REFRESH')


_classes = (SETO_PT_smooth_edge_panel, SETO_PT_smooth_edge_object_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
