"""routes/sdn_v2.py — OBSERVE › SDN: a network's SDN controllers and their switches' flows
(PHASE8_PLAN 17.1 S11; boards SdnControllers, SdnFlows and SdnPhone, signed off 2026-10-27 under
the Phase 7 mode; docs/fidelity/sdn.md).

A read: the SDN reader's stored value, drawn by modules/sdn_page.py beside the network's
connection list; never a controller call per view. The region redraws when the reader announces
`sdn`. The one action here, Test connection on a controller's card, asks that controller now
with what is saved, and answers in place; it changes nothing. The connections themselves are
edited in Settings › Integrations (the card's "Edit connection").
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("sdn_v2", __name__, url_prefix="/v2/sdn")

TABS = (("controllers", "Controllers"), ("flows", "Flows"), ("responses", "Responses"))


def _list_name() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return named_list(request) or listref.active().name


def _ctx(tab: str) -> dict:
    from modules import sdn_page

    network = _list_name()
    if tab == "responses":
        from modules import sdn_ops_page

        g = sdn_ops_page.responses_view(network, (request.args.get("run") or "").strip())
    else:
        g = (sdn_page.flows_view(network, request.args) if tab == "flows"
             else sdn_page.controllers_view(network))
    return {"g": g, "tabs": TABS}


@bp.route("", methods=["GET"])
def page():
    """SDN › Controllers (board SdnControllers)."""
    from routes.v2 import _page

    return _page("v2/sdn.html", active_nav="sdn", list_name=_list_name(), **_ctx("controllers"))


@bp.route("/flows", methods=["GET"])
def flows():
    """SDN › Flows (board SdnFlows)."""
    from routes.v2 import _page

    return _page("v2/sdn.html", active_nav="sdn", list_name=_list_name(), **_ctx("flows"))


@bp.route("/view", methods=["GET"])
def region():
    """The page's region alone: re-read when `sdn` is announced, and asked again with a filter.
    Writes nothing."""
    tab = request.args.get("tab") if request.args.get("tab") in dict(TABS) else "controllers"
    return _strict(render_template("v2/_sdn_view.html", **_ctx(tab)))


@bp.route("/responses", methods=["GET"])
def responses():
    """SDN › Responses (board SdnResponses): what awaits a person, the mode, the loop, the
    rules. A read."""
    from routes.v2 import _page

    return _page("v2/sdn.html", active_nav="sdn", list_name=_list_name(), **_ctx("responses"))


@bp.route("/log", methods=["GET"])
def log_region():
    """The loop's log panel alone (C1971), for the run the picker names (`?run=<job id>`; the
    newest when none): the whole run, newest line first. A read."""
    from modules import sdn_ops_page

    lg = sdn_ops_page.log_view(_list_name(), (request.args.get("run") or "").strip())
    return _strict(render_template("v2/_sdn_log.html", lg=lg))


@bp.route("/log/download", methods=["GET"])
def log_download():
    """Download log (C1971): one run of the loop's log as plain text, every line, oldest
    first, named for the network and the run (`<job id>.log`, the job id naming both). A read;
    a run that is not in the log is a 404 naming it."""
    from flask import Response

    from modules.sdn import loop

    got = loop.run_text(_list_name(), (request.args.get("run") or "").strip())
    if got["state"] != "ok":
        return Response(f"No log to download: {got['error']}.\n", status=404,
                        mimetype="text/plain")
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in got["job"])
    return Response(got["text"], mimetype="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="{safe}.log"',
                             "Cache-Control": "no-store"})


# ───────────────────────────────────────────────────────────────────────────── operations
# PHASE8_PLAN 17.1 S8 and S16 (C1912): every flow Mercury adds, edits or removes, and every
# response, is ONE operation (modules/sdn/flow_ops.py): a preview of the exact requests, a
# confirm bound to their hash as a verified person, the apply holding the switch, Verify,
# rollback, and the record. The card (_sdn_op.html) is drawn in place of the control's slot.

def _op_card(d: dict, status: int = 200):
    return _strict(render_template("v2/_sdn_op.html", d=d)), status


def _network_of_form() -> str:
    from routes.list_param import submitted_list

    name, _refusal = submitted_list(request)
    return name or _list_name()


@bp.route("/flow/form", methods=["GET"])
def flow_form():
    """The editor in place (board SdnFlowEdit): Add on a switch, Edit or Remove on a flow. A
    read; the form posts its preview."""
    return _strict(render_template("v2/_sdn_flow_form.html", f={
        "do": request.args.get("do", "add"), "connection": request.args.get("connection", ""),
        "dpid": request.args.get("dpid", ""), "target": request.args.get("target", ""),
        "list": _list_name()}))


@bp.route("/flow/preview", methods=["POST"])
def flow_preview():
    """The preview of a person's Add, Edit or Remove: the exact requests and their hash, read
    from the switch now; writes nothing."""
    from modules import sdn_ops_page
    from modules.sdn import flow_form, flow_ops

    network = _network_of_form()
    try:
        ask = flow_form.ask_from_form(request.form)
    except flow_form.FormRefused as exc:
        return _op_card(sdn_ops_page.refused(network, "flow", str(exc)), 400)
    p = flow_ops.plan(network, ask)
    return _op_card(sdn_ops_page.preview(network, "flow", ask, p), 200 if p["ok"] else 409)


@bp.route("/flow/confirm", methods=["POST"])
def flow_confirm():
    """Apply the previewed change as the verified person, bound to the preview's hash."""
    from modules import identity, sdn_ops_page
    from modules.sdn import flow_ops

    network = _network_of_form()
    ask, refused = sdn_ops_page.carried_ask(request.form)
    if refused:
        return _op_card(sdn_ops_page.refused(network, "flow", refused), 400)
    done = flow_ops.apply(network, ask, (request.form.get("hash") or "").strip(),
                          actor=identity.request_actor(),
                          actor_verified=identity.actor_verification(identity.request_actor()),
                          typed=request.form.get("typed", ""))
    return _op_card(sdn_ops_page.result(network, "flow", done),
                    200 if done["outcome"] != "refused" else 409)


