"""The collector's close helper, `deploy/collector/mercury-collector-close` (C3078; the
operator's approval and conditions of 2026-11-11), and the host step that installs it.

The helper is loaded as a module, as tests/test_controller_apply.py loads the controller's apply
script, with its configuration, request and outcome in a temporary root. No test runs as root:
the uid the helper holds its configuration to (`ROOT_UID`) is the test's own, and another owner
is planted by naming another uid or through the open file's stat. Its clocks, its sleep and its
journal are stand-ins. `ss` is a stand-in over REAL captures (tests/fixtures/collector_close/,
its README naming how each was made): it applies the filter the helper sent to the rows `ss`
printed, by a parse of its own, removes a row when the helper sends the close, and records every
argv. A test of the stand-in holds it to what the real `ss` printed for the same argv.

The operator's seven, each refused with its own code and words: a wrong listener, a peer not in
the list, two matches, zero matches, a stale request, a symlink, a non-numeric port.
"""

import ast
import contextlib
import fcntl
import importlib.machinery
import importlib.util
import io
import itertools
import json
import os
import pwd
import re
import stat
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "deploy", "collector", "mercury-collector-close")
HOST_STEP = os.path.join(ROOT, "scripts", "host-steps", "c3078-collector-close-install.sh")
FIX = os.path.join(ROOT, "tests", "fixtures", "collector_close")
ME = pwd.getpwuid(os.getuid()).pw_name
LISTENER, PEER, PORT = "192.0.2.10:57000", "192.0.2.6", "56221"
OTHER_PEER = "192.0.2.7"
NOW = 1_794_400_000.0
_names = itertools.count()


def capture(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="ascii") as fh:
        return fh.read()


def _end(text: str) -> tuple:
    """One end of a captured row, ``(address, port)``; an IPv4-mapped IPv6 end as its IPv4
    address, which is how the real `ss` matched an IPv4 filter (dual_stack.txt)."""
    host, port = text.rsplit(":", 1)
    host = host.strip("[]")
    return (host[len("::ffff:"):] if host.startswith("::ffff:") else host), port


class Ss:
    """`ss` as the helper runs it, over the captured rows of one namespace: `-4` reads the
    IPv4 sockets' table, without it every socket's. A find prints the rows the filter names;
    a close (`-K`) removes them when *closes*, and prints nothing."""

    def __init__(self, path, *, closes=True, close_exit=0):
        self.path, self.closes, self.close_exit, self.calls = path, closes, close_exit, []
        self.table4 = capture("established_all_4.txt").splitlines()
        self.table = capture("established_all.txt").splitlines()

    def closes_sent(self) -> list:
        return [c for c in self.calls if "-K" in c]

    def __call__(self, argv):
        self.calls.append(list(argv))
        assert argv[0] == self.path, "the program is the configuration's ss, by its path"
        at = argv.index("state")
        options, words = argv[1:at], argv[at:]
        assert words[:2] == ["state", "established"]
        f = words[2:]
        assert len(f) == 13 and (f[0], f[2], f[3], f[4], f[6], f[7], f[9], f[10], f[11]) == (
            "src", "and", "sport", "=", "and", "dst", "and", "dport", "="), f
        want = ((f[1], f[5][1:]), (f[8], f[12][1:]))

        def named(line):
            cols = line.split()
            return (_end(cols[2]), _end(cols[3])) == want

        hit = [line for line in (self.table4 if "-4" in options else self.table) if named(line)]
        if "-K" in options:
            if self.closes:
                self.table4 = [line for line in self.table4 if not named(line)]
                self.table = [line for line in self.table if not named(line)]
            return self.close_exit, "", ""
        return 0, "".join(line + "\n" for line in hit), ""


class Clock:
    """The monotonic clock and the sleep: time passes only when the helper sleeps."""

    def __init__(self):
        self.t, self.slept = 500.0, []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds


def pristine():
    """The helper as its file is: its installed constants untouched."""
    loader = importlib.machinery.SourceFileLoader(f"mercury_collector_close_{next(_names)}",
                                                  SCRIPT)
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(m)
    return m


