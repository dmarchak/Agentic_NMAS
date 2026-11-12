"""modules/attention_store.py — Needs attention, held in the background (C3166, slice 1).

The operator's rule (2026-11-12, CLAUDE.md): no page load or badge poll waits on a
computation. Measured before it, on the host over 6 hours: the sidebar badge read 4,023 times
at p50 1.4 s and max 60 s, Needs attention 1,721 times at p50 2.1 s and max 64 s, each request
computing the 47 sources behind one lock (C1262's shared computation), and at a heal's end
the badge's reads queued to 26 s.

**One owner per network.** This module holds, per network, each source's last result and
when it was read, and the page assembled from them (`attention.assemble`: the same folding,
acknowledgements and badge a live computation makes). One background thread (`start`, the
app's own start-up) computes; a request reads (`read`, `badge`) and never computes. A network
never computed yet draws "Reading …" (`reading`), and fills itself when its first value lands:
the badge is pushed (`PUSH_EVENT`), the list hears `attention` (`_publish`).

**Cadence** (`cadence`): each source refreshes on its own clock, FAST_S while its network is
viewed (a page's live connection is open on it, `watch`, or a page read it within VIEWED_S) or
while the source itself has rows or failed (alerting), SLOW_S otherwise. `ON_HEAD` sources
(the template check, 4.6 s of the 5.9 s a cold computation took on the host) are computed only
when their network's repository head moves (read at the network's cadence, one `git
rev-parse`), or when one of their keys is announced. A row that clears by time
(`clears_at`) has its source read again at that moment, an acknowledgement's expiry
re-assembles the page at its end.

**Events recompute only what they touch** (`mark`): every announcement and every mutating
route's declared invalidation (modules/invalidation.py `_changed`) marks the sources whose
`attention.SOURCE_KEYS` hold one of its keys (an acknowledgement re-assembles without reading
a source), and the marked sources are computed once DEBOUNCE_S after the first mark: a heal's
many step announcements are one recompute, and a fix made through Mercury clears its row
within one debounce. A key no source reads (a running card's `device_progress`) marks nothing.

**Display only** (the operator, 2026-11-12): the held values draw pages. The heal pipeline
(detect, decide, guards, apply, verify, can't-fix), deploys and their before and after reads
read live and never come here; `reads()` counts every read of a held value, and
tests/test_attention_display_only.py runs those paths through the real code and holds the
count at zero.

**Never wrong-looking-right:** every held value carries its age (each source's read time, the
assembly's, drawn as "checked … ago"); a refresh that raises keeps the last good value and
says it failed (`failed` on its line, and `store.failed`); a source past its promise is
already a row (`attention._past_promise_rows`); a network that cannot be computed keeps its
last value and its age keeps growing on the page.

Process memory: a restart starts empty, and the warm-up fills the installation's network
(modules/warmup.py) before `/health` says ready.
"""

import copy
import logging
import threading
import time

log = logging.getLogger(__name__)

#: How long after the first mark the marked sources are computed: a burst of announcements
#: within it is one recompute. About the operator's "about 2 s"; a heal's steps announce
#: within a second of each other (the smoke heal's end, 2026-11-12 03:46:22 to 03:47:27 UTC,
#: in flask-app's request lines).
DEBOUNCE_S = 2.0
#: A viewed or alerting source's cadence. The host measured the 47 sources at about 1 s warm
#: together (C3166, 2026-11-12), so a viewed network costs about 1 s of one CPU in 20 s (5%)
#: before the template check, which is ON_HEAD.
FAST_S = 20.0
#: An idle source's cadence: about 1 s in 120 s (under 1% of one CPU) with nothing viewed,
#: under the plan's 5% budget; every reader's own promise is longer than this (the fastest
#: reader's interval is 60 s, its promise 150 s), so no idle source passes its promise here.
SLOW_S = 120.0
#: A page read within this long counts as viewing its network (a page whose live connection
#: has not opened yet, or a person moving between pages): about 4.5 FAST_S.
VIEWED_S = 90.0
#: A network nobody viewed for this long, other than the installation's own, is forgotten:
#: its held value is dropped and it is computed again on its next view.
FORGET_S = 3600.0
#: The sources read only when their network's repository head moves (or their keys are
#: announced): what they read changes only with a commit.
ON_HEAD = ("template_behind_source",)
#: An open list is told to redraw when what it draws changed, and otherwise at most this often
#: while its sources were read again, so its drawn ages stay true within a minute.
REDRAW_S = 60.0
#: The live connection's event carrying a network's badge, to that network's room only.
PUSH_EVENT = "nmas_attention"
ROOM_PREFIX = "attention:"
#: Who the store's own announcement names (`invalidation.READER_BY`: it wakes no reader).
ANNOUNCED_BY = "reader:needs-attention"
#: The page keys `read` adds to a live computation's (each drawn by templates/v2/_attention.html).
STORE_KEYS = ("state", "checked_at", "oldest_at", "failed")

