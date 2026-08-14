import bpy

from . import object_settings
from ..shared import groups, icons, manual_offset, panel_layout as pl
from ..shared import sollumz_integration as szi


class SETO_PT_sign_glow_panel(bpy.types.Panel):
    """Sign Glow's own panel: what has to be decided before there is a halo.

    Second in the Materials section, after Material Maker (0). Both make a
    texture rather than the geometry it goes on, and this one is reached for
    after it in practice: the sign gets its material, then its glow.

    No Sollumz warning here, unlike the Surface and Geometry tools. Generating
    the halo and previewing it are plain Blender; only Export needs Sollumz, so
    that is the one row that says anything about it.
    """
    bl_label = "Sign Glow"
    bl_idname = "SETO_PT_sign_glow_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = pl.TAB
    bl_parent_id = groups.MATERIALS
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 1

    def draw_header(self, context):
        icons.draw_header(self.layout, "sign_glow", 'LIGHT_AREA')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_sign_glow

        col = pl.section(layout, "Generate", 'TEXTURE')
        col.prop(settings, "resolution")
        col.prop(settings, "color", text="")

        pl.create_button(layout, "seto.create_sign_glow", "Create Sign Glow",
                         'LIGHT_AREA')
        pl.hint(layout, "Select the lettering. Everything else is live after.")


class SETO_PT_sign_glow_object_panel(pl.SelectedPanel, bpy.types.Panel):
    """The selected glow's settings, all of them live.

    Ordered by what a user actually reaches for, in order: how big and bright
    the halo is, then where the plane sits, then the export row - which is the
    only thing here that has an opinion about Sollumz.
    """
    bl_label = "Selected Glow"
    bl_idname = "SETO_PT_sign_glow_object_panel"
    bl_parent_id = "SETO_PT_sign_glow_panel"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and obj.seto_sign_glow_data.is_sign_glow)

    def draw(self, context):
        layout = self.layout
        glow = context.active_object
        data = glow.seto_sign_glow_data

        pl.object_header(layout, glow, data)

        col = pl.section(layout, "Halo", 'LIGHT_AREA')
        col.prop(data, "color", text="")
        col.separator()
        col.prop(data, "core_size")
        col.prop(data, "core_intensity")
        col.separator()
        col.prop(data, "halo_size")
        col.prop(data, "halo_intensity")

        col = pl.section(layout, "Plane", 'MESH_PLANE')
        col.prop(data, "resolution")
        col.prop(data, "auto_fit")
        row = col.row()
        row.enabled = not data.auto_fit
        row.prop(data, "padding")
        col.prop(data, "offset_behind")
        col.prop(data, "edge_fade")

        # Only while the glow is still wearing the stand-in material. Once it
        # carries a Sollumz shader there is no emission node to turn up, and a
        # slider that does nothing is worse than one that is not there.
        if any(material is not None
               and material.name.endswith(object_settings.PREVIEW_MATERIAL_SUFFIX)
               for material in glow.data.materials):
            col = pl.section(layout, "Viewport", 'SHADING_RENDERED')
            col.prop(data, "preview_strength")

        manual_offset.draw(layout, data, "seto_sign_glow_data")

        if not data.live_update:
            pl.rebuild_button(layout, "seto.sign_glow_rebuild")

        col = pl.section(layout, "Shader", 'EXPORT')
        if not szi.is_sollumz_available():
            # Said here and nowhere else in this tool: everything above works
            # without Sollumz, and warning at the top of a panel whose buttons
            # all function would be telling the user their tool is broken when
            # it is not.
            col.label(text="Sollumz needed for the shader.", icon='INFO')
            col.operator("seto.sign_glow_save_dds", icon='IMAGE_DATA')
            return
        col.prop(data, "shader_name", text="")
        row = col.row(align=True)
        row.operator("seto.sign_glow_export", text="Rebuild Shader", icon='EXPORT')
        row.operator("seto.sign_glow_list_shaders", text="", icon='VIEWZOOM')
        col.operator("seto.sign_glow_save_dds", icon='IMAGE_DATA')


_classes = (SETO_PT_sign_glow_panel, SETO_PT_sign_glow_object_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
