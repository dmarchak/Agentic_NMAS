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
   - **first**: one device first (`_one`): its standing incident taken, decided again with
     guard 6 resolved and the grace dropped for this batch (`decide.BATCH_RESOLVES`), guard 10
     counted again under the batch's lock as it is recorded, refused unless its program hash
     is the one previewed, then THE heal act as its own job (`act.start`: held, the deploy's
     nine stages, verified, rolled back on failure, recorded), waited for;
   - **rest**: only once the first healed and verified, the rest at once
     (`fanout.each_until_failure`), each held and verified, starting no new device after the
     first failure (CLAUDE.md, "Reads across devices run concurrently", its heal-batch clause):
     the remaining restores and the saved scripts, each script through its normal path
     (`_script`, `saved_plans.fire` with the batch's claim, the batch named on the run's reason
     and authority, its plan hash the one approved, guards 1 to 4 asked, guard 6 resolved);
     with no restore, the first script is the one device first;
   - **record**: the batch's outcome recorded (a ``batch_done`` row), per device.

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
         ("first", "Fix one device first, held and verified"),
         ("rest", "Fix the rest at once (restores and saved scripts), each held and verified, "
                  "starting none after a failure"),
         ("record", "Record the batch's outcome"))
STEP_LABELS = {"auto": "Turn on Auto", "approve": "Approve batch", "first": "Fix first device",
               "rest": "Fix the rest", "record": "Record"}
#: A batch decision its job has not taken this long after it was decided is refused by the
#: heal runner (`act.run`): the job ended. The longest a batch waits on its first device and
#: then its rest (`WAIT_S` each) and more.
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
    the order the job does it (`STEPS`: one device first, verified, then the rest)."""
    devices = [d for d in devices if d]
    if not devices:
        return "Held for a person"
    if len(devices) == 1:
        return f"Held for a person: one press fixes {devices[0]} and verifies it"
    rest = devices[1] if len(devices) == 2 else "the rest at once"
    return (f"Held for a person: one press fixes {devices[0]}, verifies it, "
            f"then fixes {rest}")


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
            incidents_doc: dict = None, script_items=None) -> dict:
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
    caller has them."""
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
    for host, d in sorted(_newest(rows).items()):
        g = d.get("guard") or {}
        if d.get("outcome") != "held" or g.get("guard") != 6:
            continue
        inc = standing.get(d.get("incident"))
        if inc is None or (inc.get("standing") or {}).get("decision") != d.get("id"):
            continue
        b = d.get("beyond") or {}
        if b.get("outcome") == "heal" and b.get("program_hash"):
            out["items"].append({"device": host, "incident": d["incident"],
                                 "decision": d["id"], "program": list(b.get("program") or []),
                                 "program_hash": b["program_hash"],
                                 "units": int(b.get("units") or 0), "kind": b.get("kind") or "",
                                 "words": b.get("words") or ""})
        else:
            out["others"].append({"device": host, "incident": d["incident"],
                                  "why": b.get("words") or "its fix could not be previewed"})
    if not out["items"] and not out["others"]:
        return out
    # Not handed in: never read here (the module's docstring). Said, so a card drawn without
    # a list never reads as "none".
    ai_items, ai_err = _handed(ai_items, "the open incidents with no fix")
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
    out.update(on=True, n=len(devices), fixable=fixable, fix=fix_word(fixable),
               hash=batch_hash(out["items"], out["ai"], out["scripts"]),
               lead=lead_words(len(devices), fixable, len(out["items"]),
                               len(out["scripts"]), [a["device"] for a in out["ai"]]),
               hold=hold_words(len(out["items"]) + len(out["others"])))
    return out


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
                 now: float = None) -> dict:
    """Self-healing in Auto for *network* for its default duration, through THE policy write
    (planned, then applied with that plan's own fingerprint as a verified person with
    *reason*): ``{"ok", "nothing", "until", "words"}``. Already in Auto: nothing written, said.
    A refused plan raises `policy.PolicyRefused`, naming the gate."""
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
                               person=person, reason=reason, now=now)
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


