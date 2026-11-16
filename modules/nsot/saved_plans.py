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

**Who** (`identity.right_refusal`, the one chokepoint): saving or promoting a script needs the
self-healing right, saving an action the admin right; the AI proposes either and approves
neither. The store is the installation's (`STORE`), locked and replaced atomically.
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
KINDS = ("script", "action")
MODES = ("dry_run", "auto")
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


def actions() -> dict:
    """The saved reusable actions, by key, each its entry."""
    return {k: e for k, e in (read().get("plans") or {}).items() if e.get("kind") == "action"}


def scripts(network: str) -> dict:
    """*network*'s self-heal scripts, by key."""
    return {k: e for k, e in (read().get("plans") or {}).items()
            if e.get("kind") == "script" and e.get("network") == network}


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


def _store(entry: dict) -> dict:
    def change(doc):
        if entry["key"] in doc["plans"]:
            raise Refused(f"a plan {entry['key']} is saved already")
        from modules.nsot import command_plan as CP
        if entry["key"] in CP.builtin():
            raise Refused(f"{entry['key']} is the key of a plan that ships with Mercury")
        doc["plans"][entry["key"]] = entry
        return entry
    return _update(change)


def save_script(network: str, *, run_id: str, name: str, match: dict, fills: dict,
                actor: str, actor_verified: str, person: bool, dry_run: bool = False) -> dict:
    """Save the verified run *run_id* as a self-heal script of *network*: its plan with its
    parameters open, *match* (`match_refusal`) and *fills* (`fills_refusal`). Saved in Auto,
    promoted by the person saving it: saving a verified fix is the approval (the operator,
    2026-11-15); *dry_run* keeps it in Dry run until promoted. The network's self-healing mode
    still governs whether it acts (`mode_now`). Needs the self-healing right. Raises
    `Refused`, nothing saved."""
    from modules import identity
    from modules.nsot import command_plan as CP

    why = identity.right_refusal("self_healing", actor=actor, actor_verified=actor_verified,
                                 person=person)
    if why:
        raise Refused(why)
    why = match_refusal(match)
    if why:
        raise Refused(why)
    rec = _verified_run(network, run_id)
    key = _key("script", name)
    doc = _template_doc(rec, key, name, "")
    why = fills_refusal(CP.parse(doc), fills)
    if why:
        raise Refused(why)
    e = {"key": key, "kind": "script", "network": network, "name": name[:120],
         "template": doc, "match": dict(match), "fills": dict(fills),
         "mode": "dry_run", "saved_by": actor, "saved_at": _iso(),
         "from_run": {"run": run_id, "plan": rec.get("key"), "at": rec.get("at"),
                      "by": rec.get("actor")}, "track": []}
    if not dry_run:
        # As `promote` binds it: the person, when, and the plan's digest.
        e.update(mode="auto", promoted_by=actor, promoted_at=_iso(),
                 digest=CP.parse(doc).digest)
    return _store(e)


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
        if not e or e.get("kind") != "script":
            raise Refused(f"{key} is no saved self-heal script")
        if network and e.get("network") != network:
            raise Refused(f"{key} is a self-heal script of {e.get('network')}, not of {network}")
        if e.get("mode") == "auto":
            raise Refused(f"{key} is in Auto already, promoted by {e.get('promoted_by')}")
        e.update(mode="auto", promoted_by=actor, promoted_at=_iso(),
                 digest=CP.parse(e["template"]).digest)
        return e
    return _update(change)


def save_action(network: str, *, run_id: str, name: str, words: str, actor: str,
                actor_verified: str, person: bool) -> dict:
    """Save the verified run *run_id* as a reusable action: its plan, named *name* and said in
    *words*, its parameters open, the catalog's from now (`heal.catalog.entries`). Needs the
    admin right. Raises `Refused`."""
    from modules import identity

    why = identity.right_refusal("admin", actor=actor, actor_verified=actor_verified,
                                 person=person)
    if why:
        raise Refused(why)
    rec = _verified_run(network, run_id)
    key = _key("action", name)
    doc = _template_doc(rec, key, name, words)
    entry = _store({"key": key, "kind": "action", "name": name[:120], "template": doc,
                    "saved_by": actor, "saved_at": _iso(),
                    "from_run": {"network": network, "run": run_id, "plan": rec.get("key"),
                                 "at": rec.get("at"), "by": rec.get("actor")}})
    # Registered at once in this process: the catalog's entry and the plan step.
    from modules import plan_engine
    plan_engine.refresh_saved_kinds()
    return entry


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
    if e.get("kind") != "script" or e.get("mode") != "auto":
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


def _stands(row: dict, incident: str, mode: str) -> bool:
    """Whether a track *row* stands for *mode*'s fire on *incident*: a Dry run's record, or an
    Auto run in flight (``firing``) or one that sent anything (``sent``), passed or not, so a
    rolled-back or refused-at-the-device run is never tried again on every pass. A row held by
    a guard sent nothing, and stands for nothing."""
    if row.get("incident") != incident or row.get("mode") != mode:
        return False
    return mode == "dry_run" or row.get("state") == "firing" or bool(row.get("sent"))


