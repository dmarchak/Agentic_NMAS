"""A switch's OpenFlow layer as a parsed model, from its own configuration text or from a
rendered program, so the two are compared as models, never as raw text (the SDN platform design
revision 6, section 3 A, "The dry run compares parsed models"; T1, T2).

**The model per template** (`model_of`, `parse`):

- ``arista_eos``: ``controllers`` (``tcp:<a>:<p>``), ``bind_mode``, ``bound`` (interface names,
  ranges expanded: ``Et18-19`` is Ethernet18 and Ethernet19), ``enabled`` and ``lldp_off`` (the
  interfaces carrying both ``no lldp transmit`` and ``no lldp receive``). EOS's running
  configuration hides the default ``bind mode interface``, so an absent bind mode is
  ``interface``; an ``openflow`` block with no ``no shutdown`` is not enabled.
- ``aruba_os_switch``: ``controllers`` (by id: address, port, controller VLAN), ``instances``
  (by name: member VLANs, controller ids, version, fail mode, enabled), ``enabled``,
  ``lldp_disabled`` (ports) and ``untagged`` (VLAN to ports). The running configuration's
  nested contexts and the program's one-line form read the same: each context line is read as
  the line its context names (``instance "lab9"`` then ``version 1.3`` is ``openflow instance
  lab9 version 1.3``). Hidden defaults: version ``1.0`` (the guide) and fail mode
  ``fail-secure`` (the K.16.02 capture's `show openflow instance`: Fail-Secure with no line).
- ``ovs``: per bridge, ``controllers``, ``fail_mode``, ``ports`` (the bridge's own internal port
  left out), ``ofport`` (each port's number: given, from `ovs-vsctl list interface`'s
  ``ofport``, or requested, from the program's ``ofport_request``), and from a program only,
  ``protocols`` and ``datapath_id`` (`ovs-vsctl show` prints neither).

**The undo's forms read too** (`modules/sdn/openflow_cli.py`): EOS's ``no openflow``, ``no
controller``, ``no bind interface`` and ``lldp transmit``/``lldp receive``; ArubaOS-Switch's ``no
openflow controller-id``, ``no openflow instance`` (whole, or its member VLAN or controller id)
and a port untagged in a VLAN leaving the VLAN it was untagged in (a port is untagged in one VLAN
only). So the configuration as it would be after a program and its undo parses as the switch
would hold it, and a plan checks its undo before anything is sent.

**Compared** by `differences(want, have)`: every value the wanted model holds, against the
switch's (a wanted mapping that is empty where the switch's is not differs: no instance or
controller rendered where the switch has one); a value the state read does not carry is listed apart as unread, never as equal or as
different (an unreadable read neither passes nor fails). Lists the program adds to (ports) are
compared as sets. `bind_changed` says whether a program binds a port the switch does not (the
EOS agent restart's trigger, C2599). Reads only text: nothing here touches a device.
"""

import re

_EOS_SHORT = {"et": "Ethernet", "ethernet": "Ethernet", "ma": "Management",
              "management": "Management", "po": "Port-Channel", "port-channel": "Port-Channel"}
_EOS_RANGE = re.compile(r"(?i)([a-z-]+?)((?:[0-9]+/)*)([0-9]+)(?:-([0-9]+))?\Z")
UNREAD = "unread"


class Unparsable(ValueError):
    """Text that is not the configuration it was given as, in words."""


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def expand_numbers(text: str) -> list:
    """``2-3`` is ``["2", "3"]``; ``1,4-6`` is ``["1", "4", "5", "6"]``."""
    out = []
    for part in str(text or "").split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"([0-9]+)(?:-([0-9]+))?", part)
        if not m:
            raise Unparsable(f"{part!r} is not a port number or range")
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        out += [str(n) for n in range(lo, hi + 1)]
    return out


