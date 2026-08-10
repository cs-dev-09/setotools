"""N-Panel.

The main section is the workflow and nothing else: which layer, which texture,
and the paint buttons. Everything you set once and stop thinking about - the
brush, the placement sliders, the paint mesh, the library folder - is a child
panel, the same split the Decal Tool uses.

That matters here more than elsewhere because this tool has the most controls
of the five: as one column it was long enough that Start Paint scrolled off the
bottom while you were choosing a texture.

Textures are picked from a name list with the selected one previewed
underneath. Blender only shows an image in a hover tooltip for the ID datablock
list, and that one cannot be filtered to a single category - it shows every
image in the file - so this is as close as filtered browsing gets.

Blender draws child panels after their parent's draw(), so the main column
stays reachable without scrolling.
"""

import bpy

from ..shared import addon_prefs
from ..shared import groups
from ..shared import icons
from ..shared import ui_common
from . import brush
from . import library
from . import previews
from . import shell

PREVIEW_SCALE = 6.0


def _active_layer(context):
    """(layers, the one being adjusted) for whatever is selected.

    Works from either object: select the wall or select the paint mesh and the
    panel shows the same thing. Falls back to the session's layer, then to the
    top of the stack, so there is always something to adjust once one exists.
    """
    obj = context.active_object
    if obj is None or obj.type != 'MESH':
        return [], None

    settings = context.scene.seto_surface
    wall, dirt_shell = shell.resolve(obj)
    layers = shell.find_shells(wall) if wall is not None else []
    if dirt_shell is None and layers:
        dirt_shell = (settings.paint_object
                      if settings.paint_object in layers else layers[-1])
    return layers, dirt_shell


class SETO_UL_surface_textures(bpy.types.UIList):
    """The texture browser: the category's textures, listed by name.

    Hovering a row shows its file path and size through item_dyntip_propname -
    tooltips can carry text, just not an image.
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


class _LayerChildPanel(_SurfaceChildPanel):
    """A child panel that only means something once a layer exists."""

    @classmethod
    def poll(cls, context):
        return _active_layer(context)[1] is not None


class SETO_PT_surface_painter_panel(bpy.types.Panel):
    bl_label = "Surface Painter"
    bl_idname = "SETO_PT_surface_painter_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # Last of the three Surface tools, under Ambient Occlusion (0) and Decal Tool (1).
    # The other two place what they make; this one is painted by hand.
    bl_category = "Seto Tools"
    bl_parent_id = groups.SURFACE
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 2

    def draw_header(self, context):
        icons.draw_header(self.layout, "surface_painter", 'BRUSH_DATA')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_surface
        obj = context.active_object

        if ui_common.draw_sollumz_warning(layout):
            return
        if obj is None or obj.type != 'MESH':
            layout.box().label(text="Select a mesh object.", icon='INFO')
            return

        layers, dirt_shell = _active_layer(context)
        if layers:
            self._draw_layers(layout, layers, dirt_shell)
            layout.separator()
        self._draw_library(layout, settings)
        layout.separator()
        self._draw_painting(context, layout, settings, dirt_shell)

    # ----------------------------------------------------------------- layers
    def _draw_layers(self, layout, layers, active_shell):
        """One row per painted texture, bottom of the stack first.

        Each texture is its own layer: painting concrete and then dirt gives two
        rows, each with its own strokes and its own opacity - picking a new
        texture and pressing Start Paint adds a row instead of retexturing one.
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
        # Greyed out while the only entry is "<no categories>": a dropdown you
        # can open onto a single placeholder looks like a control that does
        # nothing. Refresh stays live - it is the way out of this state, so it
        # gets its own sub-row rather than being disabled along with the enum.
        category = row.row(align=True)
        category.enabled = bool(library.get_categories())
        category.prop(settings, "category", text="")
        row.operator("seto.surface_refresh_library", text="", icon='FILE_REFRESH')

        if not library.has_textures():
            # No textures ship with the add-on, so this is the normal first
            # run, not a fault. Say what to do about it - "No textures found"
            # on its own reads as broken.
            box = layout.box()
            box.scale_y = 0.8
            col = box.column(align=True)
            col.label(text="No textures yet.", icon='INFO')
            col.label(text="Set your own folder under")
            col.label(text="Library Folder below.")
            return

        # Only ever holds the selected category, so picking Graffiti shows
        # graffiti and nothing else.
        # DEFAULT, not GRID: Blender 5.x dropped the GRID list type (the enum
        # is only DEFAULT/COMPACT now).
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
        # hover preview. Half the preference size: big enough to judge a pattern
        # by, small enough not to push the paint buttons off the panel.
        path = library.texture_path(settings.category, settings.texture)
        icon_id = previews.get_icon_id(path)
        if icon_id:
            box = layout.box()
            box.template_icon(icon_value=icon_id,
                              scale=addon_prefs.preview_size() / 2.0)
        texture_row = layout.row(align=True)
        texture_row.enabled = bool(library.get_textures(settings.category))
        texture_row.prop(settings, "texture", text="")

    # --------------------------------------------------------------- painting
    def _draw_painting(self, context, layout, settings, dirt_shell):
        painting = (dirt_shell is not None
                    and settings.paint_object == dirt_shell
                    and context.mode == 'PAINT_VERTEX')
        new_layer = (dirt_shell is not None
                     and shell.texture_stem_of(dirt_shell) != settings.texture)

        if not painting:
            if dirt_shell is None:
                box = layout.box()
                box.scale_y = 0.8
                box.label(text="Paints on a mesh of its own.", icon='INFO')
            layout.operator("seto.surface_start_paint",
                            text="Paint New Layer" if new_layer else "Start Paint",
                            icon='ADD' if new_layer else 'BRUSH_DATA')
        else:
            # Erase is a toggle rather than a button so the panel shows which
            # mode you are in mid-stroke.
            row = layout.row(align=True)
            row.scale_y = 1.2
            row.prop(settings, "erase", text="Paint", icon='BRUSH_DATA',
                     toggle=True, invert_checkbox=True)
            row.prop(settings, "erase", text="Erase", icon='X', toggle=True)
            if new_layer:
                layout.operator("seto.surface_start_paint",
                                text="Paint New Layer", icon='ADD')
            layout.operator("seto.surface_stop_paint",
                            text="Stop Paint", icon='CHECKMARK')

        layout.operator("seto.surface_clear_mask", text="Clear Dirt", icon='TRASH')

        if painting and brush.get_brush(context) is None:
            layout.label(text="Pick a brush in the toolbar.", icon='ERROR')


