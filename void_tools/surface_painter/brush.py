"""Driving Blender's vertex paint brush from the panel.

The dirt shell's mask is Color 1's *alpha* - that is the channel decal.sps
blends with - so the brush paints alpha, not colour:

    painting   blend = ADD_ALPHA    strokes raise alpha toward 1 (more dirt)
    erasing    blend = ERASE_ALPHA  strokes lower alpha toward 0 (clean)

Strength is how fast a stroke builds up. The brush colour is irrelevant in
these modes and is left alone.

Two things about Blender that this module exists to absorb:

Unified paint settings can override the brush's own size/strength, and whether
they do is a preference the artist may have set years ago. Rather than detect
it, both are written - they then agree whichever one is in effect.

Brushes are assets, and the properties moved between versions: 4.x has
Brush.curve_preset, 5.x renamed it to curve_distance_falloff_preset, and
unified settings moved from ToolSettings onto Paint. Every access below is
version tolerant, and a missing brush is reported rather than crashed on - in
background mode there may be no brush at all.
"""

PAINT_BLEND = 'ADD_ALPHA'
ERASE_BLEND = 'ERASE_ALPHA'

# Presets present in both 4.x and 5.x. SMOOTHER exists only in 5.x and is left
# out so the enum means the same thing on every version.
FALLOFF_ITEMS = (
    ('SMOOTH', "Smooth", "Soft edge - the usual choice for dirt"),
    ('SPHERE', "Sphere", "Rounded, fuller in the middle"),
    ('ROOT', "Root", "Wide and soft"),
    ('SHARP', "Sharp", "Tight centre, fast falloff"),
    ('LIN', "Linear", "Even ramp from centre to edge"),
    ('CONSTANT', "Constant", "Hard edge, no falloff"),
)

_FALLOFF_ATTRS = ("curve_distance_falloff_preset", "curve_preset")


def get_paint(context):
    """The vertex paint settings, or None."""
    tool_settings = getattr(context, "tool_settings", None)
    return getattr(tool_settings, "vertex_paint", None) if tool_settings else None


def get_brush(context):
    """The active vertex paint brush, or None.

    None is normal: in background mode no brush asset may be loaded, and in the
    UI there is a moment before one is activated.
    """
    paint = get_paint(context)
    return getattr(paint, "brush", None) if paint is not None else None


def _unified(context):
    """UnifiedPaintSettings, wherever this Blender version keeps them."""
    paint = get_paint(context)
    unified = getattr(paint, "unified_paint_settings", None) if paint else None
    if unified is not None:
        return unified
    tool_settings = getattr(context, "tool_settings", None)
    return getattr(tool_settings, "unified_paint_settings", None) if tool_settings else None


def _set(target, name, value):
    """Set a property if this version has it. Returns whether it did."""
    if target is None or not hasattr(target, name):
        return False
    try:
        setattr(target, name, value)
        return True
    except (AttributeError, TypeError, ValueError):
        # A read-only or library-linked brush - not worth failing Start Paint over.
        return False


def set_falloff(brush, preset):
    for name in _FALLOFF_ATTRS:
        if hasattr(brush, name):
            return _set(brush, name, preset)
    return False


def apply_alpha(context, settings):
    """Push the panel's brush settings onto the active brush, in alpha mode.

    Returns (ok, message). ok is False only when there is no brush to
    configure, which the caller reports as a hint rather than an error - the
    shell is already set up by then and painting works with whatever brush the
    artist picks.
    """
    brush = get_brush(context)
    if brush is None:
        return False, "No vertex paint brush is active - pick one in the toolbar."

    _set(brush, "blend", ERASE_BLEND if settings.erase else PAINT_BLEND)
    _set(brush, "size", int(settings.brush_size))
    _set(brush, "strength", float(settings.brush_strength))
    set_falloff(brush, settings.falloff)

    unified = _unified(context)
    if unified is not None:
        _set(unified, "size", int(settings.brush_size))
        _set(unified, "strength", float(settings.brush_strength))

    return True, ""


def apply_alpha_safe(context, settings):
    """apply_alpha() for property update callbacks, which must never raise."""
    try:
        apply_alpha(context, settings)
    except Exception:
        pass
