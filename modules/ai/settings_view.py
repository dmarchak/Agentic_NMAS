"""Settings › Installation › AI: what its background-features section draws (board AI3,
`SettingsAi`, and AI3b, `SettingsAiOn`, on the mockups canvas's page "C1843: AI cost safety",
signed off under the Phase 7 mode 2026-10-27; PHASE8_PLAN 18.3 rules 2 to 4).

One network at a time (a network never inherits another's switch): each background feature
Mercury knows (`background.FEATURES`) with its state, read from the switches and the record of
AI calls, never guessed:

- ``off``: never turned on, or turned off.
- ``on``: in force, with who turned it on and when, when its approval ends (`APPROVAL_DAYS`),
  its caps, today's and the month's spend against them, and its estimate against actual.
- ``stopped``: on, and the gateway refused a call this period for its day or month cap
  (`spend.feature_summaries`), naming which and when.
- ``ended``: switched on, and its approval ended; the gateway refuses its calls until an admin
  turns it on again.

Its spend reads the month's window of the record once. An unreadable record is said, and the
spend is drawn as unknown (the gateway refuses every background call then).

The master switch, the key and the installation's day cap are the AI (hosted) card's, which moved
from the Connections tab to this tab whole (decision 1, C1953: `installation_settings.CARDS`,
drawn above this section); the features a person presses have no switch yet
(docs/STANDING_APPROVAL_LOG.md, "Settings › AI built").
"""
import logging
import time

log = logging.getLogger(__name__)

#: Where the master switch, the key and the installation's day cap are set: the AI (hosted)
#: card, first on this tab (C1953).
CARD_HREF = "/v2/settings/installation?tab=ai#card-ai"
#: The steps turning a background feature on runs, in order (the manual's How it works page
#: names each): the estimate shown with its digest, the person's acceptance and caps checked,
#: the estimate measured again and compared, the switch written, the decision recorded.
TURN_ON_STEPS = (("estimate", "the estimate is shown, labelled, with its digest"),
                 ("check", "a verified person, the acceptance ticked, the caps within the "
                           "installation's day cap"),
                 ("compare", "the estimate measured again and compared with the one shown"),
                 ("write", "the switch written with who, when, the estimate and the caps"),
                 ("record", "the decision recorded in the installation's settings record"))


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch)) if epoch else ""


def pick(d: dict, *keys) -> dict:
    """Only *keys* of *d*: a screen is handed what it draws (CLAUDE.md, "Every carried field is
    drawn")."""
    return {k: d.get(k) for k in keys}


def drawn_entry(entry: dict, *extra) -> dict:
    """A switch's entry as the screen draws it: who turned it on, when, the accepted
    estimate's digest and dollars a day, and *extra* keys an answer draws."""
    est = entry.get("estimate") if isinstance(entry.get("estimate"), dict) else {}
    return dict(pick(entry, "by", "at", *extra), estimate=pick(est, "digest", "usd_per_day"))


def _drawn_summary(s: dict) -> dict:
    """A feature's spend summary (`spend.feature_summaries`) as its row draws it."""
    return dict(pick(s, "fractions", "stopped", "stopped_at", "actual_usd_per_day",
                     "actual_days", "ratio"),
                spent=pick(s.get("spent") or {}, "day_usd", "month_usd"))


def networks() -> list:
    """Every network's name, sorted (`listref.names`)."""
    from modules.nsot import listref

    return listref.names()


def chosen(network: str) -> str:
    """*network* when it is a network Mercury holds (by its name or its folder's), else the
    viewer's active one."""
    from modules.nsot import listref

    every = networks()
    if network and network in every:
        return network
    if network:
        try:
            got = listref.display_name(network)
        except Exception:                                       # noqa: BLE001 (not one)
            got = ""
        if got in every:
            return got
    return listref.active_name()


