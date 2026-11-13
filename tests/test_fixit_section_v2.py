"""The incident page's "AI troubleshooting" section, drawn with no AI call
(`modules/fixit/section.py`, `routes/fixit_v2.py`, `templates/v2/_fixit_section.html`; board
recurring-fixes v2, every state but the AI's own; the fix-it plan's S4), through the real app on
tests/test_heal_resubscribe.py's lab: r2's real configuration on a box, its real intent, a
self-healing incident opened by the incidents store's own writer from two lost-stream alerts
(101 and 102), each attempt a real Re-subscribe run whose verify reads no data (`not_back`),
and Mercury's diagnosis the lost-stream runbook run on its real captures. No device, no network,
no AI call.

- **The section's states:** nothing tried; the STOP after a failed attempt, with Retry with
  more information, Cancel and Hand over; a proposal with its repeat flag; the cancelled line;
  the hand-over line; resolved, read-only, with no control.
- **The operator's test 2, at the route ("the cap refuses"):** past the cap Retry is not
  offered and its refusal names both figures; a press made from a panel drawn under the cap
  after the cap moved is refused naming what moved, the proposer asked zero times and nothing
  recorded.
- **The operator's test 3, at the route ("Cancel runs nothing"):** one line, and the AI
  gateway, a device hold, the job starter and the relay each called zero times; the page stays
  open and the section reads cancelled.
- **The operator's test 4, on the page ("a repeated proposal is flagged"):** "Proposed before
  in this incident: attempt 1, failed: …" in the HTML; the operation's card, opened from it,
  refuses Approve without what is different now, and runs with it, the run's record naming the
  incident, the attempt and the proposal (C3106).
- **The hand-over:** kept and sent to nobody with no team, sent to a team ticked, its page
  linked from the section and the record and back.
- **People by display name:** a planted actor's email address is absent and their display name
  present, in the page and in the write-up's page.
- **The setting (C3193):** the AI mode and the per-incident cap drawn on Settings › Installation
  › AI and saved there, recorded.
"""
import os
import re
import time

import pytest

from modules.fixit import incident as F
from modules.fixit import section as S
from tests.test_fixit_catalogue import half_open_run
from tests.test_fixit_handover import NAME, a_team
from tests.test_fixit_incident import T0, a_run
from tests.test_heal_diagnose_stream import stream_alert
from tests.test_heal_resubscribe import ACTOR, DEV, NET, REASON, Clock, Src
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe_v2 import HX, hidden, selection_of
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

DETECTED = T0 - 3600
#: The first attempt: before the press, inside the incident.
FIRST = T0 - 600


@pytest.fixture
def web(lab, monkeypatch):  # noqa: F811
    """The real app on the lab: r2 known to its inventory by NetBox id 7 (its identity
    ``nb:7``), the operation's sources the lab's, a started run run in the request's thread
    (its clock now), and the four starters counted (`started`)."""
    import app as A

    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(DEV, _netbox_id=7)])
    monkeypatch.setattr("modules.integration_groups.network_names", lambda: [NET])
    state = {"src": Src(clock=Clock(time.time() + 5))}
    monkeypatch.setattr("modules.heal.resubscribe.Sources", lambda net, **kw: state["src"])
    started = {"ask": 0, "hold": 0, "job": 0, "relay": 0}

    def job(lst, label, actor, work, **kw):
        started["job"] += 1
        work("j-1")
        return "j-1"
    monkeypatch.setattr("modules.nsot.capture_job.start", job)
    from modules.nsot import device_ops
    real_hold = device_ops.hold

    def hold(*a, **kw):
        started["hold"] += 1
        return real_hold(*a, **kw)
    monkeypatch.setattr(device_ops, "hold", hold)

    def ask(*a, **kw):
        started["ask"] += 1
        raise AssertionError("no AI call is made by the section")
    monkeypatch.setattr("modules.ai.gateway.ask", ask)

    def relay(event, team_ids):
        started["relay"] += 1
        return {"ok": True, "sent": len(team_ids), "failed": 0, "deliveries": [], "error": ""}
    monkeypatch.setattr("modules.notify.delivery.deliver_event", relay)
    A.app.config["TESTING"] = True
    c = A.app.test_client()
    c.state, c.started = state, started
    return c


def plant():
    """One self-healing incident on r2, opened by the incidents store's own writer from its
    two lost-stream alerts: its id."""
    from modules.heal import incidents
    first = dict(stream_alert("101"), epoch=DETECTED, at="")
    got = incidents.sight(NET, "r2", first, now=DETECTED)
    incidents.sight(NET, "r2", dict(stream_alert("102"), epoch=DETECTED + 1), now=DETECTED + 1)
    return got["incident"]


def attempt(web, subs=("101", "102")):
    """Attempt 1: a real Re-subscribe run on r2 inside the incident whose verify reads no data
    (`not_back`); the starters' counts begin again after it, so a test counts only what its
    own presses and draws start."""
    rec = a_run(FIRST, ok=False, subs=subs)
    web.started.update(dict.fromkeys(web.started, 0))
    return rec


def incident(iid):
    return F.Incident(NET, iid, "nb:7", "r2", DETECTED, ("101", "102"))


def diagnosed(iid, tmp_path):
    """Mercury's diagnosis of the incident: the lost-stream runbook run on its real captures
    (half-open), kept in the step log by its own writer, attached to the incident."""
    from modules.heal import steplog
    d = half_open_run(tmp_path)
    steplog.record_diagnosis(NET, dict(d, incident=iid))
    return d


def page(client, iid):
    r = client.get(f"/v2/incident/{iid}?list={NET}")
    return r, r.get_data(as_text=True)


def section_of(html):
    m = re.search(r'<section class="card fixit[^"]*" id="inc-ai".*?</section>', html, re.S)
    assert m, "no AI troubleshooting section drawn"
    return m.group(0)


