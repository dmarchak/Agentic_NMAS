"""Diagnose… on the device page (board H's amendment, artboards I and J; part H16 of
docs/HEAL_TO_INTENT.md 19.7; modules/heal/diagnose_page.py, routes/device_v2.py's diagnose
routes, templates/v2/_diagnose.html).

On the fleet's real intent (tests/test_heal_diagnose.py's `fleet`, the nine real configs
compiled by the real model):
- **The choices come from intent:** each intended adjacency offered with its protocols, the
  rest named with why; a device of the network by its intended loopback, or an address checked
  as one address, IPv4 beside IPv6 (refused by name: "can't reach" reads IPv4 forwarding only,
  C2415); a target is never a command.
- **The plan drawn is the plan run:** every read on each device, the private intent the reach
  runbook carries (`_intent`) not handed to the template, and the run bound to the plan's
  fingerprint: a plan that moved is refused naming both, nothing read.
- **The result** of a real diagnosis (H14's run on its real captures, r4 Gi4 shut) drawn as
  artboard J draws it: the ranked hypotheses, each piece of evidence a link to its read's run.
- **Through the routes:** the Actions menu's row, the card, the press as a job announcing
  ``diagnosis``, its card drawing the diagnosis, a refusal drawn in place.
"""

import pytest

from tests import test_heal_diagnose as T
from tests.test_heal_diagnose import world  # noqa: F401 (the fixture)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture world needs)
from tests.test_device_revert_retry_v2 import page  # noqa: F401 (the fixture)
from tests.test_intent_ops import classify, lab  # noqa: F401 (the fixtures page needs)


@pytest.fixture
def sources(monkeypatch):
    """The plan's intent and model are the fleet's, whichever network asks."""
    from modules.heal import diagnose as D
    model, intents = T.fleet()
    monkeypatch.setattr(D, "_sources", lambda network, model_=None, intents_=None:
                        (model, intents))
    return model, intents


def card(host="r3", **args):
    from modules.heal import diagnose_page as P
    return P.card("Default", host, "overview", args)


class TestTheChoices:
    def test_each_intended_adjacency_is_offered_with_its_protocols_and_the_rest_say_why(
            self, sources):
        c = card("r3")
        words = {o["value"]: o["words"] for o in c["options"]}
        assert words["link|r4|Gi4"] == "r4 over Gi4: OSPF, area 0, OSPFv3, area 0 (intent)"
        assert words["bgp|198.51.100.1"] == "198.51.100.1: BGP, AS 65002 (intent)"
        assert words["bgp|2001:db8:51::2"] == "2001:db8:51::2: BGP, AS 65002 (intent)", \
            "an IPv6 BGP neighbour is offered beside the IPv4 one"
        gi1 = [n for n in c["not_offered"] if n["words"] == "r1 over Gi1"]
        assert gi1 and "intent runs no OSPF, OSPFv3 or BGP" in gi1[0]["why"], c["not_offered"]
        assert c["adjacency"] == c["options"][0]["value"], "the first offered is chosen"

    def test_can_t_reach_offers_each_device_by_its_loopback(self, sources):
        c = card("r3", runbook="cant_reach")
        assert {"value": "10.255.1.14", "words": "r4 (Loopback0 10.255.1.14)"} in c["options"]
        assert all(not o["words"].startswith("r3 ") for o in c["options"]), "never itself"
        assert c["plan"]["rows"] == [{"device": "r3", "reads": [
            "ping 10.255.1.11 source Loopback0 repeat 5 timeout 2"], "count": 1}]

    def test_an_address_ipv4_is_planned_and_ipv6_is_refused_by_name(self, sources):
        v4 = card("r3", runbook="cant_reach", address="10.255.1.14")
        assert v4["error"] == "" and v4["plan"]["words"] == "r3 to 10.255.1.14 (r4 Lo0)"
        v6 = card("r3", runbook="cant_reach", address="2001:db8:51::2")
        assert v6["plan"] is None and "IPv6 address" in v6["error"] and \
            "follows IPv4 forwarding only" in v6["error"], v6["error"]
        assert "IPv4 forwarding only" in v6["ipv4_only"], "the card says so before it is asked"

    @pytest.mark.parametrize("address", ["10.255.1.14; show run", "show running-config",
                                         "10.255.1.14 source Gi1", "fe80::1%Gi1", "192.0.2.0/24"])
    def test_a_target_is_one_address_never_a_command(self, address):
        from modules.heal import diagnose_page as P
        target, why = P.target_of("r3", "cant_reach", "", "", address)
        assert target is None and "is not one IPv4 or IPv6 address" in why, (address, why)

    def test_an_adjacency_not_in_the_offered_shape_is_refused(self):
        from modules.heal import diagnose_page as P
        assert P.target_of("r3", "adjacency_down", "show run", "", "") == (
            None, "choose which adjacency")
        assert P.target_of("r3", "nope", "", "", "")[0] is None


