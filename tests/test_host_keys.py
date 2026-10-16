"""C906: every session checks the device's SSH host key against Mercury's record, before any
credential is sent.

Against REAL SSH servers on loopback (paramiko's own server, each with its own RSA key, the
type the fleet's C8000v and vIOS present: `show crypto key mypubkey rsa`, 2026-10-16), through
the real opener (`connection.open_ssh`, a real Netmiko session) and the real NETCONF client
(ncclient), so "nothing was sent" is measured where it happens: the server records every
password it is offered.

- first contact keeps the key, its type and SHA256 fingerprint (as `ssh-keygen -l` prints it,
  compared with ssh-keygen itself), when, and who; the store is owner-only;
- the same key signs in again; a different key is refused naming both fingerprints, the
  server offered NO password, and the refusal is kept for Needs attention;
- an unreadable store, or one others may write, refuses every session rather than trusting;
- NETCONF verifies against the same record (a matching key reaches authentication, a
  different one is refused before it), never keeps a key of its own, and a refused NETCONF
  push stops the deploy instead of carrying on over SSH;
- a planned window that expects new host keys takes one new key per device, and never one
  Mercury refused before the window was declared;
- the re-key's read takes the key with no credential.
"""

import json
import os
import shutil
import socket
import stat
import subprocess
import threading
import time

import paramiko
import pytest

from modules import connection as C
from modules import host_keys as HK

IP = "127.0.0.1"
PW = "Hostkey-Test-Pw-9q2w"


class _Answer(paramiko.ServerInterface):
    def __init__(self, offered: list):
        self.offered = offered

    def get_allowed_auths(self, username):
        return "password"

    def check_auth_password(self, username, password):
        self.offered.append((username, password))
        return paramiko.AUTH_FAILED


