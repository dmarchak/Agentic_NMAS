"""Background AI features: off by default per network, turned on by an admin who saw the
estimate, each within its own caps (PHASE8_PLAN 18.3 rules 1 to 5; CLAUDE.md, "AI cost safety";
C1843).

**A background feature** is an AI call no person pressed: a job's, on a finding deterministic
code made (rule 5). `FEATURES` names each one: the task it calls (a `profiles.TASKS` pin), the
finding kinds that may trigger it, its trigger in words, how many calls one finding makes at
most, and where its trigger's frequency is measured. **None exists yet**: the SDN loop
(PHASE8_PLAN 17.1 S10) is the first, and it adds its entry here; until then the gateway refuses
every background call by name (`triggers.check`).

**The switches** are one installation setting, ``ai_background``, keyed by network (a list's
folder name) INSIDE, so a network never inherits another's switch: ``{network: {feature:
{"on": true, "by", "verified", "at", "estimate", "day_cap_usd", "month_cap_usd", "caps_by",
"caps_at"}}}``. A network or feature absent is off. Every change is recorded in the
installation's settings record (`installation_settings._record`: ``ai_background_on``,
``ai_background_off``, ``ai_background_caps``) with who, when, and for turning on the estimate
shown.

**The gateway asks two questions**, each read from the file at the call, so turning a feature
off stops its next call in every worker at once (a call already past the question finishes and
is recorded, as any call does):

- `admit`: is the trigger's feature on for its network?
- `over_cap`: do the feature's spend today and this month on that network, plus this call's
  worst case, fit its day and month caps? (The installation's day cap is the gateway's own
  question, asked before this one.)

**Turning on** (`turn_on`) is an admin's decision bound to the estimate they saw: `estimate`
returns it with its digest, and `turn_on` recomputes it and refuses, naming both digests, when
it moved. The estimate (rule 2) is calls a day (the feature's trigger frequency, measured by
the feature, times its calls per finding) and dollars a day and a month (calls a day times the
measured cost per call: the mean cost of the task's sent calls on its pinned model in the last
30 cap days; with none measured, the task's per-call cap, its worst case, said as such). An
unmeasured frequency is said as unknown, never guessed.

**Mercury never raises a cap**: only `turn_on` and `set_caps` write one, each a person's
action. The routes that call these are the Settings › AI screen's (not built: PHASE8_PLAN
18.6), each gated as ``configure``.
"""
import hashlib
import json
import logging
import math
import time

log = logging.getLogger(__name__)

#: The setting holding every network's switches.
SETTING = "ai_background"
#: The measured cost per call is the mean over this many cap days of sent calls.
COST_WINDOW_DAYS = 30
#: A month in the estimate's words: 30 days.
MONTH_DAYS = 30

#: Each background feature (none yet; the SDN loop, PHASE8_PLAN 17.1 S10, is the first):
#: ``{name: {"task", "words", "trigger_words", "findings", "calls_per_finding",
#: "frequency"}}``. *findings* are the finding kinds a trigger may name; *frequency* is
#: ``"module:function"`` (or a callable), answering ``{"per_day": float | None, "basis": str}``
#: for a network: how often its trigger fired, measured from the feature's own record.
FEATURES: dict = {}


class Refused(ValueError):
    """Nothing was changed; the message names what was compared and both values."""


def _now() -> float:
    return time.time()


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def switches() -> dict:
    """``{network: {feature: entry}}`` as stored; a value out of shape reads as none."""
    from modules.settings_schema import get_setting

    # The key spelled out (SETTING's value), so the network-settings scan reads it as a
    # literal: a host-wide setting whose map is keyed by network inside.
    raw = get_setting("ai_background", {}) or {}
    if not isinstance(raw, dict):
        return {}
    return {n: {f: e for f, e in fs.items() if isinstance(e, dict)}
            for n, fs in raw.items() if isinstance(fs, dict)}


def entry_of(network: str, feature: str):
    """The switch's entry for *feature* on *network* when it is ON, else None."""
    got = switches().get(network, {}).get(feature)
    return got if isinstance(got, dict) and got.get("on") is True else None


def enabled() -> list:
    """``[(network, feature, entry)]`` for every switch on, sorted."""
    return sorted(((n, f, e) for n, fs in switches().items() for f, e in fs.items()
                   if e.get("on") is True), key=lambda t: (t[0], t[1]))


