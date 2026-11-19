"""Declared external flow owners (C3930; the operator's decision of 2026-11-19): flows another
program on the controller installs and keeps (Lab 9: the team's own Ryu applications, which
Mercury does not port or manage) are declared in NetBox, and Mercury knows they are not rogue.

**The data.** The declarations are the Lab 9 seed's shape: the team's cookie registry puts an
application's id in a cookie's high 16 bits (0x9a00 base, 0x9a01 forwarding, 0x9a02 DHCP,
0x9a03 DNS, 0x9a04 monitor, 0x9a07 trace probes; mask 0xffff000000000000), carried in a device's
rendered config context ``mercury.external_flow_owners`` as the NSOT export keeps it. The
switch is tests/test_sdn_flow_ops.py's: Ryu 4.34's captured flow table through the real Ryu
driver (`tests.sdn_fakes.FakeRyu`), with one of the team's forwarding flows added at the place
the team's `forwarding.py` uses (table 0, priority 1000, an eth_dst match). Documentation
addresses and MACs only.

- **The declaration** (`protected.external_owners`): the seed read whole, once however many
  devices render it, a switch named by its NetBox name or its datapath id; an entry not of its
  shape refused ALONE, with why, the rest standing (a mask of 0, bits outside the mask, a range
  claiming cookie 0 or meeting Mercury's own, an unknown switch, an unknown key, a name not a
  slug, no owner or reason, a cookie not a number), two ways of one name and two meeting ranges
  each refused; never raising.
- **Whose a flow is** (`flow_intent.classify`): a declared cookie on its switch is
  ``external`` naming its owner; on a switch its entry does not name, and an undeclared non-zero
  cookie, ``unauthorised``; cookie 0 the controller's own; Mercury's prefix never external.
- **B3** (`detect.unauthorised`): a declared flow is never reported; undeclared, it is.
- **Every writer** (`flow_ops.plan`, the one path): a person's Remove…, a response's
  remove_flow at its preview (HITL) and at its confirm (as AUTO confirms), an edit, and an add
  at the declared flow's exact place (a person's, a policy's, a re-apply's) are each refused
  naming the owner, with nothing sent; a Mercury write elsewhere goes on, a malformed entry
  beside it; a response takes a priority above the declared flow it overrides.
- **SDN › Flows:** the declared flow drawn "external: <owner>" with its declaration and no
  Remove…, counted in the summary; an undeclared one still unauthorised with Remove…; a refused
  declaration said above the switches with why.
- **Where it is read for drawing:** the committed NSOT export only, never NetBox now.
"""
import copy
import json
import re
import time
from html import unescape

import pytest

from modules import protected as P
from modules.sdn import closed_loop as CL
from modules.sdn import detect as D
from modules.sdn import flow_intent as F
from modules.sdn import flow_ops as FO
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_ops_v2 import lab  # noqa: F401 - the fixture

MASK = "0xffff000000000000"
SW1 = "0000000000000001"


def seed():
    """The Lab 9 seed, as the operator applies it (C3930's report)."""
    def one(name, app, owner, reason, **kw):
        return dict({"name": name, "owner": owner, "cookie": f"0x{app:04x}000000000000",
                     "mask": MASK, "reason": reason}, **kw)
    return [one("lab9-base", 0x9A00, "lab9 team: forwarding.py", "OVS table 0's miss to the "
                "forwarding table", switches=["switch2", "switch3"]),
            one("lab9-forwarding", 0x9A01, "lab9 team: forwarding.py", "base forwarding"),
            one("lab9-dhcp", 0x9A02, "lab9 team: lab9_dhcp.py", "DHCP through the fabric"),
            one("lab9-dns", 0x9A03, "lab9 team: lab9_dns.py", "DNS punted to the verdict"),
            one("lab9-monitor", 0x9A04, "lab9 team: forwarding.py", "a legacy monitor rule"),
            one("lab9-trace", 0x9A07, "lab9 team: trace_app.py", "trace probes, 120 s")]


def device(name, dpid=None, entries=None):
    d = {"name": name, "custom_fields": {"openflow_datapath_id": dpid},
         "config_context": {"mercury": {"protected_flows": []}}}
    if entries is not None:
        d["config_context"]["mercury"]["external_flow_owners"] = copy.deepcopy(entries)
    return d


def devices(entries):
    """Three devices rendering the one context, as NetBox renders a context on each."""
    return [device("switch2", "0000000000000003", entries),
            device("switch3", "0000000000000004", entries),
            device("SDNGroup1Router", None, entries)]


