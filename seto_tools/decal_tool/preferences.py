"""Add-on preferences - where the decal library folder lives.

The library path is deliberately NOT stored on the Scene. It is a property of
your setup, not of a particular asset, so keeping it in the add-on preferences
means it is picked once and then remembered across new files, restarts and
add-on updates. It also keeps opening a .blend from silently marking it as
modified, which is what writing the path into the scene would do.

The panel's Decal Library field edits this same property directly, so setting it
there and setting it in Edit > Preferences > Add-ons are the same action.

Blender writes preferences to disk automatically unless "Auto-Save Preferences"
has been turned off; the field is also exposed in the add-on preferences UI,
where the usual Save Preferences button applies.
"""

import bpy

from . import library

# The module name this add-on is registered under, which is what
# AddonPreferences.bl_idname has to match. Derived rather than hardcoded because
# it differs between a legacy add-on ("seto_decal_tool") and a 4.2+ extension
# ("bl_ext.user_default.seto_decal_tool").
ADDON_PACKAGE = __package__.rpartition(".")[0]


def get_preferences(context=None):
    """This add-on's preferences, or None if they are not available.

    Returns None rather than raising: preferences are legitimately missing while
    the add-on is mid-registration, and when the package is imported directly
    rather than installed as an add-on (the test harness does exactly that).
    """
    context = context or bpy.context
    addon = context.preferences.addons.get(ADDON_PACKAGE)
    return addon.preferences if addon is not None else None


def get_library_path():
    """The configured decal library folder, or "" when unavailable/unset."""
    prefs = get_preferences()
    return prefs.library_path if prefs is not None else _fallback["library_path"]


def set_library_path(path):
    """Set the library folder (and rescan). Used by the tests and by any caller
    that has no access to the preferences UI."""
    prefs = get_preferences()
    if prefs is not None:
        prefs.library_path = path
        return
    # No preferences available - keep the path in-process so the rest of the
    # tool still works for this session.
    _fallback["library_path"] = path
    library.scan_safe(path)


# Used only when AddonPreferences are unavailable (see get_preferences).
_fallback = {"library_path": ""}


def _on_library_path_changed(self, context):
    """Rescan when the folder changes, so Category/Texture are usable without
    having to press Refresh Library first.

    Never raises: an exception from a property update callback is swallowed by
    Blender and would leave the user with a silently stale cache.
    """
    library.scan_safe(self.library_path)


class SETO_AP_decal_tool(bpy.types.AddonPreferences):
    bl_idname = ADDON_PACKAGE

    library_path: bpy.props.StringProperty(
        name="Decal Library",
        description=(
            "Folder containing the decal library. Each subfolder becomes a category "
            "(Dirt, Cracks, Leaks, ...); images directly in this folder appear under "
            f"'{library.ROOT_CATEGORY}'. Remembered across files and restarts, so it "
            "only has to be picked once"
        ),
        subtype='DIR_PATH',
        default="",
        update=_on_library_path_changed,
    )

    # Shared by every Seto tool that shows a texture picker. It lives here
    # because Blender allows one AddonPreferences per add-on and this is it;
    # the other tools read it through shared/addon_prefs.py rather than
    # importing this module.
    preview_size: bpy.props.FloatProperty(
        name="Texture Preview Size",
        description=(
            "How large texture thumbnails are drawn, in UI units - both in the "
            "panel and in the browser popup. Blender cannot show a preview on "
            "hover, so making the browser tiles big is what replaces it"
        ),
        default=12.0, min=4.0, max=40.0, subtype='FACTOR',
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "library_path")
        layout.prop(self, "preview_size")
        if self.library_path:
            layout.label(
                text=f"{len(library.get_categories())} category/categories loaded.",
                icon='CHECKMARK',
            )
        else:
            layout.label(
                text="Not set - pick a folder here or in the Decal Tool panel.",
                icon='ERROR',
            )


_classes = (SETO_AP_decal_tool,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    # Fill the cache from the remembered folder, so the Category/Texture enums
    # are already populated the first time the panel is drawn.
    path = get_library_path()
    if path:
        library.scan_safe(path)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
