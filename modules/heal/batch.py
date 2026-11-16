"""G6, the one-button batch (the operator's design, 2026-11-14; ~/Documents/nmas-reports/
lab10-live-demo-plan.md, click 1): guard 6's hold, previewed whole on Needs attention and
resolved by one press.

**The preview** (`preview`, a read): the network's devices whose newest decision is held by
guard 6 (many devices at once), each with the decision it would be were guard 6 resolved (the
hold's ``beyond``, `decide._beyond`: decided as in AUTO, its exact program, masked, and its
hash), and the open incidents with no fix Mercury can run (`fixit.auto.catch_up`'s list, the
batch's own incidents left out), handed in by the caller (`control_strip.batch_ai_items`):
the heal loop's modules never import the fix-it path or the notifier (section 12's rule,
tests/test_heal_analysis_never_read.py), so this module reads neither. Beside them (C3819, the
operator, 2026-11-16), every open incident an Automatic saved script matches, each with its
plan previewed as `saved_plans.fire` previews it (asking no device), handed in the same way
(`control_strip.batch_script_items`); an incident a listed script covers is a fix, so it is
not the AI's. It leads "8 devices have faults. Mercury can fix 7 (5 restores, 2 saved
scripts); the AI starts on s5." with its real counts (`lead_words`), and its hash binds every
device, incident, decision and program hash, every script's key, incident and plan hash, and
every incident the AI would start on.

**The press** (`press`, one person, one click, no dialog), refused before anything starts
unless the person is verified, may change self-healing, and pressed the preview's hash now:
1. the AI started on each open incident with no fix, at once, as the person's press under
   every cap (the caller's *start_ai*, `heal_notice.start_catch_up`'s *press*: the incident's
   cap, the day cap and the calls in flight), in parallel with the clear; inside the request,
   since a person's call is made only there;
2. the rest as one job (`run`, `capture_job.start`, never the request: Cloudflare cuts at
   100 s), each step pushed live (`STEPS`):
   - **auto**: the batch's saved scripts claimed first (`saved_plans.claim_for_batch`, under
     the scripts store's lock across processes, so the re-decide a turn-on starts runs none of
     them), then self-healing turned on in Auto until turned off, through THE policy write
     (`policy.plan`, `apply`: the preview's own fingerprint, a verified person, a recorded
     reason), or left as it is when it is already Auto;
   - **approve**: the batch approved by its hash, recorded in the network's heal decisions
     (a ``batch`` row: who, how verified, when, the hash, each device and program hash);
   - **fix**: every device at once (`fanout.read_each`, bounded as it is; the operator,
     2026-11-16: "a self-healing batch (switch-on, Fix all, retries) runs every device at once:
     each held, preconditions checked, verified and rolled back on its own; no canary device
     first. A failure is reported on its own incident and doesn't stop the others. The canary
     stays for rollouts and template pushes"; CLAUDE.md, "Reads across devices run
     concurrently", its heal-batch clause). Each restore (`_one`): its standing incident
     taken, decided again with guard 6 resolved and the grace dropped for this batch
     (`decide.BATCH_RESOLVES`), refused unless its program hash is the one previewed, then THE
     heal act as its own job (`act.start`: held, the deploy's nine stages, verified, rolled
     back on failure, recorded), waited for. Each saved script through its normal path
     (`_script`, `saved_plans.fire` with the batch's claim, the batch named on the run's reason
     and authority, its plan hash the one approved, guards 1 to 4 asked, guard 6 resolved). A
     device that fails stops no other; its outcome is recorded on its own incident
     (`_on_incident`, the incident's ``batches``) and said in the batch's outcome;
   - **record**: the batch's outcome recorded (a ``batch_done`` row), per device.

The rollouts' and template pushes' canary (`nsot.fleet_change`, `nsot.read_account`: the same
new change to many devices) is theirs, unchanged: a heal batch puts each device back to its own
approved state, so no device's result says anything about another's.

Guards and settings are otherwise unchanged: guard 6 still holds every configuration departure
outside the approved batch (an event problem it never holds, `decide._g6`, C3819), and a later
departure is judged as before.
"""

import hashlib
import json
import logging
import time

log = logging.getLogger(__name__)

KIND = "heal_batch"
ANNOUNCER = "heal-batch"
#: What a batch's job changes, announced at its end (`invalidation.ANNOUNCERS[ANNOUNCER]`).
DONE_KEYS = ("drift", "goldens", "remote", "baselines", "device_state", "rolled_back",
             "settings")
#: The press's control and the words its row leads with.
BUTTON = "Turn on self-healing and fix all"
#: The job's steps, in order, for its card and the manual's How it works page.
STEPS = (("auto", "Turn on self-healing in Auto for the network's default duration"),
         ("approve", "Approve the previewed batch by its hash"),
         ("fix", "Fix every device at once (restores and saved scripts), each held, checked, "
                 "verified and rolled back on its own; a failure stops no other"),
         ("record", "Record the batch's outcome"))
STEP_LABELS = {"auto": "Turn on Auto", "approve": "Approve batch", "fix": "Fix all at once",
               "record": "Record"}
#: How many batch outcomes an incident keeps (``batches``), newest last.
BATCHES_KEPT = 10
#: C3823 (the operator's design, 2026-11-16): "switching Self-healing On IS the approval for
#: what's already open". The control strip's Self-healing switch, drawn with the open problems
#: it also fixes, runs THIS batch (`press` with ``switch=True``): guard 6's restores and the
#: Automatic saved scripts' matches, never the AI (no-fix incidents start from the Automatic AI
#: switch's catch-up), its run named after the switch-on (`switch_name`).
SWITCH = "Self-healing switched on"
#: The switch-on run's page: the strip, on Troubleshoot › Incidents (C3789), where its run is
#: drawn (`control_strip._run_card` tells the switch's run by this path).
SWITCH_PAGE = "/v2/incidents"
#: A batch decision its job has not taken this long after it was decided is refused by the
#: heal runner (`act.run`): the job ended. Every device starts at once, so one `WAIT_S`
#: covers a batch up to `fanout.MAX_WORKERS` devices; two cover one twice that size, a worker
#: freed for the second round, and more.
WAIT_S = 900
UNTAKEN_S = 2 * WAIT_S + 120
#: How long one device's heal job is waited for: a heal's longest declared wait (an alert's
#: symptom bound, 750 s, `act`'s bounds) and its apply. Reasoned from act's bounds, not
#: measured end to end (the demo plan's rehearsal measures the clear).


class Refused(Exception):
    """The press is refused before anything starts, naming what it compared."""


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def hold_words(n: int) -> str:
    """Guard 6's hold, as the batch card says it (the demo plan's words), and that approving it
    drops the grace too (`decide.BATCH_RESOLVES`: guards 6 and 8; the operator's G6 design, "no
    grace once approved"; Gate 2's review: said on the card)."""
    return (f"Held by guard 6: {n} devices changed at once. Approve to fix them all. "
            "Approving fixes them all now, without the usual grace.")


