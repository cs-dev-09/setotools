"""N-Panel.

Laid out so the section you use on every decal - library, category, texture,
thumbnail, CREATE - is the only thing open by default. Everything you set once
and leave alone (placement, randomization, material) lives in collapsed
sub-panels, which is what keeps the tab short.

Blender draws child panels after their parent's draw(), so the CREATE DECAL
button sits above the collapsed sections and stays reachable without scrolling.
"""

import bpy

from . import geometry
from . import library
from . import preferences
from . import previews
from ..shared import addon_prefs
from ..shared import groups
from ..shared import sollumz_integration as szi
from ..shared import ui_common

# Height of the texture thumbnail, in UI units.
PREVIEW_SCALE = 6.0


_sollumz_warning = ui_common.draw_sollumz_warning


class _DecalChildPanel:
    """Shared setup for the collapsed sub-panels under Decal Tool."""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_parent_id = "SETO_PT_decal_tool_panel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return szi.is_sollumz_available()


class SETO_PT_decal_tool_panel(bpy.types.Panel):
    bl_label = "Decal Tool"
    bl_idname = "SETO_PT_decal_tool_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # Second of the three Surface tools, between Fake AO (0) and Surface
    # Painter (2). Both of those shade a surface; this one puts an image on it.
    bl_category = "Seto Tools"
    bl_parent_id = groups.SURFACE
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 1

    def draw_header(self, context):
        self.layout.label(text="", icon='TEXTURE')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_decal

        if _sollumz_warning(layout):
            return

        prefs = preferences.get_preferences(context)
        row = layout.row(align=True)
        if prefs is not None:
            # The library folder is an add-on preference, not a scene setting,
            # so it is remembered across files and restarts - picked once.
            row.prop(prefs, "library_path", text="")
        else:
            row.label(text="Add-on preferences unavailable", icon='ERROR')
        row.operator("seto.refresh_decal_library", text="", icon='FILE_REFRESH')

        col = layout.column(align=True)
        col.prop(settings, "category", text="")
        texture_row = col.row(align=True)
        # With Random Texture on, the chosen texture is ignored, so the enum is
        # greyed out rather than hidden - the panel height stays stable.
        texture_row.enabled = not settings.random_texture
        texture_row.prop(settings, "texture", text="")

        if not library.get_categories():
            layout.label(text="Set a library folder and press Refresh.", icon='INFO')
        else:
            self._draw_preview(layout, settings)

        layout.operator("seto.create_decal", text="CREATE DECAL", icon='TEXTURE')

        if context.mode != 'EDIT_MESH':
            layout.label(text="Select faces in Edit Mode.", icon='INFO')

    def _draw_preview(self, layout, settings):
        """The texture that will actually be used, picked visually.

        A plain thumbnail of the current pick, sized by the add-on preference.
        """
        if settings.random_texture:
            layout.label(text="Random texture from this category.", icon='QUESTION')
            return

        path = library.texture_path(settings.category, settings.texture)
        icon_id = previews.get_icon_id(path)
        if icon_id:
            box = layout.box()
            box.template_icon(icon_value=icon_id, scale=addon_prefs.preview_size() / 2.0)


class SETO_PT_decal_placement_panel(_DecalChildPanel, bpy.types.Panel):
    bl_label = "Placement"
    bl_idname = "SETO_PT_decal_placement_panel"

    def draw(self, context):
        settings = context.scene.seto_decal
        self.layout.prop(settings, "merge_coplanar")
        col = self.layout.column(align=True)
        col.prop(settings, "width")
        col.prop(settings, "height")
        col.prop(settings, "edge_fade")
        col.prop(settings, "surface_offset")
        rotation_row = col.row(align=True)
        rotation_row.enabled = not settings.random_rotation
        rotation_row.prop(settings, "rotation")


