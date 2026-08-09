"""All Sollumz-specific integration for every Seto tool, isolated in one place.

Nothing in this file invents Sollumz APIs - every function it calls was verified
against the installed Sollumz source. Sollumz's own source is never modified;
this module only detects it and imports/calls its existing functions.

Sollumz can be installed either as a legacy addon (module name "Sollumz") or as
a Blender 4.2+ Extension (module name like "bl_ext.<repo>.sollumz"), so the base
module name is resolved dynamically via bpy.context.preferences.addons instead
of a hardcoded "import Sollumz".

Three of the tools used to carry a copy of this each, back when they were
separate add-ons. The copies were identical apart from their docstrings and the
one material function each needed, so merging them changed no behaviour - the
material builders are simply named apart now:

    find_or_create_decal_material       Decal Tool   decal.sps, library texture
    find_or_create_damage_material      Fake Damage  decal_normal_only.sps, bundled
    find_or_create_smooth_edge_material Smooth Edge  decal_normal_only.sps, bundled
    find_or_create_fake_ao_material     Fake AO      decal.sps, no texture

Each keeps its own material name and its own reuse rule, which is what stops one
tool from adopting - and then retexturing - a material another tool (or the
user) set up. Fake Damage and Smooth Edge use the same shader, so without that
separation they would fight over each other's materials.

Shared conventions worth knowing:

  * "UVMap 0" (FLOAT2/CORNER) and "Color 1" (BYTE_COLOR/CORNER) come from
    Sollumz's own create_uv_attr / create_color_attr, never guessed here.
  * post_create_shader_add_default_images is deliberately never called: it drops
    a blank generated image into every empty texture slot, and that blank then
    exports as a real (blank) texture.
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


# A module only Sollumz has. Importing it is what turns "this name looks like
# Sollumz" into "this is Sollumz".
_SOLLUMZ_MARKER_MODULE = "sollumz_properties"


def _addon_leaf_name(module_name):
    """The add-on's own name, with any extension-repository prefix removed.

    Splitting on the last dot is wrong here: an extension is
    "bl_ext.<repo>.<id>", where the id never contains a dot, but a legacy
    add-on folder freely does - "Sollumz-2.9.0" would come back as "0".
    """
    if module_name.startswith("bl_ext."):
        parts = module_name.split(".", 2)
        return parts[2] if len(parts) > 2 else ""
    return module_name


def _looks_like_sollumz(module_name):
    """Could this registered add-on be Sollumz? A CANDIDATE test, not a verdict.

    Deliberately loose, because the module name depends entirely on how Sollumz
    was installed, and being too strict means every tool reports "Sollumz not
    available" on a machine that plainly has it:

      - Extension (Blender 4.2+): the manifest id, so "bl_ext.<repo>.sollumz".
        The repo part varies - "user_default" for Install from Disk, something
        else when it comes from a remote repository.
      - Legacy add-on unzipped into scripts/addons: "Sollumz".
      - **Downloaded from the GitHub repository**: GitHub names its archive
        after the branch or tag, so the folder - and therefore the module - is
        "Sollumz-main", "Sollumz-master" or "Sollumz-2.9.0". This is the case
        that was being missed, and it is a completely normal way to install it.

    Guessing which separators are legitimate is a losing game, so this does not
    try: anything starting with "sollumz" is a candidate, and
    _get_sollumz_base_module_name() decides by importing. That way an unrelated
    "sollumz_extras" is rejected because it is not Sollumz, not because its
    name was spelled in a way this function failed to anticipate.
    """
    return _addon_leaf_name(module_name).lower().startswith("sollumz")


def _get_sollumz_base_module_name():
    """Resolve Sollumz's registered add-on module name, or None.

    A name that looks right is not proof, so each candidate is confirmed by
    importing a module only Sollumz has. If none confirm, the best-looking
    candidate is still returned - get_status_message() can then say what was
    found and why it did not work, which is far more useful than "not
    installed" when it plainly is.
    """
    candidates = [name for name in bpy.context.preferences.addons.keys()
                  if _looks_like_sollumz(name)]
    if not candidates:
        return None
    # An exact "sollumz" wins over "Sollumz-main" if somehow both are enabled.
    candidates.sort(key=lambda name: _addon_leaf_name(name).lower() != "sollumz")

    for name in candidates:
        try:
            importlib.import_module(f"{name}.{_SOLLUMZ_MARKER_MODULE}")
            return name
        except Exception:
            continue
    # Nothing verified. Hand back the best-looking candidate anyway so
    # get_status_message() can name it and say why it failed - far more use than
    # claiming Sollumz is not installed when something calling itself Sollumz
    # clearly is.
    return candidates[0]


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
        # Installed but unticked looks identical to not installed from here:
        # preferences.addons only lists what is enabled. Say both, because
        # "not installed" alone sends people to reinstall something they have.
        return False, ("No enabled Sollumz add-on found. Install it, and make "
                       "sure its checkbox is ticked in Preferences > Add-ons.")
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


def get_uv_map_name(index=0):
    """Sollumz's name for a UV map ("UVMap 0" for index 0).

    Falls back to the known name if Sollumz is unavailable, so live editing of an
    already-generated decal keeps working even without it.
    """
    try:
        meshhelper = _import("tools.meshhelper")
        return meshhelper.get_uv_map_name(index)
    except Exception:
        return f"UVMap {index}"


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


# ------------------------------------------------ Fake Damage material

BUMP_SAMPLER_NODE = "BumpSampler"


def _assign_bundled_texture(material, texture_path, node_names, colorspace):
    """Put a tool's bundled texture into the sampler slots it names.

    Which slots, and which colour space, depend on the shader:

      * decal_normal_only (Fake Damage, Smooth Edge) reads its normal from
        BumpSampler and still expects something in DiffuseSampler, and both want
        Non-Color - reading a normal map through sRGB bends the lighting.
      * decal.sps (Fake AO) has only DiffuseSampler, and that is a colour
        texture, so sRGB.

    A slot the shader does not have is skipped rather than treated as an error.
    Returns a warning string, or None when the texture went in cleanly.
    """
    if not texture_path:
        return ("No texture is bundled with this tool - drop one into its "
                "textures/ folder and the next strip will use it.")

    try:
        image = load_image(texture_path)
    except TextureLoadError as e:
        return str(e)

    try:
        image.colorspace_settings.name = colorspace
    except (TypeError, AttributeError):
        pass

    node_tree = material.node_tree
    for node_name in node_names:
        node = node_tree.nodes.get(node_name)
        if node is not None and isinstance(node, bpy.types.ShaderNodeTexImage):
            node.image = image
            # Left non-embedded: the texture is expected to live in the asset's
            # own TXD, referenced by name, not baked into the .ydr.
            node.texture_properties.embedded = False
    return None


def _assign_normal_map(material, texture_path):
    """The decal_normal_only case: both samplers, Non-Color."""
    return _assign_bundled_texture(
        material, texture_path,
        node_names=(BUMP_SAMPLER_NODE, DIFFUSE_SAMPLER_NODE),
        colorspace='Non-Color',
    )


DAMAGE_SHADER_FILENAME = "decal_normal_only.sps"


MATERIAL_NAME = "seto_fakedamage"


# Taken from GTA's own damage strips (hn_apt_hall_blk_milo): the shader's stock
# values, with bumpiness dialled back to 0.5.
#
# specularIntensityMult is the one that matters. decal_normal_only carries no
# colour of its own - it only perturbs the surface normal - so what makes a
# crease readable is the light's response to that normal, and most of that
# response is specular. This used to be 0.0, which switched it off entirely and
# left the strip nearly invisible in game on softly lit interior walls, however
# strong the normal map was.
#
# Smooth Edge deliberately keeps its own set (SMOOTH_EDGE_VALUE_PARAMETERS) - it
# is a different effect, tuned separately.
VALUE_PARAMETERS = {
    "useTessellation": 0.0,
    "bumpiness": 0.50,
    "specularIntensityMult": 0.125,
    "specularFalloffMult": 100.00,
    "specularFresnel": 0.97,
}


_PARAMETER_NODE_IDNAME = "SOLLUMZ_NT_SHADER_Parameter"


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


def find_or_create_damage_material(texture_path=None, reuse=True):
    """Find a Fake Damage material to reuse, or create and configure a new one.

    Never invents a shader: decal_normal_only.sps is first confirmed to exist
    in Sollumz's currently mounted ShaderManager (from szio).

    DiffuseSampler / BumpSampler are filled from the normal map bundled with
    the add-on (fake_damage/textures/). Sollumz's own
    post_create_shader_add_default_images is still never called: it would drop a
    blank generated image into every *other* slot, and that blank exports as a
    real texture.

    Returns (material, missing_parameters, texture_warning). A reused material
    is left exactly as the user has it - neither its parameters nor its textures
    are rewritten - so hand tweaks survive.
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
            return existing, [], None

    material = shader_materials.create_shader(DAMAGE_SHADER_FILENAME)
    material.name = MATERIAL_NAME
    missing = apply_value_parameters(material)
    texture_warning = _assign_normal_map(material, texture_path)
    return material, missing, texture_warning


