"""netbox_authz.py

One-shot authorization for a single NetBox write operation.

Two independent things must both be true before a write executes:

1. **``netbox_allow_writes``** — the master switch. It means "this NMAS instance
   is *permitted* to write to NetBox at all", not "writes are open". It is a
   persistent operator decision and never flips as a side effect of confirming
   an operation.
2. **A valid authorization token** — issued by a preview, bound to a hash of the
   plan that preview produced, short-lived, and consumable exactly once.

On execute the plan is **recomputed** and re-hashed. If NetBox changed between
preview and confirm the hashes differ and the operation aborts, so the operator
can never approve one set of changes and have a different set applied.

The token store is in-process, which matches the app's single-process
deployment. Tokens do not survive a restart — a restart simply means the
operator previews again.
"""

import hashlib
import json
import logging
import secrets
import threading
import time

log = logging.getLogger(__name__)

#: Tokens are meant to be confirmed within a few minutes of previewing.
DEFAULT_TTL_SECONDS = 300

_tokens: dict = {}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Plan hashing
# ---------------------------------------------------------------------------

def _normalize(value):
    """Canonicalise a plan value so the hash is stable across runs.

    Synthetic ids assigned during a dry run are negative and depend on the order
    objects happened to be visited, which varies because the sync scans devices
    in a thread pool. They carry no identity, so they collapse to a placeholder.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value < 0:
        return "<new>"
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in sorted(value.items())}
    return value


def compute_plan_hash(plan: dict) -> str:
    """Return a stable SHA-256 over the operations a plan describes.

    Order-insensitive: entries are sorted, because the plan is built from a
    thread pool and the same NetBox state must always produce the same hash.
    """
    entries = []
    for kind in ("creates", "updates", "deletes"):
        for entry in (plan or {}).get(kind, []):
            entries.append(json.dumps({
                "kind":     kind,
                "endpoint": entry.get("endpoint", ""),
                "name":     entry.get("name", ""),
                "id":       _normalize(entry.get("id")),
                "payload":  _normalize(entry.get("payload") or {}),
            }, sort_keys=True))
    entries.sort()
    digest = hashlib.sha256()
    for item in entries:
        digest.update(item.encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def _purge_expired_locked(now: float) -> None:
    for token in [t for t, e in _tokens.items() if e["expires_at"] <= now]:
        del _tokens[token]


def issue_token(operation: str, list_name: str, plan_hash: str,
                ttl: int = DEFAULT_TTL_SECONDS) -> dict:
    """Issue a single-use authorization token for one previewed operation."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _lock:
        _purge_expired_locked(now)
        _tokens[token] = {
            "operation":  operation,
            "list_name":  list_name,
            "plan_hash":  plan_hash,
            "expires_at": now + ttl,
        }
    log.info("netbox_authz: issued token for %s on '%s' (ttl %ds)",
             operation, list_name, ttl)
    return {"token": token, "expires_in": ttl, "plan_hash": plan_hash}


def consume_token(token: str, operation: str, list_name: str) -> tuple:
    """Consume a token. Returns ``(ok, error, plan_hash)``.

    The token is removed whether or not it validates, so a token can never be
    replayed — not even after a failed attempt.
    """
    now = time.time()
    with _lock:
        _purge_expired_locked(now)
        entry = _tokens.pop(token, None)

    if entry is None:
        return False, ("This confirmation has expired or was already used. "
                       "Run the preview again."), ""
    if entry["operation"] != operation:
        return False, "This confirmation was issued for a different operation.", ""
    if entry["list_name"] != list_name:
        return False, "This confirmation was issued for a different device list.", ""
    return True, "", entry["plan_hash"]


def verify_plan_unchanged(expected_hash: str, current_plan: dict) -> tuple:
    """Compare a freshly recomputed plan against the approved one."""
    current = compute_plan_hash(current_plan)
    if current != expected_hash:
        return False, ("NetBox changed since preview — the operation was not "
                       "performed. Review the new preview and confirm again.")
    return True, ""


def active_token_count() -> int:
    """Outstanding unconsumed tokens. For tests and diagnostics."""
    with _lock:
        _purge_expired_locked(time.time())
        return len(_tokens)


def clear_tokens() -> None:
    """Drop every outstanding token. Used by tests."""
    with _lock:
        _tokens.clear()
