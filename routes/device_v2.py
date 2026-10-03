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
BUILT = ("overview", "intent", "history", "monitoring", "logs", "netbox", "neighbours")


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


def _netbox_ctx(ref, dev):
    from modules import device_netbox
    return {"device": dev, "list_name": ref.name, "nb": device_netbox.for_device(ref, dev)}


def _logs_ctx(ref, dev):
    from modules import device_logs
    return {"device": dev, "list_name": ref.name, "g": device_logs.for_device(dev)}


def _neighbours_ctx(ref, dev):
    from modules import neighbours
    return {"device": dev, "list_name": ref.name, "n": neighbours.for_device(ref, dev)}


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
    """The whole page, opened on the tab the URL names. A device onboarded
    and not yet reached is in no inventory, so its page is its onboarding
    state (the brief's pending page), never a 404."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        try:
            pending = device_page.find_pending(name)
        except Exception as exc:                      # noqa: BLE001
            log.warning("device_v2: pending onboardings could not be read for %s: %s", name, exc)
            pending = None
        if pending:
            ref, p = pending
            return _strict(render_template("v2/pending.html", p=p, list_name=ref.name, who=_who()))
        return refusal
    ref, dev = found
    tab = request.args.get("tab", "overview")
    tab = tab if tab in BUILT else "overview"
    ctx = {"device": dev, "list_name": ref.name, "tabs": TABS, "built": BUILT, "tab": tab,
           "answer": device_page.answering(dev), "who": _who(),
           "hw": device_page.hardware(ref, dev)}
    ctx.update(_overview_ctx(ref, dev) if tab == "overview" else
               _intent_ctx(ref, dev) if tab == "intent" else
               _history_ctx(ref, dev) if tab == "history" else
               _neighbours_ctx(ref, dev) if tab == "neighbours" else
               _logs_ctx(ref, dev) if tab == "logs" else
               _netbox_ctx(ref, dev) if tab == "netbox" else _monitoring_ctx(ref, dev))
    # An action's card opened without script (the menu row's href): drawn in place of the
    # tab, starting as the row's own request would.
    op = request.args.get("op")
    ctx["op_card"] = ({"state": "starting", "op": "capture", "host": dev.get("hostname", ""),
                       "list": ref.name, "back": tab} if op == "capture" else
                      _persist_card(ref, dev, tab) if op == "persist" else None)
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


@bp.route("/update-available", methods=["GET"])
def update_available():
    """The top bar's quiet "Update available" (the operator, 2026-10-02): drawn
    only while attention.update_available() says so, from the app-pushed
    reader's stored comparison for THIS running commit; empty otherwise,
    including when the release is a Needs attention row instead."""
    avail = None
    try:
        from modules import attention, reader_job
        from routes import health

        got = reader_job.read_cached("app-pushed")
        v = ((((got.get("doc") or {}).get("last_good") or {}).get("value")) or {}) \
            if got.get("state") == "ok" else {}
        if v and str(v.get("running") or "") == str(health._COMMIT or ""):
            avail = attention.update_available(v)
    except Exception as exc:                            # noqa: BLE001
        # News, never a problem: a failed read draws nothing here, and the
        # Needs attention source says the comparison could not be read.
        log.warning("v2 update indicator failed: %s", exc)
    return _strict(render_template("v2/_update_available.html", avail=avail))


@bp.app_context_processor
def _attention_trigger():
    """What re-reads Needs attention and the sidebar's count, on every v2 page: every key
    that can move a row (`attention.ATTENTION_KEYS`, ONE list) and the moment a row clears
    by time. Both fragments draw this string; neither keeps its own (the operator,
    2026-10-02: the count's hand-kept list lacked keys the page heard)."""
    from modules.attention import ATTENTION_KEYS, DUE_EVENT
    return {"attention_trigger": ", ".join(f"nmas:{k} from:body"
                                           for k in ATTENTION_KEYS + (DUE_EVENT,))}


@bp.route("/attention-count", methods=["GET"])
def attention_count():
    """The sidebar's Needs attention count: `needs_attention()`'s own badge, the same rows
    the page draws, with their worst level. The fragment is the WHOLE badge, its listener
    included: the badge it replaces (`outerHTML`) was a bare span, so it updated once after
    the page loaded and never again (the operator, 2026-10-02)."""
    try:
        from modules import attention
        b = attention.needs_attention()["badge"]
        return _strict(render_template("v2/_count.html", badge=b, ok=True))
    except Exception as exc:                            # noqa: BLE001
        log.warning("v2 attention count failed: %s", exc)
        return _strict(render_template("v2/_count.html", badge=None, ok=False))


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


@bp.route("/device/<name>/neighbours", methods=["GET"])
def neighbours(name):
    """The Neighbours tab (C38): the adjacencies committed intent implies,
    against what the device reports through Prometheus. Opens no session to
    the device."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_neighbours.html", **_neighbours_ctx(ref, dev)))


@bp.route("/device/<name>/logs", methods=["GET"])
def logs(name):
    """The Logs tab: the device's syslog as Loki holds it, heartbeats folded.
    Opens no session to the device."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_logs.html", **_logs_ctx(ref, dev)))


