"""modules/fix_page.py — Troubleshooting › Fixes and a fix's own page (C3849 pieces 2 to 4;
boards docs/boards/fixes-list.html and docs/boards/fix-bpdu-guard.html, approved by the
operator 2026-11-16 with changes), the models `routes/fixes_v2.py` draws.

**Every fix a network has, from code and records, never typed:**

- *Saved* fixes: `saved_plans.fixes(network)` (its own and the shared ones), each read as a fix
  (`saved_plans.as_fix`), how it runs from its own match and mode (`saved_plans.how_of`).
- *Built-in* fixes, read-only: each command plan that ships with Mercury
  (`command_plan.builtin`), which runs only inside a plan a person approves by its hash; each
  self-healing fix kind (`heal_page._kinds`, the Self-healing tab's own rows), how it runs from
  the network's fix kinds and its tier as the heal decision judges them
  (`heal.decide._outcome`: Tier 1 in the fix kinds to heal runs by itself in Auto, else is a
  dry-run record; Tier 2 in the fix kinds to propose is a person's approval, else Mercury says
  it cannot fix it); and the telemetry re-subscribe and re-add (`heal.resubscribe`), a person's
  operations self-healing never starts.
- Each fix's record counts real runs: the operations' run records (`privileged.runs`, the
  newest `RUNS_READ`, said when reached), a saved fix's own track (its Dry-run records), and a
  fix kind's heal decisions (`heal.decisions`).

**A fix's page** (`page`): the BLUF (its name, what it fixes, how it runs and its record, Run…),
then Contents, Origin, Record and How it runs, each folded. A check's words come from the
template's own items, each check's read, and, where the template cannot say it, the sentence
its check's module declares beside the check (``SAYS``, e.g. `heal.errdisable.SAYS`): what it
reads and what it cannot prove on a port that is down (the operator's change 1).

**Run…** (`run_card`): a device and a port chosen from what Mercury already holds, never a
device read: for a fix with a match, the open incidents whose classified problem it matches
(their ports); for one with none, the device's access ports in committed intent, said so. The
preview is the runner's own (`command_plan.preview`, asking no device), and Run posts to the
existing run path for it (`fixit_v2.fix_with_script` on the matched incident, or
`saved_plans_v2.device_run`), whose live preconditions read the device when it runs.

Reads only: it writes nothing, creates no network and reaches no device.
"""

import importlib
import logging

log = logging.getLogger(__name__)

#: Rows a list group draws before it counts the rest (CLAUDE.md, built for large fleets).
SHOWN = 20
#: The newest run records a page reads for a record: a bound, said on the page when reached.
#: Reasoned, not measured: 200 small JSON files on the host's disk.
RUNS_READ = 200
#: Rows a fix's Record draws, newest first; the rest are on History.
RECORD_SHOWN = 10
#: How a fix runs, as its badge says it: (words, badge kind, the sentence after it).
HOW = {"automatic": ("Automatic", "ok", "runs by itself on a matching incident while "
                                        "self-healing is in Auto"),
       "matched": ("Dry run", "info", "records what it would do on a matching incident and "
                                      "changes nothing by itself"),
       "manual": ("Manual only", "muted", "runs only when a person presses Run…"),
       "off": ("Off", "warn", "self-healing raises it and says it cannot fix it")}
#: The modes a filter offers, by the badge's words.
MODES = ("automatic", "matched", "manual", "off")
#: The telemetry operations a person starts (`heal.resubscribe`): key, name, what it fixes, how.
TELEMETRY = (
    ("telemetry-resubscribe", "Re-subscribe a telemetry stream",
     "a device that stopped sending a telemetry stream Mercury subscribed it to",
     "A person starts it from the lost stream's Needs attention row, or approves, by its hash, "
     "an AI plan holding it; self-healing never runs it by itself"),
    ("telemetry-readd", "Re-add the receiver",
     "a telemetry receiver a re-subscribe did not bring back",
     "A person starts it after a re-subscribe whose receiver did not come back; self-healing "
     "never runs it by itself"),
)


def _people(text) -> str:
    from modules import display_names
    return display_names.people(text or "")


def _runs(network: str) -> tuple:
    """``(runs newest first, capped)``: the network's newest `RUNS_READ` run records, read
    without creating its list."""
    from modules import config
    from modules.nsot import privileged

    try:
        got = privileged.runs(network, limit=RUNS_READ,
                              data_dir=config.list_data_path(network))
    except (OSError, ValueError) as exc:
        log.error("fixes: %s's run records could not be read: %s", network, exc)
        return [], False
    runs = got.get("runs") or []
    return runs, len(runs) >= RUNS_READ


def _short(iface: str) -> str:
    from modules.nsot import ifnames
    return ifnames.abbreviate(ifnames.canonical(iface)) if iface else ""


