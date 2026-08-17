"""Density Check - colour the scene by triangle density.

The one tool in the tab that builds nothing: Analyze grades every mesh in
scope against a per-square-metre triangle budget and shows the verdict as the
object's viewport colour, Clear puts everything back. See geometry.py for the
scale, operators.py for what is measured.
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
