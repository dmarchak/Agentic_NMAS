"""A self-healing proposal on Needs attention (board H, artboard E; parts H5 and H9;
docs/HEAL_TO_INTENT.md sections 9 and 11), through the real app: its row
(`attention.heal_source`, kind ``heal``/``proposal``), its card (`templates/v2/_heal_proposal.html`,
read by routes/heal_proposal_v2.proposal) and its two controls, on test_heal_propose's lab (a
real proposal on edge-b made by the real decision, its sources faked). No device, no network.

- **The row** names what is wrong (a fix waits for a person on the device) and its action
  (Review the fix…, which opens the row to its card), and says how it clears.
- **The card** says what approving sends and to which device: the program as recorded, the
  measured process reset, its effects, verify and rollback, and the proposal's hash in the
  form; an unmeasured reset draws Approve disabled with why.
- **Approve, pressed** with the hash and a reason, starts the heal as the verified person and
  draws its answer in place; the row leaves. Refused with nothing taken when the proposal moved
  since the card was drawn (naming both hashes), without a reason, or for a caller who is not a
  verified person.
- **Decline, pressed** with a reason, is recorded as the person and sends nothing; the row
  leaves.
"""

import re

import pytest

from tests.test_heal_decide import lab  # noqa: F401  (the fixture, named by each test below)
from tests.test_heal_propose import (DS, R8, REASON, SL, FakeApproved, measured,  # noqa: F401
                                     proposed)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

HX = {"HX-Request": "true"}


@pytest.fixture
def app_client(lab, monkeypatch):
    """The real app's client; propose reads the device through the fake sources, and a started
    heal is recorded rather than run (tests/test_heal_propose.py runs the act itself)."""
    import app as A

    started = []
    monkeypatch.setattr("modules.heal.propose.Sources", lambda net: FakeApproved(R8))
    monkeypatch.setattr("modules.heal.propose.start",
                        lambda n, taken, approval, **kw: started.append(approval) or "j-1")
    A.app.config["TESTING"] = True
    c = A.app.test_client()
    c.started = started
    return c


def _rows():
    from modules import attention

    return [r for r in attention.heal_source()["rows"] if r["kind"] == "proposal"]


def _base(d):
    return f"/v2/network/Default/heal/proposal/{d['id']}"


def _card(client, d):
    r = client.get(_base(d), headers=HX)
    return r, r.get_data(as_text=True)


def _hidden(html, name):
    m = re.search(rf'<input type="hidden" name="{name}" value="([^"]*)">', html)
    assert m, f"no hidden {name}"
    return m.group(1)


def _release(d):
    from tests.test_heal_propose import INT

    INT.release("Default", d["id"])


# ── The row ─────────────────────────────────────────────────────────────────────────────────

def test_a_proposal_is_one_row_naming_the_fix_and_how_it_clears(app_client, measured):
    from modules.attention import CLEARS, ROW_KINDS

    d = proposed()
    (r,) = _rows()
    assert r["what"].startswith("A fix waits for a person on edge-b: a fix that takes effect "
                                "only through a process reset")
    assert r["action"]["open"] == "heal_proposal" and r["action"]["decision"] == d["id"]
    assert r["level"] == "warning" and r["devices"] == ["edge-b"]
    assert ("heal", "proposal") in ROW_KINDS
    assert r["clears"]["when"] == CLEARS[("heal", "proposal")][1]
    assert "approves it on its card" in r["clears"]["when"]


