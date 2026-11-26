"""Where every setting is set (Stage 5 step 2; the operator's GUI pick of 2026-11-25, C: "one
searchable document"), and the search over them.

A declared setting (`settings_scope.SCOPES`, a network's or the host's) has one HOME: the page,
the tab and the section a person sets it in. Most are derived, so a new one is placed the
moment it is declared:

- a network group with a generic card (`settings_page.tab_groups`): its network's Settings,
  the card's tab, ``card-<group>``;
- an installation card (`installation_settings.CARDS`): Settings › Installation, its tab,
  ``card-<name>``.

The groups drawn by their own templates are declared in `OWN_HOMES`, each by the section id
its template gives it, and a key inside one may name a closer section (`KEY_HOMES`). A group
with no screen is in `NO_SCREEN` with why; that list only shrinks. tests/test_settings_index.py
holds that every declared setting has exactly one of them, and that each home's page, fetched,
draws its section.

The search (`find`) reads only declarations: each setting's label (`settings_page.field_label`
or its card's), its description (`settings_schema.DESCRIPTIONS`), its group's label and its key;
it writes nothing and reads no value.
"""

import logging

log = logging.getLogger(__name__)

#: The page kinds a home names, each with how its address is made (`href`).
NETWORK, INSTALLATION, SDN, CREDENTIALS = "network", "installation", "sdn", "credentials"

#: Groups drawn by their own templates: ``group: (page, tab, section id)``.
OWN_HOMES = {
    "heal_policy": (NETWORK, "heal", "heal-guards"),
    "heal_notify": (NETWORK, "heal", "heal-told"),
    "heal_kill_switch": (NETWORK, "heal", "heal-kill"),
    "network_stage": (NETWORK, "heal", "heal-mode"),
    "code_repository": (NETWORK, "network", "code-repo-card"),
    "ai_device_state": (NETWORK, "network", "ai-classes"),
    "sdn_controllers": (NETWORK, "integrations", "sdn-card"),
    "identity": (INSTALLATION, "access", "card-access"),
    "records_db": (INSTALLATION, "connections", "records-db"),
    "platforms": (INSTALLATION, "platforms", "card-platform-map"),
    "sdn_detection": (SDN, "responses", "sdn-rules-h"),
    "sdn_responses": (SDN, "responses", "sdn-policy-h"),
    "sdn_response_policy": (SDN, "responses", "sdn-policy-h"),
    "credential_rotation": (CREDENTIALS, "profiles", "cp-rotation"),
}

#: A key whose own section is closer than its group's: ``key: section id`` on the group's page
#: and tab.
KEY_HOMES = {
    "heal_mode": "heal-mode", "heal_mode_until": "heal-mode", "heal_policy_confirmed": "heal-mode",
    "heal_kinds_auto": "heal-kinds", "heal_kinds_propose": "heal-kinds",
    "local_account_enabled": "card-local-account",
    "service_allowed_operations": "card-services", "cf_access_service_labels": "card-services",
    "platform_default_netmiko_type": "card-platform-map",
}
KEY_HOMES.update({k: "card-gates" for k in (
    "require_same_origin_writes", *(f"require_{w}_for_{op}" for w in ("identity", "person")
                                    for op in ("approve", "break_glass", "configure", "confirm",
                                               "publish_remote", "reveal")))})

#: Groups no screen sets, with why: ``group: why``. Only shrinks (tests/test_settings_index.py).
NO_SCREEN = {
    "schema": "the settings file's own version, written by the migration, never a person",
    "settings_not_applicable": "the Default network's record of the groups declared not "
                               "applicable, written by each group's switch",
    "installation_kind": "written by the laptop kit's init, never by a screen",
    "lab_demo": "lab tooling's script path, set by the lab's own setup",
    "ai_read_account": "C4266: no screen sets whether AI reads may ping and traceroute",
    "no_change_windows": "C4266: no screen sets the no-change windows",
}


