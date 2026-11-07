"""Diagnose… on the device page (board H's amendment, artboards I and J; part H16 of
docs/HEAL_TO_INTENT.md 19.7; modules/heal/diagnose_page.py, routes/device_v2.py's diagnose
routes, templates/v2/_diagnose.html).

On the fleet's real intent (tests/test_heal_diagnose.py's `fleet`, the nine real configs
compiled by the real model):
- **The choices come from intent:** each intended adjacency offered with its protocols, the
  rest named with why; a device of the network by its intended loopback, or an address checked
  as one address, IPv4 beside IPv6 (both planned since H18; the card names what the IPv6 form
  does not do, and a link-local address is refused by name); a target is never a command.
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

    def test_an_address_ipv4_and_ipv6_are_planned_and_ipv6_s_limits_said(self, sources):
        v4 = card("r3", runbook="cant_reach", address="10.255.1.14")
        assert v4["error"] == "" and v4["plan"]["words"] == "r3 to 10.255.1.14 (r4 Lo0)"
        v6 = card("r3", runbook="cant_reach", address="2001:db8:51::2")
        assert v6["error"] == "" and v6["plan"]["words"] == "r3 to 2001:db8:51::2 (r5 Gi2)"
        assert "show ipv6 cef" in v6["ipv4_only"] and "link-local" in v6["ipv4_only"] and \
            "IPv6 access lists bound on the path are not read" in v6["ipv4_only"], \
            "the card says what the IPv6 form does not do before it is asked"
        ll = card("r3", runbook="cant_reach", address="fe80::1")
        assert ll["plan"] is None and "is a link-local address" in ll["error"], ll["error"]

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


# ── H16's second part: the other entry points, the busy card, the reopened card, the hops ──

PACK = "tests/fixtures/evidence_pack/walk2_r1_pack.json"


def _pack(**edit):
    """Walk 2's real pack (r1's Device unreachable (SNMP) in Default), edited by *edit*."""
    import json
    with open(PACK, encoding="utf-8") as fh:
        pack = json.load(fh)
    pack.update(edit)
    return pack


def _interface_down(pack):
    """The real pack, its rule Grafana's Interface down (tests/fixtures/grafana/rules_view.json
    names it) and its alert piece's labels carrying the interface as `ifDescr`."""
    for s in pack["sections"]:
        if s["name"] == "alert":
            s["pieces"][0]["labels"] = dict(s["pieces"][0]["labels"],
                                            alertname="Interface down",
                                            ifDescr="GigabitEthernet4")
    pack["rule"] = "Interface down"
    return pack


class TestFromAnAlert:
    def test_device_unreachable_opens_can_t_reach_toward_it(self):
        from modules.heal import diagnose_page as P
        got = P.from_pack(_pack())
        assert (got["device"], got["list"], got["unreachable"]) == ("r1", "Default", True), got
        assert got["words"].startswith("\"Can't reach\" r1, from the device nearest it")

    def test_an_interface_alert_opens_the_adjacency_over_it(self):
        from modules.heal import diagnose_page as P
        got = P.from_pack(_interface_down(_pack(device="r3")))
        assert got["args"] == {"runbook": "adjacency_down", "interface": "GigabitEthernet4"}
        assert not got["unreachable"] and got["device"] == "r3"

    def test_another_alert_opens_the_dialog_on_its_first_choice(self):
        from modules.heal import diagnose_page as P
        got = P.from_pack(_pack(rule="NMAS heartbeat missing: r1"))
        assert got["args"] == {} and not got["unreachable"] and got["device"] == "r1"

    def test_a_pack_naming_no_device_offers_none_and_says_why(self):
        from modules.heal import diagnose_page as P
        got = P.from_pack(_pack(device=""))
        assert got["device"] == "" and got["words"] == "the alert names no device"
        assert P.from_pack(_pack(network=""))["words"] == "r1 is in no network Mercury holds"

    def test_the_interface_hint_chooses_its_adjacency_in_the_short_form(self, sources):
        c = card("r3", interface="GigabitEthernet4")
        assert c["adjacency"] == "link|r4|Gi4" and c["hint"] == "", c["hint"]
        other = card("r3", interface="GigabitEthernet9")
        assert other["adjacency"] == other["options"][0]["value"]
        assert "GigabitEthernet9" in other["hint"] and "the first is chosen" in other["hint"]

    def test_the_neighbour_hint_chooses_the_link_toward_it(self, sources):
        """On a device of the fleet whose intent offers two links or more, the hint chooses
        a link that is not the first offered (so the default could not pass for it)."""
        host, later = next((h, [o for o in card(h)["options"] if o["value"].startswith(
            "link|")][1:]) for h in ("r1", "r2", "r3", "r4", "r6", "s1", "s2")
            if len([o for o in card(h)["options"] if o["value"].startswith("link|")]) > 1)
        want = later[0]["value"]
        far = want.split("|")[1]
        c = card(host, neighbour=far)
        assert c["adjacency"] == want != c["options"][0]["value"] and c["hint"] == "", c

    def test_unreachable_opens_on_the_nearest_neighbour_with_its_loopback(self, sources):
        from modules.heal import diagnose_page as P
        model, _intents = sources
        near = P.nearest(model, "r4")
        assert near and "r4" not in near and near == sorted(near)
        got = P.unreachable("Default", "r4")
        assert got["host"] == near[0] and got["args"] == {"runbook": "cant_reach",
                                                          "to": "10.255.1.14"}, got


