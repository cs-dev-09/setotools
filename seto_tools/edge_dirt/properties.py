"""Scene-level settings for Edge Dirt.

The settings themselves are Ambient Occlusion's, imported rather than
redeclared: the two tools build the identical strip and differ only in the
texture that goes on it, so every Width, Alpha and Bevel here has to mean
exactly what it means there.

What is NOT shared is the values. Each tool gets its own PropertyGroup on the
Scene, so dialling a dirt streak in at 0.08 m cannot move the AO shadow's shelf
- which is the same reason Ambient Occlusion stays out of the strip settings
Edge Wear and Smooth Edge share.
"""

import bpy

from ..fake_ao.properties import (  # noqa: F401  (re-exported for this package)
    SETTING_NAMES,
    copy_settings,
    settings_annotations,
)


class SETO_PG_edge_dirt_settings(bpy.types.PropertyGroup):
    # Assigned rather than written with `name: bpy.props...` syntax so the
    # definitions stay shared with the operator and the per-object group -
    # see settings_annotations().
    __annotations__ = settings_annotations()


_classes = (SETO_PG_edge_dirt_settings,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_edge_dirt = bpy.props.PointerProperty(type=SETO_PG_edge_dirt_settings)


def unregister():
    del bpy.types.Scene.seto_edge_dirt
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
