"""The Self-healing switch's batch (C3823, C3866, C3909, C3750; the operator's decision 8,
2026-11-18, C3971: "Add tests for the switch's batch only where it has no coverage").

The switch on Troubleshoot › Incidents' control strip (`routes/control_v2.heal`,
`modules/control_strip.switch_on`, `heal.batch.press` with ``switch``), pressed as its form
draws it, through the real app, the real policy write, the real decisions and incidents
stores and the real preview. Stand-ins only for what starts background work: the batch's job
(`capture_job.start`, recorded, its work never run, so no device is reached), the retry thread
a turn-on starts (`heal.retry.run_soon`, recorded), and the AI's starts (a tripwire).

What is held here, each rule with its decision:
- nothing open at the press: self-healing turned on plainly, no job, no batch (C3909);
- problems open: the batch approved and recorded named after the switch-on, its job started,
  the strip answering "Starting N fixes…" (C3823, C3866);
- the switch never starts the AI, an open incident with no fix included (C3823);
- the line moved since drawn: never refused, the problems open at the press taken (C3909);
- the retry the switch-on starts leaves the batch's own incidents to the batch (C3823);
- a request that may not press is refused before anything starts (`batch.may_press`);
- Auto not confirmable: refused, nothing turned on, nothing started (Gate 2's review);
- Off is Dry run, recorded as the person's change;
- On is Auto until someone turns it off, with no expiry (C3750, N8 as changed 2026-11-16).
"""

import re
from html import unescape

import pytest

from modules.heal import batch as B
from tests.test_heal_decide import GOLDEN, ROUTE4, Fake, lab, settle  # noqa: F401
from tests.test_heal_policy import T0, confirm, record
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

NET = "Default"
FORM = re.compile(r'<form class="ctl-item" id="ctl-heal" method="post" action="([^"]+)"'
                  r'.*?name="on" value="([01])">.*?name="hash" value="([0-9a-f]*)"', re.S)


@pytest.fixture
def world(lab, monkeypatch):  # noqa: F811
    """Default marked lab, in dry run allowing the added-line kind (so a dry-run would-heal is
    a fix the switch lists, C3844), the app's client, and the recorders."""
    import app as nmas_app
    from modules import control_strip, heal_notice
    from modules.heal import retry
    from modules.nsot import capture_job

    confirm(NET, heal_mode="dry_run", heal_kinds_auto=["added_line"])
    # What a screen drew is held per process (C3866); a line another test drew is not this one's.
    monkeypatch.setattr(control_strip, "_held", {})
    w = type("World", (), {})()
    w.client, w.jobs, w.retries = nmas_app.app.test_client(), [], []

    def start(list_name, label, actor, work, **kw):
        w.jobs.append(dict(kw, list=list_name, label=label, actor=actor))
        return f"job-{len(w.jobs)}"
    monkeypatch.setattr(capture_job, "start", start)
    monkeypatch.setattr(retry, "run_soon",
                        lambda network, trigger, **kw: w.retries.append(dict(kw, trigger=trigger)))
    monkeypatch.setattr(heal_notice, "start_catch_up",
                        lambda *a, **k: pytest.fail("the Self-healing switch started the AI"))
    return w


def would_heal(device="edge-b", running=GOLDEN + ROUTE4):
    """An open incident on *device* standing on a dry-run would-heal of an added route: a fix
    Mercury runs once self-healing is On (C3844), decided by the real decision."""
    from modules.heal import decide

    inc = settle(running, device=device, claim=False)
    (d,) = decide.run(NET, now=T0, sources=Fake(running))["decided"]
    assert d["outcome"] == "would_heal", d
    return inc["id"]


def drawn(w) -> tuple:
    """The switch's form as the strip draws it: ``(action, on, hash)``."""
    body = unescape(w.client.get(f"/v2/control/strip?list={NET}").get_data(as_text=True))
    form = FORM.search(body)
    assert form, "the strip drew no Self-healing switch"
    return form.group(1), form.group(2), form.group(3)


