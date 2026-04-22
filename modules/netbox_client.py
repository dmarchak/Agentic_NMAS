"""netbox_client.py

NetBox IPAM/DCIM sync for the Network Device Manager.

Acts as the bridge that keeps NetBox in sync with the application's device lists:

  - Each device list becomes a NetBox *region* (grouping container) and a same-named
    *site* beneath it (since devices in NetBox must be attached to a site).
  - Every device in a list is scanned via SSH (show version / show inventory) to
    extract model, serial number, platform, and software version, then POSTed to
    NetBox as a device record under its list's region/site.
  - Manufacturers, device-types, and device-roles are created on demand.

NetBox URL and API token are stored in user_settings.json (`netbox_url`,
`netbox_token`, `netbox_verify_tls`).
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import threading
import time
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from modules.config import (
    DATA_DIR,
    get_user_setting,
    set_user_setting,
    list_slug,
)

log = logging.getLogger(__name__)

# Persistent sync status file (last-sync timestamp and per-list summary).
_SYNC_STATUS_FILE = os.path.join(DATA_DIR, "netbox_sync_status.json")
_status_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def get_netbox_config() -> dict:
    """Return the stored NetBox configuration."""
    return {
        "url":        (get_user_setting("netbox_url", "") or "").rstrip("/"),
        "token":      get_user_setting("netbox_token", "") or "",
        "verify_tls": bool(get_user_setting("netbox_verify_tls", True)),
        # Auth header NetBox accepts: "Bearer" (docs format) or "Token" (legacy).
        # Discovered during test_connection() and cached here.
        "auth_scheme": (get_user_setting("netbox_auth_scheme", "Bearer") or "Bearer"),
    }


def save_netbox_config(url: str, token: str, verify_tls: bool = True,
                       auth_scheme: Optional[str] = None) -> None:
    """Persist NetBox URL, token, TLS verification flag, and (optional) auth scheme."""
    set_user_setting("netbox_url", (url or "").rstrip("/"))
    set_user_setting("netbox_token", token or "")
    set_user_setting("netbox_verify_tls", bool(verify_tls))
    if auth_scheme:
        set_user_setting("netbox_auth_scheme", auth_scheme)


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

def _build_session(token: str, verify_tls: bool,
                   auth_scheme: str = "Bearer") -> requests.Session:
    """Return a requests Session preconfigured for the NetBox REST API.

    `auth_scheme` is the Authorization prefix ("Bearer" or "Token"). NetBox 4.x
    accepts Bearer (as shown in its own docs) and older versions accept Token.
    """
    s = requests.Session()
    scheme = auth_scheme if auth_scheme in ("Bearer", "Token") else "Bearer"
    s.headers.update({
        "Authorization": f"{scheme} {token}",
        "Accept":        "application/json",
        "Content-Type":  "application/json",
    })
    s.verify = verify_tls

    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET", "POST", "PATCH", "PUT", "DELETE"),
    )
    s.mount("http://",  HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _session_from_config(cfg: dict) -> requests.Session:
    """Build a session from the stored NetBox config."""
    return _build_session(cfg["token"], cfg["verify_tls"], cfg.get("auth_scheme", "Bearer"))


def test_connection(url: str, token: str, verify_tls: bool = True,
                    persist_scheme: bool = True) -> tuple[bool, str]:
    """Ping the NetBox status endpoint. Returns (ok, message).

    Tries the Bearer auth header first (NetBox's documented format) and falls
    back to the legacy Token header if Bearer is rejected. When `persist_scheme`
    is true and the probe succeeds, the working scheme is cached in user
    settings so every subsequent sync uses it directly.
    """
    if not url or not token:
        return False, "NetBox URL and API token are required"

    base = url.rstrip("/")
    last_status = None
    last_err    = None

    for scheme in ("Bearer", "Token"):
        try:
            s = _build_session(token, verify_tls, auth_scheme=scheme)
            r = s.get(f"{base}/api/status/", timeout=8)
            if r.status_code == 200:
                data = r.json() if r.content else {}
                version = data.get("netbox-version") or data.get("django-version") or "unknown"
                if persist_scheme:
                    set_user_setting("netbox_auth_scheme", scheme)
                return True, f"Connected to NetBox (version {version}) using {scheme} auth"
            last_status = r.status_code
            if r.status_code not in (401, 403):
                # A non-auth failure — don't bother trying the other scheme.
                return False, f"NetBox returned HTTP {r.status_code}"
        except requests.exceptions.SSLError as exc:
            return False, f"TLS verification failed: {exc}"
        except requests.exceptions.ConnectionError as exc:
            return False, f"Could not connect to {base}: {exc}"
        except Exception as exc:
            last_err = exc

    if last_err:
        return False, f"Connection test failed: {last_err}"
    if last_status in (401, 403):
        return False, "Authentication failed — check the API token (tried both Bearer and Token)"
    return False, "NetBox connection failed"


# ---------------------------------------------------------------------------
# Low-level get-or-create helpers
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    """Produce a NetBox-compatible slug (lowercase, hyphens, alnum + underscore)."""
    s = re.sub(r"[^\w\-]+", "-", (name or "").strip().lower()).strip("-_")
    return s or "unnamed"


def _nb_get(session: requests.Session, base: str, path: str, **params) -> list[dict]:
    """GET a NetBox list endpoint, following pagination. Returns all results."""
    results: list[dict] = []
    url: Optional[str] = f"{base}/api/{path.lstrip('/')}"
    first = True
    while url:
        r = session.get(url, params=params if first else None, timeout=15)
        r.raise_for_status()
        data = r.json()
        results.extend(data.get("results", []))
        url = data.get("next")
        first = False
    return results


def _nb_first(session: requests.Session, base: str, path: str, **params) -> Optional[dict]:
    """Return the first matching result from a NetBox list query, or None."""
    r = session.get(f"{base}/api/{path.lstrip('/')}", params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    hits = data.get("results", [])
    return hits[0] if hits else None


def _nb_post(session: requests.Session, base: str, path: str, payload: dict) -> dict:
    """POST a payload to a NetBox endpoint and return the JSON response."""
    r = session.post(f"{base}/api/{path.lstrip('/')}", json=payload, timeout=20)
    if not r.ok:
        raise RuntimeError(
            f"POST {path} failed ({r.status_code}): {r.text[:300]}"
        )
    return r.json()


def _nb_patch(session: requests.Session, base: str, path: str, payload: dict) -> dict:
    """PATCH a payload to a NetBox endpoint (id embedded in path)."""
    r = session.patch(f"{base}/api/{path.lstrip('/')}", json=payload, timeout=20)
    if not r.ok:
        raise RuntimeError(
            f"PATCH {path} failed ({r.status_code}): {r.text[:300]}"
        )
    return r.json()


def _ensure_region(session, base: str, name: str) -> dict:
    """Get-or-create a NetBox region named after the device list."""
    slug = _slug(name)
    existing = _nb_first(session, base, "dcim/regions/", slug=slug)
    if existing:
        return existing
    return _nb_post(session, base, "dcim/regions/", {
        "name": name,
        "slug": slug,
        "description": "Created by Network Device Manager — mirrors a device list.",
    })


def _ensure_site(session, base: str, name: str, region_id: int) -> dict:
    """Get-or-create a NetBox site under the given region (same name as region)."""
    slug = _slug(name)
    existing = _nb_first(session, base, "dcim/sites/", slug=slug)
    if existing:
        # Re-parent to the right region if someone moved it.
        current_region = (existing.get("region") or {}).get("id")
        if current_region != region_id:
            _nb_patch(session, base, f"dcim/sites/{existing['id']}/", {"region": region_id})
            existing["region"] = {"id": region_id}
        return existing
    return _nb_post(session, base, "dcim/sites/", {
        "name":   name,
        "slug":   slug,
        "status": "active",
        "region": region_id,
    })


def _ensure_manufacturer(session, base: str, name: str) -> dict:
    """Get-or-create a manufacturer (vendor) record."""
    name = name or "Cisco"
    slug = _slug(name)
    existing = _nb_first(session, base, "dcim/manufacturers/", slug=slug)
    if existing:
        return existing
    return _nb_post(session, base, "dcim/manufacturers/", {"name": name, "slug": slug})


def _ensure_device_type(session, base: str, model: str, manufacturer_id: int) -> dict:
    """Get-or-create a device-type (model)."""
    model = model or "Generic"
    slug = _slug(model)
    existing = _nb_first(session, base, "dcim/device-types/", slug=slug)
    if existing:
        return existing
    return _nb_post(session, base, "dcim/device-types/", {
        "manufacturer": manufacturer_id,
        "model":        model,
        "slug":         slug,
        "u_height":     1,
    })


def _ensure_device_role(session, base: str, name: str = "Network Device") -> dict:
    """Get-or-create a device-role. Uses the new /dcim/roles/ path on NetBox 4.x,
    falling back to the legacy /dcim/device-roles/ path on 3.x."""
    slug = _slug(name)
    payload = {
        "name":          name,
        "slug":          slug,
        "color":         "2196f3",
        "vm_role":       False,
        "description":   "Default role for devices auto-created by Network Device Manager.",
    }
    # Prefer legacy path — still accepted by NetBox 4.x (aliased).
    try:
        existing = _nb_first(session, base, "dcim/device-roles/", slug=slug)
        if existing:
            return existing
        return _nb_post(session, base, "dcim/device-roles/", payload)
    except requests.exceptions.HTTPError:
        existing = _nb_first(session, base, "dcim/roles/", slug=slug)
        if existing:
            return existing
        return _nb_post(session, base, "dcim/roles/", payload)


# ---------------------------------------------------------------------------
# IPAM helpers — prefixes, interfaces, IP addresses
# ---------------------------------------------------------------------------

# Map of Netmiko driver → NetBox interface type. Keep the list short and
# default to a sensible "other" for unknowns.
_IFTYPE_MAP = {
    "loopback":     "virtual",
    "tunnel":       "virtual",
    "vlan":         "virtual",
    "port-channel": "lag",
    "portchannel":  "lag",
    "gigabitethernet":  "1000base-t",
    "tengigabitethernet": "10gbase-t",
    "fortygigabitethernet": "40gbase-x-qsfpp",
    "hundredgigabitethernet": "100gbase-x-qsfp28",
    "fastethernet": "100base-tx",
    "ethernet":     "1000base-t",
    "serial":       "other",
    "mgmt":         "1000base-t",
    "management":   "1000base-t",
}


def _netbox_iface_type(iface_name: str) -> str:
    """Return the best-matching NetBox interface type for a Cisco iface name."""
    lower = iface_name.lower().lstrip()
    for prefix, nb_type in _IFTYPE_MAP.items():
        if lower.startswith(prefix):
            return nb_type
    return "other"


def _ensure_platform(session, base: str, name: str, manufacturer_id: int) -> dict:
    """Get-or-create a DCIM Platform (OS) record."""
    slug = _slug(name)
    existing = _nb_first(session, base, "dcim/platforms/", slug=slug)
    if existing:
        return existing
    return _nb_post(session, base, "dcim/platforms/", {
        "name":         name,
        "slug":         slug,
        "manufacturer": manufacturer_id,
    })


def _ensure_vrf(session, base: str, name: str, rd: str = "") -> dict:
    """Get-or-create an IPAM VRF."""
    existing = _nb_first(session, base, "ipam/vrfs/", name=name)
    if existing:
        return existing
    payload: dict = {"name": name}
    if rd:
        payload["rd"] = rd
    return _nb_post(session, base, "ipam/vrfs/", payload)


def _ensure_vlan(session, base: str, vid: int, name: str,
                 site_id: Optional[int] = None) -> dict:
    """Get-or-create an IPAM VLAN."""
    params = {"vid": vid}
    if site_id:
        params["site_id"] = site_id
    existing = _nb_first(session, base, "ipam/vlans/", **params)
    if existing:
        return existing
    payload: dict = {"vid": vid, "name": name or f"VLAN{vid}", "status": "active"}
    if site_id:
        payload["site"] = site_id
    return _nb_post(session, base, "ipam/vlans/", payload)


def _ensure_tag(session, base: str, name: str,
                slug: str = "", color: str = "9e9e9e") -> dict:
    """Get-or-create an Extras tag (for device protocol labels, route types, etc.)."""
    slug = slug or _slug(name)
    existing = _nb_first(session, base, "extras/tags/", slug=slug)
    if existing:
        return existing
    return _nb_post(session, base, "extras/tags/", {
        "name":  name,
        "slug":  slug,
        "color": color,
    })


_TUNNEL_MODE_TO_ENCAP: dict = {
    "gre multipoint": "gre",
    "gre ip":         "gre",
    "gre":            "gre",
    "ipsec ipv4":     "ipsec-transport",
    "ipsec":          "ipsec-transport",
    "ip ip":          "ip-ip",
    "ipv6ip":         "other",
    "vxlan":          "vxlan",
    "l2tp":           "l2tp",
    "mpls":           "other",
}


def _tunnel_encap(tunnel_mode: str) -> str:
    """Map a Cisco tunnel mode string to a NetBox VPN encapsulation value."""
    m = (tunnel_mode or "gre ip").lower().strip()
    for prefix, encap in _TUNNEL_MODE_TO_ENCAP.items():
        if m.startswith(prefix):
            return encap
    return "gre"


def _ensure_vpn_tunnel(session, base: str, name: str,
                       encapsulation: str = "gre",
                       tunnel_id: Optional[int] = None,
                       description: str = "") -> Optional[dict]:
    """Get-or-create a NetBox VPN tunnel (NetBox 3.7+).

    Returns None gracefully if the vpn/tunnels/ endpoint is not available
    (older NetBox versions).
    """
    try:
        existing = _nb_first(session, base, "vpn/tunnels/", name=name)
        if existing:
            return existing
        payload: dict = {
            "name":          name,
            "status":        "active",
            "encapsulation": encapsulation,
        }
        if tunnel_id is not None:
            payload["tunnel_id"] = tunnel_id
        if description:
            payload["description"] = description[:200]
        return _nb_post(session, base, "vpn/tunnels/", payload)
    except Exception as exc:
        log.debug("netbox: vpn/tunnels not available or failed: %s", exc)
        return None


def _ensure_tunnel_termination(session, base: str,
                                tunnel_nb_id: int,
                                role: str,
                                interface_id: int) -> Optional[dict]:
    """Get-or-create a VPN tunnel termination linking a tunnel to a DCIM interface."""
    try:
        existing = _nb_first(session, base, "vpn/tunnel-terminations/",
                             tunnel_id=tunnel_nb_id,
                             termination_id=interface_id)
        if existing:
            return existing
        return _nb_post(session, base, "vpn/tunnel-terminations/", {
            "tunnel":           tunnel_nb_id,
            "role":             role,
            "termination_type": "dcim.interface",
            "termination_id":   interface_id,
        })
    except Exception as exc:
        log.debug("netbox: tunnel termination failed: %s", exc)
        return None


def _ensure_cable(session, base: str,
                  a_type: str, a_id: int,
                  b_type: str, b_id: int) -> Optional[dict]:
    """Get-or-create a DCIM cable between two termination objects."""
    # Check if a cable already exists for this interface
    existing = _nb_first(session, base, "dcim/cables/",
                         **{f"termination_{a_type}_id": a_id})
    if existing:
        return existing
    try:
        return _nb_post(session, base, "dcim/cables/", {
            "a_terminations": [{"object_type": f"dcim.{a_type}", "object_id": a_id}],
            "b_terminations": [{"object_type": f"dcim.{b_type}", "object_id": b_id}],
            "status": "connected",
        })
    except RuntimeError as exc:
        log.debug("netbox: cable create failed: %s", exc)
        return None


def _ensure_interface(session, base: str, device_id: int,
                      name: str, description: str = "",
                      mac: Optional[str] = None,
                      mtu: Optional[int] = None,
                      enabled: bool = True,
                      speed_mbps: Optional[int] = None,
                      vrf_id: Optional[int] = None,
                      lag_id: Optional[int] = None,
                      mode: Optional[str] = None,
                      untagged_vlan_id: Optional[int] = None,
                      tagged_vlan_ids: Optional[list] = None) -> dict:
    """Get-or-create a DCIM interface, updating physical attributes if changed."""
    existing = _nb_first(session, base, "dcim/interfaces/",
                         device_id=device_id, name=name)
    iface_type = _netbox_iface_type(name)
    payload: dict = {
        "device":      device_id,
        "name":        name,
        "type":        iface_type,
        "description": (description or "")[:200],
        "enabled":     enabled,
    }
    if mac:
        payload["mac_address"] = mac.upper()
    if mtu:
        payload["mtu"] = mtu
    if speed_mbps:
        payload["speed"] = speed_mbps * 1000
    if vrf_id:
        payload["vrf"] = vrf_id
    if lag_id:
        payload["lag"] = lag_id
    if mode:
        payload["mode"] = mode
    if untagged_vlan_id:
        payload["untagged_vlan"] = untagged_vlan_id
    if tagged_vlan_ids:
        payload["tagged_vlans"] = tagged_vlan_ids

    if existing:
        update: dict = {}
        if (existing.get("description") or "") != payload["description"]:
            update["description"] = payload["description"]
        if (existing.get("type") or {}).get("value") != iface_type:
            update["type"] = iface_type
        if mac and (existing.get("mac_address") or "").upper() != mac.upper():
            update["mac_address"] = mac.upper()
        if mtu and existing.get("mtu") != mtu:
            update["mtu"] = mtu
        if existing.get("enabled") != enabled:
            update["enabled"] = enabled
        if vrf_id and (existing.get("vrf") or {}).get("id") != vrf_id:
            update["vrf"] = vrf_id
        if lag_id and (existing.get("lag") or {}).get("id") != lag_id:
            update["lag"] = lag_id
        if mode and (existing.get("mode") or {}).get("value") != mode:
            update["mode"] = mode
        if untagged_vlan_id and (existing.get("untagged_vlan") or {}).get("id") != untagged_vlan_id:
            update["untagged_vlan"] = untagged_vlan_id
        if tagged_vlan_ids is not None:
            existing_tagged = [v["id"] for v in (existing.get("tagged_vlans") or [])]
            if set(existing_tagged) != set(tagged_vlan_ids):
                update["tagged_vlans"] = tagged_vlan_ids
        if update:
            try:
                return _nb_patch(session, base,
                                 f"dcim/interfaces/{existing['id']}/", update)
            except RuntimeError:
                return existing
        return existing
    return _nb_post(session, base, "dcim/interfaces/", payload)


def _ensure_prefix(session, base: str, prefix: str,
                   description: str = "",
                   site_id: Optional[int] = None,
                   vrf_id: Optional[int] = None) -> dict:
    """Get-or-create an IPAM prefix (network/subnet)."""
    params: dict = {"prefix": prefix}
    if vrf_id:
        params["vrf_id"] = vrf_id
    existing = _nb_first(session, base, "ipam/prefixes/", **params)
    if existing:
        return existing
    payload: dict = {
        "prefix":      prefix,
        "status":      "active",
        "description": (description or "")[:200],
    }
    if site_id is not None:
        payload["site"] = site_id
    if vrf_id is not None:
        payload["vrf"] = vrf_id
    return _nb_post(session, base, "ipam/prefixes/", payload)


def _ensure_ip_address(session, base: str, address_cidr: str,
                       interface_id: int,
                       description: str = "",
                       vrf_id: Optional[int] = None) -> dict:
    """Get-or-create an IPAM IP address assigned to a DCIM interface."""
    params: dict = {"address": address_cidr}
    if vrf_id:
        params["vrf_id"] = vrf_id
    existing = _nb_first(session, base, "ipam/ip-addresses/", **params)
    payload: dict = {
        "address":              address_cidr,
        "status":               "active",
        "description":          (description or "")[:200],
        "assigned_object_type": "dcim.interface",
        "assigned_object_id":   interface_id,
    }
    if vrf_id is not None:
        payload["vrf"] = vrf_id
    if existing:
        needs_update = (
            existing.get("assigned_object_id") != interface_id
            or (existing.get("assigned_object_type") or "") != "dcim.interface"
            or existing.get("description") != payload["description"]
        )
        if needs_update:
            try:
                return _nb_patch(session, base,
                                 f"ipam/ip-addresses/{existing['id']}/",
                                 payload)
            except RuntimeError:
                return existing
        return existing
    return _nb_post(session, base, "ipam/ip-addresses/", payload)


# ---------------------------------------------------------------------------
# Device-fact collection via SSH
# ---------------------------------------------------------------------------

# show ip interface parsing — walks per-interface stanzas looking for
# "<Interface> is up/down" header and a "Internet address is X.X.X.X/NN" line.
_RE_IFACE_HEADER = re.compile(
    r"^(\S[\w\-/.:]*)\s+is\s+(?:administratively\s+)?(?:up|down)",
    re.MULTILINE,
)
_RE_INET_CIDR    = re.compile(
    r"Internet address is\s+(\d+\.\d+\.\d+\.\d+)/(\d+)",
    re.IGNORECASE,
)
_RE_DESCR        = re.compile(r"^\s*Description:\s*(.+?)\s*$", re.MULTILINE)


def _parse_ip_interfaces(show_ip_interface: str) -> list[dict]:
    """Parse `show ip interface` output into [{name, cidr, description}].

    Returns only interfaces that actually have an IPv4 address assigned.
    """
    if not show_ip_interface:
        return []

    # Split into per-interface blocks by locating header lines.
    results: list[dict] = []
    headers = list(_RE_IFACE_HEADER.finditer(show_ip_interface))
    for idx, hdr in enumerate(headers):
        start = hdr.start()
        end   = headers[idx + 1].start() if idx + 1 < len(headers) else len(show_ip_interface)
        block = show_ip_interface[start:end]
        name  = hdr.group(1)

        m = _RE_INET_CIDR.search(block)
        if not m:
            continue
        ip_str = m.group(1)
        mask_bits = int(m.group(2))
        if not (0 < mask_bits <= 32):
            continue
        try:
            addr = ipaddress.ip_interface(f"{ip_str}/{mask_bits}")
        except ValueError:
            continue

        desc_m = _RE_DESCR.search(block)
        results.append({
            "name":        name,
            "cidr":        str(addr),                           # e.g. 10.0.0.1/24
            "prefix":      str(addr.network),                   # e.g. 10.0.0.0/24
            "description": desc_m.group(1) if desc_m else "",
        })
    return results


# ---------------------------------------------------------------------------
# show interfaces parsing — MAC, MTU, speed/bandwidth, oper/admin state
# ---------------------------------------------------------------------------
_RE_SHIF_HEADER  = re.compile(
    r"^(\S[\w\-/.:]+) is (up|down|administratively down|deleted)", re.MULTILINE
)
_RE_SHIF_LINE_PROTO = re.compile(r"line protocol is (up|down)", re.IGNORECASE)
_RE_SHIF_DESCR   = re.compile(r"^\s+Description:\s*(.+)$", re.MULTILINE)
_RE_SHIF_MAC     = re.compile(
    r"(?:Hardware is.*?,|address is)\s+([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})",
    re.IGNORECASE,
)
_RE_SHIF_BW      = re.compile(r"BW (\d+) Kbit", re.IGNORECASE)
_RE_SHIF_MTU     = re.compile(r"MTU (\d+) bytes", re.IGNORECASE)
_RE_SHIF_SPEED   = re.compile(r"\b(\d+)Mb/s\b", re.IGNORECASE)


def _parse_interfaces_detail(output: str) -> list[dict]:
    """Parse `show interfaces` → [{name, mac, mtu, bandwidth_kbps, speed_mbps,
                                     admin_up, oper_up, description}].
    All fields optional — keys always present, values may be None/empty.
    """
    if not output:
        return []
    results: list[dict] = []
    headers = list(_RE_SHIF_HEADER.finditer(output))
    for idx, hdr in enumerate(headers):
        start = hdr.start()
        end   = headers[idx + 1].start() if idx + 1 < len(headers) else len(output)
        block = output[start:end]
        name  = hdr.group(1)
        admin_state = hdr.group(2)   # "up" | "down" | "administratively down"
        admin_up    = "administratively" not in admin_state and admin_state != "deleted"
        lp_m        = _RE_SHIF_LINE_PROTO.search(block)
        oper_up     = (lp_m.group(1) == "up") if lp_m else admin_up

        mac_m   = _RE_SHIF_MAC.search(block)
        bw_m    = _RE_SHIF_BW.search(block)
        mtu_m   = _RE_SHIF_MTU.search(block)
        spd_m   = _RE_SHIF_SPEED.search(block)
        desc_m  = _RE_SHIF_DESCR.search(block)

        # Normalise Cisco dotted-hex MAC → colon notation
        raw_mac = mac_m.group(1) if mac_m else None
        if raw_mac:
            parts = raw_mac.replace(".", "")
            raw_mac = ":".join(parts[i:i+2] for i in range(0, 12, 2)).upper()

        results.append({
            "name":          name,
            "mac":           raw_mac,
            "mtu":           int(mtu_m.group(1)) if mtu_m else None,
            "bandwidth_kbps": int(bw_m.group(1)) if bw_m else None,
            "speed_mbps":    int(spd_m.group(1)) if spd_m else None,
            "admin_up":      admin_up,
            "oper_up":       oper_up,
            "description":   desc_m.group(1).strip() if desc_m else "",
        })
    return results


# ---------------------------------------------------------------------------
# show vrf parsing
# ---------------------------------------------------------------------------
_RE_VRF_ROW = re.compile(
    r"^\s*(\S+)\s+(\S+)\s+<(\S+)>\s+(\S+)", re.MULTILINE
)
_RE_VRF_SIMPLE = re.compile(r"^\s*(\S+)\s+(\S+|\<not set\>)", re.MULTILINE)


def _parse_vrfs(output: str) -> list[dict]:
    """Parse `show vrf` → [{name, rd}].  RD may be empty."""
    if not output:
        return []
    results: list[dict] = []
    seen: set = set()
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name") or line.lower().startswith("vrf"):
            continue
        parts = line.split()
        if not parts:
            continue
        name = parts[0]
        if name.lower() in ("management", "mgmt", "mgmt-vrf", "name", "vrf"):
            continue
        rd = parts[1] if len(parts) > 1 and parts[1] != "<not" else ""
        if name not in seen:
            seen.add(name)
            results.append({"name": name, "rd": rd if rd != "<not" else ""})
    return results


# ---------------------------------------------------------------------------
# show vlan brief parsing
# ---------------------------------------------------------------------------
_RE_VLAN_ROW = re.compile(
    r"^(\d+)\s+([\w\-\.]+)\s+(active|act|act/unsup|suspended|sus)\s*([\w,/\s]*)?$",
    re.MULTILINE | re.IGNORECASE,
)


def _parse_vlans(output: str) -> list[dict]:
    """Parse `show vlan brief` → [{vlan_id, name, ports}]."""
    if not output:
        return []
    results: list[dict] = []
    for m in _RE_VLAN_ROW.finditer(output):
        vid = int(m.group(1))
        if vid in (1002, 1003, 1004, 1005):  # Cisco internal VLANs
            continue
        ports_raw = (m.group(4) or "").strip()
        ports = [p.strip() for p in ports_raw.split(",") if p.strip()] if ports_raw else []
        results.append({
            "vlan_id": vid,
            "name":    m.group(2),
            "ports":   ports,
        })
    return results


def _expand_vlan_list(vlan_str: str) -> list:
    """Expand a Cisco VLAN range string like '10,20-25,30' into a flat list of ints."""
    vlans: list = []
    for part in vlan_str.replace(" ", "").split(","):
        if "-" in part:
            try:
                lo, hi = part.split("-", 1)
                vlans.extend(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        elif part.isdigit():
            vlans.append(int(part))
    return vlans


# ---------------------------------------------------------------------------
# show cdp neighbors detail parsing
# ---------------------------------------------------------------------------
_RE_CDP_ENTRY      = re.compile(r"^-{5,}", re.MULTILINE)
_RE_CDP_DEVICE_ID  = re.compile(r"^Device ID:\s*(\S+)", re.MULTILINE)
_RE_CDP_LOCAL_INTF = re.compile(r"Interface:\s*(\S+),", re.MULTILINE)
_RE_CDP_PORT_ID    = re.compile(r"Port ID \(outgoing port\):\s*(\S+)", re.MULTILINE | re.IGNORECASE)
_RE_CDP_IP         = re.compile(r"IP(?:v4)? [Aa]ddress:\s*(\d+\.\d+\.\d+\.\d+)", re.MULTILINE)
_RE_CDP_PLATFORM   = re.compile(r"Platform:\s*([^,]+)", re.MULTILINE)


def _parse_cdp_neighbors(output: str) -> list[dict]:
    """Parse `show cdp neighbors detail` → [{local_iface, remote_hostname,
       remote_iface, remote_ip, remote_platform}]."""
    if not output:
        return []
    results: list[dict] = []
    # Split on separator lines (----------------)
    chunks = _RE_CDP_ENTRY.split(output)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        dev_m  = _RE_CDP_DEVICE_ID.search(chunk)
        loc_m  = _RE_CDP_LOCAL_INTF.search(chunk)
        port_m = _RE_CDP_PORT_ID.search(chunk)
        if not (dev_m and loc_m and port_m):
            continue
        ip_m   = _RE_CDP_IP.search(chunk)
        plat_m = _RE_CDP_PLATFORM.search(chunk)
        results.append({
            "local_iface":      loc_m.group(1),
            "remote_hostname":  dev_m.group(1).split(".")[0],  # strip domain
            "remote_iface":     port_m.group(1),
            "remote_ip":        ip_m.group(1) if ip_m else "",
            "remote_platform":  (plat_m.group(1).strip() if plat_m else ""),
        })
    return results


# ---------------------------------------------------------------------------
# show ip interface brief — used for quick oper-status snapshot
# ---------------------------------------------------------------------------
_RE_IP_BRIEF = re.compile(
    r"^(\S+)\s+(\d+\.\d+\.\d+\.\d+|unassigned)\s+\S+\s+\S+\s+(up|down|administratively down)",
    re.MULTILINE | re.IGNORECASE,
)


def _parse_ip_brief(output: str) -> dict:
    """Parse `show ip interface brief` → {iface_name: oper_state}."""
    result: dict = {}
    for m in _RE_IP_BRIEF.finditer(output or ""):
        result[m.group(1)] = m.group(3).lower()
    return result


# show version parsing — Cisco IOS / IOS-XE / NX-OS friendly patterns.
_RE_HOSTNAME_CMD  = re.compile(r"^\s*([A-Za-z0-9][\w\-.]*)[#>]", re.MULTILINE)
_RE_IOS_VERSION   = re.compile(r"(?:IOS(?:-XE)?\s+Software.*?Version\s+([\w\.\(\)-]+))", re.IGNORECASE | re.DOTALL)
_RE_NXOS_VERSION  = re.compile(r"^\s*system:\s*version\s+(\S+)", re.IGNORECASE | re.MULTILINE)
_RE_IOS_MODEL     = re.compile(
    r"^\s*[Cc]isco\s+(\S+)\s+.*?(?:processor|with|\(revision)",
    re.MULTILINE,
)
_RE_PROCESSOR_SN  = re.compile(r"[Pp]rocessor (?:board )?ID\s+(\S+)")
_RE_CHASSIS_SN    = re.compile(r"Chassis Serial Number\s*:\s*(\S+)", re.IGNORECASE)
_RE_INV_PID       = re.compile(r'^\s*NAME:\s*"Chassis".*?PID:\s*(\S+)', re.MULTILINE | re.DOTALL)
_RE_INV_SN        = re.compile(r'^\s*NAME:\s*"Chassis".*?SN:\s*(\S+)', re.MULTILINE | re.DOTALL)
_RE_ANY_PID       = re.compile(r'^\s*PID:\s*(\S+)', re.MULTILINE)
_RE_ANY_SN        = re.compile(r'\bSN:\s*(\S+)')


def _parse_device_facts(show_version: str, show_inventory: str) -> dict:
    """Extract vendor/model/serial/version fields from CLI output."""
    facts = {
        "manufacturer": "Cisco",   # all supported device_types are Cisco-flavored
        "model":        "",
        "serial":       "",
        "version":      "",
        "platform":     "",
    }

    if show_version:
        m = _RE_IOS_VERSION.search(show_version)
        if m:
            facts["version"] = m.group(1).strip(",")
            facts["platform"] = "IOS-XE" if "IOS-XE" in show_version or "IOS XE" in show_version else "IOS"
        else:
            m = _RE_NXOS_VERSION.search(show_version)
            if m:
                facts["version"]  = m.group(1)
                facts["platform"] = "NX-OS"

        m = _RE_IOS_MODEL.search(show_version)
        if m:
            facts["model"] = m.group(1)

        m = _RE_PROCESSOR_SN.search(show_version) or _RE_CHASSIS_SN.search(show_version)
        if m:
            facts["serial"] = m.group(1)

    if show_inventory:
        # Prefer the Chassis entry when present.
        m = _RE_INV_PID.search(show_inventory)
        if m:
            facts["model"] = facts["model"] or m.group(1)
        m = _RE_INV_SN.search(show_inventory)
        if m:
            facts["serial"] = facts["serial"] or m.group(1)
        # Fall back to first PID/SN lines in the inventory output.
        if not facts["model"]:
            m = _RE_ANY_PID.search(show_inventory)
            if m:
                facts["model"] = m.group(1)
        if not facts["serial"]:
            m = _RE_ANY_SN.search(show_inventory)
            if m:
                facts["serial"] = m.group(1)

    # Sensible fallback so the device-type entry in NetBox still has a name.
    if not facts["model"]:
        facts["model"] = "Unknown"
    return facts


def _scan_device(dev: dict) -> dict:
    """SSH into a device and return facts + interface IPs (or an error).

    Result keys: ip, hostname, facts, interfaces  — or  ip, hostname, error.
    """
    from modules.connection import get_persistent_connection

    ip = dev.get("ip", "")
    hostname = dev.get("hostname", "") or ip

    try:
        priv_pool: dict = {}
        priv_lock = threading.Lock()
        conn = get_persistent_connection(dev, priv_pool, priv_lock)

        from modules.commands import run_device_command

        def _cmd(cmd: str, timeout: int = 30) -> str:
            try:
                return run_device_command(conn, cmd, read_timeout=timeout) or ""
            except Exception as exc:
                log.debug("netbox: '%s' failed on %s: %s", cmd, ip, exc)
                return ""

        show_version   = _cmd("show version",             30)
        show_inventory = _cmd("show inventory",            30)
        show_ip_intf   = _cmd("show ip interface",         60)
        show_interfaces= _cmd("show interfaces",           60)
        show_vlan      = _cmd("show vlan brief",           20)
        show_vrf       = _cmd("show vrf",                  20)
        show_cdp       = _cmd("show cdp neighbors detail", 45)
        show_ip_brief  = _cmd("show ip interface brief",   20)
        show_run       = _cmd("show running-config",       90)

        try:
            conn.disconnect()
        except Exception:
            pass

        facts          = _parse_device_facts(show_version, show_inventory)
        interfaces     = _parse_ip_interfaces(show_ip_intf)
        iface_detail   = _parse_interfaces_detail(show_interfaces)
        vlans          = _parse_vlans(show_vlan)
        vrfs           = _parse_vrfs(show_vrf)
        cdp_neighbors  = _parse_cdp_neighbors(show_cdp)
        ip_brief       = _parse_ip_brief(show_ip_brief)

        # Merge show-interfaces detail into IP-interface records (same name key)
        detail_map = {d["name"]: d for d in iface_detail}
        for intf in interfaces:
            det = detail_map.get(intf["name"], {})
            intf["mac"]          = det.get("mac")
            intf["mtu"]          = det.get("mtu")
            intf["speed_mbps"]   = det.get("speed_mbps")
            intf["bandwidth_kbps"] = det.get("bandwidth_kbps")
            intf["admin_up"]     = det.get("admin_up", True)
            intf["oper_up"]      = det.get("oper_up", True)
            if not intf.get("description"):
                intf["description"] = det.get("description", "")

        # Also carry non-IP interfaces (e.g. trunk/access ports) for DCIM completeness
        ip_iface_names = {i["name"] for i in interfaces}
        for det in iface_detail:
            if det["name"] not in ip_iface_names:
                interfaces.append({
                    "name":          det["name"],
                    "cidr":          None,
                    "prefix":        None,
                    "description":   det.get("description", ""),
                    "mac":           det.get("mac"),
                    "mtu":           det.get("mtu"),
                    "speed_mbps":    det.get("speed_mbps"),
                    "bandwidth_kbps": det.get("bandwidth_kbps"),
                    "admin_up":      det.get("admin_up", True),
                    "oper_up":       det.get("oper_up", True),
                })

        # Supplement from running-config: fill in IPs and descriptions that
        # 'show ip interface' missed (e.g. due to timeout / partial output).
        rc_ifaces  = _parse_interfaces_from_running_config(show_run)
        rc_ip_map  = {i["name"]: i for i in rc_ifaces}
        all_names  = {i["name"] for i in interfaces}

        for intf in interfaces:
            rc = rc_ip_map.get(intf["name"])
            if not rc:
                continue
            # Fill missing IP
            if not intf.get("cidr") and rc.get("cidr"):
                intf["cidr"]   = rc["cidr"]
                intf["prefix"] = rc["prefix"]
            # Fill missing description (running-config is authoritative)
            if not intf.get("description") and rc.get("description"):
                intf["description"] = rc["description"]

        # Add interfaces that show ip interface missed entirely but running-config has
        for rc in rc_ifaces:
            if rc["name"] in all_names:
                continue
            det = detail_map.get(rc["name"], {})
            interfaces.append({
                "name":           rc["name"],
                "cidr":           rc["cidr"],
                "prefix":         rc["prefix"],
                "description":    rc["description"] or det.get("description", ""),
                "mac":            det.get("mac"),
                "mtu":            det.get("mtu"),
                "speed_mbps":     det.get("speed_mbps"),
                "bandwidth_kbps": det.get("bandwidth_kbps"),
                "admin_up":       rc["admin_up"],
                "oper_up":        det.get("oper_up", rc["admin_up"]),
            })
            all_names.add(rc["name"])
            log.debug("netbox: %s %s — IP from running-config (%s)",
                      hostname, rc["name"], rc["cidr"])

        # Extract hostname from show version / running config if not set
        if not hostname or hostname == ip:
            m = re.search(r"^hostname\s+(\S+)", show_run, re.MULTILINE)
            if m:
                hostname = m.group(1)
            elif show_version:
                m = re.search(r"^([A-Za-z0-9][\w\-.]+)[#>]", show_version, re.MULTILINE)
                if m:
                    hostname = m.group(1)

        return {
            "ip":            ip,
            "hostname":      hostname,
            "facts":         facts,
            "interfaces":    interfaces,
            "vlans":         vlans,
            "vrfs":          vrfs,
            "cdp_neighbors": cdp_neighbors,
            "running_config": show_run,
        }

    except Exception as exc:
        log.warning("netbox: scan failed for %s (%s): %s", hostname, ip, exc)
        return {"ip": ip, "hostname": hostname, "error": str(exc)}


# ---------------------------------------------------------------------------
# Running-config interface parser (fallback when show ip interface is incomplete)
# ---------------------------------------------------------------------------

_RE_RC_IFACE_BLOCK = re.compile(
    r"^interface\s+(\S+)(.*?)(?=^interface\s|\Z)", re.MULTILINE | re.DOTALL
)
_RE_RC_IP_ADDR = re.compile(
    r"^\s+ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)",
    re.MULTILINE,
)
_RE_RC_DESCR   = re.compile(r"^\s+description\s+(.+)$", re.MULTILINE)
_RE_RC_SHUTDOWN = re.compile(r"^\s+shutdown\b", re.MULTILINE)


def _parse_interfaces_from_running_config(config: str) -> list[dict]:
    """Extract interface IPs (CIDR) and descriptions from a running-config.

    Used as a supplement when 'show ip interface' times out or returns
    partial output.  Returns only interfaces that have an 'ip address' line.
    Each entry: {name, cidr, prefix, description, admin_up}.
    """
    if not config:
        return []
    results: list[dict] = []
    for m in _RE_RC_IFACE_BLOCK.finditer(config):
        name = m.group(1)
        body = m.group(2)

        ip_m = _RE_RC_IP_ADDR.search(body)
        if not ip_m:
            continue
        try:
            net  = ipaddress.IPv4Network(
                f"{ip_m.group(1)}/{ip_m.group(2)}", strict=False
            )
            addr = ipaddress.ip_interface(f"{ip_m.group(1)}/{net.prefixlen}")
        except ValueError:
            continue

        desc_m   = _RE_RC_DESCR.search(body)
        shutdown = bool(_RE_RC_SHUTDOWN.search(body))
        results.append({
            "name":        name,
            "cidr":        str(addr),
            "prefix":      str(addr.network),
            "description": desc_m.group(1).strip() if desc_m else "",
            "admin_up":    not shutdown,
        })
    return results


# ---------------------------------------------------------------------------
# Config context builder
# ---------------------------------------------------------------------------

# Regex patterns for extracting structured sections from running config
_RE_CFG_IFACE_BLOCK = re.compile(
    r"^(interface\s+\S+.*?)(?=^interface\s|\Z)", re.MULTILINE | re.DOTALL
)
_RE_CFG_ROUTER_BLOCK = re.compile(
    r"^(router\s+\S+.*?)(?=^router\s|^interface\s|\Z)", re.MULTILINE | re.DOTALL
)
_RE_CFG_HOSTNAME = re.compile(r"^hostname\s+(\S+)", re.MULTILINE)
_RE_CFG_BANNER   = re.compile(
    r"^banner\s+\w+\s+\^C.*?\^C", re.MULTILINE | re.DOTALL
)
_RE_CFG_SECRET   = re.compile(
    # enable secret [type] <hash>  — optional hash-type digit before the actual secret
    r"^(enable\s+(?:secret|password)\s+(?:\d+\s+)?)\S+", re.MULTILINE
)
_RE_CFG_USERNAME = re.compile(
    # username <name> secret|password [type] <hash>
    r"^(username\s+\S+\s+(?:secret|password)\s+(?:\d+\s+)?)\S+", re.MULTILINE
)
_RE_CFG_PASSWORD = re.compile(
    # <whitespace> password [type] <hash>  (interface / line / ospf etc.)
    r"(\s+password\s+(?:\d+\s+)?)\S+", re.MULTILINE
)
_RE_CFG_KEY      = re.compile(
    # IOS key-string <secret>  (hyphenated keyword)
    r"(^\s+key-string\s+)\S+", re.MULTILINE
)


def _sanitise_config(raw: str) -> str:
    """Strip secrets from a running config before storing in NetBox."""
    s = _RE_CFG_BANNER.sub("banner motd ^C[REMOVED]^C", raw)
    s = _RE_CFG_SECRET.sub(r"\g<1>[REMOVED]", s)
    s = _RE_CFG_USERNAME.sub(r"\g<1>[REMOVED]", s)
    s = _RE_CFG_PASSWORD.sub(r"\g<1>[REMOVED]", s)
    s = _RE_CFG_KEY.sub(r"\g<1>[REMOVED]", s)
    return s


def _build_config_context(hostname: str, ip: str, facts: dict,
                           interfaces: list[dict],
                           vlans: list, vrfs: list,
                           running_config: str,
                           routing_context: Optional[dict] = None) -> dict:
    """Build the JSON payload for NetBox device local_context_data.

    Stores structured extracted data plus the sanitised full running config.
    """
    ctx: dict = {
        "ndm_sync":       time.strftime("%Y-%m-%d %H:%M"),
        "mgmt_ip":        ip,
        "platform":       facts.get("platform", ""),
        "os_version":     facts.get("version", ""),
        "serial":         facts.get("serial", ""),
        "model":          facts.get("model", ""),
    }

    # Structured interface summary (IP interfaces only to keep size manageable)
    ip_ifaces = [i for i in interfaces if i.get("cidr")]
    if ip_ifaces:
        ctx["ip_interfaces"] = [
            {
                "name":    i["name"],
                "address": i["cidr"],
                "vrf":     i.get("vrf_name", "") or "",
                "enabled": i.get("admin_up", True),
            }
            for i in ip_ifaces
        ]

    if vrfs:
        ctx["vrfs"] = [{"name": v["name"], "rd": v.get("rd", "")} for v in vrfs]

    if vlans:
        ctx["vlans"] = [{"id": v["vlan_id"], "name": v["name"]} for v in vlans]

    # Structured routing data (OSPF, BGP, NTP, SNMP) from golden-config parsers
    if routing_context:
        ctx.update(routing_context)

    if running_config:
        ctx["running_config"] = _sanitise_config(running_config)

    return ctx


# ---------------------------------------------------------------------------
# Config Template (NetBox 3.5+ extras/config-templates)
# ---------------------------------------------------------------------------

# Jinja2 template stored in NetBox that renders against local_context_data.
# Variables match what _build_config_context() puts in local_context_data.
_NDM_TEMPLATE_NAME = "NDM Running Config"
_NDM_TEMPLATE_CODE = """\
! ============================================================
! Device : {{ model | default('unknown') }}
! Platform: {{ platform | default('unknown') }}  Version: {{ os_version | default('unknown') }}
! Serial  : {{ serial | default('N/A') }}
! Mgmt IP : {{ mgmt_ip | default('') }}
! Synced  : {{ ndm_sync | default('') }}
! ============================================================
{% if running_config is defined and running_config %}
{{ running_config }}
{% else %}
! No running configuration was captured during the last sync.
{% endif %}
"""


def _ensure_config_template(session: requests.Session, base: str) -> Optional[int]:
    """Get-or-create the NDM config template in NetBox.

    Returns the template id, or None if the NetBox version doesn't support
    config-templates (pre-3.5) or if the endpoint fails for any reason.
    """
    try:
        existing = _nb_first(session, base, "extras/config-templates/",
                             name=_NDM_TEMPLATE_NAME)
        if existing:
            # Keep the template code current
            if existing.get("template_code") != _NDM_TEMPLATE_CODE:
                _nb_patch(session, base,
                          f"extras/config-templates/{existing['id']}/",
                          {"template_code": _NDM_TEMPLATE_CODE})
            return existing["id"]

        result = _nb_post(session, base, "extras/config-templates/", {
            "name":           _NDM_TEMPLATE_NAME,
            "description":    "Renders device running config from NDM local_context_data.",
            "template_code":  _NDM_TEMPLATE_CODE,
            "mime_type":      "text/plain",
            "file_extension": "txt",
        })
        log.info("netbox: created config template '%s' (id=%s)",
                 _NDM_TEMPLATE_NAME, result.get("id"))
        return result["id"]
    except Exception as exc:
        log.debug("netbox: config-templates endpoint unavailable (%s) — skipping", exc)
        return None


# ---------------------------------------------------------------------------
# NetBox device upsert
# ---------------------------------------------------------------------------

def _upsert_device(session, base: str, hostname: str, ip: str, facts: dict,
                   interfaces: list[dict],
                   site_id: int, role_id: int,
                   ipam_stats: dict,
                   vlans: Optional[list] = None,
                   vrfs: Optional[list] = None,
                   running_config: str = "",
                   config_template_id: Optional[int] = None,
                   static_routes: Optional[list] = None,
                   protocol_tags: Optional[list] = None,
                   routing_context: Optional[dict] = None,
                   list_vrf_id: Optional[int] = None) -> dict:
    """Create or update a device in NetBox with full DCIM + IPAM data.

    Syncs: device record, platform, interfaces (with MAC/MTU/speed/state),
    VRFs, VLANs, IPAM prefixes, IP addresses (VRF-aware), primary_ip4,
    and local_context_data (sanitised running config + structured facts).
    `ipam_stats` is mutated in place with running counts.
    Returns {"action", "id", "name", "data", "nb_iface_map"}.
    """
    manuf    = _ensure_manufacturer(session, base, facts.get("manufacturer") or "Cisco")
    dev_type = _ensure_device_type(session, base, facts.get("model") or "Unknown", manuf["id"])

    # Platform (OS)
    platform_id: Optional[int] = None
    if facts.get("platform"):
        try:
            plat = _ensure_platform(session, base, facts["platform"], manuf["id"])
            platform_id = plat["id"]
        except Exception as exc:
            log.debug("netbox: platform upsert failed: %s", exc)

    # VRFs (IPAM) — build a name→id map used when assigning IPs later
    vrf_id_map: dict = {}
    for vrf in (vrfs or []):
        try:
            nb_vrf = _ensure_vrf(session, base, vrf["name"], vrf.get("rd", ""))
            vrf_id_map[vrf["name"]] = nb_vrf["id"]
            ipam_stats["vrfs_synced"] = ipam_stats.get("vrfs_synced", 0) + 1
        except Exception as exc:
            log.debug("netbox: VRF upsert failed for %s: %s", vrf["name"], exc)

    # VLANs
    for vlan in (vlans or []):
        try:
            _ensure_vlan(session, base, vlan["vlan_id"], vlan["name"], site_id)
            ipam_stats["vlans_synced"] = ipam_stats.get("vlans_synced", 0) + 1
        except Exception as exc:
            log.debug("netbox: VLAN %s upsert failed: %s", vlan.get("vlan_id"), exc)

    # Build device payload
    existing = _nb_first(session, base, "dcim/devices/", name=hostname, site_id=site_id)

    comments = (
        f"Platform: {facts.get('platform') or 'unknown'}  |  "
        f"Version: {facts.get('version') or 'unknown'}  |  "
        f"Mgmt IP: {ip}  |  "
        f"Synced: {time.strftime('%Y-%m-%d %H:%M')}"
    )

    # Build config context (sanitised running config + structured facts + routing)
    config_ctx = _build_config_context(
        hostname, ip, facts, interfaces or [],
        vlans or [], vrfs or [], running_config or "",
        routing_context=routing_context,
    )

    payload: dict = {
        "name":               hostname,
        "device_type":        dev_type["id"],
        "site":               site_id,
        "status":             "active",
        "serial":             (facts.get("serial") or "")[:50],
        "comments":           comments,
        "role":               role_id,
        "device_role":        role_id,
        "local_context_data": config_ctx,
    }
    if platform_id:
        payload["platform"] = platform_id
    if config_template_id:
        payload["config_template"] = config_template_id

    if existing:
        update = {k: v for k, v in payload.items()
                  if k in ("serial", "comments", "device_type", "status",
                            "role", "device_role", "platform",
                            "local_context_data", "config_template")}
        try:
            device = _nb_patch(session, base, f"dcim/devices/{existing['id']}/", update)
        except RuntimeError:
            update.pop("device_role", None)
            device = _nb_patch(session, base, f"dcim/devices/{existing['id']}/", update)
        action = "updated"
    else:
        try:
            device = _nb_post(session, base, "dcim/devices/", payload)
        except RuntimeError:
            payload.pop("device_role", None)
            device = _nb_post(session, base, "dcim/devices/", payload)
        action = "created"

    device_id = device["id"]

    # ── Protocol tags ──────────────────────────────────────────────────────
    if protocol_tags:
        tag_ids = []
        for proto in protocol_tags:
            try:
                tag = _ensure_tag(session, base, proto.upper(), proto,
                                  _PROTOCOL_TAG_COLORS.get(proto, "9e9e9e"))
                tag_ids.append(tag["id"])
            except Exception as exc:
                log.debug("netbox: tag %s failed: %s", proto, exc)
        if tag_ids:
            try:
                current_tags = [t["id"] for t in (device.get("tags") or [])]
                merged = list(set(current_tags + tag_ids))
                device = _nb_patch(session, base, f"dcim/devices/{device_id}/",
                                   {"tags": merged})
            except Exception as exc:
                log.debug("netbox: device tag update failed on %s: %s", hostname, exc)

    # ── DCIM interfaces + IPAM ─────────────────────────────────────────────
    mgmt_ip_id: Optional[int] = None
    nb_iface_map: dict = {}              # iface_name → nb_id
    deferred_lags: list = []             # (member_name, lag_parent_name) for second pass

    for intf in (interfaces or []):
        try:
            # Resolve VRF: use interface-specific VRF if set, else the list-level VRF
            vrf_name = intf.get("vrf_name", "")
            vrf_id: Optional[int] = (vrf_id_map.get(vrf_name) if vrf_name
                                     else list_vrf_id)

            # Switchport mode → NetBox mode value
            sw_mode = intf.get("switchport_mode")
            nb_mode: Optional[str] = None
            if sw_mode == "access":
                nb_mode = "access"
            elif sw_mode in ("trunk", "dot1q-tunnel"):
                nb_mode = "tagged"

            # Untagged VLAN (access vlan or dot1q tag)
            untagged_vlan_id: Optional[int] = None
            vlan_vid = intf.get("dot1q_tag") or intf.get("access_vlan")
            if vlan_vid:
                try:
                    nb_vlan = _ensure_vlan(session, base, vlan_vid,
                                          f"VLAN{vlan_vid}", site_id)
                    untagged_vlan_id = nb_vlan["id"]
                    ipam_stats["vlans_synced"] = ipam_stats.get("vlans_synced", 0) + 1
                except Exception:
                    pass

            # Tagged VLANs for trunk ports (cap at 50 to keep payloads reasonable)
            tagged_vlan_ids: Optional[list] = None
            if intf.get("trunk_vlans"):
                tagged_vlan_ids = []
                for vid in intf["trunk_vlans"][:50]:
                    try:
                        nb_vlan = _ensure_vlan(session, base, vid, f"VLAN{vid}", site_id)
                        tagged_vlan_ids.append(nb_vlan["id"])
                        ipam_stats["vlans_synced"] = ipam_stats.get("vlans_synced", 0) + 1
                    except Exception:
                        pass

            nb_intf = _ensure_interface(
                session, base,
                device_id=device_id,
                name=intf["name"],
                description=intf.get("description", ""),
                mac=intf.get("mac"),
                mtu=intf.get("mtu"),
                enabled=intf.get("admin_up", True),
                speed_mbps=intf.get("speed_mbps"),
                vrf_id=vrf_id,
                mode=nb_mode,
                untagged_vlan_id=untagged_vlan_id,
                tagged_vlan_ids=tagged_vlan_ids,
            )
            nb_iface_map[intf["name"]] = nb_intf["id"]
            ipam_stats["interfaces_synced"] = ipam_stats.get("interfaces_synced", 0) + 1

            # Queue LAG membership for deferred second pass
            if intf.get("channel_group") is not None:
                lag_parent = f"Port-channel{intf['channel_group']}"
                deferred_lags.append((intf["name"], lag_parent))

            # Skip IPAM for interfaces without any IP
            if not intf.get("cidr") and not intf.get("secondary_ips") and not intf.get("ipv6_addresses"):
                continue

            # Primary IPv4
            if intf.get("cidr"):
                _ensure_prefix(
                    session, base,
                    prefix=intf["prefix"],
                    description=f"Seen on {hostname} {intf['name']}",
                    site_id=site_id,
                    vrf_id=vrf_id,
                )
                ipam_stats["prefixes_synced"] = ipam_stats.get("prefixes_synced", 0) + 1

                nb_ip = _ensure_ip_address(
                    session, base,
                    address_cidr=intf["cidr"],
                    interface_id=nb_intf["id"],
                    description=f"{hostname} {intf['name']}",
                    vrf_id=vrf_id,
                )
                ipam_stats["ips_synced"] = ipam_stats.get("ips_synced", 0) + 1

                if intf["cidr"].split("/")[0] == ip:
                    mgmt_ip_id = nb_ip["id"]

            # Secondary IPv4 addresses
            for sec_cidr in intf.get("secondary_ips", []):
                try:
                    sec_prefix = str(ipaddress.ip_interface(sec_cidr).network)
                    _ensure_prefix(session, base, prefix=sec_prefix,
                                   description=f"Seen on {hostname} {intf['name']} (secondary)",
                                   site_id=site_id, vrf_id=vrf_id)
                    _ensure_ip_address(session, base, address_cidr=sec_cidr,
                                       interface_id=nb_intf["id"],
                                       description=f"{hostname} {intf['name']} secondary",
                                       vrf_id=vrf_id)
                    ipam_stats["ips_synced"] = ipam_stats.get("ips_synced", 0) + 1
                except Exception as exc:
                    log.debug("netbox: secondary IP %s on %s/%s: %s",
                              sec_cidr, hostname, intf["name"], exc)

            # IPv6 addresses
            for v6_cidr in intf.get("ipv6_addresses", []):
                try:
                    v6_net = str(ipaddress.ip_interface(v6_cidr).network)
                    _ensure_prefix(session, base, prefix=v6_net,
                                   description=f"Seen on {hostname} {intf['name']} (IPv6)",
                                   site_id=site_id)
                    _ensure_ip_address(session, base, address_cidr=v6_cidr,
                                       interface_id=nb_intf["id"],
                                       description=f"{hostname} {intf['name']} IPv6")
                    ipam_stats["ips_synced"] = ipam_stats.get("ips_synced", 0) + 1
                except Exception as exc:
                    log.debug("netbox: IPv6 %s on %s/%s: %s",
                              v6_cidr, hostname, intf["name"], exc)

        except Exception as exc:
            log.warning("netbox: IPAM sync failed on %s %s: %s",
                        hostname, intf.get("name"), exc)
            ipam_stats.setdefault("errors", []).append(
                f"{hostname} {intf.get('name', '?')}: {exc}"
            )

    # ── LAG membership (second pass — Port-channel must exist first) ───────
    for member_name, lag_parent_name in deferred_lags:
        lag_parent_id = nb_iface_map.get(lag_parent_name)
        member_id     = nb_iface_map.get(member_name)
        if not (lag_parent_id and member_id):
            continue
        try:
            _nb_patch(session, base, f"dcim/interfaces/{member_id}/",
                      {"lag": lag_parent_id})
        except Exception as exc:
            log.debug("netbox: LAG wire %s→%s on %s: %s",
                      member_name, lag_parent_name, hostname, exc)

    # ── VPN tunnels (NetBox 3.7+ vpn/tunnels/ endpoint) ──────────────────
    for intf in (interfaces or []):
        if not intf["name"].lower().startswith("tunnel"):
            continue
        tun_src  = intf.get("tunnel_source", "")
        tun_dst  = intf.get("tunnel_destination", "")
        tun_mode = intf.get("tunnel_mode", "")
        tun_key  = intf.get("tunnel_key")
        nhrp_id  = intf.get("nhrp_network_id")
        iface_id = nb_iface_map.get(intf["name"])
        if not iface_id:
            continue

        # Build a description from the tunnel params
        desc_parts = []
        if tun_src:
            desc_parts.append(f"src:{tun_src}")
        if tun_dst:
            desc_parts.append(f"dst:{tun_dst}")
        if tun_mode:
            desc_parts.append(tun_mode)
        tun_desc = " | ".join(desc_parts)

        # Determine role: hub = multipoint with no fixed destination (DMVPN hub)
        #                 spoke = has explicit destination (DMVPN spoke or P2P GRE)
        #                 peer  = point-to-point without explicit hub/spoke context
        is_dmvpn = bool(nhrp_id)
        is_multipoint = "multipoint" in tun_mode.lower()
        if is_dmvpn and is_multipoint and not tun_dst:
            role = "hub"
        elif tun_dst:
            role = "spoke"
        else:
            role = "peer"

        encap = _tunnel_encap(tun_mode)
        tun_name = f"{hostname} {intf['name']}"
        try:
            nb_tun = _ensure_vpn_tunnel(
                session, base,
                name=tun_name,
                encapsulation=encap,
                tunnel_id=tun_key,
                description=tun_desc,
            )
            if nb_tun:
                _ensure_tunnel_termination(session, base, nb_tun["id"], role, iface_id)
                ipam_stats["tunnels_synced"] = ipam_stats.get("tunnels_synced", 0) + 1
                log.debug("netbox: tunnel %s (%s) → %s", tun_name, encap, role)
        except Exception as exc:
            log.debug("netbox: tunnel %s failed: %s", tun_name, exc)

    # ── Static routes as IPAM prefixes ────────────────────────────────────
    if static_routes:
        sr_tag_id: Optional[int] = None
        try:
            sr_tag = _ensure_tag(session, base, "static-route", "static-route", "607d8b")
            sr_tag_id = sr_tag["id"]
        except Exception as exc:
            log.debug("netbox: static-route tag failed: %s", exc)

        for route in static_routes:
            try:
                route_vrf_id = vrf_id_map.get(route.get("vrf", "")) if route.get("vrf") else None
                params: dict = {"prefix": route["prefix"]}
                if route_vrf_id:
                    params["vrf_id"] = route_vrf_id
                if _nb_first(session, base, "ipam/prefixes/", **params):
                    continue   # already exists
                pf: dict = {
                    "prefix":      route["prefix"],
                    "status":      "active",
                    "description": f"Static via {route.get('nexthop', '')} on {hostname}",
                    "site":        site_id,
                }
                if route_vrf_id:
                    pf["vrf"] = route_vrf_id
                if sr_tag_id:
                    pf["tags"] = [sr_tag_id]
                _nb_post(session, base, "ipam/prefixes/", pf)
                ipam_stats["prefixes_synced"] = ipam_stats.get("prefixes_synced", 0) + 1
            except Exception as exc:
                log.debug("netbox: static route %s on %s: %s",
                          route.get("prefix"), hostname, exc)

    # Set primary_ip4 from management IP.
    # The strict match during the interface loop only fires when one interface IP
    # equals the device's SSH IP exactly.  If it didn't fire (e.g. the device is
    # managed via a dedicated mgmt network not in the golden config, or the IP is
    # on a subinterface), fall back through progressively looser searches.
    if not mgmt_ip_id and ip:
        try:
            # 1. Search NetBox IPAM for the mgmt IP (any prefix length) in the list VRF
            params: dict = {"address": ip}
            if list_vrf_id:
                params["vrf_id"] = list_vrf_id
            hits = _nb_get(session, base, "ipam/ip-addresses/", **params)
            # Filter to IPs actually assigned to this device
            for h in hits:
                obj_type = h.get("assigned_object_type") or ""
                if obj_type == "dcim.interface":
                    iface_id = h.get("assigned_object_id")
                    if iface_id in nb_iface_map.values():
                        mgmt_ip_id = h["id"]
                        break
            # 2. Fall back to any IP on this device — prefer Loopback0, then first
            if not mgmt_ip_id and nb_iface_map:
                all_hits = _nb_get(session, base, "ipam/ip-addresses/",
                                   device_id=device_id)
                loopback_ip = None
                first_ip    = None
                for h in all_hits:
                    if first_ip is None:
                        first_ip = h["id"]
                    iface_name = (h.get("assigned_object") or {}).get("name", "")
                    if "loopback0" in iface_name.lower():
                        loopback_ip = h["id"]
                        break
                mgmt_ip_id = loopback_ip or first_ip

            # 3. Last resort: the device has no IPs in NetBox at all (golden config has
            #    no addresses, or the SSH IP is on a management network not in the config).
            #    Create the SSH management IP directly from devices.csv as a /32 host
            #    address so the device always has a reachable primary IP.
            if not mgmt_ip_id:
                first_iface_id = next(iter(nb_iface_map.values()), None)
                mgmt_cidr = f"{ip}/32"
                try:
                    nb_mgmt_ip = _ensure_ip_address(
                        session, base,
                        address_cidr=mgmt_cidr,
                        interface_id=first_iface_id,
                        description=f"{hostname} management (device list SSH IP)",
                        vrf_id=list_vrf_id,
                    )
                    mgmt_ip_id = nb_mgmt_ip["id"]
                    ipam_stats["ips_synced"] = ipam_stats.get("ips_synced", 0) + 1
                    log.info("netbox: %s — no interface IPs found; created mgmt IP %s from device list",
                             hostname, mgmt_cidr)
                except Exception as exc2:
                    log.debug("netbox: could not create fallback mgmt IP %s on %s: %s",
                              mgmt_cidr, hostname, exc2)
        except Exception as exc:
            log.debug("netbox: primary_ip fallback failed on %s: %s", hostname, exc)

    if mgmt_ip_id and (device.get("primary_ip4") or {}).get("id") != mgmt_ip_id:
        try:
            device = _nb_patch(session, base,
                               f"dcim/devices/{device_id}/",
                               {"primary_ip4": mgmt_ip_id})
        except Exception as exc:
            log.debug("netbox: could not set primary_ip4 on %s: %s", hostname, exc)

    return {
        "action":       action,
        "id":           device_id,
        "name":         hostname,
        "data":         device,
        "nb_iface_map": nb_iface_map,
    }


# ---------------------------------------------------------------------------
# Golden-config parsers (used by _scan_device_from_golden)
# ---------------------------------------------------------------------------

def _parse_all_interfaces_from_config(config: str) -> list[dict]:
    """Parse ALL interface blocks from a running/golden config.

    Returns one entry per interface regardless of whether it has an IP.
    Keys: name, cidr, prefix, secondary_ips, ipv6_addresses, description,
          mtu, mac, speed_mbps, bandwidth_kbps, admin_up, oper_up,
          vrf_name, channel_group, switchport_mode, access_vlan,
          trunk_vlans, dot1q_tag.
    """
    results: list[dict] = []
    for m in _RE_RC_IFACE_BLOCK.finditer(config):
        name = m.group(1)
        body = m.group(2)

        # Primary IPv4
        cidr = prefix = None
        ip_m = _RE_RC_IP_ADDR.search(body)
        if ip_m:
            try:
                net  = ipaddress.IPv4Network(
                    f"{ip_m.group(1)}/{ip_m.group(2)}", strict=False
                )
                addr = ipaddress.ip_interface(f"{ip_m.group(1)}/{net.prefixlen}")
                cidr   = str(addr)
                prefix = str(addr.network)
            except ValueError:
                pass

        # Secondary IPv4 addresses
        secondary_ips: list = []
        for sec in re.finditer(
            r"^\s+ip address\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+secondary",
            body, re.MULTILINE,
        ):
            try:
                snet = ipaddress.IPv4Network(f"{sec.group(1)}/{sec.group(2)}", strict=False)
                secondary_ips.append(
                    str(ipaddress.ip_interface(f"{sec.group(1)}/{snet.prefixlen}"))
                )
            except ValueError:
                pass

        # IPv6 addresses
        ipv6_addresses: list = []
        for v6 in re.finditer(
            r"^\s+ipv6 address\s+([0-9a-fA-F:]+/\d+)", body, re.MULTILINE
        ):
            try:
                ipv6_addresses.append(str(ipaddress.ip_interface(v6.group(1))))
            except ValueError:
                pass

        # VRF assignment
        vrf_m = re.search(
            r"^\s+(?:ip\s+)?vrf\s+forwarding\s+(\S+)", body, re.MULTILINE
        )
        vrf_name = vrf_m.group(1) if vrf_m else ""

        # LAG (channel-group membership)
        lag_m = re.search(r"^\s+channel-group\s+(\d+)", body, re.MULTILINE)
        channel_group = int(lag_m.group(1)) if lag_m else None

        # Switchport mode
        sw_m = re.search(r"^\s+switchport\s+mode\s+(\w+)", body, re.MULTILINE)
        switchport_mode = sw_m.group(1).lower() if sw_m else None

        # Access VLAN
        av_m = re.search(r"^\s+switchport\s+access\s+vlan\s+(\d+)", body, re.MULTILINE)
        access_vlan = int(av_m.group(1)) if av_m else None

        # Trunk VLANs
        tv_m = re.search(
            r"^\s+switchport\s+trunk\s+allowed\s+vlan\s+(.+)", body, re.MULTILINE
        )
        trunk_vlans = _expand_vlan_list(tv_m.group(1)) if tv_m else []

        # Dot1q subinterface tag
        dq_m = re.search(r"^\s+encapsulation\s+dot1[qQ]\s+(\d+)", body, re.MULTILINE)
        dot1q_tag = int(dq_m.group(1)) if dq_m else None

        desc_m   = _RE_RC_DESCR.search(body)
        mtu_m    = re.search(r"^\s+mtu\s+(\d+)", body, re.MULTILINE)
        shutdown = bool(_RE_RC_SHUTDOWN.search(body))

        # Tunnel-specific attributes (only populated for Tunnel interfaces)
        tunnel_source      = ""
        tunnel_destination = ""
        tunnel_mode        = ""
        tunnel_key: Optional[int] = None
        nhrp_network_id: Optional[int] = None
        if name.lower().startswith("tunnel"):
            ts_m = re.search(r"^\s+tunnel source\s+(\S+)", body, re.MULTILINE)
            td_m = re.search(r"^\s+tunnel destination\s+(\S+)", body, re.MULTILINE)
            tm_m = re.search(r"^\s+tunnel mode\s+(.+?)$", body, re.MULTILINE)
            tk_m = re.search(r"^\s+tunnel key\s+(\d+)", body, re.MULTILINE)
            nh_m = re.search(r"^\s+ip nhrp network-id\s+(\d+)", body, re.MULTILINE)
            tunnel_source      = ts_m.group(1) if ts_m else ""
            tunnel_destination = td_m.group(1) if td_m else ""
            tunnel_mode        = tm_m.group(1).strip() if tm_m else ""
            tunnel_key         = int(tk_m.group(1)) if tk_m else None
            nhrp_network_id    = int(nh_m.group(1)) if nh_m else None

        # Auto-generate description for tunnels that don't have one
        raw_desc = desc_m.group(1).strip() if desc_m else ""
        if not raw_desc and name.lower().startswith("tunnel"):
            parts = []
            if tunnel_source:
                parts.append(f"src:{tunnel_source}")
            if tunnel_destination:
                parts.append(f"dst:{tunnel_destination}")
            if tunnel_mode:
                parts.append(tunnel_mode)
            raw_desc = " | ".join(parts)

        results.append({
            "name":               name,
            "cidr":               cidr,
            "prefix":             prefix,
            "secondary_ips":      secondary_ips,
            "ipv6_addresses":     ipv6_addresses,
            "description":        raw_desc,
            "mtu":                int(mtu_m.group(1)) if mtu_m else None,
            "mac":                None,
            "speed_mbps":         None,
            "bandwidth_kbps":     None,
            "admin_up":           not shutdown,
            "oper_up":            not shutdown,
            "vrf_name":           vrf_name,
            "channel_group":      channel_group,
            "switchport_mode":    switchport_mode,
            "access_vlan":        access_vlan,
            "trunk_vlans":        trunk_vlans,
            "dot1q_tag":          dot1q_tag,
            "tunnel_source":      tunnel_source,
            "tunnel_destination": tunnel_destination,
            "tunnel_mode":        tunnel_mode,
            "tunnel_key":         tunnel_key,
            "nhrp_network_id":    nhrp_network_id,
        })
    return results


def _parse_facts_from_config(config: str) -> dict:
    """Extract hostname, IOS version, and platform from a running/golden config."""
    facts = {
        "manufacturer": "Cisco",
        "model":        "Unknown",
        "serial":       "",
        "version":      "",
        "platform":     "IOS",
        "hostname":     "",
    }
    m = re.search(r"^version\s+([\d.()A-Za-z]+)", config, re.MULTILINE)
    if m:
        facts["version"] = m.group(1)
    if "IOS XE" in config or "IOS-XE" in config:
        facts["platform"] = "IOS-XE"
    elif "NX-OS" in config or "NXOS" in config:
        facts["platform"] = "NX-OS"
    m = re.search(r"^hostname\s+(\S+)", config, re.MULTILINE)
    if m:
        facts["hostname"] = m.group(1)
    return facts


def _parse_vrfs_from_config(config: str) -> list[dict]:
    """Extract VRF names and route-distinguishers from a running/golden config."""
    vrfs: list[dict] = []
    seen: set = set()

    def _add(name: str, body: str) -> None:
        if name in seen:
            return
        seen.add(name)
        rd_m = re.search(r"^\s+rd\s+(\S+)", body, re.MULTILINE)
        vrfs.append({"name": name, "rd": rd_m.group(1) if rd_m else ""})

    for m in re.finditer(r"^vrf definition\s+(\S+)(.*?)(?=^\S|\Z)",
                         config, re.MULTILINE | re.DOTALL):
        _add(m.group(1), m.group(2))
    for m in re.finditer(r"^ip vrf\s+(\S+)(.*?)(?=^\S|\Z)",
                         config, re.MULTILINE | re.DOTALL):
        _add(m.group(1), m.group(2))
    return vrfs


def _parse_vlans_from_config(config: str) -> list[dict]:
    """Extract VLAN IDs and names from a running/golden config (switch configs)."""
    vlans: list[dict] = []
    seen: set = set()
    for m in re.finditer(r"^vlan\s+(\d+)\s*$(.*?)(?=^\S|\Z)",
                         config, re.MULTILINE | re.DOTALL):
        vid = int(m.group(1))
        if vid in (1002, 1003, 1004, 1005) or vid in seen:
            continue
        seen.add(vid)
        name_m = re.search(r"^\s+name\s+(.+)$", m.group(2), re.MULTILINE)
        vlans.append({
            "vlan_id": vid,
            "name":    name_m.group(1).strip() if name_m else f"VLAN{vid}",
        })
    return vlans


def _parse_static_routes_from_config(config: str) -> list[dict]:
    """Extract static routes from a running/golden config.

    Returns [{prefix, nexthop, distance, vrf}] — suitable for IPAM prefix creation.
    """
    routes: list[dict] = []
    for m in re.finditer(
        r"^ip route\s+(?:vrf\s+(\S+)\s+)?(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+(\S+)(?:\s+(\d+))?",
        config, re.MULTILINE,
    ):
        vrf_name = m.group(1) or ""
        network  = m.group(2)
        mask     = m.group(3)
        nexthop  = m.group(4)
        distance = int(m.group(5)) if m.group(5) else 1
        try:
            net = ipaddress.IPv4Network(f"{network}/{mask}", strict=False)
            routes.append({
                "prefix":   str(net),
                "nexthop":  nexthop,
                "distance": distance,
                "vrf":      vrf_name,
            })
        except ValueError:
            pass
    return routes


_PROTOCOL_TAG_COLORS = {
    "ospf":  "2196f3",
    "bgp":   "4caf50",
    "mpls":  "ff9800",
    "cdp":   "9c27b0",
    "eigrp": "00bcd4",
    "rip":   "f44336",
}


def _parse_protocol_tags_from_config(config: str) -> list[str]:
    """Detect routing/transport protocols enabled in a config.

    Returns a list of lowercase tag names ("ospf", "bgp", "mpls", …).
    """
    tags: list[str] = []
    checks = [
        ("ospf",  r"^router ospf\s",    re.MULTILINE),
        ("bgp",   r"^router bgp\s",     re.MULTILINE),
        ("mpls",  r"^\s*mpls ip\b",     re.MULTILINE),
        ("cdp",   r"^cdp run\b",        re.MULTILINE),
        ("eigrp", r"^router eigrp\s",   re.MULTILINE),
        ("rip",   r"^router rip\b",     re.MULTILINE),
    ]
    for tag, pattern, flags in checks:
        if re.search(pattern, config, flags):
            tags.append(tag)
    return tags


def _parse_routing_context_from_config(config: str) -> dict:
    """Extract structured OSPF, BGP, NTP, and SNMP data from a config.

    Returns a dict suitable for merging into local_context_data.
    """
    ctx: dict = {}

    # OSPF processes
    ospf_procs = []
    for m in re.finditer(
        r"^router ospf\s+(\d+)(.*?)(?=^router\s|^interface\s|\Z)",
        config, re.MULTILINE | re.DOTALL,
    ):
        body = m.group(2)
        rid_m = re.search(r"^\s+router-id\s+(\S+)", body, re.MULTILINE)
        areas = sorted(set(re.findall(r"\barea\s+(\S+)", body)))
        ospf_procs.append({
            "process_id": int(m.group(1)),
            "router_id":  rid_m.group(1) if rid_m else "",
            "areas":      areas,
        })
    if ospf_procs:
        ctx["ospf"] = ospf_procs

    # BGP
    bgp_m = re.search(
        r"^router bgp\s+(\d+)(.*?)(?=^router\s|^interface\s|\Z)",
        config, re.MULTILINE | re.DOTALL,
    )
    if bgp_m:
        bgp_body = bgp_m.group(2)
        rid_m = re.search(r"^\s+bgp router-id\s+(\S+)", bgp_body, re.MULTILINE)
        neighbors = []
        for nb_m in re.finditer(
            r"^\s+neighbor\s+(\S+)\s+remote-as\s+(\d+)", bgp_body, re.MULTILINE
        ):
            neighbors.append({"peer": nb_m.group(1), "remote_as": int(nb_m.group(2))})
        ctx["bgp"] = {
            "asn":       int(bgp_m.group(1)),
            "router_id": rid_m.group(1) if rid_m else "",
            "neighbors": neighbors,
        }

    # NTP servers
    ntp = re.findall(r"^ntp server\s+(\S+)", config, re.MULTILINE)
    if ntp:
        ctx["ntp_servers"] = ntp

    # SNMP communities / version
    snmp: dict = {}
    for sm in re.finditer(r"^snmp-server community\s+(\S+)\s+(RO|RW)", config, re.MULTILINE):
        snmp.setdefault("communities", []).append({
            "community":  sm.group(1),
            "permission": sm.group(2),
        })
    sv_m = re.search(r"^snmp-server version\s+(\S+)", config, re.MULTILINE)
    if sv_m:
        snmp["version"] = sv_m.group(1)
    if snmp:
        ctx["snmp"] = snmp

    # Tunnels
    tunnels = []
    for m in re.finditer(
        r"^interface\s+(Tunnel\S+)(.*?)(?=^interface\s|\Z)",
        config, re.MULTILINE | re.DOTALL,
    ):
        body = m.group(2)
        ts_m = re.search(r"^\s+tunnel source\s+(\S+)", body, re.MULTILINE)
        td_m = re.search(r"^\s+tunnel destination\s+(\S+)", body, re.MULTILINE)
        tm_m = re.search(r"^\s+tunnel mode\s+(.+?)$", body, re.MULTILINE)
        tk_m = re.search(r"^\s+tunnel key\s+(\d+)", body, re.MULTILINE)
        nh_m = re.search(r"^\s+ip nhrp network-id\s+(\d+)", body, re.MULTILINE)
        tun: dict = {"name": m.group(1)}
        if ts_m:
            tun["source"] = ts_m.group(1)
        if td_m:
            tun["destination"] = td_m.group(1)
        if tm_m:
            tun["mode"] = tm_m.group(1).strip()
        if tk_m:
            tun["key"] = int(tk_m.group(1))
        if nh_m:
            tun["nhrp_network_id"] = int(nh_m.group(1))
        tunnels.append(tun)
    if tunnels:
        ctx["tunnels"] = tunnels

    return ctx


def _scan_device_from_golden(dev: dict) -> dict:
    """Build a NetBox scan result from the device's saved golden config.

    No SSH session is opened — all data comes from the golden config file.
    Returns the same structure as _scan_device so the rest of the sync
    pipeline is unchanged.
    """
    from modules.ai_assistant import _load_golden_config_file

    ip       = dev.get("ip", "")
    hostname = dev.get("hostname", "") or ip

    golden = _load_golden_config_file(ip)
    if not golden:
        return {
            "ip":       ip,
            "hostname": hostname,
            "error":    "No golden config saved — run 'Save Golden Config' first",
        }

    facts           = _parse_facts_from_config(golden)
    hostname        = facts.pop("hostname") or hostname
    interfaces      = _parse_all_interfaces_from_config(golden)
    vrfs            = _parse_vrfs_from_config(golden)
    vlans           = _parse_vlans_from_config(golden)
    static_routes   = _parse_static_routes_from_config(golden)
    protocol_tags   = _parse_protocol_tags_from_config(golden)
    routing_context = _parse_routing_context_from_config(golden)

    log.info("netbox: golden-config scan for %s (%s) — %d interfaces, %d static routes, tags: %s",
             hostname, ip, len(interfaces), len(static_routes), protocol_tags)
    return {
        "ip":              ip,
        "hostname":        hostname,
        "facts":           facts,
        "interfaces":      interfaces,
        "vlans":           vlans,
        "vrfs":            vrfs,
        "cdp_neighbors":   [],
        "running_config":  golden,
        "static_routes":   static_routes,
        "protocol_tags":   protocol_tags,
        "routing_context": routing_context,
    }


# ---------------------------------------------------------------------------
# Sync entry points
# ---------------------------------------------------------------------------

def sync_list_to_netbox(list_name: str, devices: list[dict],
                        status_cache: Optional[dict] = None,
                        max_workers: int = 6) -> dict:
    """Sync a single device list to NetBox. Returns a summary dict."""
    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return {"ok": False, "error": "NetBox URL and API token are not configured"}

    session = _session_from_config(cfg)
    base    = cfg["url"]

    log.info("netbox: starting sync for list '%s' (%d device(s))", list_name, len(devices))

    # Build/refresh the region, site, shared device-role, and config template up-front.
    try:
        region = _ensure_region(session, base, list_name)
        site   = _ensure_site(session, base, list_name, region["id"])
        role   = _ensure_device_role(session, base, "Network Device")
    except Exception as exc:
        log.exception("netbox: failed to provision region/site/role for '%s'", list_name)
        return {"ok": False, "error": f"Failed to set up NetBox region/site: {exc}"}

    # Config template — needed for "Render Config" in the NetBox device view.
    # Returns None gracefully on pre-3.5 NetBox instances.
    config_template_id = _ensure_config_template(session, base)

    # List-level VRF — groups all IPs for this list under one VRF in NetBox IPAM.
    # Per-interface VRFs (ip vrf forwarding X) override this on a per-interface basis.
    list_vrf_id: Optional[int] = None
    try:
        list_vrf = _ensure_vrf(session, base, list_name,
                               rd=f"ndm:{_slug(list_name)}")
        list_vrf_id = list_vrf["id"]
        log.info("netbox: list VRF '%s' id=%s", list_name, list_vrf_id)
    except Exception as exc:
        log.warning("netbox: could not create list VRF '%s': %s", list_name, exc)

    # Populate from golden configs — no SSH needed, works for offline devices.
    scanned: list[dict] = [_scan_device_from_golden(d) for d in devices]

    created = 0
    updated = 0
    failed: list[dict] = []
    ipam_stats: dict = {
        "interfaces_synced": 0, "prefixes_synced": 0,
        "ips_synced": 0,
        "vrfs_synced": 1 if list_vrf_id else 0,  # count the list-level VRF
        "vlans_synced": 0, "cables_synced": 0, "tunnels_synced": 0,
    }

    # hostname → {device_id, nb_iface_map} for cable wiring pass
    device_registry: dict = {}

    for result in scanned:
        if result.get("error"):
            failed.append({"hostname": result["hostname"], "ip": result["ip"], "error": result["error"]})
            continue
        try:
            outcome = _upsert_device(
                session, base,
                hostname=result["hostname"],
                ip=result["ip"],
                facts=result["facts"],
                interfaces=result.get("interfaces", []),
                site_id=site["id"],
                role_id=role["id"],
                ipam_stats=ipam_stats,
                vlans=result.get("vlans", []),
                vrfs=result.get("vrfs", []),
                running_config=result.get("running_config", ""),
                config_template_id=config_template_id,
                static_routes=result.get("static_routes", []),
                protocol_tags=result.get("protocol_tags", []),
                routing_context=result.get("routing_context", {}),
                list_vrf_id=list_vrf_id,
            )
            if outcome["action"] == "created":
                created += 1
            else:
                updated += 1
            device_registry[result["hostname"]] = {
                "device_id":    outcome["id"],
                "nb_iface_map": outcome.get("nb_iface_map", {}),
                "cdp_neighbors": result.get("cdp_neighbors", []),
            }
        except Exception as exc:
            log.exception("netbox: upsert failed for %s", result["hostname"])
            failed.append({"hostname": result["hostname"], "ip": result["ip"], "error": str(exc)})

    # ── CDP → cables (second pass so both endpoints exist) ────────────────
    for local_hostname, reg in device_registry.items():
        for cdp in reg.get("cdp_neighbors", []):
            remote_hostname = cdp.get("remote_hostname", "")
            if remote_hostname not in device_registry:
                continue   # remote device not in this list — skip
            local_iface  = cdp.get("local_iface", "")
            remote_iface = cdp.get("remote_iface", "")
            if not (local_iface and remote_iface):
                continue
            local_iface_id  = reg["nb_iface_map"].get(local_iface)
            remote_iface_id = device_registry[remote_hostname]["nb_iface_map"].get(remote_iface)
            if not (local_iface_id and remote_iface_id):
                continue
            try:
                cable = _ensure_cable(
                    session, base,
                    "interface", local_iface_id,
                    "interface", remote_iface_id,
                )
                if cable:
                    ipam_stats["cables_synced"] = ipam_stats.get("cables_synced", 0) + 1
            except Exception as exc:
                log.debug("netbox: cable failed %s:%s → %s:%s: %s",
                          local_hostname, local_iface, remote_hostname, remote_iface, exc)

    summary = {
        "ok":         True,
        "list":       list_name,
        "region":     region.get("name"),
        "site":       site.get("name"),
        "total":      len(devices),
        "synced":     len([r for r in scanned if not r.get("error")]),
        "created":    created,
        "updated":    updated,
        "failed":     failed,
        "config_template_id": config_template_id,
        "ipam": {
            "interfaces": ipam_stats.get("interfaces_synced", 0),
            "prefixes":   ipam_stats.get("prefixes_synced", 0),
            "ips":        ipam_stats.get("ips_synced", 0),
            "vrfs":       ipam_stats.get("vrfs_synced", 0),
            "vlans":      ipam_stats.get("vlans_synced", 0),
            "cables":     ipam_stats.get("cables_synced", 0),
            "tunnels":    ipam_stats.get("tunnels_synced", 0),
        },
        "timestamp":  time.strftime("%Y-%m-%d %H:%M:%S"),
        "netbox_url": f"{base}/dcim/sites/{site['id']}/",
        "ipam_url":   f"{base}/ipam/prefixes/",
    }

    _record_sync_status(list_name, summary)
    log.info(
        "netbox: sync complete for '%s' — devices created=%d updated=%d failed=%d; "
        "IPAM interfaces=%d prefixes=%d ips=%d vrfs=%d vlans=%d cables=%d tunnels=%d",
        list_name, created, updated, len(failed),
        summary["ipam"]["interfaces"], summary["ipam"]["prefixes"],
        summary["ipam"]["ips"], summary["ipam"]["vrfs"],
        summary["ipam"]["vlans"], summary["ipam"]["cables"],
        summary["ipam"]["tunnels"],
    )
    return summary


def remove_list_from_netbox(list_name: str) -> dict:
    """Delete all NetBox objects that were created for a device list.

    Deletes (in order): devices in the site → site → region → list VRF.
    NetBox cascades the device deletion to interfaces, IP addresses, cables,
    and config contexts automatically.

    Returns {ok, deleted_devices, deleted_site, deleted_region, deleted_vrf, error}.
    """
    cfg = get_netbox_config()
    if not cfg["url"] or not cfg["token"]:
        return {"ok": False, "error": "NetBox URL and API token are not configured"}

    session = _session_from_config(cfg)
    base    = cfg["url"]
    slug    = _slug(list_name)

    deleted_devices = 0
    deleted_site    = False
    deleted_region  = False
    deleted_vrf     = False

    try:
        # Find the site
        site = _nb_first(session, base, "dcim/sites/", slug=slug)
        if site:
            site_id = site["id"]
            # Delete all devices in the site
            devices = _nb_get(session, base, "dcim/devices/", site_id=site_id)
            for dev in devices:
                try:
                    r = session.delete(f"{base}/api/dcim/devices/{dev['id']}/", timeout=15)
                    if r.ok or r.status_code == 404:
                        deleted_devices += 1
                    else:
                        log.warning("netbox remove: device %s delete returned %s",
                                    dev.get("name"), r.status_code)
                except Exception as exc:
                    log.warning("netbox remove: device %s delete failed: %s",
                                dev.get("name"), exc)

            # Delete the site
            try:
                r = session.delete(f"{base}/api/dcim/sites/{site_id}/", timeout=15)
                if r.ok or r.status_code == 404:
                    deleted_site = True
            except Exception as exc:
                log.warning("netbox remove: site delete failed: %s", exc)

        # Find and delete the region
        region = _nb_first(session, base, "dcim/regions/", slug=slug)
        if region:
            try:
                r = session.delete(f"{base}/api/dcim/regions/{region['id']}/", timeout=15)
                if r.ok or r.status_code == 404:
                    deleted_region = True
            except Exception as exc:
                log.warning("netbox remove: region delete failed: %s", exc)

        # Delete the list-level VRF (devices are gone so IPs are already removed)
        vrf = _nb_first(session, base, "ipam/vrfs/", name=list_name)
        if vrf:
            try:
                r = session.delete(f"{base}/api/ipam/vrfs/{vrf['id']}/", timeout=15)
                if r.ok or r.status_code == 404:
                    deleted_vrf = True
            except Exception as exc:
                log.warning("netbox remove: VRF delete failed: %s", exc)

        # Clear local sync status for this list
        with _status_lock:
            data = load_sync_status()
            data.get("lists", {}).pop(list_name, None)
            data.get("running", {}).pop(list_name, None)
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                tmp = _SYNC_STATUS_FILE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2)
                os.replace(tmp, _SYNC_STATUS_FILE)
            except Exception as exc:
                log.warning("netbox remove: could not update sync status: %s", exc)

        log.info("netbox: removed list '%s' — devices=%d site=%s region=%s vrf=%s",
                 list_name, deleted_devices, deleted_site, deleted_region, deleted_vrf)
        return {
            "ok":              True,
            "list":            list_name,
            "deleted_devices": deleted_devices,
            "deleted_site":    deleted_site,
            "deleted_region":  deleted_region,
            "deleted_vrf":     deleted_vrf,
        }

    except Exception as exc:
        log.exception("netbox: remove_list_from_netbox failed for '%s'", list_name)
        return {"ok": False, "error": str(exc)}


def sync_all_lists_to_netbox(lists_with_devices: list[tuple[str, list[dict]]],
                             status_cache: Optional[dict] = None) -> dict:
    """Sync multiple device lists sequentially. Each list becomes its own region."""
    results = []
    overall_ok = True
    for name, devs in lists_with_devices:
        res = sync_list_to_netbox(name, devs, status_cache=status_cache)
        results.append(res)
        if not res.get("ok"):
            overall_ok = False
    return {"ok": overall_ok, "results": results,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}


# ---------------------------------------------------------------------------
# Status persistence (surfaced by the NetBox tab)
# ---------------------------------------------------------------------------

def _record_sync_status(list_name: str, summary: dict) -> None:
    """Persist the latest sync summary per list to disk."""
    with _status_lock:
        data = load_sync_status()
        data.setdefault("lists", {})[list_name] = summary
        data["last_sync"] = summary.get("timestamp")
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            tmp = _SYNC_STATUS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, _SYNC_STATUS_FILE)
        except Exception as exc:
            log.warning("netbox: could not write sync status: %s", exc)


def load_sync_status() -> dict:
    """Return the on-disk sync status (empty dict if none yet)."""
    if not os.path.exists(_SYNC_STATUS_FILE):
        return {}
    try:
        with open(_SYNC_STATUS_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def set_sync_running(list_name: str, running: bool) -> None:
    """Mark a list's sync as in-progress or done (for UI spinner state)."""
    with _status_lock:
        data = load_sync_status()
        data.setdefault("running", {})[list_name] = bool(running)
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(_SYNC_STATUS_FILE, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except Exception:
            pass
