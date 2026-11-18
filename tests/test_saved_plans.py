"""Saved command plans and the approval rights (Gate 1b; the operator, 2026-11-15: "clumsy
processes become tools"; C3696, C3757, C3763; modules/nsot/saved_plans.py).

- **A self-heal script** (C3696): a verified command-plan run saved with its parameters open,
  the problem's R4 match (`problem.MATCH_FIELDS` only: a field outside it is refused) and how
  each parameter is filled from the classified problem; Dry run first (it records what it would
  run and sends nothing), promoted by a person with self-healing rights, then run through the
  same runner on the promotion's authority, with no AI call.
- **A reusable action**: a verified run saved by an admin as a named entry, listed by the
  catalog as a `PlanStep` (so a plan step and an entry a proposal may name).
- **A provisional shape**: approved by an admin only (`command_policy.approve_as`), its
  proposal and its first run's measurement listed for the admin's screen.
- **The rights**, through the one chokepoint (`identity.right_refusal`): running a plan any
  verified person's; saving or promoting a script the self-healing right's; saving an action
  or approving a shape the admin's; the AI holds none.

The run records are the runner's own shape (`command_plan_run.run`'s record, kind
``command_plan``), written through the operations' own record writer (`privileged.record`), the
one edit said: its state. The built-in plan is the one that ships (errdisable-recover).
"""
import os

import pytest

from modules import identity
from modules import plan_engine as E
from modules import problem as P
from modules.nsot import command_plan as CP
from modules.nsot import command_policy as POL
from modules.nsot import saved_plans as S

NET = "Lab"
PERSON = "person@example.invalid"
OTHER = "other@example.invalid"
WHO = dict(actor=PERSON, actor_verified="access", person=True)
MATCH = {"condition": "err_disabled", "cause": "BPDU guard", "port_role": "access"}
#: The problem says its cause in words (`errdisable.CAUSES`); the plan takes its choice word: the
#: map names each (the operator, 2026-11-15: "refusing an unmapped cause by name").
FILLS = {"device": "device", "interface": "object",
         "cause": {"BPDU guard": "bpduguard", "port security": "psecure-violation"}}
BPDU = P.Problem(device="s1", object="Gi0/2", condition="err_disabled", cause="BPDU guard",
                 port_role="access", cause_cleared="no_bpdu_since", cleared="true")


@pytest.fixture
def store(tmp_path, monkeypatch):
    """The installation's data folder and Lab's, each the test's own; access rights unset (every
    verified person holds each, the behaviour before rights existed) unless a test sets them."""
    from modules.nsot import privileged

    lab = tmp_path / "lists" / "lab"
    lab.mkdir(parents=True)
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(lab))
    monkeypatch.setattr("modules.config.list_data_path", lambda name: str(lab))
    rights = {}
    monkeypatch.setattr(identity, "_setting", lambda key, default=None: (
        rights if key == "access_rights" else default))
    S._CACHE.update(mtime=None, templates={})
    S._READ.clear()

    def run(state="done", kind="command_plan", key="errdisable-recover"):
        from modules.nsot import reads
        rec = {"id": reads.new_id(), "list": NET, "device": "s1", "key": key, "kind": kind,
               "state": state, "outcome": "done" if state == "done" else "rolled_back",
               "actor": PERSON, "at": "2026-11-15T10:00:00Z"}
        privileged.record(NET, rec)
        return rec["id"]
    yield {"run": run, "rights": rights}
    # What a test saved leaves no step kind or catalog entry behind it.
    if os.path.exists(S._path()):
        os.remove(S._path())
    E.refresh_saved_kinds()


def script(store, **over):
    """The card's Save of a verified run with its match. Saving a verified fix is the approval
    (6b91dc45, the operator, 2026-11-15): saved in Auto, promoted by the person saving it;
    ``dry_run=True`` is Customize's Dry run, kept until promoted (what a test that promotes
    saves first)."""
    kw = dict(run_id=store["run"](), name="BPDU guard recovery", match=MATCH, fills=FILLS,
              **WHO)
    kw.update(over)
    return S.save_script(NET, **kw)


# ── A self-heal script ──────────────────────────────────────────────────────────────────────

class TestTheMatch:
    def test_a_field_outside_the_schema_is_refused(self):
        why = S.match_refusal(dict(MATCH, alert_name="Critical syslog received"))
        assert "it names alert_name" in why and "never matches an alert's name" in why
        assert "raw_line" in S.match_refusal({"condition": "err_disabled", "raw_line": "x"})
        assert S.match_refusal(MATCH) == ""
        assert "is none" in S.match_refusal({"condition": "no_such_condition"})
        assert S.match_refusal({"condition": "err_disabled", "cleared": "maybe"})

    def test_another_cause_or_an_unclassified_one_does_not_match(self):
        assert S.matches(MATCH, BPDU)
        assert not S.matches(MATCH, P.Problem(**dict(BPDU.as_dict(),
                                                     cause="port security")))
        assert not S.matches(MATCH, P.Problem(device="s1", object="an alert",
                                              condition="alert_unclassified"))
        assert not S.matches({}, BPDU)


