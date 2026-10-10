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

Board F3 (signed off 2026-10-09) adds the NetBox connection, Proxmox and Commit author cards on
Connections and the Server card on its own tab, every setting a control: :data:`CARDS`, drawn
by :func:`card`, saved by :func:`save_card`, tested by :func:`test_card`, their tokens replaced
by :func:`replace_secret`, and NetBox's master switch turned off by :func:`netbox_writes_off`.
"""

import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

#: The page's tabs (board F), in order. Connections and Server are built (F2, F3); the rest are
#: on today's Settings page until drawn here.
TABS = (("connections", "Connections"), ("access", "Access and identity"),
        ("platforms", "Platforms and roles"), ("server", "Server"),
        ("ai", "AI and workflow"), ("diagnostics", "Diagnostics"))
BUILT_TABS = ("connections", "access", "server", "ai", "diagnostics")
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


# ── The other cards (board F3, signed off 2026-10-09) ─────────────────────────────────────────
#
# Board F's NetBox connection, Proxmox and Commit author cards on Connections, and the Server
# card on its own tab, with every setting a control (the operator, 2026-10-09: nothing on
# Installation sends a person to today's page). The TFTP root is not drawn: it retires with the
# device file routes at 7.8, its only readers (C616). Each card is declared once here; one set
# of routes and one template draw them all.

#: A card's field kinds, and what each accepts.
KINDS = {
    "url": "an http:// or https:// address",
    "choice": "one of its choices",
    "switch": "on or off",
    "name": "letters, digits and . _ - only",
    "host": "a host name or address",
    "port": "a port number, 1 to 65535",
    "vmids": "VM ids, numbers separated by commas",
    "date": "a date, YYYY-MM-DD, or empty",
    "text": "text on one line",
    "email": "an email address",
}


def _f(key, label, kind, note="", choices=()):
    return {"key": key, "label": label, "kind": kind, "note": note, "choices": choices}


#: The cards, in the page's order. ``secret``: the secret Replace… changes (with ``with_id``,
#: a plain key replaced together with it: a Proxmox token is its id and secret), drawn before
#: field ``secret_at`` as board F3 orders it; ``integration``:
#: the client its Test asks, and whose stored health draws its badge.
CARDS = {
    "netbox": {
        "group": "netbox_connection", "title": "NetBox connection", "tab": "connections",
        "fields": (_f("netbox_url", "URL", "url"),
                   _f("netbox_auth_scheme", "Auth scheme", "choice",
                      "NetBox 4.x tokens: Bearer; older: Token", ("Bearer", "Token")),
                   _f("netbox_verify_tls", "Verify TLS", "switch")),
        "secret": ("netbox_token", "API token"), "secret_at": 1, "with_id": None,
        "integration": "netbox",
        "note": "Each network's NetBox scope (its region) is per network, under that network.",
    },
    "proxmox": {
        "group": "proxmox", "title": "Proxmox", "tab": "connections",
        "fields": (_f("proxmox_url", "URL", "url"),
                   _f("proxmox_node", "Node", "name"),
                   _f("proxmox_token_expires", "Token expires", "date",
                      "declared: the token cannot read its own (C380)"),
                   _f("proxmox_verify_tls", "Verify TLS", "switch"),
                   _f("proxmox_backup_vmids", "Backup VMs", "vmids"),
                   _f("proxmox_backup_storage", "Backup storage", "name")),
        "secret": ("proxmox_token_secret", "Token secret"), "secret_at": 2,
        "with_id": ("proxmox_token_id", "Token id"),
        "integration": "proxmox", "note": "",
    },
    "author": {
        "group": "git_author", "title": "Commit author", "tab": "connections",
        "fields": (_f("nsot_git_author_name", "Name", "text"),
                   _f("nsot_git_author_email", "Email", "email")),
        "secret": None, "with_id": None, "integration": None,
        "note": "The person is recorded in each commit's Actor: trailer; this is the commit's "
                "author line.",
    },
    "server": {
        "group": "web_server", "title": "Server", "tab": "server",
        "fields": (_f("flask_host", "Bind", "host"), _f("flask_port", "Port", "port")),
        "secret": None, "with_id": None, "integration": None,
        "note": "Bind and port take effect at the next restart, and the result says so.",
    },
    # Board F4, decision C (2026-10-10): the five workflow switches are not drawn (they change
    # only the assistant's prompt text and retire with its rewrite, C30); the background agent
    # is its state (decision D), drawn by agent_state().
    "assistant": {
        "group": "ai", "title": "The assistant", "tab": "ai",
        "fields": (_f("ai_enabled", "AI", "switch",
                      "off: the chat answers that AI is off and makes no call to the model"),),
        "secret": None, "with_id": None, "integration": None,
        "note": "On devices it is read-only: every command it sends is on the read-only "
                "allowlist, and it changes nothing.",
    },
}


def agent_state() -> dict:
    """The background agent, as board F4 draws it (decision D): its state, never a switch. Off
    until Stage 8 (MERCURY_CHARTER: it proposes, never confirms). Set on in the settings file,
    it is said as such, with C623's fact: it starts only at the next restart."""
    from modules.settings_schema import get_setting

    return {"on": bool(get_setting("background_agent_enabled", False))}


