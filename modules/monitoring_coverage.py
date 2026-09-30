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


def rows(devices=None, golden=None, get=None) -> list:
    """One job-health row per device missing an expected integration; none
    when the device is covered or nothing is expected. *devices*: (ref, row)
    pairs, default every list; *golden*: (ref, hostname) -> text, ``""`` for
    no golden, raising when it cannot be read."""
    from modules import prometheus_targets as P

    want = expected(get)
    if not want:
        return []
    devices = P.inventory() if devices is None else devices
    golden = golden or P.read_golden
    out = []
    for ref, dev in devices:
        host = (dev.get("hostname") or "").strip()
        if not host:
            continue
        unit = f"monitoring:{host}"
        what = f"{host} is configured for every integration this network uses ({', '.join(sorted(want))})"
        try:
            text = golden(ref, host)
        except Exception as exc:                        # noqa: BLE001
            out.append({"unit": unit, "what": what, "state": "unknown", "device": host,
                        "max_age_minutes": 0,
                        "detail": f"{host}'s committed golden could not be read ({type(exc).__name__}: "
                                  f"{exc}) -- not the same as not configured"})
            continue
        if not text:
            out.append({"unit": unit, "what": what, "state": "not_monitored", "device": host,
                        "max_age_minutes": 0, "action": dict(PROFILE_ACTION),
                        "headline": f"{host} is not monitored: it has no committed golden",
                        "detail": f"{host} has no committed golden, so nothing shows it configured "
                                  f"for {', '.join(WORDS[k] for k in sorted(want))}"})
            continue
        have = configured(text)
        missing = [k for k in ("snmp", "syslog", "heartbeat") if k in want and not have[k]]
        if not missing:
            continue
        detail = "; ".join(f"{host} is not monitored by {WORDS[k]}: its configuration has no "
                           f"{LACK[k]} (the network uses {want[k]})" for k in missing)
        out.append({"unit": unit, "what": what, "state": "not_monitored", "device": host,
                    "max_age_minutes": 0, "missing": missing, "action": dict(PROFILE_ACTION),
                    "headline": f"{host} is not monitored by "
                                + " or ".join(WORDS[k] for k in missing),
                    "detail": detail})
    return out
