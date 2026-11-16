"""Saved command plans: self-heal scripts (C3696) and reusable actions (the operator, 2026-11-15,
"clumsy processes become tools"; Gate 1b). Each is a command plan (`command_plan`: data, never
code) saved from a VERIFIED run of one, with its parameters left open, run by the same runner
(`command_plan_run.run`) and held by the same rule for raw lines (`command_policy`), with no AI
call and no code of its own.

**A self-heal script** (``kind: script``, one network's): the plan, and the problem's R4 match
(`problem.MATCH_FIELDS`: condition, cause, port role, cause cleared; never an alert's name or a
raw line, `match_refusal`), and how each of its parameters is filled from the classified problem
(``fills``: each parameter named by a field of `problem.FIELDS`). It starts in Dry run: when an
incident's problem matches (`fire_matching`), Mercury fills the parameters and previews the plan
(asking no device) and records what it would run, in the script's track record. A person with
self-healing rights promotes it (`promote`, binding the plan's digest); then, when it fires, it
runs through the runner as the promotion's authority (`authority_refusal`), its run Mercury's
on the promoter's standing approval, never the AI's.

**A reusable action** (``kind: action``, the installation's): a named, parameterised entry
("Bounce interface" with device and interface) the catalog lists beside the built-in command
plans (`heal.catalog.entries`, a `PlanStep` each), so it is a plan step by registration and an
entry the AI may propose. Only an admin saves one.

**A saved fix is one object, both at once** (C3849, the operator, 2026-11-16: "one object, not
two"): ``kind: fix``, its network's, optionally ``shared`` with every network: the plan (its
own template copy), optionally a problem match with its fills (then it is offered on every
matching incident, `fix_offers`, and, promoted to Auto, runs by itself there, `fire_matching`),
and always a parameterised action: listed in the catalog for its network and, shared, for
every network (`actions`), runnable by any engineer, proposable by the AI. One verified run
saves one fix: a save of a run already saved answers the fix saved from it (`save_fix`).

**Expand, then contract:** the entries saved before fixes were one object (``script`` and
``action``) are kept as they were written and never rewritten in place; every read presents
each entry as a fix (`as_fix`): an old script is its network's, not shared, matched, and kept
out of the catalog as before (its run's twin action, when one was saved, is the catalog's); an
old action is the network it was saved on's, not shared, with no match (the operator,
2026-11-16: sharing is an option, off by default). New saves write the fix's shape only.

**Who** (`identity.right_refusal`, the one chokepoint): running a fix, any engineer
(``run_plan``); saving or promoting a fix with a match (matched or automatic), the
self-healing right; saving a fix with no match (manual only), the admin right; the AI proposes
and never approves or saves (`identity.ai_acting_refusal`). The store is the installation's
(`STORE`), locked and replaced atomically.
"""

import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

STORE = "saved_plans.json"
#: The saved reusable actions as one family of the AI's tools (tests/ai_tool_homes.py): their
#: keys are people's, so they are declared together.
FAMILY = "saved action"
#: The stored kinds: a fix (C3849, every new save), and the two read as fixes (`as_fix`).
KINDS = ("script", "action", "fix")
FIX = "fix"
MODES = ("dry_run", "auto")
#: How a fix runs (`how_of`): by a person only; offered on matching incidents; and, promoted,
#: by itself on them as well.
HOWS = ("manual", "matched", "automatic")
#: How many fires a script's track record keeps, newest last.
TRACK_KEPT = 50
_SLUG = re.compile(r"[^a-z0-9]+")


class Refused(ValueError):
    """Nothing was saved or run; the words say why."""


def _path() -> str:
    from modules import config

    return os.path.join(config.DATA_DIR, STORE)


def _iso(epoch: float = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if epoch is None
                                                           else epoch))


def stamp() -> tuple:
    """The store's identity now: its path, inode, size and modification time to the
    nanosecond; raises `OSError` when there is none. Every read compares it, so nothing read
    is kept past a change, in any process (a write replaces the file: a new inode)."""
    st = os.stat(_path())
    return (_path(), st.st_ino, st.st_size, st.st_mtime_ns)


def read() -> dict:
    """The store, ``{"plans": {key: entry}}``; ``{"plans": {}}`` when absent; a store that
    cannot be read is ``{"plans": {}, "unreadable": why}`` (nothing saved is then offered)."""
    path = _path()
    try:
        mtime = stamp()
    except OSError:
        return {"plans": {}}
    if _READ.get("mtime") == mtime and _READ.get("path") == path:
        return json.loads(_READ["text"])
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        got = json.loads(text)
    except (OSError, ValueError) as exc:
        return {"plans": {}, "unreadable": type(exc).__name__}
    if not (isinstance(got, dict) and isinstance(got.get("plans"), dict)):
        return {"plans": {}, "unreadable": "not a store"}
    _READ.update(mtime=mtime, path=path, text=text)
    return got


#: The store as last read, by its file's modification time (a read per question otherwise).
_READ = {}


def _update(change):
    from modules.filestore import PathLock, read_json_for_write, write_atomic

    path = _path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PathLock(path):
        doc = read_json_for_write(path, empty={"plans": {}})
        doc.setdefault("plans", {})
        out = change(doc)
        # In the order written: a template's parameters keep their own order (as a person
        # reads them, and as its steps take them).
        write_atomic(path, json.dumps(doc, indent=1))
    return out


_CACHE = {"mtime": None, "templates": {}}


def templates() -> dict:
    """Every saved plan's template, by key (`command_plan.Template`), parsed again when the
    store changed; one that no longer parses is left out, logged."""
    from modules.nsot import command_plan as CP

    try:
        mtime = stamp()
    except OSError:
        return {}
    if _CACHE["mtime"] != mtime:
        out = {}
        for key, e in (read().get("plans") or {}).items():
            try:
                out[key] = CP.parse(e.get("template"))
            except CP.Refused as exc:
                log.error("saved plans: %s no longer parses: %s", key, exc)
        _CACHE.update(mtime=mtime, templates=out)
    return dict(_CACHE["templates"])


def how_of(e: dict) -> str:
    """How the fix *e* runs (`HOWS`): ``manual`` with no match; ``automatic`` with one,
    promoted (Auto); else ``matched`` (Dry run: offered, recorded when it fires)."""
    if not e.get("match"):
        return "manual"
    return "automatic" if e.get("mode") == "auto" else "matched"


def as_fix(e: dict) -> dict:
    """The stored entry *e* read as a fix (a copy; the store is never rewritten in place):
    ``kind`` ``fix``, ``saved_as`` the kind it was written as, ``network``, ``shared``,
    ``catalog`` (whether it is an action of the catalog), ``match``, ``fills``, ``words`` and
    ``how`` (`how_of`). An old ``script`` is its network's, not shared, and stays out of the
    catalog as before; an old ``action`` is not shared (sharing is an option, off by default:
    the operator, 2026-11-16) with no match, its network the one it was saved on."""
    kind = e.get("kind") or ""
    out = dict(e, saved_as=kind, kind=FIX, match=dict(e.get("match") or {}),
               fills=dict(e.get("fills") or {}), track=list(e.get("track") or []),
               words=str((e.get("template") or {}).get("words") or ""))
    if kind == "script":
        out.update(network=str(e.get("network") or ""), shared=False, catalog=False)
    elif kind == "action":
        # The network it was saved on, not shared (the operator, 2026-11-16: "a saved fix
        # belongs to the network it was saved on, with sharing to all networks as an option,
        # off by default"): an old action was saved with no sharing choice.
        out.update(network=str((e.get("from_run") or {}).get("network") or ""), shared=False,
                   catalog=True, match={}, fills={}, mode="")
    else:
        out.update(network=str(e.get("network") or ""), shared=bool(e.get("shared")),
                   catalog=True)
    out["how"] = how_of(out)
    return out


