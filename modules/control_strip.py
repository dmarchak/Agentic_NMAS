"""The control strip (C3748; the operator's design, 2026-11-15): one component at the top of
Troubleshoot › Incidents, for the page's network (C3789: on Incidents alone, the operator,
2026-11-15). Needs attention, where G6's batch card is pressed, draws its run part alone
(`run_view`): the press's answer and the batch's run, no toggle.

- **Self-healing**: on is Auto for the network, for its default duration
  (`heal_auto_default_hours`, C3749; 1 hour by default), labelled "Auto until HH:MM"; off is
  Dry run. One press, no dialog, through the policy's own write (`policy.apply_planned`: every
  gate its plan holds, recorded with who and why in the network's settings record, which
  History draws as the person's change). C3823 (the operator's design, 2026-11-16: "switching
  Self-healing On IS the approval for what's already open"): while it is not On and open
  problems Mercury can fix stand (guard 6's held departures, the incidents an Automatic saved
  script matches), one line beside it says so ("Also fixes the 7 open problems (5 restores, 2
  saved scripts)", `heal.batch.switch_words`) and the switch carries that line's hash; turning
  it on runs them as C3819's batch (`switch_on`, `heal.batch.press` with ``switch``: every
  device at once, each verified on its own, guard 6 resolved for those listed, the runs named
  after the switch-on), never the AI, and is refused, nothing turned on, when they moved since
  drawn.
  G6's Fix all card on Needs attention stays only for guard 6 holds formed while it is On.
- **AI troubleshooting** (Gate 2, C3769; the operator's minimal design, 2026-11-15): "AI
  troubleshooting: Automatic", the network's one control's Automatic (`troubleshoot_control`). On
  is one press through the control's own route (`settings_v2.ai_ts_level`, ``answer=strip``):
  with open incidents to start on, one line beside it first ("Also starts on N open incidents,
  about $X"), its digest the press's, and nothing else; all of them start within the caps, one
  past a cap refused and named on its card. Refused until the network's spending limits and
  their estimate are acknowledged in Settings (the refusal links the limits card). Off goes
  back to Manual at once.
- A gear to each full setting (the network's Self-healing tab, Settings › AI).
- **The batch's run**: the newest Turn on self-healing and fix all (or switch-on) of the
  network this server holds, drawn on THE stepper while it runs (`heal.batch.STEPS`); once it
  ended, one line ("Self-healing switched on at 23:00: 2 fixed and verified in 3 min 17 s ·
  Details", `_run_line`), its steps under Details, for `RUN_LINE_S` after its end or until the
  person looking dismisses it (`routes/control_v2.run_seen`, the In progress list's own
  per-person marks, `seen_runs`). The strip draws again only when something announces, so the
  line leaves at the first redraw past its bound.

Both toggles show the live state, are usable only by a person who may change those settings
(`heal.batch.may_press`: a verified person, `identity.may` ``configure``); anyone else sees the
state read-only, with why. A read of the settings and this server's job registry: no device,
no outside service (CLAUDE.md, "No page load or badge poll waits on Grafana, Loki, NetBox, a
device or a computation").
"""

import logging
import threading
import time

log = logging.getLogger(__name__)

#: The strip's element id: the top bar's status chip links here (`#control-strip`).
ANCHOR = "control-strip"

#: C3866 (the operator, 2026-11-16: "Every switch flips instantly; the work it starts happens
#: after, in the background"): what a screen drew for a press, held in this process so the
#: press is checked against it by its hash and answers at once, with no second preview: the
#: Self-healing switch's line (``switch``), the AI switch's line (``ai_line``,
#: `troubleshoot_control.strip`) and the In progress list a person last drew (``chip``,
#: routes/operations). Display only: a press still binds its hash, and each item re-checks
#: its own at apply. Held as the Incidents list holds its rows (`incidents_list.held`, the
#: pattern): keyed by `invalidation.generation`, so the next announcement or declared change
#: drops it, and for at most `HELD_S` (15 minutes, a choice, nothing measured: longer than a
#: person reads a strip before pressing). Dropped, or in a process that did not draw it, the
#: press previews again (or a list is read again), as before.
HELD_S = 900
#: ``{(kind, key): (generation, monotonic, value)}``.
_held = {}
_held_lock = threading.Lock()


