"""quick_actions.py

Persistence helpers for user-defined quick actions (command shortcuts).

Quick actions are name/command pairs stored in data/quick_actions.json.
The web UI reads the file to populate command shortcut dropdowns; the API
writes it when the user saves an updated list.  The format is intentionally
plain JSON so it can be hand-edited if needed.
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
