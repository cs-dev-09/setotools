"""One grading session at a time, and a guaranteed way back.

Two Analysis tools now paint their verdicts into object colours, and both
have to flip the viewport to Object shading to make them visible. Left to
themselves they would fight: the second tool to run would save the *first
tool's* verdict as "the user's own colour", and finishing would restore a
scene painted green and red.

So the session is shared. One record of what each object's colour was
before any grading started, one record of what the viewport was showing,
and one owner - starting a second tool ends the first cleanly rather than
layering on top of it.

`owner` is also what the panels key their two states off; a tool asking
"am I showing?" is asking this module, not its own flag.
"""

import bpy

# The one place an object's real colour is kept while a tool is painting over
# it. Named for the session rather than for a tool, because whichever tool
# started it is the one that must be able to hand it back.
SAVED_COLOUR_PROP = "seto_grade_saved_colour"

# Every measuring property any tool leaves on an object, by tool. Ending the
# session clears all of them and not merely the current owner's: switching
# tools ends the first one, and a `seto_density_tris` left behind by a run
# nobody finished is litter in the .blend that outlives the analysis.
_TOOL_PROPS = {}


def owns(tool, props):
    """Declare which ID properties `tool` leaves behind. Called at import."""
    _TOOL_PROPS[tool] = tuple(props)


def measuring_props():
    return tuple(prop for props in _TOOL_PROPS.values() for prop in props)


class SETO_PG_viewport_grade(bpy.types.PropertyGroup):
    # Which tool is painting: "" when none, otherwise its own id string.
    owner: bpy.props.StringProperty(default="", options={'HIDDEN'})
    # What the viewport's colour mode was before the flip. Saved even when it
    # was already OBJECT: end() restores this verbatim, and a viewport that
    # started on Object colours should end on them.
    saved_shading: bpy.props.StringProperty(default="", options={'HIDDEN'})


def get(context):
    return context.scene.seto_grade


def owner(context):
    return get(context).owner


def is_active(context, tool):
    return get(context).owner == tool


def _view3d_shadings(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    yield space.shading


def begin(context, tool):
    """Take over the session for `tool`, ending anyone else's first."""
    grade = get(context)
    if grade.owner and grade.owner != tool:
        end(context)
        grade = get(context)
    for shading in _view3d_shadings(context):
        if not grade.saved_shading:
            grade.saved_shading = shading.color_type
        if shading.color_type != 'OBJECT':
            shading.color_type = 'OBJECT'
    grade.owner = tool


def paint(obj, colour):
    """Colour one object, remembering its own colour the first time only.

    Saving once is what makes a second Analyze safe: without it the second
    run would adopt the first run's verdict as the colour to restore.
    """
    if SAVED_COLOUR_PROP not in obj:
        obj[SAVED_COLOUR_PROP] = list(obj.color)
    obj.color = colour


def end(context):
    """Hand every colour back and put the viewport where it was found.

    Sweeps `bpy.data.objects` rather than the current scope: the scope can
    change while an analysis is up, and a Finish that misses objects leaves
    stale verdicts painted on them. Every tool's measuring properties go in
    the same pass, whoever owned the session.
    """
    grade = get(context)
    props = measuring_props()
    count = 0
    for obj in bpy.data.objects:
        if SAVED_COLOUR_PROP in obj:
            obj.color = list(obj[SAVED_COLOUR_PROP])
            del obj[SAVED_COLOUR_PROP]
            count += 1
        for prop in props:
            if prop in obj:
                del obj[prop]

    restore = grade.saved_shading or 'MATERIAL'
    for shading in _view3d_shadings(context):
        if shading.color_type == 'OBJECT':
            shading.color_type = restore
    grade.saved_shading = ""
    grade.owner = ""
    return count


def scope_objects(context, scope):
    """Mesh objects a Visible/Selected scope names, read through the view
    layer - `context.selected_objects` is screen state and background
    Blender has no screen, so the view layer is what exists everywhere the
    tests run."""
    objects = context.view_layer.objects
    if scope == 'SELECTED':
        pool = [obj for obj in objects if obj.select_get()]
    else:
        pool = [obj for obj in objects if obj.visible_get()]
    return [obj for obj in pool if obj.type == 'MESH']


SCOPE_ITEMS = (
    ('VISIBLE', "Visible", "Every visible mesh object in the view layer"),
    ('SELECTED', "Selected", "Only the selected mesh objects"),
)


_classes = (SETO_PG_viewport_grade,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_grade = bpy.props.PointerProperty(
        type=SETO_PG_viewport_grade)


def unregister():
    del bpy.types.Scene.seto_grade
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
