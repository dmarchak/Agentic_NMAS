"""modules/dhcp_page.py — SOURCE OF TRUTH › DHCP: one network's Kea (C529 step 1; board A,
"Item 5, DHCP on v2", `DhcpNetwork.dc.html`, approved 2026-10-06 with boards B to D; compared
region by region in docs/fidelity/dhcp.md).

Everything here is the DHCP reader's stored value (modules/readers/dhcp.py): never a Kea call
per page view. Four tabs: Subnets (as Kea runs them), Leases (grouped by subnet, each group
collapsed until opened, with search and the board's filters), Reservations (each with what it
does now), Exclusions (what Kea cannot do and when Mercury's arrive). Changing a reservation is
board B (C529 step 2); subnets, options and exclusions are boards C and D (step 3).

What is said, never implied: a family Kea did not answer keeps its last good read, drawn with
its error and its age; an unknown family is "not read", never empty; "As the host holds it" is
"not readable" for a host Mercury does not reach, never blank (board A).
"""

import ipaddress
import logging
import time
from urllib.parse import urlencode

log = logging.getLogger(__name__)

READER = "dhcp"
TABS = {"sub": "Subnets", "lea": "Leases", "res": "Reservations", "exc": "Exclusions"}
#: Board A's lease filters.
SHOWS = {"all": "Every lease", "shared": "Sharing an identity",
         "not_inv": "Not in the inventory", "expiring": "Expiring within a day"}
ASKS = {"tab": "sub", "show": "all", "q": "", "open": ""}
#: The one write path's steps for a reservation, a subnet or an exclusion
#: (`dhcp_reservations.apply`, `dhcp_subnets.apply_edit`, each noting the step it reached as
#: ``at``): THE stepper's (the one stepper, 2026-10-12).
WRITE_STEPS = (("test", "Kea's own check"), ("write", "Mercury's file written"),
               ("reload", "Kea reloaded"), ("read_back", "Read back"), ("record", "Recorded"))


def write_run(got: dict):
    """A DHCP write's result on THE stepper: the steps before the one it reached done, that one
    done (the change landed) or failed with its error and what the rollback did, the rest not
    reached. None for a refusal before Kea's own check (nothing ran: the card says why)."""
    from modules import run_stepper as RS

    at = (got or {}).get("at")
    if at not in dict(WRITE_STEPS):
        return None
    reached = [k for k, _w in WRITE_STEPS].index(at)
    steps = []
    for i, (k, w) in enumerate(WRITE_STEPS):
        if i < reached or got.get("ok"):
            steps.append(RS.step(k, w, "done"))
        elif i == reached:
            why = got.get("error") or "no reason recorded"
            if got.get("rolled_back"):
                why += f"; then {got['rolled_back']}"
            steps.append(RS.step(k, w, "failed", note=why))
        else:
            steps.append(RS.step(k, w, "not_reached"))
    return RS.card([RS.row("Kea", "done" if got.get("ok") else "failed", steps, device=False)],
                   label="DHCP write", key="dhcp-write")


def write_said(got: dict) -> str:
    """A failed DHCP write's first words, from the step it reached (C723): "Nothing was
    changed" only while that is true. A record that failed comes after Kea holds the change,
    and a read-back that could not be read leaves it written (nothing was rolled back)."""
    got = got or {}
    at, back = got.get("at"), got.get("rolled_back")
    if at == "record":
        return "Written to Kea and read back, and not recorded."
    if at == "read_back" and not back:
        return "Written and Kea reloaded; what Kea runs now could not be read back."
    return "Nothing was changed" + (f" in the end: {back}" if back else "") + "."


def ask(values) -> dict:
    s = {k: (values.get(k) or "").strip() or v for k, v in ASKS.items()}
    s["tab"] = s["tab"] if s["tab"] in TABS else "sub"
    s["show"] = s["show"] if s["show"] in SHOWS else "all"
    return s


