"""Two backups of one device in one second are two backups (the operator,
2026-10-01, found by the POST sweep's fixture, C270): the name is to the
second, and the second save silently replaced the first, while the index,
read and rewritten whole by each, could lose an entry.

The clock is FROZEN, so "the same second" is certain rather than lucky.
"""
import json
import threading
from datetime import datetime as _real

import pytest


class _Frozen:
    """`datetime` with `now()` fixed at one instant."""
    at = _real(2026, 10, 1, 3, 42, 39)

    @classmethod
    def now(cls):
        return cls.at


@pytest.fixture
def store(monkeypatch, tmp_path):
    from modules import backups
    monkeypatch.setattr(backups, "get_backups_dir", lambda: str(tmp_path))
    monkeypatch.setattr(backups, "datetime", _Frozen)
    return tmp_path


def test_a_second_backup_in_the_same_second_is_its_own_file(store):
    from modules import backups
    a = backups.save_config_backup("192.0.2.2", "r2", "hostname r2\n! first\nend\n")
    b = backups.save_config_backup("192.0.2.2", "r2", "hostname r2\n! second\nend\n")
    assert a["filename"] == "r2_192.0.2.2_running_20261001_034239.cfg"
    assert b["filename"] == "r2_192.0.2.2_running_20261001_034239_2.cfg"
    assert "! first" in (store / a["filename"]).read_text()
    assert "! second" in (store / b["filename"]).read_text()
    names = [x["filename"] for x in json.loads((store / "backup_index.json").read_text())["backups"]]
    assert names == [a["filename"], b["filename"]]


def test_many_at_once_lose_nothing(store):
    """Eight at once, the same device, the same second: eight files and
    eight index entries (the index under one lock, written atomically)."""
    from modules import backups
    got, errors = [], []

    def one(i):
        try:
            got.append(backups.save_config_backup("192.0.2.2", "r2", f"hostname r2\n! {i}\nend\n"))
        except Exception as exc:                        # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=one, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert not errors, errors
    names = {g["filename"] for g in got}
    assert len(names) == 8
    assert {p.name for p in store.glob("*.cfg")} == names
    index = json.loads((store / "backup_index.json").read_text())["backups"]
    assert sorted(x["filename"] for x in index) == sorted(names)


def test_deleting_one_keeps_the_other(store):
    from modules import backups
    a = backups.save_config_backup("192.0.2.2", "r2", "hostname r2\nend\n")
    b = backups.save_config_backup("192.0.2.2", "r2", "hostname r2\nend\n")
    assert backups.delete_backup(a["filename"])
    assert not (store / a["filename"]).exists() and (store / b["filename"]).exists()
    index = json.loads((store / "backup_index.json").read_text())["backups"]
    assert [x["filename"] for x in index] == [b["filename"]]


def test_an_unreadable_index_is_kept_and_refused(store):
    """Absent and unreadable are different facts: the index is never
    rewritten from nothing (C158's rule)."""
    from modules import backups
    from modules.filestore import StoreUnreadable
    (store / "backup_index.json").write_text("{not json")
    with pytest.raises(StoreUnreadable):
        backups.save_config_backup("192.0.2.2", "r2", "hostname r2\nend\n")
    assert list(store.glob("backup_index.json.corrupt-*"))
