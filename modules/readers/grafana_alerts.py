"""The Grafana alert reader: the first reader job (modules/reader_job.py).

What it stores is what Grafana SAID, from three endpoints, each named on the
result (rule 4): the rules' configuration (the ruler), their evaluated state
(the rules view) and the instances being alerted on (the Alertmanager). It
decides nothing about what a person should do; Needs attention does that
from the cache (rule 1). The rules this reader keeps, in addition to the
pattern's, each from a finding on 2026-09-28:

- **Condition, no-data and error are three kinds, never one "firing".** C165
  compared condition-firing against all instances, and two DatasourceNoData
  instances made "0 against 2" read as a disagreement. A rule whose query
  returns nothing is not a rule whose condition holds, and a rule that
  cannot evaluate is neither.

- **A rule in no-data is shown, not only its firing instances.** Two of the
  seven hand-built rules read no-data for days while the network was healthy
  (C166, C168), and nothing outside Grafana saw it. `rules[].health` carries
  `nodata` and `error` for every rule, whether or not any instance fires.

- **Which device: from a LABEL, from the LINE, or from an ADDRESS, and the
  reader says which** (8.6's constraint; the operator's "one definition of
  which device"). A heartbeat rule is generated per device, so its `device`
  label is the generator's claim. The syslog rule extracts the device from
  the message with `ORIGIN_ID_PATTERN`, the one definition, and the reader
  records whether the rule's pattern IS that definition: C166's first fix
  captured the IOS sequence number as the device (labels 1396, 167...).
  An SNMP rule carries the polled `instance` address, which the reader
  stores as an address, never a guessed name; a consumer resolves it
  against the inventory and says when it cannot.

- **An instance is the rule, its label fingerprint and `startsAt`** (8.6), so
  a re-fire after a resolve is a new instance. The reader keeps `active_at`
  (when the condition first held), `starts_at` (when it began alerting) and
  the rule's `for` and `window_seconds`, because the ONSET, not `startsAt`,
  is what groups one outage into one incident (per-device windows fire one
  Loki outage up to 536 s apart).

- **Grafana's own evaluator is watched.** Every rule reading `ok` proves
  nothing if the evaluator stopped: a group whose last evaluation is older
  than three of its intervals at the time of the read is listed in
  `stalled_groups`.

- **Completeness is judged from Grafana's own counts** (rule 5): a group
  whose totals count more rules than it lists, or a rule whose totals count
  more instances than it lists, is a partial answer, and the read is refused.

History (`api/v1/rules/history`) is NOT read here: it is capped at 100 rows
and a claim about all time needs a window that covers all time (rule 6).
It is 8.6's, read uncapped by splitting the window.
"""

import logging
import re
import time

from modules import reader_job

log = logging.getLogger(__name__)

RULER = "api/ruler/grafana/api/v1/rules"
RULES_VIEW = "api/prometheus/grafana/api/v1/rules"
ALERTMANAGER = "api/alertmanager/grafana/api/v2/alerts"

#: The ONE definition of "which device" in a syslog line: the origin-id after
#: the IOS sequence number (``719: s4: %SYS-5-...``). The stream's host label
#: is the collector, so it can never be the device (C166). A rule extracting
#: the device from a line uses exactly this; P.7's generators import it.
ORIGIN_ID_PATTERN = r"\d+: (?P<device>[A-Za-z][A-Za-z0-9._-]*): "

#: How many of a group's intervals may pass without an evaluation before the
#: evaluator is called stalled. Three, like the reader's own staleness: one
#: late evaluation is not a stop.
STALLED_AFTER_INTERVALS = 3

_DURATION = re.compile(r"(\d+)(ms|s|m|h|d)")
_UNIT = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}
_REGEXP_ARG = re.compile(r'\|\s*regexp\s+(?:"((?:[^"\\]|\\.)*)"|`([^`]*)`)')


class PartialAnswer(RuntimeError):
    """Grafana's own counts say it listed less than it holds (rule 5)."""


def duration_seconds(text) -> int:
    """``"1m30s"`` -> 90. An empty or ``0s`` duration is 0."""
    if isinstance(text, (int, float)):
        return int(text)
    return int(sum(int(n) * _UNIT[u] for n, u in _DURATION.findall(str(text or ""))))


def _public(labels: dict) -> dict:
    """Grafana's internal labels (``__grafana_receiver__`` and the like) are
    routing, not identity: two views of one instance differ only in them."""
    return {k: v for k, v in (labels or {}).items() if not k.startswith("__")}


def _identity(labels: dict) -> tuple:
    return tuple(sorted(_public(labels).items()))


