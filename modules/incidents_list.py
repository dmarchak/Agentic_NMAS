"""The incidents list, Troubleshooting › Incidents (`/v2/incidents`; board T, the sidebar's
Troubleshooting section, ~/Documents/nmas-reports/boards/troubleshooting-nav.html, part 2's
Incidents card and part 4's wireframe; the GUI review's proposal 17 and its finding IN9: the
incident's own home). Provisional, operator review pending (the operator, 2026-11-13: "GUI
boards: approved provisionally for initial implementation and testing").

**What it draws, for one network:** every incident its self-healing holds, in two tabs:
- **Open:** each incident a person or Mercury still has to finish (`incident_page.RESOLVED`
  says which are not), grouped by what it waits for: **Needs a person**, **Mercury working**
  (a heal applying, or a fix a person approved running or passed), **Watching** (Mercury
  reading it, before its decision). A summary line first, counts by group.
- **Closed:** how each one ended: **Fixed by Mercury** (no person took part), **Fixed by a
  person** (a person approved the fix), **Fixed** (who is not recorded), **Cleared** (closed
  with no repair), **Declined** (a person declined the fix), each row with its end and its
  TIME TO REPAIR.
The board's Problems tab is "suggested" and has no page yet: it is not drawn.

**Each row** is the incident's own page's words: its title from THE title builder
(`incident_page.title`, through `said.title`), its state from THE state function
(`incident_page.status`), its times from its timeline (`incident_page.timeline`), a drill
said as a drill (`incident_page.drill_of`), and its link from the one place an incident's
address is built (`incidents.incident_href`). Nothing is worded a second time but the one
short "what it waits for" line an open row carries (`WAITS`).

**Page speed** (CLAUDE.md, "No page load or badge poll waits on…"): one read of each of the
network's own heal stores the background writes (the incidents, the step log, the decisions),
whatever the number of incidents; every row is computed from those three reads. The one
further read: an open incident a person has troubleshot has a troubleshooting record
(`fixit/<id>.json`, found by ONE listing of its folder), and its state is part of the page's
one state (`status`), so that record's section state is read for those incidents alone (an
incident nobody troubleshot has no record and no attempt: an attempt is a run its proposal's
record line started). Nothing here reaches a device, Grafana, Loki or NetBox, and nothing is
written.

**Large fleets** (CLAUDE.md, "Built for large fleets"): a summary first, groups that are
`<details>`, open only while the tab holds at most `OPEN_UNDER` rows, each group drawing at
most `SHOWN` rows and counting the rest, a search over title, device and id, and a device
filter. 900 incidents draw no long expanded list.

**The top bar's Self-healing chip** (`heal_auto`; the operator, 2026-11-14): drawn only while
some network's self-healing runs in Auto. The sidebar is navigation only, so neither
Incidents nor Self-healing carries a chip there; Needs attention's badge is the one count.

**What it does not hold, said so it is not read as held:** an incident folded into another
is not a row of its own (its page redirects to the one it joined; the count is said); an
alert incident (``al-``) and an SDN incident (``resp-``) are not listed until their pages land
(board T, part 3).
"""

import copy
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

#: The list's tabs, in order, each with its label (the board's suggested Problems tab has no
#: page yet).
TABS = {"open": "Open", "closed": "Closed"}
#: Rows a group draws before it counts the rest.
SHOWN = 50
#: A tab with at most this many rows draws its groups open; more, and every group is closed.
OPEN_UNDER = 25
#: Longest search text kept from the address.
QUERY_CHARS = 80
#: The Open tab's groups, in order: (key, words, its state's dot kind).
OPEN_GROUPS = (("needs_person", "Needs a person", "danger"),
               ("working", "Mercury working", "info"),
               ("watching", "Watching", "warn"))
