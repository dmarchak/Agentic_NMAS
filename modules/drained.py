"""drained.py

A device is DRAINED when no host traffic transits it, MEASURED, never set by hand (the
operator, 2026-10-06, reworking C550 into C551; the fastest measured form, from the interface
counters Prometheus already has; IP-MIB's forwarding counters replace it after the class).

**The measure:** every interface that is up (`ifOperStatus` 1), not a loopback, not in a VRF
(the management VRF), and not the device's MANAGEMENT PATH carries unicast below
`FLOOR_PPS` in AND out (`rate(...[2m])`) for `QUIET_SECONDS`. The management path is the
interface whose committed golden carries the device's management address: polling, SSH and
the routing protocols' unicast to the manager flow there whatever the drain. RIP and OSPF
hellos are multicast and not counted.

**Not judged, so never drained:** no Prometheus configured or readable, no golden, or no
interface in it carrying the management address (it may be on a loopback, so the path is not
known), or no interface left to judge. Absent is not drained.

**What it changes:** the Devices list and the device page draw a "Drained" badge with the
interfaces and their rates; Needs attention lists a Grafana alert on drained devices only
under What was checked instead of raising a row. It sends nothing to any device.

**Cost:** one golden `git grep` and four Prometheus queries for a whole network, kept for
`CACHE_SECONDS` per process, so a page drawing many devices asks once.
"""

import logging
import re
import threading
import time

log = logging.getLogger(__name__)

#: Unicast packets per second, in and out, below which an interface carries no host traffic
#: (the operator, 2026-10-06: "e.g. < 0.5 pkt/s"; RIP and OSPF hellos are multicast).
FLOOR_PPS = 0.5
#: How long every judged interface must stay under the floor (the operator: 3 minutes).
QUIET_SECONDS = 180
#: The rate window (the operator: 2 min, twice the 60 s SNMP scrape measured on the host).
RATE_WINDOW = "2m"
#: How far back "since" is looked for, at the scrape's step.
SINCE_LOOKBACK_SECONDS = 6 * 3600
SINCE_STEP_SECONDS = 60
#: The pages that draw the badge re-read on the reachability reader's 5 s announcement; the
#: measurement moves by the minute, so a network is asked at most this often.
CACHE_SECONDS = 30

_cache, _lock = {}, threading.Lock()
_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def _key(ifname: str) -> tuple:
    """GigabitEthernet3 and Gi3 alike: the first two letters and the number part."""
    m = re.match(r"^([A-Za-z-]+)\s*([0-9/.:]+)$", (ifname or "").strip())
    return (m.group(1)[:2].lower(), m.group(2)) if m else ((ifname or "").lower(), "")


def interfaces_from_goldens(repo_dir: str) -> dict:
    """``{device: {"interfaces": {name: {"address": [...], "vrf": bool, "shutdown": bool}}}}``
    from ONE `git grep` over the committed goldens."""
    from modules.nsot import repo as R

    rc, out, err = R.git(repo_dir, "grep", "-e", "^interface ", "-e", "^ ip address ",
                         "-e", "^ \\(ip \\)\\?vrf forwarding ",
                         "-e", "^ \\(ip \\|ipv6 \\)\\?ospf\\(v3\\)\\? .*area ",
                         "-e", "^ network [0-9.]* [0-9.]* area ", "HEAD", "--", "golden/")
    if rc not in (0, 1):
        raise RuntimeError((err or out or "git grep failed").strip())
    found, current, networks = {}, {}, {}
    for line in out.splitlines():
        try:
            _ref, path, text = line.split(":", 2)
        except ValueError:
            continue
        dev = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        ifs = found.setdefault(dev, {})
        if text.startswith("interface "):
            current[dev] = text.split(None, 1)[1].strip()
            ifs[current[dev]] = {"address": [], "vrf": False, "areas": set()}
        elif text.startswith(" network "):
            # `router ospf`'s network statements: an interface whose address they cover is in
            # that area (RIP's and BGP's network lines carry no "area").
            parts = text.split()
            networks.setdefault(dev, []).append((parts[1], parts[2], parts[4]))
        elif dev in current:
            parts = text.split()
            if "vrf forwarding" in text:
                ifs[current[dev]]["vrf"] = True
            elif "area" in parts:
                ifs[current[dev]]["areas"].add(parts[parts.index("area") + 1])
            elif len(parts) >= 3:
                ifs[current[dev]]["address"].append(parts[2])
    for dev, nets in networks.items():
        for i in found.get(dev, {}).values():
            for net, wildcard, area in nets:
                if any(_covers(net, wildcard, a) for a in i["address"]):
                    i["areas"].add(area)
    return found


