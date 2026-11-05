"""The DHCP server pack: a Cisco router's own DHCPv4 server in its intent, `dhcp_server`
(`ip dhcp excluded-address`, `ip dhcp pool <name>`). Lab 9's A4 (docs/LAB_READINESS.md, "A4:
the router's pool"); docs/FEATURE_PACKS.md, "DHCP server".

The fields are DHCP's own concepts (RFC 2131 and RFC 2132's options), not IOS's words:
addresses the server never offers, and pools, each with its network, its routers (option 3),
its name servers (option 6), its domain name (option 15) and its lease. The partial
(`templates/_common.j2`, `dhcp_server_block`) writes them in IOS's words, as Cisco's guide
gives them: "IP Addressing: DHCP Configuration Guide, Cisco IOS Release 15M&T", "Configuring
the Cisco IOS DHCP Server",
https://www.cisco.com/c/en/us/td/docs/ios-xml/ios/ipaddr_dhcp/configuration/15-mt/dhcp-15-mt-book/config-dhcp-server.html
(read 2026-11-05):

- ``ip dhcp excluded-address low-address [high-address]``;
- ``ip dhcp pool name`` (a string or an integer), and in it ``network network-number [mask |
  /prefix-length]``, ``default-router address [address2 ... address8]``, ``dns-server address
  [address2 ... address8]`` ("up to eight"), ``domain-name domain``, ``lease {days [hours
  [minutes]] | infinite}`` (the default "a one-day lease").

The checks a value must pass, each refusal naming the field, its value and the rule:

- a router is on the client's subnet (RFC 2132 section 3.5: "The router option specifies a list
  of IP addresses for routers on the client's subnet"), so a default router outside its pool's
  network, or the network's own or broadcast address, is refused;
- at most eight routers and eight name servers (the guide);
- a pool's network has its length and no host bits;
- an excluded range runs low to high.

**DHCPv6 is not covered.** IOS's DHCPv6 server is another command family (``ipv6 dhcp pool``,
with prefixes and no ``network``): its lines stay verbatim in ``unmodeled``, rendered as they
were, and an IPv6 address in any field here is refused by name.

A line the pack does not model or cannot reproduce stays verbatim: a pool's other lines (an
``option``, ``netbios-*``, ``bootfile``) in its ``raw``, in order, after the modelled ones; a
pool with a submode (a ``network ... secondary`` and its indented lines, ``class``) or a VRF's
excluded range in ``unmodeled``, whole.

Nothing here contacts a device or writes a file.
"""

import copy
import ipaddress

from modules.nsot.features import (DictOf, ListOf, body_lines, compact, complete, dotted,
                                   reproduces, token, _scalar)

# ── the schema ───────────────────────────────────────────────────────────────

#: One range the server never offers (``high`` empty: the one address ``low``).
EXCLUDED = {"low": "", "high": ""}
#: A lease: days, then hours, then minutes, each written only with the one before it; or
#: ``infinite``. All empty: the device's default, one day (the guide).
LEASE = {"days": "", "hours": "", "minutes": "", "infinite": False}
#: One pool: its network is a prefix (``192.0.2.0/24``), written out as IOS's address and mask.
POOL = {"name": "", "network": "", "default_router": ListOf(), "dns_servers": ListOf(),
        "domain_name": "", "lease": DictOf(LEASE)}
#: The pool's lines the pack does not model, verbatim and in order.
RAW_POOL = {"raw": ListOf()}
SERVER = {"excluded": ListOf(EXCLUDED), "pools": ListOf()}
#: The names only this pack's macros read: a template closure naming none of them is a library
#: from before the pack (`features.for_library`).
MARKERS = frozenset({"dhcp_server"})
#: "up to eight IP addresses in one command line" (the guide, `default-router`, `dns-server`).
MAX_ADDRESSES = 8
NOT_V6 = ("an IPv6 address: this pack serves IOS's DHCPv4 server only; DHCPv6 (`ipv6 dhcp "
          "pool`) is not covered, and its lines stay as they are in `unmodeled`")


def complete_pool(pool: dict) -> dict:
    """*pool* with every field present, and its network written out for the partial
    (``network_address``, ``network_mask``; empty when the network is unset or unreadable,
    which `problems` refuses before any render)."""
    out = complete(pool, {**POOL, **RAW_POOL})
    out["network_address"], out["network_mask"] = "", ""
    net = _network(out["network"])
    if net is not None:
        out["network_address"], out["network_mask"] = str(net.network_address), str(net.netmask)
    return out


