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

**Quoted text never reaches the model** (the operator's order of 2026-10-27, item a;
:func:`hold_quotes`): each text the person quotes is taken out before anything else reads the
sentence and an opaque placeholder (``<<text_1>>``, ``<<text_2>>``, in order) put in its place;
after the answer is validated, the placeholders in its operations are put back with the exact
text. So text a person types is never read by the model as an instruction, never names an
interface, VLAN or device, and never widens the scope. The rules:
- **Which quotes:** straight and curly double quotes ("…", “…”) always. Single quotes ('…',
  ‘…’) only where they cannot be an apostrophe: the opening one at the start or after a space
  or an opening bracket, the closing one before the end, a space or punctuation, neither
  beside a space inside. An apostrophe inside a word (Gi0/2's, don't) never opens or closes
  one, and a single quote with no such partner stays as written.
- **Unbalanced:** a double quote with no partner (or a closing curly one with no opening) is
  Mercury's question before any call: close it or remove it.
- **Nested:** the first quote opens and its own kind closes; every other quote inside is part
  of the text (“spare for 'rack 4'” keeps 'rack 4'). Curly quotes nest by depth; straight ones
  cannot (the next " closes). Empty quotes ("") hold nothing and stay as written.
- **A placeholder in the words:** text outside quotes shaped like one (``<<text_1>>``) is
  Mercury's refusal before any call (quote it); inside quotes it is the person's text, kept.
- **After the answer** (:func:`to_patches`): a placeholder the model invents or alters, one
  it drops (each quoted text must be used), and one in a field that holds no free text (an
  interface, a prefix, an area) are each refused, naming it; only a description and a VLAN's
  name take one, among other words in a description. The patch's own rules then judge the real
  text (printable ASCII, at most 240). The draft, the question back and the refusal shown to
  the person carry the real text; History's call row keeps the request and answer as sent
  (placeholders), and its use row says what each placeholder stood for (masked).

**Requests Mercury answers itself, before any call** (item b and C1890): an operation outside
the vocabulary (:func:`not_an_operation`: switchport mode or access VLAN, a routed port, MTU,
speed, duplex, a static route, an OSPF cost), refused naming the operations there are; and on a
device's tab the questions `intent_names.questions` asks (alternatives, an OSPF network with no
area, a description with no text, both ends of a link with no managed far end), each answered
with controls that continue the same draft from the sentence as decided (C1907).

