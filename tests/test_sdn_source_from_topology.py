"""A port's detection names its source from the controller's topology, and a person chooses
among the port's hosts when there are several (C2002's two remaining parts; PHASE8_PLAN 17.1
S6 and S8; board SdnResponses revised 2026-10-28 for C2002).

**The data is the Lab 8 walk's own** (2026-10-27, the network "SDN lab"): the floods and the
scan rule's fallback false positives as the walk kept them (tests/fixtures/ai_cases/
sdn_classify/recorded_walk.json, each case's collection rebuilt by
tests/test_sdn_classify_walk_cases.py's `collection_of`), and Ryu 4.34's topology REST read with
that fabric attached (tests/fixtures/sdn/ryu/topology_rest.json: h1 and a host with only a
link-local address on s1 port 1, h2 on s1 port 2, s1 port 3 to s2 port 3, h3 and another
link-local-only host on s2 port 1, h4 on s2 port 2), through the real driver and the SDN reader's
stored read (`topology.stored`), named for the walk's connection, lab-ryu. Every expected value
is read off those files by hand. The minimal edits, each made where it is used: a second host on
s1 port 2 (192.0.2.5, or 2001:db8:8::5 alone), h2 with its IPv4 address taken away, h2 left out.

- **The detection names its source** (`detect.port_source`): the walk's flood on s1 port 2,
  whose flows matched MAC addresses only, names h2 (192.0.2.2) "from the controller's topology:
  the one host on port 2", and so does the scan rule's fallback on the same port; an IPv6-only
  host is named by its IPv6 address, never its link-local one; a host with no address to match
  beside one with an address does not make the port ambiguous. Unnamed, saying why: the flood
  on s2's port 3 (a link), no host, no address to match, several hosts (each named, IPv6 beside
  IPv4), the topology not read now. Flows naming their source are never overridden, and a rule
  given no topology adds nothing (what keeps the recorded cases' rebuilds as they are).
  `observe` reads the stored topology itself.
- **The card and the classifier see it**: the detection piece of the evidence section carries
  ``source_from``; a named source may be proposed by the model; with several, the hosts may be
  named as affected and none may be proposed as the source (a person picks).
- **The picker** (`closed_loop._response_source`, `confirm_source_refusal`, routes/sdn_v2.py):
  several hosts and no choice is refused as a choice to make, naming them; a chosen host builds
  the drop on that address (IPv4 or IPv6, in any spelling), its hash differing from another
  host's, and says it was chosen; a host not on the port is refused naming both; no host to
  choose is refused saying why and never offers a choice; a confirm whose ask names another
  source is refused naming both, nothing sent. On SDN › Responses: the picker lists exactly the
  port's hosts; one host is named with no picker; none draws why and no Preview.
"""
import copy
import json
import re
from html import unescape

import pytest

from modules.sdn import closed_loop as CL
from modules.sdn import detect as D
from modules.sdn import flow_intent as F
from modules.sdn import loop as LP
from modules.sdn import topology as SDN
from tests.test_sdn_classify_walk_cases import collection_of, load as load_walk
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_ops_v2 import form_fields, lab  # noqa: F401 - the fixture
from tests.test_sdn_topology import READ_EPOCH, _cached, _stored_controller

CONN = "lab-ryu"
H2 = "192.0.2.2"
H2_MAC = "00:00:00:00:00:02"
#: The second host planted on s1 port 2 (a minimal edit: h2's entry, its MAC and addresses).
H5 = {"mac": "00:00:00:00:00:05", "ipv4": ["192.0.2.5"], "ipv6": ["2001:db8:8::5"]}
H5_V6 = {"mac": "00:00:00:00:00:05", "ipv4": [], "ipv6": ["2001:db8:8::5", "fe80::200:ff:fe00:5"]}


def stored(name=CONN, edit=None, now=READ_EPOCH + 30):
    """The SDN reader's stored topology of the captured fabric for connection *name*, through
    `topology.stored`, its hosts edited by *edit* (a function of the host list), read *now*."""
    c = _stored_controller()
    c["name"] = name
    if edit:
        c["topology"]["hosts"] = edit(copy.deepcopy(c["topology"]["hosts"]))
    return SDN.stored("Lab", now=now, cached=_cached([c]))


