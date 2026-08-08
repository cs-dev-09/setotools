"""Per-object settings that reposition and resize a decal live as you drag them.

A generated decal keeps the surface frame it was placed on - the face center,
the surface normal and the two base axes lying in that face - plus the settings
used. Dragging any of those settings recomposes the object's matrix and moves
its four vertices, so the decal slides, spins and resizes on the surface in real
time without ever leaving it.

Two deliberate differences from the Fake Damage version of this module:

  * The frame is stored on the decal, not re-read from the source mesh. A decal
    is a single quad with no topology of its own to re-derive, so there is
    nothing to look up and no way for a source edit to invalidate it.
  * Nothing is regenerated. A live change moves 4 vertices and rewrites a
    matrix; the mesh, its UVs, its Color 1 attribute and its material are all
    untouched. That also means a rebuild can never fail halfway and leave a
    decal without a material.

Like Fake Damage, this uses **no bpy.ops at all** - Blender warns against
calling operators from property update callbacks, which run mid-UI-interaction.
"""

import contextlib

import bmesh
import bpy
from mathutils import Vector

from . import geometry
from . import sollumz_integration as szi

# Guards against a rebuild triggering another rebuild through the same
# property callbacks.
_rebuilding = False


@contextlib.contextmanager
def suppress_rebuild():
    """Write a decal's settings without triggering the live rebuild.

    Needed when the create operator stamps its settings onto a freshly built
    decal: each assignment fires the update callback, and an unsuppressed
    rebuild there would move the decal before the operator has finished setting
    it up.
    """
    global _rebuilding
    previous = _rebuilding
    _rebuilding = True
    try:
        yield
    finally:
        _rebuilding = previous


def _frame(data):
    """The stored surface frame as Vectors."""
    return (
        Vector(data.frame_center),
        Vector(data.frame_normal),
        Vector(data.frame_x),
        Vector(data.frame_y),
    )


def _leaves_anchor_face(data):
    """Cheap test for "the offsets have pushed this past its own face".

    Compares against the face's bounding box in its own frame, which needs no
    mesh access at all - the box was measured once at creation. Only when this
    says yes is the source mesh opened for the real walk, so dragging a decal
    around inside its face costs nothing even on a 100k-face MLO.

    Conservative in the safe direction: on a triangle a point can be outside the
    face but still inside the box, in which case the decal simply stays put.
    """
    return abs(data.offset_u) > data.extent_u or abs(data.offset_v) > data.extent_v


def _walk(data, target):
    """Follow the surface to `target`, crossing onto neighbouring faces.

    Returns (center, normal, base_x, base_y) for wherever the decal ended up, or
    None to fall back to the stored frame. Nothing is written back to the decal:
    the walk is recomputed from the stored anchor and the current offsets every
    time, which keeps it a pure function of the values on the slider. Rewriting
    the offsets mid-drag would fight the slider the user is holding.
    """
    source = data.source_object
    if source is None or source.type != 'MESH':
        return None
    if source.mode == 'EDIT':
        # obj.data is stale while its bmesh is open in Edit Mode.
        return None

    bm = bmesh.new()
    try:
        bm.from_mesh(source.data)
        bm.faces.ensure_lookup_table()

        result = geometry.walk_across_faces(bm, source.matrix_world,
                                            data.face_index, target)
        if result is None:
            return None

        face_index, point = result
        frame = geometry.face_frame(bm, source.matrix_world, face_index)
        if frame is None:
            return None

        _, normal, base_x, base_y, _extent = frame
        return point, normal, base_x, base_y
    finally:
        bm.free()


