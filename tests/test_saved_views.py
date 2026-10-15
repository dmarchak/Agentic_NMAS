"""History › Query's saved views (C667; board A's "Saved by your team", board B's "Save this
view…"; modules/saved_views.py): a question as someone asked it, saved for the network with a
title, who and when, pinned or not.

- the store: absent and unreadable are different states; a title is needed; only a History ›
  Query address is kept, and only the keys a question reads; pinned views come first; a
  removal takes only the link; an unreadable store refuses every write and keeps its bytes;
  each change is recorded;
- the routes: Save this view… asks a title in place and saves the page's own address, as the
  verified person; pin and remove redraw the list and say what they did out of band (the list
  redraws on `saved_views`, C656), and a refusal declares no change; History lists each act.
"""

import json
import os
import re

import pytest

from modules import saved_views as SV

ME = "p@example.invalid"


@pytest.fixture
def lst(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: SimpleNamespace(name=name, data_dir=str(tmp_path)))
    return tmp_path


class TestTheStore:
    def test_absent_then_saved_pinned_and_removed(self, lst):
        assert SV.read("Lab") == {"state": "absent", "views": [], "error": ""}
        a = SV.save("Lab", "s3 discards, last 30 days",
                    "/v2/history/query/metric/errors?d=s3&range=30d&list=Lab", ME)
        b = SV.save("Lab", "Core CPU", "/v2/history/query/metric/cpu?range=180d", ME)
        assert a["ok"] and b["ok"]
        assert a["view"]["address"] == "/v2/history/query/metric/errors?d=s3&range=30d", \
            "the network is the page's, never a key of the view"
        assert [v["title"] for v in SV.read("Lab")["views"]] == ["Core CPU",
                                                                 "s3 discards, last 30 days"]
        assert SV.pin("Lab", a["view"]["id"], True, ME)["ok"]
        views = SV.read("Lab")["views"]
        assert views[0]["title"] == "s3 discards, last 30 days" and views[0]["pinned"] is True
        gone = SV.remove("Lab", b["view"]["id"], ME)
        assert gone["ok"] and gone["view"]["title"] == "Core CPU"
        assert [v["title"] for v in SV.read("Lab")["views"]] == ["s3 discards, last 30 days"]
        log = [json.loads(l) for l in (lst / SV.LOG).read_text().splitlines()]
        assert [(r["action"], r["title"]) for r in log] == [
            ("saved", "s3 discards, last 30 days"), ("saved", "Core CPU"),
            ("pinned", "s3 discards, last 30 days"), ("removed", "Core CPU")]
        assert all(r["actor"] == ME for r in log)

    @pytest.mark.parametrize("title, address, words", [
        ("", "/v2/history/query/metric/cpu", "give the view a title"),
        ("x" * 81, "/v2/history/query/metric/cpu", "at most 80"),
        ("Theirs", "https://elsewhere.example/v2/history/query/metric/cpu", "not another site"),
        ("Devices", "/v2/devices?list=Lab", "/v2/devices is not a History › Query question"),
        ("Odd", "/v2/history/query/metric/cpu?d=r1&reveal=1", "does not read: reveal"),
    ], ids=["no-title", "long-title", "another-site", "not-a-question", "unknown-key"])
    def test_what_a_view_cannot_be_is_refused_by_name(self, lst, title, address, words):
        got = SV.save("Lab", title, address, ME)
        assert not got["ok"] and words in got["error"]
        assert SV.read("Lab")["state"] == "absent"

    def test_an_unknown_view_is_refused_naming_it(self, lst):
        got = SV.pin("Lab", "abc123", True, ME)
        assert not got["ok"] and "no saved view 'abc123'" in got["error"]

    def test_an_unreadable_store_refuses_every_write_and_keeps_its_bytes(self, lst):
        (lst / SV.STORE).write_text("{not json")
        assert SV.read("Lab")["state"] == "unreadable"
        got = SV.save("Lab", "Core CPU", "/v2/history/query/metric/cpu", ME)
        assert not got["ok"] and "nothing was written" in got["error"]
        assert (lst / SV.STORE).read_text() == "{not json"

    def test_the_network_keeps_at_most_its_bound(self, lst, monkeypatch):
        monkeypatch.setattr(SV, "MAX_VIEWS", 2)
        for n in range(2):
            assert SV.save("Lab", f"v{n}", "/v2/history/query/metric/cpu", ME)["ok"]
        got = SV.save("Lab", "v2", "/v2/history/query/metric/cpu", ME)
        assert not got["ok"] and "holds 2 saved views, the most it keeps" in got["error"]


