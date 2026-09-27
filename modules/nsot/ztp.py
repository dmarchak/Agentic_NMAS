"""P.6: zero-touch provisioning -- the reservation writer and D4's posture.

ZTP is `dhcp` plus two things the tool does itself: it WRITES the Kea
reservation (this module) and it SERVES the bootstrap config (the responder).
Everything the node does after it fetches its config is Phase 2 unchanged.
Scope and decisions: docs/P6_ZTP.md. Measurements: docs/P6_ZTP_PROBE.md.

**The writer (D1).** A reservation is written into a fragment file the tool
owns, which one Kea subnet pulls in by `<?include?>`. Never by `config-set`
alone: kea-dhcp4.conf is root-owned, so `config-write` cannot persist, and a
reservation held only in memory answers every read correctly and is gone at
Kea's next restart (register C49, demonstrated by M5: the file's reservation
survived a restart and the config-set one did not, in the same run).

Every write is:
  1. checked per device (MAC or address already reserved; address leased to
     another MAC; no Kea subnet contains the address; D4);
  2. tested as a CANDIDATE with `kea-dhcp4 -t` against a copy of the main
     config that includes the candidate, before the live fragment is
     touched. A failed `config-reload` keeps the old config running and a
     bad file on disk, which the next restart would find;
  3. swapped in by rename, then `config-reload`;
  4. READ BACK from the running server, and refused unless exactly the
     intended reservations changed, naming both operands.

A set in, per-device outcomes out: P.6 proves one device, and the bulk job
that comes after Stage 7 must not need a different writer.

**D4 (decided 2026-09-26, refined by M3).** A configless IOS-XE node with a
resolver and a route out phones Cisco before it finds anything local, and its
parameter request list ASKS for routers (3), DNS (6) and static routes (33).
Kea sends a requested option wherever it is configured, so the posture held
only because nobody had configured them: held by absence. Two conditions,
both CHECKED:
  1. no route or resolver option reaches a reservation in the ZTP subnet, at
     any level: global, shared-network, subnet or the reservation itself;
     client classes are reported as not ruled out;
  2. nothing on the ZTP segment answers DNS. With no resolver the node
     broadcast its queries to 255.255.255.255:53 (M3: 8 queries, 0
     replies); a host that answered would hand it a resolver with no DHCP
     option at all.
"""

import ipaddress
import json
import logging
import os
import secrets
import shutil
import socket
import struct
import subprocess
import time

log = logging.getLogger(__name__)

#: D4's refusal list, by name and by code. Option 121 is on it because a
#: default route can arrive that way with no option 3 at all.
FORBIDDEN_OPTIONS = {"routers": 3, "domain-name-servers": 6,
                     "static-routes": 33, "classless-static-route": 121}

#: The config-source options a ZTP reservation carries (M3 measured the node
#: using both: `tftp server name <address> resolved`, `RRQ "<file>" octet`).
#: 66 carries an ADDRESS so no resolver is needed; 150 has no name in Kea
#: 2.4.1 and would need an option definition.
SERVER_OPTION = "tftp-server-name"
FILE_OPTION = "boot-file-name"

#: D4's second condition asks with a name nothing should resolve (RFC 6761),
#: so the probe itself cannot make anything reach for the internet.
DNS_PROBE_NAME = "nmas-ztp-probe.invalid"
DNS_PROBE_TIMEOUT = 2.0
#: How long a DNS measurement is reused at plan time. Every use states WHEN
#: it was measured, so a reused answer is never mistaken for a fresh one.
DNS_PROBE_REUSE_SECONDS = 300


class Refused(Exception):
    pass


# ── reading Kea's running config ───────────────────────────────────────────

def _dhcp4(config_result) -> dict:
    """The Dhcp4 object out of a Control Agent `config-get` result."""
    rows = config_result if isinstance(config_result, list) else [config_result]
    for row in rows:
        if isinstance(row, dict):
            dhcp4 = (row.get("arguments") or {}).get("Dhcp4")
            if isinstance(dhcp4, dict):
                return dhcp4
    raise Refused("Kea's config-get answer carries no Dhcp4 configuration")


