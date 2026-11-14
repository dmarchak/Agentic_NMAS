"""A device's routing NEIGHBOURS: the adjacencies its committed intent implies,
against what the device reports (register C38; the Device page's Neighbours
tab, NSOT_GUI_BRIEF 3.3).

**Expected** comes from COMMITTED intent, the whole fleet's, read in two git
calls whatever its size (`committed_intents`): OSPF peers are the managed
devices with an OSPF-enabled, non-passive interface on a shared subnet (the
network statements decide which interfaces are enabled, as IOS does); OSPFv3
the same over IPv6 prefixes with `ipv6 ospf`; BGP peers are the neighbours
intent names, each tied to a managed device by address or said to be outside
management.

**Reported** is what Prometheus last scraped from the device's own routing
tables (`ospfNbrState`, `ospfv3NbrState`, `cbgpPeer2State`, through the
snmp_exporter modules in `deploy/snmp_exporter/`). This reads PROMETHEUS, never
the device: it adds no session to a device (the operator's rule for s3,
2026-10-01). Whether a protocol is measured at all is read from `up` for its
job: a protocol nothing scrapes is "not measured", never "no neighbours".

**RIP and RIPng** keep no neighbour table a MIB walk reads, so they come from the
RIP reader's stored answer (`readers/rip`: what each RIP device hears, read every
five minutes) through Topology's own adjacency code (`rip_protocols`, C12).

What it cannot say, stated rather than implied: an adjacency is ONE side's
report; a peer outside management is observed from this side only; and intent
implies an adjacency only where the subnet and the network statements say so (a
neighbour statement, a virtual link or a demand circuit is not modelled here).
"""

import ipaddress
import logging
import re
import subprocess

log = logging.getLogger(__name__)

#: ospfNbrState / ospfv3NbrState (OSPF-MIB, OSPFV3-MIB).
OSPF_STATES = {1: "down", 2: "attempt", 3: "init", 4: "2-way", 5: "exchange start",
               6: "exchange", 7: "loading", 8: "full"}
#: 2-way is the steady state between two routers that are neither DR nor BDR
#: (golden_state accepts FULL or 2WAY for the same reason).
OSPF_UP = (4, 8)
#: cbgpPeer2State (CISCO-BGP4-MIB).
BGP_STATES = {1: "idle", 2: "connect", 3: "active", 4: "open sent", 5: "open confirm",
              6: "established"}
BGP_UP = (6,)

#: protocol -> (Prometheus job, metric).
SERIES = {"ospf": ("ospf", "ospfNbrState"), "ospfv3": ("ospfv3", "ospfv3NbrState"),
          "bgp": ("bgp", "cbgpPeer2State")}
WORDS = {"ospf": "OSPF", "ospfv3": "OSPFv3", "bgp": "BGP"}

#: A failed read keeps the last good value: a device's protocol counts as measured when ANY of
#: its scrapes in the last WINDOW answered, and its adjacencies are the last good sample in it.
#: An instant read went blank for the minute after one failed scrape (Prometheus marks the
#: series stale), and Needs attention drew "not measured": r1's OSPF walk times out (20 s) on
#: about 1.4% of scrapes, 20 lone minutes in 24 h (measured 2026-10-12). Five scrapes at the
#: 1 m interval; a device unanswering for longer still reads "not measured".
WINDOW = "5m"
WINDOW_WORDS = "5 minutes"

#: A sample is CURRENT while it is younger than the longest routing job's scrape interval plus
#: its timeout (ospf: 60 s and 20 s, read from Prometheus's targets 2026-10-12; ospfv3 scrapes
#: every 30 s), rounded up to 90 s. An older one is the last good value of a scrape that has failed since, and is
#: drawn "as of" its own scrape time, never as current (the operator, 2026-10-12: "a FULL from
#: 4 minutes ago is never read as current").
CURRENT_SECONDS = 90


def query(metric: str, label: str = "") -> str:
    """The PromQL for one adjacency series, or ``up`` for the three jobs: every raw sample in
    WINDOW (a range vector, so each sample keeps the time it was scraped; `last_over_time`
    stamped an old value with the query's time). One device's when *label* (a hostname,
    escaped by the caller) is given, else the fleet's. `rows_of` folds the answer."""
    dev = f'device="{label}"' if label else ""
    if metric == "up":
        return f'up{{{dev + "," if dev else ""}job=~"ospf|ospfv3|bgp"}}[{WINDOW}]'
    return f"{metric}{{{dev}}}[{WINDOW}]"


