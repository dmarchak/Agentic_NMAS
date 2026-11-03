"""Rate-limit this source… on a watched large-packet stream (C2313's condition, the operator's
decision of 2026-11-03, option (i); `loop.propose_from_watch`, routes/sdn_v2.py `watch_propose`,
`closed_loop.person_proposal_refusal`, `closed_loop.answered_rule`).

The walk's floods are watched under C2313's rule (one iperf UDP stream of 1,512 B packets is the
shape of RC-UDP1, which is benign, and the counters cannot tell intent), so only the automatic
proposal goes: a person may still make the stream a response awaiting a person, which is then
previewed, confirmed by hash, applied, verified and recorded as any response is. Nothing is sent
by pressing the control, and no AI is asked anywhere on this path.

**The data is the Lab 8 walk's own**: its first flood on s1 port 2 (h2 to h4, its flows matching
MAC addresses only), judged again by the rule over the evidence the walk kept with Ryu 4.34's
captured topology (tests/test_sdn_source_from_topology.py's `walk_flood`: High packet rate,
basis ``large_packets``, h2 named from the topology), watched through the loop's own pass, on
the route tests' controller (tests/test_sdn_ops_v2.py's ``lab``: Ryu's captured flow table and
topology REST through the real driver). The policy is the network's, saved through
`closed_loop.save_policy`.

- **The press** as a verified person makes exactly one response awaiting a person: the rate
  limit at the catalogue's defaults, its why naming the person, its detection the watched one
  with its evidence; the watching row is closed as proposed by a person; nothing is written to
  the controller and no AI is called.
- **Only a verified person**: an unverified request and a service are refused by the gate, and
  the function itself refuses an actor not verified; nothing is made.
- **The policy**: checked as the flood rule's (the stream is the flood rule's held candidate);
  one forbidding the flood rule's rate limit draws the control disabled with its reason, and
  refuses the POST naming the action, the rule and the actions it allows; the confirm checks
  the same rule again.
- **The response it makes** previews and confirms through the normal routes, end to end.
- **Offered only where it can act**: no control on a watched stream that is not one of large
  packets (refused if posted), and drawn disabled on one naming no source (a link port).
- **Not watched again**: the stream firing again while its response awaits a person opens no
  second watching row.
"""
import json
import re
from html import unescape

import pytest

from modules import identity
from modules.sdn import closed_loop as CL
from modules.sdn import flow_intent as F
from modules.sdn import loop as LP
from tests.conftest import TEST_PERSON
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_ops_v2 import form_fields, lab  # noqa: F401 - the fixture
from tests.test_sdn_source_from_topology import H2, stored, walk_flood

NET = "Default"
NO_DRIVER = lambda n, c: {"ok": False, "error": "unused"}  # noqa: E731
#: The policy where the flood rule may only drop (a minimal edit of the default: the flood
#: rule's rate limit taken out).
NO_FLOOD_RATE_LIMIT = {"scan": ["drop_source", "rate_limit_source"], "flood": ["drop_source"],
                       "unauthorised_flow": ["remove_flow"]}


@pytest.fixture
def no_ai(monkeypatch):
    """Every way the SDN code asks AI, refused loudly: this path makes no AI call."""
    def called(*a, **k):
        pytest.fail("an AI call was made on the person's proposal path")
    for name in ("classify_threat", "classify_pack", "classify_packs_batch"):
        monkeypatch.setattr(CL, name, called)
    monkeypatch.setattr(LP, "classify", called)


def stream(key="walk-flood-1-s1"):
    """The walk's flood *key*, a large-packet stream under C2313's rule, on the route tests'
    controller and network."""
    d, _c, _s = walk_flood(key, stored())
    assert (d["rule"], d["basis"]) == ("high_rate", "large_packets"), "premise: watched"
    return dict(d, network=NET, connection="lab-controller")


