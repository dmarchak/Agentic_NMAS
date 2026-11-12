"""Self-healing in plain words: the decision's words (`decide._outcome`, `heal.said`), the
cause it names where Mercury holds both ends of one (C2823), and the operator's three card
templates (C2817; ~/Documents/nmas-reports/2026-11-08T2000Z-human-readable-mocks.md, "right as
drawn", 2026-11-09): the Tier 2 proposal's card, the Tier 1 dry-run record with its marks
drawn on its control (C2809) and the Tier 3 can't-fix with its likeliest cause; times in the
viewer's zone, UTC on hover (MERCURY_CHARTER, "Human-facing means human-readable", rules 1 to
5). On test_heal_decide's lab (Default marked lab, dry run): no device, no network.

**The cause, never a guess** (`said.cause_of`): the facts in time order (the change, who made
it and what it changed; each symptom), then a hypothesis labelled as one only where both ends
are held: a change on interface X and a symptom on X after it (an ACL applied there that the
same change defines and that permits no OSPF is a fact too: H11 W7), or a router-id the
change set that a duplicate router-id report names (W5). A symptom on another interface, or
before the change, links nothing. Each case IPv4 and IPv6.
"""

import re
import time

import pytest

from tests.test_heal_decide import GOLDEN, PLATFORM, ROUTE4, T0, Fake, changed, settle
from tests.test_heal_decide import lab  # noqa: F401  (the fixture, named by each test below)
from tests.test_heal_policy import iso
from tests.test_heal_propose import R8, REASON, measured, proposed  # noqa: F401
from tests.test_heal_proposal_v2 import _base, _card, _hidden, app_client  # noqa: F401
from tests.test_heal_triggers import _Lazy
from tests.test_heal_triggers import world  # noqa: F401  (the fixture, named below)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

S, K, DC, DS, SL = (_Lazy("said"), _Lazy("kinds"), _Lazy("decide"), _Lazy("decisions"),
                    _Lazy("steplog"))
HX = {"HX-Request": "true"}
GI2 = "interface GigabitEthernet2\n description to leaf\n ip address 192.0.2.13 255.255.255.252\n"
#: W7's change: an inbound ACL added on Gi2 whose entries permit no OSPF.
ACL4 = ("ip access-list extended EDGE-IN\n deny tcp any any eq 22\n permit tcp any any\n"
        " permit udp any any\n")
ACL4_OSPF = "ip access-list extended EDGE-IN\n permit ospf any any\n deny ip any any\n"
ACL6 = "ipv6 access-list EDGE6-IN\n deny tcp any any eq 22\n permit tcp any any\n"
CHANGE = {"kind": "config_change", "epoch": T0 - 40, "at": iso(T0 - 40),
          "person": {"user": "lab", "words": "the line names the account lab on vty0"},
          "words": "CONFIG_I"}


def units(running):
    c = K.classify(GOLDEN, running, GOLDEN, platform=PLATFORM, mgmt_ip="192.0.2.6")
    return [K.masked_unit(u) for u in c["units"]]


def dropped(port, *, at=T0, protocol="OSPF", neighbor="192.0.2.14", peer="r4"):
    """A logged adjacency drop as the adjacency-log step keeps it (C2823's fields)."""
    return {"kind": "adjacency_log", "epoch": at, "at": iso(at), "protocol": protocol,
            "port": port, "neighbor": neighbor, "peer": peer, "logged_by": "edge-b",
            "reason": "Dead timer expired", "related": [peer],
            "words": f"edge-b logged its {protocol} adjacency to {neighbor} ({peer}) down"}


def cause(running, *triggers):
    return S.cause_of([CHANGE, *triggers], {"device": "edge-b", "units": units(running)})


# ── The cause (C2823) ──────────────────────────────────────────────────────────────────────

