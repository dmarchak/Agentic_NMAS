"""AI troubleshooting, ONE control per network: Off, Manual or Automatic (C3769, Gate 2; the
operator's minimal design, 2026-11-15).

- **Off**: nothing is offered or started; Mercury's own diagnosis still proposes a fix.
- **Manual**: an AI investigation runs only on a verified person's press, on an incident's page.
- **Automatic**: Manual, and when Mercury's fix fails the AI investigates by itself, once per
  failure (R1, ``fixit_auto``: `modules/fixit/auto.py`, `heal_notice.run_fixit`), within the
  network's spending limits.

**Where each part lives (no second store).** The mode Off or Manual is the network's own value
in its ``fixit_auto`` record (`background.OWN_FIELDS`), else the installation's
``ai_troubleshoot_mode`` (`fixit.policy.mode`, expand then contract). Automatic is that record's
switch (`background.turn_on`, `turn_off`): never stored as a mode, so the switch stays the one
owner of whether anything starts by itself. The spending limits are the record's day and month
caps (`background.caps_of`, which the gateway's `over_cap` holds every automatic call to), its
per-incident cap (``incident_cap_usd``, else the installation's `ai_cap_usd_per_incident`:
`fixit.policy.cap_usd`), all inside the installation's day cap (`gateway.day_cap`).

**The estimate is acknowledged with the limits, in Settings, once** (`set_limits`): the person
sets per incident, per day and per month, sees the estimate beside them (calls a day, cost per
call, a month: `background.estimate`) and acknowledges it; the acknowledgement records the
limits' digest and the cost per call shown (``limits_ack``, with the estimate's digest kept as
the record of what was shown). That is the background-AI estimate rule (CLAUDE.md, "AI cost
safety"), so the switch does not show it again. **It binds the limits and the cost per call,
never the frequency** (the operator's correction, 2026-11-15, C3770's option (a)): the
frequency moves with every new failure, and is drawn beside it now, unbound. It holds until a
limit changes or the measured cost per call passes `spend.OVER_ESTIMATE_AT` (1.5) times the
acknowledged figure (`cost_drift`); turning Automatic on is refused then (`readiness`, naming
what moved, its refusal linking to the limits card), and otherwise turns on with the estimate
as measured now (`background.turn_on`, which records it).

**Turning Automatic on starts on the open incidents with no fix** (`catch_up_line`, then
`heal_notice.start_catch_up`): every open incident R1 would have started on had it been on when
the fix failed (`auto.catch_up`), all of them, each planned against every cap before any starts
(C3745), the ones past a cap refused and named on their own card. The switch draws one line
before the press ("Also starts on N open incidents, about $X") and the press is bound to it by
its digest: a list that moved since is refused, naming both.

Reads, and the writes named; nothing here calls the model or holds a device. The starts are
`heal_notice.start_catch_up`'s, each its own job.
"""

import hashlib
import json
import logging
import math
import time
from urllib.parse import quote

log = logging.getLogger(__name__)

#: The levels, as the control draws them and the route takes them.
LEVELS = ("off", "manual", "automatic")
LEVEL_WORDS = {"off": "Off", "manual": "Manual", "automatic": "Automatic",
               "unknown": "Not known"}
#: What each level does, in the control's own words.
LEVEL_SAYS = {"off": "nothing is offered or started; Mercury's own diagnosis still proposes "
                     "a fix",
              "manual": "the AI investigates only when a person presses Start AI "
                        "troubleshooting on an incident's page",
              "automatic": "when Mercury's fix fails, the AI investigates by itself, within "
                           "this network's spending limits; it only proposes, and a person "
                           "approves"}
#: The Settings card's element id: the switch's refusal links here.
CARD_ID = "ai-ts"
#: The steps setting the limits and turning Automatic on run, as the manual names them.
LIMITS_STEPS = (("person", "a verified person"),
                ("acknowledge", "the estimate acknowledged with the limits"),
                ("check", "each limit a positive amount, the day within the installation's day "
                          "cap"),
                ("compare", "the estimate measured again and compared with the one shown"),
                ("write", "the limits and the acknowledgement written in the network's record"),
                ("record", "recorded in the installation's settings record, old and new"))
