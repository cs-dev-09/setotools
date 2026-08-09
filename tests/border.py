import bpy, os, sys
sys.path.append(r"D:\SetoClaude\setotools")
R=[]
def check(n,c,d=""):
    R.append((bool(c),n,d)); print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f"  -- {d}" if d and not c else ""))
    return bool(c)
def same(g,e,t=1.0/255):
    return len(g)==len(e) and all(abs(a-b)<=t for a,b in zip(g,e))

import seto_tools
if getattr(bpy.types, "SETO_PT_decal_tool_panel", None) is None:
    seto_tools.register()
from seto_tools.decal_tool import preferences as dp, geometry

lib = os.path.join(bpy.app.tempdir, "B", "Dirt"); os.makedirs(lib, exist_ok=True)
im = bpy.data.images.new("dirt_01.png",4,4,alpha=True); im.pixels=[.5,.3,.2,.5]*16
im.filepath_raw=os.path.join(lib,"dirt_01.png"); im.file_format='PNG'; im.save(); bpy.data.images.remove(im)
dp.set_library_path(os.path.join(bpy.app.tempdir,"B")); bpy.ops.seto.refresh_decal_library()
s = bpy.context.scene.seto_decal
s.category="Dirt"; s.texture="dirt_01"; s.width=2.0; s.height=1.0; s.edge_fade=0.2
s.random_position=False; s.random_rotation=False; s.random_scale=False

bpy.ops.mesh.primitive_cube_add(size=4)
cube = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_mode(type='FACE')
bpy.ops.mesh.select_all(action='DESELECT'); bpy.ops.object.mode_set(mode='OBJECT')
cube.data.polygons[0].select = True
bpy.ops.object.mode_set(mode='EDIT')
try: bpy.ops.seto.create_decal()
except RuntimeError as e: print("  (err", e, ")")
bpy.ops.object.mode_set(mode='OBJECT')

d = [o for o in bpy.data.objects if o.name.startswith("seto_decal_")][0]
m = d.data
check("decal is a 4x4 grid: 16 verts", len(m.vertices)==16, str(len(m.vertices)))
check("decal is 9 quads", len(m.polygons)==9, str(len(m.polygons)))
check("all faces are quads", all(len(p.vertices)==4 for p in m.polygons))
check("shaded smooth", all(p.use_smooth for p in m.polygons))

# Outer boundary must still be exactly Width x Height.
xs=[v.co.x for v in m.vertices]; ys=[v.co.y for v in m.vertices]
check("outer boundary is Width x Height",
      abs((max(xs)-min(xs))-2.0)<1e-5 and abs((max(ys)-min(ys))-1.0)<1e-5,
      f"{max(xs)-min(xs):.4f} x {max(ys)-min(ys):.4f}")
inner_x = sorted({round(v,4) for v in xs}); inner_y = sorted({round(v,4) for v in ys})
check("border inset by Edge Fade in X", abs((inner_x[1]-inner_x[0])-0.2)<1e-4, str(inner_x))
check("border inset by Edge Fade in Y", abs((inner_y[1]-inner_y[0])-0.2)<1e-4, str(inner_y))

# THE requirement: every outer-boundary vertex is alpha 0.
attr = m.attributes["Color 1"]
uv = m.attributes["UVMap 0"]
loops = [(m.loops[i].vertex_index, attr.data[i].color_srgb[3]) for i in range(len(m.loops))]
def is_outer(vi):
    v = m.vertices[vi].co
    return (abs(abs(v.x)-1.0)<1e-5) or (abs(abs(v.y)-0.5)<1e-5)
outer_alphas = sorted({round(a,3) for vi,a in loops if is_outer(vi)})
inner_alphas = sorted({round(a,3) for vi,a in loops if not is_outer(vi)})
check("EVERY outer edge vertex has alpha 0", outer_alphas==[0.0], str(outer_alphas))
check("inner rectangle is fully opaque", same(inner_alphas,[1.0]), str(inner_alphas))

# UVs still span 0..1 across the outer boundary, undistorted.
us=[e.vector[0] for e in uv.data]; vs=[e.vector[1] for e in uv.data]
check("UVs span 0..1 across the outer boundary",
      abs(min(us))<1e-5 and abs(max(us)-1)<1e-5 and abs(min(vs))<1e-5 and abs(max(vs)-1)<1e-5,
      f"u {min(us):.4f}..{max(us):.4f} v {min(vs):.4f}..{max(vs):.4f}")

# Live edits must preserve the border.
data = d.seto_decal_data
data.width = 3.0
xs=[v.co.x for v in m.vertices]
check("live resize keeps the outer size correct", abs((max(xs)-min(xs))-3.0)<1e-5, str(max(xs)-min(xs)))
outer_alphas = sorted({round(attr.data[i].color_srgb[3],3)
                       for i in range(len(m.loops))
                       if abs(abs(m.vertices[m.loops[i].vertex_index].co.x)-1.5)<1e-5})
