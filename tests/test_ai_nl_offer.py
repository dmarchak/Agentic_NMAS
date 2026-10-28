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

import pytest

from modules.ai import triggers
from tests.ai_person import pressed_by
from modules import history_promq as pq
from modules.ai import nl_query
from tests.test_ai_nl_query import NOW, _ask, _words, site, web, world  # noqa: F401

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "prometheus")
FLAPS = "Cisco_IOS_XE_interfaces_oper:interfaces_interface_statistics_num_flaps"


def _s1():
    with open(os.path.join(FIX, "ask_device_names_s1.json"), encoding="utf-8") as fh:
        return json.load(fh)["answer"]


#: The tie-break's read: what the inventory's devices carry, by name (C1835), never the device
#: label's presence.
FLEET = '{device=~"r1|s1"}'


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
    with pressed_by("operator@example.com"):
        got = nl_query.metrics("Lab", "Interface status changes on s1 today",
                               actor="operator@example.com",
                               trigger=triggers.person("operator@example.com"),
                               send=world.send, client=world.prom,
                               now=NOW, today="2026-10-25")
    assert asked == ['device=~"s1"'.join("{}"), FLEET]
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
    with pressed_by("operator@example.com"):
        nl_query.metrics("Lab", "Interface status changes today", actor="operator@example.com",
                         trigger=triggers.person("operator@example.com"),
                         send=world.send, client=world.prom, now=NOW, today="2026-10-25")
    assert FLAPS in _offered_in_request(world)


def test_an_unreadable_narrowing_falls_back_to_the_whole_catalogue(world):
    world.answer = {"outcome": "ask", "question": "which?", "why_not": "", "metric": "",
                    "devices": [], "role": "", "interfaces": [], "filters": [],
                    "operations": [], "top": "none", "range": "24h", "from_utc": "",
                    "to_utc": ""}
    _per_device(world, fail="connection refused")
    with pressed_by("operator@example.com"):
        nl_query.metrics("Lab", "Interface status changes on s1 today",
                         actor="operator@example.com",
                         trigger=triggers.person("operator@example.com"),
                         send=world.send, client=world.prom,
                         now=NOW, today="2026-10-25")
    assert FLAPS in _offered_in_request(world), "unread, the offer is the catalogue's"


def test_no_metric_the_device_carries_is_said_naming_the_device(world):
    _per_device(world, answer={"status": "success", "data": ["sysUpTime"]})
    with pressed_by("operator@example.com"):
        got = nl_query.metrics("Lab", "Interface errors on s1", actor="operator@example.com",
                               trigger=triggers.person("operator@example.com"),
                               send=world.send, client=world.prom, now=NOW, today="2026-10-25")
    assert got["error"] == "no_match" and world.sent == []
    assert got["detail"].startswith("no metric of the 1 s1 carries shares a word")


