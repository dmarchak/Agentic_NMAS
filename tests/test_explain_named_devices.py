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
import re

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


def _with_r3_in_the_topology(monkeypatch):
    """The world's topology sent holds r1 alone; with r3's id added, r3 is a device the
    topology sent knows and the pack holds nothing of (the pack's pieces are r1's)."""
    real = explain.topology

    def topology(pack):
        got = real(pack)
        return dict(got, ids=sorted(set(got["ids"]) | {got["names"]["r3"]}))
    monkeypatch.setattr(explain, "topology", topology)


def test_explain_shows_nothing_and_records_the_refusal(world, monkeypatch):  # noqa: F811
    """Through `explain_pack`: an answer naming a device the topology sent knows and the pack
    holds nothing of, cited nothing of, is couldn't analyse, naming it, and the call's use is
    recorded as refused by validation (Mercury cites only what the pack holds, decision 7a)."""
    from modules.ai import calls
    from tests.test_ai_explain import _answer, _explain
    _with_r3_in_the_topology(monkeypatch)
    used = []
    monkeypatch.setattr(calls, "record_use", lambda cid, use, **kw: used.append((use, kw)))
    world.answer = _answer(world.pack, rationale="r1 and r3 both logged errors.")
    got = _explain(world)
    assert got["ok"] is False and got["error"] == "couldnt_analyse", got
    assert "the answer names r3 but cites nothing of it" in got["detail"]
    assert "answer" not in got and used[-1][0] == "refused by validation"
    world.answer = _answer(world.pack)
    assert _explain(world)["ok"] is True


# --------------------------- the operator's decision 7 (2026-10-28): Mercury cites, ids read

#: The walk's pack with s4's own evidence left out, as v6's budget left it out of case 5's
#: (the failure analysis of 2026-10-28, class b): s4 is then known only by the topology sent.
SENT_WITHOUT_S4 = [dict(s, pieces=[p for p in s.get("pieces") or [] if p.get("device") != "s4"])
                   for s in SENT]


def _model(answer):
    return explain.ExplanationV2.model_validate_json(json.dumps(answer))


def test_a_named_device_the_pack_holds_is_cited_by_mercury():
    """Decision 7a: the walk's answer as written names r6, r7, s2 and s4 and cites nothing of
    them; the pack holds each one's own evidence, so Mercury cites it (an alert first, else a
    figure), and with Mercury's citations the check accepts it. The model's own references are
    not changed."""
    model = _model(ANSWER)
    added = explain.mercury_cites(model, {"sections": SENT}, explain.sent_names(NAMES, IDS), "r1")
    held = {p["ref"]: p for s in SENT for p in s.get("pieces") or []}
    assert [a["device"] for a in added] == ["r6", "r7", "s2", "s4"]
    assert all(held[a["ref"]]["device"] == a["device"] for a in added), added
    by = {a["device"]: a for a in added}
    assert by["r7"]["ref"] == R7_ALERT and by["s4"]["ref"] == S4_ALERT
    assert by["r7"]["named_in"] == "the rationale"
    refs = [a["ref"] for a in added]
    assert explain.check(model, PACK, IDS, sections=SENT, names=NAMES, added=refs) == ""
    assert _check(ANSWER).startswith("the answer names r6, r7, s2 and s4 but"), \
        "the model's answer alone is still uncited"
    assert model.hypotheses[0].evidence_refs == ANSWER["hypotheses"][0]["evidence_refs"]


def test_a_named_device_the_pack_does_not_hold_still_refuses():
    """Decision 7a: s4, its figures and alert left out of the pack (known only by the topology
    sent), gets no citation from Mercury, and the answer is still refused naming it."""
    model = _model(ANSWER)
    sent = {"sections": SENT_WITHOUT_S4}
    added = explain.mercury_cites(model, sent, explain.sent_names(NAMES, IDS), "r1")
    assert [a["device"] for a in added] == ["r6", "r7", "s2"]
    why = explain.check(model, PACK, IDS, sections=SENT_WITHOUT_S4, names=NAMES,
                        added=[a["ref"] for a in added])
    assert why.startswith("the answer names s4 but cites nothing of it"), why


def test_the_alert_s_own_device_is_cited_by_the_alert():
    a = {"outcome": "answer", "rationale": "r1 lost its scrapes.", "needs_human": False,
         "hypotheses": [{"claim": "The polling path failed.", "evidence_refs": ["concurrent"],
                         "confirm_with": "show ip route"}], "checked": [], "why_not": ""}
    added = explain.mercury_cites(_model(a), {"sections": SENT}, NAMES, "r1")
    assert added == [{"device": "r1", "ref": "alert", "named_in": "the rationale"}]


def test_a_device_of_the_network_never_sent_is_not_demanded():
    """Decision 7c: a device the network holds but the call never sent (its id in no part of
    the topology sent, and nothing of it in the pack) is not one the answer could cite."""
    names = dict(NAMES, r99="dev:u99999999")
    a = _citing(R7_ALERT, R6_HEARTBEAT, S2_SCRAPES, S4_ALERT)
    a["rationale"] += " r99 is far from it."
    assert _check(a, names=names) == ""
    assert explain.sent_names(names, IDS) == NAMES
    assert explain.sent_names(names, IDS + ["dev:u99999999"]) == names


