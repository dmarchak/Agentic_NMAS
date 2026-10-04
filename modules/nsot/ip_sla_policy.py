"""P.9 (d4), the ADD path: IP SLA probes SUGGESTED from the profile's policy
for devices that have none, reviewed, committed into the devices' own intent,
then sent by a deploy scoped to IP SLA lines (`SCOPE`). Only ADDING: changing
a running operation is the re-create (C290), gated on staged run 9.

The profile holds the POLICY, never addresses (MONITORING_PROFILE.md section
6: a probe targets another device's address, so addresses are the device's
own data):
- `peers`: probe the device's routing peers (the adjacencies its committed
  intent implies, `modules.neighbours`; a BGP peer outside management by its
  address);
- `gateway`: probe its static default route's next hop in the global table
  (a VRF's default, the emulator's `clab-mgmt`, is never a gateway);
- `none`.
With `frequency` (seconds; 60 by default, the operator, 2026-10-01: one
probe every 10 s cost s3 about 12% of its CPU) and `frequency_by_platform`.

**Prefer probing from the routers where the measured path is the same** (the
operator, 2026-10-01). A probe between two devices measures the path between
them from either end. So a switch's path to a managed router is placed ON THE
ROUTER (the router probes the switch's loopback), and a path already measured
by an existing probe, in either direction, is not added again: s3's probe to
r1 and r1's probe to s3 measure the same path.

Every suggestion states where it lives, what path it measures, why it was
placed there, and its expected CPU cost: MEASURED on vIOS only (s3: about 12%
for one probe every 10 s, C93), so a cost on IOS-XE says it is not measured.
"""

import ipaddress
import re

#: The deploy scope that sends only IP SLA lines (`ip sla N` and its body,
#: `ip sla schedule N ...`), the device's own intent held back otherwise.
SCOPE = "ip_sla"
DEFAULT_FREQUENCY = 60
#: The one measurement (C93, the operator's `show processes cpu` on s3,
#: 2026-10-01): one icmp-echo probe every 10 s cost about 12% of a vIOS
#: switch's CPU. Scaled by frequency, a cost per probe is 12 * 10 / f percent.
MEASURED = {"cisco_ios": (12.0, 10)}
SCHEDULE = "life forever start-time now"
_ECHO = re.compile(r"^\s*icmp-echo\s+(\S+)")


def is_ip_sla_line(chain, line: str) -> bool:
    """Is a keyed config line part of an IP SLA operation or its schedule?"""
    head = (list(chain) or [line])[0].strip()
    return bool(re.match(r"^ip sla \d+$", head) or re.match(r"^ip sla schedule \d+ ", head)
                or (not chain and re.match(r"^ip sla (\d+|schedule \d+ )", line.strip())))


def is_switch(dev: dict) -> tuple:
    """``(bool, basis)``: the inventory's role decides; with none, the
    platform (vIOS-L2 is this fleet's switch platform), said as such."""
    role = (dev.get("role") or "").strip().lower()
    if role:
        return role == "switch", f"its role, {role}"
    plat = (dev.get("platform") or "").strip()
    return plat == "cisco_ios", f"no role recorded; its platform, {plat or 'unknown'}"


def router_address(hv: dict) -> str:
    """The device's identity address, what the fleet's probes target: its
    Loopback0's IPv4 address, else its OSPF router-id."""
    for iface in (hv or {}).get("interfaces") or []:
        if iface.get("name") == "Loopback0":
            parts = (iface.get("ipv4") or "").split()
            if parts and parts[0] != "dhcp":
                return parts[0]
    from modules.neighbours import router_id
    return router_id(hv or {})


def existing_probes(intents: dict) -> list:
    """``[(prober, id, target address)]`` for every icmp-echo operation in
    the fleet's committed intent."""
    out = []
    for host, hv in intents.items():
        for op in (hv or {}).get("ip_sla") or []:
            for line in op.get("settings") or []:
                m = _ECHO.match(line)
                if m:
                    out.append((host, str(op.get("id")), m.group(1)))
    return out


def gateway(hv: dict) -> str:
    """The global table's static default route's next hop, or ""."""
    for r in (hv or {}).get("static_routes") or []:
        spec = (r.get("spec") or "").split()
        if r.get("family") == "ipv4" and spec[:2] == ["0.0.0.0", "0.0.0.0"] and len(spec) >= 3:
            try:
                ipaddress.ip_address(spec[2])
                return spec[2]
            except ValueError:
                continue
    return ""


