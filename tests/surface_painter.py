"""Surface Painter: the decal projection, dragging, and what Optimize keeps.

The two checks worth understanding before changing anything here:

* the paint mesh's UVs must be one AFFINE function of position. Islands or a
  repeat break that fit and nothing else does, and an island is what made a
  loop-cut wall draw the decal twice.
* dragging must leave the texture point you grabbed under the pointer, at every
  Width, Height and Rotation. That single invariant catches a wrong sign, a
  missing divide by the size, and a missing rotation, all separately.
"""
import bpy, sys, os
import math
import numpy as np
from mathutils.interpolate import poly_3d_calc

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

import seto_tools
if getattr(bpy.types, "SETO_PT_surface_painter_panel", None) is None:
    seto_tools.register()

import importlib
from seto_tools.surface_painter import shell
smod = importlib.import_module("bl_ext.user_default.sollumz.ydr.shader_materials")

st = bpy.context.scene.seto_surface
st.category = "dirt"
st.texture = "Dirt_Concrete_01"
st.shell_spacing = 0.4
st.shell_offset = 0.01


def live_uv_at(obj, face_index, location):
    """The UV actually on the mesh under a point - what the eye sees there."""
    mesh = obj.data
    uv = mesh.uv_layers["UVMap 0"]
    polygon = mesh.polygons[face_index]
    corners = [mesh.vertices[i].co for i in polygon.vertices]
    weights = poly_3d_calc(corners, location)
    u = v = 0.0
    for weight, loop_index in zip(weights, polygon.loop_indices):
        u += weight * uv.uv[loop_index].vector[0]
        v += weight * uv.uv[loop_index].vector[1]
    return u, v


