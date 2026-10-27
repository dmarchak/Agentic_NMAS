"""Build again (C1862): a kept evidence pack of an older schema than this release's built again
from the alert history as of its alert's time; the kept pack never rewritten; both findable by
their own ids; the newest drawn wherever one pack per alert is, and read by Explain from there;
every Explain answer naming the pack it read. modules/evidence_pack.py (`build_for_episode`'s
*rebuild_of*, `rebuilt_id`, `superseded`), modules/alert_history.py (`episode_of`),
routes/v2.py (`monitoring_alert_pack_rebuild`, `_pack_lineage`).

On tests/test_alert_history_packs.py's `history` (r2's heartbeat episode of 21 Oct from the
captured state history; Loki and Prometheus from their captures). The kept pack of an older
schema is the product's own Build evidence pack in the shape schema 4 kept (the walk's packs,
`ep-7607ab655cee9cd2e37c` for r1 and `ep-efbd328eb1a3800c5eea` for s1, were schema 4): the
same pack less the section schema 5 added (`concurrent`), its schema field 4, hashed again as
the builder hashes. A pack captured as its alert fired (no episode named) is matched to its
episode by the alert history's own matching.
"""
import json
import re
import os
import subprocess
import sys
import threading
import time
from html import unescape

import pytest

from modules import alert_history as H
from modules import evidence_pack as EP
from tests.test_ai_explain import world  # noqa: F401 (the fixture)
from tests.test_alert_history_packs import _episode, history  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HX = {"HX-Request": "true"}
WORDS = ("Build again with this release's evidence: other alerts, two-hop health, one id per "
         "device; the pack kept now stays")


def _as_schema_4(pack: dict) -> dict:
    """*pack* in the shape schema 4 kept it: no `concurrent` section, schema 4, hashed again."""
    old = json.loads(json.dumps(pack))
    old["sections"] = [s for s in old["sections"] if s["name"] != "concurrent"]
    old["schema"] = 4
    old.pop("hash", None)
    old["hash"] = EP.digest(old)
    return old


def _kept_four(e=None):
    """A schema-4 Build evidence pack for r2's episode, kept; the rows as kept."""
    e = e or _episode()
    old = _as_schema_4(EP.build_for_episode(e, actor="operator@example.com"))
    assert EP.record(old)["ok"]
    return old, EP.read()["rows"]


def _html(r):
    return unescape(r.get_data(as_text=True))


def _words(html: str) -> str:
    """The text a person reads: tags taken out, spaces as one."""
    return " ".join(re.sub(r"<[^>]+>", "", html).split())


class TestTheControl:
    def test_an_older_pack_offers_build_again_and_a_current_one_does_not(self, history):
        c = history["client"]
        old, _rows = _kept_four()
        html = _html(c.get(f"/v2/monitoring/alerts/pack/{old['id']}"))
        assert "Kept with schema 4; this release builds schema 5" in html
        assert WORDS in html and 'data-op="alert-evidence"' in html
        assert f'/v2/monitoring/alerts/pack/{old["id"]}/rebuild' in html
        assert "manual/alert-evidence#rebuild" in html or "alert-evidence#rebuild" in html
        new = EP.build_for_episode(_episode(), actor="operator@example.com")
        new["id"] = "ep-" + "0" * 20
        new.pop("hash")
        new["hash"] = EP.digest(new)
        assert EP.record(new)["ok"]
        now = _html(c.get(f"/v2/monitoring/alerts/pack/{new['id']}"))
        assert "Build again" not in now and "Kept with schema" not in now

    def test_one_whose_alert_the_history_does_not_hold_says_why_and_is_refused(self, history):
        c = history["client"]
        old = _as_schema_4(dict(EP.build_for_episode(_episode(), actor="operator@example.com"),
                                episode="0123456789abcdef0123"))
        assert EP.record(old)["ok"]
        html = _html(c.get(f"/v2/monitoring/alerts/pack/{old['id']}"))
        assert "Cannot be built again: the alert history holds no past alert this pack is of" \
            in html and WORDS not in html
        before = EP.read()["rows"]
        r = c.post(f"/v2/monitoring/alerts/pack/{old['id']}/rebuild", headers=HX)
        assert r.status_code == 404 and "holds no past alert this pack is of" in _html(r)
        assert EP.read()["rows"] == before

    def test_a_name_that_is_no_pack_id_is_refused(self, history):
        c = history["client"]
        r = c.post("/v2/monitoring/alerts/pack/not-a-pack/rebuild", headers=HX)
        assert r.status_code == 404 and "no evidence pack is named not-a-pack" in _html(r)
        r = c.post("/v2/monitoring/alerts/pack/ep-0123456789abcdef0123/rebuild", headers=HX)
        assert r.status_code == 404 and "is kept; nothing was built" in _html(r)
        assert EP.read()["state"] == "absent"