def complete_server(server: dict) -> dict:
    out = dict(server or {})
    out["excluded"] = [complete(e, EXCLUDED) for e in server.get("excluded") or []
                       if isinstance(e, dict)]
    out["pools"] = [complete_pool(p) for p in server.get("pools") or [] if isinstance(p, dict)]
    return out


def structured(host_vars: dict) -> bool:
    d = host_vars.get("dhcp_server") if isinstance(host_vars, dict) else None
    return isinstance(d, dict) and bool(d.get("excluded") or d.get("pools"))


def _network(value):
    text = _scalar(value)
    if "/" not in text:
        return None
    try:
        return ipaddress.IPv4Network(text)
    except ValueError:
        return None


# ── parsing ──────────────────────────────────────────────────────────────────

def _addresses(words):
    return list(words) if 1 <= len(words) <= MAX_ADDRESSES else None


def _pool_fact(line: str):
    w = line.split()
    if not w:
        return None
    if w[0] == "network" and len(w) == 3:
        try:
            return {"network": str(ipaddress.IPv4Network(f"{w[1]}/{w[2]}"))}
        except ValueError:
            return None
    if w[0] == "default-router":
        found = _addresses(w[1:])
        return {"default_router": found} if found else None
    if w[0] == "dns-server":
        found = _addresses(w[1:])
        return {"dns_servers": found} if found else None
    if w[0] == "domain-name" and len(w) == 2:
        return {"domain_name": w[1]}
    if w[0] == "lease":
        if w[1:] == ["infinite"]:
            return {"lease": {"infinite": True}}
        if 1 <= len(w) - 1 <= 3 and all(x.isdigit() for x in w[1:]):
            return {"lease": dict(zip(("days", "hours", "minutes"), w[1:]))}
    return None


def claim_pool(name: str, children: list, platform: str):
    """``ip dhcp pool <name>``'s body as the pack's fields, every line it does not model or
    cannot reproduce kept in ``raw``, in order; None (the block stays in `unmodeled`, whole)
    when the name is not one word or the body holds a submode (a line indented deeper than
    the pool's own, as a ``network ... secondary`` subnet's are)."""
    if not token(name):
        return None
    lines = []
    for raw in children:
        stripped = raw.strip()
        if not stripped:
            continue
        if len(raw) - len(raw.lstrip(" ")) > 1:
            return None
        lines.append(stripped)
    entry = {"name": name}
    extras = []
    for line in lines:
        fact = _pool_fact(line)
        ok = (fact is not None
              and not pool_problems({"name": name, **fact}, (), cross=False)
              and reproduces(platform, "dhcp_pool_body", (complete_pool(fact),), line)
              and not any(k in entry for k in fact))
        if ok:
            entry.update(fact)
        else:
            extras.append(line)
    if pool_problems(entry, (), cross=True):
        # The lines together break a rule each passes alone: model none of them.
        entry, extras = {"name": name}, list(lines)
    out = compact(complete(entry, POOL), POOL, keep=("name",))
    out["raw"] = extras
    return out


def claim_excluded(text: str, platform: str):
    """``ip dhcp excluded-address <text>`` as a range; None (the line stays in `unmodeled`)
    for any other shape, a VRF's among them."""
    w = text.split()
    if not 1 <= len(w) <= 2:
        return None
    fact = {"low": w[0], "high": w[1] if len(w) == 2 else ""}
    if excluded_problems(fact, ()):
        return None
    if not reproduces(platform, "dhcp_excluded", (fact,), f"ip dhcp excluded-address {text}"):
        return None
    return compact(fact, EXCLUDED, keep=("low",))


# ── the readers' and the old library's view ─────────────────────────────────

def lines_view(host_vars: dict, platform: str) -> dict:
    """*host_vars* with `dhcp_server` written as the lines the shipped partial renders for it,
    moved to the end of ``unmodeled`` (where intent held them before the pack), which a
    library from before the pack emits verbatim. Raises when the partial cannot render it."""
    if not structured(host_vars):
        return host_vars
    out = copy.deepcopy(host_vars)
    server = complete_server(out.pop("dhcp_server"))
    blocks = []
    for e in server["excluded"]:
        line, = body_lines(platform, "dhcp_excluded", e)
        blocks.append({"line": line, "children": [], "lineno": 0})
    for p in server["pools"]:
        children = body_lines(platform, "dhcp_pool_body", p) + list(p["raw"])
        blocks.append({"line": f"ip dhcp pool {p['name']}",
                       "children": [" " + c for c in children], "lineno": 0})
    out["unmodeled"] = list(out.get("unmodeled") or []) + blocks
    return out


