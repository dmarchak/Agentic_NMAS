"""Was this right? on every AI answer, and the review of the answers said wrong (PHASE8_PLAN
16.11 item 1, Decision 5; board FB, `AiFeedback.dc.html`, signed off under the Phase 7 mode
2026-10-28).

**What a person says.** Under every answer the model gave that Mercury draws (Explain, Ask in
words on both builders, an intent change in words, the SDN classification), a verified person
says Yes, or No with what was wrong: one of `KINDS` and a sentence (`words`), masked before it
is kept (`redact.redact_text`) and never sent to a model. One answer per person per call: a
second is refused naming the first.

**What a No becomes.** A candidate recorded case, reviewed on Settings › Installation › AI
("Answers said wrong"): a reviewer (a verified person; every verified person is an admin until
Mercury holds roles, NSOT_AUTHORIZATION section 6) accepts it into a case draft (`draft`), bound
to the draft's hash, or dismisses it with a reason. Mercury writes no case file: the accepted
drafts download as JSON per task, and a maintainer adds one to
`tests/fixtures/ai_cases/<task>/` with its `expect` written. A blind held-out set is never drawn
from these.

**Its effect on checks: stricter only.** It adds cases and loosens nothing: nothing here changes
an answer, a check, the caps or a case already recorded. **It makes no model call**: nothing is
sent to a provider and nothing counts against the caps.

**What is kept.** The records store `ai_feedback` (`records_db.STORES`; the setting
`records_store_ai_feedback`, `file` by default: ``ai_feedback.jsonl`` beside the record of AI
calls, one line per verdict or review, append-only). A verdict keeps the call's id, its task,
the sha256 of the request as it left the host and of the answer as received (both as the record
of AI calls holds them, masked), the call's subject, and the person's masked words; never the
request or the answer themselves, which stay the call's (`calls.find`).
"""
import hashlib
import json
import logging
import time
import uuid

log = logging.getLogger(__name__)

#: The records store (`records_db.STORES`) and its file.
STORE = "ai_feedback"
FILE_NAME = "ai_feedback.jsonl"

YES, NO = "yes", "no"
ACCEPTED, DISMISSED = "accepted", "dismissed"
#: A No's status before and after its review.
TO_REVIEW = "to_review"
#: The kinds of wrong a No names (board FB, state d), each as the form and the review say it.
KINDS = {"conclusion": "the conclusion is wrong",
         "missed": "it missed something that matters",
         "evidence": "it cites the wrong evidence, or none",
         "unhelpful": "right, but not useful"}
#: The longest sentence a No keeps, as the form's maxlength says.
MAX_WORDS = 300
#: The newest rows the review draws before Older… (board FB: "Past 50, the newest 50").
PAGE = 50
#: The features an answer is judged on, in the words the review's filter says them. A call's
#: task is its row's `feature` (`gateway`), so these are the tasks' names.
FEATURES = {"explain": "Explain", "nl_query": "Ask in words",
            "intent_patch": "An intent change in words",
            "sdn_classify": "Classify (an SDN detection)"}
#: The review's status filter, in the board's order.
STATUSES = {TO_REVIEW: "To review", ACCEPTED: "Accepted", DISMISSED: "Dismissed",
            "right": "Said right"}

#: Was this right?'s steps as a press runs them (the manual's page names each).
STEPS = (("person", "only a verified person's press is recorded; a service or an unverified "
                    "request is refused, naming what it is"),
         ("call", "the call is read from the record of AI calls: a call it does not hold, or "
                  "one with no answer, is refused by name"),
         ("once", "under the store's lock, a person who already answered this call is refused, "
                  "naming what they said and when"),
         ("keep", "the verdict is kept with the call's id, its task, the request's and the "
                  "answer's sha256 and the person's words masked; nothing is sent to a model"),
         ("review", "a No waits on Settings › Installation › AI, Answers said wrong, until a "
                    "verified person accepts it into a case draft (bound to the draft's hash) "
                    "or dismisses it with a reason"))


