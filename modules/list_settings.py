"""A network's settings (P.8 step 2; NSOT_P8_DESIGN, sections 2 and 3).

Two lists are two networks (the operator, 2026-09-28; decided in full 2026-10-04). Each list
keeps its own settings in ``data/lists/<slug>/settings.json``, and ONE resolver answers a
network-scoped key for a list, with where the answer came from:

- **set here**: the list's own value;
- **not applicable here**: the list declared it deliberately has none (who, when, why). It
  stops the lookup and NEVER inherits Default's value;
- **inherited from Default**: unset here, so Default's value. The global settings file IS the
  Default network's layer (decision 1: no migration, nothing copied);
- **unset here**: another key of the SAME GROUP is set here, so the group is this list's own
  and this key reads its schema default, never Default's. An integration inherits as a GROUP:
  a list that sets its own Grafana URL never sends Default's token to it;
- **unset everywhere**: unset here and in Default: the schema's default.

A host-scoped key is the global value for every list. Nothing reads this module yet: step 3
gives the integration clients a list.

Writes go through :func:`write`: validated by the schema, locked across processes, replaced
whole, owner-only; a secret is encrypted in the list's file as the global file encrypts it. An
unreadable store refuses writes and is preserved; reads say it is unreadable.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

SET_HERE = "set here"
NOT_APPLICABLE = "not applicable here"
INHERITED = "inherited from Default"
UNSET_HERE = "unset here"
UNSET_EVERYWHERE = "unset everywhere"
HOST = "host-wide"
STORE = "settings.json"
DEFAULT_LIST = "Default"


class ListSettingsUnreadable(RuntimeError):
    """A list's settings file exists and cannot be read: never read as empty."""


class NoListCarried(LookupError):
    """A network setting was asked for with no list (P.8 step 4). Its own type, outside
    ValueError and TypeError, so a reader's guard against a malformed VALUE never swallows
    a missing list into a fallback."""


def is_default(list_name: str) -> bool:
    """Whether *list_name* is the Default network, whose layer is the global file."""
    from modules.config import list_slug

    return list_slug(list_name or DEFAULT_LIST) == list_slug(DEFAULT_LIST)


def path(list_name: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(list_name), STORE)


def load(list_name: str) -> dict:
    """The list's own store: ``{"values": {...}, "not_applicable": {...}}``; absent is empty.
    Raises :class:`ListSettingsUnreadable` when the file exists and cannot be read."""
    p = path(list_name)
    if not os.path.exists(p):
        return {"values": {}, "not_applicable": {}}
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict):
            raise ValueError("not an object")
    except (OSError, ValueError) as exc:
        raise ListSettingsUnreadable(f"{p} could not be read ({type(exc).__name__})") from exc
    return {"values": dict(doc.get("values") or {}),
            "not_applicable": dict(doc.get("not_applicable") or {})}


def resolve(list_name: str, key: str, store: dict = None) -> tuple:
    """``(value, origin)`` of *key* for the network *list_name*. A secret comes back as it is
    stored (encrypted); :func:`secret` decrypts one."""
    from modules.settings_schema import DEFAULTS, get_setting, load_user_settings
    from modules.settings_scope import NETWORK, group_keys, scope_of

    scope, group = scope_of(key)
    if scope != NETWORK:
        return get_setting(key), HOST
    if is_default(list_name):
        return get_setting(key), (SET_HERE if key in load_user_settings() else UNSET_EVERYWHERE)
    store = load(list_name) if store is None else store
    if key in store["not_applicable"] or group in store["not_applicable"]:
        return None, NOT_APPLICABLE
    if key in store["values"]:
        return store["values"][key], SET_HERE
    if any(k in store["values"] for k in group_keys(group)):
        return DEFAULTS.get(key), UNSET_HERE
    in_default = key in load_user_settings()
    return get_setting(key), (INHERITED if in_default else UNSET_EVERYWHERE)


