"""Explain's fact sheet (the operator's order of 2026-10-29, C2117 and C2141): a few facts
COMPUTED BY MERCURY from the evidence pack, by code and never by a model, put at the top of what
Explain sends, each line labelled "computed by Mercury" and naming the pack's pieces it is
computed from (those pieces are what an answer cites; the sheet itself is never cited).

**Why:** recorded case 19's "no fault found" (C2141): the switch's heartbeat came every 392 s against its
neighbours' 300 s, a fact the pack held only as one figure per device, left to the model to
compare, or not. A comparison is arithmetic, so Mercury does it.

**From the pack as sent, never a read** (`explain.sent_sections`): the sections the model reads,
so what a class gate withholds stays withheld here too (with no topology sent, only the alert's
device's own figures are sent, and the sheet compares nothing beside them); the roles of the
devices only from the topology sent (*roles*), never a lookup. A line that needs what the pack
does not hold says so, by name.

The lines, in the operator's numbering (his line 3 is not built in this iteration), with the
changes and actions in the window after line 2:

1. **Heartbeat cadence** (`heartbeat_line`, C2117): the alert's device's heartbeats in the
   window (how many, the longest gap and when it ended, the last one received and how long
   before the alert's time), beside the same figures of the devices around it, those of its own
   role first when the topology sent names roles, and its longest gap against their median.
   The pack keeps each device's count, longest gap and last beat, never every receive time,
   and the line says so.
2. **Reloads in the window** (`reloads_line`): each reload or restart log line
   (``%SYS-<n>-RELOAD``, ``%SYS-<n>-RESTART``) and each restart Mercury's restart record holds
   (the device's uptime counter falling) in the window, with whether a Mercury Reload
   ("requested by Mercury's Reload, <who>") or a planned-restart window accounts for it, else
   "no receipt or window: unexplained".
- **Changes and actions in the window** (`changes_line`, the operator's order of 2026-10-29,
  "WHO, guaranteed in code" (a); sent after line 2): each Mercury receipt or record History
  holds in the window (a deploy or restore, a Reload, an intent commit, a golden recorded, a
  planned-restart window), with its action, its actor and how that actor was established, its
  time and its id; each configuration-change log line (``%SYS-5-CONFIG_I`` and its IOS-XE
  forms) with the user and the source it names, IPv4 or IPv6 (`who.config_change`); and the
  Intent check when it differs, its lines' count, the lines whose only difference is a masked
  value, and the intent file's last commit (who, how established, when). Each says "no record
  of who" where the pack holds none (`who.change_of`). The records History holds from before
  the window are counted, the newest named.
4. **Observer health at the alert's time** (`observer_line`): each scrape job of the observer
   section, the alert's own job (its ``job`` label) first: whether it was failing in the
   window's last minute, the most of its targets failing at once (`evidence_observer.at_once`,
   the count the grader's `_across` takes, C2111), how many of its targets failed at all, which
   of the pack's devices failed in it (their scrapes figures name the job), and the targets of
   every job read counted together.
5. **What the pack lacks** (`lacks_line`): each section not read, empty, withheld or not in the
   pack at all (an older schema), and each figure not measured, by name.

**Masked on the way out** (`sheet`): the whole sheet passes `redact.redact_text`, as every
string Mercury shows, before the gateway's own egress mask over the request.

**The request's order** (prompt caching): the sheet is call data, so it rides in the uncached
user turn, its block named ``fact_sheet`` so it sorts first of the data blocks
(`gateway._delimited` sorts them by name); the cached prefix (the prompt and the context) is the
same bytes with or without it.
"""
import logging
import re
import statistics

log = logging.getLogger(__name__)

#: The data block's name: it sorts before every other data block (`gateway._delimited`).
PART = "fact_sheet"
#: Every line's label, and the sheet's own first line.
LABEL = "computed by Mercury"
HEAD = ("Facts computed by Mercury from the pack below, by code, not by a model. Each line is "
        "labelled computed by Mercury and names the pack's pieces it was computed from: cite "
        "those pieces, never this sheet. A line says when the pack lacks what it needs.")
