"""The dirt shell: a separate mesh floating just above the painted surface.

This is the whole trick, and it is the same one GTA itself uses for grime: the
wall is never touched. START PAINT spawns a copy of the wall's surface, packs
it with extra vertices (paint resolution lives in vertex density, so the shell
is deliberately denser than the wall), floats it a few millimetres off the
surface, and gives it a Sollumz decal.sps material.

decal.sps reads Color 1's *alpha* as its blend factor - that is Sollumz's own
node wiring, not ours - so painting alpha is painting visibility:

    alpha 0.0   invisible, clean wall
    alpha 1.0   full dirt texture

The brush therefore paints with ADD_ALPHA / ERASE_ALPHA, and everything the
shell carries is data Sollumz exports: Color 1, UVMap 0, a decal.sps material.
Deleting the shell deletes the dirt; the wall never changed.

The shell's mesh carries exactly the data GTA reads - "Color 1" and "UVMap 0",
nothing else in either list. The bookkeeping the sliders need lives in runtime
caches in this module instead of on the mesh:

    base UVs        pristine copy of the shell's UVs, so Scale/Offset/Rotation
                    recompute UVMap 0 losslessly. After a file reload it is
                    reconstructed by inverting the last applied transform
                    (remembered in an object custom property), which is exact.
    raw alpha       the strokes at full strength, so the Opacity slider is
                    lossless. After a reload it is rebuilt from alpha divided
                    by the remembered opacity; only if the file was saved at an
                    opacity under 0.25 does byte rounding cost precision.
"""

import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.interpolate import poly_3d_calc

from ..shared import sollumz_integration as szi
from ..shared import vertex_color

# Object custom property marking a shell, holding the wall's name.
MARKER = "seto_dirt_shell_of"

TEXTURE_KEY = "seto_dirt_texture"
LAYER_KEY = "seto_dirt_layer"

COLOR_ATTR = "Color 1"
UV_ATTR = "UVMap 0"

# Earlier versions stored the slider bookkeeping as mesh layers with these
# names. adopt() migrates them into the runtime caches and removes them, so a
# shell built before this change loses the clutter the first time it is used.
LEGACY_BASE_UV_ATTR = "SetoBaseUV"
LEGACY_CACHE_ATTR = "SetoPaintCache"

# Runtime caches, keyed by mesh name. Rebuilt on demand (see the module
# docstring), so losing them to a restart costs nothing but a reconstruction.
_base_uv = {}
_alpha_raw = {}

# Where the last applied UV transform is remembered, for reconstructing the
# base UVs after the runtime cache is gone.
_PREV_UV_KEY = "seto_prev_uv_transform"

# Hard ceiling on shell vertices, whatever the spacing setting says - a paint
# helper must never be the heaviest object in the scene.
_VERTEX_BUDGET = 4000

# Below this opacity the byte-quantised alpha is too coarse to reconstruct the
# original strokes from, so the cache is only refreshed above it.
_CACHE_REFRESH_FLOOR = 0.25
_PREV_OPACITY_KEY = "seto_prev_dirt_opacity"


class ShellError(Exception):
    """The shell cannot be built on this object."""


def is_shell(obj):
    return obj is not None and MARKER in obj


def wall_of(obj):
    """The wall a shell belongs to, or None if it went away."""
    if not is_shell(obj):
        return None
    return bpy.data.objects.get(obj[MARKER])


def find_shells(wall):
    """Every dirt shell on `wall`, bottom layer first.

    A wall can carry several: one per texture, each painted independently, so
    concrete grime and a dirt pass over it are separate layers rather than one
    shell whose texture keeps changing under the paint.

    Shells in no collection are skipped: that is what a shell the user deleted
    with X looks like (the datablock lingers because the session's pointer
    property still holds it), and resurrecting a ghost the user deliberately
    deleted - or trying to select it, which raises - is exactly wrong.
    """
    found = {}
    # Children first only because shells made by older versions were parented;
    # new ones are found by the marker scan below.
    for child in wall.children:
        if is_shell(child) and child[MARKER] == wall.name and child.users_collection:
            found[child.name] = child
    for obj in bpy.data.objects:
        if is_shell(obj) and obj[MARKER] == wall.name and obj.users_collection:
            found.setdefault(obj.name, obj)
    return sorted(found.values(), key=layer_index)


def find_shell(wall):
    """The wall's bottom shell, or None. Convenience for single-layer walls."""
    shells = find_shells(wall)
    return shells[0] if shells else None


def find_by_texture(wall, texture_stem):
    """The layer already painting this texture, or None."""
    for candidate in find_shells(wall):
        if candidate.get(TEXTURE_KEY, "") == texture_stem:
            return candidate
    return None


def layer_index(shell):
    return int(shell.get(LAYER_KEY, 0))


def texture_stem_of(shell):
    return shell.get(TEXTURE_KEY, "")


def purge_orphans(wall):
    """Delete lingering unlinked shells of `wall`. Returns how many.

    Only called from operators - never from panel draw, where removing
    datablocks mid-redraw is unsafe.
    """
    ghosts = [obj for obj in bpy.data.objects
              if is_shell(obj) and obj[MARKER] == wall.name
              and not obj.users_collection]
    for ghost in ghosts:
        mesh = ghost.data
        bpy.data.objects.remove(ghost)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return len(ghosts)


def resolve(obj):
    """(wall, shell) for whichever of the two the user has selected."""
    if is_shell(obj):
        return wall_of(obj), obj
    return obj, find_shell(obj)


# ------------------------------------------------------------------- creation

