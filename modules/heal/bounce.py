"""The port bounce, and the OSPF adjacency reset through it (board H's amendment, item 2, part
H20; docs/HEAL_TO_INTENT.md 19.4, guards 13c and 13f, N17; C2424, C2425, C2702, C2704).

**One home** (CLAUDE.md, "One owner per piece of state; one home per action"): the fixed
program, its hash and authorisation, the reads that judge it, its one held send, its repair and
its planned window live here. Two callers use them: the revert-timer probe
(`scripts/nmas-revert-probe`, the operator's measurement) and self-healing's action (`consider`,
then `apply`). Neither has a copy.

**The program**, sent as ONE batch, so a cut session cannot leave ``shutdown`` alone (the device
receives the batch whole, and the timer reverts it if it does)::

    configure terminal revert timer <n>
    interface <if>
    shutdown
    no shutdown
    end

Its hash is `deploy.command_fingerprint`, over the program AND its authorised ``shutdown`` with
its reason (``shutdown`` is one of `pipeline._DANGEROUS_PATTERNS`): the policy's reason for the
kind, in the hash and the record, as a person's reason is. It never saves: every send refuses a
save shape (`assert_no_save`).

**Measured, and only where measured** (`MEASURED`, the operator's trial, 2026-11-07, C2424 and
C2425): IOS-XE and IOS each accepted ``configure terminal revert timer`` and ``configure
confirm``, stated the timer in minutes, and reverted to ``no shutdown`` and up/up; settle 26/19 s
on IOS-XE and 30/39 s on IOS (the revert path, then the confirm path). A device of any other
dialect has the bounce refused, naming the unmeasured timer. `TIMER_MINUTES` is n = 2 on both.

**The bounds, each written beside its measurement:**
- `SETTLE_BOUND_S`, 98 s: 2.5 times the larger measured settle, 39 s (IOS's confirm path),
  rounded up. The confirm is sent only inside it, and it ends before the timer's 120 s;
- `WATCH_PAST_S`, 180 s past the timer's end (the trial's watch), when the repair may send;
- `window_seconds`, 398 s: the planned window the bounce declares BEFORE it sends (C2704,
  `declare_window`, through `restarts.record_planned`, naming its interface): the timer (the
  latest moment a revert can unshut the port), the watch past it (when the repair may send
  ``no shutdown``) and the settle bound after that (the port up from the repair). Every UPDOWN
  line the bounce itself can cause falls inside it, so the adjacency flap rows it would raise
  are explained by it and guard 13e's flap count leaves them out (`flaps.flapping`, C2694). A
  window that cannot be recorded refuses the bounce, with nothing sent;
- `OSPF_FULL_S`, 100 s: the OSPF adjacency's bound to FULL once the port is up, 2.5 times the
  dead interval's default (40 s); reasoned, not measured (the register's row).

**The decision** (`consider`, `DECIDE_STEPS`): an Alert incident's diagnosis (19.3) chooses an
action only by `diagnose.ACTIONS` (`diagnose.action_for`): the port bounce, or the OSPF
adjacency reset (the bounce on an interface with exactly one OSPF neighbour). Then guards 1 to 3
(the kill switch, the mode, a halt, planned work), 9 and 10 (the rates), a fresh read of both
ends and of the device's route to Mercury, guards 13a to 13e (`actions.judge`, 13c whole: the
management address by intent, Mercury's route out of the interface by the device's own ``show ip
cef`` or ``show ipv6 cef``, and the device's only path by the blast radius), and 13f (the
archive in intent, the dialect measured). AUTO with the kind allowed is ``heal``; anything else
of Tier 1 is ``would_heal``: **in dry run the bounce records "would bounce" and sends nothing**.
No policy allows the kind by default (`settings_schema`'s ``heal_kinds_auto``: empty).

**The act** (`apply`, `STEPS`), as the policy, the decision taken once by `act.run`:
1. ``take``; 2. ``stops`` again (`act._stops`: the kill switch, AUTO, the network marked lab,
   the policy's fingerprint, the kind still allowed, no halt, no planned work, a person who
   confirmed the policy);
3. ``hash``: the program recomputed, refused unless its hash is the decision's;
4. ``hold`` the device (one operation per device, `device_ops`), every session of the act;
5. ``pre-read`` on the held session: the running configuration (BEFORE), the port, the log, a
   pending revert, the management interface and Mercury's route (``show ip cef`` toward the
   session's own source address); 13a again (a port that came back by itself is left alone)
   and 13c again, each refusal naming its read and both operands;
6. ``window``: the planned window recorded, or nothing is sent;
7. ``send``: the step log's ``started`` row first (refused unwritten), then the one batch;
8. ``watch``: a new session every `POLL_S`; 9. ``confirm``: ``configure confirm`` only once
   Mercury is back in AND the post-check passes (the port up/up, the running configuration
   equal to BEFORE, line for line) while a revert is pending, inside `SETTLE_BOUND_S`;
   otherwise nothing more is sent and the device reverts when its timer ends;
10. ``verify``: an OSPF reset's adjacency FULL within `OSPF_FULL_S`; the configuration did not
   move (read again);
11. ``stable``: after the device is released, the stability window (``heal_flap_minutes``):
   no UPDOWN transition to down after the bounce's own up, read from the flap record;
12. ``repair``: when the end is not BEFORE (the port shut, the configuration moved), ``no
   shutdown`` and ``configure confirm`` (only when pending), read back, each step saying what
   it achieved: the revert timer first, then the repair;
13. ``record``: `decisions.applied`, a halt (guard 14) for a bounce reverted, repaired or failed,
   the step log's ``act`` row (History), and the announcement.

**What it ends with** (`OUTCOMES`): ``bounced`` (confirmed, verified, stable); ``still_flapping``
(H22's dampening proposal is the next need: `dampening.raise_after`, as is 13d's second need in
`consider`); ``not_formed`` (an OSPF reset's
adjacency not FULL); ``unverified`` (its stability not readable); ``reverted`` (no confirm: the
timer reverted it, ended at BEFORE); ``repaired``; ``failed`` (NOT RESTORED); ``refused``
(nothing sent). Each but ``bounced`` is a Needs attention row (``heal``/``bounce``), as a held
bounce is.
"""

import datetime
import ipaddress
import logging
import re
import time

log = logging.getLogger(__name__)

KINDS = ("port_bounce", "ospf_reset")
#: The revert timer, in the unit both dialects stated in the operator's trial (C2425: n = 2).
TIMER_MINUTES = 2
#: The operator's trial, by dialect (C2424, C2425, 2026-11-07): the settle times measured on the
#: revert path and the confirm path, seconds, and the timer's unit as the device stated it.
MEASURED = {
    "cisco_iosxe": {"settle_s": (26, 19), "unit": "minutes", "n": 2,
                    "trial": "the operator's trial, 2026-11-07 (C2424, C2425)"},
    "cisco_ios": {"settle_s": (30, 39), "unit": "minutes", "n": 2,
                  "trial": "the operator's trial, 2026-11-07 (C2424, C2425)"},
}
#: 2.5 x the larger measured settle (39 s, IOS's confirm path) = 97.5 s, rounded up.
SETTLE_BOUND_S = 98
#: A new session is tried this often while a bounce watches (the trial's).
POLL_S = 10
#: The watch runs this long past the timer's end (the trial's: the timer plus 3 minutes).
WATCH_PAST_S = 180
#: An OSPF adjacency's bound to FULL once the port is up: 2.5 x the dead interval's 40 s default.
#: Reasoned, not measured.
OSPF_FULL_S = 100
#: How the bounce's planned window names who declared it (`restarts.record_planned`'s *via*).
VIA = "heal-bounce"
#: The bounce's hold (`device_ops.OPERATION_WORDS`).
OPERATION = "port bounce"
ROLLBACK_READ = "show archive config rollback timer"
#: Who a bounce is recorded as, and how its reads run (`reads.run`'s *by*).
ACTOR = "Mercury (self-healing)"
READS_BY = "heal"
ANNOUNCER = "heal-act"

#: The decision's steps, in order (`consider`), for the manual's How it works page.
DECIDE_STEPS = (("choose", "Choose the action from the diagnosis's first hypothesis"),
                ("stops", "Check the kill switch, the mode, a halt and planned work"),
                ("rates", "Check the rates per device and per network"),
                ("fresh", "Read both ends again, and the device's route to Mercury"),
                ("guards", "Judge guards 13a to 13e, the archive and the measured timer"),
                ("decide", "Decide: bounce, would bounce, held or can't fix"),
                ("record", "Record the decision"))
