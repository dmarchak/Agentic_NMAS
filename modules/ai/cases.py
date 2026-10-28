"""Recorded cases (PHASE8_PLAN 13.6: every feature's eval set is a versioned dataset; a feature
is done when its about 20 recorded cases pass in CI). A case file
(`tests/fixtures/ai_cases/<task>/<name>.json`) names the `model` its answers were recorded on,
which must be the task's pin (`profiles.cases_off_pin`), and holds cases, each a question, the
answer expected (`expect`), what the catalogue alone cannot settle (`flag`), and once recorded
the model's own answer (`recorded`: its choices, when and on which model).

`misses` judges one result against one case's `expect`, the same way for a live recording and
for CI's replay of it, so a case that passes live passes in CI and the other way round.

Explain's cases (`tests/fixtures/ai_cases/explain/recorded.json`, P1) are replays of a past
window (`scripts/nmas-pack-replay`), each judged on its pack: `explain_unready` says first
whether the pack holds what the case is judged on (an incident's evidence measured, a healthy
baseline's window quiet), so a wrong window fails the check, never the model; then
`explain_misses` judges the model's answer against `expect`, structured fields only. What only
a person can judge in the prose is the case's `flag`, read on the recording.
"""
import calendar
import json
import re
import time


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


#: Every evaluation run is recorded under its run, never as a person (C1784, C1846; PHASE8_PLAN
#: 18.3 rule 9: evaluation runs count against the caps, attributed to their run).
EVALUATION = "evaluation:"
_RUN = re.compile(r"^evaluation:[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")


def evaluation_actor(given: str, script: str, now: float = None) -> tuple:
    """``(actor, refusal)`` for an evaluation script's ``--actor``: none given is
    ``evaluation:<script>-<UTC time>``; one given must read ``evaluation:<run id>``. Anything
    else, a person's address above all, is refused by name, so a measurement is never recorded
    as a person nor counted against one."""
    given = (given or "").strip()
    if not given:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(time.time() if now is None
                                                             else now))
        return f"{EVALUATION}{script}-{stamp}", ""
    if "@" in given:
        return "", (f"--actor {given!r} reads as a person's address; an evaluation is recorded "
                    f"as {EVALUATION}<run id>, never as a person (C1846)")
    if not _RUN.match(given):
        return "", (f"--actor {given!r} is not {EVALUATION}<run id> (letters, digits and . _ : "
                    "-, at most 80); an evaluation is recorded under its run (C1846)")
    return given, ""


def run_network(given: str, declared: str = "") -> tuple:
    """``(network, refusal)`` for an evaluation script's ``--list`` or ``--network`` (C1903):
    *given* through the one resolver (`listref.network_id`), either spelling, and the network
    asked as its display name, the spelling every product path passes (`ListRef.name`), so a
    recording runs the product's own path. A name no network answers to is refused by name;
    so is a case file whose ``network`` (*declared*, its canonical id) is another network
    than the one given, naming both."""
    from modules.nsot import listref

    try:
        nid = listref.network_id(given)
        if declared and listref.network_id(declared) != nid:
            return "", (f"the case file is for the network {declared!r} and --list names "
                        f"{given!r} ({nid}): one network per recording")
        return listref.display_name(nid), ""
    except listref.UnknownList as exc:
        return "", str(exc)


def measure_on(task: str, model: str) -> str:
    """A comparison on another model (PHASE8_PLAN 15.12, the operator, 2026-10-27): *task*'s pin
    replaced in this process alone, never the pin file. ``""`` when done (or *model* is empty),
    else why not."""
    from modules.ai import profiles

    if not model:
        return ""
    if model not in profiles.MODELS:
        return (f"no model profile for {model!r}; known: "
                f"{', '.join(sorted(profiles.MODELS))}")
    if task not in profiles.TASKS:
        return f"no task {task!r} is pinned"
    profiles.TASKS[task] = dict(profiles.TASKS[task], model=model)
    return ""


def _yesterday(now: float) -> tuple:
    day = calendar.timegm(time.gmtime(now)[:3] + (0, 0, 0)) - 86400
    fmt = "%Y-%m-%d %H:%M"
    return time.strftime(fmt, time.gmtime(day)), time.strftime(fmt, time.gmtime(day + 86400))


def stale(data: dict, carried) -> list:
    """The expectations the live catalogue no longer bears out, in words, before any case is
    asked (the operator, 2026-10-25: cases 11, 13 and 15 were all stale expectations; a stale
    one fails this check, not the model). For each case expecting an answer with a metric, at
    least one expected metric must be carried by its named devices, else its role, else the
    network's devices. *carried(kind, value)* answers the metric names for ("devices", [...]),
    ("role", name) or ("all", None), or None when it cannot be read, itself a problem: a check
    that could not look passes nothing."""
    out = []
    for c in data["cases"]:
        e = c["expect"]
        if "answer" not in e.get("outcome", ()) or not e.get("metric"):
            continue
        scope = (("devices", e["devices"]) if e.get("devices")
                 else ("role", e["role"]) if e.get("role") else ("all", None))
        where = {"devices": f"devices {', '.join(e.get('devices') or [])}",
                 "role": f"the {e.get('role')} role",
                 "all": "the network's devices"}[scope[0]]
        names = carried(*scope)
        if names is None:
            out.append(f"case {c['n']}: what {where} carry could not be read")
        elif not set(e["metric"]) & set(names):
            out.append(f"case {c['n']}: none of {', '.join(e['metric'])} is carried by {where}")
    return out


