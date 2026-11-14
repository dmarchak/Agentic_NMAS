"""Re-subscribe a lost telemetry stream on Needs attention (C2838; routes/resubscribe_v2.py,
templates/v2/_resubscribe.html), through the real app, on tests/test_heal_resubscribe.py's lab
(r2's real configuration on a box, its real intent, the verify's reads in turn). No device, no
network.

- **The row:** a lost-stream alert group of one device (`attention.grafana_source`) carries
  Re-subscribe <device>'s telemetry (<ids>)… as its action; a group with another rule in it, or
  two devices, does not.
- **The card:** outcome first, each subscription ticked with intent's receiver line and its own
  hash in the form, the exact program one level down, the button named for the work and busy on
  itself, its How does this work? beside it.
- **Pressed:** the run starts as the verified person and its result is drawn in place, never
  green over a partial; a moved hash is refused naming both, with nothing sent.
- **Removed:** a receiver a run left removed leads the card in danger, with Re-add the receiver,
  which puts it back.
"""
import re
import time

import pytest

# The operation the card runs (C2838). Both clients' fixtures replace its sources, so nothing
# here can be set up where the module is absent: the file says so at its import.
import modules.heal.resubscribe  # noqa: F401
from tests.test_heal_resubscribe import LINE, NET, REASON, Box, Src, lab  # noqa: F401
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

HX = {"HX-Request": "true"}
BASE = "/v2/device/r2/resubscribe"


@pytest.fixture
def client(lab, monkeypatch):  # noqa: F811
    """The real app's client; the operation's sources are the lab's, and a started run is run
    in the request's thread (the job registry's thread is the job's own concern)."""
    import app as A

    state = {"src": Src()}
    monkeypatch.setattr("modules.heal.resubscribe.Sources",
                        lambda net, **kw: state["src"])
    monkeypatch.setattr("modules.nsot.capture_job.start",
                        lambda lst, label, actor, work, **kw: (work("j-1"), "j-1")[1])
    A.app.config["TESTING"] = True
    c = A.app.test_client()
    c.state = state
    return c


def card(client, subs="101,102", ticked=None):
    """The card as the row opens it for *subs*; with *ticked*, as a changed tick draws it
    again (the form's ``picked`` and each ticked ``sub``)."""
    query = f"list={NET}&subs={subs}"
    if ticked is not None:
        query += "&picked=1" + "".join(f"&sub={s}" for s in ticked)
    r = client.get(f"{BASE}?{query}", headers=HX)
    return r, r.get_data(as_text=True)


def program_drawn(html):
    """The exact program the card drew, its lines in order (the wait among them)."""
    import html as H
    blocks = re.findall(r'<pre class="ask-pre">(.*?)</pre>', html, re.S)
    assert len(blocks) == 1, f"{len(blocks)} program blocks drawn"
    return H.unescape(blocks[0]).split("\n")


def lines_for(sub, line):
    return ["configure terminal", f"telemetry ietf subscription {sub}", f" {line}", "end"]


def sent(client):
    """What the device was sent, as (subscription, removal or re-add) in order."""
    return [(b[1].rsplit(" ", 1)[1], "remove" if b[2].startswith(" no ") else "add")
            for b in client.state["src"].box.batches]


def hidden(html, name):
    m = re.search(rf'<input type="hidden" name="{re.escape(name)}" value="([^"]*)">', html)
    assert m, f"no hidden {name}"
    return m.group(1)


def selection_of(html):
    """The selection's hash as the card's confirm button carries it (the one confirm
    pattern: the button's own `hx-vals` holds the field its route binds the confirm to)."""
    m = re.search(r'hx-post="/v2/device/r2/resubscribe/confirm[^"]*" '
                  r'hx-vals=\'\{"program": "([0-9a-f]*)"\}\'', html)
    assert m, "the confirm button carries no selection hash"
    return m.group(1)


def readd_hash(html, sub):
    """The hash the Re-add the receiver button for *sub* carries."""
    m = re.search(rf'id="resub-r2-readd-{sub}".*?hx-post="/v2/device/r2/resubscribe/readd[^"]*" '
                  r'hx-vals=\'\{"hash": "([0-9a-f]*)"\}\'', html, re.S)
    assert m, f"no Re-add the receiver button carrying a hash for {sub}"
    return m.group(1)


# ── The row ─────────────────────────────────────────────────────────────────────────────────

def _instance(device, rule, n):
    starts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600))
    return {"kind": "no_data", "device": device, "device_from": "label", "address": "",
            "rule": rule, "rule_uid": f"tel-{device}-{n}", "state": "Alerting (NoData)",
            "fingerprint": f"fp{n}", "starts_at": starts, "window_seconds": 90,
            "labels": {"device": device}, "silences": []}


