"""The AI analysis of a can't-fix (board H, part H8; docs/HEAL_TO_INTENT.md section 12;
`modules/ai/heal_analysis.py`). No provider call: every call goes through the real gateway with
a real settings file and record of AI calls in the test's folder, and only the provider is a
fake (a `send` that keeps what it got and answers as the test says).

- **The trigger and the precondition:** only an incident that stopped at can't fix asks (the
  decision's can't fix, an act's symptom remaining, a rollback); a dry-run record or a healed
  incident asks nothing, and nothing reaches the gateway. The call names its background
  trigger: the feature ``heal_analysis``, a job, the network's id, the finding
  ``heal_incident`` and the incident's id, its actor the job's.
- **Off by default per network:** never turned on, the gateway refuses it, recorded, nothing is
  sent, and the analysis says "not run, off for this network"; on for Default it stays off for
  Branch. Its estimate is measured from the heal's own step log, unknown when nothing is
  recorded.
- **Egress by kind:** no configuration line of the step log leaves as text (the program, each
  unit's lines, a line a step's words held), each unit said by its kind; the intent section's
  masked intent-diff lines go, at most 20 (N10), a secret's value masked.
- **The check is Explain's:** a citation that resolves to nothing, or a next step that is not
  an allowed read, is couldn't analyse, and nothing of it is drawn.
- **Failure states said in place:** capped (and Needs attention's analysis_capped row, until its
  day ends), the provider not answering within its bound, couldn't analyse; the store keeps each.
- **Needs attention's can't-fix row:** What to do, then Mercury's facts, then the analysis,
  drawn from what it kept when the item opens (the route reads, never calls); it clears when a
  later decision finds the device with nothing to heal.
"""
import json
import os
import types

import pytest

from modules.ai import anthropic_adapter as AD
from modules.ai import background as B
from modules.ai import calls, gateway, schemas, triggers
from tests.test_ai_gateway import KEY
from tests.test_heal_decide import GI2, GOLDEN, Fake, changed, settle
from tests.test_heal_decide import lab  # the fixture, named by each test below
from tests.test_heal_policy import T0
from tests.test_sdn_connections import networks  # the fixture `lab` builds on
from tests.test_heal_triggers import _Lazy


class _Module:
    """A module imported when a test first names it (red on a tree without it, each test on
    its own, never the whole file at collection)."""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib

        return getattr(importlib.import_module(self._name), attr)


DC, DS, SL = _Lazy("decide"), _Lazy("decisions"), _Lazy("steplog")
HA = _Module("modules.ai.heal_analysis")
ADMIN = "admin@example.com"
ACL = " ip access-group EDGE-IN in\n"
ACL_RUNNING = changed((GI2, GI2 + ACL))
JOB = "heal-notice-test"


@pytest.fixture
def ai(lab, monkeypatch):
    """The heal lab (Default marked lab, dry run), hosted AI allowed with a $1.50 day cap, a
    key, the settings record and the record of AI calls in the test's folder, and a fake
    provider answering what the test sets (`w.answer`)."""
    from modules import installation_settings as I
    from modules.settings_schema import write_settings

    tmp = lab
    monkeypatch.setattr(I, "_path", lambda name: str(tmp / name))
    monkeypatch.setattr(calls, "_path", lambda: str(tmp / "ai_calls.jsonl"))
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    assert write_settings({"ai_hosted": {"by": ADMIN, "at": "2026-10-27T00:00:00Z",
                                         "reason": "the lab's heal analysis"},
                           "ai_cap_usd_per_day": 1.50})["ok"]
    # The network model is not built in a test's folder: no topology goes, said so.
    from modules.ai import explain
    monkeypatch.setattr(explain, "topology", lambda pack: {
        "sent": False, "why": "no network model in the test", "summary": "", "yaml": "",
        "ids": [], "reached": {}, "version": "", "subject": pack.get("device") or "",
        "network": pack.get("network") or "", "observed": "", "names": {}, "as_now": ""})
    w = types.SimpleNamespace(sent=[], answer=None, fail=None, dir=tmp)

    def send(body, key):
        w.sent.append(body)
        if w.fail is not None:
            raise w.fail
        text = json.dumps(w.answer if w.answer is not None else ANSWER)
        return AD.Reply(status=200, body={"content": [{"type": "text", "text": text}],
                                          "stop_reason": "end_turn",
                                          "usage": {"input_tokens": 900, "output_tokens": 120}},
                        attempts=1, latency_s=0.2)
    w.send = send
    return w


