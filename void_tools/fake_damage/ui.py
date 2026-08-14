import bpy

from ..shared import groups, icons, manual_offset, panel_layout as pl, ui_common
from ..shared import sollumz_integration as szi
from ..shared import strip_settings
from ..fake_ao.ui import _draw_bevel


def _draw_strength_values(layout, strength):
    """The two shader values Strength is setting, spelled out under it.

    Shown rather than hidden behind the slider on purpose. These are the numbers
    that go into a bug report, the ones to compare against a vanilla material in
    the Properties editor, and the ones a default gets moved to once a value has
    been dialled in in game - none of which a bare 0..6 slider can tell anyone.
    """
    col = layout.column(align=True)
    col.scale_y = 0.8
    col.enabled = False
    for name, value in szi.damage_strength_parameters(strength).items():
        col.label(text=f"{name}   {value:.3f}")


def _shared_material_count(obj):
    """How many meshes wear this strip's Edge Wear material.

    `users` counts a fake user like every other ID does, and Sollumz imports
    leave plenty of those about - counting it would report a strip that owns its
    material outright as sharing it with something invisible.
    """
    for material in obj.data.materials:
        if szi.is_damage_material(material):
            return material.users - (1 if material.use_fake_user else 0)
    return 0


class SETO_PT_fake_damage_panel(bpy.types.Panel):
    bl_label = "Edge Wear"
    bl_idname = "SETO_PT_fake_damage_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # First of the two Geometry tools, above Smooth Edge (1). Both build mesh
    # along the selected edges; this is the one that breaks the edge up.
    bl_category = pl.TAB
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

        # Nothing to set before Create. UV Scale and UV Offset are live on the
        # finished strip, and listing them here as well only invited dragging
        # the copy that does nothing - see strip_settings.draw().
        pl.create_button(layout, "seto.create_fake_damage", "Create Edge Wear",
                         'MOD_EDGESPLIT')
        pl.edit_mode_hint(layout, context)


class _EdgeWearChildPanel(pl.ToolChildPanel):
    """The collapsed sub-panels under Edge Wear.

    Everything but the parent id comes from the shared base, so this tool's
    children sit, collapse and hide themselves exactly like every other tool's -
    see shared/panel_layout.py.
    """
    bl_parent_id = "SETO_PT_fake_damage_panel"


class SETO_PT_fake_damage_material_panel(_EdgeWearChildPanel, bpy.types.Panel):
    """How loud the decal is, for the next strip.

    Strength had no home in the tab at all before this: changing it meant
    finding bumpiness and specularIntensityMult in the Properties editor, and
    "the damage is invisible in game" was the result - the value that decides
    that was three clicks outside the tool that made the strip.

    Deliberately not the material *choice*: Reuse/Create is shared with Smooth
    Edge and drawn once by the Geometry section. Strength is not shared - Smooth
    Edge is a different effect with its own tuned values.
    """
    bl_label = "Material"
    bl_idname = "SETO_PT_fake_damage_material_panel"
    bl_order = pl.MATERIAL_CHILD

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_fake_damage

        row = layout.row()
        row.enabled = False
        row.label(text=f"Shader: {szi.DAMAGE_SHADER_FILENAME}")

        layout.prop(settings, "strength")
        _draw_strength_values(layout, settings.strength)
        # Reuse is the default and a reused material keeps its own values, so
        # this only reaches a material Create has to make. On the strip itself
        # Strength is live either way, which is where it should be dialled in.
        if strip_settings.get(context).material_mode == 'AUTO':
            pl.hint(layout, "Reuse keeps the existing material's Strength.")


class SETO_PT_fake_damage_object_panel(pl.SelectedPanel, bpy.types.Panel):
    """Settings of the selected Edge Wear strip, editable after the fact.

    Nested under the Edge Wear section rather than given its own tab, and
    only drawn when the active object is actually one of our strips. Every row
    here is live: changing it rebuilds the strip in place.
    """
    bl_label = "Selected Strip"
    bl_idname = "SETO_PT_fake_damage_object_panel"
    bl_parent_id = "SETO_PT_fake_damage_panel"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and obj.seto_fake_damage_data.is_fake_damage)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        data = obj.seto_fake_damage_data

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

        col = pl.section(layout, "Texture Placement", 'UV')
        col.prop(data, "uv_scale")
        col.prop(data, "uv_offset")

        # Live like every other row here, but through the material rather than a
        # rebuild - which is also why the strip has to say when that material is
        # not its own: dragging this changes every strip wearing it.
        col = pl.section(layout, "Material", 'MATERIAL')
        col.prop(data, "strength")
        _draw_strength_values(col, data.strength)
        shared = _shared_material_count(obj)
        if shared > 1:
            col.label(text=f"Shared by {shared} strips", icon='INFO')

        manual_offset.draw(layout, data, "seto_fake_damage_data")

        layout.separator()
        if data.edge_keys:
            _draw_bevel(layout, data, tool_label="Edge Wear")
        else:
            box = layout.box()
            box.scale_y = 0.8
            box.label(text="Bevel needs a selected edge.", icon='INFO')

        if not data.live_update:
            pl.rebuild_button(layout, "seto.fake_damage_rebuild")


_classes = (SETO_PT_fake_damage_panel,
            SETO_PT_fake_damage_material_panel,
            SETO_PT_fake_damage_object_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
