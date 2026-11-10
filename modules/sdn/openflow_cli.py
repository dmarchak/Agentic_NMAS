"""The vendor OpenFlow drivers: what the OpenFlow configuration (`modules/sdn/openflow_config.py`)
needs of a switch configured by CLI lines, per template (docs/LAB9_OPENFLOW.md section 4b).

Two templates have one: ``arista_eos`` (Arista EOS, netmiko ``arista_eos``) and
``aruba_os_switch`` (HP ProCurve / ArubaOS-Switch, netmiko ``hp_procurve`` and its aliases). Each
driver states:

- **its version** (`version`): the switch's own OS version from `show version`, which selects the
  platform profile's entry (`profile.select`);
- **its datapath id** (`dpid`): from `show openflow` (EOS's ``DPID: 0x…``) or `show openflow
  instance <name>` (ArubaOS-Switch's ``Datapath ID : …``), as 16 hex digits;
- **its undo** (`undo`): from the switch's parsed OpenFlow layer before (`openflow_state`) and the
  program's, the lines that put back exactly what the program changes, in the template's own
  forms and their ``no`` forms; ``None`` with why when something cannot be put back;
- **its refusals** (`failed`): the CLI's own words when a line was not taken.

**What the session may carry** (`SHAPES`, asked by `discovery.held_config_refusal`, which
`connection._guard_writes` asks before a `send_config_set` on these drivers): each line, stripped,
is one of its template's shapes below, every argument one token of its shape (an address by
`ipaddress`), printable ASCII; and only while the switch is held. Nothing else: no save, no
`configure` of its own, no other line. Both vendor templates take an IPv4 controller only (their
vendor documents; `ipv6_controller: false`), so an IPv6 controller is refused at the render,
naming it; the switch's own management address may be IPv6 (the session opens on it).

**No save** (docs/LAB9_OPENFLOW.md section 4b): whether the OpenFlow configuration writes the
startup configuration is undecided, so the operation never sends `write memory`, and its result
says the running configuration holds the change until the switch reloads.

Reads only text here: nothing in this module opens a session.
"""

import ipaddress
import re

_V4 = r"[0-9]{1,3}(?:\.[0-9]{1,3}){3}"
_TCP = r"[0-9]{1,5}"
_EOS_IF = r"Ethernet[0-9]{1,3}(?:/[0-9]{1,3}){0,2}"
_VID = r"[0-9]{1,4}"
_AOS_PORT = r"[A-Za-z]{0,2}[0-9]{1,3}"
#: An ArubaOS-Switch instance name: `discovery._INSTANCE`'s shape.
_NAME = r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}"
_ID = r"[0-9]{1,3}"

#: template -> the shapes of the lines its session may carry (stripped), the program's and the
#: undo's. One rule per line form; nothing else is ever sent on these sessions.
SHAPES = {
    "arista_eos": tuple(re.compile(x + r"\Z") for x in (
        rf"interface {_EOS_IF}",
        r"(?:no )?lldp (?:transmit|receive)",
        r"(?:no )?openflow",
        rf"(?:no )?controller tcp:(?P<addr>{_V4}):{_TCP}",
        r"bind mode (?:interface|vlan)",
        rf"(?:no )?bind interface {_EOS_IF}",
        r"(?:no )?shutdown")),
    "aruba_os_switch": tuple(re.compile(x + r"\Z") for x in (
        rf"vlan {_VID} untagged {_AOS_PORT}",
        rf"lldp admin-status {_AOS_PORT} (?:disable|tx_rx)",
        rf"openflow controller-id {_ID} ip (?P<addr>{_V4}) port {_TCP} "
        rf"controller-interface vlan {_VID}",
        rf"no openflow controller-id {_ID}",
        rf"(?:no )?openflow instance {_NAME} member vlan {_VID}",
        rf"(?:no )?openflow instance {_NAME} controller-id {_ID}",
        rf"openflow instance {_NAME} version 1\.[03](?: only)?",
        rf"openflow instance {_NAME} connection-interruption-mode fail-(?:secure|standalone)",
        rf"openflow instance {_NAME} (?:enable|disable)",
        rf"no openflow instance {_NAME}",
        r"openflow (?:enable|disable)")),
}
#: What a CLI prints when it did not take a line (EOS: ``% Invalid input``; ArubaOS-Switch:
#: ``Invalid input:``), each a refusal of the configuration sent.
_REFUSED = re.compile(r"(?im)^\s*(%\s*\S.*|invalid input.*|incomplete (?:input|command).*|"
                      r"ambiguous (?:input|command).*|error[: ].*)$")


def line_refusal(template: str, lines) -> str:
    """``""`` when every one of *lines* is one of *template*'s shapes (`SHAPES`), else why,
    naming the line and the template. Never a partial pass: one line off its shape refuses the
    whole set."""
    shapes = SHAPES.get(template)
    if shapes is None:
        return f"the {template} template has no vendor driver, so no line of it is sent"
    if isinstance(lines, str):
        lines = [lines]
    if not lines:
        return "the configuration set is empty"
    for i, line in enumerate(lines, 1):
        if not isinstance(line, str) or not line.isascii() or not line.isprintable():
            return f"line {i} is not one line of printable ASCII"
        body = line.strip()
        found = next((rx.fullmatch(body) for rx in shapes if rx.fullmatch(body)), None)
        if found is None:
            return (f"line {i} {body[:80]!r} is not one of the {template} OpenFlow "
                    "configuration's shapes")
        addr = found.groupdict().get("addr")
        if addr:
            try:
                ipaddress.IPv4Address(addr)
            except ValueError:
                return f"line {i}'s controller {addr!r} is not an IPv4 address"
    return ""


