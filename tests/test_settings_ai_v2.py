"""Settings › Installation › AI: each network's background AI features, turned on by a verified
person bound to the estimate they were shown (board AI3 and AI3b, signed off under the Phase 7
mode 2026-10-27; PHASE8_PLAN 18.3 rules 2 to 4; C1843). Through the real routes, the real
settings file, the real record of AI calls and the real gateway; only the provider is fake (a
`send` that keeps what it got), and a fake feature with a planted frequency stands beside the
real `sdn_classify`.

Each test holds one purpose:
- the tab draws every feature on the chosen network, off by default, under the strict policy;
- Turn on… draws the estimate labelled, with its digest the form sends back;
- the estimate shown is the one confirmed: written and recorded with that digest;
- a moved estimate is refused naming both digests, nothing written, the estimate now drawn;
- the estimate not accepted is refused, nothing written;
- a non-admin (a service, an unverified request) is refused, nothing written;
- caps out of range are refused naming both operands, on Turn on and on Change caps;
- Turn off stops the next call, through the gateway;
- an approval ends after 14 days: the gateway refuses, naming its end, and the row says so;
- a switch with no approval time Mercury wrote is never in force;
- Turn off removes a switch whose approval ended;
- a cap refusal draws the feature stopped, here and on another network's view;
- changing caps is recorded with both values and never extends the approval.
"""
import calendar
import json
import re
import time
import types
from html import unescape

import pytest

from modules import identity
from modules.ai import anthropic_adapter as A
from modules.ai import background as B
from modules.ai import calls, connection, gateway, triggers
from tests.conftest import TEST_PERSON
from tests.test_ai_gateway import KEY, OK_BODY
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

TASK = "connection_check"
NET = "Branch"
BASE = "/v2/settings/installation/ai/background"


@pytest.fixture
def ai(networks, tmp_path, monkeypatch):  # noqa: F811 (the fixture above)
    """Hosted AI allowed with a $1.50 day cap, a key, the record of AI calls in the test's
    folder, the fake feature (4 detections a day, planted) and a fake provider."""
    from modules.settings_schema import write_settings
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    assert write_settings({"ai_hosted": {"by": "admin@example.com", "at": "2026-10-27T00:00:00Z",
                                         "reason": "the lab's background loop"},
                           "ai_cap_usd_per_day": 1.50})["ok"]
    freq = {"per_day": 4.0}
    monkeypatch.setitem(B.FEATURES, "fake_loop", {
        "task": TASK, "words": "The fake loop", "findings": ("detection",),
        "trigger_words": "a detection rule fires", "calls_per_finding": 1,
        "frequency": lambda network: {"per_day": freq["per_day"],
                                      "basis": f"{freq['per_day']} detections a day, planted"}})
    sent = []

    def send(body, key):
        sent.append(body)
        return A.Reply(status=200, body=OK_BODY, attempts=1, latency_s=0.1)
    return types.SimpleNamespace(client=networks["client"], dir=networks["dir"], sent=sent,
                                 send=send, freq=freq)


def _get(w, path):
    r = w.client.get(path)
    return r, unescape(r.get_data(as_text=True))


def _post(w, path, data=None):
    r = w.client.post(path, data=data or {}, headers={"HX-Request": "true"})
    return r, unescape(r.get_data(as_text=True))


def _row(html, feature):
    m = re.search(r'<div class="ai-feature[^"]*" role="listitem" id="bg-' + feature
                  + r'" data-state="([a-z]+)">(.*?)(?=<div class="ai-feature|</div>\s*</div>\s*'
                    r'(?:<div class="notice|</section>))', html, re.S)
    assert m, f"no row for {feature}"
    return m.group(1), re.sub(r"\s+", " ", m.group(2))


def _shown(html):
    m = re.search(r'name="shown" value="([0-9a-f]{64})"', html)
    assert m, "the form sends no estimate digest"
    return m.group(1)


def _record(w):
    p = w.dir / "settings_record.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def _turn_on(w, day="0.50", month="10.00", network=NET):
    _r, form = _get(w, f"{BASE}/{network}/fake_loop/on")
    return _post(w, f"{BASE}/{network}/fake_loop/on",
                 {"shown": _shown(form), "day_cap_usd": day, "month_cap_usd": month,
                  "accept": "on"})


