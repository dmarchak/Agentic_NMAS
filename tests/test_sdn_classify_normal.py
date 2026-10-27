"""A collection no rule fired on, classified (the Lab 8 walk's objective 2.3, false positives;
scripts/nmas-sdn-classify-normal's `classify_collection`, over `closed_loop.prepare_collection`
and `judge_collection`; the call is the script's, never a module's, so the AI entry-point check
holds: tests/test_ai_entry_points.py). The collection is the Lab
8 run's real capture of normal traffic (tests/fixtures/sdn/lab8/l2_only_s1.json: the first
topology after pings) through the real `collect_threat_data`; the gateway is real (its
trigger, caps, mask and record), the provider a fake. Nothing is sent to a switch.

- **The request**: the same blocks as a detection's, its detection saying no rule fired and
  resting on no evidence; every id sent is one the answer may cite, and every one the check
  accepts was sent; no pack reference is sent; the switches' DPIDs and the flows' addresses
  (IPv4 and IPv6, in any spelling) are the names.
- **The gates**, as `classify_pack`'s: the classification marking, the topology class, the
  response policy, a collection that read no switch or is another network's: nothing sent.
- **The answer**: "no threat" and "a threat" are each reported as the model gave them, a threat
  as a false positive, never refused away; the check's verdict beside it.
- **The script**: its dry run reads the collection and asks nothing; its runs are recorded as
  `evaluation:<run>`, each assessment printed, and the summary counts false positives.
"""
import importlib.machinery
import importlib.util
import json
import os
import types

import pytest

from modules.ai import calls, gateway
from modules.sdn import closed_loop as CL
from tests.sdn_fakes import lab8
from tests.test_sdn_classify import answer, rows, world  # noqa: F401 - the fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_lab8 import collect, lab  # noqa: F401 - the fixture
from tests.test_sdn_loop_live import data_of, ids_in

NET = "Default"
EVAL = "evaluation:sdn-normal-test"


def normal():
    """The Lab 8 run's normal traffic, collected as the loop collects it."""
    return collect(lab8("l2_only_s1.json"))


def ask(world, collected=None, **kw):
    from modules.ai import triggers
    return _script().classify_collection(NET, collected or normal(), actor=EVAL,
                                  trigger=triggers.evaluation(EVAL), send=world.send, **kw)


def no_threat(cite) -> dict:
    return answer(reasoning="Ports carry a few packets a second; nothing stands out.",
                  threat_detected=False, threat_type="none", severity="none",
                  affected_devices=[], recommended_action="Nothing.", action_id="none",
                  parameters={"source": "", "flow": "", "hard_timeout": 0, "rate": 0,
                              "unit": "kbps", "burst": 0}, evidence_refs=[cite])


def citing(world, make):
    """A fake provider answering ``make(data)``, *data* the request's parsed blocks."""
    base = world.send

    def send(body, key):
        world.answer = make(data_of(body))
        return base(body, key)
    return send


# ── the request ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.usefixtures("lab")
def test_the_request_says_no_rule_fired_and_every_id_sent_may_be_cited(world):
    send = citing(world, lambda d: no_threat(d["evidence"]["pieces"][0]["id"]))
    got = _script().classify_collection(NET, normal(), actor=EVAL,
                                 trigger={"kind": "evaluation", "run": "sdn-normal-test"},
                                 send=send)
    assert got["ok"], got
    (body,) = world.sent
    data = data_of(body)
    det = data["detection"]
    assert (det["rule"], det["words"], det["evidence"]) == ("none", CL.NO_DETECTION_WORDS, [])
    assert det["switches"] == ["0000000000000001"]
    req = CL.collection_request(NET, normal(), CL.network_actions(CL.policy(NET)),
                                {"sdn_response_hard_timeout_seconds": 600,
                                 "sdn_response_max_seconds": 3600})
    assert ids_in(data) == req["sent"]["ids"] and len(req["sent"]["ids"]) > 3
    kinds = {p["kind"] for p in data["evidence"]["pieces"]}
    assert kinds == {"port", "flow", "coverage"}
    text = json.dumps(data)
    assert '"ref"' not in text and '"sdn:' not in text
    assert "0000000000000001" in data["names"]
    (row,) = rows()
    assert row["prompt"] == "sdn_classify.v2" and row["actor"] == EVAL
    assert row["subject"]["kind"] == "sdn_collection"
    assert got["sent"]["ids"] == len(req["sent"]["ids"])


