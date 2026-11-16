"""A command plan: one structured document naming a device change Mercury runs on the deploy
pipeline's engine (C3757, path 2; the operator's design, 2026-11-15). Its runner is
`modules/nsot/command_plan_run.py`; Mercury's rule for its raw lines is
`modules/nsot/command_policy.py`.

**The template** (``kind: command_plan``), data, never code: its ``key``, ``title`` and
``words``; ``net_zero: true`` (a transient plan, a bounce or a clear: the running configuration
after it equals the one before it, line for line, or it is rolled back and refused; the
operator, 2026-11-15: "transient command plans are outside Mode B because they are net-zero";
a lasting change goes through intent, where Mode B applies); its typed ``parameters``; its
``preconditions`` (each a read through Mercury's read engine with ``expect_line`` or
``expect``: all must hold, re-read at apply, or the plan refuses with nothing sent); its
``steps`` (``mode: config`` and the ``commands``, each parameter a ``{name}`` placeholder); its
``verify`` (each a read with ``expect_line`` or ``expect``, read every ``poll`` until it holds
``within`` a bound, or once ``after`` a wait; each bound a name declared in
`modules/waits.py`'s `PLAN_BOUNDS`); its ``reason`` (the authorisation of any line the
pipeline's gate holds dangerous, in the hash); and ``on_finish``, a named hook of Mercury's (a
notification). Built-in templates ship with Mercury under `BUILTIN_DIR`.

**Parameters are typed and validated against Mercury's model** (`validate`), never taken as
text: ``device`` (a device of the network's inventory, its config dialect known); ``interface``
(on the device's committed intent; ``access_port``: its switchport mode access;
``not_management``: never an interface on the path Mercury manages the device through, read
from its golden: the interface holding its management address, IPv4 or IPv6, or addressed by
DHCP, or an access port in the VLAN whose interface holds it); ``choice`` (one of ``of``).
Mercury substitutes the VALIDATED value of each (an interface in its canonical name), never a
string an AI or a person wrote; a derived ``{<name>_short}`` gives an interface's short form to
reads and expectations.

**`expect_line`** is a line pattern: the read's answer must hold a line equal to it, spaces
collapsed, each ``*`` matching anything, each placeholder its validated value matched as text.
**`expect`** names one of Mercury's own checks (`NAMED_CHECKS`, a fixed table in code; never a
dotted name a template resolves), each answering pass, fail or unreadable with its words; a
check that can also be judged from Mercury's records alone (a golden) is judged at preview too.

**The preview** (`preview`) asks no device: the template parsed, the parameters validated, the
policy held, the program rendered, the hash computed over everything it binds (the template's
digest, the network, the device, the values, the program, the authorisation's reason, the
checks by name and read, the bounds), and everything drawn masked. Writes nothing.
"""

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

KIND = "command_plan"
BUILTIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "command_plans")
FIELDS = ("kind", "key", "title", "words", "net_zero", "parameters", "preconditions", "steps",
          "verify", "reason", "on_finish", "fixes")
REQUIRED = ("kind", "key", "title", "words", "parameters", "steps", "reason")
#: ``subscription`` (2026-11-16, the lost stream's ladder, rung 2): a telemetry subscription the
#: device's committed intent declares. It derives ``{<name>_each}``, EVERY subscription intent
#: sends to the same receiver (address and port) as the one named, in intent's order (the
#: review of 2026-11-16: subscriptions to one receiver share one connection, so all of them
#: are reset in one batch, or the connection survives), and ``{<name>_each_lines}``, each
#: one's lines exactly as intent renders them under its header (`templates/cisco_iosxe/
#: base.j2`). A command naming ``{<name>_each}`` is repeated for each of them; a whole
#: indented ``{<name>_each_lines}`` right after it repeats with it (`program`).
PARAM_TYPES = ("device", "interface", "choice", "subscription")
_SUB_ID = re.compile(r"[0-9]{1,10}\Z")
_KEY = re.compile(r"[a-z][a-z0-9-]{1,48}\Z")
_NAME = re.compile(r"[a-z][a-z0-9_]{0,30}\Z")
_IFNAME = re.compile(r"[A-Za-z][A-Za-z-]{0,30}[0-9][0-9/.:]{0,15}\Z")
_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}\Z")
_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]{0,40})\}")
#: Names a parameter never takes: a run's post carries them beside its values (`saved_plans_v2.
#: device_run`, `fixit_v2.fix_with_script`).
RESERVED_PARAMS = ("key", "hash", "view", "list")
#: How many of each a template holds at most.
MOST = {"preconditions": 8, "verify": 6, "commands": 20, "choices": 12}

