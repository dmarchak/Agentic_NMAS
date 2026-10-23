"""The console pieces the one-decision out-of-band onboarding runs on (modules/nsot/
oob_onboard.py), behind one small interface: the ADAPTER the run calls, never the pieces' own
modules, so the run reads as its steps and a test stands each piece in at one seam
(tests/oob_fake_steps.py).

**Phase A owns the pieces** (the operator's approved design of 2026-10-23, its changes 1 to 3;
merged on main at b8bceea9). Each function here is one call to Phase A's of the same contract:

- the static program: ``console_survey.render_kickstart(profile, params)`` on the switch
  profile whose kick-start declares ``hostname``, ``interface`` (the uplink), ``vlan``,
  ``address``, ``mask`` and ``gateway``; a switch's way back is ``ip default-gateway`` only,
  never ``ip route`` (the operator's change 2);
- the IOS-refusal detector: ``console_session.refused_in(text, profile) -> (words, before)``;
- the read-back: ``console_kickstart.readback_plan(lines)`` and
  ``console_kickstart.readback_verdict(plan, answers) -> {"ok", "differs", "mac", "mac_why"}``;
- the copy: ``console_kickstart.copy_line(server, boot_file)``,
  ``console_kickstart.copy_steps(line)`` (the copy, then RETURN to IOS's destination question;
  the run appends each step's CR) and ``console_kickstart.verify_copy(text, profile) -> {"ok",
  "bytes", "refused", "why"}``; the copy's own step bound, ``console_ztp.Timings``'s
  ``copy_timeout_s`` (the operator's change 3: an IOSv switch generates its SSH key while it
  applies the copied lines), sent through ``console_ztp._Console.then(..., step_timeout_s=)``;
- the boot file and the address source: ``ztp.boot_file(hostname)``, ``ztp.ZTP_CONSOLE``;
- the responder's narrowed gate: ``ztp_responder.console_gate`` serves a pending
  ``ztp_console`` device's bootstrap to its planned static address only while the device is
  held by an operation in ``console_ztp.FETCH_OPERATIONS``. **That tuple must hold this run's
  hold, `oob_onboard.OP`** (``"console onboard"``), or the copy is refused at the responder.
"""


def static_lines(profile, params: dict) -> tuple:
    """The static kick-start's lines, in order (``configure terminal`` first, ``end`` last, the
    console line's finite timeout before it). ValueError naming what is refused."""
    from modules.nsot import console_survey

    return console_survey.render_kickstart(profile, params)


def refused_in(text: str, profile) -> tuple:
    """``(words, before)``: the first IOS refusal in *text*, and the line it refused."""
    from modules.nsot import console_session

    return console_session.refused_in(text, profile)


def readback_plan(lines) -> dict:
    """What the run reads back after typing *lines*: ``{"reads", "expect", "not_read",
    "mac_read"}``."""
    from modules.nsot import console_kickstart

    return console_kickstart.readback_plan(lines)


def readback_verdict(plan: dict, answers: dict) -> dict:
    """``{"ok", "differs": [{"typed", "read", "found", "why"}], "mac", "mac_why"}``."""
    from modules.nsot import console_kickstart

    return console_kickstart.readback_verdict(plan, answers)


def copy_line(server: str, boot_file: str) -> str:
    """The copy from the responder into the running configuration (IPv4 only, C1245)."""
    from modules.nsot import console_kickstart

    return console_kickstart.copy_line(server, boot_file)


def copy_steps(line: str) -> list:
    """The copy's ``[[state, text], ...]`` steps, each text without its CR."""
    from modules.nsot import console_kickstart

    return console_kickstart.copy_steps(line)


def verify_copy(text: str, profile) -> dict:
    """``{"ok", "bytes", "refused", "why"}`` from the copy's answer."""
    from modules.nsot import console_kickstart

    return console_kickstart.verify_copy(text, profile)


def copy_timeout_s() -> float:
    """The copy's step bound (one home: the console kick-start's timings)."""
    from modules.nsot import console_ztp

    return console_ztp.DEFAULT_TIMINGS.copy_timeout_s


def then_with_timeout(console, steps, final, timeout_s: float):
    """One console phase whose steps are each bounded by *timeout_s* (the copy's)."""
    return console.then(steps, final, step_timeout_s=timeout_s)


def boot_file(hostname: str) -> str:
    """The file the copy asks the responder for."""
    from modules.nsot import ztp

    return ztp.boot_file(hostname)


def address_source() -> str:
    """Create's address source for an out-of-band onboarding (static, no Kea object)."""
    from modules.nsot import ztp

    return ztp.ZTP_CONSOLE


def gate_words(device: str, address: str, filename: str, server: str) -> str:
    """The responder's narrowed gate in words (the review's and the manual's)."""
    return (f"Mercury's TFTP responder at {server} serves {filename}, {device}'s bootstrap, to "
            f"{address} only while this run holds {device}; no Kea subnet, reservation or MAC "
            "rule is written")
