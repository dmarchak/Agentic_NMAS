"""The evidence pack: what Mercury gathers about a device when one of its alerts fires
(docs/PHASE8_PLAN.md 15.9, Card P1, its deterministic part; 15.1: built beside 8.0, it calls no
model and needs no 8.0 piece).

When an alert fires, a person gathers the evidence by hand: the alert, the device's recent
History, its Intent check, its expected and reported neighbours, the network around it as it
was observed (`observed`, C1712: captured here, so Explain never reads the network as it is
later), the health of the devices within two hops (`health`, C1714, `evidence_health`), and
the log lines around the onset, every time series read as of the alert's time (`build`'s
*now*). The pack gathers exactly those, once, when the `grafana-alerts` reader first stores the
alert as firing, and keeps them: one pack per firing alert, readable while it fires and after it
resolves (Monitoring › Alerts draws them). With AI off it is the answer on its own; Phase 8's
Explain call (P1's second half) cites its pieces, and a citation is checked against it.

**Triggered by the reader, never by a webhook** (C1656: Mercury takes no inbound alert
webhook). The reader's after-store step (`after_alerts_read`) looks at every alert it stored as
firing (`kind == "condition"`: no-data and error are not firing, the reader's own rule) and
builds a pack for each one no pack holds yet, keyed by the alert instance's identity
(`alert_key`: the rule, its labels and when its condition first held; a re-fire after a resolve
is a new instance, so a new pack). At most `MAX_PER_RUN` are built per read, so a storm of
alerts delays the reader's announcement by a bounded amount; the rest are built at the next
read, and the tab names how many are waiting.

**Each piece names its source and when it was read, and carries its own reference** (C1657:
History rows and reader values carry no identifier, so the pack mints them): a section's
reference is its name (``logs``), a piece's is the section's name and its place
(``logs:3``). A source that could not be read is a section saying so, with why (`unreadable`),
never an empty one; absent (nothing to read: no device, no golden, no onset) and not
configured are their own states.

**It hashes itself** (`digest`: a sha256 over its canonical JSON, every key but ``hash``), so
the same inputs give the same hash and any changed piece moves it, and a later Explain call's
references are checked against the pack they cite (`resolve`).

**What leaves it is in the allowed class** (15.11): alert labels, the masked log lines, the
Intent check's STATE (match, differs, unknown, with counts), never a configuration line; every
string in the pack is masked by `redact.redact_text` before it is hashed or stored. A line
planted in an interface description or a log line is carried as data, unchanged by anything it
says: nothing here reads a piece's text to decide what to do.

**Where it is kept:** the records store `evidence_packs` (`records_db.STORES`, the setting
`records_store_evidence_packs`, `file` by default: ``evidence_packs.jsonl`` in the data folder,
one line per pack). It cannot be computed on demand: the alert leaves the reader's value when it
resolves, its History, intent state and neighbours move on, and computing it per request would
ask Loki, Prometheus and git once per alert per page load (the enterprise-scale rule).
"""

import hashlib
import json
import logging
import os
import time

log = logging.getLogger(__name__)

#: The pack's own shape; a reader of a later shape says it cannot read this one. 2 (C1712,
#: C1714, 2026-10-25) adds the `observed` and `health` sections; a pack of 1 stays readable
#: and says it holds neither (expand, then contract).
SCHEMA = 2
#: The records store (`records_db.STORES`) and its file.
STORE = "evidence_packs"
FILE_NAME = "evidence_packs.jsonl"
#: The sections, in the order a person reads them.
SECTIONS = ("alert", "device", "history", "intent", "neighbours", "observed", "health", "logs")
SECTION_WORDS = {"alert": "The alert", "device": "The device", "history": "Recent History",
                 "intent": "Intent check", "neighbours": "Neighbours",
                 "observed": "The network around it, as observed",
                 "health": "Health of the devices around it",
                 "logs": "Log lines around the onset"}
#: A build more than this before the clock is a replay of a past alert (`build`'s *now*): the
#: sections that read a store as it is now (History, the Intent check) say what they read.
REPLAY_SLACK_SECONDS = 300
#: A section's states. `empty` is a source read that held nothing; `absent`, nothing to read.
STATES = ("ok", "empty", "absent", "not_configured", "unreadable")
#: The log window around the onset: 15 minutes each side (the reader's alerts fire from 1 to
#: 13 minutes after their onset, a heartbeat window being up to 1337 s: the capture of
#: 2026-09-28), ended at the build when that is sooner.
LOGS_BEFORE_SECONDS = 900
LOGS_AFTER_SECONDS = 900
#: The most log lines a pack keeps: those nearest the onset, the rest counted.
LOG_LINES = 50
#: History's kinds a pack reads (`history_sources.KIND_FILTERS` keys): what ran on the device
#: and what happened to it, the History tab's Deploys and restores first.
HISTORY_KINDS = ("receipts", "golden", "intent", "restarts", "reloads", "windows")
HISTORY_DAYS = "7"
HISTORY_LIMIT = 20
#: Packs built per read of the alerts. Each asks Loki twice or three times, Prometheus four
#: times and git a few times; ten keep a storm's delay to the reader's announcement bounded.
#: A scale guard, not a measured bound: the build's time is unmeasured on the host.
MAX_PER_RUN = 10
#: Packs the tab draws that no longer fire, newest first; and firing cards per group.
EARLIER_SHOWN = 50
GROUP_SHOWN = 100


