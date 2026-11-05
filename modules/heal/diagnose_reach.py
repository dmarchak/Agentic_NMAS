"""The "A can't reach B" runbook (board H amendment item 1, part H15; docs/HEAL_TO_INTENT.md
19.3), on the path trace (`modules/path_trace.py`) and the diagnosis engine
(`modules/heal/diagnose.py`): read-only and deterministic, every read through the one reads
engine as kind ``diagnosis``, held, masked, capped and recorded on History › Reads.

**What it does, in order** (`STEPS`):
1. **reach:** A pings B, from A's loopback when intent gives A one (so the return path has one
   address to follow back). The ping has no real capture yet (C2414), so it is sent, History
   holds its masked answer, and its step says it was read and not interpreted: the path is
   followed whatever it answered.
2. **trace:** the path is followed with the path trace's own hop-by-hop `show ip cef <B>`
   (`path_trace.trace`), each level's devices read concurrently, each device held for this
   diagnosis as the trace reaches it (one in another diagnosis is not read, by name).
3. **hop:** each routed hop, in order (the branches that stop first, then those that leave the
   network, then those delivered; each hop once): the egress interface's state and error
   counters (read twice, `diagnose.DELTA_SECONDS` apart), its IPv4 address and the access
   lists it binds, the next hop's ARP entry, the route toward B (sent, not yet interpreted),
   and the next hop's ingress interface on the device that holds it; an access list a hop
   binds has its counters read (sent, not yet interpreted). **It stops at the first hop that
   diverges**, and says the hops after it were not checked, never implies it.
4. **traceroute:** when the path leaves the network toward an address no managed device holds,
   A's traceroute to B is sent for the hops past the managed devices (not yet interpreted).
5. **return:** when the forward path holds at every hop and B is a managed device's, the path
   from B's device back to A's address is followed. A missing return route is the divergence.
6. logs, compare, rank and record: as the adjacency runbook's (`diagnose._judge`, `rank`,
   the step log's ``diagnosis`` row), with this runbook's rule table (`PATH_RULES`).

**"Diverges from intent," at each hop.** The comparison is with committed intent: which device
holds B and each next hop (an address two devices hold names neither, as the path trace's
`owners` does), each interface's intended admin state, and the access lists it binds. Where a
read has no parser yet it is never guessed: a rule that needed it says its evidence is
incomplete, naming the read.

**IPv4 now; the IPv6 form waits for a capture.** The path trace reads IPv4 forwarding only, and
`show ipv6 cef` has no real capture to write its parser against (C2414, C2415). An IPv6 B is
refused by name, nothing read, never followed as something else.

**Not yet built (H15's later part):** the route's source against intent (`show ip route <B>`
is read and not interpreted until captured), a switch between two routed hops (where the next
hop's MAC is learned, and that port's spanning-tree state), and the return path's own per-hop
checks.

**Its bounds:** `diagnose.MAX_COMMANDS` (70) per diagnosis and `diagnose.MAX_PER_DEVICE` (14)
per device, counted before each read; `PER_HOP` reads a hop and `FIXED` besides, so the cap
covers `HOPS_AT_CAP` hops (19.3: 9). A run reaching the cap stops and says after which hop.
"""

import ipaddress
import logging

from modules import path_trace
from modules.heal import diagnose as D

log = logging.getLogger(__name__)

RUNBOOK = "cant_reach"
#: The runbook's steps, in order, as the manual names them (H16's how-it-works page).
STEPS = ("plan", "hold", "reach", "trace", "hop", "read again", "traceroute", "return", "logs",
         "compare", "rank", "record")
#: A routed hop's reads (19.3: "about 7 a routed hop"): its `show ip cef`, the route, the
#: egress interface twice, its `show ip interface`, the next hop's ARP entry and the next
#: hop's ingress `show ip interface`; an access list's counters come on top, when one is bound.
PER_HOP = 7
#: The runbook's own reads besides the hops: the ping, the traceroute and the return path's
#: first read.
FIXED = 3
#: The hops the command cap covers.
HOPS_AT_CAP = (D.MAX_COMMANDS - FIXED) // PER_HOP
#: The trace's ends that are this runbook's divergence wherever B is; `edge` is one only when B
#: is a managed device's (an address outside management is expected to leave the network).
_DIVERGES = ("dropped", "loop")


def _short(iface: str) -> str:
    from modules.nsot.ifnames import abbreviate
    return abbreviate(iface) or iface


def holders(lines: dict) -> tuple:
    """``({IPv4 address: (host, interface)}, {address: [hosts]})``: every IPv4 interface
    address committed intent holds, and the addresses two or more devices hold (a lab tool's
    shared management address), which name no device."""
    from modules.neighbours import _v4
    seen = {}
    for host, hv in sorted((lines or {}).items()):
        for iface in (hv or {}).get("interfaces") or []:
            ip = _v4(iface.get("ipv4", ""))
            if ip is not None:
                seen.setdefault(str(ip.ip), []).append((host, iface.get("name") or ""))
    one = {a: h[0] for a, h in seen.items() if len({x for x, _ in h}) == 1}
    shared = {a: sorted({x for x, _ in h}) for a, h in seen.items() if a not in one}
    return one, shared


def _loopback(hv: dict) -> tuple:
    """``(interface, address)``: the first loopback intent gives an IPv4 address and leaves up,
    or ``("", "")``."""
    from modules.neighbours import _v4
    for iface in (hv or {}).get("interfaces") or []:
        name = iface.get("name") or ""
        ip = _v4(iface.get("ipv4", ""))
        if name.lower().startswith("loopback") and ip is not None and not iface.get("shutdown"):
            return name, str(ip.ip)
    return "", ""


