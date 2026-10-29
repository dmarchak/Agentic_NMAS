"""Alert history: every state transition of every Grafana alert, kept by Mercury (PHASE8_PLAN
15.9, the operator's order of 2026-10-26).

**What is kept.** One row per transition, appended and never rewritten: the rule, its labels,
the device they name (by label, else the polled address), the state Grafana moved to (pending,
firing, resolved, no data, error, in Grafana's own words) and WHEN, in Grafana's time: the
rules view's ``activeAt`` (when the instance's current state began; measured 2026-10-26: a
``Normal (NoData)`` instance's ``activeAt`` was its annotation's ``time`` to the second) or the
state history's ``time``. Never Mercury's clock and never a device's (vIOS clocks run slow:
CLAUDE.md, device clocks). Mercury's own clock is kept beside it as ``recorded_at``, named.

**Two writers, one key.** The `grafana-alerts` reader's after-store step (`after_alerts_read`)
records what each 60 s read shows: every alerting, pending, no-data or error instance, and a
resolve when a NORMAL instance's state began after the last recorded non-normal state of the
same instance (the reader keeps the normal instances whose state began within the last hour,
`grafana_alerts.RECENTLY_NORMAL_SECONDS`, so a reader that missed a read still sees a resolve).
A third writer, Mercury's own SDN detections (`modules/sdn/detect.py`, PHASE8_PLAN 17.1
S6, the store ``sdn``), records each detection's firing and its resolve through
`from_detections`, keyed the same way; its time is the collection's, by Mercury's clock,
because no Grafana holds the alert (``at_basis`` says so on each row).
`scripts/nmas-alert-backfill` records Grafana's own state history (its alert annotations),
as far back as Grafana holds it. A transition's key (`transition_key`) is computed the same
way from both: the reader's configuration store, the rule's title, its public labels, the state
Grafana named and the second it began. So a transition the reader recorded is never recorded
again by the backfill, nor by a second reader run, nor by a backfill rerun. Grafana's
annotation id is kept on a backfilled row (``grafana_id``); it cannot be the key, because the
reader never sees it.

**Where it is kept:** the records store `alert_history` (`records_db.STORES`, the setting
`records_store_alert_history`, `file` by default: ``alert_history.jsonl`` in the data folder),
written through `records_migrate.store_append` and read through `store_rows`, as the evidence
packs are, so it can move to the records database by its own row in Settings. Every row is
masked by `redact.redact_payload` before it is kept.

**Retention** is per network (`alert_history_retention_days`, 90 by default). A row older than
the longest retention of the networks sharing its Grafana is MOVED to the data lake (the
network's S3/MinIO archive, `integrations.s3_archive`), at
``alert-history/<network>/<first>_<last>_<count>.jsonl``, and a ``moved`` row naming each key
and the object is appended; readers leave moved rows out. The rows stay in the append-only
file: removing them is `compact`, a declared seam that refuses with its reason (the line stores
have no rewrite path). With no archive configured nothing moves, and `expire` says so.
"""

import calendar
import hashlib
import json
import logging
import os
import re
import threading
import time

log = logging.getLogger(__name__)

#: The row's own shape; a reader of a later shape says it cannot read this one.
SCHEMA = 1
#: The records store (`records_db.STORES`) and its file.
STORE = "alert_history"
FILE_NAME = "alert_history.jsonl"
#: The reader's kinds (grafana_alerts._kind) in a person's words. A normal state after a
#: non-normal one is a resolve.
KIND_WORDS = {"pending": "pending", "condition": "firing", "no_data": "no data",
              "error": "error", "normal": "resolved", "unknown_state": "unknown state"}
#: Where each source's time comes from, said on every row.
AT_BASIS = {"reader": "Grafana's rules view: when this state began (activeAt)",
            "reader_am": "Grafana's Alertmanager: when the alert began (startsAt)",
            "backfill": "Grafana's state history: the transition's time",
            "sdn": ("Mercury's SDN detection (modules/sdn/detect.py): the collection that showed "
                    "it, by Mercury's clock, the detection being Mercury's own")}
