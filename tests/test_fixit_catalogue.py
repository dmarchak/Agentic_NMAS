"""The catalogue the AI may propose from, a proposal's check against the incident, the heal
guards and committed intent, the repeat flag, and Mercury's own proposer
(modules/heal/catalog.py, modules/fixit/validate.py, modules/fixit/proposers.py; the fix-it
plan's S2; the operator's order of 2026-11-12, overnight item 6: "the AI proposes one catalog
operation with parameters; code validates it against intent and the guards; a person approves
it ... a repeated failed proposal is flagged"). No AI call, no device, nothing drawn.

**On real records and captures.** Every check runs on tests/test_heal_resubscribe.py's lab (a
lab router's real configuration on a box, its real intent with subscriptions 101 and 102), a
failed attempt is a real Re-subscribe run whose verify reads no data (`not_back`), a receiver
left removed a real run whose re-add never lands, and a device held is held by the real hold.
Mercury's proposer reads real diagnoses: the lost-stream runbook run on
tests/test_heal_diagnose_stream.py's real captures (r6's subscriptions, r2's pings, r7's
receivers, a kernel's socket tables). The one planted row, said where it is made: an
observe-only device, NetBox's real record (tests/fixtures/netbox/) adapted by the real adapter
with its context set to observe.
"""
import ast
import inspect

import pytest

from modules.fixit import incident as F
from modules.fixit import proposers as PR
from modules.fixit import validate as V
from modules.heal import catalog
from modules.heal import diagnose_stream as DS
from modules.heal import resubscribe as R
from tests.test_fixit_incident import DETECTED, ID, LATER, T0, a_run, tree
from tests.test_heal_diagnose_stream import world  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import ACTOR, NET, Box, Src, lab, run  # noqa: F401
from tests.test_sdn_connections import networks  # noqa: F401 (the fixtures build on)

RESUB, READD = R.KEY, R.READD_KEY


def inc(subs=("101", "102"), device="r2", device_id="nb:7", incident_id=ID):
    return F.Incident(NET, incident_id, device_id, device, DETECTED, tuple(subs))


def proposal(**over):
    return dict({"device": "r2", "subscriptions": ["101", "102"]}, **over)


def check(incident=None, operation=RESUB, params=None, **kw):
    kw.setdefault("now", LATER)
    kw.setdefault("sources", Src())
    return V.check(incident or inc(), operation,
                   proposal() if params is None else params, **kw)


# ── The catalogue and the incident's record name the same operations ───────────────────────

class TestTheCatalogue:
    def test_the_incidents_attempts_are_the_catalogues_operations(self):
        assert F.CATALOGUE_KEYS == tuple(catalog.CATALOG) == (RESUB, READD)
        assert set(F.PARAMETERS) == set(catalog.CATALOG) == set(V.AS_ATTEMPT)

    @pytest.mark.parametrize("key", sorted(catalog.CATALOG))
    def test_each_parameter_but_the_device_is_an_attempts_parameter(self, key):
        """A proposal's parameters reach the form an attempt is compared by, every one but the
        device (the incident's), each to a parameter the attempt declares."""
        names = [p.name for p in catalog.CATALOG[key].params]
        assert names[0] == "device" and "device" in F.NOT_PARAMETERS
        mapped = V.AS_ATTEMPT[key]
        assert sorted(mapped) == sorted(names[1:])
        declared = [n for n, _kind in F.PARAMETERS[key]]
        assert set(mapped.values()) <= set(declared)
        # What the attempt declares beyond the proposal is the collector step alone, which no
        # proposal may name until the operation takes it (C3108).
        assert set(declared) - set(mapped.values()) <= {"collector_step"}

    def test_each_operation_says_its_parameters_shapes_in_words(self):
        for op in catalog.CATALOG.values():
            assert op.words and all(p.takes for p in op.params), op.key
        readd = catalog.CATALOG[READD]
        assert [(p.name, p.takes) for p in readd.params][1] == (
            "subscription", "one subscription id, text of 1 to 10 digits, that the device's "
                            "committed intent declares")


# ── A proposal is checked by code ───────────────────────────────────────────────────────────