def _rows(*instances):
    from modules import attention
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cached = {"state": "ok", "doc": {"last_good": {"value_at": now, "value": {
        "rules": [], "instances": list(instances), "counts": {}}}}}
    return [r for r in attention.grafana_source(cached)["rows"] if r["kind"] == "incident"]


class TestTheRow:
    def test_a_lost_stream_group_offers_re_subscribe(self, lab):  # noqa: F811
        rows = _rows(_instance("r2", "NMAS telemetry stream lost: r2 subscription 101", 1),
                     _instance("r2", "NMAS telemetry stream lost: r2 subscription 102", 2))
        (row,) = rows
        assert row["what"] == "r2: 2 telemetry streams lost (101, 102)"
        a = row["action"]
        assert (a["open"], a["device"], a["subs"]) == ("resubscribe", "r2", ["101", "102"])
        assert a["label"].startswith("Re-subscribe r2's telemetry (101, 102): ")

    def test_one_stream_alone_too(self, lab):  # noqa: F811
        (row,) = _rows(_instance("r2", "NMAS telemetry stream lost: r2 subscription 102", 2))
        assert row["action"]["subs"] == ["102"] and row["action"]["open"] == "resubscribe"

    def test_another_rule_in_the_group_or_two_devices_is_not_offered(self, lab):  # noqa: F811
        from modules.attention import resubscribe_action
        mixed = [{"rule": "NMAS telemetry stream lost: r2 subscription 101", "device": "r2"},
                 {"rule": "Interface down", "device": "r2"}]
        two = [{"rule": "NMAS telemetry stream lost: r2 subscription 101", "device": "r2"},
               {"rule": "NMAS telemetry stream lost: r3 subscription 101", "device": "r3"}]
        nobody = [{"rule": "NMAS telemetry stream lost: r2 subscription 101", "device": None}]
        assert resubscribe_action(mixed) is None and resubscribe_action(two) is None
        assert resubscribe_action(nobody) is None
        assert resubscribe_action(two[:1])["subs"] == ["101"]

    def test_the_row_draws_its_action_and_its_card_slot(self, lab):  # noqa: F811
        import app as A
        from flask import render_template
        rows = _rows(_instance("r2", "NMAS telemetry stream lost: r2 subscription 101", 1))
        rows[0]["networks"] = {"r2": [NET]}
        with A.app.test_request_context("/v2/"):
            html = render_template("v2/_attention.html", a={"rows": rows, "sources": [],
                                                             "badge": {"n": 1}},
                                   attention_trigger="nmas:attention from:body")
        assert ('data-next-acts="resubscribe" href="#resub-r2">Re-subscribe r2\'s telemetry '
                '(101)…</a>') in html
        assert (f'id="resub-r2" hx-get="/v2/device/r2/resubscribe?list={NET}&amp;subs=101"'
                in html)
        assert "data-manual=\"telemetry-resubscribe\"" in html
        rows[0]["networks"] = {"r2": [NET, "Branch"]}
        with A.app.test_request_context("/v2/"):
            html = render_template("v2/_attention.html", a={"rows": rows, "sources": [],
                                                             "badge": {"n": 1}},
                                   attention_trigger="nmas:attention from:body")
        assert "Re-subscribe is not offered: 2 of the networks" in html
        assert 'id="resub-r2" hx-get' not in html


# ── The card ────────────────────────────────────────────────────────────────────────────────