def watched(d) -> dict:
    """*d* watched by the loop's own pass (`_watch_pass`): the one watching row it opens."""
    out = LP.run_pass(NET, collect=lambda: {"network": NET, "summary": {}, "state": "ok"},
                      observe=lambda n, c: {"ok": True, "fired": [d["key"]], "resolved": [],
                                            "detections": [d],
                                            "thresholds": {"sdn_flood_window_seconds": 30},
                                            "collected_at": d["at"]},
                      driver=NO_DRIVER)
    assert out["ok"], out["error"]
    (row,) = LP.watching(NET)["rows"]
    assert out["watching"] == [row["id"]] and LP.awaiting(NET)["rows"] == []
    return row


def page(lab) -> str:  # noqa: F811
    return lab["client"].get(f"/v2/sdn/responses?list={NET}").get_data(as_text=True)


def control(html: str, wid: str) -> str:
    """The Rate-limit this source… button of watching row *wid*, as drawn."""
    forms = re.findall(rf'<form class="op-act sdn-propose" hx-post="/v2/sdn/watch/{wid}/'
                       r'propose[?"].*?</form>', html, re.S)
    assert len(forms) == 1, html[html.find(f'id="sdn-i-{wid}"'):][:4000]
    (button,) = re.findall(r"<button.*?</button>", forms[0], re.S)
    return button


def press(lab, wid):  # noqa: F811
    return lab["client"].post(f"/v2/sdn/watch/{wid}/propose", data={"list": NET})


def closings(wid) -> list:
    return [r for r in LP._read(NET, LP.PENDING_FILE)["rows"]
            if r.get("id") == wid and r.get("kind") in LP.WATCH_CLOSED]


# ───────────────────────────────────────────────────────────────────────────── the press

def test_the_press_makes_one_response_awaiting_a_person_and_sends_nothing(lab, no_ai,  # noqa: F811,E501
                                                                          monkeypatch):
    from modules.sdn import topology as SDN

    d = stream()
    # The SDN reader's stored topology, the captured one for the route tests' controller: the
    # response is proposed at the ingress it tells (h2 on s1 port 2).
    topo = stored(name="lab-controller")
    monkeypatch.setattr(SDN, "stored", lambda network, now=None, cached=None: topo)
    w = watched(d)
    button = control(page(lab), w["id"])
    assert "Rate-limit this source…" in button and " disabled " not in button
    assert "data-refused" not in button
    r = press(lab, w["id"])
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200, html
    (row,) = LP.awaiting(NET)["rows"]
    assert (row["action"], row["risk"], row["params"]) == (
        "rate_limit_source", "low", CL.RATE_LIMIT_DEFAULT)
    assert row["why"] == f"proposed by {TEST_PERSON} from a watched large-packet stream"
    kept = {k: v for k, v in row["detection"].items() if k != "incident"}
    assert kept == json.loads(json.dumps(d)), "the watched detection, its evidence kept"
    assert row["detection"]["evidence"] == d["evidence"] and row["detection"]["source"] == H2
    assert row["incident"]["key"] == w["incident"]["key"]
    assert row["incident"]["ingress_known"] is True and row["incident"]["ingress_port"] == 2
    assert LP.watching(NET)["rows"] == [], "the watching row closed"
    (closed,) = closings(w["id"])
    assert (closed["kind"], closed["why"], closed["actor"], closed["response"]) == (
        "proposed_by_person", "proposed by a person", TEST_PERSON, row["id"])
    assert lab["fake"].writes == [], "nothing sent to the switch"
    # The region is drawn again with the new response open, its proposal and why.
    assert re.search(rf'<details class="sdn-inc" id="sdn-i-{row["id"]}"[^>]* open>', html)
    assert f"proposed by {TEST_PERSON} from a watched large-packet stream" in html
    # A second press finds no watching row open: refused, nothing more made.
    again = press(lab, w["id"])
    assert again.status_code == 409 and len(LP.awaiting(NET)["rows"]) == 1
    assert f"no watching row {w['id']} is open on {NET}" in unescape(again.get_data(as_text=True))


# ───────────────────────────────────────────────────────────────────────────── only a person