ANSWER = {"outcome": "answer",
          "rationale": "Self-healing stopped because the added line is a security ACL, which "
                       "it never removes.",
          "hypotheses": [{"claim": "An ACL bound inbound on Gi2 was added outside intent.",
                          "evidence_refs": ["tried:7"],
                          "confirm_with": "show ip interface GigabitEthernet2"}],
          "needs_human": True, "why_not": ""}


def turn_on(network="Default", day=0.50, month=10.0):
    est = B.estimate(network, HA.FEATURE)
    return B.turn_on(network, HA.FEATURE, day_cap_usd=day, month_cap_usd=month,
                     shown=est["digest"], actor=ADMIN, verified="access")


def cant_fix(running=ACL_RUNNING, now=T0):
    """A real can't-fix: an incident settled on *running*, decided by the real decision (a
    security ACL is Tier 4: self-healing will not fix it), its steps in the step log."""
    settle(running, claim=False)
    got = DC.run("Default", now=now, sources=Fake(running))
    (d,) = got["decided"]
    assert d["outcome"] == "cant_fix", d
    return d["incident"]


def analyse(w, incident, **kw):
    return HA.analyse("Default", incident, job=JOB, send=w.send, now=T0 + 1, **kw)


def ai_rows():
    return calls.read()["rows"]


# ── The trigger and the precondition ──────────────────────────────────────────────────────────

class TestTheTrigger:
    def test_the_call_names_its_background_trigger_and_finding(self, ai):
        turn_on()
        inc = cant_fix()
        got = analyse(ai, inc)
        assert got["state"] == "answered", got.get("words")
        (row,) = ai_rows()
        assert row["trigger"] == {"kind": "background", "feature": "heal_analysis", "job": JOB,
                                  "network": "default",
                                  "finding": {"kind": "heal_incident", "id": inc}}
        assert row["actor"] == triggers.JOB_PREFIX + JOB and row["feature"] == HA.FEATURE
        assert row["subject"]["kind"] == "heal_incident" and row["subject"]["id"] == inc

    def test_only_a_cant_fix_asks_and_nothing_else_reaches_the_gateway(self, ai):
        turn_on()
        running = GOLDEN + "ip route 192.0.2.128 255.255.255.128 192.0.2.10\n"
        settle(running, claim=False)
        (d,) = DC.run("Default", now=T0, sources=Fake(running))["decided"]
        assert d["outcome"] == "would_heal", "a dry-run record"
        got = analyse(ai, d["incident"])
        assert got["state"] == "not_cant_fix" and "only a can't-fix asks" in got["words"]
        assert ai.sent == [] and ai_rows() == [], "nothing reached the gateway"

    def test_the_outcomes_that_ask_are_the_three_named(self):
        assert HA.CANT_FIX == ("cant_fix", "symptom_remains", "rolled_back")
        assert B.FEATURES["heal_analysis"]["findings"] == ("heal_incident",)
        # The read loop's two passes (19.5: "`calls_per_finding` becomes 2", H26), so the
        # estimate shown at Turn on counts both.
        from modules.ai import read_loop
        assert B.FEATURES["heal_analysis"]["calls_per_finding"] == 2 \
            == read_loop.CALLS_PER_FINDING

    def test_a_step_log_that_cannot_be_read_asks_nothing_and_says_so(self, ai):
        turn_on()
        inc = cant_fix()
        with open(SL._path("Default"), "a", encoding="utf-8") as fh:
            fh.write("{torn\n")
        got = analyse(ai, inc)
        assert got["state"] == "couldnt_analyse" and "could not be read" in got["words"]
        assert ai.sent == []

    def test_a_pack_naming_a_person_with_no_label_key_asks_nothing_and_names_the_key(
            self, ai, monkeypatch):
        """C3458: the incident's pack names a person and no label key is installed: nothing
        is sent, no key is made, and the words name the missing key (never "could not be
        read": the step log read)."""
        from modules import display_names, secrets_store
        from modules import evidence_pack as EP
        from modules.config import get_user_setting, set_user_setting
        turn_on()
        inc = cant_fix()
        built = EP.build_incident

        def naming_a_person(*a, **kw):
            pack = built(*a, **kw)
            pack["sections"].append({"ref": "history", "name": "history", "state": "ok",
                                     "pieces": [{"ref": "history:9", "kind": "note",
                                                 "who": "alice.ops@example.com",
                                                 "what": "checked the ACL"}]})
            return pack
        monkeypatch.setattr(EP, "build_incident", naming_a_person)
        monkeypatch.delitem(display_names._LABEL_KEY, "key", raising=False)
        was = get_user_setting(display_names.LABEL_KEY_SETTING, "")
        secrets_store.set_secret(display_names.LABEL_KEY_SETTING, "")
        try:
            got = analyse(ai, inc)
            assert get_user_setting(display_names.LABEL_KEY_SETTING, "") == "", "a key made"
        finally:
            set_user_setting(display_names.LABEL_KEY_SETTING, was)
        assert got["state"] == "couldnt_analyse", got
        assert display_names.LABEL_KEY_SETTING in got["words"]
        assert "nothing was sent" in got["words"] and "could not be read" not in got["words"]
        assert ai.sent == []