class TestSavingAScript:
    def test_a_verified_run_is_saved_with_its_parameters_open_in_dry_run(self, store):
        """Saved with Customize's Dry run it stays in Dry run (a saved fix is one object keyed
        ``fix-``, 3a659d6b); a plain Save is the approval, Auto promoted by its saver
        (6b91dc45)."""
        e = script(store, dry_run=True)
        assert e["key"] == "fix-bpdu-guard-recovery" and e["mode"] == "dry_run"
        assert "promoted_by" not in S.scripts(NET)[e["key"]]
        saved = script(store, name="BPDU guard recovery saved")
        assert saved["mode"] == "auto"
        assert S.scripts(NET)[saved["key"]]["promoted_by"] == PERSON
        t = CP.template_of(e["key"])
        assert t.title == "BPDU guard recovery" and set(t.parameters) == set(FILLS)
        assert t.commands == CP.template_of("errdisable-recover").commands
        assert S.scripts(NET)[e["key"]]["match"] == MATCH

    @pytest.mark.parametrize("dry_run", [False, True])
    def test_a_plan_changed_since_its_verified_run_is_not_saved(self, store, monkeypatch,
                                                                dry_run):
        """The correctness review's G3-H2 (2026-11-18): Save stored the run's plan as it is NOW
        (`_template_doc`, the current template for the run's key), so a plan changed between
        the verified run and the Save (an edited fix's new version, a built-in plan a deploy
        changed) was stored as the verified fix, Automatic at once: lines no run verified,
        firing by themselves. The run's record names the template it ran by its digest; a Save
        whose plan's digest differs is refused naming both, nothing stored."""
        from modules.nsot import privileged

        ran = CP.template_of("errdisable-recover")
        run_id = store["run"]()
        rec = privileged.get(NET, run_id)
        privileged.record(NET, dict(rec, template_digest=ran.digest))
        changed = CP.parse(dict(ran.doc, title="Recover an err-disabled port, changed since"))
        assert changed.digest != ran.digest
        real = CP.template_of
        monkeypatch.setattr(CP, "template_of", lambda key: (
            changed if key == "errdisable-recover" else real(key)))
        with pytest.raises(S.Refused) as exc:
            script(store, run_id=run_id, dry_run=dry_run)
        assert ran.digest in str(exc.value) and changed.digest in str(exc.value), exc.value
        assert S.scripts(NET) == {}, "nothing is stored"

    @pytest.mark.parametrize("state, kind, words", [
        ("failed", "command_plan", "did not send its program and pass its own verify"),
        ("done", "privileged", "is no command plan's run"),
    ])
    def test_only_a_verified_fix_is_saved(self, store, state, kind, words):
        with pytest.raises(S.Refused) as exc:
            script(store, run_id=store["run"](state=state, kind=kind))
        assert words in str(exc.value)

    def test_every_parameter_is_filled_from_the_problems_fields(self, store):
        with pytest.raises(S.Refused) as exc:
            script(store, fills=dict(FILLS, interface="alert_name"))
        assert "and interface's 'alert_name' is not one" in str(exc.value)
        with pytest.raises(S.Refused):
            script(store, fills={"device": "device"})

    def test_its_match_is_previewed_on_the_open_incidents(self, store, monkeypatch):
        monkeypatch.setattr(S, "_incidents_problems", lambda network: [
            ("hi-aaaaaa", BPDU), ("hi-bbbbbb", P.Problem(**dict(BPDU.as_dict(),
                                                                 cause="port security")))])
        got = S.match_preview(NET, MATCH)
        assert got["ok"] and got["read"] == 2
        assert [m["incident"] for m in got["matched"]] == ["hi-aaaaaa"]
        assert not S.match_preview(NET, dict(MATCH, alert="x"))["ok"]


