"""modules/dhcp_reservations.py — SOURCE OF TRUTH › DHCP › Reservations: add, change and remove a
reservation (C529 step 2; board B, `DhcpReserve.dc.html`, approved 2026-10-06; compared in
docs/fidelity/dhcp-reserve.md).

Each operation is preview → confirm by hash as a verified person → apply → read back → record:

- **The file.** A subnet's reservations live in Mercury's own file for that subnet,
  `<Kea's config folder>/nmas/reservations-<id>.json` (`reservations6-<id>.json` for IPv6), which
  Kea's configuration pulls in with `"reservations": <?include "<file>"?>` (the ZTP writer's
  shape, P.6 D1: a reservation sent only by `config-set` is gone at Kea's next restart, C49).
  Kea's main configuration is root's; the one-time host step
  (`scripts/host-steps/c529-step2-reservation-files.sh`) gives each subnet its file. A subnet
  whose configuration does not take its reservations from Mercury's file is refused, naming
  the file and the step. ZTP's subnet is onboarding's (`modules/nsot/ztp.py`), refused here.
- **Every reservation Kea holds** is read for each check and each read-back: a subnet's own,
  those of subnets inside shared networks, and the global ones; a hosts database (whose
  reservations `config-get` does not list, and Kea 2.4.1 here has no host-commands hook to ask)
  refuses the operation, since a conflict there could not be seen.
- **Stranded:** a reservation whose address its subnet does not contain (or, a global one, no
  subnet contains) is one Kea can never give. The preview names any that exist, and a write
  that would leave one is refused.
- **The apply** holds the subnet file's lock across processes from its read to its read-back
  (`ztp.fragment_lock`, CONCURRENCY_AUDIT R22), plans again and compares the hash, tests the
  candidate with `kea-dhcp4 -t` / `kea-dhcp6 -t` on a copy of the running configuration that
  includes it (the live file untouched until it passes), swaps it in, `config-reload`s, and
  reads back every reservation: exactly the one change, nothing else moved. A difference
  restores the previous file and reloads, and says so.
- **The record:** `dhcp/reservations.yml` in the network's repository, every reservation in
  Mercury's subnet files, committed as the verified person with their reason.
"""

import hashlib
import ipaddress
import json
import logging
import os
import re

log = logging.getLogger(__name__)

FAMILY = {
    "IPv4": {"svc": "dhcp4", "root": "Dhcp4", "sub": "subnet4", "leases": "lease4-get-all",
             "program": "kea-dhcp4", "file": "reservations-{id}.json",
             "setting": "kea_dhcp4_config", "default": "/etc/kea/kea-dhcp4.conf"},
    "IPv6": {"svc": "dhcp6", "root": "Dhcp6", "sub": "subnet6", "leases": "lease6-get-all",
             "program": "kea-dhcp6", "file": "reservations6-{id}.json",
             "setting": "kea_dhcp6_config", "default": "/etc/kea/kea-dhcp6.conf"},
}
#: How a reservation names its client, in board B's order; one Kea does not match on
#: (`host-reservation-identifiers`) is not offered.
OFFERED = {"IPv4": ("hw-address", "duid", "client-id"), "IPv6": ("duid", "hw-address")}
WORDS = {"hw-address": "MAC", "duid": "DUID", "client-id": "client-id",
         "circuit-id": "circuit-id", "flex-id": "flex-id"}
OPS = ("add", "edit", "remove")
#: The apply's steps, in order, as the manual names them (docs/manual/how-it-works/
#: dhcp-reservation.md; tests/test_manual.py holds the page to them).
STEPS = (
    ("plan", "Plan again", "the subnet file's lock taken; Kea and Mercury's file read again, "
                           "and the hash compared with the preview's"),
    ("test", "Kea's own check", "the candidate file tested with kea-dhcp4 -t or kea-dhcp6 -t "
                                "on a copy of the running configuration that includes it"),
    ("write", "Write", "Mercury's file for the subnet replaced by the tested candidate"),
    ("reload", "Reload", "config-reload through Kea's API; a failure restores the file"),
    ("read-back", "Read back", "every reservation Kea holds read again: exactly the change, "
                               "nothing else moved; a difference restores the file"),
    ("record", "Record", "dhcp/reservations.yml committed as you, with your reason"),
)
RECORD = "dhcp/reservations.yml"
_HEX = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2})+$")


