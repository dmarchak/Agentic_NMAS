"""Explain of an SDN detection runs on its own task, on Haiku (the operator's replan of 2026-11-09,
item 4: "the SDN network's AI uses Haiku"; `modules/ai/explain.py` `feature_for`,
`modules/ai/pins/sdn_explain.json`).

On tests/test_ai_explain.py's world (the real builder, gateway and route; the provider faked at
its one seam), the same pack with an SDN section added and sealed again:
- the call is recorded as `sdn_explain` and sent to the SDN pin's model, Haiku, under its own
  bounds; a pack with no SDN section stays `explain`, on its own pin;
- the pack's card draws the SDN task's mark (its words, model and cap), and the control is
  checked through its real route as every drawn AI control is.
"""

import copy

from modules import evidence_pack as EP
from modules.ai import calls, explain, profiles, triggers
from tests.ai_person import pressed_by
from tests.test_ai_explain import _answer, world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)

HAIKU = "claude-haiku-5-5"


def sdn_pack(pack: dict) -> dict:
    """*pack* with an SDN detection's section added, sealed again under a new id."""
    p = copy.deepcopy(pack)
    p["sections"].append({"name": EP.SDN_SECTION, "ref": "sdn", "state": "ok",
                          "source": "the SDN loop", "read_at": p.get("built_at", ""),
                          "pieces": []})
    p["id"] = "ep-" + "5d" * 10
    p["hash"] = EP.digest(p)
    assert EP.intact(p) and EP.record(p)["ok"]
    return p


def _ask(world, pack):  # noqa: F811
    world.answer = _answer(world.pack)
    with pressed_by("operator@example.com"):
        return explain.explain(pack["id"], actor="operator@example.com",
                               trigger=triggers.person("operator@example.com"),
                               send=world.send, today="2026-10-25")


def test_the_pin_is_haiku_and_keeps_explain_s_bounds():
    sdn, own = profiles.task("sdn_explain"), profiles.task("explain")
    assert sdn["model"] == HAIKU
    assert sdn["max_prompt_tokens"] == own["max_prompt_tokens"]
    assert sdn["max_prompt_tokens"] < profiles.MODELS[HAIKU]["long_prompt_tokens"]


def test_a_pack_is_explained_on_the_sdn_task_only_when_it_carries_an_sdn_section(world):  # noqa: F811
    assert explain.feature_for(world.pack) == "explain"
    assert explain.feature_for(sdn_pack(world.pack)) == "sdn_explain"
    assert explain.feature_for(None) == "explain"


def test_an_sdn_pack_s_call_goes_to_haiku_and_is_recorded_as_its_task(world):  # noqa: F811
    _ask(world, sdn_pack(world.pack))
    assert [s["body"]["model"] for s in world.sent] == [HAIKU]
    rows = [r for r in calls.read()["rows"] if r.get("feature") == "sdn_explain"]
    assert rows and rows[-1]["model"] == HAIKU


def test_a_device_alert_s_pack_stays_on_explain_s_own_pin(world):  # noqa: F811
    _ask(world, world.pack)
    assert [s["body"]["model"] for s in world.sent] == [profiles.task("explain")["model"]]
    assert [r["feature"] for r in calls.read()["rows"]][-1] == "explain"


def test_the_sdn_pack_s_card_draws_the_sdn_task_s_mark(world):  # noqa: F811
    from html import unescape

    p = sdn_pack(world.pack)
    html = unescape(world.lab["client"].get(f"/v2/monitoring/alerts/pack/{p['id']}")
                    .get_data(as_text=True))
    words = profiles.task("sdn_explain")["words"]
    assert words in html and "Claude Haiku 5.5" in html
    other = unescape(world.lab["client"].get(f"/v2/monitoring/alerts/pack/{world.pack['id']}")
                     .get_data(as_text=True))
    assert words not in other
    # Pressed through its route: the call the mark promised goes to Haiku, its answer in place.
    world.answer = _answer(world.pack)
    r = world.lab["client"].post(f"/v2/monitoring/alerts/pack/{p['id']}/explain",
                                 headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert [s["body"]["model"] for s in world.sent] == [HAIKU]
    assert "Claude Haiku 5.5" in unescape(r.get_data(as_text=True))


def test_sdn_explain_is_an_ai_control_and_the_pack_stays_drawn(world, monkeypatch):  # noqa: F811
    """PHASE8_PLAN 15.13 through the pack's real route, as Explain's own check: the mark with
    its task, model and cap; disabled with its reason while hosted AI cannot answer."""
    from tests import ai_controls_check as AIC

    p = sdn_pack(world.pack)

    def get():
        return world.lab["client"].get(f"/v2/monitoring/alerts/pack/{p['id']}").get_data(
            as_text=True)

    def parity(html):
        assert f'data-pack="{p["id"]}"' in html
        assert html.count('class="pack-section"') == len(p["sections"]), \
            "every section of the pack is drawn"
    AIC.check_screen(monkeypatch, get, "sdn_explain", parity)
