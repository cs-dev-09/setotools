"""N-Panel for the Lighting tool.

Lighting is a container section rather than a tool of its own: each sub-tool is
a collapsible child panel under it, the way Sollumz Tools lays out its own tabs.

    Lighting
      └── God Ray Setup    (the light + shaft + dust automation)
           ├── Selected God Ray      shown only with a setup selected
           └── Advanced GTA Settings raw Sollumz properties

Master controls live in the God Ray Setup panel, the raw GTA properties in
collapsed sub-panels, so the section you use on every god ray is the only thing
open by default.
"""

import textwrap

import bpy

from . import group
from . import properties
from ..shared import sollumz_integration as szi


def _wrap(text, width):
    return textwrap.wrap(text, width) or [""]


def _sollumz_warning(layout):
    """Draws the "Sollumz not available" box. Returns True if it did."""
    available, status_msg = szi.get_status_message()
    if available:
        return False
    box = layout.box()
    box.label(text="Sollumz not available:", icon='ERROR')
    col = box.column(align=True)
    for line in _wrap(status_msg, 40):
        col.label(text=line)
    return True


class _LightingChildPanel:
    """Shared setup for the sub-tool panels under Lighting."""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_parent_id = "SETO_PT_lighting_panel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return szi.is_sollumz_available()


class _GodRayChildPanel:
    """Shared setup for the panels nested under God Ray Setup."""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_parent_id = "SETO_PT_godray_panel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (szi.is_sollumz_available()
                and obj is not None
                and group.find_group_root(obj) is not None)


class SETO_PT_lighting_panel(bpy.types.Panel):
    bl_label = "Lighting"
    bl_idname = "SETO_PT_lighting_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # Same category as the other tools, so Blender merges them into one
    # "Seto Tools" N-panel tab. bl_order 3 puts this section below Fake AO (0),
    # Fake Damage (1) and Decal Tool (2).
    bl_category = "Seto Tools"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 3

    def draw_header(self, context):
        self.layout.label(text="", icon='LIGHT_SPOT')

    def draw(self, context):
        # Only the Sollumz status lives here; everything else is a child panel,
        # so the section stays a short list of sub-tools.
        _sollumz_warning(self.layout)


class SETO_PT_godray_panel(_LightingChildPanel, bpy.types.Panel):
    bl_label = "God Ray Setup"
    bl_idname = "SETO_PT_godray_panel"
    bl_order = 0

    def draw_header(self, context):
        self.layout.label(text="", icon='OUTLINER_OB_LIGHT')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_lighting

        row = layout.row(align=True)
        row.prop(context.scene, "seto_lighting_preset", text="")
        # The preset the dropdown shows is passed explicitly, so the button
        # applies what the user is looking at rather than whatever the operator
        # last remembered.
        op = row.operator("seto.godray_apply_preset", text="", icon='CHECKMARK')
        op.preset = context.scene.seto_lighting_preset

        layout.separator()
        col = layout.column(align=True)
        col.prop(settings, "beam_color")
        col.prop(settings, "master_intensity")

        layout.separator()
        col = layout.column(align=True)
        col.prop(settings, "beam_length")
        col.prop(settings, "beam_width")
        col.prop(settings, "volumetric_strength")
        col.prop(settings, "fade_distance")

        layout.separator()
        layout.prop(settings, "add_dust")
        col = layout.column(align=True)
        col.enabled = settings.add_dust
        col.prop(settings, "dust_fx_name", text="FX")
        col.prop(settings, "dust_amount")

        layout.separator()
        layout.operator("seto.create_god_rays", text="Create God Rays", icon='LIGHT_SPOT')
        # Multi Ray lives in the F9 "Adjust Last Operation" panel along with
        # Flip Direction, rather than up here: it is a per-run choice about the
        # selection, not a setting you carry between god rays.
        hint = layout.row()
        hint.enabled = False
        hint.label(text="F9 for One Per Gap / Flip Direction")

        if context.mode != 'EDIT_MESH':
            layout.label(text="Select the opening's faces in Edit Mode.", icon='INFO')