def result_of(choices: dict) -> dict:
    """A recorded answer (`MetricsChoices`, as JSON) as nl_query.metrics says it, without the
    builder's read-back: the outcome and the builder's address. CI replays the model's
    DECISION with this; the read-back against Prometheus's live labels is the recording's."""
    from modules.ai import nl_query

    # Prompt v8's answer carries `needs` (schema v3), v1 to v7's never.
    model = nl_query.MetricsChoicesV3 if "needs" in choices else nl_query.MetricsChoices
    c = model.model_validate_json(json.dumps(choices))
    if c.outcome is nl_query.Outcome.ask:
        return {"ok": False, "error": "ask", "clarify": c.question}
    if c.outcome is nl_query.Outcome.refuse:
        return {"ok": False, "error": "unanswerable", "detail": c.why_not}
    return {"ok": True, "error": "", "values": nl_query.values(c)}


def misses(expect: dict, got: dict, now: float) -> list:
    """What *got* (nl_query.metrics's result) does that *expect* does not allow: ``[]`` is a
    pass. The outcome first: an answer is `ok`, a question back `ask`, a refusal anything else
    the model chose to say (`unanswerable`), and Mercury's own answer to a question no metric
    matches `guide`; any other refusal by Mercury (a cap) is no outcome of the model's and is
    a miss named as it is."""
    error = got.get("error", "")
    # `guide`: Mercury's own answer to a question no metric matches, no model asked (C1700).
    outcome = ("answer" if got.get("ok") else "ask" if error == "ask"
               else "refuse" if error == "unanswerable"
               else "guide" if error == "no_match" and got.get("guide")
               else f"not the model's: {error}")
    out = []
    allowed = list(expect.get("outcome", ()))
    # Mercury's own guidance asks the person to say what they mean, so on a case that expects
    # a question back it is one (the operator, 2026-10-25; ruled after held-out set 1 was
    # seen, C1743).
    if "ask" in allowed and "guide" not in allowed:
        allowed.append("guide")
    if outcome not in allowed:
        return [f"outcome {outcome}, expected one of {expect.get('outcome')}"]
    if outcome != "answer":
        return out
    v = got.get("values") or {}
    if "metric" in expect and v.get("m") not in expect["metric"]:
        out.append(f"metric {v.get('m')!r}, expected one of {expect['metric']}")
    if "devices" in expect and sorted(v.get("dev") or []) != sorted(expect["devices"]):
        out.append(f"devices {v.get('dev')}, expected {expect['devices']}")
    if "role" in expect and (v.get("role") or "") != expect["role"]:
        out.append(f"role {v.get('role')!r}, expected {expect['role']!r}")
    ops = list(v.get("op") or [])
    if "first_op" in expect and (not ops or ops[0].split(":")[0] not in expect["first_op"]):
        out.append(f"first operation {ops[:1]}, expected a kind in {expect['first_op']}")
    for need in expect.get("ops_include", ()):
        if need not in ops:
            out.append(f"operations {ops} lack {need!r}")
    if "group_any" in expect and not any(g in ops for g in expect["group_any"]):
        out.append(f"operations {ops} hold no group of {expect['group_any']}")
    # Never different devices in one line unasked (the operator, 2026-10-25, from case 3's
    # first live answer): a group with no label is one line, a miss unless the case names it.
    from modules.history_promq import AGGS
    one_line = [o for o in ops if o.endswith(":") and o[:-1] in AGGS]
    if (one_line and len(v.get("dev") or []) != 1
            and not set(one_line) & set(expect.get("group_any", ()))):
        out.append(f"operations {ops} put every device into one line ({', '.join(one_line)}), "
                   "which the question did not ask for")
    if "top" in expect and (v.get("top") or "") not in expect["top"]:
        out.append(f"top {v.get('top')!r}, expected one of {expect['top']}")
    if "range" in expect and v.get("range") not in expect["range"]:
        out.append(f"range {v.get('range')!r}, expected one of {expect['range']}")
    if expect.get("yesterday") and (v.get("from"), v.get("to")) != _yesterday(now):
        out.append(f"From {v.get('from')!r} to {v.get('to')!r}, expected yesterday "
                   f"{_yesterday(now)}")
    if expect.get("span"):
        out += _span_misses(expect["span"], v, now)
    return out


def result_of_logs(choices: dict, version: int = None) -> dict:
    """A recorded logs answer (`LogsChoices`, or v3's `LogsChoicesV2`) as nl_query.logs says
    it, without the builder's read-back, as `result_of` is for the metrics half. *version* is
    the logs prompt version it was asked with (none: the live one): from
    `nl_query.CANONICAL_LOGS_FROM`, the answer is read as nl_query.logs reads it, in its
    canonical form, its text matched in any case (C1834); a canonical recording replays as
    itself."""
    from modules.ai import nl_query

    model = nl_query.LogsChoicesV2 if "needs" in choices else nl_query.LogsChoices
    c = model.model_validate_json(json.dumps(choices))
    if c.outcome is nl_query.Outcome.ask:
        return {"ok": False, "error": "ask", "clarify": c.question}
    if c.outcome is nl_query.Outcome.refuse:
        return {"ok": False, "error": "unanswerable", "detail": c.why_not}
    version = nl_query.PROMPT_LOGS[1] if version is None else version
    any_case = version >= nl_query.CANONICAL_LOGS_FROM
    if any_case:
        c = nl_query.canonical_logs(c)
    return {"ok": True, "error": "", "values": nl_query.values_logs(c, any_case=any_case)}


