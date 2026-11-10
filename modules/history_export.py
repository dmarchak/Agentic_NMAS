"""History › Export (Lab 9 B5; board H of docs/boards/lab9-sdn.html, self-signed 2026-11-10):
the records History already keeps, downloaded for a report as CSV or JSON, masked as History
masks them. Two logs, each for one network or every network, over a range of whole UTC days:

**The call and cost log** (`calls`): every AI call the gateway recorded in the range
(modules/ai/calls.py, the ledger ``ai_calls``), one row each: when, the feature, the trigger
(a person's press with who, a background job with its job, an evaluation with its run), the
model, the prompt and its version, the tokens in and out, the cache's write and read, the
dollars, the latency, the verdict and what it means (`OUTCOMES`), and the call's History link.
Then a total per UTC day and per feature. The dollars are the ledger's own ``cost_usd`` per
call, summed by UTC day from the rows read now, never carried forward from an earlier total.

**The false-positive and failure log** (`failures`): where the AI layer was wrong or the
network's automation failed, and what was done about it, one row each with its record's link,
from each source in `FAILURE_SOURCES`:
- each SDN detection a person dismissed, with the reason and who (`loop.responses_record`);
- each AI classification the check refused (the proposed response's refused call);
- each response AUTO decided on and sent nothing for, a protected-flow refusal named as one;
- each SDN flow operation whose Verify failed or whose controller refused a request, and what
  its rollback achieved (`flow_intent.operations`);
- each evaluation call that classified a collection no rule fired on as a threat: a false
  positive by `scripts/nmas-sdn-classify-normal`'s own definition (the ledger's rows);
- each planted issue each SDN analysis in the range missed, B1's and the trace tool's
  (`sdn.analyst.sheets`, C2945), one row per issue per analysis;
- from the network's record of SDN evaluation runs (`sdn.evaluations`): each detection a
  false-positive run (B3, `scripts/nmas-sdn-false-positives`, C2946) found on traffic a person
  declared normal, and each B4 evaluation run (`scripts/nmas-sdn-b4-eval`, C2943) that missed
  its case's planted issue, kept a false-positive finding, or answered a benign case as a
  threat, per technique;
- each AI answer a person said was wrong (Was this right? No, `ai.feedback`), with its review.
The other evaluation scripts' per-case misses (``nmas-sdn-cases`` and the other ``*-cases``
scripts) are written only to their own report (``--out``), never to a store Mercury reads, so
they are not here; each file says so (`NOT_RECORDED`). The sdn_classify normal-traffic runs'
false positives are complete from the ledger: each call keeps its collection as its subject and
its answer's ``threat_detected``, which is the run's own definition of one.

**Bounded:** a range is at most `MAX_DAYS` whole UTC days, refused naming its length; a file
lists at most `MAX_ROWS` rows and says how many it left out, its totals still every row's.
**Reads only:** nothing is written, and no device, controller or model is asked anything.
Every text a row carries is masked on the way out (`_masked`, `redact.redact_text`), as
History masks what it draws.
"""

import collections
import csv
import datetime
import io
import json
import logging
import time
from urllib.parse import urlencode

log = logging.getLogger(__name__)

#: The longest range a log covers, in whole UTC days (a month: a lab's or a report's period).
MAX_DAYS = 31
#: The default range: the last week, today included.
DEFAULT_DAYS = 7
#: The most rows one file lists; past it the file says how many it left out. Not measured: a
#: month of the lab's calls is about 2000 (the board's 412 a week), so it is five times that.
MAX_ROWS = 10000
#: The Network choice that means every network.
EVERY = "*"

#: What a call's verdict means in the log, in the board's words, one of these per row.
OUTCOMES = {"ok": "ok", "validation": "refused by validation", "cap": "refused at a cap",
            "gate": "refused by a gate", "failed": "failed", "joined": "joined another's call"}
#: The verdicts a gate records before anything is sent (gateway._prepared and the caps).
CAP_VERDICTS = ("over_cap", "feature_cap")
GATE_VERDICTS = ("trigger", "ai_off", "feature_off", "no_key", "workspace_limit",
                 "unknown_task", "typed_undeclared", "unknown_model", "thinking", "temperature",
                 "prompt", "unmasked_secret", "prompt_too_long")

#: The failure log's kinds, in the order the page counts them: (key, one, many).
KINDS = (
    ("dismissed", "SDN detection dismissed", "SDN detections dismissed"),
    ("classification_refused", "classification refused by the check",
     "classifications refused by the check"),
    ("verify_failed", "Verify failure", "Verify failures"),
    ("send_failed", "request the controller refused", "requests the controller refused"),
    ("protected_refusal", "protected-flow refusal", "protected-flow refusals"),
    ("auto_failed", "response AUTO could not send", "responses AUTO could not send"),
    ("evaluation_miss", "evaluation false positive", "evaluation false positives"),
    ("normal_false_positive", "detection on normal traffic (a false-positive run)",
     "detections on normal traffic (false-positive runs)"),
    ("planted_missed", "planted issue missed", "planted issues missed"),
    ("eval_missed", "planted issue an analyst evaluation missed",
     "planted issues analyst evaluations missed"),
    ("eval_false_positive", "analyst evaluation false positive",
     "analyst evaluation false positives"),
    ("eval_benign_threat", "benign case an analyst evaluation answered as a threat",
     "benign cases analyst evaluations answered as a threat"),
    ("answer_wrong", "AI answer said wrong", "AI answers said wrong"),
)
KIND_WORDS = {k: one for k, one, _many in KINDS}
#: B4's two techniques, in the failure log's words (modules/sdn/b4_eval.py `TECHNIQUES`).
B4_TECHNIQUES = {"baseline": "without tools", "tools": "with the trace tool"}
#: The protected set's guards end every refusal they word with their citation
#: (`protected.flow_refusal` "(B, C2379)", `control_plane.refusal` "(C2022)"), so an AUTO
#: failure carrying one is a protected-flow refusal.
PROTECTED_MARKS = ("C2379", "C2022")
#: What no store Mercury reads holds, said in each failure file and on the page.
NOT_RECORDED = ("the per-case misses of nmas-sdn-cases and the other *-cases scripts "
                "(intent, heal, words, assistant) are written only to each script's own --out "
                "report, so they are not here; attach that report beside this file. B3's "
                "false-positive runs and B4's analyst evaluations are here")

