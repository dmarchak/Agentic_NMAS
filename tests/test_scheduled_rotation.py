"""C724: scheduled credential rotation (modules/nsot/scheduled_rotation.py), on a data folder,
settings file and credential store of this test's own, through the real selection, the real
run (its lock, its record, its checks: device holds, planned restarts), the real Needs
attention source, History's sources and the real routes. The rotation itself is a stand-in
for `rotate_op.run` that records how it was called: the run hands every device to that one
path, so what is held here is WHICH devices reach it, in what order, as whom, and what stops
the run.

- the timer picks exactly the due devices: older than the policy, or never rotated by
  Mercury; not a device whose profile's policy is off, nor one no profile covers;
- the preferred window, the per-run limit (oldest first), and once in any 24 hours;
- never in the nightly backup window (08:30 to 09:10 UTC), and a run that reaches it stops;
- a held device, one mid-restart (a planned window) and one off its intent are skipped with
  the reason, and the rest still run;
- the first failure stops the run, raises the CRITICAL row naming the device and the stage,
  and the timer starts nothing until a person's run finishes clean, which clears it;
- never two runs at once (the lock), and a second is refused naming the first;
- a policy is set only by a verified person, and is recorded; History draws it, and a
  scheduled rotation's rows say "scheduled rotation (policy set by <person>)".
"""

import calendar
import json
import os
import threading
import time

import pytest

from modules.nsot import scheduled_rotation as SR

SETTER = "alice@example.invalid"


def _at(text: str) -> float:
    return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ"))


NOW = _at("2026-10-12T14:00:00Z")      # inside no backup window
DAY = 86400


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.config.USER_SETTINGS_FILE", str(tmp_path / "user_settings.json"))
    monkeypatch.setattr("modules.credentials._FILE", str(tmp_path / "credential_profiles.json"))
    return tmp_path


def _policy(days=30, start=0, end=24, most=5, state="on", by=SETTER):
    return {"state": state, "days": days, "window_start": start, "window_end": end,
            "max_per_run": most, "set_by": by, "set_at": "2026-10-01T00:00:00Z",
            "verified": "access"}


DEVICES = [{"hostname": "r1", "role": "router"}, {"hostname": "r2", "role": "router"},
           {"hostname": "r3", "role": "router"}, {"hostname": "s1", "role": "switch"},
           {"hostname": "x9", "role": "firewall"}]


def _states(now=NOW, pols=None, rotations=None, names=("role:router", "role:switch")):
    return SR.device_states(
        now, lists=["Lab"], devices_of=lambda _l: DEVICES,
        rotations=rotations if rotations is not None else {
            "r1": (now - 40 * DAY, SR._iso(now - 40 * DAY)),
            "r2": (now - 5 * DAY, SR._iso(now - 5 * DAY)),
            "s1": (now - 90 * DAY, SR._iso(now - 90 * DAY))},
        pols=pols if pols is not None else {"role:router": _policy(),
                                             "role:switch": _policy(state="off")},
        profile_names=set(names))


class Rotations:
    """`rotate_op.run`'s stand-in: each call recorded; *fail* names a device whose rotation
    is reverted at the fresh login."""

    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def __call__(self, list_name, host, **kw):
        from modules.nsot import credential_rotation as cr
        self.calls.append(dict(kw, list=list_name, device=host))
        if host in self.fail:
            return {"device": host, "state": cr.REVERTED, "steps": [
                {"name": "push", "ok": True},
                {"name": "verify_new_credential", "ok": False, "detail": "refused"}]}
        return {"device": host, "state": cr.ROTATED_PERSISTED, "steps": [{"name": "commit",
                                                                         "ok": True}]}


def _plan(_l, host):
    return {"ok": True, "fingerprint": f"fp-{host}"}


CLEAN = {"off_intent": lambda _l, _h: ""}


def _run(monkeypatch, states, **kw):
    monkeypatch.setattr(SR, "device_states", lambda now=None, **_k: states)
    kw.setdefault("plan", _plan)
    kw.setdefault("checks", CLEAN)
    kw.setdefault("now", NOW)
    return SR.run(**kw)


# ---------------------------------------------------------------------------- selection