# ----------------------------------------------------- Fake AO material

FAKE_AO_MATERIAL_NAME = "seto_fakeao"


def _find_existing_fake_ao_material():
    """A Fake AO material we made earlier, or None.

    Name-scoped rather than shader-scoped. Matching on decal.sps alone - which
    is what this used to do - would happily adopt one of the Decal Tool's
    per-texture materials, since those use the same shader.
    """
    for mat in bpy.data.materials:
        if not (mat.name == FAKE_AO_MATERIAL_NAME
                or mat.name.startswith(FAKE_AO_MATERIAL_NAME + ".")):
            continue
        if not _is_shader_material(mat):
            continue
        if mat.shader_properties.filename == DECAL_SHADER_FILENAME:
            return mat
    return None


def find_or_create_fake_ao_material(texture_path=None, reuse=True):
    """Find a Fake AO material to reuse, or create and texture a new one.

    Never invents a shader: first confirms decal.sps exists in Sollumz's
    currently mounted ShaderManager (from szio), and raises SollumzShaderError
    with a clear message if not.

    DiffuseSampler is filled from the texture bundled with the add-on
    (fake_ao/textures/). decal.sps has no BumpSampler, so unlike Fake Damage and
    Smooth Edge only the one slot is set, and as sRGB rather than Non-Color -
    this is a colour texture, not a normal map.

    Returns (material, texture_warning). A reused material is left exactly as
    the user has it, so hand tweaks survive.
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
        existing = _find_existing_fake_ao_material()
        if existing is not None:
            return existing, None

    material = shader_materials.create_shader(DECAL_SHADER_FILENAME)
    material.name = FAKE_AO_MATERIAL_NAME
    texture_warning = _assign_bundled_texture(
        material, texture_path,
        node_names=(DIFFUSE_SAMPLER_NODE,),
        colorspace='sRGB',
    )
    return material, texture_warning


# ------------------------------------------------------ Smooth Edge material

SMOOTH_EDGE_SHADER_FILENAME = "decal_normal_only.sps"

# Named so it can be recognised for reuse later. Reuse is restricted to our own
# materials on purpose: matching on the shader filename alone would adopt - and
# then retexture - a decal_normal_only material the user set up by hand, or the
# one Fake Damage made.
SMOOTH_EDGE_MATERIAL_NAME = "seto_smoothedge"

# Same starting point as Fake Damage: this is the same shader doing the same
# job, a normal-map decal laid over an edge.
SMOOTH_EDGE_VALUE_PARAMETERS = {
    "useTessellation": 0.0,
    "bumpiness": 1.00,
    "specularIntensityMult": 0.00,
    "specularFalloffMult": 40.00,
    "specularFresnel": 0.75,
}


def _find_existing_smooth_edge_material():
    """A Smooth Edge material we made earlier, or None.

    Name-scoped rather than shader-scoped: Fake Damage uses the same shader, so
    matching on decal_normal_only.sps alone would let the two tools adopt - and
    retexture - each other's materials.
    """
    for mat in bpy.data.materials:
        if not (mat.name == SMOOTH_EDGE_MATERIAL_NAME
                or mat.name.startswith(SMOOTH_EDGE_MATERIAL_NAME + ".")):
            continue
        if not _is_shader_material(mat):
            continue
        if mat.shader_properties.filename == SMOOTH_EDGE_SHADER_FILENAME:
            return mat
    return None


def find_or_create_smooth_edge_material(texture_path=None, reuse=True):
    """Find a Smooth Edge material to reuse, or create and configure a new one.

    Never invents a shader: decal_normal_only.sps is first confirmed to exist in
    Sollumz's currently mounted ShaderManager (from szio).

    Unlike Fake Damage, the texture slots are filled in automatically from the
    normal map bundled with the add-on - that is the whole point of this tool
    being separate. Sollumz's own post_create_shader_add_default_images is still
    never called: it would drop a blank generated image into every *other* slot,
    and that blank exports as a real texture.

    Returns (material, missing_parameters, texture_warning). A reused material
    is left exactly as the user has it - neither its parameters nor its textures
    are rewritten - so hand tweaks survive.
    """
    try:
        shader_module = importlib.import_module("szio.gta5.shader")
    except ImportError as e:
        raise SollumzShaderError(f"Could not import szio.gta5.shader ({e}).")

    shader_materials = _import("ydr.shader_materials")

    if shader_module.ShaderManager.find_shader(SMOOTH_EDGE_SHADER_FILENAME) is None:
        raise SollumzShaderError(
            f"Shader '{SMOOTH_EDGE_SHADER_FILENAME}' was not found by Sollumz's ShaderManager."
        )

    if reuse:
        existing = _find_existing_smooth_edge_material()
        if existing is not None:
            return existing, [], None

    material = shader_materials.create_shader(SMOOTH_EDGE_SHADER_FILENAME)
    material.name = SMOOTH_EDGE_MATERIAL_NAME
    missing = apply_value_parameters(material, SMOOTH_EDGE_VALUE_PARAMETERS)
    texture_warning = _assign_normal_map(material, texture_path)
    return material, missing, texture_warning


# ---------------------------------------------------------------------------
# GTA lights (Lighting > GTA Light)
# ---------------------------------------------------------------------------
#
# Sollumz's light data model is the source of truth here. Every name below was
# read from the installed Sollumz source, not invented:
#
#   sollumz_properties.py    LightType, SollumType, SOLLUMZ_UI_NAMES
#   ydr/properties.py        LightProperties / LightFlags / LightTimeFlags,
#                            registered onto bpy.types.Light
#   ydr/lights.py            export_light(), which .ydr / .yft / .ytyp export
#                            actually calls
#   ydr/operators/lights.py  SOLLUMZ_OT_create_light, mirrored by create_gta_light
#   ydr/gta5/presets/light.py + shared/presets/store.py   the preset system
#
# THE RULE: GTA light values are read and written only through
# `light_data.light_properties`, `.light_flags`, `.time_flags` and
# `.sollum_type`. Sollumz stores seven GTA values *inside* Blender-native light
# fields through get/set wrapper properties:
#
#   intensity        <-> energy / 500        falloff          <-> cutoff_distance
#   falloff_exponent <-> shadow_soft_size*5  volume_intensity <-> volume_factor
#   cone_outer_angle <-> spot_size / 2       shadow_near_clip <-> shadow_buffer_clip_start
#   cone_inner_angle <-> spot_blend
#
# Writing those native fields directly would silently reinterpret GTA data, so
# no Seto code ever touches them.


def get_light_type_enum():
    """Sollumz's LightType enum (sollumz_properties.LightType)."""
    return _import("sollumz_properties").LightType


