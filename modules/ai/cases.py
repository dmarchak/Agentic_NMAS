"""Recorded cases (PHASE8_PLAN 13.6: every feature's eval set is a versioned dataset; a feature
is done when its about 20 recorded cases pass in CI). A case file
(`tests/fixtures/ai_cases/<task>/<name>.json`) names the `model` its answers were recorded on,
which must be the task's pin (`profiles.cases_off_pin`), and holds cases, each a question, the
answer expected (`expect`), what the catalogue alone cannot settle (`flag`), and once recorded
the model's own answer (`recorded`: its choices, when and on which model).

`misses` judges one result against one case's `expect`, the same way for a live recording and
for CI's replay of it, so a case that passes live passes in CI and the other way round.
"""
import calendar
import json
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
    if outcome not in expect.get("outcome", ()):
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
    return out
