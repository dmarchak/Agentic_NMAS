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

**What it does not hold, said so it is not read as held:** an incident folded into another
is not a row of its own (its page redirects to the one it joined; the count is said); an
alert incident (``al-``) and an SDN incident (``resp-``) are not listed until their pages land
(board T, part 3).
"""

import logging
import os
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
CLOSED_GROUPS = (("fixed_mercury", "Fixed by Mercury", "ok"),
                 ("fixed_person", "Fixed by a person", "ok"),
                 ("fixed", "Fixed, who is not recorded", "ok"),
                 ("cleared", "Cleared", "muted"),
                 ("cancelled", "Declined", "muted"))
#: What a row hands the template, each drawn (the grouping keys stay in Python).
DRAWN = ("id", "device", "href", "title", "state", "state_words", "kind", "waits", "since",
         "ended", "ttr", "by", "drill")
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
    from modules.fixit import section

    try:
        return section.view(network, found)["state"]
    except Exception as exc:                            # noqa: BLE001 (a row still draws)
        log.warning("incidents list: %s's troubleshooting of %s cannot be read (%s)",
                    network, found.get("id"), type(exc).__name__)
        return ""


def _group(st: dict, tl: dict) -> str:
    """The row's group key: an OPEN_GROUPS key while it is not resolved, else a
    CLOSED_GROUPS key."""
    if st["state"] == "needs_person":
        return "needs_person"
    if st["state"] == "open":
        return "working" if st["why"] in WORKING else "watching"
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
    fixit = (_fixit_state(network, found)
             if heal not in IP.RESOLVED and found["id"] in fixit_ids else "")
    st = IP.status(inc, entry, decisions, fixit)
    tl = IP.timeline(inc, entry, decisions)
    resolved = st["state"] in IP.RESOLVED
    who = tl["who"]
    by = ((identity.display_name(who["actor"]) if who["actor"] else "a person not recorded")
          if who["kind"] == "person" else "Mercury" if who["kind"] == "none" else "")
    return {"id": found["id"], "device": device,
            # THE incident's address (`incident_href`); "" for one that names no device, whose
            # row then says its id and links nowhere.
            "href": incidents.incident_href(network, found["id"], device=device),
            "title": IP.title(inc, entry, decisions, st["state"], who),
            "state": st["state"], "state_words": st["words"], "why": st["why"],
            "kind": STATE_KINDS.get(st["state"], "muted"),
            "group": _group(st, tl), "resolved": resolved,
            "waits": "" if resolved else WAITS.get(st["why"], ""),
            "since": tl["detected"]["at"] or (inc or {}).get("opened_at")
            or entry.get("first_at") or "",
            "ended": tl["ended"] if resolved else "",
            "ttr": tl["ttr"]["words"] if st["state"] == "fixed" else "",
            "by": by if st["state"] == "fixed" else "",
            "drill": IP.drill_of(found), "only_log": not inc}


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


def _matches(row: dict, q: str, device: str) -> bool:
    if device and row["device"] != device:
        return False
    if not q:
        return True
    hay = " ".join((row["title"], row["device"], row["id"])).lower()
    return all(word in hay for word in q.lower().split())


def page(network: str, tab: str = "open", q: str = "", device: str = "") -> dict:
    """What `templates/v2/incidents.html` draws: ``{"network", "tab", "tabs", "q", "device",
    "devices", "summary", "groups", "shown", "matched", "folded", "unreadable", "kept",
    "read_at"}``. *tabs* is each tab's count; *summary* the tab's counts by group, in words;
    *groups* each non-empty group of the matched rows, with at most `SHOWN` rows and the
    rest counted; *devices* the devices the tab's rows name (the filter's choices)."""
    from modules import display_names
    from modules.heal import incidents, steplog

    tab = tab if tab in TABS else "open"
    q = " ".join(str(q or "").split())[:QUERY_CHARS]
    device = str(device or "").strip()[:128]
    got = rows(network)
    on_tab = [r for r in got["rows"] if r["resolved"] == (tab == "closed")]
    matched = [r for r in on_tab if _matches(r, q, device)]
    groups_of = OPEN_GROUPS if tab == "open" else CLOSED_GROUPS
    counts = {k: sum(1 for r in on_tab if r["group"] == k) for k, _w, _d in groups_of}
    groups = []
    for key, words, kind in groups_of:
        members = [r for r in matched if r["group"] == key]
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
             "unreadable": got["unreadable"], "kept": incidents.CLOSED_KEPT,
             "read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    return display_names.people_payload(steplog.masked(model))


#: The sidebar's Self-healing chip: the mode that runs now (`heal.policy.current`'s ``mode``,
#: after the kill switch, the confirmation, the expiry and the stage guard), in the board's
#: words (Off / Dry run / Auto).
MODE_CHIP = {"off": "Off", "dry_run": "Dry run", "auto": "Auto"}


def heal_mode(network: str) -> dict:
    """``{"mode", "words", "why"}``: *network*'s self-healing mode as it runs now, its chip's
    word, and the policy's own sentence for the hover (`policy.current`'s ``words``). A policy
    that cannot be read is Off, as `current` reads it."""
    from modules.heal import policy

    cur = policy.current(network)
    mode = cur["mode"] if cur["mode"] in MODE_CHIP else "off"
    return {"mode": mode, "words": MODE_CHIP[mode], "why": str(cur.get("words") or "")}


def open_count(network: str) -> dict:
    """The sidebar's Incidents chip: ``{"n", "ok"}``, the open incidents of *network* (the
    Open tab's count), from the same three reads and the same incidents (`_found`); *ok* False
    when a store could not be read (the chip then says so, never a count that may be short).
    Whether an incident is resolved is `incident_page.state_of`'s answer alone (`status` says
    RESOLVED exactly when it does; troubleshooting only moves an unresolved one between
    needing a person and Mercury working), so no troubleshooting record is read here."""
    from modules import incident_page as IP
    from modules.heal import decisions as HD
    from modules.heal import incidents, steplog

    got, entries = incidents.read(network), steplog.incidents(network)
    ok = got["state"] != "unreadable" and entries["state"] != "unreadable"
    try:
        decided = HD.decisions(network)
    except RuntimeError:
        decided, ok = [], False
    found, _folded = _found(got["incidents"], entries["entries"], decided)
    n = sum(1 for f in found
            if IP.state_of(f["incident"], f["entry"], f["decisions"]) not in IP.RESOLVED)
    return {"n": n, "ok": ok}
