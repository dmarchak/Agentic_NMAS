"""Register C46: no test touches a network, and a run says whether that holds
for the processes it starts.

A test ran the clab sync script with its default URL, which on the deployment
host IS the NMAS, and the live app logged the request on every host run
(2026-09-26). The rule had been enforced for the test process only by
convention, and for what a test starts not at all.

Each test here asserts something in BOTH states (confined or not), so none of
them is a check that silently did not run.
"""

import errno
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

from tests import network_guard

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-test")

#: A child that asks the kernel for a route (sends nothing) and says what it got.
ROUTE_PROBE = (
    "import socket\n"
    "s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
    "connect = getattr(socket, '_nmas_real_connect', socket.socket.connect)\n"
    "try:\n"
    "    connect(s, ('192.0.2.1', 9)); print('ROUTE')\n"
    "except OSError as e:\n"
    "    print('NOROUTE', e.errno)\n")


class TestTheTestProcess:
    def test_a_non_loopback_connect_is_refused_by_the_harness(self):
        sock = socket.socket()
        sock.settimeout(0.05)
        with pytest.raises(network_guard.NetworkRefused):
            sock.connect(("192.0.2.1", 9))
        sock.close()

    def test_so_is_an_http_request(self):
        with pytest.raises(urllib.error.URLError) as info:
            urllib.request.urlopen("http://192.0.2.2:9/", timeout=0.05)
        assert isinstance(info.value.reason, network_guard.NetworkRefused)

    def test_loopback_is_still_the_kernels_answer(self):
        """Floor: the guard did not simply block everything. A closed loopback
        port is refused by the KERNEL, not by the harness."""
        sock = socket.socket()
        with pytest.raises(ConnectionRefusedError) as info:
            sock.connect(("127.0.0.1", 9))
        sock.close()
        assert not isinstance(info.value, network_guard.NetworkRefused)
        assert info.value.errno == errno.ECONNREFUSED


class TestTheMeasurement:
    """`confinement()` classifies what the kernel says; the three answers."""

    @staticmethod
    def _raising(code):
        def connect(sock, address):
            raise OSError(code, os.strerror(code))
        return connect

    def test_no_route_in_either_family_is_confined(self):
        confined, reason = network_guard.confinement(self._raising(errno.ENETUNREACH))
        assert confined is True and "no route" in reason

    def test_a_route_is_not_confined(self):
        confined, reason = network_guard.confinement(lambda sock, address: None)
        assert confined is False and "192.0.2.1" in reason

    def test_anything_else_is_unknown_never_confined(self):
        confined, reason = network_guard.confinement(self._raising(errno.EPERM))
        assert confined is None and "could not tell" in reason


class TestTheClaimHoldsForAChild:
    def test_what_this_run_reports_is_what_a_child_gets(self):
        """The property C46 is about: a process the test starts. The run's
        claim, whichever it is, must be true of a real child."""
        state, _ = network_guard.confinement()
        out = subprocess.run([sys.executable, "-c", ROUTE_PROBE], capture_output=True,
                             text=True, timeout=30).stdout.strip()
        if state is True:
            assert out.startswith("NOROUTE"), f"reported CONFINED, and a child got: {out}"
        else:
            assert out == "ROUTE", f"reported NOT confined, and a child got: {out}"

    def test_a_required_run_that_is_not_confined_stops(self):
        """With the requirement set, an unconfined session must stop before
        any test; a confined one must run. Either way, the child says which."""
        state, _ = network_guard.confinement()
        env = dict(os.environ, **{network_guard.REQUIRE_ENV: "1"})
        env.pop("NMAS_TEST_STORE_OWNER", None)
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "tests/test_network_guard.py::TestTheMeasurement::test_a_route_is_not_confined"],
            capture_output=True, text=True, cwd=ROOT, env=env, timeout=120)
        if state is True:
            assert done.returncode == 0, done.stdout[-500:]
        else:
            assert done.returncode == 2, done.stdout[-500:]
            assert network_guard.REQUIRE_ENV in done.stdout + done.stderr