class TestFiring:
    def _seams(self, monkeypatch):
        seen = {"preview": [], "run": [], "hold": None, "held": [], "outcome": "done",
                "during": None}

        def preview(network, key, values, **kw):
            seen["preview"].append((key, dict(values)))
            return {"ok": True, "hash": "h1", "values": dict(values), "refusals": []}

        def run(network, key, values, **kw):
            seen["run"].append((key, dict(values), kw))
            if seen["during"]:
                seen["during"]()
            o = seen["outcome"]
            # The runner's record shape: a command plan's (`saved_plans.run_verified` reads
            # its kind, state and outcome since 49e955d5's verified close).
            return {"id": f"r{len(seen['run'])}", "kind": "command_plan",
                    "state": "done" if o == "done" else o, "outcome": o,
                    "why": f"the run {o}"}

        def hold(network, record, **kw):
            seen["held"].append(dict(record))
            return seen["hold"]
        monkeypatch.setattr(CP, "preview", preview)
        monkeypatch.setattr("modules.nsot.command_plan_run.run", run)
        monkeypatch.setattr("modules.heal.decide.script_hold", hold)
        # Self-healing's mode on the network: Auto, unless a test says otherwise.
        seen["heal"] = "auto"
        monkeypatch.setattr(S, "heal_mode", lambda network: seen["heal"])
        return seen

    def test_in_dry_run_it_records_what_it_would_run_and_sends_nothing(self, store,
                                                                         monkeypatch):
        e = script(store, dry_run=True)
        seen = self._seams(monkeypatch)
        got = S.fire(NET, e["key"], BPDU, "hi-aaaaaa")
        assert got["mode"] == "dry_run" and got["words"] == "would run" and not seen["run"]
        assert seen["preview"] == [(e["key"], {"device": "s1", "interface": "Gi0/2",
                                               "cause": "bpduguard"})]
        track = S.scripts(NET)[e["key"]]["track"]
        assert len(track) == 1 and track[0]["incident"] == "hi-aaaaaa"

    def test_promoted_it_runs_through_the_runner_on_its_authority(self, store, monkeypatch):
        e = script(store, dry_run=True)
        S.promote(e["key"], **WHO)
        seen = self._seams(monkeypatch)
        got = S.fire(NET, e["key"], BPDU, "hi-aaaaaa")
        assert got["mode"] == "auto" and got["ok"] and got["run"] == "r1"
        (key, values, kw) = seen["run"][0]
        assert kw["authority"] == {"script": e["key"]} and kw["confirmed"] == "h1"
        assert kw["person"] is False and kw["actor"] == PERSON

    def test_the_runner_refuses_an_authority_that_does_not_stand(self, store):
        from modules.nsot import command_plan_run as CR
        e = script(store, dry_run=True)
        rec = CR.run(NET, e["key"], {"device": "s1"}, actor=PERSON, actor_verified="",
                     person=False, confirmed="h", authority={"script": e["key"]})
        assert rec["outcome"] == "refused" and "is not a saved script in Auto" in rec["why"]
        assert S.authority_refusal(e["key"], {"script": "other"}, NET)
        S.promote(e["key"], **WHO)
        assert S.authority_refusal(e["key"], {"script": e["key"]}, NET) == ""
        with identity.as_ai("fixit-troubleshoot"):
            assert "may not run a saved script" in S.authority_refusal(
                e["key"], {"script": e["key"]}, NET)

    @pytest.mark.parametrize("meanwhile", ["nothing", "a person's planned window",
                                           "the fix deleted", "self-healing turned off"])
    def test_a_run_that_waited_for_its_device_judges_its_stops_and_authority_again(
            self, store, monkeypatch, meanwhile):
        """The correctness review's G2-H1 (2026-11-18; 70e89a47): an Automatic fix waits for
        another operation's hold on its device (one operation per device is a wait), and its
        approval and the heal's stops were judged only before the wait, Stop and Off asked only
        while the device was busy. A person's Reload (its window declared, the device held), a
        Delete… of the fix or an Off while it waited, and the run then held the device and
        sent: a write no person approved. Judged again once the device is free, as the heal's
        act judges again after its own wait; with nothing changed, it goes on to hold and
        send."""
        import contextlib
        import time as _time

        from modules import restarts
        from modules.nsot import command_plan_run as CR

        e = script(store, dry_run=True)
        S.promote(e["key"], **WHO)
        mode = {"mode": "auto", "set": "auto", "words": "Auto"}
        monkeypatch.setattr("modules.heal.policy.current", lambda network, now=None: dict(mode))
        monkeypatch.setattr(CP, "preview", lambda network, key, values, **kw: {
            "ok": True, "hash": "h", "values": dict(values), "refusals": [],
            "program": ["interface GigabitEthernet0/2"], "title": "Recover s1 Gi0/2",
            "device_row": {"hostname": "s1", "ip": "192.0.2.21"}, "derived": {}})
        busy = [{"operation": "reload", "actor": PERSON}]
        monkeypatch.setattr("modules.nsot.device_ops.holder",
                            lambda network, device: busy.pop() if busy else None)

        def meanwhile_happens(_s):
            now = _time.time()
            if meanwhile == "a person's planned window":
                restarts.record_planned(["s1"], now, now + 600, PERSON, "maintenance", "api",
                                        list_name=NET)
            elif meanwhile == "the fix deleted":
                S.retire(e["key"], network=NET, reason="taken back by its author", **WHO)
            elif meanwhile == "self-healing turned off":
                mode.update(mode="off", set="off", words="self-healing is off")
        monkeypatch.setattr(CR.time, "sleep", meanwhile_happens)
        held = []

        @contextlib.contextmanager
        def hold(network, device, *a, **kw):
            held.append(device)
            raise RuntimeError("reached the send")
            yield
        monkeypatch.setattr("modules.nsot.device_ops.hold", hold)
        rec = CR.run(NET, e["key"], {"device": "s1", "interface": "Gi0/2",
                                     "cause": "bpduguard"}, actor=PERSON, actor_verified="",
                     person=False, confirmed="h", authority={"script": e["key"]})
        if meanwhile == "nothing":
            assert held == ["s1"], (rec["outcome"], rec.get("why"))
            return
        assert held == [], "nothing is held or sent"
        assert rec["outcome"] == "refused" and "Nothing was sent" in rec["why"], rec["why"]
        assert {"a person's planned window": "as planned", "the fix deleted": "deleted",
                "self-healing turned off": "off"}[meanwhile] in rec["why"], rec["why"]

    def test_a_scripts_authority_does_not_stand_on_another_network(self, store):
        """Review 4: the run's network is checked against the script's."""
        e = script(store, dry_run=True)
        S.promote(e["key"], **WHO)
        why = S.authority_refusal(e["key"], {"script": e["key"]}, "Other")
        assert why == f"{e['key']} is a self-heal script of {NET}, and this run is on Other"

    def test_a_promoter_who_no_longer_holds_the_right_stands_for_nothing(self, store):
        """The check this test was named for is gone (70e89a47, the operator, 2026-11-17,
        round 2: "the promoter-still-holds-the-right check" removed, so an approved fix runs
        the moment self-healing is On): a promotion stands once made, whoever holds the right
        later; promoting again still asks the right, and the AI still stands for nothing."""
        e = script(store, dry_run=True)
        S.promote(e["key"], **WHO)
        store["rights"]["self_healing"] = [OTHER]
        assert S.authority_refusal(e["key"], {"script": e["key"]}, NET) == ""
        assert S.scripts(NET)[e["key"]]["promoted_by"] == PERSON
        with pytest.raises(S.Refused) as exc:
            script(store, name="BPDU guard recovery again")
        assert "does not hold the self-healing right" in str(exc.value)
        with identity.as_ai("fixit-troubleshoot"):
            assert "may not run a saved script" in S.authority_refusal(
                e["key"], {"script": e["key"]}, NET)

    def test_a_matching_incident_fires_it_with_no_ai_call(self, store, monkeypatch):
        e = script(store)
        seen = self._seams(monkeypatch)
        monkeypatch.setattr(P, "classify", lambda found: BPDU)
        monkeypatch.setattr("modules.ai.gateway.ask", lambda *a, **kw: pytest.fail("AI"))
        got = S.fire_matching(NET, {"incident": {"id": "hi-aaaaaa"}})
        assert [g["key"] for g in got] == [e["key"]] and seen["preview"]
        monkeypatch.setattr(P, "classify", lambda found: P.Problem(**dict(
            BPDU.as_dict(), cause="port security")))
        assert S.fire_matching(NET, {"incident": {"id": "hi-bbbbbb"}}) == []

    def test_healed_by_a_promoted_script_the_ai_is_not_asked(self, store, monkeypatch):
        """The investigation's one path (`heal_notice._investigation`, the automatic start's
        and the catch-up's): a promoted script whose match holds runs first, and healed so,
        the AI is not asked; in Dry run it records what it would run and the AI is asked."""
        from modules import heal_notice
        e = script(store, dry_run=True)
        self._seams(monkeypatch)
        monkeypatch.setattr(P, "classify", lambda found: BPDU)
        monkeypatch.setattr("modules.incident_page.resolve", lambda network, iid: {
            "found": "page", "incident": {"id": iid}})
        monkeypatch.setattr("modules.fixit.section.incident_of", lambda network, found: {
            "incident": object(), "why": ""})
        asked = []

        def ask(found, inc):
            asked.append(found)
            return {"state": "answered"}
        got = heal_notice._investigation(NET, "hi-aaaaaa", "k1", ask, deliver=None,
                                         trigger="auto")
        assert asked and got == {"state": "answered"}, "in Dry run the AI is still asked"
        S.promote(e["key"], **WHO)
        asked.clear()
        got = heal_notice._investigation(NET, "hi-aaaaaa", "k1", ask, deliver=None,
                                         trigger="auto")
        assert not asked and got["state"] == "healed_by_script"
        assert got["words"] == f"Healed by saved script {e['key']}: no AI used"

    def test_a_device_a_heal_guard_holds_fires_nothing_and_says_which(self, store,
                                                                    monkeypatch):
        """Review 1: the heal guards for the script's device asked before an Auto send, on
        the incident's own record; held, nothing is sent and the row names the guard."""
        from modules.heal import guards
        e = script(store, dry_run=True)
        S.promote(e["key"], **WHO)
        seen = self._seams(monkeypatch)
        seen["hold"] = guards.hit(7, "held", "a person changed s1 3 times in 10 minutes", {})
        rec = {"id": "hi-aaaaaa", "device": "s1", "changes": []}
        got = S.fire(NET, e["key"], BPDU, "hi-aaaaaa", record=rec)
        assert not seen["run"] and seen["held"] == [rec]
        assert not got["ok"] and not got["sent"]
        assert got["words"].startswith("held by guard 7 (") and "nothing was sent" in got["words"]
        (row,) = S.scripts(NET)[e["key"]]["track"]
        assert row["words"] == got["words"] and row["state"] == "done" and not row["sent"]
        seen["hold"] = None
        assert S.fire(NET, e["key"], BPDU, "hi-aaaaaa", record=rec)["sent"], (
            "a held fire sent nothing, so it stands for nothing: the next pass runs it")

    def test_in_dry_run_no_guard_is_asked_and_nothing_is_sent(self, store, monkeypatch):
        e = script(store, dry_run=True)
        seen = self._seams(monkeypatch)
        S.fire(NET, e["key"], BPDU, "hi-aaaaaa", record={"id": "hi-aaaaaa", "device": "s1"})
        assert not seen["held"] and not seen["run"]

    def test_of_two_promoted_scripts_on_one_incident_only_one_sends(self, store,
                                                                   monkeypatch):
        """Review 2: once one Auto script has sent anything, the others only record a Dry
        run: one incident, one change."""
        first = script(store, dry_run=True)
        second = script(store, name="BPDU guard recovery again", dry_run=True)
        for e in (first, second):
            S.promote(e["key"], **WHO)
        seen = self._seams(monkeypatch)
        monkeypatch.setattr(P, "classify", lambda found: BPDU)
        got = S.fire_matching(NET, {"incident": {"id": "hi-aaaaaa", "device": "s1"}})
        assert len(seen["run"]) == 1
        assert [(g["key"], g["mode"], g["sent"]) for g in got] == [
            (first["key"], "auto", True), (second["key"], "dry_run", False)]
        assert S.scripts(NET)[second["key"]]["track"][-1]["mode"] == "dry_run"

    @pytest.mark.parametrize("outcome", ["rolled_back", "failed"])
    def test_an_auto_run_that_sent_and_did_not_pass_is_never_retried(self, store,
                                                                     monkeypatch, outcome):
        """Review 3: any Auto attempt that sent something counts as fired, so a rolled-back
        run is not tried again on every pass; a refusal at the runner sent nothing."""
        e = script(store, dry_run=True)
        S.promote(e["key"], **WHO)
        seen = self._seams(monkeypatch)
        seen["outcome"] = outcome
        first = S.fire(NET, e["key"], BPDU, "hi-aaaaaa")
        assert first["sent"] and not first["ok"]
        again = S.fire(NET, e["key"], BPDU, "hi-aaaaaa")
        assert again["already"] and len(seen["run"]) == 1

    def test_a_run_the_runner_refused_sent_nothing_and_is_tried_again(self, store,
                                                                     monkeypatch):
        e = script(store, dry_run=True)
        S.promote(e["key"], **WHO)
        seen = self._seams(monkeypatch)
        seen["outcome"] = "refused"
        assert not S.fire(NET, e["key"], BPDU, "hi-aaaaaa")["sent"]
        seen["outcome"] = "done"
        assert S.fire(NET, e["key"], BPDU, "hi-aaaaaa")["sent"] and len(seen["run"]) == 2

    def test_a_fire_in_flight_is_claimed_and_a_second_path_runs_nothing(self, store,
                                                                         monkeypatch):
        """Review 3: the claim is written under the store's lock before the run, so a second
        path asking while the first runs finds it firing and sends nothing; the investigation
        does not ask the AI then."""
        from modules import heal_notice
        e = script(store, dry_run=True)
        S.promote(e["key"], **WHO)
        seen = self._seams(monkeypatch)
        monkeypatch.setattr(P, "classify", lambda found: BPDU)
        monkeypatch.setattr("modules.incident_page.resolve", lambda network, iid: {
            "found": "page", "incident": {"id": iid, "device": "s1"}})
        monkeypatch.setattr("modules.fixit.section.incident_of", lambda network, found: {
            "incident": object(), "why": ""})
        during = {}

        def second_path():
            during["fire"] = S.fire(NET, e["key"], BPDU, "hi-aaaaaa")
            during["inv"] = heal_notice._investigation(
                NET, "hi-aaaaaa", "k1", lambda *a: pytest.fail("the AI was asked"),
                deliver=None, trigger="auto")
        seen["during"] = second_path
        S.fire(NET, e["key"], BPDU, "hi-aaaaaa")
        assert len(seen["run"]) == 1
        assert during["fire"]["already"] and during["fire"]["state"] == "firing"
        assert during["inv"]["state"] == "script_running"

    def test_the_runner_records_a_scripts_run_as_its_authority_not_a_person(self, store,
                                                                           monkeypatch):
        """Review 8: a run under a script's authority is Mercury's, by the script, promoted
        by its promoter, never recorded as the person."""
        from modules.nsot import command_plan_run as CR
        e = script(store, dry_run=True)
        S.promote(e["key"], **WHO)
        monkeypatch.setattr(S, "authority_refusal", lambda *a, **kw: "stop here")
        rec = CR.run(NET, e["key"], {"device": "s1"}, actor=PERSON, actor_verified="",
                     person=False, confirmed="h", authority={"script": e["key"]})
        assert rec["actor_kind"] == "authority" and rec["actor"] != PERSON
        assert e["key"] in rec["actor"] and PERSON in rec["actor"]
        assert rec["authority"]["promoted_by"] == PERSON


