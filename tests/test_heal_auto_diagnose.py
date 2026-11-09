"""The automatic diagnosis (board H's amendment, item 1, part H17; docs/HEAL_TO_INTENT.md 19.3,
N14, N23 and N24; `modules/heal/auto_diagnose.py`, `modules/heal_notice.py`,
`modules/evidence_pack.py`'s ``diagnosis`` section). No device and no provider: the runbook
is replaced at its seam (`diagnose=`) by a fake that records what the real one would, and the
target is chosen on the fleet's real intent (tests/test_heal_diagnose.py's `fleet`).

- **Which incidents (N14):** an Alert incident (the decision's can't fix at Tier 3) is
  diagnosed before its notice; a Never incident (a security ACL, Tier 4) is not; a proposal
  waiting for a person is diagnosed once, in its own thread, never twice.
- **Its runbook and target, from what raised it:** an alert naming an interface runs
  "adjacency down" on the adjacency over it, and only on it (a named interface intent holds
  none over is not diagnosed, said, no other link read); an adjacency down toward its other
  end; a device unreachable runs "can't reach" from its first neighbour by intent to its
  loopback; anything else is not diagnosed, said.
- **Its bounds (N24):** one per incident across processes; three at once per network, the
  fourth said "not diagnosed: 3 diagnoses already running on Default".
- **What it ends with:** the diagnosis attached to its incident (or one not made, with its
  words), and the announcement ``heal-diagnose`` (C2584).
- **By kind off the host:** the notice and the AI analysis's pack say each hypothesis by its
  rule's words, the ends it read and its strength, never the value it compared.
- **The notice waits for it:** back in time, the first message carries it after what was
  detected and before the steps; not back, the message says so and a follow-up carries it.
- **The screens:** the can't-fix row and the proposal's card carry it; the Self-healing tab
  says the AI analysis's state from the background feature's own switch (C2647).
"""
import threading

import pytest

from tests.test_heal_analysis import HA, T0, cant_fix, turn_on
from tests.test_heal_analysis import ai, lab, networks  # noqa: F401 (the fixtures)
from tests.test_heal_decide import DC, GOLDEN, Fake, changed, iso, settle
from tests.test_heal_diagnose import fleet
from tests.test_heal_triggers import _Lazy

AD, SL, P = _Lazy("auto_diagnose"), _Lazy("steplog"), _Lazy("propose")
ALERT_GI4 = {"kind": "alert", "key": "alert:gi4", "epoch": T0 - 900, "at": iso(T0 - 900),
             "rule": "Interface down", "interface": "GigabitEthernet4",
             "words": "Interface down · r3 GigabitEthernet4"}
#: A hypothesis as the adjacency runbook answers one: its claim holds the values it compared.
MTU = {"rule": "mtu", "layer": "link", "strength": "decisive", "incomplete": [], "agree": 2,
       "claim": "the MTU differs: r3 Gi4 1500 against r4 Gi4 9000",
       "evidence": [{"read": "read:rr-1:r3:show interfaces GigabitEthernet4",
                     "line": "MTU 1500 bytes", "intent": "mtu 1500"},
                    {"read": "read:rr-2:r4:show interfaces GigabitEthernet4",
                     "line": "MTU 9000 bytes", "intent": "mtu 1500"}],
       "rule_out": "the two ends printing one MTU", "todo": "Set one MTU at both ends"}
DOWN = {"rule": "down_admin_up", "layer": "physical", "strength": "decisive", "incomplete": [],
        "agree": 2, "claim": "r3 Gi4 is down while administratively up, and r4 Gi4 is up",
        "evidence": [{"read": "read:rr-1:r3:show interfaces GigabitEthernet4"}],
        "rule_out": "", "todo": "Check the link"}


def alert_incident(device="r3", trigger=None):
    """A real Alert incident: settled at its golden with *trigger* (an interface down), decided
    by the real decision: can't fix, Tier 3 (physical)."""
    settle(GOLDEN, how="at_golden", device=device, triggers=[trigger or ALERT_GI4],
           claim=False)
    (d,) = DC.run("Default", now=T0, sources=Fake(GOLDEN))["decided"]
    assert d["outcome"] == "cant_fix", d
    return d["incident"]


