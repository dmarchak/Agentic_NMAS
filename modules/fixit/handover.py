"""The hand-over: an incident's write-up for an engineer, built from its records with no AI
call, kept as a new version each time, and sent to the teams a person chose as the event
``fixit_handover`` (board recurring-fixes v2, step 8; the fix-it plan's S3).

The operator's order (overnight item 6, 2026-11-12), which this module implements in part:
"AI troubleshooting, as designed: a background job; the AI proposes one catalog operation with
parameters; code validates it against intent and the guards; a person approves it; on failure
STOP with Retry with more information (cost shown first), Cancel or Hand over; a per-incident
cap of $1.00; a repeated failed proposal is flagged; payloads use stable labels. Settings ›
Background processes, AI mode Manual by default. Section 12's rule stays in force."

**The write-up's nine sections** (`SECTIONS`, the board's step 8), built in code from the
incident's record (`modules/fixit/incident.py`) and what the page hands in: the summary; the
impact now; what is known (Mercury's facts: the diagnosis's hypotheses, each with its read time
and source); what was tried (each attempt's operation, parameters, who proposed it, who
approved it, the outcome and its words); what the AI said, labelled advisory, or "no AI was
asked"; the configuration now (each receiver a run left removed, `resubscribe.removed_now`); the
next steps (the catalog's operations not tried, the reads that would decide, the standing
don'ts); the notes (the hand-over's and each Retry's); and the cost (the incident's AI spend by
call, and that the provider bills, not Mercury).

**People by display name, teams by name, no email address and no secret** (the board):
every person is `identity.display_name`, every recorded text drawn through
`display_names.people` (which replaces an identity with its display name), every text masked
(`redact.redact_payload`, by value and by position) before it is kept.

**Kept, never overwritten** (`hand_over`): a hand-over is first recorded as the incident's
choice line (`incident.record_handover`, which numbers it), then its write-up is kept under that
number, created once (``fixit/handover/<incident id>/<version>.json``, owner-only, under its
lock; a version already kept refuses, preserved). The write-up is the page's
``/v2/incident/<incident id>/handover/<version>`` once that route is built.

**Sent only by `send`** (the relay is called nowhere else in `modules/fixit/`,
tests/test_fixit_handover.py): through the relay can't-fix uses (`delivery.deliver_event`), to
the teams the person chose, each one of the teams told about the network's can't-fix
(`heal_notify.teams_for(network, "cant_fix")`, the board's "the teams told about can't-fix,
chosen, never typed"). With no team chosen nothing is sent, and the write-up is still kept.
The message carries the incident page's link and Mercury's facts by kind, never a
configuration line, a person's identity or a secret (`notify.message.check_event`, the egress
mask at its sender).
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

EVENT = "fixit_handover"
#: The teams a hand-over may be sent to: those told about the network's can't-fix.
OFFERED_FROM = "cant_fix"
VERSION = 1
STORE_DIR = "handover"
#: The write-up's sections, in the board's order: each one's key and title.
SECTIONS = (("summary", "Summary"), ("impact", "Impact now"),
            ("known", "What is known (Mercury's facts)"), ("tried", "What was tried"),
            ("ai", "What the AI said (advisory)"), ("config", "Configuration now"),
            ("next", "Next steps for an engineer"), ("notes", "Notes"), ("cost", "Cost"))
#: How a proposal's source reads in the write-up.
SOURCE_WORDS = {"mercury": "Mercury's diagnosis", "ai": "an AI answer (advisory)",
                "person": "a person", "": "no proposal recorded"}
#: The standing don'ts that apply to every hand-over.
DONTS = ("Change the device only through a Mercury operation, previewed and confirmed: a "
         "change at its console is outside the record and reads as drift.",
         "Do not run a fix that already failed in this incident again without saying what is "
         "different now.")
#: How many of a list the write-up draws before it counts the rest.
SHOWN = 10
NOTE_CHARS = 2000


class Refused(ValueError):
    """Nothing was kept or sent; the words say why."""


def _utc(epoch) -> str:
    if epoch is None:
        return ""
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(float(epoch)))


def _ago(seconds: float) -> str:
    s = max(0, int(seconds))
    days, rest = divmod(s, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = ([f"{days} day{'s' if days != 1 else ''}"] if days else []) + (
        [f"{hours} hour{'s' if hours != 1 else ''}"] if hours else [])
    if not parts:
        parts = [f"{minutes} minute{'s' if minutes != 1 else ''}"]
    return " ".join(parts[:2])


def _listed(items) -> str:
    from modules.heal.catalog import listed

    return listed(items)


def _person(actor: str) -> str:
    from modules import identity

    return identity.display_name(actor) or "nobody recorded"


def _people(text) -> str:
    from modules import display_names

    return display_names.people(text)


# ── The store ───────────────────────────────────────────────────────────────────────────────

def folder(incident) -> str:
    """Where *incident*'s write-ups are kept, asked without creating anything."""
    from modules.fixit import incident as F

    return os.path.join(os.path.dirname(F.path(incident)), STORE_DIR, incident.id)