class Refused(Exception):
    pass


# ---------------------------------------------------------------------------- where things are

def main_config(list_name: str, family: str) -> str:
    from modules.list_settings import value
    f = FAMILY[family]
    return value(list_name, f["setting"], f["default"]) or f["default"]


def fragment(main: str, family: str, subnet_id) -> str:
    """Mercury's file for one subnet's reservations, beside Kea's configuration."""
    return os.path.join(os.path.dirname(main), "nmas", FAMILY[family]["file"].format(id=subnet_id))


def directive(path: str) -> str:
    return f'<?include "{path}"?>'


# ---------------------------------------------------------------------------- the host step

def subnet_files(main_text: str, main: str, family: str, ids: list) -> dict:
    """The one-time host step's plan for one family: ``{"add": [ids], "have": [ids],
    "refused": str, "candidate": text}``. Each subnet in *ids* (Kea's own, from `config-get`)
    whose block has no ``"reservations"`` key gets ``"reservations": <?include "<its file>"?>,``
    on the line after its ``"id": N,``; one that already takes them from Mercury's file is kept;
    one whose block lists reservations of its own is refused (moving those is the subnet move,
    C529 step 5), as is an id line that is not found exactly once. Text in, text out: Kea's file
    keeps its comments and layout."""
    lines = main_text.splitlines(keepends=True)
    at = {}
    for n, line in enumerate(lines):
        m = re.match(r'^(\s*)"id"\s*:\s*(\d+)\s*,\s*$', line)
        if m:
            at.setdefault(int(m.group(2)), []).append((n, m.group(1)))
    out = {"add": [], "have": [], "refused": "", "candidate": main_text}
    starts = sorted(n for v in at.values() for n, _i in v)
    inserts = {}
    for sid in sorted(ids):
        path = fragment(main, family, sid)
        hits = at.get(sid) or []
        if len(hits) != 1:
            out["refused"] = (f"subnet {sid}'s `\"id\": {sid},` line is found {len(hits)} times "
                              f"in {main}; expected once, on a line of its own")
            return out
        n, indent = hits[0]
        end = next((s for s in starts if s > n), len(lines))
        block = "".join(lines[n:end])
        if directive(path) in block:
            out["have"].append(sid)
            continue
        if '"reservations"' in block:
            out["refused"] = (f"subnet {sid} lists reservations in {main} itself; moving them "
                              "into Mercury's file is the subnet move (C529 step 5), not this "
                              "step")
            return out
        inserts[n] = f'{indent}"reservations": {directive(path)},\n'
        out["add"].append(sid)
    out["candidate"] = "".join(line + inserts.get(n, "") for n, line in enumerate(lines))
    return out


# ---------------------------------------------------------------------------- what Kea holds

def _arguments(result) -> dict:
    entry = result[0] if isinstance(result, list) and result else result
    return (entry or {}).get("arguments") or {}


def kea_config(kea, family: str) -> dict:
    f = FAMILY[family]
    got = kea.command("config-get", [f["svc"]])
    if not got.get("ok"):
        raise Refused(f"Kea's {f['svc']} could not be asked for its configuration: "
                      f"{got.get('error')}")
    config = _arguments(got.get("result")).get(f["root"])
    if not isinstance(config, dict):
        raise Refused(f"Kea's {f['svc']} answered config-get with no {f['root']} configuration")
    return config


def kea_leases(kea, family: str) -> list:
    """Every lease, or a refusal: an unreadable lease list is "cannot check", never "free"."""
    f = FAMILY[family]
    got = kea.command(f["leases"], [f["svc"]])
    if not got.get("ok"):
        raise Refused(f"Kea's leases could not be read ({f['leases']}: {got.get('error')}), so "
                      "whether the address is free cannot be checked")
    return list(_arguments(got.get("result")).get("leases") or [])


