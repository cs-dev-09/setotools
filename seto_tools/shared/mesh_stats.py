"""What a mesh actually costs, measured the way the exporter sees it.

Both Analysis tools need the same two numbers and must take them the same
way, or their verdicts would disagree about the same object.

Measuring the **evaluated** mesh is the point, not a nicety: a wall with a
live Bevel - which every strip tool in this add-on adds - exports what the
modifier produces, so counting the base mesh would grade a different object
than the one that ships. The area is taken in **world** space for the same
reason: a plane scaled 10× across covers 10× the floor, and both a triangle
budget and a texel density should say so.
"""


def world_mesh_stats(obj, depsgraph):
    """(triangle count, world-space surface area in m²) of `obj` as exported."""
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        mesh.calc_loop_triangles()
        matrix = eval_obj.matrix_world
        coords = [matrix @ vertex.co for vertex in mesh.vertices]
        area = 0.0
        for tri in mesh.loop_triangles:
            a, b, c = (coords[i] for i in tri.vertices)
            area += (b - a).cross(c - a).length
        return len(mesh.loop_triangles), area * 0.5
    finally:
        eval_obj.to_mesh_clear()
