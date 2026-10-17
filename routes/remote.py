"""Per-list git remote: Verify the remote and Push now, History's header's two buttons.

Publishing a network's configuration history — including the credentials in
it — is gated on ``publish_remote``: a verified PERSON, by default. Its own
operation kind rather than ``confirm``, so the audit reads "published" and so
a service grant written for some other operation cannot reach this one.

Verify is not gated: verification exists to be read *before* deciding, and a
gate on it would mean asking someone to authorise the thing they are trying to
evaluate.

Today's Remote card and its five other routes (/remote/status, /verify-write,
/preview, /acknowledge, /auto-push) left at 7.8 (2026-10-17, P7-21; /adopt on
2026-10-15). Their home is History: the header draws the remote's state from
the `remote-publication` reader and the list's record (`routes/v2._history_remote`),
and History › Remote set-up… (`routes/remote_v2.py` over `modules/remote_setup.py`)
connects, runs the write probe, reads what a first push publishes, takes its
typed acknowledgement and turns on automatic pushing, through the same
`modules/nsot/remote.py` functions those routes called.
"""

import logging

from flask import Blueprint, jsonify, request

from modules import identity
from modules.nsot import remote as R

log = logging.getLogger(__name__)
bp = Blueprint("remote", __name__, url_prefix="/remote")


def _list_name() -> str:
    from modules.config import get_current_list_name

    payload = request.get_json(silent=True) or {}
    return payload.get("list") or request.args.get("list") \
        or get_current_list_name()


@bp.route("/verify", methods=["POST"])
def verify():
    """The READ-ONLY pre-push checks. Ungated: this is how you decide.

    An SSH greeting, a ls-remote, two anonymous HTTPS requests. The write
    probe is deliberately not among them: it is History › Remote set-up…'s
    Run the write probe (`remote_v2.write_probe`), gated.
    """
    out = R.verify(_list_name(), with_write_probe=False, actor=identity.request_actor())
    return jsonify(out)


def _reread_publication() -> None:
    """A manual push goes around the post-commit hooks, so it re-reads the
    remote itself (C223): otherwise History's header and Needs attention kept
    "1 commit(s) not pushed" for up to a reader cycle after the push had sent
    it. On a thread, so the answer does not wait on the remote."""
    import threading

    from modules.readers.remote_publication import refresh_hook

    threading.Thread(target=refresh_hook, args=({},), daemon=True,
                     name="remote-publication-reread").start()


@bp.route("/push", methods=["POST"])
def push():
    """Publish. main + --follow-tags, then notes if any note ref exists."""
    ident, refusal = identity.require(request, "publish_remote")
    if refusal:
        return refusal

    list_name = _list_name()
    out = R.push(list_name, actor=ident.actor)
    _reread_publication()
    if not out["ok"]:
        return jsonify(out), 409
    out["auto_push_offered"] = True
    return jsonify(out)