def hold(kind: str, key: str, value):
    """Keep *value*, what *kind*'s screen drew for *key* (a network, a viewer), as the newest,
    under the invalidation generation now: returns *value*. None forgets it."""
    from modules import invalidation

    with _held_lock:
        _held[(kind, key)] = (invalidation.generation(), time.monotonic(), value)
    return value


def held(kind: str, key: str):
    """What *kind*'s screen last drew for *key*, while nothing was announced or declared since
    and within `HELD_S`, or None."""
    from modules import invalidation

    with _held_lock:
        got = _held.get((kind, key))
    if got is None or got[0] != invalidation.generation() \
            or time.monotonic() - got[1] > HELD_S:
        return None
    return got[2]


def _run_card(job: dict) -> dict:
    """The batch job *job* (`capture_job.card_jobs`' row) on THE stepper: one row for the batch,
    its steps its own (`op_progress.run_of`, the live list; its record once it ended), then one
    row per device once known."""
    from modules import op_progress
    from modules import run_stepper as RS
    from modules.heal import batch
    from modules.nsot import capture_job

    got = capture_job.get(job["job"]) or {}
    live = op_progress.run_of(job["job"])
    result = ((got.get("payload") or {}).get("result") or {})
    steps = (live or {}).get("steps") or result.get("steps") or []
    ended = got.get("state") != "running"
    rec = RS.from_record(batch.STEPS, steps, ended=ended, labels=batch.STEP_LABELS)
    outcome = result.get("outcome") or ("failed" if got.get("state") == "failed" else "")
    group = ("running" if not ended else "done" if outcome == "fixed"
             else "failed" if outcome or got.get("state") == "failed" else "done")
    # C3823: the Self-healing switch's batch, told by its page (`heal.batch.SWITCH_PAGE`).
    from urllib.parse import urlsplit
    label = (batch.SWITCH if urlsplit(job.get("page") or "").path == batch.SWITCH_PAGE
             else batch.BUTTON)
    rows = [RS.row(label, group, rec["steps"], device=False)]
    for d in result.get("devices") or []:
        # ``already``: a saved script another path's run had in flight when the batch claimed
        # it (C3819), drawn running, never done: the batch did not verify it.
        g = {"healed": "done", "already": "running",
             "not_started": "not_reached"}.get(d.get("outcome"), "failed")
        rows.append(RS.row(d.get("device") or "?", g, [], detail=d.get("words") or ""))
    return {"job": job["job"], "state": got.get("state") or job.get("state"),
            "outcome": outcome, "words": result.get("words") or got.get("error") or "",
            "stepper": RS.card(rows, label=label, key="heal-batch"),
            "started_at": job.get("started_at"), "ended": ended,
            "line": _run_line(label, job, result, got) if ended else None}


#: How long a finished batch run's one line stays on the strip after it ended (the operator,
#: 2026-11-16: "the line leaves the strip a few minutes after the run ended"): 5 minutes, a
#: choice, nothing measured: long enough for the person who switched it on to read the outcome
#: when the page next redraws, short enough that the strip is back to its two switches by the
#: time a later problem is looked at. Its record stays: each device's outcome on its own
#: incident (`heal.batch._on_incident`), the batch's rows in the heal decisions, and the In
#: progress list's Finished entry until `capture_job.KEEP_S`.
RUN_LINE_S = 300
#: The run's name on its one line, by its press.
RUN_LINE_NAMES = {"Self-healing switched on": "Self-healing switched on",
                  "Turn on self-healing and fix all": "Fix all"}


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch))) if epoch else ""


def _run_line(label: str, job: dict, result: dict, got: dict) -> dict:
    """A finished batch run in one line (the operator, 2026-11-16: "Self-healing switched on at
    23:00: 2 fixed and verified in 3 min 17 s · Details"): ``{"name", "at", "counts", "took",
    "ok"}``, *at* the run's start (the switch-on), drawn by the page's clock; *counts* from the
    batch's own record of each device; *took* its wall time, from the job's own start and end
    (`run_stepper.duration_words`)."""
    from modules.run_stepper import duration_words

    devices = list(result.get("devices") or [])
    healed = sum(1 for d in devices if d.get("outcome") == "healed")
    if devices:
        counts = (f"{healed} fixed and verified" if healed == len(devices) else
                  f"{healed} of {len(devices)} fixed and verified; "
                  + ", ".join(d.get("device") or "?" for d in devices
                              if d.get("outcome") != "healed")[:120] + " did not")
    else:
        counts = result.get("words") or got.get("error") or "nothing was fixed"
    start, end = job.get("started_at"), job.get("finished_at")
    took = duration_words(float(end) - float(start)) if start and end else ""
    return {"name": RUN_LINE_NAMES.get(label, label), "at": _iso(start), "counts": counts,
            "took": took, "ok": bool(devices) and healed == len(devices)}


