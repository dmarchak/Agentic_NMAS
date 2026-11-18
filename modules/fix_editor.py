"""modules/fix_editor.py — New fix… on Troubleshooting › Fixes and Edit… in a fix's Contents
fold (board docs/boards/fix-manual-controls.html, screens 2 and 3, approved by the operator
2026-11-16 with two corrections), the model `routes/fixes_v2.py` draws with
`templates/v2/_fix_form.html`.

**Every choice comes from Mercury, never free text but the name, the description and a
provisional line** (`options`):

- *What it fixes*: the classified problem's match fields (`problem.MATCH_FIELDS`): the
  condition one of `problem.CONDITIONS`; the cause one Mercury classifies (an err-disabled
  port's, `heal.errdisable.CAUSES`, and every cause the network's incidents hold); the port role
  one Mercury classifies (an err-disabled port's switchport mode, and every role its incidents
  hold); and whether the cause has cleared.
- *Lines*: the shapes Mercury's rule for raw lines offers because they keep the fix net-zero
  (`command_policy.offered`, the operator's correction 1), and another shape typed as
  provisional, held for an admin's approval when the fix is saved (the fix cannot run until
  then). A line that would last is refused in the operator's words
  (`command_policy.lasting_refusal`) before anything is saved.
- *Checks before* and *Verifies after*: each check an existing command plan holds, built in or
  saved (its read named), so only the checks Mercury has are offered; a check that reads a
  choice (an err-disabled port's cause) brings that parameter, as its own plan declares it.

**The template** (`build`) is a command plan (`command_plan.parse`, ``net_zero: true``), its
parameters the device, ``{interface}`` when a line or check names it, and each choice a check
takes; its fills, with a match, from the problem's fields (`saved_plans.fills_refusal`). An
edit whose lines, checks and verify are as they were keeps the fix's own template byte for
byte (the same version: `saved_plans.template_changed`).

**The preview** is the runner's own (`command_plan.preview`, asking no device), of the draft
exactly as Save would store it (`saved_plans.previewing`), on an example: an open incident the
draft matches, else the newest closed one it matches, else a device and port chosen from
committed intent. Reads only: nothing is written, no network is created, no device is asked.
"""

import hashlib
import json
import logging

log = logging.getLogger(__name__)

#: A line select's value for "Another shape (provisional)…".
OTHER = "__other__"
#: Lines and checks a draft holds at most (`command_plan.MOST`'s, the template's own bounds).
MOST_LINES = 20


def _item_id(item: dict) -> str:
    return hashlib.sha256(json.dumps(item, sort_keys=True).encode("utf-8")).hexdigest()[:10]


def _templates() -> list:
    """Every command plan Mercury holds, built in first, then saved (no draft)."""
    from modules.nsot import command_plan as CP
    from modules.nsot import saved_plans as S

    out = list(CP.builtin().values())
    out += [t for k, t in sorted(S.templates().items()) if k != S.DRAFT_KEY]
    return out


def _needs(t, raw: dict) -> dict:
    """The parameters (beyond the device) a check item of template *t* reads: each
    placeholder of its read or line, and, for one of Mercury's named checks (which may read
    any validated value), every interface and choice its plan declares. ``{name: spec}``;
    ``None`` when it needs a kind the editor's lines cannot fill (a telemetry subscription)."""
    from modules.nsot.command_plan import _PLACEHOLDER                # noqa: PLC2701

    names = set(_PLACEHOLDER.findall(str(raw.get("read") or "") + " "
                                     + str(raw.get("expect_line") or "")))
    names = {n[:-len("_short")] if n.endswith("_short") else n for n in names}
    if raw.get("expect"):
        if any(s.get("type") not in ("device", "interface", "choice")
               for s in t.parameters.values()):
            return None
        names |= {n for n, s in t.parameters.items() if s.get("type") in ("interface", "choice")}
    names.discard("device")
    out = {}
    for n in sorted(names):
        spec = t.parameters.get(n)
        if not spec or spec.get("type") not in ("interface", "choice"):
            return None
        if spec.get("type") == "interface" and n != "interface":
            return None
        out[n] = dict(spec)
    return out


