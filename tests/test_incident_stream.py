"""A lost telemetry stream's incident: its Needs attention row opens it (C3487), and its page
says one state, carries the row's own action and draws what the row kept under Details
(C3488; the GUI review's item 2, C3450; the operator, 2026-11-13). Through the real app on
tests/test_fixit_section_v2.py's lab: r2's real configuration on a box, a self-healing
incident opened by the incidents store's own writer from two lost-stream alerts (101 and
102), each attempt a real Re-subscribe run whose verify reads no data, Mercury's diagnosis the
lost-stream runbook run on its real captures; and r2's row on Needs attention drawn by the
real Grafana source from the alerts reader's value (tests/test_seen_before.py's, through the
real reader's parse), r2 answering by the reachability reader's own read. No device, no
network, no AI call.

The review's measured page was this incident's: the header "Open" and "No person needed",
What's wrong "Mercury is still reading r2", What to do "Nothing yet: Mercury is working on
it", above an AI section saying "Stopped … Nothing more runs unless you choose"; no button
outside that section; and its row on Needs attention, the one with Re-subscribe on it, could
not open the page at all (`attention._link_incident_pages` linked self-healing's rows only).

- **The row opens its incident** where the device's one network holds an open incident opened
  from a subscription the row names; a closed one, another device's, another subscription's or
  a device two networks hold links none; a row folded under the collector's is linked too.
- **One state on the page, in every section**, with nothing tried, after a Re-subscribe that
  stopped without fixing it, and with a fix proposed.
- **One primary button in What to do: the row's own Re-subscribe**, its card read under the
  button with the incident named, so its run is the incident's attempt; a fix proposed under
  AI troubleshooting is the action then, and its card is opened there.
- **What the row kept under Details is on the page:** whether r2 answers, what Mercury cannot
  see, Seen before, and Mercury's diagnosis with every hypothesis.
- **In a real browser at 1280 px** (headless Firefox, unconfined): the button is pressed, its
  card is drawn under it, and neither the button nor the (i) beside it moves.
"""
import json
import re
from html import unescape

import pytest

from modules import incident_page as IP
from tests import test_fixit_section_v2 as FX
from tests import test_incident_page as T
from tests import test_seen_before as SBT
from tests.test_fixit_section_v2 import counted, web  # noqa: F401  (fixtures)
from tests.test_heal_resubscribe import lab  # noqa: F401  (the fixture `web` builds on)
from tests.test_heal_resubscribe_v2 import hidden
from tests.test_incident_state import (SECTIONS, attr, card_of, live, primaries, section, todo_of,
                                       the_primary)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)
from tests.test_seen_before import loki  # noqa: F401  (a fixture)

NET = FX.NET
BUTTON = "Re-subscribe r2's telemetry (101, 102)…"


@pytest.fixture
def stream(web, loki, monkeypatch):  # noqa: F811
    """Needs attention read from Grafana's own source alone: r2's two streams lost, as the
    alerts reader's value holds them, a past loss in the alert history, r2 answering, and r2
    in exactly one network (the labs' inventory answers every network with the same device, so
    the device's network is said here)."""
    from modules import attention
    from modules.heal import seen_before as SB
    from tests.test_lost_stream_severity import probed

    SB.forget()
    SBT.past_loss()
    value = SBT.lost()
    value["streams"] = SB.context(value, SBT.STORE, sources=SBT.Src())
    cached = {"state": "ok", "doc": {"stale_after_seconds": None, "last_good": {
        "value_at": SBT.iso(SBT.NOW), "value": value}}}
    reach = probed()

    def grafana_source():
        return attention.grafana_source(cached, reachability=reach)

    monkeypatch.setattr(attention, "SOURCES", [grafana_source])
    monkeypatch.setattr(attention, "_device_networks", lambda: {"r2": [NET]})
    return web


def the_row():
    """r2's lost-stream row as Needs attention computes it now."""
    from modules import attention

    rows = [r for r in attention.needs_attention()["rows"] if r.get("fix")]
    assert len(rows) == 1, f"{len(rows)} lost-stream rows on Needs attention, not r2's one"
    return rows[0]


def carried(body: str) -> list:
    return re.findall(r'data-inc-state="([^"]*)"', live(body))


