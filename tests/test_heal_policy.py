"""Heal to intent's policy, its mode and the kill switch (`modules/heal/policy.py`,
`routes/heal_v2.py`; board H, part H1, docs/HEAL_TO_INTENT.md sections 6, 7, 9 and 18), no
network, no device, a fake clock.

- **The defaults heal nothing:** off everywhere, never AUTO, the kill switch not stopped; the
  kinds' tiers in code equal the schema's.
- **Each network's own:** a policy confirmed on Default leaves an inheriting network off.
- **A change is previewed and confirmed by hash as a verified person with a reason:** the
  six parts, the fingerprint, a confirm refused when the policy moved (naming both
  fingerprints and the value), without a person or a reason, or with a kind above its tier.
- **C2009's guard and AUTO's limits (N8):** AUTO only on a network marked lab, at most 7 days,
  naming at least one Tier 1 kind, one more at a time; past its expiry dry run, recorded once;
  marked off lab since, dry run and suspended.
- **Fails closed:** values a person did not confirm are not in force; an unreadable policy is
  off and refuses writes; an unreadable kill switch is stopped.
- **Turn off:** one press, no confirm, at once, recorded with who and when.
- **The kill switch:** stops every network at once, recorded with who, when and why; resuming
  is previewed and confirmed by hash as a verified person with a reason.
- **Lab defaults (N1, N3):** the grace period and the topology hold read their lab values on a
  network marked lab that sets none.
"""
import json
import os

import pytest

from modules.sdn import modes as MD
from tests.test_sdn_connections import networks  # the fixture, named by each test below


class _Policy:
    """`modules.heal.policy`, imported when a test first names it, so the file collects on a
    tree without it and each test is red there on its own (scripts/nmas-red-green)."""

    def __getattr__(self, name):
        from modules.heal import policy

        return getattr(policy, name)


H = _Policy()
T0 = 1_790_000_000.0
PERSON = {"actor": "admin@example.com", "actor_verified": "access", "person": True}


def iso(epoch):
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def mark(network="Default", value="lab"):
    return MD.set_stage(network, value, actor="admin@example.com", actor_verified="access",
                        reason="the course lab's network")


def confirm(network="Default", now=T0, reason="Lab 10's dry run", **proposed):
    """Preview *proposed* on *network*, then confirm it by the preview's fingerprint."""
    p = H.plan(network, proposed, now)
    return H.apply(network, proposed, p["fingerprint"], reason=reason, now=now, **PERSON)


def auto(network="Default", now=T0, hours=1, kinds=("added_line",)):
    return confirm(network, now, heal_mode="auto", heal_mode_until=iso(now + hours * 3600),
                   heal_kinds_auto=list(kinds))