def _text_misses(v: dict, allowed) -> bool:
    """Whether the answer's text is none of *allowed*. A text matched exactly is compared as
    written (Loki's ``|=`` is case-sensitive, so the case is part of the value); a text matched
    in any case (``anycase``, C1834) matches the same lines as any other casing of it, so it
    is compared with each allowed text case-folded. Only the case is folded: a different word,
    or the empty text where a text is expected, still misses."""
    has = v.get("has") or ""
    if v.get("anycase"):
        return has.casefold() not in {a.casefold() for a in allowed}
    return has not in allowed


def logs_misses(expect: dict, got: dict, now: float) -> list:
    """What *got* (nl_query.logs's result) does that *expect* does not allow (C1762, the logs
    half's cases): the outcome first, as `misses`; then, for an answer, the mnemonics one of
    the allowed sets (order aside; ``[]`` none), devices exactly, the role, the text (empty
    when `contains_empty`, else one of `contains`), the severity (``any`` for none), lines or
    counts, what counts are by and their window (counts only), the range and a named span."""
    error = got.get("error", "")
    outcome = ("answer" if got.get("ok") else "ask" if error == "ask"
               else "refuse" if error == "unanswerable" else f"not the model's: {error}")
    if outcome not in expect.get("outcome", ()):
        return [f"outcome {outcome}, expected one of {expect.get('outcome')}"]
    if outcome != "answer":
        return []
    v, out = got.get("values") or {}, []
    if "mnemonics" in expect and sorted(v.get("mn") or []) not in [
            sorted(s) for s in expect["mnemonics"]]:
        out.append(f"mnemonics {v.get('mn')}, expected one of {expect['mnemonics']}")
    if "devices" in expect and sorted(v.get("dev") or []) != sorted(expect["devices"]):
        out.append(f"devices {v.get('dev')}, expected {expect['devices']}")
    if "role" in expect and (v.get("role") or "") != expect["role"]:
        out.append(f"role {v.get('role')!r}, expected {expect['role']!r}")
    if expect.get("contains_empty") and v.get("has"):
        out.append(f"text {v.get('has')!r}, expected none (a mnemonic or severity says it)")
    if "contains" in expect and _text_misses(v, expect["contains"]):
        out.append(f"text {v.get('has')!r}, expected one of {expect['contains']}")
    if "severity" in expect and (v.get("sev") or "any") not in expect["severity"]:
        out.append(f"severity {v.get('sev') or 'any'!r}, expected one of {expect['severity']}")
    if "show" in expect and v.get("show") not in expect["show"]:
        out.append(f"show {v.get('show')!r}, expected one of {expect['show']}")
    if v.get("show") == "counts":
        if "by" in expect and v.get("by") not in expect["by"]:
            out.append(f"counted by {v.get('by')!r}, expected one of {expect['by']}")
        if "every" in expect and v.get("every") not in expect["every"]:
            out.append(f"every {v.get('every')!r}, expected one of {expect['every']}")
    if "range" in expect and v.get("range") not in expect["range"]:
        out.append(f"range {v.get('range')!r}, expected one of {expect['range']}")
    if expect.get("span"):
        out += _span_misses(expect["span"], v, now)
    return out


def stale_logs(data: dict, offered) -> list:
    """The logs cases whose expected mnemonics the evidence no longer holds, before anything
    is asked: *offered(question)* answers the mnemonics the evidence holds for it (the logs
    reader's counts and the platform pack's events; scripts/nmas-nl-cases), or None when they
    cannot be read, itself a problem. A case expecting mnemonics is stale when no allowed set
    is within them. What one prompt version offers is that version's, measured as its misses,
    never a stale case (2026-10-26)."""
    out = []
    for c in data["cases"]:
        e = c["expect"]
        sets = [s for s in e.get("mnemonics", ()) if s]
        if "answer" not in e.get("outcome", ()) or not sets or [] in e.get("mnemonics", ()):
            continue
        names = offered(c["question"])
        if names is None:
            out.append(f"case {c['n']}: what the question is offered could not be read")
        elif not any(set(s) <= set(names) for s in sets):
            out.append(f"case {c['n']}: no expected set of {sets} is offered ({names})")
    return out


#: How far a span that runs to now may end from the recording's own time: the call's data
#: gives now to the minute, read a moment after the recording's clock.
NOW_SLACK_S = 120


def _span_misses(span: str, v: dict, now: float) -> list:
    """A named span (C1740: "yesterday", "this week", "last week") judged as the recorder asks,
    in UTC (it sends no viewer timezone): from the span's start to the next one's, or to now
    within `NOW_SLACK_S`."""
    import datetime as dt

    from modules.ai import nl_query

    s = nl_query.spans(now, dt.timezone.utc)
    end = {"yesterday": s["today"], "last week": s["this week"]}.get(span)
    if v.get("from") != s[span]:
        return [f"From {v.get('from')!r}, expected {span}'s start {s[span]!r}"]
    if end is not None:
        return [] if v.get("to") == end else [f"to {v.get('to')!r}, expected {span}'s end "
                                              f"{end!r}"]
    try:
        to = calendar.timegm(time.strptime(v.get("to") or "", "%Y-%m-%d %H:%M"))
    except ValueError:
        return [f"to {v.get('to')!r}, expected now"]
    return [] if abs(to - now) <= NOW_SLACK_S else [f"to {v.get('to')!r}, expected now"]