def config_of(m) -> dict:
    with open(m.CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def put_config(m, doc=None, raw=None, mode=0o644, **changes):
    doc = dict(config_of(m) if doc is None else doc, **changes)
    with open(m.CONFIG_PATH, "wb") as fh:
        fh.write(raw if raw is not None else json.dumps(doc).encode())
    os.chmod(m.CONFIG_PATH, mode)


def load(tmp_path, *, listener=LISTENER, peers=(PEER, OTHER_PEER), service_user=ME):
    """A fresh copy of the helper, its files in *tmp_path*, its `ss`, clocks and journal
    stand-ins. "root" is the user running the test."""
    m = pristine()
    m.ROOT_UID, m.REQUIRE_ROOT = os.getuid(), False
    etc, var = tmp_path / "etc" / "mercury", tmp_path / "var"
    for folder, mode in ((etc, 0o755), (var, 0o755), (var / "request", 0o700)):
        folder.mkdir(parents=True)
        os.chmod(folder, mode)
    ss = tmp_path / "ss"
    ss.write_text("#!/bin/sh\nexit 0\n")
    os.chmod(ss, 0o755)
    m.CONFIG_PATH = str(etc / "collector-close.conf")
    address, port = listener.rsplit(":", 1)
    put_config(m, {"listener": {"address": address, "port": int(port)}, "peers": list(peers),
                   "service_user": service_user, "ss": str(ss),
                   "request": str(var / "request" / "request.json"),
                   "outcome": str(var / "outcome.json")})
    clock = Clock()
    m.now, m.monotonic, m.sleep, m.clock = (lambda: NOW), clock, clock.sleep, clock
    m.own_run, m.own_journal = m.run, m.journal
    m.run = Ss(str(ss))
    m.journalled = []
    m.journal = lambda outcome: m.journalled.append(json.loads(json.dumps(outcome))) or True
    return m


def put_request(m, *, age=10, raw=None, **changes):
    """A request written *age* seconds before the helper's clock reads it."""
    doc = {"id": "run-1", "peer": PEER, "port": PORT, "dry_run": False}
    doc.update(changes)
    path = config_of(m)["request"]
    with open(path, "wb") as fh:
        fh.write(raw if raw is not None else json.dumps(doc).encode())
    os.utime(path, (NOW - age, NOW - age))
    return path


def go(m, argv=()) -> dict:
    """The helper's main; its printed outcome, which is also its exit code's and, when it
    wrote one, its outcome file's."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        code = m.main(list(argv))
    lines = printed.getvalue().splitlines()
    assert len(lines) == 1, "one line, the outcome"
    out = json.loads(lines[0])
    assert out["exit"] == code == m.EXITS[out["code"]]
    assert m.journalled[-1] == out, "the journal holds the same line"
    if "outcome_not_written" not in out:
        with open(config_of(m)["outcome"], encoding="utf-8") as fh:
            assert json.loads(fh.read()) == out
    return out


def refused(m, code, argv=()) -> str:
    """A run refused as *code*: not ok, its own exit code, and no close sent."""
    out = go(m, argv)
    assert (out["ok"], out["code"]) == (False, code), out
    assert out["exit"] not in (0, 1), "0 is a close and 1 is sudo's own refusal"
    if isinstance(m.run, Ss):
        assert not m.run.closes_sent(), "a refusal sends no close"
    assert out["words"].endswith("Nothing was closed")
    return out["words"]


def session(m, peer=PEER, port=PORT) -> tuple:
    return (_end(LISTENER), (peer, port))


def listed(m, table=None) -> list:
    return [(_end(c[2]), _end(c[3])) for c in (line.split() for line in
                                                (m.run.table4 if table is None else table))]


# ── the stand-in is held to the real `ss` ─────────────────────────────────────────────────────

def test_the_stand_in_answers_as_the_real_ss_did_for_the_same_argv(tmp_path):
    m = load(tmp_path)
    cfg = config_of(m)

    def rows(text):
        return [line.split() for line in text.splitlines()]

    one = {"peer": PEER, "port": 56221}
    assert rows(m.run(m.list_argv(cfg, one))[1]) == rows(capture("one_session.txt")) != []
    none = {"peer": PEER, "port": 56222}
    assert m.run(m.list_argv(cfg, none))[1] == capture("no_session.txt") == ""
    dual = dict(cfg, listener={"address": "192.0.2.10", "port": 57002})
    assert m.run(m.list_argv(dual, none))[1] == ""
    assert rows(m.run(m.list_argv(dual, none, ipv4_only=False))[1]) \
        == rows(capture("dual_stack.txt")) != []


def test_the_captures_readme_names_the_helper_s_own_find(tmp_path):
    m = load(tmp_path)
    argv = m.list_argv(config_of(m), {"peer": PEER, "port": 56221})
    with open(os.path.join(FIX, "README.md"), encoding="utf-8") as fh:
        assert "`ss " + " ".join(argv[1:]) + "`" in fh.read()


# ── the close ─────────────────────────────────────────────────────────────────────────────────

FIND = ["-H", "-4", "-t", "-n", "state", "established", "src", "192.0.2.10", "and", "sport",
        "=", ":57000", "and", "dst", "192.0.2.6", "and", "dport", "=", ":56221"]
CLOSE = FIND[:4] + ["-K"] + FIND[4:]


def test_a_close_sends_one_command_naming_all_four_ends_and_reads_back_gone(tmp_path):
    m = load(tmp_path)
    path = put_request(m)
    before = listed(m)
    out = go(m)
    ss = config_of(m)["ss"]
    assert (out["ok"], out["code"], out["exit"]) == (True, "closed", 0)
    assert m.run.calls == [[ss] + FIND, [ss] + CLOSE, [ss] + FIND], \
        "the find, ONE close with the same filter, the read-back"
    assert out["tuple"] == {"local": LISTENER, "peer": "192.0.2.6:56221"}
    assert (out["id"], out["dry_run"], out["listed"]) == ("run-1", False, 1)
    assert out["words"] == (
        "closed the established session from 192.0.2.6:56221 to 192.0.2.10:57000: one was "
        f"listed before `{ss} {' '.join(CLOSE)}`, which ran (exit 0), and none 0.0 s after it "
        "(1 read)")
    assert (out["request_written"], out["started"], out["finished"]) == (
        "2026-11-11T12:26:30Z", "2026-11-11T12:26:40Z", "2026-11-11T12:26:40Z")
    assert not os.path.exists(path), "a request is acted on once"
    assert [s for s in before if s not in listed(m)] == [session(m)], \
        "exactly the requested session is gone"


def test_a_session_of_another_listener_port_or_address_is_never_touched(tmp_path):
    """The operator's "wrong listener": the same peer and port hold a session to another port
    of the listener's address and to the same port of another address (the capture's own
    rows), and both are there after the close."""
    m = load(tmp_path)
    put_request(m)
    others = [(("192.0.2.10", "57001"), (PEER, PORT)), (("198.51.100.10", "57000"), (PEER, PORT))]
    assert all(o in listed(m) for o in others)
    assert go(m)["code"] == "closed"
    assert all(o in listed(m) for o in others) and session(m) not in listed(m)


def test_a_request_cannot_name_a_listener(tmp_path):
    m = load(tmp_path)
    put_request(m, listener={"address": "198.51.100.10", "port": 57000})
    assert refused(m, "refused_listener") == (
        "the request names a listener, and a request cannot: the listener is the "
        "configuration's, 192.0.2.10:57000. Nothing was closed")
    assert m.run.calls == [], "nothing was asked of ss"


def test_a_row_of_another_local_end_refuses_the_whole_run(tmp_path):
    """An `ss` that does not hold the filter lists the namespace's every session: the first
    row that is not the listener's refuses the run, naming both ends, and no close is sent
    (the close runs with the same filter)."""
    m = load(tmp_path)
    put_request(m)
    asked = []
    m.run = lambda argv: asked.append(argv) or (0, capture("established_all_4.txt"), "")
    out = go(m)
    assert (out["ok"], out["code"], out["exit"]) == (False, "refused_listener", 35)
    assert out["words"] == (
        '`ss` listed a session whose local end is "192.0.2.10:57001", not the configured '
        "listener 192.0.2.10:57000, though the filter named the listener alone: a close with "
        "that filter could close a session that is not the listener's. Nothing was closed")
    assert len(asked) == 1 and "-K" not in asked[0]


def test_a_row_of_another_peer_refuses_the_whole_run(tmp_path):
    m = load(tmp_path)
    put_request(m)
    rows = capture("established_all_4.txt").splitlines()
    two = [r for r in rows if r.split()[2] == LISTENER]
    assert len(two) == 2, "the capture's two sessions to the listener"
    asked = []
    m.run = lambda argv: asked.append(argv) or (0, "\n".join(two) + "\n", "")
    out = go(m)
    assert (out["ok"], out["code"], out["exit"]) == (False, "filter_not_held", 42)
    assert 'whose peer is "192.0.2.7:51522", not the requested 192.0.2.6:56221' in out["words"]
    assert len(asked) == 1 and "-K" not in asked[0]


def test_a_peer_not_in_the_list_is_refused_naming_it_and_the_list(tmp_path):
    m = load(tmp_path, peers=(OTHER_PEER, "198.51.100.7"))
    put_request(m)
    assert refused(m, "refused_peer") == (
        "the request's peer 192.0.2.6 is not one of the 2 peers the configuration lists "
        f"({m.CONFIG_PATH}): only a session from a listed peer is closed. Nothing was closed")
    assert m.run.calls == [] and session(m) in listed(m)


def test_two_matches_are_refused_by_their_count(tmp_path):
    m = load(tmp_path)
    put_request(m)
    asked = []
    m.run = lambda argv: asked.append(argv) or (0, capture("one_session.txt") * 2, "")
    out = go(m)
    assert (out["ok"], out["code"], out["exit"], out["listed"]) == (False, "many_matches", 41, 2)
    assert out["words"] == (
        "2 established sessions from 192.0.2.6:56221 to 192.0.2.10:57000 are listed, and "
        "exactly 1 is what this helper closes. Nothing was closed")
    assert len(asked) == 1 and "-K" not in asked[0]


def test_zero_matches_say_it_may_have_closed_already(tmp_path):
    m = load(tmp_path)
    put_request(m, port="56220")
    assert refused(m, "no_match") == (
        "no established session from 192.0.2.6:56220 to 192.0.2.10:57000: it may have closed "
        "already. Nothing was closed")
    assert m.journalled[-1]["listed"] == 0


@pytest.mark.parametrize("age, code", [(121, "refused_stale"), (120, "would_close"),
                                       (-6, "refused_stale"), (-5, "would_close")])
def test_a_request_older_than_120_s_or_dated_ahead_is_refused(tmp_path, age, code):
    m = load(tmp_path)
    path = put_request(m, age=age, dry_run=True)
    out = go(m)
    assert out["code"] == code and out["exit"] == (25 if code == "refused_stale" else 0)
    if age == 121:
        assert out["words"] == (
            f"the request {path} was written 2026-11-11T12:24:39Z and read "
            "2026-11-11T12:26:40Z, 121 s later: older than the 120 s a request may be. "
            "Nothing was closed")
        assert m.run.calls == [] and os.path.exists(path)
    if age == -6:
        assert "is dated 2026-11-11T12:26:46Z, 6 s after it was read (2026-11-11T12:26:40Z)" \
            in out["words"]
        assert "more than the 5 s a clock may differ" in out["words"]


def test_a_symlink_at_the_request_s_path_is_never_followed(tmp_path):
    m = load(tmp_path)
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(json.dumps({"id": "run-1", "peer": PEER, "port": PORT,
                                     "dry_run": False}))
    os.utime(elsewhere, (NOW - 10, NOW - 10))
    path = config_of(m)["request"]
    os.symlink(elsewhere, path)
    assert refused(m, "refused_symlink") == (
        f"the request {path} is a symbolic link, not a regular file: it was not followed. "
        "Nothing was closed")
    assert m.run.calls == [] and elsewhere.exists() and os.path.islink(path)


def test_a_symlinked_request_folder_is_never_followed(tmp_path):
    m = load(tmp_path)
    folder = os.path.dirname(config_of(m)["request"])
    real = tmp_path / "real"
    os.rename(folder, real)
    os.symlink(real, folder)
    (real / "request.json").write_text("{}")
    assert f"the request's folder {folder} is a symbolic link" in refused(m, "refused_symlink")


@pytest.mark.parametrize("port", ["http", "57000x", "0", "65536", "99999", "+56221", "-1",
                                  " 56221", "56221 ", "56 221", "056221", "5.6e4", "",
                                  "５６２２１", "٥٦٢٢١", 56221, 56221.0, None, ["56221"]])
def test_a_port_that_is_not_digits_from_1_to_65535_is_refused(tmp_path, port):
    m = load(tmp_path)
    put_request(m, port=port)
    words = refused(m, "refused_port")
    assert m.journalled[-1]["exit"] == 34 and m.run.calls == []
    if port in ("65536", "99999"):
        assert words == f"the request's port {port} is more than 65535. Nothing was closed"
    else:
        assert "is not a string of digits from 1 to 65535 (no sign, space or leading zero)" \
            in words
    if port == "５６２２１":
        assert 'port "?????" is not' in words, "made printable"
    if port == 56221:
        assert "the request's port a number is not a string of digits" in words


@pytest.mark.parametrize("port", ["1", "65535"])
def test_the_ends_of_the_port_range_are_taken(tmp_path, port):
    m = load(tmp_path)
    put_request(m, port=port)
    assert go(m)["code"] == "no_match"


@pytest.mark.parametrize("peer", ["192.0.2.06", "192.000.2.6", "0192.0.2.6", "device.example",
                                  "localhost", " 192.0.2.6", "192.0.2.6 ", "192.0.2.6\n",
                                  "192.0.2", "192.0.2.6.1", "192.0.2.256", "192.0.2.6/32",
                                  "192.0.2.6:56221", "１９２.0.2.6", "0xC0.0.2.6", "",
                                  3221225990, None, ["192.0.2.6"]])
def test_a_peer_that_is_not_a_canonical_ipv4_literal_is_refused(tmp_path, peer):
    m = load(tmp_path)
    put_request(m, peer=peer)
    words = refused(m, "refused_peer")
    assert "is not an IPv4 address written canonically (four numbers 0 to 255 joined by dots, " \
           "no leading zero, nothing around it)" in words
    assert m.journalled[-1]["exit"] == 32 and m.run.calls == []


@pytest.mark.parametrize("peer", ["2001:db8:4::6", "::ffff:192.0.2.6", "::1"])
def test_an_ipv6_peer_is_refused_by_name(tmp_path, peer):
    m = load(tmp_path)
    put_request(m, peer=peer)
    assert refused(m, "refused_ipv6") == (
        f'the request\'s peer "{peer}" is an IPv6 address: an IPv6 peer is not served by this '
        "helper yet. Nothing was closed")
    assert m.journalled[-1]["exit"] == 33 and m.run.calls == []


def test_a_session_an_ipv6_socket_holds_is_refused_by_name(tmp_path):
    """A dual-stack listener's IPv4 session (the capture's, printed `[::ffff:...]`) is not in
    the IPv4 sockets' table: said by name, never "no session"."""
    m = load(tmp_path, listener="192.0.2.10:57002")
    put_request(m, port="56222")
    assert refused(m, "refused_ipv6") == (
        "the session from 192.0.2.6:56222 to 192.0.2.10:57002 is held by an IPv6 socket (a "
        'dual-stack listener: `ss` prints its local end "[::ffff:192.0.2.10]:57002"): an IPv6 '
        "socket is not served by this helper yet. Nothing was closed")
    assert [("-4" in c) for c in m.run.calls] == [True, False]


