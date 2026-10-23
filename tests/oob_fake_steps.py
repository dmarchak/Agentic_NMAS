"""Stand-ins for the console pieces behind modules/nsot/oob_steps.py (Not a test module.)

The one-decision out-of-band onboarding's tests stand Phase A's pieces in at ONE seam, the
adapter (`install`), so the run, its card and its routes are tested alone, end to end on the
fake console: each function below has the shape and the behaviour of the Phase A function its
docstring names (console_survey.render_kickstart, console_session.refused_in,
console_kickstart's readback_plan, readback_verdict, copy_line, copy_steps and verify_copy,
ztp.boot_file and ztp.ZTP_CONSOLE), simplified where a test needs no more: the copy is one
line (no destination question), and the read-back compares each typed line as present in its
section. Phase A's own tests hold the real pieces; at the merge both run.
"""

import ipaddress
import re

#: The address source of an out-of-band onboarding's Create (Phase A's ``ztp.ZTP_CONSOLE``).
ZTP_CONSOLE = "ztp_console"
#: A finite console timeout, as the console kick-start's (console_survey.EXEC_TIMEOUT_MINUTES).
EXEC_TIMEOUT_MINUTES = 15


def install(mp) -> None:
    """Every adapter function stood in by this module's (*mp*: a pytest MonkeyPatch)."""
    from modules.nsot import oob_steps

    for name in ("static_lines", "refused_in", "readback_plan", "readback_verdict",
                 "copy_line", "copy_steps", "verify_copy", "boot_file", "then_with_timeout"):
        mp.setattr(oob_steps, name, globals()[name])
    mp.setattr(oob_steps, "address_source", lambda: ZTP_CONSOLE)
    mp.setattr(oob_steps, "copy_timeout_s", lambda: 150.0)


def then_with_timeout(console, steps, final, timeout_s):
    """STAND-IN for ``console_ztp._Console.then(..., step_timeout_s=)``: this worktree's console
    takes no per-phase bound, so the session's is raised for the phase and put back."""
    session = console.session
    before = session.step_timeout_s
    session.step_timeout_s = max(before, timeout_s)
    try:
        return console.then(steps, final)
    finally:
        session.step_timeout_s = before


def _ipv4(what: str, value: str) -> str:
    text = str(value or "").strip()
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        raise ValueError(f"the {what} {value!r} is not an address") from None
    if ip.version == 6:
        raise ValueError(f"the {what} {text} is IPv6, and the console's static path types an "
                         "IPv4 address, mask and gateway only (C1245)")
    return text


def static_lines(profile, params: dict) -> tuple:
    """STAND-IN for ``console_survey.render_kickstart(profile, params)`` on Phase A's switch
    profile: the lines typed, in order, ``configure terminal`` first and ``end`` last, the
    console line's finite timeout just before ``end``. *params*: ``hostname``, ``interface``
    (the uplink), ``vlan``, ``address``, ``mask``, ``gateway``. ValueError naming what it
    refuses (an IPv6 value among them)."""
    from modules.nsot import console_survey as V

    p = dict(params or {})
    for need in ("hostname", "interface", "vlan", "address", "mask", "gateway"):
        if p.get(need) in (None, ""):
            raise ValueError(f"the static kick-start needs {need}, and none was given")
    address, gateway = _ipv4("planned address", p["address"]), _ipv4("gateway", p["gateway"])
    try:
        ipaddress.ip_network(f"{address}/{p['mask']}", strict=False)
    except ValueError:
        raise ValueError(f"the mask {p['mask']!r} is not an IPv4 netmask") from None
    host = V.check_param("hostname", "hostname", p["hostname"])
    uplink = V.check_param("interface", "interface", p["interface"])
    vlan = V.check_param("vlan", "vlan", p["vlan"])
    lines = ("configure terminal", f"hostname {host}", f"vlan {vlan}", f"interface {uplink}",
             " switchport mode access", f" switchport access vlan {vlan}", " no shutdown",
             f"interface Vlan{vlan}", f" ip address {address} {p['mask']}", " no shutdown",
             f"ip default-gateway {gateway}", V.CONSOLE_LINE,
             f" exec-timeout {EXEC_TIMEOUT_MINUTES} 0", "end")
    return tuple(V.check_line(line) for line in lines)