def plus(extra):
    """The hosts with *extra* planted on s1 port 2, beside h2 (h2's entry, edited)."""
    def edit(hosts):
        h2 = next(h for h in hosts if h["mac"] == H2_MAC)
        return hosts + [dict(h2, **extra)]
    return edit


def without_h2(hosts):
    return [h for h in hosts if h["mac"] != H2_MAC]


def h2_v6_only(hosts):
    """h2 with no IPv4 address, its link-local address listed first (the order Ryu keeps is the
    order it learned them in), so the global one is taken only by passing over it."""
    return [dict(h, ipv4=[], ipv6=["fe80::200:ff:fe00:2", "2001:db8:8::2"])
            if h["mac"] == H2_MAC else h for h in hosts]


def h2_link_local_only(hosts):
    return [dict(h, ipv4=[], ipv6=["fe80::200:ff:fe00:2"]) if h["mac"] == H2_MAC else h
            for h in hosts]


def walk(key):
    return next(c for c in load_walk()["cases"] if c["key"] == key)


def walk_flood(key, topo):
    """The walk's flood *key* judged again by the flood rule over its kept evidence (its
    baseline and since as its threshold and measurement state them), with *topo*."""
    case = walk(key)
    d = case["detection"]
    collected, sw = collection_of(case)
    t, m = d["threshold"], d["measurement"]
    pid = d["evidence"][0]
    baseline = {pid: {"samples": [t["baseline_pps"]] * t["baseline_samples"],
                      "at": D._epoch(d["at"])}}
    values = dict(D.THRESHOLDS, sdn_flood_factor=t["factor"],
                  sdn_flood_window_seconds=t["window_s"])
    got = D.flood(collected, baseline, values, {pid: D._epoch(m["since"])}, topo=topo)
    (det,) = [g for g in got["detections"] if g["subject"] == d["subject"]]
    return det, collected, sw


def walk_fallback(key, topo):
    """The walk's fallback scan *key* judged again by the scan rule over its kept evidence."""
    case = walk(key)
    d = case["detection"]
    collected, sw = collection_of(case)
    values = dict(D.THRESHOLDS, sdn_scan_fallback_pps=d["threshold"]["value"])
    got = D.scan(collected, values, topo=topo)["detections"]
    (det,) = [g for g in got if g["subject"] == d["subject"]]
    return det, collected, sw


# ───────────────────────────────────────────────────────────────────────────── the detection

def test_the_walks_mac_only_flood_names_h2_from_the_topology():
    """C2002's own case: the walk's flood on s1 port 2 (its flows matched MAC addresses only)
    names h2, the one host the controller lists on that port, and says how."""
    case = walk("walk-flood-1-s1")
    assert case["detection"]["source"] is None, "premise: the walk's detection named none"
    d, collected, sw = walk_flood("walk-flood-1-s1", stored())
    assert d["source"] == H2 and d["sources"] == []
    found = d["source_from"]
    assert (found["how"], found["state"], found["port"]) == ("topology", "named", 2)
    assert found["hosts"] == [{"mac": H2_MAC, "address": H2}]
    assert found["words"] == ("from the controller's topology: the one host on port 2, "
                              "192.0.2.2 (00:00:00:00:00:02)")
    assert found["read_at"] == "2026-10-27T09:35:49Z"
    # The card and the classifier see it: the section's detection piece carries it.
    sec = D.section(d, collected, sw)
    (piece,) = [p for p in sec["pieces"] if p["kind"] == "detection"]
    assert piece["source"] == H2 and piece["source_from"] == found
    sent = CL.sent_evidence(sec)
    assert sent["sources"] == [H2] and H2 in sent["names"]
    assert sent["detection"]["source_from"]["words"] == found["words"]


def test_the_fallback_scan_on_the_same_port_names_h2_too():
    """The scan rule's packet-rate fallback judges a port as the flood does (the walk's first
    false positive, on s1 port 2): its source comes the same way."""
    d, _c, _s = walk_fallback("walk-fp-1", stored())
    assert (d["rule"], d["basis"], d["port"]) == ("scan", "rate", 2)
    assert d["source"] == H2 and d["source_from"]["state"] == "named"


