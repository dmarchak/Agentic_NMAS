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
    list's slug when the group is the list's own (a key of it set here, chosen ``own``, or the
    network standalone and the group not chosen to inherit: NSOT_P8_DESIGN section 8, so a
    standalone network never shares Default's configuration or its store), or None when the
    list declared it not applicable. An unreadable list store raises
    (`ListSettingsUnreadable`): never guessed."""
    from modules import list_settings as L
    from modules.config import list_slug

    if L.is_default(list_name):
        return DEFAULT_GROUP
    choice = L.group_choice(L.load(list_name), group)
    if choice == L.NA:
        return None
    return list_slug(list_name) if choice == L.OWN else DEFAULT_GROUP


def configured(group: str, list_name: str) -> bool:
    """Whether *list_name*'s configuration of *group* names its service at all: its URL key
    (`settings_scope.URL_KEYS`) is set. A group with no URL key counts as configured."""
    from modules import list_settings as L
    from modules.settings_scope import URL_KEYS

    key = URL_KEYS.get(group)
    return not key or bool(str(L.resolve(list_name, key)[0] or "").strip())


def unconfigured(group_names: tuple, list_name: str) -> list:
    """The groups of *group_names* that are *list_name*'s own and name no service: with any,
    its configuration cannot be asked, so a reader skips it and a page says "not configured
    for this network", never a read failing every interval (section 8, step 5). Default's
    configuration is never skipped: it is read exactly as before P.8."""
    return [g for g in group_names
            if group_id(g, list_name) not in (None, DEFAULT_GROUP) and not configured(g, list_name)]


def who(group: str) -> dict:
    """Every network other than Default by what *group* is for it (board G): ``inherit`` (it
    takes Default's, whether by its mode or its own choice), ``own``, ``not_configured``,
    ``not_applicable``; and ``standalone``, the standalone networks among them all. A list
    whose store cannot be read is ``unreadable``, never counted as inheriting."""
    from modules import list_settings as L

    out = {"inherit": [], "own": [], "not_configured": [], "not_applicable": [],
           "standalone": [], "unreadable": []}
    bucket = {"inherited": "inherit", "unset_everywhere": "inherit", "own": "own",
              "not_configured": "not_configured", "not_applicable": "not_applicable"}
    for name in network_names():
        if L.is_default(name):
            continue
        try:
            store = L.load(name)
        except L.ListSettingsUnreadable:
            out["unreadable"].append(name)
            continue
        out[bucket[L.group_state(name, group, store)["state"]]].append(name)
        if store["mode"] == L.STANDALONE:
            out["standalone"].append(name)
    return out


def who_inherits(group: str) -> list:
    """The networks whose *group* resolves to Default's: what a change to Default's reaches."""
    return who(group)["inherit"]


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
    declared a group not applicable use none, and are not listed; nor is a configuration of
    a network's own that names no service (`unconfigured`): there is nothing to read, so no
    reader asks it, no store or liveness row is kept for it, and a fleet-wide merge leaves it
    out. Default's is first."""
    out = {}
    for name in network_names():
        gid = combined_id(tuple(groups_), name)
        if gid is None or unconfigured(tuple(groups_), name):
            continue
        out.setdefault(gid, {"id": gid, "lists": [], "list": name})["lists"].append(name)
    return sorted(out.values(), key=lambda g: (g["id"] != DEFAULT_GROUP, g["id"]))


def merged(group: str, fetch) -> tuple:
    """A fleet-wide read over every configuration of *group*, for a reader whose value is keyed
    by DEVICE across every list (adjacencies, restarts, platform facts). ``fetch(list_name)``
    returns ``(configured, {device: …}, …)`` for one configuration, ``""`` meaning Default's
    exactly as before P.8; it runs once per distinct configuration, and the answers merge:
    configured if any is, each mapping the union, a device two configurations report keeping
    the first (Default's). A configuration that raises fails the read, as one did before."""
    answers = []
    for g in groups((group,)):
        answers.append(fetch("" if g["id"] == DEFAULT_GROUP else g["list"]))
    if not answers:
        return (False,)
    width = len(answers[0])
    out = [any(a[0] for a in answers)] + [{} for _ in range(width - 1)]
    for a in answers:
        for i in range(1, width):
            for k, v in (a[i] or {}).items():
                out[i].setdefault(k, v)
    return tuple(out)


def store_name(reader_name: str, gid: str) -> str:
    """The store a configuration's value lives in: the reader's own name for Default's (so a
    single-network installation's stores are what they always were), else ``name@id``."""
    return reader_name if gid == DEFAULT_GROUP else f"{reader_name}@{gid}"
