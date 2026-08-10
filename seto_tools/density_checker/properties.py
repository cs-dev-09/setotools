"""Scene-level settings for the Density Check.

One budget and a scope - there is no per-object group and no live rebuild
here, because the tool builds nothing. Analyze reads the scene and paints
verdicts; the only state worth keeping is what the user considers a fair
triangle budget, and that is one number.

The budget is `1000 × √area` by default, calibrated directly against vanilla
GTA V assets rather than against any one class of them: a bottle (~250 tris
over 0.05 m²), a chair (~1000 over 1.5 m²), a tyre (800 over 2.7 m²) and a
bare room shell all measure close to 1× of it. Yellow means "spending what
Rockstar would", red means multiples of that - an unretouched Sketchfab/CAD
import, or a mesh that ate a subdivision it never needed. Tighten the number
for stricter projects; the colour scale rides along.
"""

import bpy


class SETO_PG_density_checker(bpy.types.PropertyGroup):
    budget: bpy.props.FloatProperty(
        name="Budget",
        description="Triangles a mesh may spend per square-root metre of "
                    "surface (budget = this × √area). The default of 1000 "
                    "matches vanilla GTA V assets: yellow is what Rockstar "
                    "spends, red is several times it",
        default=1000.0, min=1.0, soft_max=100000.0,
    )
    scope: bpy.props.EnumProperty(
        name="Scope",
        description="Which objects Analyze measures",
        items=(
            ('VISIBLE', "Visible", "Every visible mesh object in the view layer"),
            ('SELECTED', "Selected", "Only the selected mesh objects"),
        ),
        default='VISIBLE',
    )
    # The viewport colour mode Analyze found, so Finish can put it back instead
    # of guessing that everyone runs the default Material shading.
    saved_shading: bpy.props.StringProperty(default="", options={'HIDDEN'})
    # An analysis is on screen right now. What the panel keys its two states
    # off: saved_shading cannot serve, because it stays empty when the
    # viewport was already showing Object colours when Analyze ran.
    active: bpy.props.BoolProperty(default=False, options={'HIDDEN'})


_classes = (SETO_PG_density_checker,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_density_checker = bpy.props.PointerProperty(
        type=SETO_PG_density_checker)


def unregister():
    del bpy.types.Scene.seto_density_checker
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
