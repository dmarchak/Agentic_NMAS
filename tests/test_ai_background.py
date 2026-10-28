"""Background AI features: off by default per network, on only by an admin who saw the
estimate, each within its own caps (C1843; PHASE8_PLAN 18.3 rules 2 to 5; CLAUDE.md, "AI cost
safety"; `modules/ai/background.py`). A fake feature is registered beside the real one (the SDN
loop's `sdn_classify`, tests/test_sdn_classify.py): the connection check's task, triggered by a
detection, so these tests hold the rules for any feature.

Every call goes through the real gateway, with a real settings file and a real record of AI
calls in the test's own folder; only the provider is fake (a `send` that keeps what it got).

- **Off by default:** a background call for a feature never turned on is refused
  (`feature_off`), recorded, and nothing is sent; on for one network it stays off for another.
- **Turned on** by a verified admin, bound to the estimate they saw (a moved estimate refused
  naming both digests), with positive caps within the installation's day cap; who, when and
  the estimate are written and recorded. Then its calls are sent.
- **Off is one call** and the next call is refused at once (the switch is read at each call).
- **Its caps:** the feature's spend on its network today, or this month, plus the call's worst
  case over its cap is refused (`feature_cap`, naming which cap and both operands), recorded,
  and nothing is sent; another network's spend and a person's spend do not count; the
  installation's day cap still applies first. `set_caps` is how a stopped feature runs again.
- **The estimate:** calls a day from the feature's measured frequency, dollars from the task's
  mean cost per sent call in 30 days, or its per-call cap, said as an upper bound, when none was
  measured; an unmeasured frequency is unknown, never guessed.
"""
import json
import types

import pytest

from modules import config
from modules import installation_settings as I
from modules.ai import background as B
from modules.ai import calls, connection, gateway, profiles, triggers
from modules.ai import anthropic_adapter as A
from tests.registered_networks import register
from tests.test_ai_gateway import KEY, OK_BODY, own_record  # noqa: F401 (fixture)

ADMIN = "admin@example.com"
TASK = "connection_check"


