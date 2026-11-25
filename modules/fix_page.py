"""modules/fix_page.py — Troubleshooting › Fixes and a fix's own page (C3849 pieces 2 to 4;
boards docs/boards/fixes-list.html and docs/boards/fix-bpdu-guard.html, approved by the
operator 2026-11-16 with changes), the models `routes/fixes_v2.py` draws.

**Every fix a network has, from code and records, never typed:**

- *Saved* fixes: `saved_plans.fixes(network)` (its own and the shared ones), each read as a fix
  (`saved_plans.as_fix`), how it runs from its own match and mode (`saved_plans.how_of`).
- *Built-in* fixes, read-only: each command plan that ships with Mercury
  (`command_plan.builtin`), which runs when a person presses its Run… (as a saved fix's, below)
  or inside a plan a person approves by its hash; each
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

**Run…** (`run_card`; board docs/boards/fix-manual-controls.html screen 1): "Run on an open
incident…", the open incidents this fix's match holds, the one picked filling device, object
and cause from its problem, run through the incident's own "Fix with:" path
(`fixit_v2.fix_with_script`); and "Or choose a device and interface…", a device and a port from
committed intent and each choice the plan takes, run through the device's saved-action path
(`saved_plans_v2.device_run`). Both are chosen from what Mercury already holds, never a device
read; the preview is the runner's own (`command_plan.preview`, asking no device), and the live
preconditions read the device when it runs. A person's action: the same with self-healing on
or off.

A built-in command plan's Run… (the operator, 2026-11-17: "same as saved fixes") is the same
card and the same two run paths: its open incidents are those whose problem is one its
``fixes:`` names, each filling its parameters from the incident (`builtin_offer`, which
`fixit_v2.fix_with_script` holds the press to); else a device and each parameter the template
declares, chosen from committed intent (an interface, a telemetry subscription) or its own
choices, run through `saved_plans_v2.device_run`. The preview is a person's plan's
(``person_plan``): the person's Approve covers its provisional shapes.

**Versions** (`saved_plans.versions`): each run in the Record names the version it ran
(`saved_plans.version_at`); New fix… and Edit… are `fix_editor`'s.

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
#: The one list's default order (the operator, 2026-11-17): Mode, Automatic first, then Last
#: run newest first; a deleted fix after every mode.
MODE_RANK = {m: n for n, m in enumerate(MODES)}
#: Rows the one list draws before it counts the rest: every fix is a fix kind or a saved plan,
#: never one per device, so the whole catalogue is drawn and sorted in the page.
LIST_SHOWN = 100
#: Who a fix came from, as the Source column says it.
SOURCE_WORDS = {"builtin": "Mercury built-in", "ai": "AI", "person": "Person"}
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
    from modules import bluf, problem as P

    cond = str(problem.get("condition") or "")
    noun = (P.CONDITIONS.get(cond) or ("something", ""))[0]
    # C4032: the condition said by THE plain-words table (`bluf.TABLE`'s what, "{device}:
    # {object} lost" → "its telemetry lost"), never its key spliced in ("its telemetry
    # telemetry-lost"); only a what that leads otherwise (err-disabled's) keeps the key's words.
    what = str((bluf.TABLE.get(cond) or {}).get("what") or "")
    lead = "{device}: {object}"
    if what.startswith(lead):
        out = f"{noun} {what[len(lead):].split('{')[0].strip(' ,:')}".strip()
    else:
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
    """``{incident id: "access1 Gi1/0"}`` for *ids*, from the incidents store (one read)."""
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
    from modules.nsot import saved_plans as S

    if runs is None:
        runs, capped = _runs(network)
    keys = set(keys)
    rows, seen = [], set()
    for r in runs:
        if r.get("key") not in keys:
            continue
        seen.add(r.get("id"))
        # A run that sent nothing (``not_needed``) is no run of the fix, and never verified
        # (C3, `saved_plans.run_verified`): counted with the refused ones, said as not needed.
        nothing = r.get("outcome") == CR.NOT_NEEDED
        refused = r.get("state") == "refused" or nothing
        auto = r.get("actor_kind") == "authority" or bool(r.get("authority"))
        params = r.get("params") or {}
        rows.append({"at": r.get("at") or "", "device": r.get("device") or "",
                     "where": " ".join(x for x in (r.get("device") or "",
                                                   _short(params.get("interface") or "")) if x),
                     "who": "Automatic" if auto else f"run by {_people(r.get('actor'))}",
                     "ok": S.run_verified(r), "refused": refused, "dry": False,
                     "words": (f"not needed: {r.get('not_needed') or r.get('why') or ''}"
                               .rstrip(": ") if nothing else
                               CR.OUTCOME_WORDS.get(r.get("outcome") or "", "")
                               or str(r.get("why") or r.get("outcome") or r.get("state") or "")),
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
        out.append(_builtin_row(t.key, t.words.split(":")[0].strip(), fixes, "manual",
                                PLAN_HOVER, record_of(network, [t.key], runs=runs,
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
BUILTIN_SAID = {"plan": "a person runs it with Run…, or inside a plan approved by its hash",
                "telemetry": "a person starts it; self-healing never does",
                "automatic": HOW["automatic"][2],
                "matched": "not in the fix kinds to heal: dry-run records only",
                "manual": "self-healing proposes it; a person approves each",
                "off": "not in the fix kinds to propose: an alert only"}
#: How a built-in command plan runs, as its row's and page's hover say it.
PLAN_HOVER = ("Never by itself: a person presses Run… on its page, or the AI proposes it on a "
              "matching incident and it runs once a person approves that plan by its hash")
#: What self-healing does about an incident a built-in command plan fixes (Run…'s incidents).
PLAN_STATE = "self-healing never runs it by itself"


def _builtin_row(key, name, fixes, how, hover, record, group) -> dict:
    """A built-in's row as the list draws it (its status words are its page's, `page`)."""
    words, badge, _said = HOW[how]
    return {"key": key, "name": name, "fixes": fixes, "how": how, "badge": badge,
            "words": words, "hover": hover, "record": record, "saved": False,
            "group": group, "shared": False, "source": "builtin"}


def _source_of(network: str, f: dict) -> str:
    """``ai`` when *f* was saved from a run of an AI plan (its run's incident link names a
    proposal whose source is ``ai``), else ``person`` (written, or saved by a person from a
    run of Mercury's or a person's own fix). Two small reads; a record that cannot be read is
    ``person``, the save's own actor."""
    from modules.fixit import incident as F

    if f.get("written"):
        return "person"
    # A shared fix's run and incident are its own network's (the review: read from the
    # viewer's, a shared AI fix read Person).
    network = (f.get("from_run") or {}).get("network") or f.get("network") or network
    link = (_source_run(network, f) or {}).get(F.RUN_FIELD) or {}
    iid = str(link.get("incident") or (f.get("from_run") or {}).get("incident") or "")
    prop = str(link.get("proposal") or "")
    if not (iid and prop and F.valid_id(iid)):
        return "person"
    try:
        got = F.read(F.Incident(network, iid, "", "", 1.0))
    except Exception as exc:                          # noqa: BLE001 (said as the person's)
        log.info("fixes: %s's origin %s could not be read: %s", f.get("key"), iid, exc)
        return "person"
    line = next((x for x in got["lines"] if x.get("proposal") == prop), {})
    return "ai" if line.get("source") == "ai" else "person"


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
        # The row's Mode is its badge, who deleted it and why its hover (the one list, the
        # operator, 2026-11-17): the status sentence is its page's (`page`), never carried here.
        words, badge, _said = HOW[how]
        if deleted:
            words, badge = "Deleted", "muted"
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
                    "how": how, "badge": badge, "words": words, "hover": hover,
                    "record": rec, "saved": True, "group": "saved",
                    "shared": bool(f.get("shared")) and f.get("network") != network,
                    "devices": sorted(devices), "source": _source_of(network, f),
                    "deleted": deleted})
    return out


