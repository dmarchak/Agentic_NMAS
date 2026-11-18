"""An err-disabled switch port: its problem, its classifier, its device read, and the catalog
operation "Recover an err-disabled interface" (C3712, G7 of the Lab 10 recording plan; the
operator's R4, docs/MERCURY_CHARTER.md "Incidents are problems, not signals").

**The problem** (`modules/problem.py`'s schema, condition ``err_disabled``): the device, the
port (``object``, its short name: "Gi1/0"), the cause's display name (``cause``: "BPDU guard"
or "port security", from the device's own reason `CAUSES`), the port's role (``port_role``,
access or trunk from the interface's committed intent), who is affected (``affected``: the host
the port's description names), the check its cause clears by (``cause_cleared``) and whether it
has (``cleared``: true, false or unknown, with ``cleared_at``). Its title, the same words on
every page: "<device> <port> err-disabled by <cause>: <host> is offline" (`modules/bluf.py`).
Severity is a warning: one host down is not a network outage (R2).

**The classifier** (`classify`, pure): from the incident's own evidence, never an alert's name:
the device's syslog lines Loki holds from its opening (``%PM-4-ERR_DISABLE`` naming the port and
the cause, ``%SPANTREE-2-BLOCK_BPDUGUARD``, ``%PORT_SECURITY-2-PSECURE_VIOLATION`` naming the
violating MAC) and the Interface down alert's interface, which must agree with the lines (two
ports, or an alert naming another port, classify nothing, said). The affected host, its VLAN and
the port's role come from the device's committed intent. **Re-classification**
(`reclassify_step`, from the detect loop): each OPEN incident with an alert among its triggers
and no classification yet is read once from its own evidence (its device's lines from its
opening), so incidents opened before this module existed are classified without re-injecting
their fault; the classification is kept on the incident's record (`FIELD`,
`incidents.record_problem`) and read back by `problem.classify`.

**The device read before any action** (`confirm`, R4): ``show interfaces status err-disabled``
through Mercury's reads engine, as self-healing's read (the allowlist whole); the port must be
listed with the cause the evidence named, else no action, said. Kept on the classification
(``confirmed``: the port, the cause, when it was read, whether it agrees) and drawn on the
incident page as evidence (`problem.evidence`).

**The recovery is not an operation of its own** (C3757, path 2; the operator, 2026-11-15: "One
execution path: G7's recovery becomes the first built-in command plan"): it is the built-in
command plan `modules/nsot/command_plans/errdisable-recover.yml` (``interface <port>``,
``shutdown``, ``no shutdown``, never saved), run by the command-plan runner on the deploy
pipeline's engine (`modules/nsot/command_plan_run.py`: the hold, the gate, the read before, the
send, the verify, the rollback, the receipt and the record), its parameters validated against
Mercury's model (the port in committed intent, an access port, never the management path).
This module keeps the plan's checks, which its template names (`check_port_listed`: the port
err-disabled by the cause now; `check_no_recovery`, the cause's row of ``show errdisable
recovery``'s timer table Disabled (`recovery_timer`), and, at preview from the golden,
`preview_no_recovery`: no ``errdisable recovery cause`` line for it: never raced;
`check_cause_cleared`: BPDU guard, no BPDU guard line for the port since the err-disable; port
security, no new violation since the err-disable, by its ``PSECURE_VIOLATION`` lines and its
violation count, the MAC from the line or its Last Source Address;
`check_port_connected` and `check_port_not_listed`: the verify, connected within its bound and
the re-trip check through the quiet, whose re-trip is the run's own outcome, ``retripped``: no
retry, no rollback), and its finish (`on_finish`: the offending MAC, the
port, the time and the cause kept on the run's record and notified). A cause that has not
cleared refuses with nothing sent: "Port stays down: the device that tripped it (MAC …) is
still connected", and the engineer is notified.

Names no device: every device is the incident's or the request's.
"""

import logging
import re
import time

log = logging.getLogger(__name__)

KEY = "errdisable-recover"
WORDS = "Recover an err-disabled interface"
CONDITION = "err_disabled"
#: The signal kind this problem is classified from (`problem.CONDITION_OF`).
SIGNAL = "err_disable"
#: The classification's field on an incident's record (`incidents.record_problem`).
FIELD = "errdisable"
#: The device's own reasons this operation recovers, and each one's display name.
CAUSES = {"bpduguard": "BPDU guard", "psecure-violation": "port security"}
#: The check each cause clears by (`problem.CLEARED_CHECKS`).
CLEARED_CHECKS = {"bpduguard": "no_bpdu_since", "psecure-violation": "violator_gone"}
#: Whether the cause has cleared, as the problem says it.
CLEARED = ("true", "false", "unknown")
#: The reads the device confirmation makes, and each preflight read.
CONFIRM_READ = "show interfaces status err-disabled"
STATUS_READ = "show interfaces status"
#: The switch's own recovery, read live as its timer table (the operator, 2026-11-16: the
#: device's own answer, never a filter over its configuration): ``ErrDisable Reason`` and
#: ``Timer Status``, one row per cause (`recovery_timer`). The golden's preview reads its
#: ``errdisable recovery cause`` lines instead (`recovery_for`).
RECOVERY_READ = "show errdisable recovery"
PSEC_READ = "show port-security address"
#: The port's own port-security view: its Last Source Address and its violation count (the
#: operator, 2026-11-16: the violating MAC and "no new violation" are read here, never only
#: from the incident's evidence).
PSEC_IF_READ = "show port-security interface {port}"
#: How far back a check with no incident's classification looks for the port's err-disable
#: line: an err-disabled port stays so until recovered, so its line can be hours old; the
#: newest `LINES_LIMIT` lines are read (Loki's backward query). Reasoned, not measured.
ERRDISABLE_LOOKBACK_S = 86400
#: The re-trip's last words (the operator, 2026-11-16): no retry and no rollback follow it.
RETRIP_TAIL = "Port left err-disabled; nothing more sent."
#: How far before an incident's opening its device's lines are read: the alert's onset lags its
#: line by Grafana's evaluation (60 s) and its pending period. Reasoned, not measured: 300 s is
#: 2.5 times those two at 60 s each; the trial reads the lag from the record.
LOOKBACK_S = 300
#: A classification attempt that found nothing is tried again after this, or when the incident
#: takes a new trigger: one Loki read per incident per ten minutes at most.
RECHECK_S = 600
#: How its reads are recorded (`reads.run`'s *by*) and who a background read is.
READS_BY = "heal"
ACTOR = "Mercury (self-healing)"

_MESSAGE = re.compile(r"%(?P<mn>[A-Z0-9_]+-\d-[A-Z0-9_]+):\s*(?P<text>.*)$")
_ERRDISABLE = re.compile(r"^(?P<cause>[a-z0-9-]+) error detected on (?P<port>[^\s,]+),? putting "
                         r"(?P<port2>\S+) in err-disable state")
_BPDU = re.compile(r"^Received BPDU on port (?P<port>[^\s,]+) with BPDU Guard enabled")
_VIOLATION = re.compile(r"^Security violation occurred, caused by MAC address "
                        r"(?P<mac>[0-9a-fA-F.:]+) on port (?P<port>[^\s,]+?)\.?$")
