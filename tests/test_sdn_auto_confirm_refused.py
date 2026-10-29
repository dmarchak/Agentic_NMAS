"""AUTO's confirm refused before anything is sent reaches a person (C2195): under AUTO, a
detection whose preview passed and whose confirm was then refused, in `respond_to_threat` or in
`flow_ops.apply` before any request, is kept awaiting a person, as if AUTO were off, the
refusal said on it in its own words; it was once said only in the loop's log (C2159's class,
at the confirm instead of the preview).

**The data is C2159's** (tests/test_sdn_auto_preview_failed.py): the Lab 8 walk's second flood
on s1, whose L4 flows name 192.0.2.2, so AUTO may act on it, previewed and confirmed for real
through the flow-operation core against the lab's captured flow table
(tests/test_sdn_ops_v2.py's ``lab``: Ryu 4.34's ofctl_rest as tests/fixtures/sdn/lab8/ captured
it), its classification planted as passed. The remove_flow case is tests/test_sdn_respond.py's
unauthorised flow (the capture's cookie 0x4d45524300000001). Each refusal is a real one, made by
what a person or the network does between AUTO's preview and its confirm in one pass, at the
seam between the two calls (`between`), or before the pass for the hold, which the preview never
takes:

- **the response policy saved** without the action (`closed_loop.policy_refusal`);
- **the connection saved** with a southbound address the drop covers (`control_plane.refusal`);
- **the switch gone** from the controller, so the plan at apply cannot read its table
  (`flow_ops.plan` not ok);
- **the flow to remove changed** in the switch's table, so the plan's hash moved
  (`flow_ops.apply`'s hash comparison, both hashes named);
- **the switch held** by another operation (`device_ops.DeviceBusy`, the hold at apply).

For each: the response awaits a person (`loop.awaiting`), its ``why`` and ``auto_failed``
naming the refusal as the refusal words it, nothing written to the controller and nothing
applied; the log's line names it and the response. Needs attention's row names it and that AUTO
sent nothing; SDN › Responses draws it on the card; and a confirm that is not refused is still
applied by AUTO, through the same seam (the control). A confirm whose request reached the
controller (the controller answering it 400, so apply rolls back) is not this case: it stays
AUTO's response, its logged line saying it was rolled back.
"""
import threading

import pytest

from modules import attention as A
from modules.nsot import device_ops
from modules.sdn import closed_loop as CL
from modules.sdn import connections as C
from modules.sdn import detect as D
from modules.sdn import flow_intent as F
from modules.sdn import flow_ops as FO
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.test_sdn_auto_preview_failed import NET, auto_on, flow_named, one_awaiting
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_detect import T0, collect, save, scan_flows
from tests.test_sdn_ops_v2 import BASE, lab  # noqa: F401 - the fixture
from tests.test_sdn_respond import switch_with
from tests.test_sdn_source_from_topology import H2

HOLDER = "op@example.com"
#: The capture's unauthorised flow (tests/test_sdn_respond.py's).
UNAUTHORISED = 0x4d45524300000001


def run(monkeypatch, d, action="drop_source", params=None, driver=None):
    """One loop pass over *d*, AUTO on, its classification planted as passed proposing
    *action* (``drop_source`` on the detection's own source by default); the preview and the
    confirm are the real ones."""
    params = {"source": d["source"]} if params is None else params
    monkeypatch.setattr(LP, "classify", lambda network, det, job, **kw: {
        "action": action, "risk": "low", "params": dict(params),
        "classification": {"threat_type": "flood"}, "person": False, "why": "",
        "refused_call": "", "words": "planted: passed"})
    out = LP.run_pass(NET, driver=driver,
                      collect=lambda: {"network": NET, "summary": {}, "state": "ok"},
                      observe=lambda network, collected: {
                          "ok": True, "fired": [d["key"]], "resolved": [], "detections": [d]})
    assert out["ok"], out["error"]
    return out


def between(monkeypatch, step):
    """Run *step* between AUTO's preview (once it passed) and its confirm, in the pass: what a
    person or the network does in that time. Answers the list of the calls' answers."""
    real = CL.respond_to_threat
    seen = []

    def respond(network, detection, action_id=None, params=None, **kw):
        got = real(network, detection, action_id, params, **kw)
        seen.append(got)
        if kw.get("confirm") is None and got.get("ok"):
            step()
        return got

    monkeypatch.setattr(CL, "respond_to_threat", respond)
    return seen


def policy_saved():
    """A person saves the policy with flood answered by rate_limit_source alone."""
    CL.save_policy(NET, dict(CL.DEFAULT_POLICY, flood=["rate_limit_source"]),
                   actor="admin@example.com", actor_verified="access")


