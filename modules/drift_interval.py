"""The drift checker's one schedule: how often every network's running configs are compared
with their goldens. Moved out of the AI agent's timers (modules/agent_timers.py, which goes
with the AI family; Phase 7's order, its shared pieces first) with no behaviour change: the
value stays where the host already stores it, `data/agent_timers.json` under
`drift_check_interval`, with the same default and bounds, so nothing stored moves. Only this
key is read or written here; the agent's other timers are the agent's.

Until the AI family's removal, the agent's own page also writes this key (through
`agent_timers.save`): two writers of one stored value, both clamping to the same bounds, for as
long as that page lives."""
import json
import logging
import os

log = logging.getLogger(__name__)

KEY = "drift_check_interval"
#: Four hours, as the agent's timers defaulted it.
DEFAULT = 14400
#: Seconds, as the agent's timers bounded it.
BOUNDS = (300, 86400)
FILE = "agent_timers.json"


def _path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, FILE)


def _stored() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            stored = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return stored if isinstance(stored, dict) else {}


def _clamp(seconds) -> int:
    lo, hi = BOUNDS
    return max(lo, min(hi, int(seconds)))


def get() -> int:
    """The schedule in seconds: the stored value within its bounds, else the default."""
    value = _stored().get(KEY)
    if value is None:
        return DEFAULT
    try:
        return _clamp(value)
    except (TypeError, ValueError):
        return DEFAULT


def save(seconds) -> int:
    """Store the schedule, within its bounds, leaving every other key in the file as it was.
    Returns what was stored."""
    stored = _stored()
    stored[KEY] = _clamp(seconds)
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    with open(_path(), "w", encoding="utf-8") as fh:
        json.dump(stored, fh, indent=2)
    log.info("drift_interval: saved %s s", stored[KEY])
    return stored[KEY]
