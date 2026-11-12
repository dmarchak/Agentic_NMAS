"""Self-healing's detection read: its own live, bounded Loki read of the lines it decides on
(C3330; the operator, 2026-11-12: "Detection's source: its own live, bounded Loki read, never
through logs-tail (Display only)").

**Why its own read.** Until this, the configuration-change trigger (`triggers.from_syslog`)
and the flap record (`flaps.from_syslog`) rode on the `logs-tail` reader's stored lines: a
display reader. When its reads failed from 14:36 UTC on 2026-11-12 (C3330: its forward window
grew after each failure until every read timed out), detection was blind with them, and nothing
said so but a reader row about the Logs page. Detection is the heal pipeline's, and the heal
pipeline reads live (CLAUDE.md, the Display only clause); this reader is detection's alone, and
no page draws from it.

**What it asks.** Every `INTERVAL_SECONDS`, ONE query per Loki configuration (every device at
once, never per device): the syslog job's lines that are a configuration change
(`who.CONFIG_LOG`: CONFIG_I, CONFIG_P, DMI's CONFIG_I) or a link or line-protocol transition
(`flaps.MNEMONICS`), by Loki's own line filter, never all lines; oldest first
(``direction=forward``), from its cursor to `SETTLE_SECONDS` before now.

**Its cursor** is where the last good read ended (``through_ns`` in its value, the reader's
store): every line before it was handed to the steps. A first read resumes from the last line
the steps processed under the logs-tail store they read before (their cursors, `triggers.
cursor_for` and `flaps.cursor_for`, keyed by the old store's name until this release's first
read: expand, then contract), else from the `WINDOW_SECONDS` before it. Each step keeps its own
cursor (the last processed line's receive time), so a line handed twice is decided once.

**Bounded.** Each query asks at most `WINDOW_SECONDS` of time and `PAGE_LIMIT` lines; a read
asks at most `PAGES_PER_READ` queries. A query that returns its limit is read on from its last
line (that line's nanosecond again, its lines taken once). So after a blind spell the reads
re-scan from the cursor in bounded pages, oldest first, until current, every change in the gap
decided once; while behind, the value says how far (``behind_seconds``). A cursor older than
`HORIZON_SECONDS` is not scanned from there: the read starts at the horizon and the value says
what was not scanned (``unscanned``), which Needs attention says for a day.

**Its liveness is a Needs attention row of its own, never a reader row** (the operator,
2026-11-12): past Loki's start grace (reader_job rule 14, `LOKI`), a store whose last good read
is older than `BLIND_AFTER_SECONDS` is a WARNING row on each network it serves where healing
is on: "Self-healing can't see configuration changes on <network> since <time>" (the
operator's rule, 2026-11-12: critical is a network outage). It clears when a read succeeds
again. So that it still reaches a person, each raise is also the notice "self-healing is blind
or paused", once, to every team (modules/heal/blind_notice.py, from this reader's after-store
step).

Nothing here draws a page; the steps run after each stored read (`reader_job.after_any_store`,
`triggers._after_store` and `flaps._after_store`), and a step that fails never stops the read.
"""

import logging
import time

from modules import reader_job

log = logging.getLogger(__name__)