def checks(own: str = "") -> dict:
    """Every check Mercury's command plans hold: ``{"pre": [item], "ver": [item]}``, each
    ``{"id", "name", "read", "raw", "needs", "from"}``, *raw* the template's own item as it
    writes it, *id* its digest, deduplicated, *from* the plan it was read from. A check whose
    parameters the editor cannot fill is left out, unless it is the edited fix *own*'s (kept,
    so an edit of its name or match keeps its template as it is). A read."""
    out = {"pre": [], "ver": []}
    seen = set()
    every = _templates()
    every.sort(key=lambda t: t.key != own)
    for t in every:
        for kind, items in (("pre", t.doc.get("preconditions") or []),
                            ("ver", t.doc.get("verify") or [])):
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                iid = _item_id(raw)
                needs = _needs(t, raw)
                if needs is None and t.key == own:
                    needs = {}
                if (kind, iid) in seen or needs is None:
                    continue
                seen.add((kind, iid))
                out[kind].append({"id": iid, "name": str(raw.get("name") or ""),
                                  "read": str(raw.get("read") or ""), "raw": dict(raw),
                                  "needs": needs, "from": t.key, "fixes": list(t.fixes),
                                  "own": t.key == own})
    return out


def _incident_problems(network: str) -> list:
    """``[(record, problem)]`` for every incident *network* keeps, closed ones included,
    newest first (`saved_plans.incident_problems`, the one reading)."""
    from modules.nsot import saved_plans as S

    return list(reversed(S.incident_problems(network, closed=True)))


def options(network: str, held=None, own: str = "") -> dict:
    """What New fix… and Edit… offer on *network* (the module docstring): ``{"conditions",
    "causes", "roles", "lines", "checks"}``; *held* the network's incidents with their
    problems (`_incident_problems`), read once; *own* the edited fix's key (`checks`). A
    read."""
    from modules import problem as P
    from modules.heal import errdisable
    from modules.nsot import command_policy

    held = _incident_problems(network) if held is None else held
    causes = set(errdisable.CAUSES.values()) | {p.cause for _r, p in held if p.cause}
    roles = {"access", "trunk"} | {p.port_role for _r, p in held if p.port_role}
    return {"conditions": [{"value": c, "words": c.replace("_", "-") + f" ({noun})"}
                           for c, (noun, _chk) in P.CONDITIONS.items()],
            "causes": sorted(causes), "roles": sorted(roles),
            "lines": command_policy.offered(network), "checks": checks(own)}


# ── A draft: from the form, or from a saved fix ─────────────────────────────────────────────