def plan(network: str, target: dict, lines: dict) -> dict:
    """The run this target would make, from intent alone (nothing asks a device): A, B, B's
    device, the first reads on A, the per-hop reads and the worst case. *target* is
    ``{"device": A, "address": B}``. Raises `diagnose.Refused` naming why."""
    a = str((target or {}).get("device") or "")
    if a not in lines:
        raise D.Refused(f"{a or 'no device'} has no committed intent in {network}, so there is "
                        "no path to follow from it")
    raw = str((target or {}).get("address") or "").strip()
    try:
        b = None if "%" in raw else ipaddress.ip_address(raw)
    except ValueError:
        b = None
    if b is None:
        raise D.Refused(f"{raw!r} is not one IPv4 or IPv6 address")
    if b.version == 6:
        raise D.Refused(f"{b} is an IPv6 address; \"A can't reach B\" follows IPv4 forwarding "
                        "only (`show ip cef`): its IPv6 form waits for `show ipv6 cef` to be "
                        "captured and parsed (C2415), so nothing was read")
    dest = str(b)
    dialect = D.dialect_of(lines[a].get("platform"), a)
    one, shared = holders(lines)
    if dest in shared:
        raise D.Refused(f"{dest} is held by {' and '.join(shared[dest])} in intent, so which "
                        "device B is cannot be told")
    owner, owner_if = one.get(dest, ("", ""))
    if owner == a:
        raise D.Refused(f"{dest} is {a}'s own address ({_short(owner_if)}), so there is no "
                        "path to follow")
    src, src_address = _loopback(lines[a])
    ping = ({"kind": "reach_ping_src", "command": D.render("reach_ping_src", dialect, dest=dest,
                                                           src=src)}
            if src else {"kind": "reach_ping", "command": D.render("reach_ping", dialect,
                                                                  dest=dest)})
    words = f"{a} to {dest}" + (f" ({owner} {_short(owner_if)})" if owner
                                else " (outside management)")
    outside = ("" if owner else
               f"{dest} is outside management: the path is followed as far as the network's "
               "devices, then a traceroute; no return path is read")
    worst = (D._bound(ping["command"]) + D._bound(D.render("traceroute", dialect, dest=dest))
             + HOPS_AT_CAP * (PER_HOP * D.SHOW_BOUND_SECONDS + int(D.DELTA_SECONDS)))
    return {"network": network, "runbook": RUNBOOK, "runbook_words": D.RUNBOOKS[RUNBOOK],
            "target": {"device": a, "address": dest}, "words": words, "source": a,
            "dest": dest, "dialect": dialect, "owner": owner, "owner_interface": owner_if,
            "src": src, "src_address": src_address, "ends": [], "reads": {a: [ping]},
            "per_hop": [D.READ_WORDS[k] for k in ("cef", "route", "interfaces", "ip_interface",
                                                  "arp", "acl_counters")],
            "count": 1, "cap": D.MAX_COMMANDS, "hops_at_cap": HOPS_AT_CAP, "worst_s": worst,
            "outside": outside, "_intent": lines}


# ── Reading, through the one reads engine ───────────────────────────────────────────────────

class _Reader:
    """Every read of one run: the cap and the per-device count before each, each device held
    for this diagnosis as it is first read, each batch's devices read concurrently."""

    def __init__(self, p: dict, out: dict, actor: str, session, lock):
        self.p, self.out, self.actor, self.session, self.lock = p, out, actor, session, lock
        self.lines = p["_intent"]
        self.asked, self.capped = {}, False

    def dialect(self, host: str) -> str:
        if host not in self.lines:
            raise D.Refused(f"{host} has no committed intent, so it is not read")
        return D.dialect_of(self.lines[host].get("platform"), host)

    def read(self, batch: dict, label: str):
        """``{host: answer}`` for *batch* (``{host: [{kind, command}]}``), or None when the
        command cap stops it (nothing of it read, nor of any batch after it)."""
        from modules import fanout
        from modules.nsot import reads

        batch = {h: c for h, c in batch.items() if c}
        if self.capped or (self.out["commands"] + sum(len(c) for c in batch.values())
                           > D.MAX_COMMANDS):
            self.capped = True
            return None
        got, hosts = {}, []
        for host, cmds in batch.items():
            n = self.asked.get(host, 0)
            if n + len(cmds) > D.MAX_PER_DEVICE:
                got[host] = {"run": "", "state": reads.SKIPPED, "answers": {}, "why": (
                    f"{host} has been asked {n} reads in this diagnosis, and {len(cmds)} more "
                    f"would pass the {D.MAX_PER_DEVICE} a device may be asked")}
                continue
            try:
                self.lock.take(host)
            except D.DiagnosisBusy as exc:
                got[host] = {"run": "", "state": reads.SKIPPED, "answers": {}, "why": (
                    f"{host} is in diagnosis "
                    f"{exc.holder.get('diagnosis') or 'of an unrecorded id'}; one diagnosis "
                    "at a time per device")}
                continue
            hosts.append(host)

        def one(host):
            return D._reads_engine(self.p["network"], host,
                                   [c["command"] for c in batch[host]], self.actor,
                                   f"diagnosis {self.out['id']}, {label}", self.session)

        for host, ans in zip(hosts, fanout.read_each(one, hosts, name="diagnosis")):
            if isinstance(ans, fanout.Failed):
                ans = {"run": "", "state": "failed", "why": str(ans), "answers": {}}
            got[host] = ans
            self.asked[host] = self.asked.get(host, 0) + len(batch[host])
            self.out["commands"] += len(batch[host])
            if ans.get("run"):
                self.out["runs"].append(ans["run"])
            if host not in self.out["devices"]:
                self.out["devices"].append(host)
        return got


