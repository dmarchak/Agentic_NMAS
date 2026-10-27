"""A network's SDN controller connections (PHASE8_PLAN 17.1 S2): what each is, where it is
kept, and the one way it is written, tested and handed to a driver.

**What a connection holds:** a name (unique in its network), a driver kind (`drivers.DRIVERS`,
built drivers only: Mercury offers only what a driver declares), the controller's northbound
URL, whether its TLS certificate is verified, a timeout (seconds, per call, the driver's
bound), the southbound address its switches reach it on (informational: Mercury never dials
it), the controller application's own flow cookies (the operator's decision, 2026-10-27: a
flow carrying one of them is the controller's own, never unauthorised; `[0]` by default, a
learning switch's), and a credential.

**Where it is kept:** the connection list is the network setting `sdn_controllers`, through
`list_settings` as every integration's settings are: the Default network's in the global file,
another network's in its own store. **Each network's list is its own and never inherited** (the
operator's decision of 2026-10-27, C1841; `settings_scope.OWN_ONLY`): a network that sets none
has none, whatever its mode, and never reads Default's. The schema refuses any field it does not
name, so no credential can be in it. The credential is the credential store's
(`credentials.set_controller_credential`), encrypted at rest as device credentials are, keyed
by the network (`integration_groups.group_id`: ``default`` or the list's slug) and the name.

**A credential is never read back:** no answer here carries one, or the user's name, only
whether one is set and its kind. A blank on save keeps the stored one; erasing is said by
name (`clear_credentials`). The driver is handed a callable that resolves it at each request
(`driver_for`), never the value.

**Writes carry their network** (CLAUDE.md, "A write path carries its list"): `save_connection`
and `remove_connection` take it first and refuse an empty one, each under one cross-process
lock across its read and its write, recorded in the network's settings record (names and keys,
never values). Their routes are Settings › Integrations' SDN controllers card
(`routes/settings_v2.py`, board SdnSettings), each declared in `route_gates` and `invalidation`.
"""

import ipaddress
import logging
import os
import re
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

SETTING = "sdn_controllers"
GROUP = "sdn_controllers"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")
#: The controller application's own cookies when none are declared: a learning switch's
#: flows carry 0 (the operator's decision, 2026-10-27).
DEFAULT_OWN_COOKIES = (0,)
#: The fields a connection is saved with, in the order a card draws them.
FIELDS = ("name", "kind", "url", "verify_tls", "timeout", "southbound", "own_cookies")
SOUTHBOUND_LIMIT = 255


class ConnectionRefused(ValueError):
    """A connection that cannot be saved or removed, in words naming why."""


def _lock():
    from modules import config
    from modules.filestore import PathLock

    return PathLock(lambda: os.path.join(config.DATA_DIR, "sdn_connections"))


# ───────────────────────────────────────────────────────────────────────────── reading

def _owner(network: str):
    """*network*'s own key for its list (``default`` or its slug: never another network's,
    since the group is never inherited, C1841), or None when the network declared it not
    applicable."""
    from modules import integration_groups

    return integration_groups.group_id(GROUP, network)


def _stored(network: str) -> list:
    """*network*'s own list as stored: a fresh copy, never the schema's default object
    itself. A network that set none has none (`settings_scope.OWN_ONLY`)."""
    from modules import list_settings as L

    got, _origin = L.resolve(network, SETTING)
    return [dict(c) for c in (got or []) if isinstance(c, dict)]


def credential_key(owner: str, name: str) -> str:
    return f"{owner}/{name}"


def _public(conn: dict, owner: str) -> dict:
    """A connection as any reader may see it: every field, the driver's words, and whether a
    credential is set and its kind; never the credential or the user's name."""
    from modules import credentials
    from modules.redact import redact_text
    from modules.sdn.drivers import DRIVERS

    cls = DRIVERS.get(conn.get("kind"))
    try:
        cred = credentials.controller_credential_info(credential_key(owner, conn["name"]))
    except Exception as exc:                          # noqa: BLE001 (said, never "none")
        cred = {"set": None, "auth": "unknown",
                "error": f"the credential store could not be read ({type(exc).__name__})"}
    return {"name": conn["name"], "kind": conn.get("kind", ""),
            "label": cls.label if cls else conn.get("kind", ""),
            "status": cls.status if cls else "unknown",
            "url": redact_text(conn.get("url", "")),
            "verify_tls": bool(conn.get("verify_tls", True)),
            "timeout": conn.get("timeout", _default_timeout()),
            "southbound": conn.get("southbound", ""),
            "own_cookies": list(conn.get("own_cookies", DEFAULT_OWN_COOKIES)),
            "credentials": cred, "owner": owner}