def _section(pack: dict, name: str) -> dict:
    return next((s for s in pack.get("sections") or [] if s.get("name") == name), {})


def select(pack: dict, selector: str) -> list:
    """The pack's pieces a case's selector names: ``health:<device name>:<figure>`` (the
    figure's id carries the device's id, which a case cannot know before the pack is built);
    ``concurrent:<device name or address>``, every other alert of that device (C1850), or
    ``concurrent:<device>@<rule>``, that rule's alone (an address may hold colons, so the rule
    follows an ``@``); ``observer:<what>``, the observer's piece of that reference and every one
    under it (``observer:host`` is the host's three, ``observer:job`` every job's; C1896: its
    references are stable names, known before the pack is built); or ``<section>:*``, every
    piece of that section and the section itself."""
    parts = selector.split(":")
    if parts[0] == "observer" and selector != "observer:*":
        return [p for p in _section(pack, "observer").get("pieces") or []
                if p.get("ref") == selector or (p.get("ref") or "").startswith(selector + ":")]
    if parts[0] == "health" and len(parts) == 3:
        return [p for p in _section(pack, "health").get("pieces") or []
                if p.get("device") == parts[1] and p.get("figure") == parts[2]]
    if parts[0] == "concurrent" and selector != "concurrent:*":
        who, _at, rule = selector[len("concurrent:"):].partition("@")
        return [p for p in _section(pack, "concurrent").get("pieces") or []
                if who in (p.get("device"), p.get("address")) and (not rule
                                                                   or p.get("rule") == rule)]
    if len(parts) == 2 and parts[1] == "*":
        s = _section(pack, parts[0])
        return ([s] if s else []) + list(s.get("pieces") or [])
    return []


def _refs(pack: dict, selectors) -> set:
    return {p.get("ref") for sel in selectors for p in select(pack, sel) if p.get("ref")}


_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b)")
#: A percentage as the lines sent write it: one number, or a run of them sharing one sign
#: ("cpu 12/31/57% peak …", min/avg/max), each of the run a percentage.
_PERCENT_RUN = re.compile(r"((?:\d+(?:\.\d+)?/)*\d+(?:\.\d+)?)\s*(?:%|percent\b)")


def _percents(value) -> set:
    """Every percentage a pack holds: the min, avg and max of a piece whose unit is percent,
    and every percentage written in its text (each of a min/avg/max run sharing one sign), at
    any depth. Any other number (a count of scrapes, a gap in seconds) is not one: a stated
    percentage matching it by chance is not allowed."""
    if isinstance(value, str):
        return {float(n) for m in _PERCENT_RUN.finditer(value) for n in m.group(1).split("/")}
    if isinstance(value, list):
        return set().union(*(_percents(v) for v in value)) if value else set()
    if not isinstance(value, dict):
        return set()
    out = set().union(*(_percents(v) for v in value.values())) if value else set()
    if value.get("unit") == "percent":
        # The summary's own figures (evidence_health._summary), never its sample count or hop.
        out |= {float(value[k]) for k in ("min", "avg", "max")
                if isinstance(value.get(k), (int, float)) and not isinstance(value[k], bool)}
    return out


def sections_as_sent(pack: dict) -> list:
    """The pack's sections as the model read them (`explain.as_sent`: the health figures and
    the observer's pieces as one line each, every other section as stored); a section that
    already holds its `lines` is one as sent (a pack rebuilt from a request), its pieces
    dropped."""
    from modules.ai import explain

    return [{k: v for k, v in s.items() if k != "pieces"} if "lines" in s
            else explain.as_sent(s) for s in pack.get("sections") or []]


def invented_percents(text: str, pack: dict) -> list:
    """The percentages *text* states that are not a percentage the pack holds as sent
    (exactly, or rounded to the precision the text writes): a figure stated that is not in the
    evidence (the operator's rule, 2026-10-25: "never invent a figure"). Only percentages are
    checked. Judged against the lines the model read, not the stored pieces' fields (the
    operator, 2026-10-28: an observer line's "usual 24% on 4 CPUs" is a percentage sent,
    though its piece's field carries no unit)."""
    held = _percents(sections_as_sent(pack))
    out = []
    for m in _PERCENT.finditer(text or ""):
        said = m.group(1)
        places = len(said.split(".")[1]) if "." in said else 0
        if not any(round(h, places) == float(said) for h in held):
            out.append(said + "%")
    return out