def test_needs_attention_draws_review_the_fix_and_the_card_it_opens(app_client, measured,
                                                                    monkeypatch):
    from modules import attention, csp

    d = proposed()
    monkeypatch.setattr(attention, "SOURCES", [attention.heal_source])
    r = app_client.get("/v2/attention")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
    assert "A fix waits for a person on edge-b" in html
    # Review the fix… jumps to the card's slot, which the row loads when it is opened, naming
    # its opener (tests/test_next_steps_act.py's OPENERS).
    assert f'class="btn btn-small btn-outline att-jump" data-op="heal-proposal" ' \
           f'data-next-acts="heal_proposal" href="#heal-prop-{d["id"]}">Review the fix…</a>' \
           in html
    assert (f'id="heal-prop-{d["id"]}" hx-get="{_base(d)}" '
            'hx-trigger="toggle once from:closest details.att"') in html
    assert "Clears when a person approves it on its card" in html
    # Opened: the slot's own request draws the card, and reading it writes nothing.
    before = DS.read("Default")
    card = app_client.get(_base(d), headers=HX).get_data(as_text=True)
    assert f'id="heal-prop-{d["id"]}" data-holds-live="review"' in card
    assert DS.read("Default") == before, "opening the row writes nothing"


# ── The card ────────────────────────────────────────────────────────────────────────────────

def test_the_card_says_what_approving_sends_and_to_which_device(app_client, measured):
    from modules import csp
    from modules.heal import propose

    d = proposed()
    r, html = _card(app_client, d)
    assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
    v = propose.view("Default", d["id"])
    assert _hidden(html, "hash") == v["hash"]
    for line in v["program"]:
        assert line.strip() in html, line
    assert "! then: clear ip ospf 1 process (its prompt measured on edge-b, 2026-11-10T00:00:00Z)" \
        in html
    assert "every OSPF adjacency of process 1 on edge-b" in html
    assert "a reset cannot be undone" in html
    assert ">Approve and run on edge-b<" in html and ">Decline<" in html
    assert "Check drift now on edge-b" in html and "op=drift_check" in html
    assert 'data-holds-live="review"' in html
    assert f'hx-post="{_base(d)}/approve"' in html and f'hx-post="{_base(d)}/decline"' in html
    # What is confirmed is what is sent: pressed, Approve's form sends the hash drawn, and the
    # heal starts bound to exactly that hash.
    r = app_client.post(_base(d) + "/approve",
                        data={"hash": _hidden(html, "hash"), "reason": REASON}, headers=HX)
    try:
        assert r.status_code == 200
        (approval,) = app_client.started
        assert approval["hash"] == v["hash"] and approval["reset"]["command"] == \
            "clear ip ospf 1 process"
    finally:
        _release(d)


def test_an_unmeasured_reset_draws_approve_disabled_saying_why(app_client):
    d = proposed()
    _r, html = _card(app_client, d)
    assert "Not confirmable:</strong>" in html and "is not measured on cisco_iosxe" in html
    approve = html.split("Approve and run on edge-b")[0].rsplit("<button", 1)[1]
    assert " disabled " in approve and "is not measured" in approve
    assert "! then: clear ip ospf 1 process (not measured)" in html
    # Sent anyway (as a script could), it is refused with nothing taken.
    r = app_client.post(_base(d) + "/approve",
                        data={"hash": _hidden(html, "hash"), "reason": REASON}, headers=HX)
    assert r.status_code == 409 and "is not measured" in r.get_data(as_text=True)
    assert app_client.started == [] and [x["id"] for x in DS.proposals("Default")] == [d["id"]]


def test_a_proposal_no_longer_held_says_so_in_place(app_client):
    d = proposed()
    r = app_client.post(_base(d) + "/decline", data={"reason": "not during the lab"},
                        headers=HX)
    assert r.status_code == 200 and DS.proposals("Default") == []
    # Declined in another tab: Approve pressed on the card left open is refused, and the card
    # drawn again says who took it, its Approve not pressable.
    again = app_client.post(_base(d) + "/approve", data={"hash": "x", "reason": REASON},
                            headers=HX)
    html = again.get_data(as_text=True)
    assert again.status_code == 409 and "was taken by" in html and "is declined" in html
    approve = html.split("Approve and run on edge-b")[0].rsplit("<button", 1)[1]
    assert " disabled " in approve
    gone = app_client.get("/v2/network/Default/heal/proposal/hd-000000000000", headers=HX)
    assert gone.status_code == 404 and "Couldn't load the proposal:" in gone.get_data(
        as_text=True)
    assert app_client.started == []


