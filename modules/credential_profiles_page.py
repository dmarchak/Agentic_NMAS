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
    settings, never NetBox: a page read, no per-device work but one pass over each list.

    And, for the form's picker (C2984, `scope_options`), what a person knows each by:
    ``platform_names`` and ``site_names`` (NetBox's own name for a slug, where a loaded device
    carries it) and ``platform_devices`` and ``site_devices`` (how many loaded NetBox devices
    are on it), counted in the same pass."""
    from modules import inventory
    from modules.inventory.role_kind import KINDS as ROLE_KINDS
    from modules.nsot import listref
    from modules.settings_schema import DEFAULTS, get_setting

    roles = {k: set() for k in ROLE_KINDS}
    sites = set()
    names = {"_platform": {}, "_site": {}}
    devices = {"_platform": {}, "_site": {}}
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
            for key in ("_platform", "_site"):
                slug = d.get(key)
                if slug:
                    devices[key][slug] = devices[key].get(slug, 0) + 1
                    if d.get(f"{key}_name"):
                        names[key].setdefault(slug, str(d[f"{key}_name"]))
    platforms = sorted(get_setting("platform_map", DEFAULTS["platform_map"]) or {})
    return {"kinds": {k: sorted(v) for k, v in roles.items()}, "platforms": platforms,
            "sites": sorted(sites),
            "platform_names": names["_platform"], "site_names": names["_site"],
            "platform_devices": devices["_platform"], "site_devices": devices["_site"]}


def scope_options(known: dict = None) -> dict:
    """The form's choices for "The platform or site" (C2984; the charter's "What Mercury knows
    is chosen, never typed"): ``{"platforms": [...], "sites": [...]}``, each ``{"slug",
    "name", "devices"}``: exactly the slugs `name_of` accepts (the platform map's; the sites
    of the loaded NetBox devices), each with NetBox's name for it where a loaded device
    carries one and how many loaded NetBox devices are on it. No value outside these lists is
    accepted, so the field is a plain selection, never a combo box."""
    known = exists() if known is None else known

    def rows(slugs, names, counts):
        # A name that is the slug again adds nothing: the slug is drawn once.
        return [{"slug": s, "name": n if n != s else "",
                 "devices": (counts or {}).get(s, 0)}
                for s in slugs for n in [(names or {}).get(s, "")]]
    return {"platforms": rows(known["platforms"], known.get("platform_names"),
                              known.get("platform_devices")),
            "sites": rows(known["sites"], known.get("site_names"), known.get("site_devices"))}


def choices(known: dict = None) -> list:
    """The form's ``(value, words)`` choices: a platform, one per kind (naming the NetBox
    roles it covers now), a site, every device."""
    known = exists() if known is None else known
    out = [("platform", "every device on a platform (chosen below)")]
    for kind, slugs in known["kinds"].items():
        held = (f"NetBox roles now: {', '.join(slugs)}" if slugs else
                "no loaded NetBox device has it yet")
        out.append((f"role:{kind}",
                    f"every {kind} (its NetBox role has mercury_kind {kind}; {held})"))
    out.append(("site", "every device at a site (chosen below)"))
    out.append(("default", "every device nothing before it covers (default)"))
    return out


def name_of(kind: str, value: str, known: dict = None) -> tuple:
    """``(name, problem)``: the profile name the resolver reads for *kind* and *value*, or why
    no device could ever be given it. *kind* is ``platform``, ``site``, ``default``, ``role``
    (its *value* a kind) or ``role:<kind>`` (the form's choice)."""
    from modules.inventory.role_kind import KINDS as ROLE_KINDS

    value = (value or "").strip()
    # A scope that takes no platform or site, given one (C2984: the form's second choice left
    # at something): refused naming both, never saved as though the choice had narrowed it.
    whole = "the default profile" if kind == "default" else (
        f"a profile for every {kind.partition(':')[2]}" if kind.startswith("role:") else "")
    if whole and value:
        return "", (f"{whole} covers its devices on every platform and at every site, and "
                    f"{value!r} was chosen as its platform or site: choose none, or choose a "
                    "platform or a site as what the profile covers")
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


# ---------------------------------------------------------------- the read-only account (H28)

#: What the read-only account may run, as the card says it (board H, artboard N). Its
#: device-side shape is not measured yet (an IOS and an IOS-XE device), so the card says that.
READ_RUNS = ("the AI read set's show commands and bounded ping and traceroute, at a low "
             "privilege level; its device-side shape (a privilege level or a CLI view) is "
             "measured on an IOS and an IOS-XE device before any device holds it")
READ_USED_BY = ("the AI analysis's reads (required: a device without one is refused by name); "
                "diagnosis, collection and drift reads may move to it later")


def _read_rows(name: str) -> list:
    """*name*'s devices as the AI's reads load them, identity fields only (no credential): a
    NetBox list's loaded rows (`inventory.loaded_rows`), a local list's devices file through
    the reads engine's own path (`listref.resolve(...).csv_path`, `load_saved_devices`). A
    local inventory's devices carry their deploy login in the file, but their read-only
    account comes from the profiles all the same (`credentials.resolve_read` on their kind,
    then default), so they are counted (the operator's walk, 2026-11-07: "resolves for 0")."""
    from modules import inventory
    from modules.inventory.source_config import is_netbox_sourced
    from modules.nsot import listref

    if is_netbox_sourced(name):
        return inventory.loaded_rows(name)
    from modules.device import load_saved_devices
    return [{k: v for k, v in d.items() if k not in ("username", "password", "secret")}
            for d in load_saved_devices(listref.resolve(name).csv_path) if isinstance(d, dict)]


def read_coverage(accounts: dict = None) -> dict:
    """Which devices each profile's read-only account resolves for: ``{"total",
    "by_profile": {profile: count}, "none": count, "none_names": [up to 10]}``. From every
    network's devices (`_read_rows`: one pass over each list's rows, NetBox or local) and the
    store's names, never a value and never a device; each device's chain is the one
    `reads.read_account_for` resolves on (its platform, kind and site, then default)."""
    from modules import credentials
    from modules.nsot import listref

    accounts = credentials.read_accounts() if accounts is None else accounts
    by, none, names, total = {}, 0, [], 0
    for name in sorted(listref._registry()):
        try:
            rows = _read_rows(name)
        except Exception as exc:                      # noqa: BLE001 - that list adds nothing
            log.warning("credential_profiles_page: %s's inventory was not read: %s", name, exc)
            continue
        for d in rows:
            total += 1
            chain = credentials.read_chain(d.get("role", ""), d.get("_site", ""),
                                           d.get("_platform", ""))
            hit = next((p for p in chain if (accounts.get(p) or {}).get("password_set")), "")
            if hit:
                by[hit] = by.get(hit, 0) + 1
            else:
                none += 1
                if len(names) < 10:
                    names.append(d.get("hostname") or "?")
    return {"total": total, "by_profile": by, "none": none, "none_names": names}


def read_view() -> dict:
    """The Read-only account card: ``{"state", "rows", "coverage", "error"}``, one row per
    profile in the resolver's order, each with its deploy account's name and its read-only
    account (name, set when and by whom, never a value)."""
    import time

    from modules import credentials

    v = view()
    said = {"runs": READ_RUNS, "used_by": READ_USED_BY}
    if v["state"] != "ok":
        return dict(said, state=v["state"], rows=[], coverage={}, error=v["error"])
    accounts = credentials.read_accounts()
    cov = read_coverage(accounts)
    rows = []
    for p in v["rows"]:
        a = accounts.get(p["name"]) or {}
        read = {}
        if a:
            at = a.get("set_at")
            read = {"username": a["username"], "set_by": a.get("set_by", ""),
                    "set_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at))
                    if isinstance(at, (int, float)) else ""}
        rows.append({"name": p["name"], "deploy_username": p["username"], "read": read,
                     "resolves": cov["by_profile"].get(p["name"], 0)})
    # The card draws the counts and the names; which profile each device took is per row.
    shown = {"total": cov["total"], "none": cov["none"], "none_names": cov["none_names"]}
    return dict(said, state="ok", rows=rows, coverage=shown, error="")


def save_read(profile: str, username: str, password: str, *, actor: str,
              verified: str) -> dict:
    """Set *profile*'s read-only account (its name once, its password each time) as the
    verified person, then record it: ``{"ok", "error", "profile", "username", "replaced",
    "recorded", "record_error"}``. The password is never returned."""
    from modules import credential_changes, credentials

    try:
        got = credentials.set_read_account(profile, username, password, actor=actor,
                                           verified=verified)
    except credentials.ReadAccountRefused as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:                          # noqa: BLE001 (the store's refusal)
        log.exception("credential_profiles_page: %s's read-only account was not saved", profile)
        return {"ok": False, "error": f"the store refused it, nothing was saved: {exc}"}
    rec = credential_changes.record(
        action="read_account_replaced" if got["replaced"] else "read_account_added",
        profile=got["profile"],
        fields=(["read-only account password"] if got["replaced"] else
                ["read-only account name", "read-only account password"]),
        actor=actor, verified=verified)
    return {"ok": True, "error": "", "profile": got["profile"], "username": got["username"],
            "replaced": got["replaced"], "recorded": rec["ok"], "record_error": rec["error"]}


def delete(name: str, *, actor: str, verified: str) -> dict:
    """Delete one profile, then record it."""
    from modules import credential_changes, credentials

    if name not in {p["name"] for p in credentials.list_profiles()}:
        return {"ok": False, "error": f"no profile is named {name!r}: nothing was deleted"}
    try:
        got = credentials.delete_profile(name)
    except Exception as exc:                          # noqa: BLE001 (the store's refusal)
        log.exception("credential_profiles_page: %s was not deleted", name)
        return {"ok": False, "error": f"the store refused it, nothing was deleted: {exc}"}
    rec = credential_changes.record(action="deleted", profile=name, fields=[], actor=actor,
                                    verified=verified)
    return {"ok": True, "error": "", "profile": name, "recorded": rec["ok"],
            "record_error": rec["error"],
            "read_account_removed": bool((got or {}).get("read_account_removed"))}
