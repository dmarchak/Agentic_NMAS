"""routes/topology_view.py — the rcn-topology service's rendered graph.

Objective 1.2a(i) asks for the visualization from the previous labs, which is
the NetworkX-based `rcn-topology` service. The Topology tab had been
rediscovering the topology itself over CDP/LLDP — a second implementation of
something that already exists and is already configured under
Settings -> Topology service.

**Fetched server-side.** The browser arrives through the Cloudflare tunnel and
the service listens on the LAN only, so a browser-side request for the SVG
would work on the console at the lab host and show a broken image to every
remote viewer.

**Returned as an image, displayed with `<img>`, never inlined.** An SVG is a
document, not a picture: it can carry `<script>`, `<foreignObject>` and
external references, and injecting one into the page runs it with the page's
origin and session. Referenced through `<img>` the browser refuses to execute
any of it. The service is ours and is not expected to be hostile — but "we
trust the source" is a property of today's deployment, while `<img>` is a
property of the browser, and only one of those survives a change nobody
remembers making.
"""

import logging

from flask import Blueprint, Response, jsonify

log = logging.getLogger(__name__)

bp = Blueprint("topology_view", __name__, url_prefix="/topology/service")

#: Longer than the integration default: rendering a graph is real work, and a
#: service that takes six seconds is slow, not dead.
TIMEOUT = 15.0

#: Refused rather than passed through. A service that answers with HTML or
#: JSON where an SVG was expected is misconfigured, and handing that to an
#: `<img>` produces a broken-image icon with no reason attached.
SVG_TYPES = ("image/svg+xml", "text/xml", "application/xml")


def svg_url(base: str) -> str:
    """Where the SVG lives.

    A URL already ending in `.svg` is taken as given — the operator has
    pointed at an exact document and appending a path would break it.
    """
    base = (base or "").strip()
    if base.lower().endswith(".svg"):
        return base
    return base.rstrip("/") + "/topology.svg"


@bp.route("/svg")
def svg():
    """The rendered topology, as an image.

    Errors are returned as JSON with a reason rather than an empty 200: the
    page shows the reason beside a placeholder, because a blank area cannot
    be told from a topology with nothing in it.
    """
    from modules.integrations import get_integration
    from modules.settings_schema import get_setting

    client = get_integration("topology_service")
    if client is None:
        return jsonify({"ok": False, "error": "no topology service client"}), 503
    if not client.is_configured():
        return jsonify({"ok": False, "error": (
            "Topology service is not configured — set its URL in "
            "Settings → Topology service.")}), 503

    kind = (get_setting("topology_service_type", "json") or "").lower()
    if kind != "svg":
        # Not an error worth hiding: the panel renders an image, and a JSON
        # graph endpoint would arrive as bytes an <img> cannot show.
        log.info("topology service type is %r, not 'svg'", kind)

    url = svg_url(client.url)
    try:
        response = client.session().get(url, timeout=TIMEOUT)
    except Exception as exc:                   # noqa: BLE001
        log.warning("topology service %s: %s", url, exc)
        return jsonify({"ok": False,
                        "error": f"Could not reach the topology service: {exc}"}), 502

    if response.status_code >= 400:
        return jsonify({"ok": False,
                        "error": f"Topology service returned HTTP "
                                 f"{response.status_code}"}), 502

    content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()
    body = response.content
    looks_like_svg = b"<svg" in body[:2048].lower()
    if content_type not in SVG_TYPES and not looks_like_svg:
        return jsonify({"ok": False, "error": (
            f"Topology service answered with {content_type or 'an unknown type'}, "
            f"not an SVG. Check topology_service_url and its type setting.")}), 502

    out = Response(body, mimetype="image/svg+xml")
    # It is regenerated on the service's own schedule, and the panel busts the
    # cache itself with a timestamp. Caching here would make Refresh a lie.
    out.headers["Cache-Control"] = "no-store, max-age=0"
    # Defence in depth behind the <img>: even if this were ever rendered as a
    # document, nothing in it should run or reach out.
    out.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; sandbox")
    out.headers["X-Content-Type-Options"] = "nosniff"
    return out


@bp.route("/status")
def status():
    """Whether the panel can expect an image, and where it comes from."""
    from modules.integrations import get_integration
    from modules.settings_schema import get_setting

    client = get_integration("topology_service")
    configured = bool(client and client.is_configured())
    return jsonify({
        "ok": True,
        "configured": configured,
        "type": get_setting("topology_service_type", "json"),
        "url": svg_url(client.url) if configured else "",
    })