@bp.route("/response/<rid>/preview", methods=["POST"])
def response_preview(rid):
    """The preview of a response awaiting a person: its catalogue action built from the
    detection and checked against the evidence, the exact requests and their hash. Writes
    nothing."""
    from modules import sdn_ops_page
    from modules.sdn import closed_loop, loop

    network = _network_of_form()
    row = next((r for r in loop.awaiting(network)["rows"] if r.get("id") == rid), None)
    if row is None:
        return _op_card(sdn_ops_page.refused(network, "response", f"no response {rid} is "
                                                                  "awaiting a person"), 404)
    action = (request.form.get("action") or row.get("action") or "").strip()
    params = {k: request.form.get(k) for k in ("source", "hard_timeout", "rate", "burst", "unit")
              if (request.form.get(k) or "").strip()}
    got = closed_loop.respond_to_threat(network, row["detection"], action, params)
    return _op_card(sdn_ops_page.response_preview(network, row, got),
                    200 if got["ok"] else 409)


@bp.route("/response/<rid>/classify", methods=["POST"])
def response_classify(rid):
    """Classify (PHASE8_PLAN 17.1 S7): a response awaiting a person classified by AI, one
    recorded, capped call as the person who pressed it (`closed_loop.classify_threat`), its
    answer checked in code and kept with the response, its catalogue action proposed. Nothing
    is sent to a switch: the response still waits for a person's preview and confirm."""
    from modules import identity
    from modules.ai import triggers
    from modules.sdn import closed_loop, loop

    network = _network_of_form()
    row = next((r for r in loop.awaiting(network)["rows"] if r.get("id") == rid), None)
    if row is None:
        return _strict(render_template("v2/_sdn_answer.html",
                                       refused=f"no response {rid} is awaiting a person")), 404
    actor = identity.request_actor()
    got = closed_loop.classify_threat(network, row["detection"], actor=actor,
                                      trigger=triggers.person(actor))
    if got["ok"]:
        loop.classified(network, rid, got, actor=actor)
    ctx = _ctx("responses")
    ctx["g"]["classify"] = {"rid": rid, "ok": got["ok"], "error": got.get("error", ""),
                            "detail": got.get("detail", "")}
    return _strict(render_template("v2/_sdn_view.html", **ctx))