# ----------------------------------------------------------------------------- identity

def alert_key(inst: dict) -> str:
    """The alert instance's identity (8.6): its rule, its public labels, and when its
    condition first held (the Alertmanager's start where the rules view has none). A re-fire
    after a resolve holds again later, so it is a new key."""
    ident = [inst.get("rule_uid") or inst.get("rule") or "",
             sorted([str(k), str(v)] for k, v in (inst.get("labels") or {}).items()),
             inst.get("active_at") or inst.get("starts_at") or ""]
    return hashlib.sha256(json.dumps(ident, separators=(",", ":")).encode()).hexdigest()[:20]


def pack_id(key: str) -> str:
    return f"ep-{key}"


def firing(value: dict) -> list:
    """The instances a reader value holds as firing: the condition holds. No-data and error
    are the reader's other two kinds, never "firing" (grafana_alerts' first rule)."""
    return [i for i in (value or {}).get("instances") or [] if i.get("kind") == "condition"]


# ----------------------------------------------------------------------------- the hash

def canonical(obj) -> bytes:
    """The one byte form the hash is taken over: sorted keys, no spaces, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(pack: dict) -> str:
    return hashlib.sha256(canonical({k: v for k, v in pack.items() if k != "hash"})).hexdigest()


def intact(pack: dict) -> bool:
    """Whether the pack is the one that was hashed: its stored hash is its digest now."""
    return bool(pack.get("hash")) and digest(pack) == pack["hash"]


def references(pack: dict) -> list:
    """Every reference the pack mints, in order: each section's, then its pieces'."""
    out = []
    for s in pack.get("sections") or []:
        out.append(s["ref"])
        out += [p["ref"] for p in s.get("pieces") or []]
    return out


def resolve(pack: dict, ref: str):
    """The section or piece *ref* names, or None: a citation that resolves to nothing."""
    for s in pack.get("sections") or []:
        if s.get("ref") == ref:
            return s
        for p in s.get("pieces") or []:
            if p.get("ref") == ref:
                return p
    return None


#: The sections whose pieces each carry a read state of their own (one of STATES): a health
#: figure is measured or says why not. Every other piece's ``state`` is what it describes (an
#: alert's, an adjacency's, an intent check's), never whether it was read (C1761).
PIECES_READ_ON_THEIR_OWN = ("health",)


def read_state(pack: dict, ref: str) -> str:
    """Whether what *ref* names was read, one of STATES, or "" when it names nothing: a
    section's own state; a piece's section's, and, in a section of
    `PIECES_READ_ON_THEIR_OWN`, the piece's own when its section was read."""
    for s in pack.get("sections") or []:
        if s.get("ref") == ref:
            return s.get("state") or ""
        for p in s.get("pieces") or []:
            if p.get("ref") == ref:
                state = s.get("state") or ""
                if state in ("ok", "empty") and s.get("name") in PIECES_READ_ON_THEIR_OWN:
                    return p.get("state") or ""
                return state
    return ""


# ----------------------------------------------------------------------------- sections

def _now() -> float:
    """The clock every section's read time comes from (one seam, so a test fixes it)."""
    return time.time()


def _iso(ts) -> str:
    if ts is None or ts == "":
        return ""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))


def _section(name: str, source: str, read_at, state: str, why: str = "", pieces=(),
             **extra) -> dict:
    assert state in STATES, state
    return {"ref": name, "name": name, "words": SECTION_WORDS[name], "source": source,
            "read_at": read_at if isinstance(read_at, str) else _iso(read_at), "state": state,
            "why": why, "pieces": [dict(p, ref=f"{name}:{i}") for i, p in enumerate(pieces, 1)],
            **extra}


def _failed(exc) -> str:
    first = (str(exc).strip().splitlines() or [""])[0]
    return f"{type(exc).__name__}: {first}" if first else type(exc).__name__