def get_sollum_type_enum():
    """Sollumz's SollumType enum (sollumz_properties.SollumType)."""
    return _import("sollumz_properties").SollumType


def get_ui_names():
    """Sollumz's SOLLUMZ_UI_NAMES mapping (enum member -> display name)."""
    return _import("sollumz_properties").SOLLUMZ_UI_NAMES


def is_gta_light(obj):
    """True if `obj` is a Sollumz GTA light that export will pick up.

    Mirrors the filter Sollumz's exporter uses (ydr/lights.py:export_lights):
    a LIGHT object whose light data-block has a sollum_type other than NONE.
    The object-level sollum_type is checked too, since that is what Sollumz's
    own light panels and gizmos poll on.
    """
    if obj is None or obj.type != "LIGHT" or obj.data is None:
        return False
    try:
        SollumType = get_sollum_type_enum()
        LightType = get_light_type_enum()
    except Exception:
        return False
    return (getattr(obj, "sollum_type", None) == SollumType.LIGHT
            and getattr(obj.data, "sollum_type", None) != LightType.NONE)


def create_gta_light(context, light_type_value, location=None):
    """Create a Sollumz-compatible GTA light and return the new object.

    Mirrors Sollumz's own SOLLUMZ_OT_create_light.run() step for step, so the
    result is indistinguishable from a light made with Sollumz's Create Light
    button:

      1. bpy.data.lights.new() with the Blender light type Sollumz uses ("SPOT"
         for Spot, "POINT" otherwise - a Capsule is a POINT lamp whose
         `is_capsule` flag is set by Sollumz's sollum_type setter).
      2. Assign `sollum_type`, whose Sollumz-side setter derives light.type and
         light.is_capsule.
      3. create_blender_object(SollumType.LIGHT, ...) so the object gets the
         object-level sollum_type and is linked to the right collection.
      4. Parent into the active Drawable hierarchy when there is one.
      5. Seed with the "Default" light preset if Sollumz has one.

    `light_type_value` is a LightType *value* string, e.g. "sollumz_light_spot".
    """
    LightType = get_light_type_enum()
    SollumType = get_sollum_type_enum()
    ui_names = get_ui_names()
    blenderhelper = _import("tools.blenderhelper")

    light_type = LightType(light_type_value)
    name = ui_names.get(light_type, "Light")

    blender_light_type = "SPOT" if light_type == LightType.SPOT else "POINT"

    light_data = bpy.data.lights.new(name=name, type=blender_light_type)
    light_data.sollum_type = light_type
    light_obj = blenderhelper.create_blender_object(SollumType.LIGHT, name, light_data)

    active_obj = context.active_object
    target_loc = location if location is not None else context.scene.cursor.location

    if active_obj is not None and getattr(active_obj, "sollum_type", None) in (
        SollumType.DRAWABLE_MODEL,
        SollumType.DRAWABLE,
    ):
        light_obj.parent = (active_obj.parent
                            if active_obj.sollum_type == SollumType.DRAWABLE_MODEL
                            else active_obj)
        light_obj.matrix_world.translation = target_loc
    else:
        light_obj.location = target_loc

    apply_default_light_preset(light_data)

    return light_obj


