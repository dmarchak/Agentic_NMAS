"""Explain's answer kept with its frozen pack (C1853), one press one call through its route
(C1854), and Monitoring › Alerts › History never redrawn under a person mid-task (C1852): the
operator's Walk 2, 2026-10-27, where s1's pack `ep-efbd328eb1a3800c5eea` was explained twice,
12 s apart, both calls reaching the provider, after the list's redraw dropped the first.

Through the real routes, on tests/test_ai_explain.py's world (r1's pack built from the
captures, hosted AI allowed, a planted answer, the provider's send counted):

- **kept:** an answer is kept with its pack, keyed by the pack's hash, the prompt version and
  the model (`explain_answers.key_of`); the pack's card draws it when it opens (reopening, a
  reload, History's link), marked kept, and nothing is sent;
- **Explain on a pack with one** (a page drawn before it was kept) returns it, sending nothing;
- **Explain again** is a new call, said on the button with its cost; the first answer stays
  kept and the newest is drawn, the earlier one counted;
- what is not the model's answer (hosted AI off) is not kept; "couldn't analyse" is;
- a kept answer under another prompt version or model is not this question's answer;
- an answers store that cannot be read refuses a plain Explain, sending nothing, and says so;
- **one press, one call:** two presses of one pack in flight together (a double click), and a
  retry of a press with its key, each reach the provider once;
- **in a real browser** (History's row): Explain pressed, the list's announcement arriving
  mid-call holds the redraw (the row stays open, "Newer data is waiting"), the answer lands in
  the row, the entry says "Paused while you work" with Show it now; a reload draws the kept
  answer with no new call; a press after a reload mid-call joins the call in flight.
"""
import threading
import time
from html import unescape

import pytest

from modules import alert_history as H
from modules import evidence_pack as EP
from modules import records_migrate
from modules.ai import anthropic_adapter as A
from modules.ai import explain, explain_answers, presses, profiles
from tests.test_ai_explain import _answer, world  # noqa: F401 (the fixture)
from tests.test_alert_history import _backfill, load
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)

RULE = "NMAS heartbeat missing: r2"


def _post(world, again=False, key=None, client=None):
    headers = {"HX-Request": "true"}
    if key:
        headers[presses.HEADER] = key
    c = client or world.lab["client"]
    r = c.post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
               data={"again": "1"} if again else {}, headers=headers)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return unescape(r.get_data(as_text=True))


def _card(world):
    r = world.lab["client"].get(f"/v2/monitoring/alerts/pack/{world.pack['id']}")
    return unescape(r.get_data(as_text=True))


def _kept_rows():
    return explain_answers.read()["rows"]


CLAIM = "A configuration change on r1 preceded the errors."


# ------------------------------------------------------------------------------- kept

