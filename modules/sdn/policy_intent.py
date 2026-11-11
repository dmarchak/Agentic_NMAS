"""The intent controller (Lab 9 Objective B2; board docs/boards/lab9-sdn.html artboard E): a
person's policy in words becomes a structured policy, checked in code against the network's
NSOT and its switches, compiled to flows on the source's ingress switch, and applied through
the one flow-operation core (`flow_ops`) after the person confirms its hash.

**The policy** (`Rule`, `PolicyDraft`; strict and closed, schemas/ai/sdn_policy.v1.json): one
to `RULES_MAX` rules, each a `kind` (``block``, ``allow``, ``rate_limit``), a ``source`` and a
``destination`` (a name the sentence resolved to, or ``any``), a ``protocol`` (``tcp``,
``udp``, ``icmp``, ``any``), a ``port`` (0 for any), a ``rate_kbps`` (a rate limit's only) and a
``duration_s`` (0 until withdrawn; at most `DURATION_MAX`, OpenFlow's 16-bit hard timeout).
There is no redirect: a redirect needs a port to send to, and no name says one.

**Before any call** (`screen`; STEPS ``quote`` and ``names``), all in code:
- quoted text is taken out first (`intent_words.hold_quotes`), an opaque placeholder in its
  place; a quoted text that is exactly a NetBox host's name, a tag or an address is put back as
  that name (it is NetBox's, not free text), any other stays a placeholder no rule may name;
- each name is resolved against the network's committed NSOT export (its end hosts by name,
  tag and address, `nsot.export.hosts_of`) and the controller's learned hosts (by address,
  `topology.stored`): a host name, a tag (``web`` and ``web servers``), an address or a subnet;
- a word naming several hosts (the stem of ``db-1`` and ``db-2``, or a word that is both a host
  and a tag) is asked back with one button per candidate and Neither, with no call;
- a word shaped like a host name (``desk9``) that names nothing is refused, naming the comparison
  and both operands (the name against N NetBox hosts and M controller-learned hosts).

**One call** (``ask``): one recorded, capped call on the ``sdn_policy`` pin (Haiku 5.5, the
economy tier) as the person who pressed, given the sentence (quotes as placeholders) and the
resolved names only. The model may only answer a policy, one question back, or why not.

**Every check, in code, before any flow is shown** (`check`; STEP ``check``):
- **malformed**: a rule naming a name the sentence did not resolve to, a rate on a rule that is
  not a rate limit, a rate limit with no rate, a negative number;
- **impossible**: a source of ``any`` (a policy is placed where its source enters the fabric),
  a source on no OpenFlow port (NetBox records none and the controller has not learned it), a
  source whose hosts enter at more than one switch, the same host at both ends, a port without
  tcp or udp, a duration past `DURATION_MAX`, a rate past `RATE_MAX_KBPS`, no address family
  both ends share, and a rate limit where the ingress switch reports no meters (offering Drop
  instead, and a switch the controller links to it that reports meters);
- **contradictory**: two rules of one request whose matches overlap with different kinds (or
  two rate limits overlapping), or a rule against a committed policy (the flow intent's
  records of a policy, `committed`) whose match it overlaps with a different kind;
- **conflict with installed flows**: a flow of Mercury's above it that takes all of its
  traffic, and what it does to the flows below (`flow_intent.effect`): it may not lift or
  shadow a flow of Mercury's (a response's drop or meter);
- **protected**: a match that meets a protected flow class (`protected.overlap`: the control
  channel, management, the Services tagged ``mercury-protected``, the config context's), refused
  with a narrowing: name a protocol and port that leaves the class alone.

**Compile** (STEP ``compile``): on the source's ingress switch, one flow per source and
destination address of one family, at `flow_ops.response_priority` (above every flow not
Mercury's that could match it): ``block`` drops (no action); ``allow`` sends to ``NORMAL``, the
switch's own forwarding (the fabric is one table, so no goto); ``rate_limit`` adds one meter
(a DROP band at the rate, kbit/s) and each flow goes through it to ``NORMAL``. The duration is
each flow's hard timeout.

**Preview, confirm, apply, record** (STEPS ``preview``, ``confirm``, ``record``): the compiled
operation is `flow_ops.plan`'s (the effect in words, every request and its undo, the hash); the
confirm re-runs every check above on the carried policy, compiles it again with the preview's
cookies, meter and priorities (an operation that is not what the policy compiles to now is
refused), and is `flow_ops.apply`'s as the verified person, its writer ``policy:<id>``. Each
flow is recorded in the network's flow intent with the policy (``response.kind`` ``policy``),
which is what `committed` reads: later requests are checked against it, and History shows the
operation (``sdn_operations``). A policy is withdrawn by removing its flows on SDN › Flows.
"""

import ipaddress
import json
import logging
import re
import secrets
import time
from enum import Enum

from modules.ai.nl_query import Outcome
from modules.ai.schemas import StrictModel, register

log = logging.getLogger(__name__)

FEATURE = "sdn_policy"
PROMPT = ("sdn_policy", 1)
KINDS = ("block", "allow", "rate_limit")
KIND_WORDS = {"block": "block", "allow": "allow", "rate_limit": "rate-limit"}
#: The most rules one request may hold.
RULES_MAX = 4
#: OpenFlow 1.3's hard timeout is 16 bits (seconds).
DURATION_MAX = 0xFFFF
#: The largest rate a rate limit takes, kbit/s (100 Gbit/s); a meter band's rate is 32 bits.
RATE_MAX_KBPS = 100_000_000
ANY = "any"
TAG_PREFIX = "tag:"
#: The IP protocol numbers by family (ICMP is ICMPv6, 58, over IPv6).
PROTOCOL_NUMBERS = {"tcp": (6, 6), "udp": (17, 17), "icmp": (1, 58)}
ETH = {4: 0x0800, 6: 0x86DD}
#: A word shaped like a host's name: letters, then digits (desk9, web-3, srv12a). Never one of
#: these, each a unit, a protocol or a field.
_HOSTLIKE = re.compile(r"^[a-z][a-z_]{0,15}-?\d{1,4}[a-z0-9-]{0,8}$")
_NOT_HOSTS = ("tcp", "udp", "icmp", "ipv", "port", "vlan", "kbps", "mbps", "gbps", "kbit",
              "mbit", "gbit", "eth", "dscp", "http", "sec", "min", "hour", "x")
_PLACEHOLDER = re.compile(r"<<text_[1-9][0-9]{0,2}>>")
_STRIP = ".,;:!?()[]{}\"'“”‘’"

#: The steps, as the manual's How it works page names them (docs/manual/how-it-works/
#: sdn-policies.md).
STEPS = (
    ("quote", "quoted text taken out first, an opaque placeholder in its place; a quoted "
              "NetBox name put back as that name"),
    ("names", "each name resolved in code against the committed NSOT export (hosts by name, "
              "tag and address) and the controller's learned hosts; several matches asked "
              "back as buttons and a host-shaped name that matches nothing refused, both "
              "before any call"),
    ("ask", "one recorded, capped call through the AI gateway on the sdn_policy pin, as the "
            "person who pressed, given the sentence and the resolved names only"),
    ("check", "the answer parsed strictly and every rule checked in code: unknown names, "
              "impossible (no OpenFlow port, no meters, past a limit), contradictory (within "
              "the request and against committed policies), conflicts with installed flows "
              "and protected flows, each refusal naming what it compared"),
    ("compile", "the checked policy compiled to flows on the source's ingress switch: drop, "
                "NORMAL forward, or a meter and NORMAL, each with the duration as its hard "
                "timeout, above every flow not Mercury's that could match it"),
    ("preview", "the flow-operation core's preview: the effect in words, every REST body and "
                "its undo, and the hash; nothing is sent"),
    ("confirm", "the person confirms the hash; every check runs again and the policy is "
                "compiled again to the same requests, then applied holding the switch, "
                "verified by reading the table back, and rolled back on a failure"),
    ("record", "each flow recorded in the network's flow intent with its policy, so later "
               "requests are checked against it; the operation on History"),
)


