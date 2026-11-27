"""Mercury's rule for raw configuration lines (C3757; the operator, 2026-11-15: "The
measured-shape allowlist is Mercury's rule for raw lines for everyone (people too, as 'Run a
privileged command...' does today), not an AI restriction. The AI gets exactly what a person
gets").

A command plan (`modules/nsot/command_plan.py`) sends lines its template names, each with its
parameters substituted by Mercury from validated values. **Every line is held here, in code,
before a person sees the plan** (`check`), whoever proposed it, and again before it runs:

1. **Refused outright, whatever else is said** (`REFUSED`): reload, erase, format, delete, boot,
   username, AAA, crypto, a line vty, a save (write, copy), ``do`` and ``end``/``exit`` typed as
   lines (the runner enters and leaves config mode itself), each also when negated (``no``,
   ``default``). Refusing by resemblance is safe: a line merely beginning with one of these
   words is refused.
2. **An object the parameters do not name is refused**: a section line naming its object as
   text (``interface GigabitEthernet1/0``) rather than by a parameter (``interface
   {interface}``), so a plan acts only on what its typed parameters were validated as.
3. **Only a measured shape is allowed** (`MEASURED`, per config dialect): the line as the
   template writes it, its parameters as placeholders, under the section it is in
   (``interface {interface} > shutdown``). Anything else is unknown and refused. Allowing by
   resemblance is not safe, so a shape is the whole line, never a prefix.

**Launch shapes**: ``interface {interface}``, ``shutdown`` and ``no shutdown`` under it, on
``cisco_ios`` (the lab's IOSvL2 switches) and ``cisco_iosxe``: as sent by G7's recovery,
measured at its first run. Until a run records the measurement (`record_measurement`, the
runner's, on the first approved run that sends a shape on a dialect), the shape's record says
so: the first live run measures it (C3757).

**A shape not on the list can be proposed, and is then PROVISIONAL** (the operator,
2026-11-15): kept in the network's shape store (`STORE`, `propose`), refused to run until an
admin approves adding it (`approve`: a verified person who is an admin; the AI may propose a
shape and approves none). Its first approved run measures it and records the measurement. A
preview writes nothing (a read writes nothing): it only names the shape and whether it is
provisional. The admin's approval screen is not built yet (C3757).

Names no device and no AI module; reads nothing but the network's shape store.
"""

import logging
import os
import re
import time

log = logging.getLogger(__name__)

#: The shape store, per network (`list_data_path`): proposals, approvals and measurements.
STORE = "command_shapes.json"
#: Where a measured shape came from, as the launch shapes say it (the operator, 2026-11-15).
G7_SOURCE = "as sent by G7's recovery, measured at its first run"
#: Each config dialect's measured shapes: the section chain and the line, placeholders kept.
MEASURED = {
    dialect: {
        "interface {interface}": G7_SOURCE,
        "interface {interface} > shutdown": G7_SOURCE,
        "interface {interface} > no shutdown": G7_SOURCE,
    }
    for dialect in ("cisco_ios", "cisco_iosxe")
}
#: A dialect's name in words: the one table (C4275, `platform.FACT_WORDS`).
from modules.nsot.platform import FACT_WORDS as DIALECT_WORDS  # noqa: E402
#: A line beginning with one of these words is refused, negated or not (rule 1).
REFUSED = ("reload", "erase", "format", "delete", "boot", "username", "aaa", "crypto",
           "line vty", "write", "copy", "do", "end", "exit", "enable secret", "enable password")
#: Words naming an object a section line acts on (rule 2): its object must be a parameter.
OBJECTS = ("interface", "vlan", "router", "line", "ip vrf", "vrf definition", "policy-map",
           "class-map", "route-map", "access-list", "ip access-list", "key chain")
_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]{0,30})\}")
#: Who may approve a provisional shape, in the refusal's words.
ADMIN_WORDS = "an admin (a verified person with the admin role)"


def _words(line: str) -> str:
    return " ".join((line or "").split())


def _bare(text: str) -> str:
    """*text* without a leading ``no`` or ``default``: what it acts on."""
    words = text.split()
    while words and words[0] in ("no", "default"):
        words = words[1:]
    return " ".join(words)