def line_patterns(exprs) -> list:
    """Every ``| regexp`` argument naming a ``device`` group, unescaped as
    LogQL reads a double-quoted string (a backtick string is raw)."""
    found = []
    for expr in exprs:
        for quoted, raw in _REGEXP_ARG.findall(expr or ""):
            pattern = raw if raw else re.sub(r"\\(.)", r"\1", quoted)
            if "(?P<device>" in pattern:
                found.append(pattern)
    return found


def device_source(rule_labels: dict, exprs) -> dict:
    """How this rule's instances name their device, decided from the rule's
    CONFIGURATION, never from whichever instance happens to be firing."""
    if (rule_labels or {}).get("device"):
        return {"from": "label", "why": "the rule is generated per device and carries a "
                                        "device label"}
    patterns = line_patterns(exprs)
    if patterns:
        same = all(p == ORIGIN_ID_PATTERN for p in patterns)
        return {"from": "line", "matches_definition": same,
                "why": ("the device is extracted from the message by the one origin-id "
                        "pattern" if same else
                        "the device is extracted from the message by a pattern that is NOT "
                        f"the one definition: {patterns[0]!r}")}
    return {"from": "address_or_none",
            "why": "the rule names no device; an instance's `instance` label is the polled "
                   "address, when it has one"}


def _instance_device(labels: dict, source: dict) -> dict:
    labels = _public(labels)
    if source["from"] in ("label", "line") and labels.get("device"):
        return {"device": labels["device"], "device_from": source["from"]}
    if labels.get("instance"):
        return {"address": labels["instance"], "device_from": "address"}
    return {"device_from": "none"}


def _kind(state: str) -> str:
    """The rules view's instance state, as one of the three kinds (or a state
    that is not a problem). ``Normal (NoData)`` is a rule whose no-data state
    is OK by decision (Interface down: no data is healthy), so it is normal."""
    s = (state or "").lower()
    if s.startswith("normal"):
        return "normal"
    if s.startswith("pending"):
        return "pending"
    if "nodata" in s:
        return "no_data"
    if "error" in s:
        return "error"
    if s.startswith("alerting") or s == "firing":
        return "condition"
    return "unknown_state"


