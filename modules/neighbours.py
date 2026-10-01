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

What it cannot say, stated rather than implied: an adjacency is ONE side's
report; a peer outside management is observed from this side only; RIP keeps
no neighbour table this reads; and intent implies an adjacency only where the
subnet and the network statements say so (a neighbour statement, a virtual
link or a demand circuit is not modelled here).
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


# ---------------------------------------------------------------------------
# Committed intent, the whole fleet in a fixed number of reads.
# ---------------------------------------------------------------------------

def committed_intents(repo: str) -> tuple:
    """``({hostname: host_vars}, error)`` for every `host_vars/*.yml` committed
    at HEAD: one `git ls-tree` and one `git cat-file --batch`, never a read per
    device (the scale rule). A document that does not parse is left out and
    named in *error*."""
    from modules.nsot import hostvars
    from modules.nsot.repo import GIT_TIMEOUT, _git_env, git

    rc, out, err = git(repo, "ls-tree", "HEAD", "host_vars/")
    if rc != 0:
        if "Not a valid object name" in err or "not a tree" in err:
            return {}, ""
        return {}, f"the committed intent could not be listed ({err or rc})"
    entries = []
    for line in out.splitlines():
        m = re.match(r"^\d+ blob ([0-9a-f]+)\thost_vars/([^/]+)\.yml$", line)
        if m:
            entries.append((m.group(2), m.group(1)))
    if not entries:
        return {}, ""
    try:
        proc = subprocess.run(["git", "-C", repo, "cat-file", "--batch"],
                              input="".join(f"{sha}\n" for _h, sha in entries).encode(),
                              capture_output=True, timeout=GIT_TIMEOUT, env=_git_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, f"the committed intent could not be read ({exc})"
    if proc.returncode != 0:
        return {}, f"the committed intent could not be read ({proc.stderr.decode(errors='replace').strip()})"
    data, pos, docs, bad = proc.stdout, 0, {}, []
    for host, _sha in entries:
        nl = data.index(b"\n", pos)
        size = int(data[pos:nl].split()[2])
        body = data[nl + 1:nl + 1 + size].decode("utf-8", errors="replace")
        pos = nl + 1 + size + 1
        try:
            docs[host] = hostvars.from_yaml(body)
        except Exception:                             # noqa: BLE001
            bad.append(host)
    return docs, (f"intent that does not parse is left out: {', '.join(bad)}" if bad else "")


# ---------------------------------------------------------------------------
# What intent implies.
# ---------------------------------------------------------------------------

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


def ospfv3_links(hv: dict) -> list:
    """``[(interface, IPv6Interface)]`` carrying `ipv6 ospf`, not passive, not
    a loopback (link-local adjacencies, matched on the global prefix)."""
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
    me = intents.get(host) or {}
    out = []
    for name, mine in ospf_links(me):
        for other, hv in sorted(intents.items()):
            if other == host:
                continue
            for _oname, theirs in ospf_links(hv):
                if theirs.network == mine.network:
                    out.append({"proto": "ospf", "peer": other, "address": str(theirs.ip),
                                "via": name, "rid": router_id(hv), "managed": True})
    for name, mine in ospfv3_links(me):
        for other, hv in sorted(intents.items()):
            if other == host:
                continue
            if any(t.network == mine.network for _n, t in ospfv3_links(hv)):
                out.append({"proto": "ospfv3", "peer": other, "address": "",
                            "via": name, "rid": router_id(hv), "managed": True})
    owners = addresses(intents)
    for addr, asn in bgp_peers(me):
        peer = owners.get(addr, "")
        out.append({"proto": "bgp", "peer": peer, "address": str(addr), "via": f"AS {asn}",
                    "rid": "", "managed": bool(peer)})
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


def compare(intents: dict, host: str, results: dict, up: dict) -> dict:
    """``{"protocols": [{proto, words, measured, why, rows}], "counts"}``.

    *up* is ``{job: 0|1}`` for this device (absent: not scraped). Each row is
    one expected adjacency with what the device reports for it (``up``,
    ``down``, ``not_seen``), or one reported neighbour no expectation matched
    (``unexpected``)."""
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
            entry["why"] = (f"not measured: Prometheus's last `{job}` scrape of {host} failed, "
                            "so what it holds is not current")
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
        for row in entry["rows"]:
            if row["state"] in counts:
                counts[row["state"]] += 1
            if row.get("at"):
                row["at_iso"] = _iso(row["at"])
        protos.append(entry)
    return {"protocols": protos, "counts": counts}


def for_device(ref, dev: dict) -> dict:
    """The Neighbours tab's view for one device: committed intent (two git
    reads) and four Prometheus instant queries filtered to the device. Never
    raises; every source that could not be read is said."""
    from modules.integrations.prometheus import PrometheusIntegration

    host = dev.get("hostname", "")
    view = {"device": host, "errors": [], "protocols": [], "counts": {}, "configured": True,
            "rip": False}
    intents, err = committed_intents(ref.repo_dir)
    if err:
        view["errors"].append(err)
    view["rip"] = bool(((intents.get(host) or {}).get("routing") or {}).get("rip"))
    if host not in intents:
        view["no_intent"] = True
    prom = PrometheusIntegration()
    if not prom.is_configured():
        view["configured"] = False
        return view
    results, up = {}, {}
    label = host.replace("\\", "\\\\").replace('"', '\\"')
    for metric in [m for _j, m in SERIES.values()] + ["up"]:
        q = (f'up{{device="{label}",job=~"ospf|ospfv3|bgp"}}' if metric == "up"
             else f'{metric}{{device="{label}"}}')
        r = prom._get("api/v1/query", query=q)
        if not r.get("ok"):
            view["errors"].append(f"Prometheus could not be asked for {metric}: {r.get('error')}")
            continue
        try:
            body = r["response"].json()
        except ValueError as exc:
            view["errors"].append(f"Prometheus's answer for {metric} could not be read: {exc}")
            continue
        rows = (body.get("data") or {}).get("result") or []
        if metric == "up":
            for row in rows:
                try:
                    up[row["metric"]["job"]] = int(float(row["value"][1]))
                except (KeyError, ValueError, IndexError, TypeError):
                    pass
        else:
            results[metric] = rows
    if view["errors"] and not results and not up:
        return view
    view.update(compare(intents, host, results, up))
    return view
