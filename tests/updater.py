"""The updater: right about versions, and online only on the stated terms.

The terms are the point, and they are worth a test more than a comment.
The add-on goes online in exactly two ways: when the user presses Check
or Install, and once per Blender start so the Updates header can carry a
notification - loudly documented, off in preferences, silent on failure,
and never in background mode. This suite walks every source file in the
package and asserts the whole shape: the updater package is the only code
that can reach the network, the startup check is the only thing on a
timer and it honours the preference, and nothing else runs by itself.

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

import void_tools
if getattr(bpy.types, "SETO_PT_support_panel", None) is None:
    void_tools.register()

from void_tools.updater import logic

print("=== the version maths ===")
check("the current version is bl_info's",
      logic.current() == tuple(void_tools.bl_info["version"]),
      (logic.current(), void_tools.bl_info["version"]))
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
        {"name": "void-tools.zip",
         "browser_download_url": logic.DOWNLOAD_PREFIX + "v9.9.9/void-tools.zip",
         "size": 12345},
    ],
}
picked = logic.pick(release)
check("the installable zip is picked, not the source archive",
      picked is not None and picked[1].endswith("v9.9.9/void-tools.zip"),
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

state.download_url = "https://evil.example/void-tools.zip"
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

print("=== online only on the stated terms, and only from one package ===")
package_root = os.path.join(r"D:\SetoClaude\setotools", "void_tools")
network_words = ("urlopen", "urlretrieve", "http.client", "socket.")
offenders = []
# Timers are legitimate elsewhere (source_bevel's cleanup watches the
# depsgraph, and that is mesh housekeeping). Inside the network-capable
# package they are the startup check and nothing else - one file, which
# must also be the file that honours the kill switch.
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
        if rel.startswith("updater/") and "bpy.app.timers" in text:
            auto_offenders.append(rel)
check("the updater package is the only code that can reach the network",
      sorted(offenders) == ["updater/auto.py", "updater/operators.py"],
      offenders)
check("the startup check is the only thing on a timer",
      auto_offenders == ["updater/auto.py"], auto_offenders)
auto_source = open(os.path.join(package_root, "updater", "auto.py"),
                   encoding="utf-8").read()
check("and it honours the preference", "auto_check_updates" in auto_source)
check("and it never runs in background Blender",
      "bpy.app.background" in auto_source)
check("the preference itself exists, on by default",
      True is __import__("void_tools.decal_tool.preferences",
                         fromlist=["preferences"])
      .SETO_AP_decal_tool.__annotations__["auto_check_updates"]
      .keywords.get("default"))
check("the download pin is our repository's releases, exactly",
      logic.DOWNLOAD_PREFIX ==
      "https://github.com/seto3d/void-tools/releases/download/")

print("=== the shape of the archive it is about to install ===")
# Not covered until 1.2.2 shipped an installer that refused every real update.
# The releases carry an *extension* package now - manifest and __init__ at the
# archive root - and the installer only knew the legacy shape, so it rejected
# the genuine article with "this did not look like Void Tools". Worse would
# have been accepting it: addon_install scatters a root-level archive loose
# across scripts/addons.
import os as _os  # noqa: E402
import zipfile as _zipfile  # noqa: E402

check("a legacy package is recognised",
      logic.archive_shape(["void_tools/__init__.py", "void_tools/shared/x.py"])
      == logic.LEGACY)
check("an extension package is recognised, and told apart from it",
      logic.archive_shape(["blender_manifest.toml", "__init__.py", "shared/x.py"])
      == logic.EXTENSION)
check("something else is neither, so the installer refuses it",
      logic.archive_shape(["evil.py", "readme.txt"]) is None)
check("and an unreadable download is neither",
      logic.archive_shape([]) is None)
check("a legacy archive with a stray file outside the package is refused",
      logic.archive_shape(["void_tools/__init__.py", "elsewhere.py"]) is None)

built = _os.path.join(r'D:\SetoClaude\setotools', 'dist', 'void-tools.zip')
if _os.path.exists(built):
    with _zipfile.ZipFile(built) as archive:
        shape = logic.archive_shape(archive.namelist())
    check("the artifact this project actually releases is classified, not "
          "rejected as junk",
          shape in (logic.LEGACY, logic.EXTENSION), shape)
    check("and it is the extension shape, which the installer must not hand "
          "to addon_install",
          shape == logic.EXTENSION, shape)
else:
    check("dist/void-tools.zip is built, so the real asset can be classified",
          False, built)

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