_DOWN = re.compile(r"^Interface (?P<port>[^\s,]+), changed state to down")
_STATUS = re.compile(r"^(?P<port>[A-Za-z][A-Za-z-]*\d[\d/.:]*)\s+(?P<name>.*?)\s*"
                     r"(?P<status>err-disabled|connected|notconnect|disabled|inactive|"
                     r"monitoring|suspended|sfpAbsent)\s+(?P<rest>.*)$")
_MAC_ROW = re.compile(r"^\s*(?P<vlan>\d+|All)\s+(?P<mac>[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\."
                      r"[0-9a-fA-F]{4})\s+(?P<type>\S+)\s+(?P<port>\S+)")
_RECOVERY = re.compile(r"^\s*errdisable recovery cause (?P<cause>\S+)\s*$", re.M)
#: One ``Key : value`` row of ``show port-security interface`` (a key may hold a colon:
#: ``Last Source Address:Vlan``; the separator is the colon after the padding).
_PSEC_FIELD = re.compile(r"^(?P<key>\S.*?)\s+:\s*(?P<value>.*?)\s*$")


class Refused(ValueError):
    """Nothing was sent; the words say what was compared."""


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _canon(port: str) -> str:
    from modules.nsot import ifnames

    return ifnames.canonical(port or "")


def _short(port: str) -> str:
    from modules.nsot import ifnames

    return ifnames.abbreviate(port or "")


def same_port(a: str, b: str) -> bool:
    from modules.nsot import ifnames

    return bool(a and b) and ifnames.same_interface(a, b)


def mac_dotted(mac: str) -> str:
    """A MAC in IOS's dotted form (``aabb.cc00.8099``), from any of its forms; ``""`` if not one."""
    hexes = re.sub(r"[^0-9a-fA-F]", "", mac or "").lower()
    if len(hexes) != 12:
        return ""
    return ".".join(hexes[i:i + 4] for i in (0, 4, 8))


def mac_colon(mac: str) -> str:
    """A MAC as people write it (``aa:bb:cc:00:80:99``); ``""`` if not one."""
    hexes = mac_dotted(mac).replace(".", "")
    return ":".join(hexes[i:i + 2] for i in range(0, 12, 2)) if hexes else ""


# ── Reading the device's words ──────────────────────────────────────────────────────────────

def parse_line(line: str) -> dict:
    """One syslog line as this problem reads it: ``{"kind", "port", "cause", "mac", "mn"}``,
    *kind* one of ``errdisable``, ``bpdu``, ``violation``, ``down``, or ``{}`` for any other line.
    Anchored on the message's mnemonic and its own words (Cisco IOS's), never a substring."""
    m = _MESSAGE.search(line or "")
    if not m:
        return {}
    mn, text = m.group("mn"), m.group("text").strip()
    if mn.endswith("-ERR_DISABLE"):
        e = _ERRDISABLE.match(text)
        if e:
            return {"kind": "errdisable", "port": e.group("port"), "cause": e.group("cause"),
                    "mac": "", "mn": mn}
    elif mn.endswith("-BLOCK_BPDUGUARD"):
        e = _BPDU.match(text)
        if e:
            return {"kind": "bpdu", "port": e.group("port"), "cause": "bpduguard", "mac": "",
                    "mn": mn}
    elif mn.endswith("-PSECURE_VIOLATION"):
        e = _VIOLATION.match(text)
        if e:
            return {"kind": "violation", "port": e.group("port"), "cause": "psecure-violation",
                    "mac": mac_dotted(e.group("mac")), "mn": mn}
    elif mn.endswith("-UPDOWN"):
        e = _DOWN.match(text)
        if e:
            return {"kind": "down", "port": e.group("port"), "cause": "", "mac": "", "mn": mn}
    return {}


def status_rows(text: str, *, reasons: bool = False) -> list:
    """``show interfaces status`` (or, with *reasons*, its ``err-disabled`` view) as rows:
    ``{"port", "name", "status", "reason"|"vlan"}``. A header, a blank or any other line is
    skipped."""
    out = []
    for line in (text or "").splitlines():
        m = _STATUS.match(line.rstrip())
        if not m or m.group("port").lower() == "port":
            continue
        first = (m.group("rest").split() or [""])[0]
        row = {"port": m.group("port"), "name": m.group("name").strip(),
               "status": m.group("status")}
        row["reason" if reasons else "vlan"] = first
        out.append(row)
    return out


def mac_rows(text: str) -> list:
    """A MAC table (``show mac address-table``) or the port-security table (``show port-security
    address``) as rows ``{"vlan", "mac", "type", "port"}``, the MAC dotted."""
    out = []
    for line in (text or "").splitlines():
        m = _MAC_ROW.match(line)
        if m:
            out.append({"vlan": m.group("vlan"), "mac": mac_dotted(m.group("mac")),
                        "type": m.group("type"), "port": m.group("port")})
    return out


def port_security(text) -> dict:
    """``show port-security interface <if>`` as ``{"status", "last_mac", "last_vlan",
    "violations"}`` (the MAC dotted, ``""`` for none; the count an int, None when absent), or
    ``{}`` when *text* is None or holds no field (tests/fixtures/errdisable/s5_port_security_gi03.txt)."""
    fields = {}
    for line in (text or "").splitlines():
        m = _PSEC_FIELD.match(line.rstrip())
        if m:
            fields[m.group("key").strip().lower()] = m.group("value")
    if not fields:
        return {}
    mac, _, vlan = (fields.get("last source address:vlan") or "").rpartition(":")
    mac = mac_dotted(mac)
    count = (fields.get("security violation count") or "").strip()
    return {"status": fields.get("port status") or "",
            "last_mac": "" if mac == "0000.0000.0000" else mac, "last_vlan": vlan.strip(),
            "violations": int(count) if count.isdigit() else None}


def recovery_for(config: str, cause: str) -> str:
    """The ``errdisable recovery cause`` line of *config* that recovers *cause* by itself (that
    cause, or ``all``), or ``""``."""
    for m in _RECOVERY.finditer(config or ""):
        if m.group("cause") in (cause, "all"):
            return m.group(0).strip()
    return ""


#: ``show errdisable recovery``'s table: its header, and one row, the reason (which may hold
#: spaces, ``channel-misconfig (STP)``, and which IOS cuts at its column: ``Recovery command:
#: "clear``) then its timer's state. s1's capture, tests/fixtures/errdisable/.
_TIMER_HEAD = re.compile(r"^\s*ErrDisable Reason\s+Timer Status\s*$")
_TIMER_ROW = re.compile(r"^(?P<reason>\S.*?)\s+(?P<status>Enabled|Disabled)\s*$")
_TIMER_INTERVAL = re.compile(r"^\s*Timer interval:\s*(?P<s>\d+)\s*seconds", re.M)


