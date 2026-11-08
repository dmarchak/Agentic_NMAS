"""The controller app deploy channel's transport (P6; C2673): `modules/apps/transport.py`, the
session's guarded SFTP (`connection.open_sftp`), the host kind's one held write
(`discovery.held_write_refusal`) and the held write that runs them (`channel.held_write`).

Netmiko is faked at its boundary (`ConnectHandler`) and paramiko's SFTP client at the session's
`remote_conn_pre.open_sftp()`, so `open_ssh`, its write guard and the SFTP guard run for real.
The fake SFTP is an in-memory folder tree (FAKES at the seam, not captures: no controller has
been staged into yet); the fake command stands in for the apply script by running the script's
own `parse_request` on what was staged and answering an outcome in the script's shape.

Cases, each planted:
- the guard's allowed shapes, and each refusal in its words: `..`, an absolute part, a name or
  version outside the script's patterns, a path outside /opt/ryu-apps, a link on the way, a
  write while the device is not held, any session but the host kind's;
- the order: the files, then request.json, then the one command, then the outcome read;
- the command exactly, and every near miss of it refused even while held;
- a failure partway names what was staged and what was not, and nothing is deleted;
- the outcome is read and returned whole;
- an IPv4 and an IPv6 controller address both reach the fake.
"""

import hashlib
import io
import json
import os
import re
import stat
import threading
from types import SimpleNamespace

import pytest

from modules import connection as C
from modules import discovery
from modules.apps import channel, transport
from modules.inventory.management import HOST_DEPLOY
from modules.nsot import device_ops as D
from tests.test_controller_deploy import LISTEN, UNIT, enabled, eos, ls, show

LIST = "lab9"
ACTOR = "op@example.invalid"
ADDRESSES = ("192.0.2.10", "2001:db8::10")
ROOT = "/opt/ryu-apps"
REQUEST = "/opt/ryu-apps/.apply/request.json"
OUTCOME = "/var/lib/mercury-ryu-apply/outcome.json"
EVENTS = []


# ── the fakes at the seam ─────────────────────────────────────────────────────────────────────

class FakeFS:
    """The controller's folders as SFTP sees them: dirs, files (bytes), modes and links."""

    def __init__(self):
        self.dirs = {"/", "/opt", ROOT, "/var", "/var/lib", "/var/lib/mercury-ryu-apply"}
        self.files, self.modes, self.links = {}, {}, set()
        self.fail_on_write = None          # the n-th write raises (a transport failure)
        self.writes = 0


class FakeFile(io.BytesIO):
    def __init__(self, fs, path, mode):
        super().__init__(fs.files.get(path, b"") if "r" in mode else b"")
        self.fs, self.path, self.mode = fs, path, mode

    def close(self):
        if "w" in self.mode and not self.closed:
            self.fs.files[self.path] = self.getvalue()
        super().close()


class FakeSftp:
    def __init__(self, fs):
        self.fs = fs

    def lstat(self, path):
        if path in self.fs.links:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777)
        if path in self.fs.dirs:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755)
        if path in self.fs.files:
            return SimpleNamespace(st_mode=stat.S_IFREG | self.fs.modes.get(path, 0o644))
        raise FileNotFoundError(2, "No such file")

    def mkdir(self, path, mode=0o777):
        EVENTS.append(("mkdir", path))
        self.fs.dirs.add(path)

    def open(self, path, mode="r"):
        if "w" in mode:
            self.fs.writes += 1
            if self.fs.fail_on_write == self.fs.writes:
                raise OSError(5, "Input/output error (the fake's planted failure)")
            EVENTS.append(("write", path))
        else:
            EVENTS.append(("read", path))
            if path not in self.fs.files:
                raise FileNotFoundError(2, "No such file")
        return FakeFile(self.fs, path, mode)

    def chmod(self, path, mode):
        EVENTS.append(("chmod", path, mode))
        self.fs.modes[path] = mode

    def remove(self, path):                 # never called: the guard exposes no remove
        EVENTS.append(("remove", path))

    def close(self):
        pass


