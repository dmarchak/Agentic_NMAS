"""What a tab SAYS must be true of the code it calls.

Both descriptions were written from the design and never revisited, so each
described a flow that had since been replaced:

* the **Git tab** said "Save All Configs stages device configs … commit here
  to version the configs in Git". Phase 2 made `save_golden()` the single
  write path and one call one commit. Nothing is staged; the manual commit is
  for `infra/` and ad-hoc files. The route's own docstring said the same
  stale thing, which is how the tab text kept agreeing with something.
* the **NetBox tab** said importing "connects to every online device … pulls
  `show version`" and that "unreachable devices are reported but not created".
  Import reads the **saved golden config** and opens no SSH session at all --
  `_scan_device`, the SSH scanner, has no callers -- so an offline device *is*
  imported. That last sentence was wrong in the dangerous direction: it told
  the operator offline devices were skipped when they are not.

These tests check the claims against the code rather than against the text,
because the text agreeing with itself is exactly what happened for months.
"""

import inspect
import os
import re

import pytest

from tests.astcheck import calls_in

from tests.js_source import with_loaded_scripts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def page():
    import app as nmas

    return with_loaded_scripts(nmas.app.test_client().get("/").get_data(as_text=True))


def _pane(page, pane_id, end_marker):
    start = page.index('id="%s"' % pane_id)
    end = page.index(end_marker, start)
    block = re.sub(r"<script[^>]*>.*?</script>", "", page[start:end], flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", block))


@pytest.fixture(scope="module")
def git_tab(page):
    return _pane(page, "gitPane", "end Git tab pane")


@pytest.fixture(scope="module")
def netbox_tab(page):
    return _pane(page, "netboxPane", "end NetBox tab pane")


class TestTheGitTabDescribesWhatSaveAllDoes:
    def test_save_all_really_commits_in_one_call(self):
        """The claim, checked at the source."""
        import app as nmas

        assert calls_in(nmas.golden_configs_save_all, "save_golden") == 1
        assert calls_in(nmas.golden_configs_save_all, "write_and_stage") == 0

    def test_the_tab_no_longer_says_it_stages(self, git_tab):
        assert "stages device configs" not in git_tab

    def test_the_tab_says_it_commits_by_itself(self, git_tab):
        assert "commits by itself" in git_tab

    def test_the_tab_says_what_the_manual_commit_is_for(self, git_tab):
        """Otherwise the button looks redundant and gets used wrongly."""
        assert "infra/" in git_tab

    def test_the_route_docstring_matches_the_tab(self):
        import app as nmas

        doc = inspect.getdoc(nmas.golden_configs_save_all) or ""
        assert "ONE commit" in doc
        assert "stage the changes" not in doc


class TestTheNetBoxTabDescribesWhatImportDoes:
    def test_import_reads_golden_configs_not_ssh(self):
        """Against the IMPLEMENTATION. `sync_list_to_netbox` is a thin guard
        wrapper that delegates, so reading its source says nothing about what
        the import does."""
        from modules import netbox_client

        assert calls_in(netbox_client._sync_list_to_netbox_impl,
                        "_scan_device_from_golden") >= 1

    def test_the_ssh_scanner_is_gone(self):
        """Stage 3.3 deleted it. The test moved from "nothing calls it" to
        "it does not exist" -- 140 lines that only a reader could find.

        Restoring it means answering why a NetBox import should depend on
        device reachability, and why observed state should flow INTO the
        source of truth.
        """
        from modules import netbox_client

        # `not hasattr` subsumes "nothing calls it" -- a name that does not
        # exist cannot be called. The old `calls_in(..., "_scan_device") == 0`
        # is dropped rather than kept alongside it: two assertions where one
        # is implied by the other reads as two independent checks.
        assert not hasattr(netbox_client, "_scan_device")

    def test_the_golden_scanner_opens_no_session(self):
        from modules import netbox_client

        source = inspect.getsource(netbox_client._scan_device_from_golden)
        for opener in ("ConnectHandler", "get_connection", "send_command"):
            assert opener not in source, opener

    def test_a_device_without_a_golden_config_is_what_gets_skipped(self):
        from modules import netbox_client

        source = inspect.getsource(netbox_client._scan_device_from_golden)
        assert "No golden config saved" in source

    def test_the_tab_no_longer_claims_ssh(self, netbox_tab):
        assert "scanned via SSH" not in netbox_tab
        assert "connects to every online device" not in netbox_tab

    def test_the_tab_says_offline_devices_are_still_imported(self, netbox_tab):
        """The sentence that was wrong in the dangerous direction."""
        assert "offline device is still imported" in netbox_tab
        assert "Unreachable devices are reported but not created" not in netbox_tab

    def test_the_tab_names_the_real_skip_reason(self, netbox_tab):
        assert "no golden config saved" in netbox_tab.lower()

    def test_the_tab_still_names_the_one_live_session(self, netbox_tab):
        """CDP/LLDP genuinely needs one, so dropping the SSH claim entirely
        would replace one untruth with another."""
        assert "CDP/LLDP" in netbox_tab


class TestTheRemovalClaimIsPrecise:
    def test_removal_requires_both_tag_and_record(self):
        from modules import netbox_client

        source = inspect.getsource(netbox_client.remove_list_from_netbox)
        assert "created_ids" in source or "created_id" in source

    def test_the_tab_says_both(self, netbox_tab):
        assert "both" in netbox_tab.lower()
        assert "only ever deletes those" not in netbox_tab

    def test_the_tab_says_curated_objects_are_skipped(self, netbox_tab):
        assert "reported as skipped" in netbox_tab


class TestTheDirectionIsStated:
    """"NetBox acts as the network source of truth" sat directly above a
    description of pushing into it, which reads as a contradiction to anyone
    who has read the plan."""

    def test_the_tab_says_this_is_the_opposite_direction(self, netbox_tab):
        assert "opposite direction" in netbox_tab