def _cond_words(problem: dict) -> str:
    """A classified problem (or a match) in words: "a switch port err-disabled by BPDU guard,
    on an access port"."""
    from modules import problem as P

    cond = str(problem.get("condition") or "")
    noun = (P.CONDITIONS.get(cond) or ("something", ""))[0]
    out = f"{noun} {cond.replace('_', '-')}"
    if problem.get("cause"):
        out += f" by {problem['cause']}"
    role = str(problem.get("port_role") or "")
    if role:
        out += f", on {'an' if role[:1] in 'aeiou' else 'a'} {role} port"
    return out


def fixes_words(f: dict, t=None) -> str:
    """What a saved fix fixes, from its own match, else its template's words (their first
    clause)."""
    if f.get("match"):
        return _cond_words(f["match"])
    words = str(f.get("words") or (t.words if t is not None else "") or "")
    return words.split(":")[0].strip() or "nothing it says"


# ── The record ───────────────────────────────────────────────────────────────────────────────

def _summary(n_runs: int, verified: int, dry: int, capped: bool) -> str:
    parts = []
    if n_runs:
        parts.append(f"{n_runs} run{'s' if n_runs != 1 else ''}, "
                     + ("all verified" if verified == n_runs else
                        f"{verified} verified" if verified else "none verified"))
    if dry:
        parts.append(f"{dry} dry-run record{'s' if dry != 1 else ''}, nothing changed")
    if not parts:
        return "no run recorded" + (f" in the newest {RUNS_READ} run records" if capped else "")
    return " · ".join(parts) + (f" (of the newest {RUNS_READ} run records)" if capped else "")


def _incident_places(network: str, ids) -> dict:
    """``{incident id: "s1 Gi1/0"}`` for *ids*, from the incidents store (one read)."""
    from modules import problem as P
    from modules.heal import incidents

    want, out = set(ids), {}
    if not want:
        return out
    for rec in incidents.read(network).get("incidents") or []:
        if isinstance(rec, dict) and rec.get("id") in want:
            prob = P.classify({"incident": rec, "entry": {}})
            out[rec["id"]] = " ".join(x for x in (prob.device or rec.get("device") or "",
                                                  _short(prob.object or "")) if x)
    return out


def record_of(network: str, keys, track=(), runs=None, capped=False) -> dict:
    """A fix's record: its runs (each run record whose key is one of *keys*, newest first) and
    its track's rows that have no run record (a Dry run's, one held by a guard):
    ``{"rows", "runs", "verified", "dry", "summary", "last", "more"}``, *rows* at most
    `RECORD_SHOWN`, each ``{"at", "where", "who", "ok", "words", "run", "device"}``."""
    from modules.nsot import command_plan_run as CR

    if runs is None:
        runs, capped = _runs(network)
    keys = set(keys)
    rows, seen = [], set()
    for r in runs:
        if r.get("key") not in keys:
            continue
        seen.add(r.get("id"))
        refused = r.get("state") == "refused"
        auto = r.get("actor_kind") == "authority" or bool(r.get("authority"))
        params = r.get("params") or {}
        rows.append({"at": r.get("at") or "", "device": r.get("device") or "",
                     "where": " ".join(x for x in (r.get("device") or "",
                                                   _short(params.get("interface") or "")) if x),
                     "who": "Automatic" if auto else f"run by {_people(r.get('actor'))}",
                     "ok": r.get("state") == "done", "refused": refused, "dry": False,
                     "words": CR.OUTCOME_WORDS.get(r.get("outcome") or "", "")
                     or str(r.get("why") or r.get("outcome") or r.get("state") or ""),
                     "run": r.get("id") or ""})
    loose = [row for row in track or [] if not (row.get("run") and row.get("run") in seen)]
    places = _incident_places(network, [row.get("incident") for row in loose])
    for row in loose:
        dry = row.get("mode") == "dry_run"
        rows.append({"at": row.get("at") or "", "device": "",
                     "where": places.get(row.get("incident") or "", ""),
                     "who": "Dry run" if dry else "Automatic", "ok": bool(row.get("ok")),
                     "refused": not dry and not row.get("sent"), "dry": dry,
                     "words": str(row.get("words") or ""), "run": row.get("run") or ""})
    rows.sort(key=lambda x: x["at"], reverse=True)
    ran = [x for x in rows if not x["dry"] and not x["refused"]]
    verified = sum(1 for x in ran if x["ok"])
    dry = sum(1 for x in rows if x["dry"])
    return {"rows": rows[:RECORD_SHOWN], "more": max(0, len(rows) - RECORD_SHOWN),
            "runs": len(ran), "verified": verified, "dry": dry,
            "summary": _summary(len(ran), verified, dry, capped),
            "last": rows[0]["at"] if rows else ""}