def expand_eos(text: str) -> list:
    """EOS's interface ranges in full names: ``Et18-19`` is ``["Ethernet18", "Ethernet19"]``,
    ``Et1/1-2,Et5`` is ``["Ethernet1/1", "Ethernet1/2", "Ethernet5"]``."""
    out = []
    for part in str(text or "").replace(" ", "").split(","):
        if not part:
            continue
        m = _EOS_RANGE.fullmatch(part)
        if not m:
            raise Unparsable(f"{part!r} is not an EOS interface or range")
        kind = _EOS_SHORT.get(m.group(1).lower())
        if kind is None:
            raise Unparsable(f"{part!r}: {m.group(1)!r} is not an EOS interface kind")
        lo, hi = int(m.group(3)), int(m.group(4) or m.group(3))
        out += [f"{kind}{m.group(2)}{n}" for n in range(lo, hi + 1)]
    return out


# --------------------------------------------------------------------------- Arista EOS

def eos(text: str) -> dict:
    """The OpenFlow layer of EOS configuration *text* (`show running-config`, or a program)."""
    model = {"controllers": [], "bind_mode": "interface", "bound": [], "enabled": False,
             "lldp_off": []}
    block, iface, lldp = None, None, {}
    seen = False
    for raw in str(text or "").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("!"):
            continue
        if _indent(line) == 0:
            words = line.split()
            block, iface = words[0], None
            if words[0] == "interface" and len(words) == 2:
                try:
                    iface = expand_eos(words[1])[0]
                except Unparsable:
                    iface = words[1]          # a kind OpenFlow never binds (Vlan100, Loopback0)
            elif words == ["openflow"]:
                seen = True
            elif words == ["no", "openflow"]:
                # The whole block removed (an undo's form): the defaults again.
                model.update(controllers=[], bind_mode="interface", bound=[], enabled=False)
                seen, block = False, None
            continue
        words = line.split()
        if block == "interface" and iface:
            if words in (["no", "lldp", "transmit"], ["no", "lldp", "receive"]):
                lldp.setdefault(iface, set()).add(words[2])
            elif words in (["lldp", "transmit"], ["lldp", "receive"]):
                lldp.setdefault(iface, set()).discard(words[1])
        elif block == "openflow":
            if words[0] == "controller" and len(words) == 2:
                model["controllers"].append(words[1])
            elif words[:2] == ["no", "controller"] and len(words) == 3:
                model["controllers"] = [c for c in model["controllers"] if c != words[2]]
            elif words[:2] == ["bind", "mode"] and len(words) == 3:
                model["bind_mode"] = words[2]
            elif words[:2] == ["bind", "interface"] and len(words) == 3:
                model["bound"] += expand_eos(words[2])
            elif words[:3] == ["no", "bind", "interface"] and len(words) == 4:
                gone = set(expand_eos(words[3]))
                model["bound"] = [b for b in model["bound"] if b not in gone]
            elif words == ["no", "shutdown"]:
                model["enabled"] = True
            elif words == ["shutdown"]:
                model["enabled"] = False
    if not seen:
        model["enabled"] = False
    model["lldp_off"] = sorted(i for i, got in lldp.items() if got == {"transmit", "receive"})
    model["bound"] = sorted(set(model["bound"]))
    model["controllers"] = sorted(set(model["controllers"]))
    return model


# --------------------------------------------------------------------------- ArubaOS-Switch

_AOS_CONTEXT = (re.compile(r"openflow\Z"), re.compile(r'instance\s+"?([^"\s]+)"?\Z'),
                re.compile(r"vlan\s+[0-9]+\Z"), re.compile(r"interface\s+\S+\Z"))


def _aos_statements(text: str) -> list:
    """Each line of ArubaOS-Switch configuration *text* as the one-line statement its context
    makes it (``openflow`` / ``instance "lab9"`` / ``version 1.3`` is ``openflow instance lab9
    version 1.3``)."""
    out, stack = [], []
    for raw in str(text or "").splitlines():
        line = raw.rstrip()
        body = line.strip()
        if not body or body.startswith(";") or body in ("exit", "Running configuration:"):
            continue
        indent = _indent(line)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        words = " ".join(p for _i, p in stack)
        m = _AOS_CONTEXT[1].fullmatch(body)
        here = f"instance {m.group(1)}" if m else body
        statement = f"{words} {here}".strip()
        if any(rx.fullmatch(body) for rx in _AOS_CONTEXT):
            stack.append((indent, here))
            if indent == 0 or m:
                continue
        out.append(statement)
    return out


