"""Headless verification pass for seto_decal_tool.

Run with:
    blender -b --python verify_decal_tool.py

Registers the addon straight from D:\\SetoClaude (nothing is installed into the
user's Blender config), builds a throwaway decal library and test mesh, then
walks the verification checklist from the plan.
"""

import math
import os
import shutil
import sys
import tempfile
import traceback

import bpy
import bmesh
from mathutils import Euler, Matrix, Vector

REPO_ROOT = r"D:\SetoClaude\setotools"
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

import seto_tools
from seto_tools.decal_tool import geometry, library, preferences, previews, properties
from seto_tools.shared import sollumz_integration as szi

RESULTS = []
TOL = 1e-5


def check(name, condition, detail=""):
    RESULTS.append((bool(condition), name, detail))
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f"  -- {detail}" if detail and not condition else ""))
    return bool(condition)


def close(a, b, tol=TOL):
    return abs(a - b) <= tol


def vclose(a, b, tol=TOL):
    return (Vector(a) - Vector(b)).length <= tol


# --------------------------------------------------------------------- library

def write_png(path, rgba):
    """Write a tiny 4x4 PNG with the given RGBA, via Blender itself."""
    image = bpy.data.images.new(os.path.basename(path), 4, 4, alpha=True)
    image.pixels = list(rgba) * 16
    image.filepath_raw = path
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)


def build_library(root):
    layout = {
        "Dirt": ["dirt_01", "dirt_02", "dirt_03"],
        "Cracks": ["crack_01", "crack_02"],
        "Leaks": ["leak_01"],
        "Broken": ["broken_01"],
        "Mixed": ["mixed_good", "mixed_bad"],
    }
    for category, stems in layout.items():
        os.makedirs(os.path.join(root, category), exist_ok=True)
        for stem in stems:
            write_png(os.path.join(root, category, stem + ".png"), (0.5, 0.3, 0.2, 0.5))
    return layout


# ------------------------------------------------------------------ test mesh

