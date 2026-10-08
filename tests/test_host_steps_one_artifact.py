"""One artifact, one host-step row; a step is checked by what IT did (C442, C443; 2026-10-04).

The operator, after installing the Oxidized helper: three AFTER steps checked by
`[oxidized-cred]` (487b1da, b8f872c, 3d88cbe) were three Needs attention rows, all cleared by
one install, because rows were folded only when their WORDS matched. And 487b1da's step, the
helper's pin (`/etc/nmas/oxidized-cred.conf`), done hours earlier, reappeared as not done:
its trailer names `[oxidized-cred]`, the helper's HASH, which every helper release changes.

Now a checked step is folded by its check, the newest step's words leading and the older ones
superseded by it; and 487b1da's check is corrected to the pin's own (owner, mode, content),
since a pushed trailer is never rewritten. The three commits' REAL trailers, read from git.
"""

import json
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIN_STEP = "487b1dafcd189b48ecff0121272ec591cfff09b0"
REINSTALLS = ("b8f872c", "3d88cbe")


def _text():
    out = subprocess.run(["git", "-C", ROOT, "log", "--no-walk", "--format=%H%x1f%B%x1e",
                          REINSTALLS[1], REINSTALLS[0], PIN_STEP],
                         capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip(f"this checkout lacks the three commits: {out.stderr.strip()[:120]}")
    return out.stdout


def _full(short):
    return subprocess.run(["git", "-C", ROOT, "rev-parse", short], capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A tool with Oxidized configured, its router.db setting, and the helper's pin written
    as a host step writes it (root-owned is stood in for: a test cannot chown)."""
    from modules import config, host_steps

    monkeypatch.setattr(host_steps, "DONE", str(tmp_path / "done.jsonl"))
    settings = tmp_path / "user_settings.json"
    settings.write_text(json.dumps({"oxidized_url": "http://192.0.2.40:8888",
                                    "oxidized_router_db": str(tmp_path / "router.db")}),
                        encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(settings))
    pin = tmp_path / "oxidized-cred.conf"
    pin.write_text(f"{tmp_path / 'router.db'}\n", encoding="utf-8")
    os.chmod(pin, 0o644)
    real = os.lstat

    def lstat(p, *a, **k):
        st = real(p, *a, **k)
        if str(p) != str(pin):
            return st
        fields = list(st)
        fields[4] = 0                                   # st_uid: root's
        return os.stat_result(fields)
    monkeypatch.setattr(os, "lstat", lstat)
    # A NEW helper release: the installed copy is not this release's.
    monkeypatch.setitem(host_steps.CHECKS, "oxidized-cred",
                        lambda root: {"state": "not_done", "detail": "the installed helper "
                                      "differs (installed d03532c08b0a, this release 355818515ba5)"})
    return {"pin": pin, "tmp": tmp_path}


class TestOneArtifactOneRow:
    def test_the_helpers_re_installs_are_one_row_led_by_the_newest(self, world):
        from modules import host_steps

        steps = host_steps.owed(_full(REINSTALLS[1]), log_text=_text())["steps"]
        assert len(steps) == 1, [(s["check"], s["shas"]) for s in steps]
        (s,) = steps
        assert s["check"] == "oxidized-cred"
        assert s["shas"] == [_full(REINSTALLS[0]), _full(REINSTALLS[1])]     # oldest first
        assert s["sha"] == _full(REINSTALLS[1]) and "LOCK_WAIT_S = 5.0" in s["step"]
        assert s["superseded"] == [_full(REINSTALLS[0])]

    def test_needs_attention_draws_one_row_naming_its_commits(self, world, monkeypatch):
        from modules import attention, host_steps
        from routes import health

        text = _text()
        monkeypatch.setattr(host_steps, "_log", lambda root, rng, limit, run=None: text)
        monkeypatch.setattr(health, "_COMMIT", _full(REINSTALLS[1]))
        (r,) = attention.host_steps_source()["rows"]
        assert f"{REINSTALLS[0]}" in r["what"] and f"{REINSTALLS[1]}" in r["what"]
        assert "487b1dafcd" not in r["what"]
        assert f"It supersedes the step of {_full(REINSTALLS[0])[:10]}" in r["cause"]

    def test_unchecked_steps_are_still_folded_by_their_words_alone(self, world):
        from modules import host_steps

        text = "".join(f"{sha}\x1fx\n\nHost-Step-After: {words}\n\x1e"
                       for sha, words in (("b" * 40, "tell the team"),
                                          ("a" * 40, "tell the other team")))
        assert len(host_steps.owed("b" * 40, log_text=text)["steps"]) == 2


class TestAStepIsCheckedByWhatItDid:
    def test_a_new_helper_release_leaves_the_pin_step_done(self, world):
        from modules import host_steps

        got = host_steps.owed(_full(REINSTALLS[1]), log_text=_text())
        owed = [sha for s in got["steps"] for sha in s["shas"]]
        assert PIN_STEP not in owed, "the pin step reopened by a new helper release"
        (pin,) = [s for s in host_steps.steps_in(_text(), when="after") if s["sha"] == PIN_STEP]
        assert pin["check"] == "oxidized-pin" and "pinned the helper" in pin["check_corrected"]
        assert host_steps.check(pin)["state"] == "done"

    def test_with_oxidized_retired_the_pin_step_is_done_whatever_it_names(self, world):
        """Phase 3 step 2 (2026-10-08): nothing runs the helper, so its pin owes nothing."""
        from modules import host_steps

        world["pin"].write_text("/srv/elsewhere/router.db\n", encoding="utf-8")
        steps = host_steps.owed(_full(REINSTALLS[1]), log_text=_text())["steps"]
        assert [s for s in steps if s["check"] == "oxidized-pin"] == [], "done: not owed"
        got = host_steps.check({"check": "oxidized-pin"})
        assert got["state"] == "done" and "Oxidized is retired" in got["detail"]

    def test_no_oxidized_configured_has_nothing_to_pin(self, world):
        from modules import host_steps

        (world["tmp"] / "user_settings.json").write_text("{}", encoding="utf-8")
        world["pin"].unlink()
        assert host_steps.check_oxidized_pin()["state"] == "done"