#: The act's steps, in order (`apply`).
STEPS = (("take", "Take the decision, once"),
         ("stops", "Check the kill switch, AUTO, the stage, the policy and planned work"),
         ("hash", "Recompute the program and compare its hash"),
         ("hold", "Hold the device for every session of the bounce"),
         ("pre-read", "Read the device before: its configuration, the port, the route to "
                      "Mercury"),
         ("window", "Record the bounce's planned window, before anything is sent"),
         ("send", "Send the one batch inside the revert timer"),
         ("watch", "Open a new session every 10 s"),
         ("confirm", "Confirm on the device only once Mercury is back in and the post-check "
                     "passes"),
         ("verify", "Verify: the adjacency formed, the configuration not moved"),
         ("stable", "Read the stability window from the flap record"),
         ("repair", "Repair when the end is not as before"),
         ("record", "Record the outcome"))
#: Each step in two to four words, for its column on the stepper (the operator, 2026-11-11:
#: "short labels ... No full sentences in the step columns"); the long words above are its
#: hover. `{device}` is the run's own.
STEP_LABELS = {"take": "Take decision", "stops": "Check stops", "hash": "Check hash",
               "hold": "Hold {device}", "pre-read": "Read before", "window": "Declare window",
               "send": "Send bounce", "watch": "Watch port", "confirm": "Confirm",
               "verify": "Verify adjacency", "stable": "Check stable", "repair": "Repair",
               "record": "Record"}
OUTCOMES = ("bounced", "still_flapping", "not_formed", "unverified", "reverted", "repaired",
            "failed", "refused")
OUTCOME_WORDS = {"bounced": "bounced; configuration unchanged",
                 "still_flapping": "bounced once: still flapping",
                 "not_formed": "bounced; the OSPF adjacency did not form",
                 "unverified": "bounced; its stability window could not be read",
                 "reverted": "not confirmed: the device's revert timer reverted it",
                 "repaired": "repaired after the bounce",
                 "failed": "NOT RESTORED after the bounce",
                 "refused": "nothing was sent"}
#: The outcomes that halt the network (guard 14): the bounce had to be undone, or was not.
HALTS = ("reverted", "repaired", "failed")
#: What a held or failed bounce changes, announced at its end.
DONE_KEYS = ("drift", "device_state")

#: A syslog message's form (`%FACILITY-SEVERITY-MNEMONIC:`), which is a report, not an error.
_SYSLOG = re.compile(r"^%[A-Z0-9_]+-\d-[A-Z0-9_]+:")
#: A save, in any form IOS takes: refused by every send.
_SAVE = re.compile(r"^\s*(?:do\s+)?(?:wr(?:i(?:t(?:e)?)?)?(?:\s|$)|copy\s+\S*run)", re.I)
_UNIT = re.compile(r"\b(\d+)\s*(minutes?|mins?|seconds?|secs?)\b", re.I)
_PORT = re.compile(r"^(\S+) is (administratively down|up|down)[^,]*, line protocol is (\w+)",
                   re.M)
#: An egress line of a CEF answer, any address family: `nexthop <addr> <if>`, `next hop <addr>,
#: <if>`, `via <addr>, <if>`, `attached to <if>`.
_EGRESS = (re.compile(r"^\s*nexthop\s+\S+\s+([A-Za-z][^\s,]*)"),
           re.compile(r"^\s*next hop\s+[^,\s]+,\s*([A-Za-z][^\s,]*)"),
           re.compile(r"^\s*via\s+[^,\s]+,\s*([A-Za-z][^\s,]*)"),
           re.compile(r"^\s*(?:attached|connected) to\s+([A-Za-z][^\s,]*)"))
ARCHIVE_LOG = re.compile(r"archive|rollb|revert", re.I)


class SaveRefused(RuntimeError):
    """A send held a save; nothing of it was sent."""


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def utc(ts) -> str:
    if ts is None:
        return ""
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%f")[:-5] + "Z"


# ── The program, its hash and its authorisation ─────────────────────────────────────────────

def program(interface: str, timer: int) -> list:
    return [f"configure terminal revert timer {timer}", f"interface {interface}", "shutdown",
            "no shutdown", "end"]


def authorised(reason: str) -> list:
    """The program's one dangerous line, ``shutdown``, with its stated reason."""
    return [{"line": "shutdown", "reason": reason}]


def program_hash(lines: list, reason: str) -> str:
    from modules.nsot.deploy import command_fingerprint

    return command_fingerprint(lines, authorised(reason))


def policy_reason(network: str, kind: str, policy: dict) -> str:
    """The policy's reason for a bounce's ``shutdown`` (19.4, "the policy's reason for the
    `port_bounce` kind, in the hash and the receipt"): who confirmed it and their own words."""
    from modules.heal.actions import KIND_WORDS

    return (f"self-healing on {network}: {KIND_WORDS.get(kind, kind)}, shut and no shut in one "
            f"batch inside the device's revert timer, never saved, under the policy "
            f"{policy.get('fingerprint')} confirmed by {policy.get('by')} "
            f"({policy.get('reason') or 'no reason recorded'})")


def assert_no_save(lines) -> None:
    saves = [ln for ln in lines if _SAVE.match(ln or "")]
    if saves:
        raise SaveRefused(f"a save in the send ({', '.join(saves)}): a bounce never saves")


def window_seconds(timer: int = TIMER_MINUTES) -> int:
    """The bounce's planned window: the timer, the watch past it, then the settle bound (398 s
    at n = 2): its every own UPDOWN line falls inside it."""
    return int(timer) * 60 + WATCH_PAST_S + SETTLE_BOUND_S


def committed_intents_of(network: str) -> tuple:
    """``(intents, error)``: *network*'s committed intent, read without creating its list
    (`neighbours.committed_intents_of`, the one reader a window's far ends come from, C2751);
    intents None when it cannot be read whole, so a caller refuses (a read that failed or a
    document that did not parse came back as ``{}`` with its error before, C2751's survey)."""
    from modules.neighbours import committed_intents_of as read

    intents, error = read(network)
    return (None, error) if error else (intents, "")


def declare_window(network: str, device: str, interface: str, now: float, seconds: float, *,
                   by: str, why: str, via: str, intents: dict = None) -> dict:
    """Record the bounce's planned window on *device*, naming *interface*, BEFORE it sends
    (CLAUDE.md, "declares its planned-restart window BEFORE it acts"; C2702, C2704), so the
    adjacency drops it causes are explained, never a row, and its own UPDOWN lines are no flap
    (`flaps.flapping`). It covers the link's FAR END too, the device and interface committed
    intent puts on the same network (`neighbours.far_ends`; the operator, 2026-11-08, C2749:
    trial 1a's bounce of one router's port left its neighbour's side unexplained). Committed
    intent that cannot be read refuses the window, since its far end cannot be told; a link
    intent names no far
    end for is said in the record's ``far_end_words``. `restarts.record_planned`'s answer, or
    ``{"ok": False, "error"}``: the caller then sends nothing."""
    from modules import restarts
    from modules.neighbours import far_ends

    if intents is None:
        intents, err = committed_intents_of(network)
        if intents is None:
            return {"ok": False, "error": f"committed intent could not be read ({err}), so the "
                                          f"far end of {device} {interface} cannot be told"}
    far = far_ends(intents, device, interface)
    try:
        got = restarts.record_planned([device], now, now + float(seconds), by, why, via,
                                      list_name=network, interfaces=[interface], far_ends=far)
    except Exception as exc:                          # noqa: BLE001 (refused, said by the caller)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    got["far_end_words"] = (", ".join(f"{d} {i}" for d, i in far) if far else
                            f"committed intent names no far end for {device} {interface}")
    return got


# ── Reading answers ─────────────────────────────────────────────────────────────────────────

def device_errors(text: str) -> list:
    """Every line of *text* that is a device's error: `pipeline.IOS_ERROR_PATTERN`'s, and any
    other `%` line not in a syslog message's form (refusing by resemblance is safe)."""
    from modules.pipeline import IOS_ERROR_PATTERN

    out = []
    for line in (text or "").splitlines():
        s = line.strip()
        if re.search(IOS_ERROR_PATTERN, line) or (s.startswith("%") and not _SYSLOG.match(s)):
            out.append(s)
    return out


