"""Alert rule changes made in Grafana, recorded by Mercury (C1886; the operator, 2026-10-27:
"Mercury should record the rule change (provisioning version or rule-file hash, who, when) in
History").

**What is kept.** The `grafana-alerts` reader reads every rule's definition from Grafana's
ruler each run (`api/ruler/grafana/api/v1/rules`), and `grafana_alerts.parse` keeps, per rule,
its version (Grafana's own change counter), a hash of its definition (`definition_hash`), who
Grafana says saved it and when, and a short digest of the parts a person reads
(`facets`): never the definition itself. Its after-store step (`after_alerts_read`) compares
that with the last recorded state of each rule and appends one row per change, never
rewritten:

- ``baseline``: the first read of a configuration with nothing recorded for it: each rule
  "first seen at version N". Not a change, and drawn as one row for the read.
- ``added``: a rule not recorded before (or recorded as removed).
- ``changed``: a recorded rule whose version or definition hash moved: old and new version,
  old and new hash, and what changed in words (`summary`: the query, the condition and
  threshold, the pending period, labels, annotations, paused, and the rest by name).
- ``removed``: a recorded rule neither the ruler nor the rules view lists any more.

**Who and when are Grafana's, where Grafana says.** The ruler gives each rule ``updated`` (when
it was last saved) and ``updated_by`` (``{"name", "uid"}``: a person's or service account's
login, measured on the capture of 2026-09-28: ``admin``, ``nmas-automation``, and
``{"name": "", "uid": "service"}`` beside ``provenance: file`` for a file-provisioned rule).
A row records them as given; where Grafana gives neither, it records "Grafana does not say",
never a guess. A removed rule has no record left to read, so its row says so. Mercury's own
clock is kept beside as ``seen_at``, named.

**An unreadable read records nothing and moves no state.** A read that failed keeps the last
good value (reader_job rule 3), so the step sees nothing new. A read whose ruler did not hold
every rule the rules view lists (`grafana_alerts.parse`'s ``rule_definitions_complete``) is a
partial answer: nothing is recorded for that configuration, and the log says why. A stored
value from before this release holds no definitions, which is "not read", never "no rules".

**Where it is kept:** the records store `alert_rule_changes` (`records_db.STORES`, the setting
`records_store_alert_rule_changes`, `file` by default: ``alert_rule_changes.jsonl`` in the data
folder), through `records_migrate.store_append` and `store_rows`, as the alert history is.
The state a change is judged against is the store itself (each rule's newest row), read under
the store's cross-process lock across the comparison and the append, so two workers never both
record one change. Every row is masked by `redact.redact_payload` before it is kept.

**Which device.** A rule generated per device carries a ``device`` label (the heartbeat rules):
its rows name that device, and the device's History draws them. Any other rule's rows are the
network's only, and the device's History does not draw them: a query naming a device is not
read as naming it, because a pattern in a query is no exact claim (the heartbeat query names
its device inside a regular expression, not as a name).
"""

import copy
import hashlib
import json
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

#: The row's own shape; a reader of a later shape says it cannot read this one.
SCHEMA = 1
#: The records store (`records_db.STORES`) and its file.
STORE = "alert_rule_changes"
FILE_NAME = "alert_rule_changes.jsonl"
#: Where each row's time comes from, said on every row.
AT_BASIS = {
    "updated": "Grafana's ruler: when the rule was last saved (updated)",
    "seen": ("Mercury's alerts reader: when it first read this, by Mercury's clock (Grafana "
             "keeps no time for it)"),
}
#: Who, where Grafana does not say.
NOT_SAID = "Grafana does not say"

