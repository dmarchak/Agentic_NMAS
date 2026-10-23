"""Out-of-band ZTP's static kick-start: what it is given, what it reads back, and the copy that
fetches the device's bootstrap (C1592, C1593, C1594; the operator's redesign of 2026-10-23).

The lab's first out-of-band pass (2026-10-23, C1592 to C1594) found three things, each answered
here:

- **vIOS-L2 refuses ``ip address dhcp`` on an SVI** (C1592), so a switch's kick-start types the
  PLAN's static address: `onboarding_target` reads it from the device's pending out-of-band
  onboarding (address source ``ztp_console``): the address and mask its Create committed, the
  default gateway (the relay's own address on the link), the management VLAN (from its
  ``Vlan<N>`` interface), the config server its plan derived and the device's boot file
  (`ztp.boot_file`), and the uplink when NetBox's cabling says which port faces the relay. The
  static path touches no Kea (the operator, 2026-10-23): the responder serves the bootstrap to
  the planned address only while the device's console run holds it
  (`ztp_responder.console_gate`).
- **The MAC is read, not derived** (the operator, 2026-10-23, replacing C1590's rule on this
  path): the read-back reads ``show interfaces <the addressed interface>`` and returns the MAC
  in use (`readback_verdict`), recorded for the inventory and NetBox.
- **A prompt check cannot prove a line took** (C1593): the session stops at any refusal
  (`console_session.refusal`), and the run then READS BACK what it typed (`readback_plan`,
  `compare_readback`): the running configuration's section for each interface it configured,
  the console line, and the hostname and default gateway, compared line by line with IOS's own
  normalisation (below).
- **A running device never fetches its bootstrap by itself** (C1594): AutoInstall runs only at
  boot with an empty configuration. The kick-start ends with ``copy tftp://<server>/<boot file>
  running-config`` (`copy_line`), IOS's one question answered with RETURN, and the transfer
  verified (`verify_copy`).

**The read-back's comparison, precisely.** Each typed line is a SETTING with a key (the words
that name it: ``ip address``, ``switchport mode``, ``hostname``, ...) and the lines IOS may print
for it. In the read's scope (the one section the typed line was typed under, found by its
header, or the whole answer of the global read), the lines carrying the key (a line equal to it,
or beginning with it and a space, compared without their indent) must be EXACTLY one of the
acceptable sets; anything else is a difference naming what was typed and what was read:

- ``ip address A M``: exactly ``ip address A M``, and no ``no ip address``;
- ``no shutdown``: no ``shutdown`` line (IOS prints nothing for an interface that is up);
- ``switchport mode access``: exactly ``switchport mode access``;
- ``switchport access vlan N``: exactly that line; for VLAN 1, IOS's default, that line or none
  (IOS leaves a default out, which is documented and not yet measured on this image);
- ``exec-timeout M S`` under ``line con 0``: exactly that line;
- ``hostname X``, ``ip default-gateway G`` and ``ip route 0.0.0.0 0.0.0.0 G``: exactly that line
  in the global read (for ``ip route``, the only ``ip route`` line);
- the section's header (``interface Vlan1``, ``interface GigabitEthernet0/1``, ``line con 0``)
  must be in its read exactly once (an interface compared by its canonical name, since IOS
  prints the long form of an abbreviation typed);
- ``vlan N`` is NOT read back, and the preview says so: a VLAN lives in the VLAN database, not
  the running configuration, and the access port's ``switchport access vlan`` and the VLAN
  interface's read carry it;
- any other line has no read-back defined and is REFUSED at the preview: the kick-start types
  only what it can read back.

Lines IOS adds on its own (``media-type rj45``, ``negotiation auto``, ``Building
configuration...``) carry no typed key and are not compared.

**The copy's wording is IOS's documented one, NOT YET MEASURED on vIOS-L2** (no copy was ever
captured in this repository): ``Destination filename [running-config]?``, then ``Accessing
tftp://...``, ``Loading <file> from <server> (via <interface>): !``, ``[OK - <N> bytes]`` and
``<N> bytes copied in <t> secs``. Success is exactly one ``[OK - N bytes]`` line with N above 0
and no refusal (``%Error ...`` among them) anywhere in the answer, a line of the copied file
that IOS refused included. Its first run on a vIOS-L2 is the measurement.

Pure but for `onboarding_target`, which reads the device's manifest entry, its committed intent
and (for the uplink) NetBox, and writes nothing.
"""

import ipaddress
import logging
import os
import re
from dataclasses import dataclass, replace