AUTOMATIC_STEPS = (("ready", "the limits and their estimate acknowledged and unchanged since"),
                   ("line", "the open incidents it starts on, as the line drew them"),
                   ("mode", "the network's mode set to Manual if it was Off"),
                   ("switch", "the switch turned on with the acknowledged estimate and limits, "
                              "recorded with every open incident it starts on"),
                   ("start", "each open incident started once, as its own job, planned against "
                             "every cap before any starts; one past a cap refused, named on its "
                             "card"))


class Refused(ValueError):
    """Nothing was changed; the words name what was compared and both values. *href*, when
    set, is where the person goes to fix it (the limits card)."""

    def __init__(self, words: str, href: str = ""):
        super().__init__(words)
        self.href = href


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _feature() -> str:
    from modules.fixit import auto as A

    return A.FEATURE


def _name(network: str) -> str:
    from modules.ai.settings_view import chosen

    return chosen(network)


def _slug(network: str) -> str:
    from modules.ai import background

    try:
        return background._network(network)
    except background.Refused as exc:
        raise Refused(str(exc)) from None


def _person(actor: str) -> None:
    """A verified person, or Refused naming who asked (`background._person`'s check)."""
    from modules.ai import background

    try:
        background._person(actor)
    except background.Refused as exc:
        raise Refused(str(exc)) from None


def limits_href(network: str) -> str:
    """The limits card, on Settings › AI for *network*."""
    return f"/v2/settings/installation?tab=ai&network={quote(network)}#{CARD_ID}"


def audit_href(network: str) -> str:
    """The detailed form (the operator's item 3: "what will this start, and why"), for audit:
    Settings › AI's own Turn on… of the feature, its list and caps in full."""
    return (f"/v2/settings/installation/ai/background/{quote(network)}/{_feature()}/on")


def limits_digest(incident_usd, day_usd, month_usd) -> str:
    """The digest of a network's three limits, as acknowledged."""
    body = {"incident": round(float(incident_usd), 6) if incident_usd is not None else None,
            "day": round(float(day_usd), 6) if day_usd is not None else None,
            "month": round(float(month_usd), 6) if month_usd is not None else None}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def record_limits_digest(rec: dict) -> str:
    """The digest of the limits a network's record holds now (its own per-incident limit, its
    day and month caps): what `background.turn_on` compares, under the settings lock, with the
    digest read before (Gate 2's review). "" when a limit is not set."""
    from modules.ai import background

    caps = background.caps_of(rec)
    inc = rec.get("incident_cap_usd")
    ok = isinstance(inc, (int, float)) and not isinstance(inc, bool) and inc > 0
    if not (ok and caps["day"] and caps["month"]):
        return ""
    return limits_digest(inc, caps["day"], caps["month"])


def level(network: str) -> dict:
    """``{"level", "words", "says", "source", "error", "switch"}``: *network*'s AI
    troubleshooting now. *level* is ``unknown`` when the mode cannot be read; *source* says
    whose mode it is (``network`` or ``installation``); *switch* is `auto.switch`'s."""
    from modules.fixit import auto as A
    from modules.fixit import policy as P

    name = _name(network)
    got = P.mode(name)
    sw = A.switch(name)
    if got["state"] != "ok":
        lvl = "unknown"
    else:
        lvl = "off" if got["mode"] == "off" else "automatic" if sw["on"] else "manual"
    return {"level": lvl, "words": LEVEL_WORDS[lvl], "says": LEVEL_SAYS.get(lvl, ""),
            "source": got.get("source") or "", "error": got.get("error") or "", "switch": sw}


def _ack(rec: dict):
    ack = rec.get("limits_ack")
    return ack if isinstance(ack, dict) and ack.get("estimate_digest") else None


def cost_drift(ack: dict, est: dict) -> str:
    """Why the acknowledgement *ack* no longer holds for the estimate *est* now, or ``""``
    (the operator's Gate 2 correction, 2026-11-15, C3770's option (a)): it binds the limits and
    the cost per call it was shown, never the frequency, which moves with every new failure. It
    holds until the measured cost per call passes `spend.OVER_ESTIMATE_AT` (1.5) times the
    acknowledged figure; a cost that cannot be compared (none acknowledged, none now) asks
    again, never read as within."""
    from modules.ai import spend

    was = ack.get("usd_per_call")
    now = (est.get("cost") or {}).get("usd_per_call")
    ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
             for v in (was, now))
    if not ok or was <= 0:
        return (f"the cost per call acknowledged ({was!r}) cannot be compared with the one "
                f"measured now ({now!r}): acknowledge the limits again in Settings › AI")
    if now > was * spend.OVER_ESTIMATE_AT:
        from modules.money import usd
        return (f"the measured cost per call {usd(now, exact=True)} passed "
                f"{spend.OVER_ESTIMATE_AT:g} times the {usd(was, exact=True)} acknowledged "
                f"(over {usd(was * spend.OVER_ESTIMATE_AT, exact=True)}): look at the estimate "
                "again and acknowledge the limits in Settings › AI")
    return ""


