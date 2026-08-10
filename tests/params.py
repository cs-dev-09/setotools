import bpy, sys
sys.path.append(r"D:\SetoClaude\setotools")
R=[]
def check(n,c,d=""):
    R.append((bool(c),n,d)); print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f"  -- {d}" if d and not c else ""))
    return bool(c)

import seto_tools
if getattr(bpy.types, "SETO_PT_smooth_edge_panel", None) is None:
    seto_tools.register()
szi = sys.modules["seto_tools.shared.sollumz_integration"]

# What GTA's own damage strip (hn_apt_hall_blk_milo) uses.
REFERENCE = {"useTessellation": 0.0, "bumpiness": 0.50,
             "specularIntensityMult": 0.125, "specularFalloffMult": 100.00,
             "specularFresnel": 0.97}
# What Smooth Edge had before, and must still have.
SMOOTH_EDGE_BEFORE = {"useTessellation": 0.0, "bumpiness": 1.00,
                      "specularIntensityMult": 0.00, "specularFalloffMult": 40.00,
                      "specularFresnel": 0.75}

check("Edge Wear constants match GTA's reference", szi.VALUE_PARAMETERS == REFERENCE,
      str(szi.VALUE_PARAMETERS))
check("Smooth Edge constants are untouched",
      szi.SMOOTH_EDGE_VALUE_PARAMETERS == SMOOTH_EDGE_BEFORE,
      str(szi.SMOOTH_EDGE_VALUE_PARAMETERS))

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
    return bpy.context.active_object.data.materials[0]

def read_params(mat, names):
    out = {}
    for n in names:
        node = mat.node_tree.nodes.get(n)
        out[n] = round(node.get(0), 4) if node is not None else None
    return out

dmg = build(bpy.ops.seto.create_fake_damage, "Edge Wear")
if dmg:
    got = read_params(dmg, REFERENCE)
    for k, v in REFERENCE.items():
        check(f"Edge Wear material {k} = {v}", got[k] is not None and abs(got[k]-v) < 1e-4,
              f"{got[k]}")

se = build(bpy.ops.seto.create_smooth_edge, "Smooth Edge")
if se:
    got = read_params(se, SMOOTH_EDGE_BEFORE)
    for k, v in SMOOTH_EDGE_BEFORE.items():
        check(f"Smooth Edge material {k} still {v}", got[k] is not None and abs(got[k]-v) < 1e-4,
              f"{got[k]}")

failed=[r for r in R if not r[0]]
print("\n"+"="*60); print(f"RESULT: {len(R)-len(failed)}/{len(R)} checks passed")
for _,n,d in failed: print("  FAIL",n,"--",d)
print("="*60)
sys.exit(1 if failed else 0)