def _claim(key: str, incident: str, mode: str):
    """``(row, None)``: a ``firing`` row of *key* on *incident* in *mode*, written under the
    store's lock before anything runs, its ``id`` the one `_settle` finishes; or ``(None,
    row)``, the row already standing for it (`_stands`): the heal decision and the
    investigation never both run one, and neither runs while the other's is in flight."""
    import uuid

    def change(doc):
        e = doc["plans"].get(key)
        if e is None:
            raise Refused(f"{key} is no saved script")
        for row in reversed(e.get("track") or []):
            if _stands(row, incident, mode):
                return None, dict(row)
        row = {"id": uuid.uuid4().hex, "at": _iso(), "incident": incident, "mode": mode,
               "state": "firing", "sent": False, "ok": False, "hash": "", "run": "",
               "words": "firing"}
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
         heal_mode: str = "auto", record: dict = None, force_dry: bool = False) -> dict:
    """Script *key* fired on *problem* in *incident*, in the mode self-healing allows it now
    (`mode_now`; Dry run when *force_dry*, another script having sent already), claimed first
    (`_claim`: one standing fire per incident and mode): its values filled from the problem
    (`fill`, a value its map does not name refused by name) and the plan previewed by the
    runner's own preview (asking no device). In Dry run, what it would run is recorded and
    nothing is sent; in Auto, the heal guards for its device are asked first (`decide.
    script_hold`, on the incident's *record*): one holding it sends nothing and the row says
    which; else the plan runs through the runner (`command_plan_run.run`) on the promotion's
    authority. No AI call either way. ``{"mode", "ok", "sent", "words", "hash", "values",
    "run", "already", "state"}``."""
    from modules.nsot import command_plan as CP
    from modules.nsot import command_plan_run as CR

    e = scripts(network).get(key)
    if not e:
        raise Refused(f"{key} is no self-heal script of {network}")
    mode = "dry_run" if force_dry and mode_now(e, heal_mode) != "off" else mode_now(e, heal_mode)
    if mode == "off":
        return {"mode": "off", "ok": False, "sent": False, "hash": "", "values": {}, "run": "",
                "words": "self-healing is off on this network: nothing fired"}
    row, before = _claim(key, incident, mode)
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
    if mode == "auto" and p["ok"]:
        from modules.heal import decide
        held = decide.script_hold(network, record or {"id": incident,
                                                     "device": values.get("device")})
        if held:
            out.update(ok=False, words=(f"held by guard {held['guard']} ({held['name']}): "
                                        f"{held['words']}; nothing was sent"))
        else:
            rec = CR.run(network, key, values, actor=e.get("promoted_by") or "",
                         actor_verified="", person=False, confirmed=p["hash"],
                         incident=incident, reason=(f"self-heal script {e['name']}, promoted "
                                                    f"by {e.get('promoted_by')}"),
                         authority={"script": key})
            out.update(run=rec.get("id") or "", ok=rec.get("state") == "done",
                       sent=rec.get("outcome") != "refused",
                       words=CR.OUTCOME_WORDS.get(rec.get("outcome") or "", "")
                       or str(rec.get("why") or ""))
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


def fire_matching(network: str, found: dict, *, sources=None, mode: str = None) -> list:
    """Every script of *network* whose match the incident *found* (`incident_page.resolve`)
    holds, fired (`fire`) under self-healing's mode now (*mode*, else `heal_mode`), Auto ones
    first; one already standing on the incident (`_claim`) answers what it did then, so the
    heal decision and the investigation never fire one twice. Once one Auto script has sent
    anything, the rest only record a Dry run: one incident, one change. Its answers, in
    order."""
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
                       record=record or None, force_dry=sent)
            sent = sent or bool(got.get("sent")) or (got.get("already") and got.get("mode")
                                                     == "auto" and got.get("state") == "firing")
            out.append(dict(got, key=e["key"]))
        except Exception as exc:                      # noqa: BLE001 (said; the next is tried)
            log.error("saved plans: %s did not fire on %s: %s", e["key"], iid, exc)
            out.append({"key": e["key"], "mode": e.get("mode"), "ok": False,
                        "words": f"{type(exc).__name__}: {exc}"})
    return out


# ── A device's interface view: the saved actions an interface fills ────────────────────────

def interface_actions() -> dict:
    """The saved reusable actions whose parameters a device's interface fills alone: exactly a
    device and an interface (``Bounce interface``), by key, each its entry. An action that
    takes anything else (a choice) is offered where that is known (an incident), not here."""
    every = templates()
    out = {}
    for key, e in actions().items():
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

    acts = interface_actions()
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
           "unset": identity.rights_unset(), "actions": sorted(actions()),
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
    ``{"key", "name", "mode"}`` of the newest entry its ``from_run`` names, or None. Read from
    the store, so a redraw after the save's announcement draws the same result. A read."""
    def newest(entries):
        got = [e for e in entries if (e.get("from_run") or {}).get("run") == run_id]
        got.sort(key=lambda e: str(e.get("saved_at") or ""))
        return ({"key": got[-1]["key"], "name": got[-1].get("name") or got[-1]["key"],
                 "mode": got[-1].get("mode") or ""} if got else None)
    return {"script": newest(scripts(network).values()),
            "action": newest(e for e in actions().values()
                             if (e.get("from_run") or {}).get("network") == network)}
