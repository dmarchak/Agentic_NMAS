"""The network's MONITORING PROFILE (NSOT_PLAN P.9; docs/MONITORING_PROFILE.md).

One committed document per network, `config_repo/profiles/monitoring.yml`,
holding DATA in the parsers' `host_vars` shape (never configuration text:
the platform templates render it). Every device's intent inherits it through
ONE function, `effective()`; this module is that function and the document's
reader and writer.

The document::

    version: 1
    sections:
      snmp:
        source: prometheus            # the connector it is derived from
        data: {snmp: {communities: [...], settings: [...], hosts: [...]}}
      syslog:                         # P.1's block, whole or absent, heartbeat inside
        source: loki
        data: {logging: {syslog: {trap, origin_id, source_interface, hosts, heartbeat}}}
      ntp:
        source: setting
        data: {ntp_servers: [...]}
      telemetry:
        source: telegraf
        platforms: [cisco_iosxe]      # a section may apply to some platforms only
        data: {telemetry: [...]}
      ip_sla:
        roles: [router]               # ... or some roles only
        policy: gateway               # a POLICY, never addresses (section 6)

THE MERGE, stated once:
- a section applies to a device unless its `platforms` or `roles` exclude it,
  or the device's intent excludes it (`profile_exclude: [{section, reason}]`,
  the reason's shape rule as for an authorised line);
- the section's data is overlaid by the device's own intent, key by key, the
  DEVICE WINNING where it holds a value;
- an EMPTY device value (`[]`, `{}`, `""`, None) is not a value: the parsers
  emit empty skeletons for absent constructs (r6's intent holds
  `snmp: {communities: [], hosts: [], settings: []}`), and an empty skeleton
  that overrode the profile would mean r6 never inherits anything. Opting out
  is the explicit exclusion, never an empty list.

Every device value that DIFFERS from the profile's is an override, reported by
`overrides()` so a screen can draw it. A device value EQUAL to the profile's
is inherited, and `strip_inherited()` drops it at seed and extraction (one
owner).
"""

import copy
import logging

log = logging.getLogger(__name__)

PROFILE_REL = "profiles/monitoring.yml"
VERSION = 1
#: Every section the profile knows, in the order a preview draws them.
SECTIONS = ("snmp", "syslog", "ntp", "lldp", "cdp", "telemetry", "ip_sla")
IP_SLA_POLICIES = ("gateway", "peers", "none")


class ProfileRefused(ValueError):
    """The document cannot be committed; the message names every problem."""