#: The Closed tab's groups, in order.
CLOSED_GROUPS = (("fixed_ai", "Fixed by AI", "ok"),
                 ("fixed_script", "Fixed by Mercury: saved script", "ok"),
                 ("fixed_mercury", "Fixed by Mercury", "ok"),
                 ("fixed_person", "Fixed by a person", "ok"),
                 ("fixed", "Fixed, who is not recorded", "ok"),
                 ("cleared", "Cleared", "muted"),
                 ("cancelled", "Declined", "muted"))
#: What a row hands the template, each drawn (the grouping keys stay in Python).
DRAWN = ("id", "device", "href", "title", "state", "state_words", "kind", "waits", "since",
         "ended", "ttr", "by", "drill", "acknowledged", "ai", "impact", "status", "busy",
         "fixed_words")
#: A state's badge kind, as the incident's own page colours its state.
STATE_KINDS = {"needs_person": "danger", "open": "info", "fixed": "ok", "cleared": "muted",
               "cancelled": "muted"}
#: The `status` whys in which Mercury, or a fix a person approved, is working now.
WORKING = ("healing", "attempt_running", "attempt_passed")
#: What an open row waits for, one short line per `incident_page.WHYS` an open incident can
#: have (its page says it in full under What to do).
WAITS = {"healing": "Mercury is fixing it now",
         "attempt_running": "a fix a person approved is running",
         "attempt_passed": "its fix passed; it closes when its symptom clears",
         "watching": "Mercury is reading it, before it decides",
         "verify_failed": "its fix's verify failed",
         "proposal": "a fix waits for a person's approval",
         "decided": "Mercury decided, and it waits for a person",
         "lost_stream": "its fix changes the configuration, so a person approves it",
         "attempt_stopped": "a fix a person ran did not fix it",
         "fix_proposed": "a fix is proposed under AI troubleshooting",
         "troubleshooting_cancelled": "its troubleshooting was cancelled",
         "handed_over": "it was handed over"}


def _fixit_ids(network: str) -> set:
    """The incidents with a troubleshooting record, by ONE listing of its folder; none when
    the folder is absent or cannot be listed (a record that cannot be listed draws the
    incident by its own records, said by the page's note)."""
    from modules.config import list_data_path
    from modules.fixit import incident as F

    folder = os.path.join(list_data_path(network), F.STORE_DIR)
    try:
        return {n[:-5] for n in os.listdir(folder) if n.endswith(".json")}
    except FileNotFoundError:
        return set()
    except OSError as exc:
        log.warning("incidents list: %s's troubleshooting records cannot be listed (%s)",
                    network, type(exc).__name__)
        return set()


def _fixit_state(network: str, found: dict) -> str:
    """The incident's troubleshooting section state (`fixit.section.view`), as its page asks
    it for its one state; "" when it cannot be read (the incident's own records then say)."""
    return _fixit_of(network, found)["state"]


#: Gate 2 (the operator, 2026-11-15): what a row says of the AI's investigation.
AI_STATES = ("investigating", "ended")


def _fixit_of(network: str, found: dict) -> dict:
    """``{"state", "ai"}``: the incident's troubleshooting section state (`fixit.section.view`,
    "" when it cannot be read) and what its rows say of the AI (Gate 2): ``{"state":
    "investigating", "since", "words"}`` while an investigation runs (*since* its start line's
    time), ``{"state": "ended", "since", "words"}`` once one ended (*words* the section's own
    one-line status: what it found, or why it stopped), or None when the AI never started on
    it. From the section's view and the incident's start lines: a read of its records."""
    from modules.fixit import incident as F
    from modules.fixit import section

    try:
        v = section.view(network, found)
    except Exception as exc:                            # noqa: BLE001 (a row still draws)
        log.warning("incidents list: %s's troubleshooting of %s cannot be read (%s)",
                    network, found.get("id"), type(exc).__name__)
        return {"state": "", "ai": None, "plan": False}
    ai = None
    try:
        inc = section.incident_of(network, found)["incident"]
        starts = [s for s in (F.starts(inc)["starts"] if inc is not None else [])
                  if s.get("state") in ("started", "failed")]
    except Exception as exc:                            # noqa: BLE001 (the row says nothing)
        log.warning("incidents list: %s's AI starts of %s cannot be read (%s)", network,
                    found.get("id"), type(exc).__name__)
        starts = []
    if starts:
        last = starts[-1]
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(last.get("epoch") or 0)))
        if v.get("state") == "investigating":
            ai = {"state": "investigating", "since": since, "words": "AI investigating"}
        else:
            ai = {"state": "ended", "since": since,
                  "words": v.get("status") or "The AI's investigation ended"}
    # Whether a plan stands to approve: a proposal line with no plan (an answer that named no
    # fix, a gap) is the section's "proposed" too, and must never be said as one to approve.
    return {"state": v.get("state") or "", "ai": ai, "plan": bool(v.get("proposal")),
            "working": " · ".join(w for w in (v.get("working"), v.get("working_step")) if w)}