from modules.nsot import console_profiles as P
from modules.nsot import console_session as S

log = logging.getLogger(__name__)

#: The kick-start's parameters the plan gives, never typed by a person: a value given for one
#: must be the plan's (both named when not).
PLAN_PARAMS = ("address", "mask", "gateway")
#: A management VLAN interface, ``Vlan<N>``: the switch's management VLAN is its N.
SVI = re.compile(r"Vlan([1-9][0-9]{0,3})")
#: IOS's default access VLAN, which `show running-config` leaves out.
DEFAULT_VLAN = "1"

#: The lines that enter and leave configuration mode: no setting, nothing to read back.
CONTROL = ("configure terminal", "end")
#: The reads, each one command a session sends at the privileged prompt (each a read:
#: tests/test_console_ztp_static.py holds them to `readonly_commands`).
READ_INTERFACE = "show running-config interface {name}"
READ_SECTION = "show running-config | section {header}"
READ_GLOBAL = "show running-config | include "
#: The MAC in use on the interface the kick-start addressed (the operator, 2026-10-23: recorded
#: for the inventory and NetBox; measured shape: tests/fixtures/console/
#: vios_l2_show_interfaces_vlan10.txt, a lab switch's Vlan10, "Hardware is Ethernet SVI, address is
#: 0c00.6ce9.800a (bia 0c00.6ce9.800a)").
READ_MAC = "show interfaces {name}"
HARDWARE = re.compile(r"\s*Hardware is .*, address is ([0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\."
                       r"[0-9A-Fa-f]{4})\b")             # matched from a line's start
#: The console line, the one ``line`` section a kick-start configures.
CONSOLE_LINE = "line con 0"
#: Typed lines that are not read back, each with why (said by the preview).
NOT_READ_BACK = {
    "vlan": ("a VLAN lives in the VLAN database, not the running configuration: the access "
             "port's switchport access vlan and the VLAN interface's read carry it"),
}
#: The global settings a kick-start may type, each read back by the one global read. ``ip route``
#: is the switch's way back while it routes (a blank vIOS-L2 does, which ignores its default
#: gateway: measured on a blank lab switch, 2026-10-23, C1606); any other static route read is a
#: difference.
GLOBAL_KEYS = ("hostname", "ip default-gateway", "ip route")

#: The copy (C1594): the line typed, IOS's question it answers, and its success line.
COPY_LINE = "copy tftp://{server}/{file} running-config"
BOOT_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
COPIED = re.compile(r"\[OK - ([0-9]+) bytes\]")


@dataclass(frozen=True)
class Expect:
    """One setting a typed line made, and how its read shows it."""
    typed: str             # the line as typed, without its indent
    read: str              # the read-back command whose answer holds it
    section: str           # the header of the section holding it ("": the global read)
    key: str               # the words naming the setting in a read line
    want: tuple            # the acceptable tuples of read lines carrying the key


# ── the read-back (C1593) ─────────────────────────────────────────────────────────────────

def _interface_expects(text: str, read: str, section: str) -> list:
    """The settings one line typed under an interface makes; ValueError for a line with no
    read-back defined."""
    if text == "no shutdown":
        return [Expect(text, read, section, "shutdown", ((),))]
    if text.startswith("switchport mode "):
        return [Expect(text, read, section, "switchport mode", ((text,),))]
    if text.startswith("switchport access vlan "):
        want = ((text,), ()) if text.split()[-1] == DEFAULT_VLAN else ((text,),)
        return [Expect(text, read, section, "switchport access vlan", want)]
    if text.startswith("ip address "):
        return [Expect(text, read, section, "ip address", ((text,),)),
                Expect(text, read, section, "no ip address", ((),))]
    raise ValueError(f"no read-back is defined for {text!r} under {section!r}: the kick-start "
                     "types only what it can read back")


