"""The device page's Seed intent, on v2 (7.3; the device-actions canvas, board 8, signed off
2026-10-03 with the change asked: the device's own lines shown as such, never as blocking).

On test_seed_intent's lab (r2's REAL config as its committed golden, only onboarding's
bootstrap as its committed intent). The preview is `seed.entry_for` and
`preview_confirm.seed_preview`, the apply `seed.apply`, the ones `/templatize/seed/*` use:

- the menu row runs here (after Capture), and the page draws the card without script;
- the card: the document's change against what is committed now (the first lines, then how many
  more, the whole document one level down), whether the template reproduces r2, the device's
  own blocks (its self-signed trustpoint, certificate bodies, licence UDI) named and never
  blocking (C397), what it will not do, the operands and checks, the confirm bound to the seed
  hash; a preview commits nothing;
- a line the template does not model is named, and the seed is still offered;
- full intent already committed is not offered, and says why;
- the confirm carries its list and commits as the person (`Source: seed`, `Seeded-From:`), the
  device's own trustpoint not in the committed intent; the result says what stays true and its
  next steps; a golden that moved since the preview commits nothing; no list or no hash refused;
- a card held by another operation re-reads itself when the device is free;
- in a real browser, from the menu to the result, then the Intent tab, the page never reloaded.
"""

import html as html_mod
import json
import re
import subprocess

import pytest

from tests.conftest import TEST_PERSON
from tests.test_seed_intent import UNMODELLED, build_seed_lab


def _serve(lab, monkeypatch):
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    device = dict(lab["device"], username="admin")
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(device)])
    from modules import config
    for mod in ("modules.inventory", "modules.inventory.source_config"):
        monkeypatch.setattr(mod + ".get_list_data_dir", config.get_list_data_dir)
    return lab


@pytest.fixture
def lab(tmp_path, monkeypatch):
    return _serve(build_seed_lab(monkeypatch, tmp_path), monkeypatch)


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True).stdout.strip()


def _get(lab, url):
    r = lab["client"].get(url)
    return r, r.get_data(as_text=True)


def _vals(card):
    m = re.search(r"hx-vals='([^']*)'", card[card.index("op-confirm"):])
    return json.loads(html_mod.unescape(m.group(1)))


def _part(card, title):
    start = card.index(f"<h3>{title}</h3>")
    return card[start:card.index('<div class="op-part">', start)
                if '<div class="op-part">' in card[start:] else len(card)]


class TestTheMenu:
    def test_the_row_runs_here_after_capture_and_without_script_opens_the_page(self, lab):
        _r, page = _get(lab, "/v2/device/r2")
        menu = page[page.index('role="menu"'):page.index('class="tabs"')]
        assert 'hx-get="/v2/device/r2/seed?back=overview&amp;list=Lab"' in menu
        assert "manage_device" not in menu.split("Seed intent")[0][-400:]
        labels = re.findall(r'role="menuitem"[^>]*>([^<]+)</a>', menu)
        assert labels[:4] == ["Plan a deploy…", "Capture", "Seed intent…", "Restore from…"], labels
        assert "Every action runs here." in menu
        _r, page = _get(lab, "/v2/device/r2?op=seed")
        body = page[page.index('id="tab-body"'):]
        assert 'id="device-op"' in body and "Seed r2's intent from its golden" in body


class TestTheCard:
    def test_the_document_reproduced_and_the_devices_own_and_a_preview_commits_nothing(self, lab):
        head = _git(lab["repo"], "rev-parse", "HEAD")
        r, card = _get(lab, "/v2/device/r2/seed")
        assert r.status_code == 200 and "default-src" in r.headers.get(
            "Content-Security-Policy", "")
        what = _part(card, "What will be committed")
        shown = re.findall(r'<span class="op-(?:add|del)?[^"]*">', what)
        assert "host_vars/r2.yml" in what and "more line(s), in the whole document below" in what
        assert "The whole document (" in what and "interfaces:" in what
        assert len(shown) <= 8
        assert "Every line of r2's golden is modelled by its template" in card
        owned = _part(card, "Device-owned")
        for h in ("crypto pki trustpoint TP-self-signed-2968666059",
                  "crypto pki certificate chain SLA-TrustPoint", "license udi pid C8000V"):
            assert h in owned, h
        assert "never blocking" in owned and "regenerated at boot" in owned
        assert "Nothing is sent to any device, and no golden changes" in card
        vals = _vals(card)
        assert vals["list"] == "Lab" and vals["hash"]
        assert _git(lab["repo"], "rev-parse", "HEAD") == head, "a preview commits nothing"

    def test_a_line_the_template_does_not_model_is_named_and_still_offered(
            self, tmp_path, monkeypatch):
        lab = _serve(build_seed_lab(monkeypatch, tmp_path, unmodelled=UNMODELLED), monkeypatch)
        _r, card = _get(lab, "/v2/device/r2/seed")
        rep = _part(card, "Reproduced")
        assert "does not fully model r2" in rep and f"unmodelled: {UNMODELLED}" in rep
        assert "stays blocked" in rep and "op-confirm" in card
        assert UNMODELLED not in _part(card, "Device-owned"), "unmodelled is not the device's own"

    def test_full_intent_is_not_offered_and_says_why(self, lab):
        _r, card = _get(lab, "/v2/device/r2/seed")
        assert lab["client"].post("/v2/device/r2/seed/confirm", data=_vals(card)).status_code \
            == 200
        _r, again = _get(lab, "/v2/device/r2/seed")
        assert "op-confirm" not in again
        assert "Not available: no full intent to replace" in again


