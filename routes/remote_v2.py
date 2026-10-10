"""routes/remote_v2.py — History › Remote set-up on v2 (C631, 2026-10-10).

The card opens from History's header: connect a network's existing remote, the write probe,
what a first push would publish and its typed acknowledgement, and automatic pushing. Every
POST carries its network (a write path carries its list) and is gated in `route_gates` on
`publish_remote` (a verified person), except reading what a first push would publish, which
writes nothing. The acts are `modules/remote_setup.py`'s, which call the same
`modules/nsot/remote.py` functions today's `/remote/*` routes do. Nothing here contacts a
device; the write probe and a push are the only things that write outside this host.
"""

import logging

from flask import Blueprint, render_template, request
from html import escape

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("remote_v2", __name__, url_prefix="/v2/history/remote/setup")


def _card(list_name: str, code: int = 200, **ctx):
    from modules import remote_setup as S

    return _strict(render_template("v2/_remote_setup.html", s=S.view(list_name), **ctx), code)


def _network(source) -> str:
    from modules import remote_setup as S
    from modules.nsot import listref

    named = (source.get("list") or "").strip()
    return S.network(named) if named else listref.active().name


@bp.route("", methods=["GET"])
def card():
    """The set-up card for the network named (History's own, by default)."""
    from modules import remote_setup as S

    try:
        return _card(_network(request.args))
    except S.Refused as exc:
        return _strict(f'<section class="card" id="remote-setup"><p class="notice notice-danger">'
                       f"Couldn't load: {escape(str(exc))}</p></section>", 404)


@bp.route("/closed", methods=["GET"])
def closed():
    """Close: the empty slot below History's header, as the page draws it."""
    return _strict('<div id="remote-setup"></div>')


def _act(fn, **result_key):
    from modules import remote_setup as S

    try:
        list_name = S.network(request.form.get("list", ""))
    except S.Refused as exc:
        return _strict(f'<section class="card" id="remote-setup"><p class="notice notice-danger">'
                       f"Not done: {escape(str(exc))}.</p></section>", 404)
    try:
        out = fn(list_name)
    except S.Refused as exc:
        return _card(list_name, 409, refused=str(exc))
    return _card(list_name, **{k: out for k in result_key})


@bp.route("/connect", methods=["POST"])
def connect():
    """Record the network's existing remote: alias, owner, repository, branch, key path, each
    one token of its shape (C636); never edits the host's SSH configuration."""
    from modules import identity
    from modules import remote_setup as S

    return _act(lambda n: S.connect(n, request.form, identity.request_actor()), connected=1)


@bp.route("/write-probe", methods=["POST"])
def write_probe():
    """The read-only checks and the write probe: an empty commit to a scratch ref, removed."""
    from modules import identity
    from modules import remote_setup as S

    return _act(lambda n: S.write_probe(n, identity.request_actor()), probed=1)


@bp.route("/publication", methods=["POST"])
def publication():
    """What a first push would publish: counts, kinds and fingerprints, never a value."""
    from modules import remote_setup as S

    return _act(S.publication, pub=1)


@bp.route("/acknowledge", methods=["POST"])
def acknowledge():
    """The typed acknowledgement, bound to the fingerprints the card showed."""
    from modules import identity
    from modules import remote_setup as S

    who = identity.identify(request)
    return _act(lambda n: S.acknowledge(n, request.form.get("typed", ""),
                                        request.form.getlist("shown"),
                                        identity.request_actor(), who.kind), acknowledged=1)


@bp.route("/auto-push", methods=["POST"])
def auto_push():
    """Turn automatic pushing on: offered only after a successful push."""
    from modules import identity
    from modules import remote_setup as S

    return _act(lambda n: S.auto_push(n, identity.request_actor()), auto=1)