def refused_word(line: str) -> str:
    """The refused word *line* begins with (rule 1), or ``""``."""
    bare = _bare(_words(line).lower())
    for w in REFUSED:
        if bare == w or bare.startswith(w + " "):
            return w
    return ""


def literal_object(line: str) -> str:
    """The object word of a section line whose object is written as text, not a parameter
    (rule 2), or ``""``."""
    text = _bare(_words(line))
    low = text.lower()
    for w in sorted(OBJECTS, key=len, reverse=True):
        if low.startswith(w + " "):
            rest = text[len(w):].strip()
            return "" if _PLACEHOLDER.fullmatch(rest.split()[0]) else w
    return ""


def shapes(lines) -> list:
    """Each template line's shape, ``[(line, shape)]``: a top-level line is its own section;
    an indented line is ``<section> > <line>``. Placeholders are kept."""
    out, section = [], ""
    for raw in lines or []:
        if not str(raw or "").strip():
            continue
        indented = str(raw)[:1] in (" ", "\t")
        text = _words(raw)
        if not indented:
            section = text
            out.append((str(raw), text))
        else:
            out.append((str(raw), f"{section} > {text}" if section else text))
    return out


def check(dialect: str, lines, params=(), *, network: str = "", store=None) -> dict:
    """*lines* (a template's config-mode lines, placeholders kept) held to the rule for
    *dialect*: ``{"ok", "refusals", "unknown", "provisional"}``. *params* are the parameter
    names the template declares; a placeholder naming another is refused. *unknown* lists each
    shape not measured (``{"shape", "state", "words"}``, state ``unknown``, ``provisional`` or
    ``approved``); an approved one is allowed. Reads the network's shape store, writes
    nothing."""
    refusals, unknown = [], []
    if dialect not in MEASURED:
        return {"ok": False, "refusals": [
            f"Mercury's rule for raw lines has measured shapes for "
            f"{', '.join(DIALECT_WORDS[d] for d in MEASURED)}, and this device's platform is "
            f"{dialect or 'unknown'}: nothing is sent to it"], "unknown": [], "provisional": []}
    kept = None
    for raw, shape in shapes(lines):
        w = refused_word(raw)
        if w:
            refusals.append(f"`{_words(raw)}` begins with `{w}`, which Mercury never sends in a "
                            "command plan, whoever proposed it")
            continue
        obj = literal_object(raw)
        if obj:
            refusals.append(f"`{_words(raw)}` names its {obj} as text: a command plan acts only "
                            "on an object its parameters name, validated against Mercury's "
                            "model ({...})")
            continue
        named = set(_PLACEHOLDER.findall(raw))
        stray = sorted(named - set(params or ()))
        if stray:
            refusals.append(f"`{_words(raw)}` names {', '.join(stray)}, which is not among the "
                            f"plan's parameters ({', '.join(params or ()) or 'none'})")
            continue
        if shape in MEASURED[dialect]:
            continue
        if kept is None:
            kept = (store if store is not None else read_store(network)) if network else {}
        rec = (kept.get("shapes") or {}).get(key_of(dialect, shape)) or {}
        state = rec.get("state") or "unknown"
        if state == "approved":
            continue
        words = (f"`{shape}` on {DIALECT_WORDS[dialect]} is not a shape Mercury has measured"
                 + (f"; it was proposed by {rec.get('proposed_by') or 'someone'} at "
                    f"{rec.get('at') or '?'} and is held PROVISIONAL until {ADMIN_WORDS} "
                    "approves adding it" if state == "provisional" else
                    f"; it can be proposed as a shape, and runs once {ADMIN_WORDS} approves it"))
        unknown.append({"shape": shape, "state": state, "words": words})
        refusals.append(words)
    return {"ok": not refusals, "refusals": refusals, "unknown": unknown,
            "provisional": [u["shape"] for u in unknown if u["state"] == "provisional"]}


# ── The shape store: provisional shapes, approvals and measurements ─────────────────────────

def key_of(dialect: str, shape: str) -> str:
    return f"{dialect}: {shape}"


def _path(network: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), STORE)


def read_store(network: str) -> dict:
    """The network's shape store, ``{"shapes": {key: record}}``; ``{}`` when absent. A store
    that exists and cannot be read reads as ``{"unreadable": why}``, never empty: every shape
    not measured is then refused as unknown."""
    import json

    path = _path(network)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {"unreadable": "not an object"}
    except (OSError, ValueError) as exc:
        return {"unreadable": f"{type(exc).__name__}"}