class TestThePlanDrawn:
    def test_every_read_on_each_end_and_the_cap(self, sources):
        p = card("r3", adjacency="link|r4|Gi4")["plan"]
        assert [r["device"] for r in p["rows"]] == ["r3", "r4"]
        r3 = p["rows"][0]["reads"]
        assert "show interfaces GigabitEthernet4 (twice, 10 s apart)" in r3
        assert "show ip ospf neighbor GigabitEthernet4 detail" in r3
        assert p["count"] == sum(r["count"] for r in p["rows"]) and p["cap"] == 70

    def test_the_reach_plan_s_private_intent_is_not_carried(self, sources):
        """H15's leftover: the reach plan carries intent's lines under `_intent` for its walk;
        the card draws every field it is handed, so none of them is handed."""
        from modules.heal import diagnose as D
        model, intents = sources
        raw = D.plan("Default", "cant_reach", {"device": "r3", "address": "10.255.1.14"},
                     model=model, intents=intents)
        assert "_intent" in raw, "the premise: the raw plan carries it"
        p = card("r3", runbook="cant_reach", address="10.255.1.14")["plan"]
        assert "_intent" not in p and set(p) == {
            "runbook", "words", "rows", "per_hop", "hops_at_cap", "count", "cap", "worst",
            "outside", "fingerprint"}

    def test_a_plan_that_moved_is_refused_naming_both_and_nothing_is_run(self, sources,
                                                                         monkeypatch):
        from modules.heal import diagnose as D
        from modules.heal import diagnose_page as P
        ran = []
        monkeypatch.setattr(D, "run", lambda *a, **k: ran.append(a) or {})
        shown = card("r3", adjacency="link|r4|Gi4")["plan"]["fingerprint"]
        got = P.start("Default", "r3", "adjacency_down",
                      {"device": "r3", "neighbour": "r4", "interface": "Gi4"}, "0" * 16, "op")
        assert "error" in got and f"{'0' * 16} then, {shown} now" in got["error"], got
        assert ran == [], "nothing was read"


class TestTheResult:
    def test_a_real_diagnosis_is_drawn_ranked_with_each_read_a_link(self, world):
        from modules.heal import diagnose_page as P
        got, _ = T.diagnose(T.with_answer("r4", "show interfaces GigabitEthernet4",
                                          T.SHOW_IF.replace(
            "GigabitEthernet4 is up", "GigabitEthernet4 is administratively down").replace(
            "line protocol is up", "line protocol is down")))
        d = P.result(got)
        first = d["hypotheses"][0]
        assert first["n"] == 1 and first["layer"] == "physical" and first["claim"] == \
            got["hypotheses"][0]["claim"]
        linked = [e for h in d["hypotheses"] for e in h["evidence"] if e["run"]]
        assert linked and all(e["run"] in got["runs"] for e in linked), d["hypotheses"]
        assert any(e["label"] == "r4 show interfaces GigabitEthernet4" for e in linked)
        assert d["chip"].startswith(f"{len(got['hypotheses']) + got['more']} hypothes") and \
            d["chip"].endswith(f"the first {first['strength']}")
        assert d["ruled_out"] and d["steps"][0]["step"] == "plan"
        assert d["runs"] == sorted(set(got["runs"]))

    def test_an_ipv6_command_in_a_reference_keeps_its_colons(self):
        from modules.heal import diagnose_page as P
        ref = "read:20261105T000000000000Z-" + "0" * 32 + ":r3:ping 2001:db8:51::2 repeat 5"
        assert P._read_link(ref) == {"run": "20261105T000000000000Z-" + "0" * 32,
                                     "label": "r3 ping 2001:db8:51::2 repeat 5"}
        assert P._read_link("")["run"] == ""

    def test_no_cause_and_a_refusal_say_so(self):
        from modules.heal import diagnose_page as P
        assert P.result({"state": "done", "hypotheses": []})["chip"] == \
            "no cause found"
        busy = P.result({"state": "busy", "words": "not diagnosed: r4 is in "
                                                              "diagnosis dg-1"})
        assert busy["chip"] == "not diagnosed" and "r4 is in diagnosis" in busy["words"]


