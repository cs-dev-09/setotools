"""Floor Dirt - the overlay sheet vanilla GTA actually uses.

Measured, not guessed: of the game's 377 interiors, 176 carry entities
named like `bkr_int01_cm3dirtfloor`, `hei_int_heist_hall_over_dirt`,
`ex_int_warem_stains` - flat, hand-authored decal meshes floated a few
millimetres over the floor, wearing a dirt texture in `decal.sps`.
Rockstar does not scatter grime props (the whole game places
prop_paper_ball 21 times); the dirt on a vanilla floor is one overlay
sheet per room. This module builds that sheet procedurally.

The overlay is a copy of the scattered region's triangles, lifted along
+Z, subdivided to a working vertex spacing, textured with the bundled
dirt sheet through the Decal Tool's own material path, and patterned
through **Color 1's alpha** - the same channel every other tool here
writes, and the one `decal.sps` multiplies the texture by. The pattern
is seeded value noise with the scatter's Edge Bias folded in, so the
grime pools along the walls exactly where the litter does.

The source floor is never touched; the overlay is parented to it and
linked into its own collection (both at once, deliberately - a parented
object in a different collection draws twice in the outliner, a lesson
Surface Painter paid for first).
"""

import math
import os

import bmesh
import bpy

from ..shared import bundled_textures, sollumz_integration as szi
from . import geometry as scatter_geometry

MARKER = "seto_scatter_dirt_src"

# The overlay floats this far above the floor - the same order of height
# vanilla's own overlay sheets sit at, high enough to defeat z-fighting.
LIFT = 0.004

# World metres of texture per UV tile.
TEXTURE_TILE = 2.0

# Subdivision spacing bounds: the slider maps within these.
MIN_SPACING = 0.08

# How many vertices a blotch is worth across its width. The mesh only has
# to carry the pattern, and the pattern's finest feature is one blotch, so
# spacing is derived from Blotch Size rather than fixed: a 2 m blotch on a
# 0.25 m grid was eight samples wide - four times more mesh than the
# picture needed, and the sheet came out heavy (seen on a real floor).
SAMPLES_PER_BLOTCH = 4.0
MAX_SPACING = 0.75


def spacing_for(noise_scale):
    """The working vertex spacing for a given Blotch Size."""
    return max(MIN_SPACING, min(MAX_SPACING,
                                noise_scale / SAMPLES_PER_BLOTCH))


def _texture():
    """The bundled dirt sheet Edge Dirt already ships."""
    folder = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "edge_dirt", "textures")
    path = bundled_textures.bundled_texture_path(folder)
    stem = bundled_textures.bundled_texture_name(folder)
    return stem, path


def _hash01(ix, iy, seed):
    """Deterministic pseudo-random in [0, 1) for one lattice point."""
    h = (ix * 374761393 + iy * 668265263 + seed * 2246822519) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65536.0


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


def value_noise(x, y, seed):
    """Two octaves of lattice value noise in [0, 1]. Pure and seeded."""
    total = 0.0
    amplitude = 0.65
    frequency = 1.0
    for octave in range(2):
        fx, fy = x * frequency, y * frequency
        ix, iy = math.floor(fx), math.floor(fy)
        tx, ty = _smooth(fx - ix), _smooth(fy - iy)
        a = _hash01(ix, iy, seed + octave)
        b = _hash01(ix + 1, iy, seed + octave)
        c = _hash01(ix, iy + 1, seed + octave)
        d = _hash01(ix + 1, iy + 1, seed + octave)
        total += amplitude * ((a * (1 - tx) + b * tx) * (1 - ty)
                              + (c * (1 - tx) + d * tx) * ty)
        amplitude *= 0.5
        frequency *= 2.1
    return min(1.0, total)


def dirt_alpha(position, boundaries, seed, amount, edge_bias, noise_scale):
    """The grime value for one overlay vertex, in [0, 1].

    Noise gives the blotches; the boundary term pulls them toward the
    walls with the same falloff the litter uses; `amount` is the user's
    one big slider, applied as both threshold and gain so 0 is a clean
    floor and 1 is a floor you can write in.

    `boundaries` may be a raw segment list or a prebuilt BoundaryIndex -
    pass the index when calling this per vertex, which is the only way
    this is ever called in anger.
    """
    noise = value_noise(position.x / noise_scale, position.y / noise_scale,
                        seed)
    boost = 0.0
    if boundaries and edge_bias > 0.0:
        index = scatter_geometry.as_boundary_index(boundaries)
        distance = index.distance(position)
        boost = edge_bias * 0.45 * math.exp(
            -distance / scatter_geometry.EDGE_FALLOFF)
    value = noise * (0.35 + 0.65 * amount) + boost
    threshold = 0.62 - 0.45 * amount
    span = 0.38
    return max(0.0, min(1.0, (value - threshold) / span)) * amount ** 0.5


