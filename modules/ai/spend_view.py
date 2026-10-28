"""What the top bar's AI chip and its spend panel draw (boards AI1, `AiChip`, and AI2,
`AiSpendPanel`, the mockups canvas's page "C1843: AI cost safety", signed off under the Phase 7
mode 2026-10-27; PHASE8_PLAN 18.3 rules 8 and 10a, 10b; CLAUDE.md, "AI spend is shown where
people work").

Every figure is `modules.ai.spend`'s, so what a screen says and what the gateway counts cannot
disagree; this module only shapes it into exactly what the two templates draw (every key it
returns is drawn: tests/test_v2_context_is_drawn.py).

**The chip** is asked on every v2 page (`base.html`'s top bar, by htmx after the page loads)
and again on `ai_calls` and `settings`: `spend.chip`, today's window of the record of AI calls
and the settings, never a provider request and never per device. **The panel** is asked only
when it is opened, and again on `ai_calls` while it is open: `spend.panel`, one window of at
most 31 days. Calls in flight (`modules/ai/reservations.py`) are not drawn: a reservation lives
for the seconds a call takes, and its cost is counted when the call is recorded.

**Who sees amounts** (board AI1's case 7, decision 6) is not built: every viewer sees the
amounts, which is decision 6's default (C1953; docs/STANDING_APPROVAL_LOG.md).
"""
import datetime
import logging

log = logging.getLogger(__name__)

#: The month names the panel says its month by (never the host's locale).
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")
#: Where an admin turns a background feature on, changes its caps, or allows hosted AI.
SETTINGS_AI_HREF = "/v2/settings/installation?tab=ai"


def _pct(ratio):
    """A fraction as a whole percentage, or None."""
    return None if ratio is None else int(round(ratio * 100))


def _bar(ratio) -> int:
    """A fraction as a bar's width in percent, 0 to 100."""
    return 0 if ratio is None else max(0, min(100, int(round(ratio * 100))))


def _is_off() -> bool:
    """AI is off as the chip reads it (`spend.hosted_on`): hosted AI not allowed, or no key."""
    from modules.ai import spend

    return not spend.hosted_on()


def _why_off() -> str:
    """Why the chip says AI off: hosted AI not allowed, or no provider key."""
    from modules.ai import gateway

    allowed = gateway.hosted_allowed()
    if not allowed["allowed"]:
        return ("Hosted AI is off: an admin allows it on Settings › Installation › Connections, "
                "the AI (hosted) card, with a recorded reason.")
    return ("Hosted AI is allowed, but no provider key is set: an admin enters one on Settings "
            "› Installation › Connections, the AI (hosted) card.")


def chip(now=None) -> dict:
    """The chip, as drawn: ``{"state", "level", "text", "short", "label", "title", "no_cap"}``.
    *text* follows the chip's "AI" mark ("$0.42 today · 0 background on", "AI off", "AI spend
    unknown"); *short* is its phone-width form ("$0.42", "off", "unknown"), which moves the
    background count into the panel; *label* is `spend.chip`'s words whole; *title* the
    figure's provenance, on hover. Never blank: a read that raises is drawn as unknown."""
    from modules.ai import calls, profiles, spend

    now = now or datetime.datetime.now(datetime.timezone.utc)
    try:
        c = spend.chip(now)
    except Exception as exc:                                    # noqa: BLE001 (said, in red)
        log.exception("ai spend: the chip could not be read")
        c = {"state": "unreadable", "level": "red", "error": f"{type(exc).__name__}: {exc}",
             "words": "AI spend unknown: the record of AI calls cannot be read",
             "no_cap": False}
    out = {"state": c["state"], "level": c["level"], "label": c["words"],
           "no_cap": bool(c.get("no_cap")) and c["state"] == "on"}
    if c["state"] == "off":
        return dict(out, text="AI off", short="off",
                    title=_why_off() + " Nothing is sent to a model.")
    if c["state"] == "unreadable":
        return dict(out, text="AI spend unknown", short="unknown", title=(
            f"The record of AI calls could not be read ({c.get('error') or 'no reason given'}), "
            "so today's spend is unknown, and every AI call is refused until it can be read. "
            "It is never drawn as $0."))
    usd, cap, zone = c["usd_today"], c["day_cap"], calls.boundary()
    of_cap = (f"of the day cap ${cap:.2f} ({_pct(spend._ratio(usd, cap))}%)" if cap is not None
              else "with no day cap set (an admin chose no cap)")
    n = c.get("calls_today", 0)
    title = (f"${usd:.2f} in {n} call{'' if n == 1 else 's'} since midnight {zone} (the day "
             f"cap's boundary), {of_cap}. Read from the record of AI calls at "
             f"{now.strftime('%H:%M:%S')} UTC, priced from Mercury's table as of "
             f"{profiles.PRICES_AS_OF}; the provider bills what is spent.")
    return dict(out, text=c["words"][len("AI "):], short=f"${usd:.2f}", title=title)