class TestBuildAgain:
    def test_the_new_pack_is_kept_beside_the_old_which_is_never_rewritten(self, history):
        c = history["client"]
        old, before = _kept_four()
        r = c.post(f"/v2/monitoring/alerts/pack/{old['id']}/rebuild", headers=HX)
        html = _html(r)
        assert r.status_code == 200, html
        assert r.headers.get("X-NMAS-Invalidates")
        rows = EP.read()["rows"]
        assert len(rows) == 2 and rows[0] == before[0], "the old pack, as it was kept"
        assert EP.intact(rows[0]) and rows[0]["schema"] == 4
        new = rows[1]
        assert new["id"] == EP.rebuilt_id(old["alert_key"]) == old["id"] + "-s5"
        assert new["schema"] == EP.SCHEMA == 5 and EP.intact(new)
        assert new["rebuilt_from"] == {"id": old["id"], "schema": 4,
                                       "built_at": old["replayed_at"], "hash": old["hash"]}
        assert "concurrent" in {s["name"] for s in new["sections"]}
        assert "concurrent" not in {s["name"] for s in rows[0]["sections"]}
        assert f"in place of pack {old['id']} (schema 4), which stays kept" in new["trigger"]
        assert f'data-pack="{new["id"]}"' in html
        assert f"Built again from pack {old['id']} (schema 4" in _words(html)
        assert "Other alerts in the network around the onset" in html

    def test_both_are_findable_and_the_newest_is_drawn_for_the_alert(self, history):
        c = history["client"]
        old, _rows = _kept_four()
        c.post(f"/v2/monitoring/alerts/pack/{old['id']}/rebuild", headers=HX)
        new_id = old["id"] + "-s5"
        assert EP.find(old["id"])[0]["schema"] == 4 and EP.find(new_id)[0]["schema"] == 5
        listed = _html(c.get("/v2/monitoring/alerts/history?range=all&show=all"))
        assert f"/v2/monitoring/alerts/pack/{new_id}" in listed
        assert f"/v2/monitoring/alerts/pack/{old['id']}\"" not in listed
        assert [p["id"] for p in EP.tab()["earlier"]] == [new_id]
        opened = _html(c.get(f"/v2/monitoring/alerts/pack/{old['id']}"))
        assert f"Built again as pack {new_id} (schema 5" in _words(opened)
        assert WORDS not in opened, "built again once: not offered again"

    def test_pressing_again_builds_nothing_and_a_current_pack_is_refused(self, history):
        c = history["client"]
        old, _rows = _kept_four()
        c.post(f"/v2/monitoring/alerts/pack/{old['id']}/rebuild", headers=HX)
        rows = EP.read()["rows"]
        again = c.post(f"/v2/monitoring/alerts/pack/{old['id']}/rebuild", headers=HX)
        assert again.status_code == 200 and f'data-pack="{old["id"]}-s5"' in _html(again)
        assert EP.read()["rows"] == rows
        r = c.post(f"/v2/monitoring/alerts/pack/{old['id']}-s5/rebuild", headers=HX)
        assert r.status_code == 409 and "is of schema 5, this release's (5)" in _html(r)
        assert EP.read()["rows"] == rows

    def test_a_pack_captured_as_its_alert_fired_is_matched_to_its_past_alert(self, history):
        """No episode named: the alert history's own matching (its alert's instance, begun in
        the episode's span) finds it."""
        e = _episode()
        live = EP.build(EP.episode_instance(e), store=e["store"], value_at="",
                        now=H.epoch(e["fired_at"]))
        old = _as_schema_4(live)
        assert "episode" not in old and EP.record(old)["ok"]
        got, _state, _err = H.episode_of(old)
        assert got is not None and got["id"] == e["id"]
        r = history["client"].post(f"/v2/monitoring/alerts/pack/{old['id']}/rebuild",
                                   headers=HX)
        assert r.status_code == 200, _html(r)
        assert EP.read()["rows"][-1]["episode"] == e["id"]

    def test_two_workers_pressing_at_once_build_one_pack(self, history, tmp_path):
        """Across processes: another worker holds Build evidence's lock and, while it holds it,
        keeps the pack built again; this worker's press, sent meanwhile, waits for the lock and
        reads the store only then, so it draws that pack and builds none. (Control: read the
        store before taking the lock, and this worker builds a second.)"""
        old, _rows = _kept_four()
        theirs = EP.build_for_episode(_episode(), actor="other@example.com", rebuild_of=old)
        line = tmp_path / "theirs.json"
        line.write_text(json.dumps(theirs, sort_keys=True), encoding="utf-8")
        go = tmp_path / "go"
        holder = subprocess.Popen(
            [sys.executable, "-c", HOLDER, ROOT, H.build_lock_path(), EP._path(), str(line),
             str(go)], stdout=subprocess.PIPE, text=True)
        assert holder.stdout.readline().strip() == "held"
        got = {}

        def press():
            got["r"] = history["client"].post(
                f"/v2/monitoring/alerts/pack/{old['id']}/rebuild", headers=HX)
        t = threading.Thread(target=press)
        t.start()
        time.sleep(0.5)
        go.write_text("go", encoding="utf-8")
        t.join(30)
        assert holder.wait(30) == 0
        assert got["r"].status_code == 200
        rows = EP.read()["rows"]
        assert [r["id"] for r in rows] == [old["id"], old["id"] + "-s5"]
        assert "other@example.com" in rows[1]["trigger"]
        assert f'data-pack="{old["id"]}-s5"' in _html(got["r"])