@pytest.mark.parametrize("who", [
    identity.Identity(outcome="no_header", reason="no access assertion"),
    identity.Identity(actor="service:ci", kind="service", service_id="ci", verified=True,
                      outcome="ok", peer="127.0.0.1", peer_trusted=True),
], ids=["unverified", "service"])
def test_anyone_but_a_verified_person_is_refused_and_nothing_is_made(lab, monkeypatch, no_ai,  # noqa: F811,E501
                                                                     who):
    w = watched(stream())
    monkeypatch.setattr(identity, "identify", lambda _request: who)
    r = press(lab, w["id"])
    assert r.status_code in (401, 403), r.status_code
    assert LP.awaiting(NET)["rows"] == [] and [x["id"] for x in LP.watching(NET)["rows"]] == [
        w["id"]]
    assert closings(w["id"]) == [] and lab["fake"].writes == []


def test_the_function_refuses_an_actor_not_verified(networks, no_ai):  # noqa: F811
    """Behind the gate, the function refuses too: an actor not verified, unverified, none, or a
    verified service (were the gate set to let a service through)."""
    w = watched(stream())
    for actor, how, kind in ((TEST_PERSON, "none", "person"),
                             (identity.UNVERIFIED, "access", "person"), ("", "access", "person"),
                             ("service:ci", "access", "service")):
        with pytest.raises(LP.ProposalRefused, match="by a verified person"):
            LP.propose_from_watch(NET, w["id"], actor=actor, actor_verified=how,
                                  actor_kind=kind)
    assert LP.awaiting(NET)["rows"] == [] and len(LP.watching(NET)["rows"]) == 1


# ───────────────────────────────────────────────────────────────────────────── the policy

POLICY_WORDS = ("a large-packet stream is checked as the flood rule's held candidate: "
                "rate_limit_source is outside Default's response policy for flood, which allows "
                "drop_source")


def test_a_policy_forbidding_the_flood_rule_s_rate_limit_disables_and_refuses_it(lab, no_ai):  # noqa: F811,E501
    w = watched(stream())
    CL.save_policy(NET, NO_FLOOD_RATE_LIMIT, actor=TEST_PERSON, actor_verified="access")
    button = unescape(control(page(lab), w["id"]))
    assert ' disabled aria-disabled="true"' in button
    assert f'data-refused="Not available: {POLICY_WORDS}"' in button
    r = press(lab, w["id"])
    assert r.status_code == 409
    assert f"{POLICY_WORDS}: nothing was proposed" in unescape(r.get_data(as_text=True))
    assert LP.awaiting(NET)["rows"] == [] and len(LP.watching(NET)["rows"]) == 1
    assert closings(w["id"]) == []


# ───────────────────────────────────────────────────────────────────────────── end to end

def test_the_response_it_makes_previews_and_confirms_through_the_normal_routes(lab, no_ai):  # noqa: F811,E501
    import tests.test_sdn_lab8 as L8

    lab["fake"].topology = L8.captured_topology()
    w = watched(stream())
    assert press(lab, w["id"]).status_code == 200
    (row,) = LP.awaiting(NET)["rows"]
    c = lab["client"]
    card = c.post(f"/v2/sdn/response/{row['id']}/preview",
                  data={"list": NET, "action": "rate_limit_source", "hard_timeout": "60",
                        "rate": "1000", "unit": "kbps", "burst": "100"})
    html = card.get_data(as_text=True)
    assert card.status_code == 200, unescape(html)
    fields = form_fields(html)
    ask = json.loads(fields["ask"])
    assert ask["action"] == "rate_limit_source"
    assert (ask["detection"]["rule"], ask["detection"]["basis"]) == ("high_rate",
                                                                     "large_packets")
    meter, *flows = ask["changes"]
    assert meter["do"] == "add_meter" and flows
    assert {f["flow"]["match"]["ipv4_src"] for f in flows} == {H2}
    assert lab["fake"].writes == [], "the preview sends nothing"
    done = c.post("/v2/sdn/response/confirm", data=fields)
    assert "Done, verified" in done.get_data(as_text=True), unescape(done.get_data(as_text=True))
    assert LP.awaiting(NET)["rows"] == [], "closed as confirmed"
    (op,) = F.operations(NET)["rows"]
    assert (op["response"]["action"], op["mode"], op["actor"]) == (
        "rate_limit_source", "hitl", TEST_PERSON)
    assert op["response"]["detection"]["key"] == row["detection"]["key"]


