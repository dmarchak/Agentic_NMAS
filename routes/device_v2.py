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


def _page_list() -> str:
    """The network the address names (``?list=``, every way in names it), or ""."""
    from routes.list_param import named_list
    return named_list(request)


def _page_ref():
    """The page's network (C494): the one the address names, else the active one. An unknown
    name raises `listref.UnknownList` (a GET naming one is refused before any view runs)."""
    from modules.nsot import listref

    named = _page_list()
    return listref.resolve(named) if named else listref.active()


def carry_list(endpoint, values):
    """Every device-page URL drawn while serving a page carries that page's network (C494), so
    a link, an hx-get or an hx-post resolves the device where the page found it, never in
    whichever network is active when it is clicked. A URL naming its own list keeps it."""
    from flask import g, has_request_context

    if "list" in values or not has_request_context():
        return
    name = g.get("device_list") or _page_list()
    if name:
        values["list"] = name


bp.url_defaults(carry_list)


def _device_or_404(name):
    """``((ref, dev), None)`` for *name* in the page's network, or ``(None, refusal)``; the
    refusal names the other networks that hold the device when the address named none."""
    from flask import g

    from modules.nsot import listref

    try:
        ref = _page_ref()
    except listref.UnknownList as exc:
        return None, _strict(render_template("v2/not_found.html", why=str(exc), name=name,
                                             who=_who()), 404)
    try:
        found = device_page.find_device(name, ref=ref)
    except device_page.NoSuchDevice as exc:
        elsewhere = [] if _page_list() else device_page.networks_holding(name, besides=ref.name)
        return None, _strict(render_template("v2/not_found.html", why=str(exc), name=name,
                                             elsewhere=elsewhere, who=_who()), 404)
    g.device_list = found[0].name
    return found, None


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
    from routes.intent_v2 import may_commit

    ctx = {"device": dev, "list_name": ref.name, "iv": device_page.intent_view(ref, dev),
           "may_edit": may_commit().get("may")}
    # `?tab=intent&edit=1` opens H's editor in place (Templates board B's "Acknowledge it on
    # the Intent tab"; Edit again after a commit), without script too.
    if request.args.get("edit"):
        from routes.intent_v2 import editor_ctx
        ctx["ed"] = editor_ctx(ref, dev)
    return ctx


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
        dev, ref.name, chosen_uid=request.args.get("dashboard", ""), range_text=request.args.get("range", "1h"),
        streams=device_page.streams_telemetry(ref, dev),
        model=(hw.get("model") or "", hw.get("model_from") or ""))}


def _retired(name):
    """``(list ref, record)`` for a device retired from the active list (a read may derive its
    list), from its retire commit (`retire.retired_record`), or None. An unreadable history
    is logged and is not a record."""
    from modules.nsot import retire

    try:
        ref = _page_ref()
        rec = retire.retired_record(ref.repo_dir, name)
    except Exception as exc:                          # noqa: BLE001
        log.warning("device_v2: the retire record could not be read for %s: %s", name, exc)
        return None
    return (ref, rec) if rec else None


@bp.route("/device/<name>", methods=["GET"])
def device(name):
    """The whole page, opened on the tab the URL names. A device onboarded
    and not yet reached is in no inventory, so its page is its onboarding
    state (the brief's pending page), never a 404."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        try:
            pending = device_page.find_pending(name, ref=_page_ref())
        except Exception as exc:                      # noqa: BLE001
            log.warning("device_v2: pending onboardings could not be read for %s: %s", name, exc)
            pending = None
        if pending:
            ref, p = pending
            return _strict(render_template("v2/pending.html", p=p, list_name=ref.name, who=_who()))
        # A device that LEFT shows its retired record (C185; board 12), never a bare 404.
        retired = _retired(name)
        if retired:
            ref, rec = retired
            return _strict(render_template("v2/retired.html", r=rec, name=name,
                                           list_name=ref.name, who=_who(),
                                           finish=_finish_state(name, ref.name, rec)))
        return refusal
    ref, dev = found
    tab = request.args.get("tab", "overview")
    tab = tab if tab in BUILT else "overview"
    ctx = {"device": dev, "list_name": ref.name, "tabs": TABS, "built": BUILT, "tab": tab,
           "answer": device_page.answering(dev), "who": _who(),
           "hw": device_page.hardware(ref, dev),
           # Revert and Retry are offered only while a rollback block stands (board 11): one
           # read of the record.
           "block": _block_state(ref, dev),
           # Drained by a person (modules/drained.py): the header's badge, the menu's row.
           "drained": _drained_now(ref, dev)}
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
                      _persist_card(ref, dev, tab) if op == "persist" else
                      _rotate_starting(ref, dev, tab) if op == "rotate" else
                      _deploy_card(ref, dev, tab, {}, focus=request.args.get("focus", "")) if op == "deploy" else
                      _restore_card(ref, dev, tab, request.args) if op == "restore" else
                      _revert_card(ref, dev, tab, request.args) if op == "revert" else
                      _retry_card(ref, dev, tab, request.args) if op == "retry" else
                      _seed_card(ref, dev, tab) if op == "seed" else
                      _drained_card(ref, dev, tab) if op == "drained" else
                      _retire_card(ref, dev, tab, request.args) if op == "retire" else None)
    return _strict(render_template("v2/device.html", **ctx))


@bp.route("/device/<name>/actions", methods=["GET"])
def actions_menu(name):
    """The Actions menu alone (C507), read now: the page re-reads it on every key that changes
    what it offers (a rollback recorded or lifted, intent, goldens, a deploy, a hold, the
    inventory, the device's state), so Revert and Retry appear or grey without a reload."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_actions_menu.html", device=dev, list_name=ref.name,
                                   tab=_back(request.args), block=_block_state(ref, dev),
                                   drained=_drained_now(ref, dev)))


