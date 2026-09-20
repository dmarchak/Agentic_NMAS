"""secrets_store.py

Encryption-at-rest for settings values that are secrets (API tokens, passwords,
access keys).

Background: NetBox's API token was previously written to
``data/user_settings.json`` in plaintext via ``set_user_setting``.  Every secret
introduced by the NSoT integrations work would have inherited that, so secrets
now round-trip through the existing Fernet key at ``data/key.key`` — the same
key ``modules/device.py`` uses for CSV credential fields.

Storage format is ``enc:v1:<fernet-token>``.  Values without that prefix are
treated as legacy plaintext and returned as-is, so a settings file written by an
older build keeps working and is upgraded in place by :func:`migrate_plaintext`.

Nothing in this module logs a secret value.  Log the *key name* if you must log
anything at all.
"""

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from modules.config import (
    KEY_FILE,
    get_user_setting,
    set_user_setting,
)

log = logging.getLogger(__name__)

_PREFIX = "enc:v1:"

# Settings keys holding secrets. migrate_plaintext() upgrades these in place and
# the settings API masks them on read. Add new secret-bearing keys here.
SECRET_KEYS = (
    "netbox_token",
    "prometheus_password",
    "prometheus_bearer_token",
    "grafana_token",
    "loki_password",
    "loki_bearer_token",
    "oxidized_password",
    "kea_password",
    "topology_service_token",
    "nsot_git_token",
    "s3_access_key",
    "s3_secret_key",
)

_fernet: "Fernet | None" = None


def _get_fernet() -> Fernet:
    """Return the shared Fernet instance, creating ``data/key.key`` if absent.

    Mirrors ``device.load_key()`` rather than importing it: importing
    ``modules.device`` pulls in CSV loading and device-list side effects that
    settings code has no reason to trigger.
    """
    global _fernet
    if _fernet is None:
        if not os.path.exists(KEY_FILE):
            os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
            with open(KEY_FILE, "wb") as fh:
                fh.write(Fernet.generate_key())
            log.info("secrets_store: generated new Fernet key at %s", KEY_FILE)
        with open(KEY_FILE, "rb") as fh:
            _fernet = Fernet(fh.read())
    return _fernet


def is_encrypted(value: str) -> bool:
    """True if *value* is already in the at-rest format."""
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_value(plaintext: str) -> str:
    """Encrypt *plaintext* for storage. Empty input stays empty (means 'unset')."""
    if not plaintext:
        return ""
    if is_encrypted(plaintext):
        return plaintext
    token = _get_fernet().encrypt(plaintext.encode()).decode()
    return f"{_PREFIX}{token}"


def decrypt_value(stored: str) -> str:
    """Decrypt a stored value.

    Legacy plaintext (no prefix) is returned unchanged so older settings files
    keep working. An undecryptable value returns "" rather than raising — a
    rotated or restored ``key.key`` must not take the settings page down.
    """
    if not stored:
        return ""
    if not is_encrypted(stored):
        return stored
    try:
        return _get_fernet().decrypt(stored[len(_PREFIX):].encode()).decode()
    except (InvalidToken, ValueError):
        log.error(
            "secrets_store: could not decrypt a stored secret — the Fernet key at "
            "%s may have changed. Re-enter the value in Settings.", KEY_FILE
        )
        return ""


def get_secret(key: str, default: str = "") -> str:
    """Read and decrypt a secret setting."""
    raw = get_user_setting(key, "")
    return decrypt_value(raw) if raw else default


def set_secret(key: str, value: str) -> bool:
    """Encrypt and persist a secret setting. Empty *value* clears it."""
    return set_user_setting(key, encrypt_value(value) if value else "")


def is_set(key: str) -> bool:
    """True if a secret has a stored value, without decrypting it."""
    return bool(get_user_setting(key, ""))


def mask(key: str) -> str:
    """UI indicator for a write-only field: never returns the value itself."""
    return "••••••••" if is_set(key) else ""


def migrate_plaintext(keys=SECRET_KEYS) -> list:
    """Encrypt any secret still stored as plaintext. Idempotent.

    Returns the key names upgraded (names only — never values).
    """
    upgraded = []
    for key in keys:
        raw = get_user_setting(key, "")
        if raw and not is_encrypted(raw):
            # Verify the round-trip before dropping the plaintext.
            enc = encrypt_value(raw)
            if decrypt_value(enc) == raw:
                set_user_setting(key, enc)
                upgraded.append(key)
            else:
                log.error("secrets_store: round-trip failed for '%s' — left as-is", key)
    if upgraded:
        log.info("secrets_store: encrypted %d plaintext secret(s): %s",
                 len(upgraded), ", ".join(upgraded))
    return upgraded
