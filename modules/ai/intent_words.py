"""An intent change in words (PHASE8_PLAN feature 7; 15.7, 15.16): a person's sentence becomes
C1471's per-device intent patch (`modules/nsot/intent_patch.py`), which the intent editor
previews, exactly as a patch typed by a person.

What may leave the host for it (15.16, the operator's ruling of 2026-10-26, the topology
class): the schema of the keys a change may set, and, for each device in scope, the CURRENT
VALUES of the intent sections the sentence touches (the interfaces it names, the VLANs it
names, the OSPF network statements it names); never the intent document, never any other key,
never a secret-bearing key.
- :func:`touched`: PURE. What a sentence names, read by code, never by the model: interface
  names in any of their written forms (`ifnames.canonical`), VLAN numbers after "vlan", and
  network prefixes.
- :func:`slice_of`: PURE. One device's touched sections from its intent document, each with
  only its allowed keys (`READS`), and what the sentence names that the device does not hold.
- :func:`to_patches`: the model's answer in the patch's own shape, checked against the scope
  BEFORE any preview: an operation on a device, interface, VLAN or network the sentence did
  not name is refused.
- :func:`change`: the call, and each patch handed to the intent editor's preview (nothing is
  written). Mercury answers itself, with no call, when the sentence names nothing to change.
"""

import ipaddress
import json
import logging
import re
from enum import Enum

from modules.ai.nl_query import Outcome
from modules.ai.schemas import StrictModel, register

log = logging.getLogger(__name__)


# ── the model's answer ───────────────────────────────────────────────────────

class Op(str, Enum):
    """The patch's eight operations (`intent_patch.Operation`), by their own names."""
    set_description = "set_description"
    clear_description = "clear_description"
    shutdown = "shutdown"
    no_shutdown = "no_shutdown"
    add_vlan = "add_vlan"
    remove_vlan = "remove_vlan"
    add_ospf_network = "add_ospf_network"
    remove_ospf_network = "remove_ospf_network"


#: Each operation's own fields; every other field of `Operation` must be empty or 0.
FIELDS = {Op.set_description: ("interface", "description"),
          Op.clear_description: ("interface",), Op.shutdown: ("interface",),
          Op.no_shutdown: ("interface",), Op.add_vlan: ("vlan", "vlan_name"),
          Op.remove_vlan: ("vlan",), Op.add_ospf_network: ("process", "prefix", "area"),
          Op.remove_ospf_network: ("process", "prefix", "area")}


class Operation(StrictModel):
    """One operation, flat and closed (every field required, so the provider's schema has no
    union): the fields its op does not use are empty, or 0. Converted to the patch's own shape
    by :func:`to_patches`, where `intent_patch` validates it."""
    op: Op
    interface: str
    description: str
    vlan: int
    vlan_name: str
    process: int
    prefix: str
    area: str


class DevicePatch(StrictModel):
    hostname: str
    operations: list[Operation]


@register("intent_change", 1)
class IntentChange(StrictModel):
    """One patch per device the sentence changes; or the one question that settles what the
    words leave open; or why the change cannot be made with the patch's operations."""
    outcome: Outcome
    question: str
    why_not: str
    patches: list[DevicePatch]


# ── what the sentence touches, and what of it leaves ─────────────────────────

#: The keys a slice reads, by section: the patch's own. Everything else in a device's intent
#: stays on the host (15.16); none of these holds a secret.
READS = {"interfaces": ("name", "description", "shutdown"), "vlans": ("id", "name"),
         "ospf": ("process", "networks")}

#: An interface as a sentence writes it: a type word and its numbers, a space allowed between
#: them but for a VLAN interface ("Vlan10"; "vlan 10" is a VLAN).
_IFACE = re.compile(r"\b(?!vlan\s)([A-Za-z][A-Za-z-]*)\s?(\d+(?:[/.:]\d+)*)\b", re.I)
_VLANS = re.compile(r"\bvlans?\s+(\d{1,4}(?:\s*(?:,|and|&|or)\s*\d{1,4})*)", re.I)
_PREFIX = re.compile(r"(?<![\w.:])((?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2}|\s+(?:\d{1,3}\.){3}\d{1,3})"
                     r"|[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{0,4}){2,7}/\d{1,3})")


def _interface_like(token: str) -> bool:
    """A token naming an interface type Mercury knows (not "area 0" or "process 1")."""
    from modules.nsot import ifnames
    canonical = ifnames.canonical(token).lower()
    return any(canonical.startswith(full.lower()) for full, _abbrevs in ifnames.INTERFACE_PREFIXES)


