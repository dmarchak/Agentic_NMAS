"""PROPOSE THE NETWORK'S MONITORING PROFILE (NSOT_PLAN P.9;
docs/MONITORING_PROFILE.md 2): a profile DERIVED FROM THE CONNECTORS the
network uses (since 2026-09-30, the operator: one built from what the fleet
already agrees on is circular, and a network the tool has never seen has
nothing to agree on), cross-checked against the fleet's COMMITTED intent,
previewed, confirmed by hash and committed as the verified person. It writes
nothing to any device: a device receives the profile when a person applies it
(`profile_apply`, the scoped deploy).

The rule, stated once:

- each section's value comes from its connector (`connector_value()`): syslog
  and the heartbeat from the syslog settings, SNMP from snmp_exporter's auth
  module and the trap host, NTP from `ntp_servers`, telemetry from Telegraf's
  listener, LLDP from the lldp scrape. The fleet is then the CROSS-CHECK: a
  device holding another version is named with what it gains and what it
  keeps, and one whose stored secret differs is named (never the value);
- a section whose connector is not configured falls back to what the fleet
  agrees on, as below, and says so in its basis; CDP has no connector;
- a section is proposed only where its connector is configured (SNMP needs
  Prometheus, syslog needs Loki);
- a section's data is the value EVERY device holding it agrees on. Two
  different values are never reconciled by the tool: the section is not
  proposed, and each variant is named with its devices, because picking one
  would make the others overrides nobody chose;
- a section applies only to the platforms some device already holds it on,
  when a device of another platform lacks it (telemetry: IOS-XE only);
- a secret the section references is one value per network (decision 2): the
  devices' own stored values are compared IN MEMORY and never shown, and a
  disagreement, or a device with none stored, refuses that section by name;
- `ip_sla` is a POLICY a person chooses, never derived, and never proposed.

Sections already in the committed profile and not derived here are kept as
they are; a derived section replaces the committed one.
"""

import hashlib
import json
import logging
import os

log = logging.getLogger(__name__)

#: Each derivable section: where it lives in a device's intent, and the
#: connector setting it needs ("" for none yet).
DERIVED = {
    "snmp": ("prometheus", "prometheus_url"),
    "syslog": ("loki", "loki_url"),
    "ntp": ("fleet", ""),
    "telemetry": ("fleet", ""),
    "lldp": ("fleet", ""),
    "cdp": ("fleet", ""),
}


class ProposalRefused(ValueError):
    """The proposal cannot be committed; the message says why."""


def section_value(name: str, intent: dict):
    """A section's data as the profile would hold it, from one device's intent;
    ``None`` when the device holds none (an empty skeleton is none)."""
    from modules.nsot.profile import _empty

    intent = intent or {}
    if name == "snmp":
        from modules.nsot.profile import shared_only
        v = intent.get("snmp")
        if isinstance(v, dict) and any(not _empty(x) for x in v.values()):
            # Only SHARED fields agree or differ: a device's location and
            # contact are its own (the operator, 2026-09-30), never compared,
            # never in the profile, never overwritten.
            v = dict(v, settings=shared_only("snmp.settings", v.get("settings") or []))
            if any(not _empty(x) for x in v.values()):
                return {"snmp": v}
    elif name == "syslog":
        v = (intent.get("logging") or {}).get("syslog")
        if isinstance(v, dict) and v:
            return {"logging": {"syslog": v}}
    elif name == "ntp":
        v = intent.get("ntp_servers")
        if v:
            return {"ntp_servers": v}
    elif name == "telemetry":
        v = intent.get("telemetry")
        if v:
            return {"telemetry": v}
    elif name in FLAG_SECTIONS:
        # The parsers store these as boolean FLAGS (`_h_flag`: `flags: {"lldp
        # run": True}`, `no lldp run` as False). The first version read
        # `intent["lldp"]`, a key no parser writes, taken from the design
        # document, and reported "no device's committed intent holds it" for
        # eight devices that did (the operator, 2026-09-30).
        flags = intent.get("flags") or {}
        flag = FLAG_SECTIONS[name]
        if flag in flags:
            return {"flags": {flag: bool(flags[flag])}}
    return None


