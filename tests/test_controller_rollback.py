"""The controller app deploy's rollback, its window and an app's start-time config (P6's deploy
board, signed 2026-11-07: decisions K3 and K9, findings F1, F3, F5 and F7; C2705, C2707, C2709,
C2711; and C2706 and C2708 as the deploy uses them): `modules/apps/post_check.deploy`,
`landed`, `rollback_refusal`, `channel.rollback_target`, `channel.plan_hash`, `channel.window`,
`channel.put_back_request` and `channel.config_secret_refusal`.

The channel is a fake (`FakeChannel`, as tests/test_controller_deploy.py's) answering the apply
script's outcomes in the script's own shapes (its steps: tests/test_controller_apply.py holds the
script to them); the plan is `channel.plan`'s on temporary git repositories.

Cases, each planted:
- C2705 (F1): an apply that failed after the script wrote the new drop-in (its outcome's step
  daemon-reload, restart, wait or after-write) is rolled back and post-checked again; one that
  failed before (a refusal, a staging failure, an exception with no step) is not; an outcome not
  read is "unknown" and never rolled back by itself (K7);
- K3: a first deploy's miss (no previous request, a drop-in before) is rolled back by the second
  request kind, the put-back bound to the plan's drop-in before, and its post-check waits for
  none of Mercury's apps;
- C2709 (F5): "rolled back", "rollback failed" and "not rolled back" are three outcomes, and
  "rollback failed" only ever follows a rollback that was tried;
- C2706: the deploy post-checks the plan's expected and rolls back to the plan's rollback
  target, IPv4 and IPv6 listen addresses alike, and refuses before its window a rollback
  request or a plan whose bound fields moved after its hash, naming both;
- C2708 (K8): the deploy's post-check and its rollback's each count from their own restart;
- C2711 (F7): the window covers the session's opening, the command's wait and the post-check,
  twice, from those constants;
- C2707 (F3): an app's config rides in the request by its sha256, moves the plan's hash, and a
  config holding anything the redaction masks is refused naming the key, never the value; an
  address in a config, IPv4 or IPv6, is not a secret."""

import hashlib

import pytest

from modules import connection
from modules.apps import channel, post_check, transport
from tests.test_controller_deploy import (ALL_BACK, EXPECTED, LISTEN, MANAGER, OK_APPLY,
                                          SWITCH_2_DOWN, UNIT, Clock, FakeChannel, enabled, eos,
                                          expected_switches, ls, show)

BEFORE = "[Service]\nUser=ryu\n"
CAT = (f"# /lib/systemd/system/{UNIT}\n[Service]\nExecStart={MANAGER}\n\n"
       f"# /etc/systemd/system/{UNIT}.d/mercury.conf\n{BEFORE}")
PREVIOUS = {"apps": [{"name": "of_versions", "version": "1.0.0", "sha256": "1" * 64}],
            "listen": LISTEN}
#: The script's outcomes for an apply that failed after it wrote the drop-in (its steps).
LANDED = {
    "daemon-reload": {"ok": False, "step": "daemon-reload", "main_pid_before": "100",
                      "error": "systemctl daemon-reload answered 1 ()"},
    "restart": {"ok": False, "step": "restart", "main_pid_before": "100",
                "error": "systemctl restart ryu-manager.service answered 1 ()"},
    "wait": {"ok": False, "step": "wait", "main_pid_before": "100", "main_pid_after": "0",
             "error": "ryu-manager.service was not active with a new MainPID and User=ryu "
                      "within 60 s"},
    "after-write": {"ok": False, "step": "after-write", "main_pid_before": "100",
                    "error": "the drop-in was written, then OSError: planted"}}
NOT_LANDED = {
    "refused": {"ok": False, "refused": "apps[0]'s folder ... changed after it was staged"},
    "exception before the write": {"ok": False, "error": "OSError: [Errno 28] no space"}}
ROLLBACK_BACK = dict(ALL_BACK, health={})       # the put-back runs none of Mercury's apps


def a_plan(tmp_path, cat=CAT, items=None, previous=None, listen=LISTEN):
    """A plan whose expected is EXPECTED and whose rollback target is *previous*, or with none
    the drop-in before in *cat* (the deploy takes both from the plan; C2706)."""
    got = channel.plan(network="lab9", controller="ctl", unit=UNIT,
                       enabled=enabled(tmp_path) if items is None else items,
                       host={"show": show("ryu"), "ls": ls("mercury"), "cat": cat},
                       listen=listen, switches=expected_switches(), links=EXPECTED["links"],
                       previous=previous)
    assert got["ok"] is True, got["refusals"]
    assert got["expected"] == EXPECTED
    return got


