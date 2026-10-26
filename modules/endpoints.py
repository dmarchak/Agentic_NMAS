"""The endpoint layer (PHASE8_PLAN 15.15, "Gaps made explicit, and the endpoint layer"; C1772):
where each endpoint (a host, a phone, a printer) is attached, from what the network itself says.

**Its sources, observed, never typed:**
- each device's MAC table, ARP and IPv6 neighbours, read through the platform-pack entries
  (`modules/nsot/platform_reads.json`: per dialect, the command and the pattern its lines fill;
  a command the read-only allowlist refuses is never sent), by `readers/endpoints`;
- DHCP leases through an optional, generic lease source (`lease_sources`, Kea's the first),
  which name a MAC's host and address.

**Location.** An endpoint is located where a switch learned its MAC on a port that is neither a
trunk (committed intent) nor an uplink (a port with a managed neighbour: the network model's
point-to-point links and the Topology read's cables, `intent_names.neighbours_of`). A MAC learned
on a trunk or an uplink is everywhere upstream of it, so it locates nothing. Each endpoint keeps
where it was last located and when (`last_seen`) across reads: a switch forgets an idle host's
MAC in minutes (measured 2026-10-26: a lab switch's host ports held none while its hosts sat idle), so a
location older than the last read is said with its age, never as now.

**What it holds,** per endpoint: its MAC, its addresses, its hostname when leased, the device,
interface and VLAN it was located on, when it was last seen there, and the sources that said so;
versioned like the network model (a digest of who is where). Endpoints are the topology egress
class: nothing here sends them anywhere.
"""

import hashlib
import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

PACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nsot", "platform_reads.json")
READS = ("mac_table", "arp", "ipv6_neighbors")
#: How long an endpoint's last location is kept after it was last seen.
RETAIN_SECONDS = 30 * 86400
_MAC = re.compile(r"^[0-9a-f]{12}$")


def entries() -> dict:
    """The pack's read entries, by dialect: ``{dialect: {read: {"command", "line"}}}``."""
    with open(PACK, encoding="utf-8") as fh:
        return json.load(fh).get("reads") or {}


def entry(dialect: str, read: str) -> dict:
    """*dialect*'s entry for *read*, or ``{}`` when its pack has none (said as not supported)."""
    return (entries().get(dialect) or {}).get(read) or {}


def mac_of(text: str) -> str:
    """A MAC in one form, ``aa:c1:ab:99:f6:e2``, from any of the forms devices and Kea print;
    "" when it is no MAC."""
    hexes = re.sub(r"[^0-9a-f]", "", str(text or "").lower())
    if not _MAC.match(hexes):
        return ""
    return ":".join(hexes[i:i + 2] for i in range(0, 12, 2))


def parse(dialect: str, read: str, text: str) -> list:
    """Each line of *text* the pack's pattern fills, as its named groups (the MAC normalised);
    [] for a dialect with no entry."""
    e = entry(dialect, read)
    if not e:
        return []
    rx = re.compile(e["line"])
    out = []
    for line in (text or "").splitlines():
        m = rx.match(line)
        if m:
            got = m.groupdict()
            got["mac"] = mac_of(got.get("mac", ""))
            if got["mac"]:
                out.append(got)
    return out


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _epoch(text: str) -> float:
    try:
        import calendar
        return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return 0.0