class TestTheRunner:
    def test_it_requires_the_confinement_it_creates(self):
        """Anchored at the start of a line: the script's comments name the
        variable too."""
        with open(SCRIPT, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        assert any(re.match(r"\s+env NMAS_REQUIRE_NETWORK_CONFINEMENT=1 ", ln) for ln in lines)

    def test_it_never_runs_the_suite_as_root(self):
        """A test running as root passes every "refuses an unreadable file"
        check. The nested namespace maps back to the caller's own ids."""
        with open(SCRIPT, encoding="utf-8") as fh:
            text = fh.read()
        assert re.search(r'^\s+exec unshare --map-user="\$uid" --map-group="\$gid"', text, re.M)

    def test_an_unconfined_run_says_so_first(self):
        with open(SCRIPT, encoding="utf-8") as fh:
            text = fh.read()
        assert re.search(r'^\s+echo "nmas-test: network: NOT CONFINED: ', text, re.M)


#: The C46 address: the live NMAS, which on the deployment host is the host itself.
#: A documentation address since 2026-09-29 (the repository is public, and the
#: real one lives in data/lab_hosts.json): the guard refuses EVERY non-loopback
#: connect, so what it proves does not depend on which address is asked.
LIVE_NMAS = ("192.0.2.211", 5000)


class TestEveryProcessATestStarts:
    """Layer 3, by construction and on every machine, including the host,
    where no namespace can be made (C46)."""

    def test_a_python_child_with_a_bare_env_is_refused_and_recorded(self):
        """C46's own shape: an explicit env carrying only PATH and HOME."""
        guard = network_guard.spawn_guard()
        code = ("import socket\ns = socket.socket(); s.settimeout(3)\n"
                f"try:\n    s.connect({LIVE_NMAS!r}); print('CONNECTED')\n"
                "except OSError as e:\n    print('REFUSED', e)\n")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}, timeout=30)
        assert out.stdout.startswith("REFUSED") and "test harness refused" in out.stdout, out
        tried = guard.take()
        assert len(tried) == 1 and "192.0.2.211" in tried[0], tried

    def test_a_name_is_not_resolved_in_a_child(self):
        guard = network_guard.spawn_guard()
        out = subprocess.run([sys.executable, "-c",
                              "import socket\ntry:\n    socket.getaddrinfo('example.com', 80)\n"
                              "except OSError as e:\n    print('REFUSED', e)"],
                             capture_output=True, text=True, timeout=30)
        assert out.stdout.startswith("REFUSED"), out
        assert any("resolve 'example.com'" in t for t in guard.take())

    @pytest.mark.parametrize("argv", [["ssh", "-o", "BatchMode=yes", "u@192.0.2.5", "true"],
                                      ["curl", "-s", "http://192.0.2.6/"],
                                      ["rsync", "x", "192.0.2.7:/tmp/"]])
    def test_network_tools_are_refused_and_recorded(self, argv):
        guard = network_guard.spawn_guard()
        out = subprocess.run(argv, capture_output=True, text=True,
                             env={"PATH": "/usr/bin:/bin"}, timeout=30)
        assert out.returncode == 255 and "test harness refused" in out.stderr, out
        tried = guard.take()
        assert len(tried) == 1 and tried[0].startswith(argv[0] + "\t"), tried

    def test_git_may_use_local_paths_only(self, tmp_path):
        out = subprocess.run(["git", "clone", "-q", "ssh://u@192.0.2.8/r.git", str(tmp_path / "c")],
                             capture_output=True, text=True, timeout=30)
        assert out.returncode != 0 and "not allowed" in out.stderr, out.stderr
        network_guard.spawn_guard().take()
        local = subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / "o.git")],
                               capture_output=True, text=True)
        cloned = subprocess.run(["git", "clone", "-q", str(tmp_path / "o.git"), str(tmp_path / "l")],
                                capture_output=True, text=True)
        assert local.returncode == 0 and cloned.returncode == 0, cloned.stderr

    def test_a_fake_the_test_builds_is_run(self, tmp_path):
        """A recording `curl` in the test's own tmp_path is not a network."""
        fake = tmp_path / "bin" / "curl"
        fake.parent.mkdir()
        fake.write_text("#!/bin/sh\necho FAKE-CURL \"$@\"\n")
        fake.chmod(0o755)
        out = subprocess.run(["curl", "http://192.0.2.9/"], capture_output=True, text=True,
                             env={"PATH": f"{fake.parent}:/usr/bin:/bin"}, timeout=30)
        assert out.stdout.strip() == "FAKE-CURL http://192.0.2.9/", out
        assert network_guard.spawn_guard().take() == []

    def test_a_tool_outside_pytests_tree_is_not_a_fake(self):
        """Floor for the deferral: a directory the test did NOT build under
        pytest's temporary tree is refused, however it got onto PATH."""
        import shutil
        import tempfile
        outside = tempfile.mkdtemp(prefix="not-pytest-")
        try:
            tool = os.path.join(outside, "curl")
            with open(tool, "w") as fh:
                fh.write("#!/bin/sh\necho SHOULD-NOT-RUN\n")
            os.chmod(tool, 0o755)
            out = subprocess.run(["curl", "http://192.0.2.10/"], capture_output=True, text=True,
                                 env={"PATH": f"{outside}:/usr/bin:/bin"}, timeout=30)
            assert "SHOULD-NOT-RUN" not in out.stdout and out.returncode == 255, out
            assert len(network_guard.spawn_guard().take()) == 1
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_the_c46_case_cannot_reach_the_live_nmas(self, tmp_path):
        """The exact defect: the sync script via a symlink, NMAS_URL left at
        the script's default (the live NMAS). Refused by construction, not by
        this test's REPO happening to name nothing."""
        script = os.path.join(ROOT, "scripts", "oxidized-to-config.sh")
        link = tmp_path / "oxidized-to-config.sh"
        link.symlink_to(script)
        # The sanitiser has no host default since 2026-09-29: an unset NMAS_URL
        # comes from the hosts file, so the test gives it one naming LIVE_NMAS.
        # With no file it would refuse before asking anything, and this case
        # would pass without reaching the guard.
        hosts = tmp_path / "lab_hosts.json"
        hosts.write_text(json.dumps({"nmas": {"user": "op", "lan": LIVE_NMAS[0],
                                              "tunnel": "ssh-nmas.example.net"}}))
        out = subprocess.run(["bash", str(link), "--yes"], capture_output=True, text=True,
                             env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
                                  "REPO": str(tmp_path / "none"),
                                  "NMAS_LAB_HOSTS": str(hosts)},
                             cwd=str(tmp_path), timeout=60)
        assert "the NMAS could not be asked" in out.stdout, out.stdout
        tried = network_guard.spawn_guard().take()
        assert any("192.0.2.211" in t for t in tried), tried

    def test_the_wrapper_saw_the_suites_spawns(self):
        """Floor: a wrapper that is not on the spawn path counts nothing."""
        subprocess.run(["true"])
        assert network_guard.spawn_guard().spawned >= 1