def _owner(addr: str, intents: dict) -> str:
    from modules.neighbours import addresses
    try:
        return addresses(intents).get(ipaddress.ip_address(addr), "")
    except ValueError:
        return ""


def targets(intents: dict, host: str, policy: str) -> tuple:
    """``([(target device or "", address, network)], why)`` the policy names
    for *host*. With `peers`, ONE per network the device shares with a peer:
    on a shared segment every peer measures the same path, so one probe
    covers it (the operator's load rule, 2026-10-01)."""
    hv = intents.get(host) or {}
    if policy == "gateway":
        gw = gateway(hv)
        if not gw:
            return [], ("no static default route in its committed intent's global table (its default "
                        "is learned, or it has none), so the gateway policy names no target")
        owner = _owner(gw, intents)
        return [(owner, router_address(intents[owner]) if owner else gw, "gateway")], ""
    if policy == "peers":
        from modules.neighbours import expected
        by_net = {}
        for e in expected(intents, host):
            if e.get("proto") == "ospfv3":
                continue                      # the same peers as OSPF, over IPv6
            net = e.get("network") or e.get("address") or ""
            by_net.setdefault(net, []).append(e)
        out = []
        for net, rows in sorted(by_net.items()):
            managed = [r for r in rows if r.get("peer")]
            if managed:
                out.append(("@choose", [r["peer"] for r in managed], net))
            else:
                out.append(("", rows[0].get("address", ""), net))
        if out:
            return out, ""
        if ((hv.get("routing") or {}).get("rip")):
            return [], ("it runs RIP, whose peers this policy does not read (only OSPF and BGP "
                        "adjacencies): choose its targets by hand")
        return [], "its committed intent implies no routing peer"
    return [], "the profile's IP SLA policy is to probe nothing"


def frequency_for(section: dict, platform: str) -> int:
    by = (section or {}).get("frequency_by_platform") or {}
    f = by.get(platform, (section or {}).get("frequency", DEFAULT_FREQUENCY))
    return int(f)


def cost_words(platform: str, frequency: int, probes: int = 1) -> str:
    m = MEASURED.get(platform)
    if not m:
        return (f"not measured on {platform or 'this platform'}: the one measurement is a vIOS "
                "switch's (about 12% of its CPU for one probe every 10 s)")
    pct, at = m
    est = pct * at / frequency * probes
    return (f"about {est:.1f}% of its CPU for {probes} probe(s) every {frequency} s (measured on "
            f"s3: about {pct:g}% for one probe every {at} s, scaled by frequency)")


def operation(platform: str, op_id: int, target: str, source: str, frequency: int) -> dict:
    """One operation in the parsers' `ip_sla` shape, in the platform's own
    form: IOS-XE nests `frequency` under `icmp-echo` (r1's golden), vIOS does
    not (s3's)."""
    echo = f" icmp-echo {target}" + (f" source-interface {source}" if source else "")
    freq = ("  " if platform == "cisco_iosxe" else " ") + f"frequency {frequency}"
    return {"id": str(op_id), "settings": [echo, freq]}


def _has_loopback(hv: dict) -> bool:
    return any(i.get("name") == "Loopback0" for i in (hv or {}).get("interfaces") or [])


