"""Mercury's half of the collector's close (C3078; modules/heal/collector_close.py): the
request it writes, the one command it runs, the outcome it carries; the peers read from
committed intent; and the two scripts (`scripts/nmas-collector-peers`,
`scripts/nmas-collector-close-dry-run`).

The command is never sudo here. Its stand-in is the REAL helper
(`deploy/collector/mercury-collector-close`, loaded as tests/test_collector_close.py loads it,
its `ss` the stand-in over the real captures), run in this process where `sudo -n <helper>`
would run it: so the request this module writes is one the helper takes, and the words it
returns are the helper's own. The module's own `_run` is reached on a program of the test's.

The peers are read on the fleet's real intent (tests/test_heal_diagnose.py's), with the edit
tests/test_heal_diagnose_stream.py makes: one router's receiver and one of its interfaces in
the documentation ranges.
"""

import contextlib
import copy
import fcntl
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import stat
import time

import pytest

from modules.heal import collector_close as C
from tests import test_collector_close as H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PEER, PORT, LISTENER = H.PEER, 56221, H.LISTENER


@pytest.fixture
def world(tmp_path, monkeypatch):
    """The helper installed in a temporary root, and `run`: the helper where sudo would run
    it. ``(helper, run, calls)``; *calls* holds each argv and bound, and what the request
    file was when the command ran."""
    return _world(tmp_path, monkeypatch)


def _world(tmp_path, monkeypatch, **kw):
    m = H.load(tmp_path, **kw)
    m.now = time.time                       # the request is written now, by this module
    monkeypatch.setattr(C, "HELPER", H.SCRIPT)
    monkeypatch.setattr(C, "CONFIG", m.CONFIG_PATH)
    calls = []

    def run(argv, timeout):
        path = H.config_of(m)["request"]
        st = os.lstat(path)
        with open(path, encoding="utf-8") as fh:
            calls.append({"argv": list(argv), "timeout": timeout, "request": json.load(fh),
                          "mode": stat.S_IMODE(st.st_mode), "regular": stat.S_ISREG(st.st_mode),
                          "beside": sorted(os.listdir(os.path.dirname(path)))})
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = m.main([])
        return code, printed.getvalue(), ""
    return m, run, calls


def ask(run, *, peer=PEER, port=PORT, dry_run=True, run_id="run-7") -> dict:
    got = C.request(peer, port, dry_run=dry_run, run_id=run_id, run=run)
    assert sorted(got) == ["at", "code", "exit", "ok", "tuple", "words"]
    return got


# ── the request, the command, the outcome ────────────────────────────────────────────────────

def test_a_dry_run_goes_through_the_helper_and_comes_back_whole(world):
    m, run, calls = world
    got = ask(run)
    assert (got["ok"], got["code"], got["exit"]) == (True, "would_close", 0)
    assert got["tuple"] == {"local": LISTENER, "peer": "192.0.2.6:56221"}
    assert got["words"].startswith("dry run: would close the one established session from "
                                   "192.0.2.6:56221 to 192.0.2.10:57000 with `")
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", got["at"])
    assert got["at"] == m.journalled[-1]["finished"], "the helper's own time"
    assert not m.run.closes_sent()
    (call,) = calls
    assert call["argv"] == ["sudo", "-n", H.SCRIPT] and call["timeout"] == C.BOUND_S == 20
    assert call["request"] == {"id": "run-7", "peer": PEER, "port": "56221", "dry_run": True}
    assert (call["mode"], call["regular"]) == (0o600, True), "owner-only, a regular file"
    assert call["beside"] == ["lock", "request.json"], "renamed into place: no part-file"
    assert not os.path.exists(H.config_of(m)["request"])


def test_a_close_goes_through_the_helper_and_reads_back_gone(world):
    m, run, calls = world
    got = ask(run, dry_run=False)
    assert (got["ok"], got["code"], got["exit"]) == (True, "closed", 0)
    assert len(m.run.closes_sent()) == 1 and calls[0]["request"]["dry_run"] is False
    assert got["words"] == m.journalled[-1]["words"]


@pytest.mark.parametrize("change, code, exit_code", [
    (dict(peer="198.51.100.9"), "refused_peer", 32),
    (dict(peer="2001:db8:4::6"), "refused_ipv6", 33),
    (dict(port="http"), "refused_port", 34),
    (dict(port=56220), "no_match", 40),
    (dict(run_id="not a run id"), "refused_id", 31),
])
def test_a_refusal_is_carried_through_with_the_helper_s_code_exit_and_words(world, change,
                                                                            code, exit_code):
    m, run, _calls = world
    got = ask(run, dry_run=False, **change)
    assert (got["ok"], got["code"], got["exit"]) == (False, code, exit_code)
    assert got["words"] == m.journalled[-1]["words"] and got["words"].endswith(
        "Nothing was closed")
    assert not m.run.closes_sent()