def path(incident, version: int) -> str:
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise Refused(f"a hand-over's version is a whole number from 1, and {version!r} was "
                      "given")
    return os.path.join(folder(incident), f"{version}.json")


def _keep(incident, version: int, doc: dict) -> None:
    """Keep *doc* as *incident*'s write-up *version*, created once, masked, owner-only."""
    from modules import filestore
    from modules.redact import redact_payload

    p = path(incident, version)
    with filestore.PathLock(p):
        if os.path.exists(p):
            filestore.preserve_corrupt(p, f"hand-over {version} kept twice")
            raise Refused(f"{incident.id}'s hand-over {version} is already kept, and a "
                          "write-up is never written over: the one kept is preserved")
        filestore.write_atomic(p, json.dumps(redact_payload(doc), indent=1, sort_keys=True))


def read_version(incident, version: int) -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "doc", "error"}``: one kept write-up. A read
    creates nothing; absent and unreadable are different facts."""
    p = path(incident, version)
    if not os.path.exists(p):
        return {"state": "absent", "doc": None, "error": ""}
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "doc": None,
                "error": f"{incident.id}'s hand-over {version} cannot be read "
                         f"({type(exc).__name__})"}
    if not isinstance(doc, dict) or doc.get("incident") != incident.id \
            or doc.get("version") != version:
        return {"state": "unreadable", "doc": None,
                "error": f"{incident.id}'s hand-over {version} is not that write-up"}
    return {"state": "ok", "doc": doc, "error": ""}


def versions(incident) -> dict:
    """``{"state", "versions", "error"}``: each hand-over the incident's record holds, oldest
    first, ``{"version", "at", "by", "teams", "kept"}`` (*by* the display name; *kept* whether
    its write-up is kept: ``ok``, ``absent`` or ``unreadable``)."""
    from modules.fixit import incident as F

    rec = F.read(incident)
    if rec["state"] == "unreadable":
        return {"state": "unreadable", "versions": [], "error": rec["error"]}
    out = []
    for line in rec["lines"]:
        if line.get("choice") != "handover":
            continue
        v = line.get("version")
        kept = read_version(incident, v)["state"] if isinstance(v, int) and v >= 1 else "absent"
        out.append({"version": v, "at": line.get("at", ""), "by": _person(line.get("by")),
                    "teams": list(line.get("teams") or []), "kept": kept})
    return {"state": "ok", "versions": out, "error": ""}


# ── The write-up ────────────────────────────────────────────────────────────────────────────

def _summary(incident, title: str, tried: list, resolved) -> list:
    what = title.strip() if title else (
        f"telemetry subscription {_listed(incident.subscriptions)} lost"
        if incident.subscriptions else f"incident {incident.id}")
    where = f"{incident.device}: " if incident.device else ""
    n = len(tried)
    fixes = f"{n} fix{'es' if n != 1 else ''} tried" if n else "no fix tried"
    state = ("resolved" if resolved is not None else
             "the last fix tried passed its verify, and the symptom still stands"
             if tried and tried[-1]["passed"] else "not fixed")
    return [f"{where}{_people(what)}; {fixes}; {state}."]


def _impact(incident, resolved, now: float) -> list:
    since = _utc(incident.detected)
    if resolved is not None:
        return [f"Resolved at {_utc(resolved)}, after {_ago(float(resolved) - incident.detected)}"
                f" (detected {since})."]
    if incident.subscriptions:
        return [f"{incident.device} has sent no telemetry for subscription "
                f"{_listed(incident.subscriptions)} since {since} "
                f"({_ago(now - incident.detected)})."]
    return [f"Standing since {since} ({_ago(now - incident.detected)})."]


def _known(diagnosis) -> list:
    d = diagnosis or {}
    hyps = d.get("hypotheses") or []
    if not d:
        return ["Mercury has not diagnosed this incident."]
    read = d.get("finished_at") or d.get("started_at") or ""
    source = f"Mercury's diagnosis {d.get('id') or ''}".rstrip()
    if not hyps:
        return [f"{source} ({read}) found no cause."]
    out = [f"{h.get('strength') or ''} ({h.get('rule') or ''}): {_people(h.get('claim') or '')}"
           f" (read {read}, {source}"
           + ("; its evidence is incomplete" if h.get("incomplete") else "") + ")"
           for h in hyps[:SHOWN]]
    if len(hyps) > SHOWN:
        out.append(f"and {len(hyps) - SHOWN} more, on the incident's page")
    return out


def _tried(tried: list) -> list:
    from modules.heal import catalog

    if not tried:
        return ["Nothing was tried."]
    out = []
    for a in tried[:SHOWN]:
        op = catalog.CATALOG.get(a["operation"])
        params = "; ".join(f"{k} {', '.join(v) if isinstance(v, list) else v}"
                           for k, v in a["params"].items()
                           if v not in ("", [], False))
        out.append(f"Attempt {a['n']}, {a['at'].replace('T', ' ').replace('Z', ' UTC')}: "
                   f"{op.words if op else a['operation']} ({params or 'no parameter'}); "
                   f"proposed by {SOURCE_WORDS.get(a['source'], a['source'])}; approved by "
                   f"{_person(a['actor'])}; "
                   f"{'passed its verify' if a['passed'] else 'did not pass'}: "
                   f"{_people(a['words']) or a['outcome']}")
    if len(tried) > SHOWN:
        out.append(f"and {len(tried) - SHOWN} more attempts, on the incident's page")
    return out


def _ai(lines: list, advisory) -> list:
    asked = [ln for ln in lines if "proposal" in ln and ln.get("source") == "ai"]
    if not asked:
        return ["No AI was asked."]
    out = []
    for ln in asked[:SHOWN]:
        out.append(f"{ln.get('at', '')}: "
                   + (f"proposed {ln['operation']} (parameters {ln.get('params_hash')})"
                      if ln.get("operation") else "proposed no operation Mercury has")
                   + " — advisory; a person approves any fix")
    out += [f"Advisory: {_people(a)}" for a in list(advisory or ())[:SHOWN]]
    return out


def _config(incident) -> list:
    from modules.heal import resubscribe as R

    if not incident.device:
        return ["The incident names no device."]
    removed = R.removed_now(incident.network, incident.device)
    if not removed:
        return [f"No receiver a run left removed on {incident.device}."]
    return [f"{incident.device}'s receiver for subscription {r['sub']} is REMOVED (left by run "
            f"{r['run']}): add it back first" for r in removed]


def _next(tried: list, diagnosis) -> list:
    from modules.heal import catalog

    done = {a["operation"] for a in tried}
    out = [f"Not tried: {op.words} ({key})" for key, op in sorted(catalog.CATALOG.items())
           if key not in done]
    first = ((diagnosis or {}).get("hypotheses") or [{}])[0]
    if first.get("rule_out"):
        out.append(f"The read that would decide: {_people(first['rule_out'])}")
    for w in (first.get("incomplete") or [])[:3]:
        out.append(f"Not read: {_people(w)}")
    return out + list(DONTS)


def _notes(note: str, notes) -> list:
    out = [f"Retry note: {_people(n)}" for n in list(notes or ())[:SHOWN] if str(n).strip()]
    if note.strip():
        out.append(f"Hand-over note: {_people(note.strip())}")
    return out or ["No note was given."]


def _cost(incident) -> list:
    from modules.fixit import incident as F

    got = F.calls_of(incident)
    if got["state"] == "unreadable":
        return [f"Not known: {got['error']}."]
    from modules.fixit.policy import money

    out = [f"{c['id']}: {money(c['usd'])}" + (" (joined another's call)" if c["joined"] else "")
           for c in got["calls"]]
    total = sum((c["usd"] for c in got["calls"]), 0.0)
    out.append(f"Total {money(total)} in this incident"
               + (f" (of the calls the record holds: {got['error']})" if got["missing"] else "")
               + ". The provider bills, not Mercury.")
    return out


def build(incident, *, version: int, actor: str, at: float, note: str = "", notes=(),
          teams=(), diagnosis: dict = None, advisory=(), title: str = "",
          resolved: float = None) -> dict:
    """*incident*'s write-up, version *version*, by *actor* at *at*: ``{"version",
    "incident", "network", "device", "at", "by", "teams", "sections", "markdown"}``, every
    section a list of lines, *by* the display name. Reads the incident's records; keeps and
    sends nothing."""
    from modules.fixit import incident as F
    from modules.redact import redact_payload

    rec = F.read(incident)
    got = F.attempts(incident, resolved, now=at)
    tried = got["attempts"]
    lines = {
        "summary": _summary(incident, title, tried, resolved),
        "impact": _impact(incident, resolved, at),
        "known": _known(diagnosis),
        "tried": _tried(tried) + ([f"Not every attempt could be read: {_people(got['error'])}"]
                                  if got["state"] != "ok" else []),
        "ai": _ai(rec["lines"], advisory),
        "config": _config(incident),
        "next": _next(tried, diagnosis),
        "notes": _notes(str(note or "")[:NOTE_CHARS], notes),
        "cost": _cost(incident),
    }
    doc = {"version": version, "incident": incident.id, "network": incident.network,
           "device": incident.device, "at": _utc(at), "by": _person(actor),
           "teams": list(teams), "link": page(incident),
           "sections": [{"key": k, "title": t, "lines": lines[k]} for k, t in SECTIONS]}
    doc = redact_payload(doc)
    doc["markdown"] = markdown(doc)
    return doc


def markdown(doc: dict) -> str:
    """A write-up as Markdown, its sections in order: the board's Download as Markdown."""
    head = (f"# Hand-over {doc['version']}: {doc['incident']}"
            + (f" on {doc['device']}" if doc.get("device") else ""))
    out = [head, "", f"Handed over {doc['at']} by {doc['by']}"
           + (f" to {_listed(doc['teams'])}" if doc.get("teams") else "") + ".", ""]
    for s in doc["sections"]:
        out += [f"## {s['title']}", ""] + [f"- {ln}" for ln in s["lines"]] + [""]
    return "\n".join(out)