#: A test session computes on every read, as before (tests/conftest.py), so a test that
#: patches a source and reads the page sees it; production never does.
COMPUTE_ON_READ = False

_ASSEMBLE = "\x00assemble"        # a mark that only re-assembles (an acknowledgement)
_UNDECLARED = "\x00undeclared"    # a mark that reaches every source with no declared keys

_clock = time.time
_lock = threading.Lock()          # the held state below
_compute = threading.RLock()      # one computation at a time, whoever asks (`ensure` re-enters)
_wake = threading.Event()
_nets: dict = {}
_watchers: dict = {}              # a live connection's sid -> its page's network
_reads = [0]
_runs: dict = {}                  # a source's key -> how many times it was computed
_room_emit = None
_started = [False]


class _Net:
    """One network's held state."""

    def __init__(self):
        self.results, self.read_at, self.failed, self.timed = {}, {}, {}, {}
        self.dirty, self.deadline = set(), None
        self.value, self.value_at, self.assemble_at = None, 0.0, None
        self.head, self.head_at = None, 0.0
        self.viewed_at = 0.0
        self.tried_at = None      # a first computation's last attempt (retried every FAST_S)
        self.pushed, self.announced, self.announced_at = None, None, 0.0


def _net(name: str) -> _Net:
    n = _nets.get(name)
    if n is None:
        n = _nets[name] = _Net()
    return n


def _iso(epoch) -> str:
    from modules.attention import _iso as iso
    return iso(epoch)


def _base(key: str) -> str:
    """A source's declared name from its key: ``grafana_source@<id>`` and a repeated name's
    ``#<n>`` are the source they were made from."""
    return key.split("@", 1)[0].split("#", 1)[0]


def _keys(sources) -> list:
    """Each source's key, its name, made unique by position where two share one."""
    out, seen = [], {}
    for src in sources:
        name = getattr(src, "__name__", "source")
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name}#{seen[name]}")
    return out


def _wanted(key: str, names) -> bool:
    from modules.attention import SOURCE_KEYS

    base = _base(key)
    return (key in names or base in names
            or (_UNDECLARED in names and base not in SOURCE_KEYS))


def _network() -> str:
    from modules.nsot import listref
    return listref.active_name()


def _current() -> str:
    from modules.config import get_current_list_name
    return get_current_list_name()


def _exists(name: str) -> bool:
    from modules.nsot import listref
    return listref.exists(name)


# ── reading the held value ─────────────────────────────────────────────────────────────────

def reads() -> int:
    """How many times a held value was read (by `read` or `badge`): display only is held by
    counting these, through the real code (tests/test_attention_display_only.py)."""
    return _reads[0]


def runs() -> dict:
    """How many times each source was computed, by its key: what the one-recompute test
    counts."""
    with _lock:
        return dict(_runs)


def reading(network: str) -> dict:
    """The page before its network's first value lands: nothing claimed, "Reading …" drawn,
    filled when the value is pushed."""
    return {"ok": True, "headline": "Reading Needs attention", "rows": [], "unreadable": [],
            "acknowledged": [], "in_force": [], "badge": None, "expected": [], "sources": [],
            "store": {"state": "reading", "checked_at": None, "oldest_at": None,
                      "failed": []}}


def _live(network: str) -> dict:
    """A test session's read: `attention.needs_attention()` computed now for *network*, as every
    read was before C3166 (a test that stands in for it is read), with the store's own fields:
    read now, its oldest source's read, no refresh failed."""
    from modules import attention as A
    from modules.nsot import listref

    with listref.computing_for(network):
        page = dict(A.needs_attention())
    now = _iso(_clock())
    read_times = sorted(s["read_at"] for s in page.get("sources") or [] if s.get("read_at"))
    page.setdefault("store", {"state": "read", "checked_at": now,
                              "oldest_at": read_times[0] if read_times else now, "failed": []})
    return page


