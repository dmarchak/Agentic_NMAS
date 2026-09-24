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

**A verdict about the device requires having asked the device.** A failure
local to this process — a bad decrypt, a missing import — is not evidence
about anything on the network, so it is classified separately
(``attempted: False``), retried while the held session is still open, and, if
it persists, reported as :data:`REVERTED_UNPROVEN` rather than as a lockout.
The first hardware run got this wrong and printed its most alarming message
from code that never opened a socket.
"""

import logging
import re
import secrets
import string
import time

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
#: ``:`` is EXCLUDED because it is Oxidized's router.db field delimiter.
#: The helper refuses a colon rather than corrupting the file, so the failure
#: is safe — but it lands AFTER the device has been rotated and committed,
#: leaving the credential live and the boot copy behind. With 32 characters
#: drawn from this set, P(at least one colon) was 1 - (78/79)**32 = 0.335:
#: roughly one rotation in three would have stranded a device that way. r2's
#: password happened not to contain one.
#:
#: Not escaped: Oxidized's csv source splits on a bare regexp (`/:/`) with no
#: escape handling, so there is nothing to escape it *to*. Verified in
#: oxidized-0.37.0's sshbase/csv source, not assumed.
CHARSET = (string.ascii_letters + string.digits + "-_.+=@#%^&*,;~$!")

LENGTH = 32

#: States. Named rather than booleans because "did it work" has six answers.
#: The sixth was added after the first hardware run: a verdict about the
#: device may only be reported when the device was actually asked.
ROTATED_PERSISTED = "rotated_and_persisted"
#: Rotated and committed; persistence has NOT BEEN ATTEMPTED yet. This is the
#: state between the commit and the first persistence stage.
#:
#: It exists because :data:`ROTATED_UNVERIFIED` used to mean both this and
#: "persistence ran and failed", and one string cannot carry two states. The
#: end-of-rotation summary therefore printed the FAILURE wording — "FAILED at
#: the persistence chain. Nothing is retrying ... fix the cause" — before
#: persistence had started, on a run that then succeeded. Telling an operator
#: to abandon a run that is about to work is worse than saying nothing.
ROTATED_PENDING_PERSIST = "rotated_persistence_not_attempted"
#: Persistence was ATTEMPTED and did not complete.
ROTATED_UNVERIFIED = "rotated_persistence_unverified"
REVERTED = "reverted"
REVERT_FAILED = "revert_failed"
#: Reverted, and the proof could not RUN — a local fault, not a device verdict.
#: Distinct from REVERT_FAILED, which means the device was asked and refused.
#: The distinction exists because the first hardware run produced "MAY BE
#: LOCKED OUT" from code that never opened a socket.
REVERTED_UNPROVEN = "reverted_proof_inconclusive"
NOT_STARTED = "failed_before_any_change"

#: Passed as *confirmed_fingerprint* by a caller with **no separate plan
#: step**, so there is no window between a plan and an apply to protect.
#:
#: The fingerprint check exists because `plan()` shows an operator a program
#: and `rotate()` must refuse if the device or the plan moved in between.
#: Onboarding's phase 2 is one click running seven steps atomically: the
#: preflight it would rotate against is the one it just computed, and
#: comparing a hash to itself protects nothing.
#:
#: **Explicit, and recorded as a step**, so a reader of the result sees that
#: the comparison was skipped and why. A silently skipped check is what the
#: fingerprint was added to stop.
SELF_CONFIRMED = "self-confirmed:no-separate-plan-step"

#: The only step whose failure reverts the device.
VERIFY = "verify_new_credential"


class RotationRefused(Exception):
    """Refused before anything reached the device."""


#: Where the root-owned helper is installed, and where its source of truth is.
HELPER_INSTALLED = "/usr/local/sbin/nmas-oxidized-cred"
HELPER_SOURCE_REL = "scripts/nmas-oxidized-cred"

#: Built at CALL time, not at import: baking HELPER_INSTALLED in with `+`
#: meant the reinstall hint named the original destination even after the path
#: changed — a message telling the operator to install to the wrong place.
INSTALL_TEMPLATE = "sudo install -o root -g root -m 0755 {source} {dest}"


def install_command(source: str) -> str:
    return INSTALL_TEMPLATE.format(source=source, dest=HELPER_INSTALLED)


def _repo_root() -> str:
    import os
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


def helper_status() -> dict:
    """Is the installed helper the same script this repo ships?

    The installed copy is a **snapshot**. It is root-owned and deliberately
    outside the repository, so it does not move when the repo does — and the
    repo is where the helper's tests live. A repo whose tests pass while a
    different script actually runs as root is a test suite describing something
    that is not deployed.

    Checked in preflight and refused on mismatch, rather than discovered when
    the installed version does something the tested one does not.
    """
    import hashlib
    import os

    source = os.path.join(_repo_root(), HELPER_SOURCE_REL)
    out = {"installed_path": HELPER_INSTALLED, "source_path": source,
           "reinstall": install_command(source)}

    if not os.path.exists(source):
        return {**out, "ok": False, "state": "source_missing",
                "reason": f"{HELPER_SOURCE_REL} is missing from the repository"}
    if not os.path.exists(HELPER_INSTALLED):
        return {**out, "ok": False, "state": "not_installed",
                "reason": (f"{HELPER_INSTALLED} is not installed — "
                           "router.db cannot be updated")}

    def _sha(path):
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    installed_sha, source_sha = _sha(HELPER_INSTALLED), _sha(source)
    out.update({"installed_sha": installed_sha[:12],
                "source_sha": source_sha[:12]})
    if installed_sha != source_sha:
        return {**out, "ok": False, "state": "drifted",
                "reason": (f"the installed helper differs from "
                           f"{HELPER_SOURCE_REL}. The tests in this repository "
                           "describe the repo copy, not the one that would "
                           "run as root.")}

    st = os.stat(HELPER_INSTALLED)
    if st.st_uid != 0:
        return {**out, "ok": False, "state": "not_root_owned",
                "reason": (f"{HELPER_INSTALLED} is owned by uid {st.st_uid}, "
                           "not root — a sudoers entry pointing at it would be "
                           "a root shell for whoever can write it")}
    if st.st_mode & 0o022:
        return {**out, "ok": False, "state": "group_or_world_writable",
                "reason": (f"{HELPER_INSTALLED} is writable by group or other "
                           f"(mode {oct(st.st_mode & 0o777)})")}

    return {**out, "ok": True, "state": "ok"}


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


#: IOS-XE prompts before deleting a username. Measured verbatim on r2:
#: "This operation will remove all username related configurations with same
#: name.Do you want to continue? [confirm]" (the missing space is the
#: device's). An unanswered prompt leaves the session mid-dialogue, which is
#: how the first probe run desynced.
CONFIRM_PROMPT = r"\[confirm\]|\[yes/no\]"


def entry_kind(line: str) -> str:
    """Does this ``username`` line hold a ``secret`` or a ``password``?

    The answer decides the whole program, because the device's refusal is
    asymmetric: measured on IOS-XE 17.06 a secret over a PASSWORD entry is
    refused, and measured on vIOS-L2 15.2 a secret over a SECRET entry
    replaces cleanly with no complaint at all.

    Returns ``""`` when it cannot tell, which callers must treat as "assume
    the worst and send the two-command form".
    """
    parts = (line or "").split()
    if parts[:1] != ["username"]:
        return ""
    for keyword in ("secret", "password"):
        if keyword in parts:
            return keyword
    return ""


def rotation_commands(username: str, privilege, password: str,
                      current_kind: str = "") -> list[str]:
    """The program sent to the device. One command or two, per MEASUREMENT.

    The original one-liner could never have worked on any device in this
    fleet. Measured on r2 (IOS-XE 17.06.01a), pushing a secret at a username
    that already has a ``password`` entry is refused::

        ERROR: Can not have both a user password and a user secret.
        Please choose one or the other.

    The command is well-formed, so there is no ``% Invalid input``; the device
    declines it on semantic grounds and keeps the old line. Every device in
    this fleet carries ``password 0 <x>``, so every one of them would have
    refused. r2 was not unlucky.

    ``secret 0`` without ``algorithm-type`` is refused identically, which is
    what rules out the keyword as the cause rather than the coexistence.

    Measured on vIOS-L2 15.2, where the account already holds a ``secret 5``,
    the same push is accepted silently and replaces it: the config becomes
    ``secret 9``, the new password authenticates and the old one stops. So the
    deletion is required by the PASSWORD case and by nothing else, and sending
    it anyway would delete and recreate an account for no reason.

    When the existing entry IS a password, it must go first. Two ways were
    measured, and the choice between them is about the failure window, not
    elegance:

    ``no username`` then set          the account is briefly ABSENT -> logins
                                      fail. **Chosen.**
    ``nopassword`` then set           the account is briefly PASSWORDLESS ->
                                      at privilege 15, an open door.

    Both commands go in one ``send_config_set`` so the window is one round
    trip, and the held original session is what recovers from a failure
    between them — it stays authenticated, because IOS does not drop
    established sessions when a username is removed.
    """
    priv = f" privilege {privilege}" if privilege not in (None, "") else ""
    setter = (f"username {username}{priv} "
              f"algorithm-type scrypt secret {password}")

    # A secret over a SECRET is accepted, so the deletion is not merely
    # unnecessary — it is harmful. It opens a window in which the account does
    # not exist and raises a [confirm] prompt, both for nothing.
    if current_kind == "secret":
        return [setter]

    # A secret over a PASSWORD is refused, and an unknown kind is treated as a
    # password: the two-command form works in BOTH states (measured on IOS-XE
    # 17.06 and vIOS-L2 15.2), so it is the safe answer when we cannot tell.
    return [f"no username {username}", setter]


def rotation_command(username: str, privilege, password: str) -> str:
    """The credential-setting line alone, for fingerprinting and display.

    Deliberately NOT what is sent — :func:`rotation_commands` is. Kept
    separate because the fingerprint the operator confirms should describe the
    credential being set, and prefixing it with a deletion would change every
    stored fingerprint without changing what is being asked for.
    """
    priv = f" privilege {privilege}" if privilege not in (None, "") else ""
    return f"username {username}{priv} algorithm-type scrypt secret {password}"


def masked_commands(username: str, privilege, current_kind: str = "") -> list[str]:
    """Exactly what the operator confirms — the program chosen for THIS device."""
    return rotation_commands(username, privilege, "<generated>", current_kind)


def revert_commands(username: str, original_line: str,
                    current_kind: str = "secret") -> list[str]:
    """Putting *original_line* back, conditional for the same reason.

    After a rotation the account holds a ``secret``. Restoring a line that
    sets a ``password`` hits the refusal mirrored, so it needs the deletion
    first. Restoring a line that sets a ``secret`` — which is every switch,
    whose original is a pasted ``secret 5 $1$…`` hash — does not.

    Both forms were measured restoring a type-5 hash over a type-9 secret on
    vIOS-L2: the line comes back byte-identical and the old password
    authenticates again. Restoring a pasted hash is a different operation from
    typing a plaintext password, and it is the stage 2 lockout defence, so it
    was measured rather than assumed.
    """
    if entry_kind(original_line) == "secret" and current_kind == "secret":
        return [original_line]
    return [f"no username {username}", original_line]


def masked_command(username: str, privilege) -> str:
    """What the plan, the result, the audit row and every log line show."""
    return rotation_command(username, privilege, "<generated>")


def normalize_user_line(line: str) -> str:
    """The username line reduced to the facts a confirmation should bind.

    Whitespace is collapsed and the line is stripped, so a device that renders
    the same configuration with different spacing does not read as a change.
    Nothing else is touched: the secret token IS the fact being confirmed, and
    normalising it away would let the credential change under a confirmation
    that still matched.
    """
    return " ".join((line or "").split())


def fingerprint_for(pre: dict) -> str:
    """THE fingerprint for a preflight result. One function, both callers.

    `plan()` and `rotate()` each built this themselves, and when `entry_kind`
    was added to the inputs only `plan()` was updated. `rotate()` went on
    computing without it, so the two could never agree and every confirmation
    on the new code path was refused — safely, and permanently. The default
    value on the new parameter is what made that possible: a caller that
    omitted a now-required input still ran, and silently produced a different
    hash.

    Two callers computing the same hash from the same data is a rule that can
    be broken. One function is a rule that cannot.
    """
    return operation_fingerprint(
        device_identity=pre.get("identity", ""),
        username=pre.get("username", ""),
        privilege=pre.get("privilege", ""),
        entry_kind=pre.get("entry_kind", ""),
        user_line=pre.get("original_line") or pre.get("current_line") or "")


def operation_fingerprint(*, device_identity: str, username: str,
                          privilege, entry_kind: str, user_line: str) -> str:
    """What the operator confirms: every property except the random value.

    Deliberately excludes the password — they cannot confirm bytes they are not
    allowed to see. It binds the device, the user, the privilege, the algorithm,
    the charset and length, so a confirmation cannot be replayed against a
    different device.

    **Every parameter is required.** Giving one a default is what let
    ``rotate()`` omit ``entry_kind`` and compute a hash that could never match
    the plan's.

    What it binds about the device's state is the **normalized username
    line** and the **entry kind** — the two facts the program actually depends
    on — and not a hash of the whole captured config. A whole-config hash
    changes for reasons that have nothing to do with this operation: a
    re-saved golden, a timestamp line, an NTP clock-period drift. Binding it
    made the confirmation refuse changes it had no business refusing, which is
    safe and still wrong.

    The entry kind is bound because the program is conditional on it — one
    command over an existing secret, two over a password — so the commands are
    a pure function of the bound inputs only while it is one of them.
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
        "entry_kind": entry_kind,
        "user_line": hashlib.sha256(
            normalize_user_line(user_line).encode()).hexdigest()[:32],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def persistence_failed(result: dict) -> bool:
    """Did persistence RUN and fail? Not "has it finished"."""
    return result.get("state") == ROTATED_UNVERIFIED


