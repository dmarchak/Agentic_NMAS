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

#: The monitoring profile's section that supplies each integration (P.9): the
#: heartbeat is part of the syslog block.
SECTION_OF = {"snmp": "snmp", "syslog": "syslog", "heartbeat": "syslog", "telemetry": "telemetry"}


def profile_view(ref, dev) -> dict:
    """What the list's committed monitoring profile says about one device:
    ``{"profile": bool, "applies": {section}, "excluded": {section: reason},
    "error": str}``. An unreadable profile is an error, never "no profile"."""
    from modules.nsot import hostvars, profile as _p
    from modules.nsot.platform import platform_for_device

    host = (dev.get("hostname") or "").strip()
    try:
        doc = _p.read_committed(ref.repo_dir)
        intent = hostvars.read_committed(ref.repo_dir, host)
    except Exception as exc:                            # noqa: BLE001
        return {"profile": False, "applies": set(), "excluded": {},
                "error": f"{type(exc).__name__}: {exc}"}
    applies = (set(_p.sections_for(doc, platform_for_device(dev),
                                   (dev.get("role") or "").strip(), intent))
               if doc else set())
    return {"profile": bool(doc), "applies": applies, "excluded": _p.excluded(intent or {}),
            "error": ""}


def action_for(ref, host: str, missing: list, view: dict) -> dict:
    """The row's ONE action: apply the profile where it covers what is
    missing, otherwise propose it; an unreadable profile says so."""
    need = sorted({SECTION_OF[k] for k in missing})
    if view.get("error"):
        return {"label": (f"Find why {ref.name}'s monitoring profile cannot be read "
                          f"({view['error']})"), "known": False}
    if set(need) <= set(view.get("applies") or ()):
        return {"label": f"Apply the monitoring profile to {host}", "open": "profile_apply",
                "device": host, "list": ref.name}
    lack = [s for s in need if s not in (view.get("applies") or ())]
    return {"label": (f"Propose {ref.name}'s monitoring profile, then apply it to {host}: "
                      + ("the network has none yet" if not view.get("profile") else
                         f"it has no {', '.join(lack)} section for {host}")),
            "open": "profile_propose", "list": ref.name}


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


def rows(devices=None, golden=None, get=None, now=None, keeper=None, record=True,
         profile=None) -> list:
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
    closes; the row says which it is.

    *profile*: (ref, row) -> `profile_view()`'s answer, default the list's
    committed profile. It decides the row's action (apply, or propose first)
    and drops a section the device's intent excludes with a reason."""
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
        # A section the device's intent EXCLUDES, with its stated reason, is a
        # decision, not a gap: no row for it (MONITORING_PROFILE.md 3).
        view = (profile or profile_view)(ref, dev)
        missing = [k for k in missing if SECTION_OF[k] not in (view.get("excluded") or {})]
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
                    "max_age_minutes": 0, "missing": missing, "action": action_for(ref, host, missing, view),
                    "since": min(firsts), "since_basis": "; ".join(basis),
                    "headline": headline, "detail": detail + " (" + "; ".join(basis) + ")"})
    if record and seen != state:
        _write_state(seen)
    return out


#: Monitoring > Coverage's columns (NSOT_GUI_BRIEF 14.3): each integration's
#: words, the regex that finds it in a committed golden (CHECKS, plus IP SLA),
#: and the profile section that supplies it.
COLUMNS = (("snmp", "SNMP"), ("syslog", "Syslog"), ("heartbeat", "Heartbeat"),
           ("telemetry", "Telemetry"), ("ip_sla", "IP SLA"))
_IP_SLA = re.compile(r"^ip sla \d+", re.M)
_SECTION_OF_COLUMN = {**SECTION_OF, "ip_sla": "ip_sla"}


#: The connector that makes each integration one the network uses.
_CONNECTOR_OF = {"snmp": "Prometheus", "syslog": "Loki", "heartbeat": "Loki",
                 "telemetry": "Telegraf listener (telemetry_receiver)"}
