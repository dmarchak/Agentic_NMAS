"""C98: one operation per device at a time, refused by name, never queued.

The confirm-by-hash guarantee assumed one mover. On 2026-09-27 a restore
and a deploy ran on r2 at once, both confirmed, and the deploy's check
passed against a stored config the restore was mid-way through rewriting.
Every path that changes a device, or the record of one, now holds the device
from apply to commit, across processes (a `flock` the kernel releases when
its holder dies), and a second operation is refused with the holder named.
"""

from tests.test_capture import run_capture_preview
import ast
import os
import re
import subprocess
import sys
import threading
import time

import pytest

from modules.nsot import device_ops as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def no_hold_survives_a_test():
    """A hold a failing test leaves behind would refuse every later test on
    that device, which reads as those tests failing (measured: a control
    made one test fail and two more followed)."""
    yield
    with D._mu:
        stale = list(D._held.items())
        D._held.clear()
    for _key, info in stale:
        if info["fd"] is not None:
            os.close(info["fd"])


class Holder:
    """Holds a device from ANOTHER thread, as a concurrent request would."""

    def __init__(self, list_name, host, operation="restore", actor="operator@example.com",
                 detail="re-apply baseline/20260925T201032Z"):
        self.args = (list_name, host, operation, actor, detail)
        self.held, self.done = threading.Event(), threading.Event()
        self.t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        with D.hold(*self.args):
            self.held.set()
            self.done.wait(10)

    def __enter__(self):
        self.t.start()
        assert self.held.wait(5)
        return self

    def __exit__(self, *exc):
        self.done.set()
        self.t.join(5)


class TestTheLock:
    def test_a_second_operation_is_refused_naming_the_holder(self):
        with Holder("Lab", "r2"):
            with pytest.raises(D.DeviceBusy) as exc:
                D.acquire("Lab", "r2", "deploy", "someone@example.invalid")
        msg = str(exc.value)
        assert re.match(r"r2 is being restored by operator@example\.com, started "
                        r"\d\d:\d\d:\d\d UTC \(re-apply baseline/20260925T201032Z\)", msg), msg
        assert "refused, not queued" in msg and "nothing was sent" in msg

    def test_it_is_free_again_when_the_holder_finishes(self):
        with Holder("Lab", "r2"):
            pass
        D.acquire("Lab", "r2", "deploy", "a")
        D.release("Lab", "r2")

    def test_the_holding_thread_may_nest(self):
        """Onboarding's phase two rotates inside its own hold."""
        with D.hold("Lab", "r2", "onboard", "a"):
            with D.hold("Lab", "r2", "rotate", "a"):
                assert D.holder("Lab", "r2")["operation"] == "onboard"
        assert D.holder("Lab", "r2") is None

    def test_another_device_is_unaffected(self):
        with Holder("Lab", "r2"):
            with D.hold("Lab", "r1", "deploy", "a"):
                pass

    def test_asking_who_holds_it_creates_nothing(self):
        from modules import config

        D.holder("Nowhere", "r9")
        assert not os.path.exists(os.path.join(config.DATA_DIR, "device_ops", "nowhere"))

    def test_another_process_holds_it_and_its_death_releases_it(self):
        """The CLIs change devices from their own process; the kernel releases
        a flock when its holder dies, so a crash cannot lock a device for ever."""
        pytest.importorskip("fcntl")
        code = ("import sys, time\n"
                f"sys.path.insert(0, {ROOT!r})\n"
                "from modules.nsot import device_ops as D\n"
                "D.acquire('Lab', 'r2', 'rotate', 'operator (host shell)')\n"
                "print('held', flush=True)\n"
                "time.sleep(30)\n")
        child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE,
                                 text=True, env=dict(os.environ))
        try:
            assert child.stdout.readline().strip() == "held"
            with pytest.raises(D.DeviceBusy) as exc:
                D.acquire("Lab", "r2", "deploy", "a")
            assert "r2 is being rotated by operator (host shell)" in str(exc.value)
        finally:
            child.kill()
            child.wait(5)
        D.acquire("Lab", "r2", "deploy", "a")          # the kernel let go
        D.release("Lab", "r2")


def _spy_pipeline(monkeypatch):
    import routes.deploy as rd

    ran = []
    real = rd._deploy_one

    def spy(entry, *a, **k):
        ran.append(entry["artifact"].device)
        return real(entry, *a, **k)
    monkeypatch.setattr(rd, "_deploy_one", spy)
    return ran


