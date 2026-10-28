"""A per-device intent patch: typed operations applied to committed intent (C1471; PHASE8_PLAN
15.7 and 15.12, feature 7's first piece). Deterministic: no AI reads or writes anything here.

A patch names ONE device and a short list of operations, each one of Mercury's own words for a
change a person asks for: set or clear an interface's description, shut an interface or bring
it up, add or remove a VLAN, add or remove an OSPF network statement. It is a strict Pydantic v2
model (no coercion, no field it does not declare), so whatever produces one later (a person's
form, feature 7's model) is held to the same shape.

The path, and every step after the patch is the intent editor's (`intent_edit`), never a second
copy of it:

- :func:`parse`: the patch, or a refusal naming the field, its value and the rule.
- :func:`apply`: PURE. The patch applied to a device's intent document (a dict), returning a
  new one and what each operation changed; nothing is read or written. A patch naming an
  interface, VLAN or OSPF process the intent lacks, or contradicting what it holds, is refused
  naming both: what the patch asked and what the intent holds.
- :func:`patched_text`: the committed document's text patched and serialised by `hostvars`'
  own serialiser, then checked by the editor's own validator (`intent_edit.validate`). A
  document that does not round-trip through the serialiser (a hand edit's comments or layout)
  is refused, as bulk intent refuses it (`bulk_intent.plan`): writing it would drop them.
- :func:`preview`: the patched text handed to `intent_edit.preview`, exactly; with the blob
  (``base``) it was patched from, so the commit is bound to the version previewed.
- :func:`commit`: the patch re-applied to the version at ``base`` and handed to
  `intent_edit.commit`, which refuses when intent moved since, and commits as the person.

The device side is unchanged: the deploy plans from committed intent (`routes.deploy`'s plan
and apply), its preview, confirm by hash, apply, verify and rollback.

**What a merge-only deploy does not carry** (never a wrong thing that looks right): clearing a
description, removing a VLAN or an OSPF network statement removes the line from intent, and a
merge-only deploy sends nothing for an absent line, so the device keeps it. Each such operation
says so (``device_keeps``), and the editor's preview names the line (``diffs.not_removed``). A
removal (Mode B, `removal.py`) takes it off only where its shape is measured: as
`removal_measured.json` read on 2026-10-25, a description's is, on both dialects, and a VLAN's
and a network statement's are not.

**A VLAN is added only where a VLAN database is declared or measured** (C1692; the operator,
2026-10-28): a router's intent holds ``vlans: []`` as a switch's does, so the document cannot
tell. :func:`apply` stays pure and is handed the device's VLAN database by its caller
(`vlan_capability.of`: Mercury's platform table by dialect and NetBox device type, else the
device's recorded answer to `show vlan id 1`, else unknown); `preview`, `commit` and
`commit_many` read it once for a patch that adds a VLAN. A declared or measured "no", and an
unknown, are refused naming the device, its platform and device type and where the answer came
from. Never from a name or a role. The words are the one check's (`vlan_capability.refusal`),
which the editor's commit and bulk intent ask too (C2043, C2044); the capability read here is
handed to `intent_edit.commit` (``vlan_databases``), so a commit reads it once, and to
`intent_edit.preview`, which runs the same check (C2061), so a preview reads it once too.

**IPv6:** an OSPF network statement is OSPFv2's, an IPv4 concept; OSPFv3 joins an interface to
an area instead (``ipv6 ospf <process> area <area>``), which a patch does not offer yet. An
IPv6 prefix in a network operation is refused saying so, by name. Descriptions, shutdown and
VLANs carry no address.
"""

import copy
import ipaddress
import logging
from typing import Annotated, List, Literal, Union, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

log = logging.getLogger(__name__)

