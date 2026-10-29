"""The evidence pack: what Mercury gathers about a device when one of its alerts fires
(docs/PHASE8_PLAN.md 15.9, Card P1, its deterministic part; 15.1: built beside 8.0, it calls no
model and needs no 8.0 piece).

When an alert fires, a person gathers the evidence by hand: the alert, the other alerts in its
network around the onset (`concurrent`, C1850, from the alert history), the device's recent
History, its Intent check, its expected and reported neighbours, the network around it as it
was observed (`observed`, C1712: captured here, so Explain never reads the network as it is
later), the health of the devices within two hops (`health`, C1714, `evidence_health`), the
monitoring side over the window (`observer`, C1896, `evidence_observer`: the scrape jobs polling
those devices across all their targets, the SNMP exporter, the host Prometheus runs on), and
the log lines around the onset, every time series read as of the alert's time (`build`'s
*now*). One device has one id in all of it: the network model's, wherever the model knows the
device (C1849). The pack gathers exactly those, once, when the `grafana-alerts` reader first
stores the alert as firing, and keeps them: one pack per firing alert, readable while it fires and after it
resolves (Monitoring › Alerts draws them). With AI off it is the answer on its own; Phase 8's
Explain call (P1's second half) cites its pieces, and a citation is checked against it.

**Triggered by the reader, never by a webhook** (C1656: Mercury takes no inbound alert
webhook). The reader's after-store step (`after_alerts_read`) looks at every alert it stored as
firing (`kind == "condition"`: no-data and error are not firing, the reader's own rule, but
for a rule whose no data is its fault, a heartbeat or a telemetry stream, Grafana's "Alerting
(NoData)" is firing, C2174, and its alert piece says what was absent, ``absence``) and
builds a pack for each one no pack holds yet, keyed by the alert instance's identity
(`alert_key`: the rule, its labels and when its condition first held; a re-fire after a resolve
is a new instance, so a new pack). At most `MAX_PER_RUN` are built per read, so a storm of
alerts delays the reader's announcement by a bounded amount; the rest are built at the next
read, and the tab names how many are waiting.

**An SDN detection is an alert too** (PHASE8_PLAN 17.1 S6, `modules/sdn/detect.py`, the store
``sdn``): its pack is built when the detection first fires, from the collection it rests on
(`build_detection`): the alert, the device (absent: a controller's switch is in no inventory)
and the ``sdn`` section, the flows and port rates cited by their evidence ids, captured at the
detection's time. Its firing instances join the tab's (`sdn_firing`). A Grafana alert's pack is
unchanged: ``sdn`` is not one of `SECTIONS`.

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
Intent check's state (match, differs, unknown, with counts) and, when it differs, the intent
difference's lines, masked (the operator's order of 2026-10-29, "WHO, guaranteed in code" (c):
15.11's "intent diffs"; `intent_section`), with who last committed the device's intent; never
a golden, a captured configuration or a deploy's program. Every string in the pack is masked
by `redact.redact_text` before it is hashed or stored, and the intent difference's lines by
`redact.redact_egress` too, the mask of what leaves the host, since they are kept only to be
read and sent. A line
planted in an interface description or a log line is carried as data, unchanged by anything it
says: nothing here reads a piece's text to decide what to do.

**A pack of an older schema can be built again, never rewritten** (C1862, Build again on its
card, routes/v2.monitoring_alert_pack_rebuild): a past alert's pack built from the alert history
as `build_for_episode` builds one, with this release's evidence, kept BESIDE the old pack under
its own id (`rebuilt_id`: the alert's id ending ``-s<schema>``) and naming it
(``rebuilt_from``). Both stay findable by id (`find`); where one pack stands for its alert (the
Alerts tab's list, History's row), the newest wins (`superseded`; History's own matching takes
the newest pack naming the episode), and Explain reads the pack it is pressed on.

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
#: and says it holds neither (expand, then contract). 3 (C1778, 2026-10-26) adds `endpoints`;
#: a pack of 2 stays readable and holds none. 4 (the alert history, 2026-10-26) marks every
#: section `provenance` (`PROVENANCE`) and the pack its own; a pack of 3 stays readable and is
#: drawn as not marked. 5 (C1849 to C1851, 2026-10-27) adds `concurrent`, the other alerts in
#: the network around the onset; names every device by the network model's id wherever the
#: model knows it (the health figures, the other alerts), so one device has one id in all a
#: call sends; and reads a rebuilt pack's health figures for the devices within two hops in
#: the model as it is now, said so. A pack of 4 stays readable: it holds no `concurrent`, and
#: Explain names its devices by the model's ids as it sends it (`explain.one_id`), never
#: rewriting the pack. 6 (C1896, 2026-10-27) adds `observer`, the monitoring side over the
#: window (the scrape jobs polling the devices across all their targets, the SNMP exporter, the
#: host Prometheus runs on; `evidence_observer`); a pack of 5 stays readable and holds none, and
#: its card offers Build again. 7 (the operator's order of 2026-10-29, "WHO, guaranteed in
#: code") adds to the Intent check's piece the intent difference's lines, masked (``lines``),
#: and its intent file's last commit (``intent_commit``: when, by whom, how established), and to
#: each History piece how its actor was established (``verified``, where History knows it); a
#: pack of 6 stays readable, holds none of them, and Explain's fact sheet says so.
SCHEMA = 7
#: The records store (`records_db.STORES`) and its file.
STORE = "evidence_packs"
FILE_NAME = "evidence_packs.jsonl"
#: The sections, in the order a person reads them.
SECTIONS = ("alert", "concurrent", "device", "history", "intent", "neighbours", "observed",
            "endpoints", "health", "observer", "logs")
SECTION_WORDS = {"alert": "The alert",
                 "concurrent": "Other alerts in the network around the onset",
                 "device": "The device", "history": "Recent History",
                 "intent": "Intent check", "neighbours": "Neighbours",
                 "observed": "The network around it, as observed",
                 "endpoints": "What is attached around it, as observed",
                 "health": "Health of the devices around it",
                 "observer": "The monitoring side over the window",
                 "logs": "Log lines around the onset",
                 "sdn": "The SDN flows and port rates the detection rests on"}
#: The section only an SDN detection's pack holds (`build_detection`, PHASE8_PLAN 17.1 S6), kept
#: out of `SECTIONS` so a Grafana alert's pack, and Explain's pack format (the cached prefix,
#: `explain.vocabulary`), are unchanged: the section rides as pack data, naming itself in its
#: own words.
SDN_SECTION = "sdn"
#: What an SDN detection's alert section was read from (C1867): Mercury's own detection, never a
#: Grafana reader. A pack built before C1867 says "Grafana's alert state, as the sdn reader
#: stored it"; the card draws these words for every SDN pack's alert section (`sdn_view`).
SDN_ALERT_SOURCE = "SDN detection: the alert as Mercury recorded it"
#: A build more than this before the clock is a replay of a past alert (`build`'s *now*): the
#: sections that read a store as it is now (History, the Intent check) say what they read.
REPLAY_SLACK_SECONDS = 300
#: A section's states. `empty` is a source read that held nothing; `absent`, nothing to read.
STATES = ("ok", "empty", "absent", "not_configured", "unreadable")
#: Where a section's evidence came from (schema 4), on every section as `provenance`, with its
#: words as `provenance_words`: read when the alert was found firing; rebuilt afterwards from
#: what keeps its past (a store filtered to the alert's time, a time series asked as of it, the
#: repository at the commit current then); or missing, because what it reads keeps only its
#: latest value, which is never put in its place. The pack carries its own (`captured` when
#: every section was, else `rebuilt`).
PROVENANCE = ("captured", "rebuilt", "missing")
PROVENANCE_WORDS = {"captured": "captured at the time", "rebuilt": "rebuilt afterwards",
                    "missing": "cannot be rebuilt"}
#: A pack built from the alert history (Monitoring › Alerts › History, Build evidence): the
#: sections that read a store keeping only its latest value, each with why it cannot be rebuilt.
NOT_REBUILT = {
    "neighbours": "the Neighbours view compares committed intent with the routing tables and "
                  "the RIP reader as they are now; the adjacencies as they were then were not "
                  "captured when the alert fired",
    "observed": "the Topology reader keeps only its latest read; the network as observed then "
                "was not captured when the alert fired. The health figures' devices and the "
                "topology Explain sends are the network model as it is now, said so, which "
                "may differ from then",
    "endpoints": "the endpoint store keeps only its latest read (no endpoint history is kept "
                 "yet, C1793); who was attached then was not captured when the alert fired",
}
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
#: times for the health figures and six for the observer (each aggregated, 0.06 s at most on
#: the lab's Prometheus, 2026-10-27) and git a few times; ten keep a storm's delay to the reader's announcement bounded.
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


def rebuilt_id(key: str, schema: int = None) -> str:
    """A pack BUILT AGAIN for an alert whose kept pack is of an older schema (C1862): the
    alert's id with the schema it is built in, so the pack kept before keeps its own id and
    both stay findable (`find`), each by its id."""
    return f"{pack_id(key)}-s{SCHEMA if schema is None else int(schema)}"


#: A pack id as a route takes it: the alert's, or the alert's built again in a later schema.
PACK_ID = r"^ep-[0-9a-f]{20}(-s[0-9]{1,3})?$"


def schema_of(pack: dict) -> int:
    """The schema a kept pack was built in (1 for a pack that predates the field)."""
    try:
        return int((pack or {}).get("schema") or 1)
    except (TypeError, ValueError):
        return 1


def built_when(pack: dict) -> str:
    """When *pack* was built: a pack built after its alert (replayed or rebuilt) carries the
    alert's time as ``built_at`` (what it is as of) and when it was built as ``replayed_at``;
    one built as its alert fired, ``built_at`` alone."""
    return (pack or {}).get("replayed_at") or (pack or {}).get("built_at") or ""


def older_schema(pack: dict) -> bool:
    """Whether *pack* was built in a schema older than this release's (`SCHEMA`): what it holds
    is less than a pack built now would (no other alerts before 5, one device's health)."""
    return schema_of(pack) < SCHEMA


def superseded(rows) -> dict:
    """``{pack id: the newest pack built again from it}`` over the kept *rows* (oldest first):
    a pack built again names the one it was built from (``rebuilt_from``), and a chain is
    followed to its newest, so the newest wins wherever one pack per alert is drawn."""
    after = {}
    for r in rows or []:
        old = (r.get("rebuilt_from") or {}).get("id")
        if old and old != r.get("id"):
            after[old] = r
    out = {}
    for old in after:
        seen, cur = {old}, after[old]
        while cur.get("id") in after and cur.get("id") not in seen:
            seen.add(cur["id"])
            cur = after[cur["id"]]
        out[old] = cur
    return out


def firing(value: dict) -> list:
    """The instances a reader value holds as firing: the condition holds. No-data and error
    are the reader's other two kinds, never "firing" (grafana_alerts' first rule); a rule whose
    no data is its fault fires on it, as the condition (C2174, the reader's second rule)."""
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
#: figure, or an observer piece (C1896), is measured or says why not. Every other piece's
#: ``state`` is what it describes (an alert's, an adjacency's, an intent check's), never whether
#: it was read (C1761).
PIECES_READ_ON_THEIR_OWN = ("health", "observer")


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


def _alert_section(inst: dict, store: str, value_at: str, onset, basis: str,
                   source: str = "") -> dict:
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
    if inst.get("absence"):
        # Firing on its data's absence (C2174): the fault is what did not arrive. Carried only
        # on such an alert, so every other pack's alert piece is as it was.
        piece["absence"] = inst["absence"]
    return _section("alert", source or f"Grafana's alert state, as the {store} reader stored "
                    "it", value_at, "ok", pieces=[piece])


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
    # How each actor was established (schema 7), where History knows it (a commit's
    # Actor-Verified, a store's record): the key only then, so "not said" is never "".
    pieces = [{"at": e.get("at") or "", "kind": e.get("kind") or "", "what": e.get("what") or "",
               "who": e.get("who_short") or "", "outcome": e.get("outcome") or "",
               "sha": (e.get("sha") or "")[:12], "detail": e.get("detail") or "",
               **({"verified": e.get("verified") or ""} if "verified" in e else {})}
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


#: The most of the intent difference's lines a pack keeps (`intent_match.LINE_CAP`'s, the
#: comparison's own cap); its counts are always whole.
INTENT_LINES = 20


def intent_lines(result: dict) -> list:
    """The intent difference's lines as the pack keeps them (the operator's order of 2026-10-29
    (c)): only when the check differs, at most `INTENT_LINES`, each ``+ <line>`` (in intent and
    not on the device) or ``- <line>`` (on the device and not in intent), masked as what leaves
    the host is masked (`redact.redact_egress`: by position and by known value, then every
    secret, password, key and hash shape): a secret's line is kept as its shape, its value
    masked, never the value. `intent_match` masks its lines already (C1688); this mask is the
    pack's own, so a comparison that ever returned a value in clear still keeps it out."""
    from modules import redact

    if result.get("state") != "differs":
        return []
    return [redact.redact_egress(str(line)) for line in (result.get("lines") or [])
            [:INTENT_LINES]]


def intent_commit(repo_dir: str, host: str) -> dict:
    """The last commit of *host*'s intent file in the repository *repo_dir* as checked out
    (`hostvars.committed_rel`): ``{"state": "ok", "sha", "at", "actor", "verified", "how"}``
    (its ``Actor:`` and ``Actor-Verified:``, how that was established in words, when it was
    committed); ``{"state": "absent", "why"}`` when no commit holds the file;
    ``{"state": "unreadable", "why"}`` when git could not say. Who changed the profile or a
    template the intent inherits is not this commit's."""
    from modules.nsot import hostvars
    from modules.nsot import repo as R

    rel = hostvars.committed_rel(host)
    sep = "\x1f"
    fmt = sep.join(["%H", "%cI", "%(trailers:key=Actor,valueonly)",
                    "%(trailers:key=Actor-Verified,valueonly)"])
    rc, out, err = R.git(repo_dir, "log", "-1", f"--format={fmt}", "HEAD", "--", rel)
    if rc != 0:
        return {"state": "unreadable",
                "why": ((err or out or "git log failed").strip().splitlines() or ["?"])[0]}
    if not (out or "").strip():
        return {"state": "absent", "why": f"no commit holds {rel}"}
    from modules.ai import who

    parts = [p.strip() for p in (out.split(sep) + ["", "", "", ""])[:4]]
    first = lambda v: (v.splitlines() or [""])[0].strip()      # noqa: E731
    commit = {"state": "ok", "sha": parts[0][:12], "at": parts[1], "actor": first(parts[2]),
              "verified": first(parts[3])}
    commit["how"] = who.how(commit)
    return commit


def intent_section(ref, dev: dict) -> dict:
    """The device's Intent check (15.11: the pack is in the allowed class, its "intent
    diffs"): the deploy plan's own comparison (`intent_match`) of the committed golden against
    effective intent, as match, differs (with its counts) or unknown (with why); when it
    differs, its lines, masked (`intent_lines`), so Explain can judge whether the difference
    could explain the alert; and who last committed the device's intent (`intent_commit`)."""
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
             "why": r.get("why") or "", "golden_commit": (golden.get("commit") or "")[:7],
             "lines": intent_lines(r)}
    try:
        piece["intent_commit"] = intent_commit(ref.repo_dir, host)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        piece["intent_commit"] = {"state": "unreadable", "why": _failed(exc)}
    return _section("intent", source, at, "ok", pieces=[piece])


def intent_section_at(ref, dev: dict, at: float) -> dict:
    """The Intent check as it stood at *at* (a pack rebuilt for a past alert): the same check
    (`intent_section`) run over the network's repository at the commit current then (the
    newest commit no later than *at*), checked out in a throwaway clone, so the golden, the
    intent, the templates and the profile are all of that commit. The repository itself is
    only read."""
    import shutil
    import tempfile
    import types

    from modules.nsot import repo as R

    host = dev.get("hostname") or ""
    source = f"the Intent check (intent_match) of {host}'s committed golden"
    rc, sha, err = R.git(ref.repo_dir, "rev-list", "-1", f"--before=@{int(at)}", "HEAD")
    if rc != 0:
        return _section("intent", source, _now(), "unreadable",
                        f"the commit current at {_iso(at)} could not be found "
                        f"({(err or sha or 'git rev-list failed').splitlines()[0]})")
    if not sha:
        return _section("intent", source, _now(), "absent",
                        f"{ref.name}'s repository holds no commit as of {_iso(at)}")
    folder = tempfile.mkdtemp(prefix="nmas-intent-at-")
    try:
        clone = os.path.join(folder, "repo")
        rc, out, err = R.git(ref.repo_dir, "clone", "--quiet", "--shared", "--no-checkout",
                             ref.repo_dir, clone)
        if rc == 0:
            # --force: the repository helper writes its hygiene files into the empty clone
            # first (ensure_repo_hygiene); the commit's own copies replace them.
            rc, out, err = R.git(clone, "checkout", "--quiet", "--force", "--detach", sha)
        if rc != 0:
            return _section("intent", source, _now(), "unreadable",
                            f"the repository at {sha[:12]} could not be read "
                            f"({(err or out or 'git failed').splitlines()[0]})")
        sec = intent_section(types.SimpleNamespace(repo_dir=clone, name=ref.name), dev)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    sec["source"] = (f"the Intent check (intent_match) of {host}'s golden and intent as "
                     f"committed at {sha[:12]}, the commit current at the alert's time "
                     f"{_iso(at)}")
    sec["as_of_commit"] = sha[:12]
    return sec


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


#: How far the endpoint store's read may lie from the alert's time and still be the alert's:
#: one read interval before (the reader's 15 minutes, `readers/endpoints`) and a little
#: after (a read in flight as the alert was found). Outside it, the read is not the alert's.
ENDPOINTS_BEFORE_S, ENDPOINTS_AFTER_S = 1200, 300


def endpoints_section(network: str, devices, now: float, built: float,
                      stored: dict = None) -> dict:
    """Who was attached to the alert's device and those beside it, CAPTURED with the pack
    (C1778, as `observed_section` captures the Topology read, C1712): the endpoint store's
    read when it was made as of the alert's time (`ENDPOINTS_BEFORE_S`, `ENDPOINTS_AFTER_S`),
    each endpoint located on one of *devices* with its last-seen in words. The store keeps
    only its latest read (the endpoint history is C1793), so a replay of an older alert says
    the read is not the alert's, never a later read in its place. *stored* stands in for
    `endpoints.stored(network)` (tests)."""
    from modules import endpoints as E
    source = ("the endpoint reader's stored read (each device's MAC table, ARP and IPv6 "
              "neighbours, and the DHCP leases), captured with the pack")
    as_of = _iso(now)
    got = stored if stored is not None else E.stored(network)
    if got.get("state") != "read":
        state = "unreadable" if got.get("state") == "unreadable" else "absent"
        return _section("endpoints", source, built, state,
                        got.get("why") or "no endpoint read", as_of=as_of)
    read_at = got.get("read_at") or ""
    at = E._epoch(read_at)
    if not at or not now - ENDPOINTS_BEFORE_S <= at <= now + ENDPOINTS_AFTER_S:
        return _section("endpoints", source, built, "absent",
                        f"the endpoint store keeps only its latest read ({read_at or 'none'}), "
                        f"which is not as of this alert's time {as_of} (no endpoint history "
                        "is kept yet, C1793)", as_of=as_of, endpoints_read_at=read_at)
    hours = E.stale_after_hours(network)
    keep = set(devices)
    pieces = [{"mac": e.get("mac") or "", "addresses": list(e.get("addresses") or []),
               "hostname": e.get("hostname") or "", "device": e.get("device") or "",
               "interface": e.get("interface") or "", "vlan": e.get("vlan") or "",
               "last_seen": e.get("last_seen") or "",
               "seen": E.seen(e, now=now, stale_hours=hours)["said"]}
              for e in got.get("endpoints") or [] if e.get("device") in keep]
    if not pieces:
        return _section("endpoints", source, built, "empty",
                        f"the read of {read_at} locates no endpoint on "
                        f"{', '.join(sorted(keep)) or 'these devices'}", as_of=as_of,
                        endpoints_read_at=read_at)
    return _section("endpoints", source, built, "ok", pieces=pieces, as_of=as_of,
                    endpoints_read_at=read_at)


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
             "figures": {k: H.FIGURE_WORDS[k] for k in H.FIGURES},
             "devices_from": devices_from(capture)}
    if not capture.get("ok"):
        extra["errors"] = [capture.get("words") or
                           f"the network model could not be read ({capture.get('error')}), "
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


def observer_section(ref, host: str, capture: dict, onset, now: float, built: float,
                     prometheus=None) -> dict:
    """The monitoring side over the health section's window (C1896; `evidence_observer`): the
    scrape jobs polling the alert's device and the devices within two hops, each across all its
    targets; the SNMP exporter; the host Prometheus runs on. Each piece's reference is
    ``observer:<what>``."""
    from modules import evidence_health as H
    from modules import evidence_observer as O

    source = ("Prometheus: the scrape jobs polling the alert's device and the devices within two "
              "hops, each across all its targets; the SNMP exporter as Prometheus holds it; the "
              "host Prometheus runs on, from its node exporter; each summarised over the window")
    devices, _total = H.devices_of(capture, host)
    got = O.read(ref.name, [n for _d, n, _h in devices], onset, now, prom=prometheus)
    extra = {"window": got["window"], "as_of": _iso(now), "asked_at": _iso(built),
             "questions": got["asked"], "errors": got["errors"],
             "jobs_total": got["jobs_total"], "jobs_most": O.MAX_JOBS,
             "timeouts_from": "Prometheus's configuration as it is now (status/config), which "
                              "may differ from the alert's time"}
    pieces = [{k: v for k, v in p.items() if k != "ref"} for p in got["pieces"]]
    states = {p["state"] for p in pieces}
    if states <= {"not_configured"}:
        sec = _section("observer", source, built, "not_configured",
                       f"no Prometheus is configured for {ref.name}", pieces=pieces, **extra)
    elif states <= {"unreadable", "not_configured"}:
        sec = _section("observer", source, built, "unreadable", "; ".join(got["errors"]),
                       pieces=pieces, **extra)
    else:
        sec = _section("observer", source, built, "ok", pieces=pieces, **extra)
    # Each piece's reference is its stable name, the one an answer cites.
    for p, mine in zip(sec["pieces"], got["pieces"]):
        p["ref"] = mine["ref"]
    return sec


def devices_from(capture: dict) -> str:
    """Whose figures the health section holds, in words: the walk the capture made (C1851: a
    pack rebuilt from the alert history walks the model as it is now, and says so)."""
    if not capture.get("ok"):
        return "the alert's device alone: no walk of the network model was made"
    if capture.get("as_now"):
        return ("the devices within two hops in " + capture["as_now"] + "; the network as "
                "observed then was not captured")
    return ("the devices within two hops in the network model, walked with the observed "
            "overlay captured with the pack")


#: The most other alerts a pack keeps (`concurrent_section`): those whose start is nearest the
#: onset, the rest counted and said. Measured on the host's alert history (2026-10-27 01:35
#: UTC, read-only, 7,917 episodes): over the 1,982 alerts that fired in Default, each one's
#: window (15 minutes before its onset to when it fired) held a median of 4 other alerts, 23 at
#: the 95th percentile and 67 at most (2026-10-21 04:09 UTC, a storm of discards and
#: unreachable devices). Walk 2's first alert held 16 (about 1,400 tokens). 40 keeps 95% of windows
#: whole and the section near 3,500 tokens of Explain's 20,000-token prompt bound
#: (modules/ai/pins/explain.json), beside the health figures and the log lines; a storm past it
#: is counted, nearest the onset kept, never dropped silently.
MAX_CONCURRENT = 40
CONCURRENT_MEASURED = {"median": 4, "p95": 23, "max": 67, "walk_first": 16, "walk_second": 26}


def concurrent_section(network: str, store: str, own: str, onset, at: float, built: float,
                       ids: dict = None, rows=None) -> dict:
    """Every OTHER alert in the alert's network active from 15 minutes before its onset to its
    time (C1850; `evidence_health.window`, the health figures' own window), from the alert
    history (`alert_history.episodes`, Grafana's own times): each episode's rule, device (its
    model id where the model knows it, *ids* by name: C1849) or address, its state at the
    alert's time and its times, never what happened after the alert's time. A piece's
    reference is ``concurrent:<episode id>``, the history's own id for it. *own* is this
    alert's identity (`alert_history.identity`): its episode spanning *at* is the alert itself,
    left out; its earlier episodes in the window stay, marked ``same_alert``. An episode begun
    before the window whose resolve was never recorded is counted, not listed (its state in
    the window is not known). At most `MAX_CONCURRENT`, those nearest the onset. *rows* stand
    in for the store's (tests)."""
    from modules import alert_history as AH
    from modules import evidence_health as H
    from modules.nsot import listref

    # Named as a person sees it, whichever spelling asked (C1903; an unknown name raises).
    network = listref.display_name(network) if network else ""
    win = H.window(onset, at)
    start, end = win["start"], win["end"]
    window = {"from": _iso(start), "to": _iso(end), "words": f"the {win['seconds'] // 60} "
              f"minutes {win['basis']}" + (f"; {win['bounded']}" if win["bounded"] else "")}
    where = f"the network {network}" if network else f"the alerts read from {store}"
    source = (f"the alert history (Grafana's transitions as it timed them), every other alert "
              f"of {where} active in the window, each as it stood at the alert's time")
    if rows is None:
        got = AH.read()
        if got["state"] == "unreadable":
            return _section("concurrent", source, built, "unreadable",
                            f"the alert history cannot be read ({got['error']})", window=window)
        if got["state"] == "absent":
            return _section("concurrent", source, built, "absent",
                            "the alert history holds nothing yet: no transition was recorded",
                            window=window)
        rows = got["rows"]

    def mine(e):
        # The same network by its one id, whichever spelling the history recorded (C1903).
        nets = e.get("networks") or []
        return listref.in_networks(nets, network) if (network and nets) \
            else e.get("store") == store

    pieces, unknown, total = [], 0, 0
    for e in AH.episodes(rows):
        if not mine(e):
            continue
        began, ended = AH.epoch(e.get("started_at")), AH.epoch(e.get("resolved_at"))
        if began is None or began > end:
            continue
        if ended is not None and ended < start:
            continue
        if e.get("identity") == own and (ended is None or ended >= end):
            continue                                  # the alert itself
        if ended is None and began < start:
            unknown += 1
            continue
        total += 1
        states = [s for s in e.get("states") or [] if (AH.epoch(s.get("at")) or 0) <= end]
        over = ended is not None and ended <= end
        last = states[-1]["to"] if states else ""
        piece = {"rule": e.get("rule") or "", "device": e.get("device") or "",
                 "state": "resolved" if over else AH.KIND_WORDS.get(last, last or "unknown"),
                 "started_at": e.get("started_at") or "",
                 "fired_at": e["fired_at"] if (AH.epoch(e.get("fired_at")) or end + 1) <= end
                 else "",
                 "resolved_at": e["resolved_at"] if over else "",
                 "_episode": e.get("id") or "", "_began": began}
        if not piece["device"]:
            piece["address"] = e.get("address") or ""
        if piece["device"] and (ids or {}).get(piece["device"]):
            piece["dev"] = ids[piece["device"]]
        if e.get("identity") == own:
            piece["same_alert"] = True
        pieces.append(piece)
    centre = onset if onset is not None else end
    kept = sorted(pieces, key=lambda p: (abs(p["_began"] - centre), p["started_at"],
                                         p["rule"], p["device"]))[:MAX_CONCURRENT]
    kept.sort(key=lambda p: (p["started_at"], p["rule"], p["device"] or p.get("address", "")))
    for p in kept:
        p.pop("_began")
        p["ref"] = p.pop("_episode")
    # Those begun before the window with no resolve recorded are counted, never listed: their
    # state in the window is not known (the card and the pack format say so).
    extra = {"window": window, "total": total, "subset": total > len(kept),
             "unknown_state": unknown}
    if not kept:
        return _section("concurrent", source, built, "empty",
                        f"no other alert of {where} was active between {window['from']} and "
                        f"{window['to']}", **extra)
    episodes = [p.pop("ref") for p in kept]
    sec = _section("concurrent", source, built, "ok", pieces=kept, **extra)
    seen = set()
    for p, eid in zip(sec["pieces"], episodes):
        ref = f"concurrent:{eid}"
        while ref in seen:                            # one reference, one piece, always
            ref += "+"
        seen.add(ref)
        p["ref"] = ref
    return sec


# ----------------------------------------------------------------------------- the pack

#: Each section's provenance when a pack is NOT built as its alert was found firing: a replay
#: (`scripts/nmas-pack-replay`, its alert synthesized, its time series and topology read as of
#: then) and a pack built from the alert history (`mode="history"`, its alert recorded at the
#: time by Grafana or the reader). The endpoints are captured whenever the store's read was
#: made as of the alert's time (`endpoints_section`), else missing.
REBUILT_MARKS = {
    "replay": {"alert": "rebuilt", "concurrent": "rebuilt", "device": "rebuilt",
               "history": "rebuilt", "intent": "rebuilt", "neighbours": "rebuilt",
               "observed": "rebuilt", "health": "rebuilt", "observer": "rebuilt",
               "logs": "rebuilt"},
    "history": {"alert": "captured", "concurrent": "rebuilt", "device": "rebuilt",
                "history": "rebuilt", "intent": "rebuilt", "neighbours": "missing",
                "observed": "missing", "endpoints": "missing", "health": "rebuilt",
                "observer": "rebuilt", "logs": "rebuilt"},
}
#: Each mark's words for a section, beyond `PROVENANCE_WORDS`: what it was rebuilt from.
REBUILT_FROM = {
    "alert": "the alert's transitions, as Grafana timed them, from the alert history",
    "concurrent": ("the alert history (Grafana's own times), each other alert as it stood at "
                   "the alert's time"),
    "device": "every network's inventory as it is now",
    "history": "History as it is now, less what it recorded after the alert's time",
    "intent": "the repository at the commit current at the alert's time",
    "neighbours": "Prometheus's routing tables asked as of the alert's time",
    "observed": "the Topology reader's own read over Prometheus as of the alert's time",
    "health": "Prometheus and Loki asked over the alert's window",
    "observer": ("Prometheus asked over the alert's window: the scrape jobs, the SNMP exporter "
                 "and the collector's host as Prometheus kept them then; each job's timeout from "
                 "its configuration as it is now"),
    "logs": "Loki asked over the window around the onset",
}
#: A pack rebuilt from the alert history reads its health figures for the devices within two
#: hops in the network model AS IT IS NOW (C1851): its mark says so, never a capture.
REBUILT_FROM_HISTORY = {
    "health": ("Prometheus and Loki asked over the alert's window, for the devices within two "
               "hops in the network model as it is now, which may differ from then"),
}


def mark(section: dict, provenance: str, words: str = "") -> dict:
    """Set *section*'s `provenance` (one of PROVENANCE) and `provenance_words`."""
    assert provenance in PROVENANCE, provenance
    section["provenance"] = provenance
    section["provenance_words"] = PROVENANCE_WORDS[provenance] + (f": {words}" if words else "")
    return section


def provenance_of(section: dict) -> str:
    """A section's mark, or "" for a pack built before schema 4 (not marked)."""
    return section.get("provenance") or ""


def _marks(sections: list, mode: str, clock: float) -> None:
    """Mark every section by *mode* (`live`, `replay`, `history`)."""
    for s in sections:
        name = s.get("name")
        if mode == "live":
            mark(s, "captured", "read when the alert was found firing")
            continue
        got = REBUILT_MARKS[mode].get(name)
        if name == "endpoints" and got is None:
            got = "captured" if s.get("state") in ("ok", "empty") else "missing"
        if got == "missing":
            mark(s, "missing", NOT_REBUILT.get(name) or s.get("why") or "")
        elif got == "captured":
            mark(s, "captured", REBUILT_FROM["alert"] if name == "alert" else
                 "the store's read was made as of the alert's time")
        elif name == "alert" and mode == "replay":
            mark(s, "rebuilt", "synthesized by the replay, no Grafana rule alerting on it")
        else:
            words = ((REBUILT_FROM_HISTORY if mode == "history" else {}).get(name)
                     or REBUILT_FROM.get(name, "its source"))
            mark(s, "rebuilt", f"at {_iso(clock)}, from {words}")


def build(inst: dict, *, store: str, value_at: str, now: float = None, loki=None,
          prometheus=None, observed_read: dict = None, trigger: str = "",
          endpoints_read: dict = None, mode: str = "") -> dict:
    """One alert instance's pack, masked and hashed. Never raises: a source that fails is
    its section saying so. *now* is the alert's time, when it was found firing: every read of
    a time series (the neighbours, the observed topology, the health figures, the log lines)
    is as of it. *loki* and *prometheus* stand in for the network's clients (tests);
    *observed_read* for the Topology reader's stored read, in its store's shape (a replay of
    a past alert, `scripts/nmas-pack-replay`, gives the read made as of that time), and
    *trigger* for what made the pack (the replay's own words). *mode* ``"history"`` builds a
    past alert's pack from the alert history (`build_for_episode`): History cut at the alert's
    time, the Intent check at the commit current then, the sections that read a store keeping
    only its latest value said to be missing, never read now, and the health figures read for
    the devices within two hops in the network model as it is now, said so (C1851). Every pack
    holds the other alerts of its network around the onset (`concurrent_section`, C1850), and
    names each device by the network model's id wherever the model knows it (C1849). Every
    section is marked (`provenance`)."""
    from modules import alert_history as AH
    from modules import attention as A
    from modules import network_model as NM
    from modules import redact

    clock = _now()
    now = clock if now is None else now
    replay = clock - now > REPLAY_SLACK_SECONDS
    mode = "history" if mode == "history" else "replay" if replay else "live"
    past = mode != "live"
    onset, basis = A._onset(inst)
    sections = [_alert_section(inst, store, value_at, onset, basis)]
    try:
        dev_section, ref, dev = _device_section(inst, onset, basis)
    except Exception as exc:                          # noqa: BLE001
        dev_section, ref, dev = (_section("device", "every network's inventory", now,
                                          "unreadable", _failed(exc)), None, None)
    host = (dev or {}).get("hostname") or ""
    cap = {"ok": False, "error": "no device"}
    if ref is not None:
        # One walk of the network model per pack (C1849): its ids name every device the pack
        # names. A pack rebuilt from the alert history walks the model as it is now, reading
        # no observed state (C1851); one built as its alert fires, or replayed, walks it with
        # the observed overlay as of the alert's time (C1712).
        try:
            cap = NM.capture(ref.name, host, hops=NM.CAPTURE_HOPS, now=now,
                             stored=observed_read, observe=mode != "history")
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            cap = {"ok": False, "error": _failed(exc)}
        if not cap.get("ok") and mode == "history":
            cap["words"] = (f"the network model could not be read ({cap.get('error')}), so "
                            "only the alert's device is read")
    ids = cap.get("names") or {}
    try:
        sections.append(concurrent_section(
            ref.name if ref is not None else "", store,
            AH.identity(store, inst.get("rule") or "", inst.get("labels")), onset, now, clock,
            ids=ids))
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        sections.append(_section("concurrent", "the alert history", clock, "unreadable",
                                 _failed(exc)))
    sections.append(dev_section)
    if ref is None:
        why = f"no device to read for: {dev_section['why']}"
        for name in ("history", "intent", "neighbours", "observed", "endpoints", "health",
                     "observer", "logs"):
            sections.append(_absent(name, "", why))
    elif mode == "history":
        sections.append(history_section(ref, host, until=now))
        try:
            sections.append(intent_section_at(ref, dev, now))
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            sections.append(_section("intent", "the Intent check at the commit then", clock,
                                     "unreadable", _failed(exc)))
        # Said missing (`_marks` gives each its reason, NOT_REBUILT): never an as-of time, so
        # nothing draws it as a capture.
        for name in ("neighbours", "observed", "endpoints"):
            sections.append(_section(name, "nothing read: not captured when the alert fired",
                                     clock, "absent", "cannot be rebuilt; a later read is never "
                                     "put in its place"))
        try:
            sections.append(health_section(ref, host, cap, onset, now, clock,
                                           prometheus=prometheus, loki=loki))
        except Exception as exc:                      # noqa: BLE001
            sections.append(_section("health", "Prometheus and Loki", clock, "unreadable",
                                     _failed(exc)))
        try:
            sections.append(observer_section(ref, host, cap, onset, now, clock,
                                             prometheus=prometheus))
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            sections.append(_section("observer", "Prometheus", clock, "unreadable",
                                     _failed(exc)))
        sections.append(logs_section(ref, host, onset, now, client=loki))
    else:
        sections.append(history_section(ref, host, until=now if replay else None))
        intent = intent_section(ref, dev)
        if replay:
            intent["source"] += (f"; the committed golden and intent as they are at "
                                 f"{_iso(clock)}, not as of the alert's time {_iso(now)}")
        sections.append(intent)
        sections.append(neighbours_section(ref, dev, as_of=now))
        sections.append(observed_section(cap, now, clock))
        # The alert's device and those one hop from it, by name (the endpoint store's key);
        # the capture keys its walk by node id, named in its `nodes`.
        names = (cap.get("nodes") or {}) if cap.get("ok") else {}
        near = [host] + [names[n]["name"] for n, r in (cap.get("reached") or {}).items()
                         if (r or {}).get("hop", 9) <= 1 and names.get(n, {}).get("name")]
        try:
            sections.append(endpoints_section(ref.name, near, now, clock,
                                              stored=endpoints_read))
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            sections.append(_section("endpoints", "the endpoint reader's stored read", clock,
                                     "unreadable", _failed(exc)))
        try:
            sections.append(health_section(ref, host, cap, onset, now, clock,
                                           prometheus=prometheus, loki=loki))
        except Exception as exc:                      # noqa: BLE001
            sections.append(_section("health", "Prometheus and Loki", clock, "unreadable",
                                     _failed(exc)))
        try:
            sections.append(observer_section(ref, host, cap, onset, now, clock,
                                             prometheus=prometheus))
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            sections.append(_section("observer", "Prometheus", clock, "unreadable",
                                     _failed(exc)))
        sections.append(logs_section(ref, host, onset, now, client=loki))
    _marks(sections, mode, clock)
    key = alert_key(inst)
    pack = {"schema": SCHEMA, "id": pack_id(key), "alert_key": key, "built_at": _iso(now),
            "store": store, "rule": inst.get("rule") or "", "device": host,
            "network": ref.name if ref is not None else "", "onset": _iso(onset),
            "trigger": trigger or (f"the {store} reader stored this alert as firing (its "
                                   f"value of {value_at or 'an unrecorded time'})"),
            "provenance": "rebuilt" if past else "captured",
            "sections": sections}
    if past:
        pack["replayed_at"] = _iso(clock)
    # Masked BEFORE it is hashed or kept: what is hashed is what is stored and shown.
    pack = redact.redact_payload(pack)
    pack["hash"] = digest(pack)
    return pack


def build_detection(inst: dict, *, network: str, sdn: dict, now: float, trigger: str,
                    switch_words: str) -> dict:
    """An SDN detection's pack (PHASE8_PLAN 17.1 S6; `modules/sdn/detect.py` calls it when the
    detection first fires), masked and hashed: the alert (*inst*, in the reader's shape, its
    store ``sdn``); the device, absent (a controller's switch is in no network's inventory:
    *switch_words* says which switch); and the ``sdn`` section, *sdn* ``{"source", "read_at",
    "pieces", ...}``: the collected flows and port rates the detection rests on, as of the
    collection (*now*, the detection's time), each piece carrying its evidence id. Every section
    is marked captured. Explain reads it unchanged: the section is pack data, gated as the
    topology class (`explain.sent_sections`)."""
    from modules import redact
    from modules.sdn import detect

    onset, basis = _detection_onset(inst)
    sections = [_alert_section(inst, detect.STORE, _iso(now), onset, basis,
                               source=SDN_ALERT_SOURCE),
                _section("device", "every network's inventory", now, "absent",
                         f"{switch_words} is an SDN controller's switch, not a device in any "
                         "network's inventory (adopting switches as devices comes after "
                         "PHASE8_PLAN 17.1's slice)")]
    extra = {k: v for k, v in sdn.items() if k not in ("source", "read_at", "pieces")}
    sections.append(_section(SDN_SECTION, sdn["source"], sdn["read_at"], "ok",
                             pieces=sdn["pieces"], **extra))
    for s in sections:
        mark(s, "captured", "read when the detection was found firing"
             if s["name"] != SDN_SECTION else
             "the collection the detection rests on, read at the detection's time")
    key = alert_key(inst)
    pack = {"schema": SCHEMA, "id": pack_id(key), "alert_key": key, "built_at": _iso(now),
            "store": detect.STORE, "rule": inst.get("rule") or "", "device": "",
            "network": network, "onset": _iso(onset), "trigger": trigger,
            "provenance": "captured", "sections": sections}
    pack = redact.redact_payload(pack)
    pack["hash"] = digest(pack)
    return pack


def _detection_onset(inst: dict):
    """An SDN detection's onset: when its condition first held (``active_at``), the
    collection that first showed it (Mercury's clock)."""
    from modules import alert_history as H

    at = H.epoch(inst.get("active_at"))
    return at, ("the collection that first showed it, by Mercury's clock" if at is not None
                else "not recorded")


def sdn_firing() -> dict:
    """The SDN detections firing now (`modules/sdn/detect.firing`): ``{"state", "error",
    "updated_at", "instances": [(store, instance)]}``. Never raises: a state that cannot be
    read is said, and lists none."""
    try:
        from modules.sdn import detect
        got = detect.firing()
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.error("evidence_pack: the SDN detections could not be read (%s)", exc)
        return {"state": "unreadable", "error": _failed(exc), "updated_at": "", "instances": []}
    return {"state": got["state"], "error": got["error"], "updated_at": got["updated_at"],
            "instances": [(detect.STORE, i) for i in got["instances"]]}


def _piece_words(p: dict) -> str:
    """An ``sdn`` piece in a few words, beside its reference where a detection cites it."""
    kind = p.get("kind")
    if kind == "port":
        return f"port {p.get('port_no')}"
    if kind == "flow":
        return f"a flow, priority {p.get('priority')}"
    if kind == "displaced_flow":
        return "Mercury's flow, displaced"
    if kind == "sighting":
        return f"an earlier sighting, {p.get('port')}"
    return str(kind or "a piece")


def _meter_ids(actions) -> list:
    """The meters *actions* name (``METER`` among them, inside ``WRITE_ACTIONS`` too)."""
    out = []
    for a in actions or []:
        if a.get("type") == "METER" and a.get("meter_id") is not None:
            out.append(a["meter_id"])
        out += _meter_ids(a.get("actions"))
    return out


def sdn_view(pack: dict) -> dict:
    """What an SDN detection's pack card draws beside its stored sections (C1867), or {} for
    any other pack. From the pack: the switch its ``sdn`` section is of (the detection's DPID
    and connection), each piece's reference by its evidence id (``refs``: a detection cites ids,
    the card links them), the ids the detection cites, and each meter the section's flows name
    (``METER`` among their actions). From the SDN reader's stored value, read once, NOT part of
    the pack: the name the switch reports, and each named meter's rate, bands and counters as
    that read holds them, with its time. The collection a detection rests on reads flows and
    port counters, never meters, so a meter is drawn as a later read, saying so, and is never
    cited. Every state the reader can be in is said: never read, not configured, unreadable,
    the switch or the meter not in its read, meters not read on the switch."""
    if (pack or {}).get("store") != "sdn":
        return {}
    from modules import sdn_page

    section = next((s for s in pack.get("sections") or [] if s.get("name") == SDN_SECTION), {})
    pieces = section.get("pieces") or []
    det = next((p for p in pieces if p.get("kind") == "detection"), {})
    labels = next((p.get("labels") or {} for s in pack.get("sections") or []
                   if s.get("name") == "alert" for p in s.get("pieces") or []), {})
    dpid = det.get("dpid") or labels.get("dpid") or ""
    connection = det.get("connection") or labels.get("connection") or ""
    refs = {p["id"]: {"ref": p["ref"], "what": _piece_words(p)}
            for p in pieces if p.get("id") and p.get("ref")}
    named = {}
    for p in pieces:
        if p.get("kind") in ("flow", "displaced_flow"):
            for m in _meter_ids(p.get("actions")):
                named.setdefault(m, [])
                if p.get("ref") not in named[m]:
                    named[m].append(p.get("ref"))
    got = sdn_page.stored(pack.get("network") or "")
    reader = {"state": got["state"], "value_at": got.get("value_at") or "",
              "why": got.get("why") or got.get("failed") or ""}
    sw, sw_why = None, ""
    if got["state"] == "ok":
        ctl = next((c for c in (got.get("value") or {}).get("controllers") or []
                    if c.get("name") == connection), {})
        sw = next((s for s in ctl.get("switches") or [] if s.get("dpid_hex") == dpid), None)
        if sw is None:
            sw_why = f"the SDN reader's read holds no switch {dpid} on {connection}"
    else:
        sw_why = {"never": "the SDN reader has not read this network yet",
                  "not_configured": "this network has no SDN controller connection now",
                  "not_applicable": "the SDN reader does not read this network"}.get(
            got["state"], f"the SDN reader's store could not be read ({reader['why']})")
    name = (sw or {}).get("name") or ""
    if sw is not None and not name:
        sw_why = (f"the switch's description could not be read ({sw['desc_error']})"
                  if sw.get("desc_error") else "the switch reports no name")
    built = pack.get("built_at") or ""
    meters = []
    for mid, by in sorted(named.items(), key=lambda kv: str(kv[0])):
        m = {"meter_id": mid, "named_by": by, "state": "not_read", "why": sw_why,
             "rate": "", "bands": [], "packets_in": None, "bytes_in": None, "flows": None}
        if sw is not None and not sw.get("meters_read"):
            m["why"] = ("its meters were not read on this switch: "
                        + (sw.get("meters_error") or "the driver does not read meters"))
        elif sw is not None:
            held = next((x for x in sw.get("meters") or [] if x.get("meter_id") == mid), None)
            if held is None:
                m.update(state="absent", why=f"switch {name or dpid} held no meter {mid} when "
                                             "the SDN reader last read it")
            else:
                kbps = "KBPS" in (held.get("flags") or [])
                m.update(state="read", why="", rate=sdn_page._meter_words(held),
                         packets_in=held.get("packet_in_count"),
                         bytes_in=held.get("byte_in_count"), flows=held.get("flows"),
                         bands=[{"type": b.get("type") or "",
                                 "burst": b.get("burst_size"),
                                 "unit": "kbit" if kbps else "packets",
                                 "packets": b.get("packet_band_count"),
                                 "bytes": b.get("byte_band_count")}
                                for b in held.get("bands") or []])
        meters.append(m)
    return {"alert_source": SDN_ALERT_SOURCE,
            "switch": {"dpid": dpid, "connection": connection, "name": name, "why": sw_why},
            "reader": dict(reader, after=bool(reader["value_at"] and built
                                              and reader["value_at"] > built)),
            "refs": refs, "cited": list(det.get("evidence") or []), "meters": meters}


def episode_instance(e: dict) -> dict:
    """An alert history episode (`alert_history.episodes`) as a firing instance in the alerts
    reader's shape: its rule and labels, its condition first holding when the episode began,
    alerting from when it fired, both Grafana's times. An episode that fired on its data's
    absence (Grafana's "Alerting (NoData)", C2174) keeps those state words and says what was
    absent, over the rule's own window (its ``window_seconds`` label, else the query window
    the alerts reader holds for its rule now, `_rule_window`)."""
    from modules.readers import grafana_alerts as G

    labels = dict(e.get("labels") or {})
    window = labels.get("window_seconds")
    window = int(window) if str(window or "").isdigit() else 0
    fired = next((s.get("state") for s in e.get("states") or []
                  if s.get("to") == "condition"), "")
    inst = {"rule": e.get("rule") or "", "rule_uid": e.get("rule_uid") or "",
            "kind": "condition", "state": "Alerting", "value": "", "labels": labels,
            "device": e.get("device") or "", "address": e.get("address") or "",
            "device_from": e.get("device_from") or ("label" if e.get("device") else "address"),
            "active_at": e.get("started_at") or "", "starts_at": e.get("fired_at") or "",
            "fingerprint": "", "for_seconds": 0, "window_seconds": window,
            "silences": []}
    if G.alerting_on_no_data(fired):
        inst["state"] = fired
        inst["absence"] = G.absence_words(
            labels, inst["device"] or inst["address"],
            window or _rule_window(e.get("store") or "", inst["rule_uid"], inst["rule"]))
    return inst


def _rule_window(store: str, uid: str, title: str = "") -> int:
    """The query window the alerts reader holds now for the rule in *store* named by *uid*
    (else by its *title*: a backfilled row carries no uid, Grafana's annotations naming the
    rule by title) as its ``query_window_seconds``, or 0 when it holds none: a past alert's
    rule may have changed or gone since, and then its window is said not recorded."""
    from modules import reader_job

    if not store or not (uid or title):
        return 0
    got = reader_job.read_cached(store)
    value = (((got.get("doc") or {}).get("last_good") or {}).get("value") or {})
    return next((int(r.get("query_window_seconds") or 0) for r in value.get("rules") or []
                 if (r.get("uid") == uid if uid else r.get("title") == title)), 0)


def build_for_episode(e: dict, *, actor: str, loki=None, prometheus=None,
                      rebuild_of: dict = None) -> dict:
    """A past alert's pack, rebuilt from the alert history (Monitoring › Alerts › History,
    Build evidence): as of the alert's time (when it fired, else when it began), its window
    from 15 minutes before the onset to that time, each section marked. Frozen once kept:
    Explain reads it by id and checks its hash, never building it again.

    *rebuild_of* is a kept pack of an older schema this one is built AGAIN for (C1862, Build
    again): the new pack takes `rebuilt_id` (its own id, so the kept one keeps its), names the
    one it was built from (``rebuilt_from``: its id, schema, built time and hash) and says so
    in its trigger. The kept pack is never rewritten."""
    from modules import alert_history as H

    at = H.epoch(e.get("fired_at")) or H.epoch(e.get("started_at"))
    words = (f"built from the alert history by {actor} at {_iso(_now())}: "
             f"{e.get('rule') or 'an alert'} fired at {_iso(at)}, resolved at "
             f"{e.get('resolved_at') or 'a time Grafana did not record'}; "
             "nothing was captured when it fired")
    if rebuild_of:
        words = (f"built again from the alert history by {actor} at {_iso(_now())}, with this "
                 f"release's evidence (schema {SCHEMA}), in place of pack {rebuild_of.get('id')} "
                 f"(schema {schema_of(rebuild_of)}), which stays kept: "
                 f"{e.get('rule') or 'an alert'} fired at {_iso(at)}, resolved at "
                 f"{e.get('resolved_at') or 'a time Grafana did not record'}")
    pack = build(episode_instance(e), store=e.get("store") or "", value_at="", now=at,
                 loki=loki, prometheus=prometheus, mode="history", trigger=words)
    from modules import redact
    pack.pop("hash", None)
    pack["episode"] = e.get("id") or ""
    pack["resolved_at"] = e.get("resolved_at") or ""
    if rebuild_of:
        pack["id"] = rebuilt_id(pack["alert_key"])
        pack["rebuilt_from"] = {"id": rebuild_of.get("id") or "",
                                "schema": schema_of(rebuild_of),
                                "built_at": built_when(rebuild_of),
                                "hash": rebuild_of.get("hash") or ""}
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
            "pack": None, "switch": None}
    if store == "sdn":
        # An SDN detection is of a controller's switch, never a device (C1867): the card names
        # the switch by its labels, and its source as SDN detection.
        card["switch"] = {"dpid": labels.get("dpid") or "",
                          "connection": labels.get("connection") or ""}
    if pack:
        card["pack"] = pack_summary(pack)
    return card


