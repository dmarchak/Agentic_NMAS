"""nsot/credential_rotation.py

Rotate a device's login credential to a device-generated type-9 secret.

See ``docs/NSOT_SET_CREDENTIAL_PLAN.md`` for the whole design. The two things
that shape this module:

**It is not a template deploy.** The program contains a live secret that the
deploy contract would record in its result, its audit row and its log;
``assert_no_mask()`` correctly refuses masked content on that path; and the
program is generated at apply time rather than derived from committed intent.
So the operator confirms an *operation fingerprint* — every property except the
random value — and the tool guarantees that value was freshly generated and
never recorded.

**Rotation failure and persistence failure are different events.** Once the
device has accepted the new password and it has been verified and committed,
the rotation has *happened*. A later failure to teach Oxidized about it, or to
get it into a startup file, does not un-happen it — and reverting the device at
that point would be destroying a completed change to fix a bookkeeping problem.
Only :data:`VERIFY` failing reverts.
"""

import logging
import secrets
import string

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Password generation
# ---------------------------------------------------------------------------

#: 79 characters. Every exclusion has a reason; see the plan's §1 table.
#:
#: ``?`` is the IOS help key mid-command. Space is the token separator, and
#: excluding it disposes of the leading/trailing-space question entirely.
#: ``" ' \\ ` |`` are quoting, escaping and the CLI filter operator.
#:
#: ``[ ] < > ( )`` are excluded because of **our own redactor**:
#: ``redact._VALUE`` refuses to capture a token beginning with one, so a
#: password starting with ``[`` would not be positionally masked in a log. A
#: defensive measure added elsewhere constrains the generator here, which is
#: the kind of interaction that stays invisible until it is in a log file.
CHARSET = (string.ascii_letters + string.digits + "-_.+=:@#%^&*,;~$!")

LENGTH = 32

#: States. Named rather than booleans because "did it work" has five answers.
ROTATED_PERSISTED = "rotated_and_persisted"
ROTATED_UNVERIFIED = "rotated_persistence_unverified"
REVERTED = "reverted"
REVERT_FAILED = "revert_failed"
NOT_STARTED = "failed_before_any_change"

#: The only step whose failure reverts the device.
VERIFY = "verify_new_credential"


class RotationRefused(Exception):
    """Refused before anything reached the device."""


def generate_password(hostname: str = "device", length: int = LENGTH) -> str:
    """A fresh random password. ``secrets``, never ``random``.

    Validated through the same guards the deploy path uses, so the guard
    decides rather than this function's author.

    The retry catches **only** the guards' own rejections. A first version
    caught ``Exception``, which swallowed a ``TypeError`` from calling
    ``assert_printable`` with the wrong arity and retried it a hundred times —
    reporting "the charset and the guards disagree" when the truth was "this
    function calls the guard incorrectly". A broad except around a validation
    call converts a programming error into a confident, wrong diagnosis.
    """
    from modules.nsot.deploy import UnsendableCommand, assert_sendable
    from modules.nsot.hostvars import NonPrintableContent, assert_printable

    rejected = 0
    for _ in range(100):
        candidate = "".join(secrets.choice(CHARSET) for _ in range(length))
        if candidate != candidate.strip():
            rejected += 1
            continue
        try:
            assert_sendable([rotation_command("x", 15, candidate)])
            assert_printable(candidate, hostname)
        except (UnsendableCommand, NonPrintableContent):
            rejected += 1
            continue
        return candidate
    raise RotationRefused(
        f"could not generate a password the send guards accept after 100 "
        f"attempts ({rejected} rejected) — the charset and the guards "
        "disagree, which is a bug in one of them")


def rotation_command(username: str, privilege, password: str) -> str:
    """The one line sent to the device. Verified on IOS-XE 17.06.01a."""
    priv = f" privilege {privilege}" if privilege not in (None, "") else ""
    return f"username {username}{priv} algorithm-type scrypt secret {password}"


def masked_command(username: str, privilege) -> str:
    """What the plan, the result, the audit row and every log line show."""
    return rotation_command(username, privilege, "<generated>")


def operation_fingerprint(*, device_identity: str, username: str,
                          privilege, capture_hash: str) -> str:
    """What the operator confirms: every property except the random value.

    Deliberately excludes the password — they cannot confirm bytes they are not
    allowed to see. It binds the device, the user, the privilege, the algorithm,
    the charset and length, and the capture the plan was computed against, so a
    confirmation cannot be replayed against a different device or a changed
    device.
    """
    import hashlib
    import json

    payload = {
        "device": device_identity,
        "username": username,
        "privilege": str(privilege),
        "algorithm": "scrypt",
        "charset": hashlib.sha256(CHARSET.encode()).hexdigest()[:12],
        "length": LENGTH,
        "capture_hash": capture_hash,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def persistence_failed(result: dict) -> bool:
    """Did the device rotate but the record of it not reach the boot path?"""
    return result.get("state") == ROTATED_UNVERIFIED


def summarise(result: dict) -> str:
    """One honest sentence. The states are not interchangeable."""
    device = result.get("device", "the device")
    return {
        ROTATED_PERSISTED: (
            f"{device}: rotated, verified, committed, and confirmed present in "
            "the startup config — survives redeploy."),
        ROTATED_UNVERIFIED: (
            f"{device}: ROTATED and committed — the new credential is live and "
            "recorded. Persistence to the startup config is NOT yet verified, "
            "so a redeploy would restore the old password. Retrying; the device "
            "is not reverted for this."),
        REVERTED: (
            f"{device}: the new credential did not verify, so the original was "
            "restored and proven. The device is unchanged."),
        REVERT_FAILED: (
            f"{device}: the new credential did not verify AND the revert "
            "failed. THE DEVICE MAY BE LOCKED OUT — recover on the serial "
            "console (see the plan's GAP 3)."),
        NOT_STARTED: (
            f"{device}: refused before anything was sent. The device is "
            "untouched."),
    }.get(result.get("state"), f"{device}: unknown state")