#: The most operations one patch holds: a person reads every one at the preview before the
#: commit. A change to many interfaces or devices at once is bulk intent's (`bulk_intent`).
MAX_OPERATIONS = 64
#: IOS's longest interface description, in characters.
MAX_DESCRIPTION = 240
#: The VLANs a device holds by default and refuses to create or delete (1, and 1002 to 1005).
DEFAULT_VLANS = frozenset({1, 1002, 1003, 1004, 1005})
#: How many of the intent's names a refusal lists before "and N more".
NAMES_SHOWN = 12


# ── the patch ────────────────────────────────────────────────────────────────

class _Strict(BaseModel):
    """No coercion, no undeclared field, and immutable once made."""
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


def _printable(value: str, what: str) -> str:
    """*value* when it is printable ASCII with no leading or trailing space (anything reaching
    a CLI is printable ASCII), else a ValueError naming *what* and the rule."""
    bad = [c for c in value if not (" " <= c <= "~")]
    if bad:
        raise ValueError(f"{what} must be printable ASCII; it holds {bad[0]!r}")
    if value != value.strip():
        raise ValueError(f"{what} must not begin or end with a space")
    return value


class _OnInterface(_Strict):
    interface: Annotated[str, Field(min_length=1, max_length=64)]

    @field_validator("interface")
    @classmethod
    def _one_word(cls, value: str) -> str:
        _printable(value, "an interface name")
        if " " in value:
            raise ValueError("an interface name is one word, such as GigabitEthernet0/1")
        return value


class SetDescription(_OnInterface):
    op: Literal["set_description"]
    description: Annotated[str, Field(min_length=1, max_length=MAX_DESCRIPTION)]

    @field_validator("description")
    @classmethod
    def _cli_text(cls, value: str) -> str:
        return _printable(value, "a description")


class ClearDescription(_OnInterface):
    op: Literal["clear_description"]


class Shutdown(_OnInterface):
    op: Literal["shutdown"]


class NoShutdown(_OnInterface):
    op: Literal["no_shutdown"]


class _OnVlan(_Strict):
    vlan: Annotated[int, Field(ge=1, le=4094)]

    @field_validator("vlan")
    @classmethod
    def _not_a_default(cls, value: int) -> int:
        if value in DEFAULT_VLANS:
            raise ValueError(f"VLAN {value} is one the device holds by default (1 and 1002 "
                             "to 1005), which it neither creates nor deletes")
        return value


class AddVlan(_OnVlan):
    op: Literal["add_vlan"]
    #: One word of up to 32 characters (IOS's VLAN name), or empty for no name.
    name: Annotated[str, Field(max_length=32, pattern=r"^[A-Za-z0-9_.-]*$")] = ""


class RemoveVlan(_OnVlan):
    op: Literal["remove_vlan"]


_NOT_V2 = ("an OSPF network statement is OSPFv2's, IPv4 only. OSPFv3 joins an interface to an "
           "area instead (ipv6 ospf <process> area <area>), which a patch does not offer yet")


class _OspfNetwork(_Strict):
    process: Annotated[int, Field(ge=1, le=65535)]
    #: The network as a prefix, such as 192.0.2.0/24 (a host is /32), host bits clear.
    prefix: Annotated[str, Field(min_length=1, max_length=43)]
    #: The area as a number (0) or the same number as a dotted quad ("0.0.0.0").
    area: Union[int, str]

    @field_validator("prefix")
    @classmethod
    def _ipv4_network(cls, value: str) -> str:
        try:
            net = ipaddress.ip_network(value, strict=True)
        except ValueError as exc:
            try:
                loose = ipaddress.ip_network(value, strict=False)
            except ValueError:
                raise ValueError(f"{value!r} is not a network prefix ({exc})") from None
            if loose.version == 6:
                raise ValueError(f"{value!r} is an IPv6 prefix: {_NOT_V2}") from None
            raise ValueError(f"{value!r} has host bits set; its network is {loose}") from None
        if net.version == 6:
            raise ValueError(f"{value!r} is an IPv6 prefix: {_NOT_V2}")
        return str(net)

    @field_validator("area")
    @classmethod
    def _area(cls, value) -> str:
        from modules.nsot.features import area_number
        if isinstance(value, bool) or area_number(value) is None:
            raise ValueError(f"{value!r} is not an OSPF area: a number from 0 to 4294967295, "
                             "or the same number as a dotted quad")
        return str(value)