class SSHServer:
    """An SSH server on loopback with one host key, refusing every sign-in and recording
    each password it was offered (`offered`): the measure of what a client SENT."""

    def __init__(self, key):
        self.key = key
        self.offered = []
        self.transports = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((IP, 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True, name="test-ssh-server")
        self.thread.start()

    def _serve(self):
        while not self.stopping.is_set():
            try:
                client, _ = self.sock.accept()
            except OSError:
                return
            if self.stopping.is_set():
                client.close()
                return
            t = paramiko.Transport(client)
            t.add_server_key(self.key)
            self.transports.append(t)
            try:
                t.start_server(event=threading.Event(), server=_Answer(self.offered))
            except Exception:                       # noqa: BLE001 - a client that left
                pass

    def close(self):
        """Stop the accept loop BEFORE the socket's number is freed (CI #848): closing a
        listening socket does not wake a thread blocked in `accept()` on Linux, so the loop
        outlived the test, and its next `accept()` could run on the freed number, which the
        next test's server took: it stole that server's connection, and werkzeug's own
        `accept()` (told a connection was waiting) blocked for good, hanging its shutdown.
        `shutdown()` wakes the blocked `accept()`; the loop is joined, then the socket closed."""
        self.stopping.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.thread.join(5)
        self.sock.close()
        for t in self.transports:
            t.close()
        assert not self.thread.is_alive(), "the test SSH server's accept loop outlived its test"


@pytest.fixture(scope="module")
def keys():
    """Three RSA host keys, generated for this run (a server needs its private half)."""
    return [paramiko.RSAKey.generate(2048) for _ in range(3)]


@pytest.fixture
def servers(keys):
    made = [SSHServer(k) for k in keys]
    yield made
    for s in made:
        s.close()


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr("modules.config.DATA_DIR", str(data))
    monkeypatch.setattr(C, "vty_lines", lambda ip: (5, "the test's device"))
    monkeypatch.setattr(HK, "names_for", lambda ip: [("Lab", "r9")] if ip == IP else [])
    C._sessions.clear()
    yield data
    C._sessions.clear()


def _held():
    """The record kept for the address, which the test expects to exist."""
    rec = HK.held(IP)
    assert rec is not None, "no key is held for the address"
    return rec


def _store_file(store):
    path = store / HK.STORE
    assert path.exists(), "nothing was written to the host-key record"
    return path


def _params(server, **over):
    return dict({"device_type": "cisco_ios", "ip": IP, "username": "admin", "password": PW,
                 "secret": PW, "port": server.port, "fast_cli": False, "conn_timeout": 10,
                 "banner_timeout": 10, "auth_timeout": 10}, **over)


def _sign_in(server, owner="test:session"):
    """One session through the ONE opener: these servers refuse every password, so a session
    that got as far as signing in raises Netmiko's authentication failure."""
    from netmiko.exceptions import NetmikoAuthenticationException
    with pytest.raises(NetmikoAuthenticationException):
        C.open_ssh(_params(server), owner=owner)


def _ssh_keygen_fingerprint(key, tmp_path) -> str:
    """The fingerprint as OpenSSH's own tool prints it: the control's expectation, by a path
    independent of the code under test."""
    if not shutil.which("ssh-keygen"):
        pytest.skip("ssh-keygen is not installed here")
    pub = tmp_path / "key.pub"
    pub.write_text(f"{key.get_name()} {key.get_base64()}\n")
    out = subprocess.run(["ssh-keygen", "-l", "-E", "sha256", "-f", str(pub)],
                         capture_output=True, text=True, check=True).stdout
    return out.split()[1]


class TestFirstContactKeepsTheKey:
    def test_it_is_kept_with_its_type_fingerprint_when_and_who(self, servers, keys, tmp_path):
        before = time.time()
        _sign_in(servers[0], owner="test:first-contact")
        rec = _held()
        assert rec["type"] == "ssh-rsa"
        assert rec["fingerprint"] == _ssh_keygen_fingerprint(keys[0], tmp_path)
        assert rec["how"] == HK.FIRST_CONTACT and rec["history"] == []
        assert HK._epoch(rec["kept_at"]) >= int(before)
        # No operation holds the device and no person is verified in this thread: said so,
        # with the code that opened the session.
        assert rec["kept_by"] == "no verified person (test:first-contact)"
        assert servers[0].offered == [("admin", PW)], "kept, then it signed in"

    def test_the_operation_holding_the_device_is_who(self, servers):
        from modules.nsot import device_ops
        with device_ops.hold("Lab", "r9", "persist", "alex@example.invalid", ip=IP):
            _sign_in(servers[0], owner="persist:apply")
        assert _held()["kept_by"] == "alex@example.invalid (persist; persist:apply)"

    def test_the_store_is_owner_only(self, servers, store):
        _sign_in(servers[0])
        mode = stat.S_IMODE(os.stat(_store_file(store)).st_mode)
        assert mode == 0o600, oct(mode)


class TestTheSameKeyPasses:
    def test_a_second_session_signs_in_and_changes_nothing(self, servers, store):
        _sign_in(servers[0])
        first = _store_file(store).read_bytes()
        _sign_in(servers[0])
        assert servers[0].offered == [("admin", PW), ("admin", PW)]
        assert _store_file(store).read_bytes() == first, "a match writes nothing"


class TestAChangedKeyIsRefused:
    def test_both_fingerprints_are_named_and_nothing_is_sent(self, servers, keys, tmp_path):
        _sign_in(servers[0], owner="test:first")
        with pytest.raises(HK.HostKeyRefused) as got:
            C.open_ssh(_params(servers[1]), owner="reader:capture")
        said = str(got.value)
        held = _ssh_keygen_fingerprint(keys[0], tmp_path)
        offered = _ssh_keygen_fingerprint(keys[1], tmp_path)
        assert f"r9 ({IP}) answered with SSH host key {offered} (ssh-rsa)" in said
        assert f"where Mercury holds {held} (ssh-rsa, kept " in said
        assert "nothing was sent" in said
        assert servers[1].offered == [], "the credential never reached the other key"
        # The refusal is kept for Needs attention; the held key is unchanged.
        rec = _held()
        assert rec["fingerprint"] == held
        assert "refused" in rec, "the refusal was not recorded"
        assert rec["refused"]["fingerprint"] == offered and rec["refused"]["count"] == 1
        assert "reader:capture" in rec["refused"]["by"]
        # Nothing is left counted against the device's budget.
        assert C.held_sessions() == {}

    def test_it_is_never_retried_as_a_transport_that_did_not_come_up(self, servers):
        _sign_in(servers[0])
        with pytest.raises(HK.HostKeyRefused):
            C.open_ssh(_params(servers[1]))
        assert len(servers[1].transports) == 1, "one connection, never a second try"

    def test_the_held_key_again_clears_the_refusal(self, servers):
        _sign_in(servers[0])
        with pytest.raises(HK.HostKeyRefused):
            C.open_ssh(_params(servers[1]))
        _sign_in(servers[0])
        assert "refused" not in HK.held(IP)


class TestAnUnreadableStoreRefuses:
    @pytest.mark.parametrize("content", ["{not json", "[]", '{"version": 1}'])
    def test_nothing_is_kept_and_nothing_sent(self, servers, store, content):
        (store / HK.STORE).write_text(content)
        os.chmod(store / HK.STORE, 0o600)
        with pytest.raises(HK.HostKeyStoreUnreadable) as got:
            C.open_ssh(_params(servers[0]))
        assert "could not be read" in str(got.value) or "not a host-key record" in str(got.value)
        assert servers[0].offered == []
        assert _store_file(store).read_text() == content, "the record is left for a person"

    def test_a_record_others_may_write_is_not_trusted(self, servers, store):
        _sign_in(servers[0])
        os.chmod(_store_file(store), 0o666)
        with pytest.raises(HK.HostKeyStoreUnreadable) as got:
            C.open_ssh(_params(servers[0]))
        assert "may be written by others (mode 666" in str(got.value)
        assert servers[0].offered == [("admin", PW)], "only the first session signed in"


class TestOneKeptUnderConcurrentFirstContacts:
    def test_one_key_wins_and_every_other_is_refused(self, keys):
        """Several sessions meeting an unrecorded device at once: the record's read-modify-
        write is one lock, so exactly one key is kept and the others are refused."""
        outcomes = []

        def meet(k):
            try:
                outcomes.append(HK.check(IP, k, owner="test")["state"])
            except HK.HostKeyRefused:
                outcomes.append("refused")

        threads = [threading.Thread(target=meet, args=(keys[i % 3],)) for i in range(9)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        kept = _held()["fingerprint"]
        winners = [k for k in keys if HK.offered(k)["fingerprint"] == kept]
        assert len(winners) == 1
        assert outcomes.count("kept") == 1
        assert outcomes.count("refused") == 6 and outcomes.count("matched") == 2


class TestNetconfUsesTheRecord:
    @pytest.fixture(autouse=True)
    def no_agent(self, monkeypatch, tmp_path):
        """ncclient offers agent and ~/.ssh keys before the password: none here."""
        monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))

    def _push(self, monkeypatch, server):
        from modules import pipeline
        monkeypatch.setattr(HK, "NETCONF_PORT", server.port)
        dev = {"ip": IP, "username": "admin", "password": PW, "hostname": "r9"}
        return pipeline._push_via_netconf(dev, ["logging buffered 64000"])

    def test_a_matching_key_reaches_authentication(self, servers, monkeypatch):
        from ncclient.transport.errors import AuthenticationError
        _sign_in(servers[0])
        with pytest.raises(AuthenticationError):
            self._push(monkeypatch, servers[0])
        assert ("admin", PW) in servers[0].offered[1:], "NETCONF signed in to the held key"

    def test_a_different_key_is_refused_before_authentication(self, servers, monkeypatch):
        _sign_in(servers[0])
        with pytest.raises(HK.HostKeyRefused) as got:
            self._push(monkeypatch, servers[1])
        assert servers[1].offered == []
        said = str(got.value)
        held = _held()
        assert f"where Mercury holds MD5 {HK.md5_of(servers[0].key.asbytes())}" in said
        assert held["fingerprint"] in said
        assert f"whose MD5 is {HK.md5_of(servers[1].key.asbytes())}" in said
        assert "refused" in held, "the NETCONF refusal was not recorded"
        assert held["refused"]["port"] == HK.NETCONF_PORT

    def test_ncclient_s_iosxe_handler_alone_would_sign_in_to_any_key(self, servers):
        """Why `host_keys._pinned_handler` exists, measured: with `hostkey_verify=True`, the
        held key as `hostkey_b64` and an unknown-host answer of False, ncclient's own IOS-XE
        handler replaces that answer with one that accepts, and signs in to a DIFFERENT
        key."""
        from ncclient import manager
        from ncclient.transport.errors import AuthenticationError
        with pytest.raises(AuthenticationError):
            manager.connect(host=IP, port=servers[1].port, username="admin", password=PW,
                            hostkey_verify=True, hostkey_b64=servers[0].key.get_base64(),
                            unknown_host_cb=lambda host, fingerprint: False,
                            device_params={"name": "iosxe"}, allow_agent=False,
                            look_for_keys=False, timeout=10)
        assert servers[1].offered == [("admin", PW)], "the password went to the other key"

    def test_netconf_keeps_no_key_of_its_own(self, servers, monkeypatch):
        with pytest.raises(HK.HostKeyRefused) as got:
            self._push(monkeypatch, servers[0])
        assert "NETCONF never keeps one" in str(got.value)
        assert servers[0].offered == [] and HK.held(IP) is None

    def test_a_refused_netconf_push_stops_the_deploy(self, monkeypatch):
        """Not carried on over SSH as if a transport had failed (`_push_config`)."""
        from modules import pipeline
        monkeypatch.setattr("modules.nsot.deploy.transport_for", lambda p: "netconf")

        def refused(dev, cmds):
            raise HK.HostKeyRefused("r9 answered NETCONF with another key", ip=IP)
        monkeypatch.setattr(pipeline, "_push_via_netconf", refused)
        over_ssh = []
        monkeypatch.setattr(pipeline, "_push_via_netmiko", lambda *a: over_ssh.append(a))
        with pytest.raises(HK.HostKeyRefused):
            pipeline._push_config({"ip": IP, "platform": "x"}, ["x"], {}, threading.Lock())
        assert over_ssh == []