#: How the check words a policy the protected set refuses (`check`): its first words, which
#: History › Export reads to tell such a refusal in a call's use recorded before refusals
#: were kept as records of their own (`history_export._from_refused_calls`, C2944).
PROTECTED_LEAD = "it would cover the protected flow"


class Refused(ValueError):
    """A policy refused before anything is sent, in words."""


# ───────────────────────────────────────────────────────────────────────────── the schema

class Kind(str, Enum):
    block = "block"
    allow = "allow"
    rate_limit = "rate_limit"


class Protocol(str, Enum):
    tcp = "tcp"
    udp = "udp"
    icmp = "icmp"
    any = "any"


class Rule(StrictModel):
    """One rule, flat and closed: every field required (the provider's schema has no union);
    a field the kind does not use is 0."""
    kind: Kind
    source: str
    destination: str
    protocol: Protocol
    port: int
    rate_kbps: int
    duration_s: int


@register("sdn_policy", 1)
class PolicyDraft(StrictModel):
    """The policy the sentence states, as rules over the names given; or one question back,
    when the words leave a choice to the person; or why it cannot be stated."""
    outcome: Outcome
    question: str
    why_not: str
    rules: list[Rule]


def vocabulary() -> str:
    """What a rule is, the same bytes on every call (the cached prefix)."""
    return ("kind: block (drop the traffic), allow (let it pass), rate_limit (limit it to "
            "rate_kbps)\n"
            "source, destination: exactly one of the names given, or any\n"
            "protocol: tcp, udp, icmp or any\n"
            "port: the destination port (tcp or udp only), 0 for every port\n"
            f"rate_kbps: a rate limit's rate in kbit/s (1 Mbit/s is 1000), 0 for any other "
            f"kind\nduration_s: how long the rule lasts in seconds (an hour is 3600), 0 until "
            f"withdrawn; at most {DURATION_MAX}\n"
            f"At most {RULES_MAX} rules.")


# ───────────────────────────────────────────────────────────────────────────── the world

def _addr(text) -> str:
    """An address's text without its prefix length, compressed; "" when it is none."""
    try:
        return ipaddress.ip_interface(str(text).strip()).ip.compressed
    except ValueError:
        return ""


def _stored_topology(network: str) -> dict:
    from modules.sdn import topology
    return topology.stored(network)


def world(network: str) -> dict:
    """What the checks read, once per request: ``{"ok", "error", "export_sha256", "hosts":
    {name: {"name", "tags", "addresses", "ports"}}, "learned": [{"address", "mac", "dpid",
    "port_no", "connection"}], "switches": {dpid: {"name", "platform"}}, "links": {dpid:
    [(dpid, port, connection)]}, "connections": {dpid: connection}, "only_connection",
    "learned_state"}``. An export not committed, unreadable, or from before hosts were
    recorded refuses: a host could not be told unknown."""
    from modules.nsot import export as X
    from modules.sdn.drivers.base import SpecError, parse_dpid

    out = {"ok": False, "error": "", "export_sha256": "", "hosts": {}, "learned": [],
           "switches": {}, "links": {}, "connections": {}, "only_connection": "",
           "learned_state": ""}
    got = X.read(network)
    if not got["ok"]:
        out["error"] = (f"{network}'s committed NSOT export cannot be read ({got['error']}), so "
                        "no host can be checked against NetBox")
        return out
    doc = got["export"]
    hosts = X.hosts_of(doc)
    if hosts is None:
        out["error"] = (f"{network}'s committed NSOT export {got['sha256'][:12]} was built "
                        "before end hosts were recorded, so no host can be checked against "
                        "NetBox: export it again on SDN › Apps")
        return out
    out["export_sha256"] = got["sha256"]
    rows = X.host_ports(doc)
    for h in hosts:
        addrs = []
        for i in h.get("interfaces") or []:
            for a in i.get("ip_addresses") or []:
                if _addr(a) and _addr(a) not in addrs:
                    addrs.append(_addr(a))
        out["hosts"][h["name"]] = {"name": h["name"], "tags": list(h.get("tags") or []),
                                   "addresses": addrs,
                                   "ports": [r for r in rows if r["host"] == h["name"]]}
    out["devices"] = sorted(d["name"] for d in (doc.get("body") or {}).get("devices") or [])
    for d in (doc.get("body") or {}).get("devices") or []:
        raw = str((d.get("custom_fields") or {}).get("openflow_datapath_id") or "")
        if not raw:
            continue
        try:
            out["switches"][parse_dpid(raw)] = {"name": d["name"],
                                                "platform": d.get("platform") or ""}
        except SpecError:
            continue
    topo = _stored_topology(network)
    out["learned_state"] = topo.get("state", "")
    for c in topo.get("controllers") or []:
        if c.get("state") == "not_declared":
            continue
        inner = set()
        for link in c.get("links") or []:
            s, t = link["src"], link["dst"]
            inner.add((int(s["dpid"]), int(s["port_no"])))
            inner.add((int(t["dpid"]), int(t["port_no"])))
            out["links"].setdefault(int(s["dpid"]), []).append(
                (int(t["dpid"]), int(s["port_no"]), c["name"]))
        for sw in c.get("switches") or []:
            out["connections"].setdefault(int(sw["dpid"]), c["name"])
        have = {int(sw["dpid"]) for sw in c.get("switches") or []}
        for h in c.get("hosts") or []:
            place = (int(h["dpid"]), int(h["port_no"]))
            if place[0] not in have or place in inner:
                continue
            for a in list(h.get("ipv4") or []) + list(h.get("ipv6") or []):
                addr = _addr(a)
                if addr and not ipaddress.ip_address(addr).is_link_local:
                    out["learned"].append({"address": addr, "mac": h.get("mac", ""),
                                           "dpid": place[0], "port_no": place[1],
                                           "connection": c["name"]})
    from modules.sdn import connections
    conns = connections.connections(network)
    if conns.get("state") == "ok" and len(conns["connections"]) == 1:
        out["only_connection"] = conns["connections"][0]["name"]
    out["ok"] = True
    return out


def switch_words(w: dict, dpid: int) -> str:
    from modules.sdn.drivers.base import dpid_hex
    sw = w["switches"].get(dpid)
    platform = {"arista-eos": "an Arista EOS switch", "hp-procurve": "an ArubaOS-Switch",
                "aruba-os-switch": "an ArubaOS-Switch", "ovs-linux": "an Open vSwitch server"}
    if not sw:
        return f"switch {dpid_hex(dpid)}"
    kind = platform.get(sw["platform"], sw["platform"] or "a switch")
    return f"{sw['name']} ({kind}, DPID {dpid_hex(dpid)})"


# ───────────────────────────────────────────────────────────────────────────── names

def _tags(w: dict) -> dict:
    out = {}
    for h in w["hosts"].values():
        for t in h["tags"]:
            if t == "mercury-end-host":
                continue
            out.setdefault(t, []).append(h["name"])
    return out


def _stem(name: str) -> str:
    return re.sub(r"[-_]?\d+[a-z]?$", "", name.lower())