READER_NAME = "heal-detect"
#: Detection's latency as it was on the logs-tail reader (every 5 s): a change outside Mercury
#: is sighted within about 15 s of reaching Loki (this interval and `SETTLE_SECONDS`).
INTERVAL_SECONDS = 5
#: How far before now a read asks to: a line reaches Loki a little after the receive time it
#: carries (the collector batches, Alloy's loki.write waits 1 s by default), and a line that
#: arrives after a read asked past its time would be missed. Not measured yet (C3203); ten
#: seconds is the margin, ten times the batching wait.
SETTLE_SECONDS = 10
#: The most time one query asks: the logs-tail's window. A 15-minute ask of EVERY line answered
#: in 0.7 to 3.5 s on the host under load (measured 2026-11-12 16:43 UTC), under the client's
#: 5 s; this query filters to a few mnemonics, so it is no dearer. A failed read never makes
#: the next ask longer (C3330's spiral).
WINDOW_SECONDS = 900
#: The most lines one query returns; a full page is read on from its last line.
PAGE_LIMIT = 500
#: The most queries one read asks, so a read after a blind spell is bounded too: an hour of
#: quiet lines a read, and a read of four failed asks is about 64 s (a failed ask is the
#: client's 5 s three times, `integrations.base`'s Retry, and its 0.9 s of backoff).
PAGES_PER_READ = 4
#: How far back a re-scan reaches: a day. A change older than that is the drift check's to
#: find (it compares each device with its golden); the span not scanned is said.
HORIZON_SECONDS = 24 * 3600
#: How old the last good read may be before detection is called blind: about 2.5x a healthy
#: read cycle at its slowest (the interval and four asks of 3.5 s, about 19 s, measured
#: 2026-11-12), so one slow read is no row.
BLIND_AFTER_SECONDS = 60
KEEPALIVE_SECONDS = 300

#: Loki as reader_job rule 14's dependency: within its grace after Mercury's start a read that
#: finds it not answering is waiting, never blind.
LOKI = reader_job.Dependency(
    key="loki", label="Loki", start_grace_seconds=30,
    # Measured read-only on the Mercury host (Loki's own log of its 2026-10-28 start): the
    # container started 02:00:19.7Z, Loki logged "Loki started" at 02:00:21.2Z and answered
    # its first query at 02:00:31.1Z: 11.4 s. 2.5x is 28.5 s; 30 s.
    grace_basis=("about 2.5x Loki's measured start: 11.4 s from its container's start to its "
                 "first answered query (the Mercury host, 2026-10-28)"),
    start_unreadable="Loki runs in its own container, whose start is not Mercury's to read")

_SELECT = []


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def line_filter() -> str:
    """The lines detection decides on, as one RE2 alternation: a configuration change or a
    transition, each by its mnemonic."""
    from modules.heal import flaps

    # The mnemonics are letters, digits, % and -: literal in RE2 as they are.
    alts = [r"%(?:SYS|DMI)-\d-CONFIG_[IP]\b"] + list(flaps.MNEMONICS)
    return "|".join(alts)


def _hash(line: str) -> str:
    import hashlib

    return hashlib.sha256(line.encode("utf-8", "replace")).hexdigest()[:16]


def query(loki) -> str:
    """The one query: the syslog job's detection lines. Raises `device_logs.NoSyslogJob`."""
    from modules.readers.logs_summary import _job

    return f"{{{_job(loki)}}} |~ `{line_filter()}`"


class NotAnswered(RuntimeError):
    """Loki did not answer (refused, reset, or out of time before any answer): rule 14's."""


class _Ask:
    """One configuration's Loki, asked through its integration client (its auth and TLS)."""

    def __init__(self, list_name: str):
        from modules.readers.logs_summary import _Loki

        self.inner = _Loki(list_name)
        self.client = self.inner.client

    def configured(self) -> bool:
        return self.inner.configured()

    def ask(self, path: str, **params) -> list:
        r = self.client._get(path, **params)          # noqa: SLF001 (the client's one GET)
        if not r.get("ok"):
            words = (r["error"] if r.get("timed_out") else
                     f"Loki could not be asked ({path}): {r.get('error')}")
            if r.get("not_answering"):
                raise RuntimeError(words) from NotAnswered(r.get("error"))
            raise RuntimeError(words)
        try:
            return (r["response"].json().get("data") or {}).get("result") or []
        except ValueError as exc:
            raise RuntimeError(f"Loki's answer to {path} could not be read: {exc}") from exc


