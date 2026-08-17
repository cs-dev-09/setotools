"""Sign Glow - the halo behind lit lettering, contributed by Molo Modding.

What is worth pinning here is not "does it make a plane". It is the four
things that would be invisible until someone looked at the sign in game:

* **the silhouette is actually traced** - a halo built from an empty mask is a
  transparent rectangle, and a transparent rectangle looks exactly like a
  working tool until night falls in the scene;
* **the two blurs are two blurs** - the whole idea is a tight core plus a wide
  bloom, and a core radius that quietly does nothing turns the sign into a
  smudge;
* **alpha is the halo's shape** - the emissive shaders read coverage from it,
  so RGB and alpha have to carry the same value or the viewport and the game
  disagree;
* **the .dds bytes are right** - Blender cannot write DDS, so this add-on
  writes the header itself, and the two things that go wrong there (BGRA
  order, top-down rows) both produce a file that opens fine and looks wrong.

Plus the rules this repo keeps everywhere: the source mesh is never touched,
the live rebuild never calls `bpy.ops`, and nothing arrived carrying its old
add-on's namespace.
"""
import os
import sys

import bpy

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  -- {detail}" if detail and not cond else ""))


import void_tools  # noqa: E402
if getattr(bpy.types, "SETO_PT_sign_glow_panel", None) is None:
    void_tools.register()

import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

from void_tools.shared import dds  # noqa: E402
from void_tools.sign_glow import geometry, object_settings  # noqa: E402

BYTE = 1.5 / 255.0          # BYTE_COLOR quantises; compare with a byte of slack

print("=== it lives in this add-on's namespace, not the one it arrived in ===")
check("the operator is seto.create_sign_glow",
      hasattr(bpy.ops.seto, "create_sign_glow")
      and getattr(bpy.types, "SETO_OT_create_sign_glow", None) is not None)
check("the panel is a SETO_PT_ panel, so the suite can see it",
      getattr(bpy.types, "SETO_PT_sign_glow_panel", None) is not None)
check("no MOLO_ class is registered any more",
      not [n for n in dir(bpy.types) if n.startswith("MOLO_")],
      [n for n in dir(bpy.types) if n.startswith("MOLO_")])
check("it sits in the tab, under Materials",
      bpy.types.SETO_PT_sign_glow_panel.bl_parent_id == "SETO_PT_materials_group")
check("its settings hang off the scene and the object under this prefix",
      hasattr(bpy.context.scene, "seto_sign_glow")
      and hasattr(bpy.types.Object, "seto_sign_glow_data"))

print("=== the maths, with no Blender in the way ===")
source = open(geometry.__file__, encoding="utf-8").read()
check("geometry.py stays pure - no bpy in it at all",
      "import bpy" not in source)

# One square letter, one metre across, on the XY plane at z = 0.
square = [
    [Vector((-0.5, -0.5, 0.0)), Vector((0.5, -0.5, 0.0)), Vector((0.5, 0.5, 0.0))],
    [Vector((-0.5, -0.5, 0.0)), Vector((0.5, 0.5, 0.0)), Vector((-0.5, 0.5, 0.0))],
]
u, v, forward = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
mask, bounds, nearest = geometry.rasterize(square, u, v, forward, 64, 0.25)
check("the silhouette is filled, not empty", mask.max() == 1.0)
check("and it is not the whole image - there is room for the halo",
      0.2 < mask.mean() < 0.8, mask.mean())
check("the plane's bounds are the letters plus the padding",
      abs((bounds[2] - bounds[0]) - 1.5) < 1e-6, bounds)
check("the frontmost point is measured, so the plane can go behind it",
      abs(nearest) < 1e-6, nearest)

wide = geometry.blur(mask, 8)
tight = geometry.blur(mask, 1)
check("a wider blur spreads further into the empty border",
      wide[0].sum() > tight[0].sum(), (wide[0].sum(), tight[0].sum()))
check("and blurring conserves roughly what was there",
      abs(wide.sum() - mask.sum()) / mask.sum() < 0.05,
      (mask.sum(), wide.sum()))

halo = geometry.halo_from_mask(mask, 0.015, 1.0, 0.08, 0.55, 1.0,
                               (1.0, 0.0, 0.0, 1.0))
check("the halo is RGBA at the mask's size", halo.shape == mask.shape + (4,),
      halo.shape)
check("alpha carries the same value as the colour does",
      np.allclose(halo[..., 0], halo[..., 3], atol=1e-6))
check("nothing overshoots 1.0 after two layers are added",
      halo.max() <= 1.0, halo.max())
check("the core reaches further than the letters do",
      halo[..., 3][mask == 0.0].max() > 0.0)

only_core = geometry.halo_from_mask(mask, 0.015, 1.0, 0.08, 0.0, 1.0,
                                    (1.0, 1.0, 1.0, 1.0))
check("dropping the wide layer really does narrow the glow",
      only_core[..., 3].sum() < halo[..., 3].sum(),
      (only_core[..., 3].sum(), halo[..., 3].sum()))

