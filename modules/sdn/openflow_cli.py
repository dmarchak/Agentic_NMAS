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
- **its refusals** (`failed`): the CLI's own words when a line was not taken;
- **EOS's bound set in one line** (`Eos.bind_set`; C2996): every OpenFlow port of an EOS switch
  as the ONE argument of a `bind interface` line, in a form an EOS switch has been read to hold
  (one interface, or one unbroken range of Ethernet<n> interfaces, ``Et18-19``); any other set
  is refused, never guessed. Whether EOS 4.17.0F ADDS a `bind interface` line's interfaces to
  its bound set or REPLACES the set with them is not measured, and one line naming the whole set
  is right either way. The undo is right either way too: `no bind interface <the program's
  set>` and then `bind interface <the set before>`;
- **its agent's own answer** (`Eos.bound`, `Eos.agent_check`; C2779): the interfaces `show
  openflow` lists under ``Bind mode:``, compared as a set of full names with the program's.

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
#: Neighbouring Ethernet<n> interfaces as EOS's own configuration writes them (``Et18-19``:
#: tests/fixtures/lab9_captures/2026-11-06/arista-sw1.txt, its openflow block).
_EOS_RANGE = r"Et[0-9]{1,3}-[0-9]{1,3}"
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
        rf"(?:no )?bind interface (?:{_EOS_IF}|{_EOS_RANGE})",
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


def _natural(name: str) -> list:
    """A sort key reading the numbers in *name* as numbers (Ethernet9 before Ethernet18)."""
    return [int(x) if x.isdigit() else x for x in re.split(r"([0-9]+)", str(name))]


def _said(names) -> str:
    return ", ".join(sorted(set(names), key=_natural)) or "none"


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

    #: The read Verify asks for the agent's own bound interfaces (C2779): on EOS's capture
    #: list, whole (`discovery`).
    AGENT_READ = "show openflow"
    AGENT_CHECK = "the OpenFlow agent's bound interfaces"
    #: What Verify checks on this family beyond every vendor switch's two checks, as the
    #: preview says it.
    VERIFY_ALSO = ("the switch's own show openflow lists the program's bound interfaces",)
    #: The one-line forms `bind_set` writes, as a refusal says them.
    BIND_SET_FORMS = ("one interface, or one unbroken range of Ethernet<n> interfaces "
                      "(`bind interface Et18-19`, as an EOS switch's own configuration "
                      "holds it)")

    @staticmethod
    def bind_set(ports) -> tuple:
        """``(text, "")``: *ports* (interface names, in any spelling EOS prints: Ethernet18,
        Et18) as the ONE argument of a `bind interface` line; or ``("", why)`` for a set whose
        one-line form no EOS switch has been read to hold (C2996). Two forms are written:

        - one interface, by its full name (``Ethernet18``): the line the template rendered for
          each port before, under its cited command entry (`eos-bind-interface`); no capture
          holds a switch binding a single interface;
        - two or more Ethernet<n> interfaces with no gap between them, as EOS 4.17.0F's own
          running configuration writes them (``Et18-19``; ``Et17-18``:
          tests/fixtures/lab9_captures/2026-11-06/arista-sw1.txt and arista-sw2.txt).

        A set with a gap, or one naming Ethernet<n>/<m> or another kind beside others, is
        refused: how EOS writes it in one line (a comma list, several ranges) is in no capture
        and no cited document, and a guessed syntax is never sent. No ports is ``("", "")``."""
        from modules.sdn import openflow_state as S
        names = []
        for port in ports or []:
            try:
                one = S.expand_eos(port)
            except S.Unparsable:
                one = []
            if len(one) != 1:
                return "", f"{str(port)!r} is not the name of one EOS interface"
            names.append(one[0])
        names = sorted(set(names), key=_natural)
        if len(names) < 2:
            return (names[0] if names else ""), ""
        numbers = []
        for name in names:
            m = re.fullmatch(r"Ethernet([0-9]+)", name)
            if not m:
                return "", f"{name} is not named Ethernet<n>"
            numbers.append(int(m.group(1)))
        gaps = sorted(set(range(numbers[0], numbers[-1] + 1)) - set(numbers))
        if gaps:
            return "", (", ".join(f"Ethernet{n}" for n in gaps)
                        + f" {'is' if len(gaps) == 1 else 'are'} not among them")
        return f"Et{numbers[0]}-{numbers[-1]}", ""

    @staticmethod
    def bound(text: str) -> tuple:
        """``(names, "")``: the interfaces `show openflow` lists under ``Bind mode:``, as full
        names (``Et18-19`` is Ethernet18 and Ethernet19; ``<none>`` is no interface); or
        ``(None, why)`` when the answer holds no such list or a word of it is not an EOS
        interface or range: unread, never an empty set."""
        from modules.sdn import openflow_state as S
        lines = str(text or "").splitlines()
        at = next((i for i, x in enumerate(lines) if re.match(r"Bind mode:", x)), None)
        if at is None:
            return None, "it prints no `Bind mode:` section"
        words, indent = None, 0
        for raw in lines[at + 1:]:
            here = len(raw) - len(raw.lstrip(" "))
            if not raw.strip():
                continue
            if words is None:
                m = re.match(r"\s+interfaces:(.*)\Z", raw)
                if not m:
                    break
                words, indent = m.group(1).replace(",", " ").split(), here
            elif here > indent:
                words += raw.replace(",", " ").split()
            else:
                break
        if words is None:
            return None, "its `Bind mode:` section lists no interfaces"
        if not words:
            return None, "its `interfaces:` list is empty (an agent binding none prints <none>)"
        if words == ["<none>"]:
            return [], ""
        names = []
        for word in words:
            try:
                names += S.expand_eos(word)
            except S.Unparsable as exc:
                return None, f"its `interfaces:` list holds {word!r}: {exc}"
        return sorted(set(names), key=_natural), ""

    @staticmethod
    def agent_check(want: dict, shown: str) -> dict:
        """Verify's check of the agent's own bound interfaces (C2779): *shown* (`show
        openflow`'s answer) against the program's model *want*, as sets of full names.
        ``{"name", "state", "words"}``: ``pass``; ``fail`` naming both sets (intended, read);
        ``unread`` when the answer cannot be read for them (neither passes nor fails)."""
        intended = list(want.get("bound") or [])
        got, why = Eos.bound(shown)
        if got is None:
            state, words = "unread", (f"bound interfaces: intended {_said(intended)}; "
                                      f"`{Eos.AGENT_READ}` could not be read for them: {why}")
        elif set(got) == set(intended):
            state, words = "pass", (f"`{Eos.AGENT_READ}` lists the program's bound "
                                    f"interfaces ({_said(intended)})")
        else:
            state, words = "fail", (f"bound interfaces: intended {_said(intended)}; "
                                    f"`{Eos.AGENT_READ}` lists {_said(got)}")
        return {"name": Eos.AGENT_CHECK, "state": state, "words": words}

    @staticmethod
    def undo(before: dict, want: dict, values: dict) -> tuple:
        """``(lines, "")``: the lines putting back what the program changes on an EOS switch
        whose OpenFlow layer was *before*; an agent that ran before and whose binding the undo
        changes is restarted (C2599), as the program's change was.

        **The bound set** (C2996): when the program changes it, the undo is `no bind interface
        <the program's set>` and then, for a switch that bound some before, `bind interface
        <the set before>`, each set in one line (`bind_set`). That is right whichever way EOS
        reads a `bind interface` line. If a line ADDS to the set, the program left the set
        before plus the program's, which is the program's (a plan is refused unless the
        program's set holds every interface bound before); the ``no`` line empties it and the
        last line binds the set before. If a line REPLACES the set, the program left the
        program's set; the ``no`` line empties it, or leaves what it does not name, which is
        nothing; and the last line sets the set before. ``(None, why)`` when the set before
        has no one-line form Mercury writes."""
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
            was, now = list(before.get("bound") or []), list(want.get("bound") or [])
            if now and set(now) != set(was):
                gone, why = Eos.bind_set(now)
                if why:
                    return None, (f"the program's bound interfaces ({_said(now)}) have no "
                                  f"one-line form for the undo to name: {why}")
                back, why = Eos.bind_set(was)
                if why:
                    return None, (f"the switch binds {_said(was)} now, and the undo would put "
                                  "that set back in one `bind interface` line, which Mercury "
                                  f"writes only as {Eos.BIND_SET_FORMS}: {why}, so Mercury "
                                  "could not put it back on a rollback")
                body.append(f"   no bind interface {gone}")
                if back:
                    body.append(f"   bind interface {back}")
                changed = True
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
#: A template's ``port_set`` -> the writer of all its ports as one value, ``{ports.one_line}``
#: (`openflow_templates.render`): ``(text, "")``, or ``("", why)`` for a set it does not write.
PORT_SETS = {"eos_range": (Eos.bind_set, "one `bind interface` line", Eos.BIND_SET_FORMS)}