class TestTheCard:
    def test_outcome_first_each_subscription_its_hash_and_the_program(self, client):
        from modules.heal import resubscribe as R
        r, html = card(client)
        assert r.status_code == 200
        first = html.index("Afterwards:")
        assert first < html.index('name="sub" value="101"') < html.index("The exact program")
        p = R.plan(NET, "r2", ["101", "102"], sources=client.state["src"])
        for u in p["units"]:
            assert hidden(html, f"hash::{u['sub']}") == u["hash"]
        assert f"no {LINE}" in html and "(wait 10 s)" in html
        button = re.search(r'<button[^>]*hx-post="/v2/device/r2/resubscribe/confirm[^"]*"[^>]*>'
                           r'<span class="op-idle">([^<]*)</span>', html)
        assert button and button.group(1) == "Re-subscribe r2's telemetry (101, 102)"
        assert 'hx-disabled-elt="this"' in button.group(0)
        assert 'hx-include="#resub-r2-form"' in button.group(0)
        assert 'data-manual="telemetry-resubscribe"' in html
        assert "nothing is saved to startup" in html
        assert "their receivers removed together and then added back" in html
        assert "removed first, in the order listed (101, then 102)" in html
        # The batch, drawn exactly: every removal, the one wait, every re-add; bound to the
        # selection's hash, which the form carries.
        from modules.nsot import privileged
        drawn = program_drawn(html)
        assert drawn == (lines_for("101", f"no {LINE}") + lines_for("102", f"no {LINE}")
                         + ["(wait 10 s)"]
                         + lines_for("101", LINE) + lines_for("102", LINE))
        assert selection_of(html) == p.get("hash") and hidden(html, "previewed") == "101,102"
        # Pressed with what the card's form holds: what the device is sent is the program the
        # card drew, line for line, and the run is bound to the hashes it showed.
        r = press(client, html)
        assert r.status_code == 200
        assert [ln for b in client.state["src"].box.batches for ln in b] == [
            ln for ln in drawn if ln != "(wait 10 s)"]
        steps = privileged.runs(NET)["runs"][0]["steps"]
        said = next(s["words"] for s in steps if s["step"] == "hash" and s["result"] == "ok")
        for u in p["units"]:
            assert f"{u['sub']}: {u['hash']}" in said
        assert f"the selection's is too ({p['hash']})" in said

    def test_one_subscription_draws_its_own_two_sends(self, client):
        _r, html = card(client, subs="102")
        assert program_drawn(html) == (lines_for("102", f"no {LINE}") + ["(wait 10 s)"]
                                       + lines_for("102", LINE))
        assert "Its receiver is removed for about 10 s, so subscription 102 sends nothing" in html
        assert "removed together" not in html
        press(client, html, subs=("102",))
        assert sent(client) == [("102", "remove"), ("102", "add")]

    def test_one_that_shares_the_receiver_and_is_not_ticked_is_said_and_offered(self, client):
        """Opened for 101 alone: 102 sends to the same receiver, so the card lists it,
        unticked, says it may keep the old connection, and says it can be ticked; ticked, the
        notice goes, the program drawn is the batch, and the batch is what is sent."""
        _r, html = card(client, subs="101")
        assert re.search(r'<input type="checkbox" name="sub" value="101" checked>', html)
        assert re.search(r'<input type="checkbox" name="sub" value="102">', html), \
            "102 is listed, not ticked"
        assert "(not in this alert; it sends to the same receiver as 101)" in html
        assert ("Subscription 102 is not ticked, and it sends to the same receiver as 101"
                in html)
        assert "102 may keep the old connection open" in html
        assert "Tick 102 to re-subscribe them together." in html
        assert program_drawn(html) == (lines_for("101", f"no {LINE}") + ["(wait 10 s)"]
                                       + lines_for("101", LINE)), "drawn for the ticked one"
        one = selection_of(html)
        _r, both = card(client, subs="101", ticked=("101", "102"))
        assert "is not ticked" not in both
        assert re.search(r'<input type="checkbox" name="sub" value="102" checked>', both)
        assert selection_of(both) != one, "another selection, another hash"
        assert hidden(both, "hash::101") == hidden(html, "hash::101"), "its own hash is its own"
        assert program_drawn(both)[:8] == (lines_for("101", f"no {LINE}")
                                           + lines_for("102", f"no {LINE}"))
        r = press(client, both)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        assert sent(client) == [("101", "remove"), ("102", "remove"), ("101", "add"),
                                ("102", "add")]

    def test_nothing_ticked_draws_no_program_and_no_button(self, client):
        _r, html = card(client, ticked=())
        assert "Nothing is ticked: tick a subscription to draw its program." in html
        assert "resubscribe/confirm" not in html and "ask-pre" not in html
        assert re.search(r'<input type="checkbox" name="sub" value="101">', html), \
            "the subscriptions stay, to tick"
        r = client.post(f"{BASE}/confirm?list={NET}", headers=HX, data={
            "reason": REASON, "subs": "101,102", "picked": "1", "program": ""})
        assert r.status_code == 409 and "no subscription was chosen" in r.get_data(as_text=True)
        assert sent(client) == []

    def test_a_refused_plan_says_why_and_draws_no_button(self, client):
        from modules.nsot import privileged
        _r, html = card(client, subs="103")
        assert "Re-subscribe is not offered:" in html
        assert "intent declares no telemetry subscription 103 on r2" in html
        assert "resubscribe/confirm" not in html
        # The button it does not draw, pressed anyway: refused with the same reason, nothing
        # sent to the device and no run started.
        r = client.post(f"{BASE}/confirm?list={NET}", headers=HX, data={
            "sub": "103", "reason": REASON, "subs": "103", "hash::103": "0" * 16})
        assert r.status_code == 409
        assert "intent declares no telemetry subscription 103 on r2" in r.get_data(as_text=True)
        assert client.state["src"].box.batches == [] and client.state["src"].box.opened == 0
        assert privileged.runs(NET)["runs"] == []


