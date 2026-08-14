"""The glow plane's own settings, and the rebuild they drive.

A Sign Glow is one quad carrying a generated texture, sitting behind the
lettering it was built from. Every setting on it is live: change Halo Size and
the texture is regenerated and the quad resized to fit the wider bloom, in
place, without touching the letters.

Three things here are not obvious:

* **The source mesh is never modified** - the rule this add-on keeps
  everywhere. The letters are read (evaluated, in world space, so modifiers
  and scale count) and nothing else.
* **No `bpy.ops`.** These run from property callbacks, where operators are not
  safe. Meshes are built with bmesh and swapped in through the data API.
* **The plane's geometry is local and its rotation lives in the matrix.** It
  would be simpler to build the quad from world-space corners and leave the
  object at the origin, and it would also mean the transform gizmo pointed
  along the world axes while the sign sat at 40 degrees on a wall. Built this
  way, the quad's own axes are the sign's, so dragging it along Z moves it up
  the sign rather than up the map.

The rebuild is **debounced**: a slider fires its callback on every mouse move,
and rasterising a few thousand triangles per move is a drag that stutters.
The callback marks the object and arms a short timer; the rebuild runs once,
when the hand stops. Background Blender has no event loop, so tests take the
immediate path.
"""

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

from . import geometry
from . import properties
from ..decal_tool import geometry as decal_geometry
from ..shared import dds
from ..shared import manual_offset
from ..shared import sollumz_integration as szi
from ..shared import vertex_color

# The objects this glow was built from, by name, as an ID property. A
# CollectionProperty of pointers would be tidier, but this has to survive being
# appended into another file, and names are what survive that.
SOURCE_NAMES_KEY = "seto_sign_glow_sources"
# The generated image's datablock name, so a rebuild replaces its own texture
# rather than filling the file with orphans.
IMAGE_NAME_KEY = "seto_sign_glow_image"

# Guard against a rebuild's own property writes coming back round as callbacks.
_rebuilding = False


def is_rebuilding():
    return _rebuilding


def source_objects(glow):
    """The lettering this glow belongs to: the pointer, plus any extra sources."""
    found = []
    for name in list(glow.get(SOURCE_NAMES_KEY, [])):
        obj = bpy.data.objects.get(name)
        if obj is not None and obj not in found:
            found.append(obj)
    pointer = glow.seto_sign_glow_data.source_object
    if pointer is not None and pointer not in found:
        found.append(pointer)
    return [obj for obj in found if obj.type == 'MESH']


def gather_triangles(objects, depsgraph):
    """World-space triangles of every source, and their area-weighted normal.

    Evaluated, so a sign built with a Solidify or an Array is measured as what
    it actually looks like. Area weighting is what keeps a bevel's many small
    side faces from out-voting the one big face that points at the viewer.
    """
    triangles = []
    normal_accumulator = Vector((0.0, 0.0, 0.0))
    for obj in objects:
        if obj.type != 'MESH':
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            matrix = evaluated.matrix_world
            normal_matrix = matrix.to_3x3()
            for tri in mesh.loop_triangles:
                triangles.append([matrix @ mesh.vertices[i].co for i in tri.vertices])
                normal_accumulator += (normal_matrix @ tri.normal) * tri.area
        finally:
            evaluated.to_mesh_clear()
    return triangles, normal_accumulator


def _store_image(name, pixels):
    """Put the halo into an image datablock, reusing the one we made last time.

    Reused by name and resized only when the shape actually changed, so the
    material's image node keeps pointing at the same datablock across a slider
    drag - repointing it every rebuild is how a live tool ends up with two
    hundred images called `sign_glow_001_tex.043`.
    """
    height, width = pixels.shape[:2]
    image = bpy.data.images.get(name)
    if image is not None and tuple(image.size) != (width, height):
        bpy.data.images.remove(image)
        image = None
    if image is None:
        image = bpy.data.images.new(name, width, height, alpha=True)
    image.pixels.foreach_set(np.ascontiguousarray(pixels).ravel())
    image.update()
    if not image.filepath:
        # Packed, so the .blend can be handed to someone else and still show
        # the halo - and packed *again* on every rebuild, because the packed
        # bytes are a snapshot: writing new pixels does not update them, and a
        # .blend saved after a slider drag would carry the halo from before it.
        # Asked of the filepath rather than of `source`, which packing sets to
        # 'FILE' whether or not there is a file. Once Export has written a
        # .dds there is one, and packing over it would undo that.
        image.pack()
    return image


