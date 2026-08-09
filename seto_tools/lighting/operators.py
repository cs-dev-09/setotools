"""God ray operators: create, aim, sync, duplicate, delete.

Create God Rays is all-or-nothing by design. It resolves the archetype before
creating anything, and if a later step still fails it removes everything it has
made - objects and archetype extensions alike - so a failed run never leaves the
user with half a setup to clean up by hand.
"""

import bpy
import bmesh
from mathutils import Vector

from . import godray
from . import group
from . import properties
from ..shared import sollumz_integration as szi


def _get_or_create_collection(context, name):
    """Find or create the collection generated setups are gathered into.

    Same rules as the other Seto tools: reuse one we made earlier even if
    Blender had to suffix its name, and never adopt an unrelated collection the
    user already has elsewhere in the scene.
    """
    scene_collection = context.scene.collection
    for child in scene_collection.children:
        if child.name == name or child.name.startswith(name + "."):
            return child
    collection = bpy.data.collections.new(name)
    scene_collection.children.link(collection)
    return collection


def _parent_keep_transform(child, parent):
    """Parent without visually moving the child, whatever the parent's transform."""
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted_safe()


def _select_only(context, obj):
    for other in context.selected_objects:
        if other is not obj:
            other.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _drawable_center(drawable):
    """World-space centre of a drawable's geometry, used to guess which side of
    a wall the room is on. Falls back to the drawable's own origin when it has
    no evaluable children."""
    points = []
    for child in [drawable, *drawable.children_recursive]:
        if child.type != 'MESH' or child.data is None:
            continue
        for corner in child.bound_box:
            points.append(child.matrix_world @ Vector(corner))
    if not points:
        return drawable.matrix_world.translation.copy()
    return sum(points, Vector()) / len(points)


class _Rollback:
    """Undo log for the all-or-nothing create.

    Records every object and archetype extension created, newest first, so a
    failure can unwind them in reverse order.
    """

    def __init__(self):
        self._objects = []
        self._extensions = []

    def add_object(self, obj):
        self._objects.append(obj)

    def add_extension(self, archetype, name):
        self._extensions.append((archetype, name))

    def undo(self):
        for archetype, name in reversed(self._extensions):
            try:
                szi.remove_extension_by_name(archetype, name)
            except Exception:
                pass
        for obj in reversed(self._objects):
            try:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                # Lights own their data-block; leaving it behind would be a leak.
                if data is not None and data.users == 0 and isinstance(data, bpy.types.Light):
                    bpy.data.lights.remove(data)
            except Exception:
                pass