#: The sections the parsers store as boolean flags, by the flag's key.
FLAG_SECTIONS = {"lldp": "lldp run", "cdp": "cdp run"}

DEFAULTS_FILE = os.path.join(os.path.dirname(__file__), "platform_defaults.json")


def platform_default(dialect: str, flag: str, path: str = None) -> dict:
    """``{"state": "on"|"off"|"not_measured", ...}``: whether *flag* is ON on
    *dialect* when its line is ABSENT, as MEASURED (platform_defaults.json).
    An unreadable record is not measured, never on or off."""
    path = path or DEFAULTS_FILE                   # read at call time, not definition
    try:
        with open(path, encoding="utf-8") as fh:
            got = ((json.load(fh).get("by_dialect") or {}).get(dialect) or {}).get(flag)
    except (OSError, ValueError) as exc:
        return {"state": "not_measured", "why": f"the defaults record could not be read: {exc}"}
    return dict(got) if isinstance(got, dict) and got.get("state") else {"state": "not_measured"}


# ---------------------------------------------------------------------------
# The connectors: the PRIMARY source (the operator, 2026-09-30)
# ---------------------------------------------------------------------------
# "Configure the monitoring stack once and the profile writes itself." A
# proposal built from what the fleet already agrees on is circular: a network
# the tool has never seen, or one nobody configured consistently, has nothing
# to agree on. So each section is derived from the connector that consumes it,
# and the fleet is the CROSS-CHECK that names a device configured differently.

#: The fleet's measured subscriptions (r1 to r4's committed intent, 2026-09-30):
#: CPU and interface statistics, the device dashboard's telemetry panels.
TELEMETRY_SUBSCRIPTIONS = (("101", "/process-cpu-ios-xe-oper:cpu-usage/cpu-utilization"),
                           ("102", "/interfaces-ios-xe-oper:interfaces/interface/statistics"))
#: Model-driven telemetry runs on IOS-XE. No switch (vIOS) holds a subscription
#: in its committed intent; whether the image would accept one is not measured,
#: so the section is never applied there.
TELEMETRY_PLATFORMS = ["cisco_iosxe"]
#: What the SNMP consumers need beyond the community and the trap host: link
#: traps for the trap receiver's alerts, and stable ifIndex for the exporter's
#: series across a reload.
SNMP_SETTINGS = ("enable traps snmp linkdown linkup", "snmp ifmib ifindex persist")
COMMUNITY_REF = "snmp_community_ro"


def exporter_community(path: str, auth: str) -> tuple:
    """``(community, why)``: the community snmp_exporter's *auth* module polls
    with, read from its config IN MEMORY. *why* names what was missing; the
    value is never returned in it."""
    import re

    import yaml

    if not path:
        return "", "snmp_exporter_config is not configured"
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return "", f"{path} could not be read ({exc.strerror})"
    m = re.search(r"^auths:[ \t]*\n((?:[ \t]+.*\n|[ \t]*\n)*)", text, re.M)
    if not m:
        return "", f"{path} has no auths section"
    try:
        auths = (yaml.safe_load("auths:\n" + m.group(1)) or {}).get("auths") or {}
    except yaml.YAMLError as exc:
        return "", f"{path}'s auths section does not parse ({type(exc).__name__})"
    entry = auths.get(auth)
    if not isinstance(entry, dict):
        return "", f"{path} has no auth module {auth!r} (it has: {', '.join(sorted(auths))})"
    if str(entry.get("version")) not in ("1", "2"):
        return "", (f"the auth module {auth!r} is SNMP version {entry.get('version')}: the "
                    "profile's SNMP section is a community, v1 or v2c")
    community = str(entry.get("community") or "")
    if not community:
        return "", f"the auth module {auth!r} names no community"
    return community, ""