def page(incident) -> str:
    """The incident's page on its network, as Mercury's own path: what the write-up and the
    message link to, built by the one place an incident's address is built
    (`incidents.incident_href`); ``""`` for an incident that names no device."""
    from modules.heal.incidents import incident_href

    return incident_href(incident.network, incident.id, device=incident.device)


# ── Handing over, and sending ───────────────────────────────────────────────────────────────

def offered(network: str) -> dict:
    """``{"state", "teams", "error"}``: the teams a hand-over on *network* may be sent to, each
    ``{"id", "name"}``: those told about its can't-fix (`heal_notify.teams_for`)."""
    from modules import heal_notify
    from modules.notify import teams

    ids = heal_notify.teams_for(network, OFFERED_FROM)
    got = teams.read()
    if got["state"] == "unreadable":
        return {"state": "unreadable", "teams": [], "error": got["error"]}
    return {"state": "ok", "error": "",
            "teams": [{"id": t, "name": (got["teams"].get(t) or {}).get("name", t)}
                      for t in ids]}


def _chosen(network: str, team_ids) -> list:
    if isinstance(team_ids, (str, bytes)):
        raise Refused(f"the teams chosen are a list of team ids, and {team_ids!r} was given")
    ids = list(dict.fromkeys(team_ids or ()))
    if not ids:
        return []
    got = offered(network)
    if got["state"] != "ok":
        raise Refused(f"the teams cannot be read ({got['error']}), so the teams chosen cannot "
                      "be checked: nothing was kept or sent")
    have = {t["id"]: t for t in got["teams"]}
    other = [t for t in ids if t not in have]
    if other:
        raise Refused(f"a hand-over goes to the teams told about {network}'s can't-fix, and "
                      f"team {_listed(other)} is not one of them (they are "
                      f"{_listed(t['name'] for t in got['teams']) if got['teams'] else 'none'})"
                      ": nothing was kept or sent")
    return [have[t] for t in ids]