#: A reload or restart the device logged (IOS and IOS-XE: ``%SYS-5-RELOAD: Reload requested
#: by ...``, ``%SYS-5-RESTART: System restarted --``), any severity.
RELOAD_LINE = re.compile(r"%SYS-\d-(?:RELOAD|RESTART)\b")
#: The most a quoted log line keeps, and a section's why.
QUOTE_CHARS = 160
#: The line names, in the order sent (the operator's numbering 1, 2, 4 and 5, and the changes
#: and actions after 2).
LINES = ("heartbeat", "reloads", "changes", "observer", "lacks")
#: The most changes the line names before the window (the newest), the rest counted.
BEFORE_NAMED = 3


def _section(sections, name: str) -> dict:
    return next((s for s in sections or [] if s.get("name") == name), {})


def _epoch(text):
    from modules import alert_history as AH
    return AH.epoch(text)


def _ref(p: dict) -> str:
    return f"[{p.get('ref')}]" if p.get("ref") else ""


def _list(items) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _gap_words(p: dict) -> str:
    """One device's heartbeat in a few words: its longest gap, or why there is none."""
    if p.get("state") == "empty" or (p.get("state") == "ok" and not p.get("beats")):
        return "no beat in the window"
    if p.get("state") != "ok":
        return f"not measured ({p.get('state')})"
    if not p.get("beats"):
        return "no beat in the window"
    if p.get("max_gap_s") is None:
        return f"{p.get('beats')} beat, no gap measured"
    return f"longest gap {p['max_gap_s']} s"


# ── 1. heartbeat cadence (C2117) ───────────────────────────────────────────────────────────

def heartbeat_line(pack: dict, sections: list, roles: dict = None) -> str:
    """The alert's device's heartbeats beside its neighbours' (the module's docstring, line 1).
    *roles*: the topology sent's role of each device by name (none when no topology is sent)."""
    head = f"Heartbeat cadence ({LABEL}): "
    own = pack.get("device") or ""
    health = _section(sections, "health")
    if not own:
        return head + "the alert is not one device's, so no device's heartbeat is compared."
    if not health:
        return head + "this pack holds no health section, so no heartbeat was measured."
    if health.get("state") not in ("ok", "empty"):
        return head + (f"the health section was not read ({health.get('state')}), so no "
                       "heartbeat was measured.")
    beats = [p for p in health.get("pieces") or [] if p.get("figure") == "heartbeat"]
    mine = next((p for p in beats if p.get("device") == own), None)
    if mine is None:
        return head + f"the pack holds no heartbeat figure for {own}."
    window = health.get("window") or {}
    span = (_epoch(window.get("to")) or 0) - (_epoch(window.get("from")) or 0)
    if mine.get("state") not in ("ok", "empty"):
        said = f"{own} {_ref(mine)}: its heartbeat was not measured ({mine.get('state')})"
    elif not mine.get("beats"):
        said = (f"{own} {_ref(mine)}: no heartbeat received in the window's {span:g} s "
                f"({window.get('from', '?')} to {window.get('to', '?')})")
    else:
        said = f"{own} {_ref(mine)}: {mine['beats']} beats in the window's {span:g} s"
        if mine.get("max_gap_s") is not None:
            said += (f", longest gap {mine['max_gap_s']} s ending "
                     f"{mine.get('max_gap_ended_at') or '?'}")
        if mine.get("last_at"):
            said += (f", the last received {mine['last_at']}, {mine.get('since_last_s')} s "
                     "before the alert's time")
    others = [p for p in beats if p.get("device") != own]
    if not others:
        why = (f" ({health['withheld']})" if health.get("withheld") else "")
        return head + said + ". No other device's heartbeat was sent" + why + "."
    role = (roles or {}).get(own) or ((_alert_piece(pack).get("labels") or {}).get("role") or "")
    same = [p for p in others if role and (roles or {}).get(p.get("device")) == role]
    rest = [p for p in others if p not in same]
    groups = []
    if same:
        groups.append(f"of its role ({role}): " + _list(
            [f"{p.get('device')} {_gap_words(p)} {_ref(p)}" for p in same]))
    if rest:
        groups.append(("the others: " if same else "") + _list(
            [f"{p.get('device')} {_gap_words(p)} {_ref(p)}" for p in rest]))
    said += ". Beside it, " + "; ".join(groups)
    if role and not same:
        said += f" (none of these is of its role, {role}, in what was sent)"
    elif not role:
        said += " (no role of these devices was sent, so every device measured is compared)"
    basis = same if same else others
    gaps = [p["max_gap_s"] for p in basis if p.get("state") == "ok"
            and p.get("max_gap_s") is not None]
    if gaps and mine.get("state") == "ok" and mine.get("max_gap_s") is not None:
        median = statistics.median(gaps)
        whose = f"its role's ({role})" if same else "theirs"
        said += (f". {own}'s longest gap, {mine['max_gap_s']} s, against the median of "
                 f"{whose}, {median:g} s over {len(gaps)} device{'s' if len(gaps) != 1 else ''}"
                 + (f": {mine['max_gap_s'] - median:+g} s, {mine['max_gap_s'] / median:.2f} "
                    "times" if median else ""))
    return head + said + (". The pack keeps each device's beat count, longest gap and last "
                          "beat, not every receive time.")


