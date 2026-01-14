"""quick_actions.py

Small persistence helpers for the user-configurable "quick actions"
feature. Quick actions are simple named command/label pairs stored in
a JSON file; the web UI reads this file to populate dropdowns and the
API writes it when the user updates the global quick action list.

This module intentionally stays tiny: load and save operations are
plain JSON reads/writes to keep the format simple and human-editable.
"""

import os
import json
from modules.config import QUICK_ACTIONS_FILE


def load_quick_actions() -> dict:
    """Load quick actions from `QUICK_ACTIONS_FILE`.

    Returns an empty dict when the file does not exist so callers can
    assume a mapping is always returned.
    """
    if os.path.exists(QUICK_ACTIONS_FILE):
        with open(QUICK_ACTIONS_FILE) as f:
            return json.load(f)
    return {}


def save_quick_actions(actions: dict) -> None:
    """Write `actions` to `QUICK_ACTIONS_FILE` as pretty JSON."""
    with open(QUICK_ACTIONS_FILE, "w") as f:
        json.dump(actions, f, indent=2)