def post(client, iid, what, **data):
    return client.post(f"/v2/incident/{iid}/fixit/{what}?list={NET}", data=data, headers=HX)


# ── The section's states ────────────────────────────────────────────────────────────────────

class TestTheStates:
    def test_nothing_tried_offers_no_retry_and_says_where_a_fix_starts(self, web):
        iid = plant()
        r, html = page(web, iid)
        assert r.status_code == 200, html
        sec = section_of(html)
        assert 'data-state="ready"' in sec
        assert "No fix has been tried in this incident" in sec
        assert "AI $0.00 of its cap of $1.00" in sec
        assert "/fixit/retry" not in sec and "/fixit/cancel" not in sec
        assert "/fixit/handover" in sec
        assert sum(web.started.values()) == 0

    def test_a_failed_attempt_stops_with_its_three_choices(self, web):
        iid = plant()
        rec = attempt(web)
        _r, html = page(web, iid)
        sec = section_of(html)
        assert 'data-state="stopped"' in sec
        assert "Stopped: " in sec and "Nothing more runs unless you choose." in sec
        assert 'data-attempt="1"' in sec and "<strong>failed:</strong>" in sec
        assert f"result={rec['id']}" in sec, "Open the run opens the run's own card"
        assert "Retry with more information…" in sec and "/fixit/cancel" in sec
        assert "Hand over…" in sec
        # What it found is the run's own record: each subscription's line says its outcome,
        # and opens to its checks (C3455, the GUI review's AI2: one line per subscription).
        for sub in ("101", "102"):
            found = sec.split(f"<summary>Subscription {sub}: re-subscribed; the stream did not "
                              "come back", 1)
            assert len(found) == 2, sub
            line = found[1].split("</details>", 1)[0]
            assert "The stream ✗" in line and "The device ✓" in line and "The collector" in line
        assert sum(web.started.values()) == 0
        # What Mercury has done never says nothing ran beside an attempt (C3198).
        done = html.split('id="inc-done"', 1)[1].split("</section>", 1)[0]
        assert "Nothing has run in this incident." not in done
        assert "The 1 fix a person ran is listed under AI troubleshooting, below." in done

    def test_resolved_is_read_only(self, web):
        from modules.heal import incidents
        iid = plant()
        attempt(web)
        incidents.close(NET, iid, "the alert cleared", now=T0)
        _r, html = page(web, iid)
        sec = section_of(html)
        assert 'data-state="resolved"' in sec and "read-only" in sec
        assert "hx-post" not in sec and "<form" not in sec
        assert 'data-attempt="1"' in sec
        # A press sent to it all the same (an older tab) is refused, with nothing recorded.
        for what in ("cancel", "retry", "handover"):
            r = post(web, iid, what)
            assert r.status_code == 409, what
            assert "is resolved (cleared)" in r.get_data(as_text=True), what
        assert F.read(incident(iid))["state"] == "absent"
        assert sum(web.started.values()) == 0

    def test_no_identity_is_no_section_said(self, web, monkeypatch):
        monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [dict(DEV)])
        iid = plant()
        _r, html = page(web, iid)
        sec = section_of(html)
        assert 'data-state="none"' in sec and "identity is not known" in sec
        r = post(web, iid, "cancel")
        assert r.status_code == 409 and "identity is not known" in r.get_data(as_text=True)
        from modules.config import list_data_path
        assert not os.path.exists(os.path.join(list_data_path(NET), "fixit")), \
            "a refused press writes nothing"


# ── C3455: three choices drawn alike, each a modal; What it found one line each ────────────

def choices_of(sec):
    """The section's row of choices: each button's ``(attributes, words)``, left to right."""
    m = re.search(r'<div class="fixit-choices"[^>]*>(.*?)</div>', sec, re.S)
    assert m, "no row of choices drawn"
    return [(a, " ".join(re.sub(r"<[^>]+>", " ", w).split()))
            for a, w in re.findall(r"<button\b([^>]*)>(.*?)</button>", m.group(1), re.S)]


def attr(attrs, name):
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return m.group(1) if m else None


def modal_of(sec, mid):
    """The body of the modal *mid* the section draws, or None."""
    m = re.search(rf'<dialog class="modal" id="{re.escape(mid)}"[^>]*>(.*?)</dialog>', sec, re.S)
    return m.group(1) if m else None


def outside_modals(html):
    return re.sub(r"<dialog\b.*?</dialog>", "", html, flags=re.S)


#: An IPv4 or an IPv6 address, as a subscription's checks write them.
ADDRESS = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b|\b[0-9a-f]{1,4}(?::[0-9a-f]{0,4}){2,7}\b",
                     re.I)


