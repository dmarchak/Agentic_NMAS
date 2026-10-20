"""modules/dhcp_subnets.py — Kea's subnets as Mercury's (C529 step 5, board C's section 6; the
operator's decision, 2026-10-06: ONE careful host step, once, moves ALL of Kea's hand-written
subnets into Mercury's own files, previewed, Kea's running configuration compared before and
after so nothing a client sees changes; no per-subnet move and no new root helper).

**The move is text in, text out, per family.** Kea's main configuration's ``"subnet4": [ … ]``
(``"subnet6"``) array is moved VERBATIM, its comments, layout and each subnet's
``"reservations": <?include …?>`` (step 2's files, and ZTP's) kept, into Mercury's file
``<Kea's folder>/nmas/subnets4.json`` (``subnets6.json``), and the main file keeps one
``"subnet4": <?include "<that file>"?>`` in its place. Kea resolves a nested include (measured
on the host's kea-dhcp4 2.4.1 before this was relied on), so every subnet's reservations stay in
the files their writers own. Kea's resolved configuration is then the same, which the host step
proves by comparing `config-get` and every lease before and after.

Refused, naming what was found: a ``"subnet4"`` key found other than once, a value that is
not an array, and a ``"shared-networks"`` key (subnets inside one are not moved by this step).
"""

import hashlib
import ipaddress
import json
import logging
import os
import re

log = logging.getLogger(__name__)

FILES = {"IPv4": ("subnet4", "subnets4.json"), "IPv6": ("subnet6", "subnets6.json")}
#: Renew and rebind as shares of each lease's own lifetime (the operator, 2026-10-13, E19:
#: "T1/T2 at 50%/80%"), so Kea computes them (`calculate-tee-times`) for whatever lifetime a
#: lease is given: the pool's, or the `mercury-reserved` class's longer one. Fixed timers would
#: send a 7-day reserved lease back every 2 hours, the pool's renew. IPv6 computes them from
#: the preferred lifetime, IPv4 from the valid one (Kea's rule).
T1_PERCENT, T2_PERCENT = 0.5, 0.8
TIMERS = ("renew-timer", "rebind-timer")


def subnets_file(main: str, family: str) -> str:
    """Mercury's file holding every subnet of *family*, beside Kea's configuration."""
    return os.path.join(os.path.dirname(main), "nmas", FILES[family][1])


def _skip(text: str, i: int) -> int:
    """The index after a string, a comment or an include directive starting at *i*; *i* when
    none starts there."""
    if text.startswith('"', i):
        j = i + 1
        while j < len(text):
            if text[j] == "\\":
                j += 2
                continue
            if text[j] == '"':
                return j + 1
            j += 1
        raise ValueError("a string is not closed")
    if text.startswith("//", i) or text.startswith("#", i):
        j = text.find("\n", i)
        return len(text) if j < 0 else j + 1
    if text.startswith("/*", i):
        j = text.find("*/", i + 2)
        if j < 0:
            raise ValueError("a /* comment is not closed")
        return j + 2
    if text.startswith("<?", i):
        j = text.find("?>", i + 2)
        if j < 0:
            raise ValueError("a <? directive is not closed")
        return j + 2
    return i


def _keys(text: str, key: str) -> list:
    """Where ``"<key>"`` appears as a KEY (followed by a colon) outside comments and other
    strings: ``[(start of the key, index just after its colon)]``."""
    out, i, quoted = [], 0, f'"{key}"'
    while i < len(text):
        j = _skip(text, i)
        if j != i:
            if text.startswith(quoted, i) and j == i + len(quoted):
                k = j
                while k < len(text) and text[k] in " \t\r\n":
                    k += 1
                if k < len(text) and text[k] == ":":
                    out.append((i, k + 1))
            i = j
            continue
        i += 1
    return out


def _array_end(text: str, i: int) -> int:
    """*i* at a ``[``: the index of its matching ``]``."""
    depth = 0
    while i < len(text):
        j = _skip(text, i)
        if j != i:
            i = j
            continue
        c = text[i]
        if c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("an array is not closed")


def move_plan(main_text: str, main: str, family: str) -> dict:
    """The move for one family: ``{"state": "move"|"done"|"refused", "refused", "subnets_text",
    "candidate", "file"}``. *subnets_text* is the array exactly as Kea's file holds it;
    *candidate* is Kea's file with the array replaced by the include of Mercury's file."""
    key, _f = FILES[family]
    path = subnets_file(main, family)
    out = {"state": "refused", "refused": "", "subnets_text": "", "candidate": main_text,
           "file": path}
    try:
        if _keys(main_text, "shared-networks"):
            out["refused"] = (f"{main} has a \"shared-networks\" key: subnets inside a shared "
                              "network are not moved by this step")
            return out
        hits = _keys(main_text, key)
        if len(hits) != 1:
            out["refused"] = f'"{key}" is found {len(hits)} times as a key in {main}; expected once'
            return out
        _k, after = hits[0]
        i = after
        while i < len(main_text) and main_text[i] in " \t\r\n":
            i += 1
        include = f'<?include "{path}"?>'
        if main_text.startswith(include, i):
            out.update(state="done")
            return out
        if not main_text.startswith("[", i):
            out["refused"] = (f'"{key}" in {main} is not an array (it starts '
                              f"{main_text[i:i + 30]!r}); expected [ … ] or the include of "
                              f"{path}")
            return out
        end = _array_end(main_text, i)
    except ValueError as exc:
        out["refused"] = f"{main} could not be read as Kea's configuration: {exc}"
        return out
    out.update(state="move", subnets_text=main_text[i:end + 1] + "\n",
               candidate=main_text[:i] + include + main_text[end + 1:])
    return out


