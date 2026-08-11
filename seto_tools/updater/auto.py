"""The once-per-session check that puts the notification on the header.

This is the one deliberate exception to "the network waits for a press",
made at the owner's request so users learn about a release without
thinking to ask. It is kept as narrow as an automatic check can be:

- **Once per Blender start**, never again in the session, never on a
  schedule. The timer that starts it runs a single time and unregisters.
- **Off in preferences** turns it off entirely - the timer fires, sees
  the preference, and does nothing.
- The request itself is the same one the Check button sends: GitHub's
  public release listing, carrying nothing about the user or the file.
- The HTTP happens on a **worker thread**, because a slow connection at
  startup must cost Blender nothing; the thread writes into a plain
  module variable and a timer - the only safe way back onto the main
  thread - copies it into the WindowManager state and redraws the
  viewports so the header badge appears.

Failures are silent, deliberately. A startup check that cannot reach
GitHub has nothing useful to say; the Check button is there when the
answer matters enough to ask for it.
"""

import json
import threading
import urllib.request

import bpy

from ..shared import addon_prefs
from . import logic

_HEADERS = {"User-Agent": "seto-tools-updater",
            "Accept": "application/vnd.github+json"}

# Written by the worker thread, read by the timer. A plain attribute is
# enough: one writer, one reader, and the reader tolerates "not yet".
_result = None
_started = False


def _fetch():
    global _result
    try:
        request = urllib.request.Request(logic.RELEASES_LATEST,
                                         headers=_HEADERS)
        with urllib.request.urlopen(request, timeout=10) as response:
            _result = json.load(response)
    except Exception:
        _result = {}          # nothing to say - see the module docstring


def _apply():
    """Move the worker's answer onto the WindowManager, on the main thread."""
    if _result is None:
        return 1.0            # still fetching - look again in a second
    picked = logic.pick(_result)
    if picked is not None:
        tag, url, _size = picked
        if logic.is_newer(tag):
            for window_manager in bpy.data.window_managers:
                state = window_manager.seto_updater
                state.latest = tag
                state.download_url = url
                state.update_available = True
                state.status = (f"{tag} is available - you have "
                                f"{logic.current_str()}.")
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
    return None


def _start():
    """Runs once, shortly after startup, then never again."""
    global _started
    if _started:
        return None
    _started = True
    preferences = addon_prefs.get()
    if preferences is not None and not getattr(preferences,
                                               "auto_check_updates", True):
        return None
    threading.Thread(target=_fetch, daemon=True).start()
    bpy.app.timers.register(_apply, first_interval=1.0)
    return None


def register():
    # A few seconds in, so the check never competes with Blender's own
    # startup - and never at all in background mode, where there is no
    # user to notify and the timer would outlive the script.
    if not bpy.app.background:
        bpy.app.timers.register(_start, first_interval=4.0)


def unregister():
    for fn in (_start, _apply):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
