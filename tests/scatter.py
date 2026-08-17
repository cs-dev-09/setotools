"""Trash Scatter, end to end - the sampling maths and the entity plumbing.

What matters here: that the same seed reproduces the same layout (the seed
is a design control, not a dice roll); that spacing is honoured so props
never stack; that Edge Bias measurably pulls the layout toward the region
boundary; that every preset name really exists in the catalogue with a
bounding box that grounds it; and that Scatter registers each proxy as an
MLO entity on the right archetype, attaches it to the room whose bounds
hold it, replaces its own previous run instead of stacking, and that Clear
takes both the proxies and their entity rows away.
"""
import math
import sys

import bpy

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  -- {detail}" if detail and not cond else ""))


import void_tools  # noqa: E402
if getattr(bpy.types, "SETO_PT_scatter_panel", None) is None:
    void_tools.register()

from mathutils import Vector  # noqa: E402
from void_tools.scatter import (  # noqa: E402
    catalog, geometry, library, object_settings, operators)
from void_tools.shared import addon_prefs  # noqa: E402

# Never let this run write test paths into the user's saved preferences.
bpy.context.preferences.use_preferences_save = False

# The user's real prop library must not dress the deterministic sections:
# boxes vs models is part of what they assert. Restored at the end.
_prefs = addon_prefs.get()
_saved_library = getattr(_prefs, "scatter_library", "") if _prefs else ""
if _prefs is not None:
    _prefs.scatter_library = ""
library.forget()

print("=== the catalogue holds together ===")
for preset_id, entries in catalog.PRESETS.items():
    check(f"{preset_id}: every prop has measured bounds",
          all(name in catalog.PROPS for name, _w in entries),
          [name for name, _w in entries if name not in catalog.PROPS])
    check(f"{preset_id}: every weight is positive",
          all(w > 0 for _n, w in entries))
check("preset enum and preset table agree",
      {item[0] for item in catalog.PRESET_ITEMS} == set(catalog.PRESETS))
for name, (bb_min, bb_max) in catalog.PROPS.items():
    if not all(hi >= lo for lo, hi in zip(bb_min, bb_max)):
        check(f"{name} bounds are ordered", False, (bb_min, bb_max))
        break
else:
    check("all bounds are min<=max", True)
check("grounding puts bbMin.z on the floor",
      all(abs(catalog.PROPS[n][0][2] + catalog.ground_offset(n)) < 1e-9
          for n in catalog.PROPS))
check("every footprint radius is positive",
      all(catalog.footprint_radius(n) > 0.0 for n in catalog.PROPS))

print("=== the sampling maths, before any scene is involved ===")
SQUARE = [(Vector((0, 0, 0)), Vector((4, 0, 0)), Vector((4, 4, 0))),
          (Vector((0, 0, 0)), Vector((4, 4, 0)), Vector((0, 4, 0)))]
RIM = [(0, 0, 4, 0), (4, 0, 4, 4), (4, 4, 0, 4), (0, 4, 0, 0)]
# (weight, upright radius, lying radius, standing)
ITEMS = [(1.0, 0.05, 0.05, False), (2.0, 0.1, 0.12, True)]

a = geometry.scatter(SQUARE, RIM, ITEMS, 1.0, 7, 0.0, 0.1)
b = geometry.scatter(SQUARE, RIM, ITEMS, 1.0, 7, 0.0, 0.1)
check("same seed, same layout",
      len(a) == len(b) and all(
          (p.position - q.position).length < 1e-12 and p.item == q.item
          and abs(p.yaw - q.yaw) < 1e-12 and abs(p.scale - q.scale) < 1e-12
          for p, q in zip(a, b)))
c = geometry.scatter(SQUARE, RIM, ITEMS, 1.0, 8, 0.0, 0.1)
check("different seed, different layout",
      len(a) != len(c) or any(
          (p.position - q.position).length > 1e-6 for p, q in zip(a, c)))
