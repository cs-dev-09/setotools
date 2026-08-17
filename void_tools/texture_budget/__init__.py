"""Texture Budget - what the scene costs in VRAM, and which prop is why.

The second read-only tool in the Analysis section. Analyze colours every
mesh by the texture resolution it carries for its physical size and totals
the scene's texture memory; Finish puts the colours back. See geometry.py
for the texel-density scale and why vanilla GTA sets it so low.
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
