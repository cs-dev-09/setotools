"""One layout vocabulary for the whole tab.

Six tools grew their panels separately and ended up saying the same things six
different ways: three spellings of the child-panel boilerplate, five copies of
the "Selected X" header box, Create buttons at three different sizes, and
settings listed as one long unlabelled column on the tools that had not been
split up yet.

Everything here is drawing only. No tool logic, no Sollumz, no `bpy.data` -
which is what lets `tests/panels.py` drive all of it against a stub layout.

The shape every tool panel now has:

    <tool panel>            what has to be decided BEFORE Create, then Create
      <child panel>         settings you set once - collapsed by default
      ...
      Selected X            the finished object's own settings, open, last

and inside a panel, related rows are grouped under a `section()` heading rather
than run together in one column. That is the whole convention.
"""

from . import sollumz_integration as szi
from . import ui_common

# Where a tool's own child panels sit, and where the "Selected X" panel sits.
# Explicit numbers rather than declaration order: Blender sorts children by
# bl_order, and two panels that both leave it at 0 come out in whatever order
# registration happened to run.
FIRST_CHILD = 0
MATERIAL_CHILD = 80
SELECTED = 90

# The N-panel tab every panel in this add-on lives in. One constant rather than
# the same string typed into sixteen classes: the tab is the add-on's name in
# the only place most users ever read it, and renaming it should be one edit.
TAB = "Seto Tools"


class ToolChildPanel:
    """Base for a collapsed settings panel under a tool.

    Subclasses set `bl_parent_id`, `bl_label`, `bl_idname` and `bl_order`.

    The poll matters: a child panel is a panel in its own right, and Blender
    draws it whether or not its parent drew anything. Surface Painter's five
    children used to come up fully populated on a machine with no Sollumz,
    under a parent that had just said the tool could not run.
    """
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return szi.is_sollumz_available()


class PlainChildPanel:
    """A collapsed settings panel under a tool that does **not** need Sollumz.

    `ToolChildPanel` hides itself when Sollumz is missing, which is right for
    every tool that ends up building a Sollumz material. It is wrong for a tool
    that only touches Blender: the Analysis tools avoid the question by having
    no children at all, but Materialize genuinely has four, and a machine with
    no working Sollumz is exactly the one that might still want to turn a
    diffuse image into a normal map.

    `tests/panels.py` accepts this base as an answer to the Sollumz poll rule.
    Reach for it only when the tool underneath really does run without Sollumz -
    the rule exists because Blender draws a child whether or not its parent drew
    anything, and five panels once came up fully populated under a parent that
    had just said the tool could not run.
    """
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = TAB
    bl_options = {'DEFAULT_CLOSED'}

    # Read by tests/panels.py. A subclass is free to write its own poll() - and
    # Materialize's Settings panel does, on whether an image has been picked -
    # so the contract cannot be checked by looking at where poll came from.
    # Declaring it is the honest version: this tool says it does not need
    # Sollumz, and the test takes it at its word for that panel only.
    needs_sollumz = False


class SelectedPanel:
    """Base for a tool's "Selected X" panel - the finished object's settings.

    Not `DEFAULT_CLOSED`, unlike the settings children: it only appears when
    one of the tool's objects is selected, and selecting it is the act of
    asking to edit it. Last of the children, by bl_order.
    """
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Seto Tools"
    bl_order = SELECTED

    def draw_header(self, context):
        self.layout.label(text="", icon='MODIFIER')


def section(layout, title, icon='NONE'):
    """A titled group of rows. Returns the column to draw them into.

    Aligned, so the rows read as one control rather than as a stack of
    unrelated ones, and titled, because "Alpha Center / Alpha Outer / Alpha
    Bottom / Alpha Top / Invert Fade" in a bare column is a wall - the same
    five rows under "Fade" are a setting.
    """
    box = layout.box()
    header = box.row()
    header.label(text=title, icon=icon)
    return box.column(align=True)


def create_button(layout, operator, text, icon):
    """The button the panel exists for.

    Deliberately taller than a normal row and always the last thing in the
    tool's own draw(): child panels are drawn after their parent, so this stays
    at the top of the tool's block whatever is expanded underneath it.
    """
    row = layout.row()
    row.scale_y = 1.4
    row.operator(operator, text=text, icon=icon)


def hint(layout, text, icon='INFO'):
    """A one-line note under the button, in the one place they all live."""
    box = layout.box()
    box.scale_y = 0.8
    box.label(text=text, icon=icon)


def edit_mode_hint(layout, context, ready_text="Settings stay live on the created strip."):
    """The "you are not in Edit Mode" note every edge tool draws."""
    if context.mode != 'EDIT_MESH':
        hint(layout, "Enter Edit Mode and select edges first.")
    else:
        hint(layout, ready_text)


def object_header(layout, obj, data, verb="rebuild"):
    """The identity block at the top of every "Selected X" panel.

    Name, face count, what it was built from, why the last update could not
    run, and the Live Update switch - five tools drew this, five times, with
    the wording drifting between them.
    """
    box = layout.box()
    row = box.row()
    row.label(text=obj.name, icon='OUTLINER_OB_MESH')
    row.label(text=f"{len(obj.data.polygons)} quads")
    # Editable, so the X beside it can cut the link. A generated object that
    # has been moved somewhere else of its own accord snaps back to its source
    # the next time any setting is touched; clearing this is how you keep it
    # where you put it. What it costs is the live rebuild, which the status
    # line then says plainly.
    box.prop(data, "source_object", text="From")

    if data.status:
        warn = layout.box()
        warn.alert = True
        col = warn.column(align=True)
        col.label(text=f"Cannot {verb}:", icon='ERROR')
        for line in ui_common.wrap(data.status, 38):
            col.label(text=line)

    layout.prop(data, "live_update")


def rebuild_button(layout, operator):
    """The manual rebuild, drawn only where it can do something.

    With Live Update on it is dead weight - the strip has already rebuilt by
    the time the button could be pressed.
    """
    layout.separator()
    layout.operator(operator, icon='FILE_REFRESH')


# Nothing here registers anything: these are layout helpers, and the module is
# imported by the tools' ui.py rather than by the add-on's register().
