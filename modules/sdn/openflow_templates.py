"""Mercury's OpenFlow configuration templates, one per switch family (docs/LAB9_OPENFLOW.md).

Each template is a YAML file in `openflow_templates/` (vendor knowledge, product): its family,
the netmiko drivers it is for, its form (``ovs-vsctl``: one transaction; ``cli``: configuration
lines in order), the OpenFlow versions and transports the vendor's document says it supports,
whether a controller may be given by an IPv6 address, and its lines. **Every line cites its
vendor document** (``cite``: keys of the template's ``citations``, each naming the document,
the section or command entry, the release, the URL and the date it was read, and whether it
was read on the vendor's page, ``verified``). `problems` checks this, and `render` refuses a
template it finds a problem in.

A citation is a vendor document (the fields above) or a **measurement** (``measured``: the
register row; ``what``, ``evidence``: the masked capture or harness run in this repository that
shows the line accepted, ``release``, ``read``), for a line the lab's own release was seen to
take where no document for that release was read.

**Every line says why** (the SDN design revision 6, 11b(e)): ``why`` is a fixed sentence naming
the concept and the input the line comes from, carried with each rendered line, so the preview
can show each line beside its reason with no AI call; a line without one is a problem.

**Rendered from NetBox values** (`modules/sdn/openflow_values.py`): a line's ``{name}`` is a
value; ``each: ports`` repeats it per OpenFlow port (``{port}``, and ``{port.<value>}`` that
port's own value, such as ``{port.openflow_port}``); a ``text`` of several lines renders as
several program lines. ``when`` keeps a line only when its condition holds (a list: all of
them): ``<name>`` (the value is given), ``<name> == <word>`` or ``<word> in <name>``. A missing
value refuses the render, naming it and where in NetBox it comes from
(`openflow_values.WHERE`). A transport or IPv6 controller the template does not support
refuses too, naming both. ``{ports.one_line}`` is every OpenFlow port in one value, written by
the template's ``port_set`` (`openflow_cli.PORT_SETS`; ``eos_range``: EOS's bound set in one
`bind interface` line, C2996); a set its writer has no evidenced one-line form for refuses the
render, naming the ports, the forms it writes and what is wrong with the set.

**The platform profile decides what the release needs** (`modules/platforms/profile.py`): the
OpenFlow versions the switch offers (a version outside them refuses, naming both; the template
no longer lists versions, C2598), and the values a template reads as ``profile.openflow.<key>``:
`bind_change_requires` (the EOS agent restart, C2599), `openflow_ports_require` (LLDP off on
each OpenFlow port, C2600) and `port_numbering` (an OVS port's number requested as NetBox's,
C2603; elsewhere NetBox's number checked against the switch's own, `numbering_problems`). The
entry is the one `profile.select` chose for the switch's OS version, or, given none, the
profile's only entry; a profile with more than one entry and no selection refuses, naming its
ranges, and a template reading a key its entry does not hold refuses, naming the key.
``state.<name>`` values are the switch's present state as a plan compares it (``state.
bind_changed``: the bound ports differ from the switch's own); a line whose condition reads a
state value not given is left out and said in ``notes``.

**B, the protected set** (`modules/protected.py`; C2588, C2589): `takes` names every port the
switch's OpenFlow instance will take, by the profile's `instance_takes` (the ports NetBox tags
``openflow``, and on a `vlan_members` platform every port carrying the member VLAN as well), and
the render refuses when one is a protected object (``protected.objects``, which
`openflow_values` carries; values without it refuse too), naming the port and both reasons.

**Draft until confirmed, per network.** A template is ``draft`` until a verified person confirms
it on a network against a saved capture of one of its devices (`discovery.captures`): the
confirmation is committed in that network's repository (`openflow_confirmations/<name>.yml`)
naming the capture and the template's SHA-256, so a changed template is a draft again. Only a
CONFIRMED template is ever sent: `push_refusal` is ``""`` for a confirmed template and names the
template and its status otherwise, and every path that sends a template's lines asks it first
(`ovs_config.apply`; `openflow_config.apply` for the vendor drivers). The discovery sessions
refuse every other write as well (`connection._guard_writes`).
"""