def record(network="Default", kinds=None):
    from modules.config import list_data_path

    kinds = H.RECORD_KINDS if kinds is None else kinds
    path = os.path.join(list_data_path(network), "settings_record.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [r for r in (json.loads(x) for x in fh if x.strip()) if r.get("kind") in kinds]


def install_record():
    from modules import installation_settings as I

    return list(reversed(I.changes(kinds=H.INSTALL_RECORD_KINDS)["rows"]))


def tear(network="Branch"):
    from modules import list_settings as L

    path = L.path(network)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{torn")


# ── The defaults and the declarations ─────────────────────────────────────────────────────────

def test_the_defaults_heal_nothing_anywhere(networks):
    from modules.settings_schema import DEFAULTS

    assert (DEFAULTS["heal_mode"], DEFAULTS["heal_kinds_auto"], DEFAULTS["heal_stopped"]) == \
        ("off", [], False)
    for name in ("Default", "Branch", "Lab-3"):
        got = H.current(name, T0)
        assert got["mode"] == "off", name
        assert got["words"] == f"off: self-healing is off for {name}"


def test_the_kinds_tiers_in_code_are_the_schemas():
    from modules.settings_schema import DEFAULTS, SCHEMA

    props = SCHEMA["properties"]
    assert tuple(props["heal_kinds_auto"]["items"]["enum"]) == H.TIER1_KINDS
    assert tuple(props["heal_kinds_propose"]["items"]["enum"]) == H.TIER2_KINDS
    # Every Tier 2 heal kind is proposed by default; no action kind is (H21: the session
    # clear is Tier 2 off a lab network, and no policy names it by default).
    from modules.heal.actions import KINDS as ACTIONS
    assert DEFAULTS["heal_kinds_propose"] == [k for k in H.TIER2_KINDS if k not in ACTIONS]
    assert "session_clear" in H.TIER2_KINDS and "session_clear" in H.TIER1_KINDS
    assert not set(ACTIONS) & set(DEFAULTS["heal_kinds_propose"] + DEFAULTS["heal_kinds_auto"])


def test_the_guards_are_section_6s_in_order_and_each_setting_named_once():
    from modules.settings_scope import SCOPES

    assert [g[0] for g in H.GUARDS] == list(range(1, 15))
    named = [k for _n, _w, keys in H.GUARDS for k in keys]
    assert sorted(named) == sorted(set(named))
    assert set(H.GUARD_KEYS) | {H.KINDS_AUTO_KEY, H.KINDS_PROPOSE_KEY} <= set(named)
    assert {k for k, (_s, g) in SCOPES.items() if g == H.GROUP} == \
        set(H.POLICY_KEYS) | {H.CONFIRMED_KEY}
    assert SCOPES[H.KILL_KEY][0] == "host"


def test_the_policy_is_each_networks_own_and_never_inherited(networks):
    from modules.settings_scope import CARDLESS, OWN_ONLY

    assert H.GROUP in OWN_ONLY and H.GROUP in CARDLESS
    confirm("Default", heal_mode="dry_run")
    assert H.current("Default", T0)["mode"] == "dry_run"
    # Branch inherits from Default (no mode of its own), and still heals nothing.
    branch = H.current("Branch", T0)
    assert branch["mode"] == "off" and branch["set"] == "off"


# ── A change: previewed, confirmed by hash, as a verified person ─────────────────────────────

def test_a_confirmed_change_is_in_force_and_recorded_with_who_and_why(networks):
    out = confirm("Default", heal_mode="dry_run", heal_max_per_network_hour=4)
    got = H.current("Default", T0)
    assert got["mode"] == "dry_run" and got["guards"]["heal_max_per_network_hour"] == \
        {"value": 4, "source": "set", "words": "heals per network an hour: 4"}
    assert got["confirmed"]["by"] == "admin@example.com"
    assert got["confirmed"]["fingerprint"] == out["policy_fingerprint"] == got["fingerprint"]
    [row] = record()
    assert (row["kind"], row["actor"], row["reason"], row["mode"]) == \
        ("heal_policy", "admin@example.com", "Lab 10's dry run", "dry_run")
    assert ["heal_mode", "off", "dry_run"] in row["changes"]
    assert ["heal_max_per_network_hour", 6, 4] in row["changes"]


def test_a_confirm_after_the_policy_moved_is_refused_naming_both(networks):
    stale = H.plan("Default", {"heal_mode": "dry_run"}, T0)
    confirm("Default", heal_max_per_device_hour=0)
    with pytest.raises(H.PolicyRefused) as exc:
        H.apply("Default", {"heal_mode": "dry_run"}, stale["fingerprint"], reason="r",
                now=T0, seen=stale["operands"], **PERSON)
    words = str(exc.value)
    assert words.startswith(f"Default's heal policy moved since the preview (confirmed "
                            f"{stale['fingerprint']}, now ")
    assert "heal_max_per_device_hour (before): previewed 1, now 0" in words
    assert H.current("Default", T0)["set"] == "off"


@pytest.mark.parametrize("who,reason,words", [
    ({"actor": "", "actor_verified": "access", "person": True}, "r", "verified person"),
    ({"actor": "svc", "actor_verified": "none", "person": True}, "r", "verified none"),
    ({"actor": "svc", "actor_verified": "access", "person": False}, "r", "verified person"),
    (PERSON, "  ", "with a recorded reason, and none was given"),
], ids=["no-actor", "unverified", "a-service", "no-reason"])
def test_a_confirm_needs_a_verified_person_and_a_reason(networks, who, reason, words):
    p = H.plan("Default", {"heal_mode": "dry_run"}, T0)
    with pytest.raises(H.PolicyRefused) as exc:
        H.apply("Default", {"heal_mode": "dry_run"}, p["fingerprint"], reason=reason, now=T0,
                **who)
    assert words in str(exc.value)
    assert H.current("Default", T0)["set"] == "off" and record() == []


@pytest.mark.parametrize("proposed,words", [
    ({"heal_kinds_auto": ["process_reset"]}, "heal_kinds_auto names Tier 1 kinds only"),
    ({"heal_kinds_propose": ["missing_line"]}, "heal_kinds_propose names Tier 2 kinds only"),
    ({"heal_mode": "on"}, "the mode is off, dry_run, auto, not 'on'"),
    ({"heal_grace_seconds": 5}, "not a heal policy: heal_grace_seconds"),
    ({"heal_max_removed_units": 2}, "not a heal policy: heal_max_removed_units"),
    ({"network_stage": "lab"}, "network_stage is not part of a heal policy"),
], ids=["tier-2-auto", "tier-1-proposed", "unknown-mode", "grace-too-short",
        "two-removals", "not-a-policy-key"])
def test_a_value_outside_the_policy_is_refused_naming_it(networks, proposed, words):
    with pytest.raises(H.PolicyRefused) as exc:
        H.plan("Default", proposed, T0)
    assert words in str(exc.value)


def test_the_preview_has_its_six_parts_and_binds_its_fingerprint(networks):
    from modules import preview_confirm as PC

    p = H.plan("Default", {"heal_mode": "dry_run"}, T0)
    pv = PC.heal_policy_preview(p, {"statement": "You are confirming as admin@example.com."})
    assert pv["parts"] == list(PC.PARTS)
    assert pv["what"]["summary"] == "Default's self-healing policy: dry run; 1 value(s) change"
    assert pv["what"]["targets"][0]["select_data"]["fingerprint"] == p["fingerprint"]
    assert pv["targets"][0]["program"]["lines"] == ["heal_mode: off -> dry run"]
    assert any(i["text"] == "Nothing is sent to any device by this change"
               for i in pv["what_not"]["items"])
    nothing = H.plan("Default", {"heal_mode": "off"}, T0)
    assert not nothing["confirmable"]
    pv = PC.heal_policy_preview(nothing, {"statement": "s"})
    assert pv["what"]["targets"][0]["why_not"] == ("something to confirm: the policy would "
                                                   "be what it is now")


# ── C2009's guard and AUTO's limits ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("stage,words", [
    ("", "Default is not marked"), ("pilot", "Default is marked pilot"),
    ("production", "Default is marked production")], ids=["not-marked", "pilot", "production"])