def resolve(w: dict, key: str) -> dict:
    """The name *key* (as the names list gives it: a host's name, ``tag:<slug>``, an address
    or a subnet, or ``any``) resolved: ``{"key", "kind", "label", "hosts": [host names],
    "addresses": [address or subnet texts], "learned": [learned rows]}``; raises Refused
    naming the comparison when it resolves to nothing."""
    if key == ANY:
        return {"key": ANY, "kind": ANY, "label": "any", "hosts": [], "addresses": [],
                "learned": []}
    if key in w["hosts"]:
        h = w["hosts"][key]
        return {"key": key, "kind": "host", "hosts": [key], "addresses": list(h["addresses"]),
                "learned": [], "label": f"{key} = {', '.join(h['addresses']) or 'no address'} "
                                        "(NetBox)"}
    if key.startswith(TAG_PREFIX):
        tag = key[len(TAG_PREFIX):]
        names = sorted(_tags(w).get(tag) or [])
        if not names:
            raise Refused(f"no NetBox host carries the tag {tag!r} (compared with the "
                          f"{len(_tags(w))} tags {len(w['hosts'])} hosts carry)")
        addrs = [a for n in names for a in w["hosts"][n]["addresses"]]
        return {"key": key, "kind": "tag", "hosts": names, "addresses": addrs, "learned": [],
                "label": f"tag {tag} = {', '.join(names)} (NetBox)"}
    try:
        net = ipaddress.ip_network(key, strict=False)
    except ValueError:
        raise Refused(f"{key!r} is no NetBox host ({len(w['hosts'])} held), tag or address") \
            from None
    if net.num_addresses == 1:
        addr = net.network_address.compressed
        for h in w["hosts"].values():
            if addr in h["addresses"]:
                return {"key": key, "kind": "host", "hosts": [h["name"]], "addresses": [addr],
                        "learned": [], "label": f"{addr} = {h['name']} (NetBox)"}
        seen = [r for r in w["learned"] if r["address"] == addr]
        if seen:
            return {"key": key, "kind": "learned", "hosts": [], "addresses": [addr],
                    "learned": seen, "label": f"{addr} (the controller has learned it)"}
        return {"key": key, "kind": "address", "hosts": [], "addresses": [addr], "learned": [],
                "label": f"{addr} (an address no host of NetBox's or the controller's holds)"}
    names = sorted(h["name"] for h in w["hosts"].values()
                   if any(ipaddress.ip_address(a) in net for a in h["addresses"]
                          if ipaddress.ip_address(a).version == net.version))
    seen = [r for r in w["learned"] if ipaddress.ip_address(r["address"]).version ==
            net.version and ipaddress.ip_address(r["address"]) in net]
    return {"key": net.compressed, "kind": "subnet", "hosts": names, "addresses": [net.compressed],
            "learned": seen, "label": f"subnet {net.compressed}"
                                      + (f": {', '.join(names)} (NetBox)" if names else "")}


def _tokens(text: str) -> list:
    out = []
    for raw in text.split():
        t = raw.strip(_STRIP)
        if t.lower().endswith("'s"):
            t = t[:-2]
        if t:
            out.append(t)
    return out


def _as_address(token: str):
    if not re.fullmatch(r"[0-9a-fA-F:.]+(/\d{1,3})?", token) or not re.search(r"[.:]", token):
        return None
    try:
        return ipaddress.ip_network(token, strict=False)
    except ValueError:
        return None


def names_in(w: dict, sentence: str, picks: dict = None) -> dict:
    """The names *sentence* uses, resolved in code (no call): ``{"names": {key: resolved},
    "ask": None or {"word", "question", "candidates": [{"key", "label"}]}, "unknown": None or
    {"word", "words"}, "sentence": the sentence with each picked word replaced}``. *picks*
    (``{word: key}``) answers an earlier question; a pick that is not one of the word's
    candidates raises Refused."""
    picks = dict(picks or {})
    tags = _tags(w)
    lower_hosts = {n.lower(): n for n in w["hosts"]}
    # A managed device's name (a switch, the controller) is no host and no unknown name: a
    # policy is placed at its source's ingress, whatever switch the words name.
    devices = {d.lower() for d in w.get("devices") or []}
    names, seen_words = {}, set()
    text = sentence
    for token in _tokens(sentence):
        if _PLACEHOLDER.fullmatch(token):
            continue
        word = token.lower()
        if word in seen_words or (word in devices and word not in lower_hosts):
            continue
        seen_words.add(word)
        net = _as_address(token)
        if net is not None:
            got = resolve(w, net.compressed if net.num_addresses > 1 or "/" in token
                          else net.network_address.compressed)
            names[got["key"]] = got
            continue
        host = lower_hosts.get(word)
        tag = word if word in tags else (word[:-1] if word.endswith("s") and word[:-1] in tags
                                         else "")
        candidates = []
        if host and tag:
            candidates = [{"key": host, "label": resolve(w, host)["label"]},
                          {"key": TAG_PREFIX + tag, "label": resolve(w, TAG_PREFIX + tag)["label"]}]
        elif host:
            names[host] = resolve(w, host)
            continue
        elif tag:
            names[TAG_PREFIX + tag] = resolve(w, TAG_PREFIX + tag)
            continue
        else:
            stems = sorted(n for n in w["hosts"] if _stem(n) == word and len(word) >= 2)
            if stems:
                candidates = [{"key": n, "label": resolve(w, n)["label"]} for n in stems]
            elif _HOSTLIKE.match(word) and not word.startswith(_NOT_HOSTS):
                return {"names": names, "ask": None, "sentence": text, "unknown": {
                    "word": token, "words": (
                        f"NetBox holds no host {token} and the controller has not seen one. "
                        f"Compared: the name against {len(w['hosts'])} NetBox host"
                        f"{'s' if len(w['hosts']) != 1 else ''} and "
                        f"{len({r['address'] for r in w['learned']})} controller-learned "
                        f"host{'s' if len({r['address'] for r in w['learned']}) != 1 else ''}"
                        " (the controller learns addresses, not names)")}}
            else:
                continue
        if token in picks or word in picks:
            chosen = picks.get(token, picks.get(word))
            if chosen not in [c["key"] for c in candidates]:
                raise Refused(f"{chosen!r} is not one of the choices for {token!r} "
                              f"({', '.join(c['key'] for c in candidates)})")
            names[chosen] = resolve(w, chosen)
            text = re.sub(rf"(?<![\w-]){re.escape(token)}(?![\w-])",
                          chosen.replace(TAG_PREFIX, "") if chosen.startswith(TAG_PREFIX)
                          else chosen, text, count=1)
            continue
        return {"names": names, "sentence": text, "unknown": None, "ask": {
            "word": token, "candidates": candidates,
            "question": (f"Which {token}? \"{token}\" names "
                         + (f"the host {host} and the tag {tag}" if host and tag else
                            " and ".join(c["key"] for c in candidates)
                            + (" (NetBox)" if candidates else "")))}}
    return {"names": names, "ask": None, "unknown": None, "sentence": text}