# ---------------------------------------------------------------------------
# Drained (the operator, 2026-10-06: the smallest form, approved without a mockup: a badge,
# and a Set/Clear card in the Actions menu). A person's recorded word; nothing is sent.
# ---------------------------------------------------------------------------

def _drained_now(ref, dev) -> dict:
    """The device's drained event if it is drained now, with its words, else None."""
    from modules import drained as D
    now = D.state_of(ref.name, dev.get("hostname", ""))
    return dict(now, words=D.words(now)) if now else None


def _drained_card(ref, dev, back, **extra):
    host = dev.get("hostname", "")
    now = _drained_now(ref, dev)
    c = {"op": "drained", "state": "preview", "host": host, "list": ref.name, "back": back,
         "drained": now, "want": "cleared" if now else "drained", "why": "", "refusal": ""}
    c.update(extra)
    return c


@bp.route("/device/<name>/drained", methods=["GET"])
def drained(name):
    """The Drained card: set the mark, or clear it, with a reason. A READ."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_drained.html",
                                   c=_drained_card(ref, dev, _back(request.args))))


@bp.route("/device/<name>/drained/badge", methods=["GET"])
def drained_badge(name):
    """The header's Drained badge alone, re-read when a mark is set or cleared. A READ."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_drained_badge.html", device=dev,
                                   drained=_drained_now(ref, dev)))