class SETO_PT_decal_random_panel(_DecalChildPanel, bpy.types.Panel):
    bl_label = "Randomization"
    bl_idname = "SETO_PT_decal_random_panel"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_decal

        col = layout.column(align=True)
        col.prop(settings, "random_rotation")
        sub = col.column(align=True)
        sub.enabled = settings.random_rotation
        sub.prop(settings, "rotation_min")
        sub.prop(settings, "rotation_max")

        col = layout.column(align=True)
        col.prop(settings, "random_scale")
        sub = col.column(align=True)
        sub.enabled = settings.random_scale
        sub.prop(settings, "scale_min")
        sub.prop(settings, "scale_max")

        layout.prop(settings, "random_texture")
        layout.prop(settings, "random_position")


class SETO_PT_decal_material_panel(_DecalChildPanel, bpy.types.Panel):
    bl_label = "Material"
    bl_idname = "SETO_PT_decal_material_panel"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_decal

        row = layout.row()
        row.enabled = False
        row.label(text=f"Shader: {szi.DECAL_SHADER_FILENAME}")
        layout.prop(settings, "material_mode", text="")


class SETO_PT_decal_object_panel(bpy.types.Panel):
    """Settings of the selected decal, editable after the fact.

    Nested under the Decal Tool section rather than given its own tab, and only
    drawn when the active object is actually one of our decals.
    """
    bl_label = "Selected Decal"
    bl_idname = "SETO_PT_decal_object_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_parent_id = "SETO_PT_decal_tool_panel"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and obj.seto_decal_data.is_seto_decal)

    def draw_header(self, context):
        self.layout.label(text="", icon='MODIFIER')

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        data = obj.seto_decal_data

        row = layout.row()
        icon_id = previews.get_icon_id(data.texture_path)
        if icon_id:
            row.template_icon(icon_value=icon_id, scale=3.0)
        col = row.column(align=True)
        col.label(text=data.texture_stem or obj.name, icon='OUTLINER_OB_MESH')
        source_row = col.row()
        source_row.enabled = False
        source_row.prop(data, "source_object", text="")

        if data.status:
            warn = layout.box()
            warn.alert = True
            col = warn.column(align=True)
            col.label(text="Cannot update:", icon='ERROR')
            for line in ui_common.wrap(data.status, 38):
                col.label(text=line)

        layout.prop(data, "live_update")

        col = layout.column(align=True)
        col.prop(data, "width")
        col.prop(data, "height")
        col.prop(data, "edge_fade")
        col.prop(data, "surface_offset")
        col.prop(data, "rotation")

        col = layout.column(align=True)
        col.prop(data, "offset_u")
        col.prop(data, "offset_v")

        layout.separator()
        layout.label(text="Corner Alpha (Color 1)")
        # Laid out as the decal actually sits: top row above bottom row, so the
        # sliders map onto the corners you can see in the viewport rather than
        # onto an index you have to remember.
        grid = layout.grid_flow(row_major=True, columns=2, align=True)
        for index in (3, 2, 0, 1):      # top left, top right, bottom left, bottom right
            grid.prop(data, "corner_alpha", index=index, text="")
        row = layout.row(align=True)
        row.operator("seto.decal_alpha_uniform", text="All 1.0", icon='CHECKMARK')
        row.operator("seto.decal_alpha_fade_down", text="Fade Down", icon='SORT_ASC')

        layout.label(text="Border Alpha (edge ring)")
        col = layout.column(align=True)
        for index, side in enumerate(geometry.SIDE_NAMES):
            col.prop(data, "border_alpha", index=index, text=side)

        row = layout.row(align=True)
        row.operator("seto.decal_reset_position", text="Center", icon='PIVOT_BOUNDBOX')
        if not data.live_update:
            row.operator("seto.decal_rebuild", text="Update", icon='FILE_REFRESH')


_classes = (
    SETO_PT_decal_tool_panel,
    SETO_PT_decal_placement_panel,
    SETO_PT_decal_random_panel,
    SETO_PT_decal_material_panel,
    SETO_PT_decal_object_panel,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
