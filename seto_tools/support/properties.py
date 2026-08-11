"""What the user types into the bug report.

Three fields rather than one, deliberately. Blender has no multi-line
text field, so a single box would be a cramped one-liner - and the three
questions a maintainer ends up asking anyway ("what did you do, what
happened, what did you expect") get answered up front instead of over two
days of replies.

On the Scene rather than in the add-on preferences: a report is about the
file in front of you, and it should not follow you into the next one.
"""

import bpy


class SETO_PG_support(bpy.types.PropertyGroup):
    title: bpy.props.StringProperty(
        name="Title",
        description="One line: what is wrong",
        default="",
    )
    steps: bpy.props.StringProperty(
        name="What I did",
        description="The steps that led to it - which tool, which button",
        default="",
    )
    result: bpy.props.StringProperty(
        name="What happened",
        description="What the add-on actually did, including any red "
                    "message in the status bar",
        default="",
    )
    expected: bpy.props.StringProperty(
        name="What I expected",
        description="What you thought would happen instead",
        default="",
    )
    include_environment: bpy.props.BoolProperty(
        name="Include versions",
        description="Add your Blender, Seto Tools and Sollumz versions to "
                    "the report - the first thing anyone will ask for",
        default=True,
    )


_classes = (SETO_PG_support,)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.seto_support = bpy.props.PointerProperty(
        type=SETO_PG_support)


def unregister():
    del bpy.types.Scene.seto_support
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