check("density is honoured on an easy floor (16 m2 at 1/m2)",
      len(a) == 16, len(a))
check("everything lands inside the region",
      all(0 <= p.position.x <= 4 and 0 <= p.position.y <= 4 for p in a))


def min_gap(placements):
    worst = math.inf
    for i, p in enumerate(placements):
        for q in placements[i + 1:]:
            dx = p.position.x - q.position.x
            dy = p.position.y - q.position.y
            worst = min(worst, math.hypot(dx, dy) - (p.radius + q.radius))
    return worst


check("spacing is honoured - no two props overlap", min_gap(a) >= 0.0,
      min_gap(a))


RIM_INDEX = geometry.BoundaryIndex(RIM)


def mean_rim_distance(placements):
    return sum(RIM_INDEX.distance(p.position)
               for p in placements) / len(placements)


print("=== the boundary index answers what the full scan answered ===")
import random as _random  # noqa: E402
_rng = _random.Random(3)
worst = 0.0
for _ in range(300):
    probe = Vector((_rng.uniform(-2.0, 6.0), _rng.uniform(-2.0, 6.0), 0.0))
    slow = min(
        math.sqrt(geometry._segment_distance_sq(probe.x, probe.y, *seg))
        for seg in RIM)
    fast = RIM_INDEX.distance(probe)
    worst = max(worst, abs(min(slow, geometry.BOUNDARY_REACH) - fast))
check("the index matches an exhaustive scan (clamped at its reach)",
      worst < 1e-9, worst)
check("an empty boundary set reads as far away",
      geometry.BoundaryIndex([]).distance(Vector((0, 0, 0)))
      == geometry.BOUNDARY_REACH)


uniform = geometry.scatter(SQUARE, RIM, ITEMS, 2.0, 3, 0.0, 0.0)
hugging = geometry.scatter(SQUARE, RIM, ITEMS, 2.0, 3, 1.0, 0.0)
check("edge bias pulls the layout to the walls",
      mean_rim_distance(hugging) < mean_rim_distance(uniform) * 0.6,
      (mean_rim_distance(hugging), mean_rim_distance(uniform)))

check("no triangles, no placements",
      geometry.scatter([], RIM, ITEMS, 1.0, 1, 0.5, 0.1) == [])
check("no items, no placements",
      geometry.scatter(SQUARE, RIM, [], 1.0, 1, 0.5, 0.1) == [])
upright = geometry.scatter(SQUARE, RIM, ITEMS, 2.0, 5, 0.0, 0.0,
                           topple=0.0)
toppled = geometry.scatter(SQUARE, RIM, ITEMS, 2.0, 5, 0.0, 0.0,
                           topple=1.0)
check("topple 0 stands everything up",
      all(not p.lying for p in upright))
check("topple 1 lays every standing item down, flat items stay flat",
      all(p.lying == (ITEMS[p.item][3]) for p in toppled)
      and any(p.lying for p in toppled))

check("a standing prop knows it stands",
      catalog.is_standing("prop_beer_bottle")
      and catalog.is_standing("ng_proc_sodabot_01a")
      and not catalog.is_standing("ng_proc_paper_02a"))
check("a lying bottle rests on its rolled bounding box",
      abs(catalog.ground_offset_lying("prop_beer_bottle") - 0.0374) < 1e-4,
      catalog.ground_offset_lying("prop_beer_bottle"))

biased = geometry.scatter(SQUARE, RIM, ITEMS, 2.0, 6, 0.0, 0.0,
                          field=lambda p: 1.0 if p.x < 2.0 else 0.0)
left = sum(1 for p in biased if p.position.x < 2.0)
right = len(biased) - left
check("a dirt field pulls the litter where it is dark",
      left > right * 1.5, (left, right))


def mean_nearest_neighbour(placements):
    total = 0.0
    for i, p in enumerate(placements):
        best = math.inf
        for j, q in enumerate(placements):
            if i == j:
                continue
            best = min(best, math.hypot(p.position.x - q.position.x,
                                        p.position.y - q.position.y))
        total += best
    return total / len(placements)