def _names(devices: list) -> str:
    devices = list(dict.fromkeys(d for d in devices if d))
    if len(devices) > 3:
        return f"{len(devices)} devices"
    return " and ".join([", ".join(devices[:-1]), devices[-1]]) if len(devices) > 1 \
        else (devices[0] if devices else "")


def lead_words(n: int, m: int, restores: int = None, scripts: int = 0, ai=()) -> str:
    """The batch card's lead (C3819): "8 devices have faults. Mercury can fix 7 (5 restores,
    2 saved scripts); the AI starts on s5." *m* the fixes (*restores* guard 6's departures,
    *scripts* the incidents an Automatic saved script matches), *ai* the devices the AI
    starts on. *restores* None: the lead as before, counts alone."""
    head = (f"{n} device{'' if n == 1 else 's'} {'has' if n == 1 else 'have'} faults. "
            f"Mercury can fix {m}")
    if restores is None:
        return head + "."
    if scripts:
        head += (f" ({restores} restore{'' if restores == 1 else 's'}, {scripts} saved "
                 f"script{'' if scripts == 1 else 's'})")
    named = _names(list(ai))
    return head + (f"; the AI starts on {named}." if named else ".")


def switch_words(restores: int, scripts: int, verb: str = "Also fixes") -> str:
    """The strip's one line beside the Self-healing switch (C3823): "Also fixes the 7 open
    problems (5 restores, 2 saved scripts)", each part only when it is not zero; *verb* the
    press's answer's ("fixing")."""
    n = int(restores) + int(scripts)
    parts = ([f"{restores} restore{'' if restores == 1 else 's'}"] if restores else []) + \
        ([f"{scripts} saved script{'' if scripts == 1 else 's'}"] if scripts else [])
    return f"{verb} the {n} open problem{'' if n == 1 else 's'} ({', '.join(parts)})"


def switch_name(shown: str, epoch: float) -> str:
    """The switch-on batch's name, on its approval record and each run it starts (C3823):
    "self-healing switched on by <person> at HH:MM UTC"."""
    return (f"self-healing switched on by {shown or 'a person'} at "
            f"{time.strftime('%H:%M', time.gmtime(float(epoch)))} UTC")


def switch_moved(seen: str, now: dict) -> str:
    """The switch's refusal when the open problems it drew moved before the press (C3823),
    naming both hashes."""
    return (f"the open problems moved since the line was drawn (pressed {seen[:12] or 'none'}, "
            f"now {(now.get('hash') or 'none')[:12]}): read the line again; self-healing was "
            "not turned on and nothing was started")


def fix_word(fixable: int) -> str:
    """The count in the batch card's button (board R5, approved 2026-11-15, the operator's change
    4: "Fix both (also turns self-healing on)"): "both" for two, "all N" otherwise ("it" for
    one). The card draws "Fix <this> (also turns self-healing on)", its side effect always
    said (`button_words`). The press itself is `BUTTON`'s, the name its records keep."""
    return "it" if fixable == 1 else "both" if fixable == 2 else f"all {fixable}"


def button_words(fixable: int) -> str:
    """The batch card's button's words whole, as `_heal_batch.html` draws them."""
    return f"Fix {fix_word(fixable)} (also turns self-healing on)"


def status_words(devices: list) -> str:
    """The batch card's status line (board R5): who it waits for and what one press does, in
    the order the job does it (`STEPS`: every device at once, each verified on its own; the
    operator, 2026-11-16)."""
    devices = [d for d in devices if d]
    if not devices:
        return "Held for a person"
    if len(devices) == 1:
        return f"Held for a person: one press fixes {devices[0]} and verifies it"
    return (f"Held for a person: one press fixes {_names(devices)} at once, each verified "
            "on its own")


def batch_hash(items: list, ai: list, scripts: list = ()) -> str:
    """sha256 over each item's device, incident, decision and program hash, each saved
    script's key, incident and plan hash (C3819), and each incident the AI would start on,
    sorted: what the press is bound to. With no script, the body is as before."""
    body = {"fix": sorted([i["device"], i["incident"], i["decision"], i["program_hash"]]
                          for i in items),
            "ai": sorted(a["id"] for a in ai)}
    if scripts:
        body["scripts"] = sorted([s["key"], s["incident"], s["hash"]] for s in scripts)
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def _newest(rows: list) -> dict:
    newest = {}
    for d in rows:
        host = d.get("device") or ""
        if host and float(d.get("epoch") or 0) >= float(newest.get(host, {}).get("epoch") or 0):
            newest[host] = d
    return newest


def _handed(got, what: str) -> tuple:
    """``(items, error)`` from a list the caller handed in: None (not read, said), a list, or
    the caller's ``{"items", "error"}``."""
    if got is None:
        return [], f"{what} were not read for this preview"
    if isinstance(got, dict):
        return list(got.get("items") or []), got.get("error") or ""
    return list(got), ""