def rotation_succeeded(result: dict) -> bool:
    """Is the device rotated, whatever became of the persistence chain?"""
    return result.get("state") in (ROTATED_PENDING_PERSIST,
                                   ROTATED_UNVERIFIED, ROTATED_PERSISTED)


def _failed_stage(result: dict) -> str:
    """The persistence stage that failed, for a message that names it."""
    for stage in result.get("persistence") or []:
        if not stage.get("ok"):
            return f"{stage.get('name')} ({stage.get('error', 'no reason')})"[:120]
    return ""


def summarise(result: dict) -> str:
    """One honest sentence. The states are not interchangeable."""
    device = result.get("device", "the device")
    return {
        ROTATED_PERSISTED: (
            f"{device}: rotated, verified, committed, and confirmed present in "
            "the startup config — survives redeploy."),
        # Rotated, persistence not yet attempted. Says what happens NEXT,
        # and nothing about failure — there is none to report yet.
        ROTATED_PENDING_PERSIST: (
            f"{device}: ROTATED, verified and committed. The new credential is "
            "live and recorded. Persistence to the startup config runs next."),
        # No "retrying": by the time this is printed the process has exited
        # and nothing is retrying. A terminal message that describes work
        # which is not happening is worse than no message — it tells the
        # operator to wait for an outcome that will never arrive.
        ROTATED_UNVERIFIED: (
            f"{device}: ROTATED and committed — the new credential is live and "
            "recorded, and the device is NOT reverted for this. Persistence to "
            f"the startup config FAILED at "
            f"{_failed_stage(result) or 'the persistence chain'}. Nothing is "
            "retrying. A redeploy would boot the OLD password, so do not "
            "redeploy until this is finished: fix the cause, then run "
            f"`scripts/nmas-persist-credential {device}`."),
        REVERTED: (
            f"{device}: the new credential did not verify, so the original was "
            "restored and proven. The device is unchanged."),
        # Three ways to get here, all of them device-side: no original line
        # was captured, the revert push failed, or the device refused the
        # original afterwards. `reason` says which; the danger is the same.
        REVERT_FAILED: (
            f"{device}: the new credential did not verify and the revert did "
            f"not succeed — {result.get('reason', 'no reason recorded')}. "
            "THE DEVICE MAY BE LOCKED OUT — recover on the serial console "
            "(see the plan's GAP 3)."),
        REVERTED_UNPROVEN: (
            f"{device}: the original credential was re-sent on the held "
            "session, but the proof could not RUN — a local fault, with no "
            "connection attempted. This is NOT evidence the device is "
            "unreachable. Check it directly before assuming anything."),
        NOT_STARTED: (
            f"{device}: refused before anything was sent. The device is "
            "untouched."),
    }.get(result.get("state"), f"{device}: unknown state")


# ---------------------------------------------------------------------------
# Device-facing steps
#
# Each is a module-level function so tests can replace one without a device.
# The sequence lives in `rotate()`; these are the seams it runs through.
# ---------------------------------------------------------------------------

STAGING_REL = ".nsot/staging/credential"


def stage_plaintext(repo: str, hostname: str, password: str) -> str:
    """Park the new password, encrypted, BEFORE anything is pushed.

    The crash window is between the device accepting the password and the
    credential store being written: for that interval the new credential exists
    only in this process, and a crash leaves a device nobody can log into.
    """
    import os

    from modules.secrets_store import encrypt_value

    directory = os.path.join(repo, STAGING_REL)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = os.path.join(directory, f"{hostname}.enc")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(encrypt_value(password))
    os.chmod(path, 0o600)
    return path


def staged_plaintext(repo: str, hostname: str):
    """Recover a staged password after a crash, or ``None``."""
    import os

    from modules.secrets_store import decrypt_value

    path = os.path.join(repo, STAGING_REL, f"{hostname}.enc")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return decrypt_value(fh.read().strip())


def clear_staged(repo: str, hostname: str) -> None:
    import os

    path = os.path.join(repo, STAGING_REL, f"{hostname}.enc")
    if os.path.exists(path):
        os.remove(path)


def current_user_line(config_text: str, username: str) -> str:
    """The device's existing ``username`` line, verbatim — the revert target."""
    import re

    pattern = re.compile(rf"^username\s+{re.escape(username)}\s+.*$", re.M)
    match = pattern.search(config_text or "")
    return match.group(0) if match else ""


def captured_hash(config_text: str, username: str) -> str:
    """The stored secret the DEVICE produced, e.g. ``9 $9$…``."""
    import re

    line = current_user_line(config_text, username)
    match = re.search(r"\b(?:secret|password)\s+(\d+\s+\S+|\S+)\s*$", line)
    return match.group(1).strip() if match else ""


def open_original_session(device: dict):
    """A DEDICATED authenticated session, held open across the rotation.

    Deliberately not the pooled connection: the pool is shared, may be evicted
    by another operation mid-rotation, and is the thing that must be dropped
    afterwards because it holds the old credential. This session exists solely
    so there is a guaranteed-authenticated channel to revert on.
    """
    from netmiko import ConnectHandler

    from modules.connection import connection_params
    from modules.device import decrypt_field

    conn = ConnectHandler(**connection_params(
        device,
        password=decrypt_field(device["password"]),
        secret=decrypt_field(device.get("secret", "") or device["password"])))
    conn.enable()
    # Prove it, rather than trusting that connect() succeeding means usable.
    conn.send_command("show clock", read_timeout=30)
    return conn


#: A config with fewer top-level lines than this is not a device's
#: configuration, whatever produced it. A real IOS running-config here is
#: 300+ lines; the fragment that got committed was two.
MIN_CONFIG_LINES = 20


def capture_running_config(session) -> str:
    """The WHOLE running config, from the held session.

    Deliberately separate from the verify's read. The verify runs
    ``show running-config | include ^username`` — exactly right for proving a
    login and reading back one hash, and exactly wrong as a golden config.
    Sharing one read between "prove the credential" and "record the device"
    is what silently replaced two devices' goldens with a two-line fragment.
    """
    from modules.settings_schema import get_setting

    timeout = float(get_setting("nsot_config_read_timeout", 120))
    try:
        return session.send_command("show running-config",
                                    read_timeout=timeout) or ""
    except Exception as exc:                   # noqa: BLE001
        log.error("rotate: post-rotation capture failed: %s",
                  type(exc).__name__)
        return ""