def test_a_request_owned_by_another_user_is_refused(tmp_path, monkeypatch):
    m = load(tmp_path)
    path = put_request(m)
    real = os.fstat

    def other_owner(fd):
        st = real(fd)
        if st.st_ino == os.lstat(path).st_ino:          # the request's alone
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, 0, st.st_gid,
                                   st.st_size, st.st_atime, st.st_mtime, st.st_ctime))
        return st
    monkeypatch.setattr(os, "fstat", other_owner)
    assert refused(m, "refused_owner") == (
        f"the request {path} is owned by root (uid 0), not by the service user {ME} (uid "
        f"{os.getuid()}). Nothing was closed")
    assert m.run.calls == []


def test_a_request_folder_another_user_owns_is_refused(tmp_path):
    m = load(tmp_path, service_user="nobody")
    put_request(m)
    words = refused(m, "refused_owner")
    assert words.startswith(f"the request's folder {os.path.dirname(config_of(m)['request'])} "
                            f"is owned by {ME} (uid {os.getuid()}), not by the service user "
                            "nobody (uid ")


@pytest.mark.parametrize("plant, kind", [("dir", "a directory"), ("fifo", "a FIFO")])
def test_a_directory_or_a_fifo_at_the_request_s_path_is_refused(tmp_path, plant, kind):
    m = load(tmp_path)
    path = config_of(m)["request"]
    os.mkdir(path) if plant == "dir" else os.mkfifo(path)
    assert refused(m, "refused_file") == (
        f"the request {path} is {kind}, not a regular file. Nothing was closed")
    assert os.path.lexists(path) and m.run.calls == []


