"""routes/resubscribe_v2.py — Re-subscribe a lost telemetry stream (C2838;
`modules/heal/resubscribe.py`), drawn in place on the lost stream's Needs attention row.

The row "<device>: telemetry stream lost …" (`attention.grafana_source`, every member a
lost-stream rule of one device) carries **Re-subscribe <device>'s streams <ids>…**, which opens
the row to this card (`templates/v2/_resubscribe.html`), read by `card` when it is opened:

- ``preview``: what will be true afterwards, the device it touches, the undo, each subscription
  ticked with its receiver line from committed intent and its own hash, the exact program one
  level down, a reason (in the hash and the record: each removal is Mode B), and the button
  named for the work, which posts `confirm`. Several ticked are a batch (every removal, one
  wait, every re-add), drawn for exactly the ticks shown and bound to the selection's hash: a
  tick changed asks `preview` again for that selection. A subscription not in the alert that
  sends to the same receiver is listed too, unticked, and said while it stays so;
- ``running``: the run as a job (listening for ``privileged``, the announcement its end makes);
- ``result``: the outcome, never green over a partial, each subscription's three checks and any
  stale half-open session flagged, the record on History;
- a receiver a run left removed leads the card, in danger, with **Re-add the receiver**, which
  posts `readd` (the one-step operation, through the same preview and confirm).

The routes' declarations live in their tables (`route_gates.GATES`, `invalidation.DECLARED`,
`operation_stages.STAGES` and `HISTORY`); `gates()`, `invalidates()`, `stages()` and `history()`
are views of those tables.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _device_or_404, _strict, carry_list

log = logging.getLogger(__name__)

bp = Blueprint("resubscribe_v2", __name__, url_prefix="/v2")
bp.url_defaults(carry_list)       # the page's network on every URL it draws (C494)


def _prefix_rows(table: dict) -> dict:
    return {k: v for k, v in table.items() if k.startswith(bp.name + ".")}


def gates() -> dict:
    """These routes' rows of `modules/route_gates.py`'s GATES."""
    from modules.route_gates import GATES

    return _prefix_rows(GATES)


def invalidates() -> dict:
    """These routes' rows of `modules/invalidation.py`'s DECLARED."""
    from modules.invalidation import DECLARED

    return _prefix_rows(DECLARED)


def stages() -> dict:
    """The confirms' five stages, their rows of `modules/operation_stages.py`'s STAGES."""
    from modules.operation_stages import STAGES

    return _prefix_rows(STAGES)


def history() -> dict:
    """Where each route's record is read later, its rows of `operation_stages.HISTORY`."""
    from modules.operation_stages import HISTORY

    return _prefix_rows(HISTORY)


def _subs(text: str) -> list:
    return [s.strip() for s in str(text or "").split(",") if s.strip()][:20]


def _masked(p: dict) -> dict:
    """What the card draws of a plan: no inventory row, no intent, every line masked. The
    units are in the order the program sends them; ``hash`` is the selection's."""
    from modules.redact import redact_text

    return {"ok": p["ok"], "refusals": [redact_text(x) for x in p["refusals"]],
            "dialect": p["dialect"], "hash": p.get("hash", ""),
            "units": [{"sub": u["sub"], "line": redact_text(u["line"]), "hash": u["hash"],
                       "remove": [redact_text(x) for x in u["remove"]],
                       "readd": [redact_text(x) for x in u["readd"]]} for u in p["units"]]}


def _ticks(args) -> list:
    """The ticked subscriptions a form sent (``sub``, repeated), from a request's arguments or
    a plain mapping."""
    got = args.getlist("sub") if hasattr(args, "getlist") else (args.get("sub") or [])
    return [str(s).strip() for s in ([got] if isinstance(got, str) else got)
            if str(s).strip()][:40]


def _choices(R, network: str, host: str, whole: dict, src) -> tuple:
    """``(choices, refused)``. *choices* is every subscription the card lets a person tick:
    the ones it was opened for, then each other subscription of the device that sends to the
    same receiver as one of them (it may keep the connection they share, so it is offered
    beside them): ``[{"sub", "line", "hash", "shares"}]``, the hash each one's own, the same
    whatever else is ticked. *refused* is why such a subscription cannot be offered, by id."""
    from modules.redact import redact_text

    out = [{"sub": u["sub"], "line": redact_text(u["line"]), "hash": u["hash"], "shares": []}
           for u in whole["units"]]
    refused = {}
    for x in whole["sharing"]:
        one = R.plan(network, host, [x["sub"]], sources=src)
        if one["ok"]:
            u = one["units"][0]
            out.append({"sub": u["sub"], "line": redact_text(u["line"]), "hash": u["hash"],
                        "shares": list(x["shares"])})
        else:
            refused[x["sub"]] = redact_text("; ".join(one["refusals"]))
    return out, refused