def qs(list_name: str, s: dict, over: dict = None) -> str:
    merged = dict(s, **(over or {}))
    pairs = [("list", list_name)] + [(k, merged[k]) for k, v in ASKS.items()
                                     if merged.get(k) and merged[k] != v]
    return "?" + urlencode(pairs)


def stored(list_name: str, reader: str = READER) -> dict:
    """A Kea reader's stored value for the network, in the states its page draws (this page's
    reader, or the discovery reader's for Onboard devices › Discovered)."""
    from modules import reader_job

    got = reader_job.read_cached_for(reader, list_name)
    state = got.get("state")
    if state in ("not_applicable", "not_configured", "unreadable"):
        return {"state": state, "why": got.get("why") or "the reader's store could not be read"}
    doc = got.get("doc") or {}
    last = doc.get("last_good") or {}
    attempt = doc.get("last_attempt") or {}
    failed = "" if attempt.get("ok", True) else (attempt.get("error") or "the last read failed")
    if not last:
        return {"state": "never", "failed": failed}
    value = last.get("value") or {}
    if not value.get("configured"):
        return {"state": "not_configured", "why": "Kea is not configured for this network"}
    return {"state": "ok", "value": value, "value_at": last.get("value_at", ""),
            "failed": failed}


def _devices(list_name: str) -> set:
    """The network's device names: the inventory, read with no I/O to a device."""
    from modules.readers.adjacencies import lists
    for name, _ref, hosts in lists():
        if name == list_name:
            return set(hosts)
    return set()


def duration(seconds) -> str:
    """Board A's lease times: "365 d", "182.5 d", "5 min"; "–" when Kea has none."""
    if seconds in (None, ""):
        return "–"
    seconds = int(seconds)
    for unit, size in (("d", 86400), ("h", 3600), ("min", 60)):
        if seconds >= size:
            n = seconds / size
            return f"{n:.1f}".rstrip("0").rstrip(".") + f" {unit}"
    return f"{seconds} s"


def pool_words(pool: str) -> str:
    """"10.10.10.100-10.10.10.200" as board A writes it, "10.10.10.100 – 10.10.10.200"."""
    return " – ".join(p.strip() for p in pool.split("-", 1)) if "-" in pool else pool


def pool_size(pools: list) -> int:
    total = 0
    for pool in pools:
        try:
            if "-" in pool:
                a, b = (ipaddress.ip_address(p.strip()) for p in pool.split("-", 1))
                total += int(b) - int(a) + 1
            else:
                total += ipaddress.ip_network(pool.strip(), strict=False).num_addresses
        except ValueError:
            continue
    return total


def class_who(name: str) -> str:
    """Which clients a lifetime class serves, in words (E19's reserved class, board L's
    discovery classes); another class says its test is Kea's."""
    from modules import dhcp_lifetimes
    from modules.dhcp_discovery import CLASS_WORDS
    if name == dhcp_lifetimes.RESERVED:
        return "every client with a reservation, in every subnet"
    return CLASS_WORDS.get(name, "the clients its test in Kea's configuration matches")


def tee_words(sub: dict) -> str:
    """Renew and rebind as the page draws them: Kea's fixed timers, or the shares it computes
    from each lease's own lifetime (E19)."""
    t = sub.get("tee") or {}
    times = sub.get("times") or {}
    if t.get("computed") and times.get("renew") is None and times.get("rebind") is None:
        return (f"renew at {round((t.get('t1') or 0) * 100)}% · rebind at "
                f"{round((t.get('t2') or 0) * 100)}% of each lease")
    return f"{duration(times.get('renew'))} · {duration(times.get('rebind'))}"


def _families(value: dict) -> list:
    return [(svc, f) for svc, f in (value.get("families") or {}).items()]