def screen(network: str, sentence: str, picks: dict = None, w: dict = None) -> dict:
    """Everything decided before any call (STEPS ``quote`` and ``names``): ``{"ok": True,
    "sentence" (as the model is given it), "quoted", "names", "world"}``, or ``{"ok": False,
    "state": "asked"|"refused", "kind", "words", ...}`` when Mercury answers itself."""
    from modules.ai import intent_words
    from modules.ai.nl_query import QUESTION_MAX

    typed = " ".join((sentence or "").split())
    if not typed:
        return mercury("refused", "empty", "Type the policy first")
    if len(typed) > QUESTION_MAX:
        return mercury("refused", "too_long", f"The policy is {len(typed)} characters; at "
                                               f"most {QUESTION_MAX} are taken")
    held = intent_words.hold_quotes((sentence or "").strip())
    if not held["ok"]:
        return mercury("refused", held["error"], held["detail"])
    w = w or world(network)
    if not w["ok"]:
        return mercury("refused", "unreadable", w["error"])
    masked = " ".join(held["sentence"].split())
    quoted = dict(held["quoted"])
    for tag, text in list(quoted.items()):
        named = _quoted_name(w, text)
        if named:
            masked = masked.replace(tag, named)
            quoted.pop(tag)
    try:
        got = names_in(w, masked, picks)
    except Refused as exc:
        return mercury("refused", "not_an_answer", f"{exc}; nothing was sent")
    if got["unknown"]:
        return mercury("refused", "unknown", got["unknown"]["words"],
                        title=f"Unknown host: \"{got['unknown']['word']}\"")
    if got["ask"]:
        return dict(mercury("asked", "ambiguous", got["ask"]["question"]),
                    ask=got["ask"], sentence=typed)
    if not got["names"]:
        return mercury("refused", "no_names", (
            "The policy names no host, tag, address or subnet NetBox or the controller holds "
            f"(compared with {len(w['hosts'])} NetBox hosts, {len(_tags(w))} tags and "
            f"{len({r['address'] for r in w['learned']})} controller-learned hosts); name "
            "the source as NetBox does"))
    return {"ok": True, "sentence": got["sentence"], "quoted": quoted, "names": got["names"],
            "world": w, "decided": got["sentence"] if picks else ""}


def _quoted_name(w: dict, text: str) -> str:
    t = text.strip()
    if t in w["hosts"]:
        return t
    if t.lower() in _tags(w):
        return t.lower()
    net = _as_address(t)
    return net.compressed if net is not None and "/" in t else (
        net.network_address.compressed if net is not None else "")


def mercury(state: str, kind: str, words: str, **extra) -> dict:
    return dict({"ok": False, "state": state, "kind": kind, "words": words, "by": "mercury",
                 "call_id": "", "cost_usd": 0.0, "title": TITLES.get(kind, "")}, **extra)


TITLES = {"ambiguous": "Which one?", "unknown": "Unknown host", "impossible": "Impossible",
          "contradictory": "Contradictory", "protected": "Refused by a protected flow",
          "conflict": "Conflicts with an installed flow", "malformed": "Not a policy",
          "question": "One question first", "model_refused": "Not stated as a policy",
          "unreadable": "Cannot be checked", "no_names": "No host named",
          "empty": "Nothing typed", "too_long": "Too long", "gateway": "Not drafted",
          "not_an_answer": "Not one of the choices", "neither": "Nothing chosen"}


def names_part(names: dict, quoted: dict) -> str:
    """The names the model may use, one a line: each key and what it is."""
    lines = [f"{k}: {v['label']}" for k, v in sorted(names.items())]
    lines.append("any: every address")
    for tag in sorted(quoted):
        lines.append(f"{tag}: quoted text, not a name (no rule may name it)")
    return "\n".join(lines)


# ───────────────────────────────────────────────────────────────────────────── the call

def draft(network: str, sentence: str, *, actor: str, trigger: dict, send=None,
          today: str = None, picks: dict = None, driver=None,
          actor_verified: str = "") -> dict:
    """*sentence* made a checked policy: ``{"ok", "state", ...}``, *state* one of ``asked``
    (Mercury's question, no call), ``refused`` (*kind* naming which check, its words naming
    what it compared), ``question`` (the model's one question back), ``checked`` (the policy
    and the checks' rows, ready to preview). The call's id and cost when one was made.

    The call's use keeps the check's words whole (C3014: a reason cut at 200 characters
    ended mid-word in History › Export's AI-calls file). A policy the protected set refused
    is a record of its own too, for a verified person (`keep_refusal`, C2944: who, how
    verified by *actor_verified*, what was asked and each protected flow that refused it;
    with no *actor_verified*, or ``none``, nothing is recorded), ``refusal`` saying whether
    it was kept."""
    from modules.ai import calls, gateway

    pre = screen(network, sentence, picks)
    if not pre["ok"]:
        return dict(pre, words_typed=" ".join((sentence or "").split()))
    w = pre["world"]
    subject = {"kind": "sdn_policy", "id": network, "devices": []}
    parts = {"sentence": pre["sentence"], "names": names_part(pre["names"], pre["quoted"])}
    asked = gateway.ask(FEATURE, PROMPT, PolicyDraft, parts, actor=actor, trigger=trigger,
                        context={"rules": vocabulary()}, send=send, today=today,
                        subject=subject, network=network)
    base = {"call_id": asked.get("call_id", ""), "cost_usd": asked.get("cost_usd", 0.0),
            "words_typed": " ".join((sentence or "").split()), "sent": pre["sentence"],
            "decided": pre.get("decided", ""), "by": "model",
            **({"typed_masked": asked["typed_masked"]} if asked.get("typed_masked") else {})}
    links = {"page": f"/v2/sdn/policies?list={network}"}
    if not asked["ok"]:
        return dict(base, ok=False, state="refused", kind="gateway", title=TITLES["gateway"],
                    words=asked.get("detail") or asked.get("error") or "the call failed",
                    error=asked.get("error", ""))
    answer = asked["output"]
    if answer.outcome is Outcome.ask:
        calls.record_use(asked["call_id"], "asked a question back", actor=actor,
                         detail=_masked(answer.question[:200]), links=links)
        return dict(base, ok=False, state="question", kind="question",
                    title=TITLES["question"], words=answer.question[:200])
    if answer.outcome is Outcome.refuse:
        calls.record_use(asked["call_id"], "shown: not stated as a policy", actor=actor,
                         detail=_masked(answer.why_not[:200]), links=links)
        return dict(base, ok=False, state="refused", kind="model_refused",
                    title=TITLES["model_refused"], words=answer.why_not[:200])
    policy = {"id": new_id(), "network": network, "words": _masked(base["words_typed"]),
              "call_id": asked["call_id"],
              "rules": [r.model_dump(mode="json") for r in answer.rules]}
    got = check(network, policy, w=w, driver=driver, names=pre["names"])
    use =("refused by validation" if got["state"] == "refused" else "checked: ready to preview")
    calls.record_use(asked["call_id"], use, actor=actor,
                     detail=_masked(got.get("words", "")), links=links)
    kept = keep_refusal(network, got, stage="draft", actor=actor, actor_verified=actor_verified)
    return dict(base, **got, **({"refusal": kept} if kept else {}))


def _masked(text: str) -> str:
    from modules import redact
    return redact.redact_text(text or "")


def new_id() -> str:
    return f"pol-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{secrets.token_hex(3)}"


# ───────────────────────────────────────────────────────────────────────────── the checks

def parse_rules(policy: dict) -> list:
    """The policy's rules parsed strictly (`Rule`, from JSON so an enum is its text); raises
    Refused naming what is not of its shape."""
    from pydantic import ValidationError

    rules = (policy or {}).get("rules")
    if not isinstance(rules, list) or not rules:
        raise Refused("the answer states no rule")
    if len(rules) > RULES_MAX:
        raise Refused(f"the answer states {len(rules)} rules; at most {RULES_MAX} are taken")
    out = []
    for n, r in enumerate(rules):
        try:
            out.append(Rule.model_validate_json(json.dumps(r)))
        except (ValidationError, TypeError, ValueError) as exc:
            first = exc.errors()[0] if isinstance(exc, ValidationError) else {}
            where = ".".join(str(x) for x in first.get("loc", ())) or "the rule"
            raise Refused(f"rule {n + 1} is not of the policy's shape: {where}: "
                          f"{first.get('msg', str(exc))}") from None
    return out