_REFUSAL = re.compile(r"^\s*%")
_MESSAGE = re.compile(r"^%[A-Z0-9_]+-\d-[A-Z0-9_]+:")


def refused_in(text: str, profile) -> tuple:
    """STAND-IN for ``console_session.refused_in(text, profile)``: ``(words, before)``, the
    first refusal among *text*'s lines (a line whose first character after its indent is
    ``%`` and that is not a message the profile ignores) and the line before it that is not
    blank nor IOS's caret, or ``("", "")``."""
    before = ""
    for raw in (text or "").split("\n"):
        line = raw.strip()
        if _REFUSAL.match(raw) and not _MESSAGE.match(line) \
                and not any(p.search(line) for p in getattr(profile, "ignore", ()) or ()):
            return line, before
        if line and line != "^":
            before = line
    return "", ""


_SVI = re.compile(r"^Vlan([1-9][0-9]{0,3})$")


def readback_plan(lines) -> dict:
    """STAND-IN for ``console_kickstart.readback_plan(lines)``: the reads, in the order the
    sections were typed (each interface's running configuration, the console line's section,
    then the one global read and the MAC read of the one addressed interface), and each typed
    setting each must show. ``vlan N`` is not read back (the VLAN database holds it)."""
    reads, expect, not_read, section, read, globals_ = [], [], [], "", "", []
    addressed = ""
    for raw in lines:
        text = raw.strip()
        if text in ("configure terminal", "end"):
            section = ""
            continue
        if raw[:1] == " ":
            if text.startswith("ip address "):
                addressed = section.split()[1]
            expect.append({"typed": text, "read": read, "section": section})
            continue
        words = text.split()
        if words[0] == "interface":
            section, read = text, f"show running-config interface {words[1]}"
        elif text == "line con 0":
            section, read = text, f"show running-config | section {text}"
        elif words[0] == "vlan":
            not_read.append((text, "a VLAN lives in the VLAN database, not the running "
                                   "configuration"))
            section = "vlan"
            continue
        else:
            globals_.append({"typed": text, "read": "", "section": ""})
            continue
        if read not in reads:
            reads.append(read)
    if globals_:
        read = "show running-config | include " + "|".join(
            "^" + (" ".join(g["typed"].split()[:2]) if g["typed"].startswith("ip ")
                   else g["typed"].split()[0]) for g in globals_)
        reads.append(read)
        expect += [dict(g, read=read) for g in globals_]
    mac_read = f"show interfaces {addressed}" if addressed else ""
    if mac_read:
        reads.append(mac_read)
    return {"reads": tuple(reads), "expect": tuple(expect), "not_read": tuple(not_read),
            "mac_read": mac_read}


_HARDWARE = re.compile(r"address is ([0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4})")


def _section(text: str, header: str) -> list:
    out, inside = [], not header
    for raw in (text or "").split("\n"):
        line = raw.rstrip()
        if header and line.strip() and not line.startswith(" "):
            inside = line.strip().split()[:1] == header.split()[:1] and \
                line.strip().split()[-1].lower() == header.split()[-1].lower()
            continue
        if inside and line.strip():
            out.append(line.strip())
    return out


