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

DEFAULT_PLATFORM = "cisco_ios"

#: Netmiko driver → config dialect, used only when no platform is recorded.
#: A best-effort guess that keeps existing lists working; it is not a
#: replacement for recording the platform.
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


def platform_for_device(device: dict) -> str:
    """Config dialect for *device*, in order of decreasing authority.

    1. an explicit ``platform`` column — the operator said so
    2. ``_platform``, the NetBox platform slug carried by the inventory adapter
    3. derived from ``device_type``, the Netmiko driver — a guess, logged as one
    4. :data:`DEFAULT_PLATFORM`
    """
    explicit = (device.get("platform") or "").strip().lower()
    if explicit:
        return _FROM_NETBOX_SLUG.get(explicit, explicit)

    netbox_slug = (device.get("_platform") or "").strip().lower()
    if netbox_slug:
        mapped = _FROM_NETBOX_SLUG.get(netbox_slug)
        if mapped:
            return mapped
        from modules.settings_schema import get_setting
        entry = (get_setting("platform_map", {}) or {}).get(netbox_slug, {})
        template_dir = (entry.get("template_dir") or "").strip()
        if template_dir:
            return template_dir.replace("-", "_")

    device_type = (device.get("device_type") or "").strip().lower()
    if device_type:
        derived = _DERIVED_FROM_DEVICE_TYPE.get(device_type)
        if derived:
            return derived
        log.debug("platform: no mapping for device_type %r on %s — defaulting to %s",
                  device_type, device.get("hostname", "?"), DEFAULT_PLATFORM)

    return DEFAULT_PLATFORM


def netmiko_type_for_device(device: dict) -> str:
    """The Netmiko driver — how to open a session. Unchanged by this module."""
    return (device.get("device_type") or DEFAULT_PLATFORM).strip() or DEFAULT_PLATFORM


def describe(device: dict) -> dict:
    """Both answers plus where each came from, for the UI and diagnostics."""
    explicit = bool((device.get("platform") or "").strip())
    netbox = bool((device.get("_platform") or "").strip())
    return {
        "platform": platform_for_device(device),
        "netmiko_device_type": netmiko_type_for_device(device),
        "platform_source": ("explicit" if explicit
                            else "netbox" if netbox
                            else "derived from device_type"),
    }