def rows_of(metric: str, rows: list) -> list:
    """Prometheus's answer to `query`, one row per series in the instant shape
    ``{"metric", "value": [time, value]}``: an adjacency series' NEWEST sample with its own
    scrape time; ``up``'s 1 when ANY scrape in the window answered (a lone failure does not
    blank the read, C690). An instant row (``value``) passes through."""
    out = []
    for r in rows or []:
        if "values" not in r:
            out.append(r)
            continue
        samples = r.get("values") or []
        if not samples:
            continue
        if metric == "up":
            ok = any(str(v) == "1" for _t, v in samples)
            out.append({"metric": r.get("metric") or {}, "value": [samples[-1][0],
                                                                   "1" if ok else "0"]})
        else:
            out.append({"metric": r.get("metric") or {}, "value": list(samples[-1])})
    return out


# ---------------------------------------------------------------------------
# Committed intent, the whole fleet in a fixed number of reads.
# ---------------------------------------------------------------------------

def committed_intents(repo: str) -> tuple:
    """``({hostname: host_vars}, error)`` for every `host_vars/*.yml` committed
    at HEAD: one `git ls-tree` and one `git cat-file --batch`, never a read per
    device (the scale rule). A document that does not parse is left out and
    named in *error*.

    A LEASED ADDRESS IS ITS INTERFACE'S (C1442): the manifest committed beside the intent
    is read in the same two calls, and a device whose management address Kea leases has
    its one ``ip address dhcp`` interface given that address (`leased_address.with_leases`).
    Every reader of this answer (Neighbours, Topology, the RIP reader, Verify's expectations,
    blast radius, the IP SLA policy) then sees the address the device holds; intent itself
    is never written."""
    from modules.nsot import hostvars, leased_address
    from modules.nsot.repo import GIT_TIMEOUT, MANIFEST_REL, _git_env, git, run_git

    rc, out, err = git(repo, "ls-tree", "HEAD", "host_vars/", MANIFEST_REL)
    if rc != 0:
        if "Not a valid object name" in err or "not a tree" in err:
            return {}, ""
        return {}, f"the committed intent could not be listed ({err or rc})"
    entries, manifest_sha = [], ""
    for line in out.splitlines():
        m = re.match(r"^\d+ blob ([0-9a-f]+)\thost_vars/([^/]+)\.yml$", line)
        if m:
            entries.append((m.group(2), m.group(1)))
        m = re.match(r"^\d+ blob ([0-9a-f]+)\t" + re.escape(MANIFEST_REL) + "$", line)
        if m:
            manifest_sha = m.group(1)
    if not entries:
        return {}, ""
    blobs = [sha for _h, sha in entries] + ([manifest_sha] if manifest_sha else [])
    try:
        proc = run_git(repo, "cat-file", "--batch", text=False,
                       input="".join(f"{sha}\n" for sha in blobs).encode(),
                       timeout=GIT_TIMEOUT, env=_git_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, f"the committed intent could not be read ({exc})"
    if proc.returncode != 0:
        return {}, f"the committed intent could not be read ({proc.stderr.decode(errors='replace').strip()})"
    data, pos, docs, bad = proc.stdout, 0, {}, []

    def _next() -> str:
        nonlocal pos
        nl = data.index(b"\n", pos)
        size = int(data[pos:nl].split()[2])
        body = data[nl + 1:nl + 1 + size].decode("utf-8", errors="replace")
        pos = nl + 1 + size + 1
        return body

    for host, _sha in entries:
        body = _next()
        try:
            docs[host] = hostvars.from_yaml(body)
        except Exception:                             # noqa: BLE001
            bad.append(host)
    errors = [f"intent that does not parse is left out: {', '.join(bad)}"] if bad else []
    if manifest_sha:
        manifest, why = leased_address.parse_manifest(_next())
        if why:
            errors.append(f"{why}: no leased address is drawn")
        docs = leased_address.with_leases(docs, manifest)
    return docs, "; ".join(errors)


# ---------------------------------------------------------------------------
# What intent implies.
# ---------------------------------------------------------------------------

def _lines(hv: dict) -> dict:
    """*hv* as the functions below read it: a feature pack's fields (K7) as the lines they
    render. Intent holding lines only (every intent written before the packs) is returned as
    it is, with no render."""
    from modules.nsot.features import raw_view
    return raw_view(hv)


def _all_lines(intents: dict) -> dict:
    """`_lines` of each document, once per call of a function reading many (each render is
    about a millisecond, and `expected` reads every other device's intent per link)."""
    return {host: _lines(hv) for host, hv in (intents or {}).items()}


def _v4(value: str):
    """``IPv4Interface`` from intent's ``"A M"``, or None (dhcp, absent)."""
    parts = (value or "").split()
    if len(parts) != 2:
        return None
    try:
        return ipaddress.ip_interface(f"{parts[0]}/{parts[1]}")
    except ValueError:
        return None


def _passive(settings, name: str) -> bool:
    lines = [s.strip() for s in settings or []]
    if "passive-interface default" in lines:
        return f"no passive-interface {name}" not in lines
    return f"passive-interface {name}" in lines


def _no_adjacency(iface: dict) -> bool:
    name = iface.get("name", "")
    return (name.lower().startswith("loopback") or bool(iface.get("vrf"))
            or bool(iface.get("shutdown")))


def _covered(addr, network_line: str) -> bool:
    m = re.match(r"^network (\S+) (\S+) area \S+$", network_line.strip())
    if not m:
        return False
    try:
        net = int(ipaddress.ip_address(m.group(1)))
        wild = int(ipaddress.ip_address(m.group(2)))
    except ValueError:
        return False
    return (int(addr) & ~wild & 0xFFFFFFFF) == (net & ~wild & 0xFFFFFFFF)


def ospf_links(hv: dict) -> list:
    """``[(interface, IPv4Interface)]`` on which this device would form an OSPF
    adjacency: an address a network statement covers, not passive, not a
    loopback, not in a VRF, not shut, and not a /32."""
    hv = _lines(hv)
    out = []
    procs = ((hv or {}).get("routing") or {}).get("ospf") or []
    for iface in (hv or {}).get("interfaces") or []:
        ip = _v4(iface.get("ipv4", ""))
        if ip is None or _no_adjacency(iface) or ip.network.prefixlen >= 32:
            continue
        for proc in procs:
            if any(_covered(ip.ip, n) for n in proc.get("networks") or []) \
                    and not _passive(proc.get("settings"), iface.get("name", "")):
                out.append((iface["name"], ip))
                break
    return out


def _subnets(iface: dict) -> set:
    """The IPv4 and global IPv6 networks *iface* holds in intent (link-local, /32 and /128
    name no link)."""
    out = set()
    v4 = _v4((iface or {}).get("ipv4", ""))
    if v4 is not None and v4.network.prefixlen < 32:
        out.add(v4.network)
    for addr in (iface or {}).get("ipv6") or []:
        try:
            ip = ipaddress.ip_interface(str(addr).split()[0])
        except (ValueError, IndexError):
            continue
        if ip.network.prefixlen < 128 and not ip.ip.is_link_local:
            out.add(ip.network)
    return out


def far_ends(intents: dict, host: str, interface: str) -> list:
    """``[(device, interface)]``: the far end of *host*'s *interface* in committed intent, every
    other device's interface on one of its IPv4 or global IPv6 networks, sorted. A link to a
    device with no committed intent, or an interface holding no address, names none: the
    caller says so (C2749: a planned window covers both ends of a link it takes down)."""
    return sorted(_far_ends(_all_lines(intents), host, interface))


def _far_ends(lined: dict, host: str, interface: str) -> set:
    """`far_ends` over intents already through `_all_lines` (one render for many questions)."""
    from modules.nsot.ifnames import same_interface

    mine = next((i for i in (lined.get(host) or {}).get("interfaces") or []
                 if same_interface(i.get("name", ""), interface or "")), None)
    nets = _subnets(mine) if mine else set()
    out = set()
    for other, hv in lined.items():
        if other == host or not nets:
            continue
        for iface in (hv or {}).get("interfaces") or []:
            if _subnets(iface) & nets:
                out.add((other, iface.get("name", "")))
    return out


def link_interfaces(intents: dict, host: str) -> list:
    """*host*'s interfaces committed intent gives a neighbour on, in intent's order: an OSPF or
    OSPFv3 adjacency's local interface (`expected`), or one sharing an IPv4 or global IPv6
    network with another device's interface (`far_ends`). Never a loopback, an interface in a
    VRF or a shut one (`_no_adjacency`: no neighbour is cabled to the first, and the others
    form none). What a read of "who is cabled here" (CDP, LLDP) is asked of; ``[]`` when intent
    gives the device no neighbour, which the caller says."""
    lined = _all_lines(intents)
    via = {a["via"] for a in expected(intents, host) if a["proto"] in ("ospf", "ospfv3")}
    out = []
    for iface in (lined.get(host) or {}).get("interfaces") or []:
        name = iface.get("name", "")
        if not name or _no_adjacency(iface) or name in out:
            continue
        if name in via or _far_ends(lined, host, name):
            out.append(name)
    return out


def window_far_ends(intents: dict, devices, interfaces=None) -> list:
    """``[(device, interface)]``: the far ends of every link a planned window's operation takes
    down (C2751; the operator's rule of 2026-11-08: a window for any link-affecting operation
    covers both ends of every link it touches), by `far_ends`, the one way they are found.
    *interfaces* names the ports taken down on each of *devices* (a deploy's interface
    sections); None takes every interface committed intent gives each device (a restart takes
    every link down). A far end that is itself one of *devices* is left out: the window names
    it already. ``"*"`` (every device of a network) names no far end inside it. Sorted."""
    lined = _all_lines(intents)
    named = {d for d in (devices or ()) if d and d != "*"}
    out = set()
    for host in sorted(named):
        ports = (list(interfaces) if interfaces is not None else
                 [i.get("name", "") for i in (lined.get(host) or {}).get("interfaces") or []])
        for port in ports:
            if port:
                out |= {f for f in _far_ends(lined, host, port) if f[0] not in named}
    return sorted(out)


def restart_far_ends(network: str, devices) -> tuple:
    """``(far_ends, error)``: the far ends of every link a restart of *devices* of *network*
    takes down (`window_far_ends` over each device's every interface, from committed intent
    read once), for the restart's planned window (`restarts.record_planned`'s *far_ends*;
    C2751). A window over the whole network (``"*"``) has none outside it, and reads nothing.
    *error* names why committed intent could not be read whole, and *far_ends* is then None:
    the caller refuses the window, since its far ends cannot be told. A network with no list
    folder, or whose repository does not exist yet (its first commit makes it,
    `repo.has_repository`), has no committed intent, so no far end: absent, never unreadable."""
    from modules.nsot import listref
    from modules.nsot.repo import has_repository

    named = [d for d in (devices or ()) if d and d != "*"]
    if not named:
        return [], ""
    try:
        if not listref.exists(network) or not has_repository(listref.resolve(network).repo_dir):
            return [], ""
    except Exception as exc:                          # noqa: BLE001 (named by the caller)
        return None, f"{type(exc).__name__}: {exc}"
    intents, error = committed_intents_of(network)
    if error:
        return None, error
    return window_far_ends(intents, named), ""


def committed_intents_of(network: str) -> tuple:
    """``({hostname: host_vars}, error)``: *network*'s committed intent, read once and without
    creating its list (resolving a list's path makes its folders). A name no network has is an
    error, and so is a read that failed or a document that did not parse (`committed_intents`
    names it): a caller that must know every far end refuses on any *error*."""
    from modules.nsot import listref

    try:
        if not listref.exists(network):
            return {}, f"no network is named {network!r}"
        return committed_intents(listref.resolve(network).repo_dir)
    except Exception as exc:                          # noqa: BLE001 (named by the caller)
        return {}, f"{type(exc).__name__}: {exc}"


def peer_device(intents: dict, address: str) -> str:
    """The device whose committed intent holds *address* (IPv4 or IPv6), or ``""``."""
    try:
        want = ipaddress.ip_address(str(address))
    except ValueError:
        return ""
    for host, hv in _all_lines(intents).items():
        for iface in (hv or {}).get("interfaces") or []:
            v4 = _v4(iface.get("ipv4", ""))
            if v4 is not None and v4.ip == want:
                return host
            for addr in iface.get("ipv6") or []:
                try:
                    if ipaddress.ip_interface(str(addr).split()[0]).ip == want:
                        return host
                except (ValueError, IndexError):
                    continue
    return ""


def ospfv3_links(hv: dict) -> list:
    """``[(interface, IPv6Interface)]`` carrying `ipv6 ospf`, not passive, not
    a loopback (link-local adjacencies, matched on the global prefix)."""
    hv = _lines(hv)
    routing = (hv or {}).get("routing") or {}
    raw = [r for p in routing.get("ospfv3") or [] for r in p.get("raw") or []]
    out = []
    for iface in (hv or {}).get("interfaces") or []:
        if not iface.get("ospfv3") or _no_adjacency(iface) or _passive(raw, iface.get("name", "")):
            continue
        for addr in iface.get("ipv6") or []:
            try:
                ip = ipaddress.ip_interface(addr)
            except ValueError:
                continue
            if ip.network.prefixlen < 128 and not ip.ip.is_link_local:
                out.append((iface["name"], ip))
    return out


def router_id(hv: dict) -> str:
    hv = _lines(hv)
    routing = (hv or {}).get("routing") or {}
    for proc in routing.get("ospf") or []:
        for s in proc.get("settings") or []:
            if s.strip().startswith("router-id "):
                return s.split()[1]
    for proc in routing.get("ospfv3") or []:
        for s in proc.get("raw") or []:
            if s.strip().startswith("router-id "):
                return s.split()[1]
    return ""


def bgp_peers(hv: dict) -> list:
    """The addresses intent names as BGP neighbours (a peer-group name is not
    an address and is left out)."""
    bgp = ((hv or {}).get("routing") or {}).get("bgp") or {}
    out = []
    for line in bgp.get("neighbors") or []:
        m = re.match(r"^neighbor (\S+) remote-as (\S+)", line.strip())
        if m:
            try:
                out.append((ipaddress.ip_address(m.group(1)), m.group(2)))
            except ValueError:
                continue
    return out


def addresses(intents: dict) -> dict:
    """``{ip_address: hostname}``: every interface address in committed intent."""
    out = {}
    for host, hv in intents.items():
        for iface in (hv or {}).get("interfaces") or []:
            ip = _v4(iface.get("ipv4", ""))
            if ip is not None:
                out[ip.ip] = host
            for addr in iface.get("ipv6") or []:
                try:
                    out[ipaddress.ip_interface(addr).ip] = host
                except ValueError:
                    pass
    return out


def expected(intents: dict, host: str) -> list:
    """The adjacencies *host*'s committed intent implies, each
    ``{proto, peer, address, via, rid, managed}``."""
    intents = _all_lines(intents)
    me = intents.get(host) or {}
    out = []
    for name, mine in ospf_links(me):
        for other, hv in sorted(intents.items()):
            if other == host:
                continue
            for _oname, theirs in ospf_links(hv):
                if theirs.network == mine.network:
                    out.append({"proto": "ospf", "peer": other, "address": str(theirs.ip),
                                "via": name, "rid": router_id(hv), "managed": True,
                                "network": str(mine.network)})
    for name, mine in ospfv3_links(me):
        for other, hv in sorted(intents.items()):
            if other == host:
                continue
            if any(t.network == mine.network for _n, t in ospfv3_links(hv)):
                out.append({"proto": "ospfv3", "peer": other, "address": "",
                            "via": name, "rid": router_id(hv), "managed": True,
                            "network": str(mine.network)})
    owners = addresses(intents)
    for addr, asn in bgp_peers(me):
        peer = owners.get(addr, "")
        out.append({"proto": "bgp", "peer": peer, "address": str(addr), "via": f"AS {asn}",
                    "rid": "", "managed": bool(peer), "network": f"ipv{addr.version}"})
    return out


# ---------------------------------------------------------------------------
# What the device reports, through Prometheus.
# ---------------------------------------------------------------------------

def _rid_from_int(value: str) -> str:
    try:
        return str(ipaddress.IPv4Address(int(value)))
    except (TypeError, ValueError):
        return value or ""


def reported(results: dict) -> dict:
    """``{proto: [{address, rid, state, value, at}]}`` from Prometheus's
    instant-query results, keyed by metric name."""
    out = {}
    for proto, (_job, metric) in SERIES.items():
        rows = []
        for r in results.get(metric) or []:
            m = r.get("metric") or {}
            try:
                value = int(float(r["value"][1]))
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            if proto == "ospf":
                addr, rid = m.get("ospfNbrIpAddr", ""), m.get("ospfNbrRtrId", "")
            elif proto == "ospfv3":
                addr, rid = "", _rid_from_int(m.get("ospfv3NbrRtrId", ""))
            else:
                addr, rid = m.get("cbgpPeer2RemoteAddr", ""), ""
                try:
                    addr = str(ipaddress.ip_address(addr)) if ":" not in addr else \
                        ipaddress.ip_address(addr).compressed.upper()
                except ValueError:
                    pass
            rows.append({"address": addr, "rid": rid, "value": value,
                         "at": float(r["value"][0])})
        out[proto] = rows
    return out


def _state(proto: str, value: int) -> tuple:
    if proto == "bgp":
        return BGP_STATES.get(value, f"state {value}"), value in BGP_UP
    return OSPF_STATES.get(value, f"state {value}"), value in OSPF_UP


def _iso(epoch: float) -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _same(a: str, b: str) -> bool:
    try:
        return ipaddress.ip_address(a) == ipaddress.ip_address(b)
    except ValueError:
        return a == b


def compare(intents: dict, host: str, results: dict, up: dict, now: float = None) -> dict:
    """``{"protocols": [{proto, words, measured, why, rows, as_of}], "counts"}``.

    *up* is ``{job: 0|1}`` for this device (absent: not scraped). Each row is
    one expected adjacency with what the device reports for it (``up``,
    ``down``, ``not_seen``), or one reported neighbour no expectation matched
    (``unexpected``). With *now*, a reported value older than CURRENT_SECONDS carries
    ``as_of`` (its own scrape time), and so does a protocol whose newest sample is, with
    each neighbour it no longer reports: what a failed scrape left, never drawn as now."""
    intents = _all_lines(intents)
    exp = expected(intents, host)
    rep = reported(results)
    rid_owner = {router_id(hv): h for h, hv in intents.items() if router_id(hv)}
    owners = addresses(intents)
    protos, counts = [], {"up": 0, "down": 0, "not_seen": 0, "unexpected": 0}
    for proto in SERIES:
        mine = [e for e in exp if e["proto"] == proto]
        seen = rep.get(proto) or []
        job = SERIES[proto][0]
        if not mine and not seen:
            continue
        scraped = up.get(job)
        entry = {"proto": proto, "words": WORDS[proto], "rows": [], "measured": scraped == 1,
                 "why": ""}
        if scraped is None:
            entry["why"] = (f"not measured: Prometheus does not scrape {WORDS[proto]} from "
                            f"{host} (no `{job}` target for it)")
        elif scraped == 0:
            entry["why"] = (f"not measured: no `{job}` scrape of {host} has answered Prometheus "
                            f"in the last {WINDOW_WORDS}, so what it holds is not current")
        used = set()
        for e in mine:
            match = None
            for i, s in enumerate(seen):
                if i in used:
                    continue
                if (proto == "ospfv3" and e["rid"] and s["rid"] == e["rid"]) or \
                        (proto != "ospfv3" and e["address"] and _same(s["address"], e["address"])):
                    match = i
                    break
            row = dict(e)
            if match is None:
                row.update(state="not_seen" if entry["measured"] else "unknown",
                           words="not reported" if entry["measured"] else "not measured")
            else:
                used.add(match)
                words, ok = _state(proto, seen[match]["value"])
                row.update(state="up" if ok else "down", words=words, at=seen[match]["at"])
            entry["rows"].append(row)
        for i, s in enumerate(seen):
            if i in used:
                continue
            peer = rid_owner.get(s["rid"], "") if s["rid"] else ""
            if not peer and s["address"]:
                try:
                    peer = owners.get(ipaddress.ip_address(s["address"]), "")
                except ValueError:
                    peer = ""
            words, ok = _state(proto, s["value"])
            entry["rows"].append({"proto": proto, "peer": peer, "address": s["address"],
                                  "rid": s["rid"], "via": "", "managed": bool(peer),
                                  "state": "unexpected", "words": words, "at": s["at"],
                                  "up": ok})
        newest = max((s["at"] for s in seen if s.get("at")), default=None)
        if now is not None and newest is not None and now - newest > CURRENT_SECONDS:
            entry["as_of"] = _iso(newest)
        for row in entry["rows"]:
            if row["state"] in counts:
                counts[row["state"]] += 1
            if row.get("at"):
                row["at_iso"] = _iso(row["at"])
                if now is not None and now - row["at"] > CURRENT_SECONDS:
                    row["as_of"] = row["at_iso"]
            elif row["state"] == "not_seen" and entry.get("as_of"):
                row["as_of"] = entry["as_of"]
        protos.append(entry)
    return {"protocols": protos, "counts": counts}


#: RIP and RIPng, from the RIP reader (`readers/rip`), never Prometheus: RIP keeps no
#: neighbour table a MIB walk reads, so the reader asks the devices that run it (two
#: read-only show commands each, every five minutes) and this tab draws its stored answer.
RIP_WORDS = {"rip": "RIP", "ripng": "RIPng"}
#: A RIP source's "Last Update" in the device's own notation: ``00:01:31`` under a day, then
#: ``4d06h`` or ``1w1d`` (`pipeline._parse_rip_sources` keeps it as said).
_UNIT_S = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}