#: Days kept by default (`alert_history_retention_days`), as the log store's default.
RETENTION_DAYS = 90
#: The data lake's prefix for moved rows.
ARCHIVE_PREFIX = "alert-history"
#: How often the reader's after-store step asks whether rows are due to move: once a day per
#: process is enough for a retention counted in days.
EXPIRE_EVERY_SECONDS = 86400
#: History's summary draws at most this many episodes per rule group, newest first.
GROUP_SHOWN = 100
#: History's time ranges, in seconds ("all" is every row kept).
RANGES = {"24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400, "90d": 90 * 86400, "all": None}
RANGE_WORDS = {"24h": "the last 24 hours", "7d": "the last 7 days", "30d": "the last 30 days",
               "90d": "the last 90 days", "all": "all the history kept"}
#: An episode's outcomes, in the summary's order.
OUTCOMES = ("fired", "pending_only", "no_data", "error")
OUTCOME_WORDS = {"fired": "fired and resolved", "pending_only": "pending, never fired",
                 "no_data": "read no data", "error": "could not evaluate"}
#: A pack matches an episode when its alert began within this much of the episode's span.
PACK_SLACK_SECONDS = 60
#: Build evidence's steps (Monitoring › Alerts › History; routes/v2.
#: monitoring_alert_history_evidence), as the manual names them.
BUILD_STEPS = (
    ("find", "the past alert, from the alert history, and any pack already kept for it: one "
             "kept is drawn, never built again"),
    ("rebuild", "its pack as of the alert's time (when it fired), from 15 minutes before the "
                "onset: the other alerts of its network in the window as they stood then, "
                "History up to then, the Intent check at the commit current then, the health "
                "figures of the devices within two hops in the network model as it is now "
                "(said so) and the log lines over the window; the neighbours, the network as "
                "observed and the endpoints said to be missing, never read now"),
    ("mark", "every section marked captured at the time, rebuilt afterwards (from what), or "
             "cannot be rebuilt (why); the pack itself marked rebuilt"),
    ("keep", "masked, hashed and kept in the evidence pack record as the person who pressed "
             "it: frozen, so Explain reads this pack each time"),
    ("show", "the pack drawn in place of the button, with Explain"),
)
#: Build again's steps (C1862; an evidence pack's card, routes/v2.monitoring_alert_pack_rebuild),
#: as the manual names them (docs/manual/how-it-works/alert-evidence.md, #rebuild).
REBUILD_STEPS = (
    ("find", "the kept pack, and any pack already built again from it: one is drawn, never "
             "built twice"),
    ("check", "the kept pack's schema against this release's: one of this release's is never "
              "built again; and its past alert in the alert history: one the history does not "
              "hold, or still firing, is not built again, and says why"),
    ("rebuild", "a new pack as Build evidence builds one, as of the alert's time, with this "
                "release's evidence (the other alerts, the health of every device within two "
                "hops, one id per device), naming the kept pack it was built from"),
    ("keep", "kept beside the kept pack in the evidence pack record under its own id, as the "
             "person who pressed it; the kept pack is never rewritten or deleted"),
    ("show", "the new pack drawn in place, naming the kept one with Show it; History and "
             "Explain read the new one from now"),
)

_ISO = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.\d+)?(Z|[+-]\d\d:?\d\d)?$")


# ----------------------------------------------------------------------------- times

def epoch(text):
    """Grafana's RFC 3339 time (``2026-10-22T07:17:50Z``, nanoseconds and offsets allowed) as
    whole UTC seconds, or None: unset, unparsable, or Go's zero time (year 1)."""
    m = _ISO.match(str(text or "").strip())
    if not m:
        return None
    try:
        base = calendar.timegm(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None
    zone = m.group(2) or "Z"
    if zone != "Z":
        sign = -1 if zone[0] == "-" else 1
        digits = zone[1:].replace(":", "")
        base -= sign * (int(digits[:2]) * 3600 + int(digits[2:]) * 60)
    return base if base >= 946684800 else None


def iso(ts) -> str:
    """Whole UTC seconds as ``YYYY-MM-DDTHH:MM:SSZ``; "" for none."""
    if ts is None or ts == "":
        return ""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ts)))


def duration_words(seconds) -> str:
    """``"4 min"``, ``"2 h 5 min"``, ``"3 d 4 h"``; "" when not known."""
    if seconds is None:
        return ""
    s = int(seconds)
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min"
    if s < 86400:
        return f"{s // 3600} h {s % 3600 // 60} min"
    return f"{s // 86400} d {s % 86400 // 3600} h"


# ----------------------------------------------------------------------------- identity

def public(labels: dict) -> dict:
    """The labels that name an instance: Grafana's internal ones (``__name__``,
    ``__grafana_receiver__``) are routing, not identity (grafana_alerts._public)."""
    return {str(k): str(v) for k, v in (labels or {}).items() if not str(k).startswith("__")}