def _kind_record(decisions: list, kind: str) -> dict:
    """A fix kind's record, from the network's heal decisions: how often self-healing acted on
    it, recorded a dry run, or proposed it."""
    mine = [d for d in decisions if d.get("kind") == kind]
    acted = sum(1 for d in mine if d.get("outcome") == "heal")
    dry = sum(1 for d in mine if d.get("outcome") == "would_heal")
    proposed = sum(1 for d in mine if d.get("outcome") == "propose")
    parts = ([f"self-healing acted {acted} time{'s' if acted != 1 else ''}"] if acted else []) \
        + ([f"{dry} dry-run record{'s' if dry != 1 else ''}, nothing changed"] if dry else []) \
        + ([f"proposed {proposed} time{'s' if proposed != 1 else ''}"] if proposed else [])
    rows = [{"at": d.get("at") or "", "where": d.get("device") or "", "device": "",
             "who": {"heal": "Self-healing", "would_heal": "Dry run",
                     "propose": "Proposed"}.get(d.get("outcome"), d.get("outcome") or ""),
             "ok": d.get("outcome") == "heal", "dry": d.get("outcome") == "would_heal",
             "refused": False, "words": str(d.get("outcome_words") or ""), "run": ""}
            for d in sorted(mine, key=lambda x: str(x.get("at") or ""), reverse=True)
            if d.get("outcome") in ("heal", "would_heal", "propose")]
    return {"rows": rows[:RECORD_SHOWN], "more": max(0, len(rows) - RECORD_SHOWN),
            "runs": acted, "verified": 0, "dry": dry,
            "summary": " · ".join(parts) or "no decision recorded",
            "last": rows[0]["at"] if rows else ""}


# ── Built-in fixes ───────────────────────────────────────────────────────────────────────────

def builtins(network: str, runs=None, capped=False) -> list:
    """Every built-in fix on *network*, each ``{"key", "name", "fixes", "how", "badge", "kind",
    "status", "hover", "record", "group"}``, how it runs from code and the network's settings
    (the module docstring), never typed."""
    from modules import heal_page
    from modules.heal import decisions as HD
    from modules.heal import policy as H
    from modules.nsot import command_plan as CP
    from modules.sdn import modes as sdn_modes

    if runs is None:
        runs, capped = _runs(network)
    out = []
    for t in CP.builtin().values():
        fixes = "; ".join(_cond_words({"condition": c}) for c in t.fixes) or \
            t.words.split(":")[0]
        out.append(_builtin_row(t.key, t.words.split(":")[0].strip(), fixes, "manual", (
            "Never by itself: the AI proposes it on a matching incident, and it runs once a "
            "person approves that plan by its hash"), record_of(network, [t.key], runs=runs,
                                                                capped=capped), "plan"))
    for key, name, fixes, hover in TELEMETRY:
        keys = [key] + (["telemetry-collector-resubscribe"]
                        if key == "telemetry-resubscribe" else [])
        out.append(_builtin_row(key, name, fixes, "manual", hover,
                                record_of(network, keys, runs=runs, capped=capped),
                                "telemetry"))
    try:
        cur = H.current(network)
    except Exception as exc:                          # noqa: BLE001 (said: its rows unread)
        log.error("fixes: %s's self-healing policy could not be read: %s", network, exc)
        return out
    lab = (cur.get("stage") or {}).get("stage") == sdn_modes.AUTO_STAGE
    now = H.MODE_WORDS.get(cur.get("mode") or "off", cur.get("mode") or "off")
    try:
        decisions = HD.decisions(network)
    except RuntimeError as exc:
        log.error("fixes: %s's heal decisions could not be read: %s", network, exc)
        decisions = []
    for k in heal_page._kinds(cur, lab):               # noqa: SLF001 (the tab's own rows)
        label = k["label"]
        name = label.split(":")[0].strip()
        fixes = H.KIND_WORDS.get(k["kind"]) or label
        if k["tier"] == 1 and k["on"]:
            how, hover = "automatic", (f"In {network}'s fix kinds to heal (Tier 1): self-"
                                       f"healing runs it by itself while in Auto; it is {now} on "
                                       f"{network} now")
        elif k["tier"] == 1:
            how, hover = "matched", (f"Not in {network}'s fix kinds to heal (\"Dry run only\"): "
                                     "self-healing records what it would do and changes "
                                     "nothing")
        elif k["on"]:
            how, hover = "manual", (f"Tier 2, in {network}'s fix kinds to propose: self-healing "
                                    "proposes it and a person approves each by its hash; "
                                    "never by itself")
        else:
            how, hover = "off", (f"Tier 2, not in {network}'s fix kinds to propose (\"Alert "
                                 "only\"): self-healing raises it and says it cannot fix it")
        out.append(_builtin_row(k["kind"], name, fixes, how, hover,
                                _kind_record(decisions, k["kind"]), "kind"))
    return out


#: What a built-in row's status line says after its record, by what runs it (its hover says
#: why, from the settings and the tier).
BUILTIN_SAID = {"plan": "runs inside a plan a person approves by its hash",
                "telemetry": "a person starts it; self-healing never does",
                "automatic": HOW["automatic"][2],
                "matched": "not in the fix kinds to heal: dry-run records only",
                "manual": "self-healing proposes it; a person approves each",
                "off": "not in the fix kinds to propose: an alert only"}