def _subnets(config: dict, family: str) -> list:
    """``[(subnet, shared network name or "")]``: every subnet, those in shared networks too."""
    sub = FAMILY[family]["sub"]
    out = [(s, "") for s in config.get(sub) or []]
    for net in config.get("shared-networks") or []:
        out += [(s, net.get("name", "")) for s in net.get(sub) or []]
    return out


def identity(entry: dict, family: str) -> tuple:
    """``(key, value)``: how *entry* (a reservation or a lease) names its client, the way Kea
    keys it, its value in one spelling."""
    keys = OFFERED[family] + tuple(k for k in WORDS if k not in OFFERED[family])
    for key in keys:
        if entry.get(key):
            return key, norm(entry[key])
    return "", ""


def norm(value: str) -> str:
    return (value or "").strip().lower().replace("-", ":")


def addresses(entry: dict) -> list:
    return ([entry["ip-address"]] if entry.get("ip-address") else []) + \
        list(entry.get("ip-addresses") or [])


def every_reservation(config: dict, family: str) -> list:
    """Every reservation Kea's configuration holds: ``[{where, subnet_id, prefix, key, identity,
    addresses, hostname}]``, a subnet's own, a shared network's subnets', and the global ones."""
    out = []
    for s, net in _subnets(config, family):
        where = (f"shared network {net}, " if net else "") + f"subnet {s.get('id')}"
        for r in s.get("reservations") or []:
            key, ident = identity(r, family)
            out.append({"where": where, "subnet_id": s.get("id"), "prefix": s.get("subnet", ""),
                        "key": key, "identity": ident, "addresses": addresses(r),
                        "hostname": r.get("hostname", "")})
    for r in config.get("reservations") or []:
        key, ident = identity(r, family)
        out.append({"where": "global", "subnet_id": None, "prefix": "", "key": key,
                    "identity": ident, "addresses": addresses(r),
                    "hostname": r.get("hostname", "")})
    return out


def host_databases(config: dict) -> list:
    from modules.readers.dhcp import held_elsewhere
    return held_elsewhere(config)


def _in(address: str, prefix: str) -> bool:
    try:
        return ipaddress.ip_address(address) in ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return False


def stranded(config: dict, family: str) -> list:
    """The reservations Kea can never give: an address its subnet does not contain, or a global
    one no subnet contains; each in words naming the reservation and its address."""
    prefixes = [s.get("subnet", "") for s, _n in _subnets(config, family)]
    out = []
    for r in every_reservation(config, family):
        for a in r["addresses"]:
            home = [r["prefix"]] if r["subnet_id"] is not None else prefixes
            if not any(_in(a, p) for p in home):
                out.append(f"{r['where']}: {WORDS.get(r['key'], r['key'])} {r['identity']} -> "
                           f"{a}, which " + (f"its subnet {r['prefix']} does not contain"
                                             if r["prefix"] else "no subnet contains"))
    return out


def _pool_holds(subnet: dict, address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    for p in subnet.get("pools") or []:
        text = str(p.get("pool", "")).replace(" ", "")
        try:
            if "-" in text:
                lo, hi = (ipaddress.ip_address(x) for x in text.split("-", 1))
                if lo <= ip <= hi:
                    return True
            elif ip in ipaddress.ip_network(text, strict=False):
                return True
        except ValueError:
            continue
    return False


def _lease_ends(lease: dict) -> str:
    import time
    cltt, valid = lease.get("cltt"), lease.get("valid-lft")
    if isinstance(cltt, int) and isinstance(valid, int):
        return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(cltt + valid))
    return "an unknown time"


# ---------------------------------------------------------------------------- the ask

ASKS = ("op", "family", "subnet", "key", "identity", "address", "hostname", "was")


def ask(values) -> dict:
    """The operation as the form sends it: op, family, subnet, how the client is named and its
    value, the address and hostname; ``was`` names the reservation an edit or a removal acts
    on (``<key>=<identity>``)."""
    s = {k: (values.get(k) or "").strip() for k in ASKS}
    # The form's subnet picker sends both at once (`IPv4:20`): ids repeat across the families.
    where = (values.get("where") or "").strip()
    if where and ":" in where:
        s["family"], s["subnet"] = (x.strip() for x in where.split(":", 1))
    s["identity"] = norm(s["identity"])
    s["address"] = s["address"].lower() if ":" in s["address"] else s["address"]
    return s


