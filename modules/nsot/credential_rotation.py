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

    from modules.connection import FAST_CLI
    from modules.device import decrypt_field

    conn = ConnectHandler(
        device_type=device["device_type"], ip=device["ip"],
        username=device["username"],
        password=decrypt_field(device["password"]),
        secret=decrypt_field(device.get("secret", "") or device["password"]),
        port=22, fast_cli=FAST_CLI)
    conn.enable()
    # Prove it, rather than trusting that connect() succeeding means usable.
    conn.send_command("show clock", read_timeout=30)
    return conn


def push_rotation(session, command: str) -> dict:
    """Send the one line on the ALREADY-AUTHENTICATED original session."""
    from modules.pipeline import IOS_ERROR_PATTERN

    output = session.send_config_set([command], error_pattern=IOS_ERROR_PATTERN)
    return {"ok": True, "output_len": len(output or "")}


def verify_new_credential(device: dict, username: str, password: str) -> dict:
    """Log in **again, from scratch**, with the new credential.

    A fresh TCP session and a fresh authentication. Not the pooled connection
    and not the original session — the original is already authenticated and
    would succeed whatever the device now believes about passwords.
    """
    from modules.connection import with_temp_connection

    probe = dict(device)
    probe["username"] = username
    probe["password"] = password
    probe["secret"] = password
    try:
        out = with_temp_connection(
            probe, lambda c: c.send_command("show running-config | include ^username",
                                            read_timeout=60))
    except Exception as exc:                  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    if not out:
        return {"ok": False, "error": "logged in but read nothing back"}
    return {"ok": True, "config": out}


# ---------------------------------------------------------------------------
# The operation
# ---------------------------------------------------------------------------

def preflight(list_name: str, hostname: str) -> dict:
    """Everything checked before a password is even generated."""
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

    _name, csv_path = get_current_device_list()
    device = next((d for d in load_saved_devices(csv_path)
                   if d.get("hostname") == hostname), None)
    if not _check("device_in_inventory", device is not None,
                  "" if device else f"{hostname} is not in this list"):
        return out
    out["device_row"] = device
    out["mgmt_ip"] = device.get("ip", "")

    identity, entry = _m.find_by_name(repo, hostname)
    _check("identity_in_manifest", bool(identity),
           identity or "no manifest entry")
    out["identity"] = identity or ""

    from modules.inventory import is_stale
    _check("device_not_stale", not is_stale(device.get("ip", ""), list_name))

    config = ""
    path = _m.golden_path_for(repo, entry) if entry else ""
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            config = fh.read()
    out["capture"] = config
    _check("golden_config_present", bool(config))

    username = device.get("username", "")
    out["username"] = username
    line = current_user_line(config, username)
    out["current_line"] = line
    _check("current_user_line_found", bool(line),
           line and "found" or f"no 'username {username}' line in the capture")

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


def plan(list_name: str, hostname: str) -> dict:
    """What the operator is shown, and the fingerprint they confirm."""
    pre = preflight(list_name, hostname)
    if not pre["ok"]:
        return {"ok": False, "preflight": pre,
                "error": "; ".join(c["detail"] or c["name"]
                                   for c in pre["checks"] if not c["ok"])}

    import hashlib
    capture_hash = hashlib.sha256(pre["capture"].encode()).hexdigest()[:16]
    fingerprint = operation_fingerprint(
        device_identity=pre["identity"], username=pre["username"],
        privilege=pre["privilege"], capture_hash=capture_hash)

    return {
        "ok": True, "device": hostname, "mgmt_ip": pre["mgmt_ip"],
        "username": pre["username"], "privilege": pre["privilege"],
        "current_form": _mask_line(pre["current_line"]),
        "new_form": masked_command(pre["username"], pre["privilege"]),
        "capture_hash": capture_hash, "fingerprint": fingerprint,
        "length": LENGTH, "charset_size": len(CHARSET),
        "consumers": consumer_report(hostname, pre["mgmt_ip"]),
        "preflight": pre,
    }


def _mask_line(line: str) -> str:
    from modules import redact
    return redact.redact_positional(line) if line else ""


def consumer_report(hostname: str, mgmt_ip: str) -> list:
    """Who else logs in as this account. See the plan's GAP 1."""
    return [
        {"name": "NMAS", "where": "devices.csv (this device's row)",
         "action": "updated automatically"},
        {"name": "Oxidized", "where": f"router.db row for {mgmt_ip}",
         "action": "updated automatically, then a fetch is confirmed"},
        {"name": "yang-push-sub.py", "where": "hardcoded literal, line 21",
         "action": "NOT updated — reported as broken"},
    ]