def rip_age_seconds(stamp) -> int:
    """*stamp*, a RIP source's last update as the device said it, in seconds, or None when it
    is no such stamp (said as read, never guessed)."""
    s = str(stamp or "").strip()
    m = re.fullmatch(r"(\d+):(\d{2}):(\d{2})", s)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    parts = re.findall(r"(\d+)([wdhms])", s)
    if parts and "".join(n + u for n, u in parts) == s:
        return sum(int(n) * _UNIT_S[u] for n, u in parts)
    return None


def _age_words(seconds: int) -> str:
    """A last update's age in the State column's words: seconds under two minutes, then the
    largest whole unit."""
    if seconds < 120:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    if seconds < 86400:
        return f"{seconds // 3600} h"
    return f"{seconds // 86400} d"


def _rip_timer(mine: dict, host: str) -> tuple:
    """``(seconds, words)``: RIP's timeout a last update is judged against (C3404), *host*'s
    own invalid timer where the RIP reader read it (`readers.rip.invalid_seconds`), else IOS's
    default, and the words naming which."""
    from modules.readers.rip import DEFAULT_INVALID_SECONDS

    own = mine.get("rip_invalid_s")
    if isinstance(own, int) and own > 0:
        return own, f"RIP's timeout {own} s, {host}'s own invalid timer"
    return DEFAULT_INVALID_SECONDS, (f"RIP's timeout {DEFAULT_INVALID_SECONDS} s, IOS's default "
                                     f"({host}'s own invalid timer was not read)")


