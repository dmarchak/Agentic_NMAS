"""The "a telemetry stream lost" runbook (C2828; docs/HEAL_TO_INTENT.md 19.3), on the diagnosis
engine (`modules/heal/diagnose.py`): read-only and deterministic, every device read through the
one reads engine as kind ``diagnosis``, held, masked, capped and recorded on History › Reads.

**Why it exists** (the operator, H11 W8, 2026-11-08: "For a lost telemetry stream, the test
that matters is device -> collector on the stream's port"). A router's two dial-out streams
stayed down 40 minutes after their cause (its neighbour's access list) was put back, and the
diagnosis it got was "can't reach" from that neighbour to it, a path the stream does not use,
which found nothing. A stream
runs from the device to its collector, on the port its receiver names, so that is the path
read here, from both of its ends:

1. **the device** (one batch, held): its subscriptions' brief (`show telemetry ietf
   subscription all`: each one's state), each lost subscription's receiver (`show telemetry
   ietf subscription <id> receiver`), and a ping to each collector address its receivers name;
2. **the collector**, when it is Mercury's own host (Mercury runs beside Telegraf): its
   listener on the stream's port, and its sessions on that port from the device's addresses,
   read from the kernel's socket tables (`/proc/net/tcp` and `/proc/net/tcp6`, both families;
   an IPv4 session a dual-stack listener accepted is printed there as ``::ffff:<v4>`` and is
   read as its IPv4 address). A local read: no command, no root, nothing written. A collector
   at an address that is not this host's is not read, said by name;
3. **the cause**, from the heal records: a configuration change on another device in the
   `said.LIKELY_S` before the stream was lost (one the trigger names, else the only one), and
   whether a decision has read that device back at intent since. **A symptom outliving its
   cause is a different problem from a stale one:** the stream still lost well after its cause
   was put back (`outlived_cause`) is stuck at the device or the collector, while one put back
   less than the lost-stream alert's own clearing time ago (`settle_s`) may simply not have
   been read since (`cause_just_cleared`);
4. the device's configuration lines in the last hour, then compare, rank and record as every
   runbook (`diagnose._judge`, `rank`, the step log's ``diagnosis`` row), with this runbook's
   table (`STREAM_RULES`).

**Measured, not assumed.** The brief is parsed against its real capture (an IOS-XE router,
2026-10-17, tests/fixtures/diagnose/). The receiver read is parsed against its real captures
(one router streaming and one not, both reading State Connected, 2026-11-10; C2890), so the
device's own
side of the session is evidence in the half-open and no-session hypotheses; a receiver answer
the parser cannot read says its evidence is incomplete, never a guess. The socket tables are
parsed against a real capture of this kernel's (tests/fixtures/diagnose/collector/README.md).

**The stream itself** (C2892): each lost subscription's series in Prometheus, the lost-stream
alert's own query (`count(last_over_time({device, subscription}[90s]))`, `series_of`), read
through Mercury's Prometheus client. A series present now means the stream is back: the
half-open hypothesis is ruled out for it (a session that carries data is not half-open, which
the socket tables alone cannot tell), and `stream_flowing`'s passed check is the runbook's
symptom-gone check (`auto_diagnose.SYMPTOM_GONE_RULES`). Prometheus unread is said, and decides
nothing.

**What it does not do:** re-establish the stream. Removing and re-adding a subscription's
receiver is a device change, the operation `modules/heal/resubscribe.py` (C2838), which a
person starts from the lost stream's Needs attention row; the diagnosis names it as what to do
next.
"""

import ipaddress
import logging
import os
import re
import sys
import time

from modules.heal import diagnose as D

log = logging.getLogger(__name__)

RUNBOOK = "stream_lost"
#: The runbook's steps, in order, as the manual names them.
STEPS = ("plan", "hold", "read", "collector", "stream", "cause", "logs", "compare", "rank",
         "record")
#: The lost-stream alert's window and its group's evaluation interval, as
#: scripts/nmas-telemetry-rules writes them (`WINDOW_SECONDS`, the group's "1m"; held equal
#: by tests/test_heal_diagnose_stream.py): a stream back now is read by the alert at most
#: this long after.
ALERT_WINDOW_S = 90
ALERT_INTERVAL_S = 60
#: The lost-stream alert's title, as the generator writes it (`rule_for`): the subscription a
#: trigger recorded before triggers carried its label is read from it, anchored. Its first
#: word, the product's name in the rule's title, is any one word (the product is never named
#: in a string a screen may draw, tests/test_v2_brand.py), as Needs attention's own match.
TITLE = re.compile(r"^\S+ telemetry stream lost: (?P<device>\S+) subscription (?P<sub>\d+)$")
#: A subscription's receiver as intent holds it (the IOS-XE parser keeps each line).
RECEIVER = re.compile(r"^receiver ip address (?P<address>\S+) (?P<port>\d+)"
                      r"(?: protocol (?P<protocol>\S+))?\s*$")
_SOURCE_VRF = re.compile(r"^source-vrf (?P<vrf>\S+)\s*$")
_SOURCE_ADDRESS = re.compile(r"^source-address (?P<address>\S+)\s*$")
#: A subscription id, one token (`diagnose.render`'s own shape for it).
SUBSCRIPTION = D._SUBSCRIPTION
#: Each family's ping to a collector (`diagnose.TEMPLATES`'s reach pings, unsourced: the
#: stream leaves by the device's routing, as the ping does).
PING = {4: "reach_ping", 6: "reach_ping6"}
#: The TCP states the kernel's socket tables print, by their code (include/net/tcp_states.h).
TCP_STATES = {"01": "ESTABLISHED", "02": "SYN-SENT", "03": "SYN-RECV", "04": "FIN-WAIT-1",
              "05": "FIN-WAIT-2", "06": "TIME-WAIT", "07": "CLOSE", "08": "CLOSE-WAIT",
              "09": "LAST-ACK", "0A": "LISTEN", "0B": "CLOSING", "0C": "NEW-SYN-RECV"}
LISTEN, ESTABLISHED = "LISTEN", "ESTABLISHED"
#: What to do next when the stream is stuck at its ends: the operator's sequence (C2838), the
#: operation `modules/heal/resubscribe.py` runs.
RECOVERY = ("Re-subscribe {host}'s streams from the lost stream's row on Needs attention: for "
            "each lost subscription Mercury will remove its receiver, wait about 10 s, add it "
            "back and check its state")
#: A receiver answer the parser could not read, as a hypothesis's incomplete evidence says it.
RECEIVER_UNREAD = ("not read as a receiver's detail; the parser is built on captures of the "
                   "Connected form only (C2890), and the masked answer is on History › Reads")
#: The lost-stream alert's own query for one subscription (scripts/nmas-telemetry-rules,
#: `rule_for`), read to tell whether the stream is back (C2892).
SERIES_QUERY = 'count(last_over_time({{device="{device}", subscription="{sub}"}}[{window}s]))'
#: A device's name as a PromQL label value: one token, nothing a query could be spliced with.
_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class Refused(D.Refused):
    """The runbook asks no device; the words say why."""


def _hhmm(epoch: float) -> str:
    return time.strftime("%H:%M", time.gmtime(float(epoch)))