RUN = "20261105T000000000000Z-" + "a" * 32
FAKE = {"id": "dg-test", "runbook": "adjacency_down",
        "runbook_words": "adjacency down with both ends at intent", "target": {},
        "incident": "", "actor": "op@example.invalid", "state": "done",
        "words": "1 hypothesis, the first decisive: r2 Gi2 is administratively down",
        "steps": [{"step": "plan", "result": "ok", "words": "planned"}],
        "hypotheses": [{"rule": "admin_down", "layer": "physical", "strength": "decisive",
                        "claim": "r2 Gi2 is administratively down", "rule_out": "Gi2 up",
                        "todo": "", "incomplete": [], "agree": 1,
                        "evidence": [{"read": f"read:{RUN}:r2:show interfaces "
                                              "GigabitEthernet2",
                                      "line": "is administratively down", "intent": "up"}]}],
        "more": 0, "ruled_out": [{"check": "subnet on both"}],
        "not_checked": [{"check": "the MTU across the link", "why": "the df-bit ping did not run"}],
        "commands": 20, "cap": 70, "runs": [RUN], "stopped": "", "devices": ["r2", "r1"],
        "started_at": "2026-11-05T00:00:00Z", "finished_at": "2026-11-05T00:00:40Z",
        "recorded": True}


class TestThroughTheRoutes:
    def test_the_row_the_card_the_job_and_the_diagnosis_in_place(self, page, sources,
                                                                monkeypatch):
        import re

        from modules.heal import diagnose as D
        from modules.nsot import capture_job
        c = page["client"]
        menu = c.get("/v2/device/r2/actions?tab=overview").get_data(as_text=True)
        assert 'hx-get="/v2/device/r2/diagnose?back=overview' in menu and "Diagnose…" in menu
        body = c.get("/v2/device/r2/diagnose?back=overview").get_data(as_text=True)
        assert "Diagnose r2" in body and "r1 over Gi2: OSPF, area 0" in body
        assert "show interfaces GigabitEthernet2 (twice, 10 s apart)" in body
        fp = re.search(r'name="fingerprint" value="([0-9a-f]{16})"', body).group(1)
        ran = []
        monkeypatch.setattr(D, "run", lambda network, runbook, target, actor: ran.append(
            (network, runbook, target)) or dict(FAKE))
        r = c.post("/v2/device/r2/diagnose/run", data={
            "list": "Lab", "back": "overview", "runbook": "adjacency_down",
            "adjacency": "link|r1|Gi2", "fingerprint": fp})
        running = r.get_data(as_text=True)
        assert r.status_code == 200, running[:400]
        assert 'hx-trigger="nmas:diagnosis from:body"' in running
        job = re.search(r"/v2/device/r2/diagnose/job/([0-9a-f]+)", running).group(1)
        assert capture_job.wait(job, 10)
        assert ran == [("Lab", "adjacency_down",
                        {"device": "r2", "neighbour": "r1", "interface": "Gi2"})]
        done = c.get(f"/v2/device/r2/diagnose/job/{job}?back=overview").get_data(as_text=True)
        assert "Diagnosis: adjacency down with both ends at intent, r2 and r1" in done
        assert "r2 Gi2 is administratively down" in done and "1 hypothesis · the first " \
            "decisive" in done
        assert f'href="/v2/show-commands/run/{RUN}?list=Lab"' in done, \
            "the evidence opens its read's run on History › Reads"

    def test_a_moved_plan_and_an_unknown_job_are_drawn_in_place(self, page, sources):
        c = page["client"]
        r = c.post("/v2/device/r2/diagnose/run", data={
            "list": "Lab", "runbook": "adjacency_down", "adjacency": "link|r1|Gi2",
            "fingerprint": "f" * 16})
        assert r.status_code == 409 and "changed since the card was drawn" in \
            r.get_data(as_text=True)
        body = c.get("/v2/device/r2/diagnose/job/" + "0" * 32).get_data(as_text=True)
        assert "holds no diagnosis job" in body

    def test_another_operation_s_job_is_never_drawn_as_a_diagnosis(self, page, monkeypatch):
        """A job of another kind in the same network, its id put in the diagnosis's address:
        its payload is never read as a diagnosis (the reader's calls counted)."""
        from modules.heal import diagnose_page as P
        from modules.nsot import capture_job

        read = []
        monkeypatch.setattr(P, "result", lambda d: read.append(d) or {})
        job = capture_job.start("Lab", "reading r2 for a reload", "op", lambda _j: dict(FAKE),
                                kind="reload preview")
        assert capture_job.wait(job, 10)
        body = page["client"].get(f"/v2/device/r2/diagnose/job/{job}").get_data(as_text=True)
        assert read == [], "another operation's payload was read as a diagnosis"
        assert "holds no diagnosis job" in body and "Diagnosis:" not in body