def port_state(text: str) -> dict:
    """`show interfaces <if>`'s first line: ``{line, admin, status, protocol, up_up}``, or
    ``{line, unknown: True}`` when it is not an interface's state."""
    m = _PORT.search(text or "")
    first = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")
    if not m:
        return {"line": first, "unknown": True, "admin": "", "up_up": False}
    status = m.group(2)
    return {"line": m.group(0).strip(), "admin": "down" if status.startswith("admin") else "up",
            "status": status, "protocol": m.group(3), "unknown": False,
            "up_up": status == "up" and m.group(3) == "up"}


def stated_unit(text: str):
    """The timer's unit as the device states it: ``{n, word, seconds}``, or None when it states
    none (never assumed)."""
    m = _UNIT.search(text or "")
    if not m:
        return None
    word = m.group(2).lower()
    return {"n": int(m.group(1)), "word": word, "seconds": 60 if word.startswith("min") else 1}


def rollback_pending(text: str) -> bool:
    """Whether `show archive config rollback timer` names a pending timer (a ``Timer value``
    line); anything else, an error included, is no timer pending."""
    return bool(re.search(r"^\s*Timer value\s*:", text or "", re.M | re.I))


def archive_path(intent: dict) -> str:
    """The configuration archive's path in committed intent: H22's ``archive.path``, or until
    H22 an unmodelled ``archive`` block holding a ``path`` line. ``""`` when neither."""
    arch = (intent or {}).get("archive")
    if isinstance(arch, dict) and str(arch.get("path") or "").strip():
        return str(arch["path"]).strip()
    for entry in (intent or {}).get("unmodeled") or []:
        if (entry.get("line") or "").strip() == "archive":
            for child in entry.get("children") or []:
                m = re.match(r"^\s*path\s+(\S.*)$", child or "")
                if m:
                    return m.group(1).strip()
    return ""


def interface_with_address(brief: str, address: str) -> str:
    """The interface a brief names with *address*: `show ip interface brief` (IPv4: the
    interface, then its address, in columns) or `show ipv6 interface brief` (an interface line,
    then its addresses indented)."""
    try:
        want = ipaddress.ip_address(str(address).split("%", 1)[0])
    except ValueError:
        return ""
    if want.version == 4:
        for line in (brief or "").splitlines():
            cols = line.split()
            if len(cols) >= 2 and cols[1] == str(want):
                return cols[0]
        return ""
    current = ""
    for line in (brief or "").splitlines():
        if not line.strip():
            continue
        if not line[0].isspace():
            current = line.split()[0]
            continue
        try:
            if ipaddress.ip_address(line.strip().split()[0].split("/")[0]) == want:
                return current
        except ValueError:
            continue
    return ""


def egress_interfaces(text: str) -> tuple:
    """``(interfaces, why)`` from a `show ip cef` or `show ipv6 cef` answer: every interface a
    next hop or an attached route leaves on. `path_trace.parse_cef` reads the IPv4 answer; the
    lines are read here for both families (its hops are IPv4 only). *why* says what was not
    understood when no egress is named (a receive or a no-route answer names none)."""
    from modules.nsot.ifnames import canonical
    from modules.path_trace import parse_cef

    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return set(), "the device answered nothing"
    if lines[0].lstrip().startswith("%"):
        return set(), lines[0].strip()
    found = set()
    for line in lines[1:]:
        for rx in _EGRESS:
            m = rx.match(line)
            if m:
                found.add(canonical(m.group(1)))
                break
    cef = parse_cef(text)
    found |= {canonical(h["iface"]) for h in cef.get("hops") or []}
    if cef.get("state") == "attached" and cef.get("iface"):
        found.add(canonical(cef["iface"]))
    if found:
        return found, ""
    if cef.get("state") == "receive":
        return set(), "the device holds that address itself (a receive entry)"
    return set(), (f"no egress interface in the answer ({cef.get('state')}: "
                   f"{lines[0].strip()[:80]!r})")


def cef_command(manager: str) -> str:
    """The device's own route toward Mercury's *manager* address, IPv4 or IPv6."""
    return (f"show ipv6 cef {manager}" if ipaddress.ip_address(manager).version == 6
            else f"show ip cef {manager}")


def manager_address(conn) -> tuple:
    """``(address, why)``: Mercury's own address on *conn*'s session, the one the device's
    route back to Mercury is asked for."""
    try:
        addr = conn.remote_conn.get_transport().sock.getsockname()[0]
        return str(ipaddress.ip_address(str(addr).split("%")[0])), ""
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        return "", f"{type(exc).__name__}: {exc}"


def manager_toward(address: str) -> tuple:
    """``(address, why)``: the source address this host uses toward *address*, IPv4 or IPv6,
    chosen by the kernel's routing for a UDP connect, which sends nothing."""
    import socket

    try:
        ip = ipaddress.ip_address(str(address).split("%", 1)[0])
        fam = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
        with socket.socket(fam, socket.SOCK_DGRAM) as s:
            s.connect((str(ip), 22))
            return str(ipaddress.ip_address(s.getsockname()[0].split("%")[0])), ""
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        return "", f"{type(exc).__name__}: {exc}"


# ── The refusals (13c, 13f), each naming its read and both operands ─────────────────────────

def cef_refusal(device: str, manager: str, interface: str, command: str, answer: str,
                who: str = "Mercury") -> str:
    """13c (2): Mercury's route to its own address leaving out of *interface*, by the device's
    own `show ip cef` (`show ipv6 cef` for an IPv6 manager); an answer naming no egress *who*
    can read is refused too. ``""`` when it passes."""
    from modules.nsot.ifnames import canonical

    if not manager:
        return ("Mercury's own address toward the device could not be read, so `show ip cef` "
                "toward it cannot be asked")
    egress, why = egress_interfaces(answer)
    if canonical(interface) in egress:
        return (f"{device} reaches Mercury ({manager}) out of {interface} (`{command}` on "
                f"{device}: egress {', '.join(sorted(egress))}), so a bounce would cut Mercury's "
                f"own session to {device}")
    if not egress:
        return (f"{device}'s `{command}` names no egress {who} can read ({why}); {who} "
                f"compares {interface} with that egress and refuses what it cannot compare")
    return ""


def radius_refusal(intents: dict, nets: list, device: str, interface: str,
                   who: str = "Mercury") -> str:
    """13c (3): *interface* is *device*'s only path, by the blast radius of its shutdown over
    committed intent and this host's networks; one that cannot be read is refused."""
    from modules.nsot import blast_radius

    got = blast_radius.radius_of_shutdowns(intents, nets, device, [interface])
    if got.get("state") != "known":
        return (f"whether shutting {interface} cuts Mercury's reach is not known "
                f"({got.get('why')}); {who} compares the blast radius's cut with none and "
                "refuses one it cannot read (it reads IPv4 intent and this host's IPv4 "
                "networks only)")
    if got.get("cut"):
        cut = got["cut"]
        behind = [d for d in cut if d != device]
        said = (f"{device} and {len(behind)} device(s) behind it" if device in cut and behind
                else ", ".join(cut))
        return (f"{interface} is {device}'s only path: shutting it leaves {said} unreachable "
                f"from Mercury (blast radius over committed intent and this host's networks "
                f"{', '.join(nets)}: {', '.join(cut)})")
    return ""


def archive_refusal(device: str, network: str, intents: dict, error: str = "") -> str:
    """13f: the device's configuration archive in its committed intent, which its revert timer
    needs."""
    if device not in (intents or {}):
        return (f"{device} has no committed intent in list {network}"
                + (f" ({error})" if error else "") + "; the archive and the blast radius are "
                "read from it")
    if not archive_path(intents[device]):
        return (f"{device} has no configuration archive in its intent, so it cannot revert a "
                f"bounce by itself if Mercury's session is lost. Add the archive's path to "
                f"{device}'s intent (host_vars, `archive.path`) and deploy it. (Read: committed "
                f"host_vars/{device}.yml in list {network}: no `archive.path`, and no `archive` "
                "block with a `path` line among its unmodelled lines.)")
    return ""


def measured_refusal(device: str, dialect: str) -> str:
    """13f: the revert timer measured on the device's dialect (`MEASURED`)."""
    if dialect in MEASURED:
        return ""
    return (f"the revert timer is not measured on {dialect or 'an unknown platform'} ({device}): "
            f"the operator's trial measured {', '.join(sorted(MEASURED))} only, and a bounce "
            "runs only inside a timer measured on its platform")


