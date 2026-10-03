"""An operation cut off by a process exit (CONCURRENCY_AUDIT R5).

Receipts and the golden commit are written after a whole batch, so a process that ends in
the middle (a restart, an update, a crash) leaves the devices already pushed with no
receipt, no golden and no rollback, and the kernel releases every hold, so nothing says it
happened. Two routes ended the process outright with no check at all, and Update and
`nmas-deploy` restarted whatever was running.

Measured here, with REAL holds (a child process that holds devices and dies):

- `/ai/restart` and `/server/restart` are gone (404) and in no table;
- every hold in every list, by any process, is seen (`held_anywhere`);
- the Update preview refuses while any device is held, naming each, and passes once it is
  released; a request is refused; a waiting update keeps waiting while one runs, and is
  released when nothing does;
- `/health/operations` lists the holds and never who holds them;
- `nmas-deploy` refuses (exit 10) naming each, with the checkout NOT moved and no restart;
  when the service cannot say, it continues and says so; its own reader of the route reads
  busy, clear, a version that predates it (404) and a service not answering;
- a hold left by a process that died is an interrupted operation: listed with its operation,
  who started it and its last step; kept in `interrupted.jsonl` (0600) when the next
  operation takes the device, listed once; one Needs attention row per interrupted process
  naming its devices and step, acknowledged per event; a later interruption is a new row.
"""

import http.server
import json
import os
import stat
import subprocess
import sys
import threading

import pytest

from tests.test_nmas_deploy import _head, _run, _run_entry, world  # noqa: F401
from tests.test_update_button import _plan_kw
from tests.test_update_when_ci_passes import VERIFIED, _defer, _kw, store  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = "R5lab"


@pytest.fixture
def ops():
    from modules.nsot import device_ops as D
    yield D
    for host in ("r1", "r2", "r3"):
        while D.holder(LIST, host) and D._held.get((LIST.lower(), host)):
            D.release(LIST, host)


def _die_holding(tmp_path, devices, step="push", operation="deploy"):
    """A child process holds *devices*, records *step*, and ends WITHOUT releasing them:
    the process exit a restart or a crash is."""
    from modules import config

    pytest.importorskip("fcntl")
    script = tmp_path / "die_holding.py"
    script.write_text(
        "import os, sys\n"
        f"sys.path.insert(0, {ROOT!r})\n"
        "from modules.nsot import device_ops as D\n"
        f"for host in {list(devices)!r}:\n"
        f"    D.acquire({LIST!r}, host, {operation!r}, 'person@example.invalid')\n"
        f"D.note({step!r})\n"
        "print(os.getpid(), flush=True)\n"
        "os._exit(0)\n", encoding="utf-8")
    out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                         env=dict(os.environ, NMAS_DATA_DIR=config.DATA_DIR), timeout=60)
    assert out.returncode == 0, out.stderr
    return int(out.stdout.strip())


class TestTheRestartRoutesAreGone:
    def test_both_answer_404_and_no_table_names_them(self):
        import app as nmas
        from modules import invalidation, route_gates

        client = nmas.app.test_client()
        for path in ("/ai/restart", "/server/restart"):
            assert client.post(path).status_code == 404, path
        for name in ("ai_restart", "server_restart"):
            assert name not in route_gates.GATES and name not in invalidation.DECLARED


class TestEveryHoldIsSeen:
    def test_holds_in_two_lists_are_both_listed(self, ops):
        ops.acquire(LIST, "r1", "deploy", "a@example.invalid")
        ops.acquire("R5other", "r9", "capture", "b@example.invalid")
        try:
            got = {(h["list"].lower(), h["device"]) for h in ops.held_anywhere()}
            assert {(LIST.lower(), "r1"), ("r5other", "r9")} <= got
        finally:
            ops.release(LIST, "r1")
            ops.release("R5other", "r9")
        assert not any(h["device"] in ("r1", "r9") for h in ops.held_anywhere())


