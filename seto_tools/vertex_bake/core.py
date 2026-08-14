import bpy
import bmesh
import math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils import noise
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, PointerProperty

from ..shared import icons
from ..shared import panel_layout as pl
from ..shared import ui_common

VERTEX_COLOR_LAYER_NAME = 'Color 1'

# ============================================================
# Per-object cache
# ============================================================
_mask_cache = {}

def _geo_signature(obj, bm):
    mesh = obj.data
    vcount = len(mesh.vertices)
    ecount = len(bm.edges)
    coords = np.empty(vcount * 3, dtype=np.float64)
    mesh.vertices.foreach_get('co', coords)
    checksum = float(np.dot(coords, coords))
    # Include world matrix so moving the object invalidates the cache
    matrix_sig = tuple(round(v, 4) for row in obj.matrix_world for v in row)
    return (vcount, ecount, round(checksum, 3), matrix_sig)

def _get_cache_entry(obj, bm):
    sig = _geo_signature(obj, bm)
    entry = _mask_cache.get(obj.name)
    if entry is None or entry.get('sig') != sig:
        entry = {'sig': sig}
        _mask_cache[obj.name] = entry
    return entry

def get_bmesh_from_object(obj):
    if obj.mode == 'EDIT':
        obj.update_from_editmode()
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return bm

def detect_concave_edges(bm, threshold=0.1):
    concave = []
    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            continue
        f1, f2 = edge.link_faces
        edge_vec = (edge.verts[1].co - edge.verts[0].co).normalized()
        n1 = f1.normal
        n2 = f2.normal
        dot = max(-1.0, min(1.0, n1.dot(n2)))
        angle = math.acos(dot)
        if angle < threshold:
            continue
        edge_mid = (edge.verts[0].co + edge.verts[1].co) / 2.0
        c1 = f1.calc_center_median() - edge_mid
        c2 = f2.calc_center_median() - edge_mid
        n1_dot_c2 = n1.dot(c2)
        if n1_dot_c2 > 0:
            concave.append(edge)
    return concave

def detect_convex_edges(bm, threshold=0.1):
    convex = []
    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            continue
        f1, f2 = edge.link_faces
        n1 = f1.normal
        n2 = f2.normal
        dot = max(-1.0, min(1.0, n1.dot(n2)))
        angle = math.acos(dot)
        if angle < threshold:
            continue
        edge_mid = (edge.verts[0].co + edge.verts[1].co) / 2.0
        c1 = f1.calc_center_median() - edge_mid
        c2 = f2.calc_center_median() - edge_mid
        n1_dot_c2 = n1.dot(c2)
        if n1_dot_c2 <= 0:
            convex.append(edge)
    return convex

def detect_floor_wall_junction(bm, floor_threshold=0.9, up_vector=Vector((0, 0, 1))):
    up = up_vector.normalized()
    junction_edges = []
    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            continue
        f1, f2 = edge.link_faces
        n1_up = f1.normal.dot(up)
        n2_up = f2.normal.dot(up)
        is_junction = (
            (n1_up > floor_threshold and abs(n2_up) < (1.0 - floor_threshold)) or
            (n2_up > floor_threshold and abs(n1_up) < (1.0 - floor_threshold))
        )
        if is_junction:
            junction_edges.append(edge)
    return junction_edges

def get_verts_within_distance(bm, source_verts, max_distance):
    result = {}
    for vi in source_verts:
        result[vi] = 0.0
    bm.verts.ensure_lookup_table()
    frontier = set(source_verts)
    visited = set(source_verts)
    while frontier:
        next_frontier = set()
        for vi in frontier:
            vert = bm.verts[vi]
            for edge in vert.link_edges:
                other = edge.other_vert(vert)
                edge_len = edge.calc_length()
                new_dist = result[vi] * max_distance + edge_len
                if new_dist <= max_distance:
                    normalized = new_dist / max_distance if max_distance > 0 else 1.0
                    if other.index not in result or normalized < result[other.index]:
                        result[other.index] = normalized
                        next_frontier.add(other.index)
                        visited.add(other.index)
        frontier = next_frontier
    return result