class TestTheCause:
    def test_w7_an_acl_that_drops_ospf_on_the_port_the_adjacency_was_lost_on(self):
        got = cause(changed((GI2, GI2 + " ip access-group EDGE-IN in\n")) + ACL4,
                    dropped("Gi2"))
        texts = [f["text"] for f in got["facts"]]
        assert texts[0].startswith("edge-b's configuration was changed outside Mercury (the "
                                   "line names the account lab on vty0): ")
        assert "“ip access-group EDGE-IN in” was added to interface GigabitEthernet2" in texts[0]
        assert texts[1] == ("edge-b lost its OSPF neighbour r4 (192.0.2.14) on Gi2: Dead timer "
                            "expired")
        assert texts[2] == ("the ACL EDGE-IN, applied inbound on GigabitEthernet2, permits no "
                            "OSPF: none of its 3 entries does, and an ACL drops what it does "
                            "not permit")
        assert got["hypothesis"] == {
            "label": "Likely cause (a hypothesis, not checked)", "at": iso(T0),
            "text": ("this ACL drops OSPF on GigabitEthernet2, so edge-b lost its OSPF "
                     "neighbour r4 (192.0.2.14) on Gi2: Dead timer expired")}

    def test_w7_in_ipv6_a_traffic_filter_that_drops_ospfv3(self):
        got = cause(changed((GI2, GI2 + " ipv6 traffic-filter EDGE6-IN in\n")) + ACL6,
                    dropped("GigabitEthernet2", protocol="OSPFv3", neighbor="2001:db8::4"))
        assert got["hypothesis"]["text"].startswith("this ACL drops OSPF on GigabitEthernet2, "
                                                    "so edge-b lost its OSPFv3 neighbour r4 "
                                                    "(2001:db8::4)")
        assert any(f["text"].startswith("the ACL EDGE6-IN, applied inbound") for f in
                   got["facts"])

    @pytest.mark.parametrize("acl,proto,nbr", [
        (ACL4_OSPF, "ip access-group", "192.0.2.14"),
        ("ipv6 access-list EDGE6-IN\n permit 89 any any\n", "ipv6 traffic-filter",
         "2001:db8::4")], ids=("ipv4", "ipv6"))
    def test_an_acl_that_permits_ospf_is_no_acl_fact_only_the_port_s_link(self, acl, proto,
                                                                         nbr):
        name = "EDGE-IN" if proto.startswith("ip ") else "EDGE6-IN"
        got = cause(changed((GI2, GI2 + f" {proto} {name} in\n")) + acl,
                    dropped("Gi2", neighbor=nbr))
        assert not any(f["text"].startswith("the ACL") for f in got["facts"])
        assert got["hypothesis"]["text"].startswith("the change on GigabitEthernet2 broke what "
                                                    "was lost on it: edge-b lost its OSPF")

    @pytest.mark.parametrize("nbr", ["192.0.2.14", "2001:db8::4"], ids=("ipv4", "ipv6"))
    def test_w6_a_key_on_one_end_of_gi4_and_gi4_s_adjacency_down(self, nbr):
        gi4 = (" description to core\n ip address 192.0.2.9 255.255.255.252\n ip ospf cost 10\n")
        got = cause(changed((gi4, gi4 + " ip ospf message-digest-key 1 md5 7 0822455D0A16\n")),
                    dropped("GigabitEthernet4", neighbor=nbr))
        assert got["hypothesis"]["text"].startswith("the change on GigabitEthernet4 broke")

    @pytest.mark.parametrize("trigger", [
        dropped("Gi4"),                                    # another interface
        dropped("Gi2", at=T0 - 100),                       # before the change
        dropped("", neighbor="2001:db8::4"),               # no interface named
    ], ids=("another-port", "before-the-change", "no-port"))
    def test_never_a_guess(self, trigger):
        got = cause(changed((GI2, GI2 + " ip access-group EDGE-IN in\n")) + ACL4, trigger)
        assert got["hypothesis"] is None, got
        assert len(got["facts"]) == 2, "the facts are still said"

    @pytest.mark.parametrize("rid,new", [("192.0.2.99", " router-id 192.0.2.99\n")],
                             ids=("ipv4",))
    def test_w5_a_router_id_a_duplicate_report_names(self, rid, new):
        dup = {"kind": "duplicate_router_id", "epoch": T0, "at": iso(T0), "protocol": "OSPF",
               "router_id": rid, "related": ["r4"],
               "words": f"edge-b logged a duplicate OSPF router-id {rid} since {iso(T0)}"}
        got = cause(changed((" router-id 192.0.2.6\n", new)), dup)
        assert got["facts"][1]["text"] == f"edge-b logged a duplicate OSPF router-id {rid}"
        assert got["hypothesis"]["text"] == (f"edge-b's router-id is now {rid}, which r4 also "
                                             "uses: two routers with one router-id cannot peer")

    @pytest.mark.parametrize("protocol", ["OSPF", "OSPFv3"])
    def test_a_duplicate_of_another_router_id_links_nothing(self, protocol):
        """A router-id is a dotted 32-bit number for OSPFv3 too; a report naming another id
        than the one the change set is no link."""
        dup = {"kind": "duplicate_router_id", "epoch": T0, "at": iso(T0), "protocol": protocol,
               "router_id": "192.0.2.77", "related": ["r4"],
               "words": f"edge-b logged a duplicate {protocol} router-id 192.0.2.77"}
        got = cause(changed((" router-id 192.0.2.6\n", " router-id 192.0.2.99\n")), dup)
        assert got["hypothesis"] is None and len(got["facts"]) == 2, got

    def test_the_sentence_says_the_facts_first_at_their_times_then_the_hypothesis(self):
        got = cause(changed((GI2, GI2 + " ip access-group EDGE-IN in\n")) + ACL4,
                    dropped("Gi2"))
        said = S.sentence(got)
        t1, t2 = time.strftime("%H:%M", time.gmtime(T0 - 40)), time.strftime(
            "%H:%M", time.gmtime(T0))
        assert said.startswith(f"At {t1} UTC, edge-b's configuration was changed")
        assert said.index(f"At {t2} UTC, edge-b lost") < said.index(
            "Likely cause (a hypothesis, not checked): this ACL drops OSPF")

    def test_a_device_s_name_keeps_its_case_where_a_sentence_starts(self):
        """A device's name is a label (CLAUDE.md: "its name a label"): never capitalised to
        start a sentence; "the ACL …" is."""
        said = S.sentence({"facts": [
            {"text": "edge-b differs from its approved configuration", "at": "", "epoch": 0.0},
            {"text": "the ACL EDGE-IN permits no OSPF", "at": "", "epoch": 0.0}],
            "hypothesis": None})
        assert said == ("edge-b differs from its approved configuration. The ACL EDGE-IN "
                        "permits no OSPF.")

    def test_nothing_held_is_no_cause(self):
        assert S.cause_of([], {"device": "edge-b", "units": []}) is None

    @pytest.mark.parametrize("neighbor,peer", [("192.0.2.9", "core-b"),
                                               ("2001:db8:0:7::2", "v6-d")],
                             ids=("ipv4", "ipv6"))
    def test_a_logged_drop_keeps_its_port_neighbour_and_reason(self, world, neighbor, peer):
        """C2823: the adjacency-log step keeps the drop's own facts on its trigger, the port as
        ``port`` (never ``interface``: a logged drop is not a link's symptom, `decide._symptom`)."""
        from tests.test_heal_triggers import T, opened
        value = {"adjacencies": {f"Default|leaf-c|OSPF|{neighbor}": {
            "list": "Default", "device": "leaf-c", "protocol": "OSPF", "neighbor": neighbor,
            "interface": "GigabitEthernet2", "drops": [{"at": iso(T0), "epoch": T0,
                                                        "reason": "Dead timer expired"}]}}}
        assert T.from_adjacency_log("adjacency-log", value, now=T0, planned=[],
                                    receipts=lambda n, d: [])["sighted"] == 2
        (inc,) = opened()
        (t,) = [t for t in inc["triggers"] if t["kind"] == "adjacency_log"][:1]
        assert {k: t[k] for k in ("port", "neighbor", "peer", "logged_by", "reason")} == {
            "port": "GigabitEthernet2", "neighbor": neighbor, "peer": peer,
            "logged_by": "leaf-c", "reason": "Dead timer expired"}
        assert "interface" not in t
        assert S.symptom_words(t, "leaf-c") == (f"leaf-c lost its OSPF neighbour {peer} "
                                                f"({neighbor}) on GigabitEthernet2: Dead timer "
                                                "expired")


