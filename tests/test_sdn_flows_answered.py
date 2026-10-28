"""SDN › Flows draws a lost response a newer response already answers as answered, naming the
newer response, with no Re-apply… (C2077; board SdnFlows, revised 2026-10-28;
`sdn_page.flows_view`, `_lost_row`, templates/v2/_sdn_view.html).

C2070 made the judgement: `reapply.answered_by` over `loop.holds` judged against the SDN
reader's stored read (`reapply.as_collected`), the loop's own test of what holds a threat off
(`loop.covering`). Needs attention's row resolves and a re-apply is refused once a newer
response in force answers the same threat on that switch. Flows still drew the lost response
as Not in force with Re-apply…, a control whose only outcome is a refusal. The page now uses
the same judgement over the same stored read it draws, once per view and only when something
is lost, never a controller call.

**The data.** tests/test_sdn_reapply.py's switch (`tests.sdn_fakes.FakeRyu` seeded with Ryu
4.34's captured flow table), a response applied through the real code
(`closed_loop.respond_to_threat`), a restart the table put back and its meters emptied, the SDN
reader's run stored as the scheduler stores it; the MAC case the Lab 8 walk's flood over
MAC-only flows (C2002), as tests/test_sdn_lost_answered.py builds it. The route reads the real
clock, so each response is applied a little before it.

- **Answered:** a newer drop of the same source (IPv4, IPv6) or the MAC-keyed flood answered
  again on its port: the lost response's line says Answered, names the newer response (its id,
  its action and source, and until when it is in force), says there is nothing to re-apply, and
  carries no Re-apply… form. Its flows are still drawn Mercury's, missing in the table, as
  they are.
- **As before:** nothing newer, a newer response for another source, a flood answered on
  another port, or a controller not answering since (its read carried, so nothing on it is
  judged in force): the Not in force line with Re-apply…, as C2018 drew it.
- **No extra reads:** the view reads the reader's stored value once, judges once per view and
  only when something is lost, and asks no controller anything.
"""
import re
import time
from html import unescape

import pytest
import requests

from modules.sdn import detect as D
from tests.sdn_fakes import lab8
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_lab8 import _mac_only_flood, captured_topology, features_of, flows_of
from tests.test_sdn_lost_answered import respond
from tests.test_sdn_reapply import CONN, NET, SW, Switch, detection, drop
from tests.test_sdn_reapply import lab  # noqa: F401 - the fixture
from tests.test_sdn_v2 import store_read


def page(q=SW):
    import app as APP

    store_read(NET, clock=time.time)
    return APP.app.test_client().get(f"/v2/sdn/flows?list=Default&q={q}").get_data(as_text=True)


def answered_line(html, key):
    got = re.search(r'<p class="small sdn-answered" data-key="' + re.escape(key)
                    + r'">.*?</p>', html, re.S)
    return got.group(0) if got else ""


def lost_forms(html):
    return re.findall(r'<form class="sdn-lost".*?</form>', html, re.S)


def text(fragment):
    """A fragment's words as read: tags as spaces, no space before punctuation."""
    spaced = " ".join(unescape(re.sub(r"<[^>]+>", " ", fragment)).split())
    return re.sub(r" ([,.:;)])", r"\1", spaced)


def hm(epoch):
    return time.strftime("%H:%M", time.gmtime(epoch))


def now_less(seconds):
    """A whole second *seconds* before now: the route reads the real clock."""
    return float(int(time.time())) - seconds


# ── answered ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("source,seen_as,named", [
    ("192.0.2.1", "192.0.2.1", "192.0.2.1"),
    ("2001:db8::1", "2001:db8::1", "2001:db8::1"),
    ("2001:db8::1", "2001:DB8:0:0::1", "2001:db8::1")])
def test_a_lost_drop_answered_again_is_drawn_answered_naming_the_newer_response(
        lab, source, seen_as, named):
    """The last case: the scan seen again with its source spelled another way, under another
    key; the newer response is named by the source in one spelling, as the loop compares it."""
    at = now_less(100)
    old = drop(source, at=at)
    lab.restart()
    before = page()
    assert len(lost_forms(before)) == 1, "premise: Not in force with Re-apply…"
    new = respond(detection(seen_as), at + 30)
    html = page()
    line = answered_line(html, old["id"])
    assert line, "the lost response is drawn answered"
    assert text(line) == (
        f"Answered Drop traffic from the source ({source}): 1 flow ("
        + re.search(r"1 flow \((0x[0-9a-f]+)\)", text(lost_forms(before)[0])).group(1)
        + f") missing, and a newer response answers the same threat on this switch: response "
        f"{new['id']}, Drop traffic from the source ({named}), in force until "
        f"{hm(at + 630)} UTC. Nothing to re-apply.")
    assert f'datetime="{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at + 630))}"' in line
    assert lost_forms(html) == [], "no Re-apply… form for it"
    assert "Re-apply…" not in line and "/v2/sdn/reapply/preview" not in html
    assert 'data-manual="sdn-flows#reapply"' in line, "its (i) opens the re-apply section"


