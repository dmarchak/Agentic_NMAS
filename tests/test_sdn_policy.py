"""The SDN response policy (`closed_loop.policy`, the setting ``sdn_response_policy``; the Lab
8 walk's objective 3.1, the operator's order of 2026-10-27): for each rule, the catalogue
actions a response may take on the network, the first its default.

- **The default reproduces the release before it**: the schema's default is every catalogue
  action that answers each rule, its first the old default; the schema's actions are the
  catalogue's.
- **What the model is sent**: with SDN lab's policy (a scan rate-limited only), the catalogue
  sent for a scan is rate_limit_source and none.
- **The check**: an answer of drop_source for a scan is refused naming the action, the rule,
  the network and the allowed set, and in the loop the policy's default (rate_limit_source)
  awaits a person, said, with the refused call; AUTO does not act on it. An answer of
  rate_limit_source passes with its parameters checked (IPv4, and IPv6 in another spelling).
- **A person**: a preview of drop_source for a scan is refused through the real route, and a
  confirm of a preview the policy no longer allows is refused; nothing is sent.
- **The setting**: a bad policy is refused naming why (the function and the route); the edit
  control round-trips through the real app, recorded, and a stale form is refused naming both
  policies.
- **Fail closed**: a policy that cannot be read allows nothing, sends nothing to AI, proposes
  nothing in the loop and says so on the page.
"""
import json
import re
import time
from html import unescape

import pytest

from modules import list_settings
from modules.sdn import closed_loop as CL
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.ai_person import PERSON
from tests.test_sdn_classify import (PARAMS, SCAN, SCAN6, _feature_on, _pass, answer,
                                     classify_as_person, keep_pack, rows, world)  # noqa: F401
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_ops_v2 import lab  # noqa: F401 - the fixture

NET = "Default"
#: The SDN lab's policy as the operator ordered it: a scan rate-limited only; a flood
#: rate-limited or dropped; an unauthorised flow removed.
SDN_LAB = {"scan": ["rate_limit_source"], "flood": ["rate_limit_source", "drop_source"],
           "unauthorised_flow": ["remove_flow"]}


def set_policy(value, network=NET):
    got = list_settings.write(network, {CL.POLICY_KEY: value}, actor="test")
    assert got["ok"], got


def catalogue_entries(body) -> list:
    """The catalogue the request carried (its cached context), each entry whole."""
    text = "".join(b["text"] for b in body["system"])
    m = re.search(r'<context name="catalogue">\n(.*?)\n</context>', text, re.S)
    assert m, text[:400]
    return json.loads(m.group(1))


def catalogue_sent(body) -> list:
    """The action ids of the catalogue the request carried."""
    return [e["action_id"] for e in catalogue_entries(body)]


# ── the default ──────────────────────────────────────────────────────────────────────────────

def test_the_default_reproduces_the_release_before_it(networks):  # noqa: F811
    from modules.settings_schema import DEFAULTS, SCHEMA
    assert DEFAULTS[CL.POLICY_KEY] == CL.DEFAULT_POLICY
    for rule in CL.RULES:
        assert CL.DEFAULT_POLICY[rule][0] == CL.DEFAULT_ACTION[rule]
        assert sorted(CL.DEFAULT_POLICY[rule]) == sorted(
            a for a, e in CL.CATALOGUE.items() if rule in e["rules"])
    enum = SCHEMA["properties"][CL.POLICY_KEY]["properties"]["scan"]["items"]["enum"]
    assert sorted(enum) == sorted(CL.CATALOGUE)
    got = CL.policy(NET)
    assert got["ok"] and {r: got["rules"][r]["allowed"] for r in CL.RULES} == CL.DEFAULT_POLICY
    assert CL.policy_problems(CL.DEFAULT_POLICY) == []


def test_with_the_default_a_scan_is_still_proposed_a_drop(networks):  # noqa: F811
    from tests.test_sdn_modes_loop import collected, observed
    LP.run_pass(NET, collect=collected, observe=observed(fired=["k1"]), now=lambda: 1.79e9,
                driver=lambda n, c: {"ok": False, "error": "unused"})
    (row,) = LP.awaiting(NET)["rows"]
    assert row["action"] == "drop_source"


# ── what the model is sent, and the check ───────────────────────────────────────────────────