def overlay_name(floor):
    return f"{floor.name}_floor_dirt"


def remove_overlay(floor_name):
    doomed = [obj for obj in bpy.data.objects
              if obj.get(MARKER) == floor_name]
    for obj in doomed:
        mesh = obj.data
        bpy.data.objects.remove(obj)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return len(doomed)


def build_overlay(context, floor, triangles, boundaries, seed, amount,
                  edge_bias, noise_scale, spacing=None):
    """Build (or replace) the floor's dirt overlay. Returns the object.

    `triangles`/`boundaries` are the scattered region in world space -
    the same data the litter uses, so the dirt covers exactly the faces
    the user selected and nothing else.
    """
    remove_overlay(floor.name)
    if not triangles or amount <= 0.0:
        return None

    stem, path = _texture()
    if not path:
        return None
    material = szi.find_or_create_decal_material(stem, path, reuse=True)

    bm = bmesh.new()
    for a, b, c in triangles:
        verts = [bm.verts.new(v) for v in (a, b, c)]
        try:
            bm.faces.new(verts)
        except ValueError:
            pass  # degenerate duplicate; skip
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)

    # Subdivide until no edge is longer than the spacing: the alpha lives
    # on vertices, and blotches can be no finer than the mesh under them.
    spacing = spacing_for(noise_scale) if spacing is None \
        else max(MIN_SPACING, spacing)
    for _ in range(6):
        long_edges = [e for e in bm.edges
                      if (e.verts[0].co - e.verts[1].co).length > spacing]
        if not long_edges:
            break
        bmesh.ops.subdivide_edges(bm, edges=long_edges, cuts=1,
                                  use_grid_fill=True)

    # Equalise the triangles. The region arrives fan-triangulated, and
    # subdividing a fan keeps its long thin slivers - across which the
    # per-vertex alpha interpolates as visible streaks that follow the
    # floor's original edge lines (seen in game: the grime "drew" the
    # mesh). Beautify re-flips the diagonals toward even triangles, so
    # the noise reads as blotches, not as topology.
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.beautify_fill(bm, faces=bm.faces[:], edges=bm.edges[:])

    # Then back to quads, as far as the pairs allow. Beautified triangles
    # pair cleanly, so most of the sheet comes out quads - lighter to
    # edit, and Sollumz triangulates on export anyway, so this costs the
    # game nothing. The thresholds are Surface Painter's measured pair
    # (40 degrees / pi): a tighter shape threshold refuses the slightly
    # irregular pairs and leaves the mesh mostly triangles.
    bmesh.ops.join_triangles(
        bm, faces=bm.faces[:],
        angle_face_threshold=math.radians(40.0),
        angle_shape_threshold=math.pi,
        cmp_seam=True, cmp_sharp=True,
        cmp_uvs=True, cmp_vcols=True,
        cmp_materials=True)

    for vert in bm.verts:
        vert.co.z += LIFT

    mesh = bpy.data.meshes.new(overlay_name(floor))
    bm.to_mesh(mesh)
    bm.free()

    # UV and Color 1 through the shared writer, so the attribute names and
    # types are whatever this Sollumz version expects - the same call
    # every other tool makes.
    # One index for the whole sheet: without it every vertex measured
    # itself against every rim segment, which is most of what made a
    # rebuild slow on a real floor.
    index = scatter_geometry.as_boundary_index(boundaries)

    alphas = {}
    loop_uv = []
    loop_rgba = []
    for loop in mesh.loops:
        position = mesh.vertices[loop.vertex_index].co
        loop_uv.append((position.x / TEXTURE_TILE,
                        position.y / TEXTURE_TILE))
        if loop.vertex_index not in alphas:
            alphas[loop.vertex_index] = dirt_alpha(
                position, index, seed, amount, edge_bias, noise_scale)
        loop_rgba.append((1.0, 1.0, 1.0, alphas[loop.vertex_index]))
    szi.write_uv_and_color(mesh, loop_uv, loop_rgba)

    obj = bpy.data.objects.new(overlay_name(floor), mesh)
    obj[MARKER] = floor.name

    # The floor's own collection AND parented to the floor - both, or the
    # outliner shows the overlay twice (Surface Painter's lesson).
    collection = floor.users_collection[0] if floor.users_collection \
        else context.scene.collection
    collection.objects.link(obj)
    obj.parent = floor
    obj.matrix_parent_inverse = floor.matrix_world.inverted_safe()

    mesh.materials.append(material)
    if mesh.polygons:
        mesh.polygons.foreach_set("use_smooth",
                                  [True] * len(mesh.polygons))
    # append() adds a slot but assigns no faces (a lesson this repo keeps
    # relearning) - a fresh mesh's polygons default to index 0, which is
    # this material, so here it is genuinely enough.
    return obj