def suggest(intents: dict, devices: dict, section: dict, chosen: list) -> dict:
    """``{"suggestions": [...], "skipped": [{device, why}]}`` for the *chosen*
    devices. *devices* is ``{hostname: inventory row}``. Each suggestion:
    ``{on, platform, op, schedule, target, target_device, measures, why,
    cost}``. Deterministic, computed from committed intent only."""
    policy = (section or {}).get("policy") or "none"
    probes = existing_probes(intents)
    from modules.neighbours import expected
    paths, nets_of, load = {}, {}, {}
    for prober, op_id, addr in probes:
        load[prober] = load.get(prober, 0) + 1
        other = _owner(addr, intents) or addr
        key = frozenset((prober, other))
        paths[key] = f"{prober}'s ip sla {op_id}"
        # The network an existing probe measures: the one its two ends share
        # (so a probe already on a segment covers that segment).
        shared = [e.get("network") for e in expected(intents, prober)
                  if e.get("peer") == other and e.get("proto") == "ospf"]
        if shared:
            nets_of[key] = shared[0]
    next_id = {}

    def take_id(host):
        if host not in next_id:
            ids = [int(o.get("id")) for o in (intents.get(host) or {}).get("ip_sla") or []
                   if str(o.get("id", "")).isdigit()]
            next_id[host] = (max(ids) + 1) if ids else 1
        n = next_id[host]
        next_id[host] += 1
        return n

    out, skipped = [], []
    for host in chosen:
        if host not in intents:
            skipped.append({"device": host, "why": f"{host} has no committed intent"})
            continue
        found, why = targets(intents, host, policy)
        if not found:
            skipped.append({"device": host, "why": why})
            continue
        switch, basis = is_switch(devices.get(host) or {})
        for target_dev, addr, net in found:
            if target_dev == "@choose":
                # One probe for the shared network, from a router where one is
                # there (the same path, sparing the switch), the one with the
                # fewest probes, then by name.
                peers = sorted(addr, key=lambda p: (is_switch(devices.get(p) or {})[0],
                                                    load.get(p, 0), p))
                target_dev, addr = peers[0], router_address(intents.get(peers[0]) or {})
            key = frozenset((host, target_dev or addr))
            if key in paths:
                skipped.append({"device": host, "why": (
                    f"its path to {target_dev or addr} is already measured by {paths[key]}, "
                    "from one end or the other")})
                continue
            same_net = next((v for k, v in paths.items()
                             if host in k and nets_of.get(k) == net), None)
            if same_net:
                skipped.append({"device": host, "why": (
                    f"{net} is already measured from {host} by {same_net}: on a shared segment "
                    "one probe covers it")})
                continue
            target_switch = is_switch(devices.get(target_dev) or {})[0] if target_dev else True
            if switch and target_dev and not target_switch and target_dev in intents:
                on, aim = target_dev, router_address(intents[host])
                why_here = (f"{host} is a switch ({basis}) and {target_dev} a router: the same path is "
                            f"measured from {target_dev}, sparing the switch's CPU")
                measured_to = host
            else:
                on, aim, measured_to = host, addr, target_dev or addr
                why_here = f"{host} probes it itself ({basis})"
            if not aim:
                skipped.append({"device": host, "why": f"no address to probe for {target_dev}"})
                continue
            platform = (devices.get(on) or {}).get("platform") or ""
            f = frequency_for(section, platform)
            op = operation(platform, take_id(on), aim,
                           "Loopback0" if _has_loopback(intents.get(on)) else "", f)
            paths[key] = f"the suggested ip sla {op['id']} on {on}"
            nets_of[key] = net
            load[on] = load.get(on, 0) + 1
            out.append({"on": on, "platform": platform, "op": op,
                        "schedule": f"{op['id']} {SCHEDULE}", "target": aim,
                        "target_device": measured_to, "measures": f"{on} ↔ {measured_to}",
                        "why": why_here, "frequency": f, "cost": cost_words(platform, f)})
    per = {}
    for s in out:
        per.setdefault(s["on"], []).append(s)
    totals = {on: cost_words(rows[0]["platform"], rows[0]["frequency"], len(rows))
              for on, rows in per.items()}
    return {"policy": policy, "suggestions": out, "skipped": skipped, "cost_by_device": totals}


def scoped(intended: str, captured: str, policy_words: str = "") -> dict:
    """The deploy scoped to IP SLA (`SCOPE`): the intended config less every
    line the device lacks that is NOT an IP SLA operation or schedule, so the
    program sends only the probes intent adds (merge-only; a changed running
    operation is the re-create, C290). The groups in the profile scope's shape,
    for the same preview: ``by_section`` (`ip_sla`), ``to_send``, ``in_place``
    (IP SLA lines already on the device), ``held_back`` (everything else intent
    would add, NOT sent), ``sources``, ``superseded`` (none)."""
    from modules.nsot.profile_apply import _keyed

    eff = _keyed(intended)
    have = set(_keyed(captured))
    sla = [k for k in eff if is_ip_sla_line(*k)]
    held = [k for k in eff if k not in have and not is_ip_sla_line(*k)]
    held_keys = set(held)
    text = "\n".join(line for (chain, line) in eff if (chain, line) not in held_keys)

    def rows(keys):
        return [{"chain": list(c), "line": l} for c, l in keys]

    send = [k for k in sla if k not in have]
    return {"config": text + "\n", "to_send": rows(send), "in_place": rows(k for k in sla if k in have),
            "held_back": rows(held), "by_section": {"ip_sla": rows(send)},
            "sources": {"ip_sla": policy_words}, "superseded": []}


