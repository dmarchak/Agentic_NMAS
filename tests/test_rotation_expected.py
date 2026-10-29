"""C2158: the rotation schedule says when the TIMER would rotate a device, beside when it
falls due (`scheduled_rotation.expected`), on Credentials › Profiles and the device page.

**The case is the register's own** (C2158, read by the afternoon run's read-only rotations check
on 2026-10-29 at 00:30 UTC): r6 last rotated 2026-10-21T23:59:21Z and r7 2026-10-22T00:23:28Z
under a 7-day policy, so due 2026-10-28T23:59:21Z and 2026-10-29T00:23:28Z; the policy's last
scheduled run started at about 01:10 on 2026-10-28 (the week's passes started 00:59 to 01:10
UTC; the row says no run row since 01:16), so the timer's next pass is about 01:10 on 10-29.
The run's start is that minute (its seconds were not in the register: a captured runs-record
row is owed). A no-change hold planned on the due times missed the rotations: the schedule now
names the pass.

- **The estimate** follows the timer's own rules: a policy's scheduled run starts at most once
  in any 24 hours after its last one that ran, inside its preferred window and no no-change
  window, at most its limit a run oldest first; a device never rotated or due with no run
  recorded is the timer's next tick; a stopped timer rotates nothing, said.
- **It agrees with the timer**: `tick` at the estimate takes the device, and a minute before
  it does not (the expectation comes from the timer's code, not the estimate's).
- **The screens**: Credentials › Profiles draws the estimate in its own column, the basis on
  hover; the device page's Credential line says it, naming where the basis is.

No address is involved (times and device names only), so the IPv4/IPv6 parity rule has no
case here.
"""

import calendar
import time

import pytest

from modules.nsot import scheduled_rotation as SR

DAY = 86400


def _at(text: str) -> float:
    return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ"))


#: The register's reading (C2158).
NOW = _at("2026-10-29T00:30:00Z")
ROTATED = {"r6": "2026-10-21T23:59:21Z", "r7": "2026-10-22T00:23:28Z"}
LAST_RUN = {"trigger": "scheduled", "state": "done", "policies": ["default"],
            "started": "2026-10-28T01:10:00Z", "finished": "2026-10-28T01:16:00Z"}
PASS = "2026-10-29T01:10:00Z"


def _policy(days=7, start=0, end=24, most=None):
    return {"state": "on", "days": days, "window_start": start, "window_end": end,
            "max_per_run": most, "set_by": "alice@example.invalid",
            "set_at": "2026-10-01T00:00:00Z", "verified": "access"}


def _states(now=NOW, pol=None, rotated=None, devices=("r6", "r7")):
    rotated = ROTATED if rotated is None else rotated
    return SR.device_states(
        now, lists=["Lab"], devices_of=lambda _l: [{"hostname": d, "role": "router"}
                                                   for d in devices],
        rotations={d: (_at(t), t) for d, t in rotated.items()},
        pols={"default": pol or _policy()}, profile_names={"default"})


def _by_device(rows):
    return {s["device"]: s for s in rows}


def test_the_registers_case_names_the_pass_not_the_due_time():
    states = _states()
    assert [s["due_at"] for s in states] == ["2026-10-28T23:59:21Z", "2026-10-29T00:23:28Z"]
    got = _by_device(SR.expected(states, NOW, rows=[LAST_RUN], windows=[]))
    for d in ("r6", "r7"):
        assert got[d]["expected_at"] == PASS, got[d]
        assert got[d]["expected_words"] == (
            f"the timer rotates it at about {PASS}, an estimate (up to 5 min later)")
        assert got[d]["expected_basis"] == (
            "default's policy runs on the timer at most once in any 24 hours, its last "
            "scheduled run having started 2026-10-28T01:10:00Z; the timer starts it at its "
            "next tick, up to 5 min later, and a run rotates its devices one after another")


def test_it_agrees_with_the_timer(monkeypatch):
    """`tick` (the timer's own code) at the estimate starts the run that takes r6 and r7, and
    a minute before it starts none."""
    ran = []
    monkeypatch.setattr(SR, "run", lambda **kw: ran.append(kw["now"]) or {"state": "done"})
    monkeypatch.setattr(SR, "policies", lambda: {"default": _policy()})
    monkeypatch.setattr(SR, "runs", lambda: {"rows": [LAST_RUN]})
    monkeypatch.setattr(SR, "in_no_change_window", lambda now=None: None)
    got = _by_device(SR.expected(_states(), NOW, rows=[LAST_RUN], windows=[]))
    at = SR._epoch(got["r6"]["expected_at"])
    at_states = {t: _states(t) for t in (at - 60, at)}       # read before the seam is planted
    monkeypatch.setattr(SR, "device_states", lambda now=None, **_k: at_states[now])
    assert SR.tick(at - 60)["state"] == "idle" and ran == []
    SR.tick(at)
    assert ran == [at]
    chosen, _w = SR.select(at_states[at], at, scheduled=True)
    assert {s["device"] for s in chosen} == {"r6", "r7"}


def test_due_later_with_the_last_run_long_past_is_its_due_time():
    rotated = {"r6": "2026-10-25T10:00:00Z", "r7": "2026-10-25T10:00:00Z"}
    got = _by_device(SR.expected(_states(rotated=rotated), NOW, rows=[LAST_RUN], windows=[]))
    assert got["r6"]["expected_at"] == "2026-11-01T10:00:00Z"