def caps_of(entry: dict) -> dict:
    """``{"day": usd, "month": usd}`` of an entry: each a positive number, or None for one out
    of shape (which `over_cap` refuses on, never reads as no cap)."""
    def num(v):
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        return float(v) if ok and v > 0 else None
    return {"day": num(entry.get("day_cap_usd")), "month": num(entry.get("month_cap_usd"))}


def admit(trigger: dict) -> str:
    """``""`` when the background *trigger*'s feature is on for its network, else why not (the
    gateway's ``feature_off``). A switch that cannot be read is said, and refused."""
    try:
        entry = entry_of(trigger["network"], trigger["feature"])
    except Exception as exc:                                    # noqa: BLE001 (said, refused)
        return (f"the background switches cannot be read ({type(exc).__name__}: {exc}), so "
                f"whether {trigger.get('feature')} is on is unknown; nothing was sent")
    if entry is None:
        return (f"the background feature {trigger['feature']} is off for the network "
                f"{trigger['network']}: an admin turns it on in Settings › AI, after its "
                "estimate; nothing was sent")
    return ""


def over_cap(trigger: dict, worst: float, day: str):
    """None when the feature's spend on its network on the cap's *day* and in its month, plus
    this call's *worst* case, fits its day and month caps; else the gateway's refusal,
    ``{"kind", "why", "cap"}``: ``feature_cap`` naming both operands and which cap ("day" or
    "month"), or ``feature_off`` when it was turned off since `admit`. An unreadable record, or
    a cap out of shape, refuses."""
    from modules.ai import spend

    name, net = trigger["feature"], trigger["network"]
    entry = entry_of(net, name)
    if entry is None:
        return {"kind": "feature_off", "cap": "",
                "why": admit(trigger) or f"{name} was turned off for {net}; nothing was sent"}
    caps = caps_of(entry)
    for which in ("day", "month"):
        if caps[which] is None:
            return {"kind": "feature_cap", "cap": which,
                    "why": (f"{name} on {net} has no valid {which} cap stored "
                            f"({entry.get(which + '_cap_usd')!r}); nothing was sent")}
    got = spend.feature_spent(net, name, day)
    if got["state"] == "unreadable":
        return {"kind": "feature_cap", "cap": "day",
                "why": (f"the record of AI calls cannot be read, so {name}'s spend on {net} is "
                        f"unknown ({got['error']}); nothing was sent")}
    for which, spent in (("day", got["day_usd"]), ("month", got["month_usd"])):
        if spent + worst > caps[which]:
            period = "today" if which == "day" else "this month"
            return {"kind": "feature_cap", "cap": which,
                    "why": (f"{name}'s spend on {net} {period} ${spent:.4f} plus this call's "
                            f"worst case ${worst:.4f} is over its {which} cap "
                            f"${caps[which]:.4f}; it stops until the {which} ends or an admin "
                            "raises the cap; nothing was sent")}
    return None


# ── The estimate (rule 2) ─────────────────────────────────────────────────────────────────────

def _frequency(spec: dict, network: str) -> dict:
    fn = spec.get("frequency")
    try:
        if isinstance(fn, str):
            import importlib
            mod, _, attr = fn.partition(":")
            fn = getattr(importlib.import_module(mod), attr)
        got = fn(network) if callable(fn) else None
    except Exception as exc:                                    # noqa: BLE001 (said)
        return {"per_day": None, "basis": f"its frequency could not be measured "
                f"({type(exc).__name__}: {exc})"}
    if not isinstance(got, dict):
        return {"per_day": None, "basis": "the feature measures no frequency"}
    per = got.get("per_day")
    ok = isinstance(per, (int, float)) and not isinstance(per, bool) and math.isfinite(per) \
        and per >= 0
    return {"per_day": float(per) if ok else None, "basis": str(got.get("basis") or "")}