@bp.route("/device/<name>/drained/confirm", methods=["POST"])
def drained_confirm(name):
    """Mark the device drained, or clear the mark, as the verified person, with a reason,
    recorded in the network's store (`modules/drained.py`). Nothing is sent to the device. A
    refusal is drawn in the card, naming why, and records nothing."""
    from modules import drained as D, identity

    ref, dev, refusal = _named_device(name, request.form.get("list", ""), "v2/_drained.html")
    if refusal is not None:
        return refusal
    # The verified person, never a name the form carries; no person, no mark.
    who = identity.identify(request)
    actor = who.actor if who.is_identified else ""
    want, why = request.form.get("state", ""), request.form.get("why", "")
    back = _back(request.form)
    try:
        event = D.mark(ref.name, dev.get("hostname", ""), want, why=why, by=actor,
                       verified=identity.actor_verification(actor) if actor else "none")
    except D.Refused as exc:
        return _strict(render_template("v2/_drained.html", c=_drained_card(
            ref, dev, back, why=why, refusal=str(exc))), 409)
    return _strict(render_template("v2/_drained.html", c={
        "op": "drained", "state": "result", "host": dev.get("hostname", ""), "list": ref.name,
        "back": back, "event": event,
        "words": (D.words(event) if event["state"] == D.DRAINED else
                  f"cleared by {event['by']} at {event['at']}: {event['why']}")}))


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
    payload, code = device_page.panel_data(dev, ref.name, uid, panel_id,
                                           request.args.get("range", "1h"),
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
    down = [r for r in configured if r.get("state") not in ("up", "refused")]
    refused = [r for r in configured if r.get("state") == "refused"]
    return _strict(render_template("v2/_strip.html", rows=configured, down=down, refused=refused,
                                   value_at=at, why=why,
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


@bp.app_context_processor
def _brand():
    """The product's name for every page (`modules.brand`, the one place it is kept)."""
    from modules import brand
    return brand.context()


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
    from flask import g

    from modules.nsot import listref

    if not list_name or not listref.exists(list_name):
        return None, None, _strict(render_template(
            template, c={"state": "refused_list", "host": name,
                                   "list": list_name}), 400)
    page = _page_list()
    if page and page != list_name:
        # The confirm was drawn for one network and sent from a page of another (C494): which
        # device it means is not knowable, so nothing is done, naming both.
        return None, None, _strict(render_template(
            template, c={"state": "failed", "host": name, "list": list_name,
                         "error": (f"this confirm carries the network {list_name!r} its "
                                   f"preview was made in, and was sent from a page of "
                                   f"{page!r}; open {name} in the network you mean and preview "
                                   "again")}), 409)
    g.device_list = list_name
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


def _rotate_starting(ref, dev, back):
    return {"state": "starting", "op": "rotate", "host": dev.get("hostname", ""),
            "list": ref.name, "back": back}


@bp.route("/device/<name>/rotate", methods=["GET"])
def rotate(name):
    """The rotate card, starting: it asks for its own preview (a POST on load), whose plan
    reads the device's account line live, so the card says it is reading meanwhile."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_rotate.html",
                                   c=_rotate_starting(ref, dev, _back(request.args))))


@bp.route("/device/<name>/rotate/preview", methods=["POST"])
def rotate_preview(name):
    """The rotation's plan, drawn as the card: the preflight READS the device's account line
    live (`rotate_op.plan`), the program masked, the fingerprint to confirm. Changes nothing."""
    from modules import device_actions, identity
    from modules.nsot import rotate_op
    from modules.nsot.device_ops import busy_text
    from modules.outbound import mask_payload
    from modules.preview_confirm import confirm_part
    from modules.preview_confirm import rotate_preview as _preview

    ref, dev, refusal = _named_device(name, request.form.get("list", ""), "v2/_rotate.html")
    if refusal is not None:
        return refusal
    host = dev.get("hostname", "")
    preview = _preview(rotate_op.plan(ref.name, host), busy=busy_text(ref.name, host),
                       request=request)
    c = device_actions.rotate_card(ref, host, mask_payload(preview), viewer=dict(
        confirm_part(request, "confirm"), actor=identity.identify(request).actor or ""))
    c.update(back=_back(request.form), ip=dev.get("ip", ""))
    return _strict(render_template("v2/_rotate.html", c=c))


@bp.route("/device/<name>/rotate/confirm", methods=["POST"])
def rotate_confirm(name):
    """Start the confirmed rotation as a job, as the verified person, bound to the plan's
    fingerprint: the same confirm as `/rotate/apply` (`rotate_op.confirm_and_start`). The card
    then waits for the job's announcement."""
    from modules import identity
    from modules.nsot import rotate_op

    ref, dev, refusal = _named_device(name, request.form.get("list", ""), "v2/_rotate.html")
    if refusal is not None:
        return refusal
    host = dev.get("hostname", "")
    back = _back(request.form)
    confirmed = (request.form.get("fingerprint") or "").strip()
    if not confirmed:
        return _strict(render_template("v2/_rotate.html", c={
            "state": "refused_hash", "host": host, "list": ref.name, "back": back}), 400)
    got = rotate_op.confirm_and_start(ref.name, host, confirmed,
                                      actor=identity.identify(request).actor or "",
                                      ident=identity.verified_identity())
    if "error" in got:
        return _strict(render_template("v2/_rotate.html", c={
            "state": "refused", "host": host, "list": ref.name, "back": back,
            "error": got["error"]}), got["status"])
    from modules import device_actions
    return _strict(render_template("v2/_rotate.html", c={
        "state": "rotating", "host": host, "list": ref.name, "back": back,
        "job": got["job"], "steps": device_actions.job_steps("rotate", ref.name, host)}))


@bp.route("/device/<name>/rotate/job/<job>", methods=["GET"])
def rotate_job_card(name, job):
    """The rotate card for its job: rotating, its result, or why there is none. Re-read when
    the job announces `rotation`."""
    from modules import device_actions
    from modules.nsot import capture_job

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    c = device_actions.rotate_job_card(ref, dev.get("hostname", ""), job, capture_job.get(job))
    c.update(back=_back(request.args), ip=dev.get("ip", ""))
    return _strict(render_template("v2/_rotate.html", c=c))


@bp.route("/device/<name>/when-free", methods=["GET"])
def when_free(name):
    """For a card refused because another operation held its device, re-read when a hold
    ends (`device_holds`): 204, nothing redrawn, while the device is still held; once it is
    free, the operation's card drawn again from its start. Reads one lock file."""
    from modules.nsot.device_ops import busy_text

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    if busy_text(ref.name, dev.get("hostname", "")):
        return _strict("", 204)
    op, back = request.args.get("op", ""), _back(request.args)
    if op == "persist":
        return _strict(render_template("v2/_persist.html", c=_persist_card(ref, dev, back)))
    if op == "rotate":
        return _strict(render_template("v2/_rotate.html", c=_rotate_starting(ref, dev, back)))
    if op == "deploy":
        # The held card's redraw sends its form (C473): the ticks and reasons survive.
        return _strict(render_template("v2/_deploy.html",
                                       c=_deploy_card(ref, dev, back, request.args)))
    if op == "restore":
        return _strict(render_template("v2/_restore.html",
                                       c=_restore_card(ref, dev, back, request.args)))
    if op == "seed":
        return _strict(render_template("v2/_seed.html", c=_seed_card(ref, dev, back)))
    if op == "retire":
        return _strict(render_template("v2/_retire.html",
                                       c=_retire_card(ref, dev, back, request.args)))
    if op == "revert":
        return _strict(render_template("v2/_revert.html",
                                       c=_revert_card(ref, dev, back, request.args)))
    if op == "retry":
        return _strict(render_template("v2/_retry.html",
                                       c=_retry_card(ref, dev, back, request.args)))
    return _strict(render_template("v2/_capture.html", c={
        "state": "starting", "op": "capture", "host": dev.get("hostname", ""),
        "list": ref.name, "back": back}))


# ---------------------------------------------------------------------------
# Deploy, with Mode B (7.3; the device-actions canvas, boards 5 and 6)
# ---------------------------------------------------------------------------

def _deploy_form(fields):
    """What the deploy card's form carries: the residue ticked for removal (by id), each
    ticked line's stated reason, and each dangerous line's (by its index in the plan)."""
    getlist = getattr(fields, "getlist", lambda k: [])
    picked = [i for i in getlist("rm") if i]
    reasons = {i: (fields.get(f"why::{i}") or "").strip() for i in picked}
    danger = {}
    for k in list(fields.keys()):
        if k.startswith("dz::") and k[4:].isdigit():
            danger[int(k[4:])] = (fields.get(k) or "").strip()
    return picked, reasons, danger


def _declare_form(fields):
    """What the card's Expected effects carry (C506 phase 3): ``(raw, pending)``. *raw*: each
    declaration already made (a hidden `decl`, less any ticked `undecl`), then each new one
    whose fields are complete and whose reason has the shape of one; *pending*: the new one's
    fields as typed, with why it is not declared yet, so the card keeps them."""
    import json

    from modules.nsot.authorisation import reason_problem

    getlist = getattr(fields, "getlist", lambda k: [])
    dropped = {i for i in getlist("undecl") if i.isdigit()}
    raw = []
    for i, text in enumerate(getlist("decl")):
        if str(i) in dropped:
            continue
        try:
            item = json.loads(text)
        except ValueError:
            continue
        if isinstance(item, dict):
            raw.append(item)
    got = {k: (fields.get(k) or "").strip()
           for k in ("mv_id", "mv_to", "mv_why", "end_id", "end_why", "rt_why")}
    pending = dict(got, problem="", open="")
    for kind, need, why in (("moves", ("mv_id", "mv_to"), "mv_why"),
                            ("ends", ("end_id",), "end_why"), ("routes", (), "rt_why")):
        if not (got[why] or any(got[k] for k in need)):
            continue
        pending["open"] = kind
        missing = [k for k in need if not got[k]]
        problem = ("choose " + (" and ".join({"mv_id": "the adjacency", "mv_to": "where it moves",
                                              "end_id": "the adjacency"}[k] for k in missing))
                   if missing else reason_problem({"line": "this declaration",
                                                   "reason": got[why]}))
        if problem:
            pending["problem"] = problem
            continue
        raw.append({"kind": kind, "reason": got[why],
                    **({"id": got["mv_id"], "to": got["mv_to"]} if kind == "moves" else {}),
                    **({"id": got["end_id"]} if kind == "ends" else {})})
        for k in need + (why,):
            pending[k] = ""
        pending["open"] = ""
    return raw, pending


def _deploy_card(ref, dev, back, fields, focus=""):
    """The deploy card for *dev*: THE plan (`routes.deploy.plan_devices`, captured configs
    only, no device contacted) planned again with what the form carries, each stated reason
    in the hash, and the confirm built HERE from the unmasked plan's hashes, so it sends
    exactly the program on the screen."""
    from modules import device_actions, identity
    from modules.nsot.authorisation import key
    from modules.nsot.expected_effects import raw_of
    from modules.outbound import mask_payload
    from modules.preview_confirm import confirm_part, deploy_preview
    from routes.deploy import plan_devices

    host = dev.get("hostname", "")
    picked, reasons, danger = _deploy_form(fields)
    raw_declared, pending = _declare_form(fields)
    remove = {host: picked} if picked else {}
    declare = {host: raw_declared} if raw_declared else {}
    entry = plan_devices(ref.name, [host], remove=remove, declare=declare)[0]
    rm = entry.get("removals") or {}
    authorise = [{"line": k, "reason": reasons[rid]}
                 for rid, k in zip(rm.get("ids") or [], rm.get("keys") or [])
                 if reasons.get(rid)]
    authorise += [{"line": key(line), "reason": danger[i]}
                  for i, line in enumerate(entry.get("dangerous") or []) if danger.get(i)]
    if authorise:
        entry = plan_devices(ref.name, [host], remove=remove,
                             authorise={host: authorise}, declare=declare)[0]
    out = mask_payload({"entry": entry, "preview": deploy_preview([entry], request, scope="")})
    c = device_actions.deploy_card(
        ref, host, out["entry"], out["preview"],
        viewer=dict(confirm_part(request, "confirm"), actor=identity.identify(request).actor or ""),
        reasons=reasons, danger_reasons=danger, pending=pending)
    if c["may"]:
        rm = entry.get("removals") or {}
        # From the UNMASKED plan, as the hashes are: what is declared is what was hashed.
        c["confirm"] = {"capture_hash": entry.get("capture_hash", ""),
                        "command_hash": entry.get("command_hash", ""),
                        "remove": list(rm.get("ids") or []), "authorise": authorise,
                        "declare": [raw_of(d) for d in entry.get("declared") or []]}
    c.update(back=back, ip=dev.get("ip", ""))
    if focus == "removal":
        c["focus"] = "removal"
    return c


@bp.route("/device/<name>/deploy", methods=["GET"])
def deploy(name):
    """The deploy card: the exact program from committed intent, merge-only, what is left on
    the device (tick a line for removal, Mode B, with a reason), what will not happen, the
    operands and checks, and the confirm bound to the program's hash. A READ: the plan reads
    captured configs only, so it is drawn at once; the form plans again on each change."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    c = _deploy_card(ref, dev, _back(request.args), request.args,
                     focus=request.args.get("focus", ""))
    # The card's own re-plans (its form, aimed at the card) keep the focus and are only redrawn.
    if c.get("focus") != "removal" or request.headers.get("HX-Target") == "device-op":
        return _strict(render_template("v2/_deploy.html", c=c))
    # The Actions menu's "Remove lines (Mode B)…" (C403): removals are made as part of a
    # deploy, so the row opens THIS card at what is left on the device. With nothing
    # removable it opens nothing: the row itself says so, in place, and the menu stays open.
    residue = c.get("residue") or []
    if c.get("state") == "preview" and not any(not r.get("why_not") for r in residue):
        why = (f"{dev.get('hostname', '')} holds no line its committed intent lacks"
               if not residue else
               f"of the {len(residue)} line(s) {dev.get('hostname', '')} holds and its intent "
               f"lacks, none can be removed here ({residue[0].get('why_not')})")
        return _strict(render_template("v2/_removal_row.html", why=why))
    resp = _strict(render_template("v2/_deploy.html", c=c))
    resp.headers["HX-Retarget"] = "#tab-body"
    resp.headers["HX-Reswap"] = "innerHTML show:#removal:top"
    resp.headers["HX-Trigger"] = "nmas-close-menu"
    return resp


@bp.route("/device/<name>/deploy/confirm", methods=["POST"])
def deploy_confirm(name):
    """Deploy the confirmed program as the verified person, as a job holding the device (the
    same apply as `/deploy/apply` and the batch apply, `deploy_job`): the program is computed
    again and a different hash refuses with nothing sent. Answers with the card that follows
    the job."""
    import json

    from modules import deploy_job, device_actions, identity

    ref, dev, refusal = _named_device(name, request.form.get("list", ""), "v2/_deploy.html")
    if refusal is not None:
        return refusal
    host = dev.get("hostname", "")
    capture_hash = (request.form.get("capture_hash") or "").strip()
    command_hash = (request.form.get("command_hash") or "").strip()
    if not capture_hash or not command_hash:
        return _strict(render_template("v2/_deploy.html", c={
            "state": "refused_hash", "host": host, "list": ref.name,
            "back": _back(request.form)}), 400)
    try:
        remove = json.loads(request.form.get("remove") or "[]")
        authorise = json.loads(request.form.get("authorise") or "[]")
        # The declared effects (C506 phase 3), in the hash: checked again at apply.
        declare = json.loads(request.form.get("declare") or "[]")
    except ValueError:
        return _strict(render_template("v2/_deploy.html", c={
            "state": "refused_hash", "host": host, "list": ref.name,
            "back": _back(request.form)}), 400)
    job = deploy_job.start(
        ref.name, [host], {host: capture_hash}, {host: command_hash},
        authorise={host: authorise} if authorise else {}, remove={host: remove} if remove else {},
        scope="", actor=identity.identify(request).actor or "",
        actor_kind=getattr(identity.identify(request), "kind", ""),
        ident=identity.verified_identity(), declare={host: declare} if declare else None)
    return _strict(render_template("v2/_deploy.html", c={
        "state": "deploying", "op": "deploy", "host": host, "list": ref.name, "job": job,
        "back": _back(request.form), "steps": device_actions.job_steps("deploy", ref.name, host)}))


# ---------------------------------------------------------------------------
# Restore from a moment (7.3; the device-actions canvas, boards 9 and 10)
# ---------------------------------------------------------------------------

def _restore_form(fields):
    """What the restore card's form carries: the moment, whether to un-onboard (a moment that
    predates the device's onboarding), and each flagged line's stated reason (by its index)."""
    moment = (fields.get("moment") or "").strip()
    un_onboard = (fields.get("un_onboard") or "") == "1"
    danger = {}
    for k in list(fields.keys()):
        if k.startswith("dz::") and k[4:].isdigit():
            danger[int(k[4:])] = (fields.get(k) or "").strip()
    return moment, un_onboard, danger


def _restore_card(ref, dev, back, fields):
    """The restore card for *dev*: the chooser when no moment is chosen, else THE restore plan
    (`routes.golden.restore_plan`, captured configs only, no device contacted) at that moment,
    planned again with each stated reason (keyed from the UNMASKED plan, as the deploy card's),
    masked on the way out, the confirm built HERE from its hashes."""
    from modules import device_actions, identity
    from modules.nsot.authorisation import key
    from modules.nsot.restore import WithdrawnBaseline
    from modules.outbound import mask_payload
    from modules.preview_confirm import confirm_part
    from routes.golden import restore_plan, restore_points_for

    host = dev.get("hostname", "")
    moment, un_onboard, danger = _restore_form(fields)
    if not moment:
        show_all = (fields.get("all") or "") == "1"
        c = device_actions.restore_choose_card(
            ref, host, restore_points_for(
                ref.name, host, checked=None if show_all else device_actions.RESTORE_SHOWN),
            show_all=show_all, chosen=(fields.get("chosen") or ""))
        c.update(back=back, ip=dev.get("ip", ""))
        return c
    asked = {"un_onboard": [host] if un_onboard else None, "req": request}
    authorise = []
    try:
        plan = restore_plan(ref.name, moment, [host], **asked)
        entry = next((d for d in plan.get("devices") or [] if d.get("device") == host), None)
        if entry is not None:
            flagged = list(entry.get("dangerous") or []) + list(entry.get("secret_readded") or [])
            authorise = [{"line": key(line), "reason": danger[i]}
                         for i, line in enumerate(flagged) if danger.get(i)]
            if authorise:
                plan = restore_plan(ref.name, moment, [host], authorise={host: authorise},
                                    **asked)
    except WithdrawnBaseline as exc:
        c = {"op": "restore", "state": "not_restorable", "host": host, "list": ref.name,
             "moment": moment, "moment_words": moment, "reason": str(exc), "detail": ""}
        c.update(back=back, ip=dev.get("ip", ""))
        return c
    c = device_actions.restore_card(
        ref, host, moment, mask_payload(plan),
        viewer=dict(confirm_part(request, "confirm"), actor=identity.identify(request).actor or ""),
        danger_reasons=danger, un_onboard=un_onboard)
    if c.get("confirm"):
        entry = next(d for d in plan["devices"] if d.get("device") == host)
        c["confirm"] = {"capture_hash": entry.get("capture_hash", ""),
                        "command_hash": entry.get("command_hash", ""), "authorise": authorise}
    c.update(back=back, ip=dev.get("ip", ""))
    return c


@bp.route("/device/<name>/restore", methods=["GET"])
def restore(name):
    """Restore from a moment: the chooser (board 9), each moment with its credential state. A
    READ: the points and their credential states come from the repository."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_restore.html",
                                   c=_restore_card(ref, dev, _back(request.args), request.args)))


@bp.route("/device/<name>/restore/preview", methods=["GET"])
def restore_preview(name):
    """The restore preview at the chosen moment (board 9): the exact program, each line needing
    a stated reason, what is left on the device, the operands and checks, and the confirm bound
    to the program. A READ: the plan reads captured configs only; the form plans again on each
    change."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    # The chooser's Preview carries its ticked moment as `chosen`.
    fields = request.args.to_dict()
    fields["moment"] = fields.get("moment") or fields.get("chosen", "")
    return _strict(render_template("v2/_restore.html",
                                   c=_restore_card(ref, dev, _back(request.args), fields)))


@bp.route("/device/<name>/restore/confirm", methods=["POST"])
def restore_confirm(name):
    """Re-apply the confirmed moment as the verified person, as a job holding the device
    (`deploy_job.start_restore`, the same apply as `/golden/restore/apply`) in the list the
    preview was drawn in, which the confirm CARRIES (C396): the program is computed again and a
    different hash refuses with nothing sent. Answers with the card that follows the job."""
    import json

    from modules import deploy_job, device_actions, identity

    ref, dev, refusal = _named_device(name, request.form.get("list", ""), "v2/_restore.html")
    if refusal is not None:
        return refusal
    host = dev.get("hostname", "")
    moment = (request.form.get("moment") or "").strip()
    capture_hash = (request.form.get("capture_hash") or "").strip()
    command_hash = (request.form.get("command_hash") or "").strip()
    try:
        authorise = json.loads(request.form.get("authorise") or "[]")
    except ValueError:
        authorise = None
    if not moment or not capture_hash or not command_hash or authorise is None:
        return _strict(render_template("v2/_restore.html", c={
            "op": "restore", "state": "refused_hash", "host": host, "list": ref.name,
            "moment": moment, "moment_words": moment, "back": _back(request.form)}), 400)
    un_onboard = [host] if (request.form.get("un_onboard") or "") == "1" else None
    job = deploy_job.start_restore(
        ref.name, moment, {host: capture_hash}, {host: command_hash},
        authorise={host: authorise} if authorise else {}, un_onboard=un_onboard,
        actor=identity.identify(request).actor or "",
        actor_kind=getattr(identity.identify(request), "kind", ""),
        ident=identity.verified_identity())
    return _strict(render_template("v2/_restore.html", c={
        "op": "restore", "state": "restoring", "host": host, "list": ref.name, "job": job,
        "moment": moment, "moment_words": "golden now" if moment == "HEAD" else moment,
        "back": _back(request.form), "steps": device_actions.job_steps("restore", ref.name, host)}))


@bp.route("/device/<name>/restore/job/<job>", methods=["GET"])
def restore_job_card(name, job):
    """The restore card for its job: restoring with its stepper, its result from the receipt,
    or why there is none. Re-read when the job announces `deploy_job` and on each step."""
    from modules import deploy_job, device_actions

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    c = device_actions.restore_job_card(ref, dev.get("hostname", ""), job, deploy_job.state(job),
                                        moment=request.args.get("moment", ""))
    c.update(back=_back(request.args), ip=dev.get("ip", ""))
    return _strict(render_template("v2/_restore.html", c=c))


# ---------------------------------------------------------------------------
# Revert and Retry, the two ways out of a rollback (7.3; the device-actions canvas, board 11)
# ---------------------------------------------------------------------------

def _block_state(ref, dev) -> dict:
    from modules.nsot import intent_ops
    try:
        return intent_ops.block_state(ref.name, dev.get("hostname", ""))
    except Exception as exc:                            # noqa: BLE001
        log.warning("device_v2: the rollback record could not be read for %s: %s",
                    dev.get("hostname", ""), exc)
        return {"blocked": False, "at": "",
                "why": f"the rollback record could not be read ({type(exc).__name__})"}


def _viewer():
    from modules import identity
    from modules.preview_confirm import confirm_part
    return dict(confirm_part(request, "approve"), actor=identity.identify(request).actor or "")


def _revert_card(ref, dev, back, fields):
    """The revert card: THE revert preview (`intent_ops.revert_entry`, the builder today's
    route uses) for the chosen commit, masked on the way out, the confirm built from its hash."""
    from modules import device_actions
    from modules.nsot import intent_ops
    from modules.outbound import mask_payload
    from modules.preview_confirm import revert_preview as parts

    host = dev.get("hostname", "")
    entry = intent_ops.public(intent_ops.revert_entry(ref.name, host,
                                                      (fields.get("sha") or "").strip()))
    out = mask_payload({"entry": entry, "preview": parts(entry, list_name=ref.name,
                                                          request=request)})
    chosen = out["entry"].get("target") or ""
    commits = [dict(c, chosen=bool(chosen) and c.get("sha", "").startswith(chosen[:12]))
               for c in out["entry"].get("commits") or []]
    c = device_actions.intent_op_card("revert", ref, host, out["preview"], _viewer(),
                                      commits=commits)
    c.update(back=back, ip=dev.get("ip", ""), chosen=chosen)
    return c


def _retry_card(ref, dev, back, fields):
    """The retry card: THE retry preview (`intent_ops.retry_entry`) with the reason typed so
    far; the confirm is offered only once a reason in the shape of one is given."""
    from modules import device_actions
    from modules.nsot import intent_ops
    from modules.outbound import mask_payload
    from modules.preview_confirm import retry_preview as parts

    host = dev.get("hostname", "")
    entry = intent_ops.retry_entry(ref.name, host)
    preview = mask_payload(parts(entry, list_name=ref.name, request=request))
    c = device_actions.intent_op_card("retry", ref, host, preview, _viewer(),
                                      reason=(fields.get("reason") or "").strip())
    c.update(back=back, ip=dev.get("ip", ""))
    return c


@bp.route("/device/<name>/revert", methods=["GET"])
def revert(name):
    """Revert a change to the device's intent (board 11): the commit to revert (the one a
    rollback undid by default), the document after it, what it will not do, the checks and the
    confirm bound to its hash. A READ: git only; nothing is sent to the device."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_revert.html",
                                   c=_revert_card(ref, dev, _back(request.args), request.args)))


