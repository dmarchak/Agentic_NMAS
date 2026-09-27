"""C97: the tool counts, attributes, bounds and closes its own SSH sessions.

It locked itself out of r2 (2026-09-27): all five vty lines held by its own
idle sessions, SSH refused, the device reading offline while nothing was
wrong with it. Every deploy and restore left its pipeline pool open, the
capture reader left one per read, and nothing counted them. A dropped
Netmiko reference is not a closed session: paramiko's thread keeps it
until the device's `exec-timeout` (10 minutes, measured on a C8000v and a
vIOS).

Netmiko is faked at its own boundary, so `open_ssh()` and every caller run
for real.
"""

import ast
import logging
import os
import threading

import pytest

from modules import connection as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IP = "192.0.2.12"


class FakeConn:
    opened = []

    def __init__(self, **params):
        self.params = params
        self.disconnected = False
        FakeConn.opened.append(self)

    def enable(self):
        if FakeConn.fail_enable:
            raise RuntimeError("enable refused")

    def find_prompt(self):
        return "r2#"

    def send_command(self, cmd, **kw):
        return "hostname r2\nend\n"

    def is_alive(self):
        return not self.disconnected

    def disconnect(self):
        self.disconnected = True


FakeConn.fail_enable = False


@pytest.fixture(autouse=True)
def fake_netmiko(monkeypatch):
    import netmiko

    FakeConn.opened = []
    FakeConn.fail_enable = False
    monkeypatch.setattr(netmiko, "ConnectHandler", FakeConn)
    monkeypatch.setattr(C, "vty_lines", lambda ip: (5, "the test's device"))
    C._sessions.clear()
    yield
    C._sessions.clear()


def _params(ip=IP):
    return {"device_type": "cisco_xe", "ip": ip, "username": "u", "password": "p",
            "secret": "p", "port": 22, "fast_cli": False}


def _device(ip=IP):
    from modules import device

    enc = device.fernet.encrypt(b"pw").decode()
    return {"hostname": "r2", "ip": ip, "device_type": "cisco_xe", "username": "u",
            "password": enc, "secret": enc}


class TestEverySessionIsCounted:
    def test_open_counts_and_disconnect_releases(self):
        conn = C.open_ssh(_params(), owner="test:one")
        assert C.held_sessions()[IP]["held"] == 1
        assert C.held_sessions()[IP]["sessions"][0]["owner"] == "test:one"
        conn.disconnect()
        assert IP not in C.held_sessions()

    def test_open_and_close_name_the_device_and_the_owner(self, caplog):
        caplog.set_level(logging.INFO, logger="modules.connection")
        C.open_ssh(_params(), owner="test:named").disconnect()
        text = caplog.text
        assert f"ssh: opened {IP} for test:named" in text
        assert f"ssh: closed {IP} for test:named" in text

    def test_an_owner_is_attributed_when_the_caller_names_none(self):
        C.open_ssh(_params())
        owner = C.held_sessions()[IP]["sessions"][0]["owner"]
        assert owner.endswith("test_ssh_sessions:"
                              "test_an_owner_is_attributed_when_the_caller_names_none"), owner


class TestTheBudgetKeepsALineForAPerson:
    def test_a_five_line_device_allows_four_and_refuses_the_fifth_by_name(self):
        held = [C.open_ssh(_params(), owner=f"op{i}") for i in range(4)]
        with pytest.raises(C.SessionBudgetExceeded) as exc:
            C.open_ssh(_params(), owner="op5")
        msg = str(exc.value)
        assert "holds 4 (op0, op1, op2, op3)" in msg
        assert "keeping 1 free for a person" in msg and "5 vty line(s)" in msg
        held[0].disconnect()
        C.open_ssh(_params(), owner="op5")          # a line freed, so allowed again
        assert len(FakeConn.opened) == 5, "the refused open never reached the device"

    def test_the_vty_count_is_read_from_real_configs(self):
        fleet = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
        read = lambda h: open(os.path.join(fleet, f"{h}.cfg"), encoding="utf-8").read()
        assert C._count_vty_lines(read("r2")) == 5        # line vty 0 / 1 / 2 4
        assert C._count_vty_lines(read("s1")) == 16       # line vty 0 4 / 5 15
        assert C._count_vty_lines("hostname x\n") == 0    # unknown, never generous


class TestOperationsCloseWhatTheyOpen:
    def test_the_capture_reader_closes_its_session(self):
        import routes.golden as rg

        text, error = rg._read_running(_device())
        assert error == "" and text
        assert FakeConn.opened and all(c.disconnected for c in FakeConn.opened)
        assert C.held_sessions() == {}

    def test_verify_device_connection_closes_when_enable_raises(self):
        FakeConn.fail_enable = True
        with pytest.raises(RuntimeError):
            C.verify_device_connection(IP, "u", "p", "p")
        assert FakeConn.opened[0].disconnected and C.held_sessions() == {}

    @pytest.mark.parametrize("raises", [False, True], ids=["completes", "raises"])
    def test_a_pipeline_run_closes_its_pool(self, monkeypatch, raises):
        """The pipeline's pool is the run's own: closed when the run ends,
        whether it completes or raises. Each deploy and restore left one."""
        import routes.deploy as rd
        from modules import pipeline

        monkeypatch.setattr("modules.nsot.deploy.prepare_for_deploy",
                            lambda a: {"config": "hostname r2\n"})
        monkeypatch.setattr("modules.nsot.deploy.merge_commands",
                            lambda intended, captured: ["hostname r2"])
        monkeypatch.setattr("modules.nsot.deploy.assert_merge_only", lambda c, i: None)

        def run(self):
            C.get_persistent_connection(_device(), self.ctx.connections_pool,
                                        self.ctx.pool_lock)
            assert C.held_sessions()[IP]["held"] == 1
            if raises:
                raise RuntimeError("the pipeline broke")
            self.ctx.final_status = "success"
            return self.ctx
        monkeypatch.setattr(pipeline.PipelineRunner, "run", run)

        class Artifact:
            device = "r2"
        rd._deploy_one({"artifact": Artifact(), "fresh": "hostname x\n"}, "Lab",
                       {"r2": _device()})
        assert C.held_sessions() == {}, C.held_sessions()
        assert FakeConn.opened and FakeConn.opened[0].disconnected