def test_exactly_the_due_devices():
    states = {s["device"]: s for s in _states()}
    assert {d for d, s in states.items() if s["due"]} == {"r1", "r3"}
    assert states["r3"]["never"] and "never rotated by Mercury" in states["r3"]["words"]
    assert states["r3"]["age_words"] == "never rotated by Mercury"
    assert states["r1"]["age_words"] == "rotated 40 days ago"
    assert not states["r2"]["due"] and states["r2"]["due_at"] == SR._iso(NOW + 25 * DAY)
    # s1 is 90 days old, but its profile's policy is off; x9 has no profile at all.
    assert not states["s1"]["due"] and "policy is off" in states["s1"]["words"]
    assert not states["x9"]["due"] and states["x9"]["profile"] == ""


def test_a_one_day_policy_makes_a_day_old_credential_due():
    rot = {"r1": (NOW - DAY - 60, ""), "r2": (NOW - 3600, ""), "r3": (NOW - 3600, "")}
    states = _states(pols={"role:router": _policy(days=1)}, rotations=rot)
    assert {s["device"] for s in states if s["due"]} == {"r1"}


def test_the_most_specific_existing_profile_governs():
    assert SR.governing_profile({"role": "router", "site": "hq"},
                                {"default", "site:hq", "role:router"}) == "role:router"
    assert SR.governing_profile({"role": "router", "site": "hq"}, {"default", "site:hq"}) \
        == "site:hq"
    assert SR.governing_profile({"role": "router"}, {"default"}) == "default"
    assert SR.governing_profile({"role": "router"}, set()) == ""


def test_the_preferred_window_and_once_a_day():
    states = _states(pols={"role:router": _policy(start=10, end=12)})
    inside, outside = _at("2026-10-12T11:00:00Z"), _at("2026-10-12T12:00:00Z")
    chosen, waiting = SR.select(states, inside, scheduled=True)
    assert [s["device"] for s in chosen] == ["r3", "r1"]
    chosen, waiting = SR.select(states, outside, scheduled=True)
    assert chosen == [] and all("outside role:router's preferred window" in w["why"]
                                for w in waiting)
    # A person's run takes them outside the window too.
    assert len(SR.select(states, outside, scheduled=False)[0]) == 2
    # Once a UTC day for a scheduled run.
    chosen, waiting = SR.select(states, inside, scheduled=True, ran_today={"role:router"})
    assert chosen == [] and "ran in the last 24 hours" in waiting[0]["why"]


def test_a_window_past_midnight_wraps():
    p = {"window_start": 22, "window_end": 2}
    assert SR.in_window(p, _at("2026-10-12T23:00:00Z"))
    assert SR.in_window(p, _at("2026-10-12T01:00:00Z"))
    assert not SR.in_window(p, _at("2026-10-12T12:00:00Z"))


def test_the_per_run_limit_takes_the_oldest_first():
    rot = {"r1": (NOW - 40 * DAY, SR._iso(NOW - 40 * DAY)),
           "r2": (NOW - 60 * DAY, SR._iso(NOW - 60 * DAY))}
    states = _states(pols={"role:router": _policy(most=2)}, rotations=rot)
    chosen, waiting = SR.select(states, NOW, scheduled=True)
    # r3 was never rotated (first), then the older of r1 and r2.
    assert [s["device"] for s in chosen] == ["r3", "r2"]
    assert [w["device"] for w in waiting] == ["r1"] and "limit of 2" in waiting[0]["why"]


# ---------------------------------------------------------------------------- the backup window

@pytest.mark.parametrize("at,inside", [("08:29:59", False), ("08:30:00", True),
                                       ("09:09:59", True), ("09:10:00", False)])
def test_the_backup_window_bounds(at, inside):
    assert SR.in_backup_window(_at(f"2026-10-12T{at}Z")) is inside


def test_no_run_starts_in_the_backup_window(data, monkeypatch):
    rot = Rotations()
    got = _run(monkeypatch, _states(), trigger="scheduled", rotate=rot,
               now=_at("2026-10-12T08:45:00Z"))
    assert got["state"] == "refused" and "backup window" in got["error"]
    assert rot.calls == []
    assert SR.runs()["rows"][-1]["state"] == "refused"


def test_a_run_that_reaches_the_backup_window_stops_there(data, monkeypatch):
    rot = Rotations()
    times = iter([_at("2026-10-12T08:29:00Z")] * 4 + [_at("2026-10-12T08:31:00Z")] * 20)
    got = _run(monkeypatch, _states(), trigger="request", actor=SETTER, rotate=rot,
               clock=lambda: next(times))
    assert [c["device"] for c in rot.calls] == ["r3"]
    assert [n["device"] for n in got["not_reached"]] == ["r1"]
    assert "backup window" in got["error"]


# ---------------------------------------------------------------------------- checks before each