def _alert_section(inst: dict, store: str, value_at: str, onset, basis: str) -> dict:
    silences = [{"id": s.get("id") or "", "created_by": s.get("created_by") or "",
                 "ends_at": s.get("ends_at") or "", "comment": s.get("comment") or "",
                 "unresolved": bool(s.get("unresolved"))} for s in inst.get("silences") or []]
    piece = {"rule": inst.get("rule") or "", "rule_uid": inst.get("rule_uid") or "",
             "kind": inst.get("kind") or "", "state": inst.get("state") or "",
             "value": inst.get("value") or "", "labels": dict(inst.get("labels") or {}),
             "active_at": inst.get("active_at") or "", "starts_at": inst.get("starts_at") or "",
             "fingerprint": inst.get("fingerprint") or "",
             "for_seconds": int(inst.get("for_seconds") or 0),
             "window_seconds": int(inst.get("window_seconds") or 0),
             "onset": _iso(onset), "onset_basis": basis, "silences": silences}
    return _section("alert", f"Grafana's alert state, as the {store} reader stored it",
                    value_at, "ok", pieces=[piece])


def _device_section(inst: dict, onset, basis: str):
    """``(section, ref, dev)``: the alert's device as Needs attention resolves it (by label,
    by line or by address, `attention._member`), and its network (`attention._device_networks`,
    every network's inventory); ref and dev are None when it is not one device of one
    network."""
    from modules import attention as A
    from modules import device_page
    from modules.nsot import listref

    source = "every network's inventory, as Needs attention resolves an alert's device"
    now = _now()
    inv, inv_why = A._inventory()
    member = A._member(dict(inst, onset=onset, onset_basis=basis), inv)
    if inv is None:
        return _section("device", source, now, "unreadable", inv_why), None, None
    name, note = member.get("device"), member.get("device_note") or ""
    if not name:
        return _section("device", source, now, "absent",
                        f"no one device: {note}"), None, None
    nets = A._device_networks()
    if nets is None:
        return _section("device", source, now, "unreadable",
                        "the networks' inventories could not be read"), None, None
    held = nets.get(name) or []
    if len(held) != 1:
        why = (f"{name} is in no network's inventory ({note})" if not held else
               f"{name} is in {len(held)} networks ({', '.join(held)}), so which one is not "
               "decided")
        return _section("device", source, now, "absent", why), None, None
    try:
        ref = listref.resolve(held[0])
        ref, dev = device_page.find_device(name, ref)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        return _section("device", source, now, "unreadable",
                        f"{name}'s row in {held[0]} could not be read ({_failed(exc)})"), None, None
    piece = {"device": dev.get("hostname") or name, "network": ref.name,
             "address": dev.get("ip") or "", "platform": dev.get("platform") or "",
             "device_from": member.get("device_from") or "", "note": note}
    return _section("device", source, now, "ok", pieces=[piece]), ref, dev


def _absent(name: str, source: str, why: str) -> dict:
    return _section(name, source, _now(), "absent", why)


def history_section(ref, host: str, until: float = None) -> dict:
    """The device's recent History: `history_sources.timeline`, the History tab's own reader,
    filtered to deploys and restores, goldens, intent, restarts, reloads and planned windows.
    *until* (a replay of a past alert) leaves out what History recorded after it, counted."""
    from modules import history_sources as HS

    source = (f"History (history_sources.timeline) for {host}: "
              + ", ".join(HISTORY_KINDS) + f", the last {HISTORY_DAYS} days")
    at = _now()
    try:
        got = HS.timeline(ref, host, kinds=HISTORY_KINDS, since_days=HISTORY_DAYS,
                          limit=HISTORY_LIMIT)
    except Exception as exc:                          # noqa: BLE001
        return _section("history", source, at, "unreadable", _failed(exc))
    events, errors = got.get("events") or [], list(got.get("errors") or [])
    if until is not None:
        cut = _iso(until)
        later = [e for e in events if (e.get("at") or "") > cut]
        if later:
            events = [e for e in events if (e.get("at") or "") <= cut]
            source += (f"; {len(later)} recorded after the alert's time {cut} left out, the "
                       "pack being of that time")
    pieces = [{"at": e.get("at") or "", "kind": e.get("kind") or "", "what": e.get("what") or "",
               "who": e.get("who_short") or "", "outcome": e.get("outcome") or "",
               "sha": (e.get("sha") or "")[:12], "detail": e.get("detail") or ""}
              for e in events]
    extra = {"errors": errors, "total": int(got.get("total") or len(events)),
             "subset": int(got.get("total") or 0) > len(events)}
    if not events and errors:
        return _section("history", source, at, "unreadable", "; ".join(errors), **extra)
    if not events:
        why = ("; ".join(got.get("unborn") or []) or
               f"nothing of these kinds recorded about {host} in the last {HISTORY_DAYS} days")
        return _section("history", source, at, "empty", why, **extra)
    return _section("history", source, at, "ok", pieces=pieces, **extra)