def _alert_piece(pack: dict) -> dict:
    sec = next((s for s in pack.get("sections") or [] if s.get("name") == "alert"), {})
    return (sec.get("pieces") or [{}])[0]


# ── 2. reloads in the window ───────────────────────────────────────────────────────────────

def _window(pack: dict, sections: list) -> tuple:
    """``(start, end)``: from the health figures' window's start (15 minutes before the onset),
    else the log window's, else 15 minutes before the onset; to the pack's own time (as_of)."""
    from modules import evidence_health as H
    start = (_epoch((_section(sections, "health").get("window") or {}).get("from"))
             or _epoch((_section(sections, "logs").get("window") or {}).get("from")))
    if start is None and _epoch(pack.get("onset")) is not None:
        start = _epoch(pack.get("onset")) - H.ONSET_BEFORE_SECONDS
    return start, _epoch(pack.get("built_at"))


def accounted(t, history: dict) -> str:
    """What in the pack's History accounts for a reload or restart at *t* (epoch seconds):
    a Mercury Reload recorded within `restarts.PLANNED_SLACK_SECONDS` of it (a Reload's record
    is written when the device is back, minutes after its reload line); a restart Mercury's
    restart record judged planned within `restarts.SAME_RESTART_SECONDS` (the same restart),
    which a planned-restart window covered; a window declared before it, whose span the pack
    does not hold; else unexplained. History not read is said, never read as nothing."""
    from modules import restarts as R
    if history.get("state") not in ("ok", "empty"):
        return (f"History was not read ({history.get('state') or 'not in the pack'}), so "
                "whether a Reload or a window accounts for it is not known")
    pieces = history.get("pieces") or []

    def near(p, bound):
        at = _epoch(p.get("at"))
        return at is not None and t is not None and abs(at - t) <= bound
    reload = next((p for p in pieces if p.get("kind") == "reload"
                   and near(p, R.PLANNED_SLACK_SECONDS)), None)
    if reload:
        return (f"requested by Mercury's Reload, {reload.get('who') or 'no one recorded'} "
                f"{_ref(reload)}")
    planned = next((p for p in pieces if p.get("kind") == "restart"
                    and p.get("outcome") == "planned" and near(p, R.SAME_RESTART_SECONDS)),
                   None)
    if planned:
        return (f"a planned-restart window accounts for it, {planned.get('who') or 'no one '
                'recorded'} {_ref(planned)}")
    window = next((p for p in pieces if p.get("kind") == "window" and t is not None
                   and (_epoch(p.get("at")) or t + 1) <= t), None)
    if window:
        return (f"a planned-restart window was declared {window.get('at')} by "
                f"{window.get('who') or 'no one recorded'} {_ref(window)}; its span is not in "
                "the pack, so whether it covers this is not computed")
    return "no receipt or window: unexplained"