def _answer(ans: dict, host: str, command: str) -> tuple:
    """``(text, reference, why)``: *command*'s answered text on *host* and its reference, or
    None and why it has none."""
    a = ((ans or {}).get("answers") or {}).get(command)
    if a is None or a.get("state") != "answered":
        return None, "", ((a or {}).get("why") or (ans or {}).get("why")
                          or (ans or {}).get("state") or "it was not read")
    return a.get("answer") or "", D.ref(ans["run"], host, command), ""


def _step(step: str, host: str, cmds: list, ans: dict, prefix: str) -> dict:
    """One batch's step: what was read on *host* and why, each read by its reference."""
    from modules.heal.diagnose_parse import NOT_CAPTURED
    from modules.nsot import reads
    if ans is None:
        return {"step": step, "device": host, "result": "stopped",
                "words": f"{prefix}not read: the {D.MAX_COMMANDS}-command cap was reached"}
    if ans["state"] == reads.SKIPPED:
        return {"step": step, "device": host, "result": "not_read",
                "words": f"{prefix}not read: {ans['why']}"}
    if ans["state"] in ("refused", "failed", reads.UNKNOWN) or not ans["answers"]:
        return {"step": step, "device": host, "result": "failed",
                "words": f"{prefix}not read: {ans.get('why') or ans['state']}"}
    parts = []
    for c in cmds:
        kind = D.PARSE_KIND.get(c["kind"], c["kind"])
        parts.append(D.READ_WORDS.get(c["kind"], c["kind"]) + (
            " (read, and not yet interpreted: C2414)" if kind in NOT_CAPTURED else ""))
    return {"step": step, "device": host, "result": "ok",
            "reads": [D.ref(ans["run"], host, c["command"]) for c in cmds],
            "words": f"{prefix}{len(cmds)} read(s) on {host}: " + "; ".join(parts)}


# ── The trace, and each hop ─────────────────────────────────────────────────────────────────

def _trace(reader: _Reader, source: str, dest: str, owner_of: dict, label: str) -> tuple:
    """``(result, refs)``: `path_trace.trace` from *source* to *dest*, each level read through
    *reader*; *refs* ``{device: read reference}`` for each `show ip cef` answered."""
    refs = {}

    def read(devices):
        batch, why = {}, {}
        for d in devices:
            try:
                batch[d] = [{"kind": "cef", "command": D.render("cef", reader.dialect(d),
                                                                dest=dest)}]
            except D.Refused as exc:
                why[d] = str(exc)
        got = reader.read(batch, label) if batch else {}
        if got is None:
            return {d: {"ok": False, "why": f"the {D.MAX_COMMANDS}-command cap was reached"}
                    for d in devices}
        answered = {}
        for d in devices:
            if d in why:
                answered[d] = {"ok": False, "why": why[d]}
                continue
            text, ref, missing = _answer(got.get(d), d, batch[d][0]["command"])
            if text is None:
                answered[d] = {"ok": False, "why": missing}
            else:
                refs[d] = ref
                answered[d] = {"ok": True, "answer": text}
        return answered

    return path_trace.trace(source, dest, owner_of, read, set(reader.lines)), refs


def _branch_words(b: dict) -> str:
    chain = " > ".join(f"{h['device']} {_short(h['iface'])}" if h.get("iface") else h["device"]
                       for h in b["hops"])
    return f"{chain}: {b['words']}"


class Hop:
    """One routed hop's reads: the egress on its device, the ingress on the next hop's."""

    def __init__(self, n: int, hop: dict, ingress: str):
        self.n, self.device, self.egress = n, hop["device"], hop["iface"]
        self.nh, self.to, self.ingress = hop.get("to_address") or "", hop.get("to") or "", ingress
        self.facts, self.refs, self.why, self.command = {}, {}, {}, {}
        #: The round the command cap stopped this hop's reads at (0: it did not).
        self.capped = 0

    def host(self, where: str) -> str:
        return self.device if where == "egress" else self.to

    def iface(self, where: str) -> str:
        return self.egress if where == "egress" else self.ingress

    def name(self, where: str = "egress") -> str:
        return f"{self.host(where)} {_short(self.iface(where))}"

    def take(self, where: str, rnd: int, cmds: list, ans, dialect: str) -> None:
        from modules.heal import diagnose_parse as P
        for c in cmds:
            kind = D.PARSE_KIND.get(c["kind"], c["kind"])
            key = (where, kind, rnd)
            self.command[key] = c["command"]
            if ans is None:
                self.why[key] = f"the {D.MAX_COMMANDS}-command cap was reached"
                continue
            text, ref, missing = _answer(ans, self.host(where), c["command"])
            if text is None:
                self.why[key] = missing
                continue
            self.refs[key] = ref
            got = P.parse(kind, text, self.iface(where), dialect)
            if got["state"] == P.PARSED:
                self.facts[key] = got["facts"]
            else:
                self.why[key] = got["why"]

    def fact(self, where: str, kind: str, rnd: int = 1):
        return self.facts.get((where, kind, rnd))

    def ref_of(self, where: str, kind: str, rnd: int = 1) -> str:
        return self.refs.get((where, kind, rnd)) or ""

    def missing(self, where: str, kind: str, rnd: int = 1) -> str:
        key = (where, kind, rnd)
        if key not in self.command:
            return (f"{self.host(where) or 'the next hop'}: no read of "
                    f"{D.READ_WORDS.get(kind, kind)} at hop {self.n}")
        return f"`{self.command[key]}` on {self.host(where)}: {self.why.get(key) or 'read'}"