def pack_summary(pack: dict) -> dict:
    """What a card's closed line says of its pack: its id, when it was built, its hash, how
    many pieces, and which sections could not be read or held nothing to read."""
    sections = pack.get("sections") or []
    out = {"id": pack.get("id"), "built_at": pack.get("built_at") or "",
           "hash": pack.get("hash") or "", "intact": intact(pack),
           "pieces": sum(len(s.get("pieces") or []) for s in sections),
           "not_read": [s.get("words") or s.get("name") for s in sections
                        if s.get("state") == "unreadable"],
           "device": pack.get("device") or "", "network": pack.get("network") or "",
           "onset": pack.get("onset") or "", "rule": pack.get("rule") or "",
           "schema": schema_of(pack), "built": built_when(pack)}
    if pack.get("store") == "sdn":
        # An SDN detection's pack is of a switch (C1867), named by its alert's labels.
        labels = next((p.get("labels") or {} for s in sections if s.get("name") == "alert"
                       for p in s.get("pieces") or []), {})
        out["switch"] = {"dpid": labels.get("dpid") or "",
                         "connection": labels.get("connection") or ""}
    return out


#: Each section's count, in a person's words, as its collapsed summary names it (board
#: AlertsExplain revised 2026-10-29, "the answer card first": "Log lines around the onset · 14
#: lines", "Neighbours · 1 down, 4 up"): the noun one piece of the section is.
COUNT_NOUNS = {"alert": "alert", "concurrent": "other alert", "device": "device",
               "history": "record", "intent": "check", "neighbours": "neighbour",
               "observed": "item", "endpoints": "endpoint", "health": "figure",
               "observer": "monitoring figure", "logs": "line", "sdn": "piece"}