def reloads_line(pack: dict, sections: list) -> str:
    """Each reload or restart in the window and what accounts for it (line 2)."""
    head = f"Reloads in the window ({LABEL}): "
    start, end = _window(pack, sections)
    logs, history = _section(sections, "logs"), _section(sections, "history")
    events, said = [], []
    if logs.get("state") == "ok":
        for p in logs.get("pieces") or []:
            if RELOAD_LINE.search(p.get("text") or ""):
                events.append((_epoch(p.get("at")), p.get("at"),
                               f"{p.get('device') or 'the device'} logged "
                               f"{(p.get('text') or '')[:QUOTE_CHARS]!r} {_ref(p)}"))
    elif logs.get("state") == "empty":
        said.append("the log lines were read and hold none")
    else:
        said.append(f"the log lines were not read ({logs.get('state') or 'not in the pack'})")
    if history.get("state") == "ok":
        for p in history.get("pieces") or []:
            at = _epoch(p.get("at"))
            if p.get("kind") == "restart" and at is not None and start is not None \
                    and end is not None and start <= at <= end:
                events.append((at, p.get("at"),
                               f"{p.get('what') or 'restarted'}: Mercury's restart record (the "
                               f"uptime counter fell) {_ref(p)}"))
    elif history.get("state") != "empty":
        said.append(f"History was not read ({history.get('state') or 'not in the pack'})")
    if not events:
        n = len(logs.get("pieces") or [])
        none = ("none: no %SYS-5-RELOAD or %SYS-5-RESTART line among the pack's "
                f"{n} log line{'s' if n != 1 else ''}")
        if history.get("state") in ("ok", "empty"):
            none += (", and no restart in History between "
                     f"{_iso(start)} and {_iso(end)}")
        return head + "; ".join([none] + said) + "."
    out = [f"{when}: {what}; {accounted(t, history)}" for t, when, what in sorted(
        events, key=lambda e: (e[0] or 0))]
    return head + "; ".join(out + said) + "."


def _iso(ts) -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts is not None else "?"


# ── changes and actions in the window (the operator's order of 2026-10-29 (a)) ─────────────

def _history_words(c: dict) -> str:
    return (f"{c['at'] or 'an unrecorded time'}: {c['what']} by {c['words']} [{c['ref']}]"
            + (f", record {c['id']}" if c.get("id") else ""))


def _intent_words(piece: dict, c: dict) -> str:
    """The Intent check's difference, its lines' count and those whose only difference is a
    masked value, and who last committed the intent (`who.change_of`'s *c*)."""
    from modules.ai import who

    said = (f"the Intent check differs [{piece.get('ref')}]: {piece.get('adds', 0)} line(s) in "
            f"intent and not on the device (+), {piece.get('removes', 0)} on the device and not "
            f"in intent (-), {piece.get('reordered', 0)} section(s) reordered")
    if "lines" not in piece:
        return said + (". This pack (older than schema 7) holds neither the lines nor who "
                       f"committed the intent: {c['words']}")
    lines = [str(x) for x in piece.get("lines") or []]
    said += f"; {len(lines)} of the lines are in the pack, masked"
    plus = {x[2:] for x in lines if x.startswith("+ ")}
    minus = {x[2:] for x in lines if x.startswith("- ")}
    same = sorted(x for x in plus & minus if "<redacted:" in x)
    if same:
        said += (f"; {len(same)} differ only in a masked value, the same line on both sides "
                 "(" + "; ".join(same[:3]) + ")")
    commit = piece.get("intent_commit") or {}
    if commit.get("state") == "ok":
        by = (f"by {c['who']} ({who.how(commit)})" if c["who"] and who.how(commit)
              else f"by {c['who']}" if c["who"] else who.NO_RECORD)
        said += (f"; intent last committed {commit.get('at') or 'at an unrecorded time'} "
                 f"{by}, commit {commit.get('sha') or '?'}")
    else:
        said += (f"; {c['words']}: "
                 + (commit.get("why") or "the pack holds no commit of the device's intent"))
    return said