def _call(w, network=NET):
    t = triggers.background("fake_loop", "j1", network, "detection", "scan-1")
    return gateway.ask(TASK, ("ping", 1), connection.Ping, {"word": "w"},
                       actor=triggers.actor_of(t), trigger=t, send=w.send)


def test_the_tab_draws_every_feature_off_by_default_under_the_strict_policy(ai):
    from modules import csp
    r, html = _get(ai, f"/v2/settings/installation?tab=ai&network={NET}")
    assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
    assert 'aria-current="page">AI</a>' in html and "Background features" in html
    assert re.search(r'<option value="Branch" selected>Branch</option>', html)
    for feature in ("fake_loop", "sdn_classify"):
        state, row = _row(html, feature)
        assert state == "off" and ">off<" in row and "Turn on…" in row and "Turn off" not in row
    assert "Hosted AI" in html and "Allowed by admin@example.com" in html
    assert ai.sent == [] and B.switches() == {}


def test_turn_on_draws_the_estimate_labelled_with_the_digest_the_form_sends(ai):
    r, html = _get(ai, f"{BASE}/{NET}/fake_loop/on")
    est = B.estimate(NET, "fake_loop")
    assert r.status_code == 200 and _shown(html) == est["digest"]
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    assert "ESTIMATE" in text and "an estimate, not a measurement" in text.lower()
    assert "Calls a day 4.0" in text and "4.0 detections a day, planted" in text
    assert "not measured:" in text and "per-call cap" in text, "the cost said as an upper bound"
    assert f"Estimate {est['digest'][:8]}" in text and "the provider bills" in text
    assert 'name="day_cap_usd"' in html and 'name="month_cap_usd"' in html
    assert 'name="accept"' in html and "Turn on with this estimate" in text
    assert B.switches() == {}, "opening the estimate writes nothing"


def test_an_unknown_frequency_is_said_unknown_and_offers_no_caps(ai):
    ai.freq["per_day"] = None
    _r, html = _get(ai, f"{BASE}/{NET}/fake_loop/on")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    assert "Calls a day unknown" in text and "unknown: the caps below are the bound" in text
    assert "Turn on with no measured estimate" in text
    assert re.search(r'name="day_cap_usd"[^>]*value=""', html), "no cap guessed for the person"


def test_the_estimate_shown_is_the_one_confirmed_and_recorded(ai):
    _r, form = _get(ai, f"{BASE}/{NET}/fake_loop/on")
    shown = _shown(form)
    r, html = _post(ai, f"{BASE}/{NET}/fake_loop/on",
                    {"shown": shown, "day_cap_usd": "$0.50", "month_cap_usd": "10",
                     "accept": "on"})
    assert r.status_code == 200 and 'data-result="on"' in html
    entry = B.entry_of("branch", "fake_loop")
    assert entry["estimate"]["digest"] == shown and entry["by"] == TEST_PERSON
    assert (entry["day_cap_usd"], entry["month_cap_usd"]) == (0.5, 10.0)
    (rec,) = [x for x in _record(ai) if x["kind"] == "ai_background_on"]
    assert rec["estimate"]["digest"] == shown and rec["actor"] == TEST_PERSON
    assert rec["network"] == "branch" and rec["feature"] == "fake_loop"
    state, row = _row(html, "fake_loop")
    assert state == "on" and "approval until" in row and "Turn off" in row
    assert "Change caps…" in row and f"({shown[:8]})" in row


def test_a_moved_estimate_is_refused_naming_both_and_nothing_is_written(ai):
    _r, form = _get(ai, f"{BASE}/{NET}/fake_loop/on")
    shown = _shown(form)
    ai.freq["per_day"] = 9.0
    now = B.estimate(NET, "fake_loop")["digest"]
    assert now != shown
    r, html = _post(ai, f"{BASE}/{NET}/fake_loop/on",
                    {"shown": shown, "day_cap_usd": "0.50", "month_cap_usd": "10",
                     "accept": "on"})
    assert r.status_code == 409 and "Not turned on:" in html
    assert f"shown {shown[:12]}" in html and f"now {now[:12]}" in html
    assert _shown(html) == now and "ESTIMATE, NOW" in html, "the estimate now, to accept again"
    assert B.switches() == {} and _record(ai) == []