def southbound_saved():
    """A person saves the connection with its switches reaching it on 192.0.2.2."""
    C.save_connection(NET, {"name": "lab-controller", "kind": "ryu", "url": BASE,
                            "southbound": f"{H2}:6653"}, actor=HOLDER)


#: Each refusal's words, the refusal's own, read off its code by hand: the policy's
#: (`policy_refusal`), the control plane's (`control_plane.refusal`, the drop's match
#: ``ipv4_src`` covering the southbound address) and the plan's at apply (the fake's 404 for a
#: switch it does not hold, as C2159's preview says it).
REFUSED = {
    "policy-saved": ("AUTO could not confirm drop_source: drop_source is outside Default's "
                     "response policy for flood, which allows rate_limit_source: nothing was "
                     "sent"),
    "southbound-saved": ("AUTO could not confirm drop_source: change 1 adds a flow whose match "
                         "covers the control channel: the controller's address 192.0.2.2 "
                         "(ipv4_src 192.0.2.2). No response may cover it, in any mode (C2022): "
                         "nothing was sent"),
    "switch-gone": ("AUTO could not confirm drop_source: the flow table of switch 1 could not "
                    "be read: HTTP 404: the controller has no switch 1 (0000000000000001)"),
}


def assert_awaits_a_person(out, writes, failed, action="drop_source", params=None):
    """The response awaits a person with *failed* on it, nothing was sent, and the log says
    so, naming the response."""
    assert out["applied"] == [] and writes == [], "nothing sent"
    row = one_awaiting()
    assert out["proposed"] == [row["id"]]
    assert row["auto_failed"] == failed
    assert row["why"] == (f"HITL for this one: {failed}; nothing was sent, and a person "
                          "previews it again and confirms or dismisses it")
    assert (row["action"], row["classified"]) == (action, "planted: passed")
    if params is not None:
        assert row["params"] == params
    said = [x for x in out["lines"] if x["step"] == "respond"]
    assert [x["words"] for x in said] == [
        f"{failed}: nothing was sent; awaiting a person ({row['id']})"]
    assert said[0]["response"] == row["id"]
    return row


@pytest.mark.parametrize("case,step", [
    ("policy-saved", lambda lab: policy_saved()),
    ("southbound-saved", lambda lab: southbound_saved()),
    ("switch-gone", lambda lab: setattr(lab["fake"], "dpids", [])),
], ids=["policy-saved", "southbound-saved", "switch-gone"])
def test_a_confirm_refused_after_a_passing_preview_awaits_a_person(lab, monkeypatch, case,  # noqa: F811,E501
                                                                    step):
    auto_on()
    d = flow_named()
    assert MD.decide(NET, "low", detection=d, action="drop_source")["auto"] is True, \
        "premise: AUTO would act on it"
    seen = between(monkeypatch, lambda: step(lab))
    out = run(monkeypatch, d)
    preview, done = seen
    assert preview["ok"], f"premise: AUTO's preview passed ({preview['error']})"
    assert (done["outcome"], done.get("sent") or []) == ("refused", []), \
        "premise: the confirm was refused before any request"
    assert_awaits_a_person(out, lab["fake"].writes, REFUSED[case], params={"source": H2})


def test_a_switch_held_by_another_operation_awaits_a_person(lab, monkeypatch):  # noqa: F811
    """Another operation holds the switch (a person's flow edit, in another thread, as a
    request would): the preview reads and passes, the hold at apply is refused, naming who
    holds it."""
    auto_on()
    d = flow_named()
    took, done = threading.Event(), threading.Event()

    def other():
        with device_ops.hold(NET, FO.hold_name("lab-controller", 1), "sdn flows", HOLDER,
                             detail="1 request(s) to lab-controller"):
            took.set()
            done.wait(30)

    t = threading.Thread(target=other)
    t.start()
    try:
        assert took.wait(30), "premise: the other operation holds the switch"
        out = run(monkeypatch, d)
    finally:
        done.set()
        t.join(30)
    row = one_awaiting()
    failed = row["auto_failed"]
    # The hold's own words (`device_ops.describe`): who holds it, what for, and that nothing
    # was sent; its start and age are the clock's, so the words are matched around them.
    head = (f"AUTO could not confirm drop_source: refused: "
            f"{FO.hold_name('lab-controller', 1)} is being ")
    assert failed.startswith(head), failed
    assert f" by {HOLDER}, started " in failed and "(1 request(s) to lab-controller)" in failed
    assert failed.endswith("this one was refused, not queued, and nothing was sent to it"), \
        failed
    assert_awaits_a_person(out, lab["fake"].writes, failed, params={"source": H2})


