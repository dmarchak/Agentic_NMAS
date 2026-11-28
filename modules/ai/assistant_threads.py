"""The toolbar assistant's conversations, kept server-side per person (stage 2; docs/design/assistant.md,
"Persistent across pages"; the chat, the operator's order of 2026-11-28): a page change or a
refresh draws the same exchanges, and nothing is asked again.

**The store.** One JSON-lines file per person, ``assistant_threads/<key>.jsonl`` in the data
directory, owner-only (written whole through `filestore.write_atomic`, 0600, under the file's
own lock), holding that person's current conversation, its newest `KEEP` exchanges, oldest
first. The file is named by a digest of the person's identity (`key_of`), never by the identity
itself, so a listing of the folder names nobody.

**Past conversations** (the chat): New conversation moves the current file, as it is, into the
person's ``<key>.past/`` folder, named by when it was put aside and a random part
(``20261128T002100Z-1a2b3c4d.jsonl``), and the next question starts a new one; reopening a past
conversation moves the current one aside the same way and moves that one back as the current.
Nothing is deleted. **Expand, then contract:** the current conversation's file, its name and its
row shape are the ones the release before the chat reads; the past folder, the turns file and
the rows' new fields (``turn``, ``page``, ``took_s``) are additions it never reads, so a
rollback draws the current conversation as it is.

**A turn** (the chat's press of Send, run as a job: `assistant_turns`) is kept while it runs in
``<key>.turns.json``: its id, the question as it left, what the panel was looking at and the
page it was asked on, its steps, a stop if the person pressed Stop, and the job's last sign of
life. Its end moves it into the conversation as an exchange (`finish`); a turn whose job shows
no sign of life for `LOST_S` is drawn as lost, never as working for ever.

**What an exchange holds.** When it was asked, the question as it left (masked by
`redact.redact_typed`, as the manual's gap record holds it), what the panel was looking at
(the head's words), the page it was asked on (its path and query), and the answer as the panel
drew it, its words masked again by `redact.redact_text` on the way in: never a value the mask
removed, never a read's answer (those stay in the send log's digests and History › Reads).

**Only a verified person has a conversation.** A request whose actor is not verified keeps and
reads nothing. An unreadable file is said, never read as an empty conversation; the next
exchange kept copies it aside first (`filestore.preserve_corrupt`), then starts it again.
"""
import hashlib
import json
import logging
import os
import re
import secrets
import time

log = logging.getLogger(__name__)

#: The folder in the data directory, and the exchanges kept for each conversation (the newest).
FOLDER = "assistant_threads"
KEEP = 20
#: The past conversations a panel lists (the newest); every one stays on the host.
PAST_SHOWN = 30
#: A turn whose job showed no sign of life for this long is lost (its process ended): the
#: adapter's 235 s without a sign of life (`gateway.send_bound_s`) and a round of reads, which
#: signs of life do not cover, about 2.5 times the 235 s. Derived from that bound, not measured.
LOST_S = 600
#: How often a running turn's sign of life is written while its call streams.
ALIVE_EVERY_S = 15
#: A past conversation's id: when it was put aside and a random part.
PAST_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{8}")
#: A turn's id.
TURN_ID = re.compile(r"t-[0-9a-f]{16}")


def key_of(actor: str) -> str:
    """The file's name for *actor*: a digest, so the folder names nobody."""
    return hashlib.sha256(("assistant-thread:" + str(actor)).encode("utf-8")).hexdigest()[:32]


def _dir() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, FOLDER)


def path_of(actor: str) -> str:
    return os.path.join(_dir(), key_of(actor) + ".jsonl")


def past_dir(actor: str) -> str:
    return os.path.join(_dir(), key_of(actor) + ".past")


def turns_path(actor: str) -> str:
    return os.path.join(_dir(), key_of(actor) + ".turns.json")


def _person(actor: str) -> bool:
    from modules import identity
    return bool(actor) and actor != identity.UNVERIFIED


def _rows_of(path: str) -> list:
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return [r for r in rows if isinstance(r, dict)]


def read(actor: str) -> dict:
    """``{"state", "error", "rows"}``: *actor*'s current conversation, oldest first. *state*
    ``ok``, ``none`` (no verified person: nothing is kept) or ``unreadable`` (said, never read
    as none)."""
    if not _person(actor):
        return {"state": "none", "error": "", "rows": []}
    path = path_of(actor)
    if not os.path.exists(path):
        return {"state": "ok", "error": "", "rows": []}
    try:
        rows = _rows_of(path)
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "error": type(exc).__name__, "rows": []}
    return {"state": "ok", "error": "", "rows": rows[-KEEP:]}