def readback_plan(lines) -> dict:
    """What the kick-start reads back after typing *lines* (`console_survey.render_kickstart`'s,
    exactly), and what each read must show: ``{"reads": (command, ...), "expect": (Expect, ...),
    "not_read": ((line, why), ...)}``. The reads in the order their sections were typed, the
    global read last. ValueError for a line with no read-back defined."""
    reads, expect, not_read, globals_ = [], [], [], []
    section, read = "", ""
    for raw in lines:
        text = raw.strip()
        if text in CONTROL:
            section = ""
            continue
        if raw[:1] == " ":
            if section.startswith("interface "):
                expect += _interface_expects(text, read, section)
            elif section == CONSOLE_LINE and text.startswith("exec-timeout "):
                expect.append(Expect(text, read, section, "exec-timeout", ((text,),)))
            else:
                raise ValueError(f"no read-back is defined for {text!r} under "
                                 f"{section or 'no section'!r}: the kick-start types only what "
                                 "it can read back")
            continue
        words = text.split()
        section = ""
        if words[0] == "interface" and len(words) == 2:
            section, read = text, READ_INTERFACE.format(name=words[1])
        elif text == CONSOLE_LINE:
            section, read = text, READ_SECTION.format(header=text)
        elif words[0] == "vlan" and len(words) == 2:
            not_read.append((text, NOT_READ_BACK["vlan"]))
            section = "vlan"
            continue
        else:
            key = next((k for k in GLOBAL_KEYS if text.startswith(k + " ")), "")
            if not key:
                raise ValueError(f"no read-back is defined for {text!r}: the kick-start types "
                                 "only what it can read back")
            globals_.append(Expect(text, "", "", key, ((text,),)))
            continue
        if read not in reads:
            reads.append(read)
    if globals_:
        keys = list(dict.fromkeys(e.key for e in globals_))
        read = READ_GLOBAL + "|".join("^" + k for k in keys)
        reads.append(read)
        expect += [replace(e, read=read) for e in globals_]
    # The MAC in use, on the ONE interface the lines gave an address (none, or several: no
    # MAC read).
    addressed = sorted({e.section for e in expect if e.key == "ip address"})
    mac_read = (READ_MAC.format(name=addressed[0].split()[1]) if len(addressed) == 1 else "")
    if mac_read:
        reads.append(mac_read)
    return {"reads": tuple(reads), "expect": tuple(expect), "not_read": tuple(not_read),
            "mac_read": mac_read}


def mac_in(text: str) -> tuple:
    """``(mac, why)``: the MAC `show interfaces <name>`'s answer *text* names on its ONE
    ``Hardware is ..., address is <mac>`` line, as lower-case colon pairs
    (`console_survey.normal_mac`), or ``(None, why)``."""
    from modules.nsot.console_survey import normal_mac

    found = [m.group(1) for line in text.split("\n") for m in [HARDWARE.match(line)] if m]
    if len(found) != 1:
        return None, (f"the interface's read shows {len(found)} 'Hardware is ..., address is' "
                      "lines (it must show one), so the MAC in use is not known")
    return normal_mac(found[0]), f"the MAC in use, from {found[0]}"


def readback_verdict(plan: dict, answers: dict) -> dict:
    """The read-back's verdict: ``{"ok", "differs", "mac", "mac_why"}``: every difference
    (`compare_readback`) and the MAC in use on the addressed interface (`mac_in`, when the plan
    reads one). Not ok when anything differs, or when a MAC read the plan makes shows none."""
    differs = compare_readback(plan, answers)
    mac, why = None, "no interface was given an address, so no MAC is read"
    if plan.get("mac_read"):
        text = answers.get(plan["mac_read"])
        mac, why = (None, f"{plan['mac_read']!r} was not read") if text is None \
            else mac_in(text)
    return {"ok": not differs and (mac is not None or not plan.get("mac_read")),
            "differs": differs, "mac": mac, "mac_why": why}


def answer_lines(command: str, text: str) -> list:
    """A read's answer as lines, without the prompt it ended on (the last line) and the echo of
    *command* (the first line that is not blank, when it is the command), each without its
    trailing white space."""
    lines = [line.rstrip() for line in text.split("\n")[:-1]]
    for i, line in enumerate(lines):
        if line.strip():
            if line.strip() == command:
                del lines[i]
            break
    return lines


def _same_header(line: str, header: str) -> bool:
    """Whether *line*, unindented, is the section *header* (an interface by its canonical
    name: IOS prints the long form of an abbreviation typed)."""
    if line[:1] == " ":
        return False
    got, want = line.split(), header.split()
    if len(got) != len(want) or got[:1] != want[:1]:
        return False
    if want[0] == "interface":
        from modules.nsot.ifnames import canonical
        return canonical(got[1]) == canonical(want[1])
    return got == want


def section_body(lines: list, header: str) -> tuple:
    """``(body, count)``: the indented lines under the ONE section *header* heads in *lines*,
    each without its indent, and how many times the header was found (*body* None unless
    exactly once)."""
    starts = [i for i, line in enumerate(lines) if _same_header(line, header)]
    if len(starts) != 1:
        return None, len(starts)
    body = []
    for line in lines[starts[0] + 1:]:
        if line[:1] != " ":
            break
        body.append(line.strip())
    return body, 1