def test_a_host_with_no_address_beside_one_with_an_address_names_the_one():
    """s2 port 1 holds h3 (192.0.2.3) and d2:e6:76:c9:06:24, whose one address is link-local
    (the walk's fifth false positive is on that port): h3 is named, and the other is said."""
    d, _c, _s = walk_fallback("walk-fp-5", stored())
    assert d["source"] == "192.0.2.3"
    assert d["source_from"]["words"] == (
        "from the controller's topology: the one host on port 1, 192.0.2.3 "
        "(00:00:00:00:00:03); d2:e6:76:c9:06:24 also listed there, with no address to match")


def test_an_ipv6_only_host_is_named_by_its_ipv6_address_never_its_link_local_one():
    d, _c, _s = walk_flood("walk-flood-1-s1", stored(edit=h2_v6_only))
    assert d["source"] == "2001:db8:8::2"
    assert d["source_from"]["hosts"] == [{"mac": H2_MAC, "address": "2001:db8:8::2"}]


@pytest.mark.parametrize("key,topo,state,said", [
    ("walk-flood-1-s2", lambda: stored(), "link",
     "not named: port 3 is a link to switch 0000000000000001, so the source is not attached "
     "here; the switch it enters by names it"),
    ("walk-flood-1-s1", lambda: stored(edit=without_h2), "none",
     "not named: the controller's topology lists no host on port 2"),
    ("walk-flood-1-s1", lambda: stored(edit=h2_link_local_only), "no_address",
     "not named: the controller's topology lists 00:00:00:00:00:02 on port 2, with no address "
     "to match"),
    ("walk-flood-1-s1", lambda: stored(edit=plus(H5)), "several",
     "not named: the controller's topology lists 2 hosts on port 2 (192.0.2.2 "
     "(00:00:00:00:00:02), 192.0.2.5 (00:00:00:00:00:05))"),
    ("walk-flood-1-s1", lambda: stored(edit=plus(H5_V6)), "several",
     "not named: the controller's topology lists 2 hosts on port 2 (192.0.2.2 "
     "(00:00:00:00:00:02), 2001:db8:8::5 (00:00:00:00:00:05))"),
    ("walk-flood-1-s1", lambda: stored(now=READ_EPOCH + 3600), "unread",
     "not named: the controller's topology could not be read (the SDN reader's last read, at "
     "2026-10-27T09:35:49Z, is older than its promise of"),
    ("walk-flood-1-s1", lambda: stored(name="another"), "unread",
     "not named: the controller's topology could not be read (the SDN reader holds no topology "
     "for lab-ryu)"),
], ids=["link", "no-host", "no-address", "several", "several-ipv6", "stale", "not-held"])
def test_a_port_the_topology_cannot_resolve_to_one_host_stays_unnamed_saying_why(
        key, topo, state, said):
    d, _c, _s = walk_flood(key, topo())
    assert d["source"] is None
    assert d["source_from"]["state"] == state
    assert d["source_from"]["words"].startswith(said), d["source_from"]["words"]
    if state == "several":
        assert [h["address"] for h in d["source_from"]["hosts"]][0] == H2
        assert len(d["source_from"]["hosts"]) == 2
    else:
        assert d["source_from"]["hosts"] == []


def test_flows_naming_their_source_are_never_overridden_by_the_topology():
    """The walk's second flood on s1 (its flows L4, naming 192.0.2.2): the source is the
    flows', and the topology, even with two hosts on the port, is not consulted."""
    d, _c, _s = walk_flood("walk-flood-2-s1", stored(edit=plus(H5)))
    assert d["source"] == H2 and d["sources"] == [H2] and "source_from" not in d


def test_a_rule_given_no_topology_names_nothing_from_it():
    """What keeps the recorded cases' rebuilds as they are: no topology, no ``source_from``."""
    d, _c, _s = walk_flood("walk-flood-1-s1", None)
    assert d["source"] is None and "source_from" not in d
    assert json.loads(json.dumps(d)) == walk("walk-flood-1-s1")["detection"]