TEAM_FLOW = {"table_id": 0, "priority": 1000, "cookie": 0x9A01000000000005,
             "match": {"eth_dst": "02:00:00:00:00:01"}, "actions": [{"type": "OUTPUT", "port": 2}],
             "idle_timeout": 0, "hard_timeout": 0}


# --------------------------------------------------------------------------- the declaration

class TestTheDeclaration:
    def test_the_lab_s_seed_is_read_whole_once_with_its_switches(self):
        got = P.external_owners(devices(seed()))
        assert got["refused"] == []
        assert [o["name"] for o in got["owners"]] == [
            "lab9-base", "lab9-dhcp", "lab9-dns", "lab9-forwarding", "lab9-monitor", "lab9-trace"]
        base = got["owners"][0]
        assert base["switches"] == [3, 4] and base["mask"] == 0xFFFF << 48
        assert base["cookie"] == 0x9A00 << 48 and base["cookie_hex"] == "0x9a00000000000000"
        assert got["owners"][1]["switches"] is None
        assert base["source"] == ("NetBox: switch2's config context "
                                  "mercury.external_flow_owners")
        by_dpid = P.external_owners(devices([dict(seed()[0], switches=[
            "0000000000000003", "0x0000000000000004"])]))["owners"][0]
        assert by_dpid["switches"] == [3, 4]

    @pytest.mark.parametrize("change, said", [
        ("not a mapping", "an entry is a mapping of name, owner, cookie"),
        ({"name": "Lab 9"}, "an owner's name is a slug, not 'Lab 9'"),
        ({"colour": "red"}, "names colour, and an entry holds"),
        ({"owner": ""}, "owner is words, 1 to 100 characters"),
        ({"reason": None}, "reason is words, 1 to 300 characters"),
        ({"cookie": "9a01"}, "cookie '9a01' is not a 64-bit number"),
        ({"cookie": "0x1" + "0" * 16}, "is not a 64-bit number"),
        ({"mask": "0x0"}, "a mask of 0 would claim every flow"),
        ({"cookie": "0x9a01000000000001"}, "has bits outside its mask"),
        ({"cookie": "0x0000000000000000"}, "claims cookie 0, the controller's own"),
        ({"cookie": "0x4d45000000000000"}, "meets Mercury's own (0x4d45 in the high 16 bits)"),
        ({"cookie": "0x4000000000000000", "mask": "0xf000000000000000"}, "meets Mercury's own"),
        ({"switches": ["no-such-switch"]}, "switch 'no-such-switch' is neither a NetBox device"),
        ({"switches": []}, "switches are a list of NetBox device names"),
    ])
    def test_an_entry_not_of_its_shape_refuses_itself_alone(self, change, said):
        bad = "not a mapping" if change == "not a mapping" else dict(seed()[1], **change)
        if isinstance(bad, dict):
            bad["name"] = change.get("name", "lab9-broken")
        got = P.external_owners(devices([bad, seed()[2]]))
        assert [o["name"] for o in got["owners"]] == ["lab9-dhcp"], "the rest stand"
        assert len(got["refused"]) == 1, "said once, however many devices render it"
        assert said in got["refused"][0]["error"]
        assert got["refused"][0]["where"] == ("switch2's config context "
                                              "mercury.external_flow_owners[0]")

    def test_two_ways_of_one_name_and_two_meeting_ranges_are_each_refused(self):
        twice = [seed()[1], dict(seed()[1], cookie="0x9a05000000000000")]
        got = P.external_owners(devices(twice + [seed()[2]]))
        assert [o["name"] for o in got["owners"]] == ["lab9-dhcp"]
        assert len(got["refused"]) == 2
        assert all("lab9-forwarding is declared 2 ways" in r["error"] for r in got["refused"])
        wide = dict(seed()[2], name="lab9-wide", cookie="0x9a00000000000000",
                    mask="0xff00000000000000")
        apart = dict(seed()[2], name="lab9-apart", cookie="0x5351000000000000")
        got = P.external_owners(devices([seed()[1], wide, apart]))
        assert [o["name"] for o in got["owners"]] == ["lab9-apart"]
        said = sorted(r["name"] for r in got["refused"])
        assert said == ["lab9-forwarding", "lab9-wide"]
        assert "so a flow in both would have two owners" in got["refused"][0]["error"]

    def test_a_list_not_a_list_is_refused_and_nothing_raises(self):
        d = device("switch2", "0000000000000003")
        d["config_context"]["mercury"]["external_flow_owners"] = {"name": "x"}
        got = P.external_owners([d, device("switch3", "0000000000000004", [seed()[1]])])
        assert [o["name"] for o in got["owners"]] == ["lab9-forwarding"]
        assert "is a list of owners, not dict" in got["refused"][0]["error"]
        assert P.external_owners([{"config_context": None}, {}, "junk", None]) == {
            "owners": [], "refused": []}

    def test_cookies_are_read_as_numbers_and_owners_matched_under_the_mask(self):
        assert P.cookie_number("0x9A01_0000_0000_0000") == 0x9A01 << 48
        assert P.cookie_number(5) == 5 and P.cookie_number("12") == 12
        assert P.cookie_number(True) is None and P.cookie_number(-1) is None
        owners = P.external_owners(devices(seed()))["owners"]
        assert P.external_owner_of(owners, 0x9A01000000000005, 1)["name"] == "lab9-forwarding"
        assert P.external_owner_of(owners, 0x9A00000000000001, 3)["name"] == "lab9-base"
        assert P.external_owner_of(owners, 0x9A00000000000001, 1) is None, "not its switch"
        assert P.external_owner_of(owners, 0x9A05000000000001, 1) is None, "not declared"
        assert P.external_owner_of(owners, "0x9a01", 1) is None


