"""The incident page says one state and carries its own action (the GUI review's item 2, C3450;
the operator, 2026-11-13: "Build review items 1, 2, 5, 6, 9 first"; `modules/incident_page.py`
`status` and `item_of`, `attention.first_action`, `templates/v2/incident.html`). Through the
real app, on the heal's lab (tests/test_incident_page.py's planted incidents, each by the heal
modules' own writers). No device, no network. The lost-stream incident, on its own lab, is
tests/test_incident_stream.py's.

The review measured the page in its four planted states: 0 buttons on each, What to do sending
the person back to Needs attention, and a page whose header said "No person needed" above a
section saying "Stopped … Nothing more runs unless you choose".

- **One state, from one function** (`incident_page.status`): the header's badge, What's wrong,
  What Mercury has done, What to do and AI troubleshooting each carry it (`data-inc-state`),
  and no part of a page that needs a person says nobody is needed, or the reverse. The
  function's own answers are held for each record and each state of the troubleshooting
  record, the expectation written here from the records, never through the page.
- **One primary button in What to do, the incident's Needs attention item's own action:** the
  same words and the same target as the item's line on Needs attention, which action being
  ONE resolver's answer (`attention.first_action`) for both. A page that needs nobody draws no
  primary button; an incident whose item has left Needs attention says so and opens its
  device; a list not read yet is said as that, never as "no item".
- **What the item kept under Details is drawn on the page (C3488):** a can't-fix's diagnosis
  (none recorded said as that; its hypotheses are tests/test_incident_stream.py's, on real
  captures), the AI analysis in full, and a decision's fix kind, mode and program hash in The
  record.
"""
import re
from html import unescape

import pytest

from modules import incident_page as IP
from tests import test_incident_page as T
from tests.test_heal_decide import lab  # noqa: F401  (the fixture `client` builds on)
from tests.test_heal_policy import T0
from tests.test_heal_propose import measured  # noqa: F401  (a fixture)
from tests.test_heal_propose import proposed
from tests.test_incident_page import client, no_host_addresses  # noqa: F401  (fixtures)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

NET = T.NET


def watching():
    """An incident Mercury is still reading: sighted, nothing decided."""
    return T.I.sight(NET, "edge-b", T.CFG, now=T0 - 1000)["incident"]


def proposal():
    return proposed()["incident"]


#: Each planted incident, with the state its records alone put it in, written here from what
#: was planted (a verified heal, a rolled-back one, a can't-fix standing in dry run, a Tier 2
#: proposal nobody took, an incident only sighted).
PLANTS = {"healed": (T.healed, "fixed"), "rolled_back": (T.rolled_back, "needs_person"),
          "cant_fix": (T.cant_fix, "needs_person"), "proposal": (proposal, "needs_person"),
          "watching": (watching, "open")}
#: The words only a page that needs nobody may draw, and those only one that needs a person
#: may: the review's measured contradiction was one of each on one page.
NOBODY = ("No person needed", "Nothing yet", "Mercury is still reading", "Nothing now:",
          "Nothing: it")
SOMEBODY = ("Needs a person", "It needs a person", "Nothing more runs unless you choose",
            "Stopped:")
#: The sections that carry the page's state, by the id each has (the header has none).
SECTIONS = ("inc-wrong", "inc-done", "inc-todo", "inc-ai")


def with_its_item(monkeypatch):
    """Needs attention read from self-healing's own source alone, a can't-fix's window wide
    enough to reach the lab's clock (it decides in 2026-09), as tests/test_incident_page.py's
    own Needs attention test does."""
    from modules import attention

    monkeypatch.setattr(attention, "SOURCES", [attention.heal_source])
    monkeypatch.setattr(attention, "CANT_FIX_DAYS", 10 ** 5)


def live(body: str) -> str:
    """The page's live region above The record (the record keeps every step's raw words)."""
    return body.split('id="incident-live"', 1)[1].split('class="card tl-record-d', 1)[0]


def section(body: str, sid: str) -> str:
    part = body.split(f'id="{sid}"', 1)
    assert len(part) == 2, f"no #{sid} is drawn"
    return part[1].split("</section>", 1)[0]


