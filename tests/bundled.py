import bpy, sys, os
sys.path.append(r"D:\SetoClaude\setotools")
R=[]
def check(n,c,d=""):
    R.append((bool(c),n,d)); print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f"  -- {d}" if d and not c else ""))
    return bool(c)

import seto_tools
if getattr(bpy.types, "SETO_PT_smooth_edge_panel", None) is None:
    seto_tools.register()
from seto_tools.fake_ao import textures as ao_tex
from seto_tools.edge_dirt import textures as dirt_tex
from seto_tools.fake_damage import textures as dmg_tex
from seto_tools.smooth_edge import textures as se_tex

for label, mod, folder in (("Ambient Occlusion", ao_tex, "fake_ao"),
                           ("Edge Dirt", dirt_tex, "edge_dirt"),
                           ("Edge Wear", dmg_tex, "fake_damage"),
                           ("Smooth Edge", se_tex, "smooth_edge")):
    exists = os.path.isdir(mod.TEXTURE_DIRECTORY)
    check(f"{label} has a textures/ folder", exists, mod.TEXTURE_DIRECTORY)
    check(f"{label} folder is inside its own tool", folder in mod.TEXTURE_DIRECTORY.replace("\\", "/"))
    print(f"   {label} bundled: {mod.bundled_texture_path() or '(empty)'}")

def build(op, label, sampler_names, colorspace, mat_prefix):
    bpy.ops.mesh.primitive_cube_add(size=2)
    cube = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    cube.data.edges[0].select = True
    bpy.ops.object.mode_set(mode='EDIT')
    try: r = op()
    except RuntimeError as e:
        print("   (op error:", e, ")"); r = {'CANCELLED'}
    if bpy.context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    if not check(f"{label} created a strip", r == {'FINISHED'}, str(r)):
        return
    strip = bpy.context.active_object
    mat = strip.data.materials[0] if strip.data.materials else None
    check(f"{label} got its own material '{mat_prefix}'",
          mat is not None and mat.name.startswith(mat_prefix), getattr(mat, "name", None))
    if mat is None: return
    path = None
    for n in sampler_names:
        node = mat.node_tree.nodes.get(n)
        check(f"{label} {n} exists on its shader", node is not None)
        if node is None: continue
        has = node.image is not None
        expected = bool({"Ambient Occlusion": ao_tex, "Edge Dirt": dirt_tex,
                         "Edge Wear": dmg_tex, "Smooth Edge": se_tex}[label].bundled_texture_path())
        check(f"{label} {n} image assigned: {expected}", has == expected,
              f"image={node.image.name if node.image else None}")
        if has:
            check(f"{label} {n} colour space is {colorspace}",
                  node.image.colorspace_settings.name == colorspace,
                  node.image.colorspace_settings.name)
            check(f"{label} {n} is not embedded", not node.texture_properties.embedded)
    return mat

ao_mat = build(bpy.ops.seto.create_fake_ao, "Ambient Occlusion", ("DiffuseSampler",), "sRGB", "seto_fakeao")
dirt_mat = build(bpy.ops.seto.create_edge_dirt, "Edge Dirt", ("DiffuseSampler",), "sRGB", "seto_edgedirt")
dmg_mat = build(bpy.ops.seto.create_fake_damage, "Edge Wear", ("BumpSampler", "DiffuseSampler"), "Non-Color", "seto_fakedamage")
se_mat = build(bpy.ops.seto.create_smooth_edge, "Smooth Edge", ("BumpSampler", "DiffuseSampler"), "Non-Color", "seto_smoothedge")

names = [m for m in (ao_mat, dirt_mat, dmg_mat, se_mat) if m]
check("the four tools never share a material", len({m.name for m in names}) == len(names),
      str([m.name for m in names]))
check("Ambient Occlusion does not adopt a Decal Tool material",
      ao_mat is None or not ao_mat.name.startswith("seto_decal_mat_"), getattr(ao_mat, "name", None))
check("Edge Wear and Smooth Edge stay apart despite the same shader",
      dmg_mat is None or se_mat is None or dmg_mat is not se_mat)
check("Edge Dirt and Ambient Occlusion stay apart despite the same shader",
      dirt_mat is None or ao_mat is None or dirt_mat is not ao_mat)

failed=[r for r in R if not r[0]]
print("\n"+"="*60); print(f"RESULT: {len(R)-len(failed)}/{len(R)} checks passed")
for _,n,d in failed: print("  FAIL",n,"--",d)
print("="*60)
sys.exit(1 if failed else 0)