def connector_value(name: str, get) -> dict:
    """What the CONNECTOR says *name* must hold. ``{"value", "basis",
    "secrets", "platforms"}``; ``{"why"}`` when the connector is not
    configured (the fleet decides, said so); ``{}`` for a section no
    connector consumes (CDP)."""
    def s(key):
        v = get(key, "")
        return v.strip() if isinstance(v, str) else v

    if name == "syslog":
        from modules.nsot import hostvars

        host = s("syslog_host")
        if not host:
            return {"why": "syslog_host is not configured"}
        block = {"trap": s("syslog_trap_level") or "notifications",
                 "origin_id": s("syslog_origin_id") or "hostname",
                 "source_interface": s("syslog_source_interface") or "Loopback0",
                 "hosts": [host], "heartbeat": int(s("syslog_heartbeat_seconds") or 0)}
        problems = hostvars.syslog_block_problems({"logging": {"syslog": block}})
        if problems:
            return {"why": "the syslog settings do not make a whole block: " + "; ".join(problems)}
        return {"value": {"logging": {"syslog": block}},
                "basis": ("the syslog settings: the receiver feeding Loki at syslog_host, and the "
                          "heartbeat the alert rules are generated from")}
    if name == "ntp":
        servers = [str(x).strip() for x in (s("ntp_servers") or []) if str(x).strip()] \
            if isinstance(s("ntp_servers"), list) else []
        if not servers:
            return {"why": "ntp_servers is not configured"}
        return {"value": {"ntp_servers": servers}, "basis": "the ntp_servers setting"}
    if name == "telemetry":
        recv = s("telemetry_receiver")
        if not recv or ":" not in recv:
            return {"why": "telemetry_receiver (Telegraf's listener) is not configured"}
        addr, port = recv.rsplit(":", 1)
        subs = [{"subscription": sid,
                 "settings": ["encoding encode-kvgpb", f"filter xpath {xpath}", "stream yang-push",
                              "update-policy periodic 1000",
                              f"receiver ip address {addr} {port} protocol grpc-tcp"]}
                for sid, xpath in TELEMETRY_SUBSCRIPTIONS]
        return {"value": {"telemetry": subs}, "platforms": list(TELEMETRY_PLATFORMS),
                "basis": f"Telegraf's listener at {recv} (telemetry_receiver)"}
    if name == "snmp":
        auth = s("snmp_exporter_auth") or "public_v2"
        community, why = exporter_community(s("snmp_exporter_config"), auth)
        if not community:
            return {"why": why}
        trap = s("snmp_trap_host")
        value = {"communities": [{"access": "RO", "ref": COMMUNITY_REF}],
                 "hosts": ([{"address": trap, "options": f"version 2c __secret__:{COMMUNITY_REF}"}]
                           if trap else []),
                 "settings": ([f"trap-source {s('syslog_source_interface') or 'Loopback0'}"]
                              if trap else []) + list(SNMP_SETTINGS)}
        return {"value": {"snmp": value}, "secrets": {COMMUNITY_REF: community},
                "basis": (f"snmp_exporter's {auth!r} module (the community it polls with, read "
                          "from its config and never shown)"
                          + (f", and traps to {trap} (snmp_trap_host)" if trap
                             else "; snmp_trap_host is not configured, so no trap host"))}
    if name == "lldp":
        if not s("prometheus_url"):
            return {"why": "nothing scrapes LLDP: prometheus_url is not configured"}
        return {"value": {"flags": {"lldp run": True}},
                "basis": "the lldp scrape and the topology read LLDP-MIB"}
    return {}