def settings_place(name: str, label: str) -> str:
    """Where a person changes integration *name*'s settings on v2 (C617): its Installation card
    when it is the installation's own (NetBox, Proxmox), else the Default network's card or the
    network's own. One answer for every text that sends a person there."""
    card = next((s for s in CARDS.values() if s["integration"] == name), None)
    if card:
        return f"Settings › Installation › Connections, {card['title']}"
    return f"Settings › Default, the {label} card (or the network's own)"


#: A card's Save (its steps named on the manual's installation-settings page).
CARD_SAVE_STEPS = ("check", "write", "record")
#: A card's Replace…: the new secret checked, stored, recorded, then the card's Test.
CARD_REPLACE_STEPS = ("check", "store", "record", "test")
#: NetBox's Turn off: the master switch written off, then recorded. Turning it on is an
#: authorised NetBox write's confirm (routes/netbox_safety.py), never this card.
WRITES_OFF_STEPS = ("write", "record")
#: The fields a restart reads (the result says the change waits for one).
RESTART_KEYS = ("flask_host", "flask_port")
#: The record kinds the cards write (the records database's are its own, above).
CARD_KINDS = ("card_save", "card_replace", "netbox_writes_off")


def _health(name: str) -> dict:
    """The integration's stored health (the integrations reader, every 60 s): ``state`` up,
    down, refused, not_configured or ``unread``, with its message and the value's time. Never a
    probe per page: Test is the person asking now."""
    from modules import reader_job

    got = reader_job.read_cached("integrations")
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    if got.get("state") != "ok" or not good:
        return {"state": "unread", "message": "the integrations reader has not stored a value",
                "at_iso": ""}
    item = next((i for i in (good.get("value") or {}).get("integrations") or []
                 if i.get("name") == name), None)
    if item is None:
        return {"state": "unread", "message": f"the reader's value names no {name}",
                "at_iso": ""}
    return {"state": item.get("state") or "down", "message": item.get("message") or "",
            "at_iso": good.get("value_at") or ""}


def _writes_state() -> dict:
    """NetBox's master switch: on or off, and the last Turn off on record (who, when)."""
    from modules.settings_schema import get_setting

    on = bool(get_setting("netbox_allow_writes", False))
    last = (changes(kinds=("netbox_writes_off",))["rows"] or [None])[0]
    return {"on": on, "last_off": None if on else last}


def card(name: str) -> dict:
    """One card as drawn: its fields with today's values (a secret only as set or not set),
    its integration's stored health, and NetBox's master switch."""
    from modules.secrets_store import is_set
    from modules.settings_schema import DEFAULTS, get_setting

    spec = CARDS[name]
    fields = []
    for f in spec["fields"]:
        value = get_setting(f["key"], DEFAULTS.get(f["key"]))
        fields.append(dict(f, value=value, kind_words=KINDS[f["kind"]]))
    out = {"name": name, "spec": spec, "fields": fields, "health": None, "writes": None,
           "secret_set": bool(spec["secret"]) and is_set(spec["secret"][0]),
           "id_value": get_setting(spec["with_id"][0], "") if spec["with_id"] else ""}
    if spec["integration"]:
        out["health"] = _health(spec["integration"])
    if name == "netbox":
        out["writes"] = _writes_state()
    return out


