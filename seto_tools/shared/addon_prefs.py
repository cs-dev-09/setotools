"""Reading this add-on's preferences, from any tool.

Blender allows exactly one AddonPreferences class per add-on, and Seto Tools'
lives in decal_tool/preferences.py for historical reasons - that tool shipped
first. Settings that belong to the whole add-on rather than to one tool are
declared there and read through here, so no tool has to import another tool's
modules to reach them.

Everything returns a default rather than raising: preferences are legitimately
missing while the add-on is mid-registration, and when the package is imported
directly rather than installed (the test harness does exactly that).
"""

import bpy

# The module name the add-on is registered under. Derived rather than
# hardcoded, because it differs between a legacy add-on ("seto_tools") and a
# 4.2+ extension ("bl_ext.user_default.seto_tools").
ADDON_PACKAGE = __package__.rpartition(".")[0]

# Height of a texture thumbnail, in UI units, when no preferences are available.
DEFAULT_PREVIEW_SIZE = 12.0


def get(context=None):
    """This add-on's preferences, or None."""
    context = context or bpy.context
    addon = context.preferences.addons.get(ADDON_PACKAGE)
    return addon.preferences if addon is not None else None


def preview_size(context=None):
    """How large texture thumbnails are drawn, in UI units."""
    prefs = get(context)
    return getattr(prefs, "preview_size", DEFAULT_PREVIEW_SIZE)


def sollumz_override(context=None):
    """The Sollumz module name or folder the user pinned, or "".

    Empty is the normal case - detection finds it on its own. This exists for
    the machine where it does not, so the answer is "tell it where" rather than
    "wait for a release".
    """
    prefs = get(context)
    return getattr(prefs, "sollumz_module", "")