#: The fields left out of a rule's definition hash, each with why. Everything else in the
#: ruler's rule is hashed: its queries and expressions (``data``), the condition, the pending
#: period (``for``), keep firing, labels, annotations, paused, the no-data and error states,
#: the title, folder, group and evaluation interval, and notification settings. The ruler
#: holds no evaluation state (the last evaluation, health and instances are the rules view's,
#: read separately and never hashed), so no evaluation time is in what is hashed.
NOT_HASHED = {
    ("grafana_alert", "version"): ("Grafana's change counter: compared on its own, so the hash "
                                   "says whether what the rule does moved, which a counter "
                                   "that moves on every save cannot"),
    ("grafana_alert", "updated"): "when Grafana saved the rule: the change's time, kept beside",
    ("grafana_alert", "updated_by"): "who saved it: kept as who, never what the rule is",
    ("grafana_alert", "provenance"): ("how the rule is managed (file provisioning, the API; none "
                                      "for the UI): kept with who, and a change of it moves "
                                      "the version"),
    ("grafana_alert", "guid"): ("Grafana's row id for the rule: its identity, never its "
                                "definition (the uid is the rule's key here)"),
    ("grafana_alert", "metadata", "editor_settings"): (
        "how Grafana's editor lays the rule out (its simplified sections): nothing the rule "
        "evaluates or sends"),
}

#: A summary longer than this is cut, said with an ellipsis: a line, never the definition.
SUMMARY_MAX = 300
#: A label value longer than this is cut in the summary.
VALUE_MAX = 40
#: The facets' names, in the summary's order.
FACET_WORDS = (("title", "title"), ("folder", "folder"), ("group", "group"),
               ("queries", "query"), ("condition", "condition"),
               ("expressions", "expression"), ("for", "pending period"),
               ("keep_firing_for", "keep firing for"), ("labels", "labels"),
               ("annotations", "annotations"), ("paused", "paused"),
               ("no_data_state", "no-data state"), ("exec_err_state", "error state"),
               ("interval", "evaluation interval"), ("notifications", "notifications"))
#: A threshold's evaluator, in words.
EVALUATOR_WORDS = {"gt": "above", "lt": "below", "gte": "at or above", "lte": "at or below",
                   "eq": "equal to", "ne": "not equal to", "within_range": "within",
                   "outside_range": "outside", "within_range_included": "within (inclusive)",
                   "outside_range_included": "outside (inclusive)"}


def _sha(obj, n: int = 16) -> str:
    return hashlib.sha256(json.dumps(obj, separators=(",", ":"), sort_keys=True, default=str)
                          .encode()).hexdigest()[:n]


def iso(ts) -> str:
    """Whole UTC seconds as ``YYYY-MM-DDTHH:MM:SSZ``; "" for none."""
    if ts is None or ts == "":
        return ""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ts)))


# ----------------------------------------------------------------------------- one rule

def definition(rule: dict) -> dict:
    """*rule* (one entry of the ruler's group) without the fields `NOT_HASHED` names."""
    out = copy.deepcopy(rule or {})
    for path in NOT_HASHED:
        node = out
        for part in path[:-1]:
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict):
            node.pop(path[-1], None)
    return out


def definition_hash(rule: dict) -> str:
    """The hash of what *rule* evaluates and sends (`definition`), 16 hex characters."""
    return _sha(definition(rule))


def _query(d: dict) -> dict:
    model = d.get("model") or {}
    text = model.get("expr") if model.get("expr") is not None else model.get("query", "")
    rng = d.get("relativeTimeRange") or {}
    return {"datasource": d.get("datasourceUid") or "", "text": _sha(text or ""),
            "range": [rng.get("from"), rng.get("to")], "all": _sha(d)}


def _evaluators(model: dict) -> list:
    out = []
    for c in model.get("conditions") or []:
        ev = c.get("evaluator") or {}
        out.append([ev.get("type") or "", list(ev.get("params") or [])])
    return out


def _expression(d: dict) -> dict:
    model = d.get("model") or {}
    return {"type": model.get("type") or "", "of": model.get("expression") or "",
            "evaluators": _evaluators(model), "reducer": model.get("reducer") or "",
            "all": _sha(d)}


