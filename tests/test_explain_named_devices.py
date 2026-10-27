"""Every device an Explain answer names is cited in it (C1897). modules/ai/explain.py (`check`,
`uncited_devices`, `named_devices`, `cites_device`).

**The walk that found it** (the operator's Walk 2 re-run, 2026-10-27 05:03 UTC): Explain on r1's
"Device unreachable (SNMP)" of 2026-10-22 18:01:50Z, its pack rebuilt with schema 5, named r7 in
its rationale ("r2, r3, r4, r7, s1, s3 and s4 raised their own Device unreachable (SNMP)
alerts") and cited nothing of r7, though r7's alert was in the pack. Every reference it cited
resolved, so the check of the time accepted it.

**The captures** (tests/fixtures/evidence_pack/, read-only from the NMAS host via LAN,
2026-10-27): ``walk2_r1_pack.json``, the rebuilt pack the re-run read (`scripts/nmas-pack-replay
--episode 96671faee6a201ade8de`, schema 5, hash dc29086001f9; masked when it was built);
``walk2_r1_topology.yaml``, the topology sent with it (the call's own request); and
``walk2_r1_answer.json``, the model's structured answer as the call ai-91ed63fa03f642c5 recorded
it, word for word. Two minimal edits, for publication: the History pieces' person is
``operator@example.com`` in place of the operator's address (so the pack's stored hash, kept as
captured, is no longer its digest; nothing here checks it), and containerlab's management
subnet in the topology is 192.0.2.0/24 in place of the lab LAN's. Read as written, the answer names FOUR devices it never cites: r6 and s2 (in
"r2, r3, r4, r6, s1, s3, s4 and s2 show failed scrapes"), r7, and s4 (named three times, never
cited); the re-run's report saw only r7.
"""
import copy
import json
import os

import pytest
import yaml

from modules.ai import explain
from tests.test_ai_explain import world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "tests", "fixtures", "evidence_pack")


def _load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh) if name.endswith(".yaml") else json.load(fh)


PACK = _load("walk2_r1_pack.json")
TOPOLOGY = _load("walk2_r1_topology.yaml")
ANSWER = _load("walk2_r1_answer.json")
#: The topology sent: every id it holds, and its devices' ids by name.
IDS = sorted(set(TOPOLOGY["devices"]) | set(TOPOLOGY["links"]) | set(TOPOLOGY["adjacencies"]))
NAMES = {d["name"]: i for i, d in TOPOLOGY["devices"].items()}
#: The pack as sent: never the observed overlay (`explain.NOT_SENT`); its ids are already the
#: model's (schema 5), so `one_id` moves nothing.
SENT = [s for s in PACK["sections"] if s["name"] not in explain.NOT_SENT]
#: r7's alert in the window, and the other uncited devices' own evidence in the pack.
R7_ALERT = "concurrent:b913a5feb2052bd5623b"
R6_HEARTBEAT = "health:dev:24:heartbeat"
S2_SCRAPES = "health:dev:u9cc83d5c:scrapes"
S4_ALERT = "concurrent:d52a22dc90c0b0ef93a6"


def _check(answer, names=NAMES, ids=IDS):
    model = explain.ExplanationV2.model_validate_json(json.dumps(answer))
    return explain.check(model, PACK, ids, sections=SENT, names=names)


def _citing(*refs):
    a = copy.deepcopy(ANSWER)
    a["hypotheses"][0]["evidence_refs"] += list(refs)
    return a


def test_the_captures_are_the_walk_s():
    assert PACK["id"] == "ep-7607ab655cee9cd2e37c" and PACK["schema"] == 5
    assert PACK["hash"].startswith("dc29086001f9")
    assert "r7, s1, s3 and s4 raised their own" in ANSWER["rationale"]
    held = {p["ref"]: p for s in SENT for p in s.get("pieces") or []}
    assert held[R7_ALERT]["device"] == "r7" and held[S4_ALERT]["device"] == "s4"
    assert held[R6_HEARTBEAT]["device"] == "r6" and held[S2_SCRAPES]["device"] == "s2"


def test_the_walk_s_answer_as_written_is_refused_naming_r7():
    why = _check(ANSWER)
    assert why == ("the answer names r6, r7, s2 and s4 but cites nothing of them: every device "
                   "it names needs a citation of its own (its figures, its alerts or its id in "
                   "the topology)")


def test_with_r7_s_alert_cited_r7_is_no_longer_named():
    assert _check(_citing(R7_ALERT)).startswith("the answer names r6, s2 and s4 but")


def test_with_every_named_device_cited_it_is_accepted():
    assert _check(_citing(R7_ALERT, R6_HEARTBEAT, S2_SCRAPES, S4_ALERT)) == ""