def _canon(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


def _comparable(v, path=""):
    """*v* with every KEYED list sorted by key: the same entries in another
    order are the same version."""
    from modules.nsot.profile import KEYED_LISTS
    if isinstance(v, dict):
        return {k: _comparable(x, f"{path}.{k}" if path else k) for k, x in v.items()}
    if path in KEYED_LISTS and isinstance(v, list):
        return sorted(v, key=lambda e: str(KEYED_LISTS[path](e)))
    return v


def version_id(value) -> str:
    """A version's id: its comparable form, hashed. What a person chooses by."""
    return hashlib.sha256(_canon(_comparable(value)).encode()).hexdigest()[:12]


def _items(value, path=""):
    """{(path, key): entry} for every leaf of a section's value, a keyed
    list's entries one by one."""
    from modules.nsot.profile import KEYED_LISTS
    out = {}
    if isinstance(value, dict):
        for k, x in value.items():
            out.update(_items(x, f"{path}.{k}" if path else k))
    elif path in KEYED_LISTS and isinstance(value, list):
        for e in value:
            out[(path, str(KEYED_LISTS[path](e)))] = e
    else:
        out[(path, "")] = value
    return out


def _text(path, entry) -> str:
    return entry if isinstance(entry, str) else f"{path}: {json.dumps(entry, sort_keys=True)}"


def changes_for(chosen, theirs) -> dict:
    """What a device holding *theirs* sees when *chosen* is the profile:
    ``{"gains": [...], "keeps": [...]}``. It GAINS what it lacks; it KEEPS its
    own where it differs (its value wins: an override, said by name)."""
    mine, other = _items(chosen), _items(theirs or {})
    gains = [_text(p, e) for (p, k), e in mine.items() if (p, k) not in other]
    keeps = [_text(p, other[(p, k)]) for (p, k), e in mine.items()
             if (p, k) in other and other[(p, k)] != e]
    return {"gains": gains, "keeps": keeps}


def _fleet(list_name: str) -> tuple:
    """([(hostname, platform, role, intent)], [skipped {device, why}])."""
    from modules.nsot import hostvars
    from modules.nsot.platform import platform_for_device
    from modules.nsot.restore import _devices_of

    repo = _repo(list_name)
    out, skipped = [], []
    for dev in _devices_of(list_name):
        host = (dev.get("hostname") or "").strip()
        if not host:
            continue
        intent = hostvars.read_committed(repo, host)
        if intent is None or hostvars.is_bootstrap_only(intent):
            skipped.append({"device": host, "why": "no full committed intent to read"})
            continue
        out.append((host, platform_for_device(dev), (dev.get("role") or "").strip(), intent))
    return out, skipped


def _repo(list_name: str) -> str:
    from modules.nsot import listref

    return listref.resolve(list_name).repo_dir


def _secret_agreement(list_name: str, refs: set, holders: list) -> dict:
    """``{ref: {"agreed": bool, "value": str (in memory only), "why": str}}``."""
    from modules.credentials import get_template_secret, template_secret_key

    out = {}
    for ref in sorted(refs):
        values = {h: get_template_secret(template_secret_key(list_name, h, ref)) for h in holders}
        missing = sorted(h for h, v in values.items() if not v)
        distinct = {v for v in values.values() if v}
        if missing:
            out[ref] = {"agreed": False, "value": "",
                        "why": f"no stored value for {ref} on {', '.join(missing)}"}
        elif len(distinct) != 1:
            groups = {}
            for h, v in values.items():
                groups.setdefault(v, []).append(h)
            out[ref] = {"agreed": False, "value": "",
                        "why": (f"the devices hold {len(distinct)} different values for {ref}: "
                                + "; ".join(", ".join(sorted(g)) for g in groups.values())
                                + " (values never shown)")}
        else:
            out[ref] = {"agreed": True, "value": distinct.pop(),
                        "why": f"all {len(holders)} device(s) hold the same value"}
    return out


def _secret_differs(list_name: str, refs: set, values: dict, hosts: list) -> list:
    """The devices whose OWN stored value for a ref differs from the
    connector's: ``[{"device", "ref"}]``, names only, compared in memory."""
    from modules.credentials import get_template_secret, template_secret_key

    out = []
    for h in sorted(set(hosts)):
        for ref in sorted(refs):
            own = get_template_secret(template_secret_key(list_name, h, ref))
            if own and own != values.get(ref):
                out.append({"device": h, "ref": ref})
    return out


def propose(list_name: str, get=None, choose: dict = None) -> dict:
    """The proposal, computed from what is committed now. Carries secret
    VALUES in `secrets` for `apply()` only: `public()` strips them.

    *choose* is ``{section: version id}``: where the devices hold different
    versions of a section's SHARED fields, the tool never picks one, and a
    PERSON may (the operator, 2026-09-30). The chosen version is proposed; a
    device holding another gains what it lacks and keeps its own where it
    differs, each named, and the choice is in the hash and the commit."""
    choose = dict(choose or {})
    from modules.nsot import profile as _p

    if get is None:
        from modules.settings_schema import get_setting as get
    repo = _repo(list_name)
    current = _p.read_committed(repo)             # raises for a broken profile
    fleet, skipped = _fleet(list_name)
    doc = {"version": _p.VERSION,
           "sections": {k: v for k, v in ((current or {}).get("sections") or {}).items()
                        if k not in DERIVED}}
    sections, secrets = [], {}
    for name, (source, setting) in DERIVED.items():
        row = {"section": name, "source": source, "setting": setting, "proposed": False}
        sections.append(row)
        if setting and not (get(setting, "") or "").strip():
            row["why"] = f"{setting} is not configured, so the network does not use it"
            if name in ((current or {}).get("sections") or {}):
                doc["sections"][name] = current["sections"][name]
                row["why"] += "; the committed section is kept as it is"
            continue
        held = [(h, plat, v) for h, plat, _r, intent in fleet
                for v in [section_value(name, intent)] if v is not None]
        cv = connector_value(name, get)
        if cv.get("value") is not None:
            # THE CONNECTOR DECIDES (the operator, 2026-09-30); the fleet is the
            # CROSS-CHECK. A device holding another version is named with what
            # it gains and what it keeps (its own value wins), never silently
            # overwritten, and never makes the section unproposable.
            row.update({"basis": cv["basis"], "connector": True})
            target_id = version_id(cv["value"])
            others = {h: v for h, _p, v in held if version_id(v) != target_id}
            if others:
                row["differs"] = {h: changes_for(cv["value"], v)
                                  for h, v in sorted(others.items())}
                row["changes"] = row["differs"]
            only = {"value": cv["value"],
                    "devices": [h for h, _p, v in held if version_id(v) == target_id]}
            plats = sorted({plat for _h, plat, _r, _i in fleet})
            applies = list(cv.get("platforms") or plats)
            if name in FLAG_SECTIONS:
                dead = {p: platform_default(p, FLAG_SECTIONS[name]) for p in applies}
                dead = {p: d for p, d in dead.items() if d.get("runs_alone") is False}
                if dead:
                    row["runs_nothing"] = {p: d.get("evidence", "measured") for p, d in dead.items()}
                    applies = [p for p in applies if p not in dead]
                    if not applies:
                        row["why"] = (f"`{FLAG_SECTIONS[name]}` alone enables nothing on "
                                      + ", ".join(sorted(dead)))
                        continue
            holder_plats = applies
            # A connector's platforms are a CAPABILITY (telemetry: IOS-XE), so
            # the section carries them even where the fleet is all one platform
            # today: a switch onboarded later must not inherit it.
            restrict = bool(cv.get("platforms")) or sorted(applies) != plats
        else:
            if not held:
                row["why"] = ("no device's committed intent holds it"
                              + (f", and {cv['why']}" if cv.get("why") else ""))
                continue
            if cv.get("why"):
                row["basis"] = f"the fleet's committed intent, because {cv['why']}"
            variants = {}
            for h, plat, v in held:
                variants.setdefault(version_id(v), {"value": v, "devices": []})["devices"].append(h)
            if len(variants) > 1:
                row["variants"] = [{"id": vid, "devices": sorted(x["devices"]), "value": x["value"]}
                                   for vid, x in sorted(variants.items(),
                                                        key=lambda kv: (-len(kv[1]["devices"]), kv[0]))]
                picked = choose.get(name)
                if picked not in variants:
                    row["why"] = (f"the devices hold {len(variants)} different versions of its shared "
                                  "fields; the tool never picks one: choose a version, or reconcile "
                                  "their intent first"
                                  + (f" (or configure the connector: {cv['why']})" if cv.get("why")
                                     else ""))
                    row["choosable"] = True
                    continue
                only = variants[picked]
                row["chosen"] = picked
                by_host = {h: v for h, _p, v in held}
                row["changes"] = {h: changes_for(only["value"], by_host[h])
                                  for h in sorted(by_host) if h not in only["devices"]}
            else:
                (only,) = variants.values()
            if name in FLAG_SECTIONS:
                # A line MEASURED to enable nothing alone on a platform is never
                # proposed there (the operator, 2026-09-30: on IOS-XE `cdp run`
                # enables no interface, so "r6 gains CDP" claimed a feature that
                # would not run). A preview never claims what will not happen.
                dead = {plat: platform_default(plat, FLAG_SECTIONS[name])
                        for _h, plat, _v in held}
                dead = {p: d for p, d in dead.items() if d.get("runs_alone") is False}
                if dead:
                    held = [x for x in held if x[1] not in dead]
                    only = {"value": only["value"], "devices": [h for h, _p, _v in held]}
                    row["runs_nothing"] = {p: d.get("evidence", "measured") for p, d in dead.items()}
                    if not held:
                        row["why"] = (f"`{FLAG_SECTIONS[name]}` alone enables nothing on "
                                      + ", ".join(sorted(dead)) + " ("
                                      + "; ".join(d.get("evidence", "measured")
                                                  for d in dead.values())
                                      + "), so the profile would claim a feature that does not run")
                        continue
            holder_plats = sorted({plat for _h, plat, _v in held})
            restrict = None
        holders = sorted(only["devices"])
        # A device holding ANOTHER version is not lacking: it is in `changes`.
        lacking = [(h, plat) for h, plat, _r, intent in fleet if h not in holders
                   and h not in (row.get("changes") or {})]
        section = {"source": "connector" if row.get("connector") else source,
                   "data": only["value"]}
        if restrict or (restrict is None
                        and any(plat not in holder_plats for _h, plat in lacking)):
            section["platforms"] = holder_plats
        if name in FLAG_SECTIONS:
            # An ABSENT line may be "on by default" (the operator: CDP on vIOS).
            # Each platform a non-holder is on says what its absence means, as
            # MEASURED; the section still applies only where devices write the
            # line, so a default line is never pushed where it is never printed.
            flag = FLAG_SECTIONS[name]
            defaults = {}
            for h, plat in lacking:
                d = defaults.setdefault(plat, dict(platform_default(plat, flag), devices=[]))
                d["devices"].append(h)
            row["defaults"] = defaults
            lacking = [(h, plat) for h, plat in lacking
                       if not (defaults[plat]["state"] == "on"
                               and only["value"]["flags"][flag] is True)]
        refs = _p.secret_refs(only["value"])
        if refs and row.get("connector"):
            # The connector's value IS the network's; a device whose own stored
            # value differs is named (names only), because the collector polls
            # with the connector's and that device would not answer it.
            got = cv.get("secrets") or {}
            missing = sorted(r for r in refs if not got.get(r))
            if missing:
                row["why"] = "the connector supplies no value for " + ", ".join(missing)
                continue
            secrets.update({r: got[r] for r in refs})
            row["secrets"] = {r: "from the connector, never shown" for r in refs}
            row["secret_differs"] = _secret_differs(list_name, refs, got,
                                                    [h for h, _p, _v in held] + sorted(others))
        elif refs:
            agree = _secret_agreement(list_name, refs, holders)
            bad = [a["why"] for a in agree.values() if not a["agreed"]]
            if bad:
                row["why"] = "its secret is not one value across the fleet: " + "; ".join(bad)
                continue
            secrets.update({ref: a["value"] for ref, a in agree.items()})
            row["secrets"] = {ref: a["why"] for ref, a in agree.items()}
        doc["sections"][name] = section
        row.update({"proposed": True, "holders": holders,
                    "platforms": section.get("platforms") or [],
                    "inherit": sorted(h for h, plat in lacking
                                      if not section.get("platforms") or plat in section["platforms"])})
    effect = []
    for host, plat, role, intent in fleet:
        before = _p.effective(intent, current, plat, role) if current else intent
        after = _p.effective(intent, doc, plat, role)
        if _canon(before) != _canon(after):
            # A section it INHERITS: one that newly applies AND that its own
            # intent does not hold (its own value wins, so a section it holds
            # alike is not gained; measured, the first version said r6 "gains
            # NTP" while r6 held the same NTP itself).
            gains = sorted(s for s in _p.sections_for(doc, plat, role, intent)
                           if s not in (_p.sections_for(current, plat, role, intent)
                                        if current else {})
                           and (s not in DERIVED or section_value(s, intent) is None))
            effect.append({"device": host, "inherits": gains})
    changed = _canon(doc) != _canon(current or {})
    head = _profile_blob(repo)
    digest = hashlib.sha256(_canon({"doc": doc, "head": head, "choose": sorted(choose.items()),
                                    "secrets": sorted(secrets)}).encode()).hexdigest()[:16]
    return {"list": list_name, "doc": doc, "current": current, "changed": changed,
            "sections": sections, "effect": effect, "skipped": skipped,
            "devices_read": len(fleet), "profile_blob": head, "hash": digest,
            "secrets": secrets}


def public(proposal: dict) -> dict:
    """The proposal with no secret value: what may leave the server."""
    return {k: v for k, v in proposal.items() if k != "secrets"}


def _profile_blob(repo: str) -> str:
    from modules.nsot import profile as _p
    from modules.nsot import repo as R

    rc, out, _err = R.git_raw(repo, "rev-parse", "-q", "--verify", f"HEAD:{_p.PROFILE_REL}")
    return out.strip() if rc == 0 else ""


def document_diff(proposal: dict) -> list:
    """The profile document to commit, against what is committed now, as
    unified diff lines (no secret: the document holds references)."""
    import difflib

    import yaml

    def _text(d):
        return yaml.safe_dump(d, sort_keys=False, default_flow_style=False).splitlines() if d else []

    return list(difflib.unified_diff(_text(proposal.get("current")), _text(proposal["doc"]),
                                     "committed", "proposed", lineterm="", n=2))


def apply(list_name: str, confirmed_hash: str, actor: str, choose: dict = None) -> dict:
    """Recompute (with the person's *choose*, as previewed), refuse a proposal
    that moved, store each agreed secret under the network's key, and commit
    the document as *actor*, naming every chosen version."""
    from modules.nsot import profile as _p

    now = propose(list_name, choose=choose)
    if not now["changed"]:
        return {"outcome": "nothing", "proposal": public(now),
                "reason": "the proposal equals the committed profile"}
    if now["hash"] != confirmed_hash:
        return {"outcome": "moved", "proposal": public(now),
                "reason": (f"the proposal changed since the preview ({confirmed_hash} -> "
                           f"{now['hash']}): intent, the stored values or the committed profile "
                           "moved. Nothing was committed")}
    stored = []
    for ref, value in now["secrets"].items():
        from modules.credentials import get_template_secret, profile_secret_key

        if get_template_secret(profile_secret_key(list_name, ref)) != value:
            _p.set_secret(list_name, ref, value)
            stored.append(ref)
    proposed = [s["section"] for s in now["sections"] if s["proposed"]]
    chosen = [f"{s['section']} as held by {', '.join(next(v['devices'] for v in s['variants'] if v['id'] == s['chosen']))}"
              for s in now["sections"] if s.get("chosen")]
    by_connector = [s["section"] for s in now["sections"] if s["proposed"] and s.get("connector")]
    by_fleet = [s for s in proposed if s not in by_connector]
    out = _p.commit_profile(list_name, now["doc"], actor,
                            "proposed: "
                            + "; ".join(x for x in (
                                f"from the connectors ({', '.join(by_connector)})" if by_connector else "",
                                f"from the fleet's committed intent ({', '.join(by_fleet)})"
                                if by_fleet else "") if x)
                            + (f"; chosen: {'; '.join(chosen)}" if chosen else ""))
    if not out.get("ok"):
        return {"outcome": "failed", "proposal": public(now), "secrets_stored": stored,
                "reason": out.get("error") or "the commit did not happen"}
    return {"outcome": "committed", "proposal": public(now), "secrets_stored": stored,
            "commit": out.get("commit") or out.get("sha") or ""}