def test_a_refusal_before_the_helper_read_the_id_is_carried_through_too(world):
    """The helper refuses a stale request without reading it, so its outcome carries no id:
    it is still this run's, the one command this module ran."""
    m, run, _calls = world
    m.now = lambda: time.time() + 500
    got = ask(run, dry_run=False)
    assert (got["ok"], got["code"], got["exit"]) == (False, "refused_stale", 25)
    assert m.journalled[-1]["id"] == "" and "older than the 120 s" in got["words"]


def test_an_outcome_of_another_run_is_not_taken_for_this_one(world):
    m, run, _calls = world

    def another(argv, timeout):
        code, text, err = run(argv, timeout)
        return code, json.dumps(dict(json.loads(text), id="run-6")) + "\n", err
    got = ask(another, dry_run=False)
    assert (got["ok"], got["code"], got["exit"]) == (False, "outcome_unmatched", 0)
    assert got["words"] == ("the helper's outcome carries the id 'run-6', not this run's "
                            "'run-7': it is another run's, so nothing is known about this one")

    def no_id_and_ok(argv, timeout):
        return 0, json.dumps({"id": "", "ok": True, "code": "closed", "exit": 0}) + "\n", ""
    assert ask(no_id_and_ok)["code"] == "outcome_unmatched", "only a refusal may carry no id"


