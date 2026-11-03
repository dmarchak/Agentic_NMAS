"""The teams store: who receives notifications (docs/HEAL_TO_INTENT.md section 10).

A team is a named group with its own destinations: several email recipients and several
webhooks. **Every destination is verified by a code before use, and each is enabled on its
own**: a destination is sent incident events only while it is both verified and enabled.
Enabling an unverified destination is refused, naming it.

One file for the installation, ``notify_teams.json`` in the data folder, read-modify-written
under its cross-process lock and replaced atomically (0600); an unreadable store refuses
writes (`filestore.read_json_for_write`). A webhook's signing secret is never in it: the
destination holds its reference (``webhook/<id>``) and the credential store holds the value
(`credentials.set_notify_secret`). A verification code is never stored, only its salted
hash, its expiry and the tries left.
"""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time

from modules import filestore

log = logging.getLogger(__name__)

#: How long a verification code answers: 15 minutes, a mailbox's or a receiver's round trip
#: with room for a person to read it, as sign-up codes are commonly bounded.
CODE_TTL_S = 15 * 60
#: Wrong codes before the code is spent and a new one must be sent.
CODE_TRIES = 5
#: A code's digits: six, typed from the message.
CODE_DIGITS = 6
CHANNELS = ("email", "webhook")
#: Webhook formats built. Slack's, Teams' and PagerDuty's are deferred to after Lab 10, not cut
#: (C2387, the operator, 2026-11-03): built early if H8 or H9 finish early.
FORMATS = ("generic",)
_NAME = re.compile(r"[^\x00-\x1f\x7f]{1,60}")


class Refused(ValueError):
    """A change the store will not make, and why."""


def _path() -> str:
    from modules import config
    return os.path.join(config.DATA_DIR, "notify_teams.json")


_lock = filestore.PathLock(_path)


def _now_iso(now=None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now))


