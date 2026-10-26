"""A capture that recorded a change made outside Mercury, said wherever the golden is read
(C1819, the operator's Walk 3, 2026-10-26).

A golden is a record of what the device ran when it was captured. The drift check compares the
device with it, so a change made by hand and then captured reads as no change since that
capture: a switch carried a console `description` the operator typed, Capture made it the golden, and
the device page drew "Drift: clean at the last run" directly above "Intent: departs (+1 -1)".
The operator's rule: an out-of-band change never reads as clean.

What makes a capture one that took in an out-of-band change, measured, never guessed:

- it was a capture (`CAPTURE_SOURCES`: Capture, Save, Save All, a manual save), the paths that
  record what the device runs without Mercury having sent it; a deploy, restore, rotation,
  onboarding or adopt records Mercury's own change;
- its commit's `Intent-Match:` trailer (computed at commit time, C89) names the device as not
  matching its intent; and
- a line of the departure is one no P2 rule explains (`differs`: a VTP switch's VLAN database,
  order only, a line not modelled and the device's own certificate are not out-of-band
  changes), judged by the Intent check's comparison now.

How the device was changed is the device's own word: its `%SYS-5-CONFIG_I` lines in its log
since its previous golden (`device_logs.change_lines`, each at the time Mercury received it),
read once per departing device by the capture's apply, never by a page, and kept in the
commit as an ``Out-Of-Band: <device>: <words>`` trailer. A log that could not be read says so;
it is never "no change".
"""

import logging
import re
import time

log = logging.getLogger(__name__)

#: The golden commits' `Source:` slugs that record what the device runs without Mercury having
#: sent it (`routes.golden.apply_captures`, `save_op`, `config_git`).
CAPTURE_SOURCES = ("capture", "save", "save_all", "manual")

TRAILER = "Out-Of-Band"

#: The device's own word for a change made at its CLI (Cisco IOS's mnemonic).
CONFIG_I = "%SYS-5-CONFIG_I"
_FROM = re.compile(r"Configured from (\S+)", re.I)


def unexplained(result: dict) -> bool:
    """Does an `intent_match` result depart with a line no P2 rule explains?"""
    from modules.nsot import differs

    if (result or {}).get("state") != "differs":
        return False
    return any(c.get("class") == differs.UNEXPLAINED for c in result.get("classes") or [])


def departures(value: str) -> dict:
    """``{device: words}`` for each device an ``Intent-Match:`` trailer's value names as not
    matching its intent (``no: edge1 (+1 -1); edge2 (unknown (why))``), the words as written. A
    device it could not compare (``unknown (...)``) is not a departure and is left out."""
    value = (value or "").strip()
    if not value.startswith("no:"):
        return {}
    text, out, pos = value[3:].strip(), {}, 0
    while pos < len(text):
        opened = text.find(" (", pos)
        if opened < 0:
            break
        host, depth, i = text[pos:opened].strip(), 0, opened + 1
        while i < len(text):
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            if depth == 0:
                break
            i += 1
        words = text[opened + 2:i]
        if host and not words.startswith("unknown"):
            out[host] = words
        pos = i + 1
        while pos < len(text) and text[pos] in "; ":
            pos += 1
    return out


def named(values) -> dict:
    """``{device: words}`` from ``Out-Of-Band:`` trailer values (``<device>: <words>``)."""
    out = {}
    for v in values or []:
        host, sep, words = (v or "").partition(": ")
        if sep and host.strip():
            out[host.strip()] = words.strip()
    return out


def short(words: str) -> str:
    """The trailer's words up to the receive time: how, and per which line."""
    return (words or "").split(", received ")[0]


def evidence(dev: dict, since: float = None, *, now: float = None) -> str:
    """How the device's own log says it was changed since *since* (its previous golden's
    time): its newest `%SYS-5-CONFIG_I` line, ``by console per SYS-5-CONFIG_I, received
    <time>: <the line>``, or that there is none, or why the log could not be read. One Loki
    ask (`device_logs.change_lines`); never raises."""
    from modules import device_logs

    try:
        got = device_logs.change_lines(dev, since=since, now=now)
    except Exception as exc:                   # noqa: BLE001
        return f"its log could not be read ({type(exc).__name__})"
    if not got.get("configured", True):
        return "its log was not read: Loki is not configured"
    if got.get("error"):
        return f"its log could not be read: {got['error']}"
    mine = [l for l in got.get("lines") or [] if l.get("mnemonic") == CONFIG_I]
    window = ("since its previous golden" if since and not got.get("capped")
              else f"in the last {got.get('max_days')} days")
    if not mine:
        return f"no {CONFIG_I[1:]} line in its log {window}"
    newest = mine[0]
    m = _FROM.search(newest.get("text") or "")
    how = f"by {m.group(1)} " if m else ""
    more = f" (the newest of {len(mine)} {window})" if len(mine) > 1 else ""
    return (f"{how}per {CONFIG_I[1:]}{more}, received {newest.get('at_iso')}: "
            f"{' '.join((newest.get('text') or '').split())}")


def trailers(repo: str, departing: list, *, now: float = None) -> list:
    """``Out-Of-Band: <device>: <words>`` for each device in *departing* (inventory rows), its
    log read since its previous golden's commit, every device's ask at once
    (`fanout.read_each`). Masked: `change_lines` masks each line."""
    from modules import fanout
    from modules.nsot import repo as R

    if not departing:
        return []
    now = time.time() if now is None else now

    def one(dev):
        host = dev.get("hostname", "")
        rc, out, _err = R.git(repo, "log", "-1", "--format=%ct", "--",
                              f"golden/{R._safe_name(host)}.cfg")      # noqa: SLF001
        since = float(out.strip()) if rc == 0 and out.strip().isdigit() else None
        return f"{TRAILER}: {host}: {evidence(dev, since, now=now)}"

    got = fanout.read_each(one, departing, name="out-of-band")
    out = []
    for dev, line in zip(departing, got):
        if isinstance(line, fanout.Failed):
            line = (f"{TRAILER}: {dev.get('hostname', '')}: its log could not be read "
                    f"({line})")
        out.append(" ".join(line.split()))
    return out