def primaries(html: str) -> list:
    """Every primary button in *html*: ``(its tag, its attributes, its words)``; a button is
    whatever carries the class token ``btn-primary`` (a link, a button, a summary)."""
    found = re.findall(r'<(a|button|summary)\b([^>]*\bclass="[^"]*\bbtn-primary\b[^"]*"[^>]*)>'
                       r'(.*?)</\1>', html, re.S)
    return [(tag, unescape(attrs), T.text_of(inner)) for tag, attrs, inner in found]


def the_primary(html: str) -> tuple:
    """The ONE primary button *html* holds, or the test fails saying how many it holds."""
    found = primaries(html)
    assert len(found) == 1, f"{len(found)} primary button(s) drawn, not one: {found}"
    return found[0]


def attr(attrs: str, name: str) -> str:
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return m.group(1) if m else ""


def card_of(html: str, prefix: str = "") -> tuple:
    """The card an action opens in *html*, by the element it is read into: ``(its id, the
    address it is read from, its attributes)``, each "" when no such card is drawn."""
    m = re.search(rf'<div class="heal-prop" id="({re.escape(prefix)}[^"]*)"([^>]*)>', html)
    if not m:
        return "", "", ""
    return m.group(1), attr(unescape(m.group(2)), "hx-get"), unescape(m.group(2))


def the_row(client, iid):  # noqa: F811
    """The incident's own row as Needs attention computes it now, and that row's line as the
    list's page draws it: ``(the row, its first control's words, that control's target)``. The
    target of a control that opens a card in the row is the card's own read (its ``hx-get``)."""
    from modules import attention

    rows = [r for r in attention.needs_attention()["rows"]
            if (r.get("incident_page") or {}).get("id") == iid]
    assert len(rows) == 1, f"{len(rows)} Needs attention rows are about {iid}, not one"
    row = rows[0]
    listed = T.read(client, f"/v2/attention?list={NET}").get_data(as_text=True)
    mine = listed.split(f'data-attention-row="{row["id"]}"', 1)[1]
    first = re.search(r'<span class="att-primary">\s*<a\b([^>]*)>(.*?)</a>',
                      mine.split("</summary>", 1)[0], re.S)
    assert first, "the row's line draws its first action"
    href = attr(unescape(first.group(1)), "href")
    if href.startswith("#"):
        card = re.search(rf'<div class="heal-prop" id="{re.escape(href[1:])}"([^>]*)>', mine)
        assert card, f"the row draws the card {href} its line opens"
        href = attr(unescape(card.group(1)), "hx-get")
    return row, T.text_of(first.group(2)), href


# ── One state, from one function ───────────────────────────────────────────────────────────

class TestTheOneStateFunction:
    @pytest.mark.parametrize("name", sorted(PLANTS))
    def test_its_answer_is_the_records_state_whatever_was_not_tried(self, client, name):  # noqa: F811
        plant, state = PLANTS[name]
        found = T.model(plant())
        got = IP.status(*found)
        assert got["state"] == state and got["words"] == IP.STATE_WORDS[state]
        assert got["needs"] is (state == "needs_person") and got["why"] in IP.WHYS
        assert IP.status(*found, "ready") == got, "nothing tried changes nothing"
        assert IP.status(*found, "none") == got, "no troubleshooting record changes nothing"

    @pytest.mark.parametrize("name, why", [("rolled_back", "verify_failed"),
                                           ("cant_fix", "decided"), ("proposal", "proposal"),
                                           ("watching", "watching"), ("healed", "fixed")])
    def test_each_why_is_the_one_its_records_show(self, client, measured, name, why):  # noqa: F811
        assert IP.status(*T.model(PLANTS[name][0]()))["why"] == why

    def test_a_fix_a_person_ran_moves_an_open_incident_s_state(self, client):  # noqa: F811
        """The review's contradiction, at the function: an incident Mercury is only watching
        reads "open" by its own records, and a person's fix that stopped without fixing it
        needs a person, whatever the heal's records say; one running or passed needs nobody
        now."""
        found = T.model(watching())
        assert IP.status(*found)["why"] == "watching"
        for fixit, why in (("stopped", "attempt_stopped"), ("proposed", "fix_proposed"),
                           ("cancelled", "troubleshooting_cancelled"),
                           ("handed_over", "handed_over")):
            got = IP.status(*found, fixit)
            assert (got["state"], got["needs"], got["why"]) == ("needs_person", True, why)
        for fixit, why in (("running", "attempt_running"), ("passed", "attempt_passed")):
            got = IP.status(*found, fixit)
            assert (got["state"], got["needs"], got["why"]) == ("open", False, why)

    def test_a_resolved_incident_stays_resolved_whatever_was_tried(self, client):  # noqa: F811
        found = T.model(T.healed())
        for fixit in ("stopped", "proposed", "running", "passed", "resolved", "none"):
            assert IP.status(*found, fixit)["state"] == "fixed", fixit

    def test_a_cant_fix_with_a_fix_running_needs_nobody_now(self, client):  # noqa: F811
        found = T.model(T.cant_fix())
        assert IP.status(*found, "running")["state"] == "open"
        assert IP.status(*found, "stopped")["why"] == "attempt_stopped"


