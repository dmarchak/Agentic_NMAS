"""Tier 2: "Run a privileged command…", one device, from its Actions menu
(docs/NSOT_TIER2_PRIVILEGED.md, boards T2-A to T2-D; approved 2026-10-08 with decisions T2-1 to
T2-4; built from the probe's measurements on r2 and s1 the same day, section 5).

A recoverable exec command that changes the device's state is an OPERATION, never free text: the
command is picked from `COMMANDS`, its argument from the device's own interfaces (its committed
golden, never typed), and it runs through every device-changing operation's lifecycle:

1. ``refuse``: the plan refuses before anything is read: a command not in `COMMANDS`, one not yet
   measured (`NOT_MEASURED`), an interface the device's golden does not hold, or the one carrying
   the address Mercury reaches it on (C583's rule);
2. ``read``: the preview reads the before-state through the reads engine (a recorded run), and
   the card shows it with what the command affects, what it will not do, and why rollback does
   not apply;
3. ``confirm``: a verified person confirms with a reason of three words or more (T2-2), bound by
   hash to the device, the command and its argument;
4. ``send``: holding the device, the before-state is read again and KEPT (masked, capped; T2-4:
   these commands destroy evidence), the command is sent once, and the MEASURED prompt alone is
   answered with Enter; any other question is not answered and the session is closed, which
   abandons the command;
5. ``verify``: the after-state read back and judged by the measured rule (`_verify`);
6. ``record``: the run is written, as the person, with the reason, the before-state, what the
   device printed and the verdict; History shows it.

Rollback does not apply, and every preview says why: what these commands clear cannot be put back,
and the device rebuilds it by itself (counters count again, ARP relearns, a buffer fills).

The agent never runs one (T2-3): no tool of the agent's reaches this module.

**The OSPF process resets** (board H, part H5; docs/HEAL_TO_INTENT.md section 5, N17, 19.8's
"process clear"): `PROCESS_RESETS`, the same six steps for one more kind of command, which is
NOT on the Actions menu (`COMMANDS`): a process reset drops every adjacency of the process, so
it is sent only inside a heal a person approved (a router-id that takes effect only through
it, R8's proposal) or, later, on a router with exactly one OSPF adjacency (N17, `reset_plan`'s
``single_adjacency``). Its prompt, its answer and its settle time are a PLATFORM MEASUREMENT
(`privileged_measured.json`, `reset_measured`), and a reset with no row there is refused as
not measured, naming why: nothing is answered by resemblance. It is sent on the session the
heal's apply holds (`send_reset`), between the pipeline's verify and the save to startup; its
before-state is kept; its verify reads the neighbour table again until the adjacencies formed
before are formed again, within about 2.5 times the measured settle time.

**The BGP session clears** (board H, part H21; docs/HEAL_TO_INTENT.md 19.4 and N16):
`SESSION_CLEARS`, the same six steps for one named BGP neighbour, NOT on the Actions menu: they
are sent by self-healing's session clear (`modules/heal/session_clear.py`), as the policy on a
network marked lab and as the approving person elsewhere. The command policy changes for one
shape only (N16), and `clear_plan` is where it is judged:
- a **hard clear** (`clear-bgp-peer`, `clear ip bgp <peer>`; `clear bgp ipv6 unicast <peer>`
  for an IPv6 neighbour) only of a session **not Established in two reads in a row**: it
  carried no routes to lose;
- a **soft clear** (`clear-bgp-soft`, `... soft`, a route refresh: RFC 2918, RFC 7313) only of
  an **Established** session; it resets nothing (measured on IOS-XE, 2026-11-07: no prompt,
  Up/Down unchanged, "Connections established 1; dropped 0" before and after);
- **never** `clear ip bgp *` or anything but one address (the peer is intent's, never typed);
- **no clear at all** for a peer in Idle (Admin), an administratively shut neighbour, or a
  configuration mismatch (its last reset naming a bad peer AS): a clear cannot fix those.
Each command's prompt, answer and settle time are a platform measurement in the same record as
the resets' (`privileged_measured.json`, by dialect and address family, `measured_key`), and a
clear with no row is refused as not measured, naming why. `send_clear` reads the session again
and KEEPS it (its last reset reason is the evidence a hard clear destroys, T2-4), refuses with
nothing sent when the session no longer reads as the plan's variant needs, answers the measured
prompt alone, and reads the session until it is Established (a soft clear: still Established,
no connection dropped, a refresh sent) within about 2.5 times the measured settle time.
"""

import hashlib
import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

STEPS = ("refuse", "read", "confirm", "send", "verify", "record")

#: The probe's measured prompts (tests/fixtures/tier2/, 2026-10-08; the same on IOS-XE and IOS).
COUNTERS_PROMPT = 'Clear "show interface" counters on this interface [confirm]'
LOGGING_PROMPT = "Clear logging buffer [confirm]"

#: Each Tier 2 command: its command line, its argument, the read before and after, the prompt it
#: asks (measured), what it affects and what it will not do, and whether its before-state is
#: kept (T2-4).
COMMANDS = {
    "clear-counters": {
        "label": "clear counters", "command": "clear counters {interface}", "arg": "interface",
        "read": "show interfaces {interface}", "prompt": COUNTERS_PROMPT, "keep": True,
        "affects": "{interface}'s counters go to zero: the input and output errors and packet "
                   "counts a diagnosis reads. They are kept in the record first.",
        "not_doing": "no traffic is interrupted and no configuration is changed",
        "rollback": "cleared counters cannot be put back; they count again from zero"},
    "clear-arp": {
        "label": "clear arp-cache", "command": "clear arp-cache interface {interface}",
        "arg": "interface", "read": "show ip arp {interface}", "prompt": None, "keep": False,
        "affects": "{interface}'s ARP entries are relearned; traffic to them waits one ARP "
                   "exchange (measured: every entry back at the first read after)",
        "not_doing": "no configuration is changed, and no other interface's entries are touched",
        "rollback": "cleared entries cannot be put back; the device relearns them"},
    "clear-logging": {
        "label": "clear logging", "command": "clear logging", "arg": None,
        "read": "show logging", "prompt": LOGGING_PROMPT, "keep": True,
        "affects": "the device's log buffer is emptied. Loki keeps what was sent to it (lines at "
                   "or under the trap level); the rest is gone, so the buffer is kept in the "
                   "record first. Its 'messages logged' count is not reset (measured).",
        "not_doing": "no configuration is changed, and no line already sent to Loki is touched",
        "rollback": "a cleared buffer cannot be put back; it fills again"},
    "undebug-all": {
        "label": "undebug all", "command": "undebug all", "arg": None,
        "read": "show debugging", "prompt": None, "keep": False,
        "affects": "every debug that is on is turned off",
        "not_doing": "no configuration is changed",
        "rollback": "a debug turned off is not turned back on; nothing it printed is lost"},
}

#: Tier 2 commands not on this menu: refused, naming why. The BGP clears are `SESSION_CLEARS`,
#: sent by self-healing's session clear (board H, H21), never chosen here.
NOT_MEASURED = {
    "clear-bgp-soft": ("clear ip bgp <peer> soft is not on this menu: a BGP clear is "
                       "self-healing's session clear (one named neighbour from intent, its "
                       "session read twice first), measured per platform; a person's run of it "
                       "from here is not built"),
}