def ensure_color_layer(mesh, name=None):
    if name is None:
        name = VERTEX_COLOR_LAYER_NAME
    layer = mesh.color_attributes.get(name)
    if layer is None:
        layer = mesh.color_attributes.new(
            name=name,
            type='BYTE_COLOR',
            domain='CORNER',
        )
    return layer

def write_vertex_colors_fast(layer, values_dict):
    n_loops = len(layer.data)
    if n_loops == 0 or not values_dict:
        return
    flat = np.empty(n_loops * 4, dtype=np.float32)
    layer.data.foreach_get('color', flat)
    colors = flat.reshape(-1, 4)
    for loop_idx, (r, g, b) in values_dict.items():
        if 0 <= loop_idx < n_loops:
            colors[loop_idx, 0] = r
            colors[loop_idx, 1] = g
            colors[loop_idx, 2] = b
    layer.data.foreach_set('color', colors.reshape(-1))

# ============================================================
# Live baking
# ============================================================
# This tool writes to the user's own mesh, so "live" has to be a choice
# and a drag has to cost one bake rather than forty. Both are the same
# machinery the strip tools use: a switch, and a one-shot timer that
# fires when the hand stops. Background Blender has no event loop, so
# there the bake happens immediately.

_baking = False
_pending = set()
_timer_armed = False
DEBOUNCE_SECONDS = 0.25


def _bake_now(objects, report_to=None):
    """Bake `objects`, putting any failure where it can be seen.

    The old version swallowed every exception, which made a bake that
    could not run look exactly like a bake that had nothing to do.
    """
    settings = bpy.context.scene.seto_vertex_bake
    try:
        generate_detail_stack(bpy.context, objects=objects)
        settings.last_error = ""
    except Exception as error:
        import traceback
        traceback.print_exc()
        settings.last_error = f"{type(error).__name__}: {error}"
        if report_to is not None:
            report_to.report({'ERROR'}, f"Bake failed: {error}")
        return False
    return True


def _flush_pending():
    global _timer_armed, _baking
    _timer_armed = False
    names = list(_pending)
    _pending.clear()
    objects = [obj for obj in (bpy.data.objects.get(n) for n in names)
               if obj is not None and obj.type == 'MESH']
    if objects:
        _baking = True
        try:
            _bake_now(objects)
        finally:
            _baking = False
    return None          # one shot


def get_target_objects(context, is_live=False):
    """Return the list of mesh objects to bake, based on the target mode."""
    settings = context.scene.seto_vertex_bake
    if not is_live and settings.target_mode == 'COLLECTION' and settings.target_collection:
        col = settings.target_collection
        if settings.bake_hidden:
            return [obj for obj in col.all_objects if obj.type == 'MESH']
        else:
            return [obj for obj in col.all_objects
                    if obj.type == 'MESH' and obj.visible_get()]
    return [obj for obj in context.selected_objects if obj.type == 'MESH']


def update_detail_stack(self, context):
    global _timer_armed
    if _baking or not self.live_update:
        return
    targets = get_target_objects(context, is_live=True)
    if not targets:
        return
    if bpy.app.background:
        _bake_now(targets)
        return
    _pending.update(obj.name for obj in targets)
    if not _timer_armed:
        _timer_armed = True
        bpy.app.timers.register(_flush_pending,
                                first_interval=DEBOUNCE_SECONDS)


