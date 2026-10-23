"""Out-of-band ZTP's operations: the console survey and the console kick-start (O6a).

docs/LAB9_PLAN.md section 8 (pieces 4 to 6). A device with a console path in NetBox
(`console_path.read_console_path`) and a console-server port Mercury knows how to reach
(`console_servers`) is surveyed over its console, read-only, and, when the survey found it
factory-blank, kick-started: the profile's DHCP lines typed on its console so it fetches its
bootstrap like any other ZTP device. Library code: the routes, the card and the manual are
O6b's and O8's, and call these.

**Every operation runs the device-operation lifecycle** (the standing rule):

1. ``preview``: `survey_preview` and `kickstart_preview` contact nothing but NetBox (a read)
   and write nothing. Each names the console path, the console-server port's record, the
   transport it will open, the profile and its hash, and the PROGRAM: every line it may type,
   in the state it types it in, and the hash over all of it;
2. ``confirm``: the run is given the hash the person confirmed. It recomputes the preview NOW
   and refuses, naming both hashes, when they differ; a kick-start also refuses anyone but a
   verified person (`VERIFIED`), naming the actor and how it was verified;
3. ``apply``, holding the device (`device_ops.hold`, one operation per device across
   processes, refused by name) AND the console-server port (the transport's own lock): the
   transport is opened and the program run by `console_transport.run_plan`, which writes
   ONLY what the session state machine decides and refuses any byte for a device this thread
   does not hold (C1559);
4. ``verify``: the session reached the program's end prompt with no abort; a kick-start's end
   prompt names the hostname it typed (`verify_kickstart`), no line it typed was refused (the
   session stops at the first refusal, `console_session.refusal`, C1593), the running
   configuration read back shows every line it typed (`console_kickstart.readback_verdict`,
   which also reads the MAC in use), and its copy of the bootstrap is verified
   (`console_kickstart.verify_copy`, C1594);
5. ``record``: one record per run (`record`), masked, in the network's data folder, and the
   device's latest runs in the installation's index (`INDEX`), which Needs attention reads.
   Rollback does not apply: a kick-start saves nothing (no ``write memory``), so a reload
   returns the device to its factory state; the preview says so.

**The program, by the state the console is found in.** The session state machine
(console_session.py) sends a step only in the state it names, so a program is a table:

- the WAKE: one CR when the console is quiet (``idle``);
- a console found signed in (a ``#`` or config prompt answering the wake, the survey's rule,
  console_survey.SIGNED_IN, the operator's decision D3) or asking for a login is NOT
  factory-blank as found: the survey stops there and sends nothing more, and a kick-start
  types nothing;
- a console found at ``Press RETURN``, the setup dialog or the user prompt (``>``: recorded,
  and the blank check decides, D3) is taken to the privileged prompt by the PRELUDE for that
  state (the setup dialog declined, RETURN, ``enable``);
- the survey's READS: the pager off for this session (``terminal length 0``; nothing is saved),
  the profile's MAC read and its blank check, each its own phase so each answer is read alone;
  then the RELEASE (``disable``), leaving the console at the user prompt, so a kick-start that
  finds ``#`` knows someone signed in since;
- the kick-start's RECHECK (the blank check again, at the prompt, holding the device: a device
  configured since its survey is refused with nothing typed) and then the profile's lines
  exactly as `console_survey.render_kickstart` renders them (`build_kickstart`, the one
  builder; a switch's are STATIC from its out-of-band onboarding's plan, C1592), the READ-BACK
  of what they set, and, for the static path, the COPY of the device's bootstrap from the
  responder, which serves it only while this run holds the device (`FETCH_OPERATIONS`).

When the console prints a prompt BEFORE the wake (a device that has just booted), nothing is
woken: the session is begun again from that prompt (`_Console.attach`), so the survey's
attach state is the one the device printed.
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass

from modules.operation_stages import STAGES as _OPERATION_STAGES

log = logging.getLogger(__name__)

KIND_SURVEY = "survey"
KIND_KICKSTART = "kickstart"
#: The operations' names on the device hold (`device_ops.OPERATION_WORDS` words them).
OP_SURVEY = "console survey"
OP_KICKSTART = "console kick-start"
#: The operations whose hold on a device lets the TFTP responder serve that device's bootstrap
#: to its planned static address (`ztp_responder.console_gate`; out-of-band ZTP's static path,
#: the operator 2026-10-23): the run whose copy asks for it. A one-decision run that holds the
#: device under another name joins here.
FETCH_OPERATIONS = (OP_KICKSTART,)
#: The only verification a kick-start accepts: the access assertion's
#: (`identity.actor_verification`), a person's.
VERIFIED = "access"
#: Per network: ``<list data>/console_ztp/<run id>.json``; a retired device's runs move to
#: ``console_ztp/retired/`` (kept, read by no current reader).
FOLDER = "console_ztp"
RETIRED = "retired"
#: The installation's index of each device's latest survey and latest run, keyed
#: ``<network>|<NetBox device id>``: the one file Needs attention reads.
INDEX = "console_ztp.json"
#: What a run announces when it ends (`invalidation.ANNOUNCERS`): what a device runs, the
#: pending onboardings an Add device offer reads (O7), and the run itself, which the console
#: card (templates/v2/_console_ztp.html, O6b) listens for to read its record by id.
ANNOUNCER = "console-ztp"
ANNOUNCE_KEYS = ("device_state", "pending", "console_ztp")
#: Each operation's steps, in order: the manual's How it works section names each
#: (`modules/manual.OPERATIONS`), and the card's running words follow `device_ops.note`.
SURVEY_STEPS = (
    ("preview", "Read the console path from NetBox and the port's record; contact nothing else"),
    ("confirm", "A person confirms the preview's hash; it is recomputed now and refused if it "
                "moved"),
    ("hold", "Hold the device and its console-server port, refused by name if either is held"),
    ("wake", "One carriage return, or the prompt the console printed first"),
    ("reads", "To the privileged prompt, the pager off, the MAC read and the blank check"),
    ("release", "Back to the user prompt, so a later sign-in is seen"),
    ("verify", "Blank, not blank or unknown, with its reasons, and the MAC"),
    ("record", "The record, its masked transcript, and the device's latest run for Needs "
               "attention"),
)
KICKSTART_STEPS = (
    ("preview", "The exact lines, on the survey that found the device blank; contact nothing "
                "but NetBox"),
    ("confirm", "A verified person confirms the preview's hash; recomputed now, refused if it "
                "moved"),
    ("hold", "Hold the device and its console-server port"),
    ("wake", "One carriage return; a console found signed in since its survey is refused"),
    ("recheck", "The blank check again, holding the device: a saved configuration types "
                "nothing"),
    ("type", "The kick-start's lines, each in the state it is typed in; any line the device "
             "refuses stops the run there"),
    ("verify", "It ends at the privileged prompt, naming the hostname typed"),
    ("readback", "The running configuration read back and compared, line by line, with what "
                 "was typed"),
    ("copy", "The device's bootstrap copied from the responder into its running "
             "configuration, the transfer verified"),
    ("record", "The record, the lines sent and the masked transcript"),
)
#: THE stepper's steps for a run (C1579: drawn at the confirm, every step not yet run, and
#: filled as each begins, `device_actions.stepper` with *starts*): the steps above after the
#: preview and the confirm (both done before the job starts), each ``(key, label, waits,
#: names)``, its waits the step's own words above and its names the progress notes
#: (`device_ops.note`) the run makes as the step BEGINS. One table per operation, read by the
#: card (routes/console_ztp_v2.run_steps); tests/test_console_ztp_v2.py holds every name to a
#: note the code makes.
BEFORE_RUN = ("preview", "confirm")
STEP_LABELS = {"preview": "Preview", "confirm": "Confirm", "hold": "Hold", "wake": "Wake",
               "reads": "Read", "release": "Release", "recheck": "Blank check again",
               "type": "Type the lines", "verify": "Verify", "readback": "Read back",
               "copy": "Fetch the bootstrap", "record": "Record"}
STEP_NOTES = {
    KIND_SURVEY: {"hold": ("opening the console",), "wake": ("waking the console",),
                  "reads": ("survey: prelude", "survey: mac", "survey: blank"),
                  "release": ("survey: release",), "verify": ("survey: verify",),
                  "record": ("survey: record",)},
    KIND_KICKSTART: {"hold": ("opening the console",), "wake": ("waking the console",),
                     "recheck": ("kick-start: recheck",), "type": ("kick-start: typing",),
                     "verify": ("kick-start: verify",),
                     "readback": ("kick-start: read-back",), "copy": ("kick-start: copy",),
                     "record": ("kick-start: record",)},
}


def run_stepper_steps(kind: str) -> tuple:
    """*kind*'s run steps for THE stepper: ``((key, label, waits, names), ...)``."""
    steps = SURVEY_STEPS if kind == KIND_SURVEY else KICKSTART_STEPS
    return tuple((key, STEP_LABELS[key], words[0].lower() + words[1:], STEP_NOTES[kind][key])
                 for key, words in steps if key not in BEFORE_RUN)
