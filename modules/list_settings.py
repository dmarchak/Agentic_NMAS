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
- **unset everywhere**: unset here and in Default: the schema's default;
- **not configured for this network**: the group is this network's own and nothing of it is
  set here, so it reads its schema default and never Default's (below).

**Inheriting is a choice** (the operator, 2026-10-05; boards I and J): a network INHERITS from
Default (every network that exists, and the store's absent ``mode``) or is STANDALONE, taking
nothing from Default. Each group then chooses for itself, ``inherit``, ``own`` or not
applicable; the network's mode is only the starting point of a group that has not chosen. A
group with a value set here is its own whatever it chose before. Switching either is previewed
(:func:`plan_mode`, :func:`plan_group`), confirmed against the preview's fingerprint and
recorded (:func:`apply_mode`, :func:`apply_group`) in the list's ``settings_record.jsonl``.

A host-scoped key is the global value for every list.

Writes go through :func:`write`: validated by the schema, locked across processes, replaced
whole, owner-only; a secret is encrypted in the list's file as the global file encrypts it. An
unreadable store refuses writes and is preserved; reads say it is unreadable.
"""

import hashlib
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
NOT_CONFIGURED = "not configured for this network"
HOST = "host-wide"
STORE = "settings.json"
RECORD = "settings_record.jsonl"
DEFAULT_LIST = "Default"

#: A network's mode, and a group's choice (boards I and J). ``not_applicable`` is the store's
#: existing declaration, the third choice.
INHERIT, STANDALONE, OWN, NA = "inherit", "standalone", "own", "not_applicable"
MODES = (INHERIT, STANDALONE)
CHOICES = (INHERIT, OWN, NA)
#: A switch's steps, in order: the manual's How it works page names each (tests/test_manual.py).
SWITCH_STEPS = ("preview", "confirm", "check_again", "write", "record")
#: What a person reads for each mode and choice.
MODE_WORDS = {INHERIT: "inherits from Default", STANDALONE: "standalone"}
CHOICE_WORDS = {INHERIT: "inherit from Default", OWN: "its own", NA: "not applicable"}


class SwitchRefused(ValueError):
    """A mode or group switch cannot be applied; the message names why, and both operands
    when the preview moved."""


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


def _shape(doc: dict) -> dict:
    """The store's parts, each present: an absent ``mode`` is INHERIT, so every list that
    existed before the choice keeps today's behaviour and nothing is migrated."""
    mode = doc.get("mode") if doc.get("mode") in MODES else INHERIT
    groups = {g: c for g, c in dict(doc.get("groups") or {}).items() if c in (INHERIT, OWN)}
    return {"values": dict(doc.get("values") or {}),
            "not_applicable": dict(doc.get("not_applicable") or {}),
            "mode": mode, "groups": groups}


def load(list_name: str) -> dict:
    """The list's own store: ``{"values", "not_applicable", "mode", "groups"}``; absent is
    empty and inheriting. Raises :class:`ListSettingsUnreadable` when the file exists and
    cannot be read."""
    p = path(list_name)
    if not os.path.exists(p):
        return _shape({})
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict):
            raise ValueError("not an object")
    except (OSError, ValueError) as exc:
        raise ListSettingsUnreadable(f"{p} could not be read ({type(exc).__name__})") from exc
    return _shape(doc)


def group_choice(store: dict, group: str) -> str:
    """What *group* does for the network whose *store* this is: NA when declared not
    applicable (the group or any of its keys); OWN when any key of it is set here (a value
    set here is the network's own, whatever was chosen before); else the group's explicit
    choice; else the network's mode (standalone: OWN; inheriting: INHERIT)."""
    from modules.settings_scope import group_keys

    keys = group_keys(group)
    if group in store["not_applicable"] or any(k in store["not_applicable"] for k in keys):
        return NA
    if any(k in store["values"] for k in keys):
        return OWN
    explicit = (store.get("groups") or {}).get(group)
    if explicit in (INHERIT, OWN):
        return explicit
    return OWN if store.get("mode") == STANDALONE else INHERIT


