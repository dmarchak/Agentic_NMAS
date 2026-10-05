"""Which network's settings supply an integration, for every list (P.8 step 5).

Two lists are two networks, and an integration inherits as a GROUP (`settings_scope`): a list
that sets none of Grafana's keys reads Default's Grafana; a list that sets one owns the whole
group; a list may declare the group not applicable. So across N lists there are at most N+1
distinct configurations of one integration, and usually one. A reader that serves every list
reads each distinct configuration ONCE and keys its value by it (NSOT_P8_DESIGN section 4:
"one Grafana serving three networks is read once and its value shared").

The identity of a configuration is the network whose layer supplies it: `default`, or the slug
of the list that set it. Two lists that set identical values are still two configurations
(their credentials are each their own); the read is cheap next to the harm of sending one
network's token to another's address.
"""

import logging

log = logging.getLogger(__name__)

DEFAULT_GROUP = "default"


def group_id(group: str, list_name: str):
    """The configuration of settings group *group* that *list_name* uses: ``"default"``, the
    list's slug when the list set the group itself, or None when the list declared it not
    applicable. An unreadable list store raises (`ListSettingsUnreadable`): never guessed."""
    from modules import list_settings as L
    from modules.config import list_slug
    from modules.settings_scope import group_keys

    if L.is_default(list_name):
        return DEFAULT_GROUP
    store = L.load(list_name)
    keys = group_keys(group)
    if group in store["not_applicable"] or any(k in store["not_applicable"] for k in keys):
        return None
    if any(k in store["values"] for k in keys):
        return list_slug(list_name)
    return DEFAULT_GROUP


def combined_id(group_names: tuple, list_name: str):
    """The configuration of several groups at once (a reader that reads Prometheus AND Loki):
    ``"default"`` when every group is Default's, None when any is not applicable, else the
    parts joined with ``+``."""
    parts = [group_id(g, list_name) for g in group_names]
    if any(p is None for p in parts):
        return None
    if all(p == DEFAULT_GROUP for p in parts):
        return DEFAULT_GROUP
    return "+".join(parts)


def network_names() -> list:
    """Every registered list's name, Default first and always present."""
    # The registry's names only: `get_device_lists()` loads every list's devices to count them,
    # too much for a reader that runs every minute.
    from modules.device import _load_device_lists_config
    from modules.list_settings import DEFAULT_LIST, is_default

    names = [DEFAULT_LIST]
    for name in sorted((_load_device_lists_config() or {}).get("lists") or {}):
        if name and not is_default(name) and name not in names:
            names.append(name)
    return names


def groups(groups_: tuple) -> list:
    """``[{"id", "lists", "list"}]``: each distinct configuration of *groups_* across every
    network, the lists that use it, and the one whose client reads it (the first). Lists that
    declared a group not applicable use none, and are not listed. Default's is first."""
    out = {}
    for name in network_names():
        gid = combined_id(tuple(groups_), name)
        if gid is None:
            continue
        out.setdefault(gid, {"id": gid, "lists": [], "list": name})["lists"].append(name)
    return sorted(out.values(), key=lambda g: (g["id"] != DEFAULT_GROUP, g["id"]))


def store_name(reader_name: str, gid: str) -> str:
    """The store a configuration's value lives in: the reader's own name for Default's (so a
    single-network installation's stores are what they always were), else ``name@id``."""
    return reader_name if gid == DEFAULT_GROUP else f"{reader_name}@{gid}"
