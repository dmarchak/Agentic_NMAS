"""breakglass.py — getting back into devices that will not answer.

Written as a precondition for lifting the rcn-lab1 redeploy ban. Stage B
measured what a bad redeploy looks like: five routers up, healthy, answering
SSH, holding a credential nobody has. The recovery path is the serial console
on the clab host, and it needs the credential that was live *before* the
redeploy -- which by then exists only in `devices.csv`, encrypted with
`data/key.key`, on a machine the operator may not be sitting at.

So the record has three properties, and each of them is the answer to a
specific way the obvious version fails:

**Independent of `data/key.key`.** Encrypting with the key the application
already uses makes the record share a single point of failure with the thing
it is meant to recover from. The passphrase is supplied by the operator and
derived with scrypt.

**Outside the repository, and never committed.** `config_repo` is pushed to a
private GitHub remote. A file of live plaintext credentials is exactly what
Phase 2b's history scan exists to keep out.

**Verifiable without being read.** A break-glass record nobody has opened is
not a record, it is a hope. :func:`describe` decrypts and reports structure --
device count, fields present, a per-device digest -- and prints no value. The
rule "never print a secret value" is unconditional, and a verification step
that requires revealing everything would mean the record is only ever tested
by exposing it.

**It escrows the application's Fernet key, and proves it is the right one**
(B5, 2026-09-25). Nothing images the NMAS VM, so the key existed on one disk.
The key is sealed here by the passphrase like everything else, so the record
still does not DEPEND on it. It only carries it. A copy of the wrong key looks
exactly like a working one, so :func:`check_key_opens` decrypts the values
actually stored on the host with the ESCROWED key and counts them. That is
the check that tells the two apart, and a fingerprint match alone is not.
This module never reads the key file itself; the CLI hands it the bytes.

It is deliberately dumb: a JSON envelope, one scrypt call, one Fernet token.
Anything cleverer is something to debug during an outage.
"""

import base64
import csv
import glob
import hashlib
import json
import logging
import os
import secrets
import time

log = logging.getLogger(__name__)

FORMAT_VERSION = 1

#: scrypt parameters. n=2**15 is ~100ms on a laptop -- slow enough to make a
#: weak passphrase expensive, fast enough that nobody skips the step.
#:
#: `maxmem` is explicit and not decoration: 128 * n * r is exactly 32 MiB,
#: which is precisely OpenSSL's default ceiling, so the call fails with
#: "memory limit exceeded" unless it is raised. Tuning n without moving it
#: turns a stronger KDF into a hard error at the moment the record is written.
_SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1, "dklen": 32, "maxmem": 128 * 1024 * 1024}

#: What the payload records per device. Listed rather than inferred from
#: whatever a device dict happens to hold, so a new inventory field cannot
#: silently land in a plaintext export.
FIELDS = ("hostname", "ip", "username", "password", "secret", "platform",
          "list_name", "container")


class BreakglassError(Exception):
    """Refusal, or a passphrase that does not open the record."""


#: The shortest passphrase accepted. Not a judgement of quality: the file is
#: an OFFLINE target, attacked at the attacker's leisure, and scrypt's cost
#: only multiplies what a short passphrase gives away.
MIN_PASSPHRASE = 12


def _key_from(passphrase: str, salt: bytes) -> bytes:
    if not passphrase or len(passphrase) < MIN_PASSPHRASE:
        raise BreakglassError(
            "the passphrase must be at least 12 characters. This file is the "
            "last way into the devices; a short passphrase makes it the "
            "easiest way in for everyone else.")
    raw = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, **_SCRYPT)
    return base64.urlsafe_b64encode(raw)


def key_fingerprint(key: bytes) -> str:
    """A short digest of a Fernet key, safe to print and compare by eye.

    The key is 32 random bytes, so a hash of it reveals nothing usable.
    Surrounding whitespace is not part of the key.
    """
    return hashlib.sha256(key.strip()).hexdigest()[:16]