class Refused(Exception):
    """A press or a review that cannot be recorded, its reason said in place."""


def _path() -> str:
    """Beside the record of AI calls: a verdict is a call's, and a folder that holds one record
    holds the other."""
    import os

    from modules.ai import calls
    return os.path.join(os.path.dirname(os.path.abspath(calls._path())), FILE_NAME)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_of(value) -> str:
    """The sha256 of *value* as the record of AI calls holds it: a string's bytes, anything else
    as canonical JSON. ``""`` for nothing held."""
    if value in (None, "", {}, []):
        return ""
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read() -> dict:
    """Every verdict and review, oldest first: ``{"state", "rows", "error"}``; unreadable is
    said, never read as nothing."""
    from modules import records_migrate

    got = records_migrate.store_rows(STORE, _path(), skip_unparsable=True)
    if got["state"] == "unreadable":
        log.error("ai feedback: the store is unreadable (%s)", got["error"])
    return got


def person() -> tuple:
    """``(actor, verified, "")`` when this request is a verified person's, else
    ``("", "", why not)``, naming what it is."""
    from modules import identity

    ident = identity.verified_identity()
    if ident is None:
        return "", "", "recorded only as a verified person: this request is not verified"
    if ident.kind != "person":
        return "", "", (f"recorded only as a verified person: this request is a "
                        f"{ident.kind or 'requester of unknown kind'} ({ident.actor})")
    actor = identity.request_actor()
    return actor, identity.actor_verification(actor), ""


def _verdicts(rows: list) -> list:
    return [r for r in rows if r.get("kind") == "verdict"]


def _reviews(rows: list) -> dict:
    """``{verdict id: its review}`` (the first; a later one is never kept)."""
    out = {}
    for r in rows:
        if r.get("kind") == "review" and r.get("of") and r["of"] not in out:
            out[r["of"]] = r
    return out


def mine(call_id: str, actor: str, rows: list):
    """*actor*'s verdict on *call_id*, or None."""
    return next((r for r in _verdicts(rows)
                 if r.get("call_id") == call_id and r.get("actor") == actor), None)


def control(call_id: str) -> dict:
    """What the control under an answer draws for the viewer: ``{"call_id", "mine", "why",
    "error"}``. *mine* is the viewer's verdict when they gave one (the control then shows it,
    never the buttons); *why* why the viewer cannot record (not a verified person); *error*
    why the store cannot be read."""
    actor, _verified, why = person()
    out = {"call_id": call_id, "mine": None, "why": why, "error": "",
           "kinds": KINDS, "max_words": MAX_WORDS}
    if why or not call_id:
        return out
    got = read()
    if got["state"] == "unreadable":
        return dict(out, error=f"the answers said right or wrong cannot be read "
                               f"({got['error']}), so whether you answered already is not known")
    return dict(out, mine=_as_drawn(mine(call_id, actor, got["rows"]), CONTROL_DRAWS))


#: What each view draws of a verdict: a screen is handed only what it draws (CLAUDE.md,
#: "Every carried field is drawn").
CONTROL_DRAWS = ("call_id", "verdict", "kind_words", "words", "actor", "at")
ROW_DRAWS = ("id", "task", "feature_words", "verdict", "kind_words", "words", "actor", "at")
DETAIL_DRAWS = ROW_DRAWS + ("call_id", "model", "prompt", "subject", "request_sha256",
                            "answer_sha256")
REVIEW_DRAWS = ("outcome", "actor", "at", "reason", "draft_sha256")


def _as_drawn(row, keys=None):
    """*row* with its kind of wrong in words and its task's name, as *keys* (all, by default)."""
    if not row:
        return None
    full = dict(row, kind_words=KINDS.get(row.get("why", ""), ""),
                feature_words=FEATURES.get(row.get("task"), row.get("task") or "a task"))
    return {k: full.get(k, "") for k in keys} if keys else full