_SECTION_WORDS = {"snmp": "SNMP", "syslog": "syslog", "telemetry": "telemetry",
                  "ip_sla": "IP SLA", "ntp": "NTP", "lldp": "LLDP", "cdp": "CDP"}
_PLATFORM_WORDS = {"cisco_ios": "IOS", "cisco_iosxe": "IOS-XE"}
_IP_SLA_POLICY_WORDS = {"gateway": "probe the default gateway",
                        "peers": "probe the routing peers", "none": "probe nothing"}


def _model_words(text: str, platform: str) -> str:
    """What the device IS, in a person's words: its model from the golden
    (`vios_l2` reads "vIOS"), else its platform."""
    from modules.device_page import model_from_golden

    model, _basis = model_from_golden(text or "")
    if model.lower().startswith("vios"):
        return "vIOS"
    return model or _PLATFORM_WORDS.get(platform, platform or "this platform")


def _not_applicable_words(section: str, doc: dict, text: str, platform: str) -> str:
    """Why a section the profile holds is not for this device, plainly."""
    # Said only where it is TRUE: classic IOS (vIOS here) has no model-driven
    # telemetry. A section scoped away from a platform that has it says the
    # profile's scope instead, never a claim about the platform.
    if section == "telemetry" and platform == "cisco_ios":
        return f"not applicable — {_model_words(text, platform)} doesn't support model-driven telemetry"
    sec = (doc or {}).get("sections", {}).get(section) or {}
    scope = [_PLATFORM_WORDS.get(p, p) for p in sec.get("platforms") or []] + \
        [f"the {r} role" for r in sec.get("roles") or []]
    return (f"not applicable — the profile's {_SECTION_WORDS.get(section, section)} section is "
            f"for {' and '.join(scope) or 'other devices'}")


def _ip_sla_words(doc: dict) -> str:
    """IP SLA unconfigured, in the words of the agreed policy (P.9 decision 5):
    a probe measures ONE path, so its target is a per-device choice; the
    profile's policy decides how targets are suggested."""
    sec = ((doc or {}).get("sections") or {}).get("ip_sla") or {}
    policy = sec.get("policy")
    if not policy:
        return ("no probes configured — IP SLA targets are chosen per device; set a policy "
                "on the IP SLA page to add them")
    if policy == "none":
        return "no probes — the profile's IP SLA policy is to probe nothing"
    return (f"no probes yet — the profile's policy is to {_IP_SLA_POLICY_WORDS[policy]}; "
            "review the suggested probes on the IP SLA page")


def _expected_columns(get) -> dict:
    """``{column: connector}`` for what this network USES: SNMP and syslog as
    `expected()` decides, telemetry when Telegraf's listener is set. IP SLA is
    a per-device policy (MONITORING_PROFILE.md section 9, decision 5), never
    expected of every device."""
    out = dict(expected(get))
    if str(get("telemetry_receiver", "") or "").strip():
        out["telemetry"] = "Telegraf"
    return out


def _reporting(key, host, report, heartbeat_configured) -> dict:
    """A CONFIGURED cell, judged by the not-reporting reader's stored arrivals: ``ok`` with
    the reader's word beside "configured" (reporting, unproven, or unknown, said), or
    ``not_reporting`` naming for how long and the device tab where its cause is looked for
    (artboard A: never a redeploy)."""
    from modules.readers import coverage_reporting as CR

    value, _at, why = report
    if value is None:
        got = {"state": "unjudged", "words": f"whether it reports is unknown: {why}"}
    else:
        got = CR.judge(key, host, value, heartbeat_configured=heartbeat_configured)
    if got["state"] == "not_reporting":
        return {"state": "not_reporting", "words": f"not reporting — {got['words']}",
                "where": got["where"], "reporting": got}
    return {"state": "ok", "words": "configured", "reporting": got}