def _update(network: str, change) -> dict:
    """Read-modify-write the store under its lock, replaced atomically; an unreadable store
    refuses the write (`filestore.read_json_for_write`)."""
    import json

    from modules.config import get_list_data_dir
    from modules.filestore import PathLock, read_json_for_write, write_atomic

    path = os.path.join(get_list_data_dir(network), STORE)
    with PathLock(path):
        doc = read_json_for_write(path, empty={"shapes": {}})
        doc.setdefault("shapes", {})
        out = change(doc)
        write_atomic(path, json.dumps(doc, indent=1, sort_keys=True))
    return out


def propose(network: str, dialect: str, shape: str, *, by: str, why: str) -> dict:
    """Hold *shape* (a shape as `shapes` writes it) on *dialect* as PROVISIONAL, proposed by
    *by* (a person or the AI, in words) with *why*. Refused, naming it, when the shape is a
    refused word's, already measured or already held. ``{"ok", "state", "words"}``."""
    if dialect not in MEASURED:
        return {"ok": False, "state": "", "words": f"no dialect {dialect!r} has measured shapes"}
    line = shape.split(" > ")[-1]
    if refused_word(line) or literal_object(line):
        return {"ok": False, "state": "", "words": (
            f"`{shape}` is refused by Mercury's rule for raw lines whatever is measured, so it "
            "cannot be proposed")}
    if shape in MEASURED[dialect]:
        return {"ok": False, "state": "measured", "words": f"`{shape}` is already measured"}
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def change(doc):
        k = key_of(dialect, shape)
        if k in doc["shapes"]:
            return {"ok": False, "state": doc["shapes"][k].get("state", ""),
                    "words": f"`{shape}` is already {doc['shapes'][k].get('state')}"}
        doc["shapes"][k] = {"dialect": dialect, "shape": shape, "state": "provisional",
                            "proposed_by": str(by)[:120], "why": str(why)[:500], "at": at}
        return {"ok": True, "state": "provisional", "words": (
            f"`{shape}` is held provisional until {ADMIN_WORDS} approves adding it")}
    return _update(network, change)


def approve(network: str, dialect: str, shape: str, *, actor: str, actor_verified: str,
            person: bool, admin: bool) -> dict:
    """An admin's approval of a provisional *shape*: only a verified person who is an admin
    (*admin*, the caller's role check); the AI approves none. Its first approved run measures
    it (`record_measurement`). ``{"ok", "words"}``."""
    from modules import identity

    # The caller's word that this is an admin is never trusted alone: the one chokepoint
    # judges the admin right itself first (Gate 1b's review, item 6), the AI holding none.
    why = identity.right_refusal("admin", actor=actor, actor_verified=actor_verified,
                                 person=person)
    if why:
        return {"ok": False, "words": why}
    if admin is not True:
        return {"ok": False, "words": (
            f"adding a shape to Mercury's rule for raw lines is approved by {ADMIN_WORDS}, and "
            f"this request is not one (actor {actor or 'none'}, verified "
            f"{actor_verified or 'none'}, not an admin)")}
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def change(doc):
        rec = doc["shapes"].get(key_of(dialect, shape))
        if not rec or rec.get("state") != "provisional":
            return {"ok": False, "words": f"`{shape}` is not a provisional shape of {network}"}
        rec.update(state="approved", approved_by=actor, approved_at=at)
        return {"ok": True, "words": f"`{shape}` approved; its first run measures it"}
    return _update(network, change)


def approve_as(network: str, dialect: str, shape: str, *, actor: str, actor_verified: str,
               person: bool) -> dict:
    """`approve`, its admin judged by the one chokepoint (`identity.right_refusal`, the admin
    right): what a route or a screen calls. The AI approves none. ``{"ok", "words"}``."""
    return approve(network, dialect, shape, actor=actor, actor_verified=actor_verified,
                   person=person, admin=True)


