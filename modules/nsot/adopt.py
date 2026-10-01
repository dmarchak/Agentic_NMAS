"""ADOPT: bring a device the tool did not build into management (7.3, brownfield).

Onboarding's phase 2 without phase 1: the person supplies the list, the
address, the platform and the device's CURRENT credential; the tool reaches
the device with it, ADDS an account of its own, and from then on uses only
that. Decided by the operator, 2026-09-29 (NSOT_STAGE7_PLAN.md, "ADOPT, for
brownfield"):

- **ADD an account for the tool; never rotate the supplied one.** A
  brownfield device's account is usually a person's or a team's, and rotating
  it locks them out. Adding one is the deploy's own rule (a deploy may ADD an
  account, never CHANGE one), and it reuses rotation's machinery: the new
  password staged before the push, the push on a held authenticated session,
  a fresh-login verify, the record, and a revert on the held session if the
  verify fails. Only the program differs (one setter line, no deletion), and
  the undo is `no username <tool>`, never a restore of somebody's line.
- **No RW-community removal, and no change beyond the account.**
- **Persist previews running against startup first** (a later step).

This module is built in steps. Step 1 is the account: :func:`add_tool_account`.
"""

import logging
import re

log = logging.getLogger(__name__)

#: The tool's own account on an adopted device. A setting may name another; it
#: must never be the supplied account (that would be a rotation).
TOOL_ACCOUNT_DEFAULT = "nmas"
TOOL_PRIVILEGE = 15
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,31}$")

# States. `NOT_STARTED` is the safety property: nothing reached the device.
NOT_STARTED = "failed_before_any_change"
ADDED = "added_and_recorded"
ADDED_NOT_RECORDED = "added_not_recorded"
REVERTED = "reverted"
REVERT_FAILED = "revert_failed"


def account_lines(config_text: str, username: str) -> list:
    """Every `username <name> ...` line for exactly this account."""
    prefix = f"username {username} "
    return [l.strip() for l in (config_text or "").splitlines()
            if l.strip().startswith(prefix) or l.strip() == f"username {username}"]


_LOCAL = ("local", "local-case")


def _vty_stanzas(vty_text: str) -> list:
    """[{name, login, auth_list, exec_list, ssh}] for each `line vty` stanza."""
    out, cur = [], None
    for raw in (vty_text or "").splitlines():
        line = raw.rstrip()
        if line.startswith("line vty"):
            cur = {"name": line[len("line "):].strip(), "login": "", "auth_list": "",
                   "exec_list": "", "ssh": True}
            out.append(cur)
            continue
        if cur is None or not raw.startswith(" "):
            cur = None if not raw.startswith(" ") else cur
            continue
        s = line.strip()
        if s == "login" or s == "login local" or s == "no login":
            cur["login"] = s
        elif s.startswith("login authentication "):
            cur["auth_list"] = s.split()[-1]
        elif s.startswith("authorization exec "):
            cur["exec_list"] = s.split()[-1]
        elif s.startswith("transport input"):
            words = s.split()[2:]
            cur["ssh"] = "ssh" in words or "all" in words
    return out


def _method_lists(aaa_text: str, kind: str) -> dict:
    """{list name: [methods]} for `aaa authentication login` / `aaa authorization exec`."""
    prefix = {"login": "aaa authentication login ", "exec": "aaa authorization exec "}[kind]
    out = {}
    for raw in (aaa_text or "").splitlines():
        s = raw.strip()
        if s.startswith(prefix):
            words = s[len(prefix):].split()
            if words:
                out[words[0]] = words[1:]
    return out


def local_login_verdict(aaa_text: str, vty_text: str) -> dict:
    """Would a LOCAL account log in over SSH? ``{"ok", "reason", "lines"}``.

    Read from the device's own config before anything is sent, because a
    device authenticating through TACACS+ or RADIUS may never consult a local
    account: the fresh-login verify would then fail (safely, the account is
    removed) with a reason that names nothing (the operator, 2026-09-29). The
    lab uses local accounts; this is the first thing a real network would hit.

    `local` AFTER a server group is refused too: IOS consults the next method
    only when the servers do not ANSWER, so while they answer and reject the
    tool's account, the local one is never tried."""
    stanzas = [s for s in _vty_stanzas(vty_text) if s["ssh"]]
    if not stanzas:
        return {"ok": False, "lines": [], "reason": (
            "no vty line accepts SSH (every `line vty` stanza's `transport input` "
            "excludes it), so the tool has no way in")}
    new_model = any(l.strip() == "aaa new-model" for l in (aaa_text or "").splitlines())
    problems = []
    if not new_model:
        for s in stanzas:
            if s["login"] != "login local":
                problems.append(
                    f"line {s['name']} uses `{s['login'] or 'login (the default)'}`, which "
                    "authenticates against the line password, not local accounts; it would "
                    "take `login local` on that line")
    else:
        logins, execs = _method_lists(aaa_text, "login"), _method_lists(aaa_text, "exec")
        for s in stanzas:
            name = s["auth_list"] or "default"
            methods = logins.get(name)
            if methods is None and name != "default":
                problems.append(f"line {s['name']} names login method list '{name}', which is "
                                "not defined")
            elif methods is not None and (not methods or methods[0] not in _LOCAL):
                shown = " ".join(methods) or "(none)"
                how = ("consults a local account only if the servers do not answer, so it "
                       "would be refused while they do" if any(m in _LOCAL for m in methods)
                       else "never consults a local account")
                problems.append(
                    f"line {s['name']} authenticates with method list '{name}' = {shown}, "
                    f"which {how}; it would take the tool's account on those servers, or a "
                    "list with `local` first on the vty lines the tool uses")
            ename = s["exec_list"] or "default"
            emethods = execs.get(ename)
            if emethods is not None and (not emethods or emethods[0] not in
                                         (*_LOCAL, "if-authenticated", "none")):
                problems.append(
                    f"line {s['name']} authorizes exec with list '{ename}' = "
                    f"{' '.join(emethods) or '(none)'}, which would not grant a local account "
                    "a shell; it would take `local` or `if-authenticated` first")
    if problems:
        return {"ok": False, "lines": problems, "reason": (
            "a local account would not log in over SSH on this device: "
            + "; ".join(problems) + ". Adopt changes no authentication settings, so nothing "
            "was sent")}
    return {"ok": True, "lines": [], "reason": (
        "local accounts log in over SSH ("
        + ("aaa new-model, with local first" if new_model else "login local on every vty line")
        + ")")}


def add_program(tool_username: str, password: str) -> list:
    """The program: ONE setter line for an account the device does not have.
    Rotation's delete-then-set exists for a device that HAS a password entry;
    a new account has none, so the setter alone (measured to be accepted over
    no entry and over a secret) is the whole change."""
    from modules.nsot.credential_rotation import rotation_commands

    return rotation_commands(tool_username, TOOL_PRIVILEGE, password, current_kind="secret")


def masked_program(tool_username: str) -> list:
    from modules.nsot.credential_rotation import masked_commands

    return masked_commands(tool_username, TOOL_PRIVILEGE, "secret")


def add_tool_account(list_name: str, hostname: str, *, mgmt_ip: str, device_type: str,
                     supplied_username: str, supplied_password: str,
                     supplied_enable: str = "", repo: str,
                     tool_username: str = TOOL_ACCOUNT_DEFAULT, actor: str = "",
                     open_session=None, verify=None, record=None) -> dict:
    """Add the tool's account to a device reached with the SUPPLIED credential.

    **The supplied credential is never written** (the operator, 2026-09-29):
    on a brownfield device it is somebody else's login, the tool has no use for
    it once its own account is proven, and if adoption fails its owner still
    holds it, so no copy is needed for recovery. It lives in this call's memory
    only: never staged, never in the credential store or devices.csv, never in
    a result or a log line (a transient redaction value for the call's
    duration, and a scrub of every sentence the result carries). Staging
    belongs to the credential the TOOL generates, whose loss would lock it out.

    Returns ``{"state", "steps", "reason", ...}``; the state is one of the five
    above. The ordering is rotation's lockout defence: the supplied session
    stays open from before the push until the new account is proven on a
    FRESH login, and only a verify failure reverts.

    Collaborators are injected so the ordering and the failure behaviour are
    tested without a device: *open_session(device)*, *verify(device, username,
    password)* and *record(ip, username, password)*.
    """
    from modules import redact
    from modules.device import fernet

    # In memory only, for this call: the shape open_original_session reads.
    device = {"ip": mgmt_ip, "hostname": hostname, "device_type": device_type,
              "username": supplied_username,
              "password": fernet.encrypt((supplied_password or "").encode()).decode(),
              "secret": (fernet.encrypt(supplied_enable.encode()).decode()
                         if supplied_enable else "")}
    with redact.transient_secret(supplied_password, "adopt:supplied"), \
            redact.transient_secret(supplied_enable, "adopt:supplied-enable"):
        out = _add_tool_account(list_name, hostname, device, repo=repo,
                                tool_username=tool_username, actor=actor,
                                open_session=open_session, verify=verify, record=record)
    return _scrub(out, (supplied_password, supplied_enable))