def network_name(slug: str) -> str:
    from modules.nsot import listref

    try:
        return listref.display_name(slug)
    except Exception:                                           # noqa: BLE001 (named as stored)
        return slug


def _feature(f: dict) -> dict:
    """One background feature on, as the panel draws it (`spend.feature_summaries`' row)."""
    from modules.ai import background

    spec = background.FEATURES.get(f["feature"]) or {}
    caps, spent = f["caps"], f["spent"]
    est = (f.get("estimate") or {}).get("usd_per_day")
    stopped = "month" if f["stopped"]["month"] else "day" if f["stopped"]["day"] else ""
    return {
        "network": f["network"], "network_name": network_name(f["network"]),
        "name": f["feature"], "words": f["words"], "trigger_words": f["trigger_words"],
        "per_finding": int(spec.get("calls_per_finding") or 1),
        "day_usd": spent["day_usd"], "day_cap": caps["day"],
        "day_pct": _pct(f["fractions"]["day"]),
        "month_usd": spent["month_usd"], "month_cap": caps["month"],
        "month_pct": _pct(f["fractions"]["month"]),
        "warning": f["warning"], "stopped": stopped,
        "stopped_at": f["stopped_at"][stopped] if stopped else None,
        "estimate_usd": est, "actual_usd": f["actual_usd_per_day"],
        "actual_days": f["actual_days"], "ratio_pct": _pct(f["ratio"]),
        "on_by": f["on_by"], "on_at": f["on_at"],
    }


def panel(viewer: str = "", now=None) -> dict:
    """The spend panel, as drawn (board AI2), from `spend.panel`: ``{"state", "hosted", ...}``.
    *state* "ok", or "unreadable" with *error* and the background features on (each with Turn
    off: turning a feature off needs no spend figure). *hosted* is "" while hosted AI is
    allowed and a key is set, else why AI is off; the panel still draws what was spent."""
    from modules.ai import background, profiles, spend

    now = now or datetime.datetime.now(datetime.timezone.utc)
    hosted = _why_off() if _is_off() else ""
    base = {"hosted": hosted, "prices_as_of": profiles.PRICES_AS_OF,
            "settings_href": SETTINGS_AI_HREF}
    try:
        p = spend.panel(viewer, now=now)
    except Exception as exc:                                    # noqa: BLE001 (said in place)
        log.exception("ai spend: the panel could not be read")
        p = {"state": "unreadable", "error": f"{type(exc).__name__}: {exc}"}
    if p["state"] == "unreadable":
        on = [{"network": n, "network_name": network_name(n), "name": name,
               "words": (background.FEATURES.get(name) or {}).get("words", name)}
              for n, name, _e in background.enabled()]
        return dict(base, state="unreadable", error=p.get("error") or "no reason given",
                    features_on=on)
    cap, month = p["day_cap"], p["month"]
    usd = p["usd_today"]
    ratio = spend._ratio(usd, cap)
    kinds = p["by_kind_today"]
    runs = sorted(p["runs_today"].items(), key=lambda kv: (-kv[1], kv[0]))
    background_n = len({(f["network"], f["feature"]) for f in p["features"]})
    day = datetime.date.fromisoformat(p["today"])
    last = datetime.date(day.year, day.month, month["days"])
    m_ratio = spend._ratio(month["usd"], month["cap"])
    proj_ratio = spend._ratio(month["projection"], month["cap"])
    return dict(
        base, state="ok",
        today={"usd": usd, "calls": p["calls_today"], "cap": cap, "pct": _pct(ratio),
               "level": spend._level(ratio), "bar": _bar(ratio), "mine": p["mine_today"],
               "resets": p["resets"]},
        kinds=[{"words": "People's presses", "usd": kinds.get("person", 0.0)},
               {"words": f"Background ({background_n} feature{'' if background_n == 1 else 's'})",
                "usd": kinds.get("background", 0.0)},
               {"words": f"Evaluation runs ({len(runs)})", "usd": kinds.get("evaluation", 0.0)}],
        runs=[{"run": r, "usd": v} for r, v in runs],
        average={"week": p["average"][7], "month": p["average"][spend.WINDOW_DAYS]},
        month={"name": MONTHS[day.month - 1], "elapsed": month["elapsed_days"],
               "days": month["days"], "usd": month["usd"], "cap": month["cap"],
               "basis": month["cap_basis"], "projection": month["projection"],
               "last_day": f"{last.day} {MONTHS[last.month - 1]}",
               "bar": _bar(m_ratio), "bar_projected": max(0, _bar(proj_ratio) - _bar(m_ratio))},
        features=[_feature(f) for f in p["features"]])