def _rip_aging(row: dict, stamp, timer: tuple) -> None:
    """*row* (a RIP source heard) with its timeout named in its hover words, and ``aging`` and
    ``age_words`` when its last update is past half the timeout (C3404, the operator,
    2026-11-13: "up · last heard <age>" in the warning colour, so an aging neighbour is visible
    without hovering)."""
    limit, words = timer
    age = rip_age_seconds(stamp)
    row["words"] = f"{row['words']}; {words}"
    if age is not None and age > limit / 2:
        row.update(aging=True, age_words=_age_words(age))


def _peer_address(hv: dict, network: str) -> str:
    """*hv*'s interface address inside *network* (the peer's end of a shared subnet), or ""."""
    try:
        net = ipaddress.ip_network(network)
    except ValueError:
        return ""
    for iface in (hv or {}).get("interfaces") or []:
        for addr in [iface.get("ipv4", "")] + list(iface.get("ipv6") or []):
            ip = _v4(addr) if addr and ":" not in addr else None
            if ip is None and addr:
                try:
                    ip = ipaddress.ip_interface(addr)
                except ValueError:
                    continue
            if ip is not None and ip.ip in net:
                return str(ip.ip)
    return ""


def _owner(owners: dict, address: str) -> str:
    try:
        return owners.get(ipaddress.ip_address(address), "")
    except ValueError:
        return ""