import hashlib
import logging
import os
import re

log = logging.getLogger(__name__)

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openflow_templates")
FORMS = ("ovs-vsctl", "cli")
CITATION_FIELDS = ("document", "section", "release", "url", "read")
MEASURED_FIELDS = ("measured", "what", "evidence", "release", "read")
DIR = "openflow_confirmations"
_PLACE = re.compile(r"\{([a-z_]+(?:\.[a-z_]+)*)\}")
_EQUALS = re.compile(r"\s*([a-z_]+(?:\.[a-z_]+)*)\s*==\s*([A-Za-z0-9_.-]+)\s*\Z")
_IN = re.compile(r"\s*([A-Za-z0-9_.-]+)\s+in\s+([a-z_]+(?:\.[a-z_]+)*)\s*\Z")
_KEY = re.compile(r"\s*([a-z_]+(?:\.[a-z_]+)*)\s*\Z")
DRAFT, CONFIRMED = "draft", "confirmed"


class Refused(ValueError):
    """A render or a confirmation refused, naming what and why."""


def names() -> list:
    """The templates Mercury ships, by name."""
    return sorted(f[:-4] for f in os.listdir(HERE) if f.endswith(".yml"))


def _text(name: str) -> str:
    if name not in names():
        raise Refused(f"no OpenFlow template is named {name!r}: {', '.join(names())}")
    with open(os.path.join(HERE, f"{name}.yml"), encoding="utf-8") as fh:
        return fh.read()


def sha256(name: str) -> str:
    """The template file's SHA-256: what a confirmation is bound to."""
    return hashlib.sha256(_text(name).encode("utf-8")).hexdigest()


def load(name: str) -> dict:
    import yaml
    doc = yaml.safe_load(_text(name)) or {}
    doc.setdefault("lines", [])
    doc.setdefault("citations", {})
    return doc


def for_driver(driver: str):
    """The template for netmiko *driver*, or None."""
    for n in names():
        if driver in (load(n).get("drivers") or []):
            return n
    return None


def problems(t: dict) -> list:
    """What is wrong with template *t*: a line with no citation, a citation key it does not
    define, a citation missing a field, a line that does not say why, a condition that is not
    one of the three forms, an unknown form, or a template still listing its own versions (the
    platform profile states them, once)."""
    out = []
    if t.get("form") not in FORMS:
        out.append(f"its form {t.get('form')!r} is not one of {', '.join(FORMS)}")
    if "versions" in t:
        out.append("it lists its own OpenFlow versions: the platform profile states them "
                   "(modules/platforms/profiles/)")
    cites = t.get("citations") or {}
    for i, line in enumerate(t.get("lines") or [], 1):
        keys = line.get("cite") or []
        if not keys:
            out.append(f"line {i} ({line.get('text', '')!r}) cites no vendor document")
        for k in keys:
            if k not in cites:
                out.append(f"line {i} cites {k!r}, which the template does not define")
        if not str(line.get("why") or "").strip():
            out.append(f"line {i} ({line.get('text', '')!r}) does not say why")
        for cond in _conditions(line):
            if not (_EQUALS.match(cond) or _IN.match(cond) or _KEY.match(cond)):
                out.append(f"line {i}'s condition {cond!r} is not <name>, <name> == <word> "
                           "or <word> in <name>")
    for k, c in sorted(cites.items()):
        c = c or {}
        if "measured" in c:
            missing = [f for f in MEASURED_FIELDS if not str(c.get(f) or "").strip()]
            if missing:
                out.append(f"measured citation {k!r} names no {', '.join(missing)}")
            continue
        missing = [f for f in CITATION_FIELDS if not str(c.get(f) or "").strip()]
        if missing:
            out.append(f"citation {k!r} names no {', '.join(missing)}")
        if not isinstance(c.get("verified"), bool):
            out.append(f"citation {k!r} does not say whether it was verified on the vendor's page")
    if t.get("support") == "unknown" and not t.get("support_why"):
        out.append("its support is unknown and it does not say why")
    from modules.sdn import openflow_cli
    uses = any("{ports.one_line}" in str(line.get("text") or "") for line in t.get("lines") or [])
    if t.get("port_set") is not None and t["port_set"] not in openflow_cli.PORT_SETS:
        out.append(f"its port_set {t['port_set']!r} is not one of "
                   f"{', '.join(sorted(openflow_cli.PORT_SETS))}")
    elif uses and t.get("port_set") is None:
        out.append("a line reads {ports.one_line} and the template names no port_set to "
                   "write it")
    return out


