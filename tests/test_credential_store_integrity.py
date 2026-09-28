"""C157: the credential store gets the settings file's C20 fixes.

The store holds the only copy of every device credential. It had all three
properties that erased the settings file on 2026-09-23, fixed there and never
here: an unreadable read returned EMPTY and the next save wrote it back; the
lock was one process's `threading.Lock` while host CLIs write the same file;
and every save shared one temp name. The settings erasure was survivable only
because settings are reconstructible; credentials are not.
"""

import json
import logging
import multiprocessing
import os
import stat

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    from modules import credentials
    path = tmp_path / "credential_profiles.json"
    monkeypatch.setattr(credentials, "_FILE", str(path))
    return credentials, path


def _writer(prefix, n):
    from modules import credentials
    for i in range(n):
        credentials.set_device_override(f"{prefix}.{i}", "admin", f"Pw{prefix}{i}xyz", "")


def test_two_processes_writing_at_once_lose_nothing(store):
    """C20's lost update, across PROCESSES: each writes its own keys at the
    same time; every key must survive, and the file must still parse."""
    credentials, path = store
    ctx = multiprocessing.get_context("fork")
    n = 60
    procs = [ctx.Process(target=_writer, args=(p, n)) for p in ("10.1", "10.2")]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0, p.exitcode
    data = json.loads(path.read_text())
    assert len(data["device_overrides"]) == 2 * n, len(data["device_overrides"])


def test_an_unreadable_store_refuses_every_write_and_keeps_the_file(store):
    credentials, path = store
    path.write_text('{"profiles": {"default": {"username": "a"')   # a fragment
    before = path.read_bytes()
    with pytest.raises(credentials.CredentialStoreUnreadable):
        credentials.set_device_override("10.9.9.9", "admin", "Pw9secret9", "")
    assert path.read_bytes() == before, "the store was overwritten"
    kept = [p for p in path.parent.iterdir() if ".corrupt-" in p.name]
    assert kept and stat.S_IMODE(kept[0].stat().st_mode) == 0o600, kept
    # A READ survives on empty (the settings reader's rule) and writes nothing.
    assert credentials.has_device_override("10.9.9.9") is False
    assert path.read_bytes() == before


def test_every_write_is_logged_with_its_keys_never_a_value(store, caplog):
    credentials, _path = store
    with caplog.at_level(logging.INFO, logger="modules.credentials"):
        credentials.set_device_override("10.7.7.7", "admin", "Sup3rSecretPw", "")
        credentials.clear_device_override("10.7.7.7")
    text = caplog.text
    assert "+10.7.7.7" in text and "-10.7.7.7" in text, text
    assert f"pid {os.getpid()}" in text
    assert "Sup3rSecretPw" not in text


def test_a_save_outside_the_lock_is_refused(store):
    credentials, _path = store
    with pytest.raises(RuntimeError, match="outside the store lock"):
        credentials._save({"profiles": {}, "device_overrides": {}})
