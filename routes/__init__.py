"""routes — Flask blueprints.

``app.py`` is monolithic by design for the features that predate this package,
but it is already 5,000+ lines, so new routes go here instead. ``app.py`` gains
one ``register_blueprints(app)`` call rather than more route bodies.

Conventions match the existing routes: JSON responses shaped
``{"ok": bool, "error": str, ...}`` and a module-level
``log = logging.getLogger(__name__)``.
"""

import logging

log = logging.getLogger(__name__)


def register_blueprints(app) -> list:
    """Register every blueprint on *app*. Returns the names registered.

    A blueprint that fails to import is logged and skipped rather than taking
    the whole app down — the existing routes in app.py must keep working.
    """
    registered = []

    from routes.settings_integrations import bp as integrations_bp
    from routes.netbox_safety import bp as netbox_safety_bp
    from routes.inventory import bp as inventory_bp
    from routes.golden import bp as golden_bp
    from routes.templatize import bp as templatize_bp
    from routes.templates import bp as templates_bp
    from routes.deploy import bp as deploy_bp

    for bp in (integrations_bp, netbox_safety_bp, inventory_bp, golden_bp,
               templatize_bp, templates_bp, deploy_bp):
        try:
            app.register_blueprint(bp)
            registered.append(bp.name)
        except Exception as exc:              # noqa: BLE001
            log.error("routes: could not register blueprint '%s': %s", bp.name, exc)

    log.info("routes: registered %d blueprint(s): %s",
             len(registered), ", ".join(registered) or "none")
    return registered