def preview(network: str, rows: list = None, *, ai_items: list = None,
            incidents_doc: dict = None, script_items=None, switch: bool = False) -> dict:
    """The batch on *network* now (a read; nothing written, nothing sent): ``{"network",
    "on", "items", "scripts", "others", "ai", "n", "fixable", "fix", "hash", "lead", "hold",
    "state", "error"}``. *on* whether there is a batch at all (a device held by guard 6);
    *items* the fixable devices ``{"device", "incident", "decision", "program", "program_hash",
    "units", "kind", "words"}``; *scripts* the open incidents an Automatic saved script matches
    (C3819), each with its plan previewed as `saved_plans.fire` previews it ``{"key", "name",
    "incident", "device", "hash", "program", "title", "problem", "values"}``, an incident a
    restore already fixes left out; *others* the held devices the press cannot fix, each with
    why; *ai* the open incidents with no fix ``{"id", "device", "title", "why"}``, an incident a
    listed script covers left out (a script match is a fix). *rows* the decisions already
    read, *ai_items* `fixit.auto.catch_up`'s items, *script_items* the script matches
    (`control_strip.batch_script_items`) and *incidents_doc* the incidents store's read, where a
    caller has them.

    *switch* (C3823): the Self-healing switch's preview. The saved scripts' matches alone make
    a batch (no guard 6 hold needed), the AI part is always empty (the switch never starts the
    AI; *ai_items* is not read), and *on* only when there is something to fix, with ``also``
    its line (`switch_words`); its hash binds the restores and the scripts alone."""
    from modules.heal import decisions, incidents

    out = {"network": network, "on": False, "items": [], "scripts": [], "others": [], "ai": [],
           "n": 0, "fixable": 0, "fix": "", "hash": "", "lead": "", "hold": "", "state": "ok",
           "error": ""}
    try:
        rows = decisions.decisions(network) if rows is None else rows
    except Exception as exc:                          # noqa: BLE001 (said, never empty)
        return dict(out, state="unreadable", error=str(exc))
    doc = incidents.read(network) if incidents_doc is None else incidents_doc
    standing = {i.get("id"): i for i in doc.get("incidents") or []
                if i.get("state") == "standing"}
    held = 0
    auto_kinds = None
    for host, d in sorted(_newest(rows).items()):
        g = d.get("guard") or {}
        inc = standing.get(d.get("incident"))
        if inc is None or (inc.get("standing") or {}).get("decision") != d.get("id"):
            continue
        if d.get("outcome") == "would_heal" and d.get("program_hash"):
            # C3844 (the operator, 2026-11-16): a standing dry-run "would heal" is a fix
            # Mercury can run once self-healing is On, its program and hash the decision's own
            # (as guard 6's ``beyond`` carries them). Only one whose every kind self-healing
            # fixes in Auto (`_dry_run_fixable`): another stays a would-heal in Auto too.
            if auto_kinds is None:
                auto_kinds = _auto_kinds(network)
            if _dry_run_fixable(d, auto_kinds):
                out["items"].append({"device": host, "incident": d["incident"],
                                     "decision": d["id"], "program": list(d.get("program")
                                                                          or []),
                                     "program_hash": d["program_hash"],
                                     "units": len(d.get("units") or []),
                                     "kind": d.get("kind") or "",
                                     "words": d.get("outcome_words") or d.get("words") or "",
                                     "from": "would_heal"})
            continue
        if d.get("outcome") != "held" or g.get("guard") != 6:
            continue
        held += 1
        b = d.get("beyond") or {}
        if b.get("outcome") == "heal" and b.get("program_hash"):
            out["items"].append({"device": host, "incident": d["incident"],
                                 "decision": d["id"], "program": list(b.get("program") or []),
                                 "program_hash": b["program_hash"],
                                 "units": int(b.get("units") or 0), "kind": b.get("kind") or "",
                                 "words": b.get("words") or "", "from": "guard6"})
        else:
            out["others"].append({"device": host, "incident": d["incident"],
                                  "why": b.get("words") or "its fix could not be previewed"})
    if not out["items"] and not out["others"] and not switch:
        return out
    base = dict(out)
    # Not handed in: never read here (the module's docstring). Said, so a card drawn without
    # a list never reads as "none". The switch's batch has no AI part (C3823).
    ai_items, ai_err = _handed([] if switch else ai_items, "the open incidents with no fix")
    script_items, script_err = _handed(script_items, "the saved scripts' matches")
    out["error"] = "; ".join(e for e in (ai_err, script_err) if e)
    restored = {i["incident"] for i in out["items"]}
    out["scripts"] = [{"key": s["key"], "name": s.get("name") or s["key"],
                       "incident": s["incident"], "device": s.get("device") or "",
                       "hash": s["hash"], "program": list(s.get("program") or []),
                       "title": s.get("title") or "", "problem": dict(s.get("problem") or {}),
                       "values": dict(s.get("values") or {})}
                      for s in script_items if s.get("incident") not in restored]
    scripted = {s["incident"] for s in out["scripts"]}
    # A held device a script fixes is the script's, guard 6 resolved for it by the press.
    out["others"] = [o for o in out["others"] if o["incident"] not in scripted]
    mine = restored | {o["incident"] for o in out["others"]} | scripted
    out["ai"] = [{"id": a["id"], "device": a["device"], "title": a.get("title") or "",
                  "why": a.get("why") or ""} for a in ai_items if a["id"] not in mine]
    devices = ({i["device"] for i in out["items"]} | {o["device"] for o in out["others"]}
               | {s["device"] for s in out["scripts"]} | {a["device"] for a in out["ai"]})
    fixable = len(out["items"]) + len(out["scripts"])
    if switch:
        # C3823: nothing to fix, no line, and the switch turns on as before; a list that could
        # not be read is said (``error``), never drawn as none.
        if not fixable:
            return dict(base, error=out["error"])
        out["also"] = switch_words(len(out["items"]), len(out["scripts"]))
    out.update(on=True, n=len(devices), fixable=fixable, fix=fix_word(fixable),
               hash=batch_hash(out["items"], out["ai"], out["scripts"]),
               lead=lead_words(len(devices), fixable, len(out["items"]),
                               len(out["scripts"]), [a["device"] for a in out["ai"]]),
               hold=(hold_words(held) if held else dry_run_words(len(out["items"]))))
    return out


def dry_run_words(n: int) -> str:
    """The card's status where nothing is held by guard 6 and the fixes are dry-run "would
    heal" decisions (C3844)."""
    return (f"Decided in dry run: Mercury would put back {n} device"
            f"{'' if n == 1 else 's'}. Approve to fix {'it' if n == 1 else 'them'} now.")


def _auto_kinds(network: str) -> set:
    """The kinds self-healing fixes in Auto on *network* (`policy.current`'s ``kinds_auto``),
    or None when the policy cannot be read (then no dry-run decision is listed)."""
    from modules.heal import policy

    try:
        return set(policy.current(network).get("kinds_auto") or [])
    except Exception as exc:                          # noqa: BLE001 (none listed, logged)
        log.warning("heal batch: %s's Auto kinds could not be read: %s", network, exc)
        return None


def _dry_run_fixable(d: dict, auto_kinds) -> bool:
    """Whether the would-heal decision *d* heals once self-healing is On (C3844): decided while
    self-healing was not in Auto, every unit's kind one Auto fixes (`decide._outcome`'s rule;
    a security kind is always proposed, never healed), with its program and hash. Decided in
    Auto, it is a would-heal because a kind is not fixed in Auto: switching on changes nothing
    for it."""
    from modules.heal.policy import SECURITY_KINDS

    if not auto_kinds or d.get("mode") == "auto" or not d.get("program_hash"):
        return False
    kinds = {u.get("kind") for u in d.get("units") or [] if isinstance(u, dict)} or \
        {d.get("kind")}
    return bool(kinds) and all(k and k in auto_kinds and k not in SECURITY_KINDS
                               for k in kinds)


def moved(seen: str, now: dict) -> str:
    return (f"the batch moved since it was drawn (pressed {seen[:12] or 'none'}, now "
            f"{(now.get('hash') or 'none')[:12]}): read the card again; nothing was started")


def default_hours(network: str) -> int:
    """The network's default duration of a one-press Auto, in hours (`heal_auto_default_hours`,
    C3749; 1 hour by default, or when the setting holds no whole number): the one read, the
    press's and the control strip's."""
    from modules.list_settings import value

    try:
        return int(value(network, "heal_auto_default_hours", 1) or 1)
    except (TypeError, ValueError):
        return 1


def default_until(network: str, now: float) -> str:
    """AUTO's expiry the press and the control strip's toggle use: now plus the network's
    default duration (`default_hours`)."""
    return _iso(now + default_hours(network) * 3600)


