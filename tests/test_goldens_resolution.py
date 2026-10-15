"""C781: the golden resolver's three helpers that the AI family's removal left with no test of
their own (`modules/goldens.py`: `_identity_for_ip`, `_legacy_header_scan`,
`_find_golden_config_file`). Night #4 measured them at 0% mutation score: nothing ran them.

Each test drives the function's real code against files it writes (the manifest through
`modules.nsot.manifest`'s own writer, legacy goldens as the pre-Phase-2 store held them: a
`! ... — <hostname> (<ip>)` first line), and asserts what a caller gets: which file, which
identity, or none; never how the function got there.
"""

import logging
import os

import pytest

from modules import goldens as G
from modules.nsot import manifest as M


def _legacy(folder, name, ip, host="r1", body="hostname r1\n"):
    path = folder / name
    path.write_text(f"! Golden config — {host} ({ip})\n{body}", encoding="utf-8")
    return str(path)


@pytest.fixture
def legacy_dir(tmp_path, monkeypatch):
    d = tmp_path / "legacy_store"
    d.mkdir()
    monkeypatch.setattr(G, "_get_golden_configs_dir", lambda: str(d))
    return d


class TestTheLegacyHeaderScan:
    def test_finds_the_file_whose_first_line_names_the_address(self, legacy_dir):
        _legacy(legacy_dir, "r2.cfg", "192.0.2.2", host="r2")
        want = _legacy(legacy_dir, "r1.cfg", "192.0.2.1")
        assert G._legacy_header_scan("192.0.2.1") == want

    def test_an_address_is_matched_whole_never_as_a_prefix(self, legacy_dir):
        _legacy(legacy_dir, "r10.cfg", "192.0.2.10", host="r10")
        assert G._legacy_header_scan("192.0.2.1") is None
        assert G._legacy_header_scan("192.0.2.10") == str(legacy_dir / "r10.cfg")

    def test_only_the_first_line_and_only_cfg_files_are_read(self, legacy_dir):
        (legacy_dir / "r1.cfg").write_text("! no address here\n! (192.0.2.1)\n",
                                           encoding="utf-8")
        _legacy(legacy_dir, "r1.txt", "192.0.2.1")
        assert G._legacy_header_scan("192.0.2.1") is None

    def test_the_first_by_name_wins_and_an_unreadable_one_is_passed_over(self, legacy_dir):
        (legacy_dir / "a.cfg").mkdir()                    # opening it raises
        first = _legacy(legacy_dir, "b.cfg", "192.0.2.1")
        _legacy(legacy_dir, "c.cfg", "192.0.2.1")
        assert G._legacy_header_scan("192.0.2.1") == first

    def test_no_store_is_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(G, "_get_golden_configs_dir", lambda: str(tmp_path / "absent"))
        assert G._legacy_header_scan("192.0.2.1") is None


class TestTheLegacyRename:
    """`_migrate_golden_configs`: a legacy file named by address (`192_0_2_1.cfg`) is renamed
    to its hostname from its header, once, and never after the repository's migration."""

    @pytest.fixture
    def store(self, legacy_dir, monkeypatch):
        monkeypatch.setattr(G, "_nsot_migrated", lambda: False)
        return legacy_dir

    def test_an_address_named_file_takes_its_hostname(self, store):
        _legacy(store, "192_0_2_1.cfg", "192.0.2.1", host="r1")
        G._migrate_golden_configs()
        assert sorted(os.listdir(store)) == ["r1.cfg"]
        assert (store / "r1.cfg").read_text(encoding="utf-8").startswith("! Golden config — r1")

    def test_the_hostname_is_made_a_safe_file_name(self, store):
        _legacy(store, "192_0_2_2.cfg", "192.0.2.2", host="core.sw 1/a")
        G._migrate_golden_configs()
        assert sorted(os.listdir(store)) == ["core_sw_1_a.cfg"]

    def test_an_existing_target_is_never_overwritten(self, store):
        _legacy(store, "192_0_2_1.cfg", "192.0.2.1", host="r1", body="old\n")
        (store / "r1.cfg").write_text("newer\n", encoding="utf-8")
        G._migrate_golden_configs()
        assert sorted(os.listdir(store)) == ["192_0_2_1.cfg", "r1.cfg"]
        assert (store / "r1.cfg").read_text(encoding="utf-8") == "newer\n"

    def test_only_address_named_files_with_a_readable_header_move(self, store, caplog):
        _legacy(store, "r9.cfg", "192.0.2.9", host="r9")                  # not address-named
        (store / "192_0_2_3.cfg").write_text("! no header here\n", encoding="utf-8")
        (store / "192_0_2_4.cfg").mkdir()                                  # opening it raises
        _legacy(store, "192_0_2_5.cfg", "192.0.2.5", host="r5")
        with caplog.at_level(logging.WARNING, logger="modules.goldens"):
            G._migrate_golden_configs()
        assert sorted(os.listdir(store)) == ["192_0_2_3.cfg", "192_0_2_4.cfg", "r5.cfg",
                                             "r9.cfg"]
        assert any("192_0_2_4.cfg" in r.getMessage() for r in caplog.records)

    def test_nothing_moves_once_the_repository_is_migrated(self, legacy_dir, monkeypatch):
        monkeypatch.setattr(G, "_nsot_migrated", lambda: True)
        _legacy(legacy_dir, "192_0_2_1.cfg", "192.0.2.1", host="r1")
        G._migrate_golden_configs()
        assert sorted(os.listdir(legacy_dir)) == ["192_0_2_1.cfg"]