class FakeConn:
    """A Netmiko LinuxSSH session at its boundary; its apply command stands in for the script."""
    opened, sent = [], []
    fs = None
    answer = None                           # a function (fs) -> printed line, or None

    def __init__(self, **params):
        FakeConn.opened.append(dict(params))
        self.ip = params["ip"]
        self.remote_conn_pre = SimpleNamespace(open_sftp=lambda: FakeSftp(FakeConn.fs))

    def enable(self):
        pass

    def find_prompt(self):
        return "mercury@ctl:~$"

    def send_command(self, cmd, **kw):
        FakeConn.sent.append(cmd)
        EVENTS.append(("command", cmd))
        return (FakeConn.answer or script_ran)(FakeConn.fs)

    send_command_timing = send_command

    def disconnect(self):
        pass


def script_ran(fs):
    """The apply script's answer to what was staged: its own parser on request.json, the
    outcome written to OUTCOME_DIR/outcome.json and printed, as `main` does."""
    s = channel.script()
    if REQUEST not in fs.files:
        return '{"ok": false, "refused": "no request"}'
    req = s.parse_request(fs.files[REQUEST])
    outcome = {"ok": True, "step": "running", "request_sha256": s.request_sha256(req),
               "apps": req["apps"], "listen": req["listen"], "main_pid_before": "100",
               "main_pid_after": "200", "user": "ryu", "started": "2026-11-06T18:00:00Z",
               "finished": "2026-11-06T18:00:20Z", "unit": UNIT}
    line = json.dumps(outcome, sort_keys=True)
    fs.files[OUTCOME] = (line + "\n").encode("utf-8")
    return line


@pytest.fixture(autouse=True)
def fake_seams(monkeypatch):
    import netmiko

    EVENTS.clear()
    FakeConn.opened, FakeConn.sent, FakeConn.answer = [], [], None
    FakeConn.fs = FakeFS()
    monkeypatch.setattr(netmiko, "ConnectHandler", FakeConn)
    monkeypatch.setattr(C, "vty_lines", lambda ip: (5, "the test's host"))
    monkeypatch.setattr(C, "stored_connection_params",
                        lambda dev: C.connection_params(dev, password="p"))
    C._sessions.clear()
    yield
    C._sessions.clear()
    from tests import ssh_slot_guard
    ssh_slot_guard.release()
    with D._mu:
        stale = list(D._held.values())
        D._held.clear()
    for info in stale:
        if info["fd"] is not None:
            os.close(info["fd"])


def _open(driver="linux", ip=ADDRESSES[0]):
    return C.open_ssh(C.connection_params({"device_type": driver, "ip": ip,
                                           "username": "mercury"}, password="p"),
                      owner="test", plain=C.is_plain(driver))


def _plan(tmp_path, listen=LISTEN):
    got = channel.plan(network=LIST, controller="ctl", unit=UNIT, enabled=enabled(tmp_path),
                       host={"show": show("ryu"), "ls": ls("mercury"), "cat": ""},
                       listen=listen, switches=[eos()],
                       links=[], previous=None)
    assert got["ok"] is True, got["refusals"]
    return got


def _dev(ip=ADDRESSES[0], **over):
    return dict({"hostname": "ctl", "ip": ip, "device_type": "linux", "username": "mercury",
                 "password": "unused", "secret": ""}, **over)


def _held(ip=ADDRESSES[0]):
    return D.hold(LIST, "ctl", HOST_DEPLOY, ACTOR, ip=ip)


# ── 1. the guard's shapes ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path,kind", [
    ("/opt/ryu-apps/of_versions/1.0.0/of_versions.py", "file"),
    ("/opt/ryu-apps/of_versions/1.0.0/lib/helper.py", "file"),
    ("/opt/ryu-apps/switch_quirks/12.3.40/run.sh", "file"),
    ("/opt/ryu-apps/.apply/request.json", "file"),
    ("/opt/ryu-apps/of_versions", "dir"),
    ("/opt/ryu-apps/of_versions/1.0.0", "dir"),
    ("/opt/ryu-apps/of_versions/1.0.0/lib", "dir"),
    ("/opt/ryu-apps/.apply", "dir"),
    ("/opt/ryu-apps/of_versions/1.0.0.config.json", "file")])