def measured_cost(task: str, now=None) -> dict:
    """``{"usd_per_call", "calls", "measured", "basis"}``: the mean cost of *task*'s sent calls
    (a row with tokens: the provider answered and billed) on its pinned model over the last
    `COST_WINDOW_DAYS` cap days, from that window of the record alone; with none, the task's
    per-call cap (its worst case at its bounds), ``measured`` False and said."""
    from modules.ai import calls, profiles, spend

    pin = profiles.task(task)
    today = calls.today(now)
    got = calls.rows_since(calls.day_start(spend.day_minus(today, COST_WINDOW_DAYS)))
    sent = [r for r in got.get("rows") or [] if r.get("feature") == task
            and r.get("model") == pin["model"] and r.get("tokens")]
    if sent:
        usd = sum(float(r.get("cost_usd") or 0) for r in sent) / len(sent)
        return {"usd_per_call": usd, "calls": len(sent), "measured": True,
                "basis": (f"the mean of {len(sent)} sent {task} call(s) on {pin['model']} in "
                          f"the last {COST_WINDOW_DAYS} days")}
    worst = profiles.cap_per_call(task)
    unread = (f" (the record could not be read: {got['error']})"
              if got.get("state") == "unreadable" else "")
    return {"usd_per_call": worst, "calls": 0, "measured": False,
            "basis": (f"no {task} call on {pin['model']} was measured in the last "
                      f"{COST_WINDOW_DAYS} days{unread}: its per-call cap, the most one call "
                      "can cost, is used, so this is an upper bound")}