def test_an_ipv6_address_in_the_evidence_is_a_name_in_any_spelling(world):
    from tests.test_sdn_detect import T0, collect as collect_v6, save
    save()
    collected = collect_v6(T0)
    req = CL.collection_request(NET, collected, ["drop_source"], {
        "sdn_response_hard_timeout_seconds": 600, "sdn_response_max_seconds": 3600})
    assert "2001:db8::1" in req["sent"]["names"] and "192.0.2.1" in req["sent"]["names"]
    send = citing(world, lambda d: dict(no_threat(d["evidence"]["pieces"][0]["id"]),
                                        threat_detected=True, threat_type="other",
                                        severity="low",
                                        affected_devices=["2001:0db8:0:0:0:0:0:1"]))
    got = _script().classify_collection(NET, collected, actor=EVAL,
                                 trigger={"kind": "evaluation", "run": "sdn-normal-test"},
                                 send=send)
    assert got["ok"] and got["check"]["passed"], got


@pytest.mark.usefixtures("lab")
def test_a_busy_collection_sends_its_busiest_flows_and_counts_the_rest():
    from modules.sdn import detect
    collected = collect(lab8("scan_s1.json"))
    req = CL.collection_request(NET, collected, [], {"sdn_response_hard_timeout_seconds": 600,
                                                     "sdn_response_max_seconds": 3600})
    flows = [p for p in req["sent"]["pieces"] if p["kind"] == "flow"]
    assert len(flows) == detect.SECTION_FLOWS < req["section"]["total"]
    assert req["section"]["subset"] is True
    counts = [p["packet_count"] or 0 for p in flows]
    assert counts == sorted(counts, reverse=True)


@pytest.mark.usefixtures("lab")
def test_the_catalogue_sent_is_the_actions_the_network_allows(world):
    from modules import list_settings
    assert list_settings.write(NET, {CL.POLICY_KEY: {
        "scan": ["rate_limit_source"], "flood": ["rate_limit_source"],
        "unauthorised_flow": ["remove_flow"]}}, actor="test")["ok"]
    from tests.test_sdn_policy import catalogue_sent
    got = _script().classify_collection(
        NET, normal(), actor=EVAL, trigger={"kind": "evaluation", "run": "sdn-normal-test"},
        send=citing(world, lambda d: no_threat(d["evidence"]["pieces"][0]["id"])))
    assert got["ok"], got
    (body,) = world.sent
    assert catalogue_sent(body) == ["rate_limit_source", "remove_flow", "none"]


# ── the gates ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.usefixtures("lab")
@pytest.mark.parametrize("plant,error", [
    ({"modules.ai.egress_classes.classification_marking": lambda net: "planted-restricted"},
     "classified"),
    ({"modules.ai.egress_classes.topology_allowed":
      lambda net: {"allowed": False, "why": "planted: off"}}, "withheld"),
    ({"modules.sdn.closed_loop.policy":
      lambda net: {"ok": False, "rules": {}, "error": "planted: unreadable"}}, "policy"),
], ids=["marking", "topology", "policy"])
def test_the_gates_refuse_as_a_detection_s_do_and_send_nothing(world, monkeypatch, plant,
                                                                error):
    for target, fn in plant.items():
        monkeypatch.setattr(target, fn)
    got = ask(world)
    assert got["error"] == error and "nothing was sent" in got["detail"], got
    assert world.sent == [] and rows() == []


@pytest.mark.usefixtures("lab")
def test_a_collection_that_read_no_switch_or_another_network_s_sends_nothing(world):
    empty = dict(normal(), summary={"switches": 0}, state="unreadable", error="planted")
    got = ask(world, empty)
    assert got["error"] == "no_collection" and "(unreadable: planted)" in got["detail"]
    got = ask(world, dict(normal(), network="branch"))
    assert got["error"] == "collection" and "'branch''s, not 'Default''s" in got["detail"]
    assert world.sent == []


