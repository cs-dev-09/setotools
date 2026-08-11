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


def _sollumz_status():
    """(available, message) for the preferences box. Never raises: this is
    drawn from a UI callback, and an exception there is swallowed by Blender
    and shows as a panel that simply stops drawing."""
    try:
        from ..shared import sollumz_integration as szi
        return szi.get_status_message()
    except Exception as error:
        return False, f"Could not check: {error}"


def _wrap(text, width):
    from ..shared import ui_common
    return ui_common.wrap(text, width)


def _on_sollumz_module_changed(self, context):
    """Forget the cached detection so the new value takes effect immediately.

    Without this the box would still report the old answer until something
    else changed the set of enabled add-ons - which reads as the field doing
    nothing.
    """
    try:
        from ..shared import sollumz_integration as szi
        szi.forget_sollumz()
    except Exception:
        pass


def _on_library_path_changed(self, context):
    """Rescan when the folder changes, so Category/Texture are usable without
    having to press Refresh Library first.

    Never raises: an exception from a property update callback is swallowed by
    Blender and would leave the user with a silently stale cache.
    """
    library.scan_safe(self.library_path)
    # And refill the texture browser, which is a real collection and so cannot
    # be filled from a redraw. Imported here rather than at module level:
    # properties imports this module for the library path.
    try:
        from . import properties
        properties.rebuild_browser(context.scene.seto_decal)
    except Exception:
        pass


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

    # The kill switch for the updater's once-per-start version check. On by
    # default and said out loud everywhere it matters (the Updates panel,
    # the README): a check that is loud about existing and trivial to turn
    # off is the honest version of a notification.
    auto_check_updates: bpy.props.BoolProperty(
        name="Check for updates on startup",
        description=(
            "Once per Blender start, ask github.com whether a newer Seto "
            "Tools release exists so the Updates panel can say so. The "
            "request carries nothing about you or your files. Turn it off "
            "and the Check for Updates button still works on demand"
        ),
        default=True,
    )

    # Normally empty: every tool finds Sollumz by itself. This is the escape
    # hatch for the machine where it does not - a fork, a dev build, a folder
    # named something nobody anticipated - so the answer there is "point at it"
    # rather than "wait for the next release".
    sollumz_module: bpy.props.StringProperty(
        name="Sollumz Module",
        description=(
            "Leave empty unless Sollumz is not being detected. Accepts either "
            "the add-on's module name as Blender knows it (e.g. 'Sollumz', "
            "'Sollumz-main', 'bl_ext.user_default.sollumz') or the folder "
            "Sollumz is installed in"
        ),
        default="",
        update=_on_sollumz_module_changed,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "library_path")
        layout.prop(self, "preview_size")
        layout.prop(self, "auto_check_updates")

        # The other place a user looks for "where do I report this" - and
        # the one they can reach when the tab itself is not drawing.
        layout.separator()
        from ..support import ui as support_ui
        support_ui.draw_links(layout)

        box = layout.box()
        box.label(text="Sollumz", icon='PLUGIN')
        available, message = _sollumz_status()
        box.prop(self, "sollumz_module")
        col = box.column(align=True)
        for line in _wrap(message, 70):
            col.label(text=line, icon='CHECKMARK' if available else 'ERROR')
            break
        for line in _wrap(message, 70)[1:]:
            col.label(text=line)
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