def _masked(value):
    from modules import redact

    if isinstance(value, str):
        return redact.redact_text(value)
    if isinstance(value, list):
        return [_masked(v) for v in value]
    if isinstance(value, dict):
        return {k: _masked(v) for k, v in value.items()}
    return value


def _stamp(now: float = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now))


def _question(question) -> str:
    from modules import redact
    return redact.redact_typed(" ".join(str(question or "").split()))[:600]


def keep(actor: str, question: str, looking_at: str, got: dict, now: float = None, *,
         page: str = "", turn: str = "", took_s: float = None, at: str = "") -> dict:
    """Keep one exchange in *actor*'s current conversation, the newest `KEEP` kept: ``{"ok",
    "error"}``. The question masked as it left, the answer's words masked again; *page* the
    page it was asked on (its path and query), *turn* the press's id, *took_s* how long its
    answer took, *at* when it was asked (else now); nothing kept for a request with no verified
    person."""
    from modules.filestore import PathLock, preserve_corrupt, write_atomic

    if not _person(actor):
        return {"ok": False, "error": "no verified person: nothing is kept"}
    row = {"at": at or _stamp(now), "question": _question(question),
           "looking_at": str(looking_at or "")[:200], "got": _masked(dict(got or {}))}
    if page:
        row["page"] = str(page)[:600]
    if turn:
        row["turn"] = turn
    if took_s is not None:
        row["took_s"] = round(float(took_s), 1)
    path = path_of(actor)
    try:
        os.makedirs(_dir(), mode=0o700, exist_ok=True)
        with PathLock(path):
            got_ = read(actor)
            if got_["state"] == "unreadable":
                preserve_corrupt(path, f"the assistant's thread is unreadable ({got_['error']})")
                rows = []
            else:
                rows = got_["rows"]
            rows = (rows + [row])[-KEEP:]
            write_atomic(path, "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    except OSError as exc:
        log.error("assistant: the thread could not be kept: %s", exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"ok": True, "error": ""}


# ── past conversations ───────────────────────────────────────────────────────────────────────

def _aside(actor: str, now: float = None) -> str:
    """Move the current conversation, when it holds an exchange, into the past folder; the id
    it is kept under, or "" when there was nothing to move. Under the caller's lock."""
    path = path_of(actor)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return ""
    os.makedirs(past_dir(actor), mode=0o700, exist_ok=True)
    pid = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(time.time() if now is None else now)) \
        + "-" + secrets.token_hex(4)
    os.replace(path, os.path.join(past_dir(actor), pid + ".jsonl"))
    return pid


def _busy(actor: str, now: float = None) -> str:
    """Why the conversation cannot be put aside now: a turn still working, or ""."""
    working = [t for t in _turns(actor).values() if _turn_state(t, now) in BUSY]
    if working:
        return ("a question is still being answered in this conversation: press Stop, or wait "
                "for its answer, then start another")
    return ""


def new(actor: str, now: float = None) -> dict:
    """New conversation: the current one kept in the past folder, as it is, and the next
    question starts another. ``{"ok", "error", "kept"}``, *kept* the past id ("" when the
    current one was empty)."""
    from modules.filestore import PathLock

    if not _person(actor):
        return {"ok": False, "error": "no verified person: nothing is kept", "kept": ""}
    try:
        os.makedirs(_dir(), mode=0o700, exist_ok=True)
        with PathLock(path_of(actor)):
            settle_lost(actor, now)
            why = _busy(actor, now)
            if why:
                return {"ok": False, "error": why, "kept": ""}
            return {"ok": True, "error": "", "kept": _aside(actor, now)}
    except OSError as exc:
        log.error("assistant: a new conversation could not be started: %s", exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200], "kept": ""}


def reopen(actor: str, past_id: str, now: float = None) -> dict:
    """A past conversation made the current one again, the current one kept in the past
    folder in its place. ``{"ok", "error"}``; a past id that is not one of *actor*'s is
    refused by name."""
    from modules.filestore import PathLock

    if not _person(actor):
        return {"ok": False, "error": "no verified person: nothing is kept"}
    if not PAST_ID.fullmatch(str(past_id or "")):
        return {"ok": False, "error": f"{str(past_id)[:40]!r} is not a past conversation's id"}
    src = os.path.join(past_dir(actor), past_id + ".jsonl")
    try:
        with PathLock(path_of(actor)):
            if not os.path.exists(src):
                return {"ok": False, "error": f"no past conversation {past_id} is kept for you"}
            settle_lost(actor, now)
            why = _busy(actor, now)
            if why:
                return {"ok": False, "error": why}
            _aside(actor, now)
            os.replace(src, path_of(actor))
    except OSError as exc:
        log.error("assistant: a past conversation could not be reopened: %s", exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"ok": True, "error": ""}


