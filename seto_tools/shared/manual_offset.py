"""Keeping a hand-moved strip where it was put.

Every tool's `rebuild()` ends with the same three lines: place the object back
on its source, swap the mesh in, re-centre the origin. That is what makes
repeated rebuilds stable - and it is also what wipes a manual move. Nudge a
finished strip up off the floor, touch any setting, and it snaps back onto the
source.

The obvious fix does not work, and this was measured rather than assumed:
capturing `source.matrix_world.inverted() @ obj.matrix_world` before the
rebuild and re-applying it after leaves the strip neither where it was put nor
where it started, because `_centre_origin()` runs in between and recomputes the
origin from the *new* mesh. Any offset derived from the object's own transform
is therefore stale by the time it could be used.

So the offset is remembered instead of derived. Two values live on the strip:

    auto_location   where the last rebuild put the origin, before any offset
    manual_offset   what the user wants added to that

`apply()` writes the first and adds the second, at the very end of a rebuild.
That survives `_centre_origin` because it runs after it.

**Both are the object's own location, not its world position.** A strip built
from a source inside a Sollumz Drawable is parented into that Drawable, and a
world-space `auto_location` goes stale the moment the Drawable is moved - the
strip travels with its parent, as it should, but the remembered figure does
not. Typing into the Offset field then teleported the strip back to where the
Drawable used to be. Expressed in the object's own transform, which is what
parenting leaves alone, there is nothing to go stale.

Why there is a button rather than a silent grab of `obj.location`: a rebuild
moves the object legitimately, several times per slider drag, so there is no
way to tell the user's drag from the tool's own repositioning. Pin Position is
the moment that says "from here on, this one is mine".
"""

import bpy
from mathutils import Vector

from . import panel_layout as pl


def _on_offset_changed(self, context):
    """Move the strip as the offset is typed or dragged.

    No rebuild: the mesh is unchanged, only where its origin sits, so this is a
    matrix write and nothing more. Runs from a property callback like every
    other live update here, which is why it goes nowhere near `bpy.ops`.
    """
    obj = getattr(self, "id_data", None)
    if obj is None or not isinstance(obj, bpy.types.Object):
        return
    place(obj, self)


def annotations():
    """The two properties, for a tool's `_object_annotations()`.

    Deliberately not in `properties.settings_annotations()`: those are mirrored
    onto the Scene group as defaults for the next strip, and where one strip was
    dragged to is meaningless as a default for the next one.
    """
    return {
        "manual_offset": bpy.props.FloatVectorProperty(
            name="Position Offset",
            description=(
                "Where this strip sits relative to where the tool puts it. Set it with Pin "
                "Position after moving the strip by hand, and every rebuild keeps it there"
            ),
            size=3,
            subtype='TRANSLATION',
            unit='LENGTH',
            default=(0.0, 0.0, 0.0),
            update=_on_offset_changed,
        ),
        "auto_location": bpy.props.FloatVectorProperty(
            name="Generated Location",
            description=(
                "Where the last rebuild placed this strip's origin, before the offset above. "
                "Bookkeeping: it is what makes a hand-moved strip measurable"
            ),
            size=3,
            subtype='TRANSLATION',
            unit='LENGTH',
            default=(0.0, 0.0, 0.0),
            options={'HIDDEN'},
        ),
    }


def place(obj, data):
    """Put `obj` at its generated location plus its offset."""
    obj.location = Vector(data.auto_location) + Vector(data.manual_offset)


def reset(obj, data):
    """Mark where the object is now as its generated location, offset zero.

    For the create operators: without it, a strip that is dragged and pinned
    before it has ever been rebuilt would measure its offset against the
    origin.
    """
    data.auto_location = tuple(obj.location)
    # Through the ID-property back door on purpose: assigning the property
    # fires the update below, which would move a strip that is already exactly
    # where it belongs.
    data["manual_offset"] = (0.0, 0.0, 0.0)


def apply(obj, data):
    """The last thing a rebuild does - after `_centre_origin`, never before."""
    data.auto_location = tuple(obj.location)
    place(obj, data)


def capture(obj, data):
    """Adopt wherever the object has been dragged to as its offset."""
    data.manual_offset = Vector(obj.location) - Vector(data.auto_location)


def is_pinned(data):
    return any(abs(value) > 1e-9 for value in data.manual_offset)


class SETO_OT_pin_strip_position(bpy.types.Operator):
    """Keep this strip where you have moved it. Rebuilds stop snapping it back onto its source"""
    bl_idname = "seto.pin_strip_position"
    bl_label = "Pin Position"
    bl_options = {'REGISTER', 'UNDO'}

    # Which tool's per-object group to write, set by the panel that drew the
    # button. One operator for all four strip tools: they differ in the
    # attribute name and in nothing else.
    data_attr: bpy.props.StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        data = getattr(obj, self.data_attr, None)
        if data is None:
            self.report({'ERROR'}, "This object carries no Seto Tools strip data.")
            return {'CANCELLED'}
        capture(obj, data)
        if is_pinned(data):
            self.report({'INFO'}, f"'{obj.name}' pinned {Vector(data.manual_offset).length:.3f} m from where it is generated.")
        else:
            self.report({'INFO'}, f"'{obj.name}' is where it is generated - nothing to pin.")
        return {'FINISHED'}


class SETO_OT_clear_strip_position(bpy.types.Operator):
    """Drop the pinned offset and put this strip back where the tool generates it"""
    bl_idname = "seto.clear_strip_position"
    bl_label = "Clear Offset"
    bl_options = {'REGISTER', 'UNDO'}

    data_attr: bpy.props.StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        data = getattr(obj, self.data_attr, None)
        if data is None:
            self.report({'ERROR'}, "This object carries no Seto Tools strip data.")
            return {'CANCELLED'}
        # Assigned rather than zeroed through the ID-property back door, so the
        # update callback moves the object back.
        data.manual_offset = (0.0, 0.0, 0.0)
        return {'FINISHED'}


def draw(layout, data, data_attr):
    """The Position section on a "Selected Strip" panel."""
    col = pl.section(layout, "Position", 'ORIENTATION_LOCAL')
    col.prop(data, "manual_offset", text="Offset")

    row = col.row(align=True)
    row.operator(SETO_OT_pin_strip_position.bl_idname,
                 icon='PINNED').data_attr = data_attr
    clear = row.row(align=True)
    clear.enabled = is_pinned(data)
    clear.operator(SETO_OT_clear_strip_position.bl_idname,
                   icon='LOOP_BACK').data_attr = data_attr


_classes = (SETO_OT_pin_strip_position, SETO_OT_clear_strip_position)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