def parse(ruler: dict, view: dict, alerts: list, read_at: float) -> dict:
    """The stored value, from the three answers. Pure, so a test drives it
    with the captured answers and a changed piece."""
    config = {}
    for folder, groups in (ruler or {}).items():
        for grp in groups or []:
            for rule in grp.get("rules") or []:
                ga = rule.get("grafana_alert") or {}
                exprs = [(d.get("model") or {}).get("expr", "") for d in ga.get("data") or []]
                config[ga.get("uid")] = {
                    "folder": folder, "group": grp.get("name"),
                    "for_seconds": duration_seconds(rule.get("for")),
                    "labels": rule.get("labels") or {},
                    "no_data_state": ga.get("no_data_state"),
                    "exec_err_state": ga.get("exec_err_state"),
                    "device_source": device_source(rule.get("labels"), exprs)}

    data = (view or {}).get("data") or {}
    if data.get("groupNextToken"):
        raise PartialAnswer("the rules view returned a next-page token: it listed one page of "
                            "several")
    rules, instances, stalled = [], [], []
    counts = {"rules": 0, "normal": 0, "normal_no_data": 0, "pending": 0,
              "condition": 0, "no_data": 0, "error": 0, "unknown_state": 0}
    for grp in data.get("groups") or []:
        listed = grp.get("rules") or []
        held = sum((grp.get("totals") or {}).values())
        if held and held > len(listed):
            raise PartialAnswer(f"group {grp.get('name')!r} counts {held} rules and lists "
                                f"{len(listed)}")
        interval = int(grp.get("interval") or 0)
        last = reader_job._parse_iso((grp.get("lastEvaluation") or "")[:19] + "Z")
        if interval and (last is None or read_at - last > STALLED_AFTER_INTERVALS * interval):
            stalled.append({"group": grp.get("name"), "folder": grp.get("file"),
                            "interval_seconds": interval,
                            "last_evaluation": grp.get("lastEvaluation")})
        for r in listed:
            counts["rules"] += 1
            uid = r.get("uid")
            cfg = config.get(uid) or {}
            source = cfg.get("device_source") or device_source(r.get("labels"), [r.get("query")])
            listed_alerts = r.get("alerts") or []
            held_alerts = sum((r.get("totals") or {}).values())
            if held_alerts and held_alerts > len(listed_alerts):
                raise PartialAnswer(f"rule {r.get('name')!r} counts {held_alerts} instances and "
                                    f"lists {len(listed_alerts)}")
            rules.append({
                "uid": uid, "title": r.get("name"), "folder": cfg.get("folder"),
                "group": grp.get("name"), "state": r.get("state"),
                "health": r.get("health"), "last_error": r.get("lastError") or "",
                "last_evaluation": r.get("lastEvaluation"),
                "for_seconds": cfg.get("for_seconds", 0),
                "no_data_state": cfg.get("no_data_state"),
                "exec_err_state": cfg.get("exec_err_state"),
                "device_source": source, "configured": uid in config,
                "labels": cfg.get("labels") or r.get("labels") or {}})
            for a in listed_alerts:
                kind = _kind(a.get("state"))
                if kind == "normal":
                    counts["normal_no_data" if "nodata" in (a.get("state") or "").lower()
                           else "normal"] += 1
                    continue
                counts[kind] += 1
                labels = _public(a.get("labels"))
                instances.append({
                    "rule_uid": uid, "rule": r.get("name"), "kind": kind,
                    "state": a.get("state"), "labels": labels,
                    "active_at": a.get("activeAt"), "value": a.get("value", ""),
                    "for_seconds": cfg.get("for_seconds", 0),
                    "window_seconds": int(labels.get("window_seconds") or 0) or None,
                    "window_basis": labels.get("window_basis"),
                    "fingerprint": None, "starts_at": None, "silenced_by": [],
                    **_instance_device(labels, source)})

    # The Alertmanager's instances carry what the rules view lacks: the label
    # fingerprint and `startsAt` (8.6's instance identity). Joined on the
    # public labels. One the rules view does not list (Grafana's own
    # DatasourceNoData and DatasourceError alerts, named by `rulename`) is
    # kept as its own instance, never dropped.
    by_identity = {}
    for inst in instances:
        by_identity.setdefault(_identity(inst["labels"]), inst)
    by_title = {r["title"]: r for r in rules}
    by_uid = {r["uid"]: r for r in rules}
    unmatched = 0
    for am in alerts or []:
        labels = _public(am.get("labels"))
        status = am.get("status") or {}
        extra = {"fingerprint": am.get("fingerprint"), "starts_at": am.get("startsAt"),
                 "silenced_by": list(status.get("silencedBy") or [])}
        inst = by_identity.get(_identity(labels))
        if inst is not None:
            inst.update(extra)
            continue
        name = labels.get("alertname", "")
        rule = (by_uid.get((am.get("labels") or {}).get("__alert_rule_uid__"))
                or by_title.get(labels.get("rulename")) or by_title.get(name))
        kind = {"DatasourceNoData": "no_data", "DatasourceError": "error"}.get(name, "condition")
        source = (rule or {}).get("device_source") or {"from": "address_or_none"}
        counts[kind] += 1
        unmatched += 1
        instances.append({
            "rule_uid": (rule or {}).get("uid"), "rule": (rule or {}).get("title") or name,
            "kind": kind, "state": f"alertmanager: {status.get('state', '?')}",
            "labels": labels, "active_at": None, "value": "",
            "for_seconds": (rule or {}).get("for_seconds", 0),
            "window_seconds": int(labels.get("window_seconds") or 0) or None,
            "window_basis": labels.get("window_basis"),
            **extra, **_instance_device(labels, source)})

    return {"rules": rules, "instances": instances, "counts": counts,
            "stalled_groups": stalled, "alertmanager_only": unmatched,
            "configured_rules": len(config)}


def read(client=None) -> dict:
    """Ask Grafana. Raises when it could not ask, naming the endpoint, so the
    reader records a failed attempt and keeps the last good value (rule 3)."""
    from modules.integrations.grafana import GrafanaIntegration

    g = client or GrafanaIntegration()
    answers = {}
    for path in (RULER, RULES_VIEW, ALERTMANAGER):
        got = g._get(path)
        if not got.get("ok"):
            raise ConnectionError(f"{path}: {got.get('error') or 'no answer'}")
        try:
            answers[path] = got["response"].json()
        except ValueError as exc:
            raise ValueError(f"{path}: the answer is not JSON ({exc})") from exc
    return parse(answers[RULER], answers[RULES_VIEW], answers[ALERTMANAGER], time.time())


READER = reader_job.register(reader_job.Reader(
    name="grafana-alerts",
    what="Grafana's alert rules and instances, read for Needs attention and 8.6's triage",
    endpoints=(RULER, RULES_VIEW, ALERTMANAGER),
    interval_seconds=60,
    interval_basis=("both rule groups evaluate every 60 s (measured 2026-09-28), so a "
                    "faster read sees nothing new"),
    read=read,
    invalidates=("alerts",),
    remedy=("Check Grafana's URL and token in Settings > Integrations; the error names "
            "the endpoint that refused"),
    window="the state at the read; history is not read here (8.6 reads it uncapped)",
))