def connections(network: str) -> dict:
    """*network*'s controller connections: ``{"ok", "network", "state", "owner",
    "connections", "error"}``. ``state``: ``ok`` (one or more), ``none`` (the network set
    none: it never takes Default's, C1841), ``not_applicable`` (declared so), or
    ``unreadable`` (the network's store could not be read; never read as none)."""
    from modules import list_settings as L

    out = {"ok": False, "network": network, "state": "unreadable", "owner": None,
           "connections": [], "error": ""}
    if not network:
        out["error"] = ("a network's controllers are asked for by its name (P.8); none was "
                        "given")
        return out
    try:
        owner = _owner(network)
        if owner is None:
            out.update(ok=True, state="not_applicable")
            return out
        stored = _stored(network)
    except L.ListSettingsUnreadable as exc:
        out["error"] = str(exc)
        return out
    out.update(ok=True, owner=owner, connections=[_public(c, owner) for c in stored],
               state="ok" if stored else "none")
    return out


def _find(network: str, name: str):
    """``(stored connection or None, owner)``."""
    owner = _owner(network)
    if owner is None:
        return None, None
    return next((c for c in _stored(network) if c.get("name") == name), None), owner


def _default_timeout() -> float:
    from modules.sdn.drivers.base import DEFAULT_TIMEOUT

    return DEFAULT_TIMEOUT


def _connection(values: dict, credentials=None):
    from modules.sdn.drivers.base import Connection

    return Connection(url=values["url"], verify_tls=bool(values.get("verify_tls", True)),
                      timeout=values.get("timeout", _default_timeout()),
                      credentials=credentials)


def driver_for(network: str, name: str, **driver_kwargs) -> dict:
    """``{"ok": True, "driver", "connection"}`` for *network*'s connection *name*: the driver
    of its kind over its URL, TLS choice and timeout, with a callable that reads its credential
    from the store at each request (never the value). Else ``{"ok": False, "error"}`` naming
    why. *driver_kwargs* reach the driver (a test's session and clock)."""
    from modules import credentials, list_settings as L
    from modules.sdn import drivers

    try:
        conn, owner = _find(network, name)
    except L.ListSettingsUnreadable as exc:
        return {"ok": False, "error": str(exc)}
    if owner is None:
        return {"ok": False, "error": f"SDN controllers are declared not applicable on "
                                      f"{network}"}
    if conn is None:
        return {"ok": False, "error": f"{network} has no controller connection {name!r}"}
    key = credential_key(owner, name)
    made = drivers.make(conn.get("kind"),
                        _connection(conn, lambda: credentials.get_controller_credential(key)),
                        **driver_kwargs)
    if not made["ok"]:
        return made
    return {"ok": True, "error": "", "driver": made["driver"],
            "connection": _public(conn, owner)}


# ───────────────────────────────────────────────────────────────────────────── checking

def _cookie(value) -> int:
    if isinstance(value, bool):
        raise ValueError(f"a cookie is a number, not {value!r}")
    if isinstance(value, str):
        value = int(value.strip(), 0)
    if not isinstance(value, int) or not 0 <= value <= 2 ** 64 - 1:
        raise ValueError(f"a cookie is a whole number from 0 to 2^64-1, not {value!r}")
    return value


def _own_cookies(value) -> list:
    """The declared own cookies as sorted integers. None is the default (`[0]`); an empty list
    is a choice (the controller's application installs no flow of its own)."""
    from modules.sdn import flow_intent

    if value is None:
        return list(DEFAULT_OWN_COOKIES)
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"the controller's own cookies are a list, not {value!r}")
    try:
        cookies = sorted({_cookie(v) for v in value})
    except ValueError as exc:
        raise ValueError(f"the controller's own cookies: {exc}") from None
    ours = [c for c in cookies if flow_intent.is_mercury(c)]
    if ours:
        raise ValueError(
            "the controller's own cookies may not be in Mercury's range (high 16 bits "
            f"{flow_intent.PREFIX:#06x}): {', '.join(hex(c) for c in ours)}; a flow there is "
            "Mercury's, checked against its record")
    return cookies


