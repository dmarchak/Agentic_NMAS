"""SDN › Policies, the intent controller's screen (Lab 9 Objective B2; board lab9-sdn artboard E;
routes/sdn_policies_v2.py), through the real routes on tests/test_sdn_policy_intent.py's Lab 9
world (its NetBox export, the captured topology, FakeRyu behind the real Ryu driver, a fake
`send` behind the real gateway), the controller connection saved as a person saves it.

- **The tab**: Describe a policy (the words box, Draft the policy with its AI mark, the model
  and its cap, How does this work?), the tab in SDN's nav, committed policies (none, then the
  one confirmed); its AI control in each state (`ai_controls_check.check_screen`);
- **a draft**: checked against NetBox and the network (the five rows, Preview the flows…);
  Mercury's question (one button per candidate and Neither, no call) and its answer continuing
  the draft; a refusal before any flow (nothing sent);
- **the impossible offers**: Drop instead… checked again with no AI call;
- **the preview and Send**: the flow-operation card (the requests, the hash), and Send applying
  the flows as the verified person and recording the policy, which the tab then lists.
"""
import json
import re
from html import unescape

import pytest

from modules.sdn import connections as C
from modules.sdn import flow_intent as F
from tests import ai_controls_check
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_policy_intent import ARISTA2, BASE, CONN, NET, OVS1, answer, lab, rule  # noqa: F401


@pytest.fixture
def ui(lab, monkeypatch):  # noqa: F811 - the fixture
    from modules.sdn import drivers

    real = drivers.make

    def make(kind, connection, **kw):
        kw.setdefault("session", lab.fake)
        kw.setdefault("sleep", lambda s: None)
        return real(kind, connection, **kw)

    monkeypatch.setattr(drivers, "make", make)
    monkeypatch.setattr("modules.sdn.flow_ops.COUNTER_INTERVAL", 0)
    assert C.save_connection(NET, {"name": CONN, "kind": "ryu", "url": BASE},
                             actor="op@example.com")["ok"]
    import app as A
    lab.client = A.app.test_client()
    return lab