def facets(rule: dict, folder: str = "") -> dict:
    """The parts of *rule* a person reads, short: each query's data source, time range and a
    hash of its text; each expression's type, input, evaluators and reducer; the condition;
    the pending period; labels as they are; each annotation's hash; paused; the no-data and
    error states; the interval; the contact point. What the summary compares; never the
    queries' or annotations' text."""
    ga = (rule or {}).get("grafana_alert") or {}
    queries, exprs = {}, {}
    for d in ga.get("data") or []:
        ref = str(d.get("refId") or "?")
        if d.get("datasourceUid") == "__expr__":
            exprs[ref] = _expression(d)
        else:
            queries[ref] = _query(d)
    notes = ga.get("notification_settings") or {}
    return {"title": ga.get("title") or "", "folder": folder or "",
            "group": ga.get("rule_group") or "", "queries": queries,
            "condition": ga.get("condition") or "", "expressions": exprs,
            "for": str(rule.get("for") or "0s"),
            "keep_firing_for": str(rule.get("keep_firing_for") or "0s"),
            "labels": {str(k): str(v) for k, v in (rule.get("labels") or {}).items()},
            "annotations": {str(k): _sha(v) for k, v in (rule.get("annotations") or {}).items()},
            "paused": bool(ga.get("is_paused")),
            "no_data_state": ga.get("no_data_state") or "",
            "exec_err_state": ga.get("exec_err_state") or "",
            "interval": ga.get("intervalSeconds"),
            "notifications": notes.get("receiver") or ("set" if notes else "")}


def who(ga: dict) -> dict:
    """Who Grafana says last saved the rule: ``{"name", "uid", "provenance", "words"}``. The
    words are Grafana's: a login as given, file provisioning as such, and, where Grafana gives
    no one, `NOT_SAID`."""
    by = ga.get("updated_by") if isinstance(ga.get("updated_by"), dict) else {}
    name, uid = str(by.get("name") or ""), str(by.get("uid") or "")
    prov = str(ga.get("provenance") or "")
    if name:
        words = f"{name} (in Grafana" + (f", provisioned by {prov})" if prov else ")")
    elif prov:
        words = f"Grafana's {prov} provisioning" + (f" (as {uid})" if uid else "")
    elif uid:
        words = f"Grafana's account {uid}"
    else:
        words = NOT_SAID
    return {"name": name, "uid": uid, "provenance": prov, "words": words}


def from_ruler(ruler: dict) -> dict:
    """``{uid: {...}}``: every rule in the ruler's answer, its version, hash, who and when, the
    devices its labels name, and its facets. Pure: `grafana_alerts.parse` keeps it on the
    reader's value."""
    out = {}
    for folder, groups in (ruler or {}).items():
        for grp in groups or []:
            for rule in grp.get("rules") or []:
                ga = rule.get("grafana_alert") or {}
                uid = ga.get("uid")
                if not uid:
                    continue
                device = str((rule.get("labels") or {}).get("device") or "")
                out[uid] = {"uid": uid, "title": ga.get("title") or "", "folder": folder,
                            "group": grp.get("name") or ga.get("rule_group") or "",
                            "version": ga.get("version"), "hash": definition_hash(rule),
                            "updated": ga.get("updated") or "", "who": who(ga),
                            "devices": [device] if device else [],
                            "facets": facets(rule, folder)}
    return out


def completeness(definitions: dict, view_uids) -> tuple:
    """``(complete, why)``: whether the ruler held every rule the rules view lists. A rule the
    view lists and the ruler does not means the ruler's answer was partial (a folder this
    token cannot read, a page missing), so no change is judged from it."""
    missing = sorted({u for u in view_uids if u} - set(definitions or {}))
    if missing:
        return False, (f"the rules view lists {len(missing)} rule(s) the ruler did not return "
                       f"({', '.join(missing[:5])}{', …' if len(missing) > 5 else ''})")
    return True, ""


# ----------------------------------------------------------------------------- the summary