def _sorted(rows: list) -> list:
    """The one list's default order: Mode (Automatic first, a deleted fix last), then Last run
    newest first, then the name."""
    rows = sorted(rows, key=lambda r: r["name"].lower())
    rows = sorted(rows, key=lambda r: r["record"].get("last") or "", reverse=True)
    return sorted(rows, key=lambda r: len(MODES) if r.get("deleted")
                  else MODE_RANK.get(r["how"], len(MODES)))


#: A row's record as the list draws it: its Runs column (runs, verified, dry), its hover
#: (summary) and its Last run.
LIST_RECORD = ("runs", "verified", "dry", "summary", "last")


def _list_row(r: dict) -> dict:
    """A row (`_saved_rows`, `_builtin_row`) as the list draws it: without the devices its
    search reads, its record cut to `LIST_RECORD`."""
    return dict({k: v for k, v in r.items() if k != "devices"},
                record={k: r["record"].get(k) for k in LIST_RECORD})


def listing(network: str, q: str = "", mode: str = "", kind: str = "") -> dict:
    """Troubleshooting › Fixes for *network*: ``{"network", "total", "saved", "built",
    "deleted", "saved_counts", "rows", "more", "q", "mode", "kind", "filtered", "shown"}``,
    *rows* the one list, at most `LIST_SHOWN`. *q* matches a fix's name, what it fixes, or a
    device its record names; *mode* one of `MODES`; *kind* ``saved``, ``builtin`` or
    ``deleted`` (the deleted saved fixes, shown only by that filter: their record, origin and
    runs stay). A read."""
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
    rows_of = {"saved": saved, "builtin": built, "deleted": gone}
    for gkey, title, rows in (("saved", "Saved", saved), ("builtin", "Built-in", built),
                              ("deleted", "Deleted", gone)):
        if (kind and kind != gkey) or (gkey == "deleted" and kind != "deleted"):
            continue
        hit = [r for r in rows if keep(r)]
        groups.append({"key": gkey, "title": title, "count": len(hit), "rows": hit[:SHOWN],
                       "more": max(0, len(hit) - SHOWN)})
    # The one list (the operator, 2026-11-17: "One list instead of Saved / Built-in
    # sections"): the groups' matching rows together, in the default order.
    every = _sorted([r for g in groups for r in rows_of[g["key"]] if keep(r)])
    counts = {}
    for r in saved:
        counts[r["words"]] = counts.get(r["words"], 0) + 1
    # The groups choose the rows and count them (``shown``); the page draws the one list,
    # never the groups, so they are not carried; nor are a row's devices (searched, above)
    # or its record's rows (drawn on its own page), `_list_row`.
    return {"network": network, "total": len(saved) + len(built), "saved": len(saved),
            "built": len(built), "deleted": len(gone), "saved_counts": counts,
            "rows": [_list_row(r) for r in every[:LIST_SHOWN]],
            "more": max(0, len(every) - LIST_SHOWN),
            "mode_rank": MODE_RANK, "source_words": SOURCE_WORDS, "q": q or "",
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
        elif spec["type"] == "subscription":
            words = ("the incident's lost subscription, or one chosen at Run… from the device's "
                     "committed intent" if by_run else
                     "the subscription the approved plan names, held to committed intent")
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


def _page_record(rec: dict) -> dict:
    """*rec* (`record_of`, `_kind_record`) as a fix's page draws it: its rows, its count of
    the rest and its summary, whose words say the runs and how many verified; the counts
    themselves are the list's Runs column, never this page's."""
    return {k: v for k, v in rec.items() if k not in ("runs", "verified")}


def page(network: str, key: str) -> dict:
    """A fix's page (the module docstring): ``{"kind", "key", "network", "name", "fixes",
    "how", "badge", "words", "said", "hover", "heal_now", "from", "contents", "origin",
    "record", "limits", "changed", "runnable", "why_not"}``, *record* `record_of`'s as the page
    draws it (`_page_record`). Whether a saved fix is shared is said by its Origin's Scope. A
    read."""
    from modules.nsot import saved_plans as S

    got = find(network, key)
    out = {"kind": got["kind"], "key": key, "network": network, "name": key, "from": {},
           "contents": None, "origin": [], "record": None, "limits": [], "changed": [],
           "runnable": False, "why_not": "", "heal_now": "", "hover": "",
           "deleted": {}, "change_right": "", "by_run": False, "version": 0, "versions": [],
           "held_manual": {}, "editable": False}
    if got["kind"] == "unknown":
        return out
    if got["kind"] == "builtin":
        r = got["row"]
        out.update({k: r[k] for k in ("name", "fixes", "how", "badge", "words", "hover")},
                   said=BUILTIN_SAID[r["group"] if r["group"] in ("plan", "telemetry")
                                     else r["how"]],
                   record=_page_record(r["record"]),
                   origin=[{"dt": "Ships with", "words": "Mercury: built in, read-only here"}],
                   why_not="A built-in fix is read-only here.")
        return out
    t = got["template"]
    f = got["fix"]
    # Run… here fills a matched fix from its incident, and one with no match only when a
    # device, an interface and choices are all it takes (`saved_plans.port_actions`).
    # A built-in command plan's Run… fills it from a matching incident or a chosen device and
    # its declared parameters (`run_card`, the operator, 2026-11-17).
    by_run = got["kind"] == "plan" or (got["kind"] == "saved" and (
        bool(f.get("match")) or key in S.port_actions(network)))
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
                   or t.words, how="manual", hover=PLAN_HOVER,
                   record=_page_record(record_of(network, [key])),
                   origin=[{"dt": "Ships with", "words": "Mercury: built in, read-only here"}],
                   why_not=("Its lines ship with Mercury and are not edited here; Run… runs "
                            "it once, a person's press bound to its preview's hash"))
        out.update(words=HOW["manual"][0], badge=HOW["manual"][1], said=BUILTIN_SAID["plan"],
                   by_run=True, runnable=True)
        return out
    how = f["how"]
    words, badge, said = HOW[how]
    if how == "manual" and not by_run:
        said = ("runs as a step of a plan a person approves by its hash; Run… here cannot "
                "fill all it takes")
    elif how == "manual" and f.get("held_manual"):
        said = (f"was Automatic; Manual only until version {f['held_manual'].get('version')} "
                "has a verified run, then it can be set Automatic again")
    elif how == "manual" and f.get("match"):
        said = ("runs only when a person presses Run…; it can be set Automatic after its "
                "version's first verified run")
    out["by_run"] = by_run
    heal = S.heal_mode(network)
    out.update(name=f.get("name") or key, fixes=fixes_words(f, t), how=how, words=words,
               badge=badge, said=said,
               heal_now={"off": "Off", "dry_run": "Dry run", "auto": "Auto"}.get(heal, heal),
               record=_page_record(record_of(network, [key], f.get("track") or ())))
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
    changed = [] if f.get("written") else [
        {"words": ("Saved Automatic" if auto_at_save else "Saved in Dry run" if
                   f.get("match") else "Saved, Manual only")
         + f" by {_people(f.get('saved_by'))}", "at": f.get("saved_at") or ""}]
    # New fix…, Edit… and Set Automatic (the operator, 2026-11-16), each kept on the fix.
    for ch in f.get("changes") or []:
        what = str(S.CHANGE_WORDS.get(ch.get("action"), ch.get("action")) or "")
        changed.append({"words": f"{what[:1].upper()}{what[1:]} by "
                                 f"{_people(ch.get('by'))}: {ch.get('words') or ''}",
                        "at": ch.get("at") or ""})
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
    # Versions (the operator, 2026-11-16): every version kept, each run naming the one it ran
    # (`saved_plans.version_at`), and a fix held Manual only until its version verifies.
    vs = S.versions(f)
    out["version"] = vs[-1]["version"]
    out["versions"] = [{"version": v["version"], "at": v.get("at") or "",
                        "by": _people(v.get("by")), "why": v.get("why") or "",
                        "digest": v.get("digest") or "", "now": v is vs[-1]}
                       for v in reversed(vs)]
    for row in out["record"]["rows"]:
        row["version"] = S.version_at(f, row["at"]) if row.get("at") else 0
    out["held_manual"] = dict(f.get("held_manual") or {})
    out["editable"] = f.get("saved_as") in (S.FIX, "script") and not out["deleted"]
    return out


