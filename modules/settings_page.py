"""The v2 Settings page per network (P.8 step 7; boards A to J, approved 2026-10-05).

What the page draws, from `list_settings` alone, so the screen and the resolver cannot
disagree:

- **the scope bar** (board H): Installation (every network), Default (the base for the
  networks that inherit) and one network, with a picker that leads with the networks that
  differ from Default: the standalone ones first, then those inheriting with values of their
  own, then the ones inheriting everything, one collapsed group;
- **a network's mode** (boards I and J): inherits from Default, or standalone, with who made
  it so and when (the list's settings record);
- **one card per group** (boards A and I): its state as a chip, its three-way choice
  (inherit, its own, not applicable) for a network, and every field's value with where it
  came from. A secret is "set" or "unset", never its value; a URL goes through the redactor;
- **Default's cards** (boards D and G): each names who takes its values, counting only the
  networks that chose to inherit, with own, not configured and not applicable apart.

Reads only: it writes nothing and creates no list (a page asked about a list nobody has is
refused by `routes/list_param`, before this runs).
"""

import json
import logging

log = logging.getLogger(__name__)

#: The tabs a network's settings are split across, and the groups on each. Integrations are
#: the outside services; Network is the deploy tuning and the network's own addresses. Board
#: A's host-wide tabs (AI, Server, Security posture, Diagnostics) are Installation's (F).
INTEGRATIONS = ("grafana", "grafana_roles", "prometheus", "loki", "kea",
                "topology_service", "monitoring_profile", "s3_archive", "lab")
TABS = (("integrations", "Integrations"), ("network", "Network"))

#: A chip's colour for each state (the page's tokens): a state to act on leads in colour.
STATE_KIND = {"own": "ok", "inherited": "info", "not_configured": "warn",
              "unset_everywhere": "warn", "not_applicable": "muted"}

#: The words a field label is built from: the key without its service's prefix.
_PREFIXES = ("grafana_", "prometheus_", "loki_", "kea_", "topology_service_",
             "s3_", "syslog_", "nsot_")
_ACRONYMS = {"url": "URL", "tls": "TLS", "uid": "UID", "db": "DB", "ip": "IP", "vrfs": "VRFs",
             "ntp": "NTP", "snmp": "SNMP", "ztp": "ZTP", "dhcp4": "DHCPv4", "id": "ID"}


def field_label(key: str) -> str:
    """A setting's label from its key: ``grafana_fleet_dashboard_uid`` is "Fleet dashboard
    UID"; a group of one keeps its whole key's words."""
    words = key
    for p in _PREFIXES:
        if key.startswith(p) and len(key) > len(p):
            words = key[len(p):]
            break
    parts = [_ACRONYMS.get(w, w) for w in words.split("_")]
    text = " ".join(parts)
    return text[:1].upper() + text[1:]


def tab_groups(tab: str) -> tuple:
    from modules.settings_scope import network_groups

    groups = network_groups()
    if tab == "network":
        return tuple(g for g in groups if g not in INTEGRATIONS)
    return tuple(g for g in INTEGRATIONS if g in groups)


def _fields(list_name: str, group: str, store: dict) -> list:
    from modules import list_settings as L
    from modules.secrets_store import SECRET_KEYS
    from modules.settings_scope import group_keys

    out = []
    for k in group_keys(group):
        value, origin = L.resolve(list_name, k, store)
        out.append({"key": k, "label": field_label(k), "value": L.shown(k, value),
                    "origin": origin, "secret": k in SECRET_KEYS})
    return out


def card(list_name: str, group: str, store: dict = None, default_keys=None) -> dict:
    """One group's card for the network *list_name* (never Default: see `default_card`)."""
    from modules import list_settings as L

    store = L.load(list_name) if store is None else store
    st = L.group_state(list_name, group, store, default_keys)
    decl = {}
    if st["state"] == "not_applicable":
        keys = [group] + [k for k in store["not_applicable"] if k != group]
        decl = next((store["not_applicable"][k] for k in keys if k in store["not_applicable"]),
                    {})
    return dict(st, kind=STATE_KIND[st["state"]], fields=_fields(list_name, group, store),
                declaration=decl, choices=[{"value": c, "words": L.CHOICE_WORDS[c],
                                            "on": c == st["choice"]} for c in L.CHOICES])


