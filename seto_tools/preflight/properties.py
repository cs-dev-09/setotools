"""Where a Pre-Flight run's findings live.

A CollectionProperty on the Scene rather than a module-level list: it
survives a file save, an undo and a script reload, and the panel can draw
it without recomputing anything. Recomputing in draw() is what makes a
panel stutter, and this walk touches every polygon in the scene.
"""

import bpy

from ..shared import viewport_grade as vg
from . import checks


class SETO_PG_preflight_finding(bpy.types.PropertyGroup):
    object_name: bpy.props.StringProperty()
    check: bpy.props.StringProperty()
    severity: bpy.props.StringProperty()
    message: bpy.props.StringProperty()
    # Which material slot the finding is in, or -1 when it is about the
    # whole object. The jump button uses it to select that slot and show
    # the Material tab, so a .png in the third shader is one click away.
    material_index: bpy.props.IntProperty(default=-1)
    # Why a Fix declined, kept on the row that declined it. The status bar
    # is fine for one button press and useless for Fix All, where eleven
    # refusals scroll past as a single line nobody can act on.
    note: bpy.props.StringProperty(default="")


class SETO_PG_preflight(bpy.types.PropertyGroup):
    scope: bpy.props.EnumProperty(
        name="Scope",
        description="Which objects Pre-Flight checks",
        items=vg.SCOPE_ITEMS,
        default='VISIBLE',
    )
    findings: bpy.props.CollectionProperty(type=SETO_PG_preflight_finding)
    # One open/closed flag per heading, indexed by checks.GROUP_ORDER. A
    # vector rather than a property per group because the headings are
    # data, not code - and rather than a CollectionProperty because draw()
    # cannot add to a collection without crashing Blender.
    # Closed to start with: a run on a real MLO comes back with dozens of
    # findings, and opening the one group you care about beats scrolling
    # past four you do not. The counts on the headings are the summary.
    expanded: bpy.props.BoolVectorProperty(
        size=len(checks.GROUP_ORDER),
        default=tuple(False for _ in checks.GROUP_ORDER),
        options={'HIDDEN'},
    )
    # Whether a run has happened, as distinct from a run that found nothing -
    # an empty list means "all clear" only once something has been checked.
    has_run: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    checked: bpy.props.IntProperty(default=0, options={'HIDDEN'})


_classes = (SETO_PG_preflight_finding, SETO_PG_preflight)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_preflight = bpy.props.PointerProperty(
        type=SETO_PG_preflight)


def unregister():
    del bpy.types.Scene.seto_preflight
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