@bp.route("/device/<name>/revert/confirm", methods=["POST"])
def revert_confirm(name):
    """Revert the confirmed commit as the verified person, in the list the card CARRIES: the
    same apply as `/templatize/revert/apply` (`intent_ops.revert_apply`: computed again,
    refused if it moved, one intent commit, the block measured after it). Nothing is sent."""
    from modules import device_actions, identity
    from modules.nsot import intent_ops
    from modules.outbound import mask_payload
    from modules.preview_confirm import revert_result

    ref, dev, refusal = _named_device(name, request.form.get("list", ""), "v2/_revert.html")
    if refusal is not None:
        return refusal
    host = dev.get("hostname", "")
    sha, confirmed = (request.form.get("sha") or "").strip(), (request.form.get("hash") or "").strip()
    if not sha or not confirmed:
        return _strict(render_template("v2/_revert.html", c={
            "op": "revert", "state": "refused_hash", "host": host, "list": ref.name,
            "back": _back(request.form)}), 400)
    out = intent_ops.revert_apply(ref.name, host, sha, confirmed,
                                  identity.identify(request).actor or "")
    c = device_actions.intent_op_result_card("revert", ref, host,
                                             mask_payload(revert_result(out)))
    c.update(back=_back(request.form), ip=dev.get("ip", ""))
    return _strict(render_template("v2/_revert.html", c=c))


