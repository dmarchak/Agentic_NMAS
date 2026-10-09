"""Settings › Installation (board F, approved 2026-10-05; its records database card, board F2,
approved 2026-10-09): the settings that are the installation's own, for every network, never a
network's or Default's.

Built so far: the Connections tab's **Records database** card (F2). Its three conditions, the
operator's (2026-10-09):

1. **Save and Test work with the database down or the password wrong.** Save writes the
   installation's settings file and appends to the installation's settings record, a FILE, as
   the verified person; it never opens the database it configures. Test asks the database and
   says what it answered, a failure included.
2. **Test checks what host step 6a made and names the check that failed**
   (`records_db.TEST_STEPS`); the rest are "not tried".
3. **The card states the rotation order**: the server first (`scripts/host-steps/
   postgres-rotate.sh`), then Replace here, then Test.

The card is drawn from :func:`records_card`; the last Test's answer is kept (who, when, each
check) so it is readable later, and a Save or Replace after it says the Test is out of date.
"""

import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

#: The page's tabs (board F), in order. Connections is built; the rest are on today's Settings
#: page until drawn here.
TABS = (("connections", "Connections"), ("access", "Access and identity"),
        ("platforms", "Platforms and roles"), ("server", "Server"),
        ("ai", "AI and workflow"), ("diagnostics", "Diagnostics"))
BUILT_TABS = ("connections",)
#: The records database card's fields, in the card's order (the password is a secret, drawn
#: as set or unset and changed only by Replace…).
FIELDS = ("records_db_host", "records_db_port", "records_db_name", "records_db_user")
SECRET = "records_db_password"
#: Save's steps, in order: the manual's How it works page names each.
SAVE_STEPS = ("check", "write", "record")
#: Replace's steps: the new password checked, stored as a secret, recorded, then the Test.
REPLACE_STEPS = ("check", "store", "record", "test")
#: The password rule host step 6a and postgres-rotate.sh enforce on the server, so Mercury's
#: copy can only be one the server could have been given.
PASSWORD_RULE = re.compile(r"[A-Za-z0-9._~-]{24,}")
PASSWORD_WORDS = "letters, digits and . _ ~ - only, 24 characters or more"
#: The installation's settings record and the last Test's answer: owner-only files in data/.
RECORD = "settings_record.jsonl"
LAST_TEST = "records_db_test.json"


class Refused(ValueError):
    """Nothing was saved; the message names the field and why."""


def _now() -> float:
    return time.time()


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch))) if epoch else ""


def _path(name: str) -> str:
    from modules.config import DATA_DIR

    return os.path.join(DATA_DIR, name)


def _record(entry: dict) -> dict:
    """Append *entry* to the installation's settings record, owner-only. What it records is
    already done when this runs: a record that cannot be written says so."""
    from modules.config import open_secure
    from modules.inventory_edit import actor_label

    now = _now()
    entry = dict(entry, at=now, at_iso=_iso(now), scope="installation",
                 actor_label=actor_label(entry.get("actor", ""),
                                         entry.get("actor_verified", "")))
    try:
        with open_secure(_path(RECORD), "a") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        entry["recorded"] = True
    except OSError as exc:
        log.error("installation settings: %s done and NOT recorded: %s", entry.get("kind"), exc)
        entry.update(recorded=False, record_error=f"{type(exc).__name__}: {exc}")
    return entry


def changes(kinds=None) -> dict:
    """The installation's recorded changes, newest first. ``state``: ``absent`` (none yet),
    ``ok``, or ``unreadable`` (never read as none)."""
    p = _path(RECORD)
    if not os.path.exists(p):
        return {"state": "absent", "rows": []}
    try:
        with open(p, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [], "error": f"{type(exc).__name__}: {exc}"}
    rows = [r for r in rows if kinds is None or r.get("kind") in kinds]
    return {"state": "ok", "rows": list(reversed(rows))}


def last_test() -> dict:
    """The last Test's answer: ``{"state": "absent"|"ok"|"unreadable", ...}`` with ``at``,
    ``actor_label``, ``ok``, ``steps`` and ``error`` when there is one."""
    p = _path(LAST_TEST)
    if not os.path.exists(p):
        return {"state": "absent"}
    try:
        with open(p, encoding="utf-8") as fh:
            return dict(json.load(fh), state="ok")
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "error": f"{type(exc).__name__}: {exc}"}


def _steps_drawn(result: dict) -> list:
    """Every TEST_STEPS check, in order: passed or failed with its detail, or not tried."""
    from modules import records_db as RD

    got = {s["name"]: s for s in result.get("steps") or []}
    out = []
    for name in RD.TEST_STEPS:
        s = got.get(name)
        out.append({"name": name, "words": RD.STEP_WORDS[name],
                    "state": "not_tried" if s is None else ("pass" if s["ok"] else "fail"),
                    "detail": (s or {}).get("detail", "")})
    return out


