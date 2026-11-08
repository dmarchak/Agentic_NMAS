"""The controller app deploy's plan binds what the post-check and a rollback will use (C2706,
the board's F2, K2, K3 and K6), and the post-check times each switch from the restart (C2708,
the board's F4 and K8): `modules/apps/channel.py` `plan`, `rollback_target`, `already_wrong`;
`modules/apps/post_check.py` `restart_origin`, `wait`.

Cases, each planted:
- the plan carries the post-check's expected switches, links and apps in `post_check.evaluate`'s
  shape, and its hash changes when any one of them changes, and when the rollback target does
  (a different previous request, none, or a different drop-in before), and is the same for a
  link written in reverse (the post-check's own comparison);
- with a recorded previous request the rollback target is that request, normalised by the
  script's parser, IPv4 and IPv6 listen addresses alike; with none it is the drop-in before
  (K3's kind), said; a recorded request the script would refuse refuses the plan, naming it;
- a malformed expected link refuses the plan;
- what is already missing or failing at plan time is drawn and named for the confirm, and not
  reading the controller is said, never "nothing missing";
- each switch's time is counted from the restart (the outcome's up_after_s plus the time
  since the outcome was read), from a script outcome or the transport's result; with no
  origin, or an outcome without up_after_s, the result says the restart's time is not known."""

import hashlib
import json

import pytest

from modules.apps import channel, post_check
from modules.platforms import profile
from tests.test_controller_deploy import (ALL_BACK, EXPECTED, LISTEN, MANAGER, SWITCH_2_DOWN,
                                          UNIT, Clock, enabled, eos, link, plan)

LISTEN_V6 = {"host": "2001:db8::10", "port": 6653}
PREVIOUS = {"apps": [], "listen": LISTEN}
PREVIOUS_V6 = {"apps": [], "listen": LISTEN_V6}
LINKS = [link(1, 1, 2, 1)]


def two_switches():
    return [eos("sw-a"), {"name": "sw-b", "dpid": 2,
                          "selected": profile.select("arista_eos", "4.17.0F")}]


def a_plan(tmp_path, sub="a", **over):
    args = dict(switches=two_switches(), links=LINKS, previous=PREVIOUS)
    args.update(over)
    got = plan(tmp_path / sub, **args)
    assert got["ok"] is True, got["refusals"]
    return got


# ── C2706: what the plan carries, and what its hash covers ───────────────────────────────────

def test_the_plan_carries_the_post_check_s_expected_switches_links_and_apps(tmp_path):
    got = a_plan(tmp_path)
    assert got["expected"] == {"switches": [1, 2], "links": LINKS, "apps": ["of_versions"]}
    # In the post-check's own shape: a read with everything back passes it.
    assert post_check.evaluate(got["expected"], ALL_BACK)["ok"] is True


CHANGES = {
    # Each changes one thing the post-check or a rollback uses, and nothing else.
    "switches": {"switches": [eos("sw-a")]},
    # The driver's DPIDs are integers and the post-check compares by equality, so text is
    # another switch to it.
    "a dpid as text": {"switches": [eos("sw-a"), dict(two_switches()[1], dpid="2")]},
    "links": {"links": LINKS + [link(1, 2, 2, 2)]},
    "a port as text": {"links": [link(1, "1", 2, 1)]},
    "previous": {"previous": {"apps": [{"name": "of_versions", "version": "0.9.0",
                                        "sha256": "1" * 64}], "listen": LISTEN}},
    "no previous": {"previous": None},
    "previous v6": {"previous": PREVIOUS_V6},
}


@pytest.mark.parametrize("change", sorted(CHANGES))
def test_a_change_to_what_the_post_check_or_a_rollback_uses_changes_the_plan_s_hash(
        tmp_path, change):
    base = a_plan(tmp_path, "base")
    moved = a_plan(tmp_path, "moved", **CHANGES[change])
    assert moved["request_sha256"] == base["request_sha256"]
    assert moved["dropin_after"] == base["dropin_after"]
    assert moved["plan_sha256"] != base["plan_sha256"], change


def test_another_enabled_app_is_expected_and_changes_the_hash(tmp_path):
    """The expected apps are the enabled set's, so they move with the request."""
    base = a_plan(tmp_path, "base")
    moved = a_plan(tmp_path, "moved",
                   items=enabled(tmp_path / "two", names=("of_versions", "switch_quirks")))
    assert moved["expected"]["apps"] == ["of_versions", "switch_quirks"]
    assert moved["plan_sha256"] != base["plan_sha256"]


