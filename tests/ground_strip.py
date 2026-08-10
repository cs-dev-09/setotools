"""Ambient Occlusion along a ground line, for an object sunk into the floor.

A tester asked: "can I create a decal for an object that extends into the
ground?" There is no edge there to select - the line you see is where the mesh
crosses the floor, not geometry - so **Build From: Ground Level** cuts a copy
of the mesh at a world height and builds along that contour.

The three things that decide whether it is useful rather than merely present:

* the strip must go **up** only. Cutting a wall in half leaves the new edge
  with a face either side, and the strip then spreads both ways with half of
  it under the floor. Discarding everything below the plane is what makes the
  contour a boundary edge with one face.
* the **source must not change**. Everything happens on a BMesh copy.
* the height is **world** Z, so a rotated or non-uniformly scaled object has
  to have the plane taken into its own space properly - the case where using
  the plain matrix on the plane's normal goes wrong.
"""
import bpy, sys

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    return bool(cond)

import seto_tools
if getattr(bpy.types, "SETO_PT_fake_ao_panel", None) is None:
    seto_tools.register()

settings = bpy.context.scene.seto_fake_ao
WIDTH = 0.2
GROUND = 0.0


def clear():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def sunk_wall(rotation=(0, 0, 0), scale=(1, 1, 1)):
    """A 2 m vertical wall centred on z=0, so its lower half is 'buried'."""
    bpy.ops.mesh.primitive_plane_add(size=2)
    wall = bpy.context.active_object
    wall.rotation_euler[0] = 1.5707963
    bpy.ops.object.transform_apply(rotation=True)
    wall.rotation_euler = rotation
    wall.scale = scale
    return wall


def build(wall):
    settings.source_mode = 'GROUND'
    settings.ground_level = GROUND
    settings.width = WIDTH
    bpy.context.view_layer.objects.active = wall
    wall.select_set(True)
    try:
        result = bpy.ops.seto.create_fake_ao()
    except RuntimeError as error:
        print("  (operator reported:", error, ")")
        return None
    if result != {'FINISHED'}:
        return None
    return bpy.context.active_object


def world_z(obj):
    return [(obj.matrix_world @ vert.co).z for vert in obj.data.vertices]


print("=== a wall standing in the floor ===")
clear()
wall = sunk_wall()
before = (len(wall.data.vertices), len(wall.data.polygons))
strip = build(wall)
if check("a strip was built without any selection", strip is not None):
    zs = world_z(strip)
    check("it starts at the ground line", abs(min(zs) - GROUND) < 1e-4, min(zs))
    check("and rises by Width", abs(max(zs) - (GROUND + WIDTH)) < 1e-3, max(zs))
    check("nothing is built below the floor", min(zs) > GROUND - 1e-4, min(zs))
    check("it is one wing, not a band either side",
          len(strip.data.polygons) <= 2, len(strip.data.polygons))
check("the source mesh is untouched",
      (len(wall.data.vertices), len(wall.data.polygons)) == before,
      f"{before} -> {(len(wall.data.vertices), len(wall.data.polygons))}")

print("=== the height is world space, not object space ===")
clear()
wall = sunk_wall()
wall.location.z = 0.5           # lift it: less of it is now below the floor
bpy.context.view_layer.update()
strip = build(wall)
if check("a lifted wall still builds", strip is not None):
    zs = world_z(strip)
    check("still cut at world Z, not at the object's own middle",
          abs(min(zs) - GROUND) < 1e-3, min(zs))

print("=== rotated and non-uniformly scaled ===")
clear()
wall = sunk_wall(rotation=(0, 0, 0.6), scale=(1.0, 1.0, 2.5))
bpy.context.view_layer.update()
strip = build(wall)
if check("a rotated, unevenly scaled wall builds", strip is not None):
    zs = world_z(strip)
    check("the contour is still flat at the ground line",
          max(zs) - min(zs) > 1e-4 and abs(min(zs) - GROUND) < 1e-3,
          f"{min(zs):.4f}..{max(zs):.4f}")

print("=== an object that never reaches the floor ===")
clear()
wall = sunk_wall()
wall.location.z = 5.0
bpy.context.view_layer.update()
strip = build(wall)
check("says so instead of building nothing silently", strip is None)

print("=== the panel offers it, and hides Bevel behind it ===")
from seto_tools.fake_ao import ui as ao_ui

_UILAYOUT_PROPS = set(bpy.types.UILayout.bl_rna.properties.keys())


class Recorder:
    def __init__(self, log):
        object.__setattr__(self, "_log", log)

    def __setattr__(self, name, value):
        check(f"UILayout really has '{name}'", name in _UILAYOUT_PROPS)
        object.__setattr__(self, name, value)

    scale_y = scale_x = 1.0
    enabled = active = True
    alert = False

    def _sub(self, *a, **k): return Recorder(self._log)
    row = column = box = grid_flow = split = column_flow = _sub

    def label(self, **k): return None
    def separator(self, *a, **k): return None
    def operator(self, idname, **k):
        return type("P", (), {"__setattr__": lambda s, k, v: None})()

    def prop(self, data, name, **k):
        self._log.append(name)
        return self


def drawn(mode):
    settings.source_mode = mode
    log = []
    shim = type("Shim", (), {})()
    shim.layout = Recorder(log)
    for attr in dir(bpy.types.SETO_PT_fake_ao_panel):
        if attr.startswith("_draw") or attr == "draw":
            fn = getattr(bpy.types.SETO_PT_fake_ao_panel, attr)
            if callable(fn):
                setattr(shim, attr, fn.__get__(shim))
    shim.draw(bpy.context)
    return log


ground_rows = drawn('GROUND')
selection_rows = drawn('SELECTION')
check("Ground Level is offered when that mode is on", "ground_level" in ground_rows)
check("and hidden when it is not", "ground_level" not in selection_rows)
# Bevel is not in the create panel at all any more - it is live on the
# finished strip, where one set of controls drives the strip's seam and the
# source's corner together. So it must be absent from both modes here, and the
# Ground-mode note is what tells you it has no meaning on this one.
check("Bevel is not offered before Create, in either mode",
      not any(row.startswith("bevel") for row in ground_rows + selection_rows),
      ground_rows + selection_rows)
settings.source_mode = 'SELECTION'

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(RESULTS)-len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed:
    print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