def _malformed(rules: list, allowed: set) -> str:
    for n, r in enumerate(rules, 1):
        for end in ("source", "destination"):
            value = getattr(r, end)
            if value != ANY and value not in allowed:
                return (f"rule {n}'s {end} is {value!r}, which is not among the names the "
                        f"sentence resolved to ({', '.join(sorted(allowed)) or 'none'}) or any")
        for field in ("port", "rate_kbps", "duration_s"):
            if getattr(r, field) < 0:
                return f"rule {n}'s {field} is {getattr(r, field)}, below 0"
        if r.kind is Kind.rate_limit and r.rate_kbps == 0:
            return f"rule {n} is a rate limit with no rate (rate_kbps 0)"
        if r.kind is not Kind.rate_limit and r.rate_kbps:
            return f"rule {n} is a {r.kind.value} with a rate ({r.rate_kbps} kbps)"
    return ""


def _impossible_shape(rules: list) -> str:
    for n, r in enumerate(rules, 1):
        said = f"rule {n} ({rule_words(r)})"
        if r.source == ANY:
            return (f"{said} has the source any: a policy is placed where its source enters "
                    "the fabric, and any enters everywhere; name the source host, tag or "
                    "subnet")
        if r.source == r.destination:
            return f"{said} names {r.source} at both ends"
        if r.port and r.protocol not in (Protocol.tcp, Protocol.udp):
            return (f"{said} names port {r.port} with the protocol {r.protocol.value}: a port "
                    "is tcp's or udp's")
        if r.port > 0xFFFF:
            return f"{said} names port {r.port}; a port is 1 to 65535"
        if r.duration_s > DURATION_MAX:
            return (f"{said} lasts {r.duration_s} s, and a flow's hard timeout is at most "
                    f"{DURATION_MAX} s (OpenFlow's 16 bits, about 18 hours): say 0 to keep it "
                    "until it is withdrawn")
        if r.rate_kbps > RATE_MAX_KBPS:
            return f"{said} limits to {r.rate_kbps} kbps, above {RATE_MAX_KBPS} kbps"
    return ""


def _end_words(key: str) -> str:
    return f"the hosts tagged {key[len(TAG_PREFIX):]}" if key.startswith(TAG_PREFIX) else key


def rule_words(r) -> str:
    """A rule as a person reads it."""
    words = f"{KIND_WORDS[r.kind.value]} {_end_words(r.source)} to {_end_words(r.destination)}"
    if r.protocol is not Protocol.any:
        words += f" on {r.protocol.value}" + (f" {r.port}" if r.port else "")
    if r.kind is Kind.rate_limit:
        words += f" at {r.rate_kbps} kbps"
    if r.duration_s:
        words += f" for {r.duration_s} s"
    return words


def _place(w: dict, src: dict) -> tuple:
    """``(dpid, connection, words)`` where *src*'s hosts enter the fabric; raises Refused
    (impossible) naming why when none, or more than one switch."""
    places, missing = {}, []
    for name in src["hosts"]:
        h = w["hosts"][name]
        ports = [p for p in h["ports"] if p["dpid"] is not None and p["port_no"] is not None]
        if ports:
            for p in ports:
                places.setdefault(p["dpid"], []).append(
                    f"{name} on {p['switch']} {p['switch_interface']} (port {p['port_no']}, "
                    "NetBox)")
            continue
        seen = [r for r in w["learned"] if r["address"] in h["addresses"]]
        if seen:
            for r in seen:
                places.setdefault(r["dpid"], []).append(
                    f"{name} on {switch_words(w, r['dpid'])} port {r['port_no']} (the "
                    "controller learned it)")
            continue
        why = "; ".join(p["error"] for p in h["ports"] if p["error"]) or \
            "NetBox records no interface for it"
        missing.append(f"{name} is on no OpenFlow port: {why}, and the controller has not "
                       f"learned {' or '.join(h['addresses']) or 'it'}")
    for r in src["learned"]:
        places.setdefault(r["dpid"], []).append(
            f"{r['address']} on {switch_words(w, r['dpid'])} port {r['port_no']} (the "
            "controller learned it)")
    if missing and not places:
        raise Refused("; ".join(missing))
    if src["kind"] == "address" and not places:
        raise Refused(f"{src['addresses'][0]} is on no OpenFlow port: no NetBox host holds it "
                      "and the controller has not learned it")
    if not places:
        raise Refused(f"{src['label']} holds no host NetBox or the controller places on an "
                      "OpenFlow port")
    if len(places) > 1:
        said = "; ".join(x for xs in places.values() for x in xs)
        raise Refused(f"{src['label']}'s hosts enter the fabric at {len(places)} switches "
                      f"({said}): a policy is placed on one switch, its source's ingress; name "
                      "one source host, or a source on one switch")
    if missing:
        raise Refused("; ".join(missing))
    dpid = next(iter(places))
    conn = w["connections"].get(dpid) or w["only_connection"]
    if not conn:
        raise Refused(f"no controller connection of the network's lists {switch_words(w, dpid)}"
                      ", so nothing could be sent to it")
    return dpid, conn, "; ".join(places[dpid])


def _ends(src: dict, dst: dict) -> list:
    """Each ``(family, source text, destination text or None)`` the rule matches."""
    def by_family(entry):
        out = {}
        for a in entry["addresses"]:
            net = ipaddress.ip_network(a, strict=False)
            text = net.network_address.compressed if net.num_addresses == 1 else net.compressed
            out.setdefault(net.version, [])
            if text not in out[net.version]:
                out[net.version].append(text)
        return out
    s = by_family(src)
    if dst["kind"] == ANY:
        return [(fam, a, None) for fam in sorted(s) for a in s[fam]]
    d = by_family(dst)
    return [(fam, a, b) for fam in sorted(set(s) & set(d)) for a in s[fam] for b in d[fam]]


def _match(rule, fam: int, src: str, dst) -> dict:
    v = "ipv4" if fam == 4 else "ipv6"
    m = {"eth_type": ETH[fam], f"{v}_src": src}
    if dst:
        m[f"{v}_dst"] = dst
    if rule.protocol is not Protocol.any:
        m["ip_proto"] = PROTOCOL_NUMBERS[rule.protocol.value][0 if fam == 4 else 1]
        if rule.port:
            m[f"{rule.protocol.value}_dst"] = rule.port
    return m


def _overlap(a: dict, b: dict) -> tuple:
    """``(meets, a covers b, b covers a)`` for two matches, by `flow_intent`'s bit arithmetic
    (prerequisites implied, so an IPv4 match never meets an IPv6 one)."""
    from modules.sdn import flow_intent as F
    try:
        fa, fb = F._fields(a), F._fields(b)
    except F._CannotTell:
        return True, False, False
    return (F._match_meet(fa, fb) is not None, F._match_covers(fa, fb),
            F._match_covers(fb, fa))