class TestTheChoices:
    """The GUI review's AI1 (C3455; docs/UI_RULES.md, "Choices of one decision are drawn alike
    and together"): Retry with more information…, Cancel and Hand over… are three buttons in one
    row, left to right, drawn alike and none of them the page's primary, each opening its modal
    (the operator's rule of 2026-11-12); Cancel's modal is its confirm."""

    def test_after_a_stop_three_buttons_alike_each_opening_its_modal(self, web):
        iid = plant()
        attempt(web)
        sec = section_of(page(web, iid)[1])
        got = choices_of(sec)
        assert [w for _a, w in got] == ["Retry with more information…", "Cancel", "Hand over…"]
        assert len({attr(a, "class") for a, _w in got}) == 1, "drawn alike"
        for a, words in got:
            assert "btn-primary" not in attr(a, "class"), words
            assert attr(a, "type") == "button" and attr(a, "aria-haspopup") == "dialog", words
            mid = attr(a, "data-modal-open")
            assert mid and attr(a, "aria-controls") == mid, words
            assert "hx-post" not in a, f"{words} opens its modal; the modal's own button posts"
            assert modal_of(sec, mid) is not None, f"{words}'s modal {mid} is not drawn"
        retry, cancel, hand = (modal_of(sec, attr(a, "data-modal-open")) for a, _w in got)
        assert "/fixit/retry" in retry and "Ask Mercury's diagnosis to re-plan" in retry
        assert "/fixit/handover" in hand and "Send the hand-over" in hand
        # Cancel's modal is its confirm: it alone posts, and its other button records nothing.
        assert sec.count("/fixit/cancel") == 1 and "/fixit/cancel" in cancel
        assert "Cancel troubleshooting" in cancel
        assert re.search(r"<button[^>]*data-modal-close[^>]*>Keep troubleshooting</button>",
                         cancel)
        for body in (retry, hand):
            assert re.search(r"<button[^>]*data-modal-close[^>]*>Cancel</button>", body)
        assert "<summary>Retry with more information…" not in sec
        assert "<summary>Hand over…" not in sec
        # The section draws no primary on the page: What to do's is its one (C3450).
        assert "btn-primary" not in outside_modals(sec)
        assert sum(web.started.values()) == 0

    def test_nothing_tried_offers_hand_over_alone_and_its_modal_hands_over(self, web):
        iid = plant()
        sec = section_of(page(web, iid)[1])
        assert [w for _a, w in choices_of(sec)] == ["Hand over…"]
        assert "Troubleshoot with AI" in sec
        assert "btn-primary" not in outside_modals(sec)
        # Its modal's own form, pressed: the write-up kept, answered in the section in place,
        # whose row then holds all three choices, still alike and none primary.
        hand = modal_of(sec, f"fixit-hand-{iid}")
        m = re.search(r'<form class="fixit-form" hx-post="([^"]+)"', hand)
        assert m, f"Hand over's modal holds no form that posts: {hand}"
        r = web.post(m.group(1).replace("&amp;", "&"), data={"note": ""}, headers=HX)
        out = r.get_data(as_text=True)
        assert r.status_code == 200, out
        assert "Hand-over 1 kept." in out and 'data-state="handed_over"' in out
        assert [w for _a, w in choices_of(out)] == ["Retry with more information…", "Cancel",
                                                    "Hand over…"]
        assert "btn-primary" not in outside_modals(out)

    def test_past_the_cap_the_row_is_cancel_and_hand_over_and_cancel_confirms(self, web):
        iid = plant()
        attempt(web)
        setting(ai_cap_usd_per_incident=0.10)
        sec = section_of(page(web, iid)[1])
        assert [w for _a, w in choices_of(sec)] == ["Cancel", "Hand over…"]
        assert "Retry isn&#39;t available" in sec.split('class="fixit-choices"', 1)[0]
        # Cancel's confirm, pressed: one line recorded, and the row is Hand over… alone (Retry
        # past the cap, Cancel not twice).
        cancel = modal_of(sec, f"fixit-cancel-{iid}")
        m = re.search(r'<button[^>]*hx-post="([^"]+)"', cancel)
        assert m, f"Cancel's modal holds no button that posts: {cancel}"
        r = web.post(m.group(1).replace("&amp;", "&"), headers=HX)
        out = r.get_data(as_text=True)
        assert r.status_code == 200, out
        assert 'data-state="cancelled"' in out
        assert [ln.get("choice") for ln in F.read(incident(iid))["lines"]] == ["cancel"]
        assert [w for _a, w in choices_of(out)] == ["Hand over…"]

    def test_a_proposal_draws_its_card_s_button_as_secondary(self, web, tmp_path):
        iid = plant()
        proposed(web, iid, tmp_path)
        _r, html = page(web, iid)
        sec = section_of(html)
        assert "Open the fix's card…" in sec
        assert [w for _a, w in choices_of(sec)] == ["Retry with more information…", "Cancel",
                                                    "Hand over…"]
        assert "btn-primary" not in outside_modals(sec)
        assert outside_modals(html).count("btn-primary") <= 1, "the page draws one primary"