def read() -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "teams", "error"}``: absent and unreadable are
    different answers, and neither is an empty store said as one."""
    path = _path()
    if not os.path.exists(path):
        return {"state": "absent", "teams": {}, "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "teams": {}, "error": f"{type(exc).__name__}: {exc}"}
    return {"state": "ok", "teams": dict(data.get("teams") or {}), "error": ""}


def _write(change):
    """Read the store for a write (unreadable refuses), apply *change*, replace it."""
    with _lock:
        data = filestore.read_json_for_write(_path(), empty={"teams": {}})
        data.setdefault("teams", {})
        out = change(data["teams"])
        filestore.write_atomic(_path(), json.dumps(data, indent=1, sort_keys=True))
    return out


def _team(teams: dict, team_id: str) -> dict:
    team = teams.get(team_id)
    if team is None:
        raise Refused(f"no team {team_id!r}: the teams are {', '.join(sorted(teams)) or 'none'}")
    return team


def _dest(team: dict, dest_id: str) -> dict:
    dest = (team.get("destinations") or {}).get(dest_id)
    if dest is None:
        raise Refused(f"no destination {dest_id!r} in team {team.get('name')!r}")
    return dest


def add_team(name: str, *, by: str, now=None) -> dict:
    """A new team named *name* (unique, ignoring case). ``{"ok", "team"}``."""
    name = (name or "").strip()
    if not _NAME.fullmatch(name):
        raise Refused("a team's name is 1 to 60 characters on one line")
    if not by:
        raise Refused("a team names the person who made it")
    team_id = secrets.token_hex(6)

    def change(teams):
        if any((t.get("name") or "").lower() == name.lower() for t in teams.values()):
            raise Refused(f"a team named {name!r} exists")
        teams[team_id] = {"name": name, "created_by": by, "created_at": _now_iso(now),
                          "destinations": {}}
    _write(change)
    log.info("notify: team %s (%s) made by %s", team_id, name, by)
    return {"ok": True, "team": team_id}


def add_email(team_id: str, address: str, *, by: str, now=None) -> dict:
    """A recipient for *team_id*, added unverified and off. ``{"ok", "destination"}``."""
    from modules.notify import addresses
    try:
        address = addresses.check_email(address)
    except ValueError as exc:
        raise Refused(str(exc)) from exc
    return _add(team_id, {"channel": "email", "address": address}, by=by, now=now,
                same=lambda d: d.get("address", "").lower() == address.lower())


def add_webhook(team_id: str, url: str, secret: str, *, by: str, fmt: str = "generic",
                now=None) -> dict:
    """A webhook for *team_id*, added unverified and off; its signing *secret*, typed by a
    person, goes to the credential store and only its reference is kept here. A store write
    that fails takes the secret back out. ``{"ok", "destination"}``."""
    from modules import credentials
    from modules.notify import addresses
    if fmt not in FORMATS:
        raise Refused(f"the webhook format {fmt!r} is not one built: {', '.join(FORMATS)} "
                      "(Slack's, Teams' and PagerDuty's are later work, after Lab 10: C2387)")
    try:
        url = addresses.check_webhook_url(url)
    except ValueError as exc:
        raise Refused(str(exc)) from exc
    if not secret or len(secret) < 16:
        raise Refused("a webhook's signing secret is at least 16 characters, typed by a person")
    dest_id = secrets.token_hex(6)
    ref = f"webhook/{dest_id}"
    credentials.set_notify_secret(ref, secret)
    try:
        return _add(team_id, {"channel": "webhook", "url": url, "format": fmt,
                              "secret_ref": ref}, by=by, now=now, dest_id=dest_id,
                    same=lambda d: d.get("url") == url)
    except BaseException:
        credentials.clear_notify_secret(ref)
        raise


def _add(team_id, fields, *, by, now, same, dest_id=None) -> dict:
    if not by:
        raise Refused("a destination names the person who added it")
    dest_id = dest_id or secrets.token_hex(6)

    def change(teams):
        team = _team(teams, team_id)
        dests = team.setdefault("destinations", {})
        if any(same(d) for d in dests.values()):
            raise Refused(f"team {team.get('name')!r} already has that destination")
        dests[dest_id] = dict(fields, enabled=False, verified_at=None, verified_by="",
                              added_by=by, added_at=_now_iso(now))
    _write(change)
    log.info("notify: %s destination %s added to team %s by %s", fields["channel"], dest_id,
             team_id, by)
    return {"ok": True, "destination": dest_id}


def remove_destination(team_id: str, dest_id: str, *, by: str) -> dict:
    """Remove a destination; a webhook's secret leaves the credential store with it. Its
    delivery log rows stay (the record of what was sent is never rewritten)."""
    from modules import credentials

    def change(teams):
        team = _team(teams, team_id)
        dest = _dest(team, dest_id)
        del team["destinations"][dest_id]
        return dest
    dest = _write(change)
    if dest.get("secret_ref"):
        credentials.clear_notify_secret(dest["secret_ref"])
    log.info("notify: destination %s removed from team %s by %s", dest_id, team_id, by)
    return {"ok": True}


def set_enabled(team_id: str, dest_id: str, enabled: bool, *, by: str) -> dict:
    """Turn one destination on or off. On is refused until it is verified."""
    def change(teams):
        dest = _dest(_team(teams, team_id), dest_id)
        if enabled and not dest.get("verified_at"):
            raise Refused(f"destination {dest_id} is not verified: send it a code and type the "
                          "code back before turning it on")
        dest["enabled"] = bool(enabled)
        dest["enabled_by"], dest["enabled_at"] = by, _now_iso()
    _write(change)
    log.info("notify: destination %s turned %s by %s", dest_id, "on" if enabled else "off", by)
    return {"ok": True, "enabled": bool(enabled)}


def _code_hash(salt: str, code: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


def issue_code(team_id: str, dest_id: str, *, by: str, now=None) -> str:
    """A new verification code for one destination: its salted hash, expiry and tries are
    kept, and the code itself is returned to the one caller that sends it
    (`delivery.send_code`), never stored, logged or drawn. A new code replaces the last."""
    now = time.time() if now is None else now
    code = "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))
    salt = secrets.token_hex(8)

    def change(teams):
        dest = _dest(_team(teams, team_id), dest_id)
        dest["code"] = {"salt": salt, "hash": _code_hash(salt, code), "expires": now + CODE_TTL_S,
                        "tries": CODE_TRIES, "by": by, "at": _now_iso(now)}
    _write(change)
    log.info("notify: a verification code issued for destination %s by %s", dest_id, by)
    return code


def confirm_code(team_id: str, dest_id: str, code: str, *, by: str, now=None) -> dict:
    """Check a typed code: right and in time verifies the destination (who and when kept) and
    spends the code; wrong spends a try; expired or out of tries refuses, naming which."""
    now = time.time() if now is None else now
    typed = re.sub(r"\s", "", str(code or ""))

    def change(teams):
        dest = _dest(_team(teams, team_id), dest_id)
        held = dest.get("code")
        if not held:
            return {"ok": False, "error": "no code is waiting for this destination: send one"}
        if now > float(held.get("expires") or 0):
            dest.pop("code", None)
            return {"ok": False, "error": (f"the code expired at {_now_iso(held['expires'])} "
                                           f"(now {_now_iso(now)}): send a new one")}
        if hmac.compare_digest(_code_hash(held["salt"], typed), held["hash"]):
            dest.pop("code", None)
            dest["verified_at"], dest["verified_by"] = _now_iso(now), by
            return {"ok": True, "verified_at": dest["verified_at"]}
        held["tries"] = int(held.get("tries") or 0) - 1
        if held["tries"] <= 0:
            dest.pop("code", None)
            return {"ok": False, "error": "the code was wrong, and no tries are left: send a "
                                          "new one"}
        return {"ok": False, "error": f"the code was wrong: {held['tries']} tries left"}
    out = _write(change)
    log.info("notify: destination %s verification by %s: %s", dest_id, by,
             "verified" if out["ok"] else "refused")
    return out


def note_outcome(team_id: str, dest_id: str, last: dict) -> None:
    """Keep a delivery's final outcome on its destination (``last``): the summary Needs
    attention reads, one per destination, so a failure stays raised however old it is and
    however long the log grows. The delivery log stays the record. A destination removed
    meanwhile is left removed; a store that cannot be written is logged, never raised (the
    send it summarises has happened)."""
    def change(teams):
        dest = ((teams.get(team_id) or {}).get("destinations") or {}).get(dest_id)
        if dest is not None:
            dest["last"] = dict(last)
    try:
        _write(change)
    except (OSError, filestore.StoreUnreadable) as exc:
        log.error("notify: the outcome of delivery %s could not be kept on destination %s "
                  "(%s)", last.get("delivery"), dest_id, exc)


def failing() -> dict:
    """``{"state", "rows", "error"}``: each destination that is ON and whose last delivery
    failed or was refused, with its team. Off or removed destinations raise nothing: a
    failure there is read in place, where it was tried."""
    got = read()
    rows = []
    for team_id, team in sorted(got["teams"].items()):
        for dest_id, dest in sorted((team.get("destinations") or {}).items()):
            last = dest.get("last") or {}
            if dest.get("enabled") and last.get("outcome") in ("failed", "refused"):
                rows.append({"team": team_id, "team_name": team.get("name", ""),
                             "destination": dest_id, "dest": dest, "last": last})
    return {"state": got["state"], "rows": rows, "error": got["error"]}


def public(dest: dict) -> dict:
    """A destination as a page may draw it: never its code's hash, and its secret as set or
    not (`credentials.notify_secret_set`), never a value."""
    from modules import credentials
    out = {k: v for k, v in dest.items() if k not in ("code", "secret_ref")}
    out["code_waiting"] = bool(dest.get("code"))
    if dest.get("secret_ref"):
        out["secret_set"] = credentials.notify_secret_set(dest["secret_ref"])
    return out


def deliverable(team_ids) -> list:
    """``[(team_id, team_name, dest_id, dest)]`` for the named teams' destinations that are
    verified AND enabled, in a stable order. A team named that does not exist is skipped and
    logged: who receives is the caller's policy, and a removed team receives nothing."""
    got = read()
    if got["state"] == "unreadable":
        raise filestore.StoreUnreadable(f"the teams store could not be read: {got['error']}")
    out = []
    for team_id in team_ids or ():
        team = got["teams"].get(team_id)
        if team is None:
            log.warning("notify: team %s is named and does not exist; nothing sent to it",
                        team_id)
            continue
        for dest_id, dest in sorted((team.get("destinations") or {}).items()):
            if dest.get("enabled") and dest.get("verified_at"):
                out.append((team_id, team.get("name", ""), dest_id, dest))
    return out