def committed(network: str, now: float = None) -> dict:
    """*network*'s committed policies, from its flow intent (each flow Mercury installed for a
    policy and has not withdrawn, its hard timeout not passed): ``{"state", "error",
    "policies": [{"id", "words", "rules", "by", "at", "flows": [record]}]}``. An unreadable
    intent is ``unreadable``, never none."""
    from modules.sdn import flow_intent
    now = time.time() if now is None else now
    got = flow_intent.intent(network)
    if got["state"] != "ok":
        return {"state": "unreadable", "error": got["error"], "policies": []}
    out = {}
    for r in got["flows"]:
        resp = r.get("response") or {}
        if resp.get("kind") != "policy":
            continue
        hard, at = r.get("hard_timeout") or 0, r.get("installed_at") or 0
        if hard and at + hard <= now:
            continue
        pol = resp.get("policy") or {}
        p = out.setdefault(pol.get("id") or "?", {
            "id": pol.get("id") or "?", "words": pol.get("words", ""),
            "rules": pol.get("rules") or [], "by": r.get("actor", ""), "at": r.get("at", ""),
            "operation": resp.get("operation", ""), "flows": []})
        p["flows"].append(r)
    return {"state": "ok", "error": "", "policies": sorted(out.values(),
                                                           key=lambda p: p["at"], reverse=True)}


def _narrowing(classes: list) -> str:
    said = []
    for c in classes:
        ports = sorted({f"{k.split('_')[0]} {v}" for alt in c.get("match") or []
                        for k, v in alt.items() if k.endswith("_dst") and k[:3] in
                        ("tcp", "udp")})
        said.append(f"{', '.join(ports)} ({c['name']})" if ports else c["name"])
    return ("Narrow it: name the protocol and port to " "block (for example tcp 443), or a "
            "destination, so it leaves " + " and ".join(said) + " alone")


def _read(drv, dpid: int, meters: bool) -> dict:
    from modules.sdn import flow_ops
    return flow_ops._read_switch(drv, dpid, meters)


def _meters_offered(features) -> bool:
    f = features or {}
    return bool(f) and bool(f.get("max_meter")) and "DROP" in {
        str(t).upper() for t in f.get("band_types") or []} and "KBPS" in {
        str(c).upper() for c in f.get("capabilities") or []}