def _check_hop(reader: _Reader, n: int, hop: dict, dest: str, held: dict, sleep,
               out: dict) -> Hop:
    """Hop *n*'s reads, both rounds; ``Hop.capped`` when the cap stopped them."""
    to, nh = hop.get("to") or "", hop.get("to_address") or ""
    ingress = ""
    if to in reader.lines and held.get(nh, ("", ""))[0] == to:
        ingress = held[nh][1]
    h = Hop(n, hop, ingress)
    dialects = {}
    try:
        dialects[h.device] = reader.dialect(h.device)
        if ingress:
            dialects[to] = reader.dialect(to)
    except D.Refused as exc:
        out["steps"].append({"step": "hop", "device": h.device, "result": "failed",
                             "words": f"hop {n}: not read: {exc}"})
        return h
    eg = {"if": h.egress}
    first = {h.device: [
        {"kind": "interfaces", "command": D.render("interfaces", dialects[h.device], **eg)},
        {"kind": "ip_interface", "command": D.render("ip_interface", dialects[h.device], **eg)},
        {"kind": "arp", "command": D.render("arp", dialects[h.device], nh=nh)},
        {"kind": "route", "command": D.render("route", dialects[h.device], dest=dest)}]}
    if ingress:
        first[to] = [{"kind": "ip_interface", "command": D.render(
            "ip_interface", dialects[to], **{"if": ingress})}]
    got = reader.read(first, f"hop {n}, round 1")
    _take_round(h, out, first, got, dialects, 1, f"hop {n}: ")
    if got is None:
        h.capped = 1
        return h
    sleep(D.DELTA_SECONDS)
    second = {h.device: [{"kind": "interfaces",
                          "command": D.render("interfaces", dialects[h.device], **eg)}]}
    for where, host in (("egress", h.device), ("ingress", to if ingress else "")):
        bound = h.fact(where, "ip_interface") or {}
        for name in sorted({bound.get("acl_in") or "", bound.get("acl_out") or ""} - {""}):
            try:
                second.setdefault(host, []).append({"kind": "acl_counters", "command": D.render(
                    "acl_counters", dialects[host], acl=name)})
            except D.Refused as exc:
                out["steps"].append({"step": "read again", "device": host, "result": "failed",
                                     "words": f"hop {n}: {exc}"})
    got = reader.read(second, f"hop {n}, round 2")
    _take_round(h, out, second, got, dialects, 2, f"hop {n}, again: ")
    h.capped = 2 if got is None else 0
    return h


def _take_round(h: Hop, out: dict, batch: dict, got, dialects: dict, rnd: int,
                prefix: str) -> None:
    for host, cmds in batch.items():
        where = "egress" if host == h.device else "ingress"
        ans = None if got is None else got.get(host)
        h.take(where, rnd, cmds, ans, dialects[host])
        out["steps"].append(_step("hop" if rnd == 1 else "read again", host, cmds, ans,
                                  prefix))


def _sequence(result: dict) -> list:
    """``[(branch, index)]``: the hops in the order they are checked: the branches that stop
    first, then those leaving the network, then those delivered (`path_trace.RANK`), each
    branch's hops in order."""
    order = sorted(result.get("branches") or [], key=lambda b: path_trace.RANK[b["cls"]])
    return [(b, i) for b in order for i in range(len(b["hops"]))]


# ── The run ─────────────────────────────────────────────────────────────────────────────────

def run_plan(p: dict, out: dict, actor: str, *, session=None, logs=None, sleep=None,
             started: float = 0.0) -> None:
    """Run the plan *p* into the diagnosis *out* (`diagnose.run`'s, recorded by it)."""
    network, a, dest = p["network"], p["source"], p["dest"]
    out["devices"] = [a]
    out["steps"].append({"step": "plan", "result": "ok", "words": (
        f"\"{p['runbook_words']}\" on {p['words']}: the path is followed hop by hop, about "
        f"{PER_HOP} reads a routed hop, at most {p['cap']} (about {HOPS_AT_CAP} hops)"
        + (f"; {p['outside']}" if p["outside"] else ""))})
    try:
        with D.DiagnosisLock(network, [a], out["id"], actor) as lock:
            out["steps"].append({"step": "hold", "result": "ok",
                                 "words": f"held for this diagnosis: {a}, then each device "
                                          "as the path reaches it"})
            ctx = _walk(p, out, _Reader(p, out, actor, session, lock), sleep)
            if not any(s["step"] == "return" for s in out["steps"]):
                out["steps"].append({"step": "return", "result": "not_read", "words": (
                    "the return path is not read: " + (
                        "the command cap was reached" if out["stopped"] else
                        "the forward path diverges from intent"))})
            from modules import fanout
            got_logs = fanout.read_each(lambda h: logs(network, h, started),
                                        list(out["devices"]), name="diagnosis-logs")
    except D.DiagnosisBusy as exc:
        out.update(state="busy", words=str(exc))
        out["steps"].append({"step": "hold", "result": "refused", "words": str(exc)})
        return
    for host, g in zip(list(out["devices"]), got_logs):
        ctx.logs[host] = g if isinstance(g, dict) else {"state": "unread", "why": str(g),
                                                        "lines": []}
        read = ctx.logs[host]["state"] == "read"
        out["steps"].append({"step": "logs", "device": host,
                             "result": "ok" if read else "not_read",
                             "words": (f"{len(ctx.logs[host]['lines'])} configuration line(s) "
                                       "logged in the last hour" if read else
                                       f"the log was not read: {ctx.logs[host]['why']}")})
    D._judge(ctx, out, PATH_RULES)


class ReachContext:
    """What the rules compare: the plan, the forward trace and where it diverged, each hop
    checked, the return trace, and each device's logs."""

    def __init__(self, p: dict):
        self.plan, self.lines = p, p["_intent"]
        self.trace, self.refs, self.divergence = None, {}, None
        self.hops, self.ret, self.ret_refs, self.ret_dest = [], None, {}, ""
        self.complete, self.logs = False, {}