def _owner(list_name: str) -> dict:
    """Whose Kea the page's network uses (C1181: one owning network per Kea, the one where it
    is set): ``{"owner", "owner_why", "writable"}``. Only the owner's page changes Kea; an
    unreadable settings store writes nothing and says why."""
    from modules import list_settings

    try:
        owner, why = list_settings.kea_owner(list_name)
    except Exception as exc:                          # noqa: BLE001 (said on the page)
        return {"owner": "", "owner_why": f"whose Kea it is could not be read ({exc})",
                "writable": False}
    return {"owner": owner, "owner_why": why,
            "writable": list_settings.same_network(owner, list_name)}


def view(list_name: str, values, now: float = None) -> dict:
    """Everything the DHCP page draws for one network and question."""
    s = ask(values)
    now = time.time() if now is None else now
    out = {"list": list_name, "s": s, "qs": lambda over=None: qs(list_name, s, over),
           "tabs": TABS, "shows": SHOWS, "duration": duration, "pool_words": pool_words,
           "held_words": HELD, "tee_words": tee_words}
    out.update(_owner(list_name))
    st = stored(list_name)
    out.update(state=st["state"], why=st.get("why", ""), failed=st.get("failed", ""),
               value_at=st.get("value_at", ""))
    if st["state"] != "ok":
        return out
    mine = _devices(list_name)
    families, subnets, leases, globals_ = [], [], [], []
    for svc, f in _families(st["value"]):
        families.append({"svc": svc, "words": f.get("words", svc), "ok": f.get("ok", False),
                         "error": f.get("error", ""), "read_at": f.get("read_at", ""),
                         "version": f.get("version", ""),
                         "known": f.get("subnets") is not None,
                         "elsewhere": f.get("reservations_elsewhere") or [],
                         "lifetime_classes": [dict(c, who=class_who(c["name"]),
                                                   family=f.get("words", svc))
                                              for c in f.get("lifetime_classes") or []]})
        for sub in f.get("subnets") or []:
            subnets.append(dict(sub, svc=svc))
        for lease in f.get("leases") or []:
            leases.append(dict(lease, svc=svc))
        if f.get("global_reservations"):
            # Kea's global level, drawn as its own group: used in each subnet that turns
            # reservations-global on, and nowhere else.
            globals_.append({"svc": svc, "id": None, "prefix": "", "global": True, "ztp": False,
                             "family": f.get("words", svc),
                             "reservations": f["global_reservations"]})
    by_subnet = {(x["svc"], x["id"]): x for x in subnets}
    reserved = {}
    for sub in globals_ + subnets:
        for r in sub["reservations"]:
            for a in r["addresses"]:
                reserved[(sub["svc"], a)] = r
    active = [l for l in leases if l["state"] == "active"]
    # An identity holding more than one lease in a subnet (board A: "3 share one DUID").
    holding = {}
    for l in active:
        holding.setdefault((l["svc"], l["subnet_id"], l["identity"]), []).append(l)
    shared = {k: v for k, v in holding.items() if len(v) > 1 and k[2]}
    day = 86400
    rows = []
    for l in leases:
        r = reserved.get((l["svc"], l["address"]))
        hostname = l["hostname"]
        device = hostname if hostname in mine else ""
        ends_ts = _ts(l["ends"])
        rows.append(dict(
            l, reserved=bool(r) and r["identity"].lower() == (l["identity"] or "").lower(),
            reserved_for_other=bool(r) and r["identity"].lower() != (l["identity"] or "").lower(),
            device=device,
            holds=("pending" if device else "not_readable"),
            shared=(l["svc"], l["subnet_id"], l["identity"]) in shared,
            expiring=bool(ends_ts) and ends_ts - now < day and l["state"] == "active",
            from_pool_beside_reservation=_beside_reservation(l, by_subnet, globals_)))
    needle = s["q"].lower()

    def keep(l):
        if s["show"] == "shared" and not l["shared"]:
            return False
        if s["show"] == "not_inv" and l["device"]:
            return False
        if s["show"] == "expiring" and not l["expiring"]:
            return False
        text = " ".join(str(l.get(k) or "") for k in ("address", "identity", "mac", "hostname"))
        return not needle or needle in text.lower()

    groups = []
    for sub in subnets:
        mine_rows = [r for r in rows if r["svc"] == sub["svc"] and r["subnet_id"] == sub["id"]]
        shown = _together([r for r in mine_rows if keep(r)])
        flags = []
        n_shared = sum(1 for r in mine_rows if r["shared"])
        if n_shared:
            kinds = sorted({r["by"] for r in mine_rows if r["shared"]})
            flags.append(f"{n_shared} share one {' or '.join(kinds)}")
        n_beside = sum(1 for r in mine_rows if r["from_pool_beside_reservation"])
        if n_beside:
            flags.append(f"{n_beside} from the pool where a reservation exists")
        groups.append({"sub": sub, "rows": shown, "total": len(mine_rows), "flags": flags,
                       "open": bool(flags) or bool(needle) or s["show"] != "all"
                       or s["open"] == f"{sub['svc']}:{sub['id']}"})
    res_rows = []
    for sub in globals_ + subnets:
        for r in sub["reservations"]:
            res_rows.append(dict(r, sub=sub, now=_reservation_now(r, sub, active, subnets)))
    sub_rows = []
    intent = st["value"].get("intent") or {}
    held = {svc: f.get("held") for svc, f in _families(st["value"])}
    for sub in subnets:
        used = sum(1 for l in active if l["svc"] == sub["svc"] and l["subnet_id"] == sub["id"])
        same = all(sub["times"].get(k) == sub["global_times"].get(k) for k in sub["times"])
        sub_rows.append(dict(sub, used=used, size=pool_size(sub["pools"]), same_as_global=same,
                             gateway=gateway(sub, intent), dns=dns(sub),
                             held=(held.get(sub["svc"]) or {}).get(str(sub["id"]), "")))
    # Board D: the exclusions recorded (committed) and the conflicts found against the pools.
    from modules import dhcp_exclusions as E
    try:
        rec = E.read_committed(list_name)
        exc_error = ""
    except E.Refused as exc:
        rec, exc_error = {"exclusions": [], "pools": {}}, str(exc)
    by_key = {(x.get("family"), x.get("id")): x for x in sub_rows}
    exclusions = []
    for e in rec["exclusions"]:
        sub = by_key.get((e.get("family"), e.get("subnet"))) or {}
        as_set = rec["pools"].get(f"{e.get('family')}:{e.get('subnet')}", "")
        try:
            a, b = E.span(e.get("range", ""))
            lo, hi = E.span(as_set) if as_set else (None, None)
            inside = bool(as_set) and not (b < lo or a > hi)
        except E.Refused:
            inside = False
        exclusions.append(dict(e, prefix=sub.get("prefix", ""), as_set=as_set, inside=inside))
    shaped = [{"key": k, "as_set": v, "excluded": [e["range"] for e in rec["exclusions"]
                                                   if f"{e.get('family')}:{e.get('subnet')}" == k],
               "kea": (by_key.get(tuple([k.split(":")[0], int(k.split(":")[1])])) or {})
               .get("pools", [])} for k, v in sorted(rec["pools"].items())]
    out.update(exclusions=exclusions, shaped=shaped, exc_error=exc_error,
               conflicts=E.conflicts(st["value"], rec))
    v4 = [x for x in subnets if x["svc"] == "dhcp4"]
    out.update(
        families=families, subnets=sub_rows, groups=groups, reservations=res_rows,
        summary={"subnets": len(subnets), "v4": len(v4), "v6": len(subnets) - len(v4),
                 "ztp": sum(1 for x in v4 if x["ztp"]), "active": len(active),
                 "reservations": len(res_rows),
                 "unmatched": sum(1 for r in res_rows if r["now"]["state"] == "unmatched"),
                 "unused": sum(1 for r in res_rows if r["now"]["state"] == "off"),
                 "elsewhere": [f for f in families if f["elsewhere"]],
                 "shared": sum(len(v) for v in shared.values())},
        filtered=bool(needle) or s["show"] != "all",
        shown=sum(len(g["rows"]) for g in groups), total=len(rows))
    return out