def _is_matched(e: dict) -> bool:
    """Whether the stored entry *e* is one that fires on a match: an old script, or a fix
    saved with a match (`how_of`)."""
    return e.get("kind") == "script" or (e.get("kind") == FIX and bool(e.get("match")))


def fixes(network: str = None, *, deleted: bool = False) -> dict:
    """Every saved fix, by key, each read as a fix (`as_fix`); with *network*, those it may use:
    its own and the shared ones. A deleted fix (`retire`) is left out unless *deleted* (its
    page and the Fixes list's Deleted filter read it: its record, origin and runs stay)."""
    every = {k: as_fix(e) for k, e in (read().get("plans") or {}).items()
             if isinstance(e, dict) and e.get("kind") in KINDS
             and (deleted or not e.get("retired"))}
    if network is None:
        return every
    return {k: f for k, f in every.items() if f["network"] == network or f["shared"]}


def actions(network: str = None) -> dict:
    """The saved fixes the catalog lists (each a parameterised action, `as_fix`'s
    ``catalog``), by key: every one, or *network*'s own and the shared ones; never a deleted
    one (`fixes`): the AI cannot propose it and the catalog's check refuses it."""
    return {k: f for k, f in fixes(network).items() if f["catalog"]}


def scripts(network: str) -> dict:
    """*network*'s own fixes with a match (an old script or a fix saved with one), by key, each
    read as a fix: those offered on its matching incidents and fired on them; never a deleted
    one (`fixes`), so it is never fired, matched, offered, batched or retried."""
    return {k: f for k, f in fixes().items() if f["match"] and f["network"] == network}


# ── Delete… and Restore… (the operator, 2026-11-16: kept, never removed) ───────────────────

#: Each deletion and restore kept on the entry, newest last (``retirements``).
RETIRE_ACTIONS = ("deleted", "restored")


def change_right(e: dict) -> str:
    """The right that changing the stored fix *e* takes, as saving it did (`save_fix`): the
    self-healing right for a fix with a match (an old script, or a fix saved with one), the
    admin right for one with none."""
    return "self_healing" if _is_matched(e) else "admin"


def _retire_refusal(e, key: str, network: str, reason: str, who: dict) -> str:
    from modules import identity
    from modules.nsot import authorisation

    if not isinstance(e, dict) or e.get("kind") not in KINDS:
        return f"{key} is no saved fix"
    if as_fix(e)["network"] != network:
        return f"{key} is a saved fix of {as_fix(e)['network'] or 'no network'}, not of {network}"
    never = identity.ai_acting_refusal("delete or restore a saved fix")
    if never:
        return never
    why = identity.right_refusal(change_right(e), **who)
    if why:
        return why
    words = " ".join(str(reason or "").split())
    if len(words.split()) < authorisation.MIN_WORDS or len(words) < authorisation.MIN_CHARS:
        return (f"a reason is at least {authorisation.MIN_WORDS} words and "
                f"{authorisation.MIN_CHARS} characters, and {words or 'none'!r} is not")
    return ""


def retire(key: str, *, network: str, reason: str, actor: str, actor_verified: str,
           person: bool, restore: bool = False) -> dict:
    """Delete (or, *restore*, bring back) the saved fix *key* of *network*, as a verified
    person holding the right that changing it takes (`change_right`), with *reason*: written
    under the store's lock, never removing the entry (expand, then contract): ``retired``
    ``{"by", "at", "reason"}`` set (or cleared), and the action appended to its
    ``retirements``, which History draws (`history_sources.saved_fixes`). A deleted fix is out
    of `fixes`, `scripts` and `actions`, so nothing offers, fires or proposes it; its record,
    origin and runs stay. Raises `Refused`, nothing written. The fix (`as_fix`)."""
    who = dict(actor=actor, actor_verified=actor_verified, person=person)
    words = " ".join(str(reason or "").split())[:500]

    def change(doc):
        e = doc["plans"].get(key)
        why = _retire_refusal(e, key, network, words, who)
        if why:
            raise Refused(why)
        if restore and not e.get("retired"):
            raise Refused(f"{e.get('name') or key} is not deleted: nothing to restore")
        if not restore and e.get("retired"):
            raise Refused(f"{e.get('name') or key} is deleted already, by "
                          f"{(e['retired'] or {}).get('by') or 'a person not recorded'}")
        row = {"action": RETIRE_ACTIONS[1 if restore else 0], "by": actor, "at": _iso(),
               "reason": words, "verified": who["actor_verified"]}
        e["retirements"] = list(e.get("retirements") or []) + [row]
        if restore:
            e.pop("retired", None)
        else:
            e["retired"] = {k: row[k] for k in ("by", "at", "reason")}
        return as_fix(e)
    got = _update(change)
    # The catalog's entries and plan steps follow at once in this process.
    from modules import plan_engine
    plan_engine.refresh_saved_kinds()
    return got


# ── The match: R4's fields only ─────────────────────────────────────────────────────────────

def match_refusal(match) -> str:
    """Why *match* is not a self-heal script's match (``""`` when it is): an object of the
    classified problem's match fields only (`problem.MATCH_FIELDS`), its condition one of
    `problem.CONDITIONS`, ``cleared`` one of `problem.CLEARED`, every value text. A field
    outside the schema (an alert's name, a raw line) is refused by name."""
    from modules import problem as P

    if not isinstance(match, dict) or not match:
        return "a match is an object of the problem's fields " + ", ".join(P.MATCH_FIELDS)
    outside = sorted(set(match) - set(P.MATCH_FIELDS))
    if outside:
        return (f"a match names only the classified problem's fields "
                f"({', '.join(P.MATCH_FIELDS)}), and it names {', '.join(outside)}: a saved "
                "script never matches an alert's name or a raw line")
    if not all(isinstance(v, str) for v in match.values()):
        return "each field of a match is text"
    if match.get("condition") not in P.CONDITIONS:
        return (f"a match names the problem's condition, one of Mercury's, and "
                f"{match.get('condition')!r} is none")
    if "cleared" in match and match["cleared"] not in P.CLEARED:
        return f"a match's cleared is one of {', '.join(c for c in P.CLEARED if c)}"
    return ""


def matches(match: dict, problem) -> bool:
    """Whether *problem* (a `problem.Problem` or its dict) holds every field of *match*."""
    got = problem.as_dict() if hasattr(problem, "as_dict") else dict(problem or {})
    return bool(match) and all(str(got.get(k) or "") == v for k, v in match.items())


