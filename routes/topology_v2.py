"""routes/topology_v2.py — OBSERVE › Topology (P.11 step 2; NSOT_TOPOLOGY_BRIEF, boards A to C
signed off 2026-10-04).

How each network is connected, layer by layer, and where it is weak: drawn from the topology
reader's stored value (modules/topology_page.py), never read per request. The map region
redraws when the reader announces `topology`; a layer, a path trace or a search asks for the
region again with its question. Marking an island expected is a verified person's act, with a
reason, recorded (modules/topology_expected.py).
"""

import logging

from flask import Blueprint, render_template, request
from modules.outbound import no_store

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("topology_v2", __name__, url_prefix="/v2/topology")


def _list_name() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return (request.form.get("list") or "").strip() or named_list(request) or \
        listref.active().name


def _graph(list_name: str) -> dict:
    """*list_name*'s graph in the Topology reader's stored value (`topology_graph.network_of`,
    by either spelling of the network, C1903), ``{}`` when the read holds none. A name no
    network answers to raises `listref.UnknownList`, naming it: the region says "Couldn't
    load" with that sentence (app.py's handler), never an empty map."""
    from modules import topology_page
    from modules.readers.topology_graph import network_of

    return network_of(topology_page.stored().get("value"), list_name) or {}


def _ctx(values=None, **extra) -> dict:
    from modules import topology_page
    from modules.preview_confirm import confirm_part

    v = topology_page.view(_list_name(), request.args if values is None else values)
    return dict({"t": v, "may": confirm_part(request, "configure")}, **extra)


def _region(code: int = 200, values=None, **extra):
    return _strict(render_template("v2/_topology_map.html", **_ctx(values, **extra)), code)


def _result(op: dict):
    """A write's result (C656): the map region redrawn as it now is, and the result in the slot
    above it, out of band. The page then redraws the region by the key the
    write declares; a result drawn inside the region was wiped by that redraw."""
    note = render_template("v2/_topology_result.html", op=op)
    return _strict(render_template("v2/_topology_map.html", **_ctx())
                   + f'\n<div id="topo-result" aria-live="polite" hx-swap-oob="true">{note}</div>')


@bp.route("", methods=["GET"])
def page():
    """The page. A read: the reader's stored value, drawn."""
    from routes.v2 import _page

    return _page("v2/topology.html", active_nav="topology", list_name=_list_name(), **_ctx())


@bp.route("/map", methods=["GET"])
def region():
    """The map region alone: re-read when `topology` is announced, and asked again with its
    question (protocols, ports, labels, zoom, a selected link, a path, a what-if, a search, the
    attention list's filter). Writes nothing."""
    return _region()


@bp.route("/expected", methods=["GET"])
def expected_form():
    """Mark as expected…: the reason asked for, in place; nothing written."""
    return _region(op={"state": "form", "device": (request.args.get("device") or "").strip()})


@bp.route("/expected", methods=["POST"])
def expected_declare():
    """Declare an island expected, with why, as the verified person; recorded."""
    from modules import identity, topology_expected

    device = (request.form.get("device") or "").strip()
    holds = None
    if device.startswith((topology_expected.SPOF, topology_expected.BRIDGE)):
        # C1487: a weak point accepted by design holds what it cuts off now, from the map's
        # stored analysis, so it warns again when that changes. One the map does not draw now
        # is refused, naming it.
        from modules import topology_page
        weak = topology_page.view(_list_name(), {}).get("weak") or []
        entry = next((w for w in weak if w.get("key") == device), None)
        if entry is None:
            # Drawn at the top of the region: there is no weak point here to draw a form under.
            return _region(400, op={"state": "refused", "refused": (
                f"{topology_expected.words_for(device)} is not a weak point on the map now, "
                "so there is nothing to accept")})
        holds = entry["holds"]
    got = topology_expected.declare(_list_name(), device, request.form.get("reason", ""),
                                    identity.request_actor(), holds=holds)
    if not got["ok"]:
        return _region(400, op={"state": "form", "device": device, "refused": got["error"],
                                "reason": request.form.get("reason", "")})
    return _result(dict(got, state="declared", device=device, weak=holds is not None,
                        words=topology_expected.words_for(device)))