def _builtin_row(key, name, fixes, how, hover, record, group) -> dict:
    words, badge, _said = HOW[how]
    said = BUILTIN_SAID[group if group in ("plan", "telemetry") else how]
    return {"key": key, "name": name, "fixes": fixes, "how": how, "badge": badge,
            "words": words, "said": said, "hover": hover, "record": record, "saved": False,
            "group": group, "shared": False}


# ── The list ─────────────────────────────────────────────────────────────────────────────────

def _saved_rows(network: str, runs, capped, deleted: bool = False) -> list:
    """The network's saved fixes as rows; with *deleted*, its deleted ones instead."""
    from modules.nsot import saved_plans as S

    out = []
    every = S.fixes(network, deleted=True)
    for key, f in sorted(every.items(), key=lambda kv: kv[1].get("name") or kv[0]):
        if bool(f.get("retired")) != deleted:
            continue
        how = f["how"]
        words, badge, said = HOW[how]
        if deleted:
            r = f.get("retired") or {}
            words, badge, said = "Deleted", "muted", (
                f"deleted by {_people(r.get('by'))}; Restore… on its page brings it back")
        rec = record_of(network, [key], f.get("track") or (), runs=runs, capped=capped)
        hover = {"automatic": "Runs by itself on a matching incident while self-healing is in "
                              f"Auto; saved by {_people(f.get('promoted_by') or f.get('saved_by'))}"
                              ", and saving it was the approval",
                 "matched": "Offered on a matching incident; self-healing records what it "
                            "would do there and changes nothing by itself",
                 "manual": "Never by itself: a person presses Run… on its page"}[how]
        if deleted:
            hover = (f"Deleted by {_people((f.get('retired') or {}).get('by'))}: "
                     f"{(f.get('retired') or {}).get('reason') or 'no reason recorded'}")
        devices = {r["device"] for r in rec["rows"] if r.get("device")}
        out.append({"key": key, "name": f.get("name") or key, "fixes": fixes_words(f),
                    "how": how, "badge": badge, "words": words, "said": said, "hover": hover,
                    "record": rec, "saved": True, "group": "saved",
                    "shared": bool(f.get("shared")) and f.get("network") != network,
                    "devices": sorted(devices)})
    return out


def listing(network: str, q: str = "", mode: str = "", kind: str = "") -> dict:
    """Troubleshooting › Fixes for *network*: ``{"network", "total", "counts", "groups":
    [{"key", "title", "rows", "more", "count"}], "q", "mode", "kind", "filtered"}``. *q*
    matches a fix's name, what it fixes, or a device its record names; *mode* one of `MODES`;
    *kind* ``saved``, ``builtin`` or ``deleted`` (the deleted saved fixes, shown only by that
    filter: their record, origin and runs stay). Each group draws its first `SHOWN` rows and
    counts the rest. A read."""
    runs, capped = _runs(network)
    saved = _saved_rows(network, runs, capped)
    gone = _saved_rows(network, runs, capped, deleted=True)
    built = builtins(network, runs, capped)
    needle = " ".join(str(q or "").lower().split())

    def keep(r):
        if mode and r["how"] != mode:
            return False
        if needle and needle not in " ".join(
                [r["name"], r["fixes"], " ".join(r.get("devices") or []),
                 " ".join(x.get("where") or "" for x in r["record"]["rows"])]).lower():
            return False
        return True
    groups = []
    for gkey, title, rows in (("saved", "Saved", saved), ("builtin", "Built-in", built),
                              ("deleted", "Deleted", gone)):
        if (kind and kind != gkey) or (gkey == "deleted" and kind != "deleted"):
            continue
        hit = [r for r in rows if keep(r)]
        groups.append({"key": gkey, "title": title, "count": len(hit), "rows": hit[:SHOWN],
                       "more": max(0, len(hit) - SHOWN)})
    counts = {}
    for r in saved:
        counts[r["words"]] = counts.get(r["words"], 0) + 1
    return {"network": network, "total": len(saved) + len(built), "saved": len(saved),
            "built": len(built), "deleted": len(gone), "saved_counts": counts, "groups": groups, "q": q or "",
            "mode": mode or "", "kind": kind or "",
            "filtered": bool(needle or mode or kind), "shown": sum(g["count"] for g in groups)}


# ── A fix's page ─────────────────────────────────────────────────────────────────────────────

def _says(expect: str) -> dict:
    """What a named check's own module declares of it (``SAYS``, keyed by its function)."""
    from modules.nsot import command_plan as CP

    spec = CP.NAMED_CHECKS.get(expect or "")
    if not spec:
        return {}
    try:
        return dict((getattr(importlib.import_module(spec[0]), "SAYS", {}) or {})
                    .get(spec[1]) or {})
    except ImportError:
        return {}


def _values(f, t, name: str) -> list:
    """The values parameter *name* takes in this fix: through its fill's map, else every
    choice of the template."""
    from modules.nsot import saved_plans as S

    fills = (f or {}).get("fills") or {}
    if name in fills:
        field, mapping = S.fill_of(name, fills[name])
        if isinstance(mapping, dict):
            # A match that names the field it is filled from leaves one value only.
            held = ((f or {}).get("match") or {}).get(field)
            if held is not None and held in mapping:
                return [mapping[held]]
            return sorted(set(mapping.values()))
    return list((t.parameters.get(name) or {}).get("of") or [])


