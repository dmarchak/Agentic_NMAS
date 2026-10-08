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
