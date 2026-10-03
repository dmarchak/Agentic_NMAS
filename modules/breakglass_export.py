"""The break-glass export from the BROWSER (7.3, the operator, 2026-09-29).

The record is built and sealed IN MEMORY, verified by opening the finished
bytes with the passphrase, recorded, and handed to the browser. It never
touches the host's disk, so there is no staging file and no cleanup to get
wrong: the day's first export was lost exactly there, a copy command meant
for the laptop ran on the host and deleted the file before it was copied.

Kept apart from `modules/breakglass.py` on purpose: that module is the
record's format, deliberately dumb and independent of the application's
stores and key file (so a record opens during an outage without them). This
one READS those stores to build a record, as `scripts/nmas-breakglass
export` does; the CLI and the browser call these same functions.
"""

import hashlib
import json
import logging
import os
import time

from modules.breakglass import (MIN_PASSPHRASE, BreakglassError, build_payload,
                                check_key_opens, compare, describe, digests_of, escrowed_key,
                                key_fingerprint, live_ciphertexts, record_check, record_export,
                                seal, unseal)

log = logging.getLogger(__name__)


def list_devices(list_name: str) -> list:
    """This list's rows, decrypted, in the payload's shape. Never the active
    list: the list is named by the caller and carried. The CLI and the browser
    export both call this."""
    from modules.config import get_list_data_dir
    from modules.device import decrypt_field, load_saved_devices
    from modules.nsot.platform import platform_for_device

    path = os.path.join(get_list_data_dir(list_name), "devices.csv")
    rows, unopened = [], []
    for device in load_saved_devices(path):
        try:
            password = decrypt_field(device.get("password", ""))
            secret = decrypt_field(device.get("secret", ""))
        except Exception as exc:                    # noqa: BLE001 (InvalidToken, a bad field)
            # Named, never a crash (C384): a record built now would not recover this device.
            unopened.append(f"{device.get('hostname') or '(no name)'} ({type(exc).__name__})")
            continue
        rows.append({
            "hostname": device.get("hostname", ""),
            "ip": device.get("ip", ""),
            "username": device.get("username", ""),
            "password": password,
            "secret": secret,
            "platform": platform_for_device(device),
            "list_name": list_name,
            "container": device.get("container", ""),
        })
    if unopened:
        raise BreakglassError(
            "the stored credential of " + ", ".join(unopened) + " could not be opened with the "
            "application key, so a record built now would not recover "
            + ("it" if len(unopened) == 1 else "them") + ": fix the stored credential first")
    return rows


def live_key(data_dir: str = "") -> bytes:
    """The key file's bytes, or b"" -- READ ONLY. Deliberately not
    `device.load_key()` or `secrets_store`, both of which CREATE a key when
    none exists, and an export that generated the key it escrows would
    escrow a key nothing was encrypted with."""
    from modules.config import KEY_FILE

    path = os.path.join(data_dir, os.path.basename(KEY_FILE)) if data_dir else KEY_FILE
    try:
        with open(path, "rb") as handle:
            return handle.read().strip()
    except OSError:
        return b""


def live_stores(data_dir: str = "") -> dict:
    from modules.config import DATA_DIR
    from modules.secrets_store import _PREFIX

    return live_ciphertexts(data_dir or DATA_DIR, _PREFIX)


def export_plan(list_name: str) -> dict:
    """What an export of *list_name* would hold, and whether it can be made.
    Reveals NOTHING: device names, which have a password, the key's
    fingerprint and verdict, and a hash of the credentials held now, which the
    confirm binds (a rotation between preview and export refuses)."""
    refusals = []
    try:
        devices = list_devices(list_name)
    except BreakglassError as exc:
        devices, refusals = [], [str(exc)]
    key = live_key()
    check = check_key_opens(key, live_stores()) if key else {"verdict": "no_key", "opened": 0,
                                                            "total": 0}
    digests = digests_of(devices)
    if not devices and not refusals:
        refusals.append(f"{list_name} has no devices: there is nothing to recover")
    if not key:
        refusals.append("the application key could not be read, so it cannot be escrowed")
    return {"list_name": list_name,
            "devices": [{"hostname": d["hostname"], "ip": d["ip"], "platform": d["platform"],
                         "has_password": bool(d["password"]),
                         "has_enable_secret": bool(d["secret"]) and d["secret"] != d["password"]}
                        for d in devices],
            "key_fingerprint": key_fingerprint(key) if key else "",
            "key_check": {k: check.get(k) for k in ("verdict", "opened", "total")},
            "refusals": refusals, "ok": not refusals,
            "hash": hashlib.sha256(json.dumps({"list": list_name, "digests": digests,
                                               "key": key_fingerprint(key) if key else ""},
                                              sort_keys=True).encode()).hexdigest()[:16]}