def _value(f: dict, raw):
    """One field's value as the schema types it, or `Refused` naming the field and the kind."""
    kind, label = f["kind"], f["label"]
    if kind == "switch":
        return raw not in (None, "", "off", "0", "false")
    text = (raw or "").strip()

    def no():
        return Refused(f"{label} {text!r} is not {KINDS[kind]}")

    if kind == "url":
        if text and not re.fullmatch(r"https?://[^\s/]+(/\S*)?", text):
            raise no()
        return text
    if kind == "choice":
        if text not in f["choices"]:
            raise no()
        return text
    if kind == "name":
        if text and not re.fullmatch(r"[A-Za-z0-9._-]+", text):
            raise no()
        return text
    if kind == "host":
        if not re.fullmatch(r"[A-Za-z0-9.:_-]+", text):
            raise no()
        return text
    if kind == "port":
        if not text.isdigit() or not 1 <= int(text) <= 65535:
            raise no()
        return int(text)
    if kind == "vmids":
        if not re.fullmatch(r"[0-9, ]*", text):
            raise no()
        return ", ".join(t for t in re.split(r"[ ,]+", text) if t)
    if kind == "date":
        if text and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise no()
        if text:
            try:
                time.strptime(text, "%Y-%m-%d")
            except ValueError:
                raise no() from None
        return text
    if kind == "email":
        if not re.fullmatch(r"[^\s@]+@[^\s@]+", text):
            raise no()
        return text
    if "\n" in text or "\r" in text or not text:
        raise no()
    return text


def save_card(name: str, form: dict, actor: str, verified: str) -> dict:
    """Save a card's fields (CARD_SAVE_STEPS): check each, write what changed to the
    installation's settings, record who and which fields (never a value). A switch the form
    did not send is off. ``{"ok", "written", "nothing", "restart", "recorded", ...}``."""
    from modules.settings_schema import DEFAULTS, get_setting, write_settings

    spec = CARDS[name]
    values = {f["key"]: _value(f, form.get(f["key"])) for f in spec["fields"]}      # check
    changed = {k: v for k, v in values.items() if get_setting(k, DEFAULTS.get(k)) != v}
    if not changed:
        return {"ok": True, "nothing": True, "written": [], "recorded": True, "restart": False}
    out = write_settings(changed, actor=actor)                                       # write
    if not out["ok"]:
        raise Refused(out["error"])
    entry = _record({"kind": "card_save", "card": name, "actor": actor,             # record
                     "actor_verified": verified, "fields": sorted(changed)})
    return dict(entry, ok=True, nothing=False, written=sorted(changed),
                restart=any(k in changed for k in RESTART_KEYS))


def test_card(name: str, client=None) -> dict:
    """The card's Test: its integration asked now, with what is saved; nothing changed. The
    answer is drawn in the card (the badge stays the reader's, refreshed on its minute)."""
    from modules.integrations import get_integration

    spec = CARDS[name]
    if not spec["integration"]:
        raise Refused(f"{spec['title']} has no Test: it configures no service to ask")
    c = client or get_integration(spec["integration"])
    try:
        got = c.test_connection()
    except Exception as exc:                                            # noqa: BLE001
        got = {"ok": False, "error": f"the test raised {type(exc).__name__}: {exc}"}
    now = _now()
    return {"ok": bool(got.get("ok")), "message": got.get("message") or "",
            "error": got.get("error") or "", "at": now, "at_iso": _iso(now)}


