"""nsot/platform.py

Resolving which **config dialect** a device speaks.

``device_type`` in ``devices.csv`` is a Netmiko driver name. It answers "how do
I open a session to this box" — terminal handling, prompt detection, paging,
which command saves the config. It is not a statement about configuration
syntax, and it is deliberately coarse: ``cisco_ios`` is a *correct* Netmiko
driver for a C8000v running IOS-XE, because the session behaves the same way.

Parser selection needs a different answer: which config dialect to parse and
render. A C8000v has ``vrf definition`` blocks with address families, telemetry
subscriptions, NETCONF settings and IP SLA that a vIOS-L2 does not.

Keying the parser off ``device_type`` conflates the two. The visible symptom is
that every IOS-XE router parses with the IOS parser and its NETCONF, telemetry
and VRF config all falls into ``unmodeled``. The invisible one is worse: the fix
looks like "change device_type to cisco_xe", which alters **transport**
behaviour in order to influence a **parsing** decision.

NetBox-sourced lists already separate these — the platform map keys on a NetBox
platform slug. Local CSV lists simply had no platform concept. This module adds
one, with a derivation fallback so lists that predate it keep working unchanged.
"""

import logging

log = logging.getLogger(__name__)

#: THERE IS NO DEFAULT DIALECT (C452, the operator, 2026-10-04). An unknown device
#: was read as `cisco_ios`: a FortiGate in a CSV list would have been parsed with
#: IOS's parser, rendered from IOS's templates and recorded as an IOS golden. An
#: unknown platform is the answer "", and whatever needs a dialect refuses it,
#: naming the device and what it reports (`UnknownPlatform`, `unknown_words`).

#: Netmiko driver → config dialect, used only when no platform is recorded.
#: Five Cisco drivers whose dialect is certain; any other driver is unknown,
#: never guessed.
_DERIVED_FROM_DEVICE_TYPE = {
    "cisco_ios":     "cisco_ios",
    "cisco_xe":      "cisco_iosxe",
    "cisco_xe_ssh":  "cisco_iosxe",
    "cisco_ios_ssh": "cisco_ios",
    "cisco_iosxe":   "cisco_iosxe",
}

#: NetBox platform slug → config dialect.
_FROM_NETBOX_SLUG = {
    "cisco-ios":    "cisco_ios",
    "cisco-ios-xe": "cisco_iosxe",
    "cisco_ios":    "cisco_ios",
    "cisco_iosxe":  "cisco_iosxe",
}


#: The config dialects this program speaks. **The canonical namespace.**
#:
#: Only this form is ever stored or compared: the manifest records it, the
#: parsers key on it, and so do the template directories and
#: `bootstrap_config`. A NetBox platform **slug** (`cisco-ios-xe`) and a
#: Netmiko **driver** (`cisco_xe`) are inputs, translated here and never
#: stored.
#:
#: That is why there is no `PlatformRef`. `ListRef` exists because a list's
#: name and its slug are BOTH stored and compared to each other; a platform
#: has one stored form and two input formats, which is a translation problem
#: rather than an identity one.
DIALECTS = frozenset({"cisco_ios", "cisco_iosxe"})


def is_dialect(value: str) -> bool:
    """Is *value* a config dialect, as opposed to a slug or a driver?"""
    return (value or "").strip() in DIALECTS


class UnknownPlatform(ValueError):
    """A device whose config dialect the tool does not know (C452). Its words
    name the device, what its inventory row says and what the device reports."""


def _reported(hostname: str) -> str:
    """What *hostname* says it is, from the `platform-facts` store (C426): its
    own SNMP sysDescr. A store read, never a device or Prometheus read."""
    try:
        from modules.readers import platform_facts
        devices, _at, why = platform_facts.facts()
    except Exception as exc:                   # noqa: BLE001 - the words, never a crash
        return f"what it reports could not be read ({exc})"
    if why:
        return f"what it reports is not known ({why})"
    descr = ((devices.get(hostname) or {}).get("descr") or "").strip()
    if not descr:
        return f"it reports nothing yet (Prometheus holds no sysDescr for {hostname})"
    return f"it reports '{descr}' (its SNMP sysDescr)"


def unknown_words(device: dict) -> str:
    """Why *device*'s platform is refused: the device, its row, its report."""
    name = (device.get("hostname") or "").strip() or "this device"
    said = [f"{label} '{(device.get(key) or '').strip()}'"
            for key, label in (("platform", "platform"), ("_platform", "NetBox platform"),
                               ("device_type", "device_type"))
            if (device.get(key) or "").strip()]
    return (f"{name}: the tool does not know its platform, and refuses rather than read it "
            f"as another. Its inventory row says {', '.join(said) or 'no platform and no device_type'}; "
            f"{_reported(name)}. The platforms the tool knows: {', '.join(sorted(DIALECTS))}")


def require_platform(device: dict) -> str:
    """*device*'s config dialect, or `UnknownPlatform` naming it. For anything
    that parses, renders, records or sends: never a guessed dialect."""
    dialect = platform_for_device(device)
    if is_dialect(dialect):
        return dialect
    raise UnknownPlatform(unknown_words(device))