def test_a_held_device_is_skipped_and_the_rest_run(data, monkeypatch):
    from modules.nsot import device_ops
    rot = Rotations()
    with device_ops.hold("Lab", "r3", "deploy", "bob@example.invalid"):
        got = _run(monkeypatch, _states(), trigger="scheduled", rotate=rot)
    assert [c["device"] for c in rot.calls] == ["r1"]
    (skip,) = got["skipped"]
    assert skip["device"] == "r3" and "held by another operation" in skip["why"]
    assert got["state"] == "done"


def test_a_device_mid_restart_is_skipped(data, monkeypatch):
    from modules import restarts
    now = time.time()
    if SR.in_backup_window(now):
        pytest.skip("the real clock is inside the backup window, where no run starts")
    assert restarts.record_planned(["r1"], now - 60, now + 600, by=SETTER,
                                   why="a planned reload for this test", via="test",
                                   list_name="Lab")["ok"]
    rot = Rotations()
    got = _run(monkeypatch, _states(now=now), trigger="request", actor=SETTER, rotate=rot,
               now=now)
    assert [c["device"] for c in rot.calls] == ["r3"]
    (skip,) = got["skipped"]
    assert skip["device"] == "r1" and "planned restart window covers it" in skip["why"]


def test_off_intent_and_unreachable_are_skipped_with_the_reason(data, monkeypatch):
    rot = Rotations()
    got = _run(monkeypatch, _states(), trigger="scheduled", rotate=rot,
               checks={"off_intent": lambda _l, h: "off its intent: 2 lines" if h == "r3"
                       else ""},
               plan=lambda _l, h: {"ok": False, "error": "timed out"} if h == "r1"
               else _plan(_l, h))
    assert rot.calls == []
    why = {s["device"]: s["why"] for s in got["skipped"]}
    assert why["r3"] == "off its intent: 2 lines"
    assert "unreachable" in why["r1"] and "timed out" in why["r1"]
    assert SR.runs()["rows"][-1]["skipped"] == got["skipped"]


# ---------------------------------------------------------------------------- what the rotation is told

def test_each_rotation_is_the_device_page_path_named_as_scheduled(data, monkeypatch):
    rot = Rotations()
    got = _run(monkeypatch, _states(), trigger="scheduled", rotate=rot)
    assert got["state"] == "done" and [r["device"] for r in got["rotated"]] == ["r3", "r1"]
    for c in rot.calls:
        assert c["actor"] == SETTER and c["source"] == "scheduled_rotation"
        assert c["via"] == f"scheduled rotation (policy set by {SETTER})"
        assert c["fingerprint"] == f"fp-{c['device']}" and c["actor_kind"] == "policy"
    rot2 = Rotations()
    _run(monkeypatch, _states(), trigger="request", actor="carol@example.invalid", rotate=rot2)
    assert all(c["actor"] == "carol@example.invalid" and c["actor_kind"] == "person"
               and c["via"].endswith("run now by carol@example.invalid") for c in rot2.calls)


def test_rotate_op_run_passes_the_words_to_the_record_and_the_commit(monkeypatch):
    """`rotate_op.run` hands *via*, *actor_kind* and *source* to `credential_rotation`, so the
    record and the commit carry them; a manual rotation's are unchanged."""
    from modules.nsot import credential_rotation as cr
    from modules.nsot import rotate_op
    seen = []
    monkeypatch.setattr(cr, "rotate", lambda l, h, **kw: seen.append(kw) or
                        {"state": cr.REVERTED})
    rotate_op.run("Lab", "r1", actor=SETTER, fingerprint="fp", via="scheduled rotation (x)",
                  actor_kind="policy", source="scheduled_rotation")
    rotate_op.run("Lab", "r1", actor=SETTER, fingerprint="fp")
    assert (seen[0]["via"], seen[0]["actor_kind"], seen[0]["source"]) == \
        ("scheduled rotation (x)", "policy", "scheduled_rotation")
    assert (seen[1]["via"], seen[1]["actor_kind"], seen[1]["source"]) == \
        ("device page", "person", "rotation")


# ---------------------------------------------------------------------------- the first failure

