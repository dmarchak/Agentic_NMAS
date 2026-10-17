"""C1180: adopt and onboarding's Verify leave the list's repository CLEAN.

Both record the device's NetBox id in the manifest and then promote it (`verified_at`),
after their last golden commit. Nothing committed those two fields, so the repository was
left dirty, and the next operation needing a clean one (Retire: "no uncommitted changes
would ride into the commit") refused. Measured on the host in W4 (2026-10-17): the
manifest differed from HEAD by exactly s6's netbox_id and verified_at, written 4 s after
"adopt: s6 first capture".

Each operation runs end to end on a REAL git repository, with the device-facing parts
faked as its own tests fake them (`tests/test_adopt_apply.py`'s fake router,
`tests/test_onboard_phase_two.py`'s collaborators); the store, the manifest, the inventory
and the commits are the real ones.
"""

import json
import os
import subprocess

from modules.nsot import adopt as A
from tests.test_adopt_apply import HOST, _apply, _repo, lab          # noqa: F401
from tests.test_onboard_phase_two import _steps, world                    # noqa: F401


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True).stdout.strip()


def _manifest_at_head(repo, host):
    doc = json.loads(_git(repo, "show", "HEAD:.nsot/manifest.json"))
    found = [e for e in (doc.get("devices") or {}).values() if e.get("name") == host]
    assert len(found) == 1, (host, doc)
    return found[0]


def _assert_recorded(repo, host, *, actor, source):
    """Clean, and HEAD is the record: the manifest alone, by the person, from the
    operation, carrying both fields."""
    assert _git(repo, "status", "--porcelain") == "", (
        "the operation left the repository dirty:\n" + _git(repo, "status", "--porcelain"))
    body = _git(repo, "log", "-1", "--format=%B")
    assert body.splitlines()[0] == f"{source}: {host} verified and recorded in NetBox", body
    assert f"Actor: {actor}" in body.splitlines(), body
    assert f"Source: {source}" in body.splitlines(), body
    assert _git(repo, "show", "--name-only", "--format=", "HEAD").splitlines() == [
        ".nsot/manifest.json"]
    entry = _manifest_at_head(repo, host)
    assert entry.get("verified_at") and entry.get("netbox_id") == 7, entry


class TestAdoptLeavesItClean:
    def test_after_a_full_adoption_the_record_is_committed_by_who_adopted(self, lab):
        out = _apply(lab)
        assert out["ok"], out
        _assert_recorded(_repo(), HOST, actor="op@example.com", source="adopt")
        assert "recorded in commit" in out["steps"][-1]["detail"], out["steps"][-1]

    def test_a_commit_that_fails_is_said_and_undoes_nothing(self, lab, monkeypatch):
        from modules.nsot import repo as R
        monkeypatch.setattr(R, "_commit_paths", lambda *a, **k: {
            "ok": False, "error": "commit failed: planted"})
        out = _apply(lab)
        assert out["ok"] is False and out["state"] == "adopted", out
        promote = out["steps"][-1]
        assert promote["step"] == "promote" and promote["ok"] is False, promote
        assert "NOT committed" in out["reason"] and "planted" in out["reason"], out["reason"]
        from modules.nsot import manifest
        _i, entry = manifest.find_by_name(_repo(), HOST)
        assert entry["verified_at"], "the promotion is not undone"

    def test_the_steps_are_still_the_declared_ones(self, lab):
        out = _apply(lab)
        assert [s["step"] for s in out["steps"]] == list(A.APPLY_STEPS)


class TestVerifyLeavesItClean:
    def test_after_a_full_verify_the_record_is_committed_by_who_ran_it(self, world):
        from modules.nsot.onboard import run_phase_two
        out = run_phase_two(world["repo"], "bp1", "probe", actor="t", **_steps())
        assert out["ok"] is True, out
        _assert_recorded(world["repo"], "bp1", actor="t", source="onboarding")

    def test_a_commit_that_fails_is_said_and_undoes_nothing(self, world, monkeypatch):
        from modules.nsot import repo as R
        from modules.nsot.onboard import run_phase_two
        monkeypatch.setattr(R, "_commit_paths", lambda *a, **k: {
            "ok": False, "error": "commit failed: planted"})
        out = run_phase_two(world["repo"], "bp1", "probe", actor="t", **_steps())
        assert out["ok"] is False and out["promoted"] is True, out
        assert out["steps"][-1]["ok"] is False and out["stopped_at"] == "promote", out
        assert "NOT committed" in out["reason"] and "planted" in out["reason"], out["reason"]

    def test_a_run_that_changes_no_manifest_makes_no_extra_commit(self, world):
        """The control: no NetBox id and a promotion that writes nothing leave the
        manifest as the golden's commit left it, so the golden's commit is still HEAD."""
        from modules.nsot.onboard import run_phase_two
        out = run_phase_two(world["repo"], "bp1", "probe", actor="t", **_steps(
            netbox=lambda *a, **k: {"ok": True, "created": [], "device_id": None},
            promote=lambda *a, **k: {"ok": True}))
        assert out["ok"] is True, out
        assert _git(world["repo"], "log", "-1", "--format=%s") == "onboarding: bp1 first capture"
        assert out["record_commit"] == {"ok": True, "commit": "", "error": ""}
        assert _git(world["repo"], "status", "--porcelain") == ""


class TestTheHelper:
    def test_an_unchanged_manifest_is_not_committed(self, world):
        from modules.nsot import onboard
        from modules.nsot.onboard import run_phase_two
        run_phase_two(world["repo"], "bp1", "probe", actor="t", **_steps())
        head = _git(world["repo"], "rev-parse", "HEAD")
        # Someone else's edit elsewhere in the repository: not the manifest's change, so
        # neither a commit nor a failure, and it stays where it is, uncommitted.
        planted = os.path.join(world["repo"], "host_vars", "other.yml")
        with open(planted, "w", encoding="utf-8") as fh:
            fh.write("hostname: other\n")
        got = onboard.commit_record("probe", "bp1", "t", source="onboarding")
        assert got == {"ok": True, "commit": "", "error": ""}
        assert _git(world["repo"], "rev-parse", "HEAD") == head
        assert _git(world["repo"], "status", "--porcelain", "-uall") == "?? host_vars/other.yml"