def _walk(p: dict, out: dict, reader: _Reader, sleep) -> ReachContext:
    a, dest, ctx = p["source"], p["dest"], ReachContext(p)
    one, _shared = holders(reader.lines)
    owner_of = {addr: host for addr, (host, _if) in one.items()}
    ping = p["reads"][a]
    got = reader.read({a: ping}, "reach")
    out["steps"].append(_step("reach", a, ping, None if got is None else got.get(a), ""))
    out["hops"] = [_reach_row(a, ping, None if got is None else got.get(a))]

    ctx.trace, ctx.refs = _trace(reader, a, dest, owner_of, "trace")
    out["steps"].append({"step": "trace", "result": "ok", "reads": sorted(ctx.refs.values()),
                         "words": f"{len(ctx.trace['branches'])} branch(es): " + "; ".join(
                             _branch_words(b) for b in ctx.trace["branches"])})
    if reader.capped:
        _capped(out, "while following the path; the devices past it not read")
    seq, checked, n, traceroute = _sequence(ctx.trace), set(), 0, False
    for k, (branch, i) in enumerate(seq):
        hop, last = branch["hops"][i], i == len(branch["hops"]) - 1
        if last and (branch["end"] in _DIVERGES or (branch["end"] == "edge" and p["owner"])):
            ctx.divergence = {"branch": branch, "hop": hop}
            out["hops"].append({"n": n + 1, "device": hop["device"],
                                "read": f"show ip cef {dest}: {hop.get('words') or ''}",
                                "against": f"diverges here: {branch['words']}",
                                "verdict": "diverges"})
            _stop(out, hop["device"], seq[k + 1:], "its forwarding diverges from intent")
            _unread_rows(out, hop["device"], seq[k + 1:], n + 1)
            return ctx
        key = (hop["device"], hop.get("iface") or "", hop.get("to_address") or "")
        if hop.get("iface") and key not in checked:
            checked.add(key)
            n += 1
            h = _check_hop(reader, n, hop, dest, one, sleep, out)
            ctx.hops.append(h)
            if h.capped:
                _capped(out, "before the first hop's checks; no hop was checked" if
                        h.capped == 1 and n == 1 else
                        f"after hop {n - 1}; hops after it not read" if h.capped == 1 else
                        f"during hop {n} (its second read not made); hops after it not read")
                out["hops"].append(_hop_row(h, "", out["stopped"]))
                _unread_rows(out, h.device, seq[k + 1:], n)
                return ctx
            claim = _diverges(ctx, h)
            out["hops"].append(_hop_row(h, claim))
            if claim:
                _stop(out, h.device, seq[k + 1:], f"hop {n} diverges from intent")
                _unread_rows(out, h.device, seq[k + 1:], n)
                return ctx
        if last and branch["end"] in ("unread", "bounded"):
            out["not_checked"].append({"check": f"the path past {hop['device']}",
                                       "why": branch["words"]})
        traceroute = traceroute or (last and branch["end"] == "edge")
    ctx.complete = all(b["end"] in ("delivered", "edge") for b in ctx.trace["branches"])
    if traceroute:
        cmd = [{"kind": "traceroute", "command": D.render("traceroute", reader.dialect(a),
                                                          dest=dest)}]
        got = reader.read({a: cmd}, "traceroute")
        out["steps"].append(_step("traceroute", a, cmd, None if got is None else got.get(a),
                                  "past the managed devices: "))
        if got is None:
            _capped(out, "before the traceroute; it was not sent")
    _return(p, out, reader, ctx, owner_of)
    return ctx


def _capped(out: dict, where: str) -> None:
    """The command cap stopped the run: said once, on the diagnosis and as a step."""
    if out["stopped"]:
        return
    out["stopped"] = f"stopped at the {D.MAX_COMMANDS}-command cap {where}"
    out["steps"].append({"step": "hop", "result": "stopped", "words": out["stopped"]})


def _stop(out: dict, device: str, rest: list, why: str) -> None:
    left = sorted({b["hops"][i]["device"] for b, i in rest} - {device})
    words = f"stopped at {device}: {why}" + (
        f"; the hops after it were not checked ({', '.join(left)})" if left else "")
    out["steps"].append({"step": "hop", "device": device, "result": "stopped", "words": words})
    if left:
        out["not_checked"].append({"check": f"the hops after {device}",
                                   "why": "the runbook stops at the first hop that diverges"})


def _diverges(ctx: ReachContext, h: Hop) -> str:
    """The claim of the first decisive or strong rule hop *h* alone fires (the walk stops
    there), or "" when it fires none."""
    view = ReachContext(ctx.plan)
    view.hops = [h]
    for rule in PATH_RULES:
        if rule.scope != "hop":
            continue
        hits, _passed = rule.fn(rule, view)
        for x in hits:
            if x["strength"] in ("decisive", "strong"):
                return x["claim"]
    return ""


# ── The hop table (board H, artboard J's right: the path hop by hop against intent) ────────

def _reach_row(a: str, ping: list, ans) -> dict:
    """Hop 0: A's ping to B. Sent and kept on History › Reads; its answer is not interpreted
    until the ping has a real capture (C2414), so the row never says it passed or failed."""
    cmd = ping[0]["command"] if ping else "ping"
    if ans is None:
        return {"n": 0, "device": a, "read": f"{cmd}: not sent, the command cap was reached",
                "against": "", "verdict": "unread"}
    sent = ans.get("state") not in ("refused", "failed") and bool(ans.get("answers"))
    return {"n": 0, "device": a,
            "read": (f"{cmd}: sent, its answer on History › Reads" if sent else
                     f"{cmd}: not read ({ans.get('why') or ans.get('state') or 'no answer'})"),
            "against": "not interpreted yet (C2414): the path is followed whatever it answered",
            "verdict": "not_interpreted" if sent else "unread"}