def path_refusal(device: str, address: str, manager: str, interface: str, pre: dict,
                 who: str = "Mercury") -> str:
    """Guard 13c's three reads on the held session, and the state before: each refusal names
    its read and both operands. *pre*: the reads taken before the batch."""
    from modules.nsot.ifnames import canonical

    want = canonical(interface)
    port = pre["port"]
    if port.get("unknown"):
        return (f"{device} answered `show interfaces {interface}` with {port['line']!r}, not an "
                f"interface's state; {who} compared {interface} with the device's interfaces")
    if port["admin"] == "down":
        return (f"{interface} on {device} is administratively down before the run (`show "
                f"interfaces {interface}`: {port['line']}); the bounce's `no shutdown` would "
                "change its configuration, and the post-check compares it with BEFORE")
    if pre["pending"]:
        return (f"{device} already has a revert pending (`{ROLLBACK_READ}` names a timer "
                f"value); {who} compared it with no revert pending and sends nothing into "
                "another change's timer")
    held = interface_with_address(pre["brief"], address)
    if held and canonical(held) == want:
        return (f"{interface} carries {device}'s management address {address}, the address "
                f"Mercury reaches it on (`{pre['brief_cmd']}` on {device}: {held} holds "
                f"{address}), so a bounce would cut Mercury's own session to {device}")
    if not manager:
        return (f"Mercury's own address on this session could not be read "
                f"({pre.get('manager_why')}), so `show ip cef` toward it cannot be asked")
    return cef_refusal(device, manager, interface, pre["cef_cmd"], pre["cef"], who)


# ── The session: one bounce's reads and sends on one device ─────────────────────────────────

class Session:
    """One bounce's reads (raw kept for comparing, masked into the record) and sends on one
    device, every send holding it (C101: re-entrant in the thread that already holds it, so no
    send is ever unheld, whoever calls it). *opener(device)* opens a new session (`open`),
    *clock* is the time. The probe's run and the heal's act both use it."""

    def __init__(self, network: str, device: dict, interface: str, actor: str, values: dict,
                 *, operation: str, detail: str, label: str, opener=None, clock=None):
        self.network, self.device, self.iface, self.actor = network, device, interface, actor
        self.host = device.get("hostname", "")
        self.values, self.operation, self.detail, self.label = values, operation, detail, label
        self.opener = opener or open_session
        self.clock = clock or time.time
        self.rec = {"sent": [], "steps": []}
        self.before, self.log_before = "", ""

    def mask(self, text: str) -> str:
        from modules.redact import redact_text

        return redact_text(text or "", self.values)

    def open(self):
        return self.opener(self.device)

    def read(self, conn, command: str) -> str:
        from modules.commands import run_device_command

        return run_device_command(conn, command, read_timeout=120) or ""

    def send(self, conn, lines: list) -> tuple:
        """``(answer, lost)``: *lines* written as ONE batch and read; *lost* names a session
        that failed during it (the device may have received the batch whole)."""
        from modules.nsot import device_ops

        assert_no_save(lines)
        with device_ops.hold(self.network, self.host, self.operation, self.actor,
                             detail=self.detail, ip=self.device.get("ip", "")):
            self.rec["sent"].append({"at": utc(self.clock()), "lines": list(lines)})
            try:
                got = conn.send_command_timing("\n".join(lines), strip_prompt=False,
                                               strip_command=False, read_timeout=60,
                                               last_read=2.0, cmd_verify=False) or ""
                return got, ""
            except Exception as exc:                  # noqa: BLE001 (recorded, then watched)
                return "", f"{type(exc).__name__}: {exc}"

    def step(self, name: str) -> None:
        from modules.nsot import device_ops

        device_ops.note(f"{self.label}: {name}", self.host)
        self.rec["steps"].append({"at": utc(self.clock()), "step": name})

    def equal_to_before(self, running: str) -> dict:
        from modules.nsot import roundtrip

        got = roundtrip.configs_equivalent(self.before, running)
        return {"equal": got["equal"], "only_before": [self.mask(x) for x in got["only_left"]],
                "only_now": [self.mask(x) for x in got["only_right"]]}

    def pre_reads(self, conn, *, ospf: bool = False) -> dict:
        """The reads before the batch: BEFORE, the port, the log, a pending revert, the brief
        holding the management address and Mercury's route (and an OSPF reset's neighbours)."""
        self.step("read BEFORE")
        self.before = self.read(conn, "show running-config")
        port = port_state(self.read(conn, f"show interfaces {self.iface}"))
        self.log_before = self.read(conn, "show logging")
        pending = rollback_pending(self.read(conn, ROLLBACK_READ))
        address = self.device.get("ip", "")
        try:
            v6 = ipaddress.ip_address(address).version == 6
        except ValueError:
            v6 = False
        brief_cmd = "show ipv6 interface brief" if v6 else "show ip interface brief"
        manager, why = manager_address(conn)
        cmd = cef_command(manager) if manager else ""
        pre = {"port": port, "pending": pending, "brief_cmd": brief_cmd,
               "brief": self.read(conn, brief_cmd), "manager": manager, "manager_why": why,
               "cef_cmd": cmd, "cef": self.read(conn, cmd) if cmd else ""}
        if ospf:
            pre["ospf"] = self.read(conn, f"show ip ospf neighbor {self.iface} detail")
        self.rec["before"] = {"port": port, "pending": pending, "manager": manager,
                              "cef_cmd": cmd, "cef": self.mask(pre["cef"]),
                              "running_lines": len(self.before.splitlines())}
        return pre

    def final(self) -> dict:
        """The end, read on a new session: the port, the configuration against BEFORE, a
        pending revert."""
        self.step("read the end")
        try:
            conn = self.open()
        except Exception as exc:                      # noqa: BLE001
            return {"read": False, "why": f"{type(exc).__name__}: {exc}"}
        try:
            port = port_state(self.read(conn, f"show interfaces {self.iface}"))
            eq = self.equal_to_before(self.read(conn, "show running-config"))
            pending = rollback_pending(self.read(conn, ROLLBACK_READ))
            return {"read": True, "port": port, "pending": pending, **eq}
        except Exception as exc:                      # noqa: BLE001
            return {"read": False, "why": f"{type(exc).__name__}: {exc}"}
        finally:
            _close(conn)

    def repair(self) -> dict:
        """Back to BEFORE: `no shutdown` when the port is shut, `configure confirm` only when a
        revert is pending, then the read-back; each step says what it achieved."""
        self.step("repair")
        steps = []
        try:
            conn = self.open()
        except Exception as exc:                      # noqa: BLE001
            return {"restored": False, "steps": [{
                "step": "open a session", "achieved": f"not opened ({type(exc).__name__}: "
                f"{exc}); nothing was sent; a pending revert timer still reverts by itself"}]}
        try:
            port = port_state(self.read(conn, f"show interfaces {self.iface}"))
            if port["admin"] == "down" or port.get("unknown"):
                lines = ["configure terminal", f"interface {self.iface}", "no shutdown", "end"]
                answer, lost = self.send(conn, lines)
                after = port_state(self.read(conn, f"show interfaces {self.iface}"))
                steps.append({"step": "no shutdown", "sent": lines, "answer": self.mask(answer),
                              "errors": device_errors(answer), "lost": lost,
                              "achieved": f"{self.iface} is now: {after['line']}"})
            if rollback_pending(self.read(conn, ROLLBACK_READ)):
                answer, lost = self.send(conn, ["configure confirm"])
                still = rollback_pending(self.read(conn, ROLLBACK_READ))
                steps.append({"step": "configure confirm", "sent": ["configure confirm"],
                              "answer": self.mask(answer), "errors": device_errors(answer),
                              "lost": lost, "achieved": "a revert is STILL pending" if still
                              else "no revert pending now"})
            port = port_state(self.read(conn, f"show interfaces {self.iface}"))
            eq = self.equal_to_before(self.read(conn, "show running-config"))
            steps.append({"step": "read back", "achieved": (
                f"{self.iface}: {port['line']}; the running configuration "
                + ("equals BEFORE" if eq["equal"] else
                   f"differs from BEFORE ({len(eq['only_before'])} line(s) missing, "
                   f"{len(eq['only_now'])} added)")), **eq})
            return {"restored": bool(eq["equal"] and port["admin"] == "up"), "steps": steps,
                    "port": port}
        except Exception as exc:                      # noqa: BLE001
            steps.append({"step": "lost", "achieved": f"{type(exc).__name__}: {exc}"})
            return {"restored": False, "steps": steps}
        finally:
            _close(conn)


def _close(conn) -> None:
    try:
        conn.disconnect()
    except Exception:                                 # noqa: BLE001
        pass