def recovery_timer(text, cause: str) -> dict:
    """*cause*'s row of ``show errdisable recovery`` (*text*, its answer): ``{"state", "row",
    "reasons", "interval_s", "why"}``. *state* ``enabled`` (the switch recovers the cause by
    its own timer), ``disabled``, or ``unreadable`` (neither: no answer, an answer with a
    ``%`` line, one with no ``ErrDisable Reason / Timer Status`` table, or a table with no row
    for *cause*), *why* saying which with what was compared. *reasons* is every reason the
    table lists, in order; *interval_s* the timer's interval, or None."""
    out = {"state": "unreadable", "row": "", "reasons": [], "interval_s": None, "why": ""}
    if text is None:
        out["why"] = "no answer"
        return out
    lines = str(text).splitlines()
    err = next((ln.strip() for ln in lines if ln.lstrip().startswith("%")), "")
    if err:
        out["why"] = f"the device answered `{err[:120]}`"
        return out
    head = next((i for i, ln in enumerate(lines) if _TIMER_HEAD.match(ln)), None)
    if head is None:
        first = next((ln.strip() for ln in lines if ln.strip()), "")
        out["why"] = ("the answer is empty" if not first else
                      f"the answer holds no `ErrDisable Reason  Timer Status` table (its first "
                      f"line: `{first[:80]}`)")
        return out
    rows = {}
    for ln in lines[head + 1:]:
        if not ln.strip():
            break                                   # the table ends at its first blank line
        if set(ln.strip()) <= set("- "):
            continue                                # the rule under the header
        m = _TIMER_ROW.match(ln.rstrip())
        if m:
            rows.setdefault(m.group("reason").strip(), (m.group("status"), ln.strip()))
    out["reasons"] = list(rows)
    m = _TIMER_INTERVAL.search(str(text))
    out["interval_s"] = int(m.group("s")) if m else None
    got = rows.get(str(cause or "").strip())
    if got is None:
        shown = ", ".join(list(rows)[:6]) + (" …" if len(rows) > 6 else "")
        out["why"] = (f"its table lists no row for {cause or 'no cause'} ({len(rows)} reason(s)"
                      + (f": {shown}" if rows else "") + ")")
        return out
    out.update(state=got[0].lower(), row=got[1])
    return out


# ── The problem, from the incident's own evidence ───────────────────────────────────────────

def intent_port(intent: dict, port: str) -> dict:
    """What committed intent says of *port*: ``{"found", "description", "vlan", "mode",
    "host", "port_role"}``. The host is the description's first part ("pc-12 - VLAN 10" names pc-12),
    else the description; the role is the switchport mode (access or trunk), else ``""``."""
    for iface in (intent or {}).get("interfaces") or []:
        if isinstance(iface, dict) and same_port(iface.get("name") or "", port):
            desc = str(iface.get("description") or "").strip()
            mode = str(iface.get("switchport_mode") or "").strip()
            host = desc.split(" - ", 1)[0].strip() if desc else ""
            return {"found": True, "description": desc,
                    "vlan": str(iface.get("switchport_access_vlan") or "").strip(),
                    "mode": mode, "host": host[:40],
                    "port_role": mode if mode in ("access", "trunk") else ""}
    return {"found": False, "description": "", "vlan": "", "mode": "", "host": "",
            "port_role": ""}


def classify(device: str, alert_ports, lines: list, *, intent: dict = None,
             now: float = None) -> dict:
    """The err-disable problem the evidence holds (the module's docstring): *alert_ports* the
    interfaces the incident's alerts name, *lines* its device's lines ``[{"line", "at",
    "epoch"}]`` (masked). ``{"state": "classified", "port", "short", "cause", "at", "epoch",
    "mac", "lines", "host", "vlan", "port_role", "cleared", "cleared_at", "classified_at"}``,
    or ``{"state": "unclassified", "why"}`` naming what it compared. Pure."""
    now = time.time() if now is None else float(now)
    parsed = []
    for ln in lines or []:
        p = parse_line(ln.get("line") or "")
        if p:
            parsed.append(dict(p, at=ln.get("at") or "", epoch=float(ln.get("epoch") or 0),
                               line=ln.get("line") or ""))
    errs = [p for p in parsed if p["kind"] == "errdisable" and p["cause"] in CAUSES]
    if not errs:
        other = sorted({p["cause"] for p in parsed if p["kind"] == "errdisable"})
        return {"state": "unclassified", "why": (
            f"{device}'s lines name no port err-disabled by "
            f"{' or '.join(CAUSES)}" + (f" (they name {', '.join(other)})" if other else ""))}
    alert_ports = [a for a in alert_ports or [] if a]
    ports = list(dict.fromkeys(_canon(p["port"]) for p in errs))
    if alert_ports:
        named = [p for p in ports if any(same_port(p, a) for a in alert_ports)]
        if not named:
            return {"state": "unclassified", "why": (
                f"the evidence disagrees: the alert names {', '.join(alert_ports)} on {device}, "
                f"and its lines err-disable {', '.join(_short(p) for p in ports)}")}
        ports = named
    if len(ports) != 1:
        return {"state": "unclassified", "why": (
            f"{device}'s lines err-disable {len(ports)} ports "
            f"({', '.join(_short(p) for p in ports)}), and one incident is one port's problem: "
            "which one is not decided")}
    port = ports[0]
    mine = [p for p in parsed if same_port(p["port"], port)]
    err = max((p for p in errs if same_port(p["port"], port)), key=lambda p: p["epoch"])
    cause = err["cause"]
    mac = next((p["mac"] for p in reversed(mine) if p["kind"] == "violation" and p["mac"]), "")
    ip = intent_port(intent, port)
    if cause == "bpduguard":
        later = [p for p in mine if p["kind"] == "bpdu" and p["epoch"] > err["epoch"]]
        cleared, cleared_at = (("false", later[-1]["at"]) if later else ("true", _iso(now)))
    else:
        cleared, cleared_at = "unknown", ""
    return {"state": "classified", "port": port, "short": _short(port), "cause": cause,
            "at": err["at"], "epoch": err["epoch"], "mac": mac,
            "lines": [{"line": p["line"], "at": p["at"]} for p in mine][-6:],
            "host": ip["host"], "vlan": ip["vlan"],
            "port_role": ip["port_role"], "cleared": cleared, "cleared_at": cleared_at,
            "classified_at": _iso(now)}


def problem_fields(device: str, c: dict) -> dict:
    """The classification *c* as `problem.Problem`'s fields (`problem.FIELDS`), or ``{}``."""
    if not isinstance(c, dict) or c.get("state") != "classified":
        return {}
    cause = str(c.get("cause") or "")
    confirmed = c.get("confirmed") or {}
    cleared, at = str(c.get("cleared") or "unknown"), str(c.get("cleared_at") or "")
    if confirmed.get("cleared") in CLEARED:
        cleared, at = confirmed["cleared"], str(confirmed.get("at") or at)
    return {"device": device, "object": str(c.get("short") or _short(c.get("port") or "")),
            "condition": CONDITION, "cause": CAUSES.get(cause, cause),
            "port_role": str(c.get("port_role") or ""),
            "affected": str(c.get("host") or "") or "its host",
            "cause_cleared": CLEARED_CHECKS.get(cause, ""),
            "cleared": cleared if cleared in CLEARED else "unknown", "cleared_at": at}


def of_record(record: dict) -> dict:
    """The classification an incident's *record* keeps (`FIELD`), or ``{}``."""
    got = (record or {}).get(FIELD) if isinstance(record, dict) else None
    return dict(got) if isinstance(got, dict) else {}