class TestTheIdentityForAnAddress:
    @pytest.fixture
    def inventory(self, monkeypatch):
        rows = {"active.csv": [{"ip": "192.0.2.1", "_netbox_id": 41, "device_uid": "x"},
                               {"ip": "192.0.2.2", "device_uid": "abc"},
                               {"ip": "192.0.2.3"}],
                "other.csv": [{"ip": "192.0.2.1", "device_uid": "uid:in-other"}]}
        read = []

        def load(path):
            read.append(path)
            return [dict(r) for r in rows[path]]

        class _Ref:
            csv_path = "other.csv"

        monkeypatch.setattr("modules.device.get_current_device_list",
                            lambda: ("active", "active.csv"))
        monkeypatch.setattr("modules.device.load_saved_devices", load)
        monkeypatch.setattr("modules.nsot.listref.resolve",
                            lambda name: _Ref() if name == "other" else pytest.fail(name))
        return read

    def test_a_netbox_id_wins_then_the_local_uid(self, inventory):
        assert G._identity_for_ip("192.0.2.1") == "nb:41"
        assert G._identity_for_ip("192.0.2.2") == "uid:abc"

    def test_a_device_with_neither_or_not_listed_has_none(self, inventory):
        assert G._identity_for_ip("192.0.2.3") == ""
        assert G._identity_for_ip("192.0.2.99") == ""

    def test_a_named_list_reads_that_lists_inventory(self, inventory):
        assert G._identity_for_ip("192.0.2.1", "other") == "uid:in-other"
        assert inventory == ["other.csv"]

    def test_an_unreadable_inventory_is_none_never_a_raise(self, monkeypatch):
        def boom(path):
            raise OSError("unreadable")
        monkeypatch.setattr("modules.device.get_current_device_list",
                            lambda: ("active", "active.csv"))
        monkeypatch.setattr("modules.device.load_saved_devices", boom)
        assert G._identity_for_ip("192.0.2.1") == ""


class TestFindingAGolden:
    """The chain: the manifest by identity, then by address, then the legacy scan, then none."""

    @pytest.fixture
    def repo(self, tmp_path, monkeypatch, legacy_dir):
        repo = tmp_path / "repo"
        (repo / "golden").mkdir(parents=True)
        monkeypatch.setattr(G, "_nsot_repo_dir", lambda: str(repo))
        monkeypatch.setattr(G, "_identity_for_ip", lambda ip, list_name="": {
            "192.0.2.1": "uid:r1", "192.0.2.5": "uid:moved"}.get(ip, ""))
        G._LEGACY_SCAN_WARNED.clear()
        return repo

    def _golden(self, repo, name, identity, ip):
        path = repo / "golden" / f"{name}.cfg"
        path.write_text(f"hostname {name}\n", encoding="utf-8")
        M.upsert_device(str(repo), identity, name, ip, golden=f"golden/{name}.cfg")
        return str(path)

    def test_by_identity_when_the_manifests_address_is_stale(self, repo):
        """The device moved address outside the tool: only its identity still finds it."""
        want = self._golden(repo, "r1", "uid:r1", "192.0.2.100")
        assert G._find_golden_config_file("192.0.2.1") == want

    def test_by_address_when_the_identity_is_unknown(self, repo):
        want = self._golden(repo, "r2", "uid:r2", "192.0.2.2")
        assert G._find_golden_config_file("192.0.2.2") == want

    def test_an_identity_whose_file_is_gone_falls_to_the_address(self, repo):
        self._golden(repo, "old", "uid:moved", "192.0.2.50")
        os.remove(repo / "golden" / "old.cfg")
        want = self._golden(repo, "new", "uid:new", "192.0.2.5")
        assert G._find_golden_config_file("192.0.2.5") == want

    def test_the_manifest_first_even_when_a_legacy_file_names_the_address(
            self, repo, legacy_dir):
        _legacy(legacy_dir, "r1.cfg", "192.0.2.1")
        want = self._golden(repo, "r1", "uid:r1", "192.0.2.1")
        assert G._find_golden_config_file("192.0.2.1") == want

    def test_the_legacy_store_last_warned_once_per_device(self, repo, legacy_dir, caplog):
        want = _legacy(legacy_dir, "r7.cfg", "192.0.2.7", host="r7")
        with caplog.at_level(logging.WARNING, logger="modules.goldens"):
            assert G._find_golden_config_file("192.0.2.7") == want
            assert G._find_golden_config_file("192.0.2.7") == want
        warned = [r for r in caplog.records if "legacy header scan" in r.getMessage()]
        assert len(warned) == 1 and "192.0.2.7" in warned[0].getMessage()

    def test_nowhere_is_none_and_warns_nothing(self, repo, caplog):
        with caplog.at_level(logging.WARNING, logger="modules.goldens"):
            assert G._find_golden_config_file("192.0.2.99") is None
        assert not caplog.records

    def test_an_unreadable_manifest_still_reaches_the_legacy_store(
            self, repo, legacy_dir, monkeypatch):
        want = _legacy(legacy_dir, "r1.cfg", "192.0.2.1")

        def broken(*a, **k):
            raise ValueError("manifest unreadable")
        monkeypatch.setattr(M, "find_by_identity", broken)
        assert G._find_golden_config_file("192.0.2.1") == want