def test_no_request_is_refused_by_name(tmp_path):
    m = load(tmp_path)
    assert refused(m, "no_request") == (
        f"no request: {config_of(m)['request']} does not exist. Nothing was closed")


def test_an_oversized_request_is_refused_by_its_size_and_never_shown(tmp_path):
    m = load(tmp_path)
    path = put_request(m, raw=json.dumps({"id": "run-1", "peer": PEER, "port": PORT,
                                          "dry_run": False, "pad": "S3CRET" * 200}).encode())
    assert refused(m, "refused_size") == (
        f"the request {path} is {os.path.getsize(path)} bytes, more than the 1024 a request "
        "may be. Nothing was closed")
    assert "S3CRET" not in json.dumps(m.journalled[-1])


@pytest.mark.parametrize("raw, words", [
    (b"not json", "the request is not JSON in UTF-8"),
    (b"\xff\xfe", "the request is not JSON in UTF-8"),
    (b'{"id": NaN}', "the request is not JSON in UTF-8"),
    (b'["192.0.2.6"]', "the request is a list, not an object of exactly the keys dry_run, id, "
                       "peer, port"),
    (b'{"id": "run-1", "peer": "192.0.2.6", "port": "56221", "dry_run": false, "then": 1}',
     'the request names the key "then", which is not one of dry_run, id, peer, port'),
    (b'{"id": "run-1", "peer": "192.0.2.6", "port": "56221", "dry_run": false, "port": "1"}',
     'the request names the key "port" twice'),
    (b'{"id": "run-1", "peer": "192.0.2.6", "port": "56221"}',
     "the request lacks the key dry_run"),
    (b'{"id": "run-1", "peer": "192.0.2.6", "port": "56221", "dry_run": "false"}',
     'the request\'s dry_run is "false", not true or false'),
    (b'{"id": "run-1", "peer": "192.0.2.6", "port": "56221", "dry_run": 0}',
     "the request's dry_run is a number, not true or false"),
])
def test_a_request_of_any_other_shape_is_refused(tmp_path, raw, words):
    m = load(tmp_path)
    put_request(m, raw=raw)
    assert refused(m, "refused_shape") == words + ". Nothing was closed"
    assert m.journalled[-1]["exit"] == 30 and m.run.calls == []


@pytest.mark.parametrize("rid", ["", "run 1", "../run", "r" * 65, "-run", "run\n", 7, None])
def test_an_id_that_is_not_a_run_id_is_refused_and_not_carried(tmp_path, rid):
    m = load(tmp_path)
    put_request(m, id=rid)
    assert "is not a run id" in refused(m, "refused_id")
    assert m.journalled[-1]["id"] == "" and m.journalled[-1]["exit"] == 31


def test_a_refusal_shows_one_value_cut_and_printable_never_the_request(tmp_path):
    m = load(tmp_path)
    put_request(m, peer="A\x1b[31m" + "x" * 70 + "TAIL", port="S3CRET")
    words = refused(m, "refused_peer")
    assert 'peer "A?[31m' + "x" * 34 + '" (cut from 80 characters) is not' in words
    line = json.dumps(m.journalled[-1])
    assert "TAIL" not in line and "S3CRET" not in line and "\\u001b" not in line


# ── the dry run ───────────────────────────────────────────────────────────────────────────────

def test_a_dry_run_sends_no_close_and_says_what_it_would_close(tmp_path):
    m = load(tmp_path)
    put_request(m, dry_run=True)
    before = listed(m)
    out = go(m)
    ss = config_of(m)["ss"]
    assert (out["ok"], out["code"], out["exit"], out["dry_run"]) == (True, "would_close", 0,
                                                                    True)
    assert m.run.calls == [[ss] + FIND] and listed(m) == before
    assert out["words"] == (
        "dry run: would close the one established session from 192.0.2.6:56221 to "
        f"192.0.2.10:57000 with `{ss} {' '.join(CLOSE)}`. Nothing was closed")
    assert out["tuple"] == {"local": LISTENER, "peer": "192.0.2.6:56221"}


def test_a_dry_run_gives_the_refusal_a_request_would_get(tmp_path):
    m = load(tmp_path, peers=(OTHER_PEER,))
    put_request(m, dry_run=True)
    assert refused(m, "refused_peer").startswith(
        "dry run: the request's peer 192.0.2.6 is not one of the 1 peers")
    assert m.journalled[-1]["dry_run"] is True


# ── the close that does not land, and an `ss` that cannot be read ────────────────────────────

def test_a_session_still_listed_after_the_close_is_a_failure_naming_the_bound(tmp_path):
    m = load(tmp_path)
    put_request(m)
    m.run.closes = False
    out = go(m)
    ss = config_of(m)["ss"]
    assert (out["ok"], out["code"], out["exit"]) == (False, "not_gone", 50)
    assert len(m.run.closes_sent()) == 1, "the close is sent once, never again"
    assert m.clock.slept == [0.25] * 8 and len(m.run.calls) == 1 + 1 + 9
    assert out["words"] == (
        f"`{ss} {' '.join(CLOSE)}` ran (exit 0), and the session from 192.0.2.6:56221 to "
        "192.0.2.10:57000 is still listed 2.0 s after it (9 reads, one every 0.25 s; the bound "
        "is 2.0 s, reasoned, not measured: the kernel aborts the socket before `ss -K` "
        "returns, so the first read-back is expected to find it gone). It was not closed")