class TestFromACantFixRow:
    @pytest.mark.parametrize("triggers, want", [
        ([{"kind": "alert", "rule": "Interface down", "interface": "GigabitEthernet4"}],
         {"runbook": "adjacency_down", "interface": "GigabitEthernet4"}),
        ([{"kind": "adjacency", "related": ["r4"]}],
         {"runbook": "adjacency_down", "neighbour": "r4"}),
        ([{"kind": "drift"}], {})])
    def test_from_the_incident_s_first_trigger(self, triggers, want):
        from modules.heal import diagnose_page as P
        got = P.from_incident("Default", {"device": "r3", "triggers": ["its words"]},
                              triggers)
        assert got["args"] == want and got["device"] == "r3"

    def test_an_unreachable_alert_is_can_t_reach_and_words_alone_open_the_dialog(self):
        from modules.heal import diagnose_page as P
        got = P.from_incident("Default", {"device": "r3"}, [
            {"kind": "alert", "rule": "Device unreachable (SNMP)", "interface": ""}])
        assert got["unreachable"] is True
        plain = P.from_incident("Default", {"device": "r3", "triggers": ["the alert fired"]})
        assert plain["args"] == {} and plain["device"] == "r3", \
            "the step log keeps only the triggers' words: never read as a target"


class TestTheBusyCard:
    def test_a_device_in_a_diagnosis_is_named_in_place_of_run(self, sources, tmp_path,
                                                              monkeypatch):
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        from modules.heal import diagnose as D
        with D.DiagnosisLock("Default", ["r4"], "dg-held", "op@example.invalid"):
            c = card("r3", adjacency="link|r4|Gi4")
        assert [(b["host"], b["diagnosis"], b["actor"]) for b in c["busy"]] == [
            ("r4", "dg-held", "op@example.invalid")]
        assert card("r3", adjacency="link|r4|Gi4")["busy"] == [], "released: Run is offered"

    def test_the_route_draws_it_and_re_reads_when_a_diagnosis_ends(self, page, sources,
                                                                   tmp_path, monkeypatch):
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        from modules.heal import diagnose as D
        c = page["client"]
        with D.DiagnosisLock("Lab", ["r1"], "dg-held", "op@example.invalid"):
            body = c.get("/v2/device/r2/diagnose?back=overview&list=Lab").get_data(as_text=True)
            held = D.in_diagnosis("Lab", ["r1"])
            assert held["r1"]["diagnosis"] == "dg-held", "the card's read took nothing"
        assert f"r1 is in diagnosis {held['r1']['diagnosis']}" in body
        assert 'name="fingerprint"' not in body
        assert 'hx-trigger="nmas:diagnosis from:body"' in body
        free = c.get("/v2/device/r2/diagnose?back=overview&list=Lab").get_data(as_text=True)
        assert 'name="fingerprint"' in free and "is in diagnosis" not in free