def test_the_same_inputs_make_the_same_hash_and_a_reversed_link_is_the_same_link(tmp_path):
    one = a_plan(tmp_path, "one")
    two = a_plan(tmp_path, "two", links=[link(2, 1, 1, 1)])
    assert one["plan_sha256"] == two["plan_sha256"]


def test_a_different_drop_in_before_changes_the_hash_of_a_first_deploy(tmp_path):
    def cat(text):
        return f"# /etc/systemd/system/{UNIT}.d/mercury.conf\n{text}"
    first = a_plan(tmp_path, "first", previous=None, cat=cat("[Service]\nUser=ryu\n"))
    other = a_plan(tmp_path, "other", previous=None,
                   cat=cat(f"[Service]\nUser=ryu\nExecStart=\nExecStart={MANAGER}\n"))
    assert first["rollback"]["kind"] == other["rollback"]["kind"] == "dropin_before"
    assert first["plan_sha256"] != other["plan_sha256"]
    assert first["rollback"]["dropin_sha256"] == hashlib.sha256(
        b"[Service]\nUser=ryu\n").hexdigest()


# ── K2 and K3: the rollback target ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("previous,host", [
    (PREVIOUS, "192.0.2.10"),
    ({"apps": [], "listen": {"host": "2001:DB8:0::10", "port": 6653}}, "2001:db8::10"),
], ids=["ipv4", "ipv6"])
def test_a_recorded_previous_request_is_the_rollback_target(tmp_path, previous, host):
    got = a_plan(tmp_path, previous=previous)
    s = channel.script()
    want = s.parse_request(json.dumps(previous).encode("utf-8"))
    assert got["rollback"]["kind"] == "request"
    assert got["rollback"]["request"] == want
    assert got["rollback"]["request"]["listen"]["host"] == host      # the script's normal form
    assert got["rollback"]["request_sha256"] == s.request_sha256(want)
    assert "a miss applies the request ctl runs by Mercury's record" in got["rollback"]["words"]


def test_no_previous_request_is_the_drop_in_before_and_says_so(tmp_path):
    got = a_plan(tmp_path, previous=None)
    assert got["rollback"]["kind"] == "dropin_before" and got["rollback"]["request"] is None
    assert got["rollback"]["words"].startswith(
        "no previous request is recorded for ctl (its first deploy through Mercury)")
    assert "mercury.conf.prev" in got["rollback"]["words"]
    assert "the unit has no mercury.conf now" in got["rollback"]["words"]


@pytest.mark.parametrize("listen,said", [
    ({"host": "192.0.2.10", "port": "x"}, "listen.port is not a whole number"),
    ({"host": "2001:db8::zz", "port": 6653}, "listen.host does not parse as an IPv4 or IPv6"),
], ids=["ipv4", "ipv6"])
def test_a_recorded_request_the_script_would_refuse_refuses_the_plan(tmp_path, listen, said):
    got = plan(tmp_path, switches=two_switches(), links=LINKS,
               previous={"apps": [], "listen": listen})
    assert got["ok"] is False and "request" not in got
    [why] = got["refusals"]
    assert why.startswith("the rollback target, the request ctl ran before by Mercury's "
                          "record, would be refused by the script: ") and said in why


def test_a_malformed_expected_link_refuses_the_plan(tmp_path):
    got = plan(tmp_path, switches=two_switches(), links=[{"src": {"dpid": 1}}],
               previous=PREVIOUS)
    assert got["ok"] is False
    assert any(r.startswith("the expected link {'src': {'dpid': 1}} is not a pair of switch "
                            "ports") for r in got["refusals"]), got["refusals"]


def test_an_expected_switch_with_no_dpid_refuses_the_plan(tmp_path):
    got = plan(tmp_path, switches=[eos("sw-a"), dict(eos("sw-b"), dpid=None)], links=[],
               previous=PREVIOUS)
    assert got["ok"] is False
    assert ("the expected switch sw-b has no DPID, so the post-check could not wait for it"
            in got["refusals"]), got["refusals"]


# ── K6: what is already missing or failing at plan time ──────────────────────────────────────