class Runbook:
    """`diagnose.run` at its seam: answers *hypotheses* and records the diagnosis as the real
    run does (`steplog.record_diagnosis`), each call kept; *release*, when given, is waited on
    first (a slow run)."""

    def __init__(self, hypotheses=(), release=None):
        self.hypotheses, self.release, self.calls = list(hypotheses), release, []

    def __call__(self, network, runbook, target, actor, *, incident=""):
        self.calls.append((runbook, target, actor, incident))
        if self.release is not None:
            assert self.release.wait(10), "the test released it"
        d = {"id": f"dg-{len(self.calls):016d}", "network": network, "runbook": runbook,
             "runbook_words": "adjacency down with both ends at intent", "target": target,
             "incident": incident, "actor": actor, "state": "done", "words": "",
             "steps": [], "hypotheses": [dict(h, id=f"diag:{n}")
                                         for n, h in enumerate(self.hypotheses, 1)],
             "more": 0, "ruled_out": [{"check": "both ends on one subnet (10.255.2.14/31)",
                                       "rule": "subnet"}],
             "not_checked": [], "commands": 16, "cap": 70, "runs": ["rr-1", "rr-2"],
             "stopped": "", "devices": ["r3", "r4"], "started_at": iso(T0),
             "finished_at": iso(T0 + 30)}
        SL.record_diagnosis(network, d)
        return d


@pytest.fixture
def heard(monkeypatch):
    """Every announcement made, by its announcer."""
    from modules import invalidation
    got = []
    monkeypatch.setattr(invalidation, "announce", lambda keys, by, ok=True: got.append(
        (tuple(keys), by)))
    return got


# ── Which incidents (N14) ──────────────────────────────────────────────────────────────────

class TestWhichIncidents:
    def test_an_alert_incident_is_tier_3_can_t_fix_and_a_never_one_is_not(self, lab):
        alert = alert_incident()
        assert AD.is_alert(SL.incident("Default", alert))
        # An account added outside intent: Tier 4 (a security ACL, this test's example until
        # C2839, is Tier 2 now).
        never = cant_fix(GOLDEN + "username audit privilege 15 secret 9 $9$abc\n")
        entry = SL.incident("Default", never)
        assert (entry["tier"], AD.is_alert(entry)) == (4, False)

    def test_a_proposal_is_diagnosed_once_in_its_own_thread(self, lab):
        settle(changed((" router-id 192.0.2.6\n", " router-id 192.0.2.99\n")), claim=False)
        (d,) = DC.run("Default", now=T0, sources=Fake(changed(
            (" router-id 192.0.2.6\n", " router-id 192.0.2.99\n"))))["decided"]
        assert d["outcome"] == "propose"
        started = []
        assert AD.proposals_step("Default", starter=lambda n, i, k: started.append((i, k))) \
            == [d["incident"]]
        assert started == [(d["incident"], AD.PROPOSE)]
        assert AD.claim("Default", d["incident"], AD.PROPOSE)
        assert AD.proposals_step("Default", starter=lambda *a: started.append(a)) == []
        assert len(started) == 1, "a proposal already taken is not diagnosed again"

    def test_the_runner_diagnoses_proposals_after_each_decision(self, monkeypatch):
        """One pass of the runner's loop: the decision, then the proposals' diagnoses, on each
        network it passes."""
        from modules.heal import act, decide, detect
        import modules.heal.auto_diagnose as real
        order = []
        monkeypatch.setattr(detect, "watching_networks", lambda: ["Default"])
        monkeypatch.setattr(detect, "run", lambda n: order.append(("detect", n)))
        monkeypatch.setattr(decide, "run", lambda n: order.append(("decide", n)))
        monkeypatch.setattr(real, "proposals_step", lambda n: order.append(("diagnose", n)))
        monkeypatch.setattr(act, "run", lambda n: order.append(("act", n)))
        monkeypatch.setattr(detect, "_notify_step", lambda: order.append(("notify", "")))

        def once(_s):
            detect._stop.set()
            return True
        monkeypatch.setattr(detect._wake, "wait", once)
        detect._stop.clear()
        try:
            detect._loop()
        finally:
            detect._stop.clear()
        assert [k for k, _n in order] == ["detect", "decide", "diagnose", "act", "notify"]