def clumpiness(placements):
    """Mean nearest-neighbour distance, normalised for the point count.

    Clustering rejects many samples, so the heaped run has fewer points -
    raw distances grow with sparsity and would hide the heaps. Dividing
    by the expected spacing of a uniform layout with the same count
    (~0.5·√(area/n)) makes the two comparable: uniform ≈ 1, heaps < 1.
    """
    expected = 0.5 * math.sqrt(16.0 / len(placements))
    return mean_nearest_neighbour(placements) / expected


spread = geometry.scatter(SQUARE, RIM, ITEMS, 2.0, 8, 0.0, 0.0,
                          clustering=0.0)
heaped = geometry.scatter(SQUARE, RIM, ITEMS, 2.0, 8, 0.0, 0.0,
                          clustering=1.0)
check("clustering pulls the litter into heaps",
      len(heaped) > 3 and clumpiness(heaped) < clumpiness(spread) * 0.8,
      (round(clumpiness(heaped), 3), round(clumpiness(spread), 3)))
check("clustered layouts are still seeded",
      all((p.position - q.position).length < 1e-12 for p, q in zip(
          heaped, geometry.scatter(SQUARE, RIM, ITEMS, 2.0, 8, 0.0, 0.0,
                                   clustering=1.0))))

tiny = geometry.scatter(SQUARE, RIM, [(1.0, 3.0, 3.0, False)], 5.0, 1,
                        0.0, 0.0)
check("impossible spacing degrades to fewer, never to overlap",
      0 < len(tiny) < 80 and min_gap(tiny) >= 0.0
      if len(tiny) > 1 else len(tiny) > 0, len(tiny))

print("=== the region's rim comes from faces, not from mesh edges ===")
# Two quads meeting along x=1 with their own, unwelded vertices - which
# is how a real MLO floor is slabbed. Every side is owned by one bmesh
# edge, so edge-based rim detection called the seam a wall and both the
# litter and the grime piled along it in game.
seam_mesh = bpy.data.meshes.new("seam_floor")
seam_mesh.from_pydata(
    [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
     (1, 0, 0), (2, 0, 0), (2, 1, 0), (1, 1, 0)],
    [], [(0, 1, 2, 3), (4, 5, 6, 7)])
seam_floor = bpy.data.objects.new("seam_floor", seam_mesh)
bpy.context.scene.collection.objects.link(seam_floor)

_tris, _rim = operators._floor_region(seam_floor)
check("both slabs are floor", len(_tris) == 4, len(_tris))
check("the rim is the outside only, not the seam",
      len(_rim) == 6, len(_rim))
seam_hit = [s for s in _rim
            if abs(s[0] - 1.0) < 1e-6 and abs(s[3] - 1.0) < 1e-6]
check("the seam between the slabs is not a wall", not seam_hit, seam_hit)
bpy.data.objects.remove(seam_floor)

print("=== the dirt maths, before any scene is involved ===")
from void_tools.scatter import dirt as dirt_mod  # noqa: E402

check("value noise is deterministic and bounded",
      dirt_mod.value_noise(3.7, -1.2, 42) == dirt_mod.value_noise(3.7, -1.2, 42)
      and all(0.0 <= dirt_mod.value_noise(x * 0.7, x * 1.3, 5) <= 1.0
              for x in range(50)))
check("different seeds, different noise",
      any(abs(dirt_mod.value_noise(x * 0.7, 0.0, 1)
              - dirt_mod.value_noise(x * 0.7, 0.0, 2)) > 0.05
          for x in range(20)))
check("amount 0 is a clean floor",
      all(dirt_mod.dirt_alpha(Vector((x, 0.5, 0)), RIM, 7, 0.0, 1.0, 2.0)
          == 0.0 for x in range(4)))