def test_the_newer_response_s_operation_is_named_when_it_differs_from_its_id():
    """A response a person confirmed through the loop has a response id beside its operation
    (`loop.holds`' ``id`` and ``key``): both are drawn; AUTO's has its operation alone."""
    from modules import sdn_page as P

    x = {"key": "sdnop-old", "label": "Drop traffic from the source (192.0.2.1)",
         "missing_words": "1 flow (0x1)", "left": 300, "expires_at": 1_790_000_600,
         "connection": CONN, "dpid_hex": SW}
    hold = {"id": "resp-1a2b3c4d5e", "key": "sdnop-new", "action": "rate_limit_source",
            "sources": ["192.0.2.1"], "until": 1_790_000_900}
    row = P._lost_row(x, hold)
    assert row["answered"] == {"id": "resp-1a2b3c4d5e", "operation": "sdnop-new",
                               "label": "Rate-limit the source (192.0.2.1)",
                               "until": "2026-09-21T14:28:20Z"}
    assert P._lost_row(x)["answered"] is None


def test_the_operation_is_drawn_beside_a_response_id(lab, monkeypatch):
    """Through the template: a response a person confirmed through the loop carries its
    response id beside its operation (planted on the real judgement's answer: the test applies
    responses directly, so their id is their operation)."""
    from modules.sdn import reapply as RA

    at = now_less(100)
    old = drop(at=at)
    lab.restart()
    new = respond(detection(), at + 30)
    real = RA.answered_by

    def with_id(x, judged):
        got = real(x, judged)
        return dict(got, id="resp-1a2b3c4d5e") if got else got

    monkeypatch.setattr(RA, "answered_by", with_id)
    line = text(answered_line(page(), old["id"]))
    assert f"response resp-1a2b3c4d5e (operation {new['id']})," in line


def test_every_field_a_lost_row_carries_is_drawn(lab):
    """tests/test_v2_context_is_drawn.py's comparison (`v2_context.carried` over the template's
    reads), applied to the lost rows Flows draws, answered and not, on this file's own cases.
    That test examines SDN's payload, passed as `g`, since C2082; before, it left `g` out as
    Flask's own (a blind spot reported with C2077), and this test was the one that saw it."""
    from modules import sdn_page as P
    from tests import v2_context as V

    import app as APP

    at = now_less(100)
    drop(at=at)
    drop("2001:db8::1", at=at)
    lab.restart()
    respond(detection(), at + 30)
    store_read(NET, clock=time.time)
    (sw,) = P.flows_view(NET, {}, now=time.time())["switches"]
    assert sorted(bool(x["answered"]) for x in sw["lost"]) == [False, True], \
        "premise: one answered, one not"
    reads = V.template_reads(APP.app.jinja_env, "v2/sdn.html")
    carried, undrawn = V.carried({"lost": sw["lost"]}, reads)
    assert {"answered", "id", "operation", "label", "until", "slot"} <= carried
    assert undrawn == set(), undrawn


def test_a_lost_flood_over_mac_only_flows_answered_on_its_port_is_drawn_answered(lab):
    """The walk's flood naming no address (C2002), answered again for the same port: answered.
    Answered on another port only: as before, Not in force with Re-apply…."""
    l2 = lab8("l2_only_s1.json")
    lab.table[1], lab.features, lab.topology = flows_of(l2, 1), features_of(l2, 1), \
        captured_topology()

    def flood(port):
        return dict(_mac_only_flood(port), connection=CONN, title="SDN flood",
                    key=D.detection_key("flood", NET, CONN, SW, ["port", port]))

    at = now_less(100)
    old = respond(flood(2), at)
    lab.table[1] = flows_of(l2, 1)                      # the restart, to the L2-only table
    lab.meter[1] = {}
    respond(flood(1), at + 30)
    html = page()
    assert answered_line(html, old["id"]) == "", "another port's flood answers nothing"
    (form,) = lost_forms(html)
    assert f'value="{old["id"]}"' in form and "Re-apply…" in form
    new = respond(flood(2), at + 50)
    html = page()
    line = answered_line(html, old["id"])
    assert f"response {new['id']}," in text(line) and "Nothing to re-apply." in text(line)
    assert lost_forms(html) == []


# ── as before ─────────────────────────────────────────────────────────────────────────────────