def failed(answer: str) -> str:
    """The CLI's own words when *answer* says a line was not taken, else ``""``."""
    m = _REFUSED.search(str(answer or ""))
    return m.group(1).strip()[:200] if m else ""


def _hex16(text: str) -> str:
    t = str(text or "").strip().lower()
    t = t[2:] if t.startswith("0x") else t
    return t.rjust(16, "0") if re.fullmatch(r"[0-9a-f]{1,16}", t) else ""


# --------------------------------------------------------------------------- Arista EOS

class Eos:
    template = "arista_eos"
    family = "Arista EOS"

    @staticmethod
    def version(text: str) -> str:
        m = re.search(r"Software image version:\s*(\S+)", str(text or ""))
        return m.group(1) if m else ""

    @staticmethod
    def dpid(text: str) -> str:
        """`show openflow`'s ``DPID: 0x…`` as 16 hex digits, or ``""``."""
        m = re.search(r"(?m)^\s*DPID:\s*(0x[0-9a-fA-F]+|[0-9a-fA-F]+)\s*$", str(text or ""))
        return _hex16(m.group(1)) if m else ""

    @staticmethod
    def undo(before: dict, want: dict, values: dict) -> tuple:
        """``(lines, "")``: the lines putting back what the program changes on an EOS switch
        whose OpenFlow layer was *before*; an agent that ran before and whose binding the undo
        changes is restarted (C2599), as the program's change was."""
        default = {"controllers": [], "bind_mode": "interface", "bound": [], "enabled": False}
        lines = []
        if all(before.get(k) == v for k, v in default.items()):
            block = ["no openflow"]
        else:
            body = [f"   no controller {c}" for c in want.get("controllers") or []
                    if c not in before.get("controllers") or []]
            changed = False
            if want.get("bind_mode") and want["bind_mode"] != before.get("bind_mode"):
                body.append(f"   bind mode {before.get('bind_mode')}")
                changed = True
            added = [b for b in want.get("bound") or [] if b not in before.get("bound") or []]
            body += [f"   no bind interface {b}" for b in added]
            changed = changed or bool(added)
            if want.get("enabled") and not before.get("enabled"):
                body.append("   shutdown")
            elif changed and before.get("enabled"):
                body += ["   shutdown", "   no shutdown"]
            block = ["openflow"] + body if body else []
        for port in want.get("lldp_off") or []:
            if port not in before.get("lldp_off") or []:
                lines += [f"interface {port}", "   lldp transmit", "   lldp receive"]
        return block + lines, ""


# --------------------------------------------------------------------------- ArubaOS-Switch

class ArubaOsSwitch:
    template = "aruba_os_switch"
    family = "HP ProCurve / ArubaOS-Switch"

    @staticmethod
    def version(text: str) -> str:
        m = re.search(r"\b([A-Z]{1,2}\.[0-9]{2}\.[0-9]{2}\.[0-9]{4})\b", str(text or ""))
        return m.group(1) if m else ""

    @staticmethod
    def dpid(text: str) -> str:
        """`show openflow instance <name>`'s ``Datapath ID : …`` as 16 hex digits, or ``""``."""
        m = re.search(r"(?m)^\s*Datapath ID\s*:\s*([0-9a-fA-F]{1,16})\s*$", str(text or ""))
        return _hex16(m.group(1)) if m else ""

    @staticmethod
    def undo(before: dict, want: dict, values: dict) -> tuple:
        """``(lines, "")`` putting back what the program changes, in the template's one-line
        forms and their ``no`` forms; ``(None, why)`` when a port's VLAN before cannot be told."""
        inst = values.get("openflow.instance") or ""
        lines = []
        if want.get("enabled") and not before.get("enabled"):
            lines.append("openflow disable")
        had = (before.get("instances") or {}).get(inst)
        made = (want.get("instances") or {}).get(inst) or {}
        if had is None:
            if made:
                lines += [f"openflow instance {inst} disable", f"no openflow instance {inst}"]
        else:
            if made.get("enabled") and not had.get("enabled"):
                lines.append(f"openflow instance {inst} disable")
            lines += [f"no openflow instance {inst} member vlan {v}"
                      for v in made.get("member_vlans") or [] if v not in had["member_vlans"]]
            lines += [f"no openflow instance {inst} controller-id {c}"
                      for c in made.get("controller_ids") or [] if c not in had["controller_ids"]]
            if made.get("version") and made["version"] != had.get("version"):
                lines.append(f"openflow instance {inst} version {had.get('version')}")
            if made.get("fail_mode") and made["fail_mode"] != had.get("fail_mode"):
                lines.append(f"openflow instance {inst} connection-interruption-mode "
                             f"{had.get('fail_mode')}")
        for cid, c in sorted((want.get("controllers") or {}).items()):
            old = (before.get("controllers") or {}).get(cid)
            if old is None:
                lines.append(f"no openflow controller-id {cid}")
            elif old != c:
                lines.append(f"openflow controller-id {cid} ip {old['address']} port "
                             f"{old['port']} controller-interface vlan {old['interface_vlan']}")
        lines += [f"lldp admin-status {p} tx_rx" for p in want.get("lldp_disabled") or []
                  if p not in before.get("lldp_disabled") or []]
        vlan = values.get("openflow.vlan") or ""
        for port in values.get("ports") or []:
            was = sorted(v for v, members in (before.get("untagged") or {}).items()
                         if port in members)
            if vlan in was:
                continue
            if not was:
                return None, (f"port {port} is untagged in no VLAN in the switch's running "
                              "configuration, so Mercury could not put it back on a rollback")
            lines.append(f"vlan {was[0]} untagged {port}")
        return lines, ""


DRIVERS = {"arista_eos": Eos, "aruba_os_switch": ArubaOsSwitch}