def read(network: str = None) -> dict:
    """The page for *network* (the request's own, by default) as the background holds it, a
    copy for this caller; `reading(network)` before its first value. Never computes (but in a
    test session, `COMPUTE_ON_READ`). Counts as a view of the network."""
    name = network or _network()
    with _lock:
        _reads[0] += 1
        n = _net(name)
        n.viewed_at = _clock()
        held = n.value
    if COMPUTE_ON_READ:
        return _live(name)
    if held is None:
        _wake.set()
        return reading(name)
    return copy.deepcopy(held)


def badge(network: str = None):
    """*network*'s badge as held (`attention.badge_of`'s), a copy with ``at``, when it was
    assembled (a page drops a pushed badge older than the one it drew); None before its first
    value. Never computes (but in a test session). Counts as a view of the network."""
    name = network or _network()
    if COMPUTE_ON_READ:
        page = read(name)
        return dict(page["badge"], at=page["store"]["checked_at"]) if page["badge"] else None
    with _lock:
        _reads[0] += 1
        n = _net(name)
        n.viewed_at = _clock()
        held = n.value
    if held is None:
        _wake.set()
        return None
    return dict(held["badge"], at=held["store"]["checked_at"])


# ── events ─────────────────────────────────────────────────────────────────────────────────

def _touched(keys) -> set:
    """The sources (by declared name) a change under *keys* moves, `_ASSEMBLE` for an
    acknowledgement, and `_UNDECLARED` for any source that declares nothing (only a test's)."""
    from modules.attention import SOURCE_KEYS

    keys = set(keys or ()) - {"attention"}         # the store's own announcement moves nothing
    if not keys:
        return set()
    out = {name for name, ks in SOURCE_KEYS.items() if keys & set(ks)}
    if "acknowledgements" in keys:
        out.add(_ASSEMBLE)
    out.add(_UNDECLARED)
    return out if out - {_UNDECLARED} or _undeclared_sources() else set()


def _undeclared_sources() -> bool:
    """Whether any source in `attention.SOURCES` declares no keys (a test's planted source;
    tests/test_attention_badge.py holds SOURCES and SOURCE_KEYS equal in the product)."""
    from modules import attention as A

    return any(_base(k) not in A.SOURCE_KEYS for k in _keys(A.SOURCES))


def mark(keys, by: str = "") -> None:
    """A change under *keys* (an announcement, or a mutating route's declared invalidation):
    the sources it moves are marked in every held network, computed once DEBOUNCE_S after the
    first mark of a burst. Cheap and never raises into its caller's change.

    An acknowledgement (a person's own press, whose page redraws on its response) re-assembles
    every held network at once, reading no source: the acknowledged row has left the held
    value before the response is sent, so the acting page's redraw and its count are already
    right, and every other open page is told. Only when no computation holds the store: one
    that does assembles after it from the same mark, so the press never waits on it."""
    touched = _touched(keys)
    if not touched:
        return
    now = _clock()
    with _lock:
        for n in _nets.values():
            n.dirty |= touched
            if n.deadline is None:
                n.deadline = now + DEBOUNCE_S
        held = [name for name, n in _nets.items() if n.value is not None]
    if _ASSEMBLE in touched and held and _compute.acquire(blocking=False):
        try:
            for name in held:
                refresh(name, compute=False)
        except Exception as exc:                      # noqa: BLE001 (the debounce assembles it)
            log.error("attention store: an acknowledgement's assembly failed: %s", exc)
        finally:
            _compute.release()
    _wake.set()


# ── computing ──────────────────────────────────────────────────────────────────────────────

def ensure(network: str):
    """*network*'s first value: computed unless one is held when the computation's turn comes
    (the warm-up and the worker both ask for it at start; one computes)."""
    with _compute:
        with _lock:
            held = _nets.get(network)
            if held is not None and held.value is not None:
                return held.value
        return refresh(network)


