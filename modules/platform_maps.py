"""Settings › Installation › Platforms and roles (board F4, decision B, signed off 2026-10-10 with
the operator's validation): the platform map and the role map, editable for the first time
(C622: they had no screen).

How a NetBox-sourced device becomes something Mercury can open a session to and draw:

- **platform map**: a NetBox platform slug → its netmiko **driver** (chosen from the drivers
  Mercury supports: those whose config dialect it knows and netmiko has, never typed), its
  config **dialect** (the templates it renders from; one of `nsot.platform.DIALECTS`, C628),
  how it delivers (ssh or netconf) and whether it supports NETCONF; a **default driver** for a
  platform the map lacks (empty: the device is skipped, with its reason);
- **role map**: a NetBox role slug → router, switch, firewall, or "" (the hostname guesses).

A change is never saved blind (the operator's validation): **Preview changes** names every
device whose driver or role it moves, network by network, from each NetBox list's last
inventory (never a refresh: a preview writes nothing); a **Test** opens one read-only session to
one affected device with the new driver (the reads engine, `show version`); the **confirm** is
bound to the preview's fingerprint, refused naming what moved, written, recorded, and each
NetBox list refreshed so the change lands. Local (CSV) lists keep the driver their list names.
"""

import hashlib
import json
import os
import re

#: Preview, then confirm: the steps the manual's page names.
SAVE_STEPS = ("check", "preview", "write", "record", "refresh")
#: The roles Mercury draws and checks by ("" lets the hostname guess).
ROLES = ("router", "switch", "firewall", "")
ROLE_WORDS = {"router": "router", "switch": "switch", "firewall": "firewall",
              "": "guess from hostname"}
TRANSPORTS = ("ssh", "netconf")
SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*")
#: The command the Test asks the one device: read-only on every supported driver.
TEST_COMMAND = "show version"


class Refused(ValueError):
    """Nothing was previewed or written; the message names the field and why."""


def supported_drivers() -> list:
    """The drivers Mercury supports: those whose config dialect it knows
    (`nsot.platform._DERIVED_FROM_DEVICE_TYPE`) and netmiko has."""
    from modules.nsot.platform import _DERIVED_FROM_DEVICE_TYPE
    try:
        from netmiko.ssh_dispatcher import CLASS_MAPPER
    except ImportError:                                   # netmiko absent: none can be opened
        return []
    return sorted(d for d in _DERIVED_FROM_DEVICE_TYPE if d in CLASS_MAPPER)


def dialects() -> list:
    from modules.nsot.platform import DIALECTS

    return sorted(DIALECTS)


def dialect_of(template_dir: str) -> str:
    """The config dialect a `template_dir` names, or "" when it names none Mercury knows
    (C628: `cisco-ios-xe` becomes `cisco_ios_xe`, which is not a dialect)."""
    from modules.nsot.platform import is_dialect

    value = (template_dir or "").strip().replace("-", "_")
    return value if is_dialect(value) else ""


def _maps() -> dict:
    from modules.settings_schema import DEFAULTS, get_setting

    return {"platform_map": dict(get_setting("platform_map", DEFAULTS["platform_map"]) or {}),
            "default_driver": (get_setting("platform_default_netmiko_type", "") or "").strip(),
            "role_map": dict(get_setting("role_map", DEFAULTS["role_map"]) or {})}


def view() -> dict:
    """The two cards: each platform row (with what is wrong with it, if anything), the default
    driver, each role row, and the choices offered."""
    from modules.nsot.platform import _FROM_NETBOX_SLUG

    m = _maps()
    drivers = supported_drivers()
    rows = []
    for slug, e in sorted(m["platform_map"].items()):
        driver = (e.get("netmiko_device_type") or "").strip()
        # Mercury's own table wins for the slugs it knows (`dialect_for_netbox_slug`), so
        # their template folder is never read: no problem to say there.
        dialect = _FROM_NETBOX_SLUG.get(slug) or dialect_of(e.get("template_dir", ""))
        problems = []
        if driver not in drivers:
            problems.append(f"driver {driver or '(none)'} is not one Mercury supports")
        if not dialect:
            problems.append(f"template folder {e.get('template_dir') or '(none)'} names no "
                            "dialect Mercury knows")
        rows.append({"slug": slug, "driver": driver, "dialect": dialect,
                     "transport": e.get("deploy_transport") or "ssh",
                     "netconf": bool(e.get("supports_netconf")), "problems": problems})
    roles = [{"slug": s, "role": r or ""} for s, r in sorted(m["role_map"].items())]
    return {"rows": rows, "default_driver": m["default_driver"], "roles": roles,
            "drivers": drivers, "dialects": dialects(), "transports": TRANSPORTS,
            "role_choices": [(r, ROLE_WORDS[r]) for r in ROLES]}


def _slug(raw, what: str) -> str:
    s = (raw or "").strip().lower()
    if not SLUG.fullmatch(s):
        raise Refused(f"{what} {raw!r} is not a NetBox slug (lower-case letters, digits and "
                      ". _ -)")
    return s


