"""Every Seto Tools panel, drawn - including the state a new user starts in.

Blender only calls draw() from the UI thread, so a headless test never draws a
panel by running the add-on normally: all the logic can pass while the panel
explodes on first redraw. This drives every registered panel's draw() by hand
against a stub layout that validates what it is asked to do.

The stub has to validate three separate things, because each has shipped a bug
here before:

  1. an attribute the real UILayout does not have (`row.prop_enabled = True`)
  2. a keyword or enum value this Blender rejects - `template_list(type='GRID')`
     was valid in 4.x and removed in 5.x
  3. a property or operator name that does not exist

A stub that quietly swallows **kwargs sees none of those.

Both Sollumz states are covered. The unavailable one is not hypothetical: a
tester installed Sollumz from the GitHub repository, where the folder is called
"Sollumz-main", and every tool told them it was not installed.
"""
import bpy, sys, os

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

import seto_tools
from seto_tools.shared import sollumz_integration as szi
if getattr(bpy.types, "SETO_PT_fake_ao_panel", None) is None:
    seto_tools.register()


def _check_layout_call(fn_name, kwargs):
    fn = bpy.types.UILayout.bl_rna.functions.get(fn_name)
    if fn is None:
        check("UILayout has " + fn_name, False)
        return
    params = {p.identifier: p for p in fn.parameters}
    for key, value in kwargs.items():
        param = params.get(key)
        check(f"{fn_name}() accepts '{key}'", param is not None, sorted(params))
        if param is not None and param.type == 'ENUM':
            allowed = [i.identifier for i in param.enum_items]
            check(f"{fn_name}({key}={value!r}) is valid", value in allowed, allowed)


_UILAYOUT_PROPS = set(bpy.types.UILayout.bl_rna.properties.keys())


class StubLayout:
    def __setattr__(self, name, value):
        check(f"UILayout really has '{name}'", name in _UILAYOUT_PROPS,
              sorted(_UILAYOUT_PROPS))
        object.__setattr__(self, name, value)

    scale_y = scale_x = 1.0
    enabled = alert = False
    active = True

    def _sub(self, *a, **k): return self
    row = column = box = grid_flow = split = column_flow = _sub

    def label(self, **k): return None
    def separator(self, *a, **k): return None
    def menu(self, *a, **k): return None

    def template_icon(self, **k):
        _check_layout_call("template_icon", k)

    def template_list(self, listtype, list_id, data, prop, active_data,
                      active_prop, **k):
        check(f"template_list collection: {prop}", prop in data.bl_rna.properties)
        check(f"template_list index: {active_prop}",
              active_prop in active_data.bl_rna.properties)
        check(f"UIList registered: {listtype}",
              listtype == "" or hasattr(bpy.types, listtype))
        _check_layout_call("template_list", k)

    def template_icon_view(self, data, name, **k):
        check(f"icon_view prop: {type(data).__name__}.{name}",
              name in data.bl_rna.properties)
        _check_layout_call("template_icon_view", k)

    def template_ID(self, data, name, **k):
        check(f"template_ID target: {type(data).__name__}.{name}",
              name in data.bl_rna.properties)
        return self

    def operator(self, idname, **k):
        module, _, op = idname.partition(".")
        exists = hasattr(getattr(bpy.ops, module, object()), op)
        check("operator exists: " + idname, exists)
        rna = getattr(getattr(bpy.ops, module), op).get_rna_type() if exists else None
        keys = list(rna.properties.keys()) if rna else []
        return type("OpProps", (), {"__setattr__": lambda s, key, value: check(
            f"op prop {idname}.{key}", key in keys, keys)})()

    def prop(self, data, name, **k):
        check(f"prop exists: {type(data).__name__}.{name}",
              name in data.bl_rna.properties, list(data.bl_rna.properties.keys()))
        return self


def seto_panels():
    """Every panel this add-on registers, in tab order."""
    found = []
    for name in dir(bpy.types):
        if not name.startswith("SETO_PT_"):
            continue
        cls = getattr(bpy.types, name)
        if getattr(cls, "bl_category", None) == "Seto Tools":
            found.append(cls)
    return sorted(found, key=lambda c: (getattr(c, "bl_order", 0), c.__name__))


def draw_panel(cls, label):
    """Drive draw()/draw_header() without instantiating the Panel.

    A Panel subclass cannot be constructed (bpy_struct.__new__ refuses), so the
    methods are bound onto a plain object carrying a `layout`.
    """
    shim = type("Shim", (), {})()
    shim.layout = StubLayout()
    for attr in dir(cls):
        if attr.startswith("_draw") or attr in ("draw", "draw_header"):
            fn = getattr(cls, attr)
            if callable(fn):
                setattr(shim, attr, fn.__get__(shim))
    for entry in ("draw_header", "draw"):
        fn = getattr(shim, entry, None)
        if fn is None:
            continue
        try:
            fn(bpy.context)
            check(f"{cls.__name__}.{entry} [{label}]", True)
        except Exception as e:
            import traceback; traceback.print_exc()
            check(f"{cls.__name__}.{entry} [{label}]", False, e)


panels = seto_panels()
check("all five tools registered a top-level panel",
      len([c for c in panels if not getattr(c, "bl_parent_id", "")]) == 5,
      [c.__name__ for c in panels if not getattr(c, "bl_parent_id", "")])

print("=== every panel draws, with Sollumz available ===")
bpy.ops.mesh.primitive_cube_add(size=2)
for cls in panels:
    draw_panel(cls, "sollumz ok")

print("=== every panel draws when Sollumz is missing ===")
# The tester's state. Every tool must say so rather than drawing buttons that
# cannot work - Surface Painter used to draw its whole UI and only fail at
# Start Paint.
real_status = szi.get_status_message
szi.get_status_message = lambda: (False, "No enabled Sollumz add-on found.")
try:
    for cls in panels:
        draw_panel(cls, "no sollumz")

    from seto_tools.shared import ui_common
    for tool in ("fake_ao", "fake_damage", "smooth_edge", "decal_tool",
                 "surface_painter"):
        module = __import__(f"seto_tools.{tool}.ui", fromlist=["ui"])
        check(f"{tool} uses the shared warning, not its own copy",
              "ui_common" in dir(module) and not hasattr(module, "_wrap"))

    drawn = []

    class Sink(StubLayout):
        def label(self, text="", icon=''):
            drawn.append(text)

    check("the warning stops the panel", ui_common.draw_sollumz_warning(Sink()))
    check("and it names Sollumz", any("Sollumz" in line for line in drawn), drawn)
finally:
    szi.get_status_message = real_status

failed = [r for r in RESULTS if not r[0]]
print("\n" + "="*60)
print(f"RESULT: {len(RESULTS)-len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("="*60)
sys.exit(1 if failed else 0)