def _current_golden(repo: str, hostname: str) -> str:
    """What the golden already holds, so a bad capture can leave it alone."""
    import os

    from modules.nsot import manifest as _m

    try:
        _identity, entry = _m.find_by_name(repo, hostname)
        path = _m.golden_path_for(repo, entry) if entry else ""
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return fh.read()
    except Exception:                          # noqa: BLE001
        pass
    return ""


def looks_like_a_full_config(text: str) -> bool:
    """Cheap guard against storing a fragment as a golden.

    Not a fidelity check — a fidelity check belongs to the round-trip work.
    This only answers "could this plausibly be a device's whole config", which
    is the question nobody asked before overwriting one.
    """
    lines = [l for l in (text or "").splitlines() if l.strip()]
    if len(lines) < MIN_CONFIG_LINES:
        return False
    top = [l for l in lines if l and not l.startswith((" ", "!"))]
    return len(top) >= 10


def push_rotation(session, commands) -> dict:
    """Send the program on the ALREADY-AUTHENTICATED original session.

    ``no username`` raises a ``[confirm]`` prompt on this image, and
    ``send_config_set`` has no way to answer one — it waits for a prompt that
    never comes, times out, and leaves the session mid-dialogue. So the
    commands are sent with timing-based reads and the prompt is answered
    explicitly.

    The refusal check is done here, against the WHOLE transcript, rather than
    delegated: this is the path that read "ERROR: Can not have both a user
    password and a user secret." as a successful push.
    """
    import re

    from modules.pipeline import IOS_ERROR_PATTERN

    if isinstance(commands, str):               # one line, older callers
        commands = [commands]

    transcript = ""
    session.config_mode()
    try:
        for command in commands:
            # Only THIS command's output may trigger an answer. Searching the
            # accumulated transcript re-matched the previous command's
            # [confirm] and sent a second, unasked-for Enter — harmless at a
            # config prompt, and exactly the kind of stray keystroke that gets
            # consumed as the answer to some later prompt.
            out = session.send_command_timing(
                command, strip_prompt=False, strip_command=False)
            transcript += out
            if re.search(CONFIRM_PROMPT, out, re.I):
                transcript += session.send_command_timing(
                    "\n", strip_prompt=False, strip_command=False)
    finally:
        try:
            session.exit_config_mode()
        except Exception:                       # noqa: BLE001
            pass

    refusal = re.search(IOS_ERROR_PATTERN, transcript)
    if refusal:
        line = next((l.strip() for l in transcript.splitlines()
                     if re.search(IOS_ERROR_PATTERN, l)), refusal.group(0))
        raise RotationRefused(f"the device refused the command: {line}"[:300])
    return {"ok": True, "output_len": len(transcript)}


#: Netmiko/paramiko failures that mean "the device answered and refused us".
#: Anything else that goes wrong before or around the socket is OUR fault, not
#: a verdict about the device.
#: Exception NAMES the device produced: it answered, or it could not be
#: reached. Either way the network was consulted, so the result is a verdict.
_AUTH_REFUSED = ("AuthenticationException", "NetmikoAuthenticationException",
                 "SSHException", "BadAuthenticationType",
                 "PasswordRequiredException")
_REACHABILITY = ("NetmikoTimeoutException", "NetMikoTimeoutException",
                 "socket.timeout", "TimeoutError", "ConnectionRefusedError",
                 "NoValidConnectionsError", "OSError", "gaierror")

#: Exception names that mean **the device authenticated us and said no**.
#:
#: A strict subset of :data:`_AUTH_REFUSED`, and the difference is the point.
#: ``SSHException`` is in that list because, for the ROTATION, anything after
#: a credential change that stops the session is the alarming case and must
#: count as attempted. But paramiko also raises ``SSHException`` for transport
#: problems — ``no matching key exchange method found`` among them — so it
#: cannot carry a verdict that the device *refused a credential*.
#:
#: Used by a credential CHECK, where the definitive outcome has to be earned:
#: "the device said no" is a claim, and everything not positively identified
#: as an authentication denial is "we did not establish anything".
#:
#: The rotation must NOT use this. Narrowing `attempted` there would suppress
#: a lockout warning for a device that went silent right after its credential
#: changed, which is the case the flag exists for.
AUTH_DENIED = ("NetmikoAuthenticationException", "AuthenticationException",
               "BadAuthenticationType", "PasswordRequiredException")

#: Faults local to this process. `InvalidToken` is the r2 defect itself; the
#: rest are the ways a bug in this module presents. Identified POSITIVELY —
#: the quiet outcome must be earned, not fallen into.
_LOCAL_FAULT = ("InvalidToken", "TypeError", "NameError", "AttributeError",
                "ImportError", "ModuleNotFoundError", "KeyError", "IndexError",
                "ValueError", "UnsendableCommand", "NonPrintableContent")


def classify_failure(name: str) -> dict:
    """Did the DEVICE produce this, or did this process?

    Both lists are positive. An unrecognised name resolves to ``attempted``
    — the alarming side — because the two ways to be wrong are not
    symmetrical: a false lockout warning wastes a console trip, while a false
    "local fault" leaves a possibly-unreachable device without one. The
    fallback is flagged so the message can say it was a fallback.
    """
    if name in _LOCAL_FAULT:
        return {"attempted": False, "recognised": True}
    if name in _AUTH_REFUSED or name in _REACHABILITY:
        return {"attempted": True, "recognised": True}
    return {"attempted": True, "recognised": False}


def enable_secret(device: dict) -> str:
    """The device's enable secret, decrypted — unchanged by this operation.

    Three cases, and the distinction matters because the goal is to be
    *identical* to every other connection in the app, not to be clever:

    - the row has no ``secret`` field at all -> ``None``, which
      :func:`connection_params` turns into "reuse the login password";
    - the field decrypts to an empty string -> ``""`` is returned **as is**,
      which is what ``stored_connection_params()`` passes. Measured on r2:
      this is the real case for this fleet;
    - it decrypts to a value -> that value.

    Every device here has no enable secret configured, so nothing challenges
    it — which is precisely why this has to match the normal path rather than
    be reasoned about.
    """
    from modules.device import decrypt_field

    stored = (device.get("secret") or "").strip()
    if not stored:
        return None
    try:
        return decrypt_field(stored)
    except Exception:                          # noqa: BLE001
        # Already plaintext, or unreadable. Falling back to the login password
        # is what happened before this function existed.
        return None


def verify_new_credential(device: dict, username: str, password: str, *,
                          secret: str = None) -> dict:
    """Log in **again, from scratch**, with a PLAINTEXT credential.

    A fresh TCP session and a fresh authentication. Not the pooled connection
    and not the original session — the original is already authenticated and
    would succeed whatever the device now believes about passwords.

    **The credential here is plaintext and stays plaintext.** The first version
    built a device dict and handed it to ``with_temp_connection()``, which
    Fernet-decrypts ``password``/``secret`` because every other caller passes a
    CSV row. A plaintext password is not a Fernet token, so it raised
    ``InvalidToken`` **before any socket was opened** — and the caller read that
    as "the device refused us". Connecting directly keeps the encrypted-at-rest
    convention where it belongs (the stored inventory) and out of a code path
    whose whole input is a value that has never been stored.

    ``secret`` is the device's **enable** secret, which this operation does
    not touch — it rotates the ``username`` line only. Passing the new login
    password here instead is wrong the moment a device has a separate enable
    secret, and it fails in the worst direction: ``enable()`` raises
    ``ValueError``, which reads as a local fault, so a rotation that actually
    worked would be reverted. No device in the fleet has one today, which is
    exactly why it would have gone unnoticed until one did.

    Returns ``attempted``: whether a connection to the device was actually
    made. Past the connect, it is always ``True`` **by construction** rather
    than by name lookup — we are logged in, so whatever failed next, the
    device answered. ``ok=False, attempted=False`` is **not a verdict about the device** —
    it is a local failure, and treating it as one produced the most alarming
    message this tool can emit from code that never contacted anything.
    """
    from netmiko import ConnectHandler

    from modules.connection import connection_params

    # The SAME builder the pushing session used. If the verify negotiated
    # differently it would fail for a transport reason, be read as a device
    # verdict, and revert a rotation that worked.
    params = connection_params(dict(device, username=username),
                               password=password, secret=secret)
    conn = None
    try:
        # Only THIS may be a local fault. Classified by name, because a name
        # is all there is before a connection exists.
        try:
            conn = ConnectHandler(**params)
        except Exception as exc:              # noqa: BLE001
            name = type(exc).__name__
            verdict = classify_failure(name)
            return {"ok": False, "attempted": verdict["attempted"],
                    "recognised": verdict["recognised"], "error_type": name,
                    "error": f"{name}: {exc}"[:200], "stage": "connect"}

        # Past here we are authenticated, so every failure is the device
        # answering — established by where we are, not by the exception's
        # name. netmiko's enable() raises ValueError, which the name table
        # reads as local; a login that succeeded is not a local fault.
        try:
            conn.enable()
            out = conn.send_command("show running-config | include ^username",
                                    read_timeout=60)
        except Exception as exc:              # noqa: BLE001
            name = type(exc).__name__
            return {"ok": False, "attempted": True, "recognised": True,
                    "error_type": name, "error": f"{name}: {exc}"[:200],
                    "stage": "after_login"}
    finally:
        if conn is not None:
            try:
                conn.disconnect()
            except Exception:                 # noqa: BLE001
                pass
    if not out:
        return {"ok": False, "attempted": True, "recognised": True,
                "error": "logged in but read nothing back",
                "stage": "after_login"}
    return {"ok": True, "attempted": True, "config": out, "stage": "after_login"}


#: Indirection so a retry test does not spend six real seconds sleeping.
_SLEEP = time.sleep