def refresh(network: str, names=None, *, publish: bool = True, compute: bool = True):
    """Compute *names* (each source when None; a source never computed is computed whatever
    *names* says) for *network* now, keep each result with its read time, assemble the page
    and hold it; then push the badge and tell the list, when what they draw moved (unless
    not *publish*). A source whose adapter raises keeps its last good value and says its
    refresh failed. Not *compute*: no source is read, the page is assembled again from what
    is held (an acknowledgement, `mark`). The worker's one step and the warm-up's. (The worker
    asks only for networks that exist, `_known`.)"""
    from modules import attention as A
    from modules.nsot import listref

    with _compute:
        with listref.computing_for(network):
            sources = A.every_source()
            keys = _keys(sources)
            with _lock:
                n = _net(network)
                have = set(n.results)
            for key, src in zip(keys, sources):
                if not compute:
                    break
                if not (names is None or key not in have or _wanted(key, names)):
                    continue
                res, error = A.run_source(src)
                stamp = _clock()
                with _lock:
                    _runs[key] = _runs.get(key, 0) + 1
                    kept = n.results.get(key)
                    if error and kept is not None and kept.get("state") == "read":
                        n.failed[key] = {"at": _iso(stamp), "error": error}
                    else:
                        n.results[key] = res
                        n.failed.pop(key, None)
                    n.read_at[key] = stamp
            with _lock:
                for gone in set(n.results) - set(keys):
                    n.results.pop(gone, None)
                    n.read_at.pop(gone, None)
                    n.failed.pop(gone, None)
                results = [copy.deepcopy(n.results[k]) for k in keys if k in n.results]
                failed = {n.results[k]["source"]: dict(v, label=n.results[k]["label"])
                          for k, v in n.failed.items() if k in n.results}
                read_times = [n.read_at[k] for k in keys if k in n.read_at]
                timed = {k: _clears_at(n.results[k]) for k in keys if k in n.results}
            page = A.assemble(results)
        now = _clock()
        for line in page["sources"]:
            if line["source"] in failed:
                line["failed"] = {"at": failed[line["source"]]["at"],
                                  "error": failed[line["source"]]["error"]}
        page["store"] = {"state": "read", "checked_at": _iso(now),
                         "oldest_at": _iso(min(read_times)) if read_times else _iso(now),
                         "failed": sorted(v["label"] for v in failed.values())}
        with _lock:
            n.value, n.value_at = page, now
            n.timed = {k: t for k, t in timed.items() if t}
            n.assemble_at = _ack_ends(page)
    if publish:
        _publish(network, page)
    return page


def _clears_at(result: dict):
    """The soonest moment one of *result*'s rows clears by time, as an epoch; None if none."""
    from modules.attention import _ts

    at = [_ts(r.get("clears_at")) for top in result.get("rows") or []
          for r in [top] + (top.get("folded") or []) if r.get("clears_at")]
    at = [t for t in at if t]
    return min(at) if at else None


def _ack_ends(page: dict):
    """When an acknowledgement with a declared expiry ends, and its row comes back."""
    from modules.attention import _ts

    at = [_ts(k.get("until")) for k in page.get("acknowledged") or [] if k.get("expires")]
    at = [t for t in at if t]
    return min(at) if at else None


def _head(network: str) -> str:
    """*network*'s repository head ("" when it has none, or it cannot be read): what moves
    when a commit lands. One `git rev-parse`, about 3 ms."""
    from modules.nsot import listref
    from modules.nsot.repo import has_repository, run_git

    try:
        repo = listref.resolve(network).repo_dir
        if not has_repository(repo):
            return ""
        proc = run_git(repo, "rev-parse", "HEAD", timeout=10)
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception as exc:                          # noqa: BLE001 (read at the next cadence)
        log.warning("attention store: %s's head could not be read: %s", network, exc)
        return ""


def cadence(n: _Net, key: str, viewed: bool):
    """How long *key*'s held result stands on network *n* before it is computed again: None
    for an ON_HEAD source (its head decides), FAST_S while viewed or while it alerts (it has
    rows, could not be read, or its last refresh failed), else SLOW_S."""
    if _base(key) in ON_HEAD:
        return None
    res = n.results.get(key) or {}
    alerting = bool(res.get("rows")) or res.get("state") not in ("read", None) \
        or key in n.failed
    return FAST_S if (viewed or alerting) else SLOW_S


def _viewed(name: str, n: _Net, now: float) -> bool:
    return name in _watchers.values() or now - n.viewed_at <= VIEWED_S