def _get_light_preset_modules():
    """Return (preset light module, preset store module), or (None, None) when
    the installed Sollumz has no preset system."""
    try:
        light_presets = _import("ydr.gta5.presets.light")
        store = _import("shared.presets.store")
    except Exception:
        return None, None
    if not hasattr(light_presets, "LIGHT_PRESET_CATEGORY"):
        return None, None
    return light_presets, store


def apply_default_light_preset(light_data):
    """Apply Sollumz's "Default" light preset, exactly as Sollumz's own create
    operator does. No-op when the preset system or that preset is missing."""
    light_presets, store = _get_light_preset_modules()
    if light_presets is None:
        return False
    category = light_presets.LIGHT_PRESET_CATEGORY
    try:
        preset = store.find_preset(category, "Default")
        if preset is None:
            return False
        category.apply(light_data, preset.get("data", {}))
    except Exception:
        return False
    return True


def has_light_property(light_data, prop_name):
    """True if Sollumz's LightProperties on this light really has `prop_name`.

    Lets the panel degrade gracefully instead of raising if a future Sollumz
    renames or drops a property.
    """
    light_props = getattr(light_data, "light_properties", None)
    if light_props is None:
        return False
    return prop_name in light_props.bl_rna.properties


def get_flag_names(flags_group):
    """Flag property names of a Sollumz FlagPropertyGroup, in Sollumz's order."""
    try:
        return list(flags_group.get_flag_names())[:flags_group.size]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# YTYP archetype extensions (Lighting > God Rays)
