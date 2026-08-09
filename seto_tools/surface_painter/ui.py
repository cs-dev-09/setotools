"""N-Panel.

One workflow, one column: pick a dirt texture, press START PAINT, paint on the
spawned paint mesh, then adjust the whole dirt layer with the sliders. The wall
itself is never modified, and the panel says so.

The texture is picked through template_icon_view - the big thumbnail grid - so
what is being chosen is visible before it is chosen. Blender cannot put an
image in a tooltip, so the grid (plus a thumbnail on every dropdown row) is as
close as hovering gets. The same grid is used by the Decal Tool.

Blender draws child panels after their parent's draw(), so the main column
stays reachable without scrolling.
"""

import bpy

from ..shared import addon_prefs
from . import brush
from . import library
from . import previews
from . import shell

PREVIEW_SCALE = 6.0
# Size of each entry in the picker popup - big enough to actually judge a
# grunge pattern by, not just recognise it.
PREVIEW_POPUP_SCALE = 9.0


class SETO_UL_surface_textures(bpy.types.UIList):
    """The texture browser: the category's textures, listed by name.

    Names only, with the preview of the selected one drawn underneath at full
    size. Blender shows an image in a hover tooltip for exactly one widget -
    the ID datablock list - and that one cannot be filtered to a single
    category, so a name list plus a big preview is the closest thing that still
    only ever shows the folder you picked.

    Hovering a row does show its file path and size, through
    item_dyntip_propname: tooltips can carry text, just not an image.
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


class _SurfaceChildPanel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_parent_id = "SETO_PT_surface_painter_panel"
    bl_options = {'DEFAULT_CLOSED'}


class SETO_PT_surface_painter_panel(bpy.types.Panel):
    bl_label = "Surface Painter"
    bl_idname = "SETO_PT_surface_painter_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # Shared with the other Seto tools: every panel using this category is
    # merged by Blender into one "Seto Tools" tab. bl_order 5 puts this section
    # below Fake AO (0), Fake Damage (1), Decal Tool (2) and Smooth Edge (4).
    bl_category = "Seto Tools"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 5

    def draw_header(self, context):
        self.layout.label(text="", icon='BRUSH_DATA')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_surface
        obj = context.active_object

        if obj is None or obj.type != 'MESH':
            layout.box().label(text="Select a mesh object.", icon='INFO')
            return

        wall, dirt_shell = shell.resolve(obj)
        layers = shell.find_shells(wall) if wall is not None else []
        # The layer being adjusted: the one selected, else the session's, else
        # the top of the stack.
        if dirt_shell is None and layers:
            dirt_shell = settings.paint_object                 if settings.paint_object in layers else layers[-1]

        if layers:
            self._draw_layers(layout, settings, layers, dirt_shell)
            layout.separator()
        self._draw_library(layout, settings)
        self._draw_normal_map(layout, dirt_shell)
        layout.separator()
        self._draw_brush(layout, settings)
        layout.separator()
        self._draw_painting(layout, settings, dirt_shell)
        if dirt_shell is not None:
            layout.separator()
            self._draw_adjust(layout, dirt_shell)

    # ----------------------------------------------------------------- layers
    def _draw_layers(self, layout, settings, layers, active_shell):
        """One row per painted texture, bottom of the stack first.

        Each texture is its own layer: painting concrete and then dirt gives
        two rows, each with its own strokes and its own opacity - picking a new
        texture in the dropdown and pressing START PAINT adds a row instead of
        retexturing an old one.
        """
        layout.label(text="Layers")
        col = layout.column(align=True)
        for entry in layers:
            row = col.row(align=True)
            op = row.operator(
                "seto.surface_paint_layer",
                text=shell.texture_stem_of(entry) or entry.name,
                icon='LAYER_ACTIVE' if entry == active_shell else 'LAYER_USED',
                depress=entry == active_shell,
            )
            op.shell_name = entry.name
            sub = row.row(align=True)
            sub.scale_x = 0.5
            sub.prop(entry.seto_surface_data, "dirt_opacity", text="")

    # ---------------------------------------------------------------- library
    def _draw_library(self, layout, settings):
        layout.label(text="Dirt Texture")
        row = layout.row(align=True)
        row.prop(settings, "category", text="")
        row.operator("seto.surface_refresh_library", text="", icon='FILE_REFRESH')

        if not library.has_textures():
            box = layout.box()
            box.scale_y = 0.8
            box.label(text="No textures found.", icon='ERROR')
            return

        # The browser grid. Only ever holds the selected category, so picking
        # Graffiti shows graffiti and nothing else - unlike Blender's image
        # datablock list, which shows every image in the file and cannot be
        # filtered.
        # DEFAULT, not GRID: Blender 5.x dropped the GRID list type (the enum
        # is only DEFAULT/COMPACT now).
        size = addon_prefs.preview_size()
        if settings.browser_items:
            layout.template_list(
                "SETO_UL_surface_textures", "",
                settings, "browser_items",
                settings, "browser_index",
                rows=settings.browser_rows,
                maxrows=settings.browser_rows,
                item_dyntip_propname="tooltip",
            )
        else:
            box = layout.box()
            box.scale_y = 0.8
            box.label(text="Press Refresh to fill the browser.", icon='INFO')

        # The selected texture, drawn under the list - this is what replaces a
        # hover preview. Half the preference size: big enough to judge a
        # pattern by, small enough not to push the brush and paint buttons off
        # the panel. Turn Texture Preview Size up if you want it larger.
        path = library.texture_path(settings.category, settings.texture)
        icon_id = previews.get_icon_id(path)
        if icon_id:
            box = layout.box()
            box.template_icon(icon_value=icon_id, scale=size / 2.0)
        layout.prop(settings, "texture", text="")

    # ------------------------------------------------------------- normal map
    def _draw_normal_map(self, layout, dirt_shell):
        if dirt_shell is None:
            return
        layout.label(text="Normal Map")
        material = dirt_shell.data.materials[0] if dirt_shell.data.materials else None
        node = shell.bump_node(material) if material is not None else None
        if node is None:
            layout.operator("seto.surface_toggle_normal",
                            text="Add Normal Map", icon='ADD')
        else:
            layout.template_ID(node, "image", open="image.open")
            layout.operator("seto.surface_toggle_normal",
                            text="Remove Normal Map", icon='X')

    # ------------------------------------------------------------------ brush
    def _draw_brush(self, layout, settings):
        layout.label(text="Brush")
        col = layout.column(align=True)
        col.prop(settings, "brush_size")
        col.prop(settings, "brush_strength")
        col.prop(settings, "falloff", text="")

    # --------------------------------------------------------------- painting
    def _draw_painting(self, layout, settings, dirt_shell):
        layout.label(text="Painting")
        painting = (dirt_shell is not None and settings.paint_object == dirt_shell
                    and bpy.context.mode == 'PAINT_VERTEX')

        settings_texture = settings.texture
        new_layer = (dirt_shell is not None
                     and shell.texture_stem_of(dirt_shell) != settings_texture)
        if not painting:
            if dirt_shell is None:
                col = layout.column(align=True)
                col.scale_y = 0.8
                col.label(text="START PAINT spawns a paint mesh", icon='INFO')
                col.label(text="over this surface - the surface")
                col.label(text="itself is never touched.")
            layout.operator("seto.surface_start_paint",
                            text="PAINT NEW LAYER" if new_layer else "START PAINT",
                            icon='ADD' if new_layer else 'BRUSH_DATA')
        else:
            # Erase is a toggle rather than a button so the panel shows which
            # mode you are in mid-stroke.
            row = layout.row(align=True)
            row.scale_y = 1.2
            row.prop(settings, "erase", text="PAINT", icon='BRUSH_DATA',
                     toggle=True, invert_checkbox=True)
            row.prop(settings, "erase", text="ERASE", icon='X', toggle=True)
            if new_layer:
                layout.operator("seto.surface_start_paint",
                                text="PAINT NEW LAYER", icon='ADD')
            layout.operator("seto.surface_stop_paint",
                            text="STOP PAINT", icon='CHECKMARK')

        row = layout.row(align=True)
        row.operator("seto.surface_clear_mask", text="CLEAR DIRT", icon='TRASH')

        if painting and brush.get_brush(bpy.context) is None:
            layout.label(text="Pick a brush in the toolbar.", icon='ERROR')

    # ----------------------------------------------------------------- adjust
    def _draw_adjust(self, layout, dirt_shell):
        """The after-painting controls, drawn for the shell whichever of the
        two objects is selected. They write the shell's real data - Color 1
        alpha and UVMap 0 - so what they change is what exports."""
        layout.label(text="Dirt Adjust")
        data = dirt_shell.seto_surface_data

        # Substance-style projection: ghost the whole texture while placing it.
        ghosted = shell.has_ghost(dirt_shell)
        row = layout.row(align=True)
        row.operator("seto.surface_toggle_ghost",
                     text="Preview On" if not ghosted else "Preview Off",
                     icon='HIDE_OFF' if not ghosted else 'HIDE_ON',
                     depress=ghosted)
        sub = row.row(align=True)
        sub.enabled = ghosted
        sub.prop(bpy.context.scene.seto_surface, "ghost_strength", text="")

        layout.operator("seto.surface_move_dirt",
                        text="Place On Surface", icon='VIEW_PAN')
        sub = layout.column(align=True)
        sub.scale_y = 0.8
        sub.label(text="Move onto the wall, click to keep.")
        if not data.dirt_repeat:
            sub.label(text="Repeat is off, so it fades out")
            sub.label(text="past the edge of its patch.")

        col = layout.column(align=True)
        col.prop(data, "dirt_opacity")
        col.prop(data, "dirt_repeat")
        row = col.row(align=True)
        row.prop(data, "dirt_width", text="Width")
        row.prop(data, "dirt_height", text="Height")
        row = col.row(align=True)
        row.prop(data, "dirt_offset_u", text="Offset X")
        row.prop(data, "dirt_offset_v", text="Y")
        col.prop(data, "dirt_rotation")


class SETO_PT_surface_shell_panel(_SurfaceChildPanel, bpy.types.Panel):
    bl_label = "Paint Mesh"
    bl_idname = "SETO_PT_surface_shell_panel"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_surface
        obj = context.active_object

        col = layout.column(align=True)
        col.prop(settings, "shell_spacing")
        col.prop(settings, "shell_offset")
        sub = layout.column(align=True)
        sub.scale_y = 0.8
        sub.label(text="Used when START PAINT spawns")
        sub.label(text="a new paint mesh. Spacing =")
        sub.label(text="distance between paint vertices;")
        sub.label(text="smaller is finer but heavier.")

        if obj is not None and obj.type == 'MESH':
            wall, _ = shell.resolve(obj)
            layers = shell.find_shells(wall) if wall is not None else []
            if layers:
                col = layout.column(align=True)
                col.scale_y = 0.8
                for entry in layers:
                    col.label(text=f"{shell.texture_stem_of(entry)}: "
                                   f"{len(entry.data.vertices)} vertices",
                              icon='VERTEXSEL')
                col = layout.column(align=True)
                col.prop(settings, "optimize_detail")
                layout.operator("seto.surface_optimize_layer",
                                text="Optimize", icon='MOD_DECIM')
                sub = layout.column(align=True)
                sub.scale_y = 0.8
                sub.label(text="Drops every vertex the strokes")
                sub.label(text="do not need. The texture is")
                sub.label(text="never touched.")
                layout.operator("seto.surface_remove_shell",
                                text="Remove Selected Layer", icon='X')


class SETO_PT_surface_library_panel(_SurfaceChildPanel, bpy.types.Panel):
    bl_label = "Library Folder"
    bl_idname = "SETO_PT_surface_library_panel"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_surface

        layout.prop(settings, "custom_library_path", text="")
        layout.prop(settings, "browser_rows")
        row = layout.row()
        row.scale_y = 0.8
        row.label(text="Bundled library" if library.is_using_bundled() else "Custom library",
                  icon='FILE_FOLDER')
        layout.operator("seto.surface_refresh_library", text="Refresh", icon='FILE_REFRESH')


_classes = (
    SETO_UL_surface_textures,
    SETO_PT_surface_painter_panel,
    SETO_PT_surface_shell_panel,
    SETO_PT_surface_library_panel,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
