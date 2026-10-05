"""The product's name, in ONE place (NSOT_STAGE7_PLAN section 19; approved 2026-10-05).

"Mercury Network Automation Platform", "Mercury" for short. Every user-facing place that names
the product reads these, so a later rename is one change. Internal names (modules, scripts,
services, settings) stay `nmas` until Stage 10 renames them with their host steps.
"""

PRODUCT_NAME = "Mercury Network Automation Platform"
PRODUCT_SHORT = "Mercury"
PRODUCT_TAGLINE = "Network Automation Platform"


def context() -> dict:
    """What a template reads: ``brand.short``, ``brand.name``, ``brand.tagline``."""
    return {"brand": {"name": PRODUCT_NAME, "short": PRODUCT_SHORT, "tagline": PRODUCT_TAGLINE}}