def _scrub(text: str, passphrase: str) -> str:
    """An error string with the passphrase removed, whatever produced it."""
    text = str(text)
    return text.replace(passphrase, "<passphrase>") if passphrase else text


def export_in_memory(list_name: str, passphrase: str, confirm: str, confirmed: str,
                     *, actor: str, record_reveal) -> dict:
    """Build, seal, VERIFY and record an export, entirely in memory.

    ``{ok, blob, sha256, filename, verified, plan}`` or ``{ok: False, error,
    stage}``. The passphrase is checked (the two entries equal, the minimum
    length) BEFORE anything is built; the plan is recomputed and must hash to
    the confirmed one; the sealed bytes are then OPENED with the passphrase
    and every device, every credential (by digest) and the escrowed key are
    checked against what was put in, and the key must open what the live key
    opens; only then is the reveal recorded (*record_reveal(sha256, count)*
    must return True, or nothing is sent: the most sensitive action in the
    tool does not happen unrecorded) and the export logged. No step writes
    the file anywhere; the passphrase appears in no error, log or record."""
    def refused(stage, why):
        return {"ok": False, "stage": stage, "error": _scrub(why, passphrase)}

    if passphrase != confirm:
        return refused("passphrase", "the two passphrases do not match. Nothing was built.")
    if len(passphrase or "") < MIN_PASSPHRASE:
        return refused("passphrase", (
            f"the passphrase is shorter than {MIN_PASSPHRASE} characters. Nothing was built: "
            "the file is an offline target, and a short passphrase can be guessed at leisure "
            "whatever else protects it."))
    try:
        plan = export_plan(list_name)
        if not plan["ok"]:
            return refused("plan", "; ".join(plan["refusals"]) + ". Nothing was built.")
        if plan["hash"] != confirmed:
            return refused("plan", (
                f"the credentials or the key changed since the preview ({confirmed} -> "
                f"{plan['hash']}), a rotation most likely. Nothing was built; preview again."))
        devices = list_devices(list_name)
        key = live_key()
        payload = build_payload(devices, list_name=list_name, fernet_key=key)
        blob = seal(payload, passphrase)
        payload = None

        # VERIFY, from the finished bytes, as the laptop's `verify` would.
        opened = unseal(blob, passphrase)
        described = describe(opened)
        problems = []
        if digests_of(opened.get("devices") or []) != digests_of(devices):
            problems.append("the record's credentials are not the ones put in")
        missing = [r["hostname"] for r in described["devices"] if not r["has_password"]]
        wanted = {d["hostname"] for d in devices if d["password"]}
        if set(missing) & wanted:
            problems.append("a device lost its password in the record: "
                            + ", ".join(sorted(set(missing) & wanted)))
        if described["key_fingerprint"] != key_fingerprint(key):
            problems.append("the escrowed key is not the application key")
        escrow_check = check_key_opens(escrowed_key(opened), live_stores())
        if escrow_check["opened"] != plan["key_check"]["opened"]:
            problems.append(f"the escrowed key opens {escrow_check['opened']} stored value(s), "
                            f"the application key {plan['key_check']['opened']}")
        opened = None
        if problems:
            return refused("verify", "the finished record did not verify: " + "; ".join(problems)
                           + ". Nothing was sent.")
    except BreakglassError as exc:
        return refused("build", f"{exc}. Nothing was sent.")
    except Exception as exc:                        # noqa: BLE001
        log.error("breakglass: the browser export failed (%s)", type(exc).__name__)
        return refused("build", f"the export failed ({type(exc).__name__}). Nothing was sent.")

    sha = hashlib.sha256(blob).hexdigest()
    if not record_reveal(sha, len(devices)):
        return refused("record", "the reveal could not be recorded, so nothing was sent: this "
                                 "action is never unrecorded")
    at = time.time()
    when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at))
    filename = ("nmas-breakglass-" + "".join(c if c.isalnum() or c in "-_." else "_"
                                             for c in list_name)
                + time.strftime("-%Y%m%dT%H%M%SZ.bg", time.gmtime(at)))
    logged = True
    try:
        from modules.config import DATA_DIR
        # The name the download is GIVEN, recorded: the host never sees what it is called where
        # it is kept, so the drill card shows this labelled, never as the file to open (C387).
        record_export(DATA_DIR, list_name=list_name, devices=devices,
                      path=f"downloaded by {actor} at {when}", key_fingerprint=key_fingerprint(key),
                      actor=actor, at=at, via="browser", sha256=sha, filename=filename)
    except OSError as exc:
        logged = False
        log.error("breakglass: the browser export was not logged (%s)", exc)
    return {"ok": True, "blob": blob, "sha256": sha, "at": when, "logged": logged,
            "filename": filename,
            "verified": {"devices": len(devices), "key_fingerprint": key_fingerprint(key),
                         "key_opens": f"{escrow_check['opened']} of {escrow_check['total']}"},
            "plan": plan}