#: The session lines a platform's console needs that are not the profile's reads or its
#: kick-start: the privileged prompt, the pager off for this session, the setup dialog
#: declined. None is saved, and none is a configuration line. A profile for a platform not here
#: is refused, naming both.
SESSION_LINES = {"cisco_ios": {"enable": "enable", "pager_off": "terminal length 0",
                               "decline_setup": "no", "disable": "disable"}}


@dataclass(frozen=True)
class Timings:
    """The session's intervals and each run's whole budget, in seconds.

    NOT MEASURED against a console: no console-server run had been timed when this was
    written. The settle and quiet intervals are the session's defaults (console_session.py).
    The step bound ends one stalled step (a read or a configuration line, each answered in
    seconds when it is answered at all), and each run's budget ends the whole run, a survey's
    six sends or a kick-start's twenty, whatever its steps do. Explicit stand-ins until a run
    is measured: re-derive them then (about 2.5 times the measured time)."""
    settle_s: float = 0.5
    quiet_s: float = 5.0
    step_timeout_s: float = 120.0
    poll_s: float = 0.2
    survey_bound_s: float = 600.0
    kickstart_bound_s: float = 1200.0
    #: The copy's own step bound (C1594): from its RETURN to the prompt after the bootstrap is
    #: applied. The bootstrap generates the SSH key during the copy, and IOS prints nothing
    #: while it does (its "% Generating ..." line is a message, the profile's): MEASURED 39.5 s
    #: for the key on a vIOS-L2 in a console replay of this generator's own render (C712,
    #: stage D, 2026-10-12; `onboard.BLOCKED_PENDING_MEASUREMENT`'s note), so about 2.5 times
    #: that, 100 s, plus the transfer and the rest of the file applied (unmeasured; the first
    #: copy on a vIOS-L2 is the measurement): 150 s. A silence shorter than this is never a failure.
    copy_timeout_s: float = 150.0


DEFAULT_TIMINGS = Timings()


class Refused(ValueError):
    """Refused before anything was sent; the text names what was compared and both values."""


# ── the lifecycle's declaration, for the routes O6b registers ──────────────────────────────

#: The stages the two confirm routes declare, read from their one home, `operation_stages.STAGES`
#: (keyed there on each route's endpoint, routes/console_ztp_v2.py): the preview route, the
#: field the confirm reads its hash from, and the functions here. `tests/test_console_ztp.py`
#: resolves each.
STAGES = {
    "survey": _OPERATION_STAGES["console_ztp_v2.survey_confirm"],
    "kickstart": _OPERATION_STAGES["console_ztp_v2.kickstart_confirm"],
}


# ── reading what a run needs ──────────────────────────────────────────────────────────────

def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def _bad_id(value) -> bool:
    return not isinstance(value, int) or isinstance(value, bool) or value <= 0


def build_transport(record: dict, port_id: int, owner: str = ""):
    """The transport for console-server port *port_id*'s *record* (`console_servers`' shape),
    built and checked, NOT opened: ConsoleRefused names what is wrong."""
    from modules.nsot import console_transport as T

    driver = (record or {}).get("driver")
    if driver == "command_bridge":
        transport = T.CommandBridge(port_id, host=record.get("host"),
                                    container=record.get("container"),
                                    credential_ref=record.get("credential_ref"),
                                    ssh_port=record.get("ssh_port") or T.SSH_PORT, owner=owner)
    elif driver == "raw_tcp":
        transport = T.RawTcp(port_id, host=record.get("host"), tcp_port=record.get("tcp_port"),
                             jump_host=record.get("jump_host") or None,
                             ssh_port=record.get("ssh_port") or T.SSH_PORT,
                             credential_ref=record.get("credential_ref") or None, owner=owner)
    else:
        raise T.ConsoleRefused(f"console-server port {port_id}'s driver {driver!r} is not one "
                               "of command_bridge, raw_tcp")
    transport._check()                                    # noqa: SLF001 - refused before use
    return transport


