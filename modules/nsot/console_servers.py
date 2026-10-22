"""nsot/console_servers.py — Mercury's console-server store: how Mercury reaches each
console-server port (O4 of out-of-band ZTP, docs/LAB9_PLAN.md section 8, architecture piece 1).

NetBox says WHICH console-server port a device's console is cabled to
(`modules/nsot/console_path.py`); this store says HOW Mercury reaches that port, keyed by the
port's NetBox id (the operator's design: per-port connection detail lives in Mercury, never in a
NetBox custom field, and the credential never in NetBox). Per port it holds ONLY:

- ``driver``: ``command_bridge`` (an SSH console server whose forced command bridges stdin and
  stdout to one console, chosen by a container NAME the wrapper checks against its allowlist)
  or ``raw_tcp`` (a TCP console port, optionally reached through an SSH jump host);
- ``host``: the console server, an IPv4 or IPv6 address or a hostname (an IPv6 address stored
  canonical and unbracketed);
- ``ssh_port``: the SSH port (the console server's for ``command_bridge``, the jump host's for
  ``raw_tcp``; only with a jump host there);
- ``container`` (``command_bridge`` only): a name of `CONTAINER_RE`'s shape, no ``..``. **No
  free-form command is ever stored**: the wrapper on the console server builds its one command
  from the name, and refuses any other;
- ``tcp_port`` and ``jump_host`` (``raw_tcp`` only; the jump host optional);
- ``credential_ref``: the NAME of a key in Mercury's credential store, never a value. Required
  wherever SSH is spoken (``command_bridge``, or ``raw_tcp`` through a jump host).

Any other field, an unknown driver or a field another driver owns is refused, naming it. Every
write records who made it (*actor*, required: a route passes `identity.request_actor()`) and
when, on the record and in the store's bounded log, which keeps a removal too.

**The file** (`path()`, under the data folder): read-modify-written under `filestore.PathLock`
(an exclusive ``flock``, across processes), replaced atomically through a temp file created
0600 (`filestore.write_atomic`); a store that exists and cannot be read refuses every write and
is preserved aside (`filestore.read_json_for_write`), and a read says ``unreadable``, never
``absent``.
"""

import ipaddress
import json
import logging
import os
import re
import time

from modules import filestore

log = logging.getLogger(__name__)

FILE = "console_servers.json"
DRIVERS = ("command_bridge", "raw_tcp")

#: A container name the bridge wrapper accepts: a letter or digit, then letters, digits, ``_``,
#: ``.`` and ``-``, 63 at most. ``..`` is refused besides (`container_refusal`). Every pattern
#: here is matched WHOLE (``fullmatch``): ``$`` also matches before a trailing newline, which a
#: ``match`` let through (tests/test_console_server_store.py's ``edge-a\n``).
CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
#: A credential reference: a key NAME in Mercury's credential store (a profile name, or a
#: scoped key such as ``<network>:@profile:<ref>``). No space, no quote, no newline: a pasted
#: password or key does not fit it.
CREDENTIAL_REF_RE = re.compile(r"^[A-Za-z0-9@][A-Za-z0-9_.:@-]{0,127}$")
#: One label of a hostname (RFC 1123).
_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
#: An IPv6 zone (``fe80::1%eth0``): an interface name's characters only.
_ZONE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,15}$")

#: The fields each driver holds: (required, optional).
FIELDS = {
    "command_bridge": (("host", "ssh_port", "container", "credential_ref"), ()),
    "raw_tcp": (("host", "tcp_port"), ("jump_host", "ssh_port", "credential_ref")),
}
#: Written by the store, never taken from a caller.
STAMPS = ("by", "at")
#: The bounded log of writes kept in the store.
LOG_MAX = 500


def path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, FILE)


def _empty() -> dict:
    return {"version": 1, "ports": {}, "log": []}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── validation ──────────────────────────────────────────────────────────────────────────────