def test_sdn_lab_s_policy_sends_the_model_only_rate_limit_and_none_for_a_scan(world):
    set_policy(SDN_LAB)
    keep_pack(SCAN)
    world.answer = answer(action_id="rate_limit_source")
    got = classify_as_person(world)
    assert got["ok"], got
    (body,) = world.sent
    assert catalogue_sent(body) == ["rate_limit_source", "none"]
    rate, none = catalogue_entries(body)
    assert rate["answers"] == ["flood", "scan"] and rate["risk"] == "low"
    assert none["answers"] == ["scan", "flood", "unauthorised_flow"], \
        "none answers every rule: the model may always propose no action"


def test_the_default_policy_sends_a_scan_both_actions_that_answer_it(world):
    keep_pack(SCAN)
    classify_as_person(world)
    (body,) = world.sent
    assert catalogue_sent(body) == ["drop_source", "rate_limit_source", "none"]


def test_the_catalogue_is_sent_in_the_policy_s_order_its_default_first_and_marked(world):
    """C1988: prompt v3 tells the model to take the catalogue's `default`, so the catalogue
    sent lists the allowed actions in the network's order, the first (the policy's default)
    marked default and no other; `none` last, never a default."""
    set_policy(dict(SDN_LAB, scan=["rate_limit_source", "drop_source"]))
    keep_pack(SCAN)
    classify_as_person(world)
    (body,) = world.sent
    assert catalogue_sent(body) == ["rate_limit_source", "drop_source", "none"]
    assert [e.get("default") for e in catalogue_entries(body)] == [True, False, None]
    # The pure function: the policy's order, duplicates and unknown ids dropped.
    got = CL.catalogue_for_ai(["drop_source", "rate_limit_source", "drop_source", "nope"])
    assert [(e["action_id"], e.get("default")) for e in got] == [
        ("drop_source", True), ("rate_limit_source", False), ("none", None)]


def test_prompt_v3_takes_the_action_from_the_catalogue_and_maps_no_rule_to_an_action():
    """C1988: v3 names no rule-to-action mapping (v1's "a scan is answered by dropping its
    source" made the model answer drop under a rate-limit-only policy, 4 of 6 replays) and
    tells the model to take the catalogue's default; v1 is kept unchanged as the record."""
    from modules.ai import prompts
    v3 = prompts.load("sdn_classify", 3)["text"]
    v1 = prompts.load("sdn_classify", 1)["text"]
    for mapping in ("is answered by", "a scan is answered", "a flood by", "unauthorised flow by",
                    "rate-limiting a source before dropping"):
        assert mapping not in v3, mapping
    assert "Take the catalogue's `default` action" in v3
    assert "Never choose an action the catalogue does not list." in v3
    assert "a scan is answered by dropping its source" in v1


def test_a_drop_for_a_scan_under_sdn_lab_s_policy_is_refused_naming_both_sides(world):
    set_policy(SDN_LAB)
    keep_pack(SCAN)
    got = classify_as_person(world)                        # the planted answer: drop_source
    assert got["error"] == "couldnt_classify", got
    assert got["why"] == ("drop_source is outside Default's response policy for scan, which "
                          "allows rate_limit_source")
    assert got["classification"] is None


def test_in_the_loop_the_refused_drop_leaves_the_rate_limit_awaiting_a_person_and_auto_idle(
        world, monkeypatch):
    set_policy(SDN_LAB)
    keep_pack(SCAN)
    _feature_on()
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=time.time() + 600, allowed_risk="low")
    applied = []
    monkeypatch.setattr(CL, "respond_to_threat", lambda *a, **k: applied.append(a) or {})
    out = _pass(world)
    assert out["ok"] and applied == [], "AUTO never acts on a refused classification"
    (resp,) = LP.awaiting(NET)["rows"]
    (call,) = rows()
    assert resp["action"] == "rate_limit_source" and resp["why"] == LP.NOT_CLASSIFIED_WHY
    assert resp["classified"] == (
        "AI classification refused: drop_source is outside Default's response policy for "
        "scan, which allows rate_limit_source; proposed by the catalogue default, "
        f"rate_limit_source (AI call {call['id']})")
    assert resp["refused_call"] == call["id"]


@pytest.mark.parametrize("case,source,canon", [
    (SCAN, "192.0.2.1", "192.0.2.1"),
    (SCAN6, "2001:0db8:8:0:0:0:0:1", "2001:db8:8::1")], ids=["ipv4", "ipv6"])