class TestTheRoutesOfTheSecondPart:
    def test_unreachable_redirects_to_the_neighbour_s_dialog(self, page, sources):
        from modules.heal import diagnose_page as P
        r = page["client"].get("/v2/device/r2/diagnose/unreachable?list=Lab")
        assert r.status_code == 302, r.status_code
        to = P.unreachable("Lab", "r2")
        assert (to["host"], to["args"]) == ("r1", {"runbook": "cant_reach", "to": "10.255.1.12"})
        location = r.headers["Location"]
        assert location == (f"/v2/device/{to['host']}?list=Lab&op=diagnose"
                            f"&runbook=cant_reach&to={to['args']['to']}"), location

    def test_the_page_carries_the_hint_and_says_when_it_matches_nothing(self, page, sources):
        """The device page's ``op=diagnose`` address carries the alert's interface to the card:
        one intent holds no adjacency over is said on the card, never silently swapped."""
        body = page["client"].get("/v2/device/r2?list=Lab&op=diagnose&runbook=adjacency_down"
                                  "&interface=GigabitEthernet9").get_data(as_text=True)
        want = card("r2", runbook="adjacency_down", interface="GigabitEthernet9")
        assert "names GigabitEthernet9: no adjacency intent holds over it is offered" in \
            want["hint"] and want["hint"] in body
        assert f'value="{want["adjacency"]}" selected' in body, body[:300]

    def test_an_unread_diagnosis_is_reopened_once_and_in_progress_counts_it(
            self, page, sources, monkeypatch):
        import re

        from modules import in_flight
        from modules.heal import diagnose as D
        from modules.nsot import capture_job
        c = page["client"]
        body = c.get("/v2/device/r2/diagnose?back=overview").get_data(as_text=True)
        fp = re.search(r'name="fingerprint" value="([0-9a-f]{16})"', body).group(1)
        monkeypatch.setattr(D, "run", lambda network, runbook, target, actor: dict(FAKE))
        running = c.post("/v2/device/r2/diagnose/run", data={
            "list": "Lab", "back": "overview", "runbook": "adjacency_down",
            "adjacency": "link|r1|Gi2", "fingerprint": fp}).get_data(as_text=True)
        job = re.search(r"/v2/device/r2/diagnose/job/([0-9a-f]+)", running).group(1)
        assert capture_job.wait(job, 10)
        (row,) = [r for r in capture_job.card_jobs() if r["job"] == job]
        assert (row["device"], row["card"]) == ("r2", "diagnose")
        done = in_flight.finished_row(row, "someone-else")
        assert (done["name"], done["level"], done["words"]) == (
            "Diagnose", "ok", "1 hypothesis · the first decisive"), done
        first = c.get("/v2/device/r2?list=Lab").get_data(as_text=True)
        assert "Diagnosis: adjacency down with both ends at intent" in first
        assert "while you were elsewhere" in first
        again = c.get("/v2/device/r2?list=Lab").get_data(as_text=True)
        assert "Diagnosis: adjacency down" not in again, "opened once, the tab is drawn again"


class TestTheHopsDrawn:
    HOPS = [{"n": 0, "device": "r4", "read": "ping 192.0.2.17: sent", "against": "not "
             "interpreted yet (C2414)", "verdict": "not_interpreted"},
            {"n": 1, "device": "r4", "read": "out Gi2 toward r6", "against": "as intent",
             "verdict": "ok"},
            {"n": 2, "device": "r6", "read": "show ip cef: dropped",
             "against": "diverges here: an ACL intent does not hold", "verdict": "diverges"},
            {"n": 3, "device": "r7", "read": "not read: hops after r6 are not read",
             "against": "", "verdict": "unread"}]

    def test_the_chip_names_the_hop_and_the_table_draws_each(self, page, monkeypatch):
        from modules.heal import diagnose_page as P
        from modules.nsot import capture_job
        d = P.result(dict(FAKE, runbook="cant_reach", hops=self.HOPS))
        assert (d["chip"], d["level"]) == ("diverges at r6", "danger")
        assert [h["verdict"] for h in d["hops"]] == [h["verdict"] for h in self.HOPS]
        job = capture_job.start("Lab", "diagnosing r2", "op", lambda _j: dict(
            FAKE, runbook="cant_reach", hops=self.HOPS), kind="diagnosis")
        assert capture_job.wait(job, 10)
        body = page["client"].get(f"/v2/device/r2/diagnose/job/{job}?back=overview"
                                  ).get_data(as_text=True)
        import re
        assert capture_job.get(job)["state"] == "done", "drawing the result ran nothing again"
        stored = P.result(capture_job.get(job)["payload"])
        drawn = re.findall(r"<tr><td>(\d+ · [^<]+)</td>", body)
        assert len(drawn) == len(stored["hops"]) and drawn[2] == "2 · " + \
            stored["hops"][2]["device"], "every hop the job answered is drawn, in order"
        assert "The path, hop by hop" in body and "diverges here: an ACL intent" in body
        assert "not read: hops after r6 are not read" in body and "diverges at r6" in body
        assert ('href="/v2/device/r2?list=Lab&amp;tab=history&amp;kind=diagnoses&amp;'
                'on=2026-11-05">Open in History</a>') in body