def verify_with_retry(device: dict, username: str, password: str, *,
                      secret: str = None, attempts: int = 3, sleep=None) -> dict:
    """Verify, retrying only while the failure is LOCAL.

    An authentication refusal is a verdict and is returned immediately — there
    is nothing to retry. A local fault is not a verdict, and the held session
    is still open, so it costs nothing to try again rather than act on an
    inconclusive result.
    """
    sleep = sleep or _SLEEP
    last = {"ok": False, "attempted": False, "error": "not run"}
    for attempt in range(attempts):
        last = verify_new_credential(device, username, password,
                                     secret=secret)
        if last["ok"] or last.get("attempted"):
            return {**last, "tries": attempt + 1}
        log.warning("rotate: verify could not run (%s) — retrying %d/%d",
                    last.get("error_type", "?"), attempt + 1, attempts)
        if attempt + 1 < attempts:
            sleep(2 * (attempt + 1))
    return {**last, "tries": attempts}


# ---------------------------------------------------------------------------
# The operation
# ---------------------------------------------------------------------------

def preflight(list_name: str, hostname: str, *, device: dict = None,
              capture: str = "") -> dict:
    """Everything checked before a password is even generated.

    *device* and *capture* exist for the **onboarding** path, and they change
    only WHERE two facts come from — never the ordering below, which is the
    lockout defence.

    A device being onboarded has no `devices.csv` row: that is the pending
    model, and the row is written last, by promotion. So this looked the
    device up in the inventory and refused it, and `golden_config_present`
    checked for a file that onboarding deliberately does not write until
    after the RW community has been removed from the capture.

    Both checks were **proxies**. `device_in_inventory` stands for "we know
    this device's address and username"; `golden_config_present` stands for
    "we know what this device looks like". A caller holding the device dict
    and the capture in hand has better answers to both than the stores do,
    and handing them in is the same correction as every other proxy replaced
    in this stage.

    For an inventory device both arguments are omitted and every check runs
    exactly as before — pinned by a test that rotates one and compares.
    """
    import os

    from modules.config import get_list_data_dir
    from modules.device import get_current_device_list, load_saved_devices
    from modules.nsot import manifest as _m

    repo = os.path.join(get_list_data_dir(list_name), "config_repo")
    out = {"ok": False, "device": hostname, "repo": repo, "checks": []}

    def _check(name, ok, detail=""):
        out["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    helper = helper_status()
    _check("helper_installed_and_matching", helper["ok"],
           helper.get("reason") or f"sha {helper.get('installed_sha','')}")

    if device is None:
        _name, csv_path = get_current_device_list()
        device = next((d for d in load_saved_devices(csv_path)
                       if d.get("hostname") == hostname), None)
        if not _check("device_in_inventory", device is not None,
                      "" if device else f"{hostname} is not in this list"):
            return out
    else:
        # Named differently so a reader of the checks can tell which answer
        # was used. "device_in_inventory: ok" would be false here.
        _check("device_supplied_by_caller", True,
               "onboarding: the device is pending and has no inventory row")
    out["device_row"] = device
    out["mgmt_ip"] = device.get("ip", "")

    identity, entry = _m.find_by_name(repo, hostname)
    _check("identity_in_manifest", bool(identity),
           identity or "no manifest entry")
    out["identity"] = identity or ""

    from modules.inventory import is_stale
    _check("device_not_stale", not is_stale(device.get("ip", ""), list_name))

    config = capture
    if not config:
        path = _m.golden_path_for(repo, entry) if entry else ""
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                config = fh.read()
        out["capture"] = config
        _check("golden_config_present", bool(config))
    else:
        out["capture"] = config
        _check("capture_supplied_by_caller", True,
               "onboarding: the capture is in hand and no golden is written "
               "until the RW community has been removed from it")

    username = device.get("username", "")
    out["username"] = username
    line = current_user_line(config, username)
    out["current_line"] = line
    _check("current_user_line_found", bool(line),
           line and "found" or f"no 'username {username}' line in the capture")

    # THE LIVE READ LIVES HERE, not in plan().
    #
    # `rotate()` calls preflight() itself rather than reusing plan()'s result,
    # so anything computed only in plan() is invisible to the thing that
    # actually sends commands. The program is conditional on the entry kind,
    # which means the kind has to be established where both paths can see it.
    live = live_user_line(device, username)
    out["live_read_ok"] = live["ok"]
    out["live_line"] = live["line"]
    out["entry_kind"] = live["kind"]
    if live["ok"]:
        # Restoring the line the DEVICE has, not the one the golden stored. A
        # revert re-sends this verbatim, and for a switch it is a hash: a
        # stale golden would restore a credential nobody holds.
        out["original_line"] = live["line"]
        if entry_kind(line) != live["kind"]:
            out["discrepancy"] = (
                f"the golden records a '{entry_kind(line) or 'unknown'}' entry, "
                f"the device has a '{live['kind']}' one — the DEVICE decides "
                f"the program, and this device's golden is stale")
        else:
            out["discrepancy"] = ""
    else:
        out["original_line"] = line
        out["discrepancy"] = (
            f"the device could not be read ({live.get('error', '')}) — falling "
            f"back to the two-command form, which is correct in either state")
    _check("live_user_line_read", live["ok"], live.get("error", live["kind"]))

    out["privilege"] = ""
    if line:
        import re
        m = re.search(r"privilege\s+(\d+)", line)
        out["privilege"] = m.group(1) if m else ""
        out["already_hashed"] = bool(
            re.search(r"\bsecret\s+9\s", line))
        _check("not_already_type_9", not out["already_hashed"],
               "already a type-9 secret" if out["already_hashed"] else "")

    out["ok"] = all(c["ok"] for c in out["checks"])
    return out


def live_user_line(device: dict, username: str) -> dict:
    """Read this device's CURRENT ``username`` line, from the device.

    The golden is a stored capture, and the program now depends on whether the
    account holds a secret or a password — a fact about the device now, not
    about the last time it was captured. A stale golden would pick the wrong
    program, and on the password path the wrong program is the one that gets
    silently refused.
    """
    from netmiko import ConnectHandler

    from modules.connection import connection_params
    from modules.device import decrypt_field

    try:
        password = decrypt_field(device.get("password", ""))
    except Exception:                          # noqa: BLE001
        password = device.get("password", "")

    conn = None
    try:
        conn = ConnectHandler(**connection_params(
            device, password=password, secret=enable_secret(device)))
        conn.enable()
        out = conn.send_command(
            f"show running-config | include ^username {username}",
            read_timeout=60) or ""
    except Exception as exc:                   # noqa: BLE001
        return {"ok": False, "line": "", "kind": "",
                "error": f"{type(exc).__name__}: {exc}"[:160]}
    finally:
        if conn is not None:
            try:
                conn.disconnect()
            except Exception:                  # noqa: BLE001
                pass

    for line in out.splitlines():
        if line.strip().startswith(f"username {username}"):
            return {"ok": True, "line": line.strip(),
                    "kind": entry_kind(line.strip())}
    return {"ok": False, "line": "", "kind": "",
            "error": f"no 'username {username}' line on the device"}


def platform_of(list_name: str, hostname: str) -> str:
    """This device's config dialect, from THIS list's inventory.

    Takes the list rather than reading the active one: a function handed a
    list name must not go and ask which list is currently selected. That is
    the same correction as `PipelineContext.list_name` and `_devices_of()`.
    """
    from modules.device import load_saved_devices
    from modules.nsot.platform import platform_for_device

    for device in load_saved_devices(_csv_path_for(list_name)):
        if device.get("hostname") == hostname:
            return platform_for_device(device)
    return ""


def plan(list_name: str, hostname: str) -> dict:
    """What the operator is shown, and the fingerprint they confirm."""
    pre = preflight(list_name, hostname)
    if not pre["ok"]:
        return {"ok": False, "preflight": pre,
                "error": "; ".join(c["detail"] or c["name"]
                                   for c in pre["checks"] if not c["ok"])}

    import hashlib
    # Shown, not bound. It identifies the stored capture the plan was read
    # against, which is useful context; the confirmation binds the username
    # line and the entry kind instead.
    capture_hash = hashlib.sha256(pre["capture"].encode()).hexdigest()[:16]

    # preflight() did the live read; plan only surfaces it.
    kind = pre.get("entry_kind", "")
    disagreement = pre.get("discrepancy", "")

    fingerprint = fingerprint_for(pre)

    return {
        "ok": True, "device": hostname, "mgmt_ip": pre["mgmt_ip"],
        "username": pre["username"], "privilege": pre["privilege"],
        # Carried, not re-derived later. persist()'s applicability check needs
        # it, and a second lookup is a second chance to read a different list.
        "platform": platform_of(list_name, hostname),
        "current_form": _mask_line(pre["current_line"]),
        # The WHOLE program, masked — not just the credential line. The
        # program became two commands when the device turned out to refuse a
        # secret over an existing password entry, and `new_form` kept showing
        # only the second one. An operator would have confirmed a one-line
        # change while the line that DELETES the account went unshown, which
        # is the opposite of "what you confirm is what is sent".
        #
        # Not a fingerprint change: both commands are a pure function of
        # username and privilege, and the fingerprint already binds those.
        "new_program": masked_commands(pre["username"], pre["privilege"], kind),
        "entry_kind": kind,
        "live_read_ok": pre.get("live_read_ok", False),
        "discrepancy": disagreement,
        "new_form": masked_command(pre["username"], pre["privilege"]),
        "capture_hash": capture_hash, "fingerprint": fingerprint,
        "length": LENGTH, "charset_size": len(CHARSET),
        "consumers": consumer_report(hostname, pre["mgmt_ip"]),
        "preflight": pre,
    }


def _mask_line(line: str) -> str:
    from modules import redact
    return redact.redact_positional(line) if line else ""


import os                                    # noqa: E402  (used below)


def consumer_report(hostname: str, mgmt_ip: str) -> list:
    """Who else logs in as this account. See the plan's GAP 1."""
    return [
        {"name": "NMAS", "where": "devices.csv (this device's row)",
         "action": "updated automatically"},
        {"name": "Oxidized", "where": f"router.db row for {mgmt_ip}",
         "action": "updated automatically, then a fetch is confirmed"},
        _yang_push_consumer(mgmt_ip),
    ]


def _yang_push_consumer(mgmt_ip: str) -> dict:
    """Does the NETCONF script's hardcoded credential target THIS device?

    It holds a literal password, so this tool cannot update it — that much was
    always reported. What was not reported is *which* device it points at, and
    that is the difference between a generic caveat and a consequence: the
    script takes a host argument but falls back to a default, and rotating
    that default's credential stops the no-argument invocation working.

    The address is read out of the file rather than written here — partly
    because it can change, and partly because an IPv4 literal in this package
    fails `test_no_ip_literals`.
    """
    import re

    from modules.settings_schema import get_setting

    generic = {"name": "yang-push-sub.py",
               "where": "hardcoded literal (set yang_push_script to check)",
               "action": "NOT updated — may break"}
    path = get_setting("yang_push_script", "")
    if not path or not os.path.exists(path):
        return generic
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return generic

    line_no = next((i for i, line in enumerate(text.splitlines(), 1)
                    if "password" in line and "=" in line), 0)
    default = re.search(r"""HOST\s*=.*?["'](\d{1,3}(?:\.\d{1,3}){3})["']""",
                        text)
    where = f"hardcoded literal, line {line_no or '?'}"
    if default and default.group(1) == mgmt_ip:
        return {"name": "yang-push-sub.py", "where": where,
                "action": "NOT updated — THIS DEVICE IS ITS DEFAULT TARGET; "
                          "running it with no argument will fail after this"}
    return {"name": "yang-push-sub.py", "where": where,
            "action": "NOT updated — its default target is another device"}


def rotate(list_name: str, hostname: str, *, confirmed_fingerprint: str,
           actor: str = "", actor_kind: str = "", device: dict = None,
           capture: str = "", record: str = "csv") -> dict:
    """Rotate one device. Returns one of the five states.

    The ordering is the lockout defence, and every line of it is load-bearing:

    * the **original session stays open** from before the push until after the
      new credential is proven, because it is the only session guaranteed to
      be authenticated whatever the device now believes;
    * the verify runs on a **fresh** connection, because the original would
      succeed regardless;
    * **only** a verify failure reverts. Everything after the commit is
      bookkeeping, and reverting a device to fix bookkeeping destroys a
      completed change.
    """
    import os

    result = {"device": hostname, "state": NOT_STARTED, "steps": [],
              "actor": actor, "actor_kind": actor_kind}

    def _step(name, ok, detail=""):
        result["steps"].append({"name": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    # ---- preflight ------------------------------------------------------
    # `device` / `capture` / `record` change only WHERE two facts come from
    # and where one is written. The ordering below is untouched: it is the
    # lockout defence, and every line of it is load-bearing.
    pre = preflight(list_name, hostname, device=device, capture=capture)
    # CARRIED OUT, ALWAYS. `failed_before_any_change` is the safety property
    # and covers every refusal here; the CHECK that refused is the finding.
    # A caller given only the state knows it stopped and not what to fix.
    result["preflight_checks"] = pre["checks"]
    if not pre["ok"]:
        refused = [c for c in pre["checks"] if not c["ok"]]
        _step("preflight", False,
              "; ".join(f"{c['name']}: {c['detail']}".rstrip(": ")
                        for c in refused))
        result["reason"] = ("preflight refused: "
                            + "; ".join(f"{c['name']}: {c['detail']}".rstrip(": ")
                                        for c in refused))
        return result
    _step("preflight", True)

    # Through `fingerprint_for()`, never a hash built here: two callers
    # computing one hash from one input is a rule that can be broken.
    expected = fingerprint_for(pre)
    if confirmed_fingerprint == SELF_CONFIRMED:
        # RECORDED, not skipped. A caller with no separate plan step has no
        # window between plan and apply, so there is nothing for the
        # comparison to protect — but a check that passes silently because
        # it was not run is what the fingerprint exists to stop, so the
        # result says which of the two happened.
        _step("confirmation", True,
              "self-confirmed: the caller has no separate plan step, so "
              "there is no window between plan and apply to protect")
    elif confirmed_fingerprint != expected:
        _step("confirmation", False, "the device or the plan changed since "
                                     "you confirmed")
        result["reason"] = ("the confirmation does not match this device's "
                            "current state — re-run the plan")
        return result
    else:
        # An `else`, not a trailing call: unconditional, it appended a
        # SECOND confirmation step on the self-confirmed path, so the one
        # result that had to say which branch ran said both.
        _step("confirmation", True)

    device, repo = pre["device_row"], pre["repo"]
    username, privilege = pre["username"], pre["privilege"]
    # The line the DEVICE has, falling back to the golden when it could not be
    # read. This is what a revert re-sends verbatim.
    original_line = pre.get("original_line") or pre["current_line"]

    # ---- generate, then stage BEFORE anything is pushed ------------------
    try:
        password = generate_password(hostname)
    except RotationRefused as exc:
        _step("generate", False, str(exc))
        result["reason"] = str(exc)
        return result
    _step("generate", True, f"{LENGTH} chars")

    stage_plaintext(repo, hostname, password)
    _step("stage", True, "encrypted, before the push")

    # Redaction must know the new value before ANY line mentioning it is
    # written — not at the next cache expiry.
    from modules.redact import invalidate_cache
    invalidate_cache()
    _step("invalidate_redaction_cache", True)

    # The kind the PLAN was confirmed against. The program is a pure function
    # of it, so it is bound into the fingerprint; re-deriving it from the held
    # session below is what stops a device that changed since the confirm from
    # receiving a program nobody saw.
    confirmed_kind = pre.get("entry_kind", "")
    commands = rotation_commands(username, privilege, password, confirmed_kind)
    for masked in masked_commands(username, privilege, confirmed_kind):
        log.info("rotate %s: sending %s", hostname, masked)

    # ---- the original session: opened, proven, and held open -------------
    try:
        session = open_original_session(device)
    except Exception as exc:                   # noqa: BLE001
        _step("original_session", False, f"{type(exc).__name__}: {exc}"[:140])
        clear_staged(repo, hostname)
        result["reason"] = ("could not hold an authenticated session open, so "
                            "there would be no way to revert — refused before "
                            "the push")
        return result
    _step("original_session", True, "open and proven")

    try:
        # ---- the device has the last word on which program is correct ----
        #
        # The plan read the entry kind live, and the operator confirmed a
        # program derived from it. If the device disagrees NOW, the right
        # answer is not to quietly send a different program: it is to stop,
        # because what was confirmed would no longer be what is sent.
        live_now = ""
        try:
            out = session.send_command(
                f"show running-config | include ^username {username}",
                read_timeout=60) or ""
            for line in out.splitlines():
                if line.strip().startswith(f"username {username}"):
                    live_now = entry_kind(line.strip())
                    break
        except Exception as exc:               # noqa: BLE001
            _step("recheck_entry_kind", False, f"{type(exc).__name__}"[:80])
        if live_now and live_now != confirmed_kind:
            _step("recheck_entry_kind", False,
                  f"confirmed against a '{confirmed_kind or 'unknown'}' entry, "
                  f"the device now has a '{live_now}' one")
            clear_staged(repo, hostname)
            result["state"] = NOT_STARTED
            result["reason"] = (
                f"the device's credential entry changed between the plan and "
                f"now ('{confirmed_kind or 'unknown'}' -> '{live_now}'), so the "
                f"program you confirmed is not the program that would be sent "
                f"— re-run the plan")
            return result
        if live_now:
            _step("recheck_entry_kind", True, f"still a '{live_now}' entry")

        # ---- push --------------------------------------------------------
        try:
            push_rotation(session, commands)
        except Exception as exc:               # noqa: BLE001
            _step("push", False, f"{type(exc).__name__}: {exc}"[:160])
            clear_staged(repo, hostname)
            result["reason"] = f"the device rejected the command: {exc}"[:200]
            result["state"] = NOT_STARTED
            return result
        _step("push", True)

        # ---- VERIFY: the only step whose failure reverts ------------------
        #
        # And only a failure the DEVICE produced. A local fault is retried
        # while the session is still open, because acting on an inconclusive
        # result is how a working device gets reverted — or reported lost.
        check = verify_with_retry(device, username, password,
                                  secret=enable_secret(device))
        if not check["ok"]:
            conclusive = check.get("attempted", False)
            _step(VERIFY, False,
                  f"{check.get('error','')}"
                  f"{'' if conclusive else '  [LOCAL FAULT — no connection made]'}")
            result["verify_attempted"] = conclusive
            return _revert(result, _step, session, device, username,
                           original_line, repo, hostname,
                           inconclusive=not conclusive)
        _step(VERIFY, True, f"fresh login with the new credential "
                            f"(tries={check.get('tries', 1)})")

        new_hash = captured_hash(check["config"], username)
        if not new_hash.startswith("9 "):
            _step("captured_type_9", False,
                  f"device stored {new_hash.split()[0] if new_hash else '?'}")
            return _revert(result, _step, session, device, username,
                           original_line, repo, hostname)
        _step("captured_type_9", True)
        # Carried so the persistence chain does not have to re-derive them.
        # Re-deriving the hash from a later capture would read the device
        # again, and the answer that matters is the one the verify saw.
        result["captured_kind"] = "hash"
        result["new_hash"] = new_hash
        result["repo"] = repo
        result["mgmt_ip"] = device.get("ip", "")
        result["username"] = username

        # ---- the POST-ROTATION capture, for the golden -------------------
        #
        # Read here, on the held session, while it is still open. This is a
        # WHOLE config and is deliberately a second read: the verify's read
        # is `show running-config | include ^username`, which is the right
        # command for proving a login and reading back one hash, and
        # catastrophically the wrong thing to store as a golden.
        #
        # It was stored as one. r1 and r2's goldens went from ~330 lines to
        # two — a header and a username line — and the NSoT then recorded
        # those devices as having no interfaces, no routing and no services.
        post_config = capture_running_config(session)
        _step("post_capture", bool(post_config),
              f"{len(post_config.splitlines())} lines" if post_config
              else "read nothing back")
    finally:
        if session is not None:
            try:
                session.disconnect()
            except Exception:                  # noqa: BLE001
                pass

    # ---- from here the rotation HAS HAPPENED -----------------------------
    # An unusable capture must NOT skip the commit. The commit is what writes
    # the credential to devices.csv and the credential store, and returning
    # early here would leave the new password on the device and in the staging
    # file and nowhere else — which is the crash window this whole design
    # exists to keep shut.
    #
    # So commit as normal, but feed save_golden the EXISTING golden content
    # instead of the fragment. Identical content means save_golden writes no
    # change to golden/, while the staged host_vars keep the commit alive, so
    # the intent and the credential still land.
    golden_config, capture_ok = post_config, True
    if not looks_like_a_full_config(post_config):
        capture_ok = False
        # The existing golden, so save_golden sees identical content and
        # writes no change. Empty when the device has no golden yet, which
        # `_commit` reads as "commit the intent, write no golden at all" —
        # a fragment stored as a whole configuration is worse than none.
        golden_config = _current_golden(repo, hostname)
        _step("golden_capture", False,
              f"capture was {len(post_config.splitlines())} lines — not a "
              "config. The golden is LEFT UNCHANGED; the credential is still "
              "recorded. Re-capture this device's golden.")

    commit = _commit(list_name, repo, hostname, device, username, privilege,
                     password, new_hash, golden_config, actor, record=record)
    result["golden_updated"] = capture_ok
    _step("commit", commit["ok"], commit.get("error", commit.get("commit", "")))
    result["commit"] = commit
    result["state"] = ROTATED_PENDING_PERSIST
    result["reason"] = "rotated and committed; persistence not yet verified"
    clear_staged(repo, hostname)
    return result


def _revert(result, _step, session, device, username, original_line, repo,
            hostname, *, inconclusive: bool = False) -> dict:
    """Put the original line back and prove it. Never called after the commit.

    *inconclusive* means the verify could not run rather than the device
    refusing. The revert still happens — the device may be carrying a password
    nothing has recorded, and leaving it there would lock this tool out — but
    the verdict is never dressed up as a device verdict.
    """
    clear_staged(repo, hostname)
    if not original_line:
        _step("revert", False, "no original line was captured")
        result["state"] = REVERT_FAILED
        result["reason"] = "nothing to revert to — recover on the console"
        return result
    # The revert walks into the SAME refusal, mirrored. After a successful
    # push the account holds a secret entry, and the original line sets a
    # password — "Can not have both a user password and a user secret" is
    # symmetric. A one-line revert would be declined, and the failure that the
    # revert exists to recover from would become a real lockout.
    # Conditional for the same reason the push is. After a successful push the
    # account holds a secret; restoring a line that sets a PASSWORD hits the
    # refusal mirrored and needs the deletion first, while restoring a line
    # that sets a secret — every switch, whose original is a pasted
    # `secret 5 $1$…` — does not. Both forms were measured on vIOS-L2.
    try:
        push_rotation(session, revert_commands(username, original_line,
                                               current_kind="secret"))
    except Exception as exc:                   # noqa: BLE001
        _step("revert", False, f"{type(exc).__name__}: {exc}"[:160])
        result["state"] = REVERT_FAILED
        result["reason"] = (f"the revert command failed — recover on the "
                            f"console ({exc})")[:200]
        return result

    from modules.device import decrypt_field
    try:
        old = decrypt_field(device.get("password", ""))
    except Exception:                          # noqa: BLE001
        old = device.get("password", "")

    # Plaintext, like the verify — the inventory's encrypted form was already
    # decrypted above, and handing it back to something that decrypts again is
    # exactly the bug this run found.
    proof = verify_with_retry(device, username, old,
                              secret=enable_secret(device))
    _step("revert_verified", proof["ok"],
          f"{proof.get('error','')}"
          f"{'' if proof.get('attempted') else '  [LOCAL FAULT — no connection made]'}")

    if proof["ok"]:
        result["state"] = REVERTED
        result["reason"] = "the original credential was restored and proven"
    elif proof.get("attempted"):
        # The device was asked, and refused. This is the only path that may
        # claim a lockout.
        result["state"] = REVERT_FAILED
        result["reason"] = ("the device refused the original credential after "
                            "the revert — recover on the console")
        if not proof.get("recognised", True):
            result["reason"] += (
                f" (classified from an UNRECOGNISED error, "
                f"{proof.get('error_type', '?')} — treated as a device verdict "
                f"because that is the safer error)")
    else:
        result["state"] = REVERTED_UNPROVEN
        result["reason"] = ("the original was re-sent, but the proof could not "
                            "run locally — no connection was attempted, so "
                            "this says nothing about the device")
    if inconclusive:
        result["verify_was_inconclusive"] = True
    return result


def _csv_path_for(list_name: str) -> str:
    """This list's devices.csv, by name — not whichever list is active."""
    import os

    from modules.config import get_list_data_dir
    from modules.device import get_current_device_list

    if not list_name:
        return get_current_device_list()[1]
    return os.path.join(get_list_data_dir(list_name), "devices.csv")


def _commit(list_name, repo, hostname, device, username, privilege, password,
            new_hash, post_config, actor, *, record: str = "csv") -> dict:
    """Record the rotation: credential store, devices.csv, golden + intent.

    One commit for the golden capture and the intent change, because the
    device's stored secret and the intent that renders it are the same fact
    about the same moment.

    *record* selects where the working credential is written.

    ``"csv"`` is the inventory device's home and the default — unchanged.

    ``"override"`` is the **device override store, keyed on the management
    IP**: the same place onboarding put the bootstrap value, and the place
    `credentials.resolve()` reads **without a `devices.csv` row**. A device
    being onboarded has no row — promotion writes it, last — so recording to
    the CSV would write into nothing and leave the tool holding a credential
    the device no longer accepts.

    **"The device holds a new password" and "the tool has written that
    password where it can read it" must be atomic.** They are, either way:
    this happens in one place, immediately after the device accepts the
    change. What is NOT part of that unit is promotion, which claims
    something different — that the device is finished and belongs in the
    inventory — and therefore happens later, reading the credential back out
    of the override rather than being handed it down a call chain. No step
    passes a credential to another step, so none can pass an empty one.
    """
    import os

    from modules.credentials import set_template_secret, template_secret_key
    from modules.device import load_saved_devices, write_devices_csv
    from modules.nsot import hostvars
    from modules.nsot.repo import GoldenItem, save_golden

    out = {"ok": False}
    try:
        # 1. The hash the DEVICE produced becomes the template secret.
        ref = f"user_{username}_secret"
        set_template_secret(template_secret_key(list_name, hostname, ref),
                            new_hash, secret_kind="hash", list_name=list_name)
        out["secret_ref"] = ref

        # 2. The new plaintext becomes this device's login credential —
        #    THIS ROW ONLY. A per-device rotation never rewrites a shared
        #    profile: that would change the credential every other device
        #    inherits while only one device actually changed.
        # The list is CARRIED, never re-derived. get_current_device_list()
        # reads the active list off disk, so a list switch between the push
        # and this commit would write the new credential into a different
        # network's inventory — the same defect the pipeline had at three
        # points after its push.
        if record == "override":
            from modules import credentials as _creds

            mgmt_ip = (device or {}).get("ip", "")
            _creds.set_device_override(mgmt_ip, username, password, password)
            out["devices_csv"] = "not written — pending device"
            out["device_override"] = mgmt_ip
        else:
            csv_path = _csv_path_for(list_name)
            rows = load_saved_devices(csv_path)
            from modules.device import fernet
            for row in rows:
                if row.get("hostname") == hostname:
                    row["password"] = fernet.encrypt(password.encode()).decode()
                    row["secret"] = fernet.encrypt(password.encode()).decode()
            write_devices_csv(rows, csv_path)
            out["devices_csv"] = "this row only"

        # 3. Intent: the keyword changes password -> secret, and so does the
        #    ref name, because _h_username derives it from the keyword.
        committed = hostvars.read_committed(repo, hostname) or {}
        for user in committed.get("users") or []:
            if user.get("name") == username:
                user["secret_kind"] = "secret"
                user["secret_ref"] = ref
        refs = [r for r in (committed.get("secret_refs") or [])
                if r != f"user_{username}_password"]
        if ref not in refs:
            refs.append(ref)
        committed["secret_refs"] = sorted(refs)
        hostvars.write_committed(repo, committed)

        # 4. The old plaintext is a dead credential; drop it from the store.
        from modules.credentials import delete_template_secret
        try:
            delete_template_secret(
                template_secret_key(list_name, hostname,
                                    f"user_{username}_password"))
        except Exception:                      # noqa: BLE001
            pass

        # 5. Golden + intent, one commit.
        #
        # `post_config` empty means the capture was unusable AND there was no
        # existing golden to leave in place. Committing a fragment as a
        # device's whole configuration is worse than having no golden, so the
        # golden is skipped and only the intent and credential land — the
        # staged host_vars keep the commit from being empty.
        items = []
        if post_config:
            items.append(GoldenItem(hostname, post_config,
                                    device.get("ip", ""),
                                    netbox_id=device.get("_netbox_id"),
                                    device_uid=device.get("device_uid", "")))
        commit = save_golden(
            list_name, items, source="rotation", actor=actor or "operator",
            message=f"credential: {hostname} rotated to a device-generated "
                    "type-9 secret",
            allow_new=False, extra_paths=["host_vars"])
        out["commit"] = commit.get("commit", "")
        out["ok"] = bool(commit.get("ok"))
        if not commit.get("ok"):
            out["error"] = commit.get("error", "")
    except Exception as exc:                   # noqa: BLE001
        log.exception("rotate %s: commit failed", hostname)
        out["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return out


# ---------------------------------------------------------------------------
# Persistence chain — never reverts the device
# ---------------------------------------------------------------------------

def update_oxidized_row(mgmt_ip: str, username: str, password: str,
                        router_db: str = "") -> dict:
    """One row, through the root-owned helper. The password goes on stdin."""
    import json
    import subprocess

    from modules.settings_schema import get_setting

    router_db = router_db or get_setting("oxidized_router_db",
                                         "/opt/oxidized/router.db")
    status = helper_status()
    if not status["ok"]:
        return {"ok": False, "error": status["reason"],
                "reinstall": status["reinstall"]}
    try:
        proc = subprocess.run(
            ["sudo", "-n", HELPER_INSTALLED, "--file", router_db,
             "--ip", mgmt_ip],
            input=json.dumps({"username": username, "password": password}),
            capture_output=True, text=True, timeout=30)
    except Exception as exc:                   # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:160]}
    try:
        body = json.loads(proc.stdout or "{}")
    except ValueError:
        body = {"ok": False, "error": (proc.stderr or proc.stdout)[:200]}
    return body


def reload_oxidized(*, rest: str = "", timeout: float = 30.0, sleep=None,
                    **_ignored) -> dict:
    """Tell Oxidized to re-read router.db. **GET /reload, and nothing else.**

    Writing the file is not enough on its own: the chain used to do nothing
    between ``update_oxidized_row`` and ``confirm_fetch``, so a fetch could be
    queued against a node list Oxidized had not re-read.

    **What this deliberately does NOT do is restart the container.** An
    earlier version defaulted to ``docker restart oxidized`` on the conclusion
    that ``/reload`` could not refresh a live node's credential. That
    conclusion was drawn from a single incident in which a restart was the
    only thing varied, and it is wrong. Measured directly afterwards, on the
    same installation:

        wrong password written to r2's row, then GET /reload
          -> the very next fetch FAILED

    ``/reload`` picked the change up. It refreshes credentials.

    Restarting would also have been the wrong mechanism even if it worked:
    the app runs as a user in the ``docker`` group, so driving the Docker
    socket is root-equivalent access exercised by a web process, and a
    restart interrupts every other device's fetch on every rotation.

    This stage only establishes that Oxidized accepted the reload and is
    serving its node list again. Whether the credential actually took is not
    asserted here — :func:`confirm_fetch` requires a SUCCESSFUL fetch
    afterwards, which is the real check, and it is a check of the outcome
    rather than of the mechanism.
    """
    import time
    import urllib.request

    from modules.settings_schema import get_setting

    rest = rest or get_setting("oxidized_rest_url", "")
    sleep = sleep or time.sleep
    if not rest:
        return {"ok": False, "mechanism": "rest_reload",
                "error": "oxidized_rest_url is not configured"}

    try:
        urllib.request.urlopen(f"{rest}/reload", timeout=15).read()
    except Exception as exc:                   # noqa: BLE001
        return {"ok": False, "mechanism": "rest_reload",
                "error": f"GET {rest}/reload failed: {type(exc).__name__}"}

    # Serving again? A fetch queued against a reloading Oxidized goes nowhere.
    deadline = time.time() + timeout
    while True:
        try:
            urllib.request.urlopen(f"{rest}/nodes.json", timeout=5).read()
            return {"ok": True, "mechanism": "rest_reload"}
        except Exception:                      # noqa: BLE001
            if time.time() >= deadline:
                return {"ok": False, "mechanism": "rest_reload",
                        "error": f"node list not served within {timeout}s "
                                 f"of the reload"}
            sleep(2)


#: Oxidized reports times as ``'2026-09-21 09:12:44 UTC'`` — measured on the
#: live REST API, not assumed from its docs.
_OXIDIZED_TIME = "%Y-%m-%d %H:%M:%S"


def utc_now():
    """Timezone-AWARE now. Never ``utcnow()``.

    ``datetime.utcnow()`` returns a naive datetime that merely happens to hold
    UTC. Comparing one against an aware datetime raises ``TypeError``; comparing
    it against a naive LOCAL time silently compares two different clocks and
    answers confidently. This chain decides "did a fetch happen after the
    rotation" by exactly such a comparison, so the failure would look like a
    fetch that never arrived rather than like a bug. It is also deprecated from
    Python 3.12.
    """
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def as_utc(value):
    """Parse anything this chain handles into an AWARE UTC datetime.

    Accepts a datetime (naive is *assumed* UTC, which is what every producer
    here means) or one of Oxidized's strings, with or without its ``UTC``
    suffix, with or without ISO ``T``/offset. Returning aware on every path is
    the point: a mixed comparison must be impossible rather than unlikely.
    """
    from datetime import datetime, timezone

    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None \
            else value.astimezone(timezone.utc)

    text = (value or "").strip()
    if not text:
        raise ValueError("empty timestamp")
    text = text.removesuffix(" UTC").strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = datetime.strptime(text, _OXIDIZED_TIME)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None \
        else parsed.astimezone(timezone.utc)


def confirm_fetch(mgmt_ip: str, after_iso: str, *, attempts: int = 6,
                  base_delay: float = 10.0, rest: str = "", sleep=None) -> dict:
    """Require a SUCCESSFUL fetch timestamped after *after_iso*.

    "Requested" and "succeeded" are different events. If the sync runs on
    Oxidized's previous copy, the startup-file check fails for a reason that
    looks nothing like its cause — the file simply lacks the new hash, with no
    sign the harvest never happened.
    """
    import json
    import time
    import urllib.request

    from modules.settings_schema import get_setting

    rest = rest or get_setting("oxidized_rest_url", "")
    if not rest:
        return {"ok": False, "error": "oxidized_rest_url is not configured"}
    sleep = sleep or time.sleep
    want = as_utc(after_iso)
    last = {}
    for attempt in range(attempts):
        try:
            urllib.request.urlopen(f"{rest}/node/next/{mgmt_ip}", timeout=10).read()
        except Exception:                      # noqa: BLE001
            pass
        sleep(base_delay * (2 ** attempt) / 2)
        try:
            raw = urllib.request.urlopen(f"{rest}/nodes.json", timeout=10).read()
            for node in json.loads(raw):
                if node.get("name") != mgmt_ip:
                    continue
                last = node.get("last") or {}
                end = last.get("end") or ""
                if last.get("status") == "success" and end:
                    try:
                        when = as_utc(end)
                    except ValueError:
                        continue
                    if when >= want:
                        return {"ok": True, "end": end,
                                "attempts": attempt + 1}
        except Exception as exc:               # noqa: BLE001
            last = {"error": f"{type(exc).__name__}"}
    # Name the cause when Oxidized knows it. `PromptUndetect` means it
    # authenticated fine and then failed to match its prompt regexp — a
    # known intermittent on this fleet, affecting the switches equally and
    # predating the rotations. It is emphatically NOT a sign that the
    # rotation went wrong, and an operator who cannot tell those apart will
    # go looking at the device instead of re-running the persist-only
    # command, which is all this needs.
    detail = _fetch_failure_detail(rest, mgmt_ip)
    return {"ok": False, "attempts": attempts, "last": last,
            "cause": detail.get("cause", ""),
            "error": detail.get("error", "no successful fetch after the "
                                         "rotation")}


#: Oxidized failure classes worth telling the operator apart. The value is
#: what to DO, because that is the part they need and the part a class name
#: does not carry.
_FETCH_CAUSES = {
    "PromptUndetect": (
        "Oxidized authenticated but could not match its prompt "
        "(Oxidized::PromptUndetect). This is a known intermittent on this "
        "fleet, unrelated to the credential — the rotation itself succeeded. "
        "Re-run the persist-only command; do not investigate the device."),
    "AuthenticationFailed": (
        "Oxidized could not authenticate. That IS credential-related: check "
        "the router.db row for this device before re-running."),
}


def _fetch_failure_detail(rest: str, mgmt_ip: str) -> dict:
    """Ask Oxidized why its last attempt on this device failed."""
    import json
    import urllib.request

    generic = {"cause": "", "error": "no successful fetch after the rotation"}
    if not rest:
        return generic
    try:
        raw = urllib.request.urlopen(f"{rest}/nodes.json", timeout=10).read()
        for node in json.loads(raw):
            if node.get("name") != mgmt_ip:
                continue
            blob = json.dumps(node.get("last") or {})
            for marker, advice in _FETCH_CAUSES.items():
                if marker.lower() in blob.lower():
                    return {"cause": marker,
                            "error": f"no successful fetch after the "
                                     f"rotation — {advice}"}
    except Exception:                          # noqa: BLE001
        return generic
    return generic


def run_sync(script: str = "") -> dict:
    """Run the startup-config sync. No privilege: same user, flock inside."""
    import subprocess

    from modules.settings_schema import get_setting

    script = script or get_setting("clab_sync_script", "")
    if not script:
        return {"ok": False, "error": "clab_sync_script is not configured"}
    try:
        proc = subprocess.run([script], capture_output=True, text=True,
                              timeout=600)
    except Exception as exc:                   # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:160]}
    return {"ok": proc.returncode == 0, "rc": proc.returncode,
            "tail": (proc.stdout or "")[-400:]}


def verify_startup_file(hostname: str, new_hash: str, *, clab: str = "",
                        remote_dir: str = "") -> dict:
    """Does the file that BOOTS the node contain the new hash?

    Reads the clab VM, not the NMAS's local staging copy. Checking the local
    copy would confirm that something was generated, not that it was delivered.
    """
    import shlex
    import subprocess

    from modules.settings_schema import get_setting

    clab = clab or get_setting("clab_host", "")
    remote_dir = remote_dir or get_setting("clab_configs_dir", "labs/lab/configs")
    if not clab:
        return {"ok": False, "error": "clab_host is not configured"}
    token = new_hash.split()[-1] if new_hash else ""
    if not token:
        return {"ok": False, "error": "no hash to look for"}
    remote = f"{remote_dir}/{hostname}.cfg"
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", clab,
           f"grep -c -- {shlex.quote(token)} {shlex.quote(remote)} || true"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as exc:                   # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:160]}
    count = (proc.stdout or "0").strip().splitlines()[-1:] or ["0"]
    try:
        found = int(count[0])
    except ValueError:
        found = 0
    return {"ok": found > 0, "matches": found, "file": f"{clab}:{remote}"}


def _ssh_read(clab: str, command: str, *, timeout: int = 60) -> dict:
    """One read over SSH. Returns the text, or says why it could not."""
    import subprocess

    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", clab, command]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:                   # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:160]}
    if proc.returncode != 0:
        return {"ok": False,
                "error": (proc.stderr or "").strip()[:160] or f"rc={proc.returncode}"}
    return {"ok": True, "text": proc.stdout or ""}


def verify_startup_applies(hostname: str, *, platform: str, username: str,
                           clab: str = "", remote_dir: str = "",
                           launch_patch: str = "") -> dict:
    """Will the startup file put the device in the state it describes?

    The check :func:`verify_startup_file` should always have been. That one
    greps the file for the new hash and passes when it is there -- a
    **presence** check. Stage B measured the gap: all five routers' files
    contained their hash, and not one of them would have applied. The node
    boots, reports healthy, answers SSH, and holds vrnetlab's credential.

    Presence and applicability differ exactly when something else writes to
    the same place first, and that is the case nobody thinks of.

    **This asks the real question rather than encoding a platform rule.** The
    rule would be "a `secret` line is unappliable on a C8000v" -- true when it
    was written, and false the moment the stage-C launch patch is adopted. So
    the check reads the launch script the node actually binds and looks for
    the skip. Adopting the patch satisfies it; replacing the launch script
    with a stock one breaks it again, which is correct both times.

    Returns ``ok`` with a ``reason`` either way. An unreadable file or launch
    script is **not ok**: "I could not tell" is not "it applies", and this
    check exists because something unverifiable was treated as verified.
    """
    from modules.nsot.bootstrap_config import (LAUNCH_SKIP_MARKER,
                                               VRNETLAB_INJECTS_USER)
    from modules.settings_schema import get_setting

    # Asked FIRST, because a platform that injects nothing needs no lab host
    # to answer. Requiring one would make this fail for a reason unrelated to
    # the question -- and a check that fails spuriously gets worked around.
    if platform not in VRNETLAB_INJECTS_USER:
        return {"ok": True, "applies": True,
                "reason": (f"nothing is injected ahead of the startup config on "
                           f"{platform or 'this platform'}; the file's own "
                           f"username line is the only one")}

    clab = clab or get_setting("clab_host", "")
    remote_dir = remote_dir or get_setting("clab_configs_dir", "labs/lab/configs")
    launch_patch = launch_patch or get_setting(
        "clab_launch_patch", "labs/lab/patches/c8000v-launch.py")
    if not clab:
        return {"ok": False, "error": "clab_host is not configured"}

    import shlex

    remote = f"{remote_dir}/{hostname}.cfg"
    read = _ssh_read(clab, f"cat {shlex.quote(remote)}")
    if not read["ok"]:
        return {"ok": False,
                "error": f"could not read {clab}:{remote} -- {read['error']}"}

    entry = ""
    for line in read["text"].splitlines():
        stripped = line.strip()
        if stripped.startswith(f"username {username} "):
            entry = stripped
            break
    if not entry:
        return {"ok": False, "file": f"{clab}:{remote}",
                "error": (f"no `username {username}` line in the startup file. "
                          f"The device would boot with whatever the launch "
                          f"script injects and nothing else.")}

    kind = entry_kind(entry)
    if kind == "password":
        return {"ok": True, "applies": True, "kind": kind,
                "file": f"{clab}:{remote}",
                "reason": ("the password form applies behind the injected "
                           "line; the device ends up with this credential")}

    # A `secret` (or an unreadable form, which we must assume is the worst)
    # lands behind vrnetlab's password line and is refused -- unless the
    # launch script skips its own injection for this user.
    patch = _ssh_read(clab, f"cat {shlex.quote(launch_patch)}")
    if not patch["ok"]:
        return {"ok": False, "unknown": True, "file": f"{clab}:{remote}",
                "launch_patch": f"{clab}:{launch_patch}",
                "error": (f"could not read the launch script {clab}:"
                          f"{launch_patch} -- {patch['error']}. Whether this "
                          f"file applies depends on it, so this is unknown, "
                          f"not fine.")}

    # WHAT WAS READ, named and fingerprinted. A verdict about a remote file
    # that does not say which file, on which host, at which content, is a
    # verdict nobody can check -- and this one is read in a session where the
    # operator has just edited that file.
    import hashlib

    digest = hashlib.sha256(patch["text"].encode("utf-8")).hexdigest()[:12]
    where = f"{clab}:{launch_patch}@{digest}"

    # THE CALL SITE, not the name.
    #
    # This was `if LAUNCH_SKIP_MARKER in patch["text"]` -- a substring search
    # for an identifier, which is a PRESENCE check: the exact defect class
    # this function exists to replace, reproduced one level up inside it.
    # Three ways it passed while the property was false:
    #
    #   * `_skip_users_defined_in_startupX` CONTAINS the marker, so renaming
    #     the helper -- the obvious way to run a negative control -- left the
    #     check passing. Measured on the live host: the routers reported
    #     APPLIES with the marker renamed;
    #   * the helper defined and the call site reverted, so the injection is
    #     not skipped and the file says it is;
    #   * a comment mentioning the name.
    #
    # The property is that the concatenation goes THROUGH the helper: the
    # unpatched form absent, and the helper actually called.
    raw_concat = re.search(
        r"cfg\s*=\s*self\.gen_bootstrap_config\(\)\s*\+\s*startup_cfg",
        patch["text"])
    calls_skip = re.search(r"\b" + re.escape(LAUNCH_SKIP_MARKER) + r"\s*\(",
                           patch["text"])

    if calls_skip and not raw_concat:
        return {"ok": True, "applies": True, "kind": kind or "unknown",
                "file": f"{clab}:{remote}", "launch_patch": where,
                "reason": (f"{where} calls {LAUNCH_SKIP_MARKER}() at the "
                           f"concatenation site and no longer carries the "
                           f"unpatched form, so the `{kind or 'secret'}` "
                           f"form applies")}

    if calls_skip and raw_concat:
        return {"ok": False, "applies": False, "kind": kind or "unknown",
                "file": f"{clab}:{remote}", "launch_patch": where,
                "error": (f"{where} both calls {LAUNCH_SKIP_MARKER}() and "
                          f"still contains the unpatched "
                          f"`cfg = self.gen_bootstrap_config() + startup_cfg`. "
                          f"Half-patched: which one runs decides whether this "
                          f"device boots, and that is not something to guess.")}

    return {"ok": False, "applies": False, "kind": kind or "unknown",
            "file": f"{clab}:{remote}", "launch_patch": where,
            "error": (
                f"the hash is in {remote} and the file WILL NOT APPLY. "
                f"On {platform} the launch script injects `username {username} "
                f"privilege 15 password ...` before this file, and IOS-XE "
                f"refuses a secret for a user that already has a password "
                f"(%CVAC-4-CLI_FAILURE, measured stage B). The node would boot "
                f"healthy on the injected credential and NMAS would be locked "
                f"out. Fix: adopt the user-skip into {launch_patch} (see "
                f"docs/bootstrap-probe/ stage C), or write the password form "
                f"and rotate after boot. Read: {where}")}


def persist(result: dict, *, mgmt_ip: str, username: str, password: str,
            hostname: str, new_hash: str, after_iso: str, platform: str,
            **kw) -> dict:
    """The persistence chain. **Never reverts the device.**

    Entered only once the rotation has happened and been committed, so every
    failure here leaves the state at :data:`ROTATED_UNVERIFIED` — the device is
    rotated, the credential is live and recorded, and only the boot-time copy
    is behind.

    **Every stage is idempotent, and that is a requirement rather than a
    convenience.** This chain's recovery path re-runs it after a partial
    failure, so by construction it meets stages that are already done. A stage
    that treats "already in the intended state" as an error fails precisely
    when the recovery tool is used — which is what happened to r2: its
    router.db row was written on the first attempt, a later stage failed, and
    re-running was refused at the FIRST stage because that row was already
    correct.

    Per stage:

    ``oxidized_row``     the helper reports ``already_current`` and writes
                         nothing when the row already holds the intended
                         credential. Any *other* row differing is still a
                         refusal.
    ``oxidized_reload``  a GET. No state, nothing to repeat wrongly.
    ``fetch_confirmed``  asks for a fresh fetch and requires one that succeeds
                         after *after_iso*. Re-running asks again; a device
                         that is reachable satisfies it every time.
    ``clab_sync``        a harvest into the startup files. Re-running copies
                         the same content.
    ``startup_file``     a grep. Pure read.
    ``startup_applies``  two reads. Pure read.

    ``platform`` has **no default**. It decides whether the last stage can
    pass, and a default would pick one -- which is how a required input stops
    being required. The same correction as ``operation_fingerprint``.
    """
    chain = []
    # Entering the chain is what makes "attempted" true. Any stage failing
    # now leaves ROTATED_UNVERIFIED, which is the state that means attempted
    # and unfinished; reaching the end sets ROTATED_PERSISTED.
    result["state"] = ROTATED_UNVERIFIED

    def _stage(name, outcome):
        chain.append({"name": name, **outcome})
        return outcome.get("ok")

    result["persistence"] = chain
    # Each stage gates the next; every one of them may find its work done.
    if not _stage("oxidized_row",
                  update_oxidized_row(mgmt_ip, username, password,
                                      **{k: kw[k] for k in ("router_db",)
                                         if k in kw})):
        return result
    if not _stage("oxidized_reload",
                  reload_oxidized(**{k: kw[k] for k in ("rest", "sleep")
                                     if k in kw})):
        return result
    if not _stage("fetch_confirmed",
                  confirm_fetch(mgmt_ip, after_iso,
                                **{k: kw[k] for k in ("attempts", "base_delay",
                                                      "rest", "sleep")
                                   if k in kw})):
        return result
    if not _stage("clab_sync",
                  run_sync(**{k: kw[k] for k in ("script",) if k in kw})):
        return result
    if not _stage("startup_file",
                  verify_startup_file(hostname, new_hash,
                                      **{k: kw[k] for k in ("clab", "remote_dir")
                                         if k in kw})):
        return result
    # Presence is not applicability. Stage B measured five routers whose files
    # contained the right hash and would not have applied one of them.
    if not _stage("startup_applies",
                  verify_startup_applies(hostname, platform=platform,
                                         username=username,
                                         **{k: kw[k] for k in
                                            ("clab", "remote_dir", "launch_patch")
                                            if k in kw})):
        return result

    result["state"] = ROTATED_PERSISTED
    result["reason"] = ("rotated, committed, present in the startup config, "
                        "and that file applies on boot")
    return result