def run(tmp_path, reads, outcomes, previous=None, cat=CAT, listen=LISTEN):
    accepted = a_plan(tmp_path, cat=cat, previous=previous, listen=listen)
    clock, chan = Clock(), FakeChannel(outcomes)
    reads = iter(reads)
    receipt = post_check.deploy(accepted, channel=chan, read=lambda: next(reads, SWITCH_2_DOWN),
                                declare_window=lambda *a: {"ok": True}, by="op@example.invalid",
                                clock=clock, sleep=clock.sleep, now=clock)
    return receipt, chan, accepted


def misses():
    """Reads that miss one switch for the whole first post-check."""
    return [SWITCH_2_DOWN] * (int(post_check.bound()["seconds"] // post_check.POLL_S) + 1)


# ── C2705 (F1): an apply that landed is rolled back ──────────────────────────────────────────

@pytest.mark.parametrize("step", sorted(LANDED))
def test_an_apply_that_failed_after_the_drop_in_was_written_is_rolled_back(tmp_path, step):
    receipt, chan, accepted = run(tmp_path, [ALL_BACK], [LANDED[step], OK_APPLY],
                                  previous=PREVIOUS)
    assert receipt["outcome"] == "rolled back", receipt
    assert receipt["landed"] == "dropin" and receipt["rollback_target"] == "request"
    assert chan.staged == [accepted["request"], PREVIOUS]
    assert [s["step"] for s in receipt["steps"]] == ["window", "apply", "rollback apply",
                                                     "rollback post-check"]
    assert "the apply failed after the new drop-in was written" in receipt["error"]


@pytest.mark.parametrize("step", sorted(LANDED))
def test_a_first_deploy_whose_apply_landed_is_put_back(tmp_path, step):
    receipt, chan, accepted = run(tmp_path, [ROLLBACK_BACK], [LANDED[step], OK_APPLY])
    assert receipt["outcome"] == "rolled back", receipt
    assert receipt["rollback_target"] == "dropin_before"
    assert chan.staged[1] == channel.put_back_request(BEFORE) == accepted["rollback"]["request"]


@pytest.mark.parametrize("case", sorted(NOT_LANDED))
def test_an_apply_that_failed_before_the_drop_in_was_written_rolls_nothing_back(tmp_path,
                                                                                case):
    receipt, chan, _ = run(tmp_path, [ALL_BACK], [NOT_LANDED[case]], previous=PREVIOUS)
    assert receipt["outcome"] == "apply failed" and receipt["landed"] == "nothing"
    assert chan.calls == ["stage", "apply"], "no rollback: nothing landed"


def test_a_staging_failure_rolls_nothing_back(tmp_path):
    class Broken(FakeChannel):
        def stage(self, req):
            self.calls.append("stage")
            raise OSError("Socket is closed")

    accepted, chan = a_plan(tmp_path, previous=PREVIOUS), Broken([])
    receipt = post_check.deploy(accepted, channel=chan, read=lambda: ALL_BACK,
                                declare_window=lambda *a: {"ok": True},
                                by="op@example.invalid", clock=Clock(), sleep=lambda s: None,
                                now=Clock())
    assert receipt["outcome"] == "apply failed" and chan.calls == ["stage"]


def test_an_outcome_not_read_is_unknown_and_never_rolled_back_by_itself(tmp_path):
    unknown = {"ok": False, "unknown": True, "error": "no outcome of this run was read"}
    receipt, chan, _ = run(tmp_path, [ALL_BACK], [unknown], previous=PREVIOUS)
    assert receipt["outcome"] == "unknown" and chan.calls == ["stage", "apply"]


@pytest.mark.parametrize("outcome, want", [
    ({"ok": False, "refused": "x"}, "nothing"),
    ({"ok": False, "error": "OSError: x"}, "nothing"),
    ({"ok": False, "error": "staging failed (OSError: x)"}, "nothing"),
    ({"ok": False, "step": "daemon-reload", "error": "x"}, "dropin"),
    ({"ok": False, "step": "restart", "error": "x"}, "dropin"),
    ({"ok": False, "step": "wait", "error": "x"}, "dropin"),
    ({"ok": False, "step": "after-write", "error": "x"}, "dropin"),
    ({"ok": False, "unknown": True}, "unknown"),
    ({"ok": False, "step": "a step the script never writes"}, "unknown"),
    ({"ok": False, "step": "stage", "command_sent": False, "error": "x"}, "nothing"),
    ({"ok": False, "step": "request", "command_sent": False, "error": "x"}, "nothing"),
    ({"ok": False, "step": "command", "command_sent": True, "error": "x"}, "unknown"),
    ({"ok": False, "step": "done", "command_sent": True, "error": "x"}, "unknown"),
    ({}, "unknown"),
    (None, "unknown")])
def test_what_landed_is_read_from_the_script_s_step(outcome, want):
    assert post_check.landed(outcome) == want


def test_every_step_the_script_writes_past_the_drop_in_counts_as_landed():
    """The script's own steps (its `restart` and `restart_after_write`) are WROTE_DROPIN's."""
    import ast
    import inspect

    s = channel.script()
    src = inspect.getsource(s.restart) + inspect.getsource(s.restart_after_write)
    steps = {n.values[i].value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Dict)
             for i, k in enumerate(n.keys)
             if isinstance(k, ast.Constant) and k.value == "step"
             and isinstance(n.values[i], ast.Constant)}
    assert steps == {"daemon-reload", "restart", "wait", "after-write", "running"}
    assert steps == set(post_check.WROTE_DROPIN)


# ── K3: the first deploy's rollback is the put-back ─────────────────────────────────────────

def test_a_first_deploy_s_miss_is_put_back_and_post_checked_for_what_the_before_runs(
        tmp_path):
    receipt, chan, accepted = run(tmp_path, misses() + [ROLLBACK_BACK], [OK_APPLY, OK_APPLY])
    assert receipt["outcome"] == "rolled back", receipt
    s = channel.script()
    assert chan.staged == [accepted["request"], {"kind": s.PUT_BACK,
                                                 "before_sha256": s.before_sha256(BEFORE)}]
    assert [st["step"] for st in receipt["steps"]] == ["window", "apply", "post-check",
                                                       "rollback put-back",
                                                       "rollback post-check"]
    assert receipt["rollback_post_check"]["ok"] is True


def test_a_put_back_whose_post_check_misses_is_rollback_failed(tmp_path):
    receipt, _, _ = run(tmp_path, [], [OK_APPLY, OK_APPLY])
    assert receipt["outcome"] == "rollback failed"
    assert "the rollback's post-check missed too" in receipt["error"]


def test_a_put_back_the_script_refuses_is_rollback_failed_naming_it(tmp_path):
    refusal = {"ok": False, "refused": "there is no drop-in before to put back"}
    receipt, _, _ = run(tmp_path, [], [OK_APPLY, refusal])
    assert receipt["outcome"] == "rollback failed"
    assert "the rollback (put-back) failed: there is no drop-in before" in receipt["error"]


def test_the_put_back_is_bound_to_the_drop_in_before_the_plan_read():
    s = channel.script()
    req = channel.put_back_request(BEFORE)
    assert req == {"kind": "put-before-back", "before_sha256": hashlib.sha256(
        BEFORE.encode()).hexdigest()}
    assert s.parse_request(channel.json.dumps(req).encode()) == req
    with pytest.raises(channel.ChannelRefused, match="there was no drop-in before the deploy"):
        channel.put_back_request("")


def test_the_rollback_target_is_the_previous_request_else_the_put_back_else_none():
    """`channel.rollback_target`, the one owner of what a rollback sends (the plan carries its
    answer, and `post_check.deploy` sends that answer's request)."""
    def target(previous, before):
        return channel.rollback_target(previous, controller="ctl", dropin_before_text=before)
    s = channel.script()
    got = target(PREVIOUS, BEFORE)
    assert got["kind"] == "request" and got["request"] == s.parse_request(
        channel.json.dumps(PREVIOUS).encode())
    put_back = target(None, BEFORE)
    assert put_back["kind"] == "dropin_before"
    assert put_back["request"] == channel.put_back_request(BEFORE)
    assert put_back["dropin_sha256"] == put_back["request"]["before_sha256"]
    none = target(None, "")
    assert none["kind"] == "dropin_before" and none["request"] is None
    assert "no drop-in before for the apply script to put back" in none["words"]
    assert "a miss is not rolled back" in none["words"]


# ── C2706: the deploy uses what was confirmed; K8: times from the restart ───────────────────

LISTENS = pytest.mark.parametrize("listen", [LISTEN, {"host": "2001:db8::10", "port": 6653}],
                                  ids=["ipv4", "ipv6"])


def deploy_of(accepted, reads, outcomes):
    clock, chan, windows = Clock(), FakeChannel(outcomes), []
    reads = iter(reads)

    def declare(*args):
        windows.append(args)
        return {"ok": True}
    receipt = post_check.deploy(accepted, channel=chan, read=lambda: next(reads, SWITCH_2_DOWN),
                                declare_window=declare, by="op@example.invalid", clock=clock,
                                sleep=clock.sleep, now=clock)
    return receipt, chan, windows


@LISTENS
def test_a_deploy_post_checks_the_plan_s_expected_and_nothing_else(tmp_path, listen):
    """A plan expecting only switch 1 and no link is deployed on reads missing switch 2 and
    the link; one expecting both misses on the same reads (C2706)."""
    one = channel.plan(network="lab9", controller="ctl", unit=UNIT, enabled=enabled(tmp_path),
                       host={"show": show("ryu"), "ls": ls("mercury"), "cat": CAT},
                       listen=listen, switches=[eos()], links=[], previous=PREVIOUS)
    assert one["ok"] is True, one["refusals"]
    down = dict(SWITCH_2_DOWN, links={"ok": True, "links": []})
    receipt, _, _ = deploy_of(one, [down], [OK_APPLY])
    assert receipt["outcome"] == "deployed", receipt
    both = a_plan(tmp_path / "both", previous=PREVIOUS, listen=listen)
    receipt, _, _ = deploy_of(both, [down] * len(misses()) + [ALL_BACK], [OK_APPLY, OK_APPLY])
    assert receipt["post_check"]["ok"] is False and receipt["outcome"] == "rolled back"
    assert receipt["post_check"]["last"]["missing_switches"] == [2]


@pytest.mark.parametrize("previous, host", [
    (PREVIOUS, "192.0.2.10"),
    (dict(PREVIOUS, listen={"host": "2001:DB8:0::10", "port": 6653}), "2001:db8::10")],
    ids=["ipv4", "ipv6"])
def test_a_rollback_sends_the_plan_s_rollback_request(tmp_path, previous, host):
    """What a rollback sends is the plan's rollback target's request, in the script's normal
    form (the IPv6 listen address compressed), hashed by the plan (C2706)."""
    receipt, chan, accepted = run(tmp_path, misses() + [ALL_BACK], [OK_APPLY, OK_APPLY],
                                  previous=previous)
    assert receipt["outcome"] == "rolled back", receipt
    assert chan.staged[1] == accepted["rollback"]["request"]
    assert chan.staged[1]["listen"]["host"] == host


def test_a_put_back_sends_the_plan_s_put_back_request(tmp_path):
    receipt, chan, accepted = run(tmp_path, misses() + [ROLLBACK_BACK], [OK_APPLY, OK_APPLY])
    assert receipt["outcome"] == "rolled back", receipt
    assert accepted["rollback"]["kind"] == "dropin_before"
    assert chan.staged[1] == accepted["rollback"]["request"]
    assert chan.staged[1]["before_sha256"] == accepted["rollback"]["dropin_sha256"]


def _rehash(accepted, request):
    s = channel.script()
    rollback = dict(accepted["rollback"], request=request,
                    request_sha256=s.request_sha256(request))
    return dict(accepted, rollback=rollback)


@pytest.mark.parametrize("case", ["request moved", "put-back rebound"])
def test_a_rollback_target_that_is_not_the_plan_s_refuses_before_the_window(tmp_path, case):
    """A rollback request other than the one the plan hashed (or a put-back bound to another
    drop-in than the plan read) refuses the deploy before its window, naming both."""
    if case == "request moved":
        accepted = a_plan(tmp_path, previous=PREVIOUS)
        moved = dict(accepted["rollback"]["request"], listen={"host": "192.0.2.11",
                                                              "port": 6653})
        accepted = dict(accepted, rollback=dict(accepted["rollback"], request=moved))
        said = ["the rollback request's hash is", accepted["rollback"]["request_sha256"]]
    else:
        accepted = a_plan(tmp_path)
        accepted = _rehash(accepted, dict(accepted["rollback"]["request"],
                                          before_sha256="0" * 64))
        said = ["the put-back is bound to the drop-in '" + "0" * 64,
                accepted["rollback"]["dropin_sha256"]]
    receipt, chan, windows = deploy_of(accepted, [ALL_BACK], [OK_APPLY])
    assert receipt["outcome"] == "refused" and chan.calls == [] and windows == []
    for part in said:
        assert part in receipt["error"], (part, receipt["error"])


@LISTENS
@pytest.mark.parametrize("change", ["a switch dropped", "a link dropped", "no app",
                                    "the rollback's drop-in hash"])
def test_a_plan_whose_bound_fields_moved_after_its_hash_refuses_before_the_window(
        tmp_path, listen, change):
    """The deploy recomputes the plan's hash from what it carries (`channel.plan_hash`) and
    refuses one that moved since the confirm, naming both hashes (C2706)."""
    accepted = a_plan(tmp_path, previous=PREVIOUS, listen=listen)
    assert channel.plan_hash(accepted) == accepted["plan_sha256"]
    expected = dict(accepted["expected"])
    rollback = dict(accepted["rollback"])
    if change == "a switch dropped":
        expected["switches"] = [1]
    elif change == "a link dropped":
        expected["links"] = []
    elif change == "no app":
        expected["apps"] = []
    else:
        rollback["dropin_sha256"] = "0" * 64
    moved = dict(accepted, expected=expected, rollback=rollback)
    receipt, chan, windows = deploy_of(moved, [ALL_BACK], [OK_APPLY])
    assert receipt["outcome"] == "refused" and chan.calls == [] and windows == []
    assert f"it was confirmed as '{accepted['plan_sha256']}'" in receipt["error"]
    assert channel.plan_hash(moved) in receipt["error"]


@LISTENS
def test_each_switch_s_time_in_a_deploy_and_its_rollback_counts_from_its_restart(tmp_path,
                                                                                 listen):
    """K8: the deploy's post-check counts from the deploy's restart (the outcome's up_after_s,
    read the moment it came back), and the rollback's from the rollback's."""
    deployed = dict(OK_APPLY, up_after_s=19.4)
    receipt, _, _ = run(tmp_path / "ok", [ALL_BACK], [deployed], previous=PREVIOUS,
                        listen=listen)
    assert receipt["outcome"] == "deployed"
    assert receipt["post_check"]["origin"]["known"] is True
    assert receipt["post_check"]["after_restart"] == {1: 19.4, 2: 19.4}
    assert "back 19.4 s after the restart" in receipt["post_check"]["words"]
    rolled = dict(OK_APPLY, up_after_s=7)
    receipt, _, _ = run(tmp_path / "back", misses() + [ALL_BACK], [deployed, rolled],
                        previous=PREVIOUS, listen=listen)
    assert receipt["outcome"] == "rolled back", receipt
    assert receipt["post_check"]["after_restart"] == {1: pytest.approx(19.4)}
    assert receipt["rollback_post_check"]["after_restart"] == {1: 7.0, 2: 7.0}


def test_an_apply_outcome_without_its_time_to_active_is_said_in_the_deploy(tmp_path):
    receipt, _, _ = run(tmp_path, [ALL_BACK], [OK_APPLY], previous=PREVIOUS)
    assert receipt["outcome"] == "deployed"
    assert receipt["post_check"]["after_restart"] is None
    assert "the apply outcome reports no time to active" in receipt["post_check"]["words"]


# ── C2709 (F5): three outcomes, never "rollback failed" with none tried ─────────────────────

def test_with_nothing_to_roll_back_to_the_outcome_is_not_rolled_back(tmp_path):
    receipt, chan, _ = run(tmp_path, [], [OK_APPLY], cat="")
    assert receipt["outcome"] == "not rolled back"
    assert "no rollback was tried" in receipt["error"]
    assert chan.calls == ["stage", "apply"]


def test_rollback_failed_only_follows_a_rollback_that_was_tried(tmp_path):
    for previous, cat in ((PREVIOUS, CAT), (None, CAT), (None, "")):
        receipt, chan, _ = run(tmp_path / str(len(cat)) / str(previous is None), [],
                               [OK_APPLY, OK_APPLY], previous=previous, cat=cat)
        tried = chan.calls.count("apply") == 2
        assert (receipt["outcome"] == "rollback failed") == tried, receipt["outcome"]


# ── C2711 (F7): the window covers what it sits inside ───────────────────────────────────────

def test_the_window_covers_the_command_s_wait_and_the_post_check_twice_over():
    got = channel.window()
    # The post-check is two bounds, one after the other (2026-11-11): Ryu's start, then every
    # switch back after Ryu answers; the window covers both.
    one = (connection.CONNECT_TIMEOUT_S + transport.command_bound_s()
           + post_check.ryu_bound()["seconds"] + post_check.bound()["seconds"])
    assert got["seconds"] == channel.window_seconds() == int(round(2 * one))
    assert got["seconds"] >= 2 * (transport.command_bound_s() + post_check.bound()["seconds"])
    for part in (f"{connection.CONNECT_TIMEOUT_S} s", f"{transport.command_bound_s():.0f} s",
                 f"Ryu's start bound of {post_check.ryu_bound()['seconds']} s",
                 f"{post_check.bound()['seconds']} s", "staging transfer has no bound"):
        assert part in got["words"], part


def test_the_plan_declares_that_window(tmp_path):
    assert a_plan(tmp_path)["window"]["seconds"] == channel.window()["seconds"]


# ── C2707 (F3): an app's start-time config ──────────────────────────────────────────────────

def configured(tmp_path, config):
    items = enabled(tmp_path)
    items[0]["config"] = config
    return items


def test_a_config_rides_in_the_request_by_its_hash_and_moves_the_plan_s_hash(tmp_path):
    plain = a_plan(tmp_path / "a")
    one = a_plan(tmp_path / "b", items=configured(tmp_path / "b", {"punt_table": 100}))
    two = a_plan(tmp_path / "c", items=configured(tmp_path / "c", {"punt_table": 0}))
    assert "config_sha256" not in plain["request"]["apps"][0] and plain["configs"] == {}
    text = one["configs"]["of_versions"]
    assert text == '{"punt_table":100}\n'
    assert one["request"]["apps"][0]["config_sha256"] == hashlib.sha256(
        text.encode()).hexdigest()
    assert len({plain["plan_sha256"], one["plan_sha256"], two["plan_sha256"]}) == 3


@pytest.mark.parametrize("config, key", [
    ({"password": "hunter2xyz"}, "password"),
    ({"verdict_service": {"api_key": "abcdef123456"}}, "verdict_service.api_key"),
    ({"snmp": {"community": "public"}}, "snmp.community"),
    ({"verdict_service": {"url": "https://u:s3cr3tvalue@192.0.2.5/v1"}}, "verdict_service.url")],
    ids=["password", "api-key", "community", "credential-in-a-url"])
def test_a_config_holding_a_secret_is_refused_naming_the_key_never_the_value(tmp_path, config,
                                                                             key):
    got = channel.plan(network="lab9", controller="ctl", unit=UNIT,
                       enabled=configured(tmp_path, config),
                       host={"show": show("ryu"), "ls": ls("mercury"), "cat": CAT},
                       listen=LISTEN, switches=[eos()], links=[], previous=None)
    assert got["ok"] is False and "request" not in got
    [why] = [r for r in got["refusals"] if "start-time config" in r]
    assert f"key {key} reads as a secret" in why
    for value in ("hunter2xyz", "abcdef123456", "public", "s3cr3tvalue"):
        assert value not in why


def test_a_config_holding_a_value_mercury_holds_as_a_secret_is_refused():
    why = channel.config_secret_refusal("of_versions", "1.0.0", {"note": "x-Planted-Secret-1"},
                                        values={"x-Planted-Secret-1": "secret_planted"})
    assert why and "Planted" not in why


@pytest.mark.parametrize("url", ["http://192.0.2.5:8080/verdict", "http://[2001:db8::5]:8080/v"],
                         ids=("ipv4", "ipv6"))
def test_an_address_in_a_config_is_not_a_secret(url):
    config = {"verdict_service": {"url": url}, "punt_table": 100,
              "dpids": ["000a000000003e01"]}
    assert channel.config_secret_refusal("dns_blacklist", "0.4.0", config, values={}) == ""


def test_a_config_that_is_not_a_json_object_is_refused():
    assert "is a JSON object, not a list" in channel.config_secret_refusal(
        "of_versions", "1.0.0", [1], values={})