def host_refusal(value) -> tuple:
    """``(canonical, "")`` for an IPv4 or IPv6 address (brackets and a zone allowed; stored
    canonical, unbracketed) or an RFC 1123 hostname; ``("", why)`` for anything else."""
    text = value if isinstance(value, str) else ""
    if not text or text != text.strip():
        return "", f"{value!r} is not an address or a hostname"
    bare = text[1:-1] if text.startswith("[") and text.endswith("]") else text
    if "%" in bare:
        addr, _, zone = bare.partition("%")
        if not _ZONE_RE.fullmatch(zone):
            return "", f"{value!r}: the IPv6 zone {zone!r} is not an interface name"
    else:
        addr = bare
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        ip = None
    if ip is not None:
        if bare != text and ip.version != 6:
            return "", f"{value!r}: only an IPv6 address is written in brackets"
        if "%" in bare and ip.version != 6:
            return "", f"{value!r}: only an IPv6 address carries a zone"
        return (f"{ip}%{bare.partition('%')[2]}" if "%" in bare else str(ip)), ""
    if bare != text or ":" in text or "%" in text:
        return "", f"{value!r} is not an IPv6 address"
    name = text[:-1] if text.endswith(".") else text
    labels = name.split(".")
    if len(name) > 253 or not all(_LABEL_RE.fullmatch(lab) for lab in labels):
        return "", f"{value!r} is not an address or a hostname"
    if all(lab.isdigit() for lab in labels):
        return "", f"{value!r} is not an IPv4 address"
    return name.lower(), ""


def container_refusal(value) -> str:
    """Why *value* is not a container name the bridge accepts, or ""."""
    text = value if isinstance(value, str) else ""
    if not text:
        return f"the container name {value!r} is empty"
    if ".." in text:
        return f"the container name {text!r} holds '..'"
    if not CONTAINER_RE.fullmatch(text):
        return (f"the container name {text!r} is not a name (a letter or digit, then letters, "
                "digits, '_', '.', '-'; 63 at most): no command is ever stored")
    return ""


def _port_number(field: str, value) -> tuple:
    if isinstance(value, bool):
        return None, f"{field} {value!r} is not a port number"
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if not isinstance(value, int) or not 1 <= value <= 65535:
        return None, f"{field} {value!r} is not a port number (1 to 65535)"
    return value, ""


def validate(record) -> tuple:
    """``(clean, errors)``: *record* checked against its driver's fields. *clean* holds only
    the driver's fields, normalised (a host canonical, a port an int); *errors* names each
    field refused. An unknown or missing driver, a field the driver does not hold (a stored
    command, say) and a missing required field are each refused."""
    if not isinstance(record, dict):
        return {}, ["a console-server port's record is a mapping of its fields"]
    driver = record.get("driver")
    if driver not in DRIVERS:
        return {}, [f"driver {driver!r} is not one of {', '.join(DRIVERS)}"]
    required, optional = FIELDS[driver]
    allowed = {"driver", *required, *optional}
    errors = [f"field {k!r} is not held for the {driver} driver" for k in sorted(record)
              if k not in allowed]
    clean = {"driver": driver}
    for field in (*required, *optional):
        if field not in record or record[field] in (None, ""):
            if field in required:
                errors.append(f"{field} is required for the {driver} driver")
            continue
        value = record[field]
        if field in ("host", "jump_host"):
            value, why = host_refusal(value)
        elif field in ("ssh_port", "tcp_port"):
            value, why = _port_number(field, value)
        elif field == "container":
            why = container_refusal(value)
        else:                                            # credential_ref
            why = "" if isinstance(value, str) and CREDENTIAL_REF_RE.fullmatch(value) else (
                f"credential_ref {value!r} is not a credential store key name (a name, never "
                "a value)")
        if why:
            errors.append(why)
        else:
            clean[field] = value
    if driver == "raw_tcp":
        if "jump_host" in clean:
            for field in ("ssh_port", "credential_ref"):
                if field not in clean and not any(field in e for e in errors):
                    errors.append(f"{field} is required with a jump host")
        else:
            for field in ("ssh_port", "credential_ref"):
                if field in clean:
                    errors.append(f"{field} is held only with a jump host (raw_tcp)")
    return clean, errors


