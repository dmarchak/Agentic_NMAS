"""The endpoint reader (PHASE8_PLAN 15.15's endpoint layer, C1772): each device's MAC table, ARP
and IPv6 neighbours, read through its dialect's platform-pack entries
(`modules/nsot/platform_reads.json`), joined with the DHCP leases (`lease_sources`) into where
each endpoint is attached (`modules/endpoints.locate`).

Read-only, every device at once (`fanout.read_each`): a pack's command is sent only when the
read-only allowlist takes it whole (`readonly_commands.refusal`), so an entry can never be a
write; a dialect with no entry is said as not supported. A device that could not be read is
said with its reason, never as having no endpoints. Each network's value keeps every
endpoint's last location and when it was seen, carried from the previous read (`locate`'s
*previous*), since a switch forgets an idle host's MAC within minutes.
"""

import logging
import time

from modules import reader_job

log = logging.getLogger(__name__)

NAME = "endpoints"
#: How often the reader looks: five minutes, the shortest a network may choose. Each network
#: is read only when its own interval (`endpoint_read_interval_minutes`, 15 by default; the
#: operator's ruling of 2026-10-26) has passed since its last read; between reads its value is
#: kept as read, so a host's last location and its age carry.
INTERVAL_SECONDS = 300
INTERVAL_SETTING, INTERVAL_DEFAULT_MINUTES = "endpoint_read_interval_minutes", 15


def interval_minutes(network: str) -> int:
    """The network's `endpoint_read_interval_minutes`; the default when it cannot be read,
    logged (the reader keeps reading at the schedule it had)."""
    from modules import list_settings
    try:
        return int(list_settings.value(network, INTERVAL_SETTING, INTERVAL_DEFAULT_MINUTES))
    except Exception as exc:                            # noqa: BLE001 (the default, logged)
        log.warning("endpoints: %s's %s could not be read (%s); %s min is used", network,
                    INTERVAL_SETTING, exc, INTERVAL_DEFAULT_MINUTES)
        return INTERVAL_DEFAULT_MINUTES


def due(last_read_at: str, minutes: int, now: float) -> bool:
    """Whether a network last read at *last_read_at* is due at *now*: never read, or its
    interval passed, less half a look (so a 15-minute interval is not stretched to 20 by the
    looks' phase)."""
    from modules import endpoints as E
    if not last_read_at:
        return True
    return now - E._epoch(last_read_at) >= minutes * 60 - INTERVAL_SECONDS / 2


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def read_device(row: dict, dialect: str, connect=None) -> dict:
    """``{read: rows, "error": "", "not_supported": [read]}`` for one device: one read-only
    session, its dialect's pack commands, each parsed by the pack's pattern. Never raises."""
    from modules import endpoints as E
    from modules import readonly_commands as rc
    from modules.connection import connection_params
    from modules.device import open_stored
    from modules.nsot import credential_rotation as cr

    out = {"error": "", "not_supported": []}
    plan = []
    for read in E.READS:
        e = E.entry(dialect, read)
        if not e:
            out["not_supported"].append(read)
            continue
        why = rc.refusal(e["command"])
        if why:
            out["not_supported"].append(read)
            out["error"] = f"the pack's {read} command is not a read Mercury may send: {why}"
            continue
        plan.append((read, e["command"]))
    if not plan:
        return out
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
                return open_ssh(params, owner="reader:endpoints")
        conn = connect(**connection_params(
            {"device_type": row["device_type"], "ip": row.get("ip", ""),
             "username": row.get("username", "admin")},
            password=password, secret=cr.enable_secret(row)))
        try:
            conn.enable()
            for read, command in plan:
                out[read] = E.parse(dialect, read, conn.send_command(command))
        finally:
            conn.disconnect()
    except Exception as exc:                          # noqa: BLE001
        out["error"] = f"could not ask: {type(exc).__name__}: {exc}"
    return out