class SETO_PT_godray_selected_panel(_GodRayChildPanel, bpy.types.Panel):
    """Master controls and actions for the god ray that is currently selected."""

    bl_label = "Selected God Ray"
    bl_idname = "SETO_PT_godray_selected_panel"
    bl_options = set()  # open by default: this is the panel you work in
    bl_order = 0

    def draw_header(self, context):
        self.layout.label(text="", icon='LIGHT_AREA')

    def draw(self, context):
        layout = self.layout
        root = group.find_group_root(context.active_object)
        data = root.seto_godray
        refs = group.resolve(root)

        box = layout.box()
        row = box.row()
        row.label(text=root.name, icon='OUTLINER_OB_EMPTY')
        parts = []
        if refs.has_light:
            parts.append("light")
        if refs.has_shaft:
            parts.append("shaft")
        if refs.has_dust:
            parts.append("dust")
        row.label(text=" + ".join(parts) if parts else "empty")
        info = box.row()
        info.enabled = False
        info.label(text=f"{data.archetype_name or '?'} ({data.ytyp_name or '?'})",
                   icon='FILE_3D')

        if refs.missing:
            warn = layout.box()
            warn.alert = True
            col = warn.column(align=True)
            col.label(text="Missing from this setup:", icon='ERROR')
            for item in refs.missing:
                col.label(text=f"- {item}")

        layout.prop(data, "auto_sync")

        col = layout.column(align=True)
        col.prop(data, "beam_color")
        col.prop(data, "master_intensity")
        col.prop(data, "beam_length")
        col.prop(data, "beam_width")
        col.prop(data, "volumetric_strength")
        col.prop(data, "fade_distance")

        col = layout.column(align=True)
        col.enabled = refs.has_dust
        col.prop(data, "dust_fx_name", text="FX")
        col.prop(data, "dust_amount")

        if not data.auto_sync:
            layout.operator("seto.godray_push_masters", icon='FILE_REFRESH')

        layout.separator()
        col = layout.column(align=True)
        col.operator("seto.godray_aim_at_selected", icon='TRACKER')
        col.operator("seto.godray_sync_shaft", icon='CON_TRACKTO')
        row = layout.row(align=True)
        row.operator("seto.godray_duplicate", icon='DUPLICATE')
        row.operator("seto.godray_delete", icon='TRASH')


class SETO_PT_godray_advanced_panel(_GodRayChildPanel, bpy.types.Panel):
    """Raw Sollumz/GTA properties of the selected setup.

    Every widget here is bound straight to Sollumz's own PropertyGroups, so
    nothing shown is a Seto copy that could drift from what gets exported.
    """

    bl_label = "Advanced GTA Settings"
    bl_idname = "SETO_PT_godray_advanced_panel"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        root = group.find_group_root(context.active_object)
        refs = group.resolve(root)

        if root.seto_godray.auto_sync:
            note = layout.box()
            note.label(text="Auto Sync is on - master controls will", icon='INFO')
            note.label(text="overwrite the values they own.")

        if refs.has_light:
            light_props = refs.light.data.light_properties

            box = layout.box()
            box.label(text="Spot Light", icon='LIGHT_SPOT')
            box.prop(refs.light.data, "color")
            for name in ("intensity", "falloff", "falloff_exponent", "shadow_near_clip",
                         "cone_outer_angle", "cone_inner_angle"):
                if szi.has_light_property(refs.light.data, name):
                    box.prop(light_props, name)

            box = layout.box()
            box.label(text="Misc")
            for name in ("light_hash", "projected_texture_hash", "flashiness"):
                if szi.has_light_property(refs.light.data, name):
                    box.prop(light_props, name)

            box = layout.box()
            box.label(text="Volume")
            for name in ("volume_intensity", "volume_size_scale", "volume_outer_color",
                         "volume_outer_intensity", "volume_outer_exponent"):
                if szi.has_light_property(refs.light.data, name):
                    box.prop(light_props, name)

            box = layout.box()
            box.label(text="Distance")
            for name in ("light_fade_distance", "shadow_fade_distance",
                         "specular_fade_distance", "volumetric_fade_distance"):
                if szi.has_light_property(refs.light.data, name):
                    box.prop(light_props, name)

            box = layout.box()
            box.label(text="Advanced")
            if szi.has_light_property(refs.light.data, "shadow_blur"):
                box.prop(light_props, "shadow_blur")

        if refs.has_shaft:
            box = layout.box()
            box.label(text="Light Shaft", icon='OUTLINER_DATA_LIGHTPROBE')
            # Sollumz draws its own extension UI, including the flag checkboxes
            # and the corner operators. Reusing it means the god ray panel can
            # never fall out of step with the properties Sollumz exports.
            refs.shaft_props.draw_props(box)

        if refs.has_dust:
            box = layout.box()
            box.label(text="Dust Particle", icon='PARTICLES')
            refs.dust_props.draw_props(box)


class SETO_PT_godray_flags_panel(_GodRayChildPanel, bpy.types.Panel):
    """The GTA light flags of the selected setup's spot light.

    Drawn from Sollumz's own LightFlags group, so these are the real exported
    flags - not a Seto reimplementation that would have to be kept in sync.
    """

    bl_label = "Light Flags"
    bl_idname = "SETO_PT_godray_flags_panel"
    bl_order = 2

    @classmethod
    def poll(cls, context):
        if not _GodRayChildPanel.poll(context):
            return False
        root = group.find_group_root(context.active_object)
        return group.resolve(root).has_light

    def draw(self, context):
        layout = self.layout
        root = group.find_group_root(context.active_object)
        refs = group.resolve(root)
        light_flags = refs.light.data.light_flags

        names = szi.get_flag_names(light_flags)
        if not names:
            layout.label(text="Sollumz did not report any light flags.", icon='ERROR')
            return

        grid = layout.grid_flow(columns=2, even_columns=True, align=True)
        for name in names:
            grid.prop(light_flags, name)


_classes = (
    SETO_PT_lighting_panel,
    SETO_PT_godray_panel,
    SETO_PT_godray_selected_panel,
    SETO_PT_godray_advanced_panel,
    SETO_PT_godray_flags_panel,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