def settle(host_vars: dict, platform: str) -> dict:
    """A parse's pack element refused only beside another (none can be today: `claim_pool`
    judges a pool whole) goes back to its lines, verbatim, in ``unmodeled``. Changed in place."""
    found = problems(host_vars)
    if not found:
        return host_vars
    server = host_vars["dhcp_server"]
    refused = {p[1:3] for p, _k, _m in found if len(p) >= 3}
    back = []
    for i, e in enumerate(server.get("excluded") or []):
        if ("excluded", i) in refused:
            back.append({"line": "ip dhcp excluded-address " + " ".join(
                _scalar(e.get(k)) for k in ("low", "high") if _scalar(e.get(k))),
                "children": [], "lineno": 0})
    for i, p in enumerate(server.get("pools") or []):
        if ("pools", i) in refused:
            back.append({"line": f"ip dhcp pool {_scalar(p.get('name'))}",
                         "children": [" " + l for l in _pool_lines(p)], "lineno": 0})
    server["excluded"] = [e for i, e in enumerate(server.get("excluded") or [])
                          if ("excluded", i) not in refused]
    server["pools"] = [p for i, p in enumerate(server.get("pools") or [])
                       if ("pools", i) not in refused]
    host_vars.setdefault("unmodeled", []).extend(back)
    return host_vars


def _pool_lines(pool: dict) -> list:
    """A refused pool's own lines, as IOS words, without the partial's checks."""
    out = []
    net = _network(pool.get("network"))
    if net is not None:
        out.append(f"network {net.network_address} {net.netmask}")
    for key, word in (("default_router", "default-router"), ("dns_servers", "dns-server")):
        if pool.get(key):
            out.append(f"{word} " + " ".join(_scalar(a) for a in pool[key]))
    if pool.get("domain_name"):
        out.append(f"domain-name {pool['domain_name']}")
    lease = pool.get("lease") or {}
    if lease.get("infinite"):
        out.append("lease infinite")
    elif _scalar(lease.get("days")):
        out.append("lease " + " ".join(_scalar(lease.get(k)) for k in ("days", "hours",
                                                                        "minutes")
                                       if _scalar(lease.get(k))))
    return out + list(pool.get("raw") or [])


# ── the checks ───────────────────────────────────────────────────────────────

def _bad(path, key, value, rule) -> tuple:
    return (path, key, f"{dotted(path, key)} is {value!r}: {rule}")


def _v4_problem(value):
    """Why *value* is not an IPv4 address, or None."""
    text = _scalar(value)
    try:
        ipaddress.IPv4Address(text)
        return None
    except ValueError:
        pass
    try:
        ipaddress.IPv6Address(text.split("/")[0])
        return NOT_V6
    except ValueError:
        return "an IPv4 address, such as 192.0.2.1"


def excluded_problems(e: dict, path: tuple) -> list:
    found = []
    for key in ("low", "high"):
        value = e.get(key)
        if key == "high" and _scalar(value) == "":
            continue
        why = _v4_problem(value)
        if why and key == "low" and _scalar(value) == "":
            why = "a range's first address is required (an IPv4 address, such as 192.0.2.1)"
        if why:
            found.append(_bad(path, key, value, why))
    if not found and _scalar(e.get("high")):
        low, high = (ipaddress.IPv4Address(_scalar(e[k])) for k in ("low", "high"))
        if high < low:
            found.append(_bad(path, "high", e.get("high"),
                              f"a range runs from low to high, and low is {e.get('low')!r}"))
    return found


def _address_list(pool: dict, path: tuple, key: str, net) -> list:
    value = pool.get(key)
    if value in (None, []):
        return []
    if not isinstance(value, list):
        return [_bad(path, key, value, "a list of IPv4 addresses, in order of preference "
                                      "(RFC 2132)")]
    found = []
    if len(value) > MAX_ADDRESSES:
        found.append(_bad(path, key, value, f"IOS takes at most {MAX_ADDRESSES} in one pool "
                                            "(Cisco's DHCP server guide), and this is "
                                            f"{len(value)}"))
    for i, a in enumerate(value):
        why = _v4_problem(a)
        if why:
            found.append(_bad(path + (key,), i, a, why))
        elif key == "default_router" and net is not None:
            addr = ipaddress.IPv4Address(_scalar(a))
            if addr not in net:
                found.append(_bad(path + (key,), i, a,
                                  f"a router is on the client's subnet (RFC 2132, 3.5), and "
                                  f"this pool's network is {net}"))
            elif net.prefixlen <= 30 and addr in (net.network_address, net.broadcast_address):
                which = "network" if addr == net.network_address else "broadcast"
                found.append(_bad(path + (key,), i, a,
                                  f"it is {net}'s own {which} address, which no router "
                                  "holds"))
    return found