#: The export's steps, as the manual's How it works page names them.
STEPS = (
    ("range", f"the network (one, or every network) and whole UTC days, From to To, at most "
              f"{MAX_DAYS}: a longer range is refused, naming its length; nothing is read"),
    ("calls", "every AI call the ledger recorded in the range, one row each, with a total per "
              "UTC day and per feature; the dollars the ledger's per call, summed by UTC day "
              "from the rows read now, never carried forward"),
    ("failures", "from each network's own records: SDN detections dismissed, classifications "
                 "the check refused, responses AUTO could not send (a protected-flow refusal "
                 "named), flow operations Verify failed and what their rollback achieved, the "
                 "planted issues each analysis in the range missed, and its record of SDN "
                 "evaluation runs (each false positive a normal-traffic run found, each analyst "
                 "evaluation run that missed, kept a false positive or answered a benign case "
                 "as a threat); from the ledger, evaluation false positives; and AI answers a "
                 "person said were wrong, with their review"),
    ("mask", "every text a row carries masked on the way out, as History masks what it draws"),
    ("file", f"CSV or JSON, its first lines the log, its range, its network, when it was made "
             f"and by whom; at most {MAX_ROWS} rows, the rest counted; nothing is written"),
)


def _masked(value):
    """*value* masked on the way out (`redact.redact_text`) when it is text; anything else as
    it is. Every string a row carries passes through here."""
    if isinstance(value, str) and value:
        from modules.redact import redact_text

        return redact_text(value)
    return value


def _masked_row(row: dict) -> dict:
    return {k: _masked(v) for k, v in row.items()}


