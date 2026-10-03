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
                next=nxt.get("text", ""), export=nxt.get("open") == "breakglass_export")


# ---------------------------------------------------------------------------
# Deploy, with Mode B (7.3; the device-actions canvas, boards 5 and 6): the device's whole
# committed intent, merge-only, with a dangerous line's stated reason and the residue a person
# ticks for removal, each reason in the hash; run as a job (`deploy_job`), its stepper the
# pipeline's stages; the result from the receipt the apply wrote.
# ---------------------------------------------------------------------------

def deploy_card(ref, host: str, entry: dict, preview: dict, viewer: dict, *,
                reasons=None, danger_reasons=None) -> dict:
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
    return {"op": "deploy", "state": "preview", "host": host, "list": ref.name,
            "summary": (preview.get("what") or {}).get("summary", ""),
            "sent": lines, "none": program.get("none", ""),
            "notes": [{"title": n.get("title", ""), "lines": list(n.get("lines") or [])}
                      for n in program.get("notes") or []],
            "dangerous": dangerous, "residue": residue,
            "waiting": waiting, "authorisation_error": entry.get("authorisation_error", ""),
            "blocking": blocking, "refused": refused,
            "what_not": t["what_not"], "operands": list(t["target"].get("operands") or []),
            "gates": t["gates"], "failing": t["failing"], "may": may,
            "held": held(t["gates"]),
            "effect": confirm.get("effect", ""),
            "confirm": ({"capture_hash": entry.get("capture_hash", ""),
                         "command_hash": entry.get("command_hash", ""),
                         "remove": list(removals.get("ids") or []),
                         "authorise": list(entry.get("authorised") or [])} if may else None),
            "command_hash": entry.get("command_hash", "")}


#: A deploy's outcome -> the card's level.
DEPLOY_LEVELS = {"success": "ok", "partial": "warn", "failed": "danger", "nothing": "warn"}


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
    return dict(card, state="result", level=DEPLOY_LEVELS.get(result.get("level"), "danger"),
                outcome=outcome, words=happened.get("words", outcome.replace("_", " ")),
                summary=(result.get("happened") or {}).get("summary", ""),
                sent=list(sent.get("lines") or []), match_words=sent.get("match_words", ""),
                none=sent.get("none", ""), authorised=list(sent.get("authorised") or []),
                checks=list(checks.get("statements") or ([checks["why"]]
                                                         if checks.get("why") else [])),
                rolled_back=rolled_back, rollback_state=rollback.get("state", ""),
                rollback_detail=rollback.get("detail", ""),
                did_not=[i.get("text", "") for i in (result.get("did_not") or {}).get("items")
                         or [] if i.get("target") in (host, "this batch")],
                record=(result.get("record") or {}).get("statement", ""),
                not_watched=result.get("not_watched", ""))