def reservation_files(main_text: str, main: str, family: str, ids: list) -> dict:
    """C529 step 2's question (does every subnet Kea runs take its reservations from Mercury's
    file?) asked of the shape Kea's files have NOW, so its answer stays true after this step:
    before the move, `dhcp_reservations.subnet_files` on Kea's file; after it, Mercury's subnet
    file read as subnets, each one's ``"reservations"`` compared with the include of its own
    file. Same keys as `subnet_files`, plus ``"moved"``; after the move ``"candidate"`` is Kea's
    file unchanged (a subnet is changed on the DHCP page then, never by step 2)."""
    from modules import dhcp_reservations as D

    if move_plan(main_text, main, family)["state"] != "done":
        return dict(D.subnet_files(main_text, main, family, ids), moved=False)
    path = subnets_file(main, family)
    out = {"add": [], "have": [], "refused": "", "candidate": main_text, "moved": True}
    try:
        with open(path, encoding="utf-8") as fh:
            subs = load(fh.read())
    except (OSError, Refused) as exc:
        out["refused"] = f"{path}, which {main} includes, could not be read: {exc}"
        return out
    by_id = {s.get("id"): s for s in subs if isinstance(s, dict)}
    for sid in sorted(ids):
        if sid not in by_id:
            out["refused"] = (f"subnet {sid}, which Kea runs, is not in {path}: Kea's running "
                              "configuration and Mercury's file differ")
            return out
        want = _SENTINEL.format(D.fragment(main, family, sid))
        (out["have"] if by_id[sid].get("reservations") == want else out["add"]).append(sid)
    return out


# =============================================================================================
# Board C: a subnet's pool, options and lease times changed (C529 step 3; `DhcpSubnets.dc.html`
# sections 2 and 3). Preview → confirm by hash as a verified person with a reason → apply holding
# Mercury's subnet file → Kea's own check on a candidate → config-reload → read back (exactly
# this subnet changed) → record (`dhcp/subnets.yml`), restored on any failure after the write.
# =============================================================================================

#: The form's fields per family (board C): Kea's option names and the lease times it sets.
OPTIONS = {"IPv4": {"gateway": "routers", "dns": "domain-name-servers", "domain": "domain-name"},
           "IPv6": {"dns": "dns-servers", "domain": "domain-search"}}
ASKS = ("op", "family", "id", "prefix", "pool", "pool_note", "gateway", "dns", "domain",
         "valid", "preferred", "ack", "ztp")
#: C709: a pool's description, kept in Kea's `user-context` with the pool (Kea carries it and
#: answers it in config-get). Words a person reads, so printable and short.
POOL_NOTE_MAX = 80
#: Measured on the host's kea-dhcp4 2.4.1 (C529, 2026-10-11): a client holding an address the
#: new pool leaves out is answered with silence when it renews or rebinds, so it keeps the
#: address until its lease ends, and is then given one from the pool.
STRANDED_WORDS = ("keeps it until its lease ends {ends} (Kea answers its renewals with silence: "
                  "measured on Kea 2.4.1), then is given an address from the new pool")
STEPS = (
    ("plan", "Plan again", "the subnet file's lock taken; Kea and Mercury's subnet file read "
                           "again, and the hash compared with the preview's"),
    ("test", "Kea's own check", "the candidate subnet file tested with kea-dhcp4 -t or "
                                "kea-dhcp6 -t on a copy of the running configuration"),
    ("write", "Write", "Mercury's subnet file replaced by the tested candidate"),
    ("reload", "Reload", "config-reload through Kea's API; a failure restores the file"),
    ("read-back", "Read back", "Kea's configuration read again: exactly this subnet changed, "
                               "every other subnet and every reservation as before"),
    ("record", "Record", "dhcp/subnets.yml committed as you, with your reason"),
)
RECORD = "dhcp/subnets.yml"
_INCLUDE = re.compile(r'<\?include\s+"([^"]+)"\s*\?>')
_SENTINEL = "@@kea-include:{}@@"


class Refused(Exception):
    pass


def load(text: str) -> list:
    """Mercury's subnet file as subnet dicts: an include directive held as a sentinel string, so
    each subnet keeps its reservation file; comments dropped (Mercury writes the file whole)."""
    plain, i = [], 0
    while i < len(text):
        j = _skip(text, i)
        if j != i:
            chunk = text[i:j]
            if chunk.startswith('"'):
                plain.append(chunk)
            elif chunk.startswith("<?"):
                m = _INCLUDE.match(chunk)
                if not m:
                    raise Refused(f"a directive Mercury does not read: {chunk[:60]!r}")
                plain.append(json.dumps(_SENTINEL.format(m.group(1))))
            i = j
            continue
        plain.append(text[i])
        i += 1
    try:
        value = json.loads("".join(plain))
    except ValueError as exc:
        raise Refused(f"Mercury's subnet file is not a list of subnets: {exc}") from None
    if not isinstance(value, list):
        raise Refused("Mercury's subnet file is not a list of subnets")
    return value


def dump(subnets: list) -> str:
    """The file Mercury writes: the subnets as JSON, each sentinel back as its include."""
    text = json.dumps(subnets, indent=4)
    return re.sub(r'"@@kea-include:([^"@]+)@@"', lambda m: f'<?include "{m.group(1)}"?>',
                  text) + "\n"


def ask(values) -> dict:
    s = {k: (values.get(k) or "").strip() for k in ASKS}
    s["op"] = s["op"] or "edit"
    # C709: the form always sends the description (opened with the pool's own), so what it sends
    # is the whole intended text and empty clears it; a request without the field keeps it.
    if values.get("pool_note") is None:
        s["pool_note"] = None
    return s


def _note_refusal(note: str) -> str:
    """Why *note* cannot be a pool's description, or ""."""
    if len(note) > POOL_NOTE_MAX:
        return f"the pool's description is {len(note)} characters; at most {POOL_NOTE_MAX}"
    if any(not ch.isprintable() for ch in note):
        return "the pool's description holds a character that does not print"
    return ""