# ── Pressed ─────────────────────────────────────────────────────────────────────────────────

def press(client, html, subs=("101", "102"), reason=REASON, **override):
    """The card's button pressed with what its form holds (each ticked ``sub``, its hash, the
    selection's ``program`` and the ``previewed`` selection), *subs* ticked."""
    data = {"sub": list(subs), "reason": reason, "subs": hidden(html, "subs"), "picked": "1",
            "program": override.get("program", selection_of(html)),
            "previewed": hidden(html, "previewed")}
    for s in subs:
        data[f"hash::{s}"] = override.get(s, hidden(html, f"hash::{s}"))
    return client.post(f"{BASE}/confirm?list={NET}", data=data, headers=HX)


class TestPressed:
    def test_the_run_is_the_persons_and_its_result_is_drawn_in_place(self, client):
        from modules.nsot import privileged
        from tests.conftest import TEST_PERSON
        _r, html = card(client)
        r = press(client, html)
        out = r.get_data(as_text=True)
        assert r.status_code == 200, out
        assert "Re-subscribed; the stream is back:" in out and "notice-muted" in out
        assert 'data-holds-live="review"' in out
        run = privileged.runs(NET)["runs"][0]
        assert run["actor"] == TEST_PERSON and run["reason"] == REASON
        assert run["outcome"] == "resubscribed"
        assert sent(client) == [("101", "remove"), ("102", "remove"), ("101", "add"),
                                ("102", "add")]

    def test_a_partial_is_never_green(self, client):
        from tests.test_heal_resubscribe import ABSENT, seq
        client.state["src"] = Src(series=seq([ABSENT]))
        _r, html = card(client, subs="101")
        out = press(client, html, subs=("101",)).get_data(as_text=True)
        assert "Re-subscribed; the stream did not come back:" in out
        assert "notice-danger" in out and "notice-muted" not in out
        # Its effect: the receiver removed and put back, the run recorded as failed, and the
        # device's configuration as it began.
        from modules.nsot import privileged
        from tests.test_heal_resubscribe import R2_CFG
        box = client.state["src"].box
        assert [b[2] for b in box.batches] == [f" no {LINE}", f" {LINE}"]
        assert box.text() == R2_CFG + ("" if R2_CFG.endswith("\n") else "\n")
        run = privileged.runs(NET)["runs"][0]
        assert (run["outcome"], run["state"]) == ("not_back", "failed")

    def test_a_moved_hash_is_refused_naming_both_and_sends_nothing(self, client):
        _r, html = card(client, subs="101")
        r = press(client, html, subs=("101",), **{"101": "0" * 16})
        out = r.get_data(as_text=True)
        assert r.status_code == 409
        assert "Not sent:" in out and "confirmed 0000000000000000, now" in out
        assert client.state["src"].box.batches == []

    def test_unticking_one_draws_the_others_program_and_runs_only_it(self, client):
        """A tick changed draws the card again for that selection: 102 alone is 102's two
        sends under another hash, 101 is named as left out, and only 102 is sent."""
        _r, both = card(client)
        _r, html = card(client, ticked=("102",))
        assert re.search(r'<input type="checkbox" name="sub" value="101">', html)
        assert re.search(r'<input type="checkbox" name="sub" value="102" checked>', html)
        assert program_drawn(html) == (lines_for("102", f"no {LINE}") + ["(wait 10 s)"]
                                       + lines_for("102", LINE))
        assert selection_of(html) != selection_of(both)
        assert hidden(html, "previewed") == "102"
        assert ("Subscription 101 is not ticked, and it sends to the same receiver as 102"
                in html)
        button = re.search(r'<span class="op-idle">(Re-subscribe [^<]*)</span>', html)
        assert button and button.group(1) == "Re-subscribe r2's telemetry (102)"
        assert press(client, html, subs=("102",)).status_code == 200
        assert sent(client) == [("102", "remove"), ("102", "add")]

    def test_a_confirm_of_another_selection_is_refused_naming_both(self, client):
        """The card drew 101 alone. A confirm of 101 and 102 with that card's selection hash
        (each subscription's own hash right) is another program: refused, both selections and
        both hashes named, nothing sent, and the card drawn again for what was asked."""
        from modules.nsot import privileged
        _r, html = card(client, subs="101")
        drawn_for_one = selection_of(html)
        r = press(client, html, subs=("101", "102"))
        out = r.get_data(as_text=True)
        assert r.status_code == 409, out[:300]
        assert "Not sent:" in out and "the selection is not the one previewed" in out
        assert f"{drawn_for_one}, for subscription 101, and" in out
        now = selection_of(out)
        assert now != drawn_for_one and f"{now}, for subscription 101 and 102" in out
        assert sent(client) == [] and privileged.runs(NET)["runs"] == []
        assert re.search(r'<input type="checkbox" name="sub" value="102" checked>', out)
        # Unticking without the card drawn again is refused the same way.
        _r, both = card(client)
        r = press(client, both, subs=("102",))
        assert r.status_code == 409
        assert "for subscription 101 and 102, and" in r.get_data(as_text=True)
        assert sent(client) == []
        # The card as it was drawn again is confirmed as drawn.
        assert press(client, out).status_code == 200
        assert sent(client) == [("101", "remove"), ("102", "remove"), ("101", "add"),
                                ("102", "add")]