def open_session(device: dict):
    """The device's session through Mercury's connection layer (tests replace the opener)."""
    from modules.connection import open_ssh, stored_connection_params

    conn = open_ssh(stored_connection_params(device), owner="heal:bounce")
    conn.enable()
    return conn


# ── The decision (consider) ─────────────────────────────────────────────────────────────────

class Sources:
    """Where the decision and the act read, each replaceable in a test. The decision's reads
    run through THE reads engine (`reads.run`, the allowlist whole, the device held while it is
    read); the act's on its own held session (`Session`)."""

    def __init__(self, network: str, *, clock=time.time, sleep=time.sleep):
        self.network, self.clock, self.sleep = network, clock, sleep

    def mode(self, now):
        from modules.heal import policy

        return policy.current(self.network, now)

    def halted(self):
        from modules.heal import decisions

        return decisions.halted(self.network)

    def planned(self, device, now):
        from modules.heal import guards

        return guards.g3_planned(self.network, device, now)

    def decisions(self):
        from modules.heal import decisions

        return decisions.decisions(self.network)

    def device(self, host):
        from modules import device_page
        from modules.nsot import listref

        _ref, dev = device_page.find_device(host, listref.resolve(self.network))
        return dev or {}

    def intents(self):
        """``(intents, error)``, intents None when committed intent cannot be read whole, so
        the act's window refuses rather than naming no far end (C2795)."""
        return committed_intents_of(self.network)

    def host_networks(self):
        from modules.nsot import blast_radius

        return blast_radius.host_networks()

    def manager_toward(self, address):
        return manager_toward(address)

    def read(self, host: str, commands: list) -> dict:
        """``{command: answer}`` for the commands answered, ``{"_why": why}`` when none was."""
        from modules.nsot import reads

        try:
            rec = reads.run(self.network, [host], commands, ACTOR, by=READS_BY,
                            purpose="self-healing: the port bounce's fresh reads")
        except reads.Refused as exc:
            return {"_why": str(exc)}
        r = (rec.get("results") or {}).get(host) or {}
        got = {a["command"]: a.get("answer") or "" for a in r.get("answers") or []
               if a.get("state") == "answered"}
        return got or {"_why": r.get("why") or r.get("state") or "not read"}

    def flap(self, device, interface, now, at_least, minutes):
        from modules.heal import flaps

        return flaps.flapping(self.network, device, interface, now, at_least=at_least,
                              minutes=minutes)

    def transitions(self, device, interface, since, until):
        from modules.heal import flaps

        return flaps.transitions(self.network, device, interface, since, until)

    def holder(self, network, device):
        from modules.nsot import device_ops

        return device_ops.holder(network, device)

    def session(self, network, dev, interface, actor, values):
        return Session(network, dev, interface, actor, values, operation=OPERATION,
                       detail=f"port bounce of {interface}", label="port bounce",
                       clock=self.clock)

    def values(self):
        from modules.redact import known_secret_values

        return known_secret_values()


def _ospf_rows(text: str, interface: str):
    from modules.heal import diagnose_parse as DP

    got = DP.parse("ospf_neighbor", text or "", interface)
    return got["facts"] if got["state"] == DP.PARSED else None


def _precondition(kind: str, port_text: str, ospf_text: str, interface: str) -> dict:
    """13a's precondition on one read: a bounce's port down while administratively up; an OSPF
    reset's interface holding exactly one neighbour, not FULL."""
    from modules.heal import actions, diagnose_parse as DP

    if kind == "ospf_reset":
        rows = _ospf_rows(ospf_text, interface) if ospf_text else None
        return actions.precondition(kind, {"neighbours": rows} if rows is not None else {})
    if not port_text:
        return actions.precondition(kind, None)
    got = DP.parse("interfaces", port_text, interface)
    facts = got["facts"] if got["state"] == DP.PARSED else None
    return actions.precondition(kind, facts)


def consider(network: str, incident_id: str, diagnosis: dict, *, now: float = None,
             sources=None) -> dict:
    """The action Mercury's diagnosis of an Alert incident chooses, judged and recorded:
    ``{"state", "decision", "words"}``, *state* ``none`` (no action chosen, nothing recorded),
    ``recorded`` (the decision; its outcome ``heal`` is H4's runner's to take) or ``failed``.
    Never raises."""
    from modules.heal import decisions, diagnose

    now = time.time() if now is None else float(now)
    pick = diagnose.action_for(diagnosis or {})
    if pick["state"] != "chosen" or pick["kind"] not in KINDS:
        return {"state": "none", "decision": None, "words": pick.get("words") or ""}
    src = sources or Sources(network)
    try:
        made = decide(network, incident_id, pick, now=now, sources=src)
        steps, phase = made.pop("steps", []), made.pop("phase", "decide")
        d = decisions.record(network, made, now)
    except Exception as exc:                          # said, never raised
        log.exception("heal: %s's bounce decision for %s failed", network, incident_id)
        return {"state": "failed", "decision": None,
                "words": f"the bounce was not decided ({type(exc).__name__}: {exc})"}
    _log_decision(network, dict(d, steps=steps, phase=phase), now)
    _announce()
    out = {"state": "recorded", "decision": d, "words": d.get("words") or ""}
    if d.get("instead") == "dampening_proposal":
        # 13d: a second need within the repeat window is the dampening proposal (H22).
        from modules.heal import dampening
        out["dampening"] = dampening.raise_after(network, d, trigger="second_need", now=now,
                                                 sources=getattr(src, "dampening", None))
    return out


