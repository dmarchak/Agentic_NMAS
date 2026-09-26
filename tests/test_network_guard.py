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
    "try:\n"
    "    s.connect(('192.0.2.1', 9)); print('ROUTE')\n"
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
