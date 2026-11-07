"""Flap detection: the `logs-tail` reader's after-store step that records each interface's
UPDOWN transitions, for guard 13e (board H's amendment, item 2, part H19; docs/HEAL_TO_INTENT.md
19.4, N18). Deterministic; it reads no device and calls no model.

**A flap is measured, not felt.** At least ``heal_flap_transitions`` (3) transitions of one
interface in ``heal_flap_minutes`` (10), each network's own (`policy.current`'s guards). A
transition is a change of the interface's logged state, down or up, from IOS's own lines,
``%LINK-3-UPDOWN`` (``Interface <if>, changed state to <state>``) and ``%LINEPROTO-5-UPDOWN``
(``Line protocol on Interface <if>, changed state to <state>``): the link going down and its
line protocol following it are one transition, not two. An interface shut by a person logs
``%LINK-5-CHANGED`` (administratively down), which is no flap. The stability window (H20's
verify) is the same minutes: the transitions since the bounce (`transitions`).

**A planned window's transitions are the operation's, never a flap** (C2694, H20): guard 13e's
count (`flapping`) leaves out each transition received inside a planned window that takes the
interface down on purpose (`planned_spans`): one naming the device and that interface (the port
bounce declares one before it sends, `bounce.declare_window`), or one naming the whole device (a
planned restart takes every port down). The record keeps every transition; only the count
leaves them out, and says how many. Planned windows that cannot be read leave the count
unreadable, never read as none. The bounce's own stability window reads the transitions whole
(`transitions`), after its own up.

**Times are the collector's receive times** (each line's ``ts``, from Loki), never the device's
clock or its uptime (CLAUDE.md: slow vIOS clocks).

**Where it runs, and its bounds.** On the reader that already reads every device's syslog
once per interval (every 5 s, one query for the whole fleet), after it stored: no per-device
work per request, and no device is read. Each line is taken once (the store's cursor, its
newest receive time); a line's device is placed in the one network holding it, as the heal
triggers place it (`triggers._one_network`), and only where healing is on (a network whose
mode is off records nothing; its lines are still consumed). The record keeps `KEEP_SECONDS`
(an hour, the bounce's once-an-hour window and the longest flap window the schema allows) and
at most `MAX_KEPT` transitions an interface, the newest: more than the most a flap can ask for
(the schema's 100). It is one file, `<data>/heal/flaps.json`, changed under its lock across
processes and replaced atomically. It draws nowhere yet, so it announces nothing; a step that
fails is logged, and the reader goes on (`reader_job`'s rule).
"""

import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

READER = "logs-tail"
MNEMONICS = ("%LINK-3-UPDOWN", "%LINEPROTO-5-UPDOWN")
#: The interface and its new state, in the text after the mnemonic.
_TEXT = re.compile(r"^(?:Line protocol on )?Interface (?P<iface>[A-Za-z][\w./:-]{0,47}), "
                   r"changed state to (?P<state>up|down)\s*$")
#: How long transitions are kept: an hour (13d's window; the schema's longest flap window).
KEEP_SECONDS = 3600
#: The most transitions kept an interface (the schema's most `heal_flap_transitions`, 100).
MAX_KEPT = 100
DIR = "heal"
FILE = "flaps.json"

_installed = {"on": False}


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def transition_of(line: dict):
    """``(interface, state)`` for one of the reader's lines that is an UPDOWN line, or None."""
    if (line or {}).get("mn") not in MNEMONICS:
        return None
    m = _TEXT.match((line.get("text") or "").strip())
    return (m.group("iface"), m.group("state")) if m else None


# ── Installation ────────────────────────────────────────────────────────────────────────────

def install() -> None:
    """Run the step after every reader store (`reader_job.after_any_store`), where the readers
    start (`reader_job.start`)."""
    from modules import reader_job

    if not _installed["on"]:
        reader_job.after_any_store(_after_store)
        _installed["on"] = True


def uninstall() -> None:
    from modules import reader_job

    reader_job.after_any_store(_after_store, remove=True)
    _installed["on"] = False


