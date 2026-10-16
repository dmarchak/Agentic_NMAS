"""C487 (the operator, 2026-10-05): Needs attention for a second network filed Default's devices
under it, from a stale drift store: nine Critical "has drifted" rows naming Default's devices
from a run of 2026-08-30, "drift checking is switched off for throwaway, by nobody recorded" and
"the last drift check for throwaway is old (881 h)". The drift state's reader adopted the
installation-wide file (it predates per-network state) for ANY network with none of its own, and
wrote the copy into that network's folder.

The survey (every per-network store a reader or writer opens, and what it does when the network
has none of its own) found three more that wrote or acted outside the named network; each is
held here, on Default and Branch, Branch made through the real create path (C931):

- the drift state: a network with no run says "no drift check has run yet", writes nothing,
  and its first write holds only its own; only Default adopts the installation-wide file; a copy
  another network took before is not read as its own, and its next write drops it;
- Needs attention's per-network sources read the network the page names, not the
  installation's current list;
- a capture's queue item is closed in its own network's queue;
- a read of another network's golden runs no legacy rename in the active network's folder.
"""

import html as _html
import json
import os

import pytest

from tests.test_network_born_a_repository import _create, store  # noqa: F401 (the fixture)

#: Default's last run as the installation-wide file held it on the host (2026-08-30), and the
#: switch it recorded: disabled, by nobody.
LEGACY = {"disabled": True, "disabled_at": "2026-08-30T02:42:00Z", "disabled_by": None,
          "last_check_ts": 1756521551.0,
          "last_result": {"ok": True, "checked": 9, "inventory": 0, "drifted": 9,
                          "drifted_devices": [{"hostname": f"r{i}", "diff_lines": 4}
                                              for i in range(1, 6)]
                          + [{"hostname": f"s{i}", "diff_lines": 2} for i in range(1, 5)],
                          "triggered_by": "scheduled", "summary": "drift on all nine"}}


@pytest.fixture
def two(store):  # noqa: F811
    """Default and Branch (created on v2), and the installation-wide drift file Default held."""
    from modules import config

    _create(store, "Branch")
    legacy = os.path.join(config.DATA_DIR, "drift_state.json")
    with open(legacy, "w", encoding="utf-8") as fh:
        json.dump(LEGACY, fh)
    store["legacy"] = legacy
    store["branch_state"] = store["data"] / "lists" / "branch" / "drift_state.json"
    return store


def _status(name):
    from modules import drift_check as D

    return D.DriftChecker().status(name)


class TestTheDriftStateIsTheNetworksOwn:
    def test_a_network_with_no_run_has_none_yet_and_nothing_is_written(self, two):
        from modules import drift_check as D

        st = _status("Branch")
        assert st["last_run"] is None and st["disabled"] is False, st
        assert st["state"] == "idle"
        D.DriftChecker().next_ts("Branch")             # the scheduler's read
        assert not two["branch_state"].exists(), "a read wrote Default's state into Branch"

    def test_its_first_write_holds_only_its_own(self, two):
        from modules import drift_check as D

        D.set_disabled(False, actor="op@example.invalid", list_name="Branch")
        got = json.loads(two["branch_state"].read_text(encoding="utf-8"))
        assert "last_result" not in got and "migrated_from" not in got, got
        assert got["disabled"] is False

    def test_default_still_adopts_the_file_it_held(self, two):
        st = _status("Default")
        assert st["disabled"] is True
        assert st["last_run"]["summary"] == "drift on all nine"

    def test_a_copy_taken_before_is_not_read_as_the_networks_and_its_next_write_drops_it(
            self, two):
        """A network that adopted the file before this rule (the host's throwaway) holds the
        copy. Its own key written since (a person's switch) stays."""
        from modules import drift_check as D

        copy = dict(LEGACY, migrated_from=two["legacy"])
        two["branch_state"].write_text(json.dumps(copy), encoding="utf-8")
        st = _status("Branch")
        assert st["last_run"] is None and st["disabled"] is False, st
        D.set_disabled(True, actor="op@example.invalid", list_name="Branch")
        got = json.loads(two["branch_state"].read_text(encoding="utf-8"))
        assert "migrated_from" not in got and "last_result" not in got, got
        assert got["disabled"] is True and got["disabled_by"] == "op@example.invalid"

    def test_a_run_naming_another_network_is_not_this_ones(self, two):
        """The copy's other sign, when the installation file is gone."""
        os.remove(two["legacy"])
        two["branch_state"].write_text(json.dumps(
            {"last_check_ts": 5.0, "migrated_from": "x",
             "last_result": {"list": "Default", "drifted_devices": [{"hostname": "r1"}]}}),
            encoding="utf-8")
        assert _status("Branch")["last_run"] is None


class TestNeedsAttentionReadsThePagesNetwork:
    def _page(self, client, monkeypatch, url):
        from modules import attention

        monkeypatch.setattr(attention, "SOURCES", (attention.drift_source,))
        r = client.get(url)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        return _html.unescape(r.get_data(as_text=True))

    def test_the_second_network_says_no_drift_check_has_run_yet(self, two, monkeypatch):
        text = self._page(two["client"], monkeypatch, "/v2/attention?list=Branch")
        assert "No drift check has run yet for Branch" in text, text[:2000]
        for wrong in ("has drifted from its golden", "switched off for Branch", "is old"):
            assert wrong not in text, wrong
        assert not two["branch_state"].exists()

    def test_default_on_the_same_page_is_defaults(self, two, monkeypatch):
        text = self._page(two["client"], monkeypatch, "/v2/attention?list=Default")
        assert "r1 has drifted from its golden" in text
        assert "Drift checking is switched off for Default" in text


class TestACaptureClosesItsOwnNetworksItem:
    def test_mark_done_names_the_network_and_leaves_the_active_ones(self, two):
        from modules import approval_queue as Q

        branch = Q.add_approval(action_type=Q.DRIFT_ACTION, description="drift on tw-a",
                                device_hostname="tw-a", device_ip="192.0.2.61",
                                list_name="Branch")
        default = Q.add_approval(action_type=Q.DRIFT_ACTION, description="drift on r1",
                                 device_hostname="r1", device_ip="192.0.2.11",
                                 list_name="Default")
        assert Q.mark_done(branch, "captured", actor="op", list_name="Branch")["ok"]
        assert [e["id"] for e in Q.get_pending("Branch")] == []
        assert [e["id"] for e in Q.get_pending("Default")] == [default]


class TestAReadOfAnotherNetworkWritesNothingInTheActiveOne:
    def test_no_legacy_rename_in_the_active_networks_folder(self, two):
        from modules import goldens

        legacy = two["data"] / "lists" / "default" / "golden_configs"
        legacy.mkdir()
        (legacy / "192_0_2_11.cfg").write_text("! Golden config — r1 (192.0.2.11)\n",
                                                encoding="utf-8")
        before = sorted(os.listdir(legacy))
        goldens._golden_record("192.0.2.61", "Branch")
        assert sorted(os.listdir(legacy)) == before
        goldens._golden_record("192.0.2.11", "Default")     # the active list's own read does
        assert sorted(os.listdir(legacy)) == ["r1.cfg"]