def create(wall, texture_stem, texture_path, spacing=0.35, surface_offset=0.005,
           index=0, color_rgb=vertex_color.DEFAULT_RGB):
    """Build the dirt shell over `wall` and return it.

    The wall's mesh is copied so the shell hugs the actual surface, but its
    density is NOT inherited: coplanar faces are dissolved first and the result
    is subdivided adaptively until no edge is much longer than `spacing`. So
    the paint resolution is so-many-vertices-per-metre, decided by the Vertex
    Spacing setting - a wall that was modelled dense and a wall modelled as one
    quad produce the same shell. Finally everything is floated `surface_offset`
    along the vertex normals so it draws in front instead of z-fighting.

    Raises ShellError when the wall has no UVs (the dirt texture would have
    nowhere to sit) and TextureLoadError/SollumzShaderError from the decal
    material creation. Nothing is left behind on failure.
    """
    if not wall.data.uv_layers:
        raise ShellError(f"'{wall.name}' has no UV map - unwrap it first.")

    # One layer per texture, always. The callers check this too, but a second
    # shell for the same texture is a state nothing can make sense of, so it is
    # refused here as well - including when one was duplicated by hand.
    duplicate = find_by_texture(wall, texture_stem)
    if duplicate is not None:
        return duplicate

    # Material first: if the texture is unreadable or Sollumz is missing we
    # fail before any object exists.
    material = szi.find_or_create_decal_material(texture_stem, texture_path)

    mesh = wall.data.copy()
    mesh.name = f"{wall.name}_{texture_stem}"
    mesh.materials.clear()
    mesh.materials.append(material)

    # The copy brings the wall's own colour attributes with it; the shell wants
    # exactly one, ours, so the decal alpha is unambiguous.
    for attribute in list(mesh.color_attributes):
        mesh.color_attributes.remove(attribute)

    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        # Drop the wall's own tessellation where it is flat - without this, a
        # densely modelled wall would hand its density straight to the shell.
        # UV/seam/material boundaries are preserved so the texture cannot smear.
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1.0),
                                 verts=bm.verts[:], edges=bm.edges[:],
                                 delimit={'UV', 'MATERIAL', 'SEAM'})
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        # Adaptive subdivision: cut only the edges that are still too long, and
        # stop at the budget - paint resolution per metre, not per wall.
        for _ in range(10):
            if len(bm.verts) >= _VERTEX_BUDGET:
                break
            long_edges = [edge for edge in bm.edges
                          if edge.calc_length() > spacing * 1.5]
            if not long_edges:
                break
            bmesh.ops.subdivide_edges(bm, edges=long_edges, cuts=1,
                                      use_grid_fill=True)
        bm.normal_update()
        for vert in bm.verts:
            vert.co += vert.normal * surface_offset
        bm.to_mesh(mesh)
    finally:
        bm.free()

    # The wall's mesh brings its paint state along with its geometry, and every
    # part of it can silently stop the brush:
    #
    #   use_paint_mask / use_paint_mask_vertex - masking on with nothing
    #       selected means strokes land on nothing at all, with no error
    #   .hide_vert / .hide_edge / .hide_poly   - hidden geometry cannot be
    #       painted, and an imported asset often has some
    #
    # The shell is a fresh surface made for painting, so all of it is
    # paintable, whatever state the wall was left in.
    mesh.use_paint_mask = False
    mesh.use_paint_mask_vertex = False
    for hide_attr in (".hide_vert", ".hide_edge", ".hide_poly"):
        attribute = mesh.attributes.get(hide_attr)
        if attribute is not None:
            attribute.data.foreach_set(
                "value", np.zeros(len(attribute.data), dtype=bool))
    for polygon in mesh.polygons:
        polygon.select = True
    for vertex in mesh.vertices:
        vertex.select = True

    # Sollumz's UV name, and nothing else in the list - the pristine copy the
    # sliders need lives in the runtime cache, not on the mesh.
    mesh.uv_layers[0].name = UV_ATTR
    while len(mesh.uv_layers) > 1:
        mesh.uv_layers.remove(mesh.uv_layers[1])
    # The shell gets its OWN UVs, projected onto the surface - the wall's are
    # not inherited at all.
    #
    # Inheriting them was wrong in a way that only shows up on a real asset.
    # The wall's layout is built for the wall's own tiling texture, so it is
    # normally several islands that all sit on top of each other in 0-1: a wall
    # with one loop cut across it is two islands, both covering the whole tile.
    # Scaling that layout into 0-1 does not merge them - each island still maps
    # the whole image - so the decal was drawn once per island. That is the
    # "one graffiti, two copies" bug, and no amount of fitting can fix it,
    # because the duplication is in the layout, not in its range.
    #
    # A decal is a projection onto a surface, so that is what this is: one
    # planar projection across the whole shell. It cannot overlap itself, it
    # does not care how the wall was cut or unwrapped, and it makes UV space
    # linear in world space - which is what lets Place On Surface track the
    # cursor exactly.
    buf = _project_uvs(mesh)
    mesh.uv_layers[UV_ATTR].uv.foreach_set("vector", buf)
    _base_uv[mesh.name] = buf.copy()
    mesh.uv_layers.active = mesh.uv_layers[UV_ATTR]

    # Color 1: the repo's standard RGB, alpha 0 = fully invisible until painted.
    attribute = mesh.color_attributes.new(name=COLOR_ATTR, type='BYTE_COLOR',
                                          domain='CORNER')
    rgba = np.tile(np.array([*color_rgb, 0.0], dtype=np.float32),
                   len(attribute.data))
    attribute.data.foreach_set("color_srgb", rgba)
    mesh.color_attributes.active_color = attribute

    shell = bpy.data.objects.new(mesh.name, mesh)
    shell[MARKER] = wall.name
    shell[TEXTURE_KEY] = texture_stem
    shell[LAYER_KEY] = int(index)
    shell.matrix_world = wall.matrix_world.copy()

    # Into the wall's own collection AND parented to it. Both, deliberately:
    # a child that lives in a different collection is drawn twice in the
    # outliner - once under its collection and once under its parent - which
    # looks exactly like the tool spawned two meshes. Same collection, one row,
    # nested under the wall where it belongs.
    collections = wall.users_collection or [bpy.context.scene.collection]
    collections[0].objects.link(shell)

    shell.parent = wall
    shell.matrix_parent_inverse = wall.matrix_world.inverted()

    # One instance by default: a graffiti or a stain is placed, not tiled.
    # Repeat is a deliberate choice, made in the panel.
    set_repeat(shell, False)

    # Register it with Sollumz so it exports as drawable geometry alongside the
    # wall. Not fatal if it fails - the user can convert by hand.
    try:
        szi.convert_to_drawable_model(shell)
    except Exception:
        pass

    return shell


