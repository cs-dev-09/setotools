"""Pre-Flight - the export test you would otherwise run in game.

Third of the read-only Analysis tools. It checks every mesh in scope for
the handful of things that pass in Blender and fail after export, lists
what it found with a button to jump to each object, and fixes nothing:
what to do about an unapplied scale is the author's call. See checks.py
for what is checked and why each one earns its place.
"""

from . import properties
from . import operators
from . import ui

_modules = (properties, operators, ui)


def register():
    for module in _modules:
        module.register()


def unregister():
    for module in reversed(_modules):
        module.unregister()