# ── The runbook and its target ─────────────────────────────────────────────────────────────

class TestTheTarget:
    def test_an_interface_alert_runs_adjacency_down_on_the_link_over_it(self):
        model, intents = fleet()
        got = AD.target_for("Default", {"device": "r3", "triggers": [ALERT_GI4]}, model=model,
                            intents=intents)
        assert got["runbook"] == "adjacency_down", got
        assert got["target"] == {"device": "r3", "neighbour": "r4", "interface": "Gi4"}

    def test_an_adjacency_down_runs_toward_its_other_end(self):
        model, intents = fleet()
        trig = {"kind": "adjacency", "related": ["r4"], "words": "OSPF r3 – r4 down"}
        got = AD.target_for("Default", {"device": "r3", "triggers": [trig]}, model=model,
                            intents=intents)
        assert (got["runbook"], got["target"]["neighbour"]) == ("adjacency_down", "r4"), got

    def test_a_named_interface_with_no_adjacency_is_not_swapped_for_another_link(self):
        model, intents = fleet()
        trig = dict(ALERT_GI4, interface="GigabitEthernet9")
        got = AD.target_for("Default", {"device": "r3", "triggers": [trig]}, model=model,
                            intents=intents)
        assert "runbook" not in got
        assert got["why"].startswith("what raised it names GigabitEthernet9, and intent holds "
                                     "no adjacency over it"), got
        assert "no other link is read in its place" in got["why"]

    def test_a_device_unreachable_runs_can_t_reach_from_its_neighbour(self):
        from modules.heal import diagnose_page as P
        from modules.heal import diagnose_reach as R
        from modules.neighbours import _all_lines
        model, intents = fleet()
        trig = {"kind": "alert", "rule": "Device unreachable (SNMP)", "words": "unreachable"}
        got = AD.target_for("Default", {"device": "r4", "triggers": [trig]}, model=model,
                            intents=intents)
        near = P.nearest(model, "r4")[0]
        _n, loop = R._loopback(_all_lines(intents)["r4"])
        assert got["runbook"] == "cant_reach" and loop, got
        assert got["target"] == {"device": near, "address": loop}

    def test_a_configuration_change_alone_fits_no_runbook(self):
        model, intents = fleet()
        trig = {"kind": "config_change", "words": "CONFIG_I"}
        got = AD.target_for("Default", {"device": "r3", "triggers": [trig]}, model=model,
                            intents=intents)
        assert got == {"why": ("no runbook fits what raised it (config_change): the runbooks "
                               "read an adjacency, an interface or a device not reached")}


# ── The run: once, bounded, recorded, announced ────────────────────────────────────────────

