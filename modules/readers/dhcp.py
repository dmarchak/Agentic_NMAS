"""modules/readers/dhcp.py — the DHCP reader (C529 step 1; board A, "Item 5, DHCP on v2",
approved 2026-10-06): one network's Kea, read through its Control Agent, for the DHCP page.

Everything the page draws comes from here, never a Kea call per page view (board A). Per family
(IPv4 from ``dhcp4``, IPv6 from ``dhcp6``), three reads: ``version-get``, ``config-get`` (the
subnets, those in a shared network too, their pools, lease times, the reservations in each and
at the global level, and which of them Kea uses where, as Kea RUNS them) and ``lease4-get-all`` /
``lease6-get-all`` (every lease). Each family is read on its own: one that cannot be asked keeps
its last good value, named with its error and its age, and never blanks the other (board A).
Both families are always asked: whether Kea serves one is Kea's answer ("not served"), not a
setting's (the lab's ``kea_services`` said dhcp4 while Kea served both, measured 2026-10-11).

Measured on the lab's Kea 2.4.1 (2026-10-11): each read answers in 3 to 77 ms; ``config-get``
gives every subnet its lease times, the global ones filled in where the file sets none, so the
page can say a subnet's time is the same as the global one and never that it is inherited.
"""

import logging
import time

from modules import reader_job

log = logging.getLogger(__name__)

READER_NAME = "dhcp"
#: Board A: "it reads again every 5 minutes and after every reservation change".
INTERVAL_SECONDS = 300
KEEPALIVE_SECONDS = 1800
FAMILIES = (("dhcp4", "Dhcp4", "subnet4", "lease4-get-all", "IPv4"),
            ("dhcp6", "Dhcp6", "subnet6", "lease6-get-all", "IPv6"))
TIMES = (("valid", "valid-lifetime"), ("preferred", "preferred-lifetime"),
         ("renew", "renew-timer"), ("rebind", "rebind-timer"))
#: Kea's lease states (lease_cmds): 0 default (active), 1 declined, 2 expired-reclaimed.
LEASE_STATES = {0: "active", 1: "declined", 2: "expired-reclaimed"}


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _arguments(result) -> dict:
    """A Control Agent answer's arguments: it answers a list, one entry per service asked."""
    entry = result[0] if isinstance(result, list) and result else result
    return (entry or {}).get("arguments") or {}


#: How Kea keys a client, first to last: an IPv4 lease by its MAC, an IPv6 lease by its DUID
#: (an IPv6 lease carries the MAC too, measured; the DUID is what it is held by).
IDENTITY_ORDER = {"IPv4": (("hw-address", "MAC"), ("client-id", "client-id"),
                           ("duid", "DUID"), ("circuit-id", "circuit-id"),
                           ("flex-id", "flex-id")),
                  "IPv6": (("duid", "DUID"), ("hw-address", "MAC"),
                           ("flex-id", "flex-id"))}


def _identity(entry: dict, family: str = "IPv4") -> tuple:
    """``(kind, value)``: how a reservation or lease names its client, the way Kea keys it."""
    for key, kind in IDENTITY_ORDER[family]:
        if entry.get(key):
            return kind, entry[key]
    return "", ""


def _hostname(value) -> str:
    """Kea writes "." for a client that sent an empty name (DHCPv6, measured)."""
    value = (value or "").strip()
    return "" if value in (".", "") else value.rstrip(".")


def reservations(entries, family: str) -> list:
    """Reservations as Kea's configuration holds them, each keyed the way Kea keys its client."""
    out = []
    for r in entries or []:
        kind, ident = _identity(r, family)
        addresses = ([r["ip-address"]] if r.get("ip-address") else []) + \
            list(r.get("ip-addresses") or [])
        out.append({"hostname": _hostname(r.get("hostname")), "by": kind,
                    "identity": ident, "addresses": addresses,
                    "prefixes": list(r.get("prefixes") or [])})
    return out


#: Whether Kea uses a subnet's own reservations and the global ones there: a subnet's own
#: setting, else its shared network's, else the global one (Kea's inheritance; config-get gives
#: the global value always and a subnet's only where its file sets one, measured 2026-10-11).
USES = (("in_subnet", "reservations-in-subnet", True), ("global", "reservations-global", False))


def subnets(config: dict, family: str, sub_key: str, ztp_ids=()) -> list:
    """Each subnet as Kea runs it, those inside a shared network too: id, prefix, pools, its
    lease times and the global ones, its reservations, and which reservations Kea uses there."""
    glob = {name: config.get(key) for name, key in TIMES}
    every = [(s, {}) for s in config.get(sub_key) or []]
    for net in config.get("shared-networks") or []:
        every += [(s, net) for s in net.get(sub_key) or []]
    out = []
    for s, net in every:
        uses = {name: bool(s.get(key, net.get(key, config.get(key, default))))
                for name, key, default in USES}
        out.append({"id": s.get("id"), "prefix": s.get("subnet", ""),
                    "shared_network": net.get("name", ""),
                    "pools": [p.get("pool", "") for p in s.get("pools") or []],
                    "pd_pools": [f"{p.get('prefix')}/{p.get('prefix-len')} by "
                                 f"/{p.get('delegated-len')}" for p in s.get("pd-pools") or []],
                    "times": {name: s.get(key) for name, key in TIMES},
                    "global_times": glob, "reservations": reservations(s.get("reservations"),
                                                                       family),
                    "uses": uses, "ztp": s.get("id") in ztp_ids, "family": family})
    return out