def readback_verdict(plan: dict, answers: dict) -> dict:
    """STAND-IN for ``console_kickstart.readback_verdict(plan, answers)``: ``{"ok", "differs":
    [{"typed", "read", "found", "why"}], "mac", "mac_why"}``. ``no shutdown`` reads as no
    ``shutdown`` line; ``switchport access vlan 1`` (IOS's default) as that line or none."""
    from modules.nsot.console_survey import normal_mac

    differs = []
    for e in plan["expect"]:
        text = answers.get(e["read"])
        if text is None:
            differs.append({"typed": e["typed"], "read": e["read"], "found": None,
                            "why": f"typed {e['typed']!r}; {e['read']!r} was not read"})
            continue
        scope = _section(text, e["section"]) if e["section"] else \
            [l.strip() for l in text.split("\n") if l.strip()]
        typed = e["typed"]
        if typed == "no shutdown":
            ok = "shutdown" not in scope
        elif typed == "switchport access vlan 1":
            ok = True
        else:
            ok = " ".join(typed.split()) in {" ".join(l.split()) for l in scope}
        if not ok:
            differs.append({"typed": typed, "read": e["read"], "found": tuple(scope),
                            "why": f"typed {typed!r}; {e['read']!r} does not show it"})
    mac, why = None, "no interface was given an address, so no MAC is read"
    if plan.get("mac_read"):
        found = _HARDWARE.findall(answers.get(plan["mac_read"]) or "")
        mac, why = ((normal_mac(found[0]), f"the MAC in use, from {found[0]}")
                    if len(found) == 1 else
                    (None, f"{plan['mac_read']!r} shows {len(found)} 'address is' lines (it "
                           "must show one), so the MAC in use is not known"))
    return {"ok": not differs and (mac is not None or not plan.get("mac_read")),
            "differs": differs, "mac": mac, "mac_why": why}


def copy_line(server: str, boot_file: str) -> str:
    """STAND-IN for ``console_kickstart.copy_line(server, boot_file)``: IPv4 only (C1245)."""
    text = str(server or "").strip()
    if ":" in text:
        raise ValueError(f"the config server {text} is IPv6: out-of-band ZTP serves IPv4 "
                         "only (C1245)")
    try:
        address = ipaddress.IPv4Address(text)
    except ValueError:
        raise ValueError(f"the config server {server!r} is not an IPv4 address") from None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", str(boot_file or "")):
        raise ValueError(f"the boot file {boot_file!r} is not a file name")
    return f"copy tftp://{address}/{boot_file} running-config"


def copy_steps(line: str) -> list:
    """STAND-IN for ``console_kickstart.copy_steps(line)``: here the copy alone at the
    privileged prompt (Phase A's adds RETURN to IOS's destination question, a profile state this
    worktree's profiles do not have yet). Each step's text without its CR."""
    from modules.nsot import console_profiles as P

    return [[P.PRIV_EXEC, line]]


_COPIED = re.compile(r"\[OK - ([0-9]+) bytes\]")


def verify_copy(text: str, profile) -> dict:
    """STAND-IN for ``console_kickstart.verify_copy(text, profile)``: ``{"ok", "bytes",
    "refused", "why"}``; not ok on any refusal (``%Error`` among them), on anything but exactly
    one ``[OK - N bytes]`` line, and on N not above 0."""
    words, before = refused_in(text, profile)
    if words:
        return {"ok": False, "bytes": None, "refused": words,
                "why": f"the copy's answer holds a refusal: {words!r}"
                       + (f" (after {before!r})" if before else "")}
    sizes = [int(m.group(1)) for line in (text or "").split("\n")
             for m in [_COPIED.fullmatch(line.strip())] if m]
    if len(sizes) != 1:
        shown = [l.strip() for l in (text or "").split("\n") if l.strip()][-3:]
        return {"ok": False, "bytes": None, "refused": "",
                "why": f"the copy answered {' / '.join(shown) or 'nothing'!r}: it must print "
                       f"one '[OK - N bytes]' line, and printed {len(sizes)}"}
    if sizes[0] <= 0:
        return {"ok": False, "bytes": sizes[0], "refused": "",
                "why": f"the copy printed '[OK - {sizes[0]} bytes]': it must move more than 0 "
                       "bytes"}
    return {"ok": True, "bytes": sizes[0], "refused": "",
            "why": f"the copy printed '[OK - {sizes[0]} bytes]'"}


def boot_file(hostname: str) -> str:
    """STAND-IN for ``ztp.boot_file(hostname)``: the file AutoInstall and the copy ask for."""
    return f"{hostname}.cfg"