near = sum(dirt_mod.dirt_alpha(Vector((0.05, y * 0.4, 0)), RIM, 7, 0.6,
                               1.0, 2.0) for y in range(10)) / 10
far = sum(dirt_mod.dirt_alpha(Vector((2.0, y * 0.4, 0)), RIM, 7, 0.6,
                              1.0, 2.0) for y in range(10)) / 10
check("grime pools along the walls, like the litter", near > far,
      (round(near, 3), round(far, 3)))

print("=== scattering a real floor, wired to a real MLO archetype ===")
scene = bpy.context.scene
check("Sollumz's ytyp scene data exists", hasattr(scene, "ytyps"))

root = bpy.data.objects.new("mlo_root", None)
scene.collection.objects.link(root)

bpy.ops.mesh.primitive_plane_add(size=4)  # 16 m2 at the origin
floor = bpy.context.active_object
floor.name = "scatter_floor"
floor.parent = root

ytyp = scene.ytyps.add()
ytyp.name = "test_ytyp"
scene.ytyp_index = len(scene.ytyps) - 1
archetype = ytyp.new_archetype()
archetype.type = 'sollumz_archetype_mlo'
archetype.asset = root
# Rooms as a real MLO has them: room 0 is "limbo" - GTA's outside, with
# bounds that swallow everything and an engine cap on attached entities
# (Sollumz 2.9 enforces it with a popup per entity, which is also a crash
# in background mode). Litter must always land in the real room.
limbo = archetype.new_room()
limbo.name = "limbo"
limbo.bb_min = (-100.0, -100.0, -10.0)
limbo.bb_max = (100.0, 100.0, 10.0)
room = archetype.new_room()
room.name = "den"
room.bb_min = (-10.0, -10.0, -1.0)
room.bb_max = (10.0, 10.0, 4.0)

settings = scene.seto_scatter
settings.preset = 'TRASH'
settings.density = 1.0
settings.seed = 11
settings.edge_bias = 0.5
settings.scale_jitter = 0.1
settings.topple = 0.0  # the grounding check below assumes upright props

bpy.ops.seto.scatter_create()

proxies = [o for o in bpy.data.objects
           if o.get(object_settings.SRC_PROP) == floor.name]
check("proxies landed", len(proxies) > 4, len(proxies))
check("every proxy is a wireframe",
      all(o.display_type == 'WIRE' for o in proxies))
check("every proxy carries a real archetype name",
      all(o.name.split(".")[0] in catalog.PROPS for o in proxies),
      sorted({o.name.split(".")[0] for o in proxies} - set(catalog.PROPS)))
coll = bpy.data.collections.get(object_settings.COLLECTION_NAME)
check("they live in the scatter collection",
      coll is not None and all(o.name in coll.objects for o in proxies))
check("each rests its bounding box on the floor",
      all(abs(o.location.z
              - catalog.ground_offset(o.name.split(".")[0]) * o.scale.z)
          < 1e-5 for o in proxies))

entities = archetype.entities
check("one entity per proxy", len(entities) == len(proxies),
      (len(entities), len(proxies)))
check("entities link back to the proxies",
      all(e.linked_object in set(proxies) for e in entities))
check("entity names have no .NNN suffix",
      all(e.archetype_name in catalog.PROPS for e in entities))
check("entities sit in the room that holds them, never in limbo",
      all(e.attached_room_id == str(room.id) for e in entities),
      sorted({e.attached_room_id for e in entities}))

print("=== the floor dirt overlay - vanilla's own trick, procedural ===")
overlays = [o for o in bpy.data.objects
            if o.get(dirt_mod.MARKER) == floor.name]
check("scatter lays exactly one dirt overlay", len(overlays) == 1,
      len(overlays))