class TestTheUpdateWaitsForOperations:
    def _plan(self, **over):
        from modules import update_op
        kw = _plan_kw()
        kw.pop("operations")
        kw.update(over)
        return update_op.plan(**kw)

    def test_a_held_device_refuses_naming_it_and_its_release_passes(self, ops):
        from modules import update_op

        ops.acquire(LIST, "r1", "restore", "a@example.invalid")
        try:
            p = self._plan()
            gate = next(g for g in p["gates"] if g["name"] == update_op.OPERATIONS_GATE)
            assert gate["state"] == "fail" and not p["selectable"]
            assert "r1 (restore by a@example.invalid" in gate["detail"]
            assert "half-applied" in gate["detail"]
            refused = update_op.request(p["hash"], [], "person@example.invalid",
                                        **{k: v for k, v in _plan_kw().items()
                                           if k != "operations"})
            assert refused["ok"] is False and "r1" in refused["reason"]
        finally:
            ops.release(LIST, "r1")
        assert self._plan()["selectable"]

    def test_a_waiting_update_keeps_waiting_while_one_runs(self, store):
        from modules import update_op

        _defer()
        held = [{"list": LIST, "device": "r1", "operation": "deploy", "actor": "a",
                 "started": 1}]
        assert update_op.release_deferred(**dict(_kw(ci=VERIFIED), operations=held)) is None
        assert update_op.deferred()["target"] == "b" * 40          # still waiting
        assert not (store / "requests").exists() or os.listdir(store / "requests") == []
        ended = update_op.release_deferred(**_kw(ci=VERIFIED))      # nothing held now
        assert ended["outcome"] == "requested"


class TestHealthOperations:
    def test_it_lists_the_holds_and_never_who(self, ops):
        import app as nmas

        ops.acquire(LIST, "r2", "rotate", "secret-person@example.invalid")
        try:
            body = nmas.app.test_client().get("/health/operations").get_json()
        finally:
            ops.release(LIST, "r2")
        mine = [o for o in body["operations"] if o["device"] == "r2"]
        assert body["ok"] is True and mine and mine[0]["operation"] == "rotate"
        assert "secret-person" not in json.dumps(body)


class TestNmasDeployWaitsForOperations:
    BUSY = ("busy", [{"list": LIST, "device": "r3", "operation": "deploy", "pid": 4242,
                      "since": "2026-10-02T12:00:00.000Z"}])

    def test_a_held_device_refuses_with_nothing_moved(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, restarted, _ = _run(world, {sha: _run_entry(sha)},
                                  operations=lambda: self.BUSY)
        err = capsys.readouterr().err
        assert code == 10 and _head(world) == world.base and not restarted
        assert "NOT DEPLOYED" in err and "r3 (deploy since 2026-10-02T12:00:00.000Z" in err
        assert "The checkout was NOT moved" in err

    def test_a_service_that_cannot_say_does_not_stop_the_deploy(self, world, capsys):
        sha = world.advance({"app.py": "v = 2\n"})
        code, restarted, _ = _run(world, {sha: _run_entry(sha)},
                                  operations=lambda: ("unknown", "the service is not answering"))
        assert code == 0 and _head(world) == sha and restarted
        assert "Could not ask the service" in capsys.readouterr().out

    @pytest.mark.parametrize("status,body,expect", [
        (200, {"ok": True, "operations": [{"device": "r1"}]}, "busy"),
        (200, {"ok": True, "operations": []}, "clear"),
        (404, None, "unknown"),
    ], ids=["busy", "clear", "predates"])
    def test_its_reader_of_the_route(self, monkeypatch, status, body, expect):
        from tests.test_nmas_deploy import _script

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body or {}).encode())

            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            monkeypatch.setenv("NMAS_OPERATIONS_URL",
                               f"http://127.0.0.1:{server.server_port}/health/operations")
            state, detail = _script()._operations()
        finally:
            server.shutdown()
            server.server_close()
        assert state == expect
        if status == 404:
            assert "predates" in detail

    def test_a_service_not_answering_is_unknown(self, monkeypatch):
        from tests.test_nmas_deploy import _script

        sock = __import__("socket").socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()                                    # nothing listens there
        monkeypatch.setenv("NMAS_OPERATIONS_URL", f"http://127.0.0.1:{port}/health/operations")
        state, detail = _script()._operations()
        assert state == "unknown" and "not answering" in detail