# ---------------------------------------------------------------------------
#
# A god ray is three pieces of data living in two different export files, which
# is the single most important thing to understand about this section:
#
#   Spot Light    a real Blender LIGHT object inside the Drawable hierarchy.
#                 Exported to .ydr by ydr/lights.py:export_lights(), which walks
#                 parent_obj.children_recursive. Handled by create_gta_light()
#                 above.
#
#   Light Shaft   a CExtensionDefLightShaft, and
#   Particle      a CExtensionDefParticleEffect,
#                 both of which are NOT scene objects. They are entries in
#                 scene.ytyps[i].archetypes[j].extensions[k] and are exported to
#                 .ytyp by ytyp/ytypexport.py:create_extension(). What you see in
#                 the viewport is a gizmo (ytyp/gizmos/extensions.py), not an
#                 object you can select or parent.
#
# Everything below was read from the installed Sollumz source:
#
#   ytyp/properties/extensions.py  ExtensionType, ExtensionsContainer,
#                                  LightShaftExtensionProperties,
#                                  ParticleExtensionProperties
#   ytyp/properties/ytyp.py        CMapTypesProperties, ArchetypeProperties.asset
#   ytyp/operators/extensions.py   the corner/direction update operators whose
#                                  maths the god ray sync mirrors
#   ytyp/ytypexport.py             get_extension_props(), which is annotation
#                                  driven - it reads the *szio* class annotations
#                                  and pulls same-named attributes off the
#                                  Blender PropertyGroup
#
# TWO RULES follow from that exporter being annotation driven:
#
#   1. Only values written onto Sollumz's own PropertyGroups are exported.
#      A property Seto invents is invisible to the exporter.
#   2. Extension coordinates (offset_position, cornerA..D, direction) are in the
#      archetype ASSET's local space, not world space and not light space. Every
#      write here expects caller-supplied asset-local vectors.
#
# One Blender quirk this section defends against throughout: adding to a
# CollectionProperty can re-allocate it, invalidating any PropertyGroup
# reference taken beforehand. Sollumz notes this in duplicate_selected_extension
# and it can crash Blender, so extensions are always re-fetched by index after a
# structural change and are looked up by name rather than by a cached reference.


