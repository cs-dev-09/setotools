"""Create a glow, rebuild it, and hand it over to Sollumz.

Four buttons and a magnifier. The split between them is the same one the rest
of the add-on makes: Create and Rebuild are Blender-only and always work,
Export is the step that needs Sollumz and says so when it is missing.
"""

import os

import bpy

from . import object_settings
from ..shared import dds
from ..shared import sollumz_integration as szi


def _unique_name():
    index = 1
    while f"sign_glow_{index:03d}" in bpy.data.objects:
        index += 1
    return f"sign_glow_{index:03d}"


def _export_directory():
    """Where Export writes its .dds: beside the .blend, or the temp dir.

    A saved file gets a `textures/` folder next to it, which is where a GTA
    asset's textures live anyway. An unsaved one has nowhere of its own, and
    writing next to the .blend is not an option when there is no .blend - so it
    goes to Blender's temp dir and the report says where.
    """
    if bpy.data.filepath:
        return os.path.join(os.path.dirname(bpy.data.filepath), "textures")
    return os.path.join(bpy.app.tempdir, "sign_glow")


def _glow_image(glow):
    return bpy.data.images.get(glow.get(object_settings.IMAGE_NAME_KEY, ""))


def _is_glow(obj):
    return (obj is not None and obj.type == 'MESH'
            and obj.seto_sign_glow_data.is_sign_glow)


def apply_emissive_material(glow, image, preferred_shader, write_dds=True):
    """Put a Sollumz emissive shader on the plane. Returns `(shader, path)`.

    Raises `OSError` or one of sollumz_integration's errors, which the callers
    turn into a report.

    `write_dds` decides whether the halo is also written to disk and the image
    repointed at it. **Create does not**: generating a glow should not put a
    file on somebody's drive without being asked, and the material shows the
    packed image perfectly well in the viewport either way. Export does, and
    the order there is not cosmetic - Sollumz embeds whatever the image
    datablock points at, so the file has to exist before the material is built
    around it. From that point on the image is a file reference and the rebuild
    keeps the file equal to what the sliders say (object_settings._refresh_dds).
    """
    path = None
    if write_dds:
        directory = _export_directory()
        os.makedirs(directory, exist_ok=True)
        stem = image.name.rsplit('.', 1)[0]
        path = dds.write_image(image, os.path.join(directory, f"{stem}.dds"))
        image.filepath = path
        image.source = 'FILE'
        image.reload()

    material, shader = szi.find_or_create_emissive_material(
        glow.name, image, preferred_shader)
    glow.data.materials.clear()
    try:
        szi.assign_material_to_object(glow, material)
    except szi.SollumzUnavailableError:
        # The shader exists but Sollumz's own finishing call does not, on this
        # version. The material is still the right one; say what it is for.
        glow.data.materials.append(material)
        szi.convert_to_drawable_model(glow)
    return shader, path


class SETO_OT_create_sign_glow(bpy.types.Operator):
    """Build a glowing halo plane behind the selected lettering"""
    bl_idname = "seto.create_sign_glow"
    bl_label = "Create Sign Glow"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT'
                and any(obj.type == 'MESH' and not obj.seto_sign_glow_data.is_sign_glow
                        for obj in context.selected_objects))

    def execute(self, context):
        sources = [obj for obj in context.selected_objects
                   if obj.type == 'MESH' and not obj.seto_sign_glow_data.is_sign_glow]
        if not sources:
            self.report({'WARNING'}, "Select the lettering to trace.")
            return {'CANCELLED'}

        settings = context.scene.seto_sign_glow
        name = _unique_name()
        glow = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        # Into the lettering's own collection: a glow that lands in the scene
        # root while its sign is three collections deep is one the user has to
        # go and find every time they want to touch it.
        collection = (sources[0].users_collection[0] if sources[0].users_collection
                      else context.collection)
        collection.objects.link(glow)
        glow[object_settings.SOURCE_NAMES_KEY] = [obj.name for obj in sources]
        glow[object_settings.IMAGE_NAME_KEY] = f"{name}_tex"

        data = glow.seto_sign_glow_data
        # Everything is seeded before is_sign_glow goes true: the live callback
        # checks that flag, so until it is set none of these writes tries to
        # rebuild a glow that has no mesh yet.
        data.source_object = sources[0]
        data.resolution = settings.resolution
        data.color = settings.color
        data.is_sign_glow = True

        status = object_settings.rebuild(glow, context.evaluated_depsgraph_get())
        data.status = status or ""
        if status:
            self.report({'WARNING'}, status)

        # The finished glow wears the shader it will be exported with, not a
        # preview of it - a sign that looks right in Blender and then arrives
        # in game as a grey quad is the whole problem this tool exists to
        # avoid. Without Sollumz there is no such shader to give it, so the
        # viewport material stands in and Export swaps it later.
        #
        # The texture stays packed. Nothing here writes to the user's drive
        # until they ask for it with Export or Save DDS.
        image = _glow_image(glow)
        note = ""
        if szi.is_sollumz_available() and image is not None:
            try:
                shader, _path = apply_emissive_material(
                    glow, image, data.shader_name, write_dds=False)
                data.shader_name = shader
                note = f" - {shader}"
            except (OSError, szi.SollumzShaderError,
                    szi.SollumzUnavailableError) as error:
                self.report({'WARNING'},
                            f"Built with the viewport material: {error}")
        if not glow.data.materials:
            glow.data.materials.append(object_settings.build_preview_material(
                f"{name}{object_settings.PREVIEW_MATERIAL_SUFFIX}",
                image, data.preview_strength))

        for obj in context.selected_objects:
            obj.select_set(False)
        glow.select_set(True)
        context.view_layer.objects.active = glow
        self.report({'INFO'},
                    f"'{name}' built behind {len(sources)} object"
                    f"{'s' if len(sources) != 1 else ''}{note}.")
        return {'FINISHED'}


