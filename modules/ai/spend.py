"""AI spend, as the toolbar chip, the spend panel and the background features' caps read it
(PHASE8_PLAN 18.3 rules 4, 6, 9 and 10; CLAUDE.md, "AI cost safety"; C1843). One module, so
what a screen says and what the gateway counts cannot disagree.

**Every figure is the record's** (`ai_calls`: one row per call, sent or refused, its cost
priced from the dated table in `profiles`, never the provider's bill), attributed by the
trigger the call named (`triggers`; a row from before triggers were recorded is read as a
person's, or an evaluation's when its actor says ``evaluation:``, a read's derivation only).

**The bound** (CLAUDE.md, enterprise scale): nothing here reads the whole record. Each figure
is read from a window (`calls.rows_since`, which reads the file from its end back to the
window's start, or asks the records database for the window alone):

- the chip: today's rows (`calls.spent_usd`), on every page;
- the panel: the rows since the earlier of the month's first day and 30 cap days ago (at most
  31 days), when it is opened;
- a background call's caps (`feature_spent`, asked by the gateway): the month's rows, and only
  for a background call;
- Needs attention (`attention.ai_spend_source`): the month's rows, and only while a background
  feature is on somewhere; with none on it reads nothing.

The record grows for ever and a window does not. If the window's rows, measured on a host,
are too many to read per request, the next step is a per-day total kept for each closed day;
nothing has measured that yet.

**The day** is the cap's (`calls.today`, the stated boundary's midnight), and a month is the
cap days whose date shares its year and month.
"""
import calendar
import datetime
import logging

from modules.ai import calls

log = logging.getLogger(__name__)

#: The warnings' fractions of a cap (rule 4): 50% and 80%.
WARN_AT = (0.5, 0.8)
#: The panel's longest average: 30 cap days.
WINDOW_DAYS = 30


def trigger_of(row: dict) -> dict:
    """The trigger a call's row records; a row from before triggers were recorded is read as a
    person's press, or an evaluation's when its actor is ``evaluation:<run>`` (a read's
    derivation, never written back)."""
    from modules.ai import cases

    got = row.get("trigger")
    if isinstance(got, dict) and got.get("kind"):
        return got
    actor = str(row.get("actor") or "")
    if actor.startswith(cases.EVALUATION):
        return {"kind": "evaluation", "run": actor[len(cases.EVALUATION):], "derived": True}
    return {"kind": "person", "by": actor, "derived": True}


def _usd(rows) -> float:
    return sum(float(r.get("cost_usd") or 0) for r in rows)


def day_minus(day: str, n: int) -> str:
    """The cap day *n* days before *day*."""
    return (datetime.date.fromisoformat(day) - datetime.timedelta(days=n)).isoformat()


def days_in_month(day: str) -> int:
    d = datetime.date.fromisoformat(day)
    return calendar.monthrange(d.year, d.month)[1]


def month_start(day: str, zone: str = None):
    """When the cap's month holding *day* begins: its first day's midnight in the boundary's
    zone, as an aware UTC datetime."""
    return calls.day_start(day[:8] + "01", zone)


def _of_feature(row: dict, network: str, feature: str) -> bool:
    t = row.get("trigger")
    return (isinstance(t, dict) and t.get("kind") == "background"
            and t.get("feature") == feature and t.get("network") == network)


def feature_spent(network: str, feature: str, day: str = None, rows=None,
                  zone: str = None) -> dict:
    """``{"state", "error", "day_usd", "day_calls", "month_usd", "month_calls", "refused"}``:
    what the background *feature*'s calls on *network* cost on the cap's *day* and in its
    month, read from the month's window (or *rows*, a window a caller already read).
    ``refused`` is that period's cap refusals (``{"day": [...], "month": [...]}``, each the
    row's time and which cap), which is how a feature reads as stopped. An unreadable record
    is said, never read as nothing spent."""
    zone = zone or calls.boundary()
    day = day or calls.today(zone=zone)
    if rows is None:
        got = calls.rows_since(month_start(day, zone))
        if got["state"] == "unreadable":
            return {"state": "unreadable", "error": got["error"], "day_usd": None,
                    "day_calls": 0, "month_usd": None, "month_calls": 0,
                    "refused": {"day": [], "month": []}}
        rows = got["rows"]
    mine = [(calls._row_day(r, zone), r) for r in rows if _of_feature(r, network, feature)]
    in_month = [(d, r) for d, r in mine if d[:7] == day[:7] and d <= day]
    in_day = [r for d, r in in_month if d == day]
    refused = {"day": [], "month": []}
    for d, r in in_month:
        if r.get("verdict") == "feature_cap":
            said = {"at": r.get("at"), "cap": r.get("cap_kind") or ""}
            if said["cap"] == "month":
                refused["month"].append(said)
            elif d == day:
                refused["day"].append(said)
    return {"state": "ok", "error": "", "day_usd": _usd(in_day), "day_calls": len(in_day),
            "month_usd": _usd(r for _d, r in in_month), "month_calls": len(in_month),
            "refused": refused}