def remove(shell):
    """Delete the shell and its mesh. The wall is untouched by construction."""
    mesh = shell.data
    if mesh is not None:
        _base_uv.pop(mesh.name, None)
        _alpha_raw.pop(mesh.name, None)
    bpy.data.objects.remove(shell)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def set_texture(shell, texture_stem, texture_path):
    """Deliberately retexture ONE layer. Not called automatically anywhere -
    changing the dropdown adds a new layer instead, so strokes never change
    texture under the artist's feet. Decal materials are shared per texture, so
    this assigns rather than edits."""
    shell[TEXTURE_KEY] = texture_stem
    old = shell.data.materials[0] if shell.data.materials else None
    old_bump = bump_node(old) if old is not None else None

    if old_bump is not None:
        # Stay on the normal-map variant and carry the bump image across.
        try:
            image = bpy.data.images.load(texture_path, check_existing=True)
        except (RuntimeError, OSError) as e:
            raise ShellError(f"Could not load '{texture_path}': {e}")
        material = _find_normal_material(texture_stem, image)
        if material is None:
            shader_materials = szi._import("ydr.shader_materials")
            material = shader_materials.create_shader(NORMAL_SHADER)
            material.name = _NORMAL_MAT_PREFIX + texture_stem
            szi.get_diffuse_node(material).image = image
        new_bump = bump_node(material)
        if new_bump is not None and new_bump.image is None:
            new_bump.image = old_bump.image
    else:
        material = szi.find_or_create_decal_material(texture_stem, texture_path)

    had_ghost = has_ghost(shell)
    if had_ghost:
        disable_ghost(shell)
    mesh = shell.data
    if mesh.materials:
        mesh.materials[0] = material
    else:
        mesh.materials.append(material)
    if had_ghost:
        enable_ghost(shell)
    return material


# ------------------------------------------------------------------ the paint

def _color_attr(shell):
    return shell.data.color_attributes.get(COLOR_ATTR)


def _read_rgba(attribute):
    buf = np.empty(len(attribute.data) * 4, dtype=np.float32)
    attribute.data.foreach_get("color_srgb", buf)
    return buf


def adopt(shell):
    """Absorb a shell built by an older version.

    Earlier versions kept the slider bookkeeping as mesh layers; this moves
    them into the runtime caches and deletes them, so the mesh ends up with
    exactly Color 1 and UVMap 0 - the same two lists a fresh shell has.
    """
    mesh = shell.data

    legacy_uv = mesh.uv_layers.get(LEGACY_BASE_UV_ATTR)
    if legacy_uv is not None:
        buf = np.empty(len(legacy_uv.uv) * 2, dtype=np.float32)
        legacy_uv.uv.foreach_get("vector", buf)
        _base_uv[mesh.name] = buf
        mesh.uv_layers.remove(legacy_uv)

    legacy_cache = mesh.color_attributes.get(LEGACY_CACHE_ATTR)
    if legacy_cache is not None:
        buf = np.empty(len(legacy_cache.data) * 4, dtype=np.float32)
        legacy_cache.data.foreach_get("color", buf)
        _alpha_raw[mesh.name] = buf[0::4].copy()
        mesh.color_attributes.remove(legacy_cache)

    # A shell built before the paint state was cleared inherited the wall's
    # masking and hidden faces, which made the brush do nothing at all. Fix it
    # here rather than making the artist rebuild the layer.
    make_paintable(mesh)


def tidy_links(shell_obj, wall):
    """Keep a shell in exactly one collection - the wall's.

    An object linked into two collections is drawn twice in the outliner, once
    under each, which looks exactly like there are two of it. Files painted
    before this was fixed carry that state, so it is repaired on the way in
    rather than left for the artist to puzzle over.
    """
    if wall is None or len(shell_obj.users_collection) < 2:
        # One collection is the healthy state, wherever the artist put it.
        # Only a second link is the bug, and only that is removed - a layer
        # deliberately moved into its own collection stays there.
        return False

    target = (wall.users_collection or (bpy.context.scene.collection,))[0]
    keep = target if target in list(shell_obj.users_collection)         else shell_obj.users_collection[0]
    for collection in list(shell_obj.users_collection):
        if collection != keep:
            collection.objects.unlink(shell_obj)
    return True


def make_paintable(mesh):
    """Clear everything that can silently stop a stroke landing.

    Masking with nothing selected, and hidden geometry, both make vertex paint
    do exactly nothing without reporting anything - the worst kind of failure,
    because the tool looks like it is broken.
    """
    changed = False
    if mesh.use_paint_mask or mesh.use_paint_mask_vertex:
        mesh.use_paint_mask = False
        mesh.use_paint_mask_vertex = False
        changed = True
    for hide_attr in (".hide_vert", ".hide_edge", ".hide_poly"):
        attribute = mesh.attributes.get(hide_attr)
        if attribute is not None and len(attribute.data):
            values = np.empty(len(attribute.data), dtype=bool)
            attribute.data.foreach_get("value", values)
            if values.any():
                attribute.data.foreach_set(
                    "value", np.zeros(len(attribute.data), dtype=bool))
                changed = True
    if not all(p.select for p in mesh.polygons):
        for polygon in mesh.polygons:
            polygon.select = True
        for vertex in mesh.vertices:
            vertex.select = True
        changed = True
    if changed:
        mesh.update()
    return changed


def clear(shell):
    """All alpha back to 0 - clean wall. RGB is left as the repo standard."""
    attribute = _color_attr(shell)
    if attribute is None:
        return False
    buf = _read_rgba(attribute)
    buf[3::4] = 0.0
    attribute.data.foreach_set("color_srgb", buf)
    _alpha_raw.pop(shell.data.name, None)
    shell[_PREV_OPACITY_KEY] = 1.0
    shell.data.update()
    return True


def dirt_amount(shell):
    """Mean painted alpha, for the panel's percentage."""
    attribute = _color_attr(shell)
    if attribute is None or len(attribute.data) == 0:
        return 0.0
    return float(_read_rgba(attribute)[3::4].mean())


def set_opacity(shell, opacity):
    """Scale the whole painted mask, losslessly.

    Color 1 alpha becomes (painted strokes) x opacity. The full-strength
    strokes live in a runtime cache - not on the mesh - refreshed whenever the
    current alpha is trustworthy (previous opacity above the byte-precision
    floor). If the cache is gone (fresh session on a saved file) it is rebuilt
    from alpha divided by the remembered opacity, which is exact unless the
    file was saved with the slider near zero.
    """
    attribute = _color_attr(shell)
    if attribute is None:
        return False
    mesh = shell.data
    adopt(shell)

    buf = _read_rgba(attribute)
    alpha = buf[3::4]
    previous = float(shell.get(_PREV_OPACITY_KEY, 1.0))

    raw = _alpha_raw.get(mesh.name)
    if raw is None or len(raw) != len(alpha) or previous >= _CACHE_REFRESH_FLOOR:
        raw = np.clip(alpha / max(previous, 1e-3), 0.0, 1.0)

    buf[3::4] = np.clip(raw * opacity, 0.0, 1.0)
    attribute.data.foreach_set("color_srgb", buf)
    _alpha_raw[mesh.name] = raw
    shell[_PREV_OPACITY_KEY] = float(opacity)
    mesh.update()
    return True


