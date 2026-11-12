"""What is running on this list's devices now, and what finished recently.

Register C99: a restore ran for fifty seconds with nothing on screen, the
operator concluded it had staged something, started a deploy of the same
device, and the silence produced a second change (C98's hole). The standing
rule that followed: every process tells the person what happened or what to
do next, and one that is still RUNNING says so, since when, and what it is
waiting on.

One read serves every screen: C98's per-device lock already records who holds
each device, since when, and its last progress step, across processes (the
CLIs included). Operations that FINISHED in the last half hour come from their
receipts, so a reload in the middle of one no longer loses its result.
"""

import logging

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("operations", __name__, url_prefix="/operations")


@bp.route("/in_flight", methods=["GET"])
def in_flight():
    """``{"ok", "list", "running", "recent", "recent_state", "window_s"}``, from the one read
    every screen shares (modules/in_flight). A READ: it writes nothing.

    Asked by v2's top bar (an htmx request, C537): the In progress chip, drawn, for every
    network, as the person looking sees it (`in_flight.chip`)."""
    from modules import in_flight as F
    from modules.config import get_current_list_name
    from routes.list_param import named_list

    if request.headers.get("HX-Request"):
        return _chip()
    list_name = named_list(request) or get_current_list_name()
    try:
        got = F.read(list_name)
    except Exception as exc:                  # noqa: BLE001
        log.exception("operations: in-flight read failed for %s", list_name)
        return jsonify({"ok": False, "list": list_name,
                        "error": f"{type(exc).__name__}: {exc}"}), 500
    return jsonify({"ok": True, "list": list_name, **got,
                    "window_s": F.RECENT_SECONDS, "not_recorded": F.NOT_RECORDED})


def viewer_key() -> str:
    """Whose "not opened yet" the chip draws: the verified person looking, or "" for anyone
    not identified (who can look, and share one mark)."""
    from modules import identity

    ident = identity.viewer()
    return ident.actor if ident.is_identified else ""


def _read_chip() -> dict:
    from modules import in_flight as F
    from modules import integration_groups as IG

    try:
        return F.chip(IG.network_names(), viewer_key())
    except Exception as exc:                      # noqa: BLE001
        log.exception("operations: the In progress chip could not be read")
        return {"error": f"{type(exc).__name__}: {exc}", "shown": True, "level": "danger",
                "words": "could not be read", "running": [], "finished": [], "unread": [],
                "counts": {}}


def _chip(ip: dict = None, said: str = "", code: int = 200):
    """The In progress chip (boards A and B): nothing while nothing runs and nothing waits to
    be opened; else the chip and its list. A read that fails is drawn as unknown, never as
    nothing running (C99). *said*: a mark refused, drawn at the list's head."""
    from flask import render_template

    from routes.device_v2 import _strict

    ip = _read_chip() if ip is None else ip
    # The same read drawn two ways: the top bar's chip, and Devices' In progress list
    # (``view=panel``, the one-decision onboarding's board D: the running operations, each
    # opening its live stepper).
    if request.args.get("view") == "panel":
        # The list draws what runs and what could not be read; the chip's outcomes are its own.
        resp = _strict(render_template("v2/_in_progress_panel.html", ip={
            k: ip.get(k) or ([] if k != "error" else "") for k in ("error", "running",
                                                                   "unread")}))
    else:
        if said:
            ip = dict(ip, said=said, shown=True)
        resp = _strict(render_template("v2/_in_progress.html", ip=ip), code)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Vary"] = "HX-Request"
    return resp


def mark_seen():
    """``POST /v2/operations/seen`` (`routes.v2.seen_run`, its route): a verified person marks
    one entry of "Finished, not opened yet" seen, kept per person
    (`seen_runs`, C3081; the operator, 2026-11-12: "Opening a result must mark it seen
    PERSISTENTLY (per person, stored), so it leaves the list and the chip; add a "Dismiss" on
    each entry too"). Form: ``job`` and ``run`` (the entry's ids), ``device`` and ``list``,
    ``how`` (``opened`` or ``dismissed``).

    The entry is found again among the ones listed for this person now, and only its ids are
    marked, and its device's page is the server's (one no longer listed marks nothing, and
    Open goes to the device's page the form names, or is refused with none). ``opened``:
    marked, then the run's page (the device's page reopening THAT run's card, ``result``), as
    an htmx redirect (the network picker's do-then-open, `network_v2.choose`), else a 303.
    ``dismissed``: marked, and the list drawn again in place without it. A refusal (nobody
    verified, the store unreadable) is drawn at the list's head and nothing is written. Every
    open page's chip reads again (`in_progress`)."""
    from flask import make_response, redirect

    from modules import seen_runs
    from modules.nsot import capture_job

    form = request.form
    how = (form.get("how") or "").strip()
    job, run = (form.get("job") or "").strip(), (form.get("run") or "").strip()
    viewer = viewer_key()
    ip = _read_chip()
    entry = next((f for f in ip.get("finished") or []
                  if (job and f.get("job") == job) or (run and f.get("run") == run)), None)
    if not viewer or how not in seen_runs.HOW:
        got = seen_runs.mark(viewer, [job, run], how)          # refused, saying why
        device, network = "", ""
    elif entry is None:
        # Not listed for this person now (another tab opened it, or it aged out): nothing to
        # mark; Open still opens the page the form names, Dismiss draws the list as it is.
        device, network = (form.get("device") or "").strip(), (form.get("list") or "").strip()
        got = ({"ok": True, "news": False, "error": ""} if device or how != "opened" else
               {"ok": False, "news": False, "error": "no device was named"})
    else:
        got = seen_runs.mark(viewer, [entry.get("job"), entry.get("run")], how)
        device, network = entry["device"], entry["list"]
    verb = "opened" if how == "opened" else "dismissed"
    if not got["ok"]:
        return _chip(ip, said=f"Not marked {verb}: {got['error']}.",
                     code=403 if not viewer else 409)
    if got["news"]:
        try:
            from modules import invalidation
            invalidation.announce(capture_job.MOVED_KEYS, by=capture_job.MOVED_ANNOUNCER,
                                  ok=True)
        except RuntimeError:
            pass                                  # no emitter: nobody else to tell
        except Exception as exc:                  # noqa: BLE001
            log.warning("operations: a mark seen was not announced to open pages: %s", exc)
    if how != "opened":
        return _chip()
    # The run's address from the ONE place it is built (`run_href`, the operator, 2026-11-11:
    # "once the incident page exists, 'Open the result' goes to the incident's URL").
    from html import unescape

    from flask import current_app

    ident = (entry or {}).get("job") or (entry or {}).get("run") or job or run
    run_href = current_app.jinja_env.get_template("v2/_macros.html").module.run_href
    where = unescape(str(run_href(device, network or None, ident or None))).strip()
    if request.headers.get("HX-Request"):
        resp = make_response("", 204)
        resp.headers["HX-Redirect"] = where
        return resp
    return redirect(where, code=303)
