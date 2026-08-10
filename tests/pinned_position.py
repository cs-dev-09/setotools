"""A hand-moved strip stays where it was put.

Every tool's rebuild ends by re-deriving the strip's position from its source
and then re-centring the origin on the new mesh, which is what used to wipe a
manual move: nudge a finished strip off the floor, touch any setting, and it
snapped back. `shared/manual_offset.py` remembers the offset instead of
deriving it, and re-applies it after `_centre_origin`.

What is checked, per tool:

  * a fresh strip is unpinned, and knows where it was generated;
  * Pin Position adopts wherever the object has been dragged to;
  * a rebuild - a real settings change, the thing that used to lose it - leaves
    it there;
  * repeated rebuilds do not accumulate drift, which is the failure mode of
    deriving the offset from the object's own transform;
  * Clear Offset puts it back where the tool generates it;
  * typing into the offset field moves the object without rebuilding the mesh.

Read against `matrix_world`, never `location`: these strips are parented into a
Sollumz Drawable when the source belongs to one, and then the two differ.
"""
import bpy, sys

sys.path.append(r"D:\SetoClaude\setotools")

from mathutils import Vector

R = []
def check(n, c, d=""):
    R.append((bool(c), n, d))
    print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f"  -- {d}" if d and not c else ""))
    return bool(c)

import seto_tools
if getattr(bpy.types, "SETO_PT_fake_ao_panel", None) is None:
    seto_tools.register()

from seto_tools.shared import manual_offset

check("Pin Position is registered", hasattr(bpy.types, "SETO_OT_pin_strip_position"))
check("Clear Offset is registered", hasattr(bpy.types, "SETO_OT_clear_strip_position"))


def build_strip(operator):
    """A cube with one edge selected, run through `operator`."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    bpy.ops.mesh.primitive_cube_add(size=2)
    cube = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    cube.data.edges[0].select = True
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        result = operator()
    except RuntimeError as e:
        # bpy.ops raises where the UI would show a red status line.
        print("   (op error:", e, ")")
        result = {'CANCELLED'}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    return cube, (bpy.context.active_object if result == {'FINISHED'} else None)


def world(obj):
    return Vector(obj.matrix_world.translation)


def close(a, b, tol=1e-4):
    return (Vector(a) - Vector(b)).length <= tol


NUDGE = Vector((0.0, 0.0, 0.35))

TOOLS = (
    ("Ambient Occlusion", bpy.ops.seto.create_fake_ao, "seto_fake_ao_data"),
    ("Edge Wear", bpy.ops.seto.create_fake_damage, "seto_fake_damage_data"),
    ("Smooth Edge", bpy.ops.seto.create_smooth_edge, "seto_smooth_edge_data"),
    ("Edge Dirt", bpy.ops.seto.create_edge_dirt, "seto_edge_dirt_data"),
)

for label, create, attr in TOOLS:
    cube, strip = build_strip(create)
    if not check(f"{label}: a strip was created", strip is not None):
        continue

    data = getattr(strip, attr)
    generated = world(strip)

    check(f"{label}: a fresh strip is not pinned", not manual_offset.is_pinned(data))
    check(f"{label}: it knows where it was generated",
          close(data.auto_location, generated),
          f"auto_location {tuple(data.auto_location)} vs {tuple(generated)}")

    # Drag it up off its source, the way a user would, and pin it there.
    moved = strip.matrix_world.copy()
    moved.translation = generated + NUDGE
    strip.matrix_world = moved
    bpy.context.view_layer.objects.active = strip
    bpy.ops.seto.pin_strip_position(data_attr=attr)

    check(f"{label}: Pin Position adopts the drag",
          close(data.manual_offset, NUDGE), tuple(data.manual_offset))

    # The thing that used to lose it: a settings change, which rebuilds the
    # mesh and re-derives the transform from the source. Alpha Center is the
    # one to poke here - it repaints the strip without moving a vertex, so the
    # position it is generated at is the same before and after and the check
    # can name an absolute place rather than a relative one.
    data.alpha_center = max(0.0, data.alpha_center - 0.1)
    check(f"{label}: a rebuild leaves it where it was put",
          close(world(strip), generated + NUDGE),
          f"{tuple(world(strip))} vs {tuple(generated + NUDGE)}")

    # Deriving the offset from the object's own transform drifts here, because
    # each rebuild would measure an offset that already contains the last one.
    for step in range(4):
        data.alpha_center = max(0.0, data.alpha_center - 0.05)
    check(f"{label}: five rebuilds do not accumulate drift",
          close(world(strip), generated + NUDGE) and close(data.manual_offset, NUDGE),
          f"{tuple(world(strip))} / offset {tuple(data.manual_offset)}")

    # A setting that DOES move the strip - a wider shelf re-centres the origin -
    # keeps the offset on top of wherever the tool now generates it, rather than
    # freezing the strip at an absolute place. That is the point: the pin says
    # "this far off my source", not "at these coordinates".
    data.width = data.width + 0.02
    check(f"{label}: the offset rides a strip the tool moves itself",
          close(world(strip), Vector(data.auto_location) + NUDGE)
          and not close(data.auto_location, generated),
          f"{tuple(world(strip))} vs {tuple(Vector(data.auto_location) + NUDGE)}")

    # The source mesh is never touched by any of this.
    check(f"{label}: the source stays where it is",
          close(world(cube), (0.0, 0.0, 0.0)), tuple(world(cube)))

    # Typing into the field moves the object, and only the object.
    faces = len(strip.data.polygons)
    base = Vector(data.auto_location)
    data.manual_offset = (0.1, 0.0, 0.5)
    check(f"{label}: the offset field moves the strip",
          close(world(strip), base + Vector((0.1, 0.0, 0.5))),
          tuple(world(strip)))
    check(f"{label}: setting the offset does not rebuild the mesh",
          len(strip.data.polygons) == faces)

    bpy.ops.seto.clear_strip_position(data_attr=attr)
    check(f"{label}: Clear Offset puts it back", close(world(strip), base),
          f"{tuple(world(strip))} vs {tuple(base)}")
    check(f"{label}: and leaves it unpinned", not manual_offset.is_pinned(data))

    # A cleared strip still rebuilds onto its source, as it always did.
    data.alpha_center = max(0.0, data.alpha_center - 0.05)
    check(f"{label}: an unpinned strip still tracks its source",
          close(world(strip), base), f"{tuple(world(strip))} vs {tuple(base)}")


# The operator refuses an object that carries no strip data rather than writing
# an offset onto something it does not own.
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
bpy.ops.mesh.primitive_cube_add(size=2)
plain = bpy.context.active_object
try:
    result = bpy.ops.seto.pin_strip_position(data_attr="seto_not_a_group")
except RuntimeError:
    result = {'CANCELLED'}
check("Pin Position refuses an object with no strip data", result == {'CANCELLED'})

failed = [r for r in R if not r[0]]
print("=" * 60)
print(f"RESULT: {len(R) - len(failed)}/{len(R)} checks passed")
for _, name, detail in failed:
    print("  FAIL", name, "--", detail)
print("=" * 60)
sys.exit(1 if failed else 0)
