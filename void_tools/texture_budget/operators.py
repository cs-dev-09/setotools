"""Analyze and Finish for the Texture Budget.

Reads only: the images a material points at, and the surface they land on.
Nothing is resized, repacked or unlinked - the tool says which texture is
too big for the thing wearing it and leaves the decision to the author.

The grading session (who is painting, what the colours were, the viewport
flip) is `shared/viewport_grade.py`'s, shared with the Density Check so the
two cannot lose each other's colours.
"""

import bpy

from ..shared import budget, mesh_stats, viewport_grade as vg
from . import geometry

TOOL = 'TEXTURE'

# ID properties Analyze leaves behind, all removed by Finish.
TEXELS_PROP = "seto_texture_texels"      # texels per metre, -1 = no texture
PIXELS_PROP = "seto_texture_pixels"      # the largest single image, in pixels
BYTES_PROP = "seto_texture_bytes"        # every image on it, mips included
AREA_PROP = "seto_texture_area"
OWN_PROPS = (TEXELS_PROP, PIXELS_PROP, BYTES_PROP, AREA_PROP)
vg.owns(TOOL, OWN_PROPS)

NO_TEXTURE = -1.0

# What an object with no texture is painted: grey, not red. It is not a
# budget failure - a collision mesh or a blockout has nothing to answer for -
# and colouring it like one would teach the user to distrust the reds.
NEUTRAL = (0.35, 0.35, 0.35, 1.0)


def object_images(obj):
    """Every image the object's materials actually sample, deduplicated."""
    found = {}
    for slot in obj.material_slots:
        material = slot.material
        if material is None or not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            if node.type != 'TEX_IMAGE' or node.image is None:
                continue
            image = node.image
            if image.size[0] and image.size[1]:
                found[image.name] = image
    return list(found.values())


def _grade(obj, settings, depsgraph):
    _tris, area = mesh_stats.world_mesh_stats(obj, depsgraph)
    images = object_images(obj)
    pixels = max((i.size[0] * i.size[1] for i in images), default=0)
    total = sum(i.size[0] * i.size[1] for i in images)

    obj[AREA_PROP] = area
    obj[PIXELS_PROP] = pixels
    obj[BYTES_PROP] = geometry.vram_bytes(total)

    value = geometry.ratio(pixels, area, settings.target)
    if value is None:
        obj[TEXELS_PROP] = NO_TEXTURE
        vg.paint(obj, NEUTRAL)
        return None
    obj[TEXELS_PROP] = geometry.texel_density(pixels, area)
    vg.paint(obj, budget.colour(budget.fraction(value)))
    return value


class SETO_OT_texture_analyze(bpy.types.Operator):
    bl_idname = "seto.texture_analyze"
    bl_label = "Analyze Textures"
    bl_description = ("Colour every mesh in scope by the texture resolution "
                      "it carries for its size, and total up what the scene "
                      "costs in VRAM")
    bl_options = {'UNDO'}

    def execute(self, context):
        settings = context.scene.seto_texture_budget
        objects = vg.scope_objects(context, settings.scope)
        if not objects:
            self.report({'ERROR'}, "No mesh objects in scope to analyze.")
            return {'CANCELLED'}

        vg.begin(context, TOOL)
        depsgraph = context.evaluated_depsgraph_get()

        # Scene totals count each image once however many objects wear it -
        # a texture shared by forty props is loaded once, and totalling it
        # per object would report a streaming cost nobody pays.
        seen = {}
        for obj in objects:
            _grade(obj, settings, depsgraph)
            for image in object_images(obj):
                seen[image.name] = image.size[0] * image.size[1]

        settings.total_pixels = float(sum(seen.values()))
        settings.image_count = len(seen)
        if seen:
            name, pixels = max(seen.items(), key=lambda item: item[1])
            settings.biggest_name = name
            settings.biggest_size = int(round(pixels ** 0.5))
        else:
            settings.biggest_name = ""
            settings.biggest_size = 0

        self.report({'INFO'}, f"Analyzed {len(objects)} objects, "
                              f"{len(seen)} textures.")
        return {'FINISHED'}


class SETO_OT_texture_clear(bpy.types.Operator):
    bl_idname = "seto.texture_clear"
    bl_label = "Finish Analysis"
    bl_description = ("End the analysis: restore every object's own colour "
                      "and put the viewport shading back as it was")
    bl_options = {'UNDO'}

    def execute(self, context):
        settings = context.scene.seto_texture_budget
        count = vg.end(context)
        settings.total_pixels = 0.0
        settings.image_count = 0
        settings.biggest_name = ""
        settings.biggest_size = 0
        self.report({'INFO'}, f"Cleared {count} objects.")
        return {'FINISHED'}


_classes = (SETO_OT_texture_analyze, SETO_OT_texture_clear)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