class TestTheRun:
    def test_it_runs_once_attached_to_its_incident_and_announces(self, lab, heard):
        inc = alert_incident()
        model, intents = fleet()
        fake = Runbook([MTU])
        got = AD.run("Default", inc, AD.ALERT, diagnose=fake, model=model, intents=intents)
        assert got["state"] == "done" and len(fake.calls) == 1
        runbook, target, actor, incident = fake.calls[0]
        assert (runbook, target["interface"], actor, incident) == (
            "adjacency_down", "Gi4", AD.ACTOR, inc)
        assert SL.incident("Default", inc)["diagnosis"]["id"] == got["id"]
        assert (("diagnosis", "drift"), "heal-diagnose") in heard
        again = AD.run("Default", inc, AD.ALERT, diagnose=fake, model=model, intents=intents)
        assert again == {"state": "taken", "incident": inc} and len(fake.calls) == 1

    def test_no_fitting_runbook_is_recorded_on_its_incident_with_why(self, lab, heard):
        inc = alert_incident(trigger=dict(ALERT_GI4, interface="GigabitEthernet9"))
        model, intents = fleet()
        fake = Runbook([MTU])
        got = AD.run("Default", inc, AD.ALERT, diagnose=fake, model=model, intents=intents)
        assert fake.calls == [] and got["state"] == "refused"
        kept = SL.incident("Default", inc)["diagnosis"]
        assert kept["words"].startswith("not diagnosed: what raised it names GigabitEthernet9")
        assert heard, "a diagnosis not made is announced too: its row says why"

    def test_three_at_once_then_the_fourth_is_said_busy(self, lab, heard):
        inc = alert_incident()
        model, intents = fleet()
        held = [AD.AutoSlots("Default") for _ in range(AD.MAX_AT_ONCE)]
        for s in held:
            s.__enter__()
        try:
            with pytest.raises(AD.AllBusy):
                AD.AutoSlots("Default").__enter__()
            fake = Runbook([MTU])
            got = AD.run("Default", inc, AD.ALERT, diagnose=fake, model=model,
                         intents=intents)
        finally:
            for s in held:
                s.__exit__(None, None, None)
        assert fake.calls == [] and got["state"] == "busy"
        assert got["words"].startswith("not diagnosed: 3 diagnoses already running on "
                                       "Default"), got["words"]
        assert SL.incident("Default", inc)["diagnosis"]["state"] == "busy"
        with AD.AutoSlots("Default"):
            pass                              # released, the slots are free again


# ── By kind off the host (section 10, N23) ─────────────────────────────────────────────────

class TestByKind:
    def test_a_hypothesis_is_said_by_its_rule_its_ends_and_strength_never_its_values(self):
        said = AD.said(MTU)
        assert said == "The MTU differs between the ends: r3 Gi4, r4 Gi4 (decisive)"
        assert "1500" not in said and "9000" not in said

    def test_the_summary_says_reads_and_ruled_out_by_rule(self):
        s = AD.summary({"state": "done", "devices": ["r3", "r4"], "commands": 16,
                        "hypotheses": [MTU, DOWN],
                        "ruled_out": [{"check": "on 10.255.2.14/31", "rule": "subnet"}]})
        assert s["reads"] == "read-only; 16 reads on r3 and r4"
        assert [h["claim"] for h in s["hypotheses"]][1] == (
            "An interface down while administratively up, the far end up: r3 Gi4 (decisive)")
        assert s["ruled_out"] == ["an address not intent's, or the ends on different subnets"]
        assert "10.255" not in repr(s)

    def test_the_pack_section_cites_each_hypothesis_as_diag_n_by_kind(self):
        from modules import evidence_pack as EP
        entry = {"diagnosis": {"state": "done", "devices": ["r3", "r4"], "commands": 16,
                               "hypotheses": [MTU],
                               "ruled_out": [{"check": "x", "rule": "subnet"}]}}
        s = EP.diagnosis_section(entry, T0)
        assert s["name"] == "diagnosis" and s["state"] == "ok"
        assert [p["ref"] for p in s["pieces"]] == ["diag:1", "diag:ruled-out:1"]
        assert EP.resolve({"sections": [s]}, "diag:1")["strength"] == "decisive"
        assert "9000" not in repr(s) and "not sent" in s["values"]
        none = EP.diagnosis_section({}, T0)
        assert none["state"] == "absent" and "no diagnosis ran" in none["why"]

    def test_an_alert_incident_s_analysis_is_asked_with_its_diagnosis(self, ai, heard):
        inc = alert_incident()
        Runbook([MTU])("Default", "adjacency_down", {}, AD.ACTOR, incident=inc)
        prep = HA.prepare("Default", inc, now=T0 + 1)
        (sent,) = [s for s in prep["sections"] if s["name"] == "diagnosis"]
        assert [p["ref"] for p in sent["pieces"]] == ["diag:1", "diag:ruled-out:1"]
        assert "9000" not in prep["data"]["pack"]
        assert '"diag:1"' in prep["data"]["pack"]

    def test_the_analysis_names_the_section_in_its_pack_format(self):
        assert "diagnosis" in HA.SECTIONS
        assert "diagnosis = Mercury's diagnosis" in HA.vocabulary()
        assert "diag:<n>" in HA.tried_format()