def default_card(group: str, who: dict = None) -> dict:
    """One group's card on Default's view: its values (Default's own layer) and who takes
    them (board G), counting only the networks that chose to inherit."""
    from modules import integration_groups as IG
    from modules import list_settings as L
    from modules.settings_schema import load_user_settings
    from modules.settings_scope import group_keys, group_label

    who = IG.who(group) if who is None else who
    fields = _fields(L.DEFAULT_LIST, group, None)
    set_any = any(k in load_user_settings() for k in group_keys(group))
    return {"group": group, "label": group_label(group), "state": "own" if set_any else
            "unset_everywhere", "words": L.SET_HERE if set_any else "unset",
            "kind": "ok" if set_any else "warn", "fields": fields, "who": who,
            "inherited_by": len(who["inherit"])}


def _network_summary(name: str, store: dict, groups: tuple, default_keys) -> dict:
    """One row of the picker: the network, its mode, and what of it differs from Default."""
    from modules import list_settings as L

    parts = {"own": [], "not_configured": [], "not_applicable": [], "inherit": []}
    for g in groups:
        st = L.group_state(name, g, store, default_keys)
        if st["state"] == "own":
            parts["own"].append(st["label"])
        elif st["state"] == "not_configured":
            parts["not_configured"].append(st["label"])
        elif st["state"] == "not_applicable":
            parts["not_applicable"].append(st["label"])
        elif store["mode"] == L.STANDALONE:
            parts["inherit"].append(st["label"])         # a standalone group that chose to
    differs = any(parts[k] for k in ("own", "not_configured", "not_applicable"))
    return {"name": name, "mode": store["mode"], "parts": parts,
            "bucket": ("standalone" if store["mode"] == L.STANDALONE else
                       "differs" if differs else "inherits")}


def scope_bar(current: str) -> dict:
    """Board H: the three scopes and the picker. A list whose store cannot be read is its
    own row, never counted as inheriting."""
    from modules import integration_groups as IG
    from modules import list_settings as L
    from modules.settings_schema import load_user_settings
    from modules.settings_scope import network_groups

    default_keys = frozenset(load_user_settings())
    groups = network_groups()
    rows, unreadable = [], []
    for name in IG.network_names():
        if L.is_default(name):
            continue
        try:
            store = L.load(name)
        except L.ListSettingsUnreadable:
            unreadable.append(name)
            continue
        rows.append(_network_summary(name, store, groups, default_keys))
    buckets = {b: [r for r in rows if r["bucket"] == b]
               for b in ("standalone", "differs", "inherits")}
    total = len(rows) + len(unreadable) + 1
    return {"current": current, "is_default": L.is_default(current), "networks": total,
            "inheriting": len(buckets["differs"]) + len(buckets["inherits"]),
            "standalone": buckets["standalone"], "differs": buckets["differs"],
            "inherits": buckets["inherits"], "unreadable": unreadable,
            "others": total - 1}


def mode_since(list_name: str) -> dict:
    """Who made the network's current mode, and when, from its settings record: the newest
    mode switch. ``{}`` when it has never been switched (every network starts inheriting)."""
    from modules import list_settings as L

    got = L.changes(list_name)
    if got["state"] != "ok":
        return {"state": got["state"], "error": got.get("error", "")}
    for r in got["rows"]:
        if r.get("kind") == "mode":
            return {"state": "ok", "at": r.get("at"), "by": r.get("actor_label") or
                    r.get("actor"), "to": r.get("to")}
    return {}