def _known(now: float) -> list:
    """The networks the worker keeps: the installation's own, each a live connection shows,
    and each held, less those nobody viewed for FORGET_S and those deleted (computing one
    would make its folder again, C638)."""
    try:
        own = _current()
    except Exception as exc:                          # noqa: BLE001
        log.warning("attention store: the installation's network could not be read: %s", exc)
        own = ""
    names = set(_nets) | set(_watchers.values()) | ({own} if own else set())
    for name in sorted(names):
        idle = name != own and name not in _watchers.values() and (
            name not in _nets or now - _nets[name].viewed_at > FORGET_S)
        try:
            gone = not _exists(name)
        except Exception as exc:                      # noqa: BLE001 (kept: asked again next pass)
            log.warning("attention store: whether %s exists could not be read: %s", name, exc)
            gone = False
        if gone or (idle and name in _nets):
            _nets.pop(name, None)
            names.discard(name)
    return sorted(names)


def _plan(now: float) -> list:
    """What is due at *now*: ``(network, names or None, whether its head is due)`` per
    network, each network's marked sources taken off its marks."""
    out = []
    with _lock:
        for name in _known(now):
            n = _net(name)
            if n.value is None:
                # Never computed: at once, and a first computation that failed again after
                # FAST_S, never in a loop.
                if n.tried_at is None or now - n.tried_at >= FAST_S:
                    n.tried_at = now
                    out.append((name, None, False))
                continue
            todo = set()
            if n.deadline is not None and now >= n.deadline:
                todo |= n.dirty
                n.dirty, n.deadline = set(), None
            viewed = _viewed(name, n, now)
            for key, at in n.read_at.items():
                every = cadence(n, key, viewed)
                if every is not None and now - at >= every:
                    todo.add(key)
            todo |= {k for k, t in n.timed.items() if now >= t}
            if n.assemble_at and now >= n.assemble_at:
                todo.add(_ASSEMBLE)
            head_due = now - n.head_at >= (FAST_S if viewed else SLOW_S)
            if todo or head_due:
                out.append((name, todo, head_due))
    return out


def step(now: float = None) -> int:
    """The worker's one pass at *now*: every network's due sources computed, each network's in
    one refresh (one assembly, one push). Returns how many networks were refreshed."""
    now = _clock() if now is None else now
    done = 0
    for name, todo, head_due in _plan(now):
        if head_due:
            head = _head(name)
            with _lock:
                n = _net(name)
                moved = n.head is not None and head != n.head
                n.head, n.head_at = head, now
            if moved:
                todo = set(todo) | set(ON_HEAD)
        if todo is None or todo:
            try:
                ensure(name) if todo is None else refresh(name, todo)
                done += 1
            except Exception as exc:                  # noqa: BLE001 (kept; its age says so)
                log.error("attention store: %s could not be computed (its last value is kept "
                          "and its age shows it): %s", name, exc)
    return done


def _seconds_to_next(now: float) -> float:
    """How long the worker may sleep: until the soonest debounce, cadence, timed row,
    acknowledgement end or head check of any held network."""
    soon = [SLOW_S]
    with _lock:
        for name, n in _nets.items():
            if n.value is None:
                soon.append(0.0 if n.tried_at is None else n.tried_at + FAST_S - now)
                continue
            viewed = _viewed(name, n, now)
            if n.deadline is not None:
                soon.append(n.deadline - now)
            for key, at in n.read_at.items():
                every = cadence(n, key, viewed)
                if every is not None:
                    soon.append(at + every - now)
            soon += [t - now for t in n.timed.values()]
            if n.assemble_at:
                soon.append(n.assemble_at - now)
            soon.append(n.head_at + (FAST_S if viewed else SLOW_S) - now)
    return max(0.0, min(soon))


def run(stop: threading.Event = None) -> None:
    """The worker: a pass, then sleep until the next thing is due or a mark wakes it."""
    while stop is None or not stop.is_set():
        _wake.clear()
        try:
            step()
        except Exception as exc:                      # noqa: BLE001 (the loop goes on)
            log.error("attention store: a pass failed: %s", exc)
        # At least 0.2 s between passes: a source due at once again (a clock step) cannot spin.
        _wake.wait(timeout=max(0.2, _seconds_to_next(_clock())))


def start(spawn=None) -> bool:
    """Start the worker once a process (the app's start-up, `_start_background_daemons`);
    *spawn* starts ``spawn(target)``. False when it was already started."""
    with _lock:
        if _started[0]:
            return False
        _started[0] = True
    if spawn is None:
        threading.Thread(target=run, name="nmas-attention-store", daemon=True).start()
    else:
        spawn(run)
    return True


def clear() -> None:
    """Everything held, dropped (a test's start)."""
    with _lock:
        _nets.clear()
        _watchers.clear()
        _runs.clear()


# ── pushing ────────────────────────────────────────────────────────────────────────────────

