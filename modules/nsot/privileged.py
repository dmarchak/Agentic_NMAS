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

#: Tier 2 commands not yet measured: refused, naming why (the operator decides on r4's run).
NOT_MEASURED = {
    "clear-bgp-soft": ("clear ip bgp <peer> soft is not measured yet: whether a soft refresh "
                       "resets the session on these platforms is r4's probe run, the "
                       "operator's decision"),
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