def _call(call_id: str) -> dict:
    """The call's row from the record of AI calls, or Refused naming why not."""
    from modules.ai import calls

    found = calls.find(call_id)
    if found["state"] == "unreadable":
        raise Refused(f"the record of AI calls cannot be read ({found['error']})")
    row = found["row"]
    if not row:
        raise Refused(f"call {call_id} is not in the record of AI calls")
    if row.get("joined"):
        # A press that joined another's call: its answer is that call's (C1854).
        return _call(row["joined"])
    if not row.get("response") and not row.get("output"):
        raise Refused(f"call {call_id} has no answer to judge (its verdict: "
                      f"{row.get('verdict') or 'none'})")
    return row


def say(call_id: str, verdict: str, *, why: str = "", words: str = "") -> dict:
    """Record the viewer's *verdict* (`YES` or `NO`) on *call_id*. A No names one of `KINDS`
    (*why*) and a sentence (*words*, masked, at most `MAX_WORDS`). Returns the kept row;
    Refused naming why when it cannot be kept."""
    from modules import records_migrate, redact
    from modules.filestore import PathLock
    from modules.nsot import authorisation

    actor, verified, refused = person()
    if refused:
        raise Refused(refused)
    if verdict not in (YES, NO):
        raise Refused(f"{verdict!r} is neither yes nor no")
    words = " ".join(str(words or "").split())
    if verdict == NO:
        if why not in KINDS:
            raise Refused("say what was wrong: one of " + "; ".join(KINDS.values()))
        if len(words) > MAX_WORDS:
            raise Refused(f"the sentence is {len(words)} characters; at most {MAX_WORDS}")
        if len(words.split()) < authorisation.MIN_WORDS or len(words) < authorisation.MIN_CHARS:
            raise Refused("say in a sentence what the right answer would have said (a few "
                          "words at least)")
    else:
        why, words = "", ""
    call = _call(call_id)
    row = {"kind": "verdict", "id": "fb-" + uuid.uuid4().hex[:12], "call_id": call["id"],
           "task": call.get("feature", ""), "model": call.get("model", ""),
           "prompt": call.get("prompt", ""), "subject": call.get("subject") or {},
           "request_sha256": sha256_of(call.get("request")),
           "answer_sha256": sha256_of(call.get("response") or call.get("output")),
           "verdict": verdict, "why": why, "words": redact.redact_text(words) if words else "",
           "actor": actor, "verified": verified, "at": _now()}
    with PathLock(_path()):
        got = read()
        if got["state"] == "unreadable":
            raise Refused(f"the answers said right or wrong cannot be read ({got['error']}), so "
                          "whether you answered already is not known; nothing was recorded")
        before = mine(call["id"], actor, got["rows"])
        if before:
            said = "right" if before.get("verdict") == YES else "wrong"
            raise Refused(f"you said {said} for call {call['id']} at {before.get('at')}; one "
                          "answer per person per call")
        try:
            records_migrate.store_append(STORE, _path(), row)
        except Exception as exc:                                    # noqa: BLE001
            log.error("ai feedback: COULD NOT KEEP %s's verdict on %s (%s)", actor,
                      call["id"], exc)
            raise Refused(f"it could not be kept ({type(exc).__name__}: {exc})"[:300]) from exc
    log.info("ai feedback: %s said %s for %s (%s)", actor, verdict, call["id"], row["task"])
    return _as_drawn(row)


# ── the review ────────────────────────────────────────────────────────────────────────────


def status_of(verdict: dict, reviews: dict) -> str:
    if verdict.get("verdict") == YES:
        return "right"
    review = reviews.get(verdict.get("id"))
    return review.get("outcome") if review else TO_REVIEW