overlay = overlays[0] if overlays else None
if overlay is not None:
    check("the overlay is parented to its floor, in its collection",
          overlay.parent == floor
          and floor.users_collection[0] in overlay.users_collection)
    heights = {round((overlay.matrix_world @ v.co).z, 4)
               for v in overlay.data.vertices}
    check("it floats millimetres above the floor, never in it",
          all(0.001 < h < 0.02 for h in heights), sorted(heights)[:3])
    check("it wears a decal material",
          overlay.data.materials and overlay.data.materials[0] is not None)
    attr = overlay.data.color_attributes[0]
    alphas_set = {round(attr.data[i].color[3], 3)
                  for i in range(len(attr.data))}
    check("the grime pattern varies across the sheet",
          len(alphas_set) > 3 and max(alphas_set) > 0.2
          and min(alphas_set) >= 0.0,
          (len(alphas_set), max(alphas_set) if alphas_set else None))
    quads = sum(1 for p in overlay.data.polygons if len(p.vertices) == 4)
    check("the sheet is mostly quads",
          quads / max(1, len(overlay.data.polygons)) >= 0.6,
          (quads, len(overlay.data.polygons)))

print("=== scatter again replaces, clear removes ===")
settings.seed = 12
bpy.context.view_layer.objects.active = floor
bpy.ops.seto.scatter_create()
proxies2 = [o for o in bpy.data.objects
            if o.get(object_settings.SRC_PROP) == floor.name]
check("a second run replaces the first, never stacks",
      len(proxies2) > 0 and len(archetype.entities) == len(proxies2),
      (len(proxies), len(proxies2), len(archetype.entities)))
check("no dangling entity rows",
      all(e.linked_object is not None for e in archetype.entities))

check("a second run still has exactly one overlay",
      len([o for o in bpy.data.objects
           if o.get(dirt_mod.MARKER) == floor.name]) == 1)

print("=== toppled bottles lie down, live ===")
data = floor.seto_scatter_data
data.density = 2.5  # enough props that bottles are certain to appear
data.topple = 1.0
lying = [o for o in bpy.data.objects
         if o.get(object_settings.SRC_PROP) == floor.name
         and catalog.is_standing(o.name.split(".")[0])]
check("standing props exist to topple", len(lying) > 0, len(lying))
check("at topple 1 every standing prop lies on its side",
      all(abs(o.rotation_euler.x - 3.14159 / 2) < 1e-4 for o in lying))
check("a lying prop rests its rolled box on the floor",
      all(abs(o.location.z
              - catalog.ground_offset_lying(o.name.split(".")[0])
              * o.scale.z) < 1e-5 for o in lying))
data.topple = 0.0
still = [o for o in bpy.data.objects
         if o.get(object_settings.SRC_PROP) == floor.name
         and catalog.is_standing(o.name.split(".")[0])]
check("and at topple 0 they stand again",
      still and all(abs(o.rotation_euler.x) < 1e-6 for o in still))

print("=== optimize crops and thins the dirt overlay ===")
before_faces = len([o for o in bpy.data.objects
                    if o.get(dirt_mod.MARKER) == floor.name][0]
                   .data.polygons)
bpy.context.view_layer.objects.active = floor
bpy.ops.seto.scatter_optimize_dirt()
overlay_now = [o for o in bpy.data.objects
               if o.get(dirt_mod.MARKER) == floor.name][0]
check("optimize cuts the overlay down hard, not politely",
      len(overlay_now.data.polygons) < before_faces * 0.5,
      (before_faces, len(overlay_now.data.polygons)))
loose_faces = len(overlay_now.data.polygons)

# The same sheet again, this time optimized at a tolerance the user
# tightened: fewer faces removed, because less drift is allowed.
data.dirt_amount = 0.0
data.dirt_amount = 0.6                      # a fresh, unoptimized sheet
data.dirt_tolerance = 0.005
bpy.context.view_layer.objects.active = floor
bpy.ops.seto.scatter_optimize_dirt()
tight_faces = len([o for o in bpy.data.objects
                   if o.get(dirt_mod.MARKER) == floor.name][0].data.polygons)