#: Mercury's own checks a template's ``expect`` names: name -> (module, apply function,
#: preview function or None). Data in code; a template names one of these, nothing else.
NAMED_CHECKS = {
    "errdisable.port_listed": ("modules.heal.errdisable", "check_port_listed", None),
    "errdisable.port_not_listed": ("modules.heal.errdisable", "check_port_not_listed", None),
    "errdisable.port_connected": ("modules.heal.errdisable", "check_port_connected", None),
    # The declared on/off pair's precondition (C1, 2026-11-16: net-zero only from a port up).
    "errdisable.port_not_admin_down": ("modules.heal.errdisable", "check_port_not_admin_down",
                                       None),
    "errdisable.not_recovering_itself": ("modules.heal.errdisable", "check_no_recovery",
                                         "preview_no_recovery"),
    "errdisable.cause_cleared": ("modules.heal.errdisable", "check_cause_cleared", None),
    # The lost stream's ladder, rungs 2 and 3 (the operator, 2026-11-16; modules/fixit/ladder.py;
    # modules/heal/stream_checks.py: the re-subscribe's own checks, the baseline read first).
    "telemetry.read_before": ("modules.heal.stream_checks", "check_read_before", None),
    "telemetry.stream_back": ("modules.heal.stream_checks", "check_stream_back", None),
    "telemetry.collector_not_receiving": ("modules.heal.stream_checks",
                                          "check_collector_not_receiving", None),
    "telemetry.netconf_yang_on": ("modules.heal.stream_checks", "check_netconf_yang_on", None),
    "telemetry.dmi_others_off": ("modules.heal.stream_checks", "check_dmi_others", None),
    "telemetry.iosxe": ("modules.heal.stream_checks", "check_iosxe", None),
    "telemetry.subscription_as_intent": ("modules.heal.stream_checks",
                                         "check_subscription_as_intent", None),
}
#: The hooks a template's ``on_finish`` names: name -> (module, function).
FINISH_HOOKS = {"errdisable.notify": ("modules.heal.errdisable", "on_finish")}


class Refused(ValueError):
    """Nothing was previewed or run; ``code`` names the check."""

    def __init__(self, code: str, words: str):
        super().__init__(words)
        self.code = code


@dataclass(frozen=True)
class Template:
    key: str
    title: str
    words: str
    net_zero: bool
    parameters: dict
    preconditions: tuple
    commands: tuple
    verify: tuple
    reason: str
    on_finish: str
    digest: str
    doc: dict = field(repr=False, compare=False, default_factory=dict)
    #: The problem conditions it fixes (`modules/problem.py`): what an investigation that
    #: lacked it is restarted on once it exists (C3733, `ai.missing.available`).
    fixes: tuple = ()


def _digest(doc) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"),
                                     default=str).encode("utf-8")).hexdigest()[:16]


def _text(doc: dict, name: str, most: int = 400) -> str:
    v = doc.get(name)
    if not isinstance(v, str) or not v.strip() or len(v) > most or not v.isprintable():
        raise Refused("template", f"a command plan's {name} is text of 1 to {most} printable "
                                  "characters")
    return v.strip()


def _check_item(item, where: str, params: tuple, *, verify: bool) -> dict:
    from modules.waits import PLAN_BOUNDS

    if not isinstance(item, dict):
        raise Refused("template", f"{where} is an object")
    allowed = {"name", "read", "expect", "expect_line"} | (
        {"poll", "within", "after"} if verify else set())
    extra = sorted(set(item) - allowed)
    if extra:
        raise Refused("template", f"{where} takes {', '.join(sorted(allowed))}, and also gives "
                                  f"{', '.join(extra)}")
    if ("expect" in item) == ("expect_line" in item):
        raise Refused("template", f"{where} gives exactly one of expect and expect_line")
    if "expect" in item and item["expect"] not in NAMED_CHECKS:
        raise Refused("template", f"{where}'s expect names {item['expect']!r}, which is not one "
                                  f"of Mercury's checks ({', '.join(sorted(NAMED_CHECKS))})")
    if "expect_line" in item and "read" not in item:
        raise Refused("template", f"{where}'s expect_line needs the read it is matched in")
    out = {"name": _text(item, "name", 80), "read": "", "expect": item.get("expect", ""),
           "expect_line": item.get("expect_line", "")}
    if "read" in item:
        out["read"] = _text(item, "read", 120)
    for text in (out["read"], out["expect_line"]):
        stray = sorted(set(_PLACEHOLDER.findall(text)) - set(_names(params)))
        if stray:
            raise Refused("template", f"{where} names {', '.join(stray)}, not a parameter")
    if verify:
        bounds = [k for k in ("within", "after") if k in item]
        if len(bounds) != 1:
            raise Refused("template", f"{where} gives exactly one of within and after")
        for k in ("poll", "within", "after"):
            if k in item and item[k] not in PLAN_BOUNDS:
                raise Refused("template", f"{where}'s {k} names {item[k]!r}, which is not a "
                                          "bound declared in modules/waits.py (PLAN_BOUNDS)")
        if "within" in item and "poll" not in item:
            raise Refused("template", f"{where} polls within a bound, and names no poll")
        out.update({k: item[k] for k in ("poll", "within", "after") if k in item})
    return out


