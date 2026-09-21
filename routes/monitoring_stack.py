"""routes/monitoring_stack.py — the lab's monitoring stack, as NMAS sees it.

**Everything here is fetched server-side, and that is a requirement rather
than a preference.** The browser reaches NMAS through a Cloudflare tunnel;
Prometheus, Loki, Oxidized, Kea, NetBox and Grafana are LAN-only. A
browser-side `fetch` or an `<iframe>` would work on the console at the lab
host and show nothing at all to a remote viewer, which is every viewer that
matters for a demo. NMAS is on the LAN, so NMAS does the asking.

**One endpoint per tool, not one for all six.** A single aggregate endpoint
takes as long as its slowest member and fails as a unit, which is exactly the
behaviour the panel is supposed to avoid: one dead tool must not blank the
others. Six independent fetches run in parallel in the browser and each card
resolves on its own.

Read-only. No settings, no writes, no auth changes.
"""

import logging

from flask import Blueprint, jsonify

log = logging.getLogger(__name__)

bp = Blueprint("monitoring_stack", __name__, url_prefix="/monitoring/stack")

#: The tools the panel shows, in display order. Not `REGISTRY` in full:
#: nsot_git, s3 and topology_service are plumbing rather than monitoring, and
#: a panel that lists everything registered stops being a panel about the
#: monitoring stack.
PANEL = ("netbox", "prometheus", "loki", "oxidized", "kea", "grafana")

#: Longer than the 5s default. These run server-side while an operator waits
#: on one card, and a tool that takes six seconds is a slow tool, not a dead
#: one -- reporting it as dead would be wrong in the direction that causes
#: pointless investigation.
TIMEOUT = 8.0


@bp.route("/<name>")
def one(name: str):
    """Status for a single tool. Never raises, always shaped the same."""
    if name not in PANEL:
        return jsonify({"ok": False, "name": name,
                        "error": f"{name!r} is not on the monitoring panel"}), 404

    from modules.integrations import REGISTRY

    client_class = REGISTRY.get(name)
    if client_class is None:
        return jsonify({"ok": False, "name": name,
                        "error": "no client registered"}), 404

    label = getattr(client_class, "label", name)
    try:
        client = client_class(timeout=TIMEOUT)
        if not client.is_configured():
            # Not an error. An unconfigured tool is a decision, and showing it
            # in red teaches the operator to ignore red.
            return jsonify({"ok": True, "name": name, "label": label,
                            "state": "not_configured",
                            "message": "Not configured — set in Settings"})
        result = client.monitor()
    except Exception as exc:                   # noqa: BLE001
        # A broken client must not take the panel down with it, and the
        # failure must still be visible rather than logged and swallowed.
        log.warning("monitoring panel: %s raised: %s", name, exc)
        return jsonify({"ok": False, "name": name, "label": label,
                        "state": "down", "error": f"{type(exc).__name__}: {exc}"})

    if not result.get("ok"):
        return jsonify({"ok": False, "name": name, "label": label,
                        "state": "down",
                        "error": result.get("error") or "unreachable"})

    return jsonify({"ok": True, "name": name, "label": label, "state": "up",
                    "metrics": result.get("metrics", []),
                    "detail": result.get("detail", []),
                    "link": result.get("link")})


@bp.route("/")
def panel():
    """Which tools the panel holds. The browser fetches each one itself."""
    from modules.integrations import REGISTRY

    return jsonify({"ok": True, "tools": [
        {"name": name, "label": getattr(REGISTRY.get(name), "label", name)}
        for name in PANEL if name in REGISTRY]})