class SETO_OT_sign_glow_rebuild(bpy.types.Operator):
    """Regenerate this glow's texture and plane from its source"""
    bl_idname = "seto.sign_glow_rebuild"
    bl_label = "Rebuild"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _is_glow(context.active_object)

    def execute(self, context):
        glow = context.active_object
        status = object_settings.rebuild(glow, context.evaluated_depsgraph_get())
        glow.seto_sign_glow_data.status = status or ""
        if status:
            self.report({'WARNING'}, status)
            return {'CANCELLED'}
        self.report({'INFO'}, f"Rebuilt {glow.name}.")
        return {'FINISHED'}


class SETO_OT_sign_glow_export(bpy.types.Operator):
    """Rewrite the .dds and rebuild the Sollumz emissive shader on this plane.

    Create already does this when Sollumz is available, so this is for the
    cases where it could not or where the answer has changed: a glow built on a
    machine without Sollumz, a different shader typed into the field above, or
    a .blend that has since been saved somewhere else and wants its texture
    beside it
    """
    bl_idname = "seto.sign_glow_export"
    bl_label = "Export for Sollumz"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _is_glow(context.active_object)

    def execute(self, context):
        if not szi.is_sollumz_available():
            self.report({'ERROR'}, "Sollumz is not available.")
            return {'CANCELLED'}

        glow = context.active_object
        data = glow.seto_sign_glow_data
        image = _glow_image(glow)
        if image is None:
            self.report({'ERROR'}, "This glow has no texture - rebuild it first.")
            return {'CANCELLED'}

        try:
            shader, path = apply_emissive_material(glow, image, data.shader_name)
        except OSError as error:
            self.report({'ERROR'}, f"Could not write the .dds: {error}")
            return {'CANCELLED'}
        except (szi.SollumzShaderError, szi.SollumzUnavailableError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        data.shader_name = shader
        self.report({'INFO'}, f"{shader} + {os.path.basename(path)}")
        return {'FINISHED'}


class SETO_OT_sign_glow_save_dds(bpy.types.Operator):
    """Save this glow's texture as a .dds file"""
    bl_idname = "seto.sign_glow_save_dds"
    bl_label = "Save DDS"
    bl_options = {'REGISTER'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')

    @classmethod
    def poll(cls, context):
        return _is_glow(context.active_object)

    def invoke(self, context, event):
        glow = context.active_object
        self.filepath = f"//{glow.get(object_settings.IMAGE_NAME_KEY, 'sign_glow')}.dds"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        glow = context.active_object
        image = _glow_image(glow)
        if image is None:
            self.report({'ERROR'}, "This glow has no texture - rebuild it first.")
            return {'CANCELLED'}
        path = self.filepath
        if not path.lower().endswith(".dds"):
            path = f"{path.rsplit('.', 1)[0]}.dds"
        try:
            dds.write_image(image, bpy.path.abspath(path))
        except OSError as error:
            self.report({'ERROR'}, f"Could not write the .dds: {error}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Saved {path}")
        return {'FINISHED'}


class SETO_OT_sign_glow_list_shaders(bpy.types.Operator):
    """List the emissive shaders your Sollumz actually has"""
    bl_idname = "seto.sign_glow_list_shaders"
    bl_label = "List Emissive Shaders"

    def execute(self, context):
        if not szi.is_sollumz_available():
            self.report({'ERROR'}, "Sollumz is not available.")
            return {'CANCELLED'}
        names = szi.list_emissive_shaders()
        if not names:
            self.report({'WARNING'},
                        "No emissive shader was found in this Sollumz.")
            return {'CANCELLED'}
        print("[Void Tools] Emissive shaders available:")
        for name in names:
            print("   ", name)
        self.report({'INFO'},
                    ", ".join(names[:6]) + (" ..." if len(names) > 6 else ""))
        return {'FINISHED'}


_classes = (SETO_OT_create_sign_glow, SETO_OT_sign_glow_rebuild,
            SETO_OT_sign_glow_export, SETO_OT_sign_glow_save_dds,
            SETO_OT_sign_glow_list_shaders)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