# ── Approve ─────────────────────────────────────────────────────────────────────────────────

def test_approve_pressed_starts_the_heal_as_the_person_and_the_row_clears(app_client,
                                                                         measured):
    from tests.conftest import TEST_PERSON

    d = proposed()
    _r, html = _card(app_client, d)
    r = app_client.post(_base(d) + "/approve",
                        data={"hash": _hidden(html, "hash"), "reason": REASON}, headers=HX)
    out = r.get_data(as_text=True)
    try:
        assert r.status_code == 200, out
        assert "Approved by you:</strong> its heal runs as you on edge-b (job" in out
        assert "j-1" in out and "Approve and run" not in out
        assert "drift" in r.headers["X-NMAS-Invalidates"]
        (approval,) = app_client.started
        assert approval["by"] == TEST_PERSON and approval["reason"] == REASON
        assert DS.find("Default", d["id"])["taken"]["by"] == f"{TEST_PERSON}: approved"
        assert _rows() == [], "the row leaves once approved"
    finally:
        _release(d)


def test_approve_after_the_proposal_moved_is_refused_naming_both(app_client, measured,
                                                                 monkeypatch):
    from modules.heal import propose

    d = proposed()
    _r, html = _card(app_client, d)
    drawn = _hidden(html, "hash")
    # The proposal moves after the card was drawn: its hash is now another.
    monkeypatch.setattr(propose, "proposal_hash", lambda *a, **k: "0" * 16)
    r = app_client.post(_base(d) + "/approve", data={"hash": drawn, "reason": REASON},
                        headers=HX)
    out = r.get_data(as_text=True)
    assert r.status_code == 409
    assert f"confirmed {drawn}, now {'0' * 16}" in out and "nothing was taken or sent" in out
    assert f'value="{REASON}"' in out, "the reason typed is kept"
    assert _hidden(out, "hash") == "0" * 16, "the card is drawn again with the hash now"
    assert app_client.started == [] and len(_rows()) == 1, "nothing taken; the row stays"


def test_approve_without_a_reason_is_refused_with_nothing_taken(app_client, measured):
    d = proposed()
    _r, html = _card(app_client, d)
    r = app_client.post(_base(d) + "/approve", data={"hash": _hidden(html, "hash"),
                                                     "reason": "ok"}, headers=HX)
    out = r.get_data(as_text=True)
    assert r.status_code == 409 and "needs a reason of 3 words or more" in out
    assert app_client.started == [] and len(_rows()) == 1


@pytest.mark.real_identity
def test_a_caller_who_is_not_a_verified_person_is_refused_before_anything(app_client,
                                                                          measured):
    d = proposed()
    for path, data in (("/approve", {"hash": "x", "reason": REASON}),
                       ("/decline", {"reason": REASON})):
        r = app_client.post(_base(d) + path, data=data, headers=HX)
        assert r.status_code in (401, 403), (path, r.status_code)
    assert app_client.started == [] and len(_rows()) == 1


# ── Decline ─────────────────────────────────────────────────────────────────────────────────

def test_decline_pressed_is_recorded_as_the_person_and_the_row_clears(app_client):
    from tests.conftest import TEST_PERSON

    d = proposed()
    r = app_client.post(_base(d) + "/decline", data={"reason": "not during the lab"},
                        headers=HX)
    out = r.get_data(as_text=True)
    assert r.status_code == 200, out
    assert f"Declined:</strong> declined by {TEST_PERSON}: not during the lab" in out
    assert "Nothing was sent to edge-b" in out and "drift" in r.headers["X-NMAS-Invalidates"]
    (act,) = [x for x in SL.read("Default")["rows"] if x.get("row") == "act"]
    assert act["by"] == TEST_PERSON and act["outcome"] == "declined"
    assert DS.proposals("Default") == [] and _rows() == [] and app_client.started == []