class SETO_OT_create_god_rays(bpy.types.Operator):
    """Build a Sollumz spot light, light shaft and optional dust particle from the selected faces"""

    bl_idname = "seto.create_god_rays"
    bl_label = "Create God Rays"
    bl_options = {'REGISTER', 'UNDO'}

    __annotations__ = dict(properties.settings_annotations())
    __annotations__.update({
        "ray_mode": bpy.props.EnumProperty(
            name="Rays",
            description="How the selected faces are turned into beams",
            items=[
                ('SINGLE', "Single Beam",
                 "One god ray covering everything selected, sized to the whole opening"),
                ('PER_ISLAND', "One Per Gap",
                 "A separate god ray for each connected group of selected faces. This is what "
                 "boarded-up windows want: every gap between the boards gets its own narrow beam"),
            ],
            default='SINGLE',
        ),
        "flip_direction": bpy.props.BoolProperty(
            name="Flip Direction",
            description="Shine the light the other way through the opening. By default the "
                        "direction is guessed from which side of the drawable the room is on",
            default=False,
        ),
        "auto_beam_width": bpy.props.BoolProperty(
            name="Beam Width From Opening",
            description="Derive the cone angle from the size of the selected opening instead "
                        "of using the Beam Width setting. A narrow gap between boards gets a "
                        "narrow beam, a doorway a wide one",
            default=True,
        ),
    })

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and context.mode == 'EDIT_MESH'
                and szi.is_sollumz_available())

    def _seed_from_panel(self, context):
        """Fill in any property the caller did not set, from the N-panel.

        In execute() rather than invoke(), because Blender skips invoke() in
        background mode and the operator must behave the same from a script as
        from the button.
        """
        panel = context.scene.seto_lighting
        for name in properties.SETTING_NAMES:
            if not self.properties.is_property_set(name):
                value = getattr(panel, name)
                if hasattr(value, "__len__") and not isinstance(value, str):
                    value = tuple(value)
                setattr(self, name, value)

    def execute(self, context):
        if not szi.is_sollumz_available():
            self.report({'ERROR'}, "Sollumz is not enabled/available. Seto Lighting requires Sollumz.")
            return {'CANCELLED'}

        self._seed_from_panel(context)

        source = context.active_object
        matrix_world = source.matrix_world.copy()

        # --- read the selection while still in Edit Mode -------------------
        bm = bmesh.from_edit_mesh(source.data)
        skipped = []
        try:
            if self.ray_mode == 'PER_ISLAND':
                face_groups = godray.face_islands(godray.selected_faces(bm))
            else:
                face_groups = [godray.selected_faces(bm)]
            if not any(face_groups):
                raise godray.OpeningError(
                    "No faces selected. Select the window, gap or opening first."
                )
        except godray.OpeningError as e:
            self.report({'ERROR'}, f"Seto Lighting: {e}")
            return {'CANCELLED'}

        # --- resolve the export target BEFORE creating anything ------------
        # An all-or-nothing setup means the archetype must be known to exist
        # first; otherwise we would build a light and then discover there is
        # nowhere to put its shaft.
        try:
            drawable, ytyp, archetype = szi.resolve_archetype_target(source)
        except szi.ArchetypeNotFoundError as e:
            self.report({'ERROR'}, f"Seto Lighting: {e}")
            return {'CANCELLED'}

        # The normal that came off the faces may point out of the building; the
        # drawable's own centre is a reasonable stand-in for "inside". Decided
        # per opening, since a selection can span walls facing different ways.
        # The user can still override the lot with Flip Direction.
        auto_flip = not self.properties.is_property_set("flip_direction")
        reference = _drawable_center(drawable)

        frames = []
        for faces in face_groups:
            try:
                frame = godray.analyze_face_group(faces, matrix_world,
                                                  flip=self.flip_direction)
                if auto_flip and godray.suggest_flip(frame, reference):
                    frame = godray.analyze_face_group(faces, matrix_world, flip=True)
                frames.append(frame)
            except godray.OpeningError as e:
                skipped.append(str(e))

        if not frames:
            reason = skipped[0] if skipped else "the selection does not describe an opening."
            self.report({'ERROR'}, f"Seto Lighting: {reason}")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='OBJECT')

        # One rollback for the whole run: if the fourth beam fails, the first
        # three are removed too. A half-finished Multi Ray is exactly the kind
        # of mess all-or-nothing exists to prevent.
        rollback = _Rollback()
        created = []
        try:
            for frame in frames:
                created.append(
                    self._build(context, drawable, ytyp, archetype, frame, rollback)
                )
        except Exception as e:
            rollback.undo()
            self.report({'ERROR'}, f"Seto Lighting: setup failed and was rolled back - {e}")
            return {'CANCELLED'}

        last_root = created[-1]
        _select_only(context, last_root)
        szi.tag_redraw_ytyp(context)

        # Feed the values that produced this result back to the panel, so a
        # tweak made in the F9 panel becomes the starting point for the next
        # god ray instead of silently reverting.
        properties.copy_settings(last_root.seto_godray, context.scene.seto_lighting)

        if len(created) == 1:
            data = last_root.seto_godray
            message = (f"Created '{last_root.name}' on archetype '{archetype.name}'. "
                       f"Opening {data.opening_width:.2f} x {data.opening_height:.2f} m.")
        else:
            message = (f"Created {len(created)} god rays "
                       f"('{created[0].name}' to '{last_root.name}') "
                       f"on archetype '{archetype.name}'.")
        if skipped:
            message += f" Skipped {len(skipped)} unusable selection group(s)."
        self.report({'INFO'}, message)
        return {'FINISHED'}

    def _build(self, context, drawable, ytyp, archetype, frame, rollback):
        """Build one god ray from one opening. Returns its root Empty."""
        group_name = group.next_group_name()
        collection = _get_or_create_collection(context, group.COLLECTION_NAME)

        # --- root empty ----------------------------------------------------
        root = bpy.data.objects.new(group_name, None)
        root.empty_display_type = 'PLAIN_AXES'
        root.empty_display_size = max(frame.width, frame.height) * 0.5 or 0.25
        collection.objects.link(root)
        rollback.add_object(root)
        root.matrix_world = godray.light_matrix(frame)
        _parent_keep_transform(root, drawable)

        # --- spot light ----------------------------------------------------
        # Sollumz's own creation path, so the light is indistinguishable from
        # one made with its Create Light button.
        LightType = szi.get_light_type_enum()
        light = szi.create_gta_light(context, LightType.SPOT.value, location=frame.center)
        rollback.add_object(light)
        light.name = group_name + group.LIGHT_SUFFIX
        light.data.name = light.name
        _parent_keep_transform(light, root)
        light.matrix_world = godray.light_matrix(frame)

        # --- light shaft extension ----------------------------------------
        shaft_name = group_name + group.SHAFT_SUFFIX
        _, shaft = szi.add_light_shaft_extension(archetype, shaft_name)
        rollback.add_extension(archetype, shaft_name)
        placement = godray.shaft_placement(frame, drawable.matrix_world)
        self._write_shaft(shaft.get_properties(), placement)

        # --- dust particle extension --------------------------------------
        dust_name = ""
        if self.add_dust:
            dust_name = group_name + group.DUST_SUFFIX
            _, dust = szi.add_particle_extension(archetype, dust_name, self.dust_fx_name)
            rollback.add_extension(archetype, dust_name)
            dust.get_properties().offset_position = godray.dust_position(
                frame, drawable.matrix_world, self.beam_length * 0.5
            )

        # --- stamp the group ----------------------------------------------
        inv = drawable.matrix_world.inverted_safe()
        with group.suppress_sync():
            data = root.seto_godray
            data.is_godray = True
            data.light_object = light
            data.asset_object = drawable
            data.ytyp_name = ytyp.name
            data.archetype_name = archetype.name
            data.shaft_ext_name = shaft_name
            data.dust_ext_name = dust_name
            data.opening_center = inv @ frame.center
            data.opening_right = inv.to_3x3() @ frame.right
            data.opening_up = inv.to_3x3() @ frame.up
            data.opening_width = frame.width
            data.opening_height = frame.height
            properties.copy_settings(self, data)
            if self.auto_beam_width:
                data.beam_width = godray.cone_angle_for_opening(
                    frame, self.beam_length,
                    minimum=0.0, maximum=properties.MAX_CONE_ANGLE,
                )

        # Now that everything exists and is named, push the masters once.
        # Selection, reporting and feeding values back to the panel are the
        # caller's job - with Multi Ray this runs once per beam.
        group.apply_masters(group.resolve(root), root.seto_godray)
        return root

    def _write_shaft(self, props, placement):
        """Write geometry and the god ray look onto a light shaft extension.

        The flags match a sun shaft: it follows the sun's direction and colour
        and scales with sun intensity, and draws whether the camera is in front
        of it or behind it.
        """
        DensityType, VolumeType = szi.get_light_shaft_enums()

        props.cornerA = placement.cornerA
        props.cornerB = placement.cornerB
        props.cornerC = placement.cornerC
        props.cornerD = placement.cornerD
        props.direction = placement.direction
        props.offset_position = placement.offset_position

        props.density_type = DensityType.QUADRATIC_GRADIENT
        props.volume_type = VolumeType.SHAFT
        props.direction_amount = 1.0
        props.softness = 1.0

        props.flag_0 = True  # Use Sun Direction
        props.flag_1 = True  # Use Sun Color
        props.flag_5 = True  # Scale By Sun Intensity (mirrors scale_by_sun_intensity)
        props.flag_6 = True  # Draw In Front And Behind


