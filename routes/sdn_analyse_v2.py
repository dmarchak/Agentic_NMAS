"""routes/sdn_analyse_v2.py — SDN › Flows' Analyse this network (Lab 9 B1, C2903; board I of
docs/boards/lab9-sdn.html, self-signed 2026-11-10): the analyst's region, its two presses and
its planted-issue sheet (modules/sdn/analyst.py).

- **Collect now** starts the collection job (a read of the network's controllers, never a page
  view), one at a time per network; the region redraws when the job announces ``sdn``.
- **Analyse this network** asks ONE recorded, capped AI call over the network's latest
  snapshot, as the person who pressed it; its answer is checked in code and drawn in place.
- **Analyse with the trace tool** (Lab 9 B4) asks the same over the same snapshot through the
  read loop: at most two calls, the model's reads answered from the kept snapshot alone; its
  answer, its tool calls and the comparison with the first drawn in place.
- **Check this answer again** (on either findings card) makes NO AI call: the call's recorded
  answer is read again, held by today's check to the same kept snapshot, and drawn under the
  first check's findings with who pressed it and when; the planted issues are then marked
  from it, and the card says so.
- **Add a planted issue…** and a row's **Save** keep the network's planted-issue sheet; a row's
  **Edit…** (Save changes) corrects its name and evidence and its **Remove…** (Remove from the
  sheet) takes it off, kept marked removed (C2913), each change in the sheet's history;
  **Download the sheet** reads it as Markdown or CSV.

Nothing here sends anything to a switch. Each press redraws the region (``#sdn-analyse``) in
place; the SDN page's region carries it on Flows.
"""

import logging

from flask import Blueprint, Response, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("sdn_analyse_v2", __name__, url_prefix="/v2/sdn/analyse")


def _network() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list, submitted_list

    if request.method == "POST":
        name, _refusal = submitted_list(request)
        if name:
            return name
    return named_list(request) or listref.active().name


def _region(network: str, said: dict = None, status: int = 200):
    from modules.sdn import analyst

    return _strict(render_template("v2/_sdn_analyse.html", an=analyst.view(network),
                                   said=said or {}), status)


@bp.route("/collect", methods=["POST"])
def collect():
    """Collect now: the collection job started (refused, naming why, when the network has no
    controller or one is running)."""
    from modules import identity
    from modules.sdn import analyst

    network = _network()
    got = analyst.start_collection(network, actor=identity.request_actor())
    return _region(network, {"collect": got})


@bp.route("/ask", methods=["POST"])
def ask():
    """Analyse this network: one recorded, capped AI call over the snapshot the region drew (its
    id from the form), as the person who pressed it (`analyst.analyse`)."""
    from modules import identity
    from modules.ai import triggers
    from modules.sdn import analyst

    network = _network()
    actor = identity.request_actor()
    got = analyst.analyse(network, (request.form.get("snapshot") or "").strip(), actor=actor,
                          trigger=triggers.person(actor))
    return _region(network, {"ask": got})


@bp.route("/ask-tools", methods=["POST"])
def ask_tools():
    """Analyse with the trace tool (Lab 9 B4): at most two recorded, capped AI calls over the
    snapshot the region drew, the model asking for reads Mercury answers from that kept
    snapshot alone, as the person who pressed it (`sdn_analyst_tools.analyse`)."""
    from modules import identity
    from modules.ai import sdn_analyst_tools, triggers

    network = _network()
    actor = identity.request_actor()
    got = sdn_analyst_tools.analyse(network, (request.form.get("snapshot") or "").strip(),
                                actor=actor, trigger=triggers.person(actor))
    return _region(network, {"ask_tools": got})


@bp.route("/recheck", methods=["POST"])
def recheck():
    """Check this answer again (the Lab 9 sitting, 2026-11-10): NO AI call. The analysis the
    card drew (its id from the form: B1's or the trace tool's) has its recorded answer read
    again from the record of AI calls, parsed by the schema it was asked under and held by
    today's check to the same kept snapshot (`analyst.recheck`); the result is kept on the
    analysis's record beside the first check, with who pressed it and when, and the region
    redraws with both. A refusal is said in place, and nothing is kept."""
    from modules import identity
    from modules.sdn import analyst

    network = _network()
    got = analyst.recheck(network, (request.form.get("analysis") or "").strip(),
                          actor=identity.request_actor())
    said = {"ok": got["ok"], "error": got["error"], "id": got["id"]}
    return _region(network, {"recheck": said}, 200 if got["ok"] else 422)


@bp.route("/planted", methods=["POST"])
def planted_add():
    """Add a planted issue: its name, the evidence it should be found by, and why."""
    from modules import identity
    from modules.sdn import analyst

    network = _network()
    got = analyst.add_planted(network, request.form.get("name") or "",
                              request.form.get("evidence") or "",
                              why=request.form.get("why") or "",
                              actor=identity.request_actor())
    return _region(network, {"planted": got}, 200 if got["ok"] else 422)


@bp.route("/planted/<pid>/why", methods=["POST"])
def planted_why(pid):
    """A planted issue's why, a person's note, saved."""
    from modules import identity
    from modules.sdn import analyst

    network = _network()
    got = analyst.set_why(network, pid, request.form.get("why") or "",
                          actor=identity.request_actor())
    return _region(network, {"why": dict(got, pid=pid)}, 200 if got["ok"] else 422)


@bp.route("/planted/<pid>/edit", methods=["POST"])
def planted_edit(pid):
    """A planted issue's name and evidence corrected (C2913), as the person who pressed Save
    changes; refused when the issue changed since the form drew it (``rev``)."""
    from modules import identity
    from modules.sdn import analyst

    network = _network()
    got = analyst.edit_planted(network, pid, request.form.get("name") or "",
                               request.form.get("evidence") or "",
                               drawn=request.form.get("rev"), actor=identity.request_actor())
    return _region(network, {"edit": dict(got, pid=pid)}, 200 if got["ok"] else 422)


@bp.route("/planted/<pid>/remove", methods=["POST"])
def planted_remove(pid):
    """A planted issue taken off the sheet (C2913), as the person who pressed Remove from the
    sheet: kept in the store marked removed, its change in the sheet's history."""
    from modules import identity
    from modules.sdn import analyst

    network = _network()
    got = analyst.remove_planted(network, pid, drawn=request.form.get("rev"),
                                 actor=identity.request_actor())
    return _region(network, {"remove": dict(got, pid=pid)}, 200 if got["ok"] else 422)


@bp.route("/sheet/<fmt>", methods=["GET"])
def sheet(fmt):
    """Download the sheet, as Markdown (``md``) or CSV (``csv``); the attachment's filename
    carries the extension. A read. Its format is a path segment of its own, so every page's
    link resolves to it (tests/route_references.py `resolves`)."""
    from modules import identity
    from modules.sdn import analyst

    network = _network()
    who = identity.viewer().actor
    if fmt == "md":
        body, mime = analyst.sheet_markdown(network, by=who), "text/markdown"
    elif fmt == "csv":
        body, mime = analyst.sheet_csv(network, by=who), "text/csv"
    else:
        return Response(f"No sheet as {fmt!r}: it downloads as md or csv.\n", status=404,
                        mimetype="text/plain")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in network)
    return Response(body, mimetype=mime, headers={
        "Content-Disposition": f'attachment; filename="planted-issues-{safe}.{fmt}"',
        "Cache-Control": "no-store"})