def _group(st: dict, tl: dict, how: dict = None) -> str:
    """The row's group key: an OPEN_GROUPS key while it is not resolved, else a
    CLOSED_GROUPS key; a close on a verified run its kind's (`incident_page.fixed_how`)."""
    if st["state"] == "needs_person":
        return "needs_person"
    if st["state"] == "open":
        return "working" if st["why"] in WORKING else "watching"
    if st["state"] == "fixed" and how:
        return how["group"]
    if st["state"] == "fixed":
        return {"none": "fixed_mercury", "person": "fixed_person"}.get(tl["who"]["kind"],
                                                                        "fixed")
    return st["state"]


def _row(network: str, found: dict, fixit_ids: set) -> dict:
    """One incident's row, from its own records and THE functions its page draws by."""
    from modules import identity
    from modules import incident_page as IP
    from modules.heal import incidents

    inc, entry, decisions = found["incident"], found["entry"], found["decisions"]
    device = (inc or {}).get("device") or entry.get("device") or ""
    heal = IP.state_of(inc, entry, decisions)
    fx = (_fixit_of(network, found) if heal not in IP.RESOLVED and found["id"] in fixit_ids
          else {"state": "", "ai": None, "plan": False})
    fixit = fx["state"]
    st = IP.status(inc, entry, decisions, fixit)
    tl = IP.timeline(inc, entry, decisions, network)
    resolved = st["state"] in IP.RESOLVED
    how = IP.fixed_how(network, inc) if st["state"] == "fixed" else {}
    if not resolved and not fx.get("working"):
        # A saved script running on an incident with no troubleshooting record of its own (the
        # heal decision fired it): Mercury working all the same (the operator, 2026-11-16).
        from modules.nsot import saved_plans
        run = saved_plans.running_on(network, found["id"])
        if run:
            e = saved_plans.script_for(network, found)[0] or {}
            fx = dict(fx, working=(f"Self-healing: fixing with saved script "
                                   f"{e.get('name') or ''} · {run['step']}"))
    who = tl["who"]
    by = ((identity.display_name(who["actor"]) if who["actor"] else "a person not recorded")
          if who["kind"] == "person" else "Mercury" if who["kind"] == "none" else "")
    out = {"id": found["id"], "device": device,
            # THE incident's address (`incident_href`); "" for one that names no device, whose
            # row then says its id and links nowhere.
            "href": incidents.incident_href(network, found["id"], device=device),
            "title": IP.title(inc, entry, decisions, st["state"], who),
            "state": st["state"], "state_words": st["words"], "why": st["why"],
            "kind": STATE_KINDS.get(st["state"], "muted"),
            # Mercury working on it now (a saved script's run, an AI investigation): that group,
            # its status the live step (the operator, 2026-11-15).
            "group": "working" if fx.get("working") else _group(st, tl, how),
            "resolved": resolved, "busy": bool(fx.get("working")),
            "waits": "" if resolved else WAITS.get(st["why"], ""),
            # R5 (board R5, approved 2026-11-15): the row's status line, what it waits for in
            # one line ("Waiting for a person: …" while it needs one), "" once resolved.
            "status": "" if resolved else (fx.get("working") or status_words(
                st["state"], WAITS.get(st["why"], ""))),
            "since": tl["detected"]["at"] or (inc or {}).get("opened_at")
            or entry.get("first_at") or "",
            "ended": tl["ended"] if resolved else "",
            "ttr": tl["ttr"]["words"] if st["state"] == "fixed" else "",
            "by": by if st["state"] == "fixed" and not how else "",
            # Who fixed it, for a close on a verified run (an AI plan, a saved script).
            "fixed_words": how.get("words", "") if how else "",
            "drill": IP.drill_of(found), "only_log": not inc,
            # The Needs attention rows about it, by the ids an acknowledgement is keyed on
            # (C3701): its own row (a can't-fix, or the incident's row, keyed by its id) and a
            # hold keyed by one of its decisions.
            "ack_ids": [f"heal:{found['id']}"] + [f"heal:{d['id']}" for d in decisions
                                                  if d.get("id")],
            "acknowledged": "",
            # R2 (the operator, 2026-11-14): its bottom line, from Mercury's own table.
            # The builder's finding (the operator, 2026-11-15): an answer with no plan names the
            # next step, never "approve, modify or deny the plan".
            "bluf": bluf_of(found, NO_PLAN if st["why"] == "fix_proposed" and not fx["plan"]
                            else st["why"]),
            # Gate 2 (the operator, 2026-11-15): "AI investigating" with its start while an
            # investigation runs, its one-line outcome once it ended (`_fixit_of`); redrawn
            # when the job announces its start and end (`troubleshoot_job`, ``drift``).
            "ai": fx["ai"]}
    # R5: the row's impact line, its BLUF's (Mercury's own table).
    out["impact"] = out["bluf"].get("impact") or ""
    return out


