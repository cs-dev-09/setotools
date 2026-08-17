"""Run every verification script against a Blender, and say what failed.

    python tests/run_all.py --blender "D:/Blender52/blender.exe"

**Why this exists rather than a shell loop.** Once Void Tools is installed from
the extension repository - which is now the recommended way - the copy Blender
has enabled is `bl_ext.<repo>.void_tools`, while the tests import the working
tree. Two module objects for the same code: the panels the tests look for are
the *installed* ones, the module state they poke at is the *repo* one, and
suites start failing for reasons that have nothing to do with the code being
tested. Worse, registering the repo copy on top of the installed one is the
double-registration crash this project has written down.

So each run stands the installed extension down first, and gives the repo copy
the preferences entry it would otherwise lack (`addon_prefs.get()` returns None
without one, and panels that draw a preference then fail). Both are in memory
for that one Blender: `default_set=False`, and the preferences are never saved,
so the owner's own install is exactly as they left it when the run ends.
"""

import argparse
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
RESULT = re.compile(r"(\d+)/(\d+) checks passed")

# Every way this add-on can be installed. Whichever is enabled is stood down
# for the run; the rest are simply not there.
INSTALLED_NAMES = (
    "void_tools",
    "bl_ext.seto3d_github_io.void_tools",
    "bl_ext.user_default.void_tools",
    "seto_tools",                       # before the rename
)

PREPARE = (
    "import addon_utils, bpy\n"
    "for name in {names!r}:\n"
    "    try:\n"
    "        if addon_utils.check(name)[1]:\n"
    "            addon_utils.disable(name, default_set=False)\n"
    "    except Exception:\n"
    "        pass\n"
    "if 'void_tools' not in bpy.context.preferences.addons:\n"
    "    bpy.context.preferences.addons.new().module = 'void_tools'\n"
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", required=True)
    parser.add_argument("--only", default="", help="substring of the script name")
    args = parser.parse_args()

    scripts = sorted(glob.glob(os.path.join(TESTS, "*.py")))
    scripts = [s for s in scripts
               if os.path.basename(s) != os.path.basename(__file__)
               and args.only in os.path.basename(s)]

    prepare = PREPARE.format(names=INSTALLED_NAMES)
    failures = []
    total_passed = total_run = 0

    for script in scripts:
        name = os.path.basename(script)
        finished = subprocess.run(
            [args.blender, "-b", "--python-expr", prepare, "--python", script],
            capture_output=True, text=True, cwd=ROOT)
        output = finished.stdout + finished.stderr
        match = None
        for match in RESULT.finditer(output):
            pass                        # the last one is the script's total
        if match is None:
            failures.append((name, "no result line", output.splitlines()[-5:]))
            print(f"[ ?? ] {name}: produced no result")
            continue
        passed, ran = int(match.group(1)), int(match.group(2))
        total_passed += passed
        total_run += ran
        if passed != ran or finished.returncode != 0:
            named = [l for l in output.splitlines() if l.startswith("FAILED")]
            failures.append((name, f"{passed}/{ran}", named[:5]))
            print(f"[FAIL] {name}: {passed}/{ran}")
        else:
            print(f"[ ok ] {name}: {passed}/{ran}")

    print(f"\n{total_passed}/{total_run} checks across {len(scripts)} scripts")
    for name, summary, detail in failures:
        print(f"\n{name} — {summary}")
        for line in detail:
            print(f"    {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