def _cut(text: str, n: int) -> str:
    text = str(text)
    return text if len(text) <= n else text[:n - 1] + "…"


def _threshold(ev) -> str:
    kind, params = (ev or ["", []])[0], (ev or ["", []])[1]
    words = EVALUATOR_WORDS.get(kind, kind or "?")
    if len(params) >= 2 and "range" in kind:
        return f"{words} {params[0]} to {params[1]}"
    return f"{words} {', '.join(str(p) for p in params)}".strip()


def _dict_words(name: str, old: dict, new: dict, values: bool) -> str:
    parts = []
    for k in sorted(set(old) | set(new)):
        if k not in old:
            parts.append(f"{k} added" + (f" ({_cut(new[k], VALUE_MAX)})" if values else ""))
        elif k not in new:
            parts.append(f"{k} removed")
        elif old[k] != new[k]:
            parts.append(f"{k} {_cut(old[k], VALUE_MAX)} → {_cut(new[k], VALUE_MAX)}"
                         if values else f"{k} changed")
    return f"{name}: " + ", ".join(parts) if parts else ""


def _queries_words(old: dict, new: dict) -> list:
    out = []
    for ref in sorted(set(old) | set(new)):
        a, b = old.get(ref), new.get(ref)
        if a is None:
            out.append(f"query {ref} added")
        elif b is None:
            out.append(f"query {ref} removed")
        elif a != b:
            what = []
            if a.get("text") != b.get("text"):
                what.append("its text changed")
            if a.get("datasource") != b.get("datasource"):
                what.append("its data source changed")
            if a.get("range") != b.get("range"):
                what.append(f"its time range {a.get('range', [None])[0]} s → "
                            f"{b.get('range', [None])[0]} s back")
            out.append(f"query {ref}: " + (", ".join(what) or "its other settings changed"))
    return out


def _expressions_words(old: dict, new: dict) -> list:
    out = []
    for ref in sorted(set(old) | set(new)):
        a, b = old.get(ref), new.get(ref)
        if a is None:
            out.append(f"expression {ref} added ({(b or {}).get('type') or '?'})")
        elif b is None:
            out.append(f"expression {ref} removed")
        elif a != b:
            if a.get("evaluators") != b.get("evaluators") and b.get("evaluators"):
                olds = "; ".join(_threshold(e) for e in a.get("evaluators") or []) or "none"
                news = "; ".join(_threshold(e) for e in b.get("evaluators") or [])
                out.append(f"threshold {ref}: {olds} → {news}")
            elif a.get("reducer") != b.get("reducer"):
                out.append(f"expression {ref}: reducer {a.get('reducer') or 'none'} → "
                           f"{b.get('reducer') or 'none'}")
            elif a.get("type") != b.get("type"):
                out.append(f"expression {ref}: {a.get('type') or '?'} → {b.get('type') or '?'}")
            else:
                out.append(f"expression {ref} changed")
    return out


def summarise(old: dict, new: dict) -> tuple:
    """``(changed, words)``: the facets that differ between *old* and *new*, by name, and a
    short line saying how ("threshold C: below 1 → below 2; pending period 2m → 5m"). Empty
    when no facet differs."""
    old, new = old or {}, new or {}
    changed, parts = [], []
    for key, words in FACET_WORDS:
        a, b = old.get(key), new.get(key)
        if a == b:
            continue
        changed.append(key)
        if key == "queries":
            parts += _queries_words(a or {}, b or {})
        elif key == "expressions":
            parts += _expressions_words(a or {}, b or {})
        elif key == "labels":
            parts.append(_dict_words("labels", a or {}, b or {}, values=True))
        elif key == "annotations":
            parts.append(_dict_words("annotations", a or {}, b or {}, values=False))
        elif key == "paused":
            parts.append("paused" if b else "resumed (no longer paused)")
        elif key == "title":
            parts.append(f"renamed from {_cut(a or '', 60)!r}")
        elif key == "interval":
            parts.append(f"evaluated every {a} s → {b} s")
        else:
            parts.append(f"{words} {a or 'none'} → {b or 'none'}")
    return changed, "; ".join(p for p in parts if p)


