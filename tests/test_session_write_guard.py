"""C101: a session sends a write only while its thread holds the device.

C98's lock was taken by a LIST of functions, and five pre-existing writers
never took it: Save Device Config's `write memory` (which, racing a deploy
mid-push, saves a half-applied config while both report success), the bulk
operations, `/run_command`, and bulk reload. The rule now lives at the one
opener (`open_ssh`): a command the read-only allowlist (C61) refuses, or a
config or save call, is sent only while this thread holds that device. A
writer that forgets fails on first use, loudly. The lock's refusal also says
how long the holder has held the device and whether it is still moving.

Netmiko is faked at its boundary, so `open_ssh`, the guard and each route
run for real.
"""

import os
import threading
import time

import pytest

from modules import connection as C
from modules.nsot import device_ops as D

IP, HOST, LIST = "192.0.2.12", "r2", "Default"


class FakeConn:
    sent = []

    def __init__(self, **params):
        self.ip = params["ip"]

    def enable(self):
        pass

    def find_prompt(self):
        return "r2#"

    def check_config_mode(self):
        return False

    def exit_config_mode(self):
        pass

    def is_alive(self):
        return True

    def send_command(self, cmd, **kw):
        FakeConn.sent.append(cmd)
        return "ok"

    send_command_timing = send_command

    def send_config_set(self, cmds, **kw):
        FakeConn.sent.extend(cmds)
        return "ok"

    def save_config(self, *a, **k):
        FakeConn.sent.append("write memory")
        return "ok"

    def disconnect(self):
        pass


@pytest.fixture(autouse=True)
def fake_netmiko(monkeypatch):
    import netmiko

    FakeConn.sent = []
    monkeypatch.setattr(netmiko, "ConnectHandler", FakeConn)
    monkeypatch.setattr(C, "vty_lines", lambda ip: (5, "the test's device"))
    C._sessions.clear()
    yield
    C._sessions.clear()
    with D._mu:
        stale = list(D._held.values())
        D._held.clear()
    for info in stale:
        if info["fd"] is not None:
            os.close(info["fd"])


def _params(ip=IP):
    return {"device_type": "cisco_xe", "ip": ip, "username": "u", "password": "p",
            "secret": "p", "port": 22, "fast_cli": False}


class Holder:
    def __init__(self, host=HOST, operation="deploy", ip=IP):
        self.args = (LIST, host, operation, "other@example.invalid")
        self.ip = ip
        self.held, self.done = threading.Event(), threading.Event()
        self.t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        with D.hold(*self.args, ip=self.ip):
            self.held.set()
            self.done.wait(10)

    def __enter__(self):
        self.t.start()
        assert self.held.wait(5)
        return self

    def __exit__(self, *exc):
        self.done.set()
        self.t.join(5)


class TestTheGuardAtTheOpener:
    @pytest.mark.parametrize("call", [
        lambda c: c.send_config_set(["interface Gi2"]),
        lambda c: c.save_config(),
        lambda c: c.send_command_timing("write memory"),
        lambda c: c.send_command("reload"),
        lambda c: c.send_command("clear counters"),
    ], ids=["config set", "save", "write memory", "reload", "clear"])
    def test_a_write_without_a_hold_is_refused_and_nothing_is_sent(self, call):
        conn = C.open_ssh(_params(), owner="test")
        with pytest.raises(C.UnheldDeviceWrite) as exc:
            call(conn)
        assert FakeConn.sent == [] and "does not hold the device" in str(exc.value)

    def test_a_read_needs_no_hold(self):
        conn = C.open_ssh(_params(), owner="test")
        conn.send_command("show running-config")
        conn.send_command("show interfaces | include line protocol")
        assert len(FakeConn.sent) == 2

    def test_holding_the_device_allows_the_write(self):
        conn = C.open_ssh(_params(), owner="test")
        with D.hold(LIST, HOST, "deploy", "me", ip=IP):
            conn.send_config_set(["interface Gi2"])
            conn.save_config()
        assert FakeConn.sent == ["interface Gi2", "write memory"]

    def test_holding_ANOTHER_device_does_not(self):
        conn = C.open_ssh(_params(), owner="test")
        with D.hold(LIST, "r1", "deploy", "me", ip="192.0.2.11"):
            with pytest.raises(C.UnheldDeviceWrite):
                conn.save_config()

    def test_the_refusal_names_the_verb_never_the_command(self):
        """A command can carry a secret: a rotation's password line."""
        conn = C.open_ssh(_params(), owner="test")
        with pytest.raises(C.UnheldDeviceWrite) as exc:
            conn.send_command_timing("username admin secret SEKRETVALUE99")
        assert "'username'" in str(exc.value) and "SEKRETVALUE99" not in str(exc.value)