class TestWhatItFound:
    """The GUI review's AI2 (C3455): one line per subscription, its state in words; the
    addresses, ports and connection numbers one level down, on its line's expand."""

    def test_one_line_per_subscription_the_numbers_one_level_down(self, web):
        """In Firefox (skipped naming why where none runs): each subscription is one line, its
        state in words, no address, port or connection number on it; pressed, the line opens
        to its checks and its flag, where those are."""
        from tests import browser
        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the section's own checks above still run")
        import app as APP
        iid = plant()
        attempt(web)
        read = ("return Array.from(document.querySelectorAll('#inc-ai .fixit-sub')).map("
                "function (d) { var s = d.querySelector('summary'), r = s.getBoundingClientRect(),"
                " lh = parseFloat(getComputedStyle(s).lineHeight) || 18,"
                " u = d.querySelector('.fixit-checks'); return {line: s.textContent.replace("
                "/\\s+/g, ' ').trim(), rows: Math.round(r.height / lh), open: d.open,"
                " shown: u.getClientRects().length > 0 ? u.innerText : ''}; })")
        with browser.Served(APP.app) as srv, browser.Browser() as b:
            try:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": 1280, "height": 900})
                b.go(srv.url(f"/v2/incident/{iid}?list={NET}"))
                b.wait_for("return !!document.querySelector('#inc-ai .fixit-sub')")
                closed = b.js(read)
                b.js("document.querySelector('#inc-ai .fixit-sub > summary')"
                     ".scrollIntoView({block: 'center'})")
                b.click("#inc-ai .fixit-sub > summary")
                b.wait_for("return document.querySelector('#inc-ai .fixit-sub').open")
                opened = b.js(read)
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
        assert [c["line"] for c in closed] == [
            f"Subscription {s}: re-subscribed; the stream did not come back · flagged: stale "
            "half-open" for s in ("101", "102")]
        for c in closed:
            assert c["rows"] == 1 and not c["open"] and not c["shown"], c
            assert not ADDRESS.search(c["line"]) and " port " not in c["line"], c
            assert "connection" not in c["line"], c
        # Pressed, the first line opens to its checks and its flag: moved down, never lost.
        first = opened[0]["shown"]
        assert "port 60999" in first and "connection 985" in first, first
        assert "Flagged: stale half-open: the session from" in first, first
        assert not opened[1]["open"] and not opened[1]["shown"], "only the line pressed opens"

    @pytest.mark.parametrize("remote", ["192.0.2.6", "2001:db8::6"])
    def test_a_run_naming_no_outcome_says_what_its_checks_say(self, monkeypatch, remote):
        from modules.nsot import privileged
        stale = f"stale half-open: the session from {remote} port 60235, there before"
        rec = {"subscriptions": [{"sub": "101", "outcome": "", "stale": [stale, stale],
                                  "verify": {
                                      "device": {"state": "pass", "words": "r2 reads it"},
                                      "stream": {"state": "fail", "words": "no series"},
                                      "collector": {"state": "cant_tell",
                                                    "words": f"the collector at {remote} port "
                                                             "57000 could not be read"}}},
                                 {"sub": "102", "outcome": "not_back", "verify": {}}]}
        monkeypatch.setattr(privileged, "get", lambda net, run_id: rec)
        one, two = S._run_checks(NET, "run-1")
        assert one["said"] == "the stream did not pass; the collector could not be told"
        assert one["flags"] == ["stale half-open"], "each flag's kind once"
        assert not ADDRESS.search(one["said"] + " ".join(one["flags"]))
        assert remote in one["checks"][2]["words"] and remote in one["stale"][0]
        assert two["said"] == "re-subscribed; the stream did not come back"
        assert S.found_said("", []) == "nothing was read"
        assert S.found_said("", [{"name": "stream", "state": "pass"}]) == "every check passed"


class TestTheRepeatsHash:
    """The GUI review's AI3 (C3455): the proposal's warning holds no parameter hash; the hash
    it was compared by is in The record."""

    def test_the_warning_names_no_hash_and_the_record_does(self, web, tmp_path):
        iid = plant()
        proposed(web, iid, tmp_path)
        line = F.read(incident(iid))["lines"][-1]
        hashed = F.params_hash(line["operation"], line["params"])
        _r, html = page(web, iid)
        flag = re.search(r'<p class="fixit-flag".*?</p>', section_of(html), re.S).group(0)
        assert "Proposed before in this incident: attempt 1, failed" in flag
        assert hashed not in flag and "hash" not in flag, flag
        assert hashed not in section_of(html)
        record = html.split('class="card tl-record-d', 1)[1].split("</details>", 1)[0]
        m = re.search(r"<dt>Proposed fix's parameter hash</dt><dd>(.*?)</dd>", record, re.S)
        assert m, record[-600:]
        said = " ".join(re.sub(r"<[^>]+>", " ", m.group(1)).split())
        assert said == f"{hashed} · proposal {line['proposal']} · the same as attempt 1's"


# ── Cancel runs nothing (the operator's test 3, at the route) ───────────────────────────────

class TestCancel:
    def test_one_line_nothing_started_the_page_stays_open(self, web):
        iid = plant()
        attempt(web)
        r = post(web, iid, "cancel")
        out = r.get_data(as_text=True)
        assert r.status_code == 200, out
        assert "Troubleshooting cancelled" in out and 'data-state="cancelled"' in out
        assert sum(web.started.values()) == 0
        lines = F.read(incident(iid))["lines"]
        assert [ln.get("choice") for ln in lines] == ["cancel"] and lines[0]["attempts"] == 1
        assert F.state_of(incident(iid), None) == "cancelled"
        r2, html = page(web, iid)
        assert r2.status_code == 200 and "Troubleshooting cancelled" in section_of(html)
        # Cancelled, Retry stays the way back in; Cancel is not offered twice.
        assert "Retry with more information…" in section_of(html)
        assert "/fixit/cancel" not in section_of(html)

    def test_an_unverified_request_is_refused_and_records_nothing(self, web, monkeypatch):
        iid = plant()
        monkeypatch.setattr("modules.identity.verified_identity", lambda *a, **k: None)
        r = post(web, iid, "cancel")
        assert r.status_code == 403
        assert "verified person&#39;s press" in r.get_data(as_text=True)
        assert F.read(incident(iid))["state"] == "absent"

    def test_an_id_no_record_holds_is_404_said(self, web):
        r = post(web, "hi-000000000000", "cancel")
        assert r.status_code == 404 and "no incident" in r.get_data(as_text=True)


# ── Retry with more information, through Mercury's own proposer ────────────────────────────

@pytest.fixture
def counted(monkeypatch):
    """Mercury's proposer, counted, the real one answering."""
    from modules.fixit import proposers
    real, calls = proposers.mercury, []

    def mercury(*a, **kw):
        calls.append(a)
        return real(*a, **kw)
    monkeypatch.setattr(proposers, "mercury", mercury)
    return calls


def setting(**kw):
    from modules.settings_schema import write_settings
    got = write_settings(kw, actor=ACTOR)
    assert got["ok"], got