def test_the_result_is_the_read_back_s_never_the_close_s_exit_code(tmp_path):
    m = load(tmp_path)
    put_request(m)
    m.run.close_exit = 1
    out = go(m)
    assert (out["ok"], out["code"]) == (True, "closed") and "which ran (exit 1)" in out["words"]
    m2 = load(tmp_path / "second")
    put_request(m2)
    m2.run.close_exit, m2.run.closes = 0, False
    assert go(m2)["code"] == "not_gone", "exit 0 with the session still there is no success"


def test_a_read_back_that_cannot_be_read_is_neither_closed_nor_not(tmp_path):
    m = load(tmp_path)
    put_request(m)
    real = m.run

    def run(argv):
        if "-K" not in argv and real.closes_sent():
            return 2, "", "Cannot open netlink socket"
        return real(argv)
    m.run = run
    out = go(m)
    assert (out["ok"], out["code"], out["exit"]) == (False, "close_unread", 51)
    assert "and the read-back could not be read" in out["words"]
    assert "whether the session from 192.0.2.6:56221 to 192.0.2.10:57000 is gone is not known" \
        in out["words"]


@pytest.mark.parametrize("answer, code, words", [
    ((None, "", "it did not end within 5 s"), "ss_failed", "could not be run: it did not end "
                                                           "within 5 s"),
    ((255, "", "RTNETLINK answers: Operation not permitted\n"), "ss_failed",
     'exited 255: "RTNETLINK answers: Operation not permitt" (cut from 42 characters)'),
    ((0, "Recv-Q Send-Q Local Address:Port Peer Address:Port\n", ""), "ss_unread",
     "`ss` printed a line that is not a row of four columns"),
    ((0, "ESTAB 0 0 192.0.2.10:57000 192.0.2.6:56221\n", ""), "ss_unread",
     "`ss` printed a line that is not a row of four columns"),
])
def test_an_ss_that_cannot_be_run_or_read_closes_nothing(tmp_path, answer, code, words):
    m = load(tmp_path)
    put_request(m)
    asked = []
    m.run = lambda argv: asked.append(argv) or answer
    out = go(m)
    assert (out["ok"], out["code"]) == (False, code) and words in out["words"]
    assert out["words"].endswith("Nothing was closed") and len(asked) == 1


# ── the configuration, root's ────────────────────────────────────────────────────────────────

def _group_writable(m):
    os.chmod(m.CONFIG_PATH, 0o664)


def _not_roots(m):
    m.ROOT_UID = os.getuid() + 1


def _folder_writable(m):
    os.chmod(os.path.dirname(m.CONFIG_PATH), 0o775)


def _a_link(m):
    real = m.CONFIG_PATH + ".real"
    os.rename(m.CONFIG_PATH, real)
    os.symlink(real, m.CONFIG_PATH)


def _absent(m):
    os.unlink(m.CONFIG_PATH)


def _outcome_folder_writable(m):
    os.chmod(os.path.dirname(config_of(m)["outcome"]), 0o757)


def _ss_writable(m):
    os.chmod(config_of(m)["ss"], 0o775)


def _ss_a_link(m):
    ss = config_of(m)["ss"]
    os.rename(ss, ss + ".real")
    os.symlink(ss + ".real", ss)


@pytest.mark.parametrize("plant, words", [
    (_group_writable, "is mode -rw-rw-r-- (0o664), not 0644 (written by root alone, read by "
                      "all)"),
    (lambda m: os.chmod(m.CONFIG_PATH, 0o600), "is mode -rw------- (0o600), not 0644"),
    (lambda m: os.chmod(m.CONFIG_PATH, 0o646), "is mode -rw-r--rw- (0o646), not 0644"),
    (_not_roots, f"is owned by {ME} (uid {os.getuid()}), not by "),
    (_folder_writable, "is mode drwxrwxr-x (0o775), writable by its group or by others"),
    (_a_link, "is a symbolic link, not a regular file"),
    (_absent, "does not exist (the install step writes it)"),
    (_outcome_folder_writable, "the outcome's folder "),
    (_ss_writable, "not a program of "),
    (_ss_a_link, "is a symbolic link, not a regular file"),
    (lambda m: put_config(m, raw=b"{"), "the configuration is not JSON in UTF-8"),
    (lambda m: put_config(m, extra=1), 'names the key "extra", which is not one of listener, '
                                       "outcome, peers, request, service_user, ss"),
    (lambda m: put_config(m, {k: v for k, v in config_of(m).items() if k != "peers"}),
     "the configuration lacks the key peers"),
    (lambda m: put_config(m, peers=[]), "peers is not a list of 1 to 65536 addresses"),
    (lambda m: put_config(m, peers=[PEER, "192.0.2.007"]),
     'peer 2 ("192.0.2.007") is not an IPv4 address written canonically'),
    (lambda m: put_config(m, peers=[PEER, "2001:db8:4::6"]),
     "an IPv6 peer is not served by this helper yet"),
    (lambda m: put_config(m, listener={"address": "2001:db8::10", "port": 57000}),
     "an IPv6 listener is not served by this helper yet"),
    (lambda m: put_config(m, listener={"address": "0.0.0.0", "port": 57000}),
     "listener address is 0.0.0.0, every address"),
    (lambda m: put_config(m, peers=[PEER, "0.0.0.0"]),
     "peer 2 is 0.0.0.0, every address: a peer is one device's address"),
    (lambda m: put_config(m, listener={"address": "192.0.2.10", "port": "57000"}),
     'listener port is "57000", not a whole number from 1 to 65535'),
    (lambda m: put_config(m, listener={"address": "192.0.2.10", "port": True}),
     "listener port is true or false, not a whole number from 1 to 65535"),
    (lambda m: put_config(m, listener={"address": "192.0.2.10", "port": 0}),
     "listener port is 0, not a whole number from 1 to 65535"),
    (lambda m: put_config(m, listener={"address": "192.0.2.10", "port": 57000, "also": 1}),
     "listener is not an object of exactly address and port"),
    (lambda m: put_config(m, service_user="root"), "service_user is root"),
    (lambda m: put_config(m, service_user="no-such-account-here"),
     "is not an account on this host"),
    (lambda m: put_config(m, service_user="Robert; reboot"), "is not an account's name"),
    (lambda m: put_config(m, request="request.json"), "not one absolute path written plainly"),
    (lambda m: put_config(m, outcome=config_of(m)["outcome"] + "/../x"),
     "not one absolute path written plainly"),
    (lambda m: put_config(m, request=os.path.dirname(config_of(m)["outcome"]) + "/r.json"),
     "the request's folder is the service user's and the outcome's is root's"),
    (lambda m: put_config(m, ss="ss"), "not one absolute path written plainly"),
])
def test_a_configuration_that_is_not_as_installed_refuses_every_request(tmp_path, plant, words):
    m = load(tmp_path)
    path = put_request(m)
    plant(m)
    out = go(m)
    assert (out["ok"], out["code"], out["exit"]) == (False, "config_refused", 78), out
    assert words in out["words"] and out["words"].endswith("Nothing was closed")
    assert m.run.calls == [] and os.path.exists(path), "the request was not read"
    assert out["outcome_not_written"] and out["tuple"] == {"local": None, "peer": None}
    if plant is _not_roots:
        assert out["words"].startswith("the configuration's folder "), \
            "the folder's owner is judged first; the file's own has the test below"