class AddOspfNetwork(_OspfNetwork):
    op: Literal["add_ospf_network"]


class RemoveOspfNetwork(_OspfNetwork):
    op: Literal["remove_ospf_network"]


Operation = Annotated[Union[SetDescription, ClearDescription, Shutdown, NoShutdown, AddVlan,
                            RemoveVlan, AddOspfNetwork, RemoveOspfNetwork],
                      Field(discriminator="op")]


class IntentPatch(_Strict):
    """One device's patch: its name (a label, compared with the document's) and its
    operations, applied in order."""
    hostname: Annotated[str, Field(min_length=1, max_length=253)]
    operations: Annotated[List[Operation], Field(min_length=1, max_length=MAX_OPERATIONS)]


# ── refusals ─────────────────────────────────────────────────────────────────

class Refused(Exception):
    """An operation the intent cannot take; ``refusal`` is the dict a caller returns."""

    def __init__(self, refusal: dict):
        super().__init__(refusal.get("error", ""))
        self.refusal = refusal


def _refusal(status: int, stage: str, error: str, **extra) -> dict:
    return {"status": status, "ok": False, "stage": stage, "error": error, **extra}


def _shown(value, limit: int = 80) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _names(items) -> str:
    items = list(items)
    if not items:
        return "none"
    head = ", ".join(items[:NAMES_SHOWN])
    return head + (f" and {len(items) - NAMES_SHOWN} more" if len(items) > NAMES_SHOWN else "")


def parse(data):
    """``(patch, None)``, or ``(None, refusal)`` naming each field the model refuses, its value
    and the rule. *data* is a mapping, a JSON text, or an `IntentPatch`."""
    if isinstance(data, IntentPatch):
        return data, None
    try:
        if isinstance(data, (str, bytes)):
            return IntentPatch.model_validate_json(data), None
        return IntentPatch.model_validate(data), None
    except ValidationError as exc:
        problems = []
        for err in exc.errors():
            where = ".".join(str(p) for p in err.get("loc", ())) or "the patch"
            problems.append(f"{where} is {_shown(err.get('input'))}: {err.get('msg')}")
        return None, _refusal(400, "patch", "The patch is refused: " + "; ".join(problems[:6])
                              + (f"; and {len(problems) - 6} more" if len(problems) > 6
                                 else ""))


def _coerce(patch) -> IntentPatch:
    got, refusal = parse(patch)
    if refusal:
        raise Refused(refusal)
    return got


# ── apply: pure ──────────────────────────────────────────────────────────────

def _interface(doc: dict, name: str, index: int, hostname: str) -> dict:
    from modules.nsot import ifnames

    interfaces = [i for i in doc.get("interfaces") or [] if isinstance(i, dict)]
    for entry in interfaces:
        if ifnames.same_interface(str(entry.get("name") or ""), name):
            return entry
    raise Refused(_refusal(409, "intent", (
        f"operations[{index}] names the interface {name!r}, and {hostname}'s intent holds no "
        f"such interface; it holds {_names(str(i.get('name')) for i in interfaces)}"),
        operation=index))


def _decides(op) -> tuple:
    """``(identity, words)``: what *op* decides, so two operations deciding one thing are
    refused (one decision, one operation)."""
    from modules.nsot import ifnames

    if isinstance(op, _OnInterface):
        name = ifnames.canonical(op.interface)
        field = "description" if op.op.endswith("description") else "admin state"
        return (field, name.lower()), f"the {field} of {name}"
    if isinstance(op, _OnVlan):
        return ("vlan", op.vlan), f"VLAN {op.vlan}"
    return (("ospf network", op.process, op.prefix),
            f"the network {op.prefix} in OSPF process {op.process}")