def view(status: str = TO_REVIEW, feature: str = "", q: str = "", older: int = 0) -> dict:
    """The review card: ``{"state", "error", "counts", "rows", "shown", "matched", "older",
    "status", "feature", "q", "features", "statuses"}``. *counts* are every feature's, by
    status; *rows* the verdicts with *status* (of *feature*, matching *q* in the call's id, the
    person or the words), newest first, `PAGE` from *older*. Reads the store once and no call."""
    status = status if status in STATUSES or status == "all" else TO_REVIEW
    feature = feature if feature in FEATURES else ""
    q = " ".join(str(q or "").split())[:100]
    try:
        older = max(int(older or 0), 0)
    except (TypeError, ValueError):
        older = 0
    out = {"state": "ok", "error": "", "counts": {k: 0 for k in STATUSES}, "rows": [],
           "matched": 0, "older": older, "next": 0, "status": status, "feature": feature,
           "q": q, "features": FEATURES, "statuses": STATUSES}
    got = read()
    if got["state"] == "unreadable":
        return dict(out, state="unreadable", error=got["error"])
    reviews = _reviews(got["rows"])
    verdicts = list(reversed(_verdicts(got["rows"])))
    for v in verdicts:
        out["counts"][status_of(v, reviews)] += 1
    needle = q.lower()
    picked = [v for v in verdicts
              if (status == "all" or status_of(v, reviews) == status)
              and (not feature or v.get("task") == feature)
              and (not needle or needle in " ".join((v.get("call_id", ""), v.get("actor", ""),
                                                      v.get("words", ""))).lower())]
    out["matched"] = len(picked)
    page = picked[older:older + PAGE]
    out["next"] = older + PAGE if older + PAGE < len(picked) else 0
    out["rows"] = [dict(_as_drawn(v, ROW_DRAWS), status=status_of(v, reviews)) for v in page]
    out["judged"] = len(verdicts)
    return out


def draft(verdict: dict) -> dict:
    """The case draft a No becomes when accepted: the call, the hashes, the subject and the
    person's words as the case's `flag`; its `expect` left for a maintainer (the case is judged
    only once it is written). Made from what the verdict kept, so it never holds the request or
    the answer, which stay the call's; nor who said it, since a case file is published with the
    repository (the review names who)."""
    words = verdict.get("words", "")
    flag = KINDS.get(verdict.get("why", ""), "")
    return {"name": f"feedback-{verdict.get('id', '')}", "from_call": verdict.get("call_id", ""),
            "task": verdict.get("task", ""), "model": verdict.get("model", ""),
            "prompt": verdict.get("prompt", ""), "subject": verdict.get("subject") or {},
            "request_sha256": verdict.get("request_sha256", ""),
            "answer_sha256": verdict.get("answer_sha256", ""),
            "flag": f"{flag}: {words}" if flag else words, "expect": None}


def draft_text(verdict: dict) -> str:
    return json.dumps(draft(verdict), indent=1, sort_keys=True)


def draft_hash(verdict: dict) -> str:
    return sha256_of(json.dumps(draft(verdict), sort_keys=True))


def detail(fb_id: str) -> dict:
    """One verdict opened in the review: ``{"ok", "error", "v", "call", "received", "others",
    "draft", "draft_hash"}``. *call* is the call's row from the record of AI calls (None when it
    no longer holds it: the review then shows what the verdict kept, Accept off); *received*
    the answer as received, masked (the record's `response`, masked again on the way out)."""
    from modules import redact

    got = read()
    if got["state"] == "unreadable":
        return {"ok": False, "error": f"the answers said right or wrong cannot be read "
                                      f"({got['error']})"}
    v = next((r for r in _verdicts(got["rows"]) if r.get("id") == fb_id), None)
    if not v:
        return {"ok": False, "error": f"{fb_id} is not an answer said right or wrong"}
    reviews = _reviews(got["rows"])
    call, call_error = None, ""
    try:
        call = _call(v["call_id"])
    except Refused as exc:
        call_error = str(exc)
    received = ""
    if call:
        raw = call.get("response") or json.dumps(call.get("output") or {}, sort_keys=True)
        try:
            raw = json.dumps(json.loads(raw), indent=1, sort_keys=True)
        except (TypeError, ValueError):
            pass
        received = redact.redact_text(raw)
    others = [{"actor": r.get("actor", ""), "verdict": r.get("verdict", ""),
               "words": r.get("words", ""), "said": "right" if r.get("verdict") == YES else "wrong"}
              for r in _verdicts(got["rows"])
              if r.get("call_id") == v["call_id"] and r.get("id") != fb_id]
    review_row = reviews.get(fb_id)
    return {"ok": True, "error": "",
            "v": dict(_as_drawn(v, DETAIL_DRAWS), status=status_of(v, reviews),
                      review=_as_drawn(review_row, REVIEW_DRAWS) if review_row else None),
            # Of the call, only who asked and when: the rest is History's (its link).
            "call": {"actor": call.get("actor", ""), "at": call.get("at", "")} if call else None,
            "call_error": call_error, "received": received, "others": others,
            "draft": draft_text(v), "draft_hash": draft_hash(v),
            "accepted_of_task": sum(1 for r in _verdicts(got["rows"])
                                    if r.get("task") == v.get("task")
                                    and status_of(r, reviews) == ACCEPTED)}