def provisional(network: str) -> list:
    """Every shape of *network* waiting on an admin (C3763's screen's rows): ``[{"dialect",
    "shape", "proposed_by", "why", "at", "measured"}]``, each its proposal and what its first
    approved run measured (``{}`` until one ran). A read."""
    out = []
    for rec in (read_store(network).get("shapes") or {}).values():
        if isinstance(rec, dict) and rec.get("state") == "provisional":
            out.append({k: rec.get(k) for k in ("dialect", "shape", "proposed_by", "why", "at")}
                       | {"measured": dict(rec.get("measured") or {})})
    return sorted(out, key=lambda r: (r.get("at") or "", r.get("shape") or ""))


def measurement(network: str, dialect: str, shape: str) -> dict:
    """The recorded measurement of *shape* on *dialect* in *network*, or ``{}``."""
    rec = (read_store(network).get("shapes") or {}).get(key_of(dialect, shape)) or {}
    return dict(rec.get("measured") or {})


#: How many people's plan approvals a provisional shape keeps, newest last.
PLAN_APPROVALS_KEPT = 20


def record_measurement(network: str, dialect: str, sent_shapes, *, device: str, run: str,
                       outcome: str, answer: str, approval: dict = None) -> list:
    """Each of *sent_shapes* on *dialect* with no measurement yet gets this run's: the device,
    the run, when, the outcome and the device's answer (masked, cut). Returns the shapes
    measured now. A launch shape's record names its source (`G7_SOURCE`).

    A PROVISIONAL shape is measured only by a run a person approved with its exact lines
    shown (*approval*: ``{"by", "at", "hash", "run"}``, C3902, the operator, 2026-11-17: "a
    person approving a plan with its exact commands shown also approves its provisional
    shapes (one press; the run measures them)"), and keeps that approval among its
    ``plan_approvals``; it stays provisional, so a saved fix runs it Automatic only once an
    admin approves the shape (`check` lets only an approved state run)."""
    from modules.redact import redact_text

    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    measured = {"device": device, "run": run, "at": at, "outcome": outcome,
                "answer": redact_text(answer or "")[:600]}

    def change(doc):
        now = []
        for shape in dict.fromkeys(sent_shapes or ()):
            k = key_of(dialect, shape)
            rec = doc["shapes"].get(k)
            if rec is None and shape in MEASURED.get(dialect, {}):
                rec = doc["shapes"][k] = {"dialect": dialect, "shape": shape,
                                          "state": "measured_list",
                                          "source": MEASURED[dialect][shape]}
            if rec is None:
                continue
            if rec.get("state") == "provisional":
                if not approval:
                    continue
                rec["plan_approvals"] = (list(rec.get("plan_approvals") or [])
                                         + [dict(approval)])[-PLAN_APPROVALS_KEPT:]
            if rec.get("measured"):
                continue
            rec["measured"] = dict(measured)
            now.append(shape)
        return now
    return _update(network, change)


# ── Net-zero lines: what a saved fix's line editor offers and refuses (the operator, ────────
# 2026-11-16, correction 1 to board fix-manual-controls: "a fix's command plan must leave
# running config as it was, so the line editor (New fix and Edit) offers only shapes that keep
# it net-zero, and refuses a lasting one in plain words"). The rule is read from the lines
# alone, before a fix is saved; the run's own net-zero compare (`command_plan_run.net_zero`)
# stays the final guard.

#: The section headers a fix may enter: an interface its typed parameter names, validated on
#: the device's committed intent, so entering it creates nothing (`command_plan.validate`).
NET_ZERO_HEADERS = ("interface {interface}",)
#: The operator's words for a line that would last (2026-11-16).
LASTING_WORDS = ("This line would change {device}'s configuration permanently; a fix must "
                 "leave it as it was. Make lasting changes in Intent.")
#: The on/off pairs known to undo themselves in one batch (the review, 2026-11-16, F3): the
#: measured launch shapes, an interface's administrative state set and set back. Nothing else
#: is called net-zero by resemblance (`ip routing` / `no ip routing`, a description, an access
#: VLAN, a route are not); an admin may mark an approved shape as the other half of one
#: (its store record's ``pair_of``, `declared_pairs`).
LAUNCH_PAIRS = (("interface {interface} > shutdown", "interface {interface} > no shutdown"),)
#: A declared pair is net-zero only from a port that is up (the review, 2026-11-16, C1): a
#: port shut on purpose would come up. A fix sending one carries this precondition, read live
#: (`command_plan.NAMED_CHECKS`), added by its editor and required at save (`pair_refusal`).
PAIR_PRECONDITION = {"name": "The port is not administratively down",
                     "read": "show interfaces status",
                     "expect": "errdisable.port_not_admin_down"}