def proposal(kind: str, form) -> dict:
    """The map *form* asks for (`kind` "platforms" or "roles"), checked: each row's fields as
    sent, the add row when its slug is filled, less a removed slug. *form* is a request's
    `MultiDict`-like object (``getlist``, ``get``). Raises `Refused` naming the field."""
    drivers, known = supported_drivers(), set(dialects())
    removed = (form.get("remove") or "").strip()
    if kind == "platforms":
        out, netconf = {}, set(form.getlist("netconf"))
        for slug, driver, dialect, transport in zip(form.getlist("slug"),
                                                    form.getlist("driver"),
                                                    form.getlist("dialect"),
                                                    form.getlist("transport")):
            slug = _slug(slug, "Platform")
            if slug == removed:
                continue
            out[slug] = _platform_row(slug, driver, dialect, transport, slug in netconf,
                                      drivers, known)
        new = (form.get("new_slug") or "").strip()
        if new:
            new = _slug(new, "The new platform")
            if new in out:
                raise Refused(f"{new} is in the map already: change its row instead")
            out[new] = _platform_row(new, form.get("new_driver"), form.get("new_dialect"),
                                     form.get("new_transport"), bool(form.get("new_netconf")),
                                     drivers, known)
        default = (form.get("default_driver") or "").strip()
        if default and default not in drivers:
            raise Refused(f"the default driver {default!r} is not one Mercury supports: "
                          + ", ".join(drivers))
        return {"kind": kind, "platform_map": out, "default_driver": default,
                "removed": removed}
    if kind == "roles":
        out = {}
        for slug, role in zip(form.getlist("slug"), form.getlist("role")):
            slug = _slug(slug, "Role")
            if slug == removed:
                continue
            if role not in ROLES:
                raise Refused(f"{slug}'s role {role!r} is not one of: "
                              + ", ".join(ROLE_WORDS.values()))
            out[slug] = role
        new = (form.get("new_slug") or "").strip()
        if new:
            new = _slug(new, "The new role")
            if new in out:
                raise Refused(f"{new} is in the map already: change its row instead")
            role = form.get("new_role") or ""
            if role not in ROLES:
                raise Refused(f"the new role {role!r} is not one of: "
                              + ", ".join(ROLE_WORDS.values()))
            out[new] = role
        return {"kind": kind, "role_map": out, "removed": removed}
    raise Refused(f"{kind!r} is neither the platform map nor the role map")


def _platform_row(slug, driver, dialect, transport, netconf, drivers, known) -> dict:
    driver, dialect, transport = (driver or "").strip(), (dialect or "").strip(), \
        (transport or "ssh").strip()
    if driver not in drivers:
        raise Refused(f"{slug}'s driver {driver!r} is not one Mercury supports: "
                      + ", ".join(drivers))
    if dialect not in known:
        raise Refused(f"{slug}'s config dialect {dialect!r} is not one Mercury knows: "
                      + ", ".join(sorted(known)))
    if transport not in TRANSPORTS:
        raise Refused(f"{slug} delivers by {transport!r}, which is neither ssh nor netconf")
    return {"netmiko_device_type": driver, "template_dir": dialect,
            "deploy_transport": transport, "supports_netconf": bool(netconf)}


def _cached(list_name: str) -> dict:
    """*list_name*'s last NetBox inventory as persisted (identity fields only), read without
    refreshing it or creating its folder: ``{"devices", "skipped"}``, or ``{"unread": why}``."""
    from modules.config import list_data_path
    from modules.inventory import _CACHE_FILE

    p = os.path.join(list_data_path(list_name), _CACHE_FILE)
    if not os.path.exists(p):
        return {"devices": [], "skipped": [], "never": True}
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        return {"unread": f"{type(exc).__name__}: {exc}"}
    return {"devices": doc.get("devices") or [], "skipped": doc.get("skipped") or []}


def _driver(slug: str, pmap: dict, default: str) -> str:
    entry = pmap.get(slug) if slug else None
    if entry:
        return (entry.get("netmiko_device_type") or "").strip()
    return default