@pytest.fixture
def web(tmp_path, monkeypatch):
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr(SV, "_path", lambda name: str(tmp_path / "lab" / SV.STORE))
    import app as A
    return {"client": A.app.test_client(), "dir": tmp_path / "lab"}


class TestTheRoutes:
    def test_save_this_view_asks_a_title_then_saves_the_page_s_address(self, web):
        c = web["client"]
        where = "/v2/history/query/metric/errors?d=s3&range=30d&list=Lab"
        form = c.get("/v2/history/query/views/save", query_string={"address": where,
                                                                   "list": "Lab"})
        html = form.get_data(as_text=True)
        assert 'name="title"' in html and f'value="{where.replace("&", "&amp;")}"' in html
        r = c.post("/v2/history/query/views", data={"list": "Lab", "address": where,
                                                    "title": "s3 discards"})
        assert r.status_code == 200 and "saved_views" in r.headers.get("X-NMAS-Invalidates", "")
        assert "Saved as &ldquo;s3 discards&rdquo;" in r.get_data(as_text=True)
        stored = json.loads((web["dir"] / SV.STORE).read_text())["views"][0]
        assert stored["by"] == "test-person@example.invalid"
        assert stored["address"] == "/v2/history/query/metric/errors?d=s3&range=30d"

    def test_a_refused_save_says_why_in_place_and_declares_no_change(self, web):
        r = web["client"].post("/v2/history/query/views",
                               data={"list": "Lab", "address": "/v2/devices", "title": "x"})
        assert r.status_code == 400 and "X-NMAS-Invalidates" not in r.headers
        assert "Not saved: /v2/devices is not a History › Query question" in \
            r.get_data(as_text=True)
        assert not (web["dir"] / SV.STORE).exists()

    def test_the_query_tab_lists_them_pinned_first_with_who_and_when(self, web):
        a = SV.save("Lab", "Older", "/v2/history/query/metric/cpu", ME)["view"]
        SV.save("Lab", "Newer", "/v2/history/query/syslog?d=r4", ME)
        SV.pin("Lab", a["id"], True, ME)
        html = web["client"].get("/v2/history?tab=query&list=Lab").get_data(as_text=True)
        assert re.findall(r'<a href="[^"]+"><strong>([^<]+)</strong></a>', html)[:2] == \
            ["Older", "Newer"]
        assert 'href="/v2/history/query/syslog?d=r4&amp;list=Lab"' in html
        assert f"saved by {ME}" in html and "pinned</span>" in html
        assert 'hx-trigger="nmas:saved_views from:body"' in html

    def test_pin_and_remove_redraw_the_list_and_say_what_they_did_out_of_band(self, web):
        v = SV.save("Lab", "Core CPU", "/v2/history/query/metric/cpu", ME)["view"]
        c = web["client"]
        r = c.post(f"/v2/history/query/views/{v['id']}/pin", data={"list": "Lab", "pinned": "1"})
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "saved_views" in r.headers["X-NMAS-Invalidates"]
        result = html.split('id="hq-views-result"')[1]
        assert 'hx-swap-oob="true"' in result and "Pinned &ldquo;Core CPU&rdquo; for everyone" \
            in result
        ask = c.get(f"/v2/history/query/views/remove?id={v['id']}&list=Lab").get_data(as_text=True)
        assert "Removes the saved link only; the history it asks is untouched." in ask
        r = c.post(f"/v2/history/query/views/{v['id']}/remove", data={"list": "Lab"})
        assert "only the saved link went; the history it asked is untouched" in \
            r.get_data(as_text=True)
        assert SV.read("Lab")["views"] == []

    def test_an_unknown_view_is_refused_with_no_change_declared(self, web):
        r = web["client"].post("/v2/history/query/views/nope/remove", data={"list": "Lab"})
        assert r.status_code == 409 and "X-NMAS-Invalidates" not in r.headers
        assert "no saved view &#39;nope&#39;" in r.get_data(as_text=True)

    def test_board_b_and_board_c_offer_save_this_view(self, web, monkeypatch):
        from tests.test_history_query import _Grafana
        from modules import device_page
        monkeypatch.setattr(device_page, "_cached", lambda name, list_name=None: (
            {"datasources": [{"uid": "prom", "type": "prometheus", "isDefault": True}]},
            "2026-10-11T09:00:00Z", ""))
        monkeypatch.setattr(device_page, "grafana_client", lambda list_name: _Grafana())
        html = web["client"].get("/v2/history/query/metric/errors?d=s3&list=Lab") \
            .get_data(as_text=True)
        link = re.search(r'<a class="btn" href="(/v2/history/query/views/save\?address=[^"]+)"',
                         html)
        assert link and "d%3Ds3" in link.group(1) and ">Save this view…</a>" in html
        ask = web["client"].get("/v2/history/query/metric/ask").get_data(as_text=True)
        assert "Save this view…" not in ask, "nothing asked, nothing to save"

    def test_history_lists_each_act(self, web, monkeypatch):
        from types import SimpleNamespace
        from modules import history_sources as HS
        v = SV.save("Lab", "Core CPU", "/v2/history/query/metric/cpu", ME)["view"]
        SV.remove("Lab", v["id"], ME)
        ctx = {"ref": SimpleNamespace(name="Lab", data_dir=str(web["dir"])), "device": "",
               "since": "", "limit": 50}
        monkeypatch.setattr(HS, "_recent", lambda ctx, at: True)
        got = HS.saved_views(ctx)
        words = [e.get("what") or e.get("summary") or json.dumps(e) for e in got["events"]]
        assert len(words) == 2 and "removed" in json.dumps(got["events"][0])