def test_a_rate_limit_passes_with_its_parameters_checked(world, case, source, canon):
    set_policy(SDN_LAB)
    keep_pack(case)
    world.answer = answer(action_id="rate_limit_source",
                          affected_devices=[source] if ":" in source else answer()[
                              "affected_devices"],
                          parameters=dict(PARAMS, source=source, hard_timeout=120, rate=500,
                                          unit="pktps", burst=50),
                          evidence_refs=[case["expect"]["cites_any"][0]])
    got = classify_as_person(world, c=case)
    assert got["ok"], got
    assert (got["action"], got["params"]) == ("rate_limit_source", {
        "source": canon, "hard_timeout": 120, "rate": 500, "unit": "pktps", "burst": 50})
    world.answer["parameters"]["source"] = "192.0.2.77" if ":" not in source else "2001:db8::77"
    got = classify_as_person(world, c=case)
    assert got["error"] == "couldnt_classify" and "is not one the detection saw" in got["why"]


# ── a person's own choice ─────────────────────────────────────────────────────────────────────

SCAN_D = {"key": "k1", "rule": "scan", "title": "SDN scan", "network": NET,
          "connection": "lab-controller", "dpid": 1, "dpid_hex": "0000000000000001",
          "source": "192.0.2.1", "targets": ["192.0.2.2"], "confidence": "high",
          "words": "192.0.2.1 reached 25 distinct destination ports"}


def test_a_person_s_preview_of_a_drop_for_a_scan_is_refused_and_nothing_is_sent(lab):
    set_policy(SDN_LAB)
    row = LP.propose(NET, SCAN_D, "rate_limit_source", "low", why="HITL")
    r = lab["client"].post(f"/v2/sdn/response/{row['id']}/preview",
                           data={"list": NET, "action": "drop_source"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 409, html
    assert ("drop_source is outside Default's response policy for scan, which allows "
            "rate_limit_source") in html
    assert lab["fake"].writes == []


def test_a_confirm_of_a_preview_the_policy_no_longer_allows_sends_nothing(lab):
    from tests.test_sdn_ops_v2 import form_fields
    row = LP.propose(NET, SCAN_D, "drop_source", "low", why="HITL")
    c = lab["client"]
    fields = form_fields(c.post(f"/v2/sdn/response/{row['id']}/preview",
                                data={"list": NET}).get_data(as_text=True))
    assert json.loads(fields["ask"])["action"] == "drop_source"
    set_policy(SDN_LAB)
    r = c.post("/v2/sdn/response/confirm", data=fields)
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 409 and "Nothing was sent" in html, html
    assert "drop_source is outside Default's response policy for scan" in html
    assert lab["fake"].writes == [] and LP.awaiting(NET)["rows"]


def test_a_confirm_naming_another_action_than_its_preview_sends_nothing(lab):
    from tests.test_sdn_ops_v2 import form_fields
    row = LP.propose(NET, SCAN_D, "drop_source", "low", why="HITL")
    c = lab["client"]
    fields = form_fields(c.post(f"/v2/sdn/response/{row['id']}/preview",
                                data={"list": NET}).get_data(as_text=True))
    fields["action"] = "rate_limit_source"
    r = c.post("/v2/sdn/response/confirm", data=fields)
    assert r.status_code == 409
    assert ("the confirm names rate_limit_source and its preview drop_source"
            in unescape(r.get_data(as_text=True)))
    assert lab["fake"].writes == []


def test_the_lab_8_scan_is_rate_limited_under_sdn_lab_s_policy(networks):  # noqa: F811
    """The walk's own case: the Lab 8 run's scan of h3 from h1 on s1 (the real capture through
    the real collection and rule), previewed with no action named under SDN lab's policy,
    is one meter with a single drop band and the source's flow to h3 through it, its
    forwarding the controller's own from the captured table; confirmed and verified."""
    from modules.sdn import connections as C
    from modules.sdn import detect as D
    from tests.sdn_fakes import lab8
    from tests.test_sdn_lab8 import BASE, collect, fake_with, features_of, flows_of
    C.save_connection(NET, {"name": "lab", "kind": "ryu", "url": BASE}, actor="op")
    set_policy(SDN_LAB)
    entries = lab8("scan_s1.json")
    (d,) = D.scan(collect(entries), dict(D.THRESHOLDS))["detections"]
    fake = fake_with(flows_of(entries, 1), 1, features_of(entries, 1))
    preview = CL.respond_to_threat(NET, d, driver=fake.driver)
    assert preview["ok"], preview["error"]
    assert preview["action"] == "rate_limit_source" and preview["ask"]["action"] == \
        "rate_limit_source"
    meter, *flows = preview["plan"]["steps"]
    band = json.loads(meter["request"]["body"])["bands"]
    assert band == [{"burst_size": 100, "rate": 1000, "type": "DROP"}]
    (flow,) = flows
    body = json.loads(flow["request"]["body"])
    assert body["match"] == {"eth_type": 2048, "ipv4_dst": "192.0.2.3", "ipv4_src": "192.0.2.1"}
    assert body["actions"][0]["type"] == "METER"
    done = CL.respond_to_threat(NET, None, confirm={"ask": preview["ask"],
                                                    "hash": preview["plan"]["hash"]},
                                actor="op@example.com", actor_verified="access",
                                driver=fake.driver, sleep=lambda s: None, counter_interval=0)
    assert done["outcome"] == "verified", done["error"]


def test_with_no_action_named_a_preview_takes_the_policy_s_default(networks):  # noqa: F811
    from tests.test_sdn_respond import scan_detection, switch_with
    from tests.test_sdn_detect import save, scan_flows
    save()
    set_policy(SDN_LAB)
    flows = scan_flows(25)
    d = scan_detection(flows)
    got = CL.respond_to_threat(NET, d, driver=switch_with(flows).driver)
    assert got["action"] == "rate_limit_source", got


# ── the setting ───────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,words", [
    (dict(SDN_LAB, scan=["remove_flow"]),
     "gives scan remove_flow, which answers unauthorised_flow, not scan (the actions that "
     "answer scan: drop_source, rate_limit_source)"),
    (dict(SDN_LAB, flood=[]), "gives flood no action"),
    (dict(SDN_LAB, scan=["shutdown_port"]), "gives scan 'shutdown_port', which is not in the "
                                            "response catalogue"),
    (dict(SDN_LAB, scan=["rate_limit_source", "rate_limit_source"]),
     "names rate_limit_source twice for scan"),
    (dict(SDN_LAB, worm=["drop_source"]), "names worm, which no detection rule is"),
    ({"scan": ["drop_source"]}, "gives flood no action"),
])
def test_a_bad_policy_is_refused_naming_why(networks, value, words):  # noqa: F811
    with pytest.raises(CL.PolicyRefused, match=re.escape(words)):
        CL.save_policy(NET, value, actor=PERSON, actor_verified="access")
    assert CL.policy(NET)["rules"]["scan"]["allowed"] == CL.DEFAULT_POLICY["scan"]


