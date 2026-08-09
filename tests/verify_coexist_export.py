"""Second verification pass: the three Seto add-ons coexist, and a generated
decal survives a real Sollumz YDR export."""

import os
import shutil
import sys
import tempfile
import traceback

import bpy
from mathutils import Matrix

REPO_ROOT = r"D:\SetoClaude\setotools"
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

import seto_tools
from seto_tools.decal_tool import preferences as decal_prefs
from seto_tools.shared import sollumz_integration as szi

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((bool(condition), name, detail))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not condition else ""))
    return bool(condition)


def write_png(path):
    image = bpy.data.images.new(os.path.basename(path), 4, 4, alpha=True)
    image.pixels = [0.5, 0.3, 0.2, 0.5] * 16
    image.filepath_raw = path
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)


def main():
    tmp = tempfile.mkdtemp(prefix="seto_coexist_")
    lib = os.path.join(tmp, "Decals", "Dirt")
    os.makedirs(lib)
    write_png(os.path.join(lib, "dirt_01.png"))

    # 1. All three register together, in one tab, in order. Some may already be
    # enabled as installed add-ons in this Blender - registering twice raises, so
    # only the missing ones are registered here (and only those unregistered).
    registered = []
    if getattr(bpy.types, "SETO_PT_decal_tool_panel", None) is None:
        seto_tools.register()
        registered.append(seto_tools)
    else:
        print("       (seto_tools was already enabled in this Blender)")

    # The tab is two sections, and each tool nests inside the one that matches
    # what it produces: Geometry builds new mesh along the selected edges,
    # Surface puts texture on a surface that is already there. The checks below
    # are about that grouping, not about which number a panel happens to hold -
    # renumbering to insert a tool is fine, moving one out of its section is
    # not. A tool parented to a section that failed to register is not merely
    # misplaced: Blender drops the panel and the tab loses the tool.
    groups = ("SETO_PT_geometry_group", "SETO_PT_surface_group")
    geometry_tools = ("SETO_PT_fake_damage_panel", "SETO_PT_smooth_edge_panel")
    surface_tools = ("SETO_PT_fake_ao_panel", "SETO_PT_decal_tool_panel",
                     "SETO_PT_surface_painter_panel")

    panels = {}
    for name in groups + geometry_tools + surface_tools:
        panels[name] = getattr(bpy.types, name, None)
        check(f"{name} is registered", panels[name] is not None)

    check("every panel shares the 'Seto Tools' tab",
          all(p is not None and p.bl_category == "Seto Tools" for p in panels.values()),
          str({k: getattr(v, "bl_category", None) for k, v in panels.items()}))

    check("the two sections are the tab's top level",
          all(not getattr(panels[n], "bl_parent_id", "") for n in groups)
          and panels[groups[0]].bl_order < panels[groups[1]].bl_order,
          str({n: getattr(panels[n], "bl_order", None) for n in groups}))

    for group, tools in ((groups[0], geometry_tools), (groups[1], surface_tools)):
        parents = {n: getattr(panels[n], "bl_parent_id", None) for n in tools}
        check(f"every {group} tool is nested under it",
              all(p == group for p in parents.values()), str(parents))
        orders = {n: getattr(panels[n], "bl_order", None) for n in tools}
        check(f"every {group} tool has its own place in the section",
              len(set(orders.values())) == len(orders) and None not in orders.values(),
              str(orders))

    check("each tool keeps its own scene settings",
          hasattr(bpy.context.scene, "seto_fake_ao")
          and hasattr(bpy.context.scene, "seto_fake_damage")
          and hasattr(bpy.context.scene, "seto_decal"))
    check("all three Create operators exist in the one add-on",
          hasattr(bpy.ops.seto, "create_fake_ao")
          and hasattr(bpy.ops.seto, "create_fake_damage")
          and hasattr(bpy.ops.seto, "create_decal"))

    # 1c. Each tool files its output in its own collection, no "seto" prefix.
    bpy.ops.mesh.primitive_cube_add(size=2, location=(6, 0, 0))
    strip_source = bpy.context.active_object
    strip_source.name = "strip_source"

    def make_strip(operator, label, expected_collection):
        bpy.context.view_layer.objects.active = strip_source
        strip_source.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        strip_source.data.edges[0].select = True
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            result = operator()
        except RuntimeError as e:
            print(f"       ({label} error: {e})")
            result = {'CANCELLED'}
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        if not check(f"{label} created a strip", result == {'FINISHED'}, str(result)):
            return
        strip = bpy.context.active_object
        names = [c.name for c in strip.users_collection]
        check(f"{label} files it in '{expected_collection}'",
              expected_collection in names, str(names))
        check(f"{label} does not leave it next to the source",
              "Scene Collection" not in names and "Collection" not in names, str(names))

    make_strip(bpy.ops.seto.create_fake_ao, "Fake AO", "fake_ao")
    make_strip(bpy.ops.seto.create_fake_damage, "Fake Damage", "fake_dmg")

    check("no generated collection carries a 'seto' prefix",
          not any("seto" in c.name.lower() for c in bpy.data.collections),
          str([c.name for c in bpy.data.collections]))

    # 2. Build a decal inside a real Sollumz Drawable and export it.
    sollumz_properties = szi._import("sollumz_properties")
    drawablehelper = szi._import("tools.drawablehelper")

    bpy.ops.mesh.primitive_cube_add(size=2)
    source = bpy.context.active_object
    source.name = "mlo_piece"
    drawablehelper.convert_obj_to_drawable(source)
    # Give the source its own Sollumz material too, so the export log is clean and
    # any warning that does appear is attributable to the decal.
    shader_materials = szi._import("ydr.shader_materials")
    source_material = shader_materials.create_shader("default.sps")
    szi.assign_material_to_object(source, source_material)
    drawable = szi.find_drawable_parent(source)
    check("test Drawable was created", drawable is not None)

    settings = bpy.context.scene.seto_decal
    decal_prefs.set_library_path(os.path.join(tmp, "Decals"))
    bpy.ops.seto.refresh_decal_library()
    settings.category = "Dirt"
    settings.texture = "dirt_01"
    settings.width = 0.5
    settings.height = 0.5

    bpy.context.view_layer.objects.active = source
    source.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    source.data.polygons[0].select = True
    bpy.ops.object.mode_set(mode='EDIT')
    result = bpy.ops.seto.create_decal()
    bpy.ops.object.mode_set(mode='OBJECT')
    check("decal created on the Drawable's mesh", result == {'FINISHED'}, str(result))

    decals = [o for o in bpy.data.objects if o.name.startswith("seto_decal_")]
    check("exactly one decal for one selected face", len(decals) == 1, str(len(decals)))
    if decals:
        decal = decals[0]
        check("decal joined the Drawable hierarchy", decal.parent is drawable, str(decal.parent))
        check("decal is a Drawable Model",
              decal.sollum_type == sollumz_properties.SollumType.DRAWABLE_MODEL, decal.sollum_type)

        # The alpha path Sollumz builds for decal.sps (decalflag 1): the texture
        # alpha is multiplied by Color 1 alpha and drives a Mix Shader against a
        # Transparent BSDF. Without it a transparent PNG would render opaque.
        tree = decal.data.materials[0].node_tree
        kinds = {n.bl_idname for n in tree.nodes}
        check("material has the transparency mix Sollumz builds for decal.sps",
              "ShaderNodeMixShader" in kinds and "ShaderNodeBsdfTransparent" in kinds,
              str(sorted(kinds)))
        vertex_color_nodes = [n for n in tree.nodes if n.bl_idname == "ShaderNodeVertexColor"]
        check("alpha is driven by the Color 1 attribute",
              any(n.layer_name == "Color 1" for n in vertex_color_nodes),
              str([n.layer_name for n in vertex_color_nodes]))

    # 3. Real Sollumz export.
    out_dir = os.path.join(tmp, "export")
    os.makedirs(out_dir)
    for obj in bpy.data.objects:
        obj.select_set(False)
    drawable.select_set(True)
    bpy.context.view_layer.objects.active = drawable
    # Export settings live in Sollumz's addon preferences, not on the operator.
    preferences = szi._import("sollumz_preferences")
    export_settings = preferences.get_export_settings()
    export_settings.limit_to_selected = True
    # Sollumz 2.8.x has the legacy CodeWalker-XML exporter; 2.9.0 dropped it in
    # favour of the RAGE asset exporter. Use whichever this Blender has.
    # hasattr() on bpy.ops is always True (attribute access is lazy), so the
    # existence check has to go through dir().
    exporter = ("export_assets_legacy" if "export_assets_legacy" in dir(bpy.ops.sollumz)
                else "export_assets")
    print(f"       (exporting with sollumz.{exporter})")
    try:
        export_result = getattr(bpy.ops.sollumz, exporter)(
            directory=out_dir, direct_export=True,
        )
    except Exception as e:
        export_result = f"raised: {e}"
    written = os.listdir(out_dir)
    check("Sollumz YDR export succeeded", export_result == {'FINISHED'}, str(export_result))
    check("a .ydr was written", any(".ydr" in f.lower() for f in written), str(written))

    # Only the CodeWalker-XML export is inspectable as text. The binary .ydr that
    # 2.9.0 writes stores names as hashes, so there is nothing to grep for - a
    # clean "Successfully exported" with no warnings is the signal there.
    for f in written:
        if not f.lower().endswith(".xml"):
            continue
        raw = open(os.path.join(out_dir, f), "rb").read()
        check("exported drawable references decal.sps", b"decal.sps" in raw, f)
        check("exported drawable references the decal texture", b"dirt_01" in raw, f)
        break
    else:
        print("       (binary .ydr export - content not text-inspectable, skipped)")

    for module in reversed(registered):
        module.unregister()
    shutil.rmtree(tmp, ignore_errors=True)


try:
    main()
except Exception:
    traceback.print_exc()
    RESULTS.append((False, "coexistence/export script crashed", ""))

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 70)
print(f"RESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
for _, name, detail in failed:
    print(f"  FAIL  {name}  -- {detail}")
print("=" * 70)
sys.exit(1 if failed else 0)
