"""The strip shape the Geometry section owns for both tools.

A tester's report, made into a test: the same seven rows were drawn under Edge
Wear and again under Smooth Edge. They now belong to the section, so the checks
here are that no setting is offered twice down the tab, and - the part that
actually breaks if the wiring is wrong - that a value typed into the section
still reaches both tools' operators and lands on the strip they build.

The per-object settings deliberately stay per object: two strips built minutes
apart with different widths must each keep their own.
"""
import bpy, sys

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    return bool(cond)

import void_tools
from void_tools.shared import strip_settings
if getattr(bpy.types, "SETO_PT_fake_damage_panel", None) is None:
    void_tools.register()

scene = bpy.context.scene

# ------------------------------------------------------------ nothing twice
_UILAYOUT_PROPS = set(bpy.types.UILayout.bl_rna.properties.keys())


class Recorder:
    def __init__(self, log):
        object.__setattr__(self, "_log", log)

    def __setattr__(self, name, value):
        check(f"UILayout really has '{name}'", name in _UILAYOUT_PROPS)
        object.__setattr__(self, name, value)

    scale_y = scale_x = 1.0
    enabled = active = True
    alert = False

    def _sub(self, *a, **k): return Recorder(self._log)
    row = column = box = grid_flow = split = column_flow = _sub

    def label(self, **k): return None
    def separator(self, *a, **k): return None
    def menu(self, *a, **k): return None
    def template_icon(self, **k): return None
    def template_list(self, *a, **k): return None
    def template_icon_view(self, *a, **k): return None
    def template_ID(self, *a, **k): return self

    def operator(self, idname, **k):
        return type("P", (), {"__setattr__": lambda s, k, v: None})()

    def prop(self, data, name, **k):
        self._log.append((type(data).__name__, name))
        return self


def drawn(idname):
    log = []
    cls = getattr(bpy.types, idname)
    shim = type("Shim", (), {})()
    shim.layout = Recorder(log)
    for attr in dir(cls):
        if attr.startswith("_draw") or attr == "draw":
            fn = getattr(cls, attr)
            if callable(fn):
                setattr(shim, attr, fn.__get__(shim))
    shim.draw(bpy.context)
    return log


section = [name for _, name in drawn("SETO_PT_geometry_group")]
wear = [name for _, name in drawn("SETO_PT_fake_damage_panel")]
smooth = [name for _, name in drawn("SETO_PT_smooth_edge_panel")]

# Nothing that a finished strip can change is offered before there is one. The
# settings were listed twice - here and on the strip - and only the copy on the
# strip did anything, so dragging the one at the top of the tab looked broken.
# What is left is the material, which decides what the strip is built with.
check("the Geometry section offers only the material choice",
      section == ["material_mode"], section)
check("Edge Wear adds nothing to it", wear == [], wear)
check("Smooth Edge adds nothing to it", smooth == [], smooth)

ao_rows = [name for _, name in drawn("SETO_PT_fake_ao_panel")]
check("Ambient Occlusion's create panel is down to what it needs",
      not ({"width", "surface_offset", "alpha_center", "alpha_outer",
            "alpha_bottom", "alpha_top", "invert_fade", "flip_direction"}
           & set(ao_rows)), ao_rows)
check("but it still asks where the strip runs",
      "source_mode" in ao_rows, ao_rows)

# ------------------------------------------------- and it reaches both tools
WIDTH = 0.07
OFFSET = 0.0007
scene.seto_edge_strip.width = WIDTH
scene.seto_edge_strip.surface_offset = OFFSET
scene.seto_fake_damage.uv_scale = 2.25


def build(operator):
    """One strip along one edge of a fresh cube. Returns the created object."""
    bpy.ops.mesh.primitive_cube_add(size=2)
    cube = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    cube.data.edges[0].select = True
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        result = operator()
    except RuntimeError as error:
        # bpy.ops raises where the UI would show a red status line.
        print("  (operator reported:", error, ")")
        result = {'CANCELLED'}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    if result != {'FINISHED'}:
        return None
    return bpy.context.active_object


wear_obj = build(bpy.ops.seto.create_fake_damage)
if check("Edge Wear built a strip", wear_obj is not None):
    data = wear_obj.seto_fake_damage_data
    check("Edge Wear took Width from the section",
          abs(data.width - WIDTH) < 1e-6, data.width)
    check("Edge Wear took Surface Offset from the section",
          abs(data.surface_offset - OFFSET) < 1e-6, data.surface_offset)
    check("Edge Wear still took UV Scale from its own panel",
          abs(data.uv_scale - 2.25) < 1e-6, data.uv_scale)