def test_the_first_failure_stops_the_run_and_raises_the_row(data, monkeypatch):
    from modules import attention as A
    rot = Rotations(fail={"r3"})
    got = _run(monkeypatch, _states(), trigger="scheduled", rotate=rot)
    assert [c["device"] for c in rot.calls] == ["r3"]            # r1 never reached
    assert got["state"] == "stopped"
    assert got["failed"]["device"] == "r3" and got["failed"]["stage"] == "verify_new_credential"
    assert [n["device"] for n in got["not_reached"]] == ["r1"]

    res = A.scheduled_rotation_source()
    (row,) = res["rows"]
    assert row["level"] == "danger" and row["devices"] == ["r3"]
    assert "r3 failed at verify_new_credential" in row["what"]

    # The timer starts nothing while it stands...
    rot2 = Rotations()
    got2 = _run(monkeypatch, _states(), trigger="scheduled", rotate=rot2)
    assert got2["state"] == "refused" and "the timer starts no run" in got2["error"]
    assert rot2.calls == []
    assert A.scheduled_rotation_source()["rows"]                   # a refusal clears nothing
    # ...and a person's run that finishes clean clears it.
    got3 = _run(monkeypatch, _states(), trigger="request", actor=SETTER, rotate=Rotations())
    assert got3["state"] == "done"
    assert A.scheduled_rotation_source()["rows"] == []


def test_the_row_is_declared_with_how_it_clears():
    from modules import attention as A
    assert ("scheduled_rotation", "stopped") in A.ROW_KINDS
    assert A.CLEARS[("scheduled_rotation", "stopped")][0] == ("resolves",)
    assert A.scheduled_rotation_source in A.SOURCES


# ---------------------------------------------------------------------------- one at a time

def test_never_two_runs_at_once(data, monkeypatch):
    rot = Rotations()
    with SR.RunLock("bob@example.invalid", "request"):
        got = _run(monkeypatch, _states(), trigger="scheduled", rotate=rot)
    assert got["state"] == "refused" and rot.calls == []
    assert "another scheduled rotation run is going" in got["error"]
    assert "bob@example.invalid" in got["error"]
    # Released, the next run goes.
    assert _run(monkeypatch, _states(), trigger="scheduled", rotate=rot)["state"] == "done"


# ------------------------------------------- every due device, one after another (2026-10-13)

def _three_due():
    """r3 never rotated, r1 40 days, r2 5 days: all due under a 1-day policy with no cap, the
    queue oldest password first."""
    return _states(pols={"role:router": _policy(days=1, most=None)})


class Pushes:
    """The post-commit hooks' one spy: what was PUSHED (a held repository fires once, at the
    run's end)."""

    def __init__(self, monkeypatch):
        from modules.nsot import hooks
        self.seen, self.done = [], threading.Event()
        monkeypatch.setattr(hooks, "ensure_default_hooks", lambda: None)
        monkeypatch.setattr(hooks, "_hooks", [{"name": "spy", "timeout": 5,
                                                "func": self._spy}])

    def _spy(self, ctx):
        self.seen.append(ctx)
        self.done.set()
        return {"ok": True}

    def wait(self):
        self.done.wait(5)                     # the hooks fire on a thread: bounded, 5 s
        return self.seen


class CommittingRotations(Rotations):
    """Rotations that also COMMIT as the rotation's own commit publishes: one context a
    device into the list's repository, its golden tag beside it."""

    def __call__(self, list_name, host, **kw):
        from modules.config import list_data_path
        from modules.nsot import credential_rotation as cr, hooks
        out = super().__call__(list_name, host, **kw)
        if out["state"] == cr.ROTATED_PERSISTED:
            hooks.run_post_commit({"repo": os.path.join(list_data_path(list_name), "config_repo"),
                                   "sha": f"sha-{host}", "tags": [f"golden/{host}/t"],
                                   "devices": [host], "list_name": list_name})
        return out


def test_three_due_and_the_second_fails(data, monkeypatch):
    """First recorded, second reverted (as today), third not started, the halt raised, and
    the first's commit pushed at the stop."""
    pushes = Pushes(monkeypatch)
    rot = CommittingRotations(fail={"r1"})
    got = _run(monkeypatch, _three_due(), trigger="request", actor=SETTER, rotate=rot)
    assert [c["device"] for c in rot.calls] == ["r3", "r1"]
    assert [r["device"] for r in got["rotated"]] == ["r3"]
    assert got["state"] == "stopped" and got["failed"]["device"] == "r1"
    assert [n["device"] for n in got["not_reached"]] == ["r2"]
    assert SR.halted(SR.runs()["rows"]) is not None
    (pushed,) = pushes.wait()
    assert pushed["devices"] == ["r3"] and pushed["tags"] == ["golden/r3/t"]