def status_words(state: str, waits: str) -> str:
    """An open incident's status line (board R5): what it waits for (`WAITS`), "Waiting for a
    person: " before it while a person is needed, its first letter capital; "" with nothing to
    say."""
    if not waits:
        return "Waiting for a person" if state == "needs_person" else ""
    if state == "needs_person":
        return f"Waiting for a person: {waits}"
    return waits[:1].upper() + waits[1:]


#: The next action a Needs attention row about an incident names, by why its page says it
#: needs a person (`incident_page.status`): the BLUF's fix (`modules/bluf.py`'s kinds) and its
#: label. Anything else is the table's own kind for the incident.
#: Why for an incident the AI answered with no plan (its section "proposed", nothing to approve).
NO_PLAN = "ai_answered_no_plan"
NEXT_BY_WHY = {"fix_proposed": ("approve", "Open the incident: approve, modify or deny the plan"),
               NO_PLAN: ("button", "Open the incident: see what the AI found, then ask it "
                                   "again or hand it over"),
               "proposal": ("approve", "Open the incident: approve or decline the proposal"),
               "proposal_denied": ("button", "Open the incident: ask the AI again, or hand it "
                                             "over"),
               "ai_capped": ("hand_over", "Open the incident and hand it over"),
               "attempt_stopped": ("button", "Open the incident: ask the AI again, or hand it "
                                             "over"),
               "handed_over": ("hand_over", "Open the incident"),
               "ai_investigating": ("none", "Open the incident: the AI is investigating")}


def bluf_of(found: dict, why: str) -> dict:
    """The incident's BLUF (`bluf.bluf`): ``{"what", "impact", "fix", "severity"}``, its fix the
    next action its *why* names (`NEXT_BY_WHY`), else the table's own kind for it."""
    from modules import bluf as B

    kind, label = NEXT_BY_WHY.get(why, ("", ""))
    nxt = {"kind": kind, "label": label} if kind else None
    got = B.bluf(B.model_of(found, nxt))
    if not got["fix"].get("label"):
        got["fix"] = dict(got["fix"], label="Open the incident and decide what to do")
    return got