def _target(list_name: str, device_id, profile_name: str, *, session=None, base: str = "",
            ) -> dict:
    """What a run on NetBox device *device_id* reaches, read now: ``{"refused_by", "device",
    "path", "port_id", "port", "transport", "profile"}``. Each refusal is keyed (the card
    draws each as a gate) and names what it compared."""
    from modules.nsot import console_path, console_profiles, console_servers, listref
    from modules.nsot import console_transport as T

    out = {"refused_by": {}, "device": "", "path": None, "port_id": None, "port": None,
           "transport": None, "profile": None}

    def refuse(key, text):
        out["refused_by"].setdefault(key, text)

    if not listref.exists(list_name):
        refuse("list", f"no network named {list_name!r}")
    profile = None
    if profile_name is not None:                  # None: the caller refuses for another reason
        try:
            profile = console_profiles.load(profile_name)
        except console_profiles.ProfileError as exc:
            refuse("profile", f"console profile {profile_name!r}: {exc}")
    if profile is not None and profile.platform not in SESSION_LINES:
        refuse("profile", f"profile {profile.name}'s platform {profile.platform!r} has no "
                          f"session lines here ({sorted(SESSION_LINES)})")
        profile = None
    out["profile"] = profile
    if _bad_id(device_id):
        refuse("device", f"a NetBox device id is a positive number, not {device_id!r}")
        return out
    session, base, err = console_path._ready(session, base)    # noqa: SLF001 - the one reader
    if err:
        refuse("netbox", err)
        return out
    from modules.netbox_client import _nb_read_by_id

    state, dev = _nb_read_by_id(session, base, "dcim/devices", device_id)
    if state != "ok":
        refuse("device", f"dcim/devices/{device_id}/ is {state}" + (f": {dev}" if dev else ""))
        return out
    out["device"] = name = str((dev or {}).get("name") or "").strip()
    if not name:
        refuse("device", f"NetBox device {device_id} has no name to hold it by")
        return out
    if "list" not in out["refused_by"]:
        from modules.config import list_data_path
        from modules.nsot import manifest

        _identity, entry = manifest.find_by_name(
            os.path.join(list_data_path(list_name), "config_repo"), name)
        held = (entry or {}).get("netbox_id")
        if held not in (None, "") and str(held) != str(device_id):
            refuse("device", f"{name} in {list_name} is NetBox device {held}, not {device_id}: "
                             "another device holds this name in the network")
    path = console_path.read_console_path(device_id, session=session, base=base)
    if path.get("state") != "path":
        refuse("path", path.get("error") or path.get("why") or "no console path")
        return out
    if len(path["paths"]) != 1:
        refuse("path", f"NetBox device {device_id} has {len(path['paths'])} console paths ("
                       + ", ".join(f"{p['console_port']['name']} to {p['server']['name']} "
                                   f"{p['server_port']['name']}" for p in path["paths"])
                       + "), and a run reaches exactly one")
        return out
    one = path["paths"][0]
    out["path"] = one
    out["port_id"] = port_id = one["server_port"]["id"]
    got = console_servers.get_port(port_id)
    if got["state"] != "read":
        refuse("port", (f"console-server port {port_id} ({one['server']['name']} "
                        f"{one['server_port']['name']}) has no record in Mercury's console-server "
                        "store, so Mercury does not know how to reach it"
                        if got["state"] == "absent" else
                        f"Mercury's console-server store could not be read: {got['error']}"))
        return out
    out["port"] = {k: v for k, v in got["record"].items() if k not in ("by", "at")}
    try:
        out["transport"] = build_transport(out["port"], port_id)
    except T.ConsoleRefused as exc:
        refuse("transport", str(exc))
    return out


def _path_words(path: dict) -> dict:
    return {"console_port": path["console_port"], "cable": path["cable"],
            "server": path["server"], "server_port": path["server_port"]}


def _step(state: str, line: str) -> list:
    return [state, line + "\r"]


def _preludes(lines: dict) -> dict:
    """The sends that take a console from each state it may be found in to the privileged
    prompt: `Press RETURN`, the setup dialog, and the user prompt (`>`, recorded and left to
    the blank check: the operator's decision D3). A privileged or config prompt is signed in
    and has none: nothing more is sent to it."""
    from modules.nsot import console_profiles as P

    enable = _step(P.USER_EXEC, lines["enable"])
    return {P.PRESS_RETURN: [_step(P.PRESS_RETURN, ""), enable],
            P.SETUP_DIALOG: [_step(P.SETUP_DIALOG, lines["decline_setup"]),
                             _step(P.PRESS_RETURN, ""), enable],
            P.USER_EXEC: [enable]}


def survey_program(profile) -> dict:
    """The survey's whole program, by state (the module's note)."""
    from modules.nsot import console_profiles as P
    from modules.nsot import console_session as S

    lines = SESSION_LINES[profile.platform]
    return {"wake": [_step(S.IDLE, "")],
            "prelude": _preludes(lines),
            "reads": [_step(P.PRIV_EXEC, lines["pager_off"]),
                      _step(P.PRIV_EXEC, profile.mac_command),
                      _step(P.PRIV_EXEC, profile.blank_command)],
            "release": [_step(P.PRIV_EXEC, lines["disable"])],
            "ends": P.USER_EXEC,
            "stops": "any other state the wake finds: nothing more is sent"}


def kickstart_program(profile, kick_lines, copy: str = "") -> dict:
    """The kick-start's whole program, by state: the wake, the prelude, the blank check again,
    then *kick_lines* (`console_survey.render_kickstart`'s, exactly), ending at the privileged
    prompt; then the read-back of what they set (`console_kickstart.readback_plan`), and, when
    the onboarding gives one, the *copy* that fetches the bootstrap (C1594)."""
    from modules.nsot import console_kickstart as K
    from modules.nsot import console_profiles as P
    from modules.nsot import console_session as S

    lines = SESSION_LINES[profile.platform]
    back = K.readback_plan(kick_lines)
    out = {"wake": [_step(S.IDLE, "")],
           "prelude": _preludes(lines),
           "recheck": [_step(P.PRIV_EXEC, profile.blank_command)],
           "lines": ([_step(P.PRIV_EXEC, kick_lines[0])]
                     + [_step(P.CONFIG, line) for line in kick_lines[1:]]),
           "readback": [_step(P.PRIV_EXEC, read) for read in back["reads"]],
           "copy": [_step(state, text) for state, text in K.copy_steps(copy)] if copy else [],
           "ends": P.PRIV_EXEC,
           "stops": "a privileged, config or login prompt at the wake (signed in since its "
                    "survey left it at the user prompt), or a saved startup configuration at "
                    "the recheck: nothing of the kick-start is typed; any line the device "
                    "refuses (a % answer that is not a message): nothing more is typed; a "
                    "read-back that differs from what was typed, or any question but the "
                    "copy's destination: the copy is not sent"}
    return out


def build_kickstart(profile, params: dict, onboarding: dict = None) -> dict:
    """THE kick-start's builder, for every caller (this module's preview and run, and a
    one-decision run's): ``{"lines", "copy", "readback", "program"}``, *params* complete (as
    `kickstart_params` fills them). *lines* are `console_survey.render_kickstart`'s exactly;
    *copy* is `console_kickstart.copy_line` for a profile that types the static address (C1592)
    with a read *onboarding* (``state`` ``read``, its ``server`` and ``boot_file``), else "";
    *readback* `console_kickstart.readback_plan`'s; *program* `kickstart_program`'s, by state.
    ValueError naming what is wrong (a parameter off its shape, a line with no read-back, a
    server or boot file that cannot be copied from)."""
    from modules.nsot import console_kickstart as K
    from modules.nsot import console_survey as V

    lines = V.render_kickstart(profile, params)
    target = onboarding or {}
    copy = ""
    if "address" in profile.kickstart_params and target.get("state") == "read":
        copy = K.copy_line(target.get("server"), target.get("boot_file"))
    return {"lines": lines, "copy": copy, "readback": K.readback_plan(lines),
            "program": kickstart_program(profile, lines, copy)}


def _masked_program(program: dict, values=None) -> dict:
    from modules.redact import redact_text

    def mask(steps):
        return [[state, redact_text(text, values)] for state, text in steps]

    out = {}
    for key, value in program.items():
        if isinstance(value, dict):
            out[key] = {k: mask(v) for k, v in value.items()}
        elif isinstance(value, list):
            out[key] = mask(value)
        else:
            out[key] = value
    return out


def _base_preview(target: dict, list_name: str, device_id) -> dict:
    t = target
    profile = t["profile"]
    return {"ok": not t["refused_by"], "list_name": list_name, "device_id": device_id,
            "device": t["device"], "refused_by": dict(t["refused_by"]),
            "refusals": list(t["refused_by"].values()),
            "profile": ({"name": profile.name, "version": profile.version,
                         "sha256": profile.sha256} if profile else None),
            "path": _path_words(t["path"]) if t["path"] else None,
            "port_id": t["port_id"], "port": t["port"],
            "transport": t["transport"].describe() if t["transport"] else ""}