@bp.route("/device/<name>/retry", methods=["GET"])
def retry(name):
    """Retry the change a rollback blocked (board 11): the blocked program, how often this
    device was retried before, the reason asked for, the checks and the confirm bound to the
    block's hash. A READ: the record only; nothing is sent."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_retry.html",
                                   c=_retry_card(ref, dev, _back(request.args), request.args)))


@bp.route("/device/<name>/retry/confirm", methods=["POST"])
def retry_confirm(name):
    """Authorise the retry as the verified person, with the stated reason, in the list the card
    CARRIES: the same apply as `/templatize/retry/apply` (`intent_ops.retry_apply`: the block
    must be the one previewed, the reason in the shape of one). Nothing is sent."""
    from modules import device_actions, identity
    from modules.nsot import intent_ops
    from modules.outbound import mask_payload
    from modules.preview_confirm import retry_result

    ref, dev, refusal = _named_device(name, request.form.get("list", ""), "v2/_retry.html")
    if refusal is not None:
        return refusal
    host = dev.get("hostname", "")
    confirmed = (request.form.get("hash") or "").strip()
    if not confirmed:
        return _strict(render_template("v2/_retry.html", c={
            "op": "retry", "state": "refused_hash", "host": host, "list": ref.name,
            "back": _back(request.form)}), 400)
    out = intent_ops.retry_apply(ref.name, host, confirmed,
                                 (request.form.get("reason") or "").strip(),
                                 identity.identify(request).actor or "")
    c = device_actions.intent_op_result_card("retry", ref, host,
                                             mask_payload(retry_result(out)))
    c.update(back=_back(request.form), ip=dev.get("ip", ""))
    return _strict(render_template("v2/_retry.html", c=c))


# ---------------------------------------------------------------------------
# Seed intent (7.3; the device-actions canvas, board 8)
# ---------------------------------------------------------------------------

def _seed_card(ref, dev, back):
    """The seed card: THE seed preview (`seed.entry_for`, the builder today's route uses)
    for this device, masked on the way out, the confirm bound to its seed hash."""
    from modules import device_actions
    from modules.nsot import seed
    from modules.outbound import mask_payload
    from modules.preview_confirm import seed_preview as parts

    host = dev.get("hostname", "")
    entry = dict(seed.public(seed.entry_for(ref.name, dev)), list=ref.name)
    out = mask_payload({"entry": entry, "preview": parts([entry], request=request)})
    c = device_actions.seed_card(ref, host, out["preview"], _viewer(), out["entry"])
    c.update(back=back, ip=dev.get("ip", ""))
    return c


@bp.route("/device/<name>/seed", methods=["GET"])
def seed(name):
    """Seed the device's intent from its committed golden (board 8): the document that would
    be committed, whether the template reproduces the device, the device's own lines, what it
    will not do, the checks and the confirm bound to the seed hash. A READ: git only; nothing
    is sent to the device."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_seed.html", c=_seed_card(ref, dev, _back(request.args))))


