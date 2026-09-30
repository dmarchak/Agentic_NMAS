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

    # The gate table's hook goes on first, and is NOT inside the try below:
    # an app that started without it would serve every route ungated, which
    # is the failure P.3 exists to end. A crash here is the right outcome.
    from modules import route_gates
    route_gates.install(app)

    # A read naming a list that does not exist is refused before any view
    # resolves a path (register C51). Outside the try for the same reason:
    # without it, 24 GETs create the list they are asked about.
    from routes import list_param
    list_param.install(app)

    # Every mutating route's response names the data it changed, so the
    # panels showing that data re-fetch (Stage 7.0, NSOT_STAGE7_GUI 6b).
    from modules import invalidation
    invalidation.install(app)

    # A Content-Security-Policy on every HTML page (C88 (c)): the belt to
    # escaping's braces, bounding where injected script can send data and
    # what it can load; it cannot stop inline script running.
    from modules import csp
    csp.install(app)

    from routes.settings_integrations import bp as integrations_bp
    from routes.netbox_safety import bp as netbox_safety_bp
    from routes.inventory import bp as inventory_bp
    from routes.golden import bp as golden_bp
    from routes.templatize import bp as templatize_bp
    from routes.templates import bp as templates_bp
    from routes.deploy import bp as deploy_bp
    from routes.identity import bp as identity_bp
    from routes.remote import bp as remote_bp
    from routes.monitoring_stack import bp as monitoring_stack_bp
    from routes.topology_view import bp as topology_view_bp
    from routes.onboard import bp as onboard_bp
    from routes.clab import bp as clab_bp
    from routes.freshness import bp as freshness_bp
    from routes.jobs import bp as jobs_bp
    from routes.health import bp as health_bp
    from routes.devices_view import bp as devices_view_bp
    from routes.operations import bp as operations_bp
    from routes.attention import bp as attention_bp
    from routes.retire import bp as retire_bp
    from routes.persist import bp as persist_bp
    from routes.rotate import bp as rotate_bp
    from routes.breakglass import bp as breakglass_bp
    from routes.device_v2 import bp as device_v2_bp

    for bp in (integrations_bp, netbox_safety_bp, inventory_bp, golden_bp,
               templatize_bp, templates_bp, deploy_bp, identity_bp,
               remote_bp, monitoring_stack_bp, topology_view_bp,
               onboard_bp, clab_bp, freshness_bp, jobs_bp, health_bp,
               devices_view_bp, operations_bp, attention_bp, retire_bp, persist_bp,
               rotate_bp, breakglass_bp, device_v2_bp):
        try:
            app.register_blueprint(bp)
            registered.append(bp.name)
        except Exception as exc:              # noqa: BLE001
            log.error("routes: could not register blueprint '%s': %s", bp.name, exc)

    log.info("routes: registered %d blueprint(s): %s",
             len(registered), ", ".join(registered) or "none")
    return registered
