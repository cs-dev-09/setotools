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
from ..shared import icons
from ..shared import panel_layout as pl
from ..shared import sollumz_integration as szi
from ..shared import ui_common

# Height of the texture thumbnail, in UI units.
PREVIEW_SCALE = 6.0


_sollumz_warning = ui_common.draw_sollumz_warning


class SETO_UL_decal_textures(bpy.types.UIList):
    """The texture browser: the category's decals, listed by name.

    Hovering a row shows its path through item_dyntip_propname - a tooltip can
    carry text, just not an image, which is why the pick is previewed
    underneath the list instead.
    """

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):
        if self.layout_type == 'COMPACT':
            layout.label(text=item.name)
            return

        row = layout.row(align=True)
        row.label(text=item.name,
                  icon='FILE_IMAGE' if previews.get_icon_id(item.path)
                  else 'ERROR')


class _DecalChildPanel(pl.ToolChildPanel):
    """The collapsed sub-panels under Decal Tool.

    Everything but the parent id comes from the shared base, so this tool's
    children sit, collapse and hide themselves exactly like every other tool's
    - see shared/panel_layout.py.
    """
    bl_parent_id = "SETO_PT_decal_tool_panel"


class SETO_PT_decal_tool_panel(bpy.types.Panel):
    bl_label = "Decal Tool"
    bl_idname = "SETO_PT_decal_tool_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # Second of the three Surface tools, between Ambient Occlusion (0) and Surface
    # Painter (2). Both of those shade a surface; this one puts an image on it.
    bl_category = pl.TAB
    bl_parent_id = groups.SURFACE
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 1

    def draw_header(self, context):
        icons.draw_header(self.layout, "decal_tool", 'TEXTURE')

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

        # A dropdown whose only entry is "<no categories>" still opens, and
        # picking the placeholder out of a list of one reads as though it did
        # something. Both enums are greyed out until there is a real choice
        # behind them - the placeholder stays visible, because it says what to
        # do about it, but it is no longer a control.
        category_row = layout.row(align=True)
        category_row.enabled = bool(library.get_categories())
        category_row.prop(settings, "category", text="")

        if not library.get_categories():
            layout.label(text="Set a library folder and press Refresh.", icon='INFO')
        else:
            # The browser, then the pick underneath it - the same two-part
            # picker Surface Painter uses. A dropdown can only preview the row
            # the pointer happens to be over, and choosing a decal is choosing
            # a picture.
            browser = layout.column(align=True)
            browser.enabled = not settings.random_texture
            if settings.browser_items:
                browser.template_list(
                    "SETO_UL_decal_textures", "",
                    settings, "browser_items",
                    settings, "browser_index",
                    rows=settings.browser_rows,
                    maxrows=settings.browser_rows,
                    item_dyntip_propname="tooltip",
                )
            else:
                box = browser.box()
                box.scale_y = 0.8
                box.label(text="Press Refresh to fill the browser.", icon='INFO')

            self._draw_preview(layout, settings)

            texture_row = layout.row(align=True)
            # With Random Texture on the chosen texture is ignored, so the enum
            # is greyed out rather than hidden - the panel height stays stable.
            texture_row.enabled = (bool(library.get_textures(settings.category))
                                   and not settings.random_texture)
            texture_row.prop(settings, "texture", text="")

        pl.create_button(layout, "seto.create_decal", "Create Decal", 'TEXTURE')

        if context.mode != 'EDIT_MESH':
            pl.hint(layout, "Select faces in Edit Mode.")

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
    bl_order = pl.FIRST_CHILD

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
    bl_order = pl.FIRST_CHILD + 1

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
    bl_order = pl.MATERIAL_CHILD

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_decal

        row = layout.row()
        row.enabled = False
        row.label(text=f"Shader: {szi.DECAL_SHADER_FILENAME}")
        layout.prop(settings, "material_mode", text="")

        col = pl.section(layout, "Vertex Colour", 'COLOR')
        col.prop(settings, "color_preset", text="")
        row = col.row()
        row.enabled = settings.color_preset == 'CUSTOM'
        row.prop(settings, "color_rgb", text="")

        # How tall the texture browser is. It lives here rather than beside the
        # list itself: it is set once to taste, and a row of its own above the
        # list would push the decal you are choosing further down the panel.
        layout.separator()
        layout.prop(settings, "browser_rows")


class SETO_PT_decal_object_panel(pl.SelectedPanel, bpy.types.Panel):
    """Settings of the selected decal, editable after the fact.

    Nested under the Decal Tool section rather than given its own tab, and only
    drawn when the active object is actually one of our decals.
    """
    bl_label = "Selected Decal"
    bl_idname = "SETO_PT_decal_object_panel"
    bl_parent_id = "SETO_PT_decal_tool_panel"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and obj.seto_decal_data.is_seto_decal)

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

        col = pl.section(layout, "Placement", 'MOD_SOLIDIFY')
        col.prop(data, "width")
        col.prop(data, "height")
        col.prop(data, "edge_fade")
        col.prop(data, "surface_offset")
        col.prop(data, "rotation")
        col.separator()
        col.prop(data, "offset_u")
        col.prop(data, "offset_v")

        col = pl.section(layout, "Vertex Colour", 'COLOR')
        col.prop(data, "color_preset", text="")
        row = col.row()
        row.enabled = data.color_preset == 'CUSTOM'
        row.prop(data, "color_rgb", text="")

        col = pl.section(layout, "Corner Alpha (Color 1)", 'IMAGE_ALPHA')
        # Laid out as the decal actually sits: top row above bottom row, so the
        # sliders map onto the corners you can see in the viewport rather than
        # onto an index you have to remember.
        grid = col.grid_flow(row_major=True, columns=2, align=True)
        for index in (3, 2, 0, 1):      # top left, top right, bottom left, bottom right
            grid.prop(data, "corner_alpha", index=index, text="")
        row = col.row(align=True)
        row.operator("seto.decal_alpha_uniform", text="All 1.0", icon='CHECKMARK')
        row.operator("seto.decal_alpha_fade_down", text="Fade Down", icon='SORT_ASC')

        col = pl.section(layout, "Border Alpha (edge ring)", 'IMAGE_ALPHA')
        for index, side in enumerate(geometry.SIDE_NAMES):
            col.prop(data, "border_alpha", index=index, text=side)

        row = layout.row(align=True)
        row.operator("seto.decal_reset_position", text="Center", icon='PIVOT_BOUNDBOX')
        if not data.live_update:
            row.operator("seto.decal_rebuild", text="Update", icon='FILE_REFRESH')


_classes = (
    # The UIList first: the panel's template_list names it by string, and a
    # name Blender does not know yet simply draws nothing.
    SETO_UL_decal_textures,
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
