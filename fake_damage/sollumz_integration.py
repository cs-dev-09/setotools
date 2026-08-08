"""All Sollumz-specific integration lives here, isolated from geometry.py.

Nothing in this file invents Sollumz APIs - every function it calls was
verified against the Sollumz source. Sollumz's own source is never modified;
this module only detects it and imports/calls its existing functions.

Sollumz can be installed either as a legacy addon (module name "Sollumz") or
as a Blender 4.2+ Extension (module name like "bl_ext.<repo>.sollumz"), so the
base module name is resolved dynamically via
bpy.context.preferences.addons instead of a hardcoded "import Sollumz".

The material this tool produces:

    Shader        decal_normal_only.sps
    Render bucket 2 (Decal) - comes from the shader definition, not set here
    Parameters    useTessellation        0 (disabled)
                  bumpiness              1.00
                  specularIntensityMult  0.00
                  specularFalloffMult    40.00
                  specularFresnel        0.75
    Textures      left empty - the user assigns DiffuseSampler / BumpSampler
                  themselves (recommended: gz_v_ml_wallnormal_n.dds in both,
                  Color Space Non-Color, not embedded)

decal_normal_only.sps ships with different defaults for some of those values
(specularIntensityMult 0.125, specularFalloffMult 100, specularFresnel 0.97),
so all of them are written explicitly after the material is created.
"""

import importlib

import bpy
import numpy as np

DAMAGE_SHADER_FILENAME = "decal_normal_only.sps"

# Materials this tool creates are named so they can be recognised for reuse
# later. Reuse is deliberately restricted to our own materials: matching on the
# shader filename alone would happily adopt - and then overwrite the parameter
# values of - an unrelated decal_normal_only material the user set up by hand.
MATERIAL_NAME = "seto_fakedamage"

VALUE_PARAMETERS = {
    "useTessellation": 0.0,
    "bumpiness": 1.00,
    "specularIntensityMult": 0.00,
    "specularFalloffMult": 40.00,
    "specularFresnel": 0.75,
}

_PARAMETER_NODE_IDNAME = "SOLLUMZ_NT_SHADER_Parameter"


class SollumzUnavailableError(Exception):
    """Sollumz is not installed/enabled, or its dependencies (szio) are not mounted."""


class SollumzShaderError(Exception):
    """Sollumz is available, but the requested shader material could not be
    found or created."""


def _get_sollumz_base_module_name():
    """Resolve Sollumz's registered addon module name.

    Case-insensitive match on the last path component, because the module
    name differs depending on how Sollumz was installed:
      - Legacy addon (unzipped into scripts/addons/Sollumz): "Sollumz"
      - Blender 4.2+ Extension: derived from blender_manifest.toml's
        `id = "sollumz"` (lowercase), e.g. "bl_ext.user_default.sollumz"
    """
    for module_name in bpy.context.preferences.addons.keys():
        if module_name.rsplit(".", 1)[-1].lower() == "sollumz":
            return module_name
    return None


def _import(submodule_path):
    """Import a Sollumz submodule by dotted path, e.g. 'tools.meshhelper'."""
    base = _get_sollumz_base_module_name()
    if base is None:
        raise SollumzUnavailableError("Sollumz addon is not enabled.")
    return importlib.import_module(f"{base}.{submodule_path}")


def is_sollumz_available():
    """True if Sollumz is enabled AND has its szio dependency mounted."""
    return get_status_message()[0]


def get_status_message():
    """Returns (available: bool, message: str) with a specific reason when
    unavailable, so the UI can show something more useful than a generic
    "not detected"."""
    base = _get_sollumz_base_module_name()
    if base is None:
        return False, "Sollumz addon is not installed/enabled."
    try:
        deps = importlib.import_module(f"{base}.dependencies")
    except Exception as e:
        return False, f"Found Sollumz ('{base}') but could not import its dependencies module: {e}"
    try:
        if not deps.has_required_dependencies():
            return False, "Sollumz is enabled, but its dependencies (szio) are not installed. Open Sollumz's Preferences and install dependencies."
    except Exception as e:
        return False, f"Could not check Sollumz dependencies: {e}"
    return True, f"Sollumz OK ('{base}')."


def find_drawable_parent(obj):
    """Return the owning Drawable object for `obj`, or None if `obj` is not
    part of a Sollumz Drawable hierarchy.

    Wraps Sollumz's sollumz_helper.find_sollumz_parent(obj, SollumType.DRAWABLE).
    """
    sollumz_helper = _import("sollumz_helper")
    sollumz_properties = _import("sollumz_properties")
    return sollumz_helper.find_sollumz_parent(obj, sollumz_properties.SollumType.DRAWABLE)


