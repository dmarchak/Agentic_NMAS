"""The device page's actions on v2 (7.3; the operator's mockup, signed off 2026-10-02, the
mockups' "Device actions on v2" page): each operation's card, drawn in place of the tab's
content. The preview, the confirm and the result are the operation's own (the same job, the
same apply, the same builders the JSON routes use); this module only turns them into what one
card draws for ONE device, with the operands a person checks one level down.

Built in the order capture, persist, rotate, deploy with Mode B. Capture first:

- the preview: what it records, what it will not do, the difference from the golden now,
  the operands (the golden now, this read, committed intent), the checks, and the confirm
  bound to this read's hash; a preview that knows nothing would be recorded says so and
  offers no confirm;
- the result: what happened (the commit, who, when), what is still true (intent), what next,
  and every refusal naming the comparison it made and both operands.

Reads only: every value here comes from the job, the apply, or git.
"""

import logging
import time

log = logging.getLogger(__name__)

VERIFIED_GATE = "You are a verified person"


def _golden_now(repo: str, host: str) -> dict:
    """The device's committed golden now: ``{"commit", "at"}``, or {} when it has none."""
    from modules.nsot import manifest as _m
    from modules.nsot.repo import committed_golden_for, git

    try:
        record = committed_golden_for(repo, _m.find_by_name(repo, host)[1])
    except Exception as exc:                          # noqa: BLE001
        log.warning("device_actions: %s's golden could not be read: %s", host, exc)
        return {"error": str(exc)}
    commit = record.get("commit") or ""
    if not commit:
        return {}
    rc, out, _ = git(repo, "log", "-1", "--format=%cI", commit)
    return {"commit": commit[:10], "at": out.strip() if rc == 0 else ""}


def _intent_commit(repo: str, host: str) -> dict:
    from modules.nsot import hostvars

    try:
        return hostvars.last_intent_commit(repo, host)
    except Exception as exc:                          # noqa: BLE001
        log.warning("device_actions: %s's intent commit could not be read: %s", host, exc)
        return {"error": str(exc)}


def _operand(target: dict, name: str) -> str:
    return next((o.get("value", "") for o in target.get("operands") or []
                 if o.get("name") == name), "")


def capture_card(ref, host: str, job_id: str, got, viewer: dict = None) -> dict:
    """The capture card for *host* from the preview job *got* (`capture_job.get`, or None):
    ``{"state": "reading"|"failed"|"unknown"|"preview", ...}``. *viewer* is who would confirm,
    decided NOW (`preview_confirm.confirm_part`): the preview's own confirm part was decided when
    the read started, and says "nothing to confirm" for a device that equals its golden."""
    card = {"op": "capture", "host": host, "list": ref.name, "job": job_id}
    if got is None:
        return dict(card, state="unknown")
    if got["state"] == "running":
        return dict(card, state="reading", elapsed_s=got.get("elapsed_s"))
    if got["state"] == "failed":
        return dict(card, state="failed", error=got.get("error") or "no reason was recorded")
    preview = (got.get("payload") or {}).get("preview") or {}
    # The preview splits a target: its state and the hash the confirm is bound to are part 1
    # (`what`), its program, operands and gates are its own parts (`targets`).
    target = next((t for t in preview.get("targets") or [] if t.get("name") == host), None)
    chosen = next((t for t in (preview.get("what") or {}).get("targets") or []
                   if t.get("name") == host), None)
    if target is None or chosen is None:
        return dict(card, state="failed",
                    error=f"the preview holds no read of {host}, so nothing can be confirmed")
    what_not = [i for i in preview.get("what_not", {}).get("items") or []
                if i.get("target") == host]
    departs = next((i for i in what_not if i.get("kind") == "departs_from_intent"), None)
    read = chosen.get("state") != "unread"
    viewer = viewer or {"may": False, "statement": "nobody is identified"}
    gates = list(target.get("gates") or [])
    gates.append({"name": VERIFIED_GATE, "state": "pass" if viewer.get("may") else "fail",
                  # The person by name when they may (the mockup); else why not.
                  "detail": (viewer.get("actor") if viewer.get("may") and viewer.get("actor")
                             else viewer.get("statement", ""))})
    failing = [g for g in gates if g.get("state") == "fail"]
    changed = chosen.get("state") == "capturable"
    finished = got.get("finished_at") or time.time()
    card.update(
        state="preview", read=read,
        error=next((i.get("text", "") for i in what_not if i.get("kind") == "unread"), ""),
        changed=changed, diff=list((target.get("program") or {}).get("lines") or []),
        hash=(chosen.get("select_data") or {}).get("hash", ""),
        read_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
        read_in=_operand(target, "read in"),
        intent={"sentence": _operand(target, "committed intent"),
                "departs": departs is not None,
                "lines": list((departs or {}).get("lines") or [])},
        golden=_golden_now(ref.repo_dir, host), intent_commit=_intent_commit(ref.repo_dir, host),
        gates=gates, failing=failing, held=held(gates),
        # A shrink committed intent does not explain needs a person's reason, given where
        # it is built (today's device page); this card draws the failing check.
        acknowledge=(target.get("acknowledge") or {}).get("prompt", ""),
        may=bool(read and changed and not failing))
    return card


#: A result's outcome -> (its heading chip, its level).
RESULT_WORDS = {"captured": ("Recorded", "ok"),
                "unchanged": ("Unchanged: nothing recorded", "muted"),
                "moved": ("Not recorded", "warn"), "busy": ("Not recorded", "warn"),
                "unread": ("Not recorded", "warn"), "not_recorded": ("Not recorded", "danger")}