def check(network: str, policy: dict, *, w: dict = None, driver=None, draws: dict = None,
          instead: dict = None, now: float = None, names: dict = None) -> dict:
    """Every check of *policy* (``{"id", "rules", "words", ...}``, its rules untrusted: the
    model's, or carried back by a form), in code, before any flow is shown; then the compile.
    *instead* is the person's choice an impossible refusal offered (``{"kind": "block"}``, or
    ``{"place": dpid}``), each held to what was offered. *names* (the draft's: what the
    sentence resolved to, `screen`) limits the names a rule may use to those; a carried policy
    (a preview or a confirm, a verified person's form) may name any NetBox name, every check
    still run on it. *draws* (``{"cookies", "meter_id",
    "priorities"}``) are a preview's, given back at its confirm so the compile is the same.

    ``{"ok", "state": "checked"|"refused", "kind", "title", "words", "rows": [{"check",
    "words"}], "offers": [...], "policy", "ask", "dpid", "connection", "where"}``."""
    from modules import protected
    from modules.sdn import flow_intent, flow_ops

    out = {"ok": False, "state": "refused", "kind": "", "title": "", "words": "", "rows": [],
           "offers": [], "policy": dict(policy or {}), "ask": None, "dpid": None,
           "connection": "", "where": ""}

    def refuse(kind, words, **extra):
        out.update(kind=kind, title=TITLES.get(kind, ""), words=words, **extra)
        return out

    w = w or world(network)
    if not w["ok"]:
        return refuse("unreadable", w["error"])
    try:
        rules = parse_rules(policy)
    except Refused as exc:
        return refuse("malformed", f"{exc}; nothing of the answer is used")
    instead = dict(instead or {})
    if instead.get("kind"):
        if instead["kind"] != "block" or any(r.kind is not Kind.rate_limit for r in rules):
            return refuse("malformed", "only a rate limit may be made a block instead, and "
                                       f"this is {', '.join(r.kind.value for r in rules)}")
        # The person's choice, applied each time from the policy as drafted (its rules stay
        # the model's, checked; the record says which was made instead).
        rules = [r.model_copy(update={"kind": Kind.block, "rate_kbps": 0}) for r in rules]
        out["policy"]["instead"] = {"kind": "block"}
    allowed = set()
    resolved = {}
    for r in rules:
        for key in (r.source, r.destination):
            if key == ANY or key in resolved or (names is not None and key not in names):
                continue
            try:
                resolved[key] = resolve(w, key)
                allowed.add(key)
            except Refused:
                pass
    wrong = _malformed(rules, allowed)
    if wrong:
        return refuse("malformed", f"{wrong}; nothing of the answer is used")
    resolved[ANY] = resolve(w, ANY)
    shape = _impossible_shape(rules)
    if shape:
        return refuse("impossible", shape)
    out["rows"].append({"check": "Hosts named", "words": " · ".join(
        resolved[k]["label"] for k in dict.fromkeys(
            x for r in rules for x in (r.source, r.destination)) if k != ANY)})
    # Where: every rule on its source's ingress, one switch for the whole policy.
    placed = set()
    where = ""
    for r in rules:
        try:
            dpid, conn, where = _place(w, resolved[r.source])
        except Refused as exc:
            return refuse("impossible", str(exc))
        placed.add((dpid, conn))
    if len(placed) > 1:
        return refuse("impossible", "its rules' sources enter the fabric at different switches "
                                    f"({', '.join(switch_words(w, d) for d, _c in placed)}): "
                                    "one policy is placed on one switch; ask for each apart")
    dpid, conn = next(iter(placed))
    if instead.get("place") is not None:
        offered = _meter_places(w, dpid, driver, network)
        if int(instead["place"]) not in [o["dpid"] for o in offered]:
            return refuse("malformed", f"switch {instead['place']} is not one the refusal "
                                       "offered (a switch linked to the ingress that reports "
                                       "meters)")
        dpid = int(instead["place"])
        conn = w["connections"].get(dpid) or w["only_connection"]
        where = f"moved from the source's ingress at the person's choice: {where}"
        out["policy"]["instead"] = {"place": dpid}
    out.update(dpid=dpid, connection=conn, where=where)
    # The matches, each rule's, by family.
    matches = []
    for n, r in enumerate(rules):
        ends = _ends(resolved[r.source], resolved[r.destination])
        if not ends:
            return refuse("impossible", f"rule {n + 1} ({rule_words(r)}): its source and "
                                        "destination share no address family (IPv4 or IPv6)")
        matches.append([_match(r, fam, s, d) for fam, s, d in ends])
    # Contradictory, within the request.
    for i in range(len(rules)):
        for j in range(i + 1, len(rules)):
            a, b = rules[i], rules[j]
            if a.kind is b.kind and a.kind is not Kind.rate_limit:
                continue
            for ma in matches[i]:
                for mb in matches[j]:
                    meets, a_in_b, b_in_a = _overlap(ma, mb)
                    if meets:
                        how = ("the first lies inside the second" if b_in_a else
                               "the second lies inside the first" if a_in_b else
                               "their matches overlap")
                        what = ("two rate limits on the same traffic" if a.kind is b.kind else
                                f"the {KIND_WORDS[b.kind.value]} does what the "
                                f"{KIND_WORDS[a.kind.value]} undoes")
                        return refuse("contradictory", (
                            f"part {i + 1} ({rule_words(a)}) and part {j + 1} "
                            f"({rule_words(b)}): {what}. Compared: the two parts' matches "
                            f"({flow_ops.match_words(ma)} against {flow_ops.match_words(mb)}); "
                            f"{how}. Say which should win, or ask again"))
    # Contradictory, against committed policies.
    got = committed(network, now=now)
    if got["state"] != "ok":
        return refuse("unreadable", f"{network}'s flow intent cannot be read ({got['error']}), "
                                    "so the request cannot be checked against committed "
                                    "policies")
    same = []
    for n, r in enumerate(rules):
        for m in matches[n]:
            for p in got["policies"]:
                for rec in p["flows"]:
                    kind = ((rec.get("response") or {}).get("policy") or {}).get(
                        "kinds", {}).get(str(rec.get("cookie"))) or _kind_of(rec)
                    meets, _x, _y = _overlap(m, rec.get("match") or {})
                    if not meets:
                        continue
                    if kind != r.kind.value or kind == "rate_limit":
                        does = {"block": "blocks", "allow": "allows"}.get(kind, "rate-limits")
                        what = ("two rate limits on the same traffic" if kind == r.kind.value
                                else f"it would {KIND_WORDS[r.kind.value]} what that policy "
                                     f"{does}")
                        return refuse("contradictory", (
                            f"part {n + 1} ({rule_words(r)}) contradicts the committed policy "
                            f"{p['id']} (\"{p['words']}\", by {p['by']} at {p['at']}): {what}. "
                            f"Compared: {flow_ops.match_words(m)} against its flow "
                            f"{flow_intent.cookie_hex(rec.get('cookie'))} "
                            f"({flow_ops.match_words(rec.get('match'))}). Withdraw that "
                            "policy's flows on SDN › Flows first, or ask again"))
                    same.append(p["id"])
    out["rows"].append({"check": "Committed policies", "words": (
        f"{len(got['policies'])} committed; none contradicts it" + (
            f" ({', '.join(sorted(set(same)))} {'does' if len(set(same)) == 1 else 'do'} the "
            "same to traffic it overlaps)" if same else ""))})
    # Protected flows, with a narrowing.
    pset = protected.for_network(network)
    if pset.get("state") == "unreadable":
        return refuse("unreadable", f"the protected set could not be read ({pset.get('error')}), "
                                    "so no policy can be checked against it")
    covered, met = [], []
    for n, r in enumerate(rules):
        for m in matches[n]:
            for cls in pset.get("classes") or []:
                hit = protected.overlap(m, cls)
                if hit and cls not in covered:
                    covered.append(cls)
                    met.append(hit)
    if covered:
        classes = pset.get("classes") or []
        # What refused it and what was asked, for the record a refused press keeps
        # (`keep_refusal`, C2944); the check itself writes nothing.
        return refuse("protected", (
            f"{PROTECTED_LEAD}{'s' if len(covered) > 1 else ''} "
            + " and ".join(f"{c['name']} ({c['invariant']}; {c['source']})" for c in covered)
            + f". Compared: the policy's match{'es' if sum(map(len, matches)) > 1 else ''} "
            f"({'; '.join(flow_ops.match_words(m) for ms in matches for m in ms)}) against "
            f"{len(classes)} protected flow{'s' if len(classes) != 1 else ''}; {len(covered)} "
            f"covered. {_narrowing(covered)}"),
            refused_by=[protected.refused_by("class", c["name"], invariant=c["invariant"],
                                             source=c["source"], met=hit,
                                             citation=protected.CITATION)
                        for c, hit in zip(covered, met)],
            asked=[rule_words(r) for r in rules])
    out["rows"].append({"check": "Protected flows", "words": (
        f"none covered ({len(pset.get('classes') or [])} protected flows compared"
        + (f", from {pset.get('source')}" if pset.get("source") else "") + ")")})
    # The switch: its table, its meters where a rule needs one.
    made = flow_ops._driver(network, conn, driver)
    if not made.get("ok"):
        return refuse("unreadable", made.get("error") or f"no driver for {conn!r}")
    drv = made["driver"]
    needs_meter = any(r.kind is Kind.rate_limit for r in rules)
    read = _read(drv, dpid, False)
    if not read["ok"]:
        return refuse("unreadable", read["error"])
    features, meters = None, []
    if needs_meter:
        m = drv.meter_features(dpid)
        features = m.get("features") if m.get("ok") else None
        if not _meters_offered(features):
            said = (f"its meter features could not be read ({m.get('error')})" if not m.get("ok")
                    else "it reports no meters" if not features else
                    f"its meter features are {features}, with no kbit/s DROP band")
            # Drop instead…, and Rate-limit at <switch> instead… for each switch the
            # controller links to the ingress that reports meters (read now).
            offers = [{"kind": "block"}]
            offers += [{"place": o["dpid"], "name": o["name"]}
                       for o in _meter_places(w, dpid, driver, network)]
            return refuse("impossible", (
                f"the rate limit enters at {switch_words(w, dpid)}, and {said}. Compared: the "
                f"action rate-limit against {w['switches'].get(dpid, {}).get('name') or dpid}'s"
                " meter features read from the controller now"), offers=offers)
        mm = drv.meters(dpid)
        if not mm.get("ok"):
            return refuse("unreadable", f"the meters of switch {dpid} could not be read: "
                                        f"{mm.get('error')}")
        meters = mm.get("meters") or []
    flows = read["flows"]
    intent = flow_intent.intent(network, conn)
    if intent["state"] != "ok":
        return refuse("unreadable", f"{network}'s flow intent cannot be read "
                                    f"({intent['error']})")
    own = set(made.get("connection", {}).get("own_cookies") or [0])
    draws = dict(draws or {})
    cookies = list(draws.get("cookies") or [])
    priorities = list(draws.get("priorities") or [])
    changes, effects = [], []
    meter_id = None
    if needs_meter:
        meter_id = draws.get("meter_id") or flow_ops.free_meter_id(meters, features, flows=flows)
        rate = next(r.rate_kbps for r in rules if r.kind is Kind.rate_limit)
        if len({r.rate_kbps for r in rules if r.kind is Kind.rate_limit}) > 1:
            return refuse("impossible", "its rate limits name different rates, and one policy "
                                        "holds one meter: ask for each apart")
        changes.append({"do": "add_meter", "meter": {
            "meter_id": meter_id, "flags": ["KBPS", "STATS"],
            "bands": [{"type": "DROP", "rate": rate}]}})
    classified = flow_intent.classify(flows, made.get("connection") or {"name": conn},
                                      intent)["flows"]
    for i, f in enumerate(classified):
        f.setdefault("id", f"t{f.get('table_id', 0)}/p{f.get('priority', 0)}#{i + 1}")
    k = 0
    for n, r in enumerate(rules):
        for m in matches[n]:
            cookie = cookies[k] if k < len(cookies) else flow_intent.new_cookie()
            # Above EVERY flow that could match it, Mercury's too (no intent cookies passed):
            # a policy never sits at a flow's own priority, where OpenFlow leaves the order
            # undefined, and never under a flow that takes its traffic first; what it then
            # does to a Mercury flow below is the effect's to say (lifts, shadows).
            priority = (priorities[k] if k < len(priorities) else
                        flow_ops.response_priority(flows, own, (), match=m))
            k += 1
            actions = ([] if r.kind is Kind.block else
                       [{"type": "OUTPUT", "port": "NORMAL"}] if r.kind is Kind.allow else
                       [{"type": "METER", "meter_id": meter_id},
                        {"type": "OUTPUT", "port": "NORMAL"}])
            flow = {"table_id": 0, "priority": priority, "cookie": cookie, "idle_timeout": 0,
                    "hard_timeout": r.duration_s, "match": m, "actions": actions}
            eff =flow_intent.effect(dict(flow, owner="mercury"), classified)
            if eff["class"] in ("lifts", "shadows"):
                return refuse("conflict", (
                    f"part {n + 1} ({rule_words(r)}) {eff['words']}. Compared: its match "
                    f"({flow_ops.match_words(m)}) against the {len(flows)} flows of "
                    f"{switch_words(w, dpid)}. Remove that flow on SDN › Flows first, or ask "
                    "again"))
            said = f"part {n + 1}: it {eff['words']}"
            if said not in effects:
                effects.append(said)
            changes.append({"do": "add_flow", "flow": flow})
    out["rows"].insert(1, {"check": "Where it applies", "words": (
        f"{switch_words(w, dpid)}, the source's ingress: {where}"
        + (f"; its meter {meter_id}, the switch reports meters" if needs_meter else
           "; drop flows, no meter needed" if all(r.kind is Kind.block for r in rules) else ""))})
    out["rows"].insert(2, {"check": "Conflicts with installed flows", "words": (
        f"none: it sits above every flow that could match it, and shadows or lifts no flow of "
        f"Mercury's ({len(flows)} flow{'s' if len(flows) != 1 else ''} read). "
        + "; ".join(effects))})
    out["policy"]["kinds"] = {str(c["flow"]["cookie"]): next(
        r.kind.value for r, ms in zip(rules, matches) if c["flow"]["match"] in ms)
        for c in changes if c["do"] == "add_flow"}
    out["ask"] = {"connection": conn, "dpid": dpid, "changes": changes}
    out["draws"] = {"cookies": [c["flow"]["cookie"] for c in changes if c["do"] == "add_flow"],
                    "priorities": [c["flow"]["priority"] for c in changes
                                   if c["do"] == "add_flow"],
                    "meter_id": meter_id}
    out.update(ok=True, state="checked", kind="checked",
               words="checked: every rule resolved, placed and compared")
    return out