def draft_from_form(form, opts: dict) -> dict:
    """The editor's draft from its form (``name``, ``words``, the match's ``condition``,
    ``cause``, ``port_role``, ``cleared``; the lines ``l0``… with ``o0``… for a provisional
    one; the checks ``pre`` and ``ver`` by id; an example ``ex_device``, ``ex_interface``;
    ``add`` or ``remove`` pressed), reading nothing the form does not send."""
    from modules import problem as P

    g = form.get
    match = {}
    cond = (g("condition") or "").strip()
    if cond in P.CONDITIONS:
        match["condition"] = cond
        for f in ("cause", "port_role"):
            v = (g(f) or "").strip()
            if v and v in (opts["causes"] if f == "cause" else opts["roles"]):
                match[f] = v
        if g("cleared") == "1":
            match["cleared"] = "true"
    lines = []
    try:
        n = max(0, min(MOST_LINES, int(g("n") or 0)))
    except ValueError:
        n = 0
    for i in range(n):
        v = g(f"l{i}") or ""
        if v == OTHER:
            # A typed line sits under the interface unless it is a header itself.
            text = " ".join((g(f"o{i}") or "").split())
            if text and not text.startswith("interface "):
                text = " " + text
            lines.append({"other": True, "text": text})
        elif v:
            lines.append({"other": False, "text": v})
    remove = g("remove")
    if remove is not None and str(remove).isdigit() and int(remove) < len(lines):
        lines.pop(int(remove))
    if g("add") == "1" and len(lines) < MOST_LINES:
        lines.append({"other": False, "text": (opts["lines"][1]["line"]
                                               if len(opts["lines"]) > 1 else
                                               opts["lines"][0]["line"] if opts["lines"]
                                               else "")})
    ids = {"pre": {c["id"] for c in opts["checks"]["pre"]},
           "ver": {c["id"] for c in opts["checks"]["ver"]}}
    return {"name": " ".join((g("name") or "").split())[:80],
            "words": " ".join((g("words") or "").split())[:200], "match": match,
            "lines": lines,
            "pre": [i for i in form.getlist("pre") if i in ids["pre"]],
            "ver": [i for i in form.getlist("ver") if i in ids["ver"]],
            "ex_device": (g("ex_device") or "").strip()[:64],
            "ex_interface": (g("ex_interface") or "").strip()[:64]}


def first_draft(opts: dict) -> dict:
    """New fix…'s draft as it opens: the lines Mercury offers, in their order (the bounce the
    launch shapes are: a header, then each line before its negation), nothing else chosen."""
    return {"name": "", "words": "", "match": {}, "pre": [], "ver": [], "ex_device": "",
            "ex_interface": "",
            "lines": [{"other": False, "text": x["line"]} for x in opts["lines"]]}


def draft_from_fix(f: dict, t) -> dict:
    """Edit…'s draft as it opens: the saved fix *f* as it is, its template *t*'s lines,
    checks and verify (each check by its item's id)."""
    return {"name": f.get("name") or "", "words": f.get("words") or "",
            "match": dict(f.get("match") or {}),
            "lines": [{"other": False, "text": c} for c in t.commands],
            "pre": [_item_id(i) for i in t.doc.get("preconditions") or []],
            "ver": [_item_id(i) for i in t.doc.get("verify") or []],
            "ex_device": "", "ex_interface": ""}


# ── Building the template, its fills and its preview ────────────────────────────────────────

def _choice_fill(name: str, spec: dict, match: dict) -> dict:
    """A choice parameter's fill from the problem (`saved_plans.fill_of`'s map): the cause's
    words as the problem says them (`heal.errdisable.CAUSES`) to the plan's choice word, only
    the match's own cause when it names one; any other choice from the field of its name."""
    from modules import problem as P
    from modules.heal import errdisable

    of = list(spec.get("of") or [])
    words = {w: c for c, w in errdisable.CAUSES.items() if c in of}
    words.update({c: c for c in of if c not in words.values()})
    field = name if name in P.FIELDS else "cause"
    if match.get(field) in words:
        words = {match[field]: words[match[field]]}
    return {"from": field, "map": words}