class TestKeptWithThePack:
    def test_an_answer_is_kept_and_reopening_draws_it_with_no_call(self, world):
        world.answer = _answer(world.pack)
        html = _post(world)
        assert CLAIM in html and len(world.sent) == 1
        (row,) = _kept_rows()
        assert {k: row[k] for k in ("pack_hash", "prompt", "model", "pack_id")} == {
            "pack_hash": world.pack["hash"], "prompt": "explain.v%d" % explain.PROMPT[1],
            "model": profiles.TASKS["explain"]["model"], "pack_id": world.pack["id"]}
        assert row["call_id"] and row["actor"] and row["result"]["answer"]["hypotheses"]
        assert "Explain again" in html, "once kept, the button is a new call, said so"
        card = _card(world)
        assert CLAIM in card and "kept with the pack" in card and "Explain again" in card
        assert "A new call, up to $%.4f; this answer stays." % profiles.cap_per_call(
            "explain") in card
        assert len(world.sent) == 1, "opening the card sends nothing"

    def test_explain_on_a_pack_that_has_an_answer_sends_nothing(self, world):
        world.answer = _answer(world.pack)
        _post(world)
        html = _post(world)                       # a page drawn before the answer was kept
        assert CLAIM in html and "kept with the pack" in html
        assert len(world.sent) == 1 and len(_kept_rows()) == 1

    def test_explain_again_is_a_new_call_and_the_first_answer_stays(self, world):
        world.answer = _answer(world.pack)
        _post(world)
        world.answer = _answer(world.pack, rationale="Second look: the change came first.")
        html = _post(world, again=True)
        assert len(world.sent) == 2 and "Second look" in html
        first, second = _kept_rows()
        assert first["call_id"] != second["call_id"]
        assert first["result"]["answer"]["rationale"] != second["result"]["answer"]["rationale"]
        card = _card(world)
        assert "Second look" in card and "1 earlier" in card, "the newest, the first counted"

    def test_a_refusal_is_not_an_answer_and_is_not_kept(self, world):
        world.settings.pop("ai_hosted")
        html = _post(world)
        assert "hosted AI is off until it is allowed" in html and _kept_rows() == []
        assert "Explain again" not in _card(world)

    def test_couldnt_analyse_is_the_models_answer_and_is_kept(self, world):
        a = _answer(world.pack)
        a["hypotheses"][0]["evidence_refs"] = ["logs:999"]
        world.answer = a
        _post(world)
        (row,) = _kept_rows()
        assert row["result"]["error"] == "couldnt_analyse"
        card = _card(world)
        assert "Not explained: couldn't analyse" in card and "Explain again" in card
        assert len(world.sent) == 1

    @pytest.mark.parametrize("field, value", [("prompt", "explain.v1"),
                                              ("model", "another-model"),
                                              ("pack_hash", "0" * 64)])
    def test_an_answer_kept_under_another_key_is_not_this_packs(self, world, field, value):
        world.answer = _answer(world.pack)
        _post(world)
        rows = _kept_rows()
        rows[0][field] = value
        assert explain_answers.kept(world.pack, rows=rows)["answer"] is None
        assert explain_answers.kept(world.pack, rows=_kept_rows())["answer"] is not None

    def test_an_unreadable_answers_store_sends_nothing_and_says_why(self, world, monkeypatch):
        real = records_migrate.store_rows

        def rows(store, path, **kw):
            if store == explain_answers.STORE:
                return {"state": "unreadable", "rows": [], "error": "planted: no answer"}
            return real(store, path, **kw)
        monkeypatch.setattr(records_migrate, "store_rows", rows)
        world.answer = _answer(world.pack)
        html = _post(world)
        assert world.sent == []
        assert "the kept Explain answers cannot be read (planted: no answer)" in html
        assert "nothing was sent" in html
        assert "cannot be read (planted: no answer)" in _card(world)
        assert "Explain again" in html and 'name="again" value="1"' in html, \
            "the refusal offers the press that says it is a new call"
        again = _post(world, again=True)
        assert len(world.sent) == 1 and CLAIM in again
        assert "This answer could not be kept with the pack" in again

    def test_history_s_link_to_the_call_opens_the_card_that_draws_it(self, world):
        from modules.ai import calls
        world.answer = _answer(world.pack)
        _post(world)
        (row,) = _kept_rows()
        shown = [u for u in calls.uses()[row["call_id"]] if u["use"].startswith("shown")]
        assert shown[0]["links"]["page"] == f"/v2/monitoring/alerts/pack/{world.pack['id']}"
        assert CLAIM in _card(world)


# ----------------------------------------------------------------------- one press, one call

@pytest.fixture
def held(world, monkeypatch):
    """The provider's send held open until `release`, counting requests (`world.sent`)."""
    world.answer = _answer(world.pack)
    started, release = threading.Event(), threading.Event()
    real = world.send

    def send(body, key):
        started.set()
        assert release.wait(30), "the test never released the send"
        return real(body, key)
    monkeypatch.setattr(A, "send", send)
    world.started, world.release = started, release
    return world


class TestOnePress:
    def test_a_double_click_is_one_provider_request(self, held):
        import app as APP
        out = {}

        def press(name, key):
            out[name] = _post(held, key=key, client=APP.app.test_client())
        t1 = threading.Thread(target=press, args=("a", "a" * 32), daemon=True)
        t1.start()
        assert held.started.wait(10)
        t2 = threading.Thread(target=press, args=("b", "b" * 32), daemon=True)
        t2.start()
        time.sleep(0.5)
        held.release.set()
        t1.join(20), t2.join(20)
        assert len(held.sent) == 1
        assert CLAIM in out["a"] and CLAIM in out["b"]
        assert len(_kept_rows()) == 1, "one call, kept once"

    def test_a_retry_with_the_same_key_is_one_provider_request(self, world):
        world.answer = _answer(world.pack)
        _post(world, again=True, key="k" * 32)
        html = _post(world, again=True, key="k" * 32)
        assert len(world.sent) == 1 and CLAIM in html and len(_kept_rows()) == 1


# ------------------------------------------------------------------------ in a real browser

@pytest.fixture
def history_row(held, monkeypatch):
    """History holding the 21 Oct slice, and r2's past heartbeat alert given its rebuilt pack,
    so its row opens on the pack and Explain."""
    monkeypatch.setattr(H, "_path", lambda: str(held.lab["tmp"] / "alert_history.jsonl"))
    monkeypatch.setattr(H, "_networks", lambda: {"grafana-alerts": ["Lab"]})
    monkeypatch.setattr(H, "_firing_now", lambda: set())
    _backfill(load("annotations_firing"))
    e = next(e for e in H.episodes(H.read()["rows"]) if e["rule"] == RULE)
    e = dict(e, fired_at=e["started_at"], outcome="fired")
    pack = EP.build_for_episode(e, actor="operator@example.com")
    assert EP.record(pack)["ok"]
    held.answer = _answer(pack, hypotheses=[{"claim": "The heartbeat stopped.",
                                             "evidence_refs": ["alert"],
                                             "confirm_with": "show logging | include HEARTBEAT"}])
    held.episode, held.history_pack = e, pack
    return held


