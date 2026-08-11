"""The bug report: that it collects the right things and sends nothing.

The second half is the part worth guarding. This add-on has no business
posting on anyone's behalf, so the operator's whole job is to open
GitHub's own form with the fields filled in - what goes out is what the
user reads on screen and submits themselves, signed in as themselves.
"""
import bpy, sys, urllib.parse

sys.path.append(r"D:\SetoClaude\setotools")

RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

import seto_tools
if getattr(bpy.types, "SETO_PT_support_panel", None) is None:
    seto_tools.register()

from seto_tools.support import report

print("=== the body says what a maintainer asks for first ===")
body = report.build_body("pressed Analyze", "everything went grey",
                         "colours", include_environment=True)
for heading in ("What I did", "What happened", "What I expected",
                "Versions"):
    check(f"the body has a {heading} heading", heading in body, body)
check("what was typed is in it", "everything went grey" in body)
check("an empty field says so rather than leaving a blank heading",
      "_(not filled in)_" in report.build_body("", "", "", False))
check("the versions can be left out",
      "Versions" not in report.build_body("a", "b", "c", False))

print("=== the versions are the real ones ===")
environment = dict(report.environment())
check("Blender's version is reported",
      environment["Blender"] == bpy.app.version_string, environment)
check("the add-on's own version is found, not a placeholder",
      environment["Seto Tools"] not in ("", "unknown"), environment)
check("and it matches bl_info", environment["Seto Tools"]
      == ".".join(str(n) for n in seto_tools.bl_info["version"]), environment)
check("whether Sollumz was found is reported either way",
      environment["Sollumz"].startswith(("found", "not found")), environment)
check("the OS is named", bool(environment["OS"].strip()), environment)

print("=== the URL is GitHub's own form, filled in ===")
url = report.build_url("Strips come out inside out", body)
check("it points at the new-issue form",
      url.startswith(report.NEW_ISSUE + "?"), url)
query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
check("the title survives the round trip",
      query["title"] == ["Strips come out inside out"], query.get("title"))
check("and so does the body, newlines and all",
      query["body"] == [body], query.get("body"))
check("an empty title still gets one",
      urllib.parse.parse_qs(
          urllib.parse.urlparse(report.build_url("   ", "x")).query)["title"]
      == ["Bug report"])
check("a title with characters a URL cares about is encoded, not broken",
      urllib.parse.parse_qs(urllib.parse.urlparse(
          report.build_url("a&b=c #1", "x")).query)["title"] == ["a&b=c #1"])

print("=== a report too long for a URL falls back rather than truncating ===")
check("a normal report is not too long", not report.too_long(url), len(url))
check("a huge one is", report.too_long(report.build_url("t", "x" * 9000)))

print("=== the operator refuses an empty report ===")
# The one path that can be driven here without opening a browser. The
# success path ends in `wm.url_open`, which is exactly what a test must
# not run - so what it would have opened is asserted above, on the pure
# builder it uses.
settings = bpy.context.scene.seto_support
settings.title = ""
settings.result = ""
try:
    bpy.ops.seto.support_report()
    check("an empty report is refused", False, "operator ran")
except RuntimeError as error:
    check("an empty report is refused", "Fill in" in str(error), error)

print("=== nothing here reaches the network on its own ===")
import inspect
from seto_tools.support import operators as support_operators
source = inspect.getsource(support_operators) + inspect.getsource(report)
for forbidden in ("urlopen", "requests", "socket", "http.client"):
    check(f"no {forbidden} anywhere in the support code",
          forbidden not in source)
check("the only host it ever opens is this repository",
      report.NEW_ISSUE.startswith("https://github.com/seto3d/setotools/"))

print("=== Copy puts the same report where it can be pasted ===")
settings.title = "Test report"
settings.result = "it did the wrong thing"
settings.steps = "pressed the button"
settings.expected = "the right thing"
check("Copy runs", bpy.ops.seto.support_copy() == {'FINISHED'})

# Background Blender has no system clipboard to write to, so reading it
# back proves nothing about the operator - it is the environment that is
# missing, not the code. Where a clipboard does exist, the round trip is
# checked properly.
bpy.context.window_manager.clipboard = "seto-clipboard-probe"
if bpy.context.window_manager.clipboard == "seto-clipboard-probe":
    bpy.ops.seto.support_copy()
    clipboard = bpy.context.window_manager.clipboard
    check("the body is on the clipboard",
          "it did the wrong thing" in clipboard, clipboard[:120])
    check("and the title goes with it", "Test report" in clipboard,
          clipboard[:120])
else:
    print("[SKIP] no clipboard in this Blender - background mode")

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