def _example(network: str, draft: dict, held, t) -> dict:
    """Where the preview runs: ``{"kind": "incident"|"port"|"none", "words", "values",
    "devices", "ports", "device", "interface"}``: an open incident the match holds, else the
    newest closed one, its values filled from its problem; else a device and port chosen from
    committed intent (``ex_device``, ``ex_interface``), each choice its first."""
    from modules import fix_page
    from modules.neighbours import committed_intents_of
    from modules.nsot import ifnames
    from modules.nsot import saved_plans as S

    match = draft["match"]
    if match:
        hits = [(r, p) for r, p in held if S.matches(match, p)]
        hits.sort(key=lambda rp: rp[0].get("state") == "closed")
        for rec, prob in hits:
            try:
                values = S.fill({"fills": draft.get("fills") or {}}, prob)
            except S.Refused:
                continue
            closed = rec.get("state") == "closed"
            return {"kind": "incident", "values": values, "devices": [], "ports": [],
                    "device": values.get("device") or "", "interface": "",
                    "words": (f"{prob.device} {fix_page._short(prob.object)} "  # noqa: SLF001
                              f"({prob.cause or prob.condition.replace('_', '-')}"
                              + (", closed" if closed else ", open now") + ")"),
                    "at": (rec.get("closed_at") if closed else rec.get("opened_at")) or ""}
    intents, _err = committed_intents_of(network)
    access = bool(((t.parameters if t else {}).get("interface") or {}).get("access_port"))
    eligible = {n: [str(i["name"]) for i in fix_page._intent_ports(doc, access)]  # noqa: SLF001
                for n, doc in sorted((intents or {}).items())}
    names = [n for n, ports in eligible.items() if ports]
    if not names:
        return {"kind": "none", "values": {}, "devices": [], "ports": [], "device": "",
                "interface": "", "words": f"no device of {network} has "
                                          f"{'an access port' if access else 'an interface'} "
                                          "in its committed intent to preview on"}
    dev = draft.get("ex_device") if draft.get("ex_device") in names else names[0]
    port = next((p for p in eligible[dev] if draft.get("ex_interface")
                 and ifnames.same_interface(p, draft["ex_interface"])), eligible[dev][0])
    values = {"device": dev}
    if t is not None and "interface" in t.parameters:
        values["interface"] = port
    for n, spec in (t.parameters.items() if t else ()):
        if spec.get("type") == "choice":
            values[n] = (spec.get("of") or [""])[0]
    return {"kind": "port", "values": values, "devices": names, "ports": eligible[dev],
            "device": dev, "interface": port,
            "words": f"{dev} {fix_page._short(port)}"}                        # noqa: SLF001


def _parameters(draft_lines, items, match: dict, base: dict) -> dict:
    """The draft's parameters: the device; ``interface`` when a line or check names it (an
    access port when the match's port role is access or a check's own plan says so; never the
    management path); each choice a check needs, as its plan declares it. A parameter the
    fix's own template (*base*) declares keeps its spec."""
    from modules.nsot.command_plan import _PLACEHOLDER                # noqa: PLC2701

    out = {"device": dict((base or {}).get("device") or {
        "type": "device", "words": "one name the network's inventory holds"})}
    named = {n for ln in draft_lines for n in _PLACEHOLDER.findall(ln)}
    needs = {}
    for it in items:
        needs.update({k: v for k, v in it["needs"].items() if k not in needs})
    if "interface" in named or "interface_short" in named or "interface" in needs:
        spec = dict((base or {}).get("interface") or needs.get("interface") or {
            "type": "interface", "words": "one interface's name, as the device's committed "
                                          "intent names it: never the management path",
            "not_management": True})
        spec["not_management"] = True
        if match.get("port_role") == "access" or (needs.get("interface") or {}).get(
                "access_port"):
            spec["access_port"] = True
        out["interface"] = spec
    for n, spec in needs.items():
        if spec.get("type") == "choice":
            out[n] = dict((base or {}).get(n) or spec)
    return out