def fill_of(name: str, spec) -> tuple:
    """``(field, mapping)``: where parameter *name*'s value comes from in the classified
    problem. *spec* is a field of `problem.FIELDS` (its value as it is), or a mapping from the
    problem's values to the plan's words, ``{"from": field, "map": {value: word}}`` or, from
    the field of the parameter's own name, the map alone (``cause: {BPDU guard: bpduguard}``)."""
    if isinstance(spec, str):
        return spec, None
    if isinstance(spec, dict) and set(spec) == {"from", "map"}:
        return spec["from"], spec["map"]
    return name, spec


def fills_refusal(template, fills) -> str:
    """Why *fills* does not fill every parameter of *template* from the problem's fields
    (``""`` when it does): each parameter's fill (`fill_of`) from a field of `problem.FIELDS`,
    the device's from ``device``; a choice parameter's through a map naming one of its choices
    for each problem value it takes (the problem's words are never the plan's by chance)."""
    from modules import problem as P

    names = list(template.parameters)
    if not isinstance(fills, dict) or set(fills) != set(names):
        return f"a script fills exactly its plan's parameters ({', '.join(names)})"
    for name, spec in fills.items():
        field, mapping = fill_of(name, spec)
        if field not in P.FIELDS:
            return (f"each parameter is filled from a field of the classified problem "
                    f"({', '.join(P.FIELDS)}), and {name}'s {field!r} is not one")
        kind = template.parameters[name]
        if kind.get("type") == "choice":
            of = list(kind.get("of") or [])
            if (not isinstance(mapping, dict) or not mapping
                    or not all(isinstance(k, str) and v in of for k, v in mapping.items())):
                return (f"{name} is one of {', '.join(of)}: it is filled through a map from "
                        f"the problem's {field} to those words, each named")
        elif mapping is not None and not (isinstance(mapping, dict) and all(
                isinstance(k, str) and isinstance(v, str) for k, v in mapping.items())):
            return f"{name}'s map is from the problem's words to the plan's, each text"
    if fill_of("device", fills["device"]) != ("device", None):
        return "the device parameter is filled from the problem's device"
    return ""


def fill(entry: dict, problem) -> dict:
    """The plan's values from *problem* (`fills`): each parameter its field's value, through
    its map when it has one, validated by the runner's own preview, never trusted here. A value
    a map does not name raises `Refused`, naming the parameter, the value and the map's."""
    got = problem.as_dict() if hasattr(problem, "as_dict") else dict(problem or {})
    out = {}
    for name, spec in (entry.get("fills") or {}).items():
        field, mapping = fill_of(name, spec)
        value = str(got.get(field) or "")
        if mapping is not None:
            if value not in mapping:
                raise Refused(f"{name}: the problem's {field} is {value!r}, which this script's "
                              f"map does not name ({', '.join(map(repr, mapping))}); nothing "
                              "is filled or run")
            value = mapping[value]
        out[name] = value
    return out


def _incidents_problems(network: str) -> list:
    """``[(incident id, problem)]`` for *network*'s open incidents, each classified as its page
    classifies it (`problem.classify`). A read."""
    from modules import problem as P
    from modules.heal import incidents

    out = []
    for rec in (incidents.read(network).get("incidents") or []):
        if not isinstance(rec, dict) or rec.get("state") == "closed":
            continue
        out.append((str(rec.get("id") or ""), P.classify({"incident": rec, "entry": {}})))
    return out


def match_preview(network: str, match: dict) -> dict:
    """What *match* would match now on *network*: ``{"ok", "refused", "matched": [{"incident",
    "problem"}], "read"}``, the open incidents read and those whose classified problem holds
    the match. A read."""
    why = match_refusal(match)
    if why:
        return {"ok": False, "refused": why, "matched": [], "read": 0}
    got = _incidents_problems(network)
    return {"ok": True, "refused": "", "read": len(got),
            "matched": [{"incident": i, "problem": p.as_dict()} for i, p in got
                        if matches(match, p)]}


# ── Saving, from a verified run ─────────────────────────────────────────────────────────────

def _verified_run(network: str, run_id: str) -> dict:
    """The command-plan run *run_id* of *network*, refused unless its own verify passed."""
    from modules.nsot import privileged

    try:
        rec = privileged.get(network, run_id)
    except (ValueError, OSError):
        rec = None
    if not isinstance(rec, dict) or rec.get("kind") != "command_plan":
        raise Refused(f"{run_id} is no command plan's run of {network}")
    if rec.get("state") != "done":
        raise Refused(f"{run_id} did not pass its own verify "
                      f"({rec.get('outcome') or 'no outcome'}): only a verified fix is saved")
    return rec


def _key(kind: str, name: str) -> str:
    slug = _SLUG.sub("-", (name or "").lower()).strip("-")[:40]
    if not slug:
        raise Refused("a saved plan is named in words")
    return f"{kind}-{slug}"


def _template_doc(rec: dict, key: str, name: str, words: str) -> dict:
    from modules.nsot import command_plan as CP

    doc = dict(CP.template_of(rec.get("key")).doc, key=key, title=name)
    if words:
        doc["words"] = words
    CP.parse(doc)
    return doc


def _saved_from_run(e: dict, network: str, run_id: str) -> bool:
    """Whether the stored entry *e* was saved from *network*'s run *run_id* (`as_fix`'s
    network: an old action's is the one its run was on)."""
    return ((e.get("from_run") or {}).get("run") == run_id
            and as_fix(e)["network"] == network)


def _store(entry: dict) -> dict:
    """*entry*, a new fix, stored under the store's lock, and read back as a fix (`as_fix`,
    ``already`` False); or, when its run is saved already (in any kind), the fix saved from it
    (`_again`): one verified run, one fix."""
    from modules.nsot import command_plan as CP

    network, run_id = entry["network"], (entry.get("from_run") or {}).get("run")

    def change(doc):
        for old in doc["plans"].values():
            if isinstance(old, dict) and _saved_from_run(old, network, run_id):
                if old.get("retired"):
                    # A deleted fix is never answered as "already saved" nor changed in place
                    # (the review, 2026-11-16): it is said, with the way back.
                    raise Refused(f"this run was saved as {old.get('name') or old.get('key')}, "
                                  "which is deleted; Restore… on its page brings it back")
                return _again(old, entry)
        if entry["key"] in doc["plans"]:
            if (doc["plans"][entry["key"]] or {}).get("retired"):
                raise Refused(f"a fix named {entry['name']} is saved already and deleted; "
                              "Restore… on its page brings it back, or choose another name")
            raise Refused(f"a plan {entry['key']} is saved already")
        if entry["key"] in CP.builtin():
            raise Refused(f"{entry['key']} is the key of a plan that ships with Mercury")
        doc["plans"][entry["key"]] = entry
        return dict(as_fix(entry), already=False, changed=False)
    return _update(change)