def _net_key(address, wildcard):
    """``(network, wildcard)`` as integers, the address's wildcard bits cleared (IOS reads
    `network 192.0.2.5` with the last octet wild as 192.0.2.0's), or None when either is no
    IPv4 address."""
    try:
        addr = int(ipaddress.IPv4Address(str(address)))
        wild = int(ipaddress.IPv4Address(str(wildcard)))
    except ValueError:
        return None
    return addr & ~wild & 0xFFFFFFFF, wild


def _statements(proc: dict):
    """Every network statement *proc* holds, in either shape intent keeps them: ``(key, area,
    where)``, *where* the list and the item to remove. The lines no pack models
    (``networks``: `network A W area N`) and the pack's ``areas[].networks[]`` (address and
    wildcard, or an authored prefix)."""
    out = []
    for line in proc.get("networks") or []:
        words = str(line).split()
        if len(words) == 5 and words[0] == "network" and words[3] == "area":
            key = _net_key(words[1], words[2])
            if key:
                out.append((key, words[4], (proc["networks"], line)))
    for area in proc.get("areas") or []:
        if not isinstance(area, dict):
            continue
        for net in area.get("networks") or []:
            if not isinstance(net, dict):
                continue
            if net.get("prefix") and not net.get("address"):
                try:
                    n = ipaddress.IPv4Network(str(net["prefix"]), strict=False)
                except ValueError:
                    continue
                key = (int(n.network_address), int(n.hostmask))
            else:
                key = _net_key(net.get("address"), net.get("wildcard"))
            if key:
                out.append((key, str(area.get("id")), (area["networks"], net)))
    return out


def _shown_statement(key, area) -> str:
    net, wild = key
    return f"network {ipaddress.IPv4Address(net)} {ipaddress.IPv4Address(wild)} area {area}"


def _process(doc: dict, number: int, index: int, hostname: str) -> dict:
    from modules.nsot.features import _scalar

    procs = ((doc.get("routing") or {}).get("ospf") or []) \
        if isinstance(doc.get("routing"), dict) else []
    procs = [p for p in procs if isinstance(p, dict)]
    for proc in procs:
        if _scalar(proc.get("process")) == str(number):
            return proc
    raise Refused(_refusal(409, "intent", (
        f"operations[{index}] names OSPF process {number}, and {hostname}'s intent holds no "
        f"such process; it holds {_names(_scalar(p.get('process')) for p in procs)}"),
        operation=index))


def _vlan_entries(doc: dict) -> list:
    return [v for v in doc.get("vlans") or [] if isinstance(v, dict)]


def _changed(summary: str, changed: bool, device_keeps: bool = False) -> dict:
    return {"summary": summary, "changed": changed, "device_keeps": device_keeps}


def _description(doc: dict, op, index: int, hostname: str) -> dict:
    entry = _interface(doc, op.interface, index, hostname)
    was = str(entry.get("description") or "")
    now = op.description if isinstance(op, SetDescription) else ""
    entry["description"] = now
    name = entry.get("name")
    return _changed(f"{name}: description {now!r} (was {was!r})" if now
                    else f"{name}: description cleared (was {was!r})",
                    was != now, device_keeps=bool(was) and not now)


def _admin(doc: dict, op, index: int, hostname: str) -> dict:
    """`shutdown` or `no shutdown`: the one key set and the other cleared, so the interface
    never holds both (C1429). An up interface prints no `no shutdown`, and the deploy holds it
    as the device's default (C1401), so bringing one up converges."""
    entry = _interface(doc, op.interface, index, hostname)
    down = isinstance(op, Shutdown)
    was = (bool(entry.get("shutdown")), bool(entry.get("no_shutdown")))
    entry["shutdown"], entry["no_shutdown"] = down, not down
    return _changed(f"{entry.get('name')}: {'shutdown' if down else 'no shutdown'}",
                    was != (down, not down))


def _held_vlan(doc: dict, vlan: int):
    return next((v for v in _vlan_entries(doc) if str(v.get("id")) == str(vlan)), None)