def build_test_mesh():
    """One mesh with four coplanar-free quads: floor, ceiling, wall, slanted."""
    verts = []
    faces = []

    def quad(points):
        start = len(verts)
        verts.extend(points)
        faces.append(tuple(range(start, start + 4)))

    # floor: normal +Z
    quad([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
    # ceiling: normal -Z
    quad([(0, 0, 3), (0, 1, 3), (1, 1, 3), (1, 0, 3)])
    # wall: normal +X
    quad([(5, 0, 0), (5, 1, 0), (5, 1, 1), (5, 0, 1)])
    # slanted 45 degrees
    quad([(0, 0, 10), (0, 1, 10), (1, 1, 9), (1, 0, 9)])
    # a second floor whose edges are NOT axis-aligned: its edge tangent is not an
    # eigenvector of an axis-aligned scale, which is what makes the linear part
    # and the normal matrix actually disagree.
    quad([(0, 0, 6), (1, 0.5, 6), (0.5, 1.5, 6), (-0.5, 1, 6)])

    mesh = bpy.data.meshes.new("source_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("source_obj", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def select_all_faces(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='SELECT')


def leave_edit():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def call_create():
    """bpy.ops raises when an operator reports {'ERROR'}, which is normal Blender
    behaviour for script calls (in the UI it is just a red status message). The
    tests care about the return value, so the exception is translated back."""
    try:
        return bpy.ops.seto.create_decal()
    except RuntimeError as e:
        print(f"       (operator error: {e})")
        return {'CANCELLED'}


def decal_objects():
    return [o for o in bpy.data.objects if o.name.startswith("seto_decal_")]


def clear_decals():
    for obj in decal_objects():
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def orphan_decal_meshes():
    return [m.name for m in bpy.data.meshes
            if m.name.startswith("seto_decal") and m.users == 0]


def world_faces(obj):
    """[(center_world, normal_world), ...] computed independently of the addon."""
    m = obj.matrix_world
    normal_matrix = m.inverted_safe().transposed().to_3x3()
    out = []
    for poly in obj.data.polygons:
        n = (normal_matrix @ poly.normal).normalized()
        out.append((m @ poly.center, n))
    return out


# ----------------------------------------------------------------- assertions

def check_decal_against_face(label, decal, center, normal, offset, expect_upright):
    prefix = f"{label} [{decal.name}]"

    matrix = decal.matrix_world
    check(f"{prefix} basis is orthonormal, det +1", geometry.is_orthonormal(matrix))

    x = matrix.to_3x3().col[0].normalized()
    y = matrix.to_3x3().col[1].normalized()
    z = matrix.to_3x3().col[2].normalized()

    check(f"{prefix} local +Z matches the face normal",
          z.dot(normal) > 1.0 - TOL, f"dot={z.dot(normal):.9f}")
    check(f"{prefix} object scale is unit",
          vclose(decal.scale, (1.0, 1.0, 1.0)), str(tuple(decal.scale)))
    check(f"{prefix} origin sits at face center + normal * offset",
          vclose(decal.location, center + normal * offset, 1e-4),
          f"{tuple(decal.location)} vs {tuple(center + normal * offset)}")

    # The real "flush, no tilt, no shear" test: every corner is exactly `offset`
    # above the source face plane.
    distances = [(matrix @ Vector(v.co) - center).dot(normal) for v in decal.data.vertices]
    check(f"{prefix} all 4 corners are flush at the offset distance",
          all(close(d, offset, 1e-4) for d in distances),
          ", ".join(f"{d:.6f}" for d in distances))

    # And they all lie on the plane (no corner drifting off in-plane distance is
    # fine, but the quad must be planar with the surface).
    check(f"{prefix} quad is planar with the surface",
          max(distances) - min(distances) < 1e-5,
          f"spread={max(distances) - min(distances):.9f}")

    if expect_upright:
        expected_y = (Vector((0, 0, 1)) - normal * normal.dot(Vector((0, 0, 1)))).normalized()
        check(f"{prefix} local +Y is world-up projected onto the surface (upright)",
              y.dot(expected_y) > 1.0 - 1e-4, f"dot={y.dot(expected_y):.9f}")
    else:
        check(f"{prefix} local +Y lies in the face plane",
              abs(y.dot(normal)) < TOL, f"dot={y.dot(normal):.9f}")

    check(f"{prefix} local +X is perpendicular to +Y and the normal",
          abs(x.dot(y)) < TOL and abs(x.dot(normal)) < TOL)


def check_decal_data(label, decal, expected_size=None):
    prefix = f"{label} [{decal.name}]"
    mesh = decal.data

    check(f"{prefix} is the 16-vertex, 9-quad decal grid",
          len(mesh.vertices) == geometry.GRID_VERTEX_COUNT
          and len(mesh.polygons) == geometry.GRID_FACE_COUNT,
          f"{len(mesh.vertices)} verts / {len(mesh.polygons)} polys")

    uv = mesh.attributes.get("UVMap 0")
    check(f"{prefix} has Sollumz 'UVMap 0' (FLOAT2 / CORNER)",
          uv is not None and uv.data_type == 'FLOAT2' and uv.domain == 'CORNER')
    if uv is not None:
        us = [d.vector[0] for d in uv.data]
        vs = [d.vector[1] for d in uv.data]
        # The grid adds intermediate values at the border inset, but the island
        # still spans exactly 0..1, so the texture covers the whole decal.
        check(f"{prefix} UVs span the full 0-1 square",
              close(min(us), 0.0) and close(max(us), 1.0)
              and close(min(vs), 0.0) and close(max(vs), 1.0),
              f"u {min(us):.4f}..{max(us):.4f} v {min(vs):.4f}..{max(vs):.4f}")

    color = mesh.attributes.get("Color 1")
    check(f"{prefix} has Sollumz 'Color 1' (BYTE_COLOR / CORNER)",
          color is not None and color.data_type == 'BYTE_COLOR' and color.domain == 'CORNER')
    if color is not None:
        inner = set(geometry.INNER_CORNER_VERTS)
        border = sorted({round(color.data[i].color_srgb[3], 3)
                         for i, loop in enumerate(mesh.loops)
                         if loop.vertex_index not in inner})
        corners = sorted({round(color.data[i].color_srgb[3], 3)
                          for i, loop in enumerate(mesh.loops)
                          if loop.vertex_index in inner})
        check(f"{prefix} the border ring is alpha 0", border == [0.0], str(border))
        check(f"{prefix} the inner rectangle is alpha 1.0 (255)",
              all(close(a, 1.0, 1e-3) for a in corners), str(corners))

    check(f"{prefix} normals face outward (poly normal is local +Z)",
          mesh.polygons[0].normal.dot(Vector((0, 0, 1))) > 1.0 - TOL)

    if expected_size is not None:
        width, height = expected_size
        xs = [v.co.x for v in mesh.vertices]
        ys = [v.co.y for v in mesh.vertices]
        check(f"{prefix} outer boundary matches Width/Height",
              close(max(xs) - min(xs), width, 1e-5) and close(max(ys) - min(ys), height, 1e-5),
              f"{max(xs) - min(xs):.6f} x {max(ys) - min(ys):.6f} vs {width} x {height}")


def check_decal_material(label, decal):
    prefix = f"{label} [{decal.name}]"
    check(f"{prefix} has exactly one material", len(decal.data.materials) == 1)
    if not decal.data.materials:
        return None
    mat = decal.data.materials[0]
    check(f"{prefix} material is a Sollumz shader using decal.sps",
          getattr(mat, "shader_properties", None) is not None
          and mat.shader_properties.filename == "decal.sps",
          getattr(getattr(mat, "shader_properties", None), "filename", "<none>"))
    node = szi.get_diffuse_node(mat)
    check(f"{prefix} DiffuseSampler has an image assigned",
          node is not None and node.image is not None)
    if node is not None and node.image is not None:
        check(f"{prefix} exported texture name comes from the file name",
              node.sollumz_texture_name == os.path.splitext(os.path.basename(node.image.filepath))[0],
              node.sollumz_texture_name)
        check(f"{prefix} image keeps straight alpha", node.image.alpha_mode == 'STRAIGHT',
              node.image.alpha_mode)
    return mat


# ---------------------------------------------------------------------- cases

def run_transform_case(label, source, settings, expect_upright_by_index):
    clear_decals()
    select_all_faces(source)
    faces = world_faces(source)

    result = call_create()
    leave_edit()

    check(f"{label}: operator finished", result == {'FINISHED'}, str(result))
    decals = decal_objects()
    check(f"{label}: one decal per selected face", len(decals) == len(faces),
          f"{len(decals)} decals / {len(faces)} faces")

    # Match each decal to its face by nearest center; independent of ordering.
    for decal in decals:
        best = min(faces, key=lambda f: (f[0] + f[1] * settings.surface_offset - decal.location).length)
        index = faces.index(best)
        center, normal = best
        check_decal_against_face(label, decal, center, normal, settings.surface_offset,
                                 expect_upright_by_index[index])
    return decals


def check_tangent_matrix(source, settings):
    """Prove the floor/ceiling tangent uses the linear part, not the normal matrix.

    Both choices survive the flush test (the in-plane projection puts either back
    on the surface), so the difference only shows up as the decal's in-plane
    direction. This compares the generated +Y against both candidates and
    requires the linear-part one to win - and asserts the two actually differ, so
    the test cannot pass vacuously.
    """
    label = "tangent matrix"
    m = source.matrix_world
    linear = m.to_3x3()
    normal_matrix = m.inverted_safe().transposed().to_3x3()

    bm = bmesh.new()
    bm.from_mesh(source.data)
    bm.faces.ensure_lookup_table()
    local = [(f.calc_center_median().copy(), f.normal.copy(), f.calc_tangent_edge_pair().copy())
             for f in bm.faces]
    bm.free()

    clear_decals()
    select_all_faces(source)
    call_create()
    leave_edit()

    discriminating = []
    for center_l, normal_l, tangent_l in local:
        n = (normal_matrix @ normal_l).normalized()
        if abs(n.dot(Vector((0, 0, 1)))) <= geometry.UP_PARALLEL_THRESHOLD:
            continue  # wall/slanted uses world-up, not the tangent

        center = m @ center_l
        decal = min(decal_objects(), key=lambda d: (d.location - center).length)
        y = decal.matrix_world.to_3x3().col[1].normalized()

        def projected(matrix):
            t = matrix @ tangent_l
            t = t - n * t.dot(n)
            return t.normalized()

        right = projected(linear)
        wrong = projected(normal_matrix)

        check(f"{label}: +Y follows the linear-part tangent [{decal.name}]",
              abs(y.dot(right)) > 1.0 - 1e-4, f"dot={y.dot(right):.9f}")

        # On an axis-aligned quad the edge tangent is an eigenvector of the scale,
        # so both matrices give the same direction and there is nothing to tell
        # apart. Only the non-axis-aligned face is a real discriminator.
        if abs(right.dot(wrong)) < 1.0 - 1e-4:
            discriminating.append(decal.name)
            check(f"{label}: +Y does NOT follow the normal-matrix tangent [{decal.name}]",
                  abs(y.dot(wrong)) < 1.0 - 1e-4, f"dot={y.dot(wrong):.9f}")

    check(f"{label}: at least one face actually distinguished the two matrices",
          bool(discriminating), "no face had differing candidate tangents")


def check_coplanar_merge(settings):
    """Touching faces in the same plane must read as one surface, not N."""
    label = "coplanar merge"
    clear_decals()

    settings.width = 0.3
    settings.height = 0.3
    settings.random_position = False
    settings.random_rotation = False
    settings.random_scale = False
    settings.random_texture = False

    def build(cuts, name):
        """A 2m cube with its +X side cut into `cuts + 1` horizontal strips."""
        bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
        cube = bpy.context.active_object
        cube.name = name
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.subdivide(number_cuts=cuts)
        bpy.ops.object.mode_set(mode='OBJECT')
        return cube

    def select_plus_x(cube):
        bpy.context.view_layer.objects.active = cube
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        picked = [p for p in cube.data.polygons if p.normal.x > 0.99]
        for poly in picked:
            poly.select = True
        return picked

    # Two coplanar halves - the case from the screenshot.
    cube = build(1, "coplanar_2")
    picked = select_plus_x(cube)
    check(f"{label}: the test side really is split in two", len(picked) == 4, str(len(picked)))
    bpy.ops.object.mode_set(mode='EDIT')
    call_create()
    leave_edit()
    decals = decal_objects()
    check(f"{label}: {len(picked)} coplanar faces make ONE decal", len(decals) == 1,
          str(len(decals)))
    if decals:
        decal = decals[0]
        check(f"{label}: it faces the same way as the merged surface",
              decal.matrix_world.to_3x3().col[2].normalized().x > 1.0 - TOL,
              str(tuple(decal.matrix_world.to_3x3().col[2])))
        check(f"{label}: it is centred on the whole surface, not on one piece",
              close(decal.location.y, 0.0, 1e-4) and close(decal.location.z, 0.0, 1e-4),
              f"{tuple(decal.location)}")
        check(f"{label}: the merged extent covers the whole side",
              close(decal.seto_decal_data.extent_u, 1.0, 1e-4)
              and close(decal.seto_decal_data.extent_v, 1.0, 1e-4),
              f"{decal.seto_decal_data.extent_u:.4f} x {decal.seto_decal_data.extent_v:.4f}")
    clear_decals()
    bpy.data.objects.remove(cube, do_unlink=True)

    # Many pieces, not just two.
    cube = build(3, "coplanar_many")
    picked = select_plus_x(cube)
    check(f"{label}: the second test side is split into many", len(picked) >= 9,
          str(len(picked)))
    bpy.ops.object.mode_set(mode='EDIT')
    call_create()
    leave_edit()
    check(f"{label}: {len(picked)} coplanar faces still make ONE decal",
          len(decal_objects()) == 1, str(len(decal_objects())))
    clear_decals()

    # Two sides at once: coplanar within each side, but not with each other.
    bpy.context.view_layer.objects.active = cube
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    for poly in cube.data.polygons:
        if poly.normal.x > 0.99 or poly.normal.z > 0.99:
            poly.select = True
    bpy.ops.object.mode_set(mode='EDIT')
    call_create()
    leave_edit()
    check(f"{label}: two different planes stay two decals",
          len(decal_objects()) == 2, str(len(decal_objects())))
    normals = sorted(round(d.matrix_world.to_3x3().col[2].normalized()[i], 3)
                     for d in decal_objects() for i in (0, 2) if
                     abs(d.matrix_world.to_3x3().col[2].normalized()[i]) > 0.99)
    check(f"{label}: one per plane, each facing its own way",
          len(normals) == 2, str(normals))
    clear_decals()

    # Turning the option off restores one decal per face.
    settings.merge_coplanar = False
    picked = select_plus_x(cube)
    bpy.ops.object.mode_set(mode='EDIT')
    call_create()
    leave_edit()
    check(f"{label}: Merge Coplanar off gives one decal per face",
          len(decal_objects()) == len(picked),
          f"{len(decal_objects())} vs {len(picked)}")
    settings.merge_coplanar = True

    clear_decals()
    bpy.data.objects.remove(cube, do_unlink=True)


def check_surface_walk(settings):
    """Sliding a decal past an edge must carry it onto the neighbouring face."""
    label = "surface walk"
    clear_decals()

    # A 2m cube centred on the origin: every face is at +-1 on one axis, so the
    # expected result of a walk is easy to state exactly.
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    cube = bpy.context.active_object
    cube.name = "walk_cube"

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    # Top face (+Z). MeshPolygon.index is not reliable here, so the index comes
    # from enumerate() rather than the element itself.
    top_index, top = max(enumerate(cube.data.polygons), key=lambda kv: kv[1].center.z)
    top.select = True
    top_normal = top.normal.copy()

    settings.width = 0.3
    settings.height = 0.3
    settings.surface_offset = 0.01
    settings.random_position = False
    settings.random_rotation = False
    settings.random_scale = False

    bpy.ops.object.mode_set(mode='EDIT')
    call_create()
    bpy.ops.object.mode_set(mode='OBJECT')

    decals = decal_objects()
    if not check(f"{label}: a decal was placed on the cube's top face", len(decals) == 1,
                 str(len(decals))):
        bpy.data.objects.remove(cube, do_unlink=True)
        return
    decal = decals[0]
    data = decal.seto_decal_data

    check(f"{label}: the decal remembers which face it sits on",
          data.face_index == top_index, f"{data.face_index} vs {top_index}")
    check(f"{label}: it starts on the top face",
          decal.matrix_world.to_3x3().col[2].normalized().dot(top_normal) > 1.0 - TOL)
    start_location = decal.location.copy()

    # Small slide - still on the top face, and cheap (no mesh walk needed).
    data.offset_u = 0.2
    check(f"{label}: a small slide stays on the same face",
          decal.matrix_world.to_3x3().col[2].normalized().dot(top_normal) > 1.0 - TOL,
          str(tuple(decal.matrix_world.to_3x3().col[2])))
    check(f"{label}: a small slide moves it by exactly that much",
          close((decal.location - start_location).length, 0.2, 1e-5),
          f"{(decal.location - start_location).length:.6f}")

    # Big slide - past the edge and onto the side face.
    data.offset_u = 1.5
    normal = decal.matrix_world.to_3x3().col[2].normalized()
    location = decal.location

    check(f"{label}: crossing the edge re-orients it to a side face",
          abs(normal.dot(top_normal)) < 1e-4, f"dot with top normal={normal.dot(top_normal):.6f}")
    check(f"{label}: the new normal is one of the cube's own face normals",
          any(abs(abs(normal[i]) - 1.0) < 1e-4 for i in range(3)), str(tuple(normal)))

    # It must sit on that side face: offset out along its normal, and within the
    # cube's extent on the other two axes.
    axis = max(range(3), key=lambda i: abs(normal[i]))
    check(f"{label}: it lies on the side face, lifted by Surface Offset",
          close(abs(location[axis]), 1.0 + 0.01, 1e-4), f"{location[axis]:.6f}")
    others = [i for i in range(3) if i != axis]
    check(f"{label}: it stays within the face, not hanging off in space",
          all(abs(location[i]) <= 1.0 + 1e-4 for i in others),
          str(tuple(location)))
    # 1.5 of travel from the centre: 1.0 to reach the edge, 0.5 down the side.
    check(f"{label}: the leftover travel continued down the side face",
          close(location.z, 1.0 - 0.5, 1e-4), f"z={location.z:.6f}")

    # The quad must be flush on its NEW face, not on the old one.
    plane_point = location - normal * 0.01
    distances = [(decal.matrix_world @ Vector(v.co) - plane_point).dot(normal)
                 for v in decal.data.vertices]
    check(f"{label}: the decal is flush on the face it walked onto",
          all(close(d, 0.01, 1e-4) for d in distances),
          ", ".join(f"{d:.6f}" for d in distances))
    check(f"{label}: the basis stays orthonormal after walking",
          geometry.is_orthonormal(decal.matrix_world))

    # Walking is a pure function of the slider, so dragging back must undo it.
    data.offset_u = 0.0
    check(f"{label}: sliding back returns it exactly where it started",
          vclose(decal.location, start_location, 1e-5),
          f"{tuple(decal.location)} vs {tuple(start_location)}")
    check(f"{label}: and back onto the original face",
          decal.matrix_world.to_3x3().col[2].normalized().dot(top_normal) > 1.0 - TOL)

    # Crossing two edges in one drag: over the side and onto the bottom.
    data.offset_u = 3.5
    normal = decal.matrix_world.to_3x3().col[2].normalized()
    check(f"{label}: a longer slide keeps walking across further faces",
          any(abs(abs(normal[i]) - 1.0) < 1e-4 for i in range(3))
          and abs(decal.location[max(range(3), key=lambda i: abs(normal[i]))]) > 0.9,
          f"normal={tuple(normal)} loc={tuple(decal.location)}")

    clear_decals()
    bpy.data.objects.remove(cube, do_unlink=True)
    settings.surface_offset = 0.003


def check_category_collections(source, settings):
    """decals/<category>, one child per library category, reused across runs."""
    # Only applies outside a Drawable: inside one the decal follows the
    # Drawable's own collection instead.
    label = "collections"
    previous_parent = source.parent
    source.parent = None
    clear_decals()
    for collection in [c for c in bpy.data.collections
                       if c.name.split(".")[0] in ("decals", "Dirt", "Cracks", "Leaks")]:
        bpy.data.collections.remove(collection)

    def collection_of(decal):
        return [c.name for c in decal.users_collection]

    def parents_of(name):
        return [p.name for p in bpy.data.collections
                if any(c.name == name for c in p.children)]

    settings.category = "Dirt"
    settings.texture = "dirt_01"
    select_all_faces(source)
    call_create()
    leave_edit()
    check(f"{label}: a 'decals' collection is created",
          bpy.data.collections.get("decals") is not None,
          str([c.name for c in bpy.data.collections]))
    check(f"{label}: the decal lands in its category collection",
          all("Dirt" in collection_of(d) for d in decal_objects()),
          str([collection_of(d) for d in decal_objects()]))
    check(f"{label}: the category collection sits inside 'decals'",
          parents_of("Dirt") == ["decals"], str(parents_of("Dirt")))
    check(f"{label}: the name carries no 'seto' prefix",
          not any("seto" in c.name.lower() for c in bpy.data.collections),
          str([c.name for c in bpy.data.collections]))

    # A second category gets its own child, alongside the first.
    settings.category = "Cracks"
    settings.texture = "crack_01"
    select_all_faces(source)
    call_create()
    leave_edit()
    check(f"{label}: a second category gets its own child collection",
          parents_of("Cracks") == ["decals"], str(parents_of("Cracks")))
    decals_root = bpy.data.collections["decals"]
    check(f"{label}: both categories live under the same 'decals'",
          {c.name for c in decals_root.children} == {"Dirt", "Cracks"},
          str([c.name for c in decals_root.children]))

    # Running the same category again must reuse, not duplicate.
    settings.category = "Dirt"
    settings.texture = "dirt_01"
    select_all_faces(source)
    call_create()
    leave_edit()
    check(f"{label}: re-running a category reuses its collection",
          len([c for c in bpy.data.collections if c.name.split(".")[0] == "Dirt"]) == 1,
          str([c.name for c in bpy.data.collections]))
    check(f"{label}: only one 'decals' root exists",
          len([c for c in bpy.data.collections if c.name.split(".")[0] == "decals"]) == 1)

    # An unrelated collection of the same name must not be hijacked or moved.
    stray = bpy.data.collections.new("Leaks")
    bpy.context.scene.collection.children.link(stray)
    settings.category = "Leaks"
    settings.texture = "leak_01"
    select_all_faces(source)
    call_create()
    leave_edit()
    check(f"{label}: an unrelated same-named collection is left where it was",
          stray.name in [c.name for c in bpy.context.scene.collection.children],
          str([c.name for c in bpy.context.scene.collection.children]))
    check(f"{label}: the decals still got a category collection under 'decals'",
          any(c.name.split(".")[0] == "Leaks" for c in decals_root.children),
          str([c.name for c in decals_root.children]))
    # ...and running it again must not pile up another one.
    before = len([c for c in bpy.data.collections if c.name.split(".")[0] == "Leaks"])
    select_all_faces(source)
    call_create()
    leave_edit()
    check(f"{label}: repeating that category does not pile up more collections",
          len([c for c in bpy.data.collections if c.name.split(".")[0] == "Leaks"]) == before,
          str([c.name for c in bpy.data.collections if c.name.split(".")[0] == "Leaks"]))

    clear_decals()
    settings.category = "Dirt"
    settings.texture = "dirt_01"
    source.parent = previous_parent


def main():
    tmp_root = tempfile.mkdtemp(prefix="seto_decal_verify_")
    lib_root = os.path.join(tmp_root, "Decals")
    print(f"\n=== temp library: {lib_root}\n")

    # The add-on may already be enabled as an installed add-on in this Blender;
    # registering twice raises, so only register (and unregister) if it is not.
    already_enabled = getattr(bpy.types, "SETO_PT_decal_tool_panel", None) is not None
    if not already_enabled:
        seto_tools.register()
    else:
        print("       (seto_decal_tool was already enabled in this Blender)")
    try:
        # 0. Sollumz
        available, message = szi.get_status_message()
        check("Sollumz is available", available, message)
        if not available:
            return

        settings = bpy.context.scene.seto_decal

        # 1. Library scanning
        build_library(lib_root)
        preferences.set_library_path(lib_root)
        categories = library.get_categories()
        check("library rescans automatically when the path changes",
              set(categories) == {"Broken", "Cracks", "Dirt", "Leaks", "Mixed"}, str(categories))
        check("Dirt category lists all 3 textures",
              [s for s, _ in library.get_textures("Dirt")] == ["dirt_01", "dirt_02", "dirt_03"])

        write_png(os.path.join(lib_root, "Dirt", "dirt_07.png"), (0.2, 0.2, 0.2, 1.0))
        check("a new file is NOT picked up before Refresh",
              [s for s, _ in library.get_textures("Dirt")] == ["dirt_01", "dirt_02", "dirt_03"])
        bpy.ops.seto.refresh_decal_library()
        check("Refresh Library picks up the new file",
              "dirt_07" in [s for s, _ in library.get_textures("Dirt")],
              str([s for s, _ in library.get_textures("Dirt")]))

        # 1b. The library folder survives opening a different file
        prefs = preferences.get_preferences()
        check("the library folder is stored in the add-on preferences",
              prefs is not None and prefs.library_path == lib_root,
              str(getattr(prefs, "library_path", None)))
        bpy.ops.wm.read_homefile(use_empty=True)
        check("a brand new file still has the library folder",
              preferences.get_library_path() == lib_root,
              preferences.get_library_path())
        check("a brand new file still has its categories, with no Refresh",
              set(library.get_categories()) == {"Broken", "Cracks", "Dirt", "Leaks", "Mixed"},
              str(library.get_categories()))
        # Whether the file is already dirty depends on the rest of this Blender's
        # add-ons, so what is checked is that OUR load handler does not dirty it.
        dirty_before = bpy.data.is_dirty
        properties._on_blend_file_loaded(None)
        check("our file-load handler writes nothing into the opened file",
              bpy.data.is_dirty == dirty_before,
              f"{dirty_before} -> {bpy.data.is_dirty}")
        settings = bpy.context.scene.seto_decal
        settings.category = "Dirt"
        check("Category/Texture are usable straight away",
              [s for s, _ in library.get_textures("Dirt")][:3] == ["dirt_01", "dirt_02", "dirt_03"])

        # 2. Source mesh + Sollumz Drawable
        source = build_test_mesh()
        drawable = bpy.data.objects.new("test_drawable", None)
        bpy.context.scene.collection.objects.link(drawable)
        sollumz_properties = szi._import("sollumz_properties")
        drawable.sollum_type = sollumz_properties.SollumType.DRAWABLE
        source.parent = drawable

        source_snapshot = (
            [tuple(v.co) for v in source.data.vertices],
            len(source.data.polygons),
            [uv.name for uv in source.data.uv_layers],
            [a.name for a in source.data.color_attributes],
            [m.name if m else None for m in source.data.materials],
        )

        settings.category = "Dirt"
        settings.texture = "dirt_01"
        settings.width = 0.4
        settings.height = 0.25
        settings.surface_offset = 0.003

        # floor(+Z) and ceiling(-Z) use the tangent fallback; wall and slant are upright
        upright = [False, False, True, True, False]

        # 3/5. Alignment across transforms
        transform_cases = [
            ("identity", Matrix.Identity(4)),
            ("uniform scale 2.0", Matrix.Diagonal((2.0, 2.0, 2.0, 1.0))),
            ("non-uniform scale (0.5, 3.0, 1.2)", Matrix.Diagonal((0.5, 3.0, 1.2, 1.0))),
            ("rotated (37, 12, 55)",
             Euler((math.radians(37), math.radians(12), math.radians(55)), 'XYZ').to_matrix().to_4x4()),
            ("rotated + non-uniform scale",
             Matrix.Translation((3.0, -2.0, 1.5))
             @ Euler((math.radians(37), math.radians(12), math.radians(55)), 'XYZ').to_matrix().to_4x4()
             @ Matrix.Diagonal((0.5, 3.0, 1.2, 1.0))),
        ]
        for label, matrix in transform_cases:
            source.matrix_world = matrix
            bpy.context.view_layer.update()
            decals = run_transform_case(label, source, settings, upright)
            if label == "identity":
                for decal in decals:
                    check_decal_data(label, decal, expected_size=(0.4, 0.25))
                    check_decal_material(label, decal)
                    check(f"{label} [{decal.name}] is parented to the Drawable",
                          decal.parent is drawable, str(decal.parent))
                    check(f"{label} [{decal.name}] is a Sollumz Drawable Model",
                          decal.sollum_type == sollumz_properties.SollumType.DRAWABLE_MODEL,
                          decal.sollum_type)
                    names = sorted(c.name for c in decal.users_collection)
                    expected = sorted(c.name for c in drawable.users_collection)
                    check(f"{label} [{decal.name}] follows the Drawable's collection",
                          names == expected, f"{names} vs {expected}")

        # The tangent branch needs the WORLD normal to stay near +-Z, so this uses
        # a Z-only rotation with non-uniform X/Y scale: the floor and ceiling stay
        # horizontal while the linear part and the normal matrix diverge in-plane.
        source.matrix_world = (
            Matrix.Translation((3.0, -2.0, 1.5))
            @ Matrix.Rotation(math.radians(55), 4, 'Z')
            @ Matrix.Diagonal((0.5, 3.0, 1.2, 1.0))
        )
        bpy.context.view_layer.update()
        check_tangent_matrix(source, settings)

        source.matrix_world = Matrix.Identity(4)
        bpy.context.view_layer.update()

        # 4. Rotation happens around the face normal
        clear_decals()
        settings.rotation = 0.0
        select_all_faces(source)
        call_create()
        leave_edit()
        base = {d.location.copy().freeze(): d.matrix_world.to_3x3().col[0].normalized()
                for d in decal_objects()}
        base_normals = {d.location.copy().freeze(): d.matrix_world.to_3x3().col[2].normalized()
                        for d in decal_objects()}

        clear_decals()
        settings.rotation = math.radians(45.0)
        select_all_faces(source)
        call_create()
        leave_edit()
        for decal in decal_objects():
            key = min(base.keys(), key=lambda k: (Vector(k) - decal.location).length)
            x0 = base[key]
            n = base_normals[key]
            x1 = decal.matrix_world.to_3x3().col[0].normalized()
            angle = math.degrees(math.atan2(x0.cross(x1).dot(n), x0.dot(x1)))
            check(f"rotation 45 deg spins around the face normal [{decal.name}]",
                  close(angle, 45.0, 1e-3), f"{angle:.6f} deg")
            check(f"rotation keeps the decal on the surface [{decal.name}]",
                  decal.matrix_world.to_3x3().col[2].normalized().dot(n) > 1.0 - TOL)
        settings.rotation = 0.0

        # 6. Randomization, evaluated per face
        clear_decals()
        settings.random_rotation = True
        settings.random_scale = True
        settings.random_texture = True
        settings.rotation_min = 0.0
        settings.rotation_max = math.tau
        settings.scale_min = 0.75
        settings.scale_max = 1.25

        select_all_faces(source)
        call_create()
        leave_edit()
        decals = decal_objects()
        check("randomized run still creates one decal per face", len(decals) == 5, str(len(decals)))
        widths = {round(max(v.co.x for v in d.data.vertices) * 2, 6) for d in decals}
        check("random scale gives each decal its own size", len(widths) >= 4, str(widths))
        check("random scale stays inside Min/Max",
              all(0.4 * 0.75 - 1e-6 <= w <= 0.4 * 1.25 + 1e-6 for w in widths), str(widths))
        for decal in decals:
            check_decal_data("random", decal)
            check_decal_material("random", decal)

        stems = set()
        rotations = set()
        for _ in range(6):
            clear_decals()
            select_all_faces(source)
            call_create()
            leave_edit()
            for decal in decal_objects():
                node = szi.get_diffuse_node(decal.data.materials[0])
                stems.add(os.path.splitext(os.path.basename(node.image.filepath))[0])
                rotations.add(round(decal.matrix_world.to_3x3().col[0].x, 6))
        check("random texture varies across generated decals", len(stems) > 1, str(sorted(stems)))
        check("random rotation varies across generated decals", len(rotations) > 4, str(len(rotations)))

        settings.random_rotation = False
        settings.random_scale = False
        settings.random_texture = False

        # 6b. Random Position spreads decals instead of stacking them
        clear_decals()
        settings.random_position = True
        settings.width = 0.2
        settings.height = 0.2
        select_all_faces(source)
        call_create()
        leave_edit()
        for decal in decal_objects():
            data = decal.seto_decal_data
            check("random position stayed inside the face [%s]" % decal.name,
                  abs(data.offset_u) <= data.extent_u + 1e-6
                  and abs(data.offset_v) <= data.extent_v + 1e-6,
                  f"u={data.offset_u:.4f}/{data.extent_u:.4f} v={data.offset_v:.4f}/{data.extent_v:.4f}")
        faces_now = world_faces(source)
        for decal in decal_objects():
            best = min(faces_now, key=lambda f: (f[0] - decal.location).length)
            distances = [(decal.matrix_world @ Vector(v.co) - best[0]).dot(best[1])
                         for v in decal.data.vertices]
            check(f"randomly placed decal is still flush on its face [{decal.name}]",
                  all(close(d, settings.surface_offset, 1e-4) for d in distances),
                  ", ".join(f"{d:.6f}" for d in distances))

        # Pressing Create repeatedly on ONE face must not stack them any more.
        clear_decals()
        bpy.context.view_layer.objects.active = source
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        source.data.polygons[0].select = True
        positions = []
        for _ in range(4):
            bpy.ops.object.mode_set(mode='EDIT')
            call_create()
            bpy.ops.object.mode_set(mode='OBJECT')
        positions = [tuple(round(c, 5) for c in d.location) for d in decal_objects()]
        check("four presses on ONE face no longer stack at the same point",
              len(set(positions)) == 4, str(positions))

        settings.random_position = False
        settings.width = 0.4
        settings.height = 0.25

        # 6c. Live editing of a placed decal
        clear_decals()
        select_all_faces(source)
        call_create()
        leave_edit()
        decal = decal_objects()[0]
        data = decal.seto_decal_data
        check("created decal is marked for live editing", data.is_seto_decal)
        check("created decal remembers its source", data.source_object is source)
        check("created decal remembers its texture", data.texture_stem == "dirt_01", data.texture_stem)
        check("stored settings match what it was created with",
              close(data.width, 0.4) and close(data.height, 0.25)
              and close(data.surface_offset, 0.003),
              f"{data.width}/{data.height}/{data.surface_offset}")

        normal = Vector(data.frame_normal)
        plane_point = Vector(data.frame_center)

        def surface_distance(d):
            return [(d.matrix_world @ Vector(v.co) - plane_point).dot(normal)
                    for v in d.data.vertices]

        data.width = 0.8
        data.height = 0.6
        xs = [v.co.x for v in decal.data.vertices]
        ys = [v.co.y for v in decal.data.vertices]
        check("dragging Width/Height resizes the quad live",
              close(max(xs) - min(xs), 0.8, 1e-5) and close(max(ys) - min(ys), 0.6, 1e-5),
              f"{max(xs) - min(xs):.4f} x {max(ys) - min(ys):.4f}")
        check("resizing keeps it flush on the surface",
              all(close(d, 0.003, 1e-5) for d in surface_distance(decal)),
              str(surface_distance(decal)))
        check("resizing keeps UVs and material intact",
              decal.data.attributes.get("UVMap 0") is not None
              and decal.data.attributes.get("Color 1") is not None
              and len(decal.data.materials) == 1)

        before = decal.location.copy()
        data.offset_u = 0.3
        moved = decal.location - before
        check("Offset U slides it along the face's first axis",
              close(moved.length, 0.3, 1e-5)
              and moved.normalized().dot(Vector(data.frame_x)) > 1.0 - 1e-4,
              f"moved {moved.length:.6f}")
        check("sliding keeps it flush on the surface",
              all(close(d, 0.003, 1e-5) for d in surface_distance(decal)))

        data.offset_v = -0.2
        check("Offset V slides it along the face's second axis",
              close((decal.location - before).dot(Vector(data.frame_y)), -0.2, 1e-5))

        # Rotation must spin in place - it must NOT drag the decal along.
        spun_from = decal.location.copy()
        x_before = decal.matrix_world.to_3x3().col[0].normalized()
        data.rotation = math.radians(30.0)
        x_after = decal.matrix_world.to_3x3().col[0].normalized()
        angle = math.degrees(math.atan2(x_before.cross(x_after).dot(normal), x_before.dot(x_after)))
        check("dragging Rotation spins around the surface normal", close(angle, 30.0, 1e-3),
              f"{angle:.6f} deg")
        check("rotating does NOT slide the decal", vclose(decal.location, spun_from, 1e-6),
              f"{tuple(decal.location)} vs {tuple(spun_from)}")

        data.surface_offset = 0.02
        check("dragging Surface Offset lifts it along the normal",
              all(close(d, 0.02, 1e-5) for d in surface_distance(decal)),
              str(surface_distance(decal)))

        bpy.context.view_layer.objects.active = decal
        bpy.ops.seto.decal_reset_position()
        check("Center on Face returns it to the face center",
              close(data.offset_u, 0.0) and close(data.offset_v, 0.0)
              and vclose(decal.location, plane_point + normal * 0.02, 1e-5))

        data.live_update = False
        held = decal.location.copy()
        data.offset_u = 0.15
        check("Live Update off holds the change back", vclose(decal.location, held, 1e-9))
        bpy.ops.seto.decal_rebuild()
        check("Update Now applies it", not vclose(decal.location, held, 1e-6))
        data.live_update = True

        check("live editing never changed the object's scale",
              vclose(decal.scale, (1.0, 1.0, 1.0)))
        check("live editing kept the basis orthonormal",
              geometry.is_orthonormal(decal.matrix_world))

        # 6d. Vertex colour - per-corner alpha over the border grid. The corner
        # behaviour itself is covered in detail by corner_alpha.py; what this
        # checks is that a freshly created decal starts in the right state.
        check("there is no creation-time opacity setting any more",
              not hasattr(settings, "alpha"), "scene settings still expose 'alpha'")

        clear_decals()
        select_all_faces(source)
        call_create()
        leave_edit()
        decal = decal_objects()[0]
        colour = decal.data.attributes["Color 1"].data
        inner = set(geometry.INNER_CORNER_VERTS)

        def loop_alphas(wanted_inner):
            return sorted({round(colour[i].color_srgb[3], 3)
                           for i, loop in enumerate(decal.data.loops)
                           if (loop.vertex_index in inner) == wanted_inner})

        check("a new decal is opaque inside and 0 on its border",
              loop_alphas(True) == [1.0] and loop_alphas(False) == [0.0],
              f"inner {loop_alphas(True)} border {loop_alphas(False)}")
        check("the decal starts with alpha 1.0 in its settings",
              all(close(a, 1.0) for a in decal.seto_decal_data.corner_alpha),
              str(tuple(decal.seto_decal_data.corner_alpha)))

        decal.seto_decal_data.corner_alpha = (0.4,) * 4
        check("dragging the corner alphas rewrites Color 1 live",
              loop_alphas(True) == [0.4], str(loop_alphas(True)))
        check("the border stays at 0 while corners change",
              loop_alphas(False) == [0.0], str(loop_alphas(False)))

        # RGB must survive an alpha change untouched - it is the shared
        # #00B200 the other tools write, not white.
        from seto_tools.shared import vertex_color
        check("changing alpha does not disturb the RGB",
              all(all(close(d.color_srgb[i], vertex_color.DEFAULT_RGB[i], 1e-2)
                      for i in range(3)) for d in colour),
              str({tuple(round(c, 2) for c in d.color_srgb[:3]) for d in colour}))
        check("changing alpha leaves the geometry and material alone",
              len(decal.data.vertices) == geometry.GRID_VERTEX_COUNT
              and len(decal.data.materials) == 1
              and decal.data.attributes.get("UVMap 0") is not None)

        decal.seto_decal_data.corner_alpha = (1.0,) * 4

        # 6e. Texture thumbnails
        path = library.texture_path("Dirt", "dirt_01")
        check("library exposes the path of a named texture", os.path.isfile(path), path)
        icon_id = previews.get_icon_id(path)
        # Blender only renders preview icons when there is a UI, so in -b a
        # loaded preview still reports icon_id 0. "Did it load" is the testable
        # part here; the icon itself is checked by eye in the panel.
        check("a thumbnail loads for a real texture",
              previews.is_loaded(path) and not previews.failed_to_load(path),
              f"icon_id={icon_id} (0 is expected in background mode)")
        check("the same thumbnail is served from cache on the next draw",
              previews.get_icon_id(path) == icon_id)
        missing = os.path.join(lib_root, "nope.png")
        check("a missing file yields no thumbnail instead of raising",
              previews.get_icon_id(missing) == 0 and previews.failed_to_load(missing))
        check("an empty path yields no thumbnail", previews.get_icon_id("") == 0)
        check("generated decals remember their texture path",
              os.path.isfile(decal.seto_decal_data.texture_path),
              decal.seto_decal_data.texture_path)
        check("thumbnails do not leak into bpy.data.images",
              not any(i.filepath and "dirt_01" in i.filepath and i.users == 0
                      for i in bpy.data.images))

        # 6f. Panel layout: the long sections are collapsible children
        children = {
            "SETO_PT_decal_placement_panel": "Placement",
            "SETO_PT_decal_random_panel": "Randomization",
            "SETO_PT_decal_material_panel": "Material",
            "SETO_PT_decal_object_panel": "Selected Decal",
        }
        for idname, label in children.items():
            panel = getattr(bpy.types, idname, None)
            check(f"'{label}' is a sub-panel of Decal Tool",
                  panel is not None and panel.bl_parent_id == "SETO_PT_decal_tool_panel",
                  str(panel))
        for idname in ("SETO_PT_decal_placement_panel", "SETO_PT_decal_random_panel",
                       "SETO_PT_decal_material_panel"):
            panel = getattr(bpy.types, idname, None)
            check(f"{idname} starts collapsed",
                  panel is not None and 'DEFAULT_CLOSED' in panel.bl_options)

        # 6f2. Collection layout: decals/<category>
        check_category_collections(source, settings)

        # 6f3. Coplanar faces read as one surface
        check_coplanar_merge(settings)

        # 6g. Sliding across an edge onto the neighbouring face
        check_surface_walk(settings)
        settings.width = 0.4
        settings.height = 0.25

        # 7. Source mesh untouched
        after = (
            [tuple(v.co) for v in source.data.vertices],
            len(source.data.polygons),
            [uv.name for uv in source.data.uv_layers],
            [a.name for a in source.data.color_attributes],
            [m.name if m else None for m in source.data.materials],
        )
        check("source mesh is completely untouched", after == source_snapshot,
              f"{source_snapshot} -> {after}")

        # 8. Material reuse
        clear_decals()
        for material in [m for m in bpy.data.materials if m.name.startswith("seto_decal_mat_")]:
            bpy.data.materials.remove(material)

        settings.category = "Cracks"
        settings.texture = "crack_01"
        settings.material_mode = 'AUTO'
        for _ in range(2):
            select_all_faces(source)
            call_create()
            leave_edit()
        crack_materials = [m.name for m in bpy.data.materials if m.name.startswith("seto_decal_mat_crack_01")]
        check("the same texture reuses one material across runs",
              len(crack_materials) == 1, str(crack_materials))

        settings.texture = "crack_02"
        select_all_faces(source)
        call_create()
        leave_edit()
        check("a different texture gets its own material",
              len([m for m in bpy.data.materials if m.name.startswith("seto_decal_mat_crack_02")]) == 1)
        first = [d for d in decal_objects() if d.name.startswith("seto_decal_crack_01")][0]
        node = szi.get_diffuse_node(first.data.materials[0])
        check("the earlier decal still points at its own texture",
              node.image is not None and "crack_01" in node.image.filepath, node.image.filepath)

        # 9. Failure cleanup - every requested decal fails
        clear_decals()
        os.remove(os.path.join(lib_root, "Broken", "broken_01.png"))
        settings.category = "Broken"
        settings.texture = "broken_01"
        before_objects = len(bpy.data.objects)
        select_all_faces(source)
        result = call_create()
        leave_edit()
        check("a fully failed run reports CANCELLED", result == {'CANCELLED'}, str(result))
        check("a fully failed run creates no decal objects", len(decal_objects()) == 0)
        check("a fully failed run adds no objects at all", len(bpy.data.objects) == before_objects)
        check("a fully failed run leaves zero orphan meshes",
              not orphan_decal_meshes(), str(orphan_decal_meshes()))

        # 10. Failure cleanup - partial failure keeps the good decals
        os.remove(os.path.join(lib_root, "Mixed", "mixed_bad.png"))
        settings.category = "Mixed"
        settings.random_texture = True
        partial_seen = False
        for _ in range(25):
            clear_decals()
            select_all_faces(source)
            result = call_create()
            leave_edit()
            created = len(decal_objects())
            if result == {'FINISHED'} and 0 < created < 5:
                partial_seen = True
                check("a partial failure keeps the decals that worked", created > 0, str(created))
                check("a partial failure leaves zero orphan meshes",
                      not orphan_decal_meshes(), str(orphan_decal_meshes()))
                check("no decal was created for the broken texture",
                      all("mixed_bad" not in d.name for d in decal_objects()),
                      str([d.name for d in decal_objects()]))
                break
        check("a partial-failure run was observed", partial_seen,
              "random texture never drew the broken file in 25 runs")
        settings.random_texture = False

        # 11. Empty / missing library errors
        clear_decals()
        preferences.set_library_path(os.path.join(tmp_root, "does_not_exist"))
        check("a missing library folder clears the cache", not library.get_categories())
        check("the library folder is remembered outside the scene",
              not hasattr(bpy.context.scene.seto_decal, "library_path"),
              "library_path is still a scene property")
        select_all_faces(source)
        result = call_create()
        leave_edit()
        check("creating with no library reports CANCELLED", result == {'CANCELLED'}, str(result))

        # 12. Object-mode guard
        preferences.set_library_path(lib_root)
        bpy.ops.seto.refresh_decal_library()
        settings.category = "Dirt"
        settings.texture = "dirt_01"
        leave_edit()
        result = call_create()
        check("creating outside Edit Mode reports CANCELLED", result == {'CANCELLED'}, str(result))

        # 13. Standalone fallback when the source has no Drawable
        clear_decals()
        source.parent = None
        select_all_faces(source)
        result = call_create()
        leave_edit()
        check("a source without a Drawable still creates decals", result == {'FINISHED'}, str(result))
        check("those decals are standalone and filed by category",
              all(d.parent is None and "Dirt" in [c.name for c in d.users_collection]
                  for d in decal_objects()))
        check("only one 'decals' collection exists",
              len([c for c in bpy.data.collections if c.name.startswith("decals")]) == 1,
              str([c.name for c in bpy.data.collections]))

    finally:
        leave_edit()
        if not already_enabled:
            seto_tools.unregister()
        shutil.rmtree(tmp_root, ignore_errors=True)


try:
    main()
except Exception:
    traceback.print_exc()
    RESULTS.append((False, "verification script crashed", ""))

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 70)
print(f"RESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
for _, name, detail in failed:
    print(f"  FAIL  {name}  -- {detail}")
print("=" * 70)
sys.exit(1 if failed else 0)