@pytest.mark.usefixtures("networks")
def test_observe_reads_the_stored_topology(monkeypatch):
    """`observe` looks the source up in the SDN reader's stored topology when none is handed in;
    the pack it keeps carries how it was found."""
    collected, _sw = collection_of(walk("walk-fp-1"))
    collected["network"] = "Default"
    asked = []
    topo = stored()

    def stored_for(network, *a, **kw):
        asked.append(network)
        return topo

    monkeypatch.setattr(SDN, "stored", stored_for)
    got = D.observe("Default", collected, values=dict(D.THRESHOLDS),
                    intent={"state": "ok", "flows": [], "withdrawn": {}, "error": ""})
    assert got["ok"], got["error"]
    assert asked == ["Default"]
    (d,) = [x for x in got["detections"] if x.get("port") == 2]
    assert d["source"] == H2 and d["source_from"]["state"] == "named"
    pack = got["kept"][d["key"]]
    sec = next(s for s in pack["sections"] if s.get("name") == "sdn")
    (piece,) = [p for p in sec["pieces"] if p["kind"] == "detection"]
    assert piece["source_from"]["words"].startswith("from the controller's topology")


# ───────────────────────────────────────────────────────────────────────────── the classifier

def _answer(source, affected):
    return CL.ThreatAssessment.model_validate_json(json.dumps({
        "reasoning": "planted", "threat_detected": True, "threat_type": "flood",
        "severity": "high", "affected_devices": affected, "recommended_action": "planted",
        "action_id": "drop_source",
        "parameters": {"source": source, "flow": "", "hard_timeout": 0, "rate": 0,
                       "unit": "kbps", "burst": 0},
        "evidence_refs": ["port:lab-ryu:0000000000000001:2"]}))


@pytest.mark.usefixtures("networks")
def test_the_classifier_may_propose_a_named_source_and_never_one_of_several():
    limits = {"sdn_response_max_seconds": 3600}
    pol = CL.policy("Default")
    named, c1, s1 = walk_flood("walk-flood-1-s1", stored())
    sent = CL.sent_evidence(D.section(named, c1, s1))
    why, params = CL.check_classification(_answer(H2, [H2]), named, sent, limits, pol=pol,
                                          network="Default")
    assert why == "" and params["source"] == H2
    several, c2, s2 = walk_flood("walk-flood-1-s1", stored(edit=plus(H5_V6)))
    sent = CL.sent_evidence(D.section(several, c2, s2))
    assert {H2, "2001:db8:8::5"} <= set(sent["names"]), "the port's hosts may be named"
    why, _p = CL.check_classification(_answer("2001:db8:8::5", [H2, "2001:db8:8::5"]), several,
                                      sent, limits, pol=pol, network="Default")
    assert why == "its source '2001:db8:8::5' is not one the detection saw (none)"


# ───────────────────────────────────────────────────────────────────────────── the picker

def several_on(connection="lab-controller", extra=H5, network="Default"):
    """The walk's MAC-only flood on s1 port 2, judged with a second host there, as a detection
    of *connection* on *network* (the route tests' controller)."""
    d, _c, _s = walk_flood("walk-flood-1-s1", stored(name=CONN, edit=plus(extra)))
    return dict(d, connection=connection, network=network)


@pytest.mark.usefixtures("lab")
def test_several_hosts_and_no_choice_is_refused_as_a_choice_naming_them():
    got = CL.respond_to_threat("Default", several_on(), "drop_source")
    assert not got["ok"]
    assert got["error"] == (
        "the detection names no single source to act on: not named: the controller's topology "
        "lists 2 hosts on port 2 (192.0.2.2 (00:00:00:00:00:02), 192.0.2.5 (00:00:00:00:00:05))"
        "; choose one of 192.0.2.2, 192.0.2.5")


@pytest.mark.usefixtures("lab")
@pytest.mark.parametrize("extra,chosen,match", [
    (H5, "192.0.2.5", {"eth_type": 0x0800, "ipv4_src": "192.0.2.5"}),
    (H5_V6, "2001:DB8:8:0::5", {"eth_type": 0x86DD, "ipv6_src": "2001:db8:8::5"}),
], ids=["ipv4", "ipv6"])
def test_a_chosen_host_is_the_one_dropped_and_its_choice_is_hashed(extra, chosen, match):
    d = several_on(extra=extra)
    got = CL.respond_to_threat("Default", d, "drop_source", {"source": chosen})
    assert got["ok"], got["error"]
    body = json.loads(got["plan"]["steps"][0]["request"]["body"])
    assert body["match"] == match
    assert got["params"]["source"] == match.get("ipv4_src", match.get("ipv6_src"))
    assert got["params"]["source_from"].startswith(
        "chosen from the 2 hosts the controller's topology lists on port 2: 192.0.2.2 "
        "(00:00:00:00:00:02), ")
    assert got["ask"]["detection"]["source_from"] == got["params"]["source_from"]
    other = CL.respond_to_threat("Default", d, "drop_source", {"source": H2})
    assert other["ok"] and other["plan"]["hash"] != got["plan"]["hash"]