def test_the_staging_shapes_are_allowed(path, kind):
    assert transport.staging_refusal(path, kind) == ""


@pytest.mark.parametrize("path,kind,words", [
    ("/opt/ryu-apps/of_versions/1.0.0/../../../etc/passwd", "file", "has the part '..'"),
    ("/opt/ryu-apps/of_versions/1.0.0/./x.py", "file", "has the part '.'"),
    ("/opt/ryu-apps/of_versions/1.0.0//etc/passwd", "file", "has an empty part 3 (an absolute "
                                                             "part or a doubled"),
    ("/opt/ryu-apps/of_versions/1.0.0/", "dir", "has an empty part 3"),
    ("/etc/sudoers.d/mercury", "file", "is not under /opt/ryu-apps"),
    ("/opt/ryu-apps-evil/a/1.0.0/a.py", "file", "is not under /opt/ryu-apps"),
    ("/opt/ryu-apps/Of_Versions/1.0.0/a.py", "file", "app name 'Of_Versions' does not match "
                                                      "^[a-z][a-z0-9_]{0,40}$"),
    ("/opt/ryu-apps/of_versions/1.0/a.py", "file", "version '1.0' does not match "
                                                    "^[0-9]+\\.[0-9]+\\.[0-9]+$"),
    ("/opt/ryu-apps/of_versions/1.0.0/a b.py", "file", "part 'a b.py' does not match"),
    ("/opt/ryu-apps/of_versions/1.0.0", "file", "is a version's folder, not a file in it"),
    ("/opt/ryu-apps/of_versions", "file", "is an app's folder, not a file"),
    ("/opt/ryu-apps/.apply/other.json", "file", "app name '.apply' does not match"),
    ("/opt/ryu-apps/.apply/request.json", "dir", "app name '.apply' does not match"),
    ("/opt/ryu-apps/of_versions/1.0.0/café.py", "file", "is not printable ASCII"),
    ("/opt/ryu-apps/of_versions/1.0.0/a.py", "link", "is neither a file nor a folder write"),
    ("/opt/ryu-apps/of_versions/1.0.config.json", "file", "version '1.0.config.json' does not "
                                                            "match"),
    ("/opt/ryu-apps/of_versions/1.0.0.config.json", "dir", "version '1.0.0.config.json'"),
    ("/opt/ryu-apps/of_versions/1.0.0.config.yml", "file", "version '1.0.0.config.yml'"),
    ("/opt/ryu-apps/.apply/1.0.0.config.json", "file", "app name '.apply'")])
def test_every_other_path_is_refused_naming_it_and_the_rule(path, kind, words):
    why = transport.staging_refusal(path, kind)
    assert why.startswith("REFUSED") and words in why and why.endswith("Nothing was sent.")
    if kind in ("file", "dir") and path.isascii():
        assert repr(path) in why
        assert "a file is written only to /opt/ryu-apps/<name>/<version>/<relative path>" in why


# ── 1. the guard on the session ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ip", ADDRESSES, ids=("ipv4", "ipv6"))
def test_a_write_while_not_held_is_refused_naming_the_path_and_nothing_lands(ip):
    sftp = C.open_sftp(_open(ip=ip))
    path = "/opt/ryu-apps/of_versions/1.0.0/of_versions.py"
    with pytest.raises(C.UnheldDeviceWrite) as e:
        sftp.write(path, b"x = 1\n")
    assert path in str(e.value) and ip in str(e.value) and "does not hold the device" in \
        str(e.value)
    with pytest.raises(C.UnheldDeviceWrite):
        sftp.mkdir("/opt/ryu-apps/of_versions")
    assert EVENTS == [] and FakeConn.fs.files == {}


def test_a_hold_on_another_address_does_not_cover_the_write():
    sftp = C.open_sftp(_open(ip=ADDRESSES[0]))
    with _held(ip=ADDRESSES[1]):
        with pytest.raises(C.UnheldDeviceWrite):
            sftp.write("/opt/ryu-apps/of_versions/1.0.0/of_versions.py", b"x")
    assert EVENTS == []