# ── The notice waits for it ────────────────────────────────────────────────────────────────

def told(record):
    def deliver(network, event):
        record.append(event)
        return {"ok": True, "sent": 1, "failed": 0, "error": ""}
    return deliver


class TestTheNotice:
    def test_back_in_time_the_message_carries_it_after_what_was_detected(self, ai, heard,
                                                                         monkeypatch):
        from modules import heal_notice as N
        from modules.notify import message
        import modules.heal.auto_diagnose as real
        monkeypatch.setattr(real, "target_for", lambda network, incident, **kw: {
            "runbook": "adjacency_down",
            "target": {"device": "r3", "neighbour": "r4", "interface": "Gi4"}})
        inc = alert_incident()
        events = []
        got = N.notice("Default", inc, deliver=told(events), wait_s=5, now=T0 + 1,
                       diagnose=Runbook([MTU]), diagnosis_wait_s=5)
        (ev,) = events
        assert got["follow_up"] is None and got["diagnosis"]["state"] == "done"
        assert ev["diagnosis"]["hypotheses"][0]["claim"] == (
            "The MTU differs between the ends: r3 Gi4, r4 Gi4 (decisive)")
        text = message.text(message.check_event(ev))
        assert (text.index("Detected:") < text.index("Mercury's diagnosis (read-only; 16 "
                                                     "reads on r3 and r4)")
                < text.index("What Mercury tried:"))
        assert "9000" not in text
        assert message.payload(message.check_event(ev))["diagnosis"]["reads"]

    def test_the_action_is_considered_after_the_diagnosis_and_before_the_notice(
            self, ai, heard, monkeypatch):
        """19.3 (H20): "then item 2's actions are considered (19.4), and then the notice is
        sent"; an action that raises never stops the notice."""
        from modules import heal_notice as N
        import modules.heal.auto_diagnose as real
        monkeypatch.setattr(real, "target_for", lambda network, incident, **kw: {
            "runbook": "adjacency_down",
            "target": {"device": "r3", "neighbour": "r4", "interface": "Gi4"}})
        inc = alert_incident()
        order, events = [], []

        def consider(network, incident_id, diagnosis):
            order.append(("considered", incident_id, diagnosis["hypotheses"][0]["rule"],
                          len(events)))
            raise RuntimeError("the bounce's store is unreadable")

        got = N.notice("Default", inc, deliver=told(events), wait_s=5, now=T0 + 1,
                       diagnose=Runbook([DOWN]), diagnosis_wait_s=5, consider=consider)
        assert order == [("considered", inc, "down_admin_up", 0)], "before the notice"
        assert len(events) == 1 and got["first"], "the notice still went"

    def test_not_back_it_says_so_and_the_follow_up_carries_it(self, ai, heard, monkeypatch):
        from modules import heal_notice as N
        import modules.heal.auto_diagnose as real
        monkeypatch.setattr(real, "target_for", lambda network, incident, **kw: {
            "runbook": "adjacency_down",
            "target": {"device": "r3", "neighbour": "r4", "interface": "Gi4"}})
        inc = alert_incident()
        release, events = threading.Event(), []

        def deliver(network, event):
            events.append(event)
            release.set()                  # the first message is out: the diagnosis may end
            return {"ok": True, "sent": 1, "failed": 0, "error": ""}
        got = N.notice("Default", inc, deliver=deliver, wait_s=5, follow_s=10, now=T0 + 1,
                       diagnose=Runbook([DOWN], release=release), diagnosis_wait_s=0.1)
        first, follow = events
        assert first["diagnosis"]["words"] == ("not finished within 0 s; its result follows "
                                               "on this thread")
        assert first["analysis"]["words"] == "AI analysis: not run, off for this network"
        assert follow["event"] == "diagnosis" and follow["incident"] == inc
        assert follow["diagnosis"]["hypotheses"][0]["strength"] == "decisive"
        assert got["follow_up"]["ok"]

    def test_a_diagnosis_block_carries_only_its_fields(self):
        """The egress's closed set (section 10): a block or a hypothesis with another field (an
        evidence line, a compared value) is refused by name; each line one line, bounded."""
        from modules.notify import message
        ev = {"incident": "hi-1", "event": "cant_fix", "steps": [],
              "diagnosis": {"state": "done", "words": "1 hypothesis", "reads": "16 reads",
                            "hypotheses": [{"claim": "x\ny", "strength": "decisive"}],
                            "ruled_out": ["a"]}}
        got = message.check_event(ev)["diagnosis"]
        assert got["hypotheses"] == [{"claim": "x y", "strength": "decisive"}]
        for bad in ({"evidence": ["MTU 9000"]}, {"hypotheses": [{"claim": "x",
                                                                  "line": "MTU 9000"}]}):
            with pytest.raises(ValueError, match="carries only"):
                message.check_event(dict(ev, diagnosis=dict(ev["diagnosis"], **bad)))

    def test_a_never_incident_is_told_with_no_diagnosis(self, ai):
        from modules import heal_notice as N
        inc = cant_fix()
        fake, events = Runbook([MTU]), []
        N.notice("Default", inc, deliver=told(events), wait_s=5, now=T0 + 1, diagnose=fake)
        (ev,) = events
        assert fake.calls == [] and "diagnosis" not in ev