def test_all_due_rotated_one_after_another_and_pushed_once(data, monkeypatch):
    pushes = Pushes(monkeypatch)
    rot = CommittingRotations()
    got = _run(monkeypatch, _three_due(), trigger="request", actor=SETTER, rotate=rot)
    assert got["state"] == "done"
    assert [r["device"] for r in got["rotated"]] == ["r3", "r1", "r2"]   # oldest first
    (pushed,) = pushes.wait()                                            # ONE push
    assert pushed["devices"] == ["r1", "r2", "r3"] and pushed["sha"] == "sha-r2"
    assert pushed["tags"] == ["golden/r3/t", "golden/r1/t", "golden/r2/t"]


def test_a_cap_of_two_with_three_due_leaves_the_third_due(data, monkeypatch):
    states = _states(pols={"role:router": _policy(days=1, most=2)})
    rot = Rotations()
    got = _run(monkeypatch, states, trigger="request", actor=SETTER, rotate=rot)
    assert [r["device"] for r in got["rotated"]] == ["r3", "r1"]
    assert [w["device"] for w in got["waiting"]] == ["r2"]
    assert "limit of 2 a run" in got["waiting"][0]["why"]


def test_a_person_s_run_while_the_timer_holds_the_policy_is_refused(data, monkeypatch):
    rot = Rotations()
    with SR.RunLock("the timer", "scheduled"):
        got = _run(monkeypatch, _three_due(), trigger="request", actor=SETTER, rotate=rot)
    assert got["state"] == "refused" and rot.calls == []
    assert "the timer" in got["error"], got["error"]


def test_a_blank_cap_is_no_cap_and_says_so(data):
    _profile()
    got = SR.set_policy("role:router", {"state": "on", "days": "1", "max_per_run": ""},
                        actor=SETTER, verified="access", person=True)
    assert got["ok"] and "max_per_run" not in got["policy"], got
    assert "every due device a run" in got["words"]


# ---------------------------------------------------------------------------- the policy

def _profile(name="role:router"):
    from modules import credentials
    credentials.save_profile(name, username="netops", password="Prof-Pass-5531")


def test_a_policy_needs_a_verified_person(data):
    _profile()
    for person, verified in ((False, "access"), (True, "none")):
        got = SR.set_policy("role:router", {"state": "on", "days": "1"}, actor=SETTER,
                            verified=verified, person=person)
        assert not got["ok"] and "verified person" in got["error"]
    assert SR.policies() == {}
    got = SR.set_policy("role:router", {"state": "on", "days": "1", "window_start": "0",
                                        "window_end": "24", "max_per_run": "2"},
                        actor=SETTER, verified="access", person=True)
    assert got["ok"] and got["words"] == "every 1 day, any hour, at most 2 a run"
    assert SR.policies()["role:router"]["set_by"] == SETTER
    (rec,) = [json.loads(l) for l in (data / "credential_changes.jsonl").read_text().splitlines()]
    assert rec["action"] == "rotation_policy" and rec["actor"] == SETTER
    assert rec["policy"] == got["words"]


def test_a_policy_limited_to_named_devices_covers_only_those(data):
    """A pilot set (the walk, 2026-10-12: every lab device follows `default`, and s3 must never
    be rotated unattended): named devices only; the rest say so and are never due."""
    _profile()
    got = SR.set_policy("role:router", {"state": "on", "days": "1", "devices": "r2, r3"},
                        actor=SETTER, verified="access", person=True)
    assert got["ok"] and got["policy"]["devices"] == ["r2", "r3"]
    assert got["words"].endswith("every due device a run, only r2, r3")
    states = {s["device"]: s for s in _states(pols={"role:router": got["policy"]})}
    assert states["r3"]["due"] and not states["r1"]["due"]
    assert "names other devices (r2, r3), not this one" in states["r1"]["words"]
    bad = SR.set_policy("role:router", {"state": "on", "devices": "r2; rm"}, actor=SETTER,
                        verified="access", person=True)
    assert not bad["ok"] and "is not a device name" in bad["error"]