def page(client, iid) -> str:
    """The incident's page, held each time to the page's first property: a read. It now reads
    Needs attention's list for its action as well as the incident's own stores, and it leaves
    every file of the store exactly as it was (tests/test_incident_page.py's `read`)."""
    return T.read(client, f"/v2/incident/{iid}?list={NET}").get_data(as_text=True)


# ── C3487: the row opens its incident ──────────────────────────────────────────────────────

class TestTheRowOpensItsIncident:
    def test_a_lost_stream_s_row_opens_its_incident_s_page(self, stream):
        assert "incident_page" not in the_row(), "no incident is open for r2 yet"
        iid = FX.plant()
        row = the_row()
        assert row["action"]["open"] == "resubscribe" and row["source"].startswith("grafana")
        # Premise corrected (R1 and R2, the review of 2026-11-14): the incident offers Start AI
        # troubleshooting (no code fix, the AI not started by itself), and its link says so,
        # so the row and the page offer the same first action (`attention.first_action`).
        assert row.get("incident_page") == {"id": iid, "list": NET, "start": True}
        from modules import attention
        assert attention.first_action(row) == "start"
        listed = stream.get(f"/v2/attention?list={NET}").get_data(as_text=True)
        mine = listed.split(f'data-attention-row="{row["id"]}"', 1)[1]
        body = mine.split('<div class="att-body">', 1)[1]
        links = re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, re.S)
        assert links and (unescape(links[0][0]), T.text_of(links[0][1])) == (
            f"/v2/incident/{iid}?list={NET}", "Open the incident"), "the row's first link"
        r = stream.get(unescape(links[0][0]))
        assert r.status_code == 200 and 'id="incident-live"' in r.get_data(as_text=True)
        # Closed, the incident is no longer what the row is about.
        from modules.heal import incidents
        incidents.close(NET, iid, "the alert cleared", now=FX.T0)
        assert "incident_page" not in the_row()

    def test_only_the_incident_of_that_device_and_subscription_in_its_one_network(self):
        from modules import attention

        def row(device="r2", subs=("101", "102"), nets=(NET,), **kw):
            return dict({"action": {"label": "x", "open": "resubscribe", "device": device,
                                    "subs": list(subs)},
                         "networks": {device: list(nets)}, "devices": [device]}, **kw)

        def inc(iid, device="r2", sub="101", state="watching", **kw):
            return dict({"id": iid, "device": device, "state": state, "triggers": [
                {"kind": "alert", "subscription": sub,
                 "rule": f"NMAS telemetry stream lost: {device} subscription {sub}"}]}, **kw)

        held = {NET: [inc("hi-000000000001", device="r9"), inc("hi-000000000002", sub="300"),
                      inc("hi-000000000003", state="closed"), inc("hi-000000000004", sub="102"),
                      inc("hi-000000000005")],
                "Branch": [inc("hi-00000000000b")]}
        asked = []

        def read(net):
            asked.append(net)
            return {"state": "ok", "incidents": held.get(net, [])}

        folded = row()
        rows = [row(), row(subs=("300",)), row(device="r5"), row(nets=(NET, "Branch")),
                row(nets=()), {"action": {"label": "x", "open": "persist", "device": "r2"},
                               "networks": {"r2": [NET]}},
                dict(row(device="r7", nets=("Branch",)), folded=[folded]),
                row(incident_page={"id": "hi-00000000000f", "list": NET})]
        attention._link_stream_incidents(rows, read=read)
        assert [r.get("incident_page") for r in rows] == [
            {"id": "hi-000000000004", "list": NET},       # the first open one naming 101 or 102
            {"id": "hi-000000000002", "list": NET},
            None,                                          # no incident of r5
            None,                                          # two networks hold a device r2
            None,                                          # no network holds it
            None,                                          # not a lost stream's row
            None,                                          # Branch holds none of r7
            {"id": "hi-00000000000f", "list": NET}]        # a link it already has is kept
        assert folded.get("incident_page") == {"id": "hi-000000000004", "list": NET}
        assert asked == [NET, "Branch"], "each network's incidents are read once"

    def test_a_store_that_cannot_be_read_links_nothing_and_a_drill_says_so(self):
        from modules import attention, fault_drills

        row = {"action": {"label": "x", "open": "resubscribe", "device": "r2", "subs": ["101"]},
               "networks": {"r2": [NET]}, "devices": ["r2"]}

        def torn(net):
            raise RuntimeError("the store is torn")

        attention._link_stream_incidents([row], read=torn)
        assert "incident_page" not in row
        attention._link_stream_incidents(
            [row], read=lambda net: {"state": "unreadable", "incidents": [], "error": "torn"})
        assert "incident_page" not in row
        drill = {"id": "hi-000000000001", "device": "r2", "state": "standing",
                 fault_drills.FIELD: {"id": "fd-0001"},
                 "triggers": [{"kind": "alert", "subscription": "101"}]}
        attention._link_stream_incidents([row], read=lambda net: {"state": "ok",
                                                                   "incidents": [drill]})
        assert row.get("incident_page") == {"id": "hi-000000000001", "list": NET,
                                            "drill": "fd-0001"}