# ------------------------------------------------------------------ placement

def _base_uvs(shell, target):
    """The pristine UVs, reconstructing them if the runtime cache is gone.

    Reconstruction inverts the last applied transform (remembered on the
    object), which is exact float math - the mesh never has to carry a copy.
    """
    mesh = shell.data
    base = _base_uv.get(mesh.name)
    if base is not None and len(base) == len(target.uv) * 2:
        return base

    current = np.empty(len(target.uv) * 2, dtype=np.float32)
    target.uv.foreach_get("vector", current)
    stored = list(shell.get(_PREV_UV_KEY, ()))
    if len(stored) == 4:
        # Written before width and height were separate: one scale for both.
        offset_u, offset_v, uniform, rotation = stored
        width = height = uniform
    else:
        offset_u, offset_v, width, height, rotation =             (stored + [0.0, 0.0, 1.0, 1.0, 0.0])[:5]

    u = (current[0::2] - 0.5 + offset_u) * max(width, 0.001)
    v = (current[1::2] - 0.5 + offset_v) * max(height, 0.001)
    cos_a = math.cos(rotation)
    sin_a = math.sin(rotation)
    base = np.empty_like(current)
    base[0::2] = (u * cos_a - v * sin_a) + 0.5
    base[1::2] = (u * sin_a + v * cos_a) + 0.5
    _base_uv[mesh.name] = base
    return base


def set_repeat(shell, repeat):
    """Whether the texture tiles outside its 0-1 patch, or appears once.

    This is the image node's extension mode, not anything about the UVs: with
    REPEAT the texture wraps forever, with CLIP everything outside the patch is
    transparent - which for a decal is what "one instance" means. Made small
    with Width/Height, a repeating texture covers the wall in copies; clipped,
    it is a single graffiti you can place.
    """
    changed = False
    for slot in shell.material_slots:
        material = slot.material
        node_tree = getattr(material, "node_tree", None)
        if node_tree is None:
            continue
        for node in node_tree.nodes:
            if node.bl_idname == 'ShaderNodeTexImage':
                node.extension = 'REPEAT' if repeat else 'CLIP'
                changed = True
    return changed


def uv_at_point(shell, face_index, location):
    """The base UV under a point on one of the shell's faces.

    Read from the pristine base rather than the live UVs, because dragging
    changes the live ones: sampling those would move the reference out from
    under the drag and the decal would slide away from the cursor.
    """
    mesh = shell.data
    if not (0 <= face_index < len(mesh.polygons)):
        return None
    target = mesh.uv_layers.get(UV_ATTR)
    if target is None:
        return None

    base = _base_uvs(shell, target)
    polygon = mesh.polygons[face_index]
    corners = [mesh.vertices[i].co for i in polygon.vertices]
    weights = poly_3d_calc(corners, location)

    u = v = 0.0
    for weight, loop_index in zip(weights, polygon.loop_indices):
        u += weight * float(base[loop_index * 2])
        v += weight * float(base[loop_index * 2 + 1])
    return u, v


def projection_map(shell):
    """The shell's UV projection, as something that works off the mesh too.

    Returns (solution, centre, normal), or None if it cannot be worked out.

    Dragging used to stop dead the moment the pointer left the surface, which
    made it impossible to push a decal to the edge of a wall or past it. There
    is no reason for that: the base UVs are one planar projection, so "the UV
    at this point" is a plane equation, and a plane does not end where the mesh
    does. Fitting that equation back out of the data gives the same answer on
    the mesh and keeps answering beyond it.

    Fitted rather than recomputed so a shell built before the projection
    existed still gets a usable - if only approximate - map instead of nothing.
    The points are coplanar, so the fit is rank-deficient and there are many
    solutions; every one of them agrees on the plane, which is the only place
    this is ever evaluated.
    """
    mesh = shell.data
    target = mesh.uv_layers.get(UV_ATTR)
    if target is None or not len(mesh.vertices) or not len(mesh.polygons):
        return None
    adopt(shell)
    base = _base_uvs(shell, target)

    coords = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)
    loop_verts = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_verts)

    design = np.hstack([coords[loop_verts], np.ones((len(mesh.loops), 1))])
    observed = np.stack([base[0::2], base[1::2]], axis=1).astype(np.float64)
    solution, *_ = np.linalg.lstsq(design, observed, rcond=None)

    normal = Vector((0.0, 0.0, 0.0))
    for polygon in mesh.polygons:
        normal += polygon.normal * polygon.area
    if normal.length < 1e-9:
        return None
    return solution, Vector(coords.mean(axis=0)), normal.normalized()


def uv_for_ray(mapping, origin, direction):
    """Where a ray crosses the projection plane, in base UV. None if it misses.

    Missing only happens looking exactly along the wall or from behind it -
    everywhere else this answers, including far outside the mesh, which is the
    point of it.
    """
    solution, centre, normal = mapping
    denominator = direction.dot(normal)
    if abs(denominator) < 1e-6:
        return None
    distance = (centre - origin).dot(normal) / denominator
    if distance <= 0.0:
        return None
    point = origin + direction * distance
    uv = np.array([point.x, point.y, point.z, 1.0]) @ solution
    return float(uv[0]), float(uv[1])


def apply_uv_transform(shell, offset_u=0.0, offset_v=0.0,
                       width=1.0, height=1.0, rotation=0.0):
    """Rebuild UVMap 0 from the pristine base through offset/size/rotation.

    Recomputed from the base every time, so the sliders are lossless and
    idempotent. Texture-space semantics: width 2.0 makes the dirt twice as wide,
    positive Offset X slides it right. Width and height are separate so a streak
    can be stretched down a wall without also stretching it sideways.

    Rotation is applied before the size, so stretching a rotated pattern
    stretches it along its own axes rather than along the wall's.
    """
    mesh = shell.data
    target = mesh.uv_layers.get(UV_ATTR)
    if target is None:
        return False
    adopt(shell)
    base = _base_uvs(shell, target)

    u = base[0::2] - 0.5
    v = base[1::2] - 0.5
    cos_a = math.cos(-rotation)
    sin_a = math.sin(-rotation)
    rot_u = u * cos_a - v * sin_a
    rot_v = u * sin_a + v * cos_a
    out = np.empty_like(base)
    out[0::2] = rot_u / max(width, 0.001) + 0.5 - offset_u
    out[1::2] = rot_v / max(height, 0.001) + 0.5 - offset_v
    target.uv.foreach_set("vector", out)
    shell[_PREV_UV_KEY] = [float(offset_u), float(offset_v),
                           float(width), float(height), float(rotation)]
    mesh.update()
    return True