def _entry(family: str, key: str, ident: str, address: str, hostname: str, keep: dict = None):
    """The reservation as Mercury's file holds it; an edited one keeps its other keys (options,
    classes), which the form does not show."""
    entry = {k: v for k, v in (keep or {}).items()
             if k not in WORDS and k not in ("ip-address", "ip-addresses", "hostname")}
    entry[key] = ident
    if family == "IPv4":
        entry["ip-address"] = address
    else:
        entry["ip-addresses"] = [address]
    if hostname:
        entry["hostname"] = hostname
    return entry


def _read_file(path: str) -> tuple:
    """``(entries, text)`` of Mercury's file for a subnet. Refuses an absent or unreadable one."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        value = json.loads(text)
    except FileNotFoundError:
        raise Refused(f"Mercury's file for this subnet, {path}, does not exist: the one-time "
                      "host step (scripts/host-steps/c529-step2-reservation-files.sh) creates "
                      "it") from None
    except (OSError, ValueError) as exc:
        raise Refused(f"{path} could not be read ({exc}); nothing is written over a file that "
                      "cannot be read") from None
    if not isinstance(value, list):
        raise Refused(f"{path} is not a list of reservations")
    return value, text


def _version(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:7]


# ---------------------------------------------------------------------------- the plan

def plan(list_name: str, values, kea=None, main_text=None) -> dict:
    """What board B's preview draws: ``{ok, refused, op, family, subnet_id, prefix, title,
    change: [(sign, text)], checks: [(state, text)], not_done: [str], before, after, path,
    version, hash}``. A read: Kea is asked, Mercury's file is read; nothing is written."""
    s = ask(values)
    p = {"ok": False, "refused": "", "ask": s, "op": s["op"], "family": s["family"],
         "subnet_id": None, "prefix": "", "title": "", "change": [], "checks": [],
         "not_done": [], "before": None, "after": None, "path": "", "version": "", "hash": "",
         "stranded": [], "subject": ""}
    try:
        _plan(list_name, s, p, kea, main_text)
    except Refused as exc:
        p["refused"] = str(exc)
        return p
    p["hash"] = hashlib.sha256(json.dumps(
        {k: p[k] for k in ("op", "family", "subnet_id", "before", "after", "version")},
        sort_keys=True).encode("utf-8")).hexdigest()
    p["ok"] = True
    return p