print("=== the .dds bytes, since Blender cannot write them ===")
# One column, two rows: bottom pixel red, top pixel blue. Small enough to read
# by hand, and it exercises both of the things that go wrong.
data = dds.encode(1, 2, [1.0, 0.0, 0.0, 1.0,
                         0.0, 0.0, 1.0, 0.5])
check("it starts with the magic and a 124-byte header",
      data[:4] == b'DDS ' and len(data) == 128 + 8, len(data))
check("the first row written is the image's TOP row - DDS is top-down",
      tuple(data[128:132]) == (255, 0, 0, 128), tuple(data[128:132]))
check("and the channel order is BGRA, not RGBA",
      tuple(data[132:136]) == (0, 0, 255, 255), tuple(data[132:136]))
try:
    dds.encode(4, 4, [0.0] * 8)
    check("a buffer of the wrong length is refused", False)
except ValueError:
    check("a buffer of the wrong length is refused", True)

print("=== a glow, built on a real sign ===")
scene = bpy.context.scene
view = bpy.context.view_layer

bpy.ops.mesh.primitive_plane_add(size=2)
letters = bpy.context.active_object
letters.name = "sign_letters"
before_verts = [tuple(vert.co) for vert in letters.data.vertices]
before_mesh = letters.data.name

bpy.ops.seto.create_sign_glow()
glow = bpy.context.active_object
data = glow.seto_sign_glow_data
check("the new object is the glow, and it knows it is one",
      glow is not letters and data.is_sign_glow)
check("it remembers what it was traced from", data.source_object is letters)
check("it is a bordered grid, not a bare quad - the border is what fades it out",
      len(glow.data.polygons) == 9, len(glow.data.polygons))
check("with a generated texture on it",
      bpy.data.images.get(glow.get(object_settings.IMAGE_NAME_KEY, "")) is not None)
check("and a material to see it through", len(glow.material_slots) == 1)

# The point of Create doing the shader itself: a sign that looks right in
# Blender and arrives in game as a grey quad is the failure this tool is for.
from void_tools.shared import sollumz_integration as szi  # noqa: E402

created_material = glow.data.materials[0]
if szi.is_sollumz_available():
    check("Create gives it the Sollumz emissive shader, not a stand-in",
          created_material.name.startswith(szi.SIGN_GLOW_MATERIAL_PREFIX),
          created_material.name)
    check("and the shader it names is an emissive one",
          "emissive" in getattr(created_material.shader_properties, "filename", ""),
          getattr(created_material.shader_properties, "filename", None))

    # Create must not put a file on anybody's drive. The material shows the
    # packed image perfectly well; writing the .dds is what Export is for.
    glow_image = bpy.data.images[glow[object_settings.IMAGE_NAME_KEY]]
    # Asked of the filepath, not of `source`: packing an image sets source to
    # 'FILE' whether or not a file exists, so source alone cannot tell a packed
    # halo from an exported one.
    check("Create writes nothing to disk - the texture is packed, not saved",
          not glow_image.filepath and glow_image.packed_file is not None,
          (glow_image.source, glow_image.filepath, glow_image.packed_file))

    bpy.ops.seto.sign_glow_export()
    written = bpy.path.abspath(glow_image.filepath)
    check("Export is what puts it on disk, as a real DDS",
          written.lower().endswith(".dds") and os.path.exists(written)
          and open(written, "rb").read(4) == b'DDS ', written)

    print("=== once exported, the file on disk follows the sliders ===")
    # Without this the .dds freezes at whatever the halo looked like when the
    # material was made, and the sign in game is a version nobody chose.
    stale = os.path.getmtime(written)
    before = open(written, "rb").read()
    data.halo_size = 0.25
    after = open(written, "rb").read()
    check("changing a setting rewrites the .dds", after != before)
    check("and it is still a valid DDS afterwards", after[:4] == b'DDS ')
    data.halo_size = 0.08
else:
    check("without Sollumz it falls back to the viewport material",
          created_material.name.endswith(object_settings.PREVIEW_MATERIAL_SUFFIX),
          created_material.name)

check("the source mesh is untouched - the rule this add-on keeps",
      letters.data.name == before_mesh
      and [tuple(vert.co) for vert in letters.data.vertices] == before_verts)
check("the glow lands behind the letters, not through them",
      glow.matrix_world.translation.z < letters.matrix_world.translation.z,
      glow.matrix_world.translation.z)
check("it joins the lettering's own collection",
      set(c.name for c in glow.users_collection)
      == set(c.name for c in letters.users_collection))

image = bpy.data.images[glow[object_settings.IMAGE_NAME_KEY]]
pixels = np.empty(len(image.pixels), dtype=np.float32)
image.pixels.foreach_get(pixels)
check("the texture is not blank - something was actually traced",
      pixels.max() > 0.1, pixels.max())

colour = glow.data.color_attributes.get("Color 1")
check("Color 1 is where GTA reads it",
      colour is not None and colour.data_type == 'BYTE_COLOR'
      and colour.domain == 'CORNER',
      None if colour is None else (colour.data_type, colour.domain))