def _vlan_database(op, index: int, hostname: str, capability) -> None:
    """Refused unless *capability* (`vlan_capability.of`'s, handed in by the caller) says
    *hostname* has a VLAN database, declared or measured (C1692): a declared or measured "no"
    and an unknown are each refused, naming the device, its platform and device type, and
    where the answer came from. Never judged from a name or a role. The words are the one
    check's (`vlan_capability.refusal`), which the editor's commit and bulk intent use too."""
    from modules.nsot import vlan_capability

    words = vlan_capability.refusal(hostname, capability,
                                    f"operations[{index}] adds VLAN {op.vlan}")
    if words:
        raise Refused(_refusal(409, "capability", words, operation=index))


def _add_vlan(doc: dict, op, index: int, hostname: str, capability=None) -> dict:
    _vlan_database(op, index, hostname, capability)
    held = _held_vlan(doc, op.vlan)
    if held is not None:
        have = str(held.get("name") or "")
        if op.name and op.name != have:
            raise Refused(_refusal(409, "intent", (
                f"operations[{index}] adds VLAN {op.vlan} named {op.name!r}, and {hostname}'s "
                f"intent already holds VLAN {op.vlan} named {have!r}; adding is not renaming"),
                operation=index))
        return _changed(f"VLAN {op.vlan}: already held", False)
    if doc.get("vlans") is None:
        doc["vlans"] = []
    if not isinstance(doc["vlans"], list):
        raise Refused(_refusal(409, "intent", (
            f"operations[{index}] adds VLAN {op.vlan}, and {hostname}'s intent holds vlans as "
            f"{_shown(doc['vlans'])}, not a list"), operation=index))
    # In number order, as a device lists them.
    at = next((n for n, v in enumerate(doc["vlans"])
               if isinstance(v, dict) and str(v.get("id", "")).isdigit()
               and int(v["id"]) > op.vlan), len(doc["vlans"]))
    doc["vlans"].insert(at, {"extra": [], "id": str(op.vlan), "name": op.name})
    return _changed(f"VLAN {op.vlan} added" + (f", named {op.name!r}" if op.name else ""),
                    True)


def _remove_vlan(doc: dict, op, index: int, hostname: str) -> dict:
    from modules.nsot import ifnames

    held = _held_vlan(doc, op.vlan)
    if held is None:
        raise Refused(_refusal(409, "intent", (
            f"operations[{index}] removes VLAN {op.vlan}, and {hostname}'s intent holds no such "
            f"VLAN; it holds {_names(str(v.get('id')) for v in _vlan_entries(doc))}"),
            operation=index))
    users = []
    for entry in doc.get("interfaces") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("switchport_access_vlan") or "") == str(op.vlan):
            users.append(f"{entry.get('name')} (an access port in it)")
        elif ifnames.same_interface(str(entry.get("name") or ""), f"Vlan{op.vlan}"):
            users.append(f"{entry.get('name')} (its interface)")
    if users:
        raise Refused(_refusal(409, "intent", (
            f"operations[{index}] removes VLAN {op.vlan}, and {hostname}'s intent still uses "
            f"it: {_names(users)}. Move or remove those first"), operation=index))
    doc["vlans"].remove(held)
    return _changed(f"VLAN {op.vlan} removed", True, device_keeps=True)