def changes_line(pack: dict, sections: list) -> str:
    """Each change or action in the window and who made it (the module's docstring)."""
    from modules.ai import who

    head = f"Changes and actions in the window ({LABEL}): "
    start, end = _window(pack, sections)
    history, logs = _section(sections, "history"), _section(sections, "logs")
    intent = _section(sections, "intent")
    events, before, said = [], [], []
    if history.get("state") == "ok":
        for p in history.get("pieces") or []:
            c = who.change_of("history", p)
            if not c:
                continue
            at = _epoch(p.get("at"))
            if at is not None and start is not None and at < start:
                before.append((at, c))
            elif at is None or end is None or at <= end:
                events.append((at, _history_words(c)))
    elif history.get("state") == "empty":
        said.append("History holds no record of these kinds")
    else:
        said.append(f"History was not read ({history.get('state') or 'not in the pack'}), so "
                    "no receipt or record is known")
    n_logs = len(logs.get("pieces") or [])
    if logs.get("state") == "ok":
        for p in logs.get("pieces") or []:
            c = who.change_of("logs", p)
            if c:
                via = f" from {c['via']}" if c.get("via") else ""
                events.append((_epoch(p.get("at")),
                               f"{p.get('at') or 'an unrecorded time'}: {c['device'] or 'the '
                               'device'} logged a configuration change{via}, by {c['words']} "
                               f"[{c['ref']}]"))
    elif logs.get("state") != "empty":
        said.append(f"the log lines were not read ({logs.get('state') or 'not in the pack'})")
    out = [w for _t, w in sorted(events, key=lambda e: (e[0] or 0))]
    if not out:
        out = [f"none between {_iso(start)} and {_iso(end)}: no Mercury receipt or record in "
               "History, and no configuration-change line (%SYS-5-CONFIG_I) among the pack's "
               f"{n_logs} log line{'s' if n_logs != 1 else ''}"]
    if before:
        before.sort(key=lambda b: b[0], reverse=True)
        out.append(f"before the window, History holds {len(before)} more, the newest "
                   + "; ".join(_history_words(c) for _t, c in before[:BEFORE_NAMED]))
    ipiece = (intent.get("pieces") or [{}])[0] if intent.get("state") == "ok" else {}
    if ipiece.get("state") == "differs":
        out.append(_intent_words(ipiece, who.change_of("intent", ipiece)))
    elif intent and intent.get("state") != "ok":
        said.append(f"the Intent check was not read ({intent.get('state')})")
    return head + "; ".join(out + said) + "."


# ── 4. observer health at the alert's time ─────────────────────────────────────────────────

def observer_line(pack: dict, sections: list) -> str:
    """Each scrape job at the alert's time, the alert's own job first (line 4)."""
    from modules import evidence_health as H
    from modules import evidence_observer as O

    head = f"Observer health at the alert's time ({LABEL}): "
    obs = _section(sections, "observer")
    if not obs:
        from modules import evidence_pack as EP
        return head + (f"this pack holds no observer section (pack schema "
                       f"{EP.schema_of(pack)}, built before the monitoring side was gathered).")
    if obs.get("state") not in ("ok", "empty"):
        return head + f"the observer section was not read ({obs.get('state')})."
    jobs = [p for p in obs.get("pieces") or [] if (p.get("ref") or "").startswith("observer:job:")]
    if not jobs:
        return head + "the observer section holds no scrape job."
    own_job = (_alert_piece(pack).get("labels") or {}).get("job") or ""
    jobs.sort(key=lambda p: (p.get("job") != own_job, p.get("ref")))
    end = _epoch((obs.get("window") or {}).get("to")) or _epoch(pack.get("built_at"))
    scrapes = [p for p in _section(sections, "health").get("pieces") or []
               if p.get("figure") == "scrapes" and p.get("state") == "ok"]
    out, targets, failed = [], 0, 0
    for p in jobs:
        mark = " (the alert's own job)" if own_job and p.get("job") == own_job else ""
        if p.get("state") != "ok":
            out.append(f"{p.get('ref')}{mark}: not measured ({p.get('state')})")
            continue
        n = int(p.get("targets") or 0)
        targets += n
        failed += int(p.get("targets_failed") or 0)
        last = _epoch(p.get("last_failing_at"))
        if p.get("minutes_why"):
            then = f"its minutes were not read ({p['minutes_why'][:QUOTE_CHARS]})"
        elif last is not None and end is not None and last >= end - H.STEP_SECONDS:
            then = "failing in the window's last minute"
        elif last is not None:
            then = (f"not failing at the alert's time: last failing {p['last_failing_at']}, "
                    f"{int(end - last) if end is not None else '?'} s before it")
        else:
            then = "no minute failing in the window"
        words = f"{p.get('ref')}{mark}: {then}"
        if p.get("most_failing"):
            words += (f"; at most {O.at_once(p)} of {p.get('most_failing_of') or n} targets "
                      f"failing at once, at {p.get('most_failing_at')}")
        words += f"; {p.get('targets_failed') or 0} of its {n} targets failed at least once"
        named = [f"{s.get('device')} {_ref(s)}" for s in scrapes
                 if p.get("job") in (s.get("jobs_failing") or [])]
        if named:
            words += "; failing in it among the pack's devices: " + _list(named)
            rest = max(O.at_once(p), int(p.get("targets_failed") or 0)) - len(named)
            if rest > 0:
                words += f" (the other {rest} are not named in the pack)"
        out.append(words)
    total = (f"Across the {len(jobs)} job{'s' if len(jobs) != 1 else ''} read: {failed} of "
             f"{targets} targets failed at least once (counted per job: a device two jobs poll "
             "is two targets).")
    return head + "; ".join(out) + ". " + total