@bp.route("/device/<name>/seed/confirm", methods=["POST"])
def seed_confirm(name):
    """Seed the confirmed device as the verified person, in the list the card CARRIES: the
    same apply as `/templatize/seed/apply` (`seed.apply`: the device held, its golden parsed
    again, a moved seed refused, one intent commit). Nothing is sent."""
    from modules import device_actions, identity
    from modules.nsot import seed as seed_op
    from modules.outbound import mask_payload
    from modules.preview_confirm import seed_result

    ref, dev, refusal = _named_device(name, request.form.get("list", ""), "v2/_seed.html")
    if refusal is not None:
        return refusal
    host = dev.get("hostname", "")
    confirmed = (request.form.get("hash") or "").strip()
    if not confirmed:
        return _strict(render_template("v2/_seed.html", c={
            "op": "seed", "state": "refused_hash", "host": host, "list": ref.name,
            "back": _back(request.form)}), 400)
    done = seed_op.apply(ref.name, [dev], {host: confirmed},
                         identity.identify(request).actor or "")
    c = device_actions.seed_result_card(ref, host, mask_payload(
        seed_result(done["outcomes"], done["save"])))
    c.update(back=_back(request.form), ip=dev.get("ip", ""))
    return _strict(render_template("v2/_seed.html", c=c))