def form_fields(list_name: str, group: str) -> list:
    """The inputs of a group's "its own" card (boards B and I): each key, its kind, and the
    value it starts from: today's (the network's own, or Default's it inherits, so a person
    starts from what works). A secret never starts from anything: it is entered, and an empty
    one keeps what is stored. A value the redactor would change (a URL carrying a credential)
    starts empty and says why: a masked value saved back would replace the real one."""
    from modules import list_settings as L
    from modules.secrets_store import SECRET_KEYS
    from modules.settings_schema import DEFAULTS
    from modules.settings_scope import group_keys

    out = []
    for k in group_keys(group):
        value, origin = L.resolve(list_name, k)
        d = DEFAULTS.get(k)
        kind = ("secret" if k in SECRET_KEYS else "switch" if isinstance(d, bool) else
                "number" if isinstance(d, int) else "json" if isinstance(d, (list, dict))
                else "text")
        start, note = "", ""
        if kind == "secret":
            if L.is_default(list_name):
                # Default's secrets live in the secrets store, never in its settings file.
                from modules.secrets_store import is_set
                note = "set: leave empty to keep it" if is_set(k) else "unset: enter one"
                origin = L.SET_HERE if is_set(k) else L.UNSET_EVERYWHERE
            else:
                note = ("set: leave empty to keep it" if value and origin == L.SET_HERE else
                        f"enter {list_name}'s own: Default's is never copied")
        elif kind == "switch":
            start = "on" if value else "off"
        elif kind == "number":
            start = "" if value in (None, "") else str(value)
        elif value not in (None, "", [], {}):
            raw = json.dumps(value, sort_keys=True) if kind == "json" else str(value)
            if L.shown(k, value) != raw:
                note = "it holds a credential, so it is not shown: enter it again"
            else:
                start = raw
        out.append({"key": k, "label": field_label(k), "kind": kind, "value": start,
                    "note": note, "origin": origin})
    return out


def tab_of(group: str) -> str:
    return "integrations" if group in INTEGRATIONS else "network"


def is_group(group: str) -> bool:
    from modules.settings_scope import network_groups

    return group in network_groups()


def integration_for(group: str):
    """The integration a group configures, for its Test: the client whose URL key is the
    group's (`settings_scope.URL_KEYS`); None for a group with none (the deploy tuning, the
    monitoring profile)."""
    from modules.integrations import REGISTRY
    from modules.settings_scope import URL_KEYS

    url_key = URL_KEYS.get(group)
    return next((cls for cls in REGISTRY.values() if url_key and cls.url_key == url_key), None)


def _editing(list_name: str, group: str, c: dict) -> dict:
    """Boards A and D (approved 2026-10-05): a card set here, Default's included, takes its
    fields in place, with Save and Test. ``editable``, ``inputs`` (`form_fields`) and
    ``testable`` added to the card *c*."""
    from modules import list_settings as L

    editable = L.is_default(list_name) or c.get("state") == "own"
    c["editable"] = editable
    c["inputs"] = form_fields(list_name, group) if editable else []
    c["testable"] = editable and integration_for(group) is not None
    return c


def one_card(list_name: str, group: str) -> dict:
    """One group's card alone (a card drawn again after Cancel, a switch, a Save or a Test)."""
    from modules import list_settings as L

    c = default_card(group) if L.is_default(list_name) else card(list_name, group)
    return _editing(list_name, group, c)


def network_view(list_name: str, tab: str = "integrations") -> dict:
    """Everything a network's Settings page draws for *tab*. An unreadable store is said, and
    nothing of the network is drawn as if it were known."""
    from modules import list_settings as L
    from modules.settings_schema import load_user_settings

    tab = tab if tab in dict(TABS) else "integrations"
    out = {"network": list_name, "tab": tab, "tabs": TABS, "scope": scope_bar(list_name),
           "is_default": L.is_default(list_name), "cards": [], "error": ""}
    try:
        if out["is_default"]:
            out["cards"] = [_editing(list_name, g, default_card(g)) for g in tab_groups(tab)]
            return out
        store = L.load(list_name)
    except L.ListSettingsUnreadable as exc:
        out["error"] = str(exc)
        return out
    default_keys = frozenset(load_user_settings())
    out.update(mode=store["mode"], mode_words=L.MODE_WORDS[store["mode"]],
               since=mode_since(list_name),
               cards=[_editing(list_name, g, card(list_name, g, store, default_keys))
                      for g in tab_groups(tab)])
    out["summary"] = _network_summary(list_name, store, tab_groups("integrations"),
                                      default_keys)["parts"]
    return out