class TestRetry:
    def test_it_re_plans_with_mercury_s_diagnosis_flagging_the_repeat(self, web, counted,
                                                                      tmp_path):
        from markupsafe import escape
        iid = plant()
        rec = attempt(web)
        diagnosed(iid, tmp_path)
        web.started.update(dict.fromkeys(web.started, 0))     # the diagnosis's own reads
        _r, html = page(web, iid)
        assert "What the AI would be sent, once it is asked" in html
        assert "Mercury's diagnosis does not read words" in html
        r = post(web, iid, "retry", note="the collector's socket looks stuck",
                 drawn_spent=hidden(html, "drawn_spent"), drawn_cap=hidden(html, "drawn_cap"))
        out = r.get_data(as_text=True)
        assert r.status_code == 200, out
        assert len(counted) == 1
        assert 'data-state="proposed"' in out
        # The failed attempt's outcome in the operation's own words (its whole words are on
        # its line's hover and its card).
        assert rec["outcome"] == "not_back" and rec["why"]
        assert ("Proposed before in this incident: attempt 1, failed: re-subscribed; the "
                "stream did not come back") in out
        assert f'title="{escape(rec["why"])}"' in out
        assert "Open the fix's card…" in out
        (line,) = F.read(incident(iid))["lines"]
        assert line["source"] == "mercury" and line["operation"] == "telemetry-resubscribe"
        assert line["params"] == {"subs": ["101", "102"], "collector_step": False}
        assert line["note"] == "the collector's socket looks stuck"
        assert line["by"] and line["verified"]
        assert sum(web.started.values()) == 0, "a re-plan starts nothing"

    def test_no_diagnosis_is_a_proposal_of_nothing_said(self, web, counted):
        iid = plant()
        attempt(web)
        r = post(web, iid, "retry", note="")
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and len(counted) == 1
        assert "none Mercury can run" in out and "has not diagnosed this incident" in out
        (line,) = F.read(incident(iid))["lines"]
        assert line["operation"] == "" and "has not diagnosed" in line["words"]

    def test_past_the_cap_retry_is_not_offered_and_says_both_figures(self, web, counted):
        iid = plant()
        attempt(web)
        setting(ai_cap_usd_per_incident=0.10)
        _r, html = page(web, iid)
        sec = section_of(html)
        assert "Retry with more information…" not in sec
        from modules.fixit.policy import money
        worst = money(S.worst_usd())                  # the pin's two calls, from its prices
        assert (f"Spent $0.00 in this incident; the next attempt costs at most {worst}, which "
                f"would make {worst} against the cap of $0.10") in sec
        assert "/fixit/cancel" in sec and "Hand over…" in sec
        assert counted == []

    def test_a_press_after_the_cap_moved_is_refused_naming_what_moved(self, web, counted):
        iid = plant()
        attempt(web)
        _r, html = page(web, iid)
        drawn = {"drawn_spent": hidden(html, "drawn_spent"),
                 "drawn_cap": hidden(html, "drawn_cap")}
        assert drawn == {"drawn_spent": "0.000000", "drawn_cap": "1.000000"}
        setting(ai_cap_usd_per_incident=0.10)
        r = post(web, iid, "retry", note="x", **drawn)
        out = r.get_data(as_text=True)
        assert r.status_code == 409, out
        assert "the per-incident cap was $1.00 when the panel was drawn and is $0.10 now" in out
        assert counted == [], "the proposer is not asked past the cap"
        assert F.read(incident(iid))["state"] == "absent", "nothing is recorded"

    def test_an_unverified_press_is_refused_before_the_proposer(self, web, counted,
                                                               monkeypatch):
        iid = plant()
        attempt(web)
        monkeypatch.setattr("modules.identity.verified_identity", lambda *a, **k: None)
        r = post(web, iid, "retry", note="x")
        assert r.status_code == 403 and counted == []


# ── The operation's card from the proposal: the repeat, and the run's record (C3106) ───────

def proposed(web, iid, tmp_path):
    attempt(web)
    diagnosed(iid, tmp_path)
    r = post(web, iid, "retry", note="")
    assert r.status_code == 200
    return F.read(incident(iid))["lines"][-1]["proposal"]


def opened(web, iid, proposal):
    r = web.get(f"/v2/device/r2/resubscribe?list={NET}&subs=101,102&fixit={iid}"
                f"&proposal={proposal}", headers=HX)
    return r.get_data(as_text=True)


def confirm(web, html, **more):
    data = {"sub": ["101", "102"], "reason": REASON, "subs": hidden(html, "subs"),
            "picked": "1", "program": selection_of(html), "previewed": hidden(html, "previewed"),
            "fixit": hidden(html, "fixit"), "proposal": hidden(html, "proposal")}
    for s in ("101", "102"):
        data[f"hash::{s}"] = hidden(html, f"hash::{s}")
    data.update(more)
    return web.post(f"/v2/device/r2/resubscribe/confirm?list={NET}", data=data, headers=HX)


class TestTheCardFromTheProposal:
    def test_a_repeat_is_refused_without_what_is_different(self, web, tmp_path):
        from modules.nsot import privileged
        iid = plant()
        pid = proposed(web, iid, tmp_path)
        html = opened(web, iid, pid)
        assert "This repeats attempt 1, which failed" in html
        assert 'name="different"' in html
        before = len(privileged.runs(NET)["runs"])
        r = confirm(web, html)
        out = r.get_data(as_text=True)
        assert r.status_code == 409, out
        assert "this repeats attempt 1" in out and "Nothing was sent" in out
        assert len(privileged.runs(NET)["runs"]) == before and web.started["job"] == 0

    def test_with_it_the_run_names_the_incident_the_attempt_and_the_proposal(self, web,
                                                                           tmp_path):
        from modules.nsot import privileged
        iid = plant()
        pid = proposed(web, iid, tmp_path)
        html = opened(web, iid, pid)
        r = confirm(web, html, different="the collector was restarted since attempt one")
        assert r.status_code == 200, r.get_data(as_text=True)
        newest = privileged.runs(NET)["runs"][0]
        assert newest[F.RUN_FIELD] == {"incident": iid, "attempt": 2, "proposal": pid,
                                       "different": "the collector was restarted since "
                                                    "attempt one", "repeats": 1}
        tried = F.attempts(incident(iid))["attempts"]
        assert [(a["n"], a["linked"], a["source"]) for a in tried][-1] == (2, "record",
                                                                         "mercury")
        _r, page_html = page(web, iid)
        assert "proposed by Mercury&#39;s diagnosis" in section_of(page_html)

    def test_a_card_for_another_device_s_incident_is_refused(self, web, tmp_path):
        iid = plant()
        got = S.card_link(NET, iid, "", "r9", ["101"])
        assert "r2's incident, and this card is r9's" in got["refused"]
        with pytest.raises(S.Refused, match="Nothing was sent"):
            S.confirm_link(NET, iid, "", "r9", ["101"])

    def test_the_run_field_is_the_one_the_record_reads(self):
        from modules.heal import resubscribe as R
        assert R.FIXIT_FIELD == F.RUN_FIELD
        assert R.fixit_field({"incident": "hi-3f9c1a2b7d40", "attempt": 2, "proposal": "p1",
                              "command": "conf t", "different": True}) == {
            "incident": "hi-3f9c1a2b7d40", "attempt": 2, "proposal": "p1"}
        assert R.fixit_field("hi-x") == {} and R.fixit_field({"attempt": 1}) == {}