def home(key: str) -> dict:
    """*key*'s home: ``{"page", "tab", "section", "group"}``, or ``{"none": why}`` for a
    setting no screen sets. KeyError names an undeclared key (`settings_scope.scope_of`)."""
    from modules import installation_settings as I
    from modules import settings_page as P
    from modules.settings_scope import scope_of

    scope, group = scope_of(key)
    if group in NO_SCREEN:
        return {"group": group, "none": NO_SCREEN[group]}
    if group in OWN_HOMES:
        page, tab, section = OWN_HOMES[group]
        return {"group": group, "page": page, "tab": tab, "section": KEY_HOMES.get(key, section)}
    if scope == "network" and P.is_group(group):
        return {"group": group, "page": NETWORK, "tab": P.tab_of(group),
                "section": f"card-{group}"}
    for name, spec in I.CARDS.items():
        if spec["group"] == group:
            return {"group": group, "page": INSTALLATION, "tab": spec["tab"],
                    "section": f"card-{name}"}
    return {"group": group, "none": ""}


def settable() -> list:
    """Every setting a person may set somewhere: the network's and the host's keys
    (`settings_scope.SCOPES`), never the retiring or dead ones."""
    from modules.settings_scope import SCOPES
    return sorted(k for k, (scope, _g) in SCOPES.items() if scope in ("network", "host"))


def href(h: dict, network: str) -> str:
    """The address of home *h*, its section the fragment, *network* the network a network
    page is of."""
    from flask import url_for

    page, tab, section = h["page"], h["tab"], h["section"]
    if page == NETWORK:
        base = url_for("settings_v2.network", list_name=network, tab=tab)
    elif page == INSTALLATION:
        base = url_for("settings_v2.installation", tab=tab)
    elif page == SDN:
        base = url_for("sdn_v2.responses", list=network)
    else:
        base = url_for("credential_profiles_v2.page", list=network)
    return f"{base}#{section}"


#: The words a home's page and tab are named by, as the page draws them.
_PAGES = {NETWORK: "Settings › {network}", INSTALLATION: "Settings › Installation",
          SDN: "SDN", CREDENTIALS: "Credentials"}


def where_words(h: dict, network: str) -> str:
    """"Settings › Branch › Network": the page and the tab, as their own tabs name them."""
    from modules import installation_settings as I
    from modules import settings_page as P

    tabs = dict(P.TABS) if h["page"] == NETWORK else dict(I.TABS) if \
        h["page"] == INSTALLATION else {"responses": "Responses", "profiles": "Profiles"}
    return _PAGES[h["page"]].format(network=network) + " › " + tabs.get(h["tab"], h["tab"])


#: The most a search draws (the rest counted, never a long expanded list).
MOST = 40


def find(q: str, network: str) -> dict:
    """The settings matching *q* (every word of it, in any case, in the setting's label, its
    description, its group's label or its key), each with where it is set and the address
    there: ``{"q", "matches": [...], "count", "shown", "pages": {words: n}}``. An empty *q*
    finds nothing; a setting no screen sets is found with why."""
    from modules import installation_settings as I
    from modules import settings_page as P
    from modules.settings_schema import DESCRIPTIONS
    from modules.settings_scope import group_label

    words = [w for w in (q or "").lower().split() if w]
    out = {"q": (q or "").strip(), "matches": [], "count": 0, "shown": 0, "pages": {}}
    if not words:
        return out
    labels = {f["key"]: f["label"] for spec in I.CARDS.values() for f in spec["fields"]}
    for spec in I.CARDS.values():
        for pair in (spec.get("secret"), spec.get("with_id")):
            if pair:
                labels[pair[0]] = pair[1]
    found = []
    for key in settable():
        h = home(key)
        label = labels.get(key) or P.field_label(key)
        desc = DESCRIPTIONS.get(key, "")
        glabel = group_label(h["group"])
        text = " ".join((label, desc, glabel, key)).lower()
        if not all(w in text for w in words):
            continue
        row = {"key": key, "label": label, "desc": desc, "group": glabel}
        if "none" in h:
            row.update(where="set by no screen", why=h["none"], href="")
        else:
            row.update(where=where_words(h, network), href=href(h, network))
        found.append(row)
    out["count"] = len(found)
    for r in found:
        out["pages"][r["where"]] = out["pages"].get(r["where"], 0) + 1
    out["matches"] = found[:MOST]
    out["shown"] = len(out["matches"])
    return out