def test_a_device_named_but_never_sent_is_not_demanded_through_explain(world, monkeypatch):  # noqa: F811
    """Through `explain_pack`: the world's network holds r2, but the topology sent holds r1
    alone and the pack names r1 alone, so naming r2 is not refused."""
    from tests.test_ai_explain import _answer, _explain
    world.answer = _answer(world.pack, rationale="r1 and r2 both logged errors.")
    got = _explain(world)
    assert got["ok"] is True, got
    assert got["answer"]["mercury_cites"] == []


ADJ = "adj:ospf:dev:u342aff19~dev:uc038a8be:10.255.3.0/24"
ADJ_SWAPPED = "adj:ospf:dev:uc038a8be~dev:u342aff19:10.255.3.0/24"
ADJ6 = "adj:ospfv3:dev:u342aff19~dev:uc038a8be:2001:db8:3::/64"
ADJ6_SWAPPED = "adj:ospfv3:dev:uc038a8be~dev:u342aff19:2001:db8:3::/64"


@pytest.mark.parametrize("written,known,read", [
    (ADJ_SWAPPED, IDS, ADJ), (ADJ, IDS, ADJ), ("topology:link:10.255.3.0/24", IDS,
                                               "link:10.255.3.0/24"),
    ("topology:" + ADJ_SWAPPED, IDS, ADJ), (ADJ6_SWAPPED, [ADJ6], ADJ6),
    ("topology:link:2001:db8:2:a::/64", IDS, "link:2001:db8:2:a::/64"),
    # Never a near id: another subnet, another protocol, or an id the topology did not send.
    ("adj:ospf:dev:uc038a8be~dev:u342aff19:10.255.9.0/24", IDS, ""),
    ("adj:ospfv3:dev:uc038a8be~dev:u342aff19:10.255.3.0/24", IDS, ""),
    (ADJ_SWAPPED, (), ""), ("topology:", IDS, ""), ("link:10.255.3.0", IDS, "")])
def test_an_adjacency_s_ends_and_a_topology_prefix_are_read_as_the_id_sent(written, known, read):
    """Decision 7b (the failure analysis's 5 swapped adjacencies and one `topology:` prefix):
    an adjacency with its ends in the other order, or a topology id with ``topology:`` before
    it, is the id the topology sent, IPv4 and IPv6; nothing else is."""
    assert explain.as_topology_id(written, known) == read


def test_a_swapped_adjacency_is_accepted_and_drawn_as_written():
    """Through the check: the answer citing the adjacency with its ends swapped and a link with
    the prefix is refused as written, and accepted once read as the ids sent, the model's words
    kept beside each."""
    a = _citing(R7_ALERT, R6_HEARTBEAT, S2_SCRAPES, S4_ALERT, ADJ_SWAPPED,
                "topology:link:10.255.3.0/24")
    assert "cites 'adj:ospf:dev:uc038a8be~dev:u342aff19:" in _check(a)
    model, written = explain.normalised(_model(a), {"sections": SENT}, IDS)
    assert explain.check(model, PACK, IDS, sections=SENT, names=NAMES) == ""
    assert written == {ADJ: ADJ_SWAPPED, "link:10.255.3.0/24": "topology:link:10.255.3.0/24"}
    assert model.hypotheses[0].evidence_refs[-2:] == [ADJ, "link:10.255.3.0/24"]
    assert a["hypotheses"][0]["evidence_refs"][-2:] == [ADJ_SWAPPED, "topology:link:10.255.3.0/24"]


def test_mercury_s_citation_is_kept_recorded_and_drawn_as_mercury_s(world, monkeypatch):  # noqa: F811
    """Through `explain_pack` and the card: an answer naming the alert's device r1 and citing
    only the other alerts' section is shown, Mercury citing r1 by the alert; the hypothesis's
    citations are the model's alone; the use's record says what Mercury cited; the answer kept
    with the pack holds both; the card draws it under "cited by Mercury", never among the
    hypothesis's citations."""
    from html import unescape

    from modules.ai import calls, explain_answers
    from tests.test_ai_explain import _answer, _explain
    used = []
    real = calls.record_use

    def record(cid, use, **kw):
        used.append((use, kw))
        return real(cid, use, **kw)
    monkeypatch.setattr(calls, "record_use", record)
    a = _answer(world.pack)
    a["hypotheses"][0]["evidence_refs"] = ["concurrent"]
    world.answer = a
    got = _explain(world)
    assert got["ok"] is True, got
    assert got["answer"]["mercury_cites"] == [
        {"device": "r1", "ref": "alert", "in_pack": True, "named_in": "hypothesis 1"}]
    assert [c["ref"] for c in got["answer"]["hypotheses"][0]["cites"]] == ["concurrent"]
    assert used[-1][1].get("detail") == "cited by Mercury: r1 by the pack's alert"
    r = world.lab["client"].post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
                                 headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200
    mine = re.search(r'<p class="muted small explain-mercury-cites".*?</p>', html, re.S)
    assert mine, html
    assert "cited by Mercury" in mine.group(0)
    assert "r1, named in hypothesis 1: the pack's" in mine.group(0)
    assert f'href="#{world.pack["id"]}-alert"' in mine.group(0)
    hyp = re.search(r'<ol class="explain-list">.*?</ol>', html, re.S).group(0)
    assert 'data-ref="concurrent"' in hyp and 'data-ref="alert"' not in hyp
    kept = explain_answers.kept(world.pack)["answer"]["result"]["answer"]
    assert kept["mercury_cites"][0]["ref"] == "alert"
    assert [c["ref"] for c in kept["hypotheses"][0]["cites"]] == ["concurrent"]