def _words(lines) -> str:
    return ", ".join(repr(x) for x in lines) if lines else "nothing for it"


def compare_readback(plan: dict, answers: dict) -> list:
    """Every difference between what was typed and what the reads show (empty: none):
    ``[{"typed", "read", "found", "why"}]``, *answers* each read's text as the session received
    it (its echo, its answer, the prompt it ended on). *found* is the tuple of read lines that
    carry the setting, or None when its section or read is missing."""
    out = []
    for e in plan["expect"]:
        text = answers.get(e.read)
        if text is None:
            out.append({"typed": e.typed, "read": e.read, "found": None,
                        "why": f"typed {e.typed!r}; {e.read!r} was not read"})
            continue
        lines = answer_lines(e.read, text)
        if e.section:
            scope, count = section_body(lines, e.section)
            if scope is None:
                out.append({"typed": e.typed, "read": e.read, "found": None,
                            "why": f"typed {e.typed!r}; {e.read!r} shows {e.section!r} "
                                   f"{count} times (it must show it once)"})
                continue
        else:
            scope = lines                  # the include's lines: unindented, right-stripped
        found = tuple(line for line in scope if line == e.key or line.startswith(e.key + " "))
        if found not in e.want:
            out.append({"typed": e.typed, "read": e.read, "found": found,
                        "why": f"typed {e.typed!r}; {e.read!r} shows {_words(found)} (it must "
                               "show " + " or ".join(_words(w) for w in e.want) + ")"})
    return out


# ── the copy (C1594) ──────────────────────────────────────────────────────────────────────

def copy_line(server: str, boot_file: str) -> str:
    """The copy that fetches the device's bootstrap from the responder at *server* (the plan's
    config server) by the device's boot file (`ztp.boot_file`); ValueError naming what is
    wrong. IPv4 only (C1245): an IPv6 server is refused by name."""
    text = str(server or "").strip()
    if ":" in text:
        raise ValueError(f"the config server {text} is IPv6: out-of-band ZTP reserves and serves "
                         "IPv4 (DHCPv4) addresses only (C1245)")
    try:
        address = ipaddress.IPv4Address(text)
    except ValueError:
        raise ValueError(f"the config server {server!r} is not an IPv4 address") from None
    name = str(boot_file or "")
    if not BOOT_FILE.fullmatch(name):
        raise ValueError(f"the boot file {boot_file!r} is not a file name (it must match "
                         f"{BOOT_FILE.pattern})")
    return COPY_LINE.format(server=address, file=name)


def copy_steps(line: str) -> list:
    """The copy's steps, by state: the copy at the privileged prompt, then RETURN to IOS's one
    question (`console_profiles.COPY_DESTINATION`); any other question is a prompt no pattern
    names, which stops the session."""
    return [[P.PRIV_EXEC, line], [P.COPY_DESTINATION, ""]]


def verify_copy(text: str, profile) -> dict:
    """Did the copy fetch the bootstrap: ``{"ok", "bytes", "refused", "why"}`` from its answer
    *text* (everything after the RETURN). Not ok on any refusal in it (``%Error ...``, or a line
    of the copied file IOS refused, `console_session.refusal`), on anything but exactly one
    ``[OK - N bytes]`` line, and on N not above 0."""
    words, before = S.refused_in(text, profile)
    if words:
        return {"ok": False, "bytes": None, "refused": words,
                "why": f"the copy's answer holds a refusal: {words!r}"
                       + (f" (after {before!r})" if before else "")}
    sizes = [int(m.group(1)) for line in text.split("\n")
             for m in [COPIED.fullmatch(line.strip())] if m]
    if len(sizes) != 1:
        shown = [line.strip() for line in text.split("\n") if line.strip()][-3:]
        return {"ok": False, "bytes": None, "refused": "",
                "why": f"the copy answered {' / '.join(shown) or 'nothing'!r}: it must print "
                       f"one '[OK - N bytes]' line, and printed {len(sizes)}"}
    if sizes[0] <= 0:
        return {"ok": False, "bytes": sizes[0], "refused": "",
                "why": f"the copy printed '[OK - {sizes[0]} bytes]': it must move more than 0 "
                       "bytes"}
    return {"ok": True, "bytes": sizes[0], "refused": "",
            "why": f"the copy printed '[OK - {sizes[0]} bytes]'"}


# ── what the plan gives (C1592) ───────────────────────────────────────────────────────────

