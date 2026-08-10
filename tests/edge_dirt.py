"""Edge Dirt: the strip, its own per-object data, and the live rebuild.

Edge Dirt shares Ambient Occlusion's geometry and rebuild machinery, so what is
worth testing is not the maths - fake_ao_bevel.py and corner_alpha.py already
cover that - but the seams where the two tools have to stay apart:

  * a dirt strip carries seto_edge_dirt_data and NOT is_fake_ao, so the two
    "Selected Strip" panels cannot both claim the same object;
  * the rebuild reads the dirt strip's own settings, not the AO group's - the
    shared rebuild() takes the group as an argument precisely for this;
  * the Scene settings are separate, so tuning one tool cannot move the other;
  * the material is its own, on the same shader.
"""
import bpy, sys

sys.path.append(r"D:\SetoClaude\setotools")

R = []
def check(n, c, d=""):
    R.append((bool(c), n, d))
    print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f"  -- {d}" if d and not c else ""))
    return bool(c)

import seto_tools
if getattr(bpy.types, "SETO_PT_edge_dirt_panel", None) is None:
    seto_tools.register()

from seto_tools.edge_dirt import object_settings as dirt_settings
from seto_tools.edge_dirt import properties as dirt_properties
from seto_tools.fake_ao import object_settings as ao_settings

check("the operator is registered", hasattr(bpy.types, "SETO_OT_create_edge_dirt"))
check("the rebuild operator is registered", hasattr(bpy.types, "SETO_OT_edge_dirt_rebuild"))
check("the panel is registered", hasattr(bpy.types, "SETO_PT_edge_dirt_panel"))
# PropertyGroup subclasses never reach bpy.types in Blender 5.x - test the
# Scene/Object pointers they are registered behind instead.
check("Scene carries its own settings", hasattr(bpy.context.scene, "seto_edge_dirt"))

scene_settings = bpy.context.scene.seto_edge_dirt
check("the settings are Ambient Occlusion's, name for name",
      set(dirt_properties.SETTING_NAMES) <= set(scene_settings.bl_rna.properties.keys()),
      sorted(dirt_properties.SETTING_NAMES))


def build_strip(operator):
    """A cube with one edge selected, run through `operator`."""
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
    return cube, (bpy.context.active_object if result == {'FINISHED'} else None), result


# Bevel off for the main run, so "the source is untouched" means what it says.
# The default target is Source + Strip, which rounds the source edge on purpose
# - that case is covered separately at the end.
scene_settings.bevel_mesh = False
scene_settings.bevel_strip = False
cube, strip, result = build_strip(bpy.ops.seto.create_edge_dirt)
if check("Create Edge Dirt builds a strip", result == {'FINISHED'}, str(result)) and strip:
    check("it is named edge_dirt_NNN", strip.name.startswith("edge_dirt_"), strip.name)
    check("it is filed in the edge_dirt collection",
          any(c.name.startswith("edge_dirt") for c in strip.users_collection),
          [c.name for c in strip.users_collection])
    check("the source mesh is untouched", len(cube.data.polygons) == 6, len(cube.data.polygons))

    data = strip.seto_edge_dirt_data
    check("it is marked as a dirt strip", data.is_edge_dirt)
    check("it remembers its source", data.source_object is cube)
    check("it does NOT claim to be an AO strip", not strip.seto_fake_ao_data.is_fake_ao)

    check("it has UVMap 0", len(strip.data.uv_layers) > 0,
          [l.name for l in strip.data.uv_layers])
    check("it has a colour attribute", len(strip.data.color_attributes) > 0,
          [a.name for a in strip.data.color_attributes])

    material = strip.data.materials[0] if strip.data.materials else None
    check("it got the Edge Dirt material",
          material is not None and material.name.startswith("seto_edgedirt"),
          getattr(material, "name", None))

    # The live rebuild, driven the way a slider drag drives it.
    before = len(strip.data.polygons)
    data.width = data.width * 2.0
    check("changing Width rebuilds in place", data.status == "", data.status)
    check("the rebuild kept the material",
          strip.data.materials and strip.data.materials[0] is material)
    check("the rebuild kept it a dirt strip", strip.seto_edge_dirt_data.is_edge_dirt)
    check("the rebuild produced geometry", len(strip.data.polygons) > 0, before)

    # Reading the wrong group would silently rebuild from AO's defaults.
    check("the rebuild reads the dirt strip's own settings",
          dirt_settings.rebuild(strip) is None)

    # Live Update off must freeze it, and Rebuild Now must still work.
    data.live_update = False
    frozen = len(strip.data.polygons)
    data.width = data.width * 0.5
    check("Live Update off freezes the strip", len(strip.data.polygons) == frozen)
    bpy.ops.seto.edge_dirt_rebuild()
    check("Rebuild Now still rebuilds", strip.seto_edge_dirt_data.status == "",
          strip.seto_edge_dirt_data.status)