def _network(text: str) -> str:
    """A prefix as the patch writes it ("192.0.2.0/24"), from a prefix or an address and a
    mask or wildcard; the text as given when it is no IPv4 network (an IPv6 prefix is the
    patch's to refuse, by name)."""
    words = text.split()
    try:
        if len(words) == 2:
            mask = int(ipaddress.IPv4Address(words[1]))
            wild = mask if mask & 0x80000000 == 0 else (~mask & 0xFFFFFFFF)
            width = 32 - wild.bit_length()
            return str(ipaddress.IPv4Network(f"{words[0]}/{width}", strict=False))
        return str(ipaddress.ip_network(text, strict=False))
    except ValueError:
        return text


def touched(sentence: str) -> dict:
    """``{"interfaces": [...], "vlans": [...], "networks": [...]}``: what *sentence* names,
    interfaces canonical, VLANs as numbers, networks as prefixes; each once, in its order."""
    from modules.nsot import ifnames
    s = sentence or ""
    vlan_spans = [m.span() for m in _VLANS.finditer(s)]
    interfaces = []
    for m in _IFACE.finditer(s):
        if any(a <= m.start() < b for a, b in vlan_spans):
            continue
        token = f"{m.group(1)}{m.group(2)}"
        if _interface_like(token):
            interfaces.append(ifnames.canonical(token))
    vlans = [int(n) for m in _VLANS.finditer(s) for n in re.findall(r"\d+", m.group(1))]
    networks = [_network(m.group(1)) for m in _PREFIX.finditer(s)]
    return {"interfaces": list(dict.fromkeys(interfaces)), "vlans": list(dict.fromkeys(vlans)),
            "networks": list(dict.fromkeys(networks))}


def nothing_named(t: dict) -> bool:
    return not (t["interfaces"] or t["vlans"] or t["networks"])


def slice_of(doc: dict, t: dict) -> dict:
    """``{"interfaces", "vlans", "ospf", "not_held"}``: the sections of *doc* (an intent
    document, a dict) that *t* (`touched`) names, each with only its allowed keys and their
    current values, and what *t* names that *doc* does not hold. OSPF: each process by its
    number, with only the statements *t* names, when *t* names a network."""
    from modules.nsot import ifnames, intent_patch
    from modules.nsot.features import _scalar

    doc = doc if isinstance(doc, dict) else {}
    held = [i for i in doc.get("interfaces") or [] if isinstance(i, dict) and i.get("name")]
    interfaces, not_held = [], []
    for name in t["interfaces"]:
        entry = next((i for i in held if ifnames.same_interface(str(i["name"]), name)), None)
        if entry is None:
            not_held.append(f"interface {name}")
            continue
        interfaces.append({"name": str(entry["name"]),
                           "description": str(entry.get("description") or ""),
                           "shutdown": bool(entry.get("shutdown"))})
    vlan_entries = [v for v in doc.get("vlans") or [] if isinstance(v, dict)]
    vlans = []
    for number in t["vlans"]:
        entry = next((v for v in vlan_entries if str(v.get("id")) == str(number)), None)
        if entry is None:
            not_held.append(f"VLAN {number}")
        else:
            vlans.append({"id": str(entry.get("id")), "name": str(entry.get("name") or "")})
    ospf = []
    if t["networks"]:
        routing = doc.get("routing") if isinstance(doc.get("routing"), dict) else {}
        for proc in routing.get("ospf") or []:
            if not isinstance(proc, dict):
                continue
            networks = []
            for (net, wild), area, _where in intent_patch._statements(proc):
                prefix = str(ipaddress.IPv4Network((net, 32 - wild.bit_length()),
                                                   strict=False)) if _contiguous(wild) else ""
                if prefix in t["networks"]:
                    networks.append({"prefix": prefix, "area": str(area)})
            ospf.append({"process": _scalar(proc.get("process")), "networks": networks})
        stated = {n["prefix"] for p in ospf for n in p["networks"]}
        not_held += [f"the OSPF network {n}" for n in t["networks"] if n not in stated]
    return {"interfaces": interfaces, "vlans": vlans, "ospf": ospf, "not_held": not_held}


def _contiguous(wild: int) -> bool:
    """A wildcard IOS can also write as a prefix length (its set bits all at the right)."""
    return (wild & (wild + 1)) == 0