def press(w, action, on, shown):
    r = w.client.post(action, data={"on": on, "hash": shown})
    return r.status_code, unescape(r.get_data(as_text=True))


def batch_rows():
    from modules.heal import decisions

    return [r for r in decisions.read(NET)["rows"] if r.get("row") == "batch"]


def mode():
    from modules.heal import policy

    return policy.current(NET)


def test_the_press_is_timed_at_the_level_the_service_keeps(world, caplog):
    """f123edeb (the overnight speed pass, 2026-11-17, C3907): the Self-healing press's answer
    is timed in one line at WARNING, the level the host's service keeps, and so is the
    switch's batch decided in its request. The debt pass, 2026-11-18 (docs/FAST_LANE_DEBT.md's
    row for f123edeb and 5a808325)."""
    import logging
    would_heal()
    action, on, shown = drawn(world)
    with caplog.at_level(logging.WARNING):
        code, body = press(world, action, on, shown)
    assert code == 200, body
    said = {r.getMessage().rsplit(" in ", 1)[0]: r for r in caplog.records
            if r.levelno == logging.WARNING and r.name in ("routes.control_v2",
                                                           "modules.control_strip")}
    assert f"control strip: the Self-healing press on {NET} answered" in said, list(said)
    assert f"control strip: the switch's batch decided on {NET}" in said, list(said)


def test_nothing_open_at_the_press_turns_it_on_plainly_with_no_job(world):
    """C3909 (the operator, 2026-11-17): the line's problems gone at the press, the switch
    turns self-healing on as the switch with no line does, never refused because the line
    moved: Auto on, no batch job, no batch recorded."""
    from modules import invalidation
    from modules.heal import incidents

    iid = would_heal()
    action, on, shown = drawn(world)
    assert on == "1" and shown, "one open problem: the line and its hash drawn"
    # Gone before the press, closed and announced as the decision closes one (`decide`'s
    # nothing-to-do close, then its announcement), so the drawn line is no longer held.
    incidents.close(NET, iid, "nothing: back at its golden before the press")
    invalidation.announce(invalidation.ANNOUNCERS["heal-decide"], by="heal-decide")
    code, body = press(world, action, on, shown)
    assert code == 200, body
    assert mode()["mode"] == "auto"
    assert "Self-healing: self-healing turned on in Auto" in body
    assert world.jobs == [] and batch_rows() == []


def test_open_problems_are_the_batch_approved_and_named_after_the_switch_on(world):
    """C3823 (the operator, 2026-11-16: "switching Self-healing On IS the approval for what's
    already open") and C3866 ("Every switch flips instantly; the work it starts happens after,
    in the background"): pressed at the line's hash, Auto is on, the batch approved and
    recorded named after the switch-on with that hash and its device, its job started, and
    the strip answers "Starting 1 fix…"."""
    iid = would_heal()
    action, on, shown = drawn(world)
    code, body = press(world, action, on, shown)
    assert code == 200, body
    assert "Starting 1 fix…" in body
    assert mode()["mode"] == "auto"
    (row,) = batch_rows()
    assert row["source"] == "switch" and row["hash"] == shown
    assert row["named"].startswith("self-healing switched on by ")
    assert [(i["device"], i["incident"]) for i in row["items"]] == [("edge-b", iid)]
    (job,) = world.jobs
    assert job["kind"] == B.KIND and job["label"].startswith(B.SWITCH)
    (policy_row,) = [r for r in record(NET) if r.get("mode") == "auto"]
    assert row["named"] in policy_row["reason"] and shown[:12] in policy_row["reason"]