def _sha(obj, n: int) -> str:
    return hashlib.sha256(json.dumps(obj, separators=(",", ":"), sort_keys=True)
                          .encode()).hexdigest()[:n]


def identity(store: str, rule: str, labels: dict) -> str:
    """An alert instance across its life: the reader's configuration store, the rule's title
    and its public labels. Grafana's rule uid is not in its state history, so the title is."""
    return _sha([store or "", rule or "", sorted(public(labels).items())], 20)


def transition_key(ident: str, state: str, at) -> str:
    """One transition: the instance, the state Grafana named, and the second it began. The
    reader and the backfill compute it the same way, so either records it once."""
    return _sha([ident, (state or "").strip().lower(), int(at)], 24)


def episode_id(ident: str, started) -> str:
    """One episode (a non-normal stretch) of an instance: the instance and when it began."""
    return _sha([ident, int(started or 0)], 20)


def kind_of(state: str) -> str:
    """The reader's kind for a state Grafana named (grafana_alerts._kind): pending,
    condition (firing), no_data, error or normal."""
    from modules.readers import grafana_alerts as G
    return G._kind(state)


def kind_read(r: dict) -> str:
    """A transition row's kind as History reads it: the kind recorded, but a row recorded
    ``no_data`` for Grafana's "Alerting (NoData)" is the condition (C2174): the state Grafana
    gives only a rule whose no data is its fault, which the reader and the backfill each
    classed as no data before. The row is never rewritten; its state words stay Grafana's."""
    from modules.readers import grafana_alerts as G

    to = r.get("to") or ""
    if to == "no_data" and G.alerting_on_no_data(r.get("state")):
        return "condition"
    return to


def _device(labels: dict, device_from: str = "") -> dict:
    """The device a row names: the reader's own answer when it gave one, else the ``device``
    label, else the polled ``instance`` address (never a guessed name)."""
    labels = public(labels)
    if labels.get("device"):
        return {"device": labels["device"], "address": "", "device_from": device_from or "label"}
    if labels.get("instance"):
        return {"device": "", "address": labels["instance"], "device_from": "address"}
    return {"device": "", "address": "", "device_from": "none"}


def _row(store: str, networks, rule: str, state: str, labels: dict, at, source: str, *,
         rule_uid: str = "", prev_state: str = "", grafana_id=None, value="", kind: str = "",
         device: dict = None, now: float = None) -> dict:
    labels = public(labels)
    ident = identity(store, rule, labels)
    kind = kind or kind_of(state)
    row = {"schema": SCHEMA, "kind": "transition", "store": store,
           "networks": list(networks or []), "identity": ident,
           "key": transition_key(ident, state, at), "rule": rule or "", "rule_uid": rule_uid or "",
           "state": state or "", "to": kind, "prev_state": prev_state or "", "labels": labels,
           "at": iso(at), "at_basis": AT_BASIS.get(source, source), "source": source,
           "grafana_id": grafana_id, "value": value,
           "recorded_at": iso(time.time() if now is None else now)}
    row.update(device or _device(labels))
    return row


# ----------------------------------------------------------------------------- the sources

def from_reader(value: dict, store: str, networks=(), now: float = None) -> list:
    """The transitions a reader value shows: each instance in a state other than normal (its
    ``activeAt``, or the Alertmanager's ``startsAt`` for an alert only it holds), and each
    recently normal instance (a resolve, kept only after a recorded non-normal state:
    ``requires_open``). An instance with no Grafana time is left out, never timed by Mercury."""
    out = []
    for inst in (value or {}).get("instances") or []:
        at, source = epoch(inst.get("active_at")), "reader"
        if at is None:
            at, source = epoch(inst.get("starts_at")), "reader_am"
        if at is None:
            continue
        dev = {"device": inst.get("device") or "", "address": inst.get("address") or "",
               "device_from": inst.get("device_from") or "none"}
        out.append(_row(store, networks, inst.get("rule") or "", inst.get("state") or "",
                        inst.get("labels"), at, source, rule_uid=inst.get("rule_uid") or "",
                        value=inst.get("value") or "", kind=inst.get("kind") or "",
                        device=dev, now=now))
    for inst in (value or {}).get("recently_normal") or []:
        at = epoch(inst.get("active_at"))
        if at is None:
            continue
        dev = {"device": inst.get("device") or "", "address": inst.get("address") or "",
               "device_from": inst.get("device_from") or "none"}
        row = _row(store, networks, inst.get("rule") or "", inst.get("state") or "",
                   inst.get("labels"), at, "reader", rule_uid=inst.get("rule_uid") or "",
                   kind="normal", device=dev, now=now)
        row["requires_open"] = True
        out.append(row)
    return out


