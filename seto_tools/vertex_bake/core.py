import bpy
import bmesh
import math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils import noise
from bpy.props import BoolProperty, FloatProperty, FloatVectorProperty, PointerProperty

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
    return (vcount, ecount, round(checksum, 3))

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


def update_detail_stack(self, context):
    global _timer_armed
    if _baking or not self.live_update:
        return
    selected = [obj for obj in context.selected_objects
                if obj.type == 'MESH']
    if not selected:
        return
    if bpy.app.background:
        _bake_now(selected)
        return
    _pending.update(obj.name for obj in selected)
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

    detail_base_color: FloatVectorProperty(name="Base Color", subtype='COLOR', default=(1.0, 1.0, 1.0), size=3, min=0.0, max=1.0, update=update_detail_stack)
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
        col.operator("seto.vertex_bake", icon='NODETREE', text="Generate Vertex Color")

        note = layout.column(align=True)
        note.scale_y = 0.8
        note.label(text="Writes Color 1 onto the selected mesh.",
                   icon='INFO')

class SETO_OT_vertex_bake(bpy.types.Operator):
    bl_idname = "seto.vertex_bake"
    bl_label = "Generate Detail Stack"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'
        
    def execute(self, context):
        objects = [obj for obj in context.selected_objects
                   if obj.type == 'MESH']
        if not objects:
            self.report({'ERROR'}, "Select a mesh to bake onto.")
            return {'CANCELLED'}
        if not _bake_now(objects, report_to=self):
            return {'CANCELLED'}
        self.report({'INFO'},
                    f"Baked Color 1 onto {len(objects)} "
                    f"object{'s' if len(objects) != 1 else ''}.")
        return {'FINISHED'}

def generate_detail_stack(context, objects=None):
    """Bake `objects`, or the selection when none are given.

    The explicit list is what the debounced live path hands back after
    the timer fires - by then the selection may be something else, and
    baking whatever happens to be selected a quarter of a second later
    would write to the wrong mesh.
    """
    settings = context.scene.seto_vertex_bake
    for obj in (context.selected_objects if objects is None else objects):
        if obj.type != 'MESH':
            continue
        bm = get_bmesh_from_object(obj)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        cache = _get_cache_entry(obj, bm)
        result_values = {v.index: 1.0 for v in bm.verts}

        if settings.detail_use_gradient:
            if 'gradient_z' not in cache:
                min_z = min((v.co.z for v in bm.verts), default=0.0)
                max_z = max((v.co.z for v in bm.verts), default=1.0)
                z_range = max_z - min_z
                gradient_z = {}
                if z_range > 0.0001:
                    for v in bm.verts:
                        gradient_z[v.index] = (v.co.z - min_z) / z_range
                cache['gradient_z'] = gradient_z
            for vi, normalized_z in cache['gradient_z'].items():
                val = 1.0 - ((1.0 - normalized_z) * settings.detail_gradient_strength)
                result_values[vi] *= max(0.0, min(1.0, val))

        if settings.detail_use_ao:
            if 'ao_hits' not in cache:
                bvh = BVHTree.FromBMesh(bm)
                samples = 32
                golden_ratio = (1 + 5 ** 0.5) / 2
                ao_hits = {}
                for v in bm.verts:
                    hit_count = 0
                    for i in range(samples):
                        theta = 2 * math.pi * i / golden_ratio
                        phi = math.acos(1 - (i + 0.5) / samples)
                        x = math.cos(theta) * math.sin(phi)
                        y = math.sin(theta) * math.sin(phi)
                        z = math.cos(phi)
                        ray_dir = Vector((x, y, z))
                        if ray_dir.dot(v.normal) < 0:
                            ray_dir = -ray_dir
                        hit, _, _, _ = bvh.ray_cast(v.co + v.normal * 0.0001, ray_dir, 0.25)
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
                local_light_dir = obj.matrix_world.inverted().to_3x3() @ world_light_dir
                local_light_dir.normalize()
                bvh = BVHTree.FromBMesh(bm)
                to_light = -local_light_dir
                shadow_ndotl = {}
                for v in bm.verts:
                    n_dot_l = max(0.0, v.normal.dot(to_light))
                    if n_dot_l > 0.001:
                        hit, _, _, _ = bvh.ray_cast(v.co + v.normal * 0.001, to_light, 100.0)
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
        for v in bm.verts:
            val = max(0.0, min(1.0, result_values[v.index]))
            r = val * settings.detail_base_color[0]
            g = val * settings.detail_base_color[1]
            b = val * settings.detail_base_color[2]
            for loop in v.link_loops:
                values_dict[loop.index] = (r, g, b)
        bm.free()
        if values_dict:
            write_vertex_colors_fast(layer, values_dict)

classes = (
    SETO_PG_vertex_bake,
    SETO_PT_vertex_bake_panel,
    SETO_OT_vertex_bake,
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