def _all_subnets(dhcp4: dict) -> list:
    """Every subnet4, top level and inside shared networks, with the shared
    network (or None) it belongs to."""
    out = [(s, None) for s in dhcp4.get("subnet4") or []]
    for net in dhcp4.get("shared-networks") or []:
        out += [(s, net) for s in net.get("subnet4") or []]
    return out


def subnet_for_address(dhcp4: dict, address: str):
    """``(subnet, shared_network_or_None)`` whose CIDR contains *address*.
    Refuses when none does, or more than one does."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        raise Refused(f"{address!r} is not an address")
    hits = []
    for subnet, net in _all_subnets(dhcp4):
        try:
            if ip in ipaddress.ip_network(str(subnet.get("subnet")), strict=False):
                hits.append((subnet, net))
        except ValueError:
            continue
    if len(hits) != 1:
        raise Refused(f"expected exactly one Kea subnet containing {address}, "
                      f"found {len(hits)}")
    return hits[0]


def reservations(dhcp4: dict) -> dict:
    """``{mac: (subnet_id, address)}`` for every reservation Kea holds, in
    subnets, shared networks and the global list."""
    found = {}
    for subnet, _net in _all_subnets(dhcp4):
        for r in subnet.get("reservations") or []:
            if isinstance(r, dict) and r.get("hw-address"):
                found[_mac(r["hw-address"])] = (subnet.get("id"), r.get("ip-address", ""))
    for r in dhcp4.get("reservations") or []:
        if isinstance(r, dict) and r.get("hw-address"):
            found[_mac(r["hw-address"])] = ("global", r.get("ip-address", ""))
    return found


def _mac(value: str) -> str:
    return (value or "").strip().lower().replace("-", ":")


# ── D4, condition 1: no route or resolver option ───────────────────────────

def forbidden_options(dhcp4: dict, address: str) -> list:
    """Every route or resolver option a reservation for *address* would
    EFFECTIVELY receive, as ``(level, name_or_code)``. Empty means none.

    Kea sends an option the client requests from the most specific level
    that has it, so every level is looked at: global, the shared network,
    the subnet, and every reservation in that subnet. Client classes can
    carry options too and are not evaluated here, so their presence is
    reported as a level that could not be ruled out, never as clean.
    """
    subnet, net = subnet_for_address(dhcp4, address)
    codes, names = set(FORBIDDEN_OPTIONS.values()), set(FORBIDDEN_OPTIONS)
    levels = [("global", dhcp4.get("option-data") or [])]
    if net is not None:
        levels.append((f"shared-network {net.get('name')}", net.get("option-data") or []))
    levels.append((f"subnet {subnet.get('id')}", subnet.get("option-data") or []))
    for r in subnet.get("reservations") or []:
        levels.append((f"reservation {r.get('hw-address')}", r.get("option-data") or []))
    found = [(level, o.get("name") or o.get("code")) for level, opts in levels
             for o in opts if o.get("name") in names or o.get("code") in codes]
    if dhcp4.get("client-classes"):
        found.append(("client-classes", "defined: could not be ruled out"))
    return found


# ── D3: the server address is derived, never stored ────────────────────────

def server_address(subnet_cidr: str, addrs=None) -> str:
    """This host's own IPv4 address inside *subnet_cidr* (D3).

    Derived from the host's interfaces every time, because a configured copy
    of this fact is how `tftp_server_ip` came to name an address the host
    does not have (C48). Refuses when the host has none, or more than one,
    in that subnet.
    """
    net = ipaddress.ip_network(subnet_cidr, strict=False)
    if addrs is None:
        import psutil

        addrs = {name: [a.address for a in entries if a.family == socket.AF_INET]
                 for name, entries in psutil.net_if_addrs().items()}
    hits = sorted({(name, a) for name, found in addrs.items() for a in found
                   if ipaddress.ip_address(a) in net})
    if len(hits) != 1:
        raise Refused(f"expected exactly one address of this host in {subnet_cidr}, "
                      f"found {len(hits)}: {[a for _n, a in hits]}")
    return hits[0][1]


# ── D4, condition 2: nothing on the segment answers DNS ────────────────────

def _dns_query(name: str) -> tuple:
    qid = secrets.randbelow(0xFFFF)
    header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0"
    return qid, header + qname + struct.pack(">HH", 1, 1)


def dns_answerers(source: str, timeout: float = DNS_PROBE_TIMEOUT,
                  sock_factory=None, clock=time.time) -> dict:
    """Does anything on the segment answer a BROADCAST DNS query?

    Sent exactly as the node sent its own (M3): to 255.255.255.255:53, from
    this host's address on the segment, which the kernel routes out of that
    interface (measured: `ip route get 255.255.255.255 from <the host's
    address on the segment>` names the segment's interface). Any reply with the query's id is an answerer, whatever
    it says: an NXDOMAIN is still a resolver the node would use.

    ``{"state": "silent" | "answered" | "unknown", "answerers": [...],
    "measured_at": float, "error": str}``. A probe that could not be sent is
    UNKNOWN, never silent.
    """
    sock_factory = sock_factory or (lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
    out = {"state": "unknown", "answerers": [], "measured_at": clock(), "error": ""}
    qid, query = _dns_query(DNS_PROBE_NAME)
    try:
        s = sock_factory()
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((source, 0))
            s.settimeout(0.2)
            s.sendto(query, ("255.255.255.255", 53))
            deadline = clock() + timeout
            answerers = set()
            while clock() < deadline:
                try:
                    data, (peer, _port) = s.recvfrom(4096)
                except socket.timeout:
                    continue
                if len(data) >= 2 and struct.unpack(">H", data[:2])[0] == qid:
                    answerers.add(peer)
        finally:
            s.close()
    except OSError as exc:
        out["error"] = f"the probe could not be sent from {source}: {exc}"
        return out
    out["answerers"] = sorted(answerers)
    out["state"] = "answered" if answerers else "silent"
    return out


_dns_cache = {}


def dns_posture(source: str, probe=dns_answerers, clock=time.time) -> dict:
    """`dns_answerers`, reused for :data:`DNS_PROBE_REUSE_SECONDS`. The
    result always carries `measured_at`, so a reader can see its age."""
    hit = _dns_cache.get(source)
    if hit and hit["state"] != "unknown" and clock() - hit["measured_at"] < DNS_PROBE_REUSE_SECONDS:
        return dict(hit, reused=True)
    result = probe(source)
    _dns_cache[source] = result
    return dict(result, reused=False)


# ── the whole posture, for a plan and for job health ───────────────────────

def posture(address: str, *, kea=None, dns=dns_posture, addrs=None) -> dict:
    """D4 for a reservation at *address*: both conditions, plus D3's derived
    server address. ``{"ok", "reasons", "server", "subnet_id", "dns"}``.

    Every failure to ASK is a reason too: a check that did not run has not
    passed, and a ZTP plan refused here has written nothing.
    """
    out = {"ok": False, "reasons": [], "server": "", "subnet_id": None, "dns": {}}
    kea = kea or _kea()
    got = kea.command("config-get")
    if not got.get("ok"):
        out["reasons"].append(f"Kea could not be asked for its configuration: {got.get('error')}")
        return out
    try:
        dhcp4 = _dhcp4(got["result"])
        subnet, _net = subnet_for_address(dhcp4, address)
        out["subnet_id"] = subnet.get("id")
        bad = forbidden_options(dhcp4, address)
        out["server"] = server_address(str(subnet.get("subnet")), addrs)
    except Refused as exc:
        out["reasons"].append(str(exc))
        return out
    for level, what in bad:
        out["reasons"].append(
            f"D4: {what} reaches a reservation in subnet {subnet.get('id')} "
            f"(at {level}). The node requests route and resolver options, so a "
            f"configless device would be handed a path to Cisco's PnP and Call "
            f"Home services")
    out["dns"] = dns(out["server"])
    state = out["dns"].get("state")
    if state == "answered":
        out["reasons"].append(
            "D4: something on the ZTP segment answers broadcast DNS "
            f"({', '.join(out['dns']['answerers'])}), which would give a "
            "configless node a resolver with no DHCP option at all")
    elif state != "silent":
        out["reasons"].append(
            "D4: whether anything on the ZTP segment answers DNS could not be "
            f"measured ({out['dns'].get('error') or 'no answer'}); a check that "
            "did not run has not passed")
    out["ok"] = not out["reasons"]
    return out


def _kea():
    from modules.integrations.kea import KeaIntegration

    return KeaIntegration()


def ztp_subnets(dhcp4: dict, addrs=None) -> list:
    """``[(subnet, host_address)]``: every Kea subnet holding one of THIS
    host's addresses on an interface Kea listens on. That is where a node
    asking by broadcast is answered, and where the config server is (D3), so
    it is the ZTP segment without anything having to name it."""
    if addrs is None:
        import psutil

        addrs = {name: [a.address for a in entries if a.family == socket.AF_INET]
                 for name, entries in psutil.net_if_addrs().items()}
    listening = [str(i).split("/", 1)[0] for i in
                 (dhcp4.get("interfaces-config") or {}).get("interfaces") or []]
    out = []
    for iface in listening:
        for address in addrs.get(iface, []):
            try:
                subnet, _net = subnet_for_address(dhcp4, address)
            except Refused:
                continue
            out.append((subnet, address))
    return out


def posture_rows(kea=None, dns=dns_posture, addrs=None, get=None) -> list:
    """Job-health rows for D4, one per ZTP subnet. None while ZTP is not
    configured: an empty `kea_ztp_fragment` is already its own row
    (`unset_guard`), and a second row saying the same thing is noise."""
    if get is None:
        from modules.settings_schema import get_setting as get
    if not (get("kea_ztp_fragment", "") or "").strip():
        return []
    what = ("D4: a ZTP reservation gets no route or resolver option, and "
            "nothing on the segment answers DNS")
    kea = kea or _kea()
    got = kea.command("config-get")
    if not got.get("ok"):
        return [{"unit": "ztp-posture", "what": what, "state": "unknown",
                 "max_age_minutes": 0,
                 "detail": f"Kea could not be asked: {got.get('error')} -- not the same as ok"}]
    try:
        found = ztp_subnets(_dhcp4(got["result"]), addrs)
    except Refused as exc:
        found, error = [], str(exc)
    else:
        error = ""
    if not found:
        return [{"unit": "ztp-posture", "what": what, "state": "unknown",
                 "max_age_minutes": 0,
                 "detail": ("no Kea subnet holds this host's address on an interface "
                            f"Kea listens on {error}").strip()}]
    rows = []
    for subnet, address in found:
        p = posture(address, kea=kea, dns=dns, addrs=addrs)
        measured = p.get("dns", {}).get("measured_at")
        when = (time.strftime(" (DNS measured %H:%M:%S)", time.localtime(measured))
                if measured else "")
        state = "ok" if p["ok"] else ("unknown" if any("could not" in r for r in p["reasons"])
                                       else "d4_violated")
        rows.append({"unit": f"ztp-posture:subnet-{subnet.get('id')}", "what": what,
                     "state": state, "max_age_minutes": 0,
                     "detail": ("; ".join(p["reasons"]) or
                                f"subnet {subnet.get('id')} {subnet.get('subnet')}: no route "
                                f"or resolver option, and nothing answered DNS") + when})
    return rows


# ── the writer (D1) ────────────────────────────────────────────────────────

def reservation_entry(mac: str, address: str, hostname: str, server: str) -> dict:
    """The one shape the writer puts in the fragment. Both config-source
    options are `always-send`, as M3 offered them, so what the node gets
    does not depend on what it happens to request.

    `hostname` is sent as option 12. M3 showed AutoInstall APPLIES option 12
    ("Setting hostname router from DHCP reply", from Kea echoing the node's
    own name), so a reservation that names the device makes it name itself
    correctly before its config arrives, rather than after an echo."""
    return {"hw-address": _mac(mac), "ip-address": address, "hostname": hostname,
            "option-data": [
                {"name": SERVER_OPTION, "data": server, "always-send": True},
                {"name": FILE_OPTION, "data": f"{hostname}.cfg", "always-send": True}]}


def _read_fragment(path: str) -> list:
    if not os.path.exists(path):
        raise Refused(f"the fragment {path} does not exist. D1's host change "
                      "creates it (docs/DEPLOY_LINUX.md, the Kea section)")
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Refused(f"the fragment {path} is unreadable ({exc}); refusing to "
                      "write over something that cannot be read")
    if not isinstance(value, list):
        raise Refused(f"the fragment {path} is not a list of reservations")
    return value


def _write_file(path: str, text: str) -> None:
    """Create *path* with mode 0644 set explicitly: a rename carries the new
    inode's mode, and the host shell's umask is 0002 (measured)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.fchmod(fd, 0o644)
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)