def rotate(list_name: str, hostname: str, *, confirmed_fingerprint: str,
           actor: str = "", actor_kind: str = "") -> dict:
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
    pre = preflight(list_name, hostname)
    if not pre["ok"]:
        _step("preflight", False,
              "; ".join(c["name"] for c in pre["checks"] if not c["ok"]))
        result["reason"] = "preflight refused"
        return result
    _step("preflight", True)

    import hashlib
    capture_hash = hashlib.sha256(pre["capture"].encode()).hexdigest()[:16]
    expected = operation_fingerprint(
        device_identity=pre["identity"], username=pre["username"],
        privilege=pre["privilege"], capture_hash=capture_hash)
    if confirmed_fingerprint != expected:
        _step("confirmation", False, "the device or the plan changed since "
                                     "you confirmed")
        result["reason"] = ("the confirmation does not match this device's "
                            "current state — re-run the plan")
        return result
    _step("confirmation", True)

    device, repo = pre["device_row"], pre["repo"]
    username, privilege = pre["username"], pre["privilege"]
    original_line = pre["current_line"]

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

    command = rotation_command(username, privilege, password)
    log.info("rotate %s: sending %s", hostname, masked_command(username, privilege))

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
        # ---- push --------------------------------------------------------
        try:
            push_rotation(session, command)
        except Exception as exc:               # noqa: BLE001
            _step("push", False, f"{type(exc).__name__}: {exc}"[:160])
            clear_staged(repo, hostname)
            result["reason"] = "the device rejected the command"
            result["state"] = NOT_STARTED
            return result
        _step("push", True)

        # ---- VERIFY: the only step whose failure reverts ------------------
        check = verify_new_credential(device, username, password)
        if not check["ok"]:
            _step(VERIFY, False, check.get("error", ""))
            return _revert(result, _step, session, device, username,
                           original_line, repo, hostname)
        _step(VERIFY, True, "fresh login with the new credential")

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
    finally:
        if session is not None:
            try:
                session.disconnect()
            except Exception:                  # noqa: BLE001
                pass

    # ---- from here the rotation HAS HAPPENED -----------------------------
    commit = _commit(list_name, repo, hostname, device, username, privilege,
                     password, new_hash, check["config"], actor)
    _step("commit", commit["ok"], commit.get("error", commit.get("commit", "")))
    result["commit"] = commit
    result["state"] = ROTATED_UNVERIFIED
    result["reason"] = "rotated and committed; persistence not yet verified"
    clear_staged(repo, hostname)
    return result


def _revert(result, _step, session, device, username, original_line, repo,
            hostname) -> dict:
    """Put the original line back and prove it. Never called after the commit."""
    clear_staged(repo, hostname)
    if not original_line:
        _step("revert", False, "no original line was captured")
        result["state"] = REVERT_FAILED
        result["reason"] = "nothing to revert to — recover on the console"
        return result
    try:
        push_rotation(session, original_line)
    except Exception as exc:                   # noqa: BLE001
        _step("revert", False, f"{type(exc).__name__}: {exc}"[:160])
        result["state"] = REVERT_FAILED
        result["reason"] = "the revert command failed — recover on the console"
        return result

    from modules.device import decrypt_field
    try:
        old = decrypt_field(device.get("password", ""))
    except Exception:                          # noqa: BLE001
        old = device.get("password", "")
    proof = verify_new_credential(device, username, old)
    _step("revert_verified", proof["ok"], proof.get("error", ""))
    result["state"] = REVERTED if proof["ok"] else REVERT_FAILED
    result["reason"] = ("the original credential was restored and proven"
                        if proof["ok"] else
                        "the original was re-sent but could not be proven — "
                        "recover on the console")
    return result


def _commit(list_name, repo, hostname, device, username, privilege, password,
            new_hash, post_config, actor) -> dict:
    """Record the rotation: credential store, devices.csv, golden + intent.

    One commit for the golden capture and the intent change, because the
    device's stored secret and the intent that renders it are the same fact
    about the same moment.
    """
    import os

    from modules.credentials import set_template_secret, template_secret_key
    from modules.device import (get_current_device_list, load_saved_devices,
                                write_devices_csv)
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
        _n, csv_path = get_current_device_list()
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
        item = GoldenItem(hostname, post_config, device.get("ip", ""),
                          netbox_id=device.get("_netbox_id"),
                          device_uid=device.get("device_uid", ""))
        commit = save_golden(
            list_name, [item], source="rotation", actor=actor or "operator",
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
    from datetime import datetime

    from modules.settings_schema import get_setting

    rest = rest or get_setting("oxidized_rest_url", "")
    if not rest:
        return {"ok": False, "error": "oxidized_rest_url is not configured"}
    sleep = sleep or time.sleep
    want = datetime.strptime(after_iso, "%Y-%m-%d %H:%M:%S")
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
                end = (last.get("end") or "").replace(" UTC", "")
                if last.get("status") == "success" and end:
                    if datetime.strptime(end, "%Y-%m-%d %H:%M:%S") >= want:
                        return {"ok": True, "end": end, "attempts": attempt + 1}
        except Exception as exc:               # noqa: BLE001
            last = {"error": f"{type(exc).__name__}"}
    return {"ok": False, "attempts": attempts, "last": last,
            "error": "no successful fetch after the rotation"}


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


def persist(result: dict, *, mgmt_ip: str, username: str, password: str,
            hostname: str, new_hash: str, after_iso: str, **kw) -> dict:
    """The persistence chain. **Never reverts the device.**

    Entered only once the rotation has happened and been committed, so every
    failure here leaves the state at :data:`ROTATED_UNVERIFIED` — the device is
    rotated, the credential is live and recorded, and only the boot-time copy
    is behind.
    """
    chain = []

    def _stage(name, outcome):
        chain.append({"name": name, **outcome})
        return outcome.get("ok")

    result["persistence"] = chain
    if not _stage("oxidized_row",
                  update_oxidized_row(mgmt_ip, username, password,
                                      **{k: kw[k] for k in ("router_db",)
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

    result["state"] = ROTATED_PERSISTED
    result["reason"] = "rotated, committed, and present in the startup config"
    return result