def automatic_form(network: str, key: str, who: dict) -> dict:
    """Set Automatic… for a matched fix held Manual only or in Dry run (the operator,
    2026-11-16: "can be set Automatic after its first verified run"): ``{"offer", "right",
    "ran", "why", "version"}``, *offer* whether it is drawn, *right* the viewer's refusal for
    the self-healing right (the AI none), *ran* the verified run of its version now
    (`saved_plans.verified_run`) or ``{}`` with *why*. A read."""
    from modules import identity
    from modules.nsot import saved_plans as S

    f = S.fixes(network).get(key) or {}
    if not f or not f.get("match") or f.get("mode") == "auto" or f.get("network") != network:
        return {"offer": False, "right": "", "ran": {}, "why": "", "version": 0}
    n = S.versions(f)[-1]["version"]
    ran = S.verified_run(network, f)
    # What it runs on now, said before the press and bound to it (C4261): *runs_on* the
    # digest the form sends, *runs_on_words* the line.
    return {"offer": True, "version": n, "ran": ran, **S.promote_line(network, key),
            "right": (identity.ai_acting_refusal("set a fix Automatic")
                      or identity.right_refusal("self_healing", **who)),
            "why": "" if ran else (f"version {n} has no verified run yet: press Run… once, on a "
                                   "matching incident or a chosen port, and once it verifies "
                                   "it can be set Automatic")}


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

    # Run… is always a person's press, and its run (`command_plan_run.run`, no authority) is a
    # person's plan: the preview is held as the run holds it (the operator, 2026-11-17).
    p = CP.preview(network, key, values, person_plan=True)
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


