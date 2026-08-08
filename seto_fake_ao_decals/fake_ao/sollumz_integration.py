"""All Sollumz-specific integration lives here, isolated from geometry.py.

Nothing in this file invents Sollumz APIs - every function it calls was
verified against the Sollumz v2.9.0 source (see the architecture analysis
this addon was built from). Sollumz's own source is never modified; this
module only detects it and imports/calls its existing functions.

Sollumz can be installed either as a legacy addon (module name "Sollumz")
or as a Blender 4.2+ Extension (module name like
"bl_ext.<repo>.Sollumz"), so the base module name is resolved dynamically
via bpy.context.preferences.addons instead of a hardcoded "import Sollumz".
"""

import importlib

import bpy
import numpy as np

DECAL_SHADER_FILENAME = "decal.sps"


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
    (get_uv_map_name / get_color_attr_name). This is a hard dependency: if
    Sollumz is unavailable this will raise, since UV/Color data is the core
    deliverable of this tool.
    """
    meshhelper = _import("tools.meshhelper")
    uv_arr = np.array(loop_uv, dtype=np.float64)
    rgba_arr = np.array(loop_rgba, dtype=np.float64)
    meshhelper.create_uv_attr(mesh, 0, initial_values=uv_arr)
    meshhelper.create_color_attr(mesh, 0, initial_values=rgba_arr)


def find_or_create_decal_material(reuse=True):
    """Find an existing decal.sps material to reuse, or create a new one via
    Sollumz's own shader creation function.

    Never invents a shader: first confirms decal.sps exists in Sollumz's
    currently mounted ShaderManager (from szio), and raises
    SollumzShaderError with a clear message if not.
    """
    try:
        shader_module = importlib.import_module("szio.gta5.shader")
    except ImportError as e:
        raise SollumzShaderError(f"Could not import szio.gta5.shader ({e}).")

    sollumz_properties = _import("sollumz_properties")
    shader_materials = _import("ydr.shader_materials")

    shader_manager = shader_module.ShaderManager
    material_type = sollumz_properties.MaterialType

    shader_def = shader_manager.find_shader(DECAL_SHADER_FILENAME)
    if shader_def is None:
        raise SollumzShaderError(
            f"Shader '{DECAL_SHADER_FILENAME}' was not found by Sollumz's ShaderManager."
        )

    if reuse:
        for mat in bpy.data.materials:
            if mat.sollum_type == material_type.SHADER and \
                    mat.shader_properties.filename == DECAL_SHADER_FILENAME:
                return mat

    return shader_materials.create_shader(DECAL_SHADER_FILENAME)


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