def secret(list_name: str, key: str) -> str:
    """A secret key's plaintext for *list_name*, through the same resolution."""
    from modules.secrets_store import decrypt_value, get_secret
    from modules.settings_scope import NETWORK, scope_of

    if scope_of(key)[0] != NETWORK or is_default(list_name):
        return get_secret(key)
    got, origin = resolve(list_name, key)
    if origin == INHERITED:
        return get_secret(key)
    return decrypt_value(got) if got and origin == SET_HERE else ""


def value(list_name: str, key: str, default=None):
    """The value of *key* FOR the network *list_name* (P.8 step 4): the one read of a network
    setting outside this module. *default* stands in only where nothing answers: unset
    everywhere, or not applicable here, with an empty value. A write path carries its list,
    so an empty *list_name* is refused rather than read as Default's: a read that means the
    Default network says so by calling :func:`default_layer`."""
    if not list_name:
        raise NoListCarried(f"{key}: a network setting read needs its list (P.8); a read "
                            "that means the Default network calls list_settings.default_layer")
    got, origin = resolve(list_name, key)
    if got is None or (origin in (UNSET_EVERYWHERE, NOT_APPLICABLE) and got == ""):
        return default if default is not None else got
    return got


def default_layer(key: str, default=None):
    """*key* for the DEFAULT network, said by name (P.8 step 4). It is right in two places
    only, each call site listed in `tests/test_network_settings_read_for_a_list.py`, which
    only shrinks:
    - one output serves every list until P.7 makes it per network (the ZTP fragment and its
      responder, Oxidized's one router.db and its helper, the Prometheus targets directory);
    - the read is paired with an integration client still built for no list, which is the
      Default network's (steps 5 and 8 move the pair together), or it sits below any list on
      the path (the SSH layer's read bound: a device dict carries no list, C462)."""
    return value(DEFAULT_LIST, key, default)


def default_layer_secret(key: str) -> str:
    """A secret of the DEFAULT network, by name: :func:`default_layer`'s rule for a secret."""
    return secret(DEFAULT_LIST, key)


def write(list_name: str, updates: dict, actor: str = "") -> dict:
    """Set network-scoped keys for *list_name*. The Default network writes the global file
    (`settings_schema.write_settings`, the one write path there); any other list writes its own
    store. ``{"ok", "error", "written", "refused"}``."""
    from modules.filestore import PathLock, StoreUnreadable, read_json_for_write, write_atomic
    from modules.secrets_store import SECRET_KEYS, encrypt_value
    from modules.settings_schema import DEFAULTS, validate, write_settings
    from modules.settings_scope import NETWORK, SCOPES

    if not isinstance(updates, dict) or not updates:
        return {"ok": False, "error": "nothing to write", "written": [], "refused": []}
    refused = sorted(k for k in updates if SCOPES.get(k, (None,))[0] != NETWORK)
    if refused:
        return {"ok": False, "refused": refused, "written": [], "error": (
            "not a network setting: " + ", ".join(refused) + ". A host-wide or undeclared key "
            "is set once for the installation, never per list")}
    if is_default(list_name):
        return write_settings(updates, actor=actor)
    candidate = dict(DEFAULTS)
    candidate.update(updates)
    ok, why = validate(candidate)
    if not ok:
        return {"ok": False, "error": f"invalid settings: {why}", "written": [], "refused": []}
    p = path(list_name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with PathLock(p):
        try:
            doc = read_json_for_write(p, empty={"values": {}, "not_applicable": {}})
        except StoreUnreadable as exc:
            return {"ok": False, "error": str(exc), "written": [], "refused": []}
        values = dict(doc.get("values") or {})
        for k, v in updates.items():
            values[k] = encrypt_value(v) if k in SECRET_KEYS and v else v
        doc = {"values": values, "not_applicable": dict(doc.get("not_applicable") or {}),
               "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        write_atomic(p, json.dumps(doc, indent=2, sort_keys=True) + "\n")
    if actor:
        # Names and keys, never values: this line goes to the app log.
        log.info("list settings: %s wrote %s for %s", actor, ",".join(sorted(updates)),
                 list_name)
    return {"ok": True, "error": "", "written": sorted(updates), "refused": []}