def capture_result_card(ref, host: str, got: dict, confirmed: str, actor: str,
                        actor_kind: str) -> dict:
    """The result card for *host* from `routes.golden.apply_captures`' answer *got*."""
    outcome = next((o for o in got.get("outcomes") or [] if o.get("device") == host),
                   {"device": host, "outcome": "unread",
                    "reason": "the apply returned no outcome for this device"})
    kind = outcome.get("outcome", "unread")
    chip, level = RESULT_WORDS.get(kind, (kind, "warn"))
    save = got.get("save") or {}
    phases = ((got.get("timing") or {}).get("phases_s") or {}).get(host) or {}
    intent = outcome.get("intent") or {}
    from modules.nsot.intent_match import explain
    return {"op": "capture", "state": "result", "host": host, "list": ref.name,
            "outcome": kind, "chip": chip, "level": level,
            "reason": outcome.get("reason", ""),
            "confirmed": confirmed, "current": outcome.get("current_hash", ""),
            "commit": (save.get("commit") or "")[:10] if kind == "captured" else "",
            "actor": actor, "verified": actor_kind == "person",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "read_in": (f"connect {phases.get('connect_s')} s, show running-config "
                        + ("not reached" if phases.get("read_s") is None
                           else f"{phases.get('read_s')} s")) if phases else "not timed",
            "intent": {"departs": intent.get("state") == "differs",
                       "unknown": intent.get("state") not in ("match", "differs"),
                       "sentence": explain(intent) if intent else "not compared",
                       "lines": list(intent.get("lines") or [])}}


def _one_target(preview: dict, host: str, viewer: dict) -> dict:
    """The parts of a one-device preview (`preview_confirm.build`) a card draws: part 1's
    state and the data the confirm carries, the target's program, operands and gates, what
    will not happen, and the verified-person check decided NOW from *viewer*."""
    target = next((t for t in preview.get("targets") or [] if t.get("name") == host), {})
    chosen = next((t for t in (preview.get("what") or {}).get("targets") or []
                   if t.get("name") == host), {})
    viewer = viewer or {"may": False, "statement": "nobody is identified"}
    gates = list(target.get("gates") or [])
    gates.append({"name": VERIFIED_GATE, "state": "pass" if viewer.get("may") else "fail",
                  "detail": (viewer.get("actor") if viewer.get("may") and viewer.get("actor")
                             else viewer.get("statement", ""))})
    failing = [g for g in gates if g.get("state") == "fail"]
    return {"target": target, "chosen": chosen, "gates": gates, "failing": failing,
            "what_not": [i.get("text", "") for i in (preview.get("what_not") or {}).get("items")
                         or [] if i.get("target") == host],
            "may": bool(chosen.get("selectable")) and not failing}


def persist_card(ref, host: str, preview: dict, viewer: dict) -> dict:
    """The persist card for *host* from `preview_confirm.persist_preview`'s preview. The
    preview contacts no device, so the card is drawn at once, never as a job."""
    t = _one_target(preview, host, viewer)
    program = t["target"].get("program") or {}
    confirm = preview.get("confirm") or {}
    return {"op": "persist", "state": "preview", "host": host, "list": ref.name,
            "summary": (preview.get("what") or {}).get("summary", ""),
            "sent": list(program.get("lines") or []),
            "then": [line for n in program.get("notes") or [] for line in n.get("lines") or []],
            "none": program.get("none", ""),
            "what_not": t["what_not"], "operands": list(t["target"].get("operands") or []),
            "gates": t["gates"], "failing": t["failing"], "may": t["may"],
            "held": held(t["gates"]),
            "hash": (t["chosen"].get("select_data") or {}).get("hash", ""),
            "effect": confirm.get("effect", ""), "button": confirm.get("button", "")}


#: A persist result's state -> (its heading chip, its level).
PERSIST_WORDS = {"persisted": ("Persisted", "ok"),
                 "not_persisted": ("Saved, NOT persisted", "danger"),
                 "refused": ("Refused: nothing was sent", "warn")}