class TestACheckedProposal:
    def test_a_well_formed_proposal_is_the_operations_preview_and_hash(self, lab):  # noqa
        from modules import config
        src = Src()
        before = tree(config.DATA_DIR)
        got = check(sources=src)
        own = catalog.preview(RESUB, proposal(), network=NET, sources=src)
        assert got["ok"] and own["ok"]
        assert (got["operation"], got["params"], got["preview"], got["hash"]) == (
            RESUB, proposal(), own["preview"], own["hash"])
        assert got["passed"] == list(V.CHECKS) == ["schema", "scope", "guards", "intent"]
        assert got["repeat"]["kind"] == "new"
        # Nothing sent, held or written.
        assert src.box.batches == [] and src.box.opened == 0
        assert tree(config.DATA_DIR) == before

    def test_a_readd_of_a_receiver_a_run_left_removed_is_its_preview(self, lab):  # noqa
        left = run(Src(box=Box(drops_readd_of=("101",))))
        assert left["outcome"] == "removed"
        got = check(operation=READD, params={"device": "r2", "subscription": "101"})
        assert got["ok"], got
        assert got["preview"]["units"][0]["sub"] == "101" and got["hash"]

    @pytest.mark.parametrize("name,operation,params,code,check_,said", [
        ("a subscription the incident does not name", RESUB, {"subscriptions": ["101", "102"]},
         "not_named", "scope", ["the proposal names subscription 102 on r2, and "
                                f"{ID} names subscription 101: a proposal acts only on what "
                                "its incident names"]),
        ("another device", RESUB, {"device": "r1"}, "another_device", "scope",
         [f"the proposal names the device r1, and {ID} is r2's: a proposal acts on its "
          "incident's own device"]),
        ("a command string as the device", RESUB, {"device": "configure terminal"},
         "wrong_shape", "schema", ["parameter device is one name the network's inventory holds",
                                   "'configure terminal' (18 characters)"]),
        ("a command string as a subscription", RESUB, {"subscriptions": ["101; reload"]},
         "wrong_shape", "schema", ["a list holding '101; reload'"]),
        ("an unknown key", RESUB, {"commands": ["reload"]}, "unknown_parameter", "schema",
         ["takes exactly the parameters device and subscriptions", "also gives 'commands'"]),
        ("an operation the catalog does not hold", "reload-device", {}, "not_in_catalog",
         "schema", ["an operation of the catalog (telemetry-readd and telemetry-resubscribe)",
                    "names 'reload-device'"]),
        ("a re-add of a receiver no run left removed", READD,
         {"device": "r2", "subscription": "101"}, "not_removed", "scope",
         ["a re-add adds back a receiver a run left removed, and the proposal names "
          "subscription 101 on r2, while the receivers left removed there are none"]),
    ])
    def test_each_refusal_names_what_it_compared(self, lab, name, operation, params,  # noqa
                                                 code, check_, said):
        incident = inc(subs=("101",)) if code == "not_named" else inc()
        given = params if operation == READD else proposal(**params)
        if operation == "reload-device":
            given = proposal()
        got = check(incident, operation, given)
        assert (got["ok"], got["code"], got["check"]) == (False, code, check_), got
        for words in said:
            assert words in got["refused"], got["refused"]
        assert got["refused"].endswith(". Nothing was previewed, and nothing runs")
        assert got["passed"] == list(V.CHECKS[:V.CHECKS.index(check_)])
        assert set(got) == {"ok", "code", "check", "refused", "passed"}

    def test_an_incident_with_no_device_refuses_any_proposal(self, lab):  # noqa: F811
        nobody = F.Incident(NET, "al-0f3a9c2b7d4011aa22bb", "", "", DETECTED)
        got = check(nobody)
        assert (got["code"], got["check"]) == ("no_device", "scope")
        assert got["refused"].startswith("al-0f3a9c2b7d4011aa22bb names no device, and "
                                         "telemetry-resubscribe acts on one (r2 was proposed)")

    def test_a_subscription_intent_does_not_declare_is_intents_refusal(self, lab):  # noqa
        got = check(inc(subs=("101", "103")), params=proposal(subscriptions=["103"]))
        assert (got["code"], got["check"]) == ("refused_by_plan", "intent")
        assert "intent declares no telemetry subscription 103 on r2 (2 declared)" in \
            got["refused"]

    def test_a_device_another_operation_holds_is_guard_3s(self, lab):  # noqa: F811
        from modules.nsot import device_ops
        with device_ops.hold(NET, "r2", "telemetry re-subscribe", ACTOR):
            got = check(now=None)
        assert (got["code"], got["check"]) == ("planned_work", "guards")
        assert got["refused"].startswith("guard 3 (")
        assert ("r2 is held by telemetry re-subscribe of op@example.invalid: one operation "
                "per device") in got["refused"]
        assert check(now=None)["ok"], "released, the same proposal passes"

    def test_an_observe_only_device_is_refused_naming_the_key(self, lab, monkeypatch):  # noqa
        from modules import inventory
        from modules.inventory import netbox_source
        from tests.test_inventory_entry import KINDS, OBSERVE, PLATFORM_MAP, record
        monkeypatch.setattr(netbox_source, "get_setting", lambda key, default=None:
                            PLATFORM_MAP if key == "platform_map" else "")
        devices, _skipped, _warn = netbox_source.adapt_devices(
            [record("r2", "cisco-ios", "edge-router", "192.0.2.12", 7, context=OBSERVE,
                    local=OBSERVE)], kinds=KINDS)
        monkeypatch.setattr(inventory, "cached_row",
                            lambda name, host: devices[0] if host == "r2" else None)
        got = check()
        assert (got["code"], got["check"]) == ("management", "guards")
        assert got["refused"].startswith("REFUSED: a proposed telemetry-resubscribe on r2: "
                                         "NetBox's config context sets")
        assert "to observe" in got["refused"]


