"""agent_timers.py

Persistent configuration for background agent timing intervals.

All intervals are stored in data/agent_timers.json and hot-reloaded on each
poll cycle so changes take effect without a server restart.  Provides load/save
helpers, per-key min/max bounds to prevent misconfiguration, and human-readable
labels used by the settings UI.  Defaults are applied for any missing key.
"""

import json
import logging
import os

log = logging.getLogger(__name__)

_TIMERS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "agent_timers.json")

DEFAULTS = {
    "jenkins_poll_interval":  15,       # event_monitor: Jenkins sync
    "event_check_interval":   300,      # event_monitor: golden config / variable checks
    "event_drain_interval":   30,       # agent_runner:  event queue drain
    "drift_check_interval":   14400,    # agent_runner:  config drift (4 hours)
    "trap_flap_window":       15,       # agent_runner:  flap dispatch delay (15 seconds)
    "user_idle_seconds":      90,       # agent_runner:  post-user-activity pause
}

# Human-readable labels for the UI
LABELS = {
    "jenkins_poll_interval":  ("Jenkins Sync",           "How often to poll Jenkins for new build results", "s"),
    "event_check_interval":   ("Event Monitor",          "How often to check for missing golden configs and empty variables", "s"),
    "event_drain_interval":   ("Agent Queue Drain",      "How often the background agent processes queued events", "s"),
    "drift_check_interval":   ("Config Drift Check",     "How often to compare running configs against golden configs", "s"),
    "trap_flap_window":       ("Trap Flap Window",       "Seconds to wait after a down trap before dispatching AI task; recovery within this window cancels it (flap)", "s"),
    "user_idle_seconds":      ("User Idle Threshold",    "How long after a chat message before background tasks resume", "s"),
}

# Min/max bounds to prevent accidental misconfiguration
BOUNDS = {
    "jenkins_poll_interval":  (5,    3600),
    "event_check_interval":   (30,   86400),
    "event_drain_interval":   (10,   3600),
    "drift_check_interval":   (300,  86400),
    "trap_flap_window":       (5,    120),
    "user_idle_seconds":      (10,   600),
}


def load() -> dict:
    """Load timers from disk, filling missing keys from defaults."""
    try:
        with open(_TIMERS_FILE, encoding="utf-8") as fh:
            stored = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        stored = {}

    result = dict(DEFAULTS)
    for key, val in stored.items():
        if key in DEFAULTS:
            lo, hi = BOUNDS[key]
            result[key] = max(lo, min(hi, int(val)))
    return result


def save(timers: dict) -> dict:
    """Validate and persist timer values. Returns the saved (clamped) values."""
    current = load()
    for key, val in timers.items():
        if key not in DEFAULTS:
            continue
        lo, hi = BOUNDS[key]
        current[key] = max(lo, min(hi, int(val)))

    os.makedirs(os.path.dirname(_TIMERS_FILE), exist_ok=True)
    with open(_TIMERS_FILE, "w", encoding="utf-8") as fh:
        json.dump(current, fh, indent=2)
    log.info("agent_timers: saved %s", current)
    return current


def get(key: str) -> int:
    """Get a single timer value."""
    return load().get(key, DEFAULTS[key])


def get_ui_config() -> list:
    """Return timer config in a format ready for the UI."""
    values = load()
    result = []
    for key, (label, description, unit) in LABELS.items():
        lo, hi = BOUNDS[key]
        result.append({
            "key":         key,
            "label":       label,
            "description": description,
            "unit":        unit,
            "value":       values[key],
            "default":     DEFAULTS[key],
            "min":         lo,
            "max":         hi,
        })
    return result