def turn_on_auto(network: str, *, actor: str, verified: str, person: bool, reason: str,
                 now: float = None, retry_skip=()) -> dict:
    """Self-healing in Auto for *network* for its default duration, through THE policy write
    (planned, then applied with that plan's own fingerprint as a verified person with
    *reason*): ``{"ok", "nothing", "until", "words"}``. Already in Auto: nothing written, said.
    A refused plan raises `policy.PolicyRefused`, naming the gate. *retry_skip* (C3823): the
    incidents a batch is fixing, left out of the retry this turn-on starts (`heal.retry.run`'s
    *skip*), so the batch's own restores and scripts are never tried twice."""
    from modules.heal import policy

    now = time.time() if now is None else float(now)
    cur = policy.current(network, now)
    if cur["mode"] == "auto":
        return {"ok": True, "nothing": True, "until": cur.get("until") or "",
                "words": "self-healing is already in Auto"
                + (f" until {cur.get('until')}" if cur.get("until") else "")}
    # Until turned off (N8 as changed by the operator, 2026-11-16): the strip's On has no
    # expiry; Settings keeps the 1 h, 8 h and 7 d choices.
    proposed = {policy.MODE_KEY: "auto", policy.UNTIL_KEY: ""}
    got = policy.apply_planned(network, proposed, actor=actor, actor_verified=verified,
                               person=person, reason=reason, now=now, retry_skip=retry_skip)
    return {"ok": True, "nothing": False, "until": got["until"],
            "words": "self-healing turned on in Auto, until someone turns it off"}


def may_press(ident) -> str:
    """"" when *ident* may press, else why not: a verified person allowed to change
    self-healing settings (`identity.may`, ``configure``, the policy routes' gate)."""
    from modules import identity

    if ident is None or not getattr(ident, "is_identified", False):
        return "the press is a verified person's, and this request's identity is not verified"
    if ident.kind != "person":
        return (f"the press is a verified person's, and this request is a {ident.kind} "
                f"({ident.actor}), not a person")
    ok, why = identity.may(ident, "configure")
    return "" if ok else f"you may not change self-healing settings: {why}"


class TurnedOn(Refused):
    """C3866: the switch's press turned self-healing on in Auto, and its batch could not be
    approved after that (its record not written): nothing was sent, and the words say both."""


def press(network: str, shown: str, *, actor: str, verified: str, ident, ai_items=None,
          start_ai=None, starter=None, ai_starter=None, script_items=None,
          switch: bool = False, held: dict = None) -> dict:
    """The one press (the module's steps): ``{"job", "ai", "preview"}``, or `Refused` naming
    what it compared, with nothing started. The caller hands in what this module never reads
    (the module's docstring): *ai_items*, the open incidents with no fix as the card listed
    them (`control_strip.batch_ai_items`), *script_items*, the incidents an Automatic saved
    script matches with their previewed plans (`control_strip.batch_script_items`, C3819), and
    *start_ai* ``(network, ids, **kw)``, the AI's starts (`heal_notice.start_catch_up`); a
    batch with incidents for the AI and no *start_ai* is refused, nothing started. The shown
    hash binds the scripts too (`batch_hash`). *starter* and *ai_starter* replace the job and
    the AI's job (tests).

    *switch* (C3823): the Self-healing switch's press, bound to the switch's preview
    (`preview` with *switch*: restores and saved scripts, no AI, *ai_items* and *start_ai*
    never used); refused, with self-healing not turned on, when the open problems moved since
    the line was drawn (`switch_moved`); its job, its approval and each run named after the
    switch-on (`switch_name`).

    *held* (C3866; the operator, 2026-11-16: "Every switch flips instantly; the work it starts
    happens after, in the background"): the switch's preview as the strip drew it
    (`control_strip.switch_on`), or one it made just now: compared with *shown* as a preview
    made here would be, and, pressed at its hash, the batch approved with no second preview.
    The switch's
    decision (the scripts claimed, Auto turned on, the batch approved and recorded,
    `begin_switch`) is made inside the press's request, so the strip answers with the switch
    On; the fixes are the job. Each item re-checks its own hash at apply (`_one`: the act's
    program recomputed from its own read; `_script`: the runner's plan hash)."""
    from urllib.parse import quote

    from modules.nsot import capture_job

    why = may_press(ident)
    if why:
        raise Refused(why)
    if switch and held is not None:
        # The caller's preview (the drawn one, or one made just now): compared below.
        p = held
    else:
        p = preview(network, ai_items=None if switch else ai_items, script_items=script_items,
                    switch=switch)
    if p["state"] != "ok":
        raise Refused(f"the batch cannot be read ({p['error']}); nothing was started")
    if not p["on"]:
        if switch:
            raise Refused(switch_moved(shown or "", p))
        raise Refused("no batch is held by guard 6 now; nothing was started")
    if (shown or "") != p["hash"]:
        raise Refused(switch_moved(shown or "", p) if switch else moved(shown or "", p))
    # Gate 2's review: Auto's turn-on is judged before anything starts or spends. A network
    # not already in Auto is planned now (`policy.plan`, every gate the job's `turn_on_auto`
    # will hold); one that is not confirmable refuses the press, naming the gates, with no AI
    # started and no job.
    from modules.heal import policy
    now = time.time()
    if policy.current(network, now).get("mode") != "auto":
        planned = policy.plan(network, {policy.MODE_KEY: "auto", policy.UNTIL_KEY: ""}, now)
        if not planned["confirmable"]:
            failed = [g["name"] for g in planned["gates"] if g["state"] == "fail"]
            raise Refused("self-healing cannot be turned on in Auto for this network ("
                          + "; ".join(failed) + "); nothing was started")
    ai = {}
    if p["ai"] and start_ai is None:
        raise Refused(f"{len(p['ai'])} incident(s) with no fix are for the AI, and no way to "
                      "start it was handed in; nothing was started")
    if p["ai"]:
        ai = start_ai(
            network, [a["id"] for a in p["ai"]], actor=actor, verified=verified,
            press=f"started by {BUTTON}, a person's press", press_label=BUTTON,
            starter=ai_starter)
    from modules import identity
    named = switch_name(identity.display_name(actor), now) if switch else ""
    label = (f"{SWITCH}: {p['fixable']} open problem(s) on {network}" if switch
             else f"{BUTTON}: {p['fixable']} device(s) on {network}")
    # C3866: the switch's decision made now, inside its request; refused, nothing sent.
    pre = (begin_switch(network, p, actor=actor, verified=verified, person=True, now=now,
                        named=named) if switch else None)
    work = (lambda _job: {"ok": True, "result": run(network, p, actor=actor,
                                                    verified=verified, person=True,
                                                    named=named, pre=pre)})
    job = (starter or capture_job.start)(
        network, label, actor, work, kind=KIND, announce_keys=DONE_KEYS, announcer=ANNOUNCER,
        page=(f"{SWITCH_PAGE}?list={quote(network)}#control-strip" if switch
              else "/v2/?batch={job}#control-strip"))
    log.info("heal batch: %s pressed %s on %s (%d to fix, %d by saved scripts, %d for the AI)",
             identity.display_name(actor), p["hash"][:12], network, p["fixable"],
             len(p["scripts"]), len(p["ai"]))
    return {"job": job, "ai": ai, "preview": p}