def rows(network: str) -> dict:
    """Every incident of *network*, newest first, each `_row`: ``{"rows", "folded",
    "unreadable"}``. *folded* counts the closed incidents folded into another (not rows of
    their own); *unreadable* names each store that could not be read. ONE read of each store."""
    from modules.heal import decisions as HD
    from modules.heal import incidents, steplog

    unreadable = []
    got = incidents.read(network)
    if got["state"] == "unreadable":
        unreadable.append(got["error"])
    entries = steplog.incidents(network)
    if entries["state"] == "unreadable":
        unreadable.append(f"{network}'s heal step log cannot be read: {entries['error']}")
    try:
        decided = HD.decisions(network)
    except RuntimeError as exc:
        decided = []
        unreadable.append(str(exc))
    found, folded = _found(got["incidents"], entries["entries"], decided)
    fixit_ids = _fixit_ids(network)
    out = [_row(network, f, fixit_ids) for f in found]
    out.sort(key=lambda r: r["since"] or "", reverse=True)
    return {"rows": out, "folded": folded, "unreadable": unreadable}


#: How long a held list is drawn before it is read again with nothing announced (C3788): the
#: list's own states move with time too (an investigation past its bound, a cap's day), so a
#: held list never outlives this. 30 s, the attention store's fastest viewed cadence.
HOLD_S = 30.0
#: The list as last computed, by network: ``(generation, monotonic, epoch, value)``.
_held = {}
_held_lock = threading.Lock()


def held(network: str) -> dict:
    """`rows` for *network* as last computed, held (the operator, 2026-11-15, C3788: the
    Incidents page computed its list per request, 8 to 10 s on the host): the held value while
    nothing has changed since it was computed (`invalidation.generation`: every announcement and
    every mutating route's declared change moves it) and for at most `HOLD_S`; else `rows`
    computed now and held. Needs attention's background recompute computes it too
    (`attention._incidents_listed`), so the page usually finds it held. A copy for the caller,
    with ``held_at`` (epoch seconds) when it was computed."""
    from modules import attention_store, invalidation

    now = time.monotonic()
    gen = invalidation.generation()
    with _held_lock:
        h = _held.get(network)
    # A test session computes on every read, as Needs attention's store does
    # (`attention_store.COMPUTE_ON_READ`: a test writes a store and reads the page again).
    if h is not None and h[0] == gen and now - h[1] < HOLD_S \
            and not attention_store.COMPUTE_ON_READ:
        return dict(copy.deepcopy(h[3]), held_at=h[2])
    got = rows(network)
    with _held_lock:
        _held[network] = (gen, now, time.time(), got)
    return dict(copy.deepcopy(got), held_at=time.time())


def hold(network: str, value: dict, generation: int) -> None:
    """Hold *value* (`rows`' answer, computed while `invalidation.generation` was
    *generation*) for `held`: the attention store's recompute hands its own list here, so the
    Incidents page reads it rather than computing it again."""
    with _held_lock:
        _held[network] = (generation, time.monotonic(), time.time(), copy.deepcopy(value))


def _found(held: list, entries: list, decided: list) -> tuple:
    """Each listed incident as `incident_page.resolve` finds one (``{"id", "incident",
    "entry", "decisions", "advisories"}``), from the three stores' rows as read once, and how
    many closed ones were folded into another (not listed: their page redirects). An incident
    past the newest closed ones its store keeps is found by its step log alone, as its page
    is."""
    from modules import incident_page as IP

    by_entry = {e.get("incident"): e for e in entries if e.get("incident")}
    by_decision = {}
    for d in decided:
        by_decision.setdefault(d.get("incident") or "", []).append(d)
    out, folded, seen = [], 0, set()
    for inc in held:
        iid = str(inc.get("id") or "")
        if not IP.HI.match(iid):
            continue
        seen.add(iid)
        if inc.get("state") == "closed" and inc.get("folded_into"):
            folded += 1
            continue
        out.append({"id": iid, "incident": inc, "entry": by_entry.get(iid) or {},
                    "decisions": by_decision.get(iid) or [], "advisories": []})
    for iid, entry in by_entry.items():
        if iid not in seen and IP.HI.match(str(iid)):
            out.append({"id": iid, "incident": None, "entry": entry,
                        "decisions": by_decision.get(iid) or [], "advisories": []})
    return out, folded