def _empty(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def problems(doc) -> list:
    """Every reason *doc* is not a profile, at once; ``[]`` when it is."""
    out = []
    if not isinstance(doc, dict):
        return ["the profile is not a mapping"]
    if doc.get("version") != VERSION:
        out.append(f"version is {doc.get('version')!r}; this reader knows {VERSION}")
    sections = doc.get("sections")
    if not isinstance(sections, dict):
        return out + ["sections is not a mapping"]
    for name, sec in sections.items():
        if name not in SECTIONS:
            out.append(f"{name!r} is not a profile section ({', '.join(SECTIONS)})")
            continue
        if not isinstance(sec, dict):
            out.append(f"{name}: not a mapping")
            continue
        for key in ("platforms", "roles"):
            if key in sec and not (isinstance(sec[key], list) and all(isinstance(x, str) for x in sec[key])):
                out.append(f"{name}.{key} must be a list of names")
        if name == "ip_sla":
            if sec.get("policy") not in IP_SLA_POLICIES:
                out.append(f"ip_sla.policy must be one of {', '.join(IP_SLA_POLICIES)}")
            if "data" in sec:
                out.append("ip_sla holds a policy, never data: its operations are the "
                           "device's own intent, since a probe targets another device's address")
            continue
        data = sec.get("data")
        if not isinstance(data, dict) or not data:
            out.append(f"{name}: no data")
    return out


def applies(section: dict, platform: str, role: str) -> bool:
    plats, roles = section.get("platforms"), section.get("roles")
    return (not plats or platform in plats) and (not roles or role in roles)


def excluded(intent: dict) -> dict:
    """``{section: reason}`` the device's intent excludes."""
    out = {}
    for e in (intent or {}).get("profile_exclude") or []:
        if isinstance(e, dict) and e.get("section"):
            out[str(e["section"])] = str(e.get("reason") or "")
    return out


def sections_for(doc: dict, platform: str, role: str, intent: dict = None) -> dict:
    """``{section: data}``: the sections that apply to this device, excluding
    what its intent excludes. `ip_sla` carries no data and is never merged."""
    if not doc:
        return {}
    ex = excluded(intent or {})
    out = {}
    for name in SECTIONS:
        sec = (doc.get("sections") or {}).get(name)
        if not sec or name in ex or not applies(sec, platform, role) or "data" not in sec:
            continue
        out[name] = sec["data"]
    return out


#: A setting whose keyword takes ONE value is keyed on the keyword, so a
#: device's own value replaces the profile's; any other line is its own key.
KEYWORD_SETTINGS = ("trap-source", "location", "contact", "chassis-id", "packetsize",
                    "source-interface", "queue-length")


def _setting_key(entry) -> str:
    s = str(entry).strip()
    for kw in KEYWORD_SETTINGS:
        if s == kw or s.startswith(kw + " "):
            return kw
    return s


#: The lists merged ENTRY BY ENTRY, by key (the operator, 2026-09-30): r1, lacking
#: `snmp ifmib ifindex persist`, must gain it and keep its own location and
#: contact. Merged whole, a device's own list replaced the profile's and r1
#: would have gained nothing. A device keeps its entries; the profile adds the
#: entries whose key it lacks. Paths are inside a section's `data`.
#: ONLY where per-device and shared entries share one list: every other list
#: (NTP servers, syslog hosts, communities, telemetry subscriptions) stays a
#: whole value a device may override, as step (a) decided and its tests hold;
#: keying them would add the network's NTP server to a device that chose another.
KEYED_LISTS = {
    "snmp.settings": _setting_key,
}

#: PER-DEVICE fields, by the key their list gives them: meant to differ per
#: device, so never compared by a proposal, never carried in the profile, and
#: never overwritten by an apply. Every other field is SHARED: it must agree.
PER_DEVICE = {"snmp.settings": ("location", "contact", "chassis-id")}


def per_device(path: str, entry) -> bool:
    return path in PER_DEVICE and KEYED_LISTS[path](entry) in PER_DEVICE[path]


def shared_only(path: str, entries: list) -> list:
    return [e for e in (entries or []) if not per_device(path, e)]


def _overlay(base, top, path: str = ""):
    """*top* (the device) over *base* (the profile): dicts recursively, a
    KEYED list entry by entry, and any other value of *top* replaces *base*'s
    unless it is empty."""
    if isinstance(base, dict) and isinstance(top, dict):
        out = dict(base)
        for k, v in top.items():
            p = f"{path}.{k}" if path else k
            out[k] = _overlay(base[k], v, p) if k in base else copy.deepcopy(v)
        return out
    if path in KEYED_LISTS and isinstance(base, list) and isinstance(top, list) and top:
        key = KEYED_LISTS[path]
        have = {key(e) for e in top}
        return copy.deepcopy(top) + [copy.deepcopy(e) for e in base
                                     if key(e) not in have and not per_device(path, e)]
    return copy.deepcopy(base) if _empty(top) else copy.deepcopy(top)


def secret_refs(data) -> set:
    """Every secret a profile section names: a `ref:` value, or a
    `__secret__:<ref>` marker inside a string."""
    import re

    out = set()
    if isinstance(data, dict):
        for k, v in data.items():
            if k == "ref" and isinstance(v, str) and v:
                out.add(v)
            else:
                out |= secret_refs(v)
    elif isinstance(data, list):
        for v in data:
            out |= secret_refs(v)
    elif isinstance(data, str):
        out |= set(re.findall(r"__secret__:(\S+)", data))
    return out


def effective(intent: dict, doc: dict, platform: str, role: str) -> dict:
    """THE one merge: the profile's applying sections overlaid by the
    device's own intent. Every reader of intent that renders or compares
    calls this; nothing else merges the profile. The profile's secret
    references join the device's `secret_refs`, so hydration asks for them
    (the device's own value, then the profile's)."""
    out = copy.deepcopy(intent or {})
    refs = set()
    for _name, data in sections_for(doc, platform, role, intent).items():
        out = _overlay(data, out)
        refs |= secret_refs(data)
    if refs:
        out["secret_refs"] = sorted(set(out.get("secret_refs") or []) | refs)
    return out


def _walk(profile_part, device_part, path=""):
    """Yield (path, profile value, device value) for every leaf the profile
    sets; a KEYED list's entries one by one, matched by key."""
    if path in KEYED_LISTS and isinstance(profile_part, list):
        key = KEYED_LISTS[path]
        mine = {key(e): e for e in (device_part or []) if isinstance(device_part, list)}
        for e in profile_part:
            if not per_device(path, e):
                yield f"{path}[{key(e)}]", e, mine.get(key(e))
        return
    if isinstance(profile_part, dict):
        for k, v in profile_part.items():
            yield from _walk(v, (device_part or {}).get(k) if isinstance(device_part, dict) else None,
                             f"{path}.{k}" if path else k)
    else:
        yield path, profile_part, device_part


def overrides(intent: dict, doc: dict, platform: str, role: str) -> list:
    """Every place the device's own value DIFFERS from the profile's:
    ``[{"section", "path", "profile", "device"}]``. An empty device value is
    inheritance, not an override."""
    out = []
    for name, data in sections_for(doc, platform, role, intent).items():
        for path, pv, dv in _walk(data, intent or {}):
            if not _empty(dv) and dv != pv:
                out.append({"section": name, "path": path, "profile": pv, "device": dv})
    return out


def strip_inherited(intent: dict, doc: dict, platform: str, role: str) -> dict:
    """ONE OWNER at seed and extraction: every device value EQUAL to the
    profile's is dropped (the device inherits it); a differing value stays,
    an override. Containers left empty keep their empty skeleton, the shape
    the parsers emit."""
    out = copy.deepcopy(intent or {})

    def drop(pdata, node, path=""):
        if not isinstance(pdata, dict) or not isinstance(node, dict):
            return
        for k, pv in pdata.items():
            if k not in node:
                continue
            p = f"{path}.{k}" if path else k
            if isinstance(pv, dict) and isinstance(node[k], dict):
                drop(pv, node[k], p)
            elif p in KEYED_LISTS and isinstance(pv, list) and isinstance(node[k], list):
                # Entry by entry: an entry equal to the profile's is inherited;
                # a differing one, and every per-device one, stays.
                key = KEYED_LISTS[p]
                theirs = {key(e): e for e in pv}
                node[k] = [e for e in node[k] if theirs.get(key(e)) != e]
            elif node[k] == pv:
                node[k] = [] if isinstance(pv, list) else ({} if isinstance(pv, dict) else "")
    for _name, data in sections_for(doc, platform, role, intent).items():
        drop(data, out)
    return out


# ------------------------------------------------------ the committed document

def read_committed(repo: str):
    """The profile as COMMITTED at HEAD (C104: every reader takes what is
    committed); ``None`` when the network has none. Raises when it exists
    and cannot be read or is not a profile: a broken profile is never read as
    no profile, which would silently drop every inherited line."""
    import yaml

    from modules.nsot import repo as R

    # ABSENT AND UNREADABLE ARE DIFFERENT FACTS. `RefSource.read` answers None
    # for both, so the path is LISTED first: an empty listing at a readable
    # HEAD is "no profile"; a failed listing is an error, never "no profile".
    rc, out, err = R.git_raw(repo, "ls-tree", "--name-only", "HEAD", "--", PROFILE_REL)
    if rc != 0:
        rc2, _o, _e = R.git_raw(repo, "rev-parse", "--verify", "-q", "HEAD")
        if rc2 != 0:
            return None                         # a repository with no commit yet
        raise ProfileRefused(f"{PROFILE_REL} could not be listed at HEAD: {err or rc}")
    if not out.strip():
        return None
    rc, text, err = R.git_raw(repo, "show", f"HEAD:{PROFILE_REL}")
    if rc != 0:
        raise ProfileRefused(f"{PROFILE_REL} is at HEAD and could not be read: {err or rc}")
    doc = yaml.safe_load(text) or {}
    bad = problems(doc)
    if bad:
        raise ProfileRefused(f"{PROFILE_REL} at HEAD is not a profile: " + "; ".join(bad))
    return doc


def read_at(repo: str, ref: str):
    """The profile as it was at *ref* (a restore renders the ref's intent with
    the ref's profile, never today's); ``None`` when there was none then."""
    import yaml

    from modules.nsot import repo as R

    rc, out, err = R.git_raw(repo, "ls-tree", "--name-only", ref, "--", PROFILE_REL)
    if rc != 0:
        raise ProfileRefused(f"{PROFILE_REL} could not be listed at {ref}: {err or rc}")
    if not out.strip():
        return None
    rc, text, err = R.git_raw(repo, "show", f"{ref}:{PROFILE_REL}")
    if rc != 0:
        raise ProfileRefused(f"{PROFILE_REL} could not be read at {ref}: {err or rc}")
    doc = yaml.safe_load(text) or {}
    bad = problems(doc)
    if bad:
        raise ProfileRefused(f"{PROFILE_REL} at {ref} is not a profile: " + "; ".join(bad))
    return doc


def role_of(list_name: str, hostname: str) -> str:
    """The device's role in its list's inventory (C225), ``""`` when none."""
    from modules.nsot.restore import _devices_of

    row = next((d for d in _devices_of(list_name) if d.get("hostname") == hostname), None)
    return ((row or {}).get("role") or "").strip()


def effective_for(repo: str, list_name: str, hostname: str, intent: dict, platform: str,
                  role: str = None, doc=None, ref: str = "HEAD") -> dict:
    """`effective()` for a device of a list: the profile committed at *ref*
    (HEAD by default) and the device's inventory role. The intent unchanged
    when the network has no profile. A broken profile RAISES
    (`ProfileRefused`): a caller refuses by name rather than rendering without
    the lines every device inherits."""
    if intent is None:
        return None
    if doc is None:
        doc = read_committed(repo) if ref == "HEAD" else read_at(repo, ref)
    if not doc:
        return intent
    return effective(intent, doc, platform, role_of(list_name, hostname) if role is None else role)


def commit_profile(list_name: str, doc: dict, actor: str, summary: str) -> dict:
    """Commit the network's profile: ONE commit (`profile: <summary>`,
    `Source: profile`) of exactly `profiles/monitoring.yml`. Refuses, writing
    nothing, a document that is not a profile. A failed commit puts the file
    back as it was committed."""
    import os

    import yaml

    from modules.config import get_list_data_dir
    from modules.filestore import write_atomic
    from modules.nsot import repo as R

    bad = problems(doc)
    if bad:
        raise ProfileRefused("; ".join(bad))
    if not actor:
        raise ProfileRefused("a profile commit records who made it, and no actor was given")
    repo = os.path.join(get_list_data_dir(list_name), "config_repo")
    path = os.path.join(repo, PROFILE_REL)
    before = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            before = fh.read()
    text = yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)
    write_atomic(path, text)
    out = R._commit_paths(list_name, [PROFILE_REL], f"profile: {summary}",
                          [f"Actor: {actor}"], "profile")
    if not out.get("ok"):
        if before is None:
            os.remove(path)
        else:
            write_atomic(path, before)
    return out


def set_secret(list_name: str, ref: str, value: str) -> dict:
    """Store the network's value for a profile secret (never returned, never
    logged): one per network, under `credentials.profile_secret_key`."""
    from modules.credentials import profile_secret_key, set_template_secret

    if not value:
        raise ProfileRefused(f"no value given for the profile secret {ref!r}")
    return set_template_secret(profile_secret_key(list_name, ref), value, list_name=list_name)