def _names(params) -> list:
    """Each placeholder a template may use: its parameters, and an interface's short form."""
    out = []
    for name, spec in (params if isinstance(params, dict) else dict(params)).items():
        out.append(name)
        if spec.get("type") == "interface":
            out.append(f"{name}_short")
    return out


def command_names(params) -> list:
    """Each placeholder a template's COMMANDS may use: its parameters, and a subscription's
    receiver group (``{<name>_each}``, ``{<name>_each_lines}``: whole lines only)."""
    out = []
    for name, spec in (params if isinstance(params, dict) else dict(params)).items():
        out.append(name)
        if spec.get("type") == "subscription":
            out += [f"{name}_each", f"{name}_each_lines"]
    return out


def parse(doc) -> Template:
    """*doc* (a template, as loaded) held to the schema, or raises `Refused` naming what is
    wrong. Reads nothing."""
    from modules.nsot import command_policy

    if not isinstance(doc, dict):
        raise Refused("template", "a command plan is an object")
    extra = sorted(set(doc) - set(FIELDS))
    missing = [f for f in REQUIRED if f not in doc]
    if extra or missing:
        raise Refused("template", "a command plan takes " + ", ".join(FIELDS)
                      + (f"; it also gives {', '.join(extra)}" if extra else "")
                      + (f"; it gives no {', '.join(missing)}" if missing else ""))
    if doc["kind"] != KIND:
        raise Refused("template", f"a command plan's kind is {KIND}")
    key = _text(doc, "key", 50)
    if not _KEY.match(key):
        raise Refused("template", "a command plan's key is lower-case letters, digits and -")
    if doc.get("net_zero") is not True:
        raise Refused("template", "only a net-zero (transient) command plan runs today: "
                                  "net_zero is true; a lasting change goes through intent")
    params = doc["parameters"]
    if not isinstance(params, dict) or "device" not in params:
        raise Refused("template", "a command plan's parameters are an object naming device")
    held = {}
    for name, spec in params.items():
        if not isinstance(name, str) or not _NAME.match(name) or not isinstance(spec, dict):
            raise Refused("template", f"parameter {name!r} is a lower-case name and an object")
        if name in RESERVED_PARAMS:
            # A run's post carries these beside the values (C4, 2026-11-16).
            raise Refused("template", f"a parameter is never named {name}: "
                                      f"{', '.join(RESERVED_PARAMS)} are the run's own fields")
        t = spec.get("type")
        if t not in PARAM_TYPES:
            raise Refused("template", f"parameter {name}'s type is one of "
                                      f"{', '.join(PARAM_TYPES)}")
        keys = {"type", "words"} | ({"access_port", "not_management"} if t == "interface"
                                    else {"of"} if t == "choice" else set())
        # (a subscription takes its type and words alone)
        if set(spec) - keys:
            raise Refused("template", f"parameter {name} ({t}) takes {', '.join(sorted(keys))}")
        if (name == "device") != (t == "device"):
            raise Refused("template", "the device parameter, and only it, is of type device")
        if t == "choice":
            of = spec.get("of")
            if (not isinstance(of, list) or not 1 <= len(of) <= MOST["choices"]
                    or not all(isinstance(c, str) and _NAME.match(c.replace("-", "_"))
                               for c in of)):
                raise Refused("template", f"parameter {name}'s of is 1 to {MOST['choices']} "
                                          "choices, each a lower-case word")
        held[name] = dict(spec)
    steps = doc["steps"]
    if (not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], dict)
            or set(steps[0]) != {"mode", "commands"} or steps[0]["mode"] != "config"):
        raise Refused("template", "a command plan has one step, {mode: config, commands}")
    commands = steps[0]["commands"]
    if (not isinstance(commands, list) or not 1 <= len(commands) <= MOST["commands"]
            or not all(isinstance(c, str) and c.strip() and c.isprintable() and c.isascii()
                       for c in commands)):
        raise Refused("template", f"a step's commands are 1 to {MOST['commands']} printable "
                                  "ASCII lines")
    # Mercury's rule for raw lines, on the template itself: a refused word, an object not a
    # parameter, a placeholder naming no parameter (each refused whatever the dialect).
    for raw, _shape in command_policy.shapes(commands):
        w, obj = command_policy.refused_word(raw), command_policy.literal_object(raw)
        if w or obj:
            raise Refused("policy", command_policy.check("cisco_ios", [raw], held)["refusals"][0])
    stray = sorted({p for c in commands for p in _PLACEHOLDER.findall(c)}
                   - set(command_names(held)))
    if stray:
        raise Refused("template", f"the commands name {', '.join(stray)}, not a parameter")
    for n, c in enumerate(commands):
        lines_of = [p for p in _PLACEHOLDER.findall(c) if p.endswith("_each_lines")]
        if lines_of and (c.strip() != "{" + lines_of[0] + "}" or not c[:1].isspace()
                         or n == 0 or "{" + lines_of[0][:-len("_lines")] + "}"
                         not in commands[n - 1]):
            raise Refused("template", f"{{{lines_of[0]}}} is a whole indented line of its own, "
                                      f"right after the line naming its subscription: `{c}`")
    pre = doc.get("preconditions") or []
    ver = doc.get("verify") or []
    if not isinstance(pre, list) or len(pre) > MOST["preconditions"]:
        raise Refused("template", f"preconditions are at most {MOST['preconditions']}")
    if not isinstance(ver, list) or not 1 <= len(ver) <= MOST["verify"]:
        raise Refused("template", f"verify is 1 to {MOST['verify']} reads")
    pre_t = tuple(_check_item(p, f"precondition {n}", held, verify=False)
                  for n, p in enumerate(pre, 1))
    ver_t = tuple(_check_item(v, f"verify {n}", held, verify=True) for n, v in enumerate(ver, 1))
    finish = doc.get("on_finish") or ""
    if finish and finish not in FINISH_HOOKS:
        raise Refused("template", f"on_finish names {finish!r}, not one of Mercury's hooks")
    fixes = doc.get("fixes") or []
    from modules.problem import CONDITIONS
    if not isinstance(fixes, list) or any(f not in CONDITIONS for f in fixes):
        raise Refused("template", "fixes names the problem conditions the plan fixes "
                                  "(modules/problem.py's), as a list")
    return Template(key=key, title=_text(doc, "title", 160), words=_text(doc, "words", 600),
                    net_zero=True, parameters=held, preconditions=pre_t,
                    commands=tuple(commands), verify=ver_t, reason=_text(doc, "reason", 400),
                    on_finish=finish, digest=_digest(doc), doc=dict(doc), fixes=tuple(fixes))


