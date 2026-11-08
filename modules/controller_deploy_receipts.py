"""The controller app deploy's receipts, and Mercury's record of each controller's set (P6; the
signed board docs/boards/controller-app-deploy.html, artboard H and decision K2; C2677).

**Where (K2).** One JSON line per deploy in ``data/lists/<slug>/controller_deploy_receipts.jsonl``,
beside the device deploys' ``deploy_receipts.jsonl`` (`modules/nsot/receipts`), owner-only from
creation (`config.open_secure`), append-only. A receipt is written for every confirm that reached
the operation: deployed, rolled back, rollback failed, not rolled back, apply failed, unknown,
and refused (the plan moved since the preview, the controller held by another operation), so a
record that lists only the deploys that went through never silently omits the rest.

**Masked at rest, as History masks** (`masked`): every string the receipt carries passes through
Mercury's one redactor (`redact.redact_text`) on the way in, and History's reader masks again on
the way out (`modules/history_sources.controller_deploys`). A receipt carries the request (names,
versions, content hashes, the listen address), the drop-in texts and the start-time configs
(which the plan refuses when they hold anything the redactor masks: decision K9), so masking
leaves them as they were; a value that would be masked never reaches the file.

**Mercury's record of a controller's set (`record`, K2)** is the last receipt whose outcome left
the controller running a request Mercury recorded:
- "deployed": the receipt's request;
- "rolled back" to the request before (the rollback target's kind ``request``): that request;
- "rolled back" by putting the drop-in before back (kind ``dropin_before``, K3): no request
  Mercury recorded runs (the unit's own drop-in does), so the record is none;
- "not rolled back" after an apply that succeeded (the post-check missed with no rollback
  target): the receipt's request, which the controller runs;
- "apply failed" and "refused" changed nothing, so the receipt before decides;
- "unknown", "rollback failed", and "not rolled back" after a failed apply leave what runs not
  known: the record is ``unknown``, said, never guessed.
No receipt is ``none`` (the first deploy through Mercury); a file that cannot be read is
``unreadable``, and a plan is refused on it (what a miss rolls back to would not be known).
"""

import json
import logging
import os
import time
import uuid

log = logging.getLogger(__name__)

FILENAME = "controller_deploy_receipts.jsonl"

#: The receipt's outcomes (`post_check.deploy`'s, and "refused" for a confirm that sent nothing).
OUTCOMES = ("deployed", "rolled back", "rollback failed", "not rolled back", "apply failed",
            "unknown", "refused")
#: Outcomes after which the controller runs what it ran before the deploy.
UNCHANGED = ("apply failed", "refused")


def path_for(network: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), FILENAME)


def masked(value):
    """Every string in *value* masked by the one redactor, its shape kept."""
    from modules.redact import redact_text

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: masked(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [masked(v) for v in value]
    return value


def new_id() -> str:
    return uuid.uuid4().hex


def iso(at: float = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if at is None else at))


def write(network: str, receipt: dict) -> dict:
    """Append *receipt*, masked. ``{"ok", "id", "error"}``; never raises (the deploy has
    happened and a failed receipt must not read as a failed deploy), logged at ERROR and
    returned instead, so the result names it."""
    from modules.config import open_secure

    row = masked(dict(receipt))
    row.setdefault("id", new_id())
    row.setdefault("at", iso())
    row["network"] = network
    path = path_for(network)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception as exc:                          # noqa: BLE001 (returned and logged)
        log.error("controller deploy receipts: could not write %s's receipt for %s: %s",
                  row.get("controller"), network, exc)
        return {"ok": False, "id": row["id"],
                "error": f"the deploy ran and its receipt could not be written: {exc}"}
    return {"ok": True, "id": row["id"], "error": ""}