def explain_unready(case: dict, pack: dict) -> list:
    """Why *pack* cannot judge *case*, in words; ``[]`` when it can. Every selector in
    `needs` must name a piece that was measured (state ok); a `quiet` case (a healthy
    baseline) must show none of the symptoms it names anywhere in its health figures or its
    log lines, else the window was not healthy and the case is not one."""
    from modules import evidence_pack as EP

    def read(p):
        # Whether it was read is its section's state (a health figure's own, C1761); a piece's
        # own `state` may be what it describes (another alert's "firing", C1850).
        return (EP.read_state(pack, p.get("ref")) if p.get("ref") else "") or p.get("state",
                                                                                   "ok")

    out = []
    if not _section(pack, "health"):
        out.append("the pack holds no health section (built before C1714)")
    for sel in case.get("needs", ()):
        got = select(pack, sel)
        if not got:
            out.append(f"{sel}: not in the pack")
        elif not any(read(p) == "ok" for p in got):
            out.append(f"{sel}: not measured ({got[0].get('state')}: {got[0].get('why', '')})")
    alone = case.get("alone")
    if alone:
        for p in _section(pack, "health").get("pieces") or []:
            if p.get("device") == alone["device"] or p.get("state") != "ok":
                continue
            if p.get("figure") == "scrapes" and p.get("failed"):
                out.append(f"not alone: {p['device']} failed {p['failed']} scrape(s) too")
            if p.get("figure") == "heartbeat" and (p.get("max_gap_s") or 0) > alone["max_gap_s"]:
                out.append(f"not alone: {p['device']}'s longest heartbeat gap was "
                           f"{p['max_gap_s']} s, over {alone['max_gap_s']} s")
    quiet = case.get("quiet")
    if quiet:
        for p in _section(pack, "health").get("pieces") or []:
            if p.get("state") != "ok":
                continue
            if p.get("figure") == "scrapes" and (p.get("failed") or 0) > quiet["failed_scrapes"]:
                out.append(f"not quiet: {p['device']} failed {p['failed']} scrape(s)")
            if (p.get("figure") == "heartbeat"
                    and (p.get("max_gap_s") or 0) > quiet["max_gap_s"]):
                out.append(f"not quiet: {p['device']}'s longest heartbeat gap was "
                           f"{p['max_gap_s']} s, over {quiet['max_gap_s']} s")
        for p in _section(pack, "logs").get("pieces") or []:
            hit = [w for w in quiet.get("no_log_text", ()) if w in (p.get("text") or "")]
            if hit:
                out.append(f"not quiet: a log line at {p.get('at')} holds {hit[0]}")
    return out


def _across(h: dict, figured: set, by_alert: dict, pack: dict) -> int:
    """How many devices one hypothesis's cross-device evidence spans (`common`; the operator,
    2026-10-28): the devices whose named figures it cites (*figured*) together with the devices
    whose other alerts it cites (C1850), or, when more, the targets an observer job it cites was
    failing on at once (C1896: the job's most failing together, else its targets that failed)."""
    refs = set(h.get("evidence_refs") or [])
    named = len(figured | {by_alert[r] for r in refs if r in by_alert})
    jobs = [p for p in _section(pack, "observer").get("pieces") or []
            if p.get("ref") in refs and (p.get("ref") or "").startswith("observer:job:")
            and p.get("state", "ok") == "ok"]
    at_once = [p.get("most_failing", p.get("targets_failed")) or 0 for p in jobs]
    return max([named] + at_once)


def _reasoning(expect: dict, hyps: list, pack: dict) -> list:
    """What *hyps* lack of one line of reasoning: `cites` (each group cited somewhere),
    `together` (one hypothesis citing each group), and `common` (one hypothesis citing
    cross-device evidence of at least `min_devices` devices: a cause shared beneath them); and
    what they do that `no_common` forbids (a hypothesis resting on that many devices'
    figures)."""
    out = []
    cited = {r for h in hyps for r in h.get("evidence_refs") or []}
    for group in expect.get("cites", ()):
        if not cited & _refs(pack, group):
            out.append(f"cites none of {group}")
    for together in expect.get("together", ()):
        wanted = [_refs(pack, g) for g in together]
        if not any(all(set(h.get("evidence_refs") or []) & w for w in wanted) for h in hyps):
            out.append(f"no one hypothesis cites each of {together}")
    by_ref = {p.get("ref"): p for p in _section(pack, "health").get("pieces") or []}
    by_alert = {p.get("ref"): (p.get("device") or p.get("address"))
                for p in _section(pack, "concurrent").get("pieces") or []}

    def devices(h, figures):
        return {by_ref[r]["device"] for r in h.get("evidence_refs") or []
                if r in by_ref and by_ref[r].get("figure") in figures}
    common = expect.get("common")
    if common and not any(_across(h, devices(h, common["figures"]), by_alert, pack)
                          >= common["min_devices"] for h in hyps):
        out.append(f"no one hypothesis cites {' or '.join(common['figures'])} figures, other "
                   f"alerts or a failing observer job of {common['min_devices']} or more "
                   "devices")
    # A cause shared beneath several devices, cited by their alerts in the window (C1850, the
    # pack's `concurrent` section): one hypothesis citing other alerts of that many devices.
    alerts = expect.get("common_alerts")
    if alerts:
        if not any(len({by_alert[r] for r in h.get("evidence_refs") or [] if r in by_alert})
                   >= alerts["min_devices"] for h in hyps):
            out.append(f"no one hypothesis cites other alerts of {alerts['min_devices']} or "
                       "more devices")
    # The control's other side: where one device alone shows the symptom, a cause shared
    # beneath several is not the evidence's (Explain v5's proof, the operator, 2026-10-26).
    alone = expect.get("no_common")
    if alone:
        wide = [i for i, h in enumerate(hyps, 1)
                if len(devices(h, alone["figures"])) >= alone["min_devices"]]
        if wide:
            out.append(f"hypothesis {wide[0]} rests on {' or '.join(alone['figures'])} figures "
                       f"of {alone['min_devices']} or more devices, where one device alone "
                       "shows the symptom")
    return out


