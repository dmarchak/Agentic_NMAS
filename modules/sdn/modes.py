"""The SDN responses' modes, per network (PHASE8_PLAN 17.1 S9 and 17.4): Phase 9's autonomy in
miniature. Deterministic; no AI.

- **HITL, the default.** A detection's response is previewed and waits for a person's confirm
  by hash, as every operation does.
- **AUTO, off by default.** Turned on for one network by a verified person (no role is an
  admin's yet: C1655) with a recorded reason, an expiry and the risk class it allows (``low``:
  rate-limit and drop; ``medium``: also remove a flow). While it is on, the loop applies only
  catalogue actions within that class; anything else stays HITL. Each autonomous action is
  recorded as autonomous, naming the setting and its reason (`autonomous`). At the expiry the
  mode is HITL again, and the record says so once (``expired``). Turning it off is one action
  and takes effect at once.

**The store** (``sdn_mode.jsonl`` in the network's folder): append-only, one line per change
(``on``, ``off``, ``expired``), owner-only, under a cross-process lock; the mode now is the last
line's, judged against the clock. An unreadable store answers HITL and says so: it never reads
as AUTO.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

FILE_NAME = "sdn_mode.jsonl"
MODES = ("hitl", "auto")
RISKS = ("low", "medium")
#: The longest AUTO may be on before it must be turned on again (a day): an expiry is
#: required, and one past this is refused.
MAX_AUTO_SECONDS = 24 * 3600


class ModeRefused(ValueError):
    """A mode change refused, in words."""


def _path(network: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), FILE_NAME)


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _rows(network: str) -> dict:
    path = _path(network)
    if not os.path.exists(path):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"state": "ok", "error": "",
                    "rows": [json.loads(line) for line in fh if line.strip()]}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [], "error": f"{FILE_NAME}: {exc}"}


def current(network: str, now: float = None) -> dict:
    """The mode on *network* now: ``{"mode", "allowed_risk", "reason", "by", "since", "until",
    "words", "state", "error", "expired"}``. AUTO past its expiry is HITL, ``expired`` naming
    the setting that lapsed (recorded once by `record_expiry`)."""
    now = time.time() if now is None else now
    got = _rows(network)
    hitl = {"mode": "hitl", "allowed_risk": "", "reason": "", "by": "", "since": "",
            "until": "", "state": got["state"], "error": got["error"], "expired": None,
            "words": "HITL: a person confirms each response"}
    if got["state"] == "unreadable":
        hitl["words"] = (f"HITL: the mode's record cannot be read ({got['error']}), so no "
                         "response runs unattended")
        return hitl
    last = got["rows"][-1] if got["rows"] else None
    if not last or last.get("kind") != "on":
        return hitl
    if now >= float(last.get("until_epoch") or 0):
        return dict(hitl, expired=last,
                    words=f"HITL: AUTO by {last.get('by')} expired {last.get('until')}")
    return {"mode": "auto", "allowed_risk": last.get("allowed_risk"), "reason": last.get("reason"),
            "by": last.get("by"), "since": last.get("at"), "until": last.get("until"),
            "state": "ok", "error": "", "expired": None,
            "words": (f"AUTO until {last.get('until')}, by {last.get('by')}: "
                      f"{last.get('reason')} (risk {last.get('allowed_risk')} and below)")}


def _append(network: str, row: dict) -> dict:
    from modules.config import open_secure
    from modules.filestore import PathLock

    path = _path(network)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PathLock(path):
        got = _rows(network)
        if got["state"] == "unreadable":
            raise ModeRefused(f"the mode's record cannot be read ({got['error']}), so nothing "
                              "was changed")
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def turn_on(network: str, *, actor: str, actor_verified: str, reason: str, until: float,
            allowed_risk: str = "low", now: float = None) -> dict:
    """AUTO on *network* until *until* (epoch), allowing *allowed_risk* and below, as
    *actor* with *reason*. Refuses no network, no verified person, no reason, an expiry not in
    the future or more than `MAX_AUTO_SECONDS` away, an unknown risk."""
    now = time.time() if now is None else now
    if not network:
        raise ModeRefused("AUTO is turned on for one network, and none was named")
    if not actor or actor_verified in ("", "none"):
        raise ModeRefused("AUTO is turned on by a verified person")
    if not (reason or "").strip():
        raise ModeRefused("AUTO is turned on with a recorded reason, and none was given")
    if allowed_risk not in RISKS:
        raise ModeRefused(f"the allowed risk is {' or '.join(RISKS)}, not {allowed_risk!r}")
    if isinstance(until, bool) or not isinstance(until, (int, float)) or until <= now:
        raise ModeRefused(f"AUTO's expiry is in the future, not {until!r}")
    if until - now > MAX_AUTO_SECONDS:
        raise ModeRefused(f"AUTO may be on for at most {MAX_AUTO_SECONDS // 3600} hours; "
                          f"{_iso(until)} is {round((until - now) / 3600, 1)} hours away")
    return _append(network, {"kind": "on", "network": network, "by": actor,
                             "actor_verified": actor_verified, "reason": reason.strip(),
                             "allowed_risk": allowed_risk, "at": _iso(now),
                             "until": _iso(until), "until_epoch": float(until)})


def turn_off(network: str, *, actor: str, actor_verified: str = "", why: str = "",
             now: float = None) -> dict:
    """AUTO off on *network*, at once."""
    now = time.time() if now is None else now
    if not actor:
        raise ModeRefused("AUTO is turned off by someone, and no actor was given")
    if current(network, now)["mode"] != "auto":
        raise ModeRefused(f"AUTO is not on for {network}")
    return _append(network, {"kind": "off", "network": network, "by": actor,
                             "actor_verified": actor_verified, "at": _iso(now),
                             "why": (why or "").strip()})


def record_expiry(network: str, now: float = None) -> dict:
    """Record, once, that AUTO's expiry passed and the mode is HITL again (the loop calls it
    each pass). ``{"recorded": bool}``."""
    now = time.time() if now is None else now
    mode = current(network, now)
    if not mode["expired"]:
        return {"recorded": False}
    last = mode["expired"]
    _append(network, {"kind": "expired", "network": network, "by": "Mercury",
                      "actor_verified": "system", "at": _iso(now),
                      "why": f"AUTO by {last.get('by')} ({last.get('reason')}) reached its "
                             f"expiry {last.get('until')}; the mode is HITL"})
    return {"recorded": True}


def decide(network: str, risk: str, now: float = None) -> dict:
    """Whether a response of *risk* may run unattended on *network* now: ``{"auto": bool,
    "words", "autonomous"}``, *autonomous* the record an autonomous action carries (the
    setting, who turned it on, its reason and expiry)."""
    mode = current(network, now)
    if mode["mode"] != "auto":
        return {"auto": False, "words": mode["words"], "autonomous": None}
    allowed = RISKS[: RISKS.index(mode["allowed_risk"]) + 1] if mode["allowed_risk"] in RISKS \
        else ()
    if risk not in allowed:
        return {"auto": False, "autonomous": None,
                "words": f"HITL for this one: its risk is {risk}, and AUTO allows "
                         f"{mode['allowed_risk']} and below"}
    return {"auto": True, "words": mode["words"],
            "autonomous": {"setting": "sdn AUTO", "by": mode["by"], "reason": mode["reason"],
                           "since": mode["since"], "until": mode["until"],
                           "allowed_risk": mode["allowed_risk"]}}


def history(network: str) -> dict:
    """The mode's changes, oldest first: ``{"state", "rows", "error"}``."""
    return _rows(network)