@pytest.fixture
def two(tmp_path, monkeypatch):
    """Two networks, Lab (the ACTIVE one) and Other, each its own folder."""
    from types import SimpleNamespace
    for n in ("Lab", "Other"):
        (tmp_path / n).mkdir()
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name in ("Lab", "Other"))
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: SimpleNamespace(name=name, data_dir=str(tmp_path / name)))
    monkeypatch.setattr("modules.nsot.listref.active",
                        lambda: SimpleNamespace(name="Lab", data_dir=str(tmp_path / "Lab")))
    import app as A
    return {"client": A.app.test_client(), "dir": tmp_path}


def _titles(name):
    return [v["title"] for v in SV.read(name)["views"]]


class TestOffTheActiveNetwork:
    """C838: the saved views' writes act on the network their FORM names (the page's), never
    the active one; a form and an address naming two networks is refused naming both."""

    def test_saved_pinned_and_removed_on_the_network_the_form_names(self, two):
        c = two["client"]
        form = c.get("/v2/history/query/views/save",
                     query_string={"address": "/v2/history/query/metric/cpu", "list": "Other"})
        assert '<input type="hidden" name="list" value="Other">' in form.get_data(as_text=True)
        r = c.post("/v2/history/query/views", data={"list": "Other", "title": "Core CPU",
                                                    "address": "/v2/history/query/metric/cpu"})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert _titles("Other") == ["Core CPU"] and _titles("Lab") == [], \
            "the save landed on the active network, not the one the form named"
        v = SV.read("Other")["views"][0]
        r = c.post(f"/v2/history/query/views/{v['id']}/pin", data={"list": "Other",
                                                                   "pinned": "1"})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert SV.read("Other")["views"][0]["pinned"] is True
        assert 'action="/v2/history/query/views/' in r.get_data(as_text=True)
        assert '<input type="hidden" name="list" value="Other">' in r.get_data(as_text=True), \
            "the list redrawn after the pin is not the network acted on"
        r = c.post(f"/v2/history/query/views/{v['id']}/remove", data={"list": "Other"})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert _titles("Other") == []

    @pytest.mark.parametrize("path", ["/v2/history/query/views?list=Lab",
                                      "/v2/history/query/views/{id}/pin?list=Lab",
                                      "/v2/history/query/views/{id}/remove?list=Lab"])
    def test_a_form_and_an_address_naming_two_networks_are_refused_naming_both(self, two,
                                                                               path):
        v = SV.save("Other", "Core CPU", "/v2/history/query/metric/cpu", ME)["view"]
        before = {n: (two["dir"] / n / SV.STORE).read_bytes()
                  if (two["dir"] / n / SV.STORE).exists() else b"" for n in ("Lab", "Other")}
        r = two["client"].post(path.format(id=v["id"]), data={
            "list": "Other", "pinned": "1", "title": "x",
            "address": "/v2/history/query/metric/cpu"})
        page = r.get_data(as_text=True)
        assert r.status_code == 409, (r.status_code, page[:300])
        assert "the form names the network &#39;Other&#39; and the page&#39;s address names " \
               "&#39;Lab&#39;" in page, page[:600]
        assert "X-NMAS-Invalidates" not in r.headers
        after = {n: (two["dir"] / n / SV.STORE).read_bytes()
                 if (two["dir"] / n / SV.STORE).exists() else b"" for n in ("Lab", "Other")}
        assert after == before, "a refused write changed a network's views"

    def test_a_network_that_does_not_exist_is_refused_naming_it(self, two):
        r = two["client"].post("/v2/history/query/views", data={
            "list": "Nowhere", "title": "x", "address": "/v2/history/query/metric/cpu"})
        assert r.status_code == 409
        assert "there is no network named &#39;Nowhere&#39;" in r.get_data(as_text=True)
        assert not (two["dir"] / "Nowhere").exists()
