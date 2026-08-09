"""Fake AO's optional Bevel: the strip seam, the source edge, and both.

The three things that can quietly go wrong here, and are therefore what this
checks:

  * the source bevel running twice (once at creation, again on every live
    rebuild) - chamfering the chamfer,
  * the rebuild growing a wing onto the chamfer face the creation deliberately
    left bare, because the stored edge keys did not record which faces were
    used,
  * a bevel width past the strip's own Width collapsing it.
"""

import bpy, sys
from mathutils import Vector
sys.path.append(r"D:\SetoClaude\setotools")
R = []
def check(n, c, d=""):
    R.append((bool(c), n, d)); print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f"  -- {d}" if d and not c else ""))
    return bool(c)

import seto_tools
if getattr(bpy.types, "SETO_PT_fake_ao_panel", None) is None:
    seto_tools.register()
from seto_tools.fake_ao import geometry, object_settings, properties


def fresh_cube():
    """A cube with one vertical edge selected - the architectural corner the
    tool is built for: one edge, two walls."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(size=2)
    cube = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    # The +X/+Y vertical edge: both verts share x=1, y=1, differ in z.
    target = None
    for edge in cube.data.edges:
        a, b = (cube.data.vertices[i].co for i in edge.vertices)
        if abs(a.x - 1) < 1e-4 and abs(b.x - 1) < 1e-4 and abs(a.y - 1) < 1e-4 and abs(b.y - 1) < 1e-4:
            target = edge
            break
    target.select = True
    bpy.ops.object.mode_set(mode='EDIT')
    return cube


def create(prepare=None, **settings):
    """Run the operator with the given settings, leave Object Mode, and return
    (source, strip).

    `prepare` gets the cube before the operator runs, for setting up the state
    a check needs - it is called in Edit Mode with the corner already selected.
    """
    cube = fresh_cube()
    if prepare is not None:
        bpy.ops.object.mode_set(mode='OBJECT')
        prepare(cube)
        bpy.ops.object.mode_set(mode='EDIT')
    source_faces = len(cube.data.polygons)
    try:
        bpy.ops.seto.create_fake_ao(**settings)
    except RuntimeError as e:
        print("  (err", e, ")")
    bpy.ops.object.mode_set(mode='OBJECT')
    strips = [o for o in bpy.data.objects if o.name.startswith("fake_ao_")]
    return cube, (strips[-1] if strips else None), source_faces


BASE = dict(width=0.4, surface_offset=0.0003)

# --- 0. The defaults a new user gets ----------------------------------------
defaults = bpy.context.scene.seto_fake_ao
check("bevel is on out of the box", defaults.bevel_enabled is True)
check("and rounds both meshes by default", defaults.bevel_target == 'BOTH', defaults.bevel_target)
check("default bevel width", abs(defaults.bevel_width - 0.0833) < 1e-6, str(defaults.bevel_width))
check("default segments", defaults.bevel_segments == 4, str(defaults.bevel_segments))
check("default profile is circular", abs(defaults.bevel_profile - 0.5) < 1e-6, str(defaults.bevel_profile))

# --- 1. Baseline: bevel off, nothing changes anywhere -----------------------
cube, strip, before = create(**BASE, bevel_enabled=False)
if not check("baseline strip created", strip is not None):
    sys.exit(1)
base_faces = len(strip.data.polygons)
check("baseline is the two-wing L", base_faces == 2, f"{base_faces} faces")
check("bevel off leaves the source mesh alone", len(cube.data.polygons) == before,
      f"{len(cube.data.polygons)} vs {before}")

# --- 2. Strip bevel: the strip's seam is chamfered, the source is not -------
cube, strip, before = create(**BASE, bevel_enabled=True, bevel_target='STRIP',
                             bevel_width=0.02, bevel_segments=1, bevel_profile=0.5)
strip_faces = len(strip.data.polygons)
check("STRIP bevel adds the chamfer face", strip_faces == base_faces + 1, f"{strip_faces} faces")
check("STRIP bevel never touches the source", len(cube.data.polygons) == before,
      f"{len(cube.data.polygons)} vs {before}")

# Segments: a rounded seam is more faces than a flat chamfer.
cube, strip, before = create(**BASE, bevel_enabled=True, bevel_target='STRIP',
                             bevel_width=0.02, bevel_segments=4, bevel_profile=0.5)
check("Segments rounds the seam off", len(strip.data.polygons) == base_faces + 4,
      f"{len(strip.data.polygons)} faces")

# The chamfer must carry the corner's alpha, not a hole in the fade.
attr = strip.data.attributes["Color 1"]
alphas = sorted({round(e.color_srgb[3], 2) for e in attr.data})
check("the chamfer stays inside the corner..outer alpha range",
      min(alphas) >= 0.0 and max(alphas) <= 1.0 and len(alphas) >= 2, str(alphas))

# --- 3. Source bevel: the source IS modified, the strip runs on the rim -----
cube, strip, before = create(**BASE, bevel_enabled=True, bevel_target='SOURCE',
                             bevel_width=0.05, bevel_segments=1, bevel_profile=0.5)
check("SOURCE bevel chamfers the source mesh", len(cube.data.polygons) == before + 1,
      f"{len(cube.data.polygons)} vs {before}")
check("SOURCE bevel still produces a strip", strip is not None and len(strip.data.polygons) > 0,
      f"{len(strip.data.polygons) if strip else 0} faces")
# Two rim edges, one wall each - the chamfer itself is left bare.
check("the chamfer face is left bare (one wing per rim edge)", len(strip.data.polygons) == 2,
      f"{len(strip.data.polygons)} faces")
check("the excluded faces were recorded on the strip",
      ":" in strip.seto_fake_ao_data.edge_keys, strip.seto_fake_ao_data.edge_keys)
check("the strip's stored target collapses to STRIP",
      strip.seto_fake_ao_data.bevel_target == 'STRIP', strip.seto_fake_ao_data.bevel_target)
check("a source-only bevel does not arm the strip bevel",
      strip.seto_fake_ao_data.bevel_enabled is False)

# The rebuild must not re-bevel the source, and must not adopt the chamfer.
source_faces_after_create = len(cube.data.polygons)
strip_faces_after_create = len(strip.data.polygons)
strip.seto_fake_ao_data.width = 0.12          # fires the live rebuild
bpy.ops.seto.fake_ao_rebuild()
check("rebuild leaves the already-beveled source alone",
      len(cube.data.polygons) == source_faces_after_create,
      f"{len(cube.data.polygons)} vs {source_faces_after_create}")
check("rebuild does not grow a wing onto the chamfer",
      len(strip.data.polygons) == strip_faces_after_create,
      f"{len(strip.data.polygons)} vs {strip_faces_after_create}")

# --- 4. Source + Strip: the two rounds have to coincide ---------------------
BEVEL = dict(bevel_enabled=True, bevel_target='BOTH', bevel_width=0.0833,
             bevel_segments=4, bevel_profile=0.5)
cube, strip, before = create(**BASE, **BEVEL)
check("BOTH rounds the source", len(cube.data.polygons) == before + 4,
      f"{len(cube.data.polygons)} vs {before}")
check("BOTH rounds the strip to match", len(strip.data.polygons) == base_faces + 4,
      f"{len(strip.data.polygons)} faces")
check("BOTH arms the strip bevel for later rebuilds",
      strip.seto_fake_ao_data.bevel_enabled is True)


def round_profile(obj, matrix=None):
    """The rounded corner's cross-section, as distances from the sharp corner
    line the round replaced (the cube's +X/+Y vertical edge, at x=y=1).

    Sorted, so it can be compared between two meshes without depending on
    vertex order.
    """
    seen = set()
    for v in obj.data.vertices:
        co = (matrix @ v.co) if matrix else v.co
        # Only the near quadrant: the round, not the far side of the cube.
        if co.x < 0.5 or co.y < 0.5:
            continue
        d = ((co.x - 1.0) ** 2 + (co.y - 1.0) ** 2) ** 0.5
        seen.add(round(d, 4))
    return sorted(seen)


source_round = round_profile(cube)
# The strip is a separate object with its own origin - measure it in the
# source's local space, which is where it was built.
strip_local = cube.matrix_world.inverted() @ strip.matrix_world
strip_round = [d for d in round_profile(strip, strip_local)
               if d <= max(source_round) + 1e-3]
check("the strip's round has the same number of steps as the source's",
      len(strip_round) == len(source_round), f"{strip_round} vs {source_round}")
if len(strip_round) == len(source_round):
    gaps = [abs(a - b) for a, b in zip(strip_round, source_round)]
    # Each strip vertex sits Surface Offset outside its source counterpart,
    # so the two profiles differ by that and nothing more.
    check("the strip's round sits exactly Surface Offset outside the source's",
          max(gaps) < 0.0015, f"max gap {max(gaps):.5f}, {strip_round} vs {source_round}")

both_faces = len(strip.data.polygons)
check("a beveled-away corner is stored verbatim, not as indices",
      strip.seto_fake_ao_data.frozen_segments != "" and strip.seto_fake_ao_data.edge_keys == "",
      strip.seto_fake_ao_data.edge_keys)
source_faces_after_create = len(cube.data.polygons)
strip.seto_fake_ao_data.width = 0.45
check("the strip bevel survives a rebuild", len(strip.data.polygons) == both_faces,
      f"{len(strip.data.polygons)} vs {both_faces}")
check("and the rebuild does not re-bevel the source",
      len(cube.data.polygons) == source_faces_after_create,
      f"{len(cube.data.polygons)} vs {source_faces_after_create}")
rebuilt_round = [d for d in round_profile(strip, cube.matrix_world.inverted() @ strip.matrix_world)
                 if d <= max(source_round) + 1e-3]
check("the rebuilt strip still lands on the source's round",
      len(rebuilt_round) == len(source_round)
      and max(abs(a - b) for a, b in zip(rebuilt_round, source_round)) < 0.0015,
      f"{rebuilt_round} vs {source_round}")

# --- 5. The source's own look has to survive being beveled ------------------
# The coloured band down the corner was never a UV problem: bmesh.ops.bevel
# defaults its `material` to 0, where Blender's own Bevel defaults Material
# Index to -1, "same as the adjacent face". The chamfer was being dragged onto
# slot 0 - a different material entirely - which on a wall whose brick lives in
# another slot is a band of the wrong texture the full length of the corner.
def two_slots(cube):
    """Everything on slot 1; slot 0 is the material nothing should pick up."""
    for name in ("slot0_TRIM", "slot1_BRICK"):
        cube.data.materials.append(bpy.data.materials.new(name))
    for poly in cube.data.polygons:
        poly.material_index = 1


cube, strip, before = create(prepare=two_slots, **BASE, **BEVEL)
chamfer = [p for p in cube.data.polygons if p.center.x > 0.8 and p.center.y > 0.8]
slots = sorted({p.material_index for p in chamfer})
check("the chamfer inherits the wall's material, not slot 0",
      len(chamfer) == 4 and slots == [1], f"{len(chamfer)} faces on slots {slots}")
check("and the walls themselves are untouched",
      sorted({p.material_index for p in cube.data.polygons}) == [1])


def uv_bounds(obj, faces):
    uv = obj.data.uv_layers.active.data
    points = [Vector(uv[li].uv) for poly in faces
              for li in range(poly.loop_start, poly.loop_start + poly.loop_total)]
    return (min(p.x for p in points), min(p.y for p in points),
            max(p.x for p in points), max(p.y for p in points))


# Blender's own interpolation is what lays the chamfer's UVs out, and it is a
# blend between the two rims - so the chamfer can only ever land inside the
# span the walls already occupied. Worth pinning: an earlier attempt to
# "improve" on it by unrolling the chamfer could run past that span and off the
# end of the wall's island, which on an atlas is the same coloured band again.
def atlas_walls(cube):
    """Map the two walls that meet at the corner into the unit square, at a
    different rate across the wall than up it. Everything else goes far away."""
    uv = cube.data.uv_layers.active.data
    for poly in cube.data.polygons:
        centre = poly.center
        wall = abs(poly.normal.z) < 0.9 and (centre.x > 0.8 or centre.y > 0.8)
        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
            co = cube.data.vertices[cube.data.loops[li].vertex_index].co
            if wall:
                lateral = (1.0 - co.y) if centre.x > 0.8 else (1.0 - co.x)
                uv[li].uv = (lateral * 0.5, (co.z + 1.0) * 0.25)
            else:
                uv[li].uv = (5.0 + co.x * 0.1, 5.0 + co.y * 0.1)


cube, strip, before = create(prepare=atlas_walls, **BASE, **BEVEL)
chamfer = [p for p in cube.data.polygons if p.center.x > 0.8 and p.center.y > 0.8]
min_u, min_v, max_u, max_v = uv_bounds(cube, chamfer)
outside = max(-min_u, max_u - 1.0, -min_v, max_v - 1.0)
check("nothing on the chamfer leaves the wall's island",
      outside <= 0.001, f"{outside:.4f} past the edge, u [{min_u:.4f}, {max_u:.4f}]")
check("the chamfer spans the corner's full height in UV",
      abs((max_v - min_v) - 2.0 * 0.25) < 0.01, f"v span {max_v - min_v:.4f}")


# --- 6. Settings that are no longer settings --------------------------------
offset_prop = defaults.bl_rna.properties["surface_offset"]
check("Surface Offset is capped at 0.05", abs(offset_prop.hard_max - 0.05) < 1e-9,
      str(offset_prop.hard_max))
check("Merge Distance is gone from the settings",
      "merge_distance" not in properties.SETTING_NAMES, str(properties.SETTING_NAMES))
check("the automatic merge distance clears the corner seam it has to close",
      geometry.auto_merge_distance(0.25, 0.0003) > 0.0003 * 2 ** 0.5,
      str(geometry.auto_merge_distance(0.25, 0.0003)))
check("and stays far below Width",
      geometry.auto_merge_distance(0.25, 0.0003) < 0.25 * 0.1,
      str(geometry.auto_merge_distance(0.25, 0.0003)))
check("a huge Surface Offset cannot let the weld eat the strip",
      geometry.auto_merge_distance(0.1, 0.05) <= 0.1 * 0.25,
      str(geometry.auto_merge_distance(0.1, 0.05)))

# The seam still closes: one welded strip, not two wings sitting side by side.
cube, strip, before = create(**BASE, bevel_enabled=False)
loose = sum(1 for e in strip.data.edges if len([p for p in strip.data.polygons
                                                if e.key[0] in p.vertices and e.key[1] in p.vertices]) == 2)
check("the two wings are welded into one mesh", loose >= 1 and len(strip.data.vertices) == 6,
      f"{len(strip.data.vertices)} verts, {loose} shared edges")

cube, both_strip, before = create(**BASE, **BEVEL)
parsed = object_settings.parse_segments(both_strip.seto_fake_ao_data.frozen_segments)
check("frozen segments round-trip", len(parsed) == 1 and len(parsed[0].normals) == 2,
      str(len(parsed)))
check("unreadable frozen segments degrade quietly",
      object_settings.parse_segments("not json") == [])

# --- 5. Backwards compatibility and edge cases ------------------------------
keys = object_settings.parse_edge_keys("3,7 1,2")
check("edge keys stored before this feature still parse",
      keys == [(3, 7, None), (1, 2, None)], str(keys))
keys = object_settings.parse_edge_keys("3,7:1/2/3/4;0/1/2 1,2")
check("edge keys with face specs parse",
      keys[0][0:2] == (3, 7) and keys[0][2] == {frozenset({1, 2, 3, 4}), frozenset({0, 1, 2})}
      and keys[1] == (1, 2, None), str(keys))

# A bevel wider than the strip must clamp, not collapse it into nothing.
cube, strip, before = create(**BASE, bevel_enabled=True, bevel_target='STRIP',
                             bevel_width=5.0, bevel_segments=1, bevel_profile=0.5)
check("an absurd bevel width clamps instead of destroying the strip",
      strip is not None and len(strip.data.polygons) >= 2 and len(strip.data.vertices) > 0,
      f"{len(strip.data.polygons) if strip else 0} faces")

# Width 0 with the checkbox on is a no-op, not an error.
cube, strip, before = create(**BASE, bevel_enabled=True, bevel_target='BOTH',
                             bevel_width=0.0, bevel_segments=1, bevel_profile=0.5)
check("bevel width 0 is a harmless no-op",
      strip is not None and len(strip.data.polygons) == base_faces
      and len(cube.data.polygons) == before,
      f"{len(strip.data.polygons) if strip else 0} faces, source {len(cube.data.polygons)}")

failed = [r for r in R if not r[0]]
print("\n" + "=" * 60); print(f"RESULT: {len(R)-len(failed)}/{len(R)} checks passed")
for _, n, dd in failed: print("  FAIL", n, "--", dd)
print("=" * 60)
sys.exit(1 if failed else 0)
