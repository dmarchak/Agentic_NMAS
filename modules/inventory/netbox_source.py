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
        "add it in Settings → Integrations, or set a default netmiko device type"
    )


def map_role(role_slug: str) -> str:
    """Resolve a NetBox role slug to an NMAS role.

    Amendment 3: NMAS roles are router/switch/firewall and drive topology icons.
    An unmapped role returns "" so ``topology._infer_role(hostname)`` applies —
    the same treatment a local list with a blank role field gets.
    """
    role_map = get_setting("role_map", {}) or {}
    mapped = (role_map.get(role_slug) or "").strip().lower()
    return mapped if mapped in VALID_ROLES else ""


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
    try:
        return {"ok": True, "devices": _nb_get(session, base, "dcim/devices/", **params)}
    except Exception as exc:                  # noqa: BLE001
        log.warning("netbox_source: device query failed: %s", exc)
        return {"ok": False, "error": str(exc), "devices": []}


def adapt_devices(raw_devices: list, credential_list: str = "") -> tuple:
    """Map raw NetBox records to device dicts.

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
        role = map_role(role_slug)
        if role_slug and not role:
            warnings.append({
                "name": name, "netbox_id": nb_id, "field": "role",
                "reason": (f"role '{role_slug}' is not in the role map — the topology "
                           "icon will be guessed from the hostname"),
            })

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
            "_site":        site_slug,
        })

    return devices, skipped, warnings