def _with_note(pool: dict, note) -> dict:
    """*pool* carrying *note* as its description in `user-context` ("" removes it; None keeps
    whatever it has); any other key of its `user-context` kept."""
    if note is None:
        return pool
    out = dict(pool)
    ctx = {k: v for k, v in (pool.get("user-context") or {}).items() if k != "description"}
    if note:
        ctx["description"] = note
    if ctx:
        out["user-context"] = ctx
    else:
        out.pop("user-context", None)
    return out


def lifetime(text: str, what: str):
    """Seconds from ``86400``, ``1 d``, ``12 h`` or ``30 m``; None when empty; refused by name."""
    text = (text or "").strip().lower()
    if not text:
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(d|h|m|s)?", text)
    if not m:
        raise Refused(f"{what} {text!r} is not a time: write seconds, or a number of d, h or m")
    seconds = int(float(m.group(1)) * {"d": 86400, "h": 3600, "m": 60, "s": 1, None: 1}[m.group(2)])
    if not 60 <= seconds <= 10 * 365 * 86400:
        raise Refused(f"{what} {text!r} is outside one minute to ten years")
    return seconds


def _pool(text: str, prefix: str, family: str) -> tuple:
    """``(start, end)`` of a pool ``a - b`` inside *prefix*; refused naming what is wrong."""
    parts = [p.strip() for p in re.split(r"\s*[-–]\s*", text.strip()) if p.strip()]
    if len(parts) != 2:
        raise Refused(f"the pool {text!r} is not a range: write first - last")
    try:
        a, b = (ipaddress.ip_address(x) for x in parts)
    except ValueError as exc:
        raise Refused(f"the pool {text!r}: {exc}") from None
    net = ipaddress.ip_network(prefix, strict=False)
    if a.version != net.version or a not in net or b not in net:
        raise Refused(f"the pool {text!r} does not lie inside {prefix}")
    if a > b:
        raise Refused(f"the pool {text!r} ends before it starts")
    return a, b


def pool_span(text: str) -> tuple:
    """``(first, last)`` of a pool as Kea writes it: ``a - b``, ``a-b``, or a prefix (Kea's
    `config-get` reports an aligned range as a prefix, ``192.0.2.192/28``, measured 2026-10-11).
    Raises ValueError for anything else."""
    parts = [x.strip() for x in re.split(r"\s*-\s*", text or "") if x.strip()]
    if len(parts) == 2:
        a, b = (ipaddress.ip_address(x) for x in parts)
        return a, b
    if len(parts) == 1 and "/" in parts[0]:
        n = ipaddress.ip_network(parts[0], strict=False)
        return n[0], n[-1]
    raise ValueError(f"{text!r} is not a pool")


def _pools_of(subnet: dict) -> list:
    out = []
    for p in subnet.get("pools") or []:
        try:
            out.append(pool_span(p.get("pool", "")))
        except ValueError:
            continue
    return out


def _set_option(subnet: dict, name: str, data: str, family: str) -> None:
    opts = [o for o in subnet.get("option-data") or [] if o.get("name") != name]
    if data:
        opts.append({"name": name, "data": data,
                     "space": "dhcp4" if family == "IPv4" else "dhcp6"})
    if opts:
        subnet["option-data"] = opts
    else:
        subnet.pop("option-data", None)


def _option_of(subnet: dict, name: str) -> str:
    return next((str(o.get("data", "")) for o in subnet.get("option-data") or []
                 if o.get("name") == name), "")


def plan(list_name: str, values, kea=None, file_text=None, intent=None,
         created_by=None) -> dict:
    """What board C's preview draws, for an edit, an add or a removal: ``{ok, refused, op,
    family, id, prefix, title, change: [(sign, text)], checks: [(state, text)], leases: [str],
    survives: [str], ack: bool, before, after, path, version, hash, subject}``. A read: Kea is
    asked and Mercury's subnet file is read; nothing is written.

    *created_by* (C1460, ``{"device", "list"}``): the onboarding adding a relayed ZTP subnet
    for its link (Add device), recorded in the subnet's `user-context` and so in the hash; never
    a form field, so the DHCP page cannot send it."""
    from modules import dhcp_reservations as D

    s = ask(values)
    p = {"ok": False, "refused": "", "ask": s, "op": s["op"], "family": s["family"],
         "id": None, "prefix": "", "title": "", "change": [], "checks": [], "leases": [],
         "survives": [], "ack": False, "before": None, "after": None, "path": "",
         "version": "", "hash": "", "subject": "", "created_by": dict(created_by or {})}
    steps = {"edit": _plan_edit, "add": _plan_add, "remove": _plan_remove}
    try:
        if s["op"] not in steps:
            raise Refused(f"{s['op']!r} is not edit, add or remove")
        steps[s["op"]](list_name, s, p, kea, file_text, intent, D)
    except (Refused, D.Refused) as exc:
        p["refused"] = str(exc)
        return p
    p["hash"] = hashlib.sha256(json.dumps(
        {k: p[k] for k in ("op", "family", "id", "before", "after", "version", "ack")},
        sort_keys=True).encode("utf-8")).hexdigest()
    p["ok"] = True
    return p


def _state(list_name, s, p, kea, file_text, D) -> tuple:
    """``(subnets, config, kea)``: Mercury's subnet file for the family (refused before the move)
    and Kea's running configuration; *p* gets the path and the file's version."""
    if s["family"] not in FILES:
        raise Refused(f"{s['family']!r} is not IPv4 or IPv6")
    family = s["family"]
    main = D.main_config(list_name, family)
    path = subnets_file(main, family)
    p["path"] = path
    if file_text is None:
        try:
            with open(path, encoding="utf-8") as fh:
                file_text = fh.read()
        except FileNotFoundError:
            raise Refused(f"{path} does not exist: Kea's subnets are still in Kea's own file, "
                          "and the one host step moves them (scripts/host-steps/"
                          "c529-step5-subnet-files.sh)") from None
        except OSError as exc:
            raise Refused(f"{path} could not be read: {exc}") from None
    p["version"] = hashlib.sha256(file_text.encode("utf-8")).hexdigest()[:7]
    if kea is None:
        from modules.integrations.kea import KeaIntegration
        kea = KeaIntegration(list_name=list_name)
    return load(file_text), D.kea_config(kea, family), kea