def fields(html: str) -> dict:
    return {m.group(1): unescape(m.group(2)) for m in
            re.finditer(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"', html)}


def _text(r) -> str:
    """The answer as served (escaped), so `fields` reads each hidden value whole."""
    return r.get_data(as_text=True)


def test_the_tab_draws_the_words_box_and_lists_no_policy_yet(ui):
    r = ui.client.get(f"/v2/sdn/policies?list={NET}")
    html = _text(r)
    assert r.status_code == 200
    assert (f'<a class="tab on" href="/v2/sdn/policies?list={NET}" aria-current="page">'
            'Policies</a>') in html
    assert "Describe a policy" in html and 'data-op="sdn-policy"' in html
    assert "Claude Haiku 5.5 (the economy tier) · at most $" in html
    assert f"No policy is committed on {NET}" in html
    assert F.intent(NET)["flows"] == [] and ui.sent == []


def test_the_ai_control_in_each_state(ui, monkeypatch):
    def get_html():
        return ui.client.get(f"/v2/sdn/policies?list={NET}").get_data(as_text=True)

    def parity(html):
        # The path beside it: SDN › Flows, a flow added by hand, stays linked.
        assert f'href="/v2/sdn/flows?list={NET}"' in html
    ai_controls_check.check_screen(monkeypatch, get_html, "sdn_policy", parity)
    assert ui.sent == []


def test_the_tab_calls_no_model(ui, monkeypatch):
    """Loading, redrawing and refreshing SDN › Policies calls the gateway zero times
    (tests/test_ai_entry_points.py, `SDN_POLICY_PAGES`), with a committed policy drawn."""
    from tests.test_ai_entry_points import SDN_POLICY_PAGES, _count_ai, _load_each

    ui.answer = answer(rule("block", "h1", "web-2", "udp", 5001, duration=600))
    html = _text(_draft(ui, "Block h1 from web-2 on udp 5001 for 10 minutes"))
    card = _text(ui.client.post("/v2/sdn/policies/preview", data=fields(html)))
    assert "Done, verified" in _text(ui.client.post("/v2/sdn/policies/confirm",
                                                    data=fields(card)))
    seen = _count_ai(monkeypatch)
    assert _load_each(ui.client, SDN_POLICY_PAGES) == set(SDN_POLICY_PAGES)
    assert seen == {"asked": [], "sends": []}
    from modules.sdn import policy_intent
    assert len(policy_intent.committed(NET)["policies"]) == 1


def _draft(ui, words, **extra):
    return ui.client.post("/v2/sdn/policies/draft", data=dict({"list": NET, "words": words},
                                                              **extra))


def test_a_draft_is_checked_and_previewed_and_send_records_the_policy(ui):
    ui.answer = answer(rule("block", "h2", "tag:web", "tcp", 443, duration=3600))
    r = _draft(ui, "Block h2 from reaching the web servers on TCP 443 for an hour")
    html = _text(r)
    assert r.status_code == 200, html[:600]
    assert "Checked against NetBox and the network" in html
    for row in ("Hosts named", "Where it applies", "Conflicts with installed flows",
                "Committed policies", "Protected flows"):
        assert f"<td>{row}</td>" in html, row
    assert "arista-sw2 (an Arista EOS switch" in html and "Preview the flows…" in html
    assert len(ui.sent) == 1 and ui.fake.writes == []
    pv = ui.client.post("/v2/sdn/policies/preview", data=fields(html))
    card = _text(pv)
    assert pv.status_code == 200, card[:600]
    assert card.count("POST /stats/flowentry/add") == 2 and "Send 2 requests to" in card
    f = fields(card)
    assert set(f) >= {"list", "ask", "hash", "policy"} and len(f["hash"]) == 64
    assert ui.fake.writes == [], "a preview sends nothing"
    done = ui.client.post("/v2/sdn/policies/confirm", data=f)
    out = _text(done)
    assert done.status_code == 200 and "Done, verified" in out, out[:600]
    adds = [json.loads(b) for p, b in ui.fake.writes if p == "/stats/flowentry/add"]
    assert {a["dpid"] for a in adds} == {ARISTA2} and len(adds) == 2
    recs = F.intent(NET)["flows"]
    assert {r_["response"]["kind"] for r_ in recs} == {"policy"}
    assert {r_["actor"] for r_ in recs} == {"test-person@example.invalid"}
    tab = _text(ui.client.get(f"/v2/sdn/policies?list={NET}"))
    assert json.loads(f["policy"])["id"] in tab and "block h2 to the hosts tagged web" in tab


def test_mercury_s_question_is_buttons_with_no_call_and_a_pick_continues(ui):
    r = _draft(ui, "block h1 from the db on tcp 5432")
    html = _text(r)
    assert r.status_code == 200 and "Which db?" in html and "asked before any AI call" in html
    assert 'name="pick" value="db-1"' in html and 'name="pick" value="db-2"' in html
    assert "Draft with db-1" in html and "db-2 = 198.51.100.32 (NetBox)" in html
    assert ">Neither<" in html and ui.sent == []
    assert "no AI call was made" in html
    ui.answer = answer(rule("block", "h1", "db-1", "tcp", 5432))
    again = _draft(ui, "block h1 from the db on tcp 5432", word="db", pick="db-1")
    assert again.status_code == 200 and "Checked against NetBox" in _text(again)
    assert len(ui.sent) == 1
    neither = _draft(ui, "block h1 from the db on tcp 5432", word="db", pick="")
    assert neither.status_code == 409 and "You chose neither" in _text(neither)
    assert len(ui.sent) == 1 and ui.fake.writes == []


def test_a_refusal_is_drawn_in_place_and_nothing_is_sent(ui):
    r = _draft(ui, "block h9 from web-1 on tcp 80")
    html = _text(r)
    assert r.status_code == 409 and "Unknown host" in html
    assert "Compared: the name against 7 NetBox hosts" in html and "Nothing was sent" in html
    assert ui.sent == [] and ui.fake.writes == []


def test_an_impossible_rate_limit_offers_drop_instead_checked_with_no_call(ui):
    ui.answer = answer(rule("rate_limit", "h2", "web-1", rate=1000))
    r = _draft(ui, "rate-limit h2 to web-1 to 1 Mbit/s")
    html = _text(r)
    assert r.status_code == 409 and "Impossible" in html and "it reports no meters" in html
    assert "Drop instead…" in html and "Rate-limit at ovs2 instead…" in html
    f = fields(html)
    asked = len(ui.sent)
    again = ui.client.post("/v2/sdn/policies/check", data=dict(f, instead_kind="block"))
    out = _text(again)
    assert again.status_code == 200 and "made a drop instead" in out
    assert "Preview the flows…" in out and len(ui.sent) == asked
    assert ui.fake.writes == []


def test_a_confirm_with_no_policy_is_refused_naming_it(ui):
    r = ui.client.post("/v2/sdn/policies/confirm", data={"list": NET, "ask": "{}",
                                                          "hash": "0" * 64})
    assert r.status_code == 400 and "the form carried no policy" in _text(r)
    assert ui.fake.writes == [] and F.intent(NET)["flows"] == []


def test_the_allow_on_ovs_lands_ipv4_and_ipv6_through_the_routes(ui):
    ui.answer = answer(rule("allow", "h1", "web-1", "tcp", 80))
    html = _text(_draft(ui, "Allow h1 to reach web-1 on tcp 80"))
    card = _text(ui.client.post("/v2/sdn/policies/preview", data=fields(html)))
    done = ui.client.post("/v2/sdn/policies/confirm", data=fields(card))
    assert done.status_code == 200 and "Done, verified" in _text(done)
    adds = [json.loads(b) for p, b in ui.fake.writes if p == "/stats/flowentry/add"]
    assert {a["dpid"] for a in adds} == {OVS1}
    assert sorted(a["match"].get("ipv4_dst") or a["match"].get("ipv6_dst") for a in adds) == [
        "198.51.100.21", "2001:db8:c8::21"]