def _level(ratio) -> str:
    """The chip's colour for a fraction of a cap: neutral, amber from 50%, red from 80%."""
    if ratio is None:
        return "neutral"
    return "red" if ratio >= WARN_AT[1] else "amber" if ratio >= WARN_AT[0] else "neutral"


def chip(now=None) -> dict:
    """The toolbar chip's answer (rule 10a), read from today's rows alone: ``{"state", "words",
    "level", "usd_today", "day_cap", "no_cap", "background_on", "error"}``. *state* is "off"
    (hosted AI not allowed, or no key: "AI off"), "unreadable" (the record cannot be read: the
    chip says so, never blank and never $0), or "on" ("AI $X today · N background on");
    *level* neutral, amber at 50% and red at 80% of the day cap (neutral with no cap)."""
    from modules.ai import background, gateway
    from modules.secrets_store import is_set

    on = len(background.enabled())
    base = {"background_on": on, "day_cap": gateway.day_cap(), "usd_today": None, "error": ""}
    base["no_cap"] = base["day_cap"] is None
    if not gateway.hosted_allowed()["allowed"] or not is_set("anthropic_api_key"):
        return dict(base, state="off", words="AI off", level="neutral")
    today = calls.today(now)
    spent = calls.spent_usd(today)
    if spent["state"] == "unreadable":
        return dict(base, state="unreadable", level="red", error=spent["error"],
                    words="AI spend unknown: the record of AI calls cannot be read")
    usd = float(spent["usd"] or 0.0)
    return dict(base, state="on", usd_today=usd, level=_level(_ratio(usd, base["day_cap"])),
                words=f"AI ${usd:.2f} today · {on} background on")


def _averages(by_day: dict, today: str) -> dict:
    """The 7- and 30-day daily averages over the complete cap days before *today*."""
    return {n: sum(by_day.get(day_minus(today, i), 0.0) for i in range(1, n + 1)) / n
            for n in (7, WINDOW_DAYS)}


def panel(viewer: str = "", now=None) -> dict:
    """The spend panel's answer (rule 10b): today, the 7- and 30-day daily averages (over the
    complete cap days before today), month to date against the monthly cap with its month-end
    projection at the current rate, the viewer's own spend today, today's spend by trigger
    kind and each evaluation run's (rule 9), and each background feature on, with its trigger,
    caps and estimate against actual (`feature_summaries`). Read from one window of at most
    31 days. *state* "unreadable" says why, never zeros.

    The monthly cap: no setting holds one. It is the day cap times the month's days, the most
    the day cap lets a month spend (``month_cap_basis`` says so), and none with no day cap."""
    from modules.ai import gateway, profiles

    now = now or datetime.datetime.now(datetime.timezone.utc)
    zone = calls.boundary()
    today = calls.today(now, zone)
    m_start = month_start(today, zone)
    start = min(m_start, calls.day_start(day_minus(today, WINDOW_DAYS), zone))
    got = calls.rows_since(start)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "error": got["error"], "today": today}
    rows = got["rows"]
    by_day, today_rows = {}, []
    for r in rows:
        d = calls._row_day(r, zone)
        by_day[d] = by_day.get(d, 0.0) + float(r.get("cost_usd") or 0)
        if d == today:
            today_rows.append(r)
    mtd = sum(v for d, v in by_day.items() if d[:7] == today[:7] and d <= today)
    elapsed = max((now - m_start).total_seconds() / 86400.0, 1.0)
    dim = days_in_month(today)
    cap = gateway.day_cap()
    kinds, runs = {}, {}
    for r in today_rows:
        t = trigger_of(r)
        kinds[t["kind"]] = kinds.get(t["kind"], 0.0) + float(r.get("cost_usd") or 0)
        if t["kind"] == "evaluation":
            runs[t.get("run", "")] = runs.get(t.get("run", ""), 0.0) + float(
                r.get("cost_usd") or 0)
    return {
        "state": "ok", "error": "", "today": today, "zone": zone,
        "usd_today": by_day.get(today, 0.0),
        # A press that joined another's call (C1854) cost nothing and made no call.
        "calls_today": sum(1 for r in today_rows if r.get("verdict") != calls.JOINED),
        "average": _averages(by_day, today),
        "month": {"usd": mtd, "days": dim, "elapsed_days": round(elapsed, 3),
                  "projection": mtd / elapsed * dim,
                  "cap": cap * dim if cap is not None else None,
                  "cap_basis": (f"the day cap ${cap:.2f} times the month's {dim} days"
                                if cap is not None else "no day cap is set, so no month cap")},
        "mine_today": _usd(r for r in today_rows if viewer and r.get("actor") == viewer),
        "by_kind_today": kinds, "runs_today": runs,
        "day_cap": cap, "no_cap": cap is None, "resets": calls.reset_info(now, zone),
        "prices_as_of": profiles.PRICES_AS_OF,
        "features": feature_summaries(rows, today, zone, now),
    }