check("a tighter tolerance keeps more of the mesh",
      tight_faces > loose_faces, (tight_faces, loose_faces))
data.dirt_tolerance = 0.08
check("blotch size drives the working spacing",
      dirt_mod.spacing_for(4.0) > dirt_mod.spacing_for(1.0)
      and dirt_mod.spacing_for(0.1) == dirt_mod.MIN_SPACING
      and dirt_mod.spacing_for(99.0) == dirt_mod.MAX_SPACING)

data.dirt_amount = 0.0  # live: a clean floor removes its overlay
check("amount 0 takes the overlay away, live",
      not [o for o in bpy.data.objects
           if o.get(dirt_mod.MARKER) == floor.name])
data.dirt_amount = 0.6
check("and raising it brings the overlay back, live",
      len([o for o in bpy.data.objects
           if o.get(dirt_mod.MARKER) == floor.name]) == 1)

bpy.context.view_layer.objects.active = floor
bpy.ops.seto.scatter_clear()
check("clear removes the proxies",
      not [o for o in bpy.data.objects
           if o.get(object_settings.SRC_PROP) == floor.name])
check("clear removes the entity rows", len(archetype.entities) == 0,
      len(archetype.entities))
check("clear removes the dirt overlay too",
      not [o for o in bpy.data.objects
           if o.get(dirt_mod.MARKER) == floor.name])

print("=== litter avoids whatever stands on the floor ===")
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(1.0, 1.0, 0.5))
table = bpy.context.active_object
table.name = "obstacle_table"
bpy.context.view_layer.objects.active = floor
floor.select_set(True)
settings.density = 3.0
settings.dirt_enabled = False  # isolate the obstacle effect
bpy.ops.seto.scatter_create()
proxies_ob = [o for o in bpy.data.objects
              if o.get(object_settings.SRC_PROP) == floor.name]
under = [o for o in proxies_ob
         if abs(o.location.x - 1.0) < 0.45
         and abs(o.location.y - 1.0) < 0.45]
check("nothing lands under the table", not under,
      [(round(o.location.x, 2), round(o.location.y, 2)) for o in under])
check("the rest of the floor still gets its litter",
      len(proxies_ob) > 10, len(proxies_ob))
bpy.data.objects.remove(table)
bpy.context.view_layer.objects.active = floor
bpy.ops.seto.scatter_clear()
settings.dirt_enabled = True

print("=== edit mode scatters only the selected faces ===")
bpy.ops.mesh.primitive_grid_add(x_subdivisions=4, y_subdivisions=4, size=4)
grid = bpy.context.active_object
grid.name = "scatter_grid"
grid.location = (20.0, 0.0, 0.0)
bpy.ops.object.mode_set(mode='EDIT')
import bmesh  # noqa: E402
bm = bmesh.from_edit_mesh(grid.data)
for face in bm.faces:
    face.select_set(face.calc_center_median().x < 0.0)  # local left half
bmesh.update_edit_mesh(grid.data)

settings.density = 2.0
settings.edge_bias = 0.0
bpy.ops.seto.scatter_create()
bpy.ops.object.mode_set(mode='OBJECT')
half = [o for o in bpy.data.objects if o.get(object_settings.SRC_PROP) == grid.name]
check("edit mode scatters", len(half) > 0, len(half))
check("and only on the selected half",
      all(o.location.x < 20.0 + 0.01 for o in half),
      sorted(round(o.location.x, 2) for o in half)[-3:])

bpy.context.view_layer.objects.active = grid
bpy.ops.seto.scatter_clear()

print("=== live update: the floor's own settings rebuild in place ===")
bpy.context.view_layer.objects.active = floor
settings.density = 1.0
bpy.ops.seto.scatter_create()


def floor_count():
    return sum(1 for o in bpy.data.objects
               if o.get(object_settings.SRC_PROP) == floor.name)