class TestEveryChangingPathHoldsIt:
    def test_a_deploy_of_a_held_device_is_refused_and_nothing_runs(self, monkeypatch):
        from tests import payload_providers as P
        from tests.test_previews_mask_secrets import _deploy_plan

        plan, _i, _c = _deploy_plan(monkeypatch)
        device = plan["devices"][0]
        ran = _spy_pipeline(monkeypatch)
        with Holder("Default", "s4"):
            body = P._client().post("/deploy/apply", json={
                "confirmations": {"s4": device["capture_hash"]},
                "command_hashes": {"s4": device["command_hash"]},
                "authorise": {"s4": [{"line": "shutdown", "reason": "planned maintenance, port unused"}]}}).get_json()
        assert ran == []
        row = next(r for r in body["results"] if r["device"] == "s4")
        assert row["outcome"] == "refused"
        assert "s4 is being restored by operator@example.com" in row["reason"]
        assert D.holder("Default", "s4") is None

    def test_a_restore_of_a_held_device_is_refused_and_released_after(self, monkeypatch):
        import routes.deploy as rd
        from tests.test_p3_restore_is_guarded import _target

        ran = _spy_pipeline(monkeypatch)
        target = _target("r1", target_config="hostname r1\nlogging buffered 4096\n",
                         captured="hostname r1\n")
        from routes.deploy import _capture_hash
        with Holder("Lab", "r1", operation="deploy", actor="other@example.invalid",
                    detail=""):
            report = rd.run_targets("Lab", [target],
                                    {"confirmations": {"r1": _capture_hash("hostname r1\n")}},
                                    label="re-apply X", source_ref="X")
        assert ran == []
        row = next(r for r in report["results"] if r["device"] == "r1")
        assert row["outcome"] == "refused" and "r1 is being deployed to by other@" in row["reason"]
        assert D.holder("Lab", "r1") is None

    def test_a_capture_of_a_held_device_is_refused_and_records_nothing(self, tmp_path,
                                                                     monkeypatch):
        import subprocess as sp

        from tests.test_capture import _hash, build_capture_lab

        lab = build_capture_lab(monkeypatch, tmp_path)
        h = _hash(run_capture_preview(lab["client"], {"devices": ["r2"]}).get_json())
        before = sp.run(["git", "-C", lab["repo"], "rev-parse", "HEAD"],
                        capture_output=True, text=True).stdout
        with Holder("Lab", "r2"):
            d = lab["client"].post("/golden/capture/apply",
                                   json={"confirmations": {"r2": h}}).get_json()
        target = d["result"]["happened"]["targets"][0]
        assert target["outcome"] == "busy", target
        assert sp.run(["git", "-C", lab["repo"], "rev-parse", "HEAD"],
                      capture_output=True, text=True).stdout == before

    def test_a_rotation_of_a_held_device_is_refused_before_anything(self, monkeypatch):
        from modules.nsot import credential_rotation as cr

        called = []
        monkeypatch.setattr(cr, "_rotate", lambda *a, **k: called.append(1) or {})
        monkeypatch.setattr(cr, "record_outcome", lambda *a, **k: None)
        with Holder("Lab", "r2", operation="deploy", actor="other@example.invalid", detail=""):
            out = cr.rotate("Lab", "r2", confirmed_fingerprint="x", actor="me")
        assert called == [] and out["state"] == cr.NOT_STARTED
        assert "r2 is being deployed to by other@example.invalid" in out["reason"]

    def test_onboarding_phase_two_of_a_held_device_is_refused_before_any_step(self):
        from modules.nsot import onboard

        reached = []
        with Holder("Lab", "r9", operation="deploy", actor="other@example.invalid", detail=""):
            out = onboard.run_phase_two("/nonexistent", "r9", "Lab", actor="me",
                                        reach=lambda *a, **k: reached.append(1))
        assert reached == [] and out["ok"] is False
        assert "r9 is being deployed to by other@example.invalid" in out["reason"]
        assert {s["detail"] for s in out["steps"]} == {"did not run"}

    def test_a_retirement_of_a_held_device_is_refused(self):
        from modules.nsot import retire

        with Holder("Lab", "r5"):
            out = retire.apply("Lab", "r5", reason="x", actor="me", confirmed_hash="h")
        assert out["ok"] is False and "r5 is being restored by" in out["error"]

    def test_the_lock_is_released_when_the_batch_raises(self, monkeypatch):
        import routes.deploy as rd
        from routes.deploy import _capture_hash
        from tests.test_p3_restore_is_guarded import _target

        monkeypatch.setattr("modules.nsot.deploy.run_batch", lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("the batch broke")))
        target = _target("r1", target_config="hostname r1\nlogging buffered 4096\n",
                         captured="hostname r1\n")
        with pytest.raises(RuntimeError):
            rd.run_targets("Lab", [target],
                           {"confirmations": {"r1": _capture_hash("hostname r1\n")}})
        assert D.holder("Lab", "r1") is None


#: Where the lock is taken, by function. Since C101 the rule is enforced
#: where the write HAPPENS (`connection._guard_writes`), so a new path that
#: writes to a device and forgets fails on first use; this list pins the
#: paths that change the RECORD of a device (capture, retirement) as well,
#: which no session guard can see.
HOLDERS = {
    # `apply_batch` is THE apply (/deploy/apply and the v2 batch confirm, P.9 d2).
    "routes/deploy.py": ("apply_batch", "run_targets"),
    # `apply_captures` is THE capture apply (/golden/capture/apply and the v2 device page).
    "routes/golden.py": ("apply_captures",),
    "modules/nsot/credential_rotation.py": ("rotate", "persist"),
    "modules/nsot/persist_op.py": ("apply",),
    "modules/nsot/rotate_op.py": ("run",),
    "modules/nsot/onboard.py": ("_holds_the_device",),
    "modules/nsot/retire.py": ("_holds_the_device",),
    "scripts/nmas-persist-native": ("run",),
}


def test_each_changing_path_takes_the_lock():
    missing = []
    for rel, funcs in HOLDERS.items():
        tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
        defs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for f in funcs:
            src = ast.unparse(defs[f]) if f in defs else ""
            if "device_ops" not in src:
                missing.append(f"{rel}:{f}")
    assert missing == []
    tree = ast.parse(open(os.path.join(ROOT, "modules/nsot/onboard.py"), encoding="utf-8").read())
    decorated = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                 and any(getattr(d, "id", "") == "_holds_the_device" for d in n.decorator_list)]
    assert decorated == ["run_phase_two"]