def _settings(s, after: dict, before: dict, family: str, prefix: str, config: dict, sid,
              intent) -> tuple:
    """The form's pool, options and lifetimes applied to *after*: ``(pool_given, valid)``."""
    note = s.get("pool_note")
    if note is not None and _note_refusal(note):
        raise Refused(_note_refusal(note))
    if s["pool"]:
        a, b = _pool(s["pool"], prefix, family)
        for other in config.get(FILES[family][0]) or []:
            if other.get("id") == sid:
                continue
            for x, y in _pools_of(other):
                if x.version == a.version and not (b < x or a > y):
                    raise Refused(f"the pool {a} - {b} overlaps subnet {other.get('id')}'s pool "
                                  f"{x} - {y}")
        kept = next((str((p.get("user-context") or {}).get("description") or "")
                     for p in before.get("pools") or []
                     if (p.get("user-context") or {}).get("description")), "")
        after["pools"] = [_with_note({"pool": f"{a} - {b}"}, kept if note is None else note)]
    elif note is not None and after.get("pools"):
        # The description alone changed: every piece of the pool carries it (an exclusion may
        # have split the range Kea is told into several).
        after["pools"] = [_with_note(p, note) for p in after["pools"]]
    for field, name in OPTIONS[family].items():
        value = s.get(field, "")
        if not value:
            continue                       # an empty field keeps what Kea's subnet holds
        if field == "gateway":
            try:
                if ipaddress.ip_address(value) not in ipaddress.ip_network(prefix, strict=False):
                    raise Refused(f"the gateway {value} is not in {prefix}")
            except ValueError as exc:
                raise Refused(f"the gateway {value!r}: {exc}") from None
        if field == "dns":
            servers = [x.strip() for x in value.split(",") if x.strip()]
            for x in servers:
                try:
                    ipaddress.ip_address(x)
                except ValueError:
                    raise Refused(f"the DNS server {x!r} is not an address") from None
            value = ", ".join(servers)
        if value != _option_of(before, name):
            _set_option(after, name, value, family)
    valid = lifetime(s["valid"], "the valid lifetime")
    if valid is not None:
        after["valid-lifetime"] = valid
        for timer in TIMERS:
            after.pop(timer, None)
        after.update({"calculate-tee-times": True, "t1-percent": T1_PERCENT,
                      "t2-percent": T2_PERCENT})
    if family == "IPv6":
        preferred = lifetime(s["preferred"], "the preferred lifetime")
        if preferred is not None:
            if valid is not None and preferred > valid:
                raise Refused("the preferred lifetime is longer than the valid one")
            after["preferred-lifetime"] = preferred
    return bool(s["pool"]), valid


def _gateway_check(p, after, prefix, intent) -> None:
    gw = _option_of(after, "routers")
    want = sorted({g for e in ((intent or {}).get("IPv4") or {}).get(prefix) or []
                   for g in e.get("gateway") or []})
    if not want:
        p["checks"].append(("note", "intent names no first-hop address for this prefix, so "
                                    "the gateway is not compared"))
    elif gw in want:
        p["checks"].append(("pass", f"the gateway equals intent's VRRP address ({gw})"))
    else:
        p["checks"].append(("warn", f"the gateway {gw or '(none)'} is not intent's VRRP "
                                    f"address ({', '.join(want)})"))


def _plan_add(list_name, s, p, kea, file_text, intent, D) -> None:
    """Board C's section 4: a new subnet, its relay addresses and gateway from intent."""
    subnets, config, kea = _state(list_name, s, p, kea, file_text, D)
    family = s["family"]
    try:
        net = ipaddress.ip_network(s["prefix"].strip(), strict=True)
    except ValueError as exc:
        raise Refused(f"the prefix {s['prefix']!r}: {exc}") from None
    if (net.version == 4) != (family == "IPv4"):
        raise Refused(f"{net} is not an {family} prefix")
    prefix = str(net)
    p["prefix"] = prefix
    for other in config.get(FILES[family][0]) or []:
        try:
            if ipaddress.ip_network(other.get("subnet", ""), strict=False).overlaps(net):
                raise Refused(f"{prefix} overlaps Kea's subnet {other.get('id')} "
                              f"({other.get('subnet')})")
        except ValueError:
            continue
    if not s["pool"]:
        raise Refused("a new subnet needs its pool: first - last")
    entries = ((intent or {}).get(family) or {}).get(prefix.lower() if family == "IPv6"
                                                       else prefix) or []
    used = {x.get("id") for x in subnets} | {x.get("id") for x in config.get(FILES[family][0])
                                             or []}
    vlan = next((int(m.group(1)) for e in entries
                 for m in [re.match(r"^vlan(\d+)$", e.get("iface", ""), re.I)] if m), None)
    sid = vlan if vlan and vlan not in used else max([i for i in used if isinstance(i, int)]
                                                     or [0]) + 1
    p["id"] = sid
    from modules import dhcp_reservations as Dr
    main = D.main_config(list_name, family)
    after = {"id": sid, "subnet": prefix,
             "reservations": _SENTINEL.format(Dr.fragment(main, family, sid))}
    relay = sorted({e.get("address") for e in entries if e.get("address")})
    if relay:
        after["relay"] = {"ip-addresses": relay}
    for_ztp = s.get("ztp") == "1"
    if for_ztp:
        _declare_for_ztp(p, s, after, family, prefix, entries)
    elif family == "IPv4" and not s["gateway"]:
        gw = sorted({g for e in entries for g in e.get("gateway") or []})
        if len(gw) == 1:
            s = dict(s, gateway=gw[0])
    _settings(s, after, {}, family, prefix, config, sid, intent)
    p["after"] = after
    p["title"] = f"Add {prefix}"
    p["subject"] = f"dhcp: {family} subnet {sid} ({prefix}) added"
    p["change"] = [(" ", f"subnet {sid} ({prefix}), a new reservations file of Mercury's")] + [
        ("+", f"{k}: {json.dumps(v)}") for k, v in after.items() if k != "reservations"]
    where = ", ".join(f"{e['device']} {e['iface']}" for e in entries)
    if not entries:
        p["checks"].append(("warn", "no interface in intent is on this prefix: no relay brings "
                                    "a client's request, so Kea would answer nobody on it"))
    else:
        to = sorted({r for e in entries for r in e.get("relays") or []})
        p["checks"].append(("pass" if to else "warn",
                            f"relayed to {', '.join(to)} by {where} (intent)" if to else
                            f"{where} relay to no DHCP server in intent"))
    p["checks"].append(("pass", f"no Kea subnet overlaps {prefix}; Kea id {sid}"
                        + (f" (its VLAN, {vlan})" if vlan == sid else " (one more than the highest in use)")))
    if family == "IPv4":
        _gateway_check(p, after, prefix, intent)
    p["checks"].append(("pending", f"kea-{'dhcp4' if family == 'IPv4' else 'dhcp6'} -t on the "
                                   "candidate, at confirm; the live file untouched until then"))
    p["leases"].append("no lease is held in a subnet Kea does not have yet")