def persist_result_card(ref, host: str, out: dict, result: dict) -> dict:
    """The result card from `persist_op.apply`'s answer *out* and `persist_result`'s
    *result*, the same words today's page draws."""
    state = out.get("state") or "unknown"
    chip, level = PERSIST_WORDS.get(state, ("Could not be established", "danger"))
    return {"op": "persist", "state": "result", "host": host, "list": ref.name,
            "outcome": state, "chip": chip, "level": level,
            "summary": (result.get("happened") or {}).get("summary", ""),
            "record": (result.get("record") or {}).get("statement", ""),
            "not_watched": result.get("not_watched", ""),
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def held(gates: list) -> bool:
    """Whether a card was refused because another operation holds its device: it then
    listens for the hold's release (`device_holds`) and reads again."""
    from modules.preview_confirm import BUSY_GATE
    return any(g.get("name") == BUSY_GATE and g.get("state") == "fail" for g in gates or [])


def rotate_card(ref, host: str, preview: dict, viewer: dict) -> dict:
    """The rotate card for *host* from `preview_confirm.rotate_preview`'s preview, whose
    plan read the device's account line LIVE."""
    t = _one_target(preview, host, viewer)
    program = t["target"].get("program") or {}
    confirm = preview.get("confirm") or {}
    return {"op": "rotate", "state": "preview", "host": host, "list": ref.name,
            "summary": (preview.get("what") or {}).get("summary", ""),
            "sent": list(program.get("lines") or []),
            "then": [line for n in program.get("notes") or [] for line in n.get("lines") or []],
            "none": program.get("none", ""),
            "what_not": t["what_not"], "operands": list(t["target"].get("operands") or []),
            "gates": t["gates"], "failing": t["failing"], "may": t["may"],
            "held": held(t["gates"]),
            "fingerprint": (t["chosen"].get("select_data") or {}).get("fingerprint", ""),
            "effect": confirm.get("effect", ""), "button": confirm.get("button", "")}


#: A rotation result's level -> the card's level.
ROTATE_LEVELS = {"success": "ok", "partial": "warn", "failed": "danger"}


#: Every job-backed card and the steps its running state draws (C370, the operator: the
#: signed-off stepper on every job-backed v2 card): ``(module, attribute)`` of the operation's
#: declared STEPS and DETOURS, or a reason it draws none. Persist, deploy and Mode B join as
#: they land as jobs. tests/test_job_stepper.py holds every job card in the templates to this.
JOB_STEPPERS = {
    "rotate": ("modules.nsot.rotate_op", "STEPS", "DETOURS"),
    # The pipeline notes each stage as it STARTS (rotation notes a step once done).
    "deploy": ("modules.pipeline", "STEPS", None, "starts"),
    # A restore runs the same pipeline (`run_targets`), as a job.
    "restore": ("modules.pipeline", "STEPS", None, "starts"),
    "capture": ("one step: the preview's read of the device, which holds nothing and so notes "
                "no progress; its card names what it reads"),
}


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def stepper(steps, progress, *, detours=None, now=None, starts=False) -> list:
    """The signed-off stepper's rows (NSOT_GUI_BRIEF 10a) for a running job: the operation's
    DECLARED *steps* (``(key, words, waits, names)``), each done (with how long it took),
    running (since when, what it waits on, the last thing it did) or waiting, read from the
    hold's progress trail (`device_ops.note`: ``{"step", "at", "trail": [[name, at], ...]}``).
    A step is done once its last name is noted; with *starts* (an operation that notes a step
    as it begins, the pipeline), a noted name is the step now running. With no progress (the
    hold not taken yet, or held by another process) the first step runs, from now."""
    now = time.time() if now is None else now
    index = {name: i for i, s in enumerate(steps) for name in s[3]}
    keys = [s[0] for s in steps]
    index.update({name: keys.index(key) for name, key in (detours or {}).items()})
    progress = progress or {}
    trail = progress.get("trail") or ([[progress["step"], progress["at"]]]
                                      if progress.get("at") else [])
    begun = trail[0][1] if trail else now
    ends, current, last = {}, 0, ""
    for name, at in trail:
        if name not in index:
            continue
        i = index[name]
        for j in range(i):
            ends.setdefault(j, at)
        last = name
        if name == steps[i][3][-1] and not starts:
            ends[i], current = at, i + 1
        else:
            current = i
    rows, started = [], begun
    for i, (key, words, waits, _names) in enumerate(steps):
        if i < current:
            end = ends.get(i, started)
            rows.append({"key": key, "words": words, "state": "done",
                         "took_s": round(max(0.0, end - started))})
            started = end
        elif i == current:
            rows.append({"key": key, "words": words, "state": "running", "since": _iso(started),
                         "took_s": round(max(0.0, now - started)), "waits": waits,
                         "last": last if index.get(last) == i else ""})
        else:
            rows.append({"key": key, "words": words, "state": "waiting"})
    return rows


def job_steps(op: str, list_name: str, host: str, *, now=None) -> list:
    """The stepper rows for *op*'s running job on *host*, from its declared steps and the
    device's hold; [] for a card that declares why it draws none."""
    import importlib

    from modules.nsot import device_ops

    ref = JOB_STEPPERS[op]
    if isinstance(ref, str):
        return []
    mod = importlib.import_module(ref[0])
    holder = device_ops.holder(list_name, host) or {}
    return stepper(getattr(mod, ref[1]), holder.get("progress"),
                   detours=getattr(mod, ref[2], None) if ref[2] else None, now=now,
                   starts=len(ref) > 3 and ref[3] == "starts")


def rotate_job_card(ref, host: str, job_id: str, got) -> dict:
    """The rotate card for its job (`capture_job.get`, or None): rotating with its stepper,
    its result, or why there is none. The result is `rotate_result`'s, the words today's page
    draws."""
    card = {"op": "rotate", "host": host, "list": ref.name, "job": job_id}
    if got is None:
        return dict(card, state="unknown")
    if got["state"] == "running":
        return dict(card, state="rotating", elapsed_s=got.get("elapsed_s"),
                    steps=job_steps("rotate", ref.name, host))
    if got["state"] == "failed":
        return dict(card, state="failed", error=got.get("error") or "no reason was recorded")
    result = (got.get("payload") or {}).get("result") or {}
    target = ((result.get("happened") or {}).get("targets") or [{}])[0]
    checks = ((result.get("targets") or [{}])[0].get("checks") or {})
    nxt = result.get("next") or {}
    return dict(card, state="result", level=ROTATE_LEVELS.get(result.get("level"), "danger"),
                outcome=target.get("outcome", "unknown"), words=target.get("words", ""),
                summary=(result.get("happened") or {}).get("summary", ""),
                verified=(checks.get("statements") or [checks.get("why", "")])[0],
                did_not=[i.get("text", "") for i in (result.get("did_not") or {}).get("items")
                         or [] if i.get("kind") != "not_doing"],
                record=(result.get("record") or {}).get("statement", ""),
                not_watched=result.get("not_watched", ""),
                next=nxt.get("text", ""), export=nxt.get("open") == "breakglass_export",
                # C541: rotated with its persistence not attempted: the card's button is Persist.
                persist=nxt.get("open") == "persist")


# ---------------------------------------------------------------------------
# Deploy, with Mode B (7.3; the device-actions canvas, boards 5 and 6): the device's whole
# committed intent, merge-only, with a dangerous line's stated reason and the residue a person
# ticks for removal, each reason in the hash; run as a job (`deploy_job`), its stepper the
# pipeline's stages; the result from the receipt the apply wrote.
# ---------------------------------------------------------------------------

def _declare_part(ref, entry: dict, pending: dict) -> dict:
    """The card's declarations (C506 phase 3, the board approved 2026-10-06): what is declared,
    each with what verify will require and its reason, carried as the form's own value between
    plans; what may be declared; and the new declaration being typed, with why it is not one
    yet."""
    import json

    from modules.nsot import expected_effects as fx
    from modules.nsot.convergence import window_for

    effects = entry.get("expected_effects") or {}
    offers = effects.get("offers") or {}

    def requires(d):
        if d.get("kind") == "moves":
            try:
                seconds = window_for(d["proto"], ref.name)["timeout"]
            except Exception:                  # noqa: BLE001
                seconds = None
            return (f"it must re-form on {d['to']} within "
                    + (f"{'OSPFv3' if d['proto'] == 'ospfv3' else 'OSPF'}'s settle window "
                       f"({seconds} s)" if seconds else "its protocol's settle window")
                    + ", or verify fails and the change is rolled back")
        if d.get("kind") == "ends":
            return "its loss is expected, and is not a failure"
        return "a smaller route table is recorded, and is not a failure"

    declared = [{"words": fx.words(d)[0].upper() + fx.words(d)[1:], "reason": d.get("reason", ""),
                 "requires": requires(d), "raw": json.dumps(fx.raw_of(d), sort_keys=True)}
                for d in entry.get("declared") or []]
    moves = [{"id": m["id"], "words": fx.offer_words(m)} for m in offers.get("moves") or []]
    ends = [{"id": e["id"], "words": fx.offer_words(e)} for e in offers.get("ends") or []]
    to = list(offers.get("to") or [])
    return {
        "declared": declared, "moves": moves, "to": to, "ends": ends,
        "routes_declared": any(d.get("kind") == "routes" for d in entry.get("declared") or []),
        "moves_none": ("" if moves and to else
                       "Nothing to move: the program drops no OSPF adjacency whose router-id "
                       "intent gives" if not moves else
                       "Nowhere to move it: the program brings up no interface with OSPF on it"),
        "ends_none": "" if ends else ("Nothing to end: committed intent gives this device no "
                                      "other adjacency with a known identity"),
        "pending": dict({"mv_id": "", "mv_to": "", "mv_why": "", "end_id": "", "end_why": "",
                         "rt_why": "", "problem": "", "open": ""}, **(pending or {})),
        "kinds": dict(fx.DECLARE_WORDS),
    }


def deploy_card(ref, host: str, entry: dict, preview: dict, viewer: dict, *,
                reasons=None, danger_reasons=None, pending=None) -> dict:
    """The deploy card for *host* from `routes.deploy.plan_devices`'s *entry* and
    `deploy_preview`'s *preview*, both masked (the ticked residue is the plan's own `removals`),
    *reasons* each ticked line's stated reason (by id), *danger_reasons* each dangerous line's (by its
    index in the plan's list): the form carries them and the plan is computed again with them,
    so the confirm binds the program on the screen."""
    reasons, danger_reasons = reasons or {}, danger_reasons or {}
    t = _one_target(preview, host, viewer)
    program = t["target"].get("program") or {}
    removals = entry.get("removals") or {}
    chosen = set(removals.get("ids") or [])
    residue = [{"id": r.get("id", ""),
                "text": " > ".join(list(r.get("chain") or []) + [str(r.get("line", "")).strip()]),
                "why_not": r.get("why_not", ""), "picked": r.get("id") in chosen,
                "reason": reasons.get(r.get("id"), "")}
               for r in entry.get("removable") or []]
    dangerous = [{"index": i, "line": line, "reason": danger_reasons.get(i, "")}
                 for i, line in enumerate(entry.get("dangerous") or [])]
    waiting = entry.get("authorisation_ok") is False
    blocking = list(entry.get("blocking_reasons") or [])
    refused = entry.get("refused") or entry.get("error") or ""
    lines = list(program.get("lines") or [])
    # A line waiting on its reason fails the preview's own "dangerous lines" check (ticked
    # removals included), so `t["may"]` decides it; `waiting` only chooses the words.
    may = bool(t["may"]) and not blocking and not refused and bool(lines)
    confirm = preview.get("confirm") or {}
    # The one device, never the batch's "the devices you tick… N of N… for each" (C408).
    removing = any(r["picked"] for r in residue)
    summary = (f"Deploy {host}'s committed intent, merge-only"
               + (", with the lines you ticked for removal" if removing else "")
               + (f": exactly these {len(lines)} line(s) are sent, in order." if lines
                  else ": nothing to send."))
    return {"op": "deploy", "state": "preview", "host": host, "list": ref.name,
            "summary": summary,
            "sent": lines, "none": program.get("none", ""),
            "notes": [{"title": n.get("title", ""), "lines": list(n.get("lines") or [])}
                      for n in program.get("notes") or []],
            "dangerous": dangerous, "residue": residue,
            # What the program is meant to do, derived (C506 phase 2), and declared (phase 3).
            "expected": program.get("expected") or {},
            "declare": _declare_part(ref, entry, pending),
            "waiting": waiting, "authorisation_error": entry.get("authorisation_error", ""),
            "blocking": blocking, "refused": refused,
            "what_not": t["what_not"], "operands": list(t["target"].get("operands") or []),
            "gates": t["gates"], "failing": t["failing"], "may": may,
            "held": held(t["gates"]),
            "effect": confirm.get("effect", ""),
            "confirm": ({"capture_hash": entry.get("capture_hash", ""),
                         "command_hash": entry.get("command_hash", ""),
                         "remove": list(removals.get("ids") or []),
                         "authorise": list(entry.get("authorised") or []),
                         "declare": []} if may else None),
            "command_hash": entry.get("command_hash", "")}


#: A deploy's outcome -> the card's level.
DEPLOY_LEVELS = {"success": "ok", "partial": "warn", "failed": "danger", "nothing": "warn"}


# ---------------------------------------------------------------------------
# Restore from a moment (7.3; the device-actions canvas, boards 9 and 10): choose the moment,
# its preview (THE restore plan, `routes.golden.restore_plan`), run as a job (`deploy_job.
# start_restore`) in the list the preview was drawn in (C396), its result from the receipt.
# ---------------------------------------------------------------------------

#: A moment's credential state -> (badge words, level, why it cannot be chosen or "").
RESTORE_CREDENTIAL = {
    "current": ("credentials current", "ok", ""),
    "silent": ("would add back an account", "danger", ""),
    "refused": ("predates its credentials", "warn", ""),
    "no_golden": ("no golden for it", "muted", "no golden configuration for it at this moment"),
    # Beyond the moments drawn, not checked (C399); never drawn unless all are, when all are
    # checked.
    "unchecked": ("credentials not checked", "muted", "its credentials were not checked"),
}
#: How many moments the chooser draws before "Show N more".
RESTORE_SHOWN = 5


def _moment_words(point: dict) -> str:
    if point.get("kind") == "head":
        return "Golden now"
    when = (point.get("created") or "")[:16].replace("T", " ")
    if point.get("kind") == "baseline":
        return f"Baseline {when}"
    return f"Its golden {when}"


def restore_choose_card(ref, host: str, points: list, *, show_all: bool = False,
                        chosen: str = "") -> dict:
    """The chooser (board 9's first card): every moment *host* can be restored from, newest
    first, each with its credential state; a moment that cannot be chosen says why. An
    account a moment would ADD BACK is said here and asked for at the preview, as a stated
    reason (the operator, 2026-10-03), never as typed words."""
    rows = []
    for p in points:
        words, level, why_not = RESTORE_CREDENTIAL.get(p.get("credential"),
                                                       (p.get("credential", "unknown"), "muted",
                                                        "its credential state is unknown"))
        rows.append({"ref": p.get("ref", ""), "words": _moment_words(p),
                     "kind": p.get("kind", ""), "subject": p.get("subject", ""),
                     "claim": p.get("claim", ""), "claim_detail": p.get("claim_detail", ""),
                     "badge": words, "level": level, "why_not": why_not,
                     "adds_back": p.get("credential") == "silent",
                     "same_as_now": bool(p.get("same_as_now")) and p.get("kind") != "head"})
    # The golden now, and any moment holding the same golden, sends nothing by construction
    # (the program is a moment's golden against today's), so the newest moment that DIFFERS is
    # ticked first, when there is one.
    first = next((r["ref"] for r in rows if not r["why_not"] and r["kind"] != "head"
                  and not r["same_as_now"]),
                 next((r["ref"] for r in rows if not r["why_not"]), ""))
    shown = rows if show_all else rows[:RESTORE_SHOWN]
    return {"op": "restore", "state": "choose", "host": host, "list": ref.name,
            "moments": shown, "more": len(rows) - len(shown), "show_all": show_all,
            "chosen": chosen if any(r["ref"] == chosen for r in rows) else first}


def restore_card(ref, host: str, moment: str, plan: dict, viewer: dict, *,
                 danger_reasons=None, un_onboard: bool = False) -> dict:
    """The restore preview for *host* at *moment* from `restore_plan`'s *plan*, MASKED: the
    program and what each line replaces, each line needing a stated reason (a dangerous line,
    an account added back) with its reason in the hash, what is left on the device (merge-only),
    the operands and checks, and the confirm bound to the program. A moment that predates the
    device's onboarding asks: leave it as it is, or un-onboard it too."""
    danger_reasons = danger_reasons or {}
    card = {"op": "restore", "host": host, "list": ref.name, "moment": moment,
            "moment_words": "golden now" if moment == "HEAD" else moment,
            "un_onboard": un_onboard}
    entry = next((d for d in plan.get("devices") or [] if d.get("device") == host), None)
    skip = next((s for s in plan.get("skipped") or [] if s.get("hostname") == host), None)
    if entry is None:
        if skip and skip.get("un_onboardable"):
            return dict(card, state="predates", detail=skip.get("detail", ""))
        return dict(card, state="not_restorable",
                    reason=(skip or {}).get("reason", "this moment holds nothing for it"),
                    detail=(skip or {}).get("detail", ""))
    preview = plan.get("preview") or {}
    t = _one_target(preview, host, viewer)
    program = t["target"].get("program") or {}
    flagged = list(entry.get("dangerous") or []) + list(entry.get("secret_readded") or [])
    secret = set(entry.get("secret_readded") or [])
    reasons = [{"index": i, "line": line, "reason": danger_reasons.get(i, ""),
                "why": ("adds back an account the device does not hold" if line in secret
                        else "a dangerous line")}
               for i, line in enumerate(flagged)]
    blocking = list(entry.get("blocking_reasons") or [])
    refused = entry.get("error") or ""
    lines = list(program.get("lines") or [])
    may = bool(t["may"]) and not blocking and not refused and bool(lines)
    intent = entry.get("intent") or {}
    # This device and this moment, never the fleet restore's "N of M device(s) you selected"
    # (C402); and with nothing to send, one statement: nothing to confirm (C401: the shared
    # preview's "still read back at apply" is the legacy restore's, which confirms it; this
    # card offers no confirm then, board 9).
    words = card["moment_words"]
    if lines:
        summary = (f"Re-apply {host}'s golden as it was at {words}, and its committed intent "
                   f"with it: {len(lines)} line(s) to send, merge-only.")
        none = program.get("none", "")
    elif blocking or refused:
        summary = f"Re-apply {host}'s golden as it was at {words}: refused, nothing is sent."
        none = program.get("none", "")
    else:
        summary = f"{host} already holds every line of {words}: nothing to send."
        none = f"Nothing to send, so nothing to confirm: {host} already matches {words}."
    return dict(card, state="preview",
                summary=summary,
                sent=lines, none=none,
                notes=[{"title": n.get("title", ""), "lines": list(n.get("lines") or [])}
                       for n in program.get("notes") or []],
                reasons=reasons, waiting=entry.get("authorisation_ok") is False,
                authorisation_error=entry.get("authorisation_error", ""),
                residue=list(entry.get("residue_in_context") or entry.get("residue") or []),
                excluded=list(entry.get("excluded_unrenderable") or []),
                intent_words=intent.get("detail", ""), intent_action=intent.get("action", ""),
                blocking=blocking, refused=refused, what_not=t["what_not"],
                operands=list(t["target"].get("operands") or []), gates=t["gates"],
                failing=t["failing"], may=may, held=held(t["gates"]),
                effect=(preview.get("confirm") or {}).get("effect", ""),
                command_hash=entry.get("command_hash", ""),
                confirm=({"capture_hash": entry.get("capture_hash", ""),
                          "command_hash": entry.get("command_hash", ""),
                          "authorise": list(entry.get("authorised") or [])} if may else None))


# ---------------------------------------------------------------------------
# Revert and Retry (7.3; the device-actions canvas, board 11): the two ways out of a rollback,
# each committing or recording only (nothing sent to the device), drawn from the builders
# today's routes use (`preview_confirm.revert_preview`/`retry_preview` and their results).
# ---------------------------------------------------------------------------

#: An intent operation's result level -> the card's level.
INTENT_OP_LEVELS = {"success": "ok", "partial": "warn", "failed": "danger"}


def intent_op_card(op: str, ref, host: str, preview: dict, viewer: dict, *,
                   commits=None, reason: str = "") -> dict:
    """The revert or retry preview card (*op*) for *host* from its six parts (MASKED): what
    would be committed or authorised (none of it sent to the device), what it will not do,
    the operands and checks, and the confirm bound to the preview's hash. A revert carries the
    commits to choose from; a retry its stated reason, required before the confirm."""
    t = _one_target(preview, host, viewer)
    program = t["target"].get("program") or {}
    data = t["chosen"].get("select_data") or t["target"].get("select_data") or {}
    lines = list(program.get("lines") or [])
    need_reason = op == "retry"
    reason_problem = ""
    if need_reason and reason:
        from modules.nsot.authorisation import reason_problem as _problem
        reason_problem = (_problem({"line": "retry the rolled-back change", "reason": reason})
                          or "").split(": ", 1)[-1]
    may = bool(t["may"]) and bool(lines) and not (need_reason and (not reason or reason_problem))
    confirm = preview.get("confirm") or {}
    return {"op": op, "state": "preview", "host": host, "list": ref.name,
            "summary": (preview.get("what") or {}).get("summary", ""),
            "sent": lines, "caption": program.get("caption", ""), "none": program.get("none", ""),
            "notes": [{"title": n.get("title", ""), "lines": list(n.get("lines") or [])}
                      for n in program.get("notes") or []],
            "commits": list(commits or []), "reason": reason, "reason_problem": reason_problem,
            "what_not": t["what_not"], "operands": list(t["target"].get("operands") or []),
            "gates": t["gates"], "failing": t["failing"], "held": held(t["gates"]),
            "may": may, "effect": confirm.get("effect", ""),
            "button": confirm.get("button", ""),
            "confirm": ({"hash": data.get("hash", ""), "sha": data.get("sha", "")}
                        if may else None)}


def intent_op_result_card(op: str, ref, host: str, result: dict) -> dict:
    """The revert or retry result card from its `build_result`: what was committed or
    authorised, the check after it (a revert's block measured again), what it did not do, the
    record, and, for a revert whose block still stands, its ways on."""
    happened = next((x for x in (result.get("happened") or {}).get("targets") or []
                     if x.get("name") == host), {})
    target = next((x for x in result.get("targets") or [] if x.get("name") == host), {})
    checks = target.get("checks") or {}
    did_not = [i for i in (result.get("did_not") or {}).get("items") or []
               if i.get("kind") != "not_sent"]
    return {"op": op, "state": "result", "host": host, "list": ref.name,
            "level": INTENT_OP_LEVELS.get(result.get("level"), "danger"),
            "outcome": happened.get("outcome", target.get("outcome", "unknown")),
            "words": happened.get("words", ""),
            "summary": (result.get("happened") or {}).get("summary", ""),
            "checks": list(checks.get("statements") or ([checks["why"]]
                                                        if checks.get("why") else [])),
            # A block's state is the check above, drawn once (C510); `standing` still reads it.
            "did_not": [i.get("text", "") for i in did_not
                        if not str(i.get("kind", "")).startswith("block_")],
            "standing": any(i.get("kind") in ("block_standing", "block_unknown")
                            for i in did_not),
            "record": (result.get("record") or {}).get("statement", ""),
            "not_watched": result.get("not_watched", "")}


#: How many lines of the seeded document the card shows before "… N more" (board 8); the
#: whole document is one click below.
SEED_SHOWN = 8


def seed_card(ref, host: str, preview: dict, viewer: dict, entry: dict) -> dict:
    """The seed card for *host* (board 8) from `preview_confirm.seed_preview`'s preview and
    the device's `seed.public(entry_for(...))` (both MASKED): the intent document that would
    be committed against what is committed now, whether its template reproduces the device
    (an unmodelled line named, and that it blocks a deploy), the device's own lines (named,
    never blocking: C397), what it will not do, the operands and checks, and the confirm bound
    to the seed hash. Nothing is sent to the device."""
    t = _one_target(preview, host, viewer)
    program = t["target"].get("program") or {}
    lines = list(program.get("lines") or [])
    document = entry.get("document") or ""
    confirm = preview.get("confirm") or {}
    # What it will not do: this device's items and the scope's; whether the template
    # reproduces it is its own part of the card, not a thing it "will not do".
    what_not = [i.get("text", "") for i in (preview.get("what_not") or {}).get("items") or []
                if (i.get("target") == host and i.get("kind") != "not_reproduced")
                or i.get("kind") == "scope"]
    return {"op": "seed", "state": "preview", "host": host, "list": ref.name,
            # The one device, never the batch's "N of N device(s)" (C408).
            "summary": f"Commit {host}'s first full intent, parsed from its committed golden.",
            "sent": lines[:SEED_SHOWN], "more": max(0, len(lines) - SEED_SHOWN),
            "count": len(lines), "document": document,
            "document_lines": len(document.splitlines()),
            "caption": program.get("caption", ""), "none": program.get("none", ""),
            "parsed": not entry.get("error"),
            "reproduced": bool(entry.get("reproduced")),
            "unmodeled": list(entry.get("unmodeled") or []),
            "missing": list(entry.get("missing") or []),
            "extra": list(entry.get("extra") or []),
            "fidelity": entry.get("fidelity"), "coverage": entry.get("coverage"),
            "device_owned": list(entry.get("device_owned") or []),
            "self_signed": any(h.startswith("crypto pki trustpoint TP-self-signed-")
                               for h in entry.get("device_owned") or []),
            "not_compared": list(entry.get("not_compared") or []),
            "golden": entry.get("golden", ""),
            "what_not": what_not, "operands": list(t["target"].get("operands") or []),
            "gates": t["gates"], "failing": t["failing"], "may": t["may"],
            "held": held(t["gates"]),
            "hash": (t["chosen"].get("select_data") or {}).get("hash", ""),
            "effect": confirm.get("effect", ""), "button": confirm.get("button", "")}


#: A seed result's level (`seed_result`) -> the card's.
SEED_LEVELS = {"success": "ok", "partial": "warn", "failed": "danger", "nothing": "warn"}


def seed_result_card(ref, host: str, result: dict) -> dict:
    """The seed result card from `preview_confirm.seed_result` (MASKED): what happened and the
    record (the intent commit), what stays true (the template reproduces it, or what blocks a
    deploy until modelled), and, once seeded, its next steps."""
    happened = next((x for x in (result.get("happened") or {}).get("targets") or []
                     if x.get("name") == host), {})
    target = next((x for x in result.get("targets") or [] if x.get("name") == host), {})
    checks = target.get("checks") or {}
    outcome = happened.get("outcome", target.get("outcome", "unknown"))
    return {"op": "seed", "state": "result", "host": host, "list": ref.name,
            "level": SEED_LEVELS.get(result.get("level"), "danger"),
            "outcome": outcome, "seeded": outcome == "seeded",
            "words": happened.get("words", target.get("words", "")),
            "reason": target.get("reason", ""),
            # The one device, never the batch's "N of N device(s) seeded" (C408).
            "summary": f"{host}: {happened.get('words', target.get('words', outcome))}.",
            "reproduced": bool(checks.get("ok")),
            "checks": list(checks.get("statements") or ([checks["why"]]
                                                        if checks.get("why") else [])),
            "issues": list(checks.get("issues") or []),
            "record": (result.get("record") or {}).get("statement", ""),
            "not_watched": result.get("not_watched", "")}


def retire_card(ref, host: str, preview: dict, viewer: dict, plan: dict) -> dict:
    """The retire card for *host* (board 12) from `preview_confirm.retire_preview`'s preview
    and `retire.plan()` (both MASKED): the reason, what retire changes in order (each step
    skipped when already done), what is GENERATED and so dropped at its next regeneration,
    what SURVIVES with how it is removed, what it leaves unchanged, the checks (the
    break-glass one pointing at Credentials), and the confirm bound to the plan's hash."""
    from modules.preview_confirm import BREAKGLASS_GATE

    t = _one_target(preview, host, viewer)
    confirm = preview.get("confirm") or {}
    watched = {f"{w['what']}: {w['how']}" for w in plan.get("generated") or []}
    watched |= {f"{w['what']}: {w['how']}" for w in plan.get("survives") or []}
    unchanged = [n for n in plan.get("not_doing") or []
                 if n not in watched and not n.startswith(("NetBox device ", "the approval of "))]
    breakglass = next((g for g in t["gates"] if g.get("name") == BREAKGLASS_GATE), {})
    return {"op": "retire", "state": "preview", "host": host, "list": ref.name,
            "reason": plan.get("reason") or "",
            "steps": [{"what": s.get("what", ""), "done": bool(s.get("done"))}
                      for s in plan.get("steps") or []],
            "generated": list(plan.get("generated") or []),
            "survives": list(plan.get("survives") or []),
            "unchanged": unchanged, "advisories": list(plan.get("advisories") or []),
            "operands": list(t["target"].get("operands") or []),
            "gates": t["gates"], "failing": t["failing"], "may": t["may"],
            "held": held(t["gates"]),
            "breakglass_failing": breakglass.get("state") == "fail",
            "hash": (t["chosen"].get("select_data") or {}).get("hash", ""),
            "effect": confirm.get("effect", ""), "button": confirm.get("button", "")}


#: A retire result's level (`retire_result`) -> the card's.
RETIRE_LEVELS = {"success": "ok", "partial": "warn", "failed": "danger"}


def retire_result_card(ref, host: str, result: dict, plan: dict, targets: dict) -> dict:
    """The retire result card from `preview_confirm.retire_result` (MASKED), the plan it ran
    and `retire.targets_after`'s read-back: what happened and the record, what was DROPPED
    (generated, so gone or going, with when), what is still to remove and how, and, once
    retired, that this address now shows its retired record."""
    target = next((x for x in result.get("targets") or [] if x.get("name") == host), {})
    checks = target.get("checks") or {}
    stopped = next((i for i in (result.get("did_not") or {}).get("items") or []
                    if i.get("kind") == "stopped"), None)
    retired = target.get("outcome") == "retired"
    dropped = ([targets["statement"]] if targets.get("statement") else [])
    dropped += [f"{w['what'][0].upper()}{w['what'][1:]}: {w['how']}"
                for w in plan.get("generated") or []
                if not (w["what"] == "Prometheus's scrape targets" and targets.get("statement"))]
    return {"op": "retire", "state": "result", "host": host, "list": ref.name,
            "level": RETIRE_LEVELS.get(result.get("level"), "danger"), "retired": retired,
            "words": target.get("words", ""),
            "summary": (result.get("happened") or {}).get("summary", ""),
            "done": list((target.get("sent") or {}).get("lines") or []),
            "stopped": (stopped or {}).get("text", ""),
            "remaining": list((stopped or {}).get("lines") or []),
            "basis": " ".join(checks.get("statements") or ([checks["why"]]
                                                           if checks.get("why") else [])),
            # Only once the commit landed (the route reads the targets back only then).
            "dropped": dropped if targets else [],
            "targets_state": targets.get("state", ""),
            "survives": list(plan.get("survives") or []),
            "record": (result.get("record") or {}).get("statement", ""),
            "not_watched": result.get("not_watched", "")}


def restore_job_card(ref, host: str, job_id: str, got, moment: str = "") -> dict:
    """The restore card for its job: running with the pipeline's stepper, its result from the
    receipt (the deploy's own reading of it), or why there is none."""
    c = deploy_job_card(ref, host, job_id, got)
    payload = (got or {}).get("payload") or {}
    moment = moment or payload.get("ref", "")
    c.update(op="restore", moment=moment,
             moment_words="golden now" if moment == "HEAD" else moment)
    if c.get("state") == "deploying":
        c["state"] = "restoring"
    return c


def deploy_job_card(ref, host: str, job_id: str, got) -> dict:
    """The deploy card for its job (`deploy_job.state`, or None): deploying with its stepper,
    its result from the receipt, or why there is none. A failed verify that rolled back
    offers its two ways out (revert intent, retry with a reason)."""
    card = {"op": "deploy", "host": host, "list": ref.name, "job": job_id}
    if got is None:
        return dict(card, state="unknown")
    if got["state"] == "running":
        return dict(card, state="deploying", elapsed_s=got.get("elapsed_s"),
                    steps=job_steps("deploy", ref.name, host))
    if got["state"] == "failed":
        return dict(card, state="failed", error=got.get("error") or "no reason was recorded")
    result = (got.get("payload") or {}).get("result") or {}
    happened = next((x for x in (result.get("happened") or {}).get("targets") or []
                     if x.get("name") == host), {})
    target = next((x for x in result.get("targets") or [] if x.get("name") == host), {})
    sent = target.get("sent") or {}
    checks = target.get("checks") or {}
    rollback = target.get("rollback") or {}
    outcome = happened.get("outcome", "unknown")
    rolled_back = bool(rollback.get("performed"))
    words = happened.get("words", outcome.replace("_", " "))
    # C506 phase 3: each declared move as verify found it, and verify's notes (an adjacency
    # nobody declared beside the expected ones; a declared route change), from the receipt.
    declared_lines = [
        (f"As declared: {m.get('move')}, formed at +{m.get('elapsed', 0):.0f} s"
         if m.get("state") == "formed" else
         f"Declared and not found: {m.get('move')} (within {m.get('window')} s)")
        for m in checks.get("declared_moves") or []] + [
        f"Note: {n}" for n in checks.get("notes") or []]
    # C506 phase 4: how the interfaces were compared, and the settle an unexpected loss got.
    ifs = checks.get("interfaces") or {}
    if ifs.get("compared_by") == "name":
        parts = [f"{', '.join(ifs[k])} {w}" for k, w in (
            ("lost_expected", "down, as the program intends"),
            ("came_up", "came up"),
            ("lost_unexpected", "down, which the program did not touch"))
            if ifs.get(k)]
        declared_lines.append("Interfaces compared by name: "
                              + ("; ".join(parts) if parts else "every one as it was") + ".")
    elif ifs.get("compared_by") == "count":
        declared_lines.append("Interfaces counted, not named: the read named none.")
    settle = checks.get("unexpected_settle") or {}
    if settle:
        declared_lines.append(
            f"An unexpected loss was read again after the {settle.get('seconds')} s settle "
            f"({settle.get('basis', 'its basis not recorded')})"
            + ("; verify failed at once, without the routing protocols' windows."
               if checks.get("failed_at_once") else "."))
    return dict(card, state="result", level=DEPLOY_LEVELS.get(result.get("level"), "danger"),
                outcome=outcome, words=words,
                # The one device, never the batch's "N of N device(s) deployed" (C408).
                summary=f"{host}: {words}.",
                sent=list(sent.get("lines") or []), match_words=sent.get("match_words", ""),
                none=sent.get("none", ""), authorised=list(sent.get("authorised") or []),
                checks=list(checks.get("statements") or ([checks["why"]]
                                                         if checks.get("why") else []))
                + declared_lines,
                rolled_back=rolled_back, rollback_state=rollback.get("state", ""),
                rollback_detail=rollback.get("detail", ""),
                # The save to startup after verify (C511), said once: `saved` here, so the
                # not-saved item is left out of the list below.
                saved=target.get("saved") or {},
                did_not=[i.get("text", "") for i in (result.get("did_not") or {}).get("items")
                         or [] if i.get("target") in (host, "this batch")
                         and i.get("kind") != "not_saved"],
                record=(result.get("record") or {}).get("statement", ""),
                not_watched=result.get("not_watched", ""))