def _hop_row(h: Hop, claim: str, stopped: str = "") -> dict:
    """A checked hop as the table draws it: what was read (each read's state in a few words,
    "not read" naming why) and how it stands against intent."""
    parts = [f"out {_short(h.egress)} toward {h.to or h.nh}"
             + (f" ({h.nh})" if h.to and h.nh else "")]
    f = h.fact("egress", "interfaces")
    parts.append(f"{_short(h.egress)} {f['state'].replace('_', ' ')}, line protocol "
                 f"{f['protocol']}" if f else f"{_short(h.egress)}'s state not read")
    one, two = h.fact("egress", "interfaces", 1), h.fact("egress", "interfaces", 2)
    if one and two and one.get("input_errors") is not None:
        parts.append(f"input errors {one.get('input_errors')} then "
                     f"{two.get('input_errors')}")
    arp = h.fact("egress", "arp")
    if arp is not None:
        mine = any(e["address"] == h.nh for e in arp["entries"])
        parts.append(f"next hop {h.nh} resolved (ARP)" if mine else
                     f"next hop {h.nh} unresolved (ARP)")
    for where in ("egress", "ingress"):
        if where == "ingress" and not h.ingress:
            continue
        b = h.fact(where, "ip_interface")
        name = h.name(where)
        if b is None:
            parts.append(f"{name}'s access lists not read")
            continue
        acls = [f"{d} {b[k]}" for d, k in (("in", "acl_in"), ("out", "acl_out")) if b.get(k)]
        parts.append(f"{name}: " + (", ".join(f"access list {a}" for a in acls) if acls
                                    else "no access list bound"))
    if stopped:
        return {"n": h.n, "device": h.device, "read": "; ".join(parts),
                "against": f"not finished: {stopped}", "verdict": "unread"}
    return {"n": h.n, "device": h.device, "read": "; ".join(parts),
            "against": f"diverges here: {claim}" if claim else "as intent",
            "verdict": "diverges" if claim else "ok"}


def _unread_rows(out: dict, device: str, rest: list, n: int) -> None:
    """The devices after the hop the walk stopped at, each once, as rows "not read"."""
    seen = {device} | {r["device"] for r in out["hops"]}
    for b, i in rest:
        dev = b["hops"][i]["device"]
        if dev in seen:
            continue
        seen.add(dev)
        n += 1
        out["hops"].append({"n": n, "device": dev, "read": f"not read: hops after {device} "
                                                           "are not read",
                            "against": "", "verdict": "unread"})


def _return(p: dict, out: dict, reader: _Reader, ctx: ReachContext, owner_of: dict) -> None:
    """The return path, when the forward one holds and B is a managed device's: from B's
    device back to A's loopback, or to the first hop's egress address."""
    owner = p["owner"]
    if not owner or not ctx.complete or reader.capped:
        why = ("B is outside management" if not owner else
               "the forward path did not hold at every hop" if not ctx.complete else
               "the command cap was reached")
        out["steps"].append({"step": "return", "result": "not_read",
                             "words": f"the return path is not read: {why}"})
        return
    back = p["src_address"]
    if not back:
        from modules.heal.diagnose import _intent_iface
        from modules.neighbours import _v4
        first = next((h for h in ctx.hops if h.device == p["source"]), None)
        ip = _v4(_intent_iface(reader.lines[p["source"]], first.egress).get("ipv4", "")) \
            if first else None
        back = str(ip.ip) if ip is not None else ""
    if not back:
        out["steps"].append({"step": "return", "result": "not_read", "words": (
            f"the return path is not read: intent gives {p['source']} no loopback and its "
            "egress no IPv4 address to follow back")})
        out["not_checked"].append({"check": "the return path",
                                   "why": f"no address of {p['source']}'s to follow back"})
        return
    ctx.ret_dest = back
    ctx.ret, ctx.ret_refs = _trace(reader, owner, back, owner_of, "return")
    if reader.capped:
        _capped(out, "while following the return path; the devices past it not read")
    out["steps"].append({"step": "return", "result": "ok", "reads": sorted(ctx.ret_refs.values()),
                         "words": f"from {owner} back to {back}: " + "; ".join(
                             _branch_words(b) for b in ctx.ret["branches"])})
    for b in ctx.ret["branches"]:
        if b["end"] in ("unread", "bounded"):
            out["not_checked"].append({"check": f"the return path past {b['hops'][-1]['device']}",
                                       "why": b["words"]})


# ── The rules (`PATH_RULES`), each with a planted case ──────────────────────────────────────

class PathRule(D.Rule):
    """A rule of this runbook: *scope* ``hop`` (judged on each hop, so the walk can stop at
    the first that diverges) or ``path`` (on the trace, the return or the logs)."""

    def __init__(self, name, layer, strength, words, fn, scope):
        super().__init__(name, layer, strength, words, fn)
        self.scope = scope


def _intent_of(ctx, host: str, iface: str) -> dict:
    from modules.heal.diagnose import _intent_iface
    return _intent_iface(ctx.lines.get(host) or {}, iface) if host and iface else {}


def _b_words(ctx) -> str:
    p = ctx.plan
    return (f"{p['dest']} is {p['owner']} {_short(p['owner_interface'])}'s" if p["owner"]
            else f"{p['dest']} is outside management")


def _r_no_route(rule, ctx):
    d = ctx.divergence
    if d and d["branch"]["end"] == "dropped":
        hop, dev = d["hop"], d["hop"]["device"]
        cef = hop["answer"]
        claim = (f"{dev} has no route to {ctx.plan['dest']}" if cef["state"] == "no_route" else
                 f"{dev}'s route to {ctx.plan['dest']} discards it ({cef.get('prefix') or '?'})")
        return [D.finding(rule, claim, [D.ev(ctx.refs.get(dev, ""),
                                             path_trace.answer_words(cef), _b_words(ctx))],
                          rule_out=f"`show ip cef {ctx.plan['dest']}` on {dev} naming a next "
                                   "hop",
                          todo="Find why the route is missing: Diagnose… \"adjacency down\" "
                               f"from {dev} toward the next device on intent's path, or the "
                               "static route intent holds")], ""
    return [], ("every device on the path has a route toward B" if ctx.complete else "")