check("and the plane is unwrapped", len(glow.data.uv_layers) == 1)

print("=== the plane fades out instead of ending on a line ===")
# Alpha in Color 1 is what the emissive shader blends by. A plane that is 1.0
# all the way to its border does not stop where its texture does - it stops at
# a rectangle edge, which in game is a faint lit box hanging around the sign.


def plane_alphas(obj):
    layer = obj.data.color_attributes["Color 1"]
    mesh = obj.data
    outer, inner = [], []
    xs = [vertex.co.x for vertex in mesh.vertices]
    ys = [vertex.co.y for vertex in mesh.vertices]
    for loop in mesh.loops:
        position = mesh.vertices[loop.vertex_index].co
        on_border = (abs(position.x - min(xs)) < 1e-6
                     or abs(position.x - max(xs)) < 1e-6
                     or abs(position.y - min(ys)) < 1e-6
                     or abs(position.y - max(ys)) < 1e-6)
        (outer if on_border else inner).append(layer.data[loop.index].color[3])
    return outer, inner


outer, inner = plane_alphas(glow)
check("every vertex on the outside edge comes in at alpha 0",
      outer and all(alpha < BYTE for alpha in outer), sorted(set(outer))[:4])
check("and the middle of the plane is fully on",
      inner and all(alpha > 1.0 - BYTE for alpha in inner),
      sorted(set(inner))[:4])
check("the fade is a band of its own, not the whole plane",
      len({round(vertex.co.x, 5) for vertex in glow.data.vertices}) == 4)

data.edge_fade = 0.2
wide_outer, _ = plane_alphas(glow)
check("widening the fade keeps the border at 0 - it moves the band inwards, "
      "it does not raise the edge",
      all(alpha < BYTE for alpha in wide_outer))
first_ring = sorted({round(vertex.co.x, 5) for vertex in glow.data.vertices})
data.edge_fade = 0.08
narrow_ring = sorted({round(vertex.co.x, 5) for vertex in glow.data.vertices})
check("and the band really did move", first_ring[1] > narrow_ring[1],
      (first_ring[:2], narrow_ring[:2]))

print("=== every setting is live, and rebuilds are its own business ===")
import ast  # noqa: E402
# Asked of the syntax tree rather than of the text: this module's own docstring
# explains that it does not call bpy.ops, and a substring search reads that
# sentence as a violation of itself.
module = ast.parse(open(object_settings.__file__, encoding="utf-8").read())
operator_calls = [node for node in ast.walk(module)
                  if isinstance(node, ast.Attribute)
                  and isinstance(node.value, ast.Attribute)
                  and node.value.attr == "ops"
                  and isinstance(node.value.value, ast.Name)
                  and node.value.value.id == "bpy"]
check("the live rebuild never reaches for bpy.ops - it runs from a property "
      "callback, where operators are not safe",
      not operator_calls, [node.attr for node in operator_calls])

def plane_width(obj):
    xs = [vert.co.x for vert in obj.data.vertices]
    return max(xs) - min(xs)

narrow = plane_width(glow)
data.halo_size = 0.3
check("a wider halo grows the plane that has to hold it",
      plane_width(glow) > narrow, (narrow, plane_width(glow)))

data.halo_size = 0.08
back = plane_width(glow)
check("and putting it back puts the plane back",
      abs(back - narrow) < 1e-5, (narrow, back))

first = [tuple(vert.co) for vert in glow.data.vertices]
bpy.ops.seto.sign_glow_rebuild()
check("the same settings rebuild the same plane",
      [tuple(vert.co) for vert in glow.data.vertices] == first)

data.live_update = False
pinned = plane_width(glow)
data.halo_size = 0.35
check("with Live Update off, a setting change rebuilds nothing",
      plane_width(glow) == pinned)
bpy.ops.seto.sign_glow_rebuild()
check("and the button still does it when asked",
      plane_width(glow) > pinned)
data.live_update = True
data.halo_size = 0.08

print("=== it says what went wrong, on the panel ===")
data.source_object = None
glow[object_settings.SOURCE_NAMES_KEY] = []
status = object_settings.rebuild(glow)
check("a glow with no source refuses and explains itself",
      bool(status) and "source" in status.lower(), status)
glow[object_settings.SOURCE_NAMES_KEY] = [letters.name]
data.source_object = letters
check("and pointing it back at the lettering clears the complaint",
      object_settings.rebuild(glow) is None)

print("=== it refuses politely ===")
for obj in view.objects:
    obj.select_set(False)
view.objects.active = None
check("with nothing selected there is nothing to trace",
      not bpy.ops.seto.create_sign_glow.poll())
view.objects.active = glow
glow.select_set(True)
check("and a glow is not lettering - it will not trace itself",
      not bpy.ops.seto.create_sign_glow.poll())

print()
failed = [r for r in RESULTS if not r[0]]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
if failed:
    for _ok, name, detail in failed:
        print(f"FAILED: {name}  -- {detail}")
    sys.exit(1)