#: Board C's "Held by": who writes the subnet.
HELD = {"mercury": "Mercury", "ztp": "ZTP's posture (changed only where onboarding sets it)",
        "kea-file": "Kea's own file: moved into Mercury's by the one host step (C529 step 5)"}


def _option(sub: dict, name: str) -> tuple:
    """``(value, inherited)``: the subnet's own option, else the global one it inherits."""
    own = (sub.get("options") or {}).get(name)
    if own is not None:
        return own, False
    glob = (sub.get("global_options") or {}).get(name)
    return (glob, True) if glob is not None else ("", False)


def gateway(sub: dict, intent: dict) -> dict:
    """Board C's Gateway (3): what Kea offers, against intent's first-hop address for the prefix
    (the VRRP group's virtual address on its SVIs). IPv6 has no gateway option: a host's default
    route comes from the routers' advertisements, whose M and O flags intent says.
    ``{"kea", "inherited", "intent": [addresses], "where": [device iface], "state", "words",
    "ra": [{device, iface, managed, other}]}``"""
    if sub.get("family") == "IPv6":
        ra = [dict(e) for e in (intent.get("IPv6") or {}).get(sub.get("prefix", "").lower()) or []]
        return {"kea": "", "inherited": False, "intent": [], "where": [], "ra": ra,
                "state": "ra", "words": "from the routers' RAs"}
    kea, inherited = _option(sub, "routers")
    entries = (intent.get("IPv4") or {}).get(sub.get("prefix", "")) or []
    gw = sorted({a for e in entries for a in e.get("gateway") or []})
    where = [f"{e['device']} {e['iface']}" for e in entries if e.get("gateway")]
    out = {"kea": kea, "inherited": inherited, "intent": gw, "where": where, "ra": []}
    if sub.get("ztp"):
        out.update(state="ztp", words="none, by design (D4)")
    elif not gw:
        out.update(state="none", words="intent names no first-hop address for this prefix"
                   + ("" if entries else " (no interface in intent is on it)"))
    elif kea and kea in gw:
        out.update(state="match", words="matches intent")
    elif kea:
        out.update(state="differs", words=f"intent says {', '.join(gw)}")
    else:
        out.update(state="missing", words=f"Kea offers none; intent says {', '.join(gw)}")
    return out