def _r_loop(rule, ctx):
    d = ctx.divergence
    if d and d["branch"]["end"] == "loop":
        hop = d["hop"]
        return [D.finding(rule, f"{d['branch']['words']}, toward {ctx.plan['dest']}",
                          [D.ev(ctx.refs.get(hop["device"], ""), hop.get("words") or "",
                                _b_words(ctx))],
                          rule_out=f"{hop['device']}'s next hop leading on, never back",
                          todo=f"Compare {hop['device']}'s and {hop.get('to')}'s routes toward "
                               f"{ctx.plan['dest']} with intent: one points back")], ""
    return [], ("the path never loops" if ctx.complete else "")


def _r_leaves(rule, ctx):
    d = ctx.divergence
    if d and d["branch"]["end"] == "edge":
        hop = d["hop"]
        return [D.finding(rule, f"the path {d['branch']['words']}, though {_b_words(ctx)}",
                          [D.ev(ctx.refs.get(hop["device"], ""), hop.get("words") or "",
                                _b_words(ctx))],
                          rule_out=f"{hop['device']}'s next hop toward {ctx.plan['dest']} a "
                                   "device of the network",
                          todo=f"Compare {hop['device']}'s route toward {ctx.plan['dest']} "
                               "with intent's")], ""
    return [], ("the path stays inside the network to B's device"
                if ctx.complete and ctx.plan["owner"] else "")


def _state_hits(rule, ctx, want: tuple):
    """Each hop's egress (`show interfaces`) and ingress (`show ip interface`) in a state of
    *want*, as findings; ``(hits, seen)``."""
    hits, seen = [], 0
    for h in ctx.hops:
        for where, kind in (("egress", "interfaces"), ("ingress", "ip_interface")):
            if where == "ingress" and not h.ingress:
                continue
            f = h.fact(where, kind)
            if f is None:
                continue
            seen += 1
            got = (f["state"], f["protocol"])
            if got[0] not in want[0] or (want[1] and got[1] not in want[1]):
                continue
            shut = bool(_intent_of(ctx, h.host(where), h.iface(where)).get("shutdown"))
            role = ("the path's egress toward " + (h.to or h.nh) if where == "egress"
                    else f"the next hop's ingress from {h.device}")
            hits.append((h, where, kind, f, shut, role))
    return hits, seen


def _r_hop_down(rule, ctx):
    found, seen = _state_hits(rule, ctx, (("admin_down", "down"), ()))
    hits = []
    for h, where, kind, f, shut, role in found:
        if f["state"] == "admin_down":
            claim = f"{h.name(where)}, {role}, is administratively down" + (
                ", as intent holds it shut" if shut else
                ", though intent holds it up: it was shut outside intent")
            todo = ("Intent shuts it: change intent to bring it up" if shut else
                    "Check drift now…: it departs from intent")
        else:
            claim = (f"{h.name(where)}, {role}, is down while administratively up" + (
                f" ({f['reason']})" if f["reason"] else ""))
            todo = f"Check the cable and the port at {h.name(where)}"
        hits.append(D.finding(rule, claim, [D.ev(h.ref_of(where, kind),
                                                 f"{f['name']} is {f['state'].replace('_', ' ')}, "
                                                 f"line protocol is {f['protocol']}",
                                                 "shutdown" if shut else "no shutdown")],
                              rule_out=f"{h.name(where)} reading up", todo=todo))
    return hits, ("each hop's egress and its next hop's ingress are up"
                  if seen and not found and seen == _expected(ctx) else "")


def _expected(ctx) -> int:
    return sum(1 + (1 if h.ingress else 0) for h in ctx.hops)


def _r_hop_protocol_down(rule, ctx):
    found, _seen = _state_hits(rule, ctx, (("up",), ("down",)))
    return [D.finding(rule, f"{h.name(where)}, {role}, is up with its line protocol down" + (
        f" ({f['reason']})" if f["reason"] else ""),
        [D.ev(h.ref_of(where, kind), f"{f['name']} is up, line protocol is down")],
        rule_out=f"{h.name(where)}'s line protocol reading up",
        todo="Check the far side of the link: its port, its encapsulation, or keepalives")
        for h, where, kind, f, _shut, role in found], ""


def _r_hop_errors(rule, ctx):
    hits, seen = [], 0
    for h in ctx.hops:
        one, two = h.fact("egress", "interfaces", 1), h.fact("egress", "interfaces", 2)
        if one is None or two is None:
            continue
        seen += 1
        rise = {k: (two[k] or 0) - (one[k] or 0) for k in ("input_errors", "crc")
                if one.get(k) is not None and two.get(k) is not None}
        if any(v > 0 for v in rise.values()):
            hits.append(D.finding(rule, f"{h.name()}'s input errors rose by "
                                  f"{rise.get('input_errors', 0)} (CRC by {rise.get('crc', 0)}) "
                                  f"in {int(D.DELTA_SECONDS)} s", [
                                      D.ev(h.ref_of("egress", "interfaces", 1),
                                           f"{one['input_errors']} input errors, {one['crc']} "
                                           "CRC"),
                                      D.ev(h.ref_of("egress", "interfaces", 2),
                                           f"{two['input_errors']} input errors, {two['crc']} "
                                           "CRC")],
                                  agree=2, rule_out="the counters standing still across the two "
                                                    "reads",
                                  todo=f"Check the cable and the optic at {h.name()}"))
    return hits, ("no hop's egress errors rose across the two reads"
                  if seen and seen == len(ctx.hops) and not hits else "")