class TestTheConfirm:
    def test_it_commits_as_the_person_without_the_devices_own_and_draws_the_result(self, lab):
        from modules.nsot import hostvars
        _r, card = _get(lab, "/v2/device/r2/seed")
        golden = _git(lab["repo"], "log", "-1", "--format=%H", "--", "golden")[:12]
        before = _git(lab["repo"], "rev-parse", "HEAD")
        r = lab["client"].post("/v2/device/r2/seed/confirm", data=_vals(card))
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and "r2's intent seeded" in out and "op-ok" in out
        assert _git(lab["repo"], "diff", "--name-only", before, "HEAD").split() == \
            ["host_vars/r2.yml"]
        msg = _git(lab["repo"], "log", "-1", "--format=%B")
        assert "Source: seed" in msg and f"Seeded-From: r2@{golden}" in msg
        assert f"Actor: {TEST_PERSON}" in msg and "Actor-Verified: access" in msg
        text, _ = hostvars.committed_at_head(lab["repo"], "r2")
        assert "TP-self-signed" not in text, "the device's own trustpoint is not intent (C397)"
        assert "SLA-TrustPoint" in text
        assert "intent reproduces its golden" in out
        assert 'data-next-acts="intent_tab"' in out and 'data-next-acts="deploy_card"' in out

    def test_a_golden_that_moved_since_the_preview_commits_nothing(self, lab):
        from modules.nsot.repo import GoldenItem, save_golden
        _r, card = _get(lab, "/v2/device/r2/seed")
        moved = lab["captured"].replace("\nend", "\nip domain lookup source-interface "
                                                 "GigabitEthernet1\nend", 1)
        assert save_golden("Lab", [GoldenItem("r2", moved, "203.0.113.12",
                                              platform="cisco_iosxe")],
                           source="capture", actor="t", baseline=False).get("commit")
        head = _git(lab["repo"], "rev-parse", "HEAD")
        out = lab["client"].post("/v2/device/r2/seed/confirm",
                                 data=_vals(card)).get_data(as_text=True)
        assert "op-ok" not in out and "moved since the preview" in out
        assert _git(lab["repo"], "rev-parse", "HEAD") == head

    @pytest.mark.parametrize("drop, said", [("list", "names no list"),
                                            ("hash", "carried no seed")])
    def test_a_confirm_without_its_list_or_hash_is_refused(self, lab, drop, said):
        _r, card = _get(lab, "/v2/device/r2/seed")
        vals = dict(_vals(card))
        vals.pop(drop)
        head = _git(lab["repo"], "rev-parse", "HEAD")
        r = lab["client"].post("/v2/device/r2/seed/confirm", data=vals)
        assert r.status_code == 400 and said in r.get_data(as_text=True)
        assert _git(lab["repo"], "rev-parse", "HEAD") == head


def test_a_free_device_draws_the_card_again(lab):
    _r, out = _get(lab, "/v2/device/r2/when-free?op=seed&back=history")
    assert "Seed r2's intent from its golden" in out and 'id="device-op"' in out


#: The card, and htmx at rest (a swapped-in control binds while it settles).
CARD = "document.querySelector('#device-op')"
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


def test_a_real_browser_seeds_from_the_menu_then_opens_the_intent_tab(lab):
    """The path a person takes (C385: every opener clicked where it sits): Actions, "Seed
    intent…", the confirm, the result in place (the page never reloaded), then its "Open the
    Intent tab", a page load to the tab."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from tests.test_next_steps_act import OPENERS
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/device/r2"))
            b.wait_for("return !!window.Alpine && window.NMAS && "
                       "NMAS.live().state === 'connected' && " + SETTLED, 15)
            b.js("window.__notReloaded = 1; return 1")
            b.click('.page-actions button[aria-haspopup="menu"]')
            b.wait_for("var m = document.querySelector('.page-actions [role=menu]');"
                       "return m && m.offsetParent !== null", 10)
            b.click('.page-actions a[data-op="seed"]')
            b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
            b.click("#device-op .op-confirm")
            b.wait_for(f"return {CARD} && /Open in History/.test({CARD}.textContent) && {SETTLED}",
                       20)
            assert "Source: seed" in _git(lab["repo"], "log", "-1", "--format=%B")
            assert b.js("return window.__notReloaded") == 1, "the seed ran in place"
            b.click('#device-op a[data-next-acts="intent_tab"]')
            b.wait_for(f"return !!({OPENERS['intent_tab']}) && {SETTLED}", 15)
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