def _record_row(network: str, row: dict) -> dict:
    from modules.heal import decisions

    return decisions._append(network, row)


def begin_switch(network: str, p: dict, *, actor: str, verified: str, person: bool,
                 now: float = None, named: str = "") -> dict:
    """The Self-healing switch's decision, made inside its press's request (C3866; the
    operator, 2026-11-16: "the switch shows On at once and its line shows the work starting"):
    the batch's saved scripts claimed, its restores claimed on their incidents, self-healing
    turned on in Auto, and the batch approved by its hash and recorded (`_approve`, the job's
    steps ``auto`` and ``approve``, as `run` makes them for the card's press). Local writes
    only: no device, no outside service. ``{"steps", "batch", "devices", "scripts", "claims",
    "approval"}``, handed to the job (`run`'s *pre*), which fixes them. Raises `Refused`
    (nothing turned on, nothing sent, the claims let go) or `TurnedOn` (Auto on, the approval
    not recorded, nothing sent)."""
    from modules.heal import act

    now = time.time() if now is None else float(now)
    steps = []
    # Outside a job, `live_steps` records into *steps* alone; the job attaches them as its own.
    step, begin = act.live_steps(steps, STEPS, "", STEP_LABELS)
    out = {"batch": "", "devices": []}
    try:
        got = _approve(network, p, actor=actor, verified=verified, person=person, now=now,
                       named=named, step=step, begin=begin, out=out)
    except Exception as exc:                          # noqa: BLE001 (C3866: readable, never a 500)
        # `_approve` lets its claims go on every refusal it knows; this is one it does not.
        log.exception("heal batch: %s's switch-on could not be decided", network)
        raise Refused(f"the switch-on could not be decided ({type(exc).__name__}: {exc}); "
                      "nothing was sent") from None
    if got.get("refused"):
        if got.get("auto_on"):
            raise TurnedOn(f"self-healing turned on in Auto, and {got['refused']}")
        raise Refused(got["refused"])
    return dict(got, steps=steps, batch=out["batch"], devices=list(out["devices"]))


def run(network: str, p: dict, *, actor: str, verified: str, person: bool,
        sources=None, act_start=None, wait=None, now=None, named: str = "",
        pre: dict = None) -> dict:
    """The batch's job (the module's steps 2): ``{"batch", "steps", "devices", "outcome",
    "words"}``, *devices* ``[{"device", "outcome", "words"}]``. *act_start* and *wait* replace
    a device's heal job and its wait (tests). *named* (C3823): the switch-on's name
    (`switch_name`), on the turn-on's reason, the approval record and each run; "" for the
    card's press, named `BUTTON` as before. *pre* (C3866): the switch's decision, made in its
    request (`begin_switch`): its steps ``auto`` and ``approve`` already done, so the job goes
    straight to the fixes."""
    from modules.fanout import Failed, read_each
    from modules.heal import act

    now = time.time() if now is None else float(now)
    steps = list((pre or {}).get("steps") or [])
    step, begin = act.live_steps(steps, STEPS, "", STEP_LABELS)
    out = {"batch": (pre or {}).get("batch") or "", "steps": steps,
           "devices": list((pre or {}).get("devices") or []), "outcome": "", "words": ""}

    def finish(outcome, words):
        out.update(outcome=outcome, words=words)
        step("record", "ok" if outcome == "fixed" else "failed", words)
        try:
            _record_row(network, {"row": "batch_done", "batch": out["batch"],
                                  "outcome": outcome, "words": words, "at": _iso(time.time()),
                                  "devices": out["devices"]})
        except Exception as exc:                      # noqa: BLE001 (said on the card)
            step("record", "failed", f"the batch's outcome was not recorded: {exc}")
        return out

    got = pre if pre is not None else _approve(
        network, p, actor=actor, verified=verified, person=person, now=now, named=named,
        step=step, begin=begin, out=out)
    if got.get("refused"):
        return finish("refused", got["refused"])
    approval, scripts, claims = got["approval"], got["scripts"], got["claims"]
    # Every device at once, each on its own (the operator, 2026-11-16; CLAUDE.md, the
    # heal-batch clause): each restore and each saved script through its own path, held,
    # checked, verified and rolled back by that path; a failure stops no other.
    work = [("heal", i) for i in p["items"]] + [("script", s) for s in scripts]
    if not work:
        return finish("fixed", "nothing for Mercury to fix" + (
            "" if named else "; the AI was started on the rest"))

    def do(w):
        kind, i = w
        if kind == "heal":
            return _one(network, i, approval, act_start=act_start, wait=wait, sources=sources)
        return _script(network, i, approval, claims[(i["key"], i["incident"])])

    begin("fix", f"fixing {len(work)} at once")
    got = read_each(do, work, name="heal-batch")
    for w, res in zip(work, got):
        if isinstance(res, Failed):
            # A script's fire that raised keeps its claim (fails closed: never run twice).
            res = {"device": w[1]["device"], "outcome": "failed", "words": str(res),
                   **({"script": w[1]["key"]} if w[0] == "script" else {})}
        out["devices"].append(res)
        _on_incident(network, w[1]["incident"], approval, res)
    # A script another path had in flight (``already``) is not this batch's verified fix.
    bad = [d for d in out["devices"] if d["outcome"] != "healed"]
    n = len(out["devices"])
    if bad:
        step("fix", "failed", "; ".join(f"{d['device']}: {d['words']}" for d in bad[:4])
             + (f"; and {len(bad) - 4} more" if len(bad) > 4 else ""))
        return finish("failed" if len(bad) == n else "partial",
                      (f"{n - len(bad)} of {n} fixed and verified; did not: "
                       + "; ".join(f"{d['device']} ({d['words']})" for d in bad[:4])
                       + (f"; and {len(bad) - 4} more, each on its incident"
                          if len(bad) > 4 else "")))
    step("fix", "ok", f"{n} fixed and verified, each on its own")
    return finish("fixed", f"all {n} fixed and verified")


