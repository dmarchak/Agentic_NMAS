"""The AI troubleshooting starts' spend and race (C3751, C3752, C3753; the operator, 2026-11-15).

- C3751: a turn-on catch-up's investigation is the person's call AND fixit_auto's spend: its
  row's trigger is the person's with ``counts_for`` the feature, so `spend.feature_spent`
  counts it and a later automatic start the same day is held to the feature's caps with it.
  The test is the operator's: a catch-up spends X, then an automatic start with a feature cap
  below X plus one more investigation is refused, naming the cap.
- C3752: the catch-up plans and claims under the network's one start lock, each planned
  worst case reserved in `modules.ai.reservations` (so other processes and the gateway count
  it), settled once the investigation's own call reserves.
- C3753: the calls in flight are counted in the start's day check and in the list's day room.
"""

import pytest

from modules.ai import reservations
from tests.test_fixit_catch_up import (LISTED, form_of, inc_of, planted, post,  # noqa: F401
                                       world)
from tests.test_fixit_auto import NOW, policy  # noqa: F401  (the fixture)
from tests.test_fixit_section_v2 import NET, web  # noqa: F401  (the fixture)
from tests.test_fixit_troubleshoot import ai  # noqa: F401  (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401  (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)


def _spent_rows():
    from modules.ai import calls
    return [r for r in calls.read()["rows"] if r.get("feature") == "fixit_troubleshoot"
            and float(r.get("cost_usd") or 0) > 0]


class TestACatchUpCountsForTheFeature:
    def test_a_later_automatic_start_is_held_to_the_caps_with_its_spend(self, world):
        from modules import heal_notice
        from modules.ai import background, calls, spend
        from modules.ai import fixit_troubleshoot as AIT
        from modules.nsot import listref

        got = planted()
        _html, shown, each = form_of(world)
        r, out = post(world, shown, each)
        assert r.status_code == 200, out
        rows = _spent_rows()
        assert rows, "the ticked one's investigation spent"
        assert all(x["trigger"]["kind"] == "person" for x in rows)
        assert all(x["trigger"].get("counts_for") == {
            "feature": "fixit_auto", "network": listref.network_id(NET)} for x in rows), rows
        x = sum(float(r["cost_usd"]) for r in rows)
        net = listref.network_id(NET)
        mine = spend.feature_spent(net, "fixit_auto", calls.today())
        assert mine["day_usd"] == pytest.approx(x), (mine, x)
        # The feature's day cap below X plus one more investigation's worst case.
        worst = AIT.worst_usd()
        background.set_caps(net, "fixit_auto", day_cap_usd=round(x + worst * 0.5, 4),
                            month_cap_usd=10.0, actor="op@example.com", verified="access")
        trigger = AIT.background_trigger(NET, "fixit-auto-x-1", "decision:x")
        state, which, words = heal_notice._fixit_state(inc_of(got["cant_fix"]), trigger, NOW)
        assert (state, which) == ("capped", "day"), words
        assert "fixit_auto's spend on" in words and "day cap" in words, words


class TestTheStartsAreReserved:
    def test_each_planned_start_is_reserved_under_the_lock_and_settled(self, world,
                                                                       monkeypatch):
        from modules import filestore, heal_notice
        held, locked = [], []
        real_reserve, real_lock = reservations.reserve, filestore.PathLock

        def reserve(call_id, usd, **kw):
            held.append((call_id, kw.get("feature"), kw.get("counts")))
            return real_reserve(call_id, usd, **kw)

        class Lock(real_lock):
            def __enter__(self):
                locked.append(self.path())
                return super().__enter__()
        monkeypatch.setattr(reservations, "reserve", reserve)
        monkeypatch.setattr(filestore, "PathLock", Lock)
        seen = []
        monkeypatch.setattr(heal_notice, "catch_up_investigation",
                            lambda network, iid, key, **kw: seen.append(
                                (iid, kw.get("planned"),
                                 sorted(reservations.open_reservations()["held"]))) or {})
        from modules import troubleshoot_control as T
        planted()
        _html, shown, each = form_of(world)
        order = T.catch_up_line(NET)["ids"]
        r, out = post(world, shown, each)
        assert r.status_code == 200, out
        planned = [h for h in held if h[0].startswith("fixit-start-")]
        # Premise corrected (C3872, 7d54cf24: "a refused start spends no key"): five are listed,
        # the incident whose automatic start a cap refused among them (LISTED).
        assert [(f, c) for _i, f, c in planned] == [("fixit_auto", True)] * 5, held
        assert any(p.endswith("fixit_starts.lock") for p in locked), locked
        # Each investigation ran while its own planned start was still held...
        assert [s[0] for s in seen] == order and len(order) == 5
        assert all(s[1] in s[2] for s in seen), seen
        # ...and none is left once it ended.
        left = reservations.open_reservations()["held"]
        assert not [k for k in left if k.startswith("fixit-start-")], left


