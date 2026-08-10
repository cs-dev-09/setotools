"""Ambient Occlusion's Bevel - one control, two meshes, live.

The strip's own seam is beveled into its mesh; the source's corner is rounded
by a **Bevel modifier**, so it is reversible and can be dragged after the fact.
Both come off the same settings on the finished strip, and have to stay the
same shape.

What that has to get right, and is checked here:
  * the source mesh itself is never edited - only a modifier is added,
  * the round Sollumz will export (the evaluated mesh) matches the strip's,
  * switching Bevel off leaves the source exactly as it was found,
  * one modifier serves every strip on an object, at each strip's own width,
  * bevel weights are written to strip edges and nowhere else.
"""

import bpy, sys
sys.path.append(r"D:\SetoClaude\setotools")
R = []
def check(n, c, d=""):
    R.append((bool(c), n, d)); print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f"  -- {d}" if d and not c else ""))
    return bool(c)

import seto_tools
if getattr(bpy.types, "SETO_PT_fake_ao_panel", None) is None:
    seto_tools.register()
from seto_tools.fake_ao import object_settings, operators, properties, source_bevel

BASE = dict(width=0.4, surface_offset=0.0003)
BEVEL = dict(bevel_mesh=True, bevel_strip=True, bevel_width=0.0833, bevel_segments=4, bevel_profile=0.5)


def fresh_cube(prepare=None):
    """A cube with its +X/+Y vertical edge selected - one edge, two walls."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(size=2)
    cube = bpy.context.active_object
    if prepare is not None:
        prepare(cube)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    for edge in cube.data.edges:
        a, b = (cube.data.vertices[i].co for i in edge.vertices)
        if abs(a.x - 1) < 1e-4 and abs(b.x - 1) < 1e-4 and abs(a.y - 1) < 1e-4 and abs(b.y - 1) < 1e-4:
            edge.select = True
    bpy.ops.object.mode_set(mode='EDIT')
    return cube


def create(prepare=None, **settings):
    cube = fresh_cube(prepare)
    before = len(cube.data.polygons)
    try:
        bpy.ops.seto.create_fake_ao(**settings)
    except RuntimeError as e:
        print("  (err", e, ")")
    bpy.ops.object.mode_set(mode='OBJECT')
    strips = [o for o in bpy.data.objects if o.name.startswith(operators.NAME_PREFIX)]
    return cube, (strips[-1] if strips else None), before


def modifier_of(obj):
    return obj.modifiers.get(source_bevel.MODIFIER_NAME)


def evaluated_mesh(obj):
    """What Sollumz exports: the object with its modifiers applied."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return obj.evaluated_get(depsgraph).to_mesh()


def round_profile(mesh, matrix=None):
    """The rounded corner's cross-section, as distances from the sharp corner
    line it replaced (the cube's +X/+Y vertical edge)."""
    seen = set()
    for vert in mesh.vertices:
        co = (matrix @ vert.co) if matrix else vert.co
        if co.x < 0.5 or co.y < 0.5:
            continue
        seen.add(round(((co.x - 1.0) ** 2 + (co.y - 1.0) ** 2) ** 0.5, 4))
    return sorted(seen)


# --- 1. The source mesh is not edited, only modified ------------------------
cube, strip, before = create(**BASE, **BEVEL)
if not check("strip created", strip is not None):
    sys.exit(1)
check("the source mesh itself is untouched", len(cube.data.polygons) == before,
      f"{len(cube.data.polygons)} vs {before}")

modifier = modifier_of(cube)
if not check("a Bevel modifier was added", modifier is not None and modifier.type == 'BEVEL'):
    sys.exit(1)
check("driven by edge weights, on edges",
      modifier.limit_method == 'WEIGHT' and modifier.affect == 'EDGES',
      f"{modifier.limit_method}/{modifier.affect}")
check("at the strip's own settings",
      abs(modifier.width - 0.0833) < 1e-6 and modifier.segments == 4
      and abs(modifier.profile - 0.5) < 1e-6,
      f"{modifier.width}/{modifier.segments}/{modifier.profile}")