class _GodRayOperator:
    """Shared poll for operators that act on an existing god ray group."""

    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and group.find_group_root(obj) is not None

    def get_refs(self, context):
        root = group.find_group_root(context.active_object)
        return root, group.resolve(root)


class SETO_OT_godray_sync_shaft(_GodRayOperator, bpy.types.Operator):
    """Rebuild the light shaft from the spot light's current position and aim"""

    bl_idname = "seto.godray_sync_shaft"
    bl_label = "Sync Light Shaft"

    def execute(self, context):
        root, refs = self.get_refs(context)
        if not refs.has_light:
            self.report({'ERROR'}, "Seto Lighting: this god ray has no spot light to sync from.")
            return {'CANCELLED'}
        if not refs.has_shaft:
            self.report({'ERROR'}, "Seto Lighting: this god ray has no light shaft to sync.")
            return {'CANCELLED'}

        data = root.seto_godray
        drawable = data.asset_object
        asset_matrix = drawable.matrix_world

        # The light shines along its own -Z; that is the direction the shaft
        # must travel. Read from the world matrix so any parent transform on the
        # drawable or the group root is already accounted for.
        light_matrix = refs.light.matrix_world
        forward = -Vector(light_matrix.col[2][:3]).normalized()

        # Transport the stored opening rectangle to where the light now is, so
        # the corners follow the beam instead of being left behind at the
        # geometry the god ray was first generated from.
        right = (asset_matrix.to_3x3() @ Vector(data.opening_right)).normalized()
        up = (asset_matrix.to_3x3() @ Vector(data.opening_up)).normalized()
        center = asset_matrix @ Vector(data.opening_center)

        half_w = data.opening_width * 0.5
        half_h = data.opening_height * 0.5
        frame = godray.OpeningFrame(
            center=center,
            normal=forward,
            right=right,
            up=up,
            width=data.opening_width,
            height=data.opening_height,
            corners=(
                center - right * half_w + up * half_h,
                center + right * half_w + up * half_h,
                center + right * half_w - up * half_h,
                center - right * half_w - up * half_h,
            ),
        )
        placement = godray.shaft_placement(frame, asset_matrix, direction_world=forward)

        props = refs.shaft_props
        props.cornerA = placement.cornerA
        props.cornerB = placement.cornerB
        props.cornerC = placement.cornerC
        props.cornerD = placement.cornerD
        props.direction = placement.direction
        props.offset_position = placement.offset_position

        if refs.has_dust:
            refs.dust_props.offset_position = godray.world_point_to_asset(
                asset_matrix, center + forward * (data.beam_length * 0.5)
            )

        szi.tag_redraw_ytyp(context)
        self.report({'INFO'}, f"Synced light shaft of '{root.name}' to the spot light.")
        return {'FINISHED'}