# ── The decision's words (`decide._outcome`, the survey's item 3) ──────────────────────────

#: What no decision's words hold (rule 3): a fix kind's key, the mode's key, AUTO, a guard.
INTERNAL = re.compile(r"\b(missing_line|changed_line|added_line|process_reset|security_acl|"
                      r"dry_run|AUTO|[Gg]uard \d+)\b")


class TestTheDecisionsWords:
    def test_w7_end_to_end_the_decision_states_its_cause_first(self, lab):
        running = changed((GI2, GI2 + " ip access-group EDGE-IN in\n")) + ACL4
        inc = settle(running, triggers=[dict(CHANGE, key="cfg:w7"),
                                        dict(dropped("Gi2"), key="adjlog:w7")])
        d = DC.decide_one("Default", inc, now=T0, sources=Fake(running))
        assert d["outcome"] == "cant_fix" and d["cause"]["hypothesis"], d["words"]
        assert d["words"].startswith(f"At {time.strftime('%H:%M', time.gmtime(T0 - 40))} UTC, "
                                     "edge-b's configuration was changed outside Mercury")
        assert "Likely cause (a hypothesis, not checked): this ACL drops OSPF on " \
               "GigabitEthernet2" in d["words"]
        assert d["words"].endswith(d["outcome_words"]) and not INTERNAL.search(d["words"])
        # C2822: the ACL and its access-group are one unit, a security ACL (Tier 2, C2839) not
        # fixed until its removal shape is measured; no guard stops it, and its kind and tier
        # are the record's own fields, never its words.
        assert d["guard"] is None and (d["kind"], d["tier"]) == ("security_acl", 2), d
        assert [u["joined"] for u in d["units"]] == [2]

    @pytest.mark.parametrize("running,outcome", [
        (GOLDEN + ROUTE4, "would_heal"), (R8, "propose"),
        (GOLDEN + "access-list 101 permit ip any any\n", "cant_fix")],
        ids=("tier-1", "tier-2", "tier-4"))
    def test_plain_words_name_no_internal_key(self, lab, running, outcome):
        d = DC.decide_one("Default", settle(running), now=T0, sources=Fake(running))
        assert d["outcome"] == outcome, d["words"]
        assert not INTERNAL.search(d["words"]), d["words"]
        assert not INTERNAL.search(d["headline"]), d["headline"]
        assert re.search(r"\(Tier \d\)$", d["outcome_words"]), "the tier a label after them"
        for s in d["steps"]:
            assert not re.search(r"\bhi-[0-9a-f]{6,}|[0-9a-f]{12,}", s["words"]), s

    def test_the_proposal_says_what_the_fix_does_and_who_decides(self, lab):
        d = DC.decide_one("Default", settle(R8), now=T0, sources=Fake(R8))
        assert d["outcome_words"] == (
            "Mercury proposes a fix: set “router-id 192.0.2.99” back to “router-id 192.0.2.6” "
            "in router ospf 1, then restart OSPF on edge-b, which briefly drops all of edge-b's "
            "OSPF neighbours, so a person decides when. Nothing is sent until a person approves "
            "it (Tier 2)")
        assert d["headline"].endswith("Mercury has a fix that restarts OSPF on edge-b: it needs "
                                      "your decision")