def _owned_by_uid_0(st):
    return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, 0, st.st_gid,
                           st.st_size, st.st_atime, st.st_mtime, st.st_ctime))


def test_a_configuration_file_another_user_owns_is_refused_in_a_folder_of_root_s(
        tmp_path, monkeypatch):
    """The file's own owner, read from the open file, where its folder passes: uid 0 stands
    for "another user" here, since the test's own uid is the helper's root."""
    m = load(tmp_path)
    path = put_request(m)
    inode, real = os.lstat(m.CONFIG_PATH).st_ino, os.fstat
    monkeypatch.setattr(os, "fstat", lambda fd: (
        _owned_by_uid_0(real(fd)) if real(fd).st_ino == inode else real(fd)))
    out = go(m)
    assert (out["ok"], out["code"], out["exit"]) == (False, "config_refused", 78)
    assert out["words"] == (
        f"the configuration {m.CONFIG_PATH} is owned by root (uid 0), not by {ME} (uid "
        f"{os.getuid()}). Nothing was closed")
    assert m.run.calls == [] and os.path.exists(path)


def test_an_ss_another_user_owns_is_refused(tmp_path, monkeypatch):
    m = load(tmp_path)
    put_request(m)
    ss, real = config_of(m)["ss"], os.lstat
    monkeypatch.setattr(os, "lstat", lambda p, *a, **kw: (
        _owned_by_uid_0(real(p, *a, **kw)) if p == ss else real(p, *a, **kw)))
    out = go(m)
    assert (out["ok"], out["code"], out["exit"]) == (False, "config_refused", 78)
    assert out["words"] == (
        f"the configuration's ss {ss} is owned by root (uid 0) with mode -rwxr-xr-x (0o755), "
        f"not a program of {ME} (uid {os.getuid()})'s that no one else can write. Nothing was "
        "closed")
    assert m.run.calls == []


# ── any argument, root, one run at a time ────────────────────────────────────────────────────

@pytest.mark.parametrize("argv", [["--help"], ["192.0.2.6", "56221"], [""], ["--dry-run"]])
def test_any_argument_is_refused_before_anything_is_read(tmp_path, argv):
    m = load(tmp_path)
    path = put_request(m)
    os.unlink(m.CONFIG_PATH)                       # not even the configuration is read
    out = go(m, argv)
    assert (out["ok"], out["code"], out["exit"]) == (False, "refused_argument", 64)
    assert out["words"] == (
        f"mercury-collector-close takes no argument and was given {len(argv)}: its one request "
        "is the file its configuration names. Nothing was closed")
    assert m.run.calls == [] and os.path.exists(path)


def test_it_refuses_to_run_as_anyone_but_root(tmp_path):
    m = load(tmp_path)
    put_request(m)
    m.REQUIRE_ROOT = True
    out = go(m)
    assert (out["code"], out["exit"]) == ("not_root", 77) and m.run.calls == []
    assert f"was run as uid {os.geteuid()}" in out["words"]


def test_a_second_run_at_once_is_refused_and_leaves_the_first_s_outcome(tmp_path):
    m = load(tmp_path)
    put_request(m, dry_run=True)
    first = go(m)
    put_request(m, id="run-2")
    lock = os.open(os.path.join(os.path.dirname(config_of(m)["outcome"]), "lock"), os.O_RDWR)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            assert m.main([]) == 75
    finally:
        os.close(lock)
    out = json.loads(printed.getvalue())
    assert out["code"] == "busy" and out["outcome_not_written"]
    with open(config_of(m)["outcome"], encoding="utf-8") as fh:
        assert json.load(fh) == first
    assert len(m.run.calls) == 1, "the second run asked nothing of ss"


# ── the outcome and the journal ──────────────────────────────────────────────────────────────

def test_the_outcome_is_a_new_file_renamed_into_place_never_through_a_link(tmp_path,
                                                                           monkeypatch):
    m = load(tmp_path)
    outcome = config_of(m)["outcome"]
    victim, planted = tmp_path / "victim", tmp_path / "planted"
    victim.write_text("as it was\n")
    planted.write_text("as it was\n")
    os.symlink(victim, outcome)                    # a link where the outcome goes
    os.symlink(planted, outcome + ".new")          # and one where it is first written
    seen = []
    real = os.replace

    def replace(src, dst):
        with open(src, encoding="utf-8") as fh:
            seen.append((src, dst, os.path.islink(src), json.loads(fh.read())["code"]))
        return real(src, dst)
    monkeypatch.setattr(os, "replace", replace)
    put_request(m)
    out = go(m)
    assert seen == [(outcome + ".new", outcome, False, "closed")], \
        "written whole beside it, then renamed"
    assert victim.read_text() == planted.read_text() == "as it was\n"
    st = os.lstat(outcome)
    assert stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o644
    assert "outcome_not_written" not in out


class Syslog:
    LOG_PID, LOG_AUTHPRIV, LOG_NOTICE, LOG_WARNING = 1, 80, 5, 4

    def __init__(self):
        self.calls = []

    def openlog(self, *args):
        self.calls.append(("openlog",) + args)

    def syslog(self, *args):
        self.calls.append(("syslog",) + args)

    def closelog(self):
        self.calls.append(("closelog",))


def test_the_journal_takes_a_refusal_as_a_warning_and_a_close_as_a_notice(tmp_path):
    m = load(tmp_path)
    log = Syslog()
    m.syslog = log
    lines = []
    for request, level in ((dict(peer="198.51.100.9"), log.LOG_WARNING), ({}, log.LOG_NOTICE)):
        put_request(m, **request)
        printed = io.StringIO()
        m.journal = m.own_journal
        with contextlib.redirect_stdout(printed):
            m.main([])
        out = json.loads(printed.getvalue())
        assert log.calls[-3:] == [
            ("openlog", "mercury-collector-close", log.LOG_PID, log.LOG_AUTHPRIV),
            ("syslog", level, json.dumps(out, sort_keys=True)), ("closelog",)]
        lines.append(out["code"])
    assert lines == ["refused_peer", "closed"]


def test_a_journal_that_does_not_take_the_line_is_said_and_changes_no_result(tmp_path):
    m = load(tmp_path)
    put_request(m)

    class Broken(Syslog):
        def syslog(self, *args):
            raise OSError("no log socket")
    m.syslog = Broken()
    m.journal = m.own_journal
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        assert m.main([]) == 0
    out = json.loads(printed.getvalue())
    assert out["code"] == "closed" and out["journal_not_written"]