class SETO_PG_vertex_bake(bpy.types.PropertyGroup):
    live_update: BoolProperty(
        name="Live Update",
        description="Bake as these settings change. This tool writes to "
                    "the mesh you have selected, so turning it off is how "
                    "you look at the settings without touching anything - "
                    "the Generate button then does it when you ask",
        default=True,
    )
    # What the last bake failed with, or "". Shown on the panel: a
    # property callback has no status bar to report into, and a silent
    # failure is indistinguishable from having nothing to do.
    last_error: bpy.props.StringProperty(default="", options={'HIDDEN'})

    target_mode: EnumProperty(
        name="Target",
        description="Choose what to bake: your current selection or an entire collection",
        items=[
            ('SELECTED', "Selected Objects", "Bake only the currently selected mesh objects"),
            ('COLLECTION', "Collection", "Bake every mesh object inside a chosen collection"),
        ],
        default='SELECTED',
    )
    target_collection: PointerProperty(
        name="Collection",
        description="The collection whose mesh objects will be baked",
        type=bpy.types.Collection,
    )
    bake_hidden: BoolProperty(
        name="Include Hidden",
        description="When on, objects hidden in the viewport are still baked. "
                    "When off, only visible objects in the collection are processed",
        default=False,
    )

    detail_base_color: FloatVectorProperty(name="Base Color", subtype='COLOR', default=(1.0, 1.0, 1.0), size=3, min=0.0, max=1.0, update=update_detail_stack)
    gradient_use_colors: BoolProperty(name="Use Custom Colors", default=False, update=update_detail_stack)
    gradient_color_top: FloatVectorProperty(name="Top Color", subtype='COLOR', default=(1.0, 1.0, 1.0), size=3, min=0.0, max=1.0, update=update_detail_stack)
    gradient_color_bottom: FloatVectorProperty(name="Bottom Color", subtype='COLOR', default=(0.0, 0.0, 0.0), size=3, min=0.0, max=1.0, update=update_detail_stack)
    gradient_shift: FloatProperty(name="Gradient Shift", default=0.0, min=-2.0, max=2.0, update=update_detail_stack)
    gradient_scale: FloatProperty(name="Gradient Scale", default=1.0, min=0.1, max=10.0, update=update_detail_stack)
    detail_use_gradient: BoolProperty(name="Use Linear Gradient", default=False, update=update_detail_stack)
    detail_gradient_strength: FloatProperty(name="Gradient Strength", default=0.5, min=0.0, max=2.0, update=update_detail_stack)
    detail_use_ao: BoolProperty(name="Use AO", default=True, update=update_detail_stack)
    detail_use_edge_dirt: BoolProperty(name="Use Edge Dirt", default=True, update=update_detail_stack)
    detail_use_floor_grime: BoolProperty(name="Use Floor Grime", default=True, update=update_detail_stack)
    detail_use_edge_wear: BoolProperty(name="Use Edge Wear", default=True, update=update_detail_stack)
    detail_use_random: BoolProperty(name="Use Random", default=True, update=update_detail_stack)
    detail_use_fake_shadow: BoolProperty(name="Use Fake Shadow", default=False, update=update_detail_stack)
    detail_shadow_strength: FloatProperty(name="Shadow Strength", default=0.5, min=0.0, max=2.0, update=update_detail_stack)
    detail_shadow_angle: FloatProperty(name="Shadow Angle", default=45.0, min=0.0, max=360.0, update=update_detail_stack)
    detail_shadow_altitude: FloatProperty(name="Shadow Altitude", default=45.0, min=0.0, max=90.0, update=update_detail_stack)
    detail_ao_strength: FloatProperty(name="AO Strength", default=0.8, min=0.0, max=2.0, update=update_detail_stack)
    detail_edge_dirt_strength: FloatProperty(name="Edge Dirt Strength", default=0.1, min=0.0, max=2.0, update=update_detail_stack)
    detail_floor_grime_strength: FloatProperty(name="Floor Grime Strength", default=0.2, min=0.0, max=2.0, update=update_detail_stack)
    detail_wear_strength: FloatProperty(name="Wear Strength", default=0.1, min=0.0, max=2.0, update=update_detail_stack)
    detail_random_strength: FloatProperty(name="Random Strength", default=0.1, min=0.0, max=1.0, update=update_detail_stack)

