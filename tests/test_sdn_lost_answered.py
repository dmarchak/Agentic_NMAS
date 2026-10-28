"""A lost response whose threat a newer response already answers is no longer a row, and is
not put back (C2070; `reapply.answered_by`, `reapply.as_collected`,
`attention.sdn_mitigation_source`, `reapply.build`).

After a lost response's detection fires again and is answered as new (C2005), and that newer
response is applied, C2018's Needs attention row for the old one stayed up until its hard
timeout, naming a Re-apply… nobody needs. The row now resolves once a newer response in force
covers the same threat on that switch, by the loop's own test (`loop.holds`, judged against
the SDN reader's stored read, and `loop.covering`: the same rule, connection and switch, and
the same detection or every source it names). While nothing covers it the row's words are
C2018's, unchanged.

**The data.** tests/test_sdn_reapply.py's switch: `tests.sdn_fakes.FakeRyu` seeded with Ryu
4.34's captured flow table, a response applied through the real code
(`closed_loop.respond_to_threat`), a restart the table put back and its meters emptied, the
SDN reader's run stored as the scheduler stores it. A second switch, where a case needs one,
answers its port counters and description from the same capture. The MAC case is the Lab 8
walk's flood over MAC-only flows (C2002; tests/fixtures/sdn/lab8/l2_only_s1.json and the
controller's captured topology), which names no address and is covered by its own key, its
port.

- **Resolves:** a newer drop of the same source (IPv4, IPv6) for the same rule on the same
  switch, in force as read: the row is gone and What was checked names the lost response and
  the one answering it; the MAC-keyed flood answered again on the same port likewise.
- **Stays, its words unchanged:** nothing newer; a newer response for another source, rule or
  switch, or on another port (the MAC case); one not in force (its flow gone too, or a rate
  limit's meter read missing); one on a controller not answering since (its read is carried,
  so nothing on it is judged in force).
- **Re-apply on a covered threat:** refused at the preview, naming the newer response, sending
  nothing, through the route as a person on a stale page presses it; a preview taken before
  the newer response and confirmed after it is refused by the hash and sends nothing.
"""
import json
import re
import time
from html import unescape

import pytest
import requests

from modules import attention as A
from modules.sdn import closed_loop as CL
from modules.sdn import detect as D
from modules.sdn import flow_intent as F
from modules.sdn import loop as LP
from modules.sdn import reapply as RA
from tests.sdn_fakes import captured, lab8
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_lab8 import _mac_only_flood, captured_topology, features_of, flows_of
from tests.test_sdn_reapply import (CONN, NET, SW, T, Switch, detection, drop, form_fields,
                                    rate_limit, read, rows)
from tests.test_sdn_reapply import lab  # noqa: F401 - the fixture
from tests.test_sdn_v2 import WITH_PEER, store_read


def respond(d, at, action="drop_source"):
    """Detection *d* answered by *action* through the real code, applied at *at*."""
    preview = CL.respond_to_threat(NET, d, action)
    assert preview["ok"], preview["error"]
    done = CL.respond_to_threat(NET, None, action, confirm={
        "ask": preview["ask"], "hash": preview["plan"]["hash"]}, actor="op@example.com",
        actor_verified="access", sleep=lambda s: None, now=lambda: at)
    assert done["outcome"] == "verified", done["error"]
    return done


def mitigation(at):
    return A.sdn_mitigation_source(found=read(at), now=at)


def drawn(r):
    """What a row says and offers, the time of the read it names aside (it moves with each
    read)."""
    return dict({k: r[k] for k in ("level", "what", "operands", "action", "clears_at",
                                   "clears")},
                cause=re.sub(r"as the SDN reader read it at \S+", "as the SDN reader read it",
                             r["cause"]))


def hold_of(op_id, found, at=T + 40):
    """Response *op_id* as the loop's test judges it against the stored read in *found*."""
    cached = found[NET]
    value = cached["doc"]["last_good"]["value"]
    (h,) = [h for h in LP.holds(NET, RA.as_collected(value), at, cached=cached)["holds"]
            if h["key"] == op_id]
    return h