def _again(old: dict, entry: dict) -> dict:
    """A save of a run already saved as *old* (inside `_store`'s lock): *old* as a fix,
    ``already``; but a manual fix of the fix's own shape that a save with a match (*entry*'s)
    finds takes that match, its fills and its mode (``changed``; the self-healing right that
    save asked). An old entry is never rewritten (expand, then contract)."""
    from modules.nsot import command_plan as CP

    if not (entry["match"] and old.get("kind") == FIX and not old.get("match")):
        return dict(as_fix(old), already=True, changed=False)
    # The fills are written onto OLD's template, so they are checked against it (the review,
    # 2026-11-16: a built-in plan changed between the two saves could name other parameters,
    # leaving an Automatic fix that every fire refuses and no incident offers).
    why = fills_refusal(CP.parse(old["template"]), entry["fills"])
    if why:
        raise Refused(f"{old.get('key')} is saved already, and this save's fills do not fit "
                      f"its plan: {why}")
    old.update(match=entry["match"], fills=entry["fills"], mode=entry["mode"],
               changed_by=entry["saved_by"], changed_at=_iso())
    if entry["mode"] == "auto":
        old.update(promoted_by=entry["promoted_by"], promoted_at=_iso(),
                   digest=CP.parse(old["template"]).digest)
    return dict(as_fix(old), already=False, changed=True)


def save_fix(network: str, *, run_id: str, name: str, actor: str, actor_verified: str,
             person: bool, match: dict = None, fills: dict = None, words: str = "",
             shared: bool = False, dry_run: bool = False, incident: str = "") -> dict:
    """Save the verified run *run_id* of *network* as one fix (C3849): its plan with its
    parameters open, named *name* and said in *words*, its network's (*shared*: every
    network's catalog lists it too), an action of the catalog from now (`actions`). With
    *match* (`match_refusal`) and *fills* (`fills_refusal`) it is also offered on every
    matching incident and saved in Auto, promoted by the person saving it: saving a verified
    fix is the approval (the operator, 2026-11-15); *dry_run* keeps it in Dry run until
    promoted, and the network's self-healing mode still governs whether it acts (`mode_now`).
    Needs the self-healing right with a match, the admin right without. A run already saved
    answers its fix (`_store`). *incident*, the incident whose card saved it, is kept on its
    ``from_run`` (its page's "Saved from", C3849 piece 3; an entry saved before has none, and
    its page finds the incident its run fixed). The fix (`as_fix`), with ``already`` and
    ``changed``. Raises `Refused`, nothing saved."""
    from modules import identity
    from modules.nsot import command_plan as CP

    match = dict(match or {})
    why = identity.right_refusal("self_healing" if match else "admin", actor=actor,
                                 actor_verified=actor_verified, person=person)
    if why:
        raise Refused(why)
    if match:
        why = match_refusal(match)
        if why:
            raise Refused(why)
    rec = _verified_run(network, run_id)
    key = _key(FIX, name)
    doc = _template_doc(rec, key, name, words)
    t = CP.parse(doc)
    if match:
        why = fills_refusal(t, fills)
        if why:
            raise Refused(why)
    e = {"key": key, "kind": FIX, "network": network, "shared": bool(shared),
         "name": name[:120], "template": doc, "match": match,
         "fills": dict(fills) if match else {}, "saved_by": actor, "saved_at": _iso(),
         "from_run": {"network": network, "run": run_id, "plan": rec.get("key"),
                      "at": rec.get("at"), "by": rec.get("actor"),
                      **({"incident": str(incident)[:64]} if incident else {})}, "track": []}
    if match:
        e["mode"] = "dry_run"
        if not dry_run:
            # As `promote` binds it: the person, when, and the plan's digest.
            e.update(mode="auto", promoted_by=actor, promoted_at=_iso(), digest=t.digest)
    got = _store(e)
    # Registered at once in this process: the catalog's entry and the plan step.
    from modules import plan_engine
    plan_engine.refresh_saved_kinds()
    return got


def save_script(network: str, *, run_id: str, name: str, match: dict, fills: dict,
                actor: str, actor_verified: str, person: bool, dry_run: bool = False,
                shared: bool = False, incident: str = "") -> dict:
    """The card's Save (`routes/saved_plans_v2.save_script`): the verified run saved as one fix
    with *match* and *fills* (`save_fix`), in Auto unless *dry_run*. Needs the self-healing
    right. Raises `Refused`, nothing saved."""
    return save_fix(network, run_id=run_id, name=name, match=match, fills=fills,
                    dry_run=dry_run, shared=shared, actor=actor,
                    actor_verified=actor_verified, person=person, incident=incident)


def promote(key: str, *, actor: str, actor_verified: str, person: bool,
            network: str = "") -> dict:
    """Promote the script *key* of *network* from Dry run to Auto, binding its plan's digest:
    needs the self-healing right. Refused (`Refused`) for a key of another network, and for a
    script in Auto already (its promoter is kept)."""
    from modules import identity
    from modules.nsot import command_plan as CP

    why = identity.right_refusal("self_healing", actor=actor, actor_verified=actor_verified,
                                 person=person)
    if why:
        raise Refused(why)

    def change(doc):
        e = doc["plans"].get(key)
        if not e or not _is_matched(e) or e.get("retired"):
            raise Refused(f"{key} is no saved self-heal script"
                          + (" (it is deleted: Restore… on its page brings it back)"
                             if (e or {}).get("retired") else ""))
        if network and e.get("network") != network:
            raise Refused(f"{key} is a self-heal script of {e.get('network')}, not of {network}")
        if e.get("mode") == "auto":
            raise Refused(f"{key} is in Auto already, promoted by {e.get('promoted_by')}")
        e.update(mode="auto", promoted_by=actor, promoted_at=_iso(),
                 digest=CP.parse(e["template"]).digest)
        return as_fix(e)
    return _update(change)


def save_action(network: str, *, run_id: str, name: str, words: str, actor: str,
                actor_verified: str, person: bool, shared: bool = False,
                incident: str = "") -> dict:
    """The card's Save as a reusable action (`routes/saved_plans_v2.save_action`): the verified
    run saved as one fix with no match (`save_fix`), named *name* and said in *words*, its
    network's; shared with every network only when *shared* is True (an option, off by
    default: the operator, 2026-11-16). Needs the admin right. Raises `Refused`."""
    return save_fix(network, run_id=run_id, name=name, words=words, shared=shared,
                    actor=actor, actor_verified=actor_verified, person=person,
                    incident=incident)


# ── Firing: Dry run records, Auto runs, no AI call ──────────────────────────────────────────

def authority_refusal(key: str, authority, network: str = "") -> str:
    """``""``, or why *authority* (``{"script": key}``, a promoted script's) does not stand
    for a person's approval of the run of *key* on *network*: the script exists, is *network*'s,
    is in Auto, its plan's digest is the one promoted, its promoter still holds the self-healing
    right, and no AI entry point is running (the AI approves nothing)."""
    from modules import identity
    from modules.nsot import command_plan as CP

    if not isinstance(authority, dict) or authority.get("script") != key:
        return "the run's authority names no saved script of this plan"
    never = identity.ai_acting_refusal("run a saved script")
    if never:
        return never
    e = (read().get("plans") or {}).get(key) or {}
    if e.get("retired"):
        # A deleted fix's standing approval stands for nothing (Delete…, 2026-11-16).
        r = e["retired"] or {}
        return (f"{e.get('name') or key} was deleted by {r.get('by') or 'a person not '
                'recorded'} at {r.get('at') or 'an unrecorded time'}")
    if not _is_matched(e) or e.get("mode") != "auto":
        return f"{key} is not a saved script in Auto"
    if e.get("network") != network:
        return (f"{key} is a self-heal script of {e.get('network') or 'no network'}, and this "
                f"run is on {network or 'no network'}")
    if CP.parse(e["template"]).digest != e.get("digest"):
        return f"{key}'s plan is not the one promoted"
    if not identity.holds("self_healing", e.get("promoted_by") or ""):
        return f"{e.get('promoted_by')}, who promoted {key}, no longer holds self-healing rights"
    return ""