def citation_count(name: str) -> dict:
    """``{"lines", "cited", "citations", "verified", "measured"}`` for the report and the
    manual."""
    t = load(name)
    cites = t.get("citations") or {}
    return {"lines": len(t["lines"]), "cited": sum(1 for x in t["lines"] if x.get("cite")),
            "citations": len(cites), "verified": sum(1 for c in cites.values()
                                                     if (c or {}).get("verified") is True),
            "measured": sum(1 for c in cites.values() if "measured" in (c or {}))}


def _conditions(line: dict) -> list:
    when = line.get("when")
    if not when:
        return []
    return [str(c) for c in (when if isinstance(when, list) else [when])]


def _condition_keys(cond: str) -> list:
    for rx, group in ((_EQUALS, 1), (_IN, 2), (_KEY, 1)):
        m = rx.match(cond)
        if m:
            return [m.group(group)]
    return []


def profile_keys(t: dict) -> list:
    """Every ``profile.<path>`` template *t* reads (its conditions and placeholders), sorted:
    what its platform profile's entry must hold."""
    keys = set()
    for line in t.get("lines") or []:
        for cond in _conditions(line):
            keys.update(k for k in _condition_keys(cond) if k.startswith("profile."))
        keys.update(k for k in _PLACE.findall(str(line.get("text") or ""))
                    if k.startswith("profile."))
    return sorted(keys)


def _holds(cond: str, v: dict):
    """Whether *cond* holds on *v*: True, False, or None when it reads a ``state.`` value not
    given (the plan did not compare the switch's state)."""
    keys = _condition_keys(cond)
    if keys and keys[0].startswith("state.") and keys[0] not in v:
        return None
    m = _EQUALS.match(cond)
    if m:
        got = v.get(m.group(1))
        return ("null" if got is None else str(got)) == m.group(2)
    m = _IN.match(cond)
    if m:
        return m.group(1) in (v.get(m.group(2)) or [])
    return bool(_lookup(v, cond.strip()))


# --------------------------------------------------------------------------- rendering

def derived(values: dict) -> dict:
    """*values* with the family-specific words the templates use, each from one NetBox value:
    the controller's host in an OVS target (an IPv6 address in brackets), OVSDB's protocol
    name, ArubaOS-Switch's version and fail-mode words, Comware's address family keyword, and
    the controller's id on the switch (Mercury configures one controller: 1)."""
    import ipaddress
    v = dict(values or {})
    addr = v.get("controller.address")
    if addr:
        six = ipaddress.ip_address(addr).version == 6
        v["controller.host"] = f"[{addr}]" if six else addr
        v["controller.family"] = "ipv6" if six else "ipv4"
        v["comware.family"] = "ipv6" if six else "ip"
    v.setdefault("controller.id", "1")
    version = v.get("openflow.version")
    if version in ("1.0", "1.3"):
        v["openflow.ovs_protocol"] = {"1.0": "OpenFlow10", "1.3": "OpenFlow13"}[version]
        # `version 1.3` (not `1.3 only`): what the lab's K.16.02 switch runs and negotiates
        # 1.3 with, as its running configuration prints it, so the hand-built switch plans as
        # no change; it offers 1.0 and 1.3, the profile's versions.
        v["aos_s.version"] = {"1.0": "1.0", "1.3": "1.3"}[version]
    mode = v.get("openflow.fail_mode")
    if mode in ("secure", "standalone"):
        v["aos_s.fail_mode"] = f"fail-{mode}"
    return v


def _lookup(values: dict, key: str):
    return values.get(key)