def convert_to_drawable_model(obj):
    """Register `obj` as a valid Sollumz Drawable Model (sollum_type + sz_lods).

    Wraps Sollumz's tools.drawablehelper.convert_obj_to_model.
    """
    drawablehelper = _import("tools.drawablehelper")
    drawablehelper.convert_obj_to_model(obj)


def write_uv_and_color(mesh, loop_uv, loop_rgba):
    """Create Sollumz-compatible "UVMap 0" (FLOAT2/CORNER) and "Color 1"
    (BYTE_COLOR/CORNER) attributes on `mesh`.

    Wraps Sollumz's tools.meshhelper.create_uv_attr / create_color_attr, which
    already use the correct type/domain and Sollumz's own naming convention
    (get_uv_map_name / get_color_attr_name). This is a hard dependency:
    decal_normal_only's vertex layout requires both TexCoord0 and Colour0, so
    if Sollumz is unavailable this will raise.
    """
    meshhelper = _import("tools.meshhelper")
    uv_arr = np.array(loop_uv, dtype=np.float64)
    rgba_arr = np.array(loop_rgba, dtype=np.float64)
    meshhelper.create_uv_attr(mesh, 0, initial_values=uv_arr)
    meshhelper.create_color_attr(mesh, 0, initial_values=rgba_arr)


def _is_shader_material(mat):
    sollumz_properties = _import("sollumz_properties")
    return getattr(mat, "sollum_type", None) == sollumz_properties.MaterialType.SHADER


def _find_existing_damage_material():
    """Return a previously created Fake Damage material, or None.

    Accepts Blender's automatic ".001" suffixing so a material that got
    renamed on append/link is still recognised.
    """
    for mat in bpy.data.materials:
        if not (mat.name == MATERIAL_NAME or mat.name.startswith(MATERIAL_NAME + ".")):
            continue
        if not _is_shader_material(mat):
            continue
        if mat.shader_properties.filename == DAMAGE_SHADER_FILENAME:
            return mat
    return None


def apply_value_parameters(material, parameters=None):
    """Write the Fake Damage value parameters onto an existing material.

    Sollumz stores each shader value parameter as a node named after the
    parameter, so a single pass over the node tree covers all of them. Missing
    parameters are reported rather than raising: a future Shaders.xml could
    rename one, and that should not cost the user their geometry.

    Returns the list of parameter names that were not found.
    """
    if parameters is None:
        parameters = VALUE_PARAMETERS

    node_tree = material.node_tree
    missing = []
    for name, value in parameters.items():
        node = node_tree.nodes.get(name)
        if node is None or node.bl_idname != _PARAMETER_NODE_IDNAME:
            missing.append(name)
            continue
        node.set(0, float(value))
    return missing


def find_or_create_damage_material(reuse=True):
    """Find a Fake Damage material to reuse, or create and configure a new one.

    Never invents a shader: decal_normal_only.sps is first confirmed to exist
    in Sollumz's currently mounted ShaderManager (from szio).

    DiffuseSampler / BumpSampler are deliberately left empty - the user picks
    their own damage normal map in the material properties. This is also why
    Sollumz's own post_create_shader_add_default_images is never called: it
    would drop a generated blank image into every slot, which then exports as
    a real (blank) texture.

    Returns (material, missing_parameters). A reused material is left exactly
    as the user has it - its parameters are not rewritten - so hand tweaks
    survive.
    """
    try:
        shader_module = importlib.import_module("szio.gta5.shader")
    except ImportError as e:
        raise SollumzShaderError(f"Could not import szio.gta5.shader ({e}).")

    shader_materials = _import("ydr.shader_materials")

    if shader_module.ShaderManager.find_shader(DAMAGE_SHADER_FILENAME) is None:
        raise SollumzShaderError(
            f"Shader '{DAMAGE_SHADER_FILENAME}' was not found by Sollumz's ShaderManager."
        )

    if reuse:
        existing = _find_existing_damage_material()
        if existing is not None:
            return existing, []

    material = shader_materials.create_shader(DAMAGE_SHADER_FILENAME)
    material.name = MATERIAL_NAME
    return material, apply_value_parameters(material)


def assign_material_to_object(obj, material):
    """Assign `material` to `obj`'s mesh and bring its UV/Color attributes in
    line with what the shader expects, the same way Sollumz's own
    "Create Shader Material" operator does.

    Deliberately does NOT call Sollumz's post_create_shader_add_default_images:
    the user manages normal textures manually, so texture slots are left empty
    instead of getting an auto-generated blank placeholder image.
    """
    materials_ops = _import("ydr.operators.materials")
    mesh = obj.data
    mesh.materials.append(material)
    materials_ops.post_create_shader_update_object(obj, material)