class TestTheFills:
    def test_a_cause_maps_to_the_plans_choice_word(self, store):
        e = script(store)
        assert S.fill(e, BPDU) == {"device": "s1", "interface": "Gi0/2", "cause": "bpduguard"}

    def test_an_unmapped_cause_is_refused_by_name(self, store):
        e = script(store)
        with pytest.raises(S.Refused) as exc:
            S.fill(e, P.Problem(**dict(BPDU.as_dict(), cause="a loop")))
        assert "cause: the problem's cause is 'a loop', which this script's map does not " \
               "name ('BPDU guard', 'port security')" in str(exc.value)

    def test_a_choice_parameter_without_a_map_is_refused(self, store):
        with pytest.raises(S.Refused) as exc:
            script(store, fills=dict(FILLS, cause="cause"))
        assert "cause is one of bpduguard, psecure-violation: it is filled through a map" \
               in str(exc.value)
        with pytest.raises(S.Refused):
            script(store, fills=dict(FILLS, cause={"BPDU guard": "not-a-choice"}))

    def test_an_unmapped_cause_fires_as_refused_and_runs_nothing(self, store, monkeypatch):
        e = script(store, dry_run=True)
        S.promote(e["key"], **WHO)
        seen = TestFiring()._seams(monkeypatch)
        got = S.fire(NET, e["key"], P.Problem(**dict(BPDU.as_dict(), cause="a loop")),
                     "hi-aaaaaa")
        assert not got["ok"] and got["words"].startswith("refused: cause:")
        assert not seen["preview"] and not seen["run"]