def _ratio(usd, cap):
    """*usd* as a fraction of *cap*, to a millionth (so $1.20 of $1.50 is 80%, never the
    0.7999… a float divides it to), or None with no cap."""
    return round(usd / cap, 6) if (usd is not None and cap) else None


def feature_summaries(rows, today: str, zone: str, now=None) -> list:
    """Each background feature on, for each network (`background.enabled`), from *rows* (a
    window holding the month): its trigger in words, its caps, today's and the month's spend
    with their fractions of each cap, its warning (``""``, ``"50"`` or ``"80"``), whether it is
    stopped (a cap refusal recorded this period since its caps were last set), and its
    estimate against actual: the estimate recorded when it was turned on, beside the average
    daily spend over the complete cap days since then (at most 30), and their ratio."""
    from modules.ai import background

    now = now or datetime.datetime.now(datetime.timezone.utc)
    out = []
    for network, name, entry in background.enabled():
        spec = background.FEATURES.get(name) or {}
        caps = background.caps_of(entry)
        spent = feature_spent(network, name, today, rows=rows, zone=zone)
        set_at = str(entry.get("caps_at") or entry.get("at") or "")
        stopped = {k: [r for r in spent["refused"][k] if str(r.get("at") or "") >= set_at]
                   for k in ("day", "month")}
        fractions = {"day": _ratio(spent["day_usd"], caps["day"]),
                     "month": _ratio(spent["month_usd"], caps["month"])}
        top = max((f for f in fractions.values() if f is not None), default=None)
        warning = ("80" if top is not None and top >= WARN_AT[1] else
                   "50" if top is not None and top >= WARN_AT[0] else "")
        on_day = calls._row_day({"at": entry.get("at")}, zone)
        days = []
        if on_day:
            n = 1
            while n <= WINDOW_DAYS and day_minus(today, n) >= on_day:
                days.append(day_minus(today, n))
                n += 1
        by_day = {}
        for r in rows:
            if _of_feature(r, network, name):
                d = calls._row_day(r, zone)
                by_day[d] = by_day.get(d, 0.0) + float(r.get("cost_usd") or 0)
        actual = (sum(by_day.get(d, 0.0) for d in days) / len(days)) if days else None
        est = entry.get("estimate") or {}
        out.append({
            "network": network, "feature": name, "words": spec.get("words", name),
            "trigger_words": spec.get("trigger_words", ""), "on_by": entry.get("by", ""),
            "on_at": entry.get("at", ""), "caps": caps, "spent": spent,
            "fractions": fractions, "warning": warning,
            "stopped": {k: bool(v) for k, v in stopped.items()},
            "stopped_at": {k: (v[-1]["at"] if v else None) for k, v in stopped.items()},
            "estimate": est, "actual_usd_per_day": actual, "actual_days": len(days),
            "ratio": _ratio(actual, est.get("usd_per_day")),
        })
    return out