# --------------------------------------------------------------------------- whose a flow is

def _flows(dpid=1):
    team = dict(TEAM_FLOW, dpid=dpid)
    base = dict(TEAM_FLOW, cookie=0x9A00000000000000, priority=0, match={}, dpid=dpid)
    rogue = dict(TEAM_FLOW, cookie=0x1234000000000001, priority=1100, dpid=dpid)
    ryu = dict(TEAM_FLOW, cookie=0, priority=65535, match={"eth_type": 0x88CC}, dpid=dpid)
    mercury = dict(TEAM_FLOW, cookie=F.mercury_cookie(7), priority=300, dpid=dpid)
    return [team, base, rogue, ryu, mercury]


class TestWhoseAFlowIs:
    def test_a_declared_flow_is_external_and_an_undeclared_one_unauthorised(self):
        owners = P.external_owners(devices(seed()))["owners"]
        got = F.classify(_flows(1), {"name": "lab", "own_cookies": [0]},
                         {"state": "ok", "flows": [], "withdrawn": {}}, external=owners)
        by = [(f["owner"], f.get("external", {}).get("name")) for f in got["flows"]]
        assert by == [("external", "lab9-forwarding"), ("unauthorised", None),
                      ("unauthorised", None), ("controller_own", None), ("unauthorised", None)]
        team = got["flows"][0]
        assert team["words"].startswith("external: lab9 team: forwarding.py (lab9-forwarding: "
                                        "base forwarding; cookies 0x9a01000000000000 under "
                                        "0xffff000000000000, declared in NetBox: switch2's")
        assert got["counts"]["external"] == 1 and got["counts"]["unauthorised"] == 3
        on3 = F.classify(_flows(3), {"name": "lab", "own_cookies": [0]},
                         {"state": "ok", "flows": [], "withdrawn": {}}, external=owners)
        assert [f["owner"] for f in on3["flows"]][:2] == ["external", "external"], \
            "lab9-base names switch2 (datapath 3)"

    def test_with_no_declaration_every_foreign_flow_is_unauthorised_as_before(self):
        for external in (None, []):
            got = F.classify(_flows(1), {"name": "lab", "own_cookies": [0]},
                             {"state": "ok", "flows": [], "withdrawn": {}}, external=external)
            assert [f["owner"] for f in got["flows"]].count("unauthorised") == 4
            assert got["counts"]["external"] == 0


# --------------------------------------------------------------------------- B3

def _collected(flows):
    return {"collected_at": "2026-11-19T18:00:00Z", "controllers": [{
        "connection": "lab", "own_cookies": [0], "state": "ok",
        "switches": [{"dpid": 1, "dpid_hex": SW1, "active_flows": len(flows), "flows": flows,
                      "ports": []}]}]}