class TestOneStateOnThePage:
    @pytest.mark.parametrize("name", sorted(PLANTS))
    def test_every_section_says_the_header_s_state_and_none_says_another(self, client,  # noqa: F811
                                                                         monkeypatch, name):
        """The state each section carries is the header's, and the words on the page are that
        state's alone: a page that needs a person holds none of the words only a page that
        needs nobody draws, and the reverse."""
        with_its_item(monkeypatch)
        plant, state = PLANTS[name]
        body = T.page(client, plant())
        said = live(body)
        assert f'<span data-state="{state}">' in said, "the header's badge"
        carried = re.findall(r'data-inc-state="([^"]*)"', said)
        assert len(carried) == len(SECTIONS) + 1, carried
        assert set(carried) == {state}, f"a section says another state: {carried}"
        for sid in SECTIONS:
            assert f'data-inc-state="{state}"' in section(body, sid).split(">", 1)[0], sid
        words = T.text_of(said)
        wrong = NOBODY if state == "needs_person" else SOMEBODY
        right = SOMEBODY if state == "needs_person" else NOBODY
        assert [w for w in wrong if w in words] == [], (state, words)
        assert [w for w in right if w in words], f"the page says its own state: {words}"
        # And What to do says it in words, once.
        todo = T.text_of(section(body, "inc-todo"))
        assert todo.count("It needs a person") == (1 if state == "needs_person" else 0), todo

    def test_the_scan_finds_a_planted_contradiction(self, client, monkeypatch):  # noqa: F811
        """The floor under the scan above: the review's page, planted. A can't-fix whose
        sections carry "needs a person", drawn with the level of an incident nobody ever
        needed, holds one of each kind of words, and the scan's lists find both."""
        with_its_item(monkeypatch)
        monkeypatch.setattr(IP, "_severity", lambda *a, **kw: {"words": "No person needed",
                                                               "kind": "muted"})
        said = live(T.page(client, T.cant_fix()))
        assert set(re.findall(r'data-inc-state="([^"]*)"', said)) == {"needs_person"}
        words = T.text_of(said)
        assert [w for w in NOBODY if w in words] == ["No person needed"]
        assert "Needs a person" in words


# ── One primary button, the item's own action ──────────────────────────────────────────────