def test_auto_is_refused_on_a_network_not_marked_lab(networks, stage, words):
    if stage:
        mark("Default", stage)
    with pytest.raises(H.PolicyRefused) as exc:
        auto("Default")
    assert str(exc.value) == (f"not saved: AUTO only on a network marked lab (C2009): "
                              f"{MD.GATE_WORDS}; {words}")
    assert H.current("Default", T0)["set"] == "off"


def test_auto_on_a_lab_network_runs_until_its_expiry_then_dry_run_once(networks):
    mark()
    auto(hours=2)
    assert H.current("Default", T0 + 60)["mode"] == "auto"
    late = H.current("Default", T0 + 2 * 3600)
    assert (late["mode"], late["expired"]) == ("dry_run", True)
    assert late["words"].startswith("dry run: AUTO by admin@example.com expired ")
    assert H.record_expiry("Default", T0 + 2 * 3600) == {"recorded": True}
    assert H.record_expiry("Default", T0 + 3 * 3600) == {"recorded": False}
    assert [r["kind"] for r in record()] == ["heal_policy", "heal_auto_expired"]


@pytest.mark.parametrize("until,words", [
    ("", "AUTO is set with an expiry (at most 7 days; it then returns to dry run), and none "
         "was given"),
    (iso(T0 - 1), "AUTO's expiry is in the future"),
    (iso(T0 + 7 * 86400 + 60), "AUTO may be on for at most 7 days (N8)"),
    ("tomorrow", "AUTO's expiry is a UTC time, YYYY-MM-DDTHH:MM:SSZ, not 'tomorrow'"),
], ids=["none", "past", "past-7-days", "not-a-time"])
def test_autos_expiry_is_required_and_at_most_7_days(networks, until, words):
    mark()
    with pytest.raises(H.PolicyRefused) as exc:
        H.plan("Default", {"heal_mode": "auto", "heal_mode_until": until,
                           "heal_kinds_auto": ["added_line"]}, T0)
    assert str(exc.value).startswith(words)


