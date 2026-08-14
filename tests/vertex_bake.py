"""Vertex Color Bake - the one tool here that writes to your mesh.

That is what makes it worth pinning down. The checks in order of what
would hurt most if it broke: that the bake leaves `Color 1`'s **alpha**
alone (the alpha is what the decal shaders blend by - destroying it while
writing colour is the exact bug the colour picker was written to stop),
that it touches only the objects you selected, that it writes where GTA
reads, that its layers actually do something, and that a second run over
the same settings produces the same mesh.

It also guards the names. This tool arrived as `MLOPT_*` / `mlopt.*`,
which is another add-on's namespace: registering a class name twice is
the crash this project already has written down for Materialize's
`VMAT_*`, and the suite finds panels by the `SETO_PT_` prefix, so the old
name kept the whole tool out of every test - including the one that
drives every panel's draw().
"""
import sys

import bpy

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  -- {detail}" if detail and not cond else ""))


import seto_tools  # noqa: E402
if getattr(bpy.types, "SETO_PT_vertex_bake_panel", None) is None:
    seto_tools.register()

from seto_tools.vertex_bake import core  # noqa: E402

BYTE = 1.5 / 255.0          # BYTE_COLOR quantises; compare with a byte of slack

print("=== it lives in this add-on's namespace, not another's ===")
check("the operator is seto.vertex_bake",
      hasattr(bpy.ops.seto, "vertex_bake")
      and getattr(bpy.types, "SETO_OT_vertex_bake", None) is not None)
check("the panel is a SETO_PT_ panel, so the suite can see it",
      getattr(bpy.types, "SETO_PT_vertex_bake_panel", None) is not None)
check("its settings hang off the scene under this add-on's prefix",
      hasattr(bpy.context.scene, "seto_vertex_bake"))
check("no MLOPT_ class is registered any more",
      not [n for n in dir(bpy.types) if n.startswith("MLOPT_")],
      [n for n in dir(bpy.types) if n.startswith("MLOPT_")])
check("the panel sits in the tab, under Surface",
      bpy.types.SETO_PT_vertex_bake_panel.bl_parent_id
      == "SETO_PT_surface_group")

print("=== a bake, on a real mesh ===")
scene = bpy.context.scene
settings = scene.seto_vertex_bake
view = bpy.context.view_layer


def deselect_all():
    for obj in view.objects:
        obj.select_set(False)


def only(obj):
    deselect_all()
    obj.select_set(True)
    view.objects.active = obj


def colours(obj):
    layer = obj.data.color_attributes.get(core.VERTEX_COLOR_LAYER_NAME)
    return [tuple(item.color) for item in layer.data] if layer else []


bpy.ops.mesh.primitive_cube_add(size=2)
cube = bpy.context.active_object
cube.name = "bake_cube"
bpy.ops.mesh.primitive_plane_add(size=2, location=(5, 0, 0))
bystander = bpy.context.active_object
bystander.name = "bake_bystander"

# A room: a cube with its lid off and its normals turned in. Ambient
# Occlusion has nothing to find on a bare cube - every ray escapes a
# convex shape - so the layer can only be shown to work somewhere that
# actually occludes itself.
import bmesh  # noqa: E402
import math  # noqa: E402
from mathutils import Vector  # noqa: E402
room_mesh = bpy.data.meshes.new("bake_room")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=2.0)
bmesh.ops.delete(bm, geom=[f for f in bm.faces
                           if f.calc_center_median().z > 0.9],
                 context='FACES')
bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=3,
                          use_grid_fill=True)
bm.to_mesh(room_mesh)
bm.free()
room = bpy.data.objects.new("bake_room", room_mesh)
scene.collection.objects.link(room)

# Settings are changed with **nothing selected**: every one of them bakes
# the current selection the moment it changes (see the live-bake check
# below), and a test that set them with an object selected would be
# measuring that instead of what it meant to.
deselect_all()
view.objects.active = None
for name in ("detail_use_gradient", "detail_use_ao", "detail_use_edge_dirt",
             "detail_use_floor_grime", "detail_use_edge_wear",
             "detail_use_random", "detail_use_fake_shadow"):
    setattr(settings, name, False)
settings.detail_base_color = (1.0, 0.0, 0.0)

only(cube)
bpy.ops.seto.vertex_bake()