def build(network: str, draft: dict, *, fix: dict = None, held=None, opts=None) -> dict:
    """The draft as a fix's template, its fills and its preview (the module docstring):
    ``{"doc", "fills", "refusals", "notes", "lasting", "provisional", "preview", "example",
    "new_version", "version", "saveable"}``. *fix* is the saved fix Edit… opened (its own
    template kept when the lines, checks and verify are as they were). A read: nothing is
    written and no device is asked."""
    from modules.nsot import command_plan as CP
    from modules.nsot import command_policy
    from modules.nsot import saved_plans as S

    held = _incident_problems(network) if held is None else held
    opts = options(network, held) if opts is None else opts
    out = {"doc": None, "fills": {}, "refusals": [], "notes": [], "lasting": "",
           "provisional": [], "preview": None, "example": None, "new_version": False,
           "unproven": "", "drops": False, "pair": "", "pair_id": "",
           "version": 1, "saveable": False}
    base = (fix or {}).get("template") or None
    key = (fix or {}).get("key") or S.DRAFT_KEY
    if fix is None and S.key_refusal(draft["name"]):
        out["refusals"].append(S.key_refusal(draft["name"]))
    match = draft["match"]
    if not draft["name"]:
        out["refusals"].append("a fix is named in words")
    lines = [ln["text"] for ln in draft["lines"] if ln["text"].strip()]
    for ln in draft["lines"]:
        if ln["other"] and not (ln["text"].strip() and ln["text"].isascii()
                                and ln["text"].isprintable()):
            out["refusals"].append("a provisional line is printable text (a line under an "
                                   "interface begins with a space)")
    if not lines:
        out["refusals"].append("a fix sends at least one line")
    by_id = {c["id"]: c for c in opts["checks"]["pre"] + opts["checks"]["ver"]}
    pre = [by_id[i] for i in draft["pre"] if i in by_id]
    ver = [by_id[i] for i in draft["ver"] if i in by_id]
    if not ver:
        out["refusals"].append("a fix verifies at least one read after it sends")
    try:
        base_t = CP.parse(base) if base else None
    except CP.Refused:
        base_t = None
    same = bool(base_t) and (list(base_t.commands) == lines
                             and [_item_id(i) for i in base.get("preconditions") or []]
                             == draft["pre"]
                             and [_item_id(i) for i in base.get("verify") or []]
                             == draft["ver"])
    if not same and command_policy.judge(lines, network)["declared"]:
        # C1: shutdown / no shutdown is net-zero only from a port that is up, so the fix checks
        # first that it is not administratively down; added here, shown, required at save.
        raw = dict(command_policy.PAIR_PRECONDITION)
        auto = {"id": _item_id(raw), "name": raw["name"], "read": raw["read"], "raw": raw,
                "needs": {}, "from": "", "fixes": [], "own": False}
        pre = [auto] + [c for c in pre if c["id"] != auto["id"]]
        out.update(pair=command_policy.PAIR_WORDS, pair_id=auto["id"])
    if same:
        doc = dict(base)
    else:
        params = _parameters(lines, pre + ver, match, (base or {}).get("parameters"))
        title_name = draft["name"].replace("{", "(").replace("}", ")") or "A fix"
        doc = {"kind": "command_plan", "key": key,
               "title": (base or {}).get("title") or (
                   f"{title_name}: {{device}} {{interface_short}}" if "interface" in params
                   else f"{title_name}: {{device}}"),
               "words": (base or {}).get("words") or draft["words"] or draft["name"]
               or "A fix written on the Fixes page",
               "net_zero": True, "parameters": params,
               "preconditions": [c["raw"] for c in pre],
               "steps": [{"mode": "config", "commands": lines}],
               "verify": [c["raw"] for c in ver],
               "reason": (base or {}).get("reason") or (
                   f"{title_name}: sent in one batch, never saved; the configuration after "
                   "equals the one before, or it is rolled back"),
               **({"fixes": [match["condition"]]} if match.get("condition")
                  else ({"fixes": base["fixes"]} if base and base.get("fixes") else {}))}
        if base and base.get("on_finish"):
            doc["on_finish"] = base["on_finish"]
    out["doc"] = doc
    t = None
    try:
        t = CP.parse(doc) if lines and ver else None
    except CP.Refused as exc:
        out["refusals"].append(str(exc))
    if t is not None:
        if fix is not None:
            out["new_version"] = S.template_changed(base, doc)
            out["version"] = S.versions(fix)[-1]["version"] + (1 if out["new_version"] else 0)
        fills = {}
        if match:
            old = (fix or {}).get("fills") or {}
            for n, spec in t.parameters.items():
                if spec["type"] == "device":
                    fills[n] = "device"
                elif spec["type"] == "interface":
                    fills[n] = "object"
                elif n in old and (fix or {}).get("match") == match:
                    fills[n] = old[n]
                else:
                    fills[n] = _choice_fill(n, spec, match)
            why = S.fills_refusal(t, fills)
            if why:
                out["refusals"].append(why)
        out["fills"] = fills
        if fix is not None:
            # F4: what an Automatic fix's Save drops to Manual only (`saved_plans.edit_fix`).
            out["drops"] = bool(out["new_version"] or match != (fix.get("match") or {})
                                or fills != (fix.get("fills") or {}))
    draft = dict(draft, fills=out["fills"])
    ex = _example(network, draft, held, t)
    out["example"] = ex
    if t is not None:
        # Correction 1: the net-zero rule on the lines, before anything is saved, naming the
        # example's device (the runner's own net-zero compare stays the final guard). An edit
        # that keeps the fix's lines is not judged again: they are its saved version's.
        out["lasting"] = command_policy.lasting_refusal(
            t.commands, ex.get("device") or (ex.get("values") or {}).get("device") or "",
            network=network)
        if out["lasting"] and (fix is None or out["new_version"]):
            out["refusals"].append(out["lasting"])
        # A pair not known to undo itself (F3) is never called net-zero: the operator's words.
        if command_policy.judge(t.commands, network)["unproven"]:
            out["unproven"] = command_policy.UNPROVEN_WORDS
    if t is not None and ex["values"]:
        with S.previewing(key, t):
            p = CP.preview(network, key, ex["values"])
        d = p.get("drawn") or {}
        out["provisional"] = list(p.get("unknown_shapes") or [])
        # A shape not measured is held for an admin at Save (the fix cannot run until then); any
        # other refusal of the preview is the example's, said beside it, never a block on Save.
        out["preview"] = {"ok": bool(p["ok"]), "hash": p.get("hash") or "",
                          "short": (p.get("hash") or "")[:8],
                          "program": list(d.get("program") or p.get("program") or []),
                          "refusals": [r for r in p.get("refusals") or []
                                       if not any(u["words"] == r for u in out["provisional"])]}
    elif t is not None:
        out["notes"].append(ex["words"])
    out["saveable"] = t is not None and not out["refusals"]
    return out