# ── Off by default per network ────────────────────────────────────────────────────────────────

class TestOffByDefault:
    def test_never_turned_on_it_is_refused_recorded_and_nothing_is_sent(self, ai):
        inc = cant_fix()
        got = analyse(ai, inc)
        assert got["state"] == "off" and got["words"] == ("AI analysis: not run, off for this "
                                                          "network")
        assert ai.sent == []
        (row,) = ai_rows()
        assert row["verdict"] == "feature_off", row
        assert HA.latest("Default", inc)["state"] == "off", "kept, said in place"

    def test_on_for_default_it_stays_off_for_branch(self, ai):
        turn_on("Default")
        assert B.entry_of("default", HA.FEATURE) is not None
        assert B.entry_of("branch", HA.FEATURE) is None

    def test_turned_off_its_next_call_is_refused_and_nothing_is_sent(self, ai):
        """The operator's condition for H8 (2026-11-04): its switch stops it. On, a can't-fix
        is asked and recorded under the feature; Turn off, and the next one reaches no
        provider, refused as the feature off and recorded."""
        turn_on()
        inc = cant_fix()
        assert analyse(ai, inc)["state"] == "answered" and len(ai.sent) == 1
        B.turn_off("Default", HA.FEATURE, actor=ADMIN, verified="access")
        assert B.entry_of("default", HA.FEATURE) is None
        got = analyse(ai, inc)
        assert got["state"] == "off" and len(ai.sent) == 1, "nothing more reached the provider"
        assert sorted(r.get("verdict") for r in ai_rows()) == ["feature_off", "ok"], \
            "the answered call and the refusal, each recorded"

    def test_on_it_is_listed_with_the_spending_background_features_and_off_it_is_not(self, ai):
        """The operator's condition for H8: it can spend, so the spend tracker lists it among
        the background features on, its spend counted under it; off, it leaves the list."""
        import datetime

        from modules.ai import spend
        turn_on()
        assert analyse(ai, cant_fix())["state"] == "answered"
        (row,) = ai_rows()
        assert spend._of_feature(row, "default", HA.FEATURE), row["trigger"]
        now = datetime.datetime.now(datetime.timezone.utc)
        listed = {(f["network"], f["feature"]) for f in spend.panel(ADMIN, now=now)["features"]}
        assert ("default", HA.FEATURE) in listed, listed
        B.turn_off("Default", HA.FEATURE, actor=ADMIN, verified="access")
        listed = {(f["network"], f["feature"]) for f in spend.panel(ADMIN, now=now)["features"]}
        assert ("default", HA.FEATURE) not in listed, listed

    def test_hosted_ai_off_is_said(self, ai):
        from modules.settings_schema import write_settings
        turn_on()
        assert write_settings({"ai_hosted": {}})["ok"]
        got = analyse(ai, cant_fix())
        assert got["state"] == "off" and "hosted AI is off" in got["words"] and ai.sent == []

    def test_its_estimate_is_measured_from_the_heal_s_own_record(self, ai):
        assert HA.cant_fix_frequency("default", now=T0)["per_day"] is None, \
            "nothing recorded: unknown, never guessed"
        cant_fix()
        got = HA.cant_fix_frequency("default", now=T0 + 3600)
        assert got["per_day"] == pytest.approx(1.0) and "1 can't-fix" in got["basis"]
        # The estimate asks the same measurement, at the clock's time (the planted incident's
        # T0 is past the window there, so none in it: zero measured, not unknown).
        est = B.estimate("Default", HA.FEATURE)
        assert est["frequency"] == HA.cant_fix_frequency("default") and est["task"] == HA.FEATURE
        assert est["frequency"]["per_day"] == 0.0 and "heal's step log" in \
            est["frequency"]["basis"]