def offset_for_drag(start, anchor, current, width=1.0, height=1.0, rotation=0.0):
    """Offsets that keep the point of texture grabbed at `anchor` under `current`.

    This is the inverse of apply_uv_transform, and it has to be, or dragging
    does not feel like dragging:

        apply:  uv = rot(base)/size + 0.5 - offset

    so the texture point showing at a surface point is base-derived minus the
    offset. Holding that constant while the surface point moves from `anchor`
    to `current` gives offset += rot(current - anchor)/size. Three separate
    things fall out of getting this right, all of which were wrong before:

    * the sign. It was subtracted, so the decal ran away from the cursor -
      drag down, texture goes up.
    * the size. A raw delta at Width 2 moved the decal twice as far as the
      cursor.
    * the rotation. A raw delta on a rotated decal moved it along the wall's
      axes instead of its own, so it slid off sideways.

    All three vanish when the drag is expressed in the same space the
    transform is.
    """
    delta_u = current[0] - anchor[0]
    delta_v = current[1] - anchor[1]

    cos_a = math.cos(-rotation)
    sin_a = math.sin(-rotation)
    rot_u = delta_u * cos_a - delta_v * sin_a
    rot_v = delta_u * sin_a + delta_v * cos_a

    return (start[0] + rot_u / max(width, 0.001),
            start[1] + rot_v / max(height, 0.001))


def offset_for_scale(offset, point, old_size, new_size, rotation=0.0):
    """Offsets that hold the texture still under `point` while the size changes.

    Width and Height scale the layer about the middle of the surface, which is
    right for the sliders and wrong for the wheel: zooming under the pointer
    has to leave what is under the pointer where it is, or the decal crawls
    away from the spot being worked on and has to be dragged back every time.

    Same reasoning as offset_for_drag - hold the texture point at `point`
    constant and solve for the offset:

        texture = rot(point - 0.5)/size + 0.5 - offset

    so the offset moves by rot(point - 0.5) * (1/new - 1/old).
    """
    cos_a = math.cos(-rotation)
    sin_a = math.sin(-rotation)
    u = point[0] - 0.5
    v = point[1] - 0.5
    rot_u = u * cos_a - v * sin_a
    rot_v = u * sin_a + v * cos_a

    old_width, old_height = old_size
    new_width, new_height = new_size
    return (offset[0] + rot_u * (1.0 / max(new_width, 0.001)
                                 - 1.0 / max(old_width, 0.001)),
            offset[1] + rot_v * (1.0 / max(new_height, 0.001)
                                 - 1.0 / max(old_height, 0.001)))


# ---------------------------------------------------------------- normal map

NORMAL_SHADER = "normal_decal.sps"
_NORMAL_MAT_PREFIX = "seto_decal_mat_n_"


def bump_node(material):
    """The BumpSampler image node, or None on a plain decal material."""
    node_tree = getattr(material, "node_tree", None)
    if node_tree is None:
        return None
    node = node_tree.nodes.get(szi.BUMP_SAMPLER_NODE)
    if node is not None and node.bl_idname == 'ShaderNodeTexImage':
        return node
    return None


def has_normal_map(shell):
    material = shell.data.materials[0] if shell.data.materials else None
    return material is not None and bump_node(material) is not None


def _find_normal_material(stem, diffuse_image):
    base_name = _NORMAL_MAT_PREFIX + stem
    for material in bpy.data.materials:
        if not (material.name == base_name or material.name.startswith(base_name + ".")):
            continue
        node = szi.get_diffuse_node(material)
        if node is not None and node.image == diffuse_image:
            return material
    return None


def enable_normal_map(shell, texture_stem):
    """Upgrade the shell to normal_decal.sps, keeping its diffuse.

    Same decal behaviour - Color 1 alpha is still the mask, confirmed against
    Sollumz's own node wiring - plus a BumpSampler slot for the normal map.
    The plain decal material is left untouched for other users of it.
    """
    old_material = shell.data.materials[0] if shell.data.materials else None
    diffuse_node = szi.get_diffuse_node(old_material) if old_material else None
    diffuse_image = diffuse_node.image if diffuse_node else None
    if diffuse_image is None:
        raise ShellError("The shell has no dirt texture to build the material from.")

    material = _find_normal_material(texture_stem, diffuse_image)
    if material is None:
        try:
            shader_materials = szi._import("ydr.shader_materials")
        except Exception as e:
            raise ShellError(f"Sollumz not available: {e}")
        material = shader_materials.create_shader(NORMAL_SHADER)
        node = szi.get_diffuse_node(material)
        if node is None:
            bpy.data.materials.remove(material)
            raise ShellError(f"'{NORMAL_SHADER}' has no DiffuseSampler node.")
        material.name = _NORMAL_MAT_PREFIX + texture_stem
        node.image = diffuse_image

    shell.data.materials[0] = material
    return material


def disable_normal_map(shell, texture_stem, texture_path):
    """Back to the plain decal.sps material for the current texture."""
    material = szi.find_or_create_decal_material(texture_stem, texture_path)
    shell.data.materials[0] = material
    return material

# -------------------------------------------------------------- ghost preview

# Substance Painter's projection workflow: before committing any strokes, show
# the whole texture semi-transparent over the surface, position it with the
# sliders, then paint - the ghost disappears, the strokes stay.
#
# Implemented as max(painted alpha, ghost strength) spliced into a COPY of the
# decal material, assigned as an object-level override (slot.link = 'OBJECT').
# The copy is what makes it safe: the real material - shared between every
# shell using this texture - is never touched, the mesh-level assignment that
# Sollumz exports never changes, and turning the ghost off just drops the
# override and deletes the copy.

GHOST_MAT_SUFFIX = "_seto_ghost"
GHOST_NODE = "SETO_GHOST_MAX"


def has_ghost(shell):
    slots = shell.material_slots
    return bool(slots) and slots[0].link == 'OBJECT'         and slots[0].material is not None