def test_the_switch_never_starts_the_ai(world, monkeypatch):
    """C3823: the switch's batch is restores and saved scripts, never the AI: with an open
    incident Mercury has no fix for beside the one it fixes (one the card's press would start
    the AI on), the press starts no AI (the tripwire on `heal_notice.start_catch_up`), its
    batch lists none for the AI, and AI troubleshooting stays off."""
    from modules.fixit import auto as A

    # edge-c in the inventory, so its incident has an identity the AI's record takes.
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [
        {"hostname": "edge-c", "ip": "192.0.2.7", "device_type": "cisco_xe", "_netbox_id": 7}])
    would_heal()
    settle(GOLDEN + "username audit privilege 15 secret 9 $9$abc\n", device="edge-c",
           claim=False)
    from modules.heal import decide
    (d,) = decide.run(NET, now=T0, sources=Fake(
        GOLDEN + "username audit privilege 15 secret 9 $9$abc\n"))["decided"]
    assert d["outcome"] == "cant_fix", d
    # The card's press would hand this one to the AI (`control_strip.batch_ai_items`).
    from modules import control_strip
    got = control_strip.batch_ai_items(NET)
    assert [a["device"] for a in got["items"]] == ["edge-c"], got
    action, on, shown = drawn(world)
    code, body = press(world, action, on, shown)
    assert code == 200, body
    (row,) = batch_rows()
    assert row["ai"] == [] and [i["device"] for i in row["items"]] == ["edge-b"]
    assert not A.switch(NET)["on"]


def test_a_line_that_moved_takes_the_problems_open_at_the_press(world):
    """C3909 (the operator, 2026-11-17: "Self-healing On + an approved fix ... -> it runs"):
    a second problem opened after the line was drawn, the press at the old line's hash is
    never refused; the batch is the problems open at the press, both devices, under the hash
    of the preview made at the press."""
    first = would_heal()
    action, on, shown = drawn(world)
    second = would_heal(device="edge-c")
    code, body = press(world, action, on, shown)
    assert code == 200, body
    assert "Starting 2 fixes…" in body
    (row,) = batch_rows()
    assert sorted(i["incident"] for i in row["items"]) == sorted([first, second])
    assert row["hash"] != shown
    assert len(world.jobs) == 1


def test_the_retry_the_switch_on_starts_leaves_the_batch_s_incidents_to_it(world):
    """C3823: turning Auto on starts the switched-on retry (`policy.apply`'s
    `retry.run_soon`), and that retry leaves out every incident the batch fixes, so none is
    tried twice."""
    iid = would_heal()
    action, on, shown = drawn(world)
    code, body = press(world, action, on, shown)
    assert code == 200, body
    (retried,) = world.retries
    assert retried["trigger"] == "switched_on" and iid in retried["skip"]


@pytest.mark.parametrize("who", ["unverified", "service", "service-past-the-gate"])
def test_a_request_that_may_not_press_is_refused_before_anything_starts(world, monkeypatch,
                                                                       who):
    """The press is a verified person's who may change self-healing settings: an unverified
    request or a service is refused, and nothing starts: self-healing stays in Dry run, no
    batch recorded, no job, no policy change. The route gate refuses the first two; with
    ``require_person_for_configure`` off, a service passes the gate and the route's own
    first step (`batch.may_press`) refuses it."""
    from modules import identity
    from modules.settings_schema import write_settings

    would_heal()
    action, on, shown = drawn(world)
    if who == "service-past-the-gate":
        assert write_settings({"require_person_for_configure": False})["ok"]
    before = record(NET)
    ident = (identity.Identity() if who == "unverified" else
             identity.Identity(actor="service:abc.access", kind="service", verified=True,
                               outcome="ok", peer="198.51.100.7", peer_trusted=True,
                               header_present=True))
    monkeypatch.setattr(identity, "identify", lambda _request: ident)
    code, body = press(world, action, on, shown)
    assert code in (401, 403), (code, body)
    if who == "service-past-the-gate":
        assert "Self-healing was not changed: the press is a verified person's" in body
    assert mode()["mode"] == "dry_run"
    assert batch_rows() == [] and world.jobs == [] and record(NET) == before


