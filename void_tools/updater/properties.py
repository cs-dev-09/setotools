"""What the last update check found.

On the **WindowManager**, deliberately: WindowManager properties are not
saved into .blend files and do not survive a restart, so "an update is
available" can never go stale in a saved file and greet the user with an
out-of-date claim next week. Every session starts blank, and blank means
"press Check to find out".
"""

import bpy


class SETO_PG_updater(bpy.types.PropertyGroup):
    status: bpy.props.StringProperty(default="")
    latest: bpy.props.StringProperty(default="")
    download_url: bpy.props.StringProperty(default="")
    update_available: bpy.props.BoolProperty(default=False)


_classes = (SETO_PG_updater,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.seto_updater = bpy.props.PointerProperty(
        type=SETO_PG_updater)


def unregister():
    del bpy.types.WindowManager.seto_updater
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