@bp.route("/expected/withdraw", methods=["POST"])
def expected_withdraw():
    """Withdraw a declaration, as the verified person: the island warns again; recorded."""
    from modules import identity, topology_expected

    device = (request.form.get("device") or "").strip()
    got = topology_expected.withdraw(_list_name(), device, identity.request_actor())
    if not got["ok"]:
        return _region(409, op={"state": "refused", "device": device, "refused": got["error"]})
    return _result(dict(got, state="withdrawn", device=device,
                        weak=device.startswith((topology_expected.SPOF, topology_expected.BRIDGE)),
                        words=topology_expected.words_for(device)))


@bp.route("/positions", methods=["POST"])
def positions_save():
    """A person dropped a device (C661): the map as it now stands is saved as the network's
    layout, for everyone, as the verified person, the device named in the record. Every place
    must be a device the map draws; a refusal names what it compared and redraws the map as
    saved."""
    from modules import identity, topology_positions

    list_name = _list_name()
    known = set(_graph(list_name).get("nodes") or {})
    moved = (request.form.get("moved") or "").strip()
    places, error = topology_positions.parse(request.form.get("positions", ""), known)
    if not error and moved not in places:
        error = f"the device moved, {moved!r}, is not among the places sent"
    if error:
        return _region(400, op={"state": "refused", "refused": f"the move was not saved: {error}"})
    got = topology_positions.save(list_name, places, identity.request_actor(), moved)
    if not got["ok"]:
        return _region(409, op={"state": "refused", "refused": got["error"]})
    return _result(dict(got, state="moved", device=moved))


@bp.route("/path", methods=["POST"])
@no_store
def path_run():
    """Path… (board D): trace the path packets take from a device to an address, as the
    verified person, as a job reading each hop's forwarding table through the reads engine
    (each read recorded). Refused now, naming what it compared, with nothing asked; else the
    region drawn with the trace's record, which redraws as `path_trace` is announced."""
    from flask import redirect, url_for

    from modules import identity, path_trace, topology_page

    list_name = _list_name()
    net = _graph(list_name)
    nodes, bgp = net.get("nodes") or {}, (net.get("layers") or {}).get("bgp") or []
    a, b = (request.form.get("a") or "").strip(), (request.form.get("b") or "").strip()
    words = next((d["words"] for d in path_trace.destinations(nodes, bgp) if d["value"] == b),
                 b)
    got = path_trace.start(list_name, a, b, words, identity.request_actor(),
                           nodes=nodes, bgp=bgp)
    values = {k: request.form.get(k) for k in topology_page.ASKS
              if request.form.get(k) is not None}
    values.update(a=a, b=b, trace=got.get("trace", ""))
    s = topology_page.ask(values)
    there = url_for("topology_v2.page") + topology_page.qs(list_name, s)
    if not request.headers.get("HX-Request"):
        if "refused" in got:
            from routes.v2 import _page
            return _page("v2/topology.html", active_nav="topology", list_name=list_name,
                         **_ctx(values, path_refused=got["refused"]))
        return redirect(there)
    if "refused" in got:
        return _region(400, values, path_refused=got["refused"])
    resp = _region(200, values)
    resp.headers["HX-Push-Url"] = there
    return resp


@bp.route("/positions/reset", methods=["POST"])
def positions_reset():
    """Reset layout: withdraw every person's moves, as the verified person; the generated layout
    is drawn for everyone; recorded."""
    from modules import identity, topology_positions

    got = topology_positions.reset(_list_name(), identity.request_actor())
    if not got["ok"]:
        return _region(409, op={"state": "refused", "refused": got["error"]})
    return _result(dict(got, state="reset"))