class ArchetypeNotFoundError(Exception):
    """The object has no YTYP archetype to attach extensions to.

    Carries `drawable` (the object that was checked, or None) so the caller can
    name the offender in its error message.
    """

    def __init__(self, message, drawable=None):
        super().__init__(message)
        self.drawable = drawable


def get_extension_type_enum():
    """Sollumz's ExtensionType enum (ytyp.properties.extensions.ExtensionType)."""
    return _import("ytyp.properties.extensions").ExtensionType


def get_light_shaft_enums():
    """(LightShaftDensityType, LightShaftVolumeType) from Sollumz."""
    extensions = _import("ytyp.properties.extensions")
    return extensions.LightShaftDensityType, extensions.LightShaftVolumeType


def get_particle_fx_type_enum():
    """Sollumz's ParticleFxType enum (AMBIENT is 0, the god ray default)."""
    return _import("ytyp.properties.extensions").ParticleFxType


def find_archetypes_for_object(obj):
    """Every (ytyp, archetype) pair in the scene whose asset is `obj`.

    Searches all YTYPs, not just the selected one: which YTYP happens to be
    selected in Sollumz's panel is a UI detail and must not change what the
    god ray tool attaches to. Returns a list so the caller can distinguish
    "none" from "ambiguous".
    """
    matches = []
    for ytyp in bpy.context.scene.ytyps:
        for archetype in ytyp.archetypes:
            if archetype.asset is not None and archetype.asset == obj:
                matches.append((ytyp, archetype))
    return matches


def resolve_archetype_target(obj):
    """Resolve the (drawable, ytyp, archetype) a god ray on `obj` belongs to.

    Raises ArchetypeNotFoundError with a message written for the user - not a
    stack trace - for each of the three distinct ways this can fail. The
    operator is all-or-nothing, so it calls this *before* creating anything and
    cancels cleanly on failure rather than leaving a half-built setup behind.
    """
    drawable = find_drawable_parent(obj)
    if drawable is None:
        raise ArchetypeNotFoundError(
            f"'{obj.name}' is not inside a Sollumz Drawable. God Ray extensions are "
            f"YTYP archetype data, so the geometry must belong to a Drawable that an "
            f"archetype points at. Put it in a Drawable first, then run Create God Rays "
            f"again.",
            drawable=None,
        )

    matches = find_archetypes_for_object(drawable)

    if not matches:
        raise ArchetypeNotFoundError(
            f"Drawable '{drawable.name}' has no valid archetype/YTYP. God Ray extensions "
            f"cannot be created safely. Create or assign an archetype first, then run "
            f"Create God Rays again.",
            drawable=drawable,
        )

    if len(matches) > 1:
        where = ", ".join(f"{y.name}/{a.name}" for y, a in matches)
        raise ArchetypeNotFoundError(
            f"Drawable '{drawable.name}' is the asset of {len(matches)} archetypes "
            f"({where}). Seto cannot tell which one the God Ray belongs to. Leave it "
            f"assigned to a single archetype and run Create God Rays again.",
            drawable=drawable,
        )

    ytyp, archetype = matches[0]
    return drawable, ytyp, archetype


