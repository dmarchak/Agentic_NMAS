"""C2465: `/health` reports `ready` only once Mercury can serve.

On the host on 2026-11-04 `/health` answered 0.1 s after a restart while the first AI chip took
36.6 s, the first Needs attention count 37.3 s and two `/v2/` 40.8 and 21.1 s, each waiting on
the first read of the 471 MB record of AI calls. The warm-up (`modules/warmup.py`) does that
work at start, and `/health`'s `ready` is false until every declared step has finished without
an error: a planted slow step keeps it false and names the step until it completes; a step
that raises keeps it false and names the step and its error, and the warm-up goes on to the
next; a process that never started the warm-up says so, never ready. `ok`, `commit`,
`started_at` and `pid` stay what `nmas-deploy` and the updater read.
"""
import ast
import os
import threading
import time

import pytest

from modules import warmup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The longest a test waits for the warm-up's thread to finish a step that is free to (a step
#: here does nothing: measured well under 0.1 s on the laptop; about 2.5x a second is ample).
DONE_BOUND_S = 2.5


@pytest.fixture
def fresh(monkeypatch):
    """No warm-up started in this process (each test starts its own)."""
    monkeypatch.setattr(warmup, "_run", None)


def _client():
    from app import app
    app.config["TESTING"] = True
    return app.test_client()


def _health():
    r = _client().get("/health")
    assert r.status_code == 200
    body = r.get_json()
    assert {"ready", "warming", "not_ready"} <= set(body), sorted(body)
    return body


def _until(pred):
    deadline = time.monotonic() + DONE_BOUND_S
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


def _step(rows, name):
    return next(r for r in rows if r["step"] == name)


class TestASlowStepKeepsReadinessFalse:
    def test_ready_only_once_the_step_completes(self, fresh):
        release, began = threading.Event(), threading.Event()

        def slow():
            began.set()
            assert release.wait(30)

        assert warmup.start(steps=[("planted-slow", "a planted slow step", slow)])
        assert began.wait(DONE_BOUND_S)
        h = _health()
        assert h["ready"] is False
        assert _step(h["warming"], "planted-slow")["state"] == "running"
        assert "planted-slow" in h["not_ready"]
        release.set()
        assert _until(lambda: warmup.status()["ready"])
        h = _health()
        assert h["ready"] is True and h["not_ready"] == ""
        row = _step(h["warming"], "planted-slow")
        assert row["state"] == "done" and row["error"] == ""
        assert row["started_at"] and row["ended_at"] and row["seconds"] >= 0

    def test_a_step_not_begun_is_not_ready_either(self, fresh):
        release = threading.Event()
        warmup.start(steps=[("first", "", lambda: release.wait(30)),
                            ("second", "", lambda: None)])
        assert _until(lambda: _step(warmup.status()["warming"], "first")["state"] == "running")
        s = warmup.status()
        assert s["ready"] is False
        assert _step(s["warming"], "second")["state"] == "waiting"
        release.set()
        assert _until(lambda: warmup.status()["ready"])


class TestAFailedStepIsNamedAndNotReady:
    def test_the_step_and_its_error_are_said_and_the_rest_still_runs(self, fresh):
        ran = []

        def broken():
            raise OSError("the planted step could not read its store")

        warmup.start(steps=[("planted-broken", "", broken),
                            ("after", "", lambda: ran.append("after"))])
        assert _until(lambda: _step(warmup.status()["warming"], "after")["state"] == "done")
        h = _health()
        assert h["ready"] is False
        row = _step(h["warming"], "planted-broken")
        assert row["state"] == "failed"
        assert row["error"] == "OSError: the planted step could not read its store"
        assert "planted-broken" in h["not_ready"] and "could not read its store" in h["not_ready"]
        assert ran == ["after"]

    def test_the_error_is_masked(self, fresh):
        def leaks():
            raise ValueError("username admin password 0 Planted-Not-A-Secret-77")

        warmup.start(steps=[("leaky", "", leaks)])
        assert _until(lambda: _step(warmup.status()["warming"], "leaky")["state"] == "failed")
        assert "Planted-Not-A-Secret-77" not in str(_health())


class TestNotStartedIsNotReady:
    def test_a_process_that_never_started_it_says_so(self, fresh):
        h = _health()
        assert h["ready"] is False and h["warming"] == []
        assert "not started" in h["not_ready"]

    def test_it_starts_once(self, fresh):
        assert warmup.start(steps=[("one", "", lambda: None)])
        assert not warmup.start(steps=[("two", "", lambda: None)])
        assert _until(lambda: warmup.status()["ready"])
        assert [r["step"] for r in warmup.status()["warming"]] == ["one"]


class TestWhatTheDeployReadsIsUnchanged:
    def test_ok_commit_started_at_and_pid(self, fresh):
        from routes import health as H
        h = _health()
        assert h["ok"] is (H._COMMIT is not None)
        assert h["commit"] == H._COMMIT
        assert h["started_at"] == H._iso_ms(H._STARTED)
        assert h["pid"] == os.getpid()


class TestTheDeclaredSteps:
    def test_they_warm_the_ai_record_and_needs_attention(self, fresh, monkeypatch):
        from modules import attention
        from modules.ai import calls
        seen = []
        monkeypatch.setattr(calls, "warm", lambda: seen.append("ai-calls"))
        monkeypatch.setattr(attention, "needs_attention_shared",
                            lambda: seen.append("needs-attention") or {})
        warmup.start(spawn=lambda target: target())
        assert seen == ["ai-calls", "needs-attention"]
        s = warmup.status()
        assert s["ready"] is True
        assert [r["step"] for r in s["warming"]] == [n for n, _w, _f in warmup.STEPS]

    def test_the_app_starts_it_when_served(self):
        """Structurally, as C36 keeps it: the start is inside `_start_background_daemons`
        (called only from `__main__`, tests/test_harness_isolation.py), never at import."""
        with open(os.path.join(ROOT, "app.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_start_background_daemons")
        inside = [ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)]
        assert any(c.endswith("warmup.start") for c in inside), inside
        top = [ast.unparse(n.value.func) for n in tree.body
               if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]
        assert not any("warmup" in c for c in top), top