def test_what_is_already_missing_is_drawn_and_named_for_the_confirm(tmp_path):
    now = dict(SWITCH_2_DOWN, links={"ok": True, "links": []},
               health={"of_versions": {"ok": False, "error": "500"}})
    got = a_plan(tmp_path, observed=now)
    already = got["already"]
    assert already["read"] is True
    assert already["missing_switches"] == ["sw-b (2)"]
    assert already["missing_links"] == ["1:1-2:1"]
    assert already["unhealthy"] == ["of_versions (500)"]
    assert already["expecting"] == ["expecting sw-b (2) to reconnect",
                                    "expecting the link 1:1-2:1 to come back",
                                    "expecting of_versions's /health to recover"]
    assert "this deploy will miss and roll back" in already["words"]
    # A live read is drawn, not bound: the hash is the same with everything answering.
    assert got["plan_sha256"] == a_plan(tmp_path, "b", observed=ALL_BACK)["plan_sha256"]


def test_nothing_missing_and_not_read_are_different_states(tmp_path):
    fine = a_plan(tmp_path, "fine", observed=ALL_BACK)["already"]
    assert fine["read"] is True and fine["expecting"] == []
    assert fine["words"] == "every expected switch, link and app's /health answers now"
    blind = a_plan(tmp_path, "blind")["already"]
    assert blind["read"] is False and blind["expecting"] == []
    assert "not read at plan time" in blind["words"] and "not known" in blind["words"]


# ── C2708, K8: each switch's time from the restart ───────────────────────────────────────────

def test_each_switch_s_time_is_counted_from_the_restart():
    clock = Clock()
    clock.t = 100.0                        # the outcome is read back at 100 s on this clock
    origin = post_check.restart_origin({"ok": True, "up_after_s": 19.4}, read_at=clock())
    assert origin["known"] is True and origin["at"] == pytest.approx(80.6)
    clock.t = 102.0                        # the post-check's first read, 2 s later
    reads = iter([SWITCH_2_DOWN, ALL_BACK])
    got = post_check.wait(lambda: next(reads), EXPECTED, restart=origin, clock=clock,
                          sleep=clock.sleep)
    assert got["ok"] is True
    assert got["after_restart"] == {1: 21.4, 2: 26.4}
    assert got["came_back"] == {1: 0.0, 2: 5.0}          # the post-check's own, as before
    assert got["after_restart_s"] == 26.4
    assert got["words"].startswith("every expected switch, link and app's /health was back "
                                   "26.4 s after the restart (5.0 s and 2 reads of the "
                                   "post-check's own)")


def test_the_transport_s_result_carries_the_outcome_the_origin_reads():
    got = post_check.restart_origin({"ok": True, "outcome": {"ok": True, "up_after_s": 3}},
                                    read_at=10.0)
    assert got["known"] is True and got["at"] == 7.0 and got["up_after_s"] == 3.0


@pytest.mark.parametrize("outcome,why", [
    (None, "no apply outcome was read"),
    ({"ok": False, "step": "wait"}, "the apply outcome reports no time to active"),
    ({"ok": True, "up_after_s": "19.4"}, "the apply outcome reports no time to active"),
])
def test_an_unknown_restart_time_is_said_never_counted_silently(outcome, why):
    origin = post_check.restart_origin(outcome, read_at=5.0)
    assert origin["known"] is False and why in origin["words"]
    clock = Clock()
    got = post_check.wait(lambda: ALL_BACK, EXPECTED, restart=origin, clock=clock,
                          sleep=clock.sleep)
    assert got["ok"] is True and got["after_restart"] is None
    assert got["after_restart_s"] is None and got["origin"]["known"] is False
    assert "counted from its first read: the restart's time is not known" in got["words"]
    assert why in got["words"]


def test_no_origin_given_is_said():
    clock = Clock()
    got = post_check.wait(lambda: ALL_BACK, EXPECTED, clock=clock, sleep=clock.sleep)
    assert got["after_restart"] is None
    assert "the restart's time is not known: no restart origin was given" in got["words"]


def test_a_miss_names_the_time_since_the_restart_and_that_the_bound_runs_on_its_own():
    clock = Clock()
    origin = post_check.restart_origin({"up_after_s": 20}, read_at=0.0)
    got = post_check.wait(lambda: SWITCH_2_DOWN, EXPECTED, restart=origin, clock=clock,
                          sleep=clock.sleep)
    limit = post_check.bound()["seconds"]
    assert got["ok"] is False and got["elapsed_s"] == limit
    assert got["after_restart"] == {1: 20.0}
    assert f"({round(limit + 20.0, 1)} s after the restart)" in got["words"]
    assert "The bound runs on the post-check's own time" in got["words"]