def aruba_os_switch(text: str) -> dict:
    """The OpenFlow layer of ArubaOS-Switch configuration *text* (`show running-config`, or a
    program of one-line statements), its hidden defaults supplied."""
    model = {"controllers": {}, "instances": {}, "enabled": False, "lldp_disabled": [],
             "untagged": {}}
    lldp = set()
    for s in _aos_statements(text):
        w = s.split()
        if w[:3] == ["no", "openflow", "controller-id"] and len(w) == 4:
            # An undo's forms: `no <the line>` removes what the line made.
            model["controllers"].pop(w[3], None)
        elif w[:3] == ["no", "openflow", "instance"] and len(w) == 4:
            model["instances"].pop(w[3], None)
        elif w[:3] == ["no", "openflow", "instance"] and len(w) >= 6:
            inst = model["instances"].get(w[3])
            if inst is not None and w[4:6] == ["member", "vlan"] and len(w) == 7:
                gone = set(expand_numbers(w[6]))
                inst["member_vlans"] = [v for v in inst["member_vlans"] if v not in gone]
            elif inst is not None and w[4] == "controller-id" and len(w) == 6:
                inst["controller_ids"] = [c for c in inst["controller_ids"] if c != w[5]]
        elif w[:2] == ["openflow", "controller-id"] and len(w) >= 9 and w[3] == "ip":
            model["controllers"][w[2]] = {"address": w[4], "port": w[6],
                                          "interface_vlan": w[-1]}
        elif w[:2] == ["openflow", "instance"] and len(w) >= 4:
            inst = model["instances"].setdefault(w[2], {
                "member_vlans": [], "controller_ids": [], "version": "1.0",
                "fail_mode": "fail-secure", "enabled": False})
            rest = w[3:]
            if rest[:2] == ["member", "vlan"]:
                inst["member_vlans"] = sorted(set(inst["member_vlans"])
                                              | set(expand_numbers(rest[2])))
            elif rest[0] == "controller-id":
                inst["controller_ids"] = sorted(set(inst["controller_ids"]) | {rest[1]})
            elif rest[0] == "version":
                inst["version"] = " ".join(rest[1:])
            elif rest[0] == "connection-interruption-mode":
                inst["fail_mode"] = rest[1]
            elif rest == ["enable"]:
                inst["enabled"] = True
            elif rest == ["disable"]:
                inst["enabled"] = False
        elif w == ["openflow", "enable"]:
            model["enabled"] = True
        elif w == ["openflow", "disable"]:
            model["enabled"] = False
        elif w[:2] == ["lldp", "admin-status"] and len(w) == 4:
            ports = set(expand_numbers(w[2]))
            lldp = (lldp | ports) if w[3] == "disable" else (lldp - ports)
        elif w[0] == "vlan" and len(w) >= 4 and w[2] in ("untagged", "no"):
            vid = w[1]
            have = set(model["untagged"].get(vid, []))
            if w[2] == "untagged":
                ports = set(expand_numbers(w[3]))
                have |= ports
                # A port is untagged in one VLAN only: untagging it here takes it out of the
                # VLAN it was untagged in (an undo's `vlan 1 untagged 2` moves it back).
                for other, members in model["untagged"].items():
                    if other != vid:
                        model["untagged"][other] = [p for p in members if p not in ports]
            elif w[3] == "untagged" and len(w) == 5:
                have -= set(expand_numbers(w[4]))
            model["untagged"][vid] = sorted(have, key=int)
    model["lldp_disabled"] = sorted(lldp, key=int)
    # Each member VLAN's untagged ports are part of the layer even when none are set, so a
    # program that puts no port in its member VLAN never compares equal to one that does.
    for inst in model["instances"].values():
        for vid in inst["member_vlans"]:
            model["untagged"].setdefault(vid, [])
    return model


