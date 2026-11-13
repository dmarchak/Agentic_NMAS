"""AI troubleshooting's own call (`modules/ai/fixit_troubleshoot.py`, `routes/fixit_v2.py`
``troubleshoot``, `modules/ai/fix_proposal.for_incident`; the fix-it plan's S5; board
recurring-fixes v2, steps 2 and 3; docs/HEAL_TO_INTENT.md section 12, "The AI call (S5)"),
through the real app and the REAL gateway on tests/test_fixit_section_v2.py's lab (r2's real
configuration and intent, a self-healing incident opened by the incidents store's own writer
from two lost-stream alerts, attempt 1 a real Re-subscribe run that read no data). Only the
provider is replaced: every request is counted and answered with what the test sets. No device,
no network, no live AI call. The answers are stand-ins written for each case (no capture of a
model's answer exists yet: the fix-it plan's S7 records them), each shaped by the schema the
gateway sends.

- **The operator's test 1 ("no path retries without a person"), through the gateway:** the
  press is the call's trigger (a person's, the request's verified actor); no background feature
  is registered for it; the incident page, loaded and refreshed, asks no model; an unverified
  press, a resolved incident and the mode off are refused with no provider request.
- **Test 2 ("the cap refuses"):** past the per-incident cap the press is refused naming both
  figures, with no provider request and nothing recorded; the figure drawn before the press is
  the one the route compares.
- **Test 4 ("a repeated proposal is flagged"):** an answer repeating attempt 1 is drawn flagged,
  and opens the operation's own card.
- **The answer checked:** a subscription the incident does not name, another device, a command
  where a parameter goes, a past incident Seen before was not sent, and a fix and a gap together
  are each refused as unchecked, the spend counted and the refusal recorded on the call; a gap
  has no Approve; the evidence that cannot say, and an answer naming no fix, each say so.
- **The note:** a typed part, masked as it leaves and said; it never widens what a fix may act
  on.
- **One press, one call:** a second request with the same press key makes no second request.
- **The pack:** Seen before from Mercury's record, IPv4 and IPv6 addresses as written.
"""
import json
import types

import pytest

from modules.ai import calls, gateway
from modules.fixit import incident as F
from tests.test_fixit_section_v2 import (NET, attempt, incident, page, plant, post,
                                         section_of)
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

KEY = "sk-ant-planted-for-the-test"
ADMIN = "admin@example.com"
REAL_ASK = gateway.ask
CONFIRM = "show telemetry ietf subscription all"


def answer(fix=None, gap=None, *, cites=("attempt:1",), outcome="answer", why_not="",
           rationale="r2's streams stayed down after attempt 1 re-subscribed them.",
           hypotheses=None) -> dict:
    """An answer of the schema's shape (`fixit_troubleshoot.Troubleshoot`): a stand-in."""
    hyps = hypotheses if hypotheses is not None else [
        {"claim": "The collector still holds r2's old session, so no new one opens.",
         "evidence_refs": list(cites), "confirm_with": CONFIRM}]
    return {"outcome": outcome, "rationale": rationale, "hypotheses": hyps, "fix": fix,
            "gap": gap, "needs_human": True, "why_not": why_not}


def fix(operation="telemetry-resubscribe", device="r2", subscriptions=("101", "102"),
        subscription=None, cites=("attempt:1",)) -> dict:
    return {"operation": operation,
            "params": {"device": device,
                       "subscriptions": list(subscriptions) if subscriptions is not None
                       else None, "subscription": subscription},
            "why": "Re-subscribing opens a new session once the old one is gone.",
            "evidence_refs": list(cites)}