def test_never_rotated_and_no_run_recorded_is_the_next_tick():
    got = _by_device(SR.expected(_states(rotated={"r6": ROTATED["r6"]}), NOW, rows=[],
                                 windows=[]))
    assert got["r7"]["never"] and got["r7"]["expected_at"] == SR._iso(NOW)
    assert got["r6"]["expected_at"] == SR._iso(NOW), "due, and no scheduled run recorded"
    assert "no scheduled run of it is recorded" in got["r6"]["expected_basis"]


def test_the_preferred_window_moves_it_to_the_windows_start():
    pol = _policy(start=2, end=4)
    got = _by_device(SR.expected(_states(pol=pol), NOW, rows=[LAST_RUN], windows=[]))
    assert got["r6"]["expected_at"] == "2026-10-29T02:00:00Z"
    assert "inside its preferred window (" in got["r6"]["expected_basis"]


def test_a_no_change_window_moves_it_to_the_windows_end():
    window = {"start": "01:00", "end": "01:45", "reason": "a nightly backup"}
    got = _by_device(SR.expected(_states(), NOW, rows=[LAST_RUN], windows=[window]))
    assert got["r6"]["expected_at"] == "2026-10-29T01:45:00Z"
    assert ("outside the no-change window 01:00 to 01:45 UTC (a nightly backup)"
            in got["r6"]["expected_basis"])


def test_the_limit_leaves_the_newest_for_a_later_pass():
    rotated = dict(ROTATED, r8="2026-10-22T00:25:00Z")
    states = _states(pol=_policy(most=2), rotated=rotated, devices=("r6", "r7", "r8"))
    got = _by_device(SR.expected(states, NOW, rows=[LAST_RUN], windows=[]))
    assert [got[d]["expected_at"] for d in ("r6", "r7", "r8")] == [
        PASS, PASS, "2026-10-30T01:10:00Z"]
    assert "at most 2 a run, oldest first" in got["r8"]["expected_basis"]
    # One device alone (its page) does not judge the limit, and says so.
    (one,) = SR.expected([_by_device(states)["r8"]], NOW, rows=[LAST_RUN], windows=[],
                         whole=False)
    assert one["expected_at"] == PASS
    assert "the devices ahead of this one not counted here" in one["expected_basis"]


def test_a_stopped_timer_rotates_nothing_and_says_so(monkeypatch):
    monkeypatch.setattr(SR, "halted", lambda rows=None: {"failed": {"device": "r6"}})
    got = _by_device(SR.expected(_states(), NOW, rows=[LAST_RUN], windows=[]))
    assert got["r6"]["expected_at"] == ""
    assert got["r6"]["expected_words"].startswith("the timer rotates nothing while it is stopped")


def test_a_device_with_no_policy_on_has_no_estimate():
    states = SR.device_states(NOW, lists=["Lab"], devices_of=lambda _l: [{"hostname": "r6"}],
                              rotations={}, pols={}, profile_names=set())
    (got,) = SR.expected(states, NOW, rows=[], windows=[])
    assert (got["expected_at"], got["expected_words"]) == ("", "")


# ---------------------------------------------------------------------------- the screens

@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.config.USER_SETTINGS_FILE", str(tmp_path / "user_settings.json"))
    monkeypatch.setattr("modules.credentials._FILE", str(tmp_path / "credential_profiles.json"))
    return tmp_path


def test_the_profiles_page_draws_it_in_its_own_column(data, monkeypatch):
    import html as _h
    import re

    from modules import credentials
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    (data / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(data / "lab"))
    credentials.save_profile("default", username="netops", password="Prof-Pass-5531")
    states = _states(NOW)
    monkeypatch.setattr(SR, "device_states", lambda now=None, **_k: states)
    monkeypatch.setattr(SR, "policies", lambda: {"default": _policy()})
    monkeypatch.setattr(SR, "runs", lambda: {"state": "ok", "rows": [LAST_RUN], "error": ""})
    monkeypatch.setattr(SR, "_now", lambda now=None: NOW if now is None else float(now))
    import app as A
    body = A.app.test_client().get("/v2/credentials/profiles?list=Lab").get_data(as_text=True)
    assert "<th scope=\"col\">The timer rotates it</th>" in body
    cell = re.search(r'<td data-rotation-expected="r6"[^>]*>.*?</td>', body, re.S)
    assert cell, "the r6 row's estimate cell is drawn"
    words = " ".join(_h.unescape(re.sub(r"<[^>]+>", " ", cell.group(0))).split())
    assert words == f"about {PASS} (estimate)"
    title = _h.unescape(re.search(r'title="([^"]*)"', cell.group(0)).group(1))
    assert title.startswith("an estimate: default's policy runs on the timer at most once")


def test_the_device_page_line_says_it(monkeypatch):
    """The device page's Credential line (`device_page`'s checks), the one device's own
    estimate, naming where its basis is."""
    from modules import device_page
    s = _by_device(_states())["r6"]
    monkeypatch.setattr(SR, "device_state", lambda list_name, dev, now=None: dict(s))
    monkeypatch.setattr(SR, "runs", lambda: {"rows": [LAST_RUN]})
    monkeypatch.setattr("modules.change_windows.windows", lambda: [])
    monkeypatch.setattr(SR, "_now", lambda now=None: NOW if now is None else float(now))
    line = device_page.credential_check("Lab", {"hostname": "r6"})
    assert line["text"].endswith(
        f"; the timer rotates it at about {PASS}, an estimate (up to 5 min later), from the "
        "timer's rules (its basis on Credentials › Profiles)"), line["text"]