def _declare_for_ztp(p, s, after, family, prefix, entries) -> None:
    """C1346: a new subnet declared relayed for ZTP (``user-context: {"mercury-ztp":
    "relayed"}``, `ztp_relayed`). Its reservations file is then ZTP's writer's alone, the DHCP
    page refuses reservations there, and D4 holds: no gateway (option 3, which only a
    reservation may carry, as the relay's own address) and no DNS server option. Refused: an
    IPv6 subnet (ZTP is IPv4 only, C1245), and a prefix whose relay is not one interface of a
    device Mercury manages, with a helper target (the relay is read from committed intent)."""
    from modules.nsot import ztp_relayed

    try:
        ztp_relayed.ipv4_only(prefix, "the subnet")
    except ztp_relayed.Refused as exc:
        raise Refused(str(exc)) from None
    if family != "IPv4":
        raise Refused(f"{prefix} is an {family} subnet: ZTP reserves and serves IPv4 (DHCPv4) "
                      "addresses only (C1245)")
    if s.get("gateway") or s.get("dns"):
        raise Refused("a relayed ZTP subnet carries no gateway or DNS option (D4): a "
                      "configless device given a route and a resolver phones Cisco; option 3 "
                      "is a reservation's own choice, as the relay's own address, made at "
                      "Add device")
    try:
        relay = ztp_relayed.relay_for(prefix, {"IPv4": {prefix: entries}})
    except ztp_relayed.Refused as exc:
        raise Refused(str(exc)) from None
    after["relay"] = {"ip-addresses": [relay["address"]]}
    after["user-context"] = ztp_relayed.declaration()
    _match_by_mac(p, after)
    p["checks"].append(("pass", f"for ZTP behind {relay['device']} {relay['iface']} "
                                f"({relay['address']}, its relay); its reservations are "
                                "onboarding's, and it carries no gateway or DNS option (D4)"))
    made = p.get("created_by") or {}
    if made:
        # C1460: the onboarding adding it for its link, so Retire removes it with that device.
        after["user-context"][ztp_relayed.CREATED_BY] = {"device": str(made.get("device", "")),
                                                         "list": str(made.get("list", ""))}
        p["checks"].append(("pass", f"added by {made.get('device')}'s onboarding (Add device, "
                                    f"{made.get('list')}): Retire removes it with that device "
                                    "once nothing else is in it"))


def _match_by_mac(p, after: dict) -> None:
    """C1403: a ZTP subnet matches a lease by the device's MAC, never its client-id
    (`dhcp_lease_identity`, measured on this installation's Kea)."""
    from modules import dhcp_lease_identity as LI

    after[LI.KEY] = LI.WANTED
    p["checks"].append(("pass", f"{LI.KEY} false: a lease is matched by the device's MAC, so "
                                "a device redeployed with a new client-id keeps its address "
                                "(C1403)"))