def decide(network: str, incident_id: str, pick: dict, *, now: float, sources) -> dict:
    """The bounce's decision on *pick* (`diagnose.action_for`'s): a record, not yet written."""
    from modules.heal import actions, diagnose, guards
    from modules.heal.guards import value

    src = sources
    kind, at = pick["kind"], pick.get("at") or {}
    device, interface = at.get("host") or "", at.get("interface") or ""
    mode = src.mode(now)
    lab = (mode.get("stage") or {}).get("stage") == "lab"
    tier = actions.tier_of(kind, lab)
    unit = {"kind": kind, "tier": tier, "id": f"{kind}:{interface}",
            "words": f"{actions.KIND_WORDS[kind]} of {device} {interface}"}
    base = {"incident": incident_id, "device": device, "mode": mode.get("mode"),
            "policy": {"fingerprint": mode.get("fingerprint"),
                       "by": (mode.get("confirmed") or {}).get("by"),
                       "reason": (mode.get("confirmed") or {}).get("reason")},
            "guard": None, "units": [unit], "kind": kind, "tier": tier, "program": [],
            "program_hash": "", "until": None, "triggers": [pick.get("words") or ""],
            "action": {"kind": kind, "device": device, "interface": interface, "peer": "",
                       "far_device": at.get("far_host") or "",
                       "far_interface": at.get("far_interface") or "",
                       "rule": pick.get("rule") or "", "hypothesis": pick.get("hypothesis")},
            "steps": [{"step": "choose", "result": "ok", "words": pick.get("words") or ""}],
            "phase": "stops"}

    def passed(name, words, then):
        base["steps"].append({"step": name, "result": "ok", "words": words})
        base["phase"] = then

    def stop(g, phase=None):
        if phase:
            base["phase"] = phase
        return dict(base, outcome=g["outcome"] if g["outcome"] in (
            "held", "halted", "off", "nothing", "cant_fix") else "cant_fix",
            guard={k: g.get(k) for k in ("guard", "name", "words", "operands")},
            tier=g.get("tier") or base["tier"],
            words=f"guard {g['guard']}, {g['name']}: {g['words']}", until=g.get("until"))

    if not device or not interface:
        return dict(base, outcome="cant_fix", phase="choose",
                    words="the diagnosis named no device and interface to act on")
    try:
        halt = src.halted()
    except Exception as exc:
        halt = {"unreadable": str(exc)}
    for g in (guards.g1_kill_switch(mode), guards.g2_mode(mode, halt),
              src.planned(device, now)):
        if g:
            return stop(g)
    passed("stops", f"no kill switch, the mode {mode.get('mode')}, no halt, no planned work",
           "rates")
    counted = "heal" if mode.get("mode") == "auto" else "would_heal"
    try:
        rows = src.decisions()
    except Exception as exc:
        return stop(guards.hit(10, "halted", f"the heal record cannot be read ({exc}), and a "
                                             "rate that cannot be counted holds", {}))
    for g in (guards.g9_device_rate(rows, device, counted, now,
                                    value(mode, "heal_max_per_device_hour")),
              guards.g10_network_rate(rows, network, counted, now,
                                      value(mode, "heal_max_per_network_hour"))):
        if g:
            return stop(g)
    passed("rates", "under the rates per device and per network", "fresh")

    # The fresh reads (13a, 13b, 13c's route): both ends through the reads engine.
    dev = src.device(device) or {}
    intents, ierr = src.intents()
    hv = (intents or {}).get(device) or {}
    try:
        dialect = diagnose.dialect_of(hv.get("platform") or dev.get("device_type") or "",
                                      device)
    except Exception as exc:                          # an unknown platform, named
        dialect, derr = "", str(exc)
    else:
        derr = ""
    address = dev.get("ip", "")
    manager, mwhy = src.manager_toward(address) if address else ("", "no address held")
    near = [f"show interfaces {interface}"]
    cmd = cef_command(manager) if manager else ""
    if cmd:
        near.append(cmd)
    if kind == "ospf_reset":
        near.append(f"show ip ospf neighbor {interface} detail")
    got = src.read(device, near)
    far_dev, far_if = at.get("far_host") or "", at.get("far_interface") or ""
    far_got = src.read(far_dev, [f"show interfaces {far_if}"]) if far_dev and far_if else {}
    far_read = "read" if far_got and "_why" not in far_got else "not read"
    passed("fresh", (f"{device}: {len([c for c in near if c in got])} of {len(near)} read(s)"
                     + (f" ({got['_why']})" if "_why" in got else "")
                     + (f"; {far_dev}: {far_read}" if far_dev else "")), "guards")

    facts = {}
    decided = {"holds": True, "words": pick.get("words") or "the diagnosis's first hypothesis"}
    again = _precondition(kind, got.get(f"show interfaces {interface}", ""),
                          got.get(f"show ip ospf neighbor {interface} detail", ""), interface)
    facts["13a"] = actions.g13a_fresh(kind, decided, again)
    far_facts = {"device": far_dev, "interface": far_if, "managed": bool(src.device(far_dev))
                 if far_dev else False, "read": f"show interfaces {far_if}"}
    ftext = (far_got or {}).get(f"show interfaces {far_if}", "")
    if ftext:
        from modules.heal import diagnose_parse as DP

        fp = DP.parse("interfaces", ftext, far_if)
        far_facts["state"] = (fp["facts"] or {}).get("state") if fp["state"] == DP.PARSED \
            else None
    facts["13b"] = actions.g13b_far_end(network, far_facts, now,
                                        changes=value(mode, "heal_person_working_changes"),
                                        minutes=value(mode, "heal_person_working_minutes"),
                                        holder=src.holder)
    cef = ({"manager": manager, "command": cmd, "answer": got.get(cmd)} if cmd and cmd in got
           else {"manager": manager, "command": cmd, "answer": None,
                 "why": mwhy or got.get("_why") or "not read"})
    facts["13c"] = actions.g13c_path(device, interface, mgmt_ip=address, intent=hv, cef=cef,
                                     intents=intents, nets=src.host_networks())
    facts["13d"] = actions.g13d_once(kind, actions.history_of(rows, counted),
                                     {"device": device, "interface": interface,
                                      "incident": incident_id}, now,
                                     per_hour=value(mode, "heal_bounce_per_port_hour"),
                                     repeat_hours=value(mode, "heal_repeat_halts_hours"))
    facts["13e"] = actions.g13e_flap(kind, src.flap(device, interface, now,
                                                    value(mode, "heal_flap_transitions"),
                                                    value(mode, "heal_flap_minutes")))
    judged = actions.judge(kind, facts)
    base["steps"] += [{"step": "guards", "result": "ok", "words": f"{s['step']}: {s['words']}"}
                      for s in judged["steps"] if s.get("result") == "ok"]
    if judged["outcome"] != "pass":
        g = dict(judged["guard"] or {}, outcome=judged["outcome"], tier=judged["tier"],
                 until=None)
        if judged["outcome"] == "instead":
            from modules.heal.actions import not_built

            g["words"] += (f"; {actions.KIND_WORDS[judged['instead']]}: "
                           f"{not_built(judged['instead']) or 'its own record follows'}")
            g["outcome"] = "cant_fix"
            # H22: `consider` raises the dampening proposal once this decision is recorded.
            base["instead"] = judged["instead"]
        if judged["outcome"] == "held":
            g["until"] = (facts.get("13b") or {}).get("until")
        if not judged["guard"]:
            return dict(base, outcome="cant_fix", words=judged["words"], phase="guards")
        return stop(g, "guards")
    # 13f: the device's own repair route: the archive in its intent (Never without it, as 13c),
    # and the revert timer measured on its dialect (can't fix until the operator's trial).
    for why, tier13f in ((archive_refusal(device, network, intents, ierr), 4),
                         (measured_refusal(device, dialect)
                          + (f" ({derr})" if derr and not dialect else ""), 3)):
        if why:
            return dict(base, outcome="cant_fix", tier=tier13f,
                        guard={"guard": "13f", "name": "a device-side repair route",
                               "words": f"Not bounced: {why}",
                               "operands": {"device": device, "dialect": dialect,
                                            "archive": archive_path(hv)}},
                        words=f"guard 13f, a device-side repair route: Not bounced: {why}",
                        phase="guards")
    passed("guards", "13a to 13e passed; 13f: the archive in intent, the revert timer measured "
                     f"on {dialect}", "decide")
    reason = policy_reason(network, kind, base["policy"])
    prog = program(interface, TIMER_MINUTES)
    base.update(program=prog, program_hash=program_hash(prog, reason),
                bounce={"interface": interface, "timer": TIMER_MINUTES, "dialect": dialect,
                        "window_s": window_seconds(), "settle_bound_s": SETTLE_BOUND_S,
                        "manager": manager, "reason": reason})
    allowed = kind in (mode.get("kinds_auto") or [])
    if mode.get("mode") == "auto" and allowed and tier == 1:
        return dict(base, outcome="heal",
                    words=(f"bounce now: {unit['words']} (Tier 1), allowed AUTO; program "
                           f"{base['program_hash']}"))
    why = ("the mode is dry run" if mode.get("mode") != "auto" else
           f"{kind} is not allowed AUTO, so dry run for it" if not allowed else
           f"{kind} is Tier {tier} on this network")
    return dict(base, outcome="would_heal",
                words=(f"would have bounced {device} {interface} (program "
                       f"{base['program_hash']}); {why}. Nothing was sent"))


def _log_decision(network: str, d: dict, now: float) -> None:
    from modules.heal import steplog

    try:
        steplog.record_decision(network, d, now)
    except Exception as exc:
        log.error("heal: %s's bounce decision %s is not in the step log: %s", network,
                  d.get("id"), exc)


def _announce() -> None:
    try:
        from modules import invalidation
        invalidation.announce(invalidation.ANNOUNCERS[ANNOUNCER], by=ANNOUNCER)
    except Exception as exc:                          # noqa: BLE001 (a page's freshness only)
        log.info("heal: a bounce recorded, not announced: %s", exc)


# ── The act (apply) ─────────────────────────────────────────────────────────────────────────

class _Act:
    """One act's record as it runs: its steps, each with its result, words and time."""

    def __init__(self, network: str, decision: dict, src, via: str):
        self.network, self.decision, self.src, self.via = network, decision, src, via
        self.out = {"decision": decision.get("id"), "device": decision.get("device"),
                    "outcome": "refused", "words": "", "sent": False, "records": {},
                    "steps": [{"step": "take", "result": "ok", "words": f"taken by {via}"}]}

    def note(self, step: str, result: str, words: str) -> None:
        self.out["steps"].append({"step": step, "result": result, "words": words,
                                  "at": utc(self.src.clock())})

    def finish(self, outcome: str, words: str) -> dict:
        self.out.update(outcome=outcome, words=words)
        return _record(self.network, self.decision, self.out, by=self.via,
                       now=self.src.clock())

    def refuse(self, step: str, words: str, result: str = "refused") -> dict:
        self.note(step, result, words + ". Nothing was sent")
        return self.finish("refused", words + ". Nothing was sent")


class _ActSources:
    """`act._stops`' two reads, from the bounce's sources."""

    def __init__(self, src):
        self.src = src

    def mode(self, now):
        return self.src.mode(now)

    def planned(self, device, now):
        return self.src.planned(device, now)