@pytest.mark.usefixtures("lab")
@pytest.mark.parametrize("extra,chosen,listed", [
    (H5, "192.0.2.9", "192.0.2.2, 192.0.2.5"),
    (H5_V6, "2001:db8:8::9", "192.0.2.2, 2001:db8:8::5"),
], ids=["ipv4", "ipv6"])
def test_a_host_not_on_the_port_is_refused_naming_both(lab, extra, chosen, listed):
    got = CL.respond_to_threat("Default", several_on(extra=extra), "drop_source",
                               {"source": chosen})
    assert not got["ok"]
    assert got["error"] == (f"the source {chosen} is not a host the controller's topology lists "
                            f"on port 2 ({listed})")
    assert lab["fake"].writes == []


@pytest.mark.usefixtures("lab")
def test_no_host_to_choose_is_refused_saying_why_and_never_offers_a_choice():
    d, _c, _s = walk_flood("walk-flood-1-s1", stored(edit=without_h2))
    got = CL.respond_to_threat("Default", dict(d, connection="lab-controller",
                                               network="Default"), "drop_source",
                               {"source": H2})
    assert not got["ok"]
    assert got["error"] == ("the detection names no source to act on, and there is no host to "
                            "choose: not named: the controller's topology lists no host on "
                            "port 2")


@pytest.mark.usefixtures("lab")
def test_a_detection_unread_when_it_fired_is_looked_up_now_and_offers_no_choice_it_cannot(lab):
    """The topology unread when the flood fired: the preview reads the controller's hosts and
    links now (the fake answering the captured topology REST, h2 on s1 port 2) and names h2;
    with a second host there now, it is refused saying so, never "choose one", since the card
    drew no picker."""
    import tests.test_sdn_lab8 as L8

    d, _c, _s = walk_flood("walk-flood-1-s1", stored(now=READ_EPOCH + 3600))
    d = dict(d, connection="lab-controller", network="Default")
    assert d["source_from"]["state"] == "unread"
    lab["fake"].topology = L8.captured_topology()
    got = CL.respond_to_threat("Default", d, "drop_source")
    assert got["ok"], got["error"]
    assert got["params"]["source"] == H2
    assert got["params"]["source_from"].startswith("from the controller's topology: the one host")
    hosts = lab["fake"].topology["/v1.0/topology/hosts"]
    h2 = next(h for h in hosts if h["mac"] == H2_MAC)
    hosts.append(dict(h2, mac="00:00:00:00:00:05", ipv4=["192.0.2.5"]))
    got = CL.respond_to_threat("Default", d, "drop_source")
    assert not got["ok"] and "choose one" not in got["error"]
    assert got["error"] == (
        "the detection names no single source to act on: the controller's topology now lists 2 "
        "hosts on port 2 (192.0.2.2 (00:00:00:00:00:02), 192.0.2.5 (00:00:00:00:00:05)), and its "
        "card had no hosts to offer when it fired: dismiss it with a reason")
    assert lab["fake"].writes == []


@pytest.mark.usefixtures("lab")
def test_a_confirm_naming_another_source_is_refused_naming_both(lab):
    d = several_on()
    preview = CL.respond_to_threat("Default", d, "drop_source", {"source": "192.0.2.5"})
    assert preview["ok"], preview["error"]
    forged = copy.deepcopy(preview["ask"])
    forged["changes"][0]["flow"]["match"]["ipv4_src"] = "192.0.2.9"
    done = CL.respond_to_threat("Default", d, None, confirm={
        "ask": forged, "hash": preview["plan"]["hash"]}, actor="op@example.com",
        actor_verified="access")
    assert done["outcome"] == "refused"
    assert done["error"] == ("the confirm's source 192.0.2.9 is not one of the hosts on port 2 "
                             "(192.0.2.2, 192.0.2.5): nothing was sent; preview again")
    assert lab["fake"].writes == []