def readiness(network: str, est: dict = None) -> str:
    """``""`` when Automatic may be turned on for *network*, else why not: its limits and their
    estimate are not acknowledged, a limit is not set, a limit changed since it was
    acknowledged, or the estimate moved since (each naming both digests). A read."""
    got = limits(network, est=est)
    return got["ready"]


def limits(network: str, now=None, est: dict = None) -> dict:
    """The limits card's model for *network*: ``{"network", "incident", "day", "month",
    "installation", "estimate", "ack", "ready", "digest"}``. *incident* is ``{"usd", "source",
    "error"}`` (the network's own, else the installation's); *day* and *month* the record's
    caps (None while never set); *installation* the defaults beside them (the per-incident cap,
    the day cap every call is held to); *estimate* `background.estimate`'s; *ack* who
    acknowledged what and when, or None; *ready* `readiness`'s words. A read."""
    from modules.ai import background, gateway
    from modules.fixit import policy as P

    name = _name(network)
    slug = _slug(name)
    rec = background.record_of(slug, _feature())
    inc = P.cap_usd(name)
    inst = P.cap_usd()
    caps = background.caps_of(rec) if any(k in rec for k in ("day_cap_usd",
                                                             "month_cap_usd")) else \
        {"day": None, "month": None}
    est = est or background.estimate(slug, _feature(), now)
    ack = _ack(rec)
    digest = limits_digest(inc["usd"], caps["day"], caps["month"]) \
        if inc["state"] == "ok" and caps["day"] and caps["month"] else ""
    if ack is None:
        ready = ("its spending limits and their estimate are not acknowledged yet for "
                 f"{name}: set them, with the estimate beside them, in Settings › AI")
    elif not digest:
        ready = (f"{name}'s spending limits are not all set (per incident "
                 f"{P.money(inc['usd']) if inc['usd'] else inc['error'] or 'none'}, per day "
                 f"{P.money(caps['day']) if caps['day'] else 'none'}, per month "
                 f"{P.money(caps['month']) if caps['month'] else 'none'})")
    elif ack.get("limits_digest") != digest:
        ready = (f"{name}'s spending limits changed since they were acknowledged "
                 f"(acknowledged {str(ack.get('limits_digest') or 'none')[:12]}, now "
                 f"{digest[:12]}): acknowledge them again in Settings › AI")
    elif cost_drift(ack, est):
        ready = cost_drift(ack, est)
    else:
        ready = ""
    return {"network": name, "slug": slug, "incident": inc,
            "day": caps["day"], "month": caps["month"],
            "installation": {"incident": inst["usd"], "incident_error": inst["error"],
                             "day_cap": gateway.day_cap()},
            "estimate": est, "ack": ack, "ready": ready, "digest": digest,
            "href": limits_href(name)}


def _amount(value, what: str) -> float:
    ok = (isinstance(value, (int, float)) and not isinstance(value, bool)
          and math.isfinite(value) and value > 0)
    if not ok:
        raise Refused(f"the {what} limit {value!r} is not a positive amount in US dollars; "
                      "nothing was changed")
    return float(value)