def intent_section(ref, dev: dict) -> dict:
    """The device's Intent check, its STATE only (15.11: the pack is in the allowed class):
    the deploy plan's own comparison (`intent_match`) of the committed golden against
    effective intent, as match, differs (with its counts) or unknown (with why). The lines
    that differ are configuration, and never enter the pack."""
    from modules.nsot import intent_match as IM
    from modules.nsot import manifest
    from modules.nsot import repo as R

    host = dev.get("hostname") or ""
    source = f"the Intent check (intent_match) of {host}'s committed golden"
    at = _now()
    try:
        _ident, entry = manifest.find_by_name(ref.repo_dir, host)
        golden = R.committed_golden_for(ref.repo_dir, entry) if entry else {}
    except Exception as exc:                          # noqa: BLE001
        return _section("intent", source, at, "unreadable",
                        f"the committed golden could not be read ({_failed(exc)})")
    if not golden.get("text"):
        return _section("intent", source, at, "absent",
                        f"{host} has no committed golden to compare with its intent")
    try:
        r = IM.intent_match(ref.repo_dir, ref.name, host, golden["text"],
                            platform=(dev.get("platform") or "").strip())
        first = r["state"] == "unknown" and IM.first_boot(ref.repo_dir, host)
    except Exception as exc:                          # noqa: BLE001
        return _section("intent", source, at, "unreadable", _failed(exc))
    piece = {"state": r["state"], "adds": int(r.get("adds") or 0),
             "removes": int(r.get("removes") or 0), "reordered": int(r.get("reordered") or 0),
             "words": (IM.first_boot_words(host) if first else IM.words(r)
                       if r["state"] != "unknown" else
                       f"cannot be compared: {r.get('why') or 'no reason recorded'}"),
             "why": r.get("why") or "", "golden_commit": (golden.get("commit") or "")[:7]}
    return _section("intent", source, at, "ok", pieces=[piece])


def neighbours_section(ref, dev: dict, as_of: float = None) -> dict:
    """The device's expected and reported neighbours: `neighbours.for_device`, the Neighbours
    tab's own view (committed intent against what Prometheus last scraped, and RIP from its
    reader), Prometheus asked as of *as_of* (the alert's time)."""
    from modules import neighbours as N

    host = dev.get("hostname") or ""
    source = (f"the Neighbours view of {host} (neighbours.for_device): committed intent, "
              "Prometheus's routing tables, the RIP reader")
    at = _now()
    try:
        view = N.for_device(ref, dev, at=as_of)
    except Exception as exc:                          # noqa: BLE001
        return _section("neighbours", source, at, "unreadable", _failed(exc))
    errors = list(view.get("errors") or [])
    protos = view.get("protocols") or []
    pieces = []
    for p in protos:
        pieces.append({"kind": "protocol", "proto": p.get("words") or p.get("proto") or "",
                       "measured": bool(p.get("measured")), "why": p.get("why") or "",
                       "as_of": p.get("as_of") or ""})
        for row in p.get("rows") or []:
            pieces.append({"kind": "adjacency", "proto": p.get("words") or p.get("proto") or "",
                           "peer": row.get("peer") or "", "address": row.get("address") or "",
                           "via": row.get("via") or "", "state": row.get("state") or "",
                           "words": row.get("words") or "", "at": row.get("at_iso") or "",
                           "as_of": row.get("as_of") or "", "managed": bool(row.get("managed"))})
    extra = {"errors": errors, "counts": dict(view.get("counts") or {})}
    if pieces:
        return _section("neighbours", source, at, "ok", pieces=pieces, **extra)
    if not view.get("configured", True):
        return _section("neighbours", source, at, "not_configured",
                        "Prometheus is not configured, so no adjacency is measured", **extra)
    if errors:
        return _section("neighbours", source, at, "unreadable", "; ".join(errors), **extra)
    why = (f"{host} has no committed intent, so none is expected, and it reports none"
           if view.get("no_intent") else
           f"{host}'s intent implies no adjacency and it reports none")
    return _section("neighbours", source, at, "empty", why, **extra)


