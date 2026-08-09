"""The buttons.

START PAINT is one press from wall to painting: it spawns the dirt shell (a
dense paint mesh floating just above the surface), gives it the selected decal
texture, and drops into Vertex Paint with the brush in alpha mode. Nothing on
the wall itself is ever created or modified - removing the shell removes the
dirt, which is what makes the whole tool safe to experiment with.
"""

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

from . import brush
from . import library
from . import shell


def _mesh_object(context):
    obj = context.active_object
    if obj is None or obj.type != 'MESH':
        return None
    return obj


def _find_view3d(context):
    space = getattr(context, "space_data", None)
    if space is not None and getattr(space, "type", "") == 'VIEW_3D':
        return space
    screen = getattr(context, "screen", None)
    if screen is None:
        return None
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            return area.spaces.active
    return None


def _enter_material_shading(context, settings):
    space = _find_view3d(context)
    if space is None:
        return
    shading = space.shading
    if shading.type in {'MATERIAL', 'RENDERED'}:
        settings.previous_shading = ""
        return
    settings.previous_shading = shading.type
    shading.type = 'MATERIAL'


def _restore_shading(context, settings):
    if not settings.previous_shading:
        return
    space = _find_view3d(context)
    if space is not None and space.shading.type == 'MATERIAL':
        space.shading.type = settings.previous_shading
    settings.previous_shading = ""


def _make_active(context, obj):
    # Only rescue an object that belongs to no collection at all. Asking the
    # view layer instead looks right and is not: a freshly linked object is not
    # in view_layer.objects until the depsgraph catches up, so this linked it a
    # second time - one object in two collections, drawn twice in the outliner,
    # which reads as the tool spawning two meshes.
    if not obj.users_collection:
        context.scene.collection.objects.link(obj)

    # A hidden or unselectable object cannot become the active object, and
    # mode_set then fails with "Context missing active object" - which reads
    # like a bug in the tool rather than "the thing you asked to paint is
    # hidden". Asking to paint it is asking to see it.
    obj.hide_viewport = False
    obj.hide_select = False
    try:
        obj.hide_set(False, view_layer=context.view_layer)
    except TypeError:
        obj.hide_set(False)

    # The collection it lives in can be hidden too, which hides the object with
    # it however visible the object itself is.
    _reveal_collections(context, obj)

    for other in context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _reveal_collections(context, obj):
    """Un-hide any layer collection that is hiding `obj`."""
    holders = {collection.name for collection in obj.users_collection}
    if not holders:
        return

    def walk(layer_collection):
        if layer_collection.collection.name in holders:
            if layer_collection.exclude:
                layer_collection.exclude = False
            if layer_collection.hide_viewport:
                layer_collection.hide_viewport = False
            if layer_collection.collection.hide_viewport:
                layer_collection.collection.hide_viewport = False
        for child in layer_collection.children:
            walk(child)

    walk(context.view_layer.layer_collection)


class SETO_OT_surface_refresh_library(bpy.types.Operator):
    bl_idname = "seto.surface_refresh_library"
    bl_label = "Refresh Texture Library"
    bl_description = "Rescan the texture library folder"
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.seto_surface
        from . import properties
        categories, textures = library.scan(settings.custom_library_path)
        properties.rebuild_browser(settings)
        if not textures:
            self.report({'WARNING'}, f"No textures found in {library.get_root()}")
        else:
            self.report({'INFO'},
                        f"{textures} texture(s) in {categories} category/categories.")
        return {'FINISHED'}


def _load_image(path):
    """Load a library texture, reusing it if Blender already has it.

    Only the texture actually being painted ever enters the file - browsing the
    library costs nothing, because the picker reads thumbnails straight from
    disk rather than importing every file into bpy.data.images.

    The filepath is left exactly as loaded, because Sollumz exports the texture
    name from the file name - so the datablock has to keep pointing at the real
    file for the .ydr to reference the right TXD entry.
    """
    image = bpy.data.images.load(path, check_existing=True)
    try:
        image.alpha_mode = 'STRAIGHT'
        image.colorspace_settings.name = 'sRGB'
    except (TypeError, AttributeError):
        # Some .dds variants reject one of these; not worth failing over.
        pass
    return image