def _heal_words(network: str, f: dict, incident_id: str, heal: str) -> str:
    """What self-healing does about *incident_id* with this fix, from the network's mode now
    (*heal*) and the fix's own track: never a guard's hold it does not have (correction 2:
    err-disable is never held by guard 6, which holds configuration departures only, C3819)."""
    from modules.nsot import saved_plans as S

    mine = [r for r in f.get("track") or [] if r.get("incident") == incident_id]
    if heal == "off":
        return "needs a person: self-healing is Off"
    if f.get("mode") == S.MANUAL or not f.get("match"):
        return (f"self-healing is {'in Dry run' if heal == 'dry_run' else 'in Auto'}; this fix "
                "is Manual only")
    if heal == "dry_run" or f.get("mode") != "auto":
        dry = [r for r in mine if r.get("mode") == "dry_run"]
        return ("self-healing recorded what it would do" if dry else
                "self-healing records what it would do")
    ran = [r for r in mine if r.get("mode") == "auto"]
    return (f"self-healing ran it: {ran[-1].get('words')}" if ran and ran[-1].get("words")
            else "self-healing runs it by itself")


def _matching(network: str, f: dict, matches=None, state: str = "") -> list:
    """The open incidents whose classified problem the fix *f*'s match holds now (or any of
    *matches*: a built-in command plan's, one per condition it ``fixes:``), not ended by their
    page's own rule (`_ended`), newest first: ``[{"id", "problem", "record", "label", "where",
    "affected", "opened_at", "state"}]``, *state* what self-healing does about each (a built-in
    plan's own words, else the fix's track's). From Mercury's records only."""
    from modules.heal import incidents
    from modules.nsot import saved_plans as S

    recs = {str(r.get("id") or ""): r for r in incidents.read(network).get("incidents") or []
            if isinstance(r, dict)}
    heal = S.heal_mode(network)
    every = list(matches) if matches is not None else [f["match"]]
    out = []
    for iid, prob in S._incidents_problems(network):   # noqa: SLF001 (its one read)
        if (not (any(S.matches(m, prob) for m in every) and prob.device)
                or _ended(network, iid)):
            continue
        rec = recs.get(iid) or {}
        out.append({"id": iid, "problem": prob, "record": rec,
                    "where": " ".join(x for x in (prob.device, _short(prob.object or "")) if x),
                    "label": (f"{prob.device} {_short(prob.object or '')} "
                              f"{str(prob.condition).replace('_', '-')}"
                              f"{' by ' + prob.cause if prob.cause else ''}").strip(),
                    "affected": prob.affected or "", "opened_at": rec.get("opened_at") or "",
                    "state": state or _heal_words(network, f, iid, heal)})
    out.sort(key=lambda r: str(r["opened_at"]), reverse=True)
    return out


