"""nsot — Network Source of Truth.

The render context builder lives here. Later phases add the YAML variable
layers, parsers, and normalisation helpers described in docs/NSOT_PLAN.md.
"""

from modules.nsot.context import build_render_context

__all__ = ["build_render_context"]