smooth_obj = build(bpy.ops.seto.create_smooth_edge)
if check("Smooth Edge built a strip", smooth_obj is not None):
    data = smooth_obj.seto_smooth_edge_data
    check("Smooth Edge took the same Width from the same place",
          abs(data.width - WIDTH) < 1e-6, data.width)
    check("Smooth Edge took the same Surface Offset",
          abs(data.surface_offset - OFFSET) < 1e-6, data.surface_offset)

# A finished strip keeps its own values: changing the section afterwards must
# not reach back into it.
if wear_obj is not None:
    scene.seto_edge_strip.width = 0.2
    check("a finished strip is not retro-fitted",
          abs(wear_obj.seto_fake_damage_data.width - WIDTH) < 1e-6,
          wear_obj.seto_fake_damage_data.width)

# The last run is pushed back onto the section, so the next strip starts from
# what was actually used rather than silently reverting.
scene.seto_edge_strip.width = 0.2
again = build(lambda: bpy.ops.seto.create_smooth_edge(width=0.09))
if check("a strip built with an explicit width", again is not None):
    check("the section shows what the last run used",
          abs(scene.seto_edge_strip.width - 0.09) < 1e-6,
          scene.seto_edge_strip.width)

# ------------------------------------------------- the fade along the run
# Alpha Bottom/Top were Ambient Occlusion's only; both Geometry tools have them
# now, through the section. What has to hold is that the fade runs along the
# strip in WORLD up - the strip is built in the source's local space - and that
# 1.0 at both ends changes nothing at all.
def alphas_by_height(strip):
    """[(world z, Color 1 alpha), ...] for every loop of the strip."""
    layer = strip.data.color_attributes.get("Color 1")
    if layer is None:
        return []
    out = []
    for loop_index, loop in enumerate(strip.data.loops):
        vert = strip.data.vertices[loop.vertex_index]
        out.append(((strip.matrix_world @ vert.co).z,
                    layer.data[loop_index].color[3]))
    return out


def vertical_edge_strip(**overrides):
    """A strip along one vertical edge of a cube, so the run has real height."""
    bpy.ops.mesh.primitive_cube_add(size=2)
    cube = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    for edge in cube.data.edges:
        a, b = [cube.data.vertices[i].co for i in edge.vertices]
        if abs(a.x - b.x) < 1e-6 and abs(a.y - b.y) < 1e-6 and abs(a.z - b.z) > 1:
            edge.select = True
            break
    for name, value in overrides.items():
        setattr(scene.seto_edge_strip, name, value)
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        result = bpy.ops.seto.create_fake_damage()
    except RuntimeError as error:
        print("  (operator reported:", error, ")")
        result = {'CANCELLED'}
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    return bpy.context.active_object if result == {'FINISHED'} else None


scene.seto_edge_strip.width = 0.04
plain = vertical_edge_strip(alpha_bottom=1.0, alpha_top=1.0)
faded = vertical_edge_strip(alpha_bottom=0.0, alpha_top=1.0)

if check("both strips were built", plain is not None and faded is not None):
    before = alphas_by_height(plain)
    after = alphas_by_height(faded)
    # With both ends at 1.0 nothing along the run may have touched the alphas:
    # every one is still whichever end of the across-fade it came from. Color 1
    # is BYTE_COLOR, so compare with a byte of slack.
    ends = (scene.seto_edge_strip.alpha_center, scene.seto_edge_strip.alpha_outer)
    check("1.0 at both ends is a no-op",
          all(min(abs(a - end) for end in ends) < 1.0 / 255.0
              for _, a in before),
          sorted({round(a, 3) for _, a in before}))

    lowest = min(z for z, _ in after)
    highest = max(z for z, _ in after)
    bottom = [a for z, a in after if abs(z - lowest) < 1e-4]
    top = [a for z, a in after if abs(z - highest) < 1e-4]
    check("Alpha Bottom 0 kills the alpha at the foot of the run",
          bottom and max(bottom) < 0.01, bottom[:4])
    check("and leaves the top of the run alone",
          top and max(top) > 0.9, top[:4])
    check("the top is what it was before the fade",
          abs(max(top) - max(a for _, a in before)) < 0.01,
          f"{max(top)} vs {max(a for _, a in before)}")

    scene.seto_edge_strip.property_unset("alpha_bottom")
    scene.seto_edge_strip.property_unset("alpha_top")

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(RESULTS)-len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed:
    print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