def rip_protocols(intents: dict, host: str, rip: dict, error: str = "") -> list:
    """*host*'s RIP and RIPng entries in `compare`'s shape (C12, the operator's Phase 7 list),
    from the RIP reader's answer for its network (*rip*, `topology_graph.rip_answer`'s value:
    ``{device: {"rip", "ripng", "error", "read_at"}}``; *error* its reason when absent or
    stale). The adjacencies are Topology's own (`topology_graph.rip_links`), one path for both
    screens; each row is *host*'s side: ``up`` when *host* hears the peer, ``not_seen`` when its
    read answered and it does not, ``unknown`` when it was not read. A source *host* hears that
    no adjacency explains (a speaker outside management, or on an interface intent does not run
    RIP on) is ``unexpected``. Only a protocol *host*'s intent runs is drawn.

    A row's ``words`` are its hover (C3404: the State column says only its state): RIPng's
    link-local next hop, RIP's last update and the timeout it is judged against. A RIP row up
    whose last update is past half that timeout (*host*'s own invalid timer, the reader's
    ``rip_invalid_s``, else IOS's 180 s) carries ``aging`` and ``age_words``."""
    from modules.readers.rip import runs
    from modules.readers.topology_graph import rip_links

    intents = _all_lines(intents)
    wants = runs(intents.get(host) or {})
    run = {"rip": wants["rip"], "ripng": bool(wants["ripng"])}
    if not any(run.values()):
        return []
    links = rip_links(intents, sorted(intents), rip or {})
    mine = (rip or {}).get(host) or {}
    owners = addresses(intents)
    out = []
    for layer, words in RIP_WORDS.items():
        if not run[layer]:
            continue
        measured = mine.get(layer) is not None
        why = ""
        if not measured:
            why = (f"not measured: {error}" if error else
                   f"not measured: the RIP reader could not read {host} ({mine['error']})"
                   if mine.get("error") else
                   f"not measured: the RIP reader has not read {host} yet")
        at = mine.get("read_at", "") if measured else ""
        entry = {"proto": layer, "words": words, "rows": [], "measured": measured, "why": why,
                 "source": "reader"}
        timer = _rip_timer(mine, host) if layer == "rip" else None
        explained = set()
        for link in links.get(layer) or []:
            if host not in (link["a"], link["b"]) or not link["intended"]:
                continue
            peer = link["b"] if link["a"] == host else link["a"]
            row = {"proto": layer, "peer": peer, "managed": True, "rid": "",
                   "address": _peer_address(intents.get(peer), link["network"]),
                   "via": link["ports"].get(host, ""), "network": link["network"]}
            heard = link["words_by"].get(host)
            if heard:
                row.update(state="up", words=heard)
                if layer == "rip":
                    # The source Topology's words came from: the last one heard from *peer*.
                    stamp = next((s.get("last_update") for s in reversed(mine.get("rip") or [])
                                  if _owner(owners, s.get("gateway", "")) == peer), None)
                    _rip_aging(row, stamp, timer)
            elif measured:
                row.update(state="not_seen", words=(
                    f"not heard; {peer} hears {host}" if peer in link["words_by"]
                    else "not heard"))
            else:
                row.update(state="unknown", words="not measured")
            if at:
                row["at_iso"] = at
            explained.add(peer)
            entry["rows"].append(row)
        if layer == "rip":
            heard = [(s.get("gateway", ""), s.get("last_update", "?"))
                     for s in mine.get("rip") or []]
        else:
            heard = [(h.get("address", ""), h.get("interface", ""))
                     for h in mine.get("ripng") or []]
        for addr, extra in heard:
            try:
                peer = owners.get(ipaddress.ip_address(addr), "")
            except ValueError:
                peer = ""
            if peer and (peer in explained or layer == "ripng"):
                continue
            if layer == "ripng" and any(r["state"] == "up" and r["via"] == extra
                                        for r in entry["rows"]):
                continue                    # a link-local hop an adjacency already places
            entry["rows"].append({
                "proto": layer, "peer": peer, "managed": bool(peer), "rid": "",
                "address": addr, "via": extra if layer == "ripng" else "",
                "state": "unexpected", "up": True, "at_iso": at,
                "words": (f"heard, last update {extra} before the read" if layer == "rip"
                          else f"heard on {extra}") + ", not implied by intent"})
        out.append(entry)
    return out


