"""The add-on's own panel icons, and the controls that must not be clickable.

Two failures this catches, both invisible to every other script here.

A custom icon that fails to load costs no error - `icon_value=0` draws nothing,
so the panel comes up with a blank square where its icon should be and every
logic test stays green.

And an enum whose sole entry is a placeholder still opens as a dropdown, which
reads as a control that does nothing. The panels are driven with the library
forced empty - the state every new install starts in - and the recording stub
reports which rows came out disabled.

**`preview.icon_id` is always 0 in background mode.** Blender allocates icon
slots from the UI, so a headless run cannot check the id the panel would draw.
What it can check is that the PNG loaded (the preview is in the collection at
the right size) and that the header asks `icons.get()` for its id rather than
naming a built-in icon - so `icons.get` is stubbed with a sentinel and the
header is watched for it.
"""
import bpy, sys, os

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

import seto_tools
from seto_tools.shared import icons
if getattr(bpy.types, "SETO_PT_fake_ao_panel", None) is None:
    seto_tools.register()

EXPECTED = {
    "geometry": "SETO_PT_geometry_group",
    "surface": "SETO_PT_surface_group",
    "fake_damage": "SETO_PT_fake_damage_panel",
    "smooth_edge": "SETO_PT_smooth_edge_panel",
    "fake_ao": "SETO_PT_fake_ao_panel",
    "decal_tool": "SETO_PT_decal_tool_panel",
    "surface_painter": "SETO_PT_surface_painter_panel",
}

# ------------------------------------------------------------- the PNG files
check("the icons folder ships with the add-on", os.path.isdir(icons.FOLDER),
      icons.FOLDER)

for name in sorted(EXPECTED):
    path = os.path.join(icons.FOLDER, name + ".png")
    check(f"{name}.png exists", os.path.isfile(path), path)
    if not os.path.isfile(path):
        continue
    # 32x32 is the size Blender draws an icon at; anything else is rescaled by
    # Blender's own filter, which is worse than the box filter these were made
    # with. 32-bit depth means the alpha channel survived.
    image = bpy.data.images.load(path)
    check(f"{name}.png is 32x32", tuple(image.size) == (32, 32), tuple(image.size))
    check(f"{name}.png keeps its alpha", image.depth == 32, image.depth)
    bpy.data.images.remove(image)

# ---------------------------------------------------------- they got loaded
check("register() built a preview collection", icons._collection is not None)
loaded = set(icons._collection.keys()) if icons._collection else set()
check("every icon is in the collection", loaded >= set(EXPECTED),
      sorted(loaded))
for name in sorted(EXPECTED & loaded if isinstance(EXPECTED, set) else
                   set(EXPECTED) & loaded):
    check(f"{name} decoded at 32x32",
          tuple(icons._collection[name].image_size) == (32, 32),
          tuple(icons._collection[name].image_size))

check("a missing icon is 0, not a traceback", icons.get("no_such_icon") == 0)

# --------------------------------------------- every header asks for its own
SENTINEL = 4242
drawn = []


class HeaderStub:
    def label(self, text="", icon='NONE', icon_value=0):
        drawn.append((icon, icon_value))


real_get = icons.get
try:
    for name, idname in sorted(EXPECTED.items()):
        icons.get = lambda asked, want=name: SENTINEL if asked == want else 0
        cls = getattr(bpy.types, idname, None)
        if cls is None:
            check(f"{idname} registered", False)
            continue
        drawn.clear()
        shim = type("Shim", (), {})()
        shim.layout = HeaderStub()
        cls.draw_header.__get__(shim)(bpy.context)
        check(f"{idname} draws the custom {name} icon",
              drawn and drawn[0][1] == SENTINEL, drawn)

    # And when the file is missing, a header falls back to a built-in name
    # rather than drawing nothing at all.
    icons.get = lambda asked: 0
    drawn.clear()
    shim = type("Shim", (), {})()
    shim.layout = HeaderStub()
    bpy.types.SETO_PT_geometry_group.draw_header.__get__(shim)(bpy.context)
    check("a missing icon falls back to a built-in one",
          drawn and drawn[0][0] not in ('NONE', '') and drawn[0][1] == 0, drawn)
finally:
    icons.get = real_get

# --------------------------------------------------- empty enums are disabled
_UILAYOUT_PROPS = set(bpy.types.UILayout.bl_rna.properties.keys())


class Recorder:
    """Records prop()/operator() calls and the `enabled` of the row they hit."""

    def __init__(self, log, enabled=True):
        object.__setattr__(self, "_log", log)
        object.__setattr__(self, "enabled", enabled)

    def __setattr__(self, name, value):
        check(f"UILayout really has '{name}'", name in _UILAYOUT_PROPS)
        object.__setattr__(self, name, value)

    scale_y = scale_x = 1.0
    alert = False
    active = True

    def _sub(self, *a, **k):
        return Recorder(self._log, self.enabled)
    row = column = box = grid_flow = split = column_flow = _sub

    def label(self, **k): return None
    def separator(self, *a, **k): return None
    def menu(self, *a, **k): return None
    def template_icon(self, **k): return None
    def template_list(self, *a, **k): return None
    def template_icon_view(self, *a, **k): return None
    def template_ID(self, *a, **k): return self

    def operator(self, idname, **k):
        self._log.append(("op", idname, self.enabled))
        return type("P", (), {"__setattr__": lambda s, k, v: None})()

    def prop(self, data, name, **k):
        self._log.append(("prop", name, self.enabled))
        return self


def draw(idname):
    """Run a panel's draw() and return [(kind, name, enabled), ...]."""
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


def state(log, name):
    for kind, item, enabled in log:
        if kind == "prop" and item == name:
            return enabled
    return None


def clickable(log, fragment):
    return any(kind == "op" and fragment in item and enabled
               for kind, item, enabled in log)


from seto_tools.decal_tool import library as decal_library
from seto_tools.surface_painter import library as surface_library

# The user's own library may well be configured in the Blender this runs in, so
# emptiness is forced rather than assumed.
for module in (decal_library, surface_library):
    module._real_categories = module.get_categories
    module._real_textures = module.get_textures
    module.get_categories = lambda: []
    module.get_textures = lambda category=None: []
try:
    decal = draw("SETO_PT_decal_tool_panel")
    check("Decal Tool: the category enum is disabled",
          state(decal, "category") is False, decal)
    check("Decal Tool: the texture enum is disabled",
          state(decal, "texture") is False, decal)
    check("Decal Tool: Refresh Library stays clickable",
          clickable(decal, "refresh"), decal)

    surface = draw("SETO_PT_surface_painter_panel")
    check("Surface Painter: the category enum is disabled",
          state(surface, "category") is False, surface)
    check("Surface Painter: Refresh stays clickable",
          clickable(surface, "refresh"), surface)
finally:
    for module in (decal_library, surface_library):
        module.get_categories = module._real_categories
        module.get_textures = module._real_textures

# With a library behind them they must be usable again, or this fix has simply
# broken both tools.
decal_library.get_categories = lambda: ["walls"]
decal_library.get_textures = lambda category=None: [("grime", "grime.png")]
try:
    decal = draw("SETO_PT_decal_tool_panel")
    check("Decal Tool: the category enum is live once there is a category",
          state(decal, "category") is True, decal)
    check("Decal Tool: the texture enum is live once there is a texture",
          state(decal, "texture") is True, decal)
finally:
    decal_library.get_categories = decal_library._real_categories
    decal_library.get_textures = decal_library._real_textures

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(RESULTS)-len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed:
    print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