layer = cube.data.color_attributes.get(core.VERTEX_COLOR_LAYER_NAME)
check("the bake writes Color 1", layer is not None)
if layer is not None:
    check("as a per-corner byte colour, where GTA reads it",
          layer.data_type == 'BYTE_COLOR' and layer.domain == 'CORNER',
          (layer.data_type, layer.domain))
check("the base colour comes through",
      all(abs(c[0] - 1.0) < BYTE and c[1] < BYTE and c[2] < BYTE
          for c in colours(cube)),
      colours(cube)[:2])
check("your mesh is the thing that changed - deliberately, and only where "
      "you pointed it",
      core.VERTEX_COLOR_LAYER_NAME not in bystander.data.color_attributes)

print("=== the alpha it must never touch ===")
# Alpha is the channel the decal shaders blend by. Writing colour over it
# is invisible until someone looks - which is why it is asserted here
# rather than trusted.
attr = cube.data.color_attributes[core.VERTEX_COLOR_LAYER_NAME]
for item in attr.data:
    item.color = (item.color[0], item.color[1], item.color[2], 0.25)

settings.detail_use_ao = True
only(cube)
bpy.ops.seto.vertex_bake()
alphas = {round(c[3], 3) for c in colours(cube)}
check("a second bake leaves every alpha exactly where it was",
      all(abs(a - 0.25) < BYTE for a in alphas), sorted(alphas)[:4])

print("=== the layers actually do something, and repeat ===")
only(room)
bpy.ops.seto.vertex_bake()
darkest = min(sum(c[:3]) for c in colours(room))
check("Ambient Occlusion darkens the inside corners of a room",
      darkest < 1.0 - BYTE, darkest)
only(cube)

first = colours(cube)
bpy.ops.seto.vertex_bake()
second = colours(cube)
check("the same settings bake the same mesh twice",
      len(first) == len(second)
      and all(abs(a[i] - b[i]) < BYTE for a, b in zip(first, second)
              for i in range(3)))

settings.detail_ao_strength = 0.0
bpy.ops.seto.vertex_bake()
check("strength 0 gives the flat base colour back",
      all(abs(c[0] - 1.0) < BYTE for c in colours(cube)),
      colours(cube)[:2])

print("=== live update is a switch, and it is honoured ===")
# It writes to the user's own mesh, so "bake while you drag" has to be
# something they chose. With it off, a property change must not touch a
# thing - not even the object sitting selected in front of them.
settings.live_update = False
settings.detail_base_color = (1.0, 1.0, 1.0)
only(bystander)
settings.detail_base_color = (0.0, 1.0, 0.0)
check("with Live Update off, changing a setting bakes nothing",
      core.VERTEX_COLOR_LAYER_NAME not in bystander.data.color_attributes)

settings.live_update = True
settings.detail_base_color = (1.0, 1.0, 1.0)
check("with it on, the selection is baked as the setting changes",
      core.VERTEX_COLOR_LAYER_NAME in bystander.data.color_attributes)

print("=== a failed bake is never silent ===")
check("the settings carry the last failure, for the panel to show",
      hasattr(settings, "last_error"))
check("and a bake that worked leaves it empty", settings.last_error == "",
      settings.last_error)
source = open(core.__file__, encoding="utf-8").read()
check("nothing in here swallows an exception without a word",
      "except Exception:\n            pass" not in source
      and "except Exception:\n        pass" not in source)

print("=== Clear takes back the colour, and nothing else ===")
# Clear exists to undo a bake. The channel it must leave alone is the same
# one the bake must leave alone - alpha is what the decal shaders blend by,
# so a Clear that resets it to 1.0 makes every decal on that mesh fully
# opaque, invisibly, from a button that says it only clears colour.
settings.live_update = False
only(cube)
bpy.ops.seto.vertex_bake()
attr = cube.data.color_attributes[core.VERTEX_COLOR_LAYER_NAME]
for item in attr.data:
    item.color = (0.2, 0.2, 0.2, 0.4)
bpy.ops.seto.vertex_bake_clear()
cleared = colours(cube)
check("Clear puts the colour back to white",
      all(abs(c[i] - 1.0) < BYTE for c in cleared for i in range(3)),
      cleared[:2])
check("and leaves every alpha exactly where it was",
      all(abs(c[3] - 0.4) < BYTE for c in cleared),
      sorted({round(c[3], 3) for c in cleared})[:4])