data = floor.seto_scatter_data
base_count = floor_count()
check("live update is on by default", data.live_update)
data.density = 3.0  # no operator: the property callback is the rebuild
live_count = floor_count()
check("dragging Density rebuilds without an operator",
      live_count > base_count, (base_count, live_count))
check("the live rebuild keeps entities one-per-proxy",
      len(archetype.entities) == live_count,
      (len(archetype.entities), live_count))

data.prop_scale = 2.0  # live: every prop doubles
scaled = [o for o in bpy.data.objects
          if o.get(object_settings.SRC_PROP) == floor.name]
check("Prop Scale scales every prop from its live panel",
      scaled and all(1.7 < o.scale.z < 2.3 for o in scaled),
      sorted(round(o.scale.z, 2) for o in scaled)[:3])
data.prop_scale = 1.0

data.live_update = False
data.density = 0.5
check("with Live Update off, nothing moves", floor_count() == live_count,
      floor_count())
bpy.ops.seto.scatter_rebuild()
check("Re-Scatter applies the pending settings",
      0 < floor_count() < live_count, floor_count())
data.live_update = True

bpy.context.view_layer.objects.active = floor
bpy.ops.seto.scatter_clear()

print("=== the prop library dresses what it has, boxes the rest ===")
import os  # noqa: E402
import tempfile  # noqa: E402
lib_dir = tempfile.mkdtemp(prefix="seto_scatter_lib_")
cone = bpy.data.meshes.new("cone_probe")
import bmesh as _bm  # noqa: E402
_b = _bm.new()
_bm.ops.create_cone(_b, cap_ends=True, segments=7, radius1=0.05,
                    radius2=0.0, depth=0.09)
_b.to_mesh(cone)
_b.free()
lib_obj = bpy.data.objects.new("prop_paper_ball", cone)
bpy.data.libraries.write(os.path.join(lib_dir, "props.blend"), {lib_obj})
cone_polys = len(cone.polygons)
bpy.data.objects.remove(lib_obj)
bpy.data.meshes.remove(cone)

# A second library shaped the way Sollumz's own Asset Library builder can
# leave a Drawable: the archetype name is on an EMPTY, and the mesh hangs
# under it as prop_x.001. Asking only for the exact name would append the
# empty, find no mesh, and silently fall back to a box.
sollumz_dir = tempfile.mkdtemp(prefix="seto_scatter_sollumz_")
_b = _bm.new()
_bm.ops.create_cube(_b, size=0.06)
drawable_mesh = bpy.data.meshes.new("drawable_model")
_b.to_mesh(drawable_mesh)
_b.free()
empty = bpy.data.objects.new("prop_cs_paper_cup", None)
model = bpy.data.objects.new("prop_cs_paper_cup.001", drawable_mesh)
model.parent = empty
bpy.data.libraries.write(os.path.join(sollumz_dir, "drawables.blend"),
                         {empty, model})
drawable_polys = len(drawable_mesh.polygons)
bpy.data.objects.remove(model)
bpy.data.objects.remove(empty)
bpy.data.meshes.remove(drawable_mesh)

if _prefs is not None:
    _prefs.scatter_library = sollumz_dir
library.forget()
sollumz_index = library.get_index(allow_scan=True)
check("a Drawable's empty is indexed by its archetype name",
      "prop_cs_paper_cup" in sollumz_index, sorted(sollumz_index))
fetched = library.fetch_meshes(["prop_cs_paper_cup"], sollumz_index)
got = fetched.get("prop_cs_paper_cup")
check("and the mesh under it is what gets used, not a box",
      got is not None and len(got.polygons) == drawable_polys,
      got and len(got.polygons))
if got is not None:
    bpy.data.meshes.remove(got)

if _prefs is not None:
    _prefs.scatter_library = lib_dir
library.forget()
check("a scatter never scans by itself - unindexed reads as empty",
      library.get_index() == {} and not library.is_indexed())
index = library.get_index(allow_scan=True)
check("the library index finds the archetype-named object",
      index.get("prop_paper_ball") is not None, dict(index))