def entry_for(t: dict, selected=None) -> tuple:
    """``(entry, profile name, error)``: the platform profile entry template *t* renders with.
    *selected* is `profile.select`'s answer for the switch; given none, the profile covering
    the template's drivers is used when it has exactly one entry."""
    from modules.platforms import profile as P
    drivers = list(t.get("drivers") or [])
    if selected is not None:
        if not selected.get("ok"):
            return None, "", (f"no platform profile entry covers this switch: "
                              f"{selected.get('error') or 'none was selected'}")
        theirs = P.load(selected["profile"]).get("drivers") or []
        if not set(theirs) & set(drivers):
            return None, "", (f"the selected profile {selected['profile']} is for "
                              f"{', '.join(theirs)}, and the {t.get('name')} template is for "
                              f"{', '.join(drivers)}")
        return selected["entry"], selected["profile"], ""
    found = sorted({P.for_driver(d) for d in drivers} - {None})
    if not found:
        return None, "", (f"no platform profile covers {t.get('family')} "
                          f"({', '.join(drivers)}): add one under modules/platforms/profiles/")
    doc = P.load(found[0])
    bad = P.problems(doc)
    if bad:
        return None, found[0], (f"the platform profile {found[0]} cannot be used: "
                                + "; ".join(bad))
    if len(doc["entries"]) != 1:
        ranges = ", ".join(P.range_words(e["os"]) for e in doc["entries"])
        return None, found[0], (f"the platform profile {found[0]} has {len(doc['entries'])} "
                                f"entries ({ranges}): the switch's own OS version selects one "
                                "(profile.select)")
    return doc["entries"][0], found[0], ""


def _flatten(node, prefix: str) -> dict:
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            out.update(_flatten(value, f"{prefix}.{key}"))
        return out
    return {prefix: node}


def numbering_problems(values: dict, entry: dict) -> list:
    """Where NetBox's OpenFlow port numbers disagree with how the switch numbers its ports
    (the profile's `port_numbering`): on `interface_number`, a port named with one number
    (Ethernet18) is that number; on `port_number`, a port named by its number (2) is it. A name
    the rule cannot read (Ethernet1/1) is not judged. `add_order` asks nothing here: the number
    is requested, and the template refuses a port without one."""
    mode = (entry.get("openflow") or {}).get("port_numbering")
    out = []
    for port, number in sorted(((values or {}).get("port.openflow_port") or {}).items()):
        own = numbered_by_platform(port, mode)
        if own is not None and own != int(number):
            out.append(f"{port}'s openflow_port is {number}, and this platform numbers an "
                       f"OpenFlow port by its {mode.replace('_', ' ')} ({own})")
    return out


def numbered_by_platform(port: str, mode) -> object:
    """The OpenFlow port number the platform's own numbering gives *port* (the profile's
    `port_numbering`), or None where the rule cannot read it: on `interface_number`, a port
    named with one number (Ethernet18 is 18); on `port_number`, a port named by its number (2
    is 2); `add_order` gives none (the number is requested, NetBox's `openflow_port`)."""
    if mode == "interface_number":
        m = re.fullmatch(r"[A-Za-z-]*?([0-9]+)", str(port or ""))
    elif mode == "port_number":
        m = re.fullmatch(r"([0-9]+)", str(port or ""))
    else:
        return None
    return int(m.group(1)) if m else None


def takes(values: dict, entry: dict) -> tuple:
    """``([{"port", "why"}], error)``: every port the switch's OpenFlow instance takes, by the
    profile's `instance_takes` (C2588): the ports NetBox tags ``openflow``, and on a
    `vlan_members` platform every port carrying the instance's member VLAN as well, named or
    not (``openflow.vlan_members``, from `openflow_values`)."""
    from modules.platforms import profile as P
    mode = P.value(entry, "openflow.instance_takes")
    if mode is P.ABSENT:
        return [], ("the platform profile's entry does not say which ports its OpenFlow "
                    "instance takes (openflow.instance_takes), so the ports it would hand the "
                    "controller cannot be named: nothing is rendered")
    out = [{"port": p, "why": "tagged openflow in NetBox"} for p in values.get("ports") or []]
    if mode == "vlan_members":
        vlan = values.get("openflow.vlan") or ""
        members = values.get("openflow.vlan_members")
        if vlan and not isinstance(members, dict):
            return out, (f"the instance takes every port carrying VLAN {vlan}, and the values do "
                         "not say which ports carry it (openflow.vlan_members): nothing is "
                         "rendered")
        named = {t["port"] for t in out}
        out += [{"port": p, "why": f"{how} in VLAN {vlan}, the instance's member VLAN, so the "
                                   "switch makes it an OpenFlow port though NetBox does not tag "
                                   "it openflow"}
                for p, how in sorted((members or {}).items()) if p not in named]
    return out, ""