def test_a_credential_s_age_reads_the_repository_s_rotation_commits(monkeypatch, tmp_path):
    """The rotation record began after the first rotations (on the host, 2026-10-12, it held
    s1's and r2's while the repository held every device's from 2026-09-21): the age is the
    newest of the record's and the repository's."""
    log_out = ("1790000000\t2026-09-21T18:35:49+00:00\tcredential: r3 rotated to a "
               "device-generated type-9 secret\n"
               "1780000000\t2026-05-28T00:00:00+00:00\tcredential: r3 rotated to a "
               "device-generated type-9 secret\n"
               "1790000500\t2026-09-21T18:44:09+00:00\tgolden: baseline 2 device(s)\n")
    monkeypatch.setattr("modules.nsot.repo.git", lambda repo, *a: (0, log_out, ""))
    (tmp_path / "config_repo" / ".git").mkdir(parents=True)
    monkeypatch.setattr("modules.config.list_data_path", lambda name: str(tmp_path))
    assert SR.committed_rotations("Lab") == {"r3": (1790000000, "2026-09-21T18:35:49+00:00")}
    monkeypatch.setattr("modules.config.list_data_path", lambda name: str(tmp_path / "none"))
    assert SR.committed_rotations("Absent") == {}, "an absent repository is read as none"
    assert not (tmp_path / "none").exists(), "a read created a list"
    monkeypatch.setattr("modules.config.list_data_path", lambda name: str(tmp_path))
    monkeypatch.setattr(SR, "last_rotations", lambda: {"r2": (1795000000, "x")})
    states = {s["device"]: s for s in SR.device_states(
        1795000000 + 3600, lists=["Lab"], devices_of=lambda _l: DEVICES,
        pols={"role:router": _policy(days=1)}, profile_names={"role:router"})}
    assert not states["r3"]["never"] and states["r3"]["rotated_at"].startswith("2026-09-21")
    assert states["r1"]["never"] and not states["r2"]["due"]


def test_a_bad_policy_is_refused_naming_the_field(data):
    _profile()
    got = SR.set_policy("role:router", {"state": "on", "days": "0"}, actor=SETTER,
                        verified="access", person=True)
    assert not got["ok"] and "days is between 1 and 3650" in got["error"]
    got = SR.set_policy("role:nope", {"state": "on"}, actor=SETTER, verified="access",
                        person=True)
    assert not got["ok"] and "no profile is named" in got["error"]
    assert SR.policies() == {}


@pytest.fixture
def client(data, monkeypatch):
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    (data / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(data / "lab"))
    import app as A
    return A.app.test_client()