class SETO_OT_godray_aim_at_selected(_GodRayOperator, bpy.types.Operator):
    """Rotate the spot light to point at the selected geometry, object or 3D cursor"""

    bl_idname = "seto.godray_aim_at_selected"
    bl_label = "Aim At Selected"

    sync_shaft: bpy.props.BoolProperty(
        name="Also Sync Light Shaft",
        description="Update the light shaft direction to match the new aim",
        default=True,
    )

    def _find_target(self, context, root):
        """Where to aim, in world space, in order of preference:
        selected vertices, then any other selected object, then the 3D cursor."""
        obj = context.active_object
        if obj is not None and obj.type == 'MESH' and obj.mode == 'EDIT':
            obj.update_from_editmode()
            selected = [v.co for v in obj.data.vertices if v.select]
            if selected:
                local = sum(selected, Vector()) / len(selected)
                return obj.matrix_world @ local, "selected vertices"

        others = [o for o in context.selected_objects
                  if o is not root and group.find_group_root(o) is not root]
        if others:
            center = sum((o.matrix_world.translation for o in others), Vector()) / len(others)
            return center, f"{len(others)} selected object(s)"

        return context.scene.cursor.location.copy(), "the 3D cursor"

    def execute(self, context):
        root, refs = self.get_refs(context)
        if not refs.has_light:
            self.report({'ERROR'}, "Seto Lighting: this god ray has no spot light to aim.")
            return {'CANCELLED'}

        target, source_desc = self._find_target(context, root)
        light = refs.light
        matrix = godray.aim_matrix(light.matrix_world.translation.copy(), target)
        if matrix is None:
            self.report({'ERROR'},
                        "Seto Lighting: the aim target is at the light's own position, so "
                        "there is no direction to aim in.")
            return {'CANCELLED'}

        # Assigning the world matrix keeps this correct through any parent
        # transform, including a scaled or rotated drawable.
        light.matrix_world = matrix

        message = f"Aimed '{light.name}' at {source_desc}."
        if self.sync_shaft and refs.has_shaft:
            bpy.ops.seto.godray_sync_shaft()
            message += " Light shaft synced."
        self.report({'INFO'}, message)
        return {'FINISHED'}


