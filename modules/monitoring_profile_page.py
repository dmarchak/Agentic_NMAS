"""Monitoring › Profile on v2 (C566, board A, signed off 2026-10-07): the network's committed
profile, section by section, with how many devices hold each, and Propose from the connectors.

The sections' "on the devices" counts are Coverage's own cells (`monitoring_coverage.fleet`),
never a second reading of the goldens: the two pages cannot disagree. Propose is
`profile_propose`'s, the code today's dialog runs too; this draws it for v2 and adds what the
board asked of its preview: whether the network's templates render each new or changed section
(`profile_apply.unrendered_for_device`), since a committed section the template drops reaches
no device (C565).
"""

import json
import logging

log = logging.getLogger(__name__)

#: Coverage's columns that hold each section; a section with none is not measured there.
COLUMNS_OF = {"snmp": ("snmp",), "syslog": ("syslog", "heartbeat"), "ntp": ("ntp",),
              "management": ("management",), "lldp": ("lldp",), "cdp": (),
              "telemetry": ("telemetry",), "ip_sla": ("ip_sla",)}

_POLICY_WORDS = {"gateway": "probe the default gateway", "peers": "probe the routing peers",
                 "none": "probe nothing"}


def _canon(v) -> str:
    return json.dumps(v, sort_keys=True, default=str)


def _applies_words(sec: dict) -> str:
    from modules.monitoring_coverage import _PLATFORM_WORDS   # the one table of these words
    plats = [_PLATFORM_WORDS.get(p, p) for p in sec.get("platforms") or []]
    roles = list(sec.get("roles") or [])
    if not plats and not roles:
        return "every device"
    return " and ".join(x for x in ((" and ".join(plats) + " only") if plats else "",
                                    ("role " + ", ".join(roles)) if roles else "") if x)


def _held(c: dict, section: str) -> dict:
    """How the devices stand on *section*, from Coverage's cells: ``{"hold", "of", "missing",
    "not_rendered", "measured"}`` with the hosts missing it."""
    cols = COLUMNS_OF.get(section, ())
    out = {"hold": 0, "of": 0, "missing": [], "not_rendered": [], "measured": bool(cols)}
    if not cols:
        return out
    for d in c.get("devices") or []:
        states = [(d["cells"].get(k) or {}).get("state") for k in cols]
        if all(s in ("not_applicable", "excluded", "unused", None) for s in states):
            continue
        out["of"] += 1
        if "not_rendered" in states:
            out["not_rendered"].append(d["host"])
        elif any(s in ("gap", "gap_open") for s in states):
            out["missing"].append(d["host"])
        elif all(s in ("ok", "not_reporting", "not_applicable", "excluded", "unused")
                 for s in states):
            out["hold"] += 1
    return out


def sections(ref) -> dict:
    """The committed profile's rows for the page: ``{"list", "ok", "error", "committed",
    "commit", "committed_at", "rows", "not_rendered"}``. Writes nothing."""
    from modules import list_settings, monitoring_coverage
    from modules.nsot import profile as _p, profile_propose as pp
    from modules.preview_confirm import PROFILE_SECTION_WORDS

    out = {"list": ref.name, "ok": True, "error": "", "committed": False, "rows": [],
           "not_rendered": 0}
    try:
        doc = _p.read_committed(ref.repo_dir)
    except Exception as exc:                            # noqa: BLE001
        return dict(out, ok=False, error=f"{type(exc).__name__}: {exc}")
    c = monitoring_coverage.fleet(ref)
    prof = c.get("profile") or {}
    out.update(committed=bool(doc), commit=prof.get("commit", ""),
               committed_at=prof.get("committed_at", ""))

    def get(key, default=None):
        return list_settings.value(ref.name, key, default)
    for name in _p.SECTIONS:
        sec = ((doc or {}).get("sections") or {}).get(name)
        if not sec:
            continue
        if name == "ip_sla":
            basis = f"a policy: {_POLICY_WORDS.get(sec.get('policy'), sec.get('policy'))}"
        else:
            try:
                basis = pp.connector_value(name, get).get("basis") or sec.get("source") or ""
            except Exception as exc:                    # noqa: BLE001
                basis = f"{sec.get('source') or 'its source'} (not read: {type(exc).__name__})"
        held = _held(c, name)
        out["not_rendered"] += len(held["not_rendered"])
        out["rows"].append({"section": name, "words": PROFILE_SECTION_WORDS.get(name, name),
                            "basis": basis, "applies": _applies_words(sec), "held": held})
    return out


def proposal(list_name: str) -> dict:
    """Propose from the connectors, for v2's card: each section's state (new, changed, as
    committed, not proposed, with why), the devices whose effective intent moves, and, for each
    new or changed section, how many devices' templates render none of it. Writes nothing."""
    from modules.nsot import profile as _p, profile_apply, profile_propose as pp
    from modules.preview_confirm import PROFILE_SECTION_WORDS

    p = pp.public(pp.propose(list_name))
    current = (p.get("current") or {}).get("sections") or {}
    proposed = (p.get("doc") or {}).get("sections") or {}
    fleet, _skipped = pp._fleet(list_name)
    repo = pp._repo(list_name)
    rows, signatures = [], {}
    for s in p["sections"]:
        name = s["section"]
        new, cur = proposed.get(name), current.get(name)
        state = ("new" if new and not cur else
                 "changed" if new and _canon(new) != _canon(cur) else
                 "as committed" if new else "not proposed")
        row = {"section": name, "words": PROFILE_SECTION_WORDS.get(name, name),
               "state": state, "why": s.get("why") or s.get("basis") or "",
               "variants": len(s.get("variants") or []), "dropped": [], "receives": 0}
        if state in ("new", "changed") and (new or {}).get("data"):
            for host, plat, role, intent in fleet:
                if not _p.applies(new, plat, role):
                    continue
                missing, _t = profile_apply.unrendered_for_device(
                    list_name, repo, host, plat, role, intent, {name: new["data"]}, signatures)
                if missing:
                    row["dropped"].append(host)
                else:
                    row["receives"] += 1
        rows.append(row)
    changes = [r for r in rows if r["state"] in ("new", "changed")]
    return {"list": list_name, "hash": p["hash"], "changed": p["changed"], "rows": rows,
            "changes": changes, "effect": len(p.get("effect") or []),
            "devices_read": p.get("devices_read", 0), "skipped": p.get("skipped") or [],
            "dropped": sorted({h for r in changes for h in r["dropped"]}),
            "variants": [r for r in rows if r["variants"]],
            "profile_blob": p.get("profile_blob", "")}


def commit(list_name: str, confirmed_hash: str, actor: str) -> dict:
    """The confirm: `profile_propose.apply`, refusing a proposal that moved since the card."""
    from modules.nsot import profile as _p, profile_propose as pp

    try:
        out = pp.apply(list_name, confirmed_hash, actor)
    except _p.ProfileRefused as exc:
        return {"outcome": "refused", "why": f"nothing committed: {exc}"}
    out = {k: v for k, v in out.items() if k != "proposal"}
    return out