def port_set(t: dict, v: dict) -> tuple:
    """``(text, "")``: every OpenFlow port of *v* as the one value ``{ports.one_line}``, by
    template *t*'s ``port_set`` writer (`openflow_cli.PORT_SETS`); ``("", why)`` for a set the
    writer has no evidenced one-line form for, naming the ports, the forms it writes and what
    is wrong with this set. ``("", "")`` for a template with no ``port_set`` and for no ports
    (said as the missing value ``ports``)."""
    from modules.sdn import openflow_cli
    ports = [str(p) for p in v.get("ports") or []]
    if not t.get("port_set") or not ports:
        return "", ""
    write, line, forms = openflow_cli.PORT_SETS[t["port_set"]]
    text, why = write(ports)
    if why:
        return "", (f"{v.get('switch.name') or 'the switch'}'s OpenFlow ports are "
                    f"{', '.join(ports)}, and the {t.get('name')} template sends them all in "
                    f"{line}, which Mercury writes only as {forms}: {why}. How the platform "
                    "writes any other set in one line has not been read from a switch, so "
                    "nothing is rendered")
    return text, ""


def render(name: str, values: dict, selected=None) -> dict:
    """Template *name* with *values*: ``{"ok", "lines": [{"text", "cite", "why"}], "program",
    "error", "missing", "notes", "profile"}``. ``program`` is what would be sent: for
    ``ovs-vsctl`` one invocation, the lines joined by ``" -- "`` after ``sudo -n ovs-vsctl``;
    for ``cli`` the lines. *selected* is `profile.select`'s answer for the switch (see
    `entry_for`). Sends nothing."""
    from modules import protected
    from modules.platforms import profile as P
    from modules.sdn import openflow_values
    t = load(name)
    out = {"ok": False, "name": name, "family": t.get("family", ""), "form": t.get("form"),
           "lines": [], "program": [], "error": "", "missing": [], "notes": [], "profile": "",
           # Each management interface left out of the OpenFlow ports, by name and why
           # (`openflow_values.management_reason`): said, never silent.
           "excluded": list((values or {}).get("excluded") or []),
           # Every port the instance takes, each with why (`takes`): the preview names them all.
           "takes": []}
    bad = problems(t)
    if bad:
        out["error"] = f"the {name} template is refused: " + "; ".join(bad)
        return out
    if t.get("support") == "unknown":
        out["error"] = (f"{t.get('family')}'s OpenFlow support is UNKNOWN: {t['support_why']}. "
                        "Nothing is rendered.")
        return out
    entry, out["profile"], why = entry_for(t, selected)
    if why:
        out["error"] = why
        return out
    absent = [k for k in profile_keys(t) if P.value(entry, k[len("profile."):]) is P.ABSENT]
    if absent:
        out["error"] = (f"the {name} template reads {', '.join(absent)}, which the platform "
                        f"profile {out['profile']}'s entry {entry.get('os')} does not hold: "
                        "nothing is rendered")
        return out
    v = derived(values)
    v.update(_flatten(entry.get("openflow") or {}, "profile.openflow"))
    why = _supports(t, v, entry) or "; ".join(numbering_problems(v, entry))
    if why:
        out["error"] = why
        return out
    # B (modules/protected.py): every port the switch's OpenFlow instance will take, named in
    # the preview, and none of them protected (C2588, C2589).
    out["takes"], why = takes(v, entry)
    why = why or protected.ports_refusal(v.get("switch.name") or name, out["takes"],
                                         v.get("protected.objects"))
    if why:
        out["error"] = why
        return out
    # Every port in one value, for a template that sends its port set in one line (C2996).
    one_line, why = port_set(t, v)
    if why:
        out["error"] = why
        return out
    if one_line:
        v["ports.one_line"] = one_line
    lines, missing = [], []
    for line in t["lines"]:
        held = [_holds(c, v) for c in _conditions(line)]
        if None in held:
            out["notes"].append(f"{line['text'].strip()!r} is decided against the switch's "
                                "present state, and none was given: left out")
            continue
        if not all(held):
            continue
        items = [None]
        if line.get("each"):
            items = list(v.get(line["each"]) or [])
            if not items:
                missing.append(line["each"])
                continue
        for item in items:
            text, reason = line["text"], str(line.get("why") or "")
            for key in sorted(set(_PLACE.findall(text)) | set(_PLACE.findall(reason))):
                if key == "port":
                    got = item
                elif key.startswith("port."):
                    got = (v.get(key) or {}).get(item) if isinstance(v.get(key), dict) else None
                else:
                    got = _lookup(v, key)
                if got in (None, "", []):
                    # The one-line value is absent only when its input is: said as `ports`.
                    missing.append("ports" if key == "ports.one_line" else key)
                    continue
                text = text.replace("{" + key + "}", str(got))
                reason = reason.replace("{" + key + "}", str(got))
            for part in text.split("\n"):
                if part.strip():
                    lines.append({"text": part, "cite": list(line["cite"]), "why": reason})
    if missing:
        names_ = sorted(set(missing))
        out["missing"] = names_
        out["error"] = "the render is refused: " + "; ".join(
            f"{k} is not given ({openflow_values.WHERE.get(k, 'derived from another value')})"
            for k in names_)
        return out
    out["lines"] = lines
    if t["form"] == "ovs-vsctl":
        from modules.sdn import ovs
        out["program"] = [" ".join(ovs.SUDO_VSCTL) + " " + " -- ".join(x["text"] for x in lines)]
    else:
        out["program"] = [x["text"] for x in lines]
    out["ok"] = True
    return out