# ── Hand over ───────────────────────────────────────────────────────────────────────────────

class TestHandOver:
    def test_with_no_team_it_is_kept_sent_to_nobody_and_its_page_links_back(self, web):
        iid = plant()
        attempt(web)
        r = post(web, iid, "handover", note="read the collector's sessions first")
        out = r.get_data(as_text=True)
        assert r.status_code == 200, out
        assert "Hand-over 1 kept." in out and "no team was chosen" in out
        assert 'data-state="handed_over"' in out and "Open the write-up" in out
        assert web.started["relay"] == 0
        w = web.get(f"/v2/incident/{iid}/handover/1?list={NET}")
        doc = w.get_data(as_text=True)
        assert w.status_code == 200, doc
        for title in ("Summary", "What was tried", "Next steps for an engineer", "Cost"):
            assert title in doc
        assert "read the collector&#39;s sessions first" in doc
        assert f"/v2/incident/{iid}" in doc and "Download as Markdown" in doc
        # C3290: the write-up's time is the viewer's, drawn by the clock, its UTC on the hover;
        # the Markdown, which leaves Mercury, says it in UTC.
        drawn = re.search(r'Handed over <time class="clock" datetime="(\d{4}-\d\d-\d\dT\d\d:\d\dZ)"'
                          r' data-clock[^>]* title="(\d{4}-\d\d-\d\d \d\d:\d\d):00 UTC"', doc)
        assert drawn, doc.split('class="card handover-doc"')[1][:400]
        md = web.get(f"/v2/incident/{iid}/handover/1?list={NET}&download=md")
        assert md.status_code == 200 and md.mimetype == "text/markdown"
        assert md.get_data(as_text=True).startswith(f"# Hand-over 1: {iid}")
        assert f"Handed over {drawn.group(2)} UTC by " in md.get_data(as_text=True)
        _r, html = page(web, iid)
        assert f"/v2/incident/{iid}/handover/1" in html.split('class="card tl-record-d')[1]

    def test_to_a_team_ticked_it_is_sent(self, web):
        iid = plant()
        team = a_team()
        r = post(web, iid, "handover", team=team)
        out = r.get_data(as_text=True)
        assert r.status_code == 200, out
        assert web.started["relay"] == 1 and "Sent" in out
        assert "to Network team" in section_of(out)

    def test_an_unknown_version_is_404_said(self, web):
        iid = plant()
        assert post(web, iid, "handover").status_code == 200
        assert web.get(f"/v2/incident/{iid}/handover/1?list={NET}").status_code == 200
        w = web.get(f"/v2/incident/{iid}/handover/3?list={NET}")
        assert w.status_code == 404 and "No write-up 3 is kept" in w.get_data(as_text=True)


# ── People by display name ──────────────────────────────────────────────────────────────────

class TestNoEmailIsDrawn:
    def test_the_actor_is_drawn_by_display_name_never_their_address(self, web):
        from modules import display_names
        display_names.set_name(ACTOR, NAME, by=ACTOR, actor_verified="access")
        iid = plant()
        attempt(web)
        post(web, iid, "handover")
        _r, html = page(web, iid)
        sec = section_of(html)
        assert ACTOR not in sec and NAME in sec
        w = web.get(f"/v2/incident/{iid}/handover/1?list={NET}").get_data(as_text=True)
        body = w.split("<main", 1)[-1]
        assert ACTOR not in body and "example.invalid" not in body


# ── The setting (C3193) ─────────────────────────────────────────────────────────────────────