class SETO_PT_vertex_bake_panel(bpy.types.Panel):
    # SETO_* like every other class here, and `seto.*` for the operator.
    # Not tidiness: these arrived as MLOPT_*, and a class name that
    # belongs to another add-on is registered twice the moment a user has
    # both installed - which is the crash Materialize's VMAT_* names are
    # still noted for in the project's context file. The suite also finds
    # panels by the SETO_PT_ prefix, so the old name kept this one out of
    # every test, including the one that drives every panel's draw().
    bl_idname = "SETO_PT_vertex_bake_panel"
    bl_label = "Vertex Color Bake"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = pl.TAB
    bl_parent_id = "SETO_PT_surface_group"
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 100  # Ensures it appears at the bottom of the group

    def draw_header(self, context):
        icons.draw_header(self.layout, "vertex_bake", 'SHADING_SOLID')

    def draw(self, context):
        layout = self.layout
        settings = context.scene.seto_vertex_bake

        # ------------------------------------------------- target mode
        box = layout.box()
        box.label(text="Target", icon='OUTLINER_COLLECTION')
        box.prop(settings, "target_mode", text="")
        if settings.target_mode == 'COLLECTION':
            row = box.row(align=True)
            row.prop(settings, "target_collection", text="")
            row.prop(settings, "bake_hidden", text="", icon='HIDE_OFF' if settings.bake_hidden else 'HIDE_ON')

        col = layout.column(align=True)
        col.prop(settings, "detail_base_color", text="")
        layout.separator()
        col = layout.column(align=True)
        
        def draw_layer(name, prop_use, prop_strength, icon_str):
            row = col.row(align=True)
            split = row.split(factor=0.6)
            split.prop(settings, prop_use, text=name, icon=icon_str)
            sub = split.row(align=True)
            sub.active = getattr(settings, prop_use)
            sub.prop(settings, prop_strength, text="")
            
        draw_layer("Gradient", "detail_use_gradient", "detail_gradient_strength", 'COLOR')
        if settings.detail_use_gradient:
            row = col.row(align=True)
            row.separator(factor=2.0)
            row.prop(settings, "gradient_use_colors")
            if settings.gradient_use_colors:
                row = col.row(align=True)
                row.separator(factor=2.0)
                row.prop(settings, "gradient_color_top", text="Top")
                
                row = col.row(align=True)
                row.separator(factor=2.0)
                row.prop(settings, "gradient_color_bottom", text="Bottom")
                
            row = col.row(align=True)
            row.separator(factor=2.0)
            row.prop(settings, "gradient_shift", text="Shift")
            row.prop(settings, "gradient_scale", text="Scale")
                
        draw_layer("Ambient Occlusion", "detail_use_ao", "detail_ao_strength", 'SHADING_RENDERED')
        draw_layer("Edge Dirt", "detail_use_edge_dirt", "detail_edge_dirt_strength", 'BRUSH_DATA')
        draw_layer("Floor Grime", "detail_use_floor_grime", "detail_floor_grime_strength", 'MATFLUID')
        draw_layer("Edge Wear", "detail_use_edge_wear", "detail_wear_strength", 'MOD_EDGESPLIT')
        draw_layer("Random Noise", "detail_use_random", "detail_random_strength", 'MOD_NOISE')
        draw_layer("Fake Shadow", "detail_use_fake_shadow", "detail_shadow_strength", 'LIGHT_SUN')
        
        if settings.detail_use_fake_shadow:
            row = col.row(align=True)
            row.separator(factor=2.0)
            row.prop(settings, "detail_shadow_angle", text="Angle")
            row.prop(settings, "detail_shadow_altitude", text="Altitude")
            
        if settings.last_error:
            warn = layout.box()
            warn.alert = True
            col = warn.column(align=True)
            col.label(text="Last bake failed:", icon='ERROR')
            for line in ui_common.wrap(settings.last_error, 38):
                col.label(text=line)

        layout.separator()
        # The switch first: this tool writes to the mesh you have
        # selected, so whether it does that while you drag is a decision
        # worth seeing before you drag.
        layout.prop(settings, "live_update")
        col = layout.column(align=True)
        col.scale_y = 1.2
        row = col.row(align=True)
        row.operator("seto.vertex_bake_clear", icon='X', text="Clear")
        row.operator("seto.vertex_bake", icon='NODETREE', text="Generate Vertex Color")

        note = layout.column(align=True)
        note.scale_y = 0.8
        if settings.target_mode == 'COLLECTION' and settings.target_collection:
            count = len([o for o in settings.target_collection.all_objects if o.type == 'MESH'])
            note.label(text=f"Collection: {count} mesh objects.", icon='INFO')
        else:
            note.label(text="Writes Color 1 onto the selected mesh.",
                       icon='INFO')