#: The editor's words for it.
PAIR_WORDS = ("shutdown / no shutdown leaves a port as it was only when it starts up, so "
              "Mercury adds the check that the port is not administratively down, read live "
              "before anything is sent.")
#: The operator's words beside any other pair a fix sends (2026-11-16).
UNPROVEN_WORDS = ("Only shutdown / no shutdown is known to undo itself; other lines are "
                  "checked by the run's before/after compare.")
#: A line beginning with one of these words configures the device as a whole (or another
#: section), never an interface: typed under one, it is refused (F3). Refusing by
#: resemblance is safe.
GLOBAL_ONLY = ("hostname", "ip routing", "ip route", "ipv6 route", "ipv6 unicast-routing",
               "ip domain", "ip name-server", "ip default-gateway", "ip ssh", "ip http",
               "router", "vlan", "vtp", "spanning-tree mode", "spanning-tree vlan",
               "spanning-tree portfast default", "snmp-server", "logging host",
               "logging buffered", "service", "banner", "archive", "errdisable recovery",
               "access-list", "ip access-list",
               "route-map", "class-map", "policy-map", "key chain", "line", "interface",
               "telemetry", "netconf-yang", "restconf", "event manager", "license")


def negation(text: str) -> str:
    """*text*'s own negation: ``no shutdown`` for ``shutdown``, and ``shutdown`` for ``no
    shutdown`` (one leading ``no`` added or taken away)."""
    words = _words(text)
    return words[3:] if words.startswith("no ") else f"no {words}"


def global_only(text: str) -> str:
    """The `GLOBAL_ONLY` word *text* (negated or not) begins with, or ``""``."""
    bare = _bare(_words(text).lower())
    return next((w for w in GLOBAL_ONLY if bare == w or bare.startswith(w + " ")), "")


def declared_pairs(network: str = "") -> set:
    """The on/off pairs known to undo themselves (`LAUNCH_PAIRS`, and each pair *network*'s
    admin approved as one: an approved shape whose record names its other half, ``pair_of``,
    itself approved or measured), each ``(set shape, set-back shape)``. A read."""
    out = set(LAUNCH_PAIRS)
    recs = {r.get("shape"): r for r in ((read_store(network) if network else {})
                                        .get("shapes") or {}).values() if isinstance(r, dict)}
    every = set().union(*[set(m) for m in MEASURED.values()]) if MEASURED else set()
    for shape, r in recs.items():
        other = r.get("pair_of") or ""
        if r.get("state") == "approved" and other and (
                other in every or (recs.get(other) or {}).get("state") == "approved"):
            out.add((shape, other) if not shape.split(" > ")[-1].startswith("no ")
                    else (other, shape))
    return out


def judge(lines, network: str = "") -> dict:
    """*lines* (a fix's config-mode lines as its template writes them, placeholders kept)
    judged net-zero or not in one batch: ``{"lasting": [(line, why)], "unproven": [line],
    "declared": [line]}``, *declared* the lines of declared pairs (`pair_refusal`).
    Net-zero: a top-level header of `NET_ZERO_HEADERS` (entering an interface Mercury's model
    holds), and, under it, a line followed later in that section by its own negation where
    the two are a declared pair (`declared_pairs`: ``shutdown`` then ``no shutdown``).
    *unproven*: any other line its own negation follows in its section, never called
    net-zero; it is left to the run's before/after compare, said in the operator's words
    (`UNPROVEN_WORDS`). *lasting*, refused: a line no negation follows, a negation nothing
    before it set, a global command typed under an interface (`global_only`), any other
    top-level line, and a line under no section. A refused word or an object as text is the
    rule's own refusal (`check`), not judged here."""
    pairs = declared_pairs(network)
    out, unproven, declared, section, open_ = [], [], [], None, []

    def close_section():
        for raw in open_:
            out.append((raw, f"nothing after it in its section undoes `{_words(raw)}` (its "
                             f"own negation, `{negation(raw)}`, would)"))
        open_.clear()
    for raw, shape in shapes(lines):
        indented = str(raw)[:1] in (" ", "\t")
        if not indented:
            close_section()
            if shape in NET_ZERO_HEADERS:
                section = shape
            else:
                section = None
                out.append((raw, "it is a line of the device's global configuration, which "
                                 "nothing in a fix's batch undoes"))
            continue
        if section is None:
            out.append((raw, "it is under no interface Mercury's model holds"))
            continue
        text = _words(raw)
        if global_only(text):
            out.append((raw, f"`{global_only(text)}` configures the device as a whole, not "
                             "an interface"))
            continue
        if not text.startswith("no "):
            open_.append(raw)
            continue
        # A negation closes the line it negates, set before it in this section; one that
        # negates nothing set here would last (``no shutdown`` alone opens a port shut on
        # purpose).
        undoes = next((o for o in open_ if _words(o) == negation(text)), None)
        if undoes is None:
            out.append((raw, f"`{text}` undoes nothing this fix set before it in its section"))
            continue
        open_.remove(undoes)
        if (f"{section} > {_words(undoes)}", f"{section} > {text}") not in pairs:
            unproven += [undoes, raw]
        else:
            declared += [undoes, raw]
    close_section()
    return {"lasting": out, "unproven": unproven, "declared": declared}


