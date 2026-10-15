"""The list registry's one-time migration from its old format (each list's value the name of a
CSV file in the data folder) to a folder per list: `device._migrate_to_folder_structure`, run
by `_load_device_lists_config` when `_needs_migration` sees a ".csv" value (C824).

No test reached it until mutation night #10 (2026-10-15) planned it, changed by 495afbec, and
found its 38 VERDICT survivors: every one of its decisions (which entries move, where a list's
CSV goes, which network's folder takes the shared files, what is kept when both exist) ran
unchecked. Each test runs it on a temporary data folder.
"""

import csv
import json
import os

import pytest

from modules import config as C
from modules import device as D


@pytest.fixture
def data(tmp_path, monkeypatch):
    """A data folder of the test's own: the lists folder, the registry file and the data root
    the old format's file names are relative to."""
    monkeypatch.setattr(C, "LISTS_DIR", str(tmp_path / "lists"))
    monkeypatch.setattr(D, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(D, "DEVICE_LISTS_CONFIG", str(tmp_path / "device_lists.json"))
    return tmp_path


def _saved(data):
    return json.loads((data / "device_lists.json").read_text(encoding="utf-8"))


def _header(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return next(csv.reader(fh))


class TestEachListsCsv:
    def test_an_old_csv_moves_into_its_lists_folder(self, data):
        (data / "devices_branch.csv").write_text("the old rows\n", encoding="utf-8")
        out = D._migrate_to_folder_structure(
            {"current_list": "Branch Office", "lists": {"Branch Office": "devices_branch.csv"}})
        assert out["lists"] == {"Branch Office": "branch_office"}
        moved = data / "lists" / "branch_office" / "devices.csv"
        assert moved.read_text(encoding="utf-8") == "the old rows\n"
        assert not (data / "devices_branch.csv").exists()
        assert _saved(data) == out

    def test_a_missing_old_csv_leaves_an_empty_one_with_its_header(self, data):
        out = D._migrate_to_folder_structure(
            {"current_list": "Lab", "lists": {"Lab": "gone.csv"}})
        assert out["lists"] == {"Lab": "lab"}
        assert _header(data / "lists" / "lab" / "devices.csv") == list(D.DEVICE_CSV_FIELDS)

    def test_a_csv_already_in_the_folder_is_kept_and_the_old_one_left(self, data):
        (data / "old.csv").write_text("old\n", encoding="utf-8")
        (data / "lists" / "lab").mkdir(parents=True)
        (data / "lists" / "lab" / "devices.csv").write_text("new\n", encoding="utf-8")
        out = D._migrate_to_folder_structure({"current_list": "Lab", "lists": {"Lab": "old.csv"}})
        assert out["lists"] == {"Lab": "lab"}
        assert (data / "lists" / "lab" / "devices.csv").read_text(encoding="utf-8") == "new\n"
        assert (data / "old.csv").read_text(encoding="utf-8") == "old\n"

    def test_entries_already_migrated_are_left_and_do_not_stop_the_rest(self, data):
        (data / "devices_b.csv").write_text("b\n", encoding="utf-8")
        out = D._migrate_to_folder_structure({"current_list": "A", "lists": {
            "A": "a", "Odd": {"kept": "as it is"}, "Upper": "UPPER.CSV", "B": "devices_b.csv"}})
        assert out["lists"] == {"A": "a", "Odd": {"kept": "as it is"}, "Upper": "UPPER.CSV",
                                "B": "b"}
        assert (data / "lists" / "b" / "devices.csv").read_text(encoding="utf-8") == "b\n"
        assert not (data / "lists" / "upper").exists()

    def test_no_lists_at_all_saves_an_empty_registry(self, data):
        out = D._migrate_to_folder_structure({"current_list": "Default"})
        assert out["lists"] == {} and _saved(data)["lists"] == {}


class TestTheSharedFiles:
    def _shared(self, data):
        (data / "playbooks").mkdir()
        (data / "playbooks" / "p.yml").write_text("p\n", encoding="utf-8")
        (data / "network_kb.json").write_text("{}\n", encoding="utf-8")
        (data / "lab_notes.md").write_text("notes\n", encoding="utf-8")

    def test_they_move_into_the_current_lists_folder(self, data):
        self._shared(data)
        D._migrate_to_folder_structure({"current_list": "Branch", "lists": {"Branch": "b.csv"}})
        into = data / "lists" / "branch"
        assert (into / "playbooks" / "p.yml").read_text(encoding="utf-8") == "p\n"
        assert (into / "network_kb.json").read_text(encoding="utf-8") == "{}\n"
        assert (into / "lab_notes.md").read_text(encoding="utf-8") == "notes\n"
        assert not any((data / n).exists() for n in ("playbooks", "network_kb.json",
                                                     "lab_notes.md"))

    def test_with_no_current_list_they_go_to_default(self, data):
        self._shared(data)
        D._migrate_to_folder_structure({"lists": {"Branch": "b.csv"}})
        assert (data / "lists" / "default" / "lab_notes.md").read_text(encoding="utf-8") == \
            "notes\n"
        assert sorted(os.listdir(data / "lists")) == ["branch", "default"]

    def test_one_already_there_is_never_overwritten(self, data):
        self._shared(data)
        (data / "lists" / "branch").mkdir(parents=True)
        (data / "lists" / "branch" / "lab_notes.md").write_text("theirs\n", encoding="utf-8")
        D._migrate_to_folder_structure({"current_list": "Branch", "lists": {}})
        assert (data / "lists" / "branch" / "lab_notes.md").read_text(encoding="utf-8") == \
            "theirs\n"
        assert (data / "lab_notes.md").read_text(encoding="utf-8") == "notes\n"


def test_loading_an_old_registry_migrates_it(data):
    (data / "devices.csv").write_text("rows\n", encoding="utf-8")
    (data / "device_lists.json").write_text(
        json.dumps({"current_list": "Default", "lists": {"Default": "devices.csv"}}),
        encoding="utf-8")
    assert D._load_device_lists_config()["lists"] == {"Default": "default"}
    assert (data / "lists" / "default" / "devices.csv").read_text(encoding="utf-8") == "rows\n"
    assert _saved(data)["lists"] == {"Default": "default"}