class TestTheSetting:
    def test_the_mode_and_the_cap_are_drawn_on_the_ai_tab(self, web):
        from modules.fixit import policy as P
        r = web.get("/v2/settings/installation?tab=ai")
        html = r.get_data(as_text=True)
        assert r.status_code == 200
        assert 'id="card-fixit"' in html and "AI troubleshooting" in html
        assert 'name="ai_troubleshoot_mode"' in html and 'name="ai_cap_usd_per_incident"' in html
        # Saved from what the card drew (its `loaded`), the cap the drawn default.
        card = html.split('id="card-fixit"', 1)[1].split("</section>", 1)[0]
        loaded = re.search(r"name=\"loaded\" value='([^']*)'", card).group(1)
        s = web.post("/v2/settings/installation/card/fixit/save", headers=HX,
                     data={"ai_troubleshoot_mode": "off", "ai_cap_usd_per_incident": "1.00",
                           "loaded": loaded.replace("&#34;", '"')})
        assert s.status_code == 200, s.get_data(as_text=True)
        assert P.mode()["mode"] == "off" and P.cap_usd()["usd"] == 1.0

    def test_the_mode_reads_manual_and_off_capitalised_and_stores_its_key(self, web):
        """The operator, 2026-11-13: "Manual" capitalised. The control's options, its note and
        a saved change's words say Manual and Off; what is posted and stored stays the key."""
        import json

        from modules import installation_settings as I
        from modules.fixit import policy as P
        html = web.get("/v2/settings/installation?tab=ai").get_data(as_text=True)
        card = html.split('id="card-fixit"', 1)[1].split("</section>", 1)[0]
        select = card.split('name="ai_troubleshoot_mode"', 1)[1].split("</select>", 1)[0]
        assert re.findall(r"<option([^>]*)>([^<]*)</option>", select) == [
            (' value="manual" selected', "Manual"), (' value="off"', "Off")], select
        # No lower-case mode is left in the card's words (its note names each mode too).
        words = re.sub(r"<[^>]+>", " ", card.split("</select>", 1)[1])
        assert "Manual: an AI troubleshoot runs only when a person presses it" in words
        assert not re.search(r"\bmanual\b", words), words
        r = web.post("/v2/settings/installation/card/fixit/save", headers=HX,
                     data={"ai_troubleshoot_mode": "off", "ai_cap_usd_per_incident": "1.00",
                           "loaded": json.dumps(I.card("fixit")["loaded"])})
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and "AI mode Manual → Off" in out, out
        assert P.mode()["mode"] == "off"
        row = I.changes(kinds=("card_save",))["rows"][0]
        assert [(c["old"], c["new"]) for c in row["changes"]] == [("manual", "off")]

    def test_a_save_writes_both_recorded_and_the_policy_reads_them(self, web):
        import json

        from modules import installation_settings as I
        from modules.fixit import policy as P
        loaded = json.dumps(I.card("fixit")["loaded"])
        r = web.post("/v2/settings/installation/card/fixit/save",
                     data={"ai_troubleshoot_mode": "off", "ai_cap_usd_per_incident": "0.50",
                           "loaded": loaded}, headers=HX)
        out = r.get_data(as_text=True)
        assert r.status_code == 200, out
        assert "Saved" in out
        assert P.mode()["mode"] == "off" and P.cap_usd()["usd"] == 0.5
        row = I.changes(kinds=("card_save",))["rows"][0]
        assert row["card"] == "fixit" and row["fields"] == ["ai_cap_usd_per_incident",
                                                            "ai_troubleshoot_mode"]

    @pytest.mark.parametrize("cap", ["0", "-1", "", "none"])
    def test_a_cap_that_is_no_positive_amount_is_refused(self, web, cap):
        import json

        from modules import installation_settings as I
        from modules.fixit import policy as P
        loaded = json.dumps(I.card("fixit")["loaded"])
        r = web.post("/v2/settings/installation/card/fixit/save",
                     data={"ai_troubleshoot_mode": "manual", "ai_cap_usd_per_incident": cap,
                           "loaded": loaded}, headers=HX)
        assert r.status_code == 409 and "Not saved" in r.get_data(as_text=True)
        assert P.cap_usd()["usd"] == 1.0


# ── The figures ─────────────────────────────────────────────────────────────────────────────

class TestTheFigures:
    def test_a_retry_s_worst_case_is_two_calls_at_the_pin_s_cap(self):
        from modules.ai import profiles, read_loop
        assert S.CALLS_PER_ATTEMPT == read_loop.CALLS_PER_FINDING
        assert S.worst_usd() == round(2 * profiles.cap_per_call(S.WORST_PIN), 6)
        assert 0 < S.worst_usd() < 1.0, "one retry's worst case fits under the $1.00 default cap"


# ── On a projector: 1920x1080, nothing scrolls inside the section ───────────────────────────

class TestOnAProjector:
    """In Firefox (where one runs; skipped naming why elsewhere), at 1920x1080 (the board's
    "readable at 1920x1080 on a projector, with no inner scroll"): with a failed attempt, and
    Retry's and Hand over's modals each opened in turn (C3455: each choice is a modal), no
    element of the section scrolls inside itself, and each attempt is one line."""

    def test_no_element_of_the_section_scrolls_inside_itself(self, web):
        from tests import browser
        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the section's own checks above still run")
        import app as APP
        iid = plant()
        attempt(web)
        scrolls, opened = {}, {}
        with browser.Served(APP.app) as srv, browser.Browser() as b:
            try:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": 1920, "height": 1080})
                b.go(srv.url(f"/v2/incident/{iid}?list={NET}"))
                b.wait_for("return !!document.querySelector('#inc-ai .fixit-choices')")
                # Retry's modal and Hand over's opened as a person opens them, one at a time.
                for key in ("retry", "hand"):
                    mid = f"fixit-{key}-{iid}"
                    b.click(f'#inc-ai [data-modal-open="{mid}"]')
                    opened[key] = b.wait_for(f"return document.getElementById('{mid}').open")
                    scrolls[key] = b.js(
                        "return Array.prototype.filter.call(document.querySelectorAll("
                        "'#inc-ai, #inc-ai *'), function (e) { var o = getComputedStyle(e);"
                        "return (o.overflowY === 'auto' || o.overflowY === 'scroll' || "
                        "o.overflowX === 'auto' || o.overflowX === 'scroll') && "
                        "(e.scrollHeight > e.clientHeight + 1 || "
                        "e.scrollWidth > e.clientWidth + 1);}).length")
                    b.js(f"document.getElementById('{mid}').close()")
                lines = b.js("var a = document.querySelector('#inc-ai .fixit-a');"
                             "var lh = parseFloat(getComputedStyle(a).lineHeight) || 18;"
                             "return Math.round(a.getBoundingClientRect().height / lh);")
                wide = b.js("return document.documentElement.scrollWidth <= "
                            "document.documentElement.clientWidth")
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
        assert opened == {"retry": True, "hand": True}, opened
        assert scrolls == {"retry": 0, "hand": 0}, \
            "something scrolls inside the AI troubleshooting section"
        assert lines <= 2, f"an attempt's line wraps to {lines} lines at 1920"
        assert wide, "the page scrolls sideways at 1920"


