"""modules/readers/ztp_discovery.py — the discovery reader (board L, `ZtpDiscovery.dc.html`;
NSOT_STAGE7_PLAN 16): the devices asking for an address on the ZTP segment that the tool does not
know, read from Kea's leases in the discovery range (`modules/dhcp_discovery.py`).

Every 30 s (board L) it asks Kea for its IPv4 configuration (what the range is, as Kea RUNS it)
and its leases, and keeps, per MAC, what only a memory can: when it was first seen and the gaps
between its requests (each a change of the lease's last-transmission time). A device is
"asking" while its last request is under ten minutes old, "quiet" after that, and dropped
24 hours after its last request (board L). A MAC Kea now holds a reservation for, still on a
discovery lease, is "picked": reserved, and not taken yet. The pool its lease came from says its
vendor class (the ``ciscopnp`` pool first). Nothing here writes to Kea; a person picks.

Measured on the lab's Kea 2.4.1: each read answers in milliseconds (the DHCP reader's, 3 to
77 ms, 2026-10-11); a waiting C8000v asks every 3 to 7 s and never gives up (2026-10-05).
"""

import ipaddress
import logging
import time

from modules import reader_job

log = logging.getLogger(__name__)

READER_NAME = "ztp-discovery"
#: Board L: "every 30 s".
INTERVAL_SECONDS = 30
KEEPALIVE_SECONDS = 600
#: Board L: a device with no request for over ten minutes is "gone quiet", listed for 24 hours.
QUIET_S = 600
DROP_S = 86400
#: The gaps kept per device, for its cadence (the newest last).
GAPS = 20


def _iso(ts) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""


def _span(pool: str):
    from modules.dhcp_subnets import pool_span
    return pool_span(pool)


def _mac(value) -> str:
    return str(value or "").strip().lower().replace("-", ":")


def pending_macs(list_name: str) -> dict:
    """``{mac: (name, onboarded_at)}``: the network's onboardings not yet verified that carry a
    MAC (what a Pick makes), read from the committed manifest."""
    import os

    from modules.nsot import listref, manifest
    out = {}
    try:
        ref = listref.resolve(list_name)
        for row in manifest.pending_devices(os.path.join(ref.data_dir, "config_repo")):
            mac = _mac(row.get("mgmt_mac"))
            if mac:
                out[mac] = (row.get("name") or row.get("identity") or "", row.get("onboarded_at"))
    except Exception as exc:                                     # noqa: BLE001 (a read)
        log.warning("ztp-discovery: the pending onboardings could not be read: %s", exc)
    return out