def _acknowledged(open_rows: list) -> None:
    """C3701 (the operator, 2026-11-14: "acknowledged ones shown as acknowledged on both"): each
    open incident whose Needs attention row a person acknowledged says so, with who and why,
    from the acknowledgements in force (`acknowledgements.current`, the record Needs attention
    hides its acknowledged rows by), matched by the row ids `_row` names (``ack_ids``). One
    read of the record. An acknowledgement of another source's row (a Grafana alert's) is not
    matched to an incident here: it is keyed on the alert, not the incident. A record that
    cannot be read marks nothing (Needs attention says it cannot be read)."""
    from modules import acknowledgements as ACK
    from modules import identity

    if not open_rows:
        return
    try:
        got = ACK.read()
        held = [] if got["state"] == "unreadable" else ACK.current(got["rows"])
    except Exception as exc:                        # noqa: BLE001 (marks nothing)
        log.warning("incidents: the acknowledgements could not be read: %s", exc)
        return
    by_id = {}
    for a in reversed(held):                       # the newest of a row's first
        by_id.setdefault(str(a.get("row") or ""), a)
    for r in open_rows:
        a = next((by_id[i] for i in r.get("ack_ids") or () if i in by_id), None)
        if a:
            who = identity.display_name(a.get("by") or "") or "a person"
            r["acknowledged"] = f"Acknowledged by {who}: {a.get('why') or 'no reason given'}"


def _matches(row: dict, q: str, device: str) -> bool:
    if device and row["device"] != device:
        return False
    if not q:
        return True
    hay = " ".join((row["title"], row["device"], row["id"])).lower()
    return all(word in hay for word in q.lower().split())