# ── C3455: each choice's modal in a real browser ────────────────────────────────────────────

#: WebDriver's Escape key.
ESCAPE = ""

#: Where the modal *mid* and its opener are, and where the focus is: ``{"open", "modal",
#: "focus_in", "focus_on_opener", "dialog", "opener", "vw", "vh"}``.
WHERE = """
var d = document.getElementById(arguments[0]);
var o = document.querySelector('[data-modal-open="' + arguments[0] + '"]');
var a = document.activeElement, r = d.getBoundingClientRect(), q = o.getBoundingClientRect();
return {open: d.open, modal: d.matches(':modal'), focus_in: d.contains(a) && a !== d,
        focus_on_opener: a === o,
        dialog: [r.left, r.top, r.right, r.bottom], opener: [q.left, q.top, q.right, q.bottom],
        vw: document.documentElement.clientWidth, vh: window.innerHeight};
"""


def press_key(b, key):
    b._call("POST", f"/session/{b.session}/actions", {"actions": [
        {"type": "key", "id": "keyboard", "actions": [{"type": "keyDown", "value": key},
                                                       {"type": "keyUp", "value": key}]}]})
    b._call("DELETE", f"/session/{b.session}/actions")


def anchored(w: dict) -> str:
    """Why the modal is not anchored to its opener, or ``""``: just below it or just above it
    (within 12 px), its left edge at the opener's unless the window's gutter moved it, and
    inside the window."""
    left, top, right, bottom = w["dialog"]
    oleft, otop, _oright, obottom = w["opener"]
    below = 0 <= top - obottom <= 12
    above = 0 <= otop - bottom <= 12
    if not (below or above):
        return (f"the modal {w['dialog']} is not just below its opener {w['opener']} nor just "
                f"above it (the window {w['vw']}x{w['vh']})")
    want = max(16, min(oleft, w["vw"] - 16 - (right - left)))
    if abs(left - want) > 1:
        return f"the modal's left {left} is not the opener's {oleft} (kept inside: {want})"
    if left < 0 or top < 0 or right > w["vw"] or bottom > w["vh"]:
        return f"the modal {w['dialog']} leaves the window {w['vw']}x{w['vh']}"
    return ""


class TestTheModals:
    """In Firefox (skipped naming why where none runs): each of the three choices opens its
    modal on its press, anchored to it, with the focus inside it and the page behind it inert
    (`:modal`); Escape closes it and the focus is back on its button; Cancel's confirm records
    its one line, answered in the section in place, the focus on the answer (the operator's rule
    of 2026-11-12; C3455)."""

    def test_each_choice_opens_its_modal_anchored_and_escape_gives_the_focus_back(self, web):
        from tests import browser
        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the section's own checks above still run")
        import app as APP
        iid = plant()
        attempt(web)
        seen, after, closed_by_cancel, confirmed = {}, {}, None, None
        with browser.Served(APP.app) as srv, browser.Browser() as b:
            try:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": 1280, "height": 900})
                b.go(srv.url(f"/v2/incident/{iid}?list={NET}"))
                b.wait_for("return !!document.querySelector('#inc-ai .fixit-choices')")
                for key in ("retry", "cancel", "hand"):
                    mid = f"fixit-{key}-{iid}"
                    b.js("document.querySelector(arguments[0]).scrollIntoView({block: 'center'})",
                         f'[data-modal-open="{mid}"]')
                    b.click(f'#inc-ai [data-modal-open="{mid}"]')
                    b.wait_for(f"return document.getElementById('{mid}').open")
                    seen[key] = b.js(WHERE, mid)
                    press_key(b, ESCAPE)
                    b.wait_for(f"return !document.getElementById('{mid}').open")
                    after[key] = b.js(WHERE, mid)
                # Retry's own Cancel closes it too, and gives the focus back.
                mid = f"fixit-retry-{iid}"
                b.click(f'#inc-ai [data-modal-open="{mid}"]')
                b.wait_for(f"return document.getElementById('{mid}').open")
                b.click(f"#{mid} [data-modal-close]")
                b.wait_for(f"return !document.getElementById('{mid}').open")
                closed_by_cancel = b.js(WHERE, mid)
                # Cancel's confirm: its one line recorded, the answer drawn in place.
                mid = f"fixit-cancel-{iid}"
                b.click(f'#inc-ai [data-modal-open="{mid}"]')
                b.wait_for(f"return document.getElementById('{mid}').open")
                b.click(f"#{mid} button[data-op]")
                b.wait_for("return document.querySelector('#inc-ai').dataset.state === "
                           "'cancelled'")
                confirmed = b.wait_for(
                    "var a = document.activeElement; return !document.getElementById("
                    f"'{mid}') && a && a.classList.contains('set-result') && "
                    "document.querySelector('#inc-ai').contains(a) && a.textContent.trim()")
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
        for key, w in seen.items():
            assert w["open"] and w["modal"], f"{key}'s modal did not open as a modal: {w}"
            assert w["focus_in"], f"{key}'s modal opened without the focus inside it"
            assert anchored(w) == "", f"{key}: {anchored(w)}"
        for key, w in after.items():
            assert not w["open"] and w["focus_on_opener"], \
                f"Escape on {key}'s modal left {w} (the focus is not back on its button)"
        assert not closed_by_cancel["open"] and closed_by_cancel["focus_on_opener"]
        assert confirmed and confirmed.startswith("Cancelled: one line recorded"), confirmed
        assert [ln.get("choice") for ln in F.read(incident(iid))["lines"]] == ["cancel"]
        assert sum(web.started.values()) == 0
