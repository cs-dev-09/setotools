"""The God Ray group: what ties a spot light to its light shaft and dust.

A god ray is three pieces of data in two export files (see the YTYP section of
shared/sollumz_integration.py). Only one of them - the spot light - is a scene
object, so the obvious answer of "parent them together" cannot work. Instead:

    SETO_GodRay_001            an Empty, parented into the Drawable
      └── SETO_GodRay_001.light   the Sollumz spot light

and on the archetype whose asset is that Drawable:

    extensions["SETO_GodRay_001.shaft"]   CExtensionDefLightShaft
    extensions["SETO_GodRay_001.dust"]    CExtensionDefParticleEffect

The Empty carries `obj.seto_godray`, holding the master controls plus the names
needed to find the extensions again. It is a plain Empty with no Sollumz type,
so it exports as nothing at all - the requirement that viewport helpers must not
become exportable garbage geometry.

WHY NAMES AND NOT REFERENCES: extensions live in a CollectionProperty. Blender
cannot store a pointer to a collection member, an index goes stale the moment
anything is added or removed (including by the user in Sollumz's own panel), and
a stale PropertyGroup reference can crash Blender. So every access re-resolves
by name, and resolve() reports what it could not find rather than raising.
"""

import contextlib
import re

import bpy

from . import properties
from ..shared import sollumz_integration as szi

# Object naming. The group Empty is the name everything else is derived from.
GROUP_NAME_PREFIX = "SETO_GodRay_"
_GROUP_NAME_PATTERN = re.compile(r"^SETO_GodRay_(\d{3,})$")

LIGHT_SUFFIX = ".light"
SHAFT_SUFFIX = ".shaft"
DUST_SUFFIX = ".dust"

# Collection every generated setup is gathered into, mirroring how the other
# Seto tools keep their output together.
COLLECTION_NAME = "seto_god_rays"


# --------------------------------------------------------------- master fan-out
#
# The fixed ratios each master control fans out with. They are constants rather
# than user settings on purpose: the master controls exist to be predictable,
# and every one of these can still be overridden per-light in the Advanced
# panel afterwards.
#
# The defaults were taken from the reference setups: a light at intensity 150
# with a shaft at intensity 3.0, light fade 40 with shadow/specular fade 25,
# dust scale 1.2 at full probability.

# Shaft intensity is a small fraction of the light's - they are different units.
SHAFT_INTENSITY_SCALE = 0.02
# Inner cone as a fraction of the outer, giving the beam a soft edge.
CONE_INNER_RATIO = 0.6
# Shadow/specular/volumetric fade as a fraction of the light fade distance.
SHADOW_FADE_RATIO = 0.625
SPECULAR_FADE_RATIO = 0.625
VOLUMETRIC_FADE_RATIO = 0.625
# Particle scale at Dust Amount 1.0.
DUST_SCALE_BASE = 1.2


class GodRayRefs:
    """Everything a god ray group resolves to, plus what went missing.

    `missing` is a list of human-readable names; the panel and operators show it
    instead of failing, because a user is allowed to delete a light or an
    extension by hand and the tool should say so rather than raise.
    """

    def __init__(self, root):
        self.root = root
        self.light = None
        self.ytyp = None
        self.archetype = None
        self.shaft = None
        self.shaft_props = None
        self.dust = None
        self.dust_props = None
        self.missing = []

    @property
    def is_complete(self):
        return not self.missing

    @property
    def has_light(self):
        return self.light is not None

    @property
    def has_shaft(self):
        return self.shaft_props is not None

    @property
    def has_dust(self):
        return self.dust_props is not None


def is_group_root(obj):
    return (obj is not None and obj.type == 'EMPTY'
            and getattr(obj, "seto_godray", None) is not None
            and obj.seto_godray.is_godray)


def find_group_root(obj):
    """The god ray root for `obj`, whether `obj` is the root, the light, or a
    child of either. Returns None when `obj` has nothing to do with a god ray."""
    node = obj
    while node is not None:
        if is_group_root(node):
            return node
        node = node.parent
    return None


