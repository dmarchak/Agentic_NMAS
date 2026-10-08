"""The read screens on v2 (C547 and C548; NSOT_READS.md, boards A to E, signed off 2026-10-08).

Ask the device is the device page's last tab (board A). Every read goes through the reads
engine (`modules/nsot/reads.py`): the allowlist first, the device held while read, masked,
capped, recorded. A run is a job; the card listens for `reads`, never a timer.
"""

import logging

from flask import Blueprint, redirect, render_template, request, url_for

from routes.device_v2 import _device_or_404, _strict

log = logging.getLogger(__name__)

bp = Blueprint("reads_v2", __name__, url_prefix="/v2")


def _card(ref, dev, **kw):
    from modules import reads_page
    return reads_page.ask(ref.name, dev["hostname"], **kw)


# The card alone (GET) is `device_v2.ask`, the tab bar's address for every tab.


@bp.route("/device/<name>/ask/check", methods=["GET"])
def ask_check(name):
    """Run, and why the command as typed cannot run (or what it costs). Asks no device."""
    from modules import reads_page
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    c = {"check": reads_page.check(request.args.get("command", "")), "state": "idle"}
    return _strict(render_template("v2/_ask_check.html", c=c))


@bp.route("/device/<name>/ask", methods=["POST"])
def ask_run(name):
    """Start the read as a job, as the verified person, or refuse it with nothing sent (the
    refusal recorded). Answers the card (htmx), or the device page at its card."""
    from modules import identity
    from modules.nsot import reads
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    command = (request.form.get("command") or "").strip()
    got = reads.start(ref.name, [dev["hostname"]], [command], identity.request_actor())
    if not request.headers.get("HX-Request"):
        return redirect(url_for("device_v2.device", name=name, tab="ask", list=ref.name,
                                job=got.get("job", ""), run=got.get("run", ""),
                                command=command))
    c = _card(ref, dev, command=command, job=got.get("job", ""), run_id=got.get("run", ""))
    # A refusal is the card's answer (drawn in place, recorded), so it answers 200 like a run.
    return _strict(render_template("v2/_ask.html", c=c))


# =========================================================================== Show commands
# Boards B to E (C548): OBSERVE › Show commands, many devices at once, on the same engine.

def _list() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list
    return named_list(request) or (request.form.get("list") or "").strip() or listref.active().name


def _pick_args(src) -> dict:
    rows = [c for c in src.getlist("command")]
    remove = src.get("remove", "")
    if remove.isdigit() and int(remove) < len(rows):
        rows.pop(int(remove))
    if src.get("add") and len(rows) < 10:
        rows.append("")
    return {"q": src.get("q", ""), "role": src.get("role", ""),
            "platform": src.get("platform", ""), "site": src.get("site", ""), "commands": rows}


@bp.route("/show-commands", methods=["GET"])
def show_commands():
    """The page: a new read (board B) and the network's recent runs."""
    from modules import reads_page
    from routes.v2 import _page
    name = _list()
    args = _pick_args(request.args)
    set_name = request.args.get("set", "")
    if set_name:
        from modules.nsot import command_sets
        s = next((x for x in command_sets.committed(name)["sets"] if x["slug"] == set_name), None)
        if s:
            args["commands"] = list(s["commands"])
    return _page("v2/show_commands.html", active_nav="show_commands", list_name=name,
                 p=reads_page.pick(name, **args), runs=reads_page.recent_runs(name))


@bp.route("/show-commands/pick", methods=["GET"])
def show_commands_pick():
    """The pick card alone, redrawn as its filters or rows change (asks no device)."""
    from modules import reads_page
    name = _list()
    return _strict(render_template("v2/_sc_pick.html", p=reads_page.pick(name,
                                                                      **_pick_args(request.args))))


@bp.route("/show-commands/devices", methods=["GET"])
def show_commands_devices():
    """The devices part alone as the filters change, and Run beside it (out of band): never the
    field being typed in (asks no device)."""
    from modules import reads_page
    p = reads_page.pick(_list(), **_pick_args(request.args))
    return _strict(render_template("v2/_sc_devices.html", p=p)
                   + render_template("v2/_sc_run.html", p=p, oob=True))


