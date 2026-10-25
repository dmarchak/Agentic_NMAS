"""Ask in words' offer when the question names devices: only the metrics those devices carry
(2026-10-25, recorded case 13's v2 answer: "Interface status changes on s1 today" was offered,
and chose, the IOS-XE routers' flap counter, which s1, an IOS switch, has none of). One read of
Prometheus's label values, narrowed to the named devices; unreadable, the offer is the whole
catalogue's, as before. The answers are the lab's own captures
(tests/fixtures/prometheus/ask_device_names.json, every device; ask_device_names_s1.json, s1),
through tests/test_ai_nl_query.py's world.
"""
import json
import os
import re

from modules import history_promq as pq
from modules.ai import nl_query
from tests.test_ai_nl_query import NOW, _ask, world  # noqa: F401 (the fixture)

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "prometheus")
FLAPS = "Cisco_IOS_XE_interfaces_oper:interfaces_interface_statistics_num_flaps"


def _s1():
    with open(os.path.join(FIX, "ask_device_names_s1.json"), encoding="utf-8") as fh:
        return json.load(fh)["answer"]


def _per_device(world, answer=None, fail=""):
    """The stand-in answering a read narrowed to devices with *answer* (s1's capture), or
    failing it with *fail*; every other read as before. Returns the selectors asked."""
    asked, plain = [], world.prom._get

    def _get(path, **params):
        sel = params.get("match[]", "")
        if path == "api/v1/label/__name__/values" and "=~" in sel:
            asked.append(sel)
            if fail:
                return {"ok": False, "error": fail}
            return world.prom._ok(answer or _s1())
        return plain(path, **params)
    world.prom._get = _get
    return asked


def _offered_in_request(world):
    content = world.sent[-1]["body"]["messages"][0]["content"]
    block = re.search(r'<data name="metrics">\n(.*?)\n</data>', content, re.S).group(1)
    return [line.split(" | ")[0] for line in block.splitlines()]


def test_a_question_naming_a_device_is_offered_only_what_it_carries(world):
    world.answer = {"outcome": "ask", "question": "which interfaces?", "why_not": "",
                    "metric": "", "devices": [], "role": "", "interfaces": [], "filters": [],
                    "operations": [], "top": "none", "range": "24h", "from_utc": "",
                    "to_utc": ""}
    asked = _per_device(world)
    got = nl_query.metrics("Lab", "Interface status changes on s1 today",
                           actor="operator@example.com", send=world.send, client=world.prom,
                           now=NOW, today="2026-10-25")
    assert asked == ['device=~"s1"'.join("{}")]
    offered = _offered_in_request(world)
    assert "ifOperStatus" in offered and FLAPS not in offered, offered
    assert set(offered) <= set(_s1()["data"])
    assert got["offered"] == offered


def test_the_whole_catalogue_offers_the_flap_counter_without_the_narrowing(world):
    """The control: unnarrowed (no device named), the counter s1 lacks is offered, so the test
    above is the narrowing's, not the catalogue's."""
    world.answer = {"outcome": "ask", "question": "which device?", "why_not": "", "metric": "",
                    "devices": [], "role": "", "interfaces": [], "filters": [],
                    "operations": [], "top": "none", "range": "24h", "from_utc": "",
                    "to_utc": ""}
    _per_device(world)
    nl_query.metrics("Lab", "Interface status changes today", actor="operator@example.com",
                     send=world.send, client=world.prom, now=NOW, today="2026-10-25")
    assert FLAPS in _offered_in_request(world)


def test_an_unreadable_narrowing_falls_back_to_the_whole_catalogue(world):
    world.answer = {"outcome": "ask", "question": "which?", "why_not": "", "metric": "",
                    "devices": [], "role": "", "interfaces": [], "filters": [],
                    "operations": [], "top": "none", "range": "24h", "from_utc": "",
                    "to_utc": ""}
    _per_device(world, fail="connection refused")
    nl_query.metrics("Lab", "Interface status changes on s1 today",
                     actor="operator@example.com", send=world.send, client=world.prom,
                     now=NOW, today="2026-10-25")
    assert FLAPS in _offered_in_request(world), "unread, the offer is the catalogue's"


def test_no_metric_the_device_carries_is_said_naming_the_device(world):
    _per_device(world, answer={"status": "success", "data": ["sysUpTime"]})
    got = nl_query.metrics("Lab", "Interface errors on s1", actor="operator@example.com",
                           send=world.send, client=world.prom, now=NOW, today="2026-10-25")
    assert got["error"] == "no_match" and world.sent == []
    assert got["detail"].startswith("no metric of the 1 s1 carries shares a word")


def test_a_question_no_metric_matches_is_mercury_s_own_answer_at_no_cost(world):
    """Case 17 (C1700): no model asked, nothing spent, nothing recorded; the answer says
    what it could not match and among how many, and the judge reads it as `guide`."""
    from modules.ai import calls, cases
    got = nl_query.metrics("Lab", "Show me the network", actor="operator@example.com",
                           send=world.send, client=world.prom, now=NOW, today="2026-10-25")
    assert world.sent == [] and calls.read()["rows"] == []
    assert got["error"] == "no_match" and got["by"] == "mercury"
    assert got["cost_usd"] == 0.0 and got["call_id"] == ""
    g = got["guide"]
    assert g["unmatched"] == list(nl_query.terms("Show me the network"))
    assert g["devices"] == [] and g["among"] == "Prometheus holds" and g["searched"] > 100
    assert cases.misses({"outcome": ["guide"]}, got, NOW) == []
    bare = {"ok": False, "error": "no_match"}
    assert cases.misses({"outcome": ["guide"]}, bare, NOW) == [
        "outcome not the model's: no_match, expected one of ['guide']"], \
        "a no-match without Mercury's answer is no guide"


def test_each_device_is_a_literal_in_the_label_s_regex(world):
    asked = _per_device(world)
    rng = pq.window(dict(pq.DEFAULTS), NOW)
    nl_query.device_metrics(world.prom, rng, ["s1", "r1.lab"])
    assert asked == ['{device=~"s1|r1\\\\.lab"}']