def test_a_question_no_metric_matches_is_mercury_s_own_answer_at_no_cost(world):
    """Case 17 (C1700): no model asked, nothing spent, nothing recorded; the answer says
    what it could not match and among how many, and the judge reads it as `guide`."""
    from modules.ai import calls, cases
    with pressed_by("operator@example.com"):
        got = nl_query.metrics("Lab", "Show me the network", actor="operator@example.com",
                               trigger=triggers.person("operator@example.com"),
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


def test_mercury_s_answer_is_drawn_with_what_to_name_and_the_start_from_chips(site):
    """Through the real metrics route (C1700): the answer says it is Mercury's, at no cost,
    what to name and which devices, and draws the builder's own Start-from chips as links;
    nothing was sent and the words stay in the box."""
    from modules import history_promq as pq
    r, html = _words(site, "Show me the network")
    assert r.status_code == 200 and site.world.sent == []
    assert "Mercury answered this itself</strong>, with no AI call ($0)" in html
    assert "none of your words names something to measure" in html
    assert "Name what to measure, in a metric's words" in html and "which devices" in html
    answer = html.split('class="notice lq-guide"', 1)[1].split("</div></div>", 1)[0]
    held = [t for k, t, _a, p in pq.PRESETS]
    assert held and all(f">{t}<" in answer for t in held), "the chips are not in the answer"
    assert "hx-get=" in answer, "a chip is not a link"
    assert 'value="Show me the network"' in html, "the person's words were not kept"
    assert "Not filled:" not in html, "drawn as a refusal"


def test_mercury_s_answer_leaves_the_builder_marked_and_ask_off_until_kept(site):
    """The operator's walk of 2026-10-26: after Mercury's own $0 answer the builder still held
    the previous question's query with Ask on, so Ask answered the wrong question. It is now
    marked left from the previous question, Ask is off, and one click keeps the choices (the
    region drawn again without the words, Ask on)."""
    r, html = _words(site, "Show me the network", m="ifHCInOctets")
    assert "Mercury answered this itself" in html
    assert "Left from your previous question" in html and "lq-leftmark" in html
    assert " disabled" in re.search(r'<button id="lq-ask"[^>]*>', html).group(0)
    keep = re.search(r'<a class="btn btn-small" href="[^"]+" hx-get="([^"]+)"[^>]*>Keep these '
                     r'choices</a>', html).group(1)
    assert "m=ifHCInOctets" in keep and "words" not in keep
    from html import unescape
    again = unescape(site.get(keep, headers={"HX-Request": "true"}).get_data(as_text=True))
    assert "Left from your previous question" not in again and "lq-leftmark" not in again
    assert " disabled" not in re.search(r'<button id="lq-ask"[^>]*>', again).group(0)


def test_mercury_s_answer_names_the_words_it_could_not_match(site):
    r, html = _words(site, "flibbertigibbet wobbles on s1")
    assert site.world.sent == []
    assert "matches “flibbertigibbet”, “wobbles”" in html
    assert "you named s1" in html


def test_a_question_naming_a_role_is_offered_only_what_its_devices_carry(world):
    """v3's case 11 (2026-10-25): "all switches" was offered, and twice chose, the monitoring
    host's own memory. A named role narrows by the role label: one short selector, however
    many devices hold the role."""
    world.answer = {"outcome": "ask", "question": "which?", "why_not": "", "metric": "",
                    "devices": [], "role": "", "interfaces": [], "filters": [],
                    "operations": [], "top": "none", "range": "24h", "from_utc": "",
                    "to_utc": ""}
    asked = _per_device(world)
    with pressed_by("operator@example.com"):
        nl_query.metrics("Lab", "Interface status on all access devices",
                         actor="operator@example.com",
                         trigger=triggers.person("operator@example.com"),
                         send=world.send, client=world.prom,
                         now=NOW, today="2026-10-25")
    assert asked == ['{role=~"access"}', FLEET]
    offered = _offered_in_request(world)
    assert offered and set(offered) <= set(_s1()["data"]) and FLAPS not in offered


def test_a_device_and_a_role_named_are_offered_what_either_carries(world):
    world.answer = {"outcome": "ask", "question": "which?", "why_not": "", "metric": "",
                    "devices": [], "role": "", "interfaces": [], "filters": [],
                    "operations": [], "top": "none", "range": "24h", "from_utc": "",
                    "to_utc": ""}
    asked = _per_device(world)
    with pressed_by("operator@example.com"):
        nl_query.metrics("Lab", "Interface status on r1 and the access devices",
                         actor="operator@example.com",
                         trigger=triggers.person("operator@example.com"),
                         send=world.send, client=world.prom,
                         now=NOW, today="2026-10-25")
    assert asked == ['{device=~"r1"}', '{role=~"access"}', FLEET]


def test_a_role_is_named_by_its_word_or_its_plural():
    roles = ["access", "core", "router", "switch"]
    assert nl_query.named_roles("Memory used on all switches", roles) == ["switch"]
    assert nl_query.named_roles("CPU on the routers", roles) == ["router"]
    assert nl_query.named_roles("errors in the core", roles) == ["core"]
    assert nl_query.named_roles("show me the network", roles) == []
    assert nl_query.named_roles("the accessories", roles) == [], "a whole word, not a part"


def test_an_answer_counting_a_state_s_changes_fills_the_builder_with_changes(world):
    """Case 13 (the operator's ruling, 2026-10-25): the answer's `changes` (schema v2) is read
    back by the builder into its changes query. This stand-in's capture holds ifOperStatus
    with no device label, so the builder leaves the device out and says so;
    tests/test_history_ask_metrics.py's TestChanges pins the device's form,
    `changes(ifOperStatus{device="s1"}[1d])`."""
    from tests.test_ai_nl_query import _choices
    world.answer = _choices(metric="ifOperStatus", devices=["s1"], top="none",
                            operations=[{"kind": "changes", "arg": "1d"}], range="24h")
    with pressed_by("operator@example.com"):
        got = nl_query.metrics("Lab", "Interface status changes on s1 today",
                               actor="operator@example.com",
                               trigger=triggers.person("operator@example.com"),
                               send=world.send, client=world.prom,
                               now=NOW, today="2026-10-25")
    assert got["ok"] is True, got.get("detail")
    assert got["values"]["op"] == ["changes:1d"]
    view = json.dumps(got["view"], default=str)
    assert "changes(ifOperStatus" in view and "[1d])" in view, "no changes query formed"
    assert any("device chosen is left out" in e for e in got["errors"]), got["errors"]


def test_what_the_devices_carry_is_read_by_the_inventory_s_names_never_the_label(world):
    """C1835: node_exporter writes its own `device` label (enp6s18, sda), so reading which
    metrics carry the label at all counted the monitoring host's as the devices'; the
    tie-break reads what the inventory's devices carry, by name."""
    world.answer = {"outcome": "ask", "question": "which devices?", "why_not": "",
                    "metric": "", "devices": [], "role": "", "interfaces": [], "filters": [],
                    "operations": [], "top": "none", "range": "7d", "from_utc": "",
                    "to_utc": ""}
    every, plain = [], world.prom._get

    def _get(path, **params):
        if path == "api/v1/label/__name__/values" and params.get("match[]"):
            every.append(params["match[]"])
        return plain(path, **params)
    world.prom._get = _get
    asked = _per_device(world)
    with pressed_by("operator@example.com"):
        nl_query.metrics("Lab", "Which devices rebooted this week?",
                         actor="operator@example.com",
                         trigger=triggers.person("operator@example.com"),
                         send=world.send, client=world.prom, now=NOW, today="2026-10-25")
    assert asked == [FLEET]
    assert not [s for s in every if '!=""' in s], every


def test_each_device_is_a_literal_in_the_label_s_regex(world):
    asked = _per_device(world)
    rng = pq.window(dict(pq.DEFAULTS), NOW)
    nl_query.device_metrics(world.prom, rng, ["s1", "r1.lab"])
    assert asked == ['{device=~"s1|r1\\\\.lab"}']
