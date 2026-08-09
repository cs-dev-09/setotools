import os
import random
import re

import bpy
import bmesh

from . import geometry
from . import library
from . import object_settings
from . import preferences
from ..shared import sollumz_integration as szi

# Generated decals go into "decals", and inside that into one child collection
# per library category, so a scene full of decals stays sorted the same way the
# library on disk is.
DECAL_COLLECTION_NAME = "decals"

# Blender's automatic ".001" suffix, so a collection it had to rename is still
# recognised as ours on the next run instead of spawning ".002", ".003", ...
_SUFFIX_PATTERN = re.compile(r"\.\d{3}$")

# Errors that mean "this decal could not be built"; anything else is a real bug
# and should surface as a traceback rather than being silently swallowed.
_PLACEMENT_ERRORS = (
    szi.SollumzShaderError,
    szi.SollumzUnavailableError,
    szi.TextureLoadError,
    library.DecalLibraryError,
    RuntimeError,
    OSError,
)


def _base_name(name):
    return _SUFFIX_PATTERN.sub("", name)


def _get_or_create_collection(context, name, parent=None):
    """Find or create the collection called `name` under `parent`.

    Reuses one we created earlier even if Blender had to suffix its name (a
    category called "dirt" clashing with an unrelated "dirt" collection would
    otherwise pile up "dirt.001", "dirt.002", ... one per run), and never adopts
    or moves an unrelated collection the user already has in the scene.
    """
    parent = parent or context.scene.collection

    for child in parent.children:
        if _base_name(child.name) == name:
            return child

    existing = bpy.data.collections.get(name)
    if existing is not None and existing is not parent and \
            existing not in context.scene.collection.children_recursive:
        # Exists but is not in this scene (appended, or orphaned) - adopt it.
        parent.children.link(existing)
        return existing

    collection = bpy.data.collections.new(name)
    parent.children.link(collection)
    return collection


def _decal_collection(context, category, drawable_root=None):
    """Where a generated decal is filed.

    Inside a Sollumz Drawable, the decal is part of that asset, so it goes
    beside the rest of it - parenting alone is not enough, an object parented to
    the Drawable but linked elsewhere shows up greyed out under it in the
    outliner and gets left behind by anything working on the Drawable's
    collection.

    Otherwise it goes into "decals", in the category's own child collection.
    Images that sit loose in the library root have no real category, so those
    go straight into "decals" rather than into a folder named after the
    "(root)" placeholder.
    """
    if drawable_root is not None:
        drawable_collections = list(drawable_root.users_collection)
        if drawable_collections:
            return drawable_collections

    root = _get_or_create_collection(context, DECAL_COLLECTION_NAME)
    if not category or category in (library.ROOT_CATEGORY, library.NO_CATEGORY):
        return [root]
    return [_get_or_create_collection(context, category, parent=root)]


def _parent_keep_transform(child, parent):
    """Parent `child` to `parent` without visually moving it, regardless of the
    parent's own transform."""
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


def _rollback(obj, mesh):
    """Remove a half-built decal so a failure never leaves an orphan behind.

    The material is deliberately left alone: it may already be shared with
    decals that succeeded in the same run.
    """
    if obj is not None:
        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)
        bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def _format_failures(failures, limit=3):
    """'dirt_03.png, crack_01.png and 2 more' - keeps the status bar readable."""
    names = [name for name, _ in failures]
    if len(names) <= limit:
        return ", ".join(names)
    return f"{', '.join(names[:limit])} and {len(names) - limit} more"


class SETO_OT_refresh_decal_library(bpy.types.Operator):
    """Rescan the decal library folder for categories and textures"""
    bl_idname = "seto.refresh_decal_library"
    bl_label = "Refresh Library"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            categories, textures = library.scan(preferences.get_library_path())
        except library.DecalLibraryError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        if not textures:
            self.report({'WARNING'}, "Decal library folder contains no usable image files.")
            return {'FINISHED'}

        self.report({'INFO'}, f"Decal library: {categories} category/categories, {textures} texture(s).")
        return {'FINISHED'}