def _plan(list_name, s, p, kea, main_text) -> None:
    if s["op"] not in OPS:
        raise Refused(f"{s['op']!r} is not one of {', '.join(OPS)}")
    if s["family"] not in FAMILY:
        raise Refused(f"{s['family']!r} is not IPv4 or IPv6")
    family, f = s["family"], FAMILY[s["family"]]
    try:
        sid = int(s["subnet"])
    except ValueError:
        raise Refused(f"{s['subnet']!r} is not a subnet id") from None
    if kea is None:
        from modules.integrations.kea import KeaIntegration
        kea = KeaIntegration(list_name=list_name)
    if not kea.is_configured():
        from modules.installation_settings import settings_place
        raise Refused(f"Kea is not configured for this network ({settings_place('kea', 'Kea')})")
    config = kea_config(kea, family)
    found = [(sub, net) for sub, net in _subnets(config, family) if sub.get("id") == sid]
    if len(found) != 1:
        raise Refused(f"Kea's {f['svc']} has {len(found)} subnets with id {sid}; expected one")
    subnet, net = found[0]
    p.update(subnet_id=sid, prefix=subnet.get("subnet", ""))
    where = (f"shared network {net}, " if net else "") + f"subnet {sid} ({p['prefix']})"
    dbs = host_databases(config)
    if dbs:
        raise Refused(f"Kea keeps reservations in {', '.join(dbs)}, which its configuration "
                      "does not list and this Kea cannot be asked for, so a conflict there "
                      "could not be checked; nothing is written")
    main = main_config(list_name, family)
    path = fragment(main, family, sid)
    p["path"] = path
    if family == "IPv4" and _ztp_fragment(list_name) and \
            os.path.abspath(path) == os.path.abspath(_ztp_fragment(list_name)):
        raise Refused(f"subnet {sid} is ZTP's: its reservations are onboarding's (Devices › Add "
                      "device), written by onboarding's own writer")
    if main_text is None:
        try:
            with open(main, encoding="utf-8") as fh:
                main_text = fh.read()
        except OSError as exc:
            raise Refused(f"Kea's configuration {main} could not be read on this host ({exc}); "
                          "Mercury writes reservations only where Kea's files are") from None
    if directive(path) not in main_text:
        raise Refused(f"Kea's configuration ({main}) does not take subnet {sid}'s reservations "
                      f"from Mercury's file {path}: the one-time host step "
                      "(scripts/host-steps/c529-step2-reservation-files.sh) has not run for it")
    mine, text = _read_file(path)
    p["version"] = _version(text)
    held = every_reservation(config, family)
    leases = kea_leases(kea, family)
    p["stranded"] = stranded(config, family)

    before = None
    if s["op"] in ("edit", "remove"):
        wkey, _, wid = s["was"].partition("=")
        wid = norm(wid)
        hits = [e for e in mine if identity(e, family) == (wkey, wid)]
        if len(hits) != 1:
            elsewhere = [r for r in held if (r["key"], r["identity"]) == (wkey, wid)]
            raise Refused(
                f"{WORDS.get(wkey, wkey)} {wid} has {len(hits)} reservations in Mercury's file "
                f"for subnet {sid}" + (f"; Kea holds it in {elsewhere[0]['where']}, which "
                                       "Mercury did not write and does not change"
                                       if elsewhere and not hits else ""))
        before = hits[0]
    p["before"] = before
    name = (before or {}).get("hostname") or s["hostname"] or s["identity"] or "?"

    if s["op"] == "remove":
        after = None
        a0 = addresses(before)[0] if addresses(before) else "?"
        p["title"] = f"Remove the reservation for {name} on {p['prefix']}"
        p["change"] = [("-", f"reservation {name}: {before and identity(before, family)[0]} "
                             f"{identity(before, family)[1]}, address {a0}")]
        holder = next((l for l in leases if l.get("ip-address") == a0), None)
        if holder:
            p["not_done"].append(
                f"{name} keeps {a0} until its lease ends ({_lease_ends(holder)}). Kea will not "
                "give the address to another client before then. After it, it may be given "
                f"any address in the pool, and another client may be given {a0}.")
        else:
            p["not_done"].append(f"{a0} is leased to no one now: after this, Kea may give it to "
                                 "any client when it is in a pool.")
        p["not_done"].append(f"The reservation stays in the repository's history ({RECORD}); "
                             "adding it back is one Add.")
        p["subject"] = f"dhcp: {name}'s reservation on {p['prefix']} removed (was {a0})"
    else:
        key, ident, address = s["key"], s["identity"], s["address"]
        offered = [k for k in OFFERED[family] if k in (config.get("host-reservation-identifiers")
                                                        or OFFERED[family])]
        if key not in offered:
            raise Refused(f"Kea's {f['svc']} reserves by {', '.join(WORDS[k] for k in offered)}; "
                          f"{key!r} is not one of them")
        if not _HEX.match(ident) or (key == "hw-address" and len(ident) != 17):
            raise Refused(f"{ident!r} is not a {WORDS[key]} (hex bytes separated by colons"
                          + (", six of them" if key == "hw-address" else "") + ")")
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise Refused(f"{address!r} is not an address") from None
        if ip.version != (4 if family == "IPv4" else 6):
            raise Refused(f"{address} is not an {family} address")
        if s["hostname"] and not re.match(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,62})$", s["hostname"]):
            raise Refused(f"{s['hostname']!r} is not a hostname (letters, digits, dots and "
                          "hyphens)")
        after = _entry(family, key, ident, address, s["hostname"] or
                       (before or {}).get("hostname", ""), keep=before)
        if not _in(address, p["prefix"]):
            raise Refused(f"{address} is not inside {where}: it would be stranded, a "
                          "reservation Kea can never give")
        if _pool_holds(subnet, address):
            p["checks"].append(("pass", f"{address} is inside {p['prefix']} and inside its pool, "
                                        "so no other client may be given it while reserved"))
        else:
            p["checks"].append(("pass", f"{address} is inside {p['prefix']} and outside its "
                                        "pools: only this client is ever given it"))
        others = [r for r in held if r["subnet_id"] == sid and
                  (r["key"], r["identity"]) != identity(before or {}, family) and
                  ((r["key"], r["identity"]) == (key, ident) or address in r["addresses"])]
        if others:
            o = others[0]
            raise Refused(f"Not reserved: {where} already holds a reservation for "
                          f"{WORDS.get(o['key'], o['key'])} {o['identity']} -> "
                          f"{', '.join(o['addresses'])}" + (f" ({o['hostname']})"
                                                            if o["hostname"] else "")
                          + f"; asked: {WORDS[key]} {ident} -> {address}")
        p["checks"].append(("pass", f"No other reservation in subnet {sid} names {ident} or "
                                    f"{address}"))
        elsewhere = [r for r in held if r["subnet_id"] != sid and (r["key"], r["identity"]) ==
                     (key, ident)]
        for r in elsewhere:
            p["checks"].append(("note", f"{WORDS[key]} {ident} is also reserved in {r['where']} "
                                        f"({', '.join(r['addresses'])}); Kea gives it each "
                                        "subnet's own"))
        holder = next((l for l in leases if l.get("ip-address") == address and
                       l.get("subnet-id") == sid), None)
        old = identity(before or {}, family)
        if holder and before is not None and norm(holder.get(old[0], "")) == old[1] and \
                norm(holder.get(key, "")) != ident:
            p["checks"].append(("note", f"{address} is leased to this reservation's old "
                                        f"{WORDS.get(old[0], old[0])} {old[1]} until "
                                        f"{_lease_ends(holder)}; that lease ends then, and the "
                                        "new identity is given the address at its next request"))
            holder = None
            p["_old_lease"] = True
        if holder and norm(holder.get(key, "")) != ident:
            hk, hv = identity(holder, family)
            raise Refused(f"Not reserved: {address} is leased to another client. Asked: reserve "
                          f"{address} for {WORDS[key]} {ident}" + (f" ({s['hostname']})" if
                                                                  s["hostname"] else "")
                          + f". Kea's leases say {address} is leased to {WORDS.get(hk, hk)} "
                          f"{hv}" + (f" (hostname {holder.get('hostname')})"
                                     if holder.get("hostname") else "")
                          + f" until {_lease_ends(holder)}. Read just now. Pick a free "
                          "address, or end that lease first.")
        if not p.pop("_old_lease", False):
            p["checks"].append(("pass", f"{address} is leased only to this client now" if holder
                                else f"{address} is leased to no one now"))
        mine_leases = [l for l in leases if norm(l.get(key, "")) == ident and
                       l.get("subnet-id") == sid and l.get("ip-address") != address]
        for l in mine_leases:
            p["not_done"].append(
                f"{name} keeps {l.get('ip-address')} until it asks again (its lease ends "
                f"{_lease_ends(l)}); it takes {address} at its next request. A reservation does "
                "not end other leases; to move it now, release and renew on the client.")
        if s["op"] == "edit":
            bk, bv = identity(before, family)
            p["title"] = f"Edit the reservation for {name} on {p['prefix']}"
            if (bk, bv) != (key, ident):
                p["change"].append(("-", f"{bk} {bv}"))
                p["change"].append(("+", f"{key} {ident}"))
            if addresses(before) != [address]:
                p["change"].append(("-", f"address {', '.join(addresses(before))}"))
                p["change"].append(("+", f"address {address}"))
            if (before.get("hostname") or "") != (after.get("hostname") or ""):
                p["change"].append(("-", f"hostname {before.get('hostname') or '(none)'}"))
                p["change"].append(("+", f"hostname {after.get('hostname') or '(none)'}"))
            if not p["change"]:
                raise Refused("Nothing to change: the reservation already holds these values")
            p["subject"] = (f"dhcp: {name} reserved by {WORDS[key]} {ident} -> {address}"
                            + (f" (was {bv})" if bv != ident else ""))
        else:
            p["title"] = f"Reserve an address on {p['prefix']}"
            p["change"].append(("+", f"reservation {name}: {key} {ident}, address "
                                     f"{address}"))
            p["subject"] = f"dhcp: {name} reserved {address} by {WORDS[key]} {ident}"
        p["after"] = after
    p["checks"].append(("apply", f"The candidate file passes Kea's own check ({f['program']} -t "
                                 "on a copy of the running configuration that includes it), run "
                                 "when you confirm; the live file is untouched until then"))
    p["checks"].append(("pass", f"Mercury's file for subnet {sid} is the version this preview "
                                f"read ({p['version']}); if it moved, nothing is written"))
    p["checks"].append(("note" if p["stranded"] else "pass",
                        "Stranded now: " + "; ".join(p["stranded"]) if p["stranded"] else
                        "No reservation Kea holds is stranded (subnets, shared networks and "
                        "global; no hosts database)"))