def evidence_rows(record: dict) -> list:
    """The device confirmation read and the lines the classification stands on, as the incident
    page's evidence (`problem.evidence`'s rows ``{"kind", "words", "at"}``)."""
    c = of_record(record)
    if c.get("state") != "classified":
        return []
    out = []
    conf = c.get("confirmed") or {}
    if conf.get("unread"):
        out.append({"kind": "device_read", "at": conf.get("at") or "", "words": (
            f"{conf.get('why') or CONFIRM_READ + ' could not be read'} at "
            f"{conf.get('at') or '?'}: no action until the device confirms the port and "
            "the cause")})
    elif conf:
        found = conf.get("found") or {}
        out.append({"kind": "device_read", "at": conf.get("at") or "", "words": (
            f"{CONFIRM_READ} read at {conf.get('at') or '?'}: "
            + (f"{found.get('port')} err-disabled by {found.get('reason')}" if found
               else "the port is not listed err-disabled")
            + ("; it agrees with the evidence" if conf.get("agrees")
               else f"; it disagrees with the evidence ({conf.get('why') or ''}), so no action "
                    "is taken"))})
    for ln in c.get("lines") or []:
        if isinstance(ln, dict):
            out.append({"kind": "log", "words": str(ln.get("line") or ""),
                        "at": str(ln.get("at") or "")})
    return out


def confirmation(rows: list, port: str, cause: str, at: str) -> dict:
    """The device read *rows* (`status_rows` with reasons) against the evidence's *port* and
    *cause*: ``{"at", "agrees", "found", "why"}``."""
    found = next((r for r in rows if same_port(r["port"], port)), None)
    if not found:
        return {"at": at, "agrees": False, "found": {}, "why": (
            f"{_short(port)} is not listed err-disabled"
            + (f" (listed: {', '.join(r['port'] for r in rows)})" if rows else ""))}
    agrees = found.get("reason") == cause
    return {"at": at, "agrees": agrees, "found": {"port": found["port"],
                                                   "reason": found.get("reason") or ""},
            "why": "" if agrees else (f"the device says {found['port']} is err-disabled by "
                                      f"{found.get('reason') or 'no reason'}, and the evidence "
                                      f"says {cause}")}


# ── Where it reads (each replaceable in a test) ─────────────────────────────────────────────

def _model_sources():
    from modules.nsot.command_plan import Sources as ModelSources

    return ModelSources


class Sources(_model_sources()):
    """Mercury's model (the inventory, committed intent and the golden: the command plan's own
    `command_plan.Sources`), the device's lines in Loki, the reads engine, the clock, the sleep
    and the notification."""

    def __init__(self, network: str, *, clock=time.time, sleep=time.sleep):
        super().__init__(network)
        self.clock, self.sleep = clock, sleep

    def lines(self, dev: dict, since: float, until: float) -> dict:
        return log_lines(dev, since, until)

    def read(self, host: str, commands: list) -> dict:
        """``{command: answer, "_run"}``, or ``{"_why"}``: through THE reads engine, as
        self-healing's read."""
        from modules.nsot import reads

        try:
            rec = reads.run(self.network, [host], commands, ACTOR, by=READS_BY,
                            purpose="self-healing: the err-disabled port's confirmation read")
        except reads.Refused as exc:
            return {"_why": str(exc)}
        r = (rec.get("results") or {}).get(host) or {}
        got = {a["command"]: a.get("answer") or "" for a in r.get("answers") or []
               if a.get("state") == "answered"}
        return dict(got or {"_why": r.get("why") or r.get("state") or "not read"},
                    _run=rec.get("id", ""))

    def notify(self, network: str, event: dict) -> dict:
        from modules import heal_notify
        from modules.notify import delivery

        teams = heal_notify.teams_for(network, event.get("event") or "action")
        if not teams:
            return {"ok": True, "sent": 0, "nobody": True}
        return delivery.deliver_event(event, teams)


#: The device's lines this problem reads in Loki, by their mnemonics (Cisco IOS's).
LINE_PATTERN = "(?:ERR_DISABLE|BLOCK_BPDUGUARD|PSECURE_VIOLATION|UPDOWN):"
LINES_LIMIT = 100


def log_lines(dev: dict, since: float, until: float) -> dict:
    """*dev*'s err-disable, BPDU guard, port-security and up/down lines in Loki from *since* to
    *until*, oldest first, masked: ``{"error", "lines": [{"line", "at", "epoch"}], "cut"}``.
    Never raises; Loki unconfigured or unreadable is its error, never "no lines"."""
    from modules import device_logs
    from modules.integrations.loki import LokiIntegration
    from modules.redact import redact_text

    host = dev.get("hostname", "")
    out = {"error": "", "lines": [], "cut": False}
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}", host or ""):
        return dict(out, error=f"the name {host!r} cannot be matched safely in a log query")
    loki = LokiIntegration()
    if not loki.is_configured():
        return dict(out, error="Loki is not configured")
    try:
        sel = device_logs.selector(host, start=since, client=loki)
    except Exception as exc:                          # noqa: BLE001 (said)
        return dict(out, error=f"the syslog job could not be found: {exc}")
    r = loki._get("loki/api/v1/query_range", query=f"{sel} |~ `{LINE_PATTERN}`",  # noqa: SLF001
                  limit=LINES_LIMIT, start=int(since * 1e9), end=int(until * 1e9),
                  direction="backward")
    if not r.get("ok"):
        return dict(out, error=f"Loki could not be asked: {r.get('error')}")
    try:
        streams = (r["response"].json().get("data") or {}).get("result") or []
    except (ValueError, AttributeError) as exc:
        return dict(out, error=f"Loki's answer could not be read: {exc}")
    rows = [{"line": redact_text(line), "epoch": int(ns) / 1e9, "at": _iso(int(ns) / 1e9)}
            for s in streams for ns, line in s.get("values") or []]
    rows.sort(key=lambda x: x["epoch"])
    return dict(out, lines=rows, cut=len(rows) >= LINES_LIMIT)


# ── Re-classifying open incidents ───────────────────────────────────────────────────────────

#: The trigger kinds a port problem is read for: an alert on a port, or the err-disable line
#: itself (`triggers.ERRDISABLE_KIND`: decided from the device read as soon as it arrives).
PORT_TRIGGERS = ("alert", "errdisable")


def _alert_ports(inc: dict) -> list:
    return [t.get("interface") for t in inc.get("triggers") or []
            if isinstance(t, dict) and t.get("kind") in PORT_TRIGGERS and t.get("interface")]


def _due(inc: dict, now: float) -> bool:
    """Whether *inc* is read for this problem now: open, an alert among its triggers, and no
    classification, or an unclassified one older than `RECHECK_S` or with a newer trigger."""
    from modules.heal import incidents

    if inc.get("state") not in incidents.OPEN_STATES:
        return False
    if not any(isinstance(t, dict) and t.get("kind") in PORT_TRIGGERS
               for t in inc.get("triggers") or []):
        return False
    c = of_record(inc)
    if c.get("state") == "classified":
        conf = c.get("confirmed") or {}
        # Read again every RECHECK_S while open (the operator, 2026-11-16): a port read no longer
        # err-disabled closes its incident at once on that read (`detect._port_clear`).
        return not conf or now - float(conf.get("epoch") or 0) >= RECHECK_S
    if not c:
        return True
    return (now - float(c.get("checked_epoch") or 0) >= RECHECK_S
            or int(inc.get("triggers_seen") or 0) != int(c.get("seen") or 0))


