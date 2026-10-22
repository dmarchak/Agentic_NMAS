"""C1349, Lab 9's s5: the vIOS configless launch patch, tested against the REAL script.

vrnetlab's vIOS launcher types on the console of every node it starts (`no` at the setup
dialog, three RETURNs, then the startup file), and its watchdog restarts a VM after 300 quiet
console spins. On classic IOS an answer at that dialog can end AutoInstall, so a switch meant to
fetch its configuration by ZTP must boot with its console untouched.
`docs/bootstrap-probe/patches/patch-vios-configless.py` removes all of it.

Its claims are checked two ways: structurally (AST) on the patched real script, never by
searching its text (the patch's own comments quote what it changes), and by RUNNING the patched
`bootstrap_spin` against a stub console, which records every write.
"""

import ast
import hashlib
import importlib.machinery
import importlib.util
import os
import signal
import sys
import types

import pytest

#: What the launcher's module body takes over for the whole process (vrnetlab's: a SIGCHLD
#: handler that reaps ANY child, SIGINT and SIGTERM handlers that exit 0).
LAUNCHER_SIGNALS = (signal.SIGCHLD, signal.SIGINT, signal.SIGTERM)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "launch", "vios-launch.py")
PATCHER = os.path.join(ROOT, "docs", "bootstrap-probe", "patches", "patch-vios-configless.py")
MEASURED_SHA = "794788bcada997dac7aac239d86d1867f165482ae30b03376463b89418c8e93d"
#: The generator's OUTPUT from that fixture (C1546): what `--write` leaves, the launcher the lab
#: binds over s5's `/launch.py` (`patches/vios-launch-configless.py`, recorded at C2, `183aa5d`).
#: `lab/check-deployed-patches` compares the lab's copies with this same value.
GENERATED_SHA = "6d1f16e0e651a0582e12f43920f323b252c33638376dac4d1d7bfcefbc8d202d"


def _patcher():
    loader = importlib.machinery.SourceFileLoader("patch_vios_configless", PATCHER)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _real():
    with open(FIXTURE, encoding="utf-8") as fh:
        return fh.read()


def _method(tree, name):
    found = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    assert found, f"no method {name} in the launch script"
    return found[0]


def _calls(fn, attr):
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == attr and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"]