def test_the_checked_list_counts_as_a_citation():
    a = _citing(R7_ALERT, R6_HEARTBEAT, S2_SCRAPES)
    a["checked"] = a["checked"] + [S4_ALERT]
    assert _check(a) == ""


def test_a_device_known_only_by_the_topology_is_cited_by_its_id():
    """s4's id in the topology, or an adjacency holding it as an end (IPv4 and IPv6 subnets)."""
    for ref in ("dev:u66688a5c", "adj:ospf:dev:u66688a5c~dev:uc038a8be:10.255.3.0/24"):
        assert _check(_citing(R7_ALERT, R6_HEARTBEAT, S2_SCRAPES, ref)) == "", ref
    assert explain.cites_device("adj:ospfv3:dev:u342aff19~dev:uc038a8be:2001:db8:3::/64", "r2",
                                "dev:u342aff19", {"sections": SENT}, "r1")


def test_an_id_inside_a_longer_id_is_not_it():
    assert not explain.cites_device("cable:dev:26/Gi3~dev:28/Gi0/1", "rX", "dev:2",
                                    {"sections": SENT}, "r1")
    assert explain.cites_device("cable:dev:26/Gi3~dev:28/Gi0/1", "r8", "dev:26",
                                {"sections": SENT}, "r1")


@pytest.mark.parametrize("text,named", [
    ("r10 failed", ["r10"]), ("r1 and r10", ["r1", "r10"]), ("core-r1 failed", []),
    ("r1.lab failed", []), ("on r1.", ["r1"]), ("r1's CPU", ["r1"]), ("R1 failed", []),
    ("s3/s4 side", ["s3", "s4"]), ("(dev:@r1)", ["r1"]), ("Gi2 and 10.255.1.24", [])])
def test_a_name_is_matched_as_a_whole_token(text, named):
    assert explain.named_devices(text, ["r1", "r10", "s3", "s4"]) == named


def test_a_longer_name_holding_a_shorter_one_is_not_counted_twice():
    assert explain.named_devices("edge-1 is down", ["edge", "edge-1"]) == ["edge-1"]


def test_the_alert_s_own_sections_cite_its_own_device():
    """The alert, its Intent check and its History name no device in their pieces: they are the
    pack's own device's (r1), and cite no other device."""
    sent = {"sections": SENT}
    for ref in ("alert", "alert:1", "intent:1", "history:1", "logs:2"):
        assert explain.cites_device(ref, "r1", "dev:uc038a8be", sent, "r1"), ref
        assert not explain.cites_device(ref, "r3", "dev:ub937e1ed", sent, "r1"), ref


def test_r1_inside_r10_is_not_r1():
    assert explain.named_devices("r10 failed", ["r1"]) == []
    assert explain.named_devices("r10 failed", ["r1", "r10"]) == ["r10"]


def test_no_fault_found_naming_an_uncited_device_is_refused():
    nff = {"outcome": "no_fault_found", "rationale": "r1 and r3 look healthy.",
           "hypotheses": [], "checked": ["health:dev:uc038a8be:cpu"], "needs_human": False,
           "why_not": ""}
    assert _check(nff).startswith("the answer names r3 but cites nothing of it")
    nff["checked"].append("health:dev:ub937e1ed:cpu")
    assert _check(nff) == ""


def test_a_refusal_is_not_held_to_it():
    a = dict(copy.deepcopy(ANSWER), outcome="refuse", hypotheses=[], why_not="r7 is unclear")
    assert _check(a) == ""


def test_with_no_topology_sent_the_pack_s_own_names_still_count():
    """The topology class off: r7 is still known by its alert in the pack (the answer less its
    one topology citation, which nothing sent would hold)."""
    a = copy.deepcopy(ANSWER)
    a["hypotheses"][0]["evidence_refs"].remove("link:10.255.3.0/24")
    assert _check(a, names=None, ids=()).startswith("the answer names r6, r7, s2 and s4 but")


def test_explain_shows_nothing_and_records_the_refusal(world, monkeypatch):  # noqa: F811
    """Through `explain_pack`: an answer naming a device it does not cite is couldn't analyse,
    naming it, and the call's use is recorded as refused by validation."""
    from modules.ai import calls
    from tests.test_ai_explain import _answer, _explain
    used = []
    monkeypatch.setattr(calls, "record_use", lambda cid, use, **kw: used.append((use, kw)))
    world.answer = _answer(world.pack, rationale="r1 and r2 both logged errors.")
    got = _explain(world)
    assert got["ok"] is False and got["error"] == "couldnt_analyse", got
    assert "the answer names r2 but cites nothing of it" in got["detail"]
    assert "answer" not in got and used[-1][0] == "refused by validation"
    world.answer = _answer(world.pack)
    assert _explain(world)["ok"] is True