_BUILTIN = {}


def builtin() -> dict:
    """The command plans that ship with Mercury, by key (`BUILTIN_DIR`, one YAML file each,
    its file named for its key), parsed once. A file that does not parse raises: a shipped
    template is held by the tests."""
    if not _BUILTIN:
        import yaml

        for name in sorted(os.listdir(BUILTIN_DIR)):
            if not name.endswith(".yml"):
                continue
            with open(os.path.join(BUILTIN_DIR, name), encoding="utf-8") as fh:
                t = parse(yaml.safe_load(fh))
            if f"{t.key}.yml" != name:
                raise Refused("template", f"{name} holds the plan {t.key}")
            _BUILTIN[t.key] = t
    return dict(_BUILTIN)


def template_of(key) -> Template:
    """The command plan *key*: one that ships with Mercury (`builtin`), else one a person saved
    from a verified run (`saved_plans`: a self-heal script or a reusable action, each its own
    key), each held to this schema and Mercury's rule for raw lines when it was saved."""
    plans = builtin()
    if isinstance(key, str) and key not in plans:
        from modules.nsot import saved_plans
        plans = dict(plans, **saved_plans.templates())
    if not isinstance(key, str) or key not in plans:
        raise Refused("not_a_plan", f"a command plan is one of Mercury's ({', '.join(plans)})")
    return plans[key]


# ── The parameters: their shapes (no reads), then Mercury's model ───────────────────────────

def shape_refusal(spec: dict, value) -> str:
    """What *value* is instead of *spec*'s shape, or ``""``. Reads nothing."""
    t = spec.get("type")
    if not isinstance(value, str):
        return "not text"
    if t == "device":
        return "" if _HOST.match(value) else "not a device's name"
    if t == "interface":
        return "" if _IFNAME.match(value) else "not an interface's name"
    if t == "choice":
        return "" if value in (spec.get("of") or []) else f"not one of {', '.join(spec['of'])}"
    if t == "subscription":
        return "" if _SUB_ID.match(value) else "not a subscription id of 1 to 10 digits"
    return "of no type"