print("=== a whole collection, not just what you clicked ===")
group = bpy.data.collections.new("bake_group")
scene.collection.children.link(group)
members = []
for i in range(3):
    member_mesh = bpy.data.meshes.new(f"bake_member_{i}")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(member_mesh)
    bm.free()
    member = bpy.data.objects.new(f"bake_member_{i}", member_mesh)
    group.objects.link(member)
    members.append(member)
hidden = members[-1]
hidden.hide_set(True)

deselect_all()
view.objects.active = None
settings.target_mode = 'COLLECTION'
settings.target_collection = group
settings.bake_hidden = False
check("a chosen collection is a target on its own - nothing need be selected",
      bpy.ops.seto.vertex_bake.poll())
bpy.ops.seto.vertex_bake()
check("every visible member is baked",
      all(core.VERTEX_COLOR_LAYER_NAME in m.data.color_attributes
          for m in members[:-1]))
check("and one hidden in the viewport is left alone until asked for",
      core.VERTEX_COLOR_LAYER_NAME not in hidden.data.color_attributes)
settings.bake_hidden = True
bpy.ops.seto.vertex_bake()
check("Include Hidden is what reaches it",
      core.VERTEX_COLOR_LAYER_NAME in hidden.data.color_attributes)

print("=== live update stays on the selection, whatever the target is ===")
# A slider drag walking a whole collection is the difference between a
# laggy drag and a Blender that has stopped answering. The target mode is
# for the button; the drag is always just what you have selected.
settings.live_update = True
only(cube)
member_before = colours(members[0])
cube_before = colours(cube)
settings.detail_base_color = (0.0, 0.0, 1.0)
check("a setting change still bakes the selection", colours(cube) != cube_before)
check("and leaves the collection behind it untouched",
      colours(members[0]) == member_before)

print("=== the gradient can carry two colours ===")
settings.target_mode = 'SELECTED'
settings.live_update = False
only(cube)
cube.rotation_euler = (0.0, 0.0, 0.0)
view.update()
for name in ("detail_use_ao", "detail_use_edge_dirt", "detail_use_floor_grime",
             "detail_use_edge_wear", "detail_use_random",
             "detail_use_fake_shadow"):
    setattr(settings, name, False)
settings.detail_use_gradient = True
settings.gradient_use_colors = True
settings.gradient_color_top = (1.0, 0.0, 0.0)
settings.gradient_color_bottom = (0.0, 0.0, 1.0)
settings.gradient_shift = 0.0
settings.gradient_scale = 1.0
bpy.ops.seto.vertex_bake()
graded = colours(cube)
check("the top of the mesh takes the top colour",
      any(c[0] > 1.0 - BYTE and c[2] < BYTE for c in graded), graded[:2])
check("the bottom takes the bottom colour",
      any(c[2] > 1.0 - BYTE and c[0] < BYTE for c in graded), graded[:2])

print("=== the mask dies when the object moves ===")
# AO, shadow and the gradient are all measured in world space now, so a
# cached mask belongs to a transform as much as to a mesh. Without the
# matrix in the signature a rotated object keeps the shading it had while
# it was upright, and only the button (which rebuilds anyway) looks right.
probe = core.get_bmesh_from_object(cube)
sig_upright = core._geo_signature(cube, probe)
upright = colours(cube)
cube.rotation_euler = (math.radians(90.0), 0.0, 0.0)
view.update()
sig_rotated = core._geo_signature(cube, probe)
probe.free()
check("the signature follows the transform, not only the mesh",
      sig_upright != sig_rotated)
bpy.ops.seto.vertex_bake()
check("so the same cube bakes differently once it is on its side",
      colours(cube) != upright)
cube.rotation_euler = (0.0, 0.0, 0.0)
view.update()

print("=== it refuses politely ===")
deselect_all()
view.objects.active = None
check("with nothing selected the operator will not run",
      not bpy.ops.seto.vertex_bake.poll())

empty = bpy.data.objects.new("bake_empty", None)
scene.collection.objects.link(empty)
only(empty)
check("and an empty is not a mesh, so it stays out of reach",
      not bpy.ops.seto.vertex_bake.poll())

print()
failed = [r for r in RESULTS if not r[0]]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
if failed:
    for _ok, name, detail in failed:
        print(f"FAILED: {name}  -- {detail}")
    sys.exit(1)