# ── Removed, and Re-add the receiver ────────────────────────────────────────────────────────

class TestRemoved:
    def test_the_removed_receiver_leads_and_re_add_puts_it_back(self, client):
        from tests.test_heal_resubscribe import R2_101, new_connection, receiver_read, seq
        box = Box(readd_fails=2)
        client.state["src"] = Src(box=box)
        _r, html = card(client, subs="101")
        out = press(client, html, subs=("101",)).get_data(as_text=True)
        assert "r2&#39;s receiver for 101 is removed" in out and "notice-danger" in out
        _r, html = card(client, subs="101")
        assert html.index("r2's receiver for 101 is removed.") < html.index("Afterwards:")
        assert "Re-add the receiver for 101" in html
        client.state["src"] = Src(box=box, receiver=seq([
            receiver_read(R2_101), receiver_read(new_connection(R2_101))]))
        r = client.post(f"{BASE}/readd?list={NET}", headers=HX, data={
            "sub": "101", "hash": readd_hash(html, "101"), "subs": "101"})
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and "The receiver added back; the stream is back:" in out
        _r, html = card(client, subs="101")
        assert "is removed." not in html

    def test_each_receiver_a_batch_left_removed_leads_with_its_own_re_add(self, client):
        """Both re-adds dropped: the result is the danger, each subscription's own state said,
        and the card then leads with Re-add the receiver for each, until each is put back."""
        from tests.test_heal_resubscribe import R2_101, new_connection, receiver_read, seq
        box = Box(drops_readd_of=("101", "102"))
        client.state["src"] = Src(box=box)
        _r, html = card(client)
        out = press(client, html).get_data(as_text=True)
        assert "The receiver is removed:" in out
        assert "notice-danger" in out and "notice-muted" not in out
        for sub in ("101", "102"):
            assert f"Subscription {sub}: THE RECEIVER IS REMOVED" in out
        assert sent(client) == [("101", "remove"), ("102", "remove"), ("101", "add"),
                                ("101", "add"), ("102", "add"), ("102", "add")]
        _r, html = card(client)
        for sub in ("101", "102"):
            assert f"r2's receiver for {sub} is removed." in html
            assert f"Re-add the receiver for {sub}</span>" in html
        assert html.index("Re-add the receiver for 102</span>") < html.index(
            "Subscriptions</legend>")
        box.drops_readd_of.clear()
        client.state["src"] = Src(box=box, receiver=seq([
            receiver_read(R2_101), receiver_read(new_connection(R2_101))]))
        r = client.post(f"{BASE}/readd?list={NET}", headers=HX, data={
            "sub": "101", "hash": readd_hash(html, "101"), "subs": "101,102"})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        _r, html = card(client)
        assert "r2's receiver for 101 is removed." not in html
        assert "r2's receiver for 102 is removed." in html, "102 is still out, and still said"


# ── The collector step (C3078): the same card, the step on ──────────────────────────────────

def closing_card(client, tmp_path, **src):
    """The card asked for with the collector step, its sources the lab's with the REAL close
    helper where sudo would run it (tests/test_heal_resubscribe.py's `helper_world`)."""
    from tests.test_heal_resubscribe import CloseSrc, helper_world
    m, close = helper_world(tmp_path)
    client.state["src"] = CloseSrc(close, **src)
    r = client.get(f"{BASE}?list={NET}&subs=101,102&collector=1", headers=HX)
    return m, r, r.get_data(as_text=True)


def close_selection_of(html):
    m = re.search(r'hx-post="/v2/device/r2/resubscribe/close[^"]*" '
                  r'hx-vals=\'\{"program": "([0-9a-f]*)"\}\'', html)
    assert m, "the collector step's confirm button carries no selection hash"
    return m.group(1)