def to_patches(answer: IntentChange, scope: dict) -> dict:
    """``{"ok", "error", "patches"}``: each device's operations in `intent_patch`'s own shape,
    validated by `intent_patch.parse`; refused, naming why, BEFORE any preview, when an
    operation fills a field its op does not use, or changes what *scope* does not hold: a device
    out of scope, or an interface, VLAN or network the sentence did not name. *scope* is
    ``{hostname: touched(sentence)}``."""
    from modules.nsot import ifnames, intent_patch

    patches = []
    for d in answer.patches:
        if d.hostname not in scope:
            return {"ok": False, "error": f"the answer changes {d.hostname[:64]!r}, a device "
                    f"outside the request (it names {', '.join(scope) or 'none'})"}
        named = scope[d.hostname]
        ops = []
        for i, o in enumerate(d.operations):
            mine = FIELDS[o.op]
            extra = [f for f in ("interface", "description", "vlan", "vlan_name", "process",
                                 "prefix", "area") if f not in mine and getattr(o, f)]
            if extra:
                return {"ok": False, "error": f"{d.hostname}'s operation {i} ({o.op.value}) "
                        f"fills {', '.join(extra)}, which it does not use"}
            outside = _outside(o, named, ifnames)
            if outside:
                return {"ok": False, "error": f"{d.hostname}'s operation {i} ({o.op.value}) "
                        f"changes {outside}, which the request does not name"}
            op = {"op": o.op.value}
            for f in mine:
                op["name" if f == "vlan_name" else f] = getattr(o, f)
            ops.append(op)
        patch, refusal = intent_patch.parse({"hostname": d.hostname, "operations": ops})
        if refusal:
            return {"ok": False, "error": f"{d.hostname}: {refusal['error']}"}
        patches.append(patch)
    return {"ok": True, "error": "", "patches": patches}


def _outside(o: Operation, named: dict, ifnames) -> str:
    """What *o* changes that *named* does not hold, in words, or ""."""
    if "interface" in FIELDS[o.op]:
        if not any(ifnames.same_interface(o.interface, n) for n in named["interfaces"]):
            return f"the interface {o.interface[:64]!r}"
    elif "vlan" in FIELDS[o.op]:
        if o.vlan not in named["vlans"]:
            return f"VLAN {o.vlan}"
    elif _network(o.prefix) not in named["networks"]:
        return f"the network {o.prefix[:64]!r}"
    return ""


# ── the call ─────────────────────────────────────────────────────────────────

FEATURE = "intent_patch"
PROMPT = ("intent_change", 1)

#: The steps, as the manual's How it works page names them (docs/manual/how-it-works/
#: intent-in-words.md).
STEPS = (
    ("scope", "the device, and the interfaces, VLANs and networks the sentence names, read by "
              "code; a sentence naming none stops there with nothing sent"),
    ("ask", "one recorded, capped call through the AI gateway, as the person who asked, with "
            "only the named parts' current values"),
    ("check", "the draft refused before any preview if it changes what the sentence did not "
              "name; the patch's own rules then hold"),
    ("preview", "the intent editor's own preview: what the change does, what a deploy would "
                "send, its checks; nothing is written"),
)


def vocabulary() -> str:
    """The operations, their fields, and the schema of the keys a change may set: the same
    bytes on every call (the cached prefix)."""
    return "\n".join(f"{op.value}: {', '.join(FIELDS[op])}" for op in Op) + "\n" + (
        "Fields: interface (its name as the device's data gives it), description (text), "
        "vlan (a number), vlan_name (one word, or empty), process (the OSPF process number), "
        "prefix (an IPv4 prefix, host bits clear), area (a number)\n"
        "The intent keys a change may set, and the only ones given: interfaces[].description, "
        "interfaces[].shutdown; vlans[].id, vlans[].name; routing.ospf[].networks (prefix and "
        "area), by process")


def parts(sentence: str, named: list, given: dict) -> dict:
    """The call's own data: the sentence, the devices in scope, and their touched sections."""
    import yaml
    return {"sentence": sentence, "devices_named": "\n".join(named),
            "devices": yaml.safe_dump(given, sort_keys=True, default_flow_style=None)}