def checked(t: Template, values) -> dict:
    """*values* held to *t*'s parameters by shape: exactly its names, each of its shape; or
    raises `Refused`. Reads nothing (the catalog's schema check uses this)."""
    names = list(t.parameters)
    if not isinstance(values, dict):
        raise Refused("wrong_type", f"{t.key}'s parameters are an object giving "
                                    f"{', '.join(names)}")
    extra = [k for k in values if k not in names]
    if extra:
        raise Refused("unknown_parameter", f"{t.key} takes exactly {', '.join(names)}: a "
                                           "parameter it does not name is refused")
    missing = [n for n in names if n not in values]
    if missing:
        raise Refused("missing_parameter", f"{t.key} takes {', '.join(names)}, and no "
                                           f"{', '.join(missing)} was given")
    for n in names:
        why = shape_refusal(t.parameters[n], values[n])
        if why:
            takes = t.parameters[n].get("words") or t.parameters[n]["type"]
            raise Refused("wrong_shape", f"{t.key}'s parameter {n} is {takes}, and the value "
                                         f"given is {why}")
    return {n: values[n] for n in names}


class Sources:
    """Where a plan reads Mercury's model: the inventory, committed intent and the golden
    (each replaceable in a test)."""

    def __init__(self, network: str):
        self.network = network

    def device(self, host: str) -> dict:
        from modules import device_page
        from modules.nsot import listref

        try:
            _ref, dev = device_page.find_device(host, listref.resolve(self.network))
        except Exception:                             # noqa: BLE001 (no such device: refused)
            return {}
        return dev or {}

    def intent(self, host: str) -> tuple:
        from modules.neighbours import committed_intents_of

        intents, error = committed_intents_of(self.network)
        if error:
            return None, error
        return (intents or {}).get(host) or {}, ""

    def golden(self, host: str) -> tuple:
        from modules import prometheus_targets
        from modules.nsot import listref

        try:
            return prometheus_targets.read_golden(listref.resolve(self.network), host), ""
        except Exception as exc:                      # noqa: BLE001 (refused, said)
            return None, f"{type(exc).__name__}: {exc}"


def _intent_iface(intent: dict, name: str) -> dict:
    from modules.nsot import ifnames

    for iface in (intent or {}).get("interfaces") or []:
        if isinstance(iface, dict) and ifnames.same_interface(iface.get("name") or "", name):
            return iface
    return {}


def management_refusal(golden: str, mgmt_ip: str, iface: str, access_vlan: str = "",
                       mode: str = "") -> str:
    """Why *iface* is on the path Mercury manages the device through, read from its *golden*
    by THE reading Mode B and the heal share (`removal.management_refusal`), or ``""``."""
    from modules.nsot import removal

    return removal.management_refusal(removal._chains(golden or ""), mgmt_ip,  # noqa: SLF001
                                      iface, mode=mode, access_vlan=access_vlan)


def validate(network: str, t: Template, values, *, sources=None) -> dict:
    """*values* validated against Mercury's model (the module docstring): ``{"ok",
    "refusals", "values", "derived", "dialect", "device_row"}``, *values* each parameter's
    VALIDATED value (an interface canonical) and *derived* those plus each interface's short
    form, the only values substituted anywhere. Reads the inventory, committed intent and the
    golden; never a device."""
    from modules.nsot import ifnames
    from modules.nsot.platform import platform_for_device

    src = sources or Sources(network)
    out = {"ok": False, "refusals": [], "values": {}, "derived": {}, "dialect": "",
           "device_row": {}}
    try:
        held = checked(t, values)
    except Refused as exc:
        out["refusals"].append(str(exc))
        return out
    device = held["device"]
    dev = src.device(device)
    if not dev:
        out["refusals"].append(f"{device} is no device of {network}")
        return out
    out["device_row"] = dev
    out["dialect"] = platform_for_device(dev)
    intent = golden = None
    for name, spec in t.parameters.items():
        v = held[name]
        if spec["type"] == "interface":
            if intent is None:
                intent, err = src.intent(device)
                if intent is None:
                    out["refusals"].append(f"{device}'s committed intent could not be read "
                                           f"({err})")
                    return out
            iface = _intent_iface(intent, v)
            if not iface:
                out["refusals"].append(f"{device}'s committed intent holds no interface {v}: a "
                                       "command plan acts only on an interface Mercury's model "
                                       "has")
                continue
            canon = str(iface.get("name") or ifnames.canonical(v))
            if not _IFNAME.match(canon):
                # The name substituted is intent's: held to an interface's shape as the
                # parameter was, never trusted because intent holds it.
                out["refusals"].append(f"{device}'s committed intent names the interface in a "
                                       "shape that is not an interface's name")
                continue
            mode = str(iface.get("switchport_mode") or "")
            if spec.get("access_port") and mode != "access":
                out["refusals"].append(f"{canon} on {device} is {mode or 'no switchport'} in "
                                       "committed intent, and this plan acts only on an access "
                                       "port")
            if spec.get("not_management"):
                if golden is None:
                    golden, gerr = src.golden(device)
                    if golden is None:
                        out["refusals"].append(f"{device}'s golden could not be read ({gerr}), "
                                               "so whether the interface is the management "
                                               "path cannot be told")
                        continue
                why = management_refusal(golden, dev.get("ip", ""), canon,
                                         str(iface.get("switchport_access_vlan") or ""), mode)
                if why:
                    out["refusals"].append(why)
            out["values"][name] = canon
            out["derived"][name] = canon
            out["derived"][f"{name}_short"] = ifnames.abbreviate(canon)
        elif spec["type"] == "subscription":
            # One the device's committed intent declares; its lines are intent's, exactly as
            # the template renders them under its header, never typed (2026-11-16).
            if intent is None:
                intent, err = src.intent(device)
                if intent is None:
                    out["refusals"].append(f"{device}'s committed intent could not be read "
                                           f"({err})")
                    return out
            group, why = receiver_group(intent, v)
            if why:
                out["refusals"].append(f"{device}'s committed intent: {why}")
                continue
            out["values"][name] = v
            out["derived"][name] = v
            out["derived"][f"{name}_each"] = [s for s, _l in group]
            out["derived"][f"{name}_each_lines"] = {s: lines for s, lines in group}
        else:
            out["values"][name] = v
            out["derived"][name] = v
    out["ok"] = not out["refusals"]
    return out