def newest_batch_job(network: str):
    """*network*'s newest kept batch job on this server (`capture_job.card_jobs`' row), or
    None: the one the strip draws."""
    from modules.heal import batch
    from modules.nsot import capture_job

    return next((j for j in capture_job.card_jobs() if j["kind"] == batch.KIND
                 and j["list"] == network), None)


def batch_ai_items(network: str) -> dict:
    """``{"items", "error"}``: the open incidents with no fix Mercury can run, for G6's batch
    (`fixit.auto.catch_up`'s items), read here because `heal.batch` is a module of the heal
    loop, which never reads the fix-it path (section 12's rule). *error* says why they could
    not be listed, never read as none."""
    from modules.fixit import auto as A

    got = A.catch_up(network)
    return {"items": got["items"],
            "error": "" if got["state"] == "ok" else
            f"the open incidents with no fix cannot be listed ({got['error']})"}


def batch_script_items(network: str) -> dict:
    """``{"items", "error"}``: every open incident of *network* an Automatic saved script
    matches, each with its plan previewed as `saved_plans.fire` previews it, asking no device
    (`saved_plans.script_preview`), for G6's batch (C3819). Each incident is classified from
    its page (`incident_page.resolve`), as the heal decision's `fire_matching` and the
    re-decide classify it, read here because `heal.batch` never reads an incident's page. An
    incident whose script already stands on it in Auto (in flight, or sent) is left out: a fire
    would run nothing. No Automatic script on the network reads no incident. *error* says why
    they could not be listed, never read as none."""
    from modules import incident_page
    from modules.heal import incidents as INC
    from modules.nsot import saved_plans as S

    try:
        if not any(e.get("mode") == "auto" for e in S.scripts(network).values()):
            return {"items": [], "error": ""}
        out = []
        for rec in INC.read(network).get("incidents") or []:
            if not isinstance(rec, dict) or rec.get("state") not in INC.OPEN_STATES:
                continue
            found = incident_page.resolve(network, rec.get("id") or "")
            if found.get("found") != "page":
                found = {"incident": rec, "entry": {}}
            got = S.script_preview(network, found)
            if not got or S.standing_fire(network, got["key"], rec["id"]):
                continue
            out.append(dict(got, incident=rec["id"],
                            device=rec.get("device") or got["values"].get("device") or ""))
        return {"items": out, "error": ""}
    except Exception as exc:                          # noqa: BLE001 (said, never read as none)
        return {"items": [], "error": (f"the saved scripts' matches cannot be listed "
                                       f"({type(exc).__name__}: {exc})")}


def batch_preview(network: str, rows: list = None) -> dict:
    """G6's batch card on *network* (`heal.batch.preview`), with the incidents for the AI
    (`batch_ai_items`) and the saved scripts' matches (`batch_script_items`) handed in."""
    from modules.heal import batch

    return batch.preview(network, rows, ai_items=batch_ai_items(network),
                         script_items=batch_script_items(network))


def fix_all(network: str, shown: str, *, actor: str, verified: str, ident) -> dict:
    """G6's one press (`heal.batch.press`), with what the heal loop never reads handed in: the
    incidents for the AI as the card listed them, the saved scripts' matches with their
    previewed plans, and the AI's starts (`heal_notice.start_catch_up`). Raises
    `heal.batch.Refused`, nothing started."""
    from modules import heal_notice
    from modules.heal import batch

    return batch.press(network, shown, actor=actor, verified=verified, ident=ident,
                       ai_items=batch_ai_items(network), start_ai=heal_notice.start_catch_up,
                       script_items=batch_script_items(network))


def switch_preview(network: str) -> dict:
    """The Self-healing switch's batch on *network* (C3823): `heal.batch.preview` with
    ``switch`` (guard 6's restores and the Automatic saved scripts' matches, no AI), the
    scripts' matches handed in (`batch_script_items`). Its ``also`` the line, its ``hash`` what
    the switch's press is bound to; *on* False when there is nothing open to fix."""
    from modules.heal import batch

    return hold("switch", network,
                batch.preview(network, script_items=batch_script_items(network), switch=True))