def _track(key: str, row: dict) -> None:
    def change(doc):
        e = doc["plans"].get(key)
        if e is not None:
            e["track"] = (list(e.get("track") or []) + [row])[-TRACK_KEPT:]
    _update(change)


def _stands(row: dict, incident: str, mode: str, retry: str = "") -> bool:
    """Whether a track *row* stands for *mode*'s fire on *incident*: a Dry run's record, or an
    Auto run in flight (``firing``) or one that sent anything (``sent``), passed or not, so a
    rolled-back or refused-at-the-device run is never tried again on every pass. A row held by
    a guard sent nothing, and stands for nothing. Under a *retry* (the retry pass's key for one
    trigger on one incident, `modules/heal/retry.py`; the operator, 2026-11-16: a failed fix is
    tried once more per trigger), only a row in flight, a run that verified (never a fix that
    worked run again, even when its close was refused) or that retry's own row stands, so the
    retry fires each script once and never twice."""
    if row.get("incident") != incident or row.get("mode") != mode:
        return False
    if row.get("state") == "firing":
        return True
    if retry:
        return row.get("retry") == retry or (mode == "auto" and bool(row.get("ok")))
    return mode == "dry_run" or bool(row.get("sent"))


def _claim(key: str, incident: str, mode: str, retry: str = ""):
    """``(row, None)``: a ``firing`` row of *key* on *incident* in *mode*, written under the
    store's lock before anything runs, its ``id`` the one `_settle` finishes; or ``(None,
    row)``, the row already standing for it (`_stands`): the heal decision and the
    investigation never both run one, and neither runs while the other's is in flight.
    *retry*: the retry pass's key, kept on the row (`_stands`)."""
    import uuid

    def change(doc):
        e = doc["plans"].get(key)
        if e is None:
            raise Refused(f"{key} is no saved script")
        for row in reversed(e.get("track") or []):
            if _stands(row, incident, mode, retry):
                return None, dict(row)
        row = {"id": uuid.uuid4().hex, "at": _iso(), "incident": incident, "mode": mode,
               "state": "firing", "sent": False, "ok": False, "hash": "", "run": "",
               "words": "firing", **({"retry": retry} if retry else {})}
        e["track"] = (list(e.get("track") or []) + [row])[-TRACK_KEPT:]
        return dict(row), None
    return _update(change)


def _settle(key: str, row_id: str, **done) -> dict:
    """The claimed row *row_id* of *key* finished with *done*, its state ``done``."""
    def change(doc):
        e = doc["plans"].get(key) or {}
        for row in e.get("track") or []:
            if row.get("id") == row_id:
                row.update(done, state="done")
                return dict(row)
        return {}
    return _update(change)


def mode_now(entry: dict, heal_mode: str) -> str:
    """What a script does when it fires, under self-healing's mode on its network (*heal_mode*,
    `heal.policy.current`): nothing while self-healing is off (``off``); ``auto`` only when
    both the script was promoted and self-healing is in Auto; else ``dry_run``."""
    if heal_mode not in MODES:
        return "off"
    return "auto" if entry.get("mode") == "auto" and heal_mode == "auto" else "dry_run"


def fire(network: str, key: str, problem, incident: str, *, sources=None,
         heal_mode: str = "auto", record: dict = None, force_dry: bool = False,
         claimed: dict = None, batch: dict = None, expect_hash: str = "",
         retry: str = "") -> dict:
    """Script *key* fired on *problem* in *incident*, in the mode self-healing allows it now
    (`mode_now`; Dry run when *force_dry*, another script having sent already), claimed first
    (`_claim`: one standing fire per incident and mode): its values filled from the problem
    (`fill`, a value its map does not name refused by name) and the plan previewed by the
    runner's own preview (asking no device). In Dry run, what it would run is recorded and
    nothing is sent; in Auto, the heal guards for its device are asked first (`decide.
    script_hold`, on the incident's *record*): one holding it sends nothing and the row says
    which; else the plan runs through the runner (`command_plan_run.run`) on the promotion's
    authority. No AI call either way. ``{"mode", "ok", "sent", "words", "hash", "values",
    "run", "already", "state"}``.

    G6's batch (C3819) fires its scripts here too, named: *claimed* the row it claimed before
    turning self-healing on (`claim_for_batch`; no second claim is taken), *batch* its
    approval (``{"id", "by", "by_shown", "hash"}``: guard 6 resolved for this run, the batch
    named on the run's reason and authority) and *expect_hash* the plan hash the person
    approved: a plan whose hash moved since is refused, naming both, with nothing sent.

    *retry*: the retry pass's key (`modules/heal/retry.py`, through the decision's
    `fire_matching`): a run of it that sent and failed before is tried once more for that
    retry, never twice (`_stands`)."""
    from modules.nsot import command_plan as CP
    from modules.nsot import command_plan_run as CR

    e = scripts(network).get(key)
    if not e:
        if claimed is not None:
            release(key, claimed.get("id") or "", f"not run: {key} is no longer a script here")
        raise Refused(f"{key} is no self-heal script of {network}")
    mode = "dry_run" if force_dry and mode_now(e, heal_mode) != "off" else mode_now(e, heal_mode)
    if claimed is not None and mode != claimed.get("mode"):
        words = (f"not run: the batch claimed its {claimed.get('mode')} run, and self-healing "
                 f"allows {mode} now; nothing was sent")
        release(key, claimed.get("id") or "", words)
        return {"mode": mode, "ok": False, "sent": False, "hash": "", "values": {}, "run": "",
                "words": words, "state": "done"}
    if mode == "off":
        return {"mode": "off", "ok": False, "sent": False, "hash": "", "values": {}, "run": "",
                "words": "self-healing is off on this network: nothing fired"}
    if claimed is not None:
        row = claimed
    else:
        row, before = _claim(key, incident, mode, retry)
        if before is not None:
            return dict(before, already=True)
    out = {"mode": mode, "ok": False, "sent": False, "hash": "", "values": {}, "run": ""}
    try:
        values = fill(e, problem)
    except Refused as exc:
        return dict(out, **_settle(key, row["id"], words=f"refused: {exc}"))
    p = CP.preview(network, key, values, sources=sources)
    out.update(ok=bool(p["ok"]), hash=p["hash"], values=p["values"],
               words=("would run" if p["ok"] else "would be refused: "
                      + "; ".join(p["refusals"])))
    if p["ok"] and expect_hash and p["hash"] != expect_hash:
        out.update(ok=False, words=(f"its plan moved since the batch was previewed (approved "
                                    f"{expect_hash[:12]}, now {p['hash'][:12]}); nothing was "
                                    "sent"))
    elif mode == "auto" and p["ok"]:
        from modules.heal import decide
        held = decide.script_hold(network, record or {"id": incident,
                                                     "device": values.get("device")},
                                  batch=bool(batch))
        if held:
            out.update(ok=False, words=(f"held by guard {held['guard']} ({held['name']}): "
                                        f"{held['words']}; nothing was sent"))
        else:
            rec = _run_as_job(network, e, values, p["hash"], incident, batch=batch)
            out.update(run=rec.get("id") or "", ok=rec.get("state") == "done",
                       sent=rec.get("outcome") != "refused",
                       words=CR.OUTCOME_WORDS.get(rec.get("outcome") or "", "")
                       or str(rec.get("why") or ""))
            if out["ok"]:
                # Every verified script run closes its incident Fixed, whichever path fired it
                # (the heal decision, a re-decide): one close (the operator, 2026-11-16).
                close_fixed(network, incident, {"id": out["run"],
                                                "device": values.get("device")},
                            e, e.get("promoted_by") or "")
    _settle(key, row["id"], ok=out["ok"], sent=out["sent"], hash=out["hash"],
            run=out["run"], words=out["words"][:300])
    return dict(out, state="done")