def survey_preview(list_name: str, device_id, *, profile: str, session=None, base: str = "",
                   values=None) -> dict:
    """Everything a survey would do, contacting nothing but NetBox (a read) and writing nothing:
    the device's console path, the console-server port's record, the transport, the profile
    and its hash, the read-only program and the hash over all of it (which the run is bound
    to)."""
    t = _target(list_name, device_id, profile, session=session, base=base)
    out = _base_preview(t, list_name, device_id)
    program = survey_program(t["profile"]) if t["profile"] else None
    out["program"] = _masked_program(program, values) if program else None
    out["not_doing"] = [
        "no configuration line is typed and nothing is saved: the survey's sends are the wake, "
        "the prelude to the privileged prompt, the pager off for this session, two reads, and "
        "the return to the user prompt",
        "a console found signed in, or asking for a login, is recorded as not factory-blank "
        "as found, and nothing more is sent to it",
    ]
    out["hash"] = _digest({"kind": KIND_SURVEY, "list": list_name, "device_id": device_id,
                           "device": out["device"], "profile": out["profile"],
                           "path": out["path"], "port_id": out["port_id"], "port": out["port"],
                           "program": program}) if out["ok"] else ""
    return out


# ── the records ──────────────────────────────────────────────────────────────────────────

def _folder(list_name: str, create: bool = False) -> str:
    from modules import config

    base = config.get_list_data_dir(list_name) if create else config.list_data_path(list_name)
    return os.path.join(base, FOLDER)


def _run_path(list_name: str, run_id: str, create: bool = False) -> str:
    import re

    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}",
                                                       run_id):
        raise ValueError(f"not a run id: {run_id!r}")
    return os.path.join(_folder(list_name, create), f"{run_id}.json")


def index_path() -> str:
    from modules import config
    return os.path.join(config.DATA_DIR, INDEX)


def _index_key(list_name: str, device_id) -> str:
    return f"{list_name}|{device_id}"


def read_index() -> dict:
    """``{"state": "absent" | "read" | "unreadable", "devices", "error"}``: each device's
    latest survey and latest run, as the runs recorded them. Unreadable is never absent."""
    path = index_path()
    if not os.path.exists(path):
        return {"state": "absent", "devices": {}, "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict) or not isinstance(doc.get("devices"), dict):
            raise ValueError("not a console ZTP index")
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "devices": None, "error": f"{type(exc).__name__}: {exc}"}
    return {"state": "read", "devices": doc["devices"], "error": ""}


def problem(entry: dict):
    """What a device's LATEST run (its index *entry*) leaves for a person: ``not_blank`` (a
    survey or a kick-start's recheck found it not factory-blank), ``failed`` (a run that stopped
    before its end, or a survey that could not judge), or None (a survey that found it blank,
    a kick-start that ended verified). Needs attention's rows are these."""
    latest = (entry or {}).get("latest") or {}
    if latest.get("kind") == KIND_SURVEY:
        if latest.get("outcome") not in ("surveyed", "stopped"):
            return "failed"
        if latest.get("blank") is True:
            return None
        return "not_blank" if latest.get("blank") is False else "failed"
    if latest.get("outcome") == "done":
        return None
    return "not_blank" if latest.get("outcome") == "not_blank" else "failed"


def _summary(rec: dict) -> dict:
    keep = ("id", "kind", "list", "device_id", "device", "actor", "outcome", "reason", "at",
            "finished_at", "blank", "found_signed_in", "attach_state", "reasons", "mac",
            "profile", "path", "port_id", "survey_id", "verify")
    return {k: rec.get(k) for k in keep if k in rec}


def _update_index(rec: dict) -> str:
    """The device's entry moved to *rec* (its latest run, and its latest survey when *rec* is
    one), locked and replaced atomically. ``""`` or why it could not be written."""
    from modules import filestore

    path = index_path()
    key = _index_key(rec["list"], rec["device_id"])
    with filestore.PathLock(path):
        try:
            doc = filestore.read_json_for_write(path, empty={"version": 1, "devices": {}})
            if not isinstance(doc, dict) or not isinstance(doc.get("devices"), dict):
                raise filestore.StoreUnreadable(f"{INDEX} is not a console ZTP index")
        except filestore.StoreUnreadable as exc:
            log.error("console ZTP: the index was not updated: %s", exc)
            return str(exc)
        entry = dict(doc["devices"].get(key) or {}, list=rec["list"],
                     device_id=rec["device_id"], device=rec["device"])
        entry["latest"] = _summary(rec)
        if rec["kind"] == KIND_SURVEY:
            entry["survey"] = _summary(rec)
        doc["devices"][key] = entry
        filestore.write_atomic(path, json.dumps(doc, indent=1, sort_keys=True) + "\n")
    return ""


def record(list_name: str, rec: dict) -> dict:
    """Write one run's record (the lifecycle's last step), and the device's index entry once the
    run has ended. History reads the record; Needs attention reads the index."""
    from modules import filestore

    path = _run_path(list_name, rec["id"], create=True)
    from modules.config import secure_dir
    secure_dir(os.path.dirname(path))
    filestore.write_atomic(path, json.dumps(rec, indent=1, sort_keys=True) + "\n")
    if rec.get("outcome") != "running":
        why = _update_index(rec)
        if why:
            rec["index_error"] = why
    return rec