# ── the answer ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.usefixtures("lab")
def test_no_threat_is_reported_with_the_check_passed(world):
    got = _script().classify_collection(
        NET, normal(), actor=EVAL, trigger={"kind": "evaluation", "run": "sdn-normal-test"},
        send=citing(world, lambda d: no_threat(d["evidence"]["pieces"][0]["id"])))
    assert got["ok"] and got["threat_detected"] is False
    assert got["assessment"]["threat_detected"] is False and got["check"]["passed"]
    assert [u["use"] for us in calls.uses().values() for u in us] == [
        "assessed a collection no rule fired on: no threat"]


@pytest.mark.usefixtures("lab")
def test_a_threat_is_reported_as_the_model_gave_it_never_refused_away(world):
    def threat(d):
        port = d["evidence"]["pieces"][0]["id"]
        return answer(reasoning="Port 1 is busy.", threat_detected=True, threat_type="flood",
                      severity="medium", affected_devices=["0000000000000001"],
                      recommended_action="Rate-limit it.", action_id="drop_source",
                      evidence_refs=[port])
    got = _script().classify_collection(NET, normal(), actor=EVAL,
                                 trigger={"kind": "evaluation", "run": "sdn-normal-test"},
                                 send=citing(world, threat))
    assert got["ok"] and got["threat_detected"] is True
    a = got["assessment"]
    assert (a["threat_type"], a["severity"], a["action_id"]) == ("flood", "medium",
                                                                 "drop_source")
    assert got["check"]["passed"] is False
    assert got["check"]["why"] == "drop_source answers scan, flood, not the detection's rule none"
    assert [u["use"] for us in calls.uses().values() for u in us] == [
        "assessed a collection no rule fired on: a threat (a false positive to report)"]


# ── the script ────────────────────────────────────────────────────────────────────────────────

def _script():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts",
                        "nmas-sdn-classify-normal")
    loader = importlib.machinery.SourceFileLoader("nmas_sdn_classify_normal", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


@pytest.mark.usefixtures("lab")
def test_the_dry_run_reads_the_collection_and_asks_nothing(world, capsys):
    got = normal()
    assert _script().main(["--list", NET, "--dry-run"], collector=lambda n, i: got) == 0
    said = capsys.readouterr().out
    assert "would send: " in said and '"ids": ' in said and '"flows_read": ' in said
    assert world.sent == [] and rows() == []


@pytest.mark.usefixtures("lab")
@pytest.mark.parametrize("threat,summary", [
    (False, "2 of 2 said no threat (false positives: 0)"),
    (True, "0 of 2 said no threat (false positives: 2)")], ids=["no-threat", "threat"])
def test_the_runs_are_an_evaluation_each_printed_and_counted(world, monkeypatch, capsys,
                                                             tmp_path, threat, summary):
    def make(d):
        a = no_threat(d["evidence"]["pieces"][0]["id"])
        return dict(a, threat_detected=True, threat_type="other", severity="low") if threat \
            else a
    monkeypatch.setattr(gateway, "anthropic_adapter", types.SimpleNamespace(
        **{**vars(gateway.anthropic_adapter), "send": citing(world, make)}))
    got = normal()
    out = tmp_path / "normal.json"
    assert _script().main(["--list", NET, "--runs", "2", "--out", str(out),
                           "--actor", EVAL], collector=lambda n, i: got) == 0
    said = capsys.readouterr().out
    assert said.count('"threat_detected": ') == 2 and summary in said
    assert [r["actor"] for r in rows()] == [EVAL, EVAL]
    assert {r["trigger"]["kind"] for r in rows()} == {"evaluation"}
    kept = json.loads(out.read_text())
    assert kept["summary"].startswith(summary) and len(kept["recordings"]) == 2
    assert kept["collection"]["collected_at"] == got["collected_at"]


def test_a_person_s_address_is_refused_as_the_actor(networks, capsys):  # noqa: F811
    assert _script().main(["--list", NET, "--out", "/tmp/x.json", "--actor",
                           "op@example.com"], collector=lambda n, i: {}) == 2
    assert "reads as a person's address" in capsys.readouterr().err