#: A neighbour's, an observed item's and another alert's states, in the order a count names
#: them (what needs a look first) and in its words. Another alert's state is as it stood at the
#: alert's time, never now, and its end is "cleared" (C2173: nothing says it was fixed).
STATE_ORDER = ("down", "not_seen", "unexpected", "firing", "pending", "no data", "error",
               "resolved", "up", "unknown state")
COUNT_STATE_WORDS = {"not_seen": "not seen", "firing": "firing then", "pending": "pending then",
                     "no data": "no data then", "error": "in error then", "resolved": "cleared"}


def _plural(k: int, noun: str) -> str:
    return f"{k} {noun}{'' if k == 1 else 's'}"


def _by_state(pieces, key="state") -> str:
    counts = {}
    for p in pieces:
        counts[p.get(key) or "unknown state"] = counts.get(p.get(key) or "unknown state", 0) + 1
    order = sorted(counts, key=lambda s: (STATE_ORDER.index(s) if s in STATE_ORDER
                                          else len(STATE_ORDER), s))
    return ", ".join(f"{counts[s]} {COUNT_STATE_WORDS.get(s, s.replace('_', ' '))}"
                     for s in order)


def section_count(section: dict) -> str:
    """The count a pack section's collapsed summary names (board AlertsExplain revised
    2026-10-29): how many pieces it holds in its own noun ("14 lines", "14 of 40 lines" when the
    pack kept a subset), its neighbours and observed items by state ("1 down, 4 up"), the other
    alerts by their state at the alert's time, its health figures with their devices, and the
    intent check's verdict. "" for a section that holds nothing because it was not read, not
    configured or had nothing to read: its state chip says so. Pure: words over the stored
    section, never a read."""
    name = section.get("name") or ""
    pieces = section.get("pieces") or []
    n = len(pieces)
    noun = COUNT_NOUNS.get(name, "piece")
    if not pieces:
        return f"no {noun}s" if section.get("state") in ("ok", "empty") else ""
    total = section.get("total") if section.get("subset") else None
    counted = (f"{n} of {total} {noun}s" if isinstance(total, int) and total > n
               else _plural(n, noun))
    if name == "neighbours":
        peers = [p for p in pieces if p.get("kind") != "protocol"]
        protocols = n - len(peers)
        said = _by_state(peers) if peers else "no neighbour"
        return said + (f"; {_plural(protocols, 'protocol')} measured" if protocols else "")
    if name == "observed":
        return _by_state(pieces)
    if name == "concurrent":
        return f"{counted}: {_by_state(pieces)}"
    if name == "health":
        devices = len({p.get("device") or p.get("dev") for p in pieces})
        return f"{_plural(devices, 'device')}, {counted}"
    if name == "intent":
        words = {"match": "matches", "differs": "differs"}
        return ", ".join(words.get(p.get("state"), (p.get("state") or "not checked")
                                   .replace("_", " ")) for p in pieces)
    if name == "sdn":
        c = section.get("counts") or {}
        return ", ".join(_plural(c.get(k) or 0, w) for k, w in (("flows", "flow"),
                                                                 ("ports", "port"))) \
            if c else counted
    return counted