def _intent_subs(intent: dict) -> list:
    """The telemetry subscription ids a device's committed intent declares, in its order."""
    return [str(s.get("subscription")) for s in (intent or {}).get("telemetry") or []
            if isinstance(s, dict) and s.get("subscription") not in (None, "")]


def builtin_port(t) -> dict:
    """How Run… on a chosen device fills built-in command plan *t*: ``{"iface", "choices",
    "subs"}``, *iface* whether it takes an ``interface`` (chosen from committed intent),
    *choices* each choice it declares with its own values, *subs* each subscription parameter
    (chosen from the device's committed intent); ``None`` when a parameter is of a type Run…
    cannot choose from what Mercury holds. Never typed free."""
    iface, choices, subs = False, {}, []
    for name, spec in t.parameters.items():
        kind = spec.get("type")
        if kind == "device" and name == "device":
            continue
        if kind == "interface" and name == "interface":
            iface = True
        elif kind == "choice":
            choices[name] = list(spec.get("of") or [])
        elif kind == "subscription" and not subs:
            subs.append(name)
        else:
            return None
    return {"iface": iface, "choices": choices, "subs": subs}


def builtin_values(t, found: dict) -> tuple:
    """``(values, why)``: built-in command plan *t*'s parameters filled from the incident
    `incident_page.resolve` *found*, each by its declared type: the device the problem's; an
    interface the err-disabled port its classification read; a subscription the first its lost
    stream names (`diagnose_stream.target_from`; a recreate takes every subscription on that
    one's receiver); a choice the incident's own value of that name when it is one of the
    template's. *why* names a parameter the incident does not say. A read."""
    from modules import problem as P
    from modules.heal import diagnose_stream, errdisable

    rec = found.get("incident") or {}
    prob = P.classify(found)
    raw = errdisable.of_record(rec)
    values, missing = {}, []
    for name, spec in t.parameters.items():
        kind = spec.get("type")
        if kind == "device":
            v = prob.device
        elif kind == "interface":
            v = str(raw.get("port") or "")
        elif kind == "subscription":
            subs = (diagnose_stream.target_from(rec) or {}).get("subscriptions") or []
            v = str(subs[0]) if subs else ""
        else:
            of = list(spec.get("of") or [])
            v = next((str(x) for x in (raw.get(name), getattr(prob, name, None)) if x in of), "")
        if not v:
            missing.append(name)
        values[name] = v
    if missing:
        return {}, (f"the incident does not say which {', '.join(missing)} "
                    f"{t.key} takes: choose a device instead")
    return values, ""