def _change_words(prior: dict, now: dict, summary: str) -> str:
    """The row's summary: the facets' words, with what the version says beside them."""
    v0, v1 = prior.get("version"), now.get("version")
    notes = []
    if isinstance(v0, int) and isinstance(v1, int):
        if v1 > v0 + 1:
            notes.append(f"{v1 - v0} saves since the last read; Mercury saw the last")
        elif v1 < v0:
            notes.append("the version went back: the rule was made again or restored")
    if summary:
        text = summary
    elif prior.get("hash") != now.get("hash"):
        text = ("its definition changed outside the parts summarised (the query, condition, "
                "pending period, labels, annotations and paused state)")
    else:
        text = ("saved with no change to what it evaluates or sends (the editor's layout, or "
                "a save with no edit)")
    if notes:
        text += f" ({'; '.join(notes)})"
    return _cut(text, SUMMARY_MAX)


# ----------------------------------------------------------------------------- the rows

def _row(change: str, store: str, networks, cur: dict, prior: dict, now: float, **kw) -> dict:
    cur = cur or {}
    prior = prior or {}
    src = cur if cur else prior
    seen = iso(now)
    updated = cur.get("updated") or ""
    if change in ("added", "changed") and updated:
        at, basis = updated, AT_BASIS["updated"]
    else:
        at, basis = seen, AT_BASIS["seen"]
    w = cur.get("who") or {}
    row = {"schema": SCHEMA, "kind": "rule", "change": change, "store": store,
           "networks": list(networks or []), "uid": src.get("uid") or "",
           "title": src.get("title") or "", "folder": src.get("folder") or "",
           "group": src.get("group") or "",
           "version_from": prior.get("version"), "version": cur.get("version"),
           "hash_from": prior.get("hash") or "", "hash": cur.get("hash") or "",
           "changed": kw.get("changed") or [], "summary": kw.get("summary") or "",
           "facets": cur.get("facets") or {}, "devices": list(src.get("devices") or []),
           "updated": updated, "updated_by": {"name": w.get("name") or "",
                                              "uid": w.get("uid") or ""},
           "provenance": w.get("provenance") or "",
           "who": w.get("words") or (NOT_SAID + (": the rule is gone, so no record of it is "
                                                 "left to read" if change == "removed" else "")),
           "at": at, "at_basis": basis, "seen_at": seen}
    row["key"] = _sha([store, row["uid"], change, row["version"], row["hash"],
                       row["version_from"], row["hash_from"]], 24)
    return row


def latest(rows, store: str) -> dict:
    """``{uid: row}``: each rule's newest row for *store* (the order kept is the order
    recorded, under the store's lock). A removed rule's newest row is its removal."""
    out = {}
    for r in rows or []:
        if r.get("kind") == "rule" and r.get("store") == store and r.get("uid"):
            out[r["uid"]] = r
    return out


def changes(prior_rows, store: str, definitions: dict, networks=(), now: float = None) -> list:
    """The rows *definitions* (`from_ruler`'s, one configuration's) add to what *prior_rows*
    record for *store*. Pure. Nothing recorded for the store: a baseline per rule. Else a rule
    not held (or held as removed) is added, one whose version or hash moved is changed, and a
    held rule no longer listed is removed."""
    now = time.time() if now is None else now
    held = latest(prior_rows, store)
    out = []
    if not held:
        for uid in sorted(definitions or {}):
            cur = definitions[uid]
            out.append(_row("baseline", store, networks, cur, {}, now,
                            summary=f"first seen at version {cur.get('version')}"))
        return out
    for uid in sorted(definitions or {}):
        cur = definitions[uid]
        prior = held.get(uid)
        if prior is None or prior.get("change") == "removed":
            out.append(_row("added", store, networks, cur, {}, now,
                            summary=f"added at version {cur.get('version')}"))
            continue
        if prior.get("version") == cur.get("version") and prior.get("hash") == cur.get("hash"):
            continue
        from modules import redact
        # Both sides masked, as the kept facets were, so a masked value never reads as moved.
        changed, words = summarise(prior.get("facets") or {},
                                   redact.redact_payload(cur.get("facets") or {}))
        out.append(_row("changed", store, networks, cur, prior, now, changed=changed,
                        summary=_change_words(prior, cur, words)))
    for uid in sorted(set(held) - set(definitions or {})):
        prior = held[uid]
        if prior.get("change") == "removed":
            continue
        out.append(_row("removed", store, networks, {}, prior, now,
                        summary=(f"removed (was version {prior.get('version')}): neither the "
                                 "ruler nor the rules view lists it any more")))
    return out