def _device_row():
    from modules import config, device

    enc = device.fernet.encrypt(b"pw").decode()
    path = os.path.join(config.get_list_data_dir(LIST), "devices.csv")
    device.write_devices_csv([{"hostname": HOST, "ip": IP, "device_type": "cisco_xe",
                               "username": "u", "password": enc, "secret": enc}], path)


def _flashes(client) -> str:
    with client.session_transaction() as s:
        return " ".join(m for _cat, m in s.get("_flashes", []))


@pytest.fixture
def client(monkeypatch):
    import app as A

    _device_row()
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: LIST)
    A.connections.clear()
    yield A.app.test_client()
    A.connections.clear()


class TestEveryWriterNowHoldsTheDevice:
    def test_run_command_a_read_never_waits(self, client):
        with Holder():
            r = client.post(f"/run_command/{IP}", data={"command": "show clock"},
                            headers={"X-Requested-With": "XMLHttpRequest"})
        assert r.status_code == 200 and "show clock" in FakeConn.sent

    def test_run_command_a_write_is_refused_while_held_and_runs_when_free(self, client):
        with Holder():
            client.post(f"/run_command/{IP}", data={"command": "clear counters"},
                        headers={"X-Requested-With": "XMLHttpRequest"})
        assert "clear counters" not in FakeConn.sent
        assert "r2 is being deployed to by other@example.invalid" in _flashes(client)
        client.post(f"/run_command/{IP}", data={"command": "clear counters"},
                    headers={"X-Requested-With": "XMLHttpRequest"})
        assert "clear counters" in FakeConn.sent

    def _bulk(self, client, command):
        from modules.bulk_ops import bulk_manager

        d = client.post("/bulk_execute", data={"device_ips[]": [IP], "command": command,
                                               "command_mode": "enable"}).get_json()
        op = d["operation_id"]
        for _ in range(100):
            status = bulk_manager.active_operations.get(op, {})
            if len(status.get("results", [])) == 1:
                return status["results"][0]
            time.sleep(0.05)
        raise AssertionError("the bulk operation never reported")

    def test_a_bulk_write_on_a_held_device_fails_that_device_by_name(self, client):
        with Holder():
            result = self._bulk(client, "clear counters")
        assert result["status"] == "failed" and "r2 is being deployed to" in result["error"]
        assert "clear counters" not in FakeConn.sent

    def test_a_bulk_read_on_a_held_device_runs(self, client):
        with Holder():
            result = self._bulk(client, "show clock")
        assert result["status"] == "success"


class TestTheRefusalSaysHowLongAndWhetherItMoves:
    BASE = {"device": "r2", "operation": "onboard", "actor": "operator@example.com",
            "detail": "phase two", "started": 1000.0, "pid": 4242,
            "progress": {"step": "rotate", "at": 1000.0 + 14 * 60}}

    def test_a_working_holder_reads_as_wait(self):
        text = D.describe(self.BASE, now=1000.0 + 15 * 60)
        assert "held for 15 min" in text and "last progress: rotate, 60 s ago" in text
        assert "process 4242" in text and "may be stuck" not in text

    def test_a_silent_holder_reads_as_possibly_stuck_with_no_force(self):
        text = D.describe(self.BASE, now=1000.0 + 14 * 60 + D.STALL_AFTER_SECONDS + 60)
        assert "No progress for 11 min: it may be stuck" in text
        assert "There is no force" in text and "force" not in text.split("There is no force")[1]

    def test_progress_reaches_another_process_s_view(self):
        """`note()` rewrites the lock file, so a CLI refused by the app (or the
        app by a CLI) reads the step it is on."""
        pytest.importorskip("fcntl")
        with D.hold(LIST, "r7", "rotate", "me"):
            D.note("verify")
            text = D._read_holder_file(D._path(LIST, "r7"), "r7")
        assert text["progress"]["step"] == "verify"


