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

import seto_tools
from seto_tools.shared import strip_settings
if getattr(bpy.types, "SETO_PT_fake_damage_panel", None) is None:
    seto_tools.register()

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

# color_rgb has never had a row: only the alpha of Color 1 is read by these
# shaders, so the RGB is a constant the operator and the F9 panel can still
# reach but the tab does not clutter itself with.
EXPECTED_ROWS = set(strip_settings.SHARED_NAMES) - {"color_rgb"}
check("the Geometry section draws the shared block",
      set(section) == EXPECTED_ROWS,
      sorted(EXPECTED_ROWS ^ set(section)))
check("Edge Wear repeats none of it", not (set(wear) & set(section)),
      sorted(set(wear) & set(section)))
check("Smooth Edge repeats none of it", not (set(smooth) & set(section)),
      sorted(set(smooth) & set(section)))
check("Edge Wear still draws its own UV settings",
      set(wear) == {"uv_scale", "uv_offset"}, wear)
check("Smooth Edge has nothing left of its own", smooth == [], smooth)
check("Ambient Occlusion keeps its own copy",
      "width" in [name for _, name in drawn("SETO_PT_fake_ao_panel")])

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

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(RESULTS)-len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed:
    print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