# ---------------------------------------------------------------------------
# The operations: set the policy, plan the probes, commit them into intent.
# ---------------------------------------------------------------------------

POLICY_WORDS = {"peers": "probe each device's routing peers, one probe per shared network",
                "gateway": "probe each device's static default gateway",
                "none": "probe nothing"}


class Refused(Exception):
    """Nothing written; the message names why."""


def _hash(obj) -> str:
    import hashlib
    import json
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def policy_view(ref) -> dict:
    """``{"committed", "section", "words", "hash", "error"}``: the profile's IP
    SLA section as committed (absent: no policy), and the hash of the whole
    profile a policy change is bound to."""
    from modules.nsot import profile as _p
    try:
        doc = _p.read_committed(ref.repo_dir)
    except Exception as exc:                         # noqa: BLE001
        return {"committed": False, "section": {}, "words": "", "hash": "",
                "error": f"the profile cannot be read ({exc})"}
    sec = ((doc or {}).get("sections") or {}).get("ip_sla") or {}
    words = ""
    if sec.get("policy"):
        words = (f"{POLICY_WORDS.get(sec['policy'], sec['policy'])}, every "
                 f"{frequency_for(sec, '')} s")
    return {"committed": bool(doc), "section": sec, "words": words, "hash": _hash(doc or {}),
            "error": ""}


def set_policy(ref, policy: str, frequency: int, actor: str, profile_hash: str) -> dict:
    """Commit the profile with its IP SLA section set to *policy* every
    *frequency* seconds (one commit, `Source: profile`). Refuses a profile
    that moved since it was read, and a network with no profile. Recompute to commit under
    the repository's lock (CONCURRENCY_AUDIT R15)."""
    from modules.nsot.repo import repo_lock
    with repo_lock(ref.repo_dir):
        return _set_policy_locked(ref, policy, frequency, actor, profile_hash)


def _set_policy_locked(ref, policy: str, frequency: int, actor: str, profile_hash: str) -> dict:
    from modules.nsot import profile as _p
    view = policy_view(ref)
    if view["error"]:
        raise Refused(view["error"])
    if not view["committed"]:
        raise Refused(f"{ref.name} has no monitoring profile yet: propose it first")
    if view["hash"] != profile_hash:
        raise Refused("the profile changed since it was shown: nothing was committed")
    if policy not in _p.IP_SLA_POLICIES:
        raise Refused(f"the policy is one of {', '.join(_p.IP_SLA_POLICIES)}")
    doc = _p.read_committed(ref.repo_dir)
    sec = dict(((doc.get("sections") or {}).get("ip_sla")) or {})
    if sec.get("policy") == policy and frequency_for(sec, "") == frequency:
        return {"outcome": "nothing", "words": view["words"]}
    sec.update(policy=policy, frequency=int(frequency))
    doc.setdefault("sections", {})["ip_sla"] = sec
    try:
        out = _p.commit_profile(ref.name, doc, actor,
                                f"IP SLA policy: {policy}, every {int(frequency)} s")
    except _p.ProfileRefused as exc:
        raise Refused(f"the profile refused it: {exc}") from exc
    if not out.get("ok"):
        raise Refused(f"the commit failed ({out.get('error') or 'no reason given'}): nothing "
                      "changed")
    return {"outcome": "committed", "commit": out.get("commit", ""), "words": policy_view(ref)["words"]}


def _inventory(ref) -> dict:
    """``{hostname: row}`` with each row's dialect: the list's inventory read
    by the reader the deploy plan reads it with (`restore._devices_of`)."""
    from modules.nsot.platform import platform_for_device
    from modules.nsot.restore import _devices_of
    out = {}
    for d in _devices_of(ref.name):
        h = (d.get("hostname") or "").strip()
        if h:
            out[h] = dict(d, platform=platform_for_device(d))
    return out