def build_payload(devices: list, *, list_name: str, recovery: str = "",
                  fernet_key: bytes = b"") -> dict:
    """The cleartext record, before encryption.

    Carries the recovery *procedure* as well as the credentials. Someone
    opening this during an outage should not also have to find the runbook.
    *fernet_key* is the application's key, escrowed (B5); empty means the
    record carries none, which :func:`describe` reports.
    """
    entries = []
    for device in devices:
        entry = {field: str(device.get(field) or "") for field in FIELDS}
        entry["list_name"] = entry["list_name"] or list_name
        entries.append(entry)
    return {
        "format": FORMAT_VERSION,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "list_name": list_name,
        "recovery": recovery or DEFAULT_RECOVERY,
        "devices": entries,
        "fernet_key": fernet_key.strip().decode("ascii") if fernet_key else "",
    }


DEFAULT_RECOVERY = (
    "If a device will not accept these credentials, it is holding what its "
    "boot path gave it. Reach the serial console on the containerlab host -- "
    "`docker exec -it <container> telnet localhost 5000` -- and log in with "
    "the credential vrnetlab injects (see the lab's launch script). Then set "
    "the credential below by hand. Do NOT redeploy to fix a redeploy.\n\n"
    "If the NMAS host lost its application key, this record carries it: "
    "`nmas-breakglass restore-key <record> --out <data dir>/key.key` writes it "
    "back owner-only and refuses to replace an existing file. Then run "
    "`nmas-breakglass verify <record> --live` on the host: the key is the "
    "right one only if it opens the values stored there."
)