def press(network: str, shown: str, *, actor: str, verified: str, ident, ai_items=None,
          start_ai=None, starter=None, ai_starter=None, script_items=None) -> dict:
    """The one press (the module's steps): ``{"job", "ai", "preview"}``, or `Refused` naming
    what it compared, with nothing started. The caller hands in what this module never reads
    (the module's docstring): *ai_items*, the open incidents with no fix as the card listed
    them (`control_strip.batch_ai_items`), *script_items*, the incidents an Automatic saved
    script matches with their previewed plans (`control_strip.batch_script_items`, C3819), and
    *start_ai* ``(network, ids, **kw)``, the AI's starts (`heal_notice.start_catch_up`); a
    batch with incidents for the AI and no *start_ai* is refused, nothing started. The shown
    hash binds the scripts too (`batch_hash`). *starter* and *ai_starter* replace the job and
    the AI's job (tests)."""
    from modules.nsot import capture_job

    why = may_press(ident)
    if why:
        raise Refused(why)
    p = preview(network, ai_items=ai_items, script_items=script_items)
    if p["state"] != "ok":
        raise Refused(f"the batch cannot be read ({p['error']}); nothing was started")
    if not p["on"]:
        raise Refused("no batch is held by guard 6 now; nothing was started")
    if (shown or "") != p["hash"]:
        raise Refused(moved(shown or "", p))
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
    label = f"{BUTTON}: {p['fixable']} device(s) on {network}"
    work = (lambda _job: {"ok": True, "result": run(network, p, actor=actor,
                                                    verified=verified, person=True)})
    job = (starter or capture_job.start)(
        network, label, actor, work, kind=KIND, announce_keys=DONE_KEYS, announcer=ANNOUNCER,
        page="/v2/?batch={job}#control-strip")
    log.info("heal batch: %s pressed %s on %s (%d to fix, %d by saved scripts, %d for the AI)",
             identity.display_name(actor), p["hash"][:12], network, p["fixable"],
             len(p["scripts"]), len(p["ai"]))
    return {"job": job, "ai": ai, "preview": p}


def _record_row(network: str, row: dict) -> dict:
    from modules.heal import decisions

    return decisions._append(network, row)


