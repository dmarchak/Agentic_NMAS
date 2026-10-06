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
                         "-e", "^ \\(ip \\)\\?vrf forwarding ", "HEAD", "--", "golden/")
    if rc not in (0, 1):
        raise RuntimeError((err or out or "git grep failed").strip())
    found, current = {}, {}
    for line in out.splitlines():
        try:
            _ref, path, text = line.split(":", 2)
        except ValueError:
            continue
        dev = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        ifs = found.setdefault(dev, {})
        if text.startswith("interface "):
            current[dev] = text.split(None, 1)[1].strip()
            ifs[current[dev]] = {"address": [], "vrf": False}
        elif dev in current:
            if "vrf forwarding" in text:
                ifs[current[dev]]["vrf"] = True
            else:
                parts = text.split()
                if len(parts) >= 3:
                    ifs[current[dev]]["address"].append(parts[2])
    return found


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
        if not mgmt or _key(mgmt[0])[0] in ("lo",):
            out[dev] = {"drained": False, "why": (
                f"no interface in its golden carries its management address {mgmt_ip}, so its "
                "management path is not known" if not mgmt else
                f"its management address is on {mgmt[0]}, so the path to the manager is not "
                "one interface")}
            continue
        excluded = {_key(mgmt[0])} | {_key(n) for n, i in ifs.items() if i["vrf"]}
        judged, rates = [], {}
        for (d, ifname), state in series["up"].items():
            if d != dev or state != 1 or _key(ifname)[0] in ("lo", "nu") \
                    or _key(ifname) in excluded:
                continue
            judged.append(ifname)
            rates[ifname] = (series["in"].get((dev, ifname)), series["out"].get((dev, ifname)))
        if not judged:
            out[dev] = {"drained": False, "management": mgmt[0],
                        "why": "no up interface besides its management path to judge"}
            continue
        quiet = all(series["max_in"].get((dev, n)) is not None
                    and series["max_out"].get((dev, n)) is not None
                    and series["max_in"][(dev, n)] < FLOOR_PPS
                    and series["max_out"][(dev, n)] < FLOOR_PPS for n in judged)
        out[dev] = {"drained": quiet, "judged": sorted(judged), "management": mgmt[0],
                    "rates": rates, "why": ""}
    return out


def _by_interface(rows: list) -> dict:
    got = {}
    for row in rows or []:
        m = row.get("metric") or {}
        try:
            got[(m.get("device", ""), m.get("ifName", ""))] = float((row.get("value") or [0, "nan"])[1])
        except (TypeError, ValueError):
            continue
    return got


def _query(prom, query: str, what: str) -> list:
    r = prom._get("api/v1/query", query=query)
    if not r.get("ok"):
        raise RuntimeError(f"Prometheus could not be asked for {what}: {r.get('error')}")
    return (r["response"].json().get("data") or {}).get("result") or []


def _since(prom, dev: str, judged: list, now: float) -> float:
    """When every judged interface last went under the floor: the sample after the newest
    one at or over it, in the lookback; None when none is in the lookback (quiet throughout)."""
    names = "|".join(re.escape(n) for n in judged)
    last_busy = None
    for metric in ("ifHCInUcastPkts", "ifHCOutUcastPkts"):
        r = prom._get("api/v1/query_range",
                      query=f'rate({metric}{{device="{dev}",ifName=~"{names}"}}[{RATE_WINDOW}])',
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
    sel = '{device=~"' + "|".join(re.escape(d) for d in sorted(devices)) + '"}'
    q = f"[{QUIET_SECONDS}s:30s]"
    series = {
        "up": _by_interface(_query(prom, f"ifOperStatus{sel}", "interface states")),
        "in": _by_interface(_query(prom, f"rate(ifHCInUcastPkts{sel}[{RATE_WINDOW}])", "rates in")),
        "out": _by_interface(_query(prom, f"rate(ifHCOutUcastPkts{sel}[{RATE_WINDOW}])",
                                    "rates out")),
        "max_in": _by_interface(_query(
            prom, f"max_over_time(rate(ifHCInUcastPkts{sel}[{RATE_WINDOW}]){q}", "peaks in")),
        "max_out": _by_interface(_query(
            prom, f"max_over_time(rate(ifHCOutUcastPkts{sel}[{RATE_WINDOW}]){q}", "peaks out")),
    }
    verdicts = judge(devices, interfaces_from_goldens(ref.repo_dir), series)
    for dev, v in verdicts.items():
        if v["drained"]:
            v["since"] = _since(prom, dev, v["judged"], now)
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
