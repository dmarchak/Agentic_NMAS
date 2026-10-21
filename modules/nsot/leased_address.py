"""nsot/leased_address.py

An interface's IPv4 address, for every reader that needs one (C1442).

Intent and the golden say ``ip address dhcp`` for a device whose management address Kea
leases (a ZTP device, or one onboarded with a DHCP address), so a reader that takes an
interface's address from them alone finds none there: NetBox put the address on the wrong
interface, Topology called a working OSPF adjacency "not in committed intent" and drew no RIP
edge, and Verify's expectations could not predict an adjacency the program would drop.

The address is stored, once: onboarding's Verify reads Kea's lease and records it on the
device's manifest entry (``mgmt_ip``, ``mgmt_prefix_len``; `onboard.run_phase_two`),
committed with the device's first golden (`repo.save_golden` stages the manifest). This module
is the one place that joins the two:

* an interface's STATIC address in intent (``"A M"``) is its address;
* else, on a device whose manifest says its address came from DHCP (``address_source`` dhcp or
  ztp) with a known prefix length, the device's ONE ``dhcp`` interface holds the leased address.
  Several ``dhcp`` interfaces are narrowed to those outside any VRF (the lease is reached in the
  table Mercury reaches the device through); still several, or none, and no interface is given
  the address, said by `why_not`: a guess is a silent wrong answer. The lease's address is the
  reservation's when recorded (a management address moved since Verify does not move it), and
  an address intent holds statically on any interface is never a lease.

What it cannot say, stated: DHCPv6 is out of scope (an IPv6 lease is never recorded, so an
IPv6 management address in the manifest is not applied as one); an interface's IPv6
addresses are always intent's own, static. A dynamic lease that moved since Verify is not
seen: onboarding refuses a DHCP device without a Kea reservation, so the address recorded is
the reserved one.
"""

import copy
import ipaddress
import json
import logging

log = logging.getLogger(__name__)

#: The manifest's ``address_source`` values whose address is a lease.
LEASED_SOURCES = ("dhcp", "ztp")


def is_dhcp(value) -> bool:
    """Does intent's ``ipv4`` value (everything after ``ip address``) say ``dhcp``?"""
    words = str(value or "").split()
    return bool(words) and words[0].lower() == "dhcp"


def lease_of(entry: dict):
    """The leased ``IPv4Interface`` a manifest *entry* records, or None: not a leased source,
    no address, no prefix length (unknown is not guessed), or not IPv4 (DHCPv6 is out of
    scope). The address is the RESERVED one when recorded (onboarding refuses a lease that
    disagrees with its reservation, and a management address moved since Verify does not move
    the lease), else the management address Verify recorded from the lease."""
    entry = entry or {}
    if entry.get("address_source") not in LEASED_SOURCES:
        return None
    address = str(entry.get("reserved_address") or entry.get("mgmt_ip") or "").strip()
    try:
        prefix = int(entry.get("mgmt_prefix_len") or 0)
    except (TypeError, ValueError):
        return None
    if not address or prefix <= 0:
        return None
    try:
        lease = ipaddress.ip_interface(f"{address}/{prefix}")
    except ValueError:
        return None
    return lease if lease.version == 4 else None


def _static_address(value):
    """The address of a static ``ipv4`` value (intent's ``"A M"``, or ``"A/len"``), or None."""
    words = str(value or "").split()
    try:
        if len(words) == 2:
            return ipaddress.ip_interface(f"{words[0]}/{words[1]}").ip
        if len(words) == 1 and "/" in words[0]:
            return ipaddress.ip_interface(words[0]).ip
    except ValueError:
        return None
    return None


def held_statically(interfaces, entry: dict) -> str:
    """The interface of *interfaces* whose STATIC address is *entry*'s lease address, or "":
    an address intent holds statically is not a lease now, whatever the manifest says."""
    lease = lease_of(entry)
    if lease is None:
        return ""
    for iface in interfaces or []:
        if isinstance(iface, dict) and _static_address(iface.get("ipv4")) == lease.ip:
            return iface.get("name", "") or "an interface"
    return ""


