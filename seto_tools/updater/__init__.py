"""Update the add-on from inside Blender, only ever when asked.

Check for Updates asks GitHub for the latest release; Install Update
downloads it and installs it over this one. Nothing here runs on its
own - no startup check, no timers - and operators.py is the only file in
the whole add-on that can reach the network, which the suite enforces.
The box itself is drawn by the Support panel.
"""

from . import properties
from . import operators

_modules = (properties, operators)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