def run(network: str, p: dict, *, actor: str, verified: str, person: bool,
        sources=None, act_start=None, wait=None, now=None) -> dict:
    """The batch's job (the module's steps 2): ``{"batch", "steps", "devices", "outcome",
    "words"}``, *devices* ``[{"device", "outcome", "words"}]``. *act_start* and *wait* replace
    a device's heal job and its wait (tests)."""
    from modules import identity
    from modules.fanout import NOT_STARTED, Failed, each_until_failure
    from modules.heal import act, policy

    now = time.time() if now is None else float(now)
    steps = []
    step, begin = act.live_steps(steps, STEPS, "", STEP_LABELS)
    shown = identity.display_name(actor)
    out = {"batch": "", "steps": steps, "devices": [], "outcome": "", "words": ""}

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

    begin("auto", "turning on self-healing in Auto")
    # C3819: the batch's saved scripts are claimed before Auto is turned on, under the scripts
    # store's lock (`saved_plans.claim_for_batch`), so the re-decide that turn-on starts
    # (`policy.apply`'s `redecide_soon`), the heal decision's `fire_matching` and any other
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
                saved_plans.release(s["key"], row["id"], words)
    try:
        got = turn_on_auto(network, actor=actor, verified=verified, person=person,
                           reason=f"{BUTTON}, pressed on Needs attention", now=now)
    except (policy.PolicyRefused, policy.NotAPerson) as exc:
        release(scripts, "not run: self-healing was not turned on")
        step("auto", "refused", f"self-healing was not turned on: {exc}. Nothing was sent")
        return finish("refused", f"self-healing was not turned on ({exc}); nothing was sent")
    step("auto", "ok", got["words"])
    bid = "hb-" + p["hash"][:12] + "-" + hex(int(now))[2:]
    approval = {"id": bid, "by": actor, "by_shown": shown, "hash": p["hash"],
                "verified": verified}
    try:
        _record_row(network, {"row": "batch", "id": bid, "by": actor, "actor_verified": verified,
                              "hash": p["hash"], "at": _iso(now), "epoch": now,
                              "items": [{k: i[k] for k in ("device", "incident", "decision",
                                                           "program_hash")}
                                        for i in p["items"]],
                              "scripts": [{k: s[k] for k in ("key", "incident", "device",
                                                             "hash")}
                                          for s in p.get("scripts") or []],
                              "ai": [a["id"] for a in p["ai"]]})
    except Exception as exc:                          # noqa: BLE001 (nothing sent)
        release(scripts, "not run: the batch's approval could not be recorded")
        step("approve", "refused", f"the approval could not be recorded ({exc})")
        return finish("refused", "the approval could not be recorded; nothing was sent")
    out["batch"] = bid
    step("approve", "ok", (f"approved by {shown}: {len(p['items'])} device(s), each program as "
                           "previewed" + (f", and {len(scripts)} saved script(s), each plan as "
                                          "previewed" if scripts else "")))
    # One device first, verified, then the rest at once (CLAUDE.md, the heal-batch clause):
    # guard 6's restores first, then the saved scripts, each through its own path.
    work = [("heal", i) for i in p["items"]] + [("script", s) for s in scripts]
    if not work:
        return finish("fixed", "nothing for Mercury to fix; the AI was started on the rest")

    def do(w):
        kind, i = w
        if kind == "heal":
            return _one(network, i, approval, act_start=act_start, wait=wait, sources=sources)
        return _script(network, i, approval, claims[(i["key"], i["incident"])])

    def not_started(w, words):
        kind, i = w
        if kind == "script":
            release([i], f"not run: {words}")
        return {"device": i["device"], "outcome": "not_started", "words": f"not started: {words}",
                **({"script": i["key"]} if kind == "script" else {})}

    first, rest = work[0], work[1:]
    fdev = first[1]["device"]
    begin("first", f"fixing {fdev} first")
    r = do(first)
    out["devices"].append(r)
    if r["outcome"] != "healed":
        step("first", "failed", f"{fdev}: {r['words']}")
        out["devices"] += [not_started(w, "the first device did not heal") for w in rest]
        return finish("stopped", (f"{fdev} did not heal ({r['words']}), so no other "
                                  "device was started"))
    step("first", "ok", f"{fdev} healed and verified")
    if not rest:
        return finish("fixed", f"{fdev} healed and verified")
    begin("rest", f"fixing {len(rest)} at once")
    got = each_until_failure(do, rest,
                             lambda x: isinstance(x, dict) and x.get("outcome") == "healed",
                             name="heal-batch")
    for w, res in zip(rest, got):
        if res == NOT_STARTED:
            res = not_started(w, "a device before it did not heal")
        elif isinstance(res, Failed):
            # A script's fire that raised keeps its claim (fails closed: never run twice).
            res = {"device": w[1]["device"], "outcome": "failed", "words": str(res)}
        out["devices"].append(res)
    # A script another path had in flight (``already``) is not this batch's verified fix.
    bad = [d for d in out["devices"] if d["outcome"] != "healed"]
    if bad:
        step("rest", "failed", "; ".join(f"{d['device']}: {d['words']}" for d in bad[:4]))
        return finish("stopped", (f"{len(out['devices']) - len(bad)} of {len(out['devices'])} "
                                  f"fixed and verified; {bad[0]['device']} did not "
                                  f"({bad[0]['words']})"))
    step("rest", "ok", f"{len(rest)} fixed and verified")
    return finish("fixed", f"all {len(out['devices'])} fixed and verified")


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


def _one(network: str, item: dict, approval: dict, *, act_start=None, wait=None,
         sources=None) -> dict:
    """One device of the batch: ``{"device", "outcome", "words", "decision", "job"}``, its
    *outcome* the heal act's (`act.OUTCOMES`), else ``refused`` or the decision's outcome."""
    from modules.heal import act, decide, decisions, incidents, interrupted

    device, by = item["device"], f"{BUTTON} ({approval['id']})"
    now = time.time()
    try:
        inc = incidents.take_standing(network, item["incident"], by=by, now=now)
    except incidents.Refused as exc:
        return {"device": device, "outcome": "refused", "words": f"not taken: {exc}"}
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
        incidents.close(network, d["incident"], f"refused: {words} (decision {d['id']})", now)
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