class SETO_OT_vertex_bake(bpy.types.Operator):
    bl_idname = "seto.vertex_bake"
    bl_label = "Generate Detail Stack"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        settings = context.scene.seto_vertex_bake
        if settings.target_mode == 'COLLECTION':
            return settings.target_collection is not None
        return context.active_object is not None and context.active_object.type == 'MESH'
        
    def execute(self, context):
        objects = get_target_objects(context)
        if not objects:
            self.report({'ERROR'}, "No mesh objects found to bake.")
            return {'CANCELLED'}

        settings = context.scene.seto_vertex_bake
        total = len(objects)
        wm = context.window_manager
        wm.progress_begin(0, total)

        try:
            for i, obj in enumerate(objects):
                wm.progress_update(i)
                generate_detail_stack(context, objects=[obj], force_rebuild=True)
                settings.last_error = ""
        except Exception as error:
            import traceback
            traceback.print_exc()
            settings.last_error = f"{type(error).__name__}: {error}"
            self.report({'ERROR'}, f"Bake failed: {error}")
            wm.progress_end()
            return {'CANCELLED'}

        wm.progress_end()
        self.report({'INFO'},
                    f"Baked Color 1 onto {total} "
                    f"object{'s' if total != 1 else ''}.")
        return {'FINISHED'}

class SETO_OT_vertex_bake_clear(bpy.types.Operator):
    bl_idname = "seto.vertex_bake_clear"
    bl_label = "Clear Vertex Colors"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        settings = context.scene.seto_vertex_bake
        if settings.target_mode == 'COLLECTION':
            return settings.target_collection is not None
        return context.active_object is not None and context.active_object.type == 'MESH'
        
    def execute(self, context):
        objects = get_target_objects(context)
        if not objects:
            self.report({'ERROR'}, "No mesh objects found to clear.")
            return {'CANCELLED'}

        for obj in objects:
            layer = obj.data.color_attributes.get(VERTEX_COLOR_LAYER_NAME)
            if not layer:
                continue
            n_loops = len(layer.data)
            if n_loops == 0:
                continue
            # Clear undoes the colour this tool wrote, and nothing else.
            # Alpha in `Color 1` is what the decal shaders blend by, so it
            # is read back and put down untouched - writing 1.0 over it
            # would make every decal on the mesh fully opaque, invisibly,
            # from a button labelled Clear.
            flat = np.empty(n_loops * 4, dtype=np.float32)
            layer.data.foreach_get('color', flat)
            flat.reshape(n_loops, 4)[:, :3] = 1.0
            layer.data.foreach_set('color', flat)

        self.report({'INFO'}, f"Cleared Color 1 on {len(objects)} object(s).")
        return {'FINISHED'}