def find_extension_by_name(archetype, name):
    """(index, extension) of the archetype extension called `name`, else (None, None).

    Lookup is by name on every access rather than by a stored index, because an
    index goes stale as soon as any extension is added or removed - including by
    the user, in Sollumz's own panel.
    """
    for i, ext in enumerate(archetype.extensions):
        if ext.name == name:
            return i, ext
    return None, None


def _add_extension(archetype, name, ext_type):
    """Add an extension of `ext_type` named `name`, and return (index, extension).

    Uses Sollumz's ExtensionsContainer.new_extension(), which is also what seeds
    a new light shaft's corners, length and direction so its gizmo is visible
    immediately.
    """
    archetype.new_extension(ext_type)
    index = len(archetype.extensions) - 1
    # Re-fetch by index: new_extension() may have re-allocated the collection.
    ext = archetype.extensions[index]
    ext.name = name
    return index, ext


def add_light_shaft_extension(archetype, name):
    """Create a CExtensionDefLightShaft on `archetype`. Returns (index, extension).

    Only creates and names it; the god ray's geometry (corners, direction,
    length) and look (colour, intensity, flags) are written by the caller, which
    is the only place that knows the opening it was built from.
    """
    ExtensionType = get_extension_type_enum()
    return _add_extension(archetype, name, ExtensionType.LIGHT_SHAFT)


def add_particle_extension(archetype, name, fx_name="amb_dust_motes"):
    """Create a CExtensionDefParticleEffect on `archetype`. Returns (index, extension).

    `fx_name` must exist in the ENTITYFX_AMBIENT_PTFX block of entityfx.dat for
    the target build. Neither Sollumz nor Seto can validate that - a name that is
    not there exports fine and simply does nothing in game.
    """
    ExtensionType = get_extension_type_enum()
    ParticleFxType = get_particle_fx_type_enum()
    index, ext = _add_extension(archetype, name, ExtensionType.PARTICLE)
    props = ext.get_properties()
    props.fx_name = fx_name
    props.fx_type = ParticleFxType.AMBIENT.value
    return index, ext


def duplicate_extension(archetype, source_name, new_name):
    """Deep-copy the extension called `source_name` and rename the copy.

    Returns (index, extension), or (None, None) if the source is missing.

    Wraps Sollumz's ExtensionsContainer.duplicate_selected_extension(), which
    copies nested PropertyGroups properly. That method works on the *selected*
    extension, so the selection index is moved to the source first and restored
    afterwards, leaving the user's selection where they left it.
    """
    index, _ = find_extension_by_name(archetype, source_name)
    if index is None:
        return None, None

    previous_index = archetype.extension_index
    archetype.extension_index = index
    try:
        archetype.duplicate_selected_extension()
        new_index = len(archetype.extensions) - 1
        # Re-fetch by index: the collection was just re-allocated.
        new_ext = archetype.extensions[new_index]
        new_ext.name = new_name
    finally:
        archetype.extension_index = min(previous_index, len(archetype.extensions) - 1)

    return new_index, new_ext


def remove_extension_by_name(archetype, name):
    """Remove the extension called `name`. Returns True if one was removed.

    This is what makes Create God Rays all-or-nothing: if a later step fails,
    the operator removes whatever it already added so the user is never left
    with a partial setup to clean up by hand.
    """
    index, _ = find_extension_by_name(archetype, name)
    if index is None:
        return False
    archetype.extensions.remove(index)
    if archetype.extension_index >= len(archetype.extensions):
        archetype.extension_index = max(len(archetype.extensions) - 1, 0)
    return True


def tag_redraw_ytyp(context):
    """Redraw the panels that show archetype extensions.

    Writing to scene.ytyps does not dirty the UI on its own, so Sollumz's own
    extension operators call this; without it the new god ray extension does not
    appear in Sollumz's list until the user clicks something.
    """
    try:
        blenderhelper = _import("tools.blenderhelper")
    except SollumzUnavailableError:
        return
    for region_type in ("UI", "TOOL_PROPS", "TOOL_HEADER"):
        blenderhelper.tag_redraw(context, space_type="VIEW_3D", region_type=region_type)