def test_a_flow_changed_since_the_preview_moves_the_hash_and_awaits_a_person(networks,  # noqa: F811,E501
                                                                              monkeypatch):
    """The unauthorised flow AUTO previewed removing is changed on the switch before its
    confirm (its actions now output to port 3): the plan made at apply binds a different hash,
    and `flow_ops.apply` refuses, naming both."""
    save()
    flows = scan_flows(0)
    dets = D.unauthorised(collect(T0, flows=flows), F.intent(NET))["detections"]
    d = next(x for x in dets if x["measurement"]["cookie"] == F.cookie_hex(UNAUTHORISED))
    fake = switch_with(flows)
    auto_on()
    assert MD.decide(NET, "medium", detection=d, action="remove_flow")["auto"] is True, \
        "premise: AUTO would act on it"

    def changed():
        hit = next(f for f in fake.table[1] if f["cookie"] == UNAUTHORISED)
        hit["actions"] = [{"type": "OUTPUT", "port": 3}]

    seen = between(monkeypatch, changed)
    out = run(monkeypatch, d, action="remove_flow", params={}, driver=fake.driver)
    preview, done = seen
    assert preview["ok"], f"premise: AUTO's preview passed ({preview['error']})"
    assert (done["outcome"], done["at"], done["sent"]) == ("refused", "hash", [])
    was, now = preview["plan"]["hash"], done["plan"]["hash"]
    assert was != now
    failed = (f"AUTO could not confirm remove_flow: the preview's hash was {was[:12]}, and the "
              f"plan made now is {now[:12]}: the switch's table or the requests moved since the "
              "preview, so nothing was sent; preview again")
    assert_awaits_a_person(out, fake.writes, failed, action="remove_flow")


def test_the_refusal_is_a_needs_attention_row_naming_it(lab, monkeypatch):  # noqa: F811
    auto_on()
    between(monkeypatch, policy_saved)
    run(monkeypatch, flow_named())
    row = one_awaiting()
    (got,) = A.sdn_responses_source(found={NET: LP.awaiting(NET)})["rows"]
    assert got["id"] == f"sdn_responses:{NET}:{row['id']}"
    # How it clears: a person applies its response or dismisses it, never the next pass.
    assert got["clears"]["ways"] == ["resolves"] and "dismissed" in got["clears"]["when"]
    assert f"; {REFUSED['policy-saved']}, so AUTO sent nothing" in got["cause"], got["cause"]
    assert got["action"]["href"].endswith(f"incident={row['id']}#sdn-i-{row['id']}")
    assert "confirm it, or dismiss the incident with a reason" in got["action"]["label"]


def test_the_refusal_is_drawn_on_its_card(lab, monkeypatch):  # noqa: F811
    from html import unescape

    auto_on()
    between(monkeypatch, lambda: setattr(lab["fake"], "dpids", []))
    run(monkeypatch, flow_named())
    row = one_awaiting()
    lab["fake"].dpids = [1]
    html = unescape(lab["client"].get(f"/v2/sdn/responses?list={NET}").get_data(as_text=True))
    assert row["id"] in html and row["auto_failed"] in html


def test_a_confirm_not_refused_is_applied_by_auto_as_before(lab, monkeypatch):  # noqa: F811
    """The control, through the same seam: nothing moves between the two calls, and AUTO
    applies its response, awaiting nobody."""
    auto_on()
    seen = between(monkeypatch, lambda: None)
    out = run(monkeypatch, flow_named())
    assert seen[1]["outcome"] == "verified", seen[1]["error"]
    assert out["proposed"] == [] and LP.awaiting(NET)["rows"] == []
    (done,) = out["applied"]
    assert done["id"] and lab["fake"].writes, "AUTO applied it"
    said = [x for x in out["lines"] if x["step"] == "respond"]
    assert len(said) == 1 and said[0]["outcome"] == "verified"


def test_a_confirm_whose_request_was_sent_is_not_this_case(lab, monkeypatch):  # noqa: F811
    """A request that reached the controller is not a refusal before the send: the controller
    answers the drop's add 400, so apply rolls back, and the response stays AUTO's applied
    response, its logged line saying it was rolled back, never "AUTO could not confirm" and
    "nothing was sent"."""
    auto_on()
    lab["fake"].fail = {"/stats/flowentry/add": 400}
    seen = between(monkeypatch, lambda: None)
    out = run(monkeypatch, flow_named())
    done = seen[1]
    assert done["outcome"] == "rolled_back" and done["sent"], "premise: a request was sent"
    assert out["proposed"] == [] and LP.awaiting(NET)["rows"] == []
    assert [a["outcome"] for a in out["applied"]] == ["rolled_back"]
    (said,) = [x for x in out["lines"] if x["step"] == "respond"]
    assert said["outcome"] == "rolled_back" and ": rolled back (" in said["words"], said
    assert "nothing was sent" not in said["words"]
