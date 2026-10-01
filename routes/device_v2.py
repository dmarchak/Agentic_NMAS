"""routes/device_v2.py — the device page in the redesign: THE SPIKE.

Approved by the operator on 2026-09-30 (NSOT_GUI_BRIEF 9b): the device
page's Overview and Monitoring tab, built in option A (server-rendered Jinja,
htmx for fragments, Alpine's CSP build for local state, one ES5 panel island
over uPlot, no build step), in the real app with real data, to be judged
first on look, smoothness and the phone, then on page weight, the CSP, lines
of code and whether the tests catch a planted defect.

Every route here is a READ. The page and its fragments carry the strict
policy (`csp.STRICT_POLICY`): no inline script, no inline style, no eval.
The device is addressed by NAME in the active list (the brief: an address
moves for a DHCP or ZTP device).
"""

import logging

from flask import Blueprint, jsonify, render_template, request

from modules import csp, device_page

log = logging.getLogger(__name__)

bp = Blueprint("device_v2", __name__, url_prefix="/v2")

TABS = [("overview", "Overview"), ("intent", "Intent"), ("history", "History"),
        ("monitoring", "Monitoring"), ("logs", "Logs"), ("netbox", "NetBox"),
        ("neighbours", "Neighbours"), ("ask", "Ask the device")]
BUILT = ("overview", "intent", "history", "monitoring")


def _strict(resp, code=200):
    from flask import make_response

    r = make_response(resp, code)
    r.headers["Content-Security-Policy"] = csp.STRICT_POLICY
    return r


def _who() -> dict:
    """The name chip: who is looking, through `identity.viewer()`, the same
    `identify()` the gate and `/identity/status` call. Never `request_actor()`,
    which answers only inside a gated request and so drew every person as
    unauthenticated on a GET page (the operator, 2026-09-30)."""
    from modules import identity

    ident = identity.viewer()
    if not ident.is_identified:
        return {"identified": False, "name": "Not identified", "initials": "?",
                "why": ident.reason or ident.outcome,
                "note": "you can look; a gated action will refuse"}
    name = (identity.service_label(ident.service_id) if ident.kind == "service"
            else ident.actor)
    return {"identified": True, "name": name, "kind": ident.kind,
            "initials": (name or "?")[:2].upper(), "why": "", "note": ""}


def _device_or_404(name):
    try:
        return device_page.find_device(name), None
    except device_page.NoSuchDevice as exc:
        return None, _strict(render_template("v2/not_found.html", why=str(exc), who=_who()), 404)


def _overview_ctx(ref, dev):
    return {"device": dev, "list_name": ref.name, "answer": device_page.answering(dev),
            "records": device_page.records(ref, dev), "checks": device_page.checks(ref, dev),
            "hw": device_page.hardware(ref, dev)}


def _intent_ctx(ref, dev):
    return {"device": dev, "list_name": ref.name, "iv": device_page.intent_view(ref, dev)}


def _history_ctx(ref, dev):
    return {"device": dev, "h": device_page.history(ref, dev)}


def _monitored_by(ref, dev) -> dict:
    """What this device is monitored by (P.9 d3; NSOT_GUI_BRIEF 14.3): the
    same cells Monitoring > Coverage draws, from its committed golden, for this
    device alone, and whether "Apply monitoring profile" is offered. A failure
    to compute it is said, never drawn as an empty section."""
    from modules import monitoring_coverage
    try:
        c = monitoring_coverage.fleet(ref, devices=[(ref, dict(dev))])
        row = next((d for d in c["devices"] if d["host"] == dev.get("hostname")), None)
        if row is None:
            return {"error": "the coverage computation returned no row for this device"}
        return {"list": ref.name, "columns": c["columns"], "row": row, "profile": c["profile"]}
    except Exception as exc:                      # noqa: BLE001
        log.warning("device_v2: monitored-by for %s could not be computed: %s",
                    dev.get("hostname"), exc)
        return {"error": f"{type(exc).__name__}: {exc}"}