def assert_dialect(value: str, where: str = "") -> str:
    """Return *value*, or raise if it is not a dialect.

    **A dictionary lookup that misses returns the default**, and in a gate
    the default is "allowed". Measured: `/onboard/platforms` looked NetBox
    slugs up in a dialect-keyed table, found nothing, and reported every
    platform unblocked — including the one stage D blocks. No error, no log
    line, a refusal that had been written, tested and documented quietly not
    applying.

    So a boundary that requires a dialect says so, and says what to call
    instead. Cheaper than a `PlatformRef` and it addresses the actual failure:
    not two identities being confused, but an input format reaching a table
    keyed on the canonical one.
    """
    value = (value or "").strip()
    if not is_dialect(value):
        raise ValueError(
            f"{where or 'this'} expects a config dialect "
            f"({', '.join(sorted(DIALECTS))}), got {value!r}. A NetBox "
            "platform slug or a Netmiko driver must go through "
            "platform_for_device() first.")
    return value


#: Config dialect → the Oxidized model that backs it up (C512): the name of Oxidized's model
#: file, which is what a router.db row's second field names. Oxidized's `ios` model reads both
#: IOS and IOS-XE (its REST node list reports the class as `IOS`; every node of this lab's fleet,
#: routers and switches, was read so on 2026-10-06).
_OXIDIZED_MODEL = {
    "cisco_ios":   "ios",
    "cisco_iosxe": "ios",
}


def oxidized_model_for_dialect(dialect: str) -> str:
    """The Oxidized model for *dialect*; raises `ValueError` for one with none (never another
    dialect's model)."""
    wanted = assert_dialect(dialect, where="oxidized_model_for_dialect()")
    model = _OXIDIZED_MODEL.get(wanted, "")
    if not model:
        raise ValueError(f"no Oxidized model is known for dialect '{wanted}'")
    return model


def dialect_for_netbox_slug(slug: str) -> str:
    """The config dialect a NetBox platform *slug* names, or ``""`` when it
    names none this program knows (the table, then the `platform_map`
    setting). ``""`` is an answer: NetBox's `ios` (register A4) maps to
    nothing, and defaulting it would hide that."""
    slug = (slug or "").strip().lower()
    if not slug:
        return ""
    mapped = _FROM_NETBOX_SLUG.get(slug)
    if mapped:
        return mapped
    from modules.settings_schema import get_setting
    entry = (get_setting("platform_map", {}) or {}).get(slug, {})
    template_dir = (entry.get("template_dir") or "").strip()
    return template_dir.replace("-", "_") if template_dir else ""


def platform_for_device(device: dict) -> str:
    """Config dialect for *device*, in order of decreasing authority.

    1. an explicit ``platform`` column — the operator said so
    2. ``_platform``, the NetBox platform slug carried by the inventory adapter
    3. derived from ``device_type``, one of five Cisco drivers whose dialect is certain
    4. ``""``: unknown, never a default (C452). `require_platform()` refuses it.
    """
    explicit = (device.get("platform") or "").strip().lower()
    if explicit:
        return _FROM_NETBOX_SLUG.get(explicit, explicit)

    netbox_slug = (device.get("_platform") or "").strip().lower()
    if netbox_slug:
        mapped = dialect_for_netbox_slug(netbox_slug)
        if mapped:
            return mapped

    device_type = (device.get("device_type") or "").strip().lower()
    if device_type:
        derived = _DERIVED_FROM_DEVICE_TYPE.get(device_type)
        if derived:
            return derived
        log.info("platform: device_type %r on %s names no dialect the tool knows; "
                 "its platform is unknown", device_type, device.get("hostname", "?"))

    return ""


def netmiko_type_for_dialect(dialect: str) -> str:
    """Config dialect -> the Netmiko driver that opens a session to it.

    Added for phase 2, which knows a device's **dialect** (that is what the
    manifest stores) and must open an SSH session (which needs a driver).

    **Here, and only here.** The alternative was a `device_type` default in
    `routes/onboard.py`, which `test_platform_keying` caught as an
    undeclared platform literal -- correctly, because hardcoding `cisco_xe`
    is the C8000v's driver asserted as every device's. A second copy of the
    mapping is how the two come to disagree, and a test asserts there is
    exactly one.

    Refuses rather than defaulting: opening a session with the wrong driver
    fails in ways that read as the device's fault.
    """
    from modules.settings_schema import get_setting

    wanted = assert_dialect(dialect, where="netmiko_type_for_dialect()")
    for slug, entry in (get_setting("platform_map", {}) or {}).items():
        if platform_for_device({"platform": slug}) == wanted:
            driver = (entry.get("netmiko_device_type") or "").strip()
            if driver:
                return driver
    raise ValueError(
        f"no Netmiko driver is mapped for dialect '{wanted}'. Add one to "
        f"platform_map in Settings -> Integrations.")


def netmiko_type_for_device(device: dict) -> str:
    """The Netmiko driver — how to open a session: the row's own, else the one
    mapped for its dialect, else `UnknownPlatform` (never `cisco_ios` by default,
    C452)."""
    driver = (device.get("device_type") or "").strip()
    if driver:
        return driver
    return netmiko_type_for_dialect(require_platform(device))


def describe(device: dict) -> dict:
    """Both answers plus where each came from, for the UI and diagnostics."""
    explicit = bool((device.get("platform") or "").strip())
    netbox = bool((device.get("_platform") or "").strip())
    try:
        driver = netmiko_type_for_device(device)
    except ValueError:
        driver = ""
    return {
        "platform": platform_for_device(device),
        "netmiko_device_type": driver,
        "platform_source": ("explicit" if explicit
                            else "netbox" if netbox
                            else "derived from device_type"),
    }