def test_the_fixture_is_the_script_that_was_read():
    with open(FIXTURE, "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == MEASURED_SHA


def test_the_generator_writes_the_launcher_the_lab_runs(tmp_path, capsys):
    """C1546: the INPUT pinned alone lets the patcher change and the lab keep running the old
    output unnoticed. `--write` on a copy of the pinned fixture writes exactly the launcher whose
    sha the lab's check compares (C2's `6d1f16e0e651a058…`)."""
    copy = tmp_path / "vios-launch-configless.py"
    copy.write_bytes(open(FIXTURE, "rb").read())
    assert _patcher().main([str(copy), "--write"]) == 0
    capsys.readouterr()
    assert hashlib.sha256(copy.read_bytes()).hexdigest() == GENERATED_SHA
    assert GENERATED_SHA.startswith("6d1f16e0e651a058")


class TestTheRealScriptBeforeThePatch:
    """What the stock launcher does: floors, so the checks below can fail."""

    def test_it_types_on_the_console(self):
        spin = _method(ast.parse(_real()), "bootstrap_spin")
        assert _calls(spin, "wait_write") and _calls(spin, "apply_config")

    def test_its_watchdog_restarts_a_quiet_vm(self):
        spin = _method(ast.parse(_real()), "bootstrap_spin")
        assert _calls(spin, "stop") and _calls(spin, "start")

    def test_a_missing_startup_file_is_only_logged(self):
        """C1349's "fatal" is a log line: the stock script carries on and marks the node
        running, typing at its console all the same."""
        apply = _method(ast.parse(_real()), "apply_config")
        assert not [n for n in ast.walk(apply) if isinstance(n, ast.Raise)]


class TestThePatchedScript:
    @pytest.fixture(scope="class")
    def tree(self):
        return ast.parse(_patcher().patch(_real()))

    def test_it_compiles(self):
        compile(_patcher().patch(_real()), "launch.py", "exec")

    def test_nothing_is_typed_and_no_configuration_applied(self, tree):
        spin = _method(tree, "bootstrap_spin")
        assert not _calls(spin, "wait_write") and not _calls(spin, "apply_config")

    def test_the_watchdog_never_restarts_the_vm(self, tree):
        spin = _method(tree, "bootstrap_spin")
        assert not _calls(spin, "stop") and not _calls(spin, "start")

    def test_a_startup_file_is_named_and_nothing_reads_it(self, tree):
        """containerlab writes a default startup file for this kind (C1534), so its presence is
        logged by name, and the one reader of it, apply_config, is never called."""
        init = _method(tree, "__init__")
        guards = [n for n in ast.walk(init) if isinstance(n, ast.If)
                  and ast.unparse(n.test) == "os.path.exists(STARTUP_CONFIG_FILE)"]
        assert len(guards) == 1
        assert "STARTUP_CONFIG_FILE" in ast.unparse(guards[0].body[0])
        callers = [f.name for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
                   and _calls(f, "apply_config")]
        assert callers == [], callers


class _Logger:
    def __init__(self):
        self.lines = []

    def __getattr__(self, level):
        return lambda msg, *a, **k: self.lines.append((level, msg % a if a else msg))


def _load_patched(monkeypatch, tmp_path, expect):
    """The patched launcher, imported with stand-ins for vrnetlab and scrapli: the VM base
    class records every console write and close, and `con_expect` returns *expect*."""
    events = []

    class VM:
        def __init__(self, **kw):
            self.start_time = __import__("datetime").datetime.now()

        def con_expect(self, patterns, timeout=None):
            return expect

        def wait_write(self, text, wait=None, con=None):
            events.append(("write", text))

        def write_to_stdout(self, data):
            events.append(("stdout", data))

        def stop(self):
            events.append(("stop",))

        def start(self):
            events.append(("start",))

    vrnetlab = types.ModuleType("vrnetlab")
    vrnetlab.VM, vrnetlab.VR = VM, object
    vrnetlab.getenv_uint, vrnetlab.DEFAULT_SCRAPLI_TIMEOUT = (lambda n, d: d), 30
    core = types.ModuleType("scrapli.driver.core")
    core.IOSXEDriver = lambda **kw: events.append(("scrapli",))
    for name, mod in (("vrnetlab", vrnetlab), ("scrapli", types.ModuleType("scrapli")),
                      ("scrapli.driver", types.ModuleType("scrapli.driver")),
                      ("scrapli.driver.core", core)):
        monkeypatch.setitem(sys.modules, name, mod)
    path = tmp_path / "launch_patched.py"
    path.write_text(_patcher().patch(_real()), encoding="utf-8")
    loader = importlib.machinery.SourceFileLoader("launch_patched", str(path))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    # The launcher's module body installs process-wide signal handlers. Left in place, its
    # SIGCHLD reaper took the exit status of every later child in this pytest worker first, so
    # `subprocess` read 0 for a child that exited 1 or 2 (found 2026-10-22, C1546's tests of
    # lab/check-deployed-patches). They are put back the moment the module is loaded.
    saved = {s: signal.getsignal(s) for s in LAUNCHER_SIGNALS}
    try:
        loader.exec_module(mod)
    finally:
        for s, handler in saved.items():
            signal.signal(s, handler)
    monkeypatch.setattr(mod, "STARTUP_CONFIG_FILE", str(tmp_path / "no-startup.cfg"))
    monkeypatch.setattr(mod.os, "listdir", lambda p: ["vios_l2-test.qcow2"])
    return mod, events


@pytest.mark.parametrize("ridx", [0, 1, 2])
def test_at_each_console_state_it_types_nothing_and_releases_the_console(monkeypatch, tmp_path,
                                                                        ridx):
    """The dialog (0), "Press RETURN" (1) and the prompt (2): the stock script types at each."""
    mod, events = _load_patched(monkeypatch, tmp_path, (ridx, object(), b"x"))
    vm = mod.VIOS_vm("s5", "admin", "admin", "tc")
    vm.logger = _Logger()
    closed = []
    vm.scrapli_tn = types.SimpleNamespace(close=lambda: closed.append(True))
    vm.bootstrap_spin()
    assert [e for e in events if e[0] in ("write", "scrapli", "stop", "start")] == []
    assert vm.running is True and closed == [True]


def test_loading_the_launcher_leaves_this_process_s_signal_handlers_as_they_were(monkeypatch,
                                                                                tmp_path):
    """The launcher's module body takes SIGCHLD, SIGINT and SIGTERM (a floor: it does, so this
    can fail); loading it here puts each back, so no later test's child loses its exit status
    to vrnetlab's reaper."""
    assert "signal.signal(signal.SIGCHLD, handle_SIGCHLD)" in _real().splitlines()
    before = {s: signal.getsignal(s) for s in LAUNCHER_SIGNALS}
    mod, _events = _load_patched(monkeypatch, tmp_path, (-1, None, b""))
    assert callable(mod.handle_SIGCHLD)
    assert {s: signal.getsignal(s) for s in LAUNCHER_SIGNALS} == before


def test_the_quiet_watchdog_waits_instead_of_restarting(monkeypatch, tmp_path):
    mod, events = _load_patched(monkeypatch, tmp_path, (-1, None, b""))
    vm = mod.VIOS_vm("s5", "admin", "admin", "tc")
    vm.logger = _Logger()
    vm.spins = 301
    vm.bootstrap_spin()
    assert ("stop",) not in events and ("start",) not in events
    assert vm.spins == 0 and vm.running is False
    assert any("NOT restarting" in line for _level, line in vm.logger.lines)


@pytest.mark.parametrize("ridx", [0, 1, 2])
def test_with_containerlabs_default_startup_file_it_still_types_nothing(monkeypatch, tmp_path,
                                                                       ridx):
    """C1534: containerlab wrote /config/startup-config.cfg for Lab 9's s5, which names none.
    The launch goes on, names the file, and types none of it at any console state."""
    mod, events = _load_patched(monkeypatch, tmp_path, (ridx, object(), b"x"))
    (tmp_path / "no-startup.cfg").write_text("hostname vios\n", encoding="utf-8")
    vm = mod.VIOS_vm("s5", "admin", "admin", "tc")
    vm.logger = _Logger()
    vm.scrapli_tn = types.SimpleNamespace(close=lambda: None)
    vm.bootstrap_spin()
    assert [e for e in events if e[0] in ("write", "scrapli", "stop", "start")] == []
    assert vm.running is True


class TestThePatcherRefuses:
    def test_a_second_patch(self):
        p = _patcher()
        with pytest.raises(p.Refused, match="already patched"):
            p.patch(p.patch(_real()))

    def test_a_launcher_that_differs(self):
        p = _patcher()
        changed = _real().replace("# too many spins with no result -> give up",
                                  "# too many spins with no result -> give up now")
        with pytest.raises(p.Refused, match="the restart watchdog"):
            p.patch(changed)

    def test_a_containers_own_launch_py(self, monkeypatch):
        p = _patcher()
        monkeypatch.setattr(p.os.path, "realpath", lambda path: "/launch.py")
        with pytest.raises(SystemExit, match="Copy it out first"):
            p.main(["/launch.py"])

    def test_without_write_it_changes_nothing(self, tmp_path, capsys):
        p = _patcher()
        copy = tmp_path / "vios-launch-configless.py"
        copy.write_text(_real(), encoding="utf-8")
        assert p.main([str(copy)]) == 0
        assert copy.read_text(encoding="utf-8") == _real()
        assert "+            self.scrapli_tn.close()" in capsys.readouterr().out