# ── The likeliest cause on another device (C2817's amendment) ──────────────────────────────

def _inc(device, *triggers, state="standing"):
    return {"id": f"hi-{device}", "device": device, "state": state, "triggers": list(triggers)}


def _cfg(at, user="lab"):
    return {"kind": "config_change", "epoch": at, "at": iso(at),
            "person": {"words": f"the line names the account {user} on vty0"}}


def _alert(at, related=()):
    return {"kind": "alert", "epoch": at, "at": iso(at), "rule": "IP SLA probe failing",
            "related": list(related), "words": "the alert IP SLA probe failing fired on r1"}


class TestTheLikeliestCauseElsewhere:
    def test_w4_the_only_other_change_minutes_before_is_named(self):
        r1 = _inc("r1", _alert(T0))
        got = S.likely_elsewhere(r1, [r1, _inc("r4", _cfg(T0 - 180))])
        assert got == {"device": "r4", "at": iso(T0 - 180), "epoch": T0 - 180,
                       "words": "the line names the account lab on vty0"}

    def test_one_the_symptom_names_wins_over_others(self):
        r1 = _inc("r1", _alert(T0, related=["r6"]))
        got = S.likely_elsewhere(r1, [r1, _inc("r4", _cfg(T0 - 60)), _inc("r6", _cfg(T0 - 300))])
        assert got["device"] == "r6"

    @pytest.mark.parametrize("others", [
        [_inc("r4", _cfg(T0 - 60)), _inc("r6", _cfg(T0 - 120))],      # two, neither named
        [_inc("r4", _cfg(T0 - 601))],                       # too long before (LIKELY_S, 600)
        [_inc("r4", _cfg(T0 + 5))],                                    # after the symptom
        [_inc("r4", _cfg(T0 - 60), state="closed")],                   # fixed already
    ], ids=("two-unnamed", "too-early", "after", "closed"))
    def test_none_rather_than_a_guess(self, others):
        r1 = _inc("r1", _alert(T0))
        assert S.likely_elsewhere(r1, [r1, *others]) is None