def test_decline_without_a_reason_is_refused_in_place(app_client):
    d = proposed()
    r = app_client.post(_base(d) + "/decline", data={"reason": ""}, headers=HX)
    assert r.status_code == 409 and "needs a reason" in r.get_data(as_text=True)
    assert len(_rows()) == 1


# ── Enter in the reason field (C2472) ───────────────────────────────────────────────────────

def test_enter_in_the_reason_field_approves_nothing_and_approve_pressed_does(
        app_client, measured, monkeypatch):
    """C2472, in a real browser: on a confirmable card, a person types a reason and presses
    Enter (perhaps meaning to decline). Nothing is approved and the card keeps what was typed;
    pressing Approve then approves, once."""

    import time

    from tests import browser

    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as A
    from modules import attention

    monkeypatch.setattr(attention, "SOURCES", [attention.heal_source])
    d = proposed()
    field = f"#heal-prop-{d['id']}-why"
    try:
        with browser.Served(A.app) as served, browser.Browser() as b:
            b.go(served.url("/v2/"))
            b.wait_for(f"return !!document.querySelector('a.att-jump[href=\"#heal-prop-"
                       f"{d['id']}\"]')", 15)
            b.js(f"document.querySelector('a.att-jump[href=\"#heal-prop-{d['id']}\"]').click();"
                 " return 1")
            b.wait_for(f"return !!document.querySelector('{field}')", 15)
            approve = f"#heal-prop-{d['id']} button.btn-primary[data-op=heal-proposal]"
            assert b.js(f"return !document.querySelector('{approve}').disabled"), \
                "floor: the card is confirmable, so Approve is enabled"
            # Every request the page issues, and a mark a native submission (a navigation)
            # would wipe.
            b.js("window.__sent = []; window.__same_page = 1; document.body.addEventListener("
                 "'htmx:beforeRequest', function (e) { window.__sent.push("
                 "e.detail.requestConfig.verb + ' ' + e.detail.requestConfig.path); }); "
                 "return 1")
            b.type(field, REASON + "\ue007")                 # WebDriver's Enter key
            # Bounded: Enter's submission, if any, is issued at once; 3 s is far past it.
            until = time.monotonic() + 3
            while time.monotonic() < until and b.js(
                    "return window.__same_page === 1 && window.__sent.length === 0"):
                time.sleep(0.1)
            assert b.js("return window.__same_page === 1 ? window.__sent : 'navigated'") == [], \
                "Enter in the reason field submitted something"
            assert app_client.started == [], "Enter in the reason field approved"
            assert b.js(f"return document.querySelector('{field}').value") == REASON, \
                "the card keeps what was typed"
            b.click(approve)
            b.wait_for(f"return /Approved by you/.test(document.querySelector("
                       f"'#heal-prop-{d['id']}').textContent)", 15)
            posts = [s for s in b.js("return window.__sent") if s.startswith("post ")]
            assert posts == [f"post {_base(d)}/approve"], posts    # then the panels re-fetch
        (approval,) = app_client.started
        assert approval["reason"] == REASON
    finally:
        _release(d)


# ── Withdrawn (C2470) ───────────────────────────────────────────────────────────────────────

def test_a_withdrawn_proposal_s_card_says_why_and_approve_is_refused(app_client, measured):
    from tests.test_heal_propose import R8_AGAIN, _Check, _dep, _pass

    d = proposed()
    _r, html = _card(app_client, d)
    drawn = _hidden(html, "hash")
    assert "If edge-b changes, the proposal is withdrawn and made again" in html
    _pass(d["epoch"] + 121, _Check(R8_AGAIN))
    r, html = _card(app_client, d)
    assert r.status_code == 200
    assert "Withdrawn, no longer waiting:</strong> edge-b changed since it was proposed" in html
    assert d["departure"] in html and _dep(R8_AGAIN) in html, "both departures named"
    assert "Approve and run" not in html and _rows() == []
    r = app_client.post(_base(d) + "/approve", data={"hash": drawn, "reason": REASON},
                        headers=HX)
    out = r.get_data(as_text=True)
    assert r.status_code == 409 and "Not done:</strong> not approved: the proposal you " \
        f"confirmed ({drawn}" in out and "is no longer waiting" in out
    assert app_client.started == []