def test_an_outcome_that_was_not_printed_is_read_from_the_helper_s_file_by_its_id(world):
    m, run, _calls = world

    def silent(argv, timeout):
        return run(argv, timeout)[0], "", ""
    got = ask(silent)
    assert (got["ok"], got["code"], got["exit"]) == (True, "would_close", 0)
    with open(H.config_of(m)["outcome"], "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "run-6", "ok": True, "code": "closed", "exit": 0}) + "\n")
    got = ask(lambda argv, timeout: (0, "", ""))
    assert (got["ok"], got["code"], got["exit"]) == (False, "no_outcome", 0)
    assert got["words"].endswith("holds none of run run-7: whether a session was closed is "
                                 "not known")


def test_an_exit_code_that_is_not_the_outcome_s_is_never_a_success(world):
    _m, run, _calls = world
    got = ask(lambda argv, timeout: (40, run(argv, timeout)[1], ""))
    assert (got["ok"], got["code"], got["exit"]) == (False, "would_close", 40)
    assert got["words"].endswith("(the helper exited 40, and its outcome says 0)")


# ── not installed is its own state ───────────────────────────────────────────────────────────

def _never(argv, timeout):
    raise AssertionError("nothing is run")


def test_no_helper_is_not_installed_and_says_what_to_run(world, monkeypatch, tmp_path):
    monkeypatch.setattr(C, "HELPER", str(tmp_path / "absent"))
    got = ask(_never)
    assert (got["ok"], got["code"], got["exit"], got["tuple"]) == (False, "not_installed",
                                                                  None, None)
    assert got["code"] in C.NOT_INSTALLED
    assert got["words"] == (
        f"the collector's close helper is not installed: {tmp_path / 'absent'} does not "
        "exist. A person installs it once on Mercury's host with "
        "scripts/host-steps/c3078-collector-close-install.sh (the manual's \"Re-subscribe a "
        "lost telemetry stream\", under \"Closing the collector's session\")")


@pytest.mark.parametrize("plant, words", [
    (lambda m: os.unlink(m.CONFIG_PATH), "could not be read (FileNotFoundError"),
    (lambda m: open(m.CONFIG_PATH, "w").write("{"), "could not be read (JSONDecodeError"),
    (lambda m: open(m.CONFIG_PATH, "w").write("{}"), "could not be read (KeyError"),
    (lambda m: os.rmdir(os.path.dirname(H.config_of(m)["request"])),
     "is absent or not writable by Mercury's user"),
    (lambda m: os.chmod(os.path.dirname(H.config_of(m)["request"]), 0o500),
     "is absent or not writable by Mercury's user"),
])
def test_no_configuration_or_request_folder_is_not_installed(world, plant, words):
    m, _run, _calls = world
    folder = os.path.dirname(H.config_of(m)["request"])
    plant(m)
    got = ask(_never)
    if os.path.isdir(folder):
        os.chmod(folder, 0o700)
    assert (got["ok"], got["code"], got["exit"]) == (False, "not_installed", None)
    assert words in got["words"] and C.INSTALL_STEP in got["words"]


def test_sudo_refusing_is_not_installed_and_leaves_no_request(world):
    m, _run, _calls = world
    got = ask(lambda argv, timeout: (1, "", "sudo: a password is required\n"))
    assert (got["ok"], got["code"], got["exit"]) == (False, "sudo_refused", 1)
    assert got["code"] in C.NOT_INSTALLED
    assert got["words"].startswith(
        f"sudo would not run {H.SCRIPT} without asking (exit 1: sudo: a password is "
        "required): its sudoers line is absent or names another account. A person installs")
    assert not os.path.exists(H.config_of(m)["request"])


def test_no_sudo_at_all_is_not_installed(world):
    def no_sudo(argv, timeout):
        raise FileNotFoundError(2, "No such file or directory")
    got = ask(no_sudo)
    assert got["code"] == "not_installed" and "could not be run (No such file or " \
                                              "directory)" in got["words"]


# ── one at a time, bounded, and never raising ────────────────────────────────────────────────

def test_a_second_request_at_once_is_refused_never_queued(world):
    m, _run, _calls = world
    folder = os.path.dirname(H.config_of(m)["request"])
    lock = os.open(os.path.join(folder, "lock"), os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        got = ask(_never)
    finally:
        os.close(lock)
    assert (got["ok"], got["code"], got["exit"]) == (False, "busy", None)
    assert os.listdir(folder) == ["lock"], "no request was written"


def test_the_bound_is_above_the_helper_s_own_and_fires_by_name(world, monkeypatch, tmp_path):
    m, _run, _calls = world
    worst = 3 * m.SS_TIMEOUT_S + m.GONE_BOUND_S + m.GONE_POLL_S
    assert worst == C.HELPER_WORST_S == 17.25 and C.BOUND_S == 20 > worst, \
        "the helper's own bounds fire first, and say which"
    slow = tmp_path / "slow"
    slow.write_text("#!/bin/sh\nsleep 5\n")
    os.chmod(slow, 0o755)
    monkeypatch.setattr(C, "SUDO", ())
    monkeypatch.setattr(C, "HELPER", str(slow))
    monkeypatch.setattr(C, "BOUND_S", 0.2)
    got = C.request(PEER, PORT, dry_run=True, run_id="run-7")
    assert (got["ok"], got["code"], got["exit"]) == (False, "caller_bound", None)
    assert got["words"] == (
        f"`{slow}` did not end within 0.2 s (above the 17.25 s the helper bounds its own work "
        "at (three `ss` runs at 5 s each, its 2 s read-back wait and one pause); reasoned, no "
        "run on a host has been timed yet): whether a session was closed is not known")
    assert not os.path.exists(H.config_of(m)["request"])


def test_the_module_s_own_run_takes_the_outcome_a_program_prints(world, monkeypatch, tmp_path):
    """`_run` itself, on a program of the test's where sudo and the helper would be."""
    program = tmp_path / "program"
    outcome = {"id": "run-7", "ok": False, "code": "no_match", "exit": 40, "words": "none",
               "tuple": {"local": LISTENER, "peer": "192.0.2.6:56221"},
               "finished": "2026-11-11T12:00:00Z"}
    program.write_text(f"#!/bin/sh\nprintf '%s\\n' '{json.dumps(outcome)}'\nexit 40\n")
    os.chmod(program, 0o755)
    monkeypatch.setattr(C, "SUDO", ())
    monkeypatch.setattr(C, "HELPER", str(program))
    assert C.request(PEER, PORT, dry_run=False, run_id="run-7") == {
        "ok": False, "code": "no_match", "exit": 40, "words": "none",
        "tuple": outcome["tuple"], "at": "2026-11-11T12:00:00Z"}


@pytest.mark.parametrize("dry_run", ["false", 0, None])
def test_a_dry_run_that_is_not_true_or_false_asks_nothing(world, dry_run):
    got = C.request(PEER, PORT, dry_run=dry_run, run_id="run-7", run=_never)
    assert (got["ok"], got["code"], got["exit"]) == (False, "caller_error", None)
    assert "not True or False, so nothing was asked" in got["words"]


def test_it_never_raises_into_its_caller(world):
    def broken(argv, timeout):
        raise RuntimeError("the stand-in broke")
    got = ask(broken)
    assert (got["ok"], got["code"], got["exit"]) == (False, "caller_error", None)
    assert got["words"] == "the close was not asked for: RuntimeError: the stand-in broke"


def test_nothing_calls_it_yet_but_the_dry_run_script():
    """Said in the module's header: no operation closes a session until the later slice."""
    import subprocess

    found = subprocess.run(["git", "grep", "--untracked", "-l", "-w", "-e", "collector_close",
                            "--", "modules", "routes", "app.py", "scripts", "templates"],
                           cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert sorted(found) == ["modules/heal/collector_close.py",
                             "scripts/nmas-collector-close-dry-run",
                             "scripts/nmas-collector-peers"]
    assert "NOT CALLED BY ANY OPERATION YET" in C.__doc__


# ── the peers, from committed intent ─────────────────────────────────────────────────────────

def fleet_intents(edit=None) -> dict:
    from tests import test_heal_diagnose as D
    from tests.test_heal_diagnose_stream import at_collector

    intents = copy.deepcopy(D._fleet())
    at_collector()(intents)
    if edit:
        edit(intents)
    return intents


def read_peers(intents, listener=LISTENER) -> dict:
    return C.peers(listener, networks=["lab"], intents_of=lambda network: (intents, ""))


def interface_v4(hv) -> set:
    """The device's interface IPv4 addresses, read off intent's own lines."""
    return {str(i["ipv4"]).split()[0].split("/")[0] for i in hv.get("interfaces") or []
            if re.match(r"\d+\.\d+\.\d+\.\d+", str(i.get("ipv4") or ""))}


def test_the_peers_are_the_addresses_of_the_devices_whose_telemetry_targets_the_listener():
    intents = fleet_intents()
    with_telemetry = [d for d, hv in intents.items() if hv.get("telemetry")]
    assert len(with_telemetry) >= 2 and "r2" in with_telemetry, "a floor on the population"
    got = read_peers(intents)
    assert got["ok"] and got["error"] == "" and got["failed"] == ""
    mine = interface_v4(intents["r2"])
    assert "192.0.2.6" in got["peers"] and len(mine) >= 2
    assert set(got["peers"]) == mine, "each of the one device's IPv4 addresses, no other's"
    others = set().union(*(interface_v4(hv) for d, hv in intents.items() if d != "r2"))
    assert not set(got["peers"]) & (others - mine)
    assert got["peers"] == sorted(got["peers"], key=lambda a: tuple(map(int, a.split("."))))
    assert "lab r2: a subscription names no source-address, so each of its interface " \
           "addresses is listed" in got["notes"]


def test_a_declared_source_address_is_the_one_peer():
    def edit(intents):
        for s in intents["r2"]["telemetry"]:
            s["settings"] = list(s["settings"]) + ["source-address 192.0.2.6"]
    got = read_peers(fleet_intents(edit))
    assert got["ok"] and got["peers"] == ["192.0.2.6"]
    assert not [n for n in got["notes"] if "no source-address" in n]


def test_a_device_with_no_ipv4_source_is_left_out_and_said(tmp_path):
    def edit(intents):
        for s in intents["r2"]["telemetry"]:
            s["settings"] = list(s["settings"]) + ["source-address 2001:db8:4::6"]
    got = read_peers(fleet_intents(edit))
    assert got["ok"] and got["peers"] == []
    assert got["notes"] == [
        "lab r2: 1 IPv6 address left out: an IPv6 peer is not served by the close helper yet",
        "lab r2: left out: intent gives it no IPv4 address a session to 192.0.2.10:57000 can "
        "come from"]


def test_another_listener_s_devices_are_not_peers():
    got = read_peers(fleet_intents(), listener="192.0.2.10:57001")
    assert got["ok"] and got["peers"] == [] and got["notes"] == []


@pytest.mark.parametrize("listener, words", [
    ("[2001:db8::10]:57000", "is an IPv6 listener: an IPv6 listener is not served by the "
                             "close helper yet"),
    ("192.0.2.10", "is not <IPv4 address>:<port>"),
    ("192.0.2.10:0", "the port 1 to 65535"),
    ("192.0.2.10:５７０００", "the port 1 to 65535"),
    ("collector.example:57000", "is not <IPv4 address>:<port>"),
])
def test_a_listener_that_is_not_an_ipv4_address_and_port_is_refused_by_name(listener, words):
    got = read_peers(fleet_intents(), listener=listener)
    assert (got["ok"], got["peers"], got["failed"]) == (False, [], "listener")
    assert words in got["error"]


def test_a_network_whose_intent_cannot_be_read_lists_nothing():
    intents = fleet_intents()
    got = C.peers(LISTENER, networks=["lab", "other"], intents_of=lambda n: (
        (intents, "") if n == "lab" else (None, "host_vars/r9.yml did not parse")))
    assert (got["ok"], got["peers"], got["failed"]) == (False, [], "intent")
    assert got["error"] == ("other's committed intent could not be read (host_vars/r9.yml did "
                            "not parse), so the list would miss its devices: nothing is listed")


def test_the_peers_read_every_network_through_the_committed_reader(monkeypatch):
    from modules.heal import bounce
    from modules.nsot import listref

    asked = []
    monkeypatch.setattr(listref, "names", lambda: ["one", "two"])
    monkeypatch.setattr(bounce, "committed_intents_of",
                        lambda network: asked.append(network) or (fleet_intents(), ""))
    got = C.peers(LISTENER)
    assert asked == ["one", "two"] and "192.0.2.6" in got["peers"]


# ── the two scripts ──────────────────────────────────────────────────────────────────────────

def script(name: str):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"),
                                                  os.path.join(ROOT, "scripts", name))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name,
                                                                             loader))
    loader.exec_module(module)
    return module


