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
    units are in the order the program sends them; ``hash`` is the selection's; ``close`` the
    collector step's one session and the close helper's dry run naming it (C3078). One home:
    the catalog's drawn plan (`catalog._resubscribe_drawn`), what a proposal previews."""
    from modules.heal.catalog import _resubscribe_drawn

    return _resubscribe_drawn(p)


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
    from modules.heal import run_card

    host = dev["hostname"]
    subs = _subs(args.get("subs", ""))
    c = {"host": host, "list": ref.name, "subs": subs, "state": "preview",
         "job": args.get("job", ""), "run": args.get("run", ""), "error": "",
         "reason": str(args.get("reason") or "")[:300], "bound_s": R.VERIFY_BOUND_S,
         "wait_s": R.WAIT_S, "outcome_words": dict(R.OUTCOME_WORDS)}
    c.update(answer)
    if not c["run"] and not c["error"]:
        # Opened with no run named while one runs on this device (a refresh, a second tab,
        # another person): that run, never a fresh offer.
        going = run_card.running_resubscribe(ref.name, host)
        if going is not None:
            c.update(run=going["run"], job=going["job"])
            if not going["run"]:
                c["state"] = "running"
                return c
    if c["run"]:
        # Running, or its result: the outcome first, each subscription's checks, and the
        # steps taken on THE stepper, from the record History keeps whole (`run_card`).
        c.update(run_card.resubscribe_view(ref.name, host, c["run"], c["job"]))
        return c
    # The device's last run, when it ended inside the day (`run_card.FINISHED_KEEP_S`): its
    # outcome and the steps it took lead the card, so a run that ended while nobody watched
    # (or before Mercury restarted) is read where it was started (the operator, 2026-11-11).
    last = run_card.last_view(ref.name, host)
    if last is not None:
        c["last"] = last
    # Another run holds the device: the buttons are not offered, and say which run, since when
    # and by whom, from the hold the confirm would be refused by (`in_flight.held_action`).
    from modules import in_flight
    from routes.operations import viewer_key
    held = in_flight.held_action(ref.name, host, viewer_key())
    if held:
        c["held"] = held
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
    fixit = _fixit_args(args)
    proposed = ""
    if fixit:
        # Opened from an incident's page (its AI troubleshooting section's proposal, C3106):
        # the form carries the incident and the proposal into the confirm, and a repeat of an
        # attempt that failed asks what is different now.
        c["fixit"] = _fixit_card(ref.name, host, fixit, ticked, False)
        proposed = c["fixit"].pop("operation", "")
    # The collector step (C3078): asked for by the card (``collector``), or the proposal it was
    # opened for names it. Its plan asks the close helper's dry run, which closes nothing.
    c["collector"] = (str(args.get("collector") or "") == "1" or proposed == R.COLLECTOR_KEY)
    if not whole["ok"]:
        p = whole
    elif ticked:
        p = R.plan(ref.name, host, ticked, sources=src)
        if c["collector"] and p["ok"]:
            # The step's own plan; refused, the plain re-subscribe stays offered beside why.
            stepped = R.plan(ref.name, host, ticked, collector=True, sources=src)
            if stepped["ok"]:
                p = stepped
                if fixit:
                    # The repeat read under what runs: the collector step (`section._card`).
                    c["fixit"] = {k: v for k, v in _fixit_card(
                        ref.name, host, fixit, ticked, False, collector=True).items()
                        if k != "operation"}
            else:
                c["collector_refused"] = _masked(stepped)["refusals"]
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
                             "refused": "; ".join(one["refusals"]),
                             "fixit": ({k: v for k, v in _fixit_card(
                                 ref.name, host, fixit, [r["sub"]], True).items()
                                 if k != "operation"} if fixit else None)})
    return c


def _fixit_args(args) -> dict:
    """The incident and the proposal a card opened from an incident's page carries (``fixit``,
    ``proposal``), or ``{}``."""
    incident = str(args.get("fixit") or "").strip()[:64]
    if not incident:
        return {}
    return {"incident": incident, "proposal": str(args.get("proposal") or "").strip()[:16]}


def _fixit_again(form) -> dict:
    """The card's arguments that carry an incident when it is drawn again after a refusal."""
    got = _fixit_args(form)
    return {"fixit": got["incident"], "proposal": got["proposal"]} if got else {}


def _fixit_card(network: str, host: str, fixit: dict, subs, readd: bool,
                collector: bool = False) -> dict:
    """What the card draws for the incident it was opened for (`section.card_link`, its repeat
    read under what runs: the collector step with *collector*), and the proposal's operation
    under ``operation``, which the card reads and takes out before it draws (C3078: a proposal
    naming the collector step opens the card with it)."""
    from modules.fixit import section

    return section.card_link(network, fixit["incident"], fixit["proposal"], host, subs, readd,
                             collector)