def _plan_remove(list_name, s, p, kea, file_text, intent, D) -> None:
    """Board C's section 5: refused until its effect on the leases held now is acknowledged."""
    subnets, config, kea = _state(list_name, s, p, kea, file_text, D)
    family = s["family"]
    try:
        sid = int(s["id"])
    except ValueError:
        raise Refused(f"{s['id']!r} is not a Kea subnet id") from None
    p["id"] = sid
    hit = [x for x in subnets if x.get("id") == sid]
    if len(hit) != 1:
        raise Refused(f"subnet {sid} is in Mercury's {family} subnet file {len(hit)} times")
    from modules.nsot import ztp_relayed
    from modules.readers.dhcp import _ztp_ids
    running = next((x for x in config.get(FILES[family][0]) or [] if x.get("id") == sid), {})
    if family == "IPv4" and ztp_relayed.declared(running):
        # C1346: a relayed ZTP subnet goes only when onboarding holds nothing in it.
        held = running.get("reservations") or []
        if held:
            raise Refused(f"subnet {sid} is a relayed ZTP subnet holding {len(held)} "
                          "reservation(s) onboarding wrote: abandon or retire those devices "
                          "first (each removes its own)")
    elif family == "IPv4" and sid in _ztp_ids(config):
        raise Refused(f"subnet {sid} is ZTP's: onboarding's, never removed here")
    before = hit[0]
    p["before"] = before
    prefix = before.get("subnet", "")
    p["prefix"] = prefix
    p["title"] = f"Remove {prefix}"
    p["subject"] = f"dhcp: {family} subnet {sid} ({prefix}) removed"
    p["change"] = [(" ", f"subnet {sid} ({prefix})")] + [
        ("-", f"{k}: {json.dumps(v)}") for k, v in before.items() if k != "reservations"]
    held = [l for l in D.kea_leases(kea, family)
            if l.get("subnet-id") == sid and l.get("state", 0) == 0]
    kept = next((x for x in config.get(FILES[family][0]) or [] if x.get("id") == sid), {})
    res = kept.get("reservations") or []
    ends = max(((l.get("cltt", 0) or 0) + (l.get("valid-lft", 0) or 0) for l in held),
               default=0)
    if held:
        names = sorted({_host(l) or l.get("hw-address") or l.get("duid") or "?"
                        for l in held})
        p["leases"].append(f"{len(held)} active lease(s) ({', '.join(names)}): each client keeps "
                           f"its address until its lease ends (the last {_iso(ends)}), and from "
                           "its next renewal Kea answers it nothing on this subnet")
    else:
        p["leases"].append("no lease is held in this subnet now")
    if res:
        p["leases"].append(f"{len(res)} reservation(s) go with the subnet")
    p["ack"] = bool(held or res)
    p["survives"] = [f"The subnet's definition and its reservations stay in the repository's "
                     f"history (dhcp/subnets.yml, dhcp/reservations.yml); adding it back is "
                     f"one Add. Mercury's reservations file for it stays on disk, included by "
                     f"nothing."]
    p["checks"].append(("pass" if not p["ack"] else "warn",
                        "nothing is served on it now" if not p["ack"] else
                        "its clients lose DHCP service from their next renewal: acknowledged "
                        "at confirm"))
    p["checks"].append(("pending", f"kea-{'dhcp4' if family == 'IPv4' else 'dhcp6'} -t on the "
                                   "candidate, at confirm"))


def _plan_edit(list_name, s, p, kea, file_text, intent, D) -> None:
    subnets, config, kea = _state(list_name, s, p, kea, file_text, D)
    family = s["family"]
    try:
        sid = int(s["id"])
    except ValueError:
        raise Refused(f"{s['id']!r} is not a Kea subnet id") from None
    p["id"] = sid
    hit = [x for x in subnets if x.get("id") == sid]
    if len(hit) != 1:
        raise Refused(f"subnet {sid} is in Mercury's {family} subnet file {len(hit)} times")
    before = hit[0]
    p["before"] = before
    prefix = before.get("subnet", "")
    p["prefix"] = prefix
    from modules.nsot import ztp_relayed
    from modules.readers.dhcp import _ztp_ids
    running = next((x for x in config.get(FILES[family][0]) or [] if x.get("id") == sid), {})
    # C1377: a relayed ZTP subnet is Mercury's to edit (its Add wrote it), held to D4; the
    # directly attached ZTP subnet stays onboarding's. Declared in Kea or in Mercury's file:
    # either one makes D4 apply.
    relayed = family == "IPv4" and (ztp_relayed.declared(running)
                                    or ztp_relayed.declared(before))
    if not relayed and family == "IPv4" and sid in _ztp_ids(config):
        raise Refused(f"subnet {sid} is ZTP's: its posture is onboarding's, changed only where "
                      "onboarding sets it")
    if relayed:
        _d4_form(s, sid, running or before)
    after = json.loads(json.dumps(before))
    # The pool: one range as the form sets it (board D's exclusions shape it later).
    _pool_given, valid = _settings(s, after, before, family, prefix, config, sid, intent)
    if relayed:
        _d4_subnet(after, sid, running or before)
        _match_by_mac(p, after)          # one written before C1403 converges on its next edit
    if after == before:
        raise Refused("nothing would change: the values are those Kea's subnet holds now")
    p["after"] = after
    p["title"] = f"Change {prefix}"
    p["subject"] = f"dhcp: {family} subnet {sid} ({prefix}) changed"
    p["change"] = _change_lines(before, after, sid, prefix)
    # Leases now: who the new pool leaves out, and what a new lifetime touches.
    reserved = {a for r in D.every_reservation(config, family) for a in r["addresses"]}
    pools = _pools_of(after)
    for lease in D.kea_leases(kea, family):
        if lease.get("subnet-id") != sid or lease.get("state", 0) != 0:
            continue
        addr = lease.get("ip-address", "")
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if pools and not any(x <= ip <= y for x, y in pools) and addr not in reserved:
            ends = (lease.get("cltt", 0) or 0) + (lease.get("valid-lft", 0) or 0)
            who = lease.get("hw-address") or lease.get("duid") or "?"
            name = _host(lease)
            p["leases"].append(f"{addr} ({who}{', ' + name if name else ''}) is outside the new "
                               "pool: it " + STRANDED_WORDS.format(ends=_iso(ends)))
    if valid is not None:
        p["leases"].append(f"the new lifetime ({_dur(valid)}) applies to leases granted or "
                           "renewed after the change; leases held now keep theirs until they "
                           "renew")
    if not p["leases"]:
        p["leases"].append("no lease held now is affected")
    # Checks, each a measurement.
    p["checks"].append(("pass", f"the pool lies inside {prefix} and overlaps no other subnet's "
                                "pool" if s["pool"] else "the pool is as Kea holds it"))
    if relayed:
        # D4, not intent's VRRP address: a ZTP subnet carries no gateway at all (C1377).
        p["checks"].append(("pass", "a relayed ZTP subnet: no route or resolver option at the "
                                    "subnet or its pools (D4); its reservations stay "
                                    "onboarding's"))
    elif family == "IPv4":
        _gateway_check(p, after, prefix, intent)
    p["checks"].append(("pending", f"kea-{'dhcp4' if family == 'IPv4' else 'dhcp6'} -t on the "
                                   "candidate, at confirm; the live file untouched until then"))
    p["checks"].append(("pass", f"Mercury's subnet file is the version this preview read "
                                f"({p['version']})"))