def _lease_problems(lease, path: tuple) -> list:
    if lease in (None, {}):
        return []
    if not isinstance(lease, dict):
        return [_bad(path, "lease", lease, "a mapping: days, hours, minutes, or infinite")]
    where = path + ("lease",)
    found = []
    nums = {k: _scalar(lease.get(k)) for k in ("days", "hours", "minutes")}
    if lease.get("infinite") not in (None, True, False):
        found.append(_bad(where, "infinite", lease.get("infinite"), "it is true or false"))
    if lease.get("infinite") is True and any(nums.values()):
        found.append(_bad(where, "infinite", True, f"an infinite lease has no length, and "
                                                   f"this one also says {nums}"))
    for key, high in (("days", None), ("hours", 23), ("minutes", 59)):
        text = nums[key]
        if text and not (text.isdigit() and (high is None or int(text) <= high)):
            found.append(_bad(where, key, lease.get(key),
                              "a whole number" + (f" from 0 to {high}" if high else "")))
    for key, before in (("hours", "days"), ("minutes", "hours")):
        if nums[key] and not nums[before]:
            found.append(_bad(where, key, lease.get(key),
                              f"IOS's lease is `days [hours [minutes]]`, so {key} needs "
                              f"{before}, which is not set"))
    return found


def pool_problems(pool: dict, path: tuple, cross: bool = True) -> list:
    """What the pack refuses in one pool; *cross* False leaves out the rules between fields (a
    parser judges one line at a time)."""
    found = []
    if not token(pool.get("name")):
        found.append(_bad(path, "name", pool.get("name"), "a pool is named, in one word"))
    net = None
    text = _scalar(pool.get("network"))
    if text:
        if _v4_problem(text.split("/")[0]) == NOT_V6:
            found.append(_bad(path, "network", pool.get("network"), NOT_V6))
        elif "/" not in text:
            found.append(_bad(path, "network", pool.get("network"),
                              "a network is written with its length, such as 192.0.2.0/24"))
        else:
            try:
                net = ipaddress.IPv4Network(text)
            except ValueError:
                try:
                    loose = ipaddress.IPv4Network(text, strict=False)
                    found.append(_bad(path, "network", pool.get("network"),
                                      f"it has host bits set; the network is {loose}"))
                except ValueError:
                    found.append(_bad(path, "network", pool.get("network"),
                                      "a network is an IPv4 prefix, such as 192.0.2.0/24"))
    found += _address_list(pool, path, "default_router", net if cross else None)
    found += _address_list(pool, path, "dns_servers", None)
    if _scalar(pool.get("domain_name")) and not token(pool.get("domain_name")):
        found.append(_bad(path, "domain_name", pool.get("domain_name"), "one word"))
    found += _lease_problems(pool.get("lease"), path)
    raw = pool.get("raw")
    if raw is not None and not (isinstance(raw, list)
                                and all(isinstance(l, str) and "\n" not in l for l in raw)):
        found.append(_bad(path, "raw", raw, "a list of the pool's other lines, one each"))
    return found


def problems(hv: dict) -> list:
    """``[(path, key, message)]`` for `dhcp_server`, in document order."""
    d = hv.get("dhcp_server") if isinstance(hv, dict) else None
    if d in (None, {}):
        return []
    path = ("dhcp_server",)
    if not isinstance(d, dict):
        return [_bad((), "dhcp_server", d, "a mapping: excluded, pools")]
    found = []
    for key in ("excluded", "pools"):
        if d.get(key) is not None and not isinstance(d.get(key), list):
            found.append(_bad(path, key, d.get(key), "a list"))
    for i, e in enumerate(d.get("excluded") if isinstance(d.get("excluded"), list) else []):
        if not isinstance(e, dict):
            found.append(_bad(path + ("excluded",), i, e, "a mapping: low, high"))
        else:
            found += excluded_problems(e, path + ("excluded", i))
    seen = set()
    for i, p in enumerate(d.get("pools") if isinstance(d.get("pools"), list) else []):
        where = path + ("pools", i)
        if not isinstance(p, dict):
            found.append(_bad(path + ("pools",), i, p, "a mapping with a name"))
            continue
        found += pool_problems(p, where)
        name = _scalar(p.get("name"))
        if name and name in seen:
            found.append(_bad(where, "name", p.get("name"),
                              "named twice; IOS holds one pool per name"))
        seen.add(name)
    return found