weights = cube.data.attributes[source_bevel.WEIGHT_ATTRIBUTE]
weighted = [i for i, v in enumerate(weights.data) if v.value > 0.0]
selected = [e.index for e in cube.data.edges
            if all(abs(cube.data.vertices[v].co.x - 1) < 1e-4
                   and abs(cube.data.vertices[v].co.y - 1) < 1e-4 for v in e.vertices)]
check("the weight lands on the selected edge and nowhere else",
      weighted == selected, f"{weighted} vs {selected}")

# --- 2. The exported round is the strip's round -----------------------------
source_round = round_profile(evaluated_mesh(cube))
# A 4-segment round is 5 cross-section points, but measured as distance from
# the corner line they pair up by symmetry: both ends at the bevel width, two
# at the same distance in, and the apex nearest the corner. Three values.
check("the evaluated source really is rounded - the modifier reaches the export",
      len(source_round) == 3 and abs(max(source_round) - 0.0833) < 1e-3,
      str(source_round))
strip_round = [d for d in round_profile(strip.data, cube.matrix_world.inverted() @ strip.matrix_world)
               if d <= max(source_round) + 1e-3]
check("the strip's round has the same number of steps as the source's",
      len(strip_round) == len(source_round), f"{strip_round} vs {source_round}")
if len(strip_round) == len(source_round):
    check("and sits exactly Surface Offset outside it",
          max(abs(a - b) for a, b in zip(strip_round, source_round)) < 0.0015,
          f"{strip_round} vs {source_round}")

# --- 3. The chamfer keeps the wall's material -------------------------------
def two_slots(cube):
    for name in ("slot0_TRIM", "slot1_BRICK"):
        cube.data.materials.append(bpy.data.materials.new(name))
    for poly in cube.data.polygons:
        poly.material_index = 1


cube, strip, before = create(prepare=two_slots, **BASE, **BEVEL)
baked = evaluated_mesh(cube)
chamfer = [p for p in baked.polygons if p.center.x > 0.8 and p.center.y > 0.8]
check("the chamfer inherits the wall's material, not slot 0",
      len(chamfer) == 4 and {p.material_index for p in chamfer} == {1},
      f"{len(chamfer)} faces on {sorted({p.material_index for p in chamfer})}")

# --- 4. Live, in both directions --------------------------------------------
cube, strip, before = create(**BASE, **BEVEL)
data = strip.seto_fake_ao_data

data.bevel_width = 0.15
check("dragging Width moves the source's modifier with it",
      abs(modifier_of(cube).width - 0.15) < 1e-6, str(modifier_of(cube).width))
grown = round_profile(strip.data, cube.matrix_world.inverted() @ strip.matrix_world)
check("and rebuilds the strip to match", max(grown) > 0.1, str(grown))

data.bevel_segments = 8
check("Segments too", modifier_of(cube).segments == 8, str(modifier_of(cube).segments))
check("and the strip gains the same steps",
      len(strip.data.polygons) == 2 + 8, f"{len(strip.data.polygons)} faces")

data.bevel_profile = 0.75
check("Profile Shape too", abs(modifier_of(cube).profile - 0.75) < 1e-6,
      str(modifier_of(cube).profile))

# --- 5. Switching it off puts everything back -------------------------------
data.bevel_mesh = False
data.bevel_strip = False
check("switching Bevel off removes the modifier", modifier_of(cube) is None)
check("and clears the weight it set",
      all(v.value == 0.0 for v in cube.data.attributes[source_bevel.WEIGHT_ATTRIBUTE].data))
check("the source is back to a sharp corner",
      round_profile(evaluated_mesh(cube)) == [0.0], str(round_profile(evaluated_mesh(cube))))
check("and the strip is back to its plain two-wing L",
      len(strip.data.polygons) == 2, f"{len(strip.data.polygons)} faces")