def apply(network: str, decision: dict, *, now: float = None, sources=None) -> dict:
    """Apply one taken bounce decision as the policy, verify it and record it (`STEPS`):
    ``{"decision", "device", "outcome", "words", "steps", "sent", "records"}``."""
    from modules.heal import act as heal_act
    from modules.nsot import device_ops

    src = sources or Sources(network)
    now = src.clock() if now is None else float(now)
    a, b = decision.get("action") or {}, decision.get("bounce") or {}
    device, interface, kind = decision["device"], a.get("interface") or "", a.get("kind") or ""
    pol = decision.get("policy") or {}
    setter = pol.get("by") or ""
    run = _Act(network, decision, src,
               f"self-healing (policy set by {setter or 'nobody recorded'})")
    why = heal_act._stops(_ActSources(src), network, decision, now)
    if why:
        return run.refuse("stops", why)
    run.note("stops", "ok", "the kill switch, AUTO, the stage, the policy and planned work: "
                            "clear")
    timer = int(b.get("timer") or TIMER_MINUTES)
    prog = program(interface, timer)
    h = program_hash(prog, policy_reason(network, kind, pol))
    if h != decision.get("program_hash"):
        return run.refuse("hash", f"the program's hash moved since the decision (decided "
                                  f"{decision.get('program_hash')}, now {h})")
    why = measured_refusal(device, b.get("dialect") or "")
    if why:
        return run.refuse("hash", f"13f: Not bounced: {why}")
    run.note("hash", "ok", f"the program's hash {h} is the decision's")
    dev = src.device(device) or {}
    if not dev:
        return run.refuse("hold", f"{device} is not a device of {network}")
    s = src.session(network, dev, interface, setter or ACTOR, src.values())
    try:
        with device_ops.hold(network, device, OPERATION, setter or ACTOR,
                             detail=f"port bounce of {interface}", ip=dev.get("ip", "")):
            run.note("hold", "ok", f"{device} held for every session of the bounce")
            got = _held(run, s, prog, h, kind, interface, dev, timer)
    except device_ops.DeviceBusy as exc:
        return run.refuse("hold", str(exc))
    if got.get("done"):
        return got["done"]
    # Released: the stability window reads the flap record, never the device.
    return _stable(run, device, interface, got["times"])


def _held(run: _Act, s, prog: list, h: str, kind: str, interface: str, dev: dict,
          timer: int) -> dict:
    """Steps 5 to 10 and 12, holding the device: ``{"done": result}`` when the act ended here,
    or ``{"times"}`` for the stability window."""
    from modules.heal import steplog
    from modules.redact import redact_text

    src, network, decision, device = run.src, run.network, run.decision, run.decision["device"]
    clock = src.clock
    try:
        conn = s.open()
    except Exception as exc:                          # noqa: BLE001
        return {"done": run.refuse("pre-read", f"{device}'s session could not be opened "
                                               f"({type(exc).__name__}: {exc})")}
    try:
        try:
            pre = s.pre_reads(conn, ospf=kind == "ospf_reset")
        except Exception as exc:                      # noqa: BLE001 (nothing sent yet)
            return {"done": run.refuse("pre-read", f"{device}'s reads before the batch "
                                                   f"failed ({type(exc).__name__}: {exc})")}
        again = (_precondition(kind, "", pre.get("ospf", ""), interface)
                 if kind == "ospf_reset" else _port_precondition(pre["port"], interface))
        if again["holds"] is False:
            return {"done": run.refuse("pre-read", f"13a: {again['words']}: "
                                       + ("the port came back by itself" if kind != "ospf_reset"
                                          else "it resolved by itself"), result="nothing")}
        if again["holds"] is not True:
            return {"done": run.refuse("pre-read", f"13a: the precondition could not be read "
                                                   f"again before the send ({again['words']})")}
        why = path_refusal(device, dev.get("ip", ""), pre["manager"], interface, pre)
        if why:
            return {"done": run.refuse("pre-read", f"13c: Not bounced: {why}")}
        run.note("pre-read", "ok", (f"{device} read before: {pre['port']['line']}; Mercury "
                                    f"({pre['manager']}) reached elsewhere (`{pre['cef_cmd']}`)"))
        secs = window_seconds(timer)
        intents, ierr = run.src.intents()
        w = (declare_window(network, device, interface, clock(), secs, by=run.via, via=VIA,
                            why=(f"self-healing's port bounce of {interface}: shut and no shut "
                                 f"inside a {timer}-minute revert timer (decision "
                                 f"{decision.get('id')})"), intents=intents)
             if intents is not None else
             {"ok": False, "error": f"committed intent could not be read ({ierr}), so the far "
                                    f"end of {device} {interface} cannot be told"})
        rec = w.get("record") or {}
        run.out["records"]["window"] = ({**{k: rec.get(k) for k in ("from", "until", "via",
                                                                     "interfaces")},
                                         "far_ends": (rec.get("expected") or {}).get(
                                             "far_ends") or []}
                                        if w.get("ok") else {"error": w.get("error")})
        if not w.get("ok"):
            return {"done": run.refuse("window", (
                f"the planned window for the bounce could not be recorded ({w.get('error')}): "
                "an unannounced bounce reads as a fault"))}
        run.note("window", "ok", f"planned window recorded: {secs} s, {rec.get('from')} to "
                                 f"{rec.get('until')}, naming {interface}; its far end: "
                                 f"{w.get('far_end_words')}")
        try:
            steplog.record_started(network, decision, list(run.out["steps"]),
                                   [redact_text(x) for x in prog], h, by=run.via, now=clock())
        except Exception as exc:
            return {"done": run.refuse("send", f"the step log's started row could not be "
                                               f"written ({exc})")}
        s.step("send the batch")
        t0 = clock()
        answer, lost = s.send(conn, prog)
        run.out["sent"] = True
    finally:
        _close(conn)
    errors = device_errors(answer)
    run.note("send", "failed" if errors else "ok",
             (f"the batch answered {errors[0]}" if errors else
              f"the batch sent: {len(prog)} lines, one write")
             + (f"; the session was lost during it ({lost})" if lost else ""))
    times = {"t0": t0}
    confirmed = False
    if not errors:
        confirmed = _watch(run, s, t0, interface, times)
        if not confirmed:
            # Nothing more is sent: the device reverts when its timer ends; the watch reads it.
            end = t0 + timer * 60 + WATCH_PAST_S
            while clock() < end:
                src.sleep(min(POLL_S, max(0.0, end - clock())))
    ok, words = (True, "")
    if confirmed:
        ok, words = _verify(run, s, kind, interface, times)
    final = s.final()
    restored = bool(final.get("read") and final.get("equal")
                    and (final.get("port") or {}).get("admin") == "up")
    if not restored:
        rep = s.repair()
        run.out["records"]["repair"] = {"restored": rep["restored"],
                                        "steps": [{"step": x["step"], "achieved": x["achieved"]}
                                                  for x in rep["steps"]]}
        run.note("repair", "ok" if rep["restored"] else "failed",
                 "; ".join(f"{x['step']}: {x['achieved']}" for x in rep["steps"]))
        if not rep["restored"]:
            return {"done": run.finish("failed", (
                f"NOT RESTORED: {device} {interface}: the repair did not return it to BEFORE. "
                "Nothing was saved, so a reload returns it; a pending revert timer reverts it "
                "by itself"))}
        return {"done": run.finish("repaired", (
            f"{device} {interface} repaired after the bounce: "
            + (f"the batch answered {errors[0]}" if errors else "its end was not as before")))}
    if not confirmed:
        return {"done": run.finish("reverted", (
            f"{device} {interface}: not confirmed, and the device's revert timer reverted it; "
            "it ended as before (the port administratively up, the configuration unchanged)"))}
    if not ok:
        return {"done": run.finish("not_formed", words)}
    run.note("verify", "ok", (f"{words}; " if words else "")
             + "the configuration did not move (read again: equal to BEFORE, line for line)")
    return {"times": times}


def _port_precondition(port: dict, interface: str) -> dict:
    from modules.heal import actions

    if port.get("unknown"):
        return actions.precondition("port_bounce", None)
    state = ("admin_down" if port["admin"] == "down" else
             "up" if port.get("up_up") else "down")
    return actions.precondition("port_bounce", {"name": interface, "state": state})