class TestTheOnePrimaryButton:
    @pytest.mark.parametrize("name", ["cant_fix", "rolled_back", "proposal"])
    def test_it_is_the_needs_attention_item_s_own_action(self, client, monkeypatch, measured,  # noqa: F811
                                                         name):
        from modules import attention

        with_its_item(monkeypatch)
        iid = PLANTS[name][0]()
        row, words, target = the_row(client, iid)
        todo = section(T.page(client, iid), "inc-todo")
        assert 'data-item="stands"' in todo.split(">", 1)[0]
        button = the_primary(todo)
        tag, attrs, said = button
        assert said == words, "the page's button says what the item's line says"
        assert f'data-first="{attention.first_action(row)}"' in todo
        if tag == "summary":
            # An action drawn in place: its card is read from the same address the row's is,
            # under the button, when the button is pressed.
            assert '<div class="inc-card"><div class="heal-prop"' in todo
            _id, read_from, attrs = card_of(todo)
            assert read_from == target, "the card is read from where the row's is"
            opener = re.findall(r'<details class="inc-open" id="([^"]+)"', todo)
            assert len(opener) == 1 and f'hx-trigger="toggle once from:#{opener[0]}"' in attrs
        else:
            assert tag == "a" and attr(attrs, "href") == target
        # What the item says to do, in its own words, and how it clears.
        label = row["action"]["label"]
        assert T.text_of(label[:1].upper() + label[1:]) in T.text_of(todo)
        assert "clears when " + T.text_of(row["clears"]["when"]) in T.text_of(todo)
        assert "Open Needs attention" not in todo, "the page never sends a person back"

    def test_the_three_planted_items_offer_what_was_planted(self, client, monkeypatch,  # noqa: F811
                                                            measured):  # noqa: F811
        """The expectation by a path of its own: what each planted incident's button says and
        opens, written here from what was planted."""
        with_its_item(monkeypatch)
        iid = T.cant_fix()
        button = the_primary(section(T.page(client, iid), "inc-todo"))
        assert (button[0], button[2]) == ("a", "Open edge-b")
        assert attr(button[1], "href") == f"/v2/device/edge-b?list={NET}"

    def test_a_proposal_s_button_is_review_the_fix_and_opens_its_card(self, client, monkeypatch,  # noqa: F811
                                                                      measured):  # noqa: F811
        with_its_item(monkeypatch)
        d = proposed()
        todo = section(T.page(client, d["incident"]), "inc-todo")
        button = the_primary(todo)
        assert (button[0], button[2]) == ("summary", "Review the fix…")
        cid, card, _attrs = card_of(todo, "heal-prop-")
        assert cid == f'heal-prop-{d["id"]}', "the card is this incident's decision's"
        # The card it opens is the proposal's own, with Approve and Decline: read now.
        got = client.get(card, headers={"HX-Request": "true"}).get_data(as_text=True)
        assert f'id="heal-prop-{d["id"]}"' in got and "Approve" in got and "Decline" in got

    @pytest.mark.parametrize("name", ["healed", "watching"])
    def test_a_page_that_needs_nobody_draws_no_primary_button(self, client, monkeypatch, name):  # noqa: F811
        with_its_item(monkeypatch)
        plant, state = PLANTS[name]
        todo = section(T.page(client, plant()), "inc-todo")
        assert f'data-inc-state="{state}"' in todo.split(">", 1)[0], "What to do says its state"
        assert primaries(todo) == [] and "data-first=" not in todo
        assert T.text_of(todo).split("What to do", 1)[1].strip().startswith("Nothing")

    def test_an_item_that_left_needs_attention_is_said_and_the_device_opened(self, client):  # noqa: F811
        """The lab decides in 2026-09, past the days a can't-fix stays on Needs attention: the
        list was read and holds no item for it."""
        todo = section(T.page(client, T.cant_fix()), "inc-todo")
        assert 'data-item="none"' in todo.split(">", 1)[0]
        assert "Its item is not on Needs attention now" in T.text_of(todo)
        button = the_primary(todo)
        assert button[2] == "Open edge-b" and attr(button[1], "href") == \
            f"/v2/device/edge-b?list={NET}"

    def test_a_list_not_read_yet_is_never_read_as_no_item(self, client, monkeypatch):  # noqa: F811
        from modules import attention_store

        monkeypatch.setattr(attention_store, "COMPUTE_ON_READ", False)
        attention_store.clear()
        todo = section(T.page(client, T.cant_fix()), "inc-todo")
        assert 'data-item="reading"' in todo.split(">", 1)[0]
        said = T.text_of(todo)
        assert "Needs attention is still being read" in said
        assert "not on Needs attention now" not in said
        assert len(primaries(todo)) == 1

    def test_a_run_holding_the_device_stands_in_the_action_s_place(self, client, monkeypatch,  # noqa: F811
                                                                   measured):  # noqa: F811
        """While another run holds the device the action would change, the item's line offers
        Open the run, and so does the page: the same resolver's answer."""
        from modules import attention
        from modules.nsot import device_ops

        with_its_item(monkeypatch)
        d = proposed()
        with device_ops.hold(NET, "edge-b", "capture", actor="op@example.com"):
            todo = section(T.page(client, d["incident"]), "inc-todo")
        button = the_primary(todo)
        assert button[2] == "Open the run" and 'data-first="run"' in todo
        assert "<summary" not in todo and 'class="inc-card"' not in todo, \
            "the action's own button is not offered while the run holds its device"
        assert "Capture running since" in T.text_of(todo)
        assert attention.first_action({"held": {"device": "edge-b"},
                                       "action": {"open": "heal_proposal"}}) == "run"


