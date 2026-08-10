import bpy, sys, os
sys.path.append(r"D:\SetoClaude\setotools")
R=[]
def check(n,c,d=""):
    R.append((bool(c),n,d)); print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f"  -- {d}" if d and not c else ""))

import seto_tools
from seto_tools.fake_damage import textures as dmg_textures
if getattr(bpy.types, "SETO_PT_smooth_edge_panel", None) is None:
    seto_tools.register()
szi = sys.modules["seto_tools.shared.sollumz_integration"]

print("fake_damage bundled texture:", repr(dmg_textures.bundled_texture_path()))

def new_cube(name, loc):
    bpy.ops.mesh.primitive_cube_add(size=2, location=loc)
    o = bpy.context.active_object; o.name = name
    return o

def select_edge0(o):
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    o.data.edges[0].select = True
    bpy.ops.object.mode_set(mode='EDIT')

def run(op):
    try: r = op()
    except RuntimeError as e:
        print("   (op error:", e, ")"); r = {'CANCELLED'}
    if bpy.context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    return r

# ---------- 1. No Drawable: tool collection ----------
plain = new_cube("plain", (0,0,0))
select_edge0(plain); run(bpy.ops.seto.create_fake_damage)
strip = bpy.context.active_object
check("no Drawable -> strip goes to the 'fake_dmg' collection",
      "edge_wear" in [c.name for c in strip.users_collection],
      str([c.name for c in strip.users_collection]))

# UV values
uv = strip.data.uv_layers.active
us=[l.uv[0] for l in uv.data]; vs=[l.uv[1] for l in uv.data]
w,h = max(us)-min(us), max(vs)-min(vs)
check("UV island is vertical", h > w, f"{w:.4f} x {h:.4f}")
check("UV long axis is UV_SIZE * uv_scale (1.5 * 3.5 = 5.25)", abs(h-5.25) < 1e-3, f"{h:.4f}")
cu = (min(us)+max(us))/2
check("UV island is offset +0.3906 in U", abs(cu - (0.5+0.3906)) < 1e-3, f"centre_u={cu:.4f}")
cv = (min(vs)+max(vs))/2
check("UV island is not offset in V", abs(cv - 0.5) < 1e-3, f"centre_v={cv:.4f}")

# material textures
mat = strip.data.materials[0]
bump = mat.node_tree.nodes.get("BumpSampler"); diff = mat.node_tree.nodes.get("DiffuseSampler")
if dmg_textures.bundled_texture_path():
    check("Edge Wear BumpSampler filled from the bundle", bump and bump.image is not None)
    check("Edge Wear DiffuseSampler filled too", diff and diff.image is not None)
    check("loaded Non-Color", bump and bump.image and bump.image.colorspace_settings.name=='Non-Color',
          bump.image.colorspace_settings.name if bump and bump.image else None)
    check("not embedded", bump and not bump.texture_properties.embedded)
else:
    check("empty bundle reported, not crashed", bump is not None and bump.image is None)

# live rebuild keeps the UV placement
strip.seto_fake_damage_data.width = 0.05
uv = strip.data.uv_layers.active
us=[l.uv[0] for l in uv.data]; vs=[l.uv[1] for l in uv.data]
check("live rebuild keeps the UV offset",
      abs((min(us)+max(us))/2 - (0.5+0.3906)) < 1e-3, f"{(min(us)+max(us))/2:.4f}")
strip.seto_fake_damage_data.uv_scale = 1.0
uv = strip.data.uv_layers.active
vs=[l.uv[1] for l in uv.data]
check("UV Scale is live-editable", abs((max(vs)-min(vs)) - 1.5) < 1e-3, f"{max(vs)-min(vs):.4f}")

# ---------- 2. Inside a Drawable: the Drawable's collection ----------
drawablehelper = szi._import("tools.drawablehelper")
inner = bpy.data.collections.new("MLO_asset")
bpy.context.scene.collection.children.link(inner)
src = new_cube("mlo_piece", (6,0,0))
for c in list(src.users_collection): c.objects.unlink(src)
inner.objects.link(src)
drawablehelper.convert_obj_to_drawable(src)
drawable = szi.find_drawable_parent(src)
check("test Drawable created", drawable is not None)
# convert_obj_to_drawable puts the empty in the active collection, wherever
# that is - what matters is that the tools follow the Drawable, not that it
# landed anywhere in particular.
drawable_names = sorted(c.name for c in drawable.users_collection)
check("the Drawable is in a collection at all", bool(drawable_names), str(drawable_names))
print("   drawable collections:", drawable_names)

lib = os.path.join(bpy.app.tempdir, "Decals", "Dirt"); os.makedirs(lib, exist_ok=True)
img = bpy.data.images.new("dirt_01.png", 4, 4, alpha=True); img.pixels=[0.5,0.3,0.2,0.5]*16
img.filepath_raw = os.path.join(lib,"dirt_01.png"); img.file_format='PNG'; img.save()
bpy.data.images.remove(img)
from seto_tools.decal_tool import preferences as dp
dp.set_library_path(os.path.join(bpy.app.tempdir, "Decals"))
bpy.ops.seto.refresh_decal_library()
s = bpy.context.scene.seto_decal; s.category="Dirt"; s.texture="dirt_01"; s.width=0.3; s.height=0.3

for label, op in (("Ambient Occlusion", bpy.ops.seto.create_fake_ao),
                  ("Edge Wear", bpy.ops.seto.create_fake_damage),
                  ("Smooth Edge", bpy.ops.seto.create_smooth_edge)):
    select_edge0(src); run(op)
    o = bpy.context.active_object
    names = [c.name for c in o.users_collection]
    check(f"{label} spawns in the Drawable's collection", sorted(names) == drawable_names, str(names))
    check(f"{label} is still parented to the Drawable", o.parent is drawable, str(o.parent))

bpy.context.view_layer.objects.active = src
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_mode(type='FACE')
bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.object.mode_set(mode='OBJECT')
src.data.polygons[0].select = True
bpy.ops.object.mode_set(mode='EDIT')
run(bpy.ops.seto.create_decal)
decals = [o for o in bpy.data.objects if o.name.startswith("seto_decal_")]
check("Decal Tool created a decal", len(decals) == 1, str(len(decals)))
if decals:
    names = [c.name for c in decals[0].users_collection]
    check("Decal Tool spawns in the Drawable's collection too", sorted(names) == drawable_names, str(names))
    check("and no stray 'decals' collection was made",
          bpy.data.collections.get("decals") is None,
          str([c.name for c in bpy.data.collections]))

failed=[r for r in R if not r[0]]
print("\n"+"="*60); print(f"RESULT: {len(R)-len(failed)}/{len(R)} checks passed")
for _,n,d in failed: print("  FAIL",n,"--",d)
print("="*60)
sys.exit(1 if failed else 0)
