"""The toolbar assistant's thread, kept server-side per person (stage 2; docs/design/assistant.md,
"Persistent across pages"): a page change or a refresh draws the same exchanges, and nothing is
asked again.

**The store.** One JSON-lines file per person, ``assistant_threads/<key>.jsonl`` in the data
directory, owner-only (written whole through `filestore.write_atomic`, 0600, under the file's
own lock), holding that person's newest `KEEP` exchanges, oldest first. The file is named by a
digest of the person's identity (`key_of`), never by the identity itself, so a listing of the
folder names nobody.

**What an exchange holds.** When it was asked, the question as it left (masked by
`redact.redact_typed`, as the manual's gap record holds it), what the panel was looking at
(the head's words), and the answer as the panel drew it, its words masked again by
`redact.redact_text` on the way in: never a value the mask removed, never a read's answer
(those stay in the send log's digests and History › Reads).

**Only a verified person has a thread.** A request whose actor is not verified keeps and reads
nothing. An unreadable file is said, never read as an empty thread; the next exchange kept
copies it aside first (`filestore.preserve_corrupt`), then starts the thread again.
"""
import hashlib
import json
import logging
import os
import time

log = logging.getLogger(__name__)

#: The folder in the data directory, and the exchanges kept for each person (the newest).
FOLDER = "assistant_threads"
KEEP = 20


def key_of(actor: str) -> str:
    """The file's name for *actor*: a digest, so the folder names nobody."""
    return hashlib.sha256(("assistant-thread:" + str(actor)).encode("utf-8")).hexdigest()[:32]


def _dir() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, FOLDER)


def path_of(actor: str) -> str:
    return os.path.join(_dir(), key_of(actor) + ".jsonl")


def _person(actor: str) -> bool:
    from modules import identity
    return bool(actor) and actor != identity.UNVERIFIED


def read(actor: str) -> dict:
    """``{"state", "error", "rows"}``: *actor*'s exchanges kept, oldest first. *state* ``ok``,
    ``none`` (no verified person: nothing is kept) or ``unreadable`` (said, never read as
    none)."""
    if not _person(actor):
        return {"state": "none", "error": "", "rows": []}
    path = path_of(actor)
    if not os.path.exists(path):
        return {"state": "ok", "error": "", "rows": []}
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "error": type(exc).__name__, "rows": []}
    return {"state": "ok", "error": "", "rows": [r for r in rows if isinstance(r, dict)][-KEEP:]}


def _masked(value):
    from modules import redact

    if isinstance(value, str):
        return redact.redact_text(value)
    if isinstance(value, list):
        return [_masked(v) for v in value]
    if isinstance(value, dict):
        return {k: _masked(v) for k, v in value.items()}
    return value


def keep(actor: str, question: str, looking_at: str, got: dict, now: float = None) -> dict:
    """Keep one exchange in *actor*'s thread, the newest `KEEP` kept: ``{"ok", "error"}``.
    The question masked as it left, the answer's words masked again; nothing kept for a
    request with no verified person."""
    from modules import redact
    from modules.filestore import PathLock, preserve_corrupt, write_atomic

    if not _person(actor):
        return {"ok": False, "error": "no verified person: nothing is kept"}
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None
                                                                  else now)),
           "question": redact.redact_typed(" ".join(str(question or "").split()))[:600],
           "looking_at": str(looking_at or "")[:200], "got": _masked(dict(got or {}))}
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