def generate_detail_stack(context, objects=None, force_rebuild=False):
    """Bake `objects`, or the selection when none are given.

    The explicit list is what the debounced live path hands back after
    the timer fires - by then the selection may be something else, and
    baking whatever happens to be selected a quarter of a second later
    would write to the wrong mesh.
    """
    settings = context.scene.seto_vertex_bake
    depsgraph = context.evaluated_depsgraph_get()
    scene = context.scene
    for obj in (context.selected_objects if objects is None else objects):
        if obj.type != 'MESH':
            continue
        bm = get_bmesh_from_object(obj)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        cache = _get_cache_entry(obj, bm)
        if force_rebuild:
            cache.clear()
            cache['sig'] = _geo_signature(obj, bm)
        result_values = {v.index: 1.0 for v in bm.verts}

        if settings.detail_use_gradient:
            if 'gradient_z' not in cache:
                matrix_world = obj.matrix_world
                world_zs = {v.index: (matrix_world @ v.co).z for v in bm.verts}
                gradient_z = {}
                if world_zs:
                    min_z = min(world_zs.values())
                    max_z = max(world_zs.values())
                    z_range = max_z - min_z
                    if z_range > 0.0001:
                        for idx, wz in world_zs.items():
                            gradient_z[idx] = (wz - min_z) / z_range
                cache['gradient_z'] = gradient_z
            if not settings.gradient_use_colors:
                for vi, normalized_z in cache['gradient_z'].items():
                    adjusted_z = max(0.0, min(1.0, ((normalized_z - 0.5) * settings.gradient_scale) + 0.5 + settings.gradient_shift))
                    val = 1.0 - ((1.0 - adjusted_z) * settings.detail_gradient_strength)
                    result_values[vi] *= max(0.0, min(1.0, val))

        if settings.detail_use_ao:
            if 'ao_hits' not in cache:
                samples = 32
                golden_ratio = (1 + 5 ** 0.5) / 2
                ao_hits = {}
                matrix_world = obj.matrix_world
                normal_matrix = matrix_world.to_3x3()
                for v in bm.verts:
                    hit_count = 0
                    world_origin = matrix_world @ v.co
                    world_normal = (normal_matrix @ v.normal).normalized()
                    ray_start = world_origin + world_normal * 0.0001
                    for i in range(samples):
                        theta = 2 * math.pi * i / golden_ratio
                        phi = math.acos(1 - (i + 0.5) / samples)
                        x = math.cos(theta) * math.sin(phi)
                        y = math.sin(theta) * math.sin(phi)
                        z = math.cos(phi)
                        ray_dir = Vector((x, y, z))
                        if ray_dir.dot(v.normal) < 0:
                            ray_dir = -ray_dir
                        world_ray_dir = (normal_matrix @ ray_dir).normalized()
                        hit, _, _, _, _, _ = scene.ray_cast(depsgraph, ray_start, world_ray_dir, distance=0.25)
                        if hit: hit_count += 1
                    ao_hits[v.index] = hit_count
                cache['ao_hits'] = ao_hits
                cache['ao_samples'] = samples
            samples = cache['ao_samples']
            for vi, hit_count in cache['ao_hits'].items():
                ao = 1.0 - (hit_count / samples) * settings.detail_ao_strength
                ao = max(0.0, min(1.0, ao))
                result_values[vi] *= ao

        if settings.detail_use_edge_dirt:
            if 'concave_counts' not in cache:
                concave = detect_concave_edges(bm, threshold=0.1)
                concave_counts = {}
                for edge in concave:
                    for v in edge.verts:
                        concave_counts[v.index] = concave_counts.get(v.index, 0) + 1
                cache['concave_counts'] = concave_counts
            val = settings.detail_edge_dirt_strength
            for vi, count in cache['concave_counts'].items():
                result_values[vi] *= (1.0 - val) ** count

        if settings.detail_use_floor_grime:
            if 'floor_grime_dist' not in cache:
                local_up = obj.matrix_world.inverted().to_3x3() @ Vector((0, 0, 1))
                junctions = detect_floor_wall_junction(bm, floor_threshold=0.85, up_vector=local_up)
                source_verts = set()
                for edge in junctions:
                    for v in edge.verts:
                        source_verts.add(v.index)
                spread_result = {}
                if source_verts:
                    spread_result = get_verts_within_distance(bm, source_verts, max_distance=0.5)
                cache['floor_grime_dist'] = spread_result
            for vi, normalized_dist in cache['floor_grime_dist'].items():
                intensity = (1.0 - normalized_dist) * settings.detail_floor_grime_strength
                result_values[vi] *= (1.0 - intensity)

        if settings.detail_use_edge_wear:
            if 'convex_counts' not in cache:
                convex = detect_convex_edges(bm, threshold=0.5)
                convex_counts = {}
                for edge in convex:
                    for v in edge.verts:
                        convex_counts[v.index] = convex_counts.get(v.index, 0) + 1
                cache['convex_counts'] = convex_counts
            val = settings.detail_wear_strength
            for vi, count in cache['convex_counts'].items():
                result_values[vi] *= (1.0 - val) ** count

        if settings.detail_use_random:
            if 'random_raw' not in cache:
                random_raw = {}
                for v in bm.verts:
                    nv = noise.noise_vector(v.co * 5.0)
                    random_raw[v.index] = nv.length % 1.0
                cache['random_raw'] = random_raw
            for vi, raw in cache['random_raw'].items():
                val = raw * settings.detail_random_strength
                result_values[vi] *= (1.0 - val)

        if settings.detail_use_fake_shadow:
            shadow_key = (
                round(settings.detail_shadow_angle, 2),
                round(settings.detail_shadow_altitude, 2),
            )
            if cache.get('shadow_key') != shadow_key:
                yaw = math.radians(settings.detail_shadow_angle)
                pitch = math.radians(settings.detail_shadow_altitude)
                dx = math.cos(yaw) * math.cos(pitch)
                dy = math.sin(yaw) * math.cos(pitch)
                dz = -math.sin(pitch)
                world_light_dir = Vector((dx, dy, dz)).normalized()
                to_light_world = -world_light_dir
                shadow_ndotl = {}
                matrix_world = obj.matrix_world
                normal_matrix = matrix_world.to_3x3()
                for v in bm.verts:
                    world_normal = (normal_matrix @ v.normal).normalized()
                    n_dot_l = max(0.0, world_normal.dot(to_light_world))
                    if n_dot_l > 0.001:
                        world_origin = matrix_world @ v.co
                        ray_start = world_origin + world_normal * 0.001
                        hit, _, _, _, _, _ = scene.ray_cast(depsgraph, ray_start, to_light_world, distance=100.0)
                        if hit:
                            n_dot_l = 0.0
                    shadow_ndotl[v.index] = n_dot_l
                cache['shadow_key'] = shadow_key
                cache['shadow_ndotl'] = shadow_ndotl
            for vi, n_dot_l in cache['shadow_ndotl'].items():
                val = 1.0 - ((1.0 - n_dot_l) * settings.detail_shadow_strength)
                result_values[vi] *= max(0.0, min(1.0, val))

        values_dict = {}
        layer = ensure_color_layer(obj.data, VERTEX_COLOR_LAYER_NAME)
        
        base_r, base_g, base_b = settings.detail_base_color
        use_grad_colors = settings.detail_use_gradient and settings.gradient_use_colors
        top_r, top_g, top_b = settings.gradient_color_top
        bot_r, bot_g, bot_b = settings.gradient_color_bottom
        grad_cache = cache.get('gradient_z', {})

        for v in bm.verts:
            val = max(0.0, min(1.0, result_values[v.index]))
            if use_grad_colors:
                g_val = grad_cache.get(v.index, 1.0)
                g_val = max(0.0, min(1.0, ((g_val - 0.5) * settings.gradient_scale) + 0.5 + settings.gradient_shift))
                
                cr = bot_r * (1.0 - g_val) + top_r * g_val
                cg = bot_g * (1.0 - g_val) + top_g * g_val
                cb = bot_b * (1.0 - g_val) + top_b * g_val
                    
                r = val * cr
                g = val * cg
                b = val * cb
            else:
                r = val * base_r
                g = val * base_g
                b = val * base_b
                
            for loop in v.link_loops:
                values_dict[loop.index] = (r, g, b)
        bm.free()
        if values_dict:
            write_vertex_colors_fast(layer, values_dict)

classes = (
    SETO_PG_vertex_bake,
    SETO_PT_vertex_bake_panel,
    SETO_OT_vertex_bake,
    SETO_OT_vertex_bake_clear,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_vertex_bake = PointerProperty(type=SETO_PG_vertex_bake)

def unregister():
    _mask_cache.clear()
    if hasattr(bpy.types.Scene, 'seto_vertex_bake'):
        del bpy.types.Scene.seto_vertex_bake
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