def _key(port_id) -> tuple:
    if isinstance(port_id, bool) or not isinstance(port_id, int) or port_id <= 0:
        return "", f"a console-server port's NetBox id is a positive number, not {port_id!r}"
    return str(port_id), ""


# ── reads ───────────────────────────────────────────────────────────────────────────────────

def read() -> dict:
    """``{"state": "absent" | "read" | "unreadable", "doc", "error"}``: the store as held.
    Absent is no port configured yet; unreadable is never absent."""
    p = path()
    if not os.path.exists(p):
        return {"state": "absent", "doc": _empty(), "error": ""}
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict) or not isinstance(doc.get("ports"), dict):
            raise ValueError("not a console-server store")
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "doc": None, "error": f"{type(exc).__name__}: {exc}"}
    return {"state": "read", "doc": doc, "error": ""}


def get_port(port_id) -> dict:
    """``{"state": "absent" | "read" | "unreadable", "record", "error"}`` for one port."""
    key, why = _key(port_id)
    if why:
        return {"state": "unreadable", "record": None, "error": why}
    got = read()
    if got["state"] != "read":
        return {"state": got["state"], "record": None, "error": got["error"]}
    record = got["doc"]["ports"].get(key)
    return {"state": "read" if record else "absent", "record": record, "error": ""}


# ── writes ──────────────────────────────────────────────────────────────────────────────────

def _write(change, actor: str) -> dict:
    """One read-modify-write: *change(doc)* returns ``(result, log_entry)`` or raises
    ValueError to refuse. Locked across processes, replaced atomically, refused whole when the
    store cannot be read."""
    if not isinstance(actor, str) or not actor.strip():
        return {"ok": False, "error": "Not saved: no actor named; every write records who made it"}
    p = path()
    with filestore.PathLock(p):
        try:
            doc = filestore.read_json_for_write(p, empty=_empty())
            if not isinstance(doc, dict) or not isinstance(doc.get("ports"), dict):
                raise filestore.StoreUnreadable(f"{FILE} is not a console-server store, so "
                                                "nothing was written")
        except filestore.StoreUnreadable as exc:
            log.error("console servers: %s", exc)
            return {"ok": False, "error": f"Not saved: {exc}"}
        try:
            result, entry = change(doc)
        except ValueError as exc:
            return {"ok": False, "error": f"Not saved: {exc}"}
        doc.setdefault("log", []).append(dict(entry, by=actor, at=_now()))
        doc["log"] = doc["log"][-LOG_MAX:]
        filestore.write_atomic(p, json.dumps(doc, indent=1, sort_keys=True) + "\n")
    return dict(result, ok=True, error="")


def set_port(port_id, record, *, actor: str) -> dict:
    """Store *record* for console-server port *port_id* (its NetBox id), replacing what was
    there. ``{"ok", "error", "record"}``; refused whole, naming every field refused."""
    key, why = _key(port_id)
    if why:
        return {"ok": False, "error": f"Not saved: {why}"}
    clean, errors = validate(record)
    if errors:
        return {"ok": False, "error": "Not saved: " + "; ".join(errors)}
    clean = dict(clean, by=actor, at=_now())

    def change(doc):
        before = doc["ports"].get(key)
        doc["ports"][key] = clean
        return ({"record": clean},
                {"port": key, "action": "replaced" if before else "added",
                 "driver": clean["driver"]})
    return _write(change, actor)


def remove_port(port_id, *, actor: str) -> dict:
    """Forget console-server port *port_id*'s record. ``{"ok", "error", "removed"}``: a port
    with no record is refused, named (nothing to remove is not a removal)."""
    key, why = _key(port_id)
    if why:
        return {"ok": False, "error": f"Not removed: {why}"}

    def change(doc):
        if key not in doc["ports"]:
            raise ValueError(f"console-server port {key} has no record")
        removed = doc["ports"].pop(key)
        return {"removed": removed}, {"port": key, "action": "removed",
                                      "driver": removed.get("driver", "")}
    got = _write(change, actor)
    if not got["ok"]:
        got["error"] = got["error"].replace("Not saved", "Not removed")
    return got