def _r_next_hop(rule, ctx):
    hits, seen = [], 0
    for h in ctx.hops:
        f = h.fact("egress", "arp")
        if f is None:
            continue
        seen += 1
        mine = [e for e in f["entries"] if e["address"] == h.nh]
        if mine:
            continue
        pending = h.nh in f["incomplete"]
        hits.append(D.finding(rule, f"{h.device} has not resolved its next hop {h.nh} on "
                              f"{_short(h.egress)} (ARP " + ("incomplete" if pending else
                                                             "has no entry") + ")",
                              [D.ev(h.ref_of("egress", "arp"),
                                    f"Internet {h.nh} Incomplete" if pending
                                    else f"no ARP entry for {h.nh}",
                                    f"{h.nh} is {h.to}'s" if h.to else "")],
                              rule_out=f"an ARP entry for {h.nh} with its hardware address",
                              todo=f"Check the segment between {h.device} and "
                                   f"{h.to or h.nh}: the VLAN, the switch port, or the next "
                                   "hop's interface"))
    return hits, ("every hop's next hop is resolved"
                  if seen and seen == len(ctx.hops) and not hits else "")


def _r_hop_acl(rule, ctx):
    hits, seen = [], 0
    for h in ctx.hops:
        for where in ("egress", "ingress"):
            if where == "ingress" and not h.ingress:
                continue
            f = h.fact(where, "ip_interface")
            if f is None:
                continue
            seen += 1
            from modules.heal.diagnose import _acls
            intent = _acls(_intent_of(ctx, h.host(where), h.iface(where)))
            for way, key in (("in", "acl_in"), ("out", "acl_out")):
                if (f.get(key) or "") == (intent.get(way) or ""):
                    continue
                hits.append(D.finding(
                    rule, f"{h.name(where)}, on the path toward {ctx.plan['dest']}, has access "
                          f"list {f.get(key) or 'none'} bound {way}; intent binds "
                          f"{intent.get(way) or 'none'}",
                    [D.ev(h.ref_of(where, "ip_interface"),
                          f"{'Inbound' if way == 'in' else 'Outgoing'} access list is "
                          f"{f.get(key) or 'not set'}",
                          f"ip access-group {intent.get(way) or '(none)'} {way}")],
                    rule_out="the bindings reading as intent holds them",
                    todo="A person's change: an access list is never healed (Never)"))
    return hits, ("no hop binds an access list intent does not hold"
                  if seen and seen == _expected(ctx) and not hits else "")


def _r_return(rule, ctx):
    if ctx.ret is None:
        return [], ""
    bad = [b for b in ctx.ret["branches"] if b["end"] in ("dropped", "loop", "edge")]
    if not bad:
        return [], ("the return path from B's device reaches A"
                    if all(b["end"] == "delivered" for b in ctx.ret["branches"]) else "")
    b = sorted(bad, key=lambda x: path_trace.RANK[x["cls"]])[0]
    hop = b["hops"][-1]
    return [D.finding(rule, f"the return path from {ctx.plan['owner']} to "
                            f"{ctx.plan['source']}'s {ctx.ret_dest}: {b['words']}",
                      [D.ev(ctx.ret_refs.get(hop["device"], ""), hop.get("words") or "",
                            f"{ctx.ret_dest} is {ctx.plan['source']}'s")],
                      rule_out=f"`show ip cef {ctx.ret_dest}` on {hop['device']} leading on "
                               f"to {ctx.plan['source']}",
                      todo=f"Find why {hop['device']} has no way back to "
                           f"{ctx.plan['source']}: the return route is what is missing")], ""


def _r_config_changed(rule, ctx):
    hits, read = [], 0
    for host, got in sorted(ctx.logs.items()):
        if got.get("state") != "read":
            continue
        read += 1
        if got["lines"]:
            last = got["lines"][0]
            hits.append(D.finding(rule, f"{host}'s configuration was changed in the last hour "
                                  f"({len(got['lines'])} line(s) logged, the last at "
                                  f"{last['at']})", [D.ev(":".join(("log", host, last["at"])),
                                                          f"%{last['mnemonic']}")],
                                  rule_out="no configuration line logged",
                                  todo="Find who changed it on History"))
    return hits, ("no configuration change was logged on a device read in the last hour"
                  if read and read == len(ctx.logs) and not hits else "")


PATH_RULES = (
    PathRule("hop_down", "physical", "decisive",
             "a hop's egress, or its next hop's ingress, down", _r_hop_down, "hop"),
    PathRule("hop_errors_rising", "physical", "strong",
             "input errors or CRC rising on a hop's egress", _r_hop_errors, "hop"),
    PathRule("hop_protocol_down", "link", "strong", "a hop's interface up, line protocol down",
             _r_hop_protocol_down, "hop"),
    PathRule("next_hop_unresolved", "link", "strong", "a hop's next hop unresolved (ARP)",
             _r_next_hop, "hop"),
    PathRule("no_route", "network", "decisive", "no route to B at a hop", _r_no_route, "path"),
    PathRule("loop", "network", "decisive", "a forwarding loop toward B", _r_loop, "path"),
    PathRule("leaves_network", "network", "strong",
             "the path leaves the network though B is a managed device's", _r_leaves, "path"),
    PathRule("return_path", "network", "decisive", "no return path from B's device to A",
             _r_return, "path"),
    PathRule("hop_acl", "policy", "decisive",
             "an access list bound on the path that intent does not hold", _r_hop_acl, "hop"),
    PathRule("path_config_changed", "policy", "circumstantial",
             "a configuration change on a device read in the last hour", _r_config_changed,
             "path"),
)
