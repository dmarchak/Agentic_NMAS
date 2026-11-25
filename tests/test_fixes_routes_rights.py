"""A saved fix's page answers each of its writes through a request as the store's chokepoint
decides it (da740aa1 and a61bb071, C3849; the operator, 2026-11-16): Set Automatic… and Delete…
take the right the fix takes (self-healing for a fix with a match), a person without it is
refused 403 with nothing changed, and a refusal the fix's state makes (no verified run of its
version, a reason too short) is a 409 naming it.

Through tests/test_saved_plans_v2.py's `card` (the real app, a verified person's assertion stood
in, the store the test's own); the retry pass a Set Automatic starts is counted, never run.
Paid for docs/FAST_LANE_DEBT.md's rows for da740aa1 and a61bb071 (the routes' own refusals), the
debt pass, 2026-11-18.

Each test holds one purpose:
- Set Automatic: refused 403 without the self-healing right, refused 409 with no verified run of
  the version, and set with both, the retry pass asked once;
- Delete: refused 403 without the right and 409 for a short reason, nothing changed; deleted with
  both, and Restore brings it back.
"""
import re

import pytest

from modules.nsot import saved_plans as S
from tests.test_saved_plans import MATCH, NET, OTHER, PERSON, WHO, store  # noqa: F401
from tests.test_saved_plans_v2 import card  # noqa: F401 (the fixture)

FILLS = {"device": "device", "interface": "object",
         "cause": {"BPDU guard": "bpduguard", "port security": "psecure-violation"}}
HX = {"HX-Request": "true"}


@pytest.fixture
def retried(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.heal.retry.run_soon", lambda *a, **kw: seen.append((a, kw)))
    return seen


def saved(card, dry_run=True):  # noqa: F811
    """A verified run saved as a fix by its own writer: its key."""
    return S.save_script(NET, run_id=card["run"](), name="BPDU guard recovery", match=MATCH,
                         fills=FILLS, dry_run=dry_run, **WHO)["key"]


def post(card, key, what, **data):  # noqa: F811
    r = card["client"].post(f"/v2/fixes/{key}/{what}?list={NET}", data=data, headers=HX)
    return r.status_code, re.sub(r"\s+", " ", r.get_data(as_text=True))


def stored(key):
    return S.read()["plans"][key]


class TestSetAutomatic:
    def test_without_the_self_healing_right_it_is_refused_and_nothing_changes(
            self, card, retried):  # noqa: F811
        key = saved(card)
        card["rights"]["self_healing"] = [OTHER]
        code, html = post(card, key, "automatic")
        assert code == 403 and "Not set Automatic:" in html, (code, html[:300])
        assert stored(key)["mode"] != "auto" and retried == []

    def test_with_no_verified_run_of_its_version_it_is_refused_naming_it(
            self, card, retried, monkeypatch):  # noqa: F811
        key = saved(card)
        monkeypatch.setattr(S, "verified_run", lambda network, e: {})
        code, html = post(card, key, "automatic")
        assert code == 409 and "version 1 has no verified run yet" in html, (code, html[:300])
        assert stored(key)["mode"] != "auto" and retried == []

    def test_with_both_it_is_set_and_the_retry_pass_is_asked_once(self, card, retried):  # noqa: F811
        key = saved(card)
        code, html = post(card, key, "automatic")
        assert code == 200 and "Set Automatic: BPDU guard recovery runs by itself" in html, (
            code, html[:300])
        assert (stored(key)["mode"], stored(key)["promoted_by"]) == ("auto", PERSON)
        assert len(retried) == 1 and retried[0][1]["script"] == key


class TestDelete:
    def test_without_the_right_or_with_a_short_reason_nothing_changes(self, card):  # noqa: F811
        key = saved(card, dry_run=False)
        card["rights"]["self_healing"] = [OTHER]
        code, html = post(card, key, "delete", reason="taken back by its author")
        assert code == 403 and "Not deleted:" in html, (code, html[:300])
        card["rights"]["self_healing"] = [PERSON]
        code, html = post(card, key, "delete", reason="gone")
        assert code == 409 and "a reason is at least" in html, (code, html[:300])
        assert "retired" not in stored(key)

    def test_deleted_with_both_and_restore_brings_it_back(self, card):  # noqa: F811
        key = saved(card, dry_run=False)
        code, html = post(card, key, "delete", reason="taken back by its author")
        assert code == 200 and "Deleted BPDU guard recovery: no longer offered" in html, (
            code, html[:300])
        assert stored(key)["retired"]["by"] == PERSON
        code, html = post(card, key, "restore", reason="brought back after review")
        assert code == 200 and "Restored BPDU guard recovery" in html, (code, html[:300])
        assert "retired" not in stored(key)


class TestRunWithNoOpenIncident:
    """C3860 (the operator, 2026-11-16: "Run... with no matching incident shows one plain
    message ("No open incident needs this fix right now"), not a device dropdown"): the card
    says that and offers no device, interface or Run; its "Or choose a device and interface…"
    opens the device path when pressed."""

    def test_the_card_is_one_message_with_no_device_and_no_run(self, card, monkeypatch):  # noqa: F811
        from modules import fix_page
        key = saved(card, dry_run=False)
        monkeypatch.setattr(S, "_incidents_problems", lambda network: [])
        import app as A
        with A.app.test_request_context(f"/v2/fixes/{key}/run?list={NET}"):
            c = fix_page.run_card(NET, key)
        assert (c["state"], c["why"], c["none_open"]) == (
            "none", "No open incident needs this fix right now", True), c
        assert c["devices"] == [] and c["ports"] == [] and c["post"] is None, c
        assert c["port_ok"], "the device path stays its own choice"

    def test_in_a_real_browser_run_then_the_port_link(self, card, monkeypatch):  # noqa: F811
        from tests import browser
        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the card's data test above still runs")
        import app as APP
        key = saved(card, dry_run=False)
        monkeypatch.setattr(S, "_incidents_problems", lambda network: [])
        with browser.Served(APP.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url(f"/v2/fixes/{key}?list={NET}"))
                b.wait_for("return !!window.htmx && !!document.querySelector("
                           "'button[hx-get*=\"/run\"][data-op=\"plans\"]')")
                b.click('button[hx-get*="/run"][data-op="plans"]')
                # Settled and bound: CI #2210 pressed the swapped-in link before htmx had
                # processed it, and the press did nothing for 10 s.
                b.wait_for("var c = document.getElementById('fix-run');"
                           " var p = c && c.querySelector('button[data-op=\"fix-run-port\"]');"
                           " return c && c.getAttribute('data-run-state') === 'none'"
                           " && !!(p && p['htmx-internal-data'])"
                           " && !document.querySelector('.htmx-swapping, .htmx-settling,"
                           " .htmx-request')")
                got = b.js("var c = document.getElementById('fix-run');"
                           " return {text: c.innerText, dev: !!c.querySelector('#fix-run-dev'),"
                           " run: !!c.querySelector('button.btn-primary')}")
                assert "No open incident needs this fix right now." in got["text"], got
                assert not got["dev"] and not got["run"], got
                b.click('#fix-run button[data-op="fix-run-port"]')
                # The device path's own answer (this store holds no committed intent).
                b.wait_for("return /No device of " + NET + " has an access port/.test("
                           "document.getElementById('fix-run').innerText)")
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
