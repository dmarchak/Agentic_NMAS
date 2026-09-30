"""Which integrations each device is CONFIGURED for, read from its committed
golden (the operator, 2026-09-30).

r6 became an SNMP target when the targets were generated from the inventory
(C232), and Grafana's "Device unreachable (SNMP)" fired on it. That was a
false statement: r6 answers SSH and its heartbeat. The true one is that r6's
configuration has no SNMP. So:

- a device is an SNMP TARGET only once its committed golden configures SNMP
  (`prometheus_targets.generate()` asks `configured(...)["snmp"]`), the same
  way the IP SLA targets follow the goldens;
- a device NOT configured for an integration the network uses is a job-health
  row, `not_monitored`, saying which and why ("r6 is not monitored by SNMP: its
  configuration has no SNMP"), drawn by Needs attention.

An integration is EXPECTED only when its connector is configured in the NMAS:
SNMP when Prometheus is, syslog and the heartbeat when Loki is. The monitoring
profile (NSOT_PLAN P.9, designed, not built) is what will put the lines there;
until it exists the row's action says so rather than naming a control that
does not exist. Telemetry and IP SLA are the profile's too, and are not rows
here: no NMAS connector says a network uses them (the Telegraf endpoint is not
a setting), and IP SLA is per device by nature.

A golden that cannot be READ is never "not configured": the row is `unknown`.
"""

import logging
import re

log = logging.getLogger(__name__)

#: What in a golden shows each integration configured, at column 0.
CHECKS = {
    # SNMPv2c: what snmp_exporter's `public_v2` auth module speaks. A v3-only
    # device would not answer it, so a `snmp-server user` alone does not count.
    "snmp": re.compile(r"^snmp-server community \S+", re.M),
    "syslog": re.compile(r"^logging host \S+", re.M),
    "heartbeat": re.compile(r"^event manager applet NMAS-HEARTBEAT\b", re.M),
    # Model-driven telemetry: a subscription in the committed configuration.
    # Decides whether the device page folds a device's telemetry panels
    # (the operator, 2026-09-30); never whether series happen to exist now.
    "telemetry": re.compile(r"^telemetry ietf subscription \d+", re.M),
}

#: The words for each, in a sentence "r6 is not monitored by <words>".
WORDS = {"snmp": "SNMP", "syslog": "syslog", "heartbeat": "the syslog heartbeat"}
#: What the configuration lacks, in "its configuration has no <lack>".
LACK = {"snmp": "SNMP community", "syslog": "`logging host`",
        "heartbeat": "NMAS-HEARTBEAT applet"}

PROFILE_ACTION = {"label": "Apply the monitoring profile (planned: NSOT_PLAN P.9, not built "
                           "yet; until it exists nothing configures this from the NMAS)",
                  "reference": "docs/NSOT_PLAN.md"}


def configured(golden_text: str) -> dict:
    """``{integration: bool}`` for one committed golden's text."""
    text = golden_text or ""
    return {name: bool(rx.search(text)) for name, rx in CHECKS.items()}


def expected(get=None) -> dict:
    """``{integration: connector}`` for the integrations this network USES:
    each one's connector is configured in the NMAS."""
    if get is None:
        from modules.settings_schema import get_setting as get
    out = {}
    if str(get("prometheus_url", "") or "").strip():
        out["snmp"] = "Prometheus"
    if str(get("loki_url", "") or "").strip():
        out["syslog"] = "Loki"
        out["heartbeat"] = "Loki"
    return out


def _state_path() -> str:
    import os
    from modules import config

    return os.path.join(config.DATA_DIR, "monitoring_coverage.json")


def _read_state() -> dict:
    import json
    import os

    path = _state_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError) as exc:
        log.error("monitoring coverage: the first-seen record is unreadable (%s); gaps are "
                  "dated from now", exc)
        return {}


