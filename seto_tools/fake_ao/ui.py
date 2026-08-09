import bpy

from ..shared import ui_common


class SETO_PT_fake_ao_panel(bpy.types.Panel):
    bl_label = "Fake AO"
    bl_idname = "SETO_PT_fake_ao_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # Shared with the other Seto tools: every panel using this category is
    # merged by Blender into one "Seto Tools" N-panel tab, each tool appearing
    # as its own collapsible section (the way Sollumz Tools is laid out).
    # The order groups them by what they work on: edge strips first - this (0),
    # Fake Damage (1), Smooth Edge (2) - then the surface tools, Decal Tool (3)
    # and Surface Painter (4).
    bl_category = "Seto Tools"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 0

    def draw_header(self, context):
        self.layout.label(text="", icon='MOD_SOLIDIFY')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_fake_ao

        if ui_common.draw_sollumz_warning(layout):
            return

        col = layout.column(align=True)
        col.prop(settings, "width")
        col.prop(settings, "surface_offset")
        col.prop(settings, "merge_distance")

        layout.separator()
        col = layout.column(align=True)
        col.prop(settings, "alpha_center")
        col.prop(settings, "alpha_outer")
        layout.prop(settings, "invert_fade")

        layout.separator()
        layout.prop(settings, "flip_direction")
        layout.prop(settings, "material_mode")

        layout.separator()
        layout.operator("seto.create_fake_ao", text="Create Fake AO", icon='MOD_SOLIDIFY')

        if context.mode != 'EDIT_MESH':
            layout.label(text="Enter Edit Mode and select edges first.", icon='INFO')


class SETO_PT_fake_ao_object_panel(bpy.types.Panel):
    """Settings of the selected Fake AO strip, editable after the fact.

    Nested under the Fake AO section rather than given its own tab, and only
    drawn when the active object is actually one of our strips.
    """
    bl_label = "Selected Strip"
    bl_idname = "SETO_PT_fake_ao_object_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_parent_id = "SETO_PT_fake_ao_panel"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and obj.seto_fake_ao_data.is_fake_ao)

    def draw_header(self, context):
        self.layout.label(text="", icon='MODIFIER')

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        data = obj.seto_fake_ao_data

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
            layout.operator("seto.fake_ao_rebuild", icon='FILE_REFRESH')


_classes = (SETO_PT_fake_ao_panel, SETO_PT_fake_ao_object_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