def _approve(network: str, p: dict, *, actor: str, verified: str, person: bool, now: float,
             named: str, step, begin, out: dict) -> dict:
    """The batch's steps ``auto`` and ``approve`` (the module's steps 2), recorded through
    *step* and *begin*, *out*'s ``devices`` and ``batch`` filled: ``{"approval", "scripts",
    "claims"}``, or ``{"refused", "auto_on"}`` with nothing sent (*auto_on*: Auto was turned
    on before the refusal). One home for the switch's request (`begin_switch`) and the card's
    job (`run`)."""
    from modules import identity
    from modules.heal import policy

    shown = identity.display_name(actor)
    begin("auto", "turning on self-healing in Auto")
    # C3819: the batch's saved scripts are claimed before Auto is turned on, under the scripts
    # store's lock (`saved_plans.claim_for_batch`), so the retry that turn-on starts
    # (`policy.apply`'s `retry.run_soon`), the heal decision's `fire_matching` and any other
    # worker find the batch's ``firing`` row and run nothing: the batch runs them, named. One
    # another path already holds is said, never run twice.
    from modules.nsot import saved_plans
    scripts, claims = [], {}
    for s in p.get("scripts") or []:
        try:
            row, before = saved_plans.claim_for_batch(s["key"], s["incident"])
        except saved_plans.Refused as exc:
            out["devices"].append({"device": s["device"], "outcome": "refused",
                                   "script": s["key"], "words": f"not run: {exc}"})
            continue
        except Exception as exc:                      # noqa: BLE001 (C3866: said, not run)
            log.error("heal batch: saved script %s on %s was not claimed: %s", s["key"],
                      s["incident"], exc)
            out["devices"].append({"device": s["device"], "outcome": "refused",
                                   "script": s["key"], "words": (
                                       f"not run: its claim could not be written "
                                       f"({type(exc).__name__}: {exc})")})
            continue
        if before is not None:
            # In flight on another path (``already``), or it ran there: verified or not.
            outcome = ("already" if before.get("state") == "firing" else
                       "healed" if before.get("ok") else "failed")
            out["devices"].append({"device": s["device"], "script": s["key"],
                                   "outcome": outcome,
                                   "words": (f"saved script {s['name']}: already fired by "
                                             f"another path ({before.get('words') or ''})")})
            continue
        claims[(s["key"], s["incident"])] = row
        scripts.append(s)

    def release(items, words):
        for s in items:
            row = claims.get((s["key"], s["incident"]))
            if row:
                try:
                    saved_plans.release(s["key"], row["id"], words)
                except Exception as exc:              # noqa: BLE001 (logged; it fails closed)
                    log.error("heal batch: saved script %s's claim on %s was not let go: %s",
                              s["key"], s["incident"], exc)
    # C3823: the retry this turn-on starts (`policy.apply`'s `retry.run_soon`) leaves out every
    # incident this batch fixes: its restores (a guard-6 hold the retry would otherwise judge,
    # and send back for a fresh decision once guard 6 no longer holds, taking it from under
    # `_one`) and its claimed scripts (their ``firing`` rows already keep it off them).
    skip = tuple({i["incident"] for i in p["items"]} | {s["incident"] for s in scripts})

    def let_go(name: str, words: str, exc) -> dict:
        """Any error once the claims are taken (C3866): every claim let go (each guarded),
        whether Auto is on read live, and said; nothing was sent."""
        if not isinstance(exc, (policy.PolicyRefused, policy.NotAPerson)):
            log.error("heal batch: %s's %s failed: %s: %s", network, name,
                      type(exc).__name__, exc)
        why = (str(exc) if isinstance(exc, (policy.PolicyRefused, policy.NotAPerson))
               else f"{type(exc).__name__}: {exc}")
        release(scripts, f"not run: {words}")
        _claim_restores(network, p["items"], now, "", release=True)   # logs its own failure
        try:
            on = policy.current(network).get("mode") == "auto"
        except Exception:                             # noqa: BLE001 (not known: said as not on)
            on = False
        step(name, "refused", f"{words}: {why}. Nothing was sent")
        return {"refused": (f"the batch's approval was not made ({why}); nothing was sent"
                            if on else
                            f"self-healing was not turned on ({why}); nothing was sent"),
                "auto_on": on}

    # C3844: the batch's restores are claimed on their incidents before Auto is turned on,
    # under the incidents store's lock (`_claim_restores`), so the retry pass in any process
    # (its "in Auto now" catch-up on the detect pass, `retry.now_auto`, as well as this
    # turn-on's) leaves them to this batch: never sent back for a fresh decision from under
    # `_one`.
    try:
        _claim_restores(network, p["items"], now, named or BUTTON)
        reason = (f"the Self-healing switch on Troubleshoot › Incidents' control strip, turned "
                  f"on ({named}), approving the {p['fixable']} open problem(s) it listed by "
                  f"their hash {p['hash'][:12]}" if named
                  else f"{BUTTON}, pressed on Needs attention")
    except Exception as exc:                          # noqa: BLE001 (C3866: refused, readable)
        return let_go("auto", "self-healing was not turned on", exc)
    try:
        got = turn_on_auto(network, actor=actor, verified=verified, person=person,
                           reason=reason, now=now, retry_skip=skip)
    except Exception as exc:                          # noqa: BLE001 (C3866: refused, readable)
        # A policy refusal names its gate; anything else (a store that cannot be read or
        # written) is said with its type, never a bare error.
        return let_go("auto", "self-healing was not turned on", exc)
    try:
        step("auto", "ok", got["words"])
        bid = "hb-" + p["hash"][:12] + "-" + hex(int(now))[2:]
        approval = {"id": bid, "by": actor, "by_shown": shown, "hash": p["hash"],
                    "verified": verified, **({"named": named} if named else {})}
        _record_row(network, {"row": "batch", "id": bid, "by": actor, "actor_verified": verified,
                              "hash": p["hash"], "at": _iso(now), "epoch": now,
                              **({"named": named, "source": "switch"} if named else {}),
                              "items": [{k: i[k] for k in ("device", "incident", "decision",
                                                           "program_hash")}
                                        for i in p["items"]],
                              "scripts": [{k: s[k] for k in ("key", "incident", "device",
                                                             "hash")}
                                          for s in p.get("scripts") or []],
                              "ai": [a["id"] for a in p["ai"]]})
        out["batch"] = bid
        step("approve", "ok", ((f"{named[0].upper()}{named[1:]}: " if named else
                                f"approved by {shown}: ")
                               + f"{len(p['items'])} device(s), each program as "
                               "previewed" + (f", and {len(scripts)} saved script(s), each "
                                              "plan as previewed" if scripts else "")))
    except Exception as exc:                          # noqa: BLE001 (nothing sent)
        out["batch"] = ""
        return let_go("approve", "the approval could not be recorded", exc)
    return {"approval": approval, "scripts": scripts, "claims": claims}


def claimed_by_batch(inc: dict, now: float) -> bool:
    """Whether a batch claimed *inc*'s restore within `UNTAKEN_S` of *now* (`_claim_restores`):
    the retry pass leaves it to that batch."""
    c = (inc or {}).get("batch_claim") or {}
    return bool(c) and now - float(c.get("epoch") or 0) < UNTAKEN_S