def _refresh_dds(image):
    """Keep the .dds on disk equal to the halo you are looking at.

    Once a glow carries a Sollumz shader its texture is a **file**, not a
    packed datablock - that is what Sollumz embeds on export. But every slider
    here regenerates the pixels, so without this the file would freeze at
    whatever the halo looked like the moment the material was made, and the
    sign in game would be a version of itself nobody ever chose. The rebuild is
    debounced, so this costs one file write when the hand stops, not one per
    mouse move.

    Returns a sentence for the panel if the write failed, or None. A failure
    here is not a failed rebuild: what is on screen is still correct, and it is
    the copy on disk that is behind.
    """
    if not image.filepath:
        return None
    path = bpy.path.abspath(image.filepath)
    if not path.lower().endswith(".dds"):
        return None
    try:
        dds.write_image(image, path)
    except OSError as error:
        return f"The halo is up to date here, but its .dds could not be written: {error}"
    return None


def _write_attributes(mesh, loop_uv, loop_rgba):
    """UVMap 0 and Color 1, through Sollumz when it is there and by hand when not.

    Sollumz's own helpers are the right answer - they pick the type, domain and
    naming the exporter expects - but Sign Glow's preview half works on a
    machine with no Sollumz at all, and refusing to build a quad because of it
    would be refusing to run the tool.
    """
    if szi.is_sollumz_available():
        szi.write_uv_and_color(mesh, loop_uv, loop_rgba)
        return
    uv_layer = mesh.uv_layers.new(name=szi.get_uv_map_name(0))
    uv_layer.data.foreach_set('uv', [value for pair in loop_uv for value in pair])
    colour = mesh.color_attributes.new(name=szi.get_color_attr_name(0),
                                       type='BYTE_COLOR', domain='CORNER')
    colour.data.foreach_set('color', [value for rgba in loop_rgba for value in rgba])


def _plane_mesh(name, width, height, edge_fade):
    """The glow's plane: a bordered grid in local space, facing +Z.

    Not a single quad, and the reason is the border. `Color 1`'s alpha is what
    the emissive shader blends by, so a quad whose four corners are all 1.0
    ends at a hard line: the halo's own texture fades out, but the surface it
    is on does not, and in game that reads as a rectangle of slightly-lit air
    around the sign. A ring of alpha-0 vertices around an alpha-1 middle makes
    the plane itself fade out with its texture.

    This is the same grid the Decal Tool builds, imported rather than copied -
    it is pure geometry with no `bpy` in it, and a second implementation of a
    bordered quad would drift from the first the day either was fixed.
    """
    verts, faces, uvs, is_border = decal_geometry.decal_grid(
        width, height, edge_fade)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    loop_uv = decal_geometry.per_loop(faces, uvs)
    alphas = decal_geometry.vertex_alphas(
        is_border, vertex_color.DEFAULT_ALPHA_CENTER,
        decal_geometry.DEFAULT_BORDER_ALPHA)
    loop_rgba = [(*vertex_color.DEFAULT_RGB, alpha)
                 for alpha in decal_geometry.per_loop(faces, alphas)]
    _write_attributes(mesh, loop_uv, loop_rgba)
    return mesh


def _retexture(glow, image):
    """Point whatever material the glow is wearing at the new image.

    Both the preview material and a Sollumz emissive one are handled by the
    same two lines, because both read the halo out of an image node. A material
    the user swapped in themselves is treated the same way rather than being
    replaced - this tool generates a texture, it does not own the shading.
    """
    for slot in glow.material_slots:
        material = slot.material
        if material is None or not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE':
                node.image = image