# ---------------------------------------------------------------------------
# Retire (7.3; the device-actions canvas, board 12)
# ---------------------------------------------------------------------------

def _retire_card(ref, dev, back, fields):
    """The retire card: THE retire plan (`retire.plan`, the one today's route uses) with the
    reason typed so far, masked on the way out, the confirm bound to the plan's hash."""
    from modules import device_actions
    from modules.nsot import retire
    from modules.nsot.device_ops import busy_text
    from modules.outbound import mask_payload
    from modules.preview_confirm import retire_preview

    host = dev.get("hostname", "")
    p = retire.plan(ref.name, host, (fields.get("reason") or "").strip())
    out = mask_payload({"plan": p, "preview": retire_preview(
        p, busy=busy_text(ref.name, host), request=request)})
    c = device_actions.retire_card(ref, host, out["preview"], _viewer(), out["plan"])
    c.update(back=back, ip=dev.get("ip", ""))
    return c


@bp.route("/device/<name>/retire", methods=["GET"])
def retire(name):
    """Retire the device from management (board 12): the reason, what retire changes in
    order, what is generated and so dropped, what survives and how each is removed, the
    checks and the confirm bound to the plan. A READ: the repository, the CSV, the
    credential store, the settings and the export log; nothing is sent to the device."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_retire.html",
                                   c=_retire_card(ref, dev, _back(request.args), request.args)))


@bp.route("/device/<name>/retire/confirm", methods=["POST"])
def retire_confirm(name):
    """Retire the device as the verified person, with its reason, in the list the card
    CARRIES: the same apply as `/retire/apply` (`retire.apply`: the plan computed again and
    refused if it moved, the row deleted last against the export log). Once its commit
    landed, Prometheus's targets are regenerated and read back. Nothing is sent."""
    from modules import device_actions, identity
    from modules.nsot import retire as retire_op
    from modules.outbound import mask_payload
    from modules.preview_confirm import retire_result

    ref, dev, refusal = _named_device(name, request.form.get("list", ""), "v2/_retire.html")
    if refusal is not None:
        return refusal
    host = dev.get("hostname", "")
    confirmed = (request.form.get("hash") or "").strip()
    reason = (request.form.get("reason") or "").strip()
    if not confirmed:
        return _strict(render_template("v2/_retire.html", c={
            "op": "retire", "state": "refused_hash", "host": host, "list": ref.name,
            "back": _back(request.form)}), 400)
    before = retire_op.plan(ref.name, host, reason)
    actor = identity.identify(request).actor or ""
    out = retire_op.apply(ref.name, host, reason=reason, actor=actor,
                          confirmed_hash=confirmed, breakglass_log=True)
    log.info("retire (v2): %s/%s by %s: ok=%s done=%s", ref.name, host, actor,
             out.get("ok"), out.get("done"))
    targets = (retire_op.targets_after(host, before.get("ip", ""))
               if "commit" in (out.get("done") or []) else {})
    c = device_actions.retire_result_card(
        ref, host, mask_payload(retire_result(out, out.get("plan") or before)),
        mask_payload(before), targets)
    c.update(back=_back(request.form), ip=dev.get("ip", ""))
    return _strict(render_template("v2/_retire.html", c=c))