class TestAPlannedWindowThatExpectsNewKeys:
    def _window(self, new_host_keys=True, start=None):
        from modules import restarts
        now = time.time() if start is None else start
        out = restarts.record_planned(["r9"], now - 60, now + 600, "op@example.invalid",
                                      "lab redeploy", "test", list_name="Lab",
                                      new_host_keys=new_host_keys)
        assert out["ok"], out

    def test_it_takes_one_new_key_per_device(self, keys):
        HK.check(IP, keys[0], owner="test")
        self._window()
        assert HK.check(IP, keys[1], owner="test")["state"] == "window"
        rec = _held()
        assert rec["fingerprint"] == HK.offered(keys[1])["fingerprint"]
        assert rec["how"] == HK.WINDOW and rec["window"]["by"] == "op@example.invalid"
        assert rec["history"][0]["fingerprint"] == HK.offered(keys[0])["fingerprint"]
        with pytest.raises(HK.HostKeyRefused):
            HK.check(IP, keys[2], owner="test")

    def test_a_window_that_does_not_say_so_takes_none(self, keys):
        HK.check(IP, keys[0], owner="test")
        self._window(new_host_keys=False)
        with pytest.raises(HK.HostKeyRefused):
            HK.check(IP, keys[1], owner="test")

    def test_a_window_declared_after_the_refusal_does_not_take_that_key(self, keys):
        HK.check(IP, keys[0], owner="test")
        with pytest.raises(HK.HostKeyRefused):
            HK.check(IP, keys[1], owner="test")
        time.sleep(1.1)                 # the record's times are to the second
        self._window()
        with pytest.raises(HK.HostKeyRefused):
            HK.check(IP, keys[1], owner="test")

    def test_the_api_declares_it(self, monkeypatch):
        """`"new_host_keys": true` in `POST /restarts/planned` (the command's
        `--new-host-keys` passes the same argument to the same writer)."""
        import app as A
        from modules import restarts
        monkeypatch.setattr("modules.device.get_device_lists",
                            lambda: [{"name": "Lab", "filename": "lab"}])
        r = A.app.test_client().post("/restarts/planned", json={
            "list": "Lab", "devices": ["r9"], "minutes": 30, "why": "lab redeploy",
            "new_host_keys": True})
        assert r.status_code == 200, r.get_data(as_text=True)
        assert restarts.planned_rows()[-1]["new_host_keys"] is True
        bad = A.app.test_client().post("/restarts/planned", json={
            "list": "Lab", "devices": ["r9"], "minutes": 30, "why": "x", "new_host_keys": "yes"})
        assert bad.status_code == 400 and "true or false" in bad.get_json()["error"]