def view(network: str = "", now=None) -> dict:
    """``{"network", "slug", "networks", "hosted_allowed", "day_cap", "spend_state", "spend_error",
    "features", "elsewhere"}`` for Settings › AI's background section on *network* (its name;
    empty or unknown: the active network)."""
    from modules.ai import background, calls, gateway, spend
    from modules.nsot import listref

    name = chosen(network)
    slug = listref.network_id(name)
    zone = calls.boundary()
    today = calls.today(now, zone)
    got = calls.rows_since(spend.month_start(today, zone))
    readable = got.get("state") != "unreadable"
    sums = {}
    if readable:
        for s in spend.feature_summaries(got.get("rows") or [], today, zone, now):
            sums[(s["network"], s["feature"])] = s
    raw = background.switches().get(slug, {})
    features = []
    for fname, spec in background.FEATURES.items():
        entry = raw.get(fname)
        on = isinstance(entry, dict) and entry.get("on") is True
        ends = background.approval_ends(entry) if on else None
        s = sums.get((slug, fname))
        if not on:
            state = "off"
        elif not background.in_force(entry):
            state = "ended"
        elif s and (s["stopped"]["day"] or s["stopped"]["month"]):
            state = "stopped"
        else:
            state = "on"
        features.append({
            "name": fname, "words": spec.get("words", fname),
            "trigger_words": spec.get("trigger_words", ""),
            "calls_per_finding": int(spec.get("calls_per_finding") or 1),
            "state": state, "entry": drawn_entry(entry) if on else None,
            "ends_iso": _iso(ends), "summary": _drawn_summary(s) if s else None,
            "caps": background.caps_of(entry) if on else None,
            # Within RENEW_DAYS of its approval's end, or past it: Turn on again… (C1953).
            "renew": bool(on and background.renewal_due(entry, now)),
        })
    every = networks()
    named = {}
    for n in every:
        try:
            named[listref.network_id(n)] = n
        except Exception:                                       # noqa: BLE001 (its folder said)
            continue
    elsewhere = [dict(pick(s, "words", "stopped", "stopped_at"), network_name=named.get(n, n))
                 for (n, _f), s in sorted(sums.items())
                 if n != slug and (s["stopped"]["day"] or s["stopped"]["month"])]
    return {"network": name, "slug": slug, "networks": every,
            "hosted_allowed": bool(gateway.hosted_allowed()["allowed"]),
            "day_cap": gateway.day_cap(),
            "spend_state": "ok" if readable else "unreadable",
            "spend_error": "" if readable else got.get("error", ""),
            "features": features, "elsewhere": elsewhere,
            "approval_days": background.APPROVAL_DAYS, "renew_days": background.RENEW_DAYS,
            "card_href": CARD_HREF}


def turn_on_form(network: str, feature: str, now=None) -> dict:
    """The Turn on… form's answer: the network, the feature's spec, the estimate (labelled,
    its digest the one the form sends back), the installation's day cap the caps must be
    within, the caps it offers (the estimate's suggestion, or none when unknown: the person
    types them), and when the approval would end."""
    from modules.ai import background, gateway, profiles
    from modules.nsot import listref

    name = chosen(network)
    spec = background._spec(feature)
    est = background.estimate(listref.network_id(name), feature, now)
    sug = est.get("suggested") or {}
    return {"network": name, "feature": feature, "words": spec.get("words", feature),
            "trigger_words": spec.get("trigger_words", ""), "est": est,
            "day_cap": gateway.day_cap(), "prices_as_of": profiles.PRICES_AS_OF,
            "day_value": sug.get("day_cap_usd"), "month_value": sug.get("month_cap_usd"),
            "ends_iso": _iso(time.time() + background.APPROVAL_DAYS * 86400),
            "approval_days": background.APPROVAL_DAYS, "renew_days": background.RENEW_DAYS}


def caps_value(text):
    """A cap typed in the form: "$0.50", "0.5" or "1,000" as a number; anything else is
    passed as typed, so `background` refuses it naming what was given."""
    t = (text or "").strip().replace("$", "").replace(",", "").strip()
    try:
        return float(t)
    except ValueError:
        return text