@bp.route("/show-commands/check", methods=["GET"])
def show_commands_check():
    """One command row's verdict as typed, and Run (out of band) from the whole form, so a typed
    valid command turns it on at once (asks no device)."""
    from modules import reads_page
    p = reads_page.pick(_list(), **_pick_args(request.args))
    i = request.args.get("i", "0")
    row = p["rows"][int(i)] if i.isdigit() and int(i) < len(p["rows"]) else None
    k = row["check"] if row else reads_page.check(request.args.get("command", ""), 2)
    return _strict(render_template("v2/_sc_check.html", k=k, i=i)
                   + render_template("v2/_sc_run.html", p=p, oob=True))


@bp.route("/show-commands/run", methods=["POST"])
def show_commands_run():
    """Start the run as a job, as the verified person, on exactly the devices the card showed:
    refused now (recorded, nothing asked) or the run's page."""
    from modules import identity, reads_page
    from modules.nsot import reads
    name = _list()
    args = _pick_args(request.form)
    p = reads_page.pick(name, **args)
    shown = (request.form.get("fingerprint") or "").strip()
    if shown != p["fingerprint"]:
        # The devices the filters match moved since the card was drawn: what runs must be what
        # the person saw, so nothing is asked and the card is drawn again, naming both.
        p = reads_page.pick(name, **args, error=(
            f"Not run: the devices these filters match changed since the card was drawn "
            f"(fingerprint {shown or 'none'} then, {p['fingerprint']} now: {len(p['devices'])} "
            "device(s) now). Check the list below and Run again."))
        return _strict(render_template("v2/_sc_pick.html", p=p))      # drawn in place
    got = reads.start(name, p["devices"], args["commands"], identity.request_actor())
    target = url_for("reads_v2.show_commands_result", run_id=got["run"], job=got.get("job", ""),
                     list=name)
    if request.headers.get("HX-Request"):
        from flask import make_response
        r = make_response("", 204)
        r.headers["HX-Redirect"] = target
        return r
    return redirect(target)


def _result_ctx(name, run_id):
    from modules import reads_page
    a = request.args
    return reads_page.result(name, run_id, job=a.get("job", ""), find=a.get("find", ""),
                             text=a.get("text", ""), show=a.get("show", "grouped"),
                             left=a.get("left", ""), right=a.get("right", ""),
                             command=a.get("command", ""), against=a.get("against", ""))


@bp.route("/show-commands/run/<run_id>", methods=["GET"])
def show_commands_result(run_id):
    """A run's page (boards C and D): running with its progress, or its result."""
    from routes.v2 import _page
    name = _list()
    return _page("v2/show_commands_run.html", active_nav="show_commands", list_name=name,
                 r=_result_ctx(name, run_id))


@bp.route("/show-commands/run/<run_id>/part", methods=["GET"])
def show_commands_result_part(run_id):
    """The run's region alone: re-read on `reads` while running, and as its filters change."""
    name = _list()
    return _strict(render_template("v2/_sc_result.html", r=_result_ctx(name, run_id)))


@bp.route("/show-commands/sets", methods=["POST"])
def show_commands_save_set():
    """Commit the card's commands as a saved set, as the verified person (R3), and redraw the
    card saying so, or why not."""
    from modules import identity, reads_page
    from modules.nsot import command_sets
    name = _list()
    args = _pick_args(request.form)
    got = command_sets.save(name, request.form.get("set_name", ""), args["commands"],
                            identity.request_actor(), request.form.get("set_description", ""))
    p = reads_page.pick(name, **args,
                        message=(f"Saved as {request.form.get('set_name', '').strip()!r}, "
                                 f"committed to {name}'s repository ({got.get('path')})."
                                 if got["ok"] else ""), error="" if got["ok"] else got["error"])
    return _strict(render_template("v2/_sc_pick.html", p=p))
