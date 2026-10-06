"""The device page's two ways out of a rollback, on v2 (7.3; the device-actions canvas, board
11, signed off 2026-10-03): Revert intent (the change was WRONG) and Retry the rolled-back
change (it was RIGHT, with a stated reason).

On test_intent_ops' lab (r2's REAL config as its golden, full intent seeded from it, then two
intent edits: A, a description on GigabitEthernet2; B, an NTP server), with a rollback block
recorded against A's change and the classifier's answer fixed (its own tests drive the real
one). The previews are `intent_ops.revert_entry`/`retry_entry` and the applies
`revert_apply`/`retry_apply`, the ones today's `/templatize/*` routes use:

- the menu offers both only while a block stands, and otherwise says why on each row;
- the revert card: the commit a rollback undid chosen by default and marked, the document after
  it, what it will not do (nothing is sent), the confirm bound to the sha and hash;
- the revert confirm commits as the person in the list the card CARRIES; a block that still
  stands is said, with its ways on; a block measured gone is cleared; intent that moved since
  the preview commits nothing;
- the retry card: the blocked program, no confirm until a reason in the shape of one; the
  confirm lifts the block and records the person and the reason as said;
- a confirm naming no list or carrying no hash is refused; a card held by another operation
  re-reads itself when the device is free;
- in a real browser, each from the menu to its result in place, the page never reloaded.
"""

import html as html_mod
import json
import re

import pytest

from tests.conftest import TEST_PERSON
from tests.test_intent_ops import FAILED, HOST, _git, _note, classify, lab  # noqa: F401


@pytest.fixture
def page(classify, monkeypatch):  # noqa: F811
    """The lab served as the v2 device page reads it: r2 in the list 'Lab'."""
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    device = dict(classify["device"], username="admin")
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(device)])
    from modules import config
    for mod in ("modules.inventory", "modules.inventory.source_config"):
        monkeypatch.setattr(mod + ".get_list_data_dir", config.get_list_data_dir)
    return classify


@pytest.fixture
def blocked(page):
    _note(page, "blocking")
    return page


def _get(lab, url):
    r = lab["client"].get(url)
    return r, r.get_data(as_text=True)


def _vals(card):
    m = re.search(r"hx-vals='([^']*)'", card[card.index("op-confirm"):])
    return json.loads(html_mod.unescape(m.group(1)))


def _menu(lab):
    _r, body = _get(lab, "/v2/device/r2")
    return body[body.index('role="menu"'):body.index('class="tabs"')]