def _finish_state(name, list_name, rec):
    """What a retired record says of the device's Oxidized row (C398): offered, unknown, or
    nothing (no Oxidized here, or no row). One read of the helper's address list."""
    from modules.nsot import retire as retire_op

    ox = retire_op.oxidized_row(rec.get("ip", ""))
    base = {"name": name, "ip": rec.get("ip", ""), "list": list_name, "error": ox["error"]}
    if not ox["managed"] or ox["held"] is False:
        return None
    return dict(base, state="unknown" if ox["held"] is None else "offer")


@bp.route("/device/<name>/retire/finish", methods=["POST"])
def retire_finish(name):
    """Finish a retirement (C398; the operator, 2026-10-04): remove the retired device's row
    from Oxidized's router.db through the root helper's REMOVE mode, read back. The address is
    the retire commit's (the manifest just before it), never the form's; the list is CARRIED.
    Nothing is sent to any device."""
    from modules import identity
    from modules.nsot import listref
    from modules.nsot import retire as retire_op

    list_name = (request.form.get("list") or "").strip()
    f = {"name": name, "ip": "", "list": list_name}
    if not list_name or not listref.exists(list_name):
        return _strict(render_template("v2/_retire_finish.html", f=dict(
            f, state="refused", error=f"the card names no list this server knows "
                                      f"({list_name or 'none given'})")), 400)
    rec = retire_op.retired_record(listref.resolve(list_name).repo_dir, name)
    if not rec:
        return _strict(render_template("v2/_retire_finish.html", f=dict(
            f, state="refused", error=f"no retire commit in {list_name} names {name}")), 404)
    got = retire_op.remove_oxidized(rec["ip"])
    log.info("retire finish (v2): %s/%s (%s) by %s: ok=%s removed=%s %s", list_name, name,
             rec["ip"], identity.identify(request).actor or "", got["ok"], got["removed"],
             got["error"])
    return _strict(render_template("v2/_retire_finish.html", f=dict(
        f, ip=rec["ip"], state="done" if got["ok"] else "failed", removed=got["removed"],
        error=got["error"], backups_removed=got.get("backups_removed", 0),
        prune_error=got.get("prune_error", ""))))


@bp.route("/device/<name>/deploy/job/<job>", methods=["GET"])
def deploy_job_card(name, job):
    """The deploy card for its job: deploying with its stepper, its result from the receipt,
    or why there is none. Re-read when the job announces `deploy_job` and on each step."""
    from modules import deploy_job, device_actions

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    c = device_actions.deploy_job_card(ref, dev.get("hostname", ""), job, deploy_job.state(job))
    c.update(back=_back(request.args), ip=dev.get("ip", ""))
    return _strict(render_template("v2/_deploy.html", c=c))