def ports(network: str, hosts: list, intents: dict) -> dict:
    """``{host: {"trunks", "uplinks"}}``: the ports that locate nothing, from committed intent
    (trunks) and the network's neighbours (a port with a managed neighbour is an uplink)."""
    from modules.ai import intent_names
    out = {}
    for host in hosts:
        ifaces = intent_names.interfaces_of(intents.get(host) or {})
        nb = intent_names.neighbours_of(network, host)
        out[host] = {"trunks": {i["name"] for i in ifaces if i["mode"] == "trunk"},
                     "uplinks": {p for p, peers in (nb.get("ports") or {}).items() if peers}}
    return out


def population() -> list:
    """``[(network, row, dialect)]``: every device whose dialect's pack has a read entry."""
    from modules import endpoints as E
    from modules.device import load_saved_devices
    from modules.nsot.platform import platform_for_device
    from modules.readers.adjacencies import lists

    packs = E.entries()
    out = []
    for name, ref, _hosts in lists():
        for row in load_saved_devices(ref.csv_path):
            dialect = platform_for_device(row)
            if dialect in packs:
                out.append((name, row, dialect))
    return out


def read(population_fn=None, read_fn=None, clock=time.time, previous_fn=None,
         leases_fn=None, ports_fn=None, stored_fn=None, interval_fn=None) -> dict:
    """``{"lists": {network: {"endpoints", "read_at", "version", "ignored", "devices",
    "leases_said"}}, "devices": n, "not_due": {network: minutes}}``: the networks due (their
    interval passed since their last read) read now; every other network's last value kept
    as it was read, its devices not asked."""
    from modules import endpoints as E
    from modules import lease_sources
    from modules.fanout import Failed, read_each
    from modules.neighbours import committed_intents
    from modules.readers.adjacencies import lists

    everyone = (population_fn or population)()
    start = clock()
    last = {n: (stored_fn or E.stored)(n) for n in sorted({it[0] for it in everyone})}
    minutes = {n: (interval_fn or interval_minutes)(n) for n in last}
    kept = {n: {k: v for k, v in got.items() if k not in ("state", "why")}
            for n, got in last.items()
            if got.get("state") == "read" and not due(got.get("read_at", ""), minutes[n], start)}
    items = [it for it in everyone if it[0] not in kept]
    got = read_each(lambda it: (read_fn or read_device)(it[1], it[2]), items, name=NAME)
    now = clock()
    per = {}
    for (network, row, _dialect), res in zip(items, got):
        if isinstance(res, Failed):
            res = {"error": f"the read raised {res}", "not_supported": []}
        per.setdefault(network, {})[row.get("hostname", "?")] = res
    repos = {name: ref.repo_dir for name, ref, _h in lists()} if not ports_fn else {}
    out = {}
    for network, reads in per.items():
        if ports_fn:
            skip = ports_fn(network, list(reads))
        else:
            intents, _err = committed_intents(repos.get(network, ""))
            skip = ports(network, list(reads), intents or {})
        prev = (previous_fn or (lambda n: last[n].get("endpoints") or []))(network)
        lease = (leases_fn or lease_sources.leases)(network)
        located = E.locate(reads, lease["leases"], skip, previous=prev, now=now)
        out[network] = dict(located, leases_said=lease["said"], devices={
            h: {"error": r.get("error", ""), "not_supported": r.get("not_supported", []),
                "read": {k: len(r.get(k) or []) for k in E.READS if k in r},
                "read_at": _iso(now)} for h, r in sorted(reads.items())})
    out.update(kept)
    return {"lists": out, "devices": len(items), "not_due": {n: minutes[n] for n in kept}}


READER = reader_job.register(reader_job.Reader(
    name=NAME,
    what=("where each endpoint is attached: every device's MAC table, ARP and IPv6 neighbours "
          "(its platform pack's read-only commands), joined with the DHCP leases, a trunk's or "
          "uplink's MAC locating nothing; each endpoint's last location kept with when"),
    endpoints=("each device, over SSH: its dialect's pack commands "
               "(modules/nsot/platform_reads.json), read-only",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("a look every 5 minutes, the shortest interval a network may choose; each "
                    "network read at its own endpoint_read_interval_minutes (15 by default), "
                    "a host's last location kept between reads"),
    read=read,
    # Endpoints are the topology class; no screen draws them yet, so Topology hears the read.
    invalidates=("topology",),
    remedy="a device that cannot be read is named with its reason; fix its access",
    window="the moment each device was read",
))