def test_the_policy_is_set_by_a_verified_person(networks):  # noqa: F811
    with pytest.raises(CL.PolicyRefused, match="by a verified person"):
        CL.save_policy(NET, SDN_LAB, actor=PERSON, actor_verified="none")


def _policy_form(html: str) -> dict:
    form = html[html.index('class="sdn-policy"'):]
    form = form[:form.index("</form>")]
    loaded = unescape(re.search(r'name="loaded" value="([^"]*)"', form).group(1))
    return {"form": form, "loaded": loaded}


def test_the_edit_control_round_trips_through_the_real_app(networks):  # noqa: F811
    import app as A
    from tests.conftest import TEST_PERSON
    c = A.app.test_client()
    page = c.get(f"/v2/sdn/responses?list={NET}").get_data(as_text=True)
    drawn = _policy_form(page)
    assert json.loads(drawn["loaded"]) == CL.DEFAULT_POLICY
    assert 'name="scan_default"' in drawn["form"]
    assert 'hx-post="/v2/sdn/policy?list=Default"' in drawn["form"]
    assert '<option value="drop_source" selected>' in drawn["form"]
    sent = {"list": NET, "loaded": drawn["loaded"], "scan_default": "rate_limit_source",
            "flood_default": "rate_limit_source", "flood_allowed": ["drop_source"],
            "unauthorised_flow_default": "remove_flow"}
    r = c.post("/v2/sdn/policy", data=sent)
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200, html
    assert r.headers["HX-Retarget"] == "#sdn" and r.headers["HX-Reswap"] == "outerHTML"
    assert CL.policy(NET)["rules"]["scan"] == {"allowed": ["rate_limit_source"],
                                               "default": "rate_limit_source"}
    assert {r_: CL.policy(NET)["rules"][r_]["allowed"] for r_ in CL.RULES} == SDN_LAB
    scan_row = html[html.index("<td>Scan</td>"):]
    scan_row = scan_row[:scan_row.index("</tr>")]
    assert ('<span class="mono">rate_limit_source</span> <span class="faint">(default)</span>'
            in scan_row) and "drop_source" not in scan_row
    (rec,) = [x for x in list_settings.changes(NET)["rows"]
              if x.get("kind") == "sdn_response_policy"]
    assert rec["actor"] == TEST_PERSON and rec["after"] == SDN_LAB
    assert rec["before"] == CL.DEFAULT_POLICY
    # The same form again, drawn before the save: the policy moved since, so nothing is saved.
    r = c.post("/v2/sdn/policy", data=dict(sent, scan_default="drop_source"))
    said = unescape(r.get_data(as_text=True))
    assert r.status_code == 409 and "moved since the page drew it" in said
    assert "drawn: scan: drop_source (default)" in said
    assert "now: scan: rate_limit_source (default)" in said
    assert CL.policy(NET)["rules"]["scan"]["allowed"] == ["rate_limit_source"]