def tab(q: str = "", kind: str = "") -> dict:
    """Monitoring › Alerts: every firing alert, grouped by rule, each with its pack's summary
    (or that it is waiting for one), and the packs of alerts no longer firing, newest first.
    ``kinds`` counts every firing alert by its group (`family`), most first, each a filter
    (*kind*, its group's name exactly: board AlertsExplain revised 2026-10-29), over everything
    firing whatever the filter. Reads the alerts reader's stores and the pack store, once each:
    no source is asked."""
    from modules import reader_job

    q = (q or "").strip()[:80]
    kind = (kind or "").strip()[:200]
    sources, firing_now = [], []
    for name in _alert_stores():
        got = reader_job.read_cached(name)
        good = ((got.get("doc") or {}).get("last_good") or {})
        sources.append({"store": name, "value_at": good.get("value_at") or "",
                        "state": got["state"] if good else "not_read",
                        "why": got.get("why") or ((got.get("doc") or {}).get("last_attempt")
                                                  or {}).get("error") or ""})
        firing_now += [(name, i) for i in firing(good.get("value") or {})]
    # Mercury's own SDN detections (PHASE8_PLAN 17.1 S6), a source only once one has been
    # judged: a network with no SDN detection draws as before.
    sdn = sdn_firing()
    if sdn["state"] != "absent":
        sources.append({"store": "sdn", "value_at": sdn["updated_at"],
                        "state": "ok" if sdn["state"] == "ok" else "unreadable",
                        "why": sdn["error"]})
        firing_now += sdn["instances"]
    store = read()
    latest = {}
    for p in store["rows"]:
        latest[p.get("alert_key")] = p
    cards = [_card(i, name, latest.get(alert_key(i))) for name, i in firing_now]
    keys = {c["key"] for c in cards}
    want = q.lower()

    def matches(*texts):
        return not want or any(want in (t or "").lower() for t in texts)

    every = {}
    for c in cards:
        f = family(c["rule"], c["device"])
        every[f] = every.get(f, 0) + 1
    kinds = [{"family": f, "count": k}
             for f, k in sorted(every.items(), key=lambda kv: (-kv[1], kv[0]))]
    shown = [c for c in cards if matches(c["rule"], c["device"], c["summary_labels"])
             and (not kind or family(c["rule"], c["device"]) == kind)]
    groups = {}
    for c in shown:
        groups.setdefault(family(c["rule"], c["device"]), []).append(c)
    # A pack built again (C1862) is drawn in place of the one it was built from, which stays
    # kept and opens from it: one pack per alert here, the newest.
    gone = superseded(store["rows"])
    earlier_all = [pack_summary(p) for p in reversed(store["rows"])
                   if p.get("alert_key") not in keys and p.get("id") not in gone]
    earlier_all = [e for e in earlier_all if matches(e["rule"], e["device"])]
    return {"q": q, "kind": kind, "kinds": kinds,
            "sources": sources, "store": {"state": store["state"], "error": store["error"]},
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