def surface_hit(obj, x, z):
    """Raycast the shell from in front of the wall (walls here face -Y)."""
    from mathutils import Vector
    matrix = obj.matrix_world.inverted()
    origin = matrix @ Vector((x, -3.0, z))
    direction = (matrix.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
    hit, location, _, face_index = obj.ray_cast(origin, direction)
    return hit, location, face_index


# ------------------------------------------------------------------ the wall
# A wall with a loop cut across it, unwrapped the way a real one is: two
# islands that both cover the whole 0-1 tile. This is the case that used to
# draw the decal twice.
mesh = bpy.data.meshes.new("CutWall")
verts = [(-1, 0, -1), (1, 0, -1), (1, 0, 0), (-1, 0, 0), (1, 0, 1), (-1, 0, 1)]
faces = [(0, 1, 2, 3), (3, 2, 4, 5)]
mesh.from_pydata(verts, [], faces)
mesh.update()
uv_layer = mesh.uv_layers.new(name="UVMap 0")
overlapping = [0, 0, 1, 0, 1, 1, 0, 1] * 2      # both faces map the whole tile
uv_layer.uv.foreach_set("vector", np.array(overlapping, dtype=np.float32))
wall = bpy.data.objects.new("CutWall", mesh)
bpy.context.scene.collection.objects.link(wall)
mesh.materials.append(smod.create_shader("normal_spec.sps"))
bpy.context.view_layer.objects.active = wall
wall.select_set(True)

bpy.ops.seto.surface_start_paint()
sh = shell.find_shell(wall)
bpy.ops.seto.surface_stop_paint()
check("a shell was built on the cut wall", sh is not None)

print("=== the decal is projected, so it can only appear once ===")
mesh = sh.data
uv = mesh.uv_layers["UVMap 0"]
flat = np.empty(len(uv.uv) * 2, dtype=np.float32)
uv.uv.foreach_get("vector", flat)

coords = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
mesh.vertices.foreach_get("co", coords)
coords = coords.reshape(-1, 3)
loop_verts = np.empty(len(mesh.loops), dtype=np.int32)
mesh.loops.foreach_get("vertex_index", loop_verts)
points = coords[loop_verts]

# One planar projection means UV is an affine function of position across the
# WHOLE shell. Islands or a repeat would break that fit; nothing else does.
design = np.hstack([points, np.ones((len(points), 1), dtype=np.float32)])
target = np.stack([flat[0::2], flat[1::2]], axis=1)
solution, *_ = np.linalg.lstsq(design, target, rcond=None)
residual = float(np.abs(design @ solution - target).max())
check("UV is one affine map of position - no second island", residual < 1e-4, residual)

# And the concrete symptom: the top and bottom halves of the wall must not
# land on the same part of the texture.
top = points[:, 2] > 0.05
bottom = points[:, 2] < -0.05
if top.any() and bottom.any():
    top_v = flat[1::2][top]
    bottom_v = flat[1::2][bottom]
    check("the two halves of the cut wall map to different texture rows",
          float(bottom_v.max()) < float(top_v.min()) + 1e-3,
          (float(bottom_v.max()), float(top_v.min())))

check("the layer still spans one instance",
      max(float(flat[0::2].max() - flat[0::2].min()),
          float(flat[1::2].max() - flat[1::2].min())) <= 1.0001)

print("=== +V goes up the wall, +U goes right ===")
up_loops = flat[1::2][points[:, 2] > 0.5]
down_loops = flat[1::2][points[:, 2] < -0.5]
check("higher on the wall means higher V",
      float(up_loops.mean()) > float(down_loops.mean()),
      (float(up_loops.mean()), float(down_loops.mean())))

print("=== dragging: what you grab stays under the pointer ===")
for width, height, rotation in [(1.0, 1.0, 0.0),
                                (2.0, 2.0, 0.0),
                                (1.0, 2.5, 0.0),
                                (1.6, 0.7, math.radians(37.0))]:
    label = f"W{width} H{height} R{round(math.degrees(rotation))}"
    data = sh.seto_surface_data
    data.dirt_width, data.dirt_height, data.dirt_rotation = width, height, rotation
    data.dirt_offset_u, data.dirt_offset_v = 0.0, 0.0
    shell.apply_uv_transform(sh, 0.0, 0.0, width, height, rotation)

    ok_a, loc_a, face_a = surface_hit(sh, -0.4, -0.45)
    ok_b, loc_b, face_b = surface_hit(sh, 0.35, 0.5)
    if not (ok_a and ok_b):
        check(f"raycast landed on the shell ({label})", False, (ok_a, ok_b))
        continue

    grabbed = live_uv_at(sh, face_a, loc_a)          # texture point under A
    anchor = shell.uv_at_point(sh, face_a, loc_a)
    current = shell.uv_at_point(sh, face_b, loc_b)

    offset_u, offset_v = shell.offset_for_drag(
        (0.0, 0.0), anchor, current, width, height, rotation)
    shell.apply_uv_transform(sh, offset_u, offset_v, width, height, rotation)

    landed = live_uv_at(sh, face_b, loc_b)           # texture point now under B
    error = max(abs(landed[0] - grabbed[0]), abs(landed[1] - grabbed[1]))
    check(f"the grabbed texture point followed the cursor ({label})",
          error < 2e-3, (grabbed, landed, error))

print("=== the direction the user reported ===")
data = sh.seto_surface_data
data.dirt_width = data.dirt_height = 1.0
data.dirt_rotation = 0.0
shell.apply_uv_transform(sh, 0.0, 0.0, 1.0, 1.0, 0.0)
_, loc_high, face_high = surface_hit(sh, 0.0, 0.6)
_, loc_low, face_low = surface_hit(sh, 0.0, -0.6)
high = shell.uv_at_point(sh, face_high, loc_high)
low = shell.uv_at_point(sh, face_low, loc_low)

down = shell.offset_for_drag((0.0, 0.0), high, low)
check("dragging DOWN moves the decal down, not up", down[1] < -0.05, down)
up = shell.offset_for_drag((0.0, 0.0), low, high)
check("dragging UP moves the decal up", up[1] > 0.05, up)

_, loc_left, face_left = surface_hit(sh, -0.6, 0.0)
_, loc_right, face_right = surface_hit(sh, 0.6, 0.0)
left = shell.uv_at_point(sh, face_left, loc_left)
right = shell.uv_at_point(sh, face_right, loc_right)
check("dragging RIGHT moves the decal right",
      shell.offset_for_drag((0.0, 0.0), left, right)[0] > 0.05)

check("dragging back to where it was grabbed changes nothing",
      shell.offset_for_drag((0.3, -0.2), high, high) == (0.3, -0.2))

print("=== the drag keeps working off the surface ===")
from mathutils import Vector

data = sh.seto_surface_data
data.dirt_width = data.dirt_height = 1.0
data.dirt_rotation = 0.0
shell.apply_uv_transform(sh, 0.0, 0.0, 1.0, 1.0, 0.0)
mapping = shell.projection_map(sh)
check("the projection map could be worked out", mapping is not None)


def ray_uv(obj, x, z):
    """UV the way the modal reads it: aimed at the wall from in front."""
    matrix = obj.matrix_world.inverted()
    origin = matrix @ Vector((x, -3.0, z))
    direction = (matrix.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
    return shell.uv_for_ray(mapping, origin, direction)


# On the mesh the plane must agree with the surface, or the decal would jump
# the moment the pointer crossed the silhouette.
_, loc_mid, face_mid = surface_hit(sh, 0.3, 0.2)
on_surface = shell.uv_at_point(sh, face_mid, loc_mid)
on_plane = ray_uv(sh, 0.3, 0.2)
check("on the surface, plane and mesh give the same UV",
      on_plane is not None
      and abs(on_plane[0] - on_surface[0]) < 1e-4
      and abs(on_plane[1] - on_surface[1]) < 1e-4,
      (on_surface, on_plane))

# The wall spans -1..1; these are far outside it, where ray_cast finds nothing.
outside = ray_uv(sh, 6.0, 4.0)
check("well past the edge of the wall still gives a UV", outside is not None,
      outside)

miss, _, _ = surface_hit(sh, 6.0, 4.0)
check("...and that really is off the mesh", not miss)

# And it stays linear out there, so dragging does not speed up or crawl once
# the pointer leaves the wall.
near = ray_uv(sh, 2.0, 0.0)
far = ray_uv(sh, 3.0, 0.0)
centre_uv = ray_uv(sh, 0.0, 0.0)
step_in = near[0] - centre_uv[0]
step_out = far[0] - near[0]
check("the UV keeps its scale outside the mesh",
      abs(step_out - step_in / 2.0) < 1e-4, (step_in, step_out))

check("dragging off the edge still moves the decal",
      abs(shell.offset_for_drag((0.0, 0.0), centre_uv, outside)[0]) > 0.1)

# Looking straight along the wall has no answer, and must say so rather than
# throwing or returning nonsense.
matrix = sh.matrix_world.inverted()
edge_on = shell.uv_for_ray(mapping, matrix @ Vector((0.0, -3.0, 0.0)),
                           (matrix.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized())
check("a ray parallel to the wall is refused, not guessed", edge_on is None,
      edge_on)

print("=== the modal operator's setup ===")
cursors = bpy.types.Window.bl_rna.functions['cursor_modal_set'].parameters['cursor']
check("the grab cursor name is real", 'HAND' in cursors.enum_items.keys(),
      list(cursors.enum_items.keys()))

op = bpy.types.SETO_OT_surface_move_dirt
check("Place On Surface is registered", op is not None)
check("it still offers cancel via undo", 'UNDO' in op.bl_options)

import inspect
source = inspect.getsource(op.modal)
check("the modal no longer does the drag maths itself",
      "offset_for_drag" in source and "self._start[0] -" not in source)
check("axis locking is wired up", "self._axis" in source)

reader = inspect.getsource(op._uv_under_mouse)
check("the reader falls back to the plane when the ray misses",
      "uv_for_ray" in reader and "self._mapping" in reader)
check("the map is built once, not per mouse move",
      "projection_map" in inspect.getsource(op.invoke)
      and "projection_map" not in reader)
check("the wheel is handled during the drag",
      "WHEELUPMOUSE" in source and "offset_for_scale" in source)
check("the wheel respects the slider's own limits",
      "hard_min" in source and "hard_max" in source)

print("=== Optimize crops to the paint instead of keeping the whole wall ===")
bpy.ops.mesh.primitive_plane_add(size=4, location=(20, 0, 0))
big = bpy.context.active_object
big.name = "BigWall"
bpy.ops.mesh.uv_texture_add(); big.data.uv_layers[0].name = "UVMap 0"
big.data.materials.append(smod.create_shader("normal_spec.sps"))
st.shell_spacing = 0.2
bpy.ops.seto.surface_start_paint()
psh = shell.find_shell(big)
bpy.ops.seto.surface_stop_paint()

# Paint a blob in one corner of the wall, with a soft edge, and leave the rest
# of the wall untouched - the case in the screenshot.
mesh = psh.data
attribute = mesh.color_attributes["Color 1"]
coords = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
mesh.vertices.foreach_get("co", coords)
coords = coords.reshape(-1, 3)
loop_verts = np.empty(len(mesh.loops), dtype=np.int32)
mesh.loops.foreach_get("vertex_index", loop_verts)

centre = np.array([-1.2, -1.2, 0.0], dtype=np.float32)
distance = np.linalg.norm(coords[loop_verts] - centre, axis=1)
painted = np.clip(1.0 - (distance - 0.25) / 0.35, 0.0, 1.0).astype(np.float32)

rgba = np.empty(len(mesh.loops) * 4, dtype=np.float32)
attribute.data.foreach_get("color_srgb", rgba)
rgba[3::4] = painted
attribute.data.foreach_set("color_srgb", rgba)
mesh.update()

before = len(mesh.polygons)
painted_area_before = float(np.count_nonzero(painted > 0.004))
check("the test actually painted something",
      painted_area_before > 0 and painted_area_before < len(painted))

bpy.context.view_layer.objects.active = psh
bpy.ops.seto.surface_optimize_layer()
after = len(psh.data.polygons)

# The patch must now cover the blob only. Compare its bounding box with the
# wall's: cropping means it got much smaller, thinning alone never does.
# In world space: Optimize also re-centres the origin, so local coordinates
# mean something different afterwards. The wall is at x=20, the blob at
# local (-1.2, -1.2), so world (18.8, -1.2).
opt_coords = np.array([list(psh.matrix_world @ v.co) for v in psh.data.vertices])
extent_x = float(opt_coords[:, 0].max() - opt_coords[:, 0].min())
extent_y = float(opt_coords[:, 1].max() - opt_coords[:, 1].min())

check("the layer is no longer the size of the wall",
      max(extent_x, extent_y) < 2.5, (extent_x, extent_y))
check("the painted blob is still fully covered",
      opt_coords[:, 0].min() <= 18.25 and opt_coords[:, 1].min() <= -1.75,
      (float(opt_coords[:, 0].min()), float(opt_coords[:, 1].min())))
check("the untouched half of the wall is gone",
      float(opt_coords[:, 0].max()) < 21.0 and float(opt_coords[:, 1].max()) < 1.0,
      (float(opt_coords[:, 0].max()), float(opt_coords[:, 1].max())))
check("it got much cheaper", after < before / 4, (before, after))
check("but it is not empty", after > 0)

# The fade has to survive: some corners at 0 must remain, or the decal would
# end in a hard edge where it used to fade out.
opt_attr = psh.data.color_attributes["Color 1"]
opt_rgba = np.empty(len(opt_attr.data) * 4, dtype=np.float32)
opt_attr.data.foreach_get("color_srgb", opt_rgba)
opt_alpha = opt_rgba[3::4]
check("the soft edge is kept, not cut off square",
      float(opt_alpha.min()) <= 0.02 and float(opt_alpha.max()) >= 0.9,
      (float(opt_alpha.min()), float(opt_alpha.max())))

print("=== the wheel resizes around the pointer ===")
for rotation in (0.0, math.radians(37.0)):
    label = f"R{round(math.degrees(rotation))}"
    width = height = 1.0
    data = sh.seto_surface_data
    data.dirt_rotation = rotation
    shell.apply_uv_transform(sh, 0.1, -0.05, width, height, rotation)

    _, loc_p, face_p = surface_hit(sh, 0.42, -0.3)
    under_pointer = live_uv_at(sh, face_p, loc_p)
    point = shell.uv_at_point(sh, face_p, loc_p)

    grown = (width * 1.1 ** 4, height * 1.1 ** 4)
    offset = shell.offset_for_scale((0.1, -0.05), point, (width, height),
                                    grown, rotation)
    shell.apply_uv_transform(sh, offset[0], offset[1], grown[0], grown[1], rotation)
    after_zoom = live_uv_at(sh, face_p, loc_p)
    error = max(abs(after_zoom[0] - under_pointer[0]),
                abs(after_zoom[1] - under_pointer[1]))
    check(f"what was under the pointer stayed there while resizing ({label})",
          error < 2e-3, (under_pointer, after_zoom, error))

check("resizing by nothing changes nothing",
      shell.offset_for_scale((0.2, 0.3), (0.7, 0.1), (1.5, 2.0), (1.5, 2.0))
      == (0.2, 0.3))

print("=== Optimize welds stray vertices without moving the image ===")
bpy.ops.mesh.primitive_plane_add(size=4, location=(40, 0, 0))
graf = bpy.context.active_object
graf.name = "GrafWall"
bpy.ops.mesh.uv_texture_add(); graf.data.uv_layers[0].name = "UVMap 0"
graf.data.materials.append(smod.create_shader("normal_spec.sps"))
st.shell_spacing = 0.2
bpy.ops.seto.surface_start_paint()
gsh = shell.find_shell(graf)
bpy.ops.seto.surface_stop_paint()

mesh = gsh.data
attribute = mesh.color_attributes["Color 1"]
coords = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
mesh.vertices.foreach_get("co", coords)
coords = coords.reshape(-1, 3)
loop_verts = np.empty(len(mesh.loops), dtype=np.int32)
mesh.loops.foreach_get("vertex_index", loop_verts)
spot = coords[loop_verts]
# A ragged blob, the shape a real stroke leaves.
radius = np.linalg.norm(spot[:, :2] - np.array([0.3, -0.2], dtype=np.float32), axis=1)
wobble = 0.9 + 0.25 * np.sin(np.arctan2(spot[:, 1] + 0.2, spot[:, 0] - 0.3) * 5.0)
blob = np.clip((wobble - radius) / 0.3, 0.0, 1.0).astype(np.float32)
rgba = np.empty(len(mesh.loops) * 4, dtype=np.float32)
attribute.data.foreach_get("color_srgb", rgba)
rgba[3::4] = blob
attribute.data.foreach_set("color_srgb", rgba)
mesh.update()


def sample_image(obj):
    """What the decal actually shows, over a grid of fixed points in the world.

    UV and mask together: UV says which pixel of the texture lands here, mask
    says how much of it shows. If both survive the optimisation, so does the
    picture - whatever happened to the geometry underneath.

    Sampled in WORLD space and converted per call, because Optimize moves the
    object's origin: the same local coordinate is not the same place before
    and after.
    """
    from mathutils import Vector
    out = []
    inverse = obj.matrix_world.inverted()
    for x in np.linspace(-1.6, 1.6, 21):
        for z in np.linspace(-1.6, 1.6, 21):
            origin = inverse @ Vector((float(x) + 40.0, float(z), -3.0))
            direction = (inverse.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
            hit, location, _, index = obj.ray_cast(origin, direction)
            if not hit:
                out.append((float(x), float(z), None, None, None))
                continue
            u, v = live_uv_at(obj, index, location)
            polygon = obj.data.polygons[index]
            corners = [obj.data.vertices[i].co for i in polygon.vertices]
            weights = poly_3d_calc(corners, location)
            alpha_attr = obj.data.color_attributes["Color 1"]
            alpha = sum(w * alpha_attr.data[l].color_srgb[3]
                        for w, l in zip(weights, polygon.loop_indices))
            out.append((float(x), float(z), u, v, alpha))
    return out


before_image = sample_image(gsh)
tris_before = sum(len(p.vertices) - 2 for p in gsh.data.polygons)
verts_before = len(gsh.data.vertices)

bpy.context.view_layer.objects.active = gsh
bpy.ops.seto.surface_optimize_layer()

after_image = sample_image(gsh)
tris_after = sum(len(p.vertices) - 2 for p in gsh.data.polygons)

check("it costs far fewer triangles", tris_after < tris_before / 4,
      (tris_before, tris_after))
check("the mesh got smaller",
      len(gsh.data.vertices) < verts_before, (verts_before, len(gsh.data.vertices)))
# The weld carries its safe/unsafe mark on a temporary bmesh layer. If that
# ever reached the mesh it would be exported as a third attribute.
check("the temporary weld flag did not reach the mesh",
      not [a.name for a in gsh.data.attributes if "seto" in a.name.lower()],
      [a.name for a in gsh.data.attributes])
check("the layer still carries Color 1 and UVMap 0",
      "Color 1" in gsh.data.attributes and "UVMap 0" in gsh.data.attributes)

# Compare only where the patch still exists - the cropped-away area drew
# nothing before either, which the mask check below proves.
uv_error = 0.0
mask_error = 0.0
lost = 0
for (x, z, u, v, alpha), (_, _, u2, v2, alpha2) in zip(before_image, after_image):
    if u is None:
        continue
    if u2 is None:
        # The surface went away here. Only allowed where nothing was drawn.
        lost = max(lost, alpha)
        continue
    uv_error = max(uv_error, abs(u - u2), abs(v - v2))
    mask_error = max(mask_error, abs(alpha - alpha2))

# The weld protects every face that has any paint on it, so the UVs must come
# through untouched - not "close", identical. That is the guarantee, and it is
# the one worth pinning down.
check("the texture lands on exactly the same places", uv_error < 1e-5, uv_error)
# The mask does move, but that is the thinning re-interpolating a gradient
# across fewer vertices, and it predates the weld: measured at 0.153 with
# welding switched off too.
check("the painted mask is close enough", mask_error < 0.2, mask_error)
check("nothing more than a faint rim was cropped away", lost < 0.08, lost)

print("=== the origin ends up in the middle of the patch ===")
coords = np.empty(len(gsh.data.vertices) * 3, dtype=np.float64)
gsh.data.vertices.foreach_get("co", coords)
coords = coords.reshape(-1, 3)
centre = (coords.min(axis=0) + coords.max(axis=0)) / 2.0
check("the origin sits at the centre of the mesh",
      float(np.abs(centre).max()) < 1e-4, list(centre))
check("the origin is no longer the wall's",
      (gsh.matrix_world.translation - graf.matrix_world.translation).length > 0.1,
      (list(gsh.matrix_world.translation), list(graf.matrix_world.translation)))

# It has to be a pivot move and nothing else, so this is checked on its own
# where the topology cannot change underneath it: same vertices, before and
# after, in world space.
bpy.ops.mesh.primitive_plane_add(size=2, location=(50, 1.5, 0.75))
pivot_wall = bpy.context.active_object
pivot_wall.name = "PivotWall"
bpy.ops.mesh.uv_texture_add(); pivot_wall.data.uv_layers[0].name = "UVMap 0"
pivot_wall.rotation_euler = (0.4, 0.2, 0.9)      # awkward on purpose
pivot_wall.scale = (1.3, 0.8, 1.0)
pivot_wall.data.materials.append(smod.create_shader("normal_spec.sps"))
bpy.ops.seto.surface_start_paint()
psh2 = shell.find_shell(pivot_wall)
bpy.ops.seto.surface_stop_paint()

bpy.context.view_layer.update()
world_before = [psh2.matrix_world @ v.co for v in psh2.data.vertices]
moved = shell.center_origin(psh2)
bpy.context.view_layer.update()
drift = max((psh2.matrix_world @ v.co - w).length
            for v, w in zip(psh2.data.vertices, world_before))
check("centring the origin reported that it moved", moved)
check("the mesh itself did not move, on a rotated and scaled parent",
      drift < 1e-5, drift)
check("centring again is a no-op", not shell.center_origin(psh2))

print("=== an unpainted layer is not silently deleted ===")
bpy.ops.mesh.primitive_plane_add(size=2, location=(30, 0, 0))
clean = bpy.context.active_object
clean.name = "CleanWall"
bpy.ops.mesh.uv_texture_add(); clean.data.uv_layers[0].name = "UVMap 0"
clean.data.materials.append(smod.create_shader("normal_spec.sps"))
bpy.ops.seto.surface_start_paint()
csh = shell.find_shell(clean)
bpy.ops.seto.surface_stop_paint()
check("nothing is cropped when nothing was painted",
      shell._crop_unpainted(csh) == 0)
bpy.context.view_layer.objects.active = csh
bpy.ops.seto.surface_optimize_layer()
check("an unpainted layer still collapses instead of vanishing",
      0 < len(csh.data.polygons) <= 4, len(csh.data.polygons))


failed = [r for r in RESULTS if not r[0]]
print("\n" + "="*60)
print(f"RESULT: {len(RESULTS)-len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("="*60)
sys.exit(1 if failed else 0)