def test_a_bad_policy_through_the_route_is_said_beside_save(networks):  # noqa: F811
    import app as A
    c = A.app.test_client()
    drawn = _policy_form(c.get(f"/v2/sdn/responses?list={NET}").get_data(as_text=True))
    r = c.post("/v2/sdn/policy", data={
        "list": NET, "loaded": drawn["loaded"], "scan_default": "remove_flow",
        "flood_default": "rate_limit_source", "unauthorised_flow_default": "remove_flow"})
    said = unescape(r.get_data(as_text=True))
    assert r.status_code == 409 and "HX-Retarget" not in r.headers
    assert "Not saved:" in said and "gives scan remove_flow, which answers unauthorised_flow" \
        in said
    assert CL.policy(NET)["rules"]["scan"]["allowed"] == CL.DEFAULT_POLICY["scan"]


# ── fail closed ───────────────────────────────────────────────────────────────────────────────

def _unreadable(monkeypatch):
    real = list_settings.value

    def value(network, key, default=None):
        if key == CL.POLICY_KEY:
            return {"scan": ["remove_flow"], "flood": ["drop_source"],
                    "unauthorised_flow": ["remove_flow"]}
        return real(network, key, default)
    monkeypatch.setattr(list_settings, "value", value)


def test_a_policy_that_cannot_be_read_allows_nothing_and_sends_nothing(world, monkeypatch):
    keep_pack(SCAN)
    _unreadable(monkeypatch)
    pol = CL.policy(NET)
    assert pol["ok"] is False and pol["rules"] == {}
    assert "gives scan remove_flow" in pol["error"] and "no response action is allowed" in \
        pol["error"]
    got = classify_as_person(world)
    assert got["error"] == "policy" and "nothing was sent" in got["detail"]
    assert world.sent == []
    assert CL.policy_refusal(NET, "scan", "drop_source") == pol["error"]


def test_a_policy_that_cannot_be_read_proposes_nothing_in_the_loop_and_says_so(
        world, monkeypatch):
    keep_pack(SCAN)
    _unreadable(monkeypatch)
    out = _pass(world)
    (resp,) = LP.awaiting(NET)["rows"]
    assert resp["action"] == "" and resp["why"] == LP.NOT_CLASSIFIED_WHY
    assert resp["classified"].startswith("no action proposed: Default's sdn_response_policy")
    import app as A
    html = unescape(A.app.test_client().get(f"/v2/sdn/responses?list={NET}")
                    .get_data(as_text=True))
    assert "The response policy cannot be read" in html and "No action is proposed" in html
    assert out["ok"]


def test_the_classify_and_auto_paths_never_read_the_old_table(monkeypatch, networks):  # noqa: F811
    """The control the order asks for: DEFAULT_ACTION no longer decides an action. With it
    emptied, the loop and a preview still take the policy's default."""
    monkeypatch.setattr(CL, "DEFAULT_ACTION", {})
    from tests.test_sdn_modes_loop import collected, observed
    LP.run_pass(NET, collect=collected, observe=observed(fired=["k1"]), now=lambda: 1.79e9,
                driver=lambda n, c: {"ok": False, "error": "unused"})
    (row,) = LP.awaiting(NET)["rows"]
    assert row["action"] == "drop_source"