def test_the_route_sets_it_and_the_tab_draws_it(client, data):
    _profile()
    r = client.post("/v2/credentials/profiles/policy",
                    data={"name": "role:router", "state": "on", "days": "1",
                          "window_start": "0", "window_end": "24", "max_per_run": "3"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html[:400]
    assert "rotation policy: every 1 day, any hour, at most 3 a run" in html
    assert "Rotate due devices now…" in html and "Scheduled rotation" in html
    from modules import history_sources as H
    (e,) = H.credential_profiles({"device": "", "since": None})["events"]
    assert "rotation policy set: every 1 day" in e["what"]


@pytest.mark.real_identity
def test_the_route_refuses_anyone_but_a_person(client, data):
    _profile()
    r = client.post("/v2/credentials/profiles/policy",
                    data={"name": "role:router", "state": "on", "days": "1"})
    assert r.status_code in (401, 403)
    assert SR.policies() == {}


def test_the_timer_runs_only_when_a_policy_is_due_in_its_window(data, monkeypatch):
    ran = []
    monkeypatch.setattr(SR, "run", lambda **kw: ran.append(kw) or {"state": "done"})
    states = _states()
    monkeypatch.setattr(SR, "device_states", lambda now=None, **_k: states)
    monkeypatch.setattr(SR, "policies", lambda: {})
    assert SR.tick(NOW)["state"] == "idle" and ran == []          # no policy: nothing
    monkeypatch.setattr(SR, "policies", lambda: {"role:router": _policy(start=13, end=15)})
    assert SR.tick(_at("2026-10-12T08:45:00Z"))["state"] == "idle"  # the backup window
    assert SR.tick(_at("2026-10-12T16:00:00Z"))["state"] == "idle"  # outside its window
    assert ran == []
    SR.tick(NOW)
    assert ran == [{"trigger": "scheduled", "now": NOW}]


def test_the_commit_s_source_is_a_workflow_name_the_repository_accepts():
    """The host, 2026-10-12 23:56 UTC: s1 was rotated on the device and its commit refused,
    "source 'scheduled-rotation' is not a workflow name", because every test stubbed the
    commit. The slug is held to the repository's own rule, and the words for it exist."""
    from modules import device_list
    from modules.nsot import repo
    assert repo.SOURCE_SLUG.match(SR.SOURCE), SR.SOURCE
    assert device_list.SOURCE_WORDS[SR.SOURCE] == "a scheduled rotation"


def test_a_halt_clears_once_the_failed_device_s_rotation_is_committed(monkeypatch):
    """The host, 2026-10-13: s1's credential was recovered into the store (no commit), so the
    halt stood; it clears when s1's rotation is COMMITTED after the stop, never on the store
    alone, and a later clean run still clears it as before."""
    stop = {"run": "1", "trigger": "scheduled", "state": "stopped",
            "finished": "2026-10-12T23:56:40Z",
            "failed": {"device": "s1", "list": "Lab", "stage": "commit"}}
    commits = {}
    monkeypatch.setattr(SR, "committed_rotations", lambda name: commits)
    assert SR.halted([stop]) is stop                                   # nothing committed
    commits["s1"] = (SR._epoch("2026-10-12T20:00:00Z"), "")
    assert SR.halted([stop]) is stop                                   # committed BEFORE it
    assert SR.halted([stop, {"run": "2", "state": "refused"}]) is stop   # refused is no run
    commits["s1"] = (SR._epoch("2026-10-13T01:00:06Z"), "")
    assert SR.halted([stop]) is None                                   # settled after it
    commits.clear()
    assert SR.halted([stop, {"run": "2", "state": "done"}]) is None    # a clean run after


def test_a_scheduled_run_after_midnight_does_not_take_a_second_device(data, monkeypatch):
    """The host, 2026-10-12: the timer took s1 at 23:56 UTC; under "once a UTC day" its tick
    after 00:00 would have taken r2 too. One scheduled run per policy in any 24 hours."""
    ran = []
    monkeypatch.setattr(SR, "run", lambda **kw: ran.append(kw) or {"state": "done"})
    states = _states()
    monkeypatch.setattr(SR, "device_states", lambda now=None, **_k: states)
    monkeypatch.setattr(SR, "policies", lambda: {"role:router": _policy()})
    monkeypatch.setattr(SR, "runs", lambda: {"rows": [{
        "trigger": "scheduled", "started": "2026-10-12T23:56:17Z", "state": "done",
        "policies": ["role:router"]}]})
    assert SR.tick(_at("2026-10-13T00:05:41Z"))["state"] == "idle" and ran == []
    assert SR.tick(_at("2026-10-13T23:50:00Z"))["state"] == "idle" and ran == []
    SR.tick(_at("2026-10-13T23:57:00Z"))
    assert len(ran) == 1, "24 hours after the last, the next scheduled run"


def test_rotate_due_now_runs_as_a_job_through_rotate_op(data, monkeypatch):
    """`start_now` runs the run as a job whose rotations are `rotate_op.run`'s, as the
    person; the card reads it back."""
    from modules.nsot import capture_job, rotate_op
    rot = Rotations()
    monkeypatch.setattr(rotate_op, "run", rot)
    monkeypatch.setattr(rotate_op, "plan", _plan)
    monkeypatch.setattr(SR, "off_intent", lambda _l, _h: "")
    states = _states(now=time.time())
    monkeypatch.setattr(SR, "device_states", lambda now=None, **_k: states)
    if SR.in_backup_window():
        pytest.skip("the real clock is inside the backup window, where no run starts")
    job, run_id = SR.start_now(actor=SETTER, confirmed="")
    assert capture_job.wait(job, 20)
    assert capture_job.get(job)["payload"]["result"]["state"] == "done"
    assert [c["device"] for c in rot.calls] == ["r3", "r1"]
    assert {r["name"]: r["group"] for r in SR.run_card(run_id)["card"]["rows"]} == \
        {"r3": "done", "r1": "done"}


def test_the_forms_and_cards_draw(client, data):
    """The policy form, the preview with nothing due, and a run this server has no record
    of each draw their words in place."""
    _profile()
    html = client.get("/v2/credentials/profiles/policy?name=role:router").get_data(as_text=True)
    assert "Rotation policy for role:router" in html and 'name="days"' in html
    html = client.get("/v2/credentials/profiles/rotate-due").get_data(as_text=True)
    assert "Nothing is due now" in html
    html = client.get("/v2/credentials/profiles/rotate-due/job/nope?run=nope").get_data(
        as_text=True)
    assert "no record of that run" in html
    html = client.get("/v2/credentials/profiles?list=Lab").get_data(as_text=True)
    assert "Scheduled rotation" in html and "Rotation policy…" in html


def test_the_confirm_is_bound_to_the_previewed_list(client, data, monkeypatch):
    started = []
    monkeypatch.setattr(SR, "start_now", lambda **kw: started.append(kw) or ("j", "r"))
    monkeypatch.setattr(SR, "preview", lambda now=None: {
        "chosen": [{"list": "Lab", "device": "r1", "profile": "role:router",
                    "age_words": "never rotated by Mercury"}], "waiting": [],
        "hash": "abc", "backup_window": False, "covered": 1, "total": 1})
    r = client.post("/v2/credentials/profiles/rotate-due", data={"hash": "stale"})
    assert r.status_code == 409 and "(stale -&gt; abc)" in r.get_data(as_text=True)
    assert started == []
    r = client.post("/v2/credentials/profiles/rotate-due", data={"hash": "abc"})
    assert r.status_code == 202 and started[0]["confirmed"] == "abc"
    assert started[0]["actor"] == "test-person@example.invalid"


# ---------------------------------------------------------------------------- History

def test_history_names_a_scheduled_rotation(data, monkeypatch):
    from modules import history_sources as H
    from modules.nsot import credential_rotation as cr
    cr.record_outcome("rotate", {"device": "r1", "state": cr.ROTATED_PENDING_PERSIST,
                                 "actor": SETTER, "steps": [{"name": "commit", "ok": True}],
                                 "via": f"scheduled rotation (policy set by {SETTER})"})

    class Ref:
        name = "Lab"
    monkeypatch.setattr(H, "_mine", lambda ctx, device: True)
    (e,) = H.rotation({"ref": Ref, "limit": 50, "device": ""})["events"]
    assert e["what"].startswith(f"Scheduled rotation (policy set by {SETTER}): rotation:")
    # The credential age reads the same record.
    assert "r1" in SR.last_rotations()


# ---------------------------------------------------------------------------- break-glass

def test_after_a_rotation_the_break_glass_row_says_since_when(data, monkeypatch):
    """Reused, not duplicated: job health's one `breakglass_stale` row per device (C182)
    names the rotation's time from the same record the credential age reads."""
    import modules.breakglass as bg
    from modules.job_health import breakglass_rows
    from modules.nsot import credential_rotation as cr
    cr.record_outcome("rotate", {"device": "s1", "state": cr.ROTATED_PENDING_PERSIST,
                                 "steps": [], "via": "scheduled rotation (policy set by x)"})
    when = SR.last_rotations()["s1"][1]
    old = {"s1": bg.currency_digest("s1", "admin", "old-s1-pass-1234")}
    new = {"s1": bg.currency_digest("s1", "admin", "new-s1-pass-5678")}
    rows = breakglass_rows(exports={"state": "ok", "by_list": {"default": {
        "at": 1_790_000_000.0, "list": "default", "path": "/media/x.bg", "devices": old}}},
        current={"default": new}, intact={}, drills={"rows": []}, all_exports={"rows": []},
        now=1_790_000_100.0)
    (row,) = [r for r in rows if r["state"] == "breakglass_stale"]
    assert row["headline"] == f"s1's break-glass record is out of date since {when}: export " \
                              "it again"
    assert row["action"]["open"] == "breakglass_export"


# ---------------------------------------------------------------------------- the run's card

def test_the_run_is_drawn_on_the_one_stepper_in_place(client, data, monkeypatch):
    """A run's card: a row per device it took (done, failed, not reached), the skipped ones
    beside it with why, and the result line, drawn by the job route."""
    rot = Rotations(fail={"r1"})
    states = _states(rotations={"r2": (NOW - 70 * DAY, SR._iso(NOW - 70 * DAY)),
                                "r1": (NOW - 60 * DAY, SR._iso(NOW - 60 * DAY))})
    _run(monkeypatch, states, trigger="request", actor=SETTER, rotate=rot, run_id="t1",
         checks={"off_intent": lambda _l, h: "off its intent: 1 line" if h == "r3" else ""})
    card = SR.run_card("t1")
    groups = {r["name"]: r["group"] for r in card["card"]["rows"]}
    assert groups == {"r2": "done", "r1": "failed"}
    assert card["skipped"] == [{"device": "r3", "why": "skipped: off its intent: 1 line"}]
    from modules.nsot import capture_job
    monkeypatch.setattr(capture_job, "get", lambda job: {
        "state": "done", "payload": {"result": SR.runs()["rows"][-1]}})
    html = client.get("/v2/credentials/profiles/rotate-due/job/j1?run=t1").get_data(as_text=True)
    assert "data-run-stepper" in html and 'data-row="r2"' in html and 'data-row="r1"' in html
    assert "1 rotated, 1 skipped; r1 failed at verify_new_credential" in html
    assert "off its intent: 1 line" in html