# ── Egress by kind ────────────────────────────────────────────────────────────────────────────

class TestEgressByKind:
    def test_no_configuration_line_of_the_step_log_leaves_as_text(self, ai):
        turn_on()
        inc = cant_fix()
        analyse(ai, inc)
        (body,) = ai.sent
        sent = json.dumps(body)
        assert "ip access-group EDGE-IN in" not in sent, "a unit's line never leaves"
        assert "EDGE-IN" not in sent
        assert "a security ACL added outside intent on GigabitEthernet2, 1 line, content " \
               "withheld" in sent, "the unit by its kind"

    def test_a_line_a_step_s_words_held_is_withheld(self, ai, monkeypatch):
        turn_on()
        inc = cant_fix()
        real = SL.incident

        def planted(network, incident_id):
            e = real(network, incident_id)
            e["program"] = ["no ip route 192.0.2.128 255.255.255.128 192.0.2.10"]
            e["steps"].append({"step": "authorise", "result": "refused", "row": "act",
                               "words": "the program holds 1 line the CI gate counts dangerous "
                                        "(no ip route 192.0.2.128  255.255.255.128 192.0.2.10)"})
            return e
        monkeypatch.setattr("modules.heal.steplog.incident", planted)
        analyse(ai, inc)
        sent = json.dumps(ai.sent[0])
        assert "192.0.2.128" not in sent, "matched ignoring its spacing, and withheld"
        from modules import evidence_pack
        assert evidence_pack.WITHHELD in sent
        assert "the program: 1 line, hash" in sent and "content withheld" in sent

    def test_the_intent_lines_go_masked_and_at_most_twenty_n10(self, ai, monkeypatch):
        from modules import device_page
        from modules import evidence_pack as EP

        turn_on()
        inc = cant_fix()
        monkeypatch.setattr(device_page, "find_device", lambda name, ref: (ref, {
            "hostname": name, "ip": "192.0.2.6", "platform": "cisco_iosxe"}))
        diff = (["- snmp-server community Plant3dRO RO"]
                + [f"- ip route 192.0.2.{i} 255.255.255.255 Null0" for i in range(30)])

        def intent(ref, dev):
            return EP._section("intent", "planted", T0, "ok", pieces=[{
                "state": "differs", "lines": EP.intent_lines({"state": "differs",
                                                              "lines": diff})}])
        monkeypatch.setattr(EP, "intent_section", intent)
        analyse(ai, inc)
        sent = json.dumps(ai.sent[0])
        assert "Plant3dRO" not in sent, "a secret's value is masked"
        assert "192.0.2.18 " in sent and "192.0.2.19 " not in sent, "at most 20 lines"
        assert EP.INTENT_LINES == 20

    def test_the_pack_goes_as_explain_s_the_observed_overlay_never_as_pack_data(self, ai):
        turn_on()
        analyse(ai, cant_fix())
        (body,) = ai.sent
        pack = body["messages"][0]["content"]
        assert '"name":"observed"' not in pack, "the topology class rides in the subgraph only"
        assert '"name":"tried"' in pack and '"name":"incident"' in pack

    def test_the_withhold_matches_whole_lines_only(self):
        from modules import evidence_pack as EP
        assert EP.withhold("removed ip route 192.0.2.0/24 here", ["ip route 192.0.2.0/24"]) == \
            f"removed {EP.WITHHELD} here"
        assert EP.withhold("removed ipv6 route 2001:db8::/32 Null0 here",
                           ["ipv6 route 2001:db8::/32 Null0"]) == f"removed {EP.WITHHELD} here"
        assert EP.withhold("Removed IP Route 192.0.2.0/24 here", ["ip route 192.0.2.0/24"]) \
            == f"Removed {EP.WITHHELD} here", "a line found whatever its case"
        assert EP.withhold("router ospf 10", ["router ospf 1"]) == "router ospf 10", \
            "a longer line is not the line"
        assert EP.withhold("end", ["end"]) == "end", "too short to be a line"


# ── The check is Explain's ────────────────────────────────────────────────────────────────────