def counts(match: dict, held) -> dict:
    """How many of the network's incidents (*held*, `_incident_problems`) *match* holds now:
    ``{"open", "closed"}``."""
    from modules.nsot import saved_plans as S

    if not match:
        return {"open": 0, "closed": 0}
    hit = [r for r, p in held if S.matches(match, p)]
    closed = sum(1 for r in hit if r.get("state") == "closed")
    return {"open": len(hit) - closed, "closed": closed}


def cleared_check(match: dict) -> str:
    """The read that says the match's cause has cleared (`problem.CONDITIONS`, or an
    err-disabled port's cause's own, `heal.errdisable.CLEARED_CHECKS`), or ``""`` when Mercury
    has none for it: "Only once Mercury reads the cause as cleared" is offered only then."""
    from modules import problem as P
    from modules.heal import errdisable

    cond = match.get("condition") or ""
    chk = (P.CONDITIONS.get(cond) or ("", ""))[1]
    if chk:
        return chk
    words = {w: c for c, w in errdisable.CAUSES.items()}
    if cond == "err_disabled" and match.get("cause") in words:
        return errdisable.CLEARED_CHECKS.get(words[match["cause"]], "")
    return ""


def card(network: str, form=None, *, fix: dict = None, who: dict) -> dict:
    """What the form draws (`templates/v2/_fix_form.html`): ``{"mode": "new"|"edit",
    "network", "key", "draft", "opts", "built", "counts", "cleared", "right", "save",
    "version", "auto"}``. *form* is the form as it sent itself (``drafted=1``), else it opens
    (`first_draft`, or the fix as it is: `draft_from_fix`); *fix* the saved fix Edit… opened
    (`saved_plans.as_fix`); *who* the viewer. *right* is the viewer's refusal
    for the right the draft's match takes (with a match the self-healing right, without the
    admin right; the AI none), and for an edit the right the fix takes now as well. A read."""
    from modules import identity
    from modules.nsot import command_plan as CP

    held = _incident_problems(network)
    opts = options(network, held, own=(fix or {}).get("key") or "")
    t = None
    if fix is not None:
        try:
            t = CP.parse(fix.get("template"))
        except CP.Refused:
            t = None
    if form is not None and form.get("drafted") == "1":
        draft = draft_from_form(form, opts)
    elif fix is not None and t is not None:
        draft = draft_from_fix(fix, t)
    else:
        draft = first_draft(opts)
    # With a condition, the checks of the plans that fix it (and the fix's own): a check for
    # another kind of problem reads what this one does not have.
    cond = draft["match"].get("condition")
    if cond:
        for kind in ("pre", "ver"):
            opts["checks"][kind] = [x for x in opts["checks"][kind]
                                    if x["own"] or cond in x["fixes"]]
            ids = {x["id"] for x in opts["checks"][kind]}
            draft[kind] = [i for i in draft[kind] if i in ids]
    built = build(network, draft, fix=fix, held=held, opts=opts)
    rights = [bool(draft["match"])] + ([bool(fix.get("match"))] if fix else [])
    right = identity.ai_acting_refusal("write or change a fix") or next(
        (w for w in (identity.right_refusal("self_healing" if m else "admin", **who)
                     for m in rights) if w), "")
    version = (fix or {}).get("version") or 1
    if fix is None:
        save = "Save as Manual only"
    elif built["new_version"]:
        save = f"Save as version {built['version']}"
    else:
        save = "Save"
    # A draft line the offered shapes do not hold is drawn as a provisional line, its text.
    offered = {x["line"] for x in opts["lines"]}
    for ln in draft["lines"]:
        if not ln["other"] and ln["text"] not in offered:
            ln["other"] = True
    return {"mode": "edit" if fix else "new", "network": network,
            "key": (fix or {}).get("key") or "", "draft": draft, "opts": opts,
            "built": built, "counts": counts(draft["match"], held),
            "cleared": cleared_check(draft["match"]), "right": right, "save": save,
            "version": version, "auto": (fix or {}).get("how") == "automatic"}