# ── A repeated failed proposal is flagged, never hidden ─────────────────────────────────────

class TestTheRepeatFlag:
    def test_a_proposal_equal_to_a_failed_attempt_is_flagged_and_still_checked(self,  # noqa
                                                                               lab):
        failed = a_run(T0, ok=False, subs=("101", "102"))
        got = check()
        assert got["ok"] is True, "flagged, never refused or hidden"
        flag = got["repeat"]
        assert (flag["kind"], flag["attempt"], flag["run"], flag["outcome"]) == (
            "repeat", 1, failed["id"], "not_back")
        assert flag["words"] == failed["why"] and flag["complete"] is True

    def test_another_selection_is_a_variation_naming_the_change(self, lab):  # noqa: F811
        a_run(T0, ok=False, subs=("101",))
        flag = check()["repeat"]
        assert flag["kind"] == "variation"
        assert flag["changed"] == [{"name": "subs", "before": ["101"], "after": ["101", "102"]}]

    def test_a_passed_attempt_is_no_repeat(self, lab):  # noqa: F811
        a_run(T0, ok=True, subs=("101", "102"))
        assert check()["repeat"]["kind"] == "new"


class TestPropose:
    def test_a_checked_proposal_is_recorded_with_its_source_and_hash(self, lab):  # noqa
        got = V.propose(inc(), "person", RESUB, proposal(), now=LATER, sources=Src())
        assert got["ok"] and got["proposal"] == "p1"
        (line,) = F.read(inc())["lines"]
        assert (line["source"], line["operation"], line["params_hash"]) == (
            "person", RESUB, F.params_hash(RESUB, {"subs": ["101", "102"]}))
        # The run its confirm starts can name it.
        assert F.run_link(inc(), "p1")["proposal"] == "p1"

    def test_a_refused_ai_answer_is_recorded_with_no_operation_so_its_cost_counts(  # noqa
            self, lab):
        from tests.test_fixit_incident import CALL_A, a_call
        a_call(CALL_A, 0.04)
        got = V.propose(inc(), "ai", RESUB, proposal(device="r1"), calls=[CALL_A],
                        prompt="fixit_troubleshoot/1", now=LATER, sources=Src())
        assert got["ok"] is False and got["proposal"] == "p1"
        (line,) = F.read(inc())["lines"]
        assert (line["operation"], line["calls"], line["prompt"]) == (
            "", [CALL_A], "fixit_troubleshoot/1")
        assert F.cost_so_far(inc())["usd"] == pytest.approx(0.04)

    @pytest.mark.parametrize("source", ["mercury", "person"])
    def test_a_refused_proposal_of_mercury_or_a_person_records_nothing(self, lab,  # noqa
                                                                       source):
        got = V.propose(inc(), source, RESUB, proposal(device="r1"), now=LATER, sources=Src())
        assert got["ok"] is False and got["proposal"] == ""
        assert F.read(inc())["state"] == "absent"

    def test_an_unknown_source_is_refused_before_anything(self, lab):  # noqa: F811
        with pytest.raises(F.Refused, match="a proposal comes from one of mercury, ai, person"):
            V.propose(inc(), "policy", RESUB, proposal(), now=LATER)
        assert F.read(inc())["state"] == "absent"


# ── Mercury's own proposer ──────────────────────────────────────────────────────────────────