# ── The three cards (C2817) ────────────────────────────────────────────────────────────────

class TestTheProposalCard:
    def test_the_four_questions_in_order_and_the_record_collapsed(self, app_client, measured):
        d = proposed()
        base = f"/v2/network/Default/heal/proposal/{d['id']}"
        html = app_client.get(base, headers=HX).get_data(as_text=True)
        order = [html.index(w) for w in (
            "<strong>What happened.</strong>", "<strong>Does it need you? Yes.</strong>",
            "<strong>The fix Mercury proposes.</strong>", "<strong>What it affects.</strong>",
            "<strong>How Mercury checks it worked.</strong>", "<strong>If you don't.</strong>",
            ">Approve and run on edge-b<", ">Decline<", ">Show the commands</summary>",
            "<summary>Details for the record</summary>")]
        assert order == sorted(order), order
        record = html.split("<summary>Details for the record</summary>")[1]
        main = re.sub(r"<[^>]+>", " ", html.split("<summary>Details for the record</summary>")[0])
        v = DS.find("Default", d["id"])
        assert v["program_hash"] in record and v["program_hash"] not in main
        assert d["id"] in record and d["id"] not in main, "drawn only for the record"
        assert "Watching only on Default (dry run)" in main and "Approving this sends it" in main
        # What the notice says is what happens: Approve, pressed with the hash the record holds
        # and no reason, starts the heal bound to it.
        r = app_client.post(base + "/approve", data={"hash": _hidden(html, "hash")},
                            headers=HX)
        try:
            assert r.status_code == 200 and "You approved it." in r.get_data(as_text=True)
            (approval,) = app_client.started
            assert approval["hash"] in record
            assert DS.find("Default", d["id"])["taken"]["by"].endswith(": approved")
        finally:
            from tests.test_heal_propose import INT
            INT.release("Default", d["id"])

    def test_a_check_not_built_is_can_t_tell_never_a_pass(self, app_client, measured):
        from modules.heal import propose
        d = proposed()
        rec = DS.find("Default", d["id"])
        held = S.cause_of([CHANGE, dropped("Gi2")], rec)
        # A symptom the act reads again is checked; one of a kind it does not (none of today's
        # triggers, so planted) is "can't tell".
        held["facts"].append({"text": "r7's telemetry streams were lost", "at": iso(T0),
                              "epoch": T0, "kind": "telemetry"})
        plain = propose._plain(dict(rec, cause=held), "edge-b", None)
        assert ("edge-b lost its OSPF neighbour r4 (192.0.2.14) on Gi2: Dead timer expired: "
                "read again once edge-b is released", "checked") in plain["checks"]
        assert ("r7's telemetry streams were lost: Mercury does not read this again yet",
                "cant_tell") in plain["checks"]
        assert plain["checks"][0][1] == "checked"

    def test_approve_needs_no_reason_and_decline_does(self, app_client, measured):
        d = proposed()
        _r, html = _card(app_client, d)
        assert 'placeholder="optional to approve, needed to decline' in html
        r = app_client.post(_base(d) + "/decline", data={"reason": ""}, headers=HX)
        assert r.status_code == 409 and "needs a reason" in r.get_data(as_text=True)
        r = app_client.post(_base(d) + "/approve", data={"hash": _hidden(html, "hash"),
                                                         "reason": ""}, headers=HX)
        try:
            assert r.status_code == 200, r.get_data(as_text=True)[:400]
            (approval,) = app_client.started
            assert approval["reason"] == "" and approval["hash"] == _hidden(html, "hash")
        finally:
            from tests.test_heal_propose import INT
            INT.release("Default", d["id"])

    def test_a_line_that_needs_a_reason_still_needs_one(self, lab, measured, monkeypatch):
        from modules.heal import propose
        from tests.test_heal_propose import FakeApproved
        d = proposed()
        real = propose.view
        monkeypatch.setattr(propose, "view", lambda *a, **k: dict(real(*a, **k),
                                                                   reason_needed=True))
        src = FakeApproved(R8)
        with pytest.raises(propose.Refused, match="needs a reason of 3 words"):
            propose.approve("Default", d["id"],
                            confirmed_hash=real("Default", d["id"], sources=src)["hash"],
                            reason="", actor="op@example.com", actor_verified="access",
                            person=True, sources=src)
        assert [x["id"] for x in DS.proposals("Default")] == [d["id"]], "nothing taken"