def pair_refusal(commands, preconditions, network: str = "") -> str:
    """Why a fix sending *commands* with *preconditions* (a template's items) is not net-zero
    from where it starts, or ``""``: a declared pair (`judge`'s ``declared``) needs
    `PAIR_PRECONDITION` among its preconditions (C1)."""
    if not judge(commands, network)["declared"]:
        return ""
    if any((p or {}).get("expect") == PAIR_PRECONDITION["expect"] for p in preconditions or []):
        return ""
    return ("a fix sending shutdown / no shutdown checks first that the port is not "
            "administratively down (it would come up): its precondition "
            f"\"{PAIR_PRECONDITION['name']}\" is missing")


def lasting(lines, network: str = "") -> list:
    """The lines of *lines* that would last (`judge`'s ``lasting``): ``[(line, why)]``."""
    return judge(lines, network)["lasting"]


def lasting_refusal(lines, device: str = "", network: str = "") -> str:
    """The operator's words for the first line of *lines* that would last (`lasting`), naming
    *device* (or "the device"), with the line and why; ``""`` when none would."""
    got = lasting(lines, network)
    if not got:
        return ""
    raw, why = got[0]
    return (f"`{_words(raw)}`: " + LASTING_WORDS.format(device=device or "the device")
            + f" ({why})")


def offered(network: str = "") -> list:
    """The line shapes a fix's editor offers, each one that keeps it net-zero: every header of
    `NET_ZERO_HEADERS`, and each half of a declared on/off pair under it (`declared_pairs`:
    ``shutdown`` and ``no shutdown``) that every measured dialect allows (`MEASURED`) or
    *network*'s admin approved. ``[{"line", "shape", "words", "state"}]``, *line* as a template
    writes it (an indented line one space in). A read: writes nothing."""
    halves = {s for pair in declared_pairs(network) for s in pair}
    allowed = {}
    every = [set(m) for m in MEASURED.values()]
    for shape in set.intersection(*every) if every else set():
        allowed[shape] = "measured"
    kept = read_store(network) if network else {}
    for rec in (kept.get("shapes") or {}).values():
        if isinstance(rec, dict) and rec.get("state") == "approved" and rec.get("shape"):
            allowed.setdefault(rec["shape"], "approved")
    out = []
    for head in NET_ZERO_HEADERS:
        if head in allowed:
            out.append({"line": head, "shape": head, "words": head, "state": allowed[head]})
        # Each line before its own negation (``shutdown``, then ``no shutdown``): the order a
        # net-zero batch sends them in (`lasting`).
        under = sorted((s for s in allowed if s.startswith(head + " > ")),
                       key=lambda s: (_bare(s[len(head) + 3:]), s[len(head) + 3:]
                                      .startswith("no ")))
        for shape in under:
            text = shape[len(head) + 3:]
            if shape not in halves or f"{head} > {negation(text)}" not in allowed:
                continue
            out.append({"line": " " + text, "shape": shape, "words": text,
                        "state": allowed[shape]})
    return out