def _splice_ghost(material, strength):
    """factor = max(Color 1 alpha, strength), in this material only."""
    node_tree = material.node_tree
    for node in node_tree.nodes:
        if node.bl_idname == 'ShaderNodeVertexColor' and node.layer_name == COLOR_ATTR:
            alpha_out = node.outputs.get("Alpha")
            if alpha_out is None or not alpha_out.links:
                continue
            maximum = node_tree.nodes.new('ShaderNodeMath')
            maximum.name = maximum.label = GHOST_NODE
            maximum.operation = 'MAXIMUM'
            maximum.inputs[1].default_value = strength
            maximum.location = (node.location.x + 160, node.location.y - 120)
            for link in list(alpha_out.links):
                target = link.to_socket
                node_tree.links.remove(link)
                node_tree.links.new(maximum.outputs["Value"], target)
            node_tree.links.new(alpha_out, maximum.inputs[0])
            return True
    return False


def enable_ghost(shell, strength=0.35):
    """Show the whole texture ghosted over this shell. Viewport only."""
    slots = shell.material_slots
    base = shell.data.materials[0] if shell.data.materials else None
    if not slots or base is None:
        raise ShellError("The paint mesh has no material to preview.")
    if has_ghost(shell):
        set_ghost_strength(shell, strength)
        return

    ghost = base.copy()
    ghost.name = base.name + GHOST_MAT_SUFFIX
    if not _splice_ghost(ghost, strength):
        bpy.data.materials.remove(ghost)
        raise ShellError("Could not find the mask node to preview through.")
    slots[0].link = 'OBJECT'
    slots[0].material = ghost


def set_ghost_strength(shell, strength):
    if not has_ghost(shell):
        return False
    node_tree = shell.material_slots[0].material.node_tree
    node = node_tree.nodes.get(GHOST_NODE)
    if node is None:
        return False
    node.inputs[1].default_value = strength
    return True


def disable_ghost(shell):
    """Back to exactly the painted strokes. Deletes the override copy."""
    slots = shell.material_slots
    if not slots or slots[0].link != 'OBJECT':
        return False
    ghost = slots[0].material
    slots[0].link = 'DATA'
    if ghost is not None and GHOST_MAT_SUFFIX in ghost.name:
        bpy.data.materials.remove(ghost)
    return True

def _projection_axes(mesh):
    """Right/up axes to project the decal along, in the shell's own space.

    The projection looks at the surface head on: its direction is the
    area-weighted average normal, so a slightly bent or bevelled wall still
    gets the flat, undistorted projection a decal wants.

    Up is world Z wherever that is meaningful, which is what makes Offset Y
    mean "up the wall" and Rotation turn the way it looks like it should. On a
    floor or ceiling Z *is* the normal, so Y stands in for it.
    """
    normal = Vector((0.0, 0.0, 0.0))
    for polygon in mesh.polygons:
        normal += polygon.normal * polygon.area
    if normal.length < 1e-9:
        normal = Vector((0.0, 0.0, 1.0))
    normal.normalize()

    up_ref = Vector((0.0, 0.0, 1.0))
    if abs(normal.dot(up_ref)) > 0.999:
        up_ref = Vector((0.0, 1.0, 0.0))

    # Handedness matters: seen from the front, +U has to go right, not left,
    # or dragging sideways would send the decal the other way.
    right = up_ref.cross(normal).normalized()
    up = normal.cross(right).normalized()
    return right, up


def _project_uvs(mesh):
    """One planar projection of the whole shell, fitted to 0-1.

    Never per face and never per island: a single affine map from position to
    UV, so every point on the surface has its own place in the texture and the
    decal can appear only once.
    """
    right, up = _projection_axes(mesh)

    coords = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)

    loop_verts = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_verts)
    points = coords[loop_verts]

    flat = np.empty(len(mesh.loops) * 2, dtype=np.float32)
    flat[0::2] = points @ np.array(right, dtype=np.float32)
    flat[1::2] = points @ np.array(up, dtype=np.float32)
    return _fit_uvs(flat)


def _fit_uvs(flat):
    """Scale a UV layout so it spans 0-1, keeping its aspect ratio.

    Uniform rather than stretched to fill: squashing a graffiti sheet to a
    non-square wall would distort it, which is worse than leaving margin.
    """
    u = flat[0::2]
    v = flat[1::2]
    if not len(u):
        return flat
    span_u = float(u.max() - u.min())
    span_v = float(v.max() - v.min())
    span = max(span_u, span_v)
    if span <= 1e-9:
        return flat

    scale = 1.0 / span
    out = np.empty_like(flat)
    out[0::2] = (u - (u.min() + span_u / 2.0)) * scale + 0.5
    out[1::2] = (v - (v.min() + span_v / 2.0)) * scale + 0.5
    return out


# ---------------------------------------------------------------- optimising

# The sharp way to make a painted layer cheap.
#
# Baking flattens the tiling texture into one unique image, and a unique image
# can never be sharper than the source it was sampled from - on a big wall it
# is a lot worse. So the default optimisation does not touch the texture at
# all. It removes the geometry that carries no information instead, in two
# steps:
#
#   1. crop  the faces the brush never reached are deleted outright, so what is
#            left is a patch the size of the decal, not a sheet the size of the
#            wall
#   2. thin  inside that patch a stroke's detail lives entirely in the gradient
#            at its edge, so the flat middle of a blob and its flat surround
#            collapse to a couple of faces without changing a single pixel
#
# Every pixel that was painted is still drawn, at full sharpness.

def _vertex_alpha(mesh, attribute):
    """Painted alpha per vertex, averaged over the corners that meet there."""
    loop_count = len(mesh.loops)
    buf = np.empty(loop_count * 4, dtype=np.float32)
    attribute.data.foreach_get("color_srgb", buf)
    alpha = buf[3::4]

    if attribute.domain != 'CORNER':
        return alpha

    loop_verts = np.empty(loop_count, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_verts)
    totals = np.zeros(len(mesh.vertices), dtype=np.float64)
    counts = np.zeros(len(mesh.vertices), dtype=np.float64)
    np.add.at(totals, loop_verts, alpha)
    np.add.at(counts, loop_verts, 1.0)
    counts[counts == 0.0] = 1.0
    return (totals / counts).astype(np.float32)


# Below this a corner is simply unpainted: one step of the byte the alpha is
# stored in, so it is "the brush never landed here", not "faintly painted".
_CROP_ALPHA = 1.5 / 255.0