def _covers(net: str, wildcard: str, address: str) -> bool:
    """Does OSPF's `network <net> <wildcard>` cover *address*?"""
    import ipaddress
    try:
        n, w, a = (int(ipaddress.IPv4Address(x)) for x in (net, wildcard, address))
    except ValueError:
        return False
    return (a & ~w) == (n & ~w)


def judge(devices: dict, golden_ifs: dict, series: dict) -> dict:
    """``{device: verdict}`` for each device in *devices* (``{name: management address}``).

    *series* is ``{"up": {(dev, ifName): 1}, "max_in": {...}, "max_out": {...}, "in": {...},
    "out": {...}}`` from Prometheus. A verdict is ``{"drained": bool, "judged": [...],
    "management": ifName, "why": str, "rates": {ifName: (in, out)}}``; "why" says why a
    device was not judged."""
    out = {}
    for dev, mgmt_ip in devices.items():
        ifs = golden_ifs.get(dev)
        if not ifs:
            out[dev] = {"drained": False, "why": "no committed golden to find its management path"}
            continue
        mgmt = [n for n, i in ifs.items() if mgmt_ip and mgmt_ip in i["address"]]
        if not mgmt:
            out[dev] = {"drained": False, "why": (
                f"no interface in its golden carries its management address {mgmt_ip}, so its "
                "management path is not known")}
            continue
        if _key(mgmt[0])[0] == "lo":
            # The management address on a loopback (the operator, 2026-10-06: every device
            # here): the path to the manager is every interface sharing the loopback's routing
            # domain toward the core, its OSPF/OSPFv3 area(s); every other interface is data.
            areas = ifs[mgmt[0]].get("areas") or set()
            path = [n for n, i in ifs.items() if n != mgmt[0] and _key(n)[0] != "lo"
                    and not i["vrf"] and areas & (i.get("areas") or set())]
            if not path:
                out[dev] = {"drained": False, "why": (
                    f"its management address is on {mgmt[0]}, which is in no OSPF area another "
                    "interface shares, so its management path is not known")}
                continue
            mgmt = path
        excluded = {_key(n) for n in mgmt} | {_key(n) for n, i in ifs.items() if i["vrf"]}
        judged, rates = [], {}
        for (d, ifname), state in series["up"].items():
            if d != dev or state != 1 or _key(ifname)[0] in ("lo", "nu") \
                    or _key(ifname) in excluded:
                continue
            judged.append(ifname)
            rates[ifname] = (series["in"].get((dev, ifname)), series["out"].get((dev, ifname)))
        if not judged:
            out[dev] = {"drained": False, "management": ", ".join(mgmt),
                        "why": "no up interface besides its management path to judge"}
            continue
        quiet = all(series["max_in"].get((dev, n)) is not None
                    and series["max_out"].get((dev, n)) is not None
                    and series["max_in"][(dev, n)] < FLOOR_PPS
                    and series["max_out"][(dev, n)] < FLOOR_PPS for n in judged)
        out[dev] = {"drained": quiet, "judged": sorted(judged), "management": ", ".join(mgmt),
                    "rates": rates, "why": ""}
    return out


#: The SNMP exporter's labels on the interface series, read on the host (the operator,
#: 2026-10-06): the polled address as `instance`, the interface as `ifDescr`.
ADDRESS_LABEL, INTERFACE_LABEL = "instance", "ifDescr"


def _alternatives(values) -> str:
    """A PromQL regex matching exactly *values*, its backslashes doubled for PromQL's string
    (a bare `\\.` is an invalid escape there)."""
    return "|".join(re.escape(v).replace("\\", "\\\\") for v in sorted(values))


def queries(addresses) -> dict:
    """The five instant queries for the devices at *addresses*, one text each, the same text
    the reads send (tests/test_drained.py parses them)."""
    sel = f'{{{ADDRESS_LABEL}=~"{_alternatives(addresses)}"}}'
    out = {"up": f"ifOperStatus{sel}"}
    for key, metric in (("in", "ifHCInUcastPkts"), ("out", "ifHCOutUcastPkts")):
        rate = f"rate({metric}{sel}[{RATE_WINDOW}])"
        out[key] = rate
        out["max_" + key] = f"max_over_time({rate}[{QUIET_SECONDS}s:30s])"
    return out


def since_query(metric: str, address: str, interfaces) -> str:
    return (f'rate({metric}{{{ADDRESS_LABEL}="{address}",'
            f'{INTERFACE_LABEL}=~"{_alternatives(interfaces)}"}}[{RATE_WINDOW}])')