def replace_secret(name: str, form: dict, actor: str, verified: str, client=None) -> dict:
    """Replace a card's secret (CARD_REPLACE_STEPS): check, store it as a secret (with its id
    when the card has one), record the names, then Test. The value is never returned, logged
    or recorded."""
    from modules.secrets_store import set_secret
    from modules.settings_schema import write_settings

    spec = CARDS[name]
    if not spec["secret"]:
        raise Refused(f"{spec['title']} holds no secret")
    key, label = spec["secret"]
    new = (form.get(key) or "").strip()
    if not new or not re.fullmatch(r"[\x21-\x7e]+", new):                        # check
        raise Refused(f"the new {label.lower()} is empty or holds a space or a character a "
                      "token never has; nothing was replaced")
    fields = [key]
    if spec["with_id"]:
        id_key, id_label = spec["with_id"]
        new_id = (form.get(id_key) or "").strip()
        if not re.fullmatch(r"[^\s@!]+@[^\s@!]+![A-Za-z0-9._-]+", new_id):
            raise Refused(f"{id_label} {new_id!r} is not a Proxmox token id "
                          "(user@realm!name); nothing was replaced")
        out = write_settings({id_key: new_id}, actor=actor)                        # store
        if not out["ok"]:
            raise Refused(out["error"])
        fields.insert(0, id_key)
    if not set_secret(key, new):
        raise Refused(f"the secrets store refused the new {label.lower()}; "
                      + ("its id was written, the secret was not" if spec["with_id"]
                         else "nothing was replaced"))
    entry = _record({"kind": "card_replace", "card": name, "actor": actor,          # record
                     "actor_verified": verified, "fields": fields})
    return dict(entry, ok=True, tested=test_card(name, client))                     # test


def netbox_writes_off(actor: str, verified: str) -> dict:
    """Turn NetBox's master switch off (WRITES_OFF_STEPS) and record who and when. No confirm:
    turning writes off takes nothing a person must keep. Off already: nothing written."""
    from modules.settings_schema import get_setting, write_settings

    if not get_setting("netbox_allow_writes", False):
        return {"ok": True, "nothing": True, "recorded": True}
    out = write_settings({"netbox_allow_writes": False}, actor=actor)               # write
    if not out["ok"]:
        raise Refused(out["error"])
    entry = _record({"kind": "netbox_writes_off", "card": "netbox", "actor": actor,  # record
                     "actor_verified": verified, "fields": ["netbox_allow_writes"]})
    return dict(entry, ok=True, nothing=False)


# ── Access and identity (board F4, decision A, signed off 2026-10-10) ─────────────────────────
#
# Read-only by design (docs/SETTINGS.md): a session must never lower the gate it is using, and a
# wrong team domain or audience locks everyone out or lets everyone in, silently. The one control
# is Record this decision, ratify: it writes the value ALREADY in force, so it cannot change
# behaviour, and it is recorded in the installation's settings record (C625).

#: Record this decision's steps, named on the manual's page.
RATIFY_STEPS = ("check", "write", "record")
#: What each gated action is, in a person's words (identity.GATED_ACTIONS' order).
ACTION_WORDS = {
    "reveal": ("Reveal", "show a stored secret"),
    "approve": ("Approve", "approve a template or a queued change"),
    "confirm": ("Confirm", "confirm a previewed device change"),
    "publish_remote": ("Publish", "push the record to its remote"),
    "configure": ("Configure", "change Mercury's own settings, gates and records"),
    "break_glass": ("Break-glass", "export or check the break-glass record"),
}
#: The Cloudflare Access card's keys and the service tokens card's.
ACCESS_CARD_KEYS = ("cf_access_team_domain", "cf_access_aud", "cf_access_trusted_peers",
                    "cf_access_jwks_ttl")
SERVICE_CARD_KEYS = ("service_allowed_operations", "cf_access_service_labels")


def _identity_keys() -> tuple:
    from modules.settings_scope import group_keys

    return group_keys("identity")


def _ratified() -> dict:
    """``{key: entry}``: the newest Record this decision of each key, from the record."""
    out = {}
    for row in reversed(changes(kinds=("ratify",))["rows"]):
        for key in row.get("fields") or []:
            out[key] = row
    return out


def _origin(key: str, origin: str, value, default, ratified: dict) -> dict:
    """A key's origin in a person's words: defaulted (nobody decided), recorded (in the file,
    equal to the default; by whom and when when the record holds it) or chosen (differs)."""
    if origin == "default":
        return {"state": "defaulted", "words": "defaulted, nobody decided"}
    if origin != "file":
        return {"state": "unknown", "words": "origin unknown: the settings file was not read"}
    if value != default:
        return {"state": "chosen", "words": "chosen: differs from the default"}
    row = ratified.get(key)
    if row:
        return {"state": "recorded",
                "words": f"recorded by {row.get('actor_label')}, {row.get('at_iso', '')[:10]}"}
    return {"state": "recorded", "words": "recorded in the file (who and when not recorded here)"}