def dns(sub: dict) -> dict:
    """Board C's DNS (6 / 23): the servers Kea offers, and whether they are inherited."""
    name = "dns-servers" if sub.get("family") == "IPv6" else "domain-name-servers"
    value, inherited = _option(sub, name)
    return {"servers": [v.strip() for v in value.split(",") if v.strip()],
            "inherited": inherited, "code": 23 if sub.get("family") == "IPv6" else 6}


def duid_words(duid: str) -> str:
    """What a DUID is made of, where its type says (RFC 8415): DUID-LL (type 3) and DUID-LLT
    (type 1) carry the client's MAC (hardware type 1, Ethernet)."""
    octets = (duid or "").lower().split(":")
    if octets[:4] == ["00", "03", "00", "01"] and len(octets) == 10:
        return f"DUID-LL, from MAC {':'.join(octets[4:])}"
    if octets[:4] == ["00", "01", "00", "01"] and len(octets) == 14:
        return f"DUID-LLT, from MAC {':'.join(octets[8:])}"
    return ""


def _together(rows: list) -> list:
    """A subnet's leases with one client's together (board A: h1's three addresses, then the
    next client), each set's first row carrying how many it spans and the rest "the same"."""
    order, sets = [], {}
    for r in sorted(rows, key=lambda r: _addr_key(r["address"])):
        key = (r["identity"] or "").lower() or id(r)
        if key not in sets:
            sets[key] = []
            order.append(key)
        sets[key].append(r)
    out = []
    for key in order:
        members = sets[key]
        # How many IA identifiers the set's leases carry (C681): one client that drew a new
        # IAID each time it asked was given a new address each time.
        iaids = len({r.get("iaid") for r in members if r.get("iaid") is not None})
        for i, r in enumerate(members):
            out.append(dict(r, span=len(members) if (i == 0 and r["shared"]) else 0,
                            iaids=iaids,
                            same=i > 0 and r["shared"], duid=duid_words(r["identity"])
                            if r["by"] == "DUID" else ""))
    return out


