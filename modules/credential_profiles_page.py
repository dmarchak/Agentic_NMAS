"""modules/credential_profiles_page.py — Source of truth › Credentials › Profiles on v2 (the board
drawn 2026-10-10 under the Phase 7 mode; CUTOVER's "Credential profiles", whose JSON routes no
screen called).

A credential profile is a login the resolver (`credentials.resolve`) gives a device a NetBox
inventory brings in with no login of its own: after the device's own override and its network's
credential list, a profile named ``role:<role>``, then ``site:<site>``, then ``default``. Any
other name is stored and read by NOTHING, and the tab says so rather than letting it look like
it works. No value is ever returned: a password is "set" or "not set".

Saving and deleting go through `credentials.save_profile` and `delete_profile`, the store's one
write path, and each is recorded (`credential_changes`): who, which profile, which fields.
"""

import json
import logging
import os

log = logging.getLogger(__name__)

#: What a profile name covers, in the resolver's order after a device's own login.
KINDS = (("role", "every device with the role"), ("site", "every device at the site"),
         ("default", "every device nothing before it covers"))


def name_of(kind: str, value: str) -> tuple:
    """``(name, problem)``: the profile name the resolver reads for *kind* and *value*."""
    value = (value or "").strip()
    if kind == "default":
        return "default", ""
    if kind not in ("role", "site"):
        return "", f"a profile covers a role, a site or every device (default), not {kind!r}"
    if not value or any(c.isspace() for c in value) or ":" in value:
        return "", f"name the {kind} it covers as one word, as NetBox names it (got {value!r})"
    return f"{kind}:{value}", ""


def covers(name: str) -> dict:
    """``{"kind", "value", "words", "read"}``: what the resolver reads *name* for."""
    from modules.credentials import DEFAULT_PROFILE

    if name == DEFAULT_PROFILE:
        return {"kind": "default", "value": "", "read": True,
                "words": "every device nothing before it covers"}
    kind, _, value = name.partition(":")
    if kind in ("role", "site") and value:
        return {"kind": kind, "value": value, "read": True,
                "words": f"every device with the role {value}" if kind == "role" else
                         f"every device at the site {value}"}
    return {"kind": "", "value": "", "read": False, "words": (
        "nothing: the resolver reads only role:<role>, site:<site> and default, so no device "
        "is given this login")}


def view() -> dict:
    """The tab: ``{"state": "absent"|"unreadable"|"ok", "rows", "error"}``, rows in the
    resolver's order (role, site, default, then names it never reads)."""
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

    order = {"role": 0, "site": 1, "default": 2, "": 3}
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
