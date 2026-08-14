"""Update the add-on from inside Blender.

Check for Updates asks GitHub for the latest release; Install Update
downloads it and installs it over this one. One quiet check also runs at
startup - once, off-thread, silent on failure, and off in preferences -
so the Updates panel's header can carry the news without being asked; see
auto.py for why that exception exists and how narrow it is kept. The
updater package is the only code in the add-on that can reach the
network, which the suite enforces.
"""

from . import properties
from . import operators
from . import ui
from . import auto

_modules = (properties, operators, ui, auto)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