ROW = 'details[data-keep="ah-{id}"]'
HISTORY = "/v2/monitoring/alerts/history?range=all&show=all"


def _open_row(b, sel):
    b.wait_for("return !!(window.htmx && document.querySelector('#alert-history'))", 15)
    b.js(f"var r = document.querySelector('{sel}'); r.closest('details.ah-group').open = true;"
         "r.querySelector('summary').click(); return 1")
    b.wait_for(f"var f = document.querySelector('{sel} form.explain-ask');"
               "return !!(f && f['htmx-internal-data'])", 15)


def _browser():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    return browser


def test_a_refresh_mid_explain_keeps_the_row_and_the_answer_lands(history_row):
    browser = _browser()
    import app as APP

    w, sel = history_row, ROW.format(id=history_row.episode["id"])
    with browser.Served(APP.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url(HISTORY))
            _open_row(b, sel)
            b.js(f"document.querySelector('{sel} [data-op=alert-evidence]').click(); return 1")
            assert w.started.wait(15), "Explain reached the provider"
            # The alerts reader's announcement, as it arrives every minute.
            b.js("document.body.dispatchEvent(new CustomEvent('nmas:alerts')); return 1")
            b.wait_for("var h = document.getElementById('alert-history');"
                       "return !!h && h.getAttribute('data-held') === '1'", 15)
            mid = b.js(f"var r = document.querySelector('{sel}');"
                       "var n = document.querySelector('#alert-history .held-note');"
                       "return {open: !!r && r.open, note: n ? n.textContent : '',"
                       " busy: !!r && !!r.querySelector('[data-op=alert-evidence][aria-busy=true]')}")
            w.release.set()
            b.wait_for(f"return !!document.querySelector('{sel} .explain-list li')", 20)
            b.wait_for("var n = document.querySelector('#alert-history .held-note');"
                       "return !!n && n.textContent.indexOf('Paused while you work') >= 0", 10)
            after = b.js(f"var r = document.querySelector('{sel}');"
                         "return {open: r.open, claim: r.querySelector('.explain-list li strong')"
                         ".textContent, again: r.querySelector('[data-op=alert-evidence] .op-idle')"
                         ".textContent.trim()}")
            # Show it now: the newer list, the row open again, its pack and kept answer drawn.
            b.js("document.querySelector('#alert-history .held-resume').click(); return 1")
            b.wait_for("var h = document.getElementById('alert-history');"
                       f"return !h.getAttribute('data-held') && !!document.querySelector('{sel}"
                       " .explain-kept')", 20)
            resumed = b.js(f"var r = document.querySelector('{sel}'); return r.open")
            # A reload: the kept answer, no new call.
            b.go(srv.url(HISTORY))
            _open_row(b, sel)
            b.wait_for(f"return !!document.querySelector('{sel} .explain-kept')", 15)
            reloaded = b.js(f"return document.querySelector('{sel} .explain-list li strong')"
                            ".textContent")
        finally:
            w.release.set()             # never left holding a request thread
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert mid["open"] and mid["busy"], mid
    assert "Newer data is waiting; it shows when this answers." in mid["note"], mid
    assert after == {"open": True, "claim": "The heartbeat stopped.", "again": "Explain again"}
    assert resumed is True
    assert reloaded == "The heartbeat stopped."
    assert len(w.sent) == 1, "one provider request in all"


def test_a_press_after_a_reload_mid_call_joins_the_call(history_row, monkeypatch):
    """And each press carries its own key, made in the page (`X-NMAS-Press`)."""
    browser = _browser()
    import app as APP
    from flask import request

    keys, real = [], presses.current_press

    def seen(actor):
        keys.append(request.headers.get(presses.HEADER))
        return real(actor)
    monkeypatch.setattr(presses, "current_press", seen)
    w, sel = history_row, ROW.format(id=history_row.episode["id"])
    with browser.Served(APP.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url(HISTORY))
            _open_row(b, sel)
            b.js(f"document.querySelector('{sel} [data-op=alert-evidence]').click(); return 1")
            assert w.started.wait(15)
            b.go(srv.url(HISTORY))                  # the page reloaded mid-call
            _open_row(b, sel)
            b.js(f"document.querySelector('{sel} [data-op=alert-evidence]').click(); return 1")
            time.sleep(0.5)
            w.release.set()
            b.wait_for(f"return !!document.querySelector('{sel} .explain-list li')", 20)
            claim = b.js(f"return document.querySelector('{sel} .explain-list li strong')"
                         ".textContent")
        finally:
            w.release.set()             # never left holding a request thread
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert claim == "The heartbeat stopped."
    assert len(w.sent) == 1, "the second press joined the call in flight"
    assert len(keys) == 2 and keys[0] != keys[1], keys
    assert all(k and presses.KEY_SHAPE.match(k) for k in keys), keys