def _by_interface(rows: list, by_address: dict) -> dict:
    """``{(device, interface): value}``, the device found by the series' polled address."""
    got = {}
    for row in rows or []:
        m = row.get("metric") or {}
        dev = by_address.get(m.get(ADDRESS_LABEL, ""))
        if not dev:
            continue
        try:
            got[(dev, m.get(INTERFACE_LABEL, ""))] = float((row.get("value") or [0, "nan"])[1])
        except (TypeError, ValueError):
            continue
    return got


def _query(prom, query: str, what: str) -> list:
    r = prom._get("api/v1/query", query=query)
    if not r.get("ok"):
        raise RuntimeError(f"Prometheus could not be asked for {what}: {r.get('error')}")
    return (r["response"].json().get("data") or {}).get("result") or []


def _since(prom, dev: str, address: str, judged: list, now: float) -> float:
    """When every judged interface last went under the floor: the sample after the newest
    one at or over it, in the lookback; None when none is in the lookback (quiet throughout)."""
    last_busy = None
    for metric in ("ifHCInUcastPkts", "ifHCOutUcastPkts"):
        r = prom._get("api/v1/query_range", query=since_query(metric, address, judged),
                      start=now - SINCE_LOOKBACK_SECONDS, end=now, step=SINCE_STEP_SECONDS)
        if not r.get("ok"):
            raise RuntimeError(f"Prometheus could not be asked for {dev}'s history: {r.get('error')}")
        for row in (r["response"].json().get("data") or {}).get("result") or []:
            for ts, val in row.get("values") or []:
                try:
                    if float(val) >= FLOOR_PPS and (last_busy is None or ts > last_busy):
                        last_busy = float(ts)
                except (TypeError, ValueError):
                    continue
    return None if last_busy is None else last_busy + SINCE_STEP_SECONDS


def _iso(ts) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""


def measure(list_name: str, now: float = None) -> dict:
    """``{device: verdict}`` for every device of *list_name*, read now (uncached)."""
    from modules.device import load_saved_devices
    from modules.integrations.prometheus import PrometheusIntegration
    from modules.nsot import listref

    now = now or time.time()
    if not list_name or not listref.exists(list_name):
        return {}
    ref = listref.resolve(list_name)
    devices = {d.get("hostname"): d.get("ip", "") for d in load_saved_devices(ref.csv_path)
               if d.get("hostname") and _NAME.match(d.get("hostname"))}
    if not devices:
        return {}
    prom = PrometheusIntegration(list_name=list_name)
    if not prom.is_configured():
        return {d: {"drained": False, "why": "Prometheus is not configured"} for d in devices}
    by_address = {ip: d for d, ip in devices.items() if ip}
    what = {"up": "interface states", "in": "rates in", "out": "rates out",
            "max_in": "peaks in", "max_out": "peaks out"}
    series = {k: _by_interface(_query(prom, q, what[k]), by_address)
              for k, q in queries(by_address).items()}
    verdicts = judge(devices, interfaces_from_goldens(ref.repo_dir), series)
    for dev, v in verdicts.items():
        if v["drained"]:
            v["since"] = _since(prom, dev, devices[dev], v["judged"], now)
            v["device"] = dev
            v["words"] = words(v)
    return verdicts


def current(list_name: str) -> dict:
    """``{device: verdict}`` for each device MEASURED drained now, cached `CACHE_SECONDS`.
    Raises when the measurement cannot be made (the caller says so; nothing is drained)."""
    now = time.time()
    with _lock:
        hit = _cache.get(list_name)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    got = {d: v for d, v in measure(list_name, now).items() if v.get("drained")}
    with _lock:
        _cache[list_name] = (now, got)
    return got


def state_of(list_name: str, device: str) -> dict:
    """The device's verdict if it is measured drained now, else None; a measurement that
    cannot be made is logged and drains nothing."""
    try:
        return current(list_name).get(device)
    except Exception as exc:                       # noqa: BLE001
        log.warning("drained: %s could not be measured: %s", list_name, exc)
        return None


def _rate(v) -> str:
    return "?" if v is None else f"{v:.1f}/s"


def words(v: dict) -> str:
    """"no host traffic on Gi3 since 21:58 UTC (in 0.0/s, out 0.0/s)"."""
    if v.get("words"):
        return v["words"]
    since = v.get("since")
    when = (f"since {time.strftime('%H:%M', time.gmtime(since))} UTC" if since else
            f"for at least {SINCE_LOOKBACK_SECONDS // 3600} h")
    parts = [f"{n} (in {_rate((v.get('rates') or {}).get(n, (None, None))[0])}, out "
             f"{_rate((v.get('rates') or {}).get(n, (None, None))[1])})"
             for n in v.get("judged") or []]
    return f"no host traffic on {', '.join(parts)} {when}; management path {v.get('management')} not counted"