def records_card() -> dict:
    """The Records database card (board F2). ``state``: ``off`` (no host: every store on its
    files), ``untested`` (configured, never tested), ``answering`` (the last Test passed),
    ``failing`` (it failed); ``stale`` when a Save or Replace came after that Test."""
    from modules import records_db as RD

    c = RD.config()
    answer = last_test()
    saved = changes(kinds=("records_db_save", "records_db_replace"))
    last_change = (saved["rows"] or [{}])[0].get("at", 0) if saved["state"] == "ok" else 0
    if not c["host"]:
        state = "off"
    elif answer["state"] != "ok":
        state = "untested"
    else:
        state = "answering" if answer.get("ok") else "failing"
    stale = state in ("answering", "failing") and last_change > answer.get("at", 0)
    version = next((s["detail"] for s in answer.get("steps") or []
                    if s["name"] == "version" and s["ok"]), "")
    # Off: no Test is drawn, an old one included (its checks would read as today's).
    return {"state": state, "stale": stale, "config": c, "test": answer,
            "steps": _steps_drawn(answer) if answer["state"] == "ok" and state != "off" else [],
            "version": version, "stores": list(RD.STORES),
            "test_unreadable": answer["state"] == "unreadable",
            "record_unreadable": saved["state"] == "unreadable",
            "rule_words": PASSWORD_WORDS}


def _typed(form: dict) -> dict:
    """The card's fields as the schema types them, refusing (naming the field) a value that is
    not one. An empty host is "off": every store on its files."""
    out = {}
    host = (form.get("records_db_host") or "").strip()
    if host and not re.fullmatch(r"[A-Za-z0-9.:_-]+", host):
        raise Refused(f"Host {host!r} is not a host name or address")
    out["records_db_host"] = host
    raw_port = (form.get("records_db_port") or "").strip() or "5433"
    if not raw_port.isdigit() or not 1 <= int(raw_port) <= 65535:
        raise Refused(f"Port {raw_port!r} is not a port number (1 to 65535)")
    out["records_db_port"] = int(raw_port)
    for key, label in (("records_db_name", "Database"), ("records_db_user", "Role")):
        value = (form.get(key) or "").strip()
        if host and not value:
            raise Refused(f"{label} is empty: with a host set, Mercury needs it to sign in")
        if value and not re.fullmatch(r"[A-Za-z0-9_]+", value):
            raise Refused(f"{label} {value!r} is not a PostgreSQL name (letters, digits, _)")
        out[key] = value or ("mercury")
    return out


def save(form: dict, actor: str, verified: str) -> dict:
    """Save the card's fields (SAVE_STEPS): check them, write what changed to the installation's
    settings, record who and which fields. Never opens the database, so it works with it down.
    ``{"ok", "written", "nothing", "recorded", ...}``; raises `Refused` naming the field."""
    from modules import records_db as RD
    from modules.settings_schema import write_settings

    values = _typed(form)                                                     # check
    c = RD.config()
    stored = {"records_db_host": c["host"], "records_db_port": c["port"],
              "records_db_name": c["name"], "records_db_user": c["user"]}
    changed = {k: v for k, v in values.items() if stored[k] != v}
    if not changed:
        return {"ok": True, "nothing": True, "written": [], "recorded": True}
    out = write_settings(changed, actor=actor)                                # write
    if not out["ok"]:
        raise Refused(out["error"])
    entry = _record({"kind": "records_db_save", "actor": actor, "actor_verified": verified,
                     "fields": sorted(changed)})                              # record
    return dict(entry, ok=True, nothing=False, written=sorted(changed))


def replace_password(new: str, actor: str, verified: str, tester=None) -> dict:
    """Replace Mercury's copy of the role's password (REPLACE_STEPS), then Test it. The server
    is changed first, by postgres-rotate.sh; this stores the same password as a secret and
    proves both sides agree. Raises `Refused` for a password the server could not have been
    given; never returns or records the value."""
    from modules.secrets_store import set_secret

    if not PASSWORD_RULE.fullmatch(new or ""):                                # check
        raise Refused(f"The new password must be {PASSWORD_WORDS} (the rule host step 6a "
                      f"and postgres-rotate.sh use); it was {len(new or '')} characters")
    if not set_secret(SECRET, new):                                           # store
        raise Refused("the secrets store refused the new password; nothing was replaced")
    entry = _record({"kind": "records_db_replace", "actor": actor, "actor_verified": verified,
                     "fields": [SECRET]})                                     # record
    return dict(entry, ok=True, tested=test(actor, verified, tester))         # test


def test(actor: str, verified: str, tester=None) -> dict:
    """Run the Test (records_db.test_connection) and keep its answer: who, when, each check.
    The database's own answer, a failure included; the settings are not changed."""
    from modules import records_db as RD
    from modules.config import open_secure
    from modules.inventory_edit import actor_label

    result = (tester or RD.test_connection)()
    now = _now()
    kept = {"at": now, "at_iso": _iso(now), "actor_label": actor_label(actor, verified),
            "ok": result["ok"],
            "steps": result.get("steps") or [], "error": result.get("error", "")}
    try:
        tmp = _path(LAST_TEST) + ".new"
        with open_secure(tmp, "w") as fh:
            json.dump(kept, fh, sort_keys=True)
        os.replace(tmp, _path(LAST_TEST))
        kept["kept"] = True
    except OSError as exc:
        log.error("installation settings: the records database Test's answer was not kept: %s",
                  exc)
        kept.update(kept=False, keep_error=f"{type(exc).__name__}: {exc}")
    return kept