class TestIdlePooledSessionsAreClosedByTheTool:
    def test_an_idle_pooled_session_is_closed_and_leaves_its_pool(self):
        pool, lock = {}, threading.Lock()
        C.get_persistent_connection(_device(), pool, lock)
        for info in C._sessions[IP].values():
            info["last_used"] -= C.IDLE_REAP_SECONDS + 1
        assert C.reap_idle() == 1
        assert IP not in pool and C.held_sessions() == {}

    def test_a_used_session_is_not_idle(self):
        pool, lock = {}, threading.Lock()
        conn = C.get_persistent_connection(_device(), pool, lock)
        for info in C._sessions[IP].values():
            info["last_used"] -= C.IDLE_REAP_SECONDS + 1
        conn.send_command("show clock")              # through the lock: touched
        assert C.reap_idle() == 0 and IP in pool

    def test_a_session_in_use_is_skipped_never_waited_for(self):
        pool, lock = {}, threading.Lock()
        C.get_persistent_connection(_device(), pool, lock)
        for info in C._sessions[IP].values():
            info["last_used"] -= C.IDLE_REAP_SECONDS + 1
        held = threading.Event()
        release = threading.Event()

        def hold():
            with C.get_device_send_lock(IP):
                held.set()
                release.wait(5)
        t = threading.Thread(target=hold)
        t.start()
        held.wait(5)
        try:
            assert C.reap_idle() == 0 and IP in pool
        finally:
            release.set()
            t.join()

    def test_an_operation_s_own_session_is_never_reaped(self):
        C.open_ssh(_params(), owner="op")
        for info in C._sessions[IP].values():
            info["last_used"] -= 10 * C.IDLE_REAP_SECONDS
        assert C.reap_idle() == 0 and C.held_sessions()[IP]["held"] == 1


#: Files that may call ConnectHandler themselves, each with its reason.
DIRECT_OPENERS = {
    "modules/connection.py": "open_ssh() itself, the one opener",
    "scripts/netmiko_timing_probe.py": "a standalone probe measuring Netmiko's own "
                                        "timing, run by hand outside the app",
}


class TestThereIsOneOpener:
    def _calls(self):
        found = {}
        for base in ("modules", "routes", "scripts"):
            for dirpath, _dirs, files in os.walk(os.path.join(ROOT, base)):
                for name in files:
                    path = os.path.join(dirpath, name)
                    if not (name.endswith(".py") or base == "scripts"):
                        continue
                    try:
                        tree = ast.parse(open(path, encoding="utf-8").read())
                    except (SyntaxError, UnicodeDecodeError):
                        continue
                    rel = os.path.relpath(path, ROOT)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            f = node.func
                            name_ = getattr(f, "id", getattr(f, "attr", ""))
                            if name_ in ("ConnectHandler", "open_ssh"):
                                found.setdefault(name_, []).append(rel)
        app = ast.parse(open(os.path.join(ROOT, "app.py"), encoding="utf-8").read())
        for node in ast.walk(app):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "ConnectHandler":
                found.setdefault("ConnectHandler", []).append("app.py")
        return found

    def test_no_session_is_opened_outside_open_ssh(self):
        direct = sorted(set(self._calls().get("ConnectHandler", [])))
        assert set(direct) - set(DIRECT_OPENERS) == set(), direct
        assert "modules/connection.py" in direct, "the anchor: open_ssh's own call"

    def test_the_callers_go_through_it(self):
        callers = self._calls().get("open_ssh", [])
        assert len(callers) >= 9, callers
        for expected in ("modules/nsot/credential_rotation.py", "modules/nsot/onboard.py"):
            assert expected in callers


class TestJobHealthCountsThem:
    def _held(self, held, budget=4, sessions=None):
        return {IP: {"held": held, "budget": budget, "lines": budget + 1,
                     "sessions": sessions or [{"owner": "pipeline", "age_s": 30,
                                               "idle_s": 30, "pooled": False}] * held}}

    def test_a_device_at_its_budget_is_named(self):
        from modules import job_health as J

        rows = J.ssh_session_rows(self._held(4))
        assert rows[0]["state"] == "at_budget" and "The next operation on it is refused" \
            in rows[0]["detail"]

    def test_an_operation_s_session_past_ten_minutes_is_a_leak(self):
        from modules import job_health as J

        rows = J.ssh_session_rows(self._held(1, sessions=[
            {"owner": "rotation:x", "age_s": 700, "idle_s": 700, "pooled": False}]))
        assert [r["state"] for r in rows] == ["leaked"]

    def test_none_held_is_a_statement(self):
        from modules import job_health as J

        rows = J.ssh_session_rows({})
        assert rows == [{"unit": "ssh-sessions", "what": rows[0]["what"], "state": "ok",
                         "max_age_minutes": 0, "detail": "holds no SSH session now"}]