def test_nothing_newer_draws_not_in_force_with_re_apply_as_c2018_did(lab):
    at = now_less(100)
    old = drop(at=at)
    lab.restart()
    html = page()
    (form,) = lost_forms(html)
    assert f'name="key" value="{old["id"]}"' in form and "Re-apply…" in form
    assert "Not in force" in form and "of its hard timeout left" in unescape(form)
    assert "sdn-answered" not in html
    assert re.search(r'<details class="sdn-sw" data-keep="sw-' + SW + '" open>', html)


def test_a_newer_response_for_another_source_leaves_it_not_in_force(lab):
    at = now_less(100)
    old = drop(at=at)
    lab.restart()
    respond(dict(detection(), source="192.0.2.9", key="k-192.0.2.9"), at + 30)
    html = page()
    (form,) = lost_forms(html)
    assert f'value="{old["id"]}"' in form and "sdn-answered" not in html


class Down(Switch):
    """The switch's controller, answering nothing once *down* is set."""
    down = False

    def request(self, method, url, **kwargs):
        if self.down:
            raise requests.exceptions.ConnectionError("down")
        return super().request(method, url, **kwargs)


def test_a_controller_not_answering_since_leaves_it_not_in_force(lab, monkeypatch):
    """Answered as read; then the controller stops answering and its read is carried, so
    whether the newer response is in force now is not known: Not in force, with Re-apply…."""
    from modules.sdn import drivers
    from tests.test_sdn_flow_ops import captured_table

    fake = Down(lab.base, flows={1: captured_table()})
    real = drivers.make
    monkeypatch.setattr(drivers, "make", lambda kind, connection, **kw: real(
        kind, connection, **dict(kw, session=fake, sleep=lambda s: None)))
    at = now_less(100)
    old = drop(at=at)
    fake.restart()
    respond(detection(), at + 30)
    assert answered_line(page(), old["id"]), "premise: answered, as read"
    fake.down = True
    html = page()
    assert "as last read" in html, "premise: the read is carried"
    assert answered_line(html, old["id"]) == ""
    (form,) = lost_forms(html)
    assert f'value="{old["id"]}"' in form and "Re-apply…" in form


# ── no extra reads ────────────────────────────────────────────────────────────────────────────

def test_the_view_reads_the_stored_value_once_and_asks_no_controller(lab, monkeypatch):
    """Three responses lost on two switches (two on s1, one on s2), one of s1's answered: one
    read of the reader's store and one judgement for the whole view, not one per switch or per
    response; no controller asked; nothing judged when nothing is lost."""
    from modules import reader_job
    from modules import sdn_page as P
    from modules.sdn import drivers
    from modules.sdn import loop as LP
    from tests.test_sdn_flow_ops import captured_table
    from tests.test_sdn_lost_answered import TwoSwitches

    fake = TwoSwitches(lab.base, flows={1: captured_table(), 2: captured_table()},
                       dpids=(1, 2))
    real = drivers.make
    monkeypatch.setattr(drivers, "make", lambda kind, connection, **kw: real(
        kind, connection, **dict(kw, session=fake, sleep=lambda s: None)))
    at = now_less(100)
    first = drop(at=at)
    second = drop("2001:db8::1", at=at)
    third = respond(dict(detection("192.0.2.5"), dpid=2, dpid_hex="0000000000000002"), at)
    fake.table[1] = [dict(f) for f in captured_table()]          # both switches restart
    fake.table[2] = [dict(f) for f in captured_table()]
    respond(detection(), at + 30)
    store_read(NET, clock=time.time)
    calls = {"cached": 0, "holds": 0}
    real_cached, real_holds = reader_job.read_cached_for, LP.holds

    def cached(*a, **kw):
        calls["cached"] += 1
        return real_cached(*a, **kw)

    def holds(*a, **kw):
        calls["holds"] += 1
        assert kw.get("cached") is not None, "the view hands the loop the read it holds"
        return real_holds(*a, **kw)

    monkeypatch.setattr(reader_job, "read_cached_for", cached)
    monkeypatch.setattr(LP, "holds", holds)
    sent = len(fake.sent)
    g = P.flows_view(NET, {}, now=time.time())
    by_key = {x["key"]: x for sw in g["switches"] for x in sw["lost"]}
    assert sorted(by_key) == sorted([first["id"], second["id"], third["id"]])
    assert by_key[first["id"]]["answered"]
    assert not by_key[second["id"]]["answered"] and not by_key[third["id"]]["answered"]
    assert calls == {"cached": 1, "holds": 1}, \
        "three lost responses on two switches: one read and one judgement"
    assert len(fake.sent) == sent, "no controller asked"
    calls.update(cached=0, holds=0)                       # nothing lost: nothing judged
    monkeypatch.setattr("modules.sdn.reapply.lost_on_switch", lambda c, s, now: [])
    P.flows_view(NET, {}, now=time.time())
    assert calls == {"cached": 1, "holds": 0}