def _press_switch(world, html):
    """Press the control strip's AI switch as *html* draws it: the form under ``id="ctl-ai"``,
    its action and its fields."""
    import re
    form = re.search(r'id="ctl-ai" method="post" action="([^"]+)".*?name="level" '
                     r'value="([a-z]+)">.*?name="line_digest" value="([0-9a-f]*)"', html, re.S)
    assert form, "no AI switch under #ctl-ai"
    return world.client.post(form.group(1), headers={"HX-Request": "true"},
                             data={"level": form.group(2), "line_digest": form.group(3)})


class TestTheSwitchIsLinkedWhereItIsNamed:
    """The operator, 2026-11-15 (r7's card): every sentence naming the automatic
    troubleshooting switch links straight to it: the AI toggle on Troubleshoot › Incidents'
    control strip for that network (on Needs attention's before C3789)."""

    def test_the_status_and_the_costs_line_link_to_this_network_s_switch(self, world):
        import re
        from html import unescape

        from tests.test_fixit_section_v2 import page, plant
        iid = plant()
        r, html = page(world.client, iid)
        assert r.status_code == 200
        html = unescape(html)
        # Premise corrected (C3789, the operator, 2026-11-15: "The control strip: remove it
        # from Needs attention; keep it only on Incidents"): the switch is on Troubleshoot ›
        # Incidents' strip, where Needs attention's was before.
        want = f"/v2/incidents?list={NET}#ctl-ai"
        # Premise corrected (board R5's status line, becced07; 9f62b2c7 and 106c117d, the
        # operator, 2026-11-16: the status says why a person is needed, from the incident's
        # record): this incident's status says Mercury has no fix it runs by itself and the AI
        # can investigate, naming no switch, where it said "automatic troubleshooting is off for
        # this network". A status that names the switch links it (`switch_linked`); the costs
        # line names it here, linked (below).
        status = re.search(r'data-bluf="status" data-status[^>]*>(.*?)</div>', html,
                           re.S).group(1)
        plain = re.sub(r"<[^>]+>", "", status)
        assert plain.endswith("The AI can investigate"), status
        assert "automatic troubleshooting" not in plain or (
            f'<a href="{want}" data-switch="fixit_auto">automatic troubleshooting</a>'
            in status), status
        costs = re.search(r'<p class="small fixit-auto"[^>]*>(.*?)</p>', html, re.S).group(1)
        assert f'<a href="{want}" data-switch="fixit_auto">off for {NET}</a>' in costs, costs
        # Followed, the link opens the switch it names, which works: pressed before the
        # limits are acknowledged, it is refused and the switch stays off.
        from modules.fixit import auto as A
        landing = unescape(world.client.get(want.split("#")[0]).get_data(as_text=True))
        r = _press_switch(world, landing)
        assert r.status_code == 409 and not A.switch(NET)["on"]

    def test_the_strip_holds_the_anchor_the_link_names(self, world):
        """The strip's switch under the anchor the link names (``#ctl-ai``) turns Automatic on,
        pressed as drawn, once the network's limits are acknowledged (Gate 2)."""
        from html import unescape

        from modules import troubleshoot_control as troubleshoot
        from modules.ai import background
        from modules.fixit import auto as A
        est = background.estimate(background._network(NET), A.FEATURE)
        troubleshoot.set_limits(NET, incident_usd=1.0, day_usd=1.5, month_usd=10.0,
                                shown=est["digest"], accepted=True, actor="op@example.com",
                                verified="access")
        strip = unescape(world.client.get(f"/v2/control/strip?list={NET}").get_data(
            as_text=True))
        r = _press_switch(world, strip)
        assert r.status_code == 200, r.get_data(as_text=True)
        assert A.switch(NET)["on"]


class TestTheCallsInFlightAreCounted:
    def _flying(self, usd):
        assert reservations.reserve("other-call", usd, judge=lambda _h: None, ttl_s=600,
                                    feature="explain", network="", day="")["ok"]

    def test_the_start_s_day_check_counts_them(self, world):
        from modules import heal_notice
        from modules.ai import gateway, triggers
        got = planted()
        cap = gateway.day_cap()
        self._flying(cap)
        state, which, words = heal_notice._fixit_state(
            inc_of(got["stream"]), triggers.person("op@example.com"), NOW)
        assert (state, which) == ("capped", "day"), words
        assert "reserved by 1 call(s) in flight" in words, words

    def test_the_list_s_day_room_counts_them(self, world):
        from modules.ai import gateway, settings_view
        before = settings_view.catch_up_room(NET)["day"]
        self._flying(0.25)
        after = settings_view.catch_up_room(NET)["day"]
        assert gateway.day_cap() is not None
        assert after == pytest.approx(max(0.0, before - 0.25)), (before, after)