def from_detections(store: str, networks=(), fired=(), resolved=(), now: float = None) -> list:
    """The transitions of a source Mercury runs itself (the SDN detections, `modules/sdn/
    detect.py`): each of *fired*, an instance in the reader's shape, firing from its
    ``active_at``; each of *resolved*, ``(instance, epoch)``, normal from then (kept only
    after its firing, as the reader's resolves are). Keyed as the reader keys its own (the
    store, the rule, the labels, the state and its second)."""
    out = []
    none = {"device": "", "address": "", "device_from": "none"}
    for inst in fired:
        at = epoch(inst.get("active_at"))
        if at is None:
            continue
        out.append(_row(store, networks, inst.get("rule") or "", inst.get("state") or "Alerting",
                        inst.get("labels"), at, "sdn", rule_uid=inst.get("rule_uid") or "",
                        value=inst.get("value") or "", kind="condition", device=dict(none),
                        now=now))
    for inst, at in resolved:
        row = _row(store, networks, inst.get("rule") or "", "Normal", inst.get("labels"), at,
                   "sdn", rule_uid=inst.get("rule_uid") or "", kind="normal",
                   device=dict(none), now=now)
        row["requires_open"] = True
        out.append(row)
    return out


def annotation_labels(a: dict) -> dict:
    """An alert annotation's labels, exactly as the rules view names them. Grafana writes them
    twice: as tags, ``key:value``, where a colon in a VALUE becomes ``_`` (measured
    2026-10-26: ``alertname:NMAS heartbeat missing_ edge1`` for the rule ``NMAS heartbeat
    missing: edge1``; an IPv6 address or a ``host:port`` would be mangled the same way), and in
    the text's
    braces, ``{key=value, key=value}``, sorted by key, values whole. So the keys are the tags',
    and each value is read from the braces, split only before a known key; when the braces do
    not hold exactly the tags' keys, the tags are used as they are."""
    tags = {}
    for tag in a.get("tags") or []:
        k, sep, v = str(tag).partition(":")
        if sep and k:
            tags[k] = v
    m = re.search(r"\{(.*)\}(?: - |\s*$)", a.get("text") or "", re.S)
    if not m:
        return tags
    body = m.group(1)
    keys = sorted(tags, key=len, reverse=True)
    if keys:
        parts = re.split(r", (?=(?:%s)=)" % "|".join(re.escape(k) for k in keys), body)
    else:
        parts = body.split(", ")
    text = {}
    for part in parts:
        k, sep, v = part.partition("=")
        if sep and k:
            text[k.strip()] = v
    if not tags or set(text) == set(tags):
        return text
    return tags


def from_annotation(a: dict, store: str, networks=(), now: float = None):
    """One Grafana alert annotation (its state history) as a row, or None: a move between two
    normal states (``Normal`` to ``Normal (Updated)``) is not an alert's transition."""
    new, prev = a.get("newState") or "", a.get("prevState") or ""
    if kind_of(new) == "normal" and kind_of(prev) == "normal":
        return None
    ms = a.get("time")
    if not isinstance(ms, (int, float)) or ms <= 0:
        return None
    values = ((a.get("data") or {}).get("values")) or {}
    return _row(store, networks, a.get("alertName") or "", new, annotation_labels(a),
                int(ms // 1000), "backfill", prev_state=prev, grafana_id=a.get("id"),
                value=", ".join(f"{k}={v}" for k, v in sorted(values.items())), now=now)


# ----------------------------------------------------------------------------- the store

def _path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, FILE_NAME)


def build_lock_path() -> str:
    """The lock Build evidence holds across finding a past alert's pack and keeping a new one,
    beside the store (its own, so a build never holds the store a reader appends to)."""
    return _path() + ".build.lock"


def read() -> dict:
    """Every row, oldest first: ``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``. A
    torn line is skipped, as the evidence packs skip one."""
    from modules import records_migrate

    got = records_migrate.store_rows(STORE, _path(), skip_unparsable=True)
    if got["state"] == "unreadable":
        log.error("alert_history: the store is unreadable (%s)", got["error"])
    return got


def moved_keys(rows) -> set:
    out = set()
    for r in rows:
        if r.get("kind") == "moved":
            out.update(r.get("keys") or [])
    return out


def transitions(rows) -> list:
    """The transition rows still served here: every one not moved to the data lake."""
    gone = moved_keys(rows)
    return [r for r in rows if r.get("kind") == "transition" and r.get("key") not in gone]