def _dry_run():
    inc = settle(GOLDEN + ROUTE4)
    made = DC.decide_one("Default", inc, now=T0, sources=Fake(GOLDEN + ROUTE4))
    steps, phase = made.pop("steps", []), made.pop("phase", "decide")
    # Recorded now, so Needs attention's window (`decisions.MARK_DAYS`) holds it.
    d = DS.record("Default", made, time.time())
    SL.record_decision("Default", dict(d, steps=steps, phase=phase), time.time())
    return d


class TestTheDryRunRecord:
    def test_its_row_says_what_happened_and_carries_its_marks(self, app_client, monkeypatch):
        from modules import attention
        d = _dry_run()
        monkeypatch.setattr(attention, "SOURCES", [attention.heal_source])
        html = app_client.get("/v2/attention?list=Default").get_data(as_text=True)
        row = html.split(f'data-attention-row="heal:{d["id"]}"')[1]
        assert ("edge-b: “ip route 192.0.2.128 255.255.255.128 192.0.2.10” was added to the "
                "global configuration. Mercury would have put it back itself, but Default is "
                "watching only (dry run), so nothing was sent") in row
        assert f'data-next-acts="heal_mark" href="#heal-mark-{d["id"]}">Was that right?</a>' in row
        assert f'id="heal-mark-{d["id"]}"' in row and "History" not in row.split(
            "<h3>Why this happened</h3>")[0].split("<h3>What to do</h3>")[1].split(
            "Was this the right fix?")[0]
        # Right, pressed where it is drawn, records the mark and the row leaves.
        url = re.search(r'hx-post="([^"]+)" hx-vals=\'{"right": "yes"}\'', row).group(1)
        assert app_client.post(url, data={"right": "yes"}, headers=HX).status_code == 200
        assert DS.find("Default", d["id"])["mark"]["right"] is True
        again = app_client.get("/v2/attention?list=Default").get_data(as_text=True)
        assert f'data-attention-row="heal:{d["id"]}"' not in again

    def test_c2809_a_mark_drawn_again_is_drawn_on_its_control(self, app_client):
        from modules import history_sources as HS
        from tests.test_heal_mark_and_held import _ctx, _timeline
        d = _dry_run()
        assert app_client.post(f"/v2/network/Default/heal/decision/{d['id']}/mark",
                               data={"right": "yes"}, headers=HX).status_code == 200
        (e,) = HS.heal(_ctx())["events"]
        card = _timeline(e).split(f'id="heal-mark-{d["id"]}"')[1].split("</div>\n</div>")[0]
        right = re.search(r'<button type="button"[^>]*"right": "yes"[^>]*>', card).group(0)
        assert 'aria-pressed="true"' in right
        wrong = re.search(r'<summary class="btn btn-small btn-outline"[^>]*>', card).group(0)
        assert 'aria-pressed="false"' in wrong
        mark = DS.find("Default", d["id"])["mark"]
        # Board E2a: who marked it, by display name (the part before the "@"); the mark's
        # record keeps the identity.
        assert "@" in mark["by"]
        assert (f'Marked right by {mark["by"].split("@")[0]} at <time class="clock" '
                f'datetime="{mark["at"]}" '
                f'data-clock title="{mark["at"][:19].replace("T", " ")} UTC">') in card
        assert "Marked again" not in card

    def test_its_history_record_is_collapsed_and_its_cause_drawn_first(self, lab):
        from modules import history_sources as HS
        from tests.test_heal_mark_and_held import _ctx, _timeline
        _dry_run()
        (e,) = HS.heal(_ctx())["events"]
        html = _timeline(e)
        assert e["what"].startswith("edge-b: “ip route") and e["record_closed"]
        detail = html.split('class="hist-detail tl-more">')[1]
        assert detail.index("heal-facts") < detail.index("Mercury would have put it back") \
            < detail.index("<summary>Details for the record</summary>")
        assert '<details class="tl-record-d"' in detail and \
            '<details class="tl-record-d" data-keep="tl-rec-tl-1" open' not in detail