def _claim_restores(network: str, items: list, now: float, by: str, *,
                    release: bool = False) -> None:
    """Each restore's incident marked as this batch's (``batch_claim``), under the incidents
    store's lock, when it still stands on the decision previewed; *release* clears the marks
    (the batch refused before it ran). A store that cannot be written is logged: the switch-on
    retry's *skip* still leaves them out in this process."""
    from modules.heal import incidents

    want = {i["incident"]: i["decision"] for i in items or []}
    if not want:
        return

    def change(doc):
        for inc in doc["incidents"]:
            if inc.get("id") not in want:
                continue
            if release:
                inc.pop("batch_claim", None)
            elif (inc.get("state") == "standing"
                  and (inc.get("standing") or {}).get("decision") == want[inc["id"]]):
                inc["batch_claim"] = {"at": _iso(now), "epoch": now, "by": by}
    try:
        incidents._mutate(network, change)
    except Exception as exc:                          # noqa: BLE001 (logged; skip still holds)
        log.error("heal batch: %s's restores were not claimed on their incidents: %s",
                  network, exc)


def _on_incident(network: str, incident_id: str, approval: dict, res: dict) -> None:
    """One device's outcome in the batch recorded on its own incident (the operator,
    2026-11-16: "a failure is reported on its own incident"): ``batches`` on the incident's
    record, newest last (`BATCHES_KEPT`), under the incidents store's lock. A closed incident
    (a verified fix closes it) keeps it too. A store that cannot be written is logged: the
    batch's ``batch_done`` row still holds every device's outcome."""
    from modules.heal import incidents

    entry = {"batch": approval.get("id") or "", "named": approval.get("named") or BUTTON,
             "at": _iso(time.time()), "outcome": res.get("outcome") or "",
             "words": str(res.get("words") or "")[:300],
             **{k: res[k] for k in ("decision", "job", "script", "run") if res.get(k)}}

    def change(doc):
        inc = incidents._find(doc, incident_id)
        inc["batches"] = (list(inc.get("batches") or []) + [entry])[-BATCHES_KEPT:]
        inc.pop("batch_claim", None)                  # the batch is done with it
        return inc
    try:
        incidents._mutate(network, change)
    except Exception as exc:                          # noqa: BLE001 (logged; batch_done holds it)
        log.error("heal batch: %s's outcome on %s was not recorded on its incident: %s",
                  incident_id, network, exc)


def _script(network: str, item: dict, approval: dict, row: dict) -> dict:
    """One saved script of the batch (C3819), through its normal path (`saved_plans.fire`,
    the batch's claimed *row*, the batch named, its plan hash the one approved; the heal
    guards 1 to 4 asked for its device, `decide.script_hold`, guard 6 resolved by the
    approval; the runner holds the device, sends, verifies, rolls back on failure and
    records; a verified run closes its incident Fixed): ``{"device", "outcome", "script",
    "run", "words"}``, *outcome* ``healed`` when it ran and verified. Its incident is read
    as it stands when its turn comes, never as the batch began."""
    from modules.heal import incidents
    from modules.nsot import saved_plans

    device, name = item["device"], item.get("name") or item["key"]
    rec = next((r for r in incidents.read(network).get("incidents") or []
                if isinstance(r, dict) and r.get("id") == item["incident"]), None)
    if rec is None or rec.get("state") not in incidents.OPEN_STATES:
        words = "its incident is no longer open; nothing was sent"
        saved_plans.release(item["key"], row["id"], f"not run: {words}")
        return {"device": device, "outcome": "refused", "script": item["key"],
                "words": f"saved script {name}: {words}"}
    try:
        got = saved_plans.fire(network, item["key"], item.get("problem") or {},
                               item["incident"], heal_mode="auto", record=rec, claimed=row,
                               batch=approval, expect_hash=item["hash"])
    except Exception as exc:                          # noqa: BLE001 (said; its claim is kept)
        # Its claim stays standing (fails closed): what it sent, if anything, is never run
        # twice by another path; its track row and the runner's record say what happened.
        log.error("heal batch: saved script %s on %s failed: %s", item["key"],
                  item["incident"], exc)
        return {"device": device, "outcome": "failed", "script": item["key"], "run": "",
                "words": f"saved script {name}: {type(exc).__name__}: {exc}"}
    outcome = "healed" if got.get("ok") else "failed" if got.get("sent") else "refused"
    return {"device": device, "outcome": outcome, "script": item["key"],
            "run": got.get("run") or "", "words": f"saved script {name}: {got.get('words')}"}


def _wait(job: str, bound: float) -> tuple:
    """``(ended, job)``: a device's heal job waited for, within *bound*, and its record."""
    from modules.nsot import capture_job

    done = capture_job.wait(job, bound)
    return done, capture_job.get(job)