@bp.route("/device/<name>/netbox", methods=["GET"])
def netbox(name):
    """The NetBox tab, read-only: NetBox's record of the device and who owns
    it by NMAS's own provenance."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_netbox.html", **_netbox_ctx(ref, dev)))


# ---------------------------------------------------------------------------
# The device's actions on v2 (7.3; the mockup signed off 2026-10-02): each operation's card
# drawn in place of the tab's content. The preview, confirm and apply are the operation's
# own (`routes.golden.start_capture_preview`, `apply_captures`); these draw one card.
# ---------------------------------------------------------------------------

def _back(fields) -> str:
    """The tab a card returns to when it is cancelled or closed: the one it replaced."""
    back = (fields.get("back") or "").strip()
    return back if back in BUILT else "overview"


def _named_device(name, list_name, template="v2/_capture.html"):
    """``(ref, dev, refusal)`` for a WRITE path: the device in the list the card carries
    (a write path carries its list; only a read derives the active one)."""
    from modules.nsot import listref

    if not list_name or not listref.exists(list_name):
        return None, None, _strict(render_template(
            template, c={"state": "refused_list", "host": name,
                                   "list": list_name}), 400)
    try:
        ref, dev = device_page.find_device(name, ref=listref.resolve(list_name))
    except device_page.NoSuchDevice as exc:
        return None, None, _strict(render_template(
            template, c={"state": "failed", "host": name, "list": list_name,
                                   "error": str(exc)}), 404)
    return ref, dev, None


@bp.route("/device/<name>/capture", methods=["GET"])
def capture(name):
    """The capture card, starting: drawn in place of the tab, it starts its own read (a
    POST on load), so the card that waits for the read is the one that asked for it."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_capture.html", c={
        "state": "starting", "op": "capture", "host": dev.get("hostname", ""),
        "list": ref.name, "back": _back(request.args)}))


@bp.route("/device/<name>/capture/start", methods=["POST"])
def capture_start(name):
    """Start reading the device for its capture preview, as a job, and answer at once with
    the card that waits for it. A READ of the device: nothing is recorded."""
    from modules.nsot.restore import _devices_of
    from routes.golden import start_capture_preview

    ref, dev, refusal = _named_device(name, request.form.get("list", ""))
    if refusal is not None:
        return refusal
    job = start_capture_preview(ref.name, _devices_of(ref.name), [dev], fleet=False)
    return _strict(render_template("v2/_capture.html", c={
        "state": "reading", "op": "capture", "host": dev.get("hostname", ""),
        "list": ref.name, "job": job, "back": _back(request.form)}))


