import bpy, sys
sys.path.append(r"D:\SetoClaude\setotools")
R=[]
def check(n,c,d=""):
    R.append((bool(c),n,d)); print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f"  -- {d}" if d and not c else ""))
    return bool(c)

import seto_tools
if getattr(bpy.types, "SETO_PT_smooth_edge_panel", None) is None:
    seto_tools.register()
from seto_tools.shared import vertex_color

EXPECTED_RGB = (0.0, 0.7, 0.0)
check("shared constant is #00B200", tuple(round(c,4) for c in vertex_color.DEFAULT_RGB) == EXPECTED_RGB,
      str(vertex_color.DEFAULT_RGB))
check("shared alpha centre is 1.0", vertex_color.DEFAULT_ALPHA_CENTER == 1.0)
check("shared alpha outer is 0.0", vertex_color.DEFAULT_ALPHA_OUTER == 0.0)

for prop, label in (("seto_fake_ao","Fake AO"), ("seto_fake_damage","Fake Damage"),
                    ("seto_smooth_edge","Smooth Edge")):
    g = getattr(bpy.context.scene, prop)
    check(f"{label} RGB default is #00B200",
          tuple(round(c,4) for c in g.color_rgb) == EXPECTED_RGB, str(tuple(g.color_rgb)))
    check(f"{label} Alpha Center default is 1.0", abs(g.alpha_center-1.0) < 1e-6, str(g.alpha_center))
    check(f"{label} Alpha Outer default is 0.0", abs(g.alpha_outer-0.0) < 1e-6, str(g.alpha_outer))

def build(op, label):
    bpy.ops.mesh.primitive_cube_add(size=2)
    c = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT'); bpy.ops.object.mode_set(mode='OBJECT')
    c.data.edges[0].select = True
    bpy.ops.object.mode_set(mode='EDIT')
    try: r = op()
    except RuntimeError as e: print("  (err", e, ")"); r={'CANCELLED'}
    if bpy.context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    if not check(f"{label} created", r == {'FINISHED'}, str(r)): return None
    return bpy.context.active_object

def verify(obj, label, expect_alpha_range=True):
    if obj is None: return
    check(f"{label} SHADE SMOOTH on every face",
          all(p.use_smooth for p in obj.data.polygons),
          f"{sum(p.use_smooth for p in obj.data.polygons)}/{len(obj.data.polygons)}")
    attr = obj.data.attributes.get("Color 1")
    if not check(f"{label} has Color 1", attr is not None): return
    rgbs = {tuple(round(c,2) for c in d.color_srgb[:3]) for d in attr.data}
    check(f"{label} writes the green RGB on every loop", rgbs == {(0.0,0.7,0.0)}, str(rgbs))
    alphas = sorted({round(d.color_srgb[3],2) for d in attr.data})
    if expect_alpha_range:
        check(f"{label} alpha runs 0.0 -> 1.0", alphas[0]==0.0 and alphas[-1]==1.0, str(alphas))
    else:
        # The decal is a grid: border ring at 0, inner rectangle at 1.
        check(f"{label} alpha is 0 on the border and 1 inside", alphas == [0.0, 1.0],
              str(alphas))

verify(build(bpy.ops.seto.create_fake_ao, "Fake AO"), "Fake AO")
verify(build(bpy.ops.seto.create_fake_damage, "Fake Damage"), "Fake Damage")
verify(build(bpy.ops.seto.create_smooth_edge, "Smooth Edge"), "Smooth Edge")

# Decal Tool
import os
lib = os.path.join(bpy.app.tempdir, "D", "Dirt"); os.makedirs(lib, exist_ok=True)
im = bpy.data.images.new("dirt_01.png",4,4,alpha=True); im.pixels=[.5,.3,.2,.5]*16
im.filepath_raw=os.path.join(lib,"dirt_01.png"); im.file_format='PNG'; im.save(); bpy.data.images.remove(im)
from seto_tools.decal_tool import preferences as dp
dp.set_library_path(os.path.join(bpy.app.tempdir,"D")); bpy.ops.seto.refresh_decal_library()
s = bpy.context.scene.seto_decal; s.category="Dirt"; s.texture="dirt_01"
bpy.ops.mesh.primitive_cube_add(size=2, location=(9,0,0))
cube = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_mode(type='FACE')
bpy.ops.mesh.select_all(action='DESELECT'); bpy.ops.object.mode_set(mode='OBJECT')
cube.data.polygons[0].select = True
bpy.ops.object.mode_set(mode='EDIT')
try: bpy.ops.seto.create_decal()
except RuntimeError as e: print("  (err", e, ")")
bpy.ops.object.mode_set(mode='OBJECT')
decals=[o for o in bpy.data.objects if o.name.startswith("seto_decal_")]
if check("Decal Tool created", len(decals)==1, str(len(decals))):
    verify(decals[0], "Decal Tool", expect_alpha_range=False)

failed=[r for r in R if not r[0]]
print("\n"+"="*60); print(f"RESULT: {len(R)-len(failed)}/{len(R)} checks passed")
for _,n,d in failed: print("  FAIL",n,"--",d)
print("="*60)
sys.exit(1 if failed else 0)