def _ospf_network(doc: dict, op, index: int, hostname: str) -> dict:
    from modules.nsot.features import area_number

    proc = _process(doc, op.process, index, hostname)
    net = ipaddress.IPv4Network(op.prefix)
    key = (int(net.network_address), int(net.hostmask))
    held = [s for s in _statements(proc) if s[0] == key]
    same = [s for s in held if area_number(s[1]) == area_number(op.area)]
    asked = _shown_statement(key, op.area)
    if isinstance(op, RemoveOspfNetwork):
        if not same:
            holds = "; ".join(_shown_statement(k, a) for k, a, _w in _statements(proc))
            raise Refused(_refusal(409, "intent", (
                f"operations[{index}] removes {asked} from OSPF process {op.process}, and "
                f"{hostname}'s intent holds no such statement; it holds {holds or 'none'}"),
                operation=index))
        for _k, _a, (container, item) in same:
            container.remove(item)
        return _changed(f"OSPF {op.process}: {asked} removed", True, device_keeps=True)
    if same:
        return _changed(f"OSPF {op.process}: {asked} already held", False)
    if held:
        raise Refused(_refusal(409, "intent", (
            f"operations[{index}] adds {asked} to OSPF process {op.process}, and {hostname}'s "
            f"intent already holds {_shown_statement(key, held[0][1])}: one network in two "
            "areas"), operation=index))
    # Written in the OSPF pack's own fields (`features/ospf.py`, `areas[].networks[]`), which
    # the shipped template renders as `network <address> <wildcard> area <id>`.
    if proc.get("areas") is None:
        proc["areas"] = []
    area = next((a for a in proc["areas"] if isinstance(a, dict)
                 and area_number(a.get("id")) == area_number(op.area)), None)
    if area is None:
        area = {"id": op.area}
        proc["areas"].append(area)
    if area.get("networks") is None:
        area["networks"] = []
    area["networks"].append({"address": str(net.network_address),
                             "wildcard": str(net.hostmask)})
    return _changed(f"OSPF {op.process}: {asked} added", True)


#: Each operation's one implementation, by its model.
_APPLY = {SetDescription: _description, ClearDescription: _description, Shutdown: _admin,
          NoShutdown: _admin, AddVlan: _add_vlan, RemoveVlan: _remove_vlan,
          AddOspfNetwork: _ospf_network, RemoveOspfNetwork: _ospf_network}
#: Every operation a patch offers, by its ``op``, in the order above.
OPERATIONS = tuple(get_args(model.model_fields["op"].annotation)[0] for model in _APPLY)


def adds_vlan(patch) -> bool:
    """Whether *patch* (anything `parse` takes) adds a VLAN, so its caller reads the device's
    VLAN database (`vlan_capability.of`) for it; False for a patch `parse` refuses."""
    got, refusal = parse(patch)
    return not refusal and any(isinstance(op, AddVlan) for op in got.operations)


def apply(doc: dict, patch, vlan_database: dict = None) -> dict:
    """*patch* applied to the intent document *doc*, which is never changed: ``{"ok": True,
    "doc": the new document, "changes": [{"operation", "op", "summary", "changed",
    "device_keeps"}], "changed"}``, or a refusal naming the operation, what it asked and what
    the intent holds. Pure: reads and writes nothing. *vlan_database* is the device's VLAN
    database as its caller read it (`vlan_capability.of`); an added VLAN is refused unless it
    says yes (none given: unknown, refused). Removing a VLAN needs none: it takes a line out of
    intent, and nothing is sent for it (``device_keeps``)."""
    try:
        patch = _coerce(patch)
        if not isinstance(doc, dict):
            return _refusal(400, "intent", "the intent document is not a mapping")
        named = doc.get("hostname")
        if named and named != patch.hostname:
            return _refusal(400, "patch", (
                f"the patch is for {patch.hostname!r}, and this intent is {named!r}'s; a patch "
                "names the device it changes"))
        seen = {}
        for n, op in enumerate(patch.operations):
            key, words = _decides(op)
            if key in seen:
                first = seen[key]
                return _refusal(400, "patch", (
                    f"operations[{first}] ({patch.operations[first].op}) and operations[{n}] "
                    f"({op.op}) both decide {words}; one decision, one operation"),
                    operation=n)
            seen[key] = n
        out = copy.deepcopy(doc)
        changes = []
        for n, op in enumerate(patch.operations):
            extra = (vlan_database,) if isinstance(op, AddVlan) else ()
            changes.append({"operation": n, "op": op.op,
                            **_APPLY[type(op)](out, op, n, patch.hostname, *extra)})
    except Refused as exc:
        return exc.refusal
    return {"ok": True, "doc": out, "changes": changes,
            "changed": any(c["changed"] for c in changes)}


