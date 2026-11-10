"""A link down on an SDN fabric reaches Needs attention (`modules/attention.py`
`sdn_links_source`; C2935): a failed redundant link is seen by someone who is not watching
SDN › Responses.

The cards are written by the link-failure module's own writers (`link_failure.step`, which
opens a card in the network's mode and closes it as restored; `record_verify`, which keeps a
verify's answer), the detection the rule's own over the lab's REAL controller answers
(tests/test_sdn_link_failure.py's capture, the OVS-to-OVS link with port 2 of DPID 3 down), and
the verify the real trace over the Lab 8 controller's captured tables (that file's cases).

- A link down whose reroute is not verified is one WARNING row naming the network, both ends
  (each switch by its DPID and its port, as the card's title does) and since when; its action
  opens that card on the network's SDN › Responses, where Verify the reroute is.
- A verify that found the reroute not done makes it DANGER, its words (the pair by address,
  IPv4 and IPv6 alike) on the row.
- A verified reroute is not a row: the link is down and the fabric works around it.
- The link listed and up again (the loop's pass closes the card as restored) is no row, and a
  card dismissed with a reason is none.
- An unreadable store is a row of its own (level unknown), never silence, and another
  network's rows are still drawn beside it.
- Another network's link is its own network's row, never drawn as this one's.
- The page draws it, and the source is read by the page and moved by `sdn`.
"""
from html import unescape

import pytest

from modules import attention as A
from modules.sdn import link_failure as LF
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_link_failure import (LINK, OVS3, OVS4, _collect, _detection, _down,
                                         _link_gone, _rerouted, _store)
from tests.test_sdn_trace import NOW

NET = "Default"
T0 = 1_790_000_010.0


def _line(step, words, **kw):
    return None


def _real_down(monkeypatch):
    """The rule's own detection: the capture's OVS-to-OVS link, port 2 of DPID 3 down."""
    first = LF.rule(_collect(monkeypatch), {})
    got = LF.rule(_collect(monkeypatch, _down, at=T0), first["held"])
    (d,) = got["detections"]
    return d


def _opened(d, network=NET):
    """A card opened by the loop's own step (HITL, the default), and its stored row."""
    LF.step(network, [d], [], now=T0, line=_line)
    (row,) = [r for r in LF.open_rows(network)["rows"]
              if (r.get("detection") or {}).get("key") == d["key"]]
    return row


def _links_rows():
    return A.sdn_links_source()["rows"]


def test_a_link_down_not_verified_is_one_row_naming_both_ends_and_its_card(
        networks, monkeypatch):  # noqa: F811
    d = _real_down(monkeypatch)
    card = _opened(d)
    assert card["mode"] == "hitl" and card["verify"] is None
    (r,) = _links_rows()
    assert (r["source"], r["kind"], r["level"]) == ("sdn_links", "down", "warning")
    since = d["link"]["since"]
    assert r["what"] == (f"SDN link {OVS3} port 2 (eno3) to {OVS4} port 2 (eno3) on {NET} is "
                         f"down since {since}, its reroute not verified yet")
    assert r["since"] == since
    assert r["operands"]["ends"] == [f"{OVS3} port 2 (eno3)", f"{OVS4} port 2 (eno3)"]
    assert r["operands"]["link"] == LINK and r["operands"]["card"] == card["id"]
    assert r["action"]["href"] == f"/v2/sdn/responses?list={NET}#sdn-l-{card['id']}"
    assert "Verify the reroute" in r["action"]["label"]
    assert d["words"] in r["cause"] and "HITL" in r["cause"]
    assert r["clears"] == {"ways": ["resolves"], "when": A.CLEARS[("sdn_links", "down")][1]}


@pytest.mark.parametrize("ipv6_only,pair", [(False, "192.0.2.1 to 192.0.2.3"),
                                            (True, "2001:db8:8::1 to 2001:db8:8::3")])
def test_a_verify_that_found_it_not_rerouted_is_danger_naming_the_pair(
        networks, ipv6_only, pair):  # noqa: F811
    card = _opened(dict(_detection(), network=NET))
    got = LF.verify("Lab", card["detection"], now=NOW,
                    cached=_store(lambda t: _link_gone(t, ipv6_only)))
    assert got["outcome"] == "not_rerouted", got["words"]
    LF.record_verify(NET, card["id"], got, actor="op@example.com", now=T0 + 5)
    assert LF.open_rows(NET)["rows"][0]["verify"]["outcome"] == "not_rerouted"
    (r,) = _links_rows()
    assert r["level"] == "danger" and r["what"].endswith("its reroute verified as NOT done")
    assert pair in r["cause"] and "op@example.com" in r["cause"]