def without_probes(ref) -> tuple:
    """``(hosts, error)``: the inventory's devices whose COMMITTED intent
    declares no IP SLA operation, in inventory order. The IP SLA page's
    population when it is opened from its tab with no device named; read in
    the two git calls `committed_intents` makes, never per device."""
    from modules.neighbours import committed_intents
    intents, err = committed_intents(ref.repo_dir)
    if err:
        return [], err
    return [h for h in _inventory(ref)
            if h in intents and not (intents[h] or {}).get("ip_sla")], ""


def plan(ref, chosen: list) -> dict:
    """The suggestions for the *chosen* devices from committed intent, with a
    fingerprint the confirm is bound to."""
    from modules.neighbours import committed_intents
    view = policy_view(ref)
    if view["error"]:
        raise Refused(view["error"])
    sec = view["section"]
    if not sec.get("policy"):
        raise Refused("the profile has no IP SLA policy yet: choose one first")
    intents, err = committed_intents(ref.repo_dir)
    if err:
        raise Refused(err)
    out = suggest(intents, _inventory(ref), sec, list(chosen))
    for s in out["suggestions"]:
        s["key"] = f"{s['on']}:{s['op']['id']}"
    out.update(words=view["words"],
               fingerprint=_hash([out["suggestions"], view["hash"]]))
    return out


def apply(ref, chosen: list, picked: list, fingerprint: str, actor: str) -> dict:
    """Commit the picked suggestions (by key) into the devices' own intent in
    ONE commit, recomputing the plan first and refusing one that moved. Returns
    the devices to deploy (scope `ip_sla`). Refuses while host_vars/ holds an
    uncommitted change (the commit would carry it), and a failed commit puts
    every file back as committed (bulk intent's `_put_back`, C106). Recompute to commit under
    the repository's lock (CONCURRENCY_AUDIT R15)."""
    from modules.nsot.repo import repo_lock
    with repo_lock(ref.repo_dir):
        return _apply_locked(ref, chosen, picked, fingerprint, actor)


def _apply_locked(ref, chosen: list, picked: list, fingerprint: str, actor: str) -> dict:
    from modules.nsot import hostvars
    from modules.nsot.bulk_intent import _put_back
    from modules.nsot.repo import git, save_host_vars
    if not actor:
        raise Refused("a commit records who made it, and no actor was given")
    fresh = plan(ref, chosen)
    if fresh["fingerprint"] != fingerprint:
        raise Refused("the suggestions changed since they were shown (intent or the policy "
                      "moved): nothing was committed; preview again")
    take = [s for s in fresh["suggestions"] if s["key"] in set(picked)]
    if not take:
        raise Refused("no suggested probe was ticked: nothing to commit")
    rc, dirty, _err = git(ref.repo_dir, "status", "--porcelain", "--", "host_vars")
    if rc != 0 or dirty.strip():
        raise Refused("host_vars/ has uncommitted changes, which this commit would carry under "
                      "its own name: " + (dirty.strip() or "status failed"))
    by_dev = {}
    for s in take:
        by_dev.setdefault(s["on"], []).append(s)
    written = []
    try:
        for host, rows in by_dev.items():
            hv = hostvars.read_committed(ref.repo_dir, host)
            hv.setdefault("ip_sla", []).extend(s["op"] for s in rows)
            hv.setdefault("ip_sla_schedules", []).extend(s["schedule"] for s in rows)
            hostvars.write_committed(ref.repo_dir, hv)
            written.append(host)
        out = save_host_vars(
            ref.name, sorted(by_dev), actor=actor, source="ip-sla",
            message=("host_vars: add IP SLA probes from the profile's policy: "
                     + "; ".join(f"{s['on']} -> {s['target_device']} ({s['target']}, every "
                                 f"{s['frequency']} s)" for s in take)))
    except Exception:
        _put_back(ref.repo_dir, written)
        raise
    if not out.get("ok"):
        left = _put_back(ref.repo_dir, written)
        raise Refused(f"the commit failed ({out.get('error') or 'no reason given'}): "
                      + (f"LEFT UNCOMMITTED: {', '.join(left)}" if left
                         else "every file was put back as committed, nothing changed"))
    return {"outcome": "committed", "commit": out.get("commit", ""), "devices": sorted(by_dev),
            "added": [{"on": s["on"], "id": s["op"]["id"], "target": s["target"],
                       "measures": s["measures"]} for s in take]}