def rebuild(obj):
    """Reposition and resize `obj` from its stored frame and current settings.

    Returns a short status string for the panel, or None when everything is
    fine. Never raises: this runs from a UI callback, where an exception would
    surface as a traceback in the console on every mouse move.
    """
    global _rebuilding
    if _rebuilding:
        return None

    data = obj.seto_decal_data
    center, normal, base_x, base_y = _frame(data)

    if normal.length <= 1e-6:
        return "This decal has no stored surface frame - it predates live editing."

    _rebuilding = True
    try:
        if not geometry.set_quad_size(obj.data, data.width, data.height):
            return "Mesh is no longer a 4-vertex decal quad - it cannot be resized."

        if not geometry.set_quad_alpha(obj.data, data.alpha, szi.get_color_attr_name(0)):
            return "Mesh has no 'Color 1' attribute - opacity cannot be applied."

        # Offset U/V are folded into `position` here, and into the walk below, so
        # compose_matrix is always handed a final point and zero offsets - never
        # the offsets a second time.
        position = center + base_x * data.offset_u + base_y * data.offset_v
        status = None

        if _leaves_anchor_face(data):
            walked = _walk(data, position)
            if walked is not None:
                position, normal, base_x, base_y = walked
            elif data.source_object is not None:
                status = "Source mesh unavailable - the decal cannot cross onto its neighbours."

        obj.matrix_world = geometry.compose_matrix(
            position, normal, base_x, base_y,
            rotation=data.rotation,
            offset_u=0.0,
            offset_v=0.0,
            surface_offset=data.surface_offset,
        )
        return status
    finally:
        _rebuilding = False


def _on_setting_changed(self, context):
    """Property update callback - `self` is the per-object PropertyGroup."""
    obj = getattr(self, "id_data", None)
    if obj is None or not isinstance(obj, bpy.types.Object):
        return
    if _rebuilding or not self.is_seto_decal or not self.live_update:
        return
    self.status = rebuild(obj) or ""


def store_placement(obj, placement, source_object, texture_stem, alpha=1.0,
                    texture_path=""):
    """Stamp a freshly created decal with everything it needs to edit itself."""
    with suppress_rebuild():
        data = obj.seto_decal_data
        data.is_seto_decal = True
        data.source_object = source_object
        data.texture_stem = texture_stem
        data.texture_path = texture_path
        data.alpha = alpha

        data.frame_center = placement.center
        data.frame_normal = placement.normal
        data.frame_x = placement.base_x
        data.frame_y = placement.base_y
        data.face_index = placement.face_index

        min_u, max_u, min_v, max_v = placement.extent
        data.extent_u = max(abs(min_u), abs(max_u))
        data.extent_v = max(abs(min_v), abs(max_v))

        data.width = placement.width
        data.height = placement.height
        data.surface_offset = placement.surface_offset
        data.rotation = placement.rotation
        data.offset_u = placement.offset_u
        data.offset_v = placement.offset_v