def entry(ns, raw: str) -> dict:
    """One line as the steps read it: the receive time (``ts``, ``at``), the device, the
    mnemonic and its severity, and the text masked on the way in."""
    from modules import device_logs
    from modules.readers.logs_summary import _fields_of
    from modules.redact import redact_text

    ts = int(ns) / 1e9
    dev, sev = _fields_of(raw)
    p = device_logs.parse(raw, dev) if dev else {"mnemonic": "", "sev": None, "text": raw}
    return {"ns": int(ns), "at": _iso(ts), "ts": ts, "dev": dev, "sev": p.get("sev", sev),
            "mn": p.get("mnemonic", ""), "text": redact_text(p.get("text", raw) or "")}


def _store(list_name: str) -> str:
    try:
        store, _refused = reader_job.store_for(READER_NAME, list_name or _default())
    except Exception:                                   # noqa: BLE001 (Default's store)
        store = None
    return store or READER_NAME


def _previous(list_name: str) -> dict:
    try:
        got = reader_job.read_cached_for(READER_NAME, list_name or _default())
    except Exception as exc:                            # noqa: BLE001 (a first read, said)
        log.warning("heal-detect: the previous value could not be read (%s): resuming from "
                    "the steps' cursors", exc)
        return {}
    return ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}


def resume(previous: dict, store: str, now: float) -> tuple:
    """``(start_ns, basis)``: where this read starts."""
    from modules.heal import flaps, triggers

    if previous.get("configured") and previous.get("store") == store \
            and previous.get("through_ns"):
        return int(previous["through_ns"]), "where the last good read ended"
    seen = []
    for cursor in (triggers.cursor_for, flaps.cursor_for):
        try:
            got = cursor(store)
        except (OSError, ValueError) as exc:            # that step waits; said in its log
            log.warning("heal-detect: a step's cursor could not be read (%s)", exc)
            continue
        if got is not None:
            seen.append(got)
    if seen:
        return int(min(seen) * 1e9), "the last line self-healing's steps processed"
    return int((now - WINDOW_SECONDS) * 1e9), "a first read: the window before it"