class TestB3:
    def test_b3_reports_no_declared_flow(self, networks):  # noqa: F811
        owners = P.external_owners(devices(seed()))["owners"]
        flows = [dict(f, id=f"f{n}") for n, f in enumerate(_flows(1))]
        intent = {"state": "ok", "flows": [], "withdrawn": {}}
        before = D.unauthorised(_collected(flows), intent, now=time.time())
        cookies = sorted(d["measurement"]["cookie"] for d in before["detections"])
        assert "0x9a01000000000005" in cookies, "undeclared, the team's flow is reported"
        after = D.unauthorised(_collected(flows), intent, now=time.time(), external=owners)
        cookies = sorted(d["measurement"]["cookie"] for d in after["detections"])
        assert "0x9a01000000000005" not in cookies
        assert "0x1234000000000001" in cookies, "an undeclared flow is still reported"


# --------------------------------------------------------------------------- every writer

@pytest.fixture
def declared(lab, monkeypatch):  # noqa: F811 - the fixture
    """The team's forwarding flow on switch 1; ``declare(entries)`` (the seed by default),
    called in each test's own body, declares them in the network's set as NetBox would give
    it, the guard's own code unchanged."""
    lab["fake"].table[1].append(dict(TEAM_FLOW))
    held = {"lab": lab}

    def declare(entries=None):
        got = P.external_owners(devices(seed() if entries is None else entries))
        pset = {"state": "none", "source": "planted", "sha256": "", "error": "", "classes": [],
                "objects": {}, "switches": {}, "ports": {}, "external": got}
        monkeypatch.setattr(P, "for_network", lambda network: pset)
        monkeypatch.setattr(P, "external_for_network", lambda network: dict(
            got, state="ok", source="planted", error=""))
        held["pset"] = pset
        return pset

    held["declare"] = declare
    return held


def _target(flow=TEAM_FLOW):
    return {k: flow[k] for k in ("table_id", "priority", "match", "cookie")}


def _ask(*changes, response=False):
    return {"connection": "lab-controller", "dpid": 1, "changes": list(changes),
            "response": response}


REFUSED = ("is declared external: lab9 team: forwarding.py (lab9-forwarding: base forwarding; "
           "cookies 0x9a01000000000000 under 0xffff000000000000")


class TestNoWriterTouchesIt:
    def test_a_person_s_remove_is_refused_naming_the_owner(self, declared):
        declared["declare"]()
        p = FO.plan("Default", _ask({"do": "remove_flow", "target": _target()}))
        assert not p["ok"] and REFUSED in p["error"]
        assert "No Mercury writer may remove a flow another owner declared" in p["error"]
        assert "adds its own flow at a higher priority" in p["error"]
        assert declared["lab"]["fake"].writes == []

    def test_the_remove_route_refuses_it_with_nothing_sent(self, declared):
        declared["declare"]()
        c = declared["lab"]["client"]
        r = c.post("/v2/sdn/flow/preview", data={
            "list": "Default", "do": "remove", "connection": "lab-controller", "dpid": SW1,
            "target": json.dumps(_target(), sort_keys=True)})
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 409 and REFUSED in html
        assert declared["lab"]["fake"].writes == []

    def test_a_response_s_remove_is_refused_at_its_preview_and_its_confirm(self, declared):
        declared["declare"]()
        ref = CL.flow_ref("lab-controller", 1, TEAM_FLOW)
        det = {"key": "k-team", "rule": "unauthorised_flow", "title": "SDN unauthorised flow",
               "network": "Default", "connection": "lab-controller", "dpid": 1,
               "dpid_hex": SW1, "subject": {"kind": "flow", "value": ref},
               "confidence": "high", "words": "a flow", "at": "2026-11-19T18:00:00Z"}
        preview = CL.respond_to_threat("Default", det, "remove_flow")
        assert not preview["ok"] and REFUSED in preview["error"]
        ask = dict(_ask({"do": "remove_flow", "target": _target()}, response=True),
                   action="remove_flow", detection=det)
        for mode in ("hitl", "auto"):                  # a person's confirm, and AUTO's
            got = CL.respond_to_threat("Default", det, "remove_flow", confirm={
                "ask": ask, "hash": "ab" * 32}, actor="op@example.com",
                actor_verified="access", mode=mode,
                autonomous={"reason": "the lab's AUTO"} if mode == "auto" else None,
                sleep=lambda s: None)
            assert got["outcome"] == "refused" and REFUSED in got["error"], (mode, got)
        assert declared["lab"]["fake"].writes == []

    def test_an_edit_is_refused_naming_the_owner(self, declared):
        declared["declare"]()
        new = dict(TEAM_FLOW, actions=[])
        p = FO.plan("Default", _ask({"do": "edit_flow", "target": _target(), "flow": new}))
        assert not p["ok"] and REFUSED in p["error"]
        assert "No Mercury writer may change a flow another owner declared" in p["error"]

    @pytest.mark.parametrize("writer", ["person", "policy:p1", "response"])
    def test_an_add_at_its_place_is_refused_for_every_writer(self, declared, writer):
        declared["declare"]()
        flow = dict(TEAM_FLOW, cookie=F.new_cookie(), hard_timeout=60, actions=[])
        p = FO.plan("Default", _ask({"do": "add_flow", "flow": flow},
                                    response=writer == "response"), writer=writer)
        assert not p["ok"] and REFUSED in p["error"]
        assert "No Mercury writer may replace a flow another owner declared" in p["error"]
        assert declared["lab"]["fake"].writes == []

    def test_a_write_elsewhere_goes_on_with_a_malformed_entry_beside(self, declared):
        pset = declared["declare"](seed() + [dict(seed()[1], name="lab9-broken", mask="0x0")])
        assert pset["external"]["refused"]
        flow = dict(TEAM_FLOW, cookie=F.new_cookie(), priority=1001, actions=[],
                    match={"eth_type": 0x0800, "ipv4_src": "198.51.100.7"})
        p = FO.plan("Default", _ask({"do": "add_flow", "flow": flow}))
        assert p["ok"], p["error"]

    def test_a_response_takes_a_priority_above_the_declared_flow(self, declared):
        table = declared["lab"]["fake"].table[1]
        prio = FO.response_priority(table, [0], (), match={"eth_dst": "02:00:00:00:00:01"})
        assert prio > TEAM_FLOW["priority"]


