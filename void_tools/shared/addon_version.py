"""What version this add-on is, however it was installed.

There are two answers and only one of them is always there. A legacy add-on
keeps the `bl_info` dict written at the top of `__init__.py`; an **extension**
does not - Blender removes the attribute outright and rebuilds the same
information from `blender_manifest.toml`, reachable through
`addon_utils.module_bl_info()`.

Reading only the first is how the Updates panel came to offer "Void Tools
0.0.0" to anyone who installed from the repository, and how the bug-report
form would have carried that number to a maintainer trying to reproduce
something. Both now ask here.
"""

import sys

from . import addon_prefs

FALLBACK = (0, 0, 0)


def info():
    """The add-on's own `bl_info`, whichever way Blender is keeping it."""
    module = sys.modules.get(addon_prefs.ADDON_PACKAGE)
    if module is None:
        return {}
    existing = getattr(module, "bl_info", None)
    if existing:
        return existing
    try:
        import addon_utils
    except ImportError:
        return {}                       # imported outside Blender, by a test
    return addon_utils.module_bl_info(module) or {}


def current():
    """The running version as a tuple, or (0, 0, 0) if it cannot be read."""
    return tuple(info().get("version", ())) or FALLBACK


def current_str():
    return ".".join(str(number) for number in current())