def switch_on(network: str, shown: str, *, actor: str, verified: str, ident) -> dict:
    """The Self-healing switch turned on with the open problems its line drew (C3823): C3819's
    batch (`heal.batch.press` with ``switch``), bound to *shown*, the line's hash, and no AI
    (nothing to start it is handed in). C3866: the line as this process drew it (`held`),
    pressed at its hash, is the batch approved, with no second preview; otherwise the saved
    scripts' matches are read again and the preview made again, as before, and the press takes
    that (C3909: the problems open at the press, never refused because the line moved; with
    none, self-healing turned on plainly, ``job`` None and ``words`` said). Raises
    `heal.batch.Refused`, nothing turned on and nothing started (`heal.batch.TurnedOn`: Auto
    on, nothing sent)."""
    import time as _time

    from modules.heal import batch

    t0 = _time.monotonic()
    drawn = held("switch", network)
    remade = drawn is None or drawn.get("hash") != (shown or "")
    if remade:
        # Not the line held: the preview made now (and held, `switch_preview`), so a refusal
        # names it and the strip's redraw and a second press use the current line.
        drawn = switch_preview(network)
    # The speed pass (2026-11-16, item b): where the press's seconds go, one line. Timing only.
    log.warning("control strip: the switch's preview on %s %s in %.2f s", network,
             "made again (the drawn line not held in this process)" if remade else "held",
             _time.monotonic() - t0)
    if drawn.get("state") == "ok" and not drawn.get("on"):
        # C3909: the problems the line drew are gone at the press: self-healing is turned on
        # as the switch with no line turns it on, never refused because the line moved.
        from modules.heal import policy
        hold("switch", network, None)
        try:
            got = set_heal(network, True, actor=actor, verified=verified, person=True)
        except policy.PolicyRefused as exc:
            raise batch.Refused(str(exc)) from None
        return {"job": None, "ai": {}, "preview": drawn, "words": got["words"]}
    t1 = _time.monotonic()
    got = batch.press(network, shown, actor=actor, verified=verified, ident=ident,
                      switch=True, held=drawn)
    # What it listed is the batch's now: a later press is checked against a line drawn again.
    hold("switch", network, None)
    # The overnight speed pass (2026-11-17, C3907): the press's decision timed, at the level
    # the service keeps.
    log.warning("control strip: the switch's batch decided on %s in %.2f s", network,
                _time.monotonic() - t1)
    return got


def starting_words(fixes: int) -> str:
    """The switch's answer while its work starts (the operator, 2026-11-16: "the switch shows
    On at once and its line shows the work starting ("Starting 7 fixes…")")."""
    return f"Starting {fixes} fix{'' if fixes == 1 else 'es'}…"


def batch_run(network: str, now: float = None):
    """The newest kept batch job of *network* on this server, drawn, or None: while it runs,
    THE stepper; once it ended, one line (``line``, its steps under Details) for `RUN_LINE_S`
    after its end, unless the viewer dismissed it (`seen_runs`, the In progress list's own
    per-person marks, `routes/control_v2.run_seen`); then nothing."""
    job = newest_batch_job(network)
    if not job:
        return None
    now = time.time() if now is None else float(now)
    end = job.get("finished_at")
    if end is not None and job.get("state") != "running":
        if now - float(end) > RUN_LINE_S:
            return None
        from modules import seen_runs
        from routes.operations import viewer_key
        try:
            if seen_runs.is_seen(viewer_key(), job["job"]):
                return None
        except Exception as exc:                      # noqa: BLE001 (drawn: never hidden by a guess)
            log.warning("control strip: whether the run was dismissed is not known: %s", exc)
    return _run_card(job)