def _southbound(value) -> str:
    """An address the switches reach the controller on: a host name or an IP address (IPv6
    bracketed when a port follows), with an optional port. Informational: never dialled."""
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > SOUTHBOUND_LIMIT or any(ch.isspace() for ch in text):
        raise ValueError(f"the southbound address {text!r} is not an address")
    try:
        ipaddress.ip_address(text)                    # a bare address, IPv6 unbracketed too
        return text
    except ValueError:
        pass
    try:
        parts = urlsplit(f"tcp://{text}")
        host, _port = parts.hostname, parts.port
    except ValueError as exc:
        raise ValueError(f"the southbound address {text!r} is not host[:port] ({exc})") \
            from None
    if not host or parts.path or parts.query or parts.username is not None:
        raise ValueError(f"the southbound address {text!r} is not host[:port]")
    return text


def check(values: dict) -> dict:
    """*values* as a connection would be saved: ``{"ok", "error", "connection"}``, every
    problem named. Checks the name, that the kind is a built driver, the URL and timeout as
    the driver checks them (`connection_problem`: http or https, a host, no user part, an IPv6
    literal bracketed), the southbound address and the own cookies."""
    from modules.sdn.drivers import DRIVERS
    from modules.sdn.drivers.base import connection_problem

    if not isinstance(values, dict):
        return {"ok": False, "error": "a connection is given as a mapping of its fields"}
    problems = []
    name = str(values.get("name") or "").strip()
    if not NAME.fullmatch(name):
        problems.append(f"the name {name!r} must be 1 to 63 letters, digits, '.', '_' or '-', "
                        "starting with a letter or digit")
    kind = str(values.get("kind") or "").strip()
    cls = DRIVERS.get(kind)
    if cls is None:
        problems.append(f"there is no controller driver of kind {kind!r}; the kinds are "
                        f"{', '.join(sorted(DRIVERS))}")
    elif cls.status != "built":
        problems.append(f"the {cls.label} driver is not built (status: {cls.status}), so a "
                        "connection to it could do nothing")
    url = str(values.get("url") or "").strip().rstrip("/")
    timeout = values.get("timeout", _default_timeout())
    if isinstance(timeout, str):
        try:
            timeout = float(timeout)
        except ValueError:
            pass
    verify = values.get("verify_tls", True)
    if not isinstance(verify, bool):
        problems.append(f"verify_tls is true or false, not {verify!r}")
        verify = True
    problem = connection_problem(_connection({"url": url, "timeout": timeout}))
    if problem:
        problems.append(problem)
    try:
        southbound = _southbound(values.get("southbound"))
    except ValueError as exc:
        problems.append(str(exc))
        southbound = ""
    try:
        own = _own_cookies(values.get("own_cookies"))
    except ValueError as exc:
        problems.append(str(exc))
        own = []
    if problems:
        return {"ok": False, "error": "; ".join(problems)}
    return {"ok": True, "error": "", "connection": {
        "name": name, "kind": kind, "url": url, "verify_tls": verify,
        "timeout": float(timeout), "southbound": southbound, "own_cookies": own}}


def _typed_credentials(values: dict) -> dict:
    out = {}
    for k in ("username", "password", "token"):
        v = values.get(k)
        if v not in (None, ""):
            if not isinstance(v, str):
                raise ValueError(f"a controller's {k} is text")
            out[k] = v
    if out.get("token") and (out.get("password") or out.get("username")):
        raise ValueError("give a user and password or a token for a controller, not both")
    return out


# ───────────────────────────────────────────────────────────────────────────── writing

def _need(network: str, actor: str) -> None:
    if not network:
        raise ConnectionRefused("a connection is saved FOR a network, and none was given "
                                "(a write path carries its list)")
    if not actor:
        raise ConnectionRefused("a connection's save records who made it, and no actor was "
                                "given")


def _write(network: str, conns: list, actor: str) -> None:
    from modules import list_settings as L

    got = L.write(network, {SETTING: conns}, actor=actor)
    if not got.get("ok"):
        raise ConnectionRefused(f"not saved: {got.get('error')}")