def flows_of_op(op_id):
    return {r["cookie"] for r in F.intent(NET, CONN)["flows"]
            if (r.get("response") or {}).get("operation") == op_id}


# ── resolves ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("source,seen_as", [("192.0.2.1", "192.0.2.1"),
                                            ("2001:db8::1", "2001:db8::1"),
                                            ("2001:DB8:0:0::1", "2001:db8::1")])
def test_a_lost_drop_answered_again_on_its_switch_is_no_longer_a_row(lab, source, seen_as):
    """The scan's drop is lost in a restart (its row up), the scan fires again and is dropped
    again (C2005): the row resolves, and What was checked names both. The same detection, or
    (the last case) the same source spelled another way under another key, as the lost
    response's record keeps the source as its detection named it."""
    old = drop(source)
    lab.restart()
    (row,) = rows(T + 20)
    assert row["operands"]["operation"] == old["id"], "premise: the row is up"
    new = respond(detection(seen_as), T + 30)
    got = mitigation(T + 60)
    assert got["rows"] == [], got["rows"]
    assert (f"; 1 more missing and answered by a newer response in force ({NET}'s {old['id']} "
            f"by {new['id']})") in got["checked"]


def test_a_lost_flood_over_mac_only_flows_answered_again_on_its_port_is_no_longer_a_row(
        lab, monkeypatch):
    """The walk's flood naming no address (C2002): its drop takes the address on its port from
    the controller's topology, and the record names no source. Answered again for the same
    port, the newer drop covers it by its key: the row resolves. Answered on another port, it
    stays."""
    l2 = lab8("l2_only_s1.json")
    lab.table[1], lab.features, lab.topology = flows_of(l2, 1), features_of(l2, 1), \
        captured_topology()

    def flood(port):
        return dict(_mac_only_flood(port), connection=CONN, title="SDN flood",
                    key=D.detection_key("flood", NET, CONN, SW, ["port", port]))

    assert flood(2)["source"] is None, "premise: it names no address"
    old = respond(flood(2), T)
    assert (F.intent(NET, CONN)["flows"][0]["response"]["detection"]["source"]) is None
    lab.table[1] = flows_of(l2, 1)                      # the restart, to the L2-only table
    lab.meter[1] = {}
    (row,) = rows(T + 20, asked=T + 40)
    other = respond(flood(1), T + 30)
    got = mitigation(T + 40)
    (still,) = got["rows"]
    assert drawn(still) == drawn(row), \
        "a drop for another port's flood leaves it up, its words unchanged"
    assert other["id"] not in got["checked"]
    new = respond(flood(2), T + 50)
    got = mitigation(T + 60)
    assert got["rows"] == [] and f"{old['id']} by {new['id']}" in got["checked"]


# ── stays ─────────────────────────────────────────────────────────────────────────────────────

def test_nothing_newer_leaves_the_row_and_its_words_as_c2018_drew_them(lab):
    old = drop()
    lab.restart()
    (r,) = rows(T + 100)
    cookie = F.cookie_hex(next(iter(flows_of_op(old["id"]))))
    assert r["what"] == (f"Drop traffic from the source (192.0.2.1) on Default is not in force "
                         f"on switch {SW} (s1): 1 flow ({cookie}) missing, 8 min 20 s left")
    assert r["clears"]["ways"] == ["resolves", "time"] and r["clears_at"] == F._iso(T + 600)
    assert "answered by a newer response" not in mitigation(T + 100)["checked"]


@pytest.mark.parametrize("edit,why", [
    ({"source": "192.0.2.9", "key": "k-192.0.2.9"}, "another source"),
    ({"rule": "flood", "key": "k-flood-192.0.2.1"}, "another rule"),
])
def test_a_newer_response_for_another_source_or_rule_leaves_the_row(lab, edit, why):
    drop()
    lab.restart()
    (before,) = rows(T + 20, asked=T + 40)
    new = respond(dict(detection(), **edit), T + 30)
    found = read(T + 40)
    assert hold_of(new["id"], found)["state"] == "active", "premise: the newer one is in force"
    (after,) = A.sdn_mitigation_source(found=found, now=T + 40)["rows"]
    assert drawn(after) == drawn(before), why