def builtin_offer(network: str, found: dict, key: str) -> dict:
    """Built-in command plan *key* offered on the incident *found* (`incident_page.resolve`),
    as a saved fix's offer is (`saved_plans.fix_offers`): ``{"key", "name", "values", "hash",
    "refusals"}``, its values filled from the incident (`builtin_values`) and previewed as a
    person's plan (asking no device); ``{}`` when *key* is no built-in plan or the incident's
    problem is none its ``fixes:`` names. The card draws it and `fixit_v2.fix_with_script`
    holds the press to it. A read."""
    from modules import problem as P
    from modules.nsot import command_plan as CP

    t = CP.builtin().get(key)
    if t is None or found.get("found") != "page":
        return {}
    prob = P.classify(found)
    if not prob.device or prob.condition not in t.fixes:
        return {}
    name = t.words.split(":")[0].strip()
    values, why = builtin_values(t, found)
    if why:
        return {"key": key, "name": name, "values": {}, "hash": "", "refusals": [why]}
    p = CP.preview(network, key, values, person_plan=True)
    return {"key": key, "name": name, "values": values,
            "hash": (p.get("hash") or "") if p["ok"] else "",
            "refusals": list(p.get("refusals") or [])}


def run_card(network: str, key: str, *, incident: str = "", device: str = "",
             interface: str = "", port: bool = False, choices: dict = None,
             right: str = "") -> dict:
    """Run…'s card (the module docstring; board fix-manual-controls screen 1): ``{"state",
    "mode", "key", "network", "name", "incidents", "devices", "ports", "choices", "device",
    "where", "why", "note", "preview", "post", "right", "port_ok", "none_open"}``, *where* the
    device and the chosen port in words (the port itself is carried by the press, ``post``).
    *mode* ``incident`` ("Run on an open incident…": the open incidents this fix matches, the
    one chosen filling device, object and cause from its problem, run through the incident's
    own "Fix with:" path) or ``port`` ("Or choose a device and interface…": a device and a port
    from committed intent, and each choice the plan takes, run through the device's saved-action
    path). A built-in command plan's is the same card (the operator, 2026-11-17): its incidents
    by the conditions it ``fixes:`` (`builtin_offer`), else a device and each parameter it
    declares (`builtin_port`), its device chosen from committed intent; *port_words* that
    link's words. *state* ``choose`` (a preview to approve), ``none`` (*why*), ``refused`` (the
    preview's refusals) or ``not_offered``. *post* is the existing run path's ``{"url",
    "vals"}`` (its URL built here, so the card carries only what it draws). A person's action,
    the same with self-healing on or off. A read: no device is asked."""
    from flask import url_for

    from modules import incident_page
    from modules import problem as P
    from modules.neighbours import committed_intents_of
    from modules.nsot import ifnames
    from modules.nsot import saved_plans as S

    got = find(network, key)
    c = {"state": "not_offered", "mode": "port", "key": key, "network": network, "name": key,
         "incidents": [], "devices": [], "ports": [], "choices": [], "device": "",
         "why": "", "note": "", "preview": None, "post": None, "right": right,
         "port_ok": False, "none_open": False, "matched": False,
         "port_words": "Or choose a device and interface…"}
    if got["kind"] not in ("saved", "plan") or got["template"] is None:
        return dict(c, why="A built-in fix is read-only here: it runs inside a plan a person "
                           "approves on its incident")
    # A built-in command plan (the operator, 2026-11-17: "same as saved fixes"): its open
    # incidents by the conditions it ``fixes:``, else a device and its declared parameters.
    builtin = got["kind"] == "plan"
    f, t = got["fix"] or {}, got["template"]
    c["name"] = t.words.split(":")[0].strip() if builtin else (f.get("name") or key)
    if f.get("retired"):
        return dict(c, why=f"{c['name']} is deleted: Restore… under How it runs brings it back")
    porting = builtin_port(t) if builtin else S.port_actions(network).get(key)
    matches = ([{"condition": x} for x in t.fixes] if builtin else
               [f["match"]] if f.get("match") else [])
    iface = bool((porting or {}).get("iface", True))
    c.update(port_ok=porting is not None, matched=bool(matches),
             port_words=("Or choose a device and interface…" if iface else
                         "Or choose a device…"))
    if matches and not port:
        rows = _matching(network, f, matches=matches, state=PLAN_STATE if builtin else "")
        if rows:
            chosen = next((r for r in rows if r["id"] == incident), rows[0])
            c["incidents"] = [dict({k: r[k] for k in ("id", "label", "affected", "opened_at",
                                                      "state", "where")},
                                   chosen=r is chosen) for r in rows]
            prob, iid = chosen["problem"], chosen["id"]
            c.update(mode="incident", device=prob.device, where=chosen["where"])
            found = incident_page.resolve(network, iid)
            if builtin:
                # Filled from the incident (`builtin_offer`), the one the press is held to.
                offer = builtin_offer(network, found, key)
                if not offer.get("values"):
                    return dict(c, state="refused", preview={"ok": False, "refusals": (
                        offer.get("refusals") or [f"{c['name']} fixes none of this "
                                                  "incident's problem now"])})
            else:
                offer = next((o for o in S.fix_offers(network, found) if o["key"] == key),
                             None)
            if offer is None:
                try:
                    values = S.fill(f, P.classify(found))
                except S.Refused as exc:
                    return dict(c, state="refused", preview={"ok": False, "refusals": [str(exc)]})
                return dict(c, state="refused", preview=_preview(network, key, values))
            pv = _preview(network, key, offer["values"])
            if pv["ok"] and pv["hash"] != offer["hash"]:
                return dict(c, state="refused", preview=dict(pv, ok=False, refusals=[
                    "its preview moved while this card was drawn; choose again"]))
            return dict(c, state="choose" if pv["ok"] else "refused", preview=pv,
                        post={"url": url_for("fixit_v2.fix_with_script", incident_id=iid,
                                             list=network),
                              "vals": {"key": key, "hash": offer["hash"], "view": "fix"}})
        c["none_open"] = True
        # C3860 (the operator, 2026-11-16: "Run... with no matching incident shows one plain
        # message ("No open incident needs this fix right now"), not a device dropdown"): the
        # card says so and nothing else; the device and port path stays its own choice
        # (`port`, "Or choose a device and interface…").
        return dict(c, state="none", why="No open incident needs this fix right now")
    intents, err = committed_intents_of(network)
    if porting is None:
        others = [n for n in t.parameters if n not in ("device", "interface")]
        return dict(c, state="none" if c["none_open"] else "not_offered", why=(
            ("No open incident needs this fix right now, and " if c["none_open"] else "")
            + (f"Run… on a chosen port fills a device, an interface and choices, and this fix "
               f"also takes {', '.join(others) or 'more'}: it runs as a step of a plan a person "
               "approves")))
    # A subscription parameter (a built-in's) is chosen from the device's committed intent.
    subs = list(porting.get("subs") or [])
    access_only = bool((t.parameters.get("interface") or {}).get("access_port"))
    eligible = {n: (_intent_ports(i, access_only) if iface else [],
                    _intent_subs(i) if subs else [])
                for n, i in sorted((intents or {}).items())}
    names = [n for n, (ports, held) in eligible.items()
             if (ports or not iface) and (held or not subs)]
    word = "access port" if access_only else "interface"
    if not names:
        needs = (["an access port" if access_only else "an interface"] if iface else []) + (
            ["a telemetry subscription"] if subs else [])
        return dict(c, state="none", why=(f"No device of {network} has "
                                          + (f"{' and '.join(needs)} in its committed intent"
                                             if needs else "committed intent")
                                          + (f": {err}" if err else "")))
    dev = device if device in names else names[0]

    def label(n):
        ports, held = eligible[n]
        if iface:
            return f"{n} ({len(ports)} {word}{'s' if len(ports) != 1 else ''})"
        if subs:
            return f"{n} ({len(held)} subscription{'s' if len(held) != 1 else ''})"
        return n
    c["devices"] = [{"name": n, "chosen": n == dev, "label": label(n)} for n in names]
    c["device"] = dev
    ports = eligible[dev][0]
    chosen = ""
    if iface:
        chosen = next((str(i["name"]) for i in ports
                       if interface and ifnames.same_interface(str(i["name"]), interface)),
                      str(ports[0]["name"]))
        c["ports"] = [{"value": str(i["name"]), "chosen": str(i["name"]) == chosen,
                       "label": f"{_short(str(i['name']))} ("
                                + (f"{i['description']}, " if i.get("description") else "")
                                + f"{i.get('switchport_mode') or 'no switchport'})"}
                      for i in ports]
        c["note"] = (f"Every {word} in {dev}'s committed intent: "
                     + ("you choose the port, " if matches else
                        "this fix matches no problem, so Mercury cannot tell which port needs "
                        "it; ")
                     + "its checks read the port live when you run it")
    c["where"] = f"{dev} {_short(chosen)}" if chosen else dev
    # Each choice the plan takes (an err-disabled port's cause), chosen here: the match's own
    # value through its fill's map when it names one, else the first; a subscription from the
    # chosen device's committed intent.
    picked = {}
    for name, of in {**porting["choices"], **{n: eligible[dev][1] for n in subs}}.items():
        if not of:
            return dict(c, state="refused", preview={"ok": False, "refusals": [
                f"{c['name']} takes {name} and offers no choice of it"]})
        want = (choices or {}).get(name) or ""
        if want not in of:
            fill = (f.get("fills") or {}).get(name)
            _field, mapping = S.fill_of(name, fill) if fill is not None else ("", None)
            held = (f.get("match") or {}).get(_field) if _field else None
            want = (mapping or {}).get(held) if isinstance(mapping, dict) else None
            want = want if want in of else of[0]
        picked[name] = want
        words = (t.parameters.get(name) or {}).get("words") or name
        c["choices"].append({"name": name, "words": words,
                             "of": [{"value": v, "chosen": v == want} for v in of]})
    at = {"interface": chosen} if iface else {}
    pv = _preview(network, key, {"device": dev, **at, **picked})
    return dict(c, state="choose" if pv["ok"] else "refused", preview=pv,
                post={"url": url_for("saved_plans_v2.device_run", device=dev, list=network),
                      "vals": {"key": key, **at, "hash": pv["hash"], "view": "fix",
                               **picked}})


def run_state(network: str, run_id: str) -> dict:
    """A run's state from its own record, for the run card: ``{"id", "state", "outcome",
    "words", "title", "device", "ok"}``."""
    from modules.nsot import command_plan_run as CR
    from modules.nsot import privileged

    try:
        rec = privileged.get(network, run_id) or {}
    except (OSError, ValueError):
        rec = {}
    from modules.nsot import saved_plans as S

    state = rec.get("state") or "running"
    nothing = rec.get("outcome") == CR.NOT_NEEDED
    return {"id": run_id, "state": state, "outcome": rec.get("outcome") or "",
            "words": (f"not needed: {rec.get('not_needed') or rec.get('why') or ''}"
                      .rstrip(": ") if nothing else
                      CR.OUTCOME_WORDS.get(rec.get("outcome") or "", "")
                      or str(rec.get("why") or "")), "title": rec.get("title") or "",
            "device": rec.get("device") or "", "ok": S.run_verified(rec)}