def _crop_unpainted(shell, threshold=_CROP_ALPHA):
    """Delete the faces no stroke ever reached. Returns how many went.

    Dissolving alone kept the shell the full size of the wall: the untouched
    area collapsed into a handful of enormous triangles fanning right across
    it. They draw nothing - alpha is 0 everywhere on them - but they are still
    the artist's mesh, they still sit in the outliner over the whole wall, and
    they are still exported. What a decal should leave behind is a patch the
    size of the decal, so the unpainted faces are cut away instead of thinned.

    A face survives if any of its corners carries paint, which automatically
    keeps one ring of faces around the strokes - the ring where alpha falls to
    0. That is where the decal fades out, so the edge looks exactly as painted;
    cropping any tighter would cut the fade off square.

    A layer with nothing painted on it is left alone: everything would qualify,
    and silently deleting the whole mesh is not an optimisation.
    """
    mesh = shell.data
    attribute = _color_attr(shell)
    if attribute is None or not mesh.polygons:
        return 0

    buf = np.empty(len(attribute.data) * 4, dtype=np.float32)
    attribute.data.foreach_get("color_srgb", buf)
    alpha = buf[3::4]

    if attribute.domain != 'CORNER':
        loop_verts = np.empty(len(mesh.loops), dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", loop_verts)
        alpha = alpha[loop_verts]

    # Loops are stored contiguously per face, so the strongest corner of each
    # face is one segmented reduction over that run.
    starts = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    strongest = np.maximum.reduceat(alpha, starts)

    doomed = np.flatnonzero(strongest <= threshold)
    if not len(doomed) or len(doomed) == len(mesh.polygons):
        return 0

    condemned = set(doomed.tolist())
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.faces.ensure_lookup_table()
        faces = [f for f in bm.faces if f.index in condemned]
        # 'FACES' takes the vertices and edges left behind with them, so no
        # loose geometry is left hanging around the patch.
        bmesh.ops.delete(bm, geom=faces, context='FACES')
        bm.to_mesh(mesh)
    finally:
        bm.free()

    mesh.update()
    _base_uv.pop(mesh.name, None)
    _alpha_raw.pop(mesh.name, None)
    return len(doomed)


def optimize_mesh(shell, tolerance=0.02, angle_limit=math.radians(1.0),
                  max_passes=8):
    """Crop to the painting, then drop the vertices it does not need.

    Returns (before, after).

    A vertex is expendable when removing it would not change the mask: its own
    alpha is already what its neighbours interpolate to. That covers both the
    flat middle of a stroke (every neighbour identical) and the straight part
    of a falloff (the value is exactly the average of the two sides) - which is
    most of a soft edge, and is why this goes so much further than only
    removing flat areas. What stays is curvature: where the ramp actually
    bends, which is what the eye reads as the shape of the stroke.

    Geometry the mesh needs (the angle limit) and every UV seam are protected
    regardless.

    The texture is never touched, so the result is pixel-identical to what was
    painted. That is the whole difference from baking.

    Repeated until it stops removing anything: dissolving changes which
    vertices are adjacent, so a single pass leaves more to take. Converging
    here means one press does the whole job and a second press is honestly a
    no-op.
    """
    first = len(shell.data.polygons)

    # Cropping first, because it removes most of the mesh outright and leaves
    # the thinning only the painted patch to think about.
    _crop_unpainted(shell)
    _thin(shell, tolerance, angle_limit, max_passes)

    # Thinning leaves clusters of vertices almost on top of each other along
    # the edge of the patch - the leftovers of the grid it started from. They
    # cost triangles and describe nothing, so they are welded together, and
    # whatever that flattens into a sliver or an empty face is cleared out.
    # Then round again: welding gives the thinning new neighbours to work with.
    if _merge_close(shell):
        _crop_unpainted(shell)
        _thin(shell, tolerance, angle_limit, max_passes)

    # Last, once the patch has stopped changing shape: the origin belongs in
    # the middle of what is actually left, not where the wall's happened to be.
    center_origin(shell)

    return first, len(shell.data.polygons)


def _thin(shell, tolerance, angle_limit, max_passes):
    """Run the dissolve to convergence. Returns the face count it settled at."""
    total = len(shell.data.polygons)
    for _ in range(max_passes):
        before, after = _optimize_pass(shell, tolerance, angle_limit)
        total = after
        if after >= before:
            break
    return total


def _merge_close(shell, factor=2.5, threshold=_CROP_ALPHA):
    """Weld the leftover vertices around the patch. Returns how many went.

    What is left after cropping and thinning is a blob of paint inside a
    staircase of tiny faces - the crop follows the grid the shell was built
    on, and a staircase corner is a real 90 degree turn, so the dissolve is
    right to refuse it. Those steps cost triangles and describe nothing: the
    silhouette they trace is invisible, because alpha is 0 the whole way round
    it. Welding them collapses the ring into a few big faces (ngons, happily)
    without changing one drawn pixel.

    The image is protected structurally rather than by choosing a small
    distance. A vertex may only be welded if it is unpainted AND every one of
    its neighbours is unpainted, which means every face with any paint on it
    has all of its corners excluded. Those faces come through untouched -
    same positions, same UVs, same alpha - so the decal is bit-identical and
    only the invisible surround gets cheaper. That is what makes a weld of
    several edge lengths safe here, where a blind one would have to creep.

    Measured on a ragged blob: 208 triangles down to 188, UV error exactly 0,
    and the only visible cost is at the very rim, where the patch can pull back
    across a sliver that was drawing 5% opacity. Below about two edge lengths
    it finds nothing to do at all - the leftovers really are that far apart.
    """
    mesh = shell.data
    if len(mesh.edges) < 2 or len(mesh.vertices) < 4:
        return 0
    attribute = _color_attr(shell)
    if attribute is None:
        return 0

    coords = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)
    edge_verts = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", edge_verts)
    edge_verts = edge_verts.reshape(-1, 2)

    # Safe means "belongs to no face that has any paint on it". Face-based, not
    # edge-based: on a quad or an ngon the opposite corner is not a neighbour,
    # so spreading the exclusion along edges would leave it weldable and let a
    # weld deform a painted face from across the room. Measured, when it was:
    # UVs shifted by 0.04 and a faintly painted strip got cropped off.
    buf = np.empty(len(attribute.data) * 4, dtype=np.float32)
    attribute.data.foreach_get("color_srgb", buf)
    corner_alpha = buf[3::4]
    loop_verts = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_verts)
    if attribute.domain != 'CORNER':
        corner_alpha = corner_alpha[loop_verts]

    starts = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    face_alpha = np.maximum.reduceat(corner_alpha, starts)
    loop_face = np.repeat(np.arange(len(mesh.polygons)),
                          np.diff(np.append(starts, len(mesh.loops))))

    # Nothing painted anywhere means nothing to protect, and every vertex would
    # qualify - which welds the layer into a point and then dissolves it away.
    # Same rule as the crop: an untouched layer is left alone.
    if not (corner_alpha > threshold).any():
        return 0

    touches_paint = np.zeros(len(mesh.vertices), dtype=bool)
    np.logical_or.at(touches_paint, loop_verts, face_alpha[loop_face] > threshold)
    safe = ~touches_paint
    if not safe.any():
        return 0

    lengths = np.linalg.norm(coords[edge_verts[:, 0]] - coords[edge_verts[:, 1]],
                             axis=1)
    typical = float(np.median(lengths))
    if typical <= 1e-9:
        return 0
    distance = typical * factor

    weldable = set(np.flatnonzero(safe).tolist())
    before = len(mesh.vertices)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        # Carried on a temporary layer rather than on the indices, because
        # welding renumbers the vertices - looking "safe" up by index
        # afterwards would be reading someone else's answer. The layer is
        # removed again below: the exported mesh carries Color 1 and UVMap 0
        # and nothing else.
        flag = bm.verts.layers.int.new("seto_weld_safe")
        for vert in bm.verts:
            vert[flag] = 1 if vert.index in weldable else 0

        bmesh.ops.remove_doubles(
            bm, verts=[v for v in bm.verts if v[flag]], dist=distance)

        # Welding can leave faces with two corners now at the same point: no
        # area, nothing drawn, still triangles in the export. Restricted to
        # edges that are entirely safe for the same reason as above - a painted
        # face must come out of here exactly as it went in.
        degenerate = [e for e in bm.edges if e.verts[0][flag] and e.verts[1][flag]]
        if degenerate:
            bmesh.ops.dissolve_degenerate(bm, dist=distance * 0.1,
                                          edges=degenerate)
        bm.verts.layers.int.remove(flag)
        bm.to_mesh(mesh)
    finally:
        bm.free()

    mesh.update()
    _base_uv.pop(mesh.name, None)
    _alpha_raw.pop(mesh.name, None)
    return before - len(mesh.vertices)


