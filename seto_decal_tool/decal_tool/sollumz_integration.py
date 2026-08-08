"""All Sollumz-specific integration lives here, isolated from geometry.py.

Nothing in this file invents Sollumz APIs - every function it calls was verified
against the installed Sollumz source. Sollumz's own source is never modified;
this module only detects it and imports/calls its existing functions.

Sollumz can be installed either as a legacy addon (module name "Sollumz") or as
a Blender 4.2+ Extension (module name like "bl_ext.<repo>.sollumz"), so the base
module name is resolved dynamically via bpy.context.preferences.addons instead
of a hardcoded "import Sollumz".

The material this tool produces:

    Shader        decal.sps
    Render bucket 2 (Decal) - comes from the shader definition, not set here
    Parameters    left at the shader's own defaults (useTessellation 0,
                  wetnessMultiplier 1, specularIntensityMult 0,
                  specularFalloffMult 100, specularFresnel 0.97)
    Textures      DiffuseSampler <- the decal image picked from the library.
                  The exported GTA texture name comes from the image filename,
                  via Sollumz's read-only sollumz_texture_name property.

decal.sps's vertex layout is Position / Normal / Colour0 / TexCoord0, which maps
to the "UVMap 0" and "Color 1" attributes written by write_uv_and_color().
Sollumz builds its node graph so that the rendered alpha is
`Color 1 alpha * texture alpha`, which is why the caller must write alpha 1.0.
"""

import importlib
import os

import bpy
import numpy as np

DECAL_SHADER_FILENAME = "decal.sps"

# Materials this tool creates are named "<prefix><texture stem>" so they can be
# recognised for reuse later. Reuse is deliberately restricted to our own
# materials: matching on the shader filename alone would happily adopt - and then
# retexture - an unrelated decal.sps material the user set up by hand.
MATERIAL_NAME_PREFIX = "seto_decal_mat_"

DIFFUSE_SAMPLER_NODE = "DiffuseSampler"


class SollumzUnavailableError(Exception):
    """Sollumz is not installed/enabled, or its dependencies (szio) are not mounted."""


class SollumzShaderError(Exception):
    """Sollumz is available, but the requested shader material could not be
    found or created."""


class TextureLoadError(Exception):
    """The decal image file is missing or could not be read by Blender."""