# ── what it runs, and in what environment ────────────────────────────────────────────────────

def test_ss_is_given_a_fixed_environment_and_nothing_of_the_caller_s(tmp_path, monkeypatch):
    """The real `run`, on a program of the test's standing where the configuration's `ss`
    is: it writes the environment and the arguments it was given, and prints the captured
    row."""
    m = load(tmp_path)
    ss = config_of(m)["ss"]
    with open(ss, "w") as fh:
        fh.write('#!/bin/sh\nenv > "$0.env"\nprintf "%s\\n" "$@" > "$0.argv"\n'
                 f"printf '%s\\n' '{capture('one_session.txt').strip()}'\n")
    def arrived() -> dict:
        got = dict(line.split("=", 1) for line in open(ss + ".env").read().splitlines())
        return {k: v for k, v in got.items() if k not in ("PWD", "OLDPWD", "SHLVL", "_")}

    # What a child given exactly `ENV` holds here: the test harness adds its own guard to
    # every child it starts, so the comparison is with this, read before anything is planted.
    subprocess.run([ss], env=dict(m.ENV), check=True, capture_output=True)
    unplanted = arrived()
    assert unplanted["LANG"] == unplanted["LC_ALL"] == "C"
    for name, value in (("PYTHONPATH", "/planted"), ("PYTHONSTARTUP", "/planted.py"),
                        ("LD_LIBRARY_PATH", "/planted"), ("LD_AUDIT", "/planted.so"),
                        ("IFS", ":"), ("PATH", "/planted:" + os.environ["PATH"]),
                        ("BASH_ENV", "/planted"), ("ENV", "/planted")):
        monkeypatch.setenv(name, value)
    m.run = m.own_run
    handed = []
    real = subprocess.run

    def spy(argv, **kw):
        handed.append((argv, kw["env"]))
        return real(argv, **kw)
    monkeypatch.setattr(subprocess, "run", spy)
    put_request(m, dry_run=True)
    assert go(m)["code"] == "would_close"
    assert handed == [([ss] + FIND, {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C",
                                     "LC_ALL": "C"})], "the whole environment, as handed over"
    assert arrived() == unplanted, "nothing planted in the caller's environment arrived"
    assert "/planted" not in json.dumps(arrived())
    assert open(ss + ".argv").read().split("\n")[:-1] == FIND


def test_an_ss_that_is_not_there_or_hangs_is_said(tmp_path):
    m = load(tmp_path)
    run = m.own_run
    assert run([str(tmp_path / "absent")]) == (None, "", "No such file or directory")
    slow = tmp_path / "slow"
    slow.write_text("#!/bin/sh\nsleep 5\n")
    os.chmod(slow, 0o755)
    m.SS_TIMEOUT_S = 0.2
    assert run([str(slow)]) == (None, "", "it did not end within 0.2 s")


def test_the_helper_runs_one_program_the_configuration_s_ss_and_no_shell():
    text = open(SCRIPT).read()
    assert text.splitlines()[0] == "#!/usr/bin/python3 -I", \
        "root's interpreter by its path, reading no PYTHON* variable and no user packages"
    tree = ast.parse(text)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)]
    runs = [c for c in calls if (c.func.value.id, c.func.attr) == ("subprocess", "run")]
    assert len(runs) == 1
    keywords = {k.arg: ast.unparse(k.value) for k in runs[0].keywords}
    assert keywords["env"] == "ENV" and keywords["timeout"] == "SS_TIMEOUT_S"
    assert not [c for c in calls if c.func.attr in ("system", "popen", "execv", "execve",
                                                    "Popen", "call", "check_output")]
    assert "shell=True" not in text and "os.environ" not in text and "import shutil" not in text
    for argv in ("list_argv", "close_argv"):
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == argv)
        assert ast.unparse(fn.body[-1].value).startswith("[cfg['ss'], '-H'")


def test_the_helper_is_written_for_python_3_8_and_the_standard_library():
    from modules.apps.python_versions import Target, grammar_problems, name_problem

    text = open(SCRIPT).read()
    tree = ast.parse(text, feature_version=(3, 8))
    target = Target((3, 8), "the oldest Python a supported host's /usr/bin/python3 is")
    assert grammar_problems(tree, text, "mercury-collector-close", target) == []
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert imported == {"errno", "fcntl", "ipaddress", "json", "os", "pwd", "re", "stat",
                        "subprocess", "sys", "syslog", "time"}
    assert all(not name_problem(i, target) for i in imported)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]


def test_every_exit_code_is_its_own_class_and_is_in_the_header():
    m_text = open(SCRIPT).read()
    tree = ast.parse(m_text)
    doc = ast.get_docstring(tree)
    exits = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                 and getattr(n.targets[0], "id", "") == "EXITS")
    assert len(exits) == 26 and 1 not in exits.values(), "1 is sudo's own refusal"
    by_exit = {}
    for code, number in exits.items():
        by_exit.setdefault(number, []).append(code)
    assert [codes for codes in by_exit.values() if len(codes) > 1] == [["closed",
                                                                        "would_close"]]
    for code, number in exits.items():
        assert re.search(rf"^ *{number} +(closed, or )?{code}\b", doc, re.M), (code, number)
    for name in ("closed", "would_close", "refused_stale", "refused_peer", "refused_port",
                 "refused_listener", "refused_owner", "refused_symlink", "no_match",
                 "many_matches", "not_gone", "config_refused"):
        assert name in exits, name


# ── the install step ─────────────────────────────────────────────────────────────────────────

def step_text() -> str:
    with open(HOST_STEP, encoding="utf-8") as fh:
        return fh.read()


def code_lines(text: str) -> list:
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def test_the_host_step_parses():
    assert subprocess.run(["bash", "-n", HOST_STEP], capture_output=True).returncode == 0


def test_the_host_step_s_sudoers_line_is_exactly_the_one_line():
    line = next(l for l in step_text().splitlines() if l.startswith("SUDOERS_LINE="))
    got = subprocess.run(["bash", "-c", f'SERVICE_USER=svc\n{line}\nprintf "%s" "$SUDOERS_LINE"'],
                         capture_output=True, text=True, check=True).stdout
    assert got == 'svc ALL=(root) NOPASSWD: /usr/local/sbin/mercury-collector-close ""'
    step = step_text()
    assert 'printf "%s\\n" "$SUDOERS_LINE" > "$WORK/mercury-collector-close.sudoers" && sudo ' \
           'visudo -cf "$WORK/mercury-collector-close.sudoers" >/dev/null' in step
    assert step.index("sudo visudo -cf") < step.index(
        'sudo install -o root -g root -m 0440 "$WORK/mercury-collector-close.sudoers" '
        '"$SUDOERS_FILE"')
    assert step.count("SUDOERS_LINE=") == 1