def heal_mode(network: str) -> str:
    """Self-healing's mode on *network* now (`heal.policy.current`): ``off``, ``dry_run`` or
    ``auto``; ``off`` when it cannot be read (nothing fires on an unread policy)."""
    try:
        from modules.heal import policy
        return str(policy.current(network).get("mode") or "off")
    except Exception as exc:                          # noqa: BLE001 (said; nothing fires)
        log.error("saved plans: %s's self-healing mode could not be read: %s", network, exc)
        return "off"


def script_for(network: str, found: dict) -> tuple:
    """``(entry, problem)``: the first Automatic script whose match the incident *found*'s
    classified problem holds, else ``(None, None)`` (C3805)."""
    from modules import problem as P

    prob = P.classify(found)
    if not prob.condition:
        return None, None
    hit = sorted((e for e in scripts(network).values()
                  if e.get("mode") == "auto" and matches(e.get("match") or {}, prob)),
                 key=lambda e: e.get("key") or "")
    return (hit[0], prob) if hit else (None, None)


def script_preview(network: str, found: dict) -> dict:
    """The incident *found*'s matching Automatic script (`script_for`) and its plan as `fire`
    would preview it (`fill`, then the runner's own preview, `command_plan.preview`, asking no
    device), without claiming or firing anything: ``{"key", "name", "hash", "values",
    "program", "title", "problem"}``, *program* and *title* masked (the preview's ``drawn``),
    *problem* the classified problem as `fire` takes it; ``{}`` when none matches or its
    preview is refused. A read (G6's batch, C3819; the incident's offer, `script_offer`)."""
    e, prob = script_for(network, found)
    return _previewed(network, e, prob) if e else {}


def _previewed(network: str, e: dict, prob) -> dict:
    """The fix *e* filled from the classified problem *prob* (`fill`) and previewed by the
    runner's own preview (`command_plan.preview`, asking no device): `script_preview`'s
    answer, with ``mode`` and ``how``; ``{}`` when its map does not name a value or its
    preview is refused. A read."""
    from modules.nsot import command_plan as CP

    try:
        values = fill(e, prob)
    except Refused:
        return {}
    p = CP.preview(network, e["key"], values)
    if not p["ok"]:
        return {}
    d = p.get("drawn") or {}
    return {"key": e["key"], "name": e.get("name") or e["key"], "hash": p["hash"],
            "values": p["values"], "program": list(d.get("program") or []),
            "title": d.get("title") or "", "problem": prob.as_dict(),
            "mode": e.get("mode") or "", "how": how_of(e)}


#: What an incident's offer of one fix carries (`fix_offers`).
OFFER_FIELDS = ("key", "name", "hash", "values", "mode", "how")


def fix_offers(network: str, found: dict) -> list:
    """Every fix of *network* whose match the incident *found*'s classified problem holds
    (C3849, the operator, 2026-11-16: "any matching fix is offered as a button"), Automatic
    ones first, then by key, each filled and previewed by the runner's own preview (no device;
    `_previewed`): ``[{"key", "name", "hash", "values", "mode", "how"}]``; one whose preview is
    refused is left out. Each is run once by the person who presses it
    (`routes/fixit_v2.fix_with_script`); an Automatic one also runs by itself (`fire_matching`).
    A read."""
    from modules import problem as P

    prob = P.classify(found)
    if not prob.condition:
        return []
    hit = sorted((e for e in scripts(network).values() if matches(e.get("match") or {}, prob)),
                 key=lambda e: (e.get("mode") != "auto", e.get("key") or ""))
    out = []
    for e in hit:
        got = _previewed(network, e, prob)
        if got:
            out.append({k: got[k] for k in OFFER_FIELDS})
    return out


def script_offer(network: str, found: dict) -> dict:
    """The incident's first offered fix (`fix_offers`: an Automatic one first), its "Fix with
    saved script: <name>" (C3805), or ``{}`` when none matches or every preview is refused. A
    read."""
    got = fix_offers(network, found)
    return got[0] if got else {}


def standing_fire(network: str, key: str, incident: str, mode: str = "auto") -> dict:
    """The track row of *key* standing for *mode*'s fire on *incident* now (`_stands`: in
    flight, or one that sent anything), or ``{}``: a fire on it would answer that row and run
    nothing. A read."""
    e = scripts(network).get(key) or {}
    return next((dict(r) for r in reversed(e.get("track") or []) if _stands(r, incident, mode)),
                {})


def claim_for_batch(key: str, incident: str) -> tuple:
    """G6's batch claims its Auto fire of *key* on *incident* before it turns self-healing on
    (C3819): `_claim`'s ``(row, None)``, or ``(None, row)`` the row already standing. Taken
    under the store's lock across processes, so the retry a turn-on starts
    (`heal.retry.run_soon`), the heal decision's `fire_matching` and any other worker answer the
    batch's ``firing`` row and run nothing; the batch fires it later with ``claimed=``."""
    return _claim(key, incident, "auto")


def release(key: str, row_id: str, words: str) -> dict:
    """The batch's claimed row *row_id* of *key* given back, unrun (its first device did not
    heal, or self-healing was not turned on): finished with nothing sent, so it stands for
    nothing (`_stands`) and a later fire may run. Only a row still ``firing`` that sent
    nothing is released; any other is left as it is (never a sent run made re-runnable)."""
    def change(doc):
        e = doc["plans"].get(key) or {}
        for row in e.get("track") or []:
            if (row.get("id") == row_id and row.get("state") == "firing"
                    and not row.get("sent")):
                row.update(state="done", ok=False, sent=False, words=str(words)[:300])
                return dict(row)
        return {}
    return _update(change)


def close_fixed(network: str, incident_id: str, run: dict, e: dict, by: str) -> dict:
    """Close *incident_id* as Fixed by the script *e*'s verified *run* (``{"id", "device"}``)
    through the one close path (`decide.end_standing`, the close keeping ``fixed``); ``{}``
    when it is not standing (the detect pass ends it then)."""
    from modules.heal import decide

    now = time.time()
    hhmm = time.strftime("%H:%M", time.gmtime(now))
    rid = str(run.get("id") or "")
    return decide.end_standing(
        network, incident_id,
        (f"fixed: saved script {e.get('name')}'s run {rid[-8:]} verified on "
         f"{run.get('device') or '?'} at {hhmm} UTC"), now=now, by=by,
        read_words=f"the script's run {rid} read the device back and verified",
        fixed={"run": rid, "device": run.get("device") or "", "at": _iso(),
               "script": e.get("key") or "", "name": e.get("name") or ""})