def recovery_rules() -> set:
    """The lost-stream rules whose finding's next step is Re-subscribe, read from the rules'
    own source (`diagnose_stream.RECOVERY` referenced in their function), independently of the
    proposer's table."""
    from modules.heal import diagnose_stream as S
    out = set()
    for rule in S.STREAM_RULES:
        fn = rule.fn
        fn = getattr(fn, "__wrapped__", None) or next(
            (c.cell_contents for c in (fn.__closure__ or ()) if callable(c.cell_contents)), fn)
        names = {n.id for n in ast.walk(ast.parse(inspect.getsource(fn)))
                 if isinstance(n, ast.Name)}
        if "RECOVERY" in names:
            out.add(rule.name)
    return out


def a_diagnosis(rule: str, incomplete=()) -> dict:
    """A lost-stream diagnosis whose first hypothesis is *rule*'s, in `diagnose.finding`'s
    shape: for the table, every rule; the cases below are real runs."""
    from modules.heal import diagnose_stream as S
    r = next(x for x in S.STREAM_RULES if x.name == rule)
    return {"runbook": "stream_lost", "target": {"device": "r2", "subscriptions": ["101", "102"]},
            "hypotheses": [{"rule": r.name, "layer": r.layer, "strength": r.strength,
                            "claim": f"{r.words} on r2", "todo": "the rule's next step",
                            "incomplete": list(incomplete), "evidence": [], "agree": 1}]}