def test_auto_is_suspended_to_dry_run_once_the_stage_moves_off_lab(networks):
    mark()
    auto()
    mark("Default", "production")
    got = H.current("Default", T0 + 60)
    assert got["mode"] == "dry_run"
    assert got["words"] == (f"dry run: AUTO is set and suspended, since {MD.GATE_WORDS}; "
                            "Default is marked production")
    mark()
    assert H.current("Default", T0 + 60)["mode"] == "auto"


def test_auto_names_a_tier_1_kind_and_allows_one_more_at_a_time(networks):
    mark()
    none = H.plan("Default", {"heal_mode": "auto", "heal_mode_until": iso(T0 + 3600),
                              "heal_kinds_auto": []}, T0)
    assert not none["confirmable"]
    two = H.plan("Default", {"heal_mode": "auto", "heal_mode_until": iso(T0 + 3600),
                             "heal_kinds_auto": ["added_line", "missing_line"]}, T0)
    [gate] = [g for g in two["gates"] if g["state"] == "fail"]
    assert gate["name"] == "Tier 1 kinds allowed AUTO one at a time (N8)"
    auto(kinds=("added_line",))
    more = H.plan("Default", {"heal_kinds_auto": ["added_line", "missing_line"]}, T0)
    assert more["confirmable"]


# ── Fails closed ──────────────────────────────────────────────────────────────────────────────

def test_values_nobody_confirmed_are_not_in_force(networks):
    from modules import list_settings as L

    # A hand edit of the mode, with no confirmation held: off.
    L.write("Branch", {"heal_mode": "dry_run"})
    got = H.current("Branch", T0)
    assert got["mode"] == "off" and "no confirmation is held" in got["words"]
    # A confirmed policy whose values were edited since: off, naming both fingerprints.
    confirm("Default", heal_mode="dry_run")
    held = H.current("Default", T0)["confirmed"]["fingerprint"]
    L.write("Default", {"heal_max_per_device_hour": 5})
    got = H.current("Default", T0)
    assert got["mode"] == "off"
    assert f"(confirmed {held}, now {got['fingerprint']})" in got["words"]


def test_an_unreadable_policy_is_off_and_refuses_every_write(networks):
    tear("Branch")
    got = H.current("Branch", T0)
    assert (got["mode"], got["state"]) == ("off", "unreadable")
    with pytest.raises(H.PolicyRefused) as exc:
        H.plan("Branch", {"heal_mode": "dry_run"}, T0)
    assert "nothing can be previewed or saved until it can" in str(exc.value)
    off = H.turn_off("Branch", actor="op@example.com")
    assert off["nothing"] and off["words"].startswith("Nothing written: Branch's heal policy "
                                                      "cannot be read")