check("and the explicit scan leaves the folder indexed",
      library.is_indexed())

bpy.context.view_layer.objects.active = floor
found_real = []
for seed in range(1, 31):
    settings.seed = seed
    settings.density = 3.0
    bpy.ops.seto.scatter_create()
    found_real = [o for o in bpy.data.objects
                  if o.get(object_settings.SRC_PROP) == floor.name
                  and o.name.split(".")[0] == "prop_paper_ball"]
    if found_real:
        break
check("a library prop lands with its real mesh", bool(found_real))
if found_real:
    check("the real mesh is the library's, not a box",
          all(o.data.name == library.MESH_PREFIX + "prop_paper_ball"
              and len(o.data.polygons) == cone_polys for o in found_real),
          [(o.data.name, len(o.data.polygons)) for o in found_real[:2]])
    check("a dressed prop is not drawn as wireframe",
          all(o.display_type != 'WIRE' for o in found_real))
    check("one appended mesh serves every instance",
          len({o.data for o in found_real}) == 1
          and sum(1 for m in bpy.data.meshes
                  if m.name.startswith(library.MESH_PREFIX)) == 1)
others = [o for o in bpy.data.objects
          if o.get(object_settings.SRC_PROP) == floor.name
          and o.name.split(".")[0] != "prop_paper_ball"]
check("props the library lacks stay wireframe boxes",
      others and all(o.display_type == 'WIRE' for o in others),
      len(others))

if _prefs is not None:
    _prefs.scatter_library = _saved_library
library.forget()
bpy.context.view_layer.objects.active = floor
bpy.ops.seto.scatter_clear()

print("=== a floor with no archetype still scatters, with a warning ===")
bpy.ops.mesh.primitive_plane_add(size=2)
lone = bpy.context.active_object
lone.name = "scatter_lone"
lone.location = (40.0, 0.0, 0.0)
scene.ytyps.remove(0)
bpy.ops.seto.scatter_create()
lone_proxies = [o for o in bpy.data.objects
                if o.get(object_settings.SRC_PROP) == lone.name]
check("proxies still land without an MLO", len(lone_proxies) > 0,
      len(lone_proxies))
check("and the floor keeps the reason where the panel can show it",
      "MLO" in lone.seto_scatter_data.entity_status
      or "YTYP" in lone.seto_scatter_data.entity_status,
      lone.seto_scatter_data.entity_status)
bpy.ops.seto.scatter_clear()

print("=== one MLO in the file is found without any selection help ===")
# The floor is not under the archetype's asset, and the ytyp panel has a
# BASE archetype selected - the common real file. The file's only MLO must
# still be found.
ytyp2 = scene.ytyps.add()
ytyp2.name = "fallback_ytyp"
scene.ytyp_index = len(scene.ytyps) - 1
mlo_arch = ytyp2.new_archetype()
mlo_arch.type = 'sollumz_archetype_mlo'
den2 = mlo_arch.new_room()
den2.name = "den"
den2.bb_min = (-100.0, -100.0, -10.0)
den2.bb_max = (100.0, 100.0, 10.0)
base_arch = ytyp2.new_archetype()  # BASE, and now the selected one
bpy.context.view_layer.objects.active = lone
bpy.ops.seto.scatter_create()
check("the file's only MLO archetype gets the entities",
      len(mlo_arch.entities) > 0
      and len(mlo_arch.entities) == sum(
          1 for o in bpy.data.objects
          if o.get(object_settings.SRC_PROP) == lone.name),
      len(mlo_arch.entities))
check("and the panel's warning clears once they land",
      lone.seto_scatter_data.entity_status == "",
      lone.seto_scatter_data.entity_status)
bpy.ops.seto.scatter_clear()

print()
failed = [r for r in RESULTS if not r[0]]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
if failed:
    for _ok, name, detail in failed:
        print(f"FAILED: {name}  -- {detail}")
    sys.exit(1)
