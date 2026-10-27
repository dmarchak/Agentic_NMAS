"""One press, one provider request (C1854; the operator's Walk 2, 2026-10-27: one alert's pack
was explained twice, 12 s apart, both calls reaching the provider).

Every AI call passes through `gateway.ask`, and the gateway passes the part of a call that
spends (the caps, the send and the record) through `once`. Two rules, each across worker
processes (CLAUDE.md: a protection counts only across processes), by a file lock per slot in
the folder beside the record of AI calls (`calls._path`'s folder, ``ai_presses/``):

1. **A press carries a key, and a key already seen returns its call.** The page sends a fresh
   key with every press (`X-NMAS-Press`, made in the browser per request:
   static/js/nmas_v2.js, `pressKey`). The n-th call a request makes under a key is slot
   ``key-<sha256(actor, key, n)>``: a second request with the same key (a retry, a resent
   form) waits while the first's n-th call is in flight, then returns that call; one that
   arrives later returns it at once. Nothing is sent again. The slot records the access scope
   the call was made under (`identity.access_scope`): a retry under another scope (a gate
   changed between the two) is refused (``other_scope``, naming both), never handed the call.
2. **The same request in flight is joined, not started again.** The slot
   ``req-<request_digest>`` is held while a call is sent. Its identity is explicit
   (`IDENTITY`): the feature, the network, the subject, the prompt and its version, the
   model and the requester's access scope, then the masked request itself. A second press
   with all of them equal (a double click, a press after a refresh dropped the first answer,
   another person with the same scope on the same alert) finds the slot held, waits, and
   returns the call that held it. Any one of them different is another request, so a call is
   never handed across features, networks or access scopes. A request that finds the slot
   free makes its own call, however recently an identical one ended: pressing again after an
   answer is a new call (Explain's is "Explain again").

Each join is the joiner's own row in `ai_calls` (the gateway's `_joined`): their actor, the
feature and subject, verdict ``joined``, cost 0, ``joined`` the call's id, and why. It replaces
a use row on the call (which a feature's own use, "shown" or "refused by validation", would
then follow, so the call's history would read a join as what became of its answer). A join
costs nothing new: the result is the call's own row, rebuilt by the gateway (its output
validated again by its schema).

**The wait is bounded** by the adapter's own worst case for one call (the gateway's
`press_wait_s`, handed in: only the gateway reaches the adapter). Past it the press is refused
(`in_flight`), naming the bound, and nothing is sent. A holder that dies releases its lock with
its process (`flock`), its slot still marked running, and the waiter then makes its own call.

The slots hold only call ids, never a request or an answer; files older than `KEEP_S` are
removed as new ones are written.
"""
import hashlib
import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

#: The header a press's key rides in (static/js/nmas_v2.js sets it on every htmx request that
#: is not a GET).
HEADER = "X-NMAS-Press"
#: A key's shape: what the page makes (a UUID's hex, or 32 random hex), and nothing a person
#: could mistake for another field.
KEY_SHAPE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


#: Slots older than this are removed as new ones are written: far past any wait.
KEEP_S = 24 * 3600
#: How often a waiting press asks the lock again.
POLL_S = 0.1


class InFlightTooLong(Exception):
    """A slot stayed held past the wait the gateway handed in."""


def _dir() -> str:
    from modules.ai import calls
    return os.path.join(os.path.dirname(os.path.abspath(calls._path())), "ai_presses")