def explain_misses(expect: dict, answer, pack: dict, error: str = "") -> list:
    """What Explain's answer (*answer*, the model's `Explanation` as JSON; None with *error*
    when Mercury refused it, a couldn't analyse) does that *expect* does not allow: ``[]`` is a
    pass. Structured fields only; the prose is the case's `flag`, a person's to judge."""
    if answer is None:
        return [f"no answer: {error or 'nothing recorded'}"]
    out = []
    outcome = answer.get("outcome")
    if outcome not in expect.get("outcome", ()):
        return [f"outcome {outcome}, expected one of {expect.get('outcome')}"]
    hyps = answer.get("hypotheses") or []
    out += _person(expect, answer)
    out += _hypotheses_max(expect, hyps)
    checked = set(answer.get("checked") or [])
    for group in expect.get("checked", ()):
        if not checked & _refs(pack, group):
            out.append(f"checked none of {group}")
    # Evidence the answer rests on, wherever the prompt puts it (the operator, 2026-10-28, case
    # 12): an answer cites it in a hypothesis; no fault found lists it in `checked`, which the
    # prompt keeps for evidence read and found healthy.
    cited = {r for h in hyps for r in h.get("evidence_refs") or []}
    for group in expect.get("cites_or_checked", ()):
        if not (cited | checked) & _refs(pack, group):
            out.append(f"cites or checks none of {group}")
    out += _reasoning(expect, hyps, pack)
    # Any one of several acceptable lines of reasoning (the operator, 2026-10-25, on C1547:
    # a common cause beneath every device is better than one pinned on a single switch): the
    # first that holds passes; when none does, each says what it lacked. A line may also ask
    # its own `needs_human` and `says_any` (the operator, 2026-10-28: cases 8 and 19's honest
    # "insufficient evidence").
    alternatives = expect.get("one_of") or ()
    if alternatives:
        lacks = [(a.get("name") or f"line {i}",
                  _person(a, answer) + _reasoning(a, hyps, pack) + _says(a, hyps))
                 for i, a in enumerate(alternatives, 1)]
        if all(why for _n, why in lacks):
            out.append("none of the accepted lines of reasoning: " + "; ".join(
                f"{n}: {', '.join(why)}" for n, why in lacks))
    # The leading hypothesis's own evidence (C1896, case 21): it cites at least one piece of
    # each group, so the cause ranked first rests on that evidence, not a later hypothesis.
    for group in expect.get("lead_cites", ()):
        lead = set(hyps[0].get("evidence_refs") or []) if hyps else set()
        if not lead & _refs(pack, group):
            out.append(f"the leading hypothesis cites none of {group}")
    if hyps and expect.get("lead_not_only"):
        lead = set(hyps[0].get("evidence_refs") or [])
        if lead and lead <= _refs(pack, expect["lead_not_only"]):
            out.append(f"the leading hypothesis rests on {expect['lead_not_only']} alone")
    text = " ".join([answer.get("rationale") or "", answer.get("why_not") or ""]
                    + [h.get("claim") or "" for h in hyps])
    if expect.get("figures_from_pack"):
        bad = invented_percents(text, pack)
        if bad:
            out.append(f"states {', '.join(bad)}, which the pack does not hold")
    # The clock-skew case (the operator, 2026-10-26): a switch whose clock is far off stamps
    # its log lines with its own wrong time; an answer that names that time as when something
    # happened blames the wrong window. `no_text` names what the answer must never say.
    said = [w for w in expect.get("no_text", ()) if w.lower() in text.lower()]
    if said:
        out.append(f"says {said[0]!r}, which the case rules out ("
                   f"{expect.get('no_text_why') or 'not the evidence'})")
    return out + _says(expect, hyps)


def _person(expect: dict, answer: dict) -> list:
    if "needs_human" in expect and bool(answer.get("needs_human")) != expect["needs_human"]:
        return [f"needs_human {answer.get('needs_human')}, expected {expect['needs_human']}"]
    return []


#: How a hypothesis's claim says it is not in the evidence (prompt v4's edge-of-evidence rule:
#: "say in the claim that it is not in the evidence"; the schema has no field for it, so the
#: claim's words are the mark), in the forms the recorded answers write it.
_UNEVIDENCED = re.compile(
    r"\bnot (?:directly )?(?:in|shown (?:by|in)|supported by|evidenced (?:by|in)) the "
    r"(?:evidence|pack)\b|\bnot (?:directly )?evidenced\b|\bunevidenced\b"
    r"|\b(?:pack|evidence) does not show\b", re.I)


def unevidenced(h: dict) -> bool:
    """Whether hypothesis *h*'s claim says it is not in the evidence (`_UNEVIDENCED`)."""
    return bool(_UNEVIDENCED.search(h.get("claim") or ""))