def _check(f, t, item: dict) -> dict:
    """One check as the page says it: ``{"name", "reads", "limits"}``, *reads* the template's
    own read or its module's declared one, *limits* ``[{"label", "words"}]``."""
    said = _says(item.get("expect") or "")
    if "by" in said:
        vals = [v for v in _values(f, t, said["by"]) if v in said]
        each = [(said[v].get("label") or v, said[v]) for v in vals]
        reads = "; ".join((f"{lab}: " if len(each) > 1 else "") + (s.get("reads") or "")
                          for lab, s in each if s.get("reads"))
        limits = [{"label": lab if len(each) > 1 else "", "words": s["limit"]}
                  for lab, s in each if s.get("limit")]
    else:
        reads = said.get("reads") or ""
        limits = [{"label": "", "words": said["limit"]}] if said.get("limit") else []
    return {"name": item["name"], "reads": reads or item.get("read") or "", "limits": limits}


def _params(f, t, by_run: bool = True) -> list:
    """Each parameter but the device, in words: where its value comes from (*by_run*: Run…
    on this page fills it; else the plan a person approves names it)."""
    from modules.nsot import saved_plans as S

    out, matched = [], bool((f or {}).get("match"))
    for name, spec in t.parameters.items():
        if spec["type"] == "device":
            continue
        if spec["type"] == "interface":
            words = ("the matched incident's port, from Mercury's model of the switch"
                     if matched else "the port chosen at Run…, from the switch's committed "
                                     "intent" if by_run else
                     "the port the approved plan names, held to the switch's committed intent")
            if spec.get("access_port"):
                words += "; an access port"
            if spec.get("not_management"):
                words += ", never the path Mercury manages the switch through"
        else:
            vals = _values(f, t, name)
            src = ""
            if matched and name in ((f or {}).get("fills") or {}):
                src = f", from the incident's {S.fill_of(name, f['fills'][name])[0]}"
            words = (" or ".join(vals) or "one of its choices") + src
        out.append({"name": name, "words": words})
    return out


def _from_incident(network: str, f: dict) -> dict:
    """The incident a fix was saved from: ``{"title", "at", "id"}``, its id kept on the save
    (since C3849 piece 3) or the incident its run fixed; ``{}`` when none is held."""
    from modules import incident_page
    from modules.heal import incidents

    src = f.get("from_run") or {}
    iid = str(src.get("incident") or "")
    if not iid and src.get("run"):
        iid = next((str(i.get("id")) for i in incidents.read(network).get("incidents") or []
                    if isinstance(i, dict) and (i.get("fixed") or {}).get("run") == src["run"]),
                   "")
    if not iid:
        return {}
    found = incident_page.resolve(network, iid)
    if found.get("found") != "page":
        return {}
    rec = found.get("incident") or {}
    try:
        title = incident_page.title(rec, found.get("entry") or {}, found.get("decisions") or [])
    except Exception as exc:                          # noqa: BLE001 (said without a title)
        log.error("fixes: %s's title could not be built: %s", iid, exc)
        title = ""
    return {"id": iid, "title": title or "the incident",
            "at": rec.get("opened_at") or src.get("at") or ""}


def _source_run(network: str, f: dict) -> dict:
    from modules.nsot import privileged

    run = (f.get("from_run") or {}).get("run") or ""
    try:
        return (privileged.get(network, run) or {}) if run else {}
    except (OSError, ValueError):
        return {}


def find(network: str, key: str) -> dict:
    """What *key* names on *network*: ``{"kind": "saved"|"plan"|"builtin"|"unknown", "fix",
    "template", "row"}``."""
    from modules.nsot import command_plan as CP
    from modules.nsot import saved_plans as S

    f = S.fixes(network, deleted=True).get(key)
    if f:
        t = S.templates().get(key)
        return {"kind": "saved", "fix": f, "template": t, "row": None}
    if key in CP.builtin():
        return {"kind": "plan", "fix": None, "template": CP.builtin()[key], "row": None}
    row = next((r for r in builtins(network) if r["key"] == key), None)
    if row:
        return {"kind": "builtin", "fix": None, "template": None, "row": row}
    return {"kind": "unknown", "fix": None, "template": None, "row": None}