class TestTheMenu:
    def test_no_block_offers_neither_and_says_why_on_each(self, page):
        menu = _menu(page)
        assert "/v2/device/r2/revert" not in menu and "/v2/device/r2/retry" not in menu
        for label in ("Revert intent…", "Retry rolled-back change…"):
            row = menu[menu.index(label) - 300:menu.index(label) + 200]
            assert 'aria-disabled="true"' in row
            assert "no rollback block stands on r2: nothing to revert or retry" in row

    def test_a_standing_block_offers_both_here_and_without_script(self, blocked):
        menu = _menu(blocked)
        assert 'hx-get="/v2/device/r2/revert?back=overview&amp;list=Lab"' in menu
        assert 'hx-get="/v2/device/r2/retry?back=overview&amp;list=Lab"' in menu
        assert 'href="/v2/device/r2?tab=overview&amp;op=revert&amp;list=Lab"' in menu
        _r, body = _get(blocked, "/v2/device/r2?op=retry")
        body = body[body.index('id="tab-body"'):]
        assert 'id="device-op"' in body and "Retry the blocked change on r2" in body

    def test_an_unreadable_record_is_said_never_no_block(self, page):
        import os
        from modules.nsot import hostvars
        path = os.path.join(page["repo"], hostvars.ROLLED_BACK_REL)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"r2": {"at": ')                                  # torn
        menu = _menu(page)
        assert "the rollback record could not be read" in menu
        assert "no rollback block stands" not in menu


class TestRevert:
    def test_the_rolled_back_commit_is_chosen_and_the_card_writes_nothing(self, blocked):
        head = _git(blocked["repo"], "rev-parse", "HEAD")
        r, card = _get(blocked, "/v2/device/r2/revert")
        assert r.status_code == 200 and "Revert a change to r2" in card
        chosen = re.search(r'<option value="(\w+)" selected>([^<]*)</option>', card)
        assert chosen.group(1) == blocked["a"][:12]
        assert "(the change a rollback undid)" in chosen.group(2)
        assert "CHANGED-BY-A" in card
        assert "Nothing is sent to the device" in card
        vals = _vals(card)
        assert vals["list"] == "Lab" and vals["sha"] == blocked["a"][:12] and vals["hash"]
        assert _git(blocked["repo"], "rev-parse", "HEAD") == head, "a preview commits nothing"
        assert "default-src" in r.headers.get("Content-Security-Policy", "")

    def test_choosing_another_commit_plans_again(self, blocked):
        _r, card = _get(blocked, f"/v2/device/r2/revert?sha={blocked['b'][:12]}")
        assert _vals(card)["sha"] == blocked["b"][:12]
        assert "192.0.2.123" in card

    def test_a_revert_that_leaves_the_block_says_so_and_offers_its_ways_on(self, blocked):
        _r, card = _get(blocked, f"/v2/device/r2/revert?sha={blocked['b'][:12]}")
        r = blocked["client"].post("/v2/device/r2/revert/confirm", data=_vals(card))
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and "Block still stands" in out and "op-warn" in out
        assert 'data-next-acts="revert"' in out and 'data-next-acts="deploy_card"' in out
        from modules.nsot import hostvars
        assert hostvars.rolled_back_note(blocked["repo"], HOST) is not None
        msg = _git(blocked["repo"], "log", "-1", "--format=%B")
        assert f"Reverts: {blocked['b']}" in msg and f"Actor: {TEST_PERSON}" in msg
        assert "Actor-Verified: access" in msg
        assert out.count("The rollback block STANDS") == 1, "said once (C510)"
        assert "its rollback block STANDS" in out

    def test_a_revert_that_clears_the_block_is_ok_and_offers_no_way_on(self, page):
        _note(page, "no longer applies")
        _r, card = _get(page, "/v2/device/r2/revert")
        out = page["client"].post("/v2/device/r2/revert/confirm",
                                  data=_vals(card)).get_data(as_text=True)
        assert "op-ok" in out and "Block still stands" not in out
        assert "data-next-acts" not in out
        assert out.count("The rollback block is lifted") == 1, "said once (C510)"
        from modules.nsot import hostvars
        assert hostvars.rolled_back_note(page["repo"], HOST) is None
        now = hostvars.read_committed(page["repo"], HOST)
        assert now["interfaces"][1]["description"] != "CHANGED-BY-A"
        assert "192.0.2.123" in now["ntp_servers"], "B, the later commit, is kept"

    def test_intent_that_moved_since_the_preview_commits_nothing(self, blocked):
        from tests.test_intent_ops import _add_ntp, _edit
        _r, card = _get(blocked, "/v2/device/r2/revert")
        _edit(blocked["repo"], _add_ntp, "host_vars: r2 moved after the preview")
        head = _git(blocked["repo"], "rev-parse", "HEAD")
        out = blocked["client"].post("/v2/device/r2/revert/confirm",
                                     data=_vals(card)).get_data(as_text=True)
        assert "op-ok" not in out
        assert _git(blocked["repo"], "rev-parse", "HEAD") == head

    @pytest.mark.parametrize("drop, state", [("list", "names no list"),
                                             ("hash", "carried no commit or preview")])
    def test_a_confirm_without_its_list_or_hash_is_refused(self, blocked, drop, state):
        _r, card = _get(blocked, "/v2/device/r2/revert")
        vals = dict(_vals(card))
        vals.pop(drop)
        head = _git(blocked["repo"], "rev-parse", "HEAD")
        r = blocked["client"].post("/v2/device/r2/revert/confirm", data=vals)
        assert r.status_code == 400 and state in r.get_data(as_text=True)
        assert _git(blocked["repo"], "rev-parse", "HEAD") == head


class TestRetry:
    def test_the_blocked_program_and_no_confirm_until_a_reason(self, blocked):
        r, card = _get(blocked, "/v2/device/r2/retry")
        assert r.status_code == 200 and "Retry the blocked change on r2" in card
        for line in FAILED:
            assert html_mod.escape(line, quote=False) in card
        assert "op-confirm" not in card and "waits on your reason" in card

    def test_what_it_will_not_do_never_contradicts_itself(self, blocked):
        """C508 (the operator, 2026-10-05, Part 6): the card said "this changes intent and
        the record only" and then "Intent is not changed". A retry changes the record only."""
        _r, card = _get(blocked, "/v2/device/r2/retry")
        assert "changes the record only (the block is lifted)" in card
        assert "changes intent and the record" not in card
        assert "Intent is not changed" in card

    def test_a_reason_not_in_the_shape_of_one_says_so(self, blocked):
        _r, card = _get(blocked, "/v2/device/r2/retry?reason=ok")
        assert "op-confirm" not in card and "Not yet a reason:" in card

    def test_a_stated_reason_lifts_the_block_and_records_the_person_and_it(self, blocked):
        why = "the link was down for maintenance"
        _r, card = _get(blocked, f"/v2/device/r2/retry?reason={why}")
        vals = _vals(card)
        assert vals["reason"] == why and vals["list"] == "Lab" and vals["hash"]
        r = blocked["client"].post("/v2/device/r2/retry/confirm", data=vals)
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and "op-ok" in out and "Open in History" in out
        from modules.nsot import hostvars
        assert hostvars.rolled_back_note(blocked["repo"], HOST) is None
        assert [(e["device"], e["actor"], e["reason"]) for e in
                hostvars.retry_log(blocked["repo"])] == [(HOST, TEST_PERSON, why)]

    def test_a_block_that_changed_since_the_preview_is_refused(self, blocked):
        _r, card = _get(blocked, "/v2/device/r2/retry?reason=the link was down for maintenance")
        from modules.nsot import hostvars
        hostvars.record_rolled_back(blocked["repo"], HOST, blocked["b"],
                                    commands=FAILED + ["x"])
        out = blocked["client"].post("/v2/device/r2/retry/confirm",
                                     data=_vals(card)).get_data(as_text=True)
        assert "op-ok" not in out
        assert hostvars.rolled_back_note(blocked["repo"], HOST) is not None
        assert hostvars.retry_log(blocked["repo"]) == []

    def test_a_confirm_without_its_hash_is_refused(self, blocked):
        r = blocked["client"].post("/v2/device/r2/retry/confirm",
                                   data={"list": "Lab", "reason": "the link was down"})
        assert r.status_code == 400 and "carried no block" in r.get_data(as_text=True)


class TestWhenFree:
    @pytest.mark.parametrize("op, title", [("revert", "Revert a change to r2"),
                                           ("retry", "Retry the blocked change on r2")])
    def test_a_free_device_draws_the_card_again(self, blocked, op, title):
        _r, out = _get(blocked, f"/v2/device/r2/when-free?op={op}&back=history")
        assert title in out and 'id="device-op"' in out


#: The card, and htmx at rest (a swapped-in control binds while it settles).
CARD = "document.querySelector('#device-op')"
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


def _open_from_menu(b, srv, op):
    b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
    b.go(srv.url("/v2/device/r2"))
    b.wait_for("return !!window.Alpine && window.NMAS && "
               "NMAS.live().state === 'connected' && " + SETTLED, 15)
    b.js("window.__notReloaded = 1; return 1")
    b.click('.page-actions button[aria-haspopup="menu"]')
    b.wait_for("var m = document.querySelector('.page-actions [role=menu]');"
               "return m && m.offsetParent !== null", 10)
    b.click(f'.page-actions a[role=menuitem][href*="op={op}"]')


@pytest.mark.parametrize("op", ["revert", "retry"])
def test_a_real_browser_goes_from_the_menu_to_the_result(blocked, op):
    """The path a person takes (C385: every opener clicked where it sits): Actions, the row,
    for a retry the reason typed (the card plans again and offers the confirm), the confirm,
    the result in place, the page never reloaded."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            _open_from_menu(b, srv, op)
            if op == "retry":
                b.wait_for(f"return {CARD} && {CARD}.querySelector('input[name=reason]') "
                           f"&& {SETTLED}", 15)
                b.js("var i = document.querySelector('#device-op input[name=reason]');"
                     "i.value = 'the link was down for maintenance';"
                     "i.dispatchEvent(new Event('change', {bubbles: true})); return 1")
            b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
            b.click("#device-op .op-confirm")
            b.wait_for(f"return {CARD} && /Open in History/.test({CARD}.textContent) && {SETTLED}",
                       20)
            assert b.js("return window.__notReloaded") == 1
            from modules.nsot import hostvars
            if op == "retry":
                assert [e["actor"] for e in hostvars.retry_log(blocked["repo"])] == [TEST_PERSON]
            else:
                assert "Block still stands" in b.js(f"return {CARD}.textContent")
                assert f"Reverts: {blocked['a']}" in _git(blocked["repo"], "log", "-1",
                                                          "--format=%B")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