class TestUnderSelfHealingsMode:
    @pytest.mark.parametrize("script_mode, heal, now", [
        ("dry_run", "off", "off"), ("dry_run", "dry_run", "dry_run"),
        ("dry_run", "auto", "dry_run"), ("auto", "off", "off"),
        ("auto", "dry_run", "dry_run"), ("auto", "auto", "auto"), ("auto", "?", "off")])
    def test_a_script_does_what_self_healing_allows(self, script_mode, heal, now):
        assert S.mode_now({"mode": script_mode}, heal) == now

    def _decided(self, store, monkeypatch, outcome):
        from modules.heal import decide, decisions, incidents
        e = script(store, dry_run=True)
        S.promote(e["key"], **WHO)
        seen = TestFiring()._seams(monkeypatch)
        rec = {"id": "hi-aaaaaa", "device": "s1"}

        class Lock:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        monkeypatch.setattr(incidents, "HealLock", Lock)
        monkeypatch.setattr(incidents, "ready", lambda network: [rec])
        monkeypatch.setattr(incidents, "claim", lambda network, iid, **kw: rec)
        monkeypatch.setattr(decide, "decide_one", lambda *a, **kw: {"outcome": outcome})
        monkeypatch.setattr(decisions, "record", lambda network, made, now: {
            "id": "d1", "outcome": outcome})
        monkeypatch.setattr(decide, "_act", lambda *a: None)
        monkeypatch.setattr(decide, "_log_steps", lambda *a: None)
        monkeypatch.setattr("modules.incident_page.resolve", lambda network, iid: {
            "found": "page", "incident": rec, "entry": {"cause": "BPDU guard"}})
        classified = []
        monkeypatch.setattr(P, "classify", lambda found: classified.append(found) or BPDU)
        return e, seen, decide.run(NET, now=1.0), classified

    @pytest.mark.parametrize("outcome", ["heal", "would_heal", "propose", "held", "halted",
                                         "off", "deferred", "nothing"])
    def test_where_the_heal_acted_or_was_held_no_script_fires(self, store, monkeypatch,
                                                             outcome):
        """Review 1: only where the heal neither acted nor was held and no code fix exists."""
        _e, seen, out, _c = self._decided(store, monkeypatch, outcome)
        assert out["scripts"] == [] and not seen["preview"] and not seen["run"]

    def test_cant_fix_fires_on_the_incident_as_its_page_resolves_it(self, store, monkeypatch):
        """Review 5: classified from the resolved page (its entry carries the cause)."""
        e, seen, out, classified = self._decided(store, monkeypatch, "cant_fix")
        assert [s["key"] for s in out["scripts"]] == [e["key"]] and seen["run"]
        assert classified[0]["entry"] == {"cause": "BPDU guard"}
        assert seen["held"] == [{"id": "hi-aaaaaa", "device": "s1"}]

    def test_the_heal_decision_fires_it_whatever_the_ai_switch_says(self, store,
                                                                     monkeypatch):
        """`decide.run`: each decided incident's problem asked of the network's scripts, after
        the heal lock, under self-healing's mode; the AI's switch is never read."""
        from modules.heal import decide, decisions, incidents
        e = script(store, dry_run=True)
        S.promote(e["key"], **WHO)
        seen = TestFiring()._seams(monkeypatch)
        rec = {"id": "hi-aaaaaa", "device": "s1"}
        monkeypatch.setattr("modules.incident_page.resolve", lambda network, iid: {
            "found": "unknown", "incident": None, "entry": {}})

        class Lock:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        monkeypatch.setattr(incidents, "HealLock", Lock)
        monkeypatch.setattr(incidents, "ready", lambda network: [rec])
        monkeypatch.setattr(incidents, "claim", lambda network, iid, **kw: rec)
        monkeypatch.setattr(decide, "decide_one", lambda *a, **kw: {"outcome": "cant_fix"})
        monkeypatch.setattr(decisions, "record", lambda network, made, now: {
            "id": "d1", "outcome": "cant_fix"})
        monkeypatch.setattr(decide, "_act", lambda *a: None)
        monkeypatch.setattr(decide, "_log_steps", lambda *a: None)
        monkeypatch.setattr(P, "classify", lambda found: BPDU)
        monkeypatch.setattr("modules.fixit.auto.switch", lambda network: pytest.fail(
            "the AI's switch was read"), raising=False)
        out = decide.run(NET, now=1.0)
        assert [s["key"] for s in out["scripts"]] == [e["key"]] and seen["run"]
        # The investigation then sees it fired, and does not run it twice.
        again = S.fire_matching(NET, {"incident": rec})
        assert again[0]["already"] and len(seen["run"]) == 1


