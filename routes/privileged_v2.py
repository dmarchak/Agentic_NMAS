"""Tier 2 on v2: "Run a privileged command…" (boards T2-A to T2-D, approved 2026-10-08;
`modules/nsot/privileged.py`).

One card, from the device page's Actions menu, in the state its query names:

- ``choose`` (T2-A): the five commands (one not yet measured, said), and the device's own
  interfaces from its committed golden, the management one left out;
- ``reading``: the before-state being read (a reads-engine run, listening for ``reads``);
- ``confirm`` (T2-B, T2-D): the before-state, what it affects, what it will not do, why rollback
  does not apply, a reason, and the confirm bound to the plan's hash;
- ``running``: the command being sent (listening for ``privileged``);
- ``result`` (T2-C): before and after, the verdict, the record.
"""

import logging
import time

from flask import Blueprint, redirect, render_template, request, url_for

from routes.device_v2 import _device_or_404, _strict, carry_list

log = logging.getLogger(__name__)

bp = Blueprint("privileged_v2", __name__, url_prefix="/v2")
bp.url_defaults(carry_list)       # the page's network on every URL it draws (C494)


def card(ref, dev, args, back="overview") -> dict:
    """The card's context from its query: ``key``, ``arg``, ``run`` (the preview read), ``job``,
    ``result`` (a run's record), ``error``."""
    from modules.nsot import capture_job, privileged, reads
    host = dev["hostname"]
    key, arg = args.get("key", ""), args.get("arg", "")
    c = {"host": host, "list": ref.name, "key": key, "arg": arg, "back": back,
         "job": args.get("job", ""), "error": args.get("error", ""), "state": "choose"}
    c["plan"] = privileged.plan(ref.name, host, key, arg)
    if args.get("result"):
        # The JOB first, then the record (C642): read the other way round, a job that finished
        # between the two reads drew its run as a result still "running", in red, listening for
        # nothing. A job seen ended means its record is final.
        j = capture_job.get(c["job"]) if c["job"] else None
        rec = privileged.get(ref.name, args["result"])
        if rec is None or (rec.get("state") == "running" and j and j["state"] == "running"):
            c.update(state="running", run=args["result"])
        else:
            c.update(state="result", record=rec, run=args["result"])
        return c
    if args.get("run"):
        rec = reads.get(ref.name, args["run"])
        if rec is None or rec.get("state") == "running":
            c.update(state="reading", run=args["run"])
            return c
        r = (rec.get("results") or {}).get(host) or {}
        answer = next(iter(r.get("answers") or []), None)
        if rec.get("state") == "refused" or not answer or answer.get("state") != reads.ANSWERED:
            c.update(state="read_failed", run=args["run"],
                     why=rec.get("refused") or (answer or {}).get("why") or r.get("why")
                     or "no answer")
            return c
        before = answer.get("answer", "")
        c.update(state="confirm", run=args["run"], before=before, cut=answer.get("cut"),
                 read_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(rec["finished_at"]))
                 if rec.get("finished_at") else "",
                 changes_nothing=key == "undebug-all" and privileged.nothing_on(before))
    return c


def _card_or_page(ref, dev, args, back):
    c = card(ref, dev, args, back)
    if request.headers.get("HX-Request"):
        return _strict(render_template("v2/_privileged.html", c=c))
    return redirect(url_for("device_v2.device", name=dev["hostname"], list=ref.name, tab=back,
                            op="privileged", **{k: v for k, v in args.items() if v}))


@bp.route("/device/<name>/privileged", methods=["GET"])
def privileged(name):
    """The card alone, in the state its query names. Asks no device."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _strict(render_template("v2/_privileged.html",
                                   c=card(ref, dev, request.args, request.args.get("back", "overview"))))


@bp.route("/device/<name>/privileged/preview", methods=["POST"])
def preview(name):
    """Read the before-state through the reads engine, as the verified person (a recorded run),
    or draw the plan's refusal with nothing read."""
    from modules import identity
    from modules.nsot import privileged as P
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    key, arg = request.form.get("key", ""), request.form.get("arg", "")
    back = request.form.get("back", "overview")
    got = P.preview(ref.name, dev["hostname"], key, arg, identity.request_actor())
    args = {"key": key, "arg": arg, "run": got.get("run", ""), "job": got.get("job", ""),
            "error": "; ".join(got["plan"]["refusals"]) or got.get("refused", "")}
    if args["error"]:
        args["run"] = ""
    return _card_or_page(ref, dev, args, back)


@bp.route("/device/<name>/privileged/confirm", methods=["POST"])
def confirm(name):
    """Send the confirmed command as a job, as the verified person, bound to the previewed plan's
    hash, with the person's reason; or draw the refusal with nothing sent."""
    from modules import identity
    from modules.nsot import privileged as P
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    f = request.form
    got = P.start(ref.name, dev["hostname"], f.get("key", ""), f.get("arg", ""),
                  actor=identity.request_actor(), confirmed_hash=f.get("hash", ""),
                  reason=f.get("reason", ""))
    back = f.get("back", "overview")
    if got.get("refused"):
        args = {"key": f.get("key", ""), "arg": f.get("arg", ""), "run": f.get("run", ""),
                "error": got["refused"]}
        return _card_or_page(ref, dev, args, back)
    return _card_or_page(ref, dev, {"key": f.get("key", ""), "arg": f.get("arg", ""),
                                    "result": got["run"], "job": got["job"]}, back)