def access_view(ident) -> dict:
    """Board F4's Access and identity tab: the twelve gates paired per action, the Cloudflare
    Access values (shown to a verified person only), the service tokens, and the viewer."""
    from modules import identity
    from modules.settings_schema import DEFAULTS, get_setting, origin_of

    person = bool(getattr(ident, "verified", False)) and getattr(ident, "kind", "") == "person"
    p = identity.posture(reveal_config=person)
    ratified = _ratified()
    by_key = {g["key"]: g for g in p["gates"]}
    gates, off = [], 0
    for action in identity.GATED_ACTIONS:
        cells = []
        for prefix in ("require_identity_for", "require_person_for"):
            g = by_key[f"{prefix}_{action}"]
            off += 0 if g["value"] else 1
            cells.append(dict(g, origin_words=_origin(g["key"], g["origin"], g["value"],
                                                      g["default"], ratified)))
        name, means = ACTION_WORDS.get(action, (action, ""))
        gates.append({"action": action, "name": name, "means": means, "cells": cells,
                      "defaulted": [c["key"] for c in cells
                                    if c["origin_words"]["state"] == "defaulted"]})

    def card_origins(keys):
        return {k: _origin(k, origin_of(k), get_setting(k, DEFAULTS.get(k)), DEFAULTS.get(k),
                           ratified) for k in keys}

    ttl, ttl_problem = identity.jwks_ttl()
    labels = get_setting("cf_access_service_labels", {}) or {}
    return {
        "readable": p["settings_readable"], "read_failure": p["settings_read_failure"],
        "gates": gates, "off": off, "total": 2 * len(identity.GATED_ACTIONS),
        "access_configured": p["access_configured"], "access_set": p["access_values_set"],
        "access": p.get("access"), "person": person,
        "ttl": ttl, "ttl_problem": ttl_problem,
        "ttl_bounds": (identity.JWKS_TTL_MIN, identity.JWKS_TTL_MAX),
        "access_origins": card_origins(ACCESS_CARD_KEYS),
        "service_ops": p["service_allowed_operations"],
        "labels": [{"id": (f"{cid[:4]}…{cid[-2:]}" if len(cid) > 8 else "…"), "name": name}
                   for cid, name in sorted(labels.items(), key=lambda kv: kv[1])],
        "service_origins": card_origins(SERVICE_CARD_KEYS),
        "you": {"actor": getattr(ident, "actor", ""), "kind": getattr(ident, "kind", ""),
                "verified": bool(getattr(ident, "verified", False)),
                "peer_trusted": bool(getattr(ident, "peer_trusted", False)),
                "may": [(ACTION_WORDS.get(a, (a,))[0], identity.may(ident, a)[0])
                        for a in identity.GATED_ACTIONS]},
    }


def ratify_keys(keys, actor: str, verified: str) -> dict:
    """Record this decision (RATIFY_STEPS) for *keys*: each must be one of the identity group's
    and defaulted; `settings_schema.ratify` writes the value already in force (never a change);
    the decision is appended to the installation's settings record (C625)."""
    from modules.settings_schema import origin_of, ratify

    allowed = set(_identity_keys())
    keys = [k for k in dict.fromkeys(keys or []) if k]
    stray = sorted(set(keys) - allowed)                                          # check
    if not keys or stray:
        raise Refused(("nothing was named to record" if not keys else
                       f"{', '.join(stray)} {'is' if len(stray) == 1 else 'are'} not an "
                       "access or identity setting"))
    todo = [k for k in keys if origin_of(k) != "file"]
    if not todo:
        return {"ok": True, "nothing": True, "recorded": True, "written": []}
    written = []
    for key in todo:                                                             # write
        out = ratify(key, actor=actor)
        if not out.get("ok"):
            raise Refused(f"{key}: {out.get('error')}"
                          + (f" ({', '.join(written)} were recorded)" if written else ""))
        written.append(key)
    entry = _record({"kind": "ratify", "card": "access", "actor": actor,         # record
                     "actor_verified": verified, "fields": written})
    return dict(entry, ok=True, nothing=False, written=written)