def _badge_message(network: str, b: dict, at: str) -> dict:
    """What the live connection carries: the network and its badge's count, worst level, and
    the two moments the page marks (`next_change_at`, `stale_at`), and *at*, when it was
    assembled; counts and times only."""
    return {"network": network, "at": at,
            "badge": {k: b.get(k) for k in ("n", "level", "next_change_at", "stale_at",
                                            "unreadable")}}


def _drawn(page: dict) -> tuple:
    """What the list draws, less the reading times (those tick on the page by themselves)."""
    import json

    lines = [(s["source"], s["state"], s.get("checked"), s.get("count"),
              bool(s.get("failed"))) for s in page.get("sources") or []]
    return (json.dumps(page.get("rows"), sort_keys=True, default=str),
            json.dumps(page.get("acknowledged"), sort_keys=True, default=str),
            json.dumps(page.get("in_force"), sort_keys=True, default=str),
            tuple(page.get("unreadable") or ()), json.dumps(page.get("expected"), default=str),
            tuple(lines), tuple(page["store"].get("failed") or ()))


def _publish(network: str, page: dict) -> None:
    """Push the badge to the network's room when it moved, and announce `attention` when what
    the list draws moved (or REDRAW_S passed while it was read again)."""
    b = _badge_message(network, page["badge"], page["store"]["checked_at"])
    drawn = _drawn(page)
    now = _clock()
    with _lock:
        n = _net(network)
        push = b["badge"] != n.pushed
        tell = drawn != n.announced or now - n.announced_at >= REDRAW_S
        n.pushed = b["badge"]
        if tell:
            n.announced, n.announced_at = drawn, now
    if push and _room_emit is not None:
        try:
            _room_emit(PUSH_EVENT, b, ROOM_PREFIX + network)
        except Exception as exc:                      # noqa: BLE001 (the next change pushes)
            log.error("attention store: %s's badge was not pushed: %s", network, exc)
    if tell:
        from modules import invalidation
        try:
            invalidation.announce(["attention"], by=ANNOUNCED_BY)
        except Exception as exc:                      # noqa: BLE001 (no socket: nobody to tell)
            log.warning("attention store: the list was not told %s moved: %s", network, exc)


def watch(sid: str, network: str) -> None:
    """A page's live connection opened on *network*: it is viewed while the connection is."""
    with _lock:
        _watchers[sid] = network
        _net(network).viewed_at = _clock()
    _wake.set()


def unwatch(sid: str) -> None:
    with _lock:
        _watchers.pop(sid, None)


def _connection_network(request) -> str:
    """The network a page's live connection is about: the one the page names (`network` in
    the connection's address, nmas_invalidation.js reads it from the sidebar's count), else
    the person's own choice, else the installation's. Any person who can open a page can
    name any network on it (`?list=`), so naming one here shows nothing more."""
    named =str(request.args.get("network") or "").strip()
    if named and _exists(named):
        return named
    try:
        from modules import network_choice
        chosen = network_choice.for_request()
    except Exception:                                 # noqa: BLE001 (no identity: no choice)
        chosen = ""
    return chosen if chosen and _exists(chosen) else _current()


def install_socket(socketio) -> None:
    """The live connection's two handlers (registration only; nothing starts): a connection
    joins its network's room and is sent the badge held now (a page that connected after the
    last push, or reconnected, is current at once); a disconnection stops counting as a view.
    And the room's sender, for `_publish`."""
    global _room_emit
    from flask import request
    from flask_socketio import emit, join_room

    _room_emit = lambda event, msg, room: socketio.emit(event, msg, to=room)  # noqa: E731

    @socketio.on("connect")
    def _attention_connect(auth=None):
        try:
            network = _connection_network(request)
            watch(request.sid, network)
            join_room(ROOM_PREFIX + network)
            with _lock:
                held = _nets.get(network)
                msg = (_badge_message(network, held.value["badge"],
                                      held.value["store"]["checked_at"])
                       if held and held.value else None)
            if msg is not None:
                emit(PUSH_EVENT, msg)
        except Exception as exc:                      # noqa: BLE001 (the page still connects)
            log.warning("attention store: a connection's network was not joined: %s", exc)

    @socketio.on("disconnect")
    def _attention_disconnect(*_args):
        try:
            unwatch(request.sid)
        except Exception as exc:                      # noqa: BLE001
            log.warning("attention store: a disconnection was not counted: %s", exc)