def _digest(est: dict) -> str:
    body = {k: v for k, v in est.items() if k not in ("digest", "as_of")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def estimate(network: str, feature: str, now=None) -> dict:
    """What turning *feature* on for *network* is expected to cost, labelled an estimate:
    ``{"label", "feature", "network", "task", "model", "frequency", "calls_per_finding",
    "calls_per_day", "cost", "usd_per_day", "usd_per_month", "suggested", "as_of",
    "digest"}``. Unknown (None) where the frequency is unmeasured. *suggested* is a day and a
    month cap of twice the estimate, within the installation's day cap, for the screen to offer
    (the person decides). Raises Refused for a feature Mercury does not know."""
    from modules.ai import gateway, profiles

    spec = _spec(feature)
    slug = _network(network)
    pin = profiles.task(spec["task"])
    freq = _frequency(spec, slug)
    per_finding = int(spec.get("calls_per_finding") or 1)
    cost = measured_cost(spec["task"], now)
    per_day = freq["per_day"] * per_finding if freq["per_day"] is not None else None
    usd_day = per_day * cost["usd_per_call"] if per_day is not None else None
    suggested = None
    if usd_day is not None:
        cap = gateway.day_cap()
        day = max(math.ceil(usd_day * 2 * 100) / 100, 0.01)
        day = min(day, cap) if cap is not None else day
        suggested = {"day_cap_usd": day, "month_cap_usd": round(day * MONTH_DAYS, 2)}
    est = {"label": "an estimate, not a measurement of this feature's spend",
           "feature": feature, "network": slug, "task": spec["task"], "model": pin["model"],
           "frequency": freq, "calls_per_finding": per_finding, "calls_per_day": per_day,
           "cost": cost, "usd_per_day": usd_day,
           "usd_per_month": usd_day * MONTH_DAYS if usd_day is not None else None,
           "month_days": MONTH_DAYS, "suggested": suggested,
           "as_of": _iso(_now())}
    est["digest"] = _digest(est)
    return est


# ── The admin's actions ───────────────────────────────────────────────────────────────────────

def _spec(feature: str) -> dict:
    spec = FEATURES.get(feature)
    if spec is None:
        raise Refused(f"{feature!r} is not a background feature Mercury knows; known: "
                      f"{', '.join(sorted(FEATURES)) or 'none'}")
    return spec


def _network(network: str) -> str:
    from modules.nsot import listref

    try:
        return listref.resolve(network).slug
    except Exception as exc:                                    # noqa: BLE001
        raise Refused(f"{network!r} is not a network Mercury holds ({exc})") from None


def _person(actor: str) -> None:
    from modules import identity

    if not isinstance(actor, str) or not actor.strip() or actor == identity.UNVERIFIED:
        raise Refused(f"a background feature is changed by a verified admin; {actor!r} is not "
                      "one; nothing was changed")


def _caps(day_cap_usd, month_cap_usd) -> dict:
    from modules.ai import gateway

    out = caps_of({"day_cap_usd": day_cap_usd, "month_cap_usd": month_cap_usd})
    for which, given in (("day", day_cap_usd), ("month", month_cap_usd)):
        if out[which] is None:
            raise Refused(f"the {which} cap {given!r} is not a positive amount in US dollars; "
                          "nothing was changed")
    overall = gateway.day_cap()
    if overall is not None and out["day"] > overall:
        raise Refused(f"the feature's day cap ${out['day']:.4f} is over the installation's day "
                      f"cap ${overall:.4f}: a feature's caps are within the overall cap; "
                      "nothing was changed")
    return out


def _write(network: str, feature: str, entry) -> None:
    """Replace one switch's entry (None removes it), under the settings lock: a
    read-modify-write of the one setting, so two admins never write over each other."""
    from modules.config import settings_lock
    from modules.settings_schema import write_settings

    with settings_lock():
        every = switches()
        mine = dict(every.get(network, {}))
        if entry is None:
            mine.pop(feature, None)
        else:
            mine[feature] = entry
        if mine:
            every[network] = mine
        else:
            every.pop(network, None)
        out = write_settings({SETTING: every}, actor="")
    if not out["ok"]:
        raise Refused(out["error"])


def _record(kind: str, network: str, feature: str, actor: str, verified: str, **extra) -> dict:
    from modules import installation_settings

    return installation_settings._record({"kind": kind, "card": "ai", "actor": actor,
                                          "actor_verified": verified, "fields": [SETTING],
                                          "network": network, "feature": feature, **extra})


def turn_on(network: str, feature: str, *, day_cap_usd, month_cap_usd, shown: str,
            actor: str, verified: str, now=None) -> dict:
    """Turn *feature* on for *network* (an admin's decision): the caps checked, the estimate
    recomputed and compared with the *shown* digest (refused, naming both, when it moved),
    then written with who, when and that estimate, and recorded. ``{"ok", "entry",
    "recorded", ...}``; raises Refused naming why, with nothing changed."""
    _person(actor)
    _spec(feature)
    slug = _network(network)
    caps = _caps(day_cap_usd, month_cap_usd)
    est = estimate(slug, feature, now)
    if est["digest"] != shown:
        raise Refused(f"the estimate moved since it was shown (shown {shown[:12] or 'none'}, "
                      f"now {est['digest'][:12]}): look at it again and accept it; nothing "
                      "was changed")
    at = _iso(_now())
    entry = {"on": True, "by": actor, "verified": verified, "at": at, "estimate": est,
             "day_cap_usd": caps["day"], "month_cap_usd": caps["month"],
             "caps_by": actor, "caps_at": at}
    _write(slug, feature, entry)
    rec = _record("ai_background_on", slug, feature, actor, verified, estimate=est,
                  day_cap_usd=caps["day"], month_cap_usd=caps["month"])
    log.info("ai background: %s turned %s on for %s", actor, feature, slug)
    return dict(rec, ok=True, entry=entry)


def turn_off(network: str, feature: str, *, actor: str, verified: str) -> dict:
    """Turn *feature* off for *network*: one call, no confirm (turning it off spends nothing);
    its next call is refused in every worker at once, and a call already past the gateway's
    switch finishes and is recorded. Off already: nothing written."""
    _person(actor)
    slug = _network(network)
    was = entry_of(slug, feature)
    if was is None:
        return {"ok": True, "nothing": True, "recorded": True}
    _write(slug, feature, None)
    rec = _record("ai_background_off", slug, feature, actor, verified, was_on_by=was.get("by"),
                  was_on_at=was.get("at"))
    log.info("ai background: %s turned %s off for %s", actor, feature, slug)
    return dict(rec, ok=True, nothing=False)


def set_caps(network: str, feature: str, *, day_cap_usd, month_cap_usd, actor: str,
             verified: str) -> dict:
    """Change an ON feature's caps (an admin's decision: raising one is how a stopped feature
    runs again before its period ends); the change recorded with both values. Refused for a
    feature that is off (turning it on asks for its caps)."""
    _person(actor)
    slug = _network(network)
    was = entry_of(slug, feature)
    if was is None:
        raise Refused(f"{feature} is off for {slug}: turning it on sets its caps; nothing was "
                      "changed")
    caps = _caps(day_cap_usd, month_cap_usd)
    at = _iso(_now())
    entry = dict(was, day_cap_usd=caps["day"], month_cap_usd=caps["month"], caps_by=actor,
                 caps_at=at)
    _write(slug, feature, entry)
    rec = _record("ai_background_caps", slug, feature, actor, verified,
                  before={"day_cap_usd": was.get("day_cap_usd"),
                          "month_cap_usd": was.get("month_cap_usd")},
                  day_cap_usd=caps["day"], month_cap_usd=caps["month"])
    return dict(rec, ok=True, entry=entry)