# ───────────────────────────────────────────────────────────────────────────── the card

def _row_html(page, rid):
    return re.search(rf'<details class="sdn-inc" id="sdn-i-{rid}".*?</details>\s*(?=<details|'
                     r'<p class="muted sdn-none"|<p class="small faint sdn-inc-more"|</section>)',
                     page, re.S).group(0)


def test_the_card_draws_the_picker_one_host_named_and_none_with_no_preview(lab):
    c = lab["client"]
    several = LP.propose("Default", dict(several_on(), key="k-several"), "drop_source", "low",
                         why="HITL")
    one, _c, _s = walk_flood("walk-flood-1-s1", stored())
    named = LP.propose("Default", dict(one, key="k-named", connection="lab-controller",
                                       network="Default", source="192.0.2.12"),
                       "drop_source", "low", why="HITL")
    nothing, _c, _s = walk_flood("walk-flood-1-s1", stored(edit=without_h2))
    none = LP.propose("Default", dict(nothing, key="k-none", connection="lab-controller",
                                      network="Default"), "drop_source", "low", why="HITL")
    page = c.get("/v2/sdn/responses?list=Default").get_data(as_text=True)
    pick = _row_html(page, several["id"])
    (select,) = re.findall(r'<select name="source".*?</select>', pick, re.S)
    assert re.findall(r'<option value="([^"]*)"', select) == ["", H2, "192.0.2.5"]
    assert "one of the 2 hosts on port 2…" in select and " required" in select
    assert ">192.0.2.5 (00:00:00:00:00:05)</option>" in select
    assert "one of 2</span>" in pick and "Choose which one beside Preview below" in pick
    one_row = _row_html(page, named["id"])
    assert '<select name="source"' not in one_row
    assert ("<strong>Source:</strong> <span class=\"mono\">192.0.2.12</span>, from the "
            "controller's topology: the one host on port 2") in unescape(one_row)
    none_row = _row_html(page, none["id"])
    assert f"/v2/sdn/response/{none['id']}/preview" not in none_row, "no Preview"
    assert "No source to act on:</strong> the controller's topology lists no host on port 2. " \
           "There is no host to choose" in unescape(none_row)
    assert "choose one" not in unescape(none_row).lower()


def test_the_route_takes_the_choice_into_the_preview_and_the_confirm(lab):
    c = lab["client"]
    row = LP.propose("Default", dict(several_on(), key="k-route"), "drop_source", "low",
                     why="HITL")
    refused = c.post(f"/v2/sdn/response/{row['id']}/preview",
                     data={"list": "Default", "source": "192.0.2.9", "hard_timeout": "60"})
    assert refused.status_code == 409
    assert ("the source 192.0.2.9 is not a host the controller's topology lists on port 2 "
            "(192.0.2.2, 192.0.2.5)") in unescape(refused.get_data(as_text=True))
    card = c.post(f"/v2/sdn/response/{row['id']}/preview",
                  data={"list": "Default", "source": "192.0.2.5", "hard_timeout": "60"})
    html = unescape(card.get_data(as_text=True))
    assert card.status_code == 200, html
    assert "192.0.2.5</span> (chosen from the 2 hosts the controller's topology lists on " \
           "port 2:" in html
    fields = form_fields(card.get_data(as_text=True))
    forged = dict(fields, ask=fields["ask"].replace("192.0.2.5", "192.0.2.9"))
    bad = c.post("/v2/sdn/response/confirm", data=forged)
    assert bad.status_code == 409 and lab["fake"].writes == []
    assert "the confirm&#39;s source 192.0.2.9 is not one of the hosts on port 2" in \
        bad.get_data(as_text=True)
    done = c.post("/v2/sdn/response/confirm", data=fields)
    assert "Done, verified" in done.get_data(as_text=True)
    (rec,) = F.intent("Default", "lab-controller")["flows"]
    assert rec["match"]["ipv4_src"] == "192.0.2.5"