def get_run(list_name: str, run_id: str):
    """One run's record, or None."""
    try:
        with open(_run_path(list_name, run_id), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None


def runs(list_name: str, device_id=None, limit: int = 50) -> dict:
    """``{"runs": [newest first], "unreadable": [names]}``: the network's console runs (a
    retired device's are not among them), creating nothing."""
    out, bad = [], []
    folder = _folder(list_name)
    try:
        names = sorted((n for n in os.listdir(folder) if n.endswith(".json")), reverse=True)
    except FileNotFoundError:
        names = []
    for name in names:
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                r = json.load(fh)
        except (OSError, ValueError):
            bad.append(name)
            continue
        if device_id is not None and r.get("device_id") != device_id:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return {"runs": out, "unreadable": bad}


def _announce() -> None:
    try:
        from modules import invalidation
        invalidation.announce(list(ANNOUNCE_KEYS), ANNOUNCER, True)
    except RuntimeError:
        pass                              # no emitter: a script's process; nobody to tell
    except Exception:                     # noqa: BLE001 - a run never fails on telling
        log.warning("console ZTP: the run's end could not be announced", exc_info=True)


def _new_record(kind: str, preview: dict, actor: str, actor_verified: str, run_id: str) -> dict:
    from modules.nsot import reads

    now = time.time()
    return {"id": run_id or reads.new_id(now), "kind": kind, "list": preview["list_name"],
            "device_id": preview["device_id"], "device": preview["device"], "actor": actor,
            "actor_verified": actor_verified, "hash": preview["hash"],
            "profile": preview["profile"], "path": preview["path"],
            "port_id": preview["port_id"], "transport": preview["transport"],
            "started_at": now, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "finished_at": None, "outcome": "running", "reason": ""}


# ── driving the console ──────────────────────────────────────────────────────────────────

class _Console:
    """One console session over an open transport, phase by phase: the wake (or the prompt the
    console printed first), then each further plan from the prompt the last one ended on. Every
    byte is written by `console_transport.run_plan`, for the held *device*."""

    def __init__(self, transport, profile, timings: Timings, clock, device: tuple, bound_s,
                 values=None):
        self.transport, self.profile, self.timings = transport, profile, timings
        self.clock, self.device, self.values = clock, device, values
        self.deadline = clock() + bound_s
        self.written_before = transport.bytes_written
        self.sessions = []                # every session this console run drove, in order
        self.session = None
        self.seed = None                  # the prompt a new session begins from, unsent
        self.attach_state = None
        self.last = None

    def _new(self, plan):
        from modules.nsot import console_session as S

        t = self.timings
        return S.ConsoleSession(self.profile, plan, start=self.clock(), settle_s=t.settle_s,
                                quiet_s=t.quiet_s, step_timeout_s=t.step_timeout_s,
                                values=self.values)

    def _drive(self, session, plan=None, seed: bytes = b""):
        from modules.nsot import console_transport as T

        if not (self.sessions and self.sessions[-1] is session):
            self.sessions.append(session)
        left = self.deadline - self.clock()
        if left <= 0:
            self.last = T.RunResult(outcome="bound", reason="the run's bound passed between "
                                    "phases", state=session.state,
                                    attach_state=session.attach_state, sent=session.sent(),
                                    bytes_written=0, transcript=session.transcript())
        else:
            self.last = T.run_plan(self.transport, session, self.clock, bound_s=left,
                                   poll_s=self.timings.poll_s, device=self.device, plan=plan,
                                   seed=seed)
        return self.last

    def attach(self, wake):
        """Wake the console with the program's *wake* steps, or take the prompt it printed
        first. The state the console was found in, or None when the wake ended any other way
        (`last` says how)."""
        from modules.nsot import console_session as S
        from modules.nsot import console_survey as V

        first = self._new(S.Plan(steps=tuple(S.Step(state, text.encode("ascii"))
                                             for state, text in wake), final=S.FINAL))
        got = self._drive(first)
        self.attach_state = first.attach_state
        if got.outcome == "done":
            self.session = first
            return self.attach_state
        if got.outcome == "aborted" and got.sent == b"" and \
                first.attach_state in V.NOT_SIGNED_IN:
            # The console printed its prompt before the wake: begin again from that prompt.
            state, line, partial = S.read_state(first.received_since_send(), self.profile, "")
            if state == first.attach_state:
                self.seed = (line + ("" if partial else "\n")).encode("ascii", "replace")
                return self.attach_state
        return None

    def then(self, steps, final, step_timeout_s: float = None):
        """Run *steps* (``[[state, text], ...]``) from where the console is, ending in one of
        *final*, each step bounded by the timings' step bound or *step_timeout_s* (the copy's,
        which waits out key generation). The result (`last`)."""
        from modules.nsot import console_session as S

        plan = S.Plan(steps=tuple(S.Step(state, text.encode("ascii")) for state, text in steps),
                      final=tuple(final))
        if self.seed is not None:
            seed, self.seed = self.seed, None
            self.session = self._new(plan)
            self.session.step_timeout_s = step_timeout_s or self.timings.step_timeout_s
            return self._drive(self.session, seed=seed)
        self.session.step_timeout_s = step_timeout_s or self.timings.step_timeout_s
        return self._drive(self.session, plan=plan)

    def output(self) -> str:
        """What the console printed since the last send: the last phase's answer."""
        return self.session.received_since_send() if self.session else ""

    def sent(self) -> bytes:
        """Every byte the sessions decided to send, in order."""
        return b"".join(s.sent() for s in self.sessions)

    def transcript(self) -> str:
        """What every session received and sent, in order, masked."""
        return "".join(s.transcript() for s in self.sessions)

    def bytes_written(self) -> int:
        """Every byte the transport wrote in this console session, all phases."""
        return self.transport.bytes_written - self.written_before


def _finish(rec: dict, console, **fields) -> dict:
    from modules.redact import redact_text

    rec.update(fields)
    if console is not None:
        rec["sent"] = redact_text(console.sent().decode("ascii", "replace"), console.values)
        rec["bytes_written"] = console.bytes_written()
        rec["transcript"] = console.transcript()
        rec["attach_state"] = console.attach_state
    rec["reason"] = redact_text(rec.get("reason") or "", console.values if console else None)
    rec["finished_at"] = time.time()
    return rec


def _open(preview: dict, actor: str):
    """The transport for the port the confirmed preview read (its record, bound by the hash),
    open with its port held, or ConsoleRefused/OSError."""
    transport = build_transport(preview["port"], preview["port_id"],
                                owner=f"{actor}'s console run on {preview['device']}")
    return transport.open()


def verify_survey(attach_state, mac_text: str, nvram_text: str, profile) -> dict:
    """The survey's verdict from what its phases read (`console_survey.survey`: the state the
    console was found in and the blank check's answer), and the MAC from the MAC read's."""
    from modules.nsot import console_survey as V

    return {"result": V.survey(attach_state, nvram_text, profile),
            "mac": V.base_mac(mac_text, profile)}


def survey_run(list_name: str, device_id, *, profile: str, confirmed_hash: str, actor: str,
               actor_verified: str = "", timings: Timings = DEFAULT_TIMINGS, clock=time.monotonic,
               session=None, base: str = "", values=None, run_id: str = "") -> dict:
    """The survey, holding the device and its console port: the record, written. Read-only:
    it sends the wake, the prelude to the privileged prompt, the pager off, and the profile's
    two reads, and stops at a console found signed in. Raises `Refused` with nothing sent when
    the preview refuses or its hash moved."""
    from modules.nsot import console_transport as T
    from modules.nsot import device_ops
    from modules.nsot import console_profiles as P

    if not str(actor or "").strip():
        raise Refused("a survey names who ran it, and no actor was given. Nothing was sent.")
    p = survey_preview(list_name, device_id, profile=profile, session=session, base=base,
                       values=values)
    if not p["ok"]:
        raise Refused("; ".join(p["refusals"]) + ". Nothing was sent.")
    if confirmed_hash != p["hash"]:
        raise Refused(f"the survey changed since the preview you confirmed ({confirmed_hash} -> "
                      f"{p['hash']}): its console path, port, transport or profile moved. "
                      "Nothing was sent; preview again.")
    prof = P.load(profile)
    program = survey_program(prof)
    rec = _new_record(KIND_SURVEY, p, actor, actor_verified, run_id)
    console = None
    try:
        with device_ops.hold(list_name, p["device"], OP_SURVEY, actor,
                             detail=f"console-server port {p['port_id']}"):
            record(list_name, rec)
            device_ops.note("opening the console")
            try:
                transport = _open(p, actor)
            except (T.ConsoleRefused, OSError) as exc:
                _finish(rec, None, outcome="unreachable", blank=None,
                        reason=f"the console could not be opened: {type(exc).__name__}: {exc}")
            else:
                try:
                    console = _Console(transport, prof, timings, clock,
                                       (list_name, p["device"]), timings.survey_bound_s, values)
                    _survey_phases(console, prof, program, rec)
                finally:
                    transport.close()
            # The final record before the hold ends (C1579): the card reads a running run's
            # steps from the hold and its result from the record, so neither is ever missing.
            record(list_name, rec)
    except device_ops.DeviceBusy as exc:
        raise Refused(f"{exc}. Nothing was sent.") from None
    _announce()
    log.info("console survey: %s/%s by %s: %s (blank %s)", list_name, p["device"], actor,
             rec["outcome"], rec.get("blank"))
    return rec


def _survey_phases(console, profile, program, rec) -> None:
    from modules.nsot import console_profiles as P
    from modules.nsot import console_survey as V
    from modules.nsot import device_ops

    device_ops.note("waking the console")
    state = console.attach(program["wake"])
    if state not in program["prelude"]:
        # Found signed in, or asking for a login, or the wake ended another way: the verdict
        # from the state found (unknown when none), and nothing more is sent.
        verdict = V.survey(console.attach_state, "", profile)
        stopped = console.attach_state in V.SIGNED_IN + V.LOGIN
        _finish(rec, console, outcome="stopped" if stopped else console.last.outcome,
                blank=verdict.blank, found_signed_in=verdict.found_signed_in,
                reasons=list(verdict.reasons), mac=None,
                reason=(f"the console was found at {console.attach_state}: nothing more was "
                        "sent" if stopped else console.last.reason))
        return
    pager, mac, blank = program["reads"]
    answers = {}
    for phase, steps in (("prelude", program["prelude"][state] + [pager]), ("mac", [mac]),
                         ("blank", [blank])):
        device_ops.note(f"survey: {phase}")
        got = console.then(steps, (P.PRIV_EXEC,))
        if got.outcome != "done":
            _finish(rec, console, outcome=got.outcome, blank=None, found_signed_in=False,
                    reasons=[f"the survey stopped in its {phase} phase ({got.reason}), so "
                             "blank is unknown"], mac=None, reason=got.reason)
            return
        answers[phase] = console.output()
    v = verify_survey(console.attach_state, answers["mac"], answers["blank"], profile)
    reasons = list(v["result"].reasons)
    # The console left at the user prompt, so a kick-start's wake that finds `#` knows someone
    # signed in since (D3: `#` is signed in). The verdict above stands whatever this does.
    device_ops.note("survey: release")
    got = console.then(program["release"], (program["ends"],))
    if got.outcome != "done":
        reasons.append(f"the console was not left at the user prompt ({got.reason}): a "
                       "kick-start's wake will find it signed in and refuse until it is")
    device_ops.note("survey: verify")
    _finish(rec, console, outcome="surveyed" if got.outcome == "done" else got.outcome,
            blank=v["result"].blank, found_signed_in=v["result"].found_signed_in,
            reasons=reasons, startup_config_bytes=v["result"].startup_config_bytes,
            mac=v["mac"].value, mac_reason=v["mac"].reason,
            reason="" if got.outcome == "done" else f"release: {got.reason}")
    # Only a run that reached its verdict notes its record as begun: a run that stopped early
    # leaves the step it stopped in running until its record replaces the stepper, so the steps
    # it never ran are never drawn done.
    device_ops.note("survey: record")


# ── the kick-start ───────────────────────────────────────────────────────────────────────

def latest_survey(list_name: str, device_id):
    """``(survey, why)``: the device's latest survey from the index, or None and why."""
    got = read_index()
    if got["state"] == "unreadable":
        return None, f"the console ZTP index could not be read ({got['error']})"
    survey = (got["devices"].get(_index_key(list_name, device_id)) or {}).get("survey")
    if not survey:
        return None, (f"NetBox device {device_id} has no console survey in {list_name}: survey "
                      "its console first")
    return survey, ""


def kickstart_params(profile, params, device: str, onboarding: dict = None) -> dict:
    """*params* with the ones Mercury knows filled in, each only where the profile declares it
    and none was given (an empty value is none given, as a form sends it): ``hostname`` is the
    device's NetBox name (*device*), so a person never types what NetBox holds and the
    kick-start's verify compares the prompt with the name the device is onboarded as; and from
    the device's out-of-band *onboarding* (`console_kickstart.onboarding_target`, C1592) the
    static ``address``, ``mask`` and ``gateway`` (the plan's), the ``vlan`` (its management
    interface's; 1, IOS's default, when the plan names none) and the ``interface`` (the uplink
    NetBox cables to the relay, when it does). A value that was given is kept as given, and
    judged by the renderer; a given address, mask or gateway that is not the plan's is refused
    by the preview, both named."""
    from modules.nsot import console_kickstart as K

    out = {k: v for k, v in dict(params or {}).items() if v not in ("", None)}
    if profile is None:
        return out
    declared = profile.kickstart_params
    target = onboarding if (onboarding or {}).get("state") == "read" else {}
    known = {"hostname": device,
             **{k: target.get(k, "") for k in K.PLAN_PARAMS},
             "vlan": target.get("vlan", ""), "interface": target.get("uplink", "")}
    for name, value in known.items():
        if name in declared and name not in out and value:
            out[name] = value
    if "vlan" in declared and "vlan" not in out:
        out["vlan"] = K.DEFAULT_VLAN
    return out


def _onboarding(list_name: str, device: str, device_id, session, base: str) -> dict:
    """The device's out-of-band onboarding, as `console_kickstart.onboarding_target` reads it
    (NetBox's session the preview's own, for the uplink)."""
    from modules.nsot import console_kickstart as K
    from modules.nsot import console_path

    if not device:
        return K._absent("no device was read")                     # noqa: SLF001
    session, base, _err = console_path._ready(session, base)       # noqa: SLF001
    return K.onboarding_target(list_name, device, device_id=device_id, session=session,
                               base=base)


def kickstart_preview(list_name: str, device_id, params: dict, *, session=None,
                      base: str = "", values=None, onboarding: dict = None) -> dict:
    """The kick-start: the EXACT lines it types (`console_survey.render_kickstart` for the
    profile its survey used, masked as previews are), what it reads back and the copy that
    fetches the bootstrap (`console_kickstart`), the survey it stands on (refused unless that
    survey found the device factory-blank, named by its time), the transport, and the hash over
    the whole program, the profile's hash, the console path, the port and the survey's id.

    *onboarding*: what the device's out-of-band onboarding gives (address, mask, gateway, vlan,
    server, boot file, uplink: `console_kickstart.onboarding_target`'s shape), from the caller's
    own plan (Add device's one-decision run); None reads the device's pending onboarding."""
    from modules.nsot import console_kickstart as K

    survey, why = latest_survey(list_name, device_id)
    profile_name = ((survey or {}).get("profile") or {}).get("name")
    t = _target(list_name, device_id, profile_name, session=session, base=base)
    if survey is None:
        t["refused_by"].setdefault("survey", why)
    out = _base_preview(t, list_name, device_id)
    out["survey"] = survey
    prof = t["profile"]
    if survey is not None:
        when = f"the survey of {survey.get('at')} by {survey.get('actor') or 'someone'}"
        out["survey_words"] = when
        if survey.get("blank") is not True or survey.get("outcome") != "surveyed":
            out["refused_by"].setdefault("survey", (
                f"{when} did not find it factory-blank and end (blank: {survey.get('blank')}, "
                f"ended {survey.get('outcome')}; "
                + "; ".join(survey.get("reasons") or [survey.get("reason") or "no reason"])
                + "): a kick-start types only on a device its survey found blank"))
        sprof = survey.get("profile") or {}
        if prof is not None and sprof.get("sha256") != prof.sha256:
            out["refused_by"].setdefault("survey", (
                f"{when} used profile {sprof.get('name')} {str(sprof.get('sha256'))[:12]}, "
                f"and that profile is {prof.sha256[:12]} now: survey again"))
        spath = survey.get("path") or {}
        if out["path"] is not None and (spath.get("server_port") or {}).get("id") != \
                out["path"]["server_port"]["id"]:
            out["refused_by"].setdefault("survey", (
                f"{when} was over console-server port "
                f"{(spath.get('server_port') or {}).get('id')}, and the device's console path "
                f"is port {out['path']['server_port']['id']} now: survey again"))
    target = onboarding if onboarding is not None else _onboarding(
        list_name, out["device"], device_id, session, base)
    out["onboarding"] = {k: target.get(k, "") for k in ("state", "why", "address", "mask",
                                                         "gateway", "vlan", "server",
                                                         "boot_file", "uplink", "uplink_why")}
    static = prof is not None and "address" in prof.kickstart_params
    if target.get("state") == "refused":
        out["refused_by"].setdefault("onboarding", target.get("why") or "refused")
    elif static and target.get("state") != "read":
        out["refused_by"].setdefault("onboarding", (
            f"profile {prof.name} types the plan's static address (C1592), and "
            f"{target.get('why') or 'no out-of-band onboarding was read'}: create the device "
            "with the out-of-band (console) address source first, so its plan gives the "
            "address, mask, gateway and config server"))
    elif prof is not None and not static and target.get("state") == "read":
        out["refused_by"].setdefault("profile", (
            f"profile {prof.name} types no static address, and {out['device']}'s onboarding "
            "is out-of-band with a static one (C1592): choose a profile that types it"))
    given = {k: v for k, v in dict(params or {}).items() if v not in ("", None)}
    params = kickstart_params(prof, params, out["device"], target)
    out["params"] = params
    for name in K.PLAN_PARAMS:
        if name in given and target.get("state") == "read" and str(given[name]) != target[name]:
            out["refused_by"].setdefault("params", (
                f"parameter {name} {given[name]!r} is not the plan's {target[name]!r}: the plan "
                "is the one source of the static address"))
    lines, program, copy = (), None, ""
    back = {"reads": (), "not_read": ()}
    if prof is not None:
        try:
            built = build_kickstart(prof, params, target)
            lines, program, copy, back = (built["lines"], built["program"], built["copy"],
                                          built["readback"])
        except ValueError as exc:
            out["refused_by"].setdefault("params", str(exc))
    from modules.redact import redact_text

    out["lines"] = [redact_text(line, values) for line in lines]
    out["readback"] = {"reads": list(back["reads"]),
                       "not_read": [list(x) for x in back["not_read"]]}
    out["copy"] = redact_text(copy, values) if copy else ""
    out["program"] = _masked_program(program, values) if program else None
    out["refusals"] = list(out["refused_by"].values())
    out["ok"] = not out["refused_by"]
    out["not_doing"] = [
        "nothing is saved (no write memory): a reload returns the device to its factory "
        "state, which is the way back, since lines typed on a console cannot be taken back",
        "no credential crosses the console: the device's bootstrap, which holds it, is copied "
        "from the responder",
        "a device found configured at the recheck (a saved startup configuration) is refused "
        "with nothing of the kick-start typed",
        "a line the device refuses stops the run: nothing after it is typed, and the copy is "
        "not sent",
    ]
    out["hash"] = _digest({"kind": KIND_KICKSTART, "list": list_name, "device_id": device_id,
                           "device": out["device"], "lines": list(lines),
                           "profile": out["profile"], "path": out["path"],
                           "port_id": out["port_id"], "port": out["port"],
                           "survey": (survey or {}).get("id"),
                           "program": program}) if out["ok"] else ""
    return out


def verified_person(actor: str, actor_verified: str) -> str:
    """Why *actor* (verified as *actor_verified*) may not confirm a kick-start, or ""."""
    from modules import identity

    who = str(actor or "").strip()
    if not who or who == identity.UNVERIFIED or who.startswith(identity.SERVICE_ACTOR_PREFIX) \
            or actor_verified != VERIFIED:
        return (f"a kick-start is confirmed by a verified person: the actor is {who or 'none'!r}"
                f", verified {actor_verified or 'none'!r}, and it needs a person verified "
                f"{VERIFIED!r}")
    return ""


def verify_kickstart(final_prompt: str, params: dict, profile) -> dict:
    """Did the kick-start end where it should: the privileged prompt, naming the hostname it
    typed when the profile types one. ``{"ok", "why"}``."""
    host = (params or {}).get("hostname") if "hostname" in profile.kickstart_params else None
    name = final_prompt[:-1] if final_prompt.endswith("#") else ""
    if not name:
        return {"ok": False, "why": f"it ended at {final_prompt!r}, not a privileged prompt"}
    if host is not None and name != str(host):
        return {"ok": False, "why": f"it ended at {final_prompt!r}, which names {name!r}, not "
                                    f"the hostname typed, {host!r}"}
    return {"ok": True, "why": f"it ended at {final_prompt!r}"
                               + (", naming the hostname typed" if host is not None else "")}


def kickstart_apply(list_name: str, device_id, confirmed_hash: str, actor: str,
                    actor_verified: str, *, params: dict, timings: Timings = DEFAULT_TIMINGS,
                    clock=time.monotonic, session=None, base: str = "", values=None,
                    run_id: str = "", onboarding: dict = None) -> dict:
    """Type the confirmed kick-start, holding the device and its console port: the record,
    written. Raises `Refused` with nothing sent: an actor who is not a verified person, a
    preview that refuses, a hash that moved (both named), or the device held by another
    operation (named). *onboarding* as `kickstart_preview`'s."""
    from modules.nsot import console_transport as T
    from modules.nsot import device_ops

    why = verified_person(actor, actor_verified)
    if why:
        raise Refused(why + ". Nothing was sent.")
    p = kickstart_preview(list_name, device_id, params, session=session, base=base,
                          values=values, onboarding=onboarding)
    if not p["ok"]:
        raise Refused("; ".join(p["refusals"]) + ". Nothing was sent.")
    if confirmed_hash != p["hash"]:
        raise Refused(f"the kick-start changed since the preview you confirmed "
                      f"({confirmed_hash} -> {p['hash']}): its lines, profile, console path, "
                      "port or survey moved. Nothing was sent; preview again.")
    from modules.nsot import console_profiles as P

    prof = P.load(p["profile"]["name"])
    params = p["params"]
    program = build_kickstart(prof, params, p["onboarding"])["program"]
    rec = _new_record(KIND_KICKSTART, p, actor, actor_verified, run_id)
    rec.update(survey_id=p["survey"]["id"], lines=list(p["lines"]), copy=p["copy"],
               readback=p["readback"])
    console = None
    try:
        with device_ops.hold(list_name, p["device"], OP_KICKSTART, actor,
                             detail=f"console-server port {p['port_id']}"):
            record(list_name, rec)
            device_ops.note("opening the console")
            try:
                transport = _open(p, actor)
            except (T.ConsoleRefused, OSError) as exc:
                _finish(rec, None, outcome="unreachable",
                        reason=f"the console could not be opened: {type(exc).__name__}: {exc}")
            else:
                try:
                    console = _Console(transport, prof, timings, clock,
                                       (list_name, p["device"]), timings.kickstart_bound_s,
                                       values)
                    _kickstart_phases(console, prof, program, params, rec)
                finally:
                    transport.close()
            record(list_name, rec)                 # before the hold ends, as the survey's
    except device_ops.DeviceBusy as exc:
        raise Refused(f"{exc}. Nothing was sent.") from None
    _announce()
    log.info("console kick-start: %s/%s by %s: %s", list_name, p["device"], actor,
             rec["outcome"])
    return rec


def _kickstart_phases(console, profile, program, params, rec) -> None:
    from modules.nsot import console_profiles as P
    from modules.nsot import console_session as S
    from modules.nsot import console_survey as V
    from modules.nsot import device_ops

    device_ops.note("waking the console")
    state = console.attach(program["wake"])
    if state is None:
        _finish(rec, console, outcome=console.last.outcome, reason=console.last.reason)
        return
    if state not in program["prelude"]:
        _finish(rec, console, outcome="refused_state",
                reason=f"the console was found at {state}, which a kick-start does not type "
                       f"from ({', '.join(sorted(program['prelude']))}): nothing more was sent")
        return
    device_ops.note("kick-start: recheck")
    got = console.then(program["prelude"][state] + program["recheck"], (P.PRIV_EXEC,))
    if got.outcome != "done":
        _finish(rec, console, outcome=got.outcome, reason=f"recheck: {got.reason}")
        return
    check = V.blank_check(console.output(), profile)
    rec["recheck"] = {"blank": check.blank, "size": check.size, "reason": check.reason}
    if check.blank is not True:
        _finish(rec, console, outcome="not_blank",
                reason=f"the recheck found it not factory-blank ({check.reason}): nothing of "
                       "the kick-start was typed")
        return
    device_ops.note("kick-start: typing")
    got = console.then(program["lines"], (program["ends"],))
    if got.outcome != "done":
        _stopped(rec, console, "typing", got)
        return
    device_ops.note("kick-start: verify")
    _state, prompt, _partial = S.read_state(console.output(), profile,
                                            program["lines"][-1][1][:-1].strip())
    v = verify_kickstart(prompt, params, profile)
    rec["verify"] = v
    if not v["ok"]:
        _finish(rec, console, outcome="unverified", reason=v["why"])
        return
    if not _readback(console, profile, program, rec) or not _copy(console, profile, program, rec):
        return
    _finish(rec, console, outcome="done", reason="")
    device_ops.note("kick-start: record")        # as the survey's: only a run that verified


def _stopped(rec: dict, console, phase: str, got) -> None:
    """A phase that did not end: a line the device refused (C1593: ``line_refused``, with what
    was refused and IOS's words), or however else the session ended."""
    refused = console.session.refused if console.session is not None else None
    if refused:
        from modules.redact import redact_text
        rec["refused"] = {k: redact_text(str(v), console.values) for k, v in refused.items()}
        _finish(rec, console, outcome="line_refused", reason=f"{phase}: {got.reason}")
        return
    _finish(rec, console, outcome=got.outcome, reason=f"{phase}: {got.reason}")


def _readback(console, profile, program, rec) -> bool:
    """The read-back (C1593): each read on its own, then every difference between what was
    typed and what the running configuration shows (`console_kickstart.compare_readback`).
    False, the record finished, when a read did not end or anything differs."""
    from modules.nsot import console_kickstart as K
    from modules.nsot import device_ops

    device_ops.note("kick-start: read-back")
    answers = {}
    for step in program["readback"]:
        got = console.then([step], (program["ends"],))
        if got.outcome != "done":
            _stopped(rec, console, "read-back", got)
            return False
        answers[step[1][:-1]] = console.output()
    lines = [text[:-1] for _state, text in program["lines"]]
    v = K.readback_verdict(K.readback_plan(lines), answers)
    from modules.redact import redact_text
    rec["readback_differs"] = [{"typed": redact_text(d["typed"], console.values),
                                "read": d["read"],
                                "why": redact_text(d["why"], console.values)}
                               for d in v["differs"]]
    rec["mac"], rec["mac_reason"] = v["mac"], v["mac_why"]
    if not v["ok"]:
        _finish(rec, console, outcome="readback_differs",
                reason="read-back: " + "; ".join([d["why"] for d in v["differs"]]
                                                 + ([] if v["mac"] else [v["mac_why"]])))
        return False
    return True


def _copy(console, profile, program, rec) -> bool:
    """The copy (C1594), when the program has one: sent only after a read-back with no
    difference; IOS's destination question answered with RETURN; then `verify_copy`. False,
    the record finished, when it did not fetch the bootstrap."""
    from modules.nsot import console_kickstart as K
    from modules.nsot import device_ops

    if not program["copy"]:
        return True
    device_ops.note("kick-start: copy")
    got = console.then(program["copy"], (program["ends"],),
                       step_timeout_s=console.timings.copy_timeout_s)
    v = K.verify_copy(console.output(), profile)
    from modules.redact import redact_text
    rec["copied"] = {"ok": v["ok"], "bytes": v["bytes"],
                     "refused": redact_text(v["refused"], console.values),
                     "why": redact_text(v["why"], console.values)}
    if got.outcome == "done" and v["ok"]:
        return True
    refused = console.session.refused if console.session is not None else None
    if refused:
        rec["refused"] = {k: redact_text(str(v_), console.values) for k, v_ in refused.items()}
    _finish(rec, console, outcome="copy_failed",
            reason="copy: " + ("" if got.outcome == "done" else f"{got.reason}; ") + v["why"])
    return False


# ── retirement (C1553) ───────────────────────────────────────────────────────────────────

def device_entries(list_name: str, hostname: str, device_id=None) -> tuple:
    """``(keys, error)``: the index keys of the device's entries in *list_name*, by its NetBox
    id or its name; *error* when the index cannot be read (which is not none)."""
    got = read_index()
    if got["state"] == "unreadable":
        return [], f"the console ZTP index could not be read ({got['error']})"
    keys = sorted(k for k, e in got["devices"].items()
                  if e.get("list") == list_name and (
                      (device_id is not None and e.get("device_id") == device_id)
                      or (e.get("device") or "").lower() == hostname.lower()))
    return keys, ""


def device_runs(list_name: str, hostname: str, device_id=None) -> list:
    """The file names of the device's run records (current, not retired)."""
    found = runs(list_name, limit=10 ** 9)["runs"]
    return sorted(f"{r['id']}.json" for r in found
                  if (device_id is not None and r.get("device_id") == device_id)
                  or (r.get("device") or "").lower() == hostname.lower())


def forget_device(list_name: str, hostname: str, keys: list, files: list) -> dict:
    """Retirement's half here: the device's index entries removed and its run records moved to
    ``console_ztp/retired/`` (kept; read by no current reader). ``{"ok", "error", "moved",
    "removed"}``. Idempotent: what is already gone is skipped."""
    from modules import filestore

    out = {"ok": True, "error": "", "moved": [], "removed": []}
    folder = _folder(list_name)
    if files:
        aside = os.path.join(folder, RETIRED)
        os.makedirs(aside, mode=0o700, exist_ok=True)
        for name in files:
            src = os.path.join(folder, name)
            if os.path.exists(src):
                os.replace(src, os.path.join(aside, name))
                out["moved"].append(name)
    if keys:
        path = index_path()
        with filestore.PathLock(path):
            doc = filestore.read_json_for_write(path, empty={"version": 1, "devices": {}})
            for key in keys:
                if doc.get("devices", {}).pop(key, None) is not None:
                    out["removed"].append(key)
            filestore.write_atomic(path, json.dumps(doc, indent=1, sort_keys=True) + "\n")
    log.info("console ZTP: %s in %s retired: %d run(s) moved aside, %d index entr(ies) removed",
             hostname, list_name, len(out["moved"]), len(out["removed"]))
    return out
