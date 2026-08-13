"""Build seto_tools.zip, the artifact the add-on is installed from.

    python scripts/build_zip.py

The zip is gitignored - it is a build output, not source - and it is what goes
on a GitHub release and into Blender's **Install from Disk**.

**Not `Compress-Archive`.** PowerShell writes Windows separators into the entry
names (`seto_tools\\__init__.py`), which the ZIP spec forbids. Blender installs
through Python's `zipfile`, which splits paths on `/` only, so on macOS and
Linux the whole add-on extracts as a handful of files with backslashes in their
names and the tab never appears. That is the entire reason this file exists,
and the check at the bottom is what proves it did not happen.

Written down here rather than retyped from memory each time: it lived in a
scratchpad, which is how it came to be retyped at all.
"""

import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "seto_tools")
TARGET = os.path.join(ROOT, "seto_tools.zip")

# Nothing here is source. `lighting/` is not registered and does not ship;
# `__pycache__` is this machine's Python version and is regenerated on first
# import anyway.
SKIP_DIRECTORIES = {"__pycache__", "lighting", ".git"}
# `.md` covers the per-package READMEs and smooth_edge/FEEDBACK.md. They are
# the old documentation, kept in the repository where GitHub renders them and
# where the docs site is built from - but nobody has ever read a Markdown file
# inside `scripts/addons/`, and they were 60 KB of the installed add-on. The
# `.txt` files in the texture folders deliberately stay: those folders are
# opened by hand to swap a texture, the note explains what belongs there, and
# an empty folder cannot survive a zip without a file in it.
SKIP_SUFFIXES = (".pyc", ".pyo", ".blend1", ".orig", ".rej", ".md")
SKIP_NAMES = {"desktop.ini", "Thumbs.db", ".DS_Store"}


def entries():
    """Every file that ships, as (absolute path, name inside the zip)."""
    for directory, subdirectories, files in os.walk(SOURCE):
        subdirectories[:] = sorted(d for d in subdirectories if d not in SKIP_DIRECTORIES)
        for name in sorted(files):
            if name in SKIP_NAMES or name.endswith(SKIP_SUFFIXES):
                continue
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, ROOT)
            yield path, relative.replace(os.sep, "/")


def version():
    with open(os.path.join(SOURCE, "__init__.py"), encoding="utf-8") as handle:
        for line in handle:
            if '"version"' in line:
                return line.strip().rstrip(",")
    return "unknown"


def main():
    before = os.path.getsize(TARGET) if os.path.exists(TARGET) else 0

    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        count = 0
        for path, name in entries():
            archive.write(path, name)
            count += 1

    with zipfile.ZipFile(TARGET) as archive:
        names = archive.namelist()
    bad = [n for n in names if "\\" in n]
    if bad:
        print("FAILED: Windows separators in", len(bad), "entry name(s):", bad[:3])
        return 1

    after = os.path.getsize(TARGET)
    print(f"{os.path.relpath(TARGET, ROOT)}: {count} files, {version()}")
    print(f"  {after / 1024:.0f} KB" + (f"  (was {before / 1024:.0f} KB)" if before else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
