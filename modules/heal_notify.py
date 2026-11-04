"""Who is told about a network's self-healing (board H, artboard A's Who is told card;
docs/HEAL_TO_INTENT.md section 10, "Which events notify").

Each network names one team from the teams store (`modules/notify/teams.py`) and the events
that notify it (`heal_notify_team`, `heal_notify_events`): each network's own and never
inherited (`settings_scope.OWN_ONLY`), so Default's team is never told about a network that
inherits. No team, the default: nothing is told. Every event on by default, so naming a team
tells it everything section 10 lists.

Written only here (`save`, `settings_scope.CARDLESS`): the team checked against the store, the
card's values compared with what it drew (R17: another person's change since is refused,
naming both), written and recorded in the network's settings record. Read by `teams_for`,
which the heal's notices ask (H6), and by the Self-healing tab and Settings › Installation ›
Notifications' teams (`told_about`).
"""

import logging
import os

log = logging.getLogger(__name__)

GROUP = "heal_notify"
TEAM_KEY = "heal_notify_team"
EVENTS_KEY = "heal_notify_events"
#: The card's choices, in its order: each one's key, its words and the events it covers
#: (`notify.message.EVENTS`' keys). "Halted or held" is one choice, as the board draws it.
CHOICES = (("cant_fix", "can't fix", ("cant_fix",)),
           ("proposal", "a fix waiting for a person", ("proposal",)),
           ("halted", "halted or held", ("halted", "held")),
           ("healed", "every automatic heal", ("healed",)),
           ("cleared", "cleared", ("cleared",)))
#: Save's steps, in order, named on the manual's Settings page.
SAVE_STEPS = ("check", "write", "record")
RECORD_KIND = "heal_notify"
LOCK_NAME = "heal_notify"


class Refused(ValueError):
    """A Who is told change refused, in words naming what was compared."""


def _lock(network: str):
    from modules.config import list_data_path
    from modules.filestore import PathLock

    return PathLock(lambda: os.path.join(list_data_path(network), LOCK_NAME))


def read(network: str) -> dict:
    """``{"state", "error", "team", "events", "choices"}``: the network's team id ("" for
    none), the events that notify it, and which of the card's choices are on. ``state``:
    ``ok`` or ``unreadable`` (never read as nobody told while it cannot be read)."""
    from modules import list_settings as L
    from modules.config import SettingsUnreadable

    try:
        store = None if L.is_default(network) else L.load(network)
        team = L.resolve(network, TEAM_KEY, store)[0] or ""
        events = list(L.resolve(network, EVENTS_KEY, store)[0] or [])
    except (L.ListSettingsUnreadable, SettingsUnreadable) as exc:
        return {"state": "unreadable", "error": f"{network}'s Who is told cannot be read ({exc})",
                "team": "", "events": [], "choices": []}
    return {"state": "ok", "error": "", "team": team, "events": events,
            "choices": [key for key, _w, covers in CHOICES if set(covers) <= set(events)]}


def drawn(got: dict) -> dict:
    """What the card drew, as its form sends it back (``loaded``)."""
    return {"team": got.get("team", ""), "choices": list(got.get("choices") or [])}


def _events(choices) -> list:
    unknown = sorted(set(choices) - {k for k, _w, _c in CHOICES})
    if unknown:
        raise Refused(f"{', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} not an "
                      f"event that notifies: the choices are "
                      f"{', '.join(k for k, _w, _c in CHOICES)}")
    return [e for key, _w, covers in CHOICES if key in choices for e in covers]


def save(network: str, team: str, choices, *, actor: str, actor_verified: str = "",
         loaded=None) -> dict:
    """Name *network*'s team and the events that tell it, as the card sent them (SAVE_STEPS).
    ``{"ok", "network", "team", "team_name", "events", "nothing", "recorded", "at"}``;
    `Refused` naming the team, the choice or the value that moved."""
    from modules import list_settings as L
    from modules.notify import teams

    if not actor:
        raise Refused("Who is told records who saved it, and no actor was given")
    if not isinstance(loaded, dict):
        raise Refused("the card did not say what it drew, so a change another person made "
                      "since cannot be told from yours: open the tab again")
    team = (team or "").strip()
    events = _events(choices or [])                                         # check
    got = teams.read()
    if team:
        if got["state"] == "unreadable":
            raise Refused(f"the teams store could not be read ({got['error']}), so the team "
                          f"{team} cannot be checked")
        if team not in got["teams"]:
            raise Refused(f"no team {team!r}: the teams are "
                          f"{', '.join(t['name'] for t in got['teams'].values()) or 'none'}")
    name = (got["teams"].get(team) or {}).get("name", "") if team else ""
    with _lock(network):
        now = read(network)
        if now["state"] != "ok":
            raise Refused(f"{now['error']}: nothing is saved until it can be read")
        if drawn(now) != {"team": loaded.get("team", ""),
                          "choices": list(loaded.get("choices") or [])}:
            raise Refused(f"another person changed Who is told since the card drew it (drawn "
                          f"team {loaded.get('team') or 'none'} with "
                          f"{', '.join(loaded.get('choices') or []) or 'no event'}; now team "
                          f"{now['team'] or 'none'} with "
                          f"{', '.join(now['choices']) or 'no event'}): open the tab again")
        if now["team"] == team and now["events"] == events:
            return {"ok": True, "network": network, "team": team, "team_name": name,
                    "events": events, "nothing": True, "recorded": False, "at": ""}
        out = L.write(network, {TEAM_KEY: team, EVENTS_KEY: events}, actor=actor)  # write
        if not out.get("ok"):
            raise Refused(f"not saved: {out.get('error') or 'Who is told was not written'}")
    entry = L._record(network, {"kind": RECORD_KIND, "group": GROUP,          # record
                                "written": [TEAM_KEY, EVENTS_KEY],
                                "before": {"team": now["team"], "events": now["events"]},
                                "after": {"team": team, "events": events},
                                "actor": actor, "actor_verified": actor_verified})
    log.info("heal: %s set who is told for %s: team %s, %d events", actor, network,
             team or "none", len(events))
    return {"ok": True, "network": network, "team": team, "team_name": name, "events": events,
            "nothing": False, "recorded": bool(entry.get("recorded")),
            "at": entry.get("at", "")}


def teams_for(network: str, event: str) -> list:
    """The team ids told about *event* on *network*: its team when one is named and the event
    is on, else none. A Who is told that cannot be read tells nobody and says so in the log
    (the notice's own row is the heal's)."""
    got = read(network)
    if got["state"] != "ok":
        log.error("heal: %s; nobody is told about %s", got["error"], event)
        return []
    return [got["team"]] if got["team"] and event in got["events"] else []


def told_about(team_id: str, networks=None) -> list:
    """The networks that name *team_id* as Who is told, in the networks' order."""
    from modules.integration_groups import network_names

    out = []
    for name in network_names() if networks is None else networks:
        got = read(name)
        if got["state"] == "ok" and got["team"] == team_id:
            out.append(name)
    return out
