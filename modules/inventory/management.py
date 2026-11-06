"""What Mercury may change on a device it reads from NetBox (the SDN design, revision 4,
section 9a; C2606 and C2608).

Two facts, both NetBox's, decide it:

- **observe-only** (C2606, change D): NetBox's rendered ``config_context`` key
  ``mercury.management``, ``observe`` or ``manage``, default ``manage``. The RENDERED context
  is read (every context NetBox assigns by region, site, role, platform, tag and the rest,
  merged by weight, the device's own local config context data merged last, where it wins),
  never ``local_context_data`` alone. An observe device is read, captured and drift-REPORTED,
  and offered no deploy, restore, feature apply or heal: every device-changing operation
  refuses it, naming the key and where NetBox set it. A value that is neither word is read as
  ``observe`` (refusing by resemblance is safe; allowing by it is not), and said.
- **the host kind** (C2608, decision 5): a device whose role's ``mercury_kind`` is ``host`` is
  a Linux host Mercury manages services on (a controller), not a network device: excluded from
  goldens, deploys, config drift, heal, features, the fabric view's switch rows and interface
  monitoring. Its one declared write is controller management's deploy channel (the design's
  H), which P6 builds; until then it is refused, naming P6.

The inventory stamps the first on each device it loads (`netbox_source.adapt_devices`:
``_management`` and ``_management_from``); the kind is the device's ``role``. Every check
here reads the device dict or the loaded inventory: no NetBox call, no per-device work per
request beyond a dict lookup.
"""

import logging

log = logging.getLogger(__name__)

#: The config context key, as a path into the rendered context.
KEY = ("mercury", "management")
KEY_WORDS = "mercury.management"
OBSERVE, MANAGE = "observe", "manage"
MODES = (OBSERVE, MANAGE)
#: The kind of a Linux host Mercury manages services on (`role_kind.KINDS`).
HOST = "host"
#: Where the mark came from, in words a person checks in NetBox.
FROM_LOCAL = "the device's local config context"
FROM_ASSIGNED = ("a config context NetBox assigns to it (by region, site, role, platform, tag "
                 "or the like)")
FROM_DEFAULT = "not set in NetBox: manage is the default"
FROM_UNRENDERED = ("not read: NetBox's answer carried no rendered config context, so manage, "
                   "the default")

#: The operations a device that is observe-only, or a host, may still be held for: reads and
#: Mercury's own records (a capture commits a golden in git, never on the device). An
#: allowlist: an operation not named here is refused, so a new device-changing operation is
#: refused until it is judged and named.
MAY_HOLD = frozenset({
    "read", "capture", "rekey", "retire", "onboard", "onboard (create)", "abandon",
    "seed intent", "revert intent", "decline a profile section", "undo a decline",
    # A restart changes no configuration; its card judges its own gates, and a host's
    # session refuses `reload` as a discovery driver's write (modules/discovery.py).
    "reload",
})

#: A host has no golden and no intent (it is not a network device), so of those only the
#: reads and Mercury's own lifecycle records remain.
HOST_MAY_HOLD = frozenset({"read", "rekey", "retire", "onboard", "onboard (create)", "abandon",
                           "reload"})

#: What a host is excluded from, in the order the design names them (section 9a).
HOST_EXCLUDED = ("goldens", "deploys", "config drift", "heal", "features",
                 "the fabric view's switch rows", "interface monitoring")
#: Controller management's deploy channel: the host's one declared held write, built by P6.
HOST_HELD_WRITE = ("controller management's deploy channel (an app's files and the "
                   "controller's restart, the SDN design's H)")
HOST_WRITE_REFUSAL = ("REFUSED: controller management's deploy channel is declared as a "
                      "host's one held write and is not built yet: P6 (the SDN design's H) "
                      "builds it. Nothing was sent.")


def _get(ctx, path):
    for part in path:
        if not isinstance(ctx, dict) or part not in ctx:
            return None
        ctx = ctx[part]
    return ctx