def card(ref, dev, args, **answer) -> dict:
    """The card's context, in the state its query names; reads only Mercury's records.

    In the preview, ``subs`` is what the card was opened for and ``sub`` (with ``picked``) the
    ticks a redraw carries: the program, its hash and the button are drawn for exactly the
    ticked subscriptions, in the card's order, so the confirm sends what was drawn."""
    from modules.heal import resubscribe as R
    from modules.nsot import capture_job, privileged

    host = dev["hostname"]
    subs = _subs(args.get("subs", ""))
    c = {"host": host, "list": ref.name, "subs": subs, "state": "preview",
         "job": args.get("job", ""), "run": args.get("run", ""), "error": "",
         "reason": str(args.get("reason") or "")[:300], "bound_s": R.VERIFY_BOUND_S,
         "wait_s": R.WAIT_S, "outcome_words": dict(R.OUTCOME_WORDS)}
    c.update(answer)
    if c["run"]:
        j = capture_job.get(c["job"]) if c["job"] else None
        rec = privileged.get(ref.name, c["run"])
        if rec is None or (rec.get("state") == "running" and (j is None or
                                                             j["state"] == "running")):
            c["state"] = "running"
        else:
            # What the result draws, of the record History keeps whole (its steps, sessions
            # and program are read there).
            c.update(state="result", record=dict(
                {k: rec.get(k) for k in ("state", "outcome", "why", "actor", "at", "reason",
                                         "hash")},
                subscriptions=[{k: s.get(k) for k in ("sub", "outcome", "verify", "stale")}
                               for s in rec.get("subscriptions") or []]))
        return c
    src = R.Sources(ref.name)                         # committed intent read once
    whole = R.plan(ref.name, host, subs, sources=src)
    c["choices"], refused = (_choices(R, ref.name, host, whole, src) if whole["ok"]
                             else ([], {}))
    offered = [ch["sub"] for ch in c["choices"]]
    if args.get("picked") and whole["ok"]:
        ticks = _ticks(args)
        ticked = [s for s in offered if s in ticks]
    else:
        ticked = list(offered[:len(whole["units"])]) if whole["ok"] else list(subs)
    c["ticked"] = ticked
    if not whole["ok"]:
        p = whole
    elif ticked:
        p = R.plan(ref.name, host, ticked, sources=src)
    else:
        p = {"ok": False, "refusals": [], "dialect": whole["dialect"], "units": [], "hash": "",
             "sharing": []}
    c["plan"] = _masked(p)
    # A subscription left unticked that sends to a ticked one's receiver: said, and offered.
    c["sharing"] = [dict(x, offered=x["sub"] in offered, refused=refused.get(x["sub"], ""))
                    for x in p.get("sharing") or []]
    c["removed"] = []
    for r in R.removed_now(ref.name, host):
        one = R.plan(ref.name, host, [r["sub"]], readd=True, sources=src)
        c["removed"].append({"sub": r["sub"], "run": r["run"],
                             "hash": (one["units"][0]["hash"] if one["ok"] else ""),
                             "refused": "; ".join(one["refusals"])})
    return c


def _draw(ref, dev, args, code=200, **answer):
    return _strict(render_template("v2/_resubscribe.html", c=card(ref, dev, args, **answer)),
                   code)


@bp.route("/device/<name>/resubscribe", methods=["GET"])
def preview(name):
    """The card in the state its query names (``subs``; ``run`` and ``job`` once started; a
    tick changed sends ``picked``, each ticked ``sub`` and the typed ``reason``, and the card
    is drawn again for that selection). Asks no device: the program is read from committed
    intent."""
    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    return _draw(ref, dev, request.args)


def _confirmed(form, subs) -> dict:
    """Each ticked subscription's hash as previewed: the form's ``hash::<id>``."""
    return {s: (form.get("hash::" + s) or "").strip() for s in subs}


def _who() -> dict:
    """The request's verified actor, how it was established and whether it is a person, each
    as the request's own identity states it (`identity.actor_verification` reads the kind
    through `identity.verification_of`, which fails closed: an identity that does not say how
    it was established is ``none``). The operation refuses anything but a verified person
    (`resubscribe.person_refusal`), whatever the gate's settings allow."""
    from modules import identity

    actor = identity.request_actor()
    ident = identity.verified_identity()
    return {"actor": actor, "actor_verified": identity.actor_verification(actor),
            "person": bool(ident is not None and ident.kind == "person")}


def _refused_code(got: dict) -> int:
    """A confirm that is not a verified person's is 403; any other refusal is 409."""
    return 403 if got.get("not_a_person") else 409


@bp.route("/device/<name>/resubscribe/confirm", methods=["POST"])
def confirm(name):
    """Start the re-subscribe of the ticked subscriptions as a job, as the verified person,
    each bound to its previewed hash and the selection to its own (``program``, for the
    subscriptions ``previewed`` names), with the person's reason; or draw the refusal in place
    with nothing sent, the ticks and the reason kept."""
    from modules.heal import resubscribe as R

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    form = request.form
    subs = [s for s in form.getlist("sub") if s][:20]
    reason = form.get("reason") or ""
    got = R.start(ref.name, dev["hostname"], subs, confirmed=_confirmed(form, subs),
                  program=(form.get("program") or "").strip(),
                  previewed=(form.get("previewed") or "")[:200], reason=reason, **_who())
    if got.get("refused"):
        return _draw(ref, dev, {"subs": form.get("subs") or ",".join(subs), "picked": "1",
                                "sub": subs},
                     _refused_code(got), error=got["refused"], reason=reason)
    return _draw(ref, dev, {"subs": ",".join(subs), "run": got["run"], "job": got["job"]})


@bp.route("/device/<name>/resubscribe/readd", methods=["POST"])
def readd(name):
    """Re-add the receiver a run left removed (the one-step operation), as the verified
    person, bound to its previewed hash (``hash``, which its button carries: the re-add is one
    subscription's one send, so its own hash is its whole program); or draw the refusal in
    place with nothing sent."""
    from modules.heal import resubscribe as R

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    form = request.form
    sub = (form.get("sub") or "").strip()
    got = R.start(ref.name, dev["hostname"], [sub],
                  confirmed={sub: (form.get("hash") or "").strip()},
                  reason=form.get("reason") or "", readd=True, **_who())
    if got.get("refused"):
        return _draw(ref, dev, {"subs": form.get("subs") or sub}, _refused_code(got),
                     error=got["refused"])
    return _draw(ref, dev, {"subs": sub, "run": got["run"], "job": got["job"]})