def _after_store(reader, moved: bool = True) -> None:
    """A `logs-tail` store whose lines moved: its step. Never raises."""
    from modules import reader_job

    base = (getattr(reader, "name", "") or "").split("@", 1)[0]
    if base != READER or not moved:
        return
    try:
        got = reader_job.read_cached(reader.name)
        value = ((got.get("doc") or {}).get("last_good") or {}).get("value")
        if isinstance(value, dict):
            from_logs_tail(reader.name, value)
    except Exception as exc:                          # noqa: BLE001 (never stops a reader)
        log.error("heal: the flap step on %s failed: %s: %s", reader.name,
                  type(exc).__name__, exc)


# ── The record ──────────────────────────────────────────────────────────────────────────────

def _path() -> str:
    from modules import config

    return os.path.join(config.DATA_DIR, DIR, FILE)


def _read() -> dict:
    """The record, ``{}`` when absent; raises when it cannot be read (never read as quiet)."""
    p = _path()
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _move(fn):
    from modules import filestore

    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with filestore.PathLock(p):
        doc = filestore.read_json_for_write(p, empty={})
        before = json.dumps(doc, sort_keys=True)
        out = fn(doc)
        if json.dumps(doc, sort_keys=True) != before:
            filestore.write_atomic(p, json.dumps(doc, indent=1, sort_keys=True))
    return out


def from_logs_tail(store: str, value: dict, now: float = None) -> dict:
    """The step: each UPDOWN line newer than *store*'s cursor, recorded on its network's
    interface. ``{"recorded", "off", "unplaced"}``."""
    from modules.heal import triggers as T

    now = time.time() if now is None else float(now)
    lines = sorted((value or {}).get("lines") or [], key=lambda l: float(l.get("ts") or 0))
    counts = {"recorded": 0, "off": 0, "unplaced": []}
    seen = None
    try:
        seen = (_read().get("cursors") or {}).get(store)
    except (OSError, ValueError) as exc:
        log.error("heal: the flap record cannot be read (%s); the step waits", exc)
        return counts
    new = [l for l in lines if seen is None or float(l.get("ts") or 0) > float(seen)]
    if not new:
        return counts
    ctx = T._Context(now)
    allowed = T._store_networks(store, READER)
    found = []
    for l in new:
        got = transition_of(l)
        if got is None:
            continue
        dev = l.get("dev") or ""
        network, why = T._one_network(ctx, dev, allowed)
        if network is None:
            counts["unplaced"].append(why)
            continue
        if ctx.mode(network) == "off":
            counts["off"] += 1
            continue
        found.append((network, dev, got[0], got[1], float(l.get("ts") or 0)))

    def write(doc):
        from modules.nsot import listref

        doc.setdefault("cursors", {})[store] = max(float(l.get("ts") or 0) for l in new)
        nets = doc.setdefault("networks", {})
        for network, dev, iface, state, ts in found:
            # Keyed by the network's one id (C1903), never its display name.
            entry = nets.setdefault(listref.network_id(network), {}).setdefault(
                dev, {}).setdefault(
                iface.lower(), {"interface": iface, "state": "", "transitions": []})
            if entry["state"] == state:
                continue                       # its line protocol following the link: one
            entry["state"] = state
            entry["transitions"].append([ts, state])
            counts["recorded"] += 1
        # The pruning walks the stored keys themselves (each already a network's id).
        for nid, devices in list(nets.items()):
            for dev, interfaces in list(devices.items()):
                for key, e in list(interfaces.items()):
                    e["transitions"] = [t for t in e["transitions"]
                                        if t[0] >= now - KEEP_SECONDS][-MAX_KEPT:]
                    if not e["transitions"]:
                        del interfaces[key]
                if not interfaces:
                    del devices[dev]
            if not devices:
                del nets[nid]

    _move(write)
    return counts


# ── The reads (13e, and H20's stability window) ─────────────────────────────────────────────