def _monitoring_ctx(ref, dev):
    hw = device_page.hardware(ref, dev)
    return {"device": dev, "mb": _monitored_by(ref, dev), "m": device_page.monitoring(
        dev, chosen_uid=request.args.get("dashboard", ""), range_text=request.args.get("range", "1h"),
        streams=device_page.streams_telemetry(ref, dev),
        model=(hw.get("model") or "", hw.get("model_from") or ""))}


@bp.route("/device/<name>", methods=["GET"])
def device(name):
    """The whole page, opened on the tab the URL names."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    tab = request.args.get("tab", "overview")
    tab = tab if tab in BUILT else "overview"
    ctx = {"device": dev, "list_name": ref.name, "tabs": TABS, "built": BUILT, "tab": tab,
           "answer": device_page.answering(dev), "who": _who(),
           "hw": device_page.hardware(ref, dev)}
    ctx.update(_overview_ctx(ref, dev) if tab == "overview" else
               _intent_ctx(ref, dev) if tab == "intent" else
               _history_ctx(ref, dev) if tab == "history" else _monitoring_ctx(ref, dev))
    return _strict(render_template("v2/device.html", **ctx))


@bp.route("/device/<name>/overview", methods=["GET"])
def overview(name):
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_overview.html", **_overview_ctx(ref, dev)))


@bp.route("/device/<name>/monitoring", methods=["GET"])
def monitoring(name):
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_monitoring.html", **_monitoring_ctx(ref, dev)))


@bp.route("/device/<name>/status", methods=["GET"])
def status(name):
    """The answering badge, re-fetched when the reachability reader announces."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    _ref, dev = found
    return _strict(render_template("v2/_status.html", device=dev, answer=device_page.answering(dev)))


@bp.route("/device/<name>/panel/<uid>/<int:panel_id>", methods=["GET"])
def panel(name, uid, panel_id):
    """One device panel's data, for the browser to draw. Only a panel of that
    dashboard that selects the device, with the dashboard's own query."""
    try:
        ref, dev = device_page.find_device(name)
    except device_page.NoSuchDevice as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    payload, code = device_page.panel_data(dev, uid, panel_id, request.args.get("range", "1h"),
                                           streams=device_page.streams_telemetry(ref, dev))
    return jsonify(payload), code


@bp.route("/who", methods=["GET"])
def who():
    """The name chip on its own: a fragment resolving the viewer the same way
    the page does, so a v2 fragment is shown to see the verified identity."""
    return _strict(render_template("v2/_who.html", who=_who()))


@bp.route("/strip", methods=["GET"])
def strip():
    """The top bar's integration health, from the integration-health reader."""
    value, at, why = device_page._cached("integrations")
    rows = (value or {}).get("integrations") or []
    configured = [r for r in rows if r.get("state") != "not_configured"]
    down = [r for r in configured if r.get("state") != "up"]
    return _strict(render_template("v2/_strip.html", rows=configured, down=down, value_at=at, why=why,
                                   read=value is not None))


@bp.route("/attention-count", methods=["GET"])
def attention_count():
    """The sidebar's Needs attention count: rows that ask for action."""
    try:
        from modules import attention
        page = attention.needs_attention()
        n = sum(1 for r in page.get("rows") or [] if r.get("level") in ("danger", "warning"))
        return _strict(render_template("v2/_count.html", n=n, ok=True))
    except Exception as exc:                            # noqa: BLE001
        log.warning("v2 attention count failed: %s", exc)
        return _strict(render_template("v2/_count.html", n=None, ok=False))


@bp.route("/device/<name>/monitored-by", methods=["GET"])
def monitored_by(name):
    """The Monitoring tab's "Monitored by" section alone, redrawn when the
    goldens or job health move."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_monitored_by.html", device=dev, mb=_monitored_by(ref, dev)))


@bp.route("/device/<name>/history", methods=["GET"])
def history(name):
    """The History tab: one timeline of the device's golden and intent commits
    and its deploy and restore receipts."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_history.html", **_history_ctx(ref, dev)))


@bp.route("/device/<name>/intent", methods=["GET"])
def intent(name):
    """The Intent tab, read-only: the committed document, its last commit, and
    what the monitoring profile adds or the device excludes."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_intent.html", **_intent_ctx(ref, dev)))