class TestTheCheck:
    @pytest.mark.parametrize("hyp,said", [
        ({"claim": "c", "evidence_refs": ["tried:99"], "confirm_with": "show version"},
         "hypothesis 1 cites 'tried:99', which is not in the pack"),
        ({"claim": "c", "evidence_refs": ["tried:1"], "confirm_with": "configure terminal"},
         "not a read Mercury allows")])
    def test_an_answer_that_does_not_hold_is_couldnt_analyse_and_nothing_is_drawn(
            self, ai, hyp, said):
        turn_on()
        ai.answer = dict(ANSWER, hypotheses=[hyp])
        got = analyse(ai, cant_fix())
        assert got["state"] == "couldnt_analyse" and said in got["words"], got["words"]
        assert got["answer"] is None
        b = HA.block(HA.latest("Default", got["incident"]))
        assert b["hypotheses"] == [] and b["words"].startswith("AI analysis: couldn't analyse")
        uses = [r for r in calls._all()["rows"] if r.get("use_of")]
        assert uses and uses[-1]["use"] == "refused by validation"

    def test_a_checked_answer_is_drawn_with_its_label_and_next_step(self, ai):
        turn_on()
        got = analyse(ai, cant_fix())
        b = HA.block(got)
        assert b["state"] == "answered" and b["label"] == "Advisory (beta), a person should " \
                                                          "confirm"
        assert "not measured yet" in b["score"], "never Explain's figure"
        (h,) = b["hypotheses"]
        assert h["next"] == "show ip interface GigabitEthernet2" and h["cites"] == ["tried:7"]

    def test_a_recorded_pack_is_asked_as_the_feature_asks_it_and_kept_nowhere(self, ai):
        """H13's seam: a pack replayed under an evaluation run's trigger, the same request and
        check, nothing kept with the incident."""
        inc = cant_fix()
        pack = HA.prepare("Default", inc)["pack"]
        got = HA.ask_prepared(HA.request_of(pack),
                              trigger=triggers.evaluation("evaluation:h13-planted"),
                              send=ai.send)
        assert got["state"] == "answered" and got["incident"] == inc
        (row,) = ai_rows()
        assert row["trigger"] == {"kind": "evaluation", "run": "h13-planted"}
        assert HA.read("Default")["state"] == "absent", "an evaluation keeps nothing"

    def test_the_schema_is_shape_b_registered_with_no_reads_field_yet(self):
        assert schemas.REGISTRY[("heal_analysis", 1)] is HA.Analysis is HA.SCHEMA_OF[1]
        assert set(HA.Analysis.model_fields) == {"outcome", "rationale", "hypotheses",
                                                 "needs_human", "why_not"}


# ── Failure states, said in place ─────────────────────────────────────────────────────────────

class TestFailureStates:
    def test_past_its_cap_it_is_capped_and_raises_its_row_until_the_day_ends(self, ai,
                                                                           monkeypatch):
        from modules import attention

        turn_on(day=0.01, month=10.0)
        got = analyse(ai, cant_fix())
        assert got["state"] == "capped" and got["words"] == ("AI analysis: not run, its cap for "
                                                             "today is reached")
        assert ai.sent == []
        monkeypatch.setattr(attention, "_page_network", lambda: "Default")
        at = HA.latest("Default", got["incident"])["epoch"]
        rows = [r for r in attention.heal_source(now=at + 1)["rows"]
                if r["kind"] == "analysis_capped"]
        (r,) = rows
        ends = HA.capped("Default", now=at + 1)["ends"]
        assert "Settings › AI" in r["action"]["label"] and ends > at and r["clears_at"]
        assert attention.CLEARS[("heal", "analysis_capped")][0] == ("resolves", "time")
        assert [x for x in attention.heal_source(now=ends + 1)["rows"]
                if x["kind"] == "analysis_capped"] == [], "the day ended"

    def test_the_provider_not_answering_is_said_with_its_bound(self, ai):
        turn_on()
        ai.fail = AD.ProviderDown("no answer within 60 s (ReadTimeout)", attempts=3)
        got = analyse(ai, cant_fix())
        assert got["state"] == "no_answer"
        assert got["words"].startswith(f"AI analysis: the provider did not answer within "
                                       f"{int(round(gateway.send_bound_s()))} s")


# ── The store ─────────────────────────────────────────────────────────────────────────────────

