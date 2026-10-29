"""AUTO's own preview failing reaches a person (C2159): under AUTO, a detection whose response
AUTO decided to apply and could not preview is kept awaiting a person, as if AUTO were off, the
failure said on it; it was once said only in the loop's log, so a threat was seen by nobody.

**The data is the Lab 8 walk's own** (tests/test_sdn_source_from_topology.py's: the walk's second
flood on s1, whose L4 flows name 192.0.2.2, so AUTO may act on it, C2147), previewed for real
through the flow-operation core against the lab's captured flow table (tests/test_sdn_ops_v2.py's
``lab``: Ryu 4.34's ofctl_rest as tests/fixtures/sdn/lab8/ captured it). The failures are real
ones of the preview, each a minimal edit made where it is used: the switch no longer on the
controller (its DPID gone from the controller's switch list, so its flow table answers 404), and
the response's connection not saved in the network (no driver). The classification is planted
as passed (the AI call is the provider's; tests/test_sdn_loop_live.py drives it). The network is
marked lab and AUTO is on, allowing medium (so a decision is never the risk's).

- **The loop** (`loop.run_pass`): the response is kept awaiting a person, the HITL path's own
  record (`loop.awaiting`), its ``why`` and ``auto_failed`` naming AUTO's preview failure,
  nothing written to the controller and nothing applied; the log's line names the failure and
  the response.
- **Needs attention** (`attention.sdn_responses_source`): one row for it, its cause naming the
  failure and that AUTO sent nothing, its action opening the incident to preview and confirm or
  dismiss, standing until a person does.
- **SDN › Responses** draws the failure on the incident's card.
- **A preview that passes** is applied by AUTO as before (the control).
"""
import time

import pytest

from modules import attention as A
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_modes_loop import mark_lab
from tests.test_sdn_ops_v2 import lab  # noqa: F401 - the fixture
from tests.test_sdn_source_from_topology import H2, H5, plus, stored, walk_flood

NET = "Default"
ACTION = "drop_source"


def auto_on(network=NET):
    mark_lab(network)
    MD.turn_on(network, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=time.time() + 600, allowed_risk="medium")


def flow_named(connection="lab-controller"):
    """The walk's second flood on s1, its flows naming its source, on *connection*."""
    d, _c, _s = walk_flood("walk-flood-2-s1", stored(edit=plus(H5)))
    assert d["source"] == H2 and "source_from" not in d, "premise: the flows name it"
    return dict(d, network=NET, connection=connection)


def run(monkeypatch, d):
    """One loop pass over *d*, AUTO on, its classification planted as passed proposing
    ``drop_source`` on the detection's own source; the preview and apply are the real ones."""
    monkeypatch.setattr(LP, "classify", lambda network, det, job, **kw: {
        "action": ACTION, "risk": "low", "params": {"source": det["source"]},
        "classification": {"threat_type": "flood"}, "person": False, "why": "",
        "refused_call": "", "words": "planted: passed"})
    out = LP.run_pass(NET, collect=lambda: {"network": NET, "summary": {}, "state": "ok"},
                      observe=lambda network, collected: {
                          "ok": True, "fired": [d["key"]], "resolved": [], "detections": [d]})
    assert out["ok"], out["error"]
    return out


def one_awaiting():
    """The one response awaiting a person on the network (asserted: none is the defect)."""
    rows = LP.awaiting(NET)["rows"]
    assert len(rows) == 1, f"{len(rows)} responses await a person, not 1: {rows}"
    return rows[0]


def gone(lab):  # noqa: F811
    """The switch left the controller: its DPID no longer in Ryu's switch list."""
    lab["fake"].dpids = []
    return "lab-controller"


def unsaved(lab):  # noqa: F811
    """The response's connection is not one saved in the network."""
    return "lab-controller-gone"


#: Each failure's words, the preview's own (`flow_ops.plan`'s), read off the fake's 404 for a
#: switch it does not hold and `connections.driver_for`'s refusal by hand.
FAILED = {
    "switch-gone": ("AUTO could not preview drop_source: the flow table of switch 1 could not "
                    "be read: HTTP 404: the controller has no switch 1 (0000000000000001)"),
    "connection-unsaved": ("AUTO could not preview drop_source: Default has no controller "
                           "connection 'lab-controller-gone'"),
}


@pytest.mark.parametrize("fail,case", [(gone, "switch-gone"), (unsaved, "connection-unsaved")],
                         ids=["switch-gone", "connection-unsaved"])
def test_a_failed_auto_preview_awaits_a_person_with_its_failure(lab, monkeypatch, fail, case):  # noqa: F811,E501
    auto_on()
    d = flow_named(fail(lab))
    assert MD.decide(NET, "low", detection=d, action=ACTION)["auto"] is True, \
        "premise: AUTO would act on it"
    out = run(monkeypatch, d)
    assert out["applied"] == [] and lab["fake"].writes == [], "nothing sent"
    row = one_awaiting()
    assert out["proposed"] == [row["id"]]
    failed = row["auto_failed"]
    assert failed == FAILED[case]
    assert row["why"] == (f"HITL for this one: {failed}; nothing was sent, and a person "
                          "previews it again and confirms or dismisses it")
    assert (row["action"], row["params"], row["classified"]) == (
        ACTION, {"source": H2}, "planted: passed")
    said = [x for x in out["lines"] if x["step"] == "respond"]
    assert [x["words"] for x in said] == [
        f"{failed}: nothing was sent; awaiting a person ({row['id']})"]
    assert said[0]["response"] == row["id"]


def test_the_failure_is_a_needs_attention_row_naming_it(lab, monkeypatch):  # noqa: F811
    auto_on()
    d = flow_named(gone(lab))
    run(monkeypatch, d)
    row = one_awaiting()
    (got,) = A.sdn_responses_source(found={NET: LP.awaiting(NET)})["rows"]
    assert got["id"] == f"sdn_responses:{NET}:{row['id']}"
    # How it clears: a person applies its response or dismisses it, never the next pass.
    assert got["clears"]["ways"] == ["resolves"] and "dismissed" in got["clears"]["when"]
    assert f"; {row['auto_failed']}, so AUTO sent nothing" in got["cause"], got["cause"]
    assert f"proposed {ACTION} at " in got["cause"]
    assert got["action"]["href"].endswith(f"incident={row['id']}#sdn-i-{row['id']}")
    assert "confirm it, or dismiss the incident with a reason" in got["action"]["label"]


def test_the_failure_is_drawn_on_its_card(lab, monkeypatch):  # noqa: F811
    from html import unescape

    auto_on()
    run(monkeypatch, flow_named(gone(lab)))
    row = one_awaiting()
    html = unescape(lab["client"].get(f"/v2/sdn/responses?list={NET}").get_data(as_text=True))
    assert row["id"] in html and row["auto_failed"] in html


def test_a_preview_that_passes_is_applied_by_auto_as_before(lab, monkeypatch):  # noqa: F811
    auto_on()
    out = run(monkeypatch, flow_named())
    assert out["proposed"] == [] and LP.awaiting(NET)["rows"] == []
    (done,) = out["applied"]
    assert done["id"] and lab["fake"].writes, "the control: AUTO applied it"
