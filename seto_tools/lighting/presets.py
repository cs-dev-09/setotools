"""Built-in god ray presets.

A preset is a starting point, not a mode: applying one writes the master
controls and nothing else, so everything stays adjustable afterwards and no
part of the tool is built around a particular preset.

Each entry may also carry a `shaft` block, applied only when a god ray is
selected - those values are raw Sollumz light shaft properties, so they can only
be written once a shaft actually exists.

Adding a preset is adding a dict here. Nothing else needs to change: the enum,
the panel and the operator are all generated from PRESETS.
"""

import math

import bpy

from . import group
from . import properties
from ..shared import sollumz_integration as szi


def _c(r, g, b):
    return (r, g, b)


# Density types worth reaching for, by name on Sollumz's LightShaftDensityType:
#   QUADRATIC_GRADIENT  soft, fades along the beam - the usual sun shaft
#   SOFT_SHADOW_HD      crisper, more expensive, for a hero beam
#   LINEAR              even along its length, reads as haze rather than a shaft
#   CONSTANT            no falloff at all, for stylised or very short beams

PRESETS = {
    "WINDOW_SUN": {
        "label": "Window Sun Rays",
        "description": "Warm sunlight through an intact window. The everyday case",
        "settings": {
            "beam_color": _c(1.0, 0.97, 0.90),
            "master_intensity": 150.0,
            "beam_length": 6.0,
            "beam_width": math.radians(50.0),
            "volumetric_strength": 1.0,
            "fade_distance": 40.0,
            "add_dust": True,
            "dust_fx_name": "amb_dust_motes",
            "dust_amount": 1.0,
        },
        "shaft": {"density_type": "QUADRATIC_GRADIENT", "volume_type": "SHAFT", "softness": 1.0},
    },
    "BROKEN_WINDOW": {
        "label": "Broken Window Rays",
        "description": "Hard narrow beams through gaps between boards. Use with One Per Gap",
        "settings": {
            "beam_color": _c(1.0, 0.95, 0.85),
            "master_intensity": 300.0,
            "beam_length": 8.0,
            "beam_width": math.radians(25.0),
            "volumetric_strength": 1.6,
            "fade_distance": 40.0,
            "add_dust": True,
            "dust_fx_name": "amb_dust_motes",
            "dust_amount": 1.4,
        },
        "shaft": {"density_type": "SOFT_SHADOW_HD", "volume_type": "SHAFT", "softness": 0.4},
    },
    "DOORWAY": {
        "label": "Doorway Light",
        "description": "A wide, short spill of light through an open door",
        "settings": {
            "beam_color": _c(1.0, 0.98, 0.94),
            "master_intensity": 200.0,
            "beam_length": 4.0,
            "beam_width": math.radians(70.0),
            "volumetric_strength": 0.8,
            "fade_distance": 30.0,
            "add_dust": True,
            "dust_fx_name": "amb_dust_motes",
            "dust_amount": 0.7,
        },
        "shaft": {"density_type": "QUADRATIC_GRADIENT", "volume_type": "SHAFT", "softness": 1.2},
    },
    "CEILING_HOLE": {
        "label": "Ceiling Hole",
        "description": "A shaft dropping straight down from a hole in the roof",
        "settings": {
            "beam_color": _c(1.0, 0.96, 0.88),
            "master_intensity": 250.0,
            "beam_length": 10.0,
            "beam_width": math.radians(35.0),
            "volumetric_strength": 1.8,
            "fade_distance": 50.0,
            "add_dust": True,
            "dust_fx_name": "amb_dust_motes",
            "dust_amount": 1.6,
        },
        "shaft": {"density_type": "QUADRATIC_GRADIENT", "volume_type": "CYLINDER", "softness": 0.8},
    },
    "INDUSTRIAL": {
        "label": "Industrial Beam",
        "description": "A cold, hard beam through a high factory window",
        "settings": {
            "beam_color": _c(0.90, 0.94, 1.0),
            "master_intensity": 350.0,
            "beam_length": 14.0,
            "beam_width": math.radians(40.0),
            "volumetric_strength": 1.2,
            "fade_distance": 60.0,
            "add_dust": True,
            "dust_fx_name": "amb_dust_motes",
            "dust_amount": 0.9,
        },
        "shaft": {"density_type": "SOFT_SHADOW", "volume_type": "SHAFT", "softness": 0.6},
    },
    "DUSTY": {
        "label": "Dusty Interior",
        "description": "Thick air: a heavy volumetric beam with a lot of motes",
        "settings": {
            "beam_color": _c(1.0, 0.93, 0.80),
            "master_intensity": 180.0,
            "beam_length": 7.0,
            "beam_width": math.radians(45.0),
            "volumetric_strength": 3.0,
            "fade_distance": 35.0,
            "add_dust": True,
            "dust_fx_name": "amb_dust_motes",
            "dust_amount": 2.0,
        },
        "shaft": {"density_type": "LINEAR_GRADIENT", "volume_type": "SHAFT", "softness": 1.5},
    },
    "NIGHT_EXTERIOR": {
        "label": "Night Exterior Beam",
        "description": "A cool artificial beam for night use. No dust by default",
        "settings": {
            "beam_color": _c(0.85, 0.90, 1.0),
            "master_intensity": 120.0,
            "beam_length": 12.0,
            "beam_width": math.radians(30.0),
            "volumetric_strength": 2.2,
            "fade_distance": 70.0,
            "add_dust": False,
            "dust_fx_name": "amb_dust_motes",
            "dust_amount": 0.5,
        },
        "shaft": {"density_type": "CONSTANT", "volume_type": "SHAFT", "softness": 0.3},
    },
}

