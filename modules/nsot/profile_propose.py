"""PROPOSE THE NETWORK'S MONITORING PROFILE (NSOT_PLAN P.9;
docs/MONITORING_PROFILE.md 2): a profile derived from what the fleet's
COMMITTED intent already agrees on, previewed, confirmed by hash and committed
as the verified person. It writes nothing to any device: a device receives
the profile when a person applies it (`profile_apply`, the scoped deploy).

The rule, stated once:

- a section is proposed only where its connector is configured (SNMP needs
  Prometheus, syslog needs Loki); NTP, telemetry, LLDP and CDP have no
  connector setting yet, and their basis is the fleet alone, said so;
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
        if not held:
            row["why"] = "no device's committed intent holds it"
            continue
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
                              "their intent first")
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
        holders = sorted(only["devices"])
        holder_plats = sorted({plat for _h, plat, _v in held})
        # A device holding ANOTHER version is not lacking: it is in `changes`.
        lacking = [(h, plat) for h, plat, _r, intent in fleet if h not in holders
                   and h not in (row.get("changes") or {})]
        section = {"source": source, "data": only["value"]}
        if any(plat not in holder_plats for _h, plat in lacking):
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
        if refs:
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
    out = _p.commit_profile(list_name, now["doc"], actor,
                            "proposed from the fleet's committed intent ("
                            + ", ".join(proposed) + ")"
                            + (f"; chosen: {'; '.join(chosen)}" if chosen else ""))
    if not out.get("ok"):
        return {"outcome": "failed", "proposal": public(now), "secrets_stored": stored,
                "reason": out.get("error") or "the commit did not happen"}
    return {"outcome": "committed", "proposal": public(now), "secrets_stored": stored,
            "commit": out.get("commit") or out.get("sha") or ""}
