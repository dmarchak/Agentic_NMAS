"""Settings › Installation › Diagnostics (board F4, signed off 2026-10-10): is Mercury itself
healthy, and what is it doing. Four cards, each a read except the drift card's controls:

- **Redaction** (C624): `redact.health()`, the canary run through every log handler's filters
  (built and filtered, never emitted, so the read writes nothing); unhealthy, it is also a Needs
  attention row (`attention.redaction_source`).
- **Drift checks**: one schedule for every network (`drift_check_interval`), and each
  network's on or off, last and next run, with Check now. The same functions today's drift
  routes call (one home per action): `agent_timers.save` and `rearm`, `set_disabled`,
  `trigger`. Each change is recorded in the installation's settings record.
- **In flight**: every network's held devices and running operations, and what finished in
  the last half hour (`modules/in_flight`).
- **The app's log**: its last lines, filtered, read on request (`modules/app_log`).
"""

import time

#: The drift schedule's choices (today's page offers the same seven), seconds.
DRIFT_CHOICES = ((1800, "30 minutes"), (3600, "1 hour"), (7200, "2 hours"),
                 (14400, "4 hours"), (28800, "8 hours"), (43200, "12 hours"),
                 (86400, "24 hours"))
#: The drift schedule's Save, and a network's Turn off / Turn on: named on the manual's page.
DRIFT_STEPS = ("check", "write", "record")


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch))) if epoch else ""


def redaction() -> dict:
    """The redaction health, as `redact.health()` measures it now, with when it was read."""
    from modules import redact

    got = redact.health()
    return dict(got, at_iso=_iso(time.time()))


def drift() -> dict:
    """``{"interval_s", "choices", "rows": [...]}``: every network's drift state. A row:
    ``name, state (disabled|idle|running|unreadable), disabled_by, disabled_at, last_iso,
    last_words, next_iso``; an unreadable network says so in its row, never dropped."""
    from modules.drift_check import _get_interval, get_checker

    checker = get_checker()
    rows = []
    for name in checker.networks():
        try:
            s = checker.status(name)
        except Exception as exc:                      # noqa: BLE001
            rows.append({"name": name, "state": "unreadable",
                         "why": f"{type(exc).__name__}: {exc}"})
            continue
        last = s.get("last_run") or {}
        rows.append({"name": name, "state": s.get("state", "unreadable"),
                     "why": str(s.get("unreadable") or ""),
                     "disabled_by": s.get("disabled_by") or "",
                     "disabled_at": s.get("disabled_at") or "",
                     "last_iso": _iso(s.get("last_ts")),
                     "last_words": last.get("summary") or "",
                     "last_ok": last.get("ok", True),
                     "next_iso": _iso(s.get("next_ts"))})
    interval = int(_get_interval())
    choices = list(DRIFT_CHOICES)
    if interval not in dict(choices):
        choices.append((interval, f"{interval} seconds (set elsewhere)"))
    return {"interval_s": interval, "choices": choices, "rows": rows}


def save_drift_interval(raw, actor: str, verified: str) -> dict:
    """The drift schedule's Save (DRIFT_STEPS): one of DRIFT_CHOICES, written to the agent's
    timers and re-armed (as today's /drift/settings does), recorded."""
    from modules import installation_settings as I
    from modules.agent_timers import save as save_timers
    from modules.drift_check import _get_interval, get_checker

    try:
        interval = int(raw)
    except (TypeError, ValueError):
        interval = 0
    if interval not in dict(DRIFT_CHOICES):                                       # check
        raise I.Refused(f"{raw!r} is not one of the drift schedule's choices: "
                        + ", ".join(words for _s, words in DRIFT_CHOICES))
    if int(_get_interval()) == interval:
        return {"ok": True, "nothing": True, "recorded": True}
    save_timers({"drift_check_interval": interval})                               # write
    get_checker().rearm()
    entry = I._record({"kind": "drift_interval", "card": "drift", "actor": actor,  # record
                       "actor_verified": verified, "fields": ["drift_check_interval"]})
    return dict(entry, ok=True, nothing=False)


def set_drift_off(network: str, off: bool, actor: str, verified: str) -> dict:
    """A network's drift checks turned off or on (DRIFT_STEPS), with who and when (the drift
    state records them), and in the installation's settings record."""
    from modules import installation_settings as I
    from modules.drift_check import _is_disabled, get_checker

    checker = get_checker()
    if network not in checker.networks():                                         # check
        raise I.Refused(f"{network!r} is not a network: "
                        + ", ".join(checker.networks()))
    if _is_disabled(network) == off:
        return {"ok": True, "nothing": True, "recorded": True, "network": network}
    checker.set_disabled(off, actor=actor, list_name=network)                     # write
    entry = I._record({"kind": "drift_off" if off else "drift_on", "card": "drift",  # record
                       "network": network, "actor": actor, "actor_verified": verified,
                       "fields": ["disabled"]})
    return dict(entry, ok=True, nothing=False, network=network)


def check_now(network: str) -> dict:
    """A network's drift check started now, in the background (today's /drift/check): the
    schedule does it anyway, only later. Refused while one runs. The card redraws when the
    check records its result (the drift checker announces `drift`)."""
    from modules import installation_settings as I
    from modules.drift_check import get_checker

    checker = get_checker()
    if network not in checker.networks():
        raise I.Refused(f"{network!r} is not a network: " + ", ".join(checker.networks()))
    if checker.is_running(network):
        raise I.Refused(f"a drift check of {network} is already running")
    checker.trigger(network)
    return {"ok": True, "network": network, "at_iso": _iso(time.time())}


def in_flight() -> dict:
    """Every network's running operations and recent receipts (modules/in_flight)."""
    from modules import in_flight as F
    from modules.drift_check import get_checker

    return dict(F.read_all(get_checker().networks()), not_recorded=F.NOT_RECORDED,
                at_iso=_iso(time.time()))


def app_log(lines, contains: str = "") -> dict:
    """The app's log's last lines, filtered (modules/app_log), with the choices offered."""
    from modules import app_log as L

    n = L.lines_asked(lines)
    return dict(L.tail(n, contains), lines_asked=n, contains=contains or "",
                choices=L.CHOICES, at_iso=_iso(time.time()))