def _ago(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 120:
        return f"{s} s"
    if s < 7200:
        return f"{s // 60} minutes"
    return f"{s // 3600} hours"


def _and(items) -> str:
    items = list(items)
    return " and ".join([", ".join(items[:-1]), items[-1]]) if len(items) > 1 else (
        items[0] if items else "")


def _subs_words(subs) -> str:
    subs = list(subs)
    return ("subscription " if len(subs) == 1 else "subscriptions ") + _and(subs)


# ── Which triggers are a lost stream ────────────────────────────────────────────────────────

def stream_of(trigger: dict) -> dict:
    """``{"subscription", "detect_s"}`` when *trigger* is a lost-stream alert, else ``{}``: the
    subscription its labels carried (`triggers.from_alerts`), or the one its rule's title
    names (the generator's own title, anchored)."""
    t = trigger if isinstance(trigger, dict) else {}
    if t.get("kind") != "alert":
        return {}
    sub = str(t.get("subscription") or "")
    if not sub:
        m = TITLE.match(str(t.get("rule") or "").strip())
        sub = m.group("sub") if m else ""
    if not SUBSCRIPTION.fullmatch(sub):
        return {}
    try:
        detect = int(t.get("detect_seconds") or 0)
    except (TypeError, ValueError):
        detect = 0
    return {"subscription": sub, "detect_s": detect}


def _epoch(t: dict) -> float:
    try:
        return float((t or {}).get("epoch") or 0)
    except (TypeError, ValueError):
        return 0.0


def target_from(incident: dict, every=None, decided=None) -> dict:
    """The runbook's target for *incident* when a trigger of its own is a lost stream, else
    ``{}``: ``{"device", "subscriptions", "lost_at", "settle_s", "cause"}``. *every* is the
    network's incidents (open and closed), *decided* its decisions; either None reads the
    cause as not read."""
    host = (incident or {}).get("device") or ""
    trig = [t for t in (incident or {}).get("triggers") or [] if isinstance(t, dict)]
    streams = [(t, stream_of(t)) for t in trig]
    streams = [(t, s) for t, s in streams if s]
    if not host or not streams:
        return {}
    subs = sorted({s["subscription"] for _t, s in streams}, key=int)
    lost_at = min((_epoch(t) for t, _s in streams if _epoch(t)), default=0.0)
    detect = max((s["detect_s"] for _t, s in streams), default=0) or ALERT_WINDOW_S
    return {"device": host, "subscriptions": subs, "lost_at": lost_at,
            "settle_s": detect + ALERT_INTERVAL_S,
            "cause": cause_of(incident, every, decided, lost_at)}


def cause_of(incident: dict, every, decided, lost_at: float) -> dict:
    """The stream's likely cause on another device, and whether it was put back:
    ``{"state", "device", "changed_at", "cleared_at", "how", "why"}``, *state* ``cleared``
    (a decision of nothing to heal read that device back at intent after its change: *how*
    is ``put back`` when a later configuration change on it came first, its time the
    ``cleared_at``; else ``read back at intent``, the decision's time), ``stands``, ``none``,
    ``several`` (devices changed and none is named: never a guess) or ``unread``. The likely
    cause is `said.likely_elsewhere`'s rule, over closed incidents too (a cause put back has
    usually closed)."""
    from modules.heal.said import LIKELY_S

    if every is None or decided is None:
        return {"state": "unread", "why": "the heal records were not read"}
    if not lost_at:
        return {"state": "none", "why": "the trigger carries no time the stream was lost"}
    host = (incident or {}).get("device") or ""
    related = {d for t in (incident or {}).get("triggers") or [] if isinstance(t, dict)
               for d in t.get("related") or []}
    found = []
    for other in every or []:
        dev = other.get("device") or ""
        if not dev or dev == host or other.get("id") == (incident or {}).get("id"):
            continue
        ch = [t for t in other.get("triggers") or [] if isinstance(t, dict)
              and t.get("kind") == "config_change" and lost_at - LIKELY_S <= _epoch(t) <= lost_at]
        if ch:
            found.append({"device": dev, "incident": other, "epoch": _epoch(max(ch, key=_epoch))})
    named = [f for f in found if f["device"] in related]
    devices = sorted({f["device"] for f in found})
    pick = named or (found if len(devices) == 1 else [])
    if not pick:
        if len(devices) > 1:
            return {"state": "several", "why": (
                f"{_and(devices)} each changed in the {LIKELY_S // 60} minutes before the "
                "stream was lost, so none is named as its cause")}
        return {"state": "none", "why": (
            f"no change on another device is in the heal records for the {LIKELY_S // 60} "
            "minutes before the stream was lost")}
    f = max(pick, key=lambda x: x["epoch"])
    inc = f["incident"]
    out = {"device": f["device"], "changed_at": f["epoch"]}
    later = sorted((d for d in decided or [] if d.get("incident") == inc.get("id")
                    and d.get("outcome") == "nothing" and _epoch(d) > f["epoch"]), key=_epoch)
    if not later:
        return dict(out, state="stands", why="")
    read = _epoch(later[0])
    back = [t for t in inc.get("triggers") or [] if isinstance(t, dict)
            and t.get("kind") == "config_change" and f["epoch"] < _epoch(t) <= read]
    if back:
        return dict(out, state="cleared", cleared_at=_epoch(max(back, key=_epoch)),
                    how="put back", why="")
    return dict(out, state="cleared", cleared_at=read, how="read back at intent", why="")


# ── The plan: from intent alone ─────────────────────────────────────────────────────────────

def _addresses(hv: dict) -> list:
    """Every IPv4 and IPv6 address intent gives the device's interfaces: the addresses a
    session from it can come from."""
    from modules.heal.diagnose_reach import _addresses as of
    out = []
    for iface in (hv or {}).get("interfaces") or []:
        for family in (4, 6):
            out += [str(ip.ip) for ip in of(iface, family)]
    return list(dict.fromkeys(out))


def receiver_of(settings) -> dict:
    """One subscription's receiver from intent's lines: ``{"address", "port", "protocol",
    "vrf", "source"}``, or ``{"why"}`` when intent states no address and port for it."""
    rec, vrf, source = None, "", ""
    for line in settings or []:
        text = str(line).strip()
        m = RECEIVER.match(text)
        if m:
            rec = m
        m = _SOURCE_VRF.match(text)
        if m:
            vrf = m.group("vrf")
        m = _SOURCE_ADDRESS.match(text)
        if m:
            source = m.group("address")
    if rec is None:
        return {"why": "intent gives it no receiver address and port"}
    try:
        address = ipaddress.ip_address(rec.group("address"))
    except ValueError:
        return {"why": f"its receiver {rec.group('address')!r} is not one IPv4 or IPv6 address"}
    port = int(rec.group("port"))
    if not 0 < port < 65536:
        return {"why": f"its receiver's port {port} is not a TCP port"}
    return {"address": str(address), "port": port, "protocol": rec.group("protocol") or "",
            "vrf": vrf, "source": source}


def plan(network: str, target: dict, lines: dict) -> dict:
    """The run *target* would make, from intent alone: the device, its lost subscriptions and
    their collectors, every read on the device and the worst case. Raises Refused naming
    why, with nothing read."""
    a = str((target or {}).get("device") or "")
    if a not in lines:
        raise Refused(f"{a or 'no device'} has no committed intent in {network}, so there is "
                      "no stream to compare with")
    hv = lines[a]
    declared = {str(s.get("subscription")): s.get("settings") or []
                for s in hv.get("telemetry") or [] if isinstance(s, dict)}
    if not declared:
        raise Refused(f"intent declares no telemetry subscription on {a}, so no stream is "
                      "expected from it")
    asked = [str(s) for s in (target or {}).get("subscriptions") or []]
    bad = [s for s in asked if not SUBSCRIPTION.fullmatch(s)]
    if bad:
        raise Refused(f"{bad[0]!r} is not a subscription id")
    notes = []
    absent = [s for s in asked if s not in declared]
    if absent:
        notes.append(f"{_subs_words(absent)} {'is' if len(absent) == 1 else 'are'} not in "
                     f"{a}'s intent, so not read")
    subs = [s for s in asked if s in declared] or ([] if asked else sorted(declared, key=int))
    if not subs:
        raise Refused(f"intent declares none of {_subs_words(asked)} on {a}, so no stream of "
                      "them is expected")
    dialect = D.dialect_of(hv.get("platform"), a)
    receivers, collectors = {}, {}
    for s in subs:
        r = receiver_of(declared[s])
        receivers[s] = r
        if r.get("why"):
            notes.append(f"subscription {s}'s collector is not read: {r['why']}")
            continue
        key = f"{r['address']} port {r['port']}"
        c = collectors.setdefault(key, dict(r, key=key, subscriptions=[]))
        c["subscriptions"].append(s)
    reads = [{"kind": "telemetry_brief", "command": D.render("telemetry_brief", dialect)}]
    reads += [{"kind": "telemetry_receiver", "sub": s,
               "command": D.render("telemetry_receiver", dialect, sub=s)} for s in subs]
    pinged = set()
    for c in collectors.values():
        if c["vrf"]:
            notes.append(f"the stream to {c['key']} leaves by VRF {c['vrf']}, which the ping "
                         "does not take, so it is not pinged")
            continue
        if c["address"] in pinged:
            continue
        pinged.add(c["address"])
        kind = PING[ipaddress.ip_address(c["address"]).version]
        reads.append({"kind": kind, "collector": c["key"],
                      "command": D.render(kind, dialect, dest=c["address"])})
    if len(reads) > D.MAX_PER_DEVICE:
        raise Refused(f"{len(reads)} reads on {a}, past the {D.MAX_PER_DEVICE} a device may be "
                      "asked in one diagnosis")
    where = _and(sorted(collectors)) or "no collector intent names"
    return {"network": network, "runbook": RUNBOOK, "runbook_words": D.RUNBOOKS[RUNBOOK],
            "target": dict(target or {}, device=a, subscriptions=subs),
            "words": f"{a}'s {_subs_words(subs)} to {where}", "source": a,
            "dialect": dialect, "subscriptions": subs, "receivers": receivers,
            "collectors": list(collectors.values()), "addresses": _addresses(hv),
            "reads": {a: reads}, "count": len(reads), "cap": D.MAX_COMMANDS, "ends": [],
            "outside": "; ".join(notes),
            "worst_s": sum(D._bound(c["command"]) for c in reads)}


# ── The collector's side: the kernel's socket tables on Mercury's host ──────────────────────

def _hex_ip(text: str):
    """An address as /proc/net/tcp{,6} prints it (each 32-bit word in host byte order), an
    IPv4-mapped IPv6 address read as its IPv4 address."""
    raw = bytes.fromhex(text)
    if sys.byteorder == "little":
        raw = b"".join(raw[i:i + 4][::-1] for i in range(0, len(raw), 4))
    if len(raw) == 4:
        return ipaddress.IPv4Address(raw)
    got = ipaddress.IPv6Address(raw)
    return got.ipv4_mapped or got


def sockets(proc: str = "/proc") -> tuple:
    """``(rows, why)``: every TCP socket of both families, ``{"local", "lport", "remote",
    "rport", "state", "family"}`` (*family* the table's: 6 for a dual-stack socket even when
    its addresses are IPv4), or ``([], why)`` when a table cannot be read."""
    rows = []
    for name, family in (("tcp", 4), ("tcp6", 6)):
        path = os.path.join(proc, "net", name)
        try:
            with open(path, encoding="ascii") as fh:
                text = fh.read()
        except OSError as exc:
            return [], f"{path} could not be read ({type(exc).__name__})"
        for line in text.splitlines()[1:]:
            w = line.split()
            if len(w) < 4 or ":" not in w[1] or ":" not in w[2]:
                continue
            try:
                (la, lp), (ra, rp) = w[1].rsplit(":", 1), w[2].rsplit(":", 1)
                rows.append({"local": _hex_ip(la), "lport": int(lp, 16),
                             "remote": _hex_ip(ra), "rport": int(rp, 16),
                             "state": TCP_STATES.get(w[3].upper(), w[3]), "family": family})
            except ValueError:
                return [], f"{path} holds a line this reader cannot read"
    return rows, ""


_TRIE_LEAF = re.compile(r"^\s*\|--\s+(?P<address>\d+\.\d+\.\d+\.\d+)\s*$")
_TRIE_LOCAL = re.compile(r"^\s*/32 host LOCAL\s*$")


def local_addresses(proc: str = "/proc") -> tuple:
    """``(addresses, why)``: this host's own IPv4 addresses (the routing trie's ``/32 host
    LOCAL`` leaves) and IPv6 addresses (``net/if_inet6``)."""
    out = set()
    try:
        with open(os.path.join(proc, "net", "fib_trie"), encoding="ascii") as fh:
            leaf = None
            for line in fh:
                m = _TRIE_LEAF.match(line)
                if m:
                    leaf = m.group("address")
                elif leaf and _TRIE_LOCAL.match(line):
                    out.add(ipaddress.IPv4Address(leaf))
        with open(os.path.join(proc, "net", "if_inet6"), encoding="ascii") as fh:
            for line in fh:
                w = line.split()
                if w and len(w[0]) == 32:
                    out.add(ipaddress.IPv6Address(bytes.fromhex(w[0])))
    except (OSError, ValueError) as exc:
        return set(), f"this host's addresses could not be read ({type(exc).__name__})"
    return out, ""


def _v6only(proc: str) -> bool:
    """Whether a wildcard IPv6 listener here takes IPv6 only (``net.ipv6.bindv6only``; its
    default 0: it takes IPv4 too)."""
    try:
        with open(os.path.join(proc, "sys", "net", "ipv6", "bindv6only"), encoding="ascii") as fh:
            return fh.read().strip() == "1"
    except OSError:
        return False


#: Each session's last receive, from the kernel's socket diagnostics (inet_diag) as `ss -tni`
#: prints them (C2892; tests/fixtures/diagnose/collector/README.md): a session line, then its
#: indented detail line holding ``bytes_received:<n>`` and ``lastrcv:<ms>``.
SS_COMMAND = ("ss", "-tni", "state", "established")
_SS_SESSION = re.compile(r"^\s*\d+\s+\d+\s+(?P<local>\S+):(?P<lport>\d+)\s+"
                         r"(?P<remote>\S+):(?P<rport>\d+)\s*$")
_SS_FIELD = re.compile(r"\b(bytes_received|lastrcv):(\d+)\b")
#: `ss` answered in well under a second on the development laptop (2026-11-10); a local read
#: of the kernel's tables, bounded at 5 s so a hung one is named, never waited on.
SS_TIMEOUT_S = 5


def _ss_address(text: str):
    t = text[1:-1] if text.startswith("[") and text.endswith("]") else text
    got = ipaddress.ip_address(t.split("%", 1)[0])
    return getattr(got, "ipv4_mapped", None) or got


def parse_ss(text: str) -> tuple:
    """``(rows, why)``: each established session `ss -tni` printed, ``{"local", "lport",
    "remote", "rport", "bytes_received", "lastrcv_ms"}`` (an IPv4-mapped IPv6 address read as
    its IPv4 address; a field the detail line lacks is None), or ``([], why)`` when the answer
    holds no heading `ss` prints."""
    lines = (text or "").splitlines()
    if not lines or not lines[0].startswith("Recv-Q"):
        return [], "the answer is not `ss`'s table (no Recv-Q heading)"
    rows = []
    for line in lines[1:]:
        m = _SS_SESSION.match(line)
        if m:
            try:
                rows.append({"local": _ss_address(m.group("local")),
                             "lport": int(m.group("lport")),
                             "remote": _ss_address(m.group("remote")),
                             "rport": int(m.group("rport")),
                             "bytes_received": None, "lastrcv_ms": None})
            except ValueError:
                return [], f"`ss` printed a session this reader cannot read: {line.strip()!r}"
            continue
        if rows and line[:1].isspace():
            for name, value in _SS_FIELD.findall(line):
                rows[-1]["lastrcv_ms" if name == "lastrcv" else name] = int(value)
    return rows, ""


def receiving_now(session: dict):
    """Whether *session* (`read_collector`'s) received a segment inside the stream's window
    (`ALERT_WINDOW_S`, the lost-stream alert's own window): True, False, or None when its last
    receive was not read (the /proc tables alone: can't tell)."""
    ms = (session or {}).get("lastrcv_ms")
    if ms is None:
        return None
    return int(ms) <= ALERT_WINDOW_S * 1000


def run_ss(port: int) -> tuple:
    """``(text, why)``: `ss -tni state established "( sport = :<port> )"` on this host, a local
    read (no shell, no root, nothing written), or ``("", why)``."""
    import subprocess

    try:
        got = subprocess.run([*SS_COMMAND, f"( sport = :{int(port)} )"], capture_output=True,
                             text=True, timeout=SS_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return "", f"`ss` could not be run ({type(exc).__name__})"
    if got.returncode != 0:
        return "", f"`ss` exited {got.returncode}"
    return got.stdout, ""


def read_collector(address: str, port: int, sources, proc: str = "/proc", ss=None) -> dict:
    """The collector's side of one stream, read on this host: ``{"state", "why", "address",
    "port", "listening", "sessions", "others", "activity"}``. *state* ``read``, ``elsewhere``
    (*address* is not this host's: nothing is read) or ``unread`` (a table could not be read).
    *listening* names each listener on *port* that takes *address* (bound to it, or a wildcard
    of its family, or IPv6's wildcard taking IPv4 unless bindv6only); *sessions* each socket on
    *port* at *address* whose far end is one of *sources* (the device's addresses), with its
    state and, from the kernel's socket diagnostics (`ss`, C2892), its ``bytes_received`` and
    ``lastrcv_ms`` (None when they were not read: /proc carries neither, so "can't tell");
    *others* the established sessions there from any other address. The two fields are on a
    session only when the diagnostics were read. *ss(port) -> (text, why)*
    reads the diagnostics: `run_ss` on this host's own /proc, none on another (a test's
    tables); *activity* says whether they were read."""
    want = ipaddress.ip_address(address)
    src = set()
    for s in sources or []:
        try:
            src.add(ipaddress.ip_address(s))
        except ValueError:
            continue
    base = {"address": str(want), "port": int(port), "listening": [], "sessions": [],
            "others": 0}
    rows, why = sockets(proc)
    if why:
        return dict(base, state="unread", why=why)
    mine, why = local_addresses(proc)
    if why:
        return dict(base, state="unread", why=why)
    if want not in mine and not any(r["local"] == want for r in rows):
        return dict(base, state="elsewhere", why=(
            f"{want} is not an address of Mercury's host, so the collector's listener and "
            "sessions are not read here"))
    v6only = _v6only(proc)
    for r in rows:
        if r["lport"] != int(port):
            continue
        local = r["local"]
        if r["state"] == LISTEN:
            takes = (local == want or (local.is_unspecified and local.version == want.version)
                     or (local.is_unspecified and local.version == 6 and want.version == 4
                         and not v6only))
            if takes:
                base["listening"].append(f"[{local}]:{port}" if local.version == 6
                                         else f"{local}:{port}")
            continue
        if local != want:
            continue
        if r["remote"] in src:
            base["sessions"].append({"remote": str(r["remote"]), "rport": r["rport"],
                                     "state": r["state"]})
        elif r["state"] == ESTABLISHED:
            base["others"] += 1
    if ss is None and proc == "/proc":
        ss = run_ss
    if ss is None:
        base["activity"] = "not read: the socket diagnostics are read on this host only"
    else:
        text, why = ss(int(port))
        rows, why = parse_ss(text) if not why else ([], why)
        if why:
            base["activity"] = f"not read: {why}"
        else:
            seen = {(str(x["remote"]), x["rport"]): x for x in rows
                    if x["lport"] == int(port) and x["local"] == want}
            for s in base["sessions"]:
                x = seen.get((s["remote"], s["rport"])) or {}
                s["bytes_received"] = x.get("bytes_received")
                s["lastrcv_ms"] = x.get("lastrcv_ms")
            base["activity"] = "read"
    return dict(base, state="read", why="")


# ── The stream itself: its series in Prometheus (C2892) ─────────────────────────────────────

def series_of(device: str, sub: str, prom=None) -> dict:
    """Whether *device*'s subscription *sub* has data now, by the lost-stream alert's own query
    (`SERIES_QUERY`, its window `ALERT_WINDOW_S`) through Mercury's Prometheus client:
    ``{"state", "count", "why", "query"}``, *state* ``present`` (a sample in the window),
    ``absent`` (none: the stream is still lost) or ``unread`` (Prometheus not configured, not
    answering, or a name that is not one label token), which decides nothing."""
    query = ""
    if not _LABEL.match(str(device or "")) or not SUBSCRIPTION.fullmatch(str(sub or "")):
        return {"state": "unread", "count": None, "query": query,
                "why": f"{device!r} subscription {sub!r} is not one device name and one "
                       "subscription id, so no query is made of them"}
    query = SERIES_QUERY.format(device=device, sub=sub, window=ALERT_WINDOW_S)
    try:
        if prom is None:
            from modules.integrations.prometheus import PrometheusIntegration
            prom = PrometheusIntegration()
        if not prom.is_configured():
            return {"state": "unread", "count": None, "query": query,
                    "why": "Prometheus is not configured"}
        got = prom._get("api/v1/query", query=query)
        if not got.get("ok"):
            return {"state": "unread", "count": None, "query": query,
                    "why": f"Prometheus could not be asked: {got.get('error')}"}
        result = ((got["response"].json() or {}).get("data") or {}).get("result") or []
        count = sum(float(r["value"][1]) for r in result)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        return {"state": "unread", "count": None, "query": query,
                "why": f"Prometheus's answer could not be read ({type(exc).__name__})"}
    if count > 0:
        return {"state": "present", "count": int(count), "query": query,
                "why": f"{int(count)} series with a sample in the last {ALERT_WINDOW_S} s"}
    return {"state": "absent", "count": 0, "query": query,
            "why": f"no sample in the last {ALERT_WINDOW_S} s"}


# ── The run ─────────────────────────────────────────────────────────────────────────────────

def _step(p: dict, ans: dict) -> dict:
    """The device batch's step: each read in words, by its reference."""
    from modules.nsot import reads
    a = p["source"]
    if ans["state"] == reads.SKIPPED:
        return {"step": "read", "device": a, "result": "not_read",
                "words": f"not read: {ans['why']}"}
    if ans["state"] in ("refused", "failed", reads.UNKNOWN) or not ans["answers"]:
        return {"step": "read", "device": a, "result": "failed",
                "words": f"not read: {ans.get('why') or ans['state']}"}
    parts = []
    for c in p["reads"][a]:
        if c["kind"] == "telemetry_receiver":
            parts.append(f"subscription {c['sub']}'s receiver as {a} holds it")
        elif c["kind"] == "telemetry_brief":
            parts.append(f"{a}'s subscriptions and their states")
        else:
            parts.append(f"{a} reaching its collector {c['collector']}")
    return {"step": "read", "device": a, "result": "ok",
            "reads": [D.ref(ans["run"], a, c["command"]) for c in p["reads"][a]],
            "words": f"{len(parts)} read(s) on {a}: " + "; ".join(parts)}


def run_plan(p: dict, out: dict, actor: str, *, session=None, logs=None, collector=None,
             series=None, started: float = 0.0) -> None:
    """Run the plan *p* into the diagnosis *out* (`diagnose.run`'s, recorded by it).
    *collector* is ``collector(address, port, sources) -> read_collector's answer`` (tests);
    *series* ``series(device, sub) -> series_of's answer`` (tests); *logs* `diagnose._logs`'
    shape."""
    network, a = p["network"], p["source"]
    out["devices"] = [a]
    out["steps"].append({"step": "plan", "result": "ok", "words": (
        f"\"{p['runbook_words']}\" on {p['words']}: {p['count']} reads on {a}, at most "
        f"{p['cap']}; the collector's side read on Mercury's host" + (
            f"; {p['outside']}" if p["outside"] else ""))})
    cmds = [c["command"] for c in p["reads"][a]]
    try:
        with D.DiagnosisLock(network, [a], out["id"], actor):
            out["steps"].append({"step": "hold", "result": "ok",
                                 "words": f"held for this diagnosis: {a}"})
            ans = D._reads_engine(network, a, cmds, actor, f"diagnosis {out['id']}", session)
            out["commands"] += len(cmds)
            if ans.get("run"):
                out["runs"].append(ans["run"])
            out["steps"].append(_step(p, ans))
            got_logs = (logs or D._logs)(network, a, started)
    except D.DiagnosisBusy as exc:
        out.update(state="busy", words=str(exc))
        out["steps"].append({"step": "hold", "result": "refused", "words": str(exc)})
        return
    read = collector or read_collector
    ctx = StreamContext(p, ans, started)
    for c in p["collectors"]:
        try:
            got = read(c["address"], c["port"], p["addresses"])
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            got = {"state": "unread", "why": f"the read failed ({type(exc).__name__})"}
        ctx.collectors[c["key"]] = got
        words = (f"the collector at {c['key']}: " + (
            f"{len(got.get('listening') or [])} listener(s), "
            f"{len(got.get('sessions') or [])} session(s) from {a}, "
            f"{got.get('others') or 0} established from other addresses"
            if got.get("state") == "read" else f"not read: {got.get('why')}"))
        out["steps"].append({"step": "collector", "result": "ok" if got.get("state") == "read"
                             else "not_read", "words": words})
    ask = series or series_of
    for s in p["subscriptions"]:
        try:
            ctx.series[s] = ask(a, s)
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            ctx.series[s] = {"state": "unread", "why": f"the read failed ({type(exc).__name__})"}
    out["steps"].append({"step": "stream", "result": "ok" if all(
        v.get("state") != "unread" for v in ctx.series.values()) else "not_read",
        "words": "the stream's own series in Prometheus: " + "; ".join(
            f"subscription {s}: {v.get('state')} ({v.get('why')})"
            for s, v in ctx.series.items())})
    cause = (p["target"].get("cause") or {"state": "unread",
                                           "why": "no incident's records were given"})
    ctx.cause = cause
    out["steps"].append({"step": "cause", "result": "ok" if cause.get("state") in (
        "cleared", "stands") else "not_read", "words": _cause_step(cause)})
    g = got_logs if isinstance(got_logs, dict) else {"state": "unread", "why": str(got_logs),
                                                     "lines": []}
    ctx.logs = {a: g}
    out["steps"].append({"step": "logs", "device": a,
                         "result": "ok" if g["state"] == "read" else "not_read",
                         "words": (f"{len(g['lines'])} configuration line(s) logged in the last "
                                   "hour" if g["state"] == "read" else
                                   f"the log was not read: {g['why']}")})
    D._judge(ctx, out, STREAM_RULES)
    # A check a rule could not make says why in this runbook's own words.
    for n in out["not_checked"]:
        why = ctx.why_not.get(n.get("rule") or "")
        if why:
            n["why"] = why


def _cause_step(cause: dict) -> str:
    state = cause.get("state")
    if state == "cleared":
        return (f"{cause['device']} changed at {_hhmm(cause['changed_at'])} UTC and was "
                f"{cause['how']} at {_hhmm(cause['cleared_at'])} UTC (the heal records)")
    if state == "stands":
        return (f"{cause['device']} changed at {_hhmm(cause['changed_at'])} UTC, and no decision "
                "has read it back at intent since (the heal records)")
    return f"no cause named: {cause.get('why') or 'not read'}"


class StreamContext:
    """What the rules compare: the plan, the device's reads, each collector's sockets, the
    cause and the device's logs."""

    def __init__(self, p: dict, ans: dict, now: float):
        from modules.heal import diagnose_parse as P
        from modules.heal.diagnose_reach import _answer
        self.plan, self.now, self.host = p, float(now or time.time()), p["source"]
        self.answered = ans.get("state") not in ("refused", "failed", "skipped", "unknown") \
            and bool(ans.get("answers"))
        self.device_why = ans.get("why") or ans.get("state") or ""
        self.device_failed = ans.get("state") in ("failed", "unknown")
        self.brief, self.brief_ref, self.brief_why = None, "", ""
        self.receivers, self.pings, self.series = {}, {}, {}
        self.collectors, self.cause, self.logs, self.why_not = {}, {}, {}, {}
        for c in p["reads"][self.host]:
            text, ref, why = _answer(ans, self.host, c["command"])
            if c["kind"] == "telemetry_receiver":
                # The device's own side of the stream's session (C2890): its receivers for
                # this subscription, each State and Connection as the device printed them.
                rows = None
                if text is not None:
                    got = P.parse("telemetry_receiver", text)
                    if got["state"] == P.PARSED:
                        rows = got["facts"]["receivers"]
                    else:
                        why = f"{got['why']}; {RECEIVER_UNREAD}"
                self.receivers[c["sub"]] = {"ref": ref, "rows": rows,
                                            "why": "" if rows is not None else
                                            (why or RECEIVER_UNREAD)}
                continue
            facts = None
            if text is not None:
                got = P.parse("telemetry_brief" if c["kind"] == "telemetry_brief"
                              else "reach_ping", text)
                facts = got["facts"] if got["state"] == P.PARSED else None
                why = "" if facts is not None else got["why"]
            if c["kind"] == "telemetry_brief":
                self.brief, self.brief_ref, self.brief_why = facts, ref, why
            else:
                self.pings[c["collector"]] = {"facts": facts, "ref": ref, "why": why,
                                              "command": c["command"]}

    def receiver_incomplete(self, subs=None) -> list:
        """Each of *subs*' receivers (every lost subscription's by default) the device's answer
        did not give: why it is not read. One read is not missing."""
        return [f"subscription {s}'s receiver on {self.host} "
                f"(`{D.render('telemetry_receiver', self.plan['dialect'], sub=s)}`): "
                f"{self.receivers.get(s, {}).get('why') or RECEIVER_UNREAD}"
                for s in (self.plan["subscriptions"] if subs is None else subs)
                if (self.receivers.get(s) or {}).get("rows") is None]

    def receiver_words(self, sub: str) -> str:
        """What the device says of *sub*'s receivers, as it printed them; ``""`` unread."""
        rows = (self.receivers.get(sub) or {}).get("rows")
        if rows is None:
            return ""
        if not rows:
            return f"{self.host} holds no receiver for subscription {sub}"
        return "; ".join(
            f"{self.host} reads subscription {sub}'s receiver {r['address']} port {r['port']} "
            f"{r['state']}" + (f" on connection {r['connection']}" if r["connection"] else "")
            + (f" ({r['explanation']})" if r["explanation"] else "") for r in rows)

    def receiver_ev(self, subs) -> list:
        """The device's receiver reads for *subs* as evidence, those that were read."""
        out = []
        for s in subs:
            rows = (self.receivers.get(s) or {}).get("rows")
            if rows is None:
                continue
            got = "; ".join(f"State {r['state']}" + (f", connection {r['connection']}"
                                                      if r["connection"] else "")
                            for r in rows) or "no receiver"
            out.append(D.ev(self.receivers[s]["ref"], got))
        return out

    def flowing(self, subs) -> list:
        """The subscriptions of *subs* whose series is in Prometheus now (C2892)."""
        return [s for s in subs if (self.series.get(s) or {}).get("state") == "present"]


def _sockets_ref(c: dict) -> str:
    """Where the collector's facts came from, in words (no run: a local read)."""
    return f"the TCP sockets on Mercury's host, port {c['port']}"


# ── The rules (`STREAM_RULES`) ──────────────────────────────────────────────────────────────

def _r_device_unread(rule, ctx):
    if ctx.answered:
        return [], f"Mercury reads {ctx.host}"
    if not ctx.device_failed:
        ctx.why_not[rule.name] = f"{ctx.host} was not read: {ctx.device_why}"
        return [], ""
    return [D.finding(rule, f"Mercury cannot read {ctx.host} either ({ctx.device_why}): the "
                      f"stream and Mercury's own path to {ctx.host} are both cut, so the path "
                      f"to {ctx.host} is the place to look", [],
                      rule_out=f"Mercury reading {ctx.host}",
                      todo=f"Run Can't reach toward {ctx.host} from its neighbour")], ""


def _r_stream_missing(rule, ctx):
    if ctx.brief is None:
        ctx.why_not[rule.name] = ctx.brief_why or "the subscriptions were not read"
        return [], ""
    gone = [s for s in ctx.plan["subscriptions"] if s not in ctx.brief]
    if not gone:
        return [], (f"{ctx.host} holds {_subs_words(ctx.plan['subscriptions'])}, as intent "
                    "declares")
    return [D.finding(rule, f"{ctx.host} holds no {_subs_words(gone)}, though intent declares "
                      f"{'it' if len(gone) == 1 else 'them'}: removed outside intent",
                      [D.ev(ctx.brief_ref, f"{_subs_words(gone)} absent",
                            f"telemetry ietf subscription {gone[0]}")],
                      rule_out=f"{_subs_words(gone)} listed on {ctx.host}",
                      todo="Check drift now…: it departs from intent")], ""


def _r_stream_invalid(rule, ctx):
    if ctx.brief is None:
        ctx.why_not[rule.name] = ctx.brief_why or "the subscriptions were not read"
        return [], ""
    held = [s for s in ctx.plan["subscriptions"] if s in ctx.brief]
    bad = [s for s in held if ctx.brief[s]["state"].lower() != "valid"]
    if not held:
        ctx.why_not[rule.name] = f"{ctx.host} holds none of them"
        return [], ""
    if not bad:
        return [], f"{ctx.host}'s {_subs_words(held)} read Valid"
    s = bad[0]
    return [D.finding(rule, f"{ctx.host}'s subscription {s} reads {ctx.brief[s]['state']}: "
                      f"{ctx.host} does not accept it (its filter, encoding or source)",
                      [D.ev(ctx.brief_ref, f"{s} {ctx.brief[s]['type']} "
                            f"{ctx.brief[s]['state']}", "Valid")],
                      rule_out=f"subscription {s} reading Valid", agree=len(bad),
                      todo=f"Compare subscription {s} with {ctx.host}'s intent")], ""


def _r_collector_unreached(rule, ctx):
    hits, passed, pings = [], [], sorted(ctx.pings.items())
    for key, got in pings:
        f = got["facts"]
        if f is None:
            continue
        address = key.split(" port ", 1)[0]
        line = f"{f['received']} of {f['sent']} answered"
        if f["all"]:
            passed.append(f"{ctx.host} reaches the collector {address}: {line}")
            continue
        hits.append(D.finding(
            rule, (f"{ctx.host} reaches the collector {address} only some of the time ({line})"
                   if f["reached"] else
                   f"{ctx.host} does not reach the collector {address} ({line})"),
            [D.ev(got["ref"], line)], strength="decisive" if not f["reached"] else "strong",
            rule_out=f"{ctx.host}'s ping to {address} answered",
            todo=f"Run Can't reach from {ctx.host} to {address}"))
    if not pings:
        ctx.why_not[rule.name] = "no collector address was pinged"
    elif not hits and len(passed) < len(pings):
        ctx.why_not[rule.name] = "; ".join(g["why"] for _k, g in pings if g["facts"] is None)
    return hits, ("; ".join(passed) if passed and not hits and len(passed) == len(pings)
                  else "")


def _collectors_read(ctx, rule) -> list:
    got = [(c, ctx.collectors.get(c["key"]) or {}) for c in ctx.plan["collectors"]]
    unread = [f"{c['key']}: {g.get('why') or 'not read'}" for c, g in got
              if g.get("state") != "read"]
    if unread:
        ctx.why_not[rule.name] = "; ".join(unread)
    return [(c, g) for c, g in got if g.get("state") == "read"]


def _r_collector_down(rule, ctx):
    hits, ok = [], []
    for c, g in _collectors_read(ctx, rule):
        if g["listening"]:
            ok.append(f"the collector listens on {c['key']}, with {g['others']} established "
                      "session(s) from other addresses")
            continue
        hits.append(D.finding(rule, f"nothing on Mercury's host listens on {c['key']}: the "
                              "collector (Telegraf) is stopped, or listens on another port",
                              [D.ev(_sockets_ref(c), f"no listener on port {c['port']}")],
                              rule_out=f"a listener on {c['key']}",
                              todo="Start the collector on Mercury's host: Mercury has no "
                                   "operation that does this yet"))
    return hits, ("; ".join(ok) if ok and not hits else "")


def _device_side(ctx, subs) -> str:
    """The device's own words for its receivers of *subs*, as a clause; ``""`` unread."""
    said = [w for w in (ctx.receiver_words(s) for s in subs) if w]
    return f"; {'; '.join(said)}" if said else ""


def _half_open_facts(ctx, subs, session: dict) -> dict:
    """The half-open finding's facts, kept beside its claim so a screen can say them in fewer
    words (Needs attention's "Mercury's diagnosis" line, `modules/heal/seen_before.py`):
    ``{"session", "quiet_s", "connections", "connected"}``. *session* is the far end of the
    session the collector holds (the device's address and port, IPv4 or IPv6, as the socket
    table gave it); *quiet_s* how long nothing was received on it (None: the kernel's socket
    diagnostics were not read); *connections* the connection ids the device's receivers for
    *subs* read; *connected* whether every receiver read reads Connected (None when one was
    not read, or the device holds none)."""
    rows = [r for s in subs for r in ((ctx.receivers.get(s) or {}).get("rows") or [])]
    unread = any((ctx.receivers.get(s) or {}).get("rows") is None for s in subs)
    ids = sorted({str(r["connection"]) for r in rows if r.get("connection")},
                 key=lambda x: (len(x), x))
    return {"session": f"{session['remote']} port {session['rport']}",
            "quiet_s": (int(session["lastrcv_ms"]) // 1000
                        if session.get("lastrcv_ms") is not None else None),
            "connections": ids,
            "connected": (None if unread or not rows else
                          all(r.get("state") == "Connected" for r in rows))}


def _r_half_open(rule, ctx):
    hits, none, live = [], [], []
    for c, g in _collectors_read(ctx, rule):
        if not g["listening"]:
            continue
        est = [s for s in g["sessions"] if s["state"] == ESTABLISHED]
        if not est:
            none.append(c["key"])
            continue
        subs = c["subscriptions"]
        flowing = ctx.flowing(subs)
        if flowing and len(flowing) == len(subs):
            # C2892: a session that carries data is not half-open; the sockets alone cannot
            # tell the two apart, the stream's own series can.
            live.append(f"the session from {ctx.host} on {c['key']} carries data: "
                        f"{_subs_words(flowing)} in Prometheus now")
            continue
        receiving = [s for s in est if receiving_now(s)]
        if receiving:
            # The kernel's socket diagnostics: a segment received inside the stream's window.
            s = receiving[0]
            live.append(f"the session from {ctx.host} ({s['remote']} port {s['rport']}) on "
                        f"{c['key']} received data {s['lastrcv_ms'] // 1000} s ago")
            continue
        s = est[0]
        quiet = (f", nothing received on it for {_ago(s['lastrcv_ms'] / 1000)}"
                 if s.get("lastrcv_ms") is not None else "")
        facts = _half_open_facts(ctx, subs, s)
        hits.append(dict(facts=facts, **D.finding(
            rule, (f"the collector still holds an established session from {ctx.host} "
                   f"({s['remote']} port {s['rport']}) on {c['key']}{quiet}, yet {ctx.host}'s "
                   "stream is lost: half-open, the collector holding it up while "
                   f"{ctx.host} has given it up" + _device_side(ctx, subs)),
            [D.ev(_sockets_ref(c), f"{s['remote']}:{s['rport']} {s['state']}"
                  + (f", lastrcv {s['lastrcv_ms']} ms, {s.get('bytes_received')} bytes "
                     "received" if s.get("lastrcv_ms") is not None else ""))]
            + ctx.receiver_ev(subs),
            incomplete=ctx.receiver_incomplete(subs), agree=len(est),
            rule_out=f"no established session from {ctx.host} on the collector",
            todo=RECOVERY.format(host=ctx.host))))
    if hits:
        return hits, ""
    return [], "; ".join(live + ([f"no session from {ctx.host} stands on the collector at "
                                  f"{_and(none)}"] if none else []))


def _r_no_session(rule, ctx):
    hits, held = [], []
    for c, g in _collectors_read(ctx, rule):
        if not g["listening"]:
            continue
        if g["sessions"]:
            held.append(c["key"])
            continue
        ping = ctx.pings.get(c["key"]) or next(
            (v for k, v in ctx.pings.items() if k.split(" port ")[0] == c["address"]), {})
        reaches = bool((ping.get("facts") or {}).get("all"))
        hits.append(D.finding(
            rule, (f"the collector listens on {c['key']} and holds no session from "
                   f"{ctx.host}" + (f", though {ctx.host} reaches it" if reaches else "")
                   + f": {ctx.host} is not dialling out to it, or something on the path drops "
                   f"port {c['port']}" + _device_side(ctx, c["subscriptions"])),
            [D.ev(_sockets_ref(c), f"no session from {ctx.host}'s addresses")]
            + ctx.receiver_ev(c["subscriptions"]),
            incomplete=ctx.receiver_incomplete(c["subscriptions"]),
            rule_out=f"a session from {ctx.host} on the collector",
            todo=RECOVERY.format(host=ctx.host) + f"; or find what drops port {c['port']} "
                                                  "on the path"))
    return hits, (f"the collector holds a session from {ctx.host} at {_and(held)}"
                  if held and not hits else "")


def _r_stream_flowing(rule, ctx):
    """C2892: the symptom-gone check. Every lost subscription's series in Prometheus now is
    the stream back, ruled out as a cause of anything; one absent is the symptom standing,
    said, and one unread decides nothing."""
    subs = ctx.plan["subscriptions"]
    got = {s: ctx.series.get(s) or {"state": "unread", "why": "not read"} for s in subs}
    unread = [s for s in subs if got[s].get("state") == "unread"]
    absent = [s for s in subs if got[s].get("state") == "absent"]
    if absent:
        ctx.why_not[rule.name] = (f"{_subs_words(absent)} on {ctx.host} "
                                  f"{'has' if len(absent) == 1 else 'have'} no sample in "
                                  f"Prometheus in the last {ALERT_WINDOW_S} s: the stream is "
                                  "still lost")
        return [], ""
    if unread:
        ctx.why_not[rule.name] = "; ".join(f"subscription {s}: {got[s].get('why')}"
                                           for s in unread)
        return [], ""
    return [], (f"{ctx.host}'s {_subs_words(subs)} {'has' if len(subs) == 1 else 'have'} data "
                f"in Prometheus now (a sample in the last {ALERT_WINDOW_S} s, the lost-stream "
                "alert's own query): the stream is back")


def _cause_ev(cause: dict) -> dict:
    return D.ev(f"the heal records of {cause['device']}",
                f"{cause['device']} changed at {_hhmm(cause['changed_at'])} UTC" + (
                    f", {cause['how']} at {_hhmm(cause['cleared_at'])} UTC"
                    if cause.get("cleared_at") else ""))


def _cause_why(ctx, rule, want: str) -> bool:
    cause = ctx.cause or {}
    if cause.get("state") in ("cleared", "stands"):
        if cause["state"] != want:
            ctx.why_not[rule.name] = (f"{cause['device']}'s change "
                                      + ("was put back" if cause["state"] == "cleared"
                                         else "still stands"))
        return cause["state"] == want
    ctx.why_not[rule.name] = cause.get("why") or "the heal records were not read"
    return False


def _r_outlived_cause(rule, ctx):
    if not _cause_why(ctx, rule, "cleared"):
        return [], ""
    cause, settle = ctx.cause, int(ctx.plan["target"].get("settle_s") or 0)
    age = ctx.now - float(cause["cleared_at"])
    if age < settle:
        ctx.why_not[rule.name] = (f"{cause['device']} was {cause['how']} {_ago(age)} ago, "
                                  "sooner than the lost-stream alert can clear")
        return [], ""
    return [D.finding(rule, (f"{ctx.host}'s telemetry hasn't recovered since "
                             f"{cause['device']} was {cause['how']} at "
                             f"{_hhmm(cause['cleared_at'])} UTC, {_ago(age)} before this "
                             "diagnosis: the stream outlived its cause, so it is stuck at "
                             f"{ctx.host} or the collector, not waiting on {cause['device']}"),
                      [_cause_ev(cause)],
                      rule_out=f"{cause['device']}'s change still standing",
                      todo=RECOVERY.format(host=ctx.host))], ""


def _r_cause_just_cleared(rule, ctx):
    if not _cause_why(ctx, rule, "cleared"):
        return [], ""
    cause, settle = ctx.cause, int(ctx.plan["target"].get("settle_s") or 0)
    age = ctx.now - float(cause["cleared_at"])
    if age >= settle:
        return [], (f"{cause['device']} was {cause['how']} {_ago(age)} before this "
                    f"diagnosis, longer than the lost-stream alert takes to clear ({settle} s)")
    return [D.finding(rule, (f"{cause['device']} was {cause['how']} at "
                             f"{_hhmm(cause['cleared_at'])} UTC, {_ago(age)} before this "
                             f"diagnosis, sooner than the lost-stream alert can clear "
                             f"({settle} s): {ctx.host}'s stream may be back already"),
                      [_cause_ev(cause)], rule_out="the alert's clearing time passing",
                      todo=(f"Diagnose again after "
                            f"{_hhmm(float(cause['cleared_at']) + settle)} UTC"))], ""


def _r_cause_stands(rule, ctx):
    if not _cause_why(ctx, rule, "stands"):
        return [], ""
    cause = ctx.cause
    return [D.finding(rule, (f"{cause['device']}'s change at {_hhmm(cause['changed_at'])} UTC, "
                             "the likely cause, has not been read back at intent: the stream "
                             "waits on it"), [_cause_ev(cause)],
                      rule_out=f"{cause['device']} read back at intent",
                      todo=f"Put {cause['device']} back to intent first: the stream follows")], ""


def _r_config_changed(rule, ctx):
    got = ctx.logs.get(ctx.host) or {}
    if got.get("state") != "read":
        ctx.why_not[rule.name] = f"the log was not read: {got.get('why') or 'not read'}"
        return [], ""
    if not got["lines"]:
        return [], f"no configuration change was logged on {ctx.host} in the last hour"
    last = got["lines"][0]
    return [D.finding(rule, f"{ctx.host}'s configuration was changed in the last hour "
                      f"({len(got['lines'])} line(s) logged, the last at {last['at']})",
                      [D.ev(":".join(("log", ctx.host, last["at"])), f"%{last['mnemonic']}")],
                      rule_out="no configuration line logged",
                      todo="Find who changed it on History")], ""


def _unless_back(fn):
    """A cause rule judged only while the stream is lost: with every lost subscription's series
    in Prometheus now (C2892) there is no symptom left to explain, so it is not checked, said."""
    def judged(rule, ctx):
        subs = ctx.plan["subscriptions"]
        if subs and len(ctx.flowing(subs)) == len(subs):
            ctx.why_not[rule.name] = (f"the stream is back ({_subs_words(subs)} in Prometheus "
                                      "now), so there is no lost stream to explain")
            return [], ""
        return fn(rule, ctx)
    return judged


STREAM_RULES = (
    D.Rule("stream_flowing", "protocol", "strong", "the stream's own series back in "
           "Prometheus", _r_stream_flowing),
    D.Rule("device_unread", "network", "strong", "the device not read by Mercury either",
           _unless_back(_r_device_unread)),
    D.Rule("stream_missing", "policy", "decisive",
           "a lost subscription missing on the device, though intent declares it",
           _unless_back(_r_stream_missing)),
    D.Rule("stream_invalid", "protocol", "decisive", "a lost subscription not Valid on the "
           "device", _unless_back(_r_stream_invalid)),
    D.Rule("collector_unreached", "network", "decisive", "the device not reaching its "
           "collector", _unless_back(_r_collector_unreached)),
    D.Rule("collector_down", "protocol", "decisive", "nothing listening on the stream's port "
           "on the collector", _unless_back(_r_collector_down)),
    D.Rule("half_open", "protocol", "strong", "a half-open session: the collector holding a "
           "session from the device while its stream is lost", _r_half_open),
    D.Rule("no_session", "protocol", "strong", "no session from the device on the collector, "
           "which listens", _unless_back(_r_no_session)),
    D.Rule("outlived_cause", "protocol", "strong", "the stream still lost well after its cause "
           "was put back", _unless_back(_r_outlived_cause)),
    D.Rule("cause_just_cleared", "protocol", "circumstantial", "the stream's cause put back "
           "too recently for the alert to have cleared", _unless_back(_r_cause_just_cleared)),
    D.Rule("cause_stands", "policy", "circumstantial", "the stream's likely cause, a change on "
           "another device, still standing", _unless_back(_r_cause_stands)),
    D.Rule("stream_config_changed", "policy", "circumstantial",
           "a configuration change on the device in the last hour",
           _unless_back(_r_config_changed)),
)
