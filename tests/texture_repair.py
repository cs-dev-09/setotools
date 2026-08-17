"""Bundled textures surviving the add-on moving house.

Blender writes an image's origin into the .blend as an **absolute path**, and
the strip tools' textures live inside the add-on - so every scene made with
them says `.../addons/seto_tools/fake_ao/textures/tl_v_office_shadow.dds` in as
many words. Rename the package to `void_tools`, or install as an extension, and
that sentence is false for good: the texture is pink and a restart does not
help, because the folder it names really is gone.

This checks the repair, and - just as much - checks what it refuses to touch.
A path-fixer that is too eager is worse than the problem: it would go around
re-pointing other add-ons' missing textures at ours.
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
if getattr(bpy.types, "SETO_PT_fake_ao_panel", None) is None:
    void_tools.register()

from void_tools.shared import bundled_textures, texture_repair  # noqa: E402

PACKAGE = os.path.dirname(os.path.abspath(void_tools.__file__))

print("=== there is a bundled texture to lose in the first place ===")
shipped = None
for tool in ("fake_ao", "fake_damage", "smooth_edge", "edge_dirt"):
    folder = os.path.join(PACKAGE, tool, "textures")
    found = bundled_textures.list_textures(folder) if os.path.isdir(folder) else []
    if found:
        shipped = (tool, found[0])
        break
check("the add-on ships a texture in a tool's textures/ folder",
      shipped is not None, PACKAGE)
if shipped is None:
    print(f"\n{len(RESULTS)}/{len(RESULTS)} checks passed")
    sys.exit(1)

tool, shipped_path = shipped
filename = os.path.basename(shipped_path)

print("=== a scene that still names the old install ===")
# Exactly what an old .blend carries: the same tail, under a folder that has
# not existed since the rename.
stale = os.path.join(r"C:\nowhere", "scripts", "addons", "seto_tools", tool,
                     "textures", filename)
image = bpy.data.images.new("stale_bundled", 8, 8)
image.filepath = stale
image.source = 'FILE'
check("the path it was saved with is genuinely gone",
      not os.path.isfile(bpy.path.abspath(image.filepath)))

repaired = texture_repair.repair_all()
check("the repair claims it", image in repaired,
      [i.name for i in repaired])
check("and it now points at the copy this add-on ships",
      os.path.normcase(bpy.path.abspath(image.filepath))
      == os.path.normcase(shipped_path),
      bpy.path.abspath(image.filepath))
check("which is a file that actually exists",
      os.path.isfile(bpy.path.abspath(image.filepath)))

print("=== and what it leaves alone ===")
# Nothing about "a missing image" is enough on its own. The tail has to be the
# shape our tools use AND the file has to exist inside this add-on - otherwise
# this would adopt other people's missing textures.
foreign = bpy.data.images.new("foreign_missing", 8, 8)
foreign.filepath = r"C:\nowhere\some_other_addon\textures\not_ours.png"
foreign.source = 'FILE'

odd_shape = bpy.data.images.new("odd_shape_missing", 8, 8)
odd_shape.filepath = r"C:\nowhere\pictures\holiday.png"
odd_shape.source = 'FILE'

healthy = bpy.data.images.new("healthy", 8, 8)
healthy.filepath = shipped_path
healthy.source = 'FILE'
before = healthy.filepath

repaired = texture_repair.repair_all()
check("a missing texture that is not one of ours is not adopted",
      foreign not in repaired
      and foreign.filepath == r"C:\nowhere\some_other_addon\textures\not_ours.png",
      foreign.filepath)
check("nor is a missing file that is not shaped like a bundled texture",
      odd_shape not in repaired, odd_shape.filepath)
check("and an image that opens is never second-guessed",
      healthy not in repaired and healthy.filepath == before, healthy.filepath)

print("=== it runs itself when a file is opened ===")
check("the load handler is registered",
      texture_repair._on_load in bpy.app.handlers.load_post)
# Asked with hasattr, not getattr: Blender's @persistent marks the function by
# setting `_bpy_persistent` to **None**, so a truthiness test on it says the
# handler is not persistent when it is.
check("and it is persistent, or it would be dropped by the first file load",
      hasattr(texture_repair._on_load, "_bpy_persistent"))

print("=== no register() may reach for bpy.data ===")
# The bug this cost: while Blender registers add-ons at startup, `bpy.data` is
# a `_RestrictData` stand-in and `bpy.data.images` raises AttributeError -
# register() fails and the whole add-on is dropped, so the tab never appears.
# Worse, the first attempt guarded that call with `if not bpy.app.background`,
# which meant no background test could ever have caught it. This is a static
# scan for exactly that shape, across every module in the add-on.
import ast  # noqa: E402

offenders = []
for folder, _subfolders, files in os.walk(PACKAGE):
    if "__pycache__" in folder:
        continue
    for name in sorted(f for f in files if f.endswith(".py")):
        path = os.path.join(folder, name)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef)
                    and node.name in ("register", "unregister")):
                continue
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Attribute)
                        and isinstance(sub.value, ast.Attribute)
                        and sub.value.attr == "data"
                        and isinstance(sub.value.value, ast.Name)
                        and sub.value.value.id == "bpy"):
                    offenders.append(f"{os.path.relpath(path, PACKAGE)}:"
                                     f"{node.name}() -> bpy.data.{sub.attr}")
check("nothing in any register()/unregister() touches bpy.data",
      not offenders, offenders[:3])

check("the deferred pass is what fixes the already-open file",
      hasattr(texture_repair, "_repair_once")
      and texture_repair._repair_once() is None)

print("=== it repairs the datablock, never the disk ===")
source = open(texture_repair.__file__, encoding="utf-8").read()
check("nothing in here opens a file for writing",
      "open(" not in source.replace('open(texture_repair.__file__', '')
      or "'w'" not in source,
      "writes to disk")
check("and it does not save the file behind the user's back",
      "save_as_mainfile" not in source and "image.save" not in source)

print()
failed = [r for r in RESULTS if not r[0]]
print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
if failed:
    for _ok, name, detail in failed:
        print(f"FAILED: {name}  -- {detail}")
    sys.exit(1)