# ── the document's text, and the editor's path ───────────────────────────────

def patched_text(hostname: str, text: str, patch, list_name: str = "",
                 vlan_database: dict = None) -> dict:
    """The committed document *text* with *patch* applied, serialised by `hostvars.to_yaml`
    and checked by the editor's own validator: ``{"ok": True, "text", "was", "changes",
    "changed"}``, or the refusal (the validator's own when it refuses the result, with
    ``"refused_by": "validator"``). *vlan_database* goes to :func:`apply`."""
    from modules.nsot import hostvars, intent_edit

    try:
        patch = _coerce(patch)
    except Refused as exc:
        return exc.refusal
    if patch.hostname != hostname:
        return _refusal(400, "patch", (
            f"the patch is for {patch.hostname!r}, and the device is {hostname!r}; a patch "
            "names the device it changes"))
    checked = intent_edit.validate(hostname, text or "", list_name)
    if not checked["ok"]:
        return {**checked, "refused_by": "validator", "error": (
            f"{hostname}'s committed intent is refused by the editor's check before the patch: "
            + checked["error"])}
    doc = checked["parsed"]
    # The serialiser writes the patched document; one that does not round-trip through it
    # would lose its comments or layout silently (bulk intent's rule, `bulk_intent.plan`).
    if hostvars.to_yaml(doc) != text:
        return _refusal(409, "format", (
            f"{hostname}'s committed intent is hand-formatted: it does not round-trip through "
            "Mercury's serialiser, so writing the patch would silently drop its comments or "
            "layout. Normalise the formatting… on its Intent tab first: the editor proves the "
            "change is formatting only before it is committed"))
    got = apply(doc, patch, vlan_database)
    if not got["ok"]:
        return got
    new_text = hostvars.to_yaml(got["doc"])
    checked = intent_edit.validate(hostname, new_text, list_name)
    if not checked["ok"]:
        return {**checked, "refused_by": "validator", "changes": got["changes"], "error": (
            "The patched intent is refused by the editor's check: " + checked["error"])}
    return {"ok": True, "text": new_text, "was": text, "changes": got["changes"],
            "changed": got["changed"]}


def _capability(list_name: str, hostname: str, patch):
    """*hostname*'s VLAN database (`vlan_capability.of`: declared, else measured, else
    unknown), read once for a patch that adds a VLAN, from stored data only; None for any
    other patch, which never asks for it. Every path to a commit comes through here
    (`preview`, `commit`, `commit_many`), so no caller can leave it out."""
    if not adds_vlan(patch):
        return None
    from modules.nsot import vlan_capability
    return vlan_capability.of(list_name, hostname)


def _kept_words(changes: list) -> str:
    kept = [c["summary"] for c in changes if c.get("device_keeps")]
    if not kept:
        return ""
    return ("A merge-only deploy sends nothing for a line intent no longer holds, so the "
            "device keeps what these remove: " + "; ".join(kept) + ". A removal (Mode B) "
            "takes a line off only when its shape is measured on the device's platform; the "
            "deploy preview's removals say which.")


def preview(list_name: str, hostname: str, patch) -> dict:
    """What *patch* would do to *hostname*'s committed intent: the patched text handed to
    `intent_edit.preview` exactly, its answer with ``patch``, ``changes``, ``base`` (the blob
    patched) and ``yaml`` (the patched text). Writes nothing."""
    from modules.nsot import intent_edit

    opened = intent_edit.open_doc(list_name, hostname)
    if not opened["ok"]:
        return opened
    cap = _capability(list_name, hostname, patch)
    got = patched_text(hostname, opened["yaml"], patch, list_name, cap)
    if not got["ok"]:
        return {**got, "base": opened["base"]}
    patch = _coerce(patch)
    carried = {"patch": patch.model_dump(), "changes": got["changes"], "base": opened["base"],
               "yaml": got["text"], "device_keeps": _kept_words(got["changes"])}
    if not got["changed"]:
        return {"status": 200, "ok": True, "changed": False, **carried, "message": (
            f"Nothing to change: {hostname}'s committed intent already holds what the patch "
            "asks (" + "; ".join(c["summary"] for c in got["changes"]) + ").")}
    # The answer read for the patch is handed to the editor's check (C2061), which runs the
    # same VLAN check, so the preview reads it once.
    shown = intent_edit.preview(list_name, hostname, got["text"],
                                vlan_databases=None if cap is None else {hostname: cap})
    return {**shown, "changed": True, **carried}