def test_auto_not_confirmable_is_refused_and_nothing_starts(world):
    """Gate 2's review (`batch.press`): Auto's turn-on is planned before anything starts, and
    one that is not confirmable refuses the press naming the gate. Here Auto is confirmed and
    in force while the kill switch stops self-healing everywhere, so turning it on again has
    nothing to confirm: refused (409), no batch recorded, no job, no policy change."""
    from modules.heal import policy

    would_heal()
    confirm(NET, heal_mode="auto", heal_mode_until="", heal_kinds_auto=["added_line"])
    policy.stop(actor="admin@example.com", actor_verified="access", why="the drill")
    assert mode()["mode"] == "off"
    action, on, shown = drawn(world)
    before = record(NET)
    code, body = press(world, action, on, shown)
    assert code == 409, (code, body)
    assert "Self-healing was not changed" in body and "cannot be turned on in Auto" in body
    assert batch_rows() == [] and world.jobs == [] and record(NET) == before


def test_off_is_dry_run_recorded_as_the_person_s_change(world):
    """The switch's Off (`control_strip.set_heal`): once on, pressed as drawn it turns
    self-healing to Dry run through the policy's own write, recorded with the toggle's
    words as its reason, and starts nothing."""
    would_heal()
    action, on, shown = drawn(world)
    assert press(world, action, on, shown)[0] == 200
    action, on, shown = drawn(world)
    assert (on, shown) == ("0", ""), "On: the switch posts Off, with no hash"
    code, body = press(world, action, on, shown)
    assert code == 200, body
    assert mode()["mode"] == "dry_run"
    assert "Self-healing: self-healing is in Dry run" in body
    last = record(NET)[-1]
    assert last["mode"] == "dry_run" and "turned off" in last["reason"]
    assert len(world.jobs) == 1, "Off started no job of its own"


@pytest.mark.parametrize("open_problem", [True, False], ids=["with-a-line", "no-line"])
def test_on_is_auto_until_someone_turns_it_off(world, open_problem):
    """C3750 (the operator's change to N8, 2026-11-16): the strip's On has no expiry, with a
    line (the batch's turn-on) or without one (the plain toggle): Auto is stored with no
    expiry, in force as "until turned off", and the switch is drawn On, never "On until"."""
    if open_problem:
        would_heal()
    action, on, shown = drawn(world)
    assert bool(shown) is open_problem
    code, body = press(world, action, on, shown)
    assert code == 200, body
    cur = mode()
    assert (cur["mode"], cur["until"]) == ("auto", "")
    assert "until turned off" in cur["words"]
    assert "On until" not in body and "until someone turns it off" in body


def test_the_switch_line_promises_a_fix_only_for_what_it_fixes():
    """The line beside the switch (`batch.switch_words`) counts as fixed only what the
    switch-on fixes, its restores and saved scripts; the open incidents it decides again in
    Auto are said apart, each fixed only if Auto allows its kind (the correctness review's G2
    M2: after 226477ad a Tier 2 kind is proposed and an unlisted Tier 1 kind stays a dry run,
    so "read and fixed now" promised fixes that do not happen)."""
    both = B.switch_words(5, 2, decided=3)
    assert both.startswith("Also fixes the 7 open problems (5 restores, 2 saved scripts)"), both
    assert "fixed now" not in both
    assert "3 more decided again in Auto, each fixed by itself only if its kind is allowed " \
           "Auto" in both, both
    alone = B.switch_words(0, 0, decided=1)
    assert "fixes" not in alone.lower() and "fixed now" not in alone, alone
    assert alone.startswith("Decides 1 open problem again in Auto"), alone
    assert B.switch_words(2, 0) == "Also fixes the 2 open problems (2 restores)"


def test_the_switchs_contract_says_a_moved_line_is_taken_never_refused():
    """C3982: since C3909 the switch takes the problems open at the press when its line moved
    (this file's moved-line test), and its declared contract, its route's docstring and
    `control_strip`'s said it was refused; each now says what it does."""
    import inspect
    from modules import control_strip, route_gates
    from routes import control_v2
    for words in (route_gates.GATES["control_v2.heal"].reason,
                  inspect.getsource(control_v2).split('"""', 2)[1],
                  inspect.getsource(control_strip).split('"""', 2)[1]):
        flat = " ".join(words.split())
        assert "refused, nothing turned on, when they moved" not in flat, flat[:200]
        assert "the problems open at the press" in flat, flat[:200]
