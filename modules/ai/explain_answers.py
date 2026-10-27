"""Explain's answers, kept with their frozen packs (C1853; the operator's Walk 2, 2026-10-27:
an answer kept only in the record of AI calls was lost to a page refresh, and pressing Explain
again paid for it again).

**What is kept.** Each answer the model gave for a pack: the answer as drawn (the rationale and
hypotheses or no fault found, each citation resolved; or "the pack cannot say"; or "couldn't
analyse" naming why), the call's id and cost, who pressed and when, keyed by **the pack's hash,
the prompt version and the model** (`key_of`): a pack is frozen, so the same three ask the same
question of the same model. A refusal before anything was answered (hosted AI off, a cap, the
provider down, the pack changed) is not an answer and is not kept: pressing again is right.

**Where.** The records store `explain_answers` (`records_db.STORES`, the setting
`records_store_explain_answers`, `file` by default: ``explain_answers.jsonl`` in the data
folder, one line per answer, append-only). Not in the pack's own store: a pack is hashed when it
is built and never written again.

**How it is used** (`press`, the route's one call):

- the pack's card draws its newest kept answer when it opens (`kept`): reopening the alert, a
  reload, or History's link to the call shows it, and nothing is sent;
- **Explain** on a pack that has one returns it, and sends nothing (a page drawn before the
  answer was kept still offers Explain);
- **Explain again** (``again``) is a new call, said on the button with its cost; its answer is
  kept beside the first, which stays (the newest is drawn, the count of earlier ones beside it).

An answers store that cannot be read refuses a plain Explain, naming why: whether the pack was
explained already is not known, and guessing "not" would pay again. Explain again still asks.
"""
import logging
import time

log = logging.getLogger(__name__)

#: The records store (`records_db.STORES`) and its file.
STORE = "explain_answers"
FILE_NAME = "explain_answers.jsonl"
#: The results that are the model's answer, by their error kind ("" an answer drawn).
ANSWERED = ("", "unanswerable", "couldnt_analyse")


def _steps() -> tuple:
    """Explain's steps as a press runs them (the manual's page names each): explain's own,
    with the kept answer read first and the new one kept before it is shown."""
    from modules.ai import explain

    own = dict(explain.STEPS)
    return (("pack", own["pack"]),
            ("kept", "an answer kept with this pack (by its hash, the prompt version and the "
                     "model) is drawn, and nothing is sent; only Explain again asks anew"),
            ("topology", own["topology"]), ("ask", own["ask"]), ("check", own["check"]),
            ("keep", "the model's answer kept with the pack, beside any earlier one, so "
                     "reopening the alert draws it with no new call"),
            ("show", own["show"]))


#: Explain's steps, for the manual (modules/manual.py, "alert-explain").
STEPS = _steps()


def _path() -> str:
    """Beside the record of AI calls (the data folder's `ai_calls.jsonl`): an answer is a
    call's, and a folder that holds one record holds the other."""
    import os

    from modules.ai import calls
    return os.path.join(os.path.dirname(os.path.abspath(calls._path())), FILE_NAME)


def key_of(pack: dict, prompt: tuple = None) -> dict:
    """``{"pack_hash", "prompt", "model"}``: what an answer is kept under."""
    from modules.ai import explain, profiles

    name, version = prompt or explain.PROMPT
    return {"pack_hash": pack.get("hash") or "", "prompt": f"{name}.v{version}",
            "model": profiles.TASKS[explain.FEATURE]["model"]}


def read() -> dict:
    """Every kept answer, oldest first: ``{"state", "rows", "error"}``; unreadable is said."""
    from modules import records_migrate

    got = records_migrate.store_rows(STORE, _path(), skip_unparsable=True)
    if got["state"] == "unreadable":
        log.error("explain answers: the store is unreadable (%s)", got["error"])
    return got