def past(actor: str, limit: int = PAST_SHOWN) -> dict:
    """*actor*'s past conversations, newest first: ``{"state", "rows", "total"}``, each row
    ``{"id", "first", "at", "count"}`` (its first question, when it was asked and how many
    exchanges it holds); one that cannot be read is listed as such, never left out."""
    if not _person(actor):
        return {"state": "none", "rows": [], "total": 0}
    folder = past_dir(actor)
    try:
        names = sorted((n[:-6] for n in os.listdir(folder)
                        if n.endswith(".jsonl") and PAST_ID.fullmatch(n[:-6])), reverse=True)
    except FileNotFoundError:
        return {"state": "ok", "rows": [], "total": 0}
    except OSError as exc:
        return {"state": "unreadable", "rows": [], "total": 0, "error": type(exc).__name__}
    rows = []
    for pid in names[:limit]:
        try:
            got = _rows_of(os.path.join(folder, pid + ".jsonl"))
        except (OSError, ValueError) as exc:
            rows.append({"id": pid, "first": "", "at": "", "count": 0,
                         "error": type(exc).__name__})
            continue
        first = got[0] if got else {}
        rows.append({"id": pid, "first": str(first.get("question") or "")[:120],
                     "at": str(first.get("at") or ""), "count": len(got)})
    return {"state": "ok", "rows": rows, "total": len(names)}


# ── a turn while it runs (assistant_turns) ───────────────────────────────────────────────────

def _turns(actor: str) -> dict:
    try:
        with open(turns_path(actor), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in got.items() if isinstance(v, dict)} if isinstance(got, dict) else {}


def _write_turns(actor: str, turns: dict) -> None:
    from modules.filestore import write_atomic
    if turns:
        write_atomic(turns_path(actor), json.dumps(turns, sort_keys=True))
    elif os.path.exists(turns_path(actor)):
        os.remove(turns_path(actor))


#: The states in which a turn's job may still make a call: one at a time per person, so Send,
#: New conversation and a reopen wait for both (the review of 2026-11-28: Stop then Send ran two
#: jobs at once, and a New conversation while stopping took the stopped exchange with it).
BUSY = ("working", "stopping")


def _turn_state(t: dict, now: float = None) -> str:
    """``working``, ``stopping`` (Stop pressed, its job not yet ended), ``lost`` or ``ended``
    (its job ended but its exchange could not be kept: no longer working, kept by the next
    press, `settle_lost`)."""
    if t.get("ended"):
        return "ended"
    now = time.time() if now is None else now
    if now - float(t.get("alive") or t.get("started") or 0) > LOST_S:
        return "lost"
    return "stopping" if t.get("stop_at") else "working"


LOST_WORDS = ("No answer arrived: its job showed no sign of life for {m} minutes (Mercury may "
              "have restarted). Any call it made is recorded in History")