def record(rows) -> dict:
    """Append each of *rows* the store does not hold: ``{"ok", "added", "held", "unopened",
    "error"}``. Under the store's cross-process lock across the read and the append, so two
    writers (the reader in each worker, a backfill) never both add one transition. A resolve
    seen by the reader (``requires_open``) is kept only after a recorded non-normal state of
    the same instance that began no later than it. An unreadable store adds nothing."""
    from modules import records_migrate, redact
    from modules.filestore import PathLock

    added = held = unopened = 0
    try:
        with PathLock(_path):
            got = read()
            if got["state"] == "unreadable":
                return {"ok": False, "added": 0, "held": 0, "unopened": 0,
                        "error": f"the alert history cannot be read ({got['error']})"}
            keys = {r.get("key") for r in got["rows"] if r.get("kind") == "transition"}
            # Each instance's latest recorded state, in Grafana's order (a resolve after the
            # state it ends, at the same second).
            last = {}

            def note(r):
                mark = (r.get("at") or "", r.get("to") == "normal")
                if mark >= last.get(r["identity"], ("", False)):
                    last[r["identity"]] = mark

            for r in got["rows"]:
                if r.get("kind") == "transition" and r.get("identity"):
                    note(r)
            for row in sorted(rows, key=lambda r: (r.get("at") or "", r.get("to") == "normal")):
                if row["key"] in keys:
                    held += 1
                    continue
                if row.pop("requires_open", False):
                    at, normal = last.get(row["identity"], ("", True))
                    if normal or at > row["at"]:
                        unopened += 1
                        continue
                kept = redact.redact_payload(row)
                kept["key"] = row["key"]
                records_migrate.store_append(STORE, _path(), kept)
                keys.add(row["key"])
                note(row)
                added += 1
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.error("alert_history: COULD NOT KEEP %d transition(s) (%s)", len(rows), exc)
        return {"ok": False, "added": added, "held": held, "unopened": unopened,
                "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "added": added, "held": held, "unopened": unopened, "error": ""}


# ----------------------------------------------------------------------------- the reader

_LAST_SEEN: dict = {}
_LAST_EXPIRE = {"at": 0.0}
_MEMO_LOCK = threading.Lock()


def _networks() -> dict:
    """``{store: [network, ...]}``: the networks reading each configuration of the alerts
    reader (`integration_groups`), Default's store first."""
    from modules import integration_groups as IG
    from modules.readers import grafana_alerts as G

    out = {}
    try:
        for g in IG.groups(tuple(G.READER.per_group)):
            out[IG.store_name(G.READER.name, g["id"])] = list(g["lists"])
    except Exception as exc:                          # noqa: BLE001
        log.warning("alert_history: the networks of each alert configuration could not be "
                    "listed (%s)", exc)
    return out


def after_alerts_read(clock=time.time) -> bool:
    """The alerts reader's after-store step: each transition its stored values show that the
    history does not hold, recorded. The store is read only when a configuration's value
    changed since this process last recorded it. True when a row was added. Never raises."""
    from modules import evidence_pack, reader_job

    added = 0
    nets = _networks()
    for name in evidence_pack._alert_stores():
        got = reader_job.read_cached(name)
        good = ((got.get("doc") or {}).get("last_good") or {})
        value = good.get("value") or {}
        rows = from_reader(value, name, nets.get(name) or [], now=clock())
        seen = frozenset(r["key"] for r in rows)
        with _MEMO_LOCK:
            if _LAST_SEEN.get(name) == seen:
                continue
        got = record(rows)
        if got["ok"]:
            with _MEMO_LOCK:
                _LAST_SEEN[name] = seen
            added += got["added"]
    if clock() - _LAST_EXPIRE["at"] >= EXPIRE_EVERY_SECONDS:
        _LAST_EXPIRE["at"] = clock()
        try:
            got = expire(now=clock())
            if got["moved"] or got["why"]:
                log.info("alert_history: retention: %d moved to the data lake, %d kept%s",
                         got["moved"], got["kept"], f" ({got['why']})" if got["why"] else "")
        except Exception as exc:                      # noqa: BLE001
            log.error("alert_history: the retention move failed (%s)", exc)
    return added > 0


# ----------------------------------------------------------------------------- retention

def retention_days(network: str) -> int:
    """*network*'s `alert_history_retention_days` (Default's for a row naming none)."""
    from modules import list_settings
    try:
        got = int(list_settings.value(network or list_settings.DEFAULT_LIST,
                                      "alert_history_retention_days", RETENTION_DAYS)
                  or RETENTION_DAYS)
    except (TypeError, ValueError):
        got = RETENTION_DAYS
    return max(1, got)


def _archive_for(network: str):
    """``(put, "")`` for *network*'s S3/MinIO archive (the data lake), or ``(None, why)``."""
    from modules.integrations.s3_archive import Unavailable, archive

    integration = archive(network)
    if not integration.is_configured():
        return None, (f"{network or 'Default'} has no S3/MinIO archive configured, so the "
                      "alert history past retention stays here, unmoved")
    try:
        client = integration.client()
    except Unavailable as exc:
        return None, f"{exc}, so the alert history past retention stays here"

    def put(key, data):
        integration.put(integration.key(key), data,
                        metadata={"masking": "redact_payload", "rows": "alert-history"},
                        client=client)
    return put, ""


def expire(now: float = None, archive=None) -> dict:
    """Move every transition older than its networks' longest retention to the data lake:
    ``{"moved", "kept", "why", "objects"}``. *archive* is ``put(key, bytes)`` (tests), by
    default each network's S3/MinIO archive; with none, nothing moves and why is said. A row
    is due by GRAFANA's time (``at``), never by when Mercury recorded it."""
    from modules import records_migrate, redact
    from modules.filestore import PathLock

    now = time.time() if now is None else now
    got = read()
    if got["state"] == "unreadable":
        return {"moved": 0, "kept": 0, "why": f"the alert history cannot be read "
                                               f"({got['error']})", "objects": []}
    due = {}
    for r in transitions(got["rows"]):
        nets = r.get("networks") or [""]
        days = max(retention_days(n) for n in nets)
        at = epoch(r.get("at"))
        if at is not None and now - at > days * 86400:
            due.setdefault(nets[0], []).append((r, days))
    if not due:
        return {"moved": 0, "kept": 0, "why": "", "objects": []}
    moved, kept, whys, objects = 0, 0, [], []
    for network, items in sorted(due.items()):
        put, why = (archive, "") if archive is not None else _archive_for(network)
        if put is None:
            kept += len(items)
            whys.append(why)
            continue
        rows = [r for r, _d in items]
        first, last = rows[0]["at"], rows[-1]["at"]
        key = (f"{ARCHIVE_PREFIX}/{network or 'Default'}/"
               f"{first.replace(':', '')}_{last.replace(':', '')}_{len(rows)}.jsonl")
        body = "".join(json.dumps(redact.redact_payload(r), sort_keys=True) + "\n"
                       for r in rows).encode("utf-8")
        try:
            put(key, body)
        except Exception as exc:                      # noqa: BLE001 (kept, named)
            kept += len(rows)
            whys.append(f"the archive refused {key}: {type(exc).__name__}: {exc}")
            continue
        marker = {"schema": SCHEMA, "kind": "moved", "keys": [r["key"] for r in rows],
                  "archive_key": key, "network": network or "Default", "at": iso(now),
                  "days": max(d for _r, d in items), "count": len(rows),
                  "first": first, "last": last}
        with PathLock(_path):
            records_migrate.store_append(STORE, _path(), marker)
        moved += len(rows)
        objects.append(key)
    return {"moved": moved, "kept": kept, "why": "; ".join(whys), "objects": objects}


class Refused(RuntimeError):
    """A declared seam that cannot act yet, naming why."""


def compact():
    """Drop the moved rows from the store itself. Refused: the line stores are append-only
    (`records_migrate.store_append`, on the file and on the records database alike) and no
    rewrite path exists for them; until one does, a moved row stays in the store, hidden by
    its ``moved`` row, and the data lake holds its copy."""
    raise Refused("the alert history is an append-only line store (records_migrate."
                  "store_append): no rewrite path exists to drop moved rows, so they stay, "
                  "hidden by their 'moved' row, their copy in the data lake")


# ----------------------------------------------------------------------------- episodes

def _firing_now() -> set:
    """The identities the alerts reader holds in a state other than normal now (each
    configuration's last good value), so an episode whose resolve was not recorded is said to
    have ended only when the reader no longer holds it."""
    from modules import evidence_pack, reader_job

    out = set()
    for name in evidence_pack._alert_stores():
        got = reader_job.read_cached(name)
        value = (((got.get("doc") or {}).get("last_good") or {}).get("value") or {})
        for inst in value.get("instances") or []:
            out.add(identity(name, inst.get("rule") or "", inst.get("labels")))
    # Mercury's own SDN detections still firing (their store's state, PHASE8_PLAN 17.1 S6).
    for store, inst in evidence_pack.sdn_firing()["instances"]:
        out.add(identity(store, inst.get("rule") or "", inst.get("labels")))
    return out


def episodes(rows, firing_now=frozenset()) -> list:
    """Each instance's non-normal stretches, from its transitions in Grafana's order: begun at
    its first non-normal state, ended at the normal state after it. One still open is
    ``ongoing`` when the reader holds it now, else ended with its resolve not recorded."""
    by = {}
    for r in transitions(rows):
        by.setdefault(r["identity"], []).append(r)
    out = []
    for ident, rs in by.items():
        rs.sort(key=lambda r: (r.get("at") or "", r.get("to") == "normal"))
        open_ = None
        for r in rs:
            if r.get("to") != "normal":
                if open_ is None:
                    open_ = {"identity": ident, "store": r.get("store") or "",
                             "networks": r.get("networks") or [], "rule": r.get("rule") or "",
                             "rule_uid": r.get("rule_uid") or "", "labels": r.get("labels") or {},
                             "device": r.get("device") or "", "address": r.get("address") or "",
                             "device_from": r.get("device_from") or "",
                             "started_at": r.get("at") or "", "fired_at": "", "resolved_at": "",
                             "resolved_state": "", "states": [], "sources": set(),
                             "ongoing": False}
                if not open_["rule_uid"] and r.get("rule_uid"):
                    open_["rule_uid"] = r["rule_uid"]
                open_["states"].append({"at": r.get("at") or "", "state": r.get("state") or "",
                                        "to": kind_read(r)})
                open_["sources"].add(r.get("source") or "")
                if kind_read(r) == "condition" and not open_["fired_at"]:
                    open_["fired_at"] = r.get("at") or ""
            elif open_ is not None:
                open_["resolved_at"], open_["resolved_state"] = r.get("at") or "", r.get("state")
                open_["sources"].add(r.get("source") or "")
                out.append(open_)
                open_ = None
        if open_ is not None:
            open_["ongoing"] = ident in firing_now
            out.append(open_)
    for e in out:
        kinds = {s["to"] for s in e["states"]}
        e["outcome"] = ("fired" if "condition" in kinds else "no_data" if "no_data" in kinds
                        else "error" if "error" in kinds else "pending_only")
        e["sources"] = sorted(e["sources"])
        e["id"] = episode_id(e["identity"], epoch(e["started_at"]))
        start, end = epoch(e["started_at"]), epoch(e["resolved_at"])
        e["duration_s"] = (end - start) if start is not None and end is not None else None
        e["duration_words"] = duration_words(e["duration_s"])
    out.sort(key=lambda e: e["started_at"], reverse=True)
    return out


def _pack_index(packs) -> dict:
    """``{identity: [(began, summary)]}`` and ``{episode id: summary}`` for the kept packs:
    a pack built from the history names its episode; one built when its alert fired is
    matched by its alert's instance and when it began."""
    from modules import evidence_pack as EP

    by_ident, by_episode = {}, {}
    for p in packs:
        summary = EP.pack_summary(p)
        if p.get("episode"):
            by_episode[p["episode"]] = summary
            continue
        alert = next((s for s in p.get("sections") or [] if s.get("name") == "alert"), {})
        piece = (alert.get("pieces") or [{}])[0]
        began = epoch(piece.get("starts_at")) or epoch(piece.get("active_at"))
        if began is None:
            continue
        ident = identity(p.get("store") or "", piece.get("rule") or "", piece.get("labels"))
        by_ident.setdefault(ident, []).append((began, summary))
    return {"identity": by_ident, "episode": by_episode}


def pack_for(e: dict, index: dict):
    """The kept pack for episode *e*, or None."""
    got = index["episode"].get(e["id"])
    if got:
        return got
    start = epoch(e["started_at"])
    end = epoch(e["resolved_at"]) or float("inf")
    for began, summary in index["identity"].get(e["identity"], []):
        if start is not None and start - PACK_SLACK_SECONDS <= began <= end + PACK_SLACK_SECONDS:
            return summary
    return None


def find(eid: str):
    """``(episode or None, store state, error)``: the episode with id *eid*."""
    got = read()
    match = [e for e in episodes(got["rows"], _firing_now()) if e["id"] == eid]
    return (match[0] if match else None), got["state"], got["error"]


def episode_of(pack: dict):
    """``(episode or None, store state, error)``: the past alert a kept *pack* is of: the
    episode it names (one built from the history), else the one `pack_for` matches it to (one
    built as its alert fired: its alert's instance, begun within the episode's span). One still
    firing is no past alert, and is not returned."""
    if pack.get("episode"):
        e, state, error = find(pack["episode"])
        return (e if e is not None and not e["ongoing"] else None), state, error
    got = read()
    index = _pack_index([pack])
    match = [e for e in episodes(got["rows"], _firing_now())
             if not e["ongoing"] and pack_for(e, index)]
    return (match[0] if match else None), got["state"], got["error"]


def tab(args=None, now: float = None) -> dict:
    """Monitoring › Alerts › History: the episodes that ended, in the range asked, grouped by
    rule family and collapsed, each with its pack or that it has none; a summary of counts by
    outcome first. Reads the history store, the pack store and the alerts reader's stores,
    once each: no source is asked."""
    from modules import evidence_pack as EP

    args = args or {}
    now = time.time() if now is None else now
    q = (args.get("q") or "").strip()[:80]
    rule = (args.get("rule") or "").strip()[:200]
    device = (args.get("device") or "").strip()[:80]
    rng = args.get("range") if args.get("range") in RANGES else "7d"
    show = args.get("show") if args.get("show") in ("fired", "all") else "fired"
    got = read()
    rows = got["rows"]
    eps = [e for e in episodes(rows, _firing_now()) if not e["ongoing"]]
    span = RANGES[rng]
    if span:
        cut = iso(now - span)
        eps = [e for e in eps if (e["started_at"] or "") >= cut]
    in_range = len(eps)
    by_outcome = {o: sum(1 for e in eps if e["outcome"] == o) for o in OUTCOMES}
    families = sorted({EP.family(e["rule"], e["device"]) for e in eps})
    want, dev = q.lower(), device.lower()

    def matches(e):
        if show == "fired" and e["outcome"] != "fired":
            return False
        if rule and EP.family(e["rule"], e["device"]) != rule:
            return False
        if dev and dev not in (e["device"] or "").lower() and dev not in (e["address"] or ""):
            return False
        if want and not any(want in (t or "").lower() for t in (
                e["rule"], e["device"], e["address"],
                " ".join(f"{k}={v}" for k, v in sorted(e["labels"].items())))):
            return False
        return True

    shown = [e for e in eps if matches(e)]
    packs = EP.read()
    index = _pack_index(packs["rows"])
    groups = {}
    for e in shown:
        e["pack"] = pack_for(e, index)
        e["family"] = EP.family(e["rule"], e["device"])
        e["summary_labels"] = ", ".join(f"{k}={v}" for k, v in sorted(e["labels"].items())
                                        if k not in ("alertname", "grafana_folder"))
        # What the row draws, and no more: the labels as their summary, the duration in words,
        # each state as Grafana named it (an ongoing episode is never in History).
        view = {k: v for k, v in e.items()
                if k not in ("labels", "duration_s", "ongoing")}
        view["states"] = [{"at": s["at"], "state": s["state"]} for s in e["states"]]
        groups.setdefault(e["family"], []).append(view)
    trans = transitions(rows)
    oldest = min((r.get("at") for r in trans if r.get("at")), default="")
    first_reader = min((r.get("at") for r in trans if r.get("source", "").startswith("reader")
                        and r.get("at")), default="")
    return {"q": q, "rule": rule, "device": device, "range": rng, "show": show,
            "range_words": RANGE_WORDS[rng],
            "ranges": [{"value": k, "words": RANGE_WORDS[k]} for k in RANGES],
            "families": families,
            "store": {"state": got["state"], "error": got["error"]},
            "packs_store": {"state": packs["state"], "error": packs["error"]},
            "counts": {"in_range": in_range, "shown": len(shown),
                       "devices": len({e["device"] or e["address"] for e in shown}),
                       "packed": sum(1 for e in shown if e["pack"]),
                       "outcomes": by_outcome, "transitions": len(trans),
                       "moved": len(moved_keys(rows))},
            "outcome_words": OUTCOME_WORDS, "oldest": oldest, "first_reader": first_reader,
            "groups": [{"family": f, "count": len(es), "devices": len({e["device"] or
                                                                        e["address"]
                                                                        for e in es}),
                        "episodes": es[:GROUP_SHOWN]}
                       for f, es in sorted(groups.items(), key=lambda kv: (-len(kv[1]),
                                                                          kv[0]))],
            "group_shown": GROUP_SHOWN}