def read(network: str, controller: str = "", limit: int = 200) -> dict:
    """``{"state": "absent"|"ok"|"unreadable", "rows", "error"}``, newest first. A line that
    will not parse makes the whole read unreadable rather than being skipped: a receipt
    quietly missing would move Mercury's record of the set."""
    path = path_for(network)
    try:
        if not os.path.exists(path):
            return {"state": "absent", "rows": [], "error": ""}
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except Exception as exc:                          # noqa: BLE001 (said, never "none")
        return {"state": "unreadable", "rows": [], "error": f"{type(exc).__name__}: {exc}"}
    if any(not isinstance(r, dict) for r in rows):
        return {"state": "unreadable", "rows": [],
                "error": "a line of the receipts is not a JSON object"}
    if controller:
        rows = [r for r in rows if r.get("controller") == controller]
    return {"state": "ok", "rows": list(reversed(rows))[:limit], "error": ""}


def get(network: str, rid: str):
    """The receipt *rid* of *network*, or None (absent, or the store unreadable: `read`'s
    state says which)."""
    got = read(network, limit=10 ** 6)
    return next((r for r in got["rows"] if r.get("id") == rid), None)


def runs_after(r: dict) -> dict:
    """What the controller runs after receipt *r*, by its outcome: ``{"state":
    "request"|"none"|"unchanged"|"unknown", "request", "words"}`` (the module's docstring)."""
    outcome = r.get("outcome")
    when = f"the deploy of {r.get('at', '?')} by {r.get('actor') or '?'}"
    if outcome == "deployed":
        return {"state": "request", "request": r.get("request"), "words": f"{when}, deployed"}
    if outcome == "rolled back":
        before = r.get("before") or {}
        if before.get("kind") == "request" and before.get("request"):
            return {"state": "request", "request": before["request"],
                    "words": f"the request before {when}, which rolled back to it"}
        return {"state": "none", "request": None,
                "words": (f"{when} was rolled back by putting the drop-in before back, so the "
                          "controller runs no request Mercury recorded")}
    if outcome == "not rolled back" and r.get("post_check"):
        return {"state": "request", "request": r.get("request"),
                "words": f"{when}, whose post-check missed and which nothing rolled back"}
    if outcome in UNCHANGED:
        return {"state": "unchanged", "request": None, "words": f"{when}: {outcome}"}
    return {"state": "unknown", "request": None,
            "words": (f"{when} ended {outcome or 'with no outcome'}, so what the controller runs "
                      "is not known")}


def record(network: str, controller: str) -> dict:
    """Mercury's record of *controller*'s set (K2): ``{"state": "ok"|"none"|"unknown"|
    "unreadable", "request", "receipt", "words"}``; *receipt* is the receipt that decided it
    (its ``configs`` are what a rollback to its request stages again)."""
    got = read(network, controller, limit=10 ** 6)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "request": None, "receipt": None,
                "words": (f"Mercury's record of {controller}'s set cannot be read "
                          f"({path_for(network)}: {got['error']})")}
    for r in got["rows"]:
        after = runs_after(r)
        if after["state"] == "unchanged":
            continue
        if after["state"] == "request":
            return {"state": "ok", "request": after["request"], "receipt": r,
                    "words": f"Mercury's record: {after['words']}"}
        if after["state"] == "none":
            return {"state": "none", "request": None, "receipt": r, "words": after["words"]}
        return {"state": "unknown", "request": None, "receipt": r, "words": after["words"]}
    return {"state": "none", "request": None, "receipt": None,
            "words": f"no deploy through Mercury is recorded for {controller}"}


def configs_for(rec: dict, request: dict) -> dict:
    """The start-time configs a rollback to *request* stages again: the deciding receipt's own
    when *request* is its request, its ``before_configs`` when it is the request before."""
    r = (rec or {}).get("receipt") or {}
    if request is not None and request == r.get("request"):
        return dict(r.get("configs") or {})
    if request is not None and request == (r.get("before") or {}).get("request"):
        return dict(r.get("before_configs") or {})
    return {}