def _replace(path: str, text: str) -> None:
    tmp = os.path.join(os.path.dirname(path), f".{os.path.basename(path)}.{os.getpid()}.tmp")
    _write_file(tmp, text)
    os.replace(tmp, path)


def _config_test(main_text: str, fragment: str, candidate_text: str,
                 run=None) -> tuple:
    """``(ok, detail)``: `kea-dhcp4 -t` on a copy of the main config whose
    include names a CANDIDATE fragment. Both copies live beside the fragment,
    because Kea's AppArmor profile allows reads under /etc/kea only (measured:
    /tmp/kea-broken.conf was denied)."""
    directive = f'<?include "{fragment}"?>'
    folder = os.path.dirname(fragment)
    tag = f"{os.getpid()}-{secrets.token_hex(4)}"
    candidate = os.path.join(folder, f".candidate-{tag}.json")
    test_main = os.path.join(folder, f".test-main-{tag}.conf")
    run = run or _run_kea_test
    try:
        _write_file(candidate, candidate_text)
        _write_file(test_main, main_text.replace(directive, f'<?include "{candidate}"?>'))
        return run(test_main)
    finally:
        for p in (candidate, test_main):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass


def _run_kea_test(config_path: str) -> tuple:
    binary = shutil.which("kea-dhcp4")
    if not binary:
        return False, "kea-dhcp4 is not on this host's PATH, so the candidate cannot be tested"
    try:
        proc = subprocess.run([binary, "-t", config_path], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"kea-dhcp4 -t could not run: {exc}"
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
    return proc.returncode == 0, " | ".join(tail)


def write_reservations(adds=(), removes=(), *, kea=None, fragment: str = None,
                       main_config: str = None, run_test=None) -> dict:
    """Write and remove ZTP reservations. ``{"ok", "outcomes", "error",
    "reloaded"}``; `outcomes` is ``{mac: {"outcome", "detail"}}`` with outcome
    ``written | unchanged | removed | absent | refused``.

    *adds* are dicts from :func:`reservation_entry`. *removes* are MACs.
    A device refused alone does not stop the others. A failure after the
    live fragment is touched restores the previous fragment and reloads.
    """
    from modules.settings_schema import get_setting

    out = {"ok": False, "outcomes": {}, "error": "", "reloaded": False}
    fragment = fragment if fragment is not None else get_setting("kea_ztp_fragment", "")
    main_config = main_config or get_setting("kea_dhcp4_config", "/etc/kea/kea-dhcp4.conf")
    if not fragment:
        out["error"] = ("kea_ztp_fragment is not configured: a reservation written "
                        "anywhere else lives in Kea's memory until its next restart (C49)")
        return out
    kea = kea or _kea()

    try:
        with open(main_config, encoding="utf-8") as fh:
            main_text = fh.read()
        if f'<?include "{fragment}"?>' not in main_text:
            raise Refused(f"{main_config} does not include {fragment}, so a reservation "
                          "written there would never reach Kea")
        current = _read_fragment(fragment)
        got = kea.command("config-get")
        if not got.get("ok"):
            raise Refused(f"Kea could not be asked for its configuration: {got.get('error')}")
        dhcp4 = _dhcp4(got["result"])
        leases = kea.command("lease4-get-all", service=["dhcp4"])
        if not leases.get("ok"):
            raise Refused(f"Kea could not be asked for its leases: {leases.get('error')}")
    except (OSError, Refused) as exc:
        out["error"] = str(exc)
        return out

    before = reservations(dhcp4)
    leased = {}
    for row in (leases["result"] if isinstance(leases["result"], list) else [leases["result"]]):
        for lease in ((row or {}).get("arguments") or {}).get("leases") or []:
            leased[lease.get("ip-address", "")] = _mac(lease.get("hw-address", ""))
    mine = {_mac(r.get("hw-address")): r for r in current if isinstance(r, dict)}
    candidate = dict(mine)

    def refuse(mac, why):
        out["outcomes"][mac] = {"outcome": "refused", "detail": why}

    for entry in adds:
        mac, address = _mac(entry.get("hw-address")), entry.get("ip-address", "")
        if mine.get(mac) == entry:
            out["outcomes"][mac] = {"outcome": "unchanged",
                                    "detail": f"{mac} -> {address} is already in the fragment"}
            continue
        if mac in before:
            refuse(mac, f"{mac} is already reserved -> {before[mac][1]} in subnet {before[mac][0]}")
            continue
        taken = [m for m, (_sid, ip) in before.items() if ip == address]
        if taken:
            refuse(mac, f"{address} is already reserved for {taken[0]}")
            continue
        if leased.get(address) and leased[address] != mac:
            refuse(mac, f"{address} is leased to {leased[address]} right now")
            continue
        try:
            bad = forbidden_options(dhcp4, address)
        except Refused as exc:
            refuse(mac, str(exc))
            continue
        bad += [("this reservation", o.get("name") or o.get("code"))
                for o in entry.get("option-data") or []
                if o.get("name") in FORBIDDEN_OPTIONS or o.get("code") in FORBIDDEN_OPTIONS.values()]
        if bad:
            refuse(mac, "D4: " + "; ".join(f"{w} at {lvl}" for lvl, w in bad))
            continue
        candidate[mac] = entry
        out["outcomes"][mac] = {"outcome": "written", "detail": f"{mac} -> {address}"}

    for raw in removes:
        mac = _mac(raw)
        if mac in mine:
            candidate.pop(mac, None)
            out["outcomes"][mac] = {"outcome": "removed", "detail": f"{mac} -> {mine[mac].get('ip-address')}"}
        elif mac in before:
            refuse(mac, f"{mac} is reserved outside {fragment}; the tool removes only what it wrote")
        else:
            out["outcomes"][mac] = {"outcome": "absent", "detail": f"{mac} has no reservation"}

    if candidate == mine:
        out["ok"] = all(o["outcome"] != "refused" for o in out["outcomes"].values())
        return out

    candidate_text = json.dumps(list(candidate.values()), indent=2) + "\n"
    previous_text = json.dumps(current, indent=2) + "\n"
    ok, detail = _config_test(main_text, fragment, candidate_text, run_test)
    if not ok:
        return _refuse_all(out, f"kea-dhcp4 -t refused the candidate: {detail}. "
                                "The live fragment was not touched")

    _replace(fragment, candidate_text)
    reload = kea.command("config-reload")
    if not reload.get("ok"):
        _replace(fragment, previous_text)
        again = kea.command("config-reload")
        return _refuse_all(out, f"config-reload failed ({reload.get('error')}); the previous "
                                "fragment was restored" + ("" if again.get("ok") else
                                f" and ITS reload failed too ({again.get('error')})"))
    out["reloaded"] = True

    # READ BACK, and name both operands on any difference.
    after_got = kea.command("config-get")
    if not after_got.get("ok"):
        out["error"] = f"written and reloaded, and the read-back failed: {after_got.get('error')}"
        return out
    after = {m: ip for m, (_sid, ip) in reservations(_dhcp4(after_got["result"])).items()}
    expected = {m: ip for m, (_sid, ip) in before.items()}
    for mac, o in out["outcomes"].items():
        if o["outcome"] == "written":
            expected[mac] = candidate[mac]["ip-address"]
        elif o["outcome"] == "removed":
            expected.pop(mac, None)
    if after != expected:
        missing = {m: ip for m, ip in expected.items() if after.get(m) != ip}
        extra = {m: ip for m, ip in after.items() if expected.get(m) != ip}
        out["error"] = (f"the running server does not hold what was written: expected "
                        f"{missing or 'nothing more'}, but it holds {extra or 'nothing more'}")
        return out
    if _read_fragment(fragment) != list(candidate.values()):
        out["error"] = f"{fragment} does not read back as the candidate that was tested"
        return out
    out["ok"] = all(o["outcome"] != "refused" for o in out["outcomes"].values())
    return out


def _refuse_all(out: dict, why: str) -> dict:
    out["error"] = why
    for mac, o in out["outcomes"].items():
        if o["outcome"] in ("written", "removed"):
            out["outcomes"][mac] = {"outcome": "refused", "detail": why}
    return out