#: What a script's run is doing now, by its newest finished step (`command_plan_run.STEPS`).
NOW_DOING = {"approve": "holding the device", "hold": "checking preconditions",
             "read_before": "checking preconditions", "preconditions": "sending",
             "send": "verifying", "verify": "recording", "rollback": "recording"}
#: A script run's job (`capture_job`), so In progress, the row and the card see it running.
JOB_KIND = "saved script"


def actor_words(e: dict) -> str:
    """Who a script's automatic run is by, everywhere it is said (the operator, 2026-11-15)."""
    from modules import display_names
    by = e.get("promoted_by") or e.get("saved_by") or ""
    return (f"Self-healing, saved script {e.get('name')}"
            + (f" (approved by {display_names.people(by)} at save)" if by else ""))


def running_on(network: str, incident_id: str) -> dict:
    """The saved script's run on *incident_id* still running in this process (its job's page is
    the incident's), ``{"job", "step"}`` with what it is doing now, or ``{}``. A read."""
    from modules import op_progress
    from modules.nsot import capture_job

    for j in capture_job.card_jobs():
        if (j["kind"] == JOB_KIND and j["state"] == "running" and j["list"] == network
                and f"/v2/incident/{incident_id}?" in (j.get("page") or "")):
            own = op_progress.run_of(j["job"]) or {}
            done = [s.get("step") for s in own.get("steps") or []]
            return {"job": j["job"],
                    "step": NOW_DOING.get(done[-1], "starting") if done else "starting"}
    return {}


# A save, a promote and self-healing switched on try each open incident's failed fixes again
# through the retry pass (`modules/heal/retry.py`, the operator, 2026-11-16), its one home: it
# sends the incident back for a fresh decision, and the decision fires its matching scripts
# (`fire_matching` with the retry's key). It replaced C3805's `redecide`.


def _run_as_job(network: str, e: dict, values: dict, confirmed: str, incident: str, *,
                batch: dict = None) -> dict:
    """A script's automatic run (the runner) as a job of its own, waited for: In progress, the
    row and the card see it running (`running_on`), its actor Mercury's (`actor_words`),
    whichever path fired it. *batch*, G6's approval that fired it (C3819), is named on the
    run's reason and authority. The run's record, or ``{}`` when the job ended without one."""
    from urllib.parse import quote

    from modules.nsot import capture_job
    from modules.nsot import command_plan_run as CR

    out = {}
    reason = f"self-heal script {e['name']}, promoted by {e.get('promoted_by')}"
    authority = {"script": e["key"]}
    if batch and batch.get("named"):
        # C3823: a switch-on's batch is named after the switch-on.
        reason += (f"; run by {batch['named']} (the batch {batch.get('id')}, approved by its "
                   f"hash {str(batch.get('hash') or '')[:12]})")
    elif batch:
        reason += (f"; run by the batch {batch.get('id')}, approved by "
                   f"{batch.get('by_shown') or batch.get('by')} by its hash "
                   f"{str(batch.get('hash') or '')[:12]}")
        authority["batch"] = batch.get("id") or ""

    def work(_job):
        out.update(CR.run(network, e["key"], values, actor=e.get("promoted_by") or "",
                          actor_verified="", person=False, confirmed=confirmed,
                          incident=incident, reason=reason, authority=authority))
        return {"state": out.get("state"), "words": out.get("why") or ""}
    job = capture_job.start(network, actor_words(e), e.get("promoted_by") or "", work,
                            kind=JOB_KIND, actor_kind="policy",
                            page=f"/v2/incident/{incident}?list={quote(network)}")
    capture_job.wait(job, 900)
    return out


def fire_matching(network: str, found: dict, *, sources=None, mode: str = None,
                  retry: str = "") -> list:
    """Every script of *network* whose match the incident *found* (`incident_page.resolve`)
    holds, fired (`fire`) under self-healing's mode now (*mode*, else `heal_mode`), Auto ones
    first; one already standing on the incident (`_claim`) answers what it did then, so the
    heal decision and the investigation never fire one twice. Once one Auto script has sent
    anything, the rest only record a Dry run: one incident, one change. *retry*: the retry
    pass's key, each script fired once for it (`fire`). Its answers, in order."""
    from modules import problem as P

    prob = P.classify(found)
    if not prob.condition:
        return []
    record = found.get("incident") if isinstance(found.get("incident"), dict) else {}
    iid = str(record.get("id") or found.get("id") or "")
    hit = [e for e in scripts(network).values() if matches(e.get("match") or {}, prob)]
    if not hit:
        return []
    mode = heal_mode(network) if mode is None else mode
    out, sent = [], False
    for e in sorted(hit, key=lambda x: (x.get("mode") != "auto", x.get("key"))):
        try:
            got = fire(network, e["key"], prob, iid, sources=sources, heal_mode=mode,
                       record=record or None, force_dry=sent, retry=retry)
            sent = sent or bool(got.get("sent")) or (got.get("already") and got.get("mode")
                                                     == "auto" and got.get("state") == "firing")
            out.append(dict(got, key=e["key"]))
        except Exception as exc:                      # noqa: BLE001 (said; the next is tried)
            log.error("saved plans: %s did not fire on %s: %s", e["key"], iid, exc)
            out.append({"key": e["key"], "mode": e.get("mode"), "ok": False,
                        "words": f"{type(exc).__name__}: {exc}"})
    return out


# ── A device's interface view: the saved actions an interface fills ────────────────────────

def interface_actions(network: str = None) -> dict:
    """The saved fixes of the catalog (`actions`: *network*'s own and the shared ones, or every
    one) whose parameters a device's interface fills alone: exactly a device and an interface
    (``Bounce interface``), by key, each read as a fix. One that takes anything else (a choice)
    is offered where that is known (an incident), not here."""
    every = templates()
    out = {}
    for key, e in actions(network).items():
        t = every.get(key)
        if t and sorted((n, s.get("type")) for n, s in t.parameters.items()) == [
                ("device", "device"), ("interface", "interface")]:
            out[key] = e
    return out


def device_offer(network: str, device: str, *, actor: str, actor_verified: str,
                 person: bool) -> dict:
    """What *device*'s page offers of the saved actions: ``{"actions": [{"key", "name",
    "words"}], "interfaces": [names], "right", "why"}``, the interfaces from its committed
    intent, *right* the viewer's (`identity.right_refusal`, running a plan), *why* when there
    is nothing to offer. A read."""
    from modules import identity
    from modules.nsot import hostvars, listref

    acts = interface_actions(network)
    out = {"actions": [{"key": k, "name": e.get("name") or k,
                        "words": (e.get("template") or {}).get("words") or ""}
                       for k, e in sorted(acts.items())],
           "interfaces": [], "why": "",
           "right": identity.right_refusal("run_plan", actor=actor,
                                           actor_verified=actor_verified, person=person)}
    if not acts:
        return dict(out, why="no saved action acts on one interface")
    doc = hostvars.read_committed(listref.resolve(network).repo_dir, device)
    names = [str(i.get("name")) for i in (doc or {}).get("interfaces") or []
             if isinstance(i, dict) and i.get("name")]
    if not names:
        return dict(out, why=f"{device} has no interface in its committed intent")
    return dict(out, interfaces=names)


