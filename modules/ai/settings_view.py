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
                 ("record", "the decision recorded in the installation's settings record, "
                            "with the open incidents ticked and left unticked"),
                 ("catch_up", "for automatic AI troubleshooting, each ticked open incident "
                              "started once, as its own job, within the caps"))


#: Background features drawn elsewhere than this list (C3769): automatic AI troubleshooting
#: is the AI troubleshooting card's Automatic.
HIDDEN = ("fixit_auto",)
#: Background features retired from this list (C3769): drawn only while one is still on, so it
#: can be turned off.
RETIRED = ("heal_analysis",)


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
        # C3769 (Gate 2): automatic AI troubleshooting is no row of its own here: it is the
        # AI troubleshooting card's Automatic, with its limits (`troubleshoot.view`, drawn
        # above). The can't-fix analysis is retired from this list (folded into the
        # investigation's findings): drawn only while a switch of it is still on, so it can be
        # turned off; its kept records stay readable.
        if fname in HIDDEN or (fname in RETIRED and not on):
            continue
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
    # C3769: the network's one AI troubleshooting control, its limits and their estimate.
    from modules import troubleshoot_control as troubleshoot
    try:
        ts = troubleshoot.view(name, now=now)
    except Exception as exc:                                    # noqa: BLE001 (said in place)
        ts = {"error": f"{type(exc).__name__}: {exc}", "network": name,
              "card_id": troubleshoot.CARD_ID}
    return {"network": name, "slug": slug, "networks": every, "troubleshoot": ts,
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

    from modules.fixit import auto as A

    name = chosen(network)
    spec = background._spec(feature)
    est = background.estimate(listref.network_id(name), feature, now)
    sug = est.get("suggested") or {}
    day, month = sug.get("day_cap_usd"), sug.get("month_cap_usd")
    audit = feature == A.FEATURE
    if audit:
        # Gate 2 (C3769): for automatic AI troubleshooting this form is read-only, for audit:
        # what Automatic would start and why, held against the network's own limits as set
        # on its AI troubleshooting card (none set: the estimate's suggestion, said so).
        caps = background.caps_of(background.record_of(listref.network_id(name), feature))
        if caps["day"] and caps["month"]:
            day, month = caps["day"], caps["month"]
    return {"network": name, "feature": feature, "words": spec.get("words", feature),
            "trigger_words": spec.get("trigger_words", ""), "est": est,
            "day_cap": gateway.day_cap(), "prices_as_of": profiles.PRICES_AS_OF,
            "day_value": day, "month_value": month,
            "ends_iso": _iso(time.time() + background.APPROVAL_DAYS * 86400),
            "approval_days": background.APPROVAL_DAYS, "renew_days": background.RENEW_DAYS,
            "catch_up": catch_up_view(name, day, month) if audit else None}


def catch_up_view(network: str, day_typed=None, month_typed=None) -> dict:
    """Turn on…'s list for automatic AI troubleshooting (the operator, 2026-11-15: "Turning it
    on shows the list first ("starts on these N open incidents, about $X"), each tickable"):
    ``{"state", "error", "incidents", "failed", "usd_each", "usd_total", "measured", "basis",
    "incident_cap", "day_cap", "least", "room", "fit_words", "room_words"}`` (*least* the least
    one call costs, `fixit_troubleshoot.start_usd`; the last four how
    many fit under each cap, C3745, with the feature's caps as *day_typed* and *month_typed*),
    each incident ``{"id", "device", "title", "why", "why_kind",
    "at", "usd", "cap_words", "href"}``, ticked by default. The list is R1's own
    (`auto.catch_up`); each item's estimate is one investigation's (`fixit_troubleshoot.
    estimate`: the measured mean, or its worst case said), and *cap_words* says when its
    incident's cap would be passed already. A read: nothing is asked or started."""
    from modules import troubleshoot_job
    from modules.ai import fixit_troubleshoot as AIT
    from modules.ai import gateway
    from modules.fixit import auto as A
    from modules.fixit import policy as P
    from modules.heal_notice import follow_up_wait_s

    got = A.catch_up(network, bound_s=follow_up_wait_s())
    est = AIT.estimate()
    # Each start held to the least one call costs (`start_usd`): no worst case any more (the
    # operator, 2026-11-16); the gateway judges each call's counted prompt and typical output.
    worst = AIT.start_usd()
    items = []
    for i in got["items"]:
        cs = P.cap_state(i["incident"], worst)
        items.append({"id": i["id"], "device": i["device"], "title": i["title"],
                      "why": i["why"], "why_kind": i["why_kind"], "at": i["failure"]["at"],
                      "usd": est["usd"],
                      "cap_words": ("" if cs["state"] == "allowed" else
                                    "its incident's AI cap would be passed, so it would not "
                                    "start"),
                      "href": troubleshoot_job.page_of(network, i["id"])})
    cap = P.cap_usd(network)
    day = gateway.day_cap()
    room = catch_up_room(network)
    rooms = rooms_of(room, day_typed, month_typed)
    fit = catch_up_fit([not i["cap_words"] for i in items], worst, rooms)
    return {"state": got["state"], "error": got.get("error") or "", "incidents": items,
            "failed": list(got.get("failed") or []), "usd_each": est["usd"],
            "usd_total": round(est["usd"] * len(items), 6), "measured": est["measured"],
            "basis": est["basis"],
            "incident_cap": P.money(cap["usd"]) if cap["state"] == "ok" else "",
            "day_cap": P.money(day) if day is not None else "",
            # How many fit under each cap (C3745), redrawn by the browser as the ticks and the
            # typed caps change (nmas_apply.js `catchUpFit`, the same arithmetic).
            "least": worst, "room": room,
            "fit_words": fit_words(fit, len(items)), "room_words": room_words(fit, rooms, worst)}


#: Each cap a catch-up start is held against, in the order they are asked (C3745), and how the
#: list names it. ``incident`` is each incident's own; the others are shared by every start.
FIT_LABELS = {"incident": "its incident's cap", "day": "the day cap",
              "feature_day": "this feature's day cap", "feature_month": "its month cap"}
#: The room words' tail for each shared cap.
ROOM_TAIL = {"day": "left today", "feature_day": "left as typed",
             "feature_month": "left as typed"}


def catch_up_room(network: str) -> dict:
    """What is left under each shared cap before the turn-on, for the list (C3745):
    ``{"day", "feature_day_spent", "feature_month_spent"}``, *day* the installation's day cap
    less today's spend (None with no day cap; 0 when the spend cannot be read, as a start is
    then refused), and this feature's spend today and this month on *network*, which the caps
    typed in the form are measured against. A read of the settings and the record of calls."""
    from modules.ai import calls, gateway, reservations, spend
    from modules.fixit import auto as A
    from modules.nsot import listref

    # C3753: the calls in flight are counted, as the gateway and the start count them; an
    # unreadable store leaves no room (a start is then refused), never read as none.
    open_ = reservations.open_reservations()
    readable = open_["state"] == "ok"
    flying = reservations.in_flight(open_["held"]) if readable else {"usd": 0.0}
    net = listref.network_id(network)
    mine_flying = (reservations.in_flight(open_["held"], feature=A.FEATURE, network=net)
                   if readable else {"usd": 0.0})
    cap = gateway.day_cap()
    day = None
    if cap is not None:
        got = calls.spent_usd(calls.today())
        day = (max(0.0, cap - float(got["usd"]) - float(flying["usd"]))
               if got.get("usd") is not None and readable else 0.0)
    mine = spend.feature_spent(net, A.FEATURE)
    ok = mine.get("state") != "unreadable" and readable
    held = float(mine_flying["usd"])
    return {"day": day,
            "feature_day_spent": float(mine.get("day_usd") or 0) + held if ok else None,
            "feature_month_spent": float(mine.get("month_usd") or 0) + held if ok else None}


def rooms_of(room: dict, day_typed, month_typed) -> list:
    """``[(cap, room)]`` for `catch_up_fit`: the day cap's room, and the feature's day and month
    caps as typed less its spend (``"unknown"`` when not typed as a positive amount, or its
    spend cannot be read)."""
    def typed(v, spent):
        v = caps_value(v) if isinstance(v, str) else v
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0
        return max(0.0, float(v) - spent) if ok and spent is not None else "unknown"
    return [("day", room["day"]), ("feature_day", typed(day_typed, room["feature_day_spent"])),
            ("feature_month", typed(month_typed, room["feature_month_spent"]))]


def catch_up_fit(oks, worst: float, rooms) -> dict:
    """How many of the ticked fit (C3745), in tick order: *oks* each ticked one's own cap
    (True when its incident's cap allows it), *rooms* ``[(cap, room)]``, a room None for no cap
    or ``"unknown"`` (not typed). ``{"start", "refused_incident", "refused_cap", "binding",
    "slots", "unknown"}``: a start counts against every shared cap, so each cap holds
    ``floor(room / worst)`` starts; the later ones past the smallest are refused at it
    (*binding*). The arithmetic `heal_notice.start_catch_up` refuses by, and nmas_apply.js's
    `catchUpFit` draws by."""
    import math

    unknown = [c for c, r in rooms if r == "unknown"]
    slots = {c: (None if r is None or r == "unknown" else
                 max(0, int(math.floor(float(r) / float(worst) + 1e-9)))) for c, r in rooms}
    limit = min([s for s in slots.values() if s is not None], default=None)
    start = ri = rc = 0
    for ok in oks:
        if not ok:
            ri += 1
        elif limit is None or start < limit:
            start += 1
        else:
            rc += 1
    binding = next((c for c, _r in rooms if slots[c] == limit), "") if rc else ""
    return {"start": start, "refused_incident": ri, "refused_cap": rc, "binding": binding,
            "slots": slots, "unknown": unknown}


def fit_words(fit: dict, n: int) -> str:
    """The list's line of what fits under the caps (C3745): mirrored by nmas_apply.js's
    `catchUpFitWords`, word for word."""
    if fit["unknown"]:
        return "Type this feature's day and month caps to see how many fit under them."
    if not n:
        return "None ticked: nothing starts."
    if not fit["refused_incident"] and not fit["refused_cap"]:
        return ("The ticked one fits under every cap." if n == 1 else
                f"All {n} ticked fit under every cap.")
    parts = [f"{fit['start']} of the {n} ticked fit under the caps"]
    if fit["refused_cap"]:
        parts.append(f"the later {fit['refused_cap']} would pass "
                     f"{FIT_LABELS[fit['binding']]}")
    if fit["refused_incident"]:
        parts.append(f"{fit['refused_incident']} would pass "
                     f"{'its' if fit['refused_incident'] == 1 else 'their'} incident's cap")
    return "; ".join(parts) + ": refused before anything starts, each page naming the cap."


def room_words(fit: dict, rooms, worst: float) -> str:
    """What is left under each shared cap, and how many starts that holds (C3745): mirrored by
    nmas_apply.js's `catchUpRoomWords`."""
    from modules.money import usd

    said = []
    for cap, room in rooms:
        if room is None:
            said.append(f"no limit under {FIT_LABELS[cap]} (none is set)")
        elif room == "unknown":
            said.append(f"{FIT_LABELS[cap]}: type it")
        else:
            said.append(f"{fit['slots'][cap]} under {FIT_LABELS[cap]} ({usd(room)} "
                        f"{ROOM_TAIL[cap]})")
    return f"Room, each start at least {usd(worst)}: " + ", ".join(said) + "."


def caps_value(text):
    """A cap typed in the form: "$0.50", "0.5" or "1,000" as a number; anything else is
    passed as typed, so `background` refuses it naming what was given."""
    t = (text or "").strip().replace("$", "").replace(",", "").strip()
    try:
        return float(t)
    except ValueError:
        return text
