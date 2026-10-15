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

**The text is v2's since P7-19 (2026-10-15)**: the screen and the manual page one level down
(its "How does this work?"), as served (tests/interface_pages.py). Today's Git and NetBox
tabs, on the index that goes at cutover, were read until then. Save's home is Devices › Save
and the capture the device page's; the import's is Source of truth › NetBox. Today's NetBox
tab also said "the one part that needs a live session is CDP/LLDP neighbour discovery"; no
caller passes the status the live neighbour read needs, so no import opens one, and v2 says
no device is reached (`test_no_import_asks_for_a_live_session`).
"""

import ast
import inspect
import os
import re

import pytest

from tests.astcheck import calls_in, tree_of

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _main_text(html: str) -> str:
    """The words of a page's <main>: no navigation, no script, tags dropped."""
    m = re.search(r"<main\b.*?</main>", html, re.S)
    assert m, "the page has no <main>"
    block = re.sub(r"<script[^>]*>.*?</script>", "", m.group(0), flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block))


def _texts(*urls) -> str:
    from tests import interface_pages

    pages = interface_pages.pages()["v2"]
    missing = [u for u in urls if u not in pages]
    assert not missing, f"not in the interface's pages: {missing}"
    return " ".join(_main_text(pages[u]) for u in urls)


@pytest.fixture(scope="module")
def save_screens():
    """Devices › Save, and the manual's Save, Capture and Baselines pages."""
    return _texts("/v2/devices/save", "/v2/help/save", "/v2/help/capture",
                  "/v2/help/baselines")


@pytest.fixture(scope="module")
def netbox_screens():
    """Source of truth › NetBox, and the manual's NetBox and Import into NetBox pages."""
    return _texts("/v2/netbox", "/v2/help/netbox", "/v2/help/netbox-import")


class TestTheSaveScreensDescribeWhatSaveDoes:
    def test_save_all_really_commits_in_one_call(self):
        """The claim, checked at the source. Save All is now the whole-fleet
        capture (7.1 step 4): one `save_golden` call, after the confirm."""
        import routes.golden as golden

        # `apply_captures` is the apply both routes call (the v2 device page, 7.3).
        assert calls_in(golden.apply_captures, "save_golden") == 1
        assert calls_in(golden.apply_captures, "write_and_stage") == 0

    def test_devices_save_records_the_batch_in_one_commit(self):
        """Devices › Save says "one commit for the batch": one `save_golden` call in its run,
        outside any loop, carrying every device read."""
        from modules.nsot import save_op

        tree = tree_of(save_op.run)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and "save_golden" in ast.unparse(n.func)]
        assert len(calls) == 1, [ast.unparse(c) for c in calls]
        loops = [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))]
        assert not any(calls[0] in list(ast.walk(loop)) for loop in loops)

    def test_nothing_says_it_stages(self, save_screens):
        assert "stages device configs" not in save_screens

    def test_it_says_one_commit_once_you_confirm(self, save_screens):
        """It committed on one click until C89: now it previews first."""
        assert "one commit for the batch" in save_screens
        assert "After the person confirms" in save_screens
        assert "commits by itself" not in save_screens

    def test_it_says_a_baseline_needs_intent_too(self, save_screens):
        """C89 (c): coverage alone no longer earns one. The operator found the
        tab still saying "when it covers the inventory" after step 4."""
        assert "every one matches its committed intent" in save_screens
        assert "Intent-Match: no" in save_screens

    def test_it_offers_no_manual_commit(self, save_screens):
        """It said "Commit here for infra/ files" for a manual commit C104
        removed (2026-09-27)."""
        assert "Commit here" not in save_screens and "infra/" not in save_screens

    def test_the_explanation_is_one_level_down(self):
        """The presentation rule (the operator, 2026-09-29): the screen answers
        what it does in a sentence, and Save's rules are one level down, behind its
        (i), never a paragraph read every visit."""
        from tests import interface_pages

        page = interface_pages.pages()["v2"]["/v2/devices/save"]
        assert 'href="/v2/help/save"' in page

    def test_the_route_docstring_matches_the_screens(self):
        import routes.golden as golden

        doc = inspect.getdoc(golden.capture_apply) or ""
        assert "One commit" in doc and "READ AGAIN" in doc
        assert "stage the changes" not in doc


class TestTheNetBoxScreenDescribesWhatImportDoes:
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

    def test_no_import_asks_for_a_live_session(self):
        """The import's one live read, CDP and LLDP neighbours, runs only for devices a
        `status_cache` the caller passes says are online. No caller passes one, so no import
        reaches a device, which is what v2 says. Found by parsing every call of the two
        entry points in the product; a call passing it is planted to show the scan sees one."""
        from tests.source_index import tracked

        def calls(text):
            out = []
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(
                        node.func, "attr", "")) in ("sync_list_to_netbox",
                                                    "sync_all_lists_to_netbox"):
                    name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                    limit = 2 if name == "sync_list_to_netbox" else 1
                    asks = (len(node.args) > limit
                            or any(k.arg == "status_cache" for k in node.keywords))
                    out.append((name, asks))
            return out

        found = []
        for path in tracked("modules", "routes", suffix=".py") + [os.path.join(ROOT, "app.py")]:
            if path.endswith("netbox_client.py"):
                continue                 # the definitions, and the all-lists fan-out within
            found += calls(open(path, encoding="utf-8").read())
        # 6 calls measured 2026-10-15: modules/netbox_ops.py's four, routes/netbox_safety.py's two.
        assert len(found) >= 6, found
        assert not [c for c in found if c[1]], found
        planted = "sync_list_to_netbox('Lab', devs, status_cache=STATUS)"
        assert calls(planted) == [("sync_list_to_netbox", True)]

    def test_the_screens_no_longer_claim_ssh(self, netbox_screens):
        assert "scanned via SSH" not in netbox_screens
        assert "connects to every online device" not in netbox_screens

    def test_the_screens_say_it_reads_the_committed_golden_and_reaches_no_device(
            self, netbox_screens):
        """What made an offline device importable, said as v2 says it: the import is built
        from each device's committed golden, and no device is reached."""
        assert "from their committed golden configs" in netbox_screens
        assert "nothing is sent to a device" in netbox_screens
        assert "no device is reached" in netbox_screens
        assert "Unreachable devices are reported but not created" not in netbox_screens

    def test_the_screens_name_the_real_skip_reason(self, netbox_screens):
        assert "A device with no golden" in netbox_screens
        assert "not imported" in netbox_screens


class TestTheRemovalClaimIsPrecise:
    def test_removal_requires_both_tag_and_record(self):
        from modules import netbox_client

        source = inspect.getsource(netbox_client.remove_list_from_netbox)
        assert "created_ids" in source or "created_id" in source

    def test_the_screens_say_both(self, netbox_screens):
        assert "tagged AND in" in netbox_screens
        assert "only ever deletes those" not in netbox_screens

    def test_the_screens_say_untagged_objects_are_left_alone(self, netbox_screens):
        assert "left alone, treated as a person" in netbox_screens


class TestTheDirectionIsStated:
    """"NetBox acts as the network source of truth" sat directly above a
    description of pushing into it, which reads as a contradiction to anyone
    who has read the plan."""

    def test_the_screen_says_which_way_it_goes(self, netbox_screens):
        assert "devices into NetBox from their committed golden" in netbox_screens
        assert "acts as the network source of truth" not in netbox_screens
