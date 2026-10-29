"""The provider's workspace usage limit, held (C2084).

When the provider refuses a call because the workspace's own usage limit is reached (HTTP 400,
``invalid_request_error``, "You have reached your specified workspace API usage limits. You
will regain access on 2026-11-01 at 00:00 UTC."; `anthropic_adapter.WorkspaceLimit`), every
call after it would be refused the same way until that moment, or until an admin raises the
limit in the provider's console. So the gateway records the refusal here (`record`) and, while
it holds (`holding`), refuses each later call itself, in the same words, without asking the
provider. Across worker processes: the hold is a small store beside the record of AI calls,
read by every process at each call.

**How long it holds.** Until the moment the provider named (``until``). When it named none,
for `RECHECK_S` (``recheck_at``); the next call after that asks the provider again, and a
refusal holds it again. A call after the moment asks the provider; a refusal records the hold
again, a success clears it (`clear`).

**The AI card's Test asks anyway** (`rechecks`: a person's press of the ``connection_check``
task, `RECHECKS`). An admin who raises the limit in the provider's console needs a way to tell
Mercury before the moment, and the card's Test is that: one person's press, one request,
refused at no charge or answered; its answer clears the hold for every feature. No other task,
and no background job or evaluation run, is let through.

**A success clears only a hold recorded before its call was sent** (`clear`'s *sent_at*): a
call sent before another call's refusal was recorded, answered after, says nothing about the
limit now.

**The store** (``ai_provider_limit.json``, owner-only from creation: `filestore.write_atomic`'s
``mkstemp`` is 0600, replaced atomically under `filestore.PathLock`) holds no request, answer
or key: ``{"since", "until", "recheck_at", "said", "status", "call_id", "feature", "prompt"}``,
*said* the provider's own words, masked and cut by the adapter (*prompt* a refused count's,
C2157; empty for a send, whose row names it; a hold written before it has none, and reads).

**An unreadable store is read as no hold**, logged, and replaced by the next refusal: the
store only saves asking the provider, which stays the authority, and a refused request is not
billed. Reading it as a hold would stop every AI call with no moment to lift it.

**The words** are this module's (`said`): the gateway's refusal, every AI control's reason
(templates/v2/_ai.html's `reason`, through `controls.readiness`), the top bar's chip
(`spend.chip`), the spend panel and Needs attention (`attention.ai_spend_source`) all read
them here, so no two screens can word it differently.
"""
import datetime
import json
import logging
import os
import time

log = logging.getLogger(__name__)

#: The store's file name, beside the record of AI calls.
NAME = "ai_provider_limit.json"
#: The refusal's kind: the adapter's (`anthropic_adapter.WorkspaceLimit.kind`), on the provider's
#: refusal and on every call the gateway refuses while the hold stands.
KIND = "workspace_limit"
#: The tasks a hold does not refuse: the AI card's Test, the way an admin tells Mercury the
#: limit was raised (the module's docstring).
RECHECKS = ("connection_check",)
#: How long a hold lasts when the provider names no moment, seconds: 600 (10 minutes). Not
#: measured: no such refusal has been seen. Derived from what each side costs. Shorter, and
#: an unattended background feature asks the provider more often while it stays refused: at
#: most 3600 / RECHECK_S = 6 refused requests an hour, each billed nothing. Longer, and a
#: press made after an admin raised the limit, without pressing Test, is refused by Mercury
#: for up to this long after the provider would answer it. Test asks at once either way.
RECHECK_S = 600
#: The words every screen says, in parts so a template can draw the moment in the viewer's
#: own time between them (`said`).
LEAD = "AI is unavailable: the provider's workspace usage limit is reached"
TAIL = "an admin raises it in the provider's console"
#: The month names the words say a date by (never the host's locale).
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")


def _path() -> str:
    from modules.ai import calls
    return os.path.join(os.path.dirname(os.path.abspath(calls._path())), NAME)


def rechecks(feature: str, trigger_kind: str) -> bool:
    """Whether a call asks the provider while a hold stands: a PERSON's press of a task in
    `RECHECKS` (the AI card's Test), never a background job's or an evaluation run's."""
    from modules.ai import triggers

    return feature in RECHECKS and trigger_kind == triggers.PERSON


def clock() -> float:
    """Now, as an epoch: the one clock the hold is judged by (a test sets it)."""
    return time.time()


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _epoch(iso):
    """*iso* (``YYYY-MM-DDTHH:MM:SSZ``) as an epoch, or None."""
    if not isinstance(iso, str):
        return None
    try:
        return datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        return None


def read() -> dict:
    """``{"state": "ok"|"unreadable", "hold": dict|None, "error"}``: the store as it is, a
    hold whether or not it still holds (`holding` judges that)."""
    path = _path()
    if not os.path.exists(path):
        return {"state": "ok", "hold": None, "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
        if not isinstance(got, dict) or _epoch(got.get("since")) is None \
                or _epoch(got.get("recheck_at")) is None:
            raise ValueError("not a provider-limit store")
        return {"state": "ok", "hold": got, "error": ""}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "hold": None, "error": f"{type(exc).__name__}: {exc}"}