class TestMercurysProposer:
    def test_its_table_is_every_rule_whose_next_step_is_re_subscribe(self):
        found = recovery_rules()
        assert found == set(PR.STREAM_PROPOSALS) == {"half_open", "no_session",
                                                     "outlived_cause"}
        assert set(PR.STREAM_PROPOSALS.values()) <= set(catalog.CATALOG)
        assert len(DS.STREAM_RULES) >= 12

    @pytest.mark.parametrize("rule", sorted(r.name for r in DS.STREAM_RULES))
    def test_each_stream_rule_maps_to_its_operation_or_says_none(self, lab, rule):  # noqa
        got = PR.mercury(inc(), a_diagnosis(rule))
        if rule in recovery_rules():
            assert (got["state"], got["operation"], got["params"], got["rule"]) == (
                "proposed", RESUB, {"device": "r2", "subscriptions": ["101", "102"]}, rule)
        else:
            assert (got["state"], got["operation"], got["rule"]) == ("none", "", rule)
            assert got["words"].endswith("names a next step no operation of the catalog is: "
                                         "the rule's next step")

    def test_a_real_run_whose_stream_outlived_its_cause_proposes_re_subscribe(  # noqa: F811
            self, world, tmp_path):
        from tests.test_heal_diagnose_stream import rules, stream
        got, _f = stream(tmp_path, tcp6=False)
        assert rules(got)[0] == "outlived_cause" and not got["hypotheses"][0]["incomplete"]
        p = PR.mercury(inc(), got)
        assert (p["state"], p["source"], p["operation"], p["params"]) == (
            "proposed", "mercury", RESUB, {"device": "r2", "subscriptions": ["101", "102"]})
        assert p["words"].startswith("the first hypothesis (outlived_cause, strong): r2's "
                                     "telemetry hasn't recovered since r1 was put back")
        # Only what the incident names: an incident of one stream proposes that one.
        assert PR.mercury(inc(subs=("102",)), got)["params"]["subscriptions"] == ["102"]

    def test_a_real_half_open_with_its_receivers_read_proposes_it(self, world,  # noqa: F811
                                                                  tmp_path):
        """r7's real receiver answers (Connected on 496, not streaming), the stream's series
        absent, and no cause found: the half-open session is the first hypothesis, complete."""
        got = half_open_run(tmp_path)
        first = got["hypotheses"][0]
        assert (first["rule"], first["incomplete"]) == ("half_open", [])
        p = PR.mercury(inc(), got)
        assert (p["state"], p["operation"], p["params"], p["rule"]) == (
            "proposed", RESUB, {"device": "r2", "subscriptions": ["101", "102"]}, "half_open")

    def test_a_real_half_open_lacking_its_receivers_proposes_nothing(self, world,  # noqa
                                                                     tmp_path):
        from tests.test_heal_diagnose_stream import stream, target
        none = {"state": "none", "why": "no change on another device is in the heal records "
                                        "for the 10 minutes before the stream was lost"}
        got, _f = stream(tmp_path, tgt=target(none), tcp6=False)
        assert [h["rule"] for h in got["hypotheses"]] == ["half_open"]
        p = PR.mercury(inc(), got)
        assert (p["state"], p["rule"]) == ("none", "half_open")
        assert p["words"].startswith("the first hypothesis (half_open, strong) lacks evidence")
        assert p["words"].endswith("and a proposal is made only on a complete one")

    def test_a_real_collector_out_of_reach_names_its_own_next_step(self, world,  # noqa
                                                                  tmp_path):
        from tests.test_heal_diagnose_stream import PING_NONE, answers, stream
        got, _f = stream(tmp_path, answers(ping=PING_NONE), tcp6=False)
        p = PR.mercury(inc(), got)
        assert (p["state"], p["rule"]) == ("none", "collector_unreached")
        assert p["words"] == ("the first hypothesis (collector_unreached, decisive) names a "
                              "next step no operation of the catalog is: Run Can't reach from "
                              "r2 to 192.0.2.10")

    def test_a_real_stream_back_proposes_nothing(self, world, tmp_path):  # noqa: F811
        from tests.test_heal_diagnose_stream import PRESENT, flowing_run
        got = flowing_run(tmp_path, lambda d, s: PRESENT, tcp6=False)
        assert got["hypotheses"] == []
        assert PR.mercury(inc(), got) == {
            "state": "none", "source": "mercury", "operation": "", "params": {}, "rule": "",
            "words": "the diagnosis found no cause, and a proposal is never a guess"}

    def test_a_receiver_left_removed_is_re_added_first(self, lab):  # noqa: F811
        run(Src(box=Box(drops_readd_of=("101",))))
        p = PR.mercury(inc(), a_diagnosis("half_open"))
        assert (p["state"], p["operation"], p["params"]) == (
            "proposed", READD, {"device": "r2", "subscription": "101"})
        # And the check takes it: the danger state's own fix.
        assert check(operation=READD, params=p["params"])["ok"]

    @pytest.mark.parametrize("diagnosis,said", [
        (None, "Mercury has not diagnosed this incident yet: Diagnose now reads it"),
        ({"runbook": "cant_reach", "runbook_words": "r2 can't reach r1"},
         "the diagnosis ran \"r2 can't reach r1\", and only the lost-stream runbook's"),
        (dict(a_diagnosis("half_open"), target={"device": "r1", "subscriptions": ["101"]}),
         f"the diagnosis is of r1, and {ID} is r2's"),
    ])
    def test_no_proposal_from_a_diagnosis_that_does_not_name_one(self, lab, diagnosis,  # noqa
                                                                 said):
        p = PR.mercury(inc(), diagnosis)
        assert p["state"] == "none" and p["operation"] == "" and said in p["words"]

    def test_its_proposal_passes_the_check_and_is_flagged_when_it_failed_before(  # noqa
            self, lab):
        a_run(T0, ok=False, subs=("101", "102"))
        p = PR.mercury(inc(), a_diagnosis("outlived_cause"))
        got = V.propose(inc(), p["source"], p["operation"], p["params"], now=LATER,
                        sources=Src())
        assert got["ok"] and got["repeat"]["kind"] == "repeat" and got["repeat"]["attempt"] == 1
        assert F.read(inc())["lines"][0]["source"] == "mercury"


def half_open_run(tmp_path):
    """The lost-stream runbook on its real captures with r7's receiver answers, the series
    absent and no cause found (tests/test_heal_diagnose_stream.py's `flowing_run`, its target
    the no-cause one)."""
    from modules.heal import diagnose as D
    from modules.heal import diagnose_stream as S
    from tests.test_heal_diagnose import ACTOR as DIAGNOSER
    from tests.test_heal_diagnose import Fleet, fleet, quiet
    from tests.test_heal_diagnose_stream import (ABSENT, NOW, at_collector, proc, target,
                                                 with_receivers)
    model, intents = fleet(at_collector())
    root = proc(tmp_path, tcp6=False)
    none = {"state": "none", "why": "no change on another device is in the heal records for "
                                    "the 10 minutes before the stream was lost"}
    return D.run(NET, "stream_lost", target(none), DIAGNOSER, session=Fleet(with_receivers()),
                 logs=quiet, model=model, intents=intents, now=NOW,
                 series=lambda d, s: ABSENT,
                 collector=lambda a, p, s: S.read_collector(a, p, s, proc=root))