# ── Rendering and the preview ───────────────────────────────────────────────────────────────

#: A line that would leave the subscription's section, or end configuration mode (the review of
#: 2026-11-16): never one of a subscription's lines.
_LEAVES = re.compile(r"^\s*(exit|end|quit)\b", re.I)


def subscription_lines(intent: dict, sub: str):
    """Subscription *sub*'s lines in *intent* (a device's committed host vars), stripped, in
    intent's order, as `templates/cisco_iosxe/base.j2` renders them under ``telemetry ietf
    subscription <sub>``; None when intent declares no such subscription."""
    for s in (intent or {}).get("telemetry") or []:
        if isinstance(s, dict) and str(s.get("subscription")) == str(sub):
            return [str(x).strip() for x in s.get("settings") or []]
    return None


def lines_refusal(sub: str, raw_lines) -> str:
    """Why subscription *sub*'s intent lines (*raw_lines*, as committed) cannot be sent under its
    header, or ``""``: none, a line not printable ASCII (a line break among them), a line that
    leaves the section (``exit``, ``end``, ``quit``), or a line naming another section's
    header (an object word, `command_policy.literal_object`, or the subscription header
    itself), which IOS would take at global level, leaving the section. Every rendered line is
    held to the rule's refused words at preview too, and the net-zero compare reads the rest."""
    from modules.nsot import command_policy

    raw = [str(x) for x in raw_lines or []]
    if not raw:
        return f"subscription {sub} holds no line"
    for x in raw:
        if not (x.isascii() and x.isprintable() and x.strip()):
            return f"subscription {sub} holds a line that is not printable ASCII text"
        if _LEAVES.match(x):
            return f"subscription {sub} holds `{x.strip()}`, which leaves its section"
        words = x.split()
        if (command_policy.literal_object(x) or command_policy.refused_word(x)
                or words[:3] == ["telemetry", "ietf", "subscription"]):
            return (f"subscription {sub} holds `{x.strip()}`, another section's line, which "
                    "would leave its section")
    return ""


def receiver_group(intent: dict, sub: str) -> tuple:
    """``([(id, lines)], why)``: every subscription *intent* sends to the receiver *sub* sends
    to (the same address and port, `diagnose_stream.receiver_of`), *sub* among them, in
    intent's order, each with its lines (`subscription_lines`, held by `lines_refusal`); or
    ``([], why)``."""
    from modules.heal.diagnose_stream import receiver_of

    declared = [(str(s.get("subscription")), s.get("settings") or [])
                for s in (intent or {}).get("telemetry") or [] if isinstance(s, dict)]
    mine = next((settings for s, settings in declared if s == str(sub)), None)
    if mine is None:
        return [], (f"it declares no telemetry subscription {sub} (it declares "
                    f"{', '.join(s for s, _x in declared) or 'none'})")
    rec = receiver_of(mine)
    if rec.get("why"):
        return [], f"subscription {sub}'s receiver is not known: {rec['why']}"
    out = []
    for s, settings in declared:
        r = receiver_of(settings)
        if r.get("why") or (r["address"], r["port"]) != (rec["address"], rec["port"]):
            continue
        why = lines_refusal(s, settings)
        if why:
            return [], why
        out.append((s, [str(x).strip() for x in settings]))
    return out, ""


def substitute(text: str, derived: dict) -> str:
    """*text* with each placeholder replaced by its VALIDATED value (*derived*); a placeholder
    with no value raises: nothing is joined from unvalidated text. A list value (a
    subscription's lines) is expanded by `program` alone, never joined into a line here."""
    def one(m):
        if m.group(1) not in derived:
            raise Refused("render", f"{{{m.group(1)}}} has no validated value")
        if isinstance(derived[m.group(1)], (list, tuple)):
            raise Refused("render", f"{{{m.group(1)}}} is several lines, a whole line of its own")
        return str(derived[m.group(1)])
    return _PLACEHOLDER.sub(one, text)