def seal(payload: dict, passphrase: str) -> bytes:
    """Encrypt. The salt travels with the ciphertext; the passphrase does not."""
    from cryptography.fernet import Fernet

    salt = secrets.token_bytes(16)
    token = Fernet(_key_from(passphrase, salt)).encrypt(
        json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
    return json.dumps({
        "breakglass": FORMAT_VERSION,
        "kdf": "scrypt",
        # maxmem is a local resource ceiling, not part of the derivation.
        "scrypt": {k: v for k, v in _SCRYPT.items() if k != "maxmem"},
        "salt": base64.b64encode(salt).decode("ascii"),
        "ciphertext": token.decode("ascii"),
    }, indent=2).encode("utf-8")


def unseal(blob: bytes, passphrase: str) -> dict:
    """Decrypt, or say plainly that the passphrase is wrong."""
    from cryptography.fernet import Fernet, InvalidToken

    try:
        envelope = json.loads(blob.decode("utf-8"))
        salt = base64.b64decode(envelope["salt"])
    except Exception as exc:                   # noqa: BLE001
        raise BreakglassError(f"not a break-glass record: {exc}") from exc

    if envelope.get("breakglass") != FORMAT_VERSION:
        raise BreakglassError(
            f"record format {envelope.get('breakglass')!r}, this code reads "
            f"{FORMAT_VERSION}")
    try:
        plain = Fernet(_key_from(passphrase, salt)).decrypt(
            envelope["ciphertext"].encode("ascii"))
    except InvalidToken as exc:
        raise BreakglassError(
            "the passphrase does not open this record. Nothing else is "
            "wrong with the file.") from exc
    return json.loads(plain.decode("utf-8"))


def describe(payload: dict) -> dict:
    """Prove the record opens and is complete, WITHOUT printing a value.

    Per device: which fields are present, and a digest of the credential. The
    digest is salted with the hostname so two devices sharing a password do
    not display the same token -- that is a fact about the fleet, and a
    verification report is not the place to leak it.
    """
    rows = []
    for entry in payload.get("devices", []):
        present = sorted(field for field in FIELDS if entry.get(field))
        material = (entry.get("hostname", "") + "\x00"
                    + entry.get("password", "")).encode("utf-8")
        rows.append({
            "hostname": entry.get("hostname", ""),
            "ip": entry.get("ip", ""),
            "platform": entry.get("platform", ""),
            "has_password": bool(entry.get("password")),
            # A copy of the password is not an enable secret (B14): every
            # device stored one, and this reported all of them as having one.
            "has_enable_secret": bool(entry.get("secret"))
                                 and entry.get("secret") != entry.get("password"),
            "fields": present,
            "digest": hashlib.sha256(material).hexdigest()[:12],
        })
    key = payload.get("fernet_key", "")
    return {
        "created": payload.get("created", ""),
        "list_name": payload.get("list_name", ""),
        "devices": rows,
        "complete": all(row["has_password"] for row in rows) and bool(rows),
        # The fingerprint, never the key. A record from before escrow has no
        # such field and reports False rather than failing to open.
        "has_fernet_key": bool(key),
        "key_fingerprint": key_fingerprint(key.encode("ascii")) if key else "",
    }


def escrowed_key(payload: dict) -> bytes:
    key = payload.get("fernet_key", "")
    if not key:
        raise BreakglassError(
            "this record carries no application key. It predates key escrow "
            "(2026-09-25); export a new one on the NMAS host.")
    return key.encode("ascii")


#: Where the application keeps values encrypted with its Fernet key, relative
#: to its data directory. JSON stores mark a value with a prefix (the caller
#: supplies it, so this module need not import the store that owns it); the
#: CSV stores hold bare tokens in two named columns. Live files only: a
#: `.bak` copy is not what the running application decrypts.
JSON_STORES = ("user_settings.json", "credential_profiles.json",
               "jenkins_checks.json")
CSV_STORE_GLOB = os.path.join("lists", "*", "devices.csv")
CSV_SECRET_COLUMNS = ("password", "secret")


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def live_ciphertexts(data_dir: str, prefix: str) -> dict:
    """``{store: [token, ...]}`` for every encrypted value on this host.

    Tokens only, never decrypted here. An unreadable store is listed under
    ``_unreadable`` rather than skipped, because a store that could not be
    read has not been checked.
    """
    found, unreadable = {}, []
    for name in JSON_STORES:
        path = os.path.join(data_dir, name)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                doc = json.load(handle)
        except (OSError, ValueError):
            unreadable.append(name)
            continue
        tokens = [v[len(prefix):] for v in _strings(doc) if v.startswith(prefix)]
        if tokens:
            found[name] = tokens
    for path in sorted(glob.glob(os.path.join(data_dir, CSV_STORE_GLOB))):
        name = os.path.relpath(path, data_dir)
        try:
            with open(path, newline="", encoding="utf-8") as handle:
                tokens = [row[c] for row in csv.DictReader(handle)
                          for c in CSV_SECRET_COLUMNS if (row.get(c) or "").strip()]
        except (OSError, csv.Error, UnicodeDecodeError):
            unreadable.append(name)
            continue
        if tokens:
            found[name] = tokens
    if unreadable:
        found["_unreadable"] = unreadable
    return found


def check_key_opens(key: bytes, stores: dict) -> dict:
    """Does *key* decrypt the values actually stored? Counts only.

    Four verdicts, because they call for different actions:

    * ``opens``: every stored value opened. This is the key.
    * ``wrong_key``: none opened. The record holds some other key, and
      restoring it would lose every secret on the host.
    * ``mixed``: some opened. Values under two keys exist on this host,
      which is a finding in its own right, and the record is not proven.
    * ``unproven``: nothing to test against. Zero values is what a wrong
      data directory produces, so it is never a pass.

    Each plaintext is discarded the moment it is produced.
    """
    from cryptography.fernet import Fernet, InvalidToken

    try:
        fernet = Fernet(key.strip())
    except (ValueError, TypeError) as exc:
        return {"verdict": "wrong_key", "opened": 0, "total": 0, "stores": {},
                "unreadable": [], "detail": f"not a Fernet key: {exc}"}
    per_store, opened, total = {}, 0, 0
    for name, tokens in stores.items():
        if name == "_unreadable":
            continue
        ok = 0
        for token in tokens:
            try:
                fernet.decrypt(token.encode("ascii"))
                ok += 1
            except (InvalidToken, ValueError, UnicodeEncodeError):
                pass
        per_store[name] = {"opened": ok, "total": len(tokens)}
        opened, total = opened + ok, total + len(tokens)
    unreadable = list(stores.get("_unreadable", []))
    if total == 0:
        verdict = "unproven"
    elif opened == total and not unreadable:
        verdict = "opens"
    elif opened == 0:
        verdict = "wrong_key"
    elif opened == total:
        verdict = "unproven"      # everything read opened; some stores unread
    else:
        verdict = "mixed"
    return {"verdict": verdict, "opened": opened, "total": total,
            "stores": per_store, "unreadable": unreadable}


def restore_key(payload: dict, out: str) -> dict:
    """Write the escrowed key to *out*, owner-only, never over a file.

    Refusing to replace is the whole safety property: a key file that exists
    is the key the stored values are encrypted with, or it is a new one a
    fresh start generated. Either way, deciding to discard it is a person's
    call, made by moving it aside first.
    """
    key = escrowed_key(payload)
    resolved = os.path.abspath(out)
    if os.path.exists(resolved):
        raise BreakglassError(
            f"{resolved} exists. Nothing was written. If it is a key a fresh "
            f"start generated, move it aside and run this again; values "
            f"encrypted with it since then will not open with the restored key.")
    descriptor = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(key)
    return {"ok": True, "path": resolved, "fingerprint": key_fingerprint(key),
            "mode": oct(os.stat(resolved).st_mode & 0o777)}


def write_record(path: str, payload: dict, passphrase: str) -> dict:
    """Write owner-only, and refuse a path inside a git repository.

    The refusal is not politeness. `config_repo` is pushed to a private remote
    and the history scan cannot un-publish what it finds.
    """
    resolved = os.path.abspath(path)
    parent = os.path.dirname(resolved)
    probe = parent
    while True:
        if os.path.isdir(os.path.join(probe, ".git")):
            raise BreakglassError(
                f"{resolved} is inside the git repository at {probe}. This "
                f"file holds live plaintext credentials and repositories get "
                f"pushed. Write it somewhere outside, on removable media or a "
                f"password manager.")
        nxt = os.path.dirname(probe)
        if nxt == probe:
            break
        probe = nxt

    blob = seal(payload, passphrase)
    descriptor = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(blob)
    os.chmod(resolved, 0o600)
    log.info("break-glass record written for %d device(s)",
             len(payload.get("devices", [])))
    return {"ok": True, "path": resolved, "devices": len(payload.get("devices", [])),
            "mode": oct(os.stat(resolved).st_mode & 0o777)}


def read_record(path: str, passphrase: str) -> dict:
    with open(path, "rb") as handle:
        return unseal(handle.read(), passphrase)


# ---------------------------------------------------------------------------
# Currency: does the record hold the credential NMAS holds NOW? (C182)
# ---------------------------------------------------------------------------
#
# The record lives on the operator's laptop and the credentials NMAS holds live
# on the host, encrypted with the host's key. `describe()` proves the record
# opens; nothing compared it with the credentials in use, and nothing noticed
# a rotation making it stale. Both sides compute the SAME salted digest, so
# the comparison moves no credential between machines, prints no value, and
# connects to no device.

#: The export log: one row per export made on this host, the per-device
#: digests and no value (0600). Job health compares its newest row per list
#: with the credentials held now.
EXPORT_LOG = "breakglass_exports.jsonl"


def currency_digest(hostname: str, username: str, password: str) -> str:
    """A salted digest of one device's login credential. A GUESSING ORACLE
    for a weak password, stated so it is not mistaken for nothing: the value
    goes only to the laptop that already holds the record, and into a 0600
    log beside the store that holds the credential itself."""
    material = "\x00".join(("nmas-breakglass-currency", hostname or "",
                            username or "", password or "")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


def digests_of(devices: list) -> dict:
    """{hostname: digest} for device dicts carrying plaintext credentials."""
    return {d.get("hostname", ""): currency_digest(d.get("hostname", ""),
                                                   d.get("username", ""),
                                                   d.get("password", ""))
            for d in devices if d.get("hostname")}


def compare(record: dict, current: dict) -> list:
    """Per device: ``current`` (the record holds what NMAS holds), ``differs``
    (it holds another credential: exported before a rotation), ``left`` (in
    the record, not managed now: its entry is history) or ``missing`` (managed,
    not in the record). Sorted by name. Values never enter it: digests only."""
    out = []
    for host in sorted(set(record) | set(current)):
        if host not in current:
            state = "left"
        elif host not in record:
            state = "missing"
        else:
            state = "current" if record[host] == current[host] else "differs"
        out.append({"device": host, "state": state})
    return out


def record_export(data_dir: str, *, list_name: str, devices: list, path: str,
                  key_fingerprint: str, actor: str, at: float = None,
                  via: str = "host", sha256: str = "") -> dict:
    """Append this export to the log: when, which list, where it was written
    (or ``via: browser``, downloaded, with the file's sha256), the key's
    fingerprint and each device's digest. Never a value."""
    from modules.config import open_secure

    row = {"at": at if at is not None else time.time(), "list": list_name,
           "path": path, "key_fingerprint": key_fingerprint, "actor": actor,
           "via": via, "devices": digests_of(devices)}
    if sha256:
        row["sha256"] = sha256
    with open_secure(os.path.join(data_dir, EXPORT_LOG), "a") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row


#: The browser's word on each download (board 7, signed off 2026-10-03): the sha256 the
#: browser computed of the bytes it received, against the one the server recorded. A download
#: that did not arrive intact is not counted as current. Digests of a sealed file, no value.
INTACT_LOG = "breakglass_intact.jsonl"


def record_intact(data_dir: str, *, list_name: str, sha256: str, browser_sha256: str,
                  actor: str, at: float = None) -> dict:
    """Append the browser's verdict on one download: ``ok`` when its sha256 of the bytes it
    received is the server's."""
    from modules.config import open_secure

    row = {"at": at if at is not None else time.time(), "list": list_name,
           "sha256": sha256, "browser_sha256": browser_sha256,
           "ok": bool(sha256) and sha256 == browser_sha256, "actor": actor}
    with open_secure(os.path.join(data_dir, INTACT_LOG), "a") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def intact_verdicts(data_dir: str) -> dict:
    """``{"state", "by_sha": {sha256: newest verdict row}}``; absent and unreadable differ."""
    path = os.path.join(data_dir, INTACT_LOG)
    if not os.path.exists(path):
        return {"state": "absent", "by_sha": {}}
    try:
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "by_sha": {}, "error": str(exc)}
    out = {}
    for r in rows:
        if r.get("sha256") and r.get("at", 0) >= out.get(r["sha256"], {}).get("at", 0):
            out[r["sha256"]] = r
    return {"state": "ok", "by_sha": out}


def currency(last: dict, now_digests: dict, verdict: dict = None) -> dict:
    """THE judgement of one list's record (job health's row and the Credentials page both
    read it): ``{"state": never|not_intact|stale|current, "stale": [{device, state}],
    "intact": True|False|None}``. *last*: the list's newest export row (or None); *verdict*:
    the browser's on that export's sha256 (or None: a host export, or a browser that said
    nothing)."""
    if not last:
        return {"state": "never", "stale": [], "intact": None}
    intact = None if not verdict else bool(verdict.get("ok"))
    stale = [r for r in compare(last.get("devices") or {}, now_digests)
             if r["state"] in ("differs", "missing")]
    if intact is False:
        return {"state": "not_intact", "stale": stale, "intact": False}
    return {"state": "stale" if stale else "current", "stale": stale, "intact": intact}


def last_exports(data_dir: str) -> dict:
    """``{"state": absent|unreadable|ok, "by_list": {list: newest row}}``.
    Absent and unreadable are different answers (the settings erasure)."""
    path = os.path.join(data_dir, EXPORT_LOG)
    if not os.path.exists(path):
        return {"state": "absent", "by_list": {}}
    try:
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "by_list": {}, "error": str(exc)}
    newest = {}
    for r in rows:
        if r.get("list") and r.get("at", 0) >= newest.get(r["list"], {}).get("at", 0):
            newest[r["list"]] = r
    return {"state": "ok", "by_list": newest}

