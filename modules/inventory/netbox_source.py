"""inventory/netbox_source.py

Adapter turning NetBox devices into the exact device dict the rest of NMAS
already consumes.

The contract is shape fidelity. ``load_saved_devices`` returns CSV rows whose
``password`` and ``secret`` are **still Fernet-encrypted** — callers decrypt at
use. This adapter therefore re-encrypts resolved credentials, so bulk ops, the
terminal, backups, drift, topology, the connection pool, and the AI tools cannot
tell a NetBox-sourced device from a local one.

A device that cannot be represented is **skipped with a per-device reason**,
never dropped silently and never fatal to the list: nine good devices out of ten
still load and work.
"""

import logging

from modules.settings_schema import get_setting

log = logging.getLogger(__name__)

#: Device dict keys the rest of the codebase relies on.
DEVICE_FIELDS = ("hostname", "device_type", "ip", "username", "password", "secret", "role")

VALID_ROLES = ("router", "switch", "firewall", "")


def _encrypt_for_shape(value: str) -> str:
    """Encrypt a credential so the dict matches a CSV-loaded one."""
    from modules.device import fernet
    return fernet.encrypt((value or "").encode()).decode()


def map_platform(platform_slug: str) -> tuple:
    """Resolve a NetBox platform slug to ``(netmiko_type, warning)``.

    Amendment 6: an unmapped platform is a skip, unless the operator has set
    ``platform_default_netmiko_type`` — then it is used with a per-device
    warning instead, trading a skip for an explicit guess.
    """
    platform_map = get_setting("platform_map", {}) or {}
    entry = platform_map.get(platform_slug)
    if entry and entry.get("netmiko_device_type"):
        return entry["netmiko_device_type"], ""

    fallback = (get_setting("platform_default_netmiko_type", "") or "").strip()
    if fallback:
        return fallback, (
            f"platform '{platform_slug or '(none)'}' is not in the platform map — "
            f"using the default type '{fallback}'"
        )
    return "", (
        f"platform '{platform_slug or '(none)'}' is not in the platform map — "
        "add it, or a default driver, on Settings › Installation › Platforms and roles"
    )


def kind_of(role_slug: str, kinds) -> tuple:
    """``(kind, warning)`` for a NetBox role slug, from NetBox's own classification (C665): the
    Device Role's `mercury_kind` custom field (`role_kind.read`, one read per load). A role
    with none is "not classified in NetBox", said with where to set it; never guessed from a
    hostname or a map."""
    from modules.inventory.role_kind import FIELD

    kind = ((kinds or {}).get("kinds") or {}).get(role_slug, "")
    if kind or not role_slug:
        return kind, ""
    if not (kinds or {}).get("field"):
        return "", (f"not classified in NetBox: NetBox has no `{FIELD}` field on device roles "
                    "yet (scripts/nmas-netbox-role-kind adds it), so its role "
                    f"'{role_slug}' says nothing of what it is")
    return "", (f"not classified in NetBox: its role '{role_slug}' has no Mercury kind; set "
                f"`{FIELD}` (router, switch or firewall) on the role in NetBox")


def _address_only(address: str) -> str:
    """'203.0.113.1/24' -> '203.0.113.1'."""
    return (address or "").split("/")[0].strip()


def fetch_netbox_devices(filters: dict) -> dict:
    """Query NetBox for the devices matching *filters*. Raw records."""
    from modules.netbox_client import _nb_get, _nb_ready

    ok, err, session, base = _nb_ready()
    if not ok:
        return {"ok": False, "error": err, "devices": []}

    params = {"limit": 500}
    for key, nb_key in (("site", "site"), ("role", "role"),
                        ("tag", "tag"), ("status", "status")):
        value = (filters or {}).get(key, "")
        if value:
            params[nb_key] = value
    from modules.inventory.role_kind import KindUnreadable, read as read_kinds
    try:
        devices = _nb_get(session, base, "dcim/devices/", **params)
        # What each role IS (C665): NetBox's own classification, one read with the devices.
        kinds = read_kinds(session, base)
        return {"ok": True, "devices": devices, "kinds": kinds}
    except KindUnreadable as exc:
        log.warning("netbox_source: role classification query failed: %s", exc)
        return {"ok": False, "error": str(exc), "devices": []}
    except Exception as exc:                  # noqa: BLE001
        log.warning("netbox_source: device query failed: %s", exc)
        return {"ok": False, "error": str(exc), "devices": []}