# ── The halted row and Lift the halt (C2471) ────────────────────────────────────────────────

def _halt(guard=14, device="edge-b"):
    return DS.halt("Default", guard=guard, name="a rolled-back heal",
                   words=f"the heal of {device} (hd-1) was rolled back: verify failed",
                   operands={"decision": "hd-1", "device": device})


def _halted_rows():
    from modules import attention

    return [r for r in attention.heal_source()["rows"] if r["kind"] == "halted"]


def _lift_url(h):
    return f"/v2/network/Default/heal/halt/{h['id']}/lift"


def test_a_halt_is_one_critical_row_naming_its_guard_and_how_it_clears(app_client):
    from modules.attention import CLEARS, ROW_KINDS

    assert _halted_rows() == [], "no halt, no row"
    h = _halt()
    (r,) = _halted_rows()
    assert r["level"] == "danger" and r["devices"] == ["edge-b"]
    assert r["what"] == "Self-healing halted on Default: a rolled-back heal"
    assert "Guard 14, a rolled-back heal: the heal of edge-b (hd-1) was rolled back" in r["cause"]
    assert r["action"]["open"] == "heal_halt" and r["action"]["halt"] == h["id"]
    assert ("heal", "halted") in ROW_KINDS
    assert r["clears"]["when"] == CLEARS[("heal", "halted")][1]


def test_needs_attention_draws_lift_the_halt_with_its_reason_outside_any_form(app_client,
                                                                             monkeypatch):
    from modules import attention, csp

    h = _halt()
    monkeypatch.setattr(attention, "SOURCES", [attention.heal_source])
    r = app_client.get("/v2/attention")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
    assert "Self-healing halted on Default: a rolled-back heal" in html
    assert (f'data-next-acts="heal_halt" href="#heal-halt-{h["id"]}">Lift the halt…</a>'
            in html)
    card = html.split(f'<div class="heal-halt" id="heal-halt-{h["id"]}"')[1].split(
        "</div>\n</div>")[0]
    assert "data-holds-live" not in card, "drawn by the list, it holds no redraw"
    assert f'<input id="heal-halt-{h["id"]}-why" name="reason" type="text"' in card
    # C2472: no form owns the reason, so Enter in it submits nothing; the button sends it.
    assert "<form" not in card
    assert (f'hx-post="{_lift_url(h)}" hx-include="#heal-halt-{h["id"]}-why"' in card)
    assert ">Lift the halt<" in card and "Lifting…" in card and 'hx-disabled-elt="this"' in card
    assert "Edit edge-b's intent…" in card and "Open the incident" in card
    assert "Clears when a person lifts the halt on this item with a reason" in html
    # Pressed as drawn: the button posts its own URL with the included field, and it lifts.
    url = re.search(r'hx-post="([^"]+)" hx-include="#heal-halt-', card).group(1)
    r = app_client.post(url, data={"reason": "the statement is now in intent"}, headers=HX)
    assert r.status_code == 200 and "Lifted by you:" in r.get_data(as_text=True)
    assert DS.halted("Default") == {}