def _get_sollumz_base_module_name():
    """Resolve Sollumz's registered addon module name.

    Case-insensitive match on the last path component, because the module name
    differs depending on how Sollumz was installed:
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
    """Return the owning Drawable object for `obj`, or None if `obj` is not part
    of a Sollumz Drawable hierarchy.

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
    decal.sps's vertex layout requires both TexCoord0 and Colour0, so if Sollumz
    is unavailable this will raise.
    """
    meshhelper = _import("tools.meshhelper")
    uv_arr = np.array(loop_uv, dtype=np.float64)
    rgba_arr = np.array(loop_rgba, dtype=np.float64)
    meshhelper.create_uv_attr(mesh, 0, initial_values=uv_arr)
    meshhelper.create_color_attr(mesh, 0, initial_values=rgba_arr)


def get_color_attr_name(index=0):
    """Sollumz's name for a colour attribute ("Color 1" for index 0).

    Falls back to the known name if Sollumz is unavailable, so live editing of
    an already-generated decal keeps working even without it.
    """
    try:
        meshhelper = _import("tools.meshhelper")
        return meshhelper.get_color_attr_name(index)
    except Exception:
        return f"Color {index + 1}"


def _is_shader_material(mat):
    sollumz_properties = _import("sollumz_properties")
    return getattr(mat, "sollum_type", None) == sollumz_properties.MaterialType.SHADER


def material_name_for(texture_stem):
    return f"{MATERIAL_NAME_PREFIX}{texture_stem}"


def _normalized_path(path):
    return os.path.normcase(os.path.abspath(bpy.path.abspath(path)))


def _image_is_file(image, path):
    """True if `image` was loaded from the exact same file as `path`."""
    if image is None or not image.filepath:
        return False
    try:
        return _normalized_path(image.filepath) == _normalized_path(path)
    except (ValueError, OSError):
        return False


def get_diffuse_node(material):
    """The decal.sps DiffuseSampler image node, or None.

    Sollumz's create_image_node names each image node after the shader parameter
    it represents, so this lookup is exact rather than positional.
    """
    node_tree = getattr(material, "node_tree", None)
    if node_tree is None:
        return None
    node = node_tree.nodes.get(DIFFUSE_SAMPLER_NODE)
    if node is None or not isinstance(node, bpy.types.ShaderNodeTexImage):
        return None
    return node


def load_image(path):
    """Load a decal texture into Blender, reusing it if already loaded.

    The source file is only ever read - never written back - and the filepath is
    left as loaded so Sollumz's sollumz_texture_name (basename without extension)
    produces the correct GTA texture name on export.
    """
    if not os.path.isfile(path):
        raise TextureLoadError(
            f"Texture file no longer exists: {os.path.basename(path)}. Press Refresh Library."
        )
    try:
        image = bpy.data.images.load(path, check_existing=True)
    except (RuntimeError, OSError) as e:
        raise TextureLoadError(f"Could not load '{os.path.basename(path)}': {e}")

    # Straight (non-premultiplied) alpha with an sRGB colour space is what a
    # normal decal PNG/TGA wants, so transparent areas show through instead of
    # rendering as an opaque rectangle.
    try:
        image.alpha_mode = 'STRAIGHT'
        image.colorspace_settings.name = 'sRGB'
    except (TypeError, AttributeError):
        # A format Blender treats specially (some .dds) may reject one of these;
        # not worth failing the decal over.
        pass

    return image


def find_existing_decal_material(texture_stem, texture_path):
    """A previously created decal material for this exact texture file, or None.

    All three conditions must hold, which is what keeps materials shared only
    between decals that genuinely use the same image:
      * the name is ours (accepting Blender's automatic ".001" suffixing),
      * it is a Sollumz shader material using decal.sps,
      * its DiffuseSampler points at the same file on disk.
    """
    base_name = material_name_for(texture_stem)
    for mat in bpy.data.materials:
        if not (mat.name == base_name or mat.name.startswith(base_name + ".")):
            continue
        if not _is_shader_material(mat):
            continue
        if mat.shader_properties.filename != DECAL_SHADER_FILENAME:
            continue
        node = get_diffuse_node(mat)
        if node is not None and _image_is_file(node.image, texture_path):
            return mat
    return None


def find_or_create_decal_material(texture_stem, texture_path, reuse=True):
    """Find a decal.sps material for this texture, or create and texture a new one.

    Never invents a shader: decal.sps is first confirmed to exist in Sollumz's
    currently mounted ShaderManager (from szio).

    Sollumz's own post_create_shader_add_default_images is deliberately never
    called - it would drop a generated blank image into every empty slot, and
    that blank then exports as a real (blank) texture. The one slot this tool
    cares about, DiffuseSampler, is filled with the user's decal image instead.

    Raises SollumzShaderError / TextureLoadError; on failure no partially built
    material is left in the file.
    """
    try:
        shader_module = importlib.import_module("szio.gta5.shader")
    except ImportError as e:
        raise SollumzShaderError(f"Could not import szio.gta5.shader ({e}).")

    shader_materials = _import("ydr.shader_materials")

    if shader_module.ShaderManager.find_shader(DECAL_SHADER_FILENAME) is None:
        raise SollumzShaderError(
            f"Shader '{DECAL_SHADER_FILENAME}' was not found by Sollumz's ShaderManager."
        )

    if reuse:
        existing = find_existing_decal_material(texture_stem, texture_path)
        if existing is not None:
            return existing

    # Load the image first: if the texture is unreadable we fail before creating
    # a material that would otherwise be left behind untextured.
    image = load_image(texture_path)

    material = shader_materials.create_shader(DECAL_SHADER_FILENAME)
    node = get_diffuse_node(material)
    if node is None:
        bpy.data.materials.remove(material)
        raise SollumzShaderError(
            f"'{DECAL_SHADER_FILENAME}' material has no '{DIFFUSE_SAMPLER_NODE}' texture node."
        )

    material.name = material_name_for(texture_stem)
    node.image = image
    return material


def assign_material_to_object(obj, material):
    """Assign `material` to `obj`'s mesh and bring its UV/Color attributes in
    line with what the shader expects, the same way Sollumz's own
    "Create Shader Material" operator does."""
    materials_ops = _import("ydr.operators.materials")
    mesh = obj.data
    mesh.materials.append(material)
    materials_ops.post_create_shader_update_object(obj, material)