class TestTheOneResolver:
    #: A row of each kind, and the control its line draws for it, by the words only that
    #: control has.
    ROWS = [
        ({"held": {"device": "r1", "list": NET, "name": "A capture", "since": "", "by": "op"},
          "action": {"open": "heal_proposal", "decision": "hd-1"}}, "run", "Open the run"),
        # The GUI review's item 10 (C3457): a group of alike rows whose members' actions differ.
        ({"action": {"open": "alike", "anchor": "alike-1"}, "devices": ["r1"]}, "alike",
         "Open the list"),
        ({"action": {"open": "heal_proposal", "decision": "hd-1"}, "devices": ["r1"]},
         "heal_proposal", "Review the fix…"),
        ({"action": {"open": "heal_halt", "halt": "hh-1"}, "devices": ["r1"]}, "heal_halt",
         "Lift the halt…"),
        ({"action": {"open": "heal_mark", "decision": "hd-1"}, "devices": ["r1"]}, "heal_mark",
         "Was that right?"),
        ({"action": {"open": "resubscribe", "device": "r1", "subs": ["101"]},
          "devices": ["r1"], "networks": {"r1": [NET]}}, "resubscribe",
         "Re-subscribe r1's telemetry (101)…"),
        ({"action": {"open": "ai_spend_panel"}}, "ai_spend_panel", "Open the spend panel"),
        ({"action": {"open": "app_update"}, "source": "host_steps"}, "update_page",
         "Open the Update page"),
        ({"action": {}, "likely": {"device": "r9"}, "devices": ["r1"]}, "likely",
         "Open r9 (likely cause)"),
        ({"action": {"open": "persist", "device": "r1"}, "devices": ["r1"]}, "device",
         "Open r1"),
        ({"action": {"href": "/v2/history"}}, "href", "Open…"),
        ({"action": {"href": "https://example.invalid/"}}, "", ""),
    ]

    def test_it_names_one_action_per_row_in_the_line_s_order(self):
        from modules import attention

        for row, first, _words in self.ROWS:
            assert attention.first_action(row) == first, row
        assert {f for _r, f, _w in self.ROWS} == set(attention.FIRST_ACTIONS)

    def test_the_row_s_line_draws_the_control_it_names(self, client):  # noqa: F811
        """The line and the resolver cannot part: for a row of each kind, the line the list
        draws holds the control the resolver names, and no other of them."""
        import app as A
        from flask import render_template

        every = [w for _r, _f, w in self.ROWS if w]
        for n, (row, first, words) in enumerate(self.ROWS):
            r = dict({"id": f"t:{n}", "level": "warning", "what": "a row", "cause": "a cause",
                      "source": "t", "since": None, "clears": {"when": "it does"},
                      "operands": {}, "devices": [], "networks": {}}, **row)
            r["action"] = dict({"label": "do it", "known": True}, **r["action"])
            with A.app.test_request_context("/v2/"):
                page = render_template("v2/_attention.html", attention_trigger="",
                                       a={"rows": [r], "sources": [], "badge": {"n": 1}})
            line = T.text_of(page.split('<span class="att-primary">', 1)[1].split(
                "</summary>", 1)[0])
            assert [w for w in every if line.startswith(w)] == ([words] if words else []), \
                (first, line)
            from modules import attention
            assert attention.first_action(r) == first

    def test_re_subscribe_is_never_the_line_s_action_where_its_card_is_withheld(self, client):  # noqa: F811
        """A lost stream's device found in two networks, or in none: the row's body says
        Re-subscribe is not offered (which device is not decided), so its line offers the
        device, never Re-subscribe."""
        import app as A
        from flask import render_template
        from modules import attention

        for nets in ({"r1": [NET, "Other"]}, {}):
            r = {"id": "t:resub", "level": "warning", "what": "a lost stream", "cause": "c",
                 "source": "t", "since": None, "clears": {"when": "it does"}, "operands": {},
                 "devices": ["r1"], "networks": nets,
                 "action": {"label": "do it", "known": True, "open": "resubscribe",
                            "device": "r1", "subs": ["101"]}}
            assert attention.first_action(r) == "device", nets
            with A.app.test_request_context("/v2/"):
                page = render_template("v2/_attention.html", attention_trigger="",
                                       a={"rows": [r], "sources": [], "badge": {"n": 1}})
            line = T.text_of(page.split('<span class="att-primary">', 1)[1].split(
                "</summary>", 1)[0])
            assert line.startswith("Open r1") and "Re-subscribe" not in line, (nets, line)
            assert "Re-subscribe is not offered" in T.text_of(page), nets