def locate(reads: dict, leases: list, ports: dict, previous: list = None,
           now: float = None) -> dict:
    """The network's endpoints from this read: ``{"endpoints": [...], "version", "read_at",
    "ignored": n}``.

    *reads*: ``{device: {"mac_table": [...], "arp": [...], "ipv6_neighbors": [...], "error"}}``
    (`parse`'s rows). *leases*: the lease source's rows (``mac``, ``address``, ``hostname``).
    *ports*: ``{device: {"trunks": set, "uplinks": set}}``, the ports that locate nothing.
    *previous*: the last value's endpoints, whose locations are carried forward with their
    last_seen when not seen now (and dropped after `RETAIN_SECONDS`)."""
    from modules.nsot import ifnames

    now = time.time() if now is None else now
    at = _iso(now)
    by_mac, ignored = {}, 0

    def ep(mac):
        return by_mac.setdefault(mac, {"mac": mac, "addresses": [], "hostname": "",
                                       "device": "", "interface": "", "vlan": "",
                                       "last_seen": "", "sources": []})

    def note(e, source):
        if source not in e["sources"]:
            e["sources"].append(source)

    for device, got in sorted(reads.items()):
        skip = ports.get(device) or {}
        stop = {ifnames.canonical(p).lower() for p in (skip.get("trunks") or set())
                | (skip.get("uplinks") or set())}
        for row in got.get("mac_table") or []:
            port = ifnames.canonical(row.get("port", ""))
            if port.lower() in stop:
                ignored += 1
                continue
            e = ep(row["mac"])
            e.update(device=device, interface=port, vlan=str(row.get("vlan") or ""),
                     last_seen=at)
            note(e, f"{device}'s MAC table")
        for kind in ("arp", "ipv6_neighbors"):
            for row in got.get(kind) or []:
                e = by_mac.get(row["mac"])
                if e is None and row["mac"] not in {m for m in by_mac}:
                    e = ep(row["mac"])
                addr = row.get("address", "")
                if addr and addr not in e["addresses"]:
                    e["addresses"].append(addr)
                note(e, f"{device}'s {'ARP' if kind == 'arp' else 'IPv6 neighbours'}")
    for lease in leases or []:
        mac = mac_of(lease.get("mac", ""))
        if not mac:
            continue
        e = by_mac.get(mac)
        if e is None:
            continue                    # a lease no device has seen locates nothing
        if lease.get("hostname"):
            e["hostname"] = lease["hostname"]
        if lease.get("address") and lease["address"] not in e["addresses"]:
            e["addresses"].append(lease["address"])
        note(e, lease.get("source") or "a DHCP lease")
    for old in previous or []:
        mac = old.get("mac", "")
        e = by_mac.get(mac)
        seen = _epoch(old.get("last_seen", ""))
        if e is None:
            if old.get("device") and now - seen <= RETAIN_SECONDS:
                by_mac[mac] = dict(old)            # not seen in this read: kept, its age said
            continue
        if not e["device"] and old.get("device") and now - seen <= RETAIN_SECONDS:
            e.update(device=old["device"], interface=old.get("interface", ""),
                     vlan=old.get("vlan", ""), last_seen=old.get("last_seen", ""))
        if not e["hostname"] and old.get("hostname"):
            e["hostname"] = old["hostname"]
    endpoints = [by_mac[m] for m in sorted(by_mac)]
    key = json.dumps([(e["mac"], e["device"], e["interface"]) for e in endpoints])
    return {"endpoints": endpoints, "read_at": at, "ignored": ignored,
            "version": "ep-" + hashlib.sha256(key.encode()).hexdigest()[:12]}


def find(endpoints: list, name: str) -> list:
    """The endpoints *name* means: its hostname, one of its addresses, or its MAC."""
    want = str(name or "").strip().lower()
    mac = mac_of(want)
    return [e for e in endpoints or [] if (e.get("hostname") or "").lower() == want
            or want in [a.lower() for a in e.get("addresses") or []]
            or (mac and e.get("mac") == mac)]


def coverage_layer(network: str) -> dict:
    """The endpoint layer as a coverage header states it (`network_model.coverage`), from the
    endpoint store now: present when every device was read, partial when some could not be
    (named), not_collected before the first read or when the store cannot be read. A caller
    that captures it (an alert's evidence pack, at the alert's time) passes it as *carried*."""
    got = stored(network)
    if got["state"] != "read":
        return {"state": "not_collected", "source": "", "age": "",
                "why": f"no endpoint read for this network ({got['why']}) (C1772)"}
    unread = sorted(h for h, d in (got.get("devices") or {}).items() if d.get("error"))
    return {"state": "partial" if unread else "present",
            "source": "each device's MAC table, ARP and IPv6 neighbours, and the DHCP leases "
                      "(the endpoint reader)",
            "age": got.get("read_at", ""),
            "why": f"{', '.join(unread)} could not be read" if unread else ""}


def stored(network: str) -> dict:
    """The endpoint reader's stored value for *network*: ``{"state", "why", "endpoints",
    "read_at", "devices"}``; "absent" before its first read, never "none"."""
    from modules import reader_job
    got = reader_job.read_cached("endpoints")
    good = (got.get("doc") or {}).get("last_good") or {}
    value = (good.get("value") or {}).get("lists", {}).get(network)
    if value is None:
        return {"state": "absent" if got.get("state") in ("absent", "ok") else "unreadable",
                "why": got.get("why") or "the endpoint reader has not read this network",
                "endpoints": [], "read_at": "", "devices": {}}
    return dict(value, state="read", why="")