def scope_of(list_name: str, sentence: str, devices: list = None) -> dict:
    """``{"ok", "error", "detail", "named"}``: the devices a change may touch. On a device's
    tab (*devices*), those alone: another device's name in the sentence is only words (a
    description names its neighbour: "uplink to edge1"), and an answer changing that device is
    refused by the scope check after it (`to_patches`). Else the devices the sentence names."""
    from modules.ai.nl_query import _inventory, named_devices

    if devices:
        return {"ok": True, "named": list(devices)}
    said = named_devices(sentence, _inventory(list_name))
    if not said:
        return {"ok": False, "error": "no_device", "detail": (
            f"the sentence names no device of {list_name}; name each device to change, as its "
            "name reads; nothing was sent"), "named": []}
    return {"ok": True, "named": said}


def change(list_name: str, sentence: str, *, actor: str, send=None, today: str = None,
           devices: list = None) -> dict:
    """``{"ok", "error", "detail", "previews", "call_id", "cost_usd", ...}``: *sentence* made a
    patch per device it changes, each previewed by the intent editor (nothing written); or one
    question back, or a refusal naming why, with nothing previewed. *devices* limits the scope
    (a device's Intent tab). Mercury answers itself, with no call and nothing spent, when the
    sentence names no device in scope or nothing to change."""
    from modules.ai import calls, gateway
    from modules.ai.nl_query import QUESTION_MAX
    from modules.nsot import intent_patch

    sentence = " ".join((sentence or "").split())
    if not sentence:
        return {"ok": False, "error": "empty", "detail": "type the change first"}
    if len(sentence) > QUESTION_MAX:
        return {"ok": False, "error": "too_long",
                "detail": f"the sentence is {len(sentence)} characters; at most "
                          f"{QUESTION_MAX} are taken"}
    scope = scope_of(list_name, sentence, devices)
    if not scope["ok"]:
        return dict(scope, by="mercury", call_id="", cost_usd=0.0)
    named, t = scope["named"], touched(sentence)
    if nothing_named(t):
        return {"ok": False, "error": "nothing_named", "by": "mercury", "call_id": "",
                "cost_usd": 0.0, "named": named, "detail": (
                    "the sentence names no interface, VLAN or OSPF network to change; name it "
                    "as the device does (GigabitEthernet0/1, VLAN 40, 192.0.2.0/24); nothing "
                    "was sent")}
    got = slices(list_name, named, t)
    if got["missing"]:
        return {"ok": False, "error": "no_intent", "by": "mercury", "call_id": "",
                "cost_usd": 0.0, "detail": "; ".join(f"{h}: {why}" for h, why in
                                                      got["missing"]) + "; nothing was sent"}
    subject = {"kind": "intent", "id": list_name, "devices": list(named)}
    asked = gateway.ask(FEATURE, PROMPT, IntentChange, parts(sentence, named, got["devices"]),
                        actor=actor, context={"operations": vocabulary()}, send=send,
                        today=today, subject=subject)
    if not asked["ok"]:
        return asked
    answer = asked["output"]
    base = {"call_id": asked["call_id"], "cost_usd": asked["cost_usd"],
            "choices": answer.model_dump(mode="json")}
    links = {"page": f"/v2/device/{named[0]}?tab=intent"}
    if answer.outcome is Outcome.ask:
        calls.record_use(asked["call_id"], "asked a question back", actor=actor,
                         detail=answer.question[:200], links=links)
        return dict(base, ok=False, error="ask", clarify=answer.question[:200],
                    detail=f"one question first: {answer.question[:200]}")
    if answer.outcome is Outcome.refuse:
        calls.record_use(asked["call_id"], "shown: the operations cannot make it", actor=actor,
                         detail=answer.why_not[:200], links=links)
        return dict(base, ok=False, error="unanswerable",
                    detail=f"this change cannot be drafted in words: {answer.why_not[:200]}")
    if not answer.patches:
        calls.record_use(asked["call_id"], "refused by validation", actor=actor,
                         detail="an answer with no patch", links=links)
        return dict(base, ok=False, error="couldnt_change",
                    detail="the answer changes no device; nothing is previewed")
    made = to_patches(answer, {h: t for h in named})
    if not made["ok"]:
        calls.record_use(asked["call_id"], "refused by validation", actor=actor,
                         detail=made["error"][:200], links=links)
        return dict(base, ok=False, error="couldnt_change",
                    detail=f"{made['error']}; nothing is previewed")
    previews = [dict(intent_patch.preview(list_name, p.hostname, p), hostname=p.hostname)
                for p in made["patches"]]
    refused = [p for p in previews if not p.get("ok")]
    calls.record_use(asked["call_id"], "refused by the intent" if refused else
                     "previewed in the intent editor", actor=actor,
                     detail="; ".join(f"{p['hostname']}: {p.get('error', '')}"
                                      for p in refused)[:200], links=links)
    return dict(base, ok=not refused, error="intent" if refused else "", previews=previews,
                detail="; ".join(f"{p['hostname']}: {p.get('error', '')}" for p in refused))