class TestTheCantFix:
    def test_another_device_s_change_leads_labelled_as_a_hypothesis(self, app_client,
                                                                   monkeypatch):
        from modules import attention
        from modules.heal import incidents as I
        alert = {"kind": "alert", "key": "alert:r1", "epoch": T0 - 30, "at": iso(T0 - 30),
                 "source": "grafana-alerts", "rule": "IP SLA probe failing", "interface": "",
                 "words": "the alert IP SLA probe failing fired on edge-b"}
        inc = settle(GOLDEN, triggers=[alert], how="at_golden", claim=False)
        assert DC.run("Default", now=T0, sources=Fake(GOLDEN))["decided"][0]["outcome"] == \
            "cant_fix"
        # Another device changed outside Mercury 170 s before edge-b's symptom, not fixed yet.
        I.sight("Default", "edge-c", dict(_cfg(T0 - 200), key="cfg:c", words="CONFIG_I"),
                now=T0 - 200)
        monkeypatch.setattr(attention, "_page_network", lambda: "Default")
        got = attention.heal_source(now=T0 + 20)
        (r,) = [x for x in got["rows"]
                if x["kind"] == "cant_fix"]
        assert r["likely"]["device"] == "edge-c" and r["event"] == inc["id"]
        # The page and the acknowledgement read at the lab's clock, so the can't-fix's window
        # holds it.
        real = attention.heal_source

        def at_the_lab_s_clock(got=None, now=None, found=None):
            return real(got, now or T0 + 20, found)
        monkeypatch.setattr(attention, "heal_source", at_the_lab_s_clock)
        monkeypatch.setattr(attention, "SOURCES", [at_the_lab_s_clock])
        html = app_client.get("/v2/attention?list=Default").get_data(as_text=True)
        line = html.split(f'data-attention-row="{r["id"]}"')[1].split("</summary>")[0]
        assert ">Open edge-c (likely cause)</a>" in line
        assert "Likely cause (a hypothesis, not checked):</strong> edge-c's configuration was " \
               "changed outside Mercury at <time" in html
        assert "History first" not in html, "rule 5: the steps are drawn in place"
        # Acknowledge…, pressed with the cause, records it and the row leaves.
        url = re.search(r'class="att-ack" x-data="acknowledge" data-url="([^"]+)" data-row="'
                        + re.escape(r["id"]), html).group(1)
        got = app_client.post(url, json={"row": r["id"], "event": r["event"],
                                         "why": "edge-c's static route sent edge-b's probe away"})
        assert got.status_code == 200, got.get_data(as_text=True)
        again = app_client.get("/v2/attention?list=Default").get_data(as_text=True)
        assert f'data-attention-row="{r["id"]}"' not in again


def test_a_time_is_drawn_in_the_viewer_s_zone_with_utc_on_hover():
    # The server's words are the host's zone, named, until the page's script writes the
    # viewer's (`_macros.clock`, routes/v2.clock_words): pinned to a host in Denver.
    from flask import render_template_string
    import app as A
    from tests.test_local_times import zone
    with zone("America/Denver"), A.app.test_request_context("/v2/"):
        got = render_template_string('{% from "v2/_macros.html" import clock %}'
                                     '{{ clock("2026-11-08T19:41:07Z") }}|{{ clock("") }}')
    assert got == ('<time class="clock" datetime="2026-11-08T19:41:07Z" data-clock '
                   'title="2026-11-08 19:41:07 UTC">12:41 MST</time>|'
                   '<span class="clock">at an unrecorded time</span>')