def next_group_name():
    """Next free SETO_GodRay_NNN.

    Explicit sequential numbering rather than Blender's automatic ".001"
    suffixing, so the extension names derived from it stay predictable.
    """
    highest = 0
    for name in bpy.data.objects.keys():
        match = _GROUP_NAME_PATTERN.match(name)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{GROUP_NAME_PREFIX}{highest + 1:03d}"


def resolve(root):
    """Resolve a god ray root Empty into its live parts.

    Never raises for missing pieces - they are collected in `refs.missing`. Only
    a genuinely unusable Sollumz install raises, and the callers of this handle
    that where they already handle it for everything else.
    """
    refs = GodRayRefs(root)
    if not is_group_root(root):
        return refs

    data = root.seto_godray

    light = data.light_object
    if light is not None and light.name in bpy.data.objects and szi.is_gta_light(light):
        refs.light = light
    else:
        refs.missing.append("spot light")

    asset = data.asset_object
    if asset is None or asset.name not in bpy.data.objects:
        refs.missing.append("archetype asset (drawable)")
        return refs

    archetype = None
    for ytyp, arch in szi.find_archetypes_for_object(asset):
        if arch.name == data.archetype_name or archetype is None:
            refs.ytyp, archetype = ytyp, arch
            if arch.name == data.archetype_name:
                break
    if archetype is None:
        refs.missing.append(f"archetype '{data.archetype_name}'")
        return refs
    refs.archetype = archetype

    if data.shaft_ext_name:
        _, shaft = szi.find_extension_by_name(archetype, data.shaft_ext_name)
        if shaft is None:
            refs.missing.append(f"light shaft '{data.shaft_ext_name}'")
        else:
            refs.shaft = shaft
            refs.shaft_props = shaft.get_properties()

    # Dust is optional: only reported missing if this group was built with one.
    if data.dust_ext_name:
        _, dust = szi.find_extension_by_name(archetype, data.dust_ext_name)
        if dust is None:
            refs.missing.append(f"dust particle '{data.dust_ext_name}'")
        else:
            refs.dust = dust
            refs.dust_props = dust.get_properties()

    return refs


# ------------------------------------------------------------------ sync guard

_suppress_depth = 0


@contextlib.contextmanager
def suppress_sync():
    """Stop master-control update callbacks firing while inside.

    Needed whenever several settings are written in a row - during creation, or
    when copying settings between groups - because each assignment would
    otherwise trigger a full fan-out against a half-written group.
    """
    global _suppress_depth
    _suppress_depth += 1
    try:
        yield
    finally:
        _suppress_depth -= 1


def _sync_suppressed():
    return _suppress_depth > 0


def apply_masters(refs, settings):
    """Fan the master controls out onto the real Sollumz properties.

    This is the only code that writes derived values, and it writes exactly the
    properties listed in properties.MASTER_TARGETS - nothing else on the light,
    the shaft or the particle is touched, so anything set by hand in the
    Advanced panel survives unless it is explicitly one of these.

    Returns a list of the parts that were written, for reporting.
    """
    written = []

    if refs.light is not None:
        light_data = refs.light.data
        light_props = light_data.light_properties

        light_data.color = tuple(settings.beam_color)
        light_props.intensity = settings.master_intensity
        light_props.falloff = settings.beam_length
        # Sollumz clamps this to 90 degrees; the property is already limited to
        # the same range, so no value can arrive here that it would reject.
        light_props.cone_outer_angle = settings.beam_width
        light_props.cone_inner_angle = settings.beam_width * CONE_INNER_RATIO
        light_props.volume_intensity = settings.volumetric_strength
        light_props.light_fade_distance = settings.fade_distance
        light_props.shadow_fade_distance = settings.fade_distance * SHADOW_FADE_RATIO
        light_props.specular_fade_distance = settings.fade_distance * SPECULAR_FADE_RATIO
        light_props.volumetric_fade_distance = settings.fade_distance * VOLUMETRIC_FADE_RATIO
        written.append("light")

    if refs.shaft_props is not None:
        shaft = refs.shaft_props
        color = tuple(settings.beam_color)
        shaft.color = (color[0], color[1], color[2], 1.0)
        # Master Intensity and Volumetric Strength compose here rather than
        # fighting over the same property.
        shaft.intensity = (settings.master_intensity * SHAFT_INTENSITY_SCALE
                           * settings.volumetric_strength)
        shaft.length = settings.beam_length
        written.append("light shaft")

    if refs.dust_props is not None:
        dust = refs.dust_props
        dust.fx_name = settings.dust_fx_name
        dust.scale = settings.dust_amount * DUST_SCALE_BASE
        dust.probability = max(0, min(100, int(round(settings.dust_amount * 100.0))))
        written.append("dust")

    return written