class TestTheStore:
    def test_an_incident_is_claimed_once(self, ai):
        assert HA.claim("Default", "hi-000000000001", job=JOB) is True
        assert HA.claim("Default", "hi-000000000001", job=JOB) is False
        assert HA.claim("Default", "hi-000000000002", job=JOB) is True

    def test_the_newest_analysis_is_drawn_and_an_unreadable_store_is_said(self, ai):
        inc = cant_fix()
        analyse(ai, inc)
        turn_on()
        analyse(ai, inc)
        assert HA.latest("Default", inc)["state"] == "answered"
        assert HA.drawn("Default", inc)["block"]["state"] == "answered"
        with open(HA.path("Default"), "a", encoding="utf-8") as fh:
            fh.write("{torn\n")
        assert HA.drawn("Default", inc)["state"] == "unreadable"
        with pytest.raises(RuntimeError):
            HA.claim("Default", "hi-000000000009", job=JOB)

    def test_every_string_is_masked_before_it_is_kept(self, ai):
        turn_on()
        ai.answer = dict(ANSWER, rationale="It was snmp-server community S3cretRO RO on r6.")
        inc = cant_fix()
        assert analyse(ai, inc)["state"] == "answered"
        with open(HA.path("Default"), encoding="utf-8") as fh:
            kept = fh.read()
        assert "S3cretRO" not in kept and inc in kept
        assert oct(os.stat(HA.path("Default")).st_mode & 0o777) == "0o600"

    def test_a_write_creates_no_network(self, ai):
        with pytest.raises(HA.Refused, match="is no network"):
            HA.claim("Nowhere", "hi-000000000001", job=JOB)


# ── Needs attention's can't-fix row ───────────────────────────────────────────────────────────

class TestTheCantFixRow:
    def rows(self, monkeypatch, now=T0 + 20):
        from modules import attention
        monkeypatch.setattr(attention, "_page_network", lambda: "Default")
        return [r for r in attention.heal_source(now=now)["rows"] if r["kind"] == "cant_fix"]

    def test_the_row_says_what_to_do_then_the_facts_then_draws_the_analysis(self, ai,
                                                                           monkeypatch):
        from modules.attention import ACKNOWLEDGED_HERE, CLEARS

        turn_on()
        inc = cant_fix()
        analyse(ai, inc)
        (r,) = self.rows(monkeypatch)
        assert r["level"] == "danger" and r["event"] == inc and r["acknowledge"]
        assert r["action"]["label"].startswith("Decide on the ACL")
        # C2817 (mock 3a): the cause in plain words, what happened drawn from the decision's own
        # cause (C2823) and the steps tried under "Details for the record" (the operands).
        # C2839: a security ACL is Tier 2; this one waits on its removal shape's measurement.
        assert r["cause"].startswith("Mercury cannot fix this yet"), r["cause"]
        assert r["heal_cause"]["facts"][0]["text"].startswith(
            "edge-b's configuration was changed outside Mercury")
        assert [s.split(":")[0] for s in r["operands"]["steps"]][:2] == ["claim", "stops"]
        assert "History" not in r["action"]["label"], "rule 5: the facts are drawn in place"
        assert r["heal_analysis"] == {"network": "Default", "incident": inc}
        # Board H's amendment, artboard I (H16's second part): Diagnose… on a can't-fix row
        # of any tier, Never's included (this ACL's), on the incident's device.
        assert (r["diagnose"]["device"], r["diagnose"]["list"]) == (r["devices"][0],
                                                                     "Default"), r["diagnose"]
        assert ("heal", "cant_fix") in ACKNOWLEDGED_HERE
        assert "acknowledge" in CLEARS[("heal", "cant_fix")][0]

    def test_the_route_draws_what_was_kept_and_never_calls(self, ai, monkeypatch):
        from app import app

        turn_on()
        inc = cant_fix()
        analyse(ai, inc)
        sent = len(ai.sent)
        page = app.test_client().get(f"/v2/attention/heal-analysis/Default/{inc}")
        text = page.get_data(as_text=True)
        assert page.status_code == 200
        assert "Advisory (beta), a person should confirm" in text
        assert "show ip interface GigabitEthernet2" in text and "tried:7" in text
        assert len(ai.sent) == sent and len(ai_rows()) == 1, "drawing it sends nothing"
        other = app.test_client().get("/v2/attention/heal-analysis/Default/hi-000000000abc")
        assert "AI analysis: pending" in other.get_data(as_text=True)
        bad = app.test_client().get("/v2/attention/heal-analysis/Default/not-an-id")
        assert "no analysis is drawn" in bad.get_data(as_text=True)

    def test_a_later_decision_with_nothing_to_heal_clears_it(self, ai, monkeypatch):
        inc = cant_fix()
        assert [r["operands"]["incident"] for r in self.rows(monkeypatch)] == [inc]
        DS.record("Default", {"outcome": "nothing", "device": "edge-b"}, T0 + 15)
        assert self.rows(monkeypatch) == []