class TestAnAttemptFailsTheTestThatMadeIt:
    def test_by_name_in_a_nested_run(self, tmp_path):
        """The per-test check, observed from outside: a test whose child
        tries the live NMAS fails, naming the attempt, even though the child's
        own error was swallowed."""
        probe = tmp_path / "test_reaches_out.py"
        probe.write_text(
            "import subprocess, sys\n"
            "def test_swallows_its_childs_error():\n"
            "    subprocess.run([sys.executable, '-c', 'import socket; s=socket.socket()\\n"
            "try:\\n    s.connect((\\'192.0.2.211\\', 5000))\\nexcept OSError: pass'])\n")
        env = {k: v for k, v in os.environ.items() if k != "NMAS_TEST_STORE_OWNER"}
        env["PYTHONPATH"] = ROOT
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               "-p", "tests.conftest", "--rootdir", str(tmp_path), str(probe)],
                              capture_output=True, text=True, cwd=ROOT, env=env, timeout=120)
        network_guard.spawn_guard().take()
        assert done.returncode == 1, done.stdout[-1500:]
        assert "did something no test may do" in done.stdout and "192.0.2.211" in done.stdout, done.stdout[-1500:]


def test_a_run_through_the_runner_writes_no_bytecode():
    """C120: a same-size mutation restored within the same second left a
    cached .pyc matching the restored file, so the next run executed the
    MUTATED code while the source read correct. The runner exports
    PYTHONDONTWRITEBYTECODE=1. Checked in THIS process, the one the runner
    started, and skipped under plain pytest, which is not the runner."""
    import os
    import sys

    if os.environ.get("NMAS_REQUIRE_NETWORK_CONFINEMENT") != "1":
        pytest.skip("not started by scripts/nmas-test")
    assert sys.dont_write_bytecode is True
    assert os.environ.get("PYTHONDONTWRITEBYTECODE") == "1"