def page(network: str, key: str) -> dict:
    """A fix's page (the module docstring): ``{"kind", "key", "network", "name", "fixes",
    "how", "badge", "words", "said", "hover", "heal_now", "from", "contents", "origin",
    "record", "runs", "limits", "changed", "runnable", "why_not"}``. A read."""
    from modules.nsot import saved_plans as S

    got = find(network, key)
    out = {"kind": got["kind"], "key": key, "network": network, "name": key, "from": {},
           "contents": None, "origin": [], "record": None, "limits": [], "changed": [],
           "runnable": False, "why_not": "", "heal_now": "", "hover": "", "shared": False,
           "deleted": {}, "change_right": "", "by_run": False}
    if got["kind"] == "unknown":
        return out
    if got["kind"] == "builtin":
        r = got["row"]
        out.update({k: r[k] for k in ("name", "fixes", "how", "badge", "words", "said",
                                      "hover", "record")},
                   origin=[{"dt": "Ships with", "words": "Mercury: built in, read-only here"}],
                   why_not="A built-in fix is read-only here.")
        return out
    t = got["template"]
    f = got["fix"]
    # Run… here fills a matched fix from its incident, and one with no match only when a
    # device and an interface are all it takes (`saved_plans.interface_actions`).
    by_run = got["kind"] == "saved" and (bool(f.get("match"))
                                         or key in S.interface_actions(network))
    if t is not None:
        checks = [_check(f, t, i) for i in t.preconditions]
        verify = [_check(f, t, i) for i in t.verify]
        out["contents"] = {"program": list(t.commands), "params": _params(f, t, by_run),
                           "checks": checks, "verify": [v["name"] for v in verify]
                           + (["The running configuration after equals the one before, line "
                               "for line, or it is rolled back"] if t.net_zero else [])}
        out["limits"] = [{"name": c["name"], **lim} for c in checks + verify
                         for lim in c["limits"]]
    if got["kind"] == "plan":
        out.update(name=t.words.split(":")[0].strip(),
                   fixes="; ".join(_cond_words({"condition": c}) for c in t.fixes)
                   or t.words, how="manual",
                   hover=("Never by itself: the AI proposes it on a matching incident, and it "
                          "runs once a person approves that plan by its hash"),
                   record=record_of(network, [key]),
                   origin=[{"dt": "Ships with", "words": "Mercury: built in, read-only here"}],
                   why_not=("A built-in fix is read-only here: it runs inside a plan a person "
                            "approves on its incident"))
        out.update(words=HOW["manual"][0], badge=HOW["manual"][1], said=BUILTIN_SAID["plan"])
        return out
    how = f["how"]
    words, badge, said = HOW[how]
    if how == "manual" and not by_run:
        said = ("runs as a step of a plan a person approves by its hash; Run… here cannot "
                "fill all it takes")
    out["by_run"] = by_run
    heal = S.heal_mode(network)
    out.update(name=f.get("name") or key, fixes=fixes_words(f, t), how=how, words=words,
               badge=badge, said=said, shared=bool(f.get("shared")),
               heal_now={"off": "Off", "dry_run": "Dry run", "auto": "Auto"}.get(heal, heal),
               record=record_of(network, [key], f.get("track") or ()))
    out["from"] = _from_incident(network, f)
    src = f.get("from_run") or {}
    run = _source_run(network, f)
    origin = []
    if out["from"]:
        origin.append({"dt": "Saved from", "words": out["from"]["title"],
                       "at": out["from"]["at"], "incident": out["from"]["id"]})
    elif run:
        origin.append({"dt": "Saved from", "words": f"a verified run on {run.get('device')}",
                       "at": src.get("at") or ""})
    if run:
        origin.append({"dt": "The plan", "words": (
            f"{run.get('title') or src.get('plan') or 'a command plan'}, approved by "
            f"{_people(run.get('actor') or src.get('by'))} and verified on the device"),
            "at": src.get("at") or ""})
    auto_at_save = f.get("mode") == "auto" and f.get("promoted_at") == f.get("saved_at")
    origin.append({"dt": "Saved", "words": f"by {_people(f.get('saved_by'))}"
                   + (": saving it was the approval" if auto_at_save else ""),
                   "at": f.get("saved_at") or ""})
    origin.append({"dt": "Scope", "words": ("shared with every network" if f.get("shared")
                                            else f"{f.get('network') or network} only")})
    out["origin"] = origin
    changed = [{"words": ("Saved Automatic" if auto_at_save else "Saved in Dry run" if
                          f.get("match") else "Saved, Manual only")
                + f" by {_people(f.get('saved_by'))}", "at": f.get("saved_at") or ""}]
    if f.get("changed_at"):
        changed.append({"words": f"a match added by {_people(f.get('changed_by'))}",
                        "at": f["changed_at"]})
    if f.get("mode") == "auto" and not auto_at_save and f.get("promoted_at"):
        changed.append({"words": f"Dry run to Automatic by {_people(f.get('promoted_by'))}",
                        "at": f["promoted_at"]})
    for r in f.get("retirements") or []:
        changed.append({"words": f"{'Deleted' if r.get('action') == 'deleted' else 'Restored'}"
                                 f" by {_people(r.get('by'))}: {r.get('reason') or ''}",
                        "at": r.get("at") or ""})
    out["changed"] = sorted(changed, key=lambda c: str(c["at"]), reverse=True)
    out["deleted"] = dict(f.get("retired") or {})
    if out["deleted"]:
        out.update(words="Deleted", badge="muted", said=(
            f"deleted by {_people(out['deleted'].get('by'))}: never offered, matched or run, "
            "and not in the AI's catalog; its record, origin and runs are kept"),
            hover=out["deleted"].get("reason") or "")
    out["runnable"] = by_run and not out["deleted"]
    out["change_right"] = S.change_right(f)
    return out