def set_limits(network: str, *, incident_usd, day_usd, month_usd, shown: str, accepted: bool,
               actor: str, verified: str, now=None) -> dict:
    """Set *network*'s three spending limits and acknowledge the estimate drawn beside them
    (`LIMITS_STEPS`), an admin's decision: refused, naming why, with nothing changed, for anyone
    but a verified person, an estimate not acknowledged, a limit that is not a positive amount,
    a day limit over the installation's day cap, or an estimate that moved since it was shown
    (both digests named). With the switch on, its caps change at once (as Change caps did). The
    approval it gives does not end (C3770's option a is the operator's): the switch's own
    approval does. ``{"ok", "entry", "recorded", ...}``."""
    from modules.ai import background

    _person(actor)
    if not accepted:
        raise Refused("the estimate was not acknowledged: tick “I have read the estimate” with "
                      "the limits; nothing was changed")
    name = _name(network)
    slug = _slug(name)
    inc = _amount(incident_usd, "per-incident")
    try:
        caps = background._caps(day_usd, month_usd)
    except background.Refused as exc:
        raise Refused(str(exc)) from None
    est = background.estimate(slug, _feature(), now)
    if est["digest"] != shown:
        raise Refused(f"the estimate moved since it was shown (shown {str(shown)[:12] or 'none'}, "
                      f"now {est['digest'][:12]}): look at it again and acknowledge it; nothing "
                      "was changed")
    at = _iso(time.time())
    digest = limits_digest(inc, caps["day"], caps["month"])
    ack = {"by": actor, "verified": verified, "at": at, "estimate_digest": est["digest"],
           "limits_digest": digest, "calls_per_day": est.get("calls_per_day"),
           "usd_per_call": (est.get("cost") or {}).get("usd_per_call"),
           "usd_per_day": est.get("usd_per_day"), "usd_per_month": est.get("usd_per_month")}
    try:
        out = background.update_record(
            slug, _feature(),
            {"incident_cap_usd": inc, "day_cap_usd": caps["day"], "month_cap_usd": caps["month"],
             "caps_by": actor, "caps_at": at, "limits_ack": ack},
            kind="ai_troubleshoot_limits", actor=actor, verified=verified, estimate=est,
            incident_cap_usd=inc, day_cap_usd=caps["day"], month_cap_usd=caps["month"])
    except background.Refused as exc:
        raise Refused(str(exc)) from None
    log.info("ai troubleshooting: %s set %s's limits and acknowledged estimate %s", actor, slug,
             est["digest"][:12])
    return out


def catch_up_line(network: str, now: float = None) -> dict:
    """The one line the switch draws before Automatic is turned on (the operator, 2026-11-15:
    "Also starts on N open incidents, about $X"): ``{"state", "error", "ids", "n",
    "usd_each", "usd", "words", "digest"}``, from R1's own list (`auto.catch_up`) and one
    investigation's estimate (`fixit_troubleshoot.estimate`); *digest* binds the press to it.
    Empty *words* with no open incident to start on. A read."""
    from modules.ai import fixit_troubleshoot as AIT
    from modules.fixit import auto as A
    from modules.heal_notice import follow_up_wait_s
    from modules.money import usd

    name = _name(network)
    got = A.catch_up(name, now=now, bound_s=follow_up_wait_s())
    ids = [i["id"] for i in got["items"]]
    each = float(AIT.estimate()["usd"] or 0.0)
    total = round(each * len(ids), 6)
    words = "" if not ids else (f"Also starts on {len(ids)} open incident"
                                f"{'' if len(ids) == 1 else 's'}, about {usd(total)}")
    body = {"ids": sorted(ids), "each": round(each, 6)}
    return {"state": got["state"], "error": got.get("error") or "", "ids": ids, "n": len(ids),
            "usd_each": each, "usd": total, "words": words,
            "digest": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()}


def _set_mode(name: str, slug: str, mode: str, *, actor: str, verified: str) -> dict:
    from modules.ai import background

    try:
        return background.update_record(slug, _feature(), {"mode": mode},
                                        kind="ai_troubleshoot_mode", actor=actor,
                                        verified=verified, mode=mode, network_name=name)
    except background.Refused as exc:
        raise Refused(str(exc)) from None