def _supports(t: dict, v: dict, entry: dict) -> str:
    """Why the template cannot carry these values (both operands named), or ``""``. The
    versions are the platform profile entry's (what the release offers, C2598)."""
    import ipaddress
    family = t.get("family")
    version, transport = v.get("openflow.version"), v.get("openflow.transport")
    offered = list((entry.get("openflow") or {}).get("versions") or [])
    if version and version not in offered:
        return (f"{family} {_range(entry)} offers OpenFlow {', '.join(offered) or 'none'} by its "
                f"platform profile, and NetBox gives version {version}: nothing is rendered")
    if transport and transport not in (t.get("transports") or []):
        return (f"the {t['name']} template renders transport "
                f"{', '.join(t.get('transports') or []) or 'none'}, and NetBox gives {transport}: "
                "nothing is rendered")
    addr = v.get("controller.address")
    if addr and ipaddress.ip_address(addr).version == 6 and not t.get("ipv6_controller"):
        return (f"{family}'s controller address is IPv4 in its vendor's document (an IPv6 "
                f"controller is not documented), and NetBox gives {addr}: nothing is rendered")
    shape = t.get("instance_shape")
    inst = str(v.get("openflow.instance") or "")
    if shape == "number" and inst and not re.fullmatch(r"[0-9]{1,4}", inst):
        return (f"{family}'s OpenFlow instance is a number, and NetBox gives {inst!r}: nothing "
                "is rendered")
    return ""


def _range(entry: dict) -> str:
    from modules.platforms import profile as P
    try:
        return P.range_words(entry.get("os") or {})
    except KeyError:
        return ""


# --------------------------------------------------------------------------- draft or confirmed

def _repo(network: str) -> str:
    from modules.nsot import listref
    return listref.resolve(network).repo_dir


def confirmation(network: str, name: str):
    """*network*'s committed confirmation of template *name* (read at HEAD), or None."""
    import yaml
    from modules.nsot.repo import git
    rc, text, _err = git(_repo(network), "show", f"HEAD:{DIR}/{name}.yml")
    if rc != 0:
        return None
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return doc if isinstance(doc, dict) else None