def delete_form(network: str, key: str, who: dict) -> dict:
    """Delete…'s (or Restore…'s) form for a saved fix: ``{"action", "right", "rule"}``, *right*
    the viewer's refusal for the right changing it takes (`saved_plans.change_right`), *rule*
    what a reason is (`authorisation`'s shape)."""
    from modules import identity
    from modules.nsot import authorisation
    from modules.nsot import saved_plans as S

    f = S.fixes(network, deleted=True).get(key) or {}
    return {"action": "restore" if f.get("retired") else "delete",
            "right": (identity.ai_acting_refusal("delete or restore a saved fix")
                      or identity.right_refusal(S.change_right(f), **who)) if f else
            "no saved fix", "rule": (f"at least {authorisation.MIN_WORDS} words and "
                                     f"{authorisation.MIN_CHARS} characters")}


# ── Run… ─────────────────────────────────────────────────────────────────────────────────────

def _intent_ports(intent: dict, access_only: bool) -> list:
    out = []
    for i in (intent or {}).get("interfaces") or []:
        if not isinstance(i, dict) or not i.get("name"):
            continue
        if access_only and str(i.get("switchport_mode") or "") != "access":
            continue
        out.append(i)
    return out


def _preview(network: str, key: str, values: dict) -> dict:
    """The runner's own preview (asking no device), as the run card draws it."""
    from modules.nsot import command_plan as CP

    p = CP.preview(network, key, values)
    d = p.get("drawn") or {}
    return {"ok": bool(p["ok"]), "refusals": list(p.get("refusals") or []),
            "title": d.get("title") or p.get("title") or "", "hash": p.get("hash") or "",
            "short": (p.get("hash") or "")[:8], "program": list(d.get("program") or []),
            "checks": [i["name"] for i in d.get("preconditions") or []],
            "verify": [i["name"] for i in d.get("verify") or []]}


def _ended(network: str, incident_id: str) -> bool:
    """Whether *incident_id* has ended by its page's own rule (`incident_page.state_of`:
    fixed, cleared or cancelled), the rule the run's POST refuses by (`fixit_v2._ended`), so
    the card never offers a port whose run would be refused (the review, 2026-11-16). An
    incident that cannot be resolved is not offered either."""
    from modules import incident_page

    try:
        found = incident_page.resolve(network, incident_id)
        if found.get("found") != "page":
            return True
        state = incident_page.state_of(found["incident"], found["entry"], found["decisions"])
    except Exception as exc:                          # noqa: BLE001 (not offered, said)
        log.warning("fix page: %s's state could not be read: %s", incident_id, exc)
        return True
    return state in ("fixed", "cleared", "cancelled")