def test_the_steps_that_take_long_report_progress():
    """Each long holder notes its steps, or its refusal can only say when it
    started. Pinned by source: the pipeline's stage loop, rotation's steps,
    onboarding's phase-two steps and retirement's steps."""
    import inspect

    from modules import pipeline
    from modules.nsot import credential_rotation, onboard, retire

    assert "device_ops.note(" in inspect.getsource(pipeline.PipelineRunner.run)
    assert "device_ops.note(" in inspect.getsource(credential_rotation._rotate)
    assert "device_ops.note(" in inspect.getsource(onboard.run_phase_two.__wrapped__)
    assert "device_ops.note(" in inspect.getsource(retire.apply.__wrapped__)


#: Functions that send a non-read command WITHOUT taking the hold themselves,
#: because their caller holds it. Each with its caller. Only shrinks.
HELD_BY_CALLER = {
    "modules/bulk_ops.py:_run_single_enable_command": "the bulk worker, per device",
    "modules/bulk_ops.py:_execute_tftp_upload": "the bulk worker, per device",
    "modules/bulk_ops.py:_execute_tftp_download": "the bulk worker, per device",
    "modules/bulk_ops.py:_execute_config_download": "the bulk worker, per device",
    "modules/bulk_ops.py:_execute_delete_file": "the bulk worker, per device",
    "modules/nsot/credential_rotation.py:push_rotation": "rotate()",
    "modules/commands.py:_run": "run_device_command's body (C272); its callers: /run_command holds a non-read",
    "modules/device_reload.py:reload_device": "app.bulk_reload's per-device thread (C153)",
    # Found when the scan was widened to config mode and the scripts (C191,
    # 2026-09-29); each caller verified in the code.
    "modules/bulk_ops.py:_execute_remove_static_routes": "the bulk worker, per device",
    "modules/pipeline.py:_push_via_netmiko": "the deploy and restore applies, which hold "
                                             "every target for the run (acquire_many)",
    "modules/pipeline.py:_restore_config": "the deploy and restore applies (acquire_many)",
    "modules/nsot/onboard.py:remove_rw_communities": "run_phase_two (@_holds_the_device)",
    "modules/nsot/onboard.py:send_profile_program": "run_phase_two (@_holds_the_device)",
    # C203, fixed 2026-09-29: credential_rotation.persist() holds the device
    # itself now, so the CLI rotation's save is held as well.
    "modules/nsot/onboard.py:persist_on_device": (
        "run_phase_two, nmas-persist-native, credential_rotation.persist() "
        "(the CLI rotation, C203), and the pipeline's save_startup, inside the deploy and "
        "restore applies, which hold every target (acquire_many; C501)"),
}

#: Writers a caller reaches WITHOUT holding the device: the runtime guard
#: (C101) refuses them there. Named, registered, and this list only SHRINKS.
KNOWN_UNHELD = {
}

#: A name the scan matches that is not a device write, each with why.
NOT_A_DEVICE = {
    "routes/settings_integrations.py:save_integration": (
        "IntegrationClient.save_config() writes an integration's settings, not a device"),
}