def _ztp_fragment(list_name: str) -> str:
    from modules.list_settings import value
    return value(list_name, "kea_ztp_fragment", "") or ""


# ---------------------------------------------------------------------------- the apply

def apply(list_name: str, values, confirmed_hash: str, *, actor: str, reason: str, kea=None,
          run_test=None, main_text=None, record=None) -> dict:
    """``{ok, error, outcome, read_back, rolled_back, commit, plan}``. Holds the subnet file's
    lock from its read to its read-back; plans again and refuses unless the hash matches."""
    from modules.nsot import ztp

    out = {"ok": False, "error": "", "outcome": "", "read_back": "", "rolled_back": "",
           "commit": "", "plan": None}
    if not (reason or "").strip():
        out["error"] = "a reason is recorded with every reservation change; none was given"
        return out
    s = ask(values)
    if s["family"] not in FAMILY:
        out["error"] = f"{s['family']!r} is not IPv4 or IPv6"
        return out
    if kea is None:
        from modules.integrations.kea import KeaIntegration
        kea = KeaIntegration(list_name=list_name)
    family, f = s["family"], FAMILY[s["family"]]
    main = main_config(list_name, family)
    try:
        path = fragment(main, family, int(s["subnet"]))
    except ValueError:
        out["error"] = f"{s['subnet']!r} is not a subnet id"
        return out
    with ztp.fragment_lock(path):
        p = plan(list_name, values, kea=kea, main_text=main_text)
        out["plan"] = p
        if not p["ok"]:
            out["error"] = p["refused"]
            return out
        if p["hash"] != confirmed_hash:
            out["error"] = (f"what the preview showed has changed ({confirmed_hash[:12]} -> "
                            f"{p['hash'][:12]}): Kea or Mercury's file moved since; nothing was "
                            "written. Preview again")
            return out
        before_all = every_reservation(kea_config(kea, family), family)
        mine, previous_text = _read_file(path)
        ident_of = (lambda e: identity(e, family))  # noqa: E731
        candidate = [e for e in mine if p["before"] is None or ident_of(e) != ident_of(p["before"])]
        if p["after"] is not None:
            candidate.append(p["after"])
        candidate_text = json.dumps(candidate, indent=2) + "\n"
        if main_text is None:
            with open(main, encoding="utf-8") as fh:
                main_text = fh.read()
        run = run_test or (lambda cfg: ztp._run_kea_test(cfg, f["program"]))   # noqa: SLF001
        ok, detail = ztp._config_test(main_text, path, candidate_text, run)  # noqa: SLF001
        if not ok:
            out["error"] = (f"{f['program']} -t refused the candidate: {detail}. Mercury's file "
                            "was not touched")
            return out
        ztp._replace(path, candidate_text)                                   # noqa: SLF001
        reload = kea.command("config-reload", [f["svc"]])
        if not reload.get("ok"):
            ztp._replace(path, previous_text)                                # noqa: SLF001
            again = kea.command("config-reload", [f["svc"]])
            out["rolled_back"] = ("the previous file was restored" + (
                "" if again.get("ok") else f", and ITS reload failed too ({again.get('error')})"))
            out["error"] = f"config-reload failed ({reload.get('error')}): nothing changed in Kea"
            return out
        # READ BACK every reservation Kea holds: exactly the one change, nothing else moved.
        def key_of(r):
            return (r["where"], r["key"], r["identity"], tuple(r["addresses"]))
        try:
            after_config = kea_config(kea, family)
            after_all = every_reservation(after_config, family)
        except Refused as exc:
            out["error"] = f"written and reloaded, and the read-back failed: {exc}"
            return out
        expected = set(map(key_of, before_all))
        where = next((r["where"] for r in before_all + after_all if r["subnet_id"] ==
                      p["subnet_id"]), f"subnet {p['subnet_id']}")
        if p["before"] is not None:
            bk, bv = identity(p["before"], family)
            expected.discard((where, bk, bv, tuple(addresses(p["before"]))))
        if p["after"] is not None:
            ak, av = identity(p["after"], family)
            expected.add((where, ak, av, tuple(addresses(p["after"]))))
        got = set(map(key_of, after_all))
        if got != expected or stranded(after_config, family) != p["stranded"]:
            missing, extra = sorted(expected - got), sorted(got - expected)
            ztp._replace(path, previous_text)                                # noqa: SLF001
            again = kea.command("config-reload", [f["svc"]])
            out["rolled_back"] = ("Mercury's previous file restored and Kea reloaded" if
                                  again.get("ok") else "Mercury's previous file restored, and "
                                  f"Kea's reload of it FAILED ({again.get('error')})")
            out["error"] = (f"Kea's running configuration does not hold what was written: "
                            f"expected {missing or 'nothing more'}, but it holds "
                            f"{extra or 'nothing more'}")
            return out
        out["read_back"] = (f"Kea's running configuration now holds {len(got)} "
                            f"{family} reservation(s), and in {where} exactly the change shown; "
                            "nothing else changed")
        out["outcome"] = {"add": "added", "edit": "changed", "remove": "removed"}[p["op"]]
        rec = (record or record_commit)(list_name, p, actor=actor, reason=reason)
        out["commit"] = rec.get("commit", "")
        if not rec.get("ok"):
            out["error"] = (f"written to Kea and read back; the record failed: {rec.get('error')}")
            return out
        out["ok"] = True
        return out