check("live resize keeps the border at alpha 0", outer_alphas==[0.0], str(outer_alphas))
us=[e.vector[0] for e in uv.data]
check("live resize keeps UVs at 0..1", abs(min(us))<1e-5 and abs(max(us)-1)<1e-5,
      f"{min(us):.4f}..{max(us):.4f}")

data.corner_alpha = (0.0, 0.0, 1.0, 1.0)
outer_alphas = sorted({round(attr.data[i].color_srgb[3],3)
                       for i in range(len(m.loops))
                       if abs(abs(m.vertices[m.loops[i].vertex_index].co.y)-0.5)<1e-5})
check("corner alpha never resurrects the border", outer_alphas==[0.0], str(outer_alphas))

data.edge_fade = 0.5
xs=sorted({round(v.co.x,4) for v in m.vertices})
check("Edge Fade is live-editable", abs((xs[1]-xs[0])-0.5)<1e-4, str(xs))

# A fade wider than the decal must blunt, not invert.
data.edge_fade = 99.0
xs=sorted({round(v.co.x,4) for v in m.vertices})
check("an over-wide fade clamps instead of inverting", xs[1] <= xs[2] + 1e-6, str(xs))
check("material survived every live edit", len(m.materials)==1)

# ---------------------------------------------------------------- per-side border
data.width = 2.0; data.height = 1.0; data.edge_fade = 0.2
data.corner_alpha = (1.0, 1.0, 1.0, 1.0)
data.border_alpha = (0.0, 0.0, 0.0, 0.0)

def side_of(vi):
    """Which outer sides a border vertex belongs to."""
    v = m.vertices[vi].co
    sides = set()
    if abs(v.y - min(y.co.y for y in m.vertices)) < 1e-5: sides.add("Bottom")
    if abs(v.x - max(x.co.x for x in m.vertices)) < 1e-5: sides.add("Right")
    if abs(v.y - max(y.co.y for y in m.vertices)) < 1e-5: sides.add("Top")
    if abs(v.x - min(x.co.x for x in m.vertices)) < 1e-5: sides.add("Left")
    return sides

def alphas_on(side, exclusive=True):
    """Alphas of the loops on `side`; exclusive skips the shared ring corners."""
    out = set()
    for i, loop in enumerate(m.loops):
        s = side_of(loop.vertex_index)
        if side in s and (not exclusive or len(s) == 1):
            out.add(round(attr.data[i].color_srgb[3], 3))
    return sorted(out)

check("all sides at 0 by default", all(alphas_on(x)==[0.0] for x in ("Bottom","Right","Top","Left")),
      str({x: alphas_on(x) for x in ("Bottom","Right","Top","Left")}))

# Bottom hard, the other three faded - the "decal meets the floor" case.
data.border_alpha = (1.0, 0.0, 0.0, 0.0)
check("a raised side keeps its own edge opaque", alphas_on("Bottom")==[1.0], str(alphas_on("Bottom")))
check("the other sides stay faded",
      alphas_on("Right")==[0.0] and alphas_on("Top")==[0.0] and alphas_on("Left")==[0.0],
      str({x: alphas_on(x) for x in ("Right","Top","Left")}))

# Where a hard side meets a faded one, the lower value wins.
corner = [i for i, loop in enumerate(m.loops) if side_of(loop.vertex_index) == {"Bottom","Left"}]
check("a shared ring corner takes the lower of its two sides",
      all(round(attr.data[i].color_srgb[3],3)==0.0 for i in corner),
      str(sorted({round(attr.data[i].color_srgb[3],3) for i in corner})))

data.border_alpha = (1.0, 1.0, 1.0, 1.0)
check("all sides can be made hard", all(alphas_on(x)==[1.0] for x in ("Bottom","Right","Top","Left")),
      str({x: alphas_on(x) for x in ("Bottom","Right","Top","Left")}))
check("the inner rectangle is unaffected by border values",
      sorted({round(attr.data[i].color_srgb[3],3) for i,l in enumerate(m.loops)
              if l.vertex_index in set(geometry.INNER_CORNER_VERTS)}) == [1.0])

data.border_alpha = (0.0, 0.5, 0.0, 0.5)
# Color 1 is BYTE_COLOR, so 0.5 lands on 128/255 - compare with a byte of slack.
check("sides can hold different partial values",
      same(alphas_on("Right"), [0.5]) and same(alphas_on("Bottom"), [0.0]),
      f"right {alphas_on('Right')} bottom {alphas_on('Bottom')}")

data.border_alpha = (0.0, 0.0, 0.0, 0.0)

failed=[r for r in R if not r[0]]
print("\n"+"="*60); print(f"RESULT: {len(R)-len(failed)}/{len(R)} checks passed")
for _,n,dd in failed: print("  FAIL",n,"--",dd)
print("="*60)
sys.exit(1 if failed else 0)