def _now() -> float:
    return time.time()


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _instant(at) -> float:
    """An ISO UTC stamp (or an epoch) as an epoch, or None when it is neither."""
    if isinstance(at, (int, float)):
        return float(at)
    try:
        return datetime.datetime.fromisoformat(str(at).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _day(at) -> str:
    t = _instant(at)
    return time.strftime("%Y-%m-%d", time.gmtime(t)) if t is not None else ""


# ───────────────────────────────────────────────────────────────────────────── the choice

def parse_range(start: str, end: str, now: float = None) -> dict:
    """The range asked: ``{"ok", "error", "start", "end", "days", "from_s", "to_s"}``, *start*
    and *end* whole UTC days (``YYYY-MM-DD``) inclusive, *from_s* and *to_s* the epochs it
    covers (*to_s* exclusive). None given: the last `DEFAULT_DAYS`, today included. A day that
    is no date, a From after its To, and a range past `MAX_DAYS` are refused, naming both."""
    today = datetime.datetime.fromtimestamp(_now() if now is None else now,
                                            datetime.timezone.utc).date()
    start, end = (start or "").strip(), (end or "").strip()
    out = {"ok": False, "error": "", "start": start, "end": end, "days": 0,
           "from_s": None, "to_s": None}
    try:
        b = datetime.date.fromisoformat(end) if end else today
    except ValueError:
        return dict(out, error=f"To {end[:20]!r} is not a day (YYYY-MM-DD)")
    try:
        a = (datetime.date.fromisoformat(start) if start
             else b - datetime.timedelta(days=DEFAULT_DAYS - 1))
    except ValueError:
        return dict(out, error=f"From {start[:20]!r} is not a day (YYYY-MM-DD)")
    out.update(start=a.isoformat(), end=b.isoformat())
    if a > b:
        return dict(out, error=f"From {a.isoformat()} is after To {b.isoformat()}")
    days = (b - a).days + 1
    if days > MAX_DAYS:
        return dict(out, days=days, error=(
            f"the range {a.isoformat()} to {b.isoformat()} is {days} days, and a log covers at "
            f"most {MAX_DAYS}: choose a shorter range, or download it in parts"))
    utc = datetime.timezone.utc
    first = datetime.datetime.combine(a, datetime.time(0, 0), tzinfo=utc)
    after = datetime.datetime.combine(b + datetime.timedelta(days=1), datetime.time(0, 0),
                                      tzinfo=utc)
    return dict(out, ok=True, days=days, from_s=first.timestamp(), to_s=after.timestamp())


def networks() -> dict:
    """``{"names", "error"}``: every registered network, or why the registry is unreadable."""
    from modules.nsot import listref

    try:
        return {"names": list(listref.names()), "error": ""}
    except Exception as exc:                          # noqa: BLE001 (said)
        return {"names": [], "error": f"the networks could not be read ({type(exc).__name__}: "
                                      f"{exc})"}


def parse_network(text: str, default: str) -> dict:
    """``{"ok", "error", "network", "names"}``: *text* a network's name, `EVERY`, or "" (the
    page's network, *default*). A name no network has is refused, naming it."""
    known = networks()
    name = (text or "").strip() or default
    out = {"ok": False, "error": known["error"], "network": name, "names": known["names"]}
    if known["error"]:
        return out
    if name != EVERY and name not in known["names"]:
        return dict(out, error=f"there is no network named {name[:60]!r}")
    return dict(out, ok=True)


def _in(t, rng) -> bool:
    return t is not None and rng["from_s"] <= t < rng["to_s"]


def _slug(name: str) -> str:
    from modules.config import list_slug

    return list_slug(name) if name else ""


def call_network(row: dict) -> str:
    """The network a call's row names, as its folder name, or "": the row's own ``network``
    when it carries one (the gateway records the network a call names, sent or refused,
    C2942), else a background trigger's; a call that names none is the installation's own."""
    named = row.get("network") or (row.get("trigger") or {}).get("network") or ""
    return _slug(str(named)) if named else ""


def history_call_link(call_id: str) -> str:
    """The call's own row on History (its call filter, all time)."""
    return "/v2/history?" + urlencode({"call": call_id, "since": ""}) if call_id else ""


def _history_day_link(network: str, kind: str, day: str) -> str:
    return "/v2/history?" + urlencode({"list": network, "kind": kind, "on": day, "since": ""})


# ───────────────────────────────────────────────────────────────────────────── the calls

def outcome(row: dict, uses: list) -> str:
    """The `OUTCOMES` key of a call's *row*, *uses* its use rows oldest first: an answer the
    gateway passed and its feature then refused is refused by validation, as is an answer
    sent and not of its schema; a cap's refusal, a gate's (recorded before anything was sent)
    and anything else that did not answer (the provider's refusal, a model's refusal or cut,
    an exception) are told apart."""
    verdict = row.get("verdict") or ""
    last = (uses[-1].get("use") or "") if uses else ""
    if verdict == "joined":
        return "joined"
    if verdict == "ok":
        return "validation" if last.startswith("refused") else "ok"
    if verdict == "schema" and row.get("tokens"):
        return "validation"
    if verdict in CAP_VERDICTS:
        return "cap"
    if verdict in GATE_VERDICTS or verdict == "schema":
        return "gate"
    return "failed"


def _trigger(row: dict) -> tuple:
    """``(kind, by)``: what started the call and who or what: the person, the job, the run."""
    trig = row.get("trigger") or {}
    kind = trig.get("kind") or ""
    if kind == "person":
        return kind, str(trig.get("by") or row.get("actor") or "")
    if kind == "background":
        return kind, (f"job {trig.get('job') or '?'} ({trig.get('feature') or '?'}, finding "
                      f"{(trig.get('finding') or {}).get('kind') or '?'} "
                      f"{(trig.get('finding') or {}).get('id') or '?'})")
    if kind == "evaluation":
        return kind, f"run {trig.get('run') or '?'}"
    return "", str(row.get("actor") or "")


def _subject(row: dict) -> str:
    from modules.history_sources import subject_words

    return subject_words(row.get("subject"))


def _call_row(row: dict, uses: list) -> dict:
    tokens = row.get("tokens") or {}
    kind, by = _trigger(row)
    key = outcome(row, uses)
    then = "; ".join((u.get("use") or "") + (f" ({u['detail']})" if u.get("detail") else "")
                     for u in uses)
    return _masked_row({
        "at": row.get("at") or "", "day": _day(row.get("at")), "call": row.get("id") or "",
        "feature": row.get("feature") or "", "trigger": kind, "by": by,
        "network": call_network(row), "about": _subject(row), "model": row.get("model") or "",
        "prompt": row.get("prompt") or "",
        "tokens_in": int(tokens.get("input_tokens") or 0),
        "tokens_out": int(tokens.get("output_tokens") or 0),
        "cache_write": int(tokens.get("cache_creation_input_tokens") or 0),
        "cache_read": int(tokens.get("cache_read_input_tokens") or 0),
        "usd": float(row.get("cost_usd") or 0.0),
        "latency_s": row.get("latency_s") if row.get("latency_s") is not None else "",
        "verdict": row.get("verdict") or "", "outcome": OUTCOMES[key],
        "detail": row.get("detail") or "", "then": then,
        "link": history_call_link(row.get("joined") or row.get("id") or "")})


def _sums(rows: list) -> dict:
    out = {"calls": 0, "joined": 0, "usd": 0.0, "tokens_in": 0, "tokens_out": 0}
    out.update({k: 0 for k in OUTCOMES if k != "joined"})
    for r in rows:
        key = next(k for k, w in OUTCOMES.items() if w == r["outcome"])
        if key == "joined":
            out["joined"] += 1
            continue
        out["calls"] += 1
        out[key] += 1
        out["usd"] += r["usd"]
        out["tokens_in"] += r["tokens_in"]
        out["tokens_out"] += r["tokens_out"]
    return out


def _ledger() -> dict:
    """The ledger's calls and their use rows: ``{"state", "error", "rows", "uses"}``."""
    from modules.ai import calls

    got = calls.kept_all()
    if got["state"] == "unreadable":
        return {"state": "unreadable", "error": got.get("error") or "", "rows": [], "uses": {}}
    uses = {}
    for r in got.get("rows") or []:
        if "use_of" in r:
            uses.setdefault(r["use_of"], []).append(r)
    return {"state": got["state"], "error": "", "uses": uses,
            "rows": [r for r in got.get("rows") or [] if "use_of" not in r]}


def calls(network: str, start: str, end: str, now: float = None, ledger: dict = None) -> dict:
    """The call and cost log of *network* (a name, or `EVERY`) from *start* to *end* (whole UTC
    days): ``{"ok", "error", "errors", "range", "network", "rows", "cut", "by_day",
    "by_feature", "summary", "unattributed"}``. *rows* oldest first, at most `MAX_ROWS` (*cut*
    the number left out); *by_day* and *by_feature* each a row per UTC day or feature with its
    calls, dollars and outcomes, over every row in the range; *summary* the same over all of
    them. One network's log holds the calls whose row names it (`call_network`);
    *unattributed* counts the range's calls that name no network, in Every network's log only."""
    rng = parse_range(start, end, now)
    base = {"ok": False, "error": rng["error"], "errors": [], "range": rng, "network": network,
            "rows": [], "cut": 0, "by_day": [], "by_feature": [], "summary": _sums([]),
            "unattributed": 0}
    if not rng["ok"]:
        return base
    got = ledger if ledger is not None else _ledger()
    if got["state"] == "unreadable":
        return dict(base, error=f"the record of AI calls could not be read: {got['error']}")
    want = "" if network == EVERY else _slug(network)
    picked, unattributed = [], 0
    for r in got["rows"]:
        if not _in(_instant(r.get("at")), rng):
            continue
        net = call_network(r)
        if want and net != want:
            unattributed += 0 if net else 1
            continue
        picked.append(r)
    # By time, the ledger's own order kept within a second (a stable sort of its append order).
    picked.sort(key=lambda r: _instant(r.get("at")))
    rows = [_call_row(r, got["uses"].get(r.get("id")) or []) for r in picked]

    def totals(key):
        groups = collections.OrderedDict()
        for r in sorted(rows, key=lambda r: r[key]):
            groups.setdefault(r[key], []).append(r)
        return [dict({key: k}, **_sums(v)) for k, v in groups.items()]

    by_day = totals("day")
    summary = _sums(rows)
    # The dollars by UTC day, then the days summed: the ledger's figures, never a running total.
    summary["usd"] = sum(d["usd"] for d in by_day)
    return dict(base, ok=True, rows=rows[:MAX_ROWS], cut=max(0, len(rows) - MAX_ROWS),
                by_day=by_day, by_feature=totals("feature"), summary=summary,
                unattributed=unattributed)


def calls_words(summary: dict) -> str:
    """The board's line: "412 calls · $0.3800 · 3 refused by validation · …"."""
    parts = [f"{summary['calls']} call{'' if summary['calls'] == 1 else 's'}",
             f"${summary['usd']:.4f}"]
    parts += [f"{summary[k]} {OUTCOMES[k]}" for k in ("validation", "cap", "gate", "failed")
              if summary.get(k)]
    if summary.get("joined"):
        parts.append(f"{summary['joined']} {'press' if summary['joined'] == 1 else 'presses'} "
                     "joined another's call")
    return " · ".join(parts)


# ───────────────────────────────────────────────────────────────────────────── the failures

def _failure(at, kind, network, what, *, reason="", who="", outcome="", case="", expected="",
             got="", link="", source="") -> dict:
    return _masked_row({"at": at or "", "day": _day(at), "kind": kind,
                        "kind_words": KIND_WORDS[kind], "network": network, "what": what,
                        "reason": reason, "who": who, "outcome": outcome, "case": case,
                        "expected": expected, "got": got, "record": link, "source": source})


def _detection_words(d: dict) -> str:
    d = d or {}
    head = d.get("title") or d.get("rule") or "a detection"
    where = f" on {d['dpid_hex']}" if d.get("dpid_hex") else ""
    return f"{head}{where}: {d.get('words')}" if d.get("words") else f"{head}{where}"


def _from_responses(network: str, rng: dict, ctx: dict) -> dict:
    """The network's pending responses: each dismissal, each classification the check refused,
    each response AUTO decided on and could not send."""
    from modules.sdn import loop

    got = loop.responses_record(network)
    if got["state"] == "unreadable":
        return {"rows": [], "errors": [f"{network}'s SDN responses could not be read: "
                                       f"{got['error']}"]}
    opened, out = {}, []
    link = "/v2/sdn/responses?" + urlencode({"list": network})
    for r in got["rows"]:
        kind, rid = r.get("kind"), r.get("id")
        if kind in ("proposed", "watching"):
            opened[rid] = r
        at = r.get("at")
        if not _in(_instant(at), rng):
            continue
        if kind == "dismissed":
            first = opened.get(rid) or {}
            out.append(_failure(at, "dismissed", network,
                                _detection_words(first.get("detection")),
                                reason=r.get("why") or "", who=r.get("actor") or "",
                                outcome=f"dismissed ({rid})", link=link,
                                source="sdn_responses"))
        elif kind == "proposed" and r.get("refused_call"):
            out.append(_failure(at, "classification_refused", network,
                                _detection_words(r.get("detection")),
                                reason=r.get("classified") or "", who="the SDN loop",
                                outcome=f"proposed for a person to decide ({rid})",
                                got=f"AI call {r['refused_call']}",
                                link=history_call_link(r["refused_call"]),
                                source="sdn_responses"))
        if kind == "proposed" and r.get("auto_failed"):
            why = str(r["auto_failed"])
            out.append(_failure(at, "protected_refusal" if any(m in why for m in PROTECTED_MARKS)
                                else "auto_failed", network,
                                _detection_words(r.get("detection")), reason=why,
                                who="AUTO", outcome=f"nothing sent; a person's ({rid})",
                                link=link, source="sdn_responses"))
    return {"rows": out, "errors": []}


def _rollback_words(op: dict) -> str:
    """What an operation's rollback achieved, from its own record."""
    rb = op.get("rollback") or {}
    if not rb.get("ran"):
        return "no rollback: nothing had landed"
    steps = rb.get("steps") or []
    sent = sum(1 for s in steps if s.get("state") == "sent")
    words = f"{sent} of {len(steps)} undo request{'' if len(steps) == 1 else 's'} sent"
    back = rb.get("read_back") or []
    if back:
        passed = sum(1 for c in back if c.get("state") == "pass")
        words += f", {passed} of {len(back)} read back as before"
    bad = [s.get("words") or s.get("role") or "" for s in steps if s.get("state") != "sent"]
    if bad:
        words += "; not undone: " + "; ".join(w for w in bad if w)
    return words + ("" if rb.get("ok") else "; the rollback did not restore the table")


def _from_operations(network: str, rng: dict, ctx: dict) -> dict:
    """The network's SDN flow operations that did not verify: Verify failed, or the controller
    refused a request; each with what its rollback achieved."""
    from modules.sdn import flow_intent

    got = flow_intent.operations(network)
    if got["state"] == "unreadable":
        return {"rows": [], "errors": [f"{network}'s SDN operations could not be read: "
                                       f"{got['error']}"]}
    out = []
    for op in got["rows"]:
        if op.get("outcome") not in ("rolled_back", "rollback_failed"):
            continue
        at = op.get("at")
        if not _in(_instant(at), rng):
            continue
        verify = op.get("verify") or {}
        kind = "verify_failed" if verify.get("ok") is False else "send_failed"
        response = op.get("response") or {}
        who = op.get("actor") or ""
        if op.get("mode") == "auto":
            who = f"{who} (AUTO)"
        out.append(_failure(at, kind, network,
                            f"{'; '.join(op.get('words') or []) or 'a flow operation'} on "
                            f"{op.get('dpid_hex') or '?'}",
                            reason=op.get("error") or "", who=who,
                            outcome=f"{(op.get('outcome') or '').replace('_', ' ')}: "
                                    f"{_rollback_words(op)}",
                            case=op.get("id") or "",
                            got=(response.get("detection") or {}).get("words") or "",
                            link=_history_day_link(network, "sdn", _day(at)),
                            source="sdn_operations"))
    return {"rows": out, "errors": []}


def _from_planted(network: str, rng: dict, ctx: dict) -> dict:
    """Each planted issue each of the network's SDN analyses in the range missed (B1's and the
    trace tool's, `analyst.sheets`, C2945): one row per issue per analysis."""
    from modules.sdn import analyst

    got = analyst.sheets(network, rng["from_s"], rng["to_s"])
    errors = ([f"{network}'s planted-issue sheets could not all be read: {got['error']}"]
              if got["state"] == "unreadable" else [])
    page = "/v2/sdn/flows?" + urlencode({"list": network}) + "#sdn-analyse"
    out = []
    for sheet in got["sheets"]:
        result = sheet["analysis"]
        tools = " (with the trace tool)" if result.get("technique") == "trace_tool" else ""
        # Each analysis's own record: its call on History (what it found, what was shown).
        link = history_call_link(result.get("call_id") or "") or page
        out += [_failure(result.get("at"), "planted_missed", network,
                         f"planted: {r.get('name')}", reason=r.get("why") or "",
                         who=result.get("actor") or "",
                         outcome=f"missed by analysis {result.get('id')}{tools}",
                         case=r.get("name") or "",
                         expected="found by evidence " + " ".join(r.get("evidence") or []),
                         got="missed", link=link, source="sdn_analyst")
                for r in sheet["rows"] if r.get("found") == "missed"]
    return {"rows": out, "errors": errors}


def _b4_case(row: dict) -> str:
    return (f"case {row.get('case')} ({row.get('role')}), "
            f"{B4_TECHNIQUES.get(row.get('technique'), row.get('technique'))}, run {row.get('n')}")


def _b4_rows(network: str, row: dict) -> list:
    """One B4 run's wrongs (`b4_eval.wrong_row`): its miss, each false-positive finding, and a
    benign case answered as a threat, each its own row."""
    who = f"run {row.get('run') or '?'} ({row.get('script')})"
    record = history_call_link((row.get("calls") or [""])[0])
    findings = row.get("findings") or []
    out = []
    if row.get("missed"):
        cited = "; ".join(f"{f.get('severity')}: {f.get('finding')}" for f in findings)
        out.append(_failure(row.get("at"), "eval_missed", network, _b4_case(row),
                            reason=row.get("name") or "", who=who,
                            outcome="counted as a miss in the run's report",
                            case=row.get("case") or "",
                            expected="found by evidence " + " ".join(row.get("issue") or []),
                            got=(f"not answered ({row['error']})" if row.get("error") else
                                 f"{len(findings)} finding(s), none citing it"
                                 + (f": {cited}" if cited else "")),
                            link=record, source="sdn_evaluations"))
    for f in findings:
        if f.get("judged") != "false_positive":
            continue
        out.append(_failure(row.get("at"), "eval_false_positive", network,
                            f"{_b4_case(row)}: {f.get('finding')}", reason=f.get("why") or "",
                            who=who, outcome="counted as a false positive in the run's report",
                            case=row.get("case") or "",
                            expected="a finding citing the planted issue or a fact the code "
                                     "measures as abnormal",
                            got=f"{f.get('severity')}, citing "
                                + " ".join(f.get("evidence") or []),
                            link=record, source="sdn_evaluations"))
    if row.get("threat_answered"):
        over = "; ".join(f"{f.get('severity')}: {f.get('finding')}" for f in findings)
        out.append(_failure(row.get("at"), "eval_benign_threat", network, _b4_case(row),
                            reason=row.get("name") or "", who=who,
                            outcome="counted as a benign run answered as a threat in the "
                                    "run's report (the pass rule's measure)",
                            case=row.get("case") or "",
                            expected="no finding of medium or above, past "
                                     + (", ".join(row.get("severities") or []) or "none"),
                            got=over, link=record, source="sdn_evaluations"))
    return out


def _from_evaluation_runs(network: str, rng: dict, ctx: dict) -> dict:
    """The network's record of SDN evaluation runs (modules/sdn/evaluations.py): each false
    positive a normal-traffic run found (B3, C2946), and each B4 run that missed, kept a false
    positive or answered a benign case as a threat (C2943)."""
    from modules.sdn import evaluations

    got = evaluations.read(network)
    if got["state"] == "unreadable":
        return {"rows": [], "errors": [f"{network}'s record of SDN evaluation runs could not "
                                       f"be read: {got['error']}"]}
    out = []
    for r in got["rows"]:
        if not _in(_instant(r.get("at")), rng):
            continue
        if r.get("script") == evaluations.FALSE_POSITIVES and r.get("kind") == "false_positive":
            d = r.get("detection") or {}
            port = f" port {d['port']}" if d.get("port") not in (None, "") else ""
            out.append(_failure(r.get("at"), "normal_false_positive", network,
                                f"{d.get('rule')} on {d.get('switch')}{port}"
                                + (f" from {d['source']}" if d.get("source") else ""),
                                reason=d.get("words") or "",
                                who=f"run {r.get('run_id')} ({r.get('run')})",
                                outcome=d.get("done") or "",
                                case=f"{r.get('run')} pass {d.get('pass')} at {d.get('at')}",
                                expected="no detection: the traffic was declared normal",
                                got=f"{d.get('rule')}: {d.get('measured')} against "
                                    f"{d.get('threshold')}; evidence {d.get('evidence')}",
                                source="sdn_evaluations"))
        elif r.get("script") == evaluations.B4_EVAL and r.get("kind") == "case_run":
            out += _b4_rows(network, r)
    return {"rows": out, "errors": []}


def _from_evaluations(network: str, rng: dict, ctx: dict) -> dict:
    """The ledger's evaluation calls that classified a collection no rule fired on as a threat
    (`closed_loop.prepare_collection`'s subject): a false positive, by the evaluation's own
    definition. Ledger-wide: read once, for the first network asked (`ctx`)."""
    if ctx.get("evaluations_read"):
        return {"rows": [], "errors": []}
    ctx["evaluations_read"] = True
    led = ctx["ledger"]
    if led["state"] == "unreadable":
        return {"rows": [], "errors": []}      # said once, by the call log's read
    want = ctx["want"]
    out = []
    for r in led["rows"]:
        if (r.get("subject") or {}).get("kind") != "sdn_collection" or r.get("verdict") != "ok":
            continue
        o = r.get("output") or {}
        if not o.get("threat_detected") or not _in(_instant(r.get("at")), rng):
            continue
        net = call_network(r)
        if want and net != want:
            continue
        _kind, by = _trigger(r)
        out.append(_failure(r.get("at"), "evaluation_miss", net,
                            f"normal traffic collected {(r.get('subject') or {}).get('id') or '?'}",
                            reason=str(o.get("reasoning") or ""), who=by,
                            outcome="a threat found where no rule fired",
                            case=str((r.get("subject") or {}).get("id") or ""),
                            expected="no threat (no rule fired on this collection)",
                            got=f"{o.get('threat_type') or 'a threat'}, severity "
                                f"{o.get('severity') or '?'}",
                            link=history_call_link(r.get("id") or ""), source="ai_calls"))
    return {"rows": out, "errors": []}


def _from_feedback(network: str, rng: dict, ctx: dict) -> dict:
    """Each AI answer a person said was wrong, and what its review did. Installation-wide:
    read once (`ctx`); a call's network from its row in the ledger."""
    if ctx.get("feedback_read"):
        return {"rows": [], "errors": []}
    ctx["feedback_read"] = True
    from modules.ai import feedback

    got = feedback.read()
    if got["state"] == "unreadable":
        return {"rows": [], "errors": [f"the answers said right or wrong could not be read: "
                                       f"{got['error']}"]}
    by_id = {r.get("id"): r for r in ctx["ledger"]["rows"]}
    reviews = {}
    for r in got["rows"]:
        if r.get("kind") == "review" and r.get("of") and r["of"] not in reviews:
            reviews[r["of"]] = r
    want, out = ctx["want"], []
    for v in got["rows"]:
        if v.get("kind") != "verdict" or v.get("verdict") != feedback.NO:
            continue
        if not _in(_instant(v.get("at")), rng):
            continue
        net = call_network(by_id.get(v.get("call_id")) or {})
        if want and net != want:
            continue
        rev = reviews.get(v.get("id"))
        did = (f"{rev.get('outcome')} by {rev.get('actor') or '?'} at {rev.get('at') or '?'}"
               + (f": {rev['reason']}" if rev.get("reason") else "")) if rev else "to review"
        out.append(_failure(v.get("at"), "answer_wrong", net,
                            f"{feedback.FEATURES.get(v.get('task'), v.get('task') or 'a task')}"
                            f": {feedback.KINDS.get(v.get('why'), v.get('why') or '')}",
                            reason=v.get("words") or "", who=v.get("actor") or "",
                            outcome=did, case=v.get("call_id") or "",
                            link=history_call_link(v.get("call_id") or ""),
                            source="ai_feedback"))
    return {"rows": out, "errors": []}


#: Every source of the failure log: (its name, its reader ``fn(network, range, ctx)``). A
#: network's own store is read per network; the ledger's and the feedback's once, attributed
#: by the call's network.
FAILURE_SOURCES = (
    ("sdn_responses", _from_responses),
    ("sdn_operations", _from_operations),
    ("sdn_analyst", _from_planted),
    ("sdn_evaluations", _from_evaluation_runs),
    ("ai_calls", _from_evaluations),
    ("ai_feedback", _from_feedback),
)


def failures(network: str, start: str, end: str, now: float = None,
             ledger: dict = None) -> dict:
    """The false-positive and failure log of *network* (a name, or `EVERY`) from *start* to
    *end*: ``{"ok", "error", "errors", "range", "network", "rows", "cut", "counts",
    "reasons"}``. *rows* oldest first, at most `MAX_ROWS`; *counts* ``[(kind, words, n)]`` in
    `KINDS`' order over every row; *reasons* the dismissals' reasons, most given first. A
    store that cannot be read is in *errors*, never a shorter log said whole."""
    rng = parse_range(start, end, now)
    base = {"ok": False, "error": rng["error"], "errors": [], "range": rng, "network": network,
            "rows": [], "cut": 0, "counts": [(k, many, 0) for k, _one, many in KINDS],
            "reasons": []}
    if not rng["ok"]:
        return base
    names = [network]
    if network == EVERY:
        known = networks()
        if known["error"]:
            return dict(base, error=known["error"])
        names = known["names"]
    led = ledger if ledger is not None else _ledger()
    ctx = {"ledger": led, "want": "" if network == EVERY else _slug(network)}
    rows, errors = [], []
    if led["state"] == "unreadable":
        errors.append(f"the record of AI calls could not be read: {led['error']}")
    for name in names:
        for source, read in FAILURE_SOURCES:
            try:
                got = read(name, rng, ctx)
            except Exception as exc:                  # noqa: BLE001 (said, never a shorter log)
                log.error("history export: %s on %s raised %s", source, name, exc)
                got = {"rows": [], "errors": [f"{source} on {name} could not be read "
                                              f"({type(exc).__name__}: {exc})"]}
            rows += got["rows"]
            errors += got["errors"]
    # By time; within a second each source's own order (a stable sort).
    rows.sort(key=lambda r: _instant(r["at"]) or 0.0)
    n = collections.Counter(r["kind"] for r in rows)
    reasons = collections.Counter(r["reason"] for r in rows if r["kind"] == "dismissed"
                                  and r["reason"])
    return dict(base, ok=True, errors=[_masked(e) for e in errors], rows=rows[:MAX_ROWS],
                cut=max(0, len(rows) - MAX_ROWS),
                counts=[(k, one if n[k] == 1 else many, n[k]) for k, one, many in KINDS],
                reasons=reasons.most_common())


def failures_words(got: dict) -> str:
    """The board's line: "9 SDN detections dismissed (6 "normal traffic") · …", the kinds
    with none left out; "" when there is none."""
    parts = []
    for kind, words, count in got["counts"]:
        if not count:
            continue
        part = f"{count} {words}"
        if kind == "dismissed" and got["reasons"] and got["reasons"][0][1] > 1:
            reason, times = got["reasons"][0]
            part += f" ({times} “{reason[:60]}”)"
        parts.append(part)
    return " · ".join(parts)


# ───────────────────────────────────────────────────────────────────────────── the files

CALL_COLUMNS = ("at", "day", "call", "feature", "trigger", "by", "network", "about", "model",
                "prompt", "tokens_in", "tokens_out", "cache_write", "cache_read", "usd",
                "latency_s", "verdict", "outcome", "detail", "then", "link")
TOTAL_COLUMNS = ("calls", "usd", "ok", "validation", "cap", "gate", "failed", "joined",
                 "tokens_in", "tokens_out")
FAILURE_COLUMNS = ("at", "kind", "kind_words", "network", "what", "reason", "who", "outcome",
                   "case", "expected", "got", "record", "source")
AMOUNTS = ("the ledger's own cost per call in US dollars (the provider bills), summed by UTC "
           "day from the rows read now; never carried forward from an earlier total")
TITLES = {"calls": "Mercury: AI calls and cost", "failures": "Mercury: false positives and "
          "failures"}


def _network_words(network: str) -> str:
    return "every network" if network == EVERY else network


def header(kind: str, got: dict, *, by: str, now: float = None) -> list:
    """The first lines every file opens with, ``[(label, value...)]``: the log, its range, its
    network, when it was made and by whom, what its amounts are (the call log), what is not
    recorded (the failure log), and any store it could not read."""
    rng = got["range"]
    lines = [("log", TITLES[kind]),
             ("range", rng["start"], rng["end"], f"{rng['days']} whole UTC days, inclusive"),
             ("network", _network_words(got["network"])),
             ("made", _iso(_now() if now is None else now), "by", by or "unknown")]
    if kind == "calls":
        lines.append(("amounts", AMOUNTS))
        lines.append(("in the range", calls_words(got["summary"])))
        if got["unattributed"]:
            lines.append(("not in this network's log", f"{got['unattributed']} calls in the "
                          "range name no network (the installation's own, or recorded before "
                          "2026-11-10): they are in Every network's log"))
    else:
        lines.append(("in the range", failures_words(got) or "nothing"))
        lines.append(("not recorded", NOT_RECORDED))
    for e in got["errors"]:
        lines.append(("could not read", e))
    if got["cut"]:
        lines.append(("rows left out", f"{got['cut']} past the first {MAX_ROWS}; the totals "
                      "count every row in the range"))
    return lines


def _cell(value):
    """A CSV cell: a number as it is; text that a spreadsheet would read as a formula kept as
    text (a leading apostrophe)."""
    if isinstance(value, float):
        return f"{value:.6f}"
    text = str(value if value is not None else "")
    return "'" + text if text[:1] in ("=", "+", "@", "\t", "\r") else text


def to_csv(kind: str, got: dict, *, by: str, now: float = None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for line in header(kind, got, by=by, now=now):
        w.writerow(["# " + line[0]] + [_cell(v) for v in line[1:]])
    columns = CALL_COLUMNS if kind == "calls" else FAILURE_COLUMNS
    w.writerow(columns)
    for r in got["rows"]:
        w.writerow([_cell(r[c]) for c in columns])
    if kind == "calls":
        for key, words in (("day", "by UTC day"), ("feature", "by feature")):
            w.writerow([])
            w.writerow([f"# totals {words}"])
            w.writerow((key,) + TOTAL_COLUMNS)
            for t in got[f"by_{key}"]:
                w.writerow([_cell(t[key])] + [_cell(t[c]) for c in TOTAL_COLUMNS])
            w.writerow(["# all"] + [_cell(got["summary"][c]) for c in TOTAL_COLUMNS])
    return buf.getvalue()


def to_json(kind: str, got: dict, *, by: str, now: float = None) -> str:
    rng = got["range"]
    lines = header(kind, got, by=by, now=now)
    doc = {"log": TITLES[kind], "range": {"from": rng["start"], "to": rng["end"],
                                          "days": rng["days"], "days_are": "UTC, inclusive"},
           "network": _network_words(got["network"]),
           "made_at": lines[3][1], "made_by": lines[3][3]}
    if kind == "calls":
        doc.update(amounts=AMOUNTS, summary=got["summary"], unattributed=got["unattributed"])
    else:
        doc.update(counts={k: n for k, _w, n in got["counts"]}, not_recorded=NOT_RECORDED)
    doc.update(errors=got["errors"], rows_left_out=got["cut"], max_rows=MAX_ROWS,
               rows=got["rows"])
    if kind == "calls":
        doc.update(by_day=got["by_day"], by_feature=got["by_feature"])
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def download(kind: str, fmt: str, network: str, start: str, end: str, *, by: str,
             default: str, now: float = None) -> dict:
    """One file: ``{"ok", "error", "body", "mime", "filename"}``. A kind or format it does not
    make, a network no one has, or a range it refuses is an error naming it; nothing is
    written either way."""
    if kind not in TITLES:
        return {"ok": False, "error": f"no log {kind[:20]!r}: the logs are calls and failures"}
    if fmt not in ("csv", "json"):
        return {"ok": False, "error": f"no file as {fmt[:20]!r}: a log downloads as csv or json"}
    net = parse_network(network, default)
    if not net["ok"]:
        return {"ok": False, "error": net["error"]}
    got = (calls if kind == "calls" else failures)(net["network"], start, end, now=now)
    if not got["ok"]:
        return {"ok": False, "error": got["error"]}
    body = (to_csv if fmt == "csv" else to_json)(kind, got, by=by, now=now)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_"
                   for ch in _network_words(net["network"]))
    rng = got["range"]
    return {"ok": True, "error": "", "body": body,
            "mime": "text/csv" if fmt == "csv" else "application/json",
            "filename": f"mercury-{'ai-calls' if kind == 'calls' else 'failures'}-{safe}-"
                        f"{rng['start']}-to-{rng['end']}.{fmt}"}


# ───────────────────────────────────────────────────────────────────────────── the page

def view(network: str, start: str, end: str, *, default: str, now: float = None) -> dict:
    """What History › Export draws: ``{"network", "names", "first_day", "last_day", "days",
    "error", "calls", "failures", "fail_counts", "not_recorded", "errors", "empty",
    "max_days", "unattributed"}``.
    *calls* and *failures* the board's two lines; *fail_counts* ``[(words, n)]``, every kind;
    *empty* when the range holds nothing of either. A choice refused is said, and nothing is
    read for it."""
    net = parse_network(network, default)
    rng = parse_range(start, end, now)
    # The range's days by names of their own: a key is judged drawn by its name across
    # History's templates (tests/v2_context.py), and `start` and `end` are the Query pages'.
    out = {"network": net["network"], "names": net["names"], "first_day": rng["start"],
           "last_day": rng["end"], "days": rng["days"], "error": net["error"] or rng["error"],
           "calls": "", "failures": "", "fail_counts": [], "not_recorded": NOT_RECORDED,
           "errors": [], "empty": False, "max_days": MAX_DAYS, "unattributed": 0}
    if out["error"]:
        return out
    led = _ledger()
    c = calls(net["network"], rng["start"], rng["end"], now=now, ledger=led)
    f = failures(net["network"], rng["start"], rng["end"], now=now, ledger=led)
    out.update(calls=calls_words(c["summary"]) if c["ok"] else "",
               failures=failures_words(f) if f["ok"] else "",
               fail_counts=[(words, n) for _k, words, n in f["counts"]],
               errors=[e for e in [c["error"], f["error"]] + f["errors"] if e],
               unattributed=c["unattributed"],
               empty=c["ok"] and f["ok"] and not c["summary"]["calls"]
               and not c["summary"]["joined"] and not f["rows"])
    return out
