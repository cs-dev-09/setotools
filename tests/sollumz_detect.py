"""Finding Sollumz, whatever it is called and wherever it lives.

Every one of these cases is a real report. A tester who installed Sollumz from
GitHub - where the archive is named after the branch - was told it was not
installed by four tools at once. A tester on **Sollumz Development** was told
the same. The lesson both times was that the module name is not something to
predict: `resolve()` tries every enabled add-on and lets an import decide,
using the name only to choose what to try first.

`resolve()` is pure for exactly this reason - the registry and the importer are
arguments, so a fork nobody here has installed can still be tested.
"""
import bpy, sys

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

import void_tools
from void_tools.shared import sollumz_integration as szi
if getattr(bpy.types, "SETO_PT_fake_ao_panel", None) is None:
    void_tools.register()


def only(*real):
    """An importer that recognises exactly the named modules as Sollumz."""
    return lambda name: name in real


# --------------------------------------------------- the shapes seen so far
CASES = [
    ("a legacy add-on folder", ["io_scene_x", "Sollumz"], "Sollumz"),
    ("an extension", ["bl_ext.user_default.sollumz", "node_wrangler"],
     "bl_ext.user_default.sollumz"),
    ("a GitHub branch archive", ["Sollumz-main"], "Sollumz-main"),
    ("a version-numbered archive", ["Sollumz-2.9.0"], "Sollumz-2.9.0"),
    ("a development build", ["Sollumz-Development"], "Sollumz-Development"),
    ("an extension from another repo", ["bl_ext.sollumz_repo.sollumz"],
     "bl_ext.sollumz_repo.sollumz"),
]
for label, names, expected in CASES:
    found, verified = szi.resolve(names, only(expected))
    check(f"finds Sollumz as {label}", found == expected and verified,
          f"{found!r} verified={verified}")

# The point of the rewrite: a name nobody would have guessed still gets found,
# because every enabled add-on is tried rather than only the ones spelled
# "sollumz*".
found, verified = szi.resolve(["my_gta_tools", "node_wrangler"],
                              only("my_gta_tools"))
check("finds a build whose name says nothing about Sollumz",
      found == "my_gta_tools" and verified, f"{found!r}")

# ...and something merely named like it is still rejected on the evidence.
found, verified = szi.resolve(["sollumz_extras"], only("nothing"))
check("an unrelated 'sollumz_extras' does not verify", not verified, found)
check("but it is still named back, so the panel can say what it found",
      found == "sollumz_extras", found)

check("nothing at all returns None",
      szi.resolve(["node_wrangler"], only("nothing")) == (None, False))

# Order matters when more than one could answer: the real thing should win
# over a fork, and a fork over an unrelated add-on.
found, _ = szi.resolve(["zz_addon", "Sollumz-Development", "Sollumz"],
                       only("Sollumz", "Sollumz-Development"))
check("an exact 'Sollumz' wins over a fork", found == "Sollumz", found)

found, _ = szi.resolve(["aaa_addon", "Sollumz-Development"],
                       only("aaa_addon", "Sollumz-Development"))
check("a sollumz-shaped name is tried before an unrelated one",
      found == "Sollumz-Development", found)

# ------------------------------------------------------------- the override
check("an override is used verbatim",
      szi.resolve(["Sollumz"], only("Sollumz", "Whatever"), "Whatever")
      == ("Whatever", True))
check("an override that is wrong is reported, not silently ignored",
      szi.resolve(["Sollumz"], only("Sollumz"), "Whatever")
      == ("Whatever", False))

# ------------------------------------------------------- the live add-on
# This Blender has Sollumz installed, so the real thing must resolve, verify,
# and be reported as available.
base, verified = szi._resolve_cached()
check("the installed Sollumz resolves", base is not None, base)
check("and it verifies", verified, base)
available, message = szi.get_status_message()
check("get_status_message agrees", available, message)
check("and names what it found", base in message, message)

# The cache must not outlive a change of mind about the override.
szi.forget_sollumz()
check("forget_sollumz clears the cache", szi._resolved["key"] is None)
check("and the next call resolves again", szi._resolve_cached()[0] == base)

# ------------------------------------------------ dependencies are advisory
# A fork without Sollumz's `dependencies` module used to be reported as
# unavailable. Only a module that exists AND says no counts against it.
import importlib
real_import = importlib.import_module


def missing_dependencies(name, *args, **kwargs):
    if name.endswith(".dependencies"):
        raise ModuleNotFoundError(name)
    return real_import(name, *args, **kwargs)


importlib.import_module = missing_dependencies
try:
    available, message = szi.get_status_message()
    check("a build with no dependencies module is still usable",
          available, message)
finally:
    importlib.import_module = real_import

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(RESULTS)-len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed:
    print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
