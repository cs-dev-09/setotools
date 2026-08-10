"""Every "Selected X" panel, drawn with one of its objects actually selected.

The gap this closes cost a released build: `tests/panels.py` drives every
registered panel, but a Selected panel's poll() is False unless one of the
tool's own objects is active - so its draw() was never reached, and a NameError
in it shipped. These panels are the ones with the most in them, and the only
ones a user is looking at while dragging a value.

Each tool builds a real strip first, then its panel is drawn by hand against a
stub layout.
"""
import bpy, sys, traceback
sys.path.append(r"D:\SetoClaude\setotools")
import seto_tools
if getattr(bpy.types, "SETO_PT_fake_damage_panel", None) is None:
    seto_tools.register()

class Stub:
    scale_y = scale_x = 1.0
    enabled = active = True
    alert = False
    def _sub(self, *a, **k): return self
    row = column = box = grid_flow = split = column_flow = _sub
    def label(self, **k): return None
    def separator(self, *a, **k): return None
    def prop(self, *a, **k): return self
    def operator(self, *a, **k):
        return type("P", (), {"__setattr__": lambda s,k,v: None})()

RESULTS = []


def build(op):
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
    bpy.ops.mesh.primitive_cube_add(size=2)
    c = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_mode(type='EDGE')
    bpy.ops.mesh.select_all(action='DESELECT'); bpy.ops.object.mode_set(mode='OBJECT')
    c.data.edges[0].select = True
    bpy.ops.object.mode_set(mode='EDIT'); op(); bpy.ops.object.mode_set(mode='OBJECT')

for label, op, panel in (
    ("Edge Wear", bpy.ops.seto.create_fake_damage, "SETO_PT_fake_damage_object_panel"),
    ("Smooth Edge", bpy.ops.seto.create_smooth_edge, "SETO_PT_smooth_edge_object_panel"),
    ("Ambient Occlusion", bpy.ops.seto.create_fake_ao, "SETO_PT_fake_ao_object_panel"),
    ("Edge Dirt", bpy.ops.seto.create_edge_dirt, "SETO_PT_edge_dirt_object_panel"),
):
    build(op)
    cls = getattr(bpy.types, panel)
    shim = type("S", (), {})(); shim.layout = Stub()
    for a in dir(cls):
        if a.startswith("_draw") or a == "draw":
            f = getattr(cls, a)
            if callable(f): setattr(shim, a, f.__get__(shim))
    try:
        shim.draw(bpy.context)
        RESULTS.append((True, label))
        print(f"[PASS] {label} Selected panel draws")
    except Exception as e:
        traceback.print_exc()
        RESULTS.append((False, f"{label}: {type(e).__name__}: {e}"))
        print(f"[FAIL] {label} Selected panel draws -- {e}")

failed = [r for r in RESULTS if not r[0]]
print("=" * 60)
print(f"RESULT: {len(RESULTS)-len(failed)}/{len(RESULTS)} checks passed")
for _, detail in failed:
    print("  FAIL", detail)
print("=" * 60)
sys.exit(1 if failed else 0)