#: `show debugging` with nothing on, as measured (whitespace collapsed, blank lines dropped):
#: IOS prints nothing; IOS-XE prints its conditional-debug and packet-tracing headers.
NOTHING_ON = (
    (),
    ("IOSXE Conditional Debug Configs:", "Conditional Debug Global State: Stop",
     "IOSXE Packet Tracing Configs:", "Packet Infra debugs:", "Ip Address Port",
     "------------------------------------------------------|----------"),
)

#: ARP verify: entries polled every second up to this long. Measured 0 s at the probe's one-second
#: resolution, so about 2.5 times that resolution.
ARP_SETTLE = 3
#: A kept before-state's cap: the reads engine's measured answer cap (reads.CAP_KIB).
KEEP_BYTES = 32 * 1024
#: Counters are cleared when `Last clearing` reads under this (measured: 00:00:02 and 00:00:05).
COUNTERS_FRESH_S = 60
REASON_WORDS = 3


class Refused(ValueError):
    """Nothing was sent; the message names why."""


def _collapse(text: str) -> tuple:
    return tuple(" ".join(ln.split()) for ln in (text or "").splitlines() if ln.strip())


def nothing_on(text: str) -> bool:
    """`show debugging` is EXACTLY a measured nothing-on form (refusing to claim by resemblance)."""
    return _collapse(text) in NOTHING_ON


def interfaces(list_name: str, hostname: str, ip: str) -> dict:
    """``{"names": [...], "management": name, "why": ""}`` from the device's COMMITTED golden: its
    interfaces, and the one whose address is *ip* (the address Mercury reaches it on)."""
    from modules.nsot import repo as _repo
    from modules.nsot.listref import resolve
    ref = resolve(list_name)
    entry = next((e for e in _repo.list_goldens(list_name)
                  if e.get("hostname") == hostname and e.get("rel") and not e.get("legacy")), None)
    if entry is None:
        return {"names": [], "management": "", "why": f"{list_name} holds no golden for {hostname}"}
    got = _repo.committed_golden(ref.repo_dir, entry["rel"])
    if got.get("text") is None:
        return {"names": [], "management": "", "why": got.get("refused") or "no golden committed"}
    names, mgmt, current = [], "", ""
    for line in got["text"].splitlines():
        m = re.match(r"^interface (\S+)\s*$", line)
        if m:
            current = m.group(1)
            names.append(current)
            continue
        if not line.startswith(" "):
            current = ""
            continue
        a = re.match(r"^\s+ip address (\S+) \S+", line)
        if a and current and a.group(1) == ip:
            mgmt = current
    return {"names": names, "management": mgmt, "why": ""}


def plan(list_name: str, hostname: str, key: str, arg: str = "") -> dict:
    """What the command would do, what it will not, and why it would refuse. Reads only Mercury's
    records (the inventory, the committed golden); never the device."""
    from modules.device import load_saved_devices
    from modules.nsot.listref import UnknownList, resolve

    out = {"ok": False, "list_name": list_name, "hostname": hostname, "key": key, "arg": arg,
           "refusals": [], "commands": [{"key": k, "label": v["label"], "arg": v["arg"]}
                                        for k, v in COMMANDS.items()],
           "not_measured": dict(NOT_MEASURED), "interfaces": [], "management": ""}

    def refuse(text):
        out["refusals"].append(text)
        return out

    try:
        row = next((d for d in load_saved_devices(resolve(list_name).csv_path)
                    if d.get("hostname") == hostname), None)
    except UnknownList as exc:
        return refuse(f"no device list named {list_name!r} ({exc})")
    if row is None:
        return refuse(f"{hostname!r} is not in {list_name}'s inventory")
    out["ip"] = row.get("ip", "")
    found = interfaces(list_name, hostname, out["ip"])
    out["interfaces"] = [n for n in found["names"] if n != found["management"]]
    out["management"] = found["management"]
    if key in NOT_MEASURED:
        return refuse(NOT_MEASURED[key] + ". Nothing was sent.")
    spec = COMMANDS.get(key)
    if spec is None:
        return refuse(f"{key!r} is not a Tier 2 command here (they are: "
                      f"{', '.join(v['label'] for v in COMMANDS.values())}). Nothing was sent.")
    if spec["arg"] == "interface":
        if not arg:
            return refuse("choose an interface. Nothing was sent.")
        if found["why"] and not found["names"]:
            return refuse(f"{hostname}'s interfaces cannot be read from its golden: "
                          f"{found['why']}. Nothing was sent.")
        if arg == found["management"]:
            return refuse(f"{arg} carries {out['ip']}, the address Mercury reaches {hostname} "
                          "on; Tier 2 never clears it. Nothing was sent.")
        if arg not in found["names"]:
            return refuse(f"{arg!r} is not an interface of {hostname} in its committed golden "
                          f"({len(found['names'])} are). Nothing was sent.")
    elif arg:
        return refuse(f"{spec['label']} takes no argument; {arg!r} was given. Nothing was sent.")
    fill = {"interface": arg}
    out.update(ok=True, label=spec["label"], command=spec["command"].format(**fill),
               read=spec["read"].format(**fill), prompt=spec["prompt"], keep=spec["keep"],
               affects=spec["affects"].format(**fill), not_doing=spec["not_doing"],
               rollback=spec["rollback"])
    out["hash"] = hashlib.sha256(json.dumps(
        {"list": list_name, "device": hostname, "ip": out["ip"], "command": out["command"]},
        sort_keys=True).encode()).hexdigest()[:16]
    return out


def preview(list_name: str, hostname: str, key: str, arg: str, actor: str) -> dict:
    """The before-state read through the reads engine as a job (a recorded run): ``{"plan",
    "run", "job"}``, or ``{"plan"}`` when the plan refuses (nothing read)."""
    from modules.nsot import reads
    p = plan(list_name, hostname, key, arg)
    if not p["ok"]:
        return {"plan": p}
    got = reads.start(list_name, [hostname], [p["read"]], actor,
                      purpose=f"Tier 2 preview: {p['command']}")
    return {"plan": p, "run": got.get("run", ""), "job": got.get("job", ""),
            "refused": got.get("refused", "")}


# --------------------------------------------------------------------------- verify

def _last_clearing_s(text: str):
    """Seconds since the counters were last cleared; ``inf`` for ``never`` or a time in days and
    weeks (not just now); None when the read holds no such line (nothing decided)."""
    m = re.search(r'Last clearing of "show interface" counters (\S+)', text or "")
    if not m:
        return None
    hms = re.fullmatch(r"(\d+):(\d\d):(\d\d)", m.group(1))
    if hms:
        return int(hms.group(1)) * 3600 + int(hms.group(2)) * 60 + int(hms.group(3))
    return float("inf")


def _arp_entries(text: str) -> int:
    return sum(1 for ln in (text or "").splitlines() if ln.startswith("Internet"))