def title_of(key: str, values: dict) -> str:
    """Plan *key*'s title with *values* (an attempt's or a proposal's, the device included),
    each interface also in its short form, for a screen; its words when a value is missing."""
    from modules.nsot import ifnames

    t = template_of(key)
    derived = dict(values or {})
    for name, spec in t.parameters.items():
        if spec["type"] == "interface" and derived.get(name):
            derived[f"{name}_short"] = ifnames.abbreviate(ifnames.canonical(derived[name]))
    try:
        return substitute(t.title, derived)
    except Refused:
        return t.words.split(":")[0]


def program(t: Template, derived: dict) -> list:
    """The lines sent: each command substituted. A command naming ``{<name>_each}`` (a
    subscription's receiver group) is sent once for each subscription of the group, in its
    order, followed each time by that subscription's lines when the next command is the whole
    indented ``{<name>_each_lines}`` (each line with that command's indentation): so a removal
    line repeats for every subscription, then a header and its lines for every one."""
    out, cmds, n = [], list(t.commands), 0
    while n < len(cmds):
        c = cmds[n]
        each = next((p for p in _PLACEHOLDER.findall(c) if p.endswith("_each")), "")
        if not each:
            out.append(substitute(c, derived))
            n += 1
            continue
        body = None
        if n + 1 < len(cmds) and cmds[n + 1].strip() == "{" + each + "_lines}":
            body = cmds[n + 1]
        lines_of = derived.get(each + "_lines") or {}
        for sub in derived.get(each) or []:
            out.append(substitute(c, dict(derived, **{each: sub})))
            if body is not None:
                indent = body[:len(body) - len(body.lstrip())]
                out += [indent + str(x) for x in lines_of.get(sub) or []]
        n += 2 if body is not None else 1
    return out


def line_matches(pattern: str, answer: str, derived: dict) -> bool:
    """Whether *answer* holds a line equal to *pattern* (the module docstring): spaces
    collapsed, ``*`` anything, each placeholder its validated value as text."""
    parts = [" ".join(substitute(p, derived).split()) for p in pattern.split("*")]
    rx = re.compile(".*".join(re.escape(p) for p in parts) + r"\Z")
    return any(rx.match(" ".join(ln.split())) for ln in (answer or "").splitlines())


def authorised(t: Template, lines: list) -> list:
    """The lines of *lines* the pipeline's gate holds dangerous, each authorised by the
    template's reason (in the hash)."""
    from modules.pipeline import dangerous_commands

    return [{"line": ln, "reason": t.reason} for ln in dict.fromkeys(dangerous_commands(lines))]


def resolve(spec: tuple):
    import importlib

    mod, attr = spec
    return getattr(importlib.import_module(mod), attr)


#: The fields a plan's hash binds, each drawn before Approve: the template and its digest, the
#: network, the validated values, the rendered program with its authorisations' reasons, the
#: preconditions and the verify (each by name, read and expectation), their bounds, and the
#: net-zero rule.
BINDS = ("template", "digest", "network", "values", "program", "preconditions", "verify",
         "bounds", "net_zero")


def bound_fields(network: str, t: Template, values: dict, lines: list, auth: list) -> dict:
    """Exactly `BINDS`, as the hash binds them."""
    from modules.nsot.deploy import command_fingerprint
    from modules.waits import PLAN_BOUNDS

    bounds = {b: PLAN_BOUNDS[b]["seconds"] for v in t.verify
              for b in (v.get("poll"), v.get("within"), v.get("after")) if b}
    return {"template": t.key, "digest": t.digest, "network": network, "values": values,
            "program": command_fingerprint(lines, auth),
            "preconditions": [[p["name"], p["read"], p["expect"], p["expect_line"]]
                              for p in t.preconditions],
            "verify": [[v["name"], v["read"], v["expect"], v["expect_line"]]
                       for v in t.verify], "bounds": bounds, "net_zero": t.net_zero}


def plan_hash(network: str, t: Template, values: dict, lines: list, auth: list) -> str:
    return _digest(bound_fields(network, t, values, lines, auth))


