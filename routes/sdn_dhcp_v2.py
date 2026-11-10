"""routes/sdn_dhcp_v2.py — SDN › Apps, the DHCP steering card (Lab 9 Objective 4, C2904; board
docs/boards/lab9-sdn.html artboard B, self-signed 2026-11-10 under the Phase 7 mode).

One operation (modules/sdn/dhcp_steer.py): Edit settings… draws the choice of edge switches in
the card's place (a read); Preview steering… compiles the flows from the committed NSOT export,
reads each switch's table and draws every flow and its REST body with the hash (writes
nothing); the confirm, bound to that hash as a verified person, rebuilds the preview, then
applies one plan per switch through the one flow path (`flow_ops.apply`, ``writer`` =
``feature:dhcp-unicast``), each holding its switch, verified, rolled back on failure and
recorded. Remove steering… is the same, for exactly the flows this feature recorded. The card
is drawn in place of itself (``#dhcp-steering``).
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("sdn_dhcp_v2", __name__, url_prefix="/v2/sdn/dhcp")


def _card(s: dict, status: int = 200):
    from modules.sdn import dhcp_steer

    return _strict(render_template("v2/_sdn_dhcp.html", s=dhcp_steer.view(s))), status


def _network() -> tuple:
    from routes.list_param import submitted_list

    return submitted_list(request)


def _read_network() -> str:
    from modules.nsot import listref
    from routes.list_param import named_list

    return named_list(request) or listref.active().name


def _chosen():
    """The edge switches the form chose: None for every one (``scope=all``), else the
    ``switch`` fields."""
    if (request.form.get("scope") or "all") == "all":
        return None
    return [s.strip() for s in request.form.getlist("switch") if s.strip()]


def _cookies() -> dict:
    """The preview's cookies, carried as ``key=cookie`` fields (`dhcp_steer.flow_key`)."""
    out = {}
    for item in request.form.getlist("cookie"):
        key, sep, value = item.rpartition("=")
        if sep and value.isdigit():
            out[key] = int(value)
    return out


def _refused(network: str, words: str, status: int):
    return _card({"state_card": "refused", "network": network, "error": words}, status)


@bp.route("/card", methods=["GET"])
def card():
    """The card at rest (Cancel, Close): the server, the edge switches, what is steered by
    Mercury's record and the stored counters. A read."""
    from modules.sdn import dhcp_steer

    return _card(dhcp_steer.card(_read_network()))


@bp.route("/settings", methods=["GET"])
def settings():
    """Edit settings…: the edge switches to steer on (every one, or chosen), drawn in the card's
    place; its Preview… posts the choice. A read; nothing is stored."""
    from modules.sdn import dhcp_steer

    return _card(dict(dhcp_steer.card(_read_network()), state_card="settings"))


@bp.route("/preview", methods=["POST"])
def preview():
    """Preview steering…: the compiled flows, each switch's table read now, every request and
    its REST body, and the hash the confirm binds. Writes nothing."""
    from modules.sdn import dhcp_steer

    network, refused = _network()
    if refused:
        return _refused(network, refused, 400)
    p = dhcp_steer.preview(network, edge_switches=_chosen())
    if not p["ok"]:
        return _refused(network, p["error"], 409)
    return _card(dict(p, state_card="preview", scope=request.form.get("scope") or "all"))


@bp.route("/confirm", methods=["POST"])
def confirm():
    """Steer as the verified person, bound to the preview's hash: the preview made again from
    the same choice and cookies, then one plan per switch through the one flow path."""
    from modules import identity
    from modules.sdn import dhcp_steer

    network, refused = _network()
    if refused:
        return _refused(network, refused, 400)
    actor = identity.request_actor()
    done = dhcp_steer.confirm(network, "steer", (request.form.get("hash") or "").strip(),
                              actor=actor, actor_verified=identity.actor_verification(actor),
                              edge_switches=_chosen(), cookies=_cookies())
    return _card(dict(done, state_card="result"), 200 if done["outcome"] != "refused" else 409)


@bp.route("/remove/preview", methods=["POST"])
def remove_preview():
    """Remove steering…: every flow this feature recorded, each by delete-strict on its table,
    priority, match and cookie, and the hash the confirm binds. Writes nothing."""
    from modules.sdn import dhcp_steer

    network, refused = _network()
    if refused:
        return _refused(network, refused, 400)
    p = dhcp_steer.remove_preview(network)
    if not p["ok"]:
        return _refused(network, p["error"], 409)
    return _card(dict(p, state_card="preview"))


@bp.route("/remove/confirm", methods=["POST"])
def remove_confirm():
    """Remove the steering flows as the verified person, bound to the preview's hash."""
    from modules import identity
    from modules.sdn import dhcp_steer

    network, refused = _network()
    if refused:
        return _refused(network, refused, 400)
    actor = identity.request_actor()
    done = dhcp_steer.confirm(network, "remove", (request.form.get("hash") or "").strip(),
                              actor=actor, actor_verified=identity.actor_verification(actor))
    return _card(dict(done, state_card="result"), 200 if done["outcome"] != "refused" else 409)