def _scrub(result: dict, values) -> dict:
    """No sentence the result carries holds a supplied value (any length: the
    result is read by a person, not matched against configs)."""
    values = [v for v in values if v]

    def clean(text):
        for v in values:
            text = text.replace(v, "<supplied credential>")
        return text
    result["reason"] = clean(result.get("reason", ""))
    for step in result.get("steps", []):
        step["detail"] = clean(step.get("detail", ""))
    return result


def _add_tool_account(list_name, hostname, device, *, repo, tool_username, actor,
                      open_session, verify, record, convert_owner=None,
                      owner_verify=None) -> dict:
    from modules.nsot import credential_rotation as CR
    from modules.nsot import device_ops

    open_session = open_session or CR.open_original_session
    # The tool's own account is privilege 15 and carries no enable secret: its
    # password is the fallback, as its record says (B14).
    verify = verify or (lambda dev, user, pw: CR.verify_with_retry(dev, user, pw, secret=pw))

    def _record(ip, user, pw):
        from modules import credentials as _creds
        _creds.set_device_override(ip, user, pw, "")

    record = record or _record
    supplied = (device or {}).get("username", "")
    result = {"device": hostname, "list": list_name, "state": NOT_STARTED, "steps": [],
              "tool_account": tool_username, "supplied_account": supplied, "actor": actor,
              "reason": ""}

    def _step(name, ok, detail=""):
        result["steps"].append({"name": name, "ok": bool(ok), "detail": detail})
        device_ops.note(name)
        return bool(ok)

    def _refuse(name, why):
        _step(name, False, why)
        result["reason"] = why
        return result

    # ---- refusals before anything reaches the device ---------------------
    if not _NAME.match(tool_username or ""):
        return _refuse("tool_account", f"'{tool_username}' is not an account name the "
                                       "tool will create")
    if tool_username == supplied:
        return _refuse("tool_account", (
            f"the tool's account and the supplied one are both '{supplied}': adding would "
            "be REPLACING the supplied account's credential, which adopt never does. Name "
            "a different tool account"))
    if not (device or {}).get("ip"):
        return _refuse("tool_account", "no management address")
    _step("tool_account", True, f"'{tool_username}', privilege {TOOL_PRIVILEGE}")

    # ---- the supplied session, opened, proven and held -------------------
    try:
        session = open_session(device)
    except Exception as exc:                   # noqa: BLE001
        return _refuse("supplied_session", (
            f"could not log in with the supplied credential for '{supplied}': "
            f"{type(exc).__name__}: {exc}"[:200]))
    _step("supplied_session", True, f"logged in as '{supplied}' and held open")

    try:
        # Would a local account log in at all? Read before anything is sent.
        try:
            verdict = local_login_verdict(
                session.send_command("show running-config | include ^aaa", read_timeout=60)
                or "",
                session.send_command("show running-config | section ^line vty",
                                     read_timeout=60) or "")
        except Exception as exc:               # noqa: BLE001
            return _refuse("local_login", f"could not read the device's authentication "
                                          f"settings: {type(exc).__name__}: {exc}"[:200])
        if not verdict["ok"]:
            return _refuse("local_login", verdict["reason"])
        _step("local_login", True, verdict["reason"])

        # The device has the last word: an account by this name already
        # there is SOMEBODY's, and adopt changes no account it did not add.
        try:
            present = account_lines(session.send_command(
                f"show running-config | include ^username {tool_username}",
                read_timeout=60) or "", tool_username)
        except Exception as exc:               # noqa: BLE001
            return _refuse("account_absent", f"could not read the device's accounts: "
                                              f"{type(exc).__name__}: {exc}"[:200])
        if present:
            return _refuse("account_absent", (
                f"the device already has an account named '{tool_username}', which the tool "
                "did not create; adopt changes no account it did not add. Name another "
                "tool account, or remove that one by hand if it is a leftover"))
        _step("account_absent", True, f"no '{tool_username}' account on the device")

        # ---- generate, stage BEFORE the push, tell redaction --------------
        password = CR.generate_password(hostname)
        write_sidecar(repo, hostname, device["ip"], device.get("device_type", ""),
                      tool_username)
        CR.stage_plaintext(repo, hostname, password)
        _step("stage", True, "the new password encrypted, before the push")
        from modules.redact import invalidate_cache
        invalidate_cache()

        # ---- push the one setter line -------------------------------------
        for line in masked_program(tool_username):
            log.info("adopt %s: sending %s", hostname, line)
        try:
            CR.push_rotation(session, add_program(tool_username, password))
        except Exception as exc:               # noqa: BLE001
            clear_staged(repo, hostname)
            result["reason"] = f"the device refused the new account: {exc}"[:240]
            _step("push", False, result["reason"])
            return result
        _step("push", True, f"added '{tool_username}'")

        # ---- verify on a FRESH login as the new account --------------------
        check = verify(device, tool_username, password)
        new_hash = CR.captured_hash(check.get("config", ""), tool_username) if check.get("ok") else ""
        if not check.get("ok") or not new_hash.startswith("9 "):
            why = (check.get("error") or "the verify failed") if not check.get("ok") else (
                f"the device stored '{(new_hash or '?').split()[0]}', not a type-9 secret")
            _step("verify", False, why)
            return _remove_added(result, _step, session, tool_username, repo, hostname, why)
        _step("verify", True, f"a fresh login as '{tool_username}' succeeded; the device "
                              "holds a type-9 secret")
        result["new_hash"] = new_hash

        # ---- the owner's account, ONLY when the person chose it ------------
        # After the tool's own account is proven, so the device has a second
        # way in before somebody else's account is touched; on the SAME held
        # session, which stays authenticated while that account is replaced.
        if convert_owner:
            result["owner"] = _convert_owner(session, device, convert_owner,
                                             owner_verify or verify, tool_username, password,
                                             open_session)
    finally:
        try:
            session.disconnect()
        except Exception:                      # noqa: BLE001
            pass

    # ---- from here the account EXISTS on the device --------------------------
    try:
        record(device["ip"], tool_username, password)
    except Exception as exc:                   # noqa: BLE001
        # The staged copy is the ONLY copy of the new password: keep it (C106).
        # Settled by `nmas-adopt-recover`, NOT nmas-rotation-recover: that one
        # works from an inventory row, and a device being adopted has none.
        import os
        staged_at = os.path.join(repo, CR.STAGING_REL, f"{hostname}.enc")
        result["state"] = ADDED_NOT_RECORDED
        result["staged_at"] = staged_at
        result["reason"] = (f"'{tool_username}' was added and verified on the device, but "
                            f"recording it FAILED: {type(exc).__name__}: {exc}"[:240]
                            + f". The staged copy at {staged_at} is the ONLY copy of that "
                              f"account's password: keep it, and settle it with "
                              f"nmas-adopt-recover {hostname} --list {list_name}. The "
                              f"supplied account '{supplied}' still logs in, so the device "
                              f"is reachable")
        _step("record", False, result["reason"])
        return result
    _step("record", True, f"the tool now logs in as '{tool_username}'; the supplied "
                          f"account '{supplied}' is untouched and used by nothing")
    clear_staged(repo, hostname)
    result["state"] = ADDED
    result["reason"] = (f"'{tool_username}' added, verified and recorded; '{supplied}' was "
                        "not changed. Persistence not yet verified")
    return result


