"""The per-test store guard compares contents, not only paths (C571; tests/store_contents.py).

The guard itself runs around every test (conftest's `_no_test_writes_into_live_data`); these
hold its comparison on a folder of their own. Shown able to fail through the guard on
2026-10-08 with a planted test that appended to the store's `default/devices.csv`: it failed
naming "default/devices.csv rewritten", and the file was put back.
"""

from tests import store_contents as SC


def _tree(tmp_path):
    (tmp_path / "default").mkdir()
    (tmp_path / "default" / "devices.csv").write_bytes(b"hostname,ip\n")
    (tmp_path / "default" / "config_repo" / ".git").mkdir(parents=True)
    (tmp_path / "default" / "config_repo" / ".git" / "index").write_bytes(b"churns")
    return SC.contents(str(tmp_path))


def test_an_unchanged_store_has_no_changes(tmp_path):
    kept = _tree(tmp_path)
    assert len(kept) == 1, "the file, and nothing under .git"
    assert SC.changes(kept) == []


def test_a_rewrite_and_a_deletion_are_named_and_put_back(tmp_path):
    kept = _tree(tmp_path)
    path = str(tmp_path / "default" / "devices.csv")
    (tmp_path / "default" / "devices.csv").write_bytes(b"hostname,ip\nr2,192.0.2.12\n")
    assert SC.changes(kept) == [(path, "rewritten")]
    SC.restore(kept, SC.changes(kept))
    assert SC.changes(kept) == []
    (tmp_path / "default" / "devices.csv").unlink()
    assert SC.changes(kept) == [(path, "deleted")]
    SC.restore(kept, SC.changes(kept))
    assert (tmp_path / "default" / "devices.csv").read_bytes() == b"hostname,ip\n"


def test_a_git_folder_churning_is_not_a_change(tmp_path):
    kept = _tree(tmp_path)
    (tmp_path / "default" / "config_repo" / ".git" / "index").write_bytes(b"moved")
    assert SC.changes(kept) == []