def test_a_held_write_to_a_staging_path_lands_with_its_mode():
    sftp = C.open_sftp(_open())
    with _held():
        assert sftp.mkdir("/opt/ryu-apps/of_versions") is True
        assert sftp.mkdir("/opt/ryu-apps/of_versions") is False      # there already
        sftp.mkdir("/opt/ryu-apps/of_versions/1.0.0")
        sftp.write("/opt/ryu-apps/of_versions/1.0.0/run.sh", b"#!/bin/sh\n", 0o755)
    assert FakeConn.fs.files["/opt/ryu-apps/of_versions/1.0.0/run.sh"] == b"#!/bin/sh\n"
    assert FakeConn.fs.modes["/opt/ryu-apps/of_versions/1.0.0/run.sh"] == 0o755


@pytest.mark.parametrize("path", ["/etc/sudoers.d/mercury",
                                  "/opt/ryu-apps/of_versions/1.0.0/../../../root/x",
                                  "/opt/ryu-apps/of_versions/1.0.0//etc/passwd"])
def test_a_held_write_outside_the_shapes_is_refused_and_nothing_lands(path):
    sftp = C.open_sftp(_open())
    with _held():
        with pytest.raises(C.FileWriteRefused) as e:
            sftp.write(path, b"x")
    assert repr(path) in str(e.value) and EVENTS == []


def test_a_link_on_the_way_is_refused_naming_it():
    FakeConn.fs.dirs.add("/opt/ryu-apps/of_versions")
    FakeConn.fs.links.add("/opt/ryu-apps/of_versions/1.0.0")
    sftp = C.open_sftp(_open())
    with _held():
        with pytest.raises(C.FileWriteRefused) as e:
            sftp.write("/opt/ryu-apps/of_versions/1.0.0/of_versions.py", b"x")
    assert "/opt/ryu-apps/of_versions/1.0.0 is a symbolic link on the way to " \
           "/opt/ryu-apps/of_versions/1.0.0/of_versions.py" in str(e.value)
    assert EVENTS == []


def test_a_mode_other_than_644_or_755_is_refused():
    sftp = C.open_sftp(_open())
    with _held():
        with pytest.raises(C.FileWriteRefused, match="mode 777"):
            sftp.write("/opt/ryu-apps/of_versions/1.0.0/a.py", b"x", 0o777)
    assert EVENTS == []


def test_only_the_outcome_file_is_read_back():
    FakeConn.fs.files[OUTCOME] = b"{}\n"
    sftp = C.open_sftp(_open())
    assert sftp.read(OUTCOME) == b"{}\n"
    with pytest.raises(C.FileWriteRefused, match="is not /var/lib/mercury-ryu-apply/outcome"):
        sftp.read("/etc/shadow")


def test_the_guarded_client_has_no_remove_rename_or_link():
    sftp = C.open_sftp(_open())
    for name in ("remove", "unlink", "rmdir", "rename", "symlink", "posix_rename", "put",
                 "putfo", "truncate", "utime", "chown"):
        assert not hasattr(sftp, name), name


#: A raw SFTP client over a session, anywhere but the guard: the session's paramiko client
#: (`remote_conn_pre`), or paramiko's SFTP classes, named in code.
RAW_SFTP = re.compile(r"\bremote_conn_pre\b|\bSFTPClient\b|\bSFTP\.from_transport\b|"
                      r"\.open_sftp_client\b")