@bp.route("/response/confirm", methods=["POST"])
def response_confirm():
    """Apply the previewed response as the verified person (HITL), bound to its hash; the
    awaiting response is closed as confirmed with the operation's id."""
    from modules import identity, sdn_ops_page
    from modules.sdn import closed_loop, loop

    network = _network_of_form()
    ask, refused = sdn_ops_page.carried_ask(request.form)
    rid = (request.form.get("rid") or "").strip()
    if refused:
        return _op_card(sdn_ops_page.refused(network, "response", refused), 400)
    actor = identity.request_actor()
    action = (request.form.get("action") or "").strip()
    row = next((r for r in loop.awaiting(network)["rows"] if r.get("id") == rid), {}) \
        if rid else {}
    done = closed_loop.respond_to_threat(
        network, None, action,
        confirm={"ask": ask, "hash": (request.form.get("hash") or "").strip()}, actor=actor,
        actor_verified=identity.actor_verification(actor),
        classified_by=closed_loop.classified_words(row.get("classification"), action))
    if done.get("outcome") == "verified" and rid:
        try:
            loop.resolve(network, rid, "confirmed", actor=actor, operation=done.get("id", ""))
        except ValueError as exc:
            done["note"] = str(exc)
    return _op_card(sdn_ops_page.result(network, "response", done),
                    200 if done.get("outcome") != "refused" else 409)


@bp.route("/response/<rid>/dismiss", methods=["POST"])
def response_dismiss(rid):
    """Dismiss a response awaiting a person, with their reason; nothing is sent."""
    from modules import identity
    from modules.sdn import loop

    network = _network_of_form()
    try:
        loop.resolve(network, rid, "dismissed", actor=identity.request_actor(),
                     why=request.form.get("reason", ""))
    except ValueError as exc:
        return _strict(render_template("v2/_sdn_answer.html", refused=str(exc))), 409
    return _strict(render_template("v2/_sdn_view.html", **_ctx("responses")))


@bp.route("/mode", methods=["POST"])
def mode_set():
    """Turn AUTO on (a verified person, a reason, an expiry, the allowed risk) or off, for this
    network (17.4). Recorded."""
    import time

    from modules import identity
    from modules.sdn import modes

    network = _network_of_form()
    actor = identity.request_actor()
    try:
        if request.form.get("mode") == "auto":
            hours = float(request.form.get("hours") or 0)
            modes.turn_on(network, actor=actor,
                          actor_verified=identity.actor_verification(actor),
                          reason=request.form.get("reason", ""),
                          until=time.time() + hours * 3600,
                          allowed_risk=request.form.get("risk", "low"))
        else:
            modes.turn_off(network, actor=actor,
                           actor_verified=identity.actor_verification(actor),
                           why=request.form.get("reason", ""))
    except (ValueError, modes.ModeRefused) as exc:
        return _strict(render_template("v2/_sdn_answer.html", refused=str(exc))), 409
    return _strict(render_template("v2/_sdn_view.html", **_ctx("responses")))


@bp.route("/loop", methods=["POST"])
def loop_set():
    """Start or stop the loop on this network (S10). Recorded in its log."""
    from modules import identity
    from modules.sdn import loop

    network = _network_of_form()
    try:
        if request.form.get("run") == "start":
            loop.start(network, actor=identity.request_actor(),
                       interval=float(request.form.get("interval") or loop.DEFAULT_INTERVAL))
        else:
            loop.stop(network, actor=identity.request_actor())
    except ValueError as exc:
        return _strict(render_template("v2/_sdn_answer.html", refused=str(exc))), 409
    return _strict(render_template("v2/_sdn_view.html", **_ctx("responses")))


@bp.route("/controller/<name>/test", methods=["POST"])
def controller_test(name):
    """Test connection on a controller's card: its driver's `test()` now, with what is saved,
    drawn in place. Changes nothing; the card's state stays the reader's until its next read."""
    from modules.sdn import connections

    tested = connections.test_saved(_list_name(), name)
    return _strict(render_template("v2/_sdn_answer.html", tested=tested, name=name,
                                   list_name=_list_name()))