#: A sealed record of a list is a few kilobytes; anything larger is not one.
MAX_CHECK_BYTES = 2 * 1024 * 1024


def check_file(list_name: str, blob: bytes, passphrase: str, *, actor: str) -> dict:
    """"Check a break-glass file" (board 7, C): open a kept file IN MEMORY with its passphrase
    and say, per device and for the key, whether it holds what is in use now. Compared by
    digest; no value leaves this function, and the opened payload is dropped before it returns.
    Recorded: who, when, the file's sha256 and the verdict (`breakglass.record_check`).

    ``{ok, sha256, created, file_list, devices: [{device, state}], key, counts}`` or
    ``{ok: False, stage, error}``; the passphrase appears in no error."""
    def refused(stage, why):
        return {"ok": False, "stage": stage, "error": _scrub(why, passphrase)}

    if not blob:
        return refused("file", "no file was chosen. Nothing was opened.")
    if len(blob) > MAX_CHECK_BYTES:
        return refused("file", f"the file is {len(blob)} bytes, more than a break-glass record "
                                f"({MAX_CHECK_BYTES} at most). Nothing was opened.")
    sha = hashlib.sha256(blob).hexdigest()
    try:
        payload = unseal(blob, passphrase)
    except BreakglassError as exc:
        return refused("open", f"{exc} Nothing was compared.")
    try:
        created = str(payload.get("created", ""))
        file_list = str(payload.get("list_name", ""))
        if file_list and file_list != list_name:
            return refused("list", f"this file is sealed for {file_list}, not {list_name}: open "
                                    f"Credentials for {file_list} to check it. Nothing was compared.")
        in_file = digests_of(payload.get("devices") or [])
        file_key = describe(payload)["key_fingerprint"]
    finally:
        payload = None
    try:
        now = digests_of(list_devices(list_name))
    except BreakglassError as exc:
        return refused("compare", f"{exc}. Nothing was compared.")
    key = live_key()
    live = key_fingerprint(key) if key else ""
    key_state = ("absent" if not file_key else "current" if file_key == live else "differs")
    rows = compare(in_file, now)
    verdict = {r["device"]: r["state"] for r in rows}
    try:
        from modules.config import DATA_DIR
        record_check(DATA_DIR, list_name=list_name, actor=actor, sha256=sha, created=created,
                     devices=verdict, key=key_state)
        recorded = True
    except OSError as exc:
        recorded = False
        log.error("breakglass: a file check was not recorded (%s)", exc)
    counts = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return {"ok": True, "sha256": sha, "created": created, "file_list": file_list or list_name,
            "devices": rows, "key": key_state, "key_fingerprint": file_key, "counts": counts,
            "recorded": recorded}