data.bevel_mesh = True
data.bevel_strip = True
check("switching it back on restores both",
      modifier_of(cube) is not None and len(strip.data.polygons) == 2 + 8,
      f"{len(strip.data.polygons)} faces")

# --- 6. One modifier, several strips, each at its own width -----------------
cube, first, before = create(**BASE, **BEVEL)
bpy.context.view_layer.objects.active = cube
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.object.mode_set(mode='OBJECT')
for edge in cube.data.edges:          # the -X/+Y vertical edge, a second corner
    a, b = (cube.data.vertices[i].co for i in edge.vertices)
    if abs(a.x + 1) < 1e-4 and abs(b.x + 1) < 1e-4 and abs(a.y - 1) < 1e-4 and abs(b.y - 1) < 1e-4:
        edge.select = True
bpy.ops.object.mode_set(mode='EDIT')
try:
    bpy.ops.seto.create_fake_ao(**BASE, bevel_mesh=True, bevel_strip=True, bevel_width=0.04,
                                bevel_segments=4, bevel_profile=0.5)
except RuntimeError as e:
    print("  (err", e, ")")
bpy.ops.object.mode_set(mode='OBJECT')

check("a second strip on the same object reuses the one modifier",
      len([m for m in cube.modifiers if m.type == 'BEVEL']) == 1,
      str([m.name for m in cube.modifiers]))
modifier = modifier_of(cube)
check("the modifier carries the widest strip's width",
      abs(modifier.width - 0.0833) < 1e-6, str(modifier.width))
values = sorted({round(v.value, 3) for v in
                 cube.data.attributes[source_bevel.WEIGHT_ATTRIBUTE].data if v.value > 0.0})
check("and the narrower strip's edges are weighted down to their share",
      len(values) == 2 and abs(values[0] - 0.04 / 0.0833) < 0.002 and abs(values[1] - 1.0) < 1e-6,
      str(values))

baked = evaluated_mesh(cube)
wide = [p for p in baked.polygons if p.center.x > 0.8 and p.center.y > 0.8]
narrow = [p for p in baked.polygons if p.center.x < -0.8 and p.center.y > 0.8]
check("both corners come out rounded", len(wide) == 4 and len(narrow) == 4,
      f"{len(wide)} / {len(narrow)}")

# --- 7. Nothing to round -----------------------------------------------------
check("a strip with no source edges contributes nothing",
      source_bevel._edge_indices(cube.data, "") is None)
check("neither does one whose edges are gone",
      source_bevel._edge_indices(cube.data, "9990,9991") is None)

# --- 8. The create panel no longer decides any of this ----------------------
import inspect  # noqa: E402
import seto_tools.fake_ao.ui as ao_ui  # noqa: E402
create_draw = inspect.getsource(ao_ui.SETO_PT_fake_ao_panel.draw)
check("the create panel draws no Bevel block", "_draw_bevel" not in create_draw)
strip_draw = inspect.getsource(ao_ui.SETO_PT_fake_ao_object_panel.draw)
check("the finished strip's panel does", "_draw_bevel" in strip_draw)
check("and draws it with no target to pick", "show_target=True" not in strip_draw)

# --- 9. Edge keys still parse, old and new ----------------------------------
keys = object_settings.parse_edge_keys("3,7 1,2")
check("edge keys parse", keys == [(3, 7, None), (1, 2, None)], str(keys))
keys = object_settings.parse_edge_keys("3,7:1/2/3/4;0/1/2")
check("and so do the face specs older strips stored",
      keys[0][2] == {frozenset({1, 2, 3, 4}), frozenset({0, 1, 2})}, str(keys))
check("Merge Distance is still not a setting",
      "merge_distance" not in properties.SETTING_NAMES)
check("Surface Offset is still capped at 0.05",
      abs(bpy.context.scene.seto_fake_ao.bl_rna.properties["surface_offset"].hard_max - 0.05) < 1e-9)

failed = [r for r in R if not r[0]]
print("\n" + "=" * 60); print(f"RESULT: {len(R)-len(failed)}/{len(R)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