def _raw_sftp_sites():
    from tests.source_index import tracked

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sites, scanned = [], 0
    for path in tracked("modules", "routes", "app.py", "scripts", suffix=".py"):
        scanned += 1
        rel = os.path.relpath(path, here)
        with open(path, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                if RAW_SFTP.search(line.split("#", 1)[0]) and rel != "modules/connection.py":
                    sites.append(f"{rel}:{n}")
    return sites, scanned


def test_no_code_but_the_guard_opens_sftp_over_a_session():
    assert RAW_SFTP.search("sftp = conn.remote_conn_pre.open_sftp()")     # the planted case
    assert RAW_SFTP.search("paramiko.SFTPClient.from_transport(t)")
    sites, scanned = _raw_sftp_sites()
    assert scanned > 300, scanned                                          # the floor
    assert sites == []


@pytest.mark.parametrize("driver", ["cisco_xe", "ovs_linux", "arista_eos"])
def test_no_other_session_carries_a_file_write(driver):
    conn = _open(driver)
    with pytest.raises(C.FileWriteRefused) as e:
        C.open_sftp(conn)
    assert f"a file write over a {driver} session" in str(e.value)


# ── the one command ───────────────────────────────────────────────────────────────────────────

def test_the_one_command_is_exactly_the_apply_script_with_nothing_else():
    assert channel.APPLY_COMMAND == "sudo -n /usr/local/sbin/mercury-ryu-apply"
    assert discovery.held_write_refusal("linux", channel.APPLY_COMMAND) == ""


@pytest.mark.parametrize("command", [
    "sudo -n /usr/local/sbin/mercury-ryu-apply --help",
    "sudo -n /usr/local/sbin/mercury-ryu-apply; id",
    "sudo -n /usr/local/sbin/mercury-ryu-apply ",
    " sudo -n /usr/local/sbin/mercury-ryu-apply",
    "sudo  -n /usr/local/sbin/mercury-ryu-apply",
    "sudo /usr/local/sbin/mercury-ryu-apply",
    "sudo -n /usr/local/sbin/mercury-ryu-apply\nid",
    "sudo -n /tmp/mercury-ryu-apply"])
def test_every_near_miss_is_refused_even_while_held(command):
    why = discovery.held_write_refusal("linux", command)
    assert why.startswith("REFUSED") and "P6" in why and repr(command[:80]) in why
    assert "is exactly sudo -n /usr/local/sbin/mercury-ryu-apply" in why
    conn = _open()
    with _held():
        with pytest.raises(C.DiscoveryOnly):
            conn.send_command(command)
    assert FakeConn.sent == []


def test_the_one_command_is_refused_while_not_held():
    conn = _open()
    with pytest.raises(C.DiscoveryOnly):
        conn.send_command(channel.APPLY_COMMAND)
    with _held():
        conn.send_command(channel.APPLY_COMMAND)
    assert FakeConn.sent == [channel.APPLY_COMMAND]


# ── 2. the transport: order, bytes, outcome ──────────────────────────────────────────────────

def test_files_then_the_request_then_the_one_command_then_the_outcome(tmp_path):
    plan = _plan(tmp_path)
    with _held():
        got = transport.send(_open(), plan, ip=ADDRESSES[0])
    assert got["ok"] is True, got["error"]
    writes = [e[1] for e in EVENTS if e[0] == "write"]
    base = "/opt/ryu-apps/of_versions/1.0.0"
    assert sorted(writes[:-1]) == [f"{base}/lib/helper.py", f"{base}/of_versions.py",
                                   f"{base}/run.sh"]
    assert writes[-1] == REQUEST
    kinds = [e[0] for e in EVENTS]
    assert kinds.index("command") > max(i for i, k in enumerate(kinds) if k == "write")
    assert EVENTS[-1] == ("read", OUTCOME)
    assert [e for e in EVENTS if e[0] == "command"] == [("command", channel.APPLY_COMMAND)]
    assert FakeConn.sent == [channel.APPLY_COMMAND]
    assert not [e for e in EVENTS if e[0] == "remove"]
    assert got["staged"] == writes[:-1] and got["not_staged"] == []
    assert got["request_written"] is True and got["command_sent"] is True


def test_what_lands_is_the_staged_bytes_and_the_script_s_request(tmp_path):
    plan = _plan(tmp_path)
    with _held():
        transport.send(_open(), plan, ip=ADDRESSES[0])
    fs, base = FakeConn.fs, "/opt/ryu-apps/of_versions/1.0.0"
    local = plan["folders"]["of_versions"]
    for rel in ("of_versions.py", "lib/helper.py", "run.sh"):
        with open(os.path.join(local, rel), "rb") as fh:
            assert fs.files[f"{base}/{rel}"] == fh.read()
    assert fs.modes[f"{base}/run.sh"] == 0o755 and fs.modes[f"{base}/of_versions.py"] == 0o644
    assert channel.script().parse_request(fs.files[REQUEST]) == plan["request"]


def test_the_outcome_is_read_and_returned_whole(tmp_path):
    plan = _plan(tmp_path)
    with _held():
        got = transport.send(_open(), plan, ip=ADDRESSES[0])
    assert got["outcome"] == json.loads(FakeConn.fs.files[OUTCOME])
    assert got["outcome"]["request_sha256"] == plan["request_sha256"]
    assert got["printed"] == got["outcome"]


def test_the_script_s_refusal_comes_back_whole_and_not_ok(tmp_path):
    words = "refused before the request was read: ryu-manager.service's User is 'root'"

    def refused(fs):
        line = json.dumps({"ok": False, "refused": words, "started": "s", "finished": "f",
                           "unit": UNIT}, sort_keys=True)
        fs.files[OUTCOME] = (line + "\n").encode()
        return line

    FakeConn.answer = refused
    with _held():
        got = transport.send(_open(), _plan(tmp_path), ip=ADDRESSES[0])
    assert got["ok"] is False and got["error"] == words
    assert got["outcome"] == {"ok": False, "refused": words, "started": "s", "finished": "f",
                              "unit": UNIT}


def test_an_outcome_another_run_wrote_is_not_this_run_s(tmp_path):
    def locked(fs):
        fs.files[OUTCOME] = b'{"ok": true, "started": "earlier"}\n'
        return json.dumps({"ok": False, "refused": "another apply holds the lock",
                           "outcome_not_written": "this run did not hold the lock",
                           "started": "now"})

    FakeConn.answer = locked
    with _held():
        got = transport.send(_open(), _plan(tmp_path), ip=ADDRESSES[0])
    assert got["ok"] is False and got["outcome"]["started"] == "now"
    assert "the file is another run's" in got["error"]


def test_a_file_that_is_not_the_printed_line_is_never_a_pass(tmp_path):
    def other(fs):
        fs.files[OUTCOME] = b'{"ok": true, "started": "earlier"}\n'
        return json.dumps({"ok": True, "started": "now"})

    FakeConn.answer = other
    with _held():
        got = transport.send(_open(), _plan(tmp_path), ip=ADDRESSES[0])
    assert got["ok"] is False
    assert "(started 'earlier') is not the line the script printed (started 'now')" in \
        got["error"]


# ── a failure partway, and refusals before anything is sent ──────────────────────────────────

def test_a_failure_partway_names_what_landed_and_deletes_nothing(tmp_path):
    FakeConn.fs.fail_on_write = 2
    plan = _plan(tmp_path)
    with _held():
        got = transport.send(_open(), plan, ip=ADDRESSES[0])
    assert got["ok"] is False and got["step"] == "stage"
    assert len(got["staged"]) == 1 and len(got["not_staged"]) == 2
    assert got["staged"][0] in FakeConn.fs.files
    assert not set(got["not_staged"]) & set(FakeConn.fs.files)
    assert got["request_written"] is False and got["command_sent"] is False
    assert "stopped at staging: OSError" in got["error"]
    assert "Staged 1 file(s), not staged 2; the request was not written; the command was not " \
           "sent. Nothing was deleted on the controller" in got["error"]
    assert FakeConn.sent == [] and REQUEST not in FakeConn.fs.files
    assert not [e for e in EVENTS if e[0] == "remove"] and got["deleted"] == []


def test_a_failure_writing_the_request_sends_no_command(tmp_path):
    FakeConn.fs.fail_on_write = 4                  # three files, then request.json
    with _held():
        got = transport.send(_open(), _plan(tmp_path), ip=ADDRESSES[0])
    assert got["step"] == "request" and len(got["staged"]) == 3
    assert got["request_written"] is False and FakeConn.sent == []


def test_a_command_that_fails_says_whether_the_script_ran_is_not_known(tmp_path):
    def broken(fs):
        raise OSError("Socket is closed")

    FakeConn.answer = broken
    with _held():
        got = transport.send(_open(), _plan(tmp_path), ip=ADDRESSES[0])
    assert got["ok"] is False and got["step"] == "command" and got["command_sent"] is True
    assert "whether the script ran is not known" in got["error"]
    assert "a placeholder, not measured" in got["error"]


def test_not_held_is_refused_before_anything_is_sent(tmp_path):
    got = transport.send(_open(), _plan(tmp_path), ip=ADDRESSES[0])
    assert got["ok"] is False and "does not hold the controller at 192.0.2.10" in got["error"]
    assert EVENTS == [] and FakeConn.sent == []


def test_a_staged_folder_changed_after_the_plan_is_refused_naming_both(tmp_path):
    plan = _plan(tmp_path)
    with open(os.path.join(plan["folders"]["of_versions"], "of_versions.py"), "ab") as fh:
        fh.write(b"import socket\n")
    with _held():
        got = transport.send(_open(), plan, ip=ADDRESSES[0])
    assert got["ok"] is False and EVENTS == [] and FakeConn.sent == []
    want = plan["request"]["apps"][0]["sha256"]
    assert f"not the plan's {want}: it changed after the plan" in got["error"]


def test_a_plan_listing_a_path_outside_the_shapes_is_refused_before_anything_is_sent(tmp_path):
    plan = _plan(tmp_path)
    plan["files"]["of_versions"][0] = dict(plan["files"]["of_versions"][0],
                                           path="../../../etc/sudoers.d/x")
    with _held():
        got = transport.send(_open(), plan, ip=ADDRESSES[0])
    assert got["ok"] is False and "has the part '..'" in got["error"] and EVENTS == []


def test_a_plan_that_is_not_ok_stages_nothing(tmp_path):
    with _held():
        got = transport.send(_open(), {"ok": False}, ip=ADDRESSES[0])
    assert "is not an approved plan" in got["error"] and EVENTS == []


# ── 2b. an app's start-time config (decision K9), and the put-back (decision K3) ─────────────

CONFIG = {"punt_table": 100, "meter_table": 100}
CONFIG_PATH = "/opt/ryu-apps/of_versions/1.0.0.config.json"


def _configured_plan(tmp_path, config=CONFIG):
    items = enabled(tmp_path)
    items[0]["config"] = config
    got = channel.plan(network=LIST, controller="ctl", unit=UNIT, enabled=items,
                       host={"show": show("ryu"), "ls": ls("mercury"), "cat": ""},
                       listen=LISTEN, switches=[eos()], links=[], previous=None)
    assert got["ok"] is True, got["refusals"]
    return got


def test_a_config_is_staged_beside_its_version_before_the_request(tmp_path):
    plan = _configured_plan(tmp_path)
    with _held():
        got = transport.send(_open(), plan, ip=ADDRESSES[0])
    assert got["ok"] is True, got["error"]
    writes = [e[1] for e in EVENTS if e[0] == "write"]
    assert writes[-2:] == [CONFIG_PATH, REQUEST]
    data = FakeConn.fs.files[CONFIG_PATH]
    assert data == plan["configs"]["of_versions"].encode() and FakeConn.fs.modes[CONFIG_PATH] \
        == 0o644
    req = channel.script().parse_request(FakeConn.fs.files[REQUEST])
    assert req["apps"][0]["config_sha256"] == hashlib.sha256(data).hexdigest()
    assert CONFIG_PATH in got["staged"]


def test_a_config_changed_after_the_plan_is_refused_naming_both(tmp_path):
    plan = _configured_plan(tmp_path)
    plan["configs"]["of_versions"] = '{"punt_table":0}\n'
    with _held():
        got = transport.send(_open(), plan, ip=ADDRESSES[0])
    want = plan["request"]["apps"][0]["config_sha256"]
    assert got["ok"] is False and EVENTS == [] and FakeConn.sent == []
    assert "config hashes " in got["error"] and f"not the request's {want}" in got["error"]


def test_a_config_the_request_does_not_name_is_refused(tmp_path):
    plan = _plan(tmp_path)
    plan["configs"] = {"of_versions": '{"punt_table":0}\n'}
    with _held():
        got = transport.send(_open(), plan, ip=ADDRESSES[0])
    assert got["ok"] is False and EVENTS == []
    assert "which the request names no config_sha256 for" in got["error"]


def test_the_put_back_stages_only_its_request_and_sends_the_one_command(tmp_path):
    s = channel.script()
    req = channel.put_back_request("[Service]\nUser=ryu\n")

    def put_back_ran(fs):
        got = s.parse_request(fs.files[REQUEST])
        line = json.dumps(dict(got, ok=True, step="running", started="now"), sort_keys=True)
        fs.files[OUTCOME] = (line + "\n").encode()
        return line

    FakeConn.answer = put_back_ran
    with _held():
        got = transport.send(_open(), {"ok": True, "request": req}, ip=ADDRESSES[0])
    assert got["ok"] is True, got["error"]
    assert [e[1] for e in EVENTS if e[0] == "write"] == [REQUEST]
    assert json.loads(FakeConn.fs.files[REQUEST]) == {
        "kind": "put-before-back", "before_sha256": s.before_sha256("[Service]\nUser=ryu\n")}
    assert FakeConn.sent == [channel.APPLY_COMMAND] and got["staged"] == []


# ── 3. the held write, by address ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ip", ADDRESSES, ids=("ipv4", "ipv6"))
def test_the_held_write_reaches_the_controller_at_either_address(tmp_path, ip):
    got = channel.held_write(_plan(tmp_path), list_name=LIST, dev=_dev(ip), actor=ACTOR)
    assert got["ok"] is True, got
    assert [o["ip"] for o in FakeConn.opened] == [ip]
    assert FakeConn.opened[0]["device_type"] == "linux"
    assert FakeConn.opened[0]["username"] == "mercury"
    assert FakeConn.sent == [channel.APPLY_COMMAND]
    assert D.holder(LIST, "ctl") is None and C._sessions.get(ip, {}) == {}


def test_an_ipv6_listen_address_reaches_the_request(tmp_path):
    plan = _plan(tmp_path, listen={"host": "2001:db8::10", "port": 6653})
    got = channel.held_write(plan, list_name=LIST, dev=_dev(ADDRESSES[1]), actor=ACTOR)
    assert got["ok"] is True
    assert json.loads(FakeConn.fs.files[REQUEST])["listen"] == {"host": "2001:db8::10",
                                                                "port": 6653}


@pytest.mark.parametrize("over,words", [
    ({"username": "admin"}, "login is 'admin', not the deploy account 'mercury'"),
    ({"device_type": "cisco_xe"}, "driver is 'cisco_xe', not 'linux'"),
    ({"hostname": "other"}, "the plan is for 'ctl', and the device is 'other'")])
def test_the_held_write_refuses_naming_both_operands(tmp_path, over, words):
    got = channel.held_write(_plan(tmp_path), list_name=LIST, dev=_dev(**over), actor=ACTOR)
    assert got["ok"] is False and words in got["refused"]
    assert FakeConn.opened == [] and EVENTS == []


def test_a_busy_controller_is_refused_by_name_never_queued(tmp_path):
    plan = _plan(tmp_path)
    started, done = threading.Event(), threading.Event()

    def other():
        with D.hold(LIST, "ctl", "read", "someone@example.invalid", ip=ADDRESSES[0]):
            started.set()
            done.wait(10)

    t = threading.Thread(target=other)
    t.start()
    try:
        assert started.wait(10)
        got = channel.held_write(plan, list_name=LIST, dev=_dev(), actor=ACTOR)
    finally:
        done.set()
        t.join(10)
    assert got["ok"] is False and "someone@example.invalid" in got["refused"]
    assert FakeConn.opened == [] and EVENTS == []


def test_a_host_is_held_for_the_deploy_channel_and_for_nothing_device_changing(monkeypatch):
    from modules import inventory
    host = _dev(role="host")
    monkeypatch.setattr(inventory, "cached_row",
                        lambda name, h: host if (name, h) == (LIST, "ctl") else None)
    with D.hold(LIST, "ctl", HOST_DEPLOY, ACTOR, ip=host["ip"]):
        assert D.holder(LIST, "ctl")["operation"] == HOST_DEPLOY
    with pytest.raises(D.NotManaged, match="mercury_kind is host"):
        D.acquire(LIST, "ctl", "deploy", ACTOR)