def hand_over(incident, *, actor: str, actor_verified: str, note: str = "", notes=(),
              team_ids=(), diagnosis: dict = None, advisory=(), title: str = "",
              resolved: float = None, now: float = None, deliver=None) -> dict:
    """A verified person hands *incident* over: the teams chosen checked (each one told about
    the network's can't-fix), the choice line recorded (`incident.record_handover`, its
    version), the write-up built and kept as that version, and sent to the chosen teams
    (`send`). ``{"version", "doc", "sent"}``; nothing chosen sends nothing (``sent`` then
    says so). An unverified request is refused with nothing kept (`incident.NotAPerson`).
    *deliver* is `send`'s seam."""
    from modules.fixit import incident as F

    F._check(incident)
    F._person(actor, actor_verified, "a hand-over")
    at = time.time() if now is None else float(now)
    chosen = _chosen(incident.network, team_ids)
    line = F.record_handover(incident, actor, actor_verified,
                             teams=[t["name"] for t in chosen], now=at)
    version = line["version"]
    doc = build(incident, version=version, actor=actor, at=at, note=note, notes=notes,
                teams=[t["name"] for t in chosen], diagnosis=diagnosis, advisory=advisory,
                title=title, resolved=resolved)
    _keep(incident, version, doc)
    log.info("fixit: %s: hand-over %d kept by %s", incident.id, version, actor)
    sent = send(incident, version, [t["id"] for t in chosen], deliver=deliver)
    return {"version": version, "doc": doc, "sent": sent}