#: Another worker: holds the build lock, waits for the go file, keeps its pack built again (one
#: line appended under the store's own lock, as `records_migrate.store_append` keeps one), then
#: lets the lock go.
HOLDER = '''
import os, sys, time
sys.path.insert(0, sys.argv[1])
from modules.filestore import PathLock
lock, store, line, go = sys.argv[2:6]
with PathLock(lock):
    print("held", flush=True)
    for _ in range(300):
        if os.path.exists(go):
            break
        time.sleep(0.05)
    time.sleep(0.3)
    with PathLock(store):
        with open(store, "a", encoding="utf-8") as fh:
            fh.write(open(line, encoding="utf-8").read() + "\\n")
'''


class TestExplainNamesThePackItRead:
    def test_the_answer_names_the_pack_its_schema_and_when_it_was_built(self, history,
                                                                         monkeypatch):
        from modules.ai import explain
        old, _rows = _kept_four()
        history["client"].post(f"/v2/monitoring/alerts/pack/{old['id']}/rebuild", headers=HX)
        new = EP.find(old["id"] + "-s5")[0]
        seen = {}

        def ask(feature, prompt, schema, data, **kw):
            seen["pack"] = data.get("pack", "")
            return {"ok": False, "error": "provider_down", "detail": "a stand-in refusal",
                    "call_id": "call-1", "cost_usd": 0.0}
        monkeypatch.setattr(explain.gateway, "ask", ask)
        monkeypatch.setattr(explain, "_ask_round",
                            lambda prompt, schema, data, ctx, network, **kw: ask(
                                None, prompt, schema, data))
        got = explain.explain(new["id"], actor="operator@example.com")
        assert got["pack_read"] == {"id": new["id"], "schema": 5,
                                    "built_at": new["replayed_at"], "as_of": new["built_at"]}
        assert "concurrent" in seen["pack"]
        from flask import render_template
        import app as A
        with A.app.test_request_context():
            html = unescape(render_template("v2/_explain.html", x=got, explain_model="m"))
        assert f"Read pack {new['id']}, schema 5, built" in _words(html)
        older = explain.explain(old["id"], actor="operator@example.com")
        assert older["pack_read"]["id"] == old["id"] and older["pack_read"]["schema"] == 4

    def test_an_answer_shown_names_the_pack_it_read(self, world, monkeypatch):  # noqa: F811
        """Through the real gateway, the model's answer planted (test_ai_explain's world): an
        answer drawn names the pack built again."""
        from modules.ai import explain
        from tests.test_alert_history import _backfill, load
        from tests.test_ai_explain import _answer
        monkeypatch.setattr(H, "_path", lambda: str(world.lab["tmp"] / "alert_history.jsonl"))
        monkeypatch.setattr(H, "_networks", lambda: {"grafana-alerts": ["Lab"]})
        monkeypatch.setattr(H, "_firing_now", lambda: set())
        _backfill(load("annotations_firing"))
        old, _rows = _kept_four()
        new = EP.build_for_episode(_episode(), actor="operator@example.com", rebuild_of=old)
        assert EP.record(new)["ok"]
        world.answer = _answer(new, hypotheses=[{
            "claim": "The heartbeat stopped.", "evidence_refs": ["alert"],
            "confirm_with": "show logging | include HEARTBEAT"}])
        got = explain.explain(new["id"], actor="operator@example.com", send=world.send,
                              today="2026-10-26")
        assert got["ok"] is True, got
        assert got["pack_read"] == {"id": new["id"], "schema": 5,
                                    "built_at": new["replayed_at"], "as_of": new["built_at"]}


