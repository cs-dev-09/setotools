"""Real prop meshes, appended from the user's .blend prop library.

The wireframe bounding boxes place and export perfectly - the ytyp entity
only needs a transform - but a floor of grey boxes does not *read*. This
module trades the box for the real thing wherever it can: the user points
the add-on at a folder of .blend files whose objects are named after
archetypes (an asset library extracted from the game - one exists at the
scale of thousands of props), and Scatter appends the matching mesh, with
its materials and textures, the first time each prop is needed.

Three deliberate properties:

- **The library is indexed once, not searched per scatter.** Opening ~100
  library .blends just to list their object names takes seconds; doing it
  on every press would make the button feel broken. The index is cached in
  the add-on preferences with a stamp of the folder's shape, and rebuilt
  only when the stamp stops matching (or on Rescan).
- **One append per prop per .blend file.** The appended object is thrown
  away on the spot; only its mesh datablock survives, renamed to a stable
  name every later instance reuses. Forty cigarette butts stay one mesh.
- **Missing is not an error.** A prop the library does not have falls back
  to its bounding-box proxy - the export is identical either way, only the
  viewport differs.
"""

import json
import os

import bpy

from ..shared import addon_prefs
from . import catalog

# The stable name the appended mesh datablock is kept under.
MESH_PREFIX = "seto_scatter_mesh_"


def _blend_files(folder):
    """Every .blend under `folder`, recursively. Backups (.blend1) excluded."""
    found = []
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if name.lower().endswith(".blend"):
                found.append(os.path.join(root, name))
    return sorted(found)


# No mtime fingerprinting, deliberately. Indexing a real library measures
# in **minutes** (a couple of hundred .blends, each opened to list its
# objects), so an automatic rescan triggered by a changed folder would
# freeze a Scatter click - or worse, a live slider drag - for exactly that
# long. The cache is keyed to the folder path alone: pointing at a
# different folder rescans, everything else serves the cache, and a
# library whose *contents* changed is what the Rescan button is for.


def scan(folder):
    """name -> (blend path, exact object name) for every catalogue prop.

    Only catalogue names are indexed: the cache lives in the preferences
    file, and indexing a two-thousand-prop library there for the forty
    names this tool can place would be freight, not data.
    """
    wanted = set(catalog.PROPS)
    index = {}
    for path in _blend_files(folder):
        if len(index) == len(wanted):
            break
        try:
            with bpy.data.libraries.load(path, link=False) as (src, _dst):
                names = list(src.objects)
        except Exception:
            continue  # not a readable library; skip, the box covers it
        for obj_name in names:
            base = obj_name.split(".")[0]
            if base in wanted and base not in index:
                index[base] = (path, obj_name)
    return index


def _folder(prefs):
    folder = getattr(prefs, "scatter_library", "") if prefs else ""
    folder = bpy.path.abspath(folder) if folder else ""
    return folder if folder and os.path.isdir(folder) else ""


def is_indexed(context=None):
    """Whether the configured folder has an index - the panel's hint reads it."""
    prefs = addon_prefs.get(context)
    folder = _folder(prefs)
    return bool(folder) and \
        getattr(prefs, "scatter_library_stamp", "") == folder


def get_index(context=None, allow_scan=False):
    """The cached library index; {} when there is none.

    Scanning happens **only** when `allow_scan` is set, and the only
    caller that sets it is the Rescan operator - a scan measures in
    minutes, and a Scatter click or a live slider drag must never be the
    thing that pays for it. An un-indexed library costs boxes and a hint,
    not a freeze.
    """
    prefs = addon_prefs.get(context)
    folder = _folder(prefs)
    if not folder:
        return {}

    if prefs is not None and getattr(prefs, "scatter_library_stamp", "") == folder:
        try:
            cached = json.loads(prefs.scatter_library_index)
            return {k: tuple(v) for k, v in cached.items()}
        except Exception:
            pass  # corrupt cache; fall through as unindexed

    if not allow_scan:
        return {}

    index = scan(folder)
    if prefs is not None:
        try:
            prefs.scatter_library_index = json.dumps(index)
            prefs.scatter_library_stamp = folder
        except Exception:
            pass  # read-only prefs (tests); the scan result still serves
    return index


def forget():
    """Drop the cache so the next get_index() rescans."""
    prefs = addon_prefs.get()
    if prefs is not None:
        prefs.scatter_library_stamp = ""
        prefs.scatter_library_index = "{}"


def fetch_meshes(names, index):
    """name -> mesh for every prop the library can dress, batched per file.

    A library .blend takes real time to open - the big ones take seconds -
    and one file holds many props, so everything missing is appended in
    **one load per file** rather than one per prop (the difference between
    a pause and a freeze on the first Scatter). Each appended object is
    thrown away on the spot; only its mesh survives, renamed to a stable
    name every later instance and every later rebuild reuses. Nothing of
    the library's object (its transforms, its custom properties, any
    Sollumz typing) leaks into the scene.
    """
    meshes = {}
    by_path = {}
    for name in names:
        existing = bpy.data.meshes.get(MESH_PREFIX + name)
        if existing is not None:
            meshes[name] = existing
            continue
        entry = index.get(name)
        if entry is not None:
            path, obj_name = entry
            by_path.setdefault(path, []).append((name, obj_name))

    for path, wanted in by_path.items():
        try:
            with bpy.data.libraries.load(path, link=False) as (src, dst):
                available = list(src.objects)
                # The named object plus anything sharing its name as a
                # prefix. Sollumz's own Asset Library builder writes a
                # Drawable, which on some props is an empty parent with
                # the mesh underneath it (`prop_x`, `prop_x.001`) - asking
                # only for the exact name would append the empty, find no
                # mesh on it, and quietly fall back to a box.
                requested = []
                for _name, obj_name in wanted:
                    requested.append(obj_name)
                    prefix = obj_name.split(".")[0]
                    requested += [other for other in available
                                  if other != obj_name
                                  and other.split(".")[0] == prefix]
                dst.objects = list(dict.fromkeys(requested))
        except Exception:
            continue  # unreadable file; its props stay boxes

        appended = [obj for obj in dst.objects if obj is not None]
        by_prefix = {}
        for obj in appended:
            by_prefix.setdefault(obj.name.split(".")[0], []).append(obj)

        for name, obj_name in wanted:
            candidates = by_prefix.get(obj_name.split(".")[0], [])
            # The exact object first when it is a mesh, then the mesh with
            # the most geometry - a Drawable's LODs all sit here, and the
            # biggest is the one meant to be seen up close.
            exact = next((o for o in candidates
                          if o.name == obj_name and o.type == 'MESH'), None)
            mesh_objs = [o for o in candidates if o.type == 'MESH']
            chosen = exact or (max(mesh_objs, key=lambda o: len(o.data.polygons))
                               if mesh_objs else None)
            if chosen is None:
                continue
            mesh = chosen.data
            mesh.name = MESH_PREFIX + name
            meshes[name] = mesh

        for obj in appended:
            bpy.data.objects.remove(obj)

    return meshes