def test_an_unreadable_kill_switch_is_stopped(networks):
    from modules import config

    confirm("Branch", heal_mode="dry_run")
    assert H.current("Branch", T0)["mode"] == "dry_run"
    with open(config.USER_SETTINGS_FILE, "w", encoding="utf-8") as fh:
        fh.write("{torn")
    got = H.stopped()
    assert (got["stopped"], got["state"]) == (True, "unreadable")
    assert H.current("Branch", T0)["mode"] == "off"


# ── Turn off ──────────────────────────────────────────────────────────────────────────────────

def test_turn_off_is_one_press_at_once_and_recorded(networks):
    confirm("Default", heal_mode="dry_run")
    out = H.turn_off("Default", actor="op@example.com", actor_verified="access", now=T0)
    assert out["words"] == ("Self-healing turned off for Default by op@example.com (was dry "
                            f"run): {H.OFF_EFFECT}")
    assert H.current("Default", T0)["mode"] == "off"
    assert [(r["kind"], r["actor"], r.get("before")) for r in record()][-1] == \
        ("heal_off", "op@example.com", "dry_run")
    again = H.turn_off("Default", actor="op@example.com")
    assert again["nothing"] and again["words"] == "Self-healing is already off for Default"
    # Turning it back on is a change: previewed and confirmed by hash again.
    back = H.plan("Default", {"heal_mode": "dry_run"}, T0)
    assert back["changes"] == [["heal_mode", "off", "dry_run"]] and back["confirmable"]


# ── The kill switch ───────────────────────────────────────────────────────────────────────────

def test_the_kill_switch_stops_every_network_recorded_with_who_when_why(networks):
    confirm("Default", heal_mode="dry_run")
    confirm("Branch", heal_mode="dry_run")
    out = H.stop(actor="op@example.com", actor_verified="access", why="a bad rollout")
    assert not out["nothing"] and out["recorded"]
    for name in ("Default", "Branch"):
        got = H.current(name, T0)
        assert got["mode"] == "off" and got["words"].startswith(
            "off: self-healing is stopped everywhere by op@example.com")
        assert got["words"].endswith(": a bad rollout")
    [row] = install_record()
    assert (row["kind"], row["actor"], row["why"]) == ("heal_stopped", "op@example.com",
                                                       "a bad rollout")
    assert H.stop(actor="op@example.com")["nothing"]


def test_resuming_is_previewed_and_confirmed_by_hash_as_a_person(networks):
    confirm("Default", heal_mode="dry_run")
    with pytest.raises(H.PolicyRefused):
        H.resume_plan()
    H.stop(actor="op@example.com")
    p = H.resume_plan(T0)
    assert [(r["network"], r["mode"]) for r in p["networks"]][:2] == \
        [("Default", "dry_run"), ("Branch", "off")]
    with pytest.raises(H.NotAPerson):
        H.resume(p["fingerprint"], reason="fixed", actor="svc", actor_verified="access",
                 person=False)
    with pytest.raises(H.PolicyRefused) as exc:
        H.resume("0" * 16, reason="fixed", **PERSON)
    assert "moved since the preview (confirmed 0000000000000000, now " in str(exc.value)
    assert H.stopped()["stopped"]
    H.resume(p["fingerprint"], reason="the rollout was rolled back", **PERSON)
    assert not H.stopped()["stopped"] and H.current("Default", T0)["mode"] == "dry_run"
    assert [r["kind"] for r in install_record()] == ["heal_stopped", "heal_resumed"]


# ── Lab defaults (N1, N3) ─────────────────────────────────────────────────────────────────────