def test_an_estimate_not_accepted_is_refused_and_nothing_is_written(ai):
    _r, form = _get(ai, f"{BASE}/{NET}/fake_loop/on")
    r, html = _post(ai, f"{BASE}/{NET}/fake_loop/on",
                    {"shown": _shown(form), "day_cap_usd": "0.50", "month_cap_usd": "10"})
    assert r.status_code == 409 and "the estimate was not accepted" in html
    assert B.switches() == {} and _record(ai) == []


def test_a_service_is_refused_even_where_configure_lets_a_service_through(ai, monkeypatch):
    from modules.settings_schema import write_settings
    assert write_settings({"require_person_for_configure": False})["ok"]
    svc = identity.Identity(actor="service:ci", kind="service", service_id="ci", verified=True,
                            outcome="ok", peer="127.0.0.1", peer_trusted=True)
    monkeypatch.setattr(identity, "identify", lambda _request: svc)
    _r, form = _get(ai, f"{BASE}/{NET}/fake_loop/on")
    r, html = _post(ai, f"{BASE}/{NET}/fake_loop/on",
                    {"shown": _shown(form), "day_cap_usd": "0.50", "month_cap_usd": "10",
                     "accept": "on"})
    assert r.status_code == 403 and "changed by a verified person (an admin)" in html
    assert "is a service" in html
    assert B.switches() == {} and _record(ai) == []


def test_an_unverified_request_is_refused_by_the_gate_and_nothing_is_written(ai, monkeypatch):
    nobody = identity.Identity(outcome="no_header", reason="no access assertion")
    monkeypatch.setattr(identity, "identify", lambda _request: nobody)
    r = ai.client.post(f"{BASE}/{NET}/fake_loop/on",
                       data={"shown": "0" * 64, "day_cap_usd": "0.50", "month_cap_usd": "10",
                             "accept": "on"}, headers={"HX-Request": "true"})
    assert r.status_code in (401, 403)
    assert B.switches() == {} and _record(ai) == []


@pytest.mark.parametrize("day, month, words", [
    ("8.00", "10", "the feature's day cap $8.0000 is over the installation's day cap $1.5000"),
    ("0", "10", "the day cap 0.0 is not a positive amount"),
    ("0.50", "-1", "the month cap -1.0 is not a positive amount"),
    ("lots", "10", "the day cap 'lots' is not a positive amount"),
])
def test_a_cap_out_of_range_is_refused_naming_both_and_nothing_is_written(ai, day, month,
                                                                          words):
    r, html = _turn_on(ai, day=day, month=month)
    assert r.status_code == 409 and words in html
    assert B.switches() == {} and _record(ai) == []
    assert f'value="{day}"' in html, "what was typed is drawn back"


def test_change_caps_out_of_range_is_refused_and_the_caps_stand(ai):
    _turn_on(ai)
    r, html = _post(ai, f"{BASE}/{NET}/fake_loop/caps",
                    {"day_cap_usd": "9", "month_cap_usd": "10"})
    assert r.status_code == 409 and "over the installation's day cap $1.5000" in html
    assert B.entry_of("branch", "fake_loop")["day_cap_usd"] == 0.5


def test_turn_off_stops_the_next_call_through_the_gateway(ai):
    _turn_on(ai)
    assert _call(ai)["ok"] is True and len(ai.sent) == 1
    r, html = _post(ai, f"{BASE}/{NET}/fake_loop/off")
    assert r.status_code == 200 and 'data-result="off"' in html
    assert "turned off for Branch" in html and _row(html, "fake_loop")[0] == "off"
    got = _call(ai)
    assert got["ok"] is False and got.get("error") == "feature_off" and len(ai.sent) == 1
    assert [x["kind"] for x in _record(ai)] == ["ai_background_on", "ai_background_off"]