# ── What the incident card offers (templates/v2/_saved_plans_saves.html) ────────────────────

#: The match fields a person may keep or leave out at Save (the condition is always kept).
OPTIONAL_MATCH = ("cause", "port_role", "cleared")


def default_fills(t, problem, values: dict) -> dict:
    """A script's fills offered for plan *t* from the run's *values* and the incident's
    *problem*: the device from the problem's device, an interface from its object, a choice
    through a map from the problem's field of its name (else its cause) to the value the run
    took, and anything else from the field of its name. A person sees them before saving."""
    from modules import problem as P

    got = problem.as_dict() if hasattr(problem, "as_dict") else dict(problem or {})
    out = {}
    for name, spec in t.parameters.items():
        if spec.get("type") == "device":
            out[name] = "device"
        elif spec.get("type") == "interface":
            out[name] = "object"
        elif spec.get("type") == "choice":
            field = name if name in P.FIELDS else "cause"
            fill_ = {str(got.get(field) or ""): str(values.get(name) or "")}
            out[name] = fill_ if field == name else {"from": field, "map": fill_}
        else:
            out[name] = name
    return out


def offer(network: str, incident_id: str, *, actor: str, actor_verified: str,
          person: bool) -> dict:
    """What the incident's card offers to save and promote, read from records only:
    ``{"state", "why", "run", "plan", "problem", "match", "optional", "fills", "preview",
    "rights", "scripts", "actions"}``. *state* ``ready`` when the incident's newest command-plan
    attempt passed its own verify (its *run*), else ``none`` with why. *rights* the viewer's,
    ``{"script", "action"}``, each ``""`` or the refusal (`identity.right_refusal`); *scripts*
    the network's scripts whose match the problem holds (each Promote's), *actions* the saved
    reusable actions, *unset* the rights `access_rights` names no one for (every verified
    person holds each, and the card says so), *saved* what is saved from the run already
    (`saved_from`), *name* the name Save gives it by default (`default_name`) and *dismissed*
    whether Not now put the offer off (`put_off`). A read."""
    from modules import identity, incident_page
    from modules import problem as P
    from modules.fixit import incident as F
    from modules.fixit import section
    from modules.heal import catalog
    from modules.nsot import command_plan as CP
    from modules.nsot import privileged

    who = dict(actor=actor, actor_verified=actor_verified, person=person)
    out = {"state": "none", "why": "", "run": "", "plan": "", "problem": {}, "match": {},
           "optional": list(OPTIONAL_MATCH), "fills": {}, "preview": {}, "scripts": [],
           "rights": {"script": identity.right_refusal("self_healing", **who),
                      "action": identity.right_refusal("admin", **who)},
           "unset": identity.rights_unset(), "actions": sorted(actions(network)),
           "saved": {"script": None, "action": None}, "name": "", "dismissed": None}
    found = incident_page.resolve(network, incident_id)
    if found.get("found") != "page":
        return dict(out, why=f"{incident_id} has no page")
    prob = P.classify(found)
    out["problem"] = prob.as_dict()
    out["scripts"] = [{"key": k, "name": e.get("name"), "mode": e.get("mode"),
                       "promoted_by": e.get("promoted_by") or "",
                       "fired": len(e.get("track") or []), "match": e.get("match") or {}}
                      for k, e in sorted(scripts(network).items())
                      if prob.condition and matches(e.get("match") or {}, prob)]
    inc = section.incident_of(network, found).get("incident")
    if inc is None:
        return dict(out, why=f"{incident_id}'s record could not be read")
    tried = [a for a in F.attempts(inc).get("attempts") or []
             if catalog.is_command_plan(a.get("operation")) and a.get("passed")]
    if not tried:
        return dict(out, why="no command plan ran and passed its own verify on this incident")
    run_id = tried[-1]["run"]
    rec = privileged.get(network, run_id) or {}
    try:
        t = CP.template_of(rec.get("key"))
    except CP.Refused as exc:
        return dict(out, why=str(exc))
    match = {"condition": prob.condition, **{k: str(getattr(prob, k) or "")
                                             for k in OPTIONAL_MATCH if getattr(prob, k, "")}}
    out.update(state="ready", run=run_id, plan=rec.get("title") or t.title, match=match,
               fills=default_fills(t, prob, rec.get("params") or {}),
               preview=match_preview(network, match), saved=saved_from(network, run_id),
               name=default_name(prob, rec.get("title") or t.title),
               dismissed=put_off(inc))
    return out


def default_name(problem, plan_title: str) -> str:
    """The name Save gives a script by default (board R5's screen 5: "the name from the
    problem"): the cause's recovery, on the port role it matched ("BPDU guard recovery (access
    ports)"), else the plan's own title. At most 120 characters, as a saved name is kept."""
    cause = str(getattr(problem, "cause", "") or "").strip()
    role = str(getattr(problem, "port_role", "") or "").strip()
    name = (f"{cause} recovery" + (f" ({role} ports)" if role else "")) if cause else \
        str(plan_title or "Saved fix")
    return name[:120]


def put_off(incident) -> dict:
    """Whether the offer to save *incident*'s verified fix was put off (Not now, board R5's
    screen 5): its troubleshooting record's newest save choice ``dont_save``, ``{"by", "at"}``,
    or None (none, a later choice, or a record that cannot be read). A read."""
    from modules.fixit import incident as F

    try:
        lines = F.read(incident).get("lines") or []
    except Exception:                                   # noqa: BLE001 (offered as before)
        return None
    saves = [ln for ln in lines if ln.get("choice") == "save"]
    if not saves or saves[-1].get("saved") != "dont_save":
        return None
    return {"by": saves[-1].get("by") or "", "at": saves[-1].get("at") or ""}


def saved_from(network: str, run_id: str) -> dict:
    """What is saved from *network*'s run *run_id* (item 7, the operator, 2026-11-15: every
    save shows its result in place, and its form collapses): ``{"script", "action"}``, each
    ``{"key", "name", "mode"}`` of the newest fix its ``from_run`` names, or None: *script*
    one with a match, *action* one the catalog lists. One fix saved since C3849 is both, so
    it answers both. Read from the store, so a redraw after the save's
    announcement draws the same result. A read."""
    got = sorted((f for f in fixes().values() if f["network"] == network
                  and (f.get("from_run") or {}).get("run") == run_id),
                 key=lambda f: str(f.get("saved_at") or ""))

    def newest(role):
        hit = [f for f in got if role(f)]
        return ({"key": hit[-1]["key"], "name": hit[-1].get("name") or hit[-1]["key"],
                 "mode": hit[-1].get("mode") or ""} if hit else None)
    return {"script": newest(lambda f: bool(f["match"])),
            "action": newest(lambda f: f["catalog"])}