def stale(list_name: str, case: dict) -> list:
    """Why a recorded case's expectation no longer holds against *list_name*'s committed
    intent (``[]``: it holds), asked of the real path with no call: the expected operations
    made the answer, put through `to_patches` with the sentence's own scope and then the intent
    editor's preview. Stale when the device has no committed intent; when the expected answer
    is outside what the sentence names; when it changes nothing and the case does not allow
    "the answer changes no device"; when the editor refuses it and the case does not expect
    that refusal in its words; or when the case expects the editor's refusal and the intent now
    takes the change. Run first in every recording (scripts/nmas-intent-cases), so a stale
    expectation stops the run before anything is asked or spent, never scored as the model's
    miss."""
    from modules.nsot import intent_edit, intent_patch

    device, expect = case.get("device") or "", case.get("expect") or {}
    allowed, said = expect.get("outcome") or [], expect.get("said") or {}
    where = f"case {case.get('n')} ({device})"
    opened = intent_edit.open_doc(list_name, device)
    if not opened["ok"]:
        return [f"{where}: no committed intent to judge it against: {opened['error']}"]
    if not expect.get("ops") or not ({"answer", "refused_after"} & set(allowed)):
        return []
    blank = {k: (0 if f.annotation is int else "")
             for k, f in Operation.model_fields.items() if k != "op"}
    ops = [dict(blank, op=o["op"], **{("vlan_name" if k == "name" else k): v
                                      for k, v in o.items() if k != "op"})
           for o in expect["ops"]]
    # Strict, as the gateway reads an answer: from its JSON (an enum is its value there).
    answer = IntentChange.model_validate_json(json.dumps({
        "outcome": "answer", "question": "", "why_not": "",
        "patches": [{"hostname": device, "operations": ops}]}))
    made = to_patches(answer, {device: touched(case.get("sentence") or "")})
    if not made["ok"]:
        return [f"{where}: the expected operations are outside what the sentence names: "
                f"{made['error']}"]
    shown = intent_patch.preview(list_name, device, made["patches"][0])
    if not shown.get("ok"):
        words = said.get("refused_after") or ""
        if "refused_after" in allowed and words and words in (shown.get("error") or ""):
            return []
        return [f"{where}: the intent editor refuses the expected change: "
                f"{(shown.get('error') or '')[:200]}"]
    # Already so: the patch changes nothing, or changes only how the document says it (an
    # up interface given an explicit `no shutdown`, C1401) and no line of the configuration.
    if not shown.get("changed") or not shown.get("vs_intent_changed", True):
        if "refused_after" in allowed and "changes no device" in said.get("refused_after", ""):
            return []
        return [f"{where}: the expected change is already in the committed intent: "
                + (shown.get("message") or "the configuration it renders does not change")[:200]]
    if "answer" not in allowed:
        return [f"{where}: the case expects the editor's refusal, and the committed intent now "
                "takes the change"]
    return []


def slices(list_name: str, hostnames: list, t: dict) -> dict:
    """``{"devices": {hostname: slice + platform, role}, "missing": [(hostname, why)]}``: the
    touched sections of *hostnames*, each from its committed intent (`intent_edit.open_doc`,
    the blob it names), its platform and role from the inventory."""
    from modules.nsot import hostvars, intent_edit
    from modules.ai.nl_query import _inventory

    inventory = {d.get("hostname"): d for d in _inventory(list_name) if d.get("hostname")}
    out, missing = {}, []
    for name in hostnames:
        opened = intent_edit.open_doc(list_name, name)
        if not opened["ok"]:
            missing.append((name, opened["error"]))
            continue
        try:
            doc = hostvars.from_yaml(opened["yaml"]) or {}
        except Exception as exc:                          # noqa: BLE001 (said)
            missing.append((name, f"its committed intent could not be read: {exc}"))
            continue
        row = inventory.get(name) or {}
        out[name] = dict(slice_of(doc, t), platform=str(row.get("platform") or ""),
                         role=str(row.get("role") or ""))
    return {"devices": out, "missing": missing}