# Order the enum is listed in, so it does not follow dict insertion by accident.
PRESET_ORDER = (
    "WINDOW_SUN", "BROKEN_WINDOW", "DOORWAY", "CEILING_HOLE",
    "INDUSTRIAL", "DUSTY", "NIGHT_EXTERIOR",
)

# Blender keeps EnumProperty item strings by reference, so build once and keep.
_ENUM_ITEMS = tuple(
    (key, PRESETS[key]["label"], PRESETS[key]["description"])
    for key in PRESET_ORDER
)


def apply_to_settings(preset_key, settings):
    """Write a preset's master values onto any settings group.

    Only names that really exist as settings are written, so a preset that
    mentions a property removed in a later version degrades instead of raising.
    """
    preset = PRESETS[preset_key]
    written = []
    for name, value in preset["settings"].items():
        if name not in properties.SETTING_NAMES:
            continue
        setattr(settings, name, value)
        written.append(name)
    return written


def apply_to_shaft(preset_key, shaft_props):
    """Write a preset's raw light shaft values, if it has any.

    density_type and volume_type are resolved through Sollumz's own enums rather
    than written as bare strings, so a typo here fails loudly at apply time
    instead of silently producing an invalid enum value.
    """
    block = PRESETS[preset_key].get("shaft")
    if not block or shaft_props is None:
        return []

    DensityType, VolumeType = szi.get_light_shaft_enums()
    written = []
    for name, value in block.items():
        if name == "density_type":
            shaft_props.density_type = getattr(DensityType, value)
        elif name == "volume_type":
            shaft_props.volume_type = getattr(VolumeType, value)
        else:
            setattr(shaft_props, name, value)
        written.append(name)
    return written


class SETO_OT_godray_apply_preset(bpy.types.Operator):
    """Load a preset into the God Ray settings, and into the selected setup if there is one"""

    bl_idname = "seto.godray_apply_preset"
    bl_label = "Apply Preset"
    bl_options = {'REGISTER', 'UNDO'}

    preset: bpy.props.EnumProperty(name="Preset", items=_ENUM_ITEMS)

    def execute(self, context):
        key = self.preset or context.scene.seto_lighting_preset
        if key not in PRESETS:
            self.report({'ERROR'}, f"Seto Lighting: unknown preset '{key}'.")
            return {'CANCELLED'}

        apply_to_settings(key, context.scene.seto_lighting)
        label = PRESETS[key]["label"]

        root = group.find_group_root(context.active_object)
        if root is None:
            self.report({'INFO'}, f"Applied '{label}' to the God Ray settings.")
            return {'FINISHED'}

        refs = group.resolve(root)
        # Writing the masters in one go under the suppress guard, then pushing
        # once - otherwise each assignment would fan out against a half-applied
        # preset.
        with group.suppress_sync():
            apply_to_settings(key, root.seto_godray)
        group.apply_masters(refs, root.seto_godray)
        apply_to_shaft(key, refs.shaft_props)

        szi.tag_redraw_ytyp(context)
        self.report({'INFO'}, f"Applied '{label}' to the settings and to '{root.name}'.")
        return {'FINISHED'}


_classes = (SETO_OT_godray_apply_preset,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_lighting_preset = bpy.props.EnumProperty(
        name="Preset",
        description="Starting point for a god ray. Applying one writes the master controls "
                    "only - everything stays adjustable afterwards",
        items=_ENUM_ITEMS,
    )


def unregister():
    del bpy.types.Scene.seto_lighting_preset
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