def transitions(network: str, device: str, interface: str, since: float,
                until: float = None) -> dict:
    """*device*'s *interface* transitions on *network* received in [*since*, *until*]:
    ``{"state", "transitions", "words"}``, *state* ``read`` or ``unreadable``; each transition
    ``{"epoch", "at", "state"}``, oldest first. A window reaching past `KEEP_SECONDS` is
    unreadable, never read as quiet."""
    until = time.time() if until is None else float(until)
    if since < until - KEEP_SECONDS:
        return {"state": "unreadable", "transitions": [],
                "words": (f"the window from {_iso(since)} is longer than the flap record keeps "
                          f"({KEEP_SECONDS // 60} minutes)")}
    try:
        doc = _read()
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "transitions": [],
                "words": f"the flap record cannot be read ({type(exc).__name__})"}
    from modules.nsot import listref

    try:
        held = listref.keyed(doc.get("networks") or {}, network) or {}
    except listref.UnknownList as exc:
        return {"state": "unreadable", "transitions": [],
                "words": f"no network {network!r} to read flaps for ({exc})"}
    e = (held.get(device) or {}).get((interface or "").lower()) or {}
    got = [{"epoch": t[0], "at": _iso(t[0]), "state": t[1]} for t in e.get("transitions") or []
           if since <= t[0] <= until]
    return {"state": "read", "transitions": got,
            "words": f"{len(got)} transition(s) of {device} {interface} logged"}


def planned_spans(network: str, device: str, interface: str, planned: list = None) -> list:
    """``[(from, until)]``, epoch seconds: the planned windows that take *device*'s *interface*
    down on purpose (C2694, H20): a window naming the device and that interface (a port bounce
    declares one, `bounce.declare_window`), or the whole device (a window naming no interface,
    a planned restart, takes every port down too). Raises when the planned windows cannot be
    read (never read as none)."""
    from modules import restarts
    from modules.nsot.ifnames import canonical

    rows = restarts.planned_rows() if planned is None else planned
    want = canonical(interface or "")
    out = []
    for p in rows:
        if not restarts._names(p, device, network):
            continue
        ports = p.get("interfaces")
        if ports and want not in {canonical(i) for i in ports}:
            continue
        start = restarts._epoch(p.get("from", ""))
        end = restarts._epoch(p.get("ended_at") or p.get("until", ""))
        out.append((start, min(end, restarts._epoch(p.get("until", "")))))
    return out


def flapping(network: str, device: str, interface: str, now: float, *, at_least: int,
             minutes: int, planned: list = None) -> dict:
    """Guard 13e's measurement: ``{"state", "flapping", "transitions", "planned",
    "at_least", "minutes", "device", "interface", "words"}``. A transition received inside a
    planned window that takes the interface down on purpose (`planned_spans`: Mercury's own
    bounce, or a planned restart) is the operation's, not a flap, and is left out of the count,
    which says how many it left out (C2694). Planned windows that cannot be read leave the
    record unreadable."""
    got = transitions(network, device, interface, now - float(minutes) * 60, now)
    out = {"state": got["state"], "flapping": False, "transitions": 0, "planned": 0,
           "at_least": int(at_least), "minutes": int(minutes), "device": device,
           "interface": interface}
    if got["state"] != "read":
        return dict(out, words=got["words"])
    try:
        spans = planned_spans(network, device, interface, planned)
    except Exception as exc:                          # noqa: BLE001 (said, never read as none)
        return dict(out, state="unreadable",
                    words=(f"the planned windows cannot be read ({type(exc).__name__}), so "
                           "which transitions were Mercury's own cannot be told"))
    mine = [t for t in got["transitions"] if any(a <= t["epoch"] <= b for a, b in spans)]
    n = len(got["transitions"]) - len(mine)
    out.update(transitions=n, planned=len(mine), flapping=n >= int(at_least))
    return dict(out, words=(f"{n} UPDOWN transition(s) of {device} {interface} in "
                            f"{int(minutes)} min (a flap is {int(at_least)})"
                            + (f", {len(mine)} more inside a planned window left out"
                               if mine else "")
                            + ": " + ("a flap" if out["flapping"] else "not a flap")))