class TestTheReKeyReadsWithNoCredential:
    def test_read_host_key_takes_the_key_and_sends_nothing(self, servers, keys, tmp_path):
        got = C.read_host_key(IP, port=servers[1].port, owner="rekey:preview", timeout=10)
        assert got["fingerprint"] == _ssh_keygen_fingerprint(keys[1], tmp_path)
        assert got["type"] == "ssh-rsa" and got["key"] == keys[1].get_base64()
        assert servers[1].offered == [] and C.held_sessions() == {}
        assert HK.held(IP) is None, "a read compares and keeps nothing"


class TestReplaceIsCompareAndSwap:
    def test_a_held_key_that_moved_is_not_replaced(self, keys):
        """A key kept under a window by another session between a re-key's plan and its keep:
        the replace names what it holds now and changes nothing."""
        HK.check(IP, keys[0], owner="test")
        got = HK.replace(IP, expected=HK.offered(keys[1])["fingerprint"],
                         new=HK.offered(keys[2]), by="p@example.invalid", why="test")
        assert got["ok"] is False
        assert HK.offered(keys[0])["fingerprint"] in got["error"]
        assert HK.offered(keys[1])["fingerprint"] in got["error"]
        assert _held()["fingerprint"] == HK.offered(keys[0])["fingerprint"]

    def test_the_expected_key_is_replaced_and_kept_in_history(self, keys):
        HK.check(IP, keys[0], owner="test")
        got = HK.replace(IP, expected=HK.offered(keys[0])["fingerprint"],
                         new=HK.offered(keys[2]), by="p@example.invalid", why="rebuilt")
        assert got["ok"] is True
        rec = _held()
        assert rec["fingerprint"] == HK.offered(keys[2])["fingerprint"]
        assert rec["history"][-1]["replaced_why"] == "rebuilt"


class TestATelnetDriverIsRefused:
    def test_no_host_key_means_no_session(self, servers):
        with pytest.raises(HK.HostKeyRefused) as got:
            C.open_ssh(_params(servers[0], device_type="cisco_ios_telnet"))
        assert "telnet session" in str(got.value) and "in clear" in str(got.value)
        assert C.held_sessions() == {}


class TestTheRecordIsJsonKeyedByAddress:
    def test_its_shape(self, servers, store):
        _sign_in(servers[0])
        doc = json.loads(_store_file(store).read_text())
        assert doc["version"] == HK.VERSION and list(doc["keys"]) == [IP]
        assert set(doc["keys"][IP]) >= {"type", "fingerprint", "key", "kept_at", "kept_by",
                                         "how", "port", "history"}
        assert PW not in _store_file(store).read_text(), "no credential in the record"