# ── One state, and the row's action ────────────────────────────────────────────────────────

class TestOneStateAndItsAction:
    """Premise corrected throughout (the operator's R1 and R2, 2026-11-14): What to do and AI
    troubleshooting are one card under the BLUF, whose third line is the ONE next action, the
    section model's (`bluf.fix`) or, where it names nothing to press, the row's own
    (`incident_page.with_item`). A lost stream has no code fix of its kind, so its next
    action with nothing tried is Start AI troubleshooting (`fixit.auto.manual_start`), where
    it was the row's Re-subscribe; the row's Re-subscribe card is the page's action where the
    section names none (planted below), and never once it failed here."""

    def test_nothing_tried_it_needs_a_person_and_the_ai_is_its_next_action(self, stream):
        iid = FX.plant()
        assert IP.state_of(*T.model(iid)) == "open", "by the heal's records alone"
        assert IP.status(*T.model(iid), "ready")["why"] == "lost_stream"
        body = page(stream, iid)
        assert '<span data-state="needs_person">' in body
        assert carried(body) == ["needs_person"] * (len(SECTIONS) + 1), carried(body)
        words = T.text_of(live(body))
        for wrong in ("No person needed", "Nothing yet", "Mercury is still reading",
                      "Mercury is working on it"):
            assert wrong not in words, wrong
        assert "Needs a person" in words and "Warning" in words, "the row's own level"
        button = the_primary(todo_of(body))
        assert (button[0], T.text_of(button[2]).split(" Starting…")[0]) == (
            "button", "Start AI troubleshooting")
        assert re.search(r'<p class="fixit-status" data-status>[^<]+', section(body, "inc-ai"))

    def test_with_the_section_naming_nothing_the_row_s_re_subscribe_is_the_action(
            self, stream, monkeypatch):
        """The row's own action, where the section's BLUF names nothing to press: the same
        words as the row's line, its card read from the same address with the incident
        named."""
        from tests.test_incident_bluf import planted

        # Premise corrected (R1 and R2, the review of 2026-11-14): while the incident offers
        # Start AI troubleshooting, that is the row's and the page's first action; the row's
        # Re-subscribe is its action once Start is not offered (here: the AI already asked).
        monkeypatch.setattr("modules.fixit.auto.offers_start", lambda network, record: False)
        iid = FX.plant()
        planted(monkeypatch, iid, fix="none")
        body = page(stream, iid)
        todo = todo_of(body)
        button = the_primary(todo)
        assert (button[0], button[2]) == ("summary", BUTTON)
        row = the_row()
        listed = stream.get(f"/v2/attention?list={NET}").get_data(as_text=True)
        mine = listed.split(f'data-attention-row="{row["id"]}"', 1)[1]
        line = re.findall(r'<span class="att-primary">\s*<a\b[^>]*>(.*?)</a>',
                          mine.split("</summary>", 1)[0], re.S)
        assert [T.text_of(x) for x in line] == [button[2]]
        theirs, ours = card_of(mine, "resub-r2")[1], card_of(todo, "resub-r2")[1]
        assert theirs and ours == f"{theirs}&fixit={iid}", (ours, theirs)

    def test_with_no_item_on_needs_attention_it_still_never_says_no_person_needed(
            self, web, monkeypatch):  # noqa: F811
        """The same incident with Needs attention holding no row for it (its alert is not in
        the list's reading): it needs a person by its own records, so its level, which it
        would take from its item, is not drawn at all, never "No person needed". Premise
        corrected (C3701): with the sources emptied, Needs attention still gives an open
        incident that needs a person a row of its own (`attention._incidents_agree`), so no
        item is reached the one way left, the incidents not readable for the match, as a
        store that cannot be read is."""
        from modules import attention
        from modules import incidents_list

        monkeypatch.setattr(attention, "SOURCES", [])
        monkeypatch.setattr(incidents_list, "rows", lambda net: {
            "rows": [], "folded": 0, "unreadable": [f"{net}'s heal incidents (planted)"]})
        iid = FX.plant()
        body = page(web, iid)
        assert carried(body) == ["needs_person"] * (len(SECTIONS) + 1), carried(body)
        head = live(body).split("</section>", 1)[0]
        assert "No person needed" not in T.text_of(live(body))
        # Premise corrected (the operator's R2, 2026-11-14: "Severity follows impact"): the
        # level is known without the item, from Mercury's own table for a lost stream (it
        # cannot see the device; traffic is unaffected), never critical on a guess.
        sev = re.search(r'<span class="inc-sev">(.*?)</span></span>', head, re.S)
        assert sev and T.text_of(sev.group(1)) == "Warning", head[-600:]
        todo = todo_of(body)
        assert 'data-item="none"' in todo.split(">", 1)[0]
        assert len(primaries(todo)) == 1

    def test_the_card_it_opens_is_the_incident_s_own(self, stream, monkeypatch):
        from tests.test_incident_bluf import planted

        # Premise corrected, as above: the Re-subscribe card is the item's while Start is not
        # offered.
        monkeypatch.setattr("modules.fixit.auto.offers_start", lambda network, record: False)
        iid = FX.plant()
        planted(monkeypatch, iid, fix="none")
        body = page(stream, iid)
        card = card_of(todo_of(body), "resub-r2")[1]
        assert card.endswith(f"&fixit={iid}"), f"the card names the incident: {card!r}"
        before = T.stores()
        got = stream.get(card, headers=FX.HX).get_data(as_text=True)
        assert T.stores() == before, "reading the card wrote nothing"
        assert 'id="resub-r2"' in got and hidden(got, "fixit") == iid, \
            "its confirm records the run as this incident's attempt"

    def test_a_fix_that_stopped_is_said_once_by_the_whole_page(self, stream, monkeypatch):
        """A Re-subscribe ran and its verify read no data: the whole page says the one state,
        and the Re-subscribe that failed is never the next action, even where the section
        names nothing to press (planted)."""
        from tests.test_incident_bluf import planted

        iid = FX.plant()
        FX.attempt(stream)
        body = page(stream, iid)
        assert carried(body) == ["needs_person"] * (len(SECTIONS) + 1), carried(body)
        assert 'data-state="stopped"' in body and '<span data-state="needs_person">' in body
        words = T.text_of(live(body))
        for wrong in ("No person needed", "Nothing yet", "Mercury is still reading",
                      "Mercury is working on it"):
            assert wrong not in words, wrong
        assert the_primary(todo_of(body))[2].startswith("Start AI troubleshooting")
        planted(monkeypatch, iid, fix="none")
        again = todo_of(page(stream, iid))
        assert BUTTON not in T.text_of(again) and 'data-first="resubscribe"' not in again

    def test_a_fix_proposed_is_its_plan_in_the_one_card(self, stream, tmp_path):
        iid = FX.plant()
        FX.attempt(stream)
        FX.diagnosed(iid, tmp_path)
        FX.replan(iid)
        body = page(stream, iid)
        assert 'data-state="proposed"' in body
        assert carried(body) == ["needs_person"] * (len(SECTIONS) + 1)
        todo = todo_of(body)
        assert 'data-fix="approve"' in todo
        assert 'id="resub-r2"' not in todo, "no second card of the same operation"
        assert 'class="fixit-plan"' in section(body, "inc-ai")

    def test_a_fix_running_or_passed_needs_nobody_now(self, stream, monkeypatch):
        """A page that needs nobody draws no primary button: the state function's answer for
        a fix under way, drawn; the page's one state governs the BLUF's next action
        (`incident_page.with_item`)."""
        iid = FX.plant()
        FX.attempt(stream)
        real = IP.status
        monkeypatch.setattr(IP, "status", lambda i, e, d, fixit="": real(
            i, e, d, "passed" if fixit == "stopped" else fixit))
        body = page(stream, iid)
        assert carried(body)[:4] == ["open"] * 4
        todo = todo_of(body)
        assert primaries(todo) == []
        assert "Nothing to press: no person is needed." in T.text_of(todo)