def _image_identity(image):
    """(stem, absolute path) for an image datablock, as Sollumz will name it."""
    import os
    filepath = bpy.path.abspath(image.filepath) if image.filepath else ""
    stem = os.path.splitext(os.path.basename(filepath))[0] if filepath else ""
    return (stem or os.path.splitext(image.name)[0]), filepath


class SETO_OT_surface_start_paint(bpy.types.Operator):
    bl_idname = "seto.surface_start_paint"
    bl_label = "Start Paint"
    bl_description = (
        "Spawn the paint mesh over this surface (or reuse the existing one) and "
        "start painting dirt on it. The surface itself is never modified"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _mesh_object(context) is not None

    def execute(self, context):
        settings = context.scene.seto_surface
        obj = _mesh_object(context)
        if obj is None:
            self.report({'ERROR'}, "Select a mesh object first.")
            return {'CANCELLED'}

        # A pointer to a shell the user deleted with X keeps its datablock
        # alive; drop it so the ghost can actually be purged below.
        if settings.paint_object is not None and not settings.paint_object.users_collection:
            settings.paint_object = None

        wall, existing = shell.resolve(obj)
        if wall is None:
            self.report({'ERROR'}, "This dirt shell's wall no longer exists.")
            return {'CANCELLED'}

        shell.purge_orphans(wall)

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Which layer to paint. A shell stays married to its texture: if the
        # dropdown points at a different texture than the selected shell,
        # that is a request for a NEW layer on top, not a retexture of the
        # strokes already made.
        try:
            stem, path = library.resolve_texture(settings.category,
                                                 settings.texture)
        except library.LibraryError as e:
            stem, path = "", ""
            if existing is None:
                self.report({'ERROR'}, f"Pick a texture first. {e}")
                return {'CANCELLED'}

        if existing is not None and stem and shell.texture_stem_of(existing) != stem:
            existing = shell.find_by_texture(wall, stem)

        created = False
        if existing is None:
            index = len(shell.find_shells(wall))
            try:
                existing = shell.create(
                    wall, stem, path,
                    spacing=settings.shell_spacing,
                    # Each layer floats a step higher than the one below, so
                    # stacked layers draw in order instead of z-fighting.
                    surface_offset=settings.shell_offset * (index + 1),
                    index=index,
                )
            except (shell.ShellError, Exception) as e:
                self.report({'ERROR'}, str(e))
                return {'CANCELLED'}
            created = True
        else:
            shell.adopt(existing)
            # Repair a shell that an older version linked into two collections.
            if shell.tidy_links(existing, wall):
                self.report({'INFO'},
                            "This layer was linked into two collections - "
                            "that is why it looked like two. Fixed.")

        settings.paint_object = existing
        _make_active(context, existing)

        try:
            bpy.ops.object.mode_set(mode='VERTEX_PAINT')
        except RuntimeError as e:
            self.report({'ERROR'}, f"Could not enter Vertex Paint mode: {e}")
            return {'CANCELLED'}

        _enter_material_shading(context, settings)
        ok, message = brush.apply_alpha(context, settings)
        if not ok:
            self.report({'WARNING'}, message)

        layer = shell.texture_stem_of(existing) or "layer"
        verb = "New layer" if created else "Painting layer"
        self.report({'INFO'}, f"{verb} '{layer}' on '{wall.name}'.")
        return {'FINISHED'}


class SETO_OT_surface_paint_layer(bpy.types.Operator):
    bl_idname = "seto.surface_paint_layer"
    bl_label = "Paint This Layer"
    bl_description = "Switch to this layer and paint it"
    bl_options = {'REGISTER', 'UNDO'}

    shell_name: bpy.props.StringProperty(default="")

    def execute(self, context):
        target = bpy.data.objects.get(self.shell_name)
        if target is None or not shell.is_shell(target):
            self.report({'ERROR'}, "That layer no longer exists.")
            return {'CANCELLED'}
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        _make_active(context, target)

        settings = context.scene.seto_surface
        settings.paint_object = target
        shell.adopt(target)
        try:
            bpy.ops.object.mode_set(mode='VERTEX_PAINT')
        except RuntimeError as e:
            self.report({'ERROR'}, f"Could not enter Vertex Paint mode: {e}")
            return {'CANCELLED'}
        _enter_material_shading(context, settings)
        brush.apply_alpha(context, settings)
        self.report({'INFO'},
                    f"Painting layer '{shell.texture_stem_of(target)}'.")
        return {'FINISHED'}


class SETO_OT_surface_stop_paint(bpy.types.Operator):
    bl_idname = "seto.surface_stop_paint"
    bl_label = "Stop Paint"
    bl_description = "Leave paint mode. The dirt shell and everything painted on it are kept"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.seto_surface

        if context.mode == 'PAINT_VERTEX':
            bpy.ops.object.mode_set(mode='OBJECT')

        if settings.paint_object is not None and shell.is_shell(settings.paint_object):
            shell.disable_ghost(settings.paint_object)
        settings.paint_object = None
        _restore_shading(context, settings)
        self.report({'INFO'}, "Stopped. The dirt shell keeps everything you painted.")
        return {'FINISHED'}


class SETO_OT_surface_clear_mask(bpy.types.Operator):
    bl_idname = "seto.surface_clear_mask"
    bl_label = "Clear Dirt"
    bl_description = "Wipe every stroke off the paint mesh. The mesh itself stays for repainting"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = _mesh_object(context)
        if obj is None:
            return False
        _, existing = shell.resolve(obj)
        return existing is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        obj = _mesh_object(context)
        _, existing = shell.resolve(obj)
        if existing is None or not shell.clear(existing):
            self.report({'WARNING'}, "No paint mesh to clear.")
            return {'CANCELLED'}
        existing.seto_surface_data.dirt_opacity = 1.0
        self.report({'INFO'}, "Dirt cleared.")
        return {'FINISHED'}


class SETO_OT_surface_remove_shell(bpy.types.Operator):
    bl_idname = "seto.surface_remove_shell"
    bl_label = "Remove Paint Mesh"
    bl_description = (
        "Delete the paint mesh and everything painted on it, leaving the wall "
        "exactly as it always was"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = _mesh_object(context)
        if obj is None:
            return False
        _, existing = shell.resolve(obj)
        return existing is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        settings = context.scene.seto_surface
        obj = _mesh_object(context)
        wall, existing = shell.resolve(obj)
        if existing is None:
            return {'CANCELLED'}

        if context.mode == 'PAINT_VERTEX':
            bpy.ops.object.mode_set(mode='OBJECT')
        if settings.paint_object == existing:
            settings.paint_object = None
            _restore_shading(context, settings)

        shell.disable_ghost(existing)
        shell.remove(existing)
        if wall is not None:
            _make_active(context, wall)
        self.report({'INFO'}, "Paint mesh removed. The wall was never touched.")
        return {'FINISHED'}


class SETO_OT_surface_optimize_layer(bpy.types.Operator):
    bl_idname = "seto.surface_optimize_layer"
    bl_label = "Optimize"
    bl_description = (
        "Remove the vertices the painting does not need, keeping the texture "
        "exactly as it is. Detail lives at the edge of a stroke; the middle of "
        "a painted area and the untouched wall around it do not need geometry. "
        "Pixel-identical to what you painted - unlike baking, which flattens "
        "the texture and always costs sharpness"
    )
    bl_options = {'REGISTER', 'UNDO'}

    tolerance: bpy.props.FloatProperty(
        name="Detail",
        description=(
            "How much of the stroke's shape to keep. Higher strips more "
            "geometry. The texture is never affected"
        ),
        default=0.02, min=0.001, max=0.25, subtype='FACTOR',
    )

    @classmethod
    def poll(cls, context):
        obj = _mesh_object(context)
        if obj is None:
            return False
        _, existing = shell.resolve(obj)
        return existing is not None

    def invoke(self, context, event):
        # Seeded from the panel, because background mode never calls invoke and
        # the operator has to work either way.
        if not self.properties.is_property_set("tolerance"):
            self.tolerance = context.scene.seto_surface.optimize_detail
        return self.execute(context)

    def execute(self, context):
        obj = _mesh_object(context)
        _, existing = shell.resolve(obj)
        if existing is None:
            return {'CANCELLED'}

        if context.mode == 'PAINT_VERTEX':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Triangles, not faces, are what the game pays for - an ngon is free to
        # make and still costs its fan on export - so that is what is reported.
        def triangles(obj):
            return sum(len(polygon.vertices) - 2 for polygon in obj.data.polygons)

        tris_before = triangles(existing)
        before, after = shell.optimize_mesh(existing, tolerance=self.tolerance)
        if after >= before:
            self.report({'INFO'},
                        "Nothing to remove - every vertex is on a stroke edge.")
            return {'CANCELLED'}

        self.report({'INFO'},
                    f"{tris_before} tris down to {triangles(existing)} "
                    f"({after} faces), texture untouched, origin centred.")
        return {'FINISHED'}


class SETO_OT_surface_move_dirt(bpy.types.Operator):
    bl_idname = "seto.surface_move_dirt"
    bl_label = "Place On Surface"
    bl_description = (
        "Drag the dirt around with the mouse instead of typing offsets. The "
        "texture follows the pointer exactly, at any Width, Height or "
        "Rotation, and keeps following it past the edge of the surface. The "
        "wheel resizes it around the pointer without letting go of the drag "
        "(hold Shift for fine steps), X or Y locks to one axis, click keeps "
        "it, Escape or right-click puts it back"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = _mesh_object(context)
        if obj is None:
            return False
        _, existing = shell.resolve(obj)
        return existing is not None

    def _viewport_under_mouse(self, context, event):
        """The 3D window region the cursor is actually over, and its view.

        Not `context.region`: when the operator is launched from a button, that
        is the N-panel's own region, and mapping the cursor through it aims the
        ray at nothing. The cursor has to be located against the window region
        of the viewport it is really over.
        """
        for area in context.window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for region in area.regions:
                if region.type != 'WINDOW':
                    continue
                if (region.x <= event.mouse_x < region.x + region.width
                        and region.y <= event.mouse_y < region.y + region.height):
                    return region, area.spaces.active.region_3d
        return None, None

    def _uv_under_mouse(self, context, event):
        """Where the cursor is, in the layer's base UV space.

        On the mesh this is read off the surface itself, so the decal follows a
        wall that bends. Off the mesh it falls back to the projection plane the
        UVs were made from, which carries on past the edge of the wall - the
        drag has to keep working out there, or the decal cannot be pushed to a
        corner, over a gap, or half off the edge on purpose.
        """
        region, rv3d = self._viewport_under_mouse(context, event)
        if region is None or rv3d is None:
            return None

        coord = (event.mouse_x - region.x, event.mouse_y - region.y)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)

        matrix = self._shell.matrix_world.inverted()
        local_origin = matrix @ origin
        local_direction = (matrix.to_3x3() @ direction).normalized()

        hit, location, _, face_index = self._shell.ray_cast(
            local_origin, local_direction)
        if hit:
            on_surface = shell.uv_at_point(self._shell, face_index, location)
            if on_surface is not None:
                return on_surface

        if self._mapping is None:
            return None
        return shell.uv_for_ray(self._mapping, local_origin, local_direction)

    def invoke(self, context, event):
        obj = _mesh_object(context)
        _, existing = shell.resolve(obj)
        if existing is None:
            return {'CANCELLED'}

        self._shell = existing
        data = existing.seto_surface_data
        self._start = (data.dirt_offset_u, data.dirt_offset_v)
        # No anchor yet: the button that launched this is in the panel, so the
        # cursor is not over the viewport at all. It is picked up on the first
        # move inside one, so the texture never jumps as the pointer arrives.
        self._anchor = None
        self._axis = None
        # Worked out once: the mesh does not change while the drag runs, and
        # the fit is the only expensive part of following the pointer.
        self._mapping = shell.projection_map(existing)

        # A grab, so the grab cursor - it reads as "this is stuck to the
        # pointer now", which is exactly what it does.
        context.window.cursor_modal_set('HAND')
        self._status(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _status(self, context):
        """Live readout, so the drag is not a guess about where it landed."""
        data = self._shell.seto_surface_data
        axis = {None: "free", 'X': "X only", 'Y': "Y only"}[self._axis]
        context.workspace.status_text_set(
            "Drag the texture over the surface   "
            f"[{axis}]  X {data.dirt_offset_u:.3f}  Y {data.dirt_offset_v:.3f}  "
            f"Size {data.dirt_width:.2f} x {data.dirt_height:.2f}   "
            "|  Wheel: resize (Shift: fine)  |  X/Y: lock axis  "
            "|  Click: confirm  |  Esc: cancel")

    def _finish(self, context):
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)

    def modal(self, context, event):
        data = self._shell.seto_surface_data

        # Axis lock, the way every other Blender transform does it. Pressing it
        # again releases. The anchor is re-grabbed at the current spot so the
        # decal does not jump by whatever was dragged on the axis being locked.
        if event.type in {'X', 'Y'} and event.value == 'PRESS':
            self._axis = None if self._axis == event.type else event.type
            current = self._uv_under_mouse(context, event)
            if current is not None:
                self._anchor = current
                self._start = (data.dirt_offset_u, data.dirt_offset_v)
            self._status(context)
            return {'RUNNING_MODAL'}

        # The wheel resizes without letting go of the drag. It scales about the
        # pointer rather than about the middle of the wall, so the spot being
        # worked on stays put instead of sliding away as the decal grows.
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.value != 'RELEASE':
            # Multiplicative, because scale is: a step means "10% bigger", not
            # "0.1 wider", so it behaves the same at any size. Shift for fine.
            step = 1.02 if event.shift else 1.1
            if event.type == 'WHEELDOWNMOUSE':
                step = 1.0 / step

            # Clamped to the sliders' own limits, read off the property rather
            # than repeated here, so the wheel can never reach a size the panel
            # would refuse - or be silently clamped to a different one.
            limits = data.bl_rna.properties["dirt_width"]
            width = min(max(data.dirt_width * step, limits.hard_min), limits.hard_max)
            height = min(max(data.dirt_height * step, limits.hard_min), limits.hard_max)

            point = self._uv_under_mouse(context, event) or self._anchor
            if point is not None:
                offset_u, offset_v = shell.offset_for_scale(
                    (data.dirt_offset_u, data.dirt_offset_v), point,
                    (data.dirt_width, data.dirt_height), (width, height),
                    data.dirt_rotation)
                data.dirt_offset_u = offset_u
                data.dirt_offset_v = offset_v

            data.dirt_width = width
            data.dirt_height = height

            # The drag is still running, and both the offsets and the size it
            # was working from have just changed. Re-grab here or the next
            # mouse move would apply the old baseline and jump.
            if point is not None:
                self._anchor = point
            self._start = (data.dirt_offset_u, data.dirt_offset_v)
            self._status(context)
            return {'RUNNING_MODAL'}

        if event.type == 'MOUSEMOVE':
            current = self._uv_under_mouse(context, event)
            if current is None:
                return {'RUNNING_MODAL'}
            if self._anchor is None:
                # First contact with the surface: grab it here, so the texture
                # does not jump the moment the cursor arrives.
                self._anchor = current
                self._start = (data.dirt_offset_u, data.dirt_offset_v)
                return {'RUNNING_MODAL'}

            # Both the anchor and the current point are read from the base UVs,
            # which nothing here changes, so the reference cannot slide out
            # from under the drag. offset_for_drag then undoes the size and
            # rotation, which is what makes the texture sit under the pointer
            # at any Width, Height or Rotation instead of racing ahead of it.
            offset_u, offset_v = shell.offset_for_drag(
                self._start, self._anchor, current,
                data.dirt_width, data.dirt_height, data.dirt_rotation)

            if self._axis != 'Y':
                data.dirt_offset_u = offset_u
            if self._axis != 'X':
                data.dirt_offset_v = offset_v
            self._status(context)
            return {'RUNNING_MODAL'}

        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            self._finish(context)
            if self._anchor is None:
                self.report({'INFO'}, "Nothing moved - the cursor never entered a 3D viewport.")
                return {'CANCELLED'}
            return {'FINISHED'}

        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            data.dirt_offset_u, data.dirt_offset_v = self._start
            self._finish(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}


class SETO_OT_surface_toggle_ghost(bpy.types.Operator):
    bl_idname = "seto.surface_toggle_ghost"
    bl_label = "Preview Texture"
    bl_description = (
        "Show the whole texture semi-transparent over the surface - like "
        "Substance Painter's projection - so it can be positioned with the "
        "sliders before painting. Strokes and export are never affected"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = _mesh_object(context)
        if obj is None:
            return False
        _, existing = shell.resolve(obj)
        return existing is not None

    def execute(self, context):
        settings = context.scene.seto_surface
        obj = _mesh_object(context)
        _, existing = shell.resolve(obj)
        if existing is None:
            return {'CANCELLED'}
        try:
            if shell.has_ghost(existing):
                shell.disable_ghost(existing)
                self.report({'INFO'}, "Preview off - only your strokes show.")
            else:
                shell.enable_ghost(existing, settings.ghost_strength)
                self.report({'INFO'},
                            "Previewing the texture. Position it, then paint.")
        except shell.ShellError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}


class SETO_OT_surface_toggle_normal(bpy.types.Operator):
    bl_idname = "seto.surface_toggle_normal"
    bl_label = "Toggle Normal Map"
    bl_description = (
        "Add a normal map slot to the dirt (normal_decal shader), or go back to "
        "the plain decal shader. The painted mask is untouched either way"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = _mesh_object(context)
        if obj is None:
            return False
        _, existing = shell.resolve(obj)
        return existing is not None

    def execute(self, context):
        settings = context.scene.seto_surface
        obj = _mesh_object(context)
        _, existing = shell.resolve(obj)
        if existing is None:
            return {'CANCELLED'}

        try:
            if shell.has_normal_map(existing):
                stem = shell.texture_stem_of(existing)
                path = library.texture_path(settings.category, stem)
                if not path:
                    stem, path = library.resolve_texture(settings.category,
                                                         settings.texture)
                shell.disable_normal_map(existing, stem, path)
                self.report({'INFO'}, "Back to the plain decal shader.")
            else:
                shell.enable_normal_map(existing, settings.texture)
                self.report({'INFO'},
                            "Normal map slot added - load an image into it below.")
        except (shell.ShellError, library.LibraryError, Exception) as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}


_classes = (
    SETO_OT_surface_refresh_library,
    SETO_OT_surface_start_paint,
    SETO_OT_surface_paint_layer,
    SETO_OT_surface_stop_paint,
    SETO_OT_surface_clear_mask,
    SETO_OT_surface_remove_shell,
    SETO_OT_surface_optimize_layer,
    SETO_OT_surface_move_dirt,
    SETO_OT_surface_toggle_ghost,
    SETO_OT_surface_toggle_normal,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