# ── 5. what the pack lacks ─────────────────────────────────────────────────────────────────

def lacks_line(pack: dict, sections: list) -> str:
    """Each section not read, empty, withheld or not in the pack, and each figure not measured
    (line 5)."""
    from modules import evidence_pack as EP
    from modules.ai import explain

    head = f"What the pack lacks ({LABEL}): "
    held = {s.get("name") for s in pack.get("sections") or []}
    out = []
    for name in EP.SECTIONS:
        if name in explain.NOT_SENT:
            continue
        if name not in held:
            out.append(f"{name} ({EP.SECTION_WORDS[name]}): not in this pack (pack schema "
                       f"{EP.schema_of(pack)})")
            continue
        s = _section(sections, name)
        if s.get("withheld"):
            out.append(f"{name}: not sent ({s['withheld'][:QUOTE_CHARS]})")
        elif s.get("state") != "ok":
            why = (s.get("why") or "")[:QUOTE_CHARS]
            out.append(f"{name} ({EP.SECTION_WORDS[name]}): {s.get('state')}"
                       + (f" ({why})" if why else ""))
    figures = {}
    for s in sections:
        if s.get("name") not in EP.PIECES_READ_ON_THEIR_OWN or s.get("state") not in ("ok",
                                                                                      "empty"):
            continue
        for p in s.get("pieces") or []:
            if p.get("state") not in (None, "ok"):
                key = (s.get("name"), p.get("figure") or p.get("what"), p.get("state"))
                figures.setdefault(key, []).append(p.get("device") or p.get("ref") or "?")
    for (sec, what, state), who in sorted(figures.items()):
        out.append(f"{sec} {what} {state} for {_list(who)}" if sec == "health"
                   else f"{sec} {what} {state}")
    if not out:
        return head + "nothing: every section was read and held something, every figure measured."
    return head + "; ".join(out) + "."


# ── the sheet ──────────────────────────────────────────────────────────────────────────────

def lines(pack: dict, sections: list, roles: dict = None) -> list:
    """The sheet's lines, its head first, unmasked (`sheet` masks them)."""
    return [HEAD, heartbeat_line(pack, sections, roles), reloads_line(pack, sections),
            changes_line(pack, sections), observer_line(pack, sections),
            lacks_line(pack, sections)]


def sheet(pack: dict, sections: list, roles: dict = None) -> str:
    """The fact sheet as sent: its lines, one a line, masked on the way out
    (`redact.redact_text`, every string Mercury shows)."""
    from modules import redact
    return redact.redact_text("\n".join(lines(pack, sections, roles)))