def kept(pack: dict, rows: list = None) -> dict:
    """``{"state", "answer", "earlier", "error"}``: the newest answer kept for *pack* under
    today's prompt and model, and how many earlier ones are kept beside it; None when there is
    none. A pack that is not intact has none: its hash no longer names what is drawn."""
    from modules import evidence_pack as EP

    if rows is None:
        got = read()
        if got["state"] == "unreadable":
            return {"state": "unreadable", "answer": None, "earlier": 0, "error": got["error"]}
        rows = got["rows"]
    if not pack or not EP.intact(pack):
        return {"state": "ok", "answer": None, "earlier": 0, "error": ""}
    key = key_of(pack)
    mine = [r for r in rows if all(r.get(k) == v for k, v in key.items())]
    return {"state": "ok", "answer": mine[-1] if mine else None,
            "earlier": max(len(mine) - 1, 0), "error": ""}


def keep(pack: dict, result: dict, actor: str) -> dict:
    """Keep *result* (`explain.explain_pack`'s) with *pack* when it is the model's answer:
    ``{"kept": bool, "error"}``. A call already kept (a joined press, C1854) is not kept
    twice. Never raises: a failure is logged and said."""
    if not result.get("call_id") or (result.get("error") or "") not in ANSWERED:
        return {"kept": False, "error": ""}
    from modules import records_migrate
    from modules.filestore import PathLock

    row = dict(key_of(pack), pack_id=pack.get("id") or "", call_id=result["call_id"],
               cost_usd=float(result.get("cost_usd") or 0.0), actor=actor,
               at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               result={k: v for k, v in result.items() if k not in ("kept", "recorded")})
    try:
        # The read and the append under the store's own lock, so two presses joined on one call
        # keep it once (PathLock is re-entrant: store_append takes it again).
        with PathLock(_path()):
            got = read()
            if got["state"] == "unreadable":
                raise RuntimeError(got["error"])
            if any(r.get("call_id") == row["call_id"] for r in got["rows"]):
                return {"kept": True, "error": ""}
            records_migrate.store_append(STORE, _path(), row)
    except Exception as exc:                                    # noqa: BLE001
        log.error("explain answers: COULD NOT KEEP the answer of %s for %s (%s)",
                  row["call_id"], row["pack_id"], exc)
        return {"kept": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"kept": True, "error": ""}


def as_drawn(kept_answer: dict, earlier: int = 0, fresh: bool = False) -> dict:
    """A kept answer as `_explain.html` draws it: its result, and when, by whom and that it
    was kept (``kept``)."""
    return dict(kept_answer.get("result") or {},
                kept={"at": kept_answer.get("at", ""), "actor": kept_answer.get("actor", ""),
                      "earlier": earlier, "call_id": kept_answer.get("call_id", ""),
                      "fresh": fresh})


def press(pack_id: str, *, actor: str, trigger: dict, again: bool = False, send=None,
          today: str = None) -> dict:
    """Explain pressed on *pack_id*: its kept answer when it has one and *again* is not
    asked (nothing sent), else one call (`explain.explain_pack`), its answer kept. The result
    is `explain_pack`'s, with ``kept`` (a kept answer's when, who and earlier count) and
    ``keep_error`` (why a new answer could not be kept)."""
    from modules import evidence_pack as EP
    from modules.ai import explain

    pack, state, _error = EP.find(pack_id)
    if pack is None or not EP.intact(pack):
        # Not kept or changed since built: explain says which, and sends nothing.
        return explain.explain(pack_id, actor=actor, trigger=trigger, send=send, today=today)
    if not again:
        have = kept(pack)
        if have["state"] == "unreadable":
            return {"ok": False, "error": "answers_unreadable", "pack_id": pack_id,
                    "detail": f"the kept Explain answers cannot be read ({have['error']}), so "
                              "whether this pack was explained already is not known; nothing "
                              "was sent (Explain again asks anyway)"}
        if have["answer"]:
            log.info("explain answers: %s opened the kept answer %s for %s; nothing sent",
                     actor, have["answer"].get("call_id"), pack_id)
            return as_drawn(have["answer"], have["earlier"])
    got = explain.explain_pack(pack, actor=actor, trigger=trigger, send=send, today=today)
    saved = keep(pack, got, actor)
    if saved["kept"]:
        have = kept(pack)
        return as_drawn(have["answer"], have["earlier"], fresh=True) if have["answer"] else got
    return dict(got, keep_error=saved["error"])