class TwoSwitches(Switch):
    """The test's switch and a second, s2 (dpid 2), its counters and description answered from
    the same capture."""

    def _answer(self, method, path, body):
        if method == "GET" and path in ("/stats/port/2", "/stats/desc/2"):
            e = next(e for e in WITH_PEER if e["path"] == path.replace("/2", "/1"))
            return captured(dict(e, body=json.dumps({"2": json.loads(e["body"])["1"]})))
        return super()._answer(method, path, body)


def test_a_newer_response_on_another_switch_leaves_the_row(lab, monkeypatch):
    from modules.sdn import drivers
    from tests.test_sdn_flow_ops import captured_table

    fake = TwoSwitches(lab.base, flows={1: captured_table(), 2: captured_table()},
                       dpids=(1, 2))
    real = drivers.make
    monkeypatch.setattr(drivers, "make", lambda kind, connection, **kw: real(
        kind, connection, **dict(kw, session=fake, sleep=lambda s: None)))
    drop()
    fake.table[1] = [dict(f) for f in captured_table()]             # s1 restarts
    (before,) = rows(T + 20, asked=T + 40)
    new = respond(dict(detection(), dpid=2, dpid_hex="0000000000000002"), T + 30)
    found = read(T + 40)
    assert hold_of(new["id"], found)["state"] == "active", "premise: in force on s2"
    (after,) = A.sdn_mitigation_source(found=found, now=T + 40)["rows"]
    assert drawn(after) == drawn(before)


def test_a_newer_response_not_in_force_leaves_the_row(lab):
    """Its flow gone too (a second restart): it answers nothing; the row for the old one stays,
    and the newer one has its own row."""
    old = drop()
    lab.restart()
    new = respond(detection(), T + 30)
    lab.restart()
    got = mitigation(T + 40)
    assert sorted(r["operands"]["operation"] for r in got["rows"]) == sorted(
        [old["id"], new["id"]])


def test_a_newer_rate_limit_whose_meter_is_read_missing_leaves_the_row(lab):
    """The newer response's flows are on the switch and its meter is not: not in force (the
    loop's test reads the meter from the same stored read)."""
    old = drop()
    lab.restart()
    new, _flows = rate_limit()
    lab.meter[1] = {}
    got = mitigation(T + 40)
    ops = sorted(r["operands"]["operation"] for r in got["rows"])
    assert ops == sorted([old["id"], new["id"]]), got["rows"]


class Down(Switch):
    """The switch's controller, answering nothing once *down* is set."""
    down = False

    def request(self, method, url, **kwargs):
        if self.down:
            raise requests.exceptions.ConnectionError("down")
        return super().request(method, url, **kwargs)


def test_a_newer_response_on_a_controller_not_answering_since_is_not_judged(lab, monkeypatch):
    """The newer response was read in force, then the controller stopped answering: its read
    is carried, so whether it is in force now is not known, and the row stays."""
    from modules.sdn import drivers
    from tests.test_sdn_flow_ops import captured_table

    fake = Down(lab.base, flows={1: captured_table()})
    real = drivers.make
    monkeypatch.setattr(drivers, "make", lambda kind, connection, **kw: real(
        kind, connection, **dict(kw, session=fake, sleep=lambda s: None)))
    old = drop()
    fake.restart()
    respond(detection(), T + 30)
    assert mitigation(T + 40)["rows"] == [], "premise: answered, as read"
    fake.down = True
    found = read(T + 70)
    (c,) = found[NET]["doc"]["last_good"]["value"]["controllers"]
    assert c["state"] == "not_answering", "premise: the read is carried"
    (row,) = A.sdn_mitigation_source(found=found, now=T + 70)["rows"]
    assert row["operands"]["operation"] == old["id"]
    assert "has not answered since" in row["cause"]