def mode(list_name: str) -> str:
    """The network's mode; the Default network is the base layer and always INHERIT-shaped
    (it inherits from nothing, and nothing is asked of it)."""
    return INHERIT if is_default(list_name) else load(list_name)["mode"]


def resolve(list_name: str, key: str, store: dict = None) -> tuple:
    """``(value, origin)`` of *key* for the network *list_name*. A secret comes back as it is
    stored (encrypted); :func:`secret` decrypts one.

    The order (NSOT_P8_DESIGN section 8): host-wide; the Default network's own layer; not
    applicable here; set here; a group that is this network's own reads its schema default,
    never Default's (UNSET_HERE when something of it is set, NOT_CONFIGURED when nothing
    is); otherwise Default's, inherited."""
    from modules.settings_schema import DEFAULTS, get_setting, load_user_settings
    from modules.settings_scope import NETWORK, group_keys, scope_of

    scope, group = scope_of(key)
    if scope != NETWORK:
        return get_setting(key), HOST
    if is_default(list_name):
        return get_setting(key), (SET_HERE if key in load_user_settings() else UNSET_EVERYWHERE)
    store = load(list_name) if store is None else _shape(store)
    if key in store["not_applicable"] or group in store["not_applicable"]:
        return None, NOT_APPLICABLE
    if key in store["values"]:
        return store["values"][key], SET_HERE
    if group_choice(store, group) == OWN:
        set_any = any(k in store["values"] for k in group_keys(group))
        return DEFAULTS.get(key), (UNSET_HERE if set_any else NOT_CONFIGURED)
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
    if got is None or (origin in (UNSET_EVERYWHERE, NOT_APPLICABLE, NOT_CONFIGURED)
                       and got == ""):
        return default if default is not None else got
    return got


