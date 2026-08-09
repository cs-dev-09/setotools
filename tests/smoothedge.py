import bpy, sys, os
sys.path.append(r"D:\SetoClaude\setotools")
RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

import seto_tools
from seto_tools.smooth_edge import textures
if getattr(bpy.types, "SETO_PT_smooth_edge_panel", None) is None:
    seto_tools.register()

panel = getattr(bpy.types, "SETO_PT_smooth_edge_panel", None)
check("Smooth Edge panel registered", panel is not None)
check("it is in the Seto Tools tab", panel and panel.bl_category == "Seto Tools", getattr(panel, "bl_category", None))
fake_ao_panel = getattr(bpy.types, "SETO_PT_fake_ao_panel", None)
damage_panel = getattr(bpy.types, "SETO_PT_fake_damage_panel", None)
decal_panel = getattr(bpy.types, "SETO_PT_decal_tool_panel", None)
# The tab is grouped by what a tool works on, so what matters is that this
# stays with the other two edge-strip tools and above the surface ones - not
# which number it happens to hold.
check("it sits with the other edge-strip tools, above the surface tools",
      panel and damage_panel and decal_panel
      and damage_panel.bl_order < panel.bl_order < decal_panel.bl_order,
      {c.__name__: c.bl_order for c in (fake_ao_panel, damage_panel, panel, decal_panel) if c})
check("its operator exists", "create_smooth_edge" in dir(bpy.ops.seto))
check("its scene settings exist", hasattr(bpy.context.scene, "seto_smooth_edge"))
check("Fake Damage is untouched and still registered",
      getattr(bpy.types, "SETO_PT_fake_damage_panel", None) is not None
      and "create_fake_damage" in dir(bpy.ops.seto))

print("bundled texture:", repr(textures.bundled_texture_path()))

# Build a strip on a cube edge.
bpy.ops.mesh.primitive_cube_add(size=2)
cube = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_mode(type='EDGE')
bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.object.mode_set(mode='OBJECT')
cube.data.edges[0].select = True
bpy.ops.object.mode_set(mode='EDIT')
try:
    result = bpy.ops.seto.create_smooth_edge()
except RuntimeError as e:
    print("   (op error:", e, ")")
    result = {'CANCELLED'}
if bpy.context.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
check("Create Smooth Edge produced a strip", result == {'FINISHED'}, str(result))

strips = [o for o in bpy.data.objects if o.name.startswith("smooth_edge_")]
check("named smooth_edge_NNN", len(strips) == 1, str([o.name for o in bpy.data.objects]))
if strips:
    s = strips[0]
    check("filed in the 'smooth_edge' collection",
          "smooth_edge" in [c.name for c in s.users_collection],
          str([c.name for c in s.users_collection]))
    check("SHADE SMOOTH: every face is smooth",
          all(p.use_smooth for p in s.data.polygons),
          f"{sum(p.use_smooth for p in s.data.polygons)}/{len(s.data.polygons)}")
    mat = s.data.materials[0] if s.data.materials else None
    check("uses decal_normal_only.sps",
          mat is not None and mat.shader_properties.filename == "decal_normal_only.sps",
          getattr(getattr(mat, "shader_properties", None), "filename", None))
    check("material is named seto_smoothedge",
          mat is not None and mat.name.startswith("seto_smoothedge"), getattr(mat, "name", None))
    check("does NOT reuse the Fake Damage material",
          mat is not None and not mat.name.startswith("seto_fakedamage"), getattr(mat, "name", None))
    if mat:
        bump = mat.node_tree.nodes.get("BumpSampler")
        diff = mat.node_tree.nodes.get("DiffuseSampler")
        if textures.bundled_texture_path():
            check("TEXTURE: BumpSampler filled from the bundled file",
                  bump is not None and bump.image is not None)
            check("TEXTURE: DiffuseSampler filled too",
                  diff is not None and diff.image is not None)
            check("TEXTURE: loaded as Non-Color",
                  bump and bump.image and bump.image.colorspace_settings.name == 'Non-Color',
                  bump.image.colorspace_settings.name if bump and bump.image else None)
            check("TEXTURE: not embedded",
                  bump is not None and not bump.texture_properties.embedded)
        else:
            check("TEXTURE: empty folder is reported, not crashed",
                  bump is not None and bump.image is None)
    # UV orientation: the island must be taller than it is wide.
    uv = s.data.uv_layers.active
    us = [l.uv[0] for l in uv.data]; vs = [l.uv[1] for l in uv.data]
    w, h = max(us) - min(us), max(vs) - min(vs)
    check("UV island is VERTICAL (taller than wide)", h > w, f"{w:.4f} wide x {h:.4f} tall")
    # The island is deliberately fitted to UV_SIZE (1.5), centred on 0.5 - the
    # long axis overflows 0..1 on purpose, exactly as Fake Damage has always
    # done. What matters is that it is centred and vertical.
    check("UV island is centred on (0.5, 0.5)",
          abs((min(us) + max(us)) / 2 - 0.5) < 1e-4 and abs((min(vs) + max(vs)) / 2 - 0.5) < 1e-4,
          f"u {min(us):.3f}..{max(us):.3f} v {min(vs):.3f}..{max(vs):.3f}")
    check("its long axis spans UV_SIZE", abs(h - 1.5) < 1e-4, f"{h:.4f}")
    # Live rebuild must keep both.
    s.seto_smooth_edge_data.width = 0.09
    check("live rebuild keeps shade smooth",
          all(p.use_smooth for p in s.data.polygons))
    uv = s.data.uv_layers.active
    us = [l.uv[0] for l in uv.data]; vs = [l.uv[1] for l in uv.data]
    check("live rebuild keeps the UV vertical",
          (max(vs) - min(vs)) > (max(us) - min(us)),
          f"{max(us)-min(us):.4f} x {max(vs)-min(vs):.4f}")

failed = [r for r in RESULTS if not r[0]]
print("\n" + "="*60)
print(f"RESULT: {len(RESULTS)-len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("="*60)
sys.exit(1 if failed else 0)