def test_the_grace_and_topology_hold_read_their_lab_defaults_on_a_lab(networks):
    prod = H.current("Default", T0)["guards"]
    assert (prod["heal_grace_seconds"]["value"], prod["heal_topology_hold_minutes"]["value"]) \
        == (900, 240)
    mark()
    lab = H.current("Default", T0)["guards"]
    assert lab["heal_grace_seconds"] == {
        "value": 120, "source": "lab default",
        "words": ("a deviation must persist for (seconds): 120 (lab default; 900 on a "
                  "network not marked lab)")}
    assert lab["heal_topology_hold_minutes"]["value"] == 60
    confirm("Default", heal_grace_seconds=300)
    assert H.current("Default", T0)["guards"]["heal_grace_seconds"]["source"] == "set"


# ── The routes ────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(networks, monkeypatch):
    """The routes on a test app of their own: `routes/heal_v2.py`'s blueprint is registered
    on the real app only by H9, with the Self-healing tab that posts it. The app's gate and
    invalidation hooks are installed as `routes.register_blueprints` installs them, with the
    blueprint's own declarations (`heal_v2.gates`, `heal_v2.invalidates`) in their tables."""
    from flask import Flask

    from modules import invalidation, route_gates
    from routes import heal_v2

    monkeypatch.setattr(route_gates, "GATES", dict(route_gates.GATES, **heal_v2.gates()))
    monkeypatch.setattr(invalidation, "DECLARED",
                        dict(invalidation.DECLARED, **heal_v2.invalidates()))
    app = Flask(__name__)
    app.register_blueprint(heal_v2.bp)
    route_gates.install(app)
    invalidation.install(app)
    return app.test_client()


def test_the_routes_preview_confirm_turn_off_stop_and_resume(client):
    from tests.conftest import TEST_PERSON

    base = "/v2/settings/network/Default/heal"
    r = client.post(base + "/preview", data={"heal_mode": "dry_run"})
    body = r.get_json()
    assert r.status_code == 200 and body["confirmable"]
    assert body["preview"]["what"]["targets"][0]["select_data"]["fingerprint"] == \
        body["fingerprint"]
    r = client.post(base, data={"heal_mode": "dry_run", "fingerprint": body["fingerprint"],
                                "reason": "Lab 10", "seen": json.dumps(body["operands"])})
    assert r.status_code == 200 and r.get_json()["mode"] == "dry_run"
    assert "settings" in r.headers["X-NMAS-Invalidates"]
    assert H.current("Default")["confirmed"]["by"] == TEST_PERSON
    # A replay of that confirm finds nothing to change; another change sent under the old
    # preview's fingerprint is refused as moved.
    again = client.post(base, data={"heal_mode": "dry_run", "fingerprint": body["fingerprint"],
                                    "reason": "again"})
    assert again.status_code == 409 and again.get_json()["error"] == (
        "not saved: something to confirm: the policy would be what it is now")
    stale = client.post(base, data={"heal_max_per_device_hour": "0", "reason": "again",
                                    "fingerprint": body["fingerprint"]})
    assert stale.status_code == 409 and "moved since the preview" in stale.get_json()["error"]
    r = client.post(base + "/off")
    assert r.status_code == 200 and H.current("Default")["mode"] == "off"
    r = client.post("/v2/settings/installation/heal/stop", data={"why": "drill"})
    assert r.status_code == 200 and H.stopped()["stopped"]
    pv = client.post("/v2/settings/installation/heal/resume/preview").get_json()
    r = client.post("/v2/settings/installation/heal/resume",
                    data={"fingerprint": pv["fingerprint"], "reason": "drill over"})
    assert r.status_code == 200 and not H.stopped()["stopped"]


@pytest.mark.real_identity
def test_the_confirm_route_refuses_an_unverified_caller(client):
    r = client.post("/v2/settings/network/Default/heal",
                    data={"heal_mode": "dry_run", "fingerprint": "x", "reason": "r"})
    assert r.status_code in (401, 403), r.status_code
    assert H.current("Default", T0)["set"] == "off" and record() == []