# ── re-apply on a covered threat ──────────────────────────────────────────────────────────────

def test_the_re_apply_of_a_covered_threat_is_refused_naming_the_newer_response(lab):
    old = drop("2001:db8::1")
    lab.restart()
    new = respond(detection("2001:db8::1"), T + 30)
    writes = list(lab.writes)
    got = RA.preview(NET, CONN, SW, old["id"], now=T + 60)
    assert not got["ok"] and got["plan"] is None
    assert got["error"].startswith(
        f"response {old['id']}'s threat (Drop traffic from the source (2001:db8::1)) is "
        f"answered by a newer response: response {new['id']} (drop_source, operation "
        f"{new['id']}) holds 2001:db8::1 off on switch {SW} until {F._iso(T + 630)} (its 1 "
        "flow(s) on the switch as this collection read it)")
    assert got["error"].endswith("as read now; nothing to re-apply")
    assert lab.writes == writes, "nothing sent"


def test_a_lost_drop_answered_again_by_a_rate_limit_is_not_put_back_beside_it(lab):
    """The scan answered the second time by a rate limit of the same source (meter 5 and its
    flows to two hosts, another match from the drop's): the drop put back would sit beside it,
    dropping what the newer answer only limits. Refused, naming the rate limit."""
    old = drop()
    lab.restart()
    new, _flows = rate_limit()
    writes = list(lab.writes)
    got = RA.preview(NET, CONN, SW, old["id"], now=T + 60)
    assert not got["ok"], "a drop put back beside the newer rate limit"
    assert (f"is answered by a newer response: response {new['id']} (rate_limit_source, "
            f"operation {new['id']}) holds 192.0.2.1 off on switch {SW}") in got["error"]
    assert lab.writes == writes


@pytest.mark.parametrize("newer", ["drop", "rate_limit"])
def test_a_preview_taken_before_the_newer_response_confirmed_after_it_sends_nothing(lab, newer):
    """A person previewed the re-apply, the scan was answered again, then they confirmed: the
    confirm is refused naming the newer response, and nothing is sent."""
    old = drop()
    lab.restart()
    got = RA.preview(NET, CONN, SW, old["id"], now=T + 20)
    assert got["ok"], got["error"]
    new = respond(detection(), T + 30) if newer == "drop" else rate_limit()[0]
    writes = list(lab.writes)
    out = RA.confirm(NET, got["ask"], got["plan"]["hash"], actor="op@example.com",
                     actor_verified="access", sleep=lambda s: None, now=lambda: T + 40)
    assert out["outcome"] == "refused" and lab.writes == writes, out
    assert f"is answered by a newer response: response {new['id']}" in out["error"]
    assert out["error"].endswith("as read now: nothing was sent")


def test_re_apply_pressed_on_a_stale_flows_page_is_refused_in_place(lab):
    """Flows drew Re-apply… while the drop was lost; the scan was answered again before the
    person pressed it."""
    import app as APP

    c = APP.app.test_client()
    at = float(int(time.time())) - 100                    # the route reads the real clock
    old = drop(at=at)
    lab.restart()
    store_read(NET, clock=lambda: time.time())
    html = c.get(f"/v2/sdn/flows?list=Default&q={SW}").get_data(as_text=True)
    form = re.search(r'<form class="sdn-lost".*?</form>', html, re.S).group(0)
    new = respond(detection(), at + 30)
    r = c.post("/v2/sdn/reapply/preview", data=form_fields(form))
    said = unescape(r.get_data(as_text=True))
    assert r.status_code == 409, said
    assert f"is answered by a newer response: response {new['id']}" in said
    assert "nothing to re-apply" in said and old["id"] in said


def test_c2070_is_said_in_the_row_s_clears():
    ways, words = A.CLEARS[("sdn_mitigation", "lost")]
    assert ways == ("resolves", "time")
    assert words.endswith("or a newer response answers the same threat on that switch (its "
                          "detection fired again and was answered as new)")