def preview(network: str, key, values, *, sources=None, store=None) -> dict:
    """The plan *key* with *values*, previewed (the module docstring): ``{"ok", "refusals",
    "key", "title", "values", "derived", "dialect", "program", "authorised", "hash", "drawn",
    "unknown_shapes"}``. Writes nothing; asks no device."""
    from modules.nsot import command_policy
    from modules.nsot import reads as R

    out = {"ok": False, "refusals": [], "key": str(key)[:50], "title": "", "values": {},
           "derived": {}, "dialect": "", "program": [], "authorised": [], "hash": "",
           "drawn": {}, "unknown_shapes": [], "device_row": {}}
    try:
        t = template_of(key)
    except Refused as exc:
        out["refusals"].append(str(exc))
        return out
    got = validate(network, t, values, sources=sources)
    out.update(values=got["values"], derived=got["derived"], dialect=got["dialect"],
               device_row=got["device_row"])
    if not got["ok"]:
        out["refusals"] += got["refusals"]
        return out
    pol = command_policy.check(got["dialect"], t.commands, tuple(command_names(t.parameters)),
                               network=network, store=store)
    out["unknown_shapes"] = pol["unknown"]
    out["refusals"] += pol["refusals"]
    derived = got["derived"]
    lines = program(t, derived)
    # Each line intent supplies (a subscription's, the ``<name>_each_lines`` expansion) is held
    # to the rule's refused words and objects too: its shape is approved as the subscription's
    # lines, never as any line. Only those lines: the template's own commands are held by
    # `command_policy.check` above, where a parameter-named object is allowed.
    from_intent = [str(x) for name, value in derived.items() if name.endswith("_each_lines")
                   and isinstance(value, dict) for group in value.values() for x in group]
    for ln in from_intent:
        w, obj = command_policy.refused_word(ln), command_policy.literal_object(ln)
        if w or obj:
            out["refusals"].append(f"`{' '.join(ln.split())}` "
                                   + (f"begins with `{w}`, which Mercury never sends in a "
                                      "command plan" if w else
                                      f"names its {obj} as text")
                                   + ", and it came from committed intent")
    reads = [substitute(i["read"], derived) for i in t.preconditions + t.verify if i["read"]]
    for r in dict.fromkeys(reads):
        why = R.refusal([r], 1, R.OPERATION)
        if why:
            out["refusals"].append(f"the plan's read `{r}` is refused by the read engine: {why}")
    # A precondition Mercury can judge from its own records is judged now too.
    for p in t.preconditions:
        spec = NAMED_CHECKS.get(p["expect"]) if p["expect"] else None
        if spec and spec[2]:
            result, words = resolve((spec[0], spec[2]))(network, got["device_row"], derived,
                                                        sources)
            if result == "fail":
                out["refusals"].append(f"{p['name']}: {words}")
    auth = authorised(t, lines)
    out.update(title=substitute(t.title, derived), program=lines, authorised=auth)
    if out["refusals"]:
        return out
    out["hash"] = plan_hash(network, t, got["values"], lines, auth)
    out["ok"] = True
    out["drawn"] = drawn(t, out)
    return out


def drawn(t: Template, p: dict) -> dict:
    """What a person reads before Approve: every line masked, every check by name and read,
    each bound in seconds, and the net-zero rule."""
    from modules.redact import redact_text
    from modules.waits import PLAN_BOUNDS

    d = p.get("derived") or {}

    def item(i):
        bound = {k: PLAN_BOUNDS[i[k]]["seconds"] for k in ("poll", "within", "after") if i.get(k)}
        return {"name": i["name"], "read": redact_text(substitute(i["read"], d)) if i["read"]
                else "", "expect": (redact_text(substitute(i["expect_line"], d))
                                    if i["expect_line"] else i["expect"]), **bound}
    return {"ok": p["ok"], "refusals": [redact_text(x) for x in p.get("refusals") or []],
            "hash": p.get("hash", ""), "title": redact_text(p.get("title") or ""),
            "template": t.key, "template_digest": t.digest, "dialect": p.get("dialect", ""),
            "program": [redact_text(x) for x in p.get("program") or []],
            "reason": redact_text(t.reason),
            "preconditions": [item(i) for i in t.preconditions],
            "verify": [item(i) for i in t.verify],
            "net_zero": ("the running configuration after the plan must equal the one before "
                         "it, line for line, both read holding the device; any difference is "
                         "rolled back and the plan refused")}


def matched(pattern_item: dict, answer, run) -> tuple:
    """One precondition or verify item judged on *answer* (None when the read could not be
    made): ``(result, words)``, result ``pass``, ``fail`` or ``unreadable``."""
    if pattern_item["expect_line"]:
        if answer is None:
            return "unreadable", f"`{substitute(pattern_item['read'], run.derived)}` could not "\
                                 "be read"
        want = substitute(pattern_item["expect_line"], run.derived)
        ok = line_matches(pattern_item["expect_line"], answer, run.derived)
        return ("pass" if ok else "fail",
                f"a line `{want}` {'is' if ok else 'is not'} in the answer")
    fn = resolve(NAMED_CHECKS[pattern_item["expect"]][:2])
    return fn(answer, run)