def _hypotheses_max(expect: dict, hyps: list) -> list:
    """At most `hypotheses_max` hypotheses; with `unevidenced_extra` (the operator,
    2026-10-28, case 11), that many more may stand, each ranked after them and its claim
    saying it is not in the evidence, while the leading one rests on the evidence (its claim
    saying no such thing): the top-ranked hypothesis is the one graded."""
    if "hypotheses_max" not in expect:
        return []
    most, extra = expect["hypotheses_max"], expect.get("unevidenced_extra", 0)
    if len(hyps) <= most:
        return []
    if not extra or not most or len(hyps) > most + extra:
        return [f"{len(hyps)} hypotheses, at most {most} expected "
                "(a healthy window reports nothing wrong)"]
    out = []
    if unevidenced(hyps[0]):
        out.append("the leading hypothesis says it is not in the evidence, and a cause the "
                   "evidence holds is ranked after it")
    later = [i for i, h in enumerate(hyps[most:], most + 1) if not unevidenced(h)]
    if later:
        out.append(f"hypothesis {later[0]} is past the {most} expected and its claim does not "
                   "say it is not in the evidence")
    return out


def _says(expect: dict, hyps: list) -> list:
    """The clock-drift cases (the operator's correction, 2026-10-26: a switch's heartbeat alert
    is its clock at 0.703 of real time stretching the 300 s watchdog, not no fault): a cause the
    pack does not hold can only be a hypothesis, so `says_any` asks that a hypothesis's claim or
    its confirming read names it, in any of the words given, each from a word's start; with
    `unevidenced`, that hypothesis's claim also says it is not in the evidence (the operator,
    2026-10-28: cases 8 and 19's heartbeat source)."""
    words = expect.get("says_any") or ()
    if not words:
        return []
    said = [re.compile(r"\b" + re.escape(w.lower())) for w in words]

    def names(h):
        text = ((h.get("claim") or "") + " " + (h.get("confirm_with") or "")).lower()
        return any(w.search(text) for w in said)
    if any(names(h) and (not expect.get("unevidenced") or unevidenced(h)) for h in hyps):
        return []
    mark = ", its claim saying it is not in the evidence," if expect.get("unevidenced") else ""
    return [f"no hypothesis names {' or '.join(words)}{mark} ("
            f"{expect.get('says_why') or 'the evidence'})"]


# ── feature 7: an intent change in words (tests/fixtures/ai_cases/intent_patch/) ──

#: What `intent_words.change` answered, in a case's words: the model's draft previewed
#: ("answer"), one question back ("ask"), a refusal of the change ("refuse"), a draft refused
#: by Mercury after the model answered, by the scope check, the patch's rules or the intent
#: ("refused_after"), Mercury's own question about which interface a reference means, with
#: no call ("choose", part 1), or Mercury's own answer with no call ("mercury").
MERCURY_ERRORS = ("empty", "too_long", "no_device", "nothing_named", "no_intent",
                  "no_such_interface", "unbalanced_quote", "placeholder_in_words", "not_an_answer",
                  "not_an_operation", "two_ended", "alternatives", "no_area", "no_value")
#: Mercury's own question before any call (`intent_names.questions`): judged also as a
#: question back ("ask"), because a case's "ask" means the words leave a choice only the
#: person can make, and who asks it (Mercury, with no call, or the model) is cost, not
#: correctness (the operator's order of 2026-10-27, item b).
MERCURY_ASKS = ("two_ended", "alternatives", "no_area", "no_value")
#: Mercury's own refusal of a change no operation makes (`intent_words.not_an_operation`):
#: judged also as a refusal ("refuse"), for the same reason.
MERCURY_REFUSES = ("not_an_operation",)


def intent_outcome(got: dict) -> str:
    if got.get("ok"):
        return "answer"
    error = got.get("error") or ""
    if error in ("ask", "choose"):
        return error
    if error == "unanswerable":
        return "refuse"
    if error in ("couldnt_change", "intent", "ends_mismatch"):
        return "refused_after"
    if error in MERCURY_ERRORS:
        return "mercury"
    return error or "none"


def intent_ops(choices: dict) -> list:
    """The draft's operations from the model's own answer (`choices`), each with only the
    fields its op uses, in the case file's shape (interface canonical, area as its number)."""
    from modules.ai.intent_words import FIELDS, Op
    from modules.nsot import ifnames
    from modules.nsot.features import area_number

    out = []
    for patch in (choices or {}).get("patches") or []:
        for o in patch.get("operations") or []:
            name = o.get("op")
            op = {"op": name}
            fields = FIELDS[Op(name)] if name in {m.value for m in Op} else ()
            for f in fields:
                value = o.get(f)
                if f == "interface":
                    value = ifnames.canonical(str(value or ""))
                if f == "area":
                    value = str(area_number(value)) if area_number(value) is not None else value
                op["name" if f == "vlan_name" else f] = value
            out.append(op)
    return out


def _op_key(op: dict) -> tuple:
    from modules.nsot.features import area_number
    o = dict(op)
    if "area" in o and area_number(o["area"]) is not None:
        o["area"] = str(area_number(o["area"]))
    return tuple(sorted((k, str(v)) for k, v in o.items()))