def test_the_host_step_installs_each_file_by_name_from_a_fresh_folder():
    step = step_text()
    installs = [line for line in code_lines(step) if "sudo install " in line]
    assert len(installs) == 4 and "WORK=$(mktemp -d)" in step
    assert sum(line.count("sudo install ") for line in installs) == 6, \
        "the helper, the configuration and its folder, the two state folders, the sudoers line"
    assert not [line for line in installs if "*" in line or "?" in line or "[" in line], \
        "files are installed by name, never a glob"
    for line in ('sudo install -o root -g root -m 0755 "$HELPER_SRC" "$INSTALLED"',
                 'sudo install -o root -g root -m 0644 "$WORK/collector-close.conf" "$CONF"',
                 'sudo install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$REQUEST_DIR"'):
        assert line in step, line
    assert "/tmp" not in step, "nothing is rendered into a shared folder"


def test_the_host_step_carries_no_placeholder_but_its_usage():
    lines = [l for l in code_lines(step_text()) if re.search(r"<[A-Za-z][\w.@-]*(?: [\w.@-]+)*>",
                                                             l)]
    assert lines == ['    echo "Usage: bash $0 <service user> <listener address>:<port> '
                     '<peers file>"']


def test_the_host_step_changes_nothing_before_its_checks_pass_and_restarts_nothing():
    step = step_text()
    first_change = min(step.index('\nstep "'), step.index("sudo install "), step.index("mktemp"))
    for name in ("the release holds the helper, and it parses under $PYTHON (3.8 or later)",
                 "ss is a program of root's that no one else can write, and names -K",
                 "the kernel can destroy a socket (CONFIG_INET_DIAG_DESTROY=y)",
                 "the service user exists",
                 "the collector listens on the listener, on an IPv4 socket",
                 "the configuration renders by the helper's own rules",
                 "what is already there is as this step leaves it",
                 "the sudoers file is absent or exactly the one line, and visudo -c parses "
                 "every file"):
        assert step.index(f'check "{name}"') < first_change, name
    assert 'not_asked "the kernel can destroy a socket (CONFIG_INET_DIAG_DESTROY=y)"' in step
    assert not re.search(r"systemctl|\brestart\b|(?<![-\w])p?kill(all)?\b|\breboot\b|"
                         r"-K(?![,\"])", "\n".join(code_lines(step))), \
        "it restarts nothing, and -K is only ever a name it reads `ss -h` for"
    assert 'grep -q -- "-K, --kill"' in step
    # The copy is proved where it landed, by dry runs only, after everything is installed.
    assert '\\"dry_run\\": true' in step and "false" not in step
    assert step.index('check "the service user can write none of what was installed"') \
        < step.index("FIRST=$(dry_run install-step-listed")
    assert 'echo "== UNDO: sudo rm $INSTALLED $CONF $SUDOERS_FILE"' in step


def test_the_host_step_the_helper_and_mercury_name_the_same_paths(tmp_path):
    from modules.heal import collector_close as caller

    m, step = pristine(), step_text()
    assert f"INSTALLED={m.INSTALLED}\n" in step and caller.HELPER == m.INSTALLED
    assert f"CONF_DIR={os.path.dirname(m.CONFIG_PATH)}\n" in step
    assert "CONF=$CONF_DIR/" + os.path.basename(m.CONFIG_PATH) + "\n" in step
    assert caller.CONFIG == m.CONFIG_PATH
    assert f"STATE_DIR={os.path.dirname(m.OUTCOME_PATH)}\n" in step
    assert m.REQUEST_PATH == os.path.dirname(m.OUTCOME_PATH) + "/request/request.json"
    assert "REQUEST_DIR=$STATE_DIR/request\n" in step
    assert "REQUEST=$REQUEST_DIR/request.json\n" in step
    assert caller.INSTALL_STEP == os.path.relpath(HOST_STEP, ROOT)
    assert f"SUDOERS_FILE=/etc/sudoers.d/{m.TAG}\n" in step


# ── the install step's read: the configuration it writes is the one the helper accepts ───────

def test_the_configuration_the_install_writes_is_one_the_helper_takes(tmp_path, capsys):
    m = load(tmp_path)
    cfg = config_of(m)
    m.REQUEST_PATH, m.OUTCOME_PATH = cfg["request"], cfg["outcome"]
    assert m.render([ME, LISTENER, cfg["ss"]], "192.0.2.7\n192.0.2.6\n192.0.2.7\n") == 0
    text = capsys.readouterr().out
    assert json.loads(text) == dict(cfg, peers=[PEER, OTHER_PEER]), "sorted, each once"
    put_config(m, raw=text.encode())
    put_request(m, dry_run=True)
    assert go(m)["code"] == "would_close"


@pytest.mark.parametrize("argv, peers, words", [
    ([ME, LISTENER, "/usr/bin/ss"], "", "the peers are empty"),
    ([ME, LISTENER, "/usr/bin/ss"], "192.0.2.6\n\n192.0.2.7\n",
     'line 2 of the peers, "", is not an IPv4 address written canonically, one a line'),
    ([ME, LISTENER, "/usr/bin/ss"], "192.0.2.6 # the edge router\n", "line 1 of the peers"),
    ([ME, LISTENER, "/usr/bin/ss"], "192.0.2.6\n2001:db8:4::6\n",
     "(an IPv6 peer is not served by this helper yet)"),
    ([ME, "[2001:db8::10]:57000", "/usr/bin/ss"], "192.0.2.6\n",
     "an IPv6 listener is not served by this helper yet"),
    ([ME, "192.0.2.10", "/usr/bin/ss"], "192.0.2.6\n", "is not <IPv4 address>:<port 1 to "
                                                       "65535>"),
    ([ME, "192.0.2.10:0", "/usr/bin/ss"], "192.0.2.6\n", "is not <IPv4 address>:<port 1 to "
                                                         "65535>"),
    ([ME, "collector.example:57000", "/usr/bin/ss"], "192.0.2.6\n",
     "listener address \"collector.example\" is not an IPv4 address written canonically"),
    (["root", LISTENER, "/usr/bin/ss"], "192.0.2.6\n", "service_user is root"),
    ([ME, LISTENER, "ss"], "192.0.2.6\n", "not one absolute path written plainly"),
    ([ME, LISTENER], "192.0.2.6\n", "and was given 2 values"),
])
def test_the_install_s_read_refuses_what_the_helper_would(tmp_path, capsys, argv, peers, words):
    m = load(tmp_path)
    assert m.render(argv, peers) == 1
    out = capsys.readouterr().out
    assert out.startswith("REFUSED: ") and words in out
