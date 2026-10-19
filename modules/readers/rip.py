"""What RIP and RIPng hear, read from the devices that run them (C662, the operator,
2026-10-11: "RIP/RIPng into Topology as a layer and as the second witness").

Nothing else reads RIP: Prometheus holds no RIP metric (measured on the host, 2026-10-11: of
963 metric names, none is RIP's), and RIP keeps no neighbour table the routing reader could
read (`modules/neighbours`). So this reader asks the devices themselves, and only the devices
whose committed intent configures RIP (`routing.rip`) or RIPng (`ipv6 rip <name> enable` on an
interface): two allowlisted show commands each, read-only, every device at once
(`fanout.read_each`):

- ``show ip protocols``: RIP's Routing Information Sources, the gateways it hears routes from
  (`pipeline._parse_rip_sources`, its own section, C65);
- ``show ipv6 rip next-hops``: RIPng's next hops, each with the interface it is heard on
  (`pipeline._parse_ripng_next_hops`; RIPng keeps no adjacency table, and a route learned is
  the wrong evidence, measured 2026-09-27).

A device that could not be read is said with its reason, never as hearing nothing. Topology
draws the answer as the RIP and RIPng layers, and a link a RIP adjacency runs over has its
second witness (`readers/topology_graph`).
"""

import logging
import time

from modules import reader_job

log = logging.getLogger(__name__)

NAME = "rip"
#: Five minutes: RIP's own update is 30 s and its invalid timer 180 s, so a neighbour lost is
#: seen within two reads; four devices in the lab, two show commands each.
INTERVAL_SECONDS = 300
#: What each read asks. `read_device` sends them as literals, which the device-effect scans
#: (tests/test_one_home_per_action.py) resolve; tests/test_rip_reader.py holds the two equal.
COMMANDS = {"rip": "show ip protocols", "ripng": "show ipv6 rip next-hops"}


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def runs(hv: dict) -> dict:
    """``{"rip": bool, "ripng": [interface]}``: what *hv*'s committed intent configures."""
    from modules.nsot.features import raw_view
    hv = raw_view(hv or {})            # a pack's fields read as their lines (K7)
    return {"rip": bool((hv.get("routing") or {}).get("rip")),
            "ripng": sorted(i.get("name", "") for i in hv.get("interfaces") or []
                            if any(" enable" in f" {x}" for x in i.get("ripng") or []))}


def _classful(address) -> int:
    """A RIP `network` statement's prefix length: the address's class (RIP's networks are
    classful: `network 172.16.0.0` is 172.16.0.0/16)."""
    first = int(str(address).split(".")[0])
    return 8 if first < 128 else 16 if first < 192 else 24


def rip_interfaces(hv: dict) -> list:
    """The interfaces RIP sends and listens on by *hv*'s committed intent: in the global table
    (no VRF), an IPv4 address inside a `network` statement's classful network, and not passive
    (`passive-interface default` with `no passive-interface X`, or `passive-interface X`)."""
    import ipaddress

    from modules.nsot.features import raw_view
    from modules.nsot.ifnames import same_interface

    hv = raw_view(hv or {})            # a pack's fields read as their lines (K7)
    rip = ((hv or {}).get("routing") or {}).get("rip")
    if not isinstance(rip, dict):
        return []
    nets = []
    for stmt in rip.get("networks") or []:
        words = stmt.split()
        try:
            addr = ipaddress.ip_address(words[-1])
            nets.append(ipaddress.ip_network(f"{addr}/{_classful(addr)}", strict=False))
        except (ValueError, IndexError):
            continue
    settings = [s.strip() for s in rip.get("settings") or []]
    default_passive = "passive-interface default" in settings
    passive = {s.split(None, 1)[1] for s in settings if s.startswith("passive-interface ")}
    active = {s.split(None, 2)[2] for s in settings if s.startswith("no passive-interface ")}
    out = []
    for iface in (hv or {}).get("interfaces") or []:
        name, v4 = iface.get("name", ""), (iface.get("ipv4") or "").split()
        if iface.get("vrf") or len(v4) != 2:
            continue
        try:
            ip = ipaddress.ip_address(v4[0])
        except ValueError:
            continue
        if not any(ip in n for n in nets):
            continue
        named = active if default_passive else passive
        if any(same_interface(name, p) for p in named) == default_passive:
            out.append(name)
    return out