def press_close(client, html, **override):
    data = {"sub": ["101", "102"], "reason": REASON, "subs": hidden(html, "subs"),
            "picked": "1", "collector": "1",
            "program": override.get("program", close_selection_of(html)),
            "previewed": hidden(html, "previewed"),
            "close": override.get("close", hidden(html, "close"))}
    for s in ("101", "102"):
        data[f"hash::{s}"] = hidden(html, f"hash::{s}")
    return client.post(f"{BASE}/close?list={NET}", data=data, headers=HX)


class TestTheCollectorStep:
    def test_the_plain_cards_step_button_draws_the_card_with_the_session(self, client,
                                                                         tmp_path):
        """Pressed (its hx-get, with the form it includes), the plain card's Close the
        collector's stale session first… draws the card with the step: the session and its
        confirm; nothing is closed."""
        import html as H
        from tests.test_heal_resubscribe import CloseSrc, helper_world
        m, close = helper_world(tmp_path)
        client.state["src"] = CloseSrc(close)
        _r, html = card(client)
        got = re.search(r'<button[^>]*hx-get="(/v2/device/r2/resubscribe\?[^"]*collector=1'
                        r'[^"]*)"[^>]*hx-disabled-elt="this"[^>]*><span class="op-idle">Close '
                        r"the collector's stale session first…</span><span class=\"op-busy\">"
                        r"Reading…</span>", html)
        assert got, "the step is offered, busy on itself"
        assert 'href="/v2/help/telemetry-resubscribe#the-collector-step"' in html
        r = client.get(H.unescape(got.group(1)) + "&sub=101&sub=102&subs=101,102&picked=1",
                       headers=HX)
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and hidden(out, "close") == "192.0.2.6:56221"
        assert close_selection_of(out) != selection_of(html)
        assert not m.run.closes_sent() and client.state["src"].box.batches == []

    def test_with_the_step_the_card_draws_the_session_the_dry_run_names(self, client,
                                                                       tmp_path):
        m, r, html = closing_card(client, tmp_path)
        assert r.status_code == 200, html
        assert ("the collector's session from 192.0.2.6:56221 to 192.0.2.10:57000, which "
                "has received nothing for 2130 s, is closed") in html
        assert "dry run: would close the one established session from 192.0.2.6:56221" in html
        assert hidden(html, "close") == "192.0.2.6:56221" and hidden(html, "collector") == "1"
        assert ("Close the collector's stale session for r2, then re-subscribe (101, 102)"
                in html)
        assert not m.run.closes_sent() and client.state["src"].box.batches == []

    def test_pressed_it_closes_then_re_subscribes_and_draws_the_receipt(self, client,
                                                                        tmp_path):
        from modules.heal import resubscribe as R
        from modules.nsot import privileged
        m, _r, html = closing_card(client, tmp_path)
        r = press_close(client, html)
        out = r.get_data(as_text=True)
        assert r.status_code == 200, out
        assert "Re-subscribed; the stream is back:" in out
        assert ('data-close-receipt="closed"' in out
                and "the close helper answered closed (exit 0)" in out)
        assert len(m.run.closes_sent()) == 1
        assert sent(client) == [("101", "remove"), ("102", "remove"), ("101", "add"),
                                ("102", "add")]
        run = privileged.runs(NET)["runs"][0]
        assert run["key"] == R.COLLECTOR_KEY and run["collector_close"]["code"] == "closed"

    def test_a_session_other_than_the_one_drawn_is_refused_in_place(self, client, tmp_path):
        m, _r, html = closing_card(client, tmp_path)
        r = press_close(client, html, program="0" * 16, close="192.0.2.6:56000")
        out = r.get_data(as_text=True)
        assert r.status_code == 409
        assert "Not sent:" in out and "the collector&#39;s session is not the one previewed" \
            in out and "192.0.2.6:56000" in out and "192.0.2.6:56221" in out
        assert not m.run.closes_sent() and client.state["src"].box.batches == []

    def test_a_step_it_cannot_take_is_said_and_the_plain_re_subscribe_stays(self, client,
                                                                           tmp_path):
        from tests.test_heal_resubscribe import NEW, coll
        m, r, html = closing_card(client, tmp_path, before=None)
        src = client.state["src"]
        # No session before; the device's new one once the re-subscribe has sent.
        src.collector = lambda a, p, s: coll(NEW) if src.box.batches else coll()
        assert r.status_code == 200
        assert "The collector step is not offered:" in html and "nothing to close" in html
        assert "/resubscribe/close" not in html
        # Re-subscribe alone, pressed: it runs, and closes nothing.
        r = press(client, html)
        assert r.status_code == 200 and "Re-subscribed; the stream is back:" in \
            r.get_data(as_text=True)
        assert not m.run.closes_sent() and client.state["src"].asked == []
        assert sent(client) == [("101", "remove"), ("102", "remove"), ("101", "add"),
                                ("102", "add")]