def _relay_words(subnet: dict) -> str:
    """The relay's own address Kea matches *subnet* on, for a refusal: D4 restated's only
    option 3 value, and only on a reservation."""
    from modules.nsot import ztp_relayed

    got = ztp_relayed.kea_relay(subnet)
    return ", ".join(got) if got else "none named"


def _d4_option_words(name, value, level: str, sid, subnet: dict) -> str:
    """Why option *name* = *value* at *level* breaks D4 on relayed ZTP subnet *sid*."""
    if name in ("routers", 3):
        return (f"option 3 (routers) {value} at {level}: on relayed ZTP subnet {sid} option 3 "
                f"may be only the relay's own address ({_relay_words(subnet)}), and only on a "
                "reservation that chose it at Add device; at the subnet it would reach every "
                "device there (D4 restated)")
    if name in ("domain-name-servers", 6):
        return (f"option 6 (domain-name-servers) {value} at {level}: a ZTP subnet never sends "
                "a resolver (D4): a configless device given one phones Cisco")
    return (f"option {name} {value} at {level}: a ZTP subnet never sends a route option (D4)")


def _d4_form(s: dict, sid, subnet: dict) -> None:
    """D4 for an edit of a relayed ZTP subnet, on what the form sends: a gateway or a DNS
    server is refused naming the value and what D4 allows, before any other check of it."""
    bad = []
    if s.get("gateway"):
        bad.append(_d4_option_words("routers", s["gateway"], "the subnet", sid, subnet))
    if s.get("dns"):
        bad.append(_d4_option_words("domain-name-servers", s["dns"], "the subnet", sid, subnet))
    if bad:
        raise Refused("D4: " + "; ".join(bad))


def _d4_subnet(after: dict, sid, subnet: dict) -> None:
    """D4 for an edit of a relayed ZTP subnet, on the subnet it would leave: no route or
    resolver option (`ztp.FORBIDDEN_OPTIONS`, by name or code) at the subnet or any pool,
    whoever put it there. Refused naming each, with its value."""
    from modules.nsot import ztp

    names, codes = set(ztp.FORBIDDEN_OPTIONS), set(ztp.FORBIDDEN_OPTIONS.values())
    levels = [("the subnet", after.get("option-data") or [])] + [
        (f"pool {pl.get('pool')}", pl.get("option-data") or []) for pl in after.get("pools") or []]
    bad = [_d4_option_words(o.get("name") or o.get("code"), o.get("data", ""), level, sid,
                            subnet)
           for level, opts in levels for o in opts
           if o.get("name") in names or o.get("code") in codes]
    if bad:
        raise Refused("D4: " + "; ".join(bad))


def _host(lease: dict) -> str:
    """A lease's hostname, or "" when it has none (Kea stores an absent IPv6 FQDN as ".",
    measured on the lab's Kea 2.4.1)."""
    name = (lease.get("hostname") or "").strip()
    return "" if name in ("", ".") else name


def _iso(ts) -> str:
    import time
    try:
        return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(ts)))
    except (TypeError, ValueError, OverflowError):
        return "?"


def _dur(seconds: int) -> str:
    return f"{seconds // 86400} d" if seconds % 86400 == 0 else f"{seconds // 3600} h" \
        if seconds % 3600 == 0 else f"{seconds} s"


def _change_lines(before: dict, after: dict, sid, prefix) -> list:
    """The preview's +/- lines: each key of the subnet that moved, as Kea's file says it."""
    out = [(" ", f"subnet {sid} ({prefix})")]
    for key in sorted(set(before) | set(after)):
        if before.get(key) == after.get(key):
            continue
        for sign, side in (("-", before), ("+", after)):
            if key in side:
                out.append((sign, f"{key}: {json.dumps(side[key])}"))
    return out


