"""The updater: right about versions, and online only when asked.

The second half is the point. The add-on's promise is not "never online"
but "never online without being asked", and a promise like that is worth
a test more than a comment: this suite walks every source file in the
package and asserts that the update operators are the only code that can
reach the network, and that nothing in the updater runs by itself - no
timers, no handlers, no check on register.

The network paths themselves are deliberately not driven here. A test
that needs the internet is a test that fails on a train, and everything
around the request - version maths, asset choice, URL pinning, the
refusals - is testable without it.
"""
import bpy, sys, os

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

import seto_tools
if getattr(bpy.types, "SETO_PT_support_panel", None) is None:
    seto_tools.register()

from seto_tools.updater import logic

print("=== the version maths ===")
check("the current version is bl_info's",
      logic.current() == tuple(seto_tools.bl_info["version"]),
      (logic.current(), seto_tools.bl_info["version"]))
check("a v-prefixed tag parses", logic.parse_tag("v1.2.3") == (1, 2, 3))
check("a bare tag parses", logic.parse_tag("1.2.3") == (1, 2, 3))
check("a short tag pads to three", logic.parse_tag("v2.1") == (2, 1, 0))
check("garbage parses to None, and None is never newer",
      logic.parse_tag("latest") is None and not logic.is_newer("latest"))
newer = ".".join(str(n) for n in (logic.current()[0] + 1, 0, 0))
check("a bigger version is newer", logic.is_newer(f"v{newer}"))
check("the current version is not newer than itself",
      not logic.is_newer(f"v{logic.current_str()}"))

print("=== choosing the asset ===")
release = {
    "tag_name": "v9.9.9",
    "assets": [
        {"name": "Source code (zip)", "browser_download_url": "https://x/src.zip"},
        {"name": "seto_tools.zip",
         "browser_download_url": logic.DOWNLOAD_PREFIX + "v9.9.9/seto_tools.zip",
         "size": 12345},
    ],
}
picked = logic.pick(release)
check("the installable zip is picked, not the source archive",
      picked is not None and picked[1].endswith("v9.9.9/seto_tools.zip"),
      picked)
check("a release with no installable zip picks nothing",
      logic.pick({"tag_name": "v9.9.9", "assets": [
          {"name": "readme.txt", "browser_download_url": "https://x/r"}]})
      is None)

print("=== the operators exist and refuse the right things ===")
state = bpy.context.window_manager.seto_updater
for name in ("SETO_OT_update_check", "SETO_OT_update_install"):
    check(f"{name} is registered", hasattr(bpy.types, name))

state.download_url = ""
try:
    bpy.ops.seto.update_install()
    check("installing before checking is refused", False, "operator ran")
except RuntimeError as error:
    check("installing before checking is refused",
          "Check for updates" in str(error), error)

state.download_url = "https://evil.example/seto_tools.zip"
state.latest = "v9.9.9"
try:
    bpy.ops.seto.update_install()
    check("a download from anywhere but our releases is refused",
          False, "operator ran")
except RuntimeError as error:
    check("a download from anywhere but our releases is refused",
          "own releases" in str(error), error)
state.download_url = ""
state.latest = ""

print("=== online only when asked, and only from one file ===")
package_root = os.path.join(r"D:\SetoClaude\setotools", "seto_tools")
network_words = ("urlopen", "urlretrieve", "http.client", "socket.")
offenders = []
# Timers and handlers are legitimate elsewhere (source_bevel's cleanup
# watches the depsgraph, and that is mesh housekeeping) - what must never
# exist is the *network-capable* package running itself. So the no-auto
# rule is scoped to updater/, where it means "no check without a press".
auto_words = ("bpy.app.timers", "load_post", "@persistent")
auto_offenders = []
for folder, _dirs, files in os.walk(package_root):
    for filename in files:
        if not filename.endswith(".py"):
            continue
        path = os.path.join(folder, filename)
        rel = os.path.relpath(path, package_root).replace("\\", "/")
        text = open(path, encoding="utf-8").read()
        if any(word in text for word in network_words):
            offenders.append(rel)
        if rel.startswith("updater/") and any(word in text
                                              for word in auto_words):
            auto_offenders.append(rel)
check("the update operators are the only code that can reach the network",
      offenders == ["updater/operators.py"], offenders)
check("nothing in the updater runs on a timer or a load handler",
      auto_offenders == [], auto_offenders)
check("and the download pin is our repository's releases, exactly",
      logic.DOWNLOAD_PREFIX ==
      "https://github.com/seto3d/setotools/releases/download/")

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