def test_lift_pressed_is_recorded_as_the_person_and_the_row_clears(app_client):
    from tests.conftest import TEST_PERSON

    h = _halt()
    r = app_client.post(_lift_url(h), data={"reason": "the statement is now in intent"},
                        headers=HX)
    out = r.get_data(as_text=True)
    assert r.status_code == 200, out
    assert "Lifted by you:</strong> self-healing on Default runs again" in out
    assert "the statement is now in intent" in out and 'data-holds-live="review"' in out
    assert "drift" in r.headers["X-NMAS-Invalidates"]
    assert DS.halted("Default") == {} and _halted_rows() == []
    assert DS.halt_row("Default", h["id"])["lifted"]["by"] == TEST_PERSON


def test_lift_without_a_reason_is_refused_in_place_keeping_what_was_typed(app_client):
    h = _halt()
    r = app_client.post(_lift_url(h), data={"reason": "ok then"}, headers=HX)
    out = r.get_data(as_text=True)
    assert r.status_code == 409
    assert "Not lifted:</strong> a halt is lifted with a reason of 3 words or more" in out
    assert 'value="ok then"' in out and "Guard 14, a rolled-back heal" in out
    assert DS.halted("Default")["id"] == h["id"] and len(_halted_rows()) == 1


def test_lift_of_a_halt_not_in_force_names_both_and_who_lifted_it(app_client):
    from tests.conftest import TEST_PERSON

    h = _halt()
    app_client.post(_lift_url(h), data={"reason": "the statement is now in intent"},
                    headers=HX)
    r = app_client.post(_lift_url(h), data={"reason": "lifting it again now"}, headers=HX)
    out = r.get_data(as_text=True)
    assert r.status_code == 409
    assert f"the halt in force is none, not {h['id']} (lifted by {TEST_PERSON}" in out
    r = app_client.post("/v2/network/Default/heal/halt/hh-000000000000/lift",
                        data={"reason": "the wrong one entirely"})
    assert r.status_code == 409 and r.get_json()["error"].startswith(
        "the halt in force is none, not hh-000000000000")


@pytest.mark.real_identity
def test_a_caller_who_is_not_a_verified_person_cannot_lift(app_client):
    h = _halt()
    r = app_client.post(_lift_url(h), data={"reason": "the statement is now in intent"},
                        headers=HX)
    assert r.status_code in (401, 403), r.status_code
    assert DS.halted("Default")["id"] == h["id"]


def test_lift_refuses_a_request_that_is_not_a_person_s(lab):
    h = _halt()
    with pytest.raises(DS.NotAPerson, match="actor svc, verified token"):
        DS.lift("Default", h["id"], by="svc", actor_verified="token", person=False,
                reason="the statement is now in intent")
    assert DS.halted("Default")["id"] == h["id"]


def test_the_kill_switch_is_a_halted_row_whose_way_out_is_resume(app_client, monkeypatch):
    from modules.heal import policy

    monkeypatch.setattr(policy, "stopped", lambda: {
        "stopped": True, "state": "ok", "by": "op@example.com", "at": "2026-11-04T00:00:00Z",
        "why": "", "words": "self-healing is stopped everywhere by op@example.com"})
    (r,) = _halted_rows()
    assert r["what"] == ("Self-healing is stopped everywhere: the installation's kill switch, "
                         "by op@example.com")
    assert r["action"]["href"] == "/v2/settings/network/Default?tab=heal"
    assert "Resume self-healing…" in r["action"]["label"] and "open" not in r["action"]


# ── Registered ──────────────────────────────────────────────────────────────────────────────

def test_the_routes_are_the_apps_and_gated_as_declared():
    import app as A

    from modules.route_gates import GATES

    rules = {r.endpoint: r for r in A.app.url_map.iter_rules()
             if r.endpoint.startswith("heal_proposal_v2.")}
    assert set(rules) == {"heal_proposal_v2.proposal", "heal_proposal_v2.approve",
                          "heal_proposal_v2.decline", "heal_proposal_v2.lift"}
    assert GATES["heal_proposal_v2.approve"].kind == "confirm"
    assert GATES["heal_proposal_v2.decline"].kind == "configure"
    assert GATES["heal_proposal_v2.lift"].kind == "configure"