def _sha(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8") + b"\0")
    return h.hexdigest()


#: What makes two requests one, beside the feature and the masked body (`request_digest`):
#: everything that changes the answer or who may see it, named by the gateway, never left to
#: happen to be inside the body.
IDENTITY = ("network", "subject", "prompt", "model", "scope")


def request_digest(feature: str, body: dict, about: dict) -> str:
    """The identity of a request: the feature, *about* (each of `IDENTITY`, every one named:
    a missing or extra name raises, so no caller leaves one out) and the masked body as it
    would be sent. JSON with sorted keys, ASCII-escaped as the adapter's request is, so equal
    content is one request whatever order it was built in, and text that cannot be UTF-8
    (a lone surrogate) is digested as it is sent instead of failing."""
    if sorted(about) != sorted(IDENTITY):
        raise ValueError(f"a request's identity names {', '.join(IDENTITY)}; given "
                         f"{', '.join(sorted(about)) or 'none'}")
    return _sha(feature, json.dumps(about, sort_keys=True, ensure_ascii=True),
                json.dumps(body, sort_keys=True, ensure_ascii=True))


def current_press(actor: str):
    """``{"slot", "n"}`` for the request being served: its key's slot for this call (its n-th
    through the gateway), or None outside a request or with no key (a script, a test client
    sending none, a form posted without the page's script)."""
    from flask import g, has_request_context, request

    if not has_request_context():
        return None
    key = (request.headers.get(HEADER) or "").strip()
    if not KEY_SHAPE.match(key):
        return None
    n = int(g.get("nmas_ai_press_n", 0)) + 1
    g.nmas_ai_press_n = n
    return {"slot": "key-" + _sha(actor, key, n), "n": n}


class _Slot:
    """One lock file and its marker (``<name>.lock``, ``<name>.json``)."""

    def __init__(self, name: str):
        self.name = name
        self.base = os.path.join(_dir(), name)
        self.fd = None

    def claim(self, wait_s: float, clock, sleep) -> bool:
        """Take the lock; True when another held it first (this press waited)."""
        import fcntl

        os.makedirs(os.path.dirname(self.base), exist_ok=True)
        fd = os.open(self.base + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fd = fd
            return False
        except BlockingIOError:
            pass
        deadline = clock() + wait_s
        while True:
            sleep(POLL_S)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.fd = fd
                return True
            except BlockingIOError:
                if clock() > deadline:
                    os.close(fd)
                    raise InFlightTooLong(self.name)

    def marker(self):
        try:
            with open(self.base + ".json", encoding="utf-8") as fh:
                got = json.load(fh)
            return got if isinstance(got, dict) else None
        except (OSError, ValueError):
            return None

    def mark(self, **fields) -> None:
        from modules.filestore import write_atomic
        write_atomic(self.base + ".json", json.dumps(dict(fields, at=time.time())))

    def release(self) -> None:
        if self.fd is None:
            return
        import fcntl
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None


def _prune(now: float) -> None:
    folder = _dir()
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        path = os.path.join(folder, name)
        try:
            if now - os.path.getmtime(path) > KEEP_S:
                os.unlink(path)
        except OSError:
            continue


def _done_call(marker) -> str:
    if marker and marker.get("state") == "done" and isinstance(marker.get("call_id"), str):
        return marker["call_id"]
    return ""


def _join(call_id: str, rebuild, actor: str, why: str):
    """The call *call_id*'s own result, rebuilt by *rebuild* (the gateway's, which records the
    joiner's own row); None when its row cannot be read (the press then makes its own call,
    which the caps judge against the record as ever)."""
    from modules.ai import calls

    found = calls.find(call_id)
    if not found.get("row"):
        log.warning("ai presses: the call %s to join is not in the record (%s); a new call is "
                    "made", call_id, found.get("error") or found.get("state"))
        return None
    log.info("ai presses: %s joined call %s (%s)", actor, call_id, why)
    return dict(rebuild(found["row"], why), joined=call_id)


def once(feature: str, body: dict, *, about: dict, actor: str, make, rebuild, refuse,
         wait_s: float, clock=time.monotonic, sleep=time.sleep) -> dict:
    """*make*'s result (the gateway's caps, send and record), or the result of the call this
    press joins (rule 1 or 2 above), rebuilt from its row by *rebuild* (``rebuild(row, why)``).
    *about* is the request's identity beside its body (`IDENTITY`; its ``scope`` the
    requester's access scope). A press that waited past *wait_s* is refused through *refuse*
    (the gateway's, which records the row: ``in_flight``), and so is a key seen under another
    scope (``other_scope``); nothing is sent."""
    press = current_press(actor)
    digest = request_digest(feature, body, about)
    scope = about["scope"]
    slots = []
    try:
        if press:
            mine = _Slot(press["slot"])
            mine.claim(wait_s, clock, sleep)
            slots.append(mine)
            marker = mine.marker()
            seen = _done_call(marker)
            if seen and marker.get("scope") != scope:
                return refuse("other_scope", f"this press's key was answered by call {seen} "
                              f"under the access scope {marker.get('scope') or 'not recorded'!r}"
                              f", and it is sent again under {scope!r}: a call is never handed "
                              "across access scopes, so nothing was returned and nothing was "
                              "sent")
            if seen:
                got = _join(seen, rebuild, actor, "the same press sent again: its key was seen "
                            f"(call {press['n']} of the press)")
                if got is not None:
                    return got
        same = _Slot("req-" + digest)
        waited = same.claim(wait_s, clock, sleep)
        slots.append(same)
        if waited:
            seen = _done_call(same.marker())
            got = (_join(seen, rebuild, actor, "the same request was in flight: "
                         f"{feature}, the same network, subject, data, prompt, model and "
                         "access scope") if seen else None)
            if got is not None:
                if press:
                    slots[0].mark(state="done", call_id=seen, scope=scope)
                return got
        same.mark(state="running")
        if press:
            slots[0].mark(state="running", scope=scope)
        got = make()
        call_id = got.get("call_id") or ""
        same.mark(state="done", call_id=call_id)
        if press:
            slots[0].mark(state="done", call_id=call_id, scope=scope)
        return got
    except InFlightTooLong as exc:
        return refuse("in_flight", f"an identical {feature} call has been in flight for over "
                      f"{wait_s:.0f} s (slot {str(exc)[:16]}…), the most one call can take; "
                      "nothing was sent")
    finally:
        for s in reversed(slots):
            s.release()
        _prune(time.time())