def status(network: str, name: str) -> dict:
    """``{"status", "capture", "why"}``: ``confirmed`` only when *network* holds a confirmation
    bound to this template's current SHA-256; else ``draft``, saying why."""
    sha = sha256(name)
    c = confirmation(network, name)
    if c is None:
        return {"status": DRAFT, "capture": "", "why": f"{network} has not confirmed it"}
    if c.get("template_sha256") != sha:
        return {"status": DRAFT, "capture": c.get("capture", ""),
                "why": (f"it was confirmed at {str(c.get('template_sha256'))[:12]}, and the "
                        f"template is now {sha[:12]}: confirm it again")}
    return {"status": CONFIRMED, "capture": c.get("capture", ""), "why": "",
            "by": c.get("actor", ""), "at": c.get("at", "")}


def push_refusal(network: str, name: str) -> str:
    """``""`` only when template *name* is CONFIRMED on *network*; otherwise why nothing of it
    may be sent, naming the template and its status. Every path that sends a template's lines
    asks this first."""
    s = status(network, name)
    if s["status"] == CONFIRMED:
        return ""
    return (f"REFUSED: the {name} OpenFlow template is {s['status']} on {network} ({s['why']}), "
            "and only a confirmed template is ever sent: confirm it against a saved capture "
            "of one of its devices first. Nothing was sent.")


def confirm(network: str, name: str, capture_name: str, actor: str, actor_verified: str,
            template_sha256: str = None, capture_sha256: str = None) -> dict:
    """A verified person confirms template *name* on *network* against *capture_name* (one of
    `discovery.captures`, of a device whose driver the template is for): committed as that
    person. ``{"ok", "error", "path", "commit"}``. *template_sha256* and *capture_sha256*, when
    given, are what the person read (SDN › Switches' preview): a template or capture that is
    not that one now is refused, naming both, and nothing is committed."""
    import time
    import yaml
    from modules import discovery
    from modules.nsot import repo as R

    if not actor or actor_verified in ("", "none"):
        return {"ok": False, "error": "a template is confirmed by a verified person"}
    t = load(name)
    cap = discovery.capture(network, capture_name)
    if cap is None:
        return {"ok": False, "error": f"{network} holds no capture named {capture_name!r}"}
    if cap["driver"] not in (t.get("drivers") or []):
        return {"ok": False, "error": (f"the capture {capture_name!r} was read with "
                                       f"{cap['driver']}, and the {name} template is for "
                                       f"{', '.join(t.get('drivers') or [])}")}
    if cap.get("archived"):
        return {"ok": False, "error": f"the capture {capture_name!r} is archived: read it again"}
    for what, given, now in (("template", template_sha256, sha256(name)),
                             ("capture", capture_sha256, cap.get("sha256", ""))):
        if given is not None and given != now:
            return {"ok": False, "moved": True,
                    "error": (f"the {what} you read hashed {str(given)[:12] or 'none'}, and it "
                              f"hashes {str(now)[:12] or 'none'} now: nothing was committed; "
                              "read it again")}
    rel = f"{DIR}/{name}.yml"
    doc = {"template": name, "template_sha256": sha256(name), "capture": capture_name,
           "capture_sha256": cap.get("sha256", ""), "device": cap["device"],
           "actor": actor, "actor_verified": actor_verified,
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    repo = _repo(network)
    from modules.filestore import write_atomic
    with R.repo_lock(repo):
        os.makedirs(os.path.join(repo, DIR), exist_ok=True)
        write_atomic(os.path.join(repo, rel), yaml.safe_dump(doc, sort_keys=False))
        got = R._commit_paths(network, [rel],                                  # noqa: SLF001
                              f"OpenFlow template confirmed: {name} against {capture_name}",
                              [f"Actor: {actor}", f"Actor-Verified: {actor_verified}"],
                              "openflow-template")
    if not got.get("ok"):
        return {"ok": False, "error": f"the confirmation's commit failed: {got.get('error')}",
                "path": rel}
    return {"ok": True, "error": "", "path": rel, "commit": got.get("commit", "")}
