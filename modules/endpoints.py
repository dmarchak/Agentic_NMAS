"""The endpoint layer (PHASE8_PLAN 15.15, "Gaps made explicit, and the endpoint layer"; C1772):
where each endpoint (a host, a phone, a printer) is attached, from what the network itself says.

**Its sources, observed, never typed:**
- each device's MAC table, ARP and IPv6 neighbours, read through the platform-pack entries
  (`modules/nsot/platform_reads.json`: per dialect, the command and the pattern its lines fill;
  a command the read-only allowlist refuses is never sent), by `readers/endpoints`;
- DHCP leases through an optional, generic lease source (`lease_sources`, Kea's the first),
  which name a MAC's host and address;
- the hosts an SDN controller learned (PHASE8_PLAN 17.1 S14: MAC, IPv4 and IPv6 addresses,
  switch by DPID, port), read from the SDN reader's stored topology (`sdn.topology.
  endpoint_hosts`), so an endpoint behind an OpenFlow switch is located on that switch's port;
  its last seen is when the controller last listed it, with the driver's note on what a
  listing means.

**Location.** An endpoint is located where a switch learned its MAC on a port that is neither a
trunk (committed intent) nor an uplink (a port with a managed neighbour: the network model's
point-to-point links and the Topology read's cables, `intent_names.neighbours_of`). A MAC learned
on a trunk or an uplink is everywhere upstream of it, so it locates nothing. Each endpoint keeps
where it was last located and when (`last_seen`) across reads: a switch forgets an idle host's
MAC in minutes (measured 2026-10-26: a lab switch's host ports held none while its hosts sat
idle), so a location older than the last read is said with its age, never as now (`seen`:
"last seen edge1 GigabitEthernet1/0, 3 h ago").

**Kept, never dropped for its age** (the operator's ruling on C1779, 2026-10-26): passive, so a
last location stays until the endpoint is located elsewhere or its device leaves the network
(a retired device's name carries nothing forward). Past the network's
`endpoint_stale_after_hours` it is said to be stale: a history, not a location.

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
#: The setting naming when a kept location is stale, per network, and its schema default.
STALE_SETTING, STALE_DEFAULT_HOURS = "endpoint_stale_after_hours", 24
_MAC = re.compile(r"^[0-9a-f]{12}$")


def stale_after_hours(network: str) -> int:
    """The network's `endpoint_stale_after_hours`; the default when it cannot be read (logged),
    since a stale mark is a word on a screen, never a gate."""
    from modules import list_settings
    try:
        return int(list_settings.value(network, STALE_SETTING, STALE_DEFAULT_HOURS))
    except Exception as exc:                            # noqa: BLE001 (the default, logged)
        log.warning("endpoints: %s's %s could not be read (%s); %s h is used", network,
                    STALE_SETTING, exc, STALE_DEFAULT_HOURS)
        return STALE_DEFAULT_HOURS


def _ago(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 120:
        return "just now"
    if s < 7200:
        return f"{s // 60} min ago"
    if s < 2 * 86400:
        return f"{s // 3600} h ago"
    return f"{s // 86400} days ago"


def seen(e: dict, now: float = None, stale_hours: int = STALE_DEFAULT_HOURS) -> dict:
    """How an endpoint's location is said: ``{"located", "age", "stale", "said"}``, e.g. "last
    seen edge1 GigabitEthernet1/0, 3 h ago" (and ", stale" past *stale_hours*); one never
    located says so."""
    if not e.get("device"):
        return {"located": False, "age": "", "stale": False,
                "said": "not located: its MAC was in no access port's table at any read"}
    at = _epoch(e.get("last_seen", ""))
    age = (time.time() if now is None else now) - at if at else None
    stale = age is None or age > stale_hours * 3600
    words = _ago(age) if age is not None else "at an unknown time"
    return {"located": True, "age": words, "stale": stale,
            "said": f"last seen {e['device']} {e.get('interface', '')}, {words}"
                    + (" (as its controller lists it)" if e.get("note") else "")
                    + (f", stale (older than {stale_hours} h)" if stale else "")}


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
           now: float = None, controller: list = None) -> dict:
    """The network's endpoints from this read: ``{"endpoints": [...], "version", "read_at",
    "ignored": n}``.

    *reads*: ``{device: {"mac_table": [...], "arp": [...], "ipv6_neighbors": [...], "error"}}``
    (`parse`'s rows). *leases*: the lease source's rows (``mac``, ``address``, ``hostname``).
    *ports*: ``{device: {"trunks": set, "uplinks": set}}``, the ports that locate nothing.
    *previous*: the last value's endpoints, whose locations are carried forward with their
    last_seen when not seen now, whatever their age, while their device is still one this
    read covers (a device gone from the network carries nothing forward).
    *controller*: the hosts the network's SDN controllers learned (`sdn.topology.
    endpoint_hosts`, S14): each locates its MAC on its switch's port (``of:<DPID>``, ``port
    N``) as of the controller's read, unless a device's MAC table located it in this read;
    its addresses, IPv4 and IPv6, join the endpoint's, and the driver's note on what a
    listing means is kept with it (``note``)."""
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
    located_now = {m for m, e in by_mac.items() if e["device"]}
    switches = set()
    for host in controller or []:
        mac = mac_of(host.get("mac", ""))
        if not mac:
            continue
        switches.add(host["device"])
        e = ep(mac)
        if mac not in located_now:
            e.update(device=host["device"], interface=host.get("interface", ""), vlan="",
                     last_seen=host.get("last_seen") or at)
            if host.get("port_name"):
                e["port_name"] = host["port_name"]
            if host.get("note"):
                e["note"] = host["note"]
        for addr in host.get("addresses") or []:
            if addr and addr not in e["addresses"]:
                e["addresses"].append(addr)
        note(e, host.get("source") or "an SDN controller's host table")
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
        # Its device is still the network's: one read now, or a switch a controller reports.
        kept = old.get("device") in reads or old.get("device") in switches
        if e is None:
            if kept:
                by_mac[mac] = dict(old)            # not seen in this read: kept, its age said
            continue
        if not e["device"] and kept:
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
            "source": "each device's MAC table, ARP and IPv6 neighbours, the DHCP leases, and "
                      "the hosts an SDN controller learned (the endpoint reader)",
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