def read_device(row: dict, wants: dict, connect=None) -> dict:
    """``{"rip": [sources] | None, "ripng": [hops] | None, "error": ""}`` for one device: one
    read-only session, the show commands its intent needs. Never raises."""
    from modules.connection import connection_params
    from modules.device import open_stored
    from modules.nsot import credential_rotation as cr
    from modules.pipeline import _parse_rip_sources, _parse_ripng_next_hops

    out = {"rip": None, "ripng": None, "error": ""}
    password, why = open_stored(row)
    if not password:
        out["error"] = why or "no stored credential"
        return out
    if not row.get("device_type"):
        out["error"] = "no device_type in the inventory; not guessed"
        return out
    try:
        if connect is None:
            from modules.connection import open_ssh

            def connect(**params):
                return open_ssh(params, owner="reader:rip")
        conn = connect(**connection_params(
            {"device_type": row["device_type"], "ip": row.get("ip", ""),
             "username": row.get("username", "admin")},
            password=password, secret=cr.enable_secret(row)))
        try:
            conn.enable()
            if wants["rip"]:
                sources = _parse_rip_sources(conn.send_command("show ip protocols"))
                out["rip"] = sources if sources is not None else []
                if sources is None:
                    out["error"] = "RIP is configured and `show ip protocols` names no RIP"
            if wants["ripng"]:
                out["ripng"] = _parse_ripng_next_hops(
                    conn.send_command("show ipv6 rip next-hops"))
        finally:
            conn.disconnect()
    except Exception as exc:                          # noqa: BLE001
        out["error"] = f"could not ask: {type(exc).__name__}: {exc}"
    return out


def population() -> list:
    """``[(list name, row, wants)]``: each device whose committed intent configures RIP or
    RIPng, with its inventory row."""
    from modules.device import load_saved_devices
    from modules.neighbours import committed_intents
    from modules.readers.adjacencies import lists

    out = []
    for name, ref, _hosts in lists():
        intents, err = committed_intents(ref.repo_dir)
        if err:
            log.warning("rip reader: %s's intent could not be read: %s", name, err)
            continue
        rows = {r.get("hostname"): r for r in load_saved_devices(ref.csv_path)}
        for host, hv in sorted(intents.items()):
            wants = runs(hv)
            if (wants["rip"] or wants["ripng"]) and host in rows:
                out.append((name, rows[host], wants))
    return out


def read(population_fn=None, read_fn=None, clock=time.time) -> dict:
    """``{"lists": {list: {device: {"rip", "ripng", "error", "read_at"}}}, "devices": n}``."""
    from modules.fanout import Failed, read_each

    items = (population_fn or population)()
    got = read_each(lambda it: (read_fn or read_device)(it[1], it[2]), items, name="rip")
    now = _iso(clock())
    out = {}
    for (name, row, _wants), res in zip(items, got):
        if isinstance(res, Failed):
            res = {"rip": None, "ripng": None, "error": f"the read raised {res}"}
        out.setdefault(name, {})[row.get("hostname", "?")] = dict(res, read_at=now)
    return {"lists": out, "devices": len(items)}


READER = reader_job.register(reader_job.Reader(
    name=NAME,
    what=("what RIP and RIPng hear, read from the devices whose intent configures them (two "
          "read-only show commands each), for Topology's RIP layers and second witness and "
          "the device page's Neighbours"),
    endpoints=("each RIP or RIPng device, over SSH: " + ", ".join(COMMANDS.values()),),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("RIP's update timer is 30 s and its invalid timer 180 s: a lost neighbour "
                    "is seen within two reads"),
    read=read,
    # Topology's RIP layers, and the device page's Neighbours tab (C12).
    invalidates=("topology", "adjacencies"),
    remedy="a device that cannot be read is named with its reason; fix its access",
    window="the moment each device was read",
))