def _remove_added(result, _step, session, tool_username, repo, hostname, why) -> dict:
    """Undo an addition whose verify failed: `no username <tool>` on the held
    session, then read the device to prove the account is gone. Never a
    restore of anybody's line: the account did not exist before."""
    from modules.nsot import credential_rotation as CR

    try:
        CR.push_rotation(session, [f"no username {tool_username}"])
        gone = not account_lines(session.send_command(
            f"show running-config | include ^username {tool_username}",
            read_timeout=60) or "", tool_username)
    except Exception as exc:                   # noqa: BLE001
        gone, why = False, f"{why}; the removal raised {type(exc).__name__}: {exc}"
    if gone:
        clear_staged(repo, hostname)
        result["state"] = REVERTED
        result["reason"] = f"{why}. The added account was removed and read back gone"
        _step("remove_added", True, "removed, and read back gone")
    else:
        result["state"] = REVERT_FAILED
        result["reason"] = (f"{why}. The added account could NOT be proven removed: the "
                            f"device may hold '{tool_username}' with a password only the "
                            f"staged copy has (kept: settle it with nmas-adopt-recover "
                            f"{hostname} --list <its list>)")
        _step("remove_added", False, result["reason"])
    return result


#: The owner's account, converted. States, most serious last.
OWNER_CONVERTED = "converted"
OWNER_RESTORED = "conversion_failed_restored"
OWNER_AT_RISK = "owner_account_at_risk"


def _convert_owner(session, device, owner: dict, verify, tool_username: str,
                   tool_password: str, open_session) -> dict:
    """Re-send the owner's account as a SECRET with the SAME password (the
    operator's opt-in, 2026-09-29): the owner keeps logging in with the
    password they know, the device stores a salted hash, and the golden then
    holds that hash like the rest of the fleet.

    Rotation's program, unchanged: a `password` entry cannot take a secret on
    IOS-XE, so it is deleted and set in one round trip (the two-command form,
    measured on IOS-XE 17.06 and vIOS-L2 15.2), on the held session, which IOS
    does not drop when the username goes. Then a FRESH login as the owner
    with the same password, and the stored form read back.

    A failure is the most serious outcome adopt can have, because the account
    is somebody else's: the original line goes back on the held session and is
    proven by a fresh login; if that cannot be proven, once more over a fresh
    session as the tool's own account (proven a moment ago). Only when both
    fail is the owner's account at risk, and the result says so first.
    ``{"state", "detail"}``; never a value."""
    from modules.nsot import credential_rotation as CR

    name, pw = owner["username"], owner["password"]
    program = CR.rotation_commands(name, owner.get("privilege"), pw,
                                   current_kind=owner.get("kind", ""))
    for line in owner_program_masked(owner):
        log.info("adopt: converting the owner's account: %s", line)
    why = ""
    try:
        CR.push_rotation(session, program)
    except Exception as exc:                   # noqa: BLE001
        why = f"the device refused the conversion: {exc}"[:200]
    if not why:
        check = verify(device, name, pw)
        stored = CR.captured_hash(check.get("config", ""), name) if check.get("ok") else ""
        if check.get("ok") and stored.startswith("9 "):
            return {"state": OWNER_CONVERTED, "detail": (
                f"'{name}' re-sent as a secret with the same password; a fresh login as "
                f"'{name}' with it succeeded, and the device holds a type-9 secret")}
        why = (f"a fresh login as '{name}' with its password failed after the conversion "
               f"({check.get('error') or 'refused'})" if not check.get("ok") else
               f"the device stored '{(stored or '?').split()[0]}', not a type-9 secret")

    # ---- put the owner's line back exactly as it was --------------------
    restore = CR.revert_commands(name, owner["line"], current_kind="secret")

    def _restored_by(sess):
        try:
            CR.push_rotation(sess, restore)
        except Exception as exc:               # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"[:160]
        again = verify(device, name, pw)
        return bool(again.get("ok")), again.get("error", "")

    ok, err = _restored_by(session)
    how = "on the held session"
    if not ok:
        try:
            from modules.device import fernet

            tool_dev = dict(device, username=tool_username,
                            password=fernet.encrypt(tool_password.encode()).decode(),
                            secret=fernet.encrypt(tool_password.encode()).decode())
            fresh = (open_session or CR.open_original_session)(tool_dev)
            try:
                ok, err = _restored_by(fresh)
                how = f"over a fresh session as '{tool_username}'"
            finally:
                try:
                    fresh.disconnect()
                except Exception:              # noqa: BLE001
                    pass
        except Exception as exc:               # noqa: BLE001
            err = f"{err}; the tool's own session could not be opened: {exc}"[:240]
    if ok:
        return {"state": OWNER_RESTORED, "detail": (
            f"converting '{name}' failed ({why}); its original line was put back {how} "
            f"and a fresh login with its password succeeded, so '{name}' is as it was")}
    return {"state": OWNER_AT_RISK, "detail": (
        f"DANGER: '{name}', somebody else's account, may not accept its password: the "
        f"conversion failed ({why}) and putting its original line back could not be "
        f"proven ({err or 'the login still failed'}). The tool's own account "
        f"'{tool_username}' logs in and is recorded. Restore '{name}' with its owner, on "
        f"the device's console: its line was `{_form(owner['line'])}`, and the owner "
        "holds the value")}


def owner_program_masked(owner: dict) -> list:
    """The conversion as confirmed: rotation's program with the owner's OWN
    password shown as that, never as generated."""
    from modules.nsot import credential_rotation as CR

    return CR.rotation_commands(owner["username"], owner.get("privilege"),
                                "<its same password>", current_kind=owner.get("kind", ""))


def _form(line: str) -> str:
    """A credential line's FORM, its value replaced (never a second copy)."""
    from modules.nsot.onboard import _credential_form

    return _credential_form(line)


# ---------------------------------------------------------------------------
# The staged copy's sidecar: what recovery needs, never a secret
# ---------------------------------------------------------------------------

#: Beside the staged password, what settling it needs: the address, the driver
#: and the account. A device being adopted has no inventory row, so without
#: this the only copy of a password would be tied to an address nothing
#: records. Gitignored staging, like the password beside it; no secret here.
SIDECAR_REL = ".nsot/staging/adopt"


def _sidecar_path(repo: str, hostname: str) -> str:
    import os

    return os.path.join(repo, SIDECAR_REL, f"{hostname}.json")