def _absent(why: str) -> dict:
    return {"state": "absent", "why": why, "address": "", "mask": "", "gateway": "", "vlan": "",
            "server": "", "boot_file": "", "uplink": "", "uplink_why": ""}


def onboarding_target(list_name: str, hostname: str, *, device_id=None, session=None,
                      base: str = "") -> dict:
    """What *hostname*'s pending out-of-band onboarding in *list_name* gives its kick-start:
    ``{"state": "read" | "absent" | "refused", "why", "address", "mask", "gateway", "vlan",
    "server", "boot_file", "uplink", "uplink_why"}``. Read from the manifest entry Create wrote
    (pending, address source ``ztp_console``) and the committed bootstrap intent (address, mask,
    gateway, interface and server: the plan's, bound by its hash). *absent*: no such onboarding
    (a DHCP or ZTP device's kick-start types its profile's DHCP lines and copies nothing);
    *refused*: one whose intent cannot give what the kick-start needs, named. Writes nothing."""
    from modules.config import list_data_path
    from modules.nsot import hostvars, manifest, ztp

    repo = os.path.join(list_data_path(list_name), "config_repo")
    try:
        _identity, entry = manifest.find_by_name(repo, hostname)
    except Exception as exc:                          # noqa: BLE001 - said, never raised
        return dict(_absent(""), state="refused",
                    why=f"{list_name}'s manifest could not be read: {exc}")
    source = (entry or {}).get("address_source") or ""
    if not entry or source != ztp.ZTP_CONSOLE:
        return _absent(f"{hostname} has no out-of-band onboarding in {list_name} (its address "
                       f"source is {source or 'none'!r}, not {ztp.ZTP_CONSOLE!r})")
    if not entry.get("onboarded_at") or entry.get("verified_at"):
        return _absent(f"{hostname}'s out-of-band onboarding in {list_name} is not pending")
    try:
        boot = (hostvars.read_committed(repo, hostname) or {}).get("bootstrap") or {}
    except Exception as exc:                          # noqa: BLE001
        return dict(_absent(""), state="refused",
                    why=f"{hostname}'s committed intent could not be read: {exc}")
    out = _absent("")
    out.update(state="read", address=str(boot.get("address") or ""),
               mask=str(boot.get("mask") or ""), gateway=str(boot.get("gateway") or ""),
               server=str(boot.get("server") or ""), boot_file=ztp.boot_file(hostname))
    missing = [k for k in ("address", "mask", "gateway", "server") if not out[k]]
    if missing or boot.get("source") != ztp.ZTP_CONSOLE:
        return dict(out, state="refused",
                    why=f"{hostname}'s committed bootstrap intent (source "
                        f"{boot.get('source')!r}) lacks {missing or 'nothing'}: Create writes "
                        "the plan's static address, mask, gateway and config server there; "
                        "abandon and create it again")
    svi = SVI.fullmatch(str(boot.get("interface") or ""))
    out["vlan"] = svi.group(1) if svi else ""
    out["uplink"], out["uplink_why"] = _uplink(out["address"], device_id, session, base)
    return out


def _uplink(address: str, device_id, session, base: str) -> tuple:
    """``(port, why)``: the device's one interface NetBox cables to the relay's device (the
    relay read from committed intent, `ztp_relayed.link_for_address`), or ``("", why not)``.
    LLDP is not read: the device is blank and unreachable until the kick-start ends."""
    if session is None or not isinstance(device_id, int) or isinstance(device_id, bool):
        return "", "NetBox was not read for the uplink"
    from modules.nsot import console_path, ztp_relayed

    try:
        relay = ztp_relayed.link_for_address(address, ztp_relayed.intent_everywhere())["relay"]
    except ztp_relayed.Refused as exc:
        return "", f"the relay is not known from committed intent: {exc}"
    rows, error = console_path._list(session, base, "dcim/interfaces",  # noqa: SLF001
                                     device_id=device_id)
    if error:
        return "", error
    hits = sorted({str(r.get("name") or "") for r in rows or []
                   for peer in r.get("link_peers") or []
                   if isinstance(peer, dict)
                   and ((peer.get("device") or {}).get("name") or "") == relay["device"]})
    if len(hits) != 1:
        return "", (f"NetBox cables {len(hits)} of the device's interfaces to the relay "
                     f"{relay['device']}" + (f" ({', '.join(hits)})" if hits else "")
                     + ": give the uplink")
    return hits[0], f"NetBox's cable to the relay {relay['device']}"