# ── The screens ────────────────────────────────────────────────────────────────────────────

class TestTheScreens:
    def test_the_can_t_fix_row_carries_its_diagnosis(self, lab, heard):
        from modules import attention
        inc = alert_incident()
        model, intents = fleet()
        AD.run("Default", inc, AD.ALERT, diagnose=Runbook([DOWN]), model=model,
               intents=intents)
        (r,) = [r for r in attention._heal_cant_fix_rows("Default", [], T0 + 60, [])
                if r["operands"]["incident"] == inc]
        hd = r["heal_diagnosis"]
        assert hd["state"] == "done" and hd["auto"] and hd["device"] == "r3"
        assert hd["result"]["hypotheses"][0]["claim"].startswith("r3 Gi4 is down")

    def test_a_never_row_says_it_is_not_diagnosed_by_itself(self, lab):
        from modules import attention
        inc = cant_fix()
        (r,) = [r for r in attention._heal_cant_fix_rows("Default", [], T0 + 60, [])
                if r["operands"]["incident"] == inc]
        assert (r["heal_diagnosis"]["state"], r["heal_diagnosis"]["auto"]) == ("none", False)

    def test_a_physical_first_hypothesis_is_said_unchanged_by_the_fix(self):
        d = {"hypotheses": [DOWN]}
        assert AD.addresses(d).startswith("the diagnosis's first hypothesis is that r3 Gi4 is "
                                          "down while administratively up")
        assert "which this fix does not change" in AD.addresses(d)
        assert AD.addresses({"hypotheses": [MTU]}) == "", \
            "Mercury does not judge that a fix addresses a configuration cause"

    def test_the_proposal_card_carries_its_diagnosis(self, lab, heard):
        from tests.test_heal_propose import R8, FakeApproved, proposed
        d = proposed()
        before = P.view("Default", d["id"], now=T0 + 1, sources=FakeApproved(R8))
        assert before["diagnosis"]["state"] == "none"
        Runbook([DOWN])("Default", "adjacency_down", {}, AD.ACTOR, incident=d["incident"])
        v = P.view("Default", d["id"], now=T0 + 1, sources=FakeApproved(R8))
        assert v["diagnosis"]["state"] == "done"
        assert "which this fix does not change" in v["diagnosis"]["addresses"]

    def test_the_tab_says_the_analysis_from_its_switch_c2647(self, ai):
        from modules import heal_page
        off = heal_page._analysis("Default")
        assert (off["state"], off["badge"]) == ("off", "off for Default")
        assert "not built" not in off["words"]
        turn_on()
        on = heal_page._analysis("Default")
        assert (on["state"], on["level"]) == ("on", "ok"), on
        assert "turned on by admin@example.com" in on["words"]
        assert "$0.50 a day, $10.00 a month" in on["words"]
        assert heal_page._analysis("Branch")["state"] == "off", "on for Default only"