def _on_master_changed(self, context):
    """Update callback on the per-group master settings.

    Deliberately the only automatic write in the whole tool: values are pushed
    when the artist moves a slider, never from a panel redraw. `auto_sync` lets
    the artist switch even that off once they start hand-tuning in the Advanced
    panel.
    """
    if _sync_suppressed():
        return
    root = self.id_data
    if not is_group_root(root) or not self.auto_sync:
        return
    refs = resolve(root)
    if refs.has_light or refs.has_shaft or refs.has_dust:
        apply_masters(refs, self)


class SETO_PG_godray(bpy.types.PropertyGroup):
    """Per-group data, stored on the root Empty."""

    # The master controls, sharing their definitions with the Scene settings and
    # the Create operator, but wired to fire the fan-out when changed.
    __annotations__ = dict(properties.settings_annotations(update=_on_master_changed))

    __annotations__.update({
        "is_godray": bpy.props.BoolProperty(
            name="Is God Ray",
            description="Marks this Empty as the root of a Seto god ray setup",
            default=False,
        ),
        "auto_sync": bpy.props.BoolProperty(
            name="Auto Sync",
            description="Push the master controls onto the GTA properties whenever one is "
                        "changed. Turn off to hand-tune in Advanced GTA Settings without the "
                        "masters overwriting your values",
            default=True,
        ),
        "light_object": bpy.props.PointerProperty(
            name="Spot Light",
            description="The Sollumz spot light belonging to this god ray",
            type=bpy.types.Object,
        ),
        "asset_object": bpy.props.PointerProperty(
            name="Drawable",
            description="The Drawable that the archetype holding this god ray's extensions "
                        "points at",
            type=bpy.types.Object,
        ),
        "ytyp_name": bpy.props.StringProperty(name="YTYP"),
        "archetype_name": bpy.props.StringProperty(name="Archetype"),
        "shaft_ext_name": bpy.props.StringProperty(name="Light Shaft Extension"),
        "dust_ext_name": bpy.props.StringProperty(name="Dust Extension"),
        # The opening the setup was generated from, in the drawable's local
        # space. Kept so Sync Light Shaft can rebuild the corners after the
        # light has been re-aimed, without asking the user to re-select faces.
        "opening_center": bpy.props.FloatVectorProperty(name="Opening Center", subtype='TRANSLATION'),
        "opening_right": bpy.props.FloatVectorProperty(name="Opening Right", subtype='XYZ'),
        "opening_up": bpy.props.FloatVectorProperty(name="Opening Up", subtype='XYZ'),
        "opening_width": bpy.props.FloatProperty(name="Opening Width", subtype='DISTANCE'),
        "opening_height": bpy.props.FloatProperty(name="Opening Height", subtype='DISTANCE'),
    })


_classes = (SETO_PG_godray,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.seto_godray = bpy.props.PointerProperty(type=SETO_PG_godray)


def unregister():
    del bpy.types.Object.seto_godray
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
