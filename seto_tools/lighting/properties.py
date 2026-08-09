"""Scene-level settings for the Lighting tool.

These are the *artist-facing master controls* - the small set of values that
describe a god ray the way a lighting artist thinks about it, rather than the
~40 raw GTA properties spread across a Sollumz light, a light shaft extension
and a particle extension.

Each master value fans out to a fixed, documented set of GTA properties. The
mapping is recorded in MASTER_TARGETS below so the panel can tell the user
exactly what a slider will overwrite before they drag it; the code that
performs the fan-out arrives with the sync system in a later phase.

Deliberately NOT here: any duplicate of a Sollumz property. Colour, intensity,
cone angles, flags and so on are only ever stored in Sollumz's own
PropertyGroups (light.light_properties, light.light_flags,
extension.light_shaft_extension_properties, ...). What lives here are the
higher-level dials that *derive* those values.
"""

import math

import bpy

# Sollumz limits a GTA cone half-angle to 90 degrees - LightProperties.
# cone_outer_angle is stored as Blender's spot_size / 2 and declared with
# max=math.pi/2. Nothing in this tool may try to exceed it: the cap is a real
# property of the GTA data, not a Blender display limit, and writing around it
# would desync the value Sollumz exports.
MAX_CONE_ANGLE = math.pi / 2


def settings_annotations(update=None):
    """Build a fresh set of property definitions for the tool's settings.

    Same pattern as the other Seto tools (see fake_ao/properties.py): the
    definitions are shared between the Scene settings below, the Create God
    Rays operator, and the per-group settings stored on the setup's root
    empty. It has to be a function rather than a module-level dict because a
    bpy.props.* definition cannot be shared between two classes.

    `update` is the callback Blender fires when a value changes; only the
    per-group copy will pass one.
    """
    return {
        "beam_color": bpy.props.FloatVectorProperty(
            name="Beam Color",
            description="Colour of the light and of the light shaft. Sunlight through a dusty "
                        "interior is usually a warm off-white rather than pure white",
            subtype='COLOR',
            size=3,
            min=0.0,
            max=1.0,
            default=(1.0, 0.97, 0.90),
            update=update,
        ),
        "master_intensity": bpy.props.FloatProperty(
            name="Master Intensity",
            description="Overall brightness. Drives the spot light's Intensity and, together "
                        "with Volumetric Strength, the light shaft's Intensity",
            default=150.0,
            min=0.0,
            soft_max=1000.0,
            update=update,
        ),
        "beam_length": bpy.props.FloatProperty(
            name="Beam Length",
            description="How far the beam reaches into the interior. Drives the light shaft's "
                        "Length and the spot light's Falloff",
            default=6.0,
            min=0.01,
            soft_max=50.0,
            subtype='DISTANCE',
            update=update,
        ),
        "beam_width": bpy.props.FloatProperty(
            name="Beam Width",
            description="Spread of the beam, driving the spot light's Cone Outer Angle. "
                        "Capped at 90 degrees because that is Sollumz's limit for this "
                        "property (it is stored as Blender's spot_size / 2)",
            default=math.radians(50.0),
            min=0.0,
            max=MAX_CONE_ANGLE,
            subtype='ANGLE',
            update=update,
        ),
        "volumetric_strength": bpy.props.FloatProperty(
            name="Volumetric Strength",
            description="How visible the beam itself is in the air, as opposed to the pool of "
                        "light it casts. Drives the spot light's Volume Intensity and scales "
                        "the light shaft's Intensity",
            default=1.0,
            min=0.0,
            soft_max=4.0,
            update=update,
        ),
        "fade_distance": bpy.props.FloatProperty(
            name="Fade Distance",
            description="Distance at which the light stops being drawn. Drives Light Fade "
                        "Distance; Shadow/Specular Fade Distance follow at a fixed ratio",
            default=40.0,
            min=0.0,
            soft_max=200.0,
            update=update,
        ),
        "add_dust": bpy.props.BoolProperty(
            name="Add Dust Particles",
            description="Also create a particle effect extension on the archetype, so dust "
                        "motes drift through the beam in game",
            default=True,
            update=update,
        ),
        "dust_fx_name": bpy.props.StringProperty(
            name="Dust FX Name",
            description="Particle effect name. Must exist in the ENTITYFX_AMBIENT_PTFX block "
                        "of entityfx.dat for your build - Sollumz does not validate this, and "
                        "a name that is not there simply does nothing in game",
            default="amb_dust_motes",
            update=update,
        ),
        "dust_amount": bpy.props.FloatProperty(
            name="Dust Amount",
            description="How much dust is in the air. Drives the particle extension's Scale "
                        "and Probability",
            default=1.0,
            min=0.0,
            soft_max=2.0,
            update=update,
        ),
    }


# Every setting name, in panel order. Used to copy values between the Scene
# settings, the operator and the per-group settings.
SETTING_NAMES = tuple(settings_annotations().keys())


# Which GTA properties each master control writes to. This is the contract the
# sync system implements and the panel quotes back to the user, so that
# dragging a master never silently clobbers a value the user cannot predict.
# Nothing outside these lists is ever touched by a master control.
MASTER_TARGETS = {
    "beam_color": (
        "light.color",
        "light_shaft.color",
    ),
    "master_intensity": (
        "light.light_properties.intensity",
        "light_shaft.intensity",
    ),
    "beam_length": (
        "light.light_properties.falloff",
        "light_shaft.length",
    ),
    "beam_width": (
        "light.light_properties.cone_outer_angle",
        "light.light_properties.cone_inner_angle",
    ),
    "volumetric_strength": (
        "light.light_properties.volume_intensity",
        "light_shaft.intensity",
    ),
    "fade_distance": (
        "light.light_properties.light_fade_distance",
        "light.light_properties.shadow_fade_distance",
        "light.light_properties.specular_fade_distance",
        "light.light_properties.volumetric_fade_distance",
    ),
    "dust_amount": (
        "particle.scale",
        "particle.probability",
    ),
    "dust_fx_name": (
        "particle.fx_name",
    ),
}


def copy_settings(source, target):
    """Copy every setting from `source` to `target`.

    Works in any direction, since all three carry the same property names.
    Vector properties come back as a bpy_prop_array rather than a plain tuple,
    so they are unpacked before assignment.
    """
    for name in SETTING_NAMES:
        value = getattr(source, name)
        if hasattr(value, "__len__") and not isinstance(value, str):
            value = tuple(value)
        setattr(target, name, value)


class SETO_PG_lighting_settings(bpy.types.PropertyGroup):
    # Assigned rather than written with `name: bpy.props...` syntax so the
    # definitions stay shared with the operator and the per-group settings -
    # see settings_annotations().
    __annotations__ = settings_annotations()


_classes = (SETO_PG_lighting_settings,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_lighting = bpy.props.PointerProperty(type=SETO_PG_lighting_settings)


def unregister():
    del bpy.types.Scene.seto_lighting
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