class TestAnInterruptedOperationIsKeptAndSaid:
    def test_a_hold_left_by_a_dead_process_is_listed_not_held(self, ops, tmp_path):
        pid = _die_holding(tmp_path, ["r1", "r2"], step="verify")
        assert not any(h.get("pid") == pid for h in ops.held_anywhere())
        mine = [r for r in ops.interrupted(LIST) if r.get("pid") == pid]
        assert sorted(r["device"] for r in mine) == ["r1", "r2"]
        assert all(r["operation"] == "deploy" and r["actor"] == "person@example.invalid"
                   and r["progress"]["step"] == "verify" and r["found_at"] is None
                   for r in mine)

    def test_the_next_operation_keeps_the_record_and_it_is_listed_once(self, ops, tmp_path):
        from modules import config

        pid = _die_holding(tmp_path, ["r3"])
        ops.acquire(LIST, "r3", "capture", "next@example.invalid")
        try:
            log = os.path.join(config.DATA_DIR, "device_ops", LIST.lower(),
                               ops.INTERRUPTED_LOG)
            assert stat.S_IMODE(os.stat(log).st_mode) == 0o600
            kept = [json.loads(l) for l in open(log, encoding="utf-8")]
            mine = [k for k in kept if k["record"].get("pid") == pid]
            assert len(mine) == 1 and mine[0]["found_by"]["operation"] == "capture"
            listed = [r for r in ops.interrupted(LIST) if r.get("pid") == pid]
            assert len(listed) == 1 and listed[0]["found_at"]
        finally:
            ops.release(LIST, "r3")

    def test_a_released_hold_is_not_an_interruption(self, ops):
        ops.acquire(LIST, "r1", "deploy", "a@example.invalid")
        ops.release(LIST, "r1")
        assert not [r for r in ops.interrupted(LIST)
                    if r.get("device") == "r1" and r.get("actor") == "a@example.invalid"]


class TestNeedsAttentionSaysIt:
    def test_one_row_per_interrupted_process_naming_devices_and_step(self, ops, tmp_path):
        from modules import attention

        pid = _die_holding(tmp_path, ["r1", "r2"], step="verify")
        rows = [r for r in attention.interrupted_source()["rows"] if f"|{pid}|" in r["id"]]
        assert len(rows) == 1
        (r,) = rows
        assert r["devices"] == ["r1", "r2"] and r["kind"] == "interrupted"
        assert "did not finish" in r["what"] and "person@example.invalid" in r["cause"]
        assert "verify" in r["cause"].lower() or "verif" in r["cause"].lower()
        assert r["acknowledge"] is True and r["event"]
        assert "compare it with its golden" in r["action"]["label"]

    def test_acknowledged_it_leaves_and_a_later_interruption_is_a_new_row(self, ops,
                                                                          tmp_path):
        from modules import attention

        pid = _die_holding(tmp_path, ["r1"])
        page = attention.needs_attention(sources=[attention.interrupted_source])
        (r,) = [x for x in page["rows"] if f"|{pid}|" in x["id"]]
        got = attention.acknowledge(r["id"], r["event"], "read r1, it matches its golden",
                                    by="person@example.invalid", verified="access")
        assert got["ok"] is True
        page = attention.needs_attention(sources=[attention.interrupted_source])
        assert not [x for x in page["rows"] if f"|{pid}|" in x["id"]]
        assert any(a["id"] == r["id"] for a in page["acknowledged"])
        pid2 = _die_holding(tmp_path, ["r1"])
        page = attention.needs_attention(sources=[attention.interrupted_source])
        assert [x for x in page["rows"] if f"|{pid2}|" in x["id"]]

    def test_nothing_interrupted_says_what_it_looked_at(self):
        from modules import attention

        res = attention.interrupted_source(found=[])
        assert res["rows"] == [] and "none left by a process that ended" in res["checked"]