@pytest.fixture
def ai(web, monkeypatch, tmp_path):  # noqa: F811
    """`web` with the REAL gateway (the fixture's stand-in that refuses every ask put back),
    hosted AI allowed with a $1.50 day cap and a key, the record of AI calls in the test's
    folder, no topology sent (no network model in a test's folder), and the provider replaced:
    each request kept in ``ai.sent`` and answered with ``ai.answer``."""
    from modules import installation_settings as I
    from modules.ai import explain
    from modules.settings_schema import write_settings

    monkeypatch.setattr(gateway, "ask", REAL_ASK)
    monkeypatch.setattr(I, "_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    # The AI control's own readiness asks the secrets store whether a key is stored (presence
    # only): the same key, said stored.
    monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
    assert write_settings({"ai_hosted": {"by": ADMIN, "at": "2026-11-12T00:00:00Z",
                                         "reason": "the lab's AI troubleshooting"},
                           "ai_cap_usd_per_day": 1.50})["ok"]
    monkeypatch.setattr(explain, "topology", lambda pack: {
        "sent": False, "why": "no network model in the test", "summary": "", "yaml": "",
        "ids": [], "reached": {}, "version": "", "subject": pack.get("device") or "",
        "network": pack.get("network") or "", "observed": "", "names": {}, "as_now": ""})
    w = types.SimpleNamespace(sent=[], answer=answer(), client=web)
    from modules.ai import anthropic_adapter as AD

    def send(body, key):
        w.sent.append(body)
        return AD.Reply(status=200, body={
            "content": [{"type": "text", "text": json.dumps(w.answer)}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 9000, "output_tokens": 600}},
            attempts=1, latency_s=0.2)

    def count(body, key, **kw):
        raise AD.ProviderDown("no count in a test")
    monkeypatch.setattr(gateway, "anthropic_adapter", types.SimpleNamespace(
        **{**vars(AD), "send": send, "count_tokens": count}))
    return w


def press(w, iid, note="", **data):
    r = post(w.client, iid, "troubleshoot", note=note, **data)
    return r, r.get_data(as_text=True)


def data_of(body: dict) -> str:
    return body["messages"][0]["content"]


def sec_of(html: str) -> str:
    """The section's HTML with its entities read (the words as a person reads them)."""
    from html import unescape
    return unescape(section_of(html))


def stopped(w):
    """The incident with attempt 1 failed: the STOP state. Its id."""
    iid = plant()
    attempt(w.client)
    return iid


# ── The press and its one investigation ─────────────────────────────────────────────────────

class TestThePress:
    def test_one_press_asks_once_and_proposes_a_checked_fix_flagged_as_a_repeat(self, ai):
        iid = stopped(ai)
        ai.answer = answer(fix())
        r, html = press(ai, iid)
        assert r.status_code == 200, html
        assert len(ai.sent) == 1, "the device state class is off: the plain pass, one call"
        sec = sec_of(html)
        assert 'data-state="proposed"' in sec
        assert "The AI proposes one fix" in sec
        assert "What's wrong (the AI, checked against what was sent):" in sec
        assert 'class="ai-fb"' in sec, "Was this right? under the AI's answer"
        assert "Proposed before in this incident: attempt 1, failed" in sec
        assert "Open the fix's card…" in sec and "fixit=" + iid in sec
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["source"] == "ai" and line["operation"] == "telemetry-resubscribe"
        assert line["params"]["subs"] == ["101", "102"]
        assert line["prompt"] == "fixit_troubleshoot.v1"
        assert line["shown"]["hypotheses"][0]["cites"] == ["attempt:1"]
        (call,) = line["calls"]
        rows = calls.read()["rows"]
        sent = [x for x in rows if x.get("id") == call]
        assert sent and sent[0]["trigger"]["kind"] == "person"
        assert sent[0]["feature"] == "fixit_troubleshoot"
        assert [x["use"] for x in calls.uses().get(call, [])] == [
            "shown: a proposal, opened in its operation's preview"]
        # The incident's spend is the call's, drawn on the page.
        spent = F.cost_so_far(incident(iid))
        assert spent["state"] == "ok" and spent["usd"] > 0
        _r, again = page(ai.client, iid)
        assert "<strong>This incident:</strong> AI $0.00 " not in sec_of(again)

    def test_what_is_sent_is_the_pack_the_attempts_and_the_note_never_a_command(self, ai):
        iid = stopped(ai)
        press(ai, iid, note="the collector at 2001:db8::20 port 57000 still holds a session")
        (body,) = ai.sent
        text = data_of(body)
        for part in ('<data name="pack">', '<data name="note">', '<data name="the_incident">'):
            assert part in text, part
        assert "attempt:1" in text and '"name":"attempts"' in text
        assert "2001:db8::20" in text, "an IPv6 address the note holds goes as written"
        system = " ".join(b["text"] for b in body["system"])
        assert "telemetry-resubscribe" in system and "telemetry-readd" in system
        assert "read_set" not in system, "the class off: the plain pass carries no read set"
        # The attempt's approver is a stable label, never their identity (the payload's).
        from tests.test_heal_resubscribe import ACTOR
        assert ACTOR not in json.dumps(body) and "person-" in text

    def test_a_secret_in_the_note_is_masked_before_it_leaves_and_said(self, ai):
        """The note is the typed part ``note`` (`gateway.TYPED_PARTS`): masked as it leaves by
        the person's own words' mask, said back on the section, and masked at rest."""
        iid = stopped(ai)
        secret = "$9$abcdefghijklmn$opqrstuvwxyz0123456789ABCDEFG"
        r, html = press(ai, iid, note=f"the old router had enable secret 9 {secret} on it")
        assert r.status_code == 200
        (body,) = ai.sent
        assert "opqrstuvwxyz0123456789" not in json.dumps(body)
        assert "data-typed-masked" in sec_of(html), "what was masked is said in place"
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert "opqrstuvwxyz0123456789" not in json.dumps(line)

    def test_the_gap_has_no_approve(self, ai):
        iid = stopped(ai)
        ai.answer = answer(gap={"what": "close the collector's session from r2 on its host",
                                "evidence_refs": ["attempt:1"]})
        r, html = press(ai, iid)
        sec = sec_of(html)
        assert r.status_code == 200 and "a gap" in sec
        assert "Open the fix's card…" not in sec and "none Mercury can run" in sec
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["operation"] == "" and line["calls"] and line["shown"]["gap"]

    @pytest.mark.parametrize("kind,ans,said", [
        ("unanswerable", answer(outcome="refuse", hypotheses=[], why_not="nothing bears on it"),
         "the evidence cannot say"),
        ("no fix", answer(), "The AI named no fix"),
    ])
    def test_no_fix_is_said_and_kept(self, ai, kind, ans, said):
        iid = stopped(ai)
        ai.answer = ans
        _r, html = press(ai, iid)
        assert said in sec_of(html), kind
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["operation"] == "" and line["calls"], kind


# ── The check ───────────────────────────────────────────────────────────────────────────────

class TestTheCheck:
    @pytest.mark.parametrize("ans,why", [
        (answer(fix(subscriptions=("101", "103"))), "103"),
        (answer(fix(device="r6")), "r6"),
        (answer(fix(subscriptions=("101 ; configure terminal",))), "subscriptions"),
        (answer(fix(operation="configure terminal")), "catalog"),
        (answer(fix(), cites=("seen_before:2",)), "seen_before:2"),
        (answer(fix(), gap={"what": "both", "evidence_refs": ["attempt:1"]}), "both a fix"),
    ], ids=["another subscription", "another device", "a command as a parameter",
            "a command as the operation", "a past incident not sent", "a fix and a gap"])
    def test_an_answer_out_of_scope_is_refused_as_unchecked_and_recorded(self, ai, ans, why):
        iid = stopped(ai)
        ai.answer = ans
        r, html = press(ai, iid)
        sec = sec_of(html)
        assert r.status_code == 200
        assert "couldn't be checked, so it isn't shown" in sec and why in sec, sec
        assert "Open the fix's card…" not in sec
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["operation"] == "" and line["calls"], "the spend stays the incident's"
        uses = calls.uses().get(line["calls"][0], [])
        assert [u["use"] for u in uses] == ["refused by validation"]

    def test_the_note_never_widens_what_a_fix_may_act_on(self, ai):
        iid = stopped(ai)
        ai.answer = answer(fix(device="r6"), cites=("note:1",))
        _r, html = press(ai, iid, note="r6 is the one to re-subscribe, do it there")
        assert "which is not one the finding names" in sec_of(html)
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["operation"] == "" and line["params"] == {}, "nothing is proposed on r6"
        assert len(ai.sent) == 1

    def test_a_refused_fix_through_the_door_is_kept_with_no_operation(self, ai, monkeypatch):
        """A fix the catalog's schema takes and Mercury's own check refuses (here guard 3: the
        device held by planned work) is recorded on its call and kept with no operation."""
        iid = stopped(ai)
        monkeypatch.setattr("modules.heal.guards.g3_planned", lambda *a, **k: {
            "guard": 3, "name": "planned work", "words": "a planned restart window holds r2"})
        ai.answer = answer(fix())
        _r, html = press(ai, iid)
        assert "Mercury's check refused" in sec_of(html)
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["operation"] == "" and "guard 3" in line["words"]
        uses = calls.uses().get(line["calls"][0], [])
        assert [u["use"] for u in uses] == ["refused by validation"]


# ── Refused at the press, nothing sent ──────────────────────────────────────────────────────

class TestRefusedAtThePress:
    def test_past_the_cap_nothing_is_sent_and_both_figures_are_named(self, ai):
        from modules.settings_schema import write_settings
        iid = stopped(ai)
        assert write_settings({"ai_cap_usd_per_incident": 0.10})["ok"]
        r, html = press(ai, iid, drawn_spent="0.000000", drawn_cap="1.000000")
        assert r.status_code == 409
        said = sec_of(html)
        assert "Not asked" in said and "$0.2502" in said and "$0.10" in said
        assert "the per-incident cap was $1.00 when the panel was drawn" in said
        assert ai.sent == [] and calls.read()["rows"] == []
        assert F.read(incident(iid))["state"] == "absent"

    def test_the_figure_drawn_is_the_figure_compared(self, ai):
        """The worst case drawn is two calls at the pin's per-call cap, the figure the route's
        cap compares (the board's "at most $0.25"; the price table makes it $0.2502)."""
        from modules.ai import fixit_troubleshoot as AIT
        from modules.ai import profiles
        from modules.fixit import policy as P
        iid = stopped(ai)
        _r, html = page(ai.client, iid)
        sec = sec_of(html)
        worst = AIT.worst_usd()
        assert worst == round(2 * profiles.cap_per_call("fixit_troubleshoot"), 6)
        assert f"at most {P.money(worst)} (one investigation: at most two calls" in sec
        assert P.cap_state(incident(iid), worst)["worst"] == worst
        assert 'name="drawn_cap" value="1.000000"' in sec

    def test_the_mode_off_sends_nothing(self, ai):
        from modules.settings_schema import write_settings
        iid = stopped(ai)
        assert write_settings({"ai_troubleshoot_mode": "off"})["ok"]
        _r, html = page(ai.client, iid)
        assert "/fixit/troubleshoot" not in sec_of(html)
        r, html = press(ai, iid)
        assert r.status_code == 409 and "its mode is Off" in sec_of(html)
        assert ai.sent == []

    def test_an_unverified_press_sends_nothing(self, ai, monkeypatch):
        iid = stopped(ai)
        monkeypatch.setattr("modules.identity.verified_identity", lambda *a, **k: None)
        r, _html = press(ai, iid)
        assert r.status_code == 403 and ai.sent == []

    def test_a_resolved_incident_sends_nothing(self, ai):
        from modules.heal import incidents
        from tests.test_fixit_incident import T0
        iid = stopped(ai)
        incidents.close(NET, iid, "the alert cleared", now=T0)
        r, _html = press(ai, iid)
        assert r.status_code == 409 and ai.sent == []


# ── One press, the trigger, and no other way in ─────────────────────────────────────────────

class TestNoOtherWayIn:
    def test_one_press_key_is_one_call(self, ai):
        iid = stopped(ai)
        h = {"HX-Request": "true", "X-NMAS-Press": "a" * 32}
        for _ in range(2):
            r = ai.client.post(f"/v2/incident/{iid}/fixit/troubleshoot?list={NET}",
                               data={"note": ""}, headers=h)
            assert r.status_code == 200
        assert len(ai.sent) == 1

    def test_no_background_feature_and_the_only_way_in_is_the_gated_post(self):
        from modules.ai import background
        from tests import test_ai_controls as T
        from tests.test_ai_entry_points import entry_points
        assert not [f for f in background.FEATURES if "fixit" in f]
        found = entry_points(T._sources())
        mine = {k: v for k, v in found.items() if k[0] == "routes.fixit_v2"}
        assert mine == {("routes.fixit_v2", "troubleshoot"): {
            "endpoint": "fixit_v2.troubleshoot", "methods": ["POST"]}}

    def test_the_incident_page_calls_no_model_and_draws_the_control(self, ai, monkeypatch):
        from tests.test_ai_entry_points import FIXIT_PAGES, _count_ai
        iid = plant()
        seen = _count_ai(monkeypatch)
        for url in FIXIT_PAGES["fixit_troubleshoot"]:
            for headers in ({}, {"HX-Request": "true"}, {}):
                r = ai.client.get(url.format(incident=iid), headers=headers)
                assert r.status_code == 200
                assert 'data-ai-control="fixit_troubleshoot"' in r.get_data(as_text=True)
        assert seen == {"asked": [], "sends": []}

    def test_the_control_s_states(self, ai, monkeypatch):
        """The AI mark, and the control disabled with its reason in each state hosted AI
        cannot answer (tests/ai_controls_check.py); Hand over, beside it, stays usable."""
        import re

        from tests import ai_controls_check
        iid = plant()

        def get_html():
            return page(ai.client, iid)[1]

        def parity(html):
            sec = sec_of(html)
            button = re.search(r'<button[^>]*>\s*<span class="op-idle">Send the hand-over', sec)
            assert button and "data-ai-off" not in button.group(0)
        ai_controls_check.check_screen(monkeypatch, get_html, "fixit_troubleshoot", parity)


# ── The pack's own parts ────────────────────────────────────────────────────────────────────

class TestThePack:
    @pytest.mark.parametrize("address", ["192.0.2.20", "2001:db8::20"])
    def test_seen_before_is_mercury_s_record_its_addresses_as_written(self, address):
        from modules.ai import fixit_troubleshoot as AIT
        value = {"streams": {"state": "read", "devices": {"r2": {"seen": {
            "state": "match", "record": f"Seen before on r2: Nov 8, the collector {address} "
                                        "held a dead session", "from": "2026-11-08T20:05:00Z",
            "to": "2026-11-08T21:01:37Z", "what": "lost telemetry", "cause": "half_open",
            "ended": {"words": "fixed by a change on r2's console"}, "held": {}}}}}}
        s = AIT.seen_section(NET, "r2", value)
        assert s["state"] == "ok" and [p["ref"] for p in s["pieces"]] == ["seen_before:1"]
        assert address in s["pieces"][0]["words"]

    def test_no_stored_reading_is_said_never_a_match(self):
        from modules.ai import fixit_troubleshoot as AIT
        s = AIT.seen_section(NET, "r2", {})
        assert s["state"] == "absent" and not s["pieces"] and s["why"]