def _as_previewed(network: str, inc: dict, item: dict, approval: dict, now: float):
    """The heal decision for one restore of the batch, made from the decision the batch
    previewed and was approved by (C3865): guard 6's hold's ``beyond`` (`decide._beyond`,
    decided as in AUTO, with its units masked and its verify) or the dry-run would-heal itself
    (C3844), its program and hash the ones previewed, judged again by THE tier rule as
    self-healing is now (`decide._outcome`: Auto, every unit's kind one Auto fixes, none a
    security kind), and guards 4 (the golden still the approved state, `decide.guard_holds`),
    11 (a fight, where the network stops on one), 12 (the program's
    size, on its masked units, each non-stanza unit counted its own section: never looser than
    the decision's count) and 14 (a heal of the device rolled back since the newest halt)
    judged again now, from the stores, as `decide._decide_one` judges them; the batch named as
    `decide._decide_one` names it, its words `decide.said_of`'s. The policy recorded is the
    one in force now (Auto, just turned on by the batch), so the act's stops compare with it.
    No device read: the act reads the device at apply and refuses unless the program it
    recomputes from that read is this hash (what is confirmed is what is sent), with its own
    stops judged again there (the kill switch, Auto, the policy, a halt, planned work, the
    kinds). None when it cannot be made so (a hold decided before its units were kept, a
    program not the one previewed, an outcome that is not a heal now, any of guards 4, 11, 12 or
    14 hit, a store that cannot be read): `_one` then decides it again in full, reading the
    device, as before."""
    from modules import fault_drills
    from modules.heal import decide, decisions, findings, guards, policy

    try:
        d = decisions.find(network, item["decision"])
        mode = policy.current(network, now)
        rows = decisions.decisions(network)
        last_halt = decisions.last_halt_epoch(network)
    except Exception as exc:                          # noqa: BLE001 (decided again, logged)
        log.warning("heal batch: %s's previewed decision could not be read (%s); it is "
                    "decided again", item.get("incident"), exc)
        return None
    if d.get("incident") != item["incident"] or d.get("device") != item["device"]:
        return None
    if item.get("from") == "guard6":
        src = d.get("beyond") or {}
        units = src.get("units_masked")
        if src.get("outcome") != "heal":
            return None
    elif item.get("from") == "would_heal" and d.get("outcome") == "would_heal":
        src, units = d, d.get("units")
    else:
        return None
    if (not units or not src.get("program") or src.get("program_hash") != item["program_hash"]
            or mode.get("mode") != "auto"):
        return None
    device = d["device"]
    # Guards 11, 12 and 14 now, as `decide._decide_one` asks them (no device read): any hit is
    # the full re-decide's to say.
    v = guards.value
    sized = [{"op": u.get("op"), "stanza": bool(u.get("stanza")),
              "chain": [] if u.get("stanza") else [u.get("section") or ""],
              "lines": [u.get("section") or ""]} for u in units]
    try:
        key = findings.problem_key(inc)
        fight = (findings.fight_on(network, device, key[1] if key else "", mode=mode, now=now)
                 if v(mode, "heal_fight_stop") else {})
        # Guard 4 first: the golden still the approved state (`decide.guard_holds`, its one
        # home: the golden and intent read, no device).
        hit = (decide.guard_holds(network, inc, 4, now=now)
               or guards.g11_fight(fight, bool(v(mode, "heal_fight_stop")))
               or guards.g12_size(sized, v(mode, "heal_max_removed_units"),
                                  v(mode, "heal_max_units"))
               or guards.g14_rolled_back(rows, device, last_halt))
    except Exception as exc:                          # noqa: BLE001 (decided again, logged)
        log.warning("heal batch: %s's guards 11, 12 and 14 could not be judged (%s); it is "
                    "decided again", item.get("incident"), exc)
        return None
    if hit:
        return None
    outcome, words = decide._outcome(
        mode, {"tier": src.get("tier"), "kind": src.get("kind"), "units": list(units),
               "blocked": None},
        list(mode.get("kinds_auto") or []), list(mode.get("kinds_propose") or []), device)
    if outcome != "heal":
        return None
    named = approval.get("named") or ""
    made = {k: d[k] for k in ("incident", "device", "person", "settled", "triggers",
                              fault_drills.FIELD) if k in d}
    made.update({k: src.get(k) for k in ("kind", "tier", "program", "program_hash",
                                         "removal_ids", "departure", "dangerous", "verify")})
    made.update(
        units=list(units), outcome="heal", mode=mode.get("mode"), guard=None, until=None,
        words=words, previewed=d["id"],
        policy={"fingerprint": mode.get("fingerprint"),
                "by": (mode.get("confirmed") or {}).get("by"),
                "reason": (mode.get("confirmed") or {}).get("reason")},
        batch={"id": approval.get("id"), "by": approval.get("by"), "hash": approval.get("hash"),
               **({"named": named} if named else {})},
        # C2817: a step's words name no id or hash; the record's own fields hold them.
        steps=[{"step": "claim", "result": "ok", "words": f"the incident on {device} taken"},
               {"step": "decide", "result": "ok", "words": (
                   (f"approved by {named}" if named else
                    f"approved by {approval.get('by_shown') or 'a person'}'s batch")
                   + ": decided as the batch previewed it, with no second read; the act reads "
                     f"{device} again and sends only the program previewed")}],
        phase="decide")
    return decide.said_of(network, inc, made)


def _one(network: str, item: dict, approval: dict, *, act_start=None, wait=None,
         sources=None) -> dict:
    """One device of the batch: ``{"device", "outcome", "words", "decision", "job"}``, its
    *outcome* the heal act's (`act.OUTCOMES`), else ``refused`` or the decision's outcome."""
    from modules.heal import act, decide, decisions, incidents, interrupted

    device, by = item["device"], f"{approval.get('named') or BUTTON} ({approval['id']})"
    now = time.time()
    try:
        inc = incidents.take_standing(network, item["incident"], by=by, now=now)
    except incidents.Refused as exc:
        return {"device": device, "outcome": "refused", "words": f"not taken: {exc}"}
    # C3865 (the operator, 2026-11-16: "the switch-on fires the batch's restores' acts at
    # once"): the heal decision made from the decision the batch previewed, no device read;
    # one that cannot be is decided again, reading the device, as before.
    made = _as_previewed(network, inc, item, approval, now)
    if made is None:
        made = decide.decide_one(network, inc, now=now, sources=sources, batch=approval)
    steps, phase = made.pop("steps", []), made.pop("phase", "decide")
    from modules import filestore
    with filestore.PathLock(decisions.rate_lock_path(network)):
        # The operator, 2026-11-16: no rate holds a heal (guard 10's recount is gone); the
        # record is still written under the lock decide's record step takes.
        d = decisions.record(network, made, now)
    decide._act(network, inc, d, now)
    decide._log_steps(network, dict(d, steps=steps, phase=phase), now)
    if d["outcome"] != "heal":
        return {"device": device, "outcome": d["outcome"], "decision": d["id"],
                "words": d.get("outcome_words") or d.get("words") or d["outcome"]}
    if d.get("program_hash") != item["program_hash"]:
        words = (f"its program moved since the batch was previewed (approved "
                 f"{item['program_hash'][:12]}, now {(d.get('program_hash') or 'none')[:12]}). "
                 "Nothing was sent")
        decisions.take(network, d["id"], by=by, now=now)
        decisions.applied(network, d["id"], "refused", by=by, words=words, now=now)
        # Refused is no fix: its incident stands on it, said (C3870, `act.outcome_on_incident`).
        act.outcome_on_incident(network, d, "refused", words)
        return {"device": device, "outcome": "refused", "decision": d["id"], "words": words}
    try:
        interrupted.hold(network, d["id"], device, by)
    except (interrupted.Busy, OSError) as exc:
        return {"device": device, "outcome": "refused", "decision": d["id"],
                "words": f"not started: {exc}"}
    try:
        taken = decisions.take(network, d["id"], by=f"{by}: the apply", now=now)
    except decisions.Refused as exc:
        interrupted.release(network, d["id"])
        return {"device": device, "outcome": "refused", "decision": d["id"],
                "words": f"not started: {exc}"}
    job = (act_start or act.start)(network, taken)
    done, j = (wait or _wait)(job, WAIT_S)
    res = ((j or {}).get("payload") or {}).get("result") or {}
    if not done:
        return {"device": device, "outcome": "unknown", "decision": d["id"], "job": job,
                "words": f"its heal job had not ended after {WAIT_S} s; it goes on, on its card"}
    outcome = res.get("outcome") or ("failed" if (j or {}).get("state") == "failed" else "")
    return {"device": device, "outcome": outcome or "unknown", "decision": d["id"], "job": job,
            "words": act.OUTCOME_WORDS.get(outcome, res.get("words") or (j or {}).get("error")
                                           or "its outcome could not be read")}
