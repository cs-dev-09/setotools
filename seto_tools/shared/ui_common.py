"""Panel pieces every tool draws the same way.

Both of these were copy-pasted into all five tools, which is how Surface
Painter ended up without the Sollumz warning at all: it was the one tool where
nobody remembered to paste it, so it looked like the tool that worked without
Sollumz - right up to pressing Start Paint, which needs a decal.sps material
that only Sollumz can build.

Panels are the part of this add-on that breaks most often and the part a
headless test reaches least easily (Blender only calls draw() from the UI
thread), so having one copy of the code that draws them matters more here than
the line count suggests.
"""

import textwrap

from . import addon_prefs
from . import sollumz_integration as szi


def wrap(text, width):
    """Split a message into panel-width lines.

    A Blender label does not wrap, so a long status message is drawn straight
    off the edge of the panel unless it is split first. Never returns an empty
    list: a label with no lines silently draws nothing at all.
    """
    return textwrap.wrap(text, width) or [""]


def draw_sollumz_warning(layout):
    """Draw the "Sollumz not available" box. True if it did, meaning the caller
    should draw nothing else.

    Every tool here is built on Sollumz - the materials, the attributes, the
    Drawable hierarchy - so a panel that draws its buttons anyway is offering
    something that cannot work. Failing in the panel, with the reason, beats
    failing at the button.
    """
    available, message = szi.get_status_message()
    if available:
        return False
    box = layout.box()
    box.label(text="Sollumz not available:", icon='ERROR')
    col = box.column(align=True)
    for line in wrap(message, 40):
        col.label(text=line)
    # The one thing a user can do about it without leaving Blender. Detection
    # tries every enabled add-on, so reaching this at all means either it is
    # not enabled or it is somewhere unusual - and the second case is fixable
    # right here.
    box.operator("preferences.addon_show", text="Open Void Tools Preferences",
                 icon='PREFERENCES').module = addon_prefs.ADDON_PACKAGE
    return True