def shape(config: dict, leases: list, previous: dict, now: float, pending: dict,
          addrs=None) -> dict:
    """The page's value from one read of Kea and the reader's memory (*previous*)."""
    from modules import dhcp_discovery as L
    from modules import dhcp_reservations as D

    rng = L.running(config, addrs)
    reserved = {}
    for r in D.every_reservation(config, "IPv4"):
        if r.get("key") == "hw-address":
            reserved[_mac(r.get("identity"))] = (r.get("addresses") or [""])[0]
    pools = []
    for p in rng["pools"]:
        try:
            pools.append((_span(p["pool"]), p["class"]))
        except ValueError:
            continue
    seen = {d["mac"]: d for d in (previous or {}).get("devices") or []}
    devices = {}
    for lease in leases:
        if lease.get("subnet-id") != rng["id"] or lease.get("state", 0) != 0:
            continue
        try:
            ip = ipaddress.ip_address(lease.get("ip-address", ""))
        except ValueError:
            continue
        cls = next((c for (a, b), c in pools if a <= ip <= b), None)
        if cls is None:
            continue
        mac = _mac(lease.get("hw-address"))
        cltt = lease.get("cltt") or 0
        was = seen.get(mac) or {}
        gaps = list(was.get("gaps") or [])
        last = was.get("last_asked_ts") or 0
        if last and cltt > last:
            gaps = (gaps + [cltt - last])[-GAPS:]
        devices[mac] = {
            "mac": mac, "address": str(ip),
            "vendor": L.VENDOR if cls == L.PNP else "",
            "client_id": lease.get("client-id", ""), "hostname": lease.get("hostname", ""),
            "first_seen_ts": min(x for x in (was.get("first_seen_ts"), cltt) if x),
            "last_asked_ts": max(cltt, last), "lease_s": lease.get("valid-lft"),
            "gaps": gaps}
    # What the memory holds and Kea no longer leases: quiet until a day after its last request.
    for mac, was in seen.items():
        if mac not in devices and now - (was.get("last_asked_ts") or 0) < DROP_S:
            devices[mac] = dict(was)
    out = []
    for mac, d in sorted(devices.items(), key=lambda kv: -(kv[1].get("last_asked_ts") or 0)):
        age = now - (d.get("last_asked_ts") or 0)
        d = dict(d, first_seen=_iso(d.get("first_seen_ts")), last_asked=_iso(d["last_asked_ts"]),
                 quiet_for_s=int(age))
        if mac in reserved:
            name, at = pending.get(mac, ("", None))
            d.update(state="picked", reserved=reserved[mac], picked_as=name, picked_at=at or "")
        elif mac in pending:
            d.update(state="picked", reserved="", picked_as=pending[mac][0],
                     picked_at=pending[mac][1] or "")
        else:
            d.update(state="asking" if age < QUIET_S else "quiet")
        out.append(d)
    return {"range": rng, "devices": out,
            "counts": {s: sum(1 for d in out if d["state"] == s)
                       for s in ("asking", "picked", "quiet")},
            "not_listed": {"reserved": len(reserved), "pending": len(pending)}}


def read(list_name: str = "", kea=None, clock=time.time, previous=None, addrs=None) -> dict:
    """One network's discovery range: the devices asking, picked and gone quiet."""
    from modules import dhcp_reservations as D
    from modules.list_settings import DEFAULT_LIST

    list_name = list_name or DEFAULT_LIST
    if kea is None:
        from modules.integrations.kea import KeaIntegration
        kea = KeaIntegration(list_name=list_name)
    if not kea.is_configured():
        return {"configured": False}
    if previous is None:
        got = reader_job.read_cached_for(READER_NAME, list_name)
        previous = ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}
    try:
        config = D.kea_config(kea, "IPv4")
        leases = D.kea_leases(kea, "IPv4")
    except D.Refused as exc:
        raise RuntimeError(f"Kea (dhcp4) could not be asked: {exc}") from None
    now = clock()
    value = shape(config, leases, previous, now, pending_macs(list_name), addrs)
    return dict(value, configured=True, read_at=_iso(now))


def changed(previous, value) -> bool:
    """Announce when a device or the range moved, never for the read's own time or the ages."""
    def strip(v):
        v = dict(v or {})
        v.pop("read_at", None)
        v["devices"] = [{k: x for k, x in d.items() if k != "quiet_for_s"}
                        for d in v.get("devices") or []]
        return v
    return strip(previous) != strip(value)


READER = reader_job.register(reader_job.Reader(
    name=READER_NAME,
    what="the devices asking for an address on the ZTP segment that the tool does not know, "
         "from Kea's leases in the discovery range, for Devices › Onboard devices › "
         "Discovered (board L)",
    endpoints=("Kea Control Agent: config-get and lease4-get-all to dhcp4",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("board L reads every 30 s; each read took 3 to 77 ms on the lab's Kea "
                    "2.4.1 (2026-10-11), and a waiting C8000v asks every 3 to 7 s"),
    read=read,
    invalidates=("ztp_discovery",),
    remedy="Read the error above: it names the read Kea did not answer",
    window="Kea's leases in the discovery range at the read, and the reader's memory of each "
           "device's first request and gaps for 24 hours after its last",
    per_group=("kea",),
    read_for=lambda list_name: read(list_name=list_name),
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