def _opened(inc: dict) -> float:
    trig = [t for t in inc.get("triggers") or [] if isinstance(t, dict)]
    first = min([float(t.get("epoch") or 0) for t in trig if t.get("epoch")] or [0.0])
    if first:
        return first
    from modules.heal.triggers import _epoch

    return _epoch(inc.get("opened_at")) or 0.0


def reclassify(network: str, inc: dict, *, sources=None, now: float = None) -> dict:
    """*inc* (an open incident of *network*) read once for this problem from its own evidence,
    then, once classified, the device read confirming it (`confirm`). Returns the record to keep
    under `FIELD`. Reads Loki, committed intent and (classified) the device through the reads
    engine; writes nothing."""
    src = sources or Sources(network)
    now = src.clock() if now is None else float(now)
    device = inc.get("device") or ""
    c = of_record(inc)
    if c.get("state") != "classified":
        dev = src.device(device)
        if not dev:
            return {"state": "unclassified", "why": f"{device} is no device of {network}",
                    "checked_epoch": now, "seen": int(inc.get("triggers_seen") or 0)}
        since = _opened(inc) - LOOKBACK_S
        got = src.lines(dev, since, now)
        if got.get("error"):
            return {"state": "unclassified", "why": f"{device}'s lines could not be read: "
                                                     f"{got['error']}",
                    "checked_epoch": now, "seen": int(inc.get("triggers_seen") or 0)}
        intent, _err = src.intent(device)
        c = classify(device, _alert_ports(inc), got.get("lines") or [], intent=intent, now=now)
        c.update(checked_epoch=now, seen=int(inc.get("triggers_seen") or 0))
        if c["state"] != "classified":
            return c
    c["confirmed"] = confirm(network, device, c, sources=src, now=now)
    return c


def confirm(network: str, device: str, c: dict, *, sources=None, now: float = None) -> dict:
    """The device read before any action (R4): ``show interfaces status err-disabled`` (and, for
    port security, its port-security and MAC tables: whether the violating MAC is still there)
    through the reads engine. ``{"at", "agrees", "found", "why", "run", "cleared"?}``."""
    src = sources or Sources(network)
    now = src.clock() if now is None else float(now)
    cmds = [CONFIRM_READ]
    psec = c.get("cause") == "psecure-violation"
    if psec:
        cmds += [PSEC_READ, f"show mac address-table interface {c['port']}",
                 PSEC_IF_READ.format(port=c["port"])]
    got = src.read(device, cmds)
    at = _iso(now)
    if "_why" in got or CONFIRM_READ not in got:
        return {"at": at, "epoch": now, "agrees": False, "found": {}, "unread": True,
                "run": got.get("_run", ""),
                "why": f"{CONFIRM_READ} could not be read: {got.get('_why') or 'no answer'}"}
    out = confirmation(status_rows(got.get(CONFIRM_READ) or "", reasons=True), c["port"],
                       c["cause"], at)
    out.update(run=got.get("_run", ""), epoch=now)
    if psec and c.get("mac"):
        still = violator_seen(c["mac"], c["port"], got.get(PSEC_READ),
                              got.get(f"show mac address-table interface {c['port']}"))
        if still is not None:
            out["cleared"] = "false" if still else "true"
    if psec:
        # The violation count at this read: the cause-cleared check's baseline when this read
        # came after the err-disable (`check_cause_cleared`).
        ps = port_security(got.get(PSEC_IF_READ.format(port=c["port"])))
        if ps:
            out["psec"] = {"violations": ps["violations"], "last_mac": ps["last_mac"]}
    return out


def violator_seen(mac: str, port: str, psec_text, table_text):
    """Whether the violating *mac* is on *port*'s port-security table or its MAC table; None
    when either read is missing (an unreadable read neither passes nor fails)."""
    if psec_text is None or table_text is None:
        return None
    want = mac_dotted(mac)
    for r in mac_rows(psec_text) + mac_rows(table_text):
        if r["mac"] == want and same_port(r["port"], port):
            return True
    return False


def reclassify_step(network: str, *, sources=None, now: float = None) -> dict:
    """The detect loop's step: every due open incident of *network* read for this problem
    (`_due`), each answer kept on its record (`incidents.record_problem`). ``{"read",
    "classified", "errors"}``. Never raises."""
    from modules.heal import incidents

    out = {"read": 0, "classified": [], "errors": []}
    got = incidents.read(network)
    if got.get("state") != "ok":
        return out
    at = time.time() if now is None else float(now)
    for inc in got["incidents"]:
        if not _due(inc, at):
            continue
        try:
            c = reclassify(network, inc, sources=sources, now=at)
            incidents.record_problem(network, inc["id"], FIELD, c)
            out["read"] += 1
            if c.get("state") == "classified":
                out["classified"].append(inc["id"])
        except Exception as exc:                      # noqa: BLE001 (the next pass tries again)
            log.warning("errdisable: %s's %s could not be classified: %s", network,
                        inc.get("id"), exc)
            out["errors"].append(f"{inc.get('id')}: {type(exc).__name__}: {exc}")
    return out


def scope_refusal(network: str, incident_id: str, device: str, port: str, cause: str) -> str:
    """Why a recovery proposed in *incident_id* is outside its scope, or ``""``: the incident's
    own problem must be this port err-disabled by this cause, classified from its evidence and
    confirmed by the device read (R4: evidence and device disagreeing is no action)."""
    from modules.heal import incidents

    got = incidents.read(network)
    inc = next((i for i in got.get("incidents") or [] if i.get("id") == incident_id), None)
    if inc is None:
        return (f"{incident_id} is no incident {network}'s store holds"
                + (f" ({got.get('error')})" if got.get("error") else ""))
    c = of_record(inc)
    if c.get("state") != "classified":
        return (f"{incident_id}'s evidence is not classified as an err-disabled port"
                + (f" ({c.get('why')})" if c.get("why") else "")
                + ", so no recovery acts in it")
    if not same_port(c.get("port") or "", port) or c.get("cause") != cause:
        return (f"the proposal names {_short(port)} err-disabled by {cause}, and {incident_id}'s "
                f"problem is {c.get('short')} err-disabled by {c.get('cause')}: a proposal acts "
                "only on what its incident names")
    conf = c.get("confirmed") or {}
    if conf.get("agrees") is not True:
        return (f"the device has not confirmed {c.get('short')} err-disabled by "
                f"{c.get('cause')} ({conf.get('why') or 'not read yet'}), so no action is taken")
    return ""