def _with_rip(view: dict, intents: dict, host: str, list_name: str) -> dict:
    """*view* with *host*'s RIP and RIPng entries appended and counted (never raises)."""
    try:
        from modules.readers.topology_graph import rip_answer
        lists, error = rip_answer()
        entries = rip_protocols(intents, host, lists.get(list_name) or {}, error)
    except Exception as exc:                          # noqa: BLE001 - said, never raised
        log.warning("neighbours: RIP for %s could not be drawn: %s", host, exc)
        view["errors"].append(f"RIP could not be read: {exc}")
        return view
    counts = view.setdefault("counts", {})
    for e in entries:
        for row in e["rows"]:
            if row["state"] in ("up", "down", "not_seen", "unexpected"):
                counts[row["state"]] = counts.get(row["state"], 0) + 1
    view["protocols"] = list(view.get("protocols") or []) + entries
    return view


def for_device(ref, dev: dict, at: float = None) -> dict:
    """The Neighbours tab's view for one device: committed intent (two git
    reads), four Prometheus instant queries filtered to the device, and the RIP
    reader's stored answer for RIP and RIPng (C12). Never raises; every source
    that could not be read is said. *at* evaluates the queries at that time (an
    evidence pack built for a past alert, C1712); the tab asks for now."""
    from modules.integrations.prometheus import PrometheusIntegration

    host = dev.get("hostname", "")
    view = {"device": host, "errors": [], "protocols": [], "counts": {}, "configured": True}
    intents, err = committed_intents(ref.repo_dir)
    if err:
        view["errors"].append(err)
    if host not in intents:
        view["no_intent"] = True
    prom = PrometheusIntegration()
    if not prom.is_configured():
        view["configured"] = False
        return _with_rip(view, intents, host, ref.name)
    results, up = {}, {}
    label = host.replace("\\", "\\\\").replace('"', '\\"')
    when = {"time": f"{float(at):.3f}"} if at is not None else {}
    for metric in [m for _j, m in SERIES.values()] + ["up"]:
        r = prom._get("api/v1/query", query=query(metric, label), **when)
        if not r.get("ok"):
            view["errors"].append(f"Prometheus could not be asked for {metric}: {r.get('error')}")
            continue
        try:
            body = r["response"].json()
        except ValueError as exc:
            view["errors"].append(f"Prometheus's answer for {metric} could not be read: {exc}")
            continue
        rows = rows_of(metric, (body.get("data") or {}).get("result") or [])
        if metric == "up":
            for row in rows:
                try:
                    up[row["metric"]["job"]] = int(float(row["value"][1]))
                except (KeyError, ValueError, IndexError, TypeError):
                    pass
        else:
            results[metric] = rows
    if view["errors"] and not results and not up:
        return _with_rip(view, intents, host, ref.name)
    import time
    view.update(compare(intents, host, results, up, now=time.time() if at is None else at))
    return _with_rip(view, intents, host, ref.name)