def logs_section(ref, host: str, onset, now: float, client=None) -> dict:
    """The device's log lines around the onset, through History › Query's logs builder
    (`history_logq`: the query formed from choices, one token each, Mercury's heartbeat lines
    left out), masked by `redact_text` as every line Mercury shows: at most `LOG_LINES`, those
    nearest the onset, the rest counted."""
    from modules import history_logq as Q

    source = f"the network's Loki, through History › Query's logs builder, {host}'s lines"
    if onset is None:
        return _absent("logs", source, "the alert's onset is not recorded, so there is no time "
                                       "to read the lines around")
    start = onset - LOGS_BEFORE_SECONDS
    end = min(onset + LOGS_AFTER_SECONDS, now)
    # The builder reads its range to the minute: the minute before the start, the one after
    # the end.
    frm = Q._utc(int(start // 60) * 60, "%Y-%m-%d %H:%M")
    to = Q._utc(-(-int(end) // 60) * 60, "%Y-%m-%d %H:%M")
    spec, errs = Q.ask({"dev": [host], "show": "lines", "range": "custom", "from": frm,
                        "to": to})
    rng = Q.window(spec, now)
    window = {"from": _iso(rng["start"]), "to": _iso(rng["end"]), "words": rng["words"]}
    if errs or rng["error"]:
        return _section("logs", source, now, "unreadable", "; ".join(errs + [rng["error"]]
                                                                     if rng["error"] else errs),
                        window=window)
    try:
        if client is None:
            client = Q._client(ref.name, Q.wait(Q.limits(ref.name)))
        if not client.is_configured():
            return _section("logs", source, now, "not_configured",
                            f"no log store is configured for {ref.name} (its Loki card in "
                            "Settings)", window=window)
        disc = Q.discover(ref.name, rng["start"], rng["end"], client=client, now=now)
        if disc["state"] == "not_configured":
            return _section("logs", source, now, "not_configured", disc["error"], window=window)
        if disc["state"] != "ok":
            return _section("logs", source, now, "unreadable", disc["error"], window=window)
        built = Q.build(spec, disc, rng, [host])
        got = Q.lines(ref.name, spec, built, rng, client, now)
    except Exception as exc:                          # noqa: BLE001
        return _section("logs", source, now, "unreadable", _failed(exc), window=window)
    window["query"] = built["log_query"]
    if got["state"] == "error":
        return _section("logs", source, now, "unreadable", got.get("error") or "", window=window)
    rows = got.get("rows") or []
    total = got.get("total")
    total = len(rows) if total is None else int(total)
    near = sorted(rows, key=lambda r: abs(r["ns"] / 1e9 - onset))[:LOG_LINES]
    near.sort(key=lambda r: r["ns"])
    pieces = [{"at": r.get("iso") or "", "device": r.get("device") or "",
               "severity": r.get("sev"), "severity_word": r.get("sev_word") or "",
               "job": r.get("kind") or "", "text": r.get("text") or "",
               "after_onset": r["ns"] / 1e9 >= onset} for r in near]
    extra = {"window": window, "total": total, "subset": total > len(pieces)}
    if not pieces:
        return _section("logs", source, now, "empty",
                        f"Loki holds no line from {host} between {window['from']} and "
                        f"{window['to']}", **extra)
    return _section("logs", source, now, "ok", pieces=pieces, **extra)


#: An observed item's fields the pack keeps beside its id and kind (`network_model.observed`'s
#: entries): what was reported and when, never more.
OBSERVED_KINDS = {"routing": "adjacency", "cables": "cable"}


def observed_section(capture: dict, now: float, built: float) -> dict:
    """The network model's observed overlay around the device, CAPTURED now (C1712): the
    Topology reader's read as the alert was found firing (*now*, the alert's time), kept to
    the items touching a device within two hops, each with its id and the read's own time.
    Explain overlays this, never a later read. *capture* is `network_model.capture`'s."""
    source = ("the Topology reader's stored read (LLDP and the routing tables, from "
              "Prometheus), captured with the pack")
    as_of = _iso(now)
    words = f"as of {as_of}, the alert's time"
    if not capture.get("ok"):
        return _section("observed", source, built, "unreadable",
                        f"the network model could not be read ({capture.get('error')})",
                        as_of=as_of, as_of_words=words)
    ov = capture["overlay"]
    extra = {"as_of": as_of, "as_of_words": words, "observed_at": ov.get("read_at") or "",
             "subject": capture.get("subject") or "", "model": capture.get("version") or "",
             "hops": max([r["hop"] for r in (capture.get("reached") or {}).values()] or [0])}
    if ov.get("state") != "read":
        state = ov.get("cause") if ov.get("cause") in STATES else "unreadable"
        return _section("observed", source, built, state, ov.get("why") or "", **extra)
    pieces = []
    for key, kind in OBSERVED_KINDS.items():
        for oid, entry in sorted((ov.get(key) or {}).items()):
            pieces.append(dict(entry, id=oid, kind=kind))
    if not pieces:
        return _section("observed", source, built, "empty",
                        f"the read of {ov.get('read_at')} reports no adjacency or cable "
                        "touching these devices", **extra)
    return _section("observed", source, built, "ok", pieces=pieces, **extra)


def overlay_of(pack: dict) -> dict:
    """The observed overlay a pack keeps, in `network_model.observed`'s shape, for Explain to
    overlay (C1712): never a live read. A pack built before overlays were captured (schema 1)
    says so on every item."""
    from modules import network_model as NM

    sec = next((s for s in pack.get("sections") or [] if s.get("name") == "observed"), None)
    if sec is None:
        return NM.unread("observed state not captured with this pack")
    if sec.get("state") not in ("ok", "empty"):
        return dict(NM.unread(f"{sec.get('why') or 'not read'}, when the pack was built"),
                    as_of=sec.get("as_of") or "")
    out = {"state": "read", "why": "", "cause": "", "read_at": sec.get("observed_at") or "",
           "routing": {}, "cables": {}, "source": sec.get("source") or "",
           "as_of": sec.get("as_of") or ""}
    back = {kind: key for key, kind in OBSERVED_KINDS.items()}
    for p in sec.get("pieces") or []:
        key = back.get(p.get("kind"))
        if key and p.get("id"):
            out[key][p["id"]] = {k: v for k, v in p.items() if k not in ("id", "kind", "ref")}
    return out


def health_section(ref, host: str, capture: dict, onset, now: float, built: float,
                   prometheus=None, loki=None) -> dict:
    """The health figures of the alert's device and every device within two hops, over the
    incident's window, from 15 minutes before the onset to the alert's time (C1714;
    `evidence_health`): each a piece whose reference is ``health:<device id>:<figure>``."""
    from modules import evidence_health as H

    source = ("Prometheus (CPU, scrapes, interface discards) and Loki (the syslog heartbeat), "
              "for the alert's device and every device within two hops of it, one question "
              "each for them all, each summarised over the window")
    devices, total = H.devices_of(capture, host)
    got = H.read(ref.name, devices, onset, now, prom=prometheus, loki=loki)
    extra = {"window": got["window"], "as_of": _iso(now), "asked_at": _iso(built),
             "questions": got["asked"], "errors": got["errors"],
             "devices_total": total, "devices_kept": len(devices),
             "figures": {k: H.FIGURE_WORDS[k] for k in H.FIGURES}}
    if not capture.get("ok"):
        extra["errors"] = [f"the network model could not be read ({capture.get('error')}), "
                           "so only the alert's device is read"] + extra["errors"]
    pieces = [{k: v for k, v in p.items() if k != "ref"} for p in got["pieces"]]
    states = {p["state"] for p in pieces}
    if not pieces:
        return _section("health", source, built, "absent", "no device to read", **extra)
    if states <= {"not_configured"}:
        sec = _section("health", source, built, "not_configured",
                       "neither Prometheus nor a log store is configured for "
                       f"{ref.name}", pieces=pieces, **extra)
    elif states <= {"unreadable", "not_configured"}:
        sec = _section("health", source, built, "unreadable", "; ".join(got["errors"]),
                       pieces=pieces, **extra)
    else:
        sec = _section("health", source, built, "ok", pieces=pieces, **extra)
    # Each figure's reference is its stable id, the one an answer cites.
    for p, mine in zip(sec["pieces"], got["pieces"]):
        p["ref"] = mine["ref"]
    return sec


# ----------------------------------------------------------------------------- the pack

def build(inst: dict, *, store: str, value_at: str, now: float = None, loki=None,
          prometheus=None, observed_read: dict = None, trigger: str = "") -> dict:
    """One alert instance's pack, masked and hashed. Never raises: a source that fails is
    its section saying so. *now* is the alert's time, when it was found firing: every read of
    a time series (the neighbours, the observed topology, the health figures, the log lines)
    is as of it. *loki* and *prometheus* stand in for the network's clients (tests);
    *observed_read* for the Topology reader's stored read, in its store's shape (a replay of
    a past alert, `scripts/nmas-pack-replay`, gives the read made as of that time), and
    *trigger* for what made the pack (the replay's own words)."""
    from modules import attention as A
    from modules import network_model as NM
    from modules import redact

    clock = _now()
    now = clock if now is None else now
    replay = clock - now > REPLAY_SLACK_SECONDS
    onset, basis = A._onset(inst)
    sections = [_alert_section(inst, store, value_at, onset, basis)]
    try:
        dev_section, ref, dev = _device_section(inst, onset, basis)
    except Exception as exc:                          # noqa: BLE001
        dev_section, ref, dev = (_section("device", "every network's inventory", now,
                                          "unreadable", _failed(exc)), None, None)
    sections.append(dev_section)
    host = (dev or {}).get("hostname") or ""
    if ref is None:
        why = f"no device to read for: {dev_section['why']}"
        for name in ("history", "intent", "neighbours", "observed", "health", "logs"):
            sections.append(_absent(name, "", why))
    else:
        sections.append(history_section(ref, host, until=now if replay else None))
        intent = intent_section(ref, dev)
        if replay:
            intent["source"] += (f"; the committed golden and intent as they are at "
                                 f"{_iso(clock)}, not as of the alert's time {_iso(now)}")
        sections.append(intent)
        sections.append(neighbours_section(ref, dev, as_of=now))
        try:
            cap = NM.capture(ref.name, host, hops=NM.CAPTURE_HOPS, now=now,
                             stored=observed_read)
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            cap = {"ok": False, "error": _failed(exc)}
        sections.append(observed_section(cap, now, clock))
        try:
            sections.append(health_section(ref, host, cap, onset, now, clock,
                                           prometheus=prometheus, loki=loki))
        except Exception as exc:                      # noqa: BLE001
            sections.append(_section("health", "Prometheus and Loki", clock, "unreadable",
                                     _failed(exc)))
        sections.append(logs_section(ref, host, onset, now, client=loki))
    key = alert_key(inst)
    pack = {"schema": SCHEMA, "id": pack_id(key), "alert_key": key, "built_at": _iso(now),
            "store": store, "rule": inst.get("rule") or "", "device": host,
            "network": ref.name if ref is not None else "", "onset": _iso(onset),
            "trigger": trigger or (f"the {store} reader stored this alert as firing (its "
                                   f"value of {value_at or 'an unrecorded time'})"),
            "sections": sections}
    if replay:
        pack["replayed_at"] = _iso(clock)
    # Masked BEFORE it is hashed or kept: what is hashed is what is stored and shown.
    pack = redact.redact_payload(pack)
    pack["hash"] = digest(pack)
    return pack


# ----------------------------------------------------------------------------- the store

def _path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, FILE_NAME)


def record(pack: dict) -> dict:
    """Append one pack to the store: ``{"ok", "error"}``, the failure said, never raised."""
    from modules import records_migrate

    try:
        records_migrate.store_append(STORE, _path(), pack)
    except Exception as exc:                          # noqa: BLE001
        log.error("evidence_pack: COULD NOT KEEP the pack for %s on %s (%s)",
                  pack.get("rule"), pack.get("device") or "no device", exc)
        return {"ok": False, "error": _failed(exc)}
    return {"ok": True, "error": ""}


def read() -> dict:
    """Every pack, oldest first: ``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``.
    A store that cannot be read is said, never an empty one. A torn line is skipped, as the
    reveal record skips one (C1327), so one bad line never hides every pack."""
    from modules import records_migrate

    got = records_migrate.store_rows(STORE, _path(), skip_unparsable=True)
    if got["state"] == "unreadable":
        log.error("evidence_pack: the store is unreadable (%s)", got["error"])
    return got


def known_keys():
    """The alert keys the store holds packs for, or None when it cannot be read (then no pack
    is built: building blind would build each alert's pack again)."""
    got = read()
    if got["state"] == "unreadable":
        return None
    return {r.get("alert_key") for r in got["rows"]}


def find(pid: str):
    """``(pack or None, store state, error)``: the newest pack with id *pid*."""
    got = read()
    match = [r for r in got["rows"] if r.get("id") == pid]
    return (match[-1] if match else None), got["state"], got["error"]


# ----------------------------------------------------------------------------- the trigger

def _alert_stores() -> list:
    """Every store the alerts reader keeps: Default's Grafana's, and each other network's
    configuration's (P.8 step 5)."""
    from modules import reader_job
    from modules.readers import grafana_alerts as G

    try:
        return [r.name for r in reader_job.configuration_readers(G.READER)]
    except Exception as exc:                          # noqa: BLE001
        log.warning("evidence_pack: the alert configurations could not be listed (%s); "
                    "Default's is read", exc)
        return [G.READER.name]


def after_alerts_read(clock=time.time, loki=None) -> bool:
    """The alerts reader's after-store step: a pack for each firing alert no pack holds yet,
    at most `MAX_PER_RUN`. True when it built one (the reader then announces `alerts`, and
    the tab redraws with it). Never raises."""
    from modules import reader_job

    built = 0
    for name in _alert_stores():
        got = reader_job.read_cached(name)
        good = ((got.get("doc") or {}).get("last_good") or {})
        todo = firing(good.get("value") or {})
        if not todo:
            continue
        known = known_keys()
        if known is None:
            log.error("evidence_pack: the store cannot be read, so no pack is built for %d "
                      "firing alert(s) in %s", len(todo), name)
            return built > 0
        # Serial, by decision: no device is asked (each pack reads Mercury's stores, git, Loki
        # and Prometheus), at most MAX_PER_RUN are built per read, and one question at a time
        # from the reader's thread keeps a storm of alerts from becoming a storm of queries.
        for inst in todo:
            key = alert_key(inst)
            if key in known:
                continue
            if built >= MAX_PER_RUN:
                log.info("evidence_pack: %d packs built this read, the most per read; the "
                         "rest are built at the next", built)
                return True
            pack = build(inst, store=name, value_at=good.get("value_at") or "",
                         now=clock(), loki=loki)
            if not record(pack)["ok"]:
                return built > 0
            known.add(key)
            built += 1
    return built > 0


# ----------------------------------------------------------------------------- the tab

def _card(inst: dict, store: str, pack) -> dict:
    labels = inst.get("labels") or {}
    who = inst.get("device") or inst.get("address") or ""
    card = {"key": alert_key(inst), "rule": inst.get("rule") or "?", "store": store,
            "device": (pack or {}).get("device") or who, "network": (pack or {}).get("network")
            or "", "onset": (pack or {}).get("onset") or "", "state": inst.get("state") or "",
            "silenced": bool(inst.get("silenced_by")), "since": inst.get("starts_at")
            or inst.get("active_at") or "", "summary_labels": ", ".join(
                f"{k}={v}" for k, v in sorted(labels.items())
                if k not in ("alertname", "grafana_folder", "__name__")),
            "pack": None}
    if pack:
        card["pack"] = pack_summary(pack)
    return card


def pack_summary(pack: dict) -> dict:
    """What a card's closed line says of its pack: its id, when it was built, its hash, how
    many pieces, and which sections could not be read or held nothing to read."""
    sections = pack.get("sections") or []
    return {"id": pack.get("id"), "built_at": pack.get("built_at") or "",
            "hash": pack.get("hash") or "", "intact": intact(pack),
            "pieces": sum(len(s.get("pieces") or []) for s in sections),
            "not_read": [s.get("words") or s.get("name") for s in sections
                         if s.get("state") == "unreadable"],
            "device": pack.get("device") or "", "network": pack.get("network") or "",
            "onset": pack.get("onset") or "", "rule": pack.get("rule") or ""}


def tab(q: str = "") -> dict:
    """Monitoring › Alerts: every firing alert, grouped by rule, each with its pack's summary
    (or that it is waiting for one), and the packs of alerts no longer firing, newest first.
    Reads the alerts reader's stores and the pack store, once each: no source is asked."""
    from modules import reader_job

    q = (q or "").strip()[:80]
    sources, firing_now = [], []
    for name in _alert_stores():
        got = reader_job.read_cached(name)
        good = ((got.get("doc") or {}).get("last_good") or {})
        sources.append({"store": name, "value_at": good.get("value_at") or "",
                        "state": got["state"] if good else "not_read",
                        "why": got.get("why") or ((got.get("doc") or {}).get("last_attempt")
                                                  or {}).get("error") or ""})
        firing_now += [(name, i) for i in firing(good.get("value") or {})]
    store = read()
    latest = {}
    for p in store["rows"]:
        latest[p.get("alert_key")] = p
    cards = [_card(i, name, latest.get(alert_key(i))) for name, i in firing_now]
    keys = {c["key"] for c in cards}
    want = q.lower()

    def matches(*texts):
        return not want or any(want in (t or "").lower() for t in texts)

    shown = [c for c in cards if matches(c["rule"], c["device"], c["summary_labels"])]
    groups = {}
    for c in shown:
        groups.setdefault(family(c["rule"], c["device"]), []).append(c)
    earlier_all = [pack_summary(p) for p in reversed(store["rows"])
                   if p.get("alert_key") not in keys]
    earlier_all = [e for e in earlier_all if matches(e["rule"], e["device"])]
    return {"q": q, "sources": sources, "store": {"state": store["state"],
                                                  "error": store["error"]},
            "counts": {"firing": len(cards), "packed": sum(1 for c in cards if c["pack"]),
                       "waiting": sum(1 for c in cards if not c["pack"]),
                       "shown": len(shown), "earlier": len(earlier_all)},
            "groups": [{"family": f, "count": len(cs), "cards": cs[:GROUP_SHOWN]}
                       for f, cs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))],
            "earlier": earlier_all[:EARLIER_SHOWN], "max_per_run": MAX_PER_RUN}


#: Monitoring › Alerts' address (routes/v2.monitoring_alerts), for a row outside a request.
TAB_PATH = "/v2/monitoring/alerts"


def card_href(instances) -> str:
    """Where a Needs attention row about *instances* opens their evidence: one firing alert's
    own card (opened), the tab for several, "" when none is firing (no pack is built for an
    alert reading no data or not evaluating)."""
    lit = [i for i in instances or () if i.get("kind") == "condition"]
    if not lit:
        return ""
    return f"{TAB_PATH}?open={alert_key(lit[0])}" if len(lit) == 1 else TAB_PATH


def family(rule: str, device: str) -> str:
    """The group a card is drawn under: its rule, less the device a rule generated per device
    names in its title ("NMAS heartbeat missing: edge1" is one of "NMAS heartbeat missing"), so a
    fleet's heartbeats are one group, never one heading per device."""
    tail = f": {device}" if device else ""
    return rule[:-len(tail)] if tail and rule.endswith(tail) else rule