def effect(p: dict) -> dict:
    """What proposal *p* changes, from each network's last inventory, never a refresh:
    ``{"changes": [{network, device, driver_from, driver_to, role_from, role_to}],
    "local": [(network, n)], "unread": [(network, why)], "role_unknown": n,
    "now_loaded": n, "in_use": {slug: [devices]}}``."""
    from modules.inventory import source_config
    from modules.nsot import listref

    m = _maps()
    new_pmap = p.get("platform_map", m["platform_map"])
    new_default = p.get("default_driver", m["default_driver"])
    new_roles = p.get("role_map", m["role_map"])
    out = {"changes": [], "local": [], "unread": [], "role_unknown": 0, "now_loaded": 0,
           "in_use": {}}
    for name in sorted(listref._registry()):
        try:
            netbox = source_config.is_netbox_sourced(name)
        except Exception as exc:                          # noqa: BLE001
            out["unread"].append((name, f"its inventory source: {type(exc).__name__}: {exc}"))
            continue
        if not netbox:
            from modules.device import load_saved_devices
            try:
                n = len(load_saved_devices(listref.resolve(name).csv_path))
            except Exception:                             # noqa: BLE001
                n = 0
            out["local"].append((name, n))
            continue
        got = _cached(name)
        if "unread" in got:
            out["unread"].append((name, got["unread"]))
            continue
        for d in got["devices"]:
            slug, host = d.get("_platform", ""), d.get("hostname", "")
            if p.get("removed") and slug == p["removed"] and p["kind"] == "platforms":
                out["in_use"].setdefault(slug, []).append(f"{host} ({name})")
            if p["kind"] == "roles" and p.get("removed") and \
                    d.get("_role_slug") == p["removed"]:
                out["in_use"].setdefault(p["removed"], []).append(f"{host} ({name})")
            d_from = d.get("device_type", "")
            d_to = _driver(slug, new_pmap, new_default) or d_from
            r_from = d.get("role", "")
            if "_role_slug" in d:
                r_to = new_roles.get(d["_role_slug"], "") if d["_role_slug"] else r_from
            else:
                r_to = r_from
                if p["kind"] == "roles":
                    out["role_unknown"] += 1
            if d_from != d_to or r_from != r_to:
                out["changes"].append({"network": name, "device": host,
                                       "driver_from": d_from, "driver_to": d_to,
                                       "role_from": r_from, "role_to": r_to})
        for s in got["skipped"]:
            if s.get("field") == "platform":
                m_slug = re.search(r"platform '([^']*)'", s.get("reason", ""))
                if m_slug and _driver(m_slug.group(1), new_pmap, new_default):
                    out["now_loaded"] += 1
    return out


def fingerprint(p: dict, e: dict) -> str:
    """What the confirm is bound to: the proposal, the maps it replaces, and its effect."""
    blob = json.dumps({"p": p, "was": _maps(), "e": e}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def preview(kind: str, form) -> dict:
    """Preview changes: the proposal, checked; its effect; the fingerprint the confirm carries.
    A removal of a slug a device uses is refused, naming the devices."""
    p = proposal(kind, form)
    e = effect(p)
    if p.get("removed") and e["in_use"].get(p["removed"]):
        used = e["in_use"][p["removed"]]
        raise Refused(f"{p['removed']} is used by {', '.join(used[:10])}"
                      + (f" and {len(used) - 10} more" if len(used) > 10 else "")
                      + ": change their platform or role in NetBox first")
    # The Test's choices: a device whose DRIVER changes (a role change opens no session).
    testable = [c for c in e["changes"] if c["driver_to"] and c["driver_from"] != c["driver_to"]]
    return {"proposal": p, "effect": e, "fingerprint": fingerprint(p, e),
            "proposal_json": json.dumps(p, sort_keys=True), "testable": testable}


def test(network: str, device: str, driver: str, actor: str) -> dict:
    """One read-only session to one affected device with the new driver: the reads engine,
    TEST_COMMAND, as a job (a device read is bounded past a request's limit). ``{"job",
    "run"}`` or ``{"refused"}``."""
    from modules.nsot import reads

    if driver not in supported_drivers():
        raise Refused(f"{driver!r} is not a driver Mercury supports")
    return reads.start(network, [device], [TEST_COMMAND], actor,
                       purpose=f"platform map test: {device} with {driver}",
                       drivers={device: driver})


def apply(proposal_json: str, fp: str, actor: str, verified: str) -> dict:
    """The confirm: re-preview what was shown, refuse naming what moved, write the map, record
    who and which, and refresh each NetBox list so its devices take the change."""
    from modules import installation_settings as I
    from modules.inventory import invalidate, refresh_async, source_config
    from modules.nsot import listref
    from modules.settings_schema import write_settings

    try:
        p = json.loads(proposal_json or "")
    except ValueError:
        raise Refused("the confirm carried no proposal: preview it again") from None
    e = effect(p)
    if fingerprint(p, e) != fp:                                                   # check
        raise Refused("the maps or the devices moved since the preview (its fingerprint "
                      f"{fp or '(none)'} no longer matches): preview it again")
    if p["kind"] == "platforms":
        updates = {"platform_map": p["platform_map"],
                   "platform_default_netmiko_type": p["default_driver"]}
    else:
        updates = {"role_map": p["role_map"]}
    out = write_settings(updates, actor=actor)                                     # write
    if not out["ok"]:
        raise Refused(out["error"])
    entry = I._record({"kind": f"{p['kind']}_map", "card": p["kind"], "actor": actor,  # record
                       "actor_verified": verified, "fields": sorted(updates),
                       "devices_changed": len(e["changes"])})
    refreshed = []
    for name in sorted(listref._registry()):                                       # refresh
        try:
            if source_config.is_netbox_sourced(name):
                invalidate(name)
                refresh_async(name)
                refreshed.append(name)
        except Exception:                                 # noqa: BLE001 (said by its absence)
            continue
    return dict(entry, ok=True, changes=e["changes"], refreshed=refreshed, kind=p["kind"])
