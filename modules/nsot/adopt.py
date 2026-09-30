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
                      open_session, verify, record) -> dict:
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
            CR.clear_staged(repo, hostname)
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
    finally:
        try:
            session.disconnect()
        except Exception:                      # noqa: BLE001
            pass

    # ---- from here the account EXISTS on the device --------------------------
    try:
        record(device["ip"], tool_username, password)
    except Exception as exc:                   # noqa: BLE001
        # The staged copy is the ONLY copy of the new password: keep it (C106,
        # C210's recovery reads it).
        # NOT nmas-rotation-recover: it works from an inventory row, and a
        # device being adopted has none yet, so it would stop and say so.
        import os
        staged_at = os.path.join(repo, CR.STAGING_REL, f"{hostname}.enc")
        result["state"] = ADDED_NOT_RECORDED
        result["staged_at"] = staged_at
        result["reason"] = (f"'{tool_username}' was added and verified on the device, but "
                            f"recording it FAILED: {type(exc).__name__}: {exc}"[:240]
                            + f". The staged copy at {staged_at} is the ONLY copy of that "
                              f"account's password: keep it. The supplied account "
                              f"'{supplied}' still logs in, so the device is reachable")
        _step("record", False, result["reason"])
        return result
    _step("record", True, f"the tool now logs in as '{tool_username}'; the supplied "
                          f"account '{supplied}' is untouched and used by nothing")
    CR.clear_staged(repo, hostname)
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
        CR.clear_staged(repo, hostname)
        result["state"] = REVERTED
        result["reason"] = f"{why}. The added account was removed and read back gone"
        _step("remove_added", True, "removed, and read back gone")
    else:
        result["state"] = REVERT_FAILED
        result["reason"] = (f"{why}. The added account could NOT be proven removed: the "
                            f"device may hold '{tool_username}' with a password only the "
                            "staged copy has (kept for nmas-rotation-recover)")
        _step("remove_added", False, result["reason"])
    return result
