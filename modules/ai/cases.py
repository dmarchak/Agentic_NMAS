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

    c = nl_query.MetricsChoices.model_validate_json(json.dumps(choices))
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
    figure's id carries the device's id, which a case cannot know before the pack is built), or
    ``<section>:*``, every piece of that section and the section itself."""
    parts = selector.split(":")
    if parts[0] == "health" and len(parts) == 3:
        return [p for p in _section(pack, "health").get("pieces") or []
                if p.get("device") == parts[1] and p.get("figure") == parts[2]]
    if len(parts) == 2 and parts[1] == "*":
        s = _section(pack, parts[0])
        return ([s] if s else []) + list(s.get("pieces") or [])
    return []


def _refs(pack: dict, selectors) -> set:
    return {p.get("ref") for sel in selectors for p in select(pack, sel) if p.get("ref")}


_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b)")


def _percents(value) -> set:
    """Every percentage a pack holds: the min, avg and max of a piece whose unit is percent,
    and every percentage written in its text, at any depth. Any other number (a count of
    scrapes, a gap in seconds) is not one: a stated percentage matching it by chance is not
    allowed."""
    if isinstance(value, str):
        return {float(m.group(1)) for m in _PERCENT.finditer(value)}
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


def invented_percents(text: str, pack: dict) -> list:
    """The percentages *text* states that are not a percentage the pack holds (exactly, or
    rounded to the precision the text writes): a figure stated that is not in the evidence
    (the operator's rule, 2026-10-25: "never invent a figure"). Only percentages are checked."""
    held = _percents(pack)
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
    out = []
    if not _section(pack, "health"):
        out.append("the pack holds no health section (built before C1714)")
    for sel in case.get("needs", ()):
        got = select(pack, sel)
        if not got:
            out.append(f"{sel}: not in the pack")
        elif not any(p.get("state", "ok") == "ok" for p in got):
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


def _reasoning(expect: dict, hyps: list, pack: dict) -> list:
    """What *hyps* lack of one line of reasoning: `cites` (each group cited somewhere),
    `together` (one hypothesis citing each group), and `common` (one hypothesis citing the
    named figures of at least `min_devices` devices: a cause shared beneath them); and what
    they do that `no_common` forbids (a hypothesis resting on that many devices' figures)."""
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

    def devices(h, figures):
        return {by_ref[r]["device"] for r in h.get("evidence_refs") or []
                if r in by_ref and by_ref[r].get("figure") in figures}
    common = expect.get("common")
    if common and not any(len(devices(h, common["figures"])) >= common["min_devices"]
                          for h in hyps):
        out.append(f"no one hypothesis cites {' or '.join(common['figures'])} figures of "
                   f"{common['min_devices']} or more devices")
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
    if "needs_human" in expect and bool(answer.get("needs_human")) != expect["needs_human"]:
        out.append(f"needs_human {answer.get('needs_human')}, expected {expect['needs_human']}")
    if "hypotheses_max" in expect and len(hyps) > expect["hypotheses_max"]:
        out.append(f"{len(hyps)} hypotheses, at most {expect['hypotheses_max']} expected "
                   "(a healthy window reports nothing wrong)")
    checked = set(answer.get("checked") or [])
    for group in expect.get("checked", ()):
        if not checked & _refs(pack, group):
            out.append(f"checked none of {group}")
    out += _reasoning(expect, hyps, pack)
    # Any one of several acceptable lines of reasoning (the operator, 2026-10-25, on C1547:
    # a common cause beneath every device is better than one pinned on a single switch): the
    # first that holds passes; when none does, each says what it lacked.
    alternatives = expect.get("one_of") or ()
    if alternatives:
        lacks = [(a.get("name") or f"line {i}", _reasoning(a, hyps, pack))
                 for i, a in enumerate(alternatives, 1)]
        if all(why for _n, why in lacks):
            out.append("none of the accepted lines of reasoning: " + "; ".join(
                f"{n}: {', '.join(why)}" for n, why in lacks))
    if hyps and expect.get("lead_not_only"):
        lead = set(hyps[0].get("evidence_refs") or [])
        if lead and lead <= _refs(pack, expect["lead_not_only"]):
            out.append(f"the leading hypothesis rests on {expect['lead_not_only']} alone")
    if expect.get("figures_from_pack"):
        text = " ".join([answer.get("rationale") or "", answer.get("why_not") or ""]
                        + [h.get("claim") or "" for h in hyps])
        bad = invented_percents(text, pack)
        if bad:
            out.append(f"states {', '.join(bad)}, which the pack does not hold")
    return out


# ── feature 7: an intent change in words (tests/fixtures/ai_cases/intent_patch/) ──

#: What `intent_words.change` answered, in a case's words: the model's draft previewed
#: ("answer"), one question back ("ask"), a refusal of the change ("refuse"), a draft refused
#: by Mercury after the model answered, by the scope check, the patch's rules or the intent
#: ("refused_after"), or Mercury's own answer with no call ("mercury").
MERCURY_ERRORS = ("empty", "too_long", "no_device", "nothing_named", "no_intent")


def intent_outcome(got: dict) -> str:
    if got.get("ok"):
        return "answer"
    error = got.get("error") or ""
    if error == "ask":
        return "ask"
    if error == "unanswerable":
        return "refuse"
    if error in ("couldnt_change", "intent"):
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
    aside."""
    outcome = intent_outcome(got)
    why = got.get("detail") or got.get("error") or ""
    if outcome not in expect["outcome"]:
        return [f"outcome {outcome}, expected one of {expect['outcome']}"
                + (f" ({why[:160]})" if why else "")]
    said = (expect.get("said") or {}).get(outcome)
    if said and said not in why:
        return [f"outcome {outcome} says {why[:160]!r}, expected it to say {said!r}"]
    if outcome != "answer" or "ops" not in expect:
        return []
    want = sorted(_op_key(o) for o in expect["ops"])
    have = sorted(_op_key(o) for o in intent_ops(got.get("choices")))
    if want == have:
        return []
    return [f"operations {[dict(k) for k in have]}, expected {[dict(k) for k in want]}"]
