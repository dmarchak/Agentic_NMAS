"""The notice "self-healing is blind or paused" (C3330; the operator, 2026-11-12: "Add a
notification event kind "self-healing is blind or paused", on by default for everyone, so it
still reaches a person at warning").

Its row is a warning (a network outage is critical; a Mercury reader failing is not), so this
notice is what makes sure a person hears it. The event `heal_blind` (`notify.message.EVENTS`)
is sent, on by default (`ON_BY_DEFAULT`), to every team in the teams store, every verified and
enabled destination of each (`notify.delivery.deliver_event`):

- **blind**: when self-healing's detection read raises its row (`detect_read.liveness`'s
  ``blind``: its last good read older than its bound, past Loki's start grace), once per raise,
  never per read: the raise is keyed by its store and the time its last good read began, kept
  in `<data>/heal/blind_notices.json` while it stands, and a raise after a clear is a new one.
  It is sent from the detection reader's after-store step (`notify_detection`), never from a
  read of the rows (a read writes nothing);
- **paused**: when a person turns self-healing off for a network (`policy.turn_off`) or stops
  it everywhere (`policy.stop`), once, at the press.

A notice that cannot be sent is the delivery log's row, as every delivery's; it never fails
the read or the press it rides on.
"""

import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

EVENT = "heal_blind"
#: On for every team unless a person turns it off; no control turns it off yet (C3336).
ON_BY_DEFAULT = True
DIR = "heal"
FILE = "blind_notices.json"
LINK = "/v2/attention"


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _path() -> str:
    from modules import config

    return os.path.join(config.DATA_DIR, DIR, FILE)


def every_team() -> list:
    """Every team's id in the teams store, in its order; none when it cannot be read (said)."""
    from modules.notify import teams

    got = teams.read()
    if got.get("state") == "unreadable":
        log.error("heal: the teams store cannot be read (%s): nobody is told self-healing is "
                  "blind or paused", got.get("error"))
        return []
    return list((got.get("teams") or {}).keys())


def send(incident: str, network: str, happened: str, outcome: str, todo: str, *,
         deliver=None, teams=None) -> dict:
    """One `heal_blind` event to every team. ``{"sent", "failed", "teams", "error"}``."""
    if not ON_BY_DEFAULT:
        return {"sent": 0, "failed": 0, "teams": 0, "error": "off"}
    if deliver is None:
        from modules.notify import delivery
        deliver = delivery.deliver_event
    team_ids = every_team() if teams is None else list(teams)
    event = {"incident": re.sub(r"[^A-Za-z0-9._-]", "-", incident)[:80], "event": EVENT,
             "network": network, "happened": happened, "outcome": outcome, "todo": todo,
             "link": LINK}
    try:
        got = deliver(event, team_ids)
    except ValueError as exc:
        got = {"sent": 0, "failed": 0, "error": f"not sent: {exc}"}
    return {"sent": got.get("sent", 0), "failed": got.get("failed", 0),
            "teams": len(team_ids), "error": got.get("error", "")}


def _read() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.error("heal: the blind notices' record cannot be read (%s): read as none", exc)
        return {}


def notify_detection(now: float = None, *, rows=None, deliver=None, teams=None) -> list:
    """Send the notice for each detection store whose row is ``blind`` and was not told for
    this raise; forget the raises that cleared. Returns the keys sent. *rows* stands in for
    every detection store's liveness rows (`detect_read.liveness`). Never raises."""
    from modules import filestore

    now = time.time() if now is None else now
    try:
        if rows is None:
            rows = _detection_rows(now)
        blind = {f"{r['unit']}:{int(r.get('since') or 0)}": r for r in rows
                 if r.get("state") == "blind"}
        path = _path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sent = []
        with filestore.PathLock(path):
            doc = _read()
            told = {k: v for k, v in (doc.get("told") or {}).items() if k in blind}
            for key, r in blind.items():
                if key in told:
                    continue
                got = send(key, r.get("list") or "", r.get("headline") or "",
                           r.get("detail") or "", (r.get("action") or {}).get("label") or "",
                           deliver=deliver, teams=teams)
                told[key] = dict(got, at=_iso(now))
                sent.append(key)
            if told != (doc.get("told") or {}):
                filestore.write_atomic(path, json.dumps({"told": told}, indent=1,
                                                        sort_keys=True))
        return sent
    except Exception as exc:                            # noqa: BLE001 (never fails the read)
        log.error("heal: the blind notice could not be judged or sent: %s: %s",
                  type(exc).__name__, exc)
        return []


def _detection_rows(now: float) -> list:
    from modules import reader_job
    from modules.heal import detect_read as D

    out = []
    for v in reader_job.configuration_readers(D.READER):
        out += D.liveness(v, reader_job.read_cached(v.name), now)
    return out


def notify_paused(network: str, actor: str, words: str, *, deliver=None, teams=None) -> dict:
    """The notice when a person turns self-healing off for *network*, or stops it everywhere
    (*network* ""), sent once at the press. Never raises."""
    from modules import display_names

    try:
        who = display_names.people(actor) or "a person not recorded"
        where = network or "every network"
        return send(f"paused-{network or 'everywhere'}-{int(time.time())}", network,
                    f"Self-healing was turned off on {where} by {who}",
                    words, "Turn it back on in Settings › Self-healing when it should heal "
                           "again; until then nothing is healed there",
                    deliver=deliver, teams=teams)
    except Exception as exc:                            # noqa: BLE001 (never fails the press)
        log.error("heal: the paused notice could not be sent: %s: %s", type(exc).__name__, exc)
        return {"sent": 0, "failed": 0, "teams": 0, "error": str(exc)}