def view(network: str, now: float = None, drawn: bool = False, **answer) -> dict:
    """The strip's model for *network*: ``{"network", "anchor", "heal", "ai", "may",
    "why_not", "run", "answer"}``. *answer* is what a press said (``heal_set``, ``starting``,
    ``refused``), drawn in place. *drawn* (C3866, a press's answer): each switch's line as
    this process last drew it (`held`), where it holds one, so the answer waits on no
    preview; the strip's own read (its GET) makes them again."""
    from flask import url_for

    from modules import identity
    from modules.heal import batch, policy

    now = time.time() if now is None else float(now)
    why = batch.may_press(identity.viewer())
    try:
        cur = policy.current(network, now)
    except Exception as exc:                          # noqa: BLE001 (said, never drawn as off)
        cur = {"mode": "unknown", "until": "", "words": f"{type(exc).__name__}: {exc}",
               "state": "unreadable"}
    hours = batch.default_hours(network)
    heal = {"mode": cur.get("mode"), "on": cur.get("mode") == "auto",
            "until": cur.get("until") if cur.get("mode") == "auto" else "",
            "would_until": batch.default_until(network, now), "hours": hours,
            "words": cur.get("words") or "", "known": cur.get("mode") in policy.MODES,
            "gear": url_for("settings_v2.network", list_name=network, tab="heal"),
            "also": "", "hash": "", "also_error": ""}
    # C3823: while it is not On, the open problems turning it on also fixes, its one line and
    # the hash the switch's press is bound to (`switch_preview`); none, no line.
    if heal["known"] and not heal["on"]:
        try:
            sp = (held("switch", network) if drawn else None) or switch_preview(network)
            # Round 2 (2026-11-17): a line with only incidents decided at the switch-on
            # (``also`` with no hash) is drawn too; its press turns self-healing on plainly.
            if sp.get("on") or sp.get("also"):
                heal.update(also=sp.get("also") or "", hash=sp.get("hash") or "")
            if sp.get("error") or sp.get("state") != "ok":
                heal["also_error"] = sp.get("error") or sp.get("state") or ""
        except Exception as exc:                      # noqa: BLE001 (said, never drawn as none)
            heal["also_error"] = f"{type(exc).__name__}: {exc}"
    # Gate 2 (C3769; the operator's minimal design, 2026-11-15): "AI troubleshooting:
    # Automatic", on or off back to Manual, through the one control's route
    # (`troubleshoot.set_level`); the one line before turning it on; its refusal, until the
    # limits are acknowledged, linking the limits card.
    from modules import troubleshoot_control as troubleshoot
    try:
        ai = troubleshoot.strip(network, drawn=drawn)
    except Exception as exc:                          # noqa: BLE001 (said, never drawn as off)
        ai = {"on": False, "known": False, "at": "", "level": "unknown", "words": "",
              "ready": "", "line": None, "error": f"{type(exc).__name__}: {exc}"}
    ai.update(gear=url_for("settings_v2.installation", tab="ai", network=network,
                           _anchor=troubleshoot.CARD_ID))
    return {"network": network, "anchor": ANCHOR, "heal": heal, "ai": ai, "may": not why,
            "why_not": why, "run": batch_run(network), "answer": answer}


def run_view(network: str, **answer) -> dict:
    """The strip's run part alone, for Needs attention (C3789; the operator, 2026-11-15: "The
    control strip: remove it from Needs attention; keep it only on Incidents"): G6's batch card
    is pressed there, so the press's answer and the batch's run on THE stepper are drawn in
    place there, under `ANCHOR`, with no toggle. ``{"network", "anchor", "run", "answer",
    "run_only"}``; a read of this server's job registry only."""
    return {"network": network, "anchor": ANCHOR, "run": batch_run(network), "answer": answer,
            "run_only": True}


def set_heal(network: str, on: bool, *, actor: str, verified: str, person: bool,
             page: str = "Troubleshoot › Incidents", now: float = None) -> dict:
    """The Self-healing toggle: on, Auto for the default duration; off, Dry run. Through the
    policy's own write (`policy.apply_planned`), the person's reason the toggle's own words:
    ``{"ok", "nothing", "words"}``. Raises `policy.PolicyRefused` naming the gate."""
    from modules.heal import batch, policy

    reason = f"the Self-healing toggle on {page}'s control strip, turned {'on' if on else 'off'}"
    if on:
        return batch.turn_on_auto(network, actor=actor, verified=verified, person=person,
                                  reason=reason, now=now)
    cur = policy.current(network, now)
    if cur.get("set") == "dry_run" and cur["mode"] == "dry_run":
        return {"ok": True, "nothing": True, "words": "self-healing is already in Dry run"}
    policy.apply_planned(network, {policy.MODE_KEY: "dry_run"}, actor=actor,
                         actor_verified=verified, person=person, reason=reason, now=now)
    return {"ok": True, "nothing": False,
            "words": "self-healing is in Dry run: it watches and says what it would fix"}