def test_a_verified_reroute_is_not_a_row(networks):  # noqa: F811
    card = _opened(dict(_detection(), network=NET))
    got = LF.verify("Lab", card["detection"], now=NOW,
                    cached=_store(_rerouted, moved=True))
    assert got["outcome"] == "rerouted", got["words"]
    LF.record_verify(NET, card["id"], got, actor="op@example.com", now=T0 + 5)
    res = A.sdn_links_source()
    assert LF.open_rows(NET)["rows"][0]["verify"]["outcome"] == "rerouted"
    assert res["rows"] == []
    assert "1 open, 0 down with the reroute not verified, 1 down and verified rerouted" \
        in res["checked"]


def test_the_link_up_again_or_the_card_dismissed_is_no_row(networks, monkeypatch):  # noqa: F811
    d = _real_down(monkeypatch)
    _opened(d)
    assert len(_links_rows()) == 1
    LF.step(NET, [], [d["key"]], now=T0 + 30, line=_line)       # listed and up again
    assert LF.open_rows(NET)["rows"] == [] and _links_rows() == []
    other = _opened(dict(_detection(), network=NET))
    assert len(_links_rows()) == 1
    LF.close(NET, other["id"], "dismissed", actor="op@example.com", why="the cable is moved")
    assert LF.open_rows(NET)["rows"] == [] and _links_rows() == []


def test_an_unreadable_store_is_a_row_and_hides_no_other_network(networks):  # noqa: F811
    card = _opened(dict(_detection(), network=NET))
    _opened(dict(_detection(), network="Branch"), network="Branch")
    with open(LF._path("Branch"), "a", encoding="utf-8") as fh:
        fh.write("not a json line\n")
    assert LF.open_rows("Branch")["state"] == "unreadable"
    res = A.sdn_links_source()
    by = {r["operands"]["network"]: r for r in res["rows"]}
    assert set(by) == {NET, "Branch"}
    bad = by["Branch"]
    assert (bad["kind"], bad["level"]) == ("unreadable", "unknown")
    assert bad["what"] == "Branch's SDN link-failure cards cannot be read"
    assert LF.STORE_FILE in bad["cause"] and "not known" in bad["cause"]
    assert by[NET]["kind"] == "down" and by[NET]["operands"]["card"] == card["id"]
    assert "unreadable for Branch" in res["checked"]


def test_another_network_s_link_is_its_own_network_s_row(networks):  # noqa: F811
    mine = _opened(dict(_detection(), network=NET))
    theirs = _opened(dict(_detection(), network="Branch"), network="Branch")
    rows = {r["operands"]["network"]: r for r in _links_rows()}
    assert set(rows) == {NET, "Branch"}
    for net, card in ((NET, mine), ("Branch", theirs)):
        r = rows[net]
        assert r["operands"]["card"] == card["id"] and f" on {net} is down" in r["what"]
        assert r["action"]["href"] == f"/v2/sdn/responses?list={net}#sdn-l-{card['id']}"
    assert mine["id"] != theirs["id"]
    assert [r["id"] for r in LF.open_rows("Lab-3")["rows"]] == []


def test_the_page_draws_the_row_with_its_card_link(networks, monkeypatch):  # noqa: F811
    import app as APP

    card = _opened(dict(_detection(), network=NET))
    monkeypatch.setattr(A, "SOURCES", [A.sdn_links_source])
    page = unescape(APP.app.test_client().get(f"/v2/attention?list={NET}")
                    .get_data(as_text=True))
    assert "SDN link 0000000000000001 port 3 (s1-eth3) to 0000000000000002 port 3 (s2-eth3) " \
           f"on {NET} is down" in page
    assert f"/v2/sdn/responses?list={NET}#sdn-l-{card['id']}" in page
    (kept,) = LF.open_rows(NET)["rows"]
    assert kept["id"] == card["id"] and kept["verify"] is None


def test_the_source_is_read_by_the_page_and_moved_by_sdn():
    assert A.sdn_links_source in A.SOURCES
    assert A.SOURCE_KEYS["sdn_links_source"] == ("sdn",)