# ── The recovery: the built-in command plan's checks and its finish (C3757, path 2) ─────────
#
# The recovery is no operation of its own: it is the built-in command plan
# `modules/nsot/command_plans/errdisable-recover.yml`, run by the command-plan runner on the
# deploy pipeline's engine (`command_plan_run.run`). Its template names these checks
# (`command_plan.NAMED_CHECKS`): each takes the read's answer (None when it could not be read)
# and the run (`command_plan_run.CheckRun`: its validated values, the incident it acts in, its
# sources), and answers ``(result, words)``, result ``pass``, ``fail`` or ``unreadable`` (an
# unreadable read neither passes nor fails: the plan refuses).

def _port_cause(run) -> tuple:
    d = run.derived
    return d.get("interface") or "", d.get("cause") or "", d.get("interface_short") or ""


def check_port_listed(answer, run) -> tuple:
    """The port is err-disabled by the cause now (``show interfaces status err-disabled``)."""
    port, cause, short = _port_cause(run)
    if answer is None:
        return "unreadable", f"{CONFIRM_READ} could not be read"
    conf = confirmation(status_rows(answer, reasons=True), port, cause, _iso(run.at))
    if conf["agrees"]:
        return "pass", f"{conf['found']['port']} err-disabled by {conf['found']['reason']}"
    return "fail", (f"the device and the plan disagree ({conf['why']}), so the plan does not "
                    f"act on {short}")


def check_port_not_listed(answer, run) -> tuple:
    """The re-trip check ("Then re-checks for 10 s: does it trip again?"): the port not listed
    in the err-disabled view. Listed again by its own cause is the run's own outcome, the
    re-trip (`command_plan_run.RETRIPPED`, the operator, 2026-11-16): its device is still
    connected, the port is left err-disabled and nothing more is sent (`retrip_words`); listed
    by another reason fails, as before."""
    from modules.nsot.command_plan_run import RETRIPPED

    port, cause, short = _port_cause(run)
    if answer is None:
        return "unreadable", f"{CONFIRM_READ} could not be read"
    again = [r for r in status_rows(answer, reasons=True) if same_port(r["port"], port)]
    if again and again[0].get("reason") == cause:
        return RETRIPPED, retrip_words(run, port, cause, short)
    if again:
        return "fail", (f"{short} err-disabled again by {again[0].get('reason')}: its cause is "
                        "still there")
    return "pass", f"{short} did not trip again"


def retrip_words(run, port: str, cause: str, short: str) -> str:
    """The re-trip's finding, the operator's words (2026-11-16): "The device with MAC <mac> is
    still connected to <device> <port>. Port left err-disabled; nothing more sent." The MAC is
    the port's Last Source Address read now (port security), else the one the preconditions
    found; BPDU guard's lines name no MAC. Kept on ``run.found["retrip"]``."""
    mac = ""
    if cause == "psecure-violation":
        cmd = PSEC_IF_READ.format(port=port)
        mac = port_security(run.sources.read(run.device, [cmd]).get(cmd)).get("last_mac") or ""
        mac = mac_colon(mac) or (run.found.get("mac") or "")
    who = (f"The device with MAC {mac}" if mac else
           "The device sending BPDUs" if cause == "bpduguard" else "The device that tripped it")
    run.found["retrip"] = {"mac": mac, "device": run.device, "port": short, "cause": cause,
                           "at": _iso(run.at)}
    return f"{who} is still connected to {run.device} {short}. {RETRIP_TAIL}"


def check_port_connected(answer, run) -> tuple:
    """The port reads connected in ``show interfaces status``."""
    port, _cause, short = _port_cause(run)
    if answer is None:
        return "unreadable", f"{STATUS_READ} could not be read"
    rows = [r for r in status_rows(answer) if same_port(r["port"], port)]
    state = rows[0]["status"] if rows else "not listed"
    return ("pass" if state == "connected" else "fail"), f"{short} reads {state}"


def check_port_not_admin_down(answer, run) -> tuple:
    """The port is not administratively down (``show interfaces status``, the status read the
    connected check reads: ``disabled`` is a port shut on purpose). ``shutdown`` then ``no
    shutdown`` leaves a port as it was only from a port that is up (the review, 2026-11-16,
    C1): a port shut on purpose fails, and nothing is sent; one the table does not list is
    unreadable."""
    port, _cause, short = _port_cause(run)
    if answer is None:
        return "unreadable", f"{STATUS_READ} could not be read"
    rows = [r for r in status_rows(answer) if same_port(r["port"], port)]
    if not rows:
        return "unreadable", f"{short} is not listed in {STATUS_READ}"
    if rows[0]["status"] == "disabled":
        return "fail", (f"{short} reads disabled: it is administratively down on purpose, and "
                        "shutdown / no shutdown would bring it up, so nothing is sent")
    return "pass", f"{short} reads {rows[0]['status']}: not administratively down"


def check_no_recovery(answer, run) -> tuple:
    """The switch does not recover the cause itself: the cause's row of ``show errdisable
    recovery``'s timer table (`recovery_timer`) Disabled passes; Enabled fails (the switch
    recovers it by its own timer, and Mercury never races it); a cause the table does not
    list, or an answer that is not the table (none, a ``%`` line, empty), is unreadable,
    neither a pass nor a fail, so the plan refuses, naming the cause looked for and what the
    answer held."""
    _port, cause, short = _port_cause(run)
    name = CAUSES.get(cause, cause)
    if answer is not None and not any(_TIMER_HEAD.match(ln)
                                      for ln in str(answer).splitlines()):
        # Expand, then contract (CLAUDE.md): a script saved before 2026-11-16 keeps its own
        # copy of the template, whose read is ``show running-config | include errdisable
        # recovery``. Its answer is not the table, so the check reads the table itself, on
        # the run's session, and judges that: the same answer a new template's read gives.
        try:
            answer = run.sources.read(run.device, [RECOVERY_READ]).get(RECOVERY_READ)
        except Exception as exc:                      # noqa: BLE001 (unreadable, said)
            log.warning("errdisable: %s's %s could not be read: %s", run.device,
                        RECOVERY_READ, exc)
            answer = None
    if answer is None:
        return "unreadable", f"`{RECOVERY_READ}` could not be read"
    t = recovery_timer(answer, cause)
    if t["state"] == "enabled":
        every = f" (every {t['interval_s']} s)" if t["interval_s"] else ""
        return "fail", (f"`{RECOVERY_READ}` lists {cause}'s timer Enabled{every}: the switch "
                        f"recovers {short} by itself, and Mercury does not race it")
    if t["state"] == "disabled":
        return "pass", (f"`{RECOVERY_READ}` lists {cause}'s timer Disabled: no errdisable "
                        f"recovery for {name}")
    return "unreadable", (f"whether the switch recovers {name} itself cannot be told: "
                          f"`{RECOVERY_READ}` was read for {cause}'s row under ErrDisable "
                          f"Reason / Timer Status, and {t['why']}")


def preview_no_recovery(network: str, dev: dict, derived: dict, sources) -> tuple:
    """The same check, from the device's golden, at preview (no device is asked)."""
    cause = derived.get("cause") or ""
    src = sources if sources is not None and hasattr(sources, "golden") else Sources(network)
    golden, err = src.golden(dev.get("hostname") or derived.get("device") or "")
    if golden is None:
        return None, f"its golden could not be read ({err})"
    line = recovery_for(golden, cause)
    if line:
        return "fail", (f"its golden holds \"{line}\": the switch recovers "
                        f"{derived.get('interface_short')} by itself, and Mercury does not "
                        "race it")
    return "pass", ""