def record_commit(list_name: str, p: dict, *, actor: str, reason: str) -> dict:
    """Write `dhcp/reservations.yml` (every reservation in Mercury's subnet files, both families)
    and commit it as *actor*, the reason in its body."""
    import yaml

    from modules.config import get_list_data_dir
    from modules.filestore import write_atomic
    from modules.nsot import repo as R

    repo = os.path.join(get_list_data_dir(list_name), "config_repo")
    doc = {"reservations": held_by_mercury(list_name)}
    with R.repo_lock(repo):
        path = os.path.join(repo, RECORD)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_atomic(path, "# Kea reservations Mercury holds in its subnet files (C529); "
                           "written on each change.\n" + yaml.safe_dump(doc, sort_keys=False))
        subject = p.get("subject") or "dhcp: reservation changed"
        return R._commit_paths(list_name, [RECORD], f"{subject}\n\n{reason.strip()}",  # noqa: SLF001
                               [f"Actor: {actor}"], "dhcp")


def held_by_mercury(list_name: str) -> list:
    """Every reservation in Mercury's subnet files (ZTP's excluded: onboarding's), as recorded."""
    out = []
    ztp_file = os.path.abspath(_ztp_fragment(list_name)) if _ztp_fragment(list_name) else ""
    for family, f in FAMILY.items():
        folder = os.path.join(os.path.dirname(main_config(list_name, family)), "nmas")
        pattern = re.compile("^" + re.escape(f["file"]).replace(r"\{id\}", r"(\d+)") + "$")
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            m = pattern.match(name)
            path = os.path.join(folder, name)
            if not m or os.path.abspath(path) == ztp_file:
                continue
            try:
                entries, _t = _read_file(path)
            except Refused:
                continue
            for e in entries:
                key, ident = identity(e, family)
                out.append({"family": family, "subnet": int(m.group(1)), "by": WORDS.get(key, key),
                            "identity": ident, "addresses": addresses(e),
                            "hostname": e.get("hostname", "")})
    return out
