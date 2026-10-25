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

    # A run id's shape, before any blueprint's rules are built (C785): `<run_id:run_id>`.
    from modules.nsot import reads
    app.url_map.converters["run_id"] = reads.url_converter()

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

    # Every request a v2 page makes after its first render names the network the page was
    # drawn for (W2's A1): written into its HTML as it leaves, in one place. Outside the try:
    # without it a page's redraws and buttons follow the person's stored choice instead.
    from routes import page_network
    page_network.install(app)

    # Every mutating route's response names the data it changed, so the
    # panels showing that data re-fetch (Stage 7.0, NSOT_STAGE7_GUI 6b).
    from modules import invalidation
    invalidation.install(app)

    # Every gated control draws its state from `may` (Stage 7 acceptance criterion 13):
    # `{{ gate('<kind>') }}` in the control's tag, its route's own gate kind.
    from modules import preview_confirm
    app.jinja_env.globals["gate"] = preview_confirm.control_gate

    # Every AI control draws its mark and whether hosted AI could answer now (PHASE8_PLAN
    # 15.13): `{% set c = ai_control('<name>') %}`, a name in modules/ai/controls.CONTROLS.
    # Imported when a page draws one, never at the app's import.
    def ai_control(name):
        from modules.ai import controls
        return controls.control(name)
    app.jinja_env.globals["ai_control"] = ai_control

    # A Content-Security-Policy on every HTML page (C88 (c)): the belt to
    # escaping's braces, bounding where injected script can send data and
    # what it can load; it cannot stop inline script running.
    from modules import csp
    csp.install(app)

    from routes.settings_integrations import bp as integrations_bp
    # Today's inventory-source banner's two routes (/inventory/source/<list>, /inventory/refresh/
    # <list>), the golden timeline's and capture's (/golden/*) and the monitoring profile's
    # (/templatize/profile*) left at 7.8 (2026-10-17, P7-27; restore point tag
    # `pre-remove/v1-pages`) with today's index, their one caller. `routes/golden.py` and
    # `routes/templatize.py` remain as helper modules with no blueprint, called by v2.
    from routes.identity import bp as identity_bp
    from routes.remote import bp as remote_bp
    from routes.jobs import bp as jobs_bp
    from routes.health import bp as health_bp
    from routes.operations import bp as operations_bp
    from routes.attention import bp as attention_bp
    # Today's retire, persist and rotate JSON routes (/retire/*, /persist/*, /rotate/*) left at
    # 7.8 (2026-10-17, P7-24; restore point tag `pre-remove/v1-actions`): each device page's
    # Actions (`routes/device_v2.py`) runs the same operations.
    from routes.breakglass import bp as breakglass_bp
    from routes.device_v2 import bp as device_v2_bp
    from routes.v2 import bp as v2_bp
    from routes.update import bp as update_bp
    from routes.restarts import bp as restarts_bp
    from routes.settings_v2 import bp as settings_v2_bp
    from routes.intent_v2 import bp as intent_v2_bp
    from routes.templates_v2 import bp as templates_v2_bp
    from routes.reads_v2 import bp as reads_v2_bp
    from routes.privileged_v2 import bp as privileged_v2_bp
    from routes.remote_v2 import bp as remote_v2_bp
    from routes.network_v2 import bp as network_v2_bp
    from routes.netbox_v2 import bp as netbox_v2_bp
    from routes.onboard_v2 import bp as onboard_v2_bp
    from routes.adopt_v2 import bp as adopt_v2_bp
    from routes.bulk_intent_v2 import bp as bulk_intent_v2_bp
    from routes.credential_profiles_v2 import bp as credential_profiles_v2_bp
    from routes.topology_v2 import bp as topology_v2_bp
    from routes.logs_v2 import bp as logs_v2_bp
    from routes.dhcp_v2 import bp as dhcp_v2_bp
    from routes.console_ztp_v2 import bp as console_ztp_v2_bp
    from routes.console_servers_v2 import bp as console_servers_v2_bp
    from routes.oob_onboard_v2 import bp as oob_onboard_v2_bp

    for bp in (integrations_bp, identity_bp,
               remote_bp,
               jobs_bp, health_bp,
               operations_bp, attention_bp, breakglass_bp, device_v2_bp, v2_bp, update_bp,
               restarts_bp,
               settings_v2_bp, intent_v2_bp, templates_v2_bp, reads_v2_bp, privileged_v2_bp,
               remote_v2_bp, network_v2_bp, netbox_v2_bp, onboard_v2_bp, adopt_v2_bp,
               bulk_intent_v2_bp, credential_profiles_v2_bp, topology_v2_bp, logs_v2_bp,
               dhcp_v2_bp, console_ztp_v2_bp, console_servers_v2_bp, oob_onboard_v2_bp):
        try:
            app.register_blueprint(bp)
            registered.append(bp.name)
        except Exception as exc:              # noqa: BLE001
            log.error("routes: could not register blueprint '%s': %s", bp.name, exc)

    log.info("routes: registered %d blueprint(s): %s",
             len(registered), ", ".join(registered) or "none")
    return registered
