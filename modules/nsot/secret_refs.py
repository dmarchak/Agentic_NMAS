"""nsot/secret_refs.py — the secret references a device's committed intent names, and setting a
value for one (C235; board H-S, approved 2026-11-01: the Intent tab's Secret references card).

Intent holds references only (`user_lab_secret`); values live in the credential store
(`credentials.set_template_secret`, Fernet-encrypted). Until now only seeding, a rotation and the
monitoring profile wrote a value, so a reference a person added (a new account) had none, and its
deploy was refused (`<missing-secret:…>`). `set_value` stores a value a person types, kind
``plaintext``; after its verified deploy the device's own form replaces it
(`credential_rotation.capture_typed_secrets`, C2031), so intent then renders the line the device
holds. The account Mercury signs in with is never set here: it changes by Rotate only.

Write-only: no function returns or logs a value. Every set is recorded and committed in the
network's repository (`.nsot/secret_values.jsonl`): who, when, which device and reference, the
reason; never the value.
"""

import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

#: The record of sets, beside the network's other operation records, committed.
RECORDS_REL = ".nsot/secret_values.jsonl"
#: What a value may hold: printable ASCII, no space (a device's CLI takes it as one token; CLAUDE
#: "Send, read, decide": anything reaching a CLI is printable ASCII), at most 127 characters.
VALUE = re.compile(r"[\x21-\x7e]{1,127}\Z")
#: Set value…'s steps, as its How it works page names them (docs/manual/how-it-works/
#: set-secret-value.md): (key, title, what happens).
STEPS = (
    ("checks", "Check the value",
     "the two entries match, one token a CLI accepts, the reference named in the device's "
     "committed intent and not the account Mercury signs in with, and a reason; any failing "
     "refuses by name and nothing is stored"),
    ("store", "Store it",
     "the value stored encrypted for this device and reference, kind plaintext; nothing is "
     "sent to the device"),
    ("record", "Record the set",
     "who, when, the device, the reference and the reason, committed in the network's "
     "repository; never the value"),
    ("capture_back", "After its deploy",
     "once a deploy carrying it verifies, the device's own form of the value replaces it "
     "(credential_rotation.capture_typed_secrets)"),
)
#: How each state reads on the card (board H-S).
STATES = {
    "device_form": "the device's own form",
    "device_value": "the device's value, as it keeps it",
    "typed": "typed, waiting for its deploy",
    "held": "held",
    "none": "no value",
}


class Refused(ValueError):
    """A set that is not made; the message names what was compared."""


def _repo(list_name: str) -> str:
    """The network's repository, as the intent editor finds it (`intent_edit._repo_for`)."""
    from modules.nsot.intent_edit import _repo_for
    return _repo_for(list_name)


def _intent(list_name: str, host: str) -> dict:
    from modules.nsot import hostvars
    raw, _state = hostvars.committed_at_head(_repo(list_name), host)
    return hostvars.from_yaml(raw) if raw is not None else {}


def _uses(intent: dict) -> dict:
    """``{ref: what it is for}`` for every reference *intent* names (`hostvars.named_refs`, the
    list hydration resolves, so the card and the deploy never disagree on what is named)."""
    from modules.nsot.hostvars import named_refs

    out = {}
    for user in intent.get("users") or []:
        ref = (user or {}).get("secret_ref")
        if ref:
            out[ref] = (f"account {user.get('name')}, privilege {user.get('privilege', 1)}")
    if intent.get("enable_secret_ref"):
        out.setdefault(str(intent["enable_secret_ref"]), "the enable secret")
    snmp = intent.get("snmp") if isinstance(intent.get("snmp"), dict) else {}
    for c in snmp.get("communities") or []:
        if isinstance(c, dict) and c.get("ref"):
            out.setdefault(str(c["ref"]), f"SNMP community, {c.get('access') or 'access unset'}")
    for ref in named_refs(intent):
        out.setdefault(ref, "named in intent")
    return out


def _typed_pending(list_name: str, host: str, ref: str) -> bool:
    """Whether a value a person typed for *ref* on *host* still waits for its deploy: the newest
    set recorded for it (`RECORDS_REL`) is later than the device's newest deploy that verified
    (`receipts`). A value stored by seeding, a profile or a capture was never typed; one a
    verified deploy has carried is on the device, in whatever form the device keeps it (an
    SNMP community is kept as typed, so its kind stays ``plaintext`` for good)."""
    from modules.nsot import receipts

    rows = [r for r in read_records(_repo(list_name))["rows"]
            if r.get("device") == host and r.get("ref") == ref]
    if not rows:
        return False
    typed_at = rows[0].get("at") or ""
    got = receipts.read(list_name, device=host, limit=20)
    deployed = [r.get("completed_at") or r.get("at") or "" for r in got.get("rows") or []
                if r.get("outcome") == "deployed"]
    return not any(t and t >= typed_at for t in deployed)


def _state(list_name: str, host: str, ref: str) -> str:
    from modules import credentials
    kind = credentials.template_secret_kind(credentials.template_secret_key(list_name, host, ref))
    if kind == "hash":
        return "device_form"
    if kind == "plaintext":
        return "typed" if _typed_pending(list_name, host, ref) else "device_value"
    profile = credentials.template_secret_kind(credentials.profile_secret_key(list_name, ref))
    return "held" if profile else "none"