def set_level(network: str, lvl: str, *, shown: str = "", actor: str, verified: str,
              now: float = None) -> dict:
    """Set *network*'s AI troubleshooting to *lvl* (an admin's decision; the Settings card's
    three choices and the control strip's switch, on Automatic and off back to Manual, are this
    one path). ``{"ok", "level", "nothing", "caught", "line", "words"}``; raises Refused naming
    why, with nothing changed (its *href* the limits card when the limits are why).

    Automatic (`AUTOMATIC_STEPS`): refused until the limits and their estimate are acknowledged
    and unchanged since (`readiness`), and when the open incidents it would start on moved since
    the line was drawn (*shown*, `catch_up_line`'s digest); then the mode set to Manual where it
    was Off, the switch turned on with the acknowledged estimate and limits (the list recorded
    with it), and every listed incident started within the caps (`heal_notice.start_catch_up`,
    inside the press's request). Manual and Off: the switch off when it was on (one press, no
    confirm: it spends nothing), and the network's own mode written where it differs."""
    from modules.ai import background
    from modules.fixit import policy as P

    _person(actor)
    if lvl not in LEVELS:
        raise Refused(f"AI troubleshooting's levels are {', '.join(LEVEL_WORDS[x] for x in LEVELS)}"
                      f", and {lvl!r} was sent; nothing was changed")
    name = _name(network)
    slug = _slug(name)
    cur = level(name)
    if lvl == "automatic":
        got = limits(name, now=now)
        if got["ready"]:
            raise Refused(f"Automatic was not turned on: {got['ready']}", href=got["href"])
        line = catch_up_line(name, now=now)
        if line["state"] != "ok":
            raise Refused(f"Automatic was not turned on: the open incidents it would start on "
                          f"cannot be read ({line['error']}); nothing was changed")
        if shown != line["digest"]:
            raise Refused(f"Automatic was not turned on: the open incidents it starts on moved "
                          f"since the line was drawn (drawn {str(shown)[:12] or 'none'}, now "
                          f"{line['digest'][:12]}: {line['words'] or 'none to start on'}); read "
                          "it again; nothing was changed")
        moved = cur["level"] in ("off", "unknown")
        if moved:
            _set_mode(name, slug, "manual", actor=actor, verified=verified)
        try:
            out = background.turn_on(
                slug, _feature(), day_cap_usd=got["day"], month_cap_usd=got["month"],
                shown=got["estimate"]["digest"], actor=actor, verified=verified, now=now,
                limits=(got["digest"], record_limits_digest),
                catch_up={"ticked": list(line["ids"]), "unticked": [],
                          "usd_each": line["usd_each"] if line["ids"] else 0.0,
                          "usd_total": line["usd"]})
        except background.Refused as exc:
            raise Refused(f"Automatic was not turned on: {exc}"
                          + ("; its mode was set to Manual first, and stays Manual" if moved
                             else ""), href=got["href"]) from None
        caught = None
        if line["ids"]:
            from modules import heal_notice
            caught = heal_notice.start_catch_up(name, line["ids"], actor=actor,
                                                verified=verified, now=now)
        return {"ok": True, "level": "automatic", "nothing": False, "caught": caught,
                "line": line, "entry": out.get("entry"), "words": started_words(caught)}
    did = False
    if cur["switch"]["on"]:
        try:
            background.turn_off(slug, _feature(), actor=actor, verified=verified)
        except background.Refused as exc:
            raise Refused(str(exc)) from None
        did = True
    if P.mode(name).get("mode") != lvl:
        _set_mode(name, slug, lvl, actor=actor, verified=verified)
        did = True
    words = (f"AI troubleshooting is {LEVEL_WORDS[lvl]} on {name}: {LEVEL_SAYS[lvl]}"
             + ("; an investigation already running finishes"
                if cur["switch"]["on"] else ""))
    return {"ok": True, "level": lvl, "nothing": not did, "caught": None, "line": None,
            "words": words if did else f"AI troubleshooting was already {LEVEL_WORDS[lvl]} "
                                       f"on {name}; nothing was written"}


def started_words(caught) -> str:
    """What turning Automatic on did, in one line: how many it started and how many a cap or a
    choice stopped (each card names its own)."""
    base = "Automatic is on: when Mercury's fix fails, the AI investigates by itself"
    if not caught:
        return base
    parts = []
    if caught.get("started"):
        n = len(caught["started"])
        parts.append(f"started on {n} open incident{'' if n == 1 else 's'} now")
    if caught.get("capped"):
        n = len(caught["capped"])
        parts.append(f"{n} not started, a cap would be passed (each card names it)")
    if caught.get("off"):
        n = len(caught["off"])
        parts.append(f"{n} not started, hosted AI is off (each card says so)")
    left = len(caught.get("skipped") or []) + len(caught.get("failed") or [])
    if left:
        parts.append(f"{left} not started (each card says why)")
    return base + ("; " + "; ".join(parts) if parts else "")


def _line_drawn(line: dict) -> dict:
    """The line as a screen draws it: its words, the digest its press sends back, how many."""
    return {"words": line.get("words") or "", "digest": line.get("digest") or "",
            "n": int(line.get("n") or 0), "error": line.get("error") or ""}