def leased_interface(interfaces) -> str:
    """The name of the ONE interface of *interfaces* (intent's shape: ``name``, ``ipv4``,
    ``vrf``) that holds a lease, or "" when there is none or no single one."""
    dhcp = [i for i in interfaces or [] if isinstance(i, dict) and is_dhcp(i.get("ipv4"))]
    if len(dhcp) > 1:
        dhcp = [i for i in dhcp if not i.get("vrf")]
    return dhcp[0].get("name", "") if len(dhcp) == 1 else ""


def why_not(interfaces, entry: dict) -> str:
    """Why no interface of *interfaces* is given *entry*'s lease, or "" when one is."""
    if lease_of(entry) is None:
        return "the manifest records no leased IPv4 address with its prefix length"
    held = held_statically(interfaces, entry)
    if held:
        return (f"{lease_of(entry).ip} is {held}'s address statically in intent, so it is not "
                "a lease now")
    dhcp = [i.get("name", "") for i in interfaces or []
            if isinstance(i, dict) and is_dhcp(i.get("ipv4"))]
    if not dhcp:
        return "no interface says `ip address dhcp`"
    if not leased_interface(interfaces):
        return (f"{len(dhcp)} interfaces say `ip address dhcp` ({', '.join(dhcp)}), and the "
                "lease is not guessed onto one of them")
    return ""


def interface_ipv4(iface: dict, interfaces, entry: dict) -> str:
    """*iface*'s IPv4 address in intent's ``"A M"`` form: its static one, else the lease when it
    is the device's one leased interface, else ""."""
    value = str((iface or {}).get("ipv4") or "").strip()
    if not is_dhcp(value):
        return value
    lease = lease_of(entry)
    if lease is None or (iface or {}).get("name", "") != leased_interface(interfaces) \
            or held_statically(interfaces, entry):
        return ""
    return f"{lease.ip} {lease.netmask}"


def with_lease(hv: dict, entry: dict) -> dict:
    """*hv* with its one leased interface's ``ipv4`` the lease (a copy; *hv* is untouched), or
    *hv* itself when there is none to apply."""
    interfaces = (hv or {}).get("interfaces") if isinstance(hv, dict) else None
    if not interfaces or lease_of(entry) is None:
        return hv
    name = leased_interface(interfaces)
    if not name or held_statically(interfaces, entry):
        return hv
    out = copy.deepcopy(hv)
    for iface in out["interfaces"]:
        if isinstance(iface, dict) and iface.get("name") == name:
            iface["ipv4"] = interface_ipv4(iface, interfaces, entry)
    return out


def entries_by_name(manifest: dict) -> dict:
    """``{lower-case name: entry}`` from a manifest document."""
    out = {}
    for entry in ((manifest or {}).get("devices") or {}).values():
        name = str((entry or {}).get("name") or "").strip().lower()
        if name:
            out[name] = entry
    return out


def with_leases(intents: dict, manifest: dict) -> dict:
    """``{host: host_vars}`` with each device's lease applied (`with_lease`), from the manifest
    document *manifest*; a host the manifest does not hold is returned as it is."""
    entries = entries_by_name(manifest)
    return {host: with_lease(hv, entries.get(str(host).lower()))
            for host, hv in (intents or {}).items()}


def parse_manifest(text: str) -> tuple:
    """``(manifest, error)`` from the manifest's committed text; an empty one and the reason
    when it does not parse."""
    try:
        data = json.loads(text or "{}")
    except ValueError as exc:
        return {"devices": {}}, f"the committed manifest does not parse ({exc})"
    return (data if isinstance(data, dict) else {"devices": {}}), ""


def committed_manifest(repo: str) -> tuple:
    """``(manifest, error)``: the manifest committed at HEAD in *repo* (one git call); an empty
    one and no error when nothing is committed there, and the reason when it cannot be read."""
    import os

    from modules.nsot.repo import MANIFEST_REL, git

    empty = {"devices": {}}
    if not os.path.isdir(os.path.join(repo or "", ".git")):
        return empty, ""                              # no repository: nothing committed
    rc, out, err = git(repo, "show", f"HEAD:{MANIFEST_REL}")
    if rc != 0:
        said = (err or "").lower()
        if any(s in said for s in ("does not exist", "exists on disk, but not in",
                                   "invalid object name", "bad revision")):
            return empty, ""
        return empty, f"the committed manifest could not be read ({err or rc})"
    return parse_manifest(out)