# ── In a real browser: a tick changed draws the card again, and the button sends it ─────────

def test_a_tick_changed_draws_the_card_again_and_the_button_sends_it_in_a_real_browser(client):
    """The card on a real page, its own controls pressed: unticking 101 draws 102's program
    and says 101 is left out; ticking it again draws the batch; the button, pressed with a
    reason typed, sends exactly that batch and draws the result in place."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as nmas
    label = "(document.querySelector('#resub-r2 .op-idle') || {}).textContent"
    text = "document.querySelector('#resub-r2').textContent"
    with browser.Served(nmas.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/help/telemetry-resubscribe"))
            b.wait_for("return !!window.htmx && !!document.body", 15)
            b.js("window.__settled = 0; document.addEventListener('htmx:afterSettle',"
                 " function () { window.__settled++; }); return 1")

            def drawn(act, subs):
                """*act* done, and the card it draws SETTLED: htmx gives a swapped-in control
                its trigger in the settle step, 20 ms after the swap, so a tick made on a
                card whose label is already drawn can be one the page does not hear yet."""
                b.js("window.__settled = 0; return 1")
                act()
                b.wait_for("return window.__settled > 0 && "
                           f"{label} === \"Re-subscribe r2's telemetry ({subs})\"", 15)

            def tick():
                b.click('#resub-r2 input[name="sub"][value="101"]')

            drawn(lambda: b.js(
                "var d = document.createElement('div'); d.id = 'resub-r2';"
                " document.body.appendChild(d);"
                f" htmx.ajax('GET', '{BASE}?list={NET}&subs=101,102',"
                " {target: '#resub-r2', swap: 'outerHTML'}); return 1"), "101, 102")
            drawn(tick, "102")
            one = b.js(f"return {text}")
            drawn(tick, "101, 102")
            both = b.js(f"return {text}")
            b.type("#resub-r2-why", REASON)
            b.click('#resub-r2 button[data-op="telemetry-resubscribe"]')
            b.wait_for(f"return {text}.indexOf('Re-subscribed; the stream is back') >= 0", 30)
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert "Subscription 101 is not ticked, and it sends to the same receiver as 102" in one
    assert "is not ticked" not in both
    assert sent(client) == [("101", "remove"), ("102", "remove"), ("101", "add"),
                            ("102", "add")]


# ── Who may confirm: the real identity layer ────────────────────────────────────────────────

#: tests/test_local_account.py's account and its sign-in, typed here.
NAME = "lab-admin"
PW = "correct horse battery staple 42"
ORIGIN = {"Origin": "http://localhost", "HX-Request": "true"}
SIGN_IN = "/v2/settings/installation/local-account/sign-in"
NOT_A_PERSON = ("a telemetry re-subscribe is confirmed by a verified person, and this request "
                "is not one")


@pytest.fixture
def jobs(lab, monkeypatch):  # noqa: F811
    """The real app's client and the REAL job starter (`capture_job.start`), so a run is the
    job's own thread and what it carries is what the starter handed over; each started job's
    id is kept, to wait for."""
    import app as A
    from modules.nsot import capture_job

    state = {"src": Src(), "jobs": []}
    monkeypatch.setattr("modules.heal.resubscribe.Sources", lambda net, **kw: state["src"])
    real = capture_job.start

    def start(*a, **kw):
        state["jobs"].append(real(*a, **kw))
        return state["jobs"][-1]
    monkeypatch.setattr("modules.nsot.capture_job.start", start)
    A.app.config["TESTING"] = True
    c = A.app.test_client()
    c.state = state
    return c


def _local_account(monkeypatch):
    """The local account's three conditions (tests/test_local_account.py's `_on`): the
    setting, Mercury listening on loopback only, and the account."""
    from modules import config
    from modules import local_account as LA
    from modules.settings_schema import write_settings

    monkeypatch.setattr(config, "FLASK_HOST", "127.0.0.1")
    assert write_settings({LA.SETTING: True}, actor="test")["ok"]
    LA.set_password(NAME, PW)


def _gate_lets_through(monkeypatch, *keys):
    """The gate's own requirement turned off (a setting an installation can hold), so the
    request reaches the route and the OPERATION's refusal is the one read."""
    from modules import identity
    real = identity._setting
    monkeypatch.setattr(identity, "_setting",
                        lambda key, default=None: False if key in keys else real(key, default))


def _nothing_happened(c):
    from modules.nsot import privileged
    assert c.state["jobs"] == [], "no job was started"
    assert c.state["src"].box.batches == [] and c.state["src"].box.opened == 0, "nothing sent"
    assert privileged.runs(NET)["runs"] == [], "no run was recorded"


