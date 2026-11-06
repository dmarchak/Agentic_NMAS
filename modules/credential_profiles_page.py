"""modules/credential_profiles_page.py — Source of truth › Credentials › Profiles on v2 (the board
drawn 2026-10-10 under the Phase 7 mode; CUTOVER's "Credential profiles", whose JSON routes no
screen called).

A credential profile is a login the resolver (`credentials.resolve`) gives a device a NetBox
inventory brings in with no login of its own: after the device's own override and its network's
credential list, a profile named ``platform:<NetBox platform slug>`` (C2605), then
``role:<kind>``, then ``site:<site>``, then ``default``. Any other name is stored and read by
NOTHING, and the tab says so rather than letting it look like it works. No value is ever
returned: a password is "set" or "not set".

**A role profile is by Mercury's kind** (C2604): the resolver is given the role's
``mercury_kind`` (router, switch, firewall, host), never the NetBox role slug, so the form
offers the kinds as choices, each naming the NetBox roles it covers now (from the loaded
inventories), and a new profile no device can match is refused, naming the scope and what
exists: a kind Mercury has, a platform in the platform map, a site a loaded NetBox device is at.

Saving and deleting go through `credentials.save_profile` and `delete_profile`, the store's one
write path, and each is recorded (`credential_changes`): who, which profile, which fields.
"""

import json
import logging
import os

log = logging.getLogger(__name__)

#: What a profile name covers, in the resolver's order after a device's own login
#: (`credentials.PROFILE_SCOPES`, then default). A role profile is chosen by its kind
#: (`role_kind.KINDS`), so the form draws one choice per kind (`choices`).
KINDS = (("platform", "every device on the platform"), ("role", "every device of the kind"),
         ("site", "every device at the site"),
         ("default", "every device nothing before it covers"))


def exists() -> dict:
    """What a profile can match now: ``{"kinds": {kind: [NetBox role slugs]}, "platforms":
    [slugs], "sites": [slugs]}``. The kinds are Mercury's (`role_kind.KINDS`), each with the
    NetBox roles the loaded NetBox inventories hold it for; the platforms are the platform
    map's (a device whose platform is not in it is skipped, so nothing else can match); the
    sites are those a loaded NetBox device is at. Read from the loaded inventories and the
    settings, never NetBox: a page read, no per-device work but one pass over each list."""
    from modules import inventory
    from modules.inventory.role_kind import KINDS as ROLE_KINDS
    from modules.nsot import listref
    from modules.settings_schema import DEFAULTS, get_setting

    roles = {k: set() for k in ROLE_KINDS}
    sites = set()
    for name in sorted(listref._registry()):
        try:
            rows = inventory.loaded_rows(name)
        except Exception as exc:                      # noqa: BLE001 - that list adds nothing
            log.warning("credential_profiles_page: %s's inventory was not read: %s", name, exc)
            continue
        for d in rows:
            if d.get("role") in roles and d.get("_role_slug"):
                roles[d["role"]].add(d["_role_slug"])
            if d.get("_site"):
                sites.add(d["_site"])
    platforms = sorted(get_setting("platform_map", DEFAULTS["platform_map"]) or {})
    return {"kinds": {k: sorted(v) for k, v in roles.items()}, "platforms": platforms,
            "sites": sorted(sites)}


def choices(known: dict = None) -> list:
    """The form's ``(value, words)`` choices: a platform, one per kind (naming the NetBox
    roles it covers now), a site, every device."""
    known = exists() if known is None else known
    out = [("platform", "every device on a platform (its NetBox platform slug, below)")]
    for kind, slugs in known["kinds"].items():
        held = (f"NetBox roles now: {', '.join(slugs)}" if slugs else
                "no loaded NetBox device has it yet")
        out.append((f"role:{kind}",
                    f"every {kind} (its NetBox role has mercury_kind {kind}; {held})"))
    out.append(("site", "every device at a site (its NetBox site slug, below)"))
    out.append(("default", "every device nothing before it covers (default)"))
    return out


def name_of(kind: str, value: str, known: dict = None) -> tuple:
    """``(name, problem)``: the profile name the resolver reads for *kind* and *value*, or why
    no device could ever be given it. *kind* is ``platform``, ``site``, ``default``, ``role``
    (its *value* a kind) or ``role:<kind>`` (the form's choice)."""
    from modules.inventory.role_kind import KINDS as ROLE_KINDS

    value = (value or "").strip()
    if kind == "default":
        return "default", ""
    if kind.startswith("role:"):
        kind, value = "role", kind.partition(":")[2]
    if kind not in ("platform", "role", "site"):
        return "", (f"a profile covers a platform, a kind, a site or every device (default), "
                    f"not {kind!r}")
    if not value or any(c.isspace() for c in value) or ":" in value:
        return "", f"name the {kind} it covers as one word, as NetBox names it (got {value!r})"
    if kind == "role":
        if value not in ROLE_KINDS:
            return "", (f"no device can match role:{value}: a role profile is by Mercury's "
                        f"kind (the NetBox role's mercury_kind), and the kinds are "
                        f"{', '.join(ROLE_KINDS)}; a NetBox role slug matches nothing")
        return f"role:{value}", ""
    known = exists() if known is None else known
    held = known["platforms"] if kind == "platform" else known["sites"]
    if value not in held:
        where = ("in the platform map (Settings › Installation › Platforms and roles)"
                 if kind == "platform" else "of a device a NetBox inventory has loaded")
        return "", (f"no device can match {kind}:{value}: the {kind}s {where} are "
                    f"{', '.join(held) if held else 'none'}")
    return f"{kind}:{value}", ""