# --------------------------------------------------------------------------- Open vSwitch

def ovs_show(show: str, interfaces: str = "") -> dict:
    """``{bridge: {...}}`` from `ovs-vsctl show` (*show*) and, for the port numbers, `ovs-vsctl
    --columns=name,ofport list interface` (*interfaces*)."""
    bridges, bridge, name = {}, None, ""
    for raw in str(show or "").splitlines():
        body = raw.strip()
        m = re.fullmatch(r'Bridge\s+"?([^"\s]+)"?', body)
        if m:
            bridge = bridges.setdefault(m.group(1), {"controllers": [], "fail_mode": "",
                                                    "ports": [], "ofport": {}})
            name = m.group(1)
            continue
        if bridge is None:
            continue
        m = re.fullmatch(r'Controller\s+"([^"]+)"', body)
        if m:
            bridge["controllers"].append(m.group(1))
        m = re.fullmatch(r"fail_mode:\s*(\S+)", body)
        if m:
            bridge["fail_mode"] = m.group(1)
        m = re.fullmatch(r'Port\s+"?([^"\s]+)"?', body)
        if m and m.group(1) != name:
            bridge["ports"].append(m.group(1))
    numbers, current = {}, None
    for raw in str(interfaces or "").splitlines():
        m = re.fullmatch(r"\s*(name|ofport)\s*:\s*\"?([^\"]*?)\"?\s*", raw)
        if not m:
            continue
        if m.group(1) == "name":
            current = m.group(2)
        elif current is not None:
            numbers[current] = m.group(2)
    for b in bridges.values():
        b["ports"] = sorted(b["ports"])
        b["controllers"] = sorted(b["controllers"])
        b["ofport"] = {p: numbers[p] for p in b["ports"] if p in numbers} if interfaces \
            else UNREAD
    return bridges


def ovs_program(program: str) -> dict:
    """``{bridge: {...}}`` from one `sudo -n ovs-vsctl` transaction."""
    words = str(program or "").split()
    if words[:3] == ["sudo", "-n", "ovs-vsctl"]:
        words = words[3:]
    commands, cur = [], []
    for w in words:
        if w == "--":
            commands.append(cur)
            cur = []
        else:
            cur.append(w)
    commands.append(cur)
    bridges, port_of = {}, {}

    def bridge(name):
        return bridges.setdefault(name, {"controllers": [], "fail_mode": "", "ports": [],
                                         "ofport": {}})
    for c in commands:
        c = [x for x in c if x not in ("--may-exist", "--if-exists")]
        if not c:
            continue
        verb, args = c[0], c[1:]
        if verb == "add-br":
            bridge(args[0])
        elif verb == "add-port":
            bridge(args[0])["ports"].append(args[1])
            port_of[args[1]] = args[0]
        elif verb == "set-fail-mode":
            bridge(args[0])["fail_mode"] = args[1]
        elif verb == "set-controller":
            bridge(args[0])["controllers"] = sorted(args[1:])
        elif verb == "set" and args[0] == "bridge":
            key, _, value = args[2].partition("=")
            if key == "protocols":
                bridge(args[1])["protocols"] = value.split(",")
            elif key == "other-config:datapath-id":
                bridge(args[1])["datapath_id"] = value
        elif verb == "set" and args[0] == "interface":
            key, _, value = args[2].partition("=")
            if key == "ofport_request" and args[1] in port_of:
                bridge(port_of[args[1]])["ofport"][args[1]] = value
    for b in bridges.values():
        b["ports"] = sorted(b["ports"])
        # A port the program requests no number for is numbered by OVS in add order (C2603):
        # said as such, so a program without its requests never compares equal.
        b["ofport"] = {p: b["ofport"].get(p, UNREQUESTED) for p in b["ports"]}
    return bridges