@bp.route("/device/<name>/capture/job/<job>", methods=["GET"])
def capture_job_card(name, job):
    """The capture card for its preview job: reading, the preview, or why there is none.
    Re-read when the job announces `capture_preview`."""
    from modules import device_actions, identity
    from modules.nsot import capture_job

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    from modules.preview_confirm import confirm_part
    c = device_actions.capture_card(ref, dev.get("hostname", ""), job, capture_job.get(job),
                                    viewer=dict(confirm_part(request, "approve"),
                                                actor=identity.identify(request).actor or ""))
    c.update(back=_back(request.args), ip=dev.get("ip", ""))
    return _strict(render_template("v2/_capture.html", c=c))


@bp.route("/device/<name>/capture/confirm", methods=["POST"])
def capture_confirm(name):
    """Record the device's golden, as the verified person, bound to the read the preview
    showed (`hash`): the apply reads it again and refuses one that moved. The result is
    drawn in place of the preview."""
    from modules import device_actions, identity
    from routes.golden import apply_captures

    ref, dev, refusal = _named_device(name, request.form.get("list", ""))
    if refusal is not None:
        return refusal
    host = dev.get("hostname", "")
    confirmed = (request.form.get("hash") or "").strip()
    if not confirmed:
        return _strict(render_template("v2/_capture.html", c={
            "state": "refused_hash", "host": host, "list": ref.name}), 400)
    got = apply_captures(ref.name, {host: confirmed}, fleet=False, acknowledged={},
                         approvals={})
    # Who is drawn as having recorded it: the identity the gate verified (the commit's
    # `Actor:` is written by the apply itself).
    ident = identity.identify(request)
    c = device_actions.capture_result_card(ref, host, got, confirmed, ident.actor or "",
                                           ident.kind or "")
    from modules.outbound import mask_payload
    c = mask_payload(c)
    c.update(back=_back(request.form), ip=dev.get("ip", ""))
    return _strict(render_template("v2/_capture.html", c=c))


@bp.route("/device/<name>/persist", methods=["GET"])
def persist(name):
    """The persist card: what saving the running config to startup would do and would not,
    its operands and checks, and the confirm bound to the plan's hash. A READ: the preview
    contacts no device (`persist_op.plan`), so it is drawn at once."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_persist.html",
                                   c=_persist_card(ref, dev, _back(request.args))))


def _persist_card(ref, dev, back):
    """The persist card for *dev*, drawn by the card's route and by the page itself."""
    from modules import device_actions, identity
    from modules.nsot import persist_op
    from modules.nsot.device_ops import busy_text
    from modules.outbound import mask_payload
    from modules.preview_confirm import confirm_part, persist_preview

    host = dev.get("hostname", "")
    preview = persist_preview(persist_op.plan(ref.name, host), busy=busy_text(ref.name, host),
                              request=request)
    c = device_actions.persist_card(ref, host, mask_payload(preview), viewer=dict(
        confirm_part(request, "confirm"), actor=identity.identify(request).actor or ""))
    c.update(back=back, ip=dev.get("ip", ""))
    return c


@bp.route("/device/<name>/persist/confirm", methods=["POST"])
def persist_confirm(name):
    """Save the device's running config to startup and read it back, as the verified person,
    holding the device, bound to the plan the card showed (`hash`): the same apply as
    `/persist/apply`. The result is drawn in place of the preview."""
    from modules import device_actions, identity
    from modules.nsot import persist_op
    from modules.outbound import mask_payload
    from modules.preview_confirm import persist_result

    ref, dev, refusal = _named_device(name, request.form.get("list", ""), "v2/_persist.html")
    if refusal is not None:
        return refusal
    host = dev.get("hostname", "")
    confirmed = (request.form.get("hash") or "").strip()
    if not confirmed:
        return _strict(render_template("v2/_persist.html", c={
            "state": "refused_hash", "host": host, "list": ref.name,
            "back": _back(request.form)}), 400)
    actor = identity.identify(request).actor or ""
    out = persist_op.apply(ref.name, host, actor=actor, confirmed_hash=confirmed)
    c = device_actions.persist_result_card(ref, host, out, mask_payload(
        persist_result(out, out.get("plan") or {}, actor)))
    c.update(back=_back(request.form), ip=dev.get("ip", ""))
    return _strict(render_template("v2/_persist.html", c=c))