@pytest.fixture
def bg(tmp_path, monkeypatch):
    """A real settings file (hosted AI allowed, a $1.50 day cap), the settings record in the
    test's folder, a key, two networks, the fake feature, and a fake provider."""
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(tmp_path / "user_settings.json"))
    monkeypatch.setattr(I, "_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    # Two networks registered as New network… would (the real resolver answers, C1945: a fake
    # that raised hid that the real one never did).
    register(monkeypatch, tmp_path, "Lab", "Branch")
    from modules.settings_schema import write_settings
    assert write_settings({"ai_hosted": {"by": ADMIN, "at": "2026-10-27T00:00:00Z",
                                         "reason": "the lab's background loop"},
                           "ai_cap_usd_per_day": 1.50})["ok"]
    monkeypatch.setitem(B.FEATURES, "fake_loop", {
        "task": TASK, "words": "The fake loop", "findings": ("detection",),
        "trigger_words": "a detection rule fires", "calls_per_finding": 1,
        "frequency": lambda network: {"per_day": 4.0, "basis": "4 detections a day, planted"}})
    sent = []

    def send(body, key):
        sent.append(body)
        return A.Reply(status=200, body=OK_BODY, attempts=1, latency_s=0.1)
    w = types.SimpleNamespace(sent=sent, send=send, dir=tmp_path)
    return w


def _call(w, network="Lab", job="j1", finding="scan-1"):
    t = triggers.background("fake_loop", job, network, "detection", finding)
    return gateway.ask(TASK, ("ping", 1), connection.Ping, {"word": "w"},
                       actor=triggers.actor_of(t), trigger=t, send=w.send)


def _on(network="Lab", day=0.50, month=10.0, actor=ADMIN):
    est = B.estimate(network, "fake_loop")
    return B.turn_on(network, "fake_loop", day_cap_usd=day, month_cap_usd=month,
                     shown=est["digest"], actor=actor, verified="access")


def _record(w):
    p = w.dir / "settings_record.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def _plant(cost, network="lab", verdict="ok", at=None, **extra):
    """A recorded background call of the fake feature, its cost *cost*."""
    row = {"id": calls.new_id(), "feature": TASK, "actor": "job:j0", "model": "m",
           "verdict": verdict, "cost_usd": cost,
           "trigger": {"kind": "background", "feature": "fake_loop", "job": "j0",
                       "network": network, "finding": {"kind": "detection", "id": "d"}}}
    if at:
        row["at"] = at
    row.update(extra)
    assert calls.record(row)["recorded"]


# ── off by default ────────────────────────────────────────────────────────────────────────────

def test_a_feature_never_turned_on_is_refused_and_nothing_is_sent(bg, monkeypatch):
    # Refused straight after the allowance, before the key is read or a request is built.
    keys = []
    monkeypatch.setattr(gateway, "_api_key", lambda: keys.append(1) or KEY)
    got = _call(bg)
    assert keys == [], "the switch is asked before the key"
    assert got["ok"] is False and got.get("error") == "feature_off" and bg.sent == []
    assert got.get("detail", "") == ("the background feature fake_loop is off for the network lab: an "
                             "admin turns it on in Settings › AI, after its estimate; nothing "
                             "was sent")
    (row,) = calls.read()["rows"]
    assert row["verdict"] == "feature_off" and row["trigger"]["network"] == "lab"
    assert B.switches() == {} and B.enabled() == []


def test_on_for_one_network_it_stays_off_for_another(bg):
    _on("Lab")
    assert _call(bg, "Lab")["ok"] is True and len(bg.sent) == 1
    got = _call(bg, "Branch")
    assert got.get("error") == "feature_off" and "for the network branch" in got.get("detail", "")
    assert len(bg.sent) == 1


# ── turning on ────────────────────────────────────────────────────────────────────────────────

def test_turning_on_writes_and_records_who_when_and_the_estimate_shown(bg):
    est = B.estimate("Lab", "fake_loop")
    got = B.turn_on("Lab", "fake_loop", day_cap_usd=0.5, month_cap_usd=10, shown=est["digest"],
                    actor=ADMIN, verified="access")
    assert got["ok"] is True and got["recorded"] is True
    entry = B.switches()["lab"]["fake_loop"]
    assert entry["on"] is True and entry["by"] == ADMIN and entry["verified"] == "access"
    assert entry["estimate"]["digest"] == est["digest"]
    assert entry["day_cap_usd"] == 0.5 and entry["month_cap_usd"] == 10.0
    (rec,) = _record(bg)
    assert rec["kind"] == "ai_background_on" and rec["actor"] == ADMIN
    assert rec["network"] == "lab" and rec["feature"] == "fake_loop"
    assert rec["estimate"]["digest"] == est["digest"] and rec["day_cap_usd"] == 0.5


def test_an_estimate_that_moved_since_it_was_shown_is_refused_naming_both(bg):
    est = B.estimate("Lab", "fake_loop")
    B.FEATURES["fake_loop"]["frequency"] = lambda n: {"per_day": 40.0, "basis": "more"}
    with pytest.raises(B.Refused) as got:
        B.turn_on("Lab", "fake_loop", day_cap_usd=0.5, month_cap_usd=10, shown=est["digest"],
                  actor=ADMIN, verified="access")
    now = B.estimate("Lab", "fake_loop")["digest"]
    assert str(got.value) == (f"the estimate moved since it was shown (shown "
                              f"{est['digest'][:12]}, now {now[:12]}): look at it again and "
                              "accept it; nothing was changed")
    assert B.switches() == {} and _record(bg) == []


@pytest.mark.parametrize("day,month,said", [
    (0, 10, "the day cap 0 is not a positive amount"),
    (-1, 10, "the day cap -1 is not a positive amount"),
    (0.5, 0, "the month cap 0 is not a positive amount"),
    (True, 10, "the day cap True is not a positive amount"),
    ("1", 10, "the day cap '1' is not a positive amount"),
    (2.0, 10, "the feature's day cap $2.0000 is over the installation's day cap $1.5000"),
])
def test_caps_must_be_positive_and_within_the_installations_day_cap(bg, day, month, said):
    with pytest.raises(B.Refused) as got:
        _on(day=day, month=month)
    assert said in str(got.value) and B.switches() == {}


@pytest.mark.parametrize("actor", ["", "unverified", None])
def test_only_a_verified_admin_turns_a_feature_on(bg, actor):
    with pytest.raises(B.Refused) as got:
        _on(actor=actor)
    assert "a background feature is changed by a verified admin" in str(got.value)


def test_an_unknown_feature_or_network_is_refused(bg):
    with pytest.raises(B.Refused, match="'nope' is not a background feature Mercury knows"):
        B.estimate("Lab", "nope")
    with pytest.raises(B.Refused, match="'Nowhere' is not a network Mercury holds"):
        B.estimate("Nowhere", "fake_loop")


def test_a_background_call_for_a_network_mercury_does_not_hold_is_refused_naming_it(bg):
    # C1945: a switch stored ON for a name no network answers to, so the switch alone would
    # admit it: the refusal is the network's, naming the name and the networks compared with.
    on = {"on": True, "at": B._iso(B._now()), "day_cap_usd": 0.5, "month_cap_usd": 10.0}
    _store_switches({"nowhere": {"fake_loop": on}})
    got = _call(bg, network="nowhere")
    assert got.get("error") == "feature_off" and bg.sent == []
    assert got.get("detail", "").startswith(
        "'nowhere' is not a network Mercury holds (no network answers to 'nowhere': the "
        "registered networks are ")
    assert "Branch" in got["detail"] and "Lab" in got["detail"]
    assert got["detail"].endswith("; nothing was sent")


def test_a_background_call_naming_another_spelling_of_a_network_is_refused_naming_its_id(
        bg, monkeypatch):
    # A registry whose folder name is not its id's spelling: the trigger names the folder,
    # the switch stored ON under it, and the call is refused naming both (C1945).
    reg = bg.dir / "device_lists_spelling.json"
    reg.write_text(json.dumps({"current_list": "Lab", "lists": {"Lab": "lab_old"}}))
    monkeypatch.setattr("modules.device.DEVICE_LISTS_CONFIG", str(reg))
    on = {"on": True, "at": B._iso(B._now()), "day_cap_usd": 0.5, "month_cap_usd": 10.0}
    _store_switches({"lab_old": {"fake_loop": on}})
    got = _call(bg, network="lab_old")
    assert got.get("error") == "feature_off" and bg.sent == []
    assert got.get("detail", "") == ("a background trigger names its network by its id: "
                                     "'lab_old' is not, the network's id is 'lab'; nothing "
                                     "was sent")


# ── off is one call ───────────────────────────────────────────────────────────────────────────

def test_off_stops_the_next_call_at_once_and_is_recorded(bg):
    _on()
    assert _call(bg)["ok"] is True
    got = B.turn_off("Lab", "fake_loop", actor=ADMIN, verified="access")
    assert got["ok"] is True and got["nothing"] is False
    assert _call(bg).get("error") == "feature_off" and len(bg.sent) == 1
    assert [r["kind"] for r in _record(bg)] == ["ai_background_on", "ai_background_off"]
    assert B.turn_off("Lab", "fake_loop", actor=ADMIN, verified="access")["nothing"] is True


def test_a_switch_turned_off_between_admit_and_the_caps_is_refused_off(bg, monkeypatch):
    _on()
    real = B.over_cap

    def off_first(trigger, worst, day, reserved=None):
        B.turn_off("Lab", "fake_loop", actor=ADMIN, verified="access")
        return real(trigger, worst, day, reserved)
    monkeypatch.setattr(B, "over_cap", off_first)
    got = _call(bg)
    assert got.get("error") == "feature_off" and bg.sent == []


# ── its caps ──────────────────────────────────────────────────────────────────────────────────

def test_the_features_day_cap_stops_it_naming_both_operands(bg):
    _on(day=0.50, month=10.0)
    _plant(0.499999)
    got = _call(bg)
    assert got["ok"] is False and got.get("error") == "feature_cap" and bg.sent == []
    assert ("fake_loop's spend on lab today $0.5000 plus $0.0000 reserved by its 0 call(s) in "
            "flight plus this call's worst case $") in got.get("detail", "")
    assert "is over its day cap $0.5000; it stops until the day ends or an admin raises the " \
           "cap; nothing was sent" in got.get("detail", "")
    row = calls.read()["rows"][0]
    assert row["verdict"] == "feature_cap" and row["cap_kind"] == "day"


def test_the_features_month_cap_stops_it(bg):
    _on(day=0.50, month=1.00)
    # Earlier this month (the cap's day is UTC by default), so today's spend is nothing.
    first = calls.today()[:8] + "01"
    if first == calls.today():
        pytest.skip("the month's first day has no earlier day to plant on")
    _plant(0.999999, at=f"{first}T00:30:00Z")
    got = _call(bg)
    assert got.get("error") == "feature_cap" and "is over its month cap $1.0000" in got.get("detail", "")
    assert calls.read()["rows"][0]["cap_kind"] == "month"


def test_another_networks_spend_and_a_persons_do_not_count(bg):
    _on(day=0.50)
    _plant(0.499999, network="branch")
    calls.record({"id": calls.new_id(), "feature": TASK, "actor": "a@example.com",
                  "verdict": "ok", "cost_usd": 0.49,
                  "trigger": {"kind": "person", "by": "a@example.com"}})
    assert _call(bg)["ok"] is True and len(bg.sent) == 1


def test_the_installations_day_cap_still_comes_first(bg):
    _on(day=1.0, month=10.0)
    calls.record({"id": calls.new_id(), "feature": TASK, "actor": "a@example.com",
                  "verdict": "ok", "cost_usd": 1.499999})
    got = _call(bg)
    assert got.get("error") == "over_cap" and "is over the day cap $1.5000" in got.get("detail", "")


def test_raising_the_cap_is_how_a_stopped_feature_runs_again(bg):
    _on(day=0.50)
    _plant(0.499999)
    assert _call(bg).get("error") == "feature_cap"
    got = B.set_caps("Lab", "fake_loop", day_cap_usd=1.0, month_cap_usd=10.0, actor=ADMIN,
                     verified="access")
    assert got["ok"] and got["before"] == {"day_cap_usd": 0.5, "month_cap_usd": 10.0}
    assert _call(bg)["ok"] is True
    assert _record(bg)[-1]["kind"] == "ai_background_caps"


def test_set_caps_is_refused_for_a_feature_that_is_off(bg):
    with pytest.raises(B.Refused, match="fake_loop is off for lab: turning it on sets its caps"):
        B.set_caps("Lab", "fake_loop", day_cap_usd=1, month_cap_usd=2, actor=ADMIN,
                   verified="access")


def test_a_cap_out_of_shape_in_the_file_is_refused_never_read_as_no_cap(bg):
    _on()
    every = B.switches()
    every["lab"]["fake_loop"]["day_cap_usd"] = "lots"
    with open(config.USER_SETTINGS_FILE) as fh:
        stored = json.load(fh)
    stored["ai_background"] = every
    with open(config.USER_SETTINGS_FILE, "w") as fh:
        json.dump(stored, fh)
    got = _call(bg)
    assert got.get("error") == "feature_cap" and bg.sent == []
    assert got.get("detail", "") == "fake_loop on lab has no valid day cap stored ('lots'); nothing " \
                            "was sent"


def test_an_unreadable_record_refuses_the_feature(bg, monkeypatch):
    _on()
    from modules.ai import spend
    monkeypatch.setattr(spend, "feature_spent", lambda *a, **k: {"state": "unreadable",
                                                                 "error": "a torn line"})
    got = _call(bg)
    assert got.get("error") == "feature_cap" and "a torn line" in got.get("detail", "") and bg.sent == []


# ── the estimate ──────────────────────────────────────────────────────────────────────────────

def test_with_no_measured_call_the_estimate_uses_the_worst_case_and_says_so(bg):
    est = B.estimate("Lab", "fake_loop")
    worst = profiles.cap_per_call(TASK)
    assert est["label"] == "an estimate, not a measurement of this feature's spend"
    assert est["cost"]["measured"] is False and est["cost"]["usd_per_call"] == worst
    assert "its per-call cap, the most one call can cost, is used, so this is an upper bound" \
        in est["cost"]["basis"]
    assert est["calls_per_day"] == 4.0
    assert est["usd_per_day"] == pytest.approx(4.0 * worst)
    assert est["usd_per_month"] == pytest.approx(4.0 * worst * 30)


def test_the_measured_cost_is_the_mean_of_the_tasks_sent_calls_on_its_model(bg):
    model = profiles.TASKS[TASK]["model"]
    for cost in (0.001, 0.003):
        calls.record({"id": calls.new_id(), "feature": TASK, "model": model, "actor": "a",
                      "verdict": "ok", "cost_usd": cost, "tokens": {"input_tokens": 1}})
    calls.record({"id": calls.new_id(), "feature": TASK, "model": model, "actor": "a",
                  "verdict": "over_cap", "cost_usd": 0.0})            # never sent: not counted
    calls.record({"id": calls.new_id(), "feature": TASK, "model": "another", "actor": "a",
                  "verdict": "ok", "cost_usd": 9.0, "tokens": {"input_tokens": 1}})
    est = B.estimate("Lab", "fake_loop")
    assert est["cost"]["measured"] is True and est["cost"]["calls"] == 2
    assert est["cost"]["usd_per_call"] == pytest.approx(0.002)
    assert est["usd_per_day"] == pytest.approx(0.008)
    assert est["suggested"] == {"day_cap_usd": 0.02, "month_cap_usd": 0.6}


def test_an_unmeasured_frequency_is_unknown_never_guessed(bg):
    B.FEATURES["fake_loop"]["frequency"] = lambda n: {"per_day": None, "basis": "never fired"}
    est = B.estimate("Lab", "fake_loop")
    assert est["calls_per_day"] is None and est["usd_per_day"] is None
    assert est["usd_per_month"] is None and est["suggested"] is None
    assert est["frequency"] == {"per_day": None, "basis": "never fired"}


def test_a_frequency_that_fails_is_said(bg):
    def boom(n):
        raise RuntimeError("no detections store")
    B.FEATURES["fake_loop"]["frequency"] = boom
    est = B.estimate("Lab", "fake_loop")
    assert est["calls_per_day"] is None
    assert est["frequency"]["basis"] == ("its frequency could not be measured (RuntimeError: "
                                         "no detections store)")


# ── the tier hand check's survivors (C1843) ──────────────────────────────────────────────────

def _store_switches(every):
    with open(config.USER_SETTINGS_FILE) as fh:
        stored = json.load(fh)
    stored["ai_background"] = every
    with open(config.USER_SETTINGS_FILE, "w") as fh:
        json.dump(stored, fh)


def test_the_features_caps_count_on_the_calls_own_day_and_record_its_worst_case(bg):
    # The feature's caps are judged on the day the gateway counts (its *today*), never the
    # clock's; the refusal's row keeps the call's worst case, as the day cap's does.
    _on(day=0.50, month=10.0)
    _plant(0.499999, at="2026-01-15T00:30:00Z")
    t = triggers.background("fake_loop", "j1", "Lab", "detection", "scan-1")
    got = gateway.ask(TASK, ("ping", 1), connection.Ping, {"word": "w"},
                      actor=triggers.actor_of(t), trigger=t, send=bg.send, today="2026-01-15")
    assert got.get("error") == "feature_cap" and bg.sent == []
    assert "fake_loop's spend on lab today $0.5000" in got.get("detail", "")
    row = calls.read()["rows"][0]
    assert isinstance(row.get("worst_usd"), float) and row["worst_usd"] > 0
    assert f"this call's worst case ${row['worst_usd']:.4f}" in got["detail"]


def test_a_background_call_naming_no_network_names_none_and_is_refused(bg):
    # Never Default's network (list_slug("") is "default"), and the refusal names what came.
    assert triggers.background("fake_loop", "j1", "", "detection", "scan-1")["network"] == ""
    _on()
    got = _call(bg, network="")
    assert got.get("error") == "trigger" and bg.sent == []
    assert "a background trigger names its network by its folder name; '' is not one" \
        in got.get("detail", "")


@pytest.mark.parametrize("entry", [{"on": False}, {"on": "true"}, {"on": 1}, {}],
                         ids=["off", "on-as-text", "on-as-one", "no-on"])
def test_a_switch_stored_anything_but_on_true_admits_nothing(bg, entry):
    _store_switches({"lab": {"fake_loop": dict(entry, day_cap_usd=0.5, month_cap_usd=10.0)}})
    got = _call(bg)
    assert got.get("error") == "feature_off" and bg.sent == []
    assert B.entry_of("lab", "fake_loop") is None


def test_the_switches_on_are_listed_by_network_then_feature(bg, monkeypatch):
    monkeypatch.setitem(B.FEATURES, "fake_digest", dict(B.FEATURES["fake_loop"]))
    # Turned on now: an approval lasts 14 days from its `at` (B.APPROVAL_DAYS), and a switch
    # with no `at` is never in force.
    on = {"on": True, "at": B._iso(B._now()), "day_cap_usd": 0.5, "month_cap_usd": 10.0}
    _store_switches({"lab": {"fake_loop": on, "fake_digest": on},
                     "branch": {"fake_loop": on, "fake_digest": dict(on, on=False)}})
    assert [(n, f) for n, f, _e in B.enabled()] == [
        ("branch", "fake_loop"), ("lab", "fake_digest"), ("lab", "fake_loop")]


def test_switches_that_cannot_be_read_are_said_and_refused(bg, monkeypatch):
    def torn():
        raise OSError("the settings file is torn")
    monkeypatch.setattr(B, "switches", torn)
    got = _call(bg)
    assert got.get("error") == "feature_off" and bg.sent == []
    assert got.get("detail", "") == ("the background switches cannot be read (OSError: the "
                                     "settings file is torn), so whether fake_loop is on is "
                                     "unknown; nothing was sent")


def test_a_switch_turned_off_mid_call_says_admits_words_and_names_no_cap(bg, monkeypatch):
    # Turned off between `admit` and the caps: the refusal is admit's own (where an admin turns
    # it on), and its row names no cap, since no cap stopped it.
    _on()
    real = B.over_cap

    def off_first(trigger, worst, day, reserved=None):
        B.turn_off("Lab", "fake_loop", actor=ADMIN, verified="access")
        return real(trigger, worst, day, reserved)
    monkeypatch.setattr(B, "over_cap", off_first)
    got = _call(bg)
    assert got.get("detail", "") == ("the background feature fake_loop is off for the network "
                                     "lab: an admin turns it on in Settings › AI, after its "
                                     "estimate; nothing was sent")
    row = calls.read()["rows"][0]
    assert row["verdict"] == "feature_off" and row["cap_kind"] == ""


def test_an_unreadable_record_stops_the_feature_on_its_day_cap(bg, monkeypatch):
    # The refusal's row says which cap it counts against ("day" or "month", as every
    # feature_cap row does): an unknown spend stops the feature for the day.
    _on()
    from modules.ai import spend
    monkeypatch.setattr(spend, "feature_spent", lambda *a, **k: {"state": "unreadable",
                                                                 "error": "a torn line"})
    got = _call(bg)
    assert got.get("error") == "feature_cap" and bg.sent == []
    assert calls.read()["rows"][0]["cap_kind"] == "day"


def test_a_call_that_brings_the_spend_exactly_to_the_cap_is_sent(bg, monkeypatch):
    # The cap is what may be spent: spend plus the worst case AT the cap fits. Binary fractions
    # (a quarter, and 2**-12 as the worst case, under the task's per-call cap) keep the sum exact.
    worst = 2.0 ** -12
    assert worst <= profiles.cap_per_call(TASK)
    monkeypatch.setattr(gateway, "worst_case_usd", lambda model, body, tokens=None: worst)
    _on(day=0.25 + worst, month=10.0)
    _plant(0.25)
    got = _call(bg)
    assert got["ok"] is True and len(bg.sent) == 1, got


def test_the_month_caps_refusal_names_this_month(bg):
    _on(day=0.50, month=1.00)
    _plant(0.999999, at="2026-01-03T00:30:00Z")
    t = triggers.background("fake_loop", "j1", "Lab", "detection", "scan-1")
    got = gateway.ask(TASK, ("ping", 1), connection.Ping, {"word": "w"},
                      actor=triggers.actor_of(t), trigger=t, send=bg.send, today="2026-01-15")
    assert got.get("error") == "feature_cap" and bg.sent == []
    assert ("fake_loop's spend on lab this month $1.0000 plus $0.0000 reserved by its 0 "
            "call(s) in flight plus this call's worst case $") \
        in got.get("detail", ""), got
    assert "is over its month cap $1.0000; it stops until the month ends" in got["detail"]