# ── What the item kept under Details, on the page (C3488) ──────────────────────────────────

class TestWhatTheItemKeptIsOnThePage:
    def test_a_cant_fix_s_diagnosis_block_is_drawn_and_none_is_said_as_none(self, client,  # noqa: F811
                                                                            monkeypatch):
        with_its_item(monkeypatch)
        done = section(T.page(client, T.cant_fix()), "inc-done")
        assert 'id="inc-diag" data-diagnosis="none"' in done
        assert "<h3>Mercury&#39;s diagnosis</h3>" in done or "Mercury's diagnosis</h3>" in done
        assert "Not diagnosed by itself" in T.text_of(done)

    def test_the_ai_analysis_is_drawn_in_full_in_the_ai_section(self, client, monkeypatch):  # noqa: F811
        """Kept by the analysis store's own writer: its label, its rationale, its hypothesis
        with what it cites, and its next step, where the page drew one advisory line."""
        from modules.ai import heal_analysis as HA

        with_its_item(monkeypatch)
        iid = T.cant_fix()
        ai = section(T.page(client, iid), "inc-ai")
        assert 'id="inc-analysis"' in ai and "AI analysis: pending" in T.text_of(ai), \
            "an analysis not kept yet is said as pending"
        HA.record(NET, {"incident": iid, "device": "edge-b", "state": "answered",
                        "words": HA.words_of("answered"), "label": HA.beta(), "call_id": "ai-0",
                        "cost_usd": 0.03,
                        "answer": {"rationale": "The ACL drops OSPF.", "needs_human": True,
                                   "mercury_cites": [],
                                   "hypotheses": [{"claim": "An inbound ACL drops OSPF on Gi2.",
                                                   "cites": ["tried:7"],
                                                   "next": "show ip access-lists"}]}},
                  now=T0 + 40)
        said = T.text_of(section(T.page(client, iid), "inc-ai"))
        for words in ("The ACL drops OSPF.", "Hypothesis: An inbound ACL drops OSPF on Gi2.",
                      "Cites: tried:7", "confirm with show ip access-lists",
                      "Nothing in self-healing reads this answer."):
            assert words in said, words

    def test_an_incident_that_is_no_cant_fix_draws_no_analysis(self, client, monkeypatch):  # noqa: F811
        with_its_item(monkeypatch)
        body = T.page(client, T.healed())
        assert 'data-inc-state="fixed"' in body and 'id="inc-analysis"' not in body
        assert 'id="inc-diag"' not in body

    def test_a_decision_s_kind_mode_and_program_hash_are_in_the_record(self, client, monkeypatch,  # noqa: F811
                                                                       measured):  # noqa: F811
        """A proposal nobody took has no act: what its Needs attention item kept under Details
        for the record is in the page's record, from the decision's own row."""
        with_its_item(monkeypatch)
        d = proposed()
        assert d["kind"] and d["mode"] and d["program_hash"], d
        record = dict(IP.page(NET, d["incident"])["record"])
        assert record["Fix kind"] == d["kind"] and record["Mode"] == d["mode"]
        assert d["program_hash"] in (record.get("Program", "")
                                     + record.get("Program hash, as decided", ""))
        drawn = T.page(client, d["incident"]).split('class="card tl-record-d inc-record"', 1)[1]
        assert d["program_hash"] in drawn and "<dt>Fix kind</dt>" in drawn