def _classification(network: str, incident_id: str) -> dict:
    from modules.heal import incidents

    if not incident_id:
        return {}
    got = incidents.read(network)
    inc = next((i for i in got.get("incidents") or [] if i.get("id") == incident_id), None)
    return of_record(inc) if inc else {}


#: What each check here reads where its template's item names no read of its own, and what it
#: cannot prove on a port that is down, with what proves it instead, as a fix's page says them
#: (`modules/fix_page.py`; the operator's change 1 to board fix-bpdu-guard, 2026-11-16: "say
#: what the built check actually reads ... or state plainly what it can't prove"). Keyed by the
#: check's function, then, for a check that reads differently per cause, by the plan's
#: parameter ``by`` names and its value. Each sentence is this module's, beside the code it
#: describes: `check_cause_cleared` and `_psecure_cleared` below.
SAYS = {
    "check_cause_cleared": {
        "by": "cause",
        "bpduguard": {
            "label": CAUSES["bpduguard"],
            "reads": "the switch's own log lines, in Loki: a BPDU-guard line for the port "
                     "after its err-disable's time",
            "limit": "A port that is down processes no BPDU, so finding none since proves "
                     "nothing: this check fails only on a BPDU-guard line after the "
                     "err-disable, and otherwise is deferred, never passed. What proves it "
                     "is verify's re-trip check after the bounce: a BPDU source still "
                     "attached trips the port again within 10 s."},
        "psecure-violation": {
            "label": CAUSES["psecure-violation"],
            "reads": "the port's PSECURE_VIOLATION log lines since its err-disable, in Loki, "
                     f"and its violation count ({PSEC_IF_READ.format(port='{interface}')}); "
                     "the violating MAC named",
            "limit": "A violator still attached but quiet while the port is down adds no "
                     "line and no count, so this check cannot prove it has gone: it fails only "
                     "on a violation after the err-disable or a count that rose, and "
                     "otherwise is deferred, never passed. What proves "
                     "it is verify's re-trip check after the bounce: a violator still "
                     "attached trips the port again."}},
    "check_no_recovery": {
        "reads": f"{RECOVERY_READ} (its timer table) at the run; the golden's errdisable "
                 "recovery cause lines at the preview"},
}


def check_cause_cleared(_answer, run) -> tuple:
    """The cause has cleared: BPDU guard, no BPDU guard line for the port in its device's
    lines since the err-disable; port security, the violating MAC (from the incident's
    classification) on neither the port's port-security table nor its MAC table. A cause not
    cleared fails ("Port stays down: ..."); one that cannot be told is unreadable."""
    port, cause, short = _port_cause(run)
    # The run's preconditions read its lines beside the device's reads (`AHEAD`, one thread,
    # joined before this check is judged); without them (a direct call) it reads them now.
    ahead = (getattr(run, "ahead", None) or {}).get("check_cause_cleared")
    told = ahead if ahead is not None else cause_lines(run)
    if told.get("raised"):
        return "unreadable", (f"whether the cause has cleared on {short} cannot be told: "
                              f"{told['raised']}")
    c, got, start = told["c"], told["got"], told["start"]
    if cause == "bpduguard":
        if got.get("error"):
            return "unreadable", f"whether BPDUs still arrive on {short} cannot be told: " \
                                 f"{got['error']}"
        later = [ln for ln in got.get("lines") or []
                 if (lambda x: x.get("kind") == "bpdu" and same_port(x.get("port"), port))(
                     parse_line(ln.get("line") or "")) and ln.get("epoch", 0) > start + 1]
        if later:
            return "fail", ("Port stays down: BPDUs are still arriving on it, so its cause is "
                            f"still connected (the last at {later[-1].get('at')})")
        # No BPDU is processed while the port is err-disabled, so no line since is an absence
        # nothing showed could be found (the review of Gate 1a): never a pass. It is judged
        # after the bounce, by verify's no new err-disable.
        return "deferred", (f"whether BPDUs still arrive on {short} cannot be told while the "
                            "port is down; judged after the bounce by verify's no new "
                            "err-disable")
    return _psecure_cleared(run, port, cause, short, c, got)


def cause_lines(run, src=None) -> dict:
    """What `check_cause_cleared` judges besides the device: the incident's classification and
    the port's lines in Loki from its err-disable (BPDU guard: from the classification's time,
    else `LOOKBACK_S` back; port security: `LOOKBACK_S` before it, else
    `ERRDISABLE_LOOKBACK_S` back) to now. ``{"c", "got", "start", "until"}``; *got* is
    `log_lines`' answer (its ``error`` said, never "no lines"). No device is read here, so a
    run reads it in a thread beside its device reads (`AHEAD`)."""
    _port, cause, _short = _port_cause(run)
    src = src if src is not None else run.sources.of("errdisable")
    c = _classification(run.network, run.incident)
    until = run.at
    since = float(c.get("epoch") or 0)
    if cause == "bpduguard":
        start = since or (until - LOOKBACK_S)
    else:
        start = (since - LOOKBACK_S) if since else (until - ERRDISABLE_LOOKBACK_S)
    got = src.lines(src.device(run.device) or run.dev, start, until)
    return {"c": c, "got": got, "start": start, "until": until}


#: How close a violation and the err-disable it causes are logged: the same second on IOS
#: (s5's 18:21:58 pair, 2026-11-16), so ten seconds tells the triggering one from a new one.
TRIGGER_S = 10


