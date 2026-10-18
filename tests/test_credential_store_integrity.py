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


def test_a_fresh_install_with_no_store_saves_its_first_profile_and_override(store):
    """No file yet (a new installation): the first profile and the first device credential
    are saved and read back (C1265's sample: 2 of `_load`'s mutants survived, its empty answer
    losing a key, and every writer indexes both keys directly)."""
    credentials, path = store
    assert not path.exists()
    assert credentials.list_profiles() == []
    assert credentials.has_device_override("192.0.2.31") is False
    assert credentials.save_profile("first", "admin", "Pw1first1")["ok"] is True
    assert credentials.set_device_override("192.0.2.31", "admin", "Pw2first2", "")["ok"]
    assert [p["name"] for p in credentials.list_profiles()] == ["first"]
    assert credentials.has_device_override("192.0.2.31") is True


@pytest.mark.parametrize("held", [{"profiles": {}}, {"device_overrides": {}}, {}])
def test_a_store_missing_a_section_still_takes_both_writes(store, held):
    """A readable store lacking one section (written by an older version, or by hand) is read
    with the missing section empty, never refused or broken (C1265's sample: 10 of `_load`'s
    mutants on its two `setdefault`s survived)."""
    credentials, path = store
    path.write_text(json.dumps(held))
    assert credentials.list_profiles() == []
    assert credentials.has_device_override("192.0.2.32") is False
    credentials.save_profile("p", "admin", "Pw3part3")
    credentials.set_device_override("192.0.2.32", "admin", "Pw4part4", "")
    data = json.loads(path.read_text())
    assert set(data["profiles"]) == {"p"} and set(data["device_overrides"]) == {"192.0.2.32"}


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


def test_an_unreadable_store_says_what_was_wrong_on_both_paths(store, caplog):
    """Lab 7 (b), the second sample: the log is where an unreadable store's cause is kept (the
    write path's refusal names only its kind), so both the write path's preservation and the
    read path's "reading as empty" name the error the file gave."""
    credentials, path = store
    path.write_text('{"profiles": {"default": {"username": "a"')   # a fragment
    with caplog.at_level(logging.ERROR):
        with pytest.raises(credentials.CredentialStoreUnreadable):
            credentials.set_device_override("192.0.2.98", "admin", "Pw9secret8", "")
        credentials.has_device_override("192.0.2.98")
    said = [r.getMessage() for r in caplog.records]
    assert any("unreadable store (JSONDecodeError" in m and "preserved as" in m
               for m in said), said
    assert any(m.startswith("credentials: unreadable store (JSONDecodeError")
               and "reading as empty" in m for m in said), said


def test_a_store_holding_no_template_secret_answers_empty_for_any(store):
    """Lab 7 (b), the second sample: a store no template secret was ever written to (a
    fresh one, or one with only profiles and overrides) has no `template_secrets` section;
    asking it for any secret answers "", never an error."""
    credentials, path = store
    assert credentials.get_template_secret("lab:r1:snmp_community") == ""
    credentials.set_device_override("192.0.2.97", "admin", "Pw9secret7", "")
    assert "template_secrets" not in json.loads(path.read_text())
    assert credentials.get_template_secret("lab:r1:snmp_community") == ""


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