class SETO_PG_decal_object(bpy.types.PropertyGroup):
    is_seto_decal: bpy.props.BoolProperty(
        name="Is Seto Decal",
        description="Marks an object as generated by this tool, so the panel knows to show its settings",
        default=False,
    )
    source_object: bpy.props.PointerProperty(
        name="Source",
        description="The mesh this decal was placed on. Kept for reference only - the decal carries its own surface frame",
        type=bpy.types.Object,
    )
    texture_stem: bpy.props.StringProperty(
        name="Texture",
        description="Decal texture this object was created with",
        default="",
    )
    texture_path: bpy.props.StringProperty(
        name="Texture Path",
        description="File the decal texture came from, used to show its thumbnail",
        default="",
        subtype='FILE_PATH',
    )
    live_update: bpy.props.BoolProperty(
        name="Live Update",
        description="Move and resize the decal immediately whenever a setting below changes",
        default=True,
    )
    status: bpy.props.StringProperty(
        name="Status",
        description="Why the last update could not run, if it could not",
        default="",
    )

    # The surface frame the decal was placed on, in world space. Stored as plain
    # vectors so the decal is fully self-contained: it never has to look at the
    # source mesh again, and editing that mesh cannot invalidate it.
    frame_center: bpy.props.FloatVectorProperty(name="Frame Center", size=3, subtype='XYZ')
    frame_normal: bpy.props.FloatVectorProperty(name="Frame Normal", size=3, subtype='XYZ')
    frame_x: bpy.props.FloatVectorProperty(name="Frame X", size=3, subtype='XYZ')
    frame_y: bpy.props.FloatVectorProperty(name="Frame Y", size=3, subtype='XYZ')
    # How far the original face reached from its center. Doubles as the cheap
    # "have the offsets left this face?" test that decides whether the source
    # mesh has to be opened for a surface walk.
    extent_u: bpy.props.FloatProperty(name="Extent U", default=1.0)
    extent_v: bpy.props.FloatProperty(name="Extent V", default=1.0)
    face_index: bpy.props.IntProperty(
        name="Face Index",
        description=(
            "Index of the source face this decal was placed on. Used as the starting "
            "point when sliding it far enough to cross onto a neighbouring face"
        ),
        default=-1,
    )

    width: bpy.props.FloatProperty(
        name="Width",
        description="Size of the decal along its local X axis",
        default=1.0, min=0.0001, soft_max=10.0, subtype='DISTANCE',
        update=_on_setting_changed,
    )
    height: bpy.props.FloatProperty(
        name="Height",
        description="Size of the decal along its local Y axis (up, on a wall)",
        default=1.0, min=0.0001, soft_max=10.0, subtype='DISTANCE',
        update=_on_setting_changed,
    )
    surface_offset: bpy.props.FloatProperty(
        name="Surface Offset",
        description="How far the decal is lifted off the surface along its normal, to stop z-fighting",
        default=0.003, min=0.0001, soft_max=0.05, subtype='DISTANCE',
        update=_on_setting_changed,
    )
    rotation: bpy.props.FloatProperty(
        name="Rotation",
        description="Rotation around the surface normal - spins the decal in place without sliding it",
        default=0.0, subtype='ANGLE',
        update=_on_setting_changed,
    )
    offset_u: bpy.props.FloatProperty(
        name="Offset U",
        description="Slide the decal across the surface, along the face's first axis",
        default=0.0, subtype='DISTANCE',
        update=_on_setting_changed,
    )
    offset_v: bpy.props.FloatProperty(
        name="Offset V",
        description="Slide the decal across the surface, along the face's second axis",
        default=0.0, subtype='DISTANCE',
        update=_on_setting_changed,
    )
    alpha: bpy.props.FloatProperty(
        name="Alpha",
        description=(
            "Alpha of the Color 1 vertex colour, applied evenly to all four corners. "
            "decal.sps renders as 'Color 1 alpha x texture alpha', so 1.0 is as opaque "
            "as the texture allows and lower values fade the whole decal out"
        ),
        default=1.0, min=0.0, max=1.0, subtype='FACTOR',
        update=_on_setting_changed,
    )


class SETO_OT_decal_rebuild(bpy.types.Operator):
    """Apply this decal's settings now"""
    bl_idname = "seto.decal_rebuild"
    bl_label = "Update Now"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.seto_decal_data.is_seto_decal

    def execute(self, context):
        obj = context.active_object
        message = rebuild(obj)
        obj.seto_decal_data.status = message or ""
        if message:
            self.report({'WARNING'}, message)
            return {'CANCELLED'}
        self.report({'INFO'}, f"Updated '{obj.name}'.")
        return {'FINISHED'}


class SETO_OT_decal_reset_position(bpy.types.Operator):
    """Move this decal back to the center of the face it was placed on"""
    bl_idname = "seto.decal_reset_position"
    bl_label = "Center on Face"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.seto_decal_data.is_seto_decal

    def execute(self, context):
        obj = context.active_object
        data = obj.seto_decal_data
        with suppress_rebuild():
            data.offset_u = 0.0
            data.offset_v = 0.0
        data.status = rebuild(obj) or ""
        return {'FINISHED'}


_classes = (
    SETO_PG_decal_object,
    SETO_OT_decal_rebuild,
    SETO_OT_decal_reset_position,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.seto_decal_data = bpy.props.PointerProperty(type=SETO_PG_decal_object)


def unregister():
    del bpy.types.Object.seto_decal_data
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
