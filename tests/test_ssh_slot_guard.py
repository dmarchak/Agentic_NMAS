"""The SSH slot guard (tests/ssh_slot_guard.py): a test that leaks a session slot lock fails at
its OWN teardown, by name, and a test that closes what it opens passes. Red then green through a
child pytest that loads the guard alone, on planted tests in a temporary folder, Netmiko faked
there; no device is reached, and the child's store is the test's own folder.
"""
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLANTED = textwrap.dedent('''
    import netmiko
    import pytest

    from modules import connection as C


    class Fake:
        def __init__(self, **kw):
            pass

        def disconnect(self):
            pass


    @pytest.fixture(autouse=True)
    def fake(monkeypatch):
        monkeypatch.setattr(netmiko, "ConnectHandler", Fake)
        monkeypatch.setattr(C, "vty_lines", lambda ip: (5, "the planted device"))


    def _open(ip):
        return C.open_ssh({"ip": ip, "device_type": "cisco_ios"}, owner="planted")


    def test_closes_what_it_opens():
        _open("192.0.2.41").disconnect()


    def test_leaks_a_session():
        _open("192.0.2.42")                                   # never disconnected


    def test_clears_the_count_without_closing():
        _open("2001:db8::43")
        C._sessions.clear()


    def test_after_the_leaks_starts_clean():
        from tests import ssh_slot_guard
        assert ssh_slot_guard.held() == []
''')


def _run(tmp_path):
    (tmp_path / "test_planted.py").write_text(PLANTED)
    data = tmp_path / "data"
    data.mkdir()
    env = dict(os.environ, PYTHONPATH=ROOT, NMAS_DATA_DIR=str(data), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly",
         "-p", "tests.ssh_slot_guard", "--rootdir", str(tmp_path), "-o", "addopts=",
         str(tmp_path / "test_planted.py")],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=120)


def test_a_leaked_lock_fails_its_own_test_by_name_and_no_other(tmp_path):
    r = _run(tmp_path)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    # Each leak fails at ITS OWN teardown, named, and the test after them starts clean.
    assert "ERROR at teardown of test_leaks_a_session" in out, out
    assert ("test_planted.py::test_leaks_a_session left SSH session slot lock(s) held at its "
            "teardown: 192.0.2.42 slot 0") in out, out
    assert "ERROR at teardown of test_clears_the_count_without_closing" in out, out
    assert ("test_planted.py::test_clears_the_count_without_closing left SSH session slot "
            "lock(s) held at its teardown: 2001:db8::43 slot 0") in out, out
    assert "ERROR at teardown of test_closes_what_it_opens" not in out, out
    assert "ERROR at teardown of test_after_the_leaks_starts_clean" not in out, out
    assert "4 passed, 2 errors" in out, out              # the teardown errors, nothing else


def test_the_guard_is_on_for_every_test():
    import tests.conftest as conftest
    from tests import ssh_slot_guard

    assert conftest._no_ssh_slot_lock_outlives_its_test is \
        ssh_slot_guard._no_ssh_slot_lock_outlives_its_test
