"""The control strip (C3748; the operator's design, 2026-11-15): one shared component at the top
of Needs attention and Troubleshoot › Incidents, for the page's network.

- **Self-healing**: on is Auto for the network, for its default duration
  (`heal_auto_default_hours`, C3749; 1 hour by default), labelled "Auto until HH:MM"; off is
  Dry run. One press, no dialog, through the policy's own write (`policy.apply_planned`: every
  gate its plan holds, recorded with who and why in the network's settings record, which
  History draws as the person's change). It acts on new problems only: open incidents stay as
  they stand, with G6's Turn on self-healing and fix all the one place a batch is approved.
- **AI troubleshooting** (Gate 2, C3769; the operator's minimal design, 2026-11-15): "AI
  troubleshooting: Automatic", the network's one control's Automatic (`troubleshoot_control`). On
  is one press through the control's own route (`settings_v2.ai_ts_level`, ``answer=strip``):
  with open incidents to start on, one line beside it first ("Also starts on N open incidents,
  about $X"), its digest the press's, and nothing else; all of them start within the caps, one
  past a cap refused and named on its card. Refused until the network's spending limits and
  their estimate are acknowledged in Settings (the refusal links the limits card). Off goes
  back to Manual at once.
- A gear to each full setting (the network's Self-healing tab, Settings › AI).
- **The batch's run**: the newest Turn on self-healing and fix all of the network this server
  holds, drawn on THE stepper while it runs and after (`heal.batch.STEPS`).

Both toggles show the live state, are usable only by a person who may change those settings
(`heal.batch.may_press`: a verified person, `identity.may` ``configure``); anyone else sees the
state read-only, with why. A read of the settings and this server's job registry: no device,
no outside service (CLAUDE.md, "No page load or badge poll waits on Grafana, Loki, NetBox, a
device or a computation").
"""

import logging
import time

log = logging.getLogger(__name__)

#: The strip's element id: the top bar's status chip links here (`#control-strip`).
ANCHOR = "control-strip"


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
    rows = [RS.row(batch.BUTTON, group, rec["steps"], device=False)]
    for d in result.get("devices") or []:
        g = {"healed": "done", "not_started": "not_reached"}.get(d.get("outcome"), "failed")
        rows.append(RS.row(d.get("device") or "?", g, [], detail=d.get("words") or ""))
    return {"job": job["job"], "state": got.get("state") or job.get("state"),
            "outcome": outcome, "words": result.get("words") or got.get("error") or "",
            "stepper": RS.card(rows, label="Turn on self-healing and fix all", key="heal-batch"),
            "started_at": job.get("started_at")}


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


def batch_preview(network: str, rows: list = None) -> dict:
    """G6's batch card on *network* (`heal.batch.preview`), with the incidents for the AI
    handed in (`batch_ai_items`)."""
    from modules.heal import batch

    return batch.preview(network, rows, ai_items=batch_ai_items(network))


def fix_all(network: str, shown: str, *, actor: str, verified: str, ident) -> dict:
    """G6's one press (`heal.batch.press`), with what the heal loop never reads handed in: the
    incidents for the AI as the card listed them and the AI's starts
    (`heal_notice.start_catch_up`). Raises `heal.batch.Refused`, nothing started."""
    from modules import heal_notice
    from modules.heal import batch

    return batch.press(network, shown, actor=actor, verified=verified, ident=ident,
                       ai_items=batch_ai_items(network), start_ai=heal_notice.start_catch_up)


def batch_run(network: str):
    """The newest kept batch job of *network* on this server, drawn, or None."""
    from modules.heal import batch
    from modules.nsot import capture_job

    job = next((j for j in capture_job.card_jobs() if j["kind"] == batch.KIND
                and j["list"] == network), None)
    return _run_card(job) if job else None


def view(network: str, now: float = None, **answer) -> dict:
    """The strip's model for *network*: ``{"network", "anchor", "heal", "ai", "may",
    "why_not", "run", "answer"}``. *answer* is what a press said (``heal_set``, ``refused``),
    drawn in place."""
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
            "gear": url_for("settings_v2.network", list_name=network, tab="heal")}
    # Gate 2 (C3769; the operator's minimal design, 2026-11-15): "AI troubleshooting:
    # Automatic", on or off back to Manual, through the one control's route
    # (`troubleshoot.set_level`); the one line before turning it on; its refusal, until the
    # limits are acknowledged, linking the limits card.
    from modules import troubleshoot_control as troubleshoot
    try:
        ai = troubleshoot.strip(network)
    except Exception as exc:                          # noqa: BLE001 (said, never drawn as off)
        ai = {"on": False, "known": False, "at": "", "level": "unknown", "words": "",
              "ready": "", "line": None, "error": f"{type(exc).__name__}: {exc}"}
    ai.update(gear=url_for("settings_v2.installation", tab="ai", network=network,
                           _anchor=troubleshoot.CARD_ID))
    return {"network": network, "anchor": ANCHOR, "heal": heal, "ai": ai, "may": not why,
            "why_not": why, "run": batch_run(network), "answer": answer}


def set_heal(network: str, on: bool, *, actor: str, verified: str, person: bool,
             page: str = "Needs attention", now: float = None) -> dict:
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
