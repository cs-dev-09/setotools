import bpy, sys
sys.path.append(r"D:\SetoClaude\setotools")
R=[]
def check(n,c,d=""):
    R.append((bool(c),n,d)); print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f"  -- {d}" if d and not c else ""))
    return bool(c)

import void_tools
if getattr(bpy.types, "SETO_PT_smooth_edge_panel", None) is None:
    void_tools.register()
szi = sys.modules["void_tools.shared.sollumz_integration"]

# What GTA's own damage strip (hn_apt_hall_blk_milo) uses - the base Strength
# scales from, and what Strength 1.0 has to land on exactly.
REFERENCE = {"useTessellation": 0.0, "bumpiness": 0.50,
             "specularIntensityMult": 0.125, "specularFalloffMult": 100.00,
             "specularFresnel": 0.97}

# What a strip is actually built with. The shipped default is Strength 4.0, not
# GTA's 1.0: the reference values read too faintly on a softly lit interior wall.
DEFAULT_STRENGTH = 4.0
SHIPPED = dict(REFERENCE,
               bumpiness=REFERENCE["bumpiness"] * DEFAULT_STRENGTH,
               specularIntensityMult=REFERENCE["specularIntensityMult"] * DEFAULT_STRENGTH)
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

check("the shipped Strength default is 4.0",
      abs(bpy.context.scene.seto_fake_damage.bl_rna
          .properties["strength"].default - DEFAULT_STRENGTH) < 1e-6,
      str(bpy.context.scene.seto_fake_damage.bl_rna.properties["strength"].default))

dmg = build(bpy.ops.seto.create_fake_damage, "Edge Wear")
if dmg:
    got = read_params(dmg, SHIPPED)
    for k, v in SHIPPED.items():
        check(f"Edge Wear material {k} = {v}", got[k] is not None and abs(got[k]-v) < 1e-4,
              f"{got[k]}")

print("=== Strength drives the two values that decide readability ===")
# Strength 1.0 has to be GTA's own numbers exactly, or every default in the
# panel stops meaning what its tooltip says.
check("Strength 1.0 is GTA's pair",
      szi.damage_strength_parameters(1.0)
      == {"bumpiness": REFERENCE["bumpiness"],
          "specularIntensityMult": REFERENCE["specularIntensityMult"]},
      str(szi.damage_strength_parameters(1.0)))
check("Strength 4.0 doubles the bump and opens the specular",
      szi.damage_strength_parameters(4.0) == {"bumpiness": 2.0,
                                             "specularIntensityMult": 0.5},
      str(szi.damage_strength_parameters(4.0)))
check("Strength is ceilinged, not unbounded",
      szi.damage_strength_parameters(1000.0) == szi.STRENGTH_CEILINGS,
      str(szi.damage_strength_parameters(1000.0)))
check("Strength touches only its own two values",
      set(szi.damage_strength_parameters(2.0)) == set(szi.STRENGTH_PARAMETERS))

if dmg:
    strip = bpy.context.active_object
    check("the strip is the active object", strip.seto_fake_damage_data.is_fake_damage)
    check("a fresh material reads back as the default Strength",
          abs((szi.read_damage_strength(dmg) or 0.0) - DEFAULT_STRENGTH) < 1e-4,
          str(szi.read_damage_strength(dmg)))

    # The point of the whole change: dragging Strength must reach the material
    # without regenerating the mesh - it is a shader value, not geometry. Dragged
    # away from the default, so a value that never arrived cannot pass by
    # happening to match it.
    before = len(strip.data.polygons)
    strip.seto_fake_damage_data.strength = 2.0
    got = read_params(dmg, REFERENCE)
    check("dragging Strength writes bumpiness", abs(got["bumpiness"] - 1.0) < 1e-4,
          str(got["bumpiness"]))
    check("dragging Strength writes specularIntensityMult",
          abs(got["specularIntensityMult"] - 0.25) < 1e-4,
          str(got["specularIntensityMult"]))
    for name in ("useTessellation", "specularFalloffMult", "specularFresnel"):
        check(f"Strength leaves {name} alone",
              abs(got[name] - REFERENCE[name]) < 1e-4, str(got[name]))
    check("Strength does not rebuild the mesh", len(strip.data.polygons) == before,
          f"{before} -> {len(strip.data.polygons)}")
    check("and the material reads back at what was set",
          abs((szi.read_damage_strength(dmg) or 0.0) - 2.0) < 1e-4,
          str(szi.read_damage_strength(dmg)))

    # Reuse never rewrites, so the second strip must come out wearing the first
    # one's Strength rather than the panel's - and say so.
    bpy.context.scene.seto_fake_damage.strength = DEFAULT_STRENGTH
    bpy.context.scene.seto_fake_damage.material_mode = 'AUTO'
    second = build(bpy.ops.seto.create_fake_damage, "second Edge Wear")
    if second:
        check("reuse found the same material", second is dmg, second.name)
        check("the reused strip's slider shows the material, not the panel",
              abs(bpy.context.active_object.seto_fake_damage_data.strength - 2.0) < 1e-3,
              str(bpy.context.active_object.seto_fake_damage_data.strength))

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