# ── What the row kept under Details, on the page (C3488) ───────────────────────────────────

class TestWhatTheRowKeptIsOnThePage:
    def test_reachability_what_is_unseen_and_seen_before_are_drawn(self, stream):
        iid = FX.plant()
        fix = the_row()["fix"]
        assert fix["answers"]["state"] == "answers" and fix["seen"]["state"] == "match", fix
        body = page(stream, iid)
        wrong = section(body, "inc-wrong")
        said = T.text_of(wrong)
        assert T.text_of(fix["lead"]) in said
        assert T.text_of(fix["answers"]["words"]) in said and 'data-answers="answers"' in wrong
        assert T.text_of(fix["unseen"]) in said
        seen = section(body, "inc-seen")
        assert 'data-seen="match"' in seen.split(">", 1)[0]
        assert "Seen before on r2" in T.text_of(seen)
        assert T.text_of(fix["seen"]["what"]) in T.text_of(seen)
        assert "Open that incident" in seen

    def test_a_device_that_does_not_answer_is_said_in_warning(self, stream, monkeypatch):
        from modules import attention

        iid = FX.plant()
        real = attention.device_answers
        monkeypatch.setattr(attention, "device_answers", lambda *a, **kw: dict(
            real(*a, **kw), state="unknown", words="Not known whether r2 answers: its "
                                                   "reading is past its promise."))
        body = page(stream, iid)
        wrong = section(body, "inc-wrong")
        assert 'class="fix-answers warn-text" data-answers="unknown"' in wrong
        assert "Not known whether r2 answers" in T.text_of(wrong)

    def test_mercury_s_diagnosis_is_drawn_with_every_hypothesis(self, stream, tmp_path):
        """The lost-stream runbook on its real captures, attached to the incident by the step
        log's own writer: the page drew "N hypotheses, on r2's History"; now each of them."""
        iid = FX.plant()
        d = FX.diagnosed(iid, tmp_path)
        claims = [h["claim"] for h in d["hypotheses"]]
        assert claims, "the runbook found hypotheses"
        body = page(stream, iid)
        done = section(body, "inc-done")
        assert 'id="inc-diag" data-diagnosis="done"' in done
        block = done.split('id="inc-diag"', 1)[1]
        assert block.count("<li>") == min(len(claims), 5)
        said = re.sub(r"<time[^>]*>.*?</time>", "", block, flags=re.S)
        for claim in claims[:5]:
            # An instant the runbook wrote into a claim is drawn by the page's clock: the
            # words either side of it are the claim's.
            for part in re.split(r"\d{4}-\d\d-\d\dT[\d:.]+Z", claim):
                assert T.text_of(part) in T.text_of(said), part
        assert "with no AI" in T.text_of(block)