def save_connection(network: str, values: dict, actor: str, actor_verified: str = "",
                    clear_credentials: bool = False, loaded: dict = None) -> dict:
    """Save one connection FOR *network*, a new one or one of its own by the same name.
    *values*: the fields (`FIELDS`) and, optionally, ``username``, ``password`` or ``token``:
    a blank one keeps what is stored, never erases it; *clear_credentials* erases them.

    *loaded*: the connection as the form that sent *values* drew it (its `FIELDS`), or ``{}``
    for a form that added a new one. With it, a save is refused, naming each field and both
    values, when the stored connection moved since it was drawn (another person saved it, or
    a new one took the name), so no one's change is written over unseen (CONCURRENCY_AUDIT
    R17's rule for every card). Under one cross-process lock; the credential is written first
    and put back if the list's write fails. Raises `ConnectionRefused` naming why; answers
    ``{"ok", "network", "name", "created", "written", "credentials", "recorded"}``."""
    from modules import credentials, list_settings as L

    _need(network, actor)
    got = check(values)
    if not got["ok"]:
        raise ConnectionRefused(got["error"])
    new = got["connection"]
    try:
        typed = _typed_credentials(values)
    except ValueError as exc:
        raise ConnectionRefused(str(exc)) from None
    with _lock():
        try:
            owner = _owner(network)
            stored = _stored(network)
        except L.ListSettingsUnreadable as exc:
            raise ConnectionRefused(f"not saved: {exc}") from None
        if owner is None:
            raise ConnectionRefused(f"SDN controllers are declared not applicable on {network}; "
                                    "nothing was saved")
        before = next((c for c in stored if c["name"] == new["name"]), None)
        moved = _moved(loaded, before, new["name"])
        if moved:
            raise ConnectionRefused(moved)
        written = sorted(k for k in FIELDS if before is None or before.get(k) != new[k])
        conns = [new if c["name"] == new["name"] else c for c in stored]
        if before is None:
            conns.append(new)
        key = credential_key(owner, new["name"])
        if before is None and not clear_credentials:
            # A new connection never takes up a credential left under its name.
            credentials.clear_controller_credential(key)
        try:
            cred = credentials.set_controller_credential(key, clear=clear_credentials, **typed)
        except ValueError as exc:
            raise ConnectionRefused(str(exc)) from None
        try:
            if written:
                _write(network, conns, actor)
        except Exception:
            credentials.restore_controller_credential(key, cred["previous"])
            raise
    if cred["changed"]:
        _invalidate_redaction()
    state = ("cleared" if clear_credentials and cred["changed"] else
             "replaced" if cred["changed"] else "kept")
    entry = L._record(network, {
        "kind": "sdn_connection", "action": "create" if before is None else "save",
        "name": new["name"], "written": written, "credentials": state,
        "actor": actor, "actor_verified": actor_verified})
    log.info("sdn: %s saved controller connection %s on %s (%s; credential %s)", actor,
             new["name"], network, ",".join(written) or "no field changed", state)
    return {"ok": True, "error": "", "network": network, "name": new["name"],
            "created": before is None, "written": written,
            "credentials": {"state": state, "auth": cred["auth"]},
            "recorded": entry.get("recorded", False)}


def _moved(loaded, before, name: str) -> str:
    """Why a save from a form that drew *loaded* would write over a change it never saw, or
    "". None is a caller that drew nothing (a script, a test): nothing is compared."""
    if loaded is None:
        return ""
    if not loaded:
        if before is not None:
            return (f"a connection named {name} was saved since this form was drawn: open it "
                    "with Edit to change it; nothing was saved")
        return ""
    if before is None:
        return (f"{name} was removed since this form was drawn; nothing was saved")
    words = [f"{k} is now {before.get(k)!r} (this form drew {loaded.get(k)!r})"
             for k in FIELDS if k in loaded and before.get(k) != loaded.get(k)]
    if words:
        return (f"{name} was changed since this form was drawn: " + "; ".join(words)
                + ". Nothing was saved: open it again to see the change")
    return ""


def remove_connection(network: str, name: str, actor: str, actor_verified: str = "") -> dict:
    """Remove *network*'s connection *name*, and its credential. Says what survives: the
    flow-intent records naming it stay (they are a history), and nothing on the controller or
    its switches changes."""
    from modules import credentials, list_settings as L

    _need(network, actor)
    with _lock():
        try:
            conn, owner = _find(network, name)
        except L.ListSettingsUnreadable as exc:
            raise ConnectionRefused(f"not removed: {exc}") from None
        if conn is None:
            raise ConnectionRefused(f"{network} has no controller connection {name!r}; "
                                    "nothing was removed")
        _write(network, [c for c in _stored(network) if c["name"] != name], actor)
        had = credentials.clear_controller_credential(credential_key(owner, name))
    if had:
        _invalidate_redaction()
    entry = L._record(network, {"kind": "sdn_connection", "action": "remove", "name": name,
                                "credentials": "cleared" if had else "none",
                                "actor": actor, "actor_verified": actor_verified})
    log.info("sdn: %s removed controller connection %s on %s", actor, name, network)
    return {"ok": True, "error": "", "network": network, "name": name,
            "credential_cleared": had, "recorded": entry.get("recorded", False),
            "survives": ("the flow-intent records naming it are kept; nothing on the "
                         "controller or its switches changes")}


def _invalidate_redaction() -> None:
    try:
        from modules.redact import invalidate_cache
        invalidate_cache()
    except Exception:                                 # noqa: BLE001 - never fail a write
        pass