def _kind_of(rec: dict) -> str:
    acts = rec.get("actions") or []
    if not acts:
        return "block"
    if any(a.get("type") == "METER" for a in acts):
        return "rate_limit"
    return "allow"


def _meter_places(w: dict, dpid: int, driver, network: str) -> list:
    """The switches the controller links to *dpid* that report meters (read now)."""
    from modules.sdn import flow_ops
    out = []
    for other, _port, conn in w["links"].get(dpid) or []:
        if other in [o["dpid"] for o in out]:
            continue
        made = flow_ops._driver(network, conn, driver)
        if not made.get("ok"):
            continue
        m = made["driver"].meter_features(other)
        if m.get("ok") and _meters_offered(m.get("features")):
            out.append({"dpid": other, "name": (w["switches"].get(other) or {}).get("name")
                        or str(other)})
    return out


# ───────────────────────────────────────────────────────────────────────────── preview, apply

def carried(form_value: str) -> dict:
    """The policy a form carried back (its JSON), or raises Refused."""
    try:
        doc = json.loads(form_value or "")
    except ValueError:
        raise Refused("the form carried no policy: draft it again") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("rules"), list):
        raise Refused("the form's policy is not one: draft it again")
    keep = ("id", "network", "words", "call_id", "rules", "instead")
    return {k: doc[k] for k in keep if k in doc}


def preview(network: str, policy: dict, *, driver=None, instead: dict = None) -> dict:
    """The checked policy compiled and planned (`flow_ops.plan`, nothing sent): ``{"ok",
    "check", "plan"}``; a refusal is the check's or the plan's."""
    from modules.sdn import flow_ops

    got = check(network, policy, driver=driver, instead=instead or policy.get("instead"))
    if not got["ok"]:
        return {"ok": False, "check": got, "plan": None}
    p = flow_ops.plan(network, got["ask"], driver=driver, writer=writer(got["policy"]))
    return {"ok": p["ok"], "check": got, "plan": p}


def writer(policy: dict) -> str:
    return f"policy:{policy.get('id') or '?'}"


def keep_refusal(network: str, got: dict, *, stage: str, actor: str, actor_verified: str = "",
                 now: float = None) -> dict:
    """Keep the record of a policy the protected set refused (C2944), where a person's press
    is answered: *got* is `check`'s answer (a draft, a check again, a confirm) or `preview`'s
    (its check, then the flow-operation core's plan, whose guard also asks the controller's
    control channel and the protected ports and VLANs). ``{}`` when the protected set did not
    refuse it; else `flow_ops.keep_refusal`'s ``{"kept", "id", "error"}``. The record names
    the policy, its words, its rules and the AI call that drafted it. `check` and `preview`
    themselves write nothing."""
    from modules.sdn import flow_ops

    chk = got.get("check") if "check" in got else got
    plan = got.get("plan") if "check" in got else None
    policy = (chk or {}).get("policy") or {}
    said = {"id": policy.get("id") or "", "words": policy.get("words") or ""}
    who = {"what": "policy", "stage": stage, "actor": actor, "actor_verified": actor_verified,
           "call_id": policy.get("call_id") or "", "policy": said, "now": now}
    if chk and not chk.get("ok"):
        return flow_ops.keep_refusal(
            network, chk, asked=[f"“{said['words']}”"] + list(chk.get("asked") or []),
            words=f"{chk.get('title') or 'Refused'}: {chk.get('words') or ''}", **who)
    if plan is not None and not plan.get("ok"):
        return flow_ops.keep_refusal(network, plan, **who)
    return {}


def confirm(network: str, policy: dict, ask: dict, confirmed_hash: str, *, actor: str,
            actor_verified: str = "", driver=None, sleep=time.sleep) -> dict:
    """Apply a previewed policy as *actor*: every check again on the carried policy, compiled
    with the preview's own cookies, meter and priorities (read from the carried *ask*), the
    operation refused unless it is exactly what the policy compiles to now; then
    `flow_ops.apply`, bound to *confirmed_hash*, its record carrying the policy."""
    from modules.sdn import flow_ops

    refused = {"ok": False, "outcome": "refused", "at": "plan", "error": "", "id": "",
               "sent": [], "verify": {"checks": []}, "counters": [], "rollback": {"ran": False},
               "record": {"ok": False, "error": ""}}
    if not actor:
        return dict(refused, error="a policy is applied by someone, and no actor was given")
    adds = [c.get("flow") or {} for c in (ask or {}).get("changes") or []
            if isinstance(c, dict) and c.get("do") == "add_flow"]
    meter = next((c.get("meter") or {} for c in (ask or {}).get("changes") or []
                  if isinstance(c, dict) and c.get("do") == "add_meter"), {})
    draws = {"cookies": [f.get("cookie") for f in adds],
             "priorities": [f.get("priority") for f in adds], "meter_id": meter.get("meter_id")}
    got = check(network, policy, driver=driver, draws=draws, instead=policy.get("instead"))
    if not got["ok"]:
        # A confirm the protected set refuses (the set moved since the preview) is a record.
        kept = keep_refusal(network, got, stage="confirm", actor=actor,
                            actor_verified=actor_verified)
        return dict(refused, error=f"{got['title'] or 'refused'}: {got['words']}",
                    check=got, **({"refusal": kept} if kept else {}))
    if json.dumps(got["ask"], sort_keys=True) != json.dumps(ask, sort_keys=True):
        return dict(refused, error=("the confirm's requests are not what this policy compiles "
                                    "to now (the switch's table or the policy moved since the "
                                    "preview): nothing was sent; preview again"), check=got)
    pol = {k: got["policy"].get(k) for k in ("id", "words", "rules", "call_id", "kinds",
                                             "instead") if k in got["policy"]}
    done = flow_ops.apply(network, got["ask"], confirmed_hash, actor=actor,
                          actor_verified=actor_verified,
                          response={"kind": "policy", "policy": pol,
                                    "action": f"policy {pol.get('id')}"},
                          driver=driver, sleep=sleep, writer=writer(pol))
    return dict(done, check=got)