def test_an_approval_ends_after_14_days_and_the_gateway_refuses_naming_its_end(ai,
                                                                               monkeypatch):
    _turn_on(ai)
    # The approval's start read from the switch as written, and its 14 days counted here, by
    # a path independent of `approval_ends` (a check's expectation never comes from the code
    # it checks).
    at = calendar.timegm(time.strptime(B.entry_of("branch", "fake_loop")["at"],
                                       "%Y-%m-%dT%H:%M:%SZ"))
    end = at + 14 * 86400
    monkeypatch.setattr(B, "_now", lambda: end - 1)
    assert _call(ai)["ok"] is True and len(ai.sent) == 1, "in force to its last second"
    monkeypatch.setattr(B, "_now", lambda: end)
    got = _call(ai)
    assert got.get("error") == "feature_off" and len(ai.sent) == 1
    ended = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end))
    assert f"approval for the network branch ended at {ended}" in got.get("detail", "")
    assert B.enabled() == []
    _r, html = _get(ai, f"/v2/settings/installation?tab=ai&network={NET}")
    state, row = _row(html, "fake_loop")
    assert state == "ended" and "approval ended" in row and "Turn on…" in row


def test_turn_off_removes_a_switch_whose_approval_ended(ai, monkeypatch):
    _turn_on(ai)
    monkeypatch.setattr(B, "_now", lambda: time.time() + 15 * 86400)
    r, html = _post(ai, f"{BASE}/{NET}/fake_loop/off")
    assert r.status_code == 200 and "turned off for Branch" in html
    assert B.switches() == {} and _row(html, "fake_loop")[0] == "off"
    assert [x["kind"] for x in _record(ai)] == ["ai_background_on", "ai_background_off"]


@pytest.mark.parametrize("at", [None, "", "yesterday", "2026-10-27 14:00"])
def test_a_switch_with_no_time_mercury_wrote_is_never_in_force(ai, at):
    """A switch on with no approval time (or one Mercury never wrote, a hand edit) has no
    approval to be in force under: the gateway refuses it, and it is not listed as on."""
    from modules.settings_schema import write_settings
    entry = {"on": True, "by": "admin@example.com", "day_cap_usd": 0.5, "month_cap_usd": 10.0}
    if at is not None:
        entry["at"] = at
    assert write_settings({"ai_background": {"branch": {"fake_loop": entry}}})["ok"]
    got = _call(ai)
    assert got.get("error") == "feature_off" and ai.sent == []
    assert B.enabled() == []


def test_a_cap_refusal_draws_the_feature_stopped_here_and_on_another_network(ai):
    _turn_on(ai, day="0.0001", month="10")
    # Today's spend at the day cap already: a planted background call of the feature.
    assert calls.record({"id": calls.new_id(), "feature": TASK, "actor": "job:j0", "model": "m",
                         "verdict": "ok", "cost_usd": 0.0001,
                         "trigger": {"kind": "background", "feature": "fake_loop", "job": "j0",
                                     "network": "branch",
                                     "finding": {"kind": "detection", "id": "d"}}})["recorded"]
    got = _call(ai)
    assert got.get("error") == "feature_cap" and ai.sent == []
    _r, html = _get(ai, f"/v2/settings/installation?tab=ai&network={NET}")
    state, row = _row(html, "fake_loop")
    assert state == "stopped" and "stopped by its day cap" in row and "Change caps…" in row
    _r, html = _get(ai, "/v2/settings/installation?tab=ai&network=Remote")
    assert _row(html, "fake_loop")[0] == "off"
    assert "On network Branch, The fake loop is on and was stopped by its day cap" in html


def test_changing_caps_is_recorded_with_both_values_and_never_extends_the_approval(ai):
    _turn_on(ai)
    before = B.entry_of("branch", "fake_loop")
    r, html = _post(ai, f"{BASE}/{NET}/fake_loop/caps",
                    {"day_cap_usd": "1.00", "month_cap_usd": "20"})
    assert r.status_code == 200 and 'data-result="caps"' in html
    after = B.entry_of("branch", "fake_loop")
    assert (after["day_cap_usd"], after["month_cap_usd"]) == (1.0, 20.0)
    assert after["at"] == before["at"], "the approval's start, and so its end, unchanged"
    (rec,) = [x for x in _record(ai) if x["kind"] == "ai_background_caps"]
    assert rec["before"] == {"day_cap_usd": 0.5, "month_cap_usd": 10.0}
    assert (rec["day_cap_usd"], rec["month_cap_usd"]) == (1.0, 20.0)