**Both ends of a link are one draft** (C1908, the operator's ruling on board F7-Q): a
two-ended request whose far end is a device of the network makes ONE draft holding both
devices' patches, each device's scope its own end; an answer changing one end only is a half
and refused; the two ends are judged before it is offered by what the draft does to them
(:func:`ends_judged`, C1933: committed intent against the intent the draft would leave), a
mismatch the draft creates or changes refused naming it, and one already in committed intent
that the draft leaves as it is said beside the draft, with whether this change may fail
because of it (the bearing rule, in its docstring); and one commit covers both (:func:`commit_pair`, `intent_edit.commit_many`). Its answer offers the paired deploy
(C1909, `modules.nsot.paired_deploy`): the plan for both devices, both ticked, the link
verified once both apply, and both rolled back if either end or the link fails.
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
    interfaces canonical, VLANs as numbers, networks as prefixes; each once, in its order.
    Text that becomes a value is never read (C1905, the operator's design of 2026-10-27): a
    quoted text is a placeholder by now, and a description's text ("describe X as …", "the
    description of X to …") and a VLAN's name are blanked first (`intent_names.blank_values`,
    the resolver's own), so "set the description on Gi1/0 to uplink to Gi0/1" names Gi1/0
    alone and an answer touching Gi0/1 is refused."""
    from modules.ai import intent_names
    return _named_parts(intent_names.blank_values(sentence or ""))


def named_in_values(sentence: str) -> list:
    """The interfaces *sentence* names only inside a value ("set Gi0/1's description to the same
    as Gi0/2's": Gi0/2), canonical, in order: given to the model to READ, never in the scope
    (C1942: a value that refers to another interface must be readable, and `touched` keeps it
    out of what may change)."""
    scoped = touched(sentence)["interfaces"]
    return [i for i in _named_parts(sentence or "")["interfaces"] if i not in scoped]


def _named_parts(s: str) -> dict:
    from modules.nsot import ifnames
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


# ── quoted text, held back from the model (the operator's order of 2026-10-27, item a) ──

#: A placeholder as Mercury issues it.
PLACEHOLDER = re.compile(r"<<text_[1-9][0-9]{0,2}>>")
#: Anything shaped as one, issued or not: an invented or altered placeholder in an answer, or
#: one typed outside quotes.
PLACEHOLDER_LIKE = re.compile(r"<<\s*[A-Za-z][\w -]{0,30}>>")
#: The fields of an operation that take quoted text; every other one holds a name or a number.
TEXT_FIELDS = ("description", "vlan_name")
_OPENS_SINGLE = " \t([{=:"
_CLOSES_SINGLE = " \t.,;:!?)]}"


def _single_close(s: str, i: int) -> int:
    """Where the single quote opened at *i* closes, or -1 when it cannot be a quote (an
    apostrophe): the opening one at the start or after a space or an opening bracket and not
    before a space, its partner the first matching quote after a non-space and before the
    end, a space or punctuation."""
    if (i and s[i - 1] not in _OPENS_SINGLE) or i + 1 >= len(s) or s[i + 1].isspace():
        return -1
    close = "'" if s[i] == "'" else "’"
    for k in range(i + 2, len(s)):
        if s[k] == close and not s[k - 1].isspace() and (
                k + 1 == len(s) or s[k + 1] in _CLOSES_SINGLE):
            return k
    return -1


def _double_close(s: str, i: int) -> int:
    """Where the double quote opened at *i* closes (straight: the next straight one; curly:
    its partner, nesting by depth), or -1."""
    if s[i] == '"':
        return s.find('"', i + 1)
    depth = 0
    for k in range(i, len(s)):
        depth += {"“": 1, "”": -1}.get(s[k], 0)
        if depth == 0:
            return k
    return -1


def quote_spans(sentence: str) -> tuple:
    """``([(open, close)], error)``: where each quote in *sentence* opens and closes (the
    indices of both quote characters), by the module's rules, left to right; *error* is
    ``(kind, words)`` for a double quote with no partner, else ``None``. The one reader of
    quotes: `hold_quotes` here, and the name resolver's spans (`intent_names.resolve`, C1906:
    an apostrophe is never a quote there either)."""
    s = sentence or ""
    spans, i = [], 0
    while i < len(s):
        c = s[i]
        j = -1
        if c in '"“':
            j = _double_close(s, i)
            if j < 0:
                return spans, ("unbalanced_quote", (
                    f"the sentence opens a quote it does not close (the {c} at character "
                    f"{i + 1}: {s[i:i + 24]!r}); close it, or remove it, and draft again, as "
                    "Mercury does not guess where quoted text ends; nothing was sent"))
        elif c == "”":
            return spans, ("unbalanced_quote", (
                f"the sentence closes a quote it never opened (the ” at character {i + 1}); "
                "open it, or remove it, and draft again; nothing was sent"))
        elif c in "'‘":
            j = _single_close(s, i)
        if j < 0:
            i += 1
            continue
        spans.append((i, j))
        i = j + 1
    return spans, None


def hold_quotes(sentence: str) -> dict:
    """``{"ok", "sentence", "quoted", "error", "detail"}``: *sentence* with each quoted text
    taken out and an opaque placeholder in its place (``<<text_1>>``, in order), and
    ``quoted`` the placeholders' exact texts. Refused (``ok`` false, Mercury's answer before
    any call): a double quote with no partner (``unbalanced_quote``), and text outside quotes
    shaped as a placeholder (``placeholder_in_words``). The module's docstring has the rules."""
    s = sentence or ""
    spans, error = quote_spans(s)
    if error:
        return {"ok": False, "sentence": "", "quoted": {}, "error": error[0],
                "detail": error[1]}

    def refused(error, detail):
        return {"ok": False, "sentence": "", "quoted": {}, "error": error, "detail": detail}

    out, quoted, at = [], {}, 0
    for i, j in spans:
        out.extend(s[at:i])
        if j == i + 1:
            out.extend(s[i:j + 1])          # empty quotes hold nothing and stay as written
        else:
            tag = f"<<text_{len(quoted) + 1}>>"
            quoted[tag] = s[i + 1:j]
            out.append(tag)
        at = j + 1
    out.extend(s[at:])
    # Only the words outside quotes: a placeholder's own text, or one quoted, is no collision.
    typed = PLACEHOLDER_LIKE.search("".join(" " if part in quoted else part for part in out))
    if typed:
        return refused("placeholder_in_words", (
            f"the sentence holds {typed.group(0)}, the form Mercury uses for quoted text, "
            "outside quotes; put it in quotes if it is text to keep, and draft again; nothing "
            "was sent"))
    return {"ok": True, "sentence": "".join(out), "quoted": quoted, "error": "", "detail": ""}


def restore(text: str, quoted: dict) -> str:
    """*text* with each placeholder Mercury issued put back as the exact text it stands for,
    in one pass (a quoted text that itself reads ``<<text_2>>`` is never replaced again)."""
    if not quoted or not isinstance(text, str):
        return text
    return PLACEHOLDER.sub(lambda m: quoted.get(m.group(0), m.group(0)), text)


def restored(choices: dict, quoted: dict) -> dict:
    """The model's answer (``model_dump``) with the real text in every place a person reads
    it: the question, why not, and each operation's text fields."""
    if not quoted:
        return choices
    out = dict(choices, question=restore(choices.get("question", ""), quoted),
               why_not=restore(choices.get("why_not", ""), quoted))
    out["patches"] = [dict(p, operations=[dict(o, **{f: restore(o.get(f, ""), quoted)
                                                     for f in TEXT_FIELDS})
                                          for o in p.get("operations") or []])
                      for p in choices.get("patches") or []]
    return out


def quoted_note(quoted: dict) -> str:
    """What each placeholder stood for, for the call's use row in History, masked as every
    record is (``<<text_1>> = "…"``; each text cut at 60 characters, said)."""
    if not quoted:
        return ""
    from modules import redact
    parts = []
    for tag, text in quoted.items():
        shown = text if len(text) <= 60 else text[:59] + "…"
        parts.append(f"{tag} = {json.dumps(shown, ensure_ascii=False)}")
    return redact.redact_text("quoted text put back: " + "; ".join(parts))


# ── requests no operation makes, refused before any call (C1890) ──────────────────────

#: Settings no operation makes, each as a request names it in a setting position (never a
#: word inside a description or a VLAN's name, which `intent_names.blank_values` blanks first):
#: an interface made a trunk, an access port or a routed port; switchport words; MTU, speed and
#: duplex set; a static route; an OSPF cost. Refusing by resemblance is safe (CLAUDE.md): a
#: person who meant something else rewords it. An address is not among them: "add the address
#: 192.0.2.1 to OSPF" is an OSPF network (one address is /32), so it stays the model's.
_STATE = r"(?:trunk|access|routed|switched|layer[- ]?[23])"
NOT_OPERATIONS = (
    ("an interface's switchport mode (trunk, access or routed) or its access VLAN", re.compile(
        r"\b(?:make|set|turn|configure|change|convert|put)\s+(?:[A-Za-z][A-Za-z-]*\s?\d+"
        r"(?:[/.:]\d+)*|it|them|this|that|(?:the|that|this|both|all)\s+[\w-]+(?:\s+(?:ports?"
        r"|links?|interfaces?))?)\s+"
        r"(?:(?:(?:to|into|as)\s+)(?:(?:an?|the)\s+)?" + _STATE + r"\b"
        r"|(?:an?|the)\s+" + _STATE + r"\b"
        r"|" + _STATE + r"(?:\s+(?:port|mode|vlan|link|interface))?"
        r"(?=\s*$|\s*[,.;]|\s+\d|\s+(?:and|on|for)\b))", re.I)),
    ("an interface's switchport mode or VLANs", re.compile(
        r"\bswitchport\b|\b(?:trunk|access)\s+mode\b|\bnative\s+vlan\b|\ballowed\s+vlans?\b"
        r"|\b(?:put|move|assign|place)\s+[A-Za-z][A-Za-z-]*\s?\d+(?:[/.:]\d+)*\s+(?:in|into|on"
        r"|to)\s+vlan\b", re.I)),
    ("an interface's MTU", re.compile(r"\bmtu\b", re.I)),
    ("an interface's speed or duplex", re.compile(
        r"\b(?:set|change|raise|lower|make)\s+(?:the\s+)?(?:[\w/.-]+['’]s\s+)?(?:speed|duplex)\b"
        r"|\bspeed\s+(?:of\s+|to\s+)?\d+|\b(?:full|half|auto)[- ]duplex\b|\bduplex\s+(?:full"
        r"|half|auto)\b", re.I)),
    ("a static route", re.compile(r"\bstatic\s+routes?\b|\bip\s+route\b", re.I)),
    ("an OSPF cost", re.compile(
        r"\b(?:set|change|raise|lower)\s+(?:the\s+)?(?:ospf\s+)?cost\b|\bospf\s+cost\b", re.I)),
)
#: The operations there are, in words, as a refusal names them.
OPERATIONS_IN_WORDS = ("descriptions (set or clear), shut and no shut, VLANs (add or remove) "
                       "and OSPF network statements (add or remove)")


def not_an_operation(sentence: str) -> str:
    """Why *sentence* asks for a change no operation makes, naming the operations there are,
    or "" (the module's docstring: decided by where the words stand, never inside a value)."""
    from modules.ai import intent_names
    text = intent_names.blank_values(sentence)
    for what, rx in NOT_OPERATIONS:
        m = rx.search(text)
        if m:
            return (f"{what} is set by no operation of a change in words (\"{m.group(0).strip()}"
                    f"\"): it drafts {OPERATIONS_IN_WORDS} only; make this change with Edit; "
                    "nothing was sent")
    return ""


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


def to_patches(answer: IntentChange, scope: dict, quoted: dict = None) -> dict:
    """``{"ok", "error", "patches"}``: each device's operations in `intent_patch`'s own shape,
    validated by `intent_patch.parse`; refused, naming why, BEFORE any preview, when an
    operation fills a field its op does not use, or changes what *scope* does not hold: a device
    out of scope, or an interface, VLAN or network the sentence did not name. *scope* is
    ``{hostname: touched(sentence)}``. *quoted* is `hold_quotes`' placeholders: each is put
    back with its exact text after these checks and before the patch's own rules; one the
    answer invents or alters, drops, or puts in a field that holds no free text is refused,
    naming it."""
    from modules.nsot import ifnames, intent_patch

    quoted = quoted or {}
    used = set()
    patches, parsed = [], []
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
            for f in mine:
                value = getattr(o, f)
                tags = PLACEHOLDER_LIKE.findall(value) if isinstance(value, str) else []
                if tags and f not in TEXT_FIELDS:
                    return {"ok": False, "error": f"{d.hostname}'s operation {i} "
                            f"({o.op.value}) puts {tags[0][:40]} in its {f}, which holds no "
                            "quoted text"}
                invented = [t for t in tags if t not in quoted]
                if invented:
                    return {"ok": False, "error": f"{d.hostname}'s operation {i} "
                            f"({o.op.value}) holds {invented[0][:40]}, a placeholder the "
                            "sentence does not have (it quotes "
                            + (", ".join(quoted) or "nothing") + ")"}
                used.update(tags)
            op = {"op": o.op.value}
            for f in mine:
                op["name" if f == "vlan_name" else f] = restore(getattr(o, f), quoted)
            ops.append(op)
        parsed.append((d.hostname, ops))
    dropped = [t for t in quoted if t not in used]
    if dropped and answer.patches:
        return {"ok": False, "error": "the answer leaves out the quoted text " + ", ".join(
            f"{json.dumps(quoted[t][:40], ensure_ascii=False)} ({t})" for t in dropped)
            + ", which the sentence gives"}
    for hostname, ops in parsed:
        patch, refusal = intent_patch.parse({"hostname": hostname, "operations": ops})
        if refusal:
            return {"ok": False, "error": f"{hostname}: {refusal['error']}"}
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


# ── both ends of a link, as one draft (C1908, the operator's ruling on board F7-Q) ─────

def _lines(i: dict) -> list:
    """Every line an interface's intent holds in a list of text (its switchport, OSPF and
    unmodelled lines among them), stripped."""
    out = []
    for v in (i or {}).values():
        if isinstance(v, list):
            out += [str(x).strip() for x in v if isinstance(x, str)]
    return out


def _vlan_set(entries) -> set:
    """A trunk's allowed VLANs as a set of numbers ("all" for none listed, or "all")."""
    out = set()
    for entry in entries or []:
        for part in str(entry).replace(" ", "").split(","):
            if not part:
                continue
            if part.lower() in ("all", "1-4094"):
                return {"all"}
            if "-" in part:
                lo, _s, hi = part.partition("-")
                if lo.isdigit() and hi.isdigit():
                    out |= {str(n) for n in range(int(lo), int(hi) + 1)}
                    continue
            out.add(part)
    return out or {"all"}


def _shown_vlans(vlans: set) -> str:
    if "all" in vlans:
        return "all VLANs"
    nums = sorted(int(v) for v in vlans if v.isdigit())
    return "VLANs " + ", ".join(str(n) for n in nums) if nums else "no VLAN"


def _address(doc: dict, text: str):
    """An IPv4 address *text* names: itself, or the address of the interface of *doc* it names
    (a tunnel's source); ``None`` when neither."""
    from modules.nsot import ifnames
    try:
        return ipaddress.IPv4Address(text)
    except ValueError:
        pass
    for i in (doc or {}).get("interfaces") or []:
        if isinstance(i, dict) and ifnames.same_interface(str(i.get("name", "")), text):
            got = _iface_net(i)
            return got.ip if got else None
    return None


def _iface_net(i: dict):
    """An interface's IPv4 address and network (``IPv4Interface``), or ``None``."""
    words = str((i or {}).get("ipv4") or "").split()
    try:
        if len(words) >= 2:
            return ipaddress.IPv4Interface(f"{words[0]}/{words[1]}")
        if len(words) == 1:
            return ipaddress.IPv4Interface(words[0])
    except ValueError:
        return None
    return None


def _ospf_of(doc: dict, i: dict) -> dict:
    """``{"area", "auth", "v3_area"}`` of an interface: its OSPFv2 area (the network statement
    covering its address), its authentication type (the interface's own, else its area's),
    and its OSPFv3 area (its `ospfv3` lines); each "" when it has none."""
    from modules.nsot import intent_patch
    net = _iface_net(i)
    area, procs = "", []
    routing = doc.get("routing") if isinstance(doc.get("routing"), dict) else {}
    for proc in routing.get("ospf") or []:
        if not isinstance(proc, dict):
            continue
        procs.append(proc)
        for (address, wild), a, _where in intent_patch._statements(proc):
            if net is not None and (int(net.ip) & ~wild & 0xFFFFFFFF) == (
                    int(ipaddress.IPv4Address(address)) & ~wild & 0xFFFFFFFF):
                area = str(a)
    auth = ""
    for line in (i or {}).get("ospf") or []:
        m = re.match(r"authentication(?:\s+(message-digest|null|key-chain))?", str(line).strip())
        if m:
            auth = m.group(1) or "plain"
    if not auth and area:
        for proc in procs:
            for line in proc.get("settings") or []:
                m = re.match(rf"area\s+{re.escape(area)}\s+authentication(?:\s+(message-digest))?$",
                             str(line).strip())
                if m:
                    auth = m.group(1) or "plain"
    v3 = ""
    for line in (i or {}).get("ospfv3") or []:
        m = re.search(r"\barea\s+(\S+)", str(line))
        if m:
            v3 = m.group(1)
    return {"area": area, "auth": auth or ("none" if area else ""), "v3_area": v3}


#: The families a link's match facts fall in (C1933), as the warning names them.
FAMILIES = {"trunk": "trunk", "tunnel": "tunnel", "ospf": "OSPF", "ospfv3": "OSPFv3"}


def _link_checks(a: str, doc_a: dict, port_a: str, b: str, doc_b: dict, port_b: str) -> dict:
    """The facts `ends_match` judges, each mismatch kept apart: ``{"mismatches": [...],
    "facts": [...], "ends": (a's, b's)}``. A mismatch is ``{"key", "family", "values",
    "short", "rule"}``: which fact (the same key before and after a draft), its family
    (:data:`FAMILIES`; ``None`` for an end not in its device's intent, which cannot be
    checked), both ends' values as compared, the words naming them, and what a link needs.
    *ends* is each end's own values by family (``None`` for an end not in its intent): what a
    draft changing that family changes (`ends_judged`)."""
    from modules.nsot import ifnames

    def iface(doc, name):
        return next((i for i in (doc or {}).get("interfaces") or [] if isinstance(i, dict)
                     and ifnames.same_interface(str(i.get("name", "")), name)), None)

    def native(i):
        return next((m.group(1) for line in _lines(i) for m in [re.search(
            r"\bnative\s+vlan\s+(\d+)", line)] if m), "1")

    def tun(i, what):
        return next((m.group(1) for line in _lines(i) for m in [re.match(
            rf"tunnel\s+{what}\s+(\S+)", line)] if m), "")

    tunnels = all(str(n).lower().startswith("tunnel") for n in (port_a, port_b))
    ia, ib = iface(doc_a, port_a), iface(doc_b, port_b)
    end_a, end_b = f"{a} {port_a}", f"{b} {port_b}"
    bad, facts = [], []

    def mismatch(key, family, values, short, rule=""):
        bad.append({"key": key, "family": family, "values": tuple(str(v) for v in values),
                    "short": short, "rule": rule})

    if ia is None or ib is None:
        missing = end_a if ia is None else end_b
        mismatch("missing", None, (missing,), f"{missing} is not in its device's intent")
        return {"mismatches": bad, "facts": [], "ends": (None, None)}

    def own(doc, i):
        o = _ospf_of(doc, i)
        net = _iface_net(i)
        return {"trunk": (str(i.get("switchport_mode") or ""),
                          tuple(sorted(_vlan_set(i.get("switchport_trunk_vlans")))), native(i)),
                "tunnel": (tun(i, "source"), tun(i, "destination"),
                           str(net.network) if net else "") if tunnels else (),
                "ospf": (o["area"], o["auth"]), "ospfv3": (o["v3_area"],)}
    mode_a, mode_b = str(ia.get("switchport_mode") or ""), str(ib.get("switchport_mode") or "")
    if "trunk" in (mode_a, mode_b):
        if mode_a != mode_b:
            mismatch("trunk_mode", "trunk", (mode_a, mode_b),
                     f"{end_a} is {mode_a or 'not a switchport'} and {end_b} is "
                     f"{mode_b or 'not a switchport'}", "both ends of a trunk are trunks")
        else:
            va, vb = (_vlan_set(i.get("switchport_trunk_vlans")) for i in (ia, ib))
            na, nb_ = native(ia), native(ib)
            if va != vb:
                mismatch("trunk_vlans", "trunk", (_shown_vlans(va), _shown_vlans(vb)),
                         f"{end_a} allows {_shown_vlans(va)} and {end_b} allows "
                         f"{_shown_vlans(vb)}", "both ends of a trunk carry the same VLANs")
            if na != nb_:
                mismatch("native_vlan", "trunk", (na, nb_),
                         f"{end_a} has native VLAN {na} and {end_b} native VLAN {nb_}",
                         "both ends of a trunk carry the same native VLAN")
            if va == vb and na == nb_:
                facts.append(f"both trunks, {_shown_vlans(va)}, native VLAN {na}")
    if tunnels:
        src_a, dst_a, src_b, dst_b = (tun(ia, "source"), tun(ia, "destination"),
                                      tun(ib, "source"), tun(ib, "destination"))
        for key, end, dst, other, src, doc in (
                ("tunnel_destination_a", end_a, dst_a, end_b, src_b, doc_b),
                ("tunnel_destination_b", end_b, dst_b, end_a, src_a, doc_a)):
            addr = _address(doc, src) if src else None
            if not dst or addr is None:
                mismatch(key, "tunnel", (dst, src, addr or ""),
                         f"{end}'s tunnel destination ({dst or 'none'}) cannot be checked "
                         f"against {other}'s source ({src or 'none'})")
            elif str(addr) != dst:
                mismatch(key, "tunnel", (dst, src, addr),
                         f"{end}'s tunnel destination is {dst}, and {other}'s source is {addr}",
                         "each end's destination is the other's source")
    na_, nb2 = _iface_net(ia), _iface_net(ib)
    if na_ is not None and nb2 is not None:
        if na_.network != nb2.network:
            if tunnels:
                mismatch("tunnel_network", "tunnel", (na_.network, nb2.network),
                         f"{end_a} is in {na_.network} and {end_b} in {nb2.network}",
                         "both ends of a tunnel share one network")
        else:
            facts.append(f"both in {na_.network}")
    oa, ob = _ospf_of(doc_a, ia), _ospf_of(doc_b, ib)
    if oa["area"] or ob["area"]:
        if oa["area"] != ob["area"]:
            mismatch("ospf_area", "ospf", (oa["area"], ob["area"]),
                     f"{end_a} is in OSPF area {oa['area'] or '(none)'} and {end_b} in "
                     f"{ob['area'] or '(none)'}", "both ends of a link share one area")
        elif oa["auth"] != ob["auth"]:
            mismatch("ospf_auth", "ospf", (oa["auth"], ob["auth"]),
                     f"{end_a} authenticates OSPF as {oa['auth']} and {end_b} as {ob['auth']}",
                     "both ends use one authentication type")
        else:
            facts.append(f"OSPF area {oa['area']}, authentication {oa['auth']}")
    if oa["v3_area"] or ob["v3_area"]:
        if oa["v3_area"] != ob["v3_area"]:
            mismatch("ospfv3_area", "ospfv3", (oa["v3_area"], ob["v3_area"]),
                     f"{end_a} is in OSPFv3 area {oa['v3_area'] or '(none)'} and {end_b} in "
                     f"{ob['v3_area'] or '(none)'}", "both ends of a link share one area")
        else:
            facts.append(f"OSPFv3 area {oa['v3_area']}")
    return {"mismatches": bad, "facts": facts, "ends": (own(doc_a, ia), own(doc_b, ib))}


def _said(m: dict) -> str:
    return f"{m['short']}; {m['rule']}" if m["rule"] else m["short"]


def ends_match(a: str, doc_a: dict, port_a: str, b: str, doc_b: dict, port_b: str) -> dict:
    """``{"mismatches": [...], "facts": [...]}``: whether the two ends of a link match in one
    pair of intent documents (C1908): a trunk's allowed and native VLANs, a tunnel's source,
    destination and addressing, the OSPF area (OSPFv2 by the statement covering each end's
    address, OSPFv3 by its interface lines) and the OSPF authentication type. Each mismatch
    names both ends' values; each fact is what the two ends share, said in the draft. A draft
    is judged by `ends_judged`, which compares this before and after it (C1933)."""
    got = _link_checks(a, doc_a, port_a, b, doc_b, port_b)
    return {"mismatches": [_said(m) for m in got["mismatches"]], "facts": got["facts"]}


def ends_judged(a: str, port_a: str, b: str, port_b: str, before: tuple, after: tuple) -> dict:
    """``{"refused": [...], "existing": [...], "facts": [...]}``: a two-device draft's ends
    judged by what the draft does to them (C1933, the operator's decision of 2026-10-27),
    *before* the two devices' committed intent and *after* the intent the draft would leave
    (each ``(a's document, b's document)``), fact by fact as `ends_match` reads them:

    - a fact that matched before (or was not there) and does not after, or a mismatched fact
      whose values the draft changes: **refused**, naming both ends' values, as `ends_match`
      says it; so is an end not in its device's intent after the draft, which cannot be
      checked at all (and a committed version that cannot be read counts as one, so the
      draft is refused rather than let through unjudged);
    - a fact mismatched before and left with the same values after: **existing**, each
      ``{"said", "bears", "fact"}``: said beside the draft, which proceeds.

    **The bearing rule.** An existing mismatch *bears* on the draft when the draft changes any
    fact of the mismatch's own family on either end of this link, each end's values read as
    `ends_match` reads them: the trunk (switchport mode, allowed VLANs, native VLAN), the
    tunnel (source, destination and the tunnel's network, on a link of two tunnels), OSPF
    (the OSPFv2 area and authentication type) and OSPFv3 (its area). Those are the facts an
    adjacency or a trunk forms on together, so a change to one of them is verified against a
    link the existing mismatch already breaks, and the warning says the change may fail
    because of it. A change outside the family (a description, a shutdown, the other OSPF
    version) does not bear: it is said as untouched. OSPFv3 has one fact, its area, so a
    draft changing it changes the mismatch itself and is refused; its family is apart from
    OSPFv2's because neither version's adjacency forms on the other's area. *facts* are what
    the ends share after the draft."""
    was = _link_checks(a, before[0], port_a, b, before[1], port_b)
    now = _link_checks(a, after[0], port_a, b, after[1], port_b)
    held = {m["key"]: m["values"] for m in was["mismatches"] if m["family"]}
    refused, existing = [], []
    for m in now["mismatches"]:
        if m["family"] is None or held.get(m["key"]) != m["values"]:
            refused.append(_said(m))
            continue
        bears = any(w is not None and n is not None and w[m["family"]] != n[m["family"]]
                    for w, n in zip(was["ends"], now["ends"]))
        said = f"{m['short']}, already in committed intent; " + (
            f"this change touches the link's {FAMILIES[m['family']]} settings and may fail "
            "because of it" if bears else "this change does not touch it")
        existing.append({"said": said, "bears": bears, "fact": m["key"]})
    return {"refused": refused, "existing": existing, "facts": now["facts"]}


def pair_digest(items: list) -> str:
    """What a two-device draft offers to commit, as one digest: each device, its patch exactly
    and the version of its intent it was previewed on, in the order drafted. A commit of
    either end alone, or of anything else, is refused (`commit_pair`)."""
    import hashlib
    text = json.dumps([{"hostname": h, "patch": p, "base": b or ""} for h, p, b in items],
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(("pair:" + text).encode("utf-8")).hexdigest()


#: What a two-device commit's answer offers next (C1909, board F7-Q): the plan for both
#: devices, both ticked, the link carried, as one change (`modules.nsot.paired_deploy`).
PAIRED_DEPLOY = ("Deploy both ends opens the plan for {a} and {b}, both ticked: one preview, one "
                 "confirm by hash; verify then reads the link, and if either end fails, both are "
                 "rolled back")


# ── the call ─────────────────────────────────────────────────────────────────

FEATURE = "intent_patch"
#: v2 (the operator's order of 2026-10-27, item a): quoted text reaches the model only as
#: opaque placeholders (`hold_quotes`), and the prompt says what they are and where they may
#: stand. v1 stays for its record (the measurements of 2026-10-26 and 27 were made on it).
PROMPT = ("intent_change", 2)

#: The steps, as the manual's How it works page names them (docs/manual/how-it-works/
#: intent-in-words.md).
STEPS = (
    ("quote", "quoted text taken out and opaque placeholders put in its place, before anything "
              "reads the sentence; an unclosed quote is asked about with nothing sent"),
    ("scope", "the device, and the interfaces, VLANs and networks the sentence names, read by "
              "code; a sentence naming none stops there with nothing sent"),
    ("screen", "a change no operation makes refused, naming the operations; on a tab, "
               "alternatives, an OSPF network with no area, a description with no text and a "
               "two-ended request whose far end is not a managed device each asked about, "
               "answered with controls that continue the draft; both ends of a link to a "
               "managed device made one two-device draft; all before any call"),
    ("resolve", "the names as people say them, resolved by code against the device's intent "
                "and neighbours (G1/0, the host port, the uplink to edge1); several matches ask "
                "which, none says so with the device's interfaces, all before any call"),
    ("ask","one recorded, capped call through the AI gateway, as the person who asked, with "
            "only the named parts' current values"),
    ("check", "the draft refused before any preview if it changes what the sentence did not "
              "name, or invents, drops or misplaces a placeholder; the quoted text then put "
              "back exactly, and the patch's own rules hold"),
    ("preview", "the intent editor's own preview: what the change does, what a deploy would "
                "send, its checks; nothing is written"),
    ("commit", "the person commits the draft exactly as drafted (refused if the intent moved "
               "or the patch differs), as Source: ai-draft with its AI-Call; Commit and plan "
               "deploy opens the deploy preview, never confirmed for them"),
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


def change(list_name: str, sentence: str, *, actor: str, trigger: dict, send=None,
           today: str = None, devices: list = None, picks: dict = None,
           answer: dict = None) -> dict:
    """``{"ok", "error", "detail", "previews", "call_id", "cost_usd", "resolutions", ...}``:
    *sentence* made a patch per device it changes, each previewed by the intent editor
    (nothing written); or one question back, or a refusal naming why, with nothing previewed.
    *devices* limits the scope (a device's Intent tab). On a tab the device's names are
    resolved first (`intent_names.resolve`: shorthand and references), so the model is given
    the device's own names only; *picks* is the person's answer to Mercury's own question
    about which one. Mercury answers itself, with no call and nothing spent, when the sentence
    names no device in scope or nothing to change, when a reference matches several and the
    person must choose ("choose"), or when it matches nothing or names an interface the device
    lacks ("no_such_interface"); and before those (`screen`), when a quote is left open or a
    placeholder typed, when the change is one no operation makes ("not_an_operation"), and on
    a tab when the words leave a choice only the person can make ("two_ended",
    "alternatives", "no_area", "no_value"). Quoted text reaches the model only as placeholders
    (`hold_quotes`), put back after the answer is checked. *answer* (``{"kind", "value"}``) is
    the person's answer to such a question (*trigger*, C1843's, carried into the continued
    draft unchanged): the draft continues from the sentence as decided
    (``decided`` in the answer), with no retyping (C1907). A two-ended request whose far end is
    a device of the network is ONE draft of both devices' patches, checked to match before
    any preview (``pair``; C1908)."""
    from modules.ai.nl_query import QUESTION_MAX

    words = " ".join((sentence or "").split())
    if not words:
        return {"ok": False, "error": "empty", "detail": "type the change first"}
    if len(words) > QUESTION_MAX:
        return {"ok": False, "error": "too_long",
                "detail": f"the sentence is {len(words)} characters; at most "
                          f"{QUESTION_MAX} are taken"}
    pre = screen(list_name, sentence, devices, picks, answer)
    if pre.get("decided") is not None:
        # The person's answer to Mercury's own question (C1907): the same draft continues
        # from the sentence as decided, shown to them, with no retyping.
        decided = pre["decided"]
        if len(" ".join(decided.split())) > QUESTION_MAX:
            return dict(_MERCURY, error="too_long", words=words, detail=(
                f"the sentence as decided is {len(decided)} characters; at most "
                f"{QUESTION_MAX} are taken"))
        return dict(change(list_name, decided, actor=actor, trigger=trigger, send=send,
                           today=today, devices=devices), decided=" ".join(decided.split()))
    if pre.get("refusal"):
        return dict(pre["refusal"], words=words)
    extra = {"words": words, "sent": pre["sentence"], "resolutions": pre["resolutions"],
             "resolution_said": pre["said"]}
    return dict(_drafted(list_name, pre["sentence"], pre["named"], actor=actor,
                         trigger=trigger, send=send, today=today, quoted=pre["quoted"],
                         pair=pre.get("pair")), **extra)


#: Mercury's own answer before any call: no call id, nothing spent.
_MERCURY = {"ok": False, "by": "mercury", "call_id": "", "cost_usd": 0.0}


def requote(sentence: str, quoted: dict) -> str:
    """*sentence* (as `hold_quotes` left it) with each placeholder back in quotes, the person's
    exact text inside, so the sentence as decided reads as they typed it and is held again."""
    from modules.ai import intent_names

    def back(m):
        text = quoted.get(m.group(0))
        if text is None:
            return m.group(0)
        return intent_names.quoted_value(text)[0] or m.group(0)
    return PLACEHOLDER.sub(back, sentence or "")


def screen(list_name: str, sentence: str, devices: list = None, picks: dict = None,
           answer: dict = None) -> dict:
    """Everything decided before any call, in order (STEPS `quote`, `scope`, `screen`,
    `resolve`): ``{"named", "sentence", "quoted", "resolutions", "said", "pair"}``, *sentence*
    as the model is given it (quoted text as placeholders, names resolved; a two-ended request
    rewritten to name both ends, *pair* the link); or ``{"refusal": <change's answer>}`` when
    Mercury answers itself; or ``{"decided": <sentence>}`` when *answer* (``{"kind",
    "value"}``) answers Mercury's own question, the sentence as decided, quotes back in place."""
    # Quotes first, from the words as typed: the text inside is kept exactly (its spaces too),
    # and the rest is read with its spaces collapsed.
    held = hold_quotes((sentence or "").strip())
    if not held["ok"]:
        return {"refusal": dict(_MERCURY, error=held["error"], detail=held["detail"])}
    masked = " ".join(held["sentence"].split())
    scope = scope_of(list_name, masked, devices)
    if not scope["ok"]:
        return {"refusal": dict(scope, by="mercury", call_id="", cost_usd=0.0)}
    named = scope["named"]
    outside = not_an_operation(masked)
    if outside:
        return {"refusal": dict(_MERCURY, error="not_an_operation", detail=outside)}
    resolved = {"sentence": masked, "resolutions": [], "said": []}
    if devices and len(named) == 1:
        resolved = resolve_names(list_name, named[0], masked, picks, answer)
        if resolved.get("decided") is not None:
            return {"decided": requote(resolved["decided"], held["quoted"])}
        if resolved.get("refusal"):
            return resolved
        if resolved.get("pair"):
            named = [named[0], resolved["pair"]["far"]]
    elif answer:
        return {"refusal": dict(_MERCURY, error="not_an_answer", detail=(
            "an answer to Mercury's question is taken on a device's Intent tab only; nothing "
            "was sent"))}
    return {"named": named, "sentence": resolved["sentence"], "quoted": held["quoted"],
            "resolutions": resolved["resolutions"], "said": resolved["said"],
            "pair": resolved.get("pair")}


def resolve_names(list_name: str, device: str, sentence: str, picks: dict = None,
                  answer: dict = None) -> dict:
    """*sentence*'s names on *device* resolved against its committed intent and neighbours:
    ``{"sentence", "resolutions", "said", "pair"}``, or ``{"refusal": <change's answer>}`` when
    the person must choose, a name resolves to nothing, or the words leave a choice only the
    person can make (`intent_names.questions`, asked first, its controls continuing the draft:
    ``{"decided": <sentence>}`` for *answer*). A two-ended request whose far end is a device
    of the network is one draft of both (``pair``, C1908), its sentence naming both ends. A
    device with no committed intent is left as written: the slice says so after (`slices`)."""
    from modules.ai import intent_names
    from modules.nsot import hostvars, intent_edit

    opened = intent_edit.open_doc(list_name, device)
    if not opened["ok"]:
        return {"sentence": sentence, "resolutions": [], "said": []}
    try:
        doc = hostvars.from_yaml(opened["yaml"]) or {}
    except Exception:                                   # noqa: BLE001 (`slices` says it)
        return {"sentence": sentence, "resolutions": [], "said": []}
    if answer:
        d = intent_names.decide(list_name, device, doc, sentence, answer.get("kind", ""),
                                str(answer.get("value", "")))
        if not d["ok"]:
            return {"refusal": dict(_MERCURY, error="not_an_answer", detail=(
                f"{d['error']}; nothing was sent"))}
        return {"decided": d["sentence"]}
    q = intent_names.questions(list_name, device, doc, sentence)
    pair = None
    if q and q["kind"] == "pair":
        pair, sentence = q, q["sentence"]
    elif q:
        return {"refusal": dict(_MERCURY, error=q["kind"], question=q, resolutions=[],
                                resolution_said=[], detail=(
                                    f"one question first, from {device}'s own intent: "
                                    f"{q['question']}; nothing was sent"))}
    got = intent_names.resolve(list_name, device, doc, sentence, picks)
    mercury = dict(_MERCURY, resolutions=got["resolutions"], resolution_said=got["said"])
    if got["ask"]:
        a = got["ask"]
        return {"refusal": dict(mercury, error="choose", choose=a, detail=(
            f"one question first, from {device}'s own intent: {a['question']}"))}
    if got["unknown"]:
        u = got["unknown"]
        return {"refusal": dict(mercury, error="no_such_interface", unknown=u, detail=(
            f"{u['why']}; choose one of its interfaces, or see its neighbours; nothing was "
            "sent"))}
    return {"sentence": got["sentence"], "resolutions": got["resolutions"],
            "said": got["said"], "pair": pair}


def _scopes(t: dict, named: list, pair: dict) -> dict:
    """What each device may change: the sentence's own named parts for each, and for a
    two-device draft (*pair*) the far device its own end alone (and the VLANs and networks
    named), the near device everything but the far end's port."""
    from modules.nsot import ifnames
    if not pair:
        return {h: t for h in named}
    near, far = pair["device"], pair["far"]
    mine = [n for n in t["interfaces"] if ifnames.same_interface(n, pair["port"])
            or not ifnames.same_interface(n, pair["far_port"])]
    return {near: dict(t, interfaces=mine),
            far: dict(t, interfaces=[ifnames.canonical(pair["far_port"])])}


def _drafted(list_name: str, sentence: str, named: list, *, actor: str, trigger: dict,
             send, today, quoted: dict = None, pair: dict = None) -> dict:
    """`change` from the resolved *sentence* on: the touched sections, the call, and the
    answer converted, scope-checked, its placeholders put back (*quoted*) and previewed. What
    the person reads (the question, why not, the draft, `choices`) carries the real text; each
    use row says what the placeholders stood for (`quoted_note`)."""
    from modules.ai import calls, gateway
    from modules.nsot import intent_patch

    quoted = quoted or {}
    note = quoted_note(quoted)

    def detail(*parts):
        # A use row's words may hold the person's quoted text: masked, as every record is.
        from modules import redact
        return redact.redact_text("; ".join(p for p in parts + (note,) if p))[:400]

    t = touched(sentence)
    if nothing_named(t):
        return {"ok": False, "error": "nothing_named", "by": "mercury", "call_id": "",
                "cost_usd": 0.0, "named": named, "detail": (
                    "the sentence names no interface, VLAN or OSPF network to change; name it "
                    "as the device does (GigabitEthernet0/1, VLAN 40, 192.0.2.0/24); nothing "
                    "was sent")}
    scopes = _scopes(t, named, pair)
    # What the model reads: each device's scope plus, for the device the words are about (a
    # pair's near end), the interfaces named only inside a value (C1942); the answer is still
    # held to `scopes` alone.
    extra = named_in_values(sentence)
    reads = {h: dict(s, interfaces=s["interfaces"] + [i for i in extra
                                                      if i not in s["interfaces"]])
             if extra and (not pair or h == pair["device"]) else s
             for h, s in scopes.items()}
    got = slices(list_name, named, t, per_host=reads)
    if got["missing"]:
        return {"ok": False, "error": "no_intent", "by": "mercury", "call_id": "",
                "cost_usd": 0.0, "detail": "; ".join(f"{h}: {why}" for h, why in
                                                      got["missing"]) + "; nothing was sent"}
    subject = {"kind": "intent", "id": list_name, "devices": list(named)}
    asked = gateway.ask(FEATURE, PROMPT, IntentChange, parts(sentence, named, got["devices"]),
                        actor=actor, trigger=trigger, context={"operations": vocabulary()},
                        send=send, today=today, subject=subject, network=list_name)
    if not asked["ok"]:
        return asked
    answer = asked["output"]
    choices = restored(answer.model_dump(mode="json"), quoted)
    base = {"call_id": asked["call_id"], "cost_usd": asked["cost_usd"], "choices": choices}
    links = {"page": f"/v2/device/{named[0]}?tab=intent"}
    question, why_not = choices["question"][:200], choices["why_not"][:200]
    if answer.outcome is Outcome.ask:
        calls.record_use(asked["call_id"], "asked a question back", actor=actor,
                         detail=detail(answer.question[:200]), links=links)
        return dict(base, ok=False, error="ask", clarify=question,
                    detail=f"one question first: {question}")
    if answer.outcome is Outcome.refuse:
        calls.record_use(asked["call_id"], "shown: the operations cannot make it", actor=actor,
                         detail=detail(answer.why_not[:200]), links=links)
        return dict(base, ok=False, error="unanswerable",
                    detail=f"this change cannot be drafted in words: {why_not}")
    if not answer.patches:
        calls.record_use(asked["call_id"], "refused by validation", actor=actor,
                         detail=detail("an answer with no patch"), links=links)
        return dict(base, ok=False, error="couldnt_change",
                    detail="the answer changes no device; nothing is previewed")
    made = to_patches(answer, scopes, quoted)
    if made["ok"] and pair:
        # Never a half (PHASE8_PLAN 16.10): a two-device draft changes both ends or neither.
        drafted = {p.hostname for p in made["patches"]}
        if drafted != {pair["device"], pair["far"]}:
            made = {"ok": False, "error": (
                f"the request changes both ends, {pair['device']} {pair['port']} and "
                f"{pair['far']} {pair['far_port']}, and the answer changes "
                + (", ".join(sorted(drafted)) or "neither") + " only")}
    if not made["ok"]:
        calls.record_use(asked["call_id"], "refused by validation", actor=actor,
                         detail=detail(made["error"][:200]), links=links)
        return dict(base, ok=False, error="couldnt_change",
                    detail=f"{made['error']}; nothing is previewed")
    previews = [dict(intent_patch.preview(list_name, p.hostname, p), hostname=p.hostname)
                for p in made["patches"]]
    refused = [p for p in previews if not p.get("ok")]
    if pair and not refused:
        return _pair_drafted(list_name, base, previews, pair, asked["call_id"], actor, links,
                             detail)
    for p in previews:
        # What a commit of this draft must be handed exactly (part 2): its digest is on the
        # call's use row, so a commit of any other patch, or on any other version, is refused.
        if p.get("ok") and p.get("changed") and p.get("vs_intent_changed", True):
            p["draft"] = draft_digest(p["hostname"], p.get("patch"), p.get("base"))
    calls.record_use(asked["call_id"], "refused by the intent" if refused else
                     "previewed in the intent editor", actor=actor,
                     detail=detail("; ".join(f"{p['hostname']}: {p.get('error', '')}"
                                             for p in refused)[:200]), links=links,
                     drafts=[p["draft"] for p in previews if p.get("draft")])
    return dict(base, ok=not refused, error="intent" if refused else "", previews=previews,
                detail="; ".join(f"{p['hostname']}: {p.get('error', '')}" for p in refused))


def _pair_judged(list_name: str, pair: dict, shown: list) -> dict:
    """`ends_judged` for a two-device draft's previews (*shown*, near end first): before is
    each device's intent at the version its preview patched (``base``), after the text the
    preview made (``yaml``). A document that cannot be read is judged as empty, so its end
    is not in its intent and the draft is refused."""
    from modules.nsot import hostvars, intent_edit

    def doc(text):
        try:
            return hostvars.from_yaml(text or "") or {}
        except Exception:                               # noqa: BLE001 (said as a mismatch)
            return {}
    repo = intent_edit._repo_for(list_name)
    before = tuple(doc(hostvars.blob_text(repo, p["base"]) if p.get("base") else "")
                   for p in shown)
    after = tuple(doc(p.get("yaml")) for p in shown)
    return ends_judged(pair["device"], pair["port"], pair["far"], pair["far_port"], before,
                       after)


def _pair_drafted(list_name: str, base: dict, previews: list, pair: dict, call_id: str,
                  actor: str, links: dict, detail) -> dict:
    """A two-device draft's end (C1908): the two ends judged by what the draft does to them
    (`ends_judged`, C1933): a mismatch the draft creates or changes refused naming it; else
    both previews, near end first, any mismatch already in committed intent said beside them,
    offered as ONE commit (`pair_digest` on the call's use row), never either alone."""
    from modules.ai import calls

    order = {pair["device"]: 0, pair["far"]: 1}
    previews = sorted(previews, key=lambda p: order.get(p["hostname"], 2))
    near, far = previews
    got = _pair_judged(list_name, pair, previews)
    if got["refused"]:
        why = "the two ends would not match: " + "; ".join(got["refused"])
        calls.record_use(call_id, "refused: the ends would not match", actor=actor,
                         detail=detail(why[:200]), links=links)
        return dict(base, ok=False, error="ends_mismatch", detail=f"{why}; nothing is previewed")
    link = dict(pair, facts=got["facts"], existing=got["existing"])
    # What the call's record says of a mismatch already in committed intent (C1933).
    differ = "; ".join(e["said"] for e in got["existing"])
    differ = f"the ends already differ: {differ}" if differ else ""
    if not all(p.get("changed") and p.get("vs_intent_changed", True) for p in previews):
        # Already so on one end or both: nothing to commit as one change.
        calls.record_use(call_id, "previewed in the intent editor", actor=actor,
                         detail=detail("both ends; already so on "
                                       + ", ".join(p["hostname"] for p in previews
                                                   if not p.get("changed")
                                                   or not p.get("vs_intent_changed", True)),
                                       differ),
                         links=links)
        return dict(base, ok=True, error="", previews=previews, pair=link, detail="")
    digest = pair_digest([(p["hostname"], p.get("patch"), p.get("base")) for p in previews])
    calls.record_use(call_id, "previewed in the intent editor", actor=actor,
                     detail=detail(f"both ends: {near['hostname']} {pair['port']} and "
                                   f"{far['hostname']} {pair['far_port']}", differ), links=links,
                     drafts=[digest])
    return dict(base, ok=True, error="", previews=previews, pair=dict(link, draft=digest),
                detail="")


#: The Source: of an intent commit made from a draft (part 2); the call is its AI-Call:.
DRAFT_SOURCE = "ai-draft"


def draft_digest(hostname: str, patch, base: str) -> str:
    """What a draft offers to commit, as one digest: the device, the patch exactly (its JSON,
    keys sorted) and the version of the intent it was previewed on."""
    import hashlib
    text = json.dumps({"hostname": hostname, "patch": patch, "base": base or ""},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def commit_draft(list_name: str, hostname: str, call_id: str, patch_text: str, base: str,
                 summary: str, actor: str) -> dict:
    """Commit a drafted change (part 2) as *actor*, through the intent editor's own write path
    (`intent_patch.commit`: refused when the intent moved since the draft, and without the
    person's one line), as ``Source: ai-draft`` with ``AI-Call: <call_id>``. Refused before
    anything is written unless *patch_text* and *base* are exactly a draft that call offered
    (its digest on the call's use row), naming both digests. Its use row records the commit,
    so the call's History row links to it, and the commit's trailer links back."""
    from modules.ai import calls
    from modules.nsot import intent_patch

    def refused(status, stage, why):
        return {"ok": False, "status": status, "stage": stage, "error": why}

    try:
        patch = json.loads(patch_text or "")
    except ValueError:
        return refused(400, "patch", "the draft's patch could not be read; draft it again")
    found = calls.find(call_id or "")
    if found["state"] != "ok":
        return refused(404 if found["state"] == "absent" else 503, "call", (
            f"the AI call {call_id[:40]!r} that drafted this is not in the record of AI calls"
            + (f" ({found['error']})" if found.get("error") else "") + "; nothing was written"))
    if hostname not in ((found["row"].get("subject") or {}).get("devices") or []):
        return refused(409, "call", f"the AI call {call_id} drafted no change to {hostname}; "
                                    "nothing was written")
    handed = draft_digest(hostname, patch, base)
    drafted = [d for u in found["uses"] for d in u.get("drafts") or []]
    if handed not in drafted:
        return refused(409, "differs", (
            f"this is not the drafted change: the call {call_id} drafted "
            + (", ".join(d[:12] for d in drafted) or "nothing to commit")
            + f", and this commit was handed {handed[:12]} (the patch or the version of "
            f"{hostname}'s intent differs); nothing was written. Draft it again"))
    got = intent_patch.commit(list_name, hostname, patch, summary, base, actor,
                              source=DRAFT_SOURCE, extra_trailers=[f"AI-Call: {call_id}"])
    if got.get("ok") and got.get("commit"):
        calls.record_use(call_id, "committed to intent", actor=actor,
                         detail=f"commit {got['commit'][:12]} to {hostname}'s intent",
                         links={"page": f"/v2/device/{hostname}?tab=history"})
    return got


def commit_pair(list_name: str, call_id: str, pair_text: str, summary: str,
                actor: str, link_text: str = "") -> dict:
    """Commit a two-device draft (C1908) as *actor*: both devices' patches in ONE intent commit
    (`intent_patch.commit_many`, one `repo.commit()`), as ``Source: ai-draft`` with ``AI-Call:``.
    Refused before anything is written unless *pair_text* (``[{"hostname", "patch", "base"}]``,
    in the order drafted) is exactly the pair that call offered (`pair_digest` on its use
    row): one end alone, either patch changed, or another version is refused, naming both
    digests; and unless *link_text*, the link the draft was made for
    (`paired_deploy.link_text`), names exactly these two devices. The answer offers the paired
    deploy (C1909): the plan for both devices, both ticked, carrying the link (``link``), never
    started for the person."""
    from modules.ai import calls
    from modules.nsot import intent_patch, paired_deploy

    def refused(status, stage, why):
        return {"ok": False, "status": status, "stage": stage, "error": why}

    try:
        items = json.loads(pair_text or "")
        items = [(str(i["hostname"]), i["patch"], str(i.get("base") or "")) for i in items]
    except (ValueError, TypeError, KeyError):
        return refused(400, "patch", "the draft's two patches could not be read; draft it again")
    if len(items) != 2:
        return refused(400, "patch", f"a two-device draft holds two devices' patches, and this "
                                     f"holds {len(items)}; nothing was written")
    try:
        link = paired_deploy.link_of(link_text)
    except paired_deploy.LinkRefused as exc:
        return refused(400, "link", f"the draft's link could not be read ({exc}); nothing was "
                                    "written. Draft it again")
    if sorted([link["device"], link["far"]]) != sorted(h for h, _p, _b in items):
        return refused(400, "link", (
            f"the draft's link {paired_deploy.link_words(link)} is not between the two devices "
            f"it changes ({' and '.join(h for h, _p, _b in items)}); nothing was written. "
            "Draft it again"))
    found = calls.find(call_id or "")
    if found["state"] != "ok":
        return refused(404 if found["state"] == "absent" else 503, "call", (
            f"the AI call {call_id[:40]!r} that drafted this is not in the record of AI calls"
            + (f" ({found['error']})" if found.get("error") else "") + "; nothing was written"))
    hosts = [h for h, _p, _b in items]
    subject = set((found["row"].get("subject") or {}).get("devices") or [])
    if not set(hosts) <= subject:
        return refused(409, "call", f"the AI call {call_id} drafted no change to "
                                    f"{' and '.join(h for h in hosts if h not in subject)}; "
                                    "nothing was written")
    handed = pair_digest(items)
    drafted = [d for u in found["uses"] for d in u.get("drafts") or []]
    if handed not in drafted:
        return refused(409, "differs", (
            f"this is not the drafted change: the call {call_id} drafted "
            + (", ".join(d[:12] for d in drafted) or "nothing to commit")
            + f", and this commit was handed {handed[:12]} (a patch, or the version of "
            f"{' or '.join(hosts)}'s intent, differs); nothing was written. Draft it again"))
    got = intent_patch.commit_many(list_name, items, summary, actor, source=DRAFT_SOURCE,
                                   extra_trailers=[f"AI-Call: {call_id}"])
    if got.get("ok") and got.get("commit"):
        calls.record_use(call_id, "committed to intent", actor=actor,
                         detail=f"commit {got['commit'][:12]} to {' and '.join(hosts)}'s intent",
                         links={"page": f"/v2/device/{hosts[0]}?tab=history"})
    return dict(got, hostnames=hosts, link=paired_deploy.link_text(link),
                link_words=paired_deploy.link_words(link),
                deploy=PAIRED_DEPLOY.format(a=link["device"], b=link["far"]))


def _held_in(text: str, quoted: dict) -> str:
    """An expected text with each quoted text in it as its placeholder, longest first, as the
    model is asked to write it (`stale` only: a case's expectation holds the real text)."""
    for tag, value in sorted(quoted.items(), key=lambda kv: -len(kv[1])):
        if value and isinstance(text, str):
            text = text.replace(value, tag)
    return text


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
    # Everything before the call, as the recording will meet it (`screen`: the quotes held
    # back, the vocabulary, Mercury's questions, the names resolved with the case's own choice
    # given); a reference expects the current resolution, and Mercury's own answer is judged
    # as the recording judges it (`cases.intent_misses`).
    from modules.ai import cases
    resolved = screen(list_name, case.get("sentence") or "", [device], case.get("picks"))
    refusal = resolved.get("refusal") or {}
    if "choose" in allowed:
        got = [c["name"] for c in (refusal.get("choose") or {}).get("candidates") or []]
        if refusal.get("error") != "choose" or got != expect.get("candidates", got):
            return [f"{where}: the case expects Mercury to ask which of "
                    f"{expect.get('candidates')}, and the names now resolve to "
                    f"{got or [r['to'] for r in resolved.get('resolutions') or []]}"]
        return []
    if refusal:
        if not cases.intent_misses(expect, refusal):
            return []
        return [f"{where}: Mercury answers before any call, not as the case expects: "
                f"{refusal.get('detail', '')[:200]}"]
    for phrase, names in (case.get("resolves") or {}).items():
        now = next((r["to"] for r in resolved["resolutions"] if r["said"] == phrase), None)
        if now != names:
            return [f"{where}: the case expects {phrase!r} to resolve to {names}, and it now "
                    f"resolves to {now}"]
    if expect.get("patches"):
        return _stale_pair(list_name, case, resolved, where)
    if resolved.get("pair") and {"answer", "refused_after"} & set(allowed):
        return [f"{where}: the sentence is now one two-device draft of "
                f"{resolved['pair']['device']} and {resolved['pair']['far']}, and the case "
                "expects one device's operations"]
    if not expect.get("ops") or not ({"answer", "refused_after"} & set(allowed)):
        return []
    quoted = resolved["quoted"]
    # Strict, as the gateway reads an answer: from its JSON (an enum is its value there). Its
    # text as the model would write it: each quoted text as its placeholder.
    answer = _expected_answer({device: expect["ops"]}, quoted)
    made = to_patches(answer, {device: touched(resolved["sentence"])}, quoted)
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


def _expected_answer(by_host: dict, quoted: dict) -> IntentChange:
    """A case's expected operations (``{hostname: [ops]}``) as the model's answer, read as the
    gateway reads one (strict, from its JSON), each quoted text as its placeholder."""
    blank = {k: (0 if f.annotation is int else "")
             for k, f in Operation.model_fields.items() if k != "op"}
    patches = [{"hostname": host, "operations": [
        dict(blank, op=o["op"], **{("vlan_name" if k == "name" else k):
                                   (_held_in(v, quoted) if k in ("description", "name") else v)
                                   for k, v in o.items() if k != "op"}) for o in ops]}
        for host, ops in by_host.items()]
    return IntentChange.model_validate_json(json.dumps({
        "outcome": "answer", "question": "", "why_not": "", "patches": patches}))


def _stale_pair(list_name: str, case: dict, resolved: dict, where: str) -> list:
    """`stale` for a two-device expectation (C1908, ``expect.patches``): the sentence must be one
    two-device draft of the expected devices, the expected operations inside each end's scope,
    each previewed, and the two ends judged as a draft's are (`ends_judged`, C1933: refused
    only for a mismatch the change creates or changes)."""
    from modules.nsot import intent_patch

    expect, pair = case["expect"], resolved.get("pair")
    if not pair:
        return [f"{where}: the case expects one draft of {' and '.join(expect['patches'])}, and "
                "the sentence is not one two-device draft now (no link to a managed far end)"]
    if set(expect["patches"]) != {pair["device"], pair["far"]}:
        return [f"{where}: the case expects {sorted(expect['patches'])}, and the link is "
                f"{pair['device']} {pair['port']} to {pair['far']} {pair['far_port']}"]
    scopes = _scopes(touched(resolved["sentence"]), resolved["named"], pair)
    made = to_patches(_expected_answer(expect["patches"], resolved["quoted"]), scopes,
                      resolved["quoted"])
    if not made["ok"]:
        return [f"{where}: the expected operations are outside what the sentence names: "
                f"{made['error']}"]
    shown = {}
    for patch in made["patches"]:
        got = intent_patch.preview(list_name, patch.hostname, patch)
        if not got.get("ok"):
            return [f"{where}: the intent editor refuses {patch.hostname}'s expected change: "
                    f"{(got.get('error') or '')[:200]}"]
        if not got.get("changed") or not got.get("vs_intent_changed", True):
            return [f"{where}: {patch.hostname}'s expected change is already in its committed "
                    "intent"]
        shown[patch.hostname] = got
    got = _pair_judged(list_name, pair, [shown[pair["device"]], shown[pair["far"]]])
    if got["refused"]:
        if "refused_after" in expect["outcome"]:
            return []
        return [f"{where}: the expected change leaves the ends not matching: "
                + "; ".join(got["refused"])[:200]]
    if "answer" not in expect["outcome"]:
        return [f"{where}: the case expects the ends' mismatch refused, and they now match"]
    return []


def slices(list_name: str, hostnames: list, t: dict, per_host: dict = None) -> dict:
    """``{"devices": {hostname: slice + platform, role}, "missing": [(hostname, why)]}``: the
    touched sections of *hostnames*, each from its committed intent (`intent_edit.open_doc`,
    the blob it names), its platform and role from the inventory. *per_host* gives a device
    its own touched parts (a two-device draft: each end its own port), else *t* for all."""
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
        out[name] = dict(slice_of(doc, (per_host or {}).get(name, t)),
                         platform=str(row.get("platform") or ""),
                         role=str(row.get("role") or ""))
    return {"devices": out, "missing": missing}
