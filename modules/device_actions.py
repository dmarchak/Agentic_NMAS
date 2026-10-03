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
        gates=gates, failing=failing,
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
