"""What the user types into the bug report.

Blender has no multi-line text field. Nothing in the UI API wraps text
you can edit, so a box that grows as a paragraph fills it has to be built
out of the parts that do exist. Five attempts, because each one looked
right until it was used:

1. **A field per line, revealed as they fill, drawn as separate rows.**
   It typed fine and read as a new box appearing on every Enter.
2. **A fixed block of line fields inside a box, `emboss=False`** so the
   borders vanish and it reads as one area. It could not be typed into at
   all: an unembossed string field draws its text and takes no input.
3. **One field per question, `scale_y` to three rows.** `scale_y` scales
   everything inside the widget - the text floated in the middle of the
   box and the caret came out three rows high.
4. **A normal field at the top of a box with empty rows beneath.** Caret
   and text right at last, but a frame inside a frame: Blender draws a
   border on anything that takes typing.
5. **An aligned stack, revealed as it fills.** What is here. Aligned
   fields share their borders, so the stack reads as one frame rather
   than a pile of boxes, and the frame grows downwards a line at a time
   as the paragraph is written. The one honest cost left: a line does not
   wrap by itself - reaching the end of one and carrying on puts the rest
   of the sentence out of sight until you move to the next line.

`LINES` is the fixed size, and it is **one**. Every larger shape was
tried - stacks that grew as they filled, stacks that grew mid-word with
`TEXTEDIT_UPDATE`, fixed stacks of three - and each was either a panel
that moved under the user's hands or more rows than anyone filled in.
One field per question is the whole answer: it holds still, it is
obviously where to type, and a report that needs paragraphs wants a
.blend attached, not more lines here. The loop below survives so that a
bigger LINES works again if this is ever revisited.

On the Scene rather than in the add-on preferences: a report is about the
file in front of you, and it should not follow you into the next one.
"""

import bpy

# The three questions, in the order they are asked.
FIELDS = (
    ("steps", "What I did"),
    ("result", "What happened"),
    ("expected", "What I expected"),
)
LINES = 1


def _line_annotations():
    """One StringProperty per line of every question.

    Built rather than typed out: eighteen near-identical declarations is
    eighteen chances to typo one, and the panel walks them by name anyway.
    """
    annotations = {}
    for name, label in FIELDS:
        for index in range(LINES):
            annotations[f"{name}_{index}"] = bpy.props.StringProperty(
                name=label if index == 0 else "",
                description=f"{label} - line {index + 1}",
                default="",
                # The property updates on every keystroke, not on Enter -
                # which is what makes the frame grow *while* the line is
                # being written: the panel redraws, sees the line is no
                # longer empty, and draws the next one joined underneath.
                # Without this nothing changes on screen until the edit
                # is committed, and the growth reads as an extra box
                # appearing later rather than the frame extending.
                options={'TEXTEDIT_UPDATE'},
            )
    return annotations


def lines_of(settings, field):
    """Every line of `field`, trailing blanks dropped."""
    values = [getattr(settings, f"{field}_{index}") for index in range(LINES)]
    while values and not values[-1].strip():
        values.pop()
    return values


def text_of(settings, field):
    """`field` as one block of text, newlines and all."""
    return "\n".join(lines_of(settings, field))


def clear(settings):
    for name, _label in FIELDS:
        for index in range(LINES):
            setattr(settings, f"{name}_{index}", "")


class SETO_PG_support(bpy.types.PropertyGroup):
    __annotations__ = dict(
        title=bpy.props.StringProperty(
            name="Title",
            description="One line: what is wrong",
            default="",
        ),
        # No field for a screenshot: an image cannot travel in a URL, so
        # collecting one here would only be a detour on the way to
        # dragging it onto the issue by hand. The panel says so instead.
        include_environment=bpy.props.BoolProperty(
            name="Include versions",
            description="Add your Blender, Void Tools and Sollumz versions "
                        "to the report - the first thing anyone will ask for",
            default=True,
        ),
        **_line_annotations(),
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