def center_origin(shell):
    """Put the object's origin in the middle of the mesh. True if it moved.

    After cropping, the layer is a small patch but its origin is still where
    the wall's was - usually off the patch entirely, sometimes metres away,
    which makes it awkward to grab, rotate or snap. The mesh is shifted by the
    same amount in the opposite direction, so nothing moves in the scene: the
    pivot does, and only the pivot.

    The compensation goes on the mesh side of the object's transform, which is
    the same space the vertices moved in, so this stays correct whatever
    rotation, scale or parenting the wall has.
    """
    mesh = shell.data
    if not len(mesh.vertices):
        return False

    coords = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)
    centre = (coords.min(axis=0) + coords.max(axis=0)) / 2.0
    if not np.isfinite(centre).all() or np.allclose(centre, 0.0, atol=1e-9):
        return False

    shifted = (coords - centre).ravel().astype(np.float32)
    mesh.vertices.foreach_set("co", shifted)
    mesh.update()
    shell.matrix_basis = shell.matrix_basis @ Matrix.Translation(Vector(centre))
    return True


def _optimize_pass(shell, tolerance, angle_limit):
    mesh = shell.data
    attribute = _color_attr(shell)
    if attribute is None or not mesh.polygons:
        return len(mesh.polygons), len(mesh.polygons)

    per_vertex = _vertex_alpha(mesh, attribute)

    edge_verts = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", edge_verts)
    edge_verts = edge_verts.reshape(-1, 2)

    # What each vertex's neighbours would interpolate to if it were not there.
    # Comparing against that rather than against "are they all the same" is
    # what lets a smooth falloff collapse to the few vertices that describe its
    # curvature.
    totals = np.zeros(len(mesh.vertices), dtype=np.float64)
    counts = np.zeros(len(mesh.vertices), dtype=np.float64)
    np.add.at(totals, edge_verts[:, 0], per_vertex[edge_verts[:, 1]])
    np.add.at(totals, edge_verts[:, 1], per_vertex[edge_verts[:, 0]])
    np.add.at(counts, edge_verts[:, 0], 1.0)
    np.add.at(counts, edge_verts[:, 1], 1.0)

    # A vertex with no edges cannot be judged, and a lone vertex is not
    # something to dissolve anyway.
    judged = counts > 0.0
    predicted = np.zeros(len(mesh.vertices), dtype=np.float32)
    predicted[judged] = (totals[judged] / counts[judged]).astype(np.float32)
    error = np.where(judged, np.abs(per_vertex - predicted), 1.0)

    flat = set(np.flatnonzero(error <= tolerance).tolist())
    if not flat:
        return len(mesh.polygons), len(mesh.polygons)

    before = len(mesh.polygons)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        verts = [v for v in bm.verts if v.index in flat]
        edges = [e for e in bm.edges
                 if e.verts[0].index in flat and e.verts[1].index in flat]
        if verts:
            bmesh.ops.dissolve_limit(bm, angle_limit=angle_limit,
                                     verts=verts, edges=edges,
                                     delimit={'UV', 'SEAM', 'MATERIAL'})
            # Dissolving leaves ngons, which nothing downstream wants. Cut them
            # into triangles, then pair those back into quads: half as many
            # faces, and a quad mesh is what an artist expects to be handed.
            # Sollumz triangulates on export anyway, so this costs nothing in
            # game and only makes the result easier to work with.
            bmesh.ops.triangulate(bm, faces=bm.faces[:])
            # angle_face_threshold keeps quads from spanning a real bend in
            # the surface. angle_shape_threshold is deliberately wide open:
            # after a dissolve the triangles are irregular, and refusing the
            # badly-shaped pairs is what leaves the mesh mostly triangles.
            # Measured on a painted blob: 40 degrees leaves 311 faces / 27%
            # quads, 180 leaves 217 / 82%. The comparison flags cost nothing
            # here and still guard against joining across a genuine seam.
            bmesh.ops.join_triangles(
                bm, faces=bm.faces[:],
                angle_face_threshold=math.radians(40.0),
                angle_shape_threshold=math.pi,
                cmp_seam=True, cmp_sharp=True,
                cmp_uvs=True, cmp_vcols=True,
                cmp_materials=True)
        bm.to_mesh(mesh)
    finally:
        bm.free()

    mesh.update()
    # The stored placement is still valid - the UVs came along with the
    # geometry - but the cached copies are indexed by the old topology.
    _base_uv.pop(mesh.name, None)
    _alpha_raw.pop(mesh.name, None)
    return before, len(mesh.polygons)