def mark(raw: dict) -> dict:
    """``{"mode", "from", "problem"}`` for one raw NetBox device record: the mode from its
    RENDERED ``config_context``, and where NetBox set it (its local config context data when
    that holds the same value, else a context NetBox assigns; never read from the local data
    alone). *problem* is "" or why the value was read as observe."""
    raw = raw if isinstance(raw, dict) else {}
    if not isinstance(raw.get("config_context"), dict):
        return {"mode": MANAGE, "from": FROM_UNRENDERED, "problem": ""}
    value = _get(raw["config_context"], KEY)
    if value is None:
        return {"mode": MANAGE, "from": FROM_DEFAULT, "problem": ""}
    local = _get(raw.get("local_context_data") or {}, KEY)
    where = FROM_LOCAL if local is not None and local == value else FROM_ASSIGNED
    word = str(value).strip().lower() if isinstance(value, str) else ""
    if word in MODES:
        return {"mode": word, "from": where, "problem": ""}
    return {"mode": OBSERVE, "from": where,
            "problem": (f"{KEY_WORDS} is {value!r}, which is neither observe nor manage, so it "
                        "is read as observe")}


def is_host(dev: dict) -> bool:
    """Is *dev* a host (its role's ``mercury_kind`` is ``host``)?"""
    return str((dev or {}).get("role") or "").strip().lower() == HOST


def is_observe(dev: dict) -> bool:
    """Is *dev* observe-only (its inventory row's mark, from NetBox's rendered context)?"""
    return (dev or {}).get("_management") == OBSERVE


def excluded_from_config(dev: dict) -> bool:
    """Is *dev* kept out of goldens, deploys, config drift, heal and features (a host), or
    out of every change (an observe device)? Reads are still its."""
    return is_host(dev) or is_observe(dev)


def state_words(dev: dict) -> str:
    """The device's management state as its page names it: ``observe (<where>)``, ``host``,
    or "" for a device Mercury manages."""
    if is_host(dev):
        return "host: a Linux host Mercury reads and manages services on, not a network device"
    if is_observe(dev):
        return f"observe ({dev.get('_management_from') or FROM_ASSIGNED})"
    return ""


def refusal(dev: dict, what: str = "a device-changing operation") -> str:
    """"" when *what* may change *dev*, else the refusal naming the comparison: the key and
    where NetBox set it (observe), or the kind (host)."""
    dev = dev or {}
    name = dev.get("hostname") or dev.get("ip") or "the device"
    if is_host(dev):
        return (f"REFUSED: {what} on {name}: its role's mercury_kind is host, a Linux host "
                f"Mercury manages services on, not a network device, so it is kept out of "
                f"{', '.join(HOST_EXCLUDED)}. Its one write is {HOST_HELD_WRITE}, which P6 "
                "builds. Nothing was sent.")
    if is_observe(dev):
        where = dev.get("_management_from") or FROM_ASSIGNED
        problem = dev.get("_management_problem") or ""
        return (f"REFUSED: {what} on {name}: NetBox's config context sets {KEY_WORDS} to "
                f"observe ({where}{'; ' + problem if problem else ''}), so Mercury reads, "
                "captures and reports drift on it and changes nothing. Set it to manage in "
                "NetBox to allow changes. Nothing was sent.")
    return ""


def row_of(list_name: str, hostname: str) -> dict:
    """*hostname*'s row in *list_name*'s loaded inventory, or {} (absent, or a local list,
    whose rows carry no NetBox mark). No NetBox call: the inventory's cache."""
    if not list_name or not hostname:
        return {}
    try:
        from modules import inventory
        return inventory.cached_row(list_name, hostname) or {}
    except Exception as exc:                         # noqa: BLE001 - said, and judged absent
        log.warning("management: %s's row in %s could not be read: %s", hostname, list_name,
                    exc)
        return {}


def refusal_for(list_name: str, hostname: str, what: str = "a device-changing operation",
                dev: dict = None) -> str:
    """`refusal` for *hostname*, judged by *dev* when it carries the inventory's mark, else by
    its row in *list_name*'s loaded inventory."""
    if dev and ("_management" in dev or is_host(dev)):
        return refusal(dev, what)
    row = row_of(list_name, hostname)
    return refusal(row, what) if row else ""


def hold_refusal(list_name: str, hostname: str, operation: str) -> str:
    """Why *operation* may not hold *hostname* (`device_ops.acquire`): "" for an operation on
    `MAY_HOLD` (`HOST_MAY_HOLD` for a host), or for a device Mercury manages."""
    if operation in HOST_MAY_HOLD:
        return ""
    dev = row_of(list_name, hostname)
    if not dev or (operation in MAY_HOLD and not is_host(dev)):
        return ""
    return refusal(dev, what=operation or "an operation")