def _writer_sites():
    """(file, enclosing functions, command) for every command string the
    program sends that the read-only allowlist refuses, or cannot know."""
    import ast

    from modules.readonly_commands import refusal

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sends = {"send_command", "send_command_timing", "send_command_expect"}
    # Config mode and saves are writes whatever they carry (C191: the scan
    # counted `send_command*` only, so a `send_config_set` was invisible).
    config_writes = {"send_config_set", "send_config_from_file", "save_config"}
    out = []
    files = ["app.py"] + [os.path.join(dp, f) for base in ("modules", "routes")
                          for dp, _d, fs in os.walk(os.path.join(root, base))
                          for f in fs if f.endswith(".py")]
    # The host scripts too (C191): a new script that changed a device passed
    # the whole suite unnamed. A script that is not Python is not scanned.
    scripts = os.path.join(root, "scripts")
    files += [os.path.join(scripts, f) for f in sorted(os.listdir(scripts))
              if os.path.isfile(os.path.join(scripts, f))]
    for path in files:
        full = path if os.path.isabs(path) else os.path.join(root, path)
        rel = os.path.relpath(full, root)
        try:
            tree = ast.parse(open(full, encoding="utf-8").read())
        except (SyntaxError, UnicodeDecodeError):
            continue                          # a shell script
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            called = (getattr(node.func, "attr", getattr(node.func, "id", ""))
                      if isinstance(node, ast.Call) else "")
            if called not in sends and called not in config_writes:
                continue
            arg = node.args[0] if node.args else None
            if called in config_writes:
                text = f"<{called}>"          # a write, whatever it carries
            elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                text = arg.value
            elif isinstance(arg, ast.JoinedStr):
                text = "".join(v.value if isinstance(v, ast.Constant) else "X"
                               for v in arg.values)
            else:
                text = None                   # dynamic: its function is judged
            if text is not None and not refusal(text):
                continue
            chain, n = [], node
            while n in parents:
                n = parents[n]
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    chain.append(n)
            if any(f"{rel}:{f.name}" in NOT_A_DEVICE for f in chain):
                continue
            out.append((rel, chain, text, node.lineno))
    return out


def _takes_the_hold(func) -> bool:
    """A CALL that takes the lock, not a mention of its module: the first
    version accepted any function naming `device_ops`, and a control that
    removed delete_file's hold passed, because its import line survived."""
    import ast

    return any(isinstance(n, ast.Call)
               and getattr(n.func, "attr", getattr(n.func, "id", ""))
               in ("hold", "hold_device", "acquire", "acquire_many")
               for n in ast.walk(func))


def test_every_writer_takes_the_hold_or_names_the_caller_that_does():
    """C101's scan, pinned: the four writers it found (upload, delete and
    download a file, save to startup) sent their writes as COMMAND STRINGS,
    which a search for method names missed."""
    import ast

    sites = _writer_sites()
    assert len(sites) >= 30, len(sites)
    unheld = []
    for rel, chain, text, line in sites:
        if f"{rel}:*" in HELD_BY_CALLER:
            continue
        if any(f"{rel}:{f.name}" in HELD_BY_CALLER for f in chain):
            continue
        if any(f"{rel}:{f.name}" in KNOWN_UNHELD for f in chain):
            continue
        if any(_takes_the_hold(f) for f in chain):
            continue
        unheld.append(f"{rel}:{line} {text!r}")
    assert unheld == [], unheld
    names = {f"{rel}:{f.name}" for rel, chain, _t, _l in sites for f in chain}
    assert "app.py:delete_file" in names and "app.py:upload_file" in names
    ghosts = sorted((set(HELD_BY_CALLER) | set(KNOWN_UNHELD)) - names)
    assert ghosts == [], f"named but sending nothing now: {ghosts}"


def test_the_scan_reads_config_mode_and_the_scripts():
    """C191: the population is every device write, not the `send_command*`
    calls in the app. Config-mode sends and saves are found, and so is a host
    script's write (the removal probe's, which holds its device); a name that
    only looks like a device write is declared, never silently skipped."""
    sites = _writer_sites()
    found = {(rel, text) for rel, _c, text, _l in sites}
    assert ("modules/pipeline.py", "<send_config_set>") in found
    assert ("modules/nsot/onboard.py", "<save_config>") in found
    assert any(rel.startswith("scripts/") for rel, _t in found), "the scripts are read"
    assert not any(rel == "routes/settings_integrations.py" for rel, _t in found)
    assert len(KNOWN_UNHELD) == 0, "only shrinks: C203 was its last member"