def apply_edit(list_name: str, values, confirmed_hash: str, *, actor: str, reason: str,
               kea=None, run_test=None, main_text=None, record=None, intent=None,
               planner=None, created_by=None) -> dict:
    """``{ok, error, outcome, read_back, rolled_back, commit, plan}``: board C's change applied,
    holding Mercury's subnet file from its read to its read-back. *planner* is board D's
    (an exclusion shapes a subnet's pools: the same write, its own record); board C's `plan`
    otherwise. The one write path for Kea's subnets."""
    from modules import dhcp_reservations as D
    from modules.nsot import ztp

    out = {"ok": False, "error": "", "outcome": "", "read_back": "", "rolled_back": "",
           "commit": "", "plan": None}
    if not (reason or "").strip():
        out["error"] = "a reason is recorded with every subnet change; none was given"
        return out
    s = ask(values)
    if s["family"] not in FILES:
        out["error"] = f"{s['family']!r} is not IPv4 or IPv6"
        return out
    family = s["family"]
    f = D.FAMILY[family]
    if kea is None:
        from modules.integrations.kea import KeaIntegration
        kea = KeaIntegration(list_name=list_name)
    main = D.main_config(list_name, family)
    path = subnets_file(main, family)
    with ztp.fragment_lock(path):
        p = (planner or plan)(list_name, values, kea=kea, intent=intent,
                              **({"created_by": created_by} if created_by else {}))
        out["plan"] = p
        if not p["ok"]:
            out["error"] = p["refused"]
            return out
        if p["hash"] != confirmed_hash:
            out["error"] = (f"what the preview showed has changed ({confirmed_hash[:12]} -> "
                            f"{p['hash'][:12]}): Kea or Mercury's subnet file moved since; "
                            "nothing was written. Preview again")
            return out
        if p["ack"] and s["ack"] != "1":
            out["error"] = ("the removal's effect on the clients it serves was not acknowledged: "
                            "nothing was written")
            return out
        with open(path, encoding="utf-8") as fh:
            previous_text = fh.read()
        subnets = load(previous_text)
        if p["op"] == "add":
            candidate = subnets + [p["after"]]
            fresh = p["after"]["reservations"][len("@@kea-include:"):-2]
            if not os.path.exists(fresh):
                ztp._write_file(fresh, "[]\n")                                 # noqa: SLF001
        elif p["op"] == "remove":
            candidate = [x for x in subnets if x.get("id") != p["id"]]
        else:
            candidate = [p["after"] if x.get("id") == p["id"] else x for x in subnets]
        candidate_text = dump(candidate)
        before_cfg = D.kea_config(kea, family)
        if main_text is None:
            with open(main, encoding="utf-8") as fh:
                main_text = fh.read()
        out["at"] = "test"                       # the step reached: dhcp_page.WRITE_STEPS
        run = run_test or (lambda cfg: ztp._run_kea_test(cfg, f["program"]))   # noqa: SLF001
        ok, detail = ztp._config_test(main_text, path, candidate_text, run)    # noqa: SLF001
        if not ok:
            out["error"] = (f"{f['program']} -t refused the candidate: {detail}. Mercury's file "
                            "was not touched")
            return out
        out["at"] = "write"
        ztp._replace(path, candidate_text)                                     # noqa: SLF001

        def restore(why):
            ztp._replace(path, previous_text)                                  # noqa: SLF001
            again = kea.command("config-reload", [f["svc"]])
            out["rolled_back"] = ("Mercury's previous subnet file restored and Kea reloaded"
                                  if again.get("ok") else "Mercury's previous subnet file "
                                  f"restored, and Kea's reload of it FAILED ({again.get('error')})")
            out["error"] = why

        out["at"] = "reload"
        reload = kea.command("config-reload", [f["svc"]])
        if not reload.get("ok"):
            restore(f"config-reload failed ({reload.get('error')}): nothing changed in Kea")
            return out
        out["at"] = "read_back"
        try:
            after_cfg = D.kea_config(kea, family)
        except D.Refused as exc:
            out["error"] = f"written and reloaded, and the read-back failed: {exc}"
            return out
        moved = _moved(before_cfg, after_cfg, family, p["id"], p["op"])
        if moved:
            restore("Kea's running configuration does not hold exactly this change: "
                    + "; ".join(moved))
            return out
        out["read_back"] = ({"remove": f"Kea's running configuration no longer holds subnet "
                                       f"{p['id']}", "add": f"Kea's running configuration holds "
                                       f"the new subnet {p['id']}"}.get(
                                p["op"], f"Kea's running configuration holds subnet {p['id']} "
                                         "as written")
                            + ", and every other subnet and setting as before")
        out["outcome"] = {"add": "added", "remove": "removed"}.get(p["op"], "changed")
        out["at"] = "record"
        rec = (record or record_commit)(list_name, p, actor=actor, reason=reason)
        out["commit"] = rec.get("commit", "")
        if not rec.get("ok"):
            out["error"] = f"written to Kea and read back; the record failed: {rec.get('error')}"
            return out
        out["ok"] = True
        return out


def _moved(before: dict, after: dict, family: str, sid, op: str = "edit") -> list:
    """What moved in Kea's running configuration besides what *op* does to subnet *sid*, in
    words; [] when exactly that happened (an edit changed it, an add brought it, a removal took
    it away) and nothing else moved."""
    key = FILES[family][0]
    out = []
    for k in sorted(set(before) | set(after)):
        if k in (key, "hash"):
            continue
        if before.get(k) != after.get(k):
            out.append(f"Kea's setting {k!r} moved")
    b = {x.get("id"): x for x in before.get(key) or []}
    a = {x.get("id"): x for x in after.get(key) or []}
    want = set(b) | {sid} if op == "add" else set(b) - {sid} if op == "remove" else set(b)
    if set(a) != want:
        out.append(f"the subnets are {sorted(a)} after; expected {sorted(want)}")
    for i in sorted(set(a) & set(b)):
        if i != sid and a[i] != b[i]:
            out.append(f"subnet {i} moved")
    if op == "edit" and sid in a and sid in b and a[sid] == b[sid]:
        out.append(f"subnet {sid} did not change")
    return out


def write_subnets_record(list_name: str, repo: str) -> None:
    """Write `dhcp/subnets.yml` in *repo*: every subnet in Mercury's subnet files, both
    families, as Mercury's files hold them. The caller holds the repository's lock and commits."""
    import yaml

    from modules import dhcp_reservations as D
    from modules.filestore import write_atomic

    doc = {}
    for family in FILES:
        path = subnets_file(D.main_config(list_name, family), family)
        try:
            with open(path, encoding="utf-8") as fh:
                doc[family] = load(fh.read())
        except (OSError, Refused) as exc:
            doc[family] = f"not read: {exc}"
    target = os.path.join(repo, RECORD)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    write_atomic(target, "# Kea's subnets as Mercury's files hold them (C529); written on "
                         "each change.\n" + yaml.safe_dump(doc, sort_keys=False))


def record_commit(list_name: str, p: dict, *, actor: str, reason: str) -> dict:
    """Write `dhcp/subnets.yml` and commit it as *actor*, the reason in its body, in the Kea
    owner's repository (`dhcp_reservations.record_home`, C1181)."""
    from modules import dhcp_reservations as D
    from modules.config import get_list_data_dir
    from modules.list_settings import ListSettingsUnreadable
    from modules.nsot import repo as R

    try:
        owner, extra = D.record_home(list_name)
    except ListSettingsUnreadable as exc:
        return {"ok": False, "error": f"whose Kea this is could not be read: {exc}"}
    repo = os.path.join(get_list_data_dir(owner), "config_repo")
    with R.repo_lock(repo):
        write_subnets_record(owner, repo)
        subject = p.get("subject") or "dhcp: subnet changed"
        return R._commit_paths(owner, [RECORD], f"{subject}\n\n{reason.strip()}",  # noqa: SLF001
                               [f"Actor: {actor}", *extra], "dhcp")
