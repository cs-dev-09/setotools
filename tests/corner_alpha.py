import bpy, os, sys
sys.path.append(r"D:\SetoClaude\setotools")
R=[]
def check(n,c,d=""):
    R.append((bool(c),n,d)); print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f"  -- {d}" if d and not c else ""))
    return bool(c)

import void_tools
if getattr(bpy.types, "SETO_PT_decal_tool_panel", None) is None:
    void_tools.register()
from void_tools.decal_tool import preferences as dp, geometry

lib = os.path.join(bpy.app.tempdir, "L", "Dirt"); os.makedirs(lib, exist_ok=True)
im = bpy.data.images.new("dirt_01.png",4,4,alpha=True); im.pixels=[.5,.3,.2,.5]*16
im.filepath_raw=os.path.join(lib,"dirt_01.png"); im.file_format='PNG'; im.save(); bpy.data.images.remove(im)
dp.set_library_path(os.path.join(bpy.app.tempdir,"L")); bpy.ops.seto.refresh_decal_library()
s = bpy.context.scene.seto_decal; s.category="Dirt"; s.texture="dirt_01"; s.width=1.0; s.height=1.0

bpy.ops.mesh.primitive_cube_add(size=2)
cube = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_mode(type='FACE')
bpy.ops.mesh.select_all(action='DESELECT'); bpy.ops.object.mode_set(mode='OBJECT')
cube.data.polygons[0].select = True
bpy.ops.object.mode_set(mode='EDIT')
try: bpy.ops.seto.create_decal()
except RuntimeError as e: print("  (err", e, ")")
bpy.ops.object.mode_set(mode='OBJECT')

decals=[o for o in bpy.data.objects if o.name.startswith("seto_decal_")]
if not check("decal created", len(decals)==1, str(len(decals))): sys.exit(1)
d = decals[0]; data = d.seto_decal_data
attr = d.data.attributes["Color 1"]

def alphas():
    """The four inner-corner alphas, in CORNER_NAMES order.

    The decal is a 16-vertex grid now: the border ring is pinned at 0 and the
    corner values live on the inner rectangle, so a loop-order read would be
    mostly border zeros.
    """
    by_vertex = {}
    for i, loop in enumerate(d.data.loops):
        by_vertex.setdefault(loop.vertex_index, round(attr.data[i].color_srgb[3], 3))
    return [by_vertex[v] for v in geometry.INNER_CORNER_VERTS]


def border_alphas():
    inner = set(geometry.INNER_CORNER_VERTS)
    return sorted({round(attr.data[i].color_srgb[3], 3)
                   for i, loop in enumerate(d.data.loops)
                   if loop.vertex_index not in inner})

def same(got, expected):
    """Color 1 is BYTE_COLOR, so a float alpha lands on the nearest 1/255."""
    return len(got) == len(expected) and all(abs(a - b) <= 1.0 / 255 for a, b in zip(got, expected))

check("created fully opaque on all four corners", same(alphas(), [1.0]*4), str(alphas()))
check("corner_alpha property has 4 values", len(data.corner_alpha)==4, str(len(data.corner_alpha)))
check("the border ring stays at alpha 0 throughout", border_alphas()==[0.0], str(border_alphas()))
check("corner order documented", geometry.CORNER_NAMES ==
      ("Bottom Left","Bottom Right","Top Right","Top Left"), str(geometry.CORNER_NAMES))

# One corner at a time - each must land on its own loop.
for i, name in enumerate(geometry.CORNER_NAMES):
    data.corner_alpha = tuple(0.25 if j==i else 1.0 for j in range(4))
    got = alphas()
    expected = [0.25 if j==i else 1.0 for j in range(4)]
    check(f"'{name}' alpha writes only its own corner", same(got, expected), f"{got} vs {expected}")

# A real gradient: transparent along the bottom, opaque along the top.
data.corner_alpha = (0.0, 0.0, 1.0, 1.0)
check("bottom-to-top fade lands on the right loops", same(alphas(), [0.0,0.0,1.0,1.0]), str(alphas()))

# Side to side, and diagonal - the point of having four values.
data.corner_alpha = (0.0, 1.0, 1.0, 0.0)
check("left-to-right fade works too", same(alphas(), [0.0,1.0,1.0,0.0]), str(alphas()))
data.corner_alpha = (0.0, 0.5, 1.0, 0.5)
check("a diagonal gradient works", same(alphas(), [0.0,0.5,1.0,0.5]), str(alphas()))

check("RGB is untouched by alpha changes",
      all(all(abs(e.color_srgb[k]-c)<1e-2 for k,c in enumerate((0.0,0.7,0.0))) for e in attr.data),
      str({tuple(round(c,2) for c in e.color_srgb[:3]) for e in attr.data}))
check("geometry and material untouched",
      len(d.data.vertices)==geometry.GRID_VERTEX_COUNT and len(d.data.materials)==1 and d.data.attributes.get("UVMap 0") is not None)

# Shortcut operators
bpy.context.view_layer.objects.active = d
bpy.ops.seto.decal_alpha_fade_down()
check("Fade Down sets 0 at the bottom, 1 at the top", same(alphas(), [0.0,0.0,1.0,1.0]), str(alphas()))
bpy.ops.seto.decal_alpha_uniform()
check("All 1.0 restores full opacity", same(alphas(), [1.0]*4), str(alphas()))

# Live Update off must hold changes back
data.live_update = False
data.corner_alpha = (0.2,0.2,0.2,0.2)
check("Live Update off holds corner alpha back", same(alphas(), [1.0]*4), str(alphas()))
bpy.ops.seto.decal_rebuild()
check("Update applies it", same(alphas(), [0.2]*4), str(alphas()))
data.live_update = True

failed=[r for r in R if not r[0]]
print("\n"+"="*60); print(f"RESULT: {len(R)-len(failed)}/{len(R)} checks passed")
for _,n,dd in failed: print("  FAIL",n,"--",dd)
print("="*60)
sys.exit(1 if failed else 0)