def page(network: str, tab: str = "open", q: str = "", device: str = "",
         batched=()) -> dict:
    """What `templates/v2/incidents.html` draws: ``{"network", "tab", "tabs", "q", "device",
    "devices", "summary", "groups", "shown", "matched", "folded", "unreadable", "kept",
    "read_at"}``. *tabs* is each tab's count; *summary* the tab's counts by group, in words;
    *groups* each non-empty group of the matched rows, with at most `SHOWN` rows and the
    rest counted; *devices* the devices the tab's rows name (the filter's choices).
    *batched* are the incidents a batch card above the list holds (board R5, the operator's
    change 1, 2026-11-15: its problems inside it, "not as rows below"): counted in the tab and
    its summary, drawn in no group while no search or filter is applied."""
    from modules import display_names
    from modules.heal import incidents, steplog

    tab = tab if tab in TABS else "open"
    q = " ".join(str(q or "").split())[:QUERY_CHARS]
    device = str(device or "").strip()[:128]
    got = held(network)
    on_tab = [r for r in got["rows"] if r["resolved"] == (tab == "closed")]
    if tab == "open":
        _acknowledged(on_tab)
    matched = [r for r in on_tab if _matches(r, q, device)]
    groups_of = OPEN_GROUPS if tab == "open" else CLOSED_GROUPS
    counts = {k: sum(1 for r in on_tab if r["group"] == k) for k, _w, _d in groups_of}
    held_in_card = set(batched or ()) if tab == "open" and not (q or device) else set()
    groups = []
    for key, words, kind in groups_of:
        members = [r for r in matched if r["group"] == key and r["id"] not in held_in_card]
        if members:
            groups.append({"key": key, "words": words, "kind": kind, "n": len(members),
                           "rows": [{k: r[k] for k in DRAWN} for r in members[:SHOWN]],
                           "more": max(0, len(members) - SHOWN),
                           "open": len(matched) <= OPEN_UNDER})
    summary = [f"{counts[k]} {w[:1].lower() + w[1:]}".replace(" mercury", " Mercury")
               for k, w, _d in groups_of if counts[k]]
    model = {"network": network, "tab": tab,
             "tabs": [{"key": t, "words": TABS[t],
                       "n": sum(1 for r in got["rows"] if r["resolved"] == (t == "closed"))}
                      for t in TABS],
             "q": q, "device": device,
             "devices": sorted({r["device"] for r in on_tab if r["device"]}),
             "total": len(on_tab), "summary": summary, "groups": groups,
             "matched": len(matched), "folded": got["folded"],
             "in_card": sum(1 for r in matched if r["id"] in held_in_card),
             "unreadable": got["unreadable"], "kept": incidents.CLOSED_KEPT,
             # When the list drawn was computed (it is held, C3788), not when it was drawn.
             "read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                      time.gmtime(got.get("held_at") or time.time()))}
    return display_names.people_payload(steplog.masked(model))


#: The longest wait the top bar's chip schedules for its one re-read at Auto's expiry (htmx's
#: ``load delay``): a week, the longest Auto the Self-healing tab offers (its quick choices,
#: docs/UI_RULES.md "A time limit is never a typed UTC string"); a later expiry is re-read
#: then, and again at each announcement.
REREAD_MAX_S = 7 * 86400


def heal_auto(now: float = None) -> dict:
    """The top bar's Self-healing chip (the operator, 2026-11-14: "a status chip in the top bar
    beside the AI chip, shown only while Auto is in force: amber "Self-healing: Auto until
    <local time>", opening Settings › Self-healing. Nothing in the normal state"):
    ``{"on", "network", "until", "n", "networks", "reread_s"}``. *on* is whether any network's
    self-healing runs in Auto NOW, read from the policy itself (`heal.policy.current`'s
    ``mode``, after the installation's stop switch, the confirmation, the expiry and the stage
    guard), never from the stored setting; *network* and *until* are the Auto whose expiry
    comes first, *n* how many networks are in Auto, *networks* their names in expiry order, and
    *reread_s* the seconds until that first expiry (the chip reads itself again then, once).
    A policy that cannot be read is not Auto (`current` reads it as off, and Needs attention
    says it cannot be read). One read of the stop switch for every network."""
    from modules import integration_groups
    from modules.heal import policy

    now = time.time() if now is None else float(now)
    kill = policy.stopped()
    auto = []
    for net in integration_groups.network_names():
        cur = policy.current(net, now, kill=kill)
        if cur["mode"] != "auto":
            continue
        try:
            ends = policy.parse_until(cur["until"])
        except policy.PolicyRefused:
            # `current` read it as Auto in force only before a parseable expiry; kept safe.
            ends = now
        auto.append((ends, net, str(cur["until"] or "")))
    auto.sort()
    # C3748: the chip also shows while AI troubleshooting starts by itself on a network (its
    # switch, `fixit.auto.switch`), and opens Needs attention's control strip.
    from modules.fixit import auto as A
    ai = []
    for net in integration_groups.network_names():
        try:
            if A.switch(net)["on"]:
                ai.append(net)
        except Exception as exc:                      # noqa: BLE001 (the strip says it)
            # The chip is drawn by exception only; a switch that cannot be read is said on
            # the network's control strip ("cannot be read"), never drawn here as on.
            log.info("incidents: %s's AI troubleshooting switch could not be read (%s)",
                     net, type(exc).__name__)
    if not auto:
        return {"on": bool(ai), "auto": False, "network": ai[0] if ai else "", "until": "",
                "n": 0, "networks": [], "reread_s": 0, "ai": ai}
    ends, net, until = auto[0]
    return {"on": True, "auto": True, "network": net, "until": until, "n": len(auto),
            "networks": [a[1] for a in auto], "ai": ai,
            "reread_s": int(min(max(ends - now, 0), REREAD_MAX_S)) + 1}