# ----------------------------------------------------------------------------- the store

def _path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, FILE_NAME)


def read() -> dict:
    """Every row, oldest first: ``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``. A
    torn line is skipped, as the alert history skips one."""
    from modules import records_migrate

    got = records_migrate.store_rows(STORE, _path(), skip_unparsable=True)
    if got["state"] == "unreadable":
        log.error("alert_rule_changes: the store is unreadable (%s)", got["error"])
    return got


def record(store: str, definitions: dict, networks=(), now: float = None) -> dict:
    """Judge *definitions* against the store's state for *store* and append each change:
    ``{"ok", "added", "error"}``, under the store's cross-process lock across the read and the
    append. An unreadable store adds nothing and moves no state."""
    from modules import records_migrate, redact
    from modules.filestore import PathLock

    added = 0
    try:
        with PathLock(_path):
            got = read()
            if got["state"] == "unreadable":
                return {"ok": False, "added": 0,
                        "error": f"the alert rule record cannot be read ({got['error']})"}
            for row in changes(got["rows"], store, definitions, networks, now=now):
                kept = redact.redact_payload(row)
                kept["key"] = row["key"]
                records_migrate.store_append(STORE, _path(), kept)
                added += 1
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.error("alert_rule_changes: COULD NOT KEEP the rule changes of %s (%s)", store, exc)
        return {"ok": False, "added": added, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "added": added, "error": ""}


# ----------------------------------------------------------------------------- the reader

_LAST_SEEN: dict = {}
_MEMO_LOCK = threading.Lock()


def after_alerts_read(clock=time.time) -> bool:
    """The alerts reader's after-store step: each configuration's rule definitions (its last
    good value) judged against the record, and each change kept. The store is read only when
    a configuration's versions or hashes moved since this process last judged them. A value
    holding no definitions (a release before this one stored it) or a partial one records
    nothing. True when a row was added. Never raises."""
    from modules import alert_history, evidence_pack, reader_job

    added = 0
    nets = alert_history._networks()
    for name in evidence_pack._alert_stores():
        try:
            got = reader_job.read_cached(name)
            value = (((got.get("doc") or {}).get("last_good") or {}).get("value") or {})
            if "rule_definitions" not in value:
                continue
            if not value.get("rule_definitions_complete", False):
                log.warning("alert_rule_changes: %s's last read is partial, so no rule change "
                            "is judged from it: %s", name,
                            value.get("rule_definitions_why") or "no reason stored")
                continue
            defs = value.get("rule_definitions") or {}
            seen = frozenset((u, d.get("version"), d.get("hash")) for u, d in defs.items())
            with _MEMO_LOCK:
                if _LAST_SEEN.get(name) == seen:
                    continue
            out = record(name, defs, nets.get(name) or [], now=clock())
            if out["ok"]:
                with _MEMO_LOCK:
                    _LAST_SEEN[name] = seen
                added += out["added"]
        except Exception as exc:                      # noqa: BLE001 (logged, never raised)
            log.error("alert_rule_changes: %s could not be judged (%s)", name, exc)
    return added > 0