# --------------------------------------------------------------------------- SDN › Flows

def _flows_page(declared):
    from tests.test_sdn_v2 import store_read
    store_read("Default", clock=time.time)
    c = declared["lab"]["client"]
    return unescape(c.get("/v2/sdn/flows?list=Default&own=show").get_data(as_text=True))


def _row(html, cookie):
    for row in re.findall(r'<tr class="sdn-f-[a-z_]+">.*?</tr>', html, re.S):
        if f">{cookie}<" in row:
            return row
    return ""


class TestSdnFlows:
    def test_a_declared_flow_is_drawn_external_with_no_remove(self, declared):
        declared["declare"]()
        declared["lab"]["fake"].table[1].append(dict(TEAM_FLOW, cookie=0x1234000000000001,
                                                     priority=1100))
        html = _flows_page(declared)
        team = _row(html, "0x9a01000000000005")
        assert "external: lab9 team: forwarding.py" in team
        assert "lab9-forwarding: base forwarding" in team
        assert "Remove…" not in team
        rogue = _row(html, "0x1234000000000001")
        assert "unauthorised" in rogue and "Remove…" in rogue
        assert re.search(r"· 1 external ·", html)

    def test_a_refused_declaration_is_said_with_why(self, declared):
        declared["declare"]([dict(seed()[1], mask="0x0")])
        html = _flows_page(declared)
        assert "1 declared external flow owner refused" in html
        assert "a mask of 0 would claim every flow" in html
        assert "unauthorised" in _row(html, "0x9a01000000000005")


# --------------------------------------------------------------------------- where it is read

class TestWhereItIsRead:
    def test_the_committed_export_only_never_netbox_now(self, monkeypatch):
        from modules.nsot import export as X
        monkeypatch.setattr("modules.inventory.source_config.load",
                            lambda name: {"source": "netbox"})
        monkeypatch.setattr(X, "build", lambda *a, **k: pytest.fail("NetBox read now"))
        monkeypatch.setattr(X, "read", lambda network: {
            "ok": True, "sha256": "ab" * 32, "error": "",
            "export": {"body": {"devices": devices(seed())}}})
        got = P.external_for_network("lab9")
        assert got["state"] == "ok" and len(got["owners"]) == 6
        assert got["source"] == f"the committed NSOT export {'ab' * 6}"
        monkeypatch.setattr(X, "read", lambda network: {"ok": False, "absent": True,
                                                        "error": "none"})
        got = P.external_for_network("lab9")
        assert got["state"] == "none" and got["owners"] == []
        monkeypatch.setattr(X, "read", lambda network: {"ok": False, "error": "edited"})
        assert P.external_for_network("lab9")["state"] == "unreadable"
        monkeypatch.setattr("modules.inventory.source_config.load",
                            lambda name: {"source": "local"})
        assert P.external_for_network("Default")["state"] == "none"