def default_layer(key: str, default=None):
    """*key* for the DEFAULT network, said by name (P.8 step 4). It is right in two places
    only, each call site listed in `tests/test_network_settings_read_for_a_list.py`, which
    only shrinks:
    - one output serves every list until P.7 makes it per network (the ZTP fragment and its
      responder, the Prometheus targets directory);
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
    from modules.filestore import PathLock, StoreUnreadable, read_json_for_write
    from modules.secrets_store import SECRET_KEYS, encrypt_value
    from modules.settings_schema import DEFAULTS, validate, write_settings
    from modules.settings_scope import NETWORK, SCOPES, scope_of

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
            doc = _shape(read_json_for_write(p, empty={}))
        except StoreUnreadable as exc:
            return {"ok": False, "error": str(exc), "written": [], "refused": []}
        for k, v in updates.items():
            doc["values"][k] = encrypt_value(v) if k in SECRET_KEYS and v else v
            # A value set here makes its group this network's own: a stored "inherit" for it
            # would contradict the value, so it goes with the write.
            if doc["groups"].get(scope_of(k)[1]) == INHERIT:
                doc["groups"][scope_of(k)[1]] = OWN
        _write_store(p, doc)
    if actor:
        # Names and keys, never values: this line goes to the app log.
        log.info("list settings: %s wrote %s for %s", actor, ",".join(sorted(updates)),
                 list_name)
    return {"ok": True, "error": "", "written": sorted(updates), "refused": []}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_store(p: str, doc: dict) -> None:
    """Replace the list's store whole, owner-only (`write_atomic`). The caller holds its
    PathLock. An inheriting mode is stored as its absence, as every older store has it."""
    from modules.filestore import write_atomic

    out = {"values": doc["values"], "not_applicable": doc["not_applicable"],
           "written_at": _now()}
    if doc.get("mode") == STANDALONE:
        out["mode"] = STANDALONE
    if doc.get("groups"):
        out["groups"] = dict(doc["groups"])
    write_atomic(p, json.dumps(out, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Inheriting is a choice: the switches (boards I and J)
# ---------------------------------------------------------------------------

#: A group's state as a person reads it, from its choice and what is set.
STATE_WORDS = {"not_applicable": NOT_APPLICABLE, "own": "its own",
               "not_configured": NOT_CONFIGURED, "inherited": INHERITED,
               "unset_everywhere": UNSET_EVERYWHERE}


def shown(key: str, stored) -> str:
    """A value as a preview draws it: a secret only as set or unset, never its value; a URL
    through the redactor, so a user part carrying a secret is masked (C476)."""
    from modules.redact import redact_text
    from modules.secrets_store import SECRET_KEYS

    if key in SECRET_KEYS:
        return "set" if stored else "unset"
    if stored in (None, "", [], {}):
        return "unset"
    text = stored if isinstance(stored, str) else json.dumps(stored, sort_keys=True)
    return redact_text(text)


def group_state(list_name: str, group: str, store: dict = None,
                default_keys: frozenset = None) -> dict:
    """What *group* is for the network *list_name* (never the Default network):
    ``{"group", "label", "choice", "explicit", "follows", "state", "words", "url"}``.
    ``follows`` is whether the group still follows the network's mode (no choice of its own,
    nothing set, not declared not applicable): only those move when the mode moves."""
    from modules.settings_schema import load_user_settings
    from modules.settings_scope import URL_KEYS, group_keys, group_label

    store = load(list_name) if store is None else _shape(store)
    default_keys = frozenset(load_user_settings()) if default_keys is None else default_keys
    keys = group_keys(group)
    choice = group_choice(store, group)
    set_here = any(k in store["values"] for k in keys)
    if choice == NA:
        state = "not_applicable"
    elif choice == OWN:
        state = "own" if set_here else "not_configured"
    else:
        state = "inherited" if any(k in default_keys for k in keys) else "unset_everywhere"
    url_key = URL_KEYS.get(group)
    url = ""
    if url_key and state in ("own", "inherited"):
        url = shown(url_key, resolve(list_name, url_key, store)[0])
    return {"group": group, "label": group_label(group), "choice": choice,
            "explicit": group in store["groups"], "state": state,
            "follows": not set_here and choice != NA and group not in store["groups"],
            "words": STATE_WORDS[state], "url": url}


def _fingerprint(operands: dict) -> str:
    """Bound to what the preview SHOWED of today: its operands, a secret only as set or
    unset."""
    raw = json.dumps(operands, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _refuse_default(list_name: str) -> None:
    if is_default(list_name):
        raise SwitchRefused(f"{list_name} is the base layer every inheriting network reads: "
                            "it inherits from nothing, so it has no inheritance to switch")


def _transform_group(doc: dict, group: str, choice: str, values: dict, reason: str,
                     actor: str) -> tuple:
    """Apply a group's switch to a store *doc* in place: ``(removed, replaced)``, each
    ``{key: as stored}``. A secret stays as stored, encrypted."""
    from modules.secrets_store import SECRET_KEYS, encrypt_value
    from modules.settings_scope import group_keys

    keys = group_keys(group)
    removed, replaced = {}, {}
    for k in [group, *keys]:
        doc["not_applicable"].pop(k, None)
    if choice in (INHERIT, NA):
        removed = {k: doc["values"].pop(k) for k in keys if k in doc["values"]}
    if choice == INHERIT:
        doc["groups"][group] = INHERIT
    elif choice == OWN:
        doc["groups"][group] = OWN
        for k, v in (values or {}).items():
            if v is None:                    # emptied in the form: not set here any more
                if k in doc["values"]:
                    removed[k] = doc["values"].pop(k)
                continue
            if k in doc["values"]:
                replaced[k] = doc["values"][k]
            doc["values"][k] = encrypt_value(v) if k in SECRET_KEYS and v else v
    else:
        doc["groups"].pop(group, None)
        doc["not_applicable"][group] = {"by": actor or "(preview)", "at": _now(),
                                        "why": (reason or "").strip()}
    return removed, replaced


def plan_group(list_name: str, group: str, choice: str, values: dict = None,
               reason: str = "", entering: bool = False) -> dict:
    """What switching *group* to *choice* for *list_name* changes, key by key, and its
    fingerprint. Writes nothing. *values* (for OWN) are the group's values the person
    entered, None for one emptied (it is then not set here); *reason* is required for NA.
    *entering* is the card that takes the values (board B): a group already its own is then
    a form whose change is judged at apply, by what is entered. Refusals are gates by name,
    except a network, group or choice that does not exist (nothing to preview), which
    raises."""
    from modules.nsot.authorisation import reason_problem
    from modules.secrets_store import SECRET_KEYS
    from modules.settings_schema import DEFAULTS, validate
    from modules.settings_scope import group_keys, group_label, network_groups

    _refuse_default(list_name)
    if group not in network_groups():
        raise SwitchRefused(f"{group!r} is not a group a network chooses for")
    if choice not in CHOICES:
        raise SwitchRefused(f"{choice!r} is not a choice: {', '.join(CHOICES)}")
    values = dict(values or {}) if choice == OWN else {}
    label, keys = group_label(group), group_keys(group)
    store = load(list_name)
    before = group_state(list_name, group, store)
    after_doc = _shape(json.loads(json.dumps(store)))
    # A secret entered is simulated as "set" and never touches the cipher here.
    sim = {k: ("(entered)" if k in SECRET_KEYS and v else v) for k, v in values.items()}
    removed, _replaced = _transform_group(after_doc, group, choice, sim, reason, "")
    after = group_state(list_name, group, after_doc)
    rows = []
    for k in keys:
        t_val, t_origin = resolve(list_name, k, store)
        a_val, a_origin = resolve(list_name, k, after_doc)
        rows.append({"key": k, "today": shown(k, t_val), "today_origin": t_origin,
                     "after": ("set (entered)" if k in SECRET_KEYS and k in values and values[k]
                               else shown(k, a_val)), "after_origin": a_origin})
    gates = []
    stray = sorted(set(values) - set(keys))
    candidate = dict(DEFAULTS)
    candidate.update({k: v for k, v in values.items() if k in keys and v is not None})
    ok, why = validate(candidate)
    if stray or not ok:
        gates.append({"gate": "valid values", "state": "fail", "why": (
            f"not {label}'s settings: {', '.join(stray)}" if stray else f"invalid: {why}")})
    elif values:
        gates.append({"gate": "valid values", "state": "pass", "why": "checked by the schema"})
    moves = before["choice"] != choice or any(r["today"] != r["after"] or
                                              r["today_origin"] != r["after_origin"]
                                              for r in rows)
    if entering and choice == OWN and before["choice"] == OWN:
        gates.append({"gate": "a change", "state": "pass",
                      "why": "what you enter is compared with what is set when you save"})
    else:
        gates.append({"gate": "a change", "state": "pass" if moves else "fail",
                      "why": (f"{CHOICE_WORDS[before['choice']]} to {CHOICE_WORDS[choice]}"
                              if before["choice"] != choice else "the values entered"
                              if moves else f"{label} is already {CHOICE_WORDS[choice]} for "
                              f"{list_name}" + (" and nothing entered differs" if values else "")
                              + ": nothing would change")})
    if choice == NA:
        problem = reason_problem({"line": f"{label} not applicable", "reason": reason or ""})
        gates.append({"gate": "a stated reason", "state": "fail" if problem else "pass",
                      "why": problem or "stated"})
    what, what_not = _group_words(list_name, label, choice, before, after, rows, removed)
    # Bound to TODAY's values as the preview showed them (the network's and Default's): boards
    # B and C take what the person types (a group's values, a reason) in the confirm card
    # itself, so what is typed is validated at apply and written exactly as sent.
    operands = {"list": list_name, "group": group, "from": before["choice"], "to": choice,
                "rows": [[r["key"], r["today"], r["today_origin"]] for r in rows]}
    return {"list": list_name, "group": group, "label": label, "from": before["choice"],
            "to": choice, "before": before, "after": after, "rows": rows,
            "removed": sorted(removed), "what": what, "what_not": what_not, "gates": gates,
            "confirmable": all(g["state"] == "pass" for g in gates),
            "operands": operands, "fingerprint": _fingerprint(operands)}


def _group_words(list_name, label, choice, before, after, rows, removed) -> tuple:
    what = []
    if choice == INHERIT:
        what.append(f"{list_name} reads Default's {label}" + (
            f" ({after['url']})" if after["url"] else "") + (
            "" if after["state"] == "inherited" else ", which Default leaves unset"))
    elif choice == OWN:
        what.append(f"Every {label} setting becomes {list_name}'s own: {list_name} stops "
                    f"reading Default's {label}, and Default's credentials are never sent to "
                    f"{list_name}'s address")
        if after["state"] == "not_configured":
            what.append(f"Nothing of it is set yet, so {label} is not configured for "
                        f"{list_name} until it is")
    else:
        what.append(f"{list_name} declares {label} not applicable: nothing is read or sent "
                    f"for it, and it never reads Default's")
    if removed:
        what.append(f"Removes {len(removed)} of {list_name}'s own {label} values from its "
                    "settings. They survive in the record of this change, which keeps each "
                    "one (a secret as it was stored, encrypted), so going back can restore them")
    if before["choice"] == NA and choice != NA:
        what.append(f"The declaration that {label} is not applicable here is withdrawn")
    what_not = ["Default's settings are not changed",
                "No device is contacted and no configuration changes",
                f"{list_name}'s other groups and its mode are unchanged"]
    return what, what_not


def plan_mode(list_name: str, to_mode: str) -> dict:
    """What making *list_name* inherit or standalone changes, group by group: only the groups
    still following the network's mode move (a group's own choice stands, its own values
    stay, a declaration stays). Writes nothing."""
    from modules.settings_schema import load_user_settings
    from modules.settings_scope import network_groups

    _refuse_default(list_name)
    if to_mode not in MODES:
        raise SwitchRefused(f"{to_mode!r} is not a mode: {', '.join(MODES)}")
    store = load(list_name)
    default_keys = frozenset(load_user_settings())
    after_doc = dict(_shape(json.loads(json.dumps(store))), mode=to_mode)
    rows = []
    for g in network_groups():
        b = group_state(list_name, g, store, default_keys)
        a = group_state(list_name, g, after_doc, default_keys)
        rows.append({"group": g, "label": b["label"], "today": b["words"],
                     "today_state": b["state"], "today_url": b["url"], "after": a["words"],
                     "after_state": a["state"], "after_url": a["url"],
                     "follows": b["follows"], "changes": b["state"] != a["state"]})
    moving = [r for r in rows if r["changes"]]
    unconfigured = [r["label"] for r in moving if r["after_state"] == "not_configured"
                    and r["today_state"] == "inherited"]
    picked = [r["label"] for r in moving if r["after_state"] == "inherited"]
    same = store["mode"] == to_mode
    gates = [{"gate": "a change", "state": "fail" if same else "pass",
              "why": (f"{list_name} is already {MODE_WORDS[to_mode]}" if same else
                      f"{MODE_WORDS[store['mode']]} to {MODE_WORDS[to_mode]}")}]
    what = []
    if to_mode == STANDALONE:
        what.append(f"{list_name} takes nothing from Default from now on: a group that has not "
                    "chosen for itself reads only what is set here")
        if unconfigured:
            what.append(f"{_and(unconfigured)} {'is' if len(unconfigured) == 1 else 'are'} "
                        f"inherited from Default today; after this "
                        f"{'it is' if len(unconfigured) == 1 else 'they are'} not configured "
                        f"for {list_name}")
    else:
        what.append(f"{list_name} inherits from Default from now on: a group that has not "
                    "chosen for itself reads Default's")
        if picked:
            what.append(f"{list_name} picks up Default's {_and(picked)}")
    kept = [r["label"] for r in rows if not r["follows"]]
    what_not = ["Nothing is deleted: no value set here is removed",
                "Default's values stay Default's, and every other network is unchanged",
                "No device is contacted and no configuration changes"]
    if kept:
        what_not.append(f"Groups with a choice, values or a declaration of their own keep "
                        f"them: {_and(kept)}")
    operands = {"list": list_name, "from": store["mode"], "to": to_mode,
                "rows": [[r["group"], r["today"], r["today_url"], r["after"], r["after_url"]]
                         for r in rows]}
    return {"list": list_name, "from": store["mode"], "to": to_mode, "rows": rows,
            "moving": moving, "unconfigured": unconfigured, "picked": picked,
            "what": what, "what_not": what_not, "gates": gates,
            "confirmable": not same, "operands": operands,
            "fingerprint": _fingerprint(operands)}


def _and(items: list) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _moved(seen: dict, now: dict) -> str:
    """What moved between the operands a person previewed (*seen*, as the page sent them
    back) and the operands now, row by row: both values, never a guessed cause."""
    if not isinstance(seen, dict):
        return "the preview's operands were not sent back, so what moved cannot be named"
    out = []
    if seen.get("from") != now.get("from"):
        out.append(f"it was {seen.get('from')!r} when previewed and is {now.get('from')!r} now")
    old = {str(r[0]): r for r in seen.get("rows") or [] if r}
    for r in now.get("rows") or []:
        o = old.get(str(r[0]))
        if o is not None and list(o) != list(r):
            out.append(f"{r[0]}: previewed as {' / '.join(map(str, o[1:]))}, now "
                       f"{' / '.join(map(str, r[1:]))}")
    return "; ".join(out) or ("what the page sent back as shown matches today's, so the "
                              "fingerprint it sent is not that preview's")


def _check(plan: dict, fingerprint: str, seen: dict) -> None:
    if not plan["confirmable"]:
        raise SwitchRefused("; ".join(g["why"] for g in plan["gates"] if g["state"] != "pass"))
    if plan["fingerprint"] != fingerprint:
        raise SwitchRefused(f"the settings moved since the preview (confirmed {fingerprint}, "
                            f"now {plan['fingerprint']}): {_moved(seen, plan['operands'])}. "
                            "Nothing was saved")


def _record(list_name: str, entry: dict) -> dict:
    """Append *entry* to the list's record, owner-only. The switch IS made when this runs:
    a record that cannot be written says so, first, rather than undoing it."""
    from modules.config import list_data_path, open_secure
    from modules.inventory_edit import actor_label

    entry = dict(entry, at=_now(), list=list_name,
                 actor_label=actor_label(entry.get("actor", ""),
                                         entry.get("actor_verified", "")))
    p = os.path.join(list_data_path(list_name), RECORD)
    try:
        with open_secure(p, "a") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        entry["recorded"] = True
    except OSError as exc:
        log.error("list settings: %s's %s switch made and NOT recorded: %s", list_name,
                  entry.get("kind"), exc)
        entry.update(recorded=False, record_error=f"{type(exc).__name__}: {exc}")
    return entry


#: Save's steps, in order (boards A and D: a card set here, Default's included, saves its
#: fields in place): the manual's How it works page names each.
SAVE_STEPS = ("check", "write", "record")


def save_values(list_name: str, group: str, values: dict, actor: str,
                actor_verified: str = "") -> dict:
    """Save a group's fields as the card sent them (boards A and D, approved 2026-10-05): the
    Default network's values (the base layer every inheriting network reads), or a network's
    own group. A group a network inherits or declared not applicable is refused, naming its
    state: its values are Default's, and making it the network's own is its switch, previewed.

    Only what changed is written; an empty secret keeps the stored one (a secret is never drawn
    back into the form). Recorded with the keys, never the values, in the network's settings
    record. ``{"ok", "label", "written", "unchanged", "recorded", ...}``."""
    from modules.secrets_store import SECRET_KEYS, set_secret
    from modules.settings_schema import get_setting
    from modules.settings_scope import group_keys, group_label

    keys = set(group_keys(group))
    if not keys:
        raise SwitchRefused(f"{group!r} is not a settings group")
    stray = sorted(set(values) - keys)
    if stray:
        raise SwitchRefused(f"{', '.join(stray)} {'is' if len(stray) == 1 else 'are'} not "
                            f"{group_label(group)}'s: a card saves its own group only")
    default = is_default(list_name)
    if not default:
        choice = group_choice(load(list_name), group)
        if choice != OWN:
            raise SwitchRefused(
                f"{group_label(group)} is not {list_name}'s own (it is "
                f"{CHOICE_WORDS.get(choice, choice)}): its values are not saved here. Make it "
                f"{list_name}'s own with its switch, which previews what moves")

    def now(k):
        return get_setting(k) if default else resolve(list_name, k)[0]

    plain = {k: v for k, v in values.items() if k not in SECRET_KEYS and v != now(k)}
    secrets = {k: v for k, v in values.items() if k in SECRET_KEYS and v}
    if plain:
        out = write(list_name, plain, actor=actor)
        if not out.get("ok"):
            raise SwitchRefused(f"Not saved: {out.get('error')}")
    if secrets:
        if default:
            for k, v in secrets.items():
                set_secret(k, v)
        else:
            out = write(list_name, secrets, actor=actor)
            if not out.get("ok"):
                raise SwitchRefused(f"Not saved: {out.get('error')}")
    written = sorted(plain) + sorted(secrets)
    unchanged = sorted(k for k in values if k not in written)
    if not written:
        return {"ok": True, "label": group_label(group), "group": group, "written": [],
                "unchanged": unchanged, "recorded": True, "nothing": True, "at": _now(),
                "actor_label": ""}
    entry = _record(list_name, {"kind": "values", "group": group, "written": written,
                                "actor": actor, "actor_verified": actor_verified})
    return dict(entry, ok=True, label=group_label(group), unchanged=unchanged)


def apply_group(list_name: str, group: str, choice: str, fingerprint: str, actor: str,
                actor_verified: str = "", values: dict = None, reason: str = "",
                seen: dict = None) -> dict:
    """Make the switch the person confirmed, and record it. Re-plans under the list's lock
    and the settings lock (Default's values are part of what was shown), and refuses a plan
    that moved, naming what moved."""
    from modules.config import settings_lock
    from modules.filestore import PathLock, StoreUnreadable, read_json_for_write

    if not actor:
        raise SwitchRefused("a switch records who made it, and no actor was given")
    p = path(list_name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with settings_lock(), PathLock(p):
        plan = plan_group(list_name, group, choice, values, reason)
        _check(plan, fingerprint, seen)
        try:
            doc = _shape(read_json_for_write(p, empty={}))
        except StoreUnreadable as exc:
            raise SwitchRefused(str(exc)) from exc
        removed, replaced = _transform_group(doc, group, choice,
                                             values if choice == OWN else {}, reason, actor)
        _write_store(p, doc)
    log.info("list settings: %s switched %s to %s for %s", actor, group, choice, list_name)
    return _record(list_name, {
        "kind": "group", "group": group, "label": plan["label"], "from": plan["from"],
        "to": choice, "reason": (reason or "").strip(), "what": plan["what"],
        "written": sorted(k for k, v in ((values or {}) if choice == OWN else {}).items()
                          if v is not None), "removed": removed,
        "replaced": replaced, "actor": actor, "actor_verified": actor_verified,
        "fingerprint": plan["fingerprint"]})


def apply_mode(list_name: str, to_mode: str, fingerprint: str, actor: str,
               actor_verified: str = "", seen: dict = None) -> dict:
    """Switch the network's mode as confirmed, and record it (which groups moved)."""
    from modules.config import settings_lock
    from modules.filestore import PathLock, StoreUnreadable, read_json_for_write

    if not actor:
        raise SwitchRefused("a switch records who made it, and no actor was given")
    p = path(list_name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with settings_lock(), PathLock(p):
        plan = plan_mode(list_name, to_mode)
        _check(plan, fingerprint, seen)
        try:
            doc = _shape(read_json_for_write(p, empty={}))
        except StoreUnreadable as exc:
            raise SwitchRefused(str(exc)) from exc
        doc["mode"] = to_mode
        _write_store(p, doc)
    log.info("list settings: %s made %s %s", actor, list_name, MODE_WORDS[to_mode])
    return _record(list_name, {
        "kind": "mode", "from": plan["from"], "to": to_mode, "what": plan["what"],
        "moved": [[r["group"], r["today"], r["after"]] for r in plan["moving"]],
        "actor": actor, "actor_verified": actor_verified, "fingerprint": plan["fingerprint"]})


def changes(list_name: str) -> dict:
    """The recorded switches, newest first. ``state``: ``absent`` (none yet), ``ok``, or
    ``unreadable`` (never read as none)."""
    from modules.config import list_data_path

    p = os.path.join(list_data_path(list_name), RECORD)
    if not os.path.exists(p):
        return {"state": "absent", "rows": []}
    try:
        with open(p, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [], "error": f"{type(exc).__name__}: {exc}"}
    return {"state": "ok", "rows": list(reversed(rows))}