def _buffer_lines(text: str):
    """The log buffer's lines (after ``Log Buffer (… bytes):``), or None when the read holds no
    buffer header."""
    lines = (text or "").splitlines()
    i = next((n for n, ln in enumerate(lines) if ln.startswith("Log Buffer (")), None)
    if i is None:
        return None
    return [ln for ln in lines[i + 1:] if ln.strip()]


def verify(key: str, before: str, after: str) -> dict:
    """``{"ok": True|False|None, "words"}`` by the measured rule for *key*; None decides nothing
    (a read whose shape was not recognised)."""
    if key == "clear-counters":
        s = _last_clearing_s(after)
        if s is None:
            return {"ok": None, "words": "the after-read names no 'Last clearing' time in "
                                         "hours:minutes:seconds, so whether it cleared is unknown"}
        ok = s < COUNTERS_FRESH_S
        when = "never" if s == float("inf") else f"{s} s ago"
        return {"ok": ok, "words": (f"cleared {when} (Last clearing of \"show interface\" "
                                    "counters)" if ok else
                                    f"Last clearing of the counters reads {when}, not just now")}
    if key == "clear-arp":
        b, a = _arp_entries(before), _arp_entries(after)
        return {"ok": a >= b, "words": f"{a} of {b} ARP entries back"}
    if key == "clear-logging":
        b, a = _buffer_lines(before), _buffer_lines(after)
        if a is None:
            return {"ok": None, "words": "the after-read holds no 'Log Buffer' header"}
        ok = a == [] or (b is not None and len(a) < len(b))
        return {"ok": ok, "words": (f"the buffer holds {len(a)} line(s) after "
                                    f"(was {len(b) if b is not None else 'unknown'})")}
    if key == "undebug-all":
        ok = nothing_on(after)
        return {"ok": ok if ok else None,
                "words": ("no debug is on (show debugging, a measured nothing-on form)" if ok
                          else "show debugging prints lines not measured as nothing-on: read it")}
    return {"ok": None, "words": "no verify rule"}


# --------------------------------------------------------------------------- the record

def _dir(list_name: str) -> str:
    from modules import config
    return os.path.join(config.get_list_data_dir(list_name), "privileged")


def _path(list_name: str, run_id: str) -> str:
    if not re.fullmatch(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}", run_id or ""):
        raise ValueError(f"not a run id: {run_id!r}")
    return os.path.join(_dir(list_name), f"{run_id}.json")


def _write(list_name: str, record: dict) -> None:
    from modules.filestore import write_atomic
    os.makedirs(_dir(list_name), exist_ok=True)
    write_atomic(_path(list_name, record["id"]), json.dumps(record, indent=1, sort_keys=True))