def commit(list_name: str, hostname: str, patch, summary: str, base: str, actor: str, *,
           source: str = "", extra_trailers: list = None) -> dict:
    """Commit *patch* to *hostname*'s intent as *actor*: the patch applied to the version at
    *base* (the one previewed) and handed to `intent_edit.commit`, which refuses when intent
    moved since and requires the person's one-line *summary*. *source* and *extra_trailers*
    name the workflow, as `intent_edit.commit` takes them (its own when empty)."""
    from modules.nsot import hostvars, intent_edit

    base = (base or "").strip()
    if not base:
        return _refusal(400, "base", (
            f"Not saved: the patch did not say which version of {hostname}'s intent it was "
            "previewed on, so the save could replace a commit made since. Nothing was written. "
            "Preview the patch again"))
    text = hostvars.blob_text(intent_edit._repo_for(list_name), base)
    if text is None:
        return _refusal(409, "base", (
            f"Not saved: the version this patch was previewed on ({base[:12]}) is not in "
            f"{hostname}'s repository. Nothing was written. Preview the patch again"))
    cap = _capability(list_name, hostname, patch)
    got = patched_text(hostname, text, patch, list_name, cap)
    if not got["ok"]:
        return got
    out = intent_edit.commit(list_name, hostname, got["text"], summary, base, actor,
                             source=source or intent_edit.SOURCE,
                             extra_trailers=extra_trailers,
                             vlan_databases=None if cap is None else {hostname: cap})
    return {**out, "changes": got["changes"], "device_keeps": _kept_words(got["changes"])}


def commit_many(list_name: str, items: list, summary: str, actor: str, *, source: str = "",
                extra_trailers: list = None) -> dict:
    """Commit several devices' patches (``[(hostname, patch, base)]``) as ONE commit, each
    applied to the version it was previewed on, through `intent_edit.commit_many` (its moved,
    validator and secret refusals, nothing written on any): a two-ended change drafted in
    words (C1908). Each patched text is made first, so a patch refused on either device
    writes nothing on both."""
    from modules.nsot import hostvars, intent_edit

    edits, changes, caps = [], [], {}
    for hostname, patch, base in items:
        base = (base or "").strip()
        if not base:
            return _refusal(400, "base", (
                f"Not saved: the patch did not say which version of {hostname}'s intent it was "
                "previewed on, so the save could replace a commit made since. Nothing was "
                "written. Preview the patch again"))
        text = hostvars.blob_text(intent_edit._repo_for(list_name), base)
        if text is None:
            return _refusal(409, "base", (
                f"Not saved: the version this patch was previewed on ({base[:12]}) is not in "
                f"{hostname}'s repository. Nothing was written. Preview the patch again"))
        cap = _capability(list_name, hostname, patch)
        got = patched_text(hostname, text, patch, list_name, cap)
        if not got["ok"]:
            return got
        if cap is not None:
            caps[hostname] = cap
        edits.append((hostname, got["text"], base))
        changes += [dict(c, hostname=hostname) for c in got["changes"]]
    out = intent_edit.commit_many(list_name, edits, summary, actor,
                                  source=source or intent_edit.SOURCE,
                                  extra_trailers=extra_trailers, vlan_databases=caps)
    return {**out, "changes": changes, "device_keeps": _kept_words(changes)}