def test_build_again_in_a_real_browser(history):
    """On History, r2's row opens on its schema-4 kept pack, which offers Build again; pressed,
    the card draws the pack built again (schema 5, its other alerts) in place, and its Show it
    draws the old one, still readable as it was kept."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A

    old, _rows = _kept_four()
    group = ("[...document.querySelectorAll('details.ah-group')].find(g => "
             "/NMAS heartbeat missing/.test(g.querySelector('summary').textContent))")
    row = f"[...{group}.querySelectorAll('details.ah-row')].find(r => /r2/.test(r.textContent))"
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/monitoring/alerts/history?range=all&show=all"))
            b.wait_for("return !!(window.htmx && document.querySelector('details.ah-group'))")
            b.js(f"{group}.open = true; {row}.open = true;")
            b.wait_for(f"return !!{row}.querySelector('form.pack-rebuild button')", 15)
            assert b.js(f"return {row}.querySelector('.pack').getAttribute('data-pack')") \
                == old["id"]
            # The press answers in place, and its response names `alerts`, so History's list
            # is asked again after it (modules/invalidation.py). With the row open, that redraw
            # is paused, never drawn over the row (C1852): what is read below is read once the
            # list's answer has come and been held and nothing is in flight, never between.
            b.js("window.__list = document.getElementById('alert-history'); "
                 f"{row}.querySelector('form.pack-rebuild button').click()")
            drawn = (f"var r = {row}; var p = r && r.querySelector('.pack'); "
                     "return !document.querySelector('.htmx-request') && "
                     "!!p && p.getAttribute('data-pack') === ")
            held = ("document.getElementById('alert-history') === window.__list && "
                    "window.__list.getAttribute('data-held') === '1' && ")
            b.wait_for(drawn.replace("return ", "return " + held, 1) + f"'{old['id']}-s5'", 30)
            assert b.js(f"return !!{row}.querySelector('.held-note[data-held-why=\"open\"]')")
            text = b.js(f"return {row}.querySelector('.pack').textContent")
            assert "Built again from pack " + old["id"] in text
            assert b.js(f"return {row}.querySelectorAll("
                        "'section.pack-section[data-ref=\"concurrent\"]').length") == 1
            b.js(f"{row}.querySelector('.pack-lineage button').click()")
            b.wait_for(drawn + f"'{old['id']}'", 15)
            text = b.js(f"return {row}.querySelector('.pack').textContent")
            assert f"Built again as pack {old['id']}-s5" in text
            assert b.js(f"return {row}.querySelectorAll("
                        "'section.pack-section[data-ref=\"concurrent\"]').length") == 0
            assert len(EP.read()["rows"]) == 2
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