# ── In a real browser, at 1280 px ──────────────────────────────────────────────────────────

SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
#: What to do as the browser shows it: each visible primary button's words and place, the (i)
#: beside it, the card under it, every section's state, and whether the page scrolls sideways.
SEEN = r"""
var todo = document.querySelector('#inc-bluf');
function box(e) { var r = e.getBoundingClientRect();    // its place on the page, scroll apart
  return [Math.round(r.left + window.scrollX), Math.round(r.top + window.scrollY),
          Math.round(r.width), Math.round(r.height)]; }
var prim = Array.from(todo.querySelectorAll('.btn-primary')).filter(
  function (e) { return e.checkVisibility(); });
var how = todo.querySelector('.inc-act > .how-link');
var card = todo.querySelector('.inc-card');
return JSON.stringify({
  primaries: prim.map(function (e) { return [e.innerText.trim(), box(e)]; }),
  how: how ? box(how) : null,
  card: card && card.checkVisibility() ? box(card) : null,
  form: !!todo.querySelector('.inc-card form, .inc-card [name=reason]'),
  fixit: (todo.querySelector('.inc-card [name=fixit]') || {}).value || '',
  states: Array.from(document.querySelectorAll('#incident-live [data-inc-state]')).map(
    function (e) { return e.getAttribute('data-inc-state'); }),
  badge: document.querySelector('.inc-line [data-state]').innerText.trim(),
  sideways: document.documentElement.scrollWidth - document.documentElement.clientWidth
});
"""