@pytest.mark.parametrize("answer, code, out, err", [
    ({"ok": True, "peers": ["192.0.2.6", "192.0.2.7"], "notes": ["lab r9: left out"],
      "error": "", "failed": ""}, 0, "192.0.2.6\n192.0.2.7\n", "lab r9: left out\n"),
    ({"ok": True, "peers": [], "notes": [], "error": "", "failed": ""}, 3, "",
     "FAILED: no device's committed telemetry targets 192.0.2.10:57000\n"),
    ({"ok": False, "peers": [], "notes": [], "error": "lab's committed intent could not be "
      "read", "failed": "intent"}, 2, "", "FAILED: lab's committed intent could not be read\n"),
    ({"ok": False, "peers": [], "notes": [], "error": "not a listener", "failed": "listener"},
     1, "", "FAILED: not a listener\n"),
])
def test_the_peers_script_prints_addresses_alone_and_says_the_rest_aside(monkeypatch, capsys,
                                                                         answer, code, out, err):
    asked = []
    monkeypatch.setattr(C, "peers", lambda listener: asked.append(listener) or answer)
    assert script("nmas-collector-peers").main([LISTENER]) == code
    got = capsys.readouterr()
    assert (got.out, got.err) == (out, err) and asked == [LISTENER]


@pytest.mark.parametrize("name, argv, code", [
    ("nmas-collector-peers", ["--help"], 0), ("nmas-collector-peers", [], 1),
    ("nmas-collector-peers", [LISTENER, "extra"], 1),
    ("nmas-collector-close-dry-run", ["--help"], 0),
    ("nmas-collector-close-dry-run", [PEER], 1),
    ("nmas-collector-close-dry-run", [PEER, "56221", "--real"], 1),
    ("nmas-collector-close-dry-run", [PEER, "56221", "--help"], 0),
])
def test_help_or_a_wrong_count_of_arguments_says_what_the_script_does_and_does_nothing(
        monkeypatch, capsys, name, argv, code):
    monkeypatch.setattr(C, "peers", _never)
    monkeypatch.setattr(C, "request", _never)
    module = script(name)
    assert module.main(argv) == code
    assert capsys.readouterr().out.strip() == module.__doc__.strip()