def _fixit_link(network: str, host: str, form, subs, readd: bool = False,
                collector: bool = False):
    """``(link, refusal)``: what the confirm writes into its run's record when the card was
    opened from an incident's page (`section.confirm_link`), ``(None, "")`` when it was not,
    or ``(None, why)`` refused with nothing sent."""
    from modules.fixit import section

    fixit = _fixit_args(form)
    if not fixit:
        return None, ""
    try:
        return section.confirm_link(network, fixit["incident"], fixit["proposal"], host, subs,
                                    form.get("different") or "", readd, collector), ""
    except section.Refused as exc:
        return None, str(exc)


def _draw(ref, dev, args, code=200, **answer):
    c = card(ref, dev, args, **answer)
    _seen(c)
    return _strict(render_template("v2/_resubscribe.html", c=c), code)


def _seen(c: dict) -> None:
    """The person looking has read a run's outcome on this card (its result, or the last run
    the card leads with), so the In progress list's Finished stops listing that run for them:
    kept in memory beside the job's own mark (`capture_job.mark_opened`, `run_card`)."""
    from modules.heal import run_card
    from modules.nsot import capture_job
    from routes.operations import viewer_key

    viewer = viewer_key()
    if c.get("state") == "result" and c.get("run"):
        run_card.mark_opened(c["run"], viewer)
        if c.get("job"):
            capture_job.mark_opened(c["job"], viewer)
    elif c.get("last"):
        run_card.mark_opened(c["last"]["run"], viewer)


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
    again = dict({"subs": form.get("subs") or ",".join(subs), "picked": "1", "sub": subs},
                 **_fixit_again(form))
    link, why = _fixit_link(ref.name, dev["hostname"], form, subs)
    if why:
        return _draw(ref, dev, again, 409, error=why, reason=reason)
    got = R.start(ref.name, dev["hostname"], subs, confirmed=_confirmed(form, subs),
                  program=(form.get("program") or "").strip(),
                  previewed=(form.get("previewed") or "")[:200], reason=reason, fixit=link,
                  **_who())
    if got.get("refused"):
        return _draw(ref, dev, again, _refused_code(got), error=got["refused"], reason=reason)
    return _draw(ref, dev, {"subs": ",".join(subs), "run": got["run"], "job": got["job"]})


@bp.route("/device/<name>/resubscribe/close", methods=["POST"])
def close_confirm(name):
    """Start the re-subscribe WITH the collector step (C3078) as a job, as the verified person:
    the collector's one stale session closed through the root-owned close helper, then the
    ticked subscriptions re-subscribed, bound to each subscription's previewed hash and to the
    selection's (``program``), which holds the session the dry run named (``close``, the
    device's end as the card drew it); or the refusal drawn in place with nothing sent and
    nothing closed, the ticks and the reason kept."""
    from modules.heal import resubscribe as R

    found, refusal = _device_or_404(name)
    if refusal is not None:
        return refusal
    ref, dev = found
    form = request.form
    subs = [s for s in form.getlist("sub") if s][:20]
    reason = form.get("reason") or ""
    again = dict({"subs": form.get("subs") or ",".join(subs), "picked": "1", "sub": subs,
                  "collector": "1"}, **_fixit_again(form))
    link, why = _fixit_link(ref.name, dev["hostname"], form, subs, collector=True)
    if why:
        return _draw(ref, dev, again, 409, error=why, reason=reason)
    got = R.start(ref.name, dev["hostname"], subs, confirmed=_confirmed(form, subs),
                  program=(form.get("program") or "").strip(),
                  previewed=(form.get("previewed") or "")[:200], reason=reason,
                  collector=True, previewed_close=(form.get("close") or "")[:60], fixit=link,
                  **_who())
    if got.get("refused"):
        return _draw(ref, dev, again, _refused_code(got), error=got["refused"], reason=reason)
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
    link, why = _fixit_link(ref.name, dev["hostname"], form, [sub], readd=True)
    if why:
        return _draw(ref, dev, dict({"subs": form.get("subs") or sub}, **_fixit_again(form)),
                     409, error=why)
    got = R.start(ref.name, dev["hostname"], [sub],
                  confirmed={sub: (form.get("hash") or "").strip()},
                  reason=form.get("reason") or "", readd=True, fixit=link, **_who())
    if got.get("refused"):
        return _draw(ref, dev, {"subs": form.get("subs") or sub}, _refused_code(got),
                     error=got["refused"])
    return _draw(ref, dev, {"subs": sub, "run": got["run"], "job": got["job"]})