# ───────────────────────────────────────────────────────────────────────────── testing

def test_connection(values: dict, **driver_kwargs) -> dict:
    """Test a connection with the values as typed, before anything is saved, through its
    driver's `test()`: ``{"ok", "error", "switches", "version", ...}``, ``switches`` the
    number connected and ``version`` the controller's (None, and ``version_note`` saying why,
    when it reports none). The credential is the one typed; with none typed and ``network``
    and ``name`` naming a saved connection, its stored one (said: ``credentials``
    ``stored``), so editing a connection's URL can be tested without typing it again. Writes
    nothing."""
    from modules import credentials, list_settings as L
    from modules.sdn import drivers

    out = {"ok": False, "error": "", "switches": None, "version": None, "credentials": "none"}
    got = check(values if isinstance(values, dict) else {})
    if not got["ok"]:
        return dict(out, error=got["error"])
    try:
        typed = _typed_credentials(values)
    except ValueError as exc:
        return dict(out, error=str(exc))
    source = None
    if typed:
        source, out["credentials"] = (lambda: dict(typed)), "typed"
    elif values.get("network") and values.get("name"):
        try:
            conn, owner = _find(values["network"], got["connection"]["name"])
        except L.ListSettingsUnreadable as exc:
            return dict(out, error=str(exc))
        if conn is not None:
            key = credential_key(owner, conn["name"])
            if credentials.controller_credential_info(key)["set"]:
                source, out["credentials"] = \
                    (lambda: credentials.get_controller_credential(key)), "stored"
    c = got["connection"]
    made = drivers.make(c["kind"], _connection(c, source), **driver_kwargs)
    if not made["ok"]:
        return dict(out, error=made["error"])
    answer = made["driver"].test()
    out.update(ok=bool(answer.get("ok")), error=answer.get("error", ""),
               switches=answer.get("switch_count"), version=answer.get("version"))
    for k in ("version_note", "refused", "timeout", "status"):
        if k in answer:
            out[k] = answer[k]
    return out


def test_saved(network: str, name: str, **driver_kwargs) -> dict:
    """Test *network*'s saved connection *name* with what is saved (its stored credential):
    the same answer as `test_connection`'s, ``{"ok", "error", "switches", "version", ...}``.
    The one Test of a saved connection, for Settings' card and SDN › Controllers alike. Writes
    nothing."""
    out = {"ok": False, "error": "", "switches": None, "version": None}
    got = driver_for(network, name, **driver_kwargs)
    if not got["ok"]:
        return dict(out, error=got["error"])
    answer = got["driver"].test()
    out.update(ok=bool(answer.get("ok")), error=answer.get("error", ""),
               switches=answer.get("switch_count"), version=answer.get("version"))
    for k in ("version_note", "refused", "timeout", "status"):
        if k in answer:
            out[k] = answer[k]
    return out


# ───────────────────────────────────────────────────────────────────────────── health

def health_probes() -> list:
    """Every distinct controller connection across the networks, for the integrations reader
    (the top bar's total counts them): ``[{"name", "label", "probe"}]``, ``probe`` a callable
    answering ``{"state", "message"}``. Each network's list is its own (C1841), so each is
    probed once. A network whose store cannot be read is one probe that answers down, naming
    it."""
    from modules import integration_groups as IG, list_settings as L

    seen, out = set(), []
    for network in IG.network_names():
        try:
            owner = _owner(network)
            if owner is None or owner in seen:
                continue
            seen.add(owner)
            stored = _stored(network)
        except L.ListSettingsUnreadable as exc:
            words = f"{network}'s controller connections could not be read ({exc})"
            out.append({"name": f"sdn:{network}", "label": f"SDN controllers ({network})",
                        "probe": lambda w=words: {"state": "down", "message": w}})
            continue
        for conn in stored:
            out.append({"name": f"sdn:{owner}/{conn['name']}",
                        "label": f"SDN controller {conn['name']}"
                                 + ("" if owner == "default" else f" ({network})"),
                        "probe": lambda n=network, c=conn["name"]: _probe(n, c)})
    return out


def _probe(network: str, name: str) -> dict:
    got = driver_for(network, name)
    if not got["ok"]:
        return {"state": "down", "message": got["error"]}
    answer = got["driver"].test()
    if answer.get("ok"):
        words = f"{answer.get('switch_count', 0)} switch(es) connected"
        return {"state": "up", "message": words}
    return {"state": "refused" if answer.get("refused") else "down",
            "message": answer.get("error") or "no answer"}