def adapt_devices(raw_devices: list, credential_list: str = "", kinds: dict = None) -> tuple:
    """Map raw NetBox records to device dicts. *kinds* is NetBox's role classification
    (`role_kind.read`, which `fetch_netbox_devices` returns as ``kinds``); without it every
    role is not classified.

    Returns ``(devices, skipped, warnings)``:

    * ``devices``  — dicts matching :data:`DEVICE_FIELDS`, credentials encrypted
    * ``skipped``  — per-device dicts with ``name``, ``reason``, ``field``, ``netbox_id``
    * ``warnings`` — per-device dicts for devices that loaded with a caveat
    """
    from modules.credentials import resolve as resolve_credentials

    devices, skipped, warnings = [], [], []

    for raw in raw_devices or []:
        name = raw.get("name") or raw.get("display") or f"device-{raw.get('id')}"
        nb_id = raw.get("id")

        # ── management IP ────────────────────────────────────────────────────
        mgmt_ip = _address_only((raw.get("primary_ip4") or {}).get("address", ""))
        if not mgmt_ip:
            skipped.append({"name": name, "netbox_id": nb_id, "field": "primary_ip4",
                            "reason": "no primary IPv4 address set in NetBox"})
            continue

        # ── platform → netmiko device type ───────────────────────────────────
        platform_slug = (raw.get("platform") or {}).get("slug", "")
        device_type, platform_warning = map_platform(platform_slug)
        if not device_type:
            skipped.append({"name": name, "netbox_id": nb_id, "field": "platform",
                            "reason": platform_warning})
            continue
        if platform_warning:
            warnings.append({"name": name, "netbox_id": nb_id, "field": "platform",
                             "reason": platform_warning})

        # ── role ─────────────────────────────────────────────────────────────
        role_slug = (raw.get("role") or raw.get("device_role") or {}).get("slug", "")
        role, role_warning = kind_of(role_slug, kinds)
        if role_warning:
            warnings.append({"name": name, "netbox_id": nb_id, "field": "role",
                             "reason": role_warning})

        # ── credentials ──────────────────────────────────────────────────────
        site_slug = (raw.get("site") or {}).get("slug", "")
        creds = resolve_credentials(mgmt_ip, role=role, site=site_slug,
                                    credential_list=credential_list)
        if not creds["ok"]:
            skipped.append({"name": name, "netbox_id": nb_id, "field": "credentials",
                            "reason": creds["error"]})
            continue

        devices.append({
            "hostname":    name,
            "device_type": device_type,
            "ip":          mgmt_ip,
            "username":    creds["username"],
            # Encrypted, matching what load_saved_devices returns for a CSV list.
            "password":    _encrypt_for_shape(creds["password"]),
            "secret":      _encrypt_for_shape(creds["secret"]),
            "role":        role,
            # Presentation-only metadata. Stripped before the dict reaches
            # netmiko — see modules/inventory/__init__.py::strip_metadata.
            "_source":      "netbox",
            "_netbox_id":   nb_id,
            "_cred_source": creds["source"],
            "_platform":    platform_slug,
            # The NetBox role slug, so a role map change can say which devices it moves
            # (board F4, Platforms and roles); like _platform, never sent to a device.
            "_role_slug":   role_slug,
            "_site":        site_slug,
            # The device type as NetBox names it (its model), which Mercury's platform table
            # declares capabilities by (`vlan_capability`, C1692); never sent to a device.
            "_model":       str(((raw.get("device_type") or {}).get("model")) or "").strip(),
        })

    return devices, skipped, warnings
