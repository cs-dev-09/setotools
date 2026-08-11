"""The Texture Budget, end to end.

What matters: that texel density is measured against **world** area, so a
scaled object is graded as what it covers in game; that the scene total
counts a shared texture once, because a texture worn by forty props is
streamed once and totalling it per object would report a cost nobody pays;
that an object with no texture is not treated as a failure; and that Finish
gives every colour back.
"""
import bpy, sys, math

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

import seto_tools
if getattr(bpy.types, "SETO_PT_texture_budget_panel", None) is None:
    seto_tools.register()

from seto_tools.texture_budget import geometry, operators
from seto_tools.shared import budget, viewport_grade as vg

print("=== the maths ===")
check("texel density is the square root of pixels over area",
      geometry.texel_density(1024 * 1024, 4.0) == 512.0)
check("no area means nothing to measure",
      geometry.texel_density(1024, 0.0) is None)
check("no texture means nothing to measure",
      geometry.texel_density(0, 4.0) is None)
check("ratio is density over target",
      abs(geometry.ratio(1024 * 1024, 4.0, 1024.0) - 0.5) < 1e-9)
check("the suggested size is a power of two at the target",
      geometry.suggested_size(4.0, 1024.0) == 2048,
      geometry.suggested_size(4.0, 1024.0))
check("and never smaller than something usable",
      geometry.suggested_size(0.0001, 1024.0) == 8)
check("VRAM counts the mip chain",
      abs(geometry.vram_bytes(1024) - 1024 * 4 / 3) < 1e-6)
check("bytes are formatted for humans",
      geometry.format_bytes(2 * 1024 * 1024) == "2.0 MB")

scene = bpy.context.scene
settings = scene.seto_texture_budget
settings.scope = 'SELECTED'
view = bpy.context.view_layer


def deselect_all():
    for obj in view.objects:
        obj.select_set(False)


def textured(name, size, plane_size=2.0):
    """A plane wearing one generated square texture."""
    bpy.ops.mesh.primitive_plane_add(size=plane_size)
    obj = bpy.context.active_object
    obj.name = name
    image = bpy.data.images.new(name + "_tex", width=size, height=size)
    material = bpy.data.materials.new(name + "_mat")
    material.use_nodes = True
    node = material.node_tree.nodes.new('ShaderNodeTexImage')
    node.image = image
    obj.data.materials.append(material)
    return obj, image


print("=== a 2K sheet on a small plane, a 256 on the same plane ===")
big, big_image = textured("tex_big", 2048)        # 4 m², 2048²
small, _ = textured("tex_small", 256)             # 4 m², 256²
small.location.x = 4

deselect_all()
big.select_set(True)
small.select_set(True)
bpy.ops.seto.texture_analyze()

check("the big one measures 1024 texels/m",
      abs(big[operators.TEXELS_PROP] - 1024.0) < 1.0,
      big.get(operators.TEXELS_PROP))
check("the small one measures 128",
      abs(small[operators.TEXELS_PROP] - 128.0) < 1.0,
      small.get(operators.TEXELS_PROP))
check("so the big one lands on 1x of the default target",
      abs(geometry.ratio(big[operators.PIXELS_PROP],
                         big[operators.AREA_PROP], settings.target) - 1.0)
      < 1e-2)
check("the big one is drawn at yellow, not red",
      abs(budget.fraction(1.0) - 0.5) < 1e-9)
# Compared on the red channel, not the green: yellow's green channel is
# *higher* than green's, so "greener" cannot be read off that one.
check("the small one is cooler on the ramp than the big one",
      small.color[0] < big.color[0], (tuple(small.color), tuple(big.color)))
check("the scene total counted two textures", settings.image_count == 2,
      settings.image_count)
check("and named the biggest", settings.biggest_name == big_image.name
      and settings.biggest_size == 2048,
      (settings.biggest_name, settings.biggest_size))

print("=== world space: the same sheet on a bigger surface is cheaper ===")
wide, _ = textured("tex_wide", 2048)
wide.location.y = 4
wide.scale = (4.0, 4.0, 1.0)      # 64 m², sixteen times the area
deselect_all()
wide.select_set(True)
bpy.ops.seto.texture_analyze()
check("four times the width is a quarter the texel density",
      abs(wide[operators.TEXELS_PROP] - 256.0) < 1.0,
      wide.get(operators.TEXELS_PROP))

print("=== a shared texture is streamed once ===")
shared_a, shared_image = textured("tex_shared_a", 512)
shared_a.location.y = -4
bpy.ops.mesh.primitive_plane_add(size=2)
shared_b = bpy.context.active_object
shared_b.name = "tex_shared_b"
shared_b.location.y = -8
shared_b.data.materials.append(shared_a.data.materials[0])

deselect_all()
shared_a.select_set(True)
shared_b.select_set(True)
bpy.ops.seto.texture_analyze()
check("two objects wearing one texture count it once",
      settings.image_count == 1, settings.image_count)
check("and the total is that texture's pixels, not twice them",
      abs(settings.total_pixels - 512 * 512) < 1.0, settings.total_pixels)

print("=== nothing to grade is not a failure ===")
bpy.ops.mesh.primitive_plane_add(size=2)
bare = bpy.context.active_object
bare.name = "tex_bare"
bare.location.z = 4
deselect_all()
bare.select_set(True)
bpy.ops.seto.texture_analyze()
check("an untextured mesh is flagged as unmeasurable",
      bare[operators.TEXELS_PROP] == operators.NO_TEXTURE)
check("and painted neutral grey rather than red",
      abs(bare.color[0] - bare.color[1]) < 1e-6
      and abs(bare.color[1] - bare.color[2]) < 1e-6, tuple(bare.color))

print("=== Finish gives every colour back ===")
# A fresh object, and its colour set *before* any analysis touches it: a
# colour typed in while a session is up is painted over by the next grade
# and is not what Finish promises to restore.
own_obj, _ = textured("tex_own_colour", 256)
own_obj.location.z = -4
own = (0.11, 0.22, 0.33, 1.0)
own_obj.color = own
deselect_all()
own_obj.select_set(True)
bpy.ops.seto.texture_analyze()
check("it was painted over", tuple(own_obj.color) != own)
bpy.ops.seto.texture_clear()
check("the object's own colour returned",
      all(abs(a - b) < 1e-5 for a, b in zip(own_obj.color, own)),
      tuple(own_obj.color))
check("its measurements are gone",
      all(p not in own_obj for p in operators.OWN_PROPS))
check("the session is free", scene.seto_grade.owner == "")
check("and the scene totals were reset", settings.image_count == 0)

print("=== an empty scope refuses instead of pretending ===")
deselect_all()
try:
    bpy.ops.seto.texture_analyze()
    check("empty scope is an error", False, "operator ran")
except RuntimeError as e:
    check("empty scope is an error", "No mesh objects" in str(e), e)

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