def settle_lost(actor: str, now: float = None) -> None:
    """Each of *actor*'s lost turns kept in the conversation as lost, said, and let go; and each
    turn whose job ended but whose exchange could not be kept, kept now (else left ended, to be
    tried again): run by a press (Send, New conversation, a reopen), never by a read."""
    for k, t in list(_turns(actor).items()):
        state = _turn_state(t, now)
        if state == "lost":
            finish(actor, k, {"state": "lost", "detail": LOST_WORDS.format(m=LOST_S // 60)})
        elif state == "ended":
            got = {key: v for key, v in dict(t.get("got") or {}).items() if key != "kept"}
            finish(actor, k, got, t.get("took_s"))


def begin(actor: str, question: str, looking_at: str, page: str, now: float = None) -> dict:
    """A press's turn, kept while it runs: ``{"ok", "error", "turn"}``. Refused while another
    of *actor*'s turns is working (one at a time: Send is Stop while one works), naming it."""
    from modules.filestore import PathLock

    if not _person(actor):
        return {"ok": False, "error": "no verified person: an answer is kept in its asker's own "
                                      "conversation, and this request names nobody", "turn": ""}
    now = time.time() if now is None else now
    turn = "t-" + secrets.token_hex(8)
    try:
        os.makedirs(_dir(), mode=0o700, exist_ok=True)
        with PathLock(path_of(actor)):
            settle_lost(actor, now)
            turns = _turns(actor)
            if any(_turn_state(v, now) in BUSY for v in turns.values()):
                return {"ok": False, "turn": "",
                        "error": "your last question is still being answered: press Stop, "
                                 "or wait for its answer"}
            turns[turn] = {"turn": turn, "at": _stamp(now), "started": now, "alive": now,
                           "question": _question(question),
                           "looking_at": str(looking_at or "")[:200],
                           "page": str(page or "")[:600], "steps": [], "stop_at": None}
            _write_turns(actor, turns)
    except OSError as exc:
        log.error("assistant: a turn could not be started: %s", exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200], "turn": ""}
    return {"ok": True, "error": "", "turn": turn}


def _update(actor: str, turn: str, fn) -> dict:
    from modules.filestore import PathLock
    try:
        with PathLock(path_of(actor)):
            turns = _turns(actor)
            t = turns.get(turn)
            if t is None:
                return {}
            fn(t)
            _write_turns(actor, turns)
            return dict(t)
    except OSError as exc:
        log.warning("assistant: turn %s could not be updated: %s", turn, exc)
        return {}


def step(actor: str, turn: str, words: str, now: float = None) -> None:
    """The step *turn* is on, in a person's words, kept with its sign of life."""
    now = time.time() if now is None else now

    def go(t):
        t["steps"] = (list(t.get("steps") or []) + [str(words)[:160]])[-8:]
        t["alive"] = now
    _update(actor, turn, go)


def alive(actor: str, turn: str, now: float = None) -> None:
    """*turn*'s job is still running (its call streams)."""
    now = time.time() if now is None else now

    def go(t):
        t["alive"] = now
    _update(actor, turn, go)


def stop(actor: str, turn: str, now: float = None) -> dict:
    """Stop pressed on *turn*: ``{"ok", "error"}``. Its job reads it (`stop_asked`)."""
    now = time.time() if now is None else now

    def go(t):
        t["stop_at"] = t.get("stop_at") or now
    if not TURN_ID.fullmatch(str(turn or "")):
        return {"ok": False, "error": f"{str(turn)[:40]!r} is not a turn's id"}
    got = _update(actor, turn, go)
    if not got:
        return {"ok": False, "error": "that question is no longer being answered"}
    return {"ok": True, "error": ""}


def stop_asked(actor: str, turn: str) -> bool:
    """Whether *turn*'s job stops at its next check (in any worker: read from its file): Stop
    was pressed on it, or the turn is gone (let go as lost by the person's next press while
    its job was still alive: unstoppable otherwise, since Stop finds only a running turn) or
    ended (the review of 2026-11-28)."""
    t = _turns(actor).get(turn)
    return t is None or bool(t.get("ended") or t.get("stop_at"))


def finish(actor: str, turn: str, got: dict, took_s: float = None) -> dict:
    """*turn*'s end: kept in the conversation as an exchange, and no longer running. ``{"ok",
    "error"}``. When the exchange cannot be kept, the turn is kept ended with its answer, so
    the panel still draws it, saying it was not kept."""
    from modules.filestore import PathLock

    t = _turns(actor).get(turn)
    if t is None:
        return {"ok": False, "error": f"turn {turn} is not running"}
    kept = keep(actor, t.get("question") or "", t.get("looking_at") or "", got,
                page=t.get("page") or "", turn=turn, took_s=took_s, at=t.get("at") or "")
    try:
        with PathLock(path_of(actor)):
            turns = _turns(actor)
            if kept["ok"]:
                turns.pop(turn, None)
            elif turn in turns:
                turns[turn].update(ended=True, got=_masked(dict(got, kept=kept["error"])),
                                   took_s=took_s)
            _write_turns(actor, turns)
    except OSError as exc:
        log.error("assistant: turn %s's end could not be written: %s", turn, exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    return kept


def turn_of(actor: str, turn: str, now: float = None) -> dict:
    """What *turn* is now: ``{"state", ...}``: ``working``, ``stopping`` or ``lost`` with its
    running record; ``done`` with its exchange as the conversation keeps it; ``gone`` when it
    is in neither (another conversation, or not *actor*'s)."""
    if not _person(actor) or not TURN_ID.fullmatch(str(turn or "")):
        return {"state": "gone"}
    t = _turns(actor).get(turn)
    if t is not None:
        if t.get("ended"):
            return {"state": "done", "row": {k: t.get(k) for k in (
                "at", "question", "looking_at", "page", "turn", "got", "took_s")}}
        state = _turn_state(t, now)
        # What the panel draws of it; its sign of life, start and stop are the store's own.
        shown = {k: t.get(k) for k in ("turn", "at", "question", "looking_at", "page", "steps")}
        if state == "lost":
            return dict(shown, state="lost", got={"state": "lost",
                                                  "detail": LOST_WORDS.format(m=LOST_S // 60)})
        return dict(shown, state=state)
    for row in read(actor)["rows"]:
        if row.get("turn") == turn:
            return {"state": "done", "row": row}
    return {"state": "gone"}


def running(actor: str, now: float = None) -> list:
    """*actor*'s turns not yet in the conversation (working, stopping, lost or ended unkept),
    oldest first, as `turn_of` draws them."""
    if not _person(actor):
        return []
    out = [turn_of(actor, k, now) | {"turn": k} for k in _turns(actor)]
    return sorted(out, key=lambda t: t.get("at") or "")
