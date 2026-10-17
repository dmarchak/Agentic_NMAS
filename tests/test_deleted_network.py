"""A deleted network stays deleted: its Settings page says so with no actions, every write naming
it is refused, and no read makes its folder again (C1029, W2's B7; C1074).

W2 (2026-10-17, step 40, screenshot 39): after W2 walk's delete, `/v2/settings/network/W2%20walk`
drew every card with Save and Preview, and "Make W2 walk standalone…", while Default read
"0 networks inherit". Three seconds after the delete a READ (Needs attention's drift row,
`drift_check._state_file` → `network_store.own(create=True)` → `get_list_data_dir`) had made
`lists/w2_walk/` again, empty; `listref.exists` counts a folder on disk as a network, so every
guard asking it let the page draw, and a switch there wrote the folder's settings.

On the real app over a temporary store with four networks (tests/test_settings_v2's
`networks`), Branch deleted through the real preview and confirm.
"""

import json
import os
import re

import pytest

from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

GROUP = "grafana"


def _flat(r):
    return re.sub(r"\s+", " ", r.get_data(as_text=True))


def _main(html):
    m = re.search(r'<main id="main"[^>]*>(.*)</main>', html, re.S)
    assert m, "no main"
    return m.group(1)


@pytest.fixture
def gone(networks):  # noqa: F811
    """Branch, deleted through the real preview and confirm."""
    c = networks["client"]
    pv = _flat(c.post("/v2/settings/network/Branch/delete/preview",
                      headers={"HX-Request": "true"}))
    fp = re.search(r'name="fingerprint" value="([0-9a-f]+)"', pv).group(1)
    r = c.post("/v2/settings/network/Branch/delete",
               data={"typed": "Branch", "fingerprint": fp}, headers={"HX-Request": "true"})
    assert r.status_code == 200 and "Branch is deleted:" in _flat(r)
    networks["folder"] = networks["dir"] / "lists" / "branch"
    networks["moved"] = sorted((networks["dir"] / "lists_removed").glob("branch-*"))
    assert not networks["folder"].exists() and len(networks["moved"]) == 1
    return networks


def _left(n):
    """Every file and folder under lists/branch, which must not exist."""
    f = n["folder"]
    if not f.exists():
        return None
    return sorted(os.path.relpath(os.path.join(d, x), f)
                  for d, subs, files in os.walk(f) for x in subs + files) or ["(empty folder)"]


class TestTheDeletedNetwork_sPage:
    def test_it_says_when_by_whom_and_where_its_data_is(self, gone):
        from modules import csp

        r = gone["client"].get("/v2/settings/network/Branch")
        html = _flat(r)
        assert r.status_code == 410 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        main = _main(html)
        assert "<strong>Branch was deleted</strong>" in main, main[:800]
        assert f"lists_removed/{gone['moved'][0].name}" in main
        assert " UTC)" in main and 'datetime="20' in main
        rec = [json.loads(l) for l in (gone["dir"] / "settings_record.jsonl")
               .read_text().splitlines()][-1]
        assert rec["kind"] == "network_delete" and rec["folder"] == \
            f"lists_removed/{gone['moved'][0].name}", "the delete's record names the folder"
        assert rec["actor_label"] and f"by {rec['actor_label']}" in main

    def test_it_offers_no_action(self, gone):
        """Only the scope bar's navigation: no card, no form, nothing that posts, no switch."""
        main = _main(_flat(gone["client"].get("/v2/settings/network/Branch")))
        page = main.split('id="network-deleted"', 1)
        assert len(page) == 2
        for absent in ("<form", "hx-post", 'method="post"', "set-card", "Save", "Preview",
                       "standalone", "Delete Branch", "Inventory source", 'class="tabs"'):
            assert absent not in main, absent
        assert "<b>Branch</b><small>deleted: it has left every page</small>" in main

    def test_another_network_s_query_still_draws_the_deleted_page(self, gone):
        """The picker reloaded the path with Default's name (W2): the path's network is the
        page's, and it is deleted."""
        r = gone["client"].get("/v2/settings/network/Branch?list=Default")
        assert r.status_code == 410 and "<strong>Branch was deleted</strong>" in _flat(r)

    def test_a_name_that_never_was_a_network_is_still_refused(self, gone):
        r = gone["client"].get("/v2/settings/network/Nowhere")
        assert r.status_code == 404 and r.get_json()["unknown_list"] == "Nowhere"


def _writes(app):
    """Every v2 write whose PATH names a network (`<list_name>`), filled: the population a
    page drawn before the delete can still send. Found from the app's routes, not listed."""
    out = []
    for rule in app.url_map.iter_rules():
        if "POST" not in rule.methods or not rule.rule.startswith("/v2/") or \
                "list_name" not in rule.arguments:
            continue
        url = rule.rule
        for arg in rule.arguments:
            url = re.sub(rf"<(?:[a-z_]+:)?{arg}>",
                         {"list_name": "Branch", "group": GROUP}.get(arg, "x"), url)
        out.append((rule.endpoint, url))
    return sorted(out)


