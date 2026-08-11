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
                "Screenshot", "Versions"):
    check(f"the body has a {heading} heading", heading in body, body)
check("and the screenshot heading says where to drop the picture",
      "drag your screenshot" in body, body)
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

print("=== nothing here reaches the network on its own ===")
import inspect
from seto_tools.support import operators as support_operators
source = inspect.getsource(support_operators) + inspect.getsource(report)
for forbidden in ("urlopen", "requests", "socket", "http.client"):
    check(f"no {forbidden} anywhere in the support code",
          forbidden not in source)
check("the only host it ever opens is this repository",
      report.NEW_ISSUE.startswith("https://github.com/seto3d/setotools/"))

print("=== the operator refuses an empty report ===")
# The one path that can be driven here without opening a browser. The
# success path ends in `wm.url_open`, which is exactly what a test must
# not run - so what it would have opened is asserted above, on the pure
# builder it uses.
settings = bpy.context.scene.seto_support
settings.title = ""
try:
    bpy.ops.seto.support_report()
    check("an empty report is refused", False, "operator ran")
except RuntimeError as error:
    check("an empty report is refused", "Fill in" in str(error), error)

print("=== the add-on does not touch pictures or folders at all ===")
# An image cannot travel in a URL, so there is no file field, nothing
# that captures the screen and nothing that opens a folder - only the
# heading in the body that says where to drop one.
check("nothing takes a screenshot", "screen.screenshot" not in source)
check("nothing opens a folder on disk", "path_open" not in source)
check("there is no screenshot field to fill in",
      "screenshot_path" not in settings.bl_rna.properties,
      list(settings.bl_rna.properties.keys()))
check("and no folder operator left behind",
      not hasattr(bpy.types, "SETO_OT_support_open_folder"))

print("=== Clear empties the form ===")
settings.title = "something"
settings.steps_0 = "a line"
bpy.ops.seto.support_clear()
check("the title went", settings.title == "", settings.title)
check("the answers went", settings.steps_0 == "", settings.steps_0)

print("=== each question is one field, and the plumbing knows it ===")
from seto_tools.support import properties as support_properties
# One line per question is the settled answer - every taller shape either
# moved the panel under the user's hands or sat unfilled. The stack
# machinery stays for the day that changes, exercised at whatever LINES
# currently is.
check("a question is a single field", support_properties.LINES == 1,
      support_properties.LINES)
check("every question has its declared stack",
      all(f"{name}_{index}" in settings.bl_rna.properties
          for name, _label in support_properties.FIELDS
          for index in range(support_properties.LINES)))
settings.steps_0 = "opened the file"
check("what is typed is what the report carries",
      support_properties.text_of(settings, "steps") == "opened the file",
      support_properties.text_of(settings, "steps"))
support_properties.clear(settings)
check("clearing empties every question",
      not any(support_properties.text_of(settings, name)
              for name, _label in support_properties.FIELDS))

failed = [r for r in RESULTS if not r[0]]
print("\n" + "=" * 60)
print(f"RESULT: {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
for _, n, d in failed: print("  FAIL", n, "--", d)
print("=" * 60)
sys.exit(1 if failed else 0)