class SETO_OT_godray_push_masters(_GodRayOperator, bpy.types.Operator):
    """Write every master control onto the GTA properties now"""

    bl_idname = "seto.godray_push_masters"
    bl_label = "Push Masters"

    def execute(self, context):
        root, refs = self.get_refs(context)
        written = group.apply_masters(refs, root.seto_godray)
        if not written:
            self.report({'WARNING'}, f"Seto Lighting: '{root.name}' has no parts left to write to.")
            return {'CANCELLED'}
        szi.tag_redraw_ytyp(context)
        self.report({'INFO'}, f"Pushed master controls onto: {', '.join(written)}.")
        return {'FINISHED'}


class SETO_OT_godray_duplicate(_GodRayOperator, bpy.types.Operator):
    """Duplicate the whole god ray setup - light, light shaft and dust"""

    bl_idname = "seto.godray_duplicate"
    bl_label = "Duplicate Setup"

    def execute(self, context):
        root, refs = self.get_refs(context)
        data = root.seto_godray
        if refs.archetype is None:
            self.report({'ERROR'},
                        "Seto Lighting: cannot duplicate - the archetype this god ray belongs "
                        "to no longer exists.")
            return {'CANCELLED'}

        new_name = group.next_group_name()
        rollback = _Rollback()

        try:
            new_root = root.copy()
            new_root.name = new_name
            for collection in root.users_collection:
                collection.objects.link(new_root)
            rollback.add_object(new_root)

            new_light = None
            if refs.has_light:
                new_light = refs.light.copy()
                new_light.data = refs.light.data.copy()
                new_light.name = new_name + group.LIGHT_SUFFIX
                new_light.data.name = new_light.name
                for collection in refs.light.users_collection:
                    collection.objects.link(new_light)
                new_light.parent = new_root
                new_light.matrix_parent_inverse = refs.light.matrix_parent_inverse.copy()
                rollback.add_object(new_light)

            new_shaft_name = ""
            if refs.has_shaft:
                new_shaft_name = new_name + group.SHAFT_SUFFIX
                szi.duplicate_extension(refs.archetype, data.shaft_ext_name, new_shaft_name)
                rollback.add_extension(refs.archetype, new_shaft_name)

            new_dust_name = ""
            if refs.has_dust:
                new_dust_name = new_name + group.DUST_SUFFIX
                szi.duplicate_extension(refs.archetype, data.dust_ext_name, new_dust_name)
                rollback.add_extension(refs.archetype, new_dust_name)

            with group.suppress_sync():
                new_data = new_root.seto_godray
                new_data.light_object = new_light
                new_data.shaft_ext_name = new_shaft_name
                new_data.dust_ext_name = new_dust_name

        except Exception as e:
            rollback.undo()
            self.report({'ERROR'}, f"Seto Lighting: duplicate failed and was rolled back - {e}")
            return {'CANCELLED'}

        _select_only(context, new_root)
        szi.tag_redraw_ytyp(context)
        self.report({'INFO'}, f"Duplicated '{root.name}' as '{new_name}'.")
        return {'FINISHED'}


class SETO_OT_godray_delete(_GodRayOperator, bpy.types.Operator):
    """Delete this god ray - its light, its light shaft and its dust particle"""

    bl_idname = "seto.godray_delete"
    bl_label = "Delete Setup"

    def execute(self, context):
        root, refs = self.get_refs(context)
        data = root.seto_godray
        name = root.name
        removed = []

        if refs.archetype is not None:
            for ext_name, label in ((data.shaft_ext_name, "light shaft"),
                                    (data.dust_ext_name, "dust")):
                if ext_name and szi.remove_extension_by_name(refs.archetype, ext_name):
                    removed.append(label)

        for obj in [refs.light, root]:
            if obj is None:
                continue
            light_data = obj.data if obj.type == 'LIGHT' else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if light_data is not None and light_data.users == 0:
                bpy.data.lights.remove(light_data)
                removed.append("spot light")

        szi.tag_redraw_ytyp(context)
        self.report({'INFO'}, f"Deleted '{name}' ({', '.join(removed) or 'nothing left to remove'}).")
        return {'FINISHED'}


_classes = (
    SETO_OT_create_god_rays,
    SETO_OT_godray_sync_shaft,
    SETO_OT_godray_aim_at_selected,
    SETO_OT_godray_push_masters,
    SETO_OT_godray_duplicate,
    SETO_OT_godray_delete,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