def read(list_name: str = "", loki=None, clock=time.time, previous=None) -> dict:
    """One configuration's detection lines since its cursor, oldest first, bounded (see the
    module)."""
    loki = loki or _Ask(list_name)
    if not loki.configured():
        return {"configured": False}
    now = clock()
    target = int((now - SETTLE_SECONDS) * 1e9)
    if previous is None:
        previous = _previous(list_name)
    store = _store(list_name)
    start, basis = resume(previous or {}, store, now)
    floor = int((now - HORIZON_SECONDS) * 1e9)
    unscanned = previous.get("unscanned") if previous and previous.get("store") == store else None
    if unscanned and (unscanned.get("until") or 0) < now:
        unscanned = None
    if start < floor:
        unscanned = {"from": start, "to": floor, "from_at": _iso(start / 1e9),
                     "to_at": _iso(floor / 1e9), "until": now + HORIZON_SECONDS,
                     "why": (f"older than detection's {HORIZON_SECONDS // 3600} h horizon when "
                             "it read again")}
        start = floor
    q = query(loki)
    # The lines at the cursor's own nanosecond a read that ended on a full page already handed
    # over (their hashes, never their text): Loki's start is inclusive, so they come again.
    seen = ({(start, h) for h in previous.get("taken_at_through") or []}
            if previous and int(previous.get("through_ns") or -1) == start else set())
    lines, pos, asked = [], start, 0
    while pos < target and asked < PAGES_PER_READ:
        end = min(pos + WINDOW_SECONDS * 10 ** 9, target)
        got = loki.ask("loki/api/v1/query_range", query=q, limit=PAGE_LIMIT, start=str(pos),
                       end=str(end), direction="forward")
        asked += 1
        raw = sorted((int(ns), l) for s in got for ns, l in s.get("values") or [])
        fresh = [x for x in raw if (x[0], _hash(x[1])) not in seen]
        seen.update((ns, _hash(l)) for ns, l in fresh)
        lines += fresh
        if len(raw) >= PAGE_LIMIT:
            last = raw[-1][0]
            # A full page: read on from its last line's nanosecond (its lines taken once); a
            # page of nothing new at one nanosecond moves past it.
            pos = last if fresh and last > pos else max(last, pos) + 1
        else:
            pos = end
    pos = min(pos, target)
    entries = [entry(ns, l) for ns, l in sorted(lines)]
    return {"configured": True, "store": store, "lines": entries, "from_ns": start,
            "resumed_from": basis, "through_ns": pos, "through_at": _iso(pos / 1e9),
            "taken_at_through": sorted(h for ns, h in seen if ns == pos),
            "current": pos >= target, "behind_seconds": max(0, (target - pos) // 10 ** 9),
            "asked": asked, "unscanned": unscanned, "read_at": _iso(now), "read_at_ts": now}


def changed(previous, value) -> bool:
    """Announce (and so hand the steps the value) when the read holds lines, or when it caught
    up, fell behind, or the span not scanned moved."""
    v, p = value or {}, previous or {}
    if v.get("lines"):
        return True
    return ((bool(v.get("configured")), v.get("current"), bool(v.get("unscanned")))
            != (bool(p.get("configured")), p.get("current"), bool(p.get("unscanned"))))


# ── Its liveness: Needs attention's rows, never a reader row ──────────────────────────────

def _networks(store: str) -> list:
    from modules import integration_groups as IG

    reader = {r.name: r for r in reader_job.readers()}.get(READER_NAME)
    if reader is not None:
        for g in IG.groups(tuple(reader.per_group)):
            if IG.store_name(READER_NAME, g["id"]) == store:
                return sorted(g["lists"])
    return [_default()]


def _healing_on(networks: list) -> list:
    """The networks among *networks* whose healing is not off now; a mode that cannot be read
    counts as on (blindness is never hidden by an unreadable policy)."""
    from modules.heal import policy

    out = []
    for n in networks:
        try:
            if (policy.current(n) or {}).get("mode") != "off":
                out.append(n)
        except Exception:                               # noqa: BLE001 (judged on, said)
            out.append(n)
    return out


def _clock(epoch: float) -> str:
    return time.strftime("%H:%M UTC on %Y-%m-%d", time.gmtime(epoch))


def action(network: str) -> dict:
    """The blind row's one action: where Loki's connection is tested for the network."""
    from urllib.parse import quote

    return {"label": ("Test Loki's connection in this network's Settings, Integrations tab; "
                      "the row clears itself when detection reads Loki again"),
            "href": f"/v2/settings/network/{quote(network, safe='')}?tab=integrations"}


def liveness(reader, got: dict, now: float) -> list:
    """Detection's rows for one store (reader_job's `liveness` hook): ``blind`` past the grace
    when its last good read is older than `BLIND_AFTER_SECONDS`, ``waiting`` inside Loki's
    start grace, ``unscanned`` for a day after a re-scan that could not reach back, ``ok``
    otherwise. Each names the networks it serves where healing is on; none where it is off."""
    store = reader.name
    networks = _healing_on(_networks(store))
    base = {"unit": f"self-healing:{store}", "what": reader.what, "state": "ok",
            "max_age_minutes": BLIND_AFTER_SECONDS // 60, "list": ", ".join(networks)}
    if not networks:
        return [dict(base, detail="healing is off on every network this read serves")]
    doc = got.get("doc") or {}
    attempt = doc.get("last_attempt") or {}
    good = doc.get("last_good") or {}
    value = good.get("value") or {}
    if got.get("state") == "unreadable":
        return [dict(base, state="unknown",
                     detail=f"detection's store cannot be read: {got.get('why')}")]
    if good and not value.get("configured"):
        return [dict(base, detail="Loki is not configured for these networks, so detection "
                                  "reads nothing; the drift check still compares each device")]
    w = reader_job.waiting(doc, now) if attempt and not attempt.get("ok") else None
    if w:
        return [dict(base, state="waiting", waiting=w, since=reader_job._parse_iso(w["since"]),
                     headline=f"Self-healing's detection is {reader_job.waiting_words(w)}")]
    last = reader_job._parse_iso(good.get("value_at")) if good else None
    since = last if last is not None else reader_job.mercury_started()
    if now - since > BLIND_AFTER_SECONDS:
        words = ", ".join(networks)
        why = (f"its last read at {attempt.get('at')} failed: {attempt.get('error')}"
               if attempt and not attempt.get("ok") else
               f"no read since {attempt.get('at')}: its thread is not reading"
               if attempt else "it has not read since Mercury started")
        return [dict(base, state="blind", since=since,
                     headline=(f"Self-healing can't see configuration changes on {words} since "
                               f"{_clock(since)}"),
                     detail=(f"Detection reads Loki every {INTERVAL_SECONDS} s for the "
                             "configuration-change and link lines it decides on; "
                             f"{why}. Its last good read was "
                             f"{good.get('value_at') or 'never'}. When it reads again it "
                             "re-scans from there, oldest first, so a change made meanwhile "
                             f"is decided once (up to {HORIZON_SECONDS // 3600} h back). "
                             "Clears when a read succeeds."),
                     action=action(networks[0]))]
    gap = value.get("unscanned")
    if gap and (gap.get("until") or 0) > now:
        return [dict(base, state="unscanned", since=gap["to"] / 1e9,
                     headline=(f"Self-healing did not scan configuration changes on "
                               f"{', '.join(networks)} from {gap['from_at']} to "
                               f"{gap['to_at']}"),
                     detail=(f"{gap['why']}. A change made then was not decided by "
                             "self-healing; the drift check compares each device with its "
                             "golden. Clears a day after detection read again."),
                     action={"label": ("Run a drift check with Check now in Settings › "
                                       "Installation › Diagnostics, and read each departed "
                                       "device"),
                             "href": "/v2/settings/installation?tab=diagnostics"})]
    lag = value.get("behind_seconds") or 0
    return [dict(base, detail=(f"read at {good.get('value_at')}, through "
                               f"{value.get('through_at')}"
                               + (f", {lag} s behind and re-scanning" if lag else ", current")))]


def last_good_reads() -> list:
    """``[{"store", "value_at", "networks"}]`` for every detection store: the post-deploy
    check's question (scripts/nmas-post-deploy-check). Reads only."""
    out = []
    reader = {r.name: r for r in reader_job.readers()}.get(READER_NAME)
    for v in reader_job.configuration_readers(reader):
        got = reader_job.read_cached(v.name)
        good = (got.get("doc") or {}).get("last_good") or {}
        out.append({"store": v.name, "value_at": good.get("value_at"),
                    "configured": bool((good.get("value") or {}).get("configured")),
                    "state": got.get("state"), "networks": _networks(v.name)})
    return out


def _default() -> str:
    from modules.list_settings import DEFAULT_LIST
    return DEFAULT_LIST


def _after_store() -> bool:
    """After each stored read: the blind notice, once per raise (never a page's change)."""
    from modules.heal import blind_notice

    blind_notice.notify_detection()
    return False


READER = reader_job.register(reader_job.Reader(
    name=READER_NAME,
    what=("self-healing's detection: the configuration-change and link lines of every device "
          "since the last read, for the heal triggers and the flap record (C3330)"),
    endpoints=("Loki: GET /loki/api/v1/query_range (every device in one query, only the "
               "configuration-change and link lines, oldest first, from where the last read "
               "ended, at most 15 minutes and 500 lines a query, at most 4 queries a read)",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("detection's latency as it was on the logs-tail reader, every 5 s (the "
                    "operator's design, 2026-10-11, for lines as they arrive)"),
    read=read,
    invalidates=("job_health",),
    remedy="Read the error above: it names what Loki answered",
    window=("from where the last good read ended to 10 s before each read, at most 15 minutes "
            "a query; a re-scan reaches back at most 24 h"),
    per_group=("loki",),
    read_for=lambda list_name: read(list_name=list_name),
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
    dependency=LOKI,
    liveness=liveness,
    after_store=_after_store,
))