def managed_ref(username: str) -> str:
    """The reference of the account Mercury signs in with (a rotation's `user_<name>_secret`)."""
    return f"user_{username}_secret" if username else ""


def listing(list_name: str, host: str, *, signs_in_as: str = "", intent: dict = None) -> dict:
    """``{"refs": [{"ref", "for", "state", "words", "settable", "why_not"}], "counts"}`` for
    every reference *host*'s committed intent names; never a value. *signs_in_as* is the
    username Mercury signs in to the device with: its reference is not settable here."""
    intent = _intent(list_name, host) if intent is None else intent
    managed = managed_ref(signs_in_as)
    refs = []
    for ref, why in sorted(_uses(intent).items()):
        state = _state(list_name, host, ref)
        refs.append({"ref": ref, "for": why, "state": state, "words": STATES[state],
                     "settable": ref != managed,
                     "why_not": "Mercury signs in with this account: it changes by Rotate only"
                                if ref == managed else ""})
    counts = {s: sum(1 for r in refs if r["state"] == s) for s in STATES}
    return {"refs": refs, "counts": counts}


def check(list_name: str, host: str, ref: str, value: str, again: str, reason: str, *,
          signs_in_as: str = "", intent: dict = None) -> list:
    """The checks the card draws, each ``{"name", "ok", "detail"}``, never naming the value."""
    intent = _intent(list_name, host) if intent is None else intent
    uses = _uses(intent)
    checks = [
        {"name": "the two match", "ok": bool(value) and value == again,
         "detail": "the value and the value again are the same" if value and value == again
         else "the value and the value again differ, or are empty"},
        {"name": "one token a CLI accepts", "ok": bool(VALUE.match(value or "")),
         "detail": "printable characters only, no space, at most 127" if VALUE.match(value or "")
         else "it holds a space, a character a device's CLI does not take, or is too long"},
        {"name": "named in intent", "ok": ref in uses,
         "detail": f"{ref} is {uses[ref]}" if ref in uses
         else f"{ref} is not named in {host}'s committed intent"},
        {"name": "not Mercury's own account", "ok": ref != managed_ref(signs_in_as),
         "detail": "it is not the account Mercury signs in with"
         if ref != managed_ref(signs_in_as)
         else "Mercury signs in with this account: it changes by Rotate only"},
        {"name": "a reason", "ok": bool((reason or "").strip()),
         "detail": "recorded with who and when" if (reason or "").strip()
         else "say why in one line; it is recorded with who and when"},
    ]
    return checks


def set_value(list_name: str, host: str, ref: str, value: str, again: str, reason: str, *,
              actor: str, signs_in_as: str = "", now: float = None) -> dict:
    """Store *value* for *ref* on *host*, kind ``plaintext``, after every `check` passes, and
    record the set (committed): ``{"ok", "record", "checks"}``. Raises `Refused` naming each
    check that failed, nothing stored. Never returns or logs the value."""
    from modules import credentials

    intent = _intent(list_name, host)
    checks = check(list_name, host, ref, value, again, reason, signs_in_as=signs_in_as,
                   intent=intent)
    failed = [c for c in checks if not c["ok"]]
    if failed:
        raise Refused("Not stored: " + "; ".join(f"{c['name']}: {c['detail']}" for c in failed)
                      + ". Nothing was written.")
    credentials.set_template_secret(credentials.template_secret_key(list_name, host, ref), value,
                                    secret_kind="plaintext", list_name=list_name)
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None
                                                                  else now)),
           "device": host, "ref": ref, "by": actor, "reason": reason.strip(),
           "state": "typed"}
    log.info("secret refs: %s set a value for %s on %s (%s)", actor, ref, host, list_name)
    return {"ok": True, "record": record(list_name, row), "checks": checks}


def read_records(repo_dir: str) -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "rows": [...newest first], "error"}``: every
    set's row in the network whose repository is *repo_dir* (the device's History reads it).
    Absent and unreadable are different facts."""
    path = os.path.join(repo_dir, RECORDS_REL)
    if not os.path.exists(path):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except Exception as exc:                          # noqa: BLE001
        return {"state": "unreadable", "rows": [], "error": type(exc).__name__}
    return {"state": "ok", "rows": list(reversed(rows)), "error": ""}


def record(list_name: str, row: dict) -> dict:
    """Append one set's row and commit it through the one commit path; never the value.
    ``{"ok", "error", "commit", "commit_error"}``, never raising: the value is stored whether
    or not its record could be written, and the result says which."""
    from modules.config import open_secure
    from modules.nsot import repo as R

    repo = _repo(list_name)
    path = os.path.join(repo, RECORDS_REL)
    try:
        with R.repo_lock(repo):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open_secure(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
            got = R._commit_paths(list_name, [RECORDS_REL],             # noqa: SLF001
                                  # Not "secret <word>": the message masking reads that as a
                                  # password line.
                                  f"A value set for {row['ref']} on {row['device']}\n\n"
                                  f"{row['reason']}",
                                  [f"Actor: {row.get('by') or 'unknown'}",
                                   f"Secret-Device: {row['device']}"], "secret_value")
    except Exception as exc:                          # noqa: BLE001
        log.error("secret refs: the record was NOT written for %s: %s", row.get("device"),
                  type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__, "commit": "", "commit_error": ""}
    return {"ok": True, "error": "", "commit": got.get("commit", ""),
            "commit_error": "" if got.get("ok") else (got.get("error") or "not committed")}