@pytest.mark.parametrize("answer, code", [
    ({"ok": True, "code": "would_close", "exit": 0, "words": "dry run: would close ...",
      "tuple": None, "at": "2026-11-11T12:00:00Z"}, 0),
    ({"ok": False, "code": "no_match", "exit": 40, "words": "no established session ...",
      "tuple": None, "at": "2026-11-11T12:00:00Z"}, 1),
    ({"ok": True, "code": "closed", "exit": 0, "words": "closed ...", "tuple": None,
      "at": "2026-11-11T12:00:00Z"}, 1),
])
def test_the_dry_run_script_only_ever_asks_for_a_dry_run(monkeypatch, capsys, answer, code):
    asked = []

    def request(peer, port, **kw):
        asked.append((peer, port, kw["dry_run"], kw["run_id"]))
        return answer
    monkeypatch.setattr(C, "request", request)
    module = script("nmas-collector-close-dry-run")
    assert module.main([PEER, "56221"]) == code
    ((peer, port, dry_run, run_id),) = asked
    assert (peer, port, dry_run) == (PEER, "56221", True)
    assert re.fullmatch(r"dry-run-\d+-\d+", run_id)
    assert capsys.readouterr().out == (
        f"{answer['code']} (exit {answer['exit']}) at 2026-11-11T12:00:00Z: "
        f"{answer['words']}\n")
    text = open(os.path.join(ROOT, "scripts", "nmas-collector-close-dry-run")).read()
    assert text.count("dry_run=True") == 1 and "dry_run=False" not in text