def review(fb_id: str, outcome: str, *, reason: str = "", draft_seen: str = "") -> dict:
    """A reviewer settles the No *fb_id*: `ACCEPTED` into its case draft (bound to
    *draft_seen*, the draft's hash as drawn, and refused while its call cannot be read) or
    `DISMISSED` with a *reason*. Returns the review row; Refused naming why not, a No settled
    first by another reviewer among them, naming who and how."""
    from modules import records_migrate, redact
    from modules.filestore import PathLock
    from modules.nsot import authorisation

    actor, verified, refused = person()
    if refused:
        raise Refused(refused)
    if outcome not in (ACCEPTED, DISMISSED):
        raise Refused(f"{outcome!r} is neither accepted nor dismissed")
    reason = " ".join(str(reason or "").split())
    if outcome == DISMISSED and (len(reason.split()) < authorisation.MIN_WORDS
                                 or len(reason) < authorisation.MIN_CHARS):
        raise Refused("say why it is not a case (a few words at least): it is recorded with "
                      "your name")
    with PathLock(_path()):
        got = read()
        if got["state"] == "unreadable":
            raise Refused(f"the answers said right or wrong cannot be read ({got['error']})")
        v = next((r for r in _verdicts(got["rows"]) if r.get("id") == fb_id), None)
        if not v or v.get("verdict") != NO:
            raise Refused(f"{fb_id} is not an answer said wrong")
        settled = _reviews(got["rows"]).get(fb_id)
        if settled:
            raise Refused(f"{settled.get('actor')} {settled.get('outcome')} it at "
                          f"{settled.get('at')}; it is settled")
        row = {"kind": "review", "of": fb_id, "outcome": outcome, "actor": actor,
               "verified": verified, "at": _now(), "reason": redact.redact_text(reason)}
        if outcome == ACCEPTED:
            _call(v["call_id"])          # the call must still be read; Refused names why not
            now = draft_hash(v)
            if draft_seen != now:
                raise Refused(f"the draft drawn ({draft_seen[:12] or 'none'}) is not the draft "
                              f"now ({now[:12]}); open the row again and read it")
            row["draft_sha256"] = now
        try:
            records_migrate.store_append(STORE, _path(), row)
        except Exception as exc:                                    # noqa: BLE001
            log.error("ai feedback: COULD NOT KEEP %s's review of %s (%s)", actor, fb_id, exc)
            raise Refused(f"it could not be kept ({type(exc).__name__}: {exc})"[:300]) from exc
    log.info("ai feedback: %s %s %s", actor, outcome, fb_id)
    return row


def drafts(task: str) -> dict:
    """``{"state", "error", "task", "drafts"}``: every accepted No of *task* as its case draft,
    oldest first: what a maintainer adds to the task's case file, each with its `expect`
    written."""
    got = read()
    if got["state"] == "unreadable":
        return {"state": "unreadable", "error": got["error"], "task": task, "drafts": []}
    reviews = _reviews(got["rows"])
    return {"state": "ok", "error": "", "task": task,
            "drafts": [draft(v) for v in _verdicts(got["rows"])
                       if v.get("task") == task and status_of(v, reviews) == ACCEPTED]}