@pytest.mark.real_identity
class TestWhoMayConfirm:
    """No access proxy is configured here, so nobody is identified unless the local account
    signs them in (the laptop kit, where every confirm refused before C2520's first step)."""

    def test_a_signed_in_local_account_confirms_and_is_recorded_as_local_account(
            self, jobs, monkeypatch):
        from modules import identity
        from modules.history_sources import privileged as history
        from modules.nsot import capture_job, listref, privileged
        _local_account(monkeypatch)
        r = jobs.post(SIGN_IN, data={"name": NAME, "password": PW}, headers=ORIGIN)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        # What the job's own thread reads of who started it, at its first session.
        src, seen = jobs.state["src"], {}
        opener = src.opener

        def opened(dev):
            seen.setdefault("actor", identity.request_actor())
            seen.setdefault("verified", identity.actor_verification(NAME))
            seen.setdefault("another", identity.actor_verification("someone@example.invalid"))
            return opener(dev)
        src.opener = opened
        _r, html = card(jobs, subs="101")
        r = press(jobs, html, subs=("101",))
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        (job,) = jobs.state["jobs"]
        assert capture_job.wait(job, 30)
        assert capture_job.get(job)["state"] == "done", capture_job.get(job)["error"]
        (run,) = privileged.runs(NET)["runs"]
        assert run["outcome"] == "resubscribed", run["why"]
        assert (run["actor"], run["actor_verified"]) == (NAME, "local-account")
        assert seen == {"actor": NAME, "verified": "local-account", "another": "none"}
        assert [b[2] for b in src.box.batches] == [f" no {LINE}", f" {LINE}"]
        # Read again on History: the person, and how they were verified.
        (e,) = history({"ref": listref.resolve(NET), "device": "", "limit": 50, "since": None,
                        "members": None})["events"]
        assert e["who"] == f"{NAME} (local account, kit)"
        assert ("Verified by", "local-account") in e["record"]
        done = jobs.get(f"{BASE}?list={NET}&subs=101&run={run['id']}", headers=HX)
        assert f"Recorded by {NAME}" in done.get_data(as_text=True)

    @pytest.mark.parametrize("route", ["confirm", "readd"])
    def test_an_unidentified_request_is_refused_at_the_gate(self, jobs, route):
        _r, html = card(jobs, subs="101")
        r = jobs.post(f"{BASE}/{route}?list={NET}", headers=HX, data={
            "sub": "101", "reason": REASON, "subs": "101", "picked": "1", "previewed": "101",
            "program": selection_of(html), "hash": hidden(html, "hash::101"),
            "hash::101": hidden(html, "hash::101")})
        assert r.status_code == 403
        assert r.get_json()["requires_identity"] is True
        _nothing_happened(jobs)

    @pytest.mark.parametrize("route", ["confirm", "readd"])
    def test_the_operation_refuses_one_the_gate_let_through(self, jobs, monkeypatch, route):
        """With the gate's identity requirement off, the operation's own check refuses: the
        actor unverified, the kind none, never taken as the access proxy's."""
        _gate_lets_through(monkeypatch, "require_identity_for_confirm")
        _r, html = card(jobs, subs="101")
        r = jobs.post(f"{BASE}/{route}?list={NET}", headers=HX, data={
            "sub": "101", "reason": REASON, "subs": "101", "picked": "1", "previewed": "101",
            "program": selection_of(html), "hash": hidden(html, "hash::101"),
            "hash::101": hidden(html, "hash::101")})
        out = r.get_data(as_text=True)
        assert r.status_code == 403, out[:300]
        assert "Not sent:" in out and NOT_A_PERSON in out
        assert "(actor unverified, verified none, not a person)" in out
        _nothing_happened(jobs)

    def test_a_verified_service_is_not_a_person(self, jobs, monkeypatch):
        """A service the gate's settings let confirm is verified, and still not a person."""
        from modules import identity
        service = identity.Identity(actor="service:ci", kind="service", service_id="ci",
                                    verified=True, outcome="ok", peer="198.51.100.7",
                                    peer_trusted=True, header_present=True,
                                    verification=identity.ACCESS)
        assert service.is_identified
        monkeypatch.setattr(identity, "identify", lambda _request: service)
        _gate_lets_through(monkeypatch, "require_person_for_confirm")
        _r, html = card(jobs, subs="101")
        r = press(jobs, html, subs=("101",))
        out = r.get_data(as_text=True)
        assert r.status_code == 403, out[:300]
        assert NOT_A_PERSON in out and "verified access, not a person)" in out
        _nothing_happened(jobs)