UNREQUESTED = "unrequested (numbered by add order)"


# --------------------------------------------------------------------------- dispatch

def model_of(name: str, rendered: dict) -> dict:
    """The model of template *name*'s rendered program (`openflow_templates.render`'s answer)."""
    program = rendered.get("program") or []
    if name == "ovs":
        return ovs_program(program[0] if program else "")
    return parse(name, "\n".join(program))


def parse(name: str, text: str, interfaces: str = "") -> dict:
    """The model of a switch's own configuration *text* for template *name* (for ``ovs``,
    `ovs-vsctl show` and, in *interfaces*, the ``name``/``ofport`` listing)."""
    if name == "arista_eos":
        return eos(text)
    if name == "aruba_os_switch":
        return aruba_os_switch(text)
    if name == "ovs":
        return ovs_show(text, interfaces)
    raise Unparsable(f"no OpenFlow state parser for the {name} template")


def differences(want, have, path: str = "") -> tuple:
    """``(different, unread)``: each value of *want* the switch's *have* holds otherwise
    (``"<path>: wanted <w>, the switch has <h>"``), and each it does not carry (its path).
    Ports, controllers and other lists compare as sets."""
    different, unread = [], []
    if have is UNREAD:
        return different, [path or "(all)"]
    if isinstance(want, dict):
        if not isinstance(have, dict):
            return [f"{path}: wanted {want}, the switch has {have}"], []
        if not want and have:
            # A program holding no controller or instance where the switch holds some.
            return [f"{path}: wanted none, the switch has {', '.join(map(str, sorted(have)))}"], []
        for key in sorted(want):
            sub = f"{path}.{key}" if path else str(key)
            if key not in have:
                unread.append(sub)
                continue
            d, u = differences(want[key], have[key], sub)
            different += d
            unread += u
        return different, unread
    if isinstance(want, list) and isinstance(have, list):
        if sorted(map(str, want)) != sorted(map(str, have)):
            different.append(f"{path}: wanted {', '.join(map(str, want)) or 'none'}, the "
                             f"switch has {', '.join(map(str, have)) or 'none'}")
        return different, unread
    if want != have:
        different.append(f"{path}: wanted {want}, the switch has {have}")
    return different, unread


def bind_changed(want: dict, have: dict) -> bool:
    """Whether the program binds a port, or a bind mode, the switch's RUNNING agent does not
    (C2599): False for a switch whose agent is not enabled (a first enable starts it with the
    new binding) and for a model with no binding."""
    if not have.get("enabled") or "bound" not in want:
        return False
    return bool(set(want.get("bound") or []) - set(have.get("bound") or [])) \
        or (want.get("bind_mode") != have.get("bind_mode"))


def render_against(name: str, values: dict, have: dict, selected=None, first=None) -> dict:
    """Template *name* rendered for a switch whose parsed state is *have*: the ``state.``
    values derived from it (``state.bind_changed``, `bind_changed`), then the program's model
    compared with it. ``{"ok", "error", "rendered", "want", "different", "unread"}``. Sends and
    reads nothing: *have* is a model the caller parsed (`parse`). *first* is the caller's own
    render of the same values (`openflow_templates.render`, which asks B), passed so the
    planner asks B itself and nothing renders twice."""
    from modules.sdn import openflow_templates as T
    if first is None:
        first = T.render(name, values, selected=selected)
    out = {"ok": False, "error": first["error"], "rendered": first, "want": {},
           "different": [], "unread": []}
    if not first["ok"]:
        return out
    state = {"state.bind_changed": bind_changed(model_of(name, first), have)}
    rendered = T.render(name, dict(values or {}, **state), selected=selected)
    if not rendered["ok"]:
        out.update(error=rendered["error"], rendered=rendered)
        return out
    out["rendered"], out["want"] = rendered, model_of(name, rendered)
    out["different"], out["unread"] = differences(out["want"], have)
    out["ok"] = True
    return out
