import bpy

from ..shared import groups, icons, ui_common


def _draw_bevel(layout, settings, show_target):
    """The optional chamfer block, drawn the same way in the create panel and
    on a finished strip.

    `show_target` is off on a finished strip: the source bevel already
    happened once, at creation, and cannot be re-run from there.
    """
    box = layout.box()
    header = box.row()
    header.prop(settings, "bevel_enabled", text="")
    header.label(text="Bevel", icon='MOD_BEVEL')

    body = box.column(align=True)
    body.enabled = settings.bevel_enabled
    if show_target:
        body.prop(settings, "bevel_target", text="")
    body.prop(settings, "bevel_width", text="Width")
    body.prop(settings, "bevel_segments", text="Segments")
    body.prop(settings, "bevel_profile", text="Profile Shape")

    if not settings.bevel_enabled:
        return

    if show_target and settings.bevel_target in {'SOURCE', 'BOTH'}:
        box.label(text="Modifies the source mesh.", icon='ERROR')

    if settings.bevel_width >= settings.width:
        # The round eats the shelf: there is nothing flat left for the AO to
        # fade out across, and Blender clamps the bevel, so the strip's round
        # stops matching the source's.
        note = box.column(align=True)
        note.alert = True
        note.label(text="Bevel Width is not below Width.", icon='ERROR')
        note.label(text="Raise Width to leave room to fade.")


class SETO_PT_fake_ao_panel(bpy.types.Panel):
    bl_label = "Ambient Occlusion"
    bl_idname = "SETO_PT_fake_ao_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # Under the Surface section, first of its three (Decal Tool 1, Surface
    # Painter 2). It builds a strip like the two Geometry tools do, but what it
    # is for is shading a surface - which is how it gets reached for.
    bl_category = "Seto Tools"
    bl_parent_id = groups.SURFACE
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 0

    def draw_header(self, context):
        icons.draw_header(self.layout, "fake_ao", 'SHADING_RENDERED')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_fake_ao

        if ui_common.draw_sollumz_warning(layout):
            return

        col = layout.column(align=True)
        col.prop(settings, "width")
        col.prop(settings, "surface_offset")

        layout.separator()
        col = layout.column(align=True)
        col.prop(settings, "alpha_center")
        col.prop(settings, "alpha_outer")
        layout.prop(settings, "invert_fade")

        layout.separator()
        _draw_bevel(layout, settings, show_target=True)

        layout.separator()
        layout.prop(settings, "flip_direction")
        layout.prop(settings, "material_mode")

        layout.separator()
        layout.operator("seto.create_fake_ao", text="Create Ambient Occlusion", icon='MOD_SOLIDIFY')

        if context.mode != 'EDIT_MESH':
            layout.label(text="Enter Edit Mode and select edges first.", icon='INFO')


class SETO_PT_fake_ao_object_panel(bpy.types.Panel):
    """Settings of the selected Ambient Occlusion strip, editable after the fact.

    Nested under the Ambient Occlusion section rather than given its own tab, and only
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

        layout.separator()
        col = layout.column(align=True)
        col.prop(data, "alpha_center")
        col.prop(data, "alpha_outer")
        layout.prop(data, "invert_fade")
        layout.prop(data, "flip_direction")

        layout.separator()
        _draw_bevel(layout, data, show_target=False)

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