def test_the_confirm_checks_the_flood_rule_s_policy_again(lab, no_ai):  # noqa: F811
    """`answered_rule` at the confirm: the policy saved between the preview and the confirm
    forbidding the flood rule's rate limit refuses it, nothing sent."""
    import tests.test_sdn_lab8 as L8

    lab["fake"].topology = L8.captured_topology()
    w = watched(stream())
    press(lab, w["id"])
    (row,) = LP.awaiting(NET)["rows"]
    c = lab["client"]
    fields = form_fields(c.post(f"/v2/sdn/response/{row['id']}/preview",
                                data={"list": NET}).get_data(as_text=True))
    CL.save_policy(NET, NO_FLOOD_RATE_LIMIT, actor=TEST_PERSON, actor_verified="access")
    r = c.post("/v2/sdn/response/confirm", data=fields)
    assert r.status_code == 409 and lab["fake"].writes == []
    assert ("rate_limit_source is outside Default&#39;s response policy for flood, which allows "
            "drop_source: nothing was sent") in r.get_data(as_text=True)
    assert len(LP.awaiting(NET)["rows"]) == 1


# ───────────────────────────────────────────────────────────────────────────── where offered

def test_a_watched_stream_not_of_large_packets_offers_no_control_and_is_refused(lab, no_ai):  # noqa: F811,E501
    """A rate-only High packet rate (basis ``rate``, the scan fallback's): no control drawn;
    posted anyway, refused naming its basis."""
    d = dict(stream(), basis="rate", key="k-rate-only")
    w = watched(d)
    html = page(lab)
    assert f'id="sdn-i-{w["id"]}"' in html, "premise: its row is drawn"
    assert f"/v2/sdn/watch/{w['id']}/propose" not in html
    r = press(lab, w["id"])
    assert r.status_code == 409
    assert ("only a watched large-packet stream (High packet rate, basis large_packets) is "
            "proposed by a person; this one is high_rate, basis rate") in unescape(
                r.get_data(as_text=True))
    assert LP.awaiting(NET)["rows"] == []


def test_a_stream_naming_no_source_draws_the_control_disabled_saying_why(lab, no_ai):  # noqa: F811,E501
    """The walk's flood on s2 port 3, a link: no source to rate-limit there."""
    d = stream("walk-flood-1-s2")
    assert d["source"] is None and d["source_from"]["state"] == "link", "premise"
    w = watched(d)
    button = unescape(control(page(lab), w["id"]))
    assert ' disabled aria-disabled="true"' in button
    assert ('data-refused="Not available: the watched stream names no source to rate-limit: '
            "not named: port 3 is a link to switch 0000000000000001") in button
    assert press(lab, w["id"]).status_code == 409 and LP.awaiting(NET)["rows"] == []


# ───────────────────────────────────────────────────────────────────────────── not watched again

def _pass(d, fired=True):
    """One loop pass in which *d* fires again (*fired*), or resolves."""
    return LP.run_pass(NET, collect=lambda: {"network": NET, "summary": {}, "state": "ok"},
                       observe=lambda n, c: {
                           "ok": True, "fired": [d["key"]] if fired else [],
                           "resolved": [] if fired else [d["key"]],
                           "detections": [d] if fired else [],
                           "thresholds": {"sdn_flood_window_seconds": 30},
                           "collected_at": d["at"]},
                       driver=NO_DRIVER)


def test_the_stream_firing_again_while_its_response_awaits_is_not_watched_again(lab, no_ai):  # noqa: F811,E501
    """Its response is the stream's: resolving, the response is marked inactive (as any is);
    firing again, it is active again, and no second watching row opens beside it."""
    d = stream()
    w = watched(d)
    press(lab, w["id"])
    (row,) = LP.awaiting(NET)["rows"]
    out = _pass(d, fired=False)
    assert out["ok"] and out["inactive"] == [row["id"]]
    assert LP.awaiting(NET)["rows"][0]["inactive_since"]
    out = _pass(d)
    assert out["ok"] and out["watching"] == [] and LP.watching(NET)["rows"] == []
    (again,) = LP.awaiting(NET)["rows"]
    assert again["id"] == row["id"] and again["inactive_since"] == "", "active again"