class SETO_PT_surface_brush_panel(_SurfaceChildPanel, bpy.types.Panel):
    bl_label = "Brush"
    bl_idname = "SETO_PT_surface_brush_panel"
    bl_order = 0

    def draw(self, context):
        settings = context.scene.seto_surface
        col = self.layout.column(align=True)
        col.prop(settings, "brush_size")
        col.prop(settings, "brush_strength")
        col.prop(settings, "falloff", text="")


class SETO_PT_surface_place_panel(_LayerChildPanel, bpy.types.Panel):
    """Where the dirt sits on the surface.

    Everything here writes the layer's real data - Color 1 alpha and UVMap 0 -
    so what it changes is what exports. All of it recomputes from a pristine
    copy, so dragging a slider back where it was gives back what you had.
    """

    bl_label = "Placement"
    bl_idname = "SETO_PT_surface_place_panel"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        dirt_shell = _active_layer(context)[1]
        # poll() already gates this, but a panel that raises stops the whole
        # region drawing, so it does not get to depend on being called in the
        # order it expects.
        if dirt_shell is None:
            return
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
        sub.prop(context.scene.seto_surface, "ghost_strength", text="")

        layout.operator("seto.surface_move_dirt",
                        text="Place On Surface", icon='VIEW_PAN')

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


class SETO_PT_surface_normal_panel(_LayerChildPanel, bpy.types.Panel):
    bl_label = "Normal Map"
    bl_idname = "SETO_PT_surface_normal_panel"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        dirt_shell = _active_layer(context)[1]
        if dirt_shell is None:
            return
        materials = dirt_shell.data.materials
        node = shell.bump_node(materials[0]) if materials else None

        if node is None:
            layout.operator("seto.surface_toggle_normal",
                            text="Add Normal Map", icon='ADD')
        else:
            layout.template_ID(node, "image", open="image.open")
            layout.operator("seto.surface_toggle_normal",
                            text="Remove Normal Map", icon='X')


class SETO_PT_surface_shell_panel(_SurfaceChildPanel, bpy.types.Panel):
    bl_label = "Paint Mesh"
    bl_idname = "SETO_PT_surface_shell_panel"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 3

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_surface

        col = layout.column(align=True)
        col.prop(settings, "shell_spacing")
        col.prop(settings, "shell_offset")

        layers = _active_layer(context)[0]
        if not layers:
            return

        col = layout.column(align=True)
        col.scale_y = 0.8
        for entry in layers:
            col.label(text=f"{shell.texture_stem_of(entry)}: "
                           f"{len(entry.data.vertices)} vertices",
                      icon='VERTEXSEL')

        layout.prop(settings, "optimize_detail")
        layout.operator("seto.surface_optimize_layer",
                        text="Optimize", icon='MOD_DECIM')
        layout.operator("seto.surface_remove_shell",
                        text="Remove Selected Layer", icon='X')


class SETO_PT_surface_library_panel(_SurfaceChildPanel, bpy.types.Panel):
    bl_label = "Library Folder"
    bl_idname = "SETO_PT_surface_library_panel"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 4

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_surface

        layout.prop(settings, "custom_library_path", text="")
        layout.prop(settings, "browser_rows")
        row = layout.row()
        row.scale_y = 0.8
        row.label(text="Bundled library" if library.is_using_bundled()
                  else "Custom library", icon='FILE_FOLDER')


_classes = (
    SETO_UL_surface_textures,
    SETO_PT_surface_painter_panel,
    SETO_PT_surface_brush_panel,
    SETO_PT_surface_place_panel,
    SETO_PT_surface_normal_panel,
    SETO_PT_surface_shell_panel,
    SETO_PT_surface_library_panel,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