def test_the_button_is_pressed_and_its_card_opens_under_it_in_a_real_browser(stream,
                                                                              monkeypatch):
    """Premise corrected (the operator's R2, 2026-11-14): the row's Re-subscribe is the BLUF's
    one action where the section names nothing to press and nothing failed (planted), never
    after the attempt that failed, which this test ran before; What to do is the BLUF."""
    from tests import browser
    from tests.test_incident_bluf import planted

    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the page's own checks above still run")
    import app as nmas

    # Premise corrected (R1 and R2, the review of 2026-11-14): Re-subscribe is the item's
    # action once Start AI troubleshooting is not offered (here: the AI already asked).
    monkeypatch.setattr("modules.fixit.auto.offers_start", lambda network, record: False)
    iid = FX.plant()
    planted(monkeypatch, iid, fix="none")
    with browser.Served(nmas.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url(f"/v2/incident/{iid}?list={NET}"))
            b.wait_for("return !!window.htmx && !!document.querySelector('#inc-bluf "
                       f".btn-primary') && {SETTLED}", 20)
            before = json.loads(b.js(SEEN))
            assert before["badge"] == "Needs a person"
            assert before["states"] == ["needs_person"] * (len(SECTIONS) + 1), before["states"]
            assert len(before["primaries"]) == 1, before["primaries"]
            words, at = before["primaries"][0]
            assert words == BUTTON and at[3] >= 24, "one primary button, tall enough to press"
            assert before["card"] is None and before["how"], "the card is not drawn yet"
            assert before["sideways"] <= 0, "the page scrolls sideways at 1280 px"
            b.click("#inc-bluf .inc-open > summary")
            b.wait_for("return !!document.querySelector('#inc-bluf .inc-card [name=reason]')"
                       f" && {SETTLED}", 20)
            after = json.loads(b.js(SEEN))
            # The card is read and drawn under the button; the button and the (i) beside it
            # are where they were (docs/UI_RULES.md, "No control moves when its own result
            # appears").
            assert after["primaries"][0] == [words, at], (before["primaries"],
                                                          after["primaries"])
            assert after["how"] == before["how"], (before["how"], after["how"])
            assert after["card"] and after["card"][1] >= at[1] + at[3], after["card"]
            assert after["fixit"] == iid, "the card names this incident"
            assert after["sideways"] <= 0 and after["states"] == before["states"]
            # Pressed again, the card is put away, and the button has still not moved.
            b.click("#inc-bluf .inc-open > summary")
            b.wait_for("return !document.querySelector('#inc-bluf .inc-open').open", 10)
            closed = json.loads(b.js(SEEN))
            assert closed["card"] is None and closed["primaries"][0] == [words, at]
            # At phone width: the one button still, nothing scrolling sideways, and its card
            # under it when it is pressed.
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 390, "height": 800})
            b.go(srv.url(f"/v2/incident/{iid}?list={NET}"))
            b.wait_for("return !!window.htmx && !!document.querySelector('#inc-bluf "
                       f".btn-primary') && {SETTLED}", 20)
            phone = json.loads(b.js(SEEN))
            assert len(phone["primaries"]) == 1, phone["primaries"]
            small, where = phone["primaries"][0]
            assert small == BUTTON and phone["sideways"] <= 0, phone
            b.click("#inc-bluf .inc-open > summary")
            b.wait_for("return !!document.querySelector('#inc-bluf .inc-card [name=reason]')"
                       f" && {SETTLED}", 20)
            pressed = json.loads(b.js(SEEN))
            assert pressed["primaries"][0] == [small, where] and pressed["sideways"] <= 0
            assert pressed["card"][1] >= where[1] + where[3]
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
