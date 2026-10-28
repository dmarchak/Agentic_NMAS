"""Every next step a v2 result offers lands on something that ACTS (C372; the operator,
2026-10-03: "Export the break-glass record…" on the rotate result opened today's device page by
address and nothing on it; a link that only navigates is a dead end).

- The population, by parsing the templates: every control in a result card's "What next"
  (`op-next`) and every control Needs attention draws for an action's `open`. Each names what
  it opens (`data-next-acts`), one of OPENERS; a link to today's pages carries that same name
  as its `open`, and never an address.
- Every `open` the server can put on an action has its own control (the fallback that opened a
  page is gone).
- In a real browser, each opener, loaded as the link loads it, leaves its tool OPEN (today's
  modal shown with its own controls in it, or the v2 device page's card), not just a page; a link naming another list
  than the page's is refused naming both, and opens nothing; and end to end, the rotate
  result's export link, clicked, opens the export.
"""

import os
import re

import pytest

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates", "v2")

#: What each opener leaves open, as a browser expression that is true only then.
OPENERS = {
    # Board 7 (2026-10-03): the export's card, open in place on Credentials, its confirm or its
    # refusal drawn.
    "breakglass_export": ("location.pathname === '/v2/credentials' && "
                          "document.querySelector('#bg-export .op-ft')"),
    # The overdue drill's row (board 7, D): the drill's receipt field on Credentials.
    "breakglass_drill": ("location.pathname === '/v2/credentials' && "
                         "document.querySelector('#bg-drill input[name=receipt]')"),
    # Today's intent editor (`intent_editor`, today's index's `open=intent_editor`) left at 7.8
    # (2026-10-17, P7-23): the v2 Intent tab's editor is `intent_edit` below.
    # Today's deploy plan (`deploy_plan`) left with today's deploy wizard at 7.8 (2026-10-17,
    # P7-25): the v2 device page's Deploy… is `deploy_card` below.
    # C566 board A: Propose on v2, the card open in place on Monitoring › Profile.
    # C566 board C: Bring in the shipped version, its card open in place on Templates.
    "template_bring": ("document.querySelector('#tpl-card h2') && /Bring in the shipped/"
                       ".test(document.querySelector('#tpl-card h2').textContent)"),
    "profile_propose": ("document.querySelector('#prof-card h2') && /Propose the profile/"
                        ".test(document.querySelector('#prof-card h2').textContent)"),
    # The two ways out of a rollback, on the v2 device page (board 11, 2026-10-03): the card
    # in place of the tab, naming the device.
    "revert": ("document.querySelector('#device-op h2') && /Revert a change to r2/"
               ".test(document.querySelector('#device-op h2').textContent)"),
    "retry": ("document.querySelector('#device-op h2') && /Retry the blocked change on r2/"
              ".test(document.querySelector('#device-op h2').textContent)"),
    # The v2 device page's deploy card (a revert whose block still stands offers it).
    "deploy_card": ("document.querySelector('#device-op h2') && /Deploy committed intent to r2/"
                    ".test(document.querySelector('#device-op h2').textContent)"),
    # Templates' Approve… card (the template editor's result offers it for each approval its
    # commit revoked, cutover blocker 5).
    "template_approve": ("document.querySelector('#tpl-card h2') && /^Approve /"
                         ".test(document.querySelector('#tpl-card h2').textContent)"),
    # The v2 device page's restore card (C486: Capture's "Restore from…" when the device
    # lacks lines intent holds).
    "restore_card": ("document.querySelector('#device-op h2') && /Restore r2 from/"
                     ".test(document.querySelector('#device-op h2').textContent)"),
    # The v2 device page's intent editor, open (C569: Capture's "Edit intent…" opened today's).
    "intent_edit": ("document.querySelector('#intent-form #ie-text') && /Editing r2's intent/"
                    ".test(document.getElementById('ed-h').textContent)"),
    # The v2 device page's Intent tab (a seed's next step: read what was committed).
    "intent_tab": ("document.querySelector('[role=tab].on') && /Intent/"
                   ".test(document.querySelector('[role=tab].on').textContent) && "
                   "document.querySelector('#tab-body')"),
    # The v2 device page's Persist card (C541: a rotation left unpersisted, on its result card
    # and its Needs attention row).
    "persist": ("document.querySelector('#device-op h2') && /Persist r2/"
                ".test(document.querySelector('#device-op h2').textContent)"),
    # The v2 device page's Capture card (C739: a drift row's Capture…).
    "capture_card": ("document.querySelector('#device-op h2') && /Capture r2/"
                     ".test(document.querySelector('#device-op h2').textContent)"),
    # The top bar's spend panel, open in place and read (C2056: an AI spend row's Open the
    # spend panel).
    "ai_spend_panel": ("document.getElementById('ai-spend').open && "
                       "document.querySelector('#nmas-ai-panel .ai-head')"),
    #: v2 pages whose content IS the action.
    "update_page": None,
    "profile_apply_page": None,
}
_CONTROL = re.compile(r"<(a|button)\b([^>]*)>", re.S)


def _read(name):
    return open(os.path.join(TEMPLATES, name), encoding="utf-8").read()


def _next_blocks(text):
    """The text of every `op-next` block (to the end of its part)."""
    out = []
    for m in re.finditer(r'<div class="op-next">', text):
        end = text.find("</div></div>", m.end())
        out.append(text[m.end():end if end > 0 else len(text)])
    return out