def get(list_name: str, run_id: str):
    try:
        with open(_path(list_name, run_id), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None


def runs(list_name: str, device: str = "", limit: int = 50, data_dir: str = "") -> dict:
    """``{"runs": [newest first], "unreadable": [names]}``; *data_dir* reads without creating."""
    out, bad = [], []
    folder = os.path.join(data_dir, "privileged") if data_dir else _dir(list_name)
    try:
        names = sorted(os.listdir(folder), reverse=True)
    except FileNotFoundError:
        names = []
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                r = json.load(fh)
        except (OSError, ValueError):
            bad.append(name)
            continue
        if device and r.get("device") != device:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return {"runs": out, "unreadable": bad}


def record(list_name: str, rec: dict) -> dict:
    """Write the run's record (the lifecycle's last step); History reads it."""
    _write(list_name, rec)
    return rec


# --------------------------------------------------------------------------- apply

def _last_line(text: str) -> str:
    return next((ln.strip() for ln in reversed((text or "").splitlines()) if ln.strip()), "")


def apply(list_name: str, hostname: str, key: str, arg: str, *, actor: str,
          confirmed_hash: str, reason: str, session=None, run_id: str = "") -> dict:
    """Send the confirmed command, holding the device, as *actor*: the run's record (written).
    Raises `Refused` with nothing sent when the plan refuses, the hash moved, or the reason is
    short."""
    from modules.nsot import device_ops, reads
    from modules.commands import run_device_command
    from modules.device import load_saved_devices
    from modules.nsot.listref import resolve
    from modules.redact import known_secret_values, redact_text

    p = plan(list_name, hostname, key, arg)
    if not p["ok"]:
        raise Refused("; ".join(p["refusals"]))
    if confirmed_hash != p["hash"]:
        raise Refused(f"the plan changed since the preview you confirmed ({confirmed_hash} -> "
                      f"{p['hash']}): the device's address or the command moved. Nothing was "
                      "sent; preview again.")
    if len((reason or "").split()) < REASON_WORDS:
        raise Refused(f"a reason of {REASON_WORDS} words or more is needed (T2-2); "
                      f"{len((reason or '').split())} given. Nothing was sent.")
    values = known_secret_values()
    rec = {"id": run_id or reads.new_id(), "list": list_name, "device": hostname, "key": key,
           "command": p["command"], "actor": actor, "reason": reason.strip(),
           "started_at": time.time(), "finished_at": None, "state": "running", "hash": p["hash"],
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    _write(list_name, rec)
    dev = next(d for d in load_saved_devices(resolve(list_name).csv_path)
               if d.get("hostname") == hostname)
    if session is None:
        from modules.connection import with_temp_connection as session

    def read(conn, cmd):
        return redact_text(run_device_command(conn, cmd) or "", values)

    def send(conn, text):
        return redact_text(conn.send_command_timing(text, strip_prompt=False,
                                                    strip_command=False, read_timeout=30,
                                                    last_read=2.0) or "", values)

    def work(conn):
        before = read(conn, p["read"])
        out = {"before": before[:KEEP_BYTES] if p["keep"] else "",
               "before_cut": p["keep"] and len(before.encode()) > KEEP_BYTES}
        first = send(conn, p["command"])
        out["printed"] = first
        last = _last_line(first)
        if p["prompt"]:
            if last != p["prompt"]:
                out.update(state="refused", why=(f"the device asked {last!r}, not the measured "
                                                 f"prompt {p['prompt']!r}; it was not answered, "
                                                 "and the session was closed"))
                return out
            out["answered"] = p["prompt"]
            out["printed"] += send(conn, "\n")
        elif last.endswith(("]", "?", ":")) and not re.search(r"[#>]\s*$", last):
            out.update(state="refused", why=f"the device asked {last!r}; it was not answered, "
                                            "and the session was closed")
            return out
        if re.search(r"^%", out["printed"], re.M):
            out.update(state="failed", why=next(ln for ln in out["printed"].splitlines()
                                                if ln.startswith("%")))
            return out
        after = read(conn, p["read"])
        waited = 0
        if key == "clear-arp":
            while _arp_entries(after) < _arp_entries(before) and waited < ARP_SETTLE:
                time.sleep(1)
                waited += 1
                after = read(conn, p["read"])
        out["after"] = after[:KEEP_BYTES]
        v = verify(key, before, after)
        out.update(verify=v, state=("done" if v["ok"] else "unverified" if v["ok"] is None
                                    else "failed"))
        if key == "clear-arp":
            out["verify"]["waited_s"] = waited
        if key == "undebug-all":
            out["changed_nothing"] = nothing_on(before)
        return out

    try:
        with device_ops.hold(list_name, hostname, "privileged", actor,
                             detail=p["command"], ip=p["ip"]):
            device_ops.note(f"sending {p['command']}")
            got = session(dev, work)
    except device_ops.DeviceBusy as exc:
        got = {"state": "refused", "why": f"{exc}. Nothing was sent."}
    except Exception as exc:                          # noqa: BLE001 (the device's failure, named)
        from modules.utils import error_text
        got = {"state": "failed", "why": redact_text(error_text(exc), values)[:400]}
    rec.update(got, finished_at=time.time())
    record(list_name, rec)
    log.info("privileged: %s ran %r on %s/%s: %s", actor, p["command"], list_name, hostname,
             rec["state"])
    return rec


#: The announcement a run makes when it ends (`invalidation.ANNOUNCERS`).
ANNOUNCE_KEYS = ("privileged",)
ANNOUNCER = "privileged"


def start(list_name: str, hostname: str, key: str, arg: str, *, actor: str,
          confirmed_hash: str, reason: str) -> dict:
    """Refuse now (``{"refused": why}``, nothing sent) or start the run as a job:
    ``{"job", "run"}``."""
    from modules.nsot import capture_job, reads
    p = plan(list_name, hostname, key, arg)
    why = ("; ".join(p["refusals"]) if not p["ok"] else
           "" if confirmed_hash == p.get("hash") else
           f"the plan changed since the preview you confirmed ({confirmed_hash} -> "
           f"{p.get('hash')}). Nothing was sent; preview again." )
    if not why and len((reason or "").split()) < REASON_WORDS:
        why = (f"a reason of {REASON_WORDS} words or more is needed (T2-2); "
               f"{len((reason or '').split())} given. Nothing was sent.")
    if why:
        return {"refused": why}
    run_id = reads.new_id()
    job = capture_job.start(list_name, f"{p['command']} on {hostname}", actor,
                            lambda job_id: {"run": apply(list_name, hostname, key, arg,
                                                         actor=actor, confirmed_hash=confirmed_hash,
                                                         reason=reason, run_id=run_id)["id"]},
                            kind="privileged command", announce_keys=ANNOUNCE_KEYS,
                            announcer=ANNOUNCER)
    return {"job": job, "run": run_id}


# --------------------------------------------------------------------------- the process resets

#: The OSPF process resets (board H, H5; the module's docstring): each the routing process's
#: header it resets (its process id one token of digits), the command, the neighbour table it
#: reads before and after, and what it affects. IPv4's OSPF and OSPFv3 (both of IOS's forms) are
#: different processes with their own resets.
PROCESS_RESETS = {
    "clear-ospf-process": {
        "label": "reset the OSPF process", "protocol": "OSPF",
        "header": r"router ospf (\S+)", "command": "clear ip ospf {process} process",
        "read": "show ip ospf neighbor"},
    "clear-ipv6-ospf-process": {
        "label": "reset the OSPFv3 process", "protocol": "OSPFv3",
        "header": r"ipv6 router ospf (\S+)", "command": "clear ipv6 ospf {process} process",
        "read": "show ipv6 ospf neighbor"},
    "clear-ospfv3-process": {
        "label": "reset the OSPFv3 process", "protocol": "OSPFv3",
        "header": r"router ospfv3 (\S+)", "command": "clear ospfv3 {process} process",
        "read": "show ospfv3 neighbor"},
}
RESET_AFFECTS = ("every {protocol} adjacency of process {process} on {device} drops and forms "
                 "again, and the routes learned through them are withdrawn until it does")
RESET_NOT_DOING = "the reset changes no configuration, and no other routing process is reset"
RESET_ROLLBACK = ("a reset cannot be undone: the adjacencies it dropped form again by "
                  "themselves, or they do not, and Verify reads which")
#: A routing process Mercury never resets, and why.
NEVER_RESET = {
    r"router bgp \S+": ("a BGP router-id takes effect only once every session of the process "
                        "resets, and Mercury never sends `clear ip bgp *`: a person resets it"),
}
#: Why a reset is sent (N17): ``router_id``, a router-id that takes effect only through it,
#: inside a heal a person approved (R8); ``single_adjacency``, a router with exactly one OSPF
#: adjacency, where the reset drops only that one.
RESET_PURPOSES = ("router_id", "single_adjacency")
RESET_MEASURED_FILE = os.path.join(os.path.dirname(__file__), "privileged_measured.json")
#: A reset's verify waits about this many times its measured settle time (CLAUDE.md, bounds).
SETTLE_FACTOR = 2.5
#: How often the neighbour table is read again while the verify waits.
RESET_POLL_S = 5


def reset_for(section: str) -> dict:
    """The reset a routing process's *section* header needs: ``{"key", "process", "refused"}``.
    A process id is one token of digits; BGP, and anything else, is refused, naming why."""
    text = (section or "").strip()
    for key, spec in PROCESS_RESETS.items():
        m = re.fullmatch(spec["header"], text)
        if m:
            if not m.group(1).isdigit():
                return {"key": key, "process": "", "refused": (
                    f"{text!r} names its process {m.group(1)!r}, and a process id spliced into "
                    "a command is one token of digits")}
            return {"key": key, "process": m.group(1), "refused": ""}
    for pattern, why in NEVER_RESET.items():
        if re.fullmatch(pattern, text):
            return {"key": "", "process": "", "refused": why}
    return {"key": "", "process": "", "refused": (
        f"{text or 'no section'!r} is not a routing process Mercury resets (it resets: "
        "router ospf, ipv6 router ospf and router ospfv3)")}


def reset_measured() -> dict:
    """``{"state": absent|unreadable|ok, "by_dialect", "unmeasured", "error"}``: the resets'
    platform record. Absent and unreadable are different answers, and neither allows
    anything."""
    if not os.path.exists(RESET_MEASURED_FILE):
        return {"state": "absent", "by_dialect": {}, "unmeasured": {}, "error": ""}
    try:
        with open(RESET_MEASURED_FILE, encoding="utf-8") as fh:
            doc = json.load(fh)
        return {"state": "ok", "by_dialect": doc.get("by_dialect") or {},
                "unmeasured": doc.get("unmeasured") or {}, "error": ""}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "by_dialect": {}, "unmeasured": {},
                "error": f"{type(exc).__name__}: {exc}"}


def _measured_row(row) -> str:
    """Why *row* is not a whole measurement, or ``""``."""
    if not isinstance(row, dict):
        return "it is not a record"
    if "prompt" not in row or not (row["prompt"] is None or isinstance(row["prompt"], str)):
        return "it holds no prompt (null when the reset asked nothing)"
    if row["prompt"] and not isinstance(row.get("answer"), str):
        return "it holds a prompt and no answer to it"
    if not isinstance(row.get("settle_s"), (int, float)) or row["settle_s"] <= 0:
        return "it holds no settle time in seconds"
    if not row.get("device") or not row.get("at"):
        return "it names no device or time it was measured on"
    return ""


def neighbours(text: str):
    """The OSPF or OSPFv3 neighbour table's states, one per row, or None when *text* holds no
    table header (a read whose shape was not recognised). A blank read is an empty table."""
    lines = (text or "").splitlines()
    if not any(ln.strip() for ln in lines):
        return []
    i = next((n for n, ln in enumerate(lines) if ln.lstrip().startswith("Neighbor ID")), None)
    if i is None:
        return None
    out = []
    for ln in lines[i + 1:]:
        m = re.match(r"^\s*\S+\s+\d+\s+(\S+)\s", ln)
        if m:
            out.append(m.group(1))
    return out


def adjacencies(text: str):
    """How many OSPF neighbours the table lists, in any state; None when unreadable."""
    got = neighbours(text)
    return None if got is None else len(got)


def formed(text: str):
    """How many adjacencies the table shows formed (FULL, or 2WAY between two DROTHERs);
    None when unreadable."""
    got = neighbours(text)
    return None if got is None else sum(1 for s in got if s.startswith(("FULL", "2WAY")))


def reset_verify(before: str, after: str) -> dict:
    """``{"ok": True|False|None, "words"}``: the adjacencies formed before are formed again,
    and at least one; None decides nothing (an after-read whose shape was not recognised)."""
    b, a = formed(before), formed(after)
    if a is None:
        return {"ok": None, "words": "the read after the reset holds no neighbour table, so "
                                     "whether the adjacencies formed again is unknown"}
    want = max(b or 0, 1)
    said = f"{a} adjacency(ies) formed after the reset (before it: " + (
        f"{b})" if b is not None else "the table was not read)")
    return {"ok": a >= want, "words": said}


def reset_plan(key: str, process: str, *, dialect: str, device: str = "",
               purpose: str = "router_id", before: str = "") -> dict:
    """What the reset would send and why it would refuse (the six steps' ``refuse``): reads
    only the measurement record and *before* (the neighbour table, for N17's one adjacency);
    never the device. ``{"ok", "refused", "key", "process", "command", "read", "prompt",
    "answer", "settle_s", "bound_s", "affects", "not_doing", "rollback", "measured"}``."""
    import math

    out = {"ok": False, "refused": "", "key": key, "process": process, "purpose": purpose,
           "dialect": dialect, "device": device, "command": "", "read": "", "prompt": None,
           "answer": "", "settle_s": None, "bound_s": None, "measured": {},
           "not_doing": RESET_NOT_DOING, "rollback": RESET_ROLLBACK, "affects": "",
           "label": ""}

    def refuse(words):
        out["refused"] = words + ". Nothing was sent"
        return out

    spec = PROCESS_RESETS.get(key)
    if spec is None:
        return refuse(f"{key!r} is not a process reset here (they are: "
                      f"{', '.join(sorted(PROCESS_RESETS))})")
    if purpose not in RESET_PURPOSES:
        return refuse(f"a reset is sent for {' or '.join(RESET_PURPOSES)}, not {purpose!r}")
    if not (process or "").isdigit():
        return refuse(f"the process id {process!r} is not one token of digits")
    fill = {"process": process, "protocol": spec["protocol"], "device": device or "the device"}
    out.update(command=spec["command"].format(**fill), read=spec["read"],
               affects=RESET_AFFECTS.format(**fill), label=spec["label"])
    if purpose == "single_adjacency":
        n = adjacencies(before)
        if n is None:
            return refuse(f"{out['read']} could not be read as a neighbour table, so whether "
                          f"{fill['device']} has exactly one adjacency is unknown (N17)")
        if n != 1:
            return refuse(f"{fill['device']} has {n} {spec['protocol']} adjacencies, and the "
                          "process reset drops every one: it stays Alert unless the router "
                          "has exactly one (N17)")
    rec = reset_measured()
    name = os.path.basename(RESET_MEASURED_FILE)
    if rec["state"] == "absent":
        return refuse(f"the resets' measurement record ({name}) is absent, and an unmeasured "
                      "reset is never sent")
    if rec["state"] == "unreadable":
        return refuse(f"the resets' measurement record ({name}) cannot be read ({rec['error']}),"
                      " and an unmeasured reset is never sent")
    row = (rec["by_dialect"].get(dialect) or {}).get(key)
    if row is None:
        why = (rec["unmeasured"].get(dialect) or {}).get(key) or "no run of it is recorded"
        return refuse(f"`{out['command']}` is not measured on {dialect or 'an unknown platform'}"
                      f" ({why}): what it asks, what answers it and how long the adjacencies "
                      f"take to form again are measured on a real device first ({name})")
    bad = _measured_row(row)
    if bad:
        return refuse(f"the measurement of `{out['command']}` on {dialect} is incomplete: {bad}")
    out.update(ok=True, prompt=row["prompt"], answer=row.get("answer") or "",
               settle_s=row["settle_s"], bound_s=int(math.ceil(row["settle_s"] * SETTLE_FACTOR)),
               measured={"device": row["device"], "at": row["at"]})
    return out


def send_reset(plan: dict, *, read, send, clock=time.time, sleep=time.sleep) -> dict:
    """Send a planned reset on a session the caller holds (the six steps' ``send`` and
    ``verify``): *read(cmd)* and *send(text)* answer masked text. The before-state is read and
    KEPT; the command is sent once; the MEASURED prompt alone is answered with the MEASURED
    answer, and any other question is not answered (the caller closes the session, which
    abandons the command); then the table is read until the verify passes or its bound ends.
    ``{"state": "done"|"not_back"|"unverified"|"refused"|"rejected", "why", "before",
    "printed", "after", "verify", "waited_s"}``: *refused* and *rejected* reset nothing."""
    if not plan.get("ok"):
        return {"state": "refused", "why": plan.get("refused") or "the reset is not planned"}
    before = read(plan["read"])
    out = {"before": before[:KEEP_BYTES], "before_cut": len(before.encode()) > KEEP_BYTES,
           "command": plan["command"], "why": ""}
    first = send(plan["command"])
    out["printed"] = first
    last = _last_line(first)
    if plan.get("prompt"):
        if last != plan["prompt"]:
            out.update(state="refused", why=(f"the device asked {last!r}, not the measured "
                                             f"prompt {plan['prompt']!r}; it was not answered"))
            return out
        out["answered"] = plan["prompt"]
        out["printed"] += send(plan["answer"])
    elif last.endswith(("]", "?", ":")) and not re.search(r"[#>]\s*$", last):
        out.update(state="refused", why=f"the device asked {last!r}, and the measurement "
                                        "records no question; it was not answered")
        return out
    if re.search(r"^%", out["printed"], re.M):
        out.update(state="rejected", why=next(ln for ln in out["printed"].splitlines()
                                              if ln.startswith("%")))
        return out
    started = clock()
    deadline = started + float(plan.get("bound_s") or 0)
    after = read(plan["read"])
    v = reset_verify(before, after)
    while v["ok"] is not True and clock() < deadline:
        sleep(RESET_POLL_S)
        after = read(plan["read"])
        v = reset_verify(before, after)
    out.update(after=after[:KEEP_BYTES], verify=v, waited_s=round(clock() - started, 1),
               state="done" if v["ok"] else "unverified" if v["ok"] is None else "not_back")
    return out


#: A reset's own states as a Tier 2 run's record names them (History's `privileged` source).
RESET_RECORD_STATE = {"done": "done", "unverified": "unverified", "not_back": "failed",
                      "refused": "refused", "rejected": "failed"}


def reset_record(list_name: str, plan: dict, got: dict, *, actor: str, reason: str,
                 hash_: str, decision: str, started: float, run_id: str = "") -> dict:
    """The reset's record (the six steps' ``record``), as every Tier 2 run's: written as the
    person who approved it, with their reason, the before-state kept, what the device printed
    and the verdict; History shows it (`history_sources.privileged`)."""
    from modules.nsot import reads

    rec = {"id": run_id or reads.new_id(), "list": list_name, "device": plan.get("device"),
           "key": plan.get("key"), "command": plan.get("command"), "actor": actor,
           "reason": (reason or "").strip(), "started_at": started, "finished_at": time.time(),
           "hash": hash_, "decision": decision, "purpose": plan.get("purpose"),
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
           "reset_state": got.get("state"),
           "state": RESET_RECORD_STATE.get(got.get("state"), "failed")}
    rec.update({k: got[k] for k in ("why", "before", "before_cut", "printed", "answered",
                                    "after", "verify", "waited_s") if k in got})
    return record(list_name, rec)


# --------------------------------------------------------------------------- the BGP clears

#: The BGP session clears (board H, H21; the module's docstring): each one named neighbour's,
#: its command and read by address family (`clear bgp ipv6 unicast` for an IPv6 neighbour: the
#: family the session is in, never inferred), the session state it needs (the variant), what it
#: affects, what it will not do and why rollback does not apply.
SESSION_CLEARS = {
    "clear-bgp-peer": {
        "label": "hard clear of one BGP neighbour", "variant": "hard",
        "command": {"ipv4": "clear ip bgp {peer}", "ipv6": "clear bgp ipv6 unicast {peer}"},
        "read": {"ipv4": "show ip bgp neighbors {peer}",
                 "ipv6": "show bgp ipv6 unicast neighbors {peer}"},
        "needs": "not Established in two reads in a row",
        "affects": "the BGP session from {device} to {peer} is reset and forms again. It was not "
                   "Established, so it carried no routes to lose",
        "not_doing": "no configuration is changed, and no other BGP neighbour is touched "
                     "(Mercury never sends `clear ip bgp *`)",
        "rollback": "a session that was not Established had nothing to lose, so there is "
                    "nothing to put back; it forms again by itself or it does not, and Verify "
                    "reads which"},
    "clear-bgp-soft": {
        "label": "soft clear of one BGP neighbour", "variant": "soft",
        "command": {"ipv4": "clear ip bgp {peer} soft",
                    "ipv6": "clear bgp ipv6 unicast {peer} soft"},
        "read": {"ipv4": "show ip bgp neighbors {peer}",
                 "ipv6": "show bgp ipv6 unicast neighbors {peer}"},
        "needs": "Established",
        "affects": "{device} and {peer} send each other their routes again (a route refresh, "
                   "RFC 2918 and RFC 7313); the session stays Established",
        "not_doing": "no configuration is changed and the session is not reset (measured: no "
                     "connection dropped)",
        "rollback": "a route refresh resets nothing, so there is nothing to put back"},
}
#: What is never cleared, whatever asks: every neighbour at once, or anything but one address.
NEVER_CLEAR = ("*", "all")
#: A clear's verify reads the session again this often while it waits.
CLEAR_POLL_S = 2
#: The session's own states, as the Tier 2 record names them (History's `privileged` source).
CLEAR_RECORD_STATE = {"done": "done", "unverified": "unverified", "not_back": "failed",
                      "reset": "failed", "refused": "refused", "rejected": "failed"}
#: A last reset naming a remote AS that is not the configured one (RFC 4271's OPEN message
#: error, Bad Peer AS), in the words IOS prints it: a configuration cause no clear fixes.
_BAD_PEER_AS = re.compile(r"bad (?:peer|remote) AS|peer AS mismatch|wrong (?:remote )?AS", re.I)


def family_of(peer: str) -> str:
    """``ipv4`` or ``ipv6`` for one neighbour address, or ``""`` when *peer* is not one."""
    import ipaddress

    try:
        return "ipv6" if ipaddress.ip_address(str(peer or "").strip()).version == 6 else "ipv4"
    except ValueError:
        return ""


def _addr(text):
    """One address, compared as an address (an IPv6 neighbour in any case or form), or None."""
    import ipaddress

    try:
        return ipaddress.ip_address(str(text or "").strip())
    except ValueError:
        return None


def clear_hash(list_name: str, device: str, ip: str, command: str) -> str:
    """What a clear's confirm binds (the policy's decision or a person's approval): the network,
    the device, the address Mercury reaches it on and the command."""
    return hashlib.sha256(json.dumps({"list": list_name, "device": device, "ip": ip,
                                      "command": command}, sort_keys=True).encode()
                          ).hexdigest()[:16]


def measured_key(key: str, family: str) -> str:
    """The clear's row in the platform record: its key, IPv6's with ``-ipv6``."""
    return key + ("-ipv6" if family == "ipv6" else "")


def bgp_session(text: str) -> dict:
    """One neighbour's ``show ip bgp neighbors <peer>`` (or ``show bgp ipv6 unicast neighbors
    <peer>``), as IOS-XE prints it (captured 2026-11-07, tests/fixtures/tier2/'s
    neighbour reads): ``{"read", "peer", "remote_as",
    "state", "established", "admin", "up_for", "connections", "dropped", "last_reset",
    "bad_peer_as", "received", "refresh_sent", "interface"}``. *read* False when the answer
    holds no ``BGP neighbor is`` header: an answer whose shape was not recognised decides
    nothing."""
    text = text or ""
    head = re.search(r"^BGP neighbor is (\S+?),?\s+remote AS (\d+)", text, re.M)
    out = {"read": bool(head), "peer": head.group(1) if head else "",
           "remote_as": head.group(2) if head else "", "state": "", "established": False,
           "admin": False, "up_for": "", "connections": None, "dropped": None,
           "last_reset": "", "bad_peer_as": False, "received": None, "refresh_sent": None,
           "interface": ""}
    if not head:
        return out
    st = re.search(r"BGP state = ([^,\n]+?)\s*(?:,|$)", text, re.M)
    out["state"] = st.group(1).strip() if st else ""
    out["established"] = out["state"] == "Established"
    out["admin"] = ("admin" in out["state"].lower()
                    or bool(re.search(r"Administratively shut down", text)))
    up = re.search(r"BGP state = Established, up for (\S+)", text)
    out["up_for"] = up.group(1) if up else ""
    c = re.search(r"Connections established (\d+); dropped (\d+)", text)
    if c:
        out["connections"], out["dropped"] = int(c.group(1)), int(c.group(2))
    lr = re.search(r"^\s*Last reset (.+?)\s*$", text, re.M)
    out["last_reset"] = lr.group(1) if lr else ""
    out["bad_peer_as"] = bool(_BAD_PEER_AS.search(out["last_reset"]))
    p = re.search(r"Prefixes Current:\s+(\d+)\s+(\d+)", text)
    out["received"] = int(p.group(2)) if p else None
    rr = re.search(r"^\s*Route Refresh:\s+(\d+)\s+(\d+)", text, re.M)
    out["refresh_sent"] = int(rr.group(1)) if rr else None
    i = re.search(r"Interface associated: (\S+)", text)
    out["interface"] = i.group(1) if i else ""
    return out


def _session_words(s: dict) -> str:
    if not s or not s.get("read"):
        return "not read"
    return (s["state"] or "no state") + (f", up for {s['up_for']}" if s.get("up_for") else "")


def clear_plan(key: str, peer: str, *, dialect: str, device: str = "", sessions=(),
               intent_peers=None) -> dict:
    """What the clear would send and why it would refuse (the six steps' ``refuse``), judged on
    the measurement record, intent's neighbours and *sessions* (the reads the decision was made
    on, oldest first, each `bgp_session`'s; a hard clear needs the last two not Established);
    never the device. *intent_peers* (the neighbour addresses intent holds on *device*) None
    means intent was not read, which refuses. ``{"ok", "refused", "key", "variant", "family",
    "peer", "command", "read", "prompt", "answer", "settle_s", "bound_s", "affects",
    "not_doing", "rollback", "measured", "label"}``."""
    import math

    out = {"ok": False, "refused": "", "key": key, "variant": "", "family": "", "peer": peer,
           "dialect": dialect, "device": device, "command": "", "read": "", "prompt": None,
           "answer": "", "settle_s": None, "bound_s": None, "measured": {}, "affects": "",
           "not_doing": "", "rollback": "", "label": ""}

    def refuse(words):
        out["refused"] = words + ". Nothing was sent"
        return out

    spec = SESSION_CLEARS.get(key)
    if spec is None:
        return refuse(f"{key!r} is not a BGP clear here (they are: "
                      f"{', '.join(sorted(SESSION_CLEARS))})")
    out.update(variant=spec["variant"], label=spec["label"], not_doing=spec["not_doing"],
               rollback=spec["rollback"])
    text = str(peer or "").strip()
    if text.lower() in NEVER_CLEAR or "*" in text:
        return refuse(f"{text!r} is every neighbour at once: Mercury never sends "
                      "`clear ip bgp *`, a hard reset of every session (N16)")
    family = family_of(text)
    if not family or " " in text:
        return refuse(f"{text!r} is not one neighbour address, and a neighbour spliced into "
                      "a command is one address token")
    fill = {"peer": text, "device": device or "the device"}
    out.update(family=family, command=spec["command"][family].format(**fill),
               read=spec["read"][family].format(**fill), affects=spec["affects"].format(**fill))
    if intent_peers is None:
        return refuse(f"{fill['device']}'s committed intent could not be read, so whether it "
                      f"holds {text} as a BGP neighbour cannot be told (the peer is intent's, "
                      "never typed)")
    if _addr(text) not in {_addr(p) for p in intent_peers}:
        return refuse(f"{text} is not a BGP neighbour of {fill['device']} in its committed "
                      f"intent ({len(intent_peers)} are): the peer is intent's, never typed")
    reads = [s for s in sessions or () if isinstance(s, dict)]
    last = reads[-1] if reads else {}
    if not last.get("read"):
        return refuse(f"{out['read']} was not read as one neighbour's session, so its state "
                      "is unknown")
    if last.get("admin"):
        return refuse(f"{text} is {last['state'] or 'administratively shut down'}: shut by "
                      "configuration, so no clear would bring it up (N16: no clear at all)")
    if last.get("bad_peer_as"):
        return refuse(f"{text}'s last reset names a configuration mismatch "
                      f"({last['last_reset']}): it comes back down at once, so no clear at all "
                      "(N16)")
    if spec["variant"] == "hard":
        two = reads[-2:]
        if len(two) < 2 or any(not s.get("read") for s in two):
            return refuse(f"a hard clear needs {text}'s session read twice in a row, not "
                          f"Established both times; {len([s for s in two if s.get('read')])} "
                          "such read(s) were made")
        up = [s for s in two if s.get("established")]
        if up:
            return refuse(f"{text}'s session is Established ({_session_words(up[-1])}) in "
                          f"{len(up)} of the last two reads: a hard clear is sent only to a "
                          "session not Established in two reads in a row, and an Established "
                          "one gets a soft clear (N16)")
    elif not last.get("established"):
        return refuse(f"{text}'s session is {_session_words(last)}, not Established: a soft "
                      "clear refreshes an Established session's routes, and resets nothing")
    rec = reset_measured()
    name = os.path.basename(RESET_MEASURED_FILE)
    row_key = measured_key(key, family)
    if rec["state"] != "ok":
        return refuse(f"the platform measurement record ({name}) is {rec['state']}"
                      + (f" ({rec['error']})" if rec.get("error") else "")
                      + ", and an unmeasured clear is never sent")
    row = (rec["by_dialect"].get(dialect) or {}).get(row_key)
    if row is None:
        why = (rec["unmeasured"].get(dialect) or {}).get(row_key) or "no run of it is recorded"
        return refuse(f"`{out['command']}` is not measured on {dialect or 'an unknown platform'}"
                      f" ({why}): what it asks, what answers it and how long the session takes "
                      f"are measured on a real device first ({name}, {row_key})")
    bad = _measured_row(row)
    if bad:
        return refuse(f"the measurement of `{out['command']}` on {dialect} is incomplete: {bad}")
    out.update(ok=True, prompt=row["prompt"], answer=row.get("answer") or "",
               settle_s=row["settle_s"], bound_s=int(math.ceil(row["settle_s"] * SETTLE_FACTOR)),
               measured={"device": row["device"], "at": row["at"]})
    return out


def clear_verify(plan: dict, before: dict, after: dict) -> dict:
    """``{"ok": True|False|None, "words", "reset"}`` by the measured rule for the plan's
    variant, on `bgp_session`'s *before* and *after*: a hard clear, the session Established; a
    soft clear, still Established, no connection dropped and a refresh sent (``reset`` True
    when a connection dropped: the soft clear reset it). None decides nothing (an after-read
    whose shape was not recognised)."""
    if not (after or {}).get("read"):
        return {"ok": None, "reset": False, "words": "the read after the clear holds no "
                                                     "neighbour's session, so its state is "
                                                     "unknown"}
    peer = plan.get("peer") or "the neighbour"
    if plan.get("variant") == "hard":
        ok = bool(after["established"])
        return {"ok": ok, "reset": True,
                "words": f"the session to {peer} is {_session_words(after)}"}
    b, a = (before or {}).get("dropped"), after.get("dropped")
    reset = b is not None and a is not None and a > b
    sent = ((before or {}).get("refresh_sent"), after.get("refresh_sent"))
    refreshed = None not in sent and sent[1] > sent[0]
    words = (f"the session to {peer} is {_session_words(after)}; connections dropped "
             f"{b if b is not None else '?'} then {a if a is not None else '?'}; route refreshes "
             f"sent {sent[0] if sent[0] is not None else '?'} then "
             f"{sent[1] if sent[1] is not None else '?'}; "
             f"{after['received'] if after.get('received') is not None else '?'} route(s) "
             "received")
    if reset or not after["established"]:
        return {"ok": False, "reset": reset, "words": words}
    if b is None or a is None or not refreshed:
        return {"ok": None, "reset": False, "words": words}
    return {"ok": True, "reset": False, "words": words}


def run_clear(list_name: str, dev: dict, plan: dict, *, actor: str, operation: str,
              values: dict, session, prepare=None, on_hold=None, clock=time.time,
              sleep=time.sleep) -> dict:
    """The clear's one held send: hold *dev* (one operation per device, `device_ops`), open its
    session (*session(dev, work)*), let *prepare(read)* refuse before anything is sent (its
    answer a refusal, ``{"state": "refused", "why", "step"}``, or None), then `send_clear` on
    that session, every answer masked by the one redactor. `send_clear`'s answer; a refusal
    naming its step when the hold, *prepare* or the session refused first; ``unverified`` with
    ``printed`` when the session failed after the command was written (never "nothing was
    sent"). *on_hold()* is called once the device is held."""
    from modules.commands import run_device_command
    from modules.nsot import device_ops
    from modules.redact import redact_text
    from modules.utils import error_text

    state = {"sent": False, "got": None}

    def work(conn):
        def read(cmd):
            return redact_text(run_device_command(conn, cmd) or "", values)

        def send(text):
            state["sent"] = True
            return redact_text(conn.send_command_timing(text, strip_prompt=False,
                                                        strip_command=False, read_timeout=30,
                                                        last_read=2.0) or "", values)

        why = prepare(read) if prepare else None
        if why:
            return why
        state["got"] = send_clear(plan, read=read, send=send, clock=clock, sleep=sleep)
        return state["got"]

    host = dev.get("hostname", "")
    try:
        with device_ops.hold(list_name, host, operation, actor, detail=plan.get("command"),
                             ip=dev.get("ip", "")):
            if on_hold:
                on_hold()
            return session(dev, work) or {"state": "refused", "step": "send",
                                          "why": "the session answered nothing"}
    except device_ops.DeviceBusy as exc:
        return {"state": "refused", "step": "hold", "why": str(exc)}
    except Exception as exc:                          # noqa: BLE001 (the device's failure, named)
        why = redact_text(error_text(exc), values)[:400]
        if state["got"]:
            return state["got"]
        if state["sent"]:
            return {"state": "unverified", "printed": "", "why": (
                f"the session failed after the clear was sent ({why}), so whether the session "
                "came back was not read")}
        return {"state": "refused", "step": "send",
                "why": f"{host}'s session failed before anything was sent ({why})"}


def send_clear(plan: dict, *, read, send, clock=time.time, sleep=time.sleep,
               needs=None) -> dict:
    """Send a planned clear on a session the caller holds (the six steps' ``send`` and
    ``verify``): *read(cmd)* and *send(text)* answer masked text. The session is read again and
    KEPT (its last reset reason is evidence a hard clear destroys, T2-4); when it no longer
    reads as the variant needs (*needs*, the caller's check on that read, `bgp_session`'s, a
    refusal's words or ""; by default the variant's own: a hard clear refused on an
    Established session, a soft clear on one not Established), nothing is sent. The command is
    sent once; the MEASURED prompt alone is answered with the MEASURED answer, and any other
    question is not answered; then the session is read until the verify passes or its bound
    ends. ``{"state": "done"|"not_back"|"reset"|"unverified"|"refused"|"rejected", "why",
    "before", "session_before", "printed", "after", "session_after", "verify", "waited_s"}``:
    *refused* and *rejected* clear nothing."""
    if not plan.get("ok"):
        return {"state": "refused", "why": plan.get("refused") or "the clear is not planned"}
    before = read(plan["read"])
    was = bgp_session(before)
    out = {"before": before[:KEEP_BYTES], "before_cut": len(before.encode()) > KEEP_BYTES,
           "command": plan["command"], "why": "", "session_before": was}
    if needs is None:
        def needs(s):
            if not s.get("read"):
                return f"{plan['read']} was not read as one neighbour's session"
            if plan.get("variant") == "hard" and s.get("established"):
                return (f"the session is Established now ({_session_words(s)}): a hard clear "
                        "is never sent to an Established session")
            if plan.get("variant") == "soft" and not s.get("established"):
                return f"the session is {_session_words(s)} now, not Established"
            return ""
    why = needs(was)
    if why:
        out.update(state="refused", why=why)
        return out
    first = send(plan["command"])
    out["printed"] = first
    last = _last_line(first)
    if plan.get("prompt"):
        if last != plan["prompt"]:
            out.update(state="refused", why=(f"the device asked {last!r}, not the measured "
                                             f"prompt {plan['prompt']!r}; it was not answered"))
            return out
        out["answered"] = plan["prompt"]
        out["printed"] += send(plan["answer"])
    elif last.endswith(("]", "?", ":")) and not re.search(r"[#>]\s*$", last):
        out.update(state="refused", why=f"the device asked {last!r}, and the measurement "
                                        "records no question; it was not answered")
        return out
    if re.search(r"^%", out["printed"], re.M):
        out.update(state="rejected", why=next(ln for ln in out["printed"].splitlines()
                                              if ln.startswith("%")))
        return out
    started = clock()
    deadline = started + float(plan.get("bound_s") or 0)
    after = read(plan["read"])
    sess = bgp_session(after)
    v = clear_verify(plan, was, sess)
    while v["ok"] is not True and not (plan.get("variant") == "soft" and v["reset"]) \
            and clock() < deadline:
        sleep(CLEAR_POLL_S)
        after = read(plan["read"])
        sess = bgp_session(after)
        v = clear_verify(plan, was, sess)
    state = ("done" if v["ok"] else "reset" if v["reset"] and plan.get("variant") == "soft"
             else "unverified" if v["ok"] is None else "not_back")
    out.update(after=after[:KEEP_BYTES], session_after=sess, verify=v,
               waited_s=round(clock() - started, 1), state=state)
    return out


def clear_record(list_name: str, plan: dict, got: dict, *, actor: str, reason: str,
                 hash_: str, decision: str, started: float, run_id: str = "") -> dict:
    """The clear's record (the six steps' ``record``), as every Tier 2 run's: written as the
    policy's setter or the approving person, with the reason, the session before kept, what the
    device printed and the verdict; History shows it (`history_sources.privileged`)."""
    from modules.nsot import reads

    rec = {"id": run_id or reads.new_id(), "list": list_name, "device": plan.get("device"),
           "key": plan.get("key"), "command": plan.get("command"), "actor": actor,
           "reason": (reason or "").strip(), "started_at": started, "finished_at": time.time(),
           "hash": hash_, "decision": decision, "peer": plan.get("peer"),
           "variant": plan.get("variant"), "family": plan.get("family"),
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
           "clear_state": got.get("state"),
           "state": CLEAR_RECORD_STATE.get(got.get("state"), "failed")}
    rec.update({k: got[k] for k in ("why", "before", "before_cut", "printed", "answered",
                                    "after", "verify", "waited_s") if k in got})
    return record(list_name, rec)