def write_sidecar(repo: str, hostname: str, mgmt_ip: str, device_type: str,
                  tool_username: str) -> None:
    import json
    import os
    import time

    from modules.config import open_secure

    os.makedirs(os.path.dirname(_sidecar_path(repo, hostname)), exist_ok=True)
    with open_secure(_sidecar_path(repo, hostname), "w", encoding="utf-8") as fh:
        json.dump({"ip": mgmt_ip, "device_type": device_type, "tool": tool_username,
                   "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, fh)


def read_sidecar(repo: str, hostname: str):
    import json

    try:
        with open(_sidecar_path(repo, hostname), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def clear_staged(repo: str, hostname: str) -> None:
    """The staged password and its sidecar go together, never one alone."""
    import os

    from modules.nsot import credential_rotation as CR

    CR.clear_staged(repo, hostname)
    try:
        os.remove(_sidecar_path(repo, hostname))
    except FileNotFoundError:
        pass


def is_adoption_staged(repo: str, hostname: str) -> bool:
    """Was this staged password staged by an ADOPTION (so its recovery is
    `nmas-adopt-recover`, not the rotation's)?"""
    import os

    return os.path.exists(_sidecar_path(repo, hostname))


# ---------------------------------------------------------------------------
# Step 2: the preview and the apply
# ---------------------------------------------------------------------------

#: The apply's steps, in order. Promotion is LAST, as in onboarding's phase 2:
#: the inventory row is the claim "this device is managed", and it is made
#: only when everything before it held.
#: The monitoring profile (P.9 step c) after the accounts and before the
#: save, so the first golden records it.
APPLY_STEPS = ("confirm", "account", "owner_account", "profile", "persist", "golden", "netbox",
               "promote")

#: What adopt does NOT do, stated at the confirm (a commit records its
#: non-actions; so does a preview).
NOT_DOING = (
    "The supplied account is not changed, rotated or stored: it is used to log in once, "
    "for this operation, and is then used by nothing.",
    "No read-write SNMP community is removed: onboarding removes one only because the "
    "tool put it there, and on this device something real may use it.",
    "Nothing else in the configuration is changed: what is sent is the tool's account and, "
    "where the network has a monitoring profile, the profile's lines the device lacks, each "
    "listed in the program. A value the device sets differently is kept (it overrides the "
    "profile), and nothing is removed.",
    "No intent is committed: seed it from the golden afterwards, on the Device page.",
    "No NetBox object that exists now is made deletable: each is recorded as adopted, and "
    "Remove deletes only what the tool created.",
)

def _read_device(device: dict, tool_username: str) -> dict:
    """READS ONLY, over the supplied credential: the running and startup
    configs, the authentication settings and the tool account's lines."""
    from modules.nsot import credential_rotation as CR
    from modules.nsot.onboard import _read_timeout

    session = CR.open_original_session(device)
    try:
        t = _read_timeout()
        return {"running": session.send_command("show running-config", read_timeout=t) or "",
                "startup": session.send_command("show startup-config", read_timeout=t) or "",
                "aaa": session.send_command("show running-config | include ^aaa",
                                            read_timeout=60) or "",
                "vty": session.send_command("show running-config | section ^line vty",
                                            read_timeout=60) or ""}
    finally:
        try:
            session.disconnect()
        except Exception:                      # noqa: BLE001
            pass


def _netbox_existing(hostname: str) -> dict:
    """What NetBox holds for *hostname* NOW: the device, its interfaces and its
    addresses, by exact name. ``{"ok", "objects": [(endpoint, id, name)],
    "error"}``. A failed read is ``ok: False``, never an empty list."""
    try:
        from modules.netbox_client import (_nb_first, _nb_get, _session_from_config,
                                           get_netbox_config)

        cfg = get_netbox_config()
        if not cfg.get("url") or not cfg.get("token"):
            return {"ok": False, "objects": [], "error": "NetBox is not configured"}
        session, base = _session_from_config(cfg), cfg["url"]
        dev = _nb_first(session, base, "dcim/devices/", name=hostname)
        if dev is None:
            return {"ok": True, "objects": [], "error": ""}
        objects = [("dcim/devices", dev["id"], dev.get("name", hostname))]
        objects += [("dcim/interfaces", i["id"], i.get("name", ""))
                    for i in _nb_get(session, base, "dcim/interfaces/", device_id=dev["id"])]
        objects += [("ipam/ip-addresses", a["id"], a.get("address", ""))
                    for a in _nb_get(session, base, "ipam/ip-addresses/",
                                     device_id=dev["id"])]
        return {"ok": True, "objects": objects, "error": ""}
    except Exception as exc:                   # noqa: BLE001
        return {"ok": False, "objects": [],
                "error": f"NetBox could not be read: {type(exc).__name__}: {exc}"[:240]}


def _netbox_dry_run(list_name: str, hostname: str, mgmt_ip: str, platform: str,
                    config: str, actor: str = "", role: str = "") -> dict:
    """The import's own dry run over the capture being previewed (the one
    place a caller's text is honoured, and only in a dry run)."""
    try:
        from modules.netbox_client import sync_list_to_netbox

        out = sync_list_to_netbox(list_name, [{"hostname": hostname, "ip": mgmt_ip,
                                               "platform": platform, "role": role,
                                               "preview_config": config}], dry_run=True,
                                  actor=actor)
    except Exception as exc:                   # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:240]}
    plan = out.get("plan") or {}
    failed = out.get("failed") or []
    if not out.get("ok") or failed:
        return {"ok": False, "error": (out.get("error") or "; ".join(
            f"{f.get('hostname', '?')}: {f.get('error', '?')}" for f in failed))[:240]}
    return {"ok": True, "error": "", "create_count": plan.get("create_count", 0),
            "update_count": plan.get("update_count", 0),
            "creates_by_type": plan.get("creates_by_type", {}),
            "updates_by_type": plan.get("updates_by_type", {})}


def _hash(text: str) -> str:
    import hashlib

    return hashlib.sha256((text or "").encode()).hexdigest()[:16]


def _masked(lines) -> list:
    """Masked, and a comparison's `section :: line` read as a person reads it:
    a global line alone, a nested one as `section > line`."""
    from modules.redact import redact_text

    return [redact_text(l[4:] if l.startswith(" :: ") else l.replace(" :: ", " > ", 1))
            for l in lines]


def plan(list_name: str, hostname: str, *, mgmt_ip: str, platform: str,
         supplied_username: str, supplied_password: str, supplied_enable: str = "",
         tool_username: str = TOOL_ACCOUNT_DEFAULT, actor: str = "",
         convert_supplied: bool = False, read=None, netbox_existing=None,
         netbox_preview=None, role: str = "") -> dict:
    """Everything the apply would do, what it will not, and each gate.

    *convert_supplied* is the person's opt-in to re-send the SUPPLIED account
    as a secret with the same password; off, adopt changes no account it did
    not add, and a supplied account stored reversibly is refused with the
    opt-in offered (``offer``).

    READS the device with the supplied credential (a preview of a device the
    tool has no record of has nothing else to read) and sends nothing. The
    supplied credential is held for this call only. ``fingerprint`` is set
    only when nothing blocks; the apply recomputes it from the device as it
    is then and refuses when it moved."""
    from modules import redact

    with redact.transient_secret(supplied_password, "adopt:supplied"), \
            redact.transient_secret(supplied_enable, "adopt:supplied-enable"):
        out = _plan(list_name, hostname, mgmt_ip=mgmt_ip, platform=platform,
                    supplied_username=supplied_username, supplied_password=supplied_password,
                    supplied_enable=supplied_enable, tool_username=tool_username, actor=actor,
                    convert_supplied=convert_supplied, read=read,
                    netbox_existing=netbox_existing, netbox_preview=netbox_preview,
                    role=role)
    _scrub_plan(out, (supplied_password, supplied_enable))
    return out


def _scrub_plan(out: dict, values) -> None:
    values = [v for v in values if v]
    for g in out.get("gates", []):
        for v in values:
            g["detail"] = g["detail"].replace(v, "<supplied credential>")
    out["blocking"] = [g["detail"] for g in out.get("gates", []) if g["state"] == "fail"]


def _plan(list_name, hostname, *, mgmt_ip, platform, supplied_username, supplied_password,
          supplied_enable, tool_username, read, netbox_existing, netbox_preview,
          actor="", convert_supplied=False, role="") -> dict:
    import json

    from modules import credentials
    from modules.device import fernet, load_saved_devices
    from modules.netbox_guard import writes_allowed
    from modules.nsot import credential_rotation as CR
    from modules.nsot import manifest as _m
    from modules.nsot import onboard
    from modules.nsot.listref import UnknownList, exists, resolve
    from modules.nsot.roundtrip import configs_equivalent

    out = {"device": hostname, "list": list_name, "mgmt_ip": mgmt_ip, "platform": platform,
           "tool_account": tool_username, "supplied_account": supplied_username,
           "gates": [], "blocking": [], "resume": False, "program": [],
           "not_doing": list(NOT_DOING), "fingerprint": "", "persist": {}, "netbox": {},
           "rw_kept": [], "_capture": ""}

    def gate(name, ok, detail):
        out["gates"].append({"name": name, "state": "pass" if ok else "fail",
                             "detail": detail})
        return ok

    def done():
        out["blocking"] = [g["detail"] for g in out["gates"] if g["state"] == "fail"]
        return out

    # THE ROLE IS ASKED (C225), first among the gates so a missing one is
    # said with every other reason, never guessed from the platform.
    from modules.inventory_edit import role_problem
    role = (role or "").strip().lower()
    out["role"] = role
    problem = role_problem(role, list_name, platform)
    gate("role", not problem, problem or f"recorded as a {role}")

    # ---- what can be refused without the device ---------------------------
    # A WRITE never derives its list (C51): `resolve()` derives an unknown
    # name, which would bring a list into existence by adopting into it.
    try:
        if not exists(list_name):
            raise UnknownList("not registered and not on disk")
        ref = resolve(list_name)
    except UnknownList as exc:
        gate("list", False, f"no device list named {list_name!r} ({exc})")
        return done()
    out["repo"] = ref.repo_dir
    gate("list", True, f"list {ref.name!r}")
    if not _NAME.match(hostname or ""):
        gate("name", False, f"{hostname!r} is not a device name the tool will record")
        return done()
    if not mgmt_ip:
        gate("address", False, "no management address")
        return done()
    try:
        from modules.nsot.platform import netmiko_type_for_dialect

        device_type = netmiko_type_for_dialect(platform)
    except Exception as exc:                   # noqa: BLE001
        gate("platform", False, f"no driver for platform {platform!r}: {exc}")
        return done()
    out["device_type"] = device_type
    gate("platform", True, f"{platform} (driver {device_type})")
    if not _NAME.match(tool_username or "") or tool_username == supplied_username:
        gate("tool_account", False, (
            f"the tool's account must be a valid name that is not the supplied one "
            f"('{supplied_username}'): adding it would otherwise REPLACE the supplied "
            "account's credential, which adopt never does"))
        return done()

    rows = load_saved_devices(ref.csv_path) if _exists(ref.csv_path) else []
    clash = [r for r in rows if (r.get("hostname") or "").lower() == hostname.lower()
             or (r.get("ip") or "") == mgmt_ip]
    gate("not_managed", not clash, (
        f"already in the inventory as {clash[0].get('hostname')} at {clash[0].get('ip')}: "
        "a managed device is not adopted again" if clash else
        f"neither {hostname} nor {mgmt_ip} is in the inventory"))
    _ident, entry = _m.find_by_name(ref.repo_dir, hostname)
    resumable = bool(entry and entry.get("adopted_at") and not entry.get("verified_at")
                     and entry.get("mgmt_ip") == mgmt_ip)
    if entry and not resumable:
        gate("name_free", False, (
            f"{hostname!r} is already in this list's manifest"
            + (" (being onboarded)" if entry.get("onboarded_at") else "")
            + ": one name, one device"))
    else:
        by_ip = _m.find_by_ip(ref.repo_dir, mgmt_ip)[1]
        if by_ip and (by_ip.get("name") or "").lower() != hostname.lower():
            gate("name_free", False, f"{mgmt_ip} is already recorded as {by_ip.get('name')}")
        else:
            gate("name_free", True, "an adoption in progress resumes" if resumable
                 else f"{hostname} is not in this list's manifest")
    if CR.staged_plaintext(ref.repo_dir, hostname) is not None:
        gate("nothing_staged", False, (
            f"a password for the tool's account on {hostname} is staged from an earlier "
            f"run and never settled: nmas-adopt-recover {hostname} --list {ref.name} "
            "first, so its only copy is not lost"))
    if not writes_allowed():
        gate("netbox_writes", False, (
            "NetBox writes are off, and adopting records the device there before it joins "
            "the inventory; enable them in Settings -> Integrations, or nothing is sent"))
    if out["gates"] and any(g["state"] == "fail" for g in out["gates"]):
        return done()

    # ---- the device, read with the supplied credential ---------------------
    device = {"ip": mgmt_ip, "hostname": hostname, "device_type": device_type,
              "username": supplied_username,
              "password": fernet.encrypt((supplied_password or "").encode()).decode(),
              "secret": (fernet.encrypt(supplied_enable.encode()).decode()
                         if supplied_enable else "")}
    out["_device"] = device
    try:
        seen = (read or _read_device)(device, tool_username)
    except Exception as exc:                   # noqa: BLE001
        gate("supplied_login", False, (f"could not log in and read with the supplied "
                                       f"credential for '{supplied_username}': "
                                       f"{type(exc).__name__}: {exc}"[:240]))
        return done()
    running = seen.get("running", "")
    if len(running.splitlines()) < 10:
        gate("supplied_login", False, (f"the running config read was {len(running.splitlines())}"
                                       " lines: a failed read, not a configuration"))
        return done()
    gate("supplied_login", True, f"logged in as '{supplied_username}' and read the device")
    out["_capture"] = running

    named = next((l.split(None, 1)[1].strip() for l in running.splitlines()
                  if l.startswith("hostname ")), "")
    gate("hostname", named.lower() == hostname.lower(), (
        f"the device calls itself {named!r}" + ("" if named.lower() == hostname.lower()
                                                 else f", not {hostname!r}: adopt it under "
                                                      "the name it has")))
    verdict = local_login_verdict(seen.get("aaa", ""), seen.get("vty", ""))
    gate("local_login", verdict["ok"], verdict["reason"])
    cred = _credential_gate(running, supplied_username, supplied_password, supplied_enable,
                            convert_supplied)
    gate("no_reversible_credential", cred["ok"], cred["detail"])
    if cred["offer"]:
        out["offer"] = cred["offer"]
    if cred["convert"]:
        out["_convert"] = cred["convert"]
        out["convert"] = {"account": supplied_username, "sentence": cred["detail"]}

    present = account_lines(running, tool_username)
    held = credentials.resolve(mgmt_ip) if credentials.has_device_override(mgmt_ip) else {}
    ours = bool(held.get("ok")) and held.get("username") == tool_username
    # RESUMED on the tool's OWN record: the account is on the device and the
    # credential store holds it for this address (the adoption's record step
    # wrote it, and nothing else writes the tool's account for an address the
    # inventory lacks). The apply proves it on a fresh login before relying on
    # it. Not on the manifest: the identity is minted at the golden, after the
    # persist a run may have stopped at.
    if present and ours:
        out["resume"] = True
        gate("account", True, (f"'{tool_username}' was added and recorded by an earlier "
                               "adoption: the apply proves it on a fresh login and adds "
                               "nothing"))
    elif present:
        gate("account", False, (f"the device already has an account named '{tool_username}',"
                                " which the tool did not record adding; adopt changes no "
                                "account it did not add. Name another tool account"))
    elif ours:
        gate("account", False, (f"the credential store holds '{tool_username}' for "
                                 f"{mgmt_ip}, and the device has no such account: settle "
                                 "that record before adopting"))
    else:
        out["program"] = masked_program(tool_username)
        gate("account", True, f"'{tool_username}' will be added, privilege {TOOL_PRIVILEGE}")

    # ---- persist: what saving makes the boot config (C184's rule) ----------
    startup = seen.get("startup", "")
    if "startup-config is not present" in startup or not startup.strip():
        out["persist"] = {"state": "no_startup", "only_running": [], "only_startup": [],
                          "sentence": ("the device has NO startup config: saving makes its "
                                       "whole running config, with the tool's account, the "
                                       "configuration it boots")}
    else:
        eq = configs_equivalent(startup, running)
        only_run, only_start = eq.get("only_right", []), eq.get("only_left", [])
        out["persist"] = {
            "state": "same" if eq.get("equal") else "differs",
            "only_running": _masked(only_run), "only_startup": _masked(only_start),
            "sentence": ("the running and startup configs are the same: saving adds only the "
                         "tool's account to what the device boots" if eq.get("equal") else
                         f"saving makes the RUNNING config the boot config: "
                         f"{len(only_run)} line(s) only the running config has become "
                         f"permanent, and {len(only_start)} line(s) only the startup config "
                         "has are gone at the next reload")}
    out["rw_kept"] = _masked(onboard.rw_communities(running))

    # ---- the network's monitoring profile (P.9 step c) --------------------
    # Computed from THIS capture (the device has no intent yet), masked for the
    # preview; the truthful program stays in this module.
    from modules.nsot import profile_apply
    prof = profile_apply.for_capture(ref.name, hostname, platform, role, running,
                                     repo=ref.repo_dir)
    out["profile"] = {k: v for k, v in prof.items() if k != "commands"}
    out["_profile_commands"] = prof["commands"] if prof.get("applies") else []

    # ---- NetBox: what exists (to be recorded as adopted) and what changes ---
    existing = (netbox_existing or _netbox_existing)(hostname)
    if gate("netbox_read", existing.get("ok"), existing.get("error") or (
            f"{len(existing.get('objects') or [])} object(s) exist for {hostname} and will "
            "be recorded as adopted, never as created")):
        out["netbox"]["existing"] = [{"endpoint": ep, "id": i, "name": n}
                                     for ep, i, n in existing["objects"]]
    dry = (netbox_preview or _netbox_dry_run)(list_name, hostname, mgmt_ip, platform, running,
                                              actor=actor or "preview", role=role)
    if gate("netbox_preview", dry.get("ok"), dry.get("error") or (
            f"the import would create {dry.get('create_count', 0)} and update "
            f"{dry.get('update_count', 0)} object(s)")):
        out["netbox"]["dry_run"] = {k: dry.get(k) for k in (
            "create_count", "update_count", "creates_by_type", "updates_by_type")}

    out["capture_hash"], out["startup_hash"] = _hash(running), _hash(startup)
    if not any(g["state"] == "fail" for g in out["gates"]):
        if out.get("_convert"):
            conv = out["_convert"]
            out["program"] = out["program"] + owner_program_masked(conv)
        if out["_profile_commands"]:
            out["program"] = out["program"] + list(out["profile"]["masked"])
        out["fingerprint"] = _hash(json.dumps(
            {"list": ref.name, "device": hostname, "ip": mgmt_ip, "platform": platform,
             "tool": tool_username, "resume": out["resume"], "role": role,
             "convert_owner": bool(out.get("_convert")),
             "profile": (out.get("profile") or {}).get("fingerprint") or "",
             "capture": out["capture_hash"], "startup": out["startup_hash"]},
            sort_keys=True))
    return done()


#: The opt-in's words, the operator's (2026-09-29). Offered only for the
#: SUPPLIED account: it is the one password the tool holds.
CONVERT_LABEL = "Store this account as a secret — same password; the device hashes it"


def reversible_credentials(running: str) -> list:
    """Every LOCAL credential the running config holds in a reversible form:
    ``username <name> ... password 0|7 <value>`` and ``enable password``.
    ``[{"kind": "account"|"enable", "name", "form", "line"}]``. A golden records
    the configuration verbatim and is pushed to its remote, so each of these
    would put a password (type 0) or a reversible encoding of one (type 7)
    there. SNMP communities are the named, accepted exception (the operator,
    2026-09-29) and are not listed."""
    import re

    out = []
    for raw in (running or "").splitlines():
        line = raw.rstrip()
        m = re.match(r"^username (\S+)\b.*?\bpassword\s+(?:(\d+)\s+)?\S+", line)
        if m and " secret " not in f" {line} ":
            out.append({"kind": "account", "name": m.group(1),
                        "form": f"password {m.group(2) or '0'}", "line": line})
            continue
        m = re.match(r"^enable password\s+(?:level\s+\d+\s+)?(?:(\d+)\s+)?\S+", line)
        if m:
            out.append({"kind": "enable", "name": "enable",
                        "form": f"password {m.group(1) or '0'}", "line": line})
    return out


def _convertible(line: str) -> tuple:
    """``(privilege, reason)``: can the owner's line be re-sent as a secret with
    nothing else lost? Only ``username <name> [privilege N] password <t> <v>``:
    the setter carries the privilege and the secret, so any other attribute
    (a view, an autocommand, one-time) would be dropped by the delete. Refused
    by name rather than guessed at."""
    words = line.split()
    rest, privilege = words[2:], None
    if rest[:1] == ["privilege"] and len(rest) >= 2:
        privilege, rest = rest[1], rest[2:]
    if rest[:1] == ["password"] and len(rest) in (2, 3):
        return privilege, ""
    return None, (f"its line carries more than a privilege and a password "
                  f"(`{_form(line)}`), and re-sending it as a secret would drop the rest")


def _credential_gate(running: str, username: str, password: str, enable: str,
                     convert: bool) -> dict:
    """Would the device's first GOLDEN carry a reversible credential?
    ``{"ok", "detail", "convert", "offer"}``.

    * another account's, or an enable password: refused and NAMED (form, never
      value). The tool does not know those passwords, so it cannot store them
      as secrets;
    * the supplied account's, not chosen: refused, and the opt-in OFFERED;
    * the supplied account's, chosen: passes, and ``convert`` carries what the
      apply re-sends (the password, in this call's memory only);
    * the supplied value in clear in any other credential slot: refused.
    Refused, never masked: a golden that is not the device's config is a claim
    about it."""
    import re

    rev = reversible_credentials(running)
    mine = [r for r in rev if r["kind"] == "account" and r["name"] == username]
    theirs = [r for r in rev if r not in mine]
    others = [l for l in (running or "").splitlines()
              if l.rstrip() not in {r["line"] for r in mine}]
    clear = any(v and re.search(rf"\b(?:password|secret)\s+(?:0\s+)?{re.escape(v)}(?:\s|$)",
                                l) for v in (password, enable) for l in others)
    why = ("the golden records the configuration verbatim, in a repository pushed to its "
           "remote, so nothing was sent")
    out = {"ok": False, "detail": "", "convert": None, "offer": None}
    if theirs:
        named = "; ".join(("the enable password" if r["kind"] == "enable"
                           else f"account '{r['name']}'") + f" (`{r['form']}`)" for r in theirs)
        out["detail"] = (f"the device's first golden would carry {len(theirs)} credential(s) "
                         f"in a reversible form: {named}. The tool does not know these "
                         "passwords, so it cannot store them as secrets; they would have to "
                         f"be secrets on the device before it is adopted: {why}")
        return out
    if clear:
        out["detail"] = ("the supplied password appears in clear in another credential line, "
                         f"which the golden would carry: {why}")
        return out
    if mine:
        line = mine[0]["line"]
        if not convert:
            out["offer"] = {"key": "convert_supplied", "label": CONVERT_LABEL,
                            "account": username, "from": mine[0]["form"]}
            out["detail"] = (f"'{username}' is stored as `{mine[0]['form']}`, which the "
                             f"first golden would carry ({why}). Choose \"{CONVERT_LABEL}\" "
                             "to have adopt re-send it with the same password")
            return out
        # EVERY line the account has, not only the reversible one: the delete
        # removes "all username related configurations with same name"
        # (IOS-XE's own prompt, measured on r2), an autocommand line included.
        all_lines = account_lines(running, username)
        privilege, refusal = _convertible(line) if len(all_lines) == 1 else (
            None, f"it has {len(all_lines)} lines, and the delete the conversion needs "
                  "removes them all")
        if refusal:
            out["detail"] = f"'{username}' cannot be stored as a secret: {refusal}"
            return out
        from modules.nsot.credential_rotation import entry_kind

        out["convert"] = {"username": username, "password": password, "line": line,
                          "privilege": privilege, "kind": entry_kind(line)}
        out.update(ok=True, detail=(
            f"'{username}' will be re-sent as a secret with the same password: its owner "
            f"keeps logging in with the password they know, the stored form changes from "
            f"`{mine[0]['form']}` to a salted hash the device makes, and the golden holds "
            "that hash. Proven on a fresh login with the same password; put back as it was "
            "if that fails"))
        return out
    out.update(ok=True, detail=(
        "no local credential is stored in a reversible form, so the golden holds none"
        + ("; nothing to convert" if convert else "")))
    return out


def _exists(path: str) -> bool:
    import os

    return os.path.exists(path)


def public(plan_out: dict) -> dict:
    """The plan without what never leaves this module: the device dict (it
    carries the supplied credential, encrypted) and the raw capture."""
    return {k: v for k, v in plan_out.items() if not k.startswith("_")}


def apply(list_name: str, hostname: str, *, mgmt_ip: str, platform: str,
          supplied_username: str, supplied_password: str, supplied_enable: str = "",
          tool_username: str = TOOL_ACCOUNT_DEFAULT, confirmed_fingerprint: str,
          actor: str, reason: str = "", convert_supplied: bool = False,
          role: str = "", **collab) -> dict:
    """Adopt, holding the device throughout. **`ok` means all of it**, decided
    from the steps; a stop names every step that did not run and why, and a
    re-run RESUMES (an account this adoption added and recorded is proven,
    never added twice). The supplied credential is never written: held in
    this call, redacted from every log line, scrubbed from the result."""
    from modules import redact
    from modules.nsot import device_ops

    try:
        with device_ops.hold(list_name, hostname, "adopt", actor or "unknown",
                             detail="adopt", ip=mgmt_ip), \
                redact.transient_secret(supplied_password, "adopt:supplied"), \
                redact.transient_secret(supplied_enable, "adopt:supplied-enable"):
            out = _apply(list_name, hostname, mgmt_ip=mgmt_ip, platform=platform,
                         supplied_username=supplied_username,
                         supplied_password=supplied_password,
                         supplied_enable=supplied_enable, tool_username=tool_username,
                         confirmed_fingerprint=confirmed_fingerprint, actor=actor,
                         reason=reason, convert_supplied=convert_supplied, **collab, role=role)
    except device_ops.DeviceBusy as exc:
        out = {"ok": False, "device": hostname, "list": list_name, "state": "refused",
               "reason": str(exc), "remaining": [],
               "steps": [{"step": s, "ok": False, "detail": "did not run"}
                         for s in APPLY_STEPS]}
    values = [v for v in (supplied_password, supplied_enable) if v]
    for key in ("reason",):
        for v in values:
            out[key] = (out.get(key) or "").replace(v, "<supplied credential>")
    for row in out.get("steps", []) + out.get("remaining", []):
        for field in ("detail", "why"):
            for v in values:
                if row.get(field):
                    row[field] = row[field].replace(v, "<supplied credential>")
    return out


def _apply(list_name, hostname, *, mgmt_ip, platform, supplied_username, supplied_password,
           supplied_enable, tool_username, confirmed_fingerprint, actor, reason,
           convert_supplied=False, read=None, netbox_existing=None, netbox_preview=None, open_session=None,
           verify=None, record=None, persist=None, capture=None, netbox=None,
           promote=None, record_adoption=None, role="", send_profile=None) -> dict:
    from modules import credentials
    from modules.netbox_guard import get_created, record_adopted
    from modules.nsot import credential_rotation as CR
    from modules.nsot import device_ops
    from modules.nsot import manifest as _m
    from modules.nsot import onboard
    from modules.nsot.repo import GoldenItem, adopt_identity, save_golden

    result = {"ok": False, "device": hostname, "list": list_name, "state": "stopped",
              "steps": [], "remaining": [], "reason": "", "tool_account": tool_username,
              "supplied_account": supplied_username, "actor": actor}

    where = {}

    def _step(name, ok, detail=""):
        result["steps"].append({"step": name, "ok": bool(ok), "detail": detail})
        device_ops.note(name)
        return bool(ok)

    def _finish():
        result["ok"] = (bool(result["steps"]) and all(r["ok"] for r in result["steps"])
                        and len(result["steps"]) == len(APPLY_STEPS))
        repo = where.get("repo")
        if repo:
            rec = onboard.record_run(repo, "adopt", list_name, hostname, actor, result)
            result["run_record"] = {"ok": rec["ok"], "error": rec["error"]}
        return result

    def _stop(name, why):
        log.warning("adopt: %s stopped at %s: %s", hostname, name, why)
        result["reason"] = why
        ran = {r["step"] for r in result["steps"]}
        for s in APPLY_STEPS:
            if s not in ran:
                result["steps"].append({"step": s, "ok": False, "detail": "did not run"})
                result["remaining"].append({"step": s, "why": why})
        return _finish()

    # ---- confirm: the plan again, from the device as it is NOW -------------
    p = _plan(list_name, hostname, mgmt_ip=mgmt_ip, platform=platform,
              supplied_username=supplied_username, supplied_password=supplied_password,
              supplied_enable=supplied_enable, tool_username=tool_username, read=read,
              netbox_existing=netbox_existing, netbox_preview=netbox_preview, actor=actor,
              convert_supplied=convert_supplied, role=role)
    where["repo"] = p.get("repo")
    if p["blocking"]:
        return _stop("confirm", "refused, and nothing was sent: " + "; ".join(p["blocking"]))
    if p["fingerprint"] != confirmed_fingerprint:
        return _stop("confirm", (
            f"the device or the plan moved since the preview (confirmed "
            f"{confirmed_fingerprint or '(none)'}, now {p['fingerprint']}): nothing was "
            "sent. Preview again and confirm what it shows"))
    repo, device, device_type = p["repo"], p["_device"], p["device_type"]
    _step("confirm", True, f"the device is as previewed ({p['fingerprint']})")

    # ---- account ------------------------------------------------------------
    def _tool():
        held = credentials.resolve(mgmt_ip) or {}
        return held.get("username", ""), held.get("password", "")

    # The owner logs in with ITS password, and enables with the supplied enable
    # secret when one was given (a privilege-1 account needs it).
    owner_verify = verify or (lambda dev, u, w: CR.verify_with_retry(
        dev, u, w, secret=supplied_enable or w))
    owner = None
    if p["resume"]:
        user, pw = _tool()
        check = (verify or (lambda dev, u, w: CR.verify_with_retry(dev, u, w, secret=w)))(
            device, user, pw)
        if not _step("account", check.get("ok"), (
                f"'{user}' logs in on a fresh session: added by an earlier run, nothing sent"
                if check.get("ok") else check.get("error") or "the recorded account did "
                "not log in")):
            return _stop("account", (f"the tool's recorded account '{tool_username}' did not "
                                     f"log in: {check.get('error') or 'refused'}"))
    else:
        added = _add_tool_account(list_name, hostname, device, repo=repo,
                                  tool_username=tool_username, actor=actor,
                                  open_session=open_session, verify=verify, record=record,
                                  convert_owner=p.get("_convert"), owner_verify=owner_verify)
        result["account"] = {"state": added["state"], "steps": added["steps"]}
        if added["state"] != ADDED:
            _step("account", False, added["reason"])
            why = added["reason"]
            if added["state"] in (ADDED_NOT_RECORDED, REVERT_FAILED):
                result["recover"] = f"nmas-adopt-recover {hostname} --list {list_name}"
            return _stop("account", why)
        _step("account", True, added["reason"])
        user, pw = _tool()
        owner = added.get("owner")

    # ---- the owner's account: converted only when the person chose it ----
    if p.get("_convert") and p["resume"]:
        # A resumed run has no held session from the account step: open one
        # with the supplied credential, for the conversion alone.
        try:
            held = (open_session or CR.open_original_session)(device)
        except Exception as exc:               # noqa: BLE001
            _step("owner_account", False, f"could not log in as '{supplied_username}': {exc}")
            return _stop("owner_account", "the conversion could not start: nothing was sent")
        try:
            owner = _convert_owner(held, device, p["_convert"], owner_verify, user, pw,
                                   open_session)
        finally:
            try:
                held.disconnect()
            except Exception:                  # noqa: BLE001
                pass
    result["owner_account"] = owner
    if not p.get("_convert"):
        _step("owner_account", True, f"'{supplied_username}' not changed")
    elif not _step("owner_account", owner and owner["state"] == OWNER_CONVERTED,
                   (owner or {}).get("detail", "the conversion did not run")):
        if owner and owner["state"] == OWNER_AT_RISK:
            result["state"] = OWNER_AT_RISK
        return _stop("owner_account", (owner or {}).get("detail", "")
                     + ". Nothing further was done")
    if not (user and pw):
        return _stop("profile", f"the tool's credential for {mgmt_ip} could not be read back "
                                "from the store it was recorded in")

    # ---- the network's monitoring profile (P.9 step c), read back ----------
    prof = p.get("profile") or {}
    if not p.get("_profile_commands"):
        _step("profile", True, "not sent: " + (prof.get("why") or "nothing to send")
              if not prof.get("applies") else prof.get("why") or "already holds every line")
    else:
        sent = (send_profile or onboard.send_profile_program)(
            mgmt_ip, user, pw, pw, device_type, p["_profile_commands"])
        result["profile"] = {"sent": len(p["_profile_commands"]), "error": sent.get("error", "")}
        if not sent.get("ok"):
            _step("profile", False, sent.get("error") or "the profile program failed")
            return _stop("profile", (
                f"the monitoring profile was not applied ({sent.get('error') or 'no reason'}). "
                f"The tool's account is in the RUNNING config only: do not reload the device. "
                "Run adopt again to resume"))
        from modules.nsot import profile_apply
        back = (capture or onboard.capture_config)(mgmt_ip, user, pw, pw, device_type)
        left = ([l for l in profile_apply.for_capture(
                    list_name, hostname, platform, p.get("role", ""), back["config"],
                    repo=repo).get("masked") or [] if l.strip() != "exit"]
                if back.get("ok") else None)
        if left is None or left:
            why = ("the device could not be read back: " + (back.get("error") or "no reason")
                   if left is None else "not every line landed: " + "; ".join(left[:3]))
            _step("profile", False, why)
            return _stop("profile", why + ". Run adopt again to resume")
        _step("profile", True, f"{len(p['_profile_commands'])} line(s) sent and read back")

    # ---- persist, on the device, read back ----------------------------------
    pers = (persist or onboard.persist_on_device)(mgmt_ip, user, pw, pw, device_type)
    result["persist"] = pers
    onboard._record_native_persist(hostname, pers, actor, via="adopt")
    if not _step("persist", pers.get("ok"), pers.get("detail", "")):
        return _stop("persist", (
            f"{pers.get('detail') or 'the save could not be confirmed'}. The tool's account "
            "is in the RUNNING config only: do not reload the device. Run adopt again to "
            "resume; it proves the account and saves again"))

    # ---- golden: the identity, then the device's first record --------------
    cap = (capture or onboard.capture_config)(mgmt_ip, user, pw, pw, device_type)
    if not cap.get("ok"):
        _step("golden", False, cap.get("error", ""))
        return _stop("golden", cap.get("error") or "the device could not be read")
    identity, _entry = _m.find_by_name(repo, hostname)
    if not identity:
        identity = adopt_identity(repo, GoldenItem(hostname, "", mgmt_ip))
    _m.upsert_device(repo, identity, hostname, mgmt_ip=mgmt_ip, platform=platform,
                     adopted=True, role=p.get("role", ""))
    try:
        saved = save_golden(list_name, [GoldenItem(hostname, cap["config"], mgmt_ip=mgmt_ip,
                                                   platform=platform)],
                            source="adopt", actor=actor or "nmas", allow_new=False,
                            message=f"adopt: {hostname} first capture")
    except Exception as exc:                   # noqa: BLE001
        saved = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result["golden"] = saved
    if not _step("golden", saved.get("ok"), saved.get("error") or saved.get("commit", "")):
        return _stop("golden", saved.get("error") or "the golden was not saved")

    # ---- NetBox: what existed is recorded as ADOPTED, before the import ----
    existing = (netbox_existing or _netbox_existing)(hostname)
    if not existing.get("ok"):
        _step("netbox", False, existing.get("error", ""))
        return _stop("netbox", "NetBox could not be read before the import, and what "
                               "existed must be recorded first: " + existing.get("error", ""))
    authority = f"Adopt by {actor or 'unknown'}"
    nb = (netbox or onboard.create_netbox_record)(repo, hostname, list_name, actor=actor,
                                                  authority=authority)
    result["netbox"] = nb
    if not nb.get("ok"):
        _step("netbox", False, nb.get("reason", ""))
        return _stop("netbox", nb.get("reason") or "the NetBox record failed")
    made = {(ep.strip("/"), e.get("id")) for ep, rows in (get_created(list_name) or {}).items()
            for e in rows or []}
    adopted = [o for o in existing["objects"] if (o[0], o[1]) not in made]
    rec = (record_adoption or record_adopted)(
        list_name, hostname, adopted, actor=actor, reason=reason or "adopted into management",
        authority=authority)
    result["adopted"] = [{"endpoint": ep, "id": i, "name": n} for ep, i, n in adopted]
    if not _step("netbox", rec.get("ok"), (
            f"{len(nb.get('created') or [])} created (tagged, recorded as created); "
            f"{len(adopted)} that existed recorded as adopted, never deletable"
            if rec.get("ok") else rec.get("error", ""))):
        return _stop("netbox", ("the import landed and the adoption record could not be "
                                f"written: {rec.get('error')}. Run adopt again: the import "
                                "changes nothing twice and the record is taken again"))
    if nb.get("device_id") is not None:
        _m.upsert_device(repo, identity, hostname, netbox_id=nb["device_id"])

    # ---- promote, LAST --------------------------------------------------------
    prom = (promote or onboard.promote_device)(repo, hostname, list_name, actor=actor,
                                               device_type=device_type, username=user,
                                               password=pw, secret="")
    result["promote"] = prom
    if not _step("promote", prom.get("ok"), prom.get("error", "") or "in the inventory"):
        return _stop("promote", prom.get("error") or "promotion failed")

    result["state"] = "adopted"
    result["reason"] = (f"{hostname} adopted: the tool logs in as '{tool_username}', and "
                        f"'{supplied_username}' was not changed and is used by nothing")
    result["next"] = {"label": (f"Export the break-glass record: it holds no entry for "
                                f"{hostname} until you do"),
                      "open": "breakglass_export", "list": list_name}
    result["then"] = "Seed its intent from the golden, on its Device page"
    return _finish()


# ---------------------------------------------------------------------------
# Recovery: a tool password an adoption staged and never settled
# ---------------------------------------------------------------------------

NOTHING_STAGED = "nothing_staged"
RECOVERED = "recovered"
STAGED_REFUSED = "staged_refused"
RECOVERY_INCONCLUSIVE = "inconclusive"


def recover_tool_account(list_name: str, hostname: str, *, actor: str,
                         verify=None, record=None) -> dict:
    """Settle a password an adoption staged, by ASKING the device (C210's
    rule, for a device with no inventory row: the sidecar holds its address).

    * accepted on a fresh login: the device holds it. Record it; clear the
      staged file only once the record is written;
    * refused: the account is absent or holds another password. The file is
      KEPT, and the result says what a person checks, since only they hold a
      login that can look;
    * the device could not be asked: nothing changes.

    Holds the device (C98). Never prints or returns a credential."""
    from modules import credentials
    from modules.nsot import credential_rotation as CR
    from modules.nsot import device_ops
    from modules.nsot.listref import UnknownList, exists, resolve

    out = {"device": hostname, "list": list_name, "state": NOTHING_STAGED, "reason": ""}
    try:
        if not exists(list_name):
            raise UnknownList("not registered and not on disk")
        ref = resolve(list_name)
    except UnknownList as exc:
        out.update(state=RECOVERY_INCONCLUSIVE, reason=f"no device list named {list_name!r} "
                                                       f"({exc})")
        return out
    staged = CR.staged_plaintext(ref.repo_dir, hostname)
    if staged is None:
        out["reason"] = f"no tool password is staged for {hostname}: nothing to recover"
        return out
    side = read_sidecar(ref.repo_dir, hostname)
    if not side or not side.get("ip"):
        out.update(state=RECOVERY_INCONCLUSIVE, reason=(
            f"a password is staged for {hostname} and nothing records the address it "
            "belongs to (not an adoption's, or its sidecar is gone): the file is kept"))
        return out
    tool = side.get("tool") or TOOL_ACCOUNT_DEFAULT
    dev = {"ip": side["ip"], "hostname": hostname, "device_type": side.get("device_type", "")}
    verify = verify or (lambda d, u, w: CR.verify_with_retry(d, u, w, secret=w))
    record = record or (lambda ip, u, w: credentials.set_device_override(ip, u, w, ""))
    try:
        with device_ops.hold(list_name, hostname, "recover", actor or "unknown",
                             ip=side["ip"]):
            check = verify(dev, tool, staged)
            if check.get("ok"):
                try:
                    record(side["ip"], tool, staged)
                except Exception as exc:       # noqa: BLE001
                    out.update(state=RECOVERY_INCONCLUSIVE, reason=(
                        f"the device accepts the staged password for '{tool}', and "
                        f"recording it FAILED ({type(exc).__name__}): the staged file is "
                        "kept, and is the only copy"))
                    return out
                clear_staged(ref.repo_dir, hostname)
                out.update(state=RECOVERED, reason=(
                    f"the device accepts the staged password for '{tool}': it is recorded, "
                    "and the staged file cleared. Run adopt again to finish; it proves the "
                    "account and adds nothing"))
            elif not check.get("attempted", True):
                out.update(state=RECOVERY_INCONCLUSIVE, reason=(
                    f"the device could not be asked ({check.get('error', 'no reason')}): "
                    "nothing was changed and the staged file is kept"))
            else:
                out.update(state=STAGED_REFUSED, reason=(
                    f"the device refuses the staged password for '{tool}': the account is "
                    "absent or holds another password. The staged file is kept. With a login "
                    f"of your own, check `show running-config | include ^username {tool}`: "
                    "if there is no such account, the adoption never added one and the "
                    "staged file can be deleted"))
    except device_ops.DeviceBusy as exc:
        out.update(state=RECOVERY_INCONCLUSIVE,
                   reason=f"{exc}; nothing was asked and the staged file is kept")
    return out