def intent_misses(expect: dict, got: dict) -> list:
    """What *got* (`intent_words.change`'s answer) does that *expect* does not allow: ``[]``
    is a pass. The outcome must be one the case allows; where the case names what an outcome
    says (``said``: outcome to words), its detail must hold those words, so a refusal for
    another reason misses; an answer's operations must be exactly the expected ones, order
    aside. Mercury's own question (`MERCURY_ASKS`) or refusal (`MERCURY_REFUSES`) is read as
    "mercury" and also as "ask" or "refuse": it passes when either reading does."""
    outcome = intent_outcome(got)
    why = got.get("detail") or got.get("error") or ""
    error = got.get("error") or ""
    readings = [outcome] + (["ask"] if outcome == "mercury" and error in MERCURY_ASKS else
                            ["refuse"] if outcome == "mercury" and error in MERCURY_REFUSES
                            else [])
    missed = []
    for reading in readings:
        if reading not in expect["outcome"]:
            missed.append(f"outcome {outcome}" + (f" (read as {reading})" if reading != outcome
                                                  else "")
                          + f", expected one of {expect['outcome']}"
                          + (f" ({why[:160]})" if why else ""))
            continue
        said = (expect.get("said") or {}).get(reading)
        if said and said not in why:
            missed.append(f"outcome {reading} says {why[:160]!r}, expected it to say {said!r}")
            continue
        outcome = reading
        missed = []
        break
    if missed:
        return missed[:1]
    if outcome != "answer":
        return []
    if "patches" in expect:
        # A two-device draft (C1908): each device's operations exactly, and no other device.
        have_by = intent_patches(got.get("choices"))
        out = []
        for host in sorted(set(expect["patches"]) | set(have_by)):
            want = sorted(_op_key(o) for o in expect["patches"].get(host, []))
            have = sorted(_op_key(o) for o in have_by.get(host, []))
            if want != have:
                out.append(f"{host}'s operations {[dict(k) for k in have]}, expected "
                           f"{[dict(k) for k in want]}")
        return out[:1]
    if "ops" not in expect:
        return []
    want = sorted(_op_key(o) for o in expect["ops"])
    have = sorted(_op_key(o) for o in intent_ops(got.get("choices")))
    if want == have:
        return []
    return [f"operations {[dict(k) for k in have]}, expected {[dict(k) for k in want]}"]


def intent_patches(choices: dict) -> dict:
    """``{hostname: operations}`` of the model's answer, each as `intent_ops` gives it."""
    out = {}
    for patch in (choices or {}).get("patches") or []:
        out.setdefault(str(patch.get("hostname") or ""), []).extend(
            intent_ops({"patches": [patch]}))
    return out


# ── classify_threat's cases (PHASE8_PLAN 17.1 S7; tests/fixtures/ai_cases/sdn_classify/) ────

def sdn_outcome(got: dict) -> str:
    """``answer`` when the classification passed Mercury's check; ``refused by the check``
    when the model answered and the check refused it (a miss of the model's); anything else
    is no outcome of the model's, named (a refusal before the call fails the run twice:
    TESTING.md, "A run refused before it was sent fails twice")."""
    if got.get("ok"):
        return "answer"
    error = got.get("error") or ""
    if error == "couldnt_classify":
        return "refused by the check"
    return f"not the model's: {error or 'no answer'}"


def sdn_compared(got: dict) -> str:
    """The fields a run is compared on for consistency (PHASE8_PLAN 6's Decision-maker row:
    the entry, its parameters and its evidence ids; never the prose): the outcome, whether a
    threat was found and its kind, the action, the source or flow it acts on, and the evidence
    ids cited as a set."""
    outcome = sdn_outcome(got)
    if outcome != "answer":
        return json.dumps([outcome])
    c = got["classification"]
    return json.dumps([outcome, c["threat_detected"], c["threat_type"], got["action"],
                       got["params"].get("source", ""), c["parameters"].get("flow", "")
                       if got["action"] == "remove_flow" else "",
                       sorted(set(c["evidence_refs"]))])


def sdn_classify_misses(expect: dict, got: dict) -> list:
    """What *got* (`closed_loop.classify_pack`'s answer) does that the case's *expect* does
    not allow: ``[]`` is a pass. The answer must pass Mercury's check; then whether it finds a
    threat, its kind, its severity and its action must each be one the case allows; a source
    the action acts on must be the expected one (compared in canonical form), and a removed
    flow the expected one; at least one id it cites must be one the detection rests on."""
    import ipaddress

    outcome = sdn_outcome(got)
    if outcome != "answer":
        why = got.get("detail") or ""
        return [f"outcome {outcome}" + (f" ({why[:200]})" if why else "")]
    c, action = got["classification"], got["action"]
    out = []
    if c["threat_detected"] is not expect["threat_detected"]:
        out.append(f"threat_detected {c['threat_detected']}, expected {expect['threat_detected']}")
    for field in ("threat_type", "severity"):
        if c[field] not in expect[field]:
            out.append(f"{field} {c[field]}, expected one of {expect[field]}")
    if action not in expect["action_id"]:
        out.append(f"action {action}, expected one of {expect['action_id']}")
    if expect.get("source") and action in ("drop_source", "rate_limit_source"):
        want = ipaddress.ip_address(expect["source"]).compressed
        if got["params"].get("source") != want:
            out.append(f"source {got['params'].get('source')!r}, expected {want}")
    if expect.get("flow") and action == "remove_flow" \
            and c["parameters"].get("flow") != expect["flow"]:
        out.append(f"flow {c['parameters'].get('flow')!r}, expected {expect['flow']}")
    if not set(c["evidence_refs"]) & set(expect["cites_any"]):
        out.append(f"cites {c['evidence_refs'][:3]}, none of the evidence the detection rests "
                   "on")
    return out