def _psecure_cleared(run, port: str, cause: str, short: str, c: dict, got: dict) -> tuple:
    """Port security's cause cleared while the port is down (the operator, 2026-11-16): no
    new violation since the err-disable, by the port's ``PSECURE_VIOLATION`` lines (*got*,
    `cause_lines`: none after its newest err-disable line) and its violation count (unchanged
    from the one the device confirmation read after that err-disable, when it holds one); the
    violating MAC named from the line, else the port's Last Source Address. The count is read
    through the run's sources: inside a run's preconditions, the one device read they asked
    together (`AHEAD`). Verify's re-trip check catches a violator still connected once the
    port is up. Kept on ``run.found`` for the run's record."""
    cmd = PSEC_IF_READ.format(port=port)
    ps = port_security(run.sources.read(run.device, [cmd]).get(cmd))
    since = float(c.get("epoch") or 0)
    mine = []
    for ln in got.get("lines") or []:
        p = parse_line(ln.get("line") or "")
        if p and same_port(p.get("port") or "", port):
            mine.append(dict(p, epoch=float(ln.get("epoch") or 0), at=ln.get("at") or ""))
    errs = [p for p in mine if p["kind"] == "errdisable" and p["cause"] == cause]
    trips = [p for p in mine if p["kind"] == "violation" and p["mac"]]
    # The violation that err-disabled the port lands within seconds of its err-disable line
    # (s5, 2026-11-16: both at 18:21:58): it is the cause, never "new". New is a violation
    # after that pair; with no err-disable line read, the first violation is the trigger.
    anchor = (max(p["epoch"] for p in errs) if errs else
              min(p["epoch"] for p in trips) if trips else since)
    err_epoch = anchor
    later = [p for p in trips if anchor and p["epoch"] > anchor + TRIGGER_S]
    mac = (trips[-1]["mac"] if trips else "") or ps.get("last_mac") or mac_dotted(
        c.get("mac") or "")
    run.found.update(mac=mac_colon(mac), port=short, cause=cause,
                     err_at=_iso(err_epoch) if err_epoch else "",
                     violations=ps.get("violations"))
    who = f"the device with MAC {mac_colon(mac)}" if mac else "the device that tripped it"
    if later:
        return "fail", (f"Port stays down: {who} is still connected (a new violation at "
                        f"{later[-1]['at']})")
    conf = c.get("confirmed") or {}
    base = (conf.get("psec") or {}).get("violations")
    if float(conf.get("epoch") or 0) < err_epoch:
        base = None
    count = ps.get("violations")
    if base is not None and count is not None and count > base:
        return "fail", (f"Port stays down: {who} is still connected (the violation count is "
                        f"{count}, {base} at the err-disable)")
    lines_told = not got.get("error") and bool(err_epoch)
    if not lines_told and (base is None or count is None):
        why = got.get("error") or f"no err-disable line for {short} in its lines"
        return "unreadable", (f"whether a violation came since {short}'s err-disable cannot be "
                              f"told: {why}" + ("" if ps else f", and {cmd} could not be read"))
    said = [f"no new violation on {short} since its err-disable"
            + (f" at {_iso(err_epoch)}" if err_epoch else "")
            + ("" if errs else f" (no err-disable line for {short} in its lines)")]
    if count is not None:
        said.append(f"violation count {count}"
                    + (", as at the err-disable" if base is not None else ""))
    if mac:
        said.append(f"the violating MAC {mac_colon(mac)}")
    # A port that is down passes no frame, so no violation line and no count rise can come
    # while it is err-disabled: none since is an absence nothing showed could be found (the
    # correctness review's G1 MEDIUM-1 and G3 M2, 2026-11-18), never a pass, as BPDU guard's.
    return "deferred", (f"whether {who} is still connected cannot be told while {short} is "
                        "down (" + "; ".join(said) + "); judged after the bounce by verify's "
                        "no new err-disable")


def _ahead_no_recovery(_read: str, _run) -> dict:
    # The timer table, whatever the item's own read (an old saved script's `show running-config
    # | include errdisable recovery` is never judged: the check reads the table in its place).
    return {"device": [RECOVERY_READ], "answer_of": RECOVERY_READ}


def _ahead_cause_cleared(_read: str, run) -> dict:
    port, cause, _short = _port_cause(run)
    src = run.sources.of("errdisable")
    return {"device": [PSEC_IF_READ.format(port=port)] if cause == "psecure-violation" else [],
            "answer_of": "", "other": lambda: cause_lines(run, src)}


#: What each check here asks before it is judged, so a run's preconditions ask every device
#: read in one read-engine run and the rest beside it (`command_plan_run._ahead`; the
#: operator, 2026-11-16: preconditions batching). Keyed by the check's function; each answers
#: ``{"device": [commands], "answer_of": the command whose answer the check is handed, "other":
#: a callable reading no device (run in a thread beside the device's reads) or absent}``. A
#: check not listed is asked its item's own read and handed its answer, as before.
AHEAD = {"check_no_recovery": _ahead_no_recovery,
         "check_cause_cleared": _ahead_cause_cleared}


def offender_words(rec: dict) -> str:
    """The offending device, the port, the time and the cause, as the record and the
    notification say them."""
    o = rec.get("offender") or {}
    mac = f"MAC {o['mac']}" if o.get("mac") else "a MAC not logged"
    return (f"{rec.get('device')} {o.get('port')} was err-disabled by "
            f"{o.get('cause_words') or ''} at {o.get('at') or 'a time not logged'}, tripped by "
            f"{mac}")


def on_finish(network: str, rec: dict, *, sources=None) -> None:
    """The plan's finish (its template's ``on_finish``): the offender kept on the run's record
    (the MAC, the port, the time and the cause), and every run that sent, or refused because
    its cause has not cleared, notifies the engineer (C3712)."""
    from modules.nsot.command_plan_run import RETRIPPED

    values = rec.get("params") or {}
    c = _classification(network, str((rec.get("fixit") or {}).get("incident") or ""))
    cause = values.get("cause") or ""
    found = rec.get("found") or {}
    rec["offender"] = {"mac": (found.get("retrip") or {}).get("mac") or found.get("mac")
                       or mac_colon(c.get("mac") or ""),
                       "port": _short(values.get("interface") or ""), "cause": cause,
                       "cause_words": CAUSES.get(cause, cause),
                       "at": found.get("err_at") or (_iso(c["epoch"]) if c.get("epoch") else "")}
    pre = rec.get("preconditions") or []
    not_cleared = any(p.get("result") == "fail" and p.get("words", "").startswith(
        "Port stays down") for p in pre)
    outcome = rec.get("outcome")
    src = sources or Sources(network)
    if outcome == "done":
        # The success words where the host is known (the operator, 2026-11-16; `bluf.RESTORED`).
        host = str(c.get("host") or "")
        if not host:
            try:
                intent, _err = src.intent(rec.get("device") or "")
                host = intent_port(intent, values.get("interface") or "")["host"]
            except Exception as exc:                  # noqa: BLE001 (said without the host)
                log.info("errdisable: the recovered port's host was not read: %s", exc)
        if host:
            rec["said"] = rec["why"] = f"Fixed: {host} is back online."
    if outcome == RETRIPPED:
        # The recurrence finding, as the run said it: kept for the incident's page, the AI's
        # evidence (its attempt's outcome and words) and Needs attention (`rec["recurrence"]`).
        rec["said"] = rec.get("why") or ""
        rec["recurrence"] = dict(found.get("retrip") or {}, words=rec["said"])
    if outcome == "refused" and not not_cleared:
        return
    ended = ("recovered" if outcome == "done" else "tripped again" if outcome == RETRIPPED
             else "not recovered")
    event = {"incident": str((rec.get("fixit") or {}).get("incident") or rec["id"])[:80],
             "event": ("action" if outcome == "done" else "held" if not_cleared
                       else "cant_fix"),
             "network": network, "device": rec.get("device") or "", "kind": KEY,
             "title": f"{rec.get('device')} {rec['offender']['port']}: {ended}"[:120],
             "lead": (next(p["words"] for p in pre if p.get("words", "").startswith(
                 "Port stays down")) if not_cleared else rec["said"] if outcome == RETRIPPED
                 else offender_words(rec))[:800],
             "happened": offender_words(rec)[:800],
             "outcome": str(rec.get("why") or outcome)[:400]}
    try:
        got = src.notify(network, event)
        rec["notified"] = {"sent": int(got.get("sent") or 0), "nobody": bool(got.get("nobody")),
                           "error": str(got.get("error") or "")}
    except Exception as exc:                          # noqa: BLE001 (said in the record)
        rec["notified"] = {"sent": 0, "error": f"{type(exc).__name__}: {exc}"}