def fleet(ref, devices=None, golden=None, get=None, profile=None, report=None) -> dict:
    """Monitoring > Coverage for one list: every device, each integration it is
    CONFIGURED for from its committed golden, and what the list's monitoring
    profile would supply where it is not (the operator's design, 14.3).

    A cell's state is decided HERE, never in the browser: ``ok`` (configured),
    ``gap`` (expected and missing, and the profile supplies it), ``gap_open``
    (expected and missing, and the profile does not supply it, saying why),
    ``excluded`` (the device's intent excludes it, with the reason),
    ``unused`` (missing, and the network does not use it), ``unknown`` (the
    golden could not be read: never "not configured"). A device is offered for
    "Apply monitoring profile" when the profile applies to it; it starts ticked
    when the profile supplies one of its gaps; one that cannot be offered says
    why beside its box."""
    from modules import prometheus_targets as P
    from modules.nsot import hostvars
    from modules.nsot import profile as _p
    from modules.nsot import repo as R
    from modules.nsot.platform import platform_for_device

    if get is None:
        from modules.settings_schema import get_setting as get
    golden = golden or P.read_golden
    want = _expected_columns(get)
    if report is None:
        # ONE stored read for the whole grid (enterprise scale), never a query per device.
        from modules.device_page import _cached
        from modules.readers.coverage_reporting import NAME
        report = _cached(NAME)
    if devices is None:
        from modules.device import load_saved_devices
        devices = [(ref, d) for d in load_saved_devices(ref.csv_path)]
    try:
        doc = _p.read_committed(ref.repo_dir)
        prof = {"committed": bool(doc), "error": "",
                "sections": sorted((doc or {}).get("sections") or {})}
    except Exception as exc:                            # noqa: BLE001
        doc, prof = None, {"committed": False, "error": f"{type(exc).__name__}: {exc}",
                           "sections": []}
    if prof["committed"]:
        rc, out, _e = R.git(ref.repo_dir, "log", "-1", "--format=%h%x09%cI", "--", _p.PROFILE_REL)
        sha, _, at = (out.strip().partition("\t") if rc == 0 else ("", "", ""))
        prof.update(commit=sha, committed_at=at,
                    sources={k: ((doc["sections"].get(k) or {}).get("source") or "")
                             for k in prof["sections"]})
    rows, covered = [], 0
    for _ref, dev in devices:
        host = (dev.get("hostname") or "").strip()
        if not host:
            continue
        platform = platform_for_device(dev) or ""
        role = (dev.get("role") or "").strip()
        row = {"host": host, "platform": platform, "role": role, "cells": {}, "gaps": [],
               "supplies": [], "not_reporting": [], "selectable": False, "checked": False,
               "why_not": ""}
        try:
            text = golden(ref, host)
            row["golden"] = "ok" if text else "none"
        except Exception as exc:                        # noqa: BLE001
            text, row["golden"] = None, "unreadable"
            row["error"] = f"{type(exc).__name__}: {exc}"
        try:
            intent = hostvars.read_committed(ref.repo_dir, host)
        except Exception:                               # noqa: BLE001
            intent = None
        if profile is not None:
            view = profile(ref, dev)
        else:
            view = {"applies": set(_p.sections_for(doc, platform, role, intent)) if doc else set(),
                    "excluded": _p.excluded(intent or {}), "error": prof["error"]}
        have = configured(text) if text else {}
        have["ip_sla"] = bool(text and _IP_SLA.search(text))
        for key, words in COLUMNS:
            section = _SECTION_OF_COLUMN[key]
            # Every cell in a person's words, saying WHY (the operator,
            # 2026-10-01: "none (a policy per device)" explained nothing).
            if text is None:
                cell = {"state": "unknown", "words": "unknown — its golden could not be read"}
            elif have.get(key):
                cell = _reporting(key, host, report, bool(have.get("heartbeat")))
            elif section in (view.get("excluded") or {}):
                cell = {"state": "excluded",
                        "words": f"excluded — {view['excluded'][section]}"}
            elif key == "ip_sla":
                cell = {"state": "unused", "words": _ip_sla_words(doc)}
            elif key not in want:
                cell = {"state": "unused",
                        "words": f"not used — this network has no {_CONNECTOR_OF[key]} connector"}
            elif section in (view.get("applies") or ()):
                cell = {"state": "gap", "words": "missing — the profile supplies it"}
                row["supplies"].append(key)
            elif section in prof["sections"]:
                # The profile SCOPES the section away from this device (its
                # platform or role): a decision, never a gap. Telemetry on a
                # vIOS switch is the measured case: the platform cannot stream.
                cell = {"state": "not_applicable",
                        "words": _not_applicable_words(section, doc, text, platform)}
            else:
                cell = {"state": "gap_open", "words": (
                    "missing — no monitoring profile yet" if not doc else
                    f"missing — the profile has no {_SECTION_WORDS.get(section, section)} section")}
            if cell["state"] == "not_reporting":
                row["not_reporting"].append(key)
            if cell["state"] in ("gap", "gap_open"):
                row["gaps"].append(key)
            row["cells"][key] = cell
        if text is not None and not row["gaps"]:
            covered += 1
        if prof["error"]:
            row["why_not"] = f"the profile cannot be read ({prof['error']})"
        elif not doc:
            row["why_not"] = "the network has no monitoring profile yet"
        elif intent is None:
            row["why_not"] = f"{host} has no committed intent"
        elif not view.get("applies"):
            row["why_not"] = "no section of the profile applies to it (platform or role)"
        elif not row["supplies"]:
            # OFFERED ONLY FOR A GAP THE PROFILE SUPPLIES (C295, the operator,
            # 2026-10-01): s1, s2, s4 and r6 were tickable for IP SLA, and the
            # apply could send nothing, since IP SLA was not in the profile.
            row["why_not"] = _nothing_to_apply(row, doc)
        else:
            row["selectable"] = True
            row["checked"] = True
        rows.append(row)
    return {"list": ref.name, "columns": [{"key": k, "words": w, "connector": want.get(k, "")}
                                          for k, w in COLUMNS],
            "profile": prof, "devices": rows, "covered": covered, "total": len(rows),
            # Configured and its data not arriving, per cell and per device (artboard A's
            # head: "3 not reporting on 2"); and, once, why reporting could not be judged.
            "not_reporting": sum(len(r["not_reporting"]) for r in rows),
            "not_reporting_devices": sum(1 for r in rows if r["not_reporting"]),
            "reporting_unknown": next((c["reporting"]["words"] for r in rows
                                       for c in r["cells"].values()
                                       if (c.get("reporting") or {}).get("state") == "unjudged"),
                                      ""),
            # The devices running no IP SLA probe, each a link to the IP SLA
            # page, where the policy suggests probes (P.9 d4).
            "ip_sla_missing": [r["host"] for r in rows
                               if (r["cells"].get("ip_sla") or {}).get("state") == "unused"]}


def _nothing_to_apply(row: dict, doc: dict) -> str:
    """Why a device the profile applies to has nothing for Apply to send:
    what it is missing that the profile does not supply, each with why, or
    that it already holds everything the profile supplies."""
    policy = ((((doc or {}).get("sections") or {}).get("ip_sla") or {}).get("policy"))
    missing = []
    for key, words in COLUMNS:
        cell = row["cells"].get(key) or {}
        if key == "ip_sla" and cell.get("state") == "unused" and not policy:
            missing.append("IP SLA isn't in the profile yet")
        elif key == "ip_sla" and cell.get("state") == "unused" and policy != "none":
            # A policy suggests probes; they are reviewed and sent from the IP
            # SLA page, never by the profile's Apply (P.9 d4).
            missing.append("IP SLA: its probes are suggested and sent from the IP SLA page")
        elif cell.get("state") == "gap_open":
            missing.append(f"{words}: {cell['words'].split(' — ', 1)[-1]}")
    if missing:
        return "nothing for Apply to send: " + "; ".join(missing)
    return "nothing for Apply to send: it already has everything the profile supplies"


def _iso_z(epoch) -> str:
    import time as _time

    return _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(epoch))