def _write_state(state: dict) -> None:
    import json

    from modules.filestore import write_atomic

    try:
        write_atomic(_state_path(), json.dumps(state, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        log.error("monitoring coverage: the first-seen record could not be written: %s", exc)


def _epoch(iso):
    import datetime as _dt

    try:
        return _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def rows(devices=None, golden=None, get=None, now=None, keeper=None, record=True) -> list:
    """One job-health row per device missing an expected integration; none
    when the device is covered or nothing is expected. *devices*: (ref, row)
    pairs, default every list; *golden*: (ref, hostname) -> text, ``""`` for
    no golden, raising when it cannot be read.

    SINCE WHEN (the operator, 2026-09-30: "the condition began at a known
    moment"). For SNMP it is when the target files stopped including the
    device: the keeper's record (`prometheus_targets.last_sync()["excluded"]`),
    the act that ended its monitoring. For syslog and the heartbeat nothing
    acts, so it is when this check first saw the gap, kept in
    `data/monitoring_coverage.json` while the gap stands and dropped when it
    closes; the row says which it is."""
    import time as _time

    from modules import prometheus_targets as P

    now = _time.time() if now is None else now
    want = expected(get)
    if not want:
        return []
    devices = P.inventory() if devices is None else devices
    golden = golden or P.read_golden
    if keeper is None:
        got = P.last_sync()
        keeper = (got.get("excluded") or {}) if isinstance(got, dict) else {}
    state, seen = (_read_state() if record else {}), {}
    out = []
    for ref, dev in devices:
        host = (dev.get("hostname") or "").strip()
        if not host:
            continue
        unit = f"monitoring:{host}"
        # The CHECK's name, never a claim: the operator read the old wording
        # ("r6 is configured for every integration ...") as a second check
        # contradicting the headline. One check, one golden, one definition
        # (`configured()`, which the targets use too).
        what = (f"whether {host}'s committed configuration has what the network's integrations "
                f"need ({', '.join(WORDS[k] for k in sorted(want))})")
        try:
            text = golden(ref, host)
        except Exception as exc:                        # noqa: BLE001
            out.append({"unit": unit, "what": what, "state": "unknown", "device": host,
                        "max_age_minutes": 0,
                        "detail": f"{host}'s committed golden could not be read ({type(exc).__name__}: "
                                  f"{exc}) -- not the same as not configured"})
            continue
        have = configured(text) if text else {k: False for k in CHECKS}
        missing = [k for k in ("snmp", "syslog", "heartbeat") if k in want and not have[k]]
        if not missing:
            continue
        firsts, basis = [], []
        for k in missing:
            key = f"{ref.name}/{host}/{k}"
            if k == "snmp" and (keeper.get(host) or {}).get("since"):
                when = _epoch(keeper[host]["since"])
                basis.append(f"SNMP since the target files stopped including it, "
                             f"{keeper[host]['since']}")
            else:
                when = _epoch(state.get(key)) or now
                basis.append(f"{WORDS[k]} since this check first saw it, "
                             f"{_iso_z(when)}")
            seen[key] = state.get(key) or _iso_z(when)
            firsts.append(when)
        if not text:
            headline = f"{host} is not monitored: it has no committed golden"
            detail = (f"{host} has no committed golden, so nothing shows it configured for "
                      f"{', '.join(WORDS[k] for k in missing)}")
        else:
            headline = f"{host} is not monitored by " + " or ".join(WORDS[k] for k in missing)
            detail = "; ".join(f"{host} is not monitored by {WORDS[k]}: its configuration has no "
                               f"{LACK[k]} (the network uses {want[k]})" for k in missing)
        out.append({"unit": unit, "what": what, "state": "not_monitored", "device": host,
                    "max_age_minutes": 0, "missing": missing, "action": dict(PROFILE_ACTION),
                    "since": min(firsts), "since_basis": "; ".join(basis),
                    "headline": headline, "detail": detail + " (" + "; ".join(basis) + ")"})
    if record and seen != state:
        _write_state(seen)
    return out


def _iso_z(epoch) -> str:
    import time as _time

    return _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(epoch))