def _watch(run: _Act, s, t0: float, interface: str, times: dict) -> bool:
    """A new session every `POLL_S` within `SETTLE_BOUND_S`; ``configure confirm`` once
    Mercury is back in and the post-check passes while a revert is pending. True when it was
    confirmed."""
    clock, sleep = run.src.clock, run.src.sleep
    tried = 0
    s.step("watch")
    while clock() < t0 + SETTLE_BOUND_S:
        sleep(POLL_S)
        tried += 1
        try:
            conn = s.open()
        except Exception as exc:                      # noqa: BLE001 (the watch goes on)
            log.info("bounce: %s not back yet: %s", s.host, exc)
            continue
        try:
            times.setdefault("t2", clock())
            port = port_state(s.read(conn, f"show interfaces {interface}"))
            if port["up_up"] and times.get("t1") is None:
                times["t1"] = clock()
            if not port["up_up"]:
                continue
            if not s.equal_to_before(s.read(conn, "show running-config"))["equal"]:
                continue
            times.setdefault("t3", clock())
            if not rollback_pending(s.read(conn, ROLLBACK_READ)):
                run.note("confirm", "not_sent", "the post-check passed when no revert was "
                                                "pending any more: not confirmed")
                return False
            s.step("configure confirm")
            answer, lost = s.send(conn, ["configure confirm"])
            errors = device_errors(answer)
            run.note("watch", "ok", (f"Mercury back in at {round(times['t2'] - t0)} s; "
                                     f"{interface} up/up at {round(times['t1'] - t0)} s; the "
                                     "running configuration equal to BEFORE"))
            if errors or lost:
                run.note("confirm", "failed", "`configure confirm` answered "
                                              f"{errors[0] if errors else lost}")
                return False
            run.note("confirm", "ok", (f"`configure confirm` sent at {round(clock() - t0)} s, "
                                       f"inside the {SETTLE_BOUND_S} s settle bound"))
            return True
        except Exception as exc:                      # noqa: BLE001 (a session lost mid-read)
            log.info("bounce: %s lost during the watch: %s", s.host, exc)
        finally:
            _close(conn)
    run.note("watch", "failed", (f"{tried} session(s) tried in {SETTLE_BOUND_S} s: "
                                 + ("Mercury was not back in" if "t2" not in times else
                                    f"{interface} was not up/up" if "t1" not in times else
                                    "the running configuration was not equal to BEFORE")))
    run.note("confirm", "not_sent", (f"the post-check did not pass within {SETTLE_BOUND_S} s, so "
                                     "nothing more is sent: the device reverts when its timer "
                                     "ends"))
    return False


def _verify(run: _Act, s, kind: str, interface: str, times: dict) -> tuple:
    """An OSPF reset's adjacency FULL within `OSPF_FULL_S` of the port up. ``(ok, words)``."""
    if kind != "ospf_reset":
        return True, f"{interface} up/up"
    clock, sleep = run.src.clock, run.src.sleep
    start = times.get("t1") or clock()
    last = "not read"
    while clock() <= start + OSPF_FULL_S:
        try:
            conn = s.open()
            try:
                rows = _ospf_rows(s.read(conn, f"show ip ospf neighbor {interface} detail"),
                                  interface)
            finally:
                _close(conn)
        except Exception as exc:                      # noqa: BLE001
            rows, last = None, f"{type(exc).__name__}: {exc}"
        if rows is not None:
            last = ", ".join(f"{r['router_id']} {r['state']}" for r in rows) or "no neighbour"
            if len(rows) == 1 and (rows[0].get("state") or "").upper() == "FULL":
                return True, f"the OSPF adjacency on {interface} is FULL ({last})"
        sleep(POLL_S)
    run.note("verify", "failed", (f"the OSPF adjacency on {interface} did not reach FULL within "
                                  f"{OSPF_FULL_S} s of the port up (last read: {last})"))
    return False, (f"bounced, and the OSPF adjacency on {interface} did not form within "
                   f"{OSPF_FULL_S} s (last read: {last})")


def _stable(run: _Act, device: str, interface: str, times: dict) -> dict:
    """The stability window, after the device is released: no transition to down after the
    bounce's own up, for ``heal_flap_minutes``, from the flap record."""
    from modules.heal.guards import value

    src = run.src
    minutes = int(value(src.mode(src.clock()), "heal_flap_minutes") or 10)
    t0 = times["t0"]
    end = (times.get("t1") or t0) + minutes * 60.0
    while src.clock() < end:
        src.sleep(min(60.0, max(0.0, end - src.clock())))
    got = src.transitions(device, interface, t0, end)
    if got.get("state") != "read":
        run.note("stable", "unknown", f"the stability window could not be read: "
                                      f"{got.get('words')}")
        return run.finish("unverified", (f"{device} {interface} bounced and confirmed; its "
                                         "stability window could not be read "
                                         f"({got.get('words')})"))
    seen = got.get("transitions") or []
    first_up = next((i for i, t in enumerate(seen) if t["state"] == "up"), None)
    if first_up is None:
        run.note("stable", "unknown", "the bounce's own up line is not in the flap record, so "
                                      "the stability window cannot be judged")
        return run.finish("unverified", (f"{device} {interface} bounced and confirmed; the flap "
                                         "record holds no up line of the bounce, so its "
                                         "stability is not known"))
    downs = [t for t in seen[first_up + 1:] if t["state"] == "down"]
    if downs:
        run.note("stable", "failed", (f"{len(downs)} transition(s) to down after the bounce's "
                                      f"up, the first at {downs[0]['at']}, inside {minutes} min"))
        # H22 (19.4): the next need is the dampening proposal, a person's change to intent.
        from modules.heal import dampening
        got = dampening.raise_after(run.network, run.decision, trigger="still_flapping",
                                    now=src.clock(), sources=getattr(src, "dampening", None))
        run.out["records"]["dampening"] = got["words"]
        waits = ("a dampening change waits for a person" if got["state"] in (
            "recorded", "waiting") and (got.get("decision") or {}).get("outcome") == "propose"
            else "no dampening change waits")
        return run.finish("still_flapping", (
            f"{device} {interface} bounced once: still flapping ({len(downs)} down after the "
            f"bounce in {minutes} min); {waits}: {got['words']}"))
    run.note("stable", "ok", f"no transition to down in the {minutes}-minute stability window")
    return run.finish("bounced", (f"{device} {interface} bounced; configuration unchanged; "
                                  f"stable for {minutes} min"))


def _record(network: str, decision: dict, out: dict, *, by: str, now: float) -> dict:
    """``record``: what the bounce did, in the decisions store (a halt, guard 14, for one undone
    or not restored), the step log (History) and the announcement."""
    from modules.heal import decisions, steplog

    out["steps"].append({"step": "record", "result": "ok",
                         "words": OUTCOME_WORDS.get(out["outcome"], out["outcome"]),
                         "at": utc(now)})
    try:
        decisions.applied(network, decision["id"], out["outcome"], by=by, words=out["words"],
                          now=now)
        if out["outcome"] in HALTS:
            decisions.halt(network, guard=14, name="a rolled-back heal",
                           words=(f"the bounce of {decision.get('device')} "
                                  f"({decision['id']}) was {out['outcome']}: {out['words']}"),
                           operands={"decision": decision["id"],
                                     "device": decision.get("device"),
                                     "outcome": out["outcome"]}, now=now)
    except Exception as exc:
        log.error("heal: %s's bounce %s outcome not recorded: %s", network,
                  decision.get("id"), exc)
        out["records"]["error"] = f"the outcome could not be recorded ({exc})"
    # H23 (19.4, "Record"): what undid it, and the deterministic change record, both kept in
    # the act row History draws.
    from modules.heal import change_record
    out["records"]["rollback"] = rollback_words(out)
    out["records"]["change_record"] = change_record.build_action(network, decision, out,
                                                                 at=utc(now))
    try:
        steplog.record_act(network, decision, out, by=by, now=now)
    except Exception as exc:
        log.error("heal: %s's bounce %s is not in the step log: %s", network,
                  decision.get("id"), exc)
    _announce()
    return out


def rollback_words(out: dict) -> str:
    """What undid a bounce, in History's words: its repair, the device's revert, or why none
    was needed."""
    rep = (out.get("records") or {}).get("repair") or {}
    if rep:
        return (("repaired: " if rep.get("restored") else "NOT RESTORED: ")
                + "; ".join(f"{s.get('step')}: {s.get('achieved')}" for s in rep.get("steps")
                            or []))
    if out.get("outcome") == "reverted":
        return "the device's revert timer reverted it: no confirm was sent"
    if out.get("sent"):
        return ("not needed: confirmed on the device once Mercury was back in, the running "
                "configuration equal to before")
    return "not needed: nothing was sent"

