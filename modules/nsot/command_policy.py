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
DIALECT_WORDS = {"cisco_ios": "IOS", "cisco_iosxe": "IOS-XE"}
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


def record_measurement(network: str, dialect: str, sent_shapes, *, device: str, run: str,
                       outcome: str, answer: str) -> list:
    """Each of *sent_shapes* on *dialect* with no measurement yet gets this run's: the device,
    the run, when, the outcome and the device's answer (masked, cut). Returns the shapes
    measured now. A launch shape's record names its source (`G7_SOURCE`)."""
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
            if rec is None or rec.get("measured") or rec.get("state") == "provisional":
                continue
            rec["measured"] = dict(measured)
            now.append(shape)
        return now
    return _update(network, change)