def rebuild(glow, depsgraph=None):
    """Regenerate this glow's texture and plane. Returns a status, or None.

    The status is a sentence for the panel, not an exception: this runs from
    property callbacks, where there is no status bar and nowhere for a
    traceback to go that the user would ever see.
    """
    global _rebuilding
    data = glow.seto_sign_glow_data
    sources = source_objects(glow)
    if not sources:
        return "No source lettering - pick it in the From field."
    for source in sources:
        if source.mode == 'EDIT':
            return f"'{source.name}' is in Edit Mode - leave it to rebuild."

    if depsgraph is None:
        depsgraph = bpy.context.evaluated_depsgraph_get()

    _rebuilding = True
    try:
        triangles, normal_accumulator = gather_triangles(sources, depsgraph)
        if not triangles:
            return "The source has no faces to trace."

        forward, u, v = geometry.projection_basis(normal_accumulator,
                                                  sources[0].matrix_world)
        # Auto Fit sizes the margin from the halo itself: the bloom is what
        # decides how much room the plane needs, and a fixed pad either clips
        # a wide halo or leaves a wide transparent border on a tight one.
        padding = (data.halo_size * 1.6 + 0.02) if data.auto_fit else data.padding
        mask, (x0, y0, x1, y1), nearest = geometry.rasterize(
            triangles, u, v, forward, int(data.resolution), padding)
        pixels = geometry.halo_from_mask(
            mask, data.core_size, data.core_intensity, data.halo_size,
            data.halo_intensity, data.color[3], data.color)

        image = _store_image(glow.get(IMAGE_NAME_KEY, glow.name + "_tex"), pixels)
        glow[IMAGE_NAME_KEY] = image.name
        warning = _refresh_dds(image)

        old_mesh = glow.data
        materials = list(old_mesh.materials)
        width, height = x1 - x0, y1 - y0
        # The border is a fraction of the plane rather than a distance, so a
        # shop sign and a rooftop sign fade over the same *proportion* of
        # themselves instead of the small one being all border.
        mesh = _plane_mesh(old_mesh.name, width, height,
                           data.edge_fade * min(width, height))
        for material in materials:
            mesh.materials.append(material)
        glow.data = mesh
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

        centre = u * ((x0 + x1) * 0.5) + v * ((y0 + y1) * 0.5)
        depth = forward * (nearest - data.offset_behind)
        rotation = Matrix(((u.x, v.x, forward.x),
                           (u.y, v.y, forward.y),
                           (u.z, v.z, forward.z))).to_4x4()
        glow.matrix_world = Matrix.Translation(centre + depth) @ rotation
        # Last, always: a hand-placed glow is remembered rather than derived,
        # and anything after this would recompute the location it just set.
        manual_offset.apply(glow, data)

        _retexture(glow, image)
        return warning
    finally:
        _rebuilding = False


# ---- live-update debounce ----------------------------------------------

_pending = set()
_timer_armed = False
_DEBOUNCE_S = 0.25


def _flush_pending():
    global _timer_armed
    _timer_armed = False
    names = list(_pending)
    _pending.clear()
    for name in names:
        glow = bpy.data.objects.get(name)
        if glow is None or not glow.seto_sign_glow_data.is_sign_glow:
            continue
        # A rebuild that raises must not take the timer system down with it;
        # what went wrong goes on the panel, where the user is looking.
        try:
            glow.seto_sign_glow_data.status = rebuild(glow) or ""
        except Exception as error:
            import traceback
            traceback.print_exc()
            glow.seto_sign_glow_data.status = f"{type(error).__name__}: {error}"
    return None  # one shot


def _on_setting_changed(self, _context):
    if _rebuilding or not self.live_update:
        return
    glow = self.id_data
    if not isinstance(glow, bpy.types.Object) or not self.is_sign_glow:
        return
    if bpy.app.background:
        self.status = rebuild(glow) or ""
        return
    global _timer_armed
    _pending.add(glow.name)
    if not _timer_armed:
        _timer_armed = True
        bpy.app.timers.register(_flush_pending, first_interval=_DEBOUNCE_S)


PREVIEW_MATERIAL_SUFFIX = "_preview"


def build_preview_material(name, image, strength):
    """The viewport material: emission masked by the halo's own alpha.

    Plain Blender nodes, not a Sollumz shader, and that is the point - the glow
    is worth looking at before anyone decides to export it, and on a machine
    with no Sollumz this is the whole tool. Export replaces it.
    """
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    output.location = (500, 0)
    mix = tree.nodes.new("ShaderNodeMixShader")
    mix.location = (280, 0)
    transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
    transparent.location = (60, 120)
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.location = (60, -80)
    emission.inputs["Strength"].default_value = strength
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.location = (-260, 0)
    texture.image = image
    # EXTEND, not REPEAT: the halo fades to nothing at the border, and a tiled
    # one puts a second sign's bloom just off the edge of this one.
    texture.extension = 'EXTEND'
    tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
    tree.links.new(texture.outputs["Alpha"], mix.inputs["Fac"])
    tree.links.new(transparent.outputs["BSDF"], mix.inputs[1])
    tree.links.new(emission.outputs["Emission"], mix.inputs[2])
    tree.links.new(mix.outputs["Shader"], output.inputs["Surface"])
    # Blender renamed these between versions and Sollumz-era files see both;
    # whichever exists is set, and a missing one is not an error.
    for attribute, value in (("blend_method", 'BLEND'),
                             ("surface_render_method", 'BLENDED'),
                             ("shadow_method", 'NONE')):
        if hasattr(material, attribute):
            try:
                setattr(material, attribute, value)
            except (AttributeError, TypeError):
                pass
    return material