def run_card(network: str, key: str, *, device: str = "", interface: str = "",
             right: str = "") -> dict:
    """Run…'s card (the module docstring): ``{"state", "key", "network", "name", "devices",
    "ports", "device", "interface", "why", "note", "preview", "post", "right"}``. *state*
    ``choose`` (a preview to approve), ``none`` (no port needs it: *why*), ``refused`` (the
    preview refused: its refusals) or ``not_offered``. *post* is the existing run path's
    ``{"endpoint", "args", "vals"}``. A read: no device is asked."""
    from modules import incident_page
    from modules.neighbours import committed_intents_of
    from modules.nsot import ifnames
    from modules.nsot import saved_plans as S

    got = find(network, key)
    c = {"state": "not_offered", "key": key, "network": network, "name": key, "devices": [],
         "ports": [], "device": "", "interface": "", "why": "", "note": "", "preview": None,
         "post": None, "right": right}
    if got["kind"] != "saved" or got["template"] is None:
        return dict(c, why="A built-in fix is read-only here: it runs inside a plan a person "
                           "approves on its incident")
    f, t = got["fix"], got["template"]
    c["name"] = f.get("name") or key
    if f.get("retired"):
        return dict(c, why=f"{c['name']} is deleted: Restore… under How it runs brings it back")
    intents, err = committed_intents_of(network)
    if f.get("match"):
        by_dev = {}
        for iid, prob in S._incidents_problems(network):   # noqa: SLF001 (its one read)
            if S.matches(f["match"], prob) and prob.device and not _ended(network, iid):
                by_dev.setdefault(prob.device, []).append((prob.object or "", iid, prob))
        names = sorted(set(intents or {}) | set(by_dev))
        if not names:
            return dict(c, state="none", why=f"No device of {network} is in its committed "
                                             f"intent{': ' + err if err else ''}")
        dev = device if device in names else (sorted(by_dev)[0] if by_dev else names[0])
        c["devices"] = [{"name": n, "chosen": n == dev, "label": n + (
            f" ({len(by_dev[n])} port{' needs' if len(by_dev[n]) == 1 else 's need'} this fix)"
            if n in by_dev else " (none needs it now)")} for n in names]
        c["device"] = dev
        ports = by_dev.get(dev) or []
        if not ports:
            return dict(c, state="none", why=f"No port on {dev} needs this fix right now")
        intent = (intents or {}).get(dev) or {}
        desc = {ifnames.canonical(i.get("name")): str(i.get("description") or "")
                for i in _intent_ports(intent, False)}
        chosen = next((p for p in ports if interface and ifnames.same_interface(p[0], interface)),
                      ports[0])
        for port, iid, prob in ports:
            d = desc.get(ifnames.canonical(port)) if port else ""
            c["ports"].append({"value": port, "chosen": port == chosen[0], "label": (
                f"{_short(port)} ({d + ', ' if d else ''}"
                f"{str(prob.condition).replace('_', '-')}"
                f"{' by ' + prob.cause if prob.cause else ''})")})
        c["interface"], iid = chosen[0], chosen[1]
        c["note"] = ("Only the ports an open incident says need this fix now; its checks read "
                     "the port live when you run it")
        found = incident_page.resolve(network, iid)
        offer = next((o for o in S.fix_offers(network, found) if o["key"] == key), None)
        if offer is None:
            from modules import problem as P
            try:
                values = S.fill(f, P.classify(found))
            except S.Refused as exc:
                return dict(c, state="refused", preview={"ok": False, "refusals": [str(exc)]})
            return dict(c, state="refused", preview=_preview(network, key, values))
        c["where"] = f"{dev} {_short(c['interface'])}"
        pv = _preview(network, key, offer["values"])
        if pv["ok"] and pv["hash"] != offer["hash"]:
            return dict(c, state="refused", preview=dict(pv, ok=False, refusals=[
                "its preview moved while this card was drawn; choose again"]))
        return dict(c, state="choose" if pv["ok"] else "refused", preview=pv,
                    post={"endpoint": "fixit_v2.fix_with_script",
                          "args": {"incident_id": iid, "list": network},
                          "vals": {"key": key, "hash": offer["hash"], "view": "fix"}})
    if key not in S.interface_actions(network):
        others = [n for n in t.parameters if n not in ("device", "interface")]
        return dict(c, why=(f"Run… here fills a device and an interface, and this fix also "
                            f"takes {', '.join(others) or 'more'}: it runs as a step of a plan "
                            "a person approves"))
    access_only = bool((t.parameters.get("interface") or {}).get("access_port"))
    eligible = {n: _intent_ports(i, access_only) for n, i in sorted((intents or {}).items())}
    names = [n for n, ports in eligible.items() if ports]
    if not names:
        return dict(c, state="none", why=(f"No device of {network} has "
                                          f"{'an access port' if access_only else 'an interface'}"
                                          f" in its committed intent"
                                          f"{': ' + err if err else ''}"))
    dev = device if device in names else names[0]
    word = "access port" if access_only else "interface"
    c["devices"] = [{"name": n, "chosen": n == dev, "label": (
        f"{n} ({len(eligible[n])} {word}{'s' if len(eligible[n]) != 1 else ''})")}
        for n in names]
    c["device"] = dev
    ports = eligible[dev]
    chosen = next((str(i["name"]) for i in ports
                   if interface and ifnames.same_interface(str(i["name"]), interface)),
                  str(ports[0]["name"]))
    c["ports"] = [{"value": str(i["name"]), "chosen": str(i["name"]) == chosen,
                   "label": f"{_short(str(i['name']))} ("
                            + (f"{i['description']}, " if i.get("description") else "")
                            + f"{i.get('switchport_mode') or 'no switchport'})"} for i in ports]
    c["interface"] = chosen
    c["note"] = (f"Every {word} in {dev}'s committed intent: this fix matches no problem, so "
                 "Mercury cannot tell which port needs it; its checks read the port live when "
                 "you run it")
    c["where"] = f"{dev} {_short(chosen)}"
    pv = _preview(network, key, {"device": dev, "interface": chosen})
    return dict(c, state="choose" if pv["ok"] else "refused", preview=pv,
                post={"endpoint": "saved_plans_v2.device_run",
                      "args": {"device": dev, "list": network},
                      "vals": {"key": key, "interface": chosen, "hash": pv["hash"],
                               "view": "fix"}})


def run_state(network: str, run_id: str) -> dict:
    """A run's state from its own record, for the run card: ``{"id", "state", "outcome",
    "words", "title", "device", "ok"}``."""
    from modules.nsot import command_plan_run as CR
    from modules.nsot import privileged

    try:
        rec = privileged.get(network, run_id) or {}
    except (OSError, ValueError):
        rec = {}
    state = rec.get("state") or "running"
    return {"id": run_id, "state": state, "outcome": rec.get("outcome") or "",
            "words": CR.OUTCOME_WORDS.get(rec.get("outcome") or "", "")
            or str(rec.get("why") or ""), "title": rec.get("title") or "",
            "device": rec.get("device") or "", "ok": state == "done"}