def _limits_drawn(lim: dict) -> dict:
    """The limits card's figures as it draws them (CLAUDE.md, "Every carried field is drawn"):
    each limit with where it comes from, the installation's defaults beside them, the estimate
    (calls a day, cost per call, a day and a month, its basis and digest, the caps it suggests
    when none is set) and the acknowledgement."""
    est = lim["estimate"] or {}
    cost = est.get("cost") or {}
    sug = est.get("suggested") or {}
    ack = lim["ack"] or {}
    inc = lim["incident"]
    return {"incident_source": inc.get("source") or "",
            "incident_error": inc.get("error") or "",
            "day_usd": lim["day"], "month_usd": lim["month"],
            "day_value": lim["day"] if lim["day"] else sug.get("day_cap_usd"),
            "month_value": lim["month"] if lim["month"] else sug.get("month_cap_usd"),
            "incident_value": inc["usd"] if inc["usd"] else lim["installation"]["incident"],
            "inst_incident_usd": lim["installation"]["incident"],
            "inst_day_cap": lim["installation"]["day_cap"],
            "calls_per_day": est.get("calls_per_day"), "usd_per_call": cost.get("usd_per_call"),
            "cost_measured": bool(cost.get("measured")), "cost_basis": cost.get("basis") or "",
            "freq_basis": (est.get("frequency") or {}).get("basis") or "",
            "usd_per_day": est.get("usd_per_day"), "usd_per_month": est.get("usd_per_month"),
            "est_label": est.get("label") or "", "est_digest": est.get("digest") or "",
            "ack_by": ack.get("by") or "", "ack_at": ack.get("at") or "",
            "ack_digest": ack.get("estimate_digest") or "",
            "ack_usd_per_call": ack.get("usd_per_call"), "ready": lim["ready"]}


def view(network: str, now=None) -> dict:
    """The Settings card's model for *network* (board G2b): ``{"network", "card_id", "level",
    "level_words", "says", "source", "error", "on_by", "on_at", "ends", "levels", "limits",
    "limits_error", "line", "audit_href"}``. *line* is drawn only while Automatic is off. A
    read; a part that cannot be read is said in its place, never drawn as set."""
    from modules.ai import background

    name = _name(network)
    lvl = level(name)
    try:
        lim, lim_error = _limits_drawn(limits(name, now=now)), ""
    except Exception as exc:                          # noqa: BLE001 (said in place)
        lim, lim_error = None, f"{type(exc).__name__}: {exc}"
    line = None
    if lvl["level"] != "automatic":
        try:
            line = _line_drawn(catch_up_line(name, now=now))
        except Exception as exc:                      # noqa: BLE001 (said in place)
            line = _line_drawn({"error": f"{type(exc).__name__}: {exc}"})
    sw = lvl["switch"]
    ends = background.approval_ends(sw["entry"]) if sw.get("entry") else None
    return {"network": name, "card_id": CARD_ID, "level": lvl["level"],
            "level_words": lvl["words"], "says": lvl["says"], "source": lvl["source"],
            "error": lvl["error"], "on_by": sw.get("by") or "", "on_at": sw.get("at") or "",
            "ends": _iso(ends) if ends else "",
            "levels": [{"key": k, "words": LEVEL_WORDS[k], "says": LEVEL_SAYS[k]}
                       for k in LEVELS],
            "limits": lim, "limits_error": lim_error, "line": line,
            "audit_href": audit_href(name)}


def strip(network: str) -> dict:
    """The control strip's AI switch for *network* (the operator's item 1: "AI troubleshooting:
    Automatic" on or off): ``{"on", "known", "level", "words", "at", "ready", "line",
    "error"}``. *line* is the one line before turning it on; *ready* why it would be refused
    (its press is refused then, its refusal linking the limits card, `limits_href`). A read."""
    lvl = level(network)
    out = {"on": lvl["level"] == "automatic", "known": lvl["level"] != "unknown",
           "level": lvl["level"], "words": lvl["words"], "at": lvl["switch"].get("at") or "",
           "error": lvl["error"], "ready": "", "line": None}
    if out["on"] or not out["known"]:
        return out
    try:
        out["ready"] = readiness(network)
    except Exception as exc:                          # noqa: BLE001 (said, never drawn as ready)
        out["ready"] = f"its limits cannot be read ({type(exc).__name__}: {exc})"
    try:
        out["line"] = _line_drawn(catch_up_line(network))
    except Exception as exc:                          # noqa: BLE001 (said in place)
        out["error"] = f"the open incidents it would start on cannot be read ({exc})"
    return out