def drawn(c: dict) -> dict:
    """*c* (`card`) as `templates/v2/_fix_form.html` draws it: only what the form draws is
    carried. Save builds the template and its fills again from the form (`card`), so neither
    is; the example's device and port are drawn from ``built.example``, never from the draft,
    and its filled values not at all; the preview by its program, refusals and short hash; each
    check is drawn by its id, name and read (its own
    ``expect`` where it has no read), each line offered by its line and words, and each line
    held provisional by its words. *c* itself is left as it was."""
    if not c:
        return c
    opts = dict(c["opts"], lines=[{"line": x["line"], "words": x["words"]}
                                  for x in c["opts"]["lines"]],
                checks={kind: [{"id": x["id"], "name": x["name"], "read": x["read"],
                                "raw": {"expect": (x.get("raw") or {}).get("expect")}}
                               for x in items]
                        for kind, items in c["opts"]["checks"].items()})
    built = {k: v for k, v in c["built"].items() if k not in ("doc", "fills")}
    if built.get("preview"):
        # Drawn by its program, its refusals and its short hash (Save's title): Save builds
        # its preview again, so its whole hash and verdict are not carried.
        built["preview"] = {k: built["preview"].get(k) for k in ("program", "refusals", "short")}
    if built.get("example"):
        built["example"] = {k: v for k, v in built["example"].items() if k != "values"}
    built["provisional"] = [{"words": u.get("words") or ""} for u in built.get("provisional")
                            or []]
    draft = {k: v for k, v in c["draft"].items() if k not in ("ex_device", "ex_interface")}
    return dict(c, opts=opts, built=built, draft=draft)