def held_view(ref, dev: dict) -> dict:
    """The Neighbours tab's view for one device as the adjacencies reader last stored it
    (C3166's slice 3: "Neighbours: from the `adjacencies` reader"), never read here: no
    Prometheus query on a page load. The same keys `for_device` returns, and ``held``: when
    the view was read (``at``), and a newer read that failed (``refresh_error``), so the tab
    draws its age and never draws a held view as now. Before the reader's first value, or for
    a device it has not read yet (just onboarded), ``held.state`` is "reading" and the tab
    says the reader fills it on its next read. Never raises."""
    from modules import reader_job
    from modules.readers import adjacencies as ADJ

    host = dev.get("hostname", "")
    view = {"device": host, "errors": [], "protocols": [], "counts": {}, "configured": True}
    try:
        got = reader_job.read_cached(ADJ.READER.name)
    except Exception as exc:                          # noqa: BLE001 - said, never raised
        got = {"state": "unreadable", "doc": None, "why": type(exc).__name__}
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    attempt = doc.get("last_attempt") or {}
    value = good.get("value") or {}
    stored = (value.get("views") or {}).get(f"{ref.name}:{host}")
    if got["state"] != "ok" or not good or stored is None:
        # Absent and unreadable are different states: an unreadable store says so (its file's
        # path is never drawn); absent, or no view of this device yet, is "not read yet".
        why = ("the adjacencies reader's stored value could not be read, so it is read again"
               if got["state"] == "unreadable" else
               f"the adjacencies reader has not read {host}'s neighbours yet")
        view["held"] = {"state": "reading", "why": why,
                        "every": ADJ.INTERVAL_SECONDS,
                        "refresh_error": (attempt.get("error") or "")
                        if attempt.get("ok") is False else ""}
        return view
    view.update(configured=bool(value.get("configured")),
                protocols=stored.get("protocols") or [], counts=stored.get("counts") or {},
                errors=list(stored.get("errors") or []))
    if stored.get("no_intent"):
        view["no_intent"] = True
    view["held"] = {"state": "held", "at": good.get("value_at", ""),
                    "every": ADJ.INTERVAL_SECONDS,
                    "refresh_error": (attempt.get("error") or "")
                    if attempt.get("ok") is False else ""}
    return view