class SETO_OT_create_decal(bpy.types.Operator):
    """Create a separate decal plane on each selected face, aligned to its surface"""
    bl_idname = "seto.create_decal"
    bl_label = "Create Decal"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.seto_decal

        available, status_msg = szi.get_status_message()
        if not available:
            self.report({'ERROR'}, status_msg)
            return {'CANCELLED'}

        source_obj = context.active_object
        if source_obj is None or source_obj.type != 'MESH':
            self.report({'ERROR'}, "No mesh object selected.")
            return {'CANCELLED'}
        if context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Enter Edit Mode and select one or more faces.")
            return {'CANCELLED'}

        if not library.get_categories():
            self.report({'ERROR'}, "Decal library folder does not exist or has no textures. Press Refresh Library.")
            return {'CANCELLED'}
        if not library.get_textures(settings.category):
            self.report({'ERROR'}, f"No textures found in category '{settings.category}'.")
            return {'CANCELLED'}

        # Read the face selection while still in Edit Mode. sample_faces() only
        # reads - it never modifies a bmesh element and never calls
        # bmesh.update_edit_mesh() - so the source mesh stays untouched.
        bm = bmesh.from_edit_mesh(source_obj.data)
        samples, skipped = geometry.sample_faces(
            bm, source_obj.matrix_world, merge_coplanar=settings.merge_coplanar
        )

        if not samples:
            if skipped:
                self.report({'WARNING'}, f"Skipped {skipped} degenerate face(s); nothing left to place a decal on.")
            else:
                self.report({'ERROR'}, "No faces selected.")
            return {'CANCELLED'}

        rng = random.Random()

        try:
            placements = self._build_placements(settings, samples, rng)
        except library.DecalLibraryError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        materials, failures = self._resolve_materials(settings, placements)

        drawable_root = szi.find_drawable_parent(source_obj)
        collections = _decal_collection(context, settings.category, drawable_root)

        created = 0
        drawable_warnings = []
        for placement in placements:
            material = materials.get(placement.texture_path)
            if material is None:
                # Its texture already failed in _resolve_materials; skipping here
                # means no object is ever created for it.
                continue
            if self._create_one(placement, material, collections, drawable_root,
                                failures, drawable_warnings, source_obj, settings):
                created += 1

        return self._report_result(created, failures, skipped, drawable_root,
                                   drawable_warnings, source_obj)

    # ------------------------------------------------------------------ build

    def _build_placements(self, settings, samples, rng):
        """One DecalPlacement per selected face, each randomising independently."""
        placements = []
        for sample in samples:
            stem, path = library.resolve_texture(
                settings.category, settings.texture,
                randomize=settings.random_texture, rng=rng,
            )

            if settings.random_rotation:
                rotation = geometry.random_rotation(rng, settings.rotation_min, settings.rotation_max)
            else:
                rotation = settings.rotation

            if settings.random_scale:
                scale = geometry.random_scale(rng, settings.scale_min, settings.scale_max)
            else:
                scale = 1.0

            placements.append(geometry.build_placement(
                sample,
                width=settings.width * scale,
                height=settings.height * scale,
                surface_offset=settings.surface_offset,
                rotation=rotation,
                texture_stem=stem,
                texture_path=path,
                rng=rng,
                randomize_position=settings.random_position,
            ))
        return placements

    def _resolve_materials(self, settings, placements):
        """Resolve one material per distinct texture BEFORE any geometry exists.

        Doing this up front means the common failure - a missing image or an
        unavailable shader - never gets as far as creating an object, so there is
        nothing to clean up in the first place.

        With material_mode 'NEW' the reuse pass is skipped, but a single run still
        shares one material between decals using the same texture; otherwise five
        random dirt decals that happened to draw the same image would produce five
        identical materials.
        """
        materials = {}
        failures = []
        reuse = settings.material_mode == 'AUTO'

        for placement in placements:
            if placement.texture_path in materials:
                continue
            if any(name == placement.texture_stem for name, _ in failures):
                continue
            try:
                materials[placement.texture_path] = szi.find_or_create_decal_material(
                    placement.texture_stem, placement.texture_path, reuse=reuse,
                )
            except _PLACEMENT_ERRORS as e:
                failures.append((os.path.basename(placement.texture_path), str(e)))

        return materials, failures

    def _create_one(self, placement, material, collections, drawable_root,
                    failures, drawable_warnings, source_obj, settings):
        """Build one decal object. Returns True on success.

        Everything that can fail is inside the try: on any failure the
        half-built object and mesh are removed again, so a failed decal never
        leaves an untextured plane in the scene.
        """
        name = f"seto_decal_{placement.texture_stem}"
        mesh = None
        obj = None
        try:
            # Created fully opaque; the vertex colour alpha is dialled in live
            # afterwards in the Selected Decal section.
            fade = settings.edge_fade
            mesh = geometry.build_decal_mesh(name, placement.width, placement.height, fade)
            szi.write_uv_and_color(
                mesh,
                geometry.decal_loop_uv(placement.width, placement.height, fade),
                geometry.decal_loop_color(placement.width, placement.height, fade),
            )

            obj = bpy.data.objects.new(name, mesh)
            for collection in collections:
                collection.objects.link(obj)
            obj.matrix_world = placement.matrix

            szi.assign_material_to_object(obj, material)

            # Stamp the surface frame and settings onto the object so its own
            # panel can slide, spin and resize it live afterwards.
            object_settings.store_placement(obj, placement, source_obj,
                                            placement.texture_stem,
                                            texture_path=placement.texture_path,
                                            edge_fade=fade)
        except _PLACEMENT_ERRORS as e:
            _rollback(obj, mesh)
            failures.append((os.path.basename(placement.texture_path), str(e)))
            return False

        # Drawable parenting is not part of the rollback contract: a decal that
        # could not join a Drawable is still a perfectly valid decal, so it is
        # kept and only warned about - and it is NOT counted as a failure, which
        # is why these go to their own list.
        if drawable_root is not None:
            try:
                _parent_keep_transform(obj, drawable_root)
                szi.convert_to_drawable_model(obj)
            except Exception as e:
                drawable_warnings.append((obj.name, str(e)))

        return True

    # ----------------------------------------------------------------- report

    def _report_result(self, created, failures, skipped, drawable_root,
                       drawable_warnings, source_obj):
        if created == 0:
            if failures:
                name, reason = failures[0]
                self.report({'ERROR'}, f"Could not create any decals. {name}: {reason}")
            else:
                self.report({'ERROR'}, "Could not create any decals.")
            return {'CANCELLED'}

        message = f"Created {created} decal(s)."
        if skipped:
            message += f" Skipped {skipped} degenerate face(s)."

        if failures:
            self.report(
                {'WARNING'},
                f"{message} {len(failures)} failed: {_format_failures(failures)}",
            )
        else:
            self.report({'INFO'}, message)

        if drawable_root is None:
            self.report(
                {'WARNING'},
                f"'{source_obj.name}' is not part of a Sollumz Drawable - decals were left "
                f"standalone in '{DECAL_COLLECTION_NAME}'.",
            )
        elif drawable_warnings:
            name, reason = drawable_warnings[0]
            self.report(
                {'WARNING'},
                f"{len(drawable_warnings)} decal(s) could not be registered as Drawable Models "
                f"({name}: {reason}).",
            )

        return {'FINISHED'}


_classes = (SETO_OT_refresh_decal_library, SETO_OT_create_decal)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
