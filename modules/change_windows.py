"""NO-CHANGE WINDOWS: the daily spans, in UTC, in which this installation starts no scheduled
change (C1317; the operator, 2026-10-18).

One setting, ``no_change_windows``, the installation's (Settings: Installation), a list of
``{"start": "HH:MM", "end": "HH:MM", "reason": "..."}``. None by default: an installation
with nothing set holds nothing. A window is ``[start, end)``; a start after its end wraps
past midnight; a start equal to its end holds nothing, and says so in its words.

What an installation puts here is its own (a nightly backup, a maintenance freeze): nothing
in the product names one. Today the scheduled credential rotation reads it
(`modules/nsot/scheduled_rotation.py`): no run starts inside a window, and a run reaching one
stops there. The bulk actions' design (docs/BULK_ACTIONS.md, question 5) reads the same.
"""

import logging
import re
import time

log = logging.getLogger(__name__)

SETTING = "no_change_windows"
#: ``HH:MM``, 00:00 to 23:59, as the schema holds it.
HHMM = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
_HHMM = re.compile(HHMM)


def _minute(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def windows() -> list:
    """The windows as set, each well-formed one; [] when none (the default). A malformed
    entry is left out and logged (the schema refuses one on write; this is a file edited by
    hand)."""
    from modules.settings_schema import get_setting
    got = get_setting("no_change_windows", []) or []     # SETTING, the installation's
    out = []
    for w in got if isinstance(got, list) else []:
        if (isinstance(w, dict) and _HHMM.match(str(w.get("start", "")))
                and _HHMM.match(str(w.get("end", "")))):
            out.append({"start": w["start"], "end": w["end"],
                        "reason": str(w.get("reason") or "")})
        else:
            log.warning("no_change_windows: %r is not {start, end} as HH:MM; it holds nothing",
                        w)
    return out


def covers(window: dict, now=None) -> bool:
    """Is *now* (epoch seconds; the clock when None) inside *window*, in UTC?"""
    t = time.gmtime(time.time() if now is None else float(now))
    minute = t.tm_hour * 60 + t.tm_min
    start, end = _minute(window["start"]), _minute(window["end"])
    if start < end:
        return start <= minute < end
    if start > end:                          # wraps past midnight
        return minute >= start or minute < end
    return False


def holding(now=None, given=None):
    """The first window covering *now*, or None. *given* is the windows to judge (the
    setting's when None)."""
    for w in windows() if given is None else given:
        if covers(w, now):
            return w
    return None


def words(window: dict) -> str:
    """A window as the screens and records say it: "the no-change window 22:00 to 23:00 UTC
    (a maintenance freeze)"."""
    if window["start"] == window["end"]:
        span = f"{window['start']} to {window['end']} UTC, which holds nothing"
    else:
        span = f"{window['start']} to {window['end']} UTC"
    reason = f" ({window['reason']})" if window.get("reason") else ""
    return f"the no-change window {span}{reason}"