def holding(now=None):
    """The hold, while it holds: *now* (an epoch; the clock's by default) before its
    ``recheck_at``. None otherwise, and for an unreadable store (logged: the module's
    docstring)."""
    got = read()
    if got["state"] == "unreadable":
        log.error("ai provider limit: %s cannot be read (%s); read as no hold, so the next "
                  "call asks the provider", NAME, got["error"])
        return None
    hold = got["hold"]
    t = clock() if now is None else now
    if hold is None or t >= _epoch(hold["recheck_at"]):
        return None
    return hold


def record(exc, *, call_id: str = "", feature: str = "", prompt: str = "", now=None) -> dict:
    """Hold the refusal *exc* (an `anthropic_adapter.WorkspaceLimit`): until the moment it
    names, else for `RECHECK_S`. Returns the hold; a store that cannot be written is logged,
    and the hold returned all the same (this call's words still say it). *prompt* is a
    refused count's (``<name>.v<N>``, C2157: a count has no call, so no row to name its
    builder); a send's is its row's, through *call_id*."""
    from modules import filestore

    t = clock() if now is None else now
    until = getattr(exc, "until", None)
    until_t = _epoch(until)
    if until_t is not None and until_t <= t:
        # A moment already past: the provider's clock and ours disagree. Held for the
        # re-check's bound, never for nothing (the next call would only be refused again).
        log.warning("ai provider limit: the provider named %s, already past at %s; held for "
                    "%s s instead", until, _iso(t), RECHECK_S)
        until, until_t = None, None
    hold = {"since": _iso(t), "until": until,
            "recheck_at": until if until else _iso(t + RECHECK_S),
            "said": str(getattr(exc, "said", "") or exc)[:300],
            "status": int(getattr(exc, "status", 0) or 0), "call_id": call_id,
            "feature": feature, "prompt": prompt}
    path = _path()
    try:
        with filestore.PathLock(path):
            filestore.write_atomic(path, json.dumps(hold, sort_keys=True))
        log.warning("ai provider limit: the provider refused %s (%s): the workspace's usage "
                    "limit is reached; every AI call is refused until %s", call_id,
                    hold["said"], hold["recheck_at"])
    except OSError as exc_w:
        log.error("ai provider limit: the hold could not be written (%s); later calls will "
                  "ask the provider", exc_w)
    return hold


def clear(sent_at: float, *, call_id: str = "") -> bool:
    """A call sent at *sent_at* (an epoch) was answered: the hold is removed when it was
    recorded at or before that moment (one recorded after it stands: the module's docstring).
    True when a hold was removed. Never raises."""
    from modules import filestore

    path = _path()
    if not os.path.exists(path):
        return False
    hold = None
    try:
        with filestore.PathLock(path):
            got = read()
            hold = got["hold"]
            if got["state"] == "unreadable":
                os.remove(path)
                log.warning("ai provider limit: %s answered; the unreadable store (%s) was "
                            "removed", call_id, got["error"])
                return True
            if hold is None:
                return False
            since = _epoch(hold["since"])
            if since > sent_at:
                log.info("ai provider limit: %s answered, but was sent at %s, before the hold "
                         "recorded at %s: the hold stands", call_id, _iso(sent_at),
                         hold["since"])
                return False
            os.remove(path)
        log.warning("ai provider limit: %s answered (sent %s, after the hold of %s): the "
                    "hold is cleared", call_id, _iso(sent_at), hold["since"])
        return True
    except OSError as exc:
        log.error("ai provider limit: the hold could not be cleared (%s); it lifts at %s",
                  exc, (hold or {}).get("recheck_at") or "its moment")
        return False


def moment(iso: str) -> dict:
    """A moment as the screens draw it: ``{"at", "utc"}``, *at* the instant
    (``YYYY-MM-DDTHH:MM:SSZ``, drawn in the viewer's own time in the browser: nmas_v2.js
    `drawClock`) and *utc* its words in UTC ("1 November 2026 00:00"); *brief* the chip's
    shorter form ("1 Nov 00:00")."""
    t = _epoch(iso)
    d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    return {"at": iso, "utc": f"{d.day} {MONTHS[d.month - 1]} {d.year} {d:%H:%M}",
            "brief": f"{d.day} {MONTHS[d.month - 1][:3]} {d:%H:%M}"}


def said(hold: dict) -> dict:
    """What every screen says of *hold*: ``{"lead", "until", "recheck", "tail", "words",
    "short", "provider"}``. *until* is `moment` of the provider's moment, or None when it
    named none; then *recheck* is when Mercury asks again. *words* is the whole sentence in
    UTC (the gateway's refusal, Needs attention's row); *short* the chip's ("AI unavailable
    until 1 Nov 00:00 UTC"); *provider* the provider's own words."""
    until = moment(hold["until"]) if hold.get("until") else None
    recheck = None if until else moment(hold["recheck_at"])
    if until:
        when = f"until {until['utc']} UTC"
        short = f"AI unavailable until {until['brief']} UTC"
    else:
        when = (f"and it named no time access returns (Mercury asks it again from "
                f"{recheck['utc']} UTC)")
        short = "AI unavailable: the provider's usage limit"
    return {"lead": LEAD, "until": until, "recheck": recheck, "tail": TAIL,
            "words": f"{LEAD}, {when}; {TAIL}", "short": short,
            "provider": hold.get("said") or ""}