def _population():
    """[(template, attrs)] for every next-step control and every action-open control."""
    out = []
    for name in sorted(os.listdir(TEMPLATES)):
        text = _read(name)
        for block in _next_blocks(text):
            out += [(name, m.group(2)) for m in _CONTROL.finditer(block)]
    att = _read("_attention.html")
    for m in re.finditer(r"r\.action\.open == '(\w+)' %\}(<a\b[^>]*>)", att):
        out.append(("_attention.html", m.group(2)))
    return out


class TestEveryNextStepNamesWhatItOpens:
    def test_the_population_and_each_names_an_opener(self):
        pop = _population()
        assert len(pop) >= 7, pop
        bad = []
        for name, attrs in pop:
            acts = re.search(r'data-next-acts="(\w+)"', attrs)
            if not acts or acts.group(1) not in OPENERS:
                bad.append((name, attrs.strip()[:120], "names no opener"))
                continue
            href = re.search(r"href=\"\{\{ url_for\('(\w+)'(.*?)\) \}\}\"", attrs)
            if href and href.group(1) == "index":
                opens = re.search(r"open='(\w+)'", href.group(2))
                if not opens or opens.group(1) != acts.group(1):
                    bad.append((name, attrs.strip()[:120], "its link opens something else"))
            if "manage_device" in attrs or "ip=" in attrs:
                bad.append((name, attrs.strip()[:120], "links by address"))
        assert bad == []

    def test_every_open_the_server_emits_has_its_own_control(self):
        emitted = set()
        for path in tracked("modules", "routes", suffix=".py"):
            text = open(path, encoding="utf-8").read()
            emitted |= set(re.findall(r'"open": "(\w+)"', text))
        assert {"breakglass_export", "app_update", "profile_apply", "profile_propose"} <= emitted
        att = _read("_attention.html")
        branches = set(re.findall(r"r\.action\.open == '(\w+)'", att))
        assert emitted - branches == set(), "an open with no control of its own"
        assert ">Open on today's page</a>" not in att, "the control that opened only a page"


@pytest.fixture
def page(served, monkeypatch):  # noqa: F811
    """The served lab, with today's index showing the lab's list as active (`app` reads the
    active list through its own import)."""
    import app as A
    from modules import config
    monkeypatch.setattr(A, "get_current_device_list", lambda: (
        "Lab", os.path.join(config.get_list_data_dir("Lab"), "devices.csv")))
    b = served["b"]
    b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
    return served


def _open_index(served, query):
    b = served["b"]
    b.go(served["srv"].url("/?" + query))
    return b


class TestEachOpenerActsInARealBrowser:
    @pytest.mark.parametrize("name, query", [
        ("breakglass_export", "open=breakglass_export&list=Lab"),
        ("profile_propose", "/v2/monitoring/profile?propose=1"),
        ("template_bring", "/v2/templates?bring=_common.j2"),
        # The v2 device page's cards, loaded as their links load without script.
        ("revert", "/v2/device/r2?op=revert"),
        ("retry", "/v2/device/r2?op=retry"),
        ("deploy_card", "/v2/device/r2?op=deploy"),
        ("intent_tab", "/v2/device/r2?tab=intent"),
        # Capture's Remove lines, on v2 (C569); its Edit intent is opened in
        # test_v2_links_stay_on_v2, on a lab with r2's intent committed.
        ("deploy_card", "/v2/device/r2?tab=overview&op=deploy&focus=removal&list=Lab"),
        # Capture's Deploy intent… and Restore from… (C486), as their links load them.
        ("deploy_card", "/v2/device/r2?tab=overview&op=deploy&list=Lab"),
        ("restore_card", "/v2/device/r2?tab=overview&op=restore&list=Lab"),
        # The template editor's Approve… (cutover blocker 5), as its link loads it.
        ("template_approve", "/v2/templates?list=Lab&approve=cisco_iosxe/base.j2"),
        ("persist", "/v2/device/r2?op=persist"),
        # A drift row's two answers (C739), as their links load them.
        ("capture_card", "/v2/device/r2?op=capture&list=Lab"),
        ("deploy_card", "/v2/device/r2?op=deploy&list=Lab"),
        # An AI spend row's Open the spend panel (C2056), as its link loads in a new tab; the
        # click in place is tests/test_ai_spend_v2.py's.
        ("ai_spend_panel", "/v2/#nmas-ai-panel"),
    ])
    def test_the_link_leaves_its_tool_open(self, page, name, query):
        if query.startswith("/"):
            b = page["b"]
            b.go(page["srv"].url(query))
        else:
            b = _open_index(page, query)
        b.wait_for(f"return !!({OPENERS[name]})", 15)

    # test_a_link_naming_another_list_is_refused_naming_both left 2026-10-17 (P7-25): it
    # held the refusal of today's dispatcher (templates/partials/device_nsot_actions.html),
    # whose last opener, deploy_plan, left with today's deploy wizard; the dispatcher opens
    # nothing now, so nothing is left to refuse (its code leaves with P7-27). The one opener
    # today's index still has, breakglass_export, goes to Credentials for the link's own
    # network, which needs no refusal.

    def test_the_rotate_results_export_opens_the_export(self, page):
        from tests.test_device_rotate_v2 import CARD, SETTLED, TestInARealBrowser
        b = TestInARealBrowser()._open(page)
        b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
        b.click("#device-op .op-confirm")
        b.wait_for(f"return {CARD} && {CARD}.className.indexOf('op-ok') >= 0 && {SETTLED}", 20)
        b.click('#device-op a[data-next-acts="breakglass_export"]')
        b.wait_for(f"return !!({OPENERS['breakglass_export']})", 15)


from tests.test_device_rotate_v2 import live_browser, rot, served  # noqa: E402,F401
from tests.test_persist_screen import lab  # noqa: E402,F401