def _on_preview_strength(self, _context):
    """Turn the preview up without regenerating anything.

    Brightness is a node value, not a pixel: rebuilding the texture to change
    it would be a second of work for a number that is already correct.
    """
    glow = self.id_data
    if not isinstance(glow, bpy.types.Object):
        return
    for slot in glow.material_slots:
        material = slot.material
        if material is None or not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            if node.type == 'EMISSION':
                node.inputs["Strength"].default_value = self.preview_strength


def _object_annotations():
    annotations = dict(properties.annotations(update=_on_setting_changed))
    annotations.update(manual_offset.annotations())
    annotations.update({
        "is_sign_glow": bpy.props.BoolProperty(default=False, options={'HIDDEN'}),
        "source_object": bpy.props.PointerProperty(
            name="Source",
            description="The lettering this halo is traced from",
            type=bpy.types.Object,
            poll=lambda self, obj: obj.type == 'MESH',
            update=_on_setting_changed,
        ),
        # Read by shared/panel_layout.object_header, like every other tool's.
        "status": bpy.props.StringProperty(default="", options={'HIDDEN'}),
        "live_update": bpy.props.BoolProperty(
            name="Live Update",
            description="Regenerate the halo as these settings change",
            default=True,
        ),
        "auto_fit": bpy.props.BoolProperty(
            name="Auto Fit",
            description="Size the plane from the halo itself, so the bloom is "
                        "never clipped and never floats in a wide empty border",
            default=True,
            update=_on_setting_changed,
        ),
        "edge_fade": bpy.props.FloatProperty(
            name="Edge Fade",
            description="How far in from the plane's border its Color 1 alpha "
                        "climbs from 0 to 1, as a fraction of the shorter side. "
                        "The alpha is what the emissive shader blends by, so "
                        "this is what stops the plane ending on a visible line",
            default=0.08, min=0.0, max=0.45,
            update=_on_setting_changed,
        ),
        "padding": bpy.props.FloatProperty(
            name="Padding",
            description="Margin around the lettering, as a fraction of its longer side",
            default=0.12, min=0.02, max=0.5,
            update=_on_setting_changed,
        ),
        "offset_behind": bpy.props.FloatProperty(
            name="Offset Behind",
            description="How far the plane sits behind the frontmost letter",
            default=0.02, min=0.001, soft_max=0.5, precision=3,
            subtype='DISTANCE',
            update=_on_setting_changed,
        ),
        "core_size": bpy.props.FloatProperty(
            name="Core Size",
            description="The tight glow hugging the letters, as a fraction of "
                        "the texture's longer side",
            default=0.015, min=0.002, max=0.15,
            update=_on_setting_changed,
        ),
        "core_intensity": bpy.props.FloatProperty(
            name="Core Intensity", default=1.0, min=0.0, max=2.0,
            update=_on_setting_changed,
        ),
        "halo_size": bpy.props.FloatProperty(
            name="Halo Size",
            description="The wide bloom behind the letters",
            default=0.08, min=0.01, max=0.4,
            update=_on_setting_changed,
        ),
        "halo_intensity": bpy.props.FloatProperty(
            name="Halo Intensity", default=0.55, min=0.0, max=2.0,
            update=_on_setting_changed,
        ),
        "preview_strength": bpy.props.FloatProperty(
            name="Preview Strength",
            description="Emission strength of the viewport preview material. "
                        "Viewport only - it is not exported and the game never sees it",
            default=3.0, min=0.1, max=20.0,
            update=_on_preview_strength,
        ),
        "shader_name": bpy.props.StringProperty(
            name="Shader",
            description="The Sollumz emissive shader Export asks for. If your "
                        "Sollumz does not have it, the next one that exists is used",
            default="emissive_additive_alpha.sps",
        ),
    })
    return annotations


class SETO_PG_sign_glow_data(bpy.types.PropertyGroup):
    __annotations__ = _object_annotations()


def register():
    bpy.utils.register_class(SETO_PG_sign_glow_data)
    bpy.types.Object.seto_sign_glow_data = bpy.props.PointerProperty(
        type=SETO_PG_sign_glow_data)


def unregister():
    del bpy.types.Object.seto_sign_glow_data
    bpy.utils.unregister_class(SETO_PG_sign_glow_data)
