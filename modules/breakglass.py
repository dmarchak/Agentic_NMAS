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

It is deliberately dumb: a JSON envelope, one scrypt call, one Fernet token.
Anything cleverer is something to debug during an outage.
"""

import base64
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


def _key_from(passphrase: str, salt: bytes) -> bytes:
    if not passphrase or len(passphrase) < 12:
        raise BreakglassError(
            "the passphrase must be at least 12 characters. This file is the "
            "last way into the devices; a short passphrase makes it the "
            "easiest way in for everyone else.")
    raw = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, **_SCRYPT)
    return base64.urlsafe_b64encode(raw)


def build_payload(devices: list, *, list_name: str, recovery: str = "") -> dict:
    """The cleartext record, before encryption.

    Carries the recovery *procedure* as well as the credentials. Someone
    opening this during an outage should not also have to find the runbook.
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
    }


DEFAULT_RECOVERY = (
    "If a device will not accept these credentials, it is holding what its "
    "boot path gave it. Reach the serial console on the containerlab host -- "
    "`docker exec -it <container> telnet localhost 5000` -- and log in with "
    "the credential vrnetlab injects (see the lab's launch script). Then set "
    "the credential below by hand. Do NOT redeploy to fix a redeploy."
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
            "has_enable_secret": bool(entry.get("secret")),
            "fields": present,
            "digest": hashlib.sha256(material).hexdigest()[:12],
        })
    return {
        "created": payload.get("created", ""),
        "list_name": payload.get("list_name", ""),
        "devices": rows,
        "complete": all(row["has_password"] for row in rows) and bool(rows),
    }


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