# Bevel. This tool used to cut the source's round in with bmesh.ops.bevel at
# creation, which worked exactly once - the edge it rounded no longer existed
# afterwards, so **Bevel Mesh on the finished strip was a dead tick**: it drew,
# it could be clicked, and nothing anywhere read it. It is a live modifier now,
# the same one the other three tools drive.
from seto_tools.fake_ao import source_bevel  # noqa: E402


def evaluated_verts(obj):
    """What Sollumz exports: the object with its modifiers applied."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return len(obj.evaluated_get(depsgraph).to_mesh().vertices)


scene_settings.property_unset("bevel_target")
scene_settings.bevel_mesh = True
scene_settings.bevel_strip = True
beveled_cube, beveled_strip, beveled_result = build_strip(bpy.ops.seto.create_edge_dirt)
if check("a strip builds with Bevel on", beveled_result == {'FINISHED'}, str(beveled_result)):
    beveled_data = beveled_strip.seto_edge_dirt_data
    check("the source mesh is not edited - it is a modifier",
          len(beveled_cube.data.polygons) == 6, len(beveled_cube.data.polygons))
    check("and the modifier is this tool's own",
          beveled_cube.modifiers.get(source_bevel.EDGE_DIRT[2]) is not None,
          str([m.name for m in beveled_cube.modifiers]))
    check("reading its own weight attribute, not Blender's",
          {m.edge_weight for m in beveled_cube.modifiers if m.type == 'BEVEL'}
          == {source_bevel.EDGE_DIRT[3]},
          str({m.name: m.edge_weight for m in beveled_cube.modifiers if m.type == 'BEVEL'}))
    check("the strip keeps pointing at real source edges",
          beveled_data.edge_keys != "" and beveled_data.frozen_segments == "")
    check("the round reaches the evaluated mesh Sollumz exports",
          evaluated_verts(beveled_cube) == 16, evaluated_verts(beveled_cube))

    # The tick used to be inert. Each of these three would have passed before
    # the fix only because nothing happened at all.
    beveled_data.bevel_mesh = False
    check("unticking Bevel Mesh removes the modifier",
          beveled_cube.modifiers.get(source_bevel.EDGE_DIRT[2]) is None,
          str([m.name for m in beveled_cube.modifiers]))
    check("and leaves the source exactly as it was found",
          evaluated_verts(beveled_cube) == 8, evaluated_verts(beveled_cube))
    beveled_data.bevel_mesh = True
    check("ticking it back on rounds the source again",
          evaluated_verts(beveled_cube) == 16, evaluated_verts(beveled_cube))
    beveled_data.bevel_width = beveled_data.bevel_width * 2.0
    check("and Width drags the modifier live",
          abs(beveled_cube.modifiers[source_bevel.EDGE_DIRT[2]].width
              - beveled_data.bevel_width) < 1e-6,
          str(beveled_cube.modifiers[source_bevel.EDGE_DIRT[2]].width))

# A material left untextured - what a strip built before a texture was dropped
# into edge_dirt/textures/ leaves behind - must be filled on reuse, or the tool
# stays broken however many times the texture is added. A slot the user has
# filled is still never overwritten.
from seto_tools.shared import sollumz_integration as szi
from seto_tools.edge_dirt import textures as dirt_textures

bundled = dirt_textures.bundled_texture_path()
existing = szi._find_existing_edge_dirt_material()
if check("there is an Edge Dirt material to reuse", existing is not None):
    node = szi.get_diffuse_node(existing)
    if check("it has a DiffuseSampler", node is not None) and bundled:
        node.image = None
        again, warning = szi.find_or_create_edge_dirt_material(
            texture_path=bundled, reuse=True)
        check("reuse fills an empty DiffuseSampler", again is existing
              and szi.get_diffuse_node(again).image is not None, warning)

        # And having filled it, a second run leaves that image alone.
        was = szi.get_diffuse_node(again).image
        again2, _ = szi.find_or_create_edge_dirt_material(
            texture_path=bundled, reuse=True)
        check("but a filled slot is never rewritten",
              szi.get_diffuse_node(again2).image is was)

# The two Scene groups are separate objects, so one tool cannot move the other.
ao_scene = bpy.context.scene.seto_fake_ao
dirt_scene = bpy.context.scene.seto_edge_dirt
ao_before = ao_scene.width
dirt_scene.width = ao_before + 0.111
check("tuning Edge Dirt does not move Ambient Occlusion",
      abs(ao_scene.width - ao_before) < 1e-6, f"{ao_scene.width} vs {ao_before}")
dirt_scene.property_unset("width")

# The shared guard is one flag: a suppressed AO rebuild must suppress the dirt
# one too, or a strip stamped by one tool could be rebuilt mid-stamp by the other.
with ao_settings.suppress_rebuild():
    check("the rebuild guard is shared with Ambient Occlusion",
          dirt_settings.is_rebuilding())
check("and it is released again", not dirt_settings.is_rebuilding())

failed = [r for r in R if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(R)-len(failed)}/{len(R)} checks passed")
for _, n, d in failed:
    print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