def event(incident, doc: dict) -> dict:
    """The message a kept write-up is sent as (`notify.message.FIELDS`): Mercury's facts by
    kind, the link to the incident's page, people by display name, nothing else."""
    sections = {s["key"]: s["lines"] for s in doc["sections"]}
    return {"incident": incident.id, "event": EVENT, "network": incident.network,
            "device": incident.device, "kind": "hand-over to an engineer",
            "happened": " ".join(sections["summary"]),
            "outcome": (f"Handed over by {doc['by']} at {doc['at']} (version {doc['version']}). "
                        + " ".join(sections["impact"])),
            "detected": " ".join(sections["known"][:2]),
            "detected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(incident.detected)),
            "steps": [{"what": ln, "result": ""} for ln in sections["tried"][:SHOWN]],
            "todo": "Open the incident's page: its write-up has the nine sections.",
            "link": doc.get("link") or page(incident)}


def send(incident, version: int, team_ids, *, deliver=None) -> dict:
    """Send *incident*'s kept write-up *version* to *team_ids* (each already one of the teams
    told about its can't-fix, `hand_over`): ``{"ok", "sent", "failed", "nobody", "words",
    "error"}``. With no team, nothing is sent and the words say it was kept. The relay is
    `delivery.deliver_event` (*deliver* its seam); its refusal or failure is said, never
    raised. The one caller of the relay in `modules/fixit/`."""
    from modules.notify import delivery

    ids = list(dict.fromkeys(team_ids or ()))
    if not ids:
        return {"ok": True, "sent": 0, "failed": 0, "nobody": True, "error": "",
                "words": "Kept; no team was chosen, so no team is told about this hand-over"}
    got = read_version(incident, version)
    if got["state"] != "ok":
        return {"ok": False, "sent": 0, "failed": 0, "nobody": False,
                "error": got["error"] or f"{incident.id}'s hand-over {version} is not kept",
                "words": "Not sent: the write-up to send is not kept"}
    try:
        out = (deliver or delivery.deliver_event)(event(incident, got["doc"]), ids)
    except ValueError as exc:
        return {"ok": False, "sent": 0, "failed": 0, "nobody": False, "error": str(exc),
                "words": f"Kept, not sent: {exc}"}
    if out.get("ok") and not out.get("sent"):
        words = ("Kept; the teams chosen have no destination that is verified and on, so "
                 "nothing was sent")
    elif out.get("ok"):
        words = "Sent"
    else:
        words = "Kept, not sent: " + (out.get("error")
                                      or f"{out.get('failed', 0)} destination(s) failed")
    return {"ok": bool(out.get("ok")), "sent": int(out.get("sent") or 0),
            "failed": int(out.get("failed") or 0), "nobody": False,
            "error": out.get("error") or "", "words": words}