def _addr_key(address: str):
    try:
        ip = ipaddress.ip_address(address)
        return (ip.version, int(ip))
    except ValueError:
        return (9, 0)


def _ts(iso: str) -> float:
    if not iso:
        return 0.0
    import calendar
    try:
        return float(calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")))
    except ValueError:
        return 0.0


def _beside_reservation(lease: dict, by_subnet: dict, globals_=()) -> bool:
    """A lease from the pool to a host with a reservation in the same subnet for another
    address (board A: h2 asked with a new MAC and was given a pool address); a global
    reservation counts where the subnet uses the global ones."""
    sub = by_subnet.get((lease["svc"], lease["subnet_id"]))
    if not sub or not lease["hostname"]:
        return False
    uses = sub.get("uses") or {"in_subnet": True, "global": False}
    mine = list(sub["reservations"]) if uses["in_subnet"] else []
    if uses["global"]:
        mine += [r for g in globals_ if g["svc"] == lease["svc"] for r in g["reservations"]]
    return any(r["hostname"] == lease["hostname"] and lease["address"] not in r["addresses"]
               for r in mine)


def _reservation_now(r: dict, sub: dict, active: list, subnets=()) -> dict:
    """What a reservation does now (board A's "Now"): not used (Kea's reservations-in-subnet or
    reservations-global is off where it would apply); in use by it; held by another client;
    unmatched (no lease to its identity; a client under its hostname asked with another); or
    no request yet."""
    if sub.get("global"):
        where = [x["id"] for x in subnets
                 if x["svc"] == sub["svc"] and (x.get("uses") or {}).get("global")]
        if not where:
            return {"state": "off", "words": "Kea does not use it: reservations-global is off "
                                             "in every subnet"}
    else:
        if not (sub.get("uses") or {"in_subnet": True})["in_subnet"]:
            return {"state": "off", "words": "Kea does not use it: reservations-in-subnet is "
                                             "off for this subnet"}
        where = [sub["id"]]
    here = [l for l in active if l["svc"] == sub["svc"] and l["subnet_id"] in where]
    ident = (r["identity"] or "").lower()
    for a in r["addresses"]:
        lease = next((l for l in here if l["address"] == a), None)
        if lease and (lease["identity"] or "").lower() == ident:
            return {"state": "in_use", "words": "in use by it"}
        if lease:
            return {"state": "other", "words": f"held by another client, "
                                               f"{lease['identity'] or 'no identity'}"
                                               f"{' (' + lease['hostname'] + ')' if lease['hostname'] else ''}, "
                                               f"until {lease['ends'][:10]}"}
    namesake = next((l for l in here if r["hostname"] and l["hostname"] == r["hostname"]
                     and (l["identity"] or "").lower() != ident), None)
    if namesake:
        return {"state": "unmatched",
                "words": f"no client has asked with this {r['by']}; a client named "
                         f"{r['hostname']} asked as {namesake['identity']} and was given "
                         f"{namesake['address']} from the pool"}
    return {"state": "waiting", "words": "no request yet"}
