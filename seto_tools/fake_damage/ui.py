import bpy

from ..shared import groups, icons, ui_common


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

        # Only what this tool alone owns. The strip's shape and fade are drawn
        # once by the Geometry section above - they were identical here and in
        # Smooth Edge, which is what made the tab read as the same panel twice.
        col = layout.column(align=True)
        col.prop(settings, "uv_scale")
        col.prop(settings, "uv_offset")

        layout.separator()
        layout.operator("seto.create_fake_damage", text="Create Edge Wear", icon='MOD_EDGESPLIT')

        if context.mode != 'EDIT_MESH':
            layout.label(text="Enter Edit Mode and select edges first.", icon='INFO')
        else:
            layout.label(text="Settings stay live on the created strip.", icon='INFO')


class SETO_PT_fake_damage_object_panel(bpy.types.Panel):
    """Settings of the selected Edge Wear strip, editable after the fact.

    Nested under the Edge Wear section rather than given its own tab, and
    only drawn when the active object is actually one of our strips.
    """
    bl_label = "Selected Strip"
    bl_idname = "SETO_PT_fake_damage_object_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_parent_id = "SETO_PT_fake_damage_panel"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and obj.seto_fake_damage_data.is_fake_damage)

    def draw_header(self, context):
        self.layout.label(text="", icon='MODIFIER')

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        data = obj.seto_fake_damage_data

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

        layout.separator()
        col = layout.column(align=True)
        col.prop(data, "uv_scale")
        col.prop(data, "uv_offset")

        if not data.live_update:
            layout.separator()
            layout.operator("seto.fake_damage_rebuild", icon='FILE_REFRESH')


_classes = (SETO_PT_fake_damage_panel, SETO_PT_fake_damage_object_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