def covers(name: str) -> dict:
    """``{"kind", "value", "words", "read"}``: what the resolver reads *name* for."""
    from modules.credentials import DEFAULT_PROFILE
    from modules.inventory.role_kind import KINDS as ROLE_KINDS

    if name == DEFAULT_PROFILE:
        return {"kind": "default", "value": "", "read": True,
                "words": "every device nothing before it covers"}
    kind, _, value = name.partition(":")
    if kind == "role" and value and value not in ROLE_KINDS:
        return {"kind": "", "value": "", "read": False, "words": (
            f"nothing: role:{value} names no kind Mercury has ({', '.join(ROLE_KINDS)}); a "
            "role profile is by the NetBox role's mercury_kind, so no device is given this "
            "login")}
    if kind in ("platform", "role", "site") and value:
        return {"kind": kind, "value": value, "read": True,
                "words": {"platform": f"every device on the platform {value}",
                          "role": f"every {value} (its NetBox role has mercury_kind {value})",
                          "site": f"every device at the site {value}"}[kind]}
    return {"kind": "", "value": "", "read": False, "words": (
        "nothing: the resolver reads only platform:<slug>, role:<kind>, site:<site> and "
        "default, so no device is given this login")}


def view() -> dict:
    """The tab: ``{"state": "absent"|"unreadable"|"ok", "rows", "error"}``, rows in the
    resolver's order (platform, role, site, default, then names it never reads)."""
    from modules import credentials

    path = credentials._FILE
    if not os.path.exists(path):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            json.load(fh)
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [], "error": (
            f"{os.path.basename(path)} could not be read ({type(exc).__name__}): every save "
            "is refused until it is repaired, and the damaged file is kept beside it")}
    import time

    order = {"platform": 0, "role": 1, "site": 2, "default": 3, "": 4}
    # `last_rotated` is when the password was last set (the store stamps it on a save that
    # carries one); drawn as an ISO time.
    rows = [dict(p, covers=covers(p["name"]), last_set=time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(p["last_rotated"]))
                if isinstance(p.get("last_rotated"), (int, float)) else "")
            for p in credentials.list_profiles()]
    rows.sort(key=lambda r: (order[r["covers"]["kind"]], r["name"]))
    return {"state": "ok", "rows": rows, "error": ""}


def save(kind: str, value: str, username: str, password: str, secret: str, *, actor: str,
         verified: str, editing: str = "") -> dict:
    """Create or change one profile, then record it: ``{"ok", "error", "profile", "fields",
    "recorded"}``. A new profile needs its username and password; an edit keeps any field
    left empty (the store's own rule)."""
    from modules import credential_changes, credentials

    name, problem = (editing, "") if editing else name_of(kind, value)
    if problem:
        return {"ok": False, "error": problem}
    existing = {p["name"]: p for p in credentials.list_profiles()}.get(name)
    if editing and existing is None:
        return {"ok": False, "error": f"no profile is named {editing!r} any more: nothing "
                                      "was saved"}
    if not editing and existing is not None:
        return {"ok": False, "error": f"a profile named {name} exists: edit it from its row; "
                                      "nothing was saved"}
    username = (username or "").strip()
    if not editing and not (username and password):
        return {"ok": False, "error": "a new profile needs its username and its password: the "
                                      "resolver gives no device a login without both"}
    fields = [f for f, v in (("username", username if (not existing or username !=
                                                       existing.get("username")) else ""),
                             ("password", password), ("secret", secret)) if v]
    if not fields:
        return {"ok": False, "error": "nothing was changed: every field was left as it is"}
    try:
        credentials.save_profile(name, username=username, password=password or "",
                                 secret=secret or "")
    except Exception as exc:                          # noqa: BLE001 (the store's refusal)
        log.exception("credential_profiles_page: %s was not saved", name)
        return {"ok": False, "error": f"the store refused it, nothing was saved: {exc}"}
    rec = credential_changes.record(action="saved", profile=name, fields=fields, actor=actor,
                                    verified=verified)
    return {"ok": True, "error": "", "profile": name, "fields": fields,
            "recorded": rec["ok"], "record_error": rec["error"]}


def delete(name: str, *, actor: str, verified: str) -> dict:
    """Delete one profile, then record it."""
    from modules import credential_changes, credentials

    if name not in {p["name"] for p in credentials.list_profiles()}:
        return {"ok": False, "error": f"no profile is named {name!r}: nothing was deleted"}
    try:
        credentials.delete_profile(name)
    except Exception as exc:                          # noqa: BLE001 (the store's refusal)
        log.exception("credential_profiles_page: %s was not deleted", name)
        return {"ok": False, "error": f"the store refused it, nothing was deleted: {exc}"}
    rec = credential_changes.record(action="deleted", profile=name, fields=[], actor=actor,
                                    verified=verified)
    return {"ok": True, "error": "", "profile": name, "recorded": rec["ok"],
            "record_error": rec["error"]}