class TestEveryWriteNamingItIsRefused:
    def test_the_population_is_every_settings_write(self, gone):
        import app as A

        got = dict(_writes(A.app))
        for endpoint in ("settings_v2.group_switch", "settings_v2.group_save",
                         "settings_v2.mode_switch", "settings_v2.network_source_apply",
                         "settings_v2.network_source_preview", "settings_v2.network_delete"):
            assert endpoint in got, endpoint
        assert len(got) >= 9, sorted(got)          # 9 measured 2026-10-17

    def test_each_is_refused_by_name_and_writes_nothing(self, gone):
        """A stale page's Save, switch, mode, source or delete: refused before its view, naming
        Branch and that it was deleted. Before C1029 a switch or mode with ANY fingerprint made
        `lists/branch/` again (`apply_group` and `apply_mode` make the folder before checking)."""
        import app as A

        c = gone["client"]
        form = {"to": "own", "fingerprint": "0" * 16, "loaded": "{}", "typed": "Branch",
                "source": "local", GROUP + "_url": "http://192.0.2.99:3000"}
        answered = {}
        for endpoint, url in _writes(A.app):
            r = c.post(url, data=form, headers={"HX-Request": "true"})
            answered[endpoint] = (r.status_code, (r.get_json(silent=True) or {}).get("error", ""))
            assert _left(gone) is None, f"{endpoint} made lists/branch: {_left(gone)}"
        wrong = {e: a for e, a in answered.items()
                 if a[0] != 404 or "'Branch' was deleted" not in a[1]
                 or "lists_removed/branch-" not in a[1]}
        assert wrong == {}, wrong


class TestNoReadMakesItsFolder:
    """C1074: a read never creates a network's folder; and the one accessor that creates
    (`config.get_list_data_dir`) never makes a deleted network's, whoever asks."""

    def test_the_drift_record_s_reads_create_nothing(self, gone):
        from modules import drift_check as D

        assert D._load_state("Branch") == {}
        assert D._is_disabled("Branch") is False
        assert _left(gone) is None, f"the drift reads made lists/branch: {_left(gone)}"

    def test_needs_attention_s_drift_row_creates_nothing(self, gone):
        """The read W2 saw: Needs attention's drift source, for the deleted network."""
        from modules import attention
        from modules import drift_check as D

        # A checker of its own (its constructor starts nothing), asked as the page asks it.
        got = attention.drift_source(status=lambda: D.DriftChecker().status("Branch"))
        assert got is not None
        assert _left(gone) is None, f"the drift row made lists/branch: {_left(gone)}"

    def test_the_inventory_source_s_read_creates_nothing(self, gone):
        """`source_config.load` runs under every read of a network's inventory: it reads, and
        only `save` makes the folder, for a deleted network and for a name no network has."""
        from modules.inventory import source_config

        assert source_config.load("Branch")["source"] == "local"
        assert _left(gone) is None, f"source_config.load made lists/branch: {_left(gone)}"
        assert source_config.get_source("Nowhere") == "local"
        assert not (gone["dir"] / "lists" / "nowhere").exists(), \
            "source_config.load made a folder for a name no network has"

    @pytest.mark.parametrize("ask", ["accessor", "own_create", "resolve"])
    def test_the_accessor_never_makes_a_deleted_network_s_folder(self, gone, ask):
        """The shape: whoever asks the one accessor that creates, read or write, a deleted
        network's folder is not made. (A writer that makes its own folder, `write_atomic` or
        `os.makedirs`, does not ask it: v2's writes naming the network are refused before their
        view, `TestEveryWriteNamingItIsRefused`.)"""
        from modules import config, network_store
        from modules.nsot import listref

        {"accessor": lambda: config.get_list_data_dir("Branch"),
         "own_create": lambda: network_store.own("Branch", "x.json", create=True),
         "resolve": lambda: listref.resolve("Branch")}[ask]()
        assert _left(gone) is None, f"{ask} made lists/branch: {_left(gone)}"

    def test_a_network_never_deleted_still_gets_its_folder(self, gone):
        from modules import config

        assert os.path.isdir(config.get_list_data_dir("Lab-3"))
        assert os.path.isdir(config.get_list_data_dir("Brand New"))


class TestAFolderLeftAtItsPath:
    """The host's state after C1074: `lists/w2_walk/` made again, empty. It must not bring the
    network back (the page drew live because `listref.exists` counted it)."""

    def test_it_is_not_a_network_and_its_page_says_deleted(self, gone):
        from modules.nsot import listref

        gone["folder"].mkdir()
        assert listref.exists("Branch") is False
        r = gone["client"].get("/v2/settings/network/Branch")
        assert r.status_code == 410 and "<strong>Branch was deleted</strong>" in _flat(r)
        r = gone["client"].post("/v2/settings/network/Branch/mode",
                                data={"to": "standalone", "fingerprint": "0" * 16},
                                headers={"HX-Request": "true"})
        assert r.status_code == 404 and "'Branch' was deleted" in r.get_json()["error"]
        assert _left(gone) == ["(empty folder)"], "the refused write wrote nothing there"


class TestTheNameCanBeMadeAgain:
    def test_a_new_network_of_the_deleted_name_is_live(self, gone):
        c = gone["client"]
        pv = _flat(c.post("/v2/settings/networks/new/preview", data={"name": "Branch"},
                          headers={"HX-Request": "true"}))
        fp = re.search(r'name="fingerprint" value="([0-9a-f]+)"', pv).group(1)
        r = c.post("/v2/settings/networks/new", data={"name": "Branch", "fingerprint": fp},
                   headers={"HX-Request": "true"})
        assert r.status_code == 200 and "Created Branch" in _flat(r), _flat(r)[:600]
        assert gone["folder"].is_dir()
        r = c.get("/v2/settings/network/Branch")
        assert r.status_code == 200 and 'id="card-' + GROUP + '"' in _flat(r)
        assert "was deleted" not in _main(_flat(r))