class TestAnotherProcessSeesASave:
    def test_a_sync_while_another_thread_walks_the_kinds_never_breaks_its_walk(self):
        """Review 9: a walk of `STEP_KINDS` is over a copy, so a sync changing the dict
        mid-walk (another thread's save) never raises "changed size during iteration"."""
        walk = iter(E.STEP_KINDS)
        next(walk)
        dict.__setitem__(E.STEP_KINDS, "x-a-sync-mid-walk", None)
        try:
            assert list(walk)
            for view in (E.STEP_KINDS.keys(), E.STEP_KINDS.items(), E.STEP_KINDS.values()):
                it = iter(view)
                next(it)
                dict.__setitem__(E.STEP_KINDS, "x-a-second-sync", None)
                assert list(it)
                dict.pop(E.STEP_KINDS, "x-a-second-sync")
        finally:
            dict.pop(E.STEP_KINDS, "x-a-sync-mid-walk", None)
            dict.pop(E.STEP_KINDS, "x-a-second-sync", None)

    def test_a_save_another_process_made_is_seen_at_once(self, store):
        """A save written by another process (the store replaced on disk, nothing told this
        one) is a catalog entry and a step kind at the next ask; removed, it leaves both."""
        import json

        from modules.heal import catalog
        e = S.save_action(NET, run_id=store["run"](), name="Bounce interface", words="x",
                          **WHO)
        with open(S._path(), encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["plans"]["action-bounce-again"] = dict(doc["plans"][e["key"]],
                                                   key="action-bounce-again",
                                                   template=dict(doc["plans"][e["key"]][
                                                       "template"], key="action-bounce-again"))
        tmp = S._path() + ".other"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        os.replace(tmp, S._path())
        assert "action-bounce-again" in catalog.entries()
        assert "action-bounce-again" in E.STEP_KINDS
        os.remove(S._path())
        assert "action-bounce-again" not in catalog.entries()
        assert "action-bounce-again" not in E.STEP_KINDS


# ── A reusable action ───────────────────────────────────────────────────────────────────────

class TestAReusableAction:
    def test_an_admin_saves_it_and_it_is_a_catalog_entry_and_a_plan_step(self, store):
        from modules.heal import catalog
        e = S.save_action(NET, run_id=store["run"](), name="Bounce interface",
                          words="Shut and no shut one access port, net zero", **WHO)
        assert e["key"] == "fix-bounce-interface"
        op = catalog.entries()[e["key"]]
        assert isinstance(op, catalog.PlanStep) and [p.name for p in op.params] == [
            "device", "interface", "cause"]
        assert catalog.is_command_plan(e["key"])
        E.refresh_saved_kinds()
        assert E.STEP_KINDS[e["key"]].words == "Shut and no shut one access port, net zero"
        assert E.STEP_LABELS[e["key"]] == "Run a saved action"

    def test_its_name_never_takes_a_built_in_plans_key(self, store):
        with pytest.raises(S.Refused):
            S.save_action(NET, run_id=store["run"](), name="", words="x", **WHO)


# ── The approval rights, through the one chokepoint ─────────────────────────────────────────

class TestTheRights:
    @pytest.mark.parametrize("right", sorted(identity.RIGHTS))
    def test_the_ai_holds_none(self, right):
        why = identity.right_refusal(right, actor="ai:fixit", actor_verified="", person=False)
        assert "ai:fixit may not approve" in why and "proposes and never approves" in why
        with identity.as_ai("assistant"):
            assert "ai:assistant may not approve" in identity.right_refusal(right, **WHO)

    @pytest.mark.parametrize("right", sorted(identity.RIGHTS))
    def test_unset_every_verified_person_holds_it_and_no_one_else(self, store, right):
        assert identity.right_refusal(right, **WHO) == ""
        assert "approved by a verified person" in identity.right_refusal(
            right, actor=PERSON, actor_verified="none", person=True)

    @pytest.mark.parametrize("right", identity.LISTED_RIGHTS)
    def test_set_only_its_holders_hold_it(self, store, right):
        store["rights"][right] = [OTHER]
        why = identity.right_refusal(right, **WHO)
        assert f"{PERSON} does not hold the {right.replace('_', '-')} right" in why
        assert identity.right_refusal(right, actor=OTHER, actor_verified="access",
                                      person=True) == ""

    def test_running_a_plan_is_any_engineers_whatever_is_listed(self, store):
        store["rights"].update(self_healing=[OTHER], admin=[OTHER])
        assert identity.right_refusal("run_plan", **WHO) == ""

    def test_saving_and_promoting_a_script_need_self_healing_rights(self, store):
        store["rights"]["self_healing"] = [OTHER]
        with pytest.raises(S.Refused) as exc:
            script(store)
        assert "does not hold the self-healing right" in str(exc.value)
        e = script(store, actor=OTHER, dry_run=True)
        with pytest.raises(S.Refused):
            S.promote(e["key"], **WHO)
        with pytest.raises(S.Refused) as exc:
            S.promote(e["key"], actor="ai:fixit", actor_verified="", person=False)
        assert "ai:fixit may not approve" in str(exc.value)
        assert S.promote(e["key"], actor=OTHER, actor_verified="access",
                         person=True)["mode"] == "auto"

    def test_promote_refuses_another_networks_script_and_keeps_its_promoter(self, store):
        """Review 10: a key of another network is refused; one in Auto keeps who promoted it."""
        e = script(store, dry_run=True)
        with pytest.raises(S.Refused) as exc:
            S.promote(e["key"], network="Other", **WHO)
        assert str(exc.value) == f"{e['key']} is a self-heal script of {NET}, not of Other"
        S.promote(e["key"], network=NET, **WHO)
        with pytest.raises(S.Refused) as exc:
            S.promote(e["key"], network=NET, actor=OTHER, actor_verified="access", person=True)
        assert f"in Auto already, promoted by {PERSON}" in str(exc.value)
        assert S.scripts(NET)[e["key"]]["promoted_by"] == PERSON

    def test_approve_never_trusts_the_callers_admin_flag(self, store):
        """Review 6: `command_policy.approve(..., admin=True)` asks the one chokepoint too."""
        shape = "interface {interface} > description {description}"
        assert POL.propose(NET, "cisco_ios", shape, by="ai:fixit", why="x")["ok"]
        store["rights"]["admin"] = [OTHER]
        got = POL.approve(NET, "cisco_ios", shape, admin=True, **WHO)
        assert not got["ok"] and "does not hold the admin right" in got["words"]
        assert POL.provisional(NET)

    def test_one_reading_of_the_rights_setting(self, store):
        """Review A3: `identity.holds` is the one reading; unset is every verified person's."""
        assert identity.holds("admin", PERSON) and identity.rights_unset() == list(
            identity.LISTED_RIGHTS)
        store["rights"]["admin"] = [OTHER]
        assert not identity.holds("admin", PERSON) and identity.holds("admin", OTHER)
        assert identity.rights_unset() == ["self_healing"]

    def test_saving_an_action_is_an_admins(self, store):
        store["rights"]["admin"] = [OTHER]
        with pytest.raises(S.Refused) as exc:
            S.save_action(NET, run_id=store["run"](), name="Bounce interface", words="x",
                          **WHO)
        assert "does not hold the admin right" in str(exc.value)
        with identity.as_ai("fixit-troubleshoot"), pytest.raises(S.Refused):
            S.save_action(NET, run_id=store["run"](), name="Bounce interface", words="x",
                          actor=OTHER, actor_verified="access", person=True)

    def test_adding_a_shape_is_an_admins_and_its_proposal_and_measurement_are_listed(
            self, store):
        shape = "interface {interface} > description {description}"
        assert POL.propose(NET, "cisco_ios", shape, by="ai:fixit", why="a clumsy fix")["ok"]
        rows = POL.provisional(NET)
        assert [(r["shape"], r["proposed_by"], r["measured"]) for r in rows] == [
            (shape, "ai:fixit", {})]
        store["rights"]["admin"] = [OTHER]
        got = POL.approve_as(NET, "cisco_ios", shape, **WHO)
        assert not got["ok"] and "does not hold the admin right" in got["words"]
        got = POL.approve_as(NET, "cisco_ios", shape, actor="ai:fixit", actor_verified="",
                             person=False)
        assert not got["ok"] and "ai:fixit may not approve" in got["words"]
        assert POL.approve_as(NET, "cisco_ios", shape, actor=OTHER, actor_verified="access",
                              person=True)["ok"]
        assert POL.provisional(NET) == []