def held_elsewhere(config: dict) -> list:
    """Where Kea keeps reservations its configuration does not list: a hosts database, named by
    its type only (its entry also holds a user and a password, never taken)."""
    dbs = list(config.get("hosts-databases") or [])
    if config.get("hosts-database"):
        dbs.append(config["hosts-database"])
    return [f"a hosts database ({d.get('type') or 'of no stated type'})" for d in dbs]


def leases(raw: list, family: str) -> list:
    """Every lease Kea holds, with when it ends (its last transmission plus its lifetime)."""
    out = []
    for l in raw or []:
        kind, ident = _identity(l, family)
        cltt, valid = l.get("cltt"), l.get("valid-lft")
        ends = _iso(cltt + valid) if isinstance(cltt, int) and isinstance(valid, int) else ""
        out.append({"address": l.get("ip-address", ""), "subnet_id": l.get("subnet-id"),
                    "by": kind, "identity": ident, "mac": l.get("hw-address", ""),
                    "hostname": _hostname(l.get("hostname")), "valid": valid,
                    "ends": ends, "state": LEASE_STATES.get(l.get("state"), str(l.get("state"))),
                    "type": l.get("type", ""), "family": family,
                    "prefix_len": l.get("prefix-len")})
    return sorted(out, key=lambda x: (x["subnet_id"] or 0, x["address"]))


def _ztp_ids(dhcp4: dict) -> list:
    """ZTP's subnets, by ZTP's own rule (`ztp.ztp_subnets`: a subnet holding one of this
    host's addresses on an interface Kea listens on). A failure to measure names none."""
    from modules.nsot import ztp
    try:
        return [s.get("id") for s, _a in ztp.ztp_subnets(dhcp4)]
    except Exception as exc:                                  # noqa: BLE001 (a measurement)
        log.warning("dhcp: ZTP's subnets could not be measured: %s", exc)
        return []


def read_family(kea, svc: str, root: str, sub_key: str, lease_cmd: str, words: str,
                clock=time.time, ztp_ids=None) -> dict:
    """One family's three reads. Raises naming the read that failed."""
    got = {}
    for cmd in ("version-get", "config-get", lease_cmd):
        r = kea.command(cmd, svc)
        if not r.get("ok"):
            raise RuntimeError(f"Kea's {svc} could not be asked ({cmd}): {r.get('error')}")
        got[cmd] = _arguments(r.get("result"))
    config = got["config-get"].get(root) or {}
    version = ((got["version-get"].get("extended") or "").splitlines() or [""])[0]
    ids = ztp_ids if ztp_ids is not None else (_ztp_ids(config) if svc == "dhcp4" else [])
    return {"ok": True, "words": words, "version": version.strip(),
            "subnets": subnets(config, words, sub_key, ids),
            "global_reservations": reservations(config.get("reservations"), words),
            "reservations_elsewhere": held_elsewhere(config),
            "leases": leases(got[lease_cmd].get("leases"), words),
            "read_at": _iso(clock()), "error": ""}


def read(list_name: str = "", kea=None, clock=time.time, previous=None, ztp_ids=None) -> dict:
    """One network's Kea, both families, each on its own (see the module)."""
    if kea is None:
        from modules.integrations.kea import KeaIntegration
        kea = KeaIntegration(list_name=list_name) if list_name else KeaIntegration()
    if not kea.is_configured():
        return {"configured": False}
    if previous is None:
        got = reader_job.read_cached_for(READER_NAME, list_name or _default())
        previous = ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}
    families, errors = {}, []
    for svc, root, sub_key, lease_cmd, words in FAMILIES:
        try:
            families[svc] = read_family(kea, svc, root, sub_key, lease_cmd, words, clock,
                                        ztp_ids)
        except RuntimeError as exc:
            errors.append(str(exc))
            # The last good read of this family, kept and named with its error (board A:
            # never blanked by the other family, never drawn as current).
            last = dict((previous.get("families") or {}).get(svc) or {}, ok=False,
                        error=str(exc), words=words)
            last.setdefault("subnets", None)
            last.setdefault("leases", None)
            families[svc] = last
    if len(errors) == len(FAMILIES):
        raise RuntimeError("; ".join(errors))
    return {"configured": True, "families": families, "read_at": _iso(clock())}


def _default() -> str:
    from modules.list_settings import DEFAULT_LIST
    return DEFAULT_LIST


def changed(previous, value) -> bool:
    """Announce when Kea's answer moved, never for the read's own time."""
    def strip(v):
        v = dict(v or {})
        v.pop("read_at", None)
        v["families"] = {k: {kk: x for kk, x in (f or {}).items() if kk != "read_at"}
                         for k, f in (v.get("families") or {}).items()}
        return v
    return strip(previous) != strip(value)


READER = reader_job.register(reader_job.Reader(
    name=READER_NAME,
    what="the network's Kea: subnets, pools, lease times, reservations and every lease, per "
         "family, for the DHCP page (C529)",
    endpoints=("Kea Control Agent: version-get, config-get and lease4-get-all to dhcp4",
               "Kea Control Agent: version-get, config-get and lease6-get-all to dhcp6"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("each read took 3 to 77 ms on the lab's Kea 2.4.1 (2026-10-11); board A "
                    "reads every five minutes and after every reservation change"),
    read=read,
    invalidates=("dhcp",),
    remedy="Read the error above: it names the family and the read Kea did not answer",
    window="Kea's running configuration and its lease database as they are at the read",
    per_group=("kea",),
    read_for=lambda list_name: read(list_name=list_name),
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
